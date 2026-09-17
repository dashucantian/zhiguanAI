"""呼吸源可行性严格检验：能否从 Muse 4通道EEG 可靠提取呼吸节律？

这是"光球跟真实呼吸 vs 固定节律"方案的命门。判据从严：
跨通道 CV<0.25 且 主频离散<0.15 才算真实共同生理节律。
"""
import numpy as np
from scipy.signal import butter, sosfiltfilt, find_peaks, welch

f = 'muse2-repo/muse2-master/report/local_20260911_094407.npz'
with np.load(f, allow_pickle=True) as z:
    raw = np.asarray(z['eeg_pre_filter'], dtype=np.float64)
sf = 256.0
CH = ['TP9', 'AF7', 'AF8', 'TP10']

print('=== 呼吸可提取性严格检验（滤波前原始数据）===')
print('带通 0.15-0.45Hz（即 9-24 次/分，静坐典型呼吸区间）')

# 1Hz 高通边缘效应会污染更低频，故用窄带且看幅度包络而非原始峰
sos = butter(3, [0.15, 0.45], btype='bandpass', fs=sf, output='sos')
results = []
for ci, ch in enumerate(CH):
    seg = raw[:int(sf * 900), ci] - np.median(raw[:int(sf * 900), ci])
    b = sosfiltfilt(sos, seg)
    win = int(sf * 1.0)
    env = np.array([np.sqrt(np.mean(b[i:i + win] ** 2)) for i in range(0, len(b) - win, win // 2)])
    pk, _ = find_peaks(env, distance=2)          # 包络采样2Hz，2点=1秒最小间隔
    if len(pk) > 5:
        iv = np.diff(pk)
        cv = float(iv.std() / iv.mean())
        f_, p_ = welch(env, fs=2.0, nperseg=min(256, len(env) // 2))
        m = (f_ >= 0.15) & (f_ <= 0.45)
        ipk = int(np.argmax(p_[m]))
        pkfreq = float(f_[m][ipk])
        results.append((ch, cv, pkfreq, len(pk)))
        print('  %s: 峰%3d个 间隔CV=%.3f 包络主频=%.3fHz (%.1f次/分)'
              % (ch, len(pk), cv, pkfreq, 60 / pkfreq))
    else:
        print('  %s: 峰太少(%d)，不可用' % (ch, len(pk)))

if not results:
    print('\n结论: ❌ 无任何通道可提取呼吸节律')
    raise SystemExit

cvs = [r[1] for r in results]
freqs = [r[2] for r in results]
disp = float(np.std(freqs) / np.mean(freqs))
print('\n  跨通道一致性: CV范围[%.2f, %.2f]  主频范围[%.3f, %.3f]Hz'
      % (min(cvs), max(cvs), min(freqs), max(freqs)))
print('  主频离散度=%.2f  (越小越说明是真实共同生理节律而非各通道噪声)' % disp)
print('\n判据: CV<0.25 且 主频离散<0.15 → 可作呼吸源')
ok = max(cvs) < 0.25 and disp < 0.15
print('结论: ' + ('✅ 呼吸可提取，可作真实节律源' if ok else '❌ 呼吸不可靠，不能作为实时驱动源'))

# 附加：呼吸调制是否稳定到可作"底色"——看整段包络功率的时变性
print('\n=== 附加：呼吸调制的长程稳定性（能否当底色）===')
seg = raw[:, 1] - np.median(raw[:, 1])          # AF7 全程
b = sosfiltfilt(sos, seg)
win = int(sf * 1.0)
env = np.array([np.sqrt(np.mean(b[i:i + win] ** 2)) for i in range(0, len(b) - win, win // 2)])
chunks = np.array_split(env, 6)
print('  全程分6段的呼吸带能量相对值:')
base = None
for i, c in enumerate(chunks):
    v = float(np.std(c))
    if base is None:
        base = v
    print('    段%d: %.3e  (相对首段 %.2fx)' % (i + 1, v, v / base))
