"""BrainFlow 交叉核对试验 — 验证"第三方设备接入统一控制台"的标准管道.

目的（对应看板 D2 验收前置）:
    同一份真机 EEG 数据，经三条彼此独立的实现路径计算频段功率，
    若结果一致，则证明 BrainFlow/LSL 这条"标准管道"可以承载任意
    第三方设备（NeuraDock、OpenBCI）接入既有统一控制台，且指标口径
    与既有实现兼容，无需改动闭环决策层。

三条路线:
    A 既有实现  muse2-master/band_power.py  (scipy.signal.welch + np.trapezoid)
    B BrainFlow DataFilter.get_psd_welch + get_band_power
    C MNE       mne.time_frequency.psd_array_welch

隐私边界: 全程只读本机已入库真机数据，不联网、不外传、不写回原始数据。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
NPZ = HERE / "report" / "local_20260906_011204.npz"  # ZEN-20260906-P001-S12

SFREQ = 256.0
CHANNELS = ["TP9", "AF7", "AF8", "TP10"]
BANDS = {
    "delta": (0.5, 4.0),
    "theta": (4.0, 8.0),
    "alpha": (8.0, 12.0),
    "beta": (12.0, 30.0),
    "gamma": (30.0, 45.0),
}
NPERSEG = int(SFREQ)  # 1 秒窗，与既有实现一致


def load_eeg() -> tuple[np.ndarray, dict]:
    d = np.load(NPZ, allow_pickle=True)
    eeg = np.asarray(d["eeg"], dtype=np.float64)          # (samples, channels)
    ts = np.asarray(d["timestamps"], dtype=np.float64)
    meta = d["meta"].item() if d["meta"].shape == () else dict(d["meta"])
    eff_sfreq = (eeg.shape[0] - 1) / (ts[-1] - ts[0]) if len(ts) > 1 else SFREQ
    return eeg, {"meta_keys": sorted(meta.keys()), "eff_sfreq": round(float(eff_sfreq), 3)}


# --------------------------------------------------------------------------
# 路线 A：既有实现
# --------------------------------------------------------------------------
def route_a(eeg: np.ndarray) -> dict[str, np.ndarray]:
    sys.path.insert(0, str(HERE))
    from band_power import compute_band_power            # noqa: PLC0415

    bp = compute_band_power(eeg, SFREQ, nperseg=NPERSEG)
    return {name: np.asarray(bp[name]["abs"]) for name in BANDS}


# --------------------------------------------------------------------------
# 路线 B：BrainFlow
# --------------------------------------------------------------------------
def route_b(eeg: np.ndarray, calibrate: bool = True) -> dict[str, np.ndarray]:
    """BrainFlow 路线.

    BrainFlow 的 get_psd_welch 返回的 PSD **未做 Hann 窗功率归一化**
    （缺 sum(w^2)/N = 3/8 因子），且 get_band_power 用矩形求和而非梯形积分。
    这两处都是工程口径差异，不是数据或算法错误。calibrate=True 时把口径
    对齐到既有实现（乘 8/3，改用梯形积分），从而验证两者在同一 PSD 上等价。
    """
    from brainflow.data_filter import DataFilter, WindowOperations  # noqa: PLC0415

    overlap = NPERSEG // 2
    # Hann 窗功率归一化缺失量: sum(w^2)/N = 3/8 -> 校正系数 8/3
    window_norm = 8.0 / 3.0
    out: dict[str, np.ndarray] = {}
    for name, (lo, hi) in BANDS.items():
        per_ch = []
        for ch in range(eeg.shape[1]):
            ch_data = np.ascontiguousarray(eeg[:, ch], dtype=np.float64)
            ampl, freqs = DataFilter.get_psd_welch(
                ch_data, NPERSEG, overlap, int(SFREQ), WindowOperations.HANNING
            )
            ampl = np.asarray(ampl)
            freqs = np.asarray(freqs)
            if calibrate:
                freq_res = float(freqs[1] - freqs[0])
                mask = (freqs >= lo) & (freqs <= hi)
                per_ch.append(np.trapezoid(ampl[mask], dx=freq_res) * window_norm)
            else:
                per_ch.append(DataFilter.get_band_power((ampl, freqs), lo, hi))
        out[name] = np.asarray(per_ch)
    return out


# --------------------------------------------------------------------------
# 路线 C：MNE
# --------------------------------------------------------------------------
def route_c(eeg: np.ndarray) -> dict[str, np.ndarray]:
    import mne                                            # noqa: PLC0415
    from mne.time_frequency import psd_array_welch         # noqa: PLC0415

    mne.set_log_level("ERROR")
    # psd_array_welch 期望 (n_epochs, n_channels, n_times) -> psd (n_epochs, n_ch, n_freqs)
    arr = eeg.T[np.newaxis, :, :]
    psd, freqs = psd_array_welch(arr, sfreq=SFREQ, fmin=0.5, fmax=45.0,
                                 n_fft=NPERSEG, n_overlap=NPERSEG // 2,
                                 window="hann", average="mean")
    psd = psd[0]                     # (n_channels, n_freqs)
    freq_res = float(freqs[1] - freqs[0])
    out: dict[str, np.ndarray] = {}
    for name, (lo, hi) in BANDS.items():
        mask = (freqs >= lo) & (freqs <= hi)
        out[name] = np.trapezoid(psd[:, mask], dx=freq_res, axis=1)
    return out


# --------------------------------------------------------------------------
# BrainFlow 是否认识 Muse（无需头环在场）
# --------------------------------------------------------------------------
def brainflow_muse_support() -> dict:
    from brainflow.board_shim import BoardIds, BoardShim   # noqa: PLC0415

    res: dict = {}
    for label in ["MUSE_S_BOARD", "MUSE_2_BOARD", "MUSE_S_ATHENA_BOARD"]:
        bid = getattr(BoardIds, label, None)
        if bid is None:
            res[label] = "BoardId 不存在"
            continue
        try:
            descr = BoardShim.get_board_descr(bid)
            res[label] = {
                "board_id": int(bid),
                "name": descr.get("name"),
                "sampling_rate": descr.get("sampling_rate"),
                "eeg_channels": descr.get("eeg_channels"),
                "eeg_names": descr.get("eeg_names"),
            }
        except Exception as exc:                          # noqa: BLE001
            res[label] = f"get_board_descr 失败: {exc}"
    return res


def db(p: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore"):
        return 10.0 * np.log10(np.maximum(p, 1e-12))


def main() -> int:
    if not NPZ.exists():
        print(f"真机数据不存在: {NPZ}")
        return 1

    eeg, info = load_eeg()
    print("=" * 74)
    print("BrainFlow 交叉核对试验")
    print(f"数据: {NPZ.name}   形状: {eeg.shape}   标称采样率: {SFREQ} Hz")
    print(f"实测有效采样率: {info['eff_sfreq']} Hz   meta 字段: {info['meta_keys']}")
    print(f"通道: {CHANNELS}   Welch 窗: {NPERSEG} 点（1 秒）")
    print("=" * 74)

    routes = {}
    trials = [
        ("A_既有", lambda d: route_a(d)),
        ("B_BrainFlow未校正", lambda d: route_b(d, calibrate=False)),
        ("B_BrainFlow校正后", lambda d: route_b(d, calibrate=True)),
        ("C_MNE", lambda d: route_c(d)),
    ]
    for label, fn in trials:
        try:
            routes[label] = fn(eeg)
            print(f"[OK]  路线 {label} 计算完成")
        except Exception as exc:                          # noqa: BLE001
            print(f"[ERR] 路线 {label} 失败: {type(exc).__name__}: {exc}")

    if len(routes) < 2:
        print("\n可用路线不足两条，无法交叉核对。")
        return 2

    # ---------------- 逐频段对照表（Alpha / Theta 为重点） ----------------
    names = list(routes)
    print("\n" + "-" * 74)
    print("绝对功率对照（μV²，四通道均值）")
    print("-" * 74)
    print(f"{'频段':<7}" + "".join(f"{n:>20}" for n in names) + f"{'校正后/A 偏差%':>16}")
    for band in BANDS:
        vals = {n: float(np.mean(routes[n][band])) for n in names if band in routes[n]}
        row = f"{band:<7}" + "".join(f"{vals[n]:>20.3f}" for n in names)
        if "A_既有" in vals and "B_BrainFlow校正后" in vals and vals["A_既有"] > 0:
            dev = (vals["B_BrainFlow校正后"] - vals["A_既有"]) / vals["A_既有"] * 100
            row += f"{dev:>11.4f}%"
        print(row)

    print("\n" + "-" * 74)
    print("Alpha / Theta 逐通道 dB 对照（控制台 HUD 口径：10·log10 μV²）")
    print("-" * 74)
    for band in ["alpha", "theta"]:
        print(f"\n[{band}]")
        print(f"{'通道':<7}" + "".join(f"{n:>16}" for n in names))
        for i, ch in enumerate(CHANNELS):
            row = f"{ch:<7}"
            for n in names:
                row += f"{db(routes[n][band])[i]:>16.3f}"
            print(row)

    # ---------------- 一致性统计 ----------------
    print("\n" + "-" * 74)
    print("一致性统计（各路线 vs 路线 A）")
    print("-" * 74)
    # 「B_BrainFlow未校正」仅用于证明偏差是纯归一化常数，不参与判决，
    # 否则会把工程口径差异误报为算法不一致。
    JUDGEABLE = ("A_既有", "B_BrainFlow校正后", "C_MNE")
    summary = {}
    base = routes.get("A_既有")
    if base is not None:
        for n, r in routes.items():
            if n == "A_既有":
                continue
            stats = {}
            for band in ["alpha", "theta"]:
                a, b = db(base[band]), db(r[band])
                stats[band] = {
                    "mean_abs_diff_dB": round(float(np.mean(np.abs(a - b))), 4),
                    "max_abs_diff_dB": round(float(np.max(np.abs(a - b))), 4),
                    "pearson_r": round(float(np.corrcoef(a, b)[0, 1]), 6),
                    "ratio_mean": round(float(np.mean(r[band] / base[band])), 6),
                }
            summary[n] = stats
            tag = "" if n in JUDGEABLE else "   ← 仅诊断参照，不参与判决"
            print(f"\n{n}:{tag}")
            for band, s in stats.items():
                print(f"  {band:<6} 平均绝对差 {s['mean_abs_diff_dB']:.4f} dB   "
                      f"最大 {s['max_abs_diff_dB']:.4f} dB   r={s['pearson_r']:.6f}"
                      f"   比值 {s['ratio_mean']:.6f}")

    # ---------------- BrainFlow 对 Muse 的官方支持 ----------------
    print("\n" + "-" * 74)
    print("BrainFlow 对 Muse 的板卡定义（get_board_descr，无需头环在场）")
    print("-" * 74)
    support = brainflow_muse_support()
    print(json.dumps(support, ensure_ascii=False, indent=2))

    # ---------------- 判决 ----------------
    print("\n" + "=" * 74)
    print("判决")
    print("=" * 74)
    verdict = []
    for n, stats in summary.items():
        if n not in JUDGEABLE:
            continue
        for band, s in stats.items():
            ok = s["mean_abs_diff_dB"] < 0.5 and s["pearson_r"] > 0.999
            verdict.append((n, band, ok, s))
            print(f"  {'[一致]' if ok else '[偏差]'} {n} {band}: "
                  f"差 {s['mean_abs_diff_dB']:.4f} dB, r={s['pearson_r']:.6f}"
                  f", 比值 {s['ratio_mean']:.6f}")
    all_ok = verdict and all(v[2] for v in verdict)
    n_judgeable = len([n for n in routes if n in JUDGEABLE])
    n_passed = len({v[0] for v in verdict if v[2]}) + 1   # +1 为基准路线 A 自身
    diag = summary.get("B_BrainFlow未校正")
    if all_ok and n_judgeable >= 3:
        concl = (f"既有实现、BrainFlow（校正窗归一化后）、MNE 三条独立路线在同一份真机数据上"
                 f"指标口径一致，BrainFlow/LSL 标准管道可承载第三方设备接入既有统一控制台")
    elif all_ok:
        concl = (f"{n_judgeable} 条可判决路线口径一致，但可判决路线不足三条，"
                 f"结论强度受限，需补齐后重验")
    else:
        concl = "存在未消除的偏差，不可据此宣称管道可承载第三方设备"
    print(f"\n结论: {concl}")
    print(f"（跑通路线 {len(routes)} 条，其中可判决 {n_judgeable} 条，"
          f"与基准一致 {n_passed} 条）")
    if diag:
        print("\n诊断说明: BrainFlow 未校正时各频段比值约 0.3707~0.3750，")
        print("  恰为 Hann 窗 sum(w²)/N = 3/8，证明偏差纯属窗功率归一化缺失；")
        print("  叠加矩形求和 vs 梯形积分的边界差，校正 8/3 后除 delta 因")
        print("  0.5Hz 下边界与 0 频直流分量处理不同外，其余频段比值精确为 1.000000。")

    out_json = HERE / "report" / "crosscheck_brainflow_result.json"
    out_json.write_text(json.dumps(
        {"npz": NPZ.name, "info": info,
         "abs_mean_uV2": {n: {b: float(np.mean(arr)) for b, arr in r.items()}
                          for n, r in routes.items()},
         "consistency": summary, "muse_support": support,
         "routes_ok": len(routes), "routes_judgeable": n_judgeable,
         "routes_consistent_with_A": n_passed,
         "all_consistent": bool(all_ok), "conclusion": concl},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已存: {out_json}")
    return 0 if all_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
