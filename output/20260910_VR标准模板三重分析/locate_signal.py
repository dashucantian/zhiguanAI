"""定位 S.a 信号在画面中的真实落点（数据驱动，不靠猜分区）

上一版 analyze_shots.py 报「天穹区存在死区」，但核查 shader 发现是**分区定义错误**：
  sky 的 uGlow 项 = pow(max(0,1-abs(h-.16)*4),3)*uGlow*.6
  → 只作用于 h≈0.16 的窄带（地平线附近），而我量的「上1/3」是大片区域，
    把窄带信号稀释掉了。与本轮此前 4 个判据 bug 同源：拿假设区域套真实物理位置。

故改用逐行/逐列亮度差剖面，让信号自己显示落在哪，再据此重定分区。
"""
import os, sys, json
import numpy as np
from PIL import Image

OUT = r"C:\Users\tiand\OneDrive\zhiguanAI\output\20260910_VR标准模板三重分析"
SHOT = os.path.join(OUT, "截图_V2")

lo = np.asarray(Image.open(os.path.join(SHOT, "A_Sa0.00_量程底.png")).convert("L"), dtype=float)
hi = np.asarray(Image.open(os.path.join(SHOT, "A_Sa1.00_量程顶.png")).convert("L"), dtype=float)
d = hi - lo
H, W = d.shape
print(f"图像 {W}x{H}，全屏平均差 {d.mean():.2f}，最大差 {d.max():.1f}\n")

NB = 24
print("【逐行亮度差剖面】（S.a 0.00→1.00）")
print(f"{'行区间':<16}{'屏幕y比例':<16}{'平均差':>9}{'最大差':>9}")
rows = []
for i in range(0, H, H // NB):
    band = d[i:i + H // NB]
    m = float(band.mean())
    rows.append({"y0": i, "y1": i + H // NB, "frac0": i / H,
                 "mean": m, "max": float(band.max())})
    print(f"{i:4d}-{i+H//NB:<4d}      {i/H:.3f}-{(i+H//NB)/H:.3f}     {m:>8.2f}{band.max():>9.1f}")

top = max(rows, key=lambda r: r["mean"])
print(f"\n信号最强水平带: y={top['y0']}-{top['y1']} (屏幕高度 {top['frac0']:.2f} 处), 平均差 {top['mean']:.2f}")

print("\n【逐列亮度差剖面】")
print(f"{'列区间':<16}{'屏幕x比例':<16}{'平均差':>9}{'最大差':>9}")
cols = []
for j in range(0, W, W // 12):
    band = d[:, j:j + W // 12]
    m = float(band.mean())
    cols.append({"x0": j, "mean": m, "max": float(band.max())})
    print(f"{j:4d}-{j+W//12:<4d}      {j/W:.3f}-{(j+W//12)/W:.3f}     {m:>8.2f}{band.max():>9.1f}")
ctop = max(cols, key=lambda c: c["mean"])
print(f"\n信号最强垂直带: x={ctop['x0']} (屏幕宽 {ctop['x0']/W:.2f} 处), 平均差 {ctop['mean']:.2f}")

# 找光球中心（hi 图最亮的 15x15 邻域均值峰值）
# 不用 scipy.ndimage：该解释器是否有 scipy 未确认，手写盒式均值等价且无依赖
print("\n【光球中心定位】（hi 图最亮 15x15 邻域均值峰值）")
K = 16
# 降采样求块均值定位最亮块（不追求精确均值，只需定位；避免手写 box filter 索引出错）
hb, wb = H // K, W // K
blocks = hi[:hb*K, :wb*K].reshape(hb, K, wb, K).mean(axis=(1, 3))
bi, bj = np.unravel_index(int(np.argmax(blocks)), blocks.shape)
# 块中心换算回原图坐标
cy, cx = bi*K + K//2, bj*K + K//2
idx = (cy, cx)
print(f"  最亮块: 行块{bi} 列块{bj}，块均值 {blocks[bi,bj]:.1f}")
print(f"  最亮区质心: y={idx[0]} (高度 {idx[0]/H:.3f}), x={idx[1]} (宽度 {idx[1]/W:.3f})")

# 水面区：下半部
print("\n【上下半部对比】")
print(f"  上半 (y<{H//2}): 平均差 {d[:H//2].mean():.2f}  最大 {d[:H//2].max():.1f}")
print(f"  下半 (y>{H//2}): 平均差 {d[H//2:].mean():.2f}  最大 {d[H//2:].max():.1f}")

with open(os.path.join(OUT, "信号落点剖面.json"), "w", encoding="utf-8") as f:
    json.dump({"shape": [int(H), int(W)], "rows": rows, "cols": cols,
               "strongest_band": top, "orb_center": [int(idx[0]), int(idx[1])],
               "orb_frac": [round(idx[0]/H, 3), round(idx[1]/W, 3)]},
              f, ensure_ascii=False, indent=2)
print("\n已存 信号落点剖面.json")
