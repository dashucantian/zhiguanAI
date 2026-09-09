"""NeuraDock 模拟器 —— 无需真机即可联调采集台/VR/质检全链路。

为什么需要它：NeuraDock 官方软件"打开数据服务"按钮绑定真机连接状态、
**全程序无模拟模式**（见日志 009 §2.2，反汇编 HomePageKt 证实）。厂商仓库
自带的 mock_neuradock_server.mjs 只推固定 10Hz 正弦（幅值 12+ch µV），
够测协议格式、不够测**生理语义**（状态分类、Alpha 阻滞、质量门控、FFT 峰）。
本模拟器按官方 TCP 协议逐字段复刻，但生成**生理可信、可注入伪迹**的脑电，
填补"无真机时验证下游分析与界面"的空缺。

协议（与 neuradock_receiver.py 对齐，定版自官方 eeg-workstation-agent）：
  - TCP 服务器，默认 127.0.0.1:9600；客户端连上后须先发 "start" 才推流；
  - 每行 CSV：timestamp(相对秒), marker, 然后 (7 EEG µV + 1 保留) × 组数；
      USB 模式 10 字段（1 组/行，无打包延迟）；蓝牙模式 42 字段（5 组/行）；
  - 通道定版：0=CP5 1=CP6 2=PO3 3=PO4 4=O1 5=Oz 6=O2，250Hz，µV；
  - 一行可能被拆成多次 TCP 写（官方 mock 故意如此），本模拟器也偶发拆行，
    以测试接收端的行缓冲。

生理建模（枕顶区 7 干电极，对应禅修监测）：
  - Alpha(8–13Hz)：枕区 O1/Oz/O2 最强；闭眼放松↑、睁眼/专注↓（Alpha 阻滞）；
  - Theta(4–8Hz)：顶中线 CP5/CP6 偏强；昏沉/浅睡↑；
  - Beta(13–30Hz)：前额/紧张↑；专注时中度；
  - 各状态按比例混合频段 + 1/f 背景 + 通道相关噪声，幅值落到真实 µV 量级。

可注入伪迹（测质量门控横幅 / 头位图 / FFT 工频）：
  --artifact blink   周期性眼动伪迹（大幅低频，前部通道）
  --artifact emg     肌电（高频宽带，beta/gamma 抬升）
  --artifact mains   50Hz 工频（FFT 上现尖峰）
  --artifact drift   基线漂移（<1Hz 慢波，测高通）
  --artifact flat    某通道悬空（峰峰值≈0，测"差"质量判定）

用法：
  python neuradock_simulator.py                      # 默认 9600/蓝牙/状态自动轮转
  python neuradock_simulator.py --port 9600 --transport usb
  python neuradock_simulator.py --state relax --artifact mains,blink
  python neuradock_simulator.py --duration 60        # 60 秒后自动停
仅监听本机回环，不外发；不写任何数据文件。
"""
import argparse
import socket
import threading
import time

import numpy as np

# ── 设备档案（与 neuradock_receiver.py 一致） ────────────────────────────
ND_CHANNELS = ["CP5", "CP6", "PO3", "PO4", "O1", "Oz", "O2"]
ND_SFREQ = 250.0
ND_N_CH = 7
_START_CMD = b"start"

# 各通道在枕顶区蒙太奇下的频段权重（经验布局，体现区域差异）
# 顺序 = ND_CHANNELS；值 = 该频段在此通道的相对强度
_W_ALPHA = np.array([0.4, 0.4, 0.7, 0.7, 1.0, 1.0, 1.0])   # 枕区 O1/Oz/O2 最强
_W_THETA = np.array([1.0, 1.0, 0.7, 0.7, 0.5, 0.6, 0.5])   # 顶中线 CP5/CP6 偏强
_W_BETA  = np.array([0.8, 0.8, 0.6, 0.6, 0.5, 0.5, 0.5])   # 偏前/颞

