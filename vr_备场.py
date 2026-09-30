# -*- coding: utf-8 -*-
"""VR 线备场自检（只读·零外联·stdlib only）—— 2026-09-30 W1 造

为什么要有这个：S1 真机验收卡（09-17）让法师"双击 闭环神经反馈实验平台.bat"，
而该 .bat 在本盘上**根本不存在**（全库 find 无此名，09-30 实测）；卡上写的
HTTPS 端口 8778 也未必是当次实际端口（09-30 现役实例走的是 8788）。
戴上头显才发现地址不对，代价是整场验收作废——所以地址必须由脚本**当场算出来**，
不许照文档抄。

用法：
    python vr_备场.py            # 只体检：谁在听、六变体可达否、Pico 该填哪个地址
    python vr_备场.py --start    # 体检后若 8777 无主，按文档口径拉起服务并等就绪
判据与退出码：全部通过 exit 0；任一项不过 exit 1（可直接当验收闸用）。

红线：本脚本不写任何数据、不入库、不改场景代码、不杀任何进程。
"""
import ipaddress
import json
import os
import socket
import ssl
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = os.environ.get("LOCALAPPDATA", "") + r"\Programs\Python\Python312\python.exe"
HTTP_PORT, HTTPS_PORT = 8777, 8778          # 文档口径（判语008／踩坑001）
VARIANTS = ["s1", "v2abyss", "v3immersion", "v4lotuspond", "v5stupa", "v6void"]
fails, notes = [], []


def _sh(cmd):
    """跑本机命令（ipconfig / netstat），零外联。"""
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, encoding="gbk",
                             errors="ignore", timeout=15).stdout
    except Exception as e:                       # 编码/超时等一律如实报，不猜
        out = ""
        notes.append(f"命令 {' '.join(cmd)} 异常：{type(e).__name__}")
    return out or ""


def listening(port):
    """返回该端口的 LISTENING 持有者 PID（可能多个），无监听返回 []。"""
    pids = []
    for ln in _sh(["netstat", "-ano", "-p", "TCP"]).splitlines():
        if f":{port} " in ln and "LISTENING" in ln:
            pids.append(ln.split()[-1])
    return sorted(set(pids))


def lan_ip():
    """从 ipconfig 里挑出可路由的 IPv4（排除回环与链路本地），多台网卡时全列出。"""
    ips = []
    for ln in _sh(["ipconfig"]).splitlines():
        if "IPv4" in ln:
            cand = ln.split(":")[-1].strip()
            try:
                a = ipaddress.ip_address(cand)
            except ValueError:
                continue
            if not (a.is_loopback or a.is_link_local):
                ips.append(cand)
    return sorted(set(ips))


