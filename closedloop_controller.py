#!/usr/bin/env python3
"""
闭环实验系统 —— 决策层

职责：把实时脑电特征翻译成音频指令（节拍频率 + 音量）。

控制策略（阈值决策起步版，透明可解释）：
  1. 基线期：收集 2 分钟频段数据，取 Alpha 分贝中位数作为个人基线
  2. 奖励逻辑（经典神经反馈范式）：
     - Alpha 能量高于「基线 + 阈值」→ 视为进入放松态 → 音量升（奖励）
     - Alpha 能量回落 → 音量缓慢淡出（撤除奖励）
  3. 节拍频率自适应（引导目标）：
     - 西塔/贝塔比偏高（困倦）→ 节拍升到 12Hz 保持清醒放松
     - 西塔/贝塔比偏低（紧张/杂念多）→ 节拍降到 8Hz 引导慢下来
     - 其余 → 维持 10Hz（阿尔法引导）
  4. 平滑约束：每个决策周期节拍最多变 0.5Hz，避免频繁跳变

用法:
    ctrl = ClosedLoopController()
    ctrl.add_baseline(alpha_db)        # 基线期反复调用
    ctrl.finalize_baseline()           # 基线期结束
    beat, vol, note = ctrl.update(features_dict)   # 闭环期每 2 秒调用
"""

import statistics


class ClosedLoopController:
    def __init__(self,
                 target_band="alpha",
                 reward_threshold_db=1.0,   # 超过基线多少算"奖励触发"
                 vol_max=0.35,              # 奖励态最大音量
                 vol_idle=0.05,             # 静默态音量（保持可闻提示）
                 vol_smooth_step=0.05,      # 每周期音量最大变化量
                 beat_default=10.0,         # 默认引导节拍
                 beat_drowsy=12.0,          # 困倦时的目标节拍
                 beat_tense=8.0,            # 紧张时的目标节拍
                 beat_min=6.0, beat_max=14.0,
                 beat_step=0.5,             # 每周期节拍最大变化量
                 tb_high=4.0, tb_low=1.5,   # θ/β 比判定阈值
                 maintain_band_db=-0.5):    # 维持区下限（低于基线多少仍维持）
        self.target_band = target_band
        self.reward_threshold_db = reward_threshold_db
        self.vol_max = vol_max
        self.vol_idle = vol_idle
        self.vol_smooth_step = vol_smooth_step
        self.beat_default = beat_default
        self.beat_drowsy = beat_drowsy
        self.beat_tense = beat_tense
        self.beat_min = beat_min
        self.beat_max = beat_max
        self.beat_step = beat_step
        self.tb_high = tb_high
        self.tb_low = tb_low
        self.maintain_band_db = maintain_band_db

        self._baseline_samples = []
        self.baseline_db = None            # 基线中位数
        self.beat = beat_default           # 当前节拍频率
        self.volume = vol_idle             # 当前指令音量
        self._last_alpha = None

    @classmethod
    def from_config(cls, cfg):
        """从实验配置字典构造（config['controller'] 段）。"""
        c = cfg.get("controller", {})
        return cls(
            target_band=c.get("target_band", "alpha"),
            reward_threshold_db=c.get("reward_threshold_db", 1.0),
            vol_max=c.get("vol_max", 0.35),
            vol_idle=c.get("vol_idle", 0.05),
            vol_smooth_step=c.get("vol_smooth_step", 0.05),
            beat_default=c.get("beat_default", 10.0),
            beat_drowsy=c.get("beat_drowsy", 12.0),
            beat_tense=c.get("beat_tense", 8.0),
            beat_min=c.get("beat_min", 6.0),
            beat_max=c.get("beat_max", 14.0),
            beat_step=c.get("beat_step", 0.5),
            tb_high=c.get("tb_high", 4.0),
            tb_low=c.get("tb_low", 1.5),
            maintain_band_db=c.get("maintain_band_db", -0.5))

    # ── 基线期 ────────────────────────────────────────────────────────
    def add_baseline(self, band_db):
        if band_db is not None:
            self._baseline_samples.append(band_db)

    def finalize_baseline(self):
        """基线期结束时调用，计算个人基线。"""
        if self._baseline_samples:
            self.baseline_db = statistics.median(self._baseline_samples)
        return self.baseline_db

    @property
    def has_baseline(self):
        return self.baseline_db is not None

    # ── 闭环期 ────────────────────────────────────────────────────────
    def update(self, features):
        """
        features: dict，至少含 'alpha'(dB)、'theta'(dB)、'beta'(dB)
        返回: (beat_hz, volume, 决策说明字符串)
        """
        alpha = features.get(self.target_band)
        theta = features.get("theta")
        beta = features.get("beta")
        if alpha is None or self.baseline_db is None:
            return self.beat, self.volume, "数据不足"

        self._last_alpha = alpha

        # ── 音量奖励逻辑 ──
        excess = alpha - self.baseline_db
        if excess >= self.reward_threshold_db:
            target_vol = self.vol_max
            note = f"Alpha高于基线{excess:+.1f}dB→奖励(音量升)"
        elif excess >= self.maintain_band_db:
            target_vol = self.volume       # 维持
            note = f"Alpha接近基线({excess:+.1f}dB)→维持"
        else:
            target_vol = self.vol_idle
            note = f"Alpha低于基线{excess:+.1f}dB→淡出"

        # 音量平滑：每周期最多变 vol_smooth_step
        dv = target_vol - self.volume
        self.volume += max(-self.vol_smooth_step,
                           min(self.vol_smooth_step, dv))

        # ── 节拍频率自适应 ──
        desired = self.beat_default
        if theta is not None and beta is not None and beta > -100:
            tb = 10 ** ((theta - beta) / 10.0)
            if tb > self.tb_high:
                desired = self.beat_drowsy
                note += f";θ/β偏高→节拍升{self.beat_drowsy:.0f}Hz防困"
            elif tb < self.tb_low:
                desired = self.beat_tense
                note += f";θ/β偏低→节拍降{self.beat_tense:.0f}Hz助松"

        # 节拍平滑：每周期最多变 beat_step
        d_beat = desired - self.beat
        self.beat += max(-self.beat_step, min(self.beat_step, d_beat))
        self.beat = max(self.beat_min, min(self.beat_max, self.beat))

        return self.beat, self.volume, note


if __name__ == "__main__":
    # 单元自测：模拟基线 20dB，之后 alpha 在 18~24 之间波动
    ctrl = ClosedLoopController()
    for v in [19.5, 20.1, 19.8, 20.5, 20.2, 19.9]:
        ctrl.add_baseline(v)
    base = ctrl.finalize_baseline()
    print(f"基线: {base:.2f} dB")
    assert 19.5 <= base <= 20.5

    for a in [22.0, 23.0, 24.0, 18.0, 17.0, 19.8]:
        beat, vol, note = ctrl.update(
            {"alpha": a, "theta": 24.0, "beta": 18.5})
        print(f"  alpha={a:5.1f} → beat={beat:.1f}Hz vol={vol:.2f} | {note}")

    # 验证：高 alpha 时音量应升到最大附近
    ctrl2 = ClosedLoopController()
    for v in [20.0] * 6:
        ctrl2.add_baseline(v)
    ctrl2.finalize_baseline()
    for _ in range(6):
        beat, vol, note = ctrl2.update(
            {"alpha": 23.0, "theta": 24.0, "beta": 18.5})
    assert vol > 0.3, f"奖励态音量未升到奖励水平: {vol}"
    print("✅ 决策层自测通过")
