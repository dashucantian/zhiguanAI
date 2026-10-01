"""NeuraDock 接入枢纽（nd_hub）——扇出中转 ＋ 端口发现 ＋ 进程拉起。

〔2026-10-01 W1·AI-005·DeepSeek(deepseek-flash) 建〕
依据：真机实测（见 `01_项目管理/20260930_乙案探索方案_两APP嵌入实践驾驶舱_可测分层与判据_v1.md` §十）
实测撞出三个硬约束：
  1. **1.2.0 的数据服务只绑局域网 IP**（例 192.168.188.105:9600），**不绑回环** ⇒ 写 `127.0.0.1:9600` 必失败；
  2. **该服务只服务一个客户端**：第二客户端一连，第一客户端被静默踢掉，且**不自愈**；
  3. 该 IP **随网络环境漂移**，写死即脆。

本模块用"扇出中转"一并解掉：
      1.2.0:9600（单客户端）
            ↑ 本枢纽独占这一条
      ┌─────┴─────┐
   驾驶舱       指标平台（连本枢纽的回环口，不再直连 1.2.0）
   ⇒ 下游都连 `127.0.0.1:<枢纽口>`，谁先谁后都不再互踢；IP 漂移由枢纽内部吸收。

**不建平行体系**（红线5）：本模块只提供"取数与拉起"的机制，路由与界面仍归 `console_server.py`／`console.html`。
**只读边界**：本模块不解析、不改写 EEG 数值，只做**逐行原样转发**（字节级转发，不做任何数值加工）。
"""
import os
import socket
import struct
import subprocess
import sys
import threading
import time

# ── 已知的外部程序（可由调用方覆盖） ─────────────────────────────────────
APP_EXE = r"C:\Program Files\Pulse\NeuraDock\NeuraDock.exe"
PLATFORM_EXE = os.path.join(os.path.expanduser("~"), "Desktop",
                            "NeuraDock_Developer_Metrics.exe")
APP_PROC_NAME = "NeuraDock"
PLATFORM_PROC_NAME = "NeuraDock_Developer_Metrics"

UPSTREAM_RECONNECT_SEC = 3.0
START_CMD = b"start"

# 发现失败的原因写在这里——**失败必须留痕，不静默吞**
# （教训：本模块首版用 subprocess 读输出，在受限环境下被拦后被我 except 吞掉，
#   表现为"进程明明在跑却报未运行"。静默失败＝没有告警。）
last_discovery_error = None


# ══════════════════════════════════════════════════════════════════════
# 一、发现：进程 → 监听端口（甲案③手法；已实测可行）
# ══════════════════════════════════════════════════════════════════════
def _tcp_listen_rows():
    """直接问系统要 TCP 监听表 ⇒ [(ip, port, pid)]。

    **不用 subprocess/netstat**：①避免读子进程输出（受限环境下管道可能被拦）；
    ②避免 netstat 文本解析受语言/版本影响。ctypes 调 iphlpapi，零依赖、零文本解析。
    """
    global last_discovery_error
    try:
        import ctypes
        from ctypes import wintypes

        AF_INET, TCP_TABLE_OWNER_PID_ALL, MIB_TCP_STATE_LISTEN = 2, 5, 2

        class MIB_TCPROW_OWNER_PID(ctypes.Structure):
            _fields_ = [("dwState", wintypes.DWORD),
                        ("dwLocalAddr", wintypes.DWORD),
                        ("dwLocalPort", wintypes.DWORD),
                        ("dwRemoteAddr", wintypes.DWORD),
                        ("dwRemotePort", wintypes.DWORD),
                        ("dwOwningPid", wintypes.DWORD)]

        iphlpapi = ctypes.windll.iphlpapi
        size = wintypes.DWORD(0)
        iphlpapi.GetExtendedTcpTable(None, ctypes.byref(size), False, AF_INET,
                                     TCP_TABLE_OWNER_PID_ALL, 0)
        buf = ctypes.create_string_buffer(size.value)
        ret = iphlpapi.GetExtendedTcpTable(buf, ctypes.byref(size), False, AF_INET,
                                           TCP_TABLE_OWNER_PID_ALL, 0)
        if ret != 0:
            last_discovery_error = f"GetExtendedTcpTable ret={ret}"
            return []
        n = ctypes.cast(buf, ctypes.POINTER(wintypes.DWORD)).contents.value
        arr = ctypes.cast(ctypes.byref(buf, 4),
                          ctypes.POINTER(MIB_TCPROW_OWNER_PID * n)).contents
        rows = []
        for r in arr:
            if r.dwState != MIB_TCP_STATE_LISTEN:
                continue
            port = socket.ntohs(r.dwLocalPort & 0xFFFF)
            ip = socket.inet_ntoa(struct.pack("<L", r.dwLocalAddr))
            rows.append((ip, port, int(r.dwOwningPid)))
        return rows
    except Exception as e:                                  # noqa: BLE001
        last_discovery_error = f"tcp_table: {type(e).__name__}: {e}"
        return []


