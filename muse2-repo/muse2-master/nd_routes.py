"""NeuraDock 接入路由（nd_routes）——把 nd_hub 接到实践驾驶舱，**只增不改**。

〔2026-10-01 W1·AI-005·DeepSeek(deepseek-flash) 建〕

**为什么做成"注册式模块"而不是直接写进 console_server.py**：
建此文件时 `console_server.py` 上压着另一窗（W1·AI-008，ZG-080 `/demo` 路由）未提交的改动，
按并发纪律③④不得叠加；且若对方以 `git commit -- console_server.py` 提交，会把本窗改动一并扫走
（KZ-0927-W3a 模式）。故本模块把改动面压到**最小两行**：

    import nd_routes
    nd_routes.register(app)

**不建平行体系（红线5）**：本模块只注册新增路由，不改既有端点、不动既有数据流。
**与既有 `/api/ndmetrics` 的分工**：指标代理 W1 已有（旁证源），本模块**不重复实现**，
只补"发现／拉起／扇出中转／数据源选择"这四件它没有的事。
"""
import threading

import nd_hub

# ── 模块级单例（一个进程一个枢纽） ──────────────────────────────────────
_hub = None
_hub_lock = threading.Lock()


def hub():
    return _hub


def start_hub(listen_port=0, idle_stop_sec=30.0):
    """起扇出中转；已在跑则原样返回。返回 (port, bridge)。"""
    global _hub
    with _hub_lock:
        if _hub is not None and _hub.port:
            return _hub.port, _hub
        br = nd_hub.FanoutBridge(listen_host="127.0.0.1",
                                 listen_port=listen_port,
                                 idle_stop_sec=idle_stop_sec)
        port = br.start()
        _hub = br
        return port, br


def stop_hub():
    global _hub
    with _hub_lock:
        if _hub is not None:
            _hub.stop()
            _hub = None
    return True


def snapshot():
    """驾驶舱要看的全部状态（只读，不启动任何东西）。"""
    br = _hub
    return {
        "app": {
            "running": nd_hub.is_running(nd_hub.APP_PROC_NAME),
            "endpoint": nd_hub.find_app_endpoint(),      # ⚠ 局域网 IP，非回环
            "exe": nd_hub.APP_EXE,
        },
        "platform": {
            "running": nd_hub.is_running(nd_hub.PLATFORM_PROC_NAME),
            "port": nd_hub.discover_platform_port(),     # ⚠ 每次启动随机
            "exe": nd_hub.PLATFORM_EXE,
        },
        "hub": (br.stats() if br else None),
        "discovery_error": nd_hub.last_discovery_error,
    }


def register(app):
    """把路由注册到既有 FastAPI app。**只在 import 处加两行，不改 console_server.py 任何既有代码。**"""
    from fastapi import Body, HTTPException

    @app.get("/api/nd/status")
    def nd_status():
        """NeuraDock 接入现状（只读）。前端状态灯／端口回填都读这一支。"""
        return snapshot()

    @app.post("/api/nd/launch")
    def nd_launch(payload: dict = Body(default={})):
        """缺谁起谁（单例守卫，已在跑就不重起）。**只启动、不停止。**

        body: {"which": "app" | "platform" | "both"}
        """
        which = (payload or {}).get("which", "both")
        out = {}
        if which in ("app", "both"):
            launched, msg = nd_hub.launch_if_needed(nd_hub.APP_EXE, nd_hub.APP_PROC_NAME)
            out["app"] = {"launched": launched, "msg": msg}
        if which in ("platform", "both"):
            launched, msg = nd_hub.launch_if_needed(nd_hub.PLATFORM_EXE, nd_hub.PLATFORM_PROC_NAME)
            out["platform"] = {"launched": launched, "msg": msg}
        out["status"] = snapshot()
        return out

    @app.post("/api/nd/hub/start")
    def nd_hub_start(payload: dict = Body(default={})):
        """起扇出中转。返回枢纽地址——**下游（驾驶舱与平台）都应连这个回环口**。"""
        port, br = start_hub(listen_port=int((payload or {}).get("port", 0)))
        return {"ok": True, "hub_port": port, "hub_addr": f"127.0.0.1:{port}",
                "stats": br.stats(),
                "note": "驾驶舱数据源填 127.0.0.1:<hub_port>；平台用 /api/nd/platform/connect 指向它"}

    @app.post("/api/nd/hub/stop")
    def nd_hub_stop():
        stop_hub()
        return {"ok": True, "status": snapshot()}

    @app.get("/api/nd/platform/status")
    def nd_platform_status():
        """只读转发平台 /api/v1/status（拿端口自述、能力清单）。"""
        port = nd_hub.discover_platform_port()
        if not port:
            raise HTTPException(status_code=502,
                                detail="指标平台未运行或端口未发现。请先用「一键启动」拉起它。")
        import json as _json
        import urllib.request
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v1/status", timeout=6) as r:
                return _json.loads(r.read().decode("utf-8"))
        except Exception as e:                              # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"读平台状态失败：{type(e).__name__}: {e}")

    @app.post("/api/nd/platform/connect")
    def nd_platform_connect(payload: dict = Body(default={})):
        """把平台的数据源切到 TCP 并指向指定目标。

        body: {"target": "hub"}   → 指向**本枢纽回环口**（推荐：解单客户端限制）
              {"target": "app"}   → 直连 1.2.0 的数据服务（**用它的局域网 IP，不是回环**）
              {"host": "...", "port": N} → 显式指定

        ⚠ 实测：`connect_tcp("127.0.0.1", 9600)` **必失败**——1.2.0 只绑局域网 IP。
        ⚠ 实测：该服务**只服务一个客户端**，谁后连谁拿到、先连的静默失效 ⇒ 推荐 target=hub。
        """
        p = payload or {}
        port = nd_hub.discover_platform_port()
        if not port:
            raise HTTPException(status_code=502, detail="指标平台未运行或端口未发现。")
        target = p.get("target", "hub")
        if target == "hub":
            hub_port, _ = start_hub()
            host, tcp_port = "127.0.0.1", hub_port
        elif target == "app":
            ep = nd_hub.find_app_endpoint()
            if not ep:
                raise HTTPException(status_code=502,
                                    detail="未发现 1.2.0 数据服务（需先启动它并点「Open data sources」）。")
            host, tcp_port = ep
        else:
            host, tcp_port = p.get("host"), p.get("port")
            if not host or not tcp_port:
                raise HTTPException(status_code=400, detail="target 非 hub/app 时必须给 host 与 port。")
        try:
            res = nd_hub.platform_connect_tcp(port, host, int(tcp_port))
        except Exception as e:                              # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"平台动作失败：{type(e).__name__}: {e}")
        return {"ok": bool(res.get("ok")), "target": target,
                "pointed_at": f"{host}:{tcp_port}", "platform_reply_ok": res.get("ok")}

    return app


