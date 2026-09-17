"""B2 映射 v2 标定与验证（2026-09-08）.

vr_feedback.html 顶部 CAL 常数的来源脚本，可复算、可复查。

背景：v1（绝对 dB 线性映射）被 09-08 凌晨法师 42 分钟真机会话证伪——
Alpha/Theta dB 双双被总功率（伪迹幅度）劫持，corr(α,θ)=+0.98，
画面退化为"幅度镜子"，无法区分定/躁/沉；v1 theta 上限远低于实测 p95，
80% 帧顶格。v2 改用对总功率不敏感的相对量：
    S.a  ← relα = Alpha功率 / 五频段总功率      （安定度）
    S.th ← log10(θ/β) = (theta_dB - beta_dB)/10 （沉掉轴）

标定：两份真机数据合并 p5/p95，09-06 合格 baseline 帧×3 加权，
防止重伪迹的 09-08 test 会话主导区间。

数据边界：只读已入库/待处置 npz；本脚本不写数据工厂、不联网。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
for p in (str(HERE), str(HERE / "muse-cloud-server")):
    if p not in sys.path:
        sys.path.insert(0, p)

import report_generator as rg                          # noqa: E402

SF = 256.0
STEP = int(2.0 * SF)                    # 线上 2 秒节流口径
NSEC = int(10 * SF)                     # 10 秒窗（BP_EPOCH_SAMPLES）
WEIGHT_A = 3                            # A 帧加权倍数

DATASETS = {
    "A_baseline_0906": ("report/local_20260906_011204.npz",
                        "合格 baseline，267.6s，contact_quality=good"),
    "B_test_0908": ("report/local_20260908_023101.npz",
                    "法师 42 分钟 test 会话（重伪迹，不入库），2526.7s"),
}


def frames(path: Path) -> list[tuple]:
    """按线上口径走窗，返回 (t_sec, rel_alpha, log10_tb, total_pow, noisy)。"""
    eeg = np.asarray(np.load(path, allow_pickle=True)["eeg"], dtype=np.float64)
    n_ch = eeg.shape[1]
    out = []
    i = 0
    while i + NSEC <= eeg.shape[0]:
        bp = rg.compute_band_power_chunk(eeg[i:i + NSEC], SF)
        if bp and all(bp["db"][b].shape[0] == n_ch for b in rg.BANDS):
            m = {b: float(np.mean(bp["db"][b])) for b in rg.BANDS}
            pow5 = {b: 10 ** (m[b] / 10.0) for b in rg.BANDS}
            total = sum(pow5.values())
            out.append((i / SF,
                        pow5["Alpha"] / total,
                        (m["Theta"] - m["Beta"]) / 10.0,
                        total,
                        bool(np.all(bp["noise"]))))
        i += STEP
    return out


def main() -> int:
    stats = {}
    pool_ra, pool_lt = [], []
    for key, (rel, desc) in DATASETS.items():
        fr = frames(HERE / rel)
        nz = [f for f in fr if not f[4]]
        ra = np.array([f[1] for f in nz])
        lt = np.array([f[2] for f in nz])
        tot = np.log10([f[3] for f in nz])
        stats[key] = {
            "desc": desc,
            "frames": len(fr), "non_noise": len(nz),
            "rel_alpha": {"p5": round(float(np.percentile(ra, 5)), 4),
                          "median": round(float(np.median(ra)), 4),
                          "p95": round(float(np.percentile(ra, 95)), 4)},
            "log10_theta_beta": {"p5": round(float(np.percentile(lt, 5)), 4),
                                 "median": round(float(np.median(lt)), 4),
                                 "p95": round(float(np.percentile(lt, 95)), 4)},
            "corr_relA_vs_logTotal": round(float(np.corrcoef(ra, tot)[0, 1]), 3),
            "corr_logTB_vs_logTotal": round(float(np.corrcoef(lt, tot)[0, 1]), 3),
        }
        # A 加权防伪迹主导
        reps = WEIGHT_A if key.startswith("A") else 1
        pool_ra.append(np.repeat(ra, reps))
        pool_lt.append(np.repeat(lt, reps))

    RA = np.concatenate(pool_ra)
    LT = np.concatenate(pool_lt)
    ra_lo, ra_hi = float(np.percentile(RA, 5)), float(np.percentile(RA, 95))
    lt_lo, lt_hi = float(np.percentile(LT, 5)), float(np.percentile(LT, 95))

    def c01(x, lo, sp):
        return np.clip((x - lo) / sp, 0.0, 1.0)

    span_ra = ra_hi - ra_lo
    span_lt = lt_hi - lt_lo
    # 分数据集验证解耦效果与新参数下的响应
    for key in DATASETS:
        fr = [f for f in frames(HERE / DATASETS[key][0]) if not f[4]]
        a = c01(np.array([f[1] for f in fr]), ra_lo, span_ra)
        t = c01(np.array([f[2] for f in fr]), lt_lo, span_lt)
        stats[key]["v2"] = {
            "S_a": {"mean": round(float(a.mean()), 3),
                    "min": round(float(a.min()), 3), "max": round(float(a.max()), 3)},
            "S_th": {"mean": round(float(t.mean()), 3),
                     "min": round(float(t.min()), 3), "max": round(float(t.max()), 3)},
            "corr_a_vs_th": round(float(np.corrcoef(a, t)[0, 1]), 3),
            "a_sat_pct": round(float(((a <= 0) | (a >= 1)).mean() * 100), 1),
            "th_sat_pct": round(float(((t <= 0) | (t >= 1)).mean() * 100), 1),
        }

    result = {
        "mapping": "v2",
        "date": "2026-09-08",
        "formula": {
            "S_a": "relα = Alpha功率/(Δ+Θ+Α+Β+Γ功率)，线性映射 [%.4f, %.4f]" % (ra_lo, ra_hi),
            "S_th": "log10(θ/β)=(theta_dB−beta_dB)/10，线性映射 [%.4f, %.4f]" % (lt_lo, lt_hi),
        },
        "CAL_constants_for_page": {
            "relALo": round(ra_lo, 4), "relASpan": round(span_ra, 4),
            "ltBLo": round(lt_lo, 4), "ltBSpan": round(span_lt, 4),
        },
        "weighting": f"datasets A frames x{WEIGHT_A}（防伪迹会话主导标定）",
        "corr_relA_vs_logTB_pooled": round(float(np.corrcoef(RA, LT)[0, 1]), 3),
        "v1_problem_reference": "corr(α_dB,θ_dB)=+0.98（总功率劫持）；v1 θ饱和帧80.2%（B会话）",
        "stats": stats,
        "semantics_pending": "方向语义（安定=亮；昏沉=暗而快；躁动=暗而慢）待法师审定",
    }
    out = HERE / "report" / "b2_mapping_v2.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\n已存: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
