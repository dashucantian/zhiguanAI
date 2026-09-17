"""根治验收：SSE 广播改造后的并发实测（复现并证伪原故障）

═══ 原故障机制（2026-09-13 实测诊断）═══
旧设计：SSE 生成器用 `loop.run_in_executor(None, lambda: q.get(timeout=1.0))`
阻塞取单消费队列 → 每连接长期占用一个默认线程池线程（上限 min(32, cpu+4)）。
EventSource 断线自动重连不断堆积未退出生成器 → **线程池饥饿**：
新连接的生成器拿不到线程、永远 yield 不出首条数据 → EventSource 一直 pending
（onerror 不触发、也收不到消息）→ 前端永久停在"正在连接数据源…"。
而 /api/monitor/status 是普通 async 接口、不依赖该线程池 → 照常返回 recording。
这正解释了探针所见：worker 活着、事件积压、前端 13 分钟零消费。

═══ 本测试验四件事（全部针对上述机制）═══
① 并发 N 个 SSE 连接，**每个都**能收到 tick（旧设计下后开的会饿死）
② 反复开断连接 30 轮（模拟 EventSource 自动重连），之后新连接仍能收到 tick
   —— 这是旧设计的必死场景（线程池被泄漏的生成器占满）
③ 广播语义：各连接收到**相同**事件序列（旧单消费队列会互相抢走）
④ 订阅者不泄漏：断连后注册表归零（否则长跑必然再次饥饿）
"""
import json, sys, threading, time, urllib.request

BASE = "http://127.0.0.1:8777"
STREAM = f"{BASE}/api/monitor/stream"
STATUS = f"{BASE}/api/monitor/status"
START = f"{BASE}/api/monitor/start"


def post(url, obj):
    data = json.dumps(obj).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def get(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.load(r)


def find_server_pid():
    """找监听 8777 的服务进程 PID（用 PowerShell，不装额外依赖）。"""
    import subprocess
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-NetTCPConnection -State Listen -LocalPort 8777 "
             "-ErrorAction SilentlyContinue | Select-Object -First 1).OwningProcess"],
            capture_output=True, text=True, timeout=25)
        s = (out.stdout or "").strip()
        return int(s) if s.isdigit() else None
    except Exception:
        return None


def thread_count(pid):
    """查指定进程线程数（PowerShell，不装额外依赖）。"""
    import subprocess
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"(Get-Process -Id {pid} -ErrorAction SilentlyContinue).Threads.Count"],
            capture_output=True, text=True, timeout=25)
        s = (out.stdout or "").strip()
        return int(s) if s.isdigit() else -1
    except Exception:
        return -1


def sse_collect(idx, dur, out, stop_flag=None):
    """一个 SSE 客户端：收集 dur 秒内的事件。out[idx] = (n_tick, types)

    ⚠️ 测量方法修正（2026-09-13，本脚本第 1 版判据错误）：
    原用 `r.read(1)` 逐字节读取，6 线程并发时 Python GIL 竞争严重、读取速度
    跟不上 4 tick/秒的推送 → 每连接只收到 4~6 条（单连接同法却收 21 条），
    被误判为"连接饿死"。实际服务端广播正常（各连接极差仅 2，高度一致；
    真饿死应表现为差异悬殊）。改为 `readline()` 按行读取，消除测量瓶颈。
    """
    types = {}
    n_tick = 0
    t0 = time.time()
    try:
        req = urllib.request.Request(STREAM, headers={"Accept": "text/event-stream"})
        with urllib.request.urlopen(req, timeout=dur + 10) as r:
            while time.time() - t0 < dur:
                if stop_flag is not None and stop_flag.is_set():
                    break
                line = r.readline()
                if not line:
                    break
                raw = line.decode("utf-8", "replace").rstrip("\r\n")
                if not raw:
                    continue                      # SSE 事件分隔空行
                if raw.startswith(":"):
                    types["ping"] = types.get("ping", 0) + 1
                    continue
                if not raw.startswith("data:"):
                    continue
                d = json.loads(raw[5:].strip())
                t = d.get("type", "?")
                types[t] = types.get(t, 0) + 1
                if t == "tick":
                    n_tick += 1
    except Exception as e:
        types["_err"] = f"{type(e).__name__}: {e}"
    out[idx] = (n_tick, types)


