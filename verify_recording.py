"""验证 OpenMuse 录制的头环数据：解码并检查各传感器是否真实有效。"""
import sys
import numpy as np
import OpenMuse

import os
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_data.txt"), "r", encoding="utf-8") as f:  # 2026-09-19 随项目迁 D 盘，改为脚本同目录
    messages = f.readlines()

print(f"读取原始通知: {len(messages)} 条")
data = OpenMuse.decode_rawdata(messages)

print(f"\n解码出的数据流: {list(data.keys())}")

for name, df in data.items():
    n = len(df)
    cols = [c for c in df.columns if c != "time"]
    print(f"\n=== {name} ===")
    print(f"  样本数: {n}, 通道: {cols}")
    if n < 2:
        continue
    # 估算采样率
    t = df["time"].to_numpy(dtype=float)
    dur = t[-1] - t[0]
    if dur > 0:
        rate = n / dur
        print(f"  时长: {dur:.1f}s, 估算采样率: {rate:.1f} Hz")
    # 各通道统计
    for c in cols[:8]:
        v = df[c].to_numpy(dtype=float)
        print(f"    {c}: 均值={np.mean(v):.2f}, 标准差={np.std(v):.2f}, 范围=[{np.min(v):.1f}, {np.max(v):.1f}]")
