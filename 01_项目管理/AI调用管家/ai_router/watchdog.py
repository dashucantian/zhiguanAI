"""看门狗：代理与窗口桥，谁不在了就把谁拉起来。

每几分钟跑一次，做四件事：
一、探 8791 上的代理还活着没有（真发一次 HTTP 请求，光看端口不算）。
二、探 8792 上的 Qoder 窗口桥还活着没有（同上）。
三、谁不在就请计划任务把它起起来；任务起不来就自己拉一个进程顶上。
四、把这一趟的结果记进日志——代理一条、桥一条，各记各的。

⚠2026-11-10 改：原版只探 8791，不探 8792。结果 8792 挂了几个小时没人知道，
看门狗每 5 分钟报一次「代理在跑，不用管」（17:23—21:55 报了 58 次），
而群里 @ 机器人其实没有引擎接。法师当日字「看门狗改成盯 8792」后补上这一路。

不碰上游密钥，不出网（除了往本机 8791／8792 各发的那一探）。
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("AI_ROUTER_DATA_DIR") or (BASE_DIR / "数据"))
LOG_FILE = DATA_DIR / "看门狗.log"
PROXY_TASK = "AI调用管家代理"
PORT = int(os.environ.get("AI_ROUTER_PORT", "8791"))
# 用 ASCII 的那条健康路径（代理同时认 /健康）：URL 里放中文会被 urllib 挡下。
HEALTH_URL = f"http://127.0.0.1:{PORT}/health"
PROBE_TIMEOUT = 5.0
WAIT_AFTER_START = 8

# ---- Qoder 窗口桥（8792）----
BRIDGE_TASK = "AI调用管家窗口桥"
BRIDGE_PORT = int(os.environ.get("QODER_BRIDGE_PORT", "8792"))
BRIDGE_HEALTH_URL = f"http://127.0.0.1:{BRIDGE_PORT}/health"
BRIDGE_WAIT = 20  # 桥要现起 Qoder 工作进程，给它比代理宽的时间


def _log(message: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(f"{stamp}　{message}\n")


def _console_encoding() -> str:
    """schtasks 的中文提示走控制台代码页（简体中文机器是 936），按它解才不会花。"""
    if os.name == "nt":
        try:
            import ctypes
            return f"cp{ctypes.windll.kernel32.GetOEMCP()}"
        except Exception:  # noqa: BLE001
            pass
    return "gbk"


def proxy_alive() -> tuple[bool, str]:
    """代理是不是真的能应答。光看端口在不算——挂死的进程也会占着端口。"""
    try:
        request = urllib.request.Request(HEALTH_URL, method="GET")
        with urllib.request.urlopen(request, timeout=PROBE_TIMEOUT) as response:
            body = response.read().decode("utf-8", "replace")
            if response.status == 200:
                return True, body[:80]
            return False, f"健康检查退 {response.status}"
    except urllib.error.HTTPError as exc:
        return False, f"健康检查退 {exc.code}"
    except Exception as exc:  # noqa: BLE001
        return False, f"探不到：{exc}"


def start_by_task() -> tuple[bool, str]:
    """请计划任务起代理。起不来不算失败——下面还有自己拉进程那一手。"""
    try:
        proc = subprocess.run(["schtasks", "/Run", "/TN", PROXY_TASK],
                              capture_output=True, timeout=30)
        raw = (proc.stdout + proc.stderr)
        text = ""
        for enc in (_console_encoding(), "utf-8"):
            try:
                text = raw.decode(enc)
                break
            except (UnicodeDecodeError, LookupError):
                continue
        if not text:
            text = raw.decode("utf-8", errors="replace")
        return proc.returncode == 0, text.strip()[:160]
    except Exception as exc:  # noqa: BLE001
        return False, f"调计划任务失败：{exc}"


def start_direct() -> tuple[bool, str]:
    """计划任务这条路走不通时，自己起一个代理进程顶上。"""
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    else:
        flags = 0
    try:
        proc = subprocess.Popen(
            [sys.executable, str(BASE_DIR / "ai_router" / "cli.py"), "serve"],
            cwd=str(BASE_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
        return True, f"自己起了进程 {proc.pid}"
    except Exception as exc:  # noqa: BLE001
        return False, f"自己起也失败：{exc}"


def bridge_alive() -> tuple[bool, str]:
    """窗口桥是不是真的能应答。返回 (活否, 说明)。"""
    try:
        request = urllib.request.Request(BRIDGE_HEALTH_URL, method="GET")
        with urllib.request.urlopen(request, timeout=PROBE_TIMEOUT) as response:
            body = response.read().decode("utf-8", "replace")
            if response.status == 200:
                ready = '"就绪": true' in body or '"就绪":true' in body
                return True, (body[:120] if ready else ("在跑但未就绪：" + body[:100]))
            return False, f"健康检查退 {response.status}"
    except urllib.error.HTTPError as exc:
        return False, f"健康检查退 {exc.code}"
    except Exception as exc:  # noqa: BLE001
        return False, f"探不到：{exc}"


def start_bridge_by_task() -> tuple[bool, str]:
    try:
        proc = subprocess.run(["schtasks", "/Run", "/TN", BRIDGE_TASK],
                              capture_output=True, timeout=30)
        raw = (proc.stdout + proc.stderr)
        text = ""
        for enc in (_console_encoding(), "utf-8"):
            try:
                text = raw.decode(enc)
                break
            except (UnicodeDecodeError, LookupError):
                continue
        if not text:
            text = raw.decode("utf-8", errors="replace")
        return proc.returncode == 0, text.strip()[:160]
    except Exception as exc:  # noqa: BLE001
        return False, f"调计划任务失败：{exc}"


def start_bridge_direct() -> tuple[bool, str]:
    """自己起窗口桥：python -m ai_router.qoder_bridge（cwd 必须是管家根）。"""
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    else:
        flags = 0
    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "ai_router.qoder_bridge"],
            cwd=str(BASE_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
        return True, f"自己起了进程 {proc.pid}"
    except Exception as exc:  # noqa: BLE001
        return False, f"自己起也失败：{exc}"


def tend_bridge() -> int:
    """桥这一路：活就记一行，不活就拉，拉完再验。返回 0 成／1 不成。"""
    alive, why = bridge_alive()
    if alive:
        _log(f"窗口桥在跑，不用管（{why}）")
        return 0

    _log(f"⚠窗口桥不在了（{why}）——群里 @ 机器人这会儿没有引擎接，去拉起来")
    ok, text = start_bridge_by_task()
    _log(f"请计划任务起桥：{'成' if ok else '不成'}　{text}")
    if not ok:
        ok, text = start_bridge_direct()
        _log(f"改为自己起桥：{'成' if ok else '不成'}　{text}")

    for _ in range(BRIDGE_WAIT):
        time.sleep(1)
        alive, why = bridge_alive()
        if alive:
            _log(f"桥拉起来了（{why}）")
            return 0

    _log("桥还是没起来，得人看一眼")
    return 1


def main() -> int:
    alive, why = proxy_alive()
    if alive:
        _log(f"代理在跑，不用管（{why}）")
        rc_bridge = tend_bridge()
        rc_listen = tend_listener()
        return 0 if (rc_bridge == 0 and rc_listen == 0) else 1

    _log(f"代理不在了（{why}），去拉起来")
    ok, text = start_by_task()
    _log(f"请计划任务起：{'成' if ok else '不成'}　{text}")

    for _ in range(WAIT_AFTER_START):
        time.sleep(1)
        alive, why = proxy_alive()
        if alive:
            _log(f"拉起来了（{why}）")
            return 0

    ok, text = start_direct()
    _log(f"改为自己起：{'成' if ok else '不成'}　{text}")
    for _ in range(WAIT_AFTER_START):
        time.sleep(1)
        alive, why = proxy_alive()
        if alive:
            _log(f"起来了（{why}）")
            return tend_bridge()

    _log("代理还是没起来，得人看一眼（桥与监听两路仍照查）")
    tend_bridge()
    tend_listener()
    return 1


# ---- 飞书事件监听（lark-cli event consume）----
# 2026-11-11 加：W5｜群面 的常驻监听只跑 24 小时上限，到期或崩溃后没有任何东西会发现。
# 这里只做"还在不在"，不在就拉起来一个；**不判断它属于哪个窗**，谁起的不重要，活着就行。
LISTENER_MARK = "event consume"
LISTENER_CMD = None


def _listener_pids() -> list[str]:
    """按命令行找 event consume 进程。查不到就返回空——宁可多起一个，不可漏报。"""
    try:
        ps = ("Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'lark-cli.exe' -and $_.CommandLine -like '*"
              + LISTENER_MARK + "*' } | Select-Object -ExpandProperty ProcessId")
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, timeout=40)
        out = r.stdout.decode("utf-8", "replace")
        return [x.strip() for x in out.splitlines() if x.strip().isdigit()]
    except Exception:  # noqa: BLE001
        return []


def _resolve_lark_cmd() -> str | None:
    env = os.environ.get("LARK_CLI")
    if env and os.path.exists(env):
        return env
    guess = os.path.join(os.path.expanduser("~"),
                         ".qoder-cn/plugins/cache/qoder-marketplace/lark/0.1.1/bin/lark-cli.cmd")
    return guess if os.path.exists(guess) else None


def start_listener() -> tuple[bool, str]:
    cmd = _resolve_lark_cmd()
    if not cmd:
        return False, "找不到 lark-cli.cmd（可设环境变量 LARK_CLI）"
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    else:
        flags = 0
    try:
        logf = open(DATA_DIR / "事件监听.log", "ab")
        logf.write(("\n===== 看门狗拉起 %s =====\n" % time.strftime("%Y-%m-%d %H:%M:%S")).encode("utf-8"))
        logf.flush()
        p = subprocess.Popen(
            [os.environ.get("COMSPEC", "cmd"), "/c", cmd, "event", "consume",
             "im.message.receive_v1", "--as", "bot", "--timeout", "86400s"],
            cwd=str(BASE_DIR), stdout=logf, stderr=logf, creationflags=flags,
        )
        return True, f"起了监听进程 {p.pid}（24h 上限）"
    except Exception as exc:  # noqa: BLE001
        return False, f"起监听失败：{exc}"


def tend_listener() -> int:
    pids = _listener_pids()
    if pids:
        _log(f"事件监听在跑（pid {','.join(pids[:3])}），不用管")
        return 0
    _log("⚠事件监听不在——群里这会儿没人接，去拉起一个")
    ok, text = start_listener()
    _log(f"起监听：{'成' if ok else '不成'}　{text}")
    for _ in range(12):
        time.sleep(1)
        if _listener_pids():
            _log("监听拉起来了")
            return 0
    _log("监听还是没起来，得人看一眼")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
