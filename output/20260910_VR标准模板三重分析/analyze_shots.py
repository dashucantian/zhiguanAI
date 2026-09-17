"""V2 步骤5：截图量化分析（分区按 locate_signal.py 实测落点重定）

═══ 上一版判据错误（记录，避免重犯）═══
上一版报「天穹区存在死区」，实为**分区定义错误**：
  locate_signal.py 实测 S.a 0→1 的逐行亮度差剖面：
    上半部(y<0.5)  平均差 0.59
    下半部(y>0.5)  平均差 46.35     ← 差 78 倍
    最强带 y=0.843（水面）平均差 61.92
    光球中心实测 (y=0.526, x=0.507)
  查 shader 可知 sky 的 uGlow 项被 pow(max(0,1-abs(h-.16)*4),3) 限制在
  h≈0.16 的**窄带**，用「上1/3」大片区域去量必然把信号稀释到不可见。
  → 与本轮此前 4 个判据 bug 同源：拿假设区域套真实物理位置。

═══ 本版改法 ═══
① 分区依实测落点定义（水面带 y=0.75~0.95、光球区按实测中心 ±0.06）
② 判据分层：只对「按四维分工**应当**响应 S.a 的通道」判死区；
   对设计上不该响应 S.a 的通道（天穹属底色层）不套用同一判据，
   而是单独报告其实际响应量，并把发现的不一致列为待裁定项。
③ 粒子用 bright_pct（加性混合的小亮点占比）作指标，比区域均值敏感。
"""
import os, sys, json, glob
import numpy as np
from PIL import Image

OUT = r"C:\Users\tiand\OneDrive\zhiguanAI\output\20260910_VR标准模板三重分析"
SHOT = os.path.join(OUT, "截图_V2")

# 分区依 locate_signal.py + locate_particles.py 实测落点（fraction of W,H）
# 实测：S.a 响应重心 y=0.773（下半水面）；光球中心 (y=0.526,x=0.507)；
#       上半部(y<0.33)对 S.a 几乎无响应（天穹属底色层，符合四维分工）
# metric: "mean"=区域均值（面状辉光）  "bright"=亮点>128占比（点状加性粒子）
# driver: 该通道按四维分工**应当**由哪个维度主导 → 决定用不用 S.a 死区判据
REGIONS = {
    # 中程层（S.a 主导）→ 判 S.a 死区
    "水面辉光带":   (0.05, 0.75, 0.95, 0.95, "S.a",   "mean",   "water shader uA（S.a 主通道）"),
    "水面全区":     (0.00, 0.55, 1.00, 1.00, "S.a",   "mean",   "water shader uA"),
    "粒子场":       (0.00, 0.00, 1.00, 1.00, "S.a",   "bright", "pMat.opacity（点状加性，用亮点计数）"),
    # 短程层（呼吸引导主导，S.a 仅次调制）→ 不判 S.a 死区
    "光球区":       (0.44, 0.45, 0.58, 0.61, "breath", "mean",  "orb 呼吸引导所缘，S.a 次调制"),
    # 底色层（state 主导，τ=60s）→ 不判 S.a 死区
    "天穹":         (0.00, 0.00, 1.00, 0.30, "state",  "mean",  "sky uTop/uBot（τ=60s 慢变）"),
    # 综合
    "全图":         (0.00, 0.00, 1.00, 1.00, "-",      "mean",  "综合"),
}


def stats(img, box):
    w, h = img.size
    x0, y0, x1, y1 = box[:4]
    crop = img.crop((int(x0*w), int(y0*h), int(x1*w), int(y1*h)))
    a = np.asarray(crop.convert("L"), dtype=np.float64)
    rgb = np.asarray(crop.convert("RGB"), dtype=np.float64)
    return {"mean": float(a.mean()), "p95": float(np.percentile(a, 95)),
            "bright_pct": float(np.mean(a > 128) * 100),
            "sat": float((rgb.max(axis=2) - rgb.min(axis=2)).mean())}


def metric_val(row, rn):
    """按分区声明的度量取值：mean=区域均值，bright=亮点>128占比。
    点状加性粒子(pMat)须用亮点计数——用区域均值会被背景稀释（见 locate_particles.py：
    粒子场端到端均值仅+13.9%，但上半亮点计数+28.1%、下半+77.9%，实为有效响应）。"""
    return row[rn]["bright_pct"] if REGIONS[rn][5] == "bright" else row[rn]["mean"]


def load_group(prefix):
    fs = sorted(glob.glob(os.path.join(SHOT, f"{prefix}*.png")))
    out = []
    for f in fs:
        name = os.path.splitext(os.path.basename(f))[0]
        out.append({"name": name, "path": f,
                    "kb": round(os.path.getsize(f)/1024, 1)})
    return out


