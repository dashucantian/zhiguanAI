"""读取第一重分析结果，计算 CAL 重标定建议值，并绘制全部图表。"""
import json
import os

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = r"C:\Users\tiand\OneDrive\zhiguanAI\output\20260910_VR标准模板三重分析"
FIG = os.path.join(OUT, "图")
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

d = json.load(open(os.path.join(OUT, "第一重_脑电分析数据.json"), encoding="utf-8"))
m = d["merged"]
cal = d["cal"]

print("=== 合并分布（两会话非噪声 epoch）===")
for k in ["rel_alpha", "lt", "S_a", "S_th"]:
    s = m[k]
    print(f"{k:10s} n={s['n']:4d} min={s['min']:.4f} p5={s['p5']:.4f} q1={s['q1']:.4f} "
          f"med={s['median']:.4f} q3={s['q3']:.4f} p95={s['p95']:.4f} max={s['max']:.4f}")

print(f"\n当前 CAL: relALo={cal['relALo']} relASpan={cal['relASpan']}  "
      f"→ relα 映射区间 [{cal['relALo']:.4f}, {cal['relALo']+cal['relASpan']:.4f}]")
print(f"          ltBLo={cal['ltBLo']} ltBSpan={cal['ltBSpan']}  "
      f"→ lt 映射区间 [{cal['ltBLo']:.4f}, {cal['ltBLo']+cal['ltBSpan']:.4f}]")

ra = m["rel_alpha"]
lt = m["lt"]
for name, lo, hi in [("p5~p95", ra["p5"], ra["p95"]), ("q1~q3", ra["q1"], ra["q3"]),
                     ("min~max", ra["min"], ra["max"])]:
    print(f"重标定 relA [{name}]: Lo={lo:.4f} Span={hi-lo:.4f}")
for name, lo, hi in [("p5~p95", lt["p5"], lt["p95"]), ("q1~q3", lt["q1"], lt["q3"]),
                     ("min~max", lt["min"], lt["max"])]:
    print(f"重标定 ltB  [{name}]: Lo={lo:.4f} Span={hi-lo:.4f}")

# 保存重标定建议
sugg = {
    "current": cal,
    "merged_distribution": {k: m[k] for k in ["rel_alpha", "lt", "S_a", "S_th"]},
    "relA_candidates": {n: {"Lo": float(m["rel_alpha"][a]), "Span": float(m["rel_alpha"][b] - m["rel_alpha"][a])}
                        for n, a, b in [("p5_p95", "p5", "p95"), ("q1_q3", "q1", "q3"), ("min_max", "min", "max")]},
    "ltB_candidates": {n: {"Lo": float(m["lt"][a]), "Span": float(m["lt"][b] - m["lt"][a])}
                       for n, a, b in [("p5_p95", "p5", "p95"), ("q1_q3", "q1", "q3"), ("min_max", "min", "max")]},
}
json.dump(sugg, open(os.path.join(OUT, "CAL重标定建议.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("\n已写 CAL重标定建议.json")
