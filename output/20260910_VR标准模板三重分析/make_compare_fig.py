"""拼接视觉对照图：把受控截图按「参数↔视觉」排成对照面板。"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.image import imread

OUT = r"C:\Users\tiand\OneDrive\zhiguanAI\output\20260910_VR标准模板三重分析"
SHOT = os.path.join(OUT, "截图")
FIG = os.path.join(OUT, "图")
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# 面板：(文件, 标题含关键参数)
PANELS = [
    ("R1_安定高_吸气.png",   "① 安定高 S.a=0.90 吸气顶点\n亮度3.03 光色#85CFCB 水面辉光0.92"),
    ("R1_安定高_呼气.png",   "② 安定高 S.a=0.90 呼气谷点\n亮度1.33 光色#3FAE8C 球径0.134m"),
    ("M_会话A实测_吸气.png", "③ 法师会话A实测中位 S.a=0.170\n亮度2.52 水面辉光0.34（量程34%）"),
    ("M_会话B实测_吸气.png", "④ 法师会话B实测中位 S.a=0.034\n亮度2.42 水面辉光0.23（量程8%·近死区）"),
    ("R3_昏沉_吸气.png",     "⑤ 昏沉 S.a=0.20 S.th=0.80\n雾密度0.044 粒子0.46 偏紫"),
    ("V_V1基线_无注入.png",  "⑥ V1 基线（无注入·真实连接）\n法师实机所见状态"),
]


def main():
    fig, axes = plt.subplots(2, 3, figsize=(21, 12))
    for ax, (fn, title) in zip(axes.flat, PANELS):
        p = os.path.join(SHOT, fn)
        if os.path.exists(p):
            ax.imshow(imread(p))
        ax.set_title(title, fontsize=11)
        ax.axis("off")
    fig.suptitle("图6  参数与视觉 受控对照面板（同 V1 模板、同水面时刻 wt=8，仅参数不同）\n"
                 "①②示呼吸双相位差异（球径/亮度/光色）；③④示法师真实落点 vs 高安定态的视觉落差；"
                 "⑤示昏沉态雾与色调；⑥为无注入基线",
                 fontsize=14, y=0.995)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "图6_参数视觉对照面板.png"), dpi=110, bbox_inches="tight")
    plt.close(fig)
    print("图6 完成")


if __name__ == "__main__":
    main()
