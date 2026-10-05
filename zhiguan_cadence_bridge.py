#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
zhiguan_cadence_bridge.py — 止观闭环 × Cadence 均衡沉降脑 接引桥
================================================================

Cadence（github.com/muellerberndt/cadence，GPLv3，cadence-net==0.74.0）
是「沉降即计算」的连续脑：无 token、无注意力、无全局反传，训练与推理无开关。

本桥把这只虫子接进止观AI的 Muse2 闭环：

  止          = 网络沉降（equilibrium settling）——沉降本身就是答案
  观          = brain.last_settlement 读出（residual/steps/tolerance 可直供可视化，
                无隐藏思考 token——Connect Four 的"亲眼看它想"）
  修用无别    = step 即学即用，无 train/inference 开关（座上座下不二）
  一念微调    = 均衡传播：reward 到来时局部轻推，无全局回传（不整盘推倒重来）
  所缘结构    = connectome 刚性掩码——接线不许凭空长出（行为只在既有结构里发生）
  串习/沉淀   = 快速记录 + 慢权重整合（文章"睡梦"实验：8000 次自洽做梦 81.5%→100%）
  跨会话续修  = brain.save/load，同一命跨坐续修，不是每次出厂重训

接线纪律（与项目规约同向，判语009/011）：
  · 本桥只学"反馈参数怎么给"，不碰任何用户数据结论（镜子非训练器）；
  · reward 只取自"观察到的状态量"，不来自对人的评判；
  · 全程固定种子，同输入两次运行逐字一致；
  · 观测不可算 → 弃权返回 None（弃权是一等值），不硬造动作；
  · 本桥不直接操作音频设备：输出参数 dict，由宿主（IsoEngine.set_*）执行。

