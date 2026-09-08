#!/usr/bin/env python3
"""
闭环实验脚本 —— 闭环实验系统第二阶段

完整闭环链路：
  头环蓝牙 → 实时频段特征（每 2 秒）→ 决策层（基线对照+阈值奖励）
            → 实时音频引擎（节拍频率与音量随脑电自动调整）→ 扬声器

实验流程：
  1. 基线期（默认 120 秒）：以极低固定音量播放 10Hz 节拍，
     只采集脑电，建立个人 Alpha 基线
  2. 闭环期（默认 480 秒）：音频音量与节拍频率随实时脑电自动调整
     （Alpha 超过基线→音量升=奖励；回落→淡出）
  3. 收尾：保存原始数据与中文报告，输出决策统计

用法:
    python closedloop_experiment.py --simulate                    # 模拟模式
    python closedloop_experiment.py --address 00:55:DA:BB:E8:D8   # 真机模式
    可选: --baseline 120  --duration 600  --tag closedloop
    其余参数（奖励阈值/音量/节拍范围等）统一在 experiment_config.json 中配置
"""

import os
import sys
import csv
import time
import threading
import argparse
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.join(SCRIPT_DIR, "muse2-repo", "muse2-master")
# 注：muse2-repo 为历史目录名（保留不改）；代码服务于在用设备 Muse S（第 3 代）。
if REPO_DIR not in sys.path:
    sys.path.insert(0, REPO_DIR)

import numpy as np
from muse_local_server import DataBuffer, CHANNELS, SFREQ
from closedloop_engine import IsoEngine
from closedloop_controller import ClosedLoopController
from experiment_config_loader import (load_experiment_config, save_snapshot)

EXP_DIR = os.path.join(SCRIPT_DIR, "experiments")
os.makedirs(EXP_DIR, exist_ok=True)
CONFIG_DEFAULT_PATH = os.path.join(SCRIPT_DIR, "experiment_config.json")


class MinimalApp:
    """最小界面适配器：满足接收器回调，不创建窗口。

    device="neuradock" 时按 NeuraDock 7 通道/250Hz 构造缓冲（V1.4 多设备）；
    缺省与旧行为一致（Muse 4 通道/256Hz）。"""

    def __init__(self, device="muse"):
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
        def config(self, text=""):
            pass

    @property
    def bottom_label(self):
        return self._Lbl()


class SimulateFeeder:
    """模拟数据源：Alpha 振幅缓慢起伏，让闭环控制器有真实反馈可追。"""

    def __init__(self, app):
        self.app = app
        self.running = False
        self._thread = None
        # 与 BleDirectReceiver/MonitorSimulator 接口对齐（2026-09-08 采集台合并）：
        # 前端"数据稳定性条"据 packet_count 递增判断数据流推进，缺则误报静默。
        self.packet_count = 0
        self.battery_percent = None
        self.last_error = None

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
        rng = np.random.default_rng(7)
        t = 0.0
        dt = 1.0 / SFREQ
        while self.running:
            batch = []
            for _ in range(12):
                # Alpha 振幅随时间缓慢起伏（周期约 120 秒）
                alpha_amp = 7.0 + 5.0 * np.sin(2 * np.pi * t / 120.0)
                vals = []
                for ch in range(4):
                    v = alpha_amp * np.sin(2 * np.pi * 10.0 * t + ch) \
                        + 1.5 * np.sin(2 * np.pi * 20.0 * t + ch * 0.7) \
                        + rng.normal(0, 1.5)
                    vals.append(v)
                batch.extend(vals)
                batch.append(0.0)
                t += dt
            self.app.buffer.add_eeg(batch)
            self.packet_count += 1   # 前端稳定条据此判断数据流推进（对齐监测端）
            time.sleep(12.0 / SFREQ)


