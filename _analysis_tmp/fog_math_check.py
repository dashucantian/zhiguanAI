"""S2 雾场通道 · 幅度反解（AI-005，2026-09-17）

用途：把"雾呼吸该给多大幅度"从感觉变成算式。
FogExp2 的剩余可见度 T = exp(-(rho*d)^2)。以**最远可见层的透过率峰谷摆幅**
为设计量，反解所需的 rho 半幅，并检查近/中/远各层是否同步可见
（若只有远处变、近处不动，读起来会是"背景在闪"而不是"空间在呼吸"）。

用法：python fog_math_check.py
"""
import math

CAM = [0.0, 1.6, 3.2]          # s1 相机位置
FAR_Z = -9.6                   # s1 大地层最外环半径（rings 9.6）
BASE = 0.022                   # s1 雾基准密度
LAYERS = {"内环": 4.522, "中环": 9.214, "大地原点": 3.569}


def T(rho, d):
    return math.exp(-((rho * d) ** 2))


def main():
    far = math.dist(CAM, [0.0, 0.02, FAR_Z])
    print(f"最远可见点距离 = {far:.3f} m（大地层 z={FAR_Z}，离眼 {math.hypot(1.58, 12.8):.3f} m）")
    print(f"基准 rho = {BASE} → 该点透过率 {T(BASE, far):.4f}")
    print()
    print("幅度反解（以最远可见点的透过率峰谷为设计量）：")
    for d in (0.003, 0.004, 0.005, 0.0066, 0.008, 0.010):
        lo, hi = T(BASE - d, far), T(BASE + d, far)
        print(f"  Δrho=±{d:.4f} → rho∈[{BASE-d:.4f},{BASE+d:.4f}]"
              f" · 透过率 {lo:.4f}~{hi:.4f} · 峰谷 {(hi-lo)*100:5.1f} pp")
    print()
    print("各层同步性检查（看是否只有远处在变）：")
    for rho in (BASE - 0.0066, BASE, BASE + 0.0066):
        vals = " · ".join(f"{k} {T(rho, v):.3f}" for k, v in LAYERS.items())
        print(f"  rho={rho:.4f}: {vals} · 最远 {T(rho, far):.3f}")
    print()
    print("结论提示：若选定 Δrho，则各层透过率的峰谷应同号、且近层摆幅明显小于远层"
          "（这正是大气透视的应有表现，不是缺陷）。")


if __name__ == "__main__":
    main()
