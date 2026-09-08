"""实验路径 tick 字段自测（审计问题1的回归防线，2026-09-08）。

为什么需要它：集成自测 neuradock_console_selftest 只覆盖**监测路径** tick；
独立审计发现采集台合并"只做了一半"——前端统一了仪表渲染，但后端**实验路径**
tick 缺 psd/vitals/ppg/motion_xyz/connected/packets 字段，致闭环模式下
FFT 频谱图、体征面板、数据稳定条全部空转。本脚本跑一次最小闭环实验，断言
实验 tick 携带全部共享仪表字段，堵住这个覆盖盲区。

设计（规避真闭环实验的两个副作用）：
  - monkeypatch IsoEngine → 静音 stub：测试期间**不播放任何声音**；
  - 直接传 cfg 字典（baseline=11/duration=16）：绕过 load_experiment_config
    的 ≥30s 校验，约 16 秒跑完（数据积累 8s 后才有首个频段/PSD）；
  - simulate 模式：无需任何硬件；
  - 唯一 tag + before/after 差集：跑完精确清理 experiments/ 与 report/ 产物。

运行：python closedloop_selftest.py    退出码 0=通过。仅本机，不外发、不发声。
"""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "muse2-repo", "muse2-master"))

REPORT_DIR = os.path.join(ROOT, "muse2-repo", "muse2-master", "report")
EXP_DIR = os.path.join(ROOT, "experiments")
TAG = "SELFTESTLOOP"
BASELINE_S = 11      # >8s：保证基线期内已有 ≥2 次频段产出可供 finalize
DURATION_S = 16      # 闭环期约 5s，足够产出多个带 psd 的 tick
DECISION_DT = 1.0


class SilentEngine:
    """静音音频引擎 stub：替换 IsoEngine，测试期间不发声。"""
    def __init__(self, *a, **k): pass
    def start(self): pass
    def stop(self): pass
    def set_beat(self, hz): pass
    def set_volume(self, v): pass


def _snapshot(d):
    return set(glob.glob(os.path.join(d, "*"))) if os.path.isdir(d) else set()


def _cleanup(new_paths):
    for p in new_paths:
        try:
            os.remove(p)
        except OSError as e:
            print(f"NOTE: 产物延迟删除失败（稍后手工清理）：{p} ({e})")


def main():
    import closedloop_experiment as cle
    cle.IsoEngine = SilentEngine          # monkeypatch 静音，避免测试放声音

    cfg_path = os.path.join(ROOT, "experiment_config.json")
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["experiment"]["baseline_seconds"] = BASELINE_S
    cfg["experiment"]["duration_seconds"] = DURATION_S
    cfg["experiment"]["tag"] = TAG
    cfg["device"]["decision_interval_seconds"] = DECISION_DT

    before_report = _snapshot(REPORT_DIR)
    before_exp = _snapshot(EXP_DIR)

    events = []
    try:
        cle.run_closed_loop(cfg, simulate=True,
                            callback=lambda e: events.append(e),
                            session_info={"participant": "SELFTEST"})
    finally:
        new = (_snapshot(REPORT_DIR) - before_report) | (_snapshot(EXP_DIR) - before_exp)
        _cleanup(new)

    ticks = [e for e in events if e.get("type") == "tick"]
    fails = []
    if not ticks:
        fails.append("实验路径未产出任何 tick（检查 run_closed_loop 是否正常）")
    else:
        with_psd = [t for t in ticks if t.get("psd")]
        if not with_psd:
            fails.append("实验 tick 无 psd 字段（FFT 频谱数据源缺失，审计问题1未修复）")
        t = with_psd[-1] if with_psd else ticks[-1]
        # 采集台合并后，实验 tick 须携带与监测端一致的全部共享仪表字段
        for key in ("psd", "vitals", "ppg", "motion_xyz",
                    "connected", "packets", "wave", "bands"):
            if key not in t:
                fails.append(f"实验 tick 缺字段 {key}（闭环模式该仪表会空转）")
        psd = t.get("psd")
        if psd and not (psd.get("freqs") and psd.get("db")):
            fails.append("psd 结构不完整（缺 freqs/db）")
        if t.get("packets") in (None, 0):
            fails.append(f"实验 tick packets 未递增={t.get('packets')}"
                         "（前端稳定条会误报数据流静默）")
        if not isinstance(t.get("vitals"), dict):
            fails.append("vitals 非 dict（前端 updateLabPanel 会异常）")

    n_psd = len([t for t in ticks if t.get("psd")])
    print(f"ticks={len(ticks)} with_psd={n_psd} "
          f"packets={ticks[-1].get('packets') if ticks else '-'}")
    if fails:
        for f in fails:
            print("FAIL:", f)
        return 1
    print("PASS: 实验路径 tick 字段完整（审计问题1回归防线，静音/无硬件/自清理）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
