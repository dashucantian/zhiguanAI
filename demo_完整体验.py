# -*- coding: utf-8 -*-
"""完整体验 Demo 启动器（ZG-080·2026-10-01 W1 造·stdlib only）

为什么要有这个：法师 10-01 金口「先出一个完整版的demo最重要」。给第一次来
的人一条双击即得的路——不用知道端口、不用会命令行：
    双击 止观AI完整体验Demo.bat（本机快捷方式，不进库）
      → 本脚本确保服务在跑（没起就按文档口径拉起 8777/8778，不杀不改任何进程）
      → 自动打开浏览器进入 /demo 向导页（四站：看脑电／进空间／听闭环／看成果）

红线：本脚本只读＋拉起服务＋开浏览器；不写数据、不入库、不改场景代码。
"""
import os
import socket
import subprocess
import sys
import time
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = os.environ.get("LOCALAPPDATA", "") + r"\Programs\Python\Python312\python.exe"
HTTP_PORT, HTTPS_PORT = 8777, 8778
URL = f"http://127.0.0.1:{HTTP_PORT}/demo"


def service_up():
    """8777 是否已在听（只探测，不猜进程）。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        return s.connect_ex(("127.0.0.1", HTTP_PORT)) == 0


def main():
    print("=" * 60)
    print("止观AI · 完整体验 Demo")
    print("=" * 60)
    if service_up():
        print(f"[服务] {HTTP_PORT} 已在跑，直接复用（不杀不改）")
    else:
        if not os.path.exists(PY):
            print(f"[错误] 找不到项目固定解释器 {PY}")
            print("       （勿用裸 python：PATH 上的 3.14 缺依赖）")
            input("按回车键关闭……")
            sys.exit(1)
        log = open(os.path.join(ROOT, "output", "demo_start.log"),
                   "a", encoding="utf-8")
        subprocess.Popen([PY, os.path.join(ROOT, "console_server.py"),
                          "--port", str(HTTP_PORT),
                          "--https-port", str(HTTPS_PORT)],
                         cwd=ROOT, stdout=log, stderr=log)
        print(f"[服务] 正在启动（{HTTP_PORT}/{HTTPS_PORT}）……")
        for _ in range(30):
            time.sleep(1)
            if service_up():
                break
        if not service_up():
            print("[错误] 服务 30 秒内没起来——看 output/demo_start.log")
            input("按回车键关闭……")
            sys.exit(1)
        print(f"[服务] 已就绪（pid 口 {HTTP_PORT}）")
    print(f"[打开] 浏览器进入向导页：{URL}")
    webbrowser.open(URL)
    print("[完成] 页面已打开，照页面上的四个大按钮玩即可。")
    print("       本窗口可以关掉（服务不会跟着关）。")
    time.sleep(2)


if __name__ == "__main__":
    main()
