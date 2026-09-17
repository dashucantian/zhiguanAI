"""PWA 安装能力实测：自签证书 HTTPS 下 SW 能否注册并完成预缓存

═══ 为何必须单独验这一步 ═══
PWA 能否装到 Pico 应用库，取决于 Service Worker 是否注册成功；
而 Pico 走的是 **自签证书 HTTPS**（https://<局域网IP>:8778），
自签证书下 SW 注册与 Cache API 行为须实证，不能凭"标准说可以"就断言。
本测试验四件事：
① SW 注册成功、scope='/'（否则控制不了 /vr）
② 预缓存真的把资源写进 Cache Storage（含 26MB 模型）
③ 缓存条目数与体积（证明离线可用）
④ 断网（模拟 offline）后页面仍能从缓存加载 → 证明"装好后离线可跑"
"""
import asyncio, json, os, subprocess, sys, time, urllib.request
import ssl, http.client

BASE = r"C:\Users\tiand\OneDrive\zhiguanAI"
OUT = os.path.join(BASE, r"output\20260910_VR标准模板三重分析")
SHOT = os.path.join(OUT, "截图_V2")
os.makedirs(SHOT, exist_ok=True)

EDGE = next((p for p in [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe"] if os.path.exists(p)), None)

# 用 HTTPS + 自签证书，完全模拟 Pico 的访问条件
HTTPS_URL = "https://127.0.0.1:8778/vr?mode=guided"
PORT = 9337


async def main():
    if not EDGE:
        print("未找到 Edge/Chrome"); return 2
    import websockets
    # --ignore-certificate-errors 模拟用户在 Pico 上点「继续访问」接受自签证书
    proc = subprocess.Popen(
        [EDGE, f"--remote-debugging-port={PORT}", "--headless=new", "--disable-gpu",
         "--no-sandbox", "--window-size=1280,720", "--hide-scrollbars",
         "--remote-allow-origins=*", "--ignore-certificate-errors",
         "--autoplay-policy=no-user-gesture-required", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=2); break
            except Exception:
                time.sleep(0.5)
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=5) as r:
            targets = json.load(r)
        page = next(t for t in targets if t["type"] == "page")

        fails, notes = [], []
        mid = 0
        exceptions = []
        async with websockets.connect(page["webSocketDebuggerUrl"],
                                      max_size=80*1024*1024) as ws:
            async def send(method, params=None):
                nonlocal mid
                mid += 1; myid = mid
                await ws.send(json.dumps({"id": myid, "method": method, "params": params or {}}))
                while True:
                    m = json.loads(await ws.recv())
                    if m.get("method") == "Runtime.exceptionThrown":
                        d = m["params"]["exceptionDetails"]
                        exceptions.append(str(d.get("exception", {}).get("description") or d.get("text"))[:200])
                    if m.get("id") == myid:
                        return m
            async def ev(expr, await_promise=False):
                r = await send("Runtime.evaluate", {"expression": expr,
                                                    "returnByValue": True,
                                                    "awaitPromise": await_promise})
                res = r.get("result", {})
                if "exceptionDetails" in res:
                    return {"__err": str(res["exceptionDetails"].get("exception", {}).get("description"))[:300]}
                return res.get("result", {}).get("value")

            await send("Runtime.enable"); await send("Page.enable")
            await send("Security.enable")
            await send("Page.navigate", {"url": HTTPS_URL})

            # 等页面渲染
            t0 = time.time()
            while time.time() - t0 < 60:
                if await ev("var l=document.getElementById('load');l?getComputedStyle(l).display:'none'") == "none":
                    break
                await asyncio.sleep(0.5)

            print("="*84)
            print("① 安全上下文与 SW 注册")
            print("="*84)
            ctx = await ev("JSON.stringify({secure: window.isSecureContext, proto: location.protocol, swOK: window.__swOK, supported: 'serviceWorker' in navigator})")
            print(f"  页面安全上下文: {ctx}")
            cj = json.loads(ctx) if isinstance(ctx, str) else {}
            if not cj.get("secure"):
                fails.append("页面不是安全上下文（isSecureContext=false）→ SW 无法注册")
            else:
                print("  ✅ isSecureContext=true（HTTPS 生效，SW 可注册）")

            # 等 SW 注册与安装（26MB 预缓存需要时间）
            reg = None
            for i in range(90):
                reg = await ev("""(async()=>{
                  const r = await navigator.serviceWorker.getRegistration('/');
                  if(!r) return null;
                  return JSON.stringify({
                    scope: r.scope,
                    active: !!r.active,
                    installing: !!r.installing,
                    waiting: !!r.waiting,
                    state: r.active ? r.active.state : (r.installing ? r.installing.state : 'none')
                  });
                })()""", await_promise=True)
                if reg:
                    rj = json.loads(reg)
                    if rj.get("active") and rj.get("state") == "activated":
                        break
                await asyncio.sleep(1)
            print(f"  SW 注册状态: {reg}")
            if not reg:
                fails.append("SW 未注册成功（getRegistration('/') 为空）→ PWA 装不上")
            else:
                rj = json.loads(reg)
                if rj.get("scope") != "https://127.0.0.1:8778/":
                    notes.append(f"⚠️ SW scope = {rj.get('scope')}")
                if rj.get("state") == "activated":
                    print(f"  ✅ SW 已激活，scope={rj['scope']}（覆盖 /vr 页面）")
                else:
                    fails.append(f"SW 未激活，state={rj.get('state')}")

            print()
            print("="*84)
            print("② Cache Storage 预缓存内容（证明离线可用）")
            print("="*84)
            cache_info = await ev("""(async()=>{
              const keys = await caches.keys();
              const out = [];
              for(const k of keys){
                const c = await caches.open(k);
                const reqs = await c.keys();
                out.push({cache:k, n:reqs.length, urls:reqs.map(r=>r.url)});
              }
              return JSON.stringify(out);
            })()""", await_promise=True)
            if isinstance(cache_info, str):
                arr = json.loads(cache_info)
                if not arr:
                    fails.append("Cache Storage 为空 → 离线不可用")
                for c in arr:
                    print(f"  缓存 '{c['cache']}' 共 {c['n']} 条：")
                    for u in c["urls"]:
                        print(f"      {u}")
                    expect = ["three.module.js", "GLTFLoader.js", "4.glb", "manifest.webmanifest"]
                    for e in expect:
                        if any(e in u for u in c["urls"]):
                            print(f"    ✅ 含 {e}")
                        else:
                            fails.append(f"预缓存缺 {e}")
                    # 安全红线：私钥绝不可进缓存
                    if any("tls/" in u or u.endswith(".pem") for u in c["urls"]):
                        fails.append("⚠️ 安全红线：缓存中出现了 TLS 私钥/证书")
                    else:
                        print(f"    ✅ 缓存中无 TLS 私钥/证书（安全红线守住）")
            else:
                fails.append(f"读取 Cache Storage 失败: {cache_info}")

            # 缓存体积（模型 26MB 是否真进缓存）
            usage = await ev("""(async()=>{
              if(!navigator.storage || !navigator.storage.estimate) return null;
              const e = await navigator.storage.estimate();
              return JSON.stringify({usageMB:+(e.usage/1048576).toFixed(2), quotaMB:+(e.quota/1048576).toFixed(1)});
            })()""", await_promise=True)
            print(f"\n  存储占用: {usage}")
            if isinstance(usage, str):
                uj = json.loads(usage)
                if uj["usageMB"] < 20:
                    notes.append(f"⚠️ 存储仅 {uj['usageMB']}MB，26MB 模型可能未完整入缓存")
                else:
                    print(f"  ✅ 存储占用 {uj['usageMB']}MB ≥ 20MB，模型已实际入缓存")

            print()
            print("="*84)
            print("③ 离线模拟：断网后从缓存重新加载引导页")
            print("="*84)
            await send("Network.enable")
            await send("Network.emulateNetworkConditions",
                       {"offline": True, "latency": 0, "downloadThroughput": -1,
                        "uploadThroughput": -1})
            await asyncio.sleep(1)
            await send("Page.navigate", {"url": HTTPS_URL})
            t0 = time.time(); offline_ok = False
            while time.time() - t0 < 40:
                disp = await ev("var l=document.getElementById('load');l?getComputedStyle(l).display:'none'")
                hud = await ev("(document.getElementById('hud')||{}).textContent||''")
                if disp == "none" and "引导冥想" in (hud or ""):
                    offline_ok = True; break
                await asyncio.sleep(0.5)
            hud_off = await ev("(document.getElementById('hud')||{}).textContent||''")
            await send("Network.emulateNetworkConditions",
                       {"offline": False, "latency": 0, "downloadThroughput": -1,
                        "uploadThroughput": -1})
            if offline_ok:
                print(f"  ✅ 断网后引导页仍成功加载（从缓存）：用时 {time.time()-t0:.1f}s")
                print(f"     HUD: {hud_off[:120]}")
                notes.append("离线加载成功 → 装到 Pico 后无网也能点开即用")
            else:
                fails.append(f"断网后页面未能加载（HUD='{(hud_off or '')[:60]}'）→ 离线不可用")
                notes.append("⚠️ 离线加载失败，须检查 SW fetch 策略")

            # 离线截图留证
            r = await send("Page.captureScreenshot", {"format": "png"})
            d = r.get("result", {}).get("data")
            if d:
                import base64
                p = os.path.join(SHOT, "F_PWA离线加载.png")
                with open(p, "wb") as f: f.write(base64.b64decode(d))
                print(f"  截图留证: {p} ({os.path.getsize(p)/1024:.1f}KB)")

            print()
            print("="*84)
            print("④ 运行时异常")
            print("="*84)
            if exceptions:
                print(f"  ❌ {len(exceptions)} 个异常:")
                for e in exceptions[:6]: print(f"     {e}")
                fails.append(f"运行时 {len(exceptions)} 个异常")
            else:
                print("  ✅ 无运行时异常")

        print()
        print("="*84)
        print("实测记录：")
        for n in notes: print("  · " + n)
        print("="*84)
        if fails:
            print("❌ PWA 安装能力实测未通过：")
            for f in fails: print("   - " + f)
            return 1
        print("✅ PWA 安装能力实测通过：安全上下文成立、SW 激活且 scope 覆盖 /vr、")
        print("   预缓存含全部必需资源（模型已入缓存）、私钥未入缓存、断网后可加载")
        return 0
    finally:
        proc.terminate()
        try: proc.wait(timeout=10)
        except Exception: proc.kill()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
