"""第一重分析：法师 VR 场景标准脑电数据深度分析（2026-09-10）

口径原则：完全复用项目既有 report_generator（频段定义、Welch 参数、状态分类），
不自立标准。另按 vr_feedback.html 的 CAL 标定把数据映射到 VR 参数空间（S.a/S.th），
检验标定区间是否匹配法师真实禅修状态——这是本轮迭代的关键依据。

数据：local_20260910_121639.npz（22分钟）、local_20260910_130105.npz（42分钟）
两份均含 eeg（1-40Hz带通后）与 eeg_pre_filter（原始）——可做滤波前后对照。
"""
import json
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.signal import welch

# ── 路径 ──────────────────────────────────────────────
RG_DIR = r"C:\Users\tiand\OneDrive\zhiguanAI\muse2-repo\muse2-master\muse-cloud-server"
sys.path.insert(0, RG_DIR)
import report_generator as rg  # noqa: E402

REPORT_DIR = r"C:\Users\tiand\OneDrive\zhiguanAI\muse2-repo\muse2-master\report"
OUT = r"C:\Users\tiand\OneDrive\zhiguanAI\output\20260910_VR标准模板三重分析"
FIG = os.path.join(OUT, "图")

# 中文字体
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# ── vr_feedback.html 的 CAL 标定（必须与前端一致，改动需同步）──
CAL = {
    "relALo": 0.0303, "relASpan": 0.0582,     # 安定度 S.a ← 相对Alpha占比
    "ltBLo": -0.8198, "ltBSpan": 1.2105,      # 沉掉轴 S.th ← log10(theta/beta)
}
BANDS = rg.BANDS                 # Delta .5-4 / Theta 4-8 / Alpha 8-12 / Beta 12-30 / Gamma 30-45
EPOCH_S, EPOCH_STEP = rg.EPOCH_SECONDS, rg.EPOCH_STEP   # 10s 窗、5s 步
NOISE_BG_RATIO = rg.NOISE_BG_RATIO                      # beta+gamma 相对功率 > 0.65 判噪声

SESSIONS = [
    ("121639", "local_20260910_121639.npz", "会话A 22分钟"),
    ("130105", "local_20260910_130105.npz", "会话B 42分钟"),
]


def clamp01(v):
    return np.clip(v, 0.0, 1.0)


def load_npz(name):
    """读 npz，返回 dict：滤波后数据、原始数据、通道、采样率、时间戳。"""
    path = os.path.join(REPORT_DIR, name)
    with np.load(path, allow_pickle=True) as z:
        meta = z["meta"].item() if "meta" in z.files else {}
        d = {
            "eeg": np.asarray(z["eeg"], dtype=np.float64),
            "raw": np.asarray(z["eeg_pre_filter"], dtype=np.float64) if "eeg_pre_filter" in z.files else None,
            "ts": np.asarray(z["timestamps"], dtype=np.float64) if "timestamps" in z.files else None,
            "meta": meta,
            "channels": meta.get("channels") or list(BANDS and rg.CHANNELS),
            "sfreq": float(meta.get("sfreq") or rg.SFREQ),
        }
    return d


def epoch_iter(eeg, sfreq):
    """按项目口径切 epoch：10s 窗、5s 步。产出 (idx, t_start, block)。"""
    win, step = int(EPOCH_S * sfreq), int(EPOCH_STEP * sfreq)
    n = eeg.shape[0]
    k = 0
    for s in range(0, max(1, n - win + 1), step):
        yield k, s / sfreq, eeg[s:s + win]
        k += 1


