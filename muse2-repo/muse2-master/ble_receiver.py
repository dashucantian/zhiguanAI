#!/usr/bin/env python3
"""
ble_receiver.py —— 唯一硬件层：Muse S 蓝牙直连接收器（无 GUI 依赖）

本模块是项目中唯一负责"头环蓝牙连接与数据解码"的模块，从 muse_direct.py
抽离而来（2026-09-01 架构统一），供两类上层共用：
  - muse_direct.py     Tk 监测窗口（调试工具）
  - console_server.py  Web 统一控制台（正式入口）
  - closedloop/openloop_experiment.py  实验脚本

设计约定：
  - 不导入 tkinter / zh_ui，不创建任何窗口；界面适配通过鸭子类型的
    `app` 对象完成（只需 after() 与 bottom_label 两个成员）。
  - 数据解码后统一投递进 muse_local_server.DataBuffer。
  - V1.2 数据流看门狗：连续 WATCHDOG_SILENCE_SEC 秒无新数据判定静默
    断连，自动保存已采数据并声音告警（幂等）。
"""

import asyncio
import threading
import time
from datetime import datetime, timezone

# 路径准备：本文件与 muse_local_server.py 同目录，保证直接运行时也可导入
import os
import sys
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from muse_local_server import CHANNELS, PPG_HR_CHANNEL  # noqa: E402

import OpenMuse  # noqa: F401,E402  (真机验证过的连接/解码库)
from OpenMuse import decode as om_decode  # noqa: E402
from OpenMuse.muse import MuseS, find_muse  # noqa: E402
import bleak  # noqa: E402

# EEG 主通道在 OpenMuse 解码结果中的列索引（TP9, AF7, AF8, TP10 恒为前 4 列）
MAIN_EEG_IDX = (0, 1, 2, 3)
# OpenMuse 光学通道名 → 界面缓冲通道名（去掉 OPTICS_ 前缀即一致）
_OPTICS_PREFIX = "OPTICS_"
# EEG 直流分量滤除系数（每采样点一阶 EMA，时间常数约 0.8s）
DC_ALPHA = 0.008
# V1.2 数据流看门狗：连续超过该秒数没有新数据包，判定为静默断连
WATCHDOG_SILENCE_SEC = 10.0
# V1.3（2026-09-06）静默断连自动重连：最多尝试次数与重试间隔。
# 重连期间不保存、不中止会话；次数用尽才走原"自动保存+告警"路径。
RECONNECT_MAX_ATTEMPTS = 3
RECONNECT_DELAY_SEC = 5.0


