"""V2 修复验收：粒子穿透本尊是否消除（运行时实测，非语法检查）
法师 09-12 实测反馈：水面透明方块粒子碰到瑜伽士时会穿透过去，
应触碰即消失、不从背面穿出。

验证两层（都是运行时证据）：
① 逻辑层：真加载模型 → 读 window.__vrDiag
   - relocated > 0  证明修复前确有粒子在体内（否则无从谈起穿透）
   - insideAfter == 0  证明修复后体内零粒子
② 视觉层：按页面自己的 camera 投影矩形取样，确认模型投影区内无粒子亮点
   （不靠猜分区——本轮已三次因猜分区误判）

CDP 用 websockets（异步），与已跑通的 smoke_test.py 同一依赖，不新装。
"""
import asyncio, base64, json, os, subprocess, sys, time, urllib.request
import numpy as np
from PIL import Image

BASE = r"C:\Users\tiand\OneDrive\zhiguanAI"
OUT  = os.path.join(BASE, r"output\20260910_VR标准模板三重分析")
SHOT = os.path.join(OUT, "截图_V2")
os.makedirs(SHOT, exist_ok=True)

CHROME = None
for p in [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
          r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
          r"C:\Program Files\Google\Chrome\Application\chrome.exe",
          r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
          os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")]:
    if os.path.exists(p):
        CHROME = p; break

URL  = "http://127.0.0.1:8777/vr?autoload=1&fix_a=0.5&fix_th=0.5&state=calm&breath=1.5708"
PORT = 9333

async def run():
    import websockets
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=5) as r:
        targets = json.load(r)
    page = next(t for t in targets if t["type"] == "page")

    async with websockets.connect(page["webSocketDebuggerUrl"],
                                  max_size=60*1024*1024) as ws:
        mid = 0
        async def send(method, params=None):
            nonlocal mid
            mid += 1; myid = mid
            await ws.send(json.dumps({"id": myid, "method": method, "params": params or {}}))
            while True:
                m = json.loads(await ws.recv())
                if m.get("id") == myid:
                    return m
        async def ev(expr):
            r = await send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
            return r.get("result", {}).get("result", {}).get("value")

        await send("Runtime.enable"); await send("Page.enable")
        await send("Page.navigate", {"url": URL})

        # 等模型载入：__vrDiag 出现即代表 loadModel 完成且避让已执行
        diag = None
        t0 = time.time()
        while time.time() - t0 < 150:
            diag = await ev("window.__vrDiag || null")
            if diag: break
            await asyncio.sleep(1)
        # 再多渲染几帧，让主循环运行时守卫也跑过
        await asyncio.sleep(3)
        diag2 = await ev("window.__vrDiag || null")

        print("="*78)
        print("① 逻辑层：粒子是否仍在模型包围盒内")
        print("="*78)
        if not diag:
            print("  ✗ __vrDiag 未出现——模型未载入或避让未执行")
            print("    msg =", await ev("(document.getElementById('msg')||{}).textContent"))
            return 1, None
        b = diag["box"]; sr = diag.get("screenRect")
        print(f"  模型包围盒(世界坐标,含0.18外扩):")
        print(f"    x[{b['x0']},{b['x1']}] y[{b['y0']},{b['y1']}] z[{b['z0']},{b['z1']}]")
        print(f"  粒子总数         : {diag['total']}")
        print(f"  载入时体内重排数 : {diag['relocated']}   ← >0 证明修复前确有穿透")
        print(f"  重排后体内残留   : {diag['insideAfter']}   ← 必须为 0")
        if diag2:
            print(f"  运行数帧后再查残留: {diag2['insideAfter']}   ← 主循环守卫是否稳定")

        print()
        print("="*78)
        print("② 视觉层：模型投影区内粒子亮点取样")
        print("="*78)
        # 截图
        r = await send("Page.captureScreenshot", {"format": "png"})
        data = r.get("result", {}).get("data")
        shot = os.path.join(SHOT, "E_粒子避让_修复后.png")
        ok_shot = False
        if data:
            with open(shot, "wb") as f: f.write(base64.b64decode(data))
            ok_shot = True
            print(f"  截图留证: {shot} ({os.path.getsize(shot)/1024:.1f}KB)")
        if not sr:
            print("  （无 screenRect，视觉层跳过——逻辑层已足判定）")
        elif ok_shot:
            print(f"  模型屏幕投影矩形(归一化): x[{sr['x0']},{sr['x1']}] y[{sr['y0']},{sr['y1']}]")

        logic_ok = diag["relocated"] > 0 and diag["insideAfter"] == 0 and (diag2 is None or diag2["insideAfter"] == 0)
        print()
        print("="*78)
        print(f"结论：{'✅ 穿透已消除' if logic_ok else '❌ 未通过'}")
        print("="*78)
        return (0 if logic_ok else 1), diag

async def main():
    if not CHROME:
        print("未找到 Chrome"); return 2
    proc = subprocess.Popen([CHROME, f"--remote-debugging-port={PORT}",
                             "--headless=new", "--disable-gpu", "--no-sandbox",
                             "--window-size=1280,720", "--hide-scrollbars",
                             "--remote-allow-origins=*", URL],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=2); break
            except Exception:
                time.sleep(0.5)
        code, diag = await run()
        # 视觉层量化：模型投影区 vs 外围的亮点对比
        if code == 0 and diag and diag.get("screenRect"):
            shot = os.path.join(SHOT, "E_粒子避让_修复后.png")
            if os.path.exists(shot):
                im = np.array(Image.open(shot).convert("L")).astype(float)
                H, W = im.shape
                sr = diag["screenRect"]
                x0, x1 = int(sr["x0"]*W), int(sr["x1"]*W)
                y0, y1 = int(sr["y0"]*H), int(sr["y1"]*H)
                if x1 > x0 and y1 > y0:
                    inner = im[y0:y1, x0:x1]
                    # 模型区因瑜伽士本身是实体，亮度未必低；关键是「粒子亮点」——
                    # 用 >128 的高亮点占比衡量（粒子是 AdditiveBlending 的亮白点）
                    hi = (inner > 128).mean()*100
                    print(f"\n视觉层：模型投影区内高亮点(>128)占比 {hi:.2f}%")
                    print(f"  说明：粒子为亮白点(size=.06,Additive)，若穿透则此区会散布额外亮点。")
                    print(f"  此值为参考——瑜伽士本体也有高光，最终以①逻辑层 insideAfter=0 为准。")
        return code
    finally:
        proc.terminate()
        try: proc.wait(timeout=10)
        except Exception: proc.kill()

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
