"""TcpReceiver 自测：官方 mock 服务器（Node）+ 真协议数据流 → 缓冲 → 7 通道验证。

运行方式（在 muse2-master 目录）：
    python neuradock_selftest.py
退出码 0=全部通过。本脚本只连 127.0.0.1 本地端口，不外发数据。
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
MOCK = os.path.join(HERE, "..", "..", "05_产品与开发", "NeuraDock", "参考仓库",
                    "neuradock-codex-plugin", "plugins", "neuradock-codex-plugin",
                    "scripts", "mock_neuradock_server.mjs")
PORT = 19601
DURATION = 6


def main():
    import numpy as np
    sys.path.insert(0, HERE)
    from muse_local_server import DataBuffer
    from neuradock_receiver import TcpReceiver, ND_CHANNELS, ND_SFREQ

    mock = os.path.abspath(MOCK)
    if not os.path.exists(mock):
        print(f"FAIL: 官方 mock 服务器不存在：{mock}")
        return 1

    node = "node"
    proc = subprocess.Popen(
        [node, mock, f"--port={PORT}", f"--duration={DURATION}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        time.sleep(1.0)   # 等 mock 监听
        if proc.poll() is not None:
            err = proc.stderr.read().decode("utf-8", "replace")
            print(f"FAIL: mock 启动失败：{err}")
            return 1

        class App:
            pass
        app = App()
        app.buffer = DataBuffer(channels=ND_CHANNELS, sfreq=ND_SFREQ,
                                device="neuradock")
        app.after = lambda _ms, fn: fn()

        rx = TcpReceiver(app, host="127.0.0.1", port=PORT)
        events = []
        rx.on_status = lambda t: events.append(t)
        rx.start()

        deadline = time.time() + DURATION + 4
        while time.time() < deadline and rx.raw_count < 20:
            time.sleep(0.3)
        time.sleep(0.5)
        rx.stop()

        # ── 断言 ────────────────────────────────────────────────────────
        fails = []
        if not rx.is_connected() and rx.packet_count == 0:
            fails.append(f"未收到任何数据（last_error={rx.last_error}）")
        if rx.raw_count < 10:
            fails.append(f"行数过少：raw={rx.raw_count} packets={rx.packet_count}")
        if rx.bad_line_count > 0:
            fails.append(f"存在坏行：{rx.bad_line_count}")
        if rx.detected_transport != "bluetooth":
            fails.append(f"模式识别错误：{rx.detected_transport}（mock 为 5 组打包行）")
        n = min(len(app.buffer.eeg_all[ch]) for ch in ND_CHANNELS)
        if n < 40:
            fails.append(f"缓冲样本不足：{n}")
        # 7 通道数据长度一致
        lens = {ch: len(v) for ch, v in app.buffer.eeg_all.items()}
        if len(set(lens.values())) != 1:
            fails.append(f"各通道长度不一致：{lens}")
        # mock 信号 = 每通道 10Hz 正弦（幅度 12+ch µV）：滤波后应仍在 5–15Hz 有峰
        sig = np.asarray(app.buffer.eeg_all["Oz"])
        if sig.size > 128:
            spec = np.abs(np.fft.rfft(sig - sig.mean()))
            freqs = np.fft.rfftfreq(sig.size, d=1.0 / ND_SFREQ)
            peak = freqs[1 + np.argmax(spec[1:])]
            if not 7.0 <= peak <= 13.0:
                fails.append(f"Oz 主峰频率异常：{peak:.1f}Hz（期望 ~10Hz）")
        # 时间戳网格密度应≈250Hz（mock 每 20ms 发 5 样本）
        ts = np.asarray(app.buffer.timestamps)
        if ts.size > 2:
            rate = (ts.size - 1) / (ts[-1] - ts[0])
            if not 150 <= rate <= 350:
                fails.append(f"有效采样率异常：{rate:.0f}Hz（期望≈250）")

        print(f"raw={rx.raw_count} packets={rx.packet_count} "
              f"bad={rx.bad_line_count} mode={rx.detected_transport} "
              f"samples/ch={n} transport_ok")
        for e in events:
            print("  event:", e)
        if fails:
            for f in fails:
                print("FAIL:", f)
            return 1
        print("PASS: TcpReceiver 全链路自测通过（握手/断行重组/7通道/滤波/入缓冲）")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
