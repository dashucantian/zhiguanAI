"""NeuraDock TCP 数据流接收器（硬件层，2026-09-08）

与 BleDirectReceiver 同一鸭子接口（running/last_error/packet_count/
battery_percent/on_status/start/stop/is_connected），可直接挂进
console_server 的 _worker 与 closedloop_experiment，实现"单一硬件层、
多设备可切换"的统一架构。

协议依据（厂商开源仓库，2026-09-08 克隆研读定版）：
  - eeg-workstation-agent/docs/data-protocol.md
  - eeg-workstation-agent/configs/neuradock-v1.json
  - neuradock-codex-plugin/scripts/{neuradock_mcp.mjs, mock_neuradock_server.mjs}
要点：
  1. NeuraDock 软件"打开数据服务"后为 TCP 服务器（默认 127.0.0.1:9600，端口可改）；
  2. 客户端连上后必须先发送 "start"，服务器才开始按行推 CSV；
  3. 每行 = timestamp, marker, 然后 (7 EEG + 1 保留) 重复若干组：
       USB 模式 10 字段（1 组，无打包延迟）；蓝牙模式 42 字段（5 组）；
  4. 通道定版顺序：0=CP5 1=CP6 2=PO3 3=PO4 4=O1 5=Oz 6=O2，250Hz，µV；
  5. TCP 可能把一行拆成多个包到达（官方 mock 故意如此），须按行缓冲解析；
  6. timestamp 字段是相对秒（非 epoch），到达时间以本地时钟为准（与 BLE 路径一致）。

信号调理：与 Muse 接收路径同构——去直流（一阶 EMA）+ 1–40Hz 带通后送入
buffer，保证下游（频段功率/状态分类/VR 映射/报告）对两种设备行为一致。
"""
import threading
import time

import numpy as np

# ── 设备档案（定版自官方 configs/neuradock-v1.json） ──────────────────────
ND_CHANNELS = ["CP5", "CP6", "PO3", "PO4", "O1", "Oz", "O2"]
ND_SFREQ = 250.0
ND_N_CH = 7
_START_CMD = b"start"
_BT_MIN_FIELDS = 42          # 2 + 5*(7+1)
_USB_MIN_FIELDS = 10         # 2 + 1*(7+1)

# 数据流看门狗：连续超过该秒数没有新行，判定为断流（与 BLE 路径同参数）
WATCHDOG_SILENCE_SEC = 10.0
RECONNECT_MAX_ATTEMPTS = 3
RECONNECT_DELAY_SEC = 5.0
# EEG 直流分量滤除系数（每采样点一阶 EMA，时间常数约 0.8s，与 Muse 路径一致）
DC_ALPHA = 0.008
# 异常值阈值（官方质检用 100µV；超限样本视为坏行丢弃，不污染缓冲）
OUTLIER_UV = 100.0 * 20      # 放宽 20 倍：官方阈值用于"段级质检"，实时丢弃须保守得多


