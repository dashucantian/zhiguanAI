"""V2 步骤1a-2：诊断居中失败根因 + 参数扫描（先诊断后调参，不猜）

步骤1a 首验结果：抖动治理成功（|Δ|p90 降两个数量级），但居中失败：
  会话A 中位0.078 触底18% / 会话B 中位0.000 触底69.5% / 09-11 中位1.000 触顶51%

首验根因假设：基线期（前2分钟）rel_alpha 不代表个人常态。
  会话B b0=0.0543 而全场中位 0.0327 → 基线偏高 → 整场被判"低于基线"

本脚本先做事实核查（rel_alpha 有无单调趋势/基线期是否异常），
再扫描 base×scale×gain 参数空间找达标组合。
"""
import os, sys, json, itertools
import numpy as np

RG_DIR = r"C:\Users\tiand\OneDrive\zhiguanAI\muse2-repo\muse2-master\muse-cloud-server"
sys.path.insert(0, RG_DIR)
import report_generator as rg

REPORT_DIR = r"C:\Users\tiand\OneDrive\zhiguanAI\muse2-repo\muse2-master\report"
OUT = r"C:\Users\tiand\OneDrive\zhiguanAI\output\20260910_VR标准模板三重分析"
CACHE = os.path.join(OUT, "_relalpha_cache.npz")
BANDS = rg.BANDS
EPOCH_S, EPOCH_STEP = rg.EPOCH_SECONDS, rg.EPOCH_STEP
TICK_SEC = 0.25
TPE = int(round(EPOCH_STEP / TICK_SEC))          # ticks per epoch

SESSIONS = [
    ("local_20260910_121639.npz", "A_0910_22min"),
    ("local_20260910_130105.npz", "B_0910_42min"),
    ("local_20260911_094407.npz", "C_0911_43min"),
]


def rel_alpha_series(name):
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
            ras.append(lin["Alpha"] / tot); ts.append(s / sfreq)
    return np.asarray(ras), np.asarray(ts)


def load_all():
    """缓存 rel_alpha 序列，避免重复 Welch（扫描要跑很多组）。"""
    if os.path.exists(CACHE):
        with np.load(CACHE, allow_pickle=True) as c:
            return {tag: (c[tag + "_ra"], c[tag + "_ts"]) for _, tag in SESSIONS
                    if tag + "_ra" in c.files}
    data = {}
    for name, tag in SESSIONS:
        p = os.path.join(REPORT_DIR, name)
        if not os.path.exists(p):
            continue
        ra, ts = rel_alpha_series(name)
        data[tag] = (ra, ts)
        print(f"  载入 {tag}: {ra.size} epoch, {ts[-1]/60:.1f}分钟")
    flat = {}
    for tag, (ra, ts) in data.items():
        flat[tag + "_ra"] = ra; flat[tag + "_ts"] = ts
    np.savez_compressed(CACHE, **flat)
    print("  已缓存 _relalpha_cache.npz")
    return data


def mad(x):
    if x.size < 3:
        return 1e-4
    return max(1.4826 * float(np.median(np.abs(x - np.median(x)))), 1e-4)


def rolling_med(x, k):
    """向量化滚动中位数（窗 k 个 epoch，因果，只用过去）。"""
    n = len(x); out = np.empty(n)
    for i in range(n):
        j0 = max(0, i - k + 1)
        out[i] = np.median(x[j0:i + 1])
    return out


def rolling_mad(x, k):
    n = len(x); out = np.empty(n)
    for i in range(n):
        j0 = max(0, i - k + 1)
        out[i] = mad(x[j0:i + 1])
    return out


def ema_tick(s_raw, tau):
    s_tick = np.repeat(s_raw, TPE)
    a = TICK_SEC / tau
    sm = np.empty_like(s_tick); sm[0] = s_tick[0]
    for i in range(1, len(s_tick)):
        sm[i] = sm[i - 1] + (s_tick[i] - sm[i - 1]) * a
    return sm


