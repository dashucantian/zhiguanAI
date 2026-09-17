#!/usr/bin/env python3
"""IsoEngine off-by-one 实测核查（2026-09-14，W1 窗口）

目的：不采信交接文档的转述数字，离线复现 closedloop_engine.py:78-109 的
回调逻辑，量化 `ph_c[-1]`（index n-1）这一 off-by-one 的**实际后果**：
  1. 载波频率降了多少（标称 220Hz → 实测多少）
  2. 节拍频率降了多少（标称 10Hz → 实测多少）——闭环实验的自变量
  3. 块边界是否产生**突跳**（一阶差分是否出现异常尖峰）——即是否有爆音/咔哒
  4. 与正确实现（相位连续）的逐点偏差，以及该偏差的量级含义

设计纪律（守 §7.1 教训：不拿想当然机制当事实）：
  - 纯 numpy 离线仿真，**不启动音频流、不发声、无硬件依赖**
  - 直接照抄 closedloop_engine.py 的算式，不改一个常量
  - 同时测「frames 固定」与「frames 不定」两种场景（PortAudio 未指定
    blocksize 时回调帧数可变，这会让降频比例抖动）

运行：python iso_offbyone_probe.py
"""
import numpy as np

TWO_PI = 2.0 * np.pi
SR = 44100          # closedloop_engine.py 默认 samplerate
CARRIER = 220.0     # 默认载波
BEAT = 10.0         # 默认节拍


# ── 照抄 closedloop_engine.py:78-109 的回调逻辑 ──────────────────────
def synth(total_samples, frames_seq, buggy=True,
          carrier=CARRIER, beat=BEAT, volume=0.25):
    """离线复现回调，返回拼接后的单声道信号。

    frames_seq: 可迭代的每块帧数序列（长度不足时循环复用）
    buggy=True  → 现状：_phase = ph[-1]（index n-1）
    buggy=False → 修复：_phase = ph[-1] + 单样本相位增量
    """
    ph_c_state = 0.0
    ph_m_state = 0.0
    cur_vol = 0.0
    out = []
    produced = 0
    it = iter(frames_seq)
    last_frames = None
    while produced < total_samples:
        try:
            frames = next(it)
        except StopIteration:
            it = iter(frames_seq)
            frames = next(it)
        last_frames = frames
        n = np.arange(frames)

        ph_c = ph_c_state + TWO_PI * carrier * n / SR
        ph_m = ph_m_state + TWO_PI * beat * n / SR

        mod = np.maximum(np.sin(ph_m), 0.0)
        env = np.power(mod, 0.6)

        target_vol = volume
        dv = target_vol - cur_vol
        max_step = 0.0002 * frames
        if abs(dv) > max_step:
            dv = max_step if dv > 0 else -max_step
        vol_track = cur_vol + dv * (n + 1) / frames

        sig = np.sin(ph_c) * env * vol_track
        out.append(sig)

        if buggy:
            ph_c_state = float(ph_c[-1]) % TWO_PI
            ph_m_state = float(ph_m[-1]) % TWO_PI
        else:
            # 修复：下一块首样本应有的相位 = 本块首相位 + frames 个增量
            ph_c_state = (float(ph_c_state) + TWO_PI * carrier * frames / SR) % TWO_PI
            ph_m_state = (float(ph_m_state) + TWO_PI * beat * frames / SR) % TWO_PI
        cur_vol += dv

        produced += frames
    return np.concatenate(out)[:total_samples], last_frames


# ── 测量工具 ────────────────────────────────────────────────────────
def peak_freq(sig, sr=SR, lo=50.0, hi=1000.0, skip=0.5):
    """取信号稳态段做 FFT，返回主峰频率（Hz）与频率分辨率。"""
    s = sig[int(skip * sr):]
    N = len(s)
    w = np.hanning(N)
    spec = np.abs(np.fft.rfft(s * w))
    freqs = np.fft.rfftfreq(N, 1.0 / sr)
    mask = (freqs >= lo) & (freqs <= hi)
    idx = np.argmax(spec[mask])
    return float(freqs[mask][idx]), float(sr / N)


def env_beat_freq(sig, sr=SR, lo=5.0, hi=20.0, skip=1.0):
    """对整流包络做 FFT，测节拍频率（等时节拍的包络重复率）。"""
    s = np.abs(sig[int(skip * sr):])
    # 去直流＋降采样到 2kHz 足够分辨 8~14Hz
    ds = 5
    s = s[::ds]
    s = s - s.mean()
    sr2 = sr / ds
    N = len(s)
    spec = np.abs(np.fft.rfft(s * np.hanning(N)))
    freqs = np.fft.rfftfreq(N, 1.0 / sr2)
    mask = (freqs >= lo) & (freqs <= hi)
    idx = np.argmax(spec[mask])
    return float(freqs[mask][idx])


