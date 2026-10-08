# -*- coding: utf-8 -*-
"""合成信号只读筛查（W1·AI-019，2026-10-08）

法师令：「先跑只读筛查工具过一遍那 25 坐」。

## 性质：只读筛查工具，**不是判据**

  · 不写任何项目文件（报告 JSON 落 `output/sim_screen/`，该路径 `.gitignore:75` 已排除）
  · 不改任何阈值、不动 `qc_pipeline.py`／`congci_pipeline.py` 一字
  · **绝不执行 enqueue／drain**——只产候选清单与命令文本，喂不喂由法师裁
  · 结论＝组织证据；**判定权在法师**（`别编09:5` 层级纪律：AI 不产生真值）

## 为什么需要它

`qc_pipeline.py:388` 的 reasons 全集里**没有「合成信号鉴别」这一项**（可穷举：读盘失败／
samples 不一致／channels 不一致／时长／丢包／负丢包／干净度／坏通道）。
⇒ **QC 判 `ingest` ≠ 数据是真人真坐。** 实测：暂存池 57 个模拟器文件中 32 个 QC 现判 `ingest`，
含 6 个 5～55 分钟、标注 `baseline` 的长坐，只差一条入库命令即进正式库并喂从此。

## 签名来源（反推自 `console_server.py:317` `MonitorSimulator`，合成式 `:350-355`）

    (7+3·sin(2πt/90))·sin(2π·10·t+ch) + 1.2·sin(2π·20·t+0.7ch) + N(0,1.5)

⇒ 主峰 10.00Hz（被 1/90Hz 调幅）＋次峰 20.00Hz＋alpha 相对功率极高＋通道 std 极小且各通道近乎同值。
从 buffer 层注入，**录制后与真机 npz 同格式同目录，文件形态无法区分**，只能从频谱认。

## ⚠ 本工具的边界（必须随结果一起读）

**只打得中 `MonitorSimulator`。** `neuradock_simulator.py`（TCP 9600／7 通道 250Hz）输出的是
生理可信信号，**频谱无法证伪**。故：
  · 判「命中」＝**强证据**是 MonitorSimulator 那一路的合成件；
  · 判「未命中」＝**只等于**「不是 MonitorSimulator 那一路」，**不等于「一定是真人」**。
    NeuraDock 侧只能靠采集台账确证（本工具在 `note` 列如实报「频谱不可判」）。

## 用法

    python 合成信号筛查.py                     # 全量扫（暂存池＋归档位＋隔离位）
    python 合成信号筛查.py --no-qc             # 跳过 QC 现算（快，只出频谱签名）
    python 合成信号筛查.py --check FILE...      # 只查指定文件
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime

import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ZEN_ROOT = os.environ.get("CONGCI_PIPELINE_ZEN_ROOT") or r"D:\Project\Zen-EEG"
STAGING = os.path.join(SCRIPT_DIR, "muse2-repo", "muse2-master", "report")
OUT_DIR = os.path.join(SCRIPT_DIR, "output", "sim_screen")

# ── 频段与签名阈值（本窗依实测标定，**候法师定**；改这里＝改筛查口径，不是改 QC 判据）──
BANDS = {"delta": (0.5, 4.0), "theta": (4.0, 8.0), "alpha": (8.0, 12.0),
         "beta": (12.0, 30.0), "gamma": (30.0, 100.0)}
SIG_ALPHA_REL = 0.50      # A：alpha 相对功率 > 此值（实测真坐 0.040–0.110，模拟 0.94+）
SIG_PEAK_HZ = 10.0        # B：主峰
SIG_PEAK_TOL = 1.0
SIG_PEAK2_HZ = 20.0       # C：次峰
SIG_PEAK2_TOL = 1.5
SIG_STD_MAX_UV = 8.0      # D：通道 std 均值 < 此值（实测模拟 5.4–5.9µV，真坐 Oz 达 74.7µV）
PEAK_SEARCH = (1.0, 45.0)
NPERSEG = 1024

MIN_CANDIDATE_MIN = 10.0          # 第一梯队门槛：时长 ≥10 分钟
NEVER_FEED_TYPES = {"test", "smoke", "replay"}   # 与 congci_pipeline.py:90 同口径（只读引用，不改）


def _upstream_threshold(name, fallback):
    """向 `qc_pipeline` **只读取**现值，不在本工具里另立一份阈值副本（防两处漂移）。"""
    try:
        sys.path.insert(0, SCRIPT_DIR)
        import qc_pipeline
        v = getattr(qc_pipeline, name, None)
        return float(v) if v is not None else fallback
    except Exception:
        return fallback


# 下列两个数**不是本工具的判据**，只是"把 QC 自己算的描述量里值得法师看一眼的挑出来"的显示门槛，
# 取值直接引 qc_pipeline 现值：CH_MAINS_RATIO（QC 只 warn 不拒那条线）、MIN_CLEAN_RATIO（干净度下限）。
CH_MAINS_NOTE = _upstream_threshold("CH_MAINS_RATIO", 0.35)
MIN_CLEAN_NOTE = _upstream_threshold("MIN_CLEAN_RATIO", 0.60)


def _promotable(r):
    """晋升就绪＝meta 同时带 participant（P\\d{3}）与 session_type。

    依 `console_server.py:2648,2650` 两道校验：缺任一项，`/api/ingest` 直接 422，
    且 `_build_ingest_cmd`（:710-725）会往命令串里塞 `<P001>` 这类字面占位符，粘出去跑不通。
    """
    import re
    return bool(re.fullmatch(r"P\d{3}", (r.get("participant") or "").strip())
                and (r.get("session_type") or "").strip())


def _sfreq(npz, meta):
    """采样率三级取源，与 `zhiguan_cadence_bridge.py:264-292`（裁定⑤ 已追认）同口径。

    ⚠ 不得用 `np.median(np.diff(timestamps))`：新格式 timestamps 存绝对 Unix 纪元（~1.79e9），
    float64 在该量级精度仅 ~1e-6，逐点差分被压成量化噪声（实测 9.54e-07）→ 推出 1,048,576Hz。
    """
    try:
        s = float((meta or {}).get("sfreq") or 0)
        if s >= 50:
            return s, "meta.sfreq"
    except Exception:
        pass
    try:
        with np.load(npz, allow_pickle=False) as d:
            if "timestamps" in d.files:
                ts = np.asarray(d["timestamps"], dtype=float)
                span = float(ts[-1] - ts[0]) if ts.size > 1 else 0.0
                if span > 0:
                    return float(round((ts.size - 1) / span)), "inferred_from_span"
    except Exception:
        pass
    return 0.0, "unavailable"


def _meta(npz):
    """窄读 meta（object 数组须 pickle）；eeg 一律 allow_pickle=False，口径不混。"""
    try:
        with np.load(npz, allow_pickle=True) as d:
            if "meta" in d.files:
                m = d["meta"].item()
                return m if isinstance(m, dict) else {}
    except Exception:
        pass
    return {}


def spectral(eeg, sfreq):
    """四项签名 ＋ 描述量。返回 dict。"""
    from scipy.signal import welch
    n, c = eeg.shape
    nperseg = int(min(NPERSEG, max(64, n)))
    f, p = welch(eeg, fs=sfreq, nperseg=nperseg, axis=0, average="mean")
    p = np.asarray(p, dtype=float)
    if p.ndim == 1:
        p = p[:, None]
    p = p.mean(axis=1)                       # 通道平均

    def rel(lo, hi):
        m = (f >= lo) & (f < hi)
        return float(p[m].sum()) if m.any() else 0.0

    tot = sum(rel(lo, hi) for lo, hi in BANDS.values()) or 1.0
    bands = {k: rel(lo, hi) / tot for k, (lo, hi) in BANDS.items()}

    sel = (f >= PEAK_SEARCH[0]) & (f <= PEAK_SEARCH[1])
    fs, ps = f[sel], p[sel]
    if fs.size == 0:
        return {"ok": False}
    i1 = int(np.argmax(ps))
    peak = float(fs[i1])
    keep = np.abs(fs - peak) > SIG_PEAK_TOL
    if keep.any():
        i2 = int(np.argmax(ps[keep]))
        peak2 = float(fs[keep][i2])
    else:
        peak2 = 0.0

    std = eeg.std(axis=0, dtype=float)
    return {"ok": True, "peak_hz": round(peak, 3), "peak2_hz": round(peak2, 3),
            "bands": {k: round(v, 4) for k, v in bands.items()},
            "std_mean_uv": round(float(std.mean()), 3),
            "std_min_uv": round(float(std.min()), 3),
            "std_max_uv": round(float(std.max()), 3),
            "std_spread": round(float(std.max() / std.min()) if std.min() > 0 else 0.0, 3)}


def signature(sp):
    """四项签名判定 → (档位, 命中项列表)。"""
    if not sp.get("ok"):
        return "不可判", []
    hits = []
    if sp["bands"]["alpha"] > SIG_ALPHA_REL:
        hits.append("A:alpha%.3f>%.2f" % (sp["bands"]["alpha"], SIG_ALPHA_REL))
    if abs(sp["peak_hz"] - SIG_PEAK_HZ) <= SIG_PEAK_TOL:
        hits.append("B:峰%.2fHz≈10" % sp["peak_hz"])
    if abs(sp["peak2_hz"] - SIG_PEAK2_HZ) <= SIG_PEAK2_TOL:
        hits.append("C:次峰%.2fHz≈20" % sp["peak2_hz"])
    if sp["std_mean_uv"] < SIG_STD_MAX_UV:
        hits.append("D:std%.2fµV<%.0f" % (sp["std_mean_uv"], SIG_STD_MAX_UV))
    n = len(hits)
    return ("命中" if n == 4 else "存疑" if n >= 2 else "未命中"), hits


def eeg_hash(npz):
    """eeg 内容 sha16（前 16 位）——用于揪双写重复件。"""
    h = hashlib.sha256()
    with np.load(npz, allow_pickle=False) as d:
        a = np.asarray(d["eeg"])
        h.update(str(a.shape).encode())
        h.update(np.ascontiguousarray(a).tobytes())
    return h.hexdigest()[:16]


def _qc_extra(q):
    """从 QC 结果里取描述量。定稿 qc.json 是平铺结构，`assess()` 却嵌在 metrics 下——两种都兼容。

    这些数一律**转述 QC 自己算出来的值**，本工具不新立任何判据、不改任何阈值。
    """
    m = q.get("metrics") if isinstance(q.get("metrics"), dict) else {}
    cq = q.get("channel_quality") or m.get("channel_quality") or {}
    mains, mx, bad = [], [], []
    for ch, v in cq.items():
        if not isinstance(v, dict):
            continue
        if v.get("state") == "bad":
            bad.append(ch)
        try:
            if v.get("mains_ratio") is not None:
                mains.append(float(v["mains_ratio"]))
            if v.get("max_abs_uv") is not None:
                mx.append(float(v["max_abs_uv"]))
        except (TypeError, ValueError):
            pass
    cr = q.get("clean_ratio")
    if cr is None:
        cr = m.get("clean_ratio")
    return {"clean_ratio": cr,
            "mains_max": round(max(mains), 4) if mains else None,
            "max_abs_uv": round(max(mx), 1) if mx else None,
            "bad_channels": bad}


def qc_verdict(npz):
    """只读调 `qc_pipeline.assess()`（纯函数、返回 dict、不写盘；写盘的是 `write_qc_json`）。

    同目录 `qc.json` 优先（隔离位 `03_quality_control/quarantine/<sid>/` 自带定稿），
    其次归档位的 `03_quality_control/<sid>/qc.json`（两者与 `congci_pipeline._qc_verdict` 同口径）。
    ⚠ 顺序要紧：`congci_pipeline.py:326-330` 对隔离位路径多退一级 `..`，normpath 出
    `03_quality_control\\03_quality_control\\...` 恒不存在，故永远读不到定稿、落到 assess_cached，
    把定稿里的 `quarantined=True` 丢掉。本工具不复制那个 bug。
    """
    d = os.path.dirname(os.path.abspath(npz))
    sid = os.path.basename(d)
    probes = []
    if sid.startswith("ZEN-"):
        probes.append(os.path.join(d, "qc.json"))
        probes.append(os.path.normpath(os.path.join(d, "..", "..", "03_quality_control",
                                                    sid, "qc.json")))
    for qj in probes:
        if os.path.exists(qj):
            try:
                with open(qj, encoding="utf-8-sig") as fh:
                    q = json.load(fh)
                out = {"recommend": q.get("recommend"), "source": "定稿 qc.json",
                       "reasons": q.get("reasons") or [], "threshold_version": q.get("threshold_version"),
                       "quarantined": q.get("quarantined")}
                out.update(_qc_extra(q))
                return out
            except Exception as e:
                return {"recommend": None, "source": "定稿不可读:%s" % type(e).__name__, "reasons": []}
    try:
        sys.path.insert(0, SCRIPT_DIR)
        import qc_pipeline
        r = qc_pipeline.assess(npz)
        out = {"recommend": r.get("recommend"), "source": "assess 现算",
               "reasons": r.get("reasons") or [], "quarantined": None,
               "threshold_version": getattr(qc_pipeline, "THRESHOLD_VERSION", None)}
        out.update(_qc_extra(r))
        return out
    except Exception as e:
        return {"recommend": None, "source": "现算失败:%s:%s" % (type(e).__name__, e), "reasons": []}


def collect():
    """扫描面：暂存池 ＋ Zen-EEG 全域遍历（实测 2026-10-08 布局：
    归档位 `02_raw/<sid>/eeg_raw.npz`、隔离位 `03_quality_control/quarantine/<sid>/eeg_raw.npz`）。

    Zen-EEG 侧走 os.walk 全遍历而非列名，是为了不靠猜目录名——漏一个位就是漏一批数据。
    """
    out = []
    for p in sorted(os.listdir(STAGING)):
        if p.endswith(".npz"):
            out.append(("暂存池", os.path.join(STAGING, p), p))
    zen = []
    for base, dirs, files in os.walk(ZEN_ROOT):
        for f in files:
            if f.endswith(".npz"):
                zen.append(os.path.join(base, f))
    for npz in sorted(zen):
        rel = os.path.relpath(npz, ZEN_ROOT).replace("\\", "/")
        parts = rel.split("/")
        sid = parts[-2] if len(parts) >= 2 else parts[-1]
        if rel.startswith("02_raw/"):
            tag = "归档位"
        elif "/quarantine/" in ("/" + rel):
            tag = "隔离位"
        else:
            tag = "其他位"
        out.append((tag, npz, sid if sid.startswith("ZEN-") else os.path.basename(npz)))
    return out


def scan(files, do_qc=True, prog=True):
    rows = []
    for i, (tag, npz, name) in enumerate(files, 1):
        r = {"tag": tag, "name": name, "path": npz,
             "bytes": os.path.getsize(npz),
             "mtime": datetime.fromtimestamp(os.path.getmtime(npz)).strftime("%Y-%m-%d %H:%M")}
        try:
            with np.load(npz, allow_pickle=False) as d:
                if "eeg" not in d.files:
                    r["error"] = "缺 eeg 数组"
                    rows.append(r)
                    continue
                eeg = np.asarray(d["eeg"], dtype=float)
        except Exception as e:
            r["error"] = "%s: %s" % (type(e).__name__, e)
            rows.append(r)
            continue
        if eeg.ndim != 2 or eeg.shape[0] < 1:
            r["error"] = "eeg 非 (N,C) 二维"
            rows.append(r)
            continue

        meta = _meta(npz)
        sf, src = _sfreq(npz, meta)
        n, c = eeg.shape
        r.update(shape=[n, c], sfreq=sf, sfreq_src=src,
                 duration_min=round(n / sf / 60.0, 2) if sf else None,
                 participant=str(meta.get("participant") or ""),
                 scene=str(meta.get("scene") or ""),
                 session_type=str(meta.get("session_type") or ""),
                 note=str(meta.get("session_note") or meta.get("note") or "")[:120],
                 data_origin=("simulator" if "simulator" in json.dumps(meta, ensure_ascii=False, default=str).lower() else ""))
        r["eeg_sha16"] = eeg_hash(npz)
        if sf:
            sp = spectral(eeg, sf)
            r["spectral"] = sp
            r["sig_verdict"], r["sig_hits"] = signature(sp)
        else:
            r["spectral"] = {"ok": False}
            r["sig_verdict"], r["sig_hits"] = "sfreq不可得", []
        if do_qc:
            r["qc"] = qc_verdict(npz)
        rows.append(r)
        if prog and (i % 10 == 0 or i == len(files)):
            print("  ... %d/%d" % (i, len(files)), flush=True)
        del eeg
    return rows


def dedup(rows):
    """按 eeg_sha16 分组，标出逐位重复件。"""
    g = {}
    for r in rows:
        if r.get("eeg_sha16"):
            g.setdefault(r["eeg_sha16"], []).append(r["name"])
    for r in rows:
        k = r.get("eeg_sha16")
        peers = g.get(k, [])
        r["dup_of"] = [x for x in peers if x != r["name"]]
    return rows


def candidates(rows):
    """第一梯队候选（喂从此用）＝暂存池 ＋ 签名非「命中」＋ QC=ingest ＋ ≥10min ＋ 非 test ＋ 非重复。

    ⚠ 这只是**筛查口径**，不是准入判定。真正的准入闸是 `congci_pipeline.admit()`；
      本函数不代替它，也不调用它的写路径。
    """
    out = []
    for r in rows:
        if r.get("error"):
            continue
        if r["tag"] != "暂存池":
            continue
        if r.get("sig_verdict") == "命中":
            continue
        if (r.get("session_type") or "").lower() in NEVER_FEED_TYPES:
            continue
        if r.get("dup_of"):
            continue
        if not (r.get("duration_min") or 0) >= MIN_CANDIDATE_MIN:
            continue
        if (r.get("qc") or {}).get("recommend") != "ingest":
            continue
        out.append(r)
    return sorted(out, key=lambda x: -(x.get("duration_min") or 0))


def epoch_est(r):
    """从此可切 epoch 估算（`state_segmentation.py:58-70`：win=round(1.0*sfreq)，n_epochs=n//win）。"""
    if not r.get("sfreq") or not r.get("shape"):
        return None
    win = int(round(1.0 * r["sfreq"]))
    return r["shape"][0] // win if win else None