# 脑状态 → 各频段目标功率（µV²，对数正态量级，落到真实干电极幅值）
# 数值经缩放使枕区 Alpha 峰约 8–20µV，符合静坐闭眼实测
_STATES = {
    #          alpha  theta  beta   说明
    "relax":   (1.00, 0.35, 0.25),  # 闭眼放松：Alpha 主导
    "focus":   (0.35, 0.30, 0.90),  # 睁眼专注：Alpha 阻滞、Beta 抬升
    "drowsy":  (0.55, 1.00, 0.20),  # 昏沉欲睡：Theta 主导
    "meditate":(0.80, 0.60, 0.20),  # 禅定：Alpha+Theta 俱高、Beta 低
}
_STATE_CYCLE = ["relax", "focus", "drowsy", "meditate"]


class EegSynth:
    """生理可信的多通道 EEG 合成器（按状态混合频段 + 1/f 背景 + 伪迹）。"""

    def __init__(self, sfreq=ND_SFREQ, seed=7):
        self.sfreq = sfreq
        self.rng = np.random.default_rng(seed)
        self.t = 0.0                       # 设备相对时钟（秒）
        self._phase = {}                   # 各频段相位，保证连续
        self._drift = np.zeros(ND_N_CH)    # 基线漂移状态
        self._flat_ch = None               # 悬空通道索引（artifact=flat）

    def _osc(self, key, freq, amp, weight, ch_noise):
        """生成一组通道的正弦振荡（相位连续），amp 为峰值 µV。

        key：稳定的相位字典键（不可用 freq 本身——alpha 峰频每样本漂移，
        若以 freq 为键则相位每样本重启、被搅成宽带噪声，主峰错落到固定频的
        theta/beta。freq 仅用于推进本样本相位增量。）
        """
        ph = self._phase.get(key)
        if ph is None:
            ph = self.rng.uniform(0, 2 * np.pi, ND_N_CH)
        ph = ph + 2 * np.pi * freq / self.sfreq
        self._phase[key] = ph
        return amp * weight * np.sin(ph) + ch_noise

    def synth(self, state, artifacts, n):
        """生成 n 个样本（7 通道），返回 (7, n) µV 数组。"""
        a_w, t_w, b_w = _STATES.get(state, _STATES["relax"])
        out = np.zeros((ND_N_CH, n))
        for k in range(n):
            self.t += 1.0 / self.sfreq
            # Alpha 峰频在 9–11Hz 缓慢起伏（个体/状态差异）；用固定键 "a" 存相位
            a_peak = 10.0 + 0.8 * np.sin(2 * np.pi * self.t / 40.0)
            noise = self.rng.normal(0, 1.0, ND_N_CH)   # 1/f 背景近似
            v = np.zeros(ND_N_CH)
            v += self._osc("a", a_peak, 12.0 * a_w, _W_ALPHA, noise * 0.6)
            v += self._osc("t", 6.0, 8.0 * t_w, _W_THETA, noise * 0.4)
            v += self._osc("b", 20.0, 5.0 * b_w, _W_BETA, noise * 0.5)
            v += noise * 1.5                            # 宽带本底
            out[:, k] = v

        # ── 伪迹注入 ──
        if "drift" in artifacts:
            # <1Hz 慢漂移（测高通/去直流）：随机游走 + 0.3Hz 正弦，幅度 ~15µV
            self._drift = self._drift * 0.999 + self.rng.normal(0, 0.4, ND_N_CH)
            tt = self.t - np.arange(n)[::-1] / self.sfreq
            wave = 15.0 * np.sin(2 * np.pi * 0.3 * tt)        # (n,)
            out += self._drift[:, None] + wave[None, :]
        if "mains" in artifacts:
            # 50Hz 工频（FFT 上现尖峰，约 +20dB）
            tt = self.t - np.arange(n)[::-1] / self.sfreq
            out += 8.0 * np.sin(2 * np.pi * 50.0 * tt)[None, :]
        if "emg" in artifacts:
            # 肌电：高频宽带（抬 beta/gamma）
            out += self.rng.normal(0, 6.0, (ND_N_CH, n))
        if "blink" in artifacts:
            # 周期性眼动：每 ~4 秒一次大幅低频脉冲，前部通道(CP/PO)更明显
            for k in range(n):
                tk = self.t - (n - 1 - k) / self.sfreq
                if (tk % 4.0) < 0.25:
                    env = np.sin(np.pi * (tk % 4.0) / 0.25)
                    prof = np.array([1.0, 1.0, 0.8, 0.8, 0.4, 0.3, 0.4])
                    out[:, k] += env * 60.0 * prof
        if "flat" in artifacts:
            # 通道悬空：O2(索引6) 峰峰值压到≈0，测"差"质量判定
            if self._flat_ch is None:
                self._flat_ch = 6
            out[self._flat_ch, :] = self.rng.normal(0, 0.3, n)
        return out


