"""V2 步骤5 冒烟测试（修正版）：真实加载页面，验证运行时行为

═══ 上一版探针错误（记录以免重犯）═══
CAL/ALGO/GUIDE/ANCHOR/THEME/AUDIO/S/pushRA 全部报 UNDEFINED，看似严重，
实则**测试写错了**：这些常量都在 <script type="module"> 内，属模块作用域，
不挂到 window → Runtime.evaluate 在全局作用域取不到。renderer 同理，
故 frame 返回 -1。页面本身正常：msg='已连接控制台'、load.display=none、
截图 123.3KB 真实渲染、零运行时异常。

═══ 本版改用的探针（不依赖模块作用域）═══
① HUD 文本：由主循环用 S.a/S.th/GUIDE.bpm/S.soundOn 等**运行时值**渲染，
   既是用户可见输出，又直接证明模块执行到了渲染阶段且值正确。
② 两次截图像素差：证明动画循环持续推进（水面 uT=t*0.4、粒子漂移），
   而非崩溃冻结。无需模块访问。
③ Runtime.exceptionThrown 订阅：捕获任何运行时异常（定义顺序/TDZ 错误
   会在此暴露，这是 node --check 覆盖不到的）。
④ 算法逻辑本身不在此测 —— 已由 equiv_test.py 提取真实 JS 与 Python
   基准逐点比对（零偏差），职责不重叠。
"""
import asyncio, base64, json, os, sys, time, urllib.request

OUT = r"C:\Users\tiand\OneDrive\zhiguanAI\output\20260910_VR标准模板三重分析\截图"
os.makedirs(OUT, exist_ok=True)
PAGE = "http://127.0.0.1:8777/vr"
PORT = 9334

try:
    import websockets
except ImportError:
    print("❌ 缺 websockets 库")
    sys.exit(1)

for _ in range(30):
    try:
        with urllib.request.urlopen("http://127.0.0.1:8777/", timeout=2) as r:
            r.read()
        print("✅ 控制台服务已就绪（8777）")
        break
    except Exception:
        time.sleep(0.5)
else:
    print("❌ 控制台服务未就绪")
    sys.exit(1)

EDGE = next((p for p in [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]
    if os.path.exists(p)), None)
if not EDGE:
    print("❌ 未找到 Edge"); sys.exit(1)


