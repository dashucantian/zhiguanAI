"""V2 步骤5：视觉连续性量化对比（新旧算法 → 真实视觉参数）

═══ 为何不用静态截图验证"闪" ═══
法师抱怨的是「不流畅、会闪、有跳跃感」——这是**时间维度**现象。
静态截图只能拍单帧，单帧之间没有"流畅度"可言。
故改为：把新旧算法的 S.a 时间序列代入**页面真实的视觉参数公式**，
算出各视觉通道的逐帧值，量化相邻帧变化并可视化。
公式取自 vr_feedback.html 主循环（grep 核实，非臆测）：
  sky.uGlow            = .2 + .8*S.a
  pMat.opacity         = .35 + .55*S.a
  orb.emissiveIntensity= 0.7 + 1.7*inhale + 0.7*S.a
  water shader uA      = S.a
"""
import os, sys, json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE = r"C:\Users\tiand\OneDrive\zhiguanAI"
OUT = os.path.join(BASE, "output", "20260910_VR标准模板三重分析")
FIG = os.path.join(OUT, "图")
CACHE = os.path.join(OUT, "_ra_2s_cache.npz")
os.makedirs(FIG, exist_ok=True)
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

SR = 48000
WIN_SEC, STEP_SEC, TICK_SEC = 10.0, 2.0, 0.25
TPE = int(round(STEP_SEC / TICK_SEC))        # 8 tick/值
FPS_VR = 90                                   # Pico 头显帧率
NOISE_BG = 0.65
SHORT_SEC, HIST_SEC, TAU = 60.0, 300.0, 12.0
WARM_SEC, MIN_HIST = 90.0, 15
CAL_OLD = {"lo": 0.0306, "span": 0.0119}      # q1q3（已废弃）
CAL_P5P95 = {"lo": 0.0253, "span": 0.0480}    # p5/p95（更早版本）
TAU_OLD = 0.87                                # 旧前端 α=.25 @ tick0.25s

SESSIONS = ["A_0910_22min", "B_0910_42min", "C_0911_43min"]


def mad(x):
    if x.size < 3:
        return 1e-4
    return max(1.4826 * float(np.median(np.abs(x - np.median(x)))), 1e-4)


def roll_med_time(x, nz, t, win_sec):
    n = len(x); out = np.empty(n)
    for i in range(n):
        j0 = int(np.searchsorted(t, t[i] - win_sec))
        seg, segz = x[j0:i+1], nz[j0:i+1]
        good = seg[~segz]
        out[i] = np.median(good) if good.size >= 3 else np.median(seg)
    return out


def algo_new(ra, nz, ts):
    """H-A′ 因果滚动分位数 + EMA τ=12s（已实装并验证）"""
    short = roll_med_time(ra, nz, ts, SHORT_SEC)
    n = len(short)
    s_val = np.full(n, 0.5)
    for i in range(n):
        j0 = int(np.searchsorted(ts, ts[i] - HIST_SEC))
        hist = short[j0:i+1]; hz = nz[j0:i+1]
        hist = hist[~hz] if (~hz).sum() >= 3 else hist
        if hist.size >= MIN_HIST:
            s_val[i] = float(np.mean(hist <= short[i]))
    # 展到 tick 级后 EMA
    s_tick = np.repeat(s_val, TPE)
    a = TICK_SEC / TAU
    sm = np.empty_like(s_tick); sm[0] = s_tick[0]
    for i in range(1, len(s_tick)):
        sm[i] = sm[i-1] + (s_tick[i] - sm[i-1]) * a
    return sm


def algo_static(ra, nz, ts, cal, tau):
    """旧静态标定 + 旧 EMA（q1q3 与 p5p95 两版对照）"""
    s = np.clip((ra - cal["lo"]) / cal["span"], 0.0, 1.0)
    s_tick = np.repeat(s, TPE)
    a = TICK_SEC / tau
    sm = np.empty_like(s_tick); sm[0] = s_tick[0]
    for i in range(1, len(s_tick)):
        sm[i] = sm[i-1] + (s_tick[i] - sm[i-1]) * a
    return sm


