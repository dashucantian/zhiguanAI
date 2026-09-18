# -*- coding: utf-8 -*-
"""
L4-02b 素材生产 · 第三步：验证 S09/S11 是否为模拟器数据
==========================================================
背景：第二步提取发现 S09/S11 的 Alpha 相对功率高达 0.956/0.947，
而其余 9 个 session 仅 0.044–0.080。这一形态与 MonitorSimulator
（console_server.py:341-346）的合成信号高度吻合：
    7.0·sin(2π·10Hz·t) + 1.2·sin(2π·20Hz·t) + N(0, 1.5)
    → Alpha(8-12Hz) 功率占比理论值 ≈ 7²/(7²+1.2²) ≈ 0.971
    → 通道标准差理论值 ≈ sqrt((7/√2)² + 1.5²) ≈ 5.17 µV

若验证成立，则 S09/S11 不是真实脑电，而是模拟器数据被当作"链路测试"
录进了 npz。这对评测集是**重大利好**：我们因此拥有了一组
**已知标准答案**的样本（合成 vs 真实），L4-02b 不再"无标准答案可比对"。

纪律：02_raw 只读；只输出统计量与峰值频率，不输出原始波形。
"""
import numpy as np
from scipy.signal import welch
import glob
import os

BASE = r"D:\Project\Zen-EEG"  # 2026-09-19 数据工厂随项目迁 D 盘（原 C:\...\OneDrive\Zen-EEG）
SFREQ = 256.0
BANDS = {"Delta": (0.5, 4), "Theta": (4, 8), "Alpha": (8, 12),
         "Beta": (12, 30), "Gamma": (30, 45)}

paths = sorted(glob.glob(os.path.join(BASE, "02_raw", "*", "eeg_raw.npz")))
paths += sorted(glob.glob(os.path.join(
    BASE, "03_quality_control", "quarantine", "*", "eeg_raw.npz")))

print("=" * 104)
print("各 session 峰值频率与全频段相对功率分布")
print("=" * 104)
hdr = "%-24s %8s %8s | " % ("session_id", "峰值Hz", "次峰Hz")
hdr += " ".join("%7s" % b for b in BANDS)
print(hdr)
print("-" * 104)

verdict = {}
for p in paths:
    sid = os.path.basename(os.path.dirname(p))
    z = np.load(p, allow_pickle=True)
    eeg = z["eeg"]

    # 跨通道平均 PSD，频率分辨率取高一些以便看清峰
    freqs, psd = welch(eeg, SFREQ, nperseg=int(SFREQ * 4), axis=0)
    psd_mean = psd.mean(axis=1)

    # 只在 0.5-45Hz 范围内找峰（与项目 BANDS 口径一致）
    band_mask = (freqs >= 0.5) & (freqs <= 45)
    f_b = freqs[band_mask]
    p_b = psd_mean[band_mask]

    order = np.argsort(p_b)[::-1]
    peak1 = f_b[order[0]]
    # 次峰：与主峰至少隔 3Hz
    peak2 = None
    for idx in order[1:]:
        if abs(f_b[idx] - peak1) >= 3.0:
            peak2 = f_b[idx]
            break

    total = 0.0
    abs_p = {}
    for b, (lo, hi) in BANDS.items():
        m = (f_b >= lo) & (f_b <= hi)
        abs_p[b] = np.trapezoid(p_b[m], f_b[m])
        total += abs_p[b]
    rel = {b: abs_p[b] / total for b in BANDS}

    row = "%-24s %8.2f %8s | " % (
        sid, peak1, ("%.2f" % peak2) if peak2 else "—")
    row += " ".join("%7.4f" % rel[b] for b in BANDS)
    print(row)

    # 模拟器判定：Alpha>0.5 且峰值≈10Hz 且次峰≈20Hz
    is_sim = (rel["Alpha"] > 0.5 and abs(peak1 - 10.0) < 1.0
              and peak2 is not None and abs(peak2 - 20.0) < 1.5)
    verdict[sid] = {
        "peak1": round(float(peak1), 2),
        "peak2": round(float(peak2), 2) if peak2 else None,
        "rel_alpha": round(float(rel["Alpha"]), 4),
        "std_mean": round(float(np.mean(np.std(eeg, axis=0))), 2),
        "判定": "模拟器合成数据" if is_sim else "真实采集",
    }

print()
print("=" * 104)
print("模拟器理论值对照：峰值 10Hz / 次峰 20Hz / Alpha占比 ≈0.971 / 通道std ≈5.17µV")
print("=" * 104)
print("%-24s %8s %8s %10s %9s   %s" % (
    "session_id", "峰值Hz", "次峰Hz", "Alpha占比", "std均值", "判定"))
print("-" * 104)
for sid, v in sorted(verdict.items()):
    print("%-24s %8.2f %8s %10.4f %9.2f   %s" % (
        sid, v["peak1"], v["peak2"] if v["peak2"] else "—",
        v["rel_alpha"], v["std_mean"], v["判定"]))

sims = [s for s, v in verdict.items() if v["判定"] == "模拟器合成数据"]
reals = [s for s, v in verdict.items() if v["判定"] == "真实采集"]
print()
print("判为模拟器合成: %d 个 → %s" % (len(sims), sims))
print("判为真实采集  : %d 个" % len(reals))
