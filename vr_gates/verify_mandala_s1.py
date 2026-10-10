# 〔VR 闸正本·2026-09-30 起〕自 output/ 收拢进 vr_gates/（output/* 被 .gitignore 忽略，
#  验收能力本身不入库＝随时可被清盘丢掉）。证据产物仍写 output/（大图不入库）。
# 原位置：output/20260914_W1两项待裁定核查/verify_mandala_s1.py
"""S1 曼荼罗场域运行时验收（CDP 无头 Edge，复用 cdp_shoot.py 范式）

判据（v0.3 §六 S1 ＋ 巡检线教训9：headless SwiftShader 下 canvas 非 0 才算渲染成功）：
  1. 页面加载无 JS 错误（window.__vrErr 为空）
  2. __mandalaDiag 钩子可读且 stage=S1
  3. WebGL canvas 尺寸非 0（软件渲染也算渲染成功）
  4. 截图像素：黑底占比 ≥85%；金色系像素存在且占比 0.3%~15%（金线可见但不刺眼）
  5. 金色像素色相落在色板容差内（R>G>B，暖金方向）
  6. 静态纪律：间隔 2.5s 两帧截图，逐像素平均绝对差 ≤1.0/255（"绝对安静"）
  7. 中心光点存在：画面中央区域有亮于周边的暖色像素

用法：python verify_mandala_s1.py
前置：console_server 已在 8777 运行（/mandala 路由）
产物：output/20260916_曼荼罗S1/ 下 frame1.png frame2.png（供法师与 GPT 对照）
"""
import asyncio
import base64
import json
import math
import os
import subprocess
import sys
import time