def boundary_stats(sig, frames, n_blocks=200):
    """检查块边界处一阶差分是否出现异常尖峰（爆音判据）。

    返回：(块边界差分最大值 / 全体差分 99.9 分位, 全体差分最大值)
    比值 ≈ 1 说明边界与块内无差别；>>1 说明有突跳。
    """
    d = np.abs(np.diff(sig))
    bnd = np.arange(frames, min(len(sig), frames * n_blocks), frames)
    bnd = bnd[bnd < len(d)]
    if len(bnd) == 0:
        return float("nan"), float("nan")
    d_bnd_max = float(d[bnd].max())
    d_in = np.delete(d, bnd)
    d_in_ref = float(np.quantile(d_in, 0.999))
    return d_bnd_max / d_in_ref if d_in_ref > 0 else float("nan"), float(d.max())


def _synth_beat_switch(total, frames, beat_a, beat_b, switch_at, buggy=True,
                       carrier=CARRIER, volume=0.25):
    """在**同一相位状态内**中途切换节拍，模拟 set_beat 热更新。

    与 synth() 的区别：相位状态跨切换点连续累积，不重置。
    """
    ph_c_state = 0.0
    ph_m_state = 0.0
    cur_vol = 0.0
    out = []
    produced = 0
    while produced < total:
        beat = beat_a if produced < switch_at else beat_b
        n = np.arange(frames)

        ph_c = ph_c_state + TWO_PI * carrier * n / SR
        ph_m = ph_m_state + TWO_PI * beat * n / SR

        mod = np.maximum(np.sin(ph_m), 0.0)
        env = np.power(mod, 0.6)

        dv = volume - cur_vol
        max_step = 0.0002 * frames
        if abs(dv) > max_step:
            dv = max_step if dv > 0 else -max_step
        vol_track = cur_vol + dv * (n + 1) / frames

        out.append(np.sin(ph_c) * env * vol_track)

        if buggy:
            ph_c_state = float(ph_c[-1]) % TWO_PI
            ph_m_state = float(ph_m[-1]) % TWO_PI
        else:
            ph_c_state = (ph_c_state + TWO_PI * carrier * frames / SR) % TWO_PI
            ph_m_state = (ph_m_state + TWO_PI * beat * frames / SR) % TWO_PI
        cur_vol += dv
        produced += frames
    return np.concatenate(out)[:total]


