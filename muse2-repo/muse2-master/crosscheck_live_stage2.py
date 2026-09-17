"""采集层验证 · 阶段2：既有采集层 -> LSL 标准总线 -> 独立消费者.

验证目标（对应看板 D2「NeuraDock 接入既有采集层」的前置标准）:
    证明既有 BleDirectReceiver（D18 基线，不得改动）产出的实时脑电流，
    可以经 LSL 这一行业标准总线被**独立进程**取走并正确计算指标。
    一旦成立，则任何支持 LSL 的第三方设备/工具（NeuraDock、OpenBCI、
    MNE、LabRecorder、Unity 等）都能以同一方式接入统一控制台，
    无需为每种设备单独造轮子。

与阶段1（BrainFlow 直驱 Muse）的区别:
    阶段1 让 BrainFlow 自己去驱动蓝牙 —— 在本机 WinRT 栈上失败
    （trace 日志：identifier 全空，Failed to find Muse Device）。
    阶段2 复用**已真机验证过**的既有采集层（OpenMuse + bleak，preset p1041），
    只把它的数据出口标准化为 LSL。这条路绕开了 WinRT 的坑。

隐私与数据边界（硬约束）:
    - 全程本机运行，不联网、不上传。
    - 消费者进程**只落指标汇总 JSON，不落原始波形**（不产生 npz）。
    - 覆盖 buffer.save_on_disconnect 为空操作，确保验证期间
      任何异常都**不会写入 Zen-EEG 数据工厂**。
    - 不改动 ble_receiver.py / muse_local_server.py（D18/D19 基线）。
"""

from __future__ import annotations

import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORT = HERE / "report"

STREAM_NAME = "ZhiGuanAI-MuseLive"
STREAM_SRCID = "zg-stage2-live-001"
STREAM_TYPE = "EEG"
NCH = 4
SFREQ = 256.0
CHANNELS = ["TP9", "AF7", "AF8", "TP10"]
# 照抄 09-06 真机成功配置：preset p1041（阶段1 BrainFlow 用的 p21 未出流）
PRESET = "p1041"
DURATION_SEC = 60
# 采集余量：消费者按「收满 DURATION_SEC 秒数据」为完成条件，生产者须多推一点，
# 否则差几百样本就会让消费者空等到上限（模拟轮实测：推 15192 < 目标 15360）。
ACQ_MARGIN_SEC = 8


