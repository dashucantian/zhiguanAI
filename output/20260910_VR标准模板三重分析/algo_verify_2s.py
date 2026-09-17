"""V2 步骤1a-3：按前端真实节奏重验（移植前的最后一道关卡）

═══ 为何必须重验（发现的移植陷阱）═══
验证脚本用 report_generator 口径：10秒窗、**5秒步进**（EPOCH_STEP=5）
前端实际收到：10秒窗（BP_EPOCH_SEC=10）、**2秒步进**（last_bp_time<2.0 则跳过）

若直接照搬"历史窗 120 epoch"，移植后变成 120×2秒=4分钟，而非验证的 10 分钟。
→ 窗口必须按【时间】定义，且须在前端真实节奏下重验。

═══ 本脚本做的事 ═══
1. 按 10秒窗 / 2秒步进 重算 rel_alpha 序列（＝前端 bands 到达节奏）
2. 前端可自算噪声门：bg_rel=(beta+gamma)/total > 0.65（NOISE_BG_RATIO，复用既有阈值）
3. 短窗 60秒 = 最近 30 个值的中位数；历史窗按【秒】定义
4. EMA 在 tick 级（0.25秒）跑，输入每 2秒才变一次 —— 与前端结构一致
"""
import os, sys, json, itertools
import numpy as np

RG_DIR = r"C:\Users\tiand\OneDrive\zhiguanAI\muse2-repo\muse2-master\muse-cloud-server"
sys.path.insert(0, RG_DIR)
import report_generator as rg

REPORT_DIR = r"C:\Users\tiand\OneDrive\zhiguanAI\muse2-repo\muse2-master\report"
OUT = r"C:\Users\tiand\OneDrive\zhiguanAI\output\20260910_VR标准模板三重分析"
CACHE = os.path.join(OUT, "_ra_2s_cache.npz")

BANDS = rg.BANDS
NOISE_BG_RATIO = rg.NOISE_BG_RATIO      # 0.65，复用既有阈值不自建
WIN_SEC = 10.0                          # BP_EPOCH_SEC，后端窗口
STEP_SEC = 2.0                          # 后端重算间隔（last_bp_time<2.0 跳过）
TICK_SEC = 0.25                         # console_server TICK_SEC

SESSIONS = [
    ("local_20260910_121639.npz", "A_0910_22min"),
    ("local_20260910_130105.npz", "B_0910_42min"),
    ("local_20260911_094407.npz", "C_0911_43min"),
]


def series_2s(name):
    """按前端真实节奏算 rel_alpha：10秒窗、2秒步进。同时算噪声门标志。"""
    with np.load(os.path.join(REPORT_DIR, name), allow_pickle=True) as z:
        meta = z["meta"].item() if "meta" in z.files else {}
        eeg = np.asarray(z["eeg"], dtype=np.float64)
        sfreq = float(meta.get("sfreq") or rg.SFREQ)
    win = int(WIN_SEC * sfreq)
    step = int(STEP_SEC * sfreq)
    ras, ts, nz = [], [], []
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
        nz.append((lin["Beta"] + lin["Gamma"]) / tot > NOISE_BG_RATIO)
    return np.asarray(ras), np.asarray(ts), np.asarray(nz, dtype=bool)


def load_all():
    if os.path.exists(CACHE):
        with np.load(CACHE, allow_pickle=True) as c:
            return {tag: (c[tag + "_ra"], c[tag + "_ts"], c[tag + "_nz"])
                    for _, tag in SESSIONS if tag + "_ra" in c.files}
    data, flat = {}, {}
    for name, tag in SESSIONS:
        p = os.path.join(REPORT_DIR, name)
        if not os.path.exists(p):
            continue
        ra, ts, nz = series_2s(name)
        data[tag] = (ra, ts, nz)
        flat[tag + "_ra"] = ra; flat[tag + "_ts"] = ts; flat[tag + "_nz"] = nz
        print(f"  载入 {tag}: {ra.size} 个值（2秒步进），{ts[-1]/60:.1f}分钟，"
              f"噪声门 {nz.sum()} ({nz.mean()*100:.1f}%)")
    np.savez_compressed(CACHE, **flat)
    print("  已缓存 _ra_2s_cache.npz")
    return data


def roll_med_time(x, nz, t, win_sec):
    """按【时间】滚动中位数，窗内剔噪声（因果只用过去）。"""
    n = len(x); out = np.empty(n)
    for i in range(n):
        j0 = int(np.searchsorted(t, t[i] - win_sec))
        seg, segn = x[j0:i + 1], nz[j0:i + 1]
        good = seg[~segn]
        out[i] = np.median(good) if good.size >= 3 else np.median(seg)
    return out


def runq_time(x, nz, t, short_sec, hist_sec, tau):
    """H-A′ 因果滚动分位数（窗口按时间定义）→ tick 级 S.a 序列。"""
    short = roll_med_time(x, nz, t, short_sec)
    n = len(short)
    s_val = np.full(n, 0.5)                    # 历史不足→中性（判语009 不当场评分）
    for i in range(n):
        j0 = int(np.searchsorted(t, t[i] - hist_sec))
        hist = short[j0:i + 1]; hz = nz[j0:i + 1]
        hist = hist[~hz] if (~hz).sum() >= 3 else hist
        if hist.size >= 15:                    # 至少 30 秒历史才出数
            s_val[i] = float(np.mean(hist <= short[i]))
    # 展到 tick 级：每 2 秒一个输入值 → 8 个 tick
    tpe = int(round(STEP_SEC / TICK_SEC))
    s_tick = np.repeat(s_val, tpe)
    t_tick = np.repeat(t, tpe)
    a = TICK_SEC / tau
    sm = np.empty_like(s_tick); sm[0] = s_tick[0]
    for i in range(1, len(s_tick)):
        sm[i] = sm[i - 1] + (s_tick[i] - sm[i - 1]) * a
    return sm, t_tick, s_val


