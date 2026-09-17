"""V2 步骤1a-2（修订版）：套用既有噪声门 + 修订 H-A 假设形式

═══ 步骤1a 首验的预测误差（须登记，按方法论准则2）═══
首验结果：抖动治理成功（|Δ|p90 0.473-0.680 → 0.0008-0.0029，降两个数量级，H-B 成立）
          但居中失败：A 中位0.078触底18% / B 中位0.000触底69.5% / C 中位1.000触顶51%

事实核查（diag 实测，非推测）：
  A: 六等分 0.0467→0.0365，单调下降 -21.9%（r=-0.357）→ 固定基线必然持续触底
  B: 开场2分钟 MAD=0.03514 是全场 0.00672 的 5.2 倍 → 伪迹污染致 b0 偏高 66.3%
  C: 六等分 0.0314→0.0538→0.0355 倒U型（中段冲高）→ 固定基线必然在峰值触顶

═══ 两处方法论错误（同源：未复用既有资产）═══
错误1：未套项目既有噪声门 NOISE_BG_RATIO（report_generator），三重分析时用了、本次漏了
       → 会话B 开场伪迹本应被剔除，却进了基线计算
错误2：H-A 假设"固定基线"形式被证伪 —— 三段数据呈下降/平稳/倒U三形态，
       单一固定基线无法同时适配

═══ H-A 修订（假设轻持，由预测误差驱动）═══
H-A′：状态标准 = 因果滚动分位数（causal running quantile）
  当前长时窗值在"本次会话已见历史"中的分位排名 → S.a ∈ [0,1]
  性质：中位≈0.5 由构造保证；量程随个人波动自适应；无固定标定 → 无触顶/触底
  叠加噪声门：先用既有 NOISE_BG_RATIO 剔除伪迹 epoch，再算分位

⚠️ 诚实声明（损失投影，方法论准则5）：
  滚动分位数使"中位0.3-0.7""IQR>0.2"两项验收由构造必然满足 → 这两项检验失去判别力。
  真正有效的验收只剩：抖动预算（|Δ|p90<0.05）、触顶触底占比、以及法师实测体感。
  不得因数值全绿即宣称"达标"。
"""
import os, sys, json, itertools
import numpy as np

RG_DIR = r"C:\Users\tiand\OneDrive\zhiguanAI\muse2-repo\muse2-master\muse-cloud-server"
sys.path.insert(0, RG_DIR)
import report_generator as rg

REPORT_DIR = r"C:\Users\tiand\OneDrive\zhiguanAI\muse2-repo\muse2-master\report"
OUT = r"C:\Users\tiand\OneDrive\zhiguanAI\output\20260910_VR标准模板三重分析"
CACHE = os.path.join(OUT, "_relalpha_cache2.npz")
BANDS = rg.BANDS
EPOCH_S, EPOCH_STEP = rg.EPOCH_SECONDS, rg.EPOCH_STEP
NOISE_BG_RATIO = rg.NOISE_BG_RATIO          # 既有噪声门，复用不自建
TICK_SEC = 0.25
TPE = int(round(EPOCH_STEP / TICK_SEC))

SESSIONS = [
    ("local_20260910_121639.npz", "A_0910_22min"),
    ("local_20260910_130105.npz", "B_0910_42min"),
    ("local_20260911_094407.npz", "C_0911_43min"),
]


def series_with_noise(name):
    """按项目口径切 epoch，返回 rel_alpha + 既有噪声门标志。"""
    with np.load(os.path.join(REPORT_DIR, name), allow_pickle=True) as z:
        meta = z["meta"].item() if "meta" in z.files else {}
        eeg = np.asarray(z["eeg"], dtype=np.float64)
        sfreq = float(meta.get("sfreq") or rg.SFREQ)
    win, step = int(EPOCH_S * sfreq), int(EPOCH_STEP * sfreq)
    ras, ts, noise = [], [], []
    for s in range(0, max(1, eeg.shape[0] - win + 1), step):
        bp = rg.compute_band_power_chunk(eeg[s:s + win], sfreq)
        if bp is None:
            continue
        db = {b: float(np.mean(np.asarray(bp["db"][b], dtype=np.float64))) for b in BANDS}
        lin = {b: 10.0 ** (db[b] / 10.0) for b in BANDS}
        tot = sum(lin.values())
        if tot <= 0:
            continue
        ras.append(lin["Alpha"] / tot)
        ts.append(s / sfreq)
        bg = (lin["Beta"] + lin["Gamma"]) / tot
        noise.append(bg > NOISE_BG_RATIO)
    return np.asarray(ras), np.asarray(ts), np.asarray(noise, dtype=bool)


