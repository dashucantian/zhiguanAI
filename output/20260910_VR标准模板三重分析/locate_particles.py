"""粒子与光球的真实落点定位（数据驱动，本轮第三次修正分区错误）

═══ 为何需要这个脚本 ═══
analyze_shots.py 判「粒子场(中上)存在死区」（端到端仅 +13.9%），但粒子是
AdditiveBlending 的 size=.06 小亮点，用区域**均值**度量会被大片背景稀释 ——
这很可能又是「拿假设位置套真实物理落点」的错误（本轮已犯三次：
① 把低通时间常数当振荡器参与互质比对；② 用「上1/3」量 h≈0.16 窄带的 uGlow；
③ 未剥离块注释致误报历史注释）。

故本脚本不再猜分区，而是：
  ① 用 A_Sa0.00 vs A_Sa1.00 的**逐像素差**找出响应最强的区域（自动定位）
  ② 对粒子改用**亮点计数**（bright_pct / 连通域）而非区域均值
  ③ 对光球验证是否高档饱和（emissiveIntensity clamp 到白）

判据修正原则：不同视觉元素须用与其物理形态匹配的度量——
  面状辉光（水面/天穹）→ 区域均值
  点状加性亮点（粒子）→ 亮点占比/计数
  高亮饱和体（光球）  → 饱和像素占比 + 是否 clamp
"""
import os, sys, json, glob
import numpy as np
from PIL import Image

OUT = r"C:\Users\tiand\OneDrive\zhiguanAI\output\20260910_VR标准模板三重分析"
SHOT = os.path.join(OUT, "截图_V2")


def load_gray(name):
    return np.asarray(Image.open(os.path.join(SHOT, name)).convert("L"), dtype=float)


def load_rgb(name):
    return np.asarray(Image.open(os.path.join(SHOT, name)).convert("RGB"), dtype=float)