def _pids_by_name(name):
    """按进程名取 PID（Toolhelp 快照，不走子进程）。"""
    global last_discovery_error
    try:
        import ctypes
        from ctypes import wintypes

        TH32CS_SNAPPROCESS = 0x2
        INVALID = ctypes.c_void_p(-1).value

        class PROCESSENTRY32(ctypes.Structure):
            _fields_ = [("dwSize", wintypes.DWORD),
                        ("cntUsage", wintypes.DWORD),
                        ("th32ProcessID", wintypes.DWORD),
                        ("th32DefaultHeapID", ctypes.c_size_t),
                        ("th32ModuleID", wintypes.DWORD),
                        ("cntThreads", wintypes.DWORD),
                        ("th32ParentProcessID", wintypes.DWORD),
                        ("pcPriClassBase", ctypes.c_long),
                        ("dwFlags", wintypes.DWORD),
                        ("szExeFile", ctypes.c_char * 260)]

        k32 = ctypes.windll.kernel32
        snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snap == INVALID or snap is None:
            last_discovery_error = "CreateToolhelp32Snapshot 失败"
            return []
        try:
            entry = PROCESSENTRY32()
            entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
            pids = []
            ok = k32.Process32First(snap, ctypes.byref(entry))
            target = (name + ".exe").lower()
            while ok:
                exe = entry.szExeFile.decode("mbcs", "replace").lower()
                if exe == target:
                    pids.append(str(entry.th32ProcessID))
                ok = k32.Process32Next(snap, ctypes.byref(entry))
            return pids
        finally:
            k32.CloseHandle(snap)
    except Exception as e:                                  # noqa: BLE001
        last_discovery_error = f"pids_by_name: {type(e).__name__}: {e}"
        return []


def _listening_ports_for(pids):
    if not pids:
        return []
    want = {int(p) for p in pids}
    return sorted({port for (_ip, port, pid) in _tcp_listen_rows() if pid in want})


def discover_platform_port():
    """指标平台的 HTTP 端口（每次启动随机，故只能运行时发现）。取不到返回 None。"""
    ports = _listening_ports_for(_pids_by_name(PLATFORM_PROC_NAME))
    return ports[0] if ports else None


def find_app_endpoint():
    """1.2.0 数据服务的实际地址 (host, port)。**注意它绑局域网 IP，不是回环。**

    host 取自 TCP 表里的本地地址 ⇒ **IP 漂移自动跟随**，不必写死。
    返回 (host, port) 或 None。
    """
    pids = {int(p) for p in _pids_by_name(APP_PROC_NAME)}
    if not pids:
        return None
    for (ip, port, pid) in _tcp_listen_rows():
        if pid in pids:
            return (ip, port)
    return None


