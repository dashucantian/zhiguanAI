"""存盘数据信号链实测：离线 Welch PSD 检验三个频段的能量占比。

检验问题（讨论稿第八节）：save_bin 落盘的数据是否经过 1–40Hz 带通？
判据：若 <1Hz 相对能量 ≈0 而正常静坐闭眼数据应有可观 Delta，则证实被滤。
只读检验，不写任何数据。"""
import sys
import numpy as np
from scipy.signal import welch

FILES = [
    r"C:\Users\tiand\OneDrive\Zen-EEG\02_raw\ZEN-20260906-P001-S12\eeg_raw.npz",
    r"C:\Users\tiand\OneDrive\Zen-EEG\02_raw\ZEN-20260901-P001-S06\eeg_raw.npz",
    r"C:\Users\tiand\OneDrive\zhiguanAI\muse2-repo\muse2-master\report\local_20260908_023101.npz",
]

for path in FILES:
    try:
        with np.load(path, allow_pickle=True) as z:
            eeg = z["eeg"]
            meta = z["meta"].item()
    except Exception as e:
        print(f"SKIP {path}: {e}")
        continue
    sfreq = float(np.asarray(meta["sfreq"]).item())
    dur = eeg.shape[0] / sfreq
    x = eeg[:, :int(meta.get("channels", ["x"]) and 4)].T   # 前 4 通道
    nper = int(min(len(x[0]), sfreq * 4))
    f, p = welch(x, fs=sfreq, nperseg=nper, axis=-1)
    p = p.mean(axis=0)                       # 通道平均 PSD
    total = np.trapezoid(p, f)
    def band(a, b):
        m = (f >= a) & (f < b)
        return 100.0 * np.trapezoid(p[m], f[m]) / total if total else 0.0
    # 50Hz 工频尖峰：与两侧基线比较
    m50 = (f >= 49.5) & (f <= 50.5)
    base = (f >= 45) & (f <= 55) & ~m50
    notch_db = 10 * np.log10(p[m50].max() / np.median(p[base])) if m50.any() and base.any() else float("nan")
    print(f"{path.split(chr(92))[-1]} | {dur:.0f}s | ch={eeg.shape[1]}")
    print(f"  <1Hz: {band(0.0, 1.0):5.2f}%   1-4Hz(Delta通带内应>10%若无): {band(1.0, 4.0):5.1f}%   "
          f"8-13(Alpha): {band(8.0, 13.0):5.1f}%   >45Hz(含50工频): {band(45.0, 60.0):5.2f}%   "
          f"50Hz尖峰: {notch_db:+.0f}dB")
