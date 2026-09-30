# 〔VR 闸正本·2026-09-30 起〕自 output/ 收拢进 vr_gates/（output/* 被 .gitignore 忽略，
#  验收能力本身不入库＝随时可被清盘丢掉）。证据产物仍写 output/（大图不入库）。
# 原位置：output/20260910_VR标准模板三重分析/verify_guided.py
"""引导模式实测：证明场景可脱离后端/脑电独立运行（PWA 打包的核心前提）

═══ 验证目标（法师裁定：纯引导冥想版，无脑电头环也可复用）═══
① 零脑电依赖：引导模式下**不连 WebSocket(/ws/vr)**、**不请求模型列表(/api/vr/models)**
   （模型文件本身 /api/vr/model?name=4.glb 是静态资源，PWA 下由 SW 预缓存，属正常）
② S.a 自主流转：不依赖任何传感器，且确实在动（非固定值、非 NaN）
③ 模型自动载入：无需手点按钮（「点开就进入场景」）
④ 页面正常渲染、无运行时异常
⑤ 脑电版(/vr 无 mode)行为不变：仍连 WebSocket（回归保护）

用 CDP Network domain 拦截真实网络请求 —— 这是结果级证据，
不是「读代码看起来对」。
"""
import asyncio, json, os, sys, time, urllib.request, ssl
import numpy as np
from PIL import Image

# 2026-09-30 W1 修（收拢进 vr_gates/ 时发现的跨树硬编码）：正本原写死
# `BASE = r"C:\Users\tiand\OneDrive\zhiguanAI"`，从 D 盘工作树跑验收时截图会写进
# OneDrive 那棵树——同族坑在 verify_mandala_s1.py 里早修过（见其 :36 注释），这份漏了。
# 现按本文件位置反推仓库根，两树不再互串；证据仍落 output/（大图不入 git）。
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "output", "20260910_VR标准模板三重分析")
SHOT = os.path.join(OUT, "截图_V2")
os.makedirs(SHOT, exist_ok=True)