# ══════════════════════════════════════════════════════════════════════
# 二、拉起：缺谁起谁（单例守卫，绝不重复起）
# ══════════════════════════════════════════════════════════════════════
def is_running(proc_name):
    return bool(_pids_by_name(proc_name))


def _errlog_path(proc_name):
    """子进程 stderr 落盘位置（**不丢进 DEVNULL**——失败时要能说出原话）。"""
    for d in (os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                           "_analysis_tmp"),
              os.path.dirname(os.path.abspath(__file__))):
        try:
            if d and os.path.isdir(d):
                return os.path.join(d, f"_nd_launch_{proc_name}.err")
        except Exception:                                   # noqa: BLE001
            pass
    return None


def launch_if_needed(exe, proc_name, wait_sec=25.0, want_port=False, port_probe=None):
    """已在跑则不动；否则拉起并等它就绪。

    **就绪判据**：`want_port=False` → 进程出现；`want_port=True` → `port_probe()` 取到端口
    （比"进程出现"更接近"能用"——PyInstaller 单文件会先出现再因解包失败而退出）。

    返回 dict：{launched, ok, msg, pid, err}。**失败必带 `err`（子进程原话），不静默。**
    """
    if is_running(proc_name):
        return {"launched": False, "ok": True, "msg": f"{proc_name} 已在运行",
                "pid": None, "err": None}
    if not os.path.exists(exe):
        return {"launched": False, "ok": False, "msg": f"找不到可执行文件：{exe}",
                "pid": None, "err": None}

    logf = _errlog_path(proc_name)
    fh = None
    try:
        if logf:
            fh = open(logf, "w", encoding="utf-8", errors="replace")
        child = subprocess.Popen([exe], cwd=os.path.dirname(exe),
                                 stdout=(fh or subprocess.DEVNULL),
                                 stderr=(fh or subprocess.DEVNULL))
    except Exception as e:                                  # noqa: BLE001
        if fh:
            fh.close()
        return {"launched": False, "ok": False,
                "msg": f"启动失败：{type(e).__name__}: {e}", "pid": None, "err": None}

    pid = child.pid
    t0 = time.time()
    while time.time() - t0 < wait_sec:
        if want_port and port_probe:
            if port_probe():
                if fh:
                    fh.close()
                return {"launched": True, "ok": True,
                        "msg": f"{proc_name} 已就绪（端口在听）", "pid": pid, "err": None}
        elif is_running(proc_name):
            if fh:
                fh.close()
            return {"launched": True, "ok": True,
                    "msg": f"{proc_name} 已启动", "pid": pid, "err": None}
        if child.poll() is not None:                        # 已退出，不必等满
            break
        time.sleep(0.5)

    if fh:
        fh.close()
    err = None
    if logf and os.path.exists(logf):
        try:
            with open(logf, "r", encoding="utf-8", errors="replace") as f:
                err = (f.read() or "").strip() or None
        except Exception:                                   # noqa: BLE001
            pass
    exited = child.poll()
    why = (f"进程已退出（code={exited}）" if exited is not None
           else f"{wait_sec:.0f}s 内未就绪")
    return {"launched": True, "ok": False,
            "msg": f"{proc_name} {why}", "pid": pid, "err": err}


