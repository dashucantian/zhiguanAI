"""诊断"闪动/跳跃感"的成因：标定收窄对 epoch 间抖动的放大效应。

核心问题：q1/q3 把 relASpan 从 0.0582 收窄到 0.0119（4.9倍灵敏），
rel_alpha 的固有噪声是否被同倍放大成可见抖动？叠加 clamp 触顶-回落是否形成跳跃？

用真机数据（含 09-11 实测段）按项目口径算，不自立标准。
"""
import os, sys, json
import numpy as np

RG_DIR = r"C:\Users\tiand\OneDrive\zhiguanAI\muse2-repo\muse2-master\muse-cloud-server"
sys.path.insert(0, RG_DIR)
import report_generator as rg

REPORT_DIR = r"C:\Users\tiand\OneDrive\zhiguanAI\muse2-repo\muse2-master\report"
BANDS = rg.BANDS
EPOCH_S, EPOCH_STEP = rg.EPOCH_SECONDS, rg.EPOCH_STEP

# 两档标定对比
CAL_OLD = {"lo": 0.0303, "span": 0.0582}   # p5/p95（重标定前）
CAL_NEW = {"lo": 0.0306, "span": 0.0119}   # q1/q3（已应用）

SESSIONS = [
    ("local_20260910_121639.npz", "09-10会话A 22min"),
    ("local_20260910_130105.npz", "09-10会话B 42min"),
    ("local_20260911_094407.npz", "09-11实测 45MB"),
]


def series(name):
    """按项目口径切 epoch，返回 rel_alpha 时间序列。"""
    with np.load(os.path.join(REPORT_DIR, name), allow_pickle=True) as z:
        meta = z["meta"].item() if "meta" in z.files else {}
        eeg = np.asarray(z["eeg"], dtype=np.float64)
        sfreq = float(meta.get("sfreq") or rg.SFREQ)
    win, step = int(EPOCH_S * sfreq), int(EPOCH_STEP * sfreq)
    ras = []
    for s in range(0, max(1, eeg.shape[0] - win + 1), step):
        bp = rg.compute_band_power_chunk(eeg[s:s + win], sfreq)
        if bp is None:
            continue
        db = {b: float(np.mean(np.asarray(bp["db"][b], dtype=np.float64))) for b in BANDS}
        lin = {b: 10.0 ** (db[b] / 10.0) for b in BANDS}
        tot = sum(lin.values())
        if tot > 0:
            ras.append(lin["Alpha"] / tot)
    return np.asarray(ras), eeg.shape[0] / sfreq / 60


def cl(v):
    return np.clip(v, 0.0, 1.0)


print("=" * 78)
print("标定收窄对抖动的放大效应诊断")
print("=" * 78)
summary = {}
for name, label in SESSIONS:
    if not os.path.exists(os.path.join(REPORT_DIR, name)):
        print(f"\n[{label}] 文件不存在，跳过")
        continue
    ra, mins = series(name)
    if ra.size < 4:
        print(f"\n[{label}] epoch 太少({ra.size})，跳过")
        continue
    d_old = cl((ra - CAL_OLD["lo"]) / CAL_OLD["span"])
    d_new = cl((ra - CAL_NEW["lo"]) / CAL_NEW["span"])
    # 逐 epoch 跳变幅度（|ΔS.a|）——这是"闪"的直接度量
    j_old = np.abs(np.diff(d_old))
    j_new = np.abs(np.diff(d_new))
    # 触顶比例（clamp 到 1.0 的时段，触顶-回落即跳跃感）
    top_new = float(np.mean(d_new >= 0.999))
    top_old = float(np.mean(d_old >= 0.999))
    print(f"\n[{label}] {mins:.0f}分钟, epoch {ra.size}")
    print(f"  S.a 中位   旧 {np.median(d_old):.3f} → 新 {np.median(d_new):.3f}")
    print(f"  逐epoch跳变|ΔS.a| 中位  旧 {np.median(j_old):.3f} → 新 {np.median(j_new):.3f}  (放大 {np.median(j_new)/max(np.median(j_old),1e-9):.1f}x)")
    print(f"  逐epoch跳变|ΔS.a| p90   旧 {np.percentile(j_old,90):.3f} → 新 {np.percentile(j_new,90):.3f}  (放大 {np.percentile(j_new,90)/max(np.percentile(j_old,90),1e-9):.1f}x)")
    print(f"  触顶(=1.0)时段占比      旧 {top_old*100:.1f}% → 新 {top_new*100:.1f}%")
    # rel_alpha 固有噪声：相邻 epoch 差分标准差
    print(f"  rel_alpha 固有噪声 σ(Δ) = {np.std(np.diff(ra)):.5f}  →  映射到 S.a 的噪声 旧 {np.std(np.diff(ra))/CAL_OLD['span']:.3f} / 新 {np.std(np.diff(ra))/CAL_NEW['span']:.3f}")
    summary[label] = {
        "minutes": round(float(mins), 1), "n_epoch": int(ra.size),
        "sa_median_old": round(float(np.median(d_old)), 3), "sa_median_new": round(float(np.median(d_new)), 3),
        "jump_median_old": round(float(np.median(j_old)), 4), "jump_median_new": round(float(np.median(j_new)), 4),
        "jump_p90_old": round(float(np.percentile(j_old, 90)), 4), "jump_p90_new": round(float(np.percentile(j_new, 90)), 4),
        "saturate_old": round(top_old, 4), "saturate_new": round(top_new, 4),
        "ra_noise_sigma": round(float(np.std(np.diff(ra))), 5),
    }

print("\n" + "=" * 78)
print("平滑系数模拟：ws 每 tick 做 S.a += (a-S.a)*α，检验不同 α 的残余抖动")
print("=" * 78)
# 取最长的一段 rel_alpha，按 4 tick/秒插值后模拟前端平滑
if summary:
    name = "local_20260911_094407.npz" if any("09-11" in k for k in summary) else SESSIONS[0][0]
    ra, _ = series(name)
    if ra.size >= 4:
        # epoch 步长 5s，tick 4/秒 → 每 epoch 20 tick；线性插值到 tick 级
        n_tick = (ra.size - 1) * int(EPOCH_STEP * 4)
        tick = np.linspace(0, ra.size - 1, n_tick)
        ra_tick = np.interp(tick, np.arange(ra.size), ra)
        a_tick = cl((ra_tick - CAL_NEW["lo"]) / CAL_NEW["span"])
        print(f"用 {os.path.basename(name)}，tick 级序列 {n_tick} 点（{EPOCH_STEP*4:.0f} tick/epoch）")
        for alpha in [0.25, 0.10, 0.05, 0.02]:
            sm = np.zeros_like(a_tick)
            sm[0] = a_tick[0]
            for i in range(1, n_tick):
                sm[i] = sm[i - 1] + (a_tick[i] - sm[i - 1]) * alpha
            # 残余抖动：平滑后逐 tick 变化量
            jit = np.abs(np.diff(sm))
            # 有效时间常数（秒）
            tau = EPOCH_STEP / (-np.log(1 - alpha)) if alpha < 1 else 0
            print(f"  α={alpha:.2f}  时间常数≈{tau:5.1f}s  残余|Δ/tick|中位 {np.median(jit):.4f}  p90 {np.percentile(jit,90):.4f}  值域[{sm.min():.2f},{sm.max():.2f}]")

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "抖动诊断.json"), "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)
print("\n已存 抖动诊断.json")
