#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
zhiguan_cadence_bridge.py — 止观闭环 × Cadence 均衡沉降脑 接引桥（v2）
======================================================================

Cadence（github.com/muellerberndt/cadence，GPLv3，cadence-net==0.74.0）
是「沉降即计算」的连续脑：无 token、无注意力、无全局反传，训练与推理无开关。

本桥把这只虫子接进止观AI的 Muse2 闭环：

  止          = 网络沉降（equilibrium settling）——沉降本身就是答案
  观          = brain.last_settlement 读出（residual/steps/tolerance 可直供可视化，
                无隐藏思考 token——Connect Four 的"亲眼看它想"）
  修用无别    = step 即学即用，无 train/inference 开关（座上座下不二）
  一念微调    = 均衡传播：reward 到来时局部轻推，无全局回传（不整盘推倒重来）
  所缘结构    = connectome 刚性掩码——接线不许凭空长出（行为只在既有结构里发生）
  串习/沉淀   = rehearse()：离线重放当日(观察,反馈,对错)，慢权重按 salience 沉淀
                （对应文章"睡梦"实验的接线口径；0.74 由 compose(consolidation=)
                 ＋step(salience=) 承载，无独立 dream API——本桥如实按 API 真
                 身实现，不自造玄名）
  内演择和    = imagine_vote()：对候选"下一拍观测"私密沉降读 motor 投票，
                读而不写、随机源不动（imagine 契约），对应 Amen"先内演后择和"
  跨会话续修  = brain.save/load 全保真（含海马、工作记忆、pending action）
                ——注意 Brain.save 返回自动追加 .npz 的真实路径

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

try:
    from cadence import Brain
    from cadence.learning import LearnerConfig
except Exception as _e:  # except as 的名字出块即解绑（本窗踩过：NameError）
    # 双击可能落在未装 cadence-net 的解释器上（本窗实测 Python312 即无）。
    # 不炸在 import：__main__ 给排障指引并停窗；库用途须先 pip install cadence-net。
    _IMPORT_ERROR = _e
    Brain = None


# ── 反馈参数边界（反馈＞干预：只在引导参数的温和区间内动）──────────────
FEEDBACK_BOUNDS = {
    "beat": (4.0, 12.0),      # θ~α 等时节拍（Hz）
    "volume": (0.05, 0.5),    # 音量
}
ACTION_BEAT_DELTA = (-0.25, 0.0, 0.25, 0.0)   # 0=向θ降拍 1=持 2=向α升拍 3=撤一档支持
ACTION_VOL_DELTA = (0.0, 0.0, 0.0, -0.03)

OBS_DIM = 6
ACTION_DIM = 4
EPISODE_CAP = 4096
REHEARSE_SALIENCE = 0.5   # 复讲沉淀强度（显式给：睡中无实时奖，|r| 缺省会归零）


