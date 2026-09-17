#!/usr/bin/env python3
"""ZG-059 A2 `zx_phase` **端到端**验证（2026-09-14）

为什么需要它（守 §7.3「编译通过≠运行时正确」）：
  verify_zx_phase.py 验的是 derive_zx_phase 函数 + save_bin 兼容性，
  但**没有验证 console_server._do_save 与 closedloop_experiment 里我插入的
  那段 try/except 代码真的被执行、真的把 zx_phase 写进了 npz**。
  closedloop_selftest PASS 也只断言 tick 字段完整，同样不检查 zx_phase。
  故本脚本走**真实会话全链路**，读回落盘的 npz 断言字段确实存在且值正确。

覆盖两条写入路径：
  路径 A：MonitorSession(simulate=True) → _do_save → npz
  路径 B：run_closed_loop(simulate=True) → npz

诚实边界（不夸大验证范围）：
  - simulate 会话时长远短于 baseline_seconds(120s)，故 ctrl_phase 自然停在
    "baseline"，**端到端只能自然验证到 ["入","照"]**；
    "locked"（含「运」）分支须 120 秒基线期，端到端不验，已由
    verify_zx_phase.py 判据 2 在单元层覆盖 —— 此处如实标注，不冒充已验。
  - 全程 simulate，**不经真机蓝牙**；真机链路须法师侧验证。

设计纪律：
  - 静音：闭环路径 monkeypatch IsoEngine 为 stub，不发声
  - 产物清理：前后快照差集，只删本次自产文件（红线7：显式、不 glob 既有数据）
  - 不改任何项目代码

运行：python verify_zx_phase_e2e.py    退出码 0=通过
"""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MUSE_DIR = os.path.join(ROOT, "muse2-repo", "muse2-master")
sys.path.insert(0, ROOT)
sys.path.insert(0, MUSE_DIR)

import numpy as np

REPORT_DIR = os.path.join(MUSE_DIR, "report")
EXP_DIR = os.path.join(ROOT, "experiments")
fails = []


def check(cond, ok_msg, fail_msg):
    if cond:
        print(f"  ✅ {ok_msg}")
    else:
        print(f"  ❌ {fail_msg}")
        fails.append(fail_msg)


def snapshot(d):
    return set(glob.glob(os.path.join(d, "*"))) if os.path.isdir(d) else set()


def cleanup(new_paths):
    """只删本次新增文件（前后差集），绝不 glob 既有数据（红线7）。"""
    for p in new_paths:
        try:
            os.remove(p)
        except OSError as e:
            print(f"  NOTE: 产物延迟删除失败（须手工清理）：{p} ({e})")


def read_meta(npz_path):
    with np.load(npz_path, allow_pickle=True) as z:
        return z["meta"].item()


def path_a_monitor():
    """路径 A：监测会话 → console_server._do_save"""
    print("\n── 路径 A：MonitorSession(simulate) → _do_save ────────────────")
    from console_server import MONITOR

    before = snapshot(REPORT_DIR)
    npz_path = None
    try:
        MONITOR.start(simulate=True, session_info={"participant": "ZXPHASE_E2E"})
        # 等到有 tick 且 bands 产出（照相证据成立的前提）
        got_bands = False
        import time as _t
        deadline = _t.time() + 25
        while _t.time() < deadline:
            try:
                ev = MONITOR.events.get(timeout=0.5)
            except Exception:
                continue
            if ev.get("type") == "tick" and ev.get("bands"):
                got_bands = True
                break
        check(got_bands, "监测会话已产出 bands（照相证据成立）",
              "未产出 bands → 无法验证照相派生")
        MONITOR.request_stop(save=True)
        # 等 saved 事件
        deadline = _t.time() + 20
        while _t.time() < deadline:
            try:
                ev = MONITOR.events.get(timeout=0.5)
            except Exception:
                continue
            if ev.get("type") in ("saved", "end"):
                if MONITOR.saved and MONITOR.saved.get("npz"):
                    npz_path = MONITOR.saved["npz"]
                    break
    finally:
        try:
            MONITOR.request_stop(save=False)
        except Exception:
            pass

    if not npz_path or not os.path.exists(npz_path):
        check(False, "", f"监测会话未落盘 npz（saved={MONITOR.saved}）")
        cleanup(snapshot(REPORT_DIR) - before)
        return

    try:
        m = read_meta(npz_path)
        zp = m.get("zx_phase")
        print(f"  实测 npz: {os.path.basename(npz_path)}")
        print(f"  实测 meta.zx_phase = {zp!r}")
        print(f"  实测 meta.scene    = {m.get('scene')!r}")
        check(zp is not None,
              "🔑 console_server._do_save 里插入的 zx_phase 代码**确实执行并写入**",
              "npz 中无 zx_phase → 插入代码未生效（try/except 吞掉异常？）")
        if zp is not None:
            check(isinstance(zp, list), f"值是数组 {zp}", f"值非数组：{type(zp).__name__}")
            check(zp == ["入", "照"],
                  f"simulate 短会话（基线期未出决策）→ ['入','照']，实得 {zp}",
                  f"值不符预期：{zp}")
            check("运" not in zp,
                  "如实未记「运」相：ctrl_phase 仍为 baseline，未虚构闭环决策",
                  "误记了「运」相 → 违反红线9（不得把未发生的记成已发生）")
        # 既有字段未受影响
        check(m.get("scene") == "monitor", f"scene 仍为 monitor（未被五相化）",
              f"scene 被改动：{m.get('scene')}")
        for k in ("timestamp", "sfreq", "channels", "device", "samples",
                  "duration", "signal_chain"):
            if k not in m:
                check(False, "", f"既有字段 {k} 丢失")
        check(all(k in m for k in ("timestamp", "sfreq", "channels", "device",
                                   "samples", "duration", "signal_chain")),
              "既有 7 个固定字段全部完好",
              "既有字段缺失")
        check("phase" not in m,
              "未写入撞名的 phase 字段（新字段名 zx_phase 生效）",
              "写入了 phase → 撞名未解决")
    finally:
        cleanup(snapshot(REPORT_DIR) - before)


