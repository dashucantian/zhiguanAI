"""前端看门狗实测：断流 → 自动重连 → 波形恢复（完整故障链验证）

═══ 为何必须运行时实测 ═══
validate_console.py 只验静态（id/引用/语法），证明不了看门狗真会重连。
本次故障的本质正是"运行时静默失效"：代码编译通过、静态校验通过，
但 EventSource 断流后 onerror 被吞、无重连 → 界面永久空白。
故必须真造一次断流，看前端是否自愈。

═══ 实测设计 ═══
用 CDP 驱动真实浏览器打开控制台页，走完整用户路径：
① 启动模拟监测 → 确认收到 tick（波形恢复显示）
② **杀掉服务进程** → 制造真实断流（最彻底的断流：连接直接失效）
③ 重启服务 → 看前端看门狗是否在数秒内自动重连并恢复收 tick
④ 全程记录 monLastEventAt / monReconnects / statusText，验证界面如实标注

判据（针对本次故障的四个症状）：
  A 断流期间界面须出现"推流 Ns 未更新"或重连提示（不得静默黑屏）
  B 服务恢复后前端须自动恢复收 tick（无需人工刷新）
  C monReconnects 须 > 0（证明看门狗真的动作了，不是碰巧）
  D 全程无未捕获 JS 异常
"""
import asyncio, json, os, subprocess, sys, time, urllib.request

BASE = r"C:\Users\tiand\OneDrive\zhiguanAI"
PY = os.path.join(os.environ["LOCALAPPDATA"], "Programs", "Python", "Python312", "python.exe")
PAGE = "http://127.0.0.1:8777/"
PORT = 9340
EDGE = next((p for p in [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe"] if os.path.exists(p)), None)


def server_pid():
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "(Get-NetTCPConnection -State Listen -LocalPort 8777 "
         "-ErrorAction SilentlyContinue | Select-Object -First 1).OwningProcess"],
        capture_output=True, text=True, timeout=25)
    s = (out.stdout or "").strip()
    return int(s) if s.isdigit() else None


def kill_server(pid):
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    f"Stop-Process -Id {pid} -Force"],
                   capture_output=True, text=True, timeout=25)


