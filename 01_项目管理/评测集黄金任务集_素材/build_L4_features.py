# -*- coding: utf-8 -*-
"""
评测集 L4-02b 素材生产 · 第二步：提取真实 session 频段统计特征
================================================================
法师 2026-09-11 授权（D24 / §9.6）：授权从真实 session 提取频段统计特征。

严格纪律：
  1. 02_raw 为只读区（《数据字典 V1.2》§3.1 末）——本脚本只 np.load 读取，
     绝不写入、绝不修改 Zen-EEG 下任何文件。
  2. 06_features 在字段清单定义前"只允许存放人工文档，不允许存放未定义结构的
     数据文件"（字典 §4 末注）——故输出**不得**写入 06_features，
     改存评测集自有素材目录。
  3. 只输出**统计特征**（频段功率、比值、振幅统计），**绝不输出原始波形样本**、
     不输出逐样本时间戳。原始数据不出本目录。
  4. 全程本机，产物仅供轨道 B（本地评）使用，**不得发送给任何线上模型**。

频段口径：照抄项目既有定义（analyze_recording.py:18-26），不自创
  BANDS = Delta(0.5-4) Theta(4-8) Alpha(8-12) Beta(12-30) Gamma(30-45)
  CHANNELS = ['TP9','AF7','AF8','TP10']，SFREQ = 256.0
  PSD: scipy.signal.welch, nperseg = int(sfreq*2) = 512
"""
import numpy as np
from scipy.signal import welch
import glob
import os
import json
import csv

BASE = r"D:\Project\Zen-EEG"  # 2026-09-19 数据工厂随项目迁 D 盘（原 C:\...\OneDrive\Zen-EEG）
OUT_DIR = os.path.dirname(os.path.abspath(__file__))

BANDS = {
    "Delta": (0.5, 4),
    "Theta": (4, 8),
    "Alpha": (8, 12),
    "Beta": (12, 30),
    "Gamma": (30, 45),
}
CHANNELS = ["TP9", "AF7", "AF8", "TP10"]
SFREQ = 256.0


def band_power(data, sfreq):
    """照抄 analyze_recording.py:29-48 的口径，返回各通道绝对/相对功率。"""
    nperseg = int(sfreq * 2)
    freqs, psd = welch(data, sfreq, nperseg=nperseg, axis=0)
    abs_p = {}
    total = np.zeros(data.shape[1])
    for band, (lo, hi) in BANDS.items():
        mask = (freqs >= lo) & (freqs <= hi)
        bp = np.trapezoid(psd[mask], freqs[mask], axis=0)
        abs_p[band] = bp
        total += bp
    rel_p = {b: abs_p[b] / total for b in BANDS}
    return abs_p, rel_p, total


