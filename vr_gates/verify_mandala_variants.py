# 〔VR 闸正本·2026-09-30 起〕自 output/ 收拢进 vr_gates/（output/* 被 .gitignore 忽略，
#  验收能力本身不入库＝随时可被清盘丢掉）。证据产物仍写 output/（大图不入库）。
# 原位置：output/20260914_W1两项待裁定核查/verify_mandala_variants.py
"""曼荼罗场域 · 变体批量验收（CDP 无头 Edge，S1 验收脚本的泛化版）

流程固化（本脚本＝"设计规格→无头验收→截图对比"流水线，供本地模型复用）：
  1. 逐变体导航 ?variant=KEY
  2. 判据：无JS错 / 诊断钩子 variant 正确 / static=true / canvas 非 0
  3. 像素：黑底≥85% / 金色占比 0.3%~15% / 暖金方向 R>G>B / 帧差≤1.0
  4. 各变体截图 frame_<key>.png；全部通过后生成 compare.html 三栏对比页

用法：python verify_mandala_variants.py s1 v2abyss v3immersion
前置：console_server 在 8777 运行
产物：output/20260916_曼荼罗S1/frame_<key>.png ＋ compare.html
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
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"]
    if os.path.exists(p)), None)
PORT = 9344
BASE = "http://127.0.0.1:8777/mandala"
# 产物落点＝**脚本自己所在的那棵工作树**（AI-005 2026-09-17 修，同 verify_mandala_s1.py）。
# 可用环境变量 MANDALA_OUT 覆盖。
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.environ.get("MANDALA_OUT") or os.path.join(_ROOT, "output", "20260916_曼荼罗S1")
os.makedirs(OUT, exist_ok=True)

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
    return res.get("value")


async def verify_variant(ws, key):
    """导航并对单变体跑判据，返回 (fails, diag, png_path)"""
    fails = []
    await send(ws, "Page.navigate", {"url": f"{BASE}?variant={key}&breath=off"})
    for _ in range(60):
        await asyncio.sleep(0.5)
        gone = await evaluate(ws, "document.getElementById('load').style.display")
        if gone == "none":
            break
    await asyncio.sleep(2.0)

    err = await evaluate(ws, "window.__vrErr || ''")
    if err != "":
        fails.append(f"JS错误：{err}")

    diag = await evaluate(ws, "JSON.stringify(window.__mandalaDiag || null)")
    d = json.loads(diag) if diag and diag != "null" else None
    if not d:
        fails.append("诊断钩子不可读")
        return fails, None, None
    if d.get("variant") != key:
        fails.append(f"变体不符：期望{key} 实际{d.get('variant')}")
    if d.get("static") is not True:
        fails.append("static 非 true")

    canvas = await evaluate(ws, """JSON.stringify((()=>{
        const c=document.querySelector('canvas');
        return c?{w:c.width,h:c.height}:null})())""")
    cv = json.loads(canvas) if canvas else None
    if not (cv and cv["w"] > 0 and cv["h"] > 0):
        fails.append(f"canvas 异常：{cv}")
        return fails, d, None

    shot = await send(ws, "Page.captureScreenshot", {"format": "png"})
    png = base64.b64decode(shot["result"]["data"])
    path = os.path.join(OUT, f"frame_{key}.png")
    with open(path, "wb") as f:
        f.write(png)

    from PIL import Image
    import numpy as np
    img = np.asarray(Image.open(path).convert("RGB")).astype(np.int16)
    lum = img.sum(axis=2) / 3.0
    black_ratio = float((lum < 24).mean())
    if black_ratio < 0.85:
        fails.append(f"黑底占比不足：{black_ratio:.1%}")
    r, g, b = img[:, :, 0], img[:, :, 1], img[:, :, 2]
    gold = (r > g) & (g > b) & (r > 90) & (r < 250) & ((r - b) > 30)
    gr_ = float(gold.mean())
    if not (0.003 <= gr_ <= 0.15):
        fails.append(f"金色占比异常：{gr_:.2%}")
    if gold.any():
        gm = img[gold].mean(axis=0)
        if not (gm[0] > gm[1] > gm[2]):
            fails.append(f"金色方向异常：{gm.astype(int)}")
    else:
        fails.append("无金色像素")

    await asyncio.sleep(2.5)
    shot2 = await send(ws, "Page.captureScreenshot", {"format": "png"})
    p2 = os.path.join(OUT, f"frame_{key}_b.png")
    with open(p2, "wb") as f:
        f.write(base64.b64decode(shot2["result"]["data"]))
    img2 = np.asarray(Image.open(p2).convert("RGB")).astype(np.int16)
    mad = float(np.abs(img - img2).mean())
    if mad > 1.0:
        fails.append(f"帧差 {mad:.4f} 非静态")
    os.remove(p2)  # 中间对帧，用完即删

    # ── 构图语义代理（AI-005 2026-09-17 加）─────────────────────────
    # 把"三层纵深"从说法变成数字：角半径比、圆心角距、各层雾透过率。
    # **关键**：对钩子自述做**独立复算**——S1 那次"层参数 8/16/8 PASS"正是栽在
    # 钩子把大地层写死成 8（几何实为 16 瓣）而判据只看钩子自述。这里用钩子给出
    # 的 pos/cam 重算距离、角半径、雾透过率，任一项对不上即判失败——即"钩子也要被验收"。
    semantic = {}
    cam = d.get("cam") or [0, 0, 0]
    for layer in ("inner", "middle", "ground"):
        m = (d.get("depth") or {}).get(layer)
        if not m:
            continue
        pos = m.get("pos") or [0, 0, 0]
        dist2 = math.dist(cam, pos)
        if abs(dist2 - m.get("dist", -1)) > 0.01:
            fails.append(f"{layer} 距离自述 {m.get('dist')} ≠ 独立复算 {dist2:.3f}（钩子失实）")
        ang2 = math.degrees(math.atan2(m.get("rOut", 0), dist2 or 1e-9))
        if abs(ang2 - m.get("angRadiusDeg", -1)) > 0.15:
            fails.append(f"{layer} 角半径自述 {m.get('angRadiusDeg')} ≠ 独立复算 {ang2:.2f}")
        fog2 = math.exp(-((d.get("fog", 0) * dist2) ** 2))
        if abs(fog2 - m.get("fogTransmittance", -1)) > 0.002:
            fails.append(f"{layer} 雾透过率自述 {m.get('fogTransmittance')} ≠ 独立复算 {fog2:.4f}")
        semantic[layer] = m
    if semantic.get("inner") and semantic.get("middle"):
        a, b = semantic["inner"], semantic["middle"]
        ratio = (a["angRadiusDeg"] / b["angRadiusDeg"]) if b["angRadiusDeg"] else float("nan")
        gap = abs(a["elevDeg"] - b["elevDeg"])
        print(f"    ↳ 纵深代理：内/中角半径比 {ratio:.2f} · 圆心角距 {gap:.1f}°"
              f" · 雾透过率差 {abs(a['fogTransmittance'] - b['fogTransmittance']) * 100:.1f}pp")
    # s1 与文档/判据的记数一致性（Case-M01 §二 ＝ 8/16/8 瓣）：只报不判，
    # 取值方向（改几何 vs 改文档）涉义理，待法师裁定，脚本不擅自选一个。
    if key == "s1":
        expect = {"inner": 8, "middle": 16, "ground": 8}
        got = d.get("layers") or {}
        diff = [f"{k} 实际 {got.get(k)} ≠ 文档 {v}" for k, v in expect.items() if got.get(k) != v]
        if diff:
            print(f"    ⚠️ s1 与 Case-M01 §二 记数不一致：{'；'.join(diff)}（待法师裁定）")

    print(f"  [{key}] 黑底{black_ratio:.1%} 金色{gr_:.2%} 帧差{mad:.4f} "
          f"层{d.get('layers')} → {'✅' if not fails else '❌ ' + '; '.join(fails)}")
    return fails, d, path


async def main():
    keys = sys.argv[1:] or ["s1", "v2abyss", "v3immersion"]
    print("=" * 70)
    print(f"曼荼罗变体批量验收：{keys}")
    print("=" * 70)
    proc = subprocess.Popen([
        EDGE, "--headless=new", f"--remote-debugging-port={PORT}",
        "--window-size=1280,800", "--use-gl=swiftshader",
        "--enable-unsafe-swiftshader", "--no-first-run",
        "--user-data-dir=" + os.path.join(OUT, "_profile"),
        "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    results = {}
    try:
        import urllib.request
        targets = None
        # 60×0.5s＝30s（AI-005 09-17：原 30×0.5s＝15s，实测本机 Edge 冷启动
        # 常超过 15s，会误报"DevTools 未就绪"）
        for _ in range(60):
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{PORT}/json", timeout=1) as rq:
                    targets = json.loads(rq.read())
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
        for k in keys:
            fails, diag, path = await verify_variant(ws, k)
            results[k] = {"fails": fails, "diag": diag, "png": path}
        await ws.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

    # 三栏对比页（供法师一眼比较；本地模型验收同用此页）
    rows = []
    for k in keys:
        d = results[k]["diag"] or {}
        verdict = "✅ 全部判据通过" if not results[k]["fails"] \
            else "❌ " + "；".join(results[k]["fails"])
        rows.append(f"""<div class="cell">
      <img src="frame_{k}.png" alt="{k}">
      <h3>{d.get('variantLabel', k)}</h3>
      <p>雾 {d.get('fog')} · 相机 {d.get('cam')}<br>
         层 {json.dumps(d.get('layers'), ensure_ascii=False)}<br>
         {verdict}</p></div>""")
    html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<title>曼荼罗构图变体对比 · S1</title><style>
body{{background:#000;color:#c9b287;font-family:"PingFang SC",serif;margin:24px}}
h1{{font-size:18px;letter-spacing:3px}}
.wrap{{display:flex;gap:16px;flex-wrap:wrap}}
.cell{{flex:1 1 380px;border:1px solid #3a2f1c;padding:10px}}
img{{width:100%;display:block}}
h3{{font-size:14px;margin:8px 0 4px;color:#e3cb76}}
p{{font-size:12px;line-height:1.6;color:#8a7a5c}}
</style></head><body>
<h1>曼荼罗构图变体对比（无头验收截图，2026-09-16）</h1>
<div class="wrap">{''.join(rows)}</div>
<p style="margin-top:16px">共同纪律：黑底金线 · 完全静态 · 无粒子无bloom无数据流。
差异仅在构图：s1 三层纵深基准｜v2abyss 大地铺开主坛远望｜v3immersion 单坛浓雾沉浸。
最终取舍以 Pico 真机体感为准（D 级判据）。</p>
</body></html>"""
    with open(os.path.join(OUT, "compare.html"), "w", encoding="utf-8") as f:
        f.write(html)

    bad = sum(1 for v in results.values() if v["fails"])
    print("\n" + "=" * 70)
    print(f"{'✅ 全部变体通过' if bad == 0 else f'❌ {bad} 个变体有失败项'}"
          f" · 对比页：{OUT}\\compare.html")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