# ══════════════════════════════════════════════════════════════════════
# 自测：起一个最小 FastAPI app、注册本模块、真打每个端点
#   —— 不需要 console_server.py、不需要任何厂商程序
# ══════════════════════════════════════════════════════════════════════
def _selftest():
    import json as _json
    import socket as _socket
    import time as _time
    import urllib.request

    try:
        import uvicorn
        from fastapi import FastAPI
    except Exception as e:                                  # noqa: BLE001
        print(f"[selftest] 跳过：fastapi/uvicorn 不可用（{type(e).__name__}: {e}）")
        return 0

    app = FastAPI()
    register(app)

    s = _socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()

    cfg = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    srv = uvicorn.Server(cfg)
    threading.Thread(target=srv.run, daemon=True).start()
    for _ in range(60):
        if getattr(srv, "started", False):
            break
        _time.sleep(0.1)
    print(f"[selftest] 测试服务 127.0.0.1:{port}")

    def get(path):
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=10) as r:
            return _json.loads(r.read().decode("utf-8"))

    def post(path, body):
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
                                     data=_json.dumps(body).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return _json.loads(r.read().decode("utf-8"))

    ok = True

    st = get("/api/nd/status")
    print(f"[selftest] /api/nd/status → app.running={st['app']['running']} "
          f"platform.running={st['platform']['running']} platform.port={st['platform']['port']} "
          f"hub={st['hub']} err={st['discovery_error']}")
    if not isinstance(st.get("app"), dict) or "running" not in st["app"]:
        print("[selftest] ❌ status 结构不对")
        ok = False

    hs = post("/api/nd/hub/start", {})
    print(f"[selftest] /api/nd/hub/start → hub_port={hs['hub_port']}  {hs['hub_addr']}")
    if not hs.get("hub_port"):
        print("[selftest] ❌ 枢纽未起")
        ok = False

    st2 = get("/api/nd/status")
    if not st2.get("hub") or not st2["hub"].get("listen"):
        print("[selftest] ❌ status 未反映枢纽已在跑")
        ok = False
    else:
        print(f"[selftest] 枢纽已被 status 反映：{st2['hub']['listen']}")

    # 平台未运行时，route 应给**可操作的中文报错**而不是崩
    try:
        get("/api/nd/platform/status")
        print("[selftest] （平台在跑，直接读到状态——正常）")
    except urllib.error.HTTPError as e:
        detail = _json.loads(e.read().decode("utf-8")).get("detail", "")
        print(f"[selftest] 平台状态端点在中止时返回 HTTP {e.code}：{detail}")
        if e.code != 502 or not detail:
            print("[selftest] ❌ 应为 502 ＋ 中文可操作提示")
            ok = False

    stp = post("/api/nd/hub/stop", {})
    print(f"[selftest] /api/nd/hub/stop → ok={stp.get('ok')}")
    srv.should_exit = True
    _time.sleep(0.5)
    print("[selftest] " + ("✅ 全过：注册式接线成立（两行接入、端点齐、错误可操作）"
                           if ok else "❌ 有失败项，见上"))
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    print("nd_routes：请用 --selftest 跑自测，或由 console_server.py import 后 register(app)")