def metrics(sm, t_tick, skip_s):
    post = sm[t_tick >= skip_s]
    if post.size < 40:
        return None
    d = np.abs(np.diff(post))
    return {"median": float(np.median(post)),
            "q1": float(np.percentile(post, 25)), "q3": float(np.percentile(post, 75)),
            "top": float(np.mean(post >= 0.999)), "bot": float(np.mean(post <= 0.001)),
            "p90": float(np.percentile(d, 90)),
            "p99": float(np.percentile(d, 99)),
            "max_jump": float(d.max())}


def hard_pass(m):
    """有判别力的验收项（median/IQR 在分位族下由构造满足，不计入）"""
    return m["top"] < 0.05 and m["bot"] < 0.05 and m["p90"] < 0.05


print("=" * 84)
print("V2 步骤1a-3：按前端真实节奏（10秒窗/2秒步进）重验 —— 窗口按时间定义")
print("=" * 84)
data = load_all()

SHORT_SEC = 60.0          # 短窗 60 秒
TAU = 12.0                # 裁定6默认值
HISTS = [300.0, 600.0, 900.0]      # 历史窗 5/10/15 分钟
results = []

for tag, (ra, ts, nz) in data.items():
    total = float(ts[-1])
    print(f"\n[{tag}] {ra.size} 值 / {total/60:.1f}分钟 / 噪声 {nz.mean()*100:.1f}%")
    print(f"  σ(Δrel_alpha)={np.std(np.diff(ra)):.5f}  全场中位={np.median(ra):.4f}")
    for hist in HISTS:
        if total < hist + 120:
            print(f"  hist={hist:.0f}s: 数据不足（需 {hist+120:.0f}s，仅 {total:.0f}s），跳过")
            continue
        sm, t_tick, s_val = runq_time(ra, nz, ts, SHORT_SEC, hist, TAU)
        m = metrics(sm, t_tick, hist)
        if not m:
            print(f"  hist={hist:.0f}s: 评估段太短")
            continue
        hp = hard_pass(m)
        results.append({"tag": tag, "hist_s": hist, "tau": TAU, "short_s": SHORT_SEC,
                        **{k: round(v, 5) for k, v in m.items()}, "hard_pass": hp})
        print(f"  hist={hist:5.0f}s({hist/60:.0f}分): 中位{m['median']:.3f} "
              f"IQR[{m['q1']:.3f},{m['q3']:.3f}] 顶{m['top']*100:4.1f}% 底{m['bot']*100:4.1f}% "
              f"|Δ|p90 {m['p90']:.4f} p99 {m['p99']:.4f} max {m['max_jump']:.4f} "
              f"{'✅' if hp else '❌'}")

print("\n" + "=" * 84)
print("汇总：三段全过硬验收的历史窗配置")
print("=" * 84)
by_hist = {}
for r in results:
    by_hist.setdefault(r["hist_s"], []).append(r)
ok = [(h, rs) for h, rs in by_hist.items() if len(rs) == len(data) and all(x["hard_pass"] for x in rs)]
print(f"\n评估配置 {len(by_hist)} 组（历史窗档），三段全过 {len(ok)} 组")
for h, rs in sorted(ok, key=lambda kv: kv[0]):
    print(f"\n  ✅ 历史窗 {h:.0f}s（{h/60:.0f}分钟）短窗{rs[0]['short_s']:.0f}s τ={rs[0]['tau']:.0f}s")
    for x in rs:
        print(f"      {x['tag']}: 中位{x['median']:.3f} 顶{x['top']*100:.1f}% 底{x['bot']*100:.1f}% "
              f"|Δ|p90 {x['p90']:.4f} max {x['max_jump']:.4f}")
if not ok:
    print("\n  ❌ 无配置全过，须再调参")

# ── 与旧 q1q3 静态标定的直接对比（同节奏下）──
print("\n" + "=" * 84)
print("对照：同节奏下旧 q1q3 静态标定（已应用版本）的抖动")
print("=" * 84)
CAL_Q1Q3 = {"lo": 0.0306, "span": 0.0119}
for tag, (ra, ts, nz) in data.items():
    s_old = np.clip((ra - CAL_Q1Q3["lo"]) / CAL_Q1Q3["span"], 0.0, 1.0)
    tpe = int(round(STEP_SEC / TICK_SEC))
    tick_old = np.repeat(s_old, tpe)
    a = TICK_SEC / 0.87        # 前端现状 α=0.25 → τ≈0.87s
    sm_old = np.empty_like(tick_old); sm_old[0] = tick_old[0]
    for i in range(1, len(tick_old)):
        sm_old[i] = sm_old[i-1] + (tick_old[i] - sm_old[i-1]) * a
    d = np.abs(np.diff(sm_old))
    print(f"  {tag}: 中位{np.median(sm_old):.3f} 顶{np.mean(sm_old>=0.999)*100:4.1f}% "
          f"底{np.mean(sm_old<=0.001)*100:4.1f}% |Δ|p90 {np.percentile(d,90):.4f} "
          f"p99 {np.percentile(d,99):.4f} max {d.max():.4f}")

with open(os.path.join(OUT, "V2算法验证_前端节奏.json"), "w", encoding="utf-8") as f:
    json.dump({"win_sec": WIN_SEC, "step_sec": STEP_SEC, "tick_sec": TICK_SEC,
               "short_sec": SHORT_SEC, "tau": TAU, "results": results,
               "passing_hists": [h for h, _ in ok]}, f, ensure_ascii=False, indent=2, default=str)
print("\n已存 V2算法验证_前端节奏.json")
