"""用更新后的中文模板重新生成已保存的报告。"""
import os
import sys
import numpy as np

SCRIPT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "muse2-repo", "muse2-master")  # 2026-09-19 由写死 C 盘旧路径改为随脚本位置推导
# Note: muse2-repo is a historical directory name (kept unchanged); the code supports the in-use device Muse S (3rd generation).
sys.path.insert(0, SCRIPT_DIR)

import muse_local_server as mls

REPORT_DIR = os.path.join(SCRIPT_DIR, "report")
for fname in ["local_20260830_183343.npz", "local_20260830_183719.npz"]:
    path = os.path.join(REPORT_DIR, fname)
    if not os.path.exists(path):
        print(f"skip {fname}")
        continue
    data = np.load(path, allow_pickle=True)
    eeg_arr = data["eeg"]
    ts = fname.replace(".npz", "")
    out = os.path.join(REPORT_DIR, ts + ".report.html")
    mls._generate_report_from_array(eeg_arr, 256.0, ts, out)
    print(f"regenerated: {out}")
