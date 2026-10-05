#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_congci_card.py — 批 C2 真浏览器验收：从此脑·观照曼陀罗卡（CDP 无头 Edge）

判据（施工正本方案稿 v2 §三＋W4 验收口径：卡渲染与脑档案逐字一致）：
  1. 8777 就绪（env 指向 tmp 夹具；S99 committed 在案）
  2. 卡三态明示：committed 渲染（iframe 可见＋曼陀罗 P 数据载入＝120 拍）
     ／失联（S98 未入队）／坏 key（400 bad_key 明示）
  3. 数据版本＋会话身份一致性：响应回显 key == 所请求 key（卡侧复核）
  4. 截图留证 output/20261006_从此脑卡/

用法：python verify_congci_card.py（解释器须有 websockets＋fastapi——8777 同款）
前置：_analysis_tmp/_c2_setup.py 已装配夹具（committed S99）。
"""
import asyncio
import base64
import json
import os
import subprocess
import sys
import time
import urllib.request

P312 = r"C:\Users\tiand\AppData\Local\Programs\Python\Python312\python.exe"
PROJ = r"D:\Project\zhiguanAI"
EDGE = next((p for p in [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"]
    if os.path.exists(p)), None)
# 端口可参数化（验收实例避让生产 8777；HTTPS 子端口显式关闭防撞生产 8778）
PORT = int(os.environ.get("CONGCI_ACCEPT_PORT", "8777"))
CDP_PORT = int(os.environ.get("CONGCI_ACCEPT_CDP", "9345"))
SK = "ZEN-20261006-P001-S99"
ENV = json.load(open(os.path.join(PROJ, "_analysis_tmp", "_c2_env.json"),
                     encoding="utf-8"))
OUT = os.path.join(PROJ, "output", "20261006_从此脑卡")
os.makedirs(OUT, exist_ok=True)

fails = []


def check(cond, ok_msg, fail_msg):
    if cond:
        print(f"  ✅ {ok_msg}")
    else:
        print(f"  ❌ {fail_msg}")
        fails.append(fail_msg)


def url_ok(u, timeout=1.5):
    try:
        with urllib.request.urlopen(u, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


async def cdp(ws_url):
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
                   {"expression": expr, "returnByValue": True,
                    "awaitPromise": True})
    res = r.get("result", {}).get("result", {})
    if "value" in res:
        return res["value"]
    err = r.get("result", {}).get("exceptionDetails")
    if err:
        return None
    return None


async def wait_for(ws, expr, want, timeout=20, every=0.4):
    deadline = time.time() + timeout
    while time.time() < deadline:
        v = await evaluate(ws, expr)
        if v == want or (isinstance(want, str) and isinstance(v, str)
                         and want in v):
            return v
        await asyncio.sleep(every)
    return await evaluate(ws, expr)


async def main() -> int:
    if not EDGE:
        print("FAIL: 未找到 Edge")
        return 1
    server = None
    edge = None
    logf = os.path.join(OUT, "_srv8777.log")
    errf = os.path.join(OUT, "_srv8777.err")
    try:
        # ── 1. 启 8777（env 指向 tmp 夹具；输出落文件不落管道）──────────
        env = dict(os.environ)
        env["CONGCI_PIPELINE_ROOT"] = ENV["congci_root"]
        env["CONGCI_PIPELINE_ZEN_ROOT"] = ENV["zen_root"]
        with open(logf, "w", encoding="utf-8") as lo, \
                open(errf, "w", encoding="utf-8") as le:
            server = subprocess.Popen(
                [P312, "-X", "utf8", os.path.join(PROJ, "console_server.py"),
                 "--port", str(PORT), "--https-port", "0"],
                cwd=PROJ, env=env, stdout=lo, stderr=le)
        ok_ready = False
        for _ in range(60):
            if url_ok(f"http://127.0.0.1:{PORT}/api/monitor/status"):
                ok_ready = True
                break
            time.sleep(0.5)
        check(ok_ready, f"8777 就绪（env=tmp 夹具）", f"8777 未就绪：{errf}")

        # ── 2. 启无头 Edge（CDP）──────────────────────────────────────
        edge = subprocess.Popen([
            EDGE, "--headless=new", f"--remote-debugging-port={CDP_PORT}",
            "--window-size=1440,900", "--use-gl=swiftshader",
            "--enable-unsafe-swiftshader", "--no-first-run",
            "--user-data-dir=" + os.path.join(OUT, "_profile"),
            "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        targets = None
        for _ in range(60):
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{CDP_PORT}/json", timeout=1) as r:
                    targets = json.loads(r.read())
                break
            except Exception:
                time.sleep(0.5)
        if not targets:
            print("FAIL: Edge DevTools 未就绪")
            return 1
        page = next((t for t in targets if t["type"] == "page"), targets[0])
        ws = await cdp(page["webSocketDebuggerUrl"])
        await send(ws, "Page.enable")
        await send(ws, "Runtime.enable")
        await send(ws, "Page.navigate", {"url": f"http://127.0.0.1:{PORT}/"})

        # 等主控台就绪（从此脑卡元素在位）
        v = await wait_for(ws,
                           "document.getElementById('congciKey') ? '1' : '0'",
                           "1", timeout=30)
        check(v == "1", "主控台加载，从此脑卡元素在位", "主控台未就绪")
        # 批 C3 声带消费面（上屏行/日志元素在位；SSE 数据流另由端到端验收覆盖）
        voice_ui = await evaluate(
            ws, "!!(document.getElementById('congciVoiceLine') && "
                "document.getElementById('congciVoiceLog'))")
        check(voice_ui is True, "声带上屏消费面在位（声带行＋日志）",
              "声带消费面元素缺失")
        await send(ws, "Runtime.evaluate",
                   {"expression": "document.querySelector('[data-tab=\"review\"]').click()"})
        await asyncio.sleep(1.0)

        # ── 3. committed 渲染：填 S99 → 观这一坐 ──────────────────────
        await evaluate(ws, "document.getElementById('congciKey').value='" + SK + "'")
        await evaluate(ws, "document.getElementById('congciLoad').click()")
        bn = await wait_for(ws, "document.getElementById('congciBanner').textContent",
                            "committed", timeout=25)
        check(bn and "committed" in bn, f"卡横幅：committed（{SK}）", f"横幅未达 committed：{bn}")
        check(SK in (bn or ""), "身份一致性：横幅回显所请求 session_key", f"横幅缺 key：{bn}")
        vis = await evaluate(ws, "document.getElementById('congciIframe').style.display")
        check(vis == "block", "iframe 显示（曼陀罗容器展开）", f"iframe 未显示：{vis}")
        # 曼陀罗数据断言走 iframe 内 DOM（cadence_mandala 的 P 为 const 脚本
        # 绑定、不挂 window——2026-10-06 自验实测：读 contentWindow.P 恒为
        # undefined，系测试方法缺陷而非渲染缺陷）：#sum 由 renderSummary 填、
        # #clock 由 draw 每帧刷新，均含拍数/总时长。
        sum_txt = await wait_for(
            ws, "document.getElementById('congciIframe').contentDocument && "
                "document.getElementById('congciIframe').contentDocument."
                "getElementById('sum') ? document.getElementById('congciIframe')."
                "contentDocument.getElementById('sum').textContent : ''",
            "120", timeout=25)
        check(sum_txt and "120" in sum_txt,
              f"曼陀罗数据载入（iframe #sum 含 120 拍）：{str(sum_txt)[:80]}",
              f"曼陀罗数据未载入：{sum_txt!r}")
        clock_txt = await evaluate(
            ws, "document.getElementById('congciIframe').contentDocument."
                "getElementById('clock').textContent")
        check(clock_txt and "02:00" in clock_txt,
              f"整座时长渲染（#clock={clock_txt}）", f"#clock 异常：{clock_txt!r}")
        has_cv = await evaluate(
            ws, "!!document.getElementById('congciIframe').contentDocument."
                "getElementById('cv')")
        check(has_cv is True, "曼陀罗画布在位（canvas#cv）", "画布缺失")
        # 截图前把卡滚入视口（供法师视角查看卡本体，非页顶仪表盘）
        await evaluate(ws, "document.getElementById('congciBanner')"
                           ".scrollIntoView({block:'center'})")
        await asyncio.sleep(0.8)
        shot = await send(ws, "Page.captureScreenshot", {"format": "png"})
        with open(os.path.join(OUT, "console_card_committed.png"), "wb") as f:
            f.write(base64.b64decode(shot["result"]["data"]))
        print(f"  截图：{OUT}\\console_card_committed.png")

        # ── 4. 失联态：S98（装配未入队）──────────────────────────────
        await evaluate(ws, "document.getElementById('congciKey').value='ZEN-20261006-P001-S98'")
        await evaluate(ws, "document.getElementById('congciLoad').click()")
        bn2 = await wait_for(ws, "document.getElementById('congciBanner').textContent",
                             "失联", timeout=15)
        check(bn2 and "失联" in bn2, "失联态明示（S98 未入队）", f"失联横幅异常：{bn2}")
        shot2 = await send(ws, "Page.captureScreenshot", {"format": "png"})
        with open(os.path.join(OUT, "console_card_lost.png"), "wb") as f:
            f.write(base64.b64decode(shot2["result"]["data"]))
        print(f"  截图：{OUT}\\console_card_lost.png")

        # ── 5. 坏 key：超长 key 拒绝（400 bad_key 卡内明示）─────────────
        # 注：路径字符类 key（如 ../../etc）会被浏览器在发请求前归一化，
        # 到达服务端前已是 /etc/record → 404 Not Found（2026-10-06 自验实测）；
        # 故用不含路径字符的超长 key 直击校验层（unit 测试另覆盖路径字符面）。
        long_key = "a" * 129
        await evaluate(ws, "document.getElementById('congciKey').value='" + long_key + "'")
        await evaluate(ws, "document.getElementById('congciLoad').click()")
        bn3 = await wait_for(ws, "document.getElementById('congciBanner').textContent",
                             "非法", timeout=15)
        check(bn3 and "非法" in bn3, "坏 key 明示（bad_key 校验层拒绝）",
              f"坏 key 横幅异常：{bn3}")

        if fails:
            print(f"FAIL: {len(fails)} 项未过")
            return 1
        print("PASS: 从此脑卡真浏览器验收全过（committed 渲染＋失联＋坏 key）")
        return 0
    finally:
        if edge:
            edge.terminate()
        if server:
            server.terminate()
            try:
                server.wait(timeout=5)
            except Exception:
                server.kill()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
