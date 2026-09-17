"""第二重：VR 场景受控状态截图采集（2026-09-10）

用本机 Edge 无头（WebGL 已验证可渲染）对 V1 模板做受控截图。
注入参数走 vr_feedback.html 的 INJ 钩子（仅 URL 带参生效，默认零影响）。

截图矩阵：
  R 代表性状态 × 2 呼吸相位（吸气顶点 breath=π/2 / 呼气谷点 breath=3π/2）
    - 安定高 S.a=0.90 S.th=0.10 态=静
    - 中性   S.a=0.50 S.th=0.50 态=专注
    - 昏沉   S.a=0.20 S.th=0.80 态=昏
  M 法师实测落点（第一重分析中位）× 2 呼吸相位
    - 会话A S.a=0.170 S.th=0.666 态=专注
    - 会话B S.a=0.034 S.th=0.522 态=专注
  C 标定对照：同一份原始 relα=0.0350（合并中位）在当前 CAL 与三种重标定下的 S.a
    - 当前   S.a=0.080
    - 建议p5p95 S.a≈0.202   建议q1q3 S.a≈0.370
  V V1 基线：不带任何参数（真实连接+真实呼吸节奏），对照组
"""
import os
import subprocess
import time

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
BASE = "http://127.0.0.1:8777/vr"
OUT = r"C:\Users\tiand\OneDrive\zhiguanAI\output\20260910_VR标准模板三重分析\截图"

INHALE = 1.5708    # π/2 → sin=1 吸气顶点
EXHALE = 4.7124    # 3π/2 → sin=-1 呼气谷点

CASES = [
    # (文件名, fix_a, fix_th, state, breath)
    ("R1_安定高_吸气", 0.90, 0.10, "静", INHALE),
    ("R1_安定高_呼气", 0.90, 0.10, "静", EXHALE),
    ("R2_中性_吸气",   0.50, 0.50, "专注", INHALE),
    ("R2_中性_呼气",   0.50, 0.50, "专注", EXHALE),
    ("R3_昏沉_吸气",   0.20, 0.80, "昏", INHALE),
    ("R3_昏沉_呼气",   0.20, 0.80, "昏", EXHALE),
    ("M_会话A实测_吸气", 0.170, 0.666, "专注", INHALE),
    ("M_会话A实测_呼气", 0.170, 0.666, "专注", EXHALE),
    ("M_会话B实测_吸气", 0.034, 0.522, "专注", INHALE),
    ("M_会话B实测_呼气", 0.034, 0.522, "专注", EXHALE),
    ("C_当前CAL_吸气",   0.080, 0.579, "专注", INHALE),
    ("C_建议p5p95_吸气", 0.202, 0.579, "专注", INHALE),
    ("C_建议q1q3_吸气",  0.370, 0.579, "专注", INHALE),
]


def shot(name, params, budget=15000, w=1280, h=720):
    url = BASE + "?" + "&".join(params)
    png = os.path.join(OUT, name + ".png")
    cmd = [EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars",
           f"--window-size={w},{h}", f"--virtual-time-budget={budget}",
           f"--screenshot={png}", url]
    r = subprocess.run(cmd, capture_output=True, timeout=120)
    ok = os.path.exists(png)
    sz = os.path.getsize(png) if ok else 0
    print(f"{'OK ' if ok else 'FAIL'} {name:22s} {sz/1024:6.1f}KB  {url}")
    return ok, sz


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, a, th, state, br in CASES:
        p = [f"fix_a={a}", f"fix_th={th}", f"state={state}",
             f"breath={br:.4f}", "wt=8.0", "autoload=1"]
        shot(name, p)
        time.sleep(0.5)
    # V1 基线：无注入参数，真实连接真实呼吸
    shot("V_V1基线_无注入", ["autoload=1"], budget=18000)
    print("\n截图完成 →", OUT)


if __name__ == "__main__":
    main()
