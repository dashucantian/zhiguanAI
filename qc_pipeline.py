# -*- coding: utf-8 -*-
"""质检（QC）唯一实现 —— P0-1 施工。

背景（2026-09-19/20 数据全链路盘查 · 缺陷 A-1／C-5）：
    旧实现把「干净数据比例」用正则从 `report.html` 里抠出来。而报告模板
    只在**检出噪声时**才渲染该字段（`muse_local_server.py:1025-1031`）——
    于是**越干净的会话越取不到干净度**：实测 12 个归档会话中，4 个有噪声的
    取到值、7 个完全干净的取到 `null`；09-19 全部 5 次新采集 `clean_ratio` 全为 null。

    同型的第二处：`qc.json.channel_quality` 恒为常量 `{ch:"ok"}`，
    **从未测过任何通道**（`ingest_session.py:326`）。

本模块的两个目标（对应 Gate-A 的两条）：
    A1  `clean_ratio` 直接由 npz 计算，**脱离 `report.html`**；
    A2  `channel_quality` 由真实指标判定，**不再是常量**。

设计约束（照项目纪律）：
    红线5  单一实现——`console_server.qc_assess` 与 `ingest_session` 都改为调用本模块，
           旧的 `_extract_report_metrics` 只保留给"报告页展示"，不参与任何判定；
    P6     弃权是一等值——测不出的通道写 `unknown`，**不许写 `ok`**；
    判语011 结论须可从数据重算——同一 npz 连算两次必须逐字节一致。

本模块只依赖 numpy（scipy 可选：有则用 scipy.signal.welch，无则用自实现的
分段 FFT 周期图，两者在本用途上等价）。
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime

# ── 版本与阈值（写进 qc.json，回答"这条质检是哪个阈值版本产生的"）────────

QC_VERSION = "1.1"
THRESHOLD_VERSION = "20260920"

# 分段口径：沿用报告模板既有值（10 s 窗 / 5 s 步长），**不改判据只改取值来源**
EPOCH_SECONDS = 10.0
EPOCH_STEP = 5.0

# 闸门阈值（与 console_server 原常量一致；此处为唯一源，那边改为 import）
MIN_DURATION_S = 30.0
MAX_PACKET_LOSS = 0.20
MIN_CLEAN_RATIO = 0.60

# 噪声判定：beta+gamma 相对功率占比超过此值即判该段为噪声（沿用 report_generator）
NOISE_BG_RATIO = 0.65

# 频段定义（与 report_generator.BANDS 一致）
BANDS = {"delta": (0.5, 4.0), "theta": (4.0, 8.0), "alpha": (8.0, 12.0),
         "beta": (12.0, 30.0), "gamma": (30.0, 45.0)}

# 通道质量判据（V1.0；实测指标 → ok/warn/bad/unknown）
CH_FLAT_STD_UV = 0.5          # 标准差低于此值 → 平线（电极脱落/未接触）
CH_RAIL_UV = 1800.0           # 绝对幅度超过此值 → 饱和/削顶
CH_MAINS_RATIO = 0.35         # 50Hz 功率占 45–55Hz 带内比例 → 工频污染
CH_RMS_BAD_UV = 500.0         # RMS 过高 → 运动/肌电主导
CH_MIN_SAMPLES = 64           # 样本太少 → unknown（弃权）

# IAF（个体 α 峰频，2026-10-01 W3人机建构-01 增）：静息闭眼 α 段主峰位置，
# 用法照 Mikhaylets et al., Sci Rep (2026) 16:23560 §2.1（冥想前后静息测算取均）。
# 仅作描述性指标输出，**不参与 recommend 判定**（守"判据来源唯一"）。
IAF_SEARCH = (7.0, 13.0)      # 峰值搜索带（略宽于 BANDS["alpha"]，容个体差异）
IAF_MIN_CONTRAST = 1.3        # 峰功率 / 带内均值 低于此值视为无明确峰（弃权）


def _now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


# ── 频段功率（scipy 可选）──────────────────────────────────────────────

def _psd(data, sfreq):
    """返回 (freqs, psd)，psd shape=(n_freq, n_chan)。优先 scipy，缺失则自实现。"""
    try:
        from scipy.signal import welch
        return welch(data, sfreq, nperseg=int(sfreq), axis=0)
    except Exception:
        pass
    import numpy as np
    n = data.shape[0]
    nper = max(8, int(sfreq))
    if n < nper:
        nper = n
    step = nper // 2 or 1
    win = np.hanning(nper)[:, None]
    segs = []
    for start in range(0, n - nper + 1, step):
        seg = data[start:start + nper, :] * win
        segs.append(np.abs(np.fft.rfft(seg, axis=0)) ** 2)
    if not segs:
        seg = data[:nper, :] * win[:data[:nper].shape[0]]
        segs = [np.abs(np.fft.rfft(seg, axis=0)) ** 2]
    psd = np.mean(segs, axis=0) / (sfreq * np.sum(np.hanning(nper) ** 2))
    freqs = np.fft.rfftfreq(nper, d=1.0 / sfreq)
    return freqs, psd


def _band_relative(freqs, psd, sfreq):
    """返回 (rel_dict, mains_ratio, total) —— rel 为各频段相对功率（逐通道）。"""
    import numpy as np
    abs_power = {}
    total = np.zeros(psd.shape[1])
    for band, (lo, hi) in BANDS.items():
        mask = (freqs >= lo) & (freqs <= hi)
        if not mask.any():
            abs_power[band] = np.full(psd.shape[1], 1e-12)
            continue
        if hasattr(np, "trapezoid"):
            bp = np.trapezoid(psd[mask], freqs[mask], axis=0)
        else:
            bp = np.trapz(psd[mask], freqs[mask], axis=0)
        abs_power[band] = np.maximum(bp, 1e-12)
        total += bp
    total_safe = np.maximum(total, 1e-12)
    rel = {b: abs_power[b] / total_safe for b in BANDS}
    # 工频占比：45–55 Hz 与全带之比（50Hz 陷波缺失会显著抬高）
    m_mask = (freqs >= 45.0) & (freqs <= 55.0)
    if m_mask.any():
        if hasattr(np, "trapezoid"):
            mains = np.trapezoid(psd[m_mask], freqs[m_mask], axis=0)
        else:
            mains = np.trapz(psd[m_mask], freqs[m_mask], axis=0)
    else:
        mains = np.zeros(psd.shape[1])
    all_mask = (freqs >= 0.5) & (freqs <= 45.0)
    if hasattr(np, "trapezoid"):
        allp = np.trapezoid(psd[all_mask], freqs[all_mask], axis=0)
    else:
        allp = np.trapz(psd[all_mask], freqs[all_mask], axis=0)
    mains_ratio = mains / np.maximum(allp, 1e-12)
    return rel, mains_ratio, total_safe


# ── 通道质量（A2：实测，不再恒 ok）────────────────────────────────────

def _channel_quality(eeg, sfreq, channels):
    """逐通道质量：ok / warn / bad / unknown（测不出即 unknown，P6 弃权）。"""
    import numpy as np
    out = {}
    n = eeg.shape[0]
    if n < CH_MIN_SAMPLES or sfreq <= 0:
        return {ch: {"state": "unknown",
                     "reason": f"样本不足（{n} < {CH_MIN_SAMPLES}）"} for ch in channels}
    try:
        freqs, psd = _psd(eeg, sfreq)
        _, mains_ratio, _ = _band_relative(freqs, psd, sfreq)
    except Exception as ex:
        return {ch: {"state": "unknown",
                     "reason": f"频域计算失败：{type(ex).__name__}"} for ch in channels}
    for i, ch in enumerate(channels):
        if i >= eeg.shape[1]:
            out[ch] = {"state": "unknown", "reason": "通道索引超出数据列数"}
            continue
        col = eeg[:, i]
        std = float(np.std(col))
        rms = float(np.sqrt(np.mean(col ** 2)))
        mx = float(np.max(np.abs(col)))
        mains = float(mains_ratio[i]) if i < len(mains_ratio) else float("nan")
        metrics = {"std_uv": round(std, 3), "rms_uv": round(rms, 3),
                   "max_abs_uv": round(mx, 1), "mains_ratio": round(mains, 4)}
        if std < CH_FLAT_STD_UV:
            out[ch] = {"state": "bad", "reason": f"平线（std={std:.3f}µV）", **metrics}
        elif mx > CH_RAIL_UV:
            out[ch] = {"state": "bad", "reason": f"疑似饱和（max={mx:.0f}µV）", **metrics}
        elif rms > CH_RMS_BAD_UV:
            out[ch] = {"state": "bad", "reason": f"幅值过高（rms={rms:.0f}µV）", **metrics}
        elif mains > CH_MAINS_RATIO:
            out[ch] = {"state": "warn", "reason": f"工频污染（50Hz占比{mains:.0%}）", **metrics}
        else:
            out[ch] = {"state": "ok", "reason": "", **metrics}
    return out


# ── IAF（个体 α 峰频：描述性指标，不进判定链）──────────────────────────

def compute_iaf(eeg, sfreq, channels):
    """逐通道 α 峰频 + 全通道中位 IAF。

    返回 {"per_channel": {ch: {"iaf_hz": x|null, "contrast": c|null}},
          "iaf_hz": x|null}。测不出（带内无明确峰/样本不足）如实置 null。
    """
    import numpy as np
    out = {"per_channel": {}, "iaf_hz": None}
    n = eeg.shape[0]
    win_needed = int(IAF_SEARCH[0] * 4)      # 至少 4 个最低搜索频率的周期
    if n < max(CH_MIN_SAMPLES, win_needed) or sfreq <= 0:
        for ch in channels:
            out["per_channel"][ch] = {"iaf_hz": None, "contrast": None}
        return out
    try:
        freqs, psd = _psd(eeg, sfreq)
    except Exception:
        for ch in channels:
            out["per_channel"][ch] = {"iaf_hz": None, "contrast": None}
        return out
    lo, hi = IAF_SEARCH
    mask = (freqs >= lo) & (freqs <= hi)
    vals = []
    for i, ch in enumerate(channels):
        if i >= psd.shape[1] or not mask.any():
            out["per_channel"][ch] = {"iaf_hz": None, "contrast": None}
            continue
        p = psd[mask, i]
        f = freqs[mask]
        peak_i = int(np.argmax(p))
        contrast = float(p[peak_i] / max(np.mean(p), 1e-24))
        if contrast < IAF_MIN_CONTRAST:
            out["per_channel"][ch] = {"iaf_hz": None, "contrast": round(contrast, 3)}
            continue
        iaf = float(f[peak_i])
        out["per_channel"][ch] = {"iaf_hz": round(iaf, 2),
                                  "contrast": round(contrast, 3)}
        vals.append(iaf)
    if vals:
        out["iaf_hz"] = round(float(np.median(vals)), 2)
    return out


# ── 分段干净度（A1：由 npz 实算）──────────────────────────────────────

def _epochs(eeg, sfreq):
    """按 EPOCH_SECONDS / EPOCH_STEP 切段，返回 [(start, stop), ...]。"""
    win = int(round(EPOCH_SECONDS * sfreq))
    step = int(round(EPOCH_STEP * sfreq))
    if win <= 0 or step <= 0:
        return []
    out = []
    n = eeg.shape[0]
    start = 0
    while start + win <= n:
        out.append((start, start + win))
        start += step
    return out


def _clean_stats(eeg, sfreq):
    """返回 (noise_epochs, total_epochs, clean_ratio, per_epoch_noise[]) 。

    噪声判定沿用报告模板口径：该段 beta+gamma 相对功率 > NOISE_BG_RATIO，
    且**所有通道**都超阈才判该段为噪声（与 report_generator 的 all_noisy 一致）。
    """
    import numpy as np
    spans = _epochs(eeg, sfreq)
    if not spans:
        return 0, 0, None, []
    flags = []
    for (a, b) in spans:
        chunk = eeg[a:b, :]
        try:
            freqs, psd = _psd(chunk, sfreq)
            rel, _, _ = _band_relative(freqs, psd, sfreq)
            bg = rel["beta"] + rel["gamma"]
            flags.append(bool(np.all(bg > NOISE_BG_RATIO)))
        except Exception:
            flags.append(None)          # 该段不可判定，不计入 clean 也不计噪声
    decided = [f for f in flags if f is not None]
    total = len(decided)
    noise = sum(1 for f in decided if f)
    ratio = (1.0 - noise / total) if total else None
    return noise, total, ratio, flags


# ── 主入口 ────────────────────────────────────────────────────────────

def assess(npz_path, thresholds=None):
    """质检唯一入口。返回 dict（可直接写 qc.json）。

    与原 `console_server.qc_assess` 的差别：
      · `clean_ratio` 由 npz 计算，**不读 report.html**；
      · `channel_quality` 为实测结果（dict），而非常量 "ok"；
      · 增 `qc_version` / `threshold_version` / `thresholds` / `generated_by`。
    """
    import numpy as np
    th = {"min_duration_s": MIN_DURATION_S,
          "max_packet_loss": MAX_PACKET_LOSS,
          "min_clean_ratio": MIN_CLEAN_RATIO}
    if thresholds:
        th.update(thresholds)

    reasons = []
    metrics = {}
    base = {"qc_version": QC_VERSION, "threshold_version": THRESHOLD_VERSION,
            "thresholds": th, "generated_by": f"qc_pipeline@{THRESHOLD_VERSION}",
            "generated_at": _now()}

    try:
        with np.load(npz_path, allow_pickle=True) as d:
            meta = d["meta"].item()
            eeg = np.asarray(d["eeg"])
    except Exception as ex:
        return {**base, "recommend": "quarantine",
                "reasons": [f"无法读取 npz：{type(ex).__name__}: {ex}"],
                "metrics": metrics}

    sfreq = float(meta.get("sfreq") or 0.0)
    channels = list(meta.get("channels") or [])
    if not channels:
        channels = [f"ch{i}" for i in range(eeg.shape[1])]
    samples = int(meta.get("samples") or eeg.shape[0])
    duration = float(meta.get("duration") or 0.0)

    # 长度自洽性（此前从不校验 —— 见盘查 C-2）
    if samples != int(eeg.shape[0]):
        metrics["samples_mismatch"] = {"meta_samples": samples,
                                       "eeg_rows": int(eeg.shape[0])}
        reasons.append(f"meta.samples({samples}) 与 eeg 行数({eeg.shape[0]}) 不一致")
    if len(channels) != eeg.shape[1]:
        metrics["channels_mismatch"] = {"meta_channels": len(channels),
                                        "eeg_cols": int(eeg.shape[1])}
        reasons.append(f"meta.channels 数({len(channels)}) 与 eeg 列数({eeg.shape[1]}) 不一致")

    eff = samples / duration if duration > 0 else 0.0
    loss = round(1.0 - eff / sfreq, 4) if sfreq > 0 else None
    metrics.update({"samples": samples, "duration": round(duration, 1),
                    "sfreq": sfreq, "channels": channels,
                    "effective_hz": round(eff, 2),
                    "packet_loss_rate": loss})

    # 会话跨度对账（2026-09-25 法师裁定：**并列显示、不替换**上项口径）
    #   缘起：09-25 首场真机会话尾段断流 12.6 分钟（末样本 17:36:09.9，会话至 17:48:44），
    #   而 packet_loss_rate 的分母是"样本自身跨度"（duration），断流后分母同步停住 →
    #   真丢 39% 只报 1.33%，判据结构性失明（定位报告：…样本差定位报告_尾段断流_v1.md）。
    #   本处**只新增派生字段供并列显示**；是否据其产生 reasons/影响 recommend，属另一裁定，
    #   未获裁前**不接入判定链**（守"判据来源唯一"）。
    _span_s = None
    _sp_start = meta.get("recording_started_at_epoch")
    _sp_end = meta.get("recording_ended_at_epoch")
    try:
        if _sp_start is not None and _sp_end is not None and float(_sp_end) > float(_sp_start):
            _span_s = float(_sp_end) - float(_sp_start)
    except (TypeError, ValueError):
        _span_s = None
    if _span_s and _span_s > 0:
        _span_eff = samples / _span_s
        metrics["session_span_s"] = round(_span_s, 1)
        metrics["session_span_hz"] = round(_span_eff, 2)
        metrics["span_loss_rate"] = round(1.0 - _span_eff / sfreq, 4) if sfreq > 0 else None
    if duration < th["min_duration_s"]:
        reasons.append(f"时长 {duration:.0f}s 低于下限 {th['min_duration_s']:.0f}s")
    if loss is not None and loss > th["max_packet_loss"]:
        reasons.append(f"丢包率 {loss:.0%} 超过上限 {th['max_packet_loss']:.0%}")
    elif loss is not None and loss < 0:
        # 物理上不可能（eff > sfreq）——此前会静默写出负值（盘查 C-3）
        reasons.append(f"丢包率为负（{loss:.2%}）：有效采样率 {eff:.2f}Hz 高于标称 "
                       f"{sfreq:.0f}Hz，请核对 meta.duration 口径")

    # A1：干净度由 npz 实算
    try:
        noise, total, ratio, _ = _clean_stats(eeg, sfreq)
        metrics["noise_epochs"] = f"{noise}/{total}" if total else ""
        metrics["noise_epochs_n"] = noise
        metrics["total_epochs"] = total
        metrics["clean_ratio"] = round(ratio, 4) if ratio is not None else None
        if ratio is not None and ratio < th["min_clean_ratio"]:
            reasons.append(f"干净数据 {ratio:.0%} 低于下限 {th['min_clean_ratio']:.0%}")
    except Exception as ex:
        metrics["clean_ratio"] = None
        metrics["clean_ratio_error"] = f"{type(ex).__name__}: {ex}"
        reasons.append("干净度计算失败（不可判定）")

    # A2：通道质量实测
    try:
        metrics["channel_quality"] = _channel_quality(eeg, sfreq, channels)
    except Exception as ex:
        metrics["channel_quality"] = {ch: {"state": "unknown",
                                           "reason": f"{type(ex).__name__}"}
                                      for ch in channels}

    # IAF（QC v1.1 增）：描述性指标，不进 reasons、不影响 recommend
    try:
        metrics["iaf"] = compute_iaf(eeg, sfreq, channels)
    except Exception:
        metrics["iaf"] = {"per_channel": {ch: {"iaf_hz": None, "contrast": None}
                                          for ch in channels},
                          "iaf_hz": None}
    bad = [ch for ch, v in (metrics.get("channel_quality") or {}).items()
           if isinstance(v, dict) and v.get("state") == "bad"]
    if bad:
        reasons.append(f"通道质量不合格：{'、'.join(bad)}")

    # 稳定指纹：同 npz 连算两次必须一致（Gate-A 的 A3）
    metrics["eeg_sha256_16"] = _digest(eeg)

    return {**base, "recommend": "quarantine" if reasons else "ingest",
            "reasons": reasons, "metrics": metrics}


def _digest(arr):
    """对数组内容取短指纹（只用于一致性自检，不替代文件 sha256）。"""
    import numpy as np
    if not isinstance(arr, np.ndarray):
        arr = np.asarray(arr)
    h = hashlib.sha256()
    h.update(str(arr.shape).encode())
    h.update(str(arr.dtype).encode())
    a = np.ascontiguousarray(arr)
    h.update(memoryview(a.view(np.uint8)) if a.dtype.itemsize else b"")
    return h.hexdigest()[:16]


def extract_report_metrics(report_path):
    """**仅供报告页展示**，不参与任何判定（A-1 修复后判定一律走 assess）。

    保留此函数只为兼容既有展示需求；新代码不得用它生成 qc.json。
    """
    import re as _re
    metrics = {}
    if not report_path or not os.path.exists(report_path):
        return metrics
    try:
        with open(report_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except Exception:
        return metrics
    aliases = {"noise_epochs": ("Noise epochs", "噪声段数"),
               "clean_pct": ("Clean data", "干净数据比例", "干净数据占比")}
    for canon, labels in aliases.items():
        for label in labels:
            m = _re.search(_re.escape(label) +
                           r'</span><br>\s*<span class="value"[^>]*>([^<]+)</span>',
                           text)
            if m:
                metrics[canon] = m.group(1).strip()
                break
    return metrics


def write_qc_json(npz_path, out_path, thresholds=None, extra=None):
    """算并落盘 qc.json（原子写：tmp → os.replace）。返回结果 dict。

    落盘内容含 `recommend`／`reasons`——**这是审计追踪的必需项**：
    `reasons` 说明"为什么建议隔离"，此前只存在于调用方的瞬时变量里、
    归档后无据可查（2026-09-20 施工中发现并修）。
    """
    res = assess(npz_path, thresholds=thresholds)
    doc = {"recommend": res["recommend"], "reasons": list(res["reasons"])}
    doc.update(res["metrics"])
    doc.update({k: res[k] for k in ("qc_version", "threshold_version",
                                    "thresholds", "generated_by", "generated_at")})
    if extra:
        doc.update(extra)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    os.replace(tmp, out_path)
    return doc


# ── 结果缓存（P0-1 配套；盘查 C-1）────────────────────────────────────
#
# 为什么必须做：`/api/reports` 每次请求都对**全部暂存 npz** 跑一次 assess。
# 实测 102 个会话 ≈ 12.3 s（均 121 ms），而前端 `api()` 超时是 15 s——
# 即"改成实算"会把历史页推到超时边缘。缓存按
# (路径, mtime_ns, size, THRESHOLD_VERSION) 命中，文件一变即失效。

_CACHE_DIR = None
_MEM_CACHE = {}
_MEM_MAX = 256


def cache_dir():
    global _CACHE_DIR
    if _CACHE_DIR is None:
        _CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  ".qc_cache")
    return _CACHE_DIR


def _cache_key(npz_path, thresholds):
    st = os.stat(npz_path)
    raw = "|".join([os.path.abspath(npz_path), str(st.st_mtime_ns),
                    str(st.st_size), QC_VERSION, THRESHOLD_VERSION,
                    json.dumps(thresholds or {}, sort_keys=True)])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def assess_cached(npz_path, thresholds=None):
    """带缓存的 assess。语义与 assess 完全一致，仅在文件未变时省去重算。"""
    try:
        key = _cache_key(npz_path, thresholds)
    except Exception:
        return assess(npz_path, thresholds=thresholds)
    if key in _MEM_CACHE:
        return _MEM_CACHE[key]
    p = os.path.join(cache_dir(), key + ".json")
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                res = json.load(f)
            _MEM_CACHE[key] = res
            return res
        except Exception:
            pass
    res = assess(npz_path, thresholds=thresholds)
    _MEM_CACHE[key] = res
    if len(_MEM_CACHE) > _MEM_MAX:
        for k in list(_MEM_CACHE)[: _MEM_MAX // 4]:
            _MEM_CACHE.pop(k, None)
    try:
        os.makedirs(cache_dir(), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False)
        os.replace(tmp, p)
    except Exception:
        pass          # 缓存是加速项，失败绝不影响判定（同契约纪律）
    return res


# ── 自测（Gate-A 的 A1/A2/A3/A4 判据的最小化验证）─────────────────────

def _selftest():
    import tempfile
    import numpy as np
    fails = []
    root = os.path.dirname(os.path.abspath(__file__))
    tmp = os.path.join(root, "_analysis_tmp", "qc_selftest")
    os.makedirs(tmp, exist_ok=True)
    sfreq = 256.0
    n = int(sfreq * 60)
    t = np.arange(n) / sfreq
    rng = np.random.default_rng(42)

    def save(name, col, sf=sfreq, ch=None):
        eeg = np.column_stack([col] * 4)
        p = os.path.join(tmp, name)
        np.savez(p, eeg=eeg, timestamps=t[:eeg.shape[0]],
                 meta={"timestamp": "2026-09-20T00:00:00", "sfreq": sf,
                       "channels": ch or ["TP9", "AF7", "AF8", "TP10"],
                       "device": "test", "samples": eeg.shape[0],
                       "duration": float(eeg.shape[0] / sf)})
        return p

    # ① 干净信号：10Hz 正弦 + 轻噪声 → clean_ratio 应接近 1 且**不为 None**
    clean = 8 * np.sin(2 * np.pi * 10 * t) + rng.normal(0, 1.0, n)
    p1 = save("clean.npz", clean)
    r1 = assess(p1)
    cr = r1["metrics"].get("clean_ratio")
    if cr is None:
        fails.append("① 干净会话 clean_ratio 为 None（A-1 未修复）")
    elif cr < 0.9:
        fails.append(f"① 干净会话 clean_ratio={cr} 偏低（应接近 1）")

    # ② 确定性：连算两次必须完全一致（A3）
    r2 = assess(p1)
    if json.dumps(r1["metrics"], sort_keys=True) != json.dumps(r2["metrics"], sort_keys=True):
        fails.append("② 同一 npz 两次计算结果不一致（A3 失败）")

    # ③ 坏通道必须被报出（A2：不再恒 ok）
    eeg_bad = np.column_stack([
        8 * np.sin(2 * np.pi * 10 * t) + rng.normal(0, 1.0, n),  # ok
        np.zeros(n),                                             # 平线 → bad
        np.full(n, 5000.0),                                      # 饱和 → bad
        8 * np.sin(2 * np.pi * 10 * t) + rng.normal(0, 1.0, n),
    ])
    p2 = os.path.join(tmp, "badchan.npz")
    np.savez(p2, eeg=eeg_bad, timestamps=t,
             meta={"timestamp": "2026-09-20T00:00:00", "sfreq": sfreq,
                   "channels": ["TP9", "AF7", "AF8", "TP10"], "device": "test",
                   "samples": n, "duration": float(n / sfreq)})
    r3 = assess(p2)
    cq = r3["metrics"].get("channel_quality") or {}
    states = {c: (v.get("state") if isinstance(v, dict) else v) for c, v in cq.items()}
    if states.get("AF7") != "bad":
        fails.append(f"③ 平线通道未被判 bad（AF7={states.get('AF7')}）")
    if states.get("AF8") != "bad":
        fails.append(f"③ 饱和通道未被判 bad（AF8={states.get('AF8')}）")
    if not any(s == "ok" for s in states.values()):
        fails.append(f"③ 好通道未判 ok（states={states}）")
    if not r3["reasons"]:
        fails.append("③ 有坏通道但 reasons 为空")

    # ④ 版本字段必须落盘（A4）
    for k in ("qc_version", "threshold_version", "thresholds"):
        if k not in r1:
            fails.append(f"④ 缺版本字段 {k}")

    # ⑤ 极短会话：不可判定要如实（P6 弃权）
    p3 = save("tooshort.npz", clean[:100])
    r4 = assess(p3)
    if r4["metrics"].get("clean_ratio") is not None:
        fails.append("⑤ 过短会话不应给出 clean_ratio（应弃权为 None）")
    if r4["recommend"] != "quarantine":
        fails.append("⑤ 过短会话应建议隔离")

    # ⑥ 通道数与列数不一致必须报出（C-2）
    p4 = os.path.join(tmp, "mismatch.npz")
    np.savez(p4, eeg=eeg_bad, timestamps=t,
             meta={"timestamp": "2026-09-20T00:00:00", "sfreq": sfreq,
                   "channels": ["TP9", "AF7"], "device": "test",
                   "samples": n, "duration": float(n / sfreq)})
    r5 = assess(p4)
    if not any("channels" in x for x in r5["reasons"]):
        fails.append("⑥ 通道数不一致未被报出")

    # ⑦ IAF（QC v1.1）：10Hz 正弦的干净会话应测得 α 峰 ≈10Hz，且不影响判定
    iaf1 = r1["metrics"].get("iaf") or {}
    got = iaf1.get("iaf_hz")
    if got is None or abs(got - 10.0) > 0.5:
        fails.append(f"⑦ 干净会话 IAF 应 ≈10Hz（得 {got}）")
    r_bad = assess(p2)
    iaf_bad = (r_bad["metrics"].get("iaf") or {}).get("iaf_hz")
    if iaf_bad is None or abs(iaf_bad - 10.0) > 0.5:
        fails.append(f"⑦ 含坏通道会话仍应从好通道测得 IAF（得 {iaf_bad}）")
    if r1["recommend"] != "ingest":
        fails.append("⑦ IAF 增列不应改变干净会话的 ingest 判定")

    if fails:
        for x in fails:
            print("FAIL:", x)
        return 1
    print("PASS: qc_pipeline 自测通过（A1 干净度实算 / A2 通道质量实测 / "
          "A3 确定性 / A4 版本字段 / P6 弃权 / C-2 长度自洽 / "
          "QC1.1 IAF 实算且不进判定链）")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_selftest())