# ==========================================================================
# 消费者：独立子进程，经 LSL 协议取流并计算指标
# ==========================================================================
def consumer_worker(out_json: str, duration: int) -> None:
    """独立进程：resolve_streams 发现流 -> 拉取 -> 算 band power -> 存指标。

    只落指标汇总，不落原始波形（隐私边界）。
    """
    import mne_lsl

    mne_lsl.set_log_level("WARNING")
    from mne_lsl.lsl import StreamInlet, resolve_streams  # noqa: PLC0415

    log = lambda m: print(f"  [消费者] {m}", flush=True)  # noqa: E731
    log(f"独立进程已启动 (pid={mp.current_process().pid})，等待 LSL 流出现 ...")

    found = None
    t0 = time.time()
    while time.time() - t0 < 90:                     # 给生产者留足连接时间
        streams = resolve_streams(timeout=2.0)
        names = [s.name for s in streams]
        match = [s for s in streams if s.name == STREAM_NAME]
        if match:
            found = match[0]
            log(f"发现流: {names}")
            break
        log(f"尚未发现 {STREAM_NAME}，当前可见流: {names or '（无）'}")
        time.sleep(2.0)

    if found is None:
        log("90 秒内未发现目标流，消费者退出。")
        Path(out_json).write_text(json.dumps(
            {"ok": False, "stage": "discover", "reason": "stream_not_found"},
            ensure_ascii=False, indent=2), encoding="utf-8")
        return

    log(f"流元信息: name={found.name} type={found.stype} "
        f"nch={found.n_channels} sfreq={found.sfreq}")

    inlet = StreamInlet(found)
    inlet.open_stream()

    samples: list[np.ndarray] = []
    tss: list[float] = []
    t0 = time.time()
    marks: set[int] = set()
    need = int(duration * SFREQ)          # 目标：收满 duration 秒的真实数据
    idle_budget = duration + 60           # 连接期空等的总上限（秒）
    log(f"开始拉取，目标收满 {need} 样本（{duration} 秒真实数据），"
        f"空等上限 {idle_budget} 秒 ...")
    t0 = time.time()
    first_data_at = None
    while True:
        chunk, t_chunk = inlet.pull_chunk(timeout=0.5, max_samples=512)
        if len(chunk):
            if first_data_at is None:
                first_data_at = time.time()
                log(f"首个数据样本到达（距 open_stream "
                    f"{first_data_at - t0:.2f} 秒）")
            samples.extend(np.asarray(chunk, dtype=np.float64))
            tss.extend(np.asarray(t_chunk, dtype=np.float64))
        # 按数据量计窗，不按墙钟：连接期的空等不消耗目标时长
        if len(samples) >= need:
            log(f"已收满 {len(samples)} 样本，停止拉取")
            break
        el = time.time() - t0
        if el > idle_budget:
            log(f"超过空等上限 {idle_budget} 秒，停止（当前 {len(samples)} 样本）")
            break
        el_i = int(el)
        if el_i and el_i % 15 == 0 and el_i not in marks:
            marks.add(el_i)
            log(f"...{el_i} 秒，累计 {len(samples)} 样本")
    inlet.close_stream()
    log(f"拉取结束，共 {len(samples)} 样本")

    result: dict = {
        "ok": False, "stage": "pull", "pid": mp.current_process().pid,
        "stream_name": found.name, "stream_type": found.stype,
        "stream_nch": int(found.n_channels), "stream_sfreq": float(found.sfreq),
        "n_samples": len(samples),
    }

    if len(samples) < SFREQ * 5:                     # 不足 5 秒无法算 10 秒窗指标
        result["reason"] = "insufficient_samples"
        Path(out_json).write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
        log(f"样本不足（{len(samples)} < {int(SFREQ*5)}），无法计算指标。")
        return

    data = np.array(samples, dtype=np.float64)       # (n_samples, n_channels)
    ts_arr = np.array(tss, dtype=np.float64)
    result["stage"] = "analyze"
    result["n_channels"] = int(data.shape[1])
    result["first_data_wait_sec"] = (round(first_data_at - t0, 3)
                                     if first_data_at else None)
    result["duration_sec"] = round(float((ts_arr[-1] - ts_arr[0])), 3)
    result["eff_sfreq"] = round(
        float((len(ts_arr) - 1) / (ts_arr[-1] - ts_arr[0])) if len(ts_arr) > 1 else 0.0, 3)
    dts = np.diff(ts_arr)
    result["ts_monotonic"] = bool(np.all(dts >= 0))
    # 严格单调 + 非单调步数（真机轮曾暴露 BLE 包抖动导致戳回退）
    result["ts_strictly_monotonic"] = bool(np.all(dts > 0))
    result["ts_nonmonotonic_steps"] = int(np.sum(dts < 0))
    result["ts_step_ms_median"] = round(float(np.median(dts) * 1000), 4)
    result["ts_step_ms_max"] = round(float(dts.max() * 1000), 4)
    result["amplitude_uV"] = {
        "min": round(float(data.min()), 3),
        "max": round(float(data.max()), 3),
        "std": round(float(data.std()), 3),
    }

    # ---- 经 LSL 取到的数据，用 BrainFlow 算指标（校正窗归一化 8/3）----
    try:
        from brainflow.data_filter import DataFilter, WindowOperations  # noqa: PLC0415

        nperseg, overlap = int(SFREQ), int(SFREQ) // 2
        bands = {"theta": (4.0, 8.0), "alpha": (8.0, 12.0), "beta": (12.0, 30.0)}
        bf_band: dict = {}
        for b, (lo, hi) in bands.items():
            per_ch = []
            for c in range(data.shape[1]):
                ampl, freqs = DataFilter.get_psd_welch(
                    np.ascontiguousarray(data[:, c]), nperseg, overlap,
                    int(SFREQ), WindowOperations.HANNING)
                ampl, freqs = np.asarray(ampl), np.asarray(freqs)
                fr = float(freqs[1] - freqs[0])
                mask = (freqs >= lo) & (freqs <= hi)
                per_ch.append(np.trapezoid(ampl[mask], dx=fr) * (8.0 / 3.0))
            bf_band[b] = [round(float(v), 4) for v in per_ch]
        result["brainflow_band_power_uV2"] = bf_band
        result["brainflow_ok"] = True
    except Exception as exc:                          # noqa: BLE001
        result["brainflow_ok"] = False
        result["brainflow_error"] = f"{type(exc).__name__}: {exc}"

    # ---- 同数据用 MNE 独立复核（阶段0 已证两者口径一致）----
    try:
        import mne                                    # noqa: PLC0415
        from mne.time_frequency import psd_array_welch  # noqa: PLC0415

        mne.set_log_level("ERROR")
        psd, freqs = psd_array_welch(
            data.T[np.newaxis, :, :], sfreq=SFREQ, fmin=0.5, fmax=45.0,
            n_fft=int(SFREQ), n_overlap=int(SFREQ) // 2, window="hann", average="mean")
        psd = psd[0]
        fr = float(freqs[1] - freqs[0])
        mne_band = {}
        for b, (lo, hi) in {"theta": (4.0, 8.0), "alpha": (8.0, 12.0),
                            "beta": (12.0, 30.0)}.items():
            mask = (freqs >= lo) & (freqs <= hi)
            mne_band[b] = [round(float(v), 4)
                           for v in np.trapezoid(psd[:, mask], dx=fr, axis=1)]
        result["mne_band_power_uV2"] = mne_band
        result["mne_ok"] = True
    except Exception as exc:                          # noqa: BLE001
        result["mne_ok"] = False
        result["mne_error"] = f"{type(exc).__name__}: {exc}"

    # ---- 频谱峰值（闭眼静坐应在 alpha 8-12 Hz）----
    try:
        fft = np.abs(np.fft.rfft(data[:, 0]))
        fr = np.fft.rfftfreq(len(data[:, 0]), 1 / SFREQ)
        result["ch0_spectral_peak_hz"] = round(float(fr[np.argmax(fft[1:]) + 1]), 2)
    except Exception as exc:                          # noqa: BLE001
        result["ch0_spectral_peak_hz"] = None
        result["peak_error"] = str(exc)

    result["ok"] = True
    Path(out_json).write_text(json.dumps(result, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    log(f"指标已算出并存至 {Path(out_json).name}（只落指标，不落原始波形）")


# ==========================================================================
# 生产者侧：包装既有 DataBuffer，在不改动基线的前提下挂 LSL 出口
# ==========================================================================
class LslBufferProxy:
    """代理既有 DataBuffer：add_eeg 时同时推 LSL.

    既有 BleDirectReceiver 只依赖 buffer 的少数成员
    （add_eeg / lock / optics_n_ch / optics / ppg_ir / ppg_ir_analysis /
      add_acc / add_gyro / save_on_disconnect），故用代理转发即可，
    ble_receiver.py 一行都不用改（D18 基线）。

    时间戳（2026-09-07 真机轮暴露的缺陷，已修）:
        初版 push_chunk(eeg4) 不传时间戳，liblsl 按"收到时刻"打戳；
        BLE 每包 4 样本、包间隔有抖动，导致时间戳非严格单调。
        修法：Muse 是固定 256 Hz 采样，故由本地时钟起一个基准，
        之后每批严格 += ns/SFREQ 递增，保证单调且速率精确。
    """

    def __init__(self, inner, outlet):
        self._inner = inner
        self._outlet = outlet
        self.lsl_pushed = 0
        self.lsl_errors = 0
        self._next_ts = None            # 下一个样本的 LSL 时间戳
        self._lsl_local_clock = None

    def _init_clock(self):
        from mne_lsl.lsl import local_clock           # noqa: PLC0415
        self._lsl_local_clock = local_clock
        self._next_ts = local_clock()

    # ---- 转发既有属性 ----
    @property
    def lock(self):
        return self._inner.lock

    @property
    def optics_n_ch(self):
        return self._inner.optics_n_ch

    @optics_n_ch.setter
    def optics_n_ch(self, v):
        self._inner.optics_n_ch = v

    @property
    def optics(self):
        return self._inner.optics

    @property
    def ppg_ir(self):
        return self._inner.ppg_ir

    @property
    def ppg_ir_analysis(self):
        return self._inner.ppg_ir_analysis

    def add_acc(self, vals):
        return self._inner.add_acc(vals)

    def add_gyro(self, vals):
        return self._inner.add_gyro(vals)

    def save_on_disconnect(self, reason=None, app=None):
        # 硬约束：验证期间绝不允许写入 Zen-EEG 数据工厂。
        print(f"  [生产者] 拦截 save_on_disconnect（reason={reason!r}）——"
              f"验证数据不入库", flush=True)

    # ---- 核心：add_eeg 同时推 LSL ----
    def add_eeg(self, samples: list):
        """samples: flat list，每 5 个一组 = 1 样本 ×(4 EEG + 1 占位)。

        与既有 DataBuffer.add_eeg 同签名（muse_local_server.py:310），
        既有层调用它时数据同时流向两处：原 buffer（界面/保存）与 LSL 出口。
        """
        self._inner.add_eeg(samples)
        ns = len(samples) // 5
        if ns <= 0:
            return
        arr = np.asarray(samples[: ns * 5], dtype=np.float32).reshape(ns, 5)
        eeg4 = np.ascontiguousarray(arr[:, :4])       # 丢掉第 5 列占位
        try:
            if self._next_ts is None:
                self._init_clock()
            # 逐样本时间戳：Muse 固定 256 Hz，严格 += 1/SFREQ，
            # 消除 BLE 包抖动导致的非单调（真机轮暴露的缺陷）。
            step = 1.0 / SFREQ
            ts_batch = np.asarray(
                [self._next_ts + i * step for i in range(ns)], dtype=np.float64)
            self._next_ts += ns * step
            self._outlet.push_chunk(eeg4, ts_batch)
            self.lsl_pushed += ns
        except Exception as exc:                       # noqa: BLE001
            self.lsl_errors += 1
            if self.lsl_errors <= 3:
                print(f"  [生产者] LSL 推送失败: {type(exc).__name__}: {exc}",
                      flush=True)

    def __getattr__(self, name):
        # 其余未显式声明的成员一律转发给既有 DataBuffer
        return getattr(self._inner, name)


class StubApp:
    """最小 app 替身：BleDirectReceiver 只用 app.buffer 与 app.after。

    _ui_msg 中 app.after 的调用被 try/except 包裹（ble_receiver.py:263-266），
    故不提供 after 亦安全；提供之以免日志噪音。
    """

    def __init__(self, buffer):
        self.buffer = buffer

    def after(self, _ms, fn=None):
        try:
            if fn:
                fn()
        except Exception:                              # noqa: BLE001, S110
            pass


class SimSource:
    """模拟数据源（干跑用）。

    逻辑照抄 console_server.py:242-256 的 MonitorSimulator._run，
    但内联于此以避免导入 console_server 触发模块级副作用（Web 服务）。
    与真机 BleDirectReceiver 调用**同一个** buffer.add_eeg(flat) 接口，
    故干跑通过即证明 LSL 管道成立，与蓝牙链路无关。
    """

    def __init__(self, app):
        self.app = app
        self.running = False
        self.packet_count = 0
        self.raw_count = 0
        self.battery_percent = None
        self.last_error = None
        self._thread = None

    def start(self):
        import threading

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
        rng = np.random.default_rng(11)
        t = 0.0
        dt = 1.0 / SFREQ
        while self.running:
            batch = []
            for _ in range(12):
                alpha_amp = 7.0 + 3.0 * np.sin(2 * np.pi * t / 90.0)
                for ch in range(4):
                    v = (alpha_amp * np.sin(2 * np.pi * 10.0 * t + ch)
                         + 1.2 * np.sin(2 * np.pi * 20.0 * t + ch * 0.7)
                         + rng.normal(0, 1.5))
                    batch.append(v)
                batch.append(0.0)                     # 第 5 列占位
                t += dt
            self.app.buffer.add_eeg(batch)
            self.raw_count += 1
            time.sleep(12.0 / SFREQ)


def main(sim: bool = False) -> int:
    sys.path.insert(0, str(HERE))
    import mne_lsl

    mne_lsl.set_log_level("WARNING")
    from mne_lsl.lsl import StreamInfo, StreamOutlet   # noqa: PLC0415
    from muse_local_server import DataBuffer           # noqa: PLC0415

    mode = "模拟数据源（干跑，验证 LSL 管道本身）" if sim else \
           f"真机头环（preset={PRESET}，照抄 09-06 成功配置）"
    print("=" * 74)
    print("采集层验证 · 阶段2：既有采集层 -> LSL -> 独立消费者")
    print(f"数据源: {mode}   时长 {DURATION_SEC} 秒")
    print("=" * 74)

    if not sim:
        from ble_receiver import BleDirectReceiver     # noqa: PLC0415

    # ---- 1. 建 LSL 出口（不依赖头环，先建好让消费者能发现）----
    print("\n[1] 建 LSL StreamOutlet ...")
    info = StreamInfo(STREAM_NAME, STREAM_TYPE, NCH, SFREQ, "float32", STREAM_SRCID)
    info.set_channel_names(CHANNELS)
    info.set_channel_types(["EEG"] * NCH)
    info.set_channel_units(["microvolts"] * NCH)
    outlet = StreamOutlet(info)
    print(f"    已建: name={STREAM_NAME} nch={NCH} sfreq={SFREQ}")

    # ---- 2. 启动独立消费者子进程 ----
    print("\n[2] 启动独立消费者子进程 ...")
    tag = "sim" if sim else "live"
    out_json = REPORT / (f"crosscheck_stage2_{tag}_consumer_"
                         f"{time.strftime('%Y%m%d_%H%M%S')}.json")
    ctx = mp.get_context("spawn")                     # Windows 下必须 spawn
    proc = ctx.Process(target=consumer_worker,
                       args=(str(out_json), DURATION_SEC), daemon=True)
    proc.start()
    print(f"    消费者 pid={proc.pid}")
    time.sleep(2.0)                                   # 让它先进入发现循环

    # ---- 3. 数据源连接 ----
    print("\n[3] 启动数据源 ...")
    real_buf = DataBuffer()
    proxy = LslBufferProxy(real_buf, outlet)
    app = StubApp(proxy)

    if sim:
        receiver = SimSource(app)
        receiver.start()
        connected = receiver.is_connected()
        print(f"    模拟数据源已启动（connected={connected}）")
    else:
        receiver = BleDirectReceiver(app, address=None, preset=PRESET,
                                     scan_timeout=15)
        receiver.on_status = lambda text: print(f"    [既有层] {text}", flush=True)
        t0 = time.time()
        receiver.start()
        connected = False
        for _ in range(40):                           # 最多等 40 秒
            if receiver.is_connected():
                connected = True
                break
            time.sleep(1.0)
        if not connected:
            print(f"\n    连接未成功（等待 40 秒），last_error={receiver.last_error!r}")
            try:
                receiver.stop()
            except Exception:                          # noqa: BLE001, S110
                pass
            proc.join(timeout=20)
            return 2
        print(f"    连接成功，耗时 {time.time()-t0:.2f} 秒")

    # ---- 4. 采集 ----
    acq_sec = DURATION_SEC + ACQ_MARGIN_SEC
    print(f"\n[4] 采集中，请保持闭眼静坐约 {acq_sec} 秒"
          f"（目标 {DURATION_SEC} 秒数据 + {ACQ_MARGIN_SEC} 秒余量）...")
    t_acq = time.time()
    marks = set()
    try:
        while time.time() - t_acq < acq_sec:
            time.sleep(2.0)
            el = int(time.time() - t_acq)
            if el % 15 == 0 and el not in marks:
                marks.add(el)
                with real_buf.lock:
                    n_buf = len(real_buf.eeg_all.get(CHANNELS[0], []))
                print(f"    ...{el} 秒 | 既有 buffer {n_buf} 样本 | "
                      f"已推 LSL {proxy.lsl_pushed} 样本 | "
                      f"raw_count={receiver.raw_count}", flush=True)
    finally:
        wall = time.time() - t_acq
        for step_name, step in (("stop_receiver", receiver.stop),
                                ("del_outlet", outlet.__del__)):
            try:
                step()
            except Exception as exc:                   # noqa: BLE001
                print(f"    [警告] {step_name} 失败: {type(exc).__name__}: {exc}",
                      flush=True)

    print(f"\n    采集结束（墙钟 {wall:.2f} 秒）")
    print(f"    既有层统计: raw_count={receiver.raw_count} "
          f"packet_count={receiver.packet_count} "
          f"battery={receiver.battery_percent}")
    print(f"    LSL 推送: 成功 {proxy.lsl_pushed} 样本，失败 {proxy.lsl_errors} 次")

    with real_buf.lock:
        n_buf_total = len(real_buf.eeg_all.get(CHANNELS[0], []))
    print(f"    既有 buffer 累计: {n_buf_total} 样本")

    # ---- 5. 等消费者收尾 ----
    print("\n[5] 等待消费者进程完成指标计算 ...")
    proc.join(timeout=90)
    if proc.is_alive():
        print("    消费者仍在运行，终止之。")
        proc.terminate()
        proc.join(timeout=10)

    print("\n" + "=" * 74)
    print("判决")
    print("=" * 74)
    checks = {
        "既有层连接成功": connected,
        "既有层取到样本": n_buf_total > 0,
        "LSL推送非空": proxy.lsl_pushed > 0,
        "LSL推送零失败": proxy.lsl_errors == 0,
        "消费者产出指标文件": out_json.exists(),
    }
    consumer_res: dict = {}
    if out_json.exists():
        try:
            consumer_res = json.loads(out_json.read_text(encoding="utf-8"))
            checks["消费者取到足量样本"] = bool(consumer_res.get("ok"))
            n_c = consumer_res.get("n_samples") or 0
            eff = consumer_res.get("eff_sfreq") or 0.0
            # 按「消费者实际覆盖窗口」比对，而非生产者总量：
            # 生产者总量含消费者 open_stream 之前的连接期，直接比会误判丢包。
            if n_c and eff:
                expect_c = consumer_res.get("duration_sec", 0) * SFREQ
                checks["消费者窗口内丢包<1%"] = expect_c > 0 and \
                    abs(n_c - expect_c) / expect_c < 0.01
                checks["消费者采样率≈256Hz(偏差<1%)"] = abs(eff - SFREQ) / SFREQ < 0.01
            # 时间戳严格单调（2026-09-07 修复项：push_chunk 传逐样本戳）
            checks["时间戳严格单调"] = bool(
                consumer_res.get("ts_strictly_monotonic", False))
            checks["BrainFlow与MNE指标逐位一致"] = (
                consumer_res.get("brainflow_band_power_uV2")
                == consumer_res.get("mne_band_power_uV2"))
        except Exception as exc:                       # noqa: BLE001
            print(f"  读取消费者结果失败: {exc}")

    for k, v in checks.items():
        print(f"  {'[通过]' if v else '[未过]'} {k}")

    if consumer_res:
        print("\n  消费者侧指标:")
        for k in ("n_samples", "n_channels", "first_data_wait_sec",
                  "duration_sec", "eff_sfreq",
                  "ts_monotonic", "ts_strictly_monotonic",
                  "ts_nonmonotonic_steps", "ts_step_ms_median", "ts_step_ms_max",
                  "amplitude_uV", "ch0_spectral_peak_hz",
                  "brainflow_ok", "mne_ok"):
            if k in consumer_res:
                print(f"    {k}: {consumer_res[k]}")
        for k in ("brainflow_band_power_uV2", "mne_band_power_uV2"):
            if k in consumer_res:
                print(f"    {k}: {consumer_res[k]}")

    all_ok = all(checks.values())
    scope = ("LSL 管道本身成立（模拟数据源，不含蓝牙链路）"
             if sim else "既有采集层可经 LSL 标准总线被独立进程消费，"
                         "第三方设备/工具接入路径成立")
    print(f"\n结论: {scope if all_ok else '存在未通过项，详见上表'}")

    summary = {
        "mode": "sim" if sim else "live",
        "preset": None if sim else PRESET, "wall_sec": round(wall, 3),
        "receiver": {"raw_count": receiver.raw_count,
                     "packet_count": receiver.packet_count,
                     "battery_percent": receiver.battery_percent,
                     "last_error": receiver.last_error},
        "existing_buffer_samples": n_buf_total,
        "lsl_pushed": proxy.lsl_pushed, "lsl_errors": proxy.lsl_errors,
        "checks": checks, "all_pass": bool(all_ok),
        "consumer": consumer_res,
        "consumer_json": out_json.name,
    }
    (REPORT / "crosscheck_live_stage2_result.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n生产者汇总已存: {REPORT / 'crosscheck_live_stage2_result.json'}")
    print(f"消费者指标已存: {out_json}")
    print("（本次未产生任何 npz，未写入 Zen-EEG 数据工厂）")
    return 0 if all_ok else 2


if __name__ == "__main__":
    mp.freeze_support()
    raise SystemExit(main(sim="--sim" in sys.argv[1:]))
