"""受控截图（CDP 实时控制版，2026-09-10 建，2026-09-11 扩展 V2 档位集）

为什么不用 --virtual-time-budget：虚拟时钟会冻结真实网络请求，
28MB 模型的 fetch+GLTF 解析是真实 IO/CPU 工作，在虚拟时间里永远等不到完成
（实测 15s/90s 预算模型都不载入，DOM 里 msg 为空卡在第一个 await）。

本脚本用 Chrome DevTools Protocol 实时驱动：
  1. 起一个带 --remote-debugging-port 的无头 Edge；
  2. 对每个用例 Page.navigate 到注入 URL；
  3. 真实轮询页面 #msg 文本，直到出现「模型已载入」（或「载入失败」）；
  4. 等 settle 秒让渲染稳定后 Page.captureScreenshot。
不修改 vr_feedback.html 的任何时序逻辑，注入仍走 INJ 钩子。

用法：
  python cdp_shoot.py                       # 默认 v1 集 → 截图/（历史行为不变）
  python cdp_shoot.py --set v2              # v2 集 → 截图_V2/
  python cdp_shoot.py --set v2 --no-model   # 跳过28MB模型，快出图（验参数分布用）
  python cdp_shoot.py --set v2 --only D_    # 只跑 settle 扫描组

═══ 2026-09-11 扩展（V2 步骤5）═══
新增 --set v2 档位集，输出到 **截图_V2/** 独立目录。
V1 历史截图是三重分析的证据链，**绝不覆盖**，故默认仍跑 v1 集、输出原目录。

⚠️ V1↔V2 截图的可比性边界（诚实声明，勿误读）：
  INJ 注入态下 S.a = INJ.a 是**直接赋值、不经 EMA**，故同一 settle 时间内
  S.a 档间严格可比 —— 这是本工具的核心用途（A/B/C 组）。
  但**底色层 curCol 的收敛速度 V1≠V2**：V1 为 lerp(.04)/帧（τ≈0.41s，10s 内
  100% 收敛），V2 为 τ=60s（10s 仅收敛 15.4%）。故 V1/V2 截图的**色相不可
  直接比对**，只有 S.a 驱动的亮度/透明度通道可比。
  V2「底色是分钟级慢变」这一特性由 D 组 settle 扫描单独验证。
  V1↔V2 的时间连续性（闪 vs 连绵）由 verify_continuity.py 量化 —— 静态截图
  本就无法验证时间维度现象，这是方法论边界，不是工具缺陷。
"""
import argparse
import asyncio
import base64
import json
import os
import subprocess
import sys
import time

import websockets

