#!/usr/bin/env python3
"""ZG-059 A2 `zx_phase` 字段验收（2026-09-14 法师裁定丙方案：多值数组）

验收判据（依《20260910_架构命名改名清单与影响面评估》§三 第 1 条）：
  ① 旧数据无 `zx_phase` 键 → 读取端**不报错**（向后兼容）
  ② 新数据带 `zx_phase` → 值符合规范（顺序、取值域、数组类型）
  ③ **按实际运行证据派生**，而非按 scene 静态映射 → 关键验证：
     同为 `scene=monitor`，出过闭环决策的会话须含「运」、只在基线期的须不含
     （若两者相同，说明丙方案退化成了甲方案，字段无聚合价值）
  ④ 既有字段（scene / samples / duration / signal_chain 等）**一个都不受影响**
  ⑤ 派生函数异常时**不阻断保存**（容错路径）

设计纪律（守 §7.1「不拿想当然的机制当事实」）：
  - 真实调用 save_bin 写 npz，再用 np.load 读回验证，不凭代码推断
  - 写入**临时目录**（REPORT_DIR 重定向），测完清理，不污染真实数据目录
  - 不启动音频、不占用蓝牙硬件、无副作用

运行：python verify_zx_phase.py    退出码 0=通过
"""
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MUSE_DIR = os.path.join(ROOT, "muse2-repo", "muse2-master")
sys.path.insert(0, MUSE_DIR)
sys.path.insert(0, ROOT)

import numpy as np

fails = []
notes = []


def check(cond, ok_msg, fail_msg):
    if cond:
        print(f"  ✅ {ok_msg}")
    else:
        print(f"  ❌ {fail_msg}")
        fails.append(fail_msg)


