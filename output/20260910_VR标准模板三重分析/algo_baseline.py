"""V2 步骤1a：个人基线自适应算法 —— Python 验证（先验证后移植，守红线8）

设计（按对齐方案 H-A/H-B）：
  1. 基线期：会话前 BASELINE_S 秒的 rel_alpha 中位数 = 个人基线 b0
  2. 度量：当前长时窗（WIN_S 秒）rel_alpha 中位数 m，z = (m - b0) / MAD_scale
  3. 归一到 0..1：S = clamp01(0.5 + z * GAIN)，0.5 = 中性（等于个人基线）
  4. 平滑：EMA，时间常数 τ ≥ 10s（源数据 2s 周期的 5 倍）

为何用稳健统计而非收窄量程：
  q1q3 失败根因是 σ(Δrel_alpha)≈0.0116 ≈ 整个量程 0.0119，噪声淹没信号。
  长时窗中位数把单 epoch 抖动平均掉，MAD 归一让量程随个人波动自适应，
  从源头降噪而非事后压噪。

验收（对齐方案 H-A/H-B）：
  触顶占比 <5%、|ΔS.a| p90 <0.05、中位落 0.3-0.7、IQR >0.2
"""
import os, sys, json
import numpy as np

RG_DIR = r"C:\Users\tiand\OneDrive\zhiguanAI\muse2-repo\muse2-master\muse-cloud-server"
sys.path.insert(0, RG_DIR)
import report_generator as rg

REPORT_DIR = r"C:\Users\tiand\OneDrive\zhiguanAI\muse2-repo\muse2-master\report"
OUT = r"C:\Users\tiand\OneDrive\zhiguanAI\output\20260910_VR标准模板三重分析"
BANDS = rg.BANDS
EPOCH_S, EPOCH_STEP = rg.EPOCH_SECONDS, rg.EPOCH_STEP   # 10s 窗、5s 步
TICK_SEC = 0.25                                          # console_server TICK_SEC

SESSIONS = [
    ("local_20260910_121639.npz", "09-10会话A 22min"),
    ("local_20260910_130105.npz", "09-10会话B 42min"),
    ("local_20260911_094407.npz", "09-11实测 43min"),
]

# 待调参数
BASELINE_S = 120.0     # 基线期 2 分钟（复用 closedloop_controller 范式）
WIN_S = 60.0           # 长时窗 60 秒
TAU_S = 12.0           # EMA 时间常数（裁定6默认值）
GAIN = 1.0             # z→S 增益，0.5+z*GAIN


def rel_alpha_series(name):
    """按项目口径切 epoch，返回 (rel_alpha 序列, 每 epoch 起始秒, 总分钟)。"""
    with np.load(os.path.join(REPORT_DIR, name), allow_pickle=True) as z:
        meta = z["meta"].item() if "meta" in z.files else {}
        eeg = np.asarray(z["eeg"], dtype=np.float64)
        sfreq = float(meta.get("sfreq") or rg.SFREQ)
    win, step = int(EPOCH_S * sfreq), int(EPOCH_STEP * sfreq)
    ras, ts = [], []
    for s in range(0, max(1, eeg.shape[0] - win + 1), step):
        bp = rg.compute_band_power_chunk(eeg[s:s + win], sfreq)
        if bp is None:
            continue
        db = {b: float(np.mean(np.asarray(bp["db"][b], dtype=np.float64))) for b in BANDS}
        lin = {b: 10.0 ** (db[b] / 10.0) for b in BANDS}
        tot = sum(lin.values())
        if tot > 0:
            ras.append(lin["Alpha"] / tot)
            ts.append(s / sfreq)
    return np.asarray(ras), np.asarray(ts), eeg.shape[0] / sfreq / 60


def robust_scale(x):
    """MAD 稳健尺度（比 std 抗离群），带下限防除零与过灵敏。"""
    med = np.median(x)
    mad = np.median(np.abs(x - med))
    scale = 1.4826 * mad           # MAD→正态等价 σ
    return max(scale, 1e-4)