# ══════════════════════════════════════════════════════════════════════
# 三、扇出中转：独占上游，向下游原样转发
# ══════════════════════════════════════════════════════════════════════
class FanoutBridge:
    """独占 1.2.0 的唯一客户端位，把每一行**原样**转发给所有下游。

    上游懒连接：第一个下游接入时才连上游；最后一个下游断开后按 idle_stop_sec 释放上游
    （避免长期占着那个唯一的客户端位）。
    """

    def __init__(self, upstream=None, listen_host="127.0.0.1", listen_port=0,
                 idle_stop_sec=30.0, on_line=None):
        self.upstream = upstream              # (host, port) 或 None（None＝接入时自动发现）
        self.listen_host = listen_host
        self.listen_port = listen_port        # 0＝让系统挑一个空闲口
        self.idle_stop_sec = idle_stop_sec
        self.on_line = on_line                # 可选：我方自用回调（驾驶舱记录/入库走这里）

        self._srv = None
        self._port = None
        self._downstreams = []                # list[socket]
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._up_sock = None
        self._up_thread = None
        self._accept_thread = None

        self.lines_forwarded = 0
        self.upstream_connects = 0
        self.upstream_errors = 0
        self.last_error = None
        self._last_downstream_gone = time.time()

    # ── 生命周期 ────────────────────────────────────────────────────
    @property
    def port(self):
        return self._port

    def start(self):
        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind((self.listen_host, self.listen_port))
        self._srv.listen(8)
        self._port = self._srv.getsockname()[1]
        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._accept_thread.start()
        return self._port

    def stop(self):
        self._stop.set()
        try:
            if self._srv:
                self._srv.close()
        except Exception:
            pass
        self._close_upstream()
        with self._lock:
            for c in list(self._downstreams):
                try:
                    c.close()
                except Exception:
                    pass
            self._downstreams = []

    # ── 上游 ────────────────────────────────────────────────────────
    def _ensure_upstream(self):
        if self._up_thread and self._up_thread.is_alive():
            return
        self._up_thread = threading.Thread(target=self._upstream_loop, daemon=True)
        self._up_thread.start()

    def _close_upstream(self):
        try:
            if self._up_sock:
                self._up_sock.close()
        except Exception:
            pass
        self._up_sock = None

    def _upstream_loop(self):
        while not self._stop.is_set():
            with self._lock:
                n_down = len(self._downstreams)
            if n_down == 0 and (time.time() - self._last_downstream_gone) > self.idle_stop_sec:
                return                                    # 空闲自停，释放唯一客户端位
            target = self.upstream or find_app_endpoint()
            if not target:
                time.sleep(UPSTREAM_RECONNECT_SEC)
                continue
            host, port = target
            try:
                s = socket.create_connection((host, port), timeout=6)
                s.sendall(START_CMD)                      # 协议：连上必须先发 start
                self._up_sock = s
                self.upstream_connects += 1
                self.last_error = None
                buf = b""
                while not self._stop.is_set():
                    try:
                        chunk = s.recv(65536)
                    except socket.timeout:
                        continue
                    if not chunk:
                        raise ConnectionError("上游关闭了连接")
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        self._fanout(line + b"\n")
            except Exception as e:                        # noqa: BLE001
                self.upstream_errors += 1
                self.last_error = f"{type(e).__name__}: {e}"
                self._close_upstream()
                time.sleep(UPSTREAM_RECONNECT_SEC)

    def _fanout(self, raw):
        """**字节级原样**转发给所有下游，并交给可选回调。不解析、不改写。"""
        self.lines_forwarded += 1
        with self._lock:
            dead = []
            for c in self._downstreams:
                try:
                    c.sendall(raw)
                except Exception:
                    dead.append(c)
            for c in dead:
                try:
                    c.close()
                except Exception:
                    pass
                self._downstreams.remove(c)
        if self.on_line:
            try:
                self.on_line(raw)
            except Exception:
                pass

    # ── 接受下游 ────────────────────────────────────────────────────
    def _accept_loop(self):
        while not self._stop.is_set():
            try:
                conn, _ = self._srv.accept()
            except Exception:
                return
            try:
                conn.settimeout(0.5)
            except Exception:
                pass
            with self._lock:
                self._downstreams.append(conn)
            self._ensure_upstream()

    # ── 自述 ────────────────────────────────────────────────────────
    def stats(self):
        up = self.upstream or find_app_endpoint()
        return {
            "listen": f"{self.listen_host}:{self._port}",
            "downstreams": len(self._downstreams),
            "upstream": (f"{up[0]}:{up[1]}" if up else None),
            "upstream_alive": bool(self._up_sock),
            "lines_forwarded": self.lines_forwarded,
            "upstream_connects": self.upstream_connects,
            "upstream_errors": self.upstream_errors,
            "last_error": self.last_error,
        }