# ══════════ 视觉参数映射（页面真实公式） ══════════
def to_visual(sa, inhale=0.5):
    """S.a → 各视觉通道值（公式取自 vr_feedback.html 主循环）"""
    return {
        "sky_glow": .2 + .8*sa,                       # 天穹辉光
        "particle_opacity": .35 + .55*sa,             # 粒子透明度
        "orb_intensity": 0.7 + 1.7*inhale + 0.7*sa,   # 光球亮度（含呼吸项）
        "water_uA": sa,                               # 水面辉光强度
    }


def frame_diff(v_seq, fps=FPS_VR):
    """把 tick 级序列重采样到 VR 帧级，算相邻帧变化。
    tick=0.25s，VR帧=1/90s → 每 tick 含 22.5 帧；
    同一 tick 内值恒定（EMA 在主循环逐帧做），故按帧插值更真实。"""
    n_tick = len(v_seq)
    dur = n_tick * TICK_SEC
    n_frame = int(dur * fps)
    t_tick = np.arange(n_tick) * TICK_SEC
    t_frame = np.linspace(0, dur, n_frame, endpoint=False)
    v_frame = np.interp(t_frame, t_tick, v_seq)
    return v_frame, np.abs(np.diff(v_frame))


# ══════════ 载入数据 ══════════
with np.load(CACHE, allow_pickle=True) as c:
    data = {tag: (c[tag+"_ra"], c[tag+"_ts"], c[tag+"_nz"])
            for tag in SESSIONS if tag+"_ra" in c.files}

print("=" * 88)
print("V2 步骤5：视觉连续性量化（S.a → 页面真实视觉参数 → VR 90fps 帧级变化）")
print("=" * 88)

summary = {}
fig, axes = plt.subplots(3, 2, figsize=(17, 12))

for row, tag in enumerate(SESSIONS):
    if tag not in data:
        continue
    ra, ts, nz = data[tag]
    total = float(ts[-1])
    sa_new = algo_new(ra, nz, ts)
    sa_q1q3 = algo_static(ra, nz, ts, CAL_OLD, TAU_OLD)
    sa_p5 = algo_static(ra, nz, ts, CAL_P5P95, TAU_OLD)

    # 跳过预热/历史填充段
    skip_t = HIST_SEC
    keep = lambda arr: arr[int(skip_t/TICK_SEC):]
    sn, sq, sp = keep(sa_new), keep(sa_q1q3), keep(sa_p5)

    print(f"\n[{tag}] {total/60:.0f}分钟，评估段 {len(sn)*TICK_SEC/60:.1f} 分钟")
    row_sum = {}
    for name, arr in [("新(H-A′)", sn), ("旧q1q3", sq), ("旧p5p95", sp)]:
        vf, df = frame_diff(arr)
        vis = to_visual(vf)
        # 各视觉通道的帧级变化
        glow_d = np.abs(np.diff(vis["sky_glow"]))
        part_d = np.abs(np.diff(vis["particle_opacity"]))
        orb_d = np.abs(np.diff(vis["orb_intensity"]))
        row_sum[name] = {
            "sa_median": round(float(np.median(arr)), 3),
            "sa_top_pct": round(float(np.mean(arr >= 0.999))*100, 1),
            "sa_bot_pct": round(float(np.mean(arr <= 0.001))*100, 1),
            "sa_frame_p90": round(float(np.percentile(df, 90)), 5),
            "sa_frame_max": round(float(df.max()), 5),
            "glow_frame_max": round(float(glow_d.max()), 4),
            "particle_frame_max": round(float(part_d.max()), 4),
            "orb_frame_max": round(float(orb_d.max()), 4),
            "n_frames": int(len(vf)),
        }
        r = row_sum[name]
        print(f"  {name:10s}: S.a中位{r['sa_median']:.3f} 顶{r['sa_top_pct']:4.1f}% 底{r['sa_bot_pct']:4.1f}% | "
              f"帧级|ΔS.a| p90 {r['sa_frame_p90']:.5f} max {r['sa_frame_max']:.4f} | "
              f"天穹辉光max {r['glow_frame_max']:.4f} 粒子max {r['particle_frame_max']:.4f} 光球max {r['orb_frame_max']:.4f}")
    summary[tag] = row_sum

    # ── 左图：S.a 时间序列（三算法）──
    ax = axes[row][0]
    tmin = np.arange(len(sq)) * TICK_SEC / 60
    tmin_n = np.arange(len(sn)) * TICK_SEC / 60
    ax.plot(tmin, sq, color="#e03131", lw=0.6, alpha=0.85, label="旧 q1q3（τ=0.87s）")
    ax.plot(tmin, sp, color="#f08c00", lw=0.6, alpha=0.65, label="旧 p5p95（τ=0.87s）")
    ax.plot(tmin_n, sn, color="#2f9e44", lw=1.0, label="新 H-A′（τ=12s）")
    ax.set_ylim(-0.05, 1.05)
    ax.axhline(0.5, color="#888", ls=":", lw=0.7)
    ax.set_title(f"{tag} · S.a 时间序列", fontsize=11)
    ax.set_xlabel("分钟"); ax.set_ylabel("S.a")
    ax.legend(fontsize=8, loc="upper right")
    ax.grid(alpha=0.25)

    # ── 右图：视觉通道帧级变化（VR 90fps）──
    ax = axes[row][1]
    vf_q, _ = frame_diff(sq); vf_n, _ = frame_diff(sn)
    tsec_q = np.arange(len(vf_q)) / FPS_VR
    tsec_n = np.arange(len(vf_n)) / FPS_VR
    # 只画前 120 秒（细节可辨）
    m_q = tsec_q < 120; m_n = tsec_n < 120
    vq = to_visual(vf_q[m_q]); vn = to_visual(vf_n[m_n])
    ax.plot(tsec_q[m_q], vq["sky_glow"], color="#e03131", lw=0.5, alpha=0.8, label="旧 q1q3 天穹辉光")
    ax.plot(tsec_n[m_n], vn["sky_glow"], color="#2f9e44", lw=1.2, label="新 H-A′ 天穹辉光")
    ax.plot(tsec_q[m_q], vq["particle_opacity"], color="#e03131", lw=0.5, alpha=0.4, ls="--", label="旧 q1q3 粒子透明度")
    ax.plot(tsec_n[m_n], vn["particle_opacity"], color="#2f9e44", lw=1.0, ls="--", alpha=0.8, label="新 H-A′ 粒子透明度")
    ax.set_title(f"{tag} · 视觉通道值（VR 90fps，前120秒）", fontsize=11)
    ax.set_xlabel("秒"); ax.set_ylabel("通道值")
    ax.legend(fontsize=7, loc="best", ncol=2)
    ax.grid(alpha=0.25)