def get(url, timeout=8):
    """取一次，返回 (状态码, 字节数)；失败返回 (None, 中文原因)。"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False       # 自签证书，仅局域网自用（操作卡 §二 既有口径）
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(url, timeout=timeout, context=ctx) as r:
            body = r.read()
            return r.status, len(body)
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:70]}"


def main():
    start = "--start" in sys.argv
    print("=" * 66)
    print("VR 线备场自检 · 只读 · 零外联")
    print("=" * 66)

    # ── 1. 谁在听 ──────────────────────────────────────────────
    http_pids, https_pids = listening(HTTP_PORT), listening(HTTPS_PORT)
    print(f"[端口] {HTTP_PORT}(HTTP) {'在听 pid=' + ','.join(http_pids) if http_pids else '无主'}"
          f" ｜ {HTTPS_PORT}(HTTPS) {'在听 pid=' + ','.join(https_pids) if https_pids else '无主'}")
    # 现役实例可能把 HTTPS 挂在别的端口（09-30 实测见 8788）——照实找出来，不假装是 8778
    alt = [p for p in (8788, 8789) if listening(p)]
    if not https_pids and alt:
        print(f"[端口] ⚠ {HTTPS_PORT} 无监听，但发现备用 HTTPS 口：{alt}（以这些口为准）")

    # ── 2. 需要时拉起（只在不与别人抢端口的前提下） ───────────────
    if start and not http_pids:
        if not os.path.exists(PY):
            fails.append(f"找不到项目固定解释器 {PY}（勿用裸 python，3.14 缺依赖）")
        else:
            log = open(os.path.join(ROOT, "output", "vr_备场_start.log"), "a", encoding="utf-8")
            subprocess.Popen([PY, os.path.join(ROOT, "console_server.py"),
                              "--port", str(HTTP_PORT), "--https-port", str(HTTPS_PORT)],
                             cwd=ROOT, stdout=log, stderr=log)
            print(f"[启动] 已按文档口径拉起：{HTTP_PORT}/{HTTPS_PORT}，等待就绪…")
            for _ in range(30):
                time.sleep(1)
                if listening(HTTP_PORT):
                    break
            print(f"[启动] 结果：{HTTP_PORT} pid={listening(HTTP_PORT) or '仍无主'}")
    elif start and http_pids:
        print(f"[启动] 8777 已有主（pid={','.join(http_pids)}），本脚本**不杀不改**，直接复用")

    if not listening(HTTP_PORT):
        fails.append(f"{HTTP_PORT} 无监听：服务没起或没起来——先跑 python vr_备场.py --start")

    # ── 3. 六变体＋两场景逐一实取（真发请求，不靠推断） ─────────────
    base = f"http://127.0.0.1:{HTTP_PORT}"
    ok_cnt = 0
    for key in VARIANTS:
        code, info = get(f"{base}/mandala?variant={key}")
        flag = "OK " if code == 200 else "FAIL"
        print(f"[页面] {flag} /mandala?variant={key:<13} → {code}  {info if code != 200 else str(info) + ' B'}")
        ok_cnt += code == 200
        if code != 200:
            fails.append(f"/mandala?variant={key} 返回 {code} {info if code != 200 else ''}")
    for path in ("/vr", "/focus", "/"):
        code, info = get(base + path)
        print(f"[页面] {'OK ' if code == 200 else 'FAIL'} {path:<20} → {code}")
        if code != 200:
            fails.append(f"{path} 返回 {code}")

    # ── 4. HTTPS 侧（WebXR 入场券，踩坑001） ────────────────────
    https_ok = None
    for p in [HTTPS_PORT] + alt:
        code, _ = get(f"https://127.0.0.1:{p}/mandala?variant=s1")
        if code == 200:
            https_ok = p
            print(f"[HTTPS] {p} 可达（WebXR 需安全上下文，进 VR 必走此口）")
            break
    if https_ok is None:
        fails.append("HTTPS 侧不可达 ⇒ 头显里点『进入 VR』必无反应（判语008／踩坑001）")

    # ── 5. 头显该填什么（当场算，不抄文档） ──────────────────────
    ips = lan_ip()
    print("-" * 66)
    if ips and https_ok:
        for ip in ips:
            print(f"  Pico 浏览器填：  https://{ip}:{https_ok}/mandala?variant=s1")
            print(f"  桌面预览（非 VR）：http://{ip}:{HTTP_PORT}/mandala?variant=s1")
    else:
        print("  ⚠ 算不出可路由 IP 或 HTTPS 不可达，暂给不了头显地址（见上）")
    print("  同网段自检：头显与本机须在 192.168.x 同一网段；不通先查路由器隔离，别怀疑引擎")
    print("-" * 66)
    for n in notes:
        print(f"[备注] {n}")
    if fails:
        print(f"\n结果：**未就绪**，{len(fails)} 项待解：")
        for f in fails:
            print("  ✗ " + f)
        sys.exit(1)
    print(f"\n结果：**就绪**（六变体 {ok_cnt}/6 全通，HTTPS 口 {https_ok}，可戴头显）")


if __name__ == "__main__":
    main()