def analyse_block(block, sfreq):
    """对单个 epoch 算五频段 dB / 相对功率 / 噪声标志 / S.a / S.th。

    复用 report_generator.compute_band_power_chunk，保证与项目报告同口径。
    """
    bp = rg.compute_band_power_chunk(block, sfreq)
    if bp is None:
        return None
    db = {b: np.asarray(bp["db"][b], dtype=np.float64) for b in BANDS}
    rel = {b: np.asarray(bp["rel"][b], dtype=np.float64) for b in BANDS}
    # 通道均值（前端 S.bands 即 4 通道 dB 均值）
    db_m = {b: float(np.mean(db[b])) for b in BANDS}
    rel_m = {b: float(np.mean(rel[b])) for b in BANDS}
    # 相对Alpha：前端用 dB→线性→占比，这里同法
    lin = {b: 10.0 ** (db_m[b] / 10.0) for b in BANDS}
    tot = sum(lin.values())
    rel_alpha = lin["Alpha"] / tot if tot > 0 else np.nan
    lt = (db_m["Theta"] - db_m["Beta"]) / 10.0            # = log10(theta/beta)
    bg_rel = (lin["Beta"] + lin["Gamma"]) / tot if tot > 0 else np.nan
    return {
        "db": db_m, "rel": rel_m, "rel_alpha": rel_alpha, "lt": lt,
        "bg_rel": bg_rel, "noise": bool(bg_rel > NOISE_BG_RATIO),
        "S_a": float(clamp01((rel_alpha - CAL["relALo"]) / CAL["relASpan"])),
        "S_th": float(clamp01((lt - CAL["ltBLo"]) / CAL["ltBSpan"])),
        "a_raw": float((rel_alpha - CAL["relALo"]) / CAL["relASpan"]),   # 未 clamp，看是否越界
        "th_raw": float((lt - CAL["ltBLo"]) / CAL["ltBSpan"]),
        "tb_lin": float(10.0 ** lt),
    }


def run_session(tag, name, label):
    d = load_npz(name)
    sfreq, eeg, raw = d["sfreq"], d["eeg"], d["raw"]
    rows, rows_raw = [], []
    for k, t, blk in epoch_iter(eeg, sfreq):
        r = analyse_block(blk, sfreq)
        if r:
            r["t"] = t
            rows.append(r)
    if raw is not None and raw.shape == eeg.shape:
        for k, t, blk in epoch_iter(raw, sfreq):
            r = analyse_block(blk, sfreq)
            if r:
                r["t"] = t
                rows_raw.append(r)
    print(f"[{label}] 样本 {eeg.shape[0]} @ {sfreq}Hz = {eeg.shape[0]/sfreq/60:.1f} 分钟, "
          f"epoch数 {len(rows)}, 原始副本 {'有' if rows_raw else '无'}({len(rows_raw)})")
    return {"tag": tag, "label": label, "d": d, "rows": rows, "rows_raw": rows_raw}


def pct(vals):
    """分位数摘要。"""
    a = np.asarray(vals, dtype=np.float64)
    a = a[np.isfinite(a)]
    if a.size == 0:
        return None
    return {
        "n": int(a.size), "min": float(a.min()), "p5": float(np.percentile(a, 5)),
        "q1": float(np.percentile(a, 25)), "median": float(np.median(a)),
        "q3": float(np.percentile(a, 75)), "p95": float(np.percentile(a, 95)),
        "max": float(a.max()), "mean": float(a.mean()), "std": float(a.std()),
    }


