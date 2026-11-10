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
        return tend_bridge()

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

    _log("代理还是没起来，得人看一眼（桥这一路仍照查）")
    tend_bridge()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