plt.suptitle("V2 步骤5 · 视觉连续性量化对比：旧标定（锯齿跳变＝法师所见『闪』） vs 新 H-A′（连绵）",
             fontsize=13, y=0.995)
plt.tight_layout()
p = os.path.join(FIG, "图7_视觉连续性对比.png")
plt.savefig(p, dpi=105, bbox_inches="tight")
print(f"\n已存 {p}")

# ── 汇总判定 ──
print("\n" + "=" * 88)
print("帧级变化汇总（VR 90fps，越小越连绵）")
print("=" * 88)
print(f"{'段':<16}{'算法':<12}{'帧级|ΔS.a|max':>14}{'天穹max':>10}{'粒子max':>10}{'光球max':>10}{'触顶%':>8}")
for tag, row in summary.items():
    for name, r in row.items():
        print(f"{tag:<16}{name:<12}{r['sa_frame_max']:>14.5f}{r['glow_frame_max']:>10.4f}"
              f"{r['particle_frame_max']:>10.4f}{r['orb_frame_max']:>10.4f}{r['sa_top_pct']:>8.1f}")

# 改善倍数
print("\n改善倍数（旧 q1q3 → 新 H-A′）：")
for tag, row in summary.items():
    if "旧q1q3" in row and "新(H-A′)" in row:
        o, n = row["旧q1q3"], row["新(H-A′)"]
        ratio = o["sa_frame_max"] / max(n["sa_frame_max"], 1e-9)
        print(f"  {tag}: 帧级最大跳变 {o['sa_frame_max']:.4f} → {n['sa_frame_max']:.5f}  (改善 {ratio:.1f} 倍)")

with open(os.path.join(OUT, "V2视觉连续性.json"), "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
print("\n已存 V2视觉连续性.json")