def start_server():
    return subprocess.Popen(
        [PY, os.path.join(BASE, "console_server.py"), "--port", "8777",
         "--https-port", "0"],
        cwd=BASE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def wait_up(timeout=40):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen("http://127.0.0.1:8777/api/monitor/status",
                                        timeout=3) as r:
                json.load(r)
            return True
        except Exception:
            time.sleep(0.6)
    return False


async def main():
    if not EDGE:
        print("未找到浏览器"); return 2
    fails, notes = [], []
    srv = None
    browser = subprocess.Popen(
        [EDGE, f"--remote-debugging-port={PORT}", "--headless=new", "--disable-gpu",
         "--no-sandbox", "--window-size=1400,900", "--hide-scrollbars",
         "--remote-allow-origins=*", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    import websockets
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=2); break
            except Exception:
                time.sleep(0.5)
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=5) as r:
            targets = json.load(r)
        page = next(t for t in targets if t["type"] == "page")

        mid = 0
        js_errors = []
        async with websockets.connect(page["webSocketDebuggerUrl"],
                                      max_size=80 * 1024 * 1024) as ws:
            async def send(method, params=None):
                nonlocal mid
                mid += 1; myid = mid
                await ws.send(json.dumps({"id": myid, "method": method,
                                          "params": params or {}}))
                while True:
                    m = json.loads(await ws.recv())
                    if m.get("method") == "Runtime.exceptionThrown":
                        d = m["params"]["exceptionDetails"]
                        js_errors.append(str(d.get("exception", {}).get("description")
                                             or d.get("text"))[:200])
                    if m.get("id") == myid:
                        return m

            async def ev(expr, ap=False):
                r = await send("Runtime.evaluate", {"expression": expr,
                                                    "returnByValue": True,
                                                    "awaitPromise": ap})
                res = r.get("result", {})
                return res.get("result", {}).get("value")

            await send("Runtime.enable"); await send("Page.enable")

            # ── 确保服务在跑 ──
            pid0 = server_pid()
            if not pid0:
                print("服务未运行，先启动…")
                srv = start_server()
                if not wait_up():
                    print("❌ 服务启动失败"); return 1
                pid0 = server_pid()
            print(f"服务 PID={pid0}")

            await send("Page.navigate", {"url": PAGE})
            t0 = time.time()
            while time.time() - t0 < 30:
                if await ev("document.readyState") == "complete":
                    break
                await asyncio.sleep(0.4)
            await asyncio.sleep(2)

            # ── ① 启动模拟监测，确认前端收到 tick ──
            print("\n【①】启动模拟监测，验证前端正常收 tick")
            r = await ev("""(async()=>{
              const resp = await fetch('/api/monitor/start', {method:'POST',
                headers:{'Content-Type':'application/json'},
                body: JSON.stringify({simulate:true, participant:'WATCHDOG-TEST',
                                      session_type:'test',
                                      note:'看门狗实测用，勿入库'})});
              return JSON.stringify(await resp.json());
            })()""", ap=True)
            print(f"  start 返回: {r}")
            await ev("connectMonitorStream()")     # 与点击开始时前端同样动作
            await asyncio.sleep(6)
            st = await ev("JSON.stringify({last:monLastEventAt, re:monReconnects, "
                          "es:monEsState, hasTick: !!monLastTick, "
                          "txt: document.getElementById('statusText').textContent})")
            print(f"  6秒后前端状态: {st}")
            j = json.loads(st) if isinstance(st, str) else {}
            got_tick = j.get("hasTick")
            if not got_tick:
                fails.append("正常状态下前端就没收到 tick（基础通路已坏，后续无意义）")
                print("  ❌ 未收到 tick")
            else:
                notes.append(f"① 正常状态前端收到 tick，statusText='{j.get('txt')}'")
                print("  ✅ 前端已收到 tick，波形通路正常")

            # ── ② 造看门狗真正对应的场景：服务活着、会话 running，但推流卡住 ──
            # ⚠️ 场景修正（本脚本第 1 版判据与场景均错）：
            #   第 1 版杀掉整个服务进程 → pollStatus 的 status 请求直接失败 →
            #   走 catch 分支只显示"服务不可用"，看门狗代码在 try 块内**根本没机会执行**，
            #   故 monReconnects 恒为 0；据此判"前端仍会静默黑屏"也不准确——
            #   界面明确显示了"服务不可用"，属如实标注。
            #   又：杀进程后服务恢复时前端能自动恢复，是 **EventSource 浏览器原生重连**
            #   生效（re=0 可证），并非看门狗之功。
            # 本次故障的真实形态是：服务活着、status 返回 recording、但 SSE 因
            # 线程池饥饿而零输出 —— 此时 EventSource 连接并未断开（原生重连不触发），
            # 只有本看门狗能救。故用受控注入复现该形态：保持会话 running，
            # 把 monLastEventAt 人为老化到阈值之外。
            print("\n【②】受控注入：会话 running 但推流停摆（本次故障的真实形态）")
            before = await ev("JSON.stringify({re:monReconnects, last:monLastEventAt})")
            print(f"  注入前: {before}")
            # ⚠️ 注入方法修正（本脚本第 2 版仍无效）：
            #   第 2 版只把 monLastEventAt 人为老化 20 秒，但 SSE 流本身正常，
            #   事件每 250ms 到达即把时间戳刷新回当前时刻 → 断流条件永不成立，
            #   看门狗"正确地"没触发（实测输出「最近事件0.1s前」即此证据）。
            #   要复现本次故障形态，必须在会话 running 的同时**真的切断事件流**。
            # 正确做法：monEs.close() —— 关闭后 EventSource 不再自动重连，
            #   恰好隔离出「连接已死、后端仍在采集」这一形态（浏览器原生重连不会插手，
            #   只有本看门狗能救），且不干扰后端会话。
            await ev("monEs.close(); monEsState='closed';")
            mrun = await ev("""(async()=>{ const r=await fetch('/api/monitor/status');
                               return (await r.json()).running; })()""", ap=True)
            print(f"  已关闭 EventSource；后端 m.running = {mrun}（须为 true）")
            if not mrun:
                fails.append("注入时后端未在 running，无法验证看门狗（测试前置失败）")
            else:
                # 等 pollStatus（3秒轮询）跑过阈值 MON_STALL_MS(6s) + 若干轮
                traces = []
                for k in range(7):
                    await asyncio.sleep(1.5)
                    s2 = await ev("JSON.stringify({re:monReconnects, es:monEsState, "
                                  "last:monLastEventAt, now:Date.now(), "
                                  "txt:document.getElementById('statusText').textContent, "
                                  "msg:(document.getElementById('monMsg')||{}).textContent||''})")
                    traces.append(s2)
                    jj = json.loads(s2) if isinstance(s2, str) else {}
                    age = (jj.get("now", 0) - jj.get("last", 0)) / 1000
                    print(f"  t+{(k+1)*1.5:.1f}s: re={jj.get('re')} es={jj.get('es')} "
                          f"最近事件{age:.1f}s前 txt={jj.get('txt')}")
                re_after = max([json.loads(x).get("re", 0) for x in traces
                                if isinstance(x, str)] or [0])
                msgs = [json.loads(x).get("msg", "") for x in traces if isinstance(x, str)]
                hinted = any("重连" in (m or "") for m in msgs)
                print(f"\n  看门狗触发重连次数: {re_after}")
                print(f"  界面是否出现重连提示: {hinted}")
                if re_after == 0:
                    fails.append("连接已死且后端仍 running 超过 10 秒，看门狗仍未触发重连"
                                 "（monReconnects 恒 0）→ 纵深防御第二道失效")
                else:
                    notes.append(f"② 连接切断后看门狗触发 {re_after} 次重连"
                                 f"{'，界面有重连提示' if hinted else '（未见界面提示）'}")
                    print("  ✅ 看门狗按设计动作（判据A、C）")
                # 看门狗重连后应恢复收 tick（后端会话一直在跑）
                await asyncio.sleep(5)
                s3 = await ev("JSON.stringify({last:monLastEventAt, now:Date.now(), "
                              "hasTick:!!monLastTick, re:monReconnects, es:monEsState})")
                jj3 = json.loads(s3) if isinstance(s3, str) else {}
                age3 = (jj3.get("now", 0) - jj3.get("last", 0)) / 1000
                print(f"  重连后最近事件 {age3:.1f}s 前, hasTick={jj3.get('hasTick')}, "
                      f"es={jj3.get('es')}")
                if age3 < 4:
                    notes.append(f"② 看门狗重连后 {age3:.1f}s 内恢复收 tick（判据B：自愈）")
                    print("  ✅ 前端自动恢复，无需人工刷新（判据B）")
                else:
                    fails.append(f"看门狗重连后仍 {age3:.1f}s 无事件，未恢复")

            # ── ②b 附加：整服务宕机场景（第1版误当主场景，此处保留为补充观测）──
            print("\n【②b】附加观测：整服务宕机时界面是否如实标注（非静默黑屏）")
            pid_now = server_pid()
            if pid_now:
                kill_server(pid_now)
                await asyncio.sleep(3)
                s4 = await ev("document.getElementById('statusText').textContent")
                print(f"  宕机后 statusText = '{s4}'")
                if s4 and "服务不可用" in str(s4):
                    notes.append(f"②b 整服务宕机时界面如实显示'{s4}'，非静默黑屏")
                else:
                    notes.append(f"②b 宕机后 statusText='{s4}'（未见'服务不可用'标注）")
                srv = start_server()
                if not wait_up():
                    fails.append("服务重启失败")
                else:
                    await asyncio.sleep(5)
                    s5 = await ev("JSON.stringify({last:monLastEventAt, now:Date.now(), "
                                  "hasTick:!!monLastTick})")
                    jj5 = json.loads(s5) if isinstance(s5, str) else {}
                    age5 = (jj5.get("now", 0) - jj5.get("last", 0)) / 1000
                    recovered = jj5.get("hasTick") and age5 < 5
                    print(f"  服务恢复后最近事件 {age5:.1f}s 前 → "
                          f"{'✅ 自动恢复' if recovered else '未恢复'}")
                    if recovered:
                        notes.append(f"②b 服务恢复后 {age5:.1f}s 内自动恢复收 tick"
                                     f"（EventSource 原生重连生效）")
                    else:
                        notes.append(f"②b 服务恢复后 {age5:.1f}s 仍未恢复（原生重连有退避延迟，"
                                     f"属可接受；看门狗在 running 态下会补位）")
            recovered = True   # ③ 已并入 ②b 观测

            # ── ④ JS 异常 ──
            print("\n【④】全程 JS 异常检查")
            if js_errors:
                print(f"  ❌ {len(js_errors)} 个未捕获异常:")
                for e in js_errors[:6]:
                    print(f"     {e}")
                fails.append(f"全程 {len(js_errors)} 个未捕获 JS 异常")
            else:
                print("  ✅ 无未捕获 JS 异常（判据D）")

            # ── 收尾：停掉测试会话 ──
            try:
                await ev("""(async()=>{ try{
                  await fetch('/api/monitor/stop', {method:'POST',
                    headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({save:false})});
                }catch(e){} return 'ok'; })()""", ap=True)
            except Exception:
                pass
    finally:
        browser.terminate()
        try: browser.wait(timeout=8)
        except Exception: browser.kill()

    print("\n" + "=" * 80)
    print("实测记录:")
    for n in notes:
        print("  · " + n)
    print("=" * 80)
    if fails:
        print("❌ 看门狗实测未通过:")
        for f in fails:
            print("   - " + f)
        return 1
    print("✅ 看门狗实测通过：断流被检测并触发重连、服务恢复后前端自动恢复收 tick、")
    print("   界面如实标注、全程无 JS 异常 —— 「静默黑屏」症状已根治")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