def main():
    os.makedirs(FIG, exist_ok=True)
    res = [run_session(*s) for s in SESSIONS]
    out = {"cal": CAL, "bands": BANDS, "epoch": [EPOCH_S, EPOCH_STEP],
           "noise_bg_ratio": NOISE_BG_RATIO, "sessions": {}}

    for r in res:
        rows, tag = r["rows"], r["tag"]
        clean = [x for x in rows if not x["noise"]]
        s = {
            "label": r["label"],
            "n_samples": int(r["d"]["eeg"].shape[0]),
            "sfreq": r["d"]["sfreq"],
            "minutes": round(r["d"]["eeg"].shape[0] / r["d"]["sfreq"] / 60, 2),
            "n_epochs": len(rows),
            "n_noise": sum(1 for x in rows if x["noise"]),
            "noise_ratio": round(sum(1 for x in rows if x["noise"]) / max(len(rows), 1), 4),
            "db": {b: pct([x["db"][b] for x in clean]) for b in BANDS},
            "rel": {b: pct([x["rel"][b] for x in clean]) for b in BANDS},
            "rel_alpha": pct([x["rel_alpha"] for x in clean]),
            "lt": pct([x["lt"] for x in clean]),
            "tb_lin": pct([x["tb_lin"] for x in clean]),
            "S_a": pct([x["S_a"] for x in clean]),
            "S_th": pct([x["S_th"] for x in clean]),
            # 标定越界诊断：clamp 前落到区间外的比例
            "a_raw": pct([x["a_raw"] for x in clean]),
            "th_raw": pct([x["th_raw"] for x in clean]),
            "a_below0": round(float(np.mean([x["a_raw"] < 0 for x in clean])), 4) if clean else None,
            "a_above1": round(float(np.mean([x["a_raw"] > 1 for x in clean])), 4) if clean else None,
            "th_below0": round(float(np.mean([x["th_raw"] < 0 for x in clean])), 4) if clean else None,
            "th_above1": round(float(np.mean([x["th_raw"] > 1 for x in clean])), 4) if clean else None,
        }
        # 状态分类（复用项目 classify_state）
        states = {}
        for x in clean:
            st = rg.classify_state(x["db"]["Alpha"], x["db"]["Theta"], x["db"]["Beta"],
                                   x["db"]["Delta"], x["tb_lin"], None)
            states[st] = states.get(st, 0) + 1
        s["states"] = {k: [v, round(v / max(len(clean), 1), 4)] for k, v in
                       sorted(states.items(), key=lambda kv: -kv[1])}
        # 滤波前后对照
        if r["rows_raw"]:
            rc = [x for x in r["rows_raw"] if not x["noise"]]
            s["filter_compare"] = {
                "n_epochs_raw": len(r["rows_raw"]),
                "db_raw": {b: pct([x["db"][b] for x in rc]) for b in BANDS},
                "S_a_raw": pct([x["S_a"] for x in rc]),
                "S_th_raw": pct([x["S_th"] for x in rc]),
            }
        out["sessions"][tag] = s

    # 合并两次的 S.a/S.th 分布（供 CAL 重标定建议）
    all_a = [x["S_a"] for r in res for x in r["rows"] if not x["noise"]]
    all_th = [x["S_th"] for r in res for x in r["rows"] if not x["noise"]]
    all_ra = [x["rel_alpha"] for r in res for x in r["rows"] if not x["noise"]]
    all_lt = [x["lt"] for r in res for x in r["rows"] if not x["noise"]]
    out["merged"] = {"S_a": pct(all_a), "S_th": pct(all_th),
                     "rel_alpha": pct(all_ra), "lt": pct(all_lt)}

    with open(os.path.join(OUT, "第一重_脑电分析数据.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    print("\n=== 汇总 ===")
    for r in res:
        s = out["sessions"][r["tag"]]
        print(f"\n{s['label']}: {s['minutes']}分钟, epoch {s['n_epochs']}, 噪声占比 {s['noise_ratio']*100:.1f}%")
        print(f"  rel_alpha 中位 {s['rel_alpha']['median']:.4f} [IQR {s['rel_alpha']['q1']:.4f}~{s['rel_alpha']['q3']:.4f}]")
        print(f"  lt(θ/β)   中位 {s['lt']['median']:+.3f} [IQR {s['lt']['q1']:+.3f}~{s['lt']['q3']:+.3f}]")
        print(f"  S.a       中位 {s['S_a']['median']:.3f} [IQR {s['S_a']['q1']:.3f}~{s['S_a']['q3']:.3f}] "
              f"越下界 {s['a_below0']*100:.1f}% 越上界 {s['a_above1']*100:.1f}%")
        print(f"  S.th      中位 {s['S_th']['median']:.3f} [IQR {s['S_th']['q1']:.3f}~{s['S_th']['q3']:.3f}] "
              f"越下界 {s['th_below0']*100:.1f}% 越上界 {s['th_above1']*100:.1f}%")
        print(f"  状态分布: {s['states']}")
        if "filter_compare" in s:
            fc = s["filter_compare"]
            print(f"  滤波前 S.a 中位 {fc['S_a_raw']['median']:.3f} / S.th 中位 {fc['S_th_raw']['median']:.3f}")
    return out, res


if __name__ == "__main__":
    main()
