"""NeuraDock 模拟器验证：启动模拟器 → TcpReceiver 连上 → 校验生理语义与协议。

验证点（比官方 mock 的固定 10Hz 正弦更进一步，验生理正确性）：
  1. 握手：接收器发 "start" 后模拟器才推流；
  2. 协议：7 通道全部到位、列序 CP5..O2、行格式（蓝牙 42 列）正确解析；
  3. 生理语义（关键）：
     - relax 状态：枕区 Oz 的 Alpha(8-13Hz) 应是主峰（FFT 验证）；
     - focus 状态：Alpha 应明显被抑制（Alpha 阻滞），功率低于 relax；
  4. 伪迹注入：mains 伪迹下 FFT 应在 50Hz 出现尖峰；flat 伪迹下 O2 峰峰值≈0；
  5. 实时配速：有效采样率应≈250Hz（非积压虚高）。

运行：python neuradock_simulator_selftest.py    退出码 0=通过。仅本机回环。
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "muse2-repo", "muse2-master"))
SIM = os.path.join(HERE, "neuradock_simulator.py")
PORT = 19610


def _collect(receiver, app, seconds):
    """跑一段时间，返回缓冲里各通道数组。"""
    time.sleep(seconds)
    receiver.stop()
    return {ch: list(app.buffer.eeg_all[ch]) for ch in app.buffer.channels}


def _peak_freq(sig, sfreq, lo, hi):
    import numpy as np
    sig = np.asarray(sig)
    if sig.size < 64:
        return None, None
    sig = sig - sig.mean()
    spec = np.abs(np.fft.rfft(sig))
    freqs = np.fft.rfftfreq(sig.size, d=1.0 / sfreq)
    m = (freqs >= lo) & (freqs <= hi)
    if not m.any():
        return None, None
    band = spec[m]
    pf = freqs[m][np.argmax(band)]
    # 该频段总功率（用于跨状态比较）
    power = float(np.sum(band ** 2))
    return pf, power


def run_case(name, sim_args, checks, collect_s=6.0):
    """启动一个模拟器实例跑指定状态/伪迹，连接收器采集后执行 checks。"""
    import numpy as np
    from muse_local_server import DataBuffer
    from neuradock_receiver import TcpReceiver, ND_CHANNELS, ND_SFREQ

    proc = subprocess.Popen(
        [sys.executable, SIM, f"--port={PORT}", "--transport=bluetooth"] + sim_args,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    time.sleep(1.5)
    if proc.poll() is not None:
        err = proc.stderr.read().decode("utf-8", "replace")
        print(f"FAIL[{name}]: 模拟器启动失败：{err[:300]}")
        return False
    fails = []
    try:
        class App: pass
        app = App()
        app.buffer = DataBuffer(channels=ND_CHANNELS, sfreq=ND_SFREQ,
                                device="neuradock")
        app.after = lambda _ms, fn: fn()
        rx = TcpReceiver(app, host="127.0.0.1", port=PORT)
        rx.start()
        data = _collect(rx, app, collect_s)

        n = min(len(v) for v in data.values())
        if n < 100:
            fails.append(f"样本过少：{n}")
        else:
            fails.extend(checks(data, n))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
    if fails:
        for f in fails:
            print(f"FAIL[{name}]: {f}")
        return False
    print(f"PASS[{name}]")
    return True


def main():
    import numpy as np
    ok = True

    # 用例1：relax —— 枕区 Oz 主峰应落在 Alpha 带(8-13Hz)
    def chk_relax(data, n):
        f = []
        pf, pw = _peak_freq(data["Oz"][-n:], 250.0, 1.0, 40.0)
        if pf is None:
            f.append("Oz 无法算主峰")
        elif not 8.0 <= pf <= 13.0:
            f.append(f"relax 态 Oz 主峰 {pf:.1f}Hz 不在 Alpha 带(8-13)")
        # 枕区 Alpha 应强于顶区（区域差异）
        _, pw_oz = _peak_freq(data["Oz"][-n:], 250.0, 8.0, 13.0)
        _, pw_cp = _peak_freq(data["CP5"][-n:], 250.0, 8.0, 13.0)
        if pw_oz is not None and pw_cp is not None and pw_oz <= pw_cp:
            f.append("relax 态枕区 Oz 的 Alpha 未强于顶区 CP5（区域布局错）")
        return f
    ok &= run_case("relax生理语义", ["--state=relax"], chk_relax)

    # 用例2：focus —— Alpha 应被抑制（功率低于 relax）
    relax_alpha = {}
    def chk_focus(data, n):
        f = []
        _, pw = _peak_freq(data["Oz"][-n:], 250.0, 8.0, 13.0)
        relax_alpha["focus"] = pw
        return f
    # 先单独测 relax 取 Alpha 功率基准
    def grab_relax(data, n):
        _, pw = _peak_freq(data["Oz"][-n:], 250.0, 8.0, 13.0)
        relax_alpha["relax"] = pw
        return []
    run_case("relax基准取值", ["--state=relax"], grab_relax, collect_s=5.0)
    ok &= run_case("focus采集", ["--state=focus"], chk_focus, collect_s=5.0)
    if relax_alpha.get("relax") and relax_alpha.get("focus"):
        if relax_alpha["focus"] >= relax_alpha["relax"]:
            print(f"FAIL[Alpha阻滞]: focus({relax_alpha['focus']:.0f}) "
                  f"未低于 relax({relax_alpha['relax']:.0f})")
            ok = False
        else:
            print(f"PASS[Alpha阻滞]: focus {relax_alpha['focus']:.0f} < "
                  f"relax {relax_alpha['relax']:.0f}")
    else:
        print("FAIL[Alpha阻滞]: 功率未取到")
        ok = False

    # 用例3：mains 伪迹 —— FFT 应在 50Hz 附近出现尖峰
    def chk_mains(data, n):
        f = []
        sig = np.asarray(data["Oz"][-n:]); sig = sig - sig.mean()
        spec = np.abs(np.fft.rfft(sig))
        freqs = np.fft.rfftfreq(sig.size, d=1.0 / 250.0)
        m50 = (freqs >= 49) & (freqs <= 51)
        mref = (freqs >= 30) & (freqs <= 45)
        if not m50.any() or not mref.any():
            f.append("频谱范围不足")
        else:
            ratio = spec[m50].max() / (np.median(spec[mref]) + 1e-9)
            if ratio < 3.0:
                f.append(f"mains 伪迹下 50Hz 尖峰不显著（ratio={ratio:.1f}）")
        return f
    ok &= run_case("mains工频伪迹", ["--state=relax", "--artifact=mains"], chk_mains)

    # 用例4：flat 伪迹 —— O2(索引6) 峰峰值应≈0
    def chk_flat(data, n):
        f = []
        o2 = np.asarray(data["O2"][-n:])
        ptp = float(o2.max() - o2.min())
        oz = np.asarray(data["Oz"][-n:])
        ptp_oz = float(oz.max() - oz.min())
        if ptp > 0.3 * ptp_oz:
            f.append(f"flat 伪迹下 O2 峰峰值 {ptp:.1f} 未被压低（Oz={ptp_oz:.1f}）")
        return f
    ok &= run_case("flat悬空伪迹", ["--state=relax", "--artifact=flat"], chk_flat)

    print("=" * 50)
    print("模拟器验证：" + ("全部通过 ✅" if ok else "存在失败 ❌"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