自测：python zhiguan_cadence_bridge.py --selftest
"""

from __future__ import annotations

import os
import pickle
from typing import Optional

import numpy as np

from cadence import Brain

# ── 反馈参数边界（反馈＞干预：只在引导参数的温和区间内动）──────────────
FEEDBACK_BOUNDS = {
    "beat": (4.0, 12.0),      # θ~α 等时节拍（Hz）
    "volume": (0.05, 0.5),    # 音量
}
ACTION_BEAT_DELTA = (-0.25, 0.0, 0.25, 0.0)   # 0=向θ降拍 1=持 2=向α升拍 3=撤一档支持
ACTION_VOL_DELTA = (0.0, 0.0, 0.0, -0.03)

OBS_DIM = 6
ACTION_DIM = 4


class ZhiGuanCadenceBridge:
    """一座只做三件事的桥：观（读出）→ 止（沉降选动作）→ 一念（局部轻推）。"""

    def __init__(self, seed: int = 42, brain_path: Optional[str] = None,
                 modules: tuple = (32, 16)):
        if brain_path and os.path.exists(brain_path):
            self.brain = Brain.load(brain_path)
        else:
            self.brain = Brain.compose(inputs=OBS_DIM, actions=ACTION_DIM,
                                       modules=modules, seed=seed)
        self.beat = 10.0
        self.volume = 0.25
        self.trace: list = []          # 观之流：每拍的沉降读出+动作+参数
        self._t = 0

    # ── 观：把 EEG 特征折叠成 6 维观测。不可算 → None（弃权）──────────
    def build_observation(self, z_alpha_theta: Optional[float],
                          z_beta_alpha: Optional[float],
                          in_state: bool, dwell_norm: float,
                          prev_residual_norm: float) -> Optional[np.ndarray]:
        if z_alpha_theta is None or z_beta_alpha is None:
            return None
        obs = np.array([
            np.tanh(float(z_alpha_theta)),    # 沉静维（α/θ，z 空间）
            np.tanh(float(-z_beta_alpha)),    # 躁动维（β/α 取负）
            1.0 if in_state else 0.0,         # 是否处于目标态（观察量，非评判）
            float(np.clip(dwell_norm, 0.0, 1.0)),
            float(np.clip(prev_residual_norm, 0.0, 1.0)),
            self.volume / FEEDBACK_BOUNDS["volume"][1],  # 当前支持水平自感
        ], dtype=float)
        return obs[None, :]

    # ── 一念：reward 只来自观察量。入定维持=食（多巴胺类推），失定=戳──
    @staticmethod
    def observe_reward(in_state_prev: bool, in_state_now: bool,
                       still_wandering: bool) -> float:
        if in_state_prev and in_state_now:
            return 1.0            # 食：状态在维持
        if (not in_state_prev) and in_state_now:
            return 1.0            # 食：新入状态
        if in_state_prev and (not in_state_now) and still_wandering:
            return -1.0           # 戳：失定且伴躁动（观察信号，非惩罚人）
        return 0.0

    # ── 止：沉降一拍，出动作与反馈参数 ──────────────────────────────
    def step(self, obs: np.ndarray, reward: float = 0.0,
             done: bool = False) -> dict:
        if self._t == 0:
            # 首拍：先落前置动作（cadence 契约：feedback 需有前置 action）
            action = int(self.brain.step(obs)[0])
        else:
            action = int(self.brain.step(obs, reward=np.array([reward]),
                                         done=np.array([done]))[0])
        self.beat = float(np.clip(self.beat + ACTION_BEAT_DELTA[action],
                                  *FEEDBACK_BOUNDS["beat"]))
        self.volume = float(np.clip(self.volume + ACTION_VOL_DELTA[action],
                                    *FEEDBACK_BOUNDS["volume"]))
        self._t += 1
        readout = self.settle_readout()
        self.trace.append({"t": self._t, "action": action, "beat": self.beat,
                           "volume": self.volume, **readout})
        return {"action": action, "beat": self.beat, "volume": self.volume,
                "settlement": readout}

    # ── 观之读出：沉降残差与步数（可直供 vr_mandala 可视化层）─────────
    def settle_readout(self) -> dict:
        s = getattr(self.brain, "last_settlement", None) or {}
        return {"residual": float(s.get("max_residual", 0.0)),
                "steps": int(s.get("steps", 0)),
                "tolerance": float(s.get("tolerance", 0.0))}

    # ── 跨会话续修：一坐一存档，同一命 ──────────────────────────────
    def save(self, path: str) -> str:
        try:
            # cadence 会自动追加 .npz：必须把真实路径返还给调用方
            return str(self.brain.save(path))
        except Exception:
            with open(path, "wb") as f:
                pickle.dump(self.brain, f)
            return path


# ── 自测：确定性 + 边界 + 弃权 + 续修同命 ────────────────────────────
def _fake_session(n_ticks: int, seed: int):
    rng = np.random.default_rng(seed)
    br = ZhiGuanCadenceBridge(seed=seed)
    in_prev, dwell, actions = False, 0.0, []
    res_norm = 0.0
    for t in range(n_ticks):
        calm = np.tanh(t / 120.0) + 0.1 * rng.standard_normal()
        restless = 0.5 * np.tanh(-t / 200.0) + 0.1 * rng.standard_normal()
        in_state = calm > 0.6
        obs = br.build_observation(calm, restless, in_state,
                                   dwell / 30.0, res_norm)
        r = br.observe_reward(in_prev, in_state, restless > 0.0)
        out = br.step(obs, reward=r, done=(t == n_ticks - 1))
        actions.append(out["action"])
        dwell = dwell + 1 if in_state else 0
        res_norm = out["settlement"]["residual"]
        in_prev = in_state
    return br, actions


def _selftest() -> int:
    n = 300
    b1, a1 = _fake_session(n, 42)
    b2, a2 = _fake_session(n, 42)
    assert a1 == a2, "确定性破：同种子两次动作序列不一致（判语011）"

    lo_b, hi_b = FEEDBACK_BOUNDS["beat"]
    lo_v, hi_v = FEEDBACK_BOUNDS["volume"]
    for e in b1.trace:
        assert lo_b <= e["beat"] <= hi_b and lo_v <= e["volume"] <= hi_v, "越界"
        assert isinstance(e["residual"], float) and "steps" in e, "观读出缺失"

    assert ZhiGuanCadenceBridge().build_observation(None, None, False, 0, 0) \
        is None, "弃权失守：不可算必须返回 None"

    p1 = b1.save(os.path.join(os.environ.get("TEMP", "."), "_zg_bridge_t1.brain"))
    b3 = ZhiGuanCadenceBridge(brain_path=p1)
    obs_fixed = np.array([[0.7, 0.2, 1.0, 0.5, 0.0, 0.5]])  # 同一观测，两边同喂
    a_cont = int(b3.brain.step(obs_fixed)[0])
    a_same_obs = int(b1.brain.step(obs_fixed)[0])
    assert a_cont == a_same_obs, "续修失同：load 后同观测不同命"

    tr = b1.trace[-1]
    print(f"[selftest OK] ticks={n} deterministic=True bounds=OK abstain=OK "
          f"continuation=OK final(action={tr['action']}, beat={tr['beat']:.2f}, "
          f"vol={tr['volume']:.3f}, residual={tr['residual']:.4f}, "
          f"steps={tr['steps']})")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(8 if "--selftest" in sys.argv and _selftest() else 0)