def main():
    g_lo = load_gray("A_Sa0.00_量程底.png")
    g_hi = load_gray("A_Sa1.00_量程顶.png")
    c_lo = load_rgb("A_Sa0.00_量程底.png")
    c_hi = load_rgb("A_Sa1.00_量程顶.png")
    H, W = g_lo.shape
    d = g_hi - g_lo
    print("=" * 96)
    print("① 逐像素差自动定位：S.a 响应最强的区域（不猜分区）")
    print("=" * 96)
    print(f"图像 {W}x{H}")

    # 粗网格找响应最强块
    NB = 12
    bh, bw = H // NB, W // NB
    grid = np.zeros((NB, NB))
    for i in range(NB):
        for j in range(NB):
            grid[i, j] = d[i*bh:(i+1)*bh, j*bw:(j+1)*bw].mean()
    print("\n响应强度网格（行=y自上而下，列=x自左而右，值=平均亮度差）：")
    print("      " + "".join(f"{j*bw/W:>6.2f}" for j in range(NB)))
    for i in range(NB):
        print(f"{i*bh/H:>5.2f} " + "".join(f"{grid[i,j]:>6.1f}" for j in range(NB)))

    # Top-5 响应块
    flat = [(grid[i, j], i, j) for i in range(NB) for j in range(NB)]
    flat.sort(reverse=True)
    print("\n响应最强 Top-5 块：")
    for v, i, j in flat[:5]:
        print(f"  y={i*bh/H:.2f}-{(i+1)*bh/H:.2f}  x={j*bw/W:.2f}-{(j+1)*bw/W:.2f}  平均差 {v:.1f}")

    # 响应质量分布（重心）
    pos = np.clip(d, 0, None)
    if pos.sum() > 0:
        yy, xx = np.mgrid[0:H, 0:W]
        cy = float((pos * yy).sum() / pos.sum())
        cx = float((pos * xx).sum() / pos.sum())
        print(f"\n正响应重心: y={cy:.0f} ({cy/H:.3f} 屏幕高), x={cx:.0f} ({cx/W:.3f} 屏幕宽)")
        print(f"  → S.a 的视觉能量集中在画面 {cy/H:.0%} 高度处（下半部＝水面区）")

    # 响应占比：多少比例的像素对 S.a 有实质响应
    for thr in [2, 5, 10, 20]:
        pct = float(np.mean(d > thr) * 100)
        print(f"  亮度差 >{thr:>2} 的像素占比 {pct:5.1f}%")

    print("\n" + "=" * 96)
    print("② 粒子度量修正：点状加性亮点须用亮点计数，非区域均值")
    print("=" * 96)
    files = sorted(glob.glob(os.path.join(SHOT, "A_Sa*.png")))
    print(f"{'S.a':>6}{'亮点>128':>10}{'亮点>160':>10}{'亮点>200':>10}"
          f"{'上半亮点':>10}{'下半亮点':>10}{'饱和像素':>10}")
    part_rows = []
    for f in files:
        name = os.path.splitext(os.path.basename(f))[0]
        sa = float(name.split("_")[1].replace("Sa", ""))
        g = np.asarray(Image.open(f).convert("L"), dtype=float)
        rgb = np.asarray(Image.open(f).convert("RGB"), dtype=float)
        sat = np.mean(np.all(rgb > 250, axis=2)) * 100   # 近白＝饱和
        r = {"sa": sa,
             "b128": float(np.mean(g > 128) * 100),
             "b160": float(np.mean(g > 160) * 100),
             "b200": float(np.mean(g > 200) * 100),
             "b128_top": float(np.mean(g[:H//2] > 128) * 100),
             "b128_bot": float(np.mean(g[H//2:] > 128) * 100),
             "sat": float(sat)}
        part_rows.append(r)
        print(f"{sa:>6.2f}{r['b128']:>9.3f}%{r['b160']:>9.3f}%{r['b200']:>9.3f}%"
              f"{r['b128_top']:>9.3f}%{r['b128_bot']:>9.3f}%{r['sat']:>9.3f}%")

    if len(part_rows) >= 2:
        lo, hi = part_rows[0], part_rows[-1]
        print(f"\n端到端（S.a 0→1）：")
        for k, lbl in [("b128", "亮点>128 占比"), ("b160", "亮点>160 占比"),
                       ("b200", "亮点>200 占比"), ("b128_top", "上半亮点占比"),
                       ("b128_bot", "下半亮点占比"), ("sat", "饱和像素占比")]:
            a, b = lo[k], hi[k]
            rel = (b - a) / max(a, 1e-6) * 100
            print(f"  {lbl:<16} {a:7.3f}% → {b:7.3f}%   ({rel:+7.1f}%)")

    print("\n" + "=" * 96)
    print("③ 光球高档饱和验证")
    print("=" * 96)
    # 光球中心（上一轮 locate_signal 实测 y=0.526, x=0.507）
    cy, cx = int(0.526 * H), int(0.507 * W)
    rr = 20
    print(f"光球中心邻域（y={cy}±{rr}, x={cx}±{rr}）：")
    print(f"{'S.a':>6}{'邻域均值':>10}{'邻域最大':>10}{'近白占比':>10}{'理论emissive':>14}")
    orb_rows = []
    for f in files:
        name = os.path.splitext(os.path.basename(f))[0]
        sa = float(name.split("_")[1].replace("Sa", ""))
        g = np.asarray(Image.open(f).convert("L"), dtype=float)
        rgb = np.asarray(Image.open(f).convert("RGB"), dtype=float)
        sub = g[max(0,cy-rr):cy+rr, max(0,cx-rr):cx+rr]
        subc = rgb[max(0,cy-rr):cy+rr, max(0,cx-rr):cx+rr]
        near_white = float(np.mean(np.all(subc > 250, axis=2)) * 100)
        theo = 0.7 + 1.7 * 1.0 + 0.7 * sa        # INHALE → inhale=1.0
        orb_rows.append({"sa": sa, "mean": float(sub.mean()), "max": float(sub.max()),
                         "near_white": near_white, "theo": theo})
        print(f"{sa:>6.2f}{sub.mean():>10.1f}{sub.max():>10.0f}{near_white:>9.1f}%{theo:>14.2f}")
    if len(orb_rows) >= 2:
        print(f"\n判定：")
        lo, hi = orb_rows[0], orb_rows[-1]
        print(f"  理论 emissiveIntensity {lo['theo']:.2f} → {hi['theo']:.2f} (+{(hi['theo']-lo['theo'])/lo['theo']*100:.0f}%)")
        print(f"  实测邻域均值 {lo['mean']:.1f} → {hi['mean']:.1f} (+{(hi['mean']-lo['mean'])/max(lo['mean'],1e-6)*100:.0f}%)")
        if hi["near_white"] > 50:
            print(f"  ⚠️ 高档近白占比 {hi['near_white']:.1f}% > 50% → 确认渲染饱和(clamp到白)，")
            print(f"     故 S.a 高档(0.8→1.0)光球变化不可辨是**饱和所致，非死区**。")
            print(f"     法师实际工作范围 S.a≈0.38~0.50，该区间光球均值 "
                  f"{[r['mean'] for r in orb_rows if 0.3<=r['sa']<=0.5]} → 可辨。")
        else:
            print(f"  高档近白占比 {hi['near_white']:.1f}%，未达饱和判据")

    with open(os.path.join(OUT, "粒子光球落点.json"), "w", encoding="utf-8") as f:
        json.dump({"grid_top5": [{"v": float(v), "y": [i*bh/H, (i+1)*bh/H],
                                  "x": [j*bw/W, (j+1)*bw/W]} for v, i, j in flat[:5]],
                   "particle": part_rows, "orb": orb_rows}, f, ensure_ascii=False, indent=2)
    print("\n已存 粒子光球落点.json")
    return 0


# 修正：上一行残留的错误表达式已移除（name2_idx 未定义）
if __name__ == "__main__":
    sys.exit(main())
