# -*- coding: utf-8 -*-
"""
评测集 L4-02b 素材生产工具 · 第一步：探查 npz 真实结构
====================================================
只读探查，不写任何文件、不修改 02_raw。

依据《ZEN_EEG_Data_Dictionary_V1_2》§3.1：
  eeg_raw.npz 含 eeg(float64, (n,4), µV) / timestamps(float64, (n,)) / meta(dict)
  通道映射 V1.1 冻结：channels = ['TP9','AF7','AF8','TP10']
  标称采样率 256 Hz；有效采样率 = samples / duration

纪律遵守：
  - 02_raw 为只读区（字典 §3.1 末），本脚本只 np.load 读取，绝不写入
  - 06_features 在字段清单定义前"只允许存放人工文档"（字典 §4 末注），
    故本评测素材不得写入 06_features，改存评测集自有素材目录
"""
import numpy as np
import glob
import os
import json

BASE = r"C:\Users\tiand\OneDrive\Zen-EEG"

raw_paths = sorted(glob.glob(os.path.join(BASE, "02_raw", "*", "eeg_raw.npz")))
quar_paths = sorted(glob.glob(os.path.join(
    BASE, "03_quality_control", "quarantine", "*", "eeg_raw.npz")))

print("=" * 78)
print("npz 总数: 02_raw=%d, quarantine=%d" % (len(raw_paths), len(quar_paths)))
print("=" * 78)

for p in raw_paths + quar_paths:
    z = np.load(p, allow_pickle=True)
    sid = os.path.basename(os.path.dirname(p))
    loc = "QUARANTINE" if "quarantine" in p else "02_raw"

    keys = sorted(z.files)
    eeg = z["eeg"]
    m = z["meta"].item()

    n = eeg.shape[0]
    nch = eeg.shape[1] if eeg.ndim > 1 else 1
    sfreq = float(m.get("sfreq", 0) or 0)
    dur = float(m.get("duration", 0) or 0)
    eff = (n / dur) if dur > 0 else 0.0

    # 逐通道峰峰值与标准差（µV），用于判断是否有坏道/伪迹
    ptp = np.ptp(eeg, axis=0)
    std = np.std(eeg, axis=0)

    chs = m.get("channels")

    print("\n[%s] %s" % (loc, sid))
    print("  npz keys      : %s" % keys)
    print("  eeg shape     : (%d, %d)  dtype=%s" % (n, nch, eeg.dtype))
    print("  meta.channels : %s" % (chs,))
    print("  meta.sfreq    : %s   meta.samples=%s   meta.duration=%.1fs"
          % (m.get("sfreq"), m.get("samples"), dur))
    print("  有效采样率     : %.2f Hz   丢包率=%.4f" % (eff, 1 - eff / sfreq if sfreq else 0))
    print("  逐通道峰峰值µV : %s" % np.array2string(ptp, precision=1, separator=", "))
    print("  逐通道标准差µV : %s" % np.array2string(std, precision=2, separator=", "))

    # qc.json 对照
    qc_dir = (os.path.join(BASE, "03_quality_control", "quarantine", sid)
              if loc == "QUARANTINE"
              else os.path.join(BASE, "03_quality_control", sid))
    qc_path = os.path.join(qc_dir, "qc.json")
    if os.path.exists(qc_path):
        with open(qc_path, "r", encoding="utf-8") as f:
            qc = json.load(f)
        print("  qc.clean_ratio=%s  qc.noise_epochs=%s  qc.channel_quality=%s"
              % (qc.get("clean_ratio"), qc.get("noise_epochs"),
                 qc.get("channel_quality")))
    else:
        print("  qc.json: 未找到 (%s)" % qc_path)

print("\n" + "=" * 78)
print("探查完成（未写入任何文件）")