def _format_lines(samples, transport, t0, start_idx, rng, fragment_prob=0.15):
    """把 (7, n) 样本数组格式化为协议 CSV 行列表。

    transport='usb'：每行 1 样本（10 字段）；'bluetooth'：每行 5 样本（42 字段）。
    返回 [(line_bytes, split:bool), ...]，split=True 表示该行要拆成两次发送。
    """
    n = samples.shape[1]
    per_line = 1 if transport == "usb" else 5
    lines = []
    idx = start_idx
    for s0 in range(0, n - per_line + 1, per_line):
        fields = []
        ts = t0 + idx / ND_SFREQ
        fields.append(f"{ts:.6f}")
        fields.append("0")                       # marker
        for g in range(per_line):
            col = s0 + g
            for c in range(ND_N_CH):
                fields.append(f"{samples[c, col]:.8f}")
            fields.append("0")                   # 保留列
        line = ",".join(fields) + "\n"
        split = rng.random() < fragment_prob     # 偶发拆行，测接收端行缓冲
        lines.append((line.encode("utf-8"), split))
        idx += per_line
    return lines, idx


def _handle_client(conn, addr, args, rng):
    """处理单个客户端：等 'start' 握手 → 按实时配速推流。"""
    print(f"[sim] 客户端连接 {addr}，等待 'start' 握手…")
    conn.settimeout(5.0)
    # 1. 等握手
    got_start = False
    buf = b""
    deadline = time.time() + 10.0
    while time.time() < deadline:
        try:
            chunk = conn.recv(64)
        except socket.timeout:
            continue
        except OSError:
            return
        if not chunk:
            return
        buf += chunk
        if _START_CMD in buf:
            got_start = True
            break
    if not got_start:
        print("[sim] 未收到 'start'，关闭连接")
        return
    print(f"[sim] 收到 'start'，开始推流（{args.transport} 模式，"
          f"{ND_SFREQ:.0f}Hz × {ND_N_CH}ch，状态={args.state}）")

    # 2. 实时推流
    synth = EegSynth(seed=args.seed)
    artifacts = set(a.strip() for a in args.artifact.split(",") if a.strip())
    if artifacts:
        print(f"[sim] 注入伪迹：{sorted(artifacts)}")
    conn.settimeout(None)
    samples_per_line = 1 if args.transport == "usb" else 5
    # 每次生成一个推流批（蓝牙 5 样本/行 × 多行；USB 1 样本/行 × 多行）
    batch_lines = 5                              # 每批 5 行
    batch_samples = samples_per_line * batch_lines
    interval = batch_samples / ND_SFREQ          # 实时配速
    t_start = time.time()
    idx = 0                                      # 累计样本索引（设备时钟基准）
    state = args.state
    state_t0 = time.time()
    n_sent = 0
    try:
        while True:
            if args.duration and (time.time() - t_start) >= args.duration:
                print(f"[sim] 达到时长 {args.duration}s，停止推流")
                break
            # 状态轮转（--state cycle 时按 args.state_period 秒切换）
            if args.state == "cycle" and \
                    (time.time() - state_t0) >= args.state_period:
                state_t0 = time.time()
                cur = _STATE_CYCLE.index(state) if state in _STATE_CYCLE else -1
                state = _STATE_CYCLE[(cur + 1) % len(_STATE_CYCLE)]
                print(f"[sim] 状态切换 → {state}")
            cur_state = state if state != "cycle" else "relax"

            samples = synth.synth(cur_state, artifacts, batch_samples)
            t0 = synth.t - batch_samples / ND_SFREQ
            lines, idx = _format_lines(samples, args.transport,
                                       t0, idx, rng)
            for line_bytes, split in lines:
                if split and len(line_bytes) > 8:
                    mid = len(line_bytes) // 2
                    conn.sendall(line_bytes[:mid])
                    conn.sendall(line_bytes[mid:])   # 故意拆成两次 TCP 写
                else:
                    conn.sendall(line_bytes)
                n_sent += 1
            # 实时配速：睡到该批应结束的时刻
            target = t_start + idx / ND_SFREQ
            slack = target - time.time()
            if slack > 0:
                time.sleep(slack)
    except (BrokenPipeError, ConnectionResetError, OSError) as e:
        print(f"[sim] 客户端断开：{e}")
    finally:
        print(f"[sim] 连接关闭，共推送 {n_sent} 行")
        try:
            conn.close()
        except OSError:
            pass


