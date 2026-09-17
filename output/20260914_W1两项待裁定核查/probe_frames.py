#!/usr/bin/env python3
"""探测本机 IsoEngine 回调的**真实帧数**（静音，volume=0.0，不发声）

为什么要测：off-by-one 造成的降频比例 = 1/frames。frames=32 → 3.1%，
frames=512 → 0.2%，差 16 倍。裁定前必须知道本机真实落在哪一档。

`sd.default.blocksize` 与创建流后的 `st.blocksize` 都是 0
（paFramesPerBufferUnspecified），真实帧数只能在**回调被调用时**读到。
故本脚本以 volume=0.0 启动真实音频流（输出全零样本，物理上不发声），
只收集回调收到的 frames 分布，随即停止。不改动 IsoEngine 任何代码。
"""
import numpy as np
import sounddevice as sd

SR = 44100
frames_seen = []
status_seen = []


def cb(outdata, frames, time_info, status):
    frames_seen.append(frames)
    if status:
        status_seen.append(str(status))
    outdata[:] = 0.0            # 全零输出，静音


def main():
    print("=" * 66)
    print("IsoEngine 真实回调帧数探测 · volume=0.0 全零输出（不发声）")
    print("=" * 66)
    stream = sd.OutputStream(samplerate=SR, channels=2, dtype="float32",
                             callback=cb)
    print(f"创建后 stream.blocksize = {stream.blocksize}（0=未指定）")
    stream.start()
    sd.sleep(2000)              # 跑 2 秒收集帧数分布
    stream.stop()
    stream.close()

    if not frames_seen:
        print("⚠ 未收到任何回调（音频设备不可用？）")
        return
    a = np.array(frames_seen)
    print(f"\n回调次数 = {len(a)}（2 秒内）")
    print(f"帧数分布：min={a.min()}  max={a.max()}  "
          f"唯一值={sorted(set(a.tolist()))}")
    vals, cnts = np.unique(a, return_counts=True)
    for v, c in zip(vals, cnts):
        print(f"  frames={v:>6}  出现 {c:>4} 次  → 降频 {100.0/v:.4f}%")
    print(f"\n状态回调 = {status_seen if status_seen else '无（无 underrun）'}")

    print("\n── 对本机 off-by-one 影响的换算 ─────────────────────────")
    for v in sorted(set(a.tolist())):
        print(f"  frames={v:>6}：220Hz 载波 → {220*(1-1/v):.4f}Hz"
              f"（偏 {220/v:.4f}Hz）｜10Hz 节拍 → {10*(1-1/v):.6f}Hz"
              f"（偏 {10/v:.6f}Hz）")
    print("\n  注：帧数**固定**时降频是恒定比例；帧数**抖动**时降频比例随之抖动，")
    print("      相当于给载波/节拍叠加了一个极低频的频率调制（FM 抖动）。")


if __name__ == "__main__":
    main()