EDGE = next((p for p in [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]
    if os.path.exists(p)),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
BASE = "http://127.0.0.1:8777/vr"
SHOT_ROOT = r"C:\Users\tiand\OneDrive\zhiguanAI\output\20260910_VR标准模板三重分析"
PORT = 9333

INHALE = 1.5708
EXHALE = 4.7124

# 元组：(名称, fix_a, fix_th, state, breath, settle秒)
# ══════════ V1 档位集（历史行为，输出 截图/，勿改勿覆盖）══════════
CASES_V1 = [
    ("R1_安定高_吸气", 0.90, 0.10, "静", INHALE, 1.5),
    ("R1_安定高_呼气", 0.90, 0.10, "静", EXHALE, 1.5),
    ("R2_中性_吸气",   0.50, 0.50, "专注", INHALE, 1.5),
    ("R2_中性_呼气",   0.50, 0.50, "专注", EXHALE, 1.5),
    ("R3_昏沉_吸气",   0.20, 0.80, "昏", INHALE, 1.5),
    ("R3_昏沉_呼气",   0.20, 0.80, "昏", EXHALE, 1.5),
    ("M_会话A实测_吸气", 0.170, 0.666, "专注", INHALE, 1.5),
    ("M_会话A实测_呼气", 0.170, 0.666, "专注", EXHALE, 1.5),
    ("M_会话B实测_吸气", 0.034, 0.522, "专注", INHALE, 1.5),
    ("M_会话B实测_呼气", 0.034, 0.522, "专注", EXHALE, 1.5),
    ("C_当前CAL_吸气",   0.080, 0.579, "专注", INHALE, 1.5),
    ("C_建议p5p95_吸气", 0.202, 0.579, "专注", INHALE, 1.5),
    ("C_建议q1q3_吸气",  0.370, 0.579, "专注", INHALE, 1.5),
    ("V_V1基线_无注入",  None, None, None, None, 1.5),
]

# ══════════ V2 档位集（输出 截图_V2/）══════════
# A 组：S.a 全量程扫描。验「脑电腿是否真的可见」——V2 的核心目标，也是 09-10
#   三重分析发现的死区问题（旧标定下 S.a 贴底 0.08 致视觉不可见）。
#   同 state、同 settle，S.th 固定 0.5 以隔离 S.a 单一变量 → 档间严格可比。
# B 组：状态档 × 呼吸相位，沿用 V1 的 R 组参数 → 可比对**亮度/透明度通道**
#   （色相不可比，见文件头声明）。
# C 组：V2 三段真机在新算法下的实测 S.a 中位（verify_continuity.py 产出：
#   A=0.382 / B=0.503 / C=0.445）→ 法师日常状态下画面的真实样子；
#   并列旧 q1q3 的中位（0.753/0.996，触顶致失真）作对照。
# D 组：settle 扫描（同参数、等待时间递增）→ 验证底色层确为分钟级慢变，
#   而非 V1 的秒级跳变。这是「使其成为底色」的直接视觉证据。
CASES_V2 = [
    # A 组：S.a 全量程（S.th 固定 0.5 隔离变量）
    ("A_Sa0.00_量程底",   0.00, 0.50, "专注", INHALE, 8.0),
    ("A_Sa0.20_量程低",   0.20, 0.50, "专注", INHALE, 8.0),
    ("A_Sa0.40_量程中下", 0.40, 0.50, "专注", INHALE, 8.0),
    ("A_Sa0.50_量程中",   0.50, 0.50, "专注", INHALE, 8.0),
    ("A_Sa0.60_量程中上", 0.60, 0.50, "专注", INHALE, 8.0),
    ("A_Sa0.80_量程高",   0.80, 0.50, "专注", INHALE, 8.0),
    ("A_Sa1.00_量程顶",   1.00, 0.50, "专注", INHALE, 8.0),
    # B 组：状态档 × 呼吸（与 V1 R 组同参，比对亮度通道）
    ("B_安定高_吸气",     0.90, 0.10, "静", INHALE, 8.0),
    ("B_安定高_呼气",     0.90, 0.10, "静", EXHALE, 8.0),
    ("B_中性_吸气",       0.50, 0.50, "专注", INHALE, 8.0),
    ("B_中性_呼气",       0.50, 0.50, "专注", EXHALE, 8.0),
    ("B_昏沉_吸气",       0.20, 0.80, "昏", INHALE, 8.0),
    ("B_昏沉_呼气",       0.20, 0.80, "昏", EXHALE, 8.0),
    # C 组：V2 真机实测中位 vs 旧 q1q3 中位（失真对照）
    ("C_V2实测_会话A中位", 0.382, 0.579, "专注", INHALE, 8.0),
    ("C_V2实测_会话B中位", 0.503, 0.579, "专注", INHALE, 8.0),
    ("C_V2实测_会话C中位", 0.445, 0.579, "专注", INHALE, 8.0),
    ("C_旧q1q3_会话A中位", 0.753, 0.579, "专注", INHALE, 8.0),
    ("C_旧q1q3_会话C中位", 0.996, 0.579, "专注", INHALE, 8.0),
    # D 组：settle 扫描（同参数，等待时间递增）→ 验底色分钟级慢变
    ("D_settle005s",      0.50, 0.50, "静", INHALE, 5.0),
    ("D_settle030s",      0.50, 0.50, "静", INHALE, 30.0),
    ("D_settle060s",      0.50, 0.50, "静", INHALE, 60.0),
    ("D_settle180s",      0.50, 0.50, "静", INHALE, 180.0),
    # 基线：无注入（走真实算法路径，S.a 应为中性 0.5）
    ("V_V2基线_无注入",   None, None, None, None, 8.0),
]

SETS = {
    "v1": (CASES_V1, os.path.join(SHOT_ROOT, "截图")),
    "v2": (CASES_V2, os.path.join(SHOT_ROOT, "截图_V2")),
}


def build_url(a, th, state, br, with_model=True):
    """构造注入 URL。with_model=False 时不带 autoload=1，跳过 28MB 模型载入。"""
    if a is None:
        return BASE + ("?autoload=1" if with_model else "")
    p = [f"fix_a={a}", f"fix_th={th}", f"state={state}",
         f"breath={br:.4f}", "wt=8.0"]
    if with_model:
        p.append("autoload=1")
    return BASE + "?" + "&".join(p)


async def wait_model_ready(ws, mid, timeout=90.0):
    """真实轮询 #msg 文本直到模型加载结论出现。"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        await ws.send(json.dumps({"id": mid, "method": "Runtime.evaluate",
                                  "params": {"expression":
                                      "(document.getElementById('msg')||{}).textContent||''"}}))
        msg = await ws.recv()
        d = json.loads(msg)
        if d.get("id") == mid:
            txt = (d.get("result", {}).get("result", {}).get("value") or "")
            if "模型已载入" in txt:
                return True, txt
            if "载入失败" in txt or "加载异常" in txt:
                return False, txt
        await asyncio.sleep(0.4)
    return False, "超时未等到模型加载结论"


async def shoot_case(ws, name, url, mid_base, outdir, settle=1.5, with_model=True):
    await ws.send(json.dumps({"id": mid_base, "method": "Page.enable"}))
    await ws.recv()
    await ws.send(json.dumps({"id": mid_base + 1, "method": "Page.navigate",
                              "params": {"url": url}}))
    # 排空 navigate 响应
    while True:
        m = json.loads(await ws.recv())
        if m.get("id") == mid_base + 1:
            break
    if with_model:
        ok, txt = await wait_model_ready(ws, mid_base + 2)
    else:
        ok, txt = True, "跳过模型"
    await asyncio.sleep(settle)      # 渲染稳定 / 底色层收敛
    await ws.send(json.dumps({"id": mid_base + 3, "method": "Page.captureScreenshot",
                              "params": {"format": "png"}}))
    data = None
    while True:
        m = json.loads(await ws.recv())
        if m.get("id") == mid_base + 3:
            data = m.get("result", {}).get("data")
            break
    png = os.path.join(outdir, name + ".png")
    if data:
        with open(png, "wb") as f:
            f.write(base64.b64decode(data))
    sz = os.path.getsize(png) / 1024 if data and os.path.exists(png) else 0
    print(f"{'OK ' if data else 'FAIL'} {name:24s} settle={settle:5.1f}s "
          f"模型={'载入' if ok else '未:' + txt[:18]}  {sz:.1f}KB", flush=True)
    return data is not None, sz


async def main():
    ap = argparse.ArgumentParser(description="VR 场景受控截图")
    ap.add_argument("--set", choices=["v1", "v2"], default="v1",
                    help="档位集：v1=历史三重分析用（默认），v2=本轮 V2 验证")
    ap.add_argument("--no-model", action="store_true",
                    help="跳过 28MB 3D 模型载入（快出图，仅验参数分布）")
    ap.add_argument("--only", type=str, default=None,
                    help="只跑名称含该子串的用例（如 --only D_ 只跑 settle 扫描）")
    args = ap.parse_args()

    cases, outdir = SETS[args.set]
    with_model = not args.no_model
    if args.only:
        cases = [c for c in cases if args.only in c[0]]
        if not cases:
            print(f"❌ --only '{args.only}' 无匹配用例")
            return 1
    os.makedirs(outdir, exist_ok=True)

    print("=" * 80)
    print(f"受控截图：档位集 {args.set}  →  {outdir}")
    print(f"用例 {len(cases)} 个 | 模型载入 {'是' if with_model else '否（快出图）'}")
    print("=" * 80, flush=True)

    proc = subprocess.Popen(
        [EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars",
         "--window-size=1280,720", f"--remote-debugging-port={PORT}",
         "--autoplay-policy=no-user-gesture-required", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    import urllib.request
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version",
                                        timeout=2) as r:
                json.load(r)
            break
        except Exception:
            await asyncio.sleep(0.5)
    else:
        proc.kill()
        print("❌ 调试端口未就绪")
        return 1

    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=5) as r:
        targets = json.load(r)
    page = next(t for t in targets if t["type"] == "page")

    results = []
    async with websockets.connect(page["webSocketDebuggerUrl"],
                                  max_size=60 * 1024 * 1024) as ws:
        for i, c in enumerate(cases):
            name, a, th, state, br, settle = c
            url = build_url(a, th, state, br, with_model)
            ok, sz = await shoot_case(ws, name, url, 1000 + i * 10,
                                      outdir, settle, with_model)
            results.append({"name": name, "ok": ok, "kb": round(sz, 1),
                            "settle": settle, "fix_a": a, "fix_th": th,
                            "state": state, "breath": br, "url": url})
    proc.kill()

    n_ok = sum(1 for r in results if r["ok"])
    small = [r for r in results if r["ok"] and r["kb"] < 25]
    print("\n" + "=" * 80)
    print(f"完成：{n_ok}/{len(results)} 张成功 → {outdir}")
    if small:
        print(f"⚠️ {len(small)} 张 <25KB，疑似黑屏/纯色，须人工确认：")
        for r in small:
            print(f"     {r['name']} ({r['kb']}KB)")
    meta = os.path.join(outdir, "_截图元数据.json")
    with open(meta, "w", encoding="utf-8") as f:
        json.dump({
            "set": args.set, "with_model": with_model,
            "note": "INJ注入态S.a直接赋值不经EMA，档间严格可比；但底色curCol收敛速度"
                    "V1(τ≈0.41s)≠V2(τ=60s)，故色相不可跨版本比对，只可比亮度/透明度通道",
            "shots": results}, f, ensure_ascii=False, indent=2)
    print(f"元数据 → {meta}")
    print("=" * 80)
    return 0 if n_ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