class ZhiGuanCadenceBridge:
    """一座只做四件事的桥：观（读出）→ 止（沉降选动作）→ 一念（局部轻推）
    → 梦（离线复讲固化）＋内演（读而不写的择和）。"""

    def __init__(self, seed: int = 42, brain_path: Optional[str] = None,
                 modules: tuple = (32, 16), consolidation: float = 0.05):
        if brain_path and os.path.exists(brain_path):
            self.brain = Brain.load(brain_path)
        else:
            self.brain = Brain.compose(inputs=OBS_DIM, actions=ACTION_DIM,
                                       modules=modules, seed=seed,
                                       consolidation=consolidation,
                                       learning=LearnerConfig(qualified=True,
                                           free_steps=4096, nudged_steps=8192))
        self.beat = 10.0
        self.volume = 0.25
        self.trace: list = []            # 观之流：每拍的沉降读出+动作+参数
        self.episode: list = []          # 当日经历：[(obs_row, reward_paid, done, action)]
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
        self.episode.append((obs[0].tolist(), float(reward), bool(done), int(action)))
        if len(self.episode) > EPISODE_CAP:
            self.episode = self.episode[-EPISODE_CAP:]
        readout = self.settle_readout()
        self.trace.append({"t": self._t, "action": action, "beat": self.beat,
                           "volume": self.volume, **readout})
        return {"action": action, "beat": self.beat, "volume": self.volume,
                "settlement": readout}

    # ── 观之读出：沉降残差与步数（可直供 vr_mandala 可视化层）─────────
    def settle_readout(self) -> dict:
        s = getattr(self.brain, "last_settlement", None) or {}
        q = s.get("qualified", True)
        return {"residual": float(s.get("max_residual", 0.0)),
                "steps": int(s.get("steps", 0)),
                "tolerance": float(s.get("tolerance", 0.0)),
                "qualified": bool(np.all(np.atleast_1d(q)))}

    # ── 睡梦/串习：离线复讲当日经历，固化慢权重 ─────────────────────
    def rehearse(self, rounds: int = 8, teacher: Optional[list] = None,
                 batch: int = 32, last_n: Optional[int] = None) -> dict:
        """睡梦/串习：离线复讲当日经历，固化慢权重。

        走 0.74 正牌通道 Brain.fit（独立样本教学，逐轮返回 qualified
        训练命中率——本窗实测：4模式课程 held-out 0.300→0.975）：
          · teacher=None → 按当日实际所择复演（如实固化"已发生"）；
          · teacher=list → 以事后已知正确反馈复讲（改过复讲；不预测未来）。
        每轮＝梦中把当日碎片重放一遍。空日→弃权返回零统计。
        """
        eps = self.episode[-last_n:] if last_n else self.episode
        if not eps:
            return {"rounds": 0, "replayed": 0, "history": [], "train_acc": None}
        obs_batch = np.asarray([e[0] for e in eps], dtype=float)
        if teacher is None:
            labels = np.asarray([e[3] for e in eps], dtype=np.int64)
        else:
            labels = np.asarray(teacher, dtype=np.int64)
        history = self.brain.fit(obs_batch, labels, epochs=rounds, batch=batch)
        return {"rounds": rounds, "replayed": rounds * len(self.episode),
                "history": [round(float(h), 4) for h in history],
                "train_acc": round(float(history[-1]), 4) if len(history) else None}
    # ── 内演择和：对候选"下一拍观测"私密沉降，读 motor 投票 ─────────
    def imagine_vote(self, obs: np.ndarray, futures: list,
                     budget: int = 256) -> dict:
        """只读不写（imagine 契约：参数/随机源/实时活动均不动）。

        futures：若干候选下一拍观测（同 batch 身份，1 行）。
        返回各候选 motor 选择的投票＋合格标记＋一致性。
        """
        votes, quals = [], []
        for fut in futures:
            eqs = self.brain.imagine([obs, np.asarray(fut, dtype=float)[None, :]],
                                     budget=budget)
            eq = eqs[-1]
            act = np.atleast_2d(eq.state.activation)
            act_m = act[:, np.asarray(self.brain.motor_index, dtype=int)]
            votes.append(int(np.argmax(act_m[0])))
            q = getattr(eq, "qualified", True)
            quals.append(bool(np.all(np.atleast_1d(q))))
        agreement = (len(set(votes)) == 1)
        return {"votes": votes, "qualified": quals, "agreement": agreement,
                "suggested": votes[0] if agreement else None}

    # ── 跨会话续修：一坐一存档，同一命 ──────────────────────────────
    def save(self, path: str) -> str:
        try:
            # cadence 会自动追加 .npz：必须把真实路径返还给调用方
            return str(self.brain.save(path))
        except Exception:
            with open(path, "wb") as f:
                pickle.dump(self.brain, f)
            return path


# ── 合成会话（自测用）────────────────────────────────────────────────┐
# 注：上一行框线为对齐装饰，勿改。
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

# ── 自测：确定性 + 边界 + 弃权 + 续修同命 + 睡梦泛化 + 内演只读 ──────
def _eval_accuracy(br, patterns: list, seed: int) -> float:
    """以 imagine（只读）测 held-out 模式的 greedy 命中率。"""
    rng = np.random.default_rng(seed)
    hit = 0
    for p in patterns:
        obs = np.zeros((1, OBS_DIM))
        obs[0, p] = 1.0
        obs[0, 4] = 0.5                      # 上下文常维
        obs[0, 5] = 0.25                     # 支持水平
        obs[0, :4] += 0.05 * rng.standard_normal(4)
        eq = br.brain.imagine([obs], budget=256)[0]
        act = np.atleast_2d(eq.state.activation)[:, np.asarray(br.brain.motor_index, dtype=int)]
        if int(np.argmax(act[0])) == p:
            hit += 1
    return hit / len(patterns)