class BleDirectReceiver:
    """蓝牙直连接收器：接口形态与原 UdpReceiver 对齐，可直接挂进界面。

    在后台线程中运行 asyncio 事件循环：
      扫描 → 连接 → 订阅数据通道 → 发送握手指令 → 持续接收解码
    """

    def __init__(self, app, address=None, preset="p1041", scan_timeout=10):
        self.app = app
        self.buffer = app.buffer
        self.address = address
        self.preset = preset
        self.scan_timeout = scan_timeout

        # 与 UdpReceiver 兼容的状态属性
        self.packet_count = 0   # 成功解码的子包数
        self.raw_count = 0      # 收到的 BLE 通知数
        self.last_addr = None
        self.last_error = None

        self.running = False
        self.battery_percent = None
        self.on_status = None  # 可选外部状态回调 fn(text)，供控制台等上层透传
        self._connected = threading.Event()
        self._stop_event = threading.Event()
        self._thread = None
        self._watchdog_thread = None
        self._disconnect_handled = False  # V1.2 幂等断连处理标记
        self._last_data_time = time.time()   # 最近一次收到数据的时刻
        self._reconnect_attempts = 0      # V1.3 自动重连已用次数（收到数据即清零）
        self._session_stop = threading.Event()  # V1.3 本轮连接会话结束信号（重连用）
        self._reconnecting = False        # V1.3 重连进行中标记（防看门狗重复触发）
        self._dc = {}  # 每通道直流分量估计
        # 1–40 Hz 显示滤波器（逐批增量滤波，去除直流漂移与 50Hz 工频干扰）
        from scipy.signal import butter, lfilter, lfilter_zi
        self._b, self._a = butter(2, [1.0 / 128.0, 40.0 / 128.0], btype="band")
        self._lfilter = lfilter
        self._lfilter_zi = lfilter_zi
        self._zi = {}  # 每通道滤波器状态

    # ── 生命周期 ────────────────────────────────────────────────────────
    def start(self):
        self._last_data_time = time.time()
        self._thread = threading.Thread(target=self._run_thread, daemon=True)
        self._thread.start()
        # V1.2 数据流看门狗：监控静默断连
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop, daemon=True)
        self._watchdog_thread.start()
        # V1.3 重连监督线程：断连后按预算自动重建连接会话
        self._supervisor_thread = threading.Thread(
            target=self._reconnect_loop, daemon=True)
        self._supervisor_thread.start()

    def stop(self):
        self._stop_event.set()
        self._session_stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        self.running = False

    def is_connected(self):
        return self._connected.is_set()

    def _watchdog_loop(self):
        """V1.2/V1.3 数据流看门狗：已连接后若连续 WATCHDOG_SILENCE_SEC 秒无新数据，
        判定为静默断连。V1.3：先交由重连监督线程自动重连（不保存、不中止会话）；
        重连预算用尽才触发自动保存+告警（原 V1.2 行为）。"""
        while not self._stop_event.is_set():
            time.sleep(1.0)
            if not (self._connected.is_set() and self.running):
                continue
            if self._reconnecting:
                continue
            silence = time.time() - self._last_data_time
            if silence > WATCHDOG_SILENCE_SEC:
                if self._request_reconnect(f"数据流静默 {silence:.0f} 秒"):
                    continue
                reason = (f"数据流静默 {silence:.0f} 秒（疑似蓝牙断开，"
                          f"重连 {RECONNECT_MAX_ATTEMPTS} 次未成功）")
                self._ui_msg(f"❌ {reason}，正在自动保存并停止...")
                self._connected.clear()
                self.running = False
                self._stop_event.set()  # 让 _main 的事件循环退出
                self._handle_abnormal_disconnect(reason)
                return

    def _request_reconnect(self, cause):
        """V1.3 统一重连委托：预算内则置位重连并终止当前连接会话，返回 True；
        预算用尽返回 False（调用方走原保存+终止路径）。"""
        if self._reconnecting or self._stop_event.is_set():
            return False
        if self._reconnect_attempts >= RECONNECT_MAX_ATTEMPTS:
            return False
        self._reconnect_attempts += 1
        n = self._reconnect_attempts
        self._ui_msg(f"⚠️ {cause}，自动重连（第 {n}/{RECONNECT_MAX_ATTEMPTS} 次）...")
        self._connected.clear()
        self.running = False
        self._reconnecting = True
        self._session_stop.set()  # 让当前 _main 事件循环退出
        return True

    def _reconnect_loop(self):
        """V1.3 重连监督：_reconnecting 置位后等待旧事件循环退出，
        延迟 RECONNECT_DELAY_SEC 秒后重建连接会话；失败则按预算重试。"""
        while not self._stop_event.is_set():
            time.sleep(0.5)
            if not self._reconnecting:
                continue
            # 等旧线程退出（最多 8 秒），避免新旧事件循环争抢串口/蓝牙句柄
            for _ in range(16):
                if self._thread is None or not self._thread.is_alive():
                    break
                time.sleep(0.5)
            if self._stop_event.is_set():
                return
            self._ui_msg(f"🔄 {RECONNECT_DELAY_SEC:.0f} 秒后尝试重新连接头环...")
            time.sleep(RECONNECT_DELAY_SEC)
            if self._stop_event.is_set():
                return
            # 重建连接会话（保留已采缓冲；新线程接管 _thread）
            self._session_stop = threading.Event()
            self._reconnecting = False
            self._last_data_time = time.time()
            self._thread = threading.Thread(
                target=self._run_thread, daemon=True)
            self._thread.start()

    def _handle_abnormal_disconnect(self, reason):
        """幂等的异常断连处理：只有第一次调用真正执行自动保存+告警。"""
        if self._disconnect_handled:
            return
        self._disconnect_handled = True
        self.last_error = reason
        self.buffer.save_on_disconnect(reason=reason, app=self.app)

    def _run_thread(self):
        try:
            asyncio.run(self._main())
        except Exception as e:
            if not self._session_stop.is_set():
                self.last_error = str(e)
                self._ui_msg(f"❌ 蓝牙连接出错: {e}")
        finally:
            self.running = False
            # V1.3：重连进行中（_session_stop 由看门狗置位）→ 不保存、不告警，
            # 交由重连监督线程重建会话；否则按原 V1.2 路径自动保存+告警（幂等）
            if self._session_stop.is_set() and self._reconnecting:
                return
            if not self._stop_event.is_set() or self.last_error:
                self._handle_abnormal_disconnect(self.last_error or "蓝牙断连")

    # ── 主流程（运行于后台线程的事件循环） ──────────────────────────────
    # 注意：本连接流程已于 2026-09-01 上午两次真机验证成功
    # （08:33 闭环 10 分钟、10:31 闭环 5 分钟），为当前唯一验证过的
    # 连接形态，请勿改动（连接失败问题已定位为系统蓝牙栈层面，
    # 属环境性故障，见进程看板阶段 5c）。
    async def _main(self):
        addr = self.address
        if not addr:
            self._ui_msg(f"🔍 正在扫描 Muse 头环（最长 {self.scan_timeout} 秒）...")
            devices = await asyncio.to_thread(find_muse, self.scan_timeout, False)
            if not devices:
                if not self._request_reconnect("未扫描到 Muse 头环"):
                    self.last_error = "未扫描到 Muse 头环"
                    self._ui_msg("❌ 未扫描到头环。请确认头环已开机（蓝灯亮）且在 2 米内，然后重新点 Start")
                return
            addr = devices[0]["address"]
            name = devices[0].get("name", "?")
            self._ui_msg(f"✅ 发现 {name}，正在连接...")

        self.last_addr = addr
        try:
            async with bleak.BleakClient(
                    addr, timeout=15.0, use_cached_services=False) as client:
                callbacks = {
                    MuseS.EEG_UUID: self._make_cb(MuseS.EEG_UUID),
                    MuseS.OTHER_UUID: self._make_cb(MuseS.OTHER_UUID),
                }
                await MuseS.connect_and_initialize(
                    client, self.preset, callbacks, verbose=True)

                self.running = True
                self._connected.set()
                self._ui_msg(f"🧠 已连接 {addr} — 数据流传输中")

                while not self._stop_event.is_set() \
                        and not self._session_stop.is_set():
                    await asyncio.sleep(0.1)

                if not self._session_stop.is_set():
                    await MuseS.stop_streaming(client)
        except Exception as e:
            if not self._stop_event.is_set():
                if not self._request_reconnect(f"连接断开或失败: {e}"):
                    self.last_error = str(e)
                    self._ui_msg(f"❌ 连接断开或失败: {e}")

    def _make_cb(self, uuid):
        def cb(_sender, data):
            self._feed(uuid, bytes(data))
        return cb

    def _ui_msg(self, text):
        """线程安全地更新界面底部状态栏，并透传给外部回调。"""
        if self.on_status:
            try:
                self.on_status(text)
            except Exception:
                pass
        try:
            self.app.after(0, lambda: self.app.bottom_label.config(text=text))
        except Exception:
            pass

    # ── 数据解码与投递 ──────────────────────────────────────────────────
    def _feed(self, uuid, data):
        self.raw_count += 1
        self._last_data_time = time.time()  # V1.2 看门狗：刷新数据流活性
        self._reconnect_attempts = 0        # V1.3：数据恢复即重置重连预算
        ts = datetime.now(timezone.utc).isoformat()
        line = f"{ts}\t{uuid}\t{data.hex()}"
        try:
            parsed = om_decode.parse_message(line)
        except Exception as e:
            print(f"parse error: {e}")
            return

        buf = self.buffer
        n_decoded = 0

        # ── EEG（4 主通道，去直流 + 滤波后送入界面）──
        import numpy as _np
        for sub in parsed["EEG"]:
            arr = sub["data"]  # (n_samples, n_channels)
            nch = arr.shape[1]
            batch = []
            for i in MAIN_EEG_IDX:
                if i >= nch:
                    continue
                ch = CHANNELS[i]
                raw = arr[:, i].astype(float)
                # 去直流
                dc = self._dc.get(ch)
                if dc is None:
                    dc = float(raw[0])
                out_vals = []
                for v in raw:
                    dc = dc + DC_ALPHA * (v - dc)
                    out_vals.append(v - dc)
                self._dc[ch] = dc
                x = _np.asarray(out_vals, dtype=float)
                # 1–40 Hz 增量带通滤波
                zi = self._zi.get(ch)
                if zi is None:
                    zi = self._lfilter_zi(self._b, self._a) * x[0]
                y, zi = self._lfilter(self._b, self._a, x, zi=zi)
                self._zi[ch] = zi
                batch.append(y)
            if batch:
                n_s = batch[0].shape[0]
                flat = []
                for s in range(n_s):
                    for i in range(len(CHANNELS)):
                        flat.append(float(batch[i][s]) if i < len(batch) else 0.0)
                    flat.append(0.0)  # 第 5 列占位
                buf.add_eeg(flat)
                n_decoded += 1

        # ── 光学 / PPG（按通道名送入）──
        for sub in parsed["OPTICS"]:
            arr = sub["data"]  # (n_samples, n_channels)
            nch = arr.shape[1]
            names = om_decode.select_optics_channels(nch)
            with buf.lock:
                buf.optics_n_ch = max(buf.optics_n_ch, nch)
                for s in range(arr.shape[0]):
                    for c, raw_name in enumerate(names):
                        name = raw_name[len(_OPTICS_PREFIX):] if raw_name.startswith(_OPTICS_PREFIX) else raw_name
                        v = float(arr[s, c])
                        if name in buf.optics:
                            buf.optics[name].append(v)
                        if name == PPG_HR_CHANNEL:
                            buf.ppg_ir.append(v)
                            buf.ppg_ir_analysis.append(v)
            n_decoded += 1

        # ── 加速度计 / 陀螺仪 ──
        for sub in parsed["ACCGYRO"]:
            arr = sub["data"]  # (3, 6)
            for row in arr:
                buf.add_acc([float(row[0]), float(row[1]), float(row[2])])
                buf.add_gyro([float(row[3]), float(row[4]), float(row[5])])
            n_decoded += 1

        # ── 电池 ──
        for sub in parsed["BATTERY"]:
            arr = sub["data"]
            if arr.size > 0:
                self.battery_percent = float(arr.flat[0])

        self.packet_count += n_decoded