def metrics(sm, skip_s):
    post = sm[int(skip_s / TICK_SEC):]
    if post.size < 20:
        return None
    d = np.abs(np.diff(post))
    return {
        "median": float(np.median(post)),
        "q1": float(np.percentile(post, 25)), "q3": float(np.percentile(post, 75)),
        "top": float(np.mean(post >= 0.999)), "bot": float(np.mean(post <= 0.001)),
        "p90": float(np.percentile(d, 90)),
    }


def passes(m):
    return (m["top"] < 0.05 and m["bot"] < 0.05 and m["p90"] < 0.05
            and 0.3 <= m["median"] <= 0.7 and (m["q3"] - m["q1"]) > 0.2)


# ══════════ 第一部分：事实核查 ══════════
print("=" * 80)
print("第一部分 · 事实核查：rel_alpha 有无单调趋势？基线期是否异常？")
print("=" * 80)
facts = {}
for tag, (ra, ts) in load_all().items():
    total = float(ts[-1])
    seg_n = 6
    print(f"\n[{tag}] 全长 {total/60:.1f}分钟 {ra.size} epoch")
    chunks = np.array_split(ra, seg_n)
    meds = [float(np.median(c)) for c in chunks]
    print("  六等分中位数: " + " → ".join(f"{m:.4f}" for m in meds))
    drift = (meds[-1] - meds[0]) / max(meds[0], 1e-6)
    # 趋势显著性：Spearman 简化版（用 epoch 序号与 rel_alpha 的相关）
    rho = float(np.corrcoef(np.arange(ra.size), ra)[0, 1])
    b2 = float(np.median(ra[ts < 120])) if (ts < 120).sum() >= 3 else float(np.median(ra[:3]))
    b5 = float(np.median(ra[ts < 300])) if (ts < 300).sum() >= 3 else float(np.median(ra[:6]))
    full = float(np.median(ra))
    print(f"  首末漂移 {drift*100:+.1f}%   线性相关 r={rho:+.3f}   σ(Δ)={np.std(np.diff(ra)):.5f}")
    print(f"  基线期: 前2分钟={b2:.4f}  前5分钟={b5:.4f}  全场={full:.4f}")
    print(f"  基线偏差: 前2分钟 {(b2-full)/full*100:+.1f}%  前5分钟 {(b5-full)/full*100:+.1f}%")
    print(f"  全场 MAD={mad(ra):.5f}  前2分钟 MAD={mad(ra[ts<120]) if (ts<120).sum()>=3 else float('nan'):.5f}")
    facts[tag] = {"total_min": round(total / 60, 1), "n_epoch": int(ra.size),
                  "seg_medians": [round(m, 5) for m in meds], "drift_pct": round(drift * 100, 1),
                  "linear_r": round(rho, 3), "sigma_delta": round(float(np.std(np.diff(ra))), 5),
                  "b_2min": round(b2, 5), "b_5min": round(b5, 5), "full_median": round(full, 5),
                  "b2_bias_pct": round((b2 - full) / full * 100, 1),
                  "b5_bias_pct": round((b5 - full) / full * 100, 1),
                  "mad_full": round(mad(ra), 5)}

# ══════════ 第二部分：参数扫描 ══════════
print("\n" + "=" * 80)
print("第二部分 · 参数扫描：base模式 × scale模式 × gain × τ")
print("=" * 80)

data = load_all()
# 扫描空间
BASE_MODES = ["fix120", "fix300", "fix600", "roll300", "roll600", "roll900"]
SCALE_MODES = ["base_mad", "full_mad", "roll_mad600"]
GAINS = [0.5, 1.0, 2.0, 3.0]
TAUS = [12.0]
WIN_EPOCHS = int(round(60 / EPOCH_STEP))      # 60秒短窗 = 12 epoch