# 读登记表，拿 session_type 与 status
registry = {}
reg_path = os.path.join(BASE, "01_registry", "session_registry.csv")
# utf-8-sig：该 csv 带 BOM，用 utf-8 读会使首列名变成 '\ufeffsession_id'
with open(reg_path, "r", encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    if reader.fieldnames is None or "session_id" not in reader.fieldnames:
        raise SystemExit("登记表列名异常，实际为: %s" % (reader.fieldnames,))
    for row in reader:
        registry[row["session_id"]] = row

paths = sorted(glob.glob(os.path.join(BASE, "02_raw", "*", "eeg_raw.npz")))
paths += sorted(glob.glob(os.path.join(
    BASE, "03_quality_control", "quarantine", "*", "eeg_raw.npz")))

results = []
for p in paths:
    sid = os.path.basename(os.path.dirname(p))
    loc = "quarantine" if "quarantine" in p else "02_raw"
    z = np.load(p, allow_pickle=True)
    eeg = z["eeg"]
    meta = z["meta"].item()

    n, nch = eeg.shape
    dur = float(meta.get("duration") or 0)
    abs_p, rel_p, total = band_power(eeg, SFREQ)

    # 跨通道均值（4 通道平均），保留两位小数
    rel_mean = {b: round(float(np.mean(rel_p[b])), 4) for b in BANDS}
    abs_mean = {b: round(float(np.mean(abs_p[b])), 3) for b in BANDS}

    # 常用比值指标
    alpha_mean = float(np.mean(rel_p["Alpha"]))
    theta_mean = float(np.mean(rel_p["Theta"]))
    beta_mean = float(np.mean(rel_p["Beta"]))
    delta_mean = float(np.mean(rel_p["Delta"]))

    def safe_div(a, b):
        return round(a / b, 3) if b > 0 else None

    rec = {
        "session_id": sid,
        "location": loc,
        "session_type": registry.get(sid, {}).get("session_type", "?"),
        "registry_status": registry.get(sid, {}).get("status", "?"),
        "duration_seconds": round(dur, 1),
        "samples": int(n),
        "effective_sample_rate_hz": round(n / dur, 2) if dur > 0 else None,
        "packet_loss_rate": round(1 - (n / dur) / SFREQ, 4) if dur > 0 else None,
        "channels": list(meta.get("channels") or []),
        "relative_band_power_mean": rel_mean,
        "absolute_band_power_mean_uV2Hz": abs_mean,
        "total_power_uV2Hz": round(float(np.mean(total)), 3),
        "ratios": {
            "theta_over_alpha": safe_div(theta_mean, alpha_mean),
            "alpha_over_beta": safe_div(alpha_mean, beta_mean),
            "alpha_over_theta": safe_div(alpha_mean, theta_mean),
            "delta_over_alpha": safe_div(delta_mean, alpha_mean),
        },
        "amplitude_stats_uV": {
            "std_per_channel": [round(float(s), 2) for s in np.std(eeg, axis=0)],
            "ptp_per_channel": [round(float(s), 1) for s in np.ptp(eeg, axis=0)],
            "std_mean": round(float(np.mean(np.std(eeg, axis=0))), 2),
            "ptp_max": round(float(np.max(np.ptp(eeg, axis=0))), 1),
        },
        # 通道间一致性：四通道相对功率的离散度（高离散＝可能有坏道）
        "channel_dispersion": {
            b: round(float(np.std(rel_p[b]) / np.mean(rel_p[b])), 4)
            for b in BANDS if np.mean(rel_p[b]) > 0
        },
    }
    results.append(rec)

# 排序：按 session_id
results.sort(key=lambda r: r["session_id"])

out = {
    "_meta": {
        "purpose": "评测集 L4-02b 冻结素材 · 真实 session 频段统计特征",
        "generated_by": "build_L4_features.py",
        "generated_date": "2026-09-11",
        "authorization": "法师 2026-09-11 授权（评测集 §9.6 / 决策日志 D24）",
        "band_definition": "照抄 analyze_recording.py:18-26，Delta(0.5-4)/Theta(4-8)/"
                           "Alpha(8-12)/Beta(12-30)/Gamma(30-45)",
        "psd_method": "scipy.signal.welch, nperseg=512 (2×sfreq), sfreq=256.0",
        "data_level": "L0 原始脑电衍生 → 仅限轨道 B 本地评测，禁止发送任何线上模型",
        "privacy_note": "受试者 P001 即项目发起人本人（见数据字典 §1 nickname 示例"
                        "'发起人'）。session_note 中的修行体验自述属个人修习记录，"
                        "本素材**未纳入**任何自评文本，仅含数值统计特征。",
        "excludes": "原始波形样本、逐样本时间戳、session_note 文本内容",
        "raw_dir_readonly": "02_raw 全程只读，未写入未修改",
    },
    "sessions": results,
}

out_path = os.path.join(OUT_DIR, "L4-02b_真实session频段统计特征.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

print("已生成: %s" % out_path)
print("session 总数: %d" % len(results))
print()
print("%-26s %-10s %-9s %-12s %7s %8s" % (
    "session_id", "type", "location", "dur(s)", "Alpha", "std均值"))
print("-" * 86)
for r in results:
    print("%-26s %-10s %-9s %12.1f %7.4f %8.2f" % (
        r["session_id"], r["session_type"], r["location"],
        r["duration_seconds"], r["relative_band_power_mean"]["Alpha"],
        r["amplitude_stats_uV"]["std_mean"]))