def main():
    ap = argparse.ArgumentParser(
        description="NeuraDock TCP 数据服务模拟器（生理可信脑电 + 伪迹注入）")
    ap.add_argument("--host", default="127.0.0.1", help="监听地址（默认本机回环）")
    ap.add_argument("--port", type=int, default=9600, help="监听端口（默认 9600）")
    ap.add_argument("--transport", choices=["usb", "bluetooth"], default="bluetooth",
                    help="行格式：usb=10字段/行，bluetooth=42字段/行（默认蓝牙）")
    ap.add_argument("--state", default="cycle",
                    choices=list(_STATES.keys()) + ["cycle"],
                    help="脑状态：relax/focus/drowsy/meditate，或 cycle 自动轮转")
    ap.add_argument("--state-period", type=float, default=20.0,
                    help="cycle 模式下每个状态持续秒数（默认 20）")
    ap.add_argument("--artifact", default="",
                    help="注入伪迹，逗号分隔：blink,emg,mains,drift,flat")
    ap.add_argument("--duration", type=float, default=0,
                    help="推流总秒数，0=不限（Ctrl+C 停）")
    ap.add_argument("--seed", type=int, default=7, help="随机种子（可复现）")
    ap.add_argument("--single", action="store_true",
                    help="只服务一个客户端后退出（默认持续接受新连接）")
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed + 1)
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind((args.host, args.port))
    except OSError as e:
        print(f"[sim] 端口 {args.host}:{args.port} 绑定失败：{e}")
        print("      （NeuraDock 真软件可能已占用 9600；改 --port 或关闭真软件）")
        return 1
    srv.listen(5)
    print("=" * 60)
    print("NeuraDock 模拟器已启动（无需真机）")
    print(f"  监听：{args.host}:{args.port}  传输：{args.transport} 模式")
    print(f"  通道：{','.join(ND_CHANNELS)} @ {ND_SFREQ:.0f}Hz µV")
    print(f"  状态：{args.state}"
          + (f"（每 {args.state_period}s 轮转）" if args.state == "cycle" else ""))
    if args.artifact:
        print(f"  伪迹：{args.artifact}")
    print("  在控制台数据源选「NeuraDock（TCP 数据服务）」、地址填上面监听值即可联调")
    print("  按 Ctrl+C 停止")
    print("=" * 60)
    try:
        while True:
            conn, addr = srv.accept()
            if args.single:
                _handle_client(conn, addr, args, rng)
                break
            # 多客户端：每个连接一个线程（NeuraDock 软件支持 1 对多）
            threading.Thread(target=_handle_client, args=(conn, addr, args, rng),
                             daemon=True).start()
    except KeyboardInterrupt:
        print("\n[sim] 收到 Ctrl+C，停止")
    finally:
        srv.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
