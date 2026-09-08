"""存盘数据信号链自查工具：离线 Welch PSD 检验各频段能量占比。

用途（配合讨论稿第八节"L1 数据诚实性"）：自查 save_bin 落盘的 npz 是否
经过隐式带通滤波。判据：若 <1Hz 次慢波相对能量趋近 0（正常静坐闭眼数据
应有可观慢波），即证实存盘数据被高通削过；50Hz 尖峰是否残留反映有无陷波。

用法：
    python signal_chain_check.py <recording.npz> [<recording2.npz> ...]
    python signal_chain_check.py            # 无参时打印用法并退出

只读检验，不写、不修改任何数据文件。npz 需含 eeg 数组与 meta（sfreq/channels）。
"""
import os
import sys

import numpy as np
from scipy.signal import welch


def check(path):
    try:
        with np.load(path, allow_pickle=True) as z:
            eeg = z["eeg"]
            meta = z["meta"].item()
    except Exception as e:
        print(f"SKIP {path}: {e}")
        return
    sfreq = float(np.asarray(meta["sfreq"]).item())
    channels = meta.get("channels") or []
    n_ch = eeg.shape[1]
    dur = eeg.shape[0] / sfreq
    x = eeg.T                                   # (n_ch, n_times)
    nper = int(min(x.shape[1], sfreq * 4))
    f, p = welch(x, fs=sfreq, nperseg=nper, axis=-1)
    p = p.mean(axis=0)                          # 通道平均 PSD
    total = np.trapezoid(p, f)

    def band(a, b):
        m = (f >= a) & (f < b)
        return 100.0 * np.trapezoid(p[m], f[m]) / total if total else 0.0

    # 50Hz 工频尖峰：与两侧基线中位数比较（dB）
    m50 = (f >= 49.5) & (f <= 50.5)
    base = (f >= 45) & (f <= 55) & ~m50
    notch_db = (10 * np.log10(p[m50].max() / np.median(p[base]))
                if m50.any() and base.any() else float("nan"))

    chain = meta.get("signal_chain")
    tag = chain.get("chain_tag") if isinstance(chain, dict) else None
    name = os.path.basename(path)
    print(f"{name} | {dur:.0f}s | ch={n_ch}{'' if not channels else ' ' + '/'.join(map(str, channels))}"
          f" | chain={tag or '未标注(v1.2 或更早)'}")
    print(f"  <1Hz: {band(0.0, 1.0):5.2f}%   1-4Hz(Delta): {band(1.0, 4.0):5.1f}%   "
          f"8-13Hz(Alpha): {band(8.0, 13.0):5.1f}%   45-60Hz(含工频): {band(45.0, 60.0):5.2f}%   "
          f"50Hz尖峰: {notch_db:+.0f}dB")
    if band(0.0, 1.0) < 3.0:
        print("  ↳ <1Hz 占比偏低：存盘数据很可能经过高通/去直流，次慢波已丢失（不可恢复）")


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    for path in argv[1:]:
        check(path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
