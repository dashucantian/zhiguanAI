#!/usr/bin/env python3
"""
Muse Direct — 电脑蓝牙直连版脑电监测（Tk 调试窗口）

把 muse_local_server.py 的监测界面与蓝牙直连能力"嫁接"：
- 界面 / 解码缓冲 / 频段分析 / 报告生成：全部复用原界面（muse_local_server.py）
- 蓝牙连接 / 协议握手 / 数据包解码：复用唯一硬件层（ble_receiver.py）

定位（2026-09-01 架构统一）：本窗口是**调试工具**，不再是正式入口；
正式入口为项目根目录 Muse脑电监测.bat 启动的 Web 统一控制台。

用法:
    python muse_direct.py                # 自动扫描并连接第一个 Muse 头环
    python muse_direct.py --address MAC  # 直连指定设备
    python muse_direct.py --simulate     # 模拟模式（无需头环）
"""

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import tkinter as tk

from muse_local_server import MuseLocalServer, DataBuffer

# 安装中文界面（必须在创建界面前执行）
import zh_ui
zh_ui.install()

# 唯一硬件层（无 GUI 依赖，与 Web 控制台、实验脚本共用）
from ble_receiver import BleDirectReceiver  # noqa: E402


class MuseDirectApp(MuseLocalServer):
    """电脑蓝牙直连版界面：只替换"数据来源"，其余全部继承。"""

    def __init__(self, simulate=False, address=None, preset="p1041"):
        super().__init__(simulate=simulate, port=5000)
        self.ble_address = address
        self.preset = preset
        self.mode = "simulate" if simulate else "ble"

        self.title("Muse Direct — 电脑蓝牙直连脑电监测")
        if not simulate:
            self.ip_label.config(text="📶 蓝牙直连")
            self.btn_test.config(state=tk.DISABLED)
            self.bottom_label.config(
                text="就绪 — 点 Start 自动扫描并连接 Muse 头环（头环需已开机）")
        self._zh_polish()

    def _zh_polish(self):
        """翻译 matplotlib 图表标题，并优化波形显示范围。"""
        import matplotlib
        matplotlib.rcParams["font.sans-serif"] = [
            "Microsoft YaHei", "SimHei", "DejaVu Sans"]
        matplotlib.rcParams["axes.unicode_minus"] = False
        self.ax_eeg.set_title("脑电波形（5 秒窗口）", color="#ccc", fontsize=10)
        self.ax_eeg.set_ylim(-150, 150)
        self.ax_bp.set_title("频段能量（分贝）", color="#ccc", fontsize=10)
        self.ax_bp.set_xticklabels(
            ["δ 德尔塔", "θ 西塔", "α 阿尔法", "β 贝塔", "γ 伽马"],
            fontsize=9, color="#ccc")
        self.ax_ppg.set_title("脉搏波（5 秒）", color="#ccc", fontsize=9)
        self.ax_acc.set_title("头部运动（5 秒）", color="#ccc", fontsize=9)
        self.ax_acc.set_xlabel("时间（秒）", color="#888", fontsize=8)

    def _start(self):
        if self.simulate:
            super()._start()
            return

        self.running = True
        self.buffer = DataBuffer()
        self.receiver = BleDirectReceiver(
            self, address=self.ble_address, preset=self.preset)
        self.receiver.start()

        self.btn_start.config(text="⏹ Stop", bg="#b71c1c")
        self.btn_save.config(state=tk.NORMAL)
        self.status_var.set("连接中...")
        self.status_label.config(fg="#ffb74d")
        self._animate()

    def _self_test(self):
        from tkinter import messagebox
        messagebox.showinfo(
            "蓝牙直连模式", "直连模式无需自检：数据直接来自头环蓝牙。")

    def _animate(self):
        # 连接状态提示（蓝牙模式）
        if self.mode == "ble" and self.receiver:
            if self.receiver.is_connected():
                if self.status_var.get() in ("连接中...",):
                    self.status_var.set("Recording")
                    self.status_label.config(fg="#81c784")
                if self.receiver.battery_percent is not None:
                    self.raw_var.set(f"🔋 {self.receiver.battery_percent:.0f}%")
            elif self.receiver.last_error and not self.receiver.running:
                self.status_var.set("连接失败")
                self.status_label.config(fg="#ef5350")
        super()._animate()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Muse Direct — 电脑蓝牙直连")
    parser.add_argument("--address", type=str, default=None,
                        help="头环 MAC 地址（不填则自动扫描）")
    parser.add_argument("--preset", type=str, default="p1041",
                        help="传感器预设（默认 p1041：全通道）")
    parser.add_argument("--simulate", action="store_true",
                        help="模拟模式（无需头环）")
    args = parser.parse_args()

    app = MuseDirectApp(simulate=args.simulate,
                        address=args.address, preset=args.preset)
    app.mainloop()
