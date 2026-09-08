# -*- coding: utf-8 -*-
"""Zen-EEG 数据工厂入库脚本（02_raw 唯一合法写入入口）。

职责：把 muse-direct 采集端产出的 npz + report.html，按数据字典 V1.1
归档到 Zen-EEG 数据工厂，产出：
  01_registry/session_registry.csv（--sid 预登记匹配模式：把 planned 行更新为
    finished 并回填时长；不带 --sid 的补登记模式：追加新行，先校验 Zen-ID 唯一）
  02_raw/<session_id>/{eeg_raw.npz, report.html, device_info.json, session_note.txt}
  03_quality_control/<session_id>/qc.json

质检隔离区（2026-09-03 新增）：
  03_quality_control/quarantine/<session_id>/ —— 不符合标准的数据不进 02_raw，
  完整落盘到隔离区并在登记表中记 status=quarantined，保留可追溯性，
  可人工复核后另行处理。触发方式：显式 --quarantine，或 --type test
  （链路测试数据默认隔离）。

场景标记（2026-09-03 新增）：采集场景（监测采集 monitor / 闭环实验
closedloop）优先读 npz meta.scene，其次用 --scene 参数，写入
device_info.json 与 session_note.txt（登记表不加场景列，字典仍为 V1.2）。

规则：
- Zen-ID 一经写入永不复用；目标已存在即中止，不覆盖、不拼接。
- --sid 模式下，预登记行必须存在且 status=planned，受试者/日期/类型须与实参一致。
- 02_raw 落盘后只读，本脚本是唯一写入入口，且不修改源文件。
- 历史 npz 缺 timestamps 数组时按线性插值回填，并在日志中注明。

用法示例：
# 预登记匹配模式（SOP V0.2 正式流程：先登记、后采集、再匹配入库）
python ingest_session.py --npz <npz路径> [--report <html路径>] \
    --participant P001 --type baseline --sid ZEN-YYYYMMDD-P001-Snn --operator <你的代号>

# 补登记模式（历史数据补录：自动生成新 Zen-ID）
python ingest_session.py --npz <npz路径> [--report <html路径>] \
    --participant P001 --type test --operator <你的代号> [--note "..."]

# 隔离区模式（不合格数据/链路测试数据，不进 02_raw）
python ingest_session.py --npz <npz路径> --participant P001 --type test \
    --quarantine --operator <你的代号> --note "丢包率过高"
"""

import argparse
import csv
import json
import re
import shutil
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np

ZEN_ROOT = Path(r"C:\Users\tiand\OneDrive\Zen-EEG")
REGISTRY = ZEN_ROOT / "01_registry" / "session_registry.csv"
RAW_ROOT = ZEN_ROOT / "02_raw"
QC_ROOT = ZEN_ROOT / "03_quality_control"
QUARANTINE_ROOT = QC_ROOT / "quarantine"
NOMINAL_SFREQ = 256.0
LOCAL_TZ = timezone(timedelta(hours=8))