def path_b_closedloop():
    """路径 B：闭环实验 → closedloop_experiment 保存点"""
    print("\n── 路径 B：run_closed_loop(simulate) → 保存点 ─────────────────")
    import closedloop_experiment as cle

    # 静音：替换 IsoEngine，不发声（同 closedloop_selftest 范式）
    class SilentEngine:
        def __init__(self, *a, **k): pass
        def start(self): pass
        def stop(self): pass
        def set_beat(self, hz): pass
        def set_volume(self, v): pass
    cle.IsoEngine = SilentEngine

    cfg_path = os.path.join(ROOT, "experiment_config.json")
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["experiment"]["baseline_seconds"] = 11
    cfg["experiment"]["duration_seconds"] = 16
    cfg["experiment"]["tag"] = "ZXPHASEE2E"
    cfg["device"]["decision_interval_seconds"] = 1.0

    before_r = snapshot(REPORT_DIR)
    before_e = snapshot(EXP_DIR)
    npz_path = None
    m = None
    read_err = None
    try:
        cle.run_closed_loop(cfg, simulate=True, callback=lambda e: None,
                            session_info={"participant": "ZXPHASE_E2E"})
        new_npz = [p for p in (snapshot(REPORT_DIR) - before_r) if p.endswith(".npz")]
        if new_npz:
            npz_path = sorted(new_npz)[0]
            # ⚠️ 必须在 cleanup 之前读回（首轮把读取放在 finally 之后，
            #    产物已被自己删掉 → FileNotFoundError。脚本缺陷，非项目代码问题）
            try:
                m = read_meta(npz_path)
            except Exception as e:
                read_err = f"{type(e).__name__}: {e}"
    finally:
        cleanup((snapshot(REPORT_DIR) - before_r) | (snapshot(EXP_DIR) - before_e))

    if not npz_path:
        check(False, "", "闭环会话未落盘 npz，无法验证路径 B")
        return
    if m is None:
        check(False, "", f"npz 读回失败：{read_err}")
        return

    zp = m.get("zx_phase")
    print(f"  实测 npz: {os.path.basename(npz_path)}")
    print(f"  实测 meta.zx_phase = {zp!r}")
    print(f"  实测 meta.scene    = {m.get('scene')!r}")
    check(zp is not None,
          "🔑 closedloop_experiment 里插入的 zx_phase 代码**确实执行并写入**",
          "npz 中无 zx_phase → 插入代码未生效")
    if zp is not None:
        check(isinstance(zp, list), f"值是数组 {zp}", f"值非数组：{type(zp).__name__}")
        # 闭环会话跑满 5 秒闭环期 → n_loop>0 → 含「运」
        check(zp == ["入", "照", "运"],
              f"闭环会话（n_loop>0 已出决策）→ ['入','照','运']，实得 {zp}",
              f"值不符：{zp}")
        check("运" in zp,
              "如实记入「运」相：闭环决策确实产出（n_loop>0）",
              "闭环会话竟未记「运」相 → 派生判据失效")
    check(m.get("scene") == "closedloop",
          "scene 仍为 closedloop（未被五相化，C1 依裁定不动）",
          f"scene 被改动：{m.get('scene')}")
    check("experiment_tag" in m and "experiment_mode" in m,
          "既有 experiment_tag / experiment_mode 字段完好",
          "既有实验字段丢失")
    check("phase" not in m,
          "未写入撞名的 phase 字段",
          "写入了 phase → 撞名未解决")


def main():
    print("=" * 74)
    print("ZG-059 A2 `zx_phase` 端到端验证 · 真实会话全链路")
    print("=" * 74)
    print("静音（IsoEngine 已替换为 stub）、simulate 模式（无硬件）、产物自清理")

    path_a_monitor()
    path_b_closedloop()

    print("\n" + "=" * 74)
    if fails:
        print(f"❌ FAIL {len(fails)} 项：")
        for f in fails:
            print(f"   - {f}")
        return 1
    print("✅ PASS：两条写入路径的 zx_phase 均端到端验证通过")
    print("\n如实标注的未验证项：")
    print("  ① ctrl_phase=='locked' 分支（含「运」的监测会话）须 120 秒基线期，")
    print("     端到端未验；已由 verify_zx_phase.py 判据 2 在单元层覆盖")
    print("  ② 全程 simulate，未经真机蓝牙；真机会话的 zx_phase 须法师侧验证")
    return 0


if __name__ == "__main__":
    sys.exit(main())