# ══════════════════════════════════════════════════════════════════════
# 四、L4 控制口（指标平台）——法师 2026-10-01 令「用」
# ══════════════════════════════════════════════════════════════════════
def platform_csrf(port, timeout=6):
    """取控制令牌。注意：这是平台**未公开**的内部接口，只在我方驾驶舱内使用。"""
    import urllib.request
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=timeout) as r:
        import json as _json
        return _json.loads(r.read().decode("utf-8")).get("csrf")


def platform_action(port, method, args=None, timeout=15):
    """调平台动作口：POST /api/metrics/action，头带 X-NeuraDock-Token。

    实测可用方法：connect_bluetooth / connect_usb / **connect_tcp(host, port)** /
    start_api / stop_api / set_api_metrics / scan_bluetooth / refresh_usb_ports /
    set_waveform_channel / register_custom_metric / start_simulation / reset_experience /
    initial_state / poll / start_measurement。
    """
    import json as _json
    import urllib.request
    token = platform_csrf(port, timeout=timeout)
    body = _json.dumps({"method": method, "args": list(args or [])}).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/metrics/action", data=body, method="POST",
        headers={"Content-Type": "application/json", "X-NeuraDock-Token": token or ""})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return _json.loads(r.read().decode("utf-8"))


def platform_connect_tcp(platform_port, host, tcp_port, timeout=15):
    """把平台的数据源切到 TCP 并指向 (host, tcp_port)。

    ⚠ **实测要点**：`connect_tcp("127.0.0.1", 9600)` **必失败**——1.2.0 只绑局域网 IP。
    接入本枢纽后，应指向枢纽的回环口：`platform_connect_tcp(p, "127.0.0.1", hub_port)`。
    """
    return platform_action(platform_port, "connect_tcp", [host, int(tcp_port)], timeout=timeout)