class TcpReceiver:
    """NeuraDock 数据服务 TCP 客户端接收器。

    app 需提供 .buffer（DataBuffer，按 neuradock 布局构造）；
    host/port 为数据服务地址（软件"打开数据服务"后界面上显示的 Local IP/端口）。
    """

    def __init__(self, app, host="127.0.0.1", port=9600, transport="auto"):
        self.app = app
        self.buffer = app.buffer
        self.host = host
        self.port = int(port)
        self.transport = transport      # auto | usb | bluetooth

        # 与其它接收器对齐的状态属性
        self.packet_count = 0           # 成功解析的行数
        self.raw_count = 0              # 收到的完整行数（含坏行）
        self.bad_line_count = 0
        self.last_addr = f"{host}:{port}"
        self.last_error = None
        self.running = False
        self.battery_percent = None     # TCP 流不含电量信息
        self.on_status = None           # 可选外部状态回调 fn(text)
        self.detected_transport = None

        self._stop_event = threading.Event()
        self._connected = threading.Event()
        self._thread = None
        self._watchdog_thread = None
        self._reconnecting = False
        self._reconnect_attempts = 0
        self._last_data_time = time.time()
        self._last_t_rel = None         # 上一行采信的设备相对秒（时基外推用）
        self._last_batch_dur = 0.0
        self._dc = np.zeros(ND_N_CH)    # 每通道直流估计
        self._zi = None                 # 带通滤波器状态（一次性初始化）
        self._b = self._a = None

    # ── 生命周期 ────────────────────────────────────────────────────────
    def start(self):
        self.running = True
        self._last_data_time = time.time()
        self._thread = threading.Thread(target=self._run_forever, daemon=True)
        self._thread.start()
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop, daemon=True)
        self._watchdog_thread.start()

    def stop(self):
        self._stop_event.set()
        self.running = False
        if self._thread:
            self._thread.join(timeout=5)

    def is_connected(self):
        return self._connected.is_set()

    def _msg(self, text):
        print(f"[neuradock] {text}")
        cb = self.on_status
        if cb:
            try:
                cb(text)
            except Exception:
                pass

    # ── 主循环：连接 → start 握手 → 按行解析；断线按预算重连 ────────────
    def _run_forever(self):
        while not self._stop_event.is_set():
            ok = self._session()
            if self._stop_event.is_set():
                break
            if not ok:
                # 会话失败：重连预算内则重试，用尽走"自动保存+告警"
                if self._reconnect_attempts >= RECONNECT_MAX_ATTEMPTS:
                    reason = (f"NeuraDock 数据服务连接失败"
                              f"（重连 {RECONNECT_MAX_ATTEMPTS} 次未成功：{self.last_error}）")
                    self._msg(f"❌ {reason}，正在自动保存并停止...")
                    self.running = False
                    self._connected.clear()
                    self._handle_abnormal_disconnect(reason)
                    return
                self._reconnect_attempts += 1
                self._msg(f"⚠️ 连接中断，自动重连"
                          f"（第 {self._reconnect_attempts}/{RECONNECT_MAX_ATTEMPTS} 次）...")
                self._connected.clear()
                for _ in range(int(RECONNECT_DELAY_SEC * 2)):
                    if self._stop_event.is_set():
                        return
                    time.sleep(0.5)
            else:
                # 正常结束（对端关闭或看门狗判停）
                self.running = False
                return
        self.running = False

    def _session(self):
        """一次 TCP 会话。返回 True=正常结束（主动停止/对端优雅关闭且不再重连），
        False=异常（供外层重连决策）。"""
        import socket
        sock = None
        try:
            sock = socket.create_connection((self.host, self.port), timeout=5)
            sock.settimeout(2.0)
            sock.sendall(_START_CMD)                    # 官方协议：发 "start" 开始推流
            self._connected.set()
            self._reconnect_attempts = 0                # 连上即重置预算
            self._last_data_time = time.time()
            self._msg(f"✅ 已连接 NeuraDock 数据服务 {self.host}:{self.port}（已发送 start）")
            self._read_loop(sock)
            return True
        except (ConnectionRefusedError, TimeoutError, OSError) as e:
            self.last_error = f"{type(e).__name__}: {e}"
            self._msg(f"❌ 无法连接数据服务 {self.host}:{self.port}：{self.last_error}"
                      "（请确认 NeuraDock 软件已打开且已点击'打开数据服务'）")
            return False
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"
            self._msg(f"❌ 数据流异常：{self.last_error}")
            return False
        finally:
            self._connected.clear()
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass

    def _read_loop(self, sock):
        """按行缓冲解析。官方 mock 故意把一行拆成两次 TCP 写，必须攒到换行再解。"""
        buf = b""
        while self.running and not self._stop_event.is_set():
            try:
                chunk = sock.recv(4096)
            except TimeoutError:
                continue                    # 静默判定交给看门狗线程
            except OSError as e:
                if not self._stop_event.is_set():
                    self.last_error = f"recv: {e}"
                return
            if not chunk:                   # 对端关闭
                self.last_error = None
                return
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                self._handle_line(line)

    def _handle_line(self, raw: bytes):
        text = raw.decode("utf-8", "replace").strip()
        if not text:
            return
        self.raw_count += 1
        self._last_data_time = time.time()
        fields = [f.strip() for f in text.split(",")]

        # 传输模式自动识别（官方桥同款判据）
        if len(fields) >= _BT_MIN_FIELDS:
            groups, mode = 5, "bluetooth"
        elif len(fields) >= _USB_MIN_FIELDS:
            groups, mode = 1, "usb"
        else:
            self.bad_line_count += 1
            return
        if self.transport != "auto" and self.transport != mode:
            self.bad_line_count += 1
            return
        expected = 2 + groups * (ND_N_CH + 1)
        if len(fields) < expected:
            self.bad_line_count += 1
            return
        if self.detected_transport is None:
            self.detected_transport = mode
            self._msg(f"📡 检测到 {mode} 模式数据流（{ND_SFREQ:.0f}Hz × {ND_N_CH}通道，µV）")

        samples = []
        for g in range(groups):
            base = 2 + g * (ND_N_CH + 1)
            try:
                vals = [float(x) for x in fields[base:base + ND_N_CH]]
            except ValueError:
                self.bad_line_count += 1
                return
            if not all(np.isfinite(vals)):
                self.bad_line_count += 1
                return
            if max(abs(v) for v in vals) > OUTLIER_UV:
                # 超量程多为电极瞬态；计数并丢弃该样本，避免污染滤波状态
                self.bad_line_count += 1
                continue
            samples.append(vals)
        if not samples:
            return

        # 行首字段为设备相对秒（mock/官方桥一致）；解析失败则回退 None（到达时刻）。
        # 防御设备时钟回退/跳变（重连后归零）：单调且跳变 <5s 才采信，否则
        # 以"上一时间戳 + 本批时长"外推，保证时间轴连续均匀。
        try:
            t_dev = float(fields[0])
        except (ValueError, IndexError):
            t_dev = None
        batch_dur = len(samples) / ND_SFREQ
        if t_dev is not None:
            last = self._last_t_rel
            if last is not None and (t_dev < last or t_dev - last > 5.0):
                t_dev = last + self._last_batch_dur
            self._last_t_rel = t_dev
            self._last_batch_dur = batch_dur
        elif self._last_t_rel is not None:
            t_dev = self._last_t_rel + self._last_batch_dur
            self._last_t_rel = t_dev
            self._last_batch_dur = batch_dur
        self._feed_buffer(samples, t_dev)
        self.packet_count += 1

    # ── 信号调理：去直流 + 1–40Hz 带通（与 Muse BLE 路径同构） ──────────
    def _ensure_filter(self):
        if self._b is not None:
            return
        from scipy.signal import butter
        nyq = ND_SFREQ / 2.0
        self._b, self._a = butter(2, [1.0 / nyq, 40.0 / nyq], btype="band")

    def _feed_buffer(self, samples, t_rel=None):
        self._ensure_filter()
        from scipy.signal import lfilter, lfilter_zi
        x = np.asarray(samples, dtype=float).T          # (7, n)
        # 去直流
        global_dc = self._dc.copy()
        batch = np.empty_like(x)
        for k in range(x.shape[1]):
            global_dc = global_dc + DC_ALPHA * (x[:, k] - global_dc)
            batch[:, k] = x[:, k] - global_dc
        self._dc = global_dc
        # 带通（逐批增量，滤波器状态跨批复用）
        if self._zi is None:
            zi = np.array([lfilter_zi(self._b, self._a) * v[0] for v in batch])
        else:
            zi = self._zi
        out = np.empty_like(batch)
        for i in range(ND_N_CH):
            out[i], zi_i = lfilter(self._b, self._a, batch[i], zi=zi[i])
            zi[i] = zi_i
        self._zi = zi

        # 平铺送入 buffer：每样本 7 通道 + 1 保留列（stride=8，与设备协议一致）
        # t_rel=设备相对秒：TCP 积压突发到达时保持 250Hz 均匀网格
        flat = []
        for k in range(out.shape[1]):
            flat.extend(float(v) for v in out[:, k])
            flat.append(0.0)
        self.buffer.add_eeg(flat, t_rel=t_rel)

    # ── 看门狗：静默断流处理（对齐 BLE V1.3 行为） ──────────────────────
    def _watchdog_loop(self):
        while not self._stop_event.is_set():
            time.sleep(1.0)
            if not (self._connected.is_set() and self.running):
                continue
            silence = time.time() - self._last_data_time
            if silence > WATCHDOG_SILENCE_SEC:
                if (self._reconnect_attempts < RECONNECT_MAX_ATTEMPTS
                        and not self._reconnecting):
                    self._reconnecting = True
                    self._msg(f"⚠️ 数据流静默 {silence:.0f} 秒，重连中...")
                    self._reconnect_attempts += 1
                    # 踢掉当前会话让 _read_loop 的 recv 超时后返回
                    self._connected.clear()
                    self._reconnecting = False
                    continue
                reason = f"数据流静默 {silence:.0f} 秒（重连未成功）"
                self._msg(f"❌ {reason}，正在自动保存并停止...")
                self.running = False
                self._stop_event.set()
                self._handle_abnormal_disconnect(reason)
                return

    def _handle_abnormal_disconnect(self, reason):
        try:
            self.buffer.save_on_disconnect(reason=reason, app=self.app)
        except Exception as e:
            self._msg(f"断连自动保存失败：{e}")