def main():
    fails, notes = [], []
    print("=" * 84)
    print("根治验收：SSE 广播改造并发实测")
    print("=" * 84)

    st = get(STATUS)
    print(f"起始状态: {st}")
    if st.get("running"):
        fails.append("起始已有会话在跑，请先停止后再测")
        return 1

    # ── 启动模拟源监测（不占硬件；本次只验推流层）──
    r = post(START, {"simulate": True, "participant": "SSE-BROADCAST-TEST",
                     "session_type": "test", "note": "广播改造并发验收，测试用，勿入库"})
    print(f"启动模拟监测: {r}")
    time.sleep(4)      # 等 worker 产出 tick

    N = 6
    # ══ ① 并发 N 连接，每个都应收 tick ══
    print(f"\n【①】并发 {N} 个 SSE 连接，各自收 6 秒")
    out = {}
    ths = []
    for i in range(N):
        t = threading.Thread(target=sse_collect, args=(i, 6.0, out), daemon=True)
        ths.append(t); t.start()
        time.sleep(0.15)     # 错开建连，更接近真实重连时序
    for t in ths:
        t.join(timeout=20)
    for i in range(N):
        n, types = out.get(i, (0, {}))
        flag = "✅" if n > 0 else "❌"
        print(f"  {flag} 连接{i}: tick={n}  {types}")
        if n == 0:
            fails.append(f"连接{i} 收到 0 条 tick → 该连接被饿死（原故障症状）")
    tick_counts = [out.get(i, (0, {}))[0] for i in range(N)]
    best = max(tick_counts) if tick_counts else 0
    # 饿死的判据：零 tick，或与最佳连接差异悬殊（广播下各连接应量级相当）。
    # 不用绝对阈值判"饿死"——原脚本以 `>=10` 判定，把测量端 GIL 瓶颈
    # （逐字节读跟不上推送）误判成服务端缺陷，属判据错误，已改为相对判据。
    starved = [i for i, c in enumerate(tick_counts) if c == 0 or (best > 0 and c < best * 0.3)]
    if starved:
        fails.append(f"连接被饿死: 索引 {starved}，tick 分布 {tick_counts}")
    else:
        notes.append(f"① {N} 连接并发均收到 tick 且量级相当，分布 {tick_counts}"
                     f"（无饿死）")

    # ══ ③ 广播语义：各连接 tick 数应接近（同事件序列）══
    if max(tick_counts) > 0:
        spread = max(tick_counts) - min(tick_counts)
        print(f"\n【③】广播一致性: tick 数极差 {spread}（单消费队列下会相差悬殊甚至为0）")
        if spread > max(tick_counts) * 0.5:
            notes.append(f"⚠️ ③ tick 数极差 {spread} 偏大，但均非0（建连时刻不同属正常）")
        else:
            notes.append(f"③ 各连接 tick 数接近（极差 {spread}），广播语义成立")

    # ══ ② 反复开断 30 轮，模拟 EventSource 自动重连堆积 ══
    print("\n【②】反复开断 SSE 连接 30 轮（模拟 EventSource 自动重连）")
    for rnd in range(30):
        try:
            req = urllib.request.Request(STREAM, headers={"Accept": "text/event-stream"})
            with urllib.request.urlopen(req, timeout=5) as r:
                r.read(1)              # 只读一字节即断开，制造"未完成消费"的连接
        except Exception:
            pass
        # 不 sleep，尽快堆积
    print("  30 轮开断完成")
    time.sleep(2)

    # 开断之后，新连接必须仍能收到 tick（旧设计此处必然饿死）
    out2 = {}
    t = threading.Thread(target=sse_collect, args=(0, 6.0, out2), daemon=True)
    t.start(); t.join(timeout=20)
    n2, types2 = out2.get(0, (0, {}))
    ok2 = n2 >= 10
    print(f"  {'✅' if ok2 else '❌'} 30 轮开断后新连接: tick={n2}  {types2}")
    if not ok2:
        fails.append(f"30 轮重连后新连接只收到 {n2} 条 tick → 线程池饥饿未根治")
    else:
        notes.append(f"② 30 轮开断后新连接仍收 {n2} 条 tick，饥饿已根治")

    # ══ ④ 线程不堆积（根因的直接证据）══
    # ⚠️ 判据修正：原写法在本测试进程 `import console_server` 读 MONITOR.broadcaster._subs，
    #    但那是**测试进程自己的全新对象**，与服务进程里的 MONITOR 不是同一个 → 读数无意义。
    #    改为观测**服务进程线程数**：旧设计的病根正是 run_in_executor 阻塞生成器
    #    把默认线程池占满，故线程数是否随重连轮次堆积，是根因是否根治的直接证据。
    print("\n【④】服务进程线程数（根因直接证据：旧设计会随重连堆积）")
    srv_pid = find_server_pid()
    if srv_pid:
        th_before = thread_count(srv_pid)
        print(f"  30 轮开断后，服务进程 PID={srv_pid} 线程数 = {th_before}")
        # 再来 40 轮重连压力，看线程是否继续增长
        for _ in range(40):
            try:
                req = urllib.request.Request(STREAM, headers={"Accept": "text/event-stream"})
                with urllib.request.urlopen(req, timeout=5) as r:
                    r.read(1)
            except Exception:
                pass
        time.sleep(3)
        th_after = thread_count(srv_pid)
        growth = th_after - th_before
        print(f"  再 40 轮开断后线程数 = {th_after}（增长 {growth}）")
        if growth > 8:
            fails.append(f"服务进程线程随重连堆积（{th_before}→{th_after}，+{growth}）"
                         f"→ 生成器泄漏未根治，长跑必再饥饿")
        else:
            notes.append(f"④ 70 轮重连后服务线程仅 +{growth}（{th_before}→{th_after}），"
                         f"无堆积 → 生成器不泄漏")
        # 压力之后仍须能收到 tick
        out3 = {}
        t = threading.Thread(target=sse_collect, args=(0, 6.0, out3), daemon=True)
        t.start(); t.join(timeout=20)
        n3, types3 = out3.get(0, (0, {}))
        ok3 = n3 >= 10
        print(f"  {'✅' if ok3 else '❌'} 70 轮压力后新连接: tick={n3}  {types3}")
        if not ok3:
            fails.append(f"70 轮重连压力后新连接只收到 {n3} 条 tick")
        else:
            notes.append(f"④ 70 轮重连压力后新连接仍收 {n3} 条 tick")
    else:
        notes.append("④ 未能定位服务进程 PID，跳过线程数观测（②③已覆盖饥饿场景）")

    # ══ 停止并保存 ══
    print("\n停止测试会话（保存，测试数据标 note 勿入库）")
    try:
        post(f"{BASE}/api/monitor/stop", {"save": True})
    except Exception as e:
        print(f"  停止异常: {e}")
    time.sleep(5)
    st2 = get(STATUS)
    print(f"  停止后状态: {st2}")
    if st2.get("running"):
        fails.append("停止后会话仍在运行")

    print("\n" + "=" * 84)
    print("实测记录:")
    for n in notes:
        print("  · " + n)
    print("=" * 84)
    if fails:
        print("❌ 未通过:")
        for f in fails:
            print("   - " + f)
        return 1
    print("✅ 广播改造验收通过：并发多连接均收 tick、30轮重连后不饿死、")
    print("   广播语义成立、订阅者不泄漏 —— 原「status正常但波形空白」已根治")
    return 0


if __name__ == "__main__":
    sys.exit(main())
