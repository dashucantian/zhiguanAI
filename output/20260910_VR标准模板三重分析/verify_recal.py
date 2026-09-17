"""q1q3 重标定验证：从 vr_feedback.html 读回实际写入的 CAL，套合并分布 rel_alpha
七分位核算新 S.a 映射，与旧标定实测分布对比，确认脑电死区是否消除。"""
import json, os, re

BASE = r"C:\Users\tiand\OneDrive\zhiguanAI"
OUT = os.path.join(BASE, "output", "20260910_VR标准模板三重分析")
HTML = os.path.join(BASE, "vr_feedback.html")

# 1) 读回实际写入的标定值（configuration-level read-back，验证的是文件真实状态）
html = open(HTML, encoding="utf-8").read()
m = re.search(r"relALo:\s*([\d.]+),\s*relASpan:\s*([\d.]+)", html)
LO, SPAN = float(m.group(1)), float(m.group(2))
fb = float(re.search(r"relAFallback:\s*([\d.]+)", html).group(1))
print(f"[读回] vr_feedback.html 实际标定 relALo={LO} relASpan={SPAN} relAFallback={fb}")

# 2) 合并分布 rel_alpha 七分位（n=679，两段真机 22min+42min）
d = json.load(open(os.path.join(OUT, "CAL重标定建议.json"), encoding="utf-8"))
ra = d["merged_distribution"]["rel_alpha"]
old = d["current"]
sa_old_meas = d["merged_distribution"]["S_a"]

clamp01 = lambda x: max(0.0, min(1.0, x))
sa = lambda v, lo, sp: clamp01((v - lo) / sp)

pts = ["min", "p5", "q1", "median", "q3", "p95", "max"]
print(f"\n{'分位':<7}{'rel_alpha':>11}{'旧S.a(p5p95)':>14}{'新S.a(q1q3)':>13}")
for p in pts:
    v = ra[p]
    print(f"{p:<7}{v:>11.4f}{sa(v, old['relALo'], old['relASpan']):>14.3f}{sa(v, LO, SPAN):>13.3f}")

# 3) 核心结论
new_med = sa(ra["median"], LO, SPAN)
print(f"\n[核心] 中位 S.a：旧实测 {sa_old_meas['median']:.3f} -> 新 {new_med:.3f}（x{new_med/sa_old_meas['median']:.1f}）")
print(f"[展开] IQR：旧实测 [{sa_old_meas['q1']:.3f},{sa_old_meas['q3']:.3f}] -> 新 [{sa(ra['q1'],LO,SPAN):.3f},{sa(ra['q3'],LO,SPAN):.3f}]")
print(f"[fallback] 断流中性值 {fb} -> S.a={sa(fb,LO,SPAN):.3f}（应约等于中位0.37，而非触顶1.0）")
print(f"[警示] rel_alpha>={LO+SPAN:.4f}(q3) 即触顶；实测 p95={ra['p95']:.4f} 已超，约5%+时段满亮")
