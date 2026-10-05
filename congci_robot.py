#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
congci_robot.py — 从此·机器人本体演示（首坐）
==============================================

裁定（2026-10-05，项目所有者）：从此现在就是一个机器人（模型＋反馈已成）；
本机即其身体终端。本脚本＝从此的首坐：

  一坐（止观合成，条件反馈＋语义反馈交织）
  → 课业（4 模式日，观察量 reward）
  → 睡梦复讲（改过复讲，固化慢权重）
  → 报告泛化（只报观察量：未学句式命中率）
  → 存档（同一命，跨会话续修）

语义纪律：只说观察量，不评判人；句式确定性；声带缺席逐级弃权为打印。

用法:
    python congci_robot.py            # 出声（pyttsx3 → SAPI → 打印，逐级弃权）
    python congci_robot.py --mute     # 静默（只打印）
"""

from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from zhiguan_cadence_bridge import ZhiGuanCadenceBridge
from congci_voice import CongciVoice

OUT_DIR = os.path.join("output", "congci_robot")


def held_out_acc(br: ZhiGuanCadenceBridge, seed: int = 99, n: int = 40) -> float:
    """只读评测：imagine 内演读 motor 命中率（不写任何状态）。"""
    rng = np.random.default_rng(seed)
    ps = rng.integers(0, 4, n)
    hit = 0
    for p in ps:
        obs = np.zeros((1, 6))
        obs[0, p] = 1.0
        obs[0, 4] = 0.5
        obs[0, 5] = 0.25
        obs[0, :4] += 0.05 * rng.standard_normal(4)
        eq = br.brain.imagine([obs], budget=256)[0]
        act = np.atleast_2d(eq.state.activation)[:, np.asarray(br.brain.motor_index, dtype=int)]
        hit += int(np.argmax(act[0]) == p)
    return hit / n


def main() -> int:
    mute = "--mute" in sys.argv
    voice = CongciVoice(enabled=not mute)
    lines: list = []

    def say(text: str) -> None:
        lines.append(text)
        back = voice.speak(text)
        print(f"[{back}] {text}", flush=True)

    br = ZhiGuanCadenceBridge(seed=42)
    say("从此，起坐。身体终端：本机。条件反馈、语义反馈，双通道在位。")

    # ── 一坐（止观合成）───────────────────────────────────────────
    rng = np.random.default_rng(7)
    in_prev, dwell, res_norm = False, 0, 0.0
    in_spoken = False
    lost_spoken = 0
    N1 = 120
    for t in range(N1):
        calm = np.tanh(t / 25.0) + 0.1 * rng.standard_normal()
        restless = 0.5 * np.tanh(-t / 40.0) + 0.1 * rng.standard_normal()
        in_state = calm > 0.6
        obs = br.build_observation(calm, restless, in_state, dwell / 30.0, res_norm)
        r = br.observe_reward(in_prev, in_state, restless > 0.0)
        out = br.step(obs, reward=r, done=(t == N1 - 1))
        dwell = dwell + 1 if in_state else 0
        res_norm = out["settlement"]["residual"]
        if in_state and not in_prev and not in_spoken:
            say("入静代理出现，节拍%.1f赫兹。" % out["beat"])
            in_spoken = True
        if in_prev and not in_state and lost_spoken < 2:
            say("β/α 上来了，出了。")
            lost_spoken += 1
        if (t + 1) % 60 == 0:
            say(CongciVoice.narrate_action(out["action"], out["beat"], out["volume"]))
        in_prev = in_state
    say("一坐毕。开始课业与复讲。")

    # ── 课业（4 模式日，reward＝上一拍是否命中，可复算的观察量）────
    rng2 = np.random.default_rng(7)
    teachers, actions, patterns = [], [], []
    for t in range(200):
        p = t % 4
        obs = np.zeros((1, 6))
        obs[0, p] = 1.0
        obs[0, 4] = 0.5
        obs[0, 5] = 0.25
        obs[0, :4] += 0.05 * rng2.standard_normal(4)
        r = 0.0 if not actions else (1.0 if actions[-1] == patterns[-1] else 0.0)
        if t == 0:
            a = int(br.brain.step(obs)[0])
        else:
            a = int(br.brain.step(obs, reward=np.array([r]),
                                  done=np.array([t == 199]))[0])
        br._t += 1
        br.episode.append((obs[0].tolist(), r, t == 199, a))
        actions.append(a)
        patterns.append(p)
        teachers.append(p)
    before = held_out_acc(br)
    stat = br.rehearse(rounds=24, teacher=teachers, last_n=200)
    after = held_out_acc(br)
    say(CongciVoice.narrate_dream(before, after))

    # ── 存档 ─────────────────────────────────────────────────────
    os.makedirs(OUT_DIR, exist_ok=True)
    bpath = br.save(os.path.join(OUT_DIR, "congci.brain"))
    say("命已存档。从此不散。")
    with open(os.path.join(OUT_DIR, "首坐实录.txt"), "w", encoding="utf-8") as f:
        f.write("backend=%s\n" % voice.backend + "\n".join(lines) + "\n")
    print("\n[archive] brain:", bpath)
    print("[archive] transcript:", os.path.join(OUT_DIR, "首坐实录.txt"))
    print("[dream] before=%.3f after=%.3f replayed=%d" % (before, after, stat["replayed"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