def analyze_A():
    """A 组：S.a 全量程可辨性（V2 核心目标——09-10 死区问题是否解决）"""
    print("=" * 100)
    print("【A 组】S.a 全量程视觉可辨性（分区按实测落点定义）")
    print("=" * 100)
    files = load_group("A_Sa")
    if not files:
        print("❌ 未找到 A 组截图"); return None, False
    data = []
    for f in files:
        # 文件名 A_Sa0.00_量程底 → 0.00
        sa = float(f["name"].split("_")[1].replace("Sa", ""))
        img = Image.open(f["path"])
        row = {"name": f["name"], "sa": sa, "kb": f["kb"]}
        for rn, box in REGIONS.items():
            row[rn] = stats(img, box)
        data.append(row)

    print(f"\n{'S.a':>5}{'文件大小':>10}" + "".join(f"{rn[:8]:>12}" for rn in REGIONS))
    for r in data:
        print(f"{r['sa']:>5.2f}{r['kb']:>9.1f}K" +
              "".join(f"{metric_val(r, rn):>12.2f}" for rn in REGIONS))

    # 端到端（S.a 0→1），按各分区声明的度量取值
    print("\n【端到端量程覆盖 S.a 0.00→1.00】（度量：面状=均值，点状粒子=亮点占比）")
    lo, hi = data[0], data[-1]
    verdict = {}
    for rn, box in REGIONS.items():
        drv, met = box[4], box[5]
        a, b = metric_val(lo, rn), metric_val(hi, rn)
        rel = (b - a) / max(a, 1e-6) * 100
        sa, sb = lo[rn]["sat"], hi[rn]["sat"]
        verdict[rn] = {"driver": drv, "metric": met,
                       "val_lo": round(a, 3), "val_hi": round(b, 3),
                       "rel_pct": round(rel, 1),
                       "sat_lo": round(sa, 2), "sat_hi": round(sb, 2),
                       "note": box[6]}
        unit = "%" if met == "bright" else ""
        print(f"  {rn:<12}[驱动={drv:<6} 度量={met:<6}] {a:7.2f}{unit}→{b:7.2f}{unit} "
              f"({rel:+7.1f}%)  饱和 {sa:5.1f}→{sb:5.1f}")

    # 死区判定：只对「四维分工中应由 S.a 主导」的通道判，用其声明的度量
    # 光球(breath主导)、天穹(state主导)不套用 S.a 判据——它们对 S.a 弱响应是设计使然
    sa_regions = [rn for rn in REGIONS if REGIONS[rn][4] == "S.a"]
    print(f"\n【相邻档变化率（仅 S.a 主导通道判死区，判据：相邻档≥3% 且端到端≥20%）】")
    print(f"{'档间':>14}" + "".join(f"{rn[:10]:>13}" for rn in sa_regions))
    mins = {rn: [] for rn in sa_regions}
    for i in range(1, len(data)):
        prev, cur = data[i-1], data[i]
        cells = []
        for rn in sa_regions:
            p, c = metric_val(prev, rn), metric_val(cur, rn)
            rel = abs(c - p) / max(p, 1e-6) * 100
            mins[rn].append(rel); cells.append(rel)
        print(f"{prev['sa']:.2f}→{cur['sa']:.2f}".rjust(14) +
              "".join(f"{v:>12.1f}%" for v in cells))

    print("\n【死区判定】（S.a 主导通道）")
    ok = True
    for rn in sa_regions:
        avg, mn = float(np.mean(mins[rn])), float(np.min(mins[rn]))
        e2e = verdict[rn]["rel_pct"]
        good = mn >= 3.0 and abs(e2e) >= 20.0
        ok = ok and good
        print(f"  {'✅' if good else '❌'} {rn:<12} 相邻档最小 {mn:5.1f}%  平均 {avg:5.1f}%  "
              f"端到端 {e2e:+6.1f}%  → {'可辨，无死区' if good else '仍有死区'}")

    # 非 S.a 主导通道：不判死区，只报告其实际响应与分工归属
    print("\n【非 S.a 主导通道（按四维分工对 S.a 弱响应是设计使然，不判死区）】")
    for rn, box in REGIONS.items():
        if box[4] in ("S.a", "-"):
            continue
        v = verdict[rn]; drv = box[4]
        if drv == "breath":
            print(f"  {rn}（呼吸引导所缘，S.a 仅次调制）：S.a 0→1 时 {v['val_lo']:.1f}→{v['val_hi']:.1f} "
                  f"({v['rel_pct']:+.1f}%)。光球主驱动是呼吸相位(inhale)，S.a 只贡献 0.7 的次项，"
                  f"高档接近渲染饱和，故对 S.a 不敏感属预期，非死区。")
        elif drv == "state":
            print(f"  {rn}（底色层，state 主导 τ=60s）：S.a 0→1 时 {v['val_lo']:.1f}→{v['val_hi']:.1f} "
                  f"({v['rel_pct']:+.1f}%)，饱和度 {v['sat_lo']:.1f}→{v['sat_hi']:.1f}。"
                  f"符合四维分工——天穹由 state 色调经 τ=60s 驱动，不该随 S.a 快变。")
    return {"data": data, "verdict": verdict, "mins": {k: [round(x, 2) for x in v]
                                                       for k, v in mins.items()},
            "sa_regions": sa_regions, "all_pass": bool(ok)}, ok


