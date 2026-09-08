"""集成自测：console_server.MonitorSession + TcpReceiver + 官方 mock 全链路。

验证点（09-08 V1.4 多设备改造）：
  1. adapter="neuradock" 会话能以 7 通道布局建缓冲并收到数据；
  2. tick 事件的 wave 含 7 通道、bands 正常产出（compute_band_power 走 250Hz 窗口）；
  3. 停止会话后 save_bin 落盘 npz：meta.sfreq=250、channels=7、device=neuradock；
  4. 回归：simulate 会话仍为 Muse 4 通道（默认行为不变）。

运行：python muse2-master 下先起 mock，再于项目根跑本脚本（自含 mock 启动）。
仅本机回环，不外发。"""
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
MOCK = os.path.join(ROOT, "05_产品与开发", "NeuraDock", "参考仓库",
                    "neuradock-codex-plugin", "plugins", "neuradock-codex-plugin",
                    "scripts", "mock_neuradock_server.mjs")
PORT = 19603
REPORT_DIR = os.path.join(ROOT, "muse2-repo", "muse2-master", "report")


def wait_events(mon, pred, timeout=12.0):
    """从 MONITOR 事件队列取到满足 pred 的事件为止，超时返回 None。"""
    deadline = time.time() + timeout
    seen = []
    while time.time() < deadline:
        try:
            ev = mon.events.get(timeout=0.5)
        except Exception:
            # 队列空时 get 抛 queue.Empty
            continue
        seen.append(ev)
        if pred(ev):
            return ev, seen
    return None, seen


def main():
    sys.path.insert(0, ROOT)
    mock_proc = subprocess.Popen(
        ["node", MOCK, f"--port={PORT}", "--duration=30"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.2)
    fails = []
    try:
        from console_server import MONITOR
        # ── 1. NeuraDock 会话 ──
        MONITOR.start(simulate=False, address=None,
                      session_info={"participant": "SELFTEST"},
                      adapter="neuradock", serial_port=f"127.0.0.1:{PORT}")
        ev, seen = wait_events(
            MONITOR, lambda e: e.get("type") == "tick" and e.get("wave"))
        if ev is None:
            fails.append(f"未收到带波形的 tick；事件: {[e.get('type') for e in seen]}")
        else:
            wave = ev["wave"]
            if sorted(wave.keys()) != sorted(["CP5", "CP6", "PO3", "PO4", "O1", "Oz", "O2"]):
                fails.append(f"wave 通道错误: {sorted(wave.keys())}")
            if any(len(v) == 0 for v in wave.values()):
                fails.append("存在空通道波形")
            # 等第一个频段功率产出（mock 持续 30s，250Hz×8s 满足最小窗）
            ev2, _ = wait_events(
                MONITOR, lambda e: e.get("type") == "tick" and e.get("bands"),
                timeout=14.0)
            if ev2 is None:
                fails.append("bands 未产出（compute_band_power 7通道/250Hz 路径未通）")
            else:
                # 借鉴四件套之 FFT 曲线数据源：tick 应携带 psd={freqs,db}
                psd = ev2.get("psd")
                if not psd or not psd.get("freqs") or not psd.get("db"):
                    fails.append("tick.psd 缺失（前端 FFT 频谱曲线无数据源）")
                elif len(psd["freqs"]) != len(psd["db"]):
                    fails.append("psd.freqs 与 psd.db 长度不一致")
                else:
                    # mock 为 10Hz 正弦：PSD 峰值应落在 alpha 带附近（8–13Hz）
                    fmax = psd["freqs"][max(range(len(psd["db"])),
                                            key=lambda i: psd["db"][i])]
                    if not 7.0 <= fmax <= 13.0:
                        fails.append(f"PSD 峰值频率异常：{fmax:.1f}Hz（期望 ~10Hz）")
        MONITOR.request_stop(save=True)
        ev3, _ = wait_events(MONITOR, lambda e: e.get("type") in ("end", "saved"),
                             timeout=15.0)
        saved = MONITOR.saved
        if not saved or not saved.get("npz"):
            fails.append(f"会话数据未落盘（saved={saved}）")
        else:
            import numpy as np
            # 用 with 打开：np.load 对 npz 是 zip 句柄，不关会锁文件删不掉
            with np.load(saved["npz"], allow_pickle=True) as z:
                meta = z["meta"].item()
                eeg = z["eeg"]
                has_pf = "eeg_pre_filter" in z.files
                pf = z["eeg_pre_filter"] if has_pf else None
            if eeg.shape[1] != 7:
                fails.append(f"npz 通道数 {eeg.shape[1]} ≠ 7")
            if float(meta["sfreq"]) != 250.0:
                fails.append(f"npz sfreq {meta['sfreq']} ≠ 250")
            if meta.get("device") != "neuradock":
                fails.append(f"npz device {meta.get('device')} ≠ neuradock")
            if meta.get("channels", [])[:1] != ["CP5"]:
                fails.append(f"npz channels {meta.get('channels')} 首通道非 CP5")
            # L1 数据诚实性断言
            chain = meta.get("signal_chain") or {}
            if not has_pf:
                fails.append("真机会话 npz 缺少 eeg_pre_filter 列（L1 未生效）")
            else:
                if pf.shape != eeg.shape:
                    fails.append(f"pre_filter 形状 {pf.shape} ≠ eeg 形状 {eeg.shape}")
                # 滤波后与原始不应逐点相等（带通生效）
                elif np.allclose(pf, eeg):
                    fails.append("pre_filter 与 eeg 完全相同（raw 旁路可能未接滤波前数据）")
            if chain.get("chain_tag") != "v12_bp_1_40":
                fails.append(f"signal_chain.chain_tag={chain.get('chain_tag')} ≠ v12_bp_1_40")
            if chain.get("pre_filter_available") is not True:
                fails.append("signal_chain.pre_filter_available 非 True")
            try:
                os.remove(saved["npz"])   # 自测产物即删
            except OSError as e:
                print(f"NOTE: 自测 npz 延迟删除失败（稍后手工清理）: {e}")
            rp = saved.get("report")
            if rp and os.path.exists(rp):
                try:
                    os.remove(rp)
                except OSError:
                    pass

        # ── 2. 回归：模拟会话仍是 Muse 4 通道 ──
        time.sleep(1.0)
        MONITOR.start(simulate=True, session_info={})
        ev4, seen4 = wait_events(
            MONITOR, lambda e: e.get("type") == "tick" and e.get("wave"),
            timeout=10.0)
        if ev4 is None:
            fails.append(f"模拟会话无 tick: {[e.get('type') for e in seen4]}")
        elif sorted(ev4["wave"].keys()) != sorted(["TP9", "AF7", "AF8", "TP10"]):
            fails.append(f"模拟会话通道错误: {sorted(ev4['wave'].keys())}")
        MONITOR.request_stop(save=False)
        wait_events(MONITOR, lambda e: e.get("type") == "end", timeout=10.0)

        if fails:
            for f in fails:
                print("FAIL:", f)
            return 1
        print("PASS: 集成自测通过 —— NeuraDock 7通道全链路（TCP→缓冲→tick→npz）"
              " + Muse 模拟回归")
        return 0
    finally:
        mock_proc.terminate()
        try:
            mock_proc.wait(timeout=5)
        except Exception:
            mock_proc.kill()


if __name__ == "__main__":
    sys.exit(main())