async def main():
    import subprocess
    proc = subprocess.Popen(
        [EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars",
         "--window-size=1280,720", f"--remote-debugging-port={PORT}",
         "--autoplay-policy=no-user-gesture-required", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=2) as r:
                json.load(r)
            break
        except Exception:
            await asyncio.sleep(0.5)
    else:
        proc.kill(); print("❌ 调试端口未就绪"); return 1

    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=5) as r:
        targets = json.load(r)
    page = next(t for t in targets if t["type"] == "page")

    fails, notes = [], []
    exceptions = []
    mid = 0

    async with websockets.connect(page["webSocketDebuggerUrl"],
                                  max_size=60 * 1024 * 1024) as ws:
        async def send(method, params=None):
            nonlocal mid
            mid += 1
            myid = mid
            await ws.send(json.dumps({"id": myid, "method": method, "params": params or {}}))
            while True:
                m = json.loads(await ws.recv())
                if m.get("id") == myid:
                    return m
                if m.get("method") == "Runtime.exceptionThrown":
                    d = m["params"]["exceptionDetails"]
                    exceptions.append(str(d.get("exception", {}).get("description")
                                          or d.get("text") or "")[:300])

        async def ev(expr):
            r = await send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
            return r.get("result", {}).get("result", {}).get("value")

        await send("Runtime.enable")
        await send("Page.enable")
        await send("Page.navigate", {"url": PAGE})

        # ── 等页面进入渲染状态 ──
        t0 = time.time(); ready = False; msg = ""; loadvis = ""
        while time.time() - t0 < 50:
            msg = await ev("(document.getElementById('msg')||{}).textContent || ''")
            loadvis = await ev("var l=document.getElementById('load');"
                               "l ? getComputedStyle(l).display : 'none'")
            if loadvis == "none":
                ready = True; break
            await asyncio.sleep(0.5)
        print(f"\n【页面加载】load.display={loadvis}  msg='{msg}'  用时 {time.time()-t0:.1f}s")
        if not ready:
            fails.append("页面 50 秒内未进入渲染状态")
        else:
            notes.append(f"页面已进入渲染（load 层隐藏，msg='{msg}'）")

        # ── ① HUD 运行时值核查 ──
        # HUD 由主循环渲染，是模块作用域内真实值的 DOM 投影
        await asyncio.sleep(1.5)          # 让主循环跑若干帧
        hud = await ev("(document.getElementById('hud')||{}).textContent || ''")
        print(f"\n【HUD 运行时内容】\n{hud}\n")
        if not hud.strip():
            fails.append("HUD 为空（主循环未渲染 HUD，疑似循环内抛错）")

        checks = [
            # (说明, 断言)
            ("引导所缘 6 次/分（裁定4）",        "引导所缘" in hud and "6 次/分" in hud),
            ("如实标注「引导锚，非测量」（红线9）", "引导锚" in hud and "非测量" in hud),
            ("安定 S.a 有数值且非 NaN",           "安定 S.a" in hud and "NaN" not in hud),
            ("沉掉 S.th 有数值且非 NaN",          "沉掉 S.th" in hud),
            ("声音默认关闭（裁定5）",              "关（默认静音）" in hud),
            ("心率如实标注本机无 PPG（红线9）",    "本机无 PPG 设备" in hud),
            ("无 undefined 字样泄漏到界面",       "undefined" not in hud),
            ("无 NaN 泄漏到界面",                 "NaN" not in hud),
        ]
        print("【HUD 值核查】")
        for name, ok in checks:
            print(f"  {'✅' if ok else '❌'} {name}")
            if not ok:
                fails.append(f"HUD 核查失败：{name}")

        # S.a 数值须在 0..1 且有限
        import re as _re
        m = _re.search(r"安定 S\.a\s*([\d.]+|NaN)", hud)
        if m:
            v = m.group(1)
            ok = v != "NaN" and 0.0 <= float(v) <= 1.0
            print(f"  {'✅' if ok else '❌'} S.a 实测值 {v} 在 [0,1] 内")
            if not ok:
                fails.append(f"S.a 越界或 NaN: {v}")
            notes.append(f"S.a 运行时值 = {v}（未接数据时应为中性 0.500）")
        else:
            fails.append("未能从 HUD 解析 S.a 值")

        # ── ② 动画循环活性：两次截图像素差 ──
        print("\n【动画循环活性】")
        shots = []
        for i in range(2):
            r = await send("Page.captureScreenshot", {"format": "png"})
            d = r.get("result", {}).get("data")
            if not d:
                fails.append(f"第{i+1}次截图失败"); break
            shots.append(base64.b64decode(d))
            p = os.path.join(OUT, f"V2_冒烟_{i+1}.png")
            with open(p, "wb") as f:
                f.write(shots[-1])
            if i == 0:
                await asyncio.sleep(2.5)      # 水面周期数十秒，2.5s 足以产生可见位移
        if len(shots) == 2:
            same = shots[0] == shots[1]
            sizes = [len(s)/1024 for s in shots]
            print(f"  截图1 {sizes[0]:.1f}KB / 截图2 {sizes[1]:.1f}KB")
            if same:
                fails.append("两次截图字节完全相同 → 动画循环可能已冻结")
            else:
                print(f"  ✅ 两次截图不同 → 动画循环持续推进（水面/粒子在动）")
                notes.append(f"动画活性确认：两帧字节不同（{sizes[0]:.1f}KB vs {sizes[1]:.1f}KB）")
            # 量化像素差（若有 PIL）
            try:
                import io
                from PIL import Image
                import numpy as np
                a = np.asarray(Image.open(io.BytesIO(shots[0])).convert("L"), dtype=np.float64)
                b = np.asarray(Image.open(io.BytesIO(shots[1])).convert("L"), dtype=np.float64)
                diff = np.abs(a - b)
                changed = float(np.mean(diff > 2) * 100)
                print(f"  变化像素占比 {changed:.2f}%，平均亮度差 {diff.mean():.3f}/255")
                if changed < 0.05:
                    notes.append("⚠️ 变化像素极少，画面几乎静止（可能符合预期：底色层τ=60s极慢）")
                if a.mean() < 3 and b.mean() < 3:
                    fails.append("两帧均近全黑 → 疑似渲染失败")
                else:
                    notes.append(f"画面平均亮度 {a.mean():.1f}/255（非黑屏）")
            except ImportError:
                notes.append("（未装 PIL，跳过像素级量化，仅用字节差判活性）")

        # ── ③ 运行时异常 ──
        print("\n【运行时异常】")
        if exceptions:
            print(f"  ❌ 捕获 {len(exceptions)} 个：")
            for e in exceptions[:8]:
                print(f"     {e}")
            fails.append(f"运行时抛出 {len(exceptions)} 个异常")
        else:
            print("  ✅ 无运行时异常（定义顺序/TDZ 类错误会在此暴露）")

        # ── ④ WebSocket 是否真连上（数据通路）──
        src = await ev("(function(){ var h=(document.getElementById('hud')||{}).textContent||'';"
                       "var m=h.match(/数据源\\s*(\\S+)/); return m?m[1]:'?'; })()")
        print(f"\n【数据通路】HUD 显示数据源：{src}")
        if src in ("?", ""):
            notes.append("⚠️ 未能从 HUD 解析数据源")
        elif "未连接" in str(src):
            notes.append("⚠️ 未连接控制台（无采集会话时的正常状态）")
        else:
            notes.append(f"数据源已连接：{src}")

    proc.kill()
    print("\n" + "=" * 78)
    print("实测记录：")
    for n in notes:
        print("  · " + n)
    print("=" * 78)
    if fails:
        print("❌ 冒烟测试未通过：")
        for f in fails:
            print("   - " + f)
        return 1
    print("✅ 冒烟测试通过：页面真实加载渲染、HUD 运行时值符合裁定、")
    print("   动画循环持续推进、无运行时异常、无黑屏")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