def load_all():
    if os.path.exists(CACHE):
        with np.load(CACHE, allow_pickle=True) as c:
            return {tag: (c[tag + "_ra"], c[tag + "_ts"], c[tag + "_nz"])
                    for _, tag in SESSIONS if tag + "_ra" in c.files}
    data = {}
    flat = {}
    for name, tag in SESSIONS:
        p = os.path.join(REPORT_DIR, name)
        if not os.path.exists(p):
            continue
        ra, ts, nz = series_with_noise(name)
        data[tag] = (ra, ts, nz)
        flat[tag + "_ra"] = ra; flat[tag + "_ts"] = ts; flat[tag + "_nz"] = nz
        print(f"  载入 {tag}: {ra.size} epoch, 噪声门剔除 {nz.sum()} ({nz.mean()*100:.1f}%)")
    np.savez_compressed(CACHE, **flat)
    print("  已缓存 _relalpha_cache2.npz（含噪声标志）")
    return data


def mad(x):
    if x.size < 3:
        return 1e-4
    return max(1.4826 * float(np.median(np.abs(x - np.median(x)))), 1e-4)


def rolling_med_clean(ra, nz, k):
    """滚动中位数，窗内剔除噪声 epoch（因果，只用过去）。"""
    n = len(ra); out = np.empty(n); valid = np.ones(n, bool)
    for i in range(n):
        j0 = max(0, i - k + 1)
        seg = ra[j0:i + 1]; segz = nz[j0:i + 1]
        good = seg[~segz]
        if good.size < 3:
            good = seg                       # 窗内全是噪声则退回全窗（避免 NaN）
            valid[i] = False
        out[i] = np.median(good)
    return out, valid


def clean_mad(ra, nz):
    good = ra[~nz]
    return mad(good) if good.size >= 3 else mad(ra)


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
    return {"median": float(np.median(post)),
            "q1": float(np.percentile(post, 25)), "q3": float(np.percentile(post, 75)),
            "top": float(np.mean(post >= 0.999)), "bot": float(np.mean(post <= 0.001)),
            "p90": float(np.percentile(d, 90))}


def hard_checks(m):
    """仍有判别力的验收项（分位数族下 median/IQR 由构造满足，不计入）"""
    return {"触顶<5%": m["top"] < 0.05, "触底<5%": m["bot"] < 0.05, "|Δ|p90<0.05": m["p90"] < 0.05}


