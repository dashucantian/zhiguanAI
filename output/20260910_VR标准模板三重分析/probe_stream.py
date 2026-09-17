"""探针：以第二观察客户端连 /api/monitor/stream（SSE），判断后端推流是否活着。
成本声明：MONITOR.events 为单消费队列，探针连接期间前端屏幕会暂缺部分事件；
数据累积与保存在 buf 内，不受推流影响。探针限时10秒后即断开。
判据：
  收到 tick 且 elapsed 递增 → worker 活着，问题在前端接收/渲染
  只收到 ping/无 tick      → worker 线程已死或卡死（status 却仍 recording）
"""
import json, sys, time, urllib.request

URL = "http://127.0.0.1:8777/api/monitor/stream"
DUR = 10.0

def main():
    req = urllib.request.Request(URL, headers={"Accept": "text/event-stream",
                                               "Cache-Control": "no-cache"})
    ticks = pings = others = 0
    first = last = None
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=DUR + 6) as r:
            buf = b""
            while time.time() - t0 < DUR:
                chunk = r.read(1)
                if not chunk:
                    break
                buf += chunk
                while b"\n\n" in buf:
                    raw, buf = buf.split(b"\n\n", 1)
                    raw = raw.decode("utf-8", "replace")
                    if raw.startswith(":"):
                        pings += 1
                        continue
                    if not raw.startswith("data:"):
                        others += 1
                        continue
                    d = json.loads(raw[5:].strip())
                    t = d.get("type", "?")
                    if t == "tick":
                        ticks += 1
                        if first is None:
                            first = d
                        last = d
                    else:
                        others += 1
                        print(f"  非tick事件: type={t} text={str(d.get('text'))[:60]}")
    except Exception as e:
        print(f"连接异常: {type(e).__name__}: {e}")
    print(f"\n{DUR:.0f}秒观察结果: tick={ticks} ping={pings} 其他={others}")
    if first and last:
        w = first.get("wave") or {}
        print(f"首tick: elapsed={first.get('elapsed')} connected={first.get('connected')} "
              f"packets={first.get('packets')} bands={'有' if first.get('bands') else 'None'}")
        print(f"  wave通道: {{{', '.join(f'{k}:{len(v)}点' for k, v in w.items()) or '空'}}}")
        print(f"末tick: elapsed={last.get('elapsed')} packets={last.get('packets')}")
        if last.get("elapsed") != first.get("elapsed"):
            print("判定: worker 活着且推流递增 → 问题在前端接收/渲染层")
        else:
            print("判定: 仅单个tick不递增 → worker 卡在循环内某处")
    elif pings and not ticks:
        print("判定: 只有心跳ping、零tick → worker 线程已死或卡死（status却仍recording）")
    else:
        print("判定: 连接即无输出 → SSE生成器异常")
    return 0

sys.exit(main())
