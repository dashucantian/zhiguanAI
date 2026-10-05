#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cadence_replay_experiment.py — 真实 Muse npz 离线回放 × Cadence 止观桥
======================================================================

只读回放：不连设备、不触碰闭环实时链（与 state_segmentation 同纪律）。
npz 需含 eeg (N, C) 与 timestamps (N,)（muse2 report 口径）。

口径（演示用，非正式状态判据）：
  · sfreq 由 timestamps 中位差反推；
  · 特征走 state_segmentation.extract_features（1s epoch，BANDS/RATIOS 同源）；
  · 跨通道平均 log10 功率 → z → z(α−θ)、z(β−α)；
  · in_state 代理标记：z(α−θ) > 0.8；
  · 无效 epoch → 弃权拍（abstain），不动脑、不记经历。

用法:
    python cadence_replay_experiment.py [npz路径] [--out 目录]
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from state_segmentation import extract_features
from zhiguan_cadence_bridge import ZhiGuanCadenceBridge

IN_STATE_Z = 0.8


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("npz", nargs="?",
                    default=os.path.join("muse2-repo", "muse2-master", "report",
                                         "local_20260831_210138.npz"))
    ap.add_argument("--out", default=os.path.join("output", "cadence_replay"))
    a = ap.parse_args()

    d = np.load(a.npz, allow_pickle=False)
    eeg = np.asarray(d["eeg"], dtype=float)
    if eeg.ndim != 2:
        print(json.dumps({"ok": False, "reason": "npz 需含 eeg(N,C)"}))
        return 2
    if "timestamps" in d.files:
        dt = np.diff(np.asarray(d["timestamps"], dtype=float))
        dt = dt[dt > 0]
        sfreq = float(np.round(1.0 / np.median(dt))) if len(dt) else 0.0
        sfreq_src = "inferred_from_timestamps"
    else:
        sfreq = 256.0                       # muse2 report 标准率（本件未存时间戳）
        sfreq_src = "assumed_muse256"
    if sfreq < 50:
        print(json.dumps({"ok": False, "reason": f"sfreq 不可用 ({sfreq})"}))
        return 2

    feats, valid = extract_features(eeg, sfreq)
    if feats is None:
        print(json.dumps({"ok": False, "reason": "有效 epoch 不足，弃权"}))
        return 2

    n_ch = eeg.shape[1]
    powm = feats[:, :5 * n_ch].reshape(-1, n_ch, 5).mean(axis=1)   # (T,5)
    log = np.log10(np.maximum(powm, 1e-12))
    z = (log - log.mean(0)) / np.maximum(log.std(0), 1e-9)
    z_at = z[:, 2] - z[:, 1]        # alpha − theta（z 空间差）
    z_ba = z[:, 3] - z[:, 2]        # beta − alpha

    in_state = z_at > IN_STATE_Z
    br = ZhiGuanCadenceBridge(seed=42)
    dwell, res_norm, prev = 0, 0.0, False
    trace = []
    T = feats.shape[0]
    for t in range(T):
        if not valid[t]:
            trace.append({"t": t + 1, "abstain": True})
            continue
        obs = br.build_observation(float(z_at[t]), float(z_ba[t]),
                                   bool(in_state[t]), dwell / 30.0, res_norm)
        r = br.observe_reward(prev, bool(in_state[t]), float(z_ba[t]) > 0.0)
        out = br.step(obs, reward=r, done=(t == T - 1))
        dwell = dwell + 1 if in_state[t] else 0
        res_norm = out["settlement"]["residual"]
        prev = bool(in_state[t])
        trace.append({"t": t + 1, **out["settlement"], "action": out["action"],
                      "beat": round(out["beat"], 3),
                      "volume": round(out["volume"], 4),
                      "z_at": round(float(z_at[t]), 3),
                      "in_state": bool(in_state[t])})

    actions = [e["action"] for e in trace if "action" in e]
    res = [e["residual"] for e in trace if "residual" in e]
    summary = {
        "ok": True, "npz": a.npz, "sfreq": sfreq, "sfreq_source": sfreq_src, "channels": n_ch,
        "epochs": int(T), "valid_ratio": round(float(valid.mean()), 4),
        "in_state_ratio": round(float(in_state[valid].mean()), 4),
        "action_hist": ({str(k): int(v) for k, v in
                         zip(*np.unique(actions, return_counts=True))}
                        if actions else {}),
        "residual_mean": round(float(np.mean(res)), 8) if res else None,
        "final_beat": round(br.beat, 3),
        "final_volume": round(br.volume, 4),
        "obs_dim": 6, "actions_dim": 4, "seed": 42,
    }

    os.makedirs(a.out, exist_ok=True)
    stem = os.path.splitext(os.path.basename(a.npz))[0]
    jp = os.path.join(a.out, f"{stem}_cadence_trace.json")
    with open(jp, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "trace": trace}, f,
                  ensure_ascii=False, indent=1)
    summary["trace_json"] = jp
    summary["brain"] = br.save(os.path.join(a.out, stem + "_bridge.brain"))
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