EDGE = next((p for p in [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"]
    if os.path.exists(p)), None)
if not EDGE:
    print("FAIL: 未找到 Edge")
    sys.exit(1)

PORT = 9344
URL = "http://127.0.0.1:8777/mandala?variant=s1&breath=off"  # S1 回归锚：显式钉 variant（2026-10-10 C2 乙案后入口缺省已改 v4lotuspond）＋显式关断呼吸（2026-10-01 金口翻 on，照规格 §三.4 复跑）
# 产物落点＝**脚本自己所在的那棵工作树**（AI-005 2026-09-17 修）。
# 原为硬编码 C:\Users\tiand\OneDrive\zhiguanAI\output\…，导致从 D 盘工作树跑验收时
# 截图写进 OneDrive 那棵树——两树权威归属未定前，这是跨树污染源。
# 可用环境变量 MANDALA_OUT 覆盖。
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.environ.get("MANDALA_OUT") or os.path.join(_ROOT, "output", "20260916_曼荼罗S1")
os.makedirs(OUT, exist_ok=True)

fails = []


def check(cond, ok_msg, fail_msg):
    if cond:
        print(f"  ✅ {ok_msg}")
    else:
        print(f"  ❌ {fail_msg}")
        fails.append(fail_msg)


async def cdp(ws_url, sessionless=True):
    import websockets
    return await websockets.connect(ws_url, max_size=64 * 1024 * 1024)


_id = 0


async def send(ws, method, params=None):
    global _id
    _id += 1
    await ws.send(json.dumps({"id": _id, "method": method,
                              "params": params or {}}))
    while True:
        msg = json.loads(await ws.recv())
        if msg.get("id") == _id:
            return msg


async def evaluate(ws, expr):
    r = await send(ws, "Runtime.evaluate",
                   {"expression": expr, "returnByValue": True, "awaitPromise": True})
    res = r.get("result", {}).get("result", {})
    if "value" in res:
        return res["value"]
    return None


async def main():
    print("=" * 70)
    print("S1 曼荼罗场域运行时验收 · CDP 无头 Edge")
    print("=" * 70)

    proc = subprocess.Popen([
        EDGE, "--headless=new", f"--remote-debugging-port={PORT}",
        "--window-size=1280,800", "--use-gl=swiftshader",
        "--enable-unsafe-swiftshader", "--no-first-run",
        "--user-data-dir=" + os.path.join(OUT, "_profile"),
        "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        # 等 DevTools 就绪
        import urllib.request
        targets = None
        # 60×0.5s＝30s（AI-005 09-17：原 15s，实测本机 Edge 冷启动常超时）
        for _ in range(60):
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{PORT}/json", timeout=1) as r:
                    targets = json.loads(r.read())
                break
            except Exception:
                time.sleep(0.5)
        if not targets:
            print("FAIL: Edge DevTools 未就绪")
            return 1
        page = next((t for t in targets if t["type"] == "page"), targets[0])

        import websockets
        ws = await websockets.connect(page["webSocketDebuggerUrl"],
                                      max_size=64 * 1024 * 1024)
        await send(ws, "Page.enable")
        await send(ws, "Runtime.enable")
        await send(ws, "Page.navigate", {"url": URL})

        # 等渲染稳定（无模型加载，2s 足够；再等 load 遮罩移除）
        for _ in range(60):
            await asyncio.sleep(0.5)
            gone = await evaluate(ws, "document.getElementById('load').style.display")
            if gone == "none":
                break
        await asyncio.sleep(2.0)

        print("\n── 判据 1-3：加载与诊断钩子 ─────────────────────────")
        err = await evaluate(ws, "window.__vrErr || ''")
        check(err == "", f"无 JS 错误（__vrErr 为空）", f"JS 错误：{err}")

        diag = await evaluate(ws, "JSON.stringify(window.__mandalaDiag || null)")
        check(diag is not None and diag != "null", "__mandalaDiag 钩子可读",
              "__mandalaDiag 不可读")
        if diag and diag != "null":
            d = json.loads(diag)
            check(d.get("stage") == "S1", f"stage=S1", f"stage 异常：{d.get('stage')}")
            check(d.get("static") is True, "static=true（S1 静态纪律自声明）",
                  "static 非 true")
            layers = d.get("layers", {})
            kk = d.get("k", {})
            expect = {"inner": 8, "middle": 16, "ground": 8}   # Case-M01 §二 ＋ 本判据
            diff = [f"{k} 实际 {layers.get(k)} 瓣（k={kk.get(k)}）≠ 判据 {v} 瓣"
                    for k, v in expect.items() if layers.get(k) != v]
            check(not diff,
                  f"三层瓣数 8/16/8 与参数表一致 {layers}",
                  "层参数不符：" + "；".join(diff)
                  + " —— 几何以 VARIANTS 注册表为准；改几何还是改文档/判据涉义理，"
                    "待法师裁定（见 20260917_曼荼罗场域S2开工前阻塞项与规格订正_请示_v1.md §二）")

            # ── 钩子自述的**独立复算**（AI-005 2026-09-17 加）───────────────
            # 由本次实测事故而来：原钩子把 ground 写死成 8（几何实为 16 瓣），
            # 而判据只看钩子自述 → 该项"PASS"证据不成立。判据不能只信被测对象的自述。
            cam = d.get("cam") or [0, 0, 0]
            for layer in ("inner", "middle", "ground"):
                m = (d.get("depth") or {}).get(layer)
                if not m:
                    continue
                dist2 = math.dist(cam, m.get("pos") or [0, 0, 0])
                ang2 = math.degrees(math.atan2(m.get("rOut", 0), dist2 or 1e-9))
                fog2 = math.exp(-((d.get("fog", 0) * dist2) ** 2))
                ok = (abs(dist2 - m.get("dist", -1)) <= 0.01
                      and abs(ang2 - m.get("angRadiusDeg", -1)) <= 0.15
                      and abs(fog2 - m.get("fogTransmittance", -1)) <= 0.002)
                check(ok,
                      f"{layer} 纵深三量可独立复算（距离 {dist2:.2f}m／角半径 {ang2:.1f}°／雾 {fog2:.3f}）",
                      f"{layer} 钩子自述与独立复算不符：自述 dist={m.get('dist')} "
                      f"ang={m.get('angRadiusDeg')} fog={m.get('fogTransmittance')}；"
                      f"复算 {dist2:.3f}／{ang2:.2f}／{fog2:.4f}")

        canvas = await evaluate(ws, """JSON.stringify((()=>{
            const c = document.querySelector('canvas');
            return c ? {w: c.width, h: c.height} : null;
        })())""")
        cv = json.loads(canvas) if canvas else None
        check(cv and cv["w"] > 0 and cv["h"] > 0,
              f"WebGL canvas 尺寸非 0（{cv}）——软件渲染下渲染成功",
              f"canvas 异常：{cv}")

        # ── 判据 4-7：截图像素分析 ────────────────────────────────
        print("\n── 判据 4-7：截图像素（frame1）────────────────────────")
        shot1 = await send(ws, "Page.captureScreenshot", {"format": "png"})
        b1 = base64.b64decode(shot1["result"]["data"])
        p1 = os.path.join(OUT, "frame1.png")
        with open(p1, "wb") as f:
            f.write(b1)

        # 用 PIL 分析（项目已装）
        from PIL import Image
        import numpy as np
        img = np.asarray(Image.open(p1).convert("RGB")).astype(np.int16)
        h, w, _ = img.shape
        lum = img.sum(axis=2) / 3.0

        black_ratio = float((lum < 24).mean())
        check(black_ratio >= 0.85,
              f"黑底占比 {black_ratio:.1%} ≥85%（黑地基调）",
              f"黑底占比不足：{black_ratio:.1%}")

        # 金色系：R>G>B 且 R 在暖金亮度区间
        r, g, b = img[:, :, 0], img[:, :, 1], img[:, :, 2]
        gold_mask = (r > g) & (g > b) & (r > 90) & (r < 250) & ((r - b) > 30)
        gold_ratio = float(gold_mask.mean())
        check(0.003 <= gold_ratio <= 0.15,
              f"金色像素占比 {gold_ratio:.2%}（金线可见且不刺眼，区间 0.3%~15%）",
              f"金色占比异常：{gold_ratio:.2%}")

        # 金色像素的色相方向核验（平均色应落暖金：R>G>B）
        if gold_mask.any():
            gm = img[gold_mask].mean(axis=0)
            check(gm[0] > gm[1] > gm[2],
                  f"金色平均色 R>G>B 暖金方向（RGB≈{gm.astype(int)}）",
                  f"金色平均色方向异常：{gm.astype(int)}")
        else:
            check(False, "", "无金色像素可分析")

        # 中心光点：画面中央 10% 区域应有显著亮于全图的暖色像素
        cy0, cy1 = int(h * 0.30), int(h * 0.55)   # 中心光点约在视高 40% 处
        cx0, cx1 = int(w * 0.45), int(w * 0.55)
        core = lum[cy0:cy1, cx0:cx1]
        core_bright = float((core > 60).mean())
        check(core_bright > 0.01,
              f"中心区域亮像素占比 {core_bright:.1%}（中心光点存在）",
              f"中心光点未检出（亮占比 {core_bright:.1%}）")

        # ── 判据 6：静态纪律（两帧一致）───────────────────────────
        print("\n── 判据 6：静态纪律（间隔 2.5s 帧差）─────────────────")
        await asyncio.sleep(2.5)
        shot2 = await send(ws, "Page.captureScreenshot", {"format": "png"})
        b2 = base64.b64decode(shot2["result"]["data"])
        p2 = os.path.join(OUT, "frame2.png")
        with open(p2, "wb") as f:
            f.write(b2)
        img2 = np.asarray(Image.open(p2).convert("RGB")).astype(np.int16)
        mad = float(np.abs(img - img2).mean())
        check(mad <= 1.0,
              f"两帧平均绝对差 {mad:.4f}/255 ≤1.0（绝对安静，S1 完全静态）",
              f"帧差过大 {mad:.4f}——存在非预期动画")

        await ws.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

    print("\n" + "=" * 70)
    if fails:
        print(f"❌ FAIL {len(fails)} 项：")
        for f in fails:
            print(f"   - {f}")
        return 1
    print("✅ PASS：S1 运行时验收全通过")
    print(f"   截图产物：{OUT}\\frame1.png / frame2.png")
    print("\n⚠️ 如实标注的未验证项：")
    print("   ① 道场感（D级）＝法师 Pico 真机体感，本验收无法替代")
    print("   ② headless SwiftShader 与 Pico GPU 渲染存在差异（金线亮度/锯齿）")
    print("   ③ 去视觉测试在 S1 无意义（尚无音频/呼吸反馈），自 S2 起执行")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