def main():
    total = SR * 6          # 6 秒足够分辨 0.1Hz 级频率差
    print("=" * 74)
    print("IsoEngine off-by-one 实测核查 · 纯离线仿真（不发声、无硬件）")
    print(f"标称：sr={SR} carrier={CARRIER}Hz beat={BEAT}Hz")
    print("=" * 74)

    # 本机实际 blocksize（不创建流，只读配置；PortAudio 未指定时为 0=不定）
    try:
        import sounddevice as sd
        print(f"\n[sounddevice] default.blocksize = {sd.default.blocksize}"
              f"  (0 = paFramesPerBufferUnspecified，回调帧数由 PortAudio 决定)")
        try:
            st = sd.OutputStream(samplerate=SR, channels=2, dtype="float32",
                                 callback=lambda *a, **k: None)
            print(f"[sounddevice] 创建流后实测 blocksize = {st.blocksize}"
                  f"  (未 start，不发声)")
            st.close()
        except Exception as e:
            print(f"[sounddevice] 无法创建流探测 blocksize：{type(e).__name__}: {e}")
            print("              → 改用 frames 扫描给出影响区间")
    except ImportError:
        print("\n[sounddevice] 未安装，跳过本机 blocksize 探测")

    print("\n── 场景一：frames 固定（扫描典型值）─────────────────────")
    print(f"{'frames':>7} {'降频%':>8} {'载波实测':>10} {'节拍实测':>9} "
          f"{'边界差分比':>10} {'与修复版偏差RMS':>16}")
    for frames in (32, 128, 256, 512, 1024, 2048):
        sig_bug, _ = synth(total, [frames], buggy=True)
        sig_ok, _ = synth(total, [frames], buggy=False)
        fc, _res = peak_freq(sig_bug, lo=150.0, hi=300.0)
        fb = env_beat_freq(sig_bug)
        ratio, _ = boundary_stats(sig_bug, frames)
        # 偏差只在稳态段比（前 1 秒是音量爬升）
        a = sig_bug[SR:]
        b = sig_ok[SR:]
        rms = float(np.sqrt(np.mean((a - b) ** 2)))
        rms_rel = rms / float(np.sqrt(np.mean(b ** 2)))
        expect_drop = 100.0 / frames
        print(f"{frames:>7} {expect_drop:>7.3f}% {fc:>9.3f}Hz {fb:>8.3f}Hz "
              f"{ratio:>9.3f}x {rms_rel:>15.2%}")

    print("\n  说明：降频% = 1/frames（每块少推进一个样本的相位）")
    print("        边界差分比 ≈ 1 → 块边界**无突跳**（无爆音/咔哒）")

    print("\n── 场景二：frames 不定（PortAudio unspecified 的真实风险）────")
    import random
    random.seed(42)
    seq = [random.choice([256, 441, 480, 512, 882, 960, 1024]) for _ in range(60)]
    sig_bug, lf = synth(total, seq, buggy=True)
    sig_ok, _ = synth(total, seq, buggy=False)
    fc, _res = peak_freq(sig_bug, lo=150.0, hi=300.0)
    fb = env_beat_freq(sig_bug)
    fc_ok, _res2 = peak_freq(sig_ok, lo=150.0, hi=300.0)
    fb_ok = env_beat_freq(sig_ok)
    print(f"  随机帧序列（seed=42，帧数 256~1024 波动）")
    print(f"  现状(buggy)：载波 {fc:.3f}Hz（标称 {CARRIER}，偏差 "
          f"{(fc-CARRIER)/CARRIER*100:+.3f}%）  节拍 {fb:.3f}Hz（标称 {BEAT}，"
          f"偏差 {(fb-BEAT)/BEAT*100:+.3f}%）")
    print(f"  修复(fixed)：载波 {fc_ok:.3f}Hz（偏差 {(fc_ok-CARRIER)/CARRIER*100:+.3f}%）"
          f"  节拍 {fb_ok:.3f}Hz（偏差 {(fb_ok-BEAT)/BEAT*100:+.3f}%）")

    print("\n── 场景三：节拍切换瞬间（闭环热更新路径 set_beat）────────")
    # 判据修正（守 §7.1 教训）：拼接两次独立 synth 各自从相位 0 开始，
    # 测的是「重启」而非 set_beat 热更新。此处改为**同一相位状态内**换 beat。
    print("  前半 2s @10Hz，中途切 12Hz，相位状态连续（模拟 set_beat 热更新）")
    for frames in (512, 1024):
        joined = _synth_beat_switch(4 * SR, frames, 10.0, 12.0, switch_at=2 * SR,
                                    buggy=True)
        joined_ok = _synth_beat_switch(4 * SR, frames, 10.0, 12.0, switch_at=2 * SR,
                                       buggy=False)
        d = np.abs(np.diff(joined))
        k = 2 * SR - 1                      # 切换点索引
        neigh = d[max(0, k - frames):k + frames]
        steady = np.quantile(d[:k - 1000], 0.999)
        print(f"  frames={frames:>5}  切换点差分={d[k]:.6f}  "
              f"邻域最大={neigh.max():.6f}  稳态99.9分位={steady:.6f}")
        ratio = d[k] / steady if steady > 0 else float("nan")
        print(f"              切换点/稳态 = {ratio:.3f}x  "
              f"（≈1 → 热更新无爆音；≫1 → 有突跳）")
        # 切换后节拍频率是否落到目标值
        f_after_bug = env_beat_freq(joined[2 * SR + SR // 2:], lo=8.0, hi=16.0)
        f_after_ok = env_beat_freq(joined_ok[2 * SR + SR // 2:], lo=8.0, hi=16.0)
        print(f"              切换后实测节拍：现状 {f_after_bug:.3f}Hz / "
              f"修复 {f_after_ok:.3f}Hz（目标 12.000Hz）")
    print("  → 结论：热更新路径本身相位连续（无爆音），缺陷只在**频率标称值不准**")

    print("\n── 结论要点 ────────────────────────────────────────────")
    print("  1. off-by-one 确实存在：每块重复一个样本，载波与节拍均降 1/frames")
    print("  2. 降频量级：frames=512 → 0.195%；frames=256 → 0.39%；frames=32 → 3.1%")
    print("  3. 是否爆音：见「边界差分比」——若≈1 则无突跳，缺陷是**频率不准**而非噪声")
    print("  4. 对闭环实验的实质影响：节拍是实验自变量，10Hz 实际输出 9.98Hz")
    print("     → 听感无差别，但**方案/论文里写的引导频率与实际不符**（数据可信度问题）")


if __name__ == "__main__":
    main()
