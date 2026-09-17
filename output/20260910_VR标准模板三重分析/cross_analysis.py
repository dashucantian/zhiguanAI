"""第三重：参数 ↔ 视觉 ↔ 脑电 三重对照计算（2026-09-10）

把 vr_feedback.html 的映射公式逐条数值化，形成可审计的对照表：
  光球半径 = 0.28(几何) × 0.6(整体缩放) × (1.0 + 0.20·sin(breath))
  光球亮度 = 0.7 + 1.7·inhale + 0.7·S.a          （inhale=(sin(breath)+1)/2）
  光球光色 = lerp(主题主色, 0xbfeaff, 0.55·inhale)
  水面辉光 uGlow = 0.2 + 0.8·S.a
  雾密度 fog.density = 0.020 + 0.030·S.th
  粒子透明度 = 0.35 + 0.55·S.a
  水面顶点位移幅 = (0.05 + 0.16·S.a) 主波 + 0.03·S.th 次波
主题主色 THEMES：calm 0x3fae8c / focused 0x3f8fae / drowsy 0x7a6fae / active 0xae7a4f / default 0x2f8fb8
"""
import json
import os

OUT = r"C:\Users\tiand\OneDrive\zhiguanAI\output\20260910_VR标准模板三重分析"

THEMES = {
    "静": (0x3F, 0xAE, 0x8C), "专注": (0x3F, 0x8F, 0xAE),
    "昏": (0x7A, 0x6F, 0xAE), "散": (0xAE, 0x7A, 0x4F),
    "default": (0x2F, 0x8F, 0xB8),
}
INHALE_COL = (0xBF, 0xEA, 0xFF)


def hexs(rgb):
    return "#{:02X}{:02X}{:02X}".format(*[int(round(c)) for c in rgb])


def lerp(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def visual_row(sa, sth, theme, inhale):
    """给定 S.a/S.th/主题/呼吸相位，算全部视觉量。"""
    pulse = 1.0 + 0.20 * (2 * inhale - 1)          # sin(breath)=2*inhale-1
    radius = 0.28 * 0.6 * pulse
    bright = 0.7 + 1.7 * inhale + 0.7 * sa
    base = THEMES.get(theme, THEMES["default"])
    glowcol = lerp(base, INHALE_COL, 0.55 * inhale)
    return {
        "S_a": sa, "S_th": sth, "theme": theme, "inhale": inhale,
        "光球半径_m": round(radius, 4),
        "光球亮度": round(bright, 3),
        "光球光色": hexs(glowcol),
        "水面辉光": round(0.2 + 0.8 * sa, 3),
        "雾密度": round(0.020 + 0.030 * sth, 4),
        "粒子透明度": round(0.35 + 0.55 * sa, 3),
        "水面主波位移": round(0.05 + 0.16 * sa, 4),
        "水面次波位移": round(0.03 * sth, 4),
    }


def main():
    d = json.load(open(os.path.join(OUT, "第一重_脑电分析数据.json"), encoding="utf-8"))
    merged = d["merged"]

    rows = []
    # 代表性状态 × 呼吸双相位
    for theme, sa, sth in [("静", 0.9, 0.1), ("专注", 0.5, 0.5), ("昏", 0.2, 0.8)]:
        for inh, tag in [(1.0, "吸气顶点"), (0.0, "呼气谷点")]:
            r = visual_row(sa, sth, theme, inh)
            r["类别"] = f"代表态·{theme}·{tag}"
            rows.append(r)
    # 法师实测落点 × 双相位
    for lbl, sa, sth in [("会话A实测中位", 0.170, 0.666), ("会话B实测中位", 0.034, 0.522)]:
        for inh, tag in [(1.0, "吸气顶点"), (0.0, "呼气谷点")]:
            r = visual_row(sa, sth, "专注", inh)
            r["类别"] = f"{lbl}·{tag}"
            rows.append(r)
    # CAL 对照（同一 relα=0.0350 在不同标定下的 S.a）
    for lbl, sa in [("当前CAL", 0.080), ("建议p5p95", 0.202), ("建议q1q3", 0.370)]:
        r = visual_row(sa, 0.579, "专注", 1.0)
        r["类别"] = f"标定对照·{lbl}·吸气"
        rows.append(r)

    # 死区量化：法师真实 S.a 落在哪些视觉区间
    sa_dist = merged["S_a"]
    sa_vals = [sa_dist["p5"], sa_dist["q1"], sa_dist["median"], sa_dist["q3"], sa_dist["p95"]]
    dead = []
    for v in sa_vals:
        g = 0.2 + 0.8 * v
        dead.append({"S_a分位": round(v, 3), "水面辉光": round(g, 3),
                     "粒子透明度": round(0.35 + 0.55 * v, 3),
                     "亮度S.a贡献": round(0.7 * v, 3)})

    out = {
        "mapping_formulas": {
            "光球半径": "0.28×0.6×(1+0.20·sin(breath))",
            "光球亮度": "0.7+1.7·inhale+0.7·S.a",
            "光球光色": "lerp(主题色,0xBFEAFF,0.55·inhale)",
            "水面辉光": "0.2+0.8·S.a",
            "雾密度": "0.020+0.030·S.th",
            "粒子透明度": "0.35+0.55·S.a",
            "水面主波": "0.05+0.16·S.a",
            "水面次波": "0.03·S.th",
        },
        "对照表": rows,
        "死区量化": dead,
        "法师实测S_a分布": sa_dist,
    }
    with open(os.path.join(OUT, "第三重_参数视觉对照.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print("=== 参数↔视觉 对照表 ===")
    hdr = f"{'类别':22s} {'S.a':>5s} {'S.th':>5s} {'半径m':>7s} {'亮度':>6s} {'光色':>8s} {'水面辉光':>7s} {'雾':>7s} {'粒子':>5s}"
    print(hdr)
    for r in rows:
        print(f"{r['类别']:22s} {r['S_a']:5.3f} {r['S_th']:5.3f} {r['光球半径_m']:7.4f} "
              f"{r['光球亮度']:6.3f} {r['光球光色']:>8s} {r['水面辉光']:7.3f} "
              f"{r['雾密度']:7.4f} {r['粒子透明度']:5.3f}")
    print("\n=== 死区量化（法师真实 S.a 分位 → 视觉量）===")
    for r in dead:
        print(f"  S.a={r['S_a分位']:.3f} → 水面辉光 {r['水面辉光']:.3f} | 粒子 {r['粒子透明度']:.3f} "
              f"| 亮度S.a项 {r['亮度S.a贡献']:.3f}")
    print("\n=== 关键结论 ===")
    g_lo = 0.2 + 0.8 * sa_dist["p5"]
    g_hi = 0.2 + 0.8 * sa_dist["p95"]
    print(f"法师真实 S.a 从 p5={sa_dist['p5']:.3f} 到 p95={sa_dist['p95']:.3f}：")
    print(f"  水面辉光实际摆动区间 [{g_lo:.3f}, {g_hi:.3f}]（全量程 0.2~1.0）→ 用到了 "
          f"{(g_hi-g_lo)/0.8*100:.0f}% 量程")
    print(f"  而中位 S.a={sa_dist['median']:.3f} 时水面辉光仅 {0.2+0.8*sa_dist['median']:.3f}（量程的 "
          f"{(0.2+0.8*sa_dist['median']-0.2)/0.8*100:.0f}%）")
    print("\n已写 第三重_参数视觉对照.json")


if __name__ == "__main__":
    main()