def main():
    ap = argparse.ArgumentParser(description="合成信号只读筛查（非判据）")
    ap.add_argument("--no-qc", action="store_true", help="跳过 QC 现算（快）")
    ap.add_argument("--check", nargs="+", metavar="NPZ", help="只查指定文件")
    ap.add_argument("--no-json", action="store_true")
    a = ap.parse_args()

    if a.check:
        # 用 collect() 的规范三元组回填位分与会话号，避免隔离位件在 --check 下显示成 "eeg_raw.npz"
        known = {os.path.normcase(os.path.abspath(p)): (t, p, n) for t, p, n in collect()}
        files = []
        for p in a.check:
            ap_ = os.path.abspath(p)
            got = known.get(os.path.normcase(ap_))
            if got:
                files.append(got)
                continue
            base = os.path.basename(ap_)
            parent = os.path.basename(os.path.dirname(ap_))
            files.append(("指定", ap_, parent if base == "eeg_raw.npz" else base))
    else:
        files = collect()
    print("=" * 78)
    print("合成信号只读筛查 ｜ %s ｜ 待扫 %d 件" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), len(files)))
    print("签名阈值：alpha_rel>%.2f ＋ 峰%.0f±%.1fHz ＋ 次峰%.0f±%.1fHz ＋ std<%.0fµV（四项全中＝命中）"
          % (SIG_ALPHA_REL, SIG_PEAK_HZ, SIG_PEAK_TOL, SIG_PEAK2_HZ, SIG_PEAK2_TOL, SIG_STD_MAX_UV))
    print("=" * 78)

    rows = dedup(scan(files, do_qc=not a.no_qc))

    hit = [r for r in rows if r.get("sig_verdict") == "命中"]
    doubt = [r for r in rows if r.get("sig_verdict") == "存疑"]
    ing = [r for r in rows if (r.get("qc") or {}).get("recommend") == "ingest"]
    hit_ing = [r for r in hit if (r.get("qc") or {}).get("recommend") == "ingest"]

    print()
    print("【一】总览")
    print("  扫描 %d 件：暂存池 %d／归档位 %d／隔离位 %d／指定 %d"
          % (len(rows), sum(1 for r in rows if r["tag"] == "暂存池"),
             sum(1 for r in rows if r["tag"] == "归档位"),
             sum(1 for r in rows if r["tag"] == "隔离位"),
             sum(1 for r in rows if r["tag"] == "指定")))
    print("  签名命中 %d 件｜存疑 %d 件｜未命中 %d 件" % (len(hit), len(doubt),
          sum(1 for r in rows if r.get("sig_verdict") == "未命中")))
    if not a.no_qc:
        print("  QC 判 ingest %d 件，**其中签名命中 %d 件**（＝QC 看不出来的合成件）" % (len(ing), len(hit_ing)))

    print()
    print("【二】签名命中 ＋ QC=ingest（＝活的污染门，按可切 epoch 降序）")
    if hit_ing:
        for r in sorted(hit_ing, key=lambda x: -(epoch_est(x) or 0)):
            print("  %-38s %6.1fmin  alpha=%.4f std=%5.2fµV  epoch=%-5s QC=%s  %s"
                  % (r["name"], r.get("duration_min") or 0, r["spectral"]["bands"]["alpha"],
                     r["spectral"]["std_mean_uv"], epoch_est(r),
                     (r.get("qc") or {}).get("recommend"), r.get("note", "")[:30]))
    else:
        print("  （无）")

    print()
    print("【三】逐位重复件（eeg 内容 sha16 相同）")
    dups = [r for r in rows if r.get("dup_of")]
    if dups:
        for r in dups:
            print("  %-38s 与 %s 逐位相同" % (r["name"], ", ".join(r["dup_of"])))
    else:
        print("  （无）")

    print()
    print("【四】归档位＋隔离位逐坐（法师投诉的「入库」现场）")
    for r in rows:
        if r["tag"] in ("归档位", "隔离位"):
            sp = r.get("spectral") or {}
            print("  [%s] %-24s %6.1fmin %dch sf=%s  签名=%-4s alpha=%s std=%s  QC=%s %s%s"
                  % (r["tag"], r["name"], r.get("duration_min") or 0, r["shape"][1],
                     r.get("sfreq"), r.get("sig_verdict"),
                     ("%.4f" % sp["bands"]["alpha"]) if sp.get("ok") else "-",
                     ("%.1f" % sp["std_mean_uv"]) if sp.get("ok") else "-",
                     (r.get("qc") or {}).get("recommend") or "-",
                     ("｜理由：" + "；".join((r.get("qc") or {}).get("reasons") or [])) if (r.get("qc") or {}).get("reasons") else "",
                     ("｜data_origin=" + r["data_origin"]) if r.get("data_origin") else ""))

    cand = candidates(rows) if not a.no_qc else []
    if not a.no_qc:
        print()
        print("【五】第一梯队候选（可喂从此，**候法师放行**）")
        print("  筛查口径：暂存池 ＋ 签名非命中 ＋ QC=ingest ＋ ≥%.0fmin ＋ 非 test/smoke/replay ＋ 非逐位重复"
              % MIN_CANDIDATE_MIN)
        print("  共 %d 坐；其中「晋升就绪」（meta 带 participant＋session_type，一点即入库）%d 坐"
              % (len(cand), sum(1 for r in cand if _promotable(r))))
        print("  clean／mains／maxµV 三列一律**转述 QC 自算值**，本工具不新立判据")
        tot = 0
        for i, r in enumerate(cand, 1):
            e = epoch_est(r) or 0
            tot += e
            q = r.get("qc") or {}
            print("  %2d. %-38s %6.1fmin %s type=%-9s part=%-5s alpha=%.4f std=%6.2fµV "
                  "clean=%s mains=%s maxµV=%s  可切epoch≈%d"
                  % (i, r["name"], r.get("duration_min") or 0,
                     "就绪" if _promotable(r) else "缺项",
                     r.get("session_type") or "-", r.get("participant") or "-",
                     r["spectral"]["bands"]["alpha"], r["spectral"]["std_mean_uv"],
                     ("%.3f" % q["clean_ratio"]) if q.get("clean_ratio") is not None else "-",
                     ("%.2f" % q["mains_max"]) if q.get("mains_max") is not None else "-",
                     ("%.0f" % q["max_abs_uv"]) if q.get("max_abs_uv") is not None else "-",
                     e))
        print("  合计可切 epoch ≈ %d" % tot)
        dirty = [(r["name"], (r.get("qc") or {}).get("mains_max")) for r in cand
                 if ((r.get("qc") or {}).get("mains_max") or 0) > CH_MAINS_NOTE]
        if dirty:
            print("  ⚠ 候选中 mains_ratio＞%.2f（QC 只 warn 不拒、reasons 为空）共 %d 件：%s"
                  % (CH_MAINS_NOTE, len(dirty),
                     "、".join("%s(mains=%.1f)" % (n, m) for n, m in dirty)))
            print("     这些件通过了 QC，但主成分可能是 50Hz 市电而非脑电——**是否剔除候法师裁**，本工具不代判。")
        tight = [r["name"] for r in cand
                 if (r.get("qc") or {}).get("clean_ratio") is not None
                 and (r["qc"]["clean_ratio"] - MIN_CLEAN_NOTE) < 0.02]
        if tight:
            print("  ⚠ 候选中 clean_ratio 距 %.2f 下限不足 2 个百分点（贴边过闸）%d 件：%s"
                  % (MIN_CLEAN_NOTE, len(tight), "、".join(tight)))

        print()
        print("【六】交集核验（法师令的核心问题）")
        cn = {r["name"] for r in cand}
        hn = {r["name"] for r in hit}
        inter = cn & hn
        print("  候选 %d 件 ∩ 签名命中 %d 件 ＝ %d 件  %s"
              % (len(cn), len(hn), len(inter), "✓ 空集，候选清单未被合成件污染" if not inter else "✗ 有交集：" + ", ".join(sorted(inter))))
        dd = [r["name"] for r in cand if r.get("dup_of")]
        print("  候选中逐位重复件 ＝ %d 件 %s" % (len(dd), "✓" if not dd else "✗ " + ", ".join(dd)))
        unk = [r["name"] for r in cand if r.get("sig_verdict") in ("存疑", "sfreq不可得", "不可判")]
        print("  候选中「存疑／不可判」＝ %d 件 %s" % (len(unk), "✓" if not unk else "⚠ 须人工复核：" + ", ".join(unk)))
        nd = [r["name"] for r in cand if not r.get("participant")]
        print("  候选中 meta 无 participant（老格式）＝ %d 件 %s" % (len(nd), "（admit 撤回闸对空 participant 恒过，如实报）" if nd else ""))
        print()
        print("  ⚠ 本清单**不等于**已准入。真正准入闸＝`congci_pipeline.admit()`；喂不喂候法师裁定。")
        print("  ⚠ 签名只打得中 MonitorSimulator；NeuraDock 模拟器频谱不可判，**候选中若有 NeuraDock 件须靠采集台账确证**。")
        nd2 = [r["name"] for r in cand if (r.get("shape") or [0, 0])[1] == 7]
        if nd2:
            print("     本批 7 通道（NeuraDock 侧）候选 %d 件：%s" % (len(nd2), ", ".join(nd2)))

    if cand:
        print()
        print("【七】候选清单（纯文件名，供后续处置引用）")
        for r in cand:
            print("%s%s" % (r["name"], "" if _promotable(r) else "   # 缺 participant/session_type"))

    if not a.no_json:
        os.makedirs(OUT_DIR, exist_ok=True)
        jp = os.path.join(OUT_DIR, "筛查_%s.json" % datetime.now().strftime("%Y%m%d_%H%M%S"))
        with open(jp, "w", encoding="utf-8") as fh:
            json.dump({"generated_at": datetime.now().isoformat(),
                       "tool": "合成信号筛查.py",
                       "disclaimer": "只读筛查，非判据；判定权在法师；签名只打得中 MonitorSimulator",
                       "thresholds": {"alpha_rel": SIG_ALPHA_REL, "peak": [SIG_PEAK_HZ, SIG_PEAK_TOL],
                                      "peak2": [SIG_PEAK2_HZ, SIG_PEAK2_TOL], "std_max_uv": SIG_STD_MAX_UV},
                       "rows": rows,
                       "candidates": [r["name"] for r in cand],
                       "hit_and_ingest": [r["name"] for r in hit_ing]},
                      fh, ensure_ascii=False, indent=1, default=str)
        print()
        print("报告 JSON（output/ 已被 .gitignore:75 排除，不污染索引）：")
        print(" ", jp)
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