# ══════════════════════════════════════════════════════════════════
# BLED112 外置蓝牙适配器支持（2026-09-05 新增，可选路径）
# ══════════════════════════════════════════════════════════════════

BLED112_VID = 0x2458  # Bluegiga / Silicon Labs


def detect_bled112_port():
    """自动发现 BLED112 适配器占用的串口号（如 COM3）；未插入时返回 None。"""
    try:
        from serial.tools import list_ports
        for p in list_ports.comports():
            if getattr(p, "vid", None) == BLED112_VID:
                return p.device
    except Exception:
        pass
    return None


class _BgapiClientAdapter:
    """pygatt BGAPIBLEDevice → bleak 风格异步接口的适配层。

    OpenMuse 的 MuseS.connect_and_initialize / send_command 只依赖两个方法：
    start_notify(uuid, callback) 与 write_gatt_char(uuid, data, response)。
    通过这层适配即可完整复用已验证过的握手与解码逻辑，零改动。
    """

    def __init__(self, device):
        self._device = device

    async def start_notify(self, uuid, callback):
        def _cb(handle, value):
            callback(handle, bytearray(value))
        await asyncio.to_thread(self._device.subscribe, uuid, _cb, False)

    async def write_gatt_char(self, uuid, data, response=False):
        # V1.3 修复（2026-09-06）：BLED112 上对 Muse 控制特征一律用
        # "写命令"（wait_for_response=False）。原实现把 response 语义反转，
        # 默认走 char_write_handle 等待写响应，而该特征不支持写响应，
        # 导致握手第一条指令即超时、连接建立后无数据流。
        await asyncio.to_thread(
            self._device.char_write, uuid, bytes(data), False)


