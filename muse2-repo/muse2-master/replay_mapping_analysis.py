"""B3 离线回放：用已入库真机 EEG 测试 VR 映射逻辑（看板 ZG-010）.

为什么需要它:
    B1/B2（VR 端解析 Alpha/Theta、Shader 参数映射调校）的迭代若每次都靠
    佩戴真机，则每一轮都要法师戴头环、调接触、等连接（实测 20~37 秒），
    且状态不可复现。本工具用**已入库的合格 baseline** 回放，使映射参数
    的迭代不依赖头环在场，且每轮输入完全相同、结果可比。

严格复用线上口径（不自造第二套算法）:
    - 频段功率 / dB 换算 / 噪声判据 → report_generator.compute_band_power_chunk
    - 三态分类                        → report_generator.classify_state
    - 窗口长度 10 秒、最小 8 秒、节流 2 秒 → muse_local_server 的
      BP_EPOCH_SEC / BP_MIN_SAMPLES / compute_band_power 的 2.0s 节流
    - dB → 0..1 归一化与 Shader 参数     → vr_feedback.html:174-178, 252-263

数据边界:
    只读已入库 npz；不联网、不上传；不写入 Zen-EEG，不产生新 npz。
    npz 中的 eeg 已是既有采集层去直流 + 1-40Hz 带通后的数据
    （ble_receiver._feed → buffer.add_eeg），与 compute_band_power
    的输入完全同源，故直接喂入，不做二次滤波。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
CLOUD_DIR = HERE / "muse-cloud-server"
REPORT = HERE / "report"

# 与 muse_local_server.py:37-41 同样的路径设置，确保 import report_generator 成功
for p in (str(HERE), str(CLOUD_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import report_generator as rg                          # noqa: E402

# ---- 线上常量（照抄，不重新定义）----
SFREQ = 256.0
CHANNELS = ["TP9", "AF7", "AF8", "TP10"]
BP_EPOCH_SEC = 10                       # muse_local_server.py:235
BP_EPOCH_SAMPLES = int(SFREQ * BP_EPOCH_SEC)      # 2560
BP_MIN_SAMPLES = int(SFREQ * 8)                    # 2048，对齐 BP_MIN_EPOCH_SEC
BP_THROTTLE_SEC = 2.0                   # muse_local_server.py:666 的节流间隔
STEP_SAMPLES = int(SFREQ * BP_THROTTLE_SEC)        # 每帧推进 512 样本 = 2 秒

# ---- VR 页面的映射公式（vr_feedback.html:174-178）----
ALPHA_LO, ALPHA_SPAN = 5.0, 15.0        # (alpha_dB - 5)/15，注释称经验区间 5~20 dB
THETA_LO, THETA_SPAN = 2.0, 13.0        # (theta_dB - 2)/13，注释称 0~15 dB


def clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


def vr_normalize(alpha_db: float, theta_db: float) -> tuple[float, float]:
    """完全照抄 vr_feedback.html 的归一化，含其缺省兜底值（alpha 8 / theta 6）。"""
    a = clamp01(((alpha_db if alpha_db is not None else 8.0) - ALPHA_LO) / ALPHA_SPAN)
    th = clamp01(((theta_db if theta_db is not None else 6.0) - THETA_LO) / THETA_SPAN)
    return a, th


def shader_params(a: float, th: float) -> dict:
    """由归一化值算出各 Shader uniform 的实际取值（vr_feedback.html:252-263）。"""
    return {
        "water_uA": round(a, 4),                       # 水面涟漪振幅
        "water_uTh": round(th, 4),                     # 水面 theta 扰动
        "sky_uGlow": round(0.2 + 0.8 * a, 4),          # 天穹辉光
        "fog_density": round(0.020 + 0.030 * th, 5),   # 雾浓度
        "particle_opacity": round(0.35 + 0.55 * a, 4),  # 粒子不透明度
    }


def load_npz(path: Path) -> tuple[np.ndarray, dict]:
    d = np.load(path, allow_pickle=True)
    eeg = np.asarray(d["eeg"], dtype=np.float64)       # (samples, 4)
    ts = np.asarray(d["timestamps"], dtype=np.float64)
    meta = d["meta"].item() if d["meta"].shape == () else dict(d["meta"])
    return eeg, {"ts_len": int(len(ts)), "meta": meta}


def classify_with_linecode(alpha, theta, beta, delta, noisy) -> str:
    """照抄 muse_local_server.py:688-691 的状态判定顺序。"""
    tb = 10 ** ((theta - beta) / 10.0) if beta > -100 else 0.0
    if noisy:
        return "噪声 Noise"
    return rg.classify_state(alpha, theta, beta, delta, tb, None)


def replay(eeg: np.ndarray) -> list[dict]:
    """按线上节奏走窗：10 秒窗、每 2 秒推进一帧、取窗内四通道 dB 均值。"""
    frames: list[dict] = []
    n_total = eeg.shape[0]
    if n_total < BP_MIN_SAMPLES:
        return frames

    # 首帧需积累满 BP_MIN_SAMPLES；此后窗长固定 BP_EPOCH_SAMPLES（与线上一致：
    # epoch_samples = min(min_len, BP_EPOCH_SAMPLES)）
    idx = BP_MIN_SAMPLES
    while idx <= n_total:
        win = min(idx, BP_EPOCH_SAMPLES)
        chunk = eeg[idx - win: idx, :]                 # (win, 4)
        bp = rg.compute_band_power_chunk(chunk, SFREQ)
        if bp is None:
            idx += STEP_SAMPLES
            continue
        means = {b: float(np.mean(bp["db"][b])) for b in rg.BANDS}
        noisy = bool(np.all(bp["noise"]))
        state = classify_with_linecode(means["Alpha"], means["Theta"],
                                       means["Beta"], means["Delta"], noisy)
        a, th = vr_normalize(means["Alpha"], means["Theta"])
        frames.append({
            "t_sec": round(idx / SFREQ, 2),
            "win_sec": round(win / SFREQ, 2),
            "delta": round(means["Delta"], 3),
            "theta": round(means["Theta"], 3),
            "alpha": round(means["Alpha"], 3),
            "beta": round(means["Beta"], 3),
            "gamma": round(means["Gamma"], 3),
            "noise": noisy,
            "bg_rel": round(float(np.mean(bp["rel"]["Beta"] + bp["rel"]["Gamma"])), 4),
            "state": state,
            "a_norm": round(a, 4),
            "th_norm": round(th, 4),
            **shader_params(a, th),
            "a_saturated": bool(a <= 0.0 or a >= 1.0),
            "th_saturated": bool(th <= 0.0 or th >= 1.0),
        })
        idx += STEP_SAMPLES
    return frames


def summarize(frames: list[dict]) -> dict:
    def col(k):
        return np.asarray([f[k] for f in frames], dtype=float)

    alpha, theta = col("alpha"), col("theta")
    a_n, th_n = col("a_norm"), col("th_norm")
    states: dict[str, int] = {}
    for f in frames:
        states[f["state"]] = states.get(f["state"], 0) + 1

    return {
        "n_frames": len(frames),
        "coverage_sec": round(frames[-1]["t_sec"], 1) if frames else 0.0,
        "alpha_db": {"min": round(float(alpha.min()), 3),
                     "max": round(float(alpha.max()), 3),
                     "mean": round(float(alpha.mean()), 3),
                     "std": round(float(alpha.std()), 3),
                     "p5": round(float(np.percentile(alpha, 5)), 3),
                     "p95": round(float(np.percentile(alpha, 95)), 3)},
        "theta_db": {"min": round(float(theta.min()), 3),
                     "max": round(float(theta.max()), 3),
                     "mean": round(float(theta.mean()), 3),
                     "std": round(float(theta.std()), 3),
                     "p5": round(float(np.percentile(theta, 5)), 3),
                     "p95": round(float(np.percentile(theta, 95)), 3)},
        "a_norm": {"min": round(float(a_n.min()), 4),
                   "max": round(float(a_n.max()), 4),
                   "mean": round(float(a_n.mean()), 4),
                   "std": round(float(a_n.std()), 4),
                   "saturated_frames": int(np.sum(col("a_saturated"))),
                   "saturated_pct": round(float(np.mean(col("a_saturated")) * 100), 2)},
        "th_norm": {"min": round(float(th_n.min()), 4),
                    "max": round(float(th_n.max()), 4),
                    "mean": round(float(th_n.mean()), 4),
                    "std": round(float(th_n.std()), 4),
                    "saturated_frames": int(np.sum(col("th_saturated"))),
                    "saturated_pct": round(float(np.mean(col("th_saturated")) * 100), 2)},
        "state_distribution": states,
        "noise_frames": int(np.sum(col("noise"))),
        "shader_ranges": {
            "water_uA": [round(float(a_n.min()), 4), round(float(a_n.max()), 4)],
            "sky_uGlow": [round(0.2 + 0.8 * float(a_n.min()), 4),
                          round(0.2 + 0.8 * float(a_n.max()), 4)],
            "fog_density": [round(0.020 + 0.030 * float(th_n.min()), 5),
                            round(0.020 + 0.030 * float(th_n.max()), 5)],
            "particle_opacity": [round(0.35 + 0.55 * float(a_n.min()), 4),
                                 round(0.35 + 0.55 * float(a_n.max()), 4)],
        },
    }


def suggest_mapping(alpha: np.ndarray, theta: np.ndarray) -> dict:
    """按实测分位数给出映射区间建议，使动态范围用满 0..1 而不饱和。

    取 p5/p95 而非 min/max：避免个别伪迹帧把整条曲线压扁。
    """
    def bounds(x):
        return float(np.percentile(x, 5)), float(np.percentile(x, 95))

    a_lo, a_hi = bounds(alpha)
    t_lo, t_hi = bounds(theta)
    return {
        "alpha": {"lo": round(a_lo, 2), "span": round(max(a_hi - a_lo, 1e-6), 2),
                  "current": {"lo": ALPHA_LO, "span": ALPHA_SPAN}},
        "theta": {"lo": round(t_lo, 2), "span": round(max(t_hi - t_lo, 1e-6), 2),
                  "current": {"lo": THETA_LO, "span": THETA_SPAN}},
        "note": "span 取 p5→p95，使 90% 的帧落在 0..1 内且有实际动态范围",
    }


def evaluate_mapping(frames: list[dict], a_lo: float, a_span: float,
                     t_lo: float, t_span: float, label: str) -> dict:
    """用给定映射区间重算归一化与 Shader 参数，返回饱和度与动态范围。"""
    a = np.asarray([clamp01((f["alpha"] - a_lo) / a_span) for f in frames])
    th = np.asarray([clamp01((f["theta"] - t_lo) / t_span) for f in frames])
    a_sat = float(np.mean((a <= 0.0) | (a >= 1.0)) * 100)
    th_sat = float(np.mean((th <= 0.0) | (th >= 1.0)) * 100)
    return {
        "label": label,
        "alpha": {"lo": a_lo, "span": a_span},
        "theta": {"lo": t_lo, "span": t_span},
        "a_norm": {"min": round(float(a.min()), 4), "max": round(float(a.max()), 4),
                   "mean": round(float(a.mean()), 4), "std": round(float(a.std()), 4),
                   "saturated_pct": round(a_sat, 2)},
        "th_norm": {"min": round(float(th.min()), 4), "max": round(float(th.max()), 4),
                    "mean": round(float(th.mean()), 4), "std": round(float(th.std()), 4),
                    "saturated_pct": round(th_sat, 2)},
        "shader_ranges": {
            "water_uA": [round(float(a.min()), 4), round(float(a.max()), 4)],
            "sky_uGlow": [round(0.2 + 0.8 * float(a.min()), 4),
                          round(0.2 + 0.8 * float(a.max()), 4)],
            "fog_density": [round(0.020 + 0.030 * float(th.min()), 5),
                            round(0.020 + 0.030 * float(th.max()), 5)],
            "particle_opacity": [round(0.35 + 0.55 * float(a.min()), 4),
                                 round(0.35 + 0.55 * float(a.max()), 4)],
        },
    }


def main() -> int:
    target = sys.argv[1] if len(sys.argv) > 1 else str(
        REPORT / "local_20260906_011204.npz")
    npz = Path(target)
    if not npz.is_absolute():
        npz = REPORT / npz
    if not npz.exists():
        print(f"数据文件不存在: {npz}")
        return 1

    eeg, info = load_npz(npz)
    meta = info["meta"]
    print("=" * 78)
    print("B3 离线回放 · VR 映射逻辑测试（ZG-010）")
    print("=" * 78)
    print(f"数据文件    : {npz.name}")
    print(f"形状        : {eeg.shape}  (samples, channels)")
    print(f"通道        : {meta.get('channels')}")
    print(f"标称采样率  : {meta.get('sfreq')} Hz")
    print(f"时长        : {meta.get('duration'):.1f} 秒"
          if meta.get("duration") else f"时长        : {eeg.shape[0]/SFREQ:.1f} 秒")
    print(f"质检/接触   : contact_quality={meta.get('contact_quality')!r} "
          f"scene={meta.get('scene')!r} session_type={meta.get('session_type')!r} "
          f"participant={meta.get('participant')!r}")
    print(f"\n回放节奏    : 窗 {BP_EPOCH_SEC} 秒 / 推进 {BP_THROTTLE_SEC} 秒"
          f"（= 线上 compute_band_power 节流口径）")
    print(f"算法口径    : report_generator.compute_band_power_chunk + classify_state")
    print(f"VR 映射     : a=(alpha-{ALPHA_LO})/{ALPHA_SPAN}, "
          f"th=(theta-{THETA_LO})/{THETA_SPAN}（vr_feedback.html:174-178）")

    frames = replay(eeg)
    if not frames:
        print("\n数据不足，无法回放。")
        return 2

    s = summarize(frames)
    print("\n" + "-" * 78)
    print(f"回放结果：{s['n_frames']} 帧，覆盖 {s['coverage_sec']} 秒")
    print("-" * 78)
    print(f"  Alpha dB  min/max = {s['alpha_db']['min']}/{s['alpha_db']['max']}"
          f"   mean={s['alpha_db']['mean']}  std={s['alpha_db']['std']}"
          f"   p5/p95={s['alpha_db']['p5']}/{s['alpha_db']['p95']}")
    print(f"  Theta dB  min/max = {s['theta_db']['min']}/{s['theta_db']['max']}"
          f"   mean={s['theta_db']['mean']}  std={s['theta_db']['std']}"
          f"   p5/p95={s['theta_db']['p5']}/{s['theta_db']['p95']}")
    print(f"\n  归一化 a   范围 [{s['a_norm']['min']}, {s['a_norm']['max']}]"
          f"  mean={s['a_norm']['mean']}  std={s['a_norm']['std']}"
          f"  饱和帧 {s['a_norm']['saturated_frames']}"
          f"（{s['a_norm']['saturated_pct']}%）")
    print(f"  归一化 th  范围 [{s['th_norm']['min']}, {s['th_norm']['max']}]"
          f"  mean={s['th_norm']['mean']}  std={s['th_norm']['std']}"
          f"  饱和帧 {s['th_norm']['saturated_frames']}"
          f"（{s['th_norm']['saturated_pct']}%）")
    print(f"\n  状态分布  : {s['state_distribution']}")
    print(f"  噪声帧    : {s['noise_frames']} / {s['n_frames']}")
    print(f"\n  Shader 实际取值范围:")
    for k, v in s["shader_ranges"].items():
        print(f"    {k:<20} {v[0]} → {v[1]}")

    sug = suggest_mapping(np.asarray([f["alpha"] for f in frames]),
                          np.asarray([f["theta"] for f in frames]))
    print("\n" + "-" * 78)
    print("映射区间对比：现行 vs 建议（同一批帧实测）")
    print("-" * 78)
    evals = [
        evaluate_mapping(frames, ALPHA_LO, ALPHA_SPAN, THETA_LO, THETA_SPAN,
                         "现行（vr_feedback.html:174-178）"),
        evaluate_mapping(frames, sug["alpha"]["lo"], sug["alpha"]["span"],
                         sug["theta"]["lo"], sug["theta"]["span"],
                         "建议（本次 p5/p95）"),
    ]
    for e in evals:
        print(f"\n  【{e['label']}】")
        print(f"    alpha 区间 ({e['alpha']['lo']}, span {e['alpha']['span']})   "
              f"theta 区间 ({e['theta']['lo']}, span {e['theta']['span']})")
        print(f"    a  归一化 [{e['a_norm']['min']}, {e['a_norm']['max']}] "
              f"std={e['a_norm']['std']}  饱和 {e['a_norm']['saturated_pct']}%")
        print(f"    th 归一化 [{e['th_norm']['min']}, {e['th_norm']['max']}] "
              f"std={e['th_norm']['std']}  饱和 {e['th_norm']['saturated_pct']}%")
        print(f"    sky_uGlow {e['shader_ranges']['sky_uGlow']}   "
              f"fog {e['shader_ranges']['fog_density']}   "
              f"粒子 {e['shader_ranges']['particle_opacity']}")
    cur, new = evals[0], evals[1]
    gain_a = new["a_norm"]["std"] / cur["a_norm"]["std"] if cur["a_norm"]["std"] else 0
    gain_t = new["th_norm"]["std"] / cur["th_norm"]["std"] if cur["th_norm"]["std"] else 0
    print(f"\n  动态范围提升: a 的 std ×{gain_a:.2f}，th 的 std ×{gain_t:.2f}")
    print(f"  饱和帧变化  : a {cur['a_norm']['saturated_pct']}% → "
          f"{new['a_norm']['saturated_pct']}%；th {cur['th_norm']['saturated_pct']}% → "
          f"{new['th_norm']['saturated_pct']}%")
    print(f"  说明: {sug['note']}")

    # ---- 首尾各 6 帧明细，便于人工核对 ----
    print("\n" + "-" * 78)
    print("帧明细（首 6 帧 + 末 6 帧）")
    print("-" * 78)
    hdr = (f"{'t_sec':>7}{'alpha':>9}{'theta':>9}{'beta':>9}"
           f"{'a':>7}{'th':>7}{'uGlow':>8}  state")
    print(hdr)
    show = frames[:6] + ([{"t_sec": "..."}] if len(frames) > 12 else []) + frames[-6:]
    for f in show:
        if "alpha" not in f:
            print(f"{'...':>7}")
            continue
        print(f"{f['t_sec']:>7}{f['alpha']:>9.2f}{f['theta']:>9.2f}"
              f"{f['beta']:>9.2f}{f['a_norm']:>7.3f}{f['th_norm']:>7.3f}"
              f"{f['sky_uGlow']:>8.3f}  {f['state']}")

    # ---- 落盘 ----
    out = REPORT / f"b3_replay_{npz.stem}.json"
    out.write_text(json.dumps({
        "source_npz": npz.name, "meta": {k: str(v) for k, v in meta.items()},
        "cadence": {"window_sec": BP_EPOCH_SEC, "step_sec": BP_THROTTLE_SEC,
                    "min_samples": BP_MIN_SAMPLES},
        "algorithm": "report_generator.compute_band_power_chunk + classify_state",
        "vr_mapping": {"alpha": {"lo": ALPHA_LO, "span": ALPHA_SPAN},
                       "theta": {"lo": THETA_LO, "span": THETA_SPAN}},
        "summary": s, "suggested_mapping": sug,
        "mapping_comparison": evals, "frames": frames,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n完整结果已存: {out}")
    print("（只读已入库 npz，未产生新数据、未写入 Zen-EEG）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
