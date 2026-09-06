#!/usr/bin/env python3
"""
中文界面语言包 —— 把英文监测界面实时翻译成中文。

原理：在界面构建之前，给 tkinter 的 Label / Button / StringVar
套上一层"翻译外壳"，创建时和运行中更新的所有文字都会自动查表翻译。
"""

import re
import tkinter as tk
import tkinter.messagebox as _mb

# ── 静态 / 动态文字对照表 ─────────────────────────────────────────────
ZH = {
    # 标题与按钮
    "🧠 Muse Local Analyzer": "🧠 Muse 脑电监测仪",
    "▶ Start": "▶ 开始",
    "⏹ Stop": "⏹ 停止",
    "🔍 Self Test": "🔍 自检",
    "💾 Save & Report": "💾 保存并生成报告",
    # 状态
    "Stopped": "已停止",
    "Recording": "记录中",
    "⚠ Bad format": "⚠ 数据格式异常",
    "BLE: 0": "蓝牙包: 0",
    "UDP: 0": "通知包: 0",
    # 图表标题
    "EEG Waveform (5s window)": "脑电波形（5 秒窗口）",
    "Band Power (dB re 1 μV²)": "频段能量（分贝）",
    "PPG LO_NIR (5s)": "脉搏波（5 秒）",
    "Accelerometer (5s)": "头部运动（5 秒）",
    "Time (s)": "时间（秒）",
    # 右侧面板
    "Signal Channels": "脑电通道信号",
    "Latest Band Power": "最新频段能量",
    "Brain State": "大脑状态",
    "Band power: waiting for data": "频段能量：等待数据",
    "Band power: live": "频段能量：实时",
    "PPG / HRV": "心率 / 心率变异性",
    "Heart Rate": "心率",
    "-- BPM": "-- 次/分",
    "fNIRS / O₂ (prototype)": "血氧监测（实验性）",
    "Uncalibrated — research use only": "未经校准，仅供参考",
    "TSI (fNIRS)": "组织氧合 TSI",
    "SpO₂ est.": "血氧估算",
    "Optics ch": "光学通道数",
    "Head Motion": "头部运动",
    "Pitch": "俯仰角",
    "Roll": "侧倾角",
    "Acc jitter": "加速度抖动",
    "Gyro": "陀螺仪",
    "--- dB": "--- 分贝",
    # 底部提示
    "Ready — press Start to listen on port 5000":
        "就绪 — 点「开始」等待手机转发数据",
    "Stopped — press Save & Report to save data":
        "已停止 — 点「保存并生成报告」可保存本次数据",
    "Saved data, report generation failed": "数据已保存，但报告生成失败",
    "Simulation mode — generating synthetic 1/f EEG...":
        "模拟模式 — 正在生成合成脑电数据...",
    # 弹窗
    "No Data": "没有数据",
    "No EEG data recorded yet.": "还没有记录到脑电数据。",
    "Self Test": "自检",
    "Press Start first, then Self Test.": "先点「开始」，再点「自检」。",
    "Error": "错误",
    # 头部运动状态
    "Still": "静止",
    "Slight motion": "轻微动作",
    "Moving": "移动中",
}

# ── 带数字的动态文字（正则匹配） ─────────────────────────────────────
_REGEX = [
    (re.compile(r"^Band power: collecting (\d+)% \(\d+s window\)$"),
     lambda m: f"频段能量：采集中 {m.group(1)}%"),
    (re.compile(r"^(\d+) BPM$"),
     lambda m: f"{m.group(1)} 次/分"),
    (re.compile(r"^BLE: (\d+)$"),
     lambda m: f"蓝牙包: {m.group(1)}"),
    (re.compile(r"^UDP: (\d+)$"),
     lambda m: f"通知包: {m.group(1)}"),
    (re.compile(r"^Receiving from .*\| BLE:(\d+) UDP:(\d+)$"),
     lambda m: f"接收中：蓝牙包 {m.group(1)} / 通知包 {m.group(2)}"),
    (re.compile(r"^UDP from .*$"),
     lambda m: "收到未识别的数据来源"),
    (re.compile(r"^Saved: (.+)$"),
     lambda m: f"已保存：{m.group(1)}"),
    (re.compile(r"^Report: (.+)$"),
     lambda m: f"报告：{m.group(1)}"),
]


def t(value):
    """翻译一个文本值；查不到再试正则；再查不到原样返回。"""
    if not isinstance(value, str):
        return value
    if value in ZH:
        return ZH[value]
    for pat, repl in _REGEX:
        if pat.match(value):
            return repl(pat.match(value))
    return value


class _ZhLabel(tk.Label):
    def __init__(self, master=None, **kw):
        if "text" in kw:
            kw["text"] = t(kw["text"])
        super().__init__(master, **kw)

    def config(self, cnf=None, **kw):
        if "text" in kw:
            kw["text"] = t(kw["text"])
        return super().config(cnf, **kw)

    configure = config


class _ZhButton(tk.Button):
    def __init__(self, master=None, **kw):
        if "text" in kw:
            kw["text"] = t(kw["text"])
        super().__init__(master, **kw)

    def config(self, cnf=None, **kw):
        if "text" in kw:
            kw["text"] = t(kw["text"])
        return super().config(cnf, **kw)

    configure = config


class _ZhStringVar(tk.StringVar):
    def __init__(self, master=None, value=None, name=None):
        super().__init__(master, value=t(value) if value else value, name=name)

    def set(self, value):
        super().set(t(value))


# ── 安装翻译外壳（在创建界面前调用一次） ─────────────────────────────
def install():
    tk.Label = _ZhLabel
    tk.Button = _ZhButton
    tk.StringVar = _ZhStringVar

    for fn in ("showinfo", "showwarning", "showerror"):
        orig = getattr(_mb, fn)

        def make_wrapper(o):
            def wrapper(title="", message="", *args, **kwargs):
                return o(t(title), t(message), *args, **kwargs)
            return wrapper

        setattr(_mb, fn, make_wrapper(orig))