def inject_config_table(report_path, cfg, snap_name, mode, started,
                        baseline_db=None):
    """把「本次实验配置参数表」注入 HTML 报告，让报告自解释、可复现对照。

    不修改核心库报告生成函数，仅在已生成的报告上注入一个章节。
    返回 True/False 表示是否注入成功。
    """
    if not report_path or not os.path.exists(report_path):
        return False
    exp = cfg["experiment"]
    ctrl = cfg["controller"]
    audio = cfg["audio"]
    dev = cfg["device"]

    def fmt(v):
        if isinstance(v, float):
            return f"{v:g}"
        return str(v)

    rows = [
        ("实验", "实验标签", fmt(exp.get("tag", ""))),
        ("实验", "模式", mode),
        ("实验", "开始时间", f"{started:%Y-%m-%d %H:%M:%S}"),
        ("实验", "总时长",
         f"{exp['duration_seconds']} 秒（基线 {exp['baseline_seconds']} 秒 "
         f"+ 闭环 {exp['duration_seconds'] - exp['baseline_seconds']} 秒）"),
        ("决策", "目标频段", fmt(ctrl.get("target_band", ""))),
        ("决策", "奖励阈值",
         f"Alpha 超基线 {fmt(ctrl.get('reward_threshold_db'))} dB"),
        ("决策", "奖励判定",
         f"音量 > {fmt(ctrl.get('reward_detect_ratio'))} × 最大音量"),
        ("决策", "音量区间",
         f"[{fmt(ctrl.get('vol_idle'))}, {fmt(ctrl.get('vol_max'))}]"
         f"（平滑步长 {fmt(ctrl.get('vol_smooth_step'))}）"),
        ("决策", "节拍频率",
         f"默认 {fmt(ctrl.get('beat_default'))} Hz | 昏沉 {fmt(ctrl.get('beat_drowsy'))}"
         f" | 紧张 {fmt(ctrl.get('beat_tense'))}"),
        ("决策", "节拍区间",
         f"[{fmt(ctrl.get('beat_min'))}, {fmt(ctrl.get('beat_max'))}] Hz，"
         f"步长 {fmt(ctrl.get('beat_step'))}"),
        ("决策", "θ/β 判定",
         f"紧张 > {fmt(ctrl.get('tb_high'))} | 昏沉 < {fmt(ctrl.get('tb_low'))} | "
         f"维持带 {fmt(ctrl.get('maintain_band_db'))} dB"),
        ("音频", "载波频率", f"{fmt(audio.get('carrier_hz'))} Hz"),
        ("设备", "决策间隔", f"{fmt(dev.get('decision_interval_seconds'))} 秒"),
        ("设备", "采样率", f"{fmt(dev.get('sampling_rate'))} Hz"),
        ("实测", "Alpha 基线（本次锁定）",
         f"{baseline_db:.1f} dB" if baseline_db is not None else "-"),
        ("实测", "配置快照文件", snap_name),
    ]
    trs = "".join(f"<tr><td style='text-align:left'>{c}</td>"
                  f"<td style='text-align:left'>{n}</td>"
                  f"<td>{v}</td></tr>" for c, n, v in rows)
    section = (
        '<h2>四、本次实验配置参数（实际生效值）</h2>\n'
        "<table><tr><th>类别</th><th>参数</th><th>取值</th></tr>"
        f"{trs}</table>\n"
    )
    with open(report_path, "r", encoding="utf-8") as f:
        html = f.read()
    anchor = '<p class="note">'
    if anchor in html:
        html = html.replace(anchor, section + anchor, 1)
    elif "</body>" in html:
        html = html.replace("</body>", section + "</body>", 1)
    else:
        return False
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)
    return True