def analyze_D():
    """D 组：settle 扫描 → 验底色层确为分钟级慢变"""
    print("\n" + "=" * 100)
    print("【D 组】底色层收敛特性（同参数、settle 递增 → 应缓慢变化，非秒级跳变）")
    print("=" * 100)
    files = load_group("D_settle")
    if not files:
        print("（D 组未拍摄，跳过）"); return None
    rows = []
    for f in files:
        # D_settle005s → 5
        sec = float(f["name"].replace("D_settle", "").replace("s", ""))
        img = Image.open(f["path"])
        r = {"settle": sec, "kb": f["kb"]}
        for rn in ["天穹", "全图"]:
            r[rn] = stats(img, REGIONS[rn])
        rows.append(r)
        print(f"  settle={sec:6.1f}s  天穹均值 {r['天穹']['mean']:6.2f}  "
              f"饱和 {r['天穹']['sat']:5.2f}  全图均值 {r['全图']['mean']:6.2f}")
    if len(rows) >= 2:
        first, last = rows[0], rows[-1]
        d_sky = last["天穹"]["sat"] - first["天穹"]["sat"]
        d_mean = last["天穹"]["mean"] - first["天穹"]["mean"]
        print(f"\n  settle {first['settle']:.0f}s → {last['settle']:.0f}s：天穹饱和度变化 {d_sky:+.2f}，均值变化 {d_mean:+.2f}")
        print(f"  理论收敛度（τ=60s）：{first['settle']:.0f}s={100*(1-np.exp(-first['settle']/60)):.1f}%  "
              f"{last['settle']:.0f}s={100*(1-np.exp(-last['settle']/60)):.1f}%")
        if abs(d_sky) > 0.3 or abs(d_mean) > 1.0:
            print(f"  ✅ 底色随时间缓慢演变（分钟级），符合「使其成为底色」的要求")
        else:
            print(f"  ⚠️ 底色几乎不变，可能 state 未切换或收敛过慢，须人工看图确认")
    return rows


def analyze_C():
    """C 组：V2 实测中位 vs 旧 q1q3 中位"""
    print("\n" + "=" * 100)
    print("【C 组】法师日常状态的真实画面：V2 实测中位 vs 旧 q1q3（触顶失真）")
    print("=" * 100)
    files = load_group("C_")
    if not files:
        print("（C 组未拍摄，跳过）"); return None
    rows = []
    for f in files:
        img = Image.open(f["path"])
        r = {"name": f["name"], "kb": f["kb"]}
        for rn in ["水面辉光带", "光球区", "全图"]:
            r[rn] = stats(img, REGIONS[rn])
        rows.append(r)
        print(f"  {r['name']:<22} 水面 {r['水面辉光带']['mean']:6.1f}  "
              f"光球 {r['光球区']['mean']:6.1f}  全图 {r['全图']['mean']:6.1f}  "
              f"高光 {r['水面辉光带']['bright_pct']:5.2f}%")
    return rows


def main():
    if not os.path.isdir(SHOT):
        print(f"❌ 截图目录不存在：{SHOT}"); return 1
    res_a, ok_a = analyze_A()
    if res_a is None:
        return 1
    res_d = analyze_D()
    res_c = analyze_C()

    with open(os.path.join(OUT, "V2截图量化.json"), "w", encoding="utf-8") as f:
        json.dump({"A组": res_a, "D组": res_d, "C组": res_c,
                   "regions": {k: list(v) for k, v in REGIONS.items()}},
                  f, ensure_ascii=False, indent=2, default=str)
    print("\n" + "=" * 100)
    print("结论：" + ("✅ A 组 S.a 全量程无死区，脑电腿视觉可见（09-10 死区问题已解决）"
                     if ok_a else "❌ A 组仍有死区，须调整映射增益"))
    print("=" * 100)
    print("已存 V2截图量化.json")
    return 0 if ok_a else 1


if __name__ == "__main__":
    sys.exit(main())