def run_algo(ra, ts, gain=GAIN, tau=TAU_S, win_s=WIN_S, base_s=BASELINE_S):
    """仿真前端逐 tick 运行：返回 tick 级 S.a 序列。

    前端每 0.25s 收一次 tick，但频段功率每 2s 才重算，
    故 tick 级 S.a 由"最近可得 epoch 的长时窗统计"驱动，再做 EMA。
    """
    # 基线：前 base_s 秒内所有 epoch 的 rel_alpha 中位数
    base_mask = ts < base_s
    if base_mask.sum() < 3:
        base_mask = np.zeros_like(ts, dtype=bool)
        base_mask[:3] = True
    b0 = float(np.median(ra[base_mask]))
    scale = robust_scale(ra[base_mask])

    # 长时窗中位数序列（对每个 epoch，取其前 win_s 秒内 epoch 的中位数）
    n = len(ra)
    longmed = np.empty(n)
    for i in range(n):
        j0 = max(0, np.searchsorted(ts, ts[i] - win_s))
        longmed[i] = np.median(ra[j0:i + 1])

    # 基线期内输出中性 0.5（未锁定基线前不呈现状态，守判语009不当场评分）
    z = np.where(ts < base_s, 0.0, (longmed - b0) / scale)
    s_raw = np.clip(0.5 + z * gain, 0.0, 1.0)

    # 展到 tick 级（每 epoch 覆盖 EPOCH_STEP/TICK_SEC 个 tick）
    ticks_per_epoch = int(round(EPOCH_STEP / TICK_SEC))
    s_tick = np.repeat(s_raw, ticks_per_epoch)

    # EMA 平滑：alpha 由 τ 与 tick 间隔决定
    a_ema = TICK_SEC / tau
    sm = np.empty_like(s_tick)
    sm[0] = s_tick[0]
    for i in range(1, len(s_tick)):
        sm[i] = sm[i - 1] + (s_tick[i] - sm[i - 1]) * a_ema
    return sm, s_tick, {"b0": b0, "scale": scale, "gain": gain, "tau": tau,
                        "win_s": win_s, "base_s": base_s}


def evaluate(sm, label, params):
    """按验收标准评估，返回是否达标。"""
    post = sm[int(params["base_s"] / TICK_SEC):]      # 只评基线期之后
    if post.size < 10:
        print(f"\n[{label}] 基线期后数据太少，跳过")
        return None
    d = np.abs(np.diff(post))
    top = float(np.mean(post >= 0.999))
    bot = float(np.mean(post <= 0.001))
    med = float(np.median(post))
    q1, q3 = float(np.percentile(post, 25)), float(np.percentile(post, 75))
    p90 = float(np.percentile(d, 90))
    checks = {
        "触顶<5%": top < 0.05,
        "触底<5%": bot < 0.05,
        "|Δ|p90<0.05": p90 < 0.05,
        "中位0.3-0.7": 0.3 <= med <= 0.7,
        "IQR>0.2": (q3 - q1) > 0.2,
    }
    ok = all(checks.values())
    print(f"\n[{label}] 基线 rel_alpha={params['b0']:.4f} MAD尺度={params['scale']:.5f}")
    print(f"  S.a 中位 {med:.3f} [IQR {q1:.3f}~{q3:.3f}]  值域[{post.min():.2f},{post.max():.2f}]")
    print(f"  触顶 {top*100:.1f}%  触底 {bot*100:.1f}%  |Δ/tick| p90 {p90:.4f}")
    print(f"  验收: " + "  ".join(f"{'✅' if v else '❌'}{k}" for k, v in checks.items()))
    print(f"  → {'✅ 达标' if ok else '❌ 未达标'}")
    return {"label": label, "median": round(med, 3), "iqr": [round(q1, 3), round(q3, 3)],
            "saturate_top": round(top, 4), "saturate_bot": round(bot, 4),
            "jump_p90": round(p90, 4), "checks": checks, "pass": ok,
            "params": {k: round(v, 5) if isinstance(v, float) else v for k, v in params.items()}}


def main():
    print("=" * 78)
    print("V2 步骤1a：个人基线自适应算法验证（先验证后移植）")
    print(f"参数：基线期 {BASELINE_S:.0f}s / 长时窗 {WIN_S:.0f}s / τ={TAU_S:.0f}s / GAIN={GAIN}")
    print("=" * 78)
    results = {}
    for name, label in SESSIONS:
        p = os.path.join(REPORT_DIR, name)
        if not os.path.exists(p):
            print(f"\n[{label}] 文件不存在，跳过")
            continue
        ra, ts, mins = rel_alpha_series(name)
        if ra.size < 8:
            print(f"\n[{label}] epoch 太少({ra.size})，跳过")
            continue
        print(f"\n[{label}] {mins:.0f}分钟 {ra.size} epoch  rel_alpha中位={np.median(ra):.4f} σ(Δ)={np.std(np.diff(ra)):.5f}")
        sm, s_tick, params = run_algo(ra, ts)
        r = evaluate(sm, label, params)
        if r:
            # 对比：未平滑的 tick 级抖动
            d_raw = np.abs(np.diff(s_tick[int(BASELINE_S / TICK_SEC):]))
            r["jump_p90_unsmoothed"] = round(float(np.percentile(d_raw, 90)), 4)
            results[label] = r

    n_pass = sum(1 for r in results.values() if r["pass"])
    print("\n" + "=" * 78)
    print(f"汇总：{n_pass}/{len(results)} 段达标")
    if n_pass == len(results) and results:
        print("→ 算法验证通过，可移植 JS（步骤1b）")
    else:
        print("→ 未全部达标，须调参后重验（禁止直接移植）")
    print("=" * 78)

    with open(os.path.join(OUT, "V2算法验证.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    print("已存 V2算法验证.json")


if __name__ == "__main__":
    main()