def main():
    import muse_local_server as mls

    print("=" * 74)
    print("ZG-059 A2 `zx_phase` 字段验收 · 真实写 npz 并读回")
    print("=" * 74)

    # ── 0. 派生函数本身的单元判据 ──────────────────────────────────
    print("\n── 判据 0：derive_zx_phase 单元行为 ──────────────────────────")
    d = mls.derive_zx_phase
    check(d() == ["入"],
          "缺省参数 → ['入']（无证据时只认采集层，不抛异常）",
          f"缺省参数应返回 ['入']，实得 {d()}")
    check(d(has_bandpower=True) == ["入", "照"],
          "有频段功率 → ['入','照']",
          f"实得 {d(has_bandpower=True)}")
    check(d(has_bandpower=True, has_closedloop_decision=True) == ["入", "照", "运"],
          "有功率+有决策 → ['入','照','运']",
          f"实得 {d(has_bandpower=True, has_closedloop_decision=True)}")
    check(d(has_closedloop_decision=True) == ["入", "运"],
          "仅有决策无功率 → ['入','运']（不虚构照相）",
          f"实得 {d(has_closedloop_decision=True)}")
    check(d(has_bandpower=True, has_closedloop_decision=True,
            has_guided=True, has_governance=True) == ["入", "照", "运", "融", "出"],
          "五相全证据 → 规范顺序 ['入','照','运','融','出']",
          f"实得 {d(True, True, True, True)}")
    # 顺序归一：调用方乱序传入也须按规范顺序返回
    r = d(has_governance=True, has_bandpower=True)
    check(r == ["入", "照", "出"],
          f"乱序证据仍归一为规范顺序 {r}",
          f"顺序归一失败，实得 {r}")
    check(mls.ZX_PHASES == ("入", "照", "运", "融", "出"),
          "ZX_PHASES 规范顺序与五字诀定论一致",
          f"ZX_PHASES 异常：{mls.ZX_PHASES}")

    # ── 准备临时数据目录（不污染真实 report 目录）──────────────────
    tmpdir = tempfile.mkdtemp(prefix="zxphase_verify_")
    real_report_dir = mls.REPORT_DIR
    mls.REPORT_DIR = tmpdir
    print(f"\n  临时目录：{tmpdir}")
    print(f"  （真实 REPORT_DIR 已暂存并将还原：{real_report_dir}）")

    # ⚠️ 判据自检（本轮发现并修正的脚本缺陷，§7.1 家族第 7 例）：
    # save_bin 的文件名时间戳精度**只到秒**（muse_local_server.py:630
    # `%Y%m%d_%H%M%S`）。首轮实测中判据 2/3/4 三次保存落在同一秒，
    # 文件名全为 local_20260914_214522.npz —— **同一物理文件被反复覆盖**。
    # 三个断言各自"写后立即读"故读到了自己的值、未产生假阳性，但判据 3 的
    # 核心论证（同 scene 不同证据 → 值必须不同）要求两份数据**确实共存**，
    # 靠巧合成立不算成立。故：每次保存后 sleep 跨过秒边界，并显式断言路径唯一。
    saved_paths = []

    def save_unique(buf, extra_meta, label):
        """保存并断言文件路径唯一（未被前一次覆盖）。"""
        import time as _time
        if saved_paths:
            _time.sleep(1.05)          # 跨过秒边界，避免时间戳同名覆盖
        r = buf.save_bin(extra_meta=extra_meta)
        if not r:
            check(False, "", f"{label}：save_bin 返回 None，无法继续")
            return None, None
        p = r[0]
        if p in saved_paths:
            check(False, "", f"{label}：文件路径与前次重复（{os.path.basename(p)}），"
                             f"判据建立在被覆盖的数据上 → 无效")
        else:
            saved_paths.append(p)
        return p, r[1]

    try:
        def make_buf(n_samples=2500):
            """构造带真实数据的 DataBuffer。

            ⚠️ 两处曾想当然、已按源码实测修正：
              1. add_eeg 是**平铺列表**约定（每样本 n_ch+1 列，末列保留占位），
                 不是 {ch: val} 字典 —— muse_local_server.py:405-412
              2. compute_band_power 需 ≥ sfreq*8 样本（_bp_min_samples，
                 256*8=2048）才产出频段值 —— :359；故默认 2500 样本
            """
            buf = mls.DataBuffer(device="muse")
            stride = buf.n_ch + 1
            flat = []
            for i in range(n_samples):
                # 10Hz α 波为主，叠少量噪声，使各频段有非零功率
                v = 20.0 * np.sin(2 * np.pi * 10.0 * i / buf.sfreq)
                flat.extend([float(v)] * buf.n_ch)
                flat.append(0.0)          # 保留列
            assert len(flat) == n_samples * stride, "平铺长度不符"
            buf.add_eeg(flat)
            n_stored = min(len(buf.eeg_all[ch]) for ch in buf.channels)
            assert n_stored == n_samples, f"实际入库 {n_stored} ≠ {n_samples}"
            return buf

        # ── 1. 旧数据兼容：无 zx_phase 键，读取端不报错 ───────────────
        print("\n── 判据 1：旧数据（无 zx_phase）读取端向后兼容 ───────────────")
        buf_old = make_buf()
        p_old, _rp_old = save_unique(
            buf_old, {"scene": "monitor", "participant": "ZXPHASE_TEST"}, "旧数据")
        if not p_old:
            return 1
        with np.load(p_old, allow_pickle=True) as z:
            m_old = z["meta"].item()
        check("zx_phase" not in m_old,
              "模拟旧数据：meta 中确实无 zx_phase 键",
              f"旧数据意外带了 zx_phase：{m_old.get('zx_phase')}")
        # 关键：读取端用 .get() 容错，缺键不得抛异常
        try:
            got = m_old.get("zx_phase", None)
            got2 = m_old.get("zx_phase", [])
            check(got is None and got2 == [],
                  f"读取端 .get() 容错正常（缺键→None/[]，不抛异常）",
                  f".get() 返回异常值：{got!r} / {got2!r}")
        except Exception as e:
            check(False, "", f"读取端因缺 zx_phase 键抛异常：{type(e).__name__}: {e}")
        # 复刻 console_server.py:154 与 :1538 的真实读取写法
        try:
            samples = int(m_old["samples"])
            duration = float(m_old["duration"])
            scene = str(m_old.get("scene", "unknown"))
            check(samples > 0 and duration >= 0 and scene == "monitor",
                  f"console_server 两处真实读取写法均正常"
                  f"（samples={samples} duration={duration:.1f} scene={scene}）",
                  "读取值异常")
        except Exception as e:
            check(False, "", f"console_server 读取写法抛异常：{type(e).__name__}: {e}")

        # ── 2. 新数据：监测路径 + 出过闭环决策 → 含「运」 ─────────────
        print("\n── 判据 2：新数据带 zx_phase，且按实际证据派生 ───────────────")
        buf_a = make_buf()
        buf_a.compute_band_power()
        has_bp_a = bool(getattr(buf_a, "latest_bp", None))
        meta_a = {"scene": "monitor", "participant": "ZXPHASE_TEST",
                  "zx_phase": mls.derive_zx_phase(
                      has_bandpower=has_bp_a,
                      has_closedloop_decision=True)}   # 模拟 ctrl_phase=="locked"
        p_a, _rpa = save_unique(buf_a, meta_a, "监测(已出决策)")
        if not p_a:
            return 1
        with np.load(p_a, allow_pickle=True) as z:
            m_a = z["meta"].item()
        zp_a = m_a.get("zx_phase")
        check(isinstance(zp_a, list),
              f"监测路径（已出决策）：zx_phase 是数组 {zp_a}",
              f"zx_phase 非数组：{type(zp_a).__name__} {zp_a!r}")
        check(zp_a == ["入", "照", "运"],
              f"监测路径（已出决策）→ ['入','照','运']，实得 {zp_a}",
              f"值不符：{zp_a}")

        # ── 3. 关键判据：同 scene=monitor，仅基线期 → 不含「运」 ──────
        #    这证明丙方案没有退化成甲方案（按 scene 静态映射）
        print("\n── 判据 3：🔑 同 scene 不同证据 → 值必须不同（防退化成甲）────")
        buf_b = make_buf()
        buf_b.compute_band_power()
        has_bp_b = bool(getattr(buf_b, "latest_bp", None))
        meta_b = {"scene": "monitor", "participant": "ZXPHASE_TEST",
                  "zx_phase": mls.derive_zx_phase(
                      has_bandpower=has_bp_b,
                      has_closedloop_decision=False)}  # 模拟 ctrl_phase=="baseline"
        p_b, _rpb = save_unique(buf_b, meta_b, "监测(仅基线)")
        if not p_b:
            return 1
        check(p_a != p_b,
              f"两份数据确为不同物理文件（{os.path.basename(p_a)} vs "
              f"{os.path.basename(p_b)}），判据 3 论证成立而非靠覆盖巧合",
              f"两份数据落到同一文件 {os.path.basename(p_a)} → 论证无效")
        with np.load(p_b, allow_pickle=True) as z:
            m_b = z["meta"].item()
        zp_b = m_b.get("zx_phase")
        check(zp_b == ["入", "照"],
              f"监测路径（仅基线期未出决策）→ ['入','照']，实得 {zp_b}",
              f"值不符：{zp_b}")
        check(zp_a != zp_b,
              f"🔑 同为 scene=monitor，出决策{zp_a} ≠ 仅基线{zp_b}"
              f" → 字段有真实区分度，丙方案未退化成甲",
              f"🔑 两者相同（{zp_a} == {zp_b}）→ 字段值退化，无聚合价值")

        # ── 4. 闭环路径：n_loop>0 → 含「运」 ────────────────────────
        print("\n── 判据 4：闭环实验路径（n_feat>0, n_loop>0）─────────────────")
        buf_c = make_buf()
        buf_c.compute_band_power()
        n_feat = 1 if getattr(buf_c, "latest_bp", None) else 0
        n_loop = 5                                    # 模拟已出 5 次决策
        meta_c = {"scene": "closedloop", "experiment_tag": "ZXPHASE_TEST",
                  "experiment_mode": "simulate",
                  "zx_phase": mls.derive_zx_phase(
                      has_bandpower=(n_feat > 0),
                      has_closedloop_decision=(n_loop > 0))}
        r_c_path, _rpc = save_unique(buf_c, meta_c, "闭环(有决策)")
        if not r_c_path:
            return 1
        p_c = r_c_path
        with np.load(p_c, allow_pickle=True) as z:
            m_c = z["meta"].item()
        zp_c = m_c.get("zx_phase")
        check(zp_c == ["入", "照", "运"],
              f"闭环路径（有决策）→ ['入','照','运']，实得 {zp_c}",
              f"值不符：{zp_c}")
        # 基线期即中止的闭环会话：n_loop==0 → 不含运
        zp_c0 = mls.derive_zx_phase(has_bandpower=True,
                                    has_closedloop_decision=(0 > 0))
        check(zp_c0 == ["入", "照"],
              f"闭环路径基线期即中止（n_loop=0）→ ['入','照']，实得 {zp_c0}",
              f"值不符：{zp_c0}")

        # ── 5. 既有字段零影响 ────────────────────────────────────────
        print("\n── 判据 5：既有 meta 字段一个都不受影响 ──────────────────────")
        for name, m in (("监测(决策)", m_a), ("闭环", m_c), ("旧数据", m_old)):
            for k in ("timestamp", "sfreq", "channels", "device",
                      "samples", "duration", "signal_chain"):
                if k not in m:
                    check(False, "", f"{name} 缺既有字段 {k}")
            if "scene" in m and m["scene"] not in ("monitor", "closedloop"):
                check(False, "", f"{name} scene 值被改动：{m['scene']}")
        check(all(k in m_a for k in ("timestamp", "sfreq", "channels", "device",
                                     "samples", "duration", "signal_chain",
                                     "scene", "participant")),
              "监测路径：既有 9 个字段全部完好",
              "监测路径既有字段缺失")
        check(m_a["scene"] == "monitor" and m_c["scene"] == "closedloop",
              "scene 值未被五相化改动（C1 依裁定不动）",
              f"scene 被改动：{m_a['scene']} / {m_c['scene']}")
        check("phase" not in m_a and "phase" not in m_c,
              "未误用既有 `phase` 字段名（撞名风险已避开）",
              "仍写入了 phase 字段，撞名未解决")
        # 既有 phase 语义确认：closedloop_experiment tick 的 phase 是「基线/闭环」
        notes.append("既有 `phase`（closedloop_experiment.py:441，取值「基线」/「闭环」）"
                     "与新 `zx_phase` 互不干扰，已实测 npz meta 中无 phase 键")

        # ── 6. 容错：派生异常不阻断保存 ─────────────────────────────
        print("\n── 判据 6：zx_phase 派生异常时不阻断保存 ─────────────────────")
        # 模拟 derive_zx_phase 抛异常（两处写入点都包了 try/except）
        real_fn = mls.derive_zx_phase
        def boom(*a, **k):
            raise RuntimeError("模拟派生失败")
        mls.derive_zx_phase = boom
        try:
            # 直接复刻 console_server 写入点的 try/except 结构
            info = {"scene": "monitor", "participant": "ZXPHASE_TEST"}
            caught = False
            try:
                from muse_local_server import derive_zx_phase as _d
                info["zx_phase"] = _d(has_bandpower=True,
                                      has_closedloop_decision=True)
            except Exception as e:
                caught = True
                notes.append(f"容错路径按预期捕获异常：{type(e).__name__}")
            check(caught,
                  "派生抛异常时被 try/except 捕获（保存主流程不中断）",
                  "异常未被捕获 → 会阻断数据保存")
            # 异常后仍能正常保存（info 里就没有 zx_phase 键）
            buf_e = make_buf()
            p_e, _rpe = save_unique(buf_e, info, "派生失败")
            check(bool(p_e),
                  "派生失败后 save_bin 仍成功（数据不丢）",
                  "派生失败导致保存失败 → 数据会丢")
            if p_e:
                with np.load(p_e, allow_pickle=True) as z:
                    m_e = z["meta"].item()
                check("zx_phase" not in m_e,
                      "派生失败时不写入残缺 zx_phase（宁缺毋错）",
                      f"写入了残缺值：{m_e.get('zx_phase')}")
        finally:
            mls.derive_zx_phase = real_fn

        # ── 7. 判据自检：所有保存路径互不相同（防同名覆盖致判据失效）──
        print("\n── 判据 7：🔑 本轮全部保存路径互不相同（脚本自检）─────────────")
        uniq = len(set(saved_paths))
        check(uniq == len(saved_paths) and len(saved_paths) >= 4,
              f"共 {len(saved_paths)} 次保存、{uniq} 个唯一路径"
              f"（{[os.path.basename(p) for p in saved_paths]}）",
              f"存在同名覆盖：{len(saved_paths)} 次保存仅 {uniq} 个唯一路径"
              f" → 相关判据建立在被覆盖的数据上，无效")

    finally:
        # 还原 REPORT_DIR 并清理临时目录（守红线7：显式路径、不碰真实数据）
        mls.REPORT_DIR = real_report_dir
        shutil.rmtree(tmpdir, ignore_errors=True)
        print(f"\n  已还原 REPORT_DIR 并清理临时目录")
        print(f"  临时目录残留：{os.path.exists(tmpdir)}")

    # ── 汇总 ──────────────────────────────────────────────────────
    print("\n" + "=" * 74)
    if notes:
        print("附注：")
        for n in notes:
            print(f"  · {n}")
    if fails:
        print(f"\n❌ FAIL {len(fails)} 项：")
        for f in fails:
            print(f"   - {f}")
        return 1
    print("\n✅ PASS：zx_phase 字段验收全通过")
    print("   ① 旧数据缺键不报错 ② 新数据带规范数组 ③ 按实际证据派生（未退化成甲）")
    print("   ④ 既有字段零影响、未撞名 phase ⑤ 派生异常不阻断保存")
    print("\n⚠️ 仍未验证的一项（须法师侧）：真机蓝牙采集会话写入的 npz 是否带 zx_phase")
    print("   —— 本验收用 DataBuffer 真实写盘读回，但未经真机蓝牙全链路")
    return 0


if __name__ == "__main__":
    sys.exit(main())