# ══════════ 算法族 ══════════
def algo_runq(ra, nz, ts, win_ep, min_hist, tau):
    """H-A′ 因果滚动分位数：当前短窗值在已见历史中的分位排名。"""
    n = len(ra)
    short, _ = rolling_med_clean(ra, nz, win_ep)
    s_raw = np.full(n, 0.5)                       # 历史不足时落中性（守判语009不当场评分）
    for i in range(n):
        j0 = max(0, i - max(min_hist, 1) + 1)
        hist = short[j0:i + 1]
        hz = nz[j0:i + 1]
        hist = hist[~hz] if (~hz).sum() >= 3 else hist
        if hist.size >= max(6, min_hist // 4):
            s_raw[i] = float(np.mean(hist <= short[i]))
    return ema_tick(s_raw, tau), 0.0               # 无固定基线期，skip=0


def algo_madbase(ra, nz, ts, win_ep, base_s, scale_ep, gain, tau):
    """H-A 原形式（固定基线）+ 噪声门修订，作对照组。"""
    n = len(ra)
    short, _ = rolling_med_clean(ra, nz, win_ep)
    k_base = max(3, int(base_s / EPOCH_STEP))
    seg, segn = ra[:k_base], nz[:k_base]
    good = seg[~segn]
    b0 = float(np.median(good if good.size >= 3 else seg))
    k_sc = max(6, int(scale_ep / EPOCH_STEP))
    sc, _ = rolling_med_clean(np.abs(ra - b0), nz, k_sc)
    scale = np.maximum(sc, mad(good if good.size >= 3 else seg))
    s_raw = np.where(ts < base_s, 0.5, np.clip(0.5 + (short - b0) / scale * gain, 0.0, 1.0))
    return ema_tick(s_raw, tau), base_s


def algo_rolbase(ra, nz, ts, win_ep, roll_s, scale_ep, gain, tau):
    """H-A″ 滚动长基线：慢漂移由长窗基线吸收，状态=相对长基线的偏离。"""
    n = len(ra)
    short, _ = rolling_med_clean(ra, nz, win_ep)
    base, _ = rolling_med_clean(ra, nz, max(6, int(roll_s / EPOCH_STEP)))
    sc, _ = rolling_med_clean(np.abs(ra - base), nz, max(6, int(scale_ep / EPOCH_STEP)))
    scale = np.maximum(sc, clean_mad(ra, nz))
    skip = roll_s                                  # 基线窗未满前不呈现
    s_raw = np.where(ts < skip, 0.5, np.clip(0.5 + (short - base) / scale * gain, 0.0, 1.0))
    return ema_tick(s_raw, tau), skip


print("=" * 80)
print("V2 步骤1a-2（修订）：三算法族对照 × 参数扫描")
print("=" * 80)
data = load_all()

WIN_EP = int(round(60 / EPOCH_STEP))               # 60秒短窗
results = []

for tag, (ra, ts, nz) in data.items():
    print(f"\n[{tag}] {ra.size} epoch，噪声门剔除 {nz.sum()} ({nz.mean()*100:.1f}%)")

    # ── 族1：滚动分位数（H-A′）──
    for min_hist, tau in itertools.product([120, 300, 600], [12.0]):
        sm, skip = algo_runq(ra, nz, ts, WIN_EP, min_hist, tau)
        m = metrics(sm, max(skip, 60.0))
        if m:
            results.append({"tag": tag, "algo": f"runq_h{min_hist}", "tau": tau,
                            **{k: round(v, 4) for k, v in m.items()},
                            "hard_pass": all(hard_checks(m).values())})

    # ── 族2：固定基线+噪声门（H-A 修订对照）──
    for base_s, gain, tau in itertools.product([120, 300], [0.5, 1.0, 2.0], [12.0]):
        sm, skip = algo_madbase(ra, nz, ts, WIN_EP, base_s, 600, gain, tau)
        m = metrics(sm, skip)
        if m:
            results.append({"tag": tag, "algo": f"fixbase{base_s}_g{gain}", "tau": tau,
                            **{k: round(v, 4) for k, v in m.items()},
                            "hard_pass": all(hard_checks(m).values())})

    # ── 族3：滚动长基线（H-A″）──
    for roll_s, gain, tau in itertools.product([600, 900, 1200], [0.5, 1.0, 2.0], [12.0]):
        sm, skip = algo_rolbase(ra, nz, ts, WIN_EP, roll_s, 600, gain, tau)
        m = metrics(sm, skip)
        if m:
            results.append({"tag": tag, "algo": f"rollbase{roll_s}_g{gain}", "tau": tau,
                            **{k: round(v, 4) for k, v in m.items()},
                            "hard_pass": all(hard_checks(m).values())})

# ══════════ 汇总 ══════════
print("\n" + "=" * 80)
print("汇总：硬验收（触顶<5% / 触底<5% / |Δ|p90<0.05）三段全过")
print("=" * 80)
by_algo = {}
for r in results:
    by_algo.setdefault(r["algo"], []).append(r)

full = []
for algo, rs in by_algo.items():
    if len(rs) == len(data) and all(x["hard_pass"] for x in rs):
        # 排序：居中偏差小 + IQR 大（虽分位族下 IQR 由构造决定，仍作参考）
        score = np.mean([abs(x["median"] - 0.5) for x in rs]) - 0.5 * np.mean([x["q3"] - x["q1"] for x in rs])
        full.append((score, algo, rs))
full.sort(key=lambda x: x[0])

print(f"\n扫描算法配置 {len(by_algo)} 组，三段全过硬验收 {len(full)} 组\n")
for score, algo, rs in full[:10]:
    print(f"  【{algo}】τ={rs[0]['tau']:.0f}s  score={score:.3f}")
    for x in rs:
        print(f"      {x['tag']}: 中位{x['median']:.3f} IQR[{x['q1']:.3f},{x['q3']:.3f}] "
              f"顶{x['top']*100:4.1f}% 底{x['bot']*100:4.1f}% |Δ|p90 {x['p90']:.4f}")

if not full:
    print("  ❌ 无配置全过 —— 须再修订假设")
    print("\n--- 各族最佳（看哪族最接近）---")
    fams = {}
    for r in results:
        f = r["algo"].split("_")[0]
        fams.setdefault(f, []).append(r)
    for f, rs in fams.items():
        best = sorted(rs, key=lambda r: (not r["hard_pass"], abs(r["median"] - 0.5)))[:3]
        print(f"\n  族 {f}:")
        for r in best:
            print(f"    {r['tag']} {r['algo']}: 中位{r['median']:.3f} 顶{r['top']*100:.1f}% "
                  f"底{r['bot']*100:.1f}% |Δ|p90 {r['p90']:.4f} {'✅' if r['hard_pass'] else '❌'}")

with open(os.path.join(OUT, "V2算法扫描_修订.json"), "w", encoding="utf-8") as f:
    json.dump({"n_configs": len(by_algo), "n_full_pass": len(full),
               "full_pass": [{"algo": a, "score": round(s, 4), "rows": rs} for s, a, rs in full[:10]],
               "all_results": results}, f, ensure_ascii=False, indent=2, default=str)
print("\n已存 V2算法扫描_修订.json")