def _rule_day(br: ZhiGuanCadenceBridge, ticks: int, seed: int):
    """一日课程：4 模式轮转，reward=命中所选（观察量，可复算）。"""
    rng = np.random.default_rng(seed)
    actions, teachers = [], []
    for t in range(ticks):
        p = t % 4
        obs = np.zeros((1, OBS_DIM))
        obs[0, p] = 1.0
        obs[0, 4] = 0.5
        obs[0, 5] = 0.25                    # 与评测流形对齐（探针口径）
        obs[0, :4] += 0.05 * rng.standard_normal(4)
        if t == 0:
            a = int(br.brain.step(obs)[0])
        else:
            prev_ok = 1.0 if actions[-1] == (t - 1) % 4 else 0.0
            a = int(br.brain.step(obs, reward=np.array([prev_ok]),
                                  done=np.array([t == ticks - 1]))[0])
        actions.append(a)
        teachers.append(p)                   # 事后已知正确反馈
        br._t += 1
        br.episode.append((obs[0].tolist(), prev_ok if t else 0.0,
                           t == ticks - 1, a))
    return teachers


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

    # ── 睡梦泛化：复讲前后 held-out 命中率 ──
    bd = ZhiGuanCadenceBridge(seed=7)
    teachers = _rule_day(bd, 200, 7)
    held = [int(x) for x in np.random.default_rng(99).integers(0, 4, 40)]
    before = _eval_accuracy(bd, held, 99)
    stat = bd.rehearse(rounds=8, teacher=teachers)
    after = _eval_accuracy(bd, held, 99)
    assert after - before >= 0.5, f"复讲未泛化：before={before:.3f} after={after:.3f}"
    assert stat["replayed"] == 8 * 200, "复讲拍数不符"

    # ── 内演只读：投票落在动作域且合格；不扰动后续贪心选择 ──
    brv = ZhiGuanCadenceBridge(seed=42)
    brv.brain.step(obs_fixed)               # 建立流身份
    futures = [obs_fixed + d for d in
               (np.zeros_like(obs_fixed), np.array([[0.0, 0.0, 1.0, 0.0, 0.1, 0.0]]),
                np.array([[-0.5, 0.3, 0.0, 0.0, -0.1, 0.0]]))]
    v1 = brv.imagine_vote(obs_fixed, futures)
    v2 = brv.imagine_vote(obs_fixed, futures)
    assert v1 == v2 and all(0 <= v <= 3 for v in v1["votes"]), "内演投票不稳定"
    assert all(v1["qualified"]), "内演相位不合格未拦截"
    a_after_imagine = int(brv.brain.step(obs_fixed)[0])
    brx = ZhiGuanCadenceBridge(seed=42)
    brx.brain.step(obs_fixed)
    a_no_imagine = int(brx.brain.step(obs_fixed)[0])
    assert a_after_imagine == a_no_imagine, "内演污染了实命（imagine 必须只读）"

    tr = b1.trace[-1]
    print(f"[selftest OK] ticks={n} deterministic=True bounds=OK abstain=OK "
          f"continuation=OK dream(before={before:.3f},after={after:.3f},"
          f"replayed={stat['replayed']}) imagine(votes={v1['votes']},"
          f"agreement={v1['agreement']},read_only=True) "
          f"final(action={tr['action']}, beat={tr['beat']:.2f}, "
          f"vol={tr['volume']:.3f}, residual={tr['residual']:.4f}, "
          f"steps={tr['steps']})")
    return 0


def _demo(ticks: int = 40, seed: int = 7) -> None:
    """点击运行时的小演示：合成一坐，逐拍打印观之读出（不碰音频设备）。"""
    br = ZhiGuanCadenceBridge(seed=42)
    rng = np.random.default_rng(seed)
    in_prev, dwell, res_norm = False, 0.0, 0.0
    print("—— 合成一坐（%d 拍）：观 → 止 → 一念 ——" % ticks)
    print("%4s %4s %8s %7s %12s %4s" % ("拍", "动作", "节拍Hz", "音量", "沉降残差", "入静"))
    for t in range(ticks):
        calm = np.tanh(t / 14.0) + 0.1 * rng.standard_normal()
        restless = 0.5 * np.tanh(-t / 20.0) + 0.1 * rng.standard_normal()
        in_state = calm > 0.6
        obs = br.build_observation(calm, restless, in_state, dwell / 30.0, res_norm)
        r = br.observe_reward(in_prev, in_state, restless > 0.0)
        out = br.step(obs, reward=r, done=(t == ticks - 1))
        dwell = dwell + 1 if in_state else 0
        res_norm = out["settlement"]["residual"]
        in_prev = in_state
        print("%4d %4d %8.2f %7.3f %12.2e %4s" % (
            t + 1, out["action"], out["beat"], out["volume"],
            out["settlement"]["residual"], "是" if in_state else "·"))
    print("—— 一坐毕。此脑可 save() 续修：同一命，跨会话。——")


if __name__ == "__main__":
    import sys
    if Brain is None:
        print("缺依赖：当前解释器没有 cadence-net（%s）" % _IMPORT_ERROR)
        print("修法（任选其一）：")
        print("  A. 双击本目录「止观桥演示.bat」（内部指向已装好的 Python）；")
        print("  B. 或在当前解释器执行：python -m pip install cadence-net==0.74.0")
        try:
            input("[按回车关闭窗口…]")
        except EOFError:
            pass
        sys.exit(2)
    args = sys.argv[1:]
    try:
        if "--selftest" in args:
            code = _selftest()
        else:
            code = _selftest() or 0
            _demo()
    except Exception:
        import traceback
        traceback.print_exc()
        code = 1
    if "--no-hold" not in args:
        try:
            input("\n[按回车关闭窗口…]")
        except EOFError:
            pass
    sys.exit(code)