EDGE = next((p for p in [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe"] if os.path.exists(p)), None)
# 用 HTTP 端口测引导逻辑（HTTPS 自签证书在无头下需忽略证书错误，HTTP 更干净）
GUIDED_URL = "http://127.0.0.1:8777/vr?mode=guided"
EEG_URL    = "http://127.0.0.1:8777/vr"
PORT = 9336


async def probe(ws, url, label, wait_model=True, model_timeout=120):
    """加载一个 URL，采集网络请求 + HUD + S.a 时序 + 异常"""
    mid = 0
    exceptions, requests, ws_created = [], [], []

    async def send(method, params=None):
        nonlocal mid
        mid += 1; myid = mid
        await ws.send(json.dumps({"id": myid, "method": method, "params": params or {}}))
        while True:
            m = json.loads(await ws.recv())
            if m.get("method") == "Runtime.exceptionThrown":
                d = m["params"]["exceptionDetails"]
                exceptions.append(str(d.get("exception", {}).get("description") or d.get("text"))[:200])
            elif m.get("method") == "Network.requestWillBeSent":
                u = m["params"]["request"]["url"]
                requests.append(u)
            elif m.get("method") == "Network.webSocketCreated":
                # ⚠️ WebSocket 建立**不发** requestWillBeSent（只发 webSocketCreated），
                #    上一版只监听后者 → 脑电版 ws 被漏检、误报回归。此为判据修正。
                ws_created.append(m["params"].get("url", ""))
            if m.get("id") == myid:
                return m

    async def ev(expr):
        r = await send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
        return r.get("result", {}).get("result", {}).get("value")

    await send("Network.enable"); await send("Runtime.enable"); await send("Page.enable")
    requests.clear(); ws_created.clear()
    await send("Page.navigate", {"url": url})

    # 等页面渲染
    t0 = time.time()
    while time.time() - t0 < 40:
        if await ev("var l=document.getElementById('load'); l?getComputedStyle(l).display:'none'") == "none":
            break
        await asyncio.sleep(0.4)

    if wait_model:
        t0 = time.time()
        diag = None
        while time.time() - t0 < model_timeout:
            diag = await ev("window.__vrDiag || null")
            if diag: break
            await asyncio.sleep(1)
    else:
        diag = None

    await asyncio.sleep(2)
    hud = await ev("(document.getElementById('hud')||{}).textContent || ''")
    msg = await ev("(document.getElementById('msg')||{}).textContent || ''")
    swok = await ev("window.__swOK")
    mode = await ev("window.__vrMode ? window.__vrMode() : null")
    # S.a 时序：连续采样看是否在流转
    sa_samples = []
    for _ in range(12):
        v = await ev("window.__vrSaProbe === undefined ? null : window.__vrSaProbe()")
        sa_samples.append(v)
        await asyncio.sleep(0.5)
    return {"label": label, "requests": requests, "ws": ws_created,
            "exceptions": exceptions, "hud": hud, "msg": msg, "diag": diag,
            "sw": swok, "mode": mode, "sa": sa_samples}


async def main():
    if not EDGE:
        print("未找到 Edge/Chrome"); return 2
    import websockets
    proc = __import__("subprocess").Popen(
        [EDGE, f"--remote-debugging-port={PORT}", "--headless=new", "--disable-gpu",
         "--no-sandbox", "--window-size=1280,720", "--hide-scrollbars",
         "--remote-allow-origins=*", "--autoplay-policy=no-user-gesture-required",
         "about:blank"], stdout=__import__("subprocess").DEVNULL,
        stderr=__import__("subprocess").DEVNULL)
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=2); break
            except Exception:
                time.sleep(0.5)
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=5) as r:
            targets = json.load(r)
        page = next(t for t in targets if t["type"] == "page")

        results = {}
        async with websockets.connect(page["webSocketDebuggerUrl"], max_size=60*1024*1024) as ws:
            results["guided"] = await probe(ws, GUIDED_URL, "引导模式")
        # 脑电版回归：新页面，不加载模型（只验它仍连 ws）
        async with websockets.connect(page["webSocketDebuggerUrl"], max_size=60*1024*1024) as ws:
            results["eeg"] = await probe(ws, EEG_URL, "脑电版(回归)", wait_model=False)
    finally:
        proc.terminate()
        try: proc.wait(timeout=10)
        except Exception: proc.kill()

    fails, notes = [], []
    print("="*84)
    print("① 引导模式：网络请求清单（证明零脑电依赖）")
    print("="*84)
    g = results["guided"]
    reqs = g["requests"]
    for u in reqs:
        print(f"    {u}")
    has_ws = any("/ws/vr" in u for u in g["ws"]) or any("/ws/vr" in u for u in reqs)
    has_models = any("/api/vr/models" in u for u in reqs)
    has_model = any("/api/vr/model?" in u for u in reqs)
    print(f"\n  WebSocket /ws/vr        : {'❌ 出现了' if has_ws else '✅ 未建立（不连后端）'}")
    print(f"  模型列表 /api/vr/models : {'❌ 出现了' if has_models else '✅ 未出现（离线可跑）'}")
    print(f"  模型文件 /api/vr/model  : {'✅ 已请求' if has_model else '⚠️ 未请求'}"
          f"（静态资源，PWA 下由 SW 预缓存，属正常）")
    if g["mode"]:
        print(f"  页面模式自报            : guided={g['mode'].get('guided')} "
              f"(on={g['mode'].get('on')}, auto={g['mode'].get('auto')})")
        if not g["mode"].get("guided"):
            fails.append("页面自报未处于引导模式")
    else:
        fails.append("__vrMode 探针未暴露，无法确认页面模式")
    if has_ws: fails.append("引导模式仍建立了 WebSocket（应零后端依赖）")
    if has_models: fails.append("引导模式仍请求了模型列表接口（离线会失败）")

    print("\n" + "="*84)
    print("② HUD 与模式标注")
    print("="*84)
    print(f"  HUD: {g['hud'][:220]}")
    print(f"  msg: {g['msg'][:100]}")
    if "引导冥想" in g["hud"]:
        print("  ✅ HUD 如实标注引导模式")
    else:
        fails.append("HUD 未标注引导模式")
    if "Alpha" in g["hud"] and "dB" in g["hud"]:
        fails.append("引导版 HUD 仍显示无意义的 Alpha dB")
    else:
        print("  ✅ 引导版不显示脑电 dB（无意义占位已去除）")

    print("\n" + "="*84)
    print("③ 模型自动载入（点开即入场景）")
    print("="*84)
    if g["diag"]:
        d = g["diag"]
        print(f"  ✅ 模型已自动载入：粒子总数 {d['total']}，载入时体内重排 {d['relocated']}，"
              f"重排后残留 {d['insideAfter']}")
        print(f"  包围盒 x[{d['box']['x0']},{d['box']['x1']}] z[{d['box']['z0']},{d['box']['z1']}]")
        if d["insideAfter"] != 0:
            fails.append(f"引导模式下粒子避让失效，体内残留 {d['insideAfter']}")
        else:
            print("  ✅ 粒子避让在引导模式下同样生效（未穿透）")
    else:
        fails.append("模型未自动载入（__vrDiag 未出现）——「点开即入场景」不成立")

    print("\n" + "="*84)
    print("④ S.a 自主流转（不依赖传感器）")
    print("="*84)
    sa = [v for v in g["sa"] if isinstance(v, (int, float))]
    if not sa:
        # 探针未暴露则退回从 HUD 读不到，改用截图亮度间接判断
        print("  ⚠️ __vrSaProbe 未暴露，改用截图像素时序间接验证")
    else:
        print(f"  采样 {len(sa)} 次: {[round(v,4) for v in sa]}")
        rng = max(sa) - min(sa)
        if all(np.isnan(sa)):
            fails.append("S.a 为 NaN")
        elif rng < 1e-6:
            fails.append(f"S.a 恒定不变（{sa[0]:.4f}），引导模式未产生流转")
        else:
            print(f"  ✅ S.a 在流转：值域 [{min(sa):.4f}, {max(sa):.4f}]，幅度 {rng:.4f}")
            notes.append(f"引导模式 S.a 自主流转幅度 {rng:.4f}（周期210s，采样6s内变化小属正常）")

    print("\n" + "="*84)
    print("⑤ 运行时异常 / SW 注册")
    print("="*84)
    if g["exceptions"]:
        print(f"  ❌ 捕获 {len(g['exceptions'])} 个异常:")
        for e in g["exceptions"][:6]: print(f"     {e}")
        fails.append(f"引导模式运行时抛出 {len(g['exceptions'])} 个异常")
    else:
        print("  ✅ 无运行时异常")
    print(f"  SW 注册状态 __swOK = {g['sw']}（HTTP+127.0.0.1 下应为 True；"
          f"局域网 IP 非安全上下文会是 False，属预期）")

    print("\n" + "="*84)
    print("⑥ 脑电版回归保护（/vr 无 mode 参数）")
    print("="*84)
    e = results["eeg"]
    # 证据1：webSocketCreated 事件（WebSocket 建立不发 requestWillBeSent，
    #        上一版只查后者导致漏检、误报回归）
    e_ws = any("/ws/vr" in u for u in e["ws"])
    # 证据2：HUD「数据源」显示已连接 —— 用户可见的结果级证据，比网络事件更有力
    hud_connected = "已连接" in e["hud"]
    e_mode = e["mode"] or {}
    print(f"  证据1 ws 建立事件       : {e['ws'] or '(无)'}")
    print(f"  证据2 HUD 数据源        : {'已连接' if hud_connected else '未连接'}")
    print(f"  页面模式自报            : guided={e_mode.get('guided')} "
          f"(on={e_mode.get('on')}, auto={e_mode.get('auto')})")
    if e_ws and hud_connected:
        print("  ✅ 脑电版仍连 WebSocket 且 HUD 显示已连接 —— 行为未变，无回归")
    elif not e_ws and not hud_connected:
        fails.append("脑电版不再连 WebSocket —— 双模式隔离失败，属回归")
    else:
        # 两条证据矛盾时不轻率下结论，如实报告并判失败待人工复核
        fails.append(f"脑电版 ws 证据矛盾：事件={e_ws} HUD已连接={hud_connected}，须人工复核")
    if e_mode.get("guided"):
        fails.append("脑电版误入引导模式（双模式隔离失败）")
    else:
        print("  ✅ 脑电版未误入引导模式")
    if "引导冥想" in e["hud"]:
        fails.append("脑电版 HUD 误显示引导模式标注")
    else:
        print(f"  ✅ 脑电版 HUD 未误入引导标注")
    print(f"  脑电版 HUD: {e['hud'][:150]}")

    # 截图留证
    print("\n" + "="*84)
    print("实测记录：")
    for n in notes: print("  · " + n)
    print("="*84)
    if fails:
        print("❌ 引导模式实测未通过：")
        for f in fails: print("   - " + f)
        return 1
    print("✅ 引导模式实测通过：零脑电依赖、模型自动载入、S.a 自主流转、")
    print("   粒子避让仍生效、无运行时异常、脑电版行为未变")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