# ══════════════════════════════════════════════════════════════════════
# 五、自测：不依赖任何厂商程序，验"扇出"这一核心机制
# ══════════════════════════════════════════════════════════════════════
def selftest_report(downstream_sec=3.0, max_lines=120):
    """环回自检：**不碰真机、不进驾驶舱采集、不入库**——只验"扇出"这条链路本身。

    起一个假上游（只说协议：5 组/行、47 字段、末尾 5 常量列）→ FanoutBridge → 两个下游客户端。
    判据：①上游被独占（连接数=1）；②两个下游都收到行；③字段数原样 47；
          ④两流各自计数器连续；⑤晚接入者(B)首行不早于先接入者(A)；⑥**重叠区逐字节一致**。
    返回 dict（供路由/界面直接显示）；**不打印、不写盘**。
    """
    import threading as th

    stop = th.Event()
    checks = []

    def chk(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        return bool(ok)

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(2)
    up_port = srv.getsockname()[1]

    def upstream_loop():
        conn, _ = srv.accept()
        conn.recv(16)                                       # 收 start 握手
        i = 0
        while not stop.is_set() and i < 400:
            fields = [f"12:00:{i % 60:02d}.000", str(i)]
            for _g in range(5):
                for _ch in range(7):
                    fields.append(f"{i + _ch:.6f}")
                fields.append("0")
            fields += ["0", "0", "0", "100", "0"]            # 末尾 5 常量列（与真机一致）
            try:
                conn.sendall((",".join(fields) + "\n").encode())
            except Exception:
                return
            i += 1
            time.sleep(0.01)
        conn.close()

    th.Thread(target=upstream_loop, daemon=True).start()
    time.sleep(0.3)

    br = FanoutBridge(upstream=("127.0.0.1", up_port))
    hp = br.start()

    results = {}

    def downstream(tag):
        c = socket.create_connection(("127.0.0.1", hp), timeout=5)
        c.sendall(START_CMD)
        c.settimeout(3)
        buf = b""
        lines = []
        t0 = time.time()
        while time.time() - t0 < downstream_sec and len(lines) < max_lines:
            try:
                chunk = c.recv(65536)
            except socket.timeout:
                break
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                ln, buf = buf.split(b"\n", 1)
                lines.append(ln)
        c.close()
        results[tag] = lines

    th.Thread(target=downstream, args=("A",), daemon=True).start()
    time.sleep(0.5)
    th.Thread(target=downstream, args=("B",), daemon=True).start()
    time.sleep(downstream_sec + 0.2)

    a, b = results.get("A", []), results.get("B", [])
    chk("两个下游都收到数据", bool(a) and bool(b), f"A={len(a)} 行，B={len(b)} 行")

    def counters(lines):
        out = {}
        for ln in lines:
            f = ln.split(b",")
            try:
                out.setdefault(int(f[1]), ln)
            except Exception:                               # noqa: BLE001
                pass
        return out

    ca, cb = counters(a), counters(b)
    if a and b:
        widths = {len(x.split(b",")) for x in (a[:20] + b[:20])}
        chk("字段数原样透传 47", widths == {47}, f"实测 {sorted(widths)}")
        chk("下游A 计数器连续", sorted(ca) == list(range(min(ca), max(ca) + 1)),
            f"{min(ca)}–{max(ca)} 共 {len(ca)}")
        chk("下游B 计数器连续", sorted(cb) == list(range(min(cb), max(cb) + 1)),
            f"{min(cb)}–{max(cb)} 共 {len(cb)}")
        chk("晚接入者(B)首行不早于 A", min(cb) >= min(ca), f"B首={min(cb)} A首={min(ca)}")
        overlap = sorted(set(ca) & set(cb))
        bad = [i for i in overlap if ca[i] != cb[i]]
        chk("重叠区逐字节一致", bool(overlap) and not bad,
            f"重叠 {len(overlap)} 行" + (f"，不一致 {len(bad)} 行" if bad else "，全同"))

    st = br.stats()
    chk("上游被独占（只连一次）", st["upstream_connects"] == 1, f"connects={st['upstream_connects']}")
    chk("枢纽自述有监听地址", bool(st.get("listen")), st.get("listen") or "")

    br.stop()
    stop.set()
    try:
        srv.close()
    except Exception:
        pass

    return {"ok": all(c["ok"] for c in checks), "checks": checks,
            "hub_listen": st.get("listen"), "lines_forwarded": st.get("lines_forwarded"),
            "note": "环回自检：上游是假数据、下游是本函数自己的两个客户端——"
                    "**不进驾驶舱采集、不入库、不碰真机**。"}


def _selftest():
    """CLI 版：跑环回自检并打印逐项结论。"""
    r = selftest_report()
    for c in r["checks"]:
        print(f"[selftest] {'✅' if c['ok'] else '❌'} {c['name']}　{c['detail']}")
    print(f"[selftest] 枢纽统计: listen={r['hub_listen']} lines_forwarded={r['lines_forwarded']}")
    print("[selftest] " + ("✅ 全过：扇出机制成立（上游独占、下游多份、逐行原样）"
                           if r["ok"] else "❌ 有失败项，见上"))
    return 0 if r["ok"] else 1


def _report():
    """打印当前可发现的事实（只读，不启动任何程序）。"""
    hub = {"app_endpoint": find_app_endpoint(),
           "platform_port": discover_platform_port(),
           "app_running": is_running(APP_PROC_NAME),
           "platform_running": is_running(PLATFORM_PROC_NAME),
           "discovery_error": last_discovery_error}
    for k, v in hub.items():
        print(f"  {k} = {v}")
    if last_discovery_error:
        print("  ⚠ 发现过程有失败记录——**不要把它当成'没在跑'**，先查上面这条原因。")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    print("nd_hub 现状（只读）：")
    sys.exit(_report())
