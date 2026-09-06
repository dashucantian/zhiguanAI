#!/usr/bin/env python3
"""
闭环实验系统 —— 实时音频合成引擎

连续生成"等时节拍"（isochronic tone）：
  载波正弦（默认 220Hz）× 脉冲包络（频率 = 目标脑波频率，如 10Hz）

关键特性（闭环所需）：
  1. 播放中可随时热更新：节拍频率、音量、载波频率
  2. 相位累积合成 —— 频率切换瞬间波形连续，无爆音
  3. 音量限速爬升 —— 音量变化平滑，无咔哒声

用法:
    eng = IsoEngine(volume=0.25)
    eng.start()
    eng.set_beat(10.0)          # 运行中随时改
    ...
    eng.stop()
"""

import numpy as np
import sounddevice as sd

TWO_PI = 2.0 * np.pi


class IsoEngine:
    """实时等时节拍合成引擎。"""

    def __init__(self, samplerate=44100, carrier=220.0, beat=10.0, volume=0.25):
        self.samplerate = samplerate
        # 目标参数（外部线程可改，回调线程读取）
        self.beat = float(beat)
        self.carrier = float(carrier)
        self.volume = float(volume)
        # 内部状态（仅回调线程读写）
        self._phase_carrier = 0.0
        self._phase_mod = 0.0
        self._cur_vol = 0.0          # 实际输出音量（向目标爬升）
        self._stream = sd.OutputStream(
            samplerate=samplerate, channels=2, dtype="float32",
            callback=self._callback,
        )
        self._running = False

    # ── 对外接口 ──────────────────────────────────────────────────────
    def start(self):
        if not self._running:
            self._stream.start()
            self._running = True

    def stop(self):
        if self._running:
            self._running = False
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass

    def set_beat(self, hz):
        """热更新节拍频率（Hz）。相位连续，无爆音。"""
        self.beat = max(0.5, min(40.0, float(hz)))

    def set_volume(self, vol):
        """热更新音量（0~1）。"""
        self.volume = max(0.0, min(1.0, float(vol)))

    def set_carrier(self, hz):
        """热更新载波频率（Hz）。"""
        self.carrier = max(50.0, min(1500.0, float(hz)))

    @property
    def running(self):
        return self._running

    # ── 音频回调（实时线程） ──────────────────────────────────────────
    def _callback(self, outdata, frames, time_info, status):
        if status:
            print(f"⚠ 音频回调状态: {status}", flush=True)

        sr = self.samplerate
        n = np.arange(frames)

        # 相位累积：频率变化时波形不跳变
        ph_c = self._phase_carrier + TWO_PI * self.carrier * n / sr
        ph_m = self._phase_mod + TWO_PI * self.beat * n / sr

        # 等时节拍包络：正弦正半周取 0.6 次幂 → 50% 占空比脉冲，
        # 过零点连续（值为 0），无咔哒声
        mod = np.maximum(np.sin(ph_m), 0.0)
        env = np.power(mod, 0.6)

        # 音量限速爬升（每采样点最多变化 0.0002，约 9/秒满幅）
        target_vol = self.volume
        dv = target_vol - self._cur_vol
        max_step = 0.0002 * frames
        if abs(dv) > max_step:
            dv = max_step if dv > 0 else -max_step
        # 逐采样线性插值音量
        vol_track = self._cur_vol + dv * (n + 1) / frames

        sig = np.sin(ph_c) * env * vol_track
        outdata[:, 0] = sig
        outdata[:, 1] = sig

        self._phase_carrier = float(ph_c[-1]) % TWO_PI
        self._phase_mod = float(ph_m[-1]) % TWO_PI
        self._cur_vol += dv


if __name__ == "__main__":
    import time as _t
    print("引擎自测：播放 10Hz 等时节拍 5 秒 → 切 16Hz 5 秒...")
    eng = IsoEngine(volume=0.2)
    eng.start()
    _t.sleep(5)
    eng.set_beat(16.0)
    _t.sleep(5)
    eng.stop()
    print("✅ 自测完成")
