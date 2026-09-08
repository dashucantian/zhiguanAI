#!/usr/bin/env python3
"""
止观AI 统一控制台后端服务（监测 + 实验双模式）

功能:
  A. 监测采集模式（2026-09-01 整合新增）：
     - 连接控制：扫描/直连头环（真机）或模拟数据源
     - 实时推流：SSE 推送波形、频段能量、心率等体征
     - 会话保存：保存 npz+报告，并生成 Zen-EEG 入库命令
  B. 闭环实验模式（原有）：
     - 配置管理：读取/校验/保存 experiment_config.json（含变体文件列表）
     - 实验控制：后台线程启动/停止闭环实验（模拟或真机）
     - 实时推流：SSE 把每个决策周期的特征与指令推给前端
     - 历史浏览：列出历次实验的日志、配置快照、脑电报告

架构约定（2026-09-01）：
  - 唯一硬件层 = ble_receiver.BleDirectReceiver（无 GUI 依赖）
  - 唯一入口 = 项目根目录 Muse脑电监测.bat（固定 Python 3.12）
  - Tk 监测窗口（muse_direct.py）仅保留为调试工具

用法:
    python console_server.py                 # 启动后打开浏览器访问提示的地址
    python console_server.py --port 8777

依赖: fastapi, uvicorn（已安装）
"""

import os
import re
import sys
import csv
import json
import time
import queue
import shutil
import asyncio
import argparse
import threading
import subprocess
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
REPO_DIR = os.path.join(SCRIPT_DIR, "muse2-repo", "muse2-master")
# 注：muse2-repo 为历史目录名（保留不改，2026-09-05 法师拍板）；
# 其代码实际服务于本项目在用设备 Muse S（第 3 代，蓝牙广播名 MuseS-xxxx）。
if REPO_DIR not in sys.path:
    sys.path.insert(0, REPO_DIR)

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional

from closedloop_experiment import run_closed_loop, EXP_DIR
from experiment_config_loader import (load_experiment_config, validate_config,
                                      save_snapshot, DEFAULT_CONFIG)

CONFIG_DEFAULT_PATH = os.path.join(SCRIPT_DIR, "experiment_config.json")
CONFIG_TEMPLATE_PATH = os.path.join(SCRIPT_DIR, "experiment_config_template.json")
REPORT_DIR = os.path.join(REPO_DIR, "report")
INGEST_TOOL = os.path.join(SCRIPT_DIR, "05_产品与开发", "muse-direct",
                           "tools", "ingest_session.py")

# ── 本机档案与数据工厂位置（2026-09-03） ──────────────────────────────────
PROFILES_PATH = os.path.join(SCRIPT_DIR, "console_profiles.json")
ZEN_ROOT = r"C:\Users\tiand\OneDrive\Zen-EEG"
REGISTRY_CSV = os.path.join(ZEN_ROOT, "01_registry", "session_registry.csv")
SESSION_TYPES = ["baseline", "training", "sleep", "custom", "test"]

# 质检闸门默认阈值（不合格 → 建议隔离，可人工推翻）
QC_MIN_DURATION_S = 30.0      # 时长下限
QC_MAX_PACKET_LOSS = 0.20     # 丢包率上限
QC_MIN_CLEAN_RATIO = 0.60     # 干净数据比例下限