def next_session_number(participant_id: str, date_str: str) -> str:
    """返回该受试者在该日期的下一个 S 序号（S01, S02, ...）。"""
    max_n = 0
    with open(REGISTRY, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            sid = row["session_id"]
            if f"-{participant_id}-S" in sid and sid[4:12] == date_str:
                n = int(sid.split("-S")[-1])
                max_n = max(max_n, n)
            elif f"-{participant_id}-" in sid:  # 跨日期也递增 S 序号
                n = int(sid.split("-S")[-1])
                max_n = max(max_n, n)
    return f"S{max_n + 1:02d}"


def extract_report_metrics(html_path: Path):
    """从 report.html 提取噪声段数/干净数据比例（兼容中英文标签）。"""
    metrics = {}
    if html_path is None or not html_path.exists():
        return metrics
    text = html_path.read_text(encoding="utf-8", errors="ignore")
    aliases = {
        "noise_epochs": ("Noise epochs", "噪声段数"),
        "clean_pct": ("Clean data", "干净数据比例"),
    }
    for canon, labels in aliases.items():
        for label in labels:
            m = re.search(
                re.escape(label) + r"</span><br>\s*<span class=\"value\"[^>]*>([^<]+)</span>",
                text,
            )
            if m:
                metrics[canon] = m.group(1).strip()
                break
    return metrics


def main():
    ap = argparse.ArgumentParser(description="Zen-EEG 入库脚本（字典 V1.2 + 隔离区）")
    ap.add_argument("--npz", required=True, help="采集端 npz 原始文件路径")
    ap.add_argument("--report", default=None, help="采集端 report.html 路径")
    ap.add_argument("--participant", required=True, help="受试者匿名编号，如 P001")
    ap.add_argument("--type", required=True,
                    choices=["baseline", "training", "sleep", "custom", "test"],
                    help="会话类型（字典 V1.1）")
    ap.add_argument("--operator", default="tiand", help="操作员代号")
    ap.add_argument("--note", default="", help="补充说明，写入 session_note.txt")
    ap.add_argument("--sid", default=None,
                    help="预登记的 session_id（SOP V0.2 先登记后采集模式）；"
                         "省略则按补登记模式自动生成新 Zen-ID")
    ap.add_argument("--quarantine", action="store_true",
                    help="不合格数据：不进 02_raw，落盘到隔离区并在登记表记 "
                         "quarantined（--type test 默认隔离）")
    ap.add_argument("--scene", default=None, choices=["monitor", "closedloop"],
                    help="采集场景标记（缺省读 npz meta.scene）")
    ap.add_argument("--pre-state", default=None, dest="pre_state",
                    help="事前状态自评（写入 session_note）")
    ap.add_argument("--post-state", default=None, dest="post_state",
                    help="事后状态自评（写入 session_note）")
    ap.add_argument("--contact-quality", default=None, dest="contact_quality",
                    help="接触质量评价（写入 session_note）")
    args = ap.parse_args()

    npz_path = Path(args.npz).resolve()
    report_path = Path(args.report).resolve() if args.report else None

    # ---- 读取源数据（只读，不改源文件） ----
    with np.load(npz_path, allow_pickle=True) as d:
        eeg = d["eeg"]
        meta = d["meta"].item()
        has_ts = "timestamps" in d.files
        timestamps = d["timestamps"] if has_ts else None

    # ---- 场景标记：命令行优先，其次读 npz meta.scene ----
    scene = args.scene or str(meta.get("scene", "")) or "unknown"
    # ---- 隔离判定：显式 --quarantine 或 --type test（链路测试默认隔离） ----
    quarantine = bool(args.quarantine or args.type == "test")

    samples = int(meta["samples"])
    duration = float(meta["duration"])
    if eeg.shape[0] != samples:
        print(f"错误：eeg 行数 {eeg.shape[0]} 与 meta.samples {samples} 不一致，中止。")
        sys.exit(1)

    # ---- 确定 Zen-ID：--sid 预登记匹配模式 或 自动生成模式 ----
    m = re.match(r"local_(\d{8})_", npz_path.name)
    if not m:
        print("错误：npz 文件名不符合 local_YYYYMMDD_HHMMSS.npz，无法推导日期，中止。")
        sys.exit(1)
    date_str = m.group(1)
    date_fmt = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"

    with open(REGISTRY, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    fieldnames = ["session_id", "participant_id", "date", "session_type",
                  "duration_seconds", "status"]

    pre_row = None
    if args.sid:
        session_id = args.sid
        matches = [r for r in rows if r["session_id"] == session_id]
        if not matches:
            print(f"错误：{session_id} 不在登记表。预登记模式要求先登记后采集，中止。")
            sys.exit(1)
        pre_row = matches[0]
        errs = []
        if pre_row["participant_id"] != args.participant:
            errs.append(f"受试者不符（登记 {pre_row['participant_id']} ≠ 实参 {args.participant}）")
        if pre_row["date"] != date_fmt:
            errs.append(f"日期不符（登记 {pre_row['date']} ≠ 文件日期 {date_fmt}）")
        if pre_row["session_type"] != args.type:
            errs.append(f"类型不符（登记 {pre_row['session_type']} ≠ 实参 {args.type}）")
        if pre_row["status"] != "planned":
            errs.append(f"状态为 {pre_row['status']}（应为 planned）")
        if errs:
            print("错误：预登记行校验失败：" + "；".join(errs) + "。中止。")
            sys.exit(1)
    else:
        s_num = next_session_number(args.participant, date_str)
        session_id = f"ZEN-{date_str}-{args.participant}-{s_num}"
        if any(r["session_id"] == session_id for r in rows):
            print(f"错误：{session_id} 已在登记表，Zen-ID 永不复用，中止。")
            sys.exit(1)

    dest_root = QUARANTINE_ROOT if quarantine else RAW_ROOT
    dest = dest_root / session_id
    if dest.exists():
        print(f"错误：{dest} 已存在，{'隔离区' if quarantine else '02_raw'}"
              f"不覆盖，中止。")
        sys.exit(1)

    # ---- 时间戳（字典 V1.2）：统一为 Unix 纪元秒 ----
    # meta.timestamp（本地 ISO 8601）换算为起点纪元秒，用于相对时间戳的换算与缺失回填
    start_local = datetime.fromisoformat(meta["timestamp"])
    start_epoch = start_local.timestamp()
    epoch_normalized = "none"
    if not has_ts:
        # 无时间戳数组：按标称采样率线性回填（纪元秒）
        timestamps = start_epoch + np.arange(samples) / NOMINAL_SFREQ
        backfilled = "linear_interpolation"
    else:
        timestamps = np.asarray(timestamps, dtype=np.float64)
        backfilled = "none"
        if timestamps.size and float(timestamps[0]) < 1e9:
            # 相对时间戳（V1.1 期应用保存的采集端文件）：加起点换算为纪元秒
            timestamps = start_epoch + timestamps
            epoch_normalized = "from_relative"
        # 幂等保护：已是纪元秒的数组原样保留

    # ---- 写 02_raw ----
    dest.mkdir(parents=True, exist_ok=False)
    np.savez(dest / "eeg_raw.npz", eeg=eeg, timestamps=timestamps, meta=meta)
    if report_path and report_path.exists():
        shutil.copy2(report_path, dest / "report.html")

    start_utc = start_local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    device_info = {
        "session_id": session_id,
        "scene": scene,
        # 2026-09-05 更正：本项目设备为 Muse S（第 3 代，蓝牙广播名 MuseS-xxxx）；
        # 当日早些时候曾误改为 Muse 2，经法师确认纠正。
        # V1.4（2026-09-08）：多设备后按 npz meta.device 如实标注型号，
        # 采集端显式 device_model 优先，其次 device 映射，再回退 Muse S。
        "device_model": (str(meta.get("device_model")) if meta.get("device_model")
                         else {"neuradock": "NeuraDock EEG Workstation",
                               "muse": "Muse S"}.get(str(meta.get("device", "")),
                                                     "Muse S")),
        "firmware_version": "",
        "sampling_rate_hz": int(meta["sfreq"]),
        # L1（2026-09-08）：通道数与信号链如实随数据落档，不再写死 4。
        # 旧 npz 无这两字段时回退 v12_bp_1_40（实测讨论稿第八节：历史数据
        # 均经 1–40Hz 因果带通，50Hz 残留，<1Hz 削）与 eeg 实际形状。
        "n_channels": int(eeg.shape[1]),
        "signal_chain": meta.get("signal_chain") or {
            "chain_tag": "v12_bp_1_40", "pre_filter_available": False,
            "note": "旧版采集端未写链标注，按历史实测统一推定（见 2026-09-08 讨论稿第八节）。"},
        "battery_level": "unknown",
        "os_platform": "Windows 11",
        "collection_tool": "muse-direct@2026-09-01",
        "brainflow_version": "",
        "collection_start_utc": start_utc,
        "source_file": npz_path.name,
        "quarantined": quarantine,
    }
    (dest / "device_info.json").write_text(
        json.dumps(device_info, ensure_ascii=False, indent=2), encoding="utf-8")

    def _fb_field(name, value):
        """现场反馈字段：有实参则记录，否则按来源标注待补。"""
        if value:
            return f"{name}: {value}"
        return (f"{name}: unknown（补登记，未当场记录）" if not args.sid
                else f"{name}: unknown（待操作员补记）")

    note_lines = [
        f"session_id: {session_id}",
        f"operator: {args.operator}",
        f"scene: {scene}",
        ("quarantined: true（不合格数据/测试数据，未进入正式研究数据集）"
         if quarantine else "quarantined: false"),
        "environment: 室内；muse-direct 电脑版链路" +
        ("（链路测试）" if args.type == "test" else ""),
        _fb_field("pre_state", args.pre_state),
        _fb_field("contact_quality", args.contact_quality),
        "events: none",
        _fb_field("post_state", args.post_state),
        f"timestamps_backfilled: {backfilled}",
        f"timestamps_epoch_normalized: {epoch_normalized}",
        f"notes: 源文件 {npz_path.name}；"
        + ("链路测试录制，不进入研究数据集，仅保留可追溯性。" if args.type == "test" else "")
        + (args.note or ""),
    ]
    (dest / "session_note.txt").write_text("\n".join(note_lines) + "\n", encoding="utf-8")

    # ---- 写质检记录（正式数据在 03_quality_control，隔离数据在隔离区内） ----
    metrics = extract_report_metrics(report_path)
    eff_rate = samples / duration if duration > 0 else 0.0
    noise = metrics.get("noise_epochs", "")
    clean = metrics.get("clean_pct", "")
    clean_ratio = float(clean.rstrip("%")) / 100.0 if clean else None
    qc = {
        "session_id": session_id,
        "scene": scene,
        "quarantined": quarantine,
        "effective_sample_rate_hz": round(eff_rate, 2),
        "packet_loss_rate": round(1.0 - eff_rate / NOMINAL_SFREQ, 4),
        "noise_epochs": noise,
        "clean_ratio": clean_ratio,
        "channel_quality": {ch: "ok" for ch in meta["channels"]},
        "report_source": "report.html" if report_path else "",
        "generated_by": "ingest_session@2026-09-03",
    }
    qc_dir = dest if quarantine else QC_ROOT / session_id
    if qc_dir != dest:
        qc_dir.mkdir(parents=True, exist_ok=False)
    (qc_dir / "qc.json").write_text(
        json.dumps(qc, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- 更新登记表：隔离数据记 quarantined；--sid 模式回填预登记行 ----
    final_status = "quarantined" if quarantine else "finished"
    if args.sid:
        pre_row["duration_seconds"] = int(round(duration))
        pre_row["status"] = final_status
    else:
        rows.append({
            "session_id": session_id,
            "participant_id": args.participant,
            "date": date_fmt,
            "session_type": args.type,
            "duration_seconds": int(round(duration)),
            "status": final_status,
        })
    with open(REGISTRY, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    dest_label = "隔离区落盘" if quarantine else "入库完成"
    print(f"{dest_label}：{session_id}（{args.type}, {int(round(duration))}s, "
          f"scene={scene}, backfilled={backfilled}, eff={eff_rate:.2f}Hz）"
          + ("，已记入登记表（status=quarantined），未进入 02_raw 正式数据集"
             if quarantine else ""))


if __name__ == "__main__":
    main()