def run_closed_loop(cfg, simulate=True, address=None, callback=None,
                    stop_event=None, session_info=None,
                    adapter="bleak", serial_port=None):
    """执行一次完整闭环实验，返回指标字典（供对比实验汇总）。

    cfg: 已通过校验的配置字典
    callback: 可选，实时事件回调 fn(event_dict)，供控制台界面推流
    stop_event: 可选，threading.Event，置位后提前结束实验（数据仍会保存）
    session_info: 可选，测试者/场景信息字典，写入 npz meta
        （scene=closedloop、participant、pre_state 等）
    返回: {"ok": bool, "tag", "baseline_db", "n_decisions", "reward_pct",
           "mean_vol", "mean_beat", "sampling_hz", "duration_s",
           "report_path", "snap_path", "error", "stopped"}
    """
    def emit(event):
        if callback:
            try:
                callback(event)
            except Exception:
                pass
    exp = cfg["experiment"]
    audio = cfg["audio"]
    decision_dt = cfg["device"]["decision_interval_seconds"]
    reward_ratio = cfg["controller"]["reward_detect_ratio"]
    vol_idle = cfg["controller"]["vol_idle"]
    beat_default = cfg["controller"]["beat_default"]

    if simulate:
        mode = "模拟"
    elif adapter == "bled112":
        mode = f"真机（BLED112 {serial_port or '自动'}）"
    elif adapter == "neuradock":
        mode = f"NeuraDock TCP（{serial_port or '127.0.0.1:9600'}）"
    else:
        mode = "真机蓝牙"
    started = datetime.now()
    ts = started.strftime("%Y%m%d_%H%M%S")
    print("=" * 62)
    print(f"闭环实验 | 模式: {mode} | 基线 {exp['baseline_seconds']} 秒 + "
          f"闭环 {exp['duration_seconds'] - exp['baseline_seconds']} 秒")
    print(f"开始时间: {started:%Y-%m-%d %H:%M:%S} | 标签: {exp['tag']}")
    print(f"奖励阈值: 超基线 {cfg['controller']['reward_threshold_db']}dB | "
          f"音量区间: [{vol_idle}, {cfg['controller']['vol_max']}] | "
          f"节拍区间: [{cfg['controller']['beat_min']}, "
          f"{cfg['controller']['beat_max']}]Hz")
    print("=" * 62)

    # ── 1. 数据源 ─────────────────────────────────────────────────────
    emit({"type": "start", "tag": exp["tag"], "mode": mode,
          "baseline_seconds": exp["baseline_seconds"],
          "duration_seconds": exp["duration_seconds"]})
    app = MinimalApp(device="neuradock" if adapter == "neuradock" else "muse")
    buf = app.buffer
    if simulate:
        receiver = SimulateFeeder(app)
        receiver.start()
    else:
        if adapter == "bled112":
            from ble_receiver import BleBgapiReceiver, detect_bled112_port
            port = serial_port or detect_bled112_port()
            if not port:
                emit({"type": "error", "text":
                      "未检测到 BLED112 适配器（请确认已插入 USB）"})
                return {"ok": False, "error": "未检测到 BLED112 适配器"}
            emit({"type": "message", "text": f"🔌 检测到 BLED112 适配器：{port}"})
            receiver = BleBgapiReceiver(app, address=address, serial_port=port)
        elif adapter == "neuradock":
            from neuradock_receiver import TcpReceiver
            host, _, nd_port = (serial_port or "127.0.0.1:9600").partition(":")
            receiver = TcpReceiver(app, host=host or "127.0.0.1",
                                   port=int(nd_port or 9600))
        else:
            from ble_receiver import BleDirectReceiver
            receiver = BleDirectReceiver(app, address=address)
        # 把蓝牙连接进度/错误透传进事件流（控制台前端可见），
        # 常见英文错误补一句中文说明
        def _relay(text):
            if "not found" in text:
                text += "（未发现头环广播：请确认已开机、指示灯亮，且未连其他设备）"
            elif "timeout" in text.lower():
                text += "（连接超时：请靠近头环后重试）"
            emit({"type": "message", "text": text})
        receiver.on_status = _relay
        receiver.start()
        print("正在连接头环...")
        connect_error = None
        for _ in range(60):
            if receiver.is_connected():
                break
            if receiver.last_error and not receiver.running:
                connect_error = f"连接失败: {receiver.last_error}"
                break
            time.sleep(0.5)
        if connect_error is None and not receiver.is_connected():
            connect_error = "连接超时：30 秒内未连上头环"
        if connect_error:
            # 先停接收器，确保透传消息已入队，再发终结事件保证顺序确定
            receiver.stop()
            emit({"type": "error", "text": connect_error})
            emit({"type": "end", "ok": False, "error": connect_error,
                  "n_decisions": 0, "reward_pct": 0})
            return {"ok": False, "tag": exp["tag"], "error": connect_error}
        emit({"type": "message", "text": "✅ 已连接头环，数据流传输中"})
        print("✅ 已连接，数据流传输中")

    # ── 2. 决策层与音频引擎 ───────────────────────────────────────────
    ctrl = ClosedLoopController.from_config(cfg)
    engine = IsoEngine(volume=0.0, carrier=audio["carrier_hz"],
                       beat=beat_default)
    engine.start()

    feat_path = os.path.join(EXP_DIR, f"{ts}_{exp['tag']}_features.csv")
    dec_path = os.path.join(EXP_DIR, f"{ts}_{exp['tag']}_decisions.csv")
    evt_path = os.path.join(EXP_DIR, f"{ts}_{exp['tag']}_events.csv")
    snap_path = save_snapshot(cfg, EXP_DIR, tag=exp["tag"])

    stopped = False
    stream_error = None
    vitals_warned = False   # N1：体征计算异常首次警告标志（防刷屏，对齐 PSD）

    t0 = time.time()
    n_feat = 0
    n_reward = 0
    n_loop = 0
    baseline_samples = []
    vol_history = []
    beat_history = []
    reward_vol_threshold = reward_ratio * cfg["controller"]["vol_max"]
    print_every = max(1, int(30.0 / decision_dt))

    def log_event(we, text):
        we.writerow([round(time.time() - t0, 1),
                     datetime.now().strftime("%H:%M:%S"), text])

    try:
        with open(feat_path, "w", newline="", encoding="utf-8-sig") as f, \
             open(dec_path, "w", newline="", encoding="utf-8-sig") as d, \
             open(evt_path, "w", newline="", encoding="utf-8-sig") as e:
            wf = csv.writer(f)
            wf.writerow(["时间偏移(秒)", "时间", "阶段", "Delta_dB", "Theta_dB",
                         "Alpha_dB", "Beta_dB", "Gamma_dB", "Theta/Beta比",
                         "大脑状态", "节拍Hz", "指令音量"])
            wd = csv.writer(d)
            wd.writerow(["时间偏移(秒)", "时间", "Alpha_dB", "基线dB", "超基线dB",
                         "节拍Hz", "音量", "决策说明"])
            we = csv.writer(e)
            we.writerow(["时间偏移(秒)", "时间", "事件"])
            log_event(we, f"实验开始({mode})，进入基线期")
            log_event(we, f"配置快照: {os.path.basename(snap_path)}")
            print(f"【基线期】请放松静坐 {exp['baseline_seconds']} 秒，"
                  f"音频以极低音量播放...")

            while time.time() - t0 < exp["duration_seconds"]:
                if stop_event is not None and stop_event.is_set():
                    stopped = True
                    log_event(we, "收到手动停止指令，实验提前结束")
                    emit({"type": "message", "text": "收到手动停止指令"})
                    break
                time.sleep(decision_dt)
                # 真机模式：数据源中途死亡（如静默断连）→ 立即退出并报错，不空转
                if not simulate and not receiver.running and receiver.last_error:
                    stream_error = receiver.last_error
                    log_event(we, f"数据源中断: {stream_error}")
                    emit({"type": "error",
                          "text": f"数据流中断: {stream_error}"})
                    break
                buf.compute_band_power()
                bp = buf.latest_bp
                if not bp:
                    continue
                n_feat += 1
                elapsed = time.time() - t0
                in_baseline = elapsed < exp["baseline_seconds"]

                th, bt = bp.get("theta"), bp.get("beta")
                tb = round(10 ** ((th - bt) / 10.0), 3) \
                    if (th is not None and bt is not None and bt > -100) else None

                if in_baseline:
                    # 基线期：固定低音量，仅累积基线
                    ctrl.add_baseline(bp.get("alpha"))
                    engine.set_volume(vol_idle)
                    engine.set_beat(beat_default)
                    beat, vol = beat_default, vol_idle
                    note = "基线采集"
                    baseline_samples.append(bp.get("alpha"))
                else:
                    if not ctrl.has_baseline:
                        base = ctrl.finalize_baseline()
                        log_event(we, f"基线期结束，Alpha 基线 = {base:.1f} dB，进入闭环期")
                        print(f"\n【闭环期】基线已锁定: Alpha = {base:.1f} dB，"
                              f"闭环控制启动！")
                        emit({"type": "baseline_locked", "baseline_db": base})
                    beat, vol, note = ctrl.update(bp)
                    engine.set_beat(beat)
                    engine.set_volume(vol)
                    if vol > reward_vol_threshold:
                        n_reward += 1
                    n_loop += 1
                    vol_history.append(vol)
                    beat_history.append(beat)

                wf.writerow([round(elapsed, 1), datetime.now().strftime("%H:%M:%S"),
                             "基线" if in_baseline else "闭环",
                             bp.get("delta"), bp.get("theta"), bp.get("alpha"),
                             bp.get("beta"), bp.get("gamma"), tb,
                             buf.latest_state, round(beat, 1), round(vol, 2)])
                f.flush()
                wd.writerow([round(elapsed, 1), datetime.now().strftime("%H:%M:%S"),
                             bp.get("alpha"), ctrl.baseline_db,
                             round((bp.get("alpha") or 0) - (ctrl.baseline_db or 0), 2),
                             round(beat, 1), round(vol, 2), note])
                d.flush()

                # 实时脑电波形（每通道最近 5 秒）+ 全频段能量，与监测采集页一致
                # 采集台合并（2026-09-08）：补齐体征/频谱/脉搏/运动/稳定条字段，
                # 使闭环模式下共用仪表区与监测模式表现一致（此前只有 wave/bands）。
                if n_feat % 4 == 0:      # 体征计算节流，无 PPG 设备静默跳过
                    try:
                        buf.compute_vitals()
                    except Exception as _vit_err:
                        # 无 PPG 设备时 compute_vitals 静默返回不抛错；此处仅
                        # 捕获真异常，首次记录一次警告消除调试盲区（审计建议N1）。
                        if not vitals_warned:
                            vitals_warned = True
                            print(f"[warn] 体征计算异常（不影响脑电主流程）：{_vit_err}")
                wave = {}
                with buf.lock:
                    for ch in buf.channels:
                        seg = list(buf.eeg[ch])[-1280:]
                        wave[ch] = [round(v, 2) for v in seg]
                    ppg = list(buf.ppg_ir)
                    accx, accy, accz = (list(buf.acc_x), list(buf.acc_y),
                                        list(buf.acc_z))
                vitals = buf.get_vitals()

                def _ds(seq, n):
                    if not seq:
                        return []
                    step = max(1, len(seq) // n)
                    return [round(v, 2) for v in seq[::step]][:n]

                emit({"type": "tick", "elapsed": round(elapsed, 1),
                      "phase": "基线" if in_baseline else "闭环",
                      "alpha": bp.get("alpha"), "theta": bp.get("theta"),
                      "beta": bp.get("beta"), "state": buf.latest_state,
                      "beat": round(beat, 1), "vol": round(vol, 2),
                      "note": note,
                      "bands": bp,
                      "wave": wave,
                      "connected": receiver.is_connected(),
                      "packets": getattr(receiver, "packet_count", 0),
                      "battery": getattr(receiver, "battery_percent", None),
                      "psd": buf.latest_psd,
                      "vitals": {k: vitals.get(k) for k in
                                 ("hr", "rmssd", "sdnn", "pnn50", "motion",
                                  "spo2", "tsi", "d_hbo2", "d_hbr",
                                  "optics_ch")},
                      "ppg": _ds(ppg, 120),
                      "motion_xyz": {"x": _ds(accx, 80), "y": _ds(accy, 80),
                                     "z": _ds(accz, 80)}})

                # 每 30 秒打印进度（按决策间隔折算）
                if n_feat % print_every == 0:
                    phase = "基线" if in_baseline else "闭环"
                    print(f"  [{int(elapsed)}s|{phase}] 状态: {buf.latest_state} | "
                          f"Alpha: {bp.get('alpha'):.1f}dB | "
                          f"节拍: {beat:.1f}Hz | 音量: {vol:.2f}")

            log_event(we, "实验结束")
    finally:
        # ── 3. 收尾 ───────────────────────────────────────────────────
        engine.stop()
        print("\n■ 音频引擎已停止")
        receiver.stop()
        print("■ 数据源已停止")

    total = len(buf.eeg_all[buf.channels[0]])
    dur = buf.duration_seconds()
    eff = total / dur if dur > 0 else 0
    print(f"\n── 数据质量摘要 ──")
    print(f"总样本数: {total} | 时长: {dur:.1f} 秒 | "
          f"有效采样率: {eff:.1f} Hz（目标 {buf.sfreq:.0f}）")

    report_path = None
    data_path = None
    exp_meta = {"scene": "closedloop", "experiment_tag": exp["tag"],
                "experiment_mode": mode}
    if session_info:
        exp_meta.update(session_info)
    result = buf.save_bin(extra_meta=exp_meta)
    if result:
        data_path, report_path = result
        print(f"\n✅ 原始数据: {data_path}")
        if report_path:
            ok = inject_config_table(report_path, cfg,
                                     os.path.basename(snap_path), mode, started,
                                     baseline_db=ctrl.baseline_db)
            print(f"✅ 中文报告: {report_path}"
                  + ("（含配置参数表）" if ok else "（配置表注入失败）"))
    print(f"\n特征日志: {feat_path}")
    print(f"决策日志: {dec_path}")
    print(f"事件日志: {evt_path}")
    print(f"配置快照: {snap_path}")
    print("✅ 闭环实验完成")

    if n_loop:
        print(f"\n── 闭环效果统计 ──")
        print(f"决策次数: {n_loop} | 奖励态占比: "
              f"{100.0 * n_reward / max(1, n_loop):.0f}%")

    result = {
        "ok": stream_error is None,
        "tag": exp["tag"],
        "baseline_db": ctrl.baseline_db,
        "n_decisions": n_loop,
        "n_reward": n_reward,
        "reward_pct": 100.0 * n_reward / max(1, n_loop),
        "mean_vol": float(np.mean(vol_history)) if vol_history else None,
        "mean_beat": float(np.mean(beat_history)) if beat_history else None,
        "sampling_hz": eff,
        "duration_s": dur,
        "report_path": report_path,
        "data_path": data_path,
        "snap_path": snap_path,
        "error": stream_error,
        "stopped": stopped,
    }
    emit({"type": "end", **{k: v for k, v in result.items()
                            if k in ("ok", "baseline_db", "n_decisions",
                                     "reward_pct", "mean_vol", "mean_beat",
                                     "duration_s", "report_path", "data_path",
                                     "stopped", "sampling_hz", "error")}})
    return result


def main():
    ap = argparse.ArgumentParser(description="闭环实验")
    ap.add_argument("--address", type=str, default=None)
    ap.add_argument("--simulate", action="store_true")
    ap.add_argument("--baseline", type=int, default=None,
                    help="基线期秒数（默认取配置文件）")
    ap.add_argument("--duration", type=int, default=None,
                    help="实验总时长秒数（默认取配置文件）")
    ap.add_argument("--tag", type=str, default=None,
                    help="实验标签（默认取配置文件）")
    ap.add_argument("--config", type=str, default=None,
                    help="指定配置文件路径（默认 experiment_config.json）")
    ap.add_argument("--adapter", type=str, default="bleak",
                    choices=["bleak", "bled112"],
                    help="蓝牙适配器：bleak=电脑内置蓝牙，bled112=外置 BLED112")
    ap.add_argument("--serial-port", type=str, default=None,
                    help="BLED112 串口号（如 COM3），留空自动检测")
    args = ap.parse_args()

    # ── 加载配置：配置文件为底，命令行参数覆盖 ──
    overrides = {"baseline_seconds": args.baseline,
                 "duration_seconds": args.duration,
                 "tag": args.tag}
    try:
        cfg = load_experiment_config(path=args.config or CONFIG_DEFAULT_PATH,
                                     cli_overrides=overrides)
    except ValueError as ex:
        print(f"❌ {ex}")
        return 1

    res = run_closed_loop(cfg, simulate=args.simulate, address=args.address,
                          adapter=args.adapter, serial_port=args.serial_port)
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