def load_profiles():
    """读取本机测试者档案：{profiles:[...], default_participant:str}。"""
    if os.path.exists(PROFILES_PATH):
        try:
            with open(PROFILES_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {"profiles": data.get("profiles", []),
                    "default_participant": data.get("default_participant", "")}
        except Exception:
            pass
    return {"profiles": [], "default_participant": ""}


def save_profiles(data):
    with open(PROFILES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _read_registry_rows():
    """读登记表（不存在返回空行列表）。"""
    if not os.path.exists(REGISTRY_CSV):
        return []
    with open(REGISTRY_CSV, "r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _write_registry_rows(rows):
    fieldnames = ["session_id", "participant_id", "date", "session_type",
                  "duration_seconds", "status"]
    with open(REGISTRY_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def _next_session_number(rows, participant_id):
    """该受试者的下一个 S 序号（跨日期递增）。"""
    max_n = 0
    for row in rows:
        sid = row.get("session_id", "")
        if f"-{participant_id}-S" in sid:
            try:
                max_n = max(max_n, int(sid.split("-S")[-1]))
            except ValueError:
                pass
    return f"S{max_n + 1:02d}"


def _extract_report_metrics(report_path):
    """从 report.html 提取噪声段数/干净比例（与入库脚本同口径）。"""
    metrics = {}
    if not report_path or not os.path.exists(report_path):
        return metrics
    with open(report_path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()
    aliases = {"noise_epochs": ("Noise epochs", "噪声段数"),
               "clean_pct": ("Clean data", "干净数据比例")}
    for canon, labels in aliases.items():
        for label in labels:
            m = re.search(re.escape(label) +
                          r'</span><br>\s*<span class="value"[^>]*>([^<]+)</span>',
                          text)
            if m:
                metrics[canon] = m.group(1).strip()
                break
    return metrics


def qc_assess(npz_path, report_path):
    """质检闸门：返回 {recommend: 'ingest'|'quarantine', reasons:[...], metrics:{}}。"""
    reasons = []
    metrics = {}
    try:
        import numpy as np
        with np.load(npz_path, allow_pickle=True) as d:
            meta = d["meta"].item()
            samples = int(meta["samples"])
            duration = float(meta["duration"])
    except Exception as ex:
        return {"recommend": "quarantine",
                "reasons": [f"无法读取 npz：{ex}"], "metrics": metrics}

    eff = samples / duration if duration > 0 else 0.0
    loss = round(1.0 - eff / 256.0, 4)
    metrics.update({"samples": samples, "duration": round(duration, 1),
                    "effective_hz": round(eff, 2),
                    "packet_loss_rate": loss})
    if duration < QC_MIN_DURATION_S:
        reasons.append(f"时长 {duration:.0f}s 低于下限 {QC_MIN_DURATION_S:.0f}s")
    if loss > QC_MAX_PACKET_LOSS:
        reasons.append(f"丢包率 {loss:.0%} 超过上限 {QC_MAX_PACKET_LOSS:.0%}")

    rm = _extract_report_metrics(report_path)
    if "clean_pct" in rm:
        try:
            clean = float(rm["clean_pct"].rstrip("%")) / 100.0
            metrics["clean_ratio"] = clean
            if clean < QC_MIN_CLEAN_RATIO:
                reasons.append(f"干净数据 {clean:.0%} 低于下限 "
                               f"{QC_MIN_CLEAN_RATIO:.0%}")
        except ValueError:
            pass
    if "noise_epochs" in rm:
        metrics["noise_epochs"] = rm["noise_epochs"]
    return {"recommend": "quarantine" if reasons else "ingest",
            "reasons": reasons, "metrics": metrics}

app = FastAPI(title="止观AI 统一控制台")

# ── 共享数据源适配器（供控制台无界面运行硬件层/模拟源） ─────────────────


class HeadlessApp:
    """最小界面适配器：满足蓝牙接收器回调接口，不创建任何窗口。

    device="neuradock" 时按 NeuraDock 7 通道/250Hz 布局构造缓冲；
    其余（含缺省）保持 Muse 4 通道/256Hz 旧行为不变。"""

    def __init__(self, device="muse"):
        from muse_local_server import DataBuffer
        if device == "neuradock":
            from neuradock_receiver import ND_CHANNELS, ND_SFREQ
            self.buffer = DataBuffer(channels=ND_CHANNELS, sfreq=ND_SFREQ,
                                     device="neuradock")
        else:
            self.buffer = DataBuffer()

    def after(self, _ms, func):
        try:
            func()
        except Exception:
            pass

    class _Lbl:
        def config(self, text="", **kw):
            pass

    @property
    def bottom_label(self):
        return self._Lbl()


class ReplaySource:
    """离线回放数据源（B3／ZG-010）：把已入库 npz 按线上节奏回灌 buffer。

    为什么需要它：B1/B2 的映射参数调校若每次都靠佩戴真机，则每轮都要戴头环、
    调接触、等连接（实测 20~37 秒），且脑状态不可复现。本源使映射迭代
    不依赖头环在场，且每轮输入完全相同、结果可比。

    与 MonitorSimulator 同接口形态（running/last_error/packet_count/
    battery_percent/start/stop/is_connected），且走**同一个**
    app.buffer.add_eeg() 入口，故下游 compute_band_power → tick →
    VRSession → /ws/vr → vr_feedback.html 全链路与真机完全一致。

    数据边界：只读 npz；回放会话不得入库（调用方须传 save=False）。
    """

    BATCH_SAMPLES = 12          # 与 MonitorSimulator 一致：每批 12 样本 ×5 列

    def __init__(self, app, npz_path, speed=1.0):
        self.app = app
        self.npz_path = npz_path
        self.speed = max(0.1, float(speed))   # >1 加速回放，便于快速看映射效果
        self.running = False
        self.last_error = None
        self.packet_count = 0
        self.battery_percent = None
        self._thread = None
        self._eeg = None
        self.n_total = 0

    def load(self):
        """载入 npz；失败时把原因写入 last_error，由调用方走 error+end 事件。"""
        import numpy as np
        # 用 os.path 而非 pathlib.Path：本文件通篇用 os.path，未导入 Path
        if not os.path.exists(self.npz_path):
            self.last_error = f"回放文件不存在: {self.npz_path}"
            return False
        try:
            d = np.load(self.npz_path, allow_pickle=True)
            eeg = np.asarray(d["eeg"], dtype=np.float64)
        except Exception as ex:                        # noqa: BLE001
            self.last_error = f"回放文件读取失败: {type(ex).__name__}: {ex}"
            return False
        if eeg.ndim != 2 or eeg.shape[1] < 4:
            self.last_error = f"回放数据形状异常: {eeg.shape}（期望 (samples, 4)）"
            return False
        self._eeg = eeg[:, :4]
        self.n_total = int(self._eeg.shape[0])
        return True

    def start(self):
        if self._eeg is None and not self.load():
            return False
        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join(timeout=3)

    def is_connected(self):
        return self.running

    def _run(self):
        import numpy as np
        from muse_local_server import CHANNELS, SFREQ
        n_ch = len(CHANNELS)
        dt = self.BATCH_SAMPLES / SFREQ / self.speed
        i = 0
        n = self.n_total
        while self.running and i < n:
            end = min(i + self.BATCH_SAMPLES, n)
            chunk = self._eeg[i:end, :]
            batch = []
            for row in chunk:
                for c in range(n_ch):
                    batch.append(float(row[c]) if c < row.shape[0] else 0.0)
                batch.append(0.0)          # 第 5 列占位，与既有 add_eeg 约定一致
            self.app.buffer.add_eeg(batch)
            self.packet_count += 1
            i = end
            time.sleep(dt)
        # 回放放完即视为正常结束（不报 last_error，避免触发保存/告警路径）
        self.running = False


class MonitorSimulator:
    """监测模式模拟数据源：Alpha 占优的合成脑电，供无头环时演练全流程。"""

    def __init__(self, app):
        self.app = app
        self.running = False
        self.last_error = None
        self.packet_count = 0   # 与 BleDirectReceiver 接口对齐
        self.battery_percent = None
        self._thread = None

    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join(timeout=3)

    def is_connected(self):
        return self.running

    def _run(self):
        import numpy as np
        from muse_local_server import SFREQ
        rng = np.random.default_rng(11)
        t = 0.0
        dt = 1.0 / SFREQ
        while self.running:
            batch = []
            for _ in range(12):
                alpha_amp = 7.0 + 3.0 * np.sin(2 * np.pi * t / 90.0)
                vals = []
                for ch in range(4):
                    v = alpha_amp * np.sin(2 * np.pi * 10.0 * t + ch) \
                        + 1.2 * np.sin(2 * np.pi * 20.0 * t + ch * 0.7) \
                        + rng.normal(0, 1.5)
                    vals.append(v)
                batch.extend(vals)
                batch.append(0.0)
                t += dt
            self.app.buffer.add_eeg(batch)
            time.sleep(12.0 / SFREQ)


def make_ingest_command(npz_path, report_path=None, scene="monitor",
                        participant="<P001>", session_type="<baseline|training|test|custom>",
                        quarantine=False, note="", pre_state="",
                        post_state="", contact_quality=""):
    """生成 Zen-EEG 数据工厂入库命令（需操作员确认后手动执行）。"""
    cmd = [f'python "{INGEST_TOOL}"',
           f'--npz "{npz_path}"']
    if report_path:
        cmd.append(f'--report "{report_path}"')
    cmd.append(f"--participant {participant}")
    cmd.append(f"--type {session_type}")
    cmd.append("--operator tiand")
    cmd.append(f"--scene {scene}")
    if quarantine:
        cmd.append("--quarantine")
    if note:
        cmd.append(f'--note "{note}"')
    if pre_state:
        cmd.append(f'--pre-state "{pre_state}"')
    if post_state:
        cmd.append(f'--post-state "{post_state}"')
    if contact_quality:
        cmd.append(f'--contact-quality "{contact_quality}"')
    cmd.append('# 预登记模式追加 --sid <ZEN-YYYYMMDD-P001-Sxx>')
    return " ".join(cmd)


# ── 监测采集会话（单例，同一时间只允许一个监测或实验） ─────────────────


class MonitorSession:
    """监测采集会话：连接头环/模拟源 → 实时推流 → 保存会话数据。"""

    TICK_SEC = 0.25          # SSE 推流间隔
    VITALS_EVERY = 12        # 每 N 个 tick 计算一次心率/运动等体征

    def __init__(self):
        self.thread = None
        self.stop_event = threading.Event()
        self.events = queue.Queue()
        self.status = "idle"   # idle / connecting / recording / saving
        self.mode = None
        self.started_at = None
        self.app = None
        self.receiver = None
        self.saved = None      # {"npz": ..., "report": ..., "ingest_cmd": ...}
        self.session_info = {}  # 测试者信息/反馈（保存时写入 meta）
        self._save_req = threading.Event()

    def is_running(self):
        return self.thread is not None and self.thread.is_alive()

    def snapshot(self):
        return {
            "status": self.status,
            "running": self.is_running(),
            "started_at": (self.started_at.strftime("%Y-%m-%d %H:%M:%S")
                           if self.started_at else None),
            "mode": self.mode,
            "saved": self.saved,
        }

    def start(self, simulate=True, address=None, session_info=None,
              adapter="bleak", serial_port=None, replay_npz=None):
        if self.is_running():
            raise RuntimeError("已有监测会话正在运行")
        self.stop_event.clear()
        self._save_req.clear()
        self.events = queue.Queue()
        self.saved = None
        self.status = "connecting"
        self.started_at = datetime.now()
        # 回放优先于模拟：给定 npz 即走 ReplaySource（B3／ZG-010）
        if replay_npz:
            self.mode = f"离线回放（{os.path.basename(replay_npz)}）"
        elif simulate:
            self.mode = "模拟"
        elif adapter == "bled112":
            self.mode = f"真机（BLED112 {serial_port or '自动'}）"
        elif adapter == "neuradock":
            self.mode = f"NeuraDock TCP（{serial_port or '127.0.0.1:9600'}）"
        else:
            self.mode = "真机蓝牙"
        self.session_info = dict(session_info or {})
        self.thread = threading.Thread(
            target=self._worker,
            args=(simulate, address, adapter, serial_port, replay_npz),
            daemon=True)
        self.thread.start()

    def request_stop(self, save=True):
        """请求停止；save=True 时先保存数据再结束。"""
        if not self.is_running():
            return False
        if save:
            self._save_req.set()
        self.stop_event.set()
        return True

    def request_save(self):
        """请求不断连保存（保存后可继续采集）。"""
        if not self.is_running():
            return False
        self._save_req.set()
        return True

    def _emit(self, ev):
        self.events.put(ev)

    def _do_save(self, tag=""):
        # 数据边界硬约束：B3 离线回放的数据来自已入库 npz，回放会话
        # 一律不得再落盘、不得生成入库命令，否则同一份数据会重复入库。
        if self.session_info.get("session_type") == "replay":
            self.saved = {
                "npz": None, "report": None, "ingest_cmd": None,
                "again": False, "blocked": True,
                "reason": "离线回放会话禁止保存与入库（数据源已是入库 npz）",
            }
            self._emit({"type": "message",
                        "text": "📼 回放会话已跳过保存（禁止入库，数据源本身已是入库 npz）"})
            return self.saved
        buf = self.app.buffer
        if buf._saved_data_path is not None:
            # 幂等：本会话已保存过
            self.saved = {
                "npz": buf._saved_data_path,
                "report": buf._saved_report_path,
                "ingest_cmd": self._build_ingest_cmd(
                    buf._saved_data_path, buf._saved_report_path),
                "again": True,
            }
            return self.saved
        info = dict(self.session_info)
        info["scene"] = "monitor"
        result = buf.save_bin(extra_meta=info)
        if result:
            data_path, report_path = result
            qc = qc_assess(data_path, report_path)
            self.saved = {
                "npz": data_path,
                "report": report_path,
                "ingest_cmd": self._build_ingest_cmd(
                    data_path, report_path, qc),
                "again": False,
                "qc": qc,
            }
            self._emit({"type": "saved", **self.saved})
        return self.saved

    def _build_ingest_cmd(self, data_path, report_path, qc=None):
        """生成入库命令：带上场景、测试者信息与质检建议的隔离参数。"""
        info = self.session_info
        if qc is None:
            qc = qc_assess(data_path, report_path)
        recommend_q = qc["recommend"] == "quarantine"
        return make_ingest_command(
            data_path, report_path, scene="monitor",
            participant=info.get("participant") or "<P001>",
            session_type=info.get("session_type")
            or "<baseline|training|test|custom>",
            quarantine=recommend_q,
            note=info.get("note", ""),
            pre_state=info.get("pre_state", ""),
            post_state=info.get("post_state", ""),
            contact_quality=info.get("contact_quality", ""))

    def _worker(self, simulate, address, adapter="bleak", serial_port=None,
                replay_npz=None):
        try:
            self.app = HeadlessApp(
                device="neuradock" if adapter == "neuradock" else "muse")
            if replay_npz:
                # B3／ZG-010：离线回放源。走与真机同一个 buffer.add_eeg 入口，
                # 故下游 compute_band_power → tick → VRSession → /ws/vr 全链路一致。
                self.receiver = ReplaySource(self.app, replay_npz)
                if not self.receiver.load():
                    err = self.receiver.last_error
                    self._emit({"type": "error", "text": err})
                    self._emit({"type": "end", "ok": False, "error": err})
                    self.status = "idle"
                    return
                self.receiver.start()
                self.status = "recording"
                self._emit({"type": "message",
                            "text": f"📼 离线回放已启动（{self.receiver.n_total} 样本，"
                                    f"约 {self.receiver.n_total / 256.0:.0f} 秒）"})
            elif simulate:
                self.receiver = MonitorSimulator(self.app)
                self.receiver.start()
                self.status = "recording"
                self._emit({"type": "message", "text": "模拟数据源已启动"})
            else:
                if adapter == "bled112":
                    from ble_receiver import BleBgapiReceiver, detect_bled112_port
                    port = serial_port or detect_bled112_port()
                    if not port:
                        connect_error = ("未检测到 BLED112 适配器（请确认已插入 USB，"
                                         "或在设备管理器查看其串口号）")
                        self._emit({"type": "error", "text": connect_error})
                        self._emit({"type": "end", "ok": False,
                                    "error": connect_error})
                        self.status = "idle"
                        return
                    self._emit({"type": "message",
                                "text": f"🔌 检测到 BLED112 适配器：{port}"})
                    self.receiver = BleBgapiReceiver(
                        self.app, address=address, serial_port=port)
                elif adapter == "neuradock":
                    from neuradock_receiver import TcpReceiver
                    host, _, nd_port = (serial_port or
                                        "127.0.0.1:9600").partition(":")
                    self.receiver = TcpReceiver(
                        self.app, host=host or "127.0.0.1",
                        port=int(nd_port or 9600))
                else:
                    from ble_receiver import BleDirectReceiver
                    self.receiver = BleDirectReceiver(self.app, address=address)

                def _relay(text):
                    if "not found" in text:
                        text += "（未发现头环广播：请确认已开机、指示灯亮，且未连其他设备）"
                    self._emit({"type": "message", "text": text})
                self.receiver.on_status = _relay
                self.receiver.start()
                connect_error = None
                for _ in range(60):
                    if self.receiver.is_connected():
                        break
                    if self.receiver.last_error and not self.receiver.running:
                        connect_error = f"连接失败: {self.receiver.last_error}"
                        break
                    if self.stop_event.is_set():
                        connect_error = "已取消连接"
                        break
                    time.sleep(0.5)
                if connect_error is None and not self.receiver.is_connected():
                    connect_error = "连接超时：30 秒内未连上头环"
                if connect_error:
                    self.receiver.stop()
                    self._emit({"type": "error", "text": connect_error})
                    self._emit({"type": "end", "ok": False,
                                "error": connect_error})
                    self.status = "idle"
                    return
                self.status = "recording"
                self._emit({"type": "message",
                            "text": "✅ 已连接，数据流传输中"})

            # ── 实时推流主循环 ──
            n_ticks = 0
            while not self.stop_event.is_set():
                buf = self.app.buffer
                buf.compute_band_power()
                if n_ticks % self.VITALS_EVERY == 0:
                    try:
                        buf.compute_vitals()
                    except Exception:
                        pass
                bp, state = buf.get_latest_bp()
                vitals = buf.get_vitals()
                # 最近 5 秒波形（每通道 1280 点；通道布局随设备，V1.4）
                wave = {}
                with buf.lock:
                    for ch in buf.channels:
                        seg = list(buf.eeg[ch])[-1280:]
                        wave[ch] = [round(v, 2) for v in seg]
                battery = (self.receiver.battery_percent
                           if hasattr(self.receiver, "battery_percent")
                           else None)
                # 脉搏波与三轴运动 5 秒窗口（降采样到约 100/60 点，控制载荷）
                with buf.lock:
                    ppg = list(buf.ppg_ir)
                    accx, accy, accz = (list(buf.acc_x), list(buf.acc_y),
                                        list(buf.acc_z))
                def _ds(seq, n):
                    if not seq:
                        return []
                    step = max(1, len(seq) // n)
                    return [round(v, 2) for v in seq[::step]][:n]
                payload = {
                    "type": "tick",
                    "elapsed": round(buf.duration_seconds(), 1),
                    "connected": self.receiver.is_connected(),
                    "packets": self.receiver.packet_count,
                    "battery": battery,
                    "bands": bp, "state": state,
                    "vitals": {k: vitals.get(k) for k in
                               ("hr", "rmssd", "sdnn", "pnn50", "motion",
                                "spo2", "tsi", "d_hbo2", "d_hbr",
                                "optics_ch")},
                    "ppg": _ds(ppg, 120),
                    "motion_xyz": {"x": _ds(accx, 80), "y": _ds(accy, 80),
                                   "z": _ds(accz, 80)},
                    "wave": wave,
                }
                self._emit(payload)
                VR.push_from_monitor(payload)
                n_ticks += 1
                # 保存请求优先处理（不断连保存）
                if self._save_req.is_set():
                    self._save_req.clear()
                    self.status = "saving"
                    self._do_save()
                    self.status = "recording"
                # 真机静默断连后，看门狗会停止接收器；此处收尾
                if not simulate and not self.receiver.running \
                        and self.receiver.last_error:
                    self._emit({"type": "error",
                                "text": f"数据流中断：{self.receiver.last_error}"})
                    break
                time.sleep(self.TICK_SEC)
        except Exception as ex:
            import traceback
            print(f"[monitor] worker exception: {ex}")
            traceback.print_exc()
            self._emit({"type": "error", "text": f"监测异常: {ex}"})
        finally:
            # ── 收尾：停止数据源 + 按需保存 ──
            try:
                if self.receiver is not None:
                    self.receiver.stop()
            except Exception:
                pass
            if self._save_req.is_set() or self.status == "recording":
                # 停止即保存（与 V1.2 断连自动保存幂等共存）
                self.status = "saving"
                try:
                    self._do_save()
                except Exception as ex:
                    self._emit({"type": "error", "text": f"保存失败: {ex}"})
            self.status = "idle"
            self._emit({"type": "end", "ok": True,
                        "saved": self.saved})


MONITOR = MonitorSession()

# ── 实验会话（单例，同一时间只允许一个实验） ──────────────────────────────


class ExperimentSession:
    def __init__(self):
        self.lock = threading.Lock()
        self.thread = None
        self.stop_event = threading.Event()
        self.events = queue.Queue()
        self.status = "idle"          # idle / running / saving
        self.started_at = None
        self.mode = None
        self.tag = None
        self.last_result = None

    def is_running(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self, cfg, simulate, address, session_info=None,
              adapter="bleak", serial_port=None):
        if self.is_running():
            raise RuntimeError("已有实验正在运行")
        self.stop_event.clear()
        self.events = queue.Queue()
        self.status = "running"
        self.started_at = datetime.now()
        if simulate:
            self.mode = "模拟"
        elif adapter == "bled112":
            self.mode = f"真机（BLED112 {serial_port or '自动'}）"
        elif adapter == "neuradock":
            self.mode = f"NeuraDock TCP（{serial_port or '127.0.0.1:9600'}）"
        else:
            self.mode = "真机蓝牙"
        self.tag = cfg["experiment"]["tag"]
        self.session_info = dict(session_info or {})

        def worker():
            try:
                def _exp_relay(ev):
                    self.events.put(ev)
                    VR.push_from_experiment(ev)
                result = run_closed_loop(
                    cfg, simulate=simulate, address=address,
                    adapter=adapter, serial_port=serial_port,
                    callback=_exp_relay,
                    stop_event=self.stop_event,
                    session_info=self.session_info)
            except Exception as ex:
                result = {"ok": False, "error": f"实验异常: {ex}"}
                self.events.put({"type": "error", "text": str(ex)})
            self.last_result = result
            self.status = "idle"

        self.thread = threading.Thread(target=worker, daemon=True)
        self.thread.start()

    def stop(self):
        if not self.is_running():
            return False
        self.stop_event.set()
        return True

    def snapshot(self):
        return {
            "status": self.status,
            "running": self.is_running(),
            "started_at": (self.started_at.strftime("%Y-%m-%d %H:%M:%S")
                           if self.started_at else None),
            "mode": self.mode,
            "tag": self.tag,
            "last_result": self.last_result,
        }


SESSION = ExperimentSession()


# ── VR 桥接（2026-09-05 A4：脑电指标 → Pico 头显 WebSocket 出口） ──────────
# 设计约定：VR 端只消费「低频指标」（频段能量/状态/体征），不消费原始波形；
# 原始波形体积大且 VR 渲染用不上，视觉反馈由头显端 Shader 用指标参数实时驱动。
VR_MODEL_DIR = os.path.join(SCRIPT_DIR, "05_产品与开发", "VR素材", "3D模型")
VR_ASSET_DIR = os.path.join(SCRIPT_DIR, "vr_assets")   # 本地化 three.js（MIT）


class VRSession:
    """向所有已连接的 VR 客户端广播脑电指标（线程安全，跨事件循环推送）。

    2026-09-06：HTTP(8777) 与 HTTPS(8778) 双服务并存后，两个 uvicorn
    各有独立事件循环；客户端与其所属循环绑定登记，广播时按循环分发。
    """

    def __init__(self):
        self.clients = set()   # {(ws, loop)}
        self._lock = threading.Lock()

    def attach(self, ws, loop):
        with self._lock:
            self.clients.add((ws, loop))

    def detach(self, ws):
        with self._lock:
            self.clients = {(w, l) for (w, l) in self.clients if w is not ws}

    @property
    def count(self):
        return len(self.clients)

    def _send(self, payload):
        text = json.dumps(payload, ensure_ascii=False, default=str)
        with self._lock:
            targets = list(self.clients)
        for ws, loop in targets:
            try:
                asyncio.run_coroutine_threadsafe(ws.send_text(text), loop)
            except Exception:
                pass

    def push_from_monitor(self, ev):
        """监测模式 tick → VR 指标包。"""
        if ev.get("type") != "tick":
            return
        self._send({"type": "tick", "source": "monitor", "t": time.time(),
                    "elapsed": ev.get("elapsed"),
                    "connected": ev.get("connected"),
                    "battery": ev.get("battery"),
                    "bands": ev.get("bands"), "state": ev.get("state"),
                    "vitals": ev.get("vitals")})

    def push_from_experiment(self, ev):
        """闭环实验事件 → VR 指标包（剥离原始波形）。"""
        et = ev.get("type")
        if et == "tick":
            self._send({"type": "tick", "source": "experiment", "t": time.time(),
                        "elapsed": ev.get("elapsed"), "phase": ev.get("phase"),
                        "alpha": ev.get("alpha"), "theta": ev.get("theta"),
                        "beta": ev.get("beta"), "bands": ev.get("bands"),
                        "state": ev.get("state"), "beat": ev.get("beat"),
                        "vol": ev.get("vol")})
        elif et in ("start", "end", "baseline_locked", "error", "message"):
            self._send({"source": "experiment", "t": time.time(),
                        **{k: v for k, v in ev.items() if k != "wave"}})


VR = VRSession()


def _assert_no_other_session(active):
    """监测与实验互斥：同一时间只能有一个数据源占用头环。"""
    other = SESSION if active is MONITOR else MONITOR
    if other.is_running():
        raise HTTPException(
            status_code=409,
            detail="另一个会话（监测/实验）正在运行，请先停止它")


# ── 配置管理接口 ────────────────────────────────────────────────────────────


class ConfigPayload(BaseModel):
    path: Optional[str] = None
    content: Optional[dict] = None


def _resolve_config_path(path=None):
    """限定配置文件只能位于项目根目录且为 .json。"""
    base = path or CONFIG_DEFAULT_PATH
    if not os.path.isabs(base):
        base = os.path.join(SCRIPT_DIR, base)
    real = os.path.realpath(base)
    if os.path.dirname(real) != os.path.realpath(SCRIPT_DIR):
        raise HTTPException(status_code=400, detail="配置文件必须位于项目根目录")
    if not real.endswith(".json"):
        raise HTTPException(status_code=400, detail="仅支持 .json 配置文件")
    return real


@app.get("/api/config")
def get_config(path: Optional[str] = None):
    """读取配置文件内容；不存在时返回内置默认值。"""
    real = _resolve_config_path(path)
    if os.path.exists(real):
        with open(real, "r", encoding="utf-8") as f:
            content = json.load(f)
    else:
        content = json.loads(json.dumps(DEFAULT_CONFIG))
    # 同时返回与默认值合并后的生效配置，供前端预览
    try:
        merged = load_experiment_config(real)
        merged_ok, merged_err = True, None
    except ValueError as ex:
        merged, merged_ok, merged_err = None, False, str(ex)
    return {"path": os.path.basename(real), "content": content,
            "merged": merged, "merged_ok": merged_ok,
            "merged_error": merged_err}


@app.post("/api/config/validate")
def validate_config_api(payload: ConfigPayload):
    """校验配置内容，返回是否通过及错误详情。"""
    if payload.content is None:
        raise HTTPException(status_code=400, detail="缺少 content")
    tmp = os.path.join(SCRIPT_DIR, "_tmp_validate.json")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload.content, f, ensure_ascii=False)
        merged = load_experiment_config(tmp)
        return {"ok": True, "merged": merged}
    except ValueError as ex:
        return {"ok": False, "errors": str(ex)}
    except Exception as ex:
        return {"ok": False, "errors": f"JSON 解析失败: {ex}"}
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


@app.post("/api/config/save")
def save_config(payload: ConfigPayload):
    """保存配置；保存前自动备份旧文件，保存后校验生效结果。"""
    real = _resolve_config_path(payload.path)
    if payload.content is None:
        raise HTTPException(status_code=400, detail="缺少 content")
    try:
        json.dumps(payload.content)
    except Exception as ex:
        raise HTTPException(status_code=400, detail=f"内容不是合法 JSON: {ex}")
    backup = None
    if os.path.exists(real):
        backup = real + ".bak"
        with open(real, "r", encoding="utf-8") as f:
            old = f.read()
        with open(backup, "w", encoding="utf-8") as f:
            f.write(old)
    with open(real, "w", encoding="utf-8") as f:
        json.dump(payload.content, f, ensure_ascii=False, indent=2)
    try:
        load_experiment_config(real)
        valid, err = True, None
    except ValueError as ex:
        valid, err = False, str(ex)
    return {"ok": True, "path": os.path.basename(real),
            "backup": os.path.basename(backup) if backup else None,
            "valid": valid, "validation_error": err}


@app.get("/api/config/files")
def list_config_files():
    """列出项目根目录下可用的配置文件。"""
    files = []
    for name in sorted(os.listdir(SCRIPT_DIR)):
        if name.endswith(".json") and ("config" in name or "variant" in name):
            full = os.path.join(SCRIPT_DIR, name)
            files.append({"name": name,
                          "size": os.path.getsize(full),
                          "mtime": datetime.fromtimestamp(
                              os.path.getmtime(full)).strftime("%Y-%m-%d %H:%M")})
    return {"files": files, "default": os.path.basename(CONFIG_DEFAULT_PATH),
            "template": (os.path.basename(CONFIG_TEMPLATE_PATH)
                         if os.path.exists(CONFIG_TEMPLATE_PATH) else None)}


@app.get("/api/config/template")
def get_template():
    """读取带注释的配置模板。"""
    if not os.path.exists(CONFIG_TEMPLATE_PATH):
        raise HTTPException(status_code=404, detail="模板文件不存在")
    with open(CONFIG_TEMPLATE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ── 监测采集接口 ────────────────────────────────────────────────────────────


class MonitorStartPayload(BaseModel):
    simulate: bool = True
    address: Optional[str] = None
    adapter: Optional[str] = "bleak"  # bleak=内置蓝牙 | bled112=外置适配器 | neuradock=TCP 数据服务
    serial_port: Optional[str] = None  # bled112 串口号；neuradock 时为 "host:port"（默认 127.0.0.1:9600）
    replay_npz: Optional[str] = None   # B3／ZG-010：离线回放的 npz 文件名
    participant: Optional[str] = None
    session_type: Optional[str] = None
    pre_state: Optional[str] = None
    contact_quality: Optional[str] = None
    note: Optional[str] = None


def _resolve_replay_path(name: str) -> str:
    """把回放文件名解析为 report 目录内的绝对路径。

    复用既有的 REPORT_DIR（= muse2-repo/muse2-master/report，即 save_bin 的
    真实落盘目录）与 _safe_join（越界防护），不另造一套路径逻辑。
    只允许 .npz。
    """
    if not name.lower().endswith(".npz"):
        raise HTTPException(status_code=400, detail="回放文件必须为 .npz")
    real = _safe_join(REPORT_DIR, os.path.basename(name))
    if not os.path.exists(real):
        raise HTTPException(status_code=404,
                            detail=f"回放文件不存在: {os.path.basename(name)}")
    return real


@app.post("/api/monitor/start")
def monitor_start(payload: MonitorStartPayload):
    _assert_no_other_session(MONITOR)
    replay_path = None
    if payload.replay_npz:
        replay_path = _resolve_replay_path(payload.replay_npz)
    session_info = {"participant": payload.participant or "",
                    "session_type": payload.session_type or "",
                    "pre_state": payload.pre_state or "",
                    "contact_quality": payload.contact_quality or "",
                    "note": payload.note or ""}
    if replay_path:
        # 数据边界：回放会话一律标记为回放，禁止入库 Zen-EEG。
        session_info["session_type"] = "replay"
        session_info["note"] = ((session_info["note"] + " | ") if session_info["note"] else "") \
            + "B3离线回放，禁止入库"
    MONITOR.start(simulate=payload.simulate, address=payload.address,
                  session_info=session_info,
                  adapter=payload.adapter or "bleak",
                  serial_port=payload.serial_port,
                  replay_npz=replay_path)
    mode = (f"离线回放（{os.path.basename(replay_path)}）" if replay_path
            else "模拟" if payload.simulate
            else f"真机（BLED112）" if payload.adapter == "bled112"
            else "NeuraDock TCP" if payload.adapter == "neuradock"
            else "真机蓝牙")
    return {"ok": True, "mode": mode}


class MonitorStopPayload(BaseModel):
    save: bool = True
    post_state: Optional[str] = None


@app.post("/api/monitor/stop")
def monitor_stop(payload: MonitorStopPayload):
    if payload.post_state:
        MONITOR.session_info["post_state"] = payload.post_state
    if not MONITOR.request_stop(save=payload.save):
        raise HTTPException(status_code=409, detail="当前没有正在运行的监测会话")
    return {"ok": True, "message": "已发送停止指令" +
            ("（将先保存数据）" if payload.save else "")}


@app.post("/api/monitor/save")
def monitor_save():
    if not MONITOR.request_save():
        raise HTTPException(status_code=409, detail="当前没有正在运行的监测会话")
    return {"ok": True, "message": "已请求保存（保存不中断采集）"}


@app.get("/api/monitor/status")
def monitor_status():
    return MONITOR.snapshot()


@app.get("/api/monitor/stream")
async def monitor_stream():
    """SSE 实时推流：把监测线程产生的事件持续推给前端。"""

    async def gen():
        loop = asyncio.get_running_loop()
        last_ping = time.time()
        while True:
            try:
                ev = await loop.run_in_executor(
                    None, lambda: MONITOR.events.get(timeout=1.0))
                yield f"data: {json.dumps(ev, ensure_ascii=False, default=str)}\n\n"
                if ev.get("type") == "end":
                    break
            except queue.Empty:
                if time.time() - last_ping > 10:
                    yield ": ping\n\n"
                    last_ping = time.time()
            if not MONITOR.is_running() and MONITOR.events.empty():
                break

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


# ── 实验控制接口 ────────────────────────────────────────────────────────────


class StartPayload(BaseModel):
    simulate: bool = True
    address: Optional[str] = None
    adapter: Optional[str] = "bleak"  # bleak=内置蓝牙 | bled112=外置适配器
    serial_port: Optional[str] = None  # bled112 的串口号，留空自动检测
    config_path: Optional[str] = None
    baseline: Optional[int] = None
    duration: Optional[int] = None
    tag: Optional[str] = None
    participant: Optional[str] = None
    pre_state: Optional[str] = None
    contact_quality: Optional[str] = None
    post_state: Optional[str] = None
    note: Optional[str] = None


@app.post("/api/experiment/start")
def start_experiment(payload: StartPayload):
    if SESSION.is_running():
        raise HTTPException(status_code=409, detail="已有实验正在运行")
    _assert_no_other_session(SESSION)
    real = _resolve_config_path(payload.config_path)
    overrides = {"baseline_seconds": payload.baseline,
                 "duration_seconds": payload.duration, "tag": payload.tag}
    try:
        cfg = load_experiment_config(real, cli_overrides=overrides)
    except ValueError as ex:
        raise HTTPException(status_code=400, detail=str(ex))
    session_info = {"participant": payload.participant or "",
                    "pre_state": payload.pre_state or "",
                    "contact_quality": payload.contact_quality or "",
                    "post_state": payload.post_state or "",
                    "note": payload.note or ""}
    SESSION.start(cfg, simulate=payload.simulate, address=payload.address,
                  adapter=payload.adapter or "bleak",
                  serial_port=payload.serial_port,
                  session_info=session_info)
    mode = ("模拟" if payload.simulate
            else "真机（BLED112）" if payload.adapter == "bled112"
            else "真机蓝牙")
    return {"ok": True, "tag": cfg["experiment"]["tag"], "mode": mode}


@app.post("/api/experiment/stop")
def stop_experiment():
    if not SESSION.stop():
        raise HTTPException(status_code=409, detail="当前没有正在运行的实验")
    return {"ok": True, "message": "已发送停止指令，实验将在当前决策周期后结束"}


@app.get("/api/experiment/status")
def experiment_status():
    return SESSION.snapshot()


@app.get("/api/experiment/stream")
async def experiment_stream():
    """SSE 实时推流：把实验线程产生的事件持续推给前端。"""

    async def gen():
        loop = asyncio.get_running_loop()
        last_ping = time.time()
        while True:
            try:
                ev = await loop.run_in_executor(
                    None, lambda: SESSION.events.get(timeout=1.0))
                yield f"data: {json.dumps(ev, ensure_ascii=False, default=str)}\n\n"
                if ev.get("type") == "end":
                    break
            except queue.Empty:
                if time.time() - last_ping > 10:
                    yield ": ping\n\n"
                    last_ping = time.time()
            if not SESSION.is_running() and SESSION.events.empty():
                break

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


# ── VR 桥接接口（2026-09-05 A4） ────────────────────────────────────────────


@app.websocket("/ws/vr")
async def vr_ws(ws: WebSocket):
    """VR 客户端（Pico 浏览器等）连接入口：注册后即接收脑电指标广播。"""
    await ws.accept()
    VR.attach(ws, asyncio.get_running_loop())
    try:
        await ws.send_text(json.dumps({
            "type": "vr_connected", "clients": VR.count,
            "server_time": datetime.now().isoformat()}))
        while True:
            # 心跳：VR 端可发 ping，服务端回 pong；断开由异常捕获
            await ws.receive_text()
            await ws.send_text(json.dumps({"type": "pong"}))
    except Exception:
        pass
    finally:
        VR.detach(ws)


@app.get("/vr")
def vr_page():
    """VR 视觉反馈页（Pico 浏览器 / 桌面浏览器均可打开）。"""
    return FileResponse(os.path.join(SCRIPT_DIR, "vr_feedback.html"),
                        media_type="text/html; charset=utf-8",
                        headers={"Cache-Control": "no-store"})


@app.get("/vr_assets/{path:path}")
def vr_asset(path: str):
    """本地 3D 引擎文件（three.js 等），限定 vr_assets 目录。"""
    real = _safe_join(VR_ASSET_DIR, path)
    if not os.path.isfile(real):
        raise HTTPException(status_code=404, detail="资源不存在")
    media = ("text/javascript; charset=utf-8" if real.endswith(".js")
             else "text/html; charset=utf-8" if real.endswith(".html")
             else "application/octet-stream")
    return FileResponse(real, media_type=media,
                        headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/vr/status")
def vr_status():
    return {"clients": VR.count,
            "monitor_running": MONITOR.is_running(),
            "experiment_running": SESSION.is_running()}


@app.get("/api/vr/models")
def vr_models():
    """列出可供 VR 场景加载的 3D 模型（限 VR素材/3D模型 目录）。"""
    items = []
    if os.path.isdir(VR_MODEL_DIR):
        for name in sorted(os.listdir(VR_MODEL_DIR)):
            if name.lower().endswith((".glb", ".gltf")):
                full = os.path.join(VR_MODEL_DIR, name)
                items.append({"name": name,
                              "size_mb": round(os.path.getsize(full) / 1e6, 2)})
    return {"models": items}


@app.get("/api/vr/model")
def vr_model(name: str):
    """按文件名下发 3D 模型（限定目录，防路径穿越）。"""
    real = _safe_join(VR_MODEL_DIR, name)
    if not os.path.isfile(real):
        raise HTTPException(status_code=404, detail="模型不存在")
    return FileResponse(real, media_type="model/gltf-binary",
                        filename=os.path.basename(real))


# ── 历史实验浏览接口 ────────────────────────────────────────────────────────


def _safe_join(root, name):
    real = os.path.realpath(os.path.join(root, name))
    if not real.startswith(os.path.realpath(root) + os.sep):
        raise HTTPException(status_code=400, detail="非法路径")
    return real


@app.get("/api/experiments")
def list_experiments():
    """按时间戳前缀归组，列出历次实验的全部产物。"""
    groups = {}
    if os.path.isdir(EXP_DIR):
        for name in sorted(os.listdir(EXP_DIR), reverse=True):
            full = os.path.join(EXP_DIR, name)
            if not os.path.isfile(full):
                continue
            ts = name[:15] if len(name) > 15 and name[8] == "_" else name
            groups.setdefault(ts, []).append(name)
    result = []
    for ts, files in groups.items():
        files.sort()
        result.append({
            "timestamp": ts,
            "files": files,
            "mtime": datetime.fromtimestamp(os.path.getmtime(
                os.path.join(EXP_DIR, files[0]))).strftime("%Y-%m-%d %H:%M:%S"),
        })
    return {"experiments": result}


@app.get("/api/reports")
def list_reports():
    """列出脑电分析报告（HTML）与对应的原始数据（npz），附场景与质检结论。"""
    reports = []
    if os.path.isdir(REPORT_DIR):
        names = sorted(os.listdir(REPORT_DIR), reverse=True)
        npz_set = {n for n in names if n.endswith(".npz")}
        for name in names:
            if name.endswith(".report.html"):
                full = os.path.join(REPORT_DIR, name)
                npz_name = name.replace(".report.html", ".npz")
                npz_full = os.path.join(REPORT_DIR, npz_name)
                has_npz = npz_name in npz_set
                scene = "unknown"
                qc = None
                if has_npz:
                    try:
                        import numpy as np
                        with np.load(npz_full, allow_pickle=True) as d:
                            scene = str(d["meta"].item().get("scene", "unknown"))
                        qc = qc_assess(npz_full, full)
                    except Exception:
                        qc = None
                reports.append({
                    "name": name,
                    "npz": npz_name if has_npz else None,
                    "report_path": full,
                    "npz_path": npz_full if has_npz else None,
                    "scene": scene,
                    "qc": qc,
                    "mtime": datetime.fromtimestamp(os.path.getmtime(full)
                                                    ).strftime("%Y-%m-%d %H:%M:%S"),
                    "size": os.path.getsize(full),
                })
    return {"reports": reports}


@app.get("/api/file")
def get_file(path: str):
    """下载/预览实验目录或报告目录内的文件。"""
    if path.startswith("report/"):
        real = _safe_join(REPORT_DIR, path[len("report/"):])
    else:
        real = _safe_join(EXP_DIR, path)
    if not os.path.exists(real) or not os.path.isfile(real):
        raise HTTPException(status_code=404, detail="文件不存在")
    media = ("text/html" if real.endswith(".html")
             else "application/json" if real.endswith(".json")
             else "text/csv" if real.endswith(".csv")
             else "application/octet-stream")
    return FileResponse(real, media_type=media + "; charset=utf-8",
                        filename=os.path.basename(real))


# ── 本机档案接口（测试者默认可选，多人多份） ──────────────────────────────


class ProfilePayload(BaseModel):
    profiles: Optional[list] = None
    default_participant: Optional[str] = None


@app.get("/api/profiles")
def get_profiles():
    return load_profiles()


@app.post("/api/profiles")
def set_profiles(payload: ProfilePayload):
    """整体保存本机档案列表与默认测试者。"""
    data = {"profiles": payload.profiles if payload.profiles is not None
            else load_profiles()["profiles"],
            "default_participant": payload.default_participant or ""}
    save_profiles(data)
    return {"ok": True}


# ── 登记表与预登记接口 ──────────────────────────────────────────────────────


class PreregisterPayload(BaseModel):
    participant: str
    session_type: str = "baseline"
    date: Optional[str] = None  # YYYY-MM-DD，缺省取今天
    note: Optional[str] = None


@app.get("/api/registry")
def get_registry():
    return {"rows": _read_registry_rows(), "session_types": SESSION_TYPES}


@app.post("/api/registry/preregister")
def preregister(payload: PreregisterPayload):
    """新建预登记（SOP V0.2 先登记后采集）；Zen-ID 永不复用。"""
    p = payload.participant.strip()
    if not re.fullmatch(r"P\d{3}", p):
        raise HTTPException(status_code=400,
                            detail="受试者编号格式应为 P001 形式")
    if payload.session_type not in SESSION_TYPES:
        raise HTTPException(status_code=400, detail="会话类型不合法")
    date = payload.date or datetime.now().strftime("%Y-%m-%d")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise HTTPException(status_code=400, detail="日期格式应为 YYYY-MM-DD")
    rows = _read_registry_rows()
    date_compact = date.replace("-", "")
    s_num = _next_session_number(rows, p)
    sid = f"ZEN-{date_compact}-{p}-{s_num}"
    if any(r["session_id"] == sid for r in rows):
        raise HTTPException(status_code=409,
                            detail=f"{sid} 已存在，Zen-ID 永不复用")
    rows.append({"session_id": sid, "participant_id": p, "date": date,
                 "session_type": payload.session_type,
                 "duration_seconds": "", "status": "planned"})
    _write_registry_rows(rows)
    return {"ok": True, "session_id": sid}


# ── 一键入库接口（服务端代执行入库脚本，输出回传前端） ─────────────────────


class IngestPayload(BaseModel):
    npz: str
    report: Optional[str] = None
    participant: str = ""
    session_type: str = ""
    sid: Optional[str] = None
    quarantine: bool = False
    scene: Optional[str] = None
    note: Optional[str] = None
    pre_state: Optional[str] = None
    post_state: Optional[str] = None
    contact_quality: Optional[str] = None


@app.post("/api/ingest")
def ingest(payload: IngestPayload):
    """执行入库脚本（正式入库或隔离区落盘），返回脚本输出。"""
    if not os.path.exists(payload.npz):
        raise HTTPException(status_code=400, detail="npz 文件不存在")
    if payload.session_type not in SESSION_TYPES:
        raise HTTPException(status_code=400, detail="会话类型不合法")
    if not re.fullmatch(r"P\d{3}", payload.participant.strip()):
        raise HTTPException(status_code=400,
                            detail="受试者编号格式应为 P001 形式")
    if payload.scene not in (None, "monitor", "closedloop"):
        raise HTTPException(status_code=400, detail="场景标记不合法")
    cmd = [sys.executable, INGEST_TOOL,
           "--npz", payload.npz,
           "--participant", payload.participant.strip(),
           "--type", payload.session_type,
           "--operator", "tiand"]
    if payload.report and os.path.exists(payload.report):
        cmd += ["--report", payload.report]
    if payload.sid:
        cmd += ["--sid", payload.sid.strip()]
    if payload.quarantine:
        cmd.append("--quarantine")
    if payload.scene:
        cmd += ["--scene", payload.scene]
    for name, value in (("--note", payload.note),
                        ("--pre-state", payload.pre_state),
                        ("--post-state", payload.post_state),
                        ("--contact-quality", payload.contact_quality)):
        if value:
            cmd += [name, value]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=120, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="入库脚本执行超时")
    output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    return {"ok": proc.returncode == 0, "returncode": proc.returncode,
            "output": output.strip()}


@app.get("/api/ingest/qc")
def ingest_qc(npz: str, report: Optional[str] = None):
    """对已保存的会话数据做质检评估（不入库）。"""
    if not os.path.exists(npz):
        raise HTTPException(status_code=400, detail="npz 文件不存在")
    return qc_assess(npz, report)


@app.get("/api/quarantine")
def list_quarantine():
    """列出隔离区会话（含隔离原因摘要）。"""
    quarantine_root = os.path.join(ZEN_ROOT, "03_quality_control", "quarantine")
    items = []
    if os.path.isdir(quarantine_root):
        for name in sorted(os.listdir(quarantine_root), reverse=True):
            full = os.path.join(quarantine_root, name)
            if not os.path.isdir(full):
                continue
            reason = ""
            note_path = os.path.join(full, "session_note.txt")
            if os.path.exists(note_path):
                with open(note_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if line.startswith("notes:"):
                            reason = line[len("notes:"):].strip()
                            break
            items.append({
                "session_id": name,
                "mtime": datetime.fromtimestamp(os.path.getmtime(full)
                                                ).strftime("%Y-%m-%d %H:%M"),
                "reason": reason,
            })
    return {"items": items, "root": quarantine_root}


# ── 前端页面 ────────────────────────────────────────────────────────────────


@app.get("/")
def index():
    return FileResponse(os.path.join(SCRIPT_DIR, "console.html"),
                        media_type="text/html; charset=utf-8",
                        headers={"Cache-Control": "no-store"})


def main():
    ap = argparse.ArgumentParser(description="止观AI 统一控制台服务")
    ap.add_argument("--port", type=int, default=8777)
    ap.add_argument("--host", type=str, default="0.0.0.0",
                    help="2026-09-05 起默认监听所有网卡，供 Pico 头显同网访问；"
                         "仅本机使用可传 127.0.0.1")
    ap.add_argument("--https-port", type=int, default=8778,
                    help="HTTPS 端口（WebXR 需要安全上下文，Pico 进 VR 走此端口）；"
                         "传 0 关闭 HTTPS")
    args = ap.parse_args()

    # 计算局域网地址供 VR 端使用
    lan_ip = None
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        lan_ip = s.getsockname()[0]
        s.close()
    except Exception:
        pass

    import uvicorn

    # HTTPS 证书（WebXR 安全上下文要求；自签证书，仅局域网自用）
    ssl_kwargs = {}
    if args.https_port:
        try:
            from local_tls import ensure_cert
            cert, key = ensure_cert()
            ssl_kwargs = {"ssl_certfile": cert, "ssl_keyfile": key}
        except Exception as ex:
            print(f"[警告] 自签证书生成失败，HTTPS 关闭: {ex}")
            args.https_port = 0

    print("=" * 62)
    print("止观AI 统一控制台已启动（监测 + 实验双模式）")
    print(f"本机浏览器打开: http://127.0.0.1:{args.port}")
    if lan_ip:
        print(f"VR 端（Pico 浏览器）打开: http://{lan_ip}:{args.port}/vr")
        if args.https_port:
            print(f"  ↳ 进入 VR 必须用 HTTPS: https://{lan_ip}:{args.https_port}/vr")
            print(f"    （首次打开提示证书不受信任时，选择“继续访问”）")
    print("按 Ctrl+C 停止服务")
    print("=" * 62)

    if args.https_port:
        # 双端口：HTTP(控制台) + HTTPS(VR/WebXR)，同一 app、同一事件循环
        cfg_http = uvicorn.Config(app, host=args.host, port=args.port,
                                  log_level="warning")
        cfg_https = uvicorn.Config(app, host=args.host, port=args.https_port,
                                   log_level="warning", **ssl_kwargs)
        srv_http = uvicorn.Server(cfg_http)
        srv_https = uvicorn.Server(cfg_https)

        async def serve_both():
            await asyncio.gather(srv_http.serve(), srv_https.serve())
        try:
            asyncio.run(serve_both())
        except KeyboardInterrupt:
            pass
    else:
        uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