results = []
for tag, (ra, ts) in data.items():
    n = len(ra)
    short = rolling_med(ra, WIN_EPOCHS)        # 60秒短窗中位（当前状态）
    # 预计算各基线模式
    bases = {}
    for bm in BASE_MODES:
        if bm.startswith("fix"):
            sec = int(bm[3:])
            k = max(3, int(sec / EPOCH_STEP))
            b = float(np.median(ra[:k]))
            bases[bm] = np.full(n, b)
        else:
            sec = int(bm[4:])
            k = max(6, int(sec / EPOCH_STEP))
            bases[bm] = rolling_med(ra, k)
    scales = {}
    for sm_ in SCALE_MODES:
        if sm_ == "base_mad":
            k = max(3, int(120 / EPOCH_STEP))
            scales[sm_] = np.full(n, mad(ra[:k]))
        elif sm_ == "full_mad":
            scales[sm_] = np.full(n, mad(ra))     # oracle：不可实时，仅作参考上界
        else:
            k = max(6, int(600 / EPOCH_STEP))
            scales[sm_] = rolling_mad(ra, k)

    for bm, smode, g, tau in itertools.product(BASE_MODES, SCALE_MODES, GAINS, TAUS):
        b, sc = bases[bm], scales[smode]
        skip = 120.0 if bm.startswith("fix") else max(300.0, int(bm[4:]))
        z = np.where(ts < skip, 0.0, (short - b) / sc)
        s_raw = np.clip(0.5 + z * g, 0.0, 1.0)
        sm = ema_tick(s_raw, tau)
        m = metrics(sm, skip)
        if m is None:
            continue
        results.append({"tag": tag, "base": bm, "scale": smode, "gain": g, "tau": tau,
                        "skip_s": skip, **{k: round(v, 4) for k, v in m.items()},
                        "pass": passes(m)})

# 汇总：找三段全达标的组合
by_combo = {}
for r in results:
    key = (r["base"], r["scale"], r["gain"], r["tau"])
    by_combo.setdefault(key, []).append(r)

full_pass = []
for key, rs in by_combo.items():
    if len(rs) == len(data) and all(x["pass"] for x in rs):
        # 评分：居中越好、IQR 越大越优
        score = np.mean([abs(x["median"] - 0.5) for x in rs]) - np.mean([x["q3"] - x["q1"] for x in rs])
        full_pass.append((score, key, rs))

full_pass.sort(key=lambda x: x[0])
print(f"\n扫描组合数 {len(by_combo)}，三段全达标 {len(full_pass)} 组")
if full_pass:
    print("\n--- 最优 8 组（按居中偏差小 + IQR 大排序）---")
    for score, key, rs in full_pass[:8]:
        b, sc, g, tau = key
        print(f"\n  base={b} scale={sc} gain={g} τ={tau:.0f}s  (score={score:.3f})")
        for x in rs:
            print(f"    {x['tag']}: 中位{x['median']:.3f} IQR[{x['q1']:.3f},{x['q3']:.3f}] "
                  f"顶{x['top']*100:.1f}% 底{x['bot']*100:.1f}% |Δ|p90 {x['p90']:.4f}")
else:
    print("\n❌ 无组合三段全达标 —— 须修订 H-A 假设形式（记录为预测误差）")
    print("\n--- 各段单独最优（诊断哪段最难）---")
    for tag in data:
        rs = [r for r in results if r["tag"] == tag]
        good = [r for r in rs if r["pass"]]
        print(f"\n  {tag}: 达标 {len(good)}/{len(rs)} 组")
        best = sorted(rs, key=lambda r: (not r["pass"], abs(r["median"] - 0.5), -(r["q3"] - r["q1"])))[:3]
        for r in best:
            print(f"    base={r['base']} scale={r['scale']} gain={r['gain']}: "
                  f"中位{r['median']:.3f} IQR[{r['q1']:.3f},{r['q3']:.3f}] "
                  f"顶{r['top']*100:.1f}% 底{r['bot']*100:.1f}% {'✅' if r['pass'] else '❌'}")

with open(os.path.join(OUT, "V2算法扫描.json"), "w", encoding="utf-8") as f:
    json.dump({"facts": facts, "n_combos": len(by_combo), "n_full_pass": len(full_pass),
               "full_pass_top": [{"combo": list(map(str, k)), "rows": rs} for _, k, rs in full_pass[:10]],
               "all_results_sample": results[:200]}, f, ensure_ascii=False, indent=2, default=str)
print("\n已存 V2算法扫描.json")