class BleBgapiReceiver(BleDirectReceiver):
    """BLED112 外置适配器接收器：BGAPI 串口直连，绕过 Windows 系统蓝牙栈。

    与内置蓝牙路径（BleDirectReceiver）的区别仅在连接通道：
      - 内置路径：bleak → Windows WinRT 蓝牙栈（Mediatek 内置适配器）
      - 本类：pygatt BGAPIBackend → BLED112 串口（COM 口）→ 头环
    连接成功后的握手、解码、缓冲、看门狗全部复用父类，行为一致。
    """

    def __init__(self, app, address=None, preset="p1041", scan_timeout=10,
                 serial_port=None):
        super().__init__(app, address=address, preset=preset,
                         scan_timeout=scan_timeout)
        self.serial_port = serial_port  # 如 "COM3"

    async def _main(self):
        import pygatt

        if not self.serial_port:
            self.last_error = "未指定 BLED112 串口"
            self._ui_msg("❌ 未检测到 BLED112 适配器串口")
            return

        self._ui_msg(f"🔌 正在初始化 BLED112 适配器（{self.serial_port}）...")
        backend = pygatt.BGAPIBackend(serial_port=self.serial_port)
        try:
            backend.start()
        except Exception as e:
            if not self._request_reconnect(f"BLED112 初始化失败: {e}"):
                self.last_error = f"BLED112 初始化失败: {e}"
                self._ui_msg(f"❌ {self.last_error}（请确认适配器已插入且未被占用）")
            return

        try:
            addr = self.address
            if not addr:
                self._ui_msg(
                    f"🔍 正在通过 BLED112 扫描 Muse 头环（{self.scan_timeout} 秒）...")
                devices = await asyncio.to_thread(
                    backend.scan, self.scan_timeout, active=True)

                def _d_name(d):
                    if isinstance(d, dict):
                        return d.get("name")
                    return getattr(d, "name", None)

                def _d_addr(d):
                    if isinstance(d, dict):
                        return d.get("address")
                    return getattr(d, "address", None)

                muses = [d for d in devices
                         if "muse" in (_d_name(d) or "").lower()]
                if not muses:
                    if not self._request_reconnect("BLED112 扫描未发现 Muse 头环"):
                        self.last_error = "BLED112 扫描未发现 Muse 头环"
                        self._ui_msg("❌ 未扫描到头环。请确认头环已开机（蓝灯亮）且在 2 米内")
                    return
                addr = _d_addr(muses[0])
                self._ui_msg(f"✅ 发现 {_d_name(muses[0])}（{addr}），正在连接...")

            # 连接：先尝试 public 地址，失败再试 random
            device = None
            last_exc = None
            for atype in (pygatt.BLEAddressType.public,
                          pygatt.BLEAddressType.random):
                try:
                    device = await asyncio.to_thread(
                        backend.connect, addr, timeout=15, address_type=atype)
                    break
                except Exception as e:
                    last_exc = e
            if device is None:
                if not self._request_reconnect(f"BLED112 连接失败: {last_exc}"):
                    self.last_error = f"BLED112 连接失败: {last_exc}"
                    self._ui_msg(f"❌ {self.last_error}")
                return

            # 连接稳定后，用适配层复用 OpenMuse 握手（与内置路径完全相同）
            await asyncio.sleep(0.5)
            client = _BgapiClientAdapter(device)
            callbacks = {
                MuseS.EEG_UUID: self._make_cb(MuseS.EEG_UUID),
                MuseS.OTHER_UUID: self._make_cb(MuseS.OTHER_UUID),
            }
            await MuseS.connect_and_initialize(
                client, self.preset, callbacks, verbose=True)

            self.running = True
            self._connected.set()
            self._ui_msg(f"🧠 已通过 BLED112 连接 {addr} — 数据流传输中")

            while not self._stop_event.is_set() \
                    and not self._session_stop.is_set():
                await asyncio.sleep(0.1)

            try:
                await MuseS.stop_streaming(client)
            except Exception:
                pass
        except Exception as e:
            if not self._stop_event.is_set():
                if not self._request_reconnect(f"BLED112 数据流中断: {e}"):
                    self.last_error = str(e)
                    self._ui_msg(f"❌ 连接断开或失败: {e}")
        finally:
            try:
                backend.stop()
            except Exception:
                pass
