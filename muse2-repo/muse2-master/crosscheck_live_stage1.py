"""采集层验证 · 第 1 阶段：BrainFlow 直接驱动 Muse 头环实时流.

目标:
    证明 BrainFlow 能在本机 Windows 蓝牙栈上完成"扫描→连接→订阅→实时解码"，
    产出与既有 BleDirectReceiver 同构的数据（256 Hz、4 通道、TP9/AF7/AF8/TP10），
    从而可作为统一控制台采集层的可替换后端（对应看板 D2）。

隐私与数据边界:
    - 全程本机运行，不联网、不上传。
    - 产出文件为**验证性测试数据**，文件名带 crosscheck_ 前缀，
      严禁入库 Zen-EEG，不参与质检登记表。
    - 不改动既有 ble_receiver.py（D18 约定其为基线）。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORT = HERE / "report"

DEVICE_NAME = "MuseS-E8D8"
MAC_ADDRESS = "00:55:DA:BB:E8:D8"
DURATION_SEC = 45          # 采集时长（诊断轮缩短；正式验证轮可改回 75）
EXPECT_SFREQ = 256.0
EXPECT_EEG_NAMES = ["TP9", "AF7", "AF8", "TP10"]


def try_connect(params_builder, label: str):
    """按给定参数尝试建流；失败返回 (None, 错误文本)。"""
    from brainflow.board_shim import BoardIds, BoardShim, BrainFlowInputParams  # noqa: PLC0415

    board_id = BoardIds.MUSE_S_BOARD
    params = params_builder(BrainFlowInputParams())
    print(f"\n[{label}] 使用 BoardIds.MUSE_S_BOARD (id={int(board_id)})")
    print(f"[{label}] 参数: mac_address={params.mac_address!r} "
          f"serial_number={params.serial_number!r}")
    board = BoardShim(board_id, params)
    try:
        t0 = time.time()
        board.prepare_session()
        t_conn = time.time() - t0
        print(f"[{label}] 连接成功，耗时 {t_conn:.2f} 秒")
        return board, board_id, t_conn
    except Exception as exc:                                 # noqa: BLE001
        msg = f"{type(exc).__name__}: {exc}"
        print(f"[{label}] 连接失败 → {msg}")
        try:
            board.release_session()
        except Exception:                                    # noqa: BLE001, S110
            pass
        return None, msg, None


def main() -> int:
    from brainflow.board_shim import BoardShim, BrainFlowInputParams  # noqa: PLC0415
    from brainflow.data_filter import DataFilter              # noqa: PLC0415

    # 文件级调试日志：记录 GATT 订阅与命令写入全过程，用于定位零数据卡点。
    # 控制台仍用 info 级，避免刷屏。
    log_path = str(HERE / "brainflow_dev.log")
    try:
        from brainflow.board_shim import LogLevels          # noqa: PLC0415
        BoardShim.set_log_file(log_path)
        BoardShim.set_log_level(int(LogLevels.LEVEL_TRACE))
        print(f"[调试] BrainFlow trace 级日志 → {log_path}")
    except Exception as exc:                                 # noqa: BLE001
        BoardShim.enable_board_logger()
        print(f"[调试] 文件日志不可用（{exc}），退回控制台 info 级")
    print("=" * 74)
    print("采集层验证 · 阶段1：BrainFlow 驱动 Muse 实时流")
    print(f"设备 {DEVICE_NAME} ({MAC_ADDRESS})   目标时长 {DURATION_SEC} 秒")
    print("=" * 74)

    # 策略 A：按设备名自动发现（WinRT 下对已配对设备更稳）
    # timeout 放宽到 30 秒：BrainFlow 默认仅 6 秒，而本机 WinRT 栈扫描
    # 常慢于 bleak，上一轮即因 6 秒内未发现而 BOARD_NOT_READY_ERROR。
    board, board_id_or_err, t_conn = try_connect(
        lambda p: (setattr(p, "serial_number", DEVICE_NAME),
                   setattr(p, "timeout", 30), p)[-1],
        "A_按名发现_timeout30")

    # 策略 B：按 MAC 直连
    if board is None:
        board, board_id_or_err, t_conn = try_connect(
            lambda p: (setattr(p, "mac_address", MAC_ADDRESS),
                       setattr(p, "timeout", 30), p)[-1],
            "B_按MAC直连_timeout30")

    # 策略 C：不指定标识，让 BrainFlow 自行全量扫描发现第一个 Muse
    if board is None:
        board, board_id_or_err, t_conn = try_connect(
            lambda p: (setattr(p, "timeout", 30), p)[-1],
            "C_全量扫描_timeout30")

    if board is None:
        print("\n" + "=" * 74)
        print("判决：BrainFlow 未能驱动本机 Muse 头环。")
        print(f"两种参数策略均失败，最后一次错误：{board_id_or_err}")
        print("排查方向：Windows 蓝牙栈状态（本机有环境性故障史）、头环是否被")
        print("          手机 App 或其他进程占用、设备配对状态。")
        print("=" * 74)
        return 2

    board_id = board_id_or_err

    # ---- 官方口径核对 ----
    descr = BoardShim.get_board_descr(board_id)
    eeg_ch = BoardShim.get_eeg_channels(board_id)
    sfreq = float(BoardShim.get_sampling_rate(board_id))
    eeg_names = (descr.get("eeg_names") or "").split(",")
    ts_ch = BoardShim.get_timestamp_channel(board_id)

    print("\n--- BrainFlow 官方口径 ---")
    print(f"  采样率      : {sfreq} Hz   (期望 {EXPECT_SFREQ})")
    print(f"  EEG 通道索引: {eeg_ch}")
    print(f"  EEG 通道名  : {eeg_names}   (期望 {EXPECT_EEG_NAMES})")
    print(f"  时间戳通道  : {ts_ch}")

    checks = {
        "sampling_rate_match": sfreq == EXPECT_SFREQ,
        "channel_count_match": len(eeg_ch) == 4,
        "channel_names_match": eeg_names == EXPECT_EEG_NAMES,
    }

    # ---- 实时采集 ----
    print(f"\n开始实时采集 {DURATION_SEC} 秒，请保持闭眼静坐（便于观察 Alpha）...")
    board.start_stream()
    t_start = time.time()
    data = None
    progress_marks = set()
    recovery_tried = False
    try:
        while time.time() - t_start < DURATION_SEC:
            time.sleep(2.0)
            el = int(time.time() - t_start)
            cnt = board.get_board_data_count()
            if el % 10 == 0 and el not in progress_marks:
                progress_marks.add(el)
                print(f"  ...{el} 秒，已缓存 {cnt} 样本/通道")
            # 零数据自动恢复：连接成功但订阅后无流，与本项目 V1.3 修过的
            # 「控制特征握手未生效」同类症状。到 24 秒仍为 0 则显式重发 preset。
            if el >= 24 and cnt == 0 and not recovery_tried:
                recovery_tried = True
                print("  [诊断] 24 秒仍零样本 → 显式重发 Muse preset 'p21'")
                try:
                    resp = board.config_board("p21")
                    print(f"  [诊断] config_board('p21') 返回: {resp!r}")
                except Exception as exc:                     # noqa: BLE001
                    print(f"  [诊断] config_board 失败: {type(exc).__name__}: {exc}")
    finally:
        # 逐步独立守护：上一轮 stop_stream() 抛 BOARD_WRITE_ERROR 时，
        # 后续 release_session() 被跳过，会话可能残留占用头环。
        # 故三步各自 try，确保 release_session 一定被执行。
        wall = time.time() - t_start
        for step_name, step in (("stop_stream", board.stop_stream),
                                ("get_board_data", board.get_board_data),
                                ("release_session", board.release_session)):
            try:
                result = step()
                if step_name == "get_board_data":
                    data = result
            except Exception as exc:                         # noqa: BLE001
                print(f"  [警告] {step_name} 失败: {type(exc).__name__}: {exc}")
                if step_name == "get_board_data":
                    data = None
                elif step_name == "release_session":
                    print("  [警告] 会话未能释放，头环可能被占用；"
                          "下一轮前请关机重启头环。")

    if data is None:
        print("\n判决：未能取回数据数组（get_board_data 失败），本轮验证无效。")
        return 2

    print(f"\n采集结束，释放会话（墙钟 {wall:.2f} 秒）。数据形状: {data.shape}")

    # ---- 结构核验 ----
    ts = data[ts_ch, :]
    eeg = data[eeg_ch, :].T                    # -> (samples, 4)，与既有层同构
    n_samples = int(eeg.shape[0])

    if n_samples == 0:
        print("\n" + "=" * 74)
        print("判决：BrainFlow 连接成功但未取得任何数据样本。")
        print("  已成功环节：BLE 扫描发现设备、建立连接、定位 control characteristic、")
        print("              官方口径（256 Hz / 4 通道 / TP9-AF7-AF8-TP10）读取正确。")
        print("  失败环节：订阅 EEG 数据通道后无样本流入，或握手 preset 未被设备接受。")
        print("  详细日志见 brainflow_dev.log（含 GATT 订阅与命令写入记录）。")
        print("  结论：采集层尚不可用，不得据此认定 BrainFlow 可作控制台后端。")
        print("=" * 74)
        return 2

    dur_dev = (ts[-1] - ts[0]) if len(ts) > 1 else 0.0
    eff_sfreq = (n_samples - 1) / dur_dev if dur_dev > 0 else 0.0
    expected_samples = sfreq * wall
    loss_pct = (1 - n_samples / expected_samples) * 100 if expected_samples else float("nan")

    print("\n--- 实时流实测 ---")
    print(f"  样本数        : {n_samples}")
    print(f"  设备时长      : {dur_dev:.3f} 秒")
    print(f"  实测有效采样率: {eff_sfreq:.3f} Hz   (标称 {sfreq})")
    print(f"  预期样本数    : {expected_samples:.0f}   丢包率约 {loss_pct:.3f}%")
    print(f"  幅值范围 μV   : [{eeg.min():.2f}, {eeg.max():.2f}]")
    print(f"  各通道均值 μV : "
          f"{', '.join(f'{n}={eeg[:,i].mean():.2f}' for i, n in enumerate(eeg_names))}")
    print(f"  各通道标准差  : "
          f"{', '.join(f'{n}={eeg[:,i].std():.2f}' for i, n in enumerate(eeg_names))}")

    checks["stream_nonempty"] = n_samples > 0
    checks["eff_sfreq_within_2pct"] = abs(eff_sfreq - sfreq) / sfreq < 0.02
    checks["loss_under_5pct"] = bool(np.isnan(loss_pct)) or loss_pct < 5.0
    checks["amplitude_plausible_uV"] = bool(
        1.0 < eeg.std() < 500.0)        # 静息 EEG 常见量级
    checks["connect_time_under_20s"] = t_conn < 20.0

    # ---- 保存为验证性测试数据（不入库） ----
    out_npz = REPORT / f"crosscheck_live_brainflow_{time.strftime('%Y%m%d_%H%M%S')}.npz"
    np.savez_compressed(
        out_npz,
        eeg=eeg.astype(np.float64),
        timestamps=ts.astype(np.float64),
        meta=json.dumps({
            "purpose": "VALIDATION_ONLY_NOT_FOR_INGEST",
            "backend": "BrainFlow",
            "board_id": int(board_id),
            "device_name": DEVICE_NAME,
            "mac_address": MAC_ADDRESS,
            "sfreq": sfreq,
            "eeg_names": eeg_names,
            "wall_sec": round(wall, 3),
            "connect_sec": round(t_conn, 3),
            "eff_sfreq": round(float(eff_sfreq), 3),
            "loss_pct": round(float(loss_pct), 4),
            "note": "采集层验证测试数据，严禁入库 Zen-EEG",
        }, ensure_ascii=False),
    )
    print(f"\n已保存验证数据（不入库）: {out_npz.name}")

    print("\n" + "=" * 74)
    print("判决")
    print("=" * 74)
    for k, v in checks.items():
        print(f"  {'[通过]' if v else '[未过]'} {k}")
    all_ok = all(checks.values())
    print(f"\n结论: {'BrainFlow 可驱动本机 Muse 头环实时流，'
          '可作为统一控制台采集层的可替换后端'
          if all_ok else '存在未通过项，详见上表，不可据此认定管道可用'}")

    result = {
        "device_name": DEVICE_NAME, "mac_address": MAC_ADDRESS,
        "board_id": int(board_id), "connect_sec": round(t_conn, 3),
        "wall_sec": round(wall, 3), "n_samples": int(n_samples),
        "sfreq": sfreq, "eff_sfreq": round(float(eff_sfreq), 3),
        "loss_pct": round(float(loss_pct), 4),
        "eeg_names": eeg_names,
        "amplitude_uV": {"min": round(float(eeg.min()), 3),
                         "max": round(float(eeg.max()), 3),
                         "std": round(float(eeg.std()), 3)},
        "per_channel_mean_uV": {n: round(float(eeg[:, i].mean()), 3)
                                for i, n in enumerate(eeg_names)},
        "checks": checks, "all_pass": bool(all_ok),
        "npz": out_npz.name,
    }
    (REPORT / "crosscheck_live_brainflow_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"结果已存: {REPORT / 'crosscheck_live_brainflow_result.json'}")
    return 0 if all_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
