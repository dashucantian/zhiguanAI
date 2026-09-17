"""第一重分析配图：PSD、时间演化、S.a/S.th 分布、CAL 标定映射诊断。"""
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.signal import welch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyse_eeg as A  # noqa: E402

OUT = A.OUT
FIG = A.FIG
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

CACHE = os.path.join(OUT, "series.npz")


def build_series():
    """逐 epoch 序列（滤波后 + 原始），缓存避免重复计算。"""
    if os.path.exists(CACHE):
        z = np.load(CACHE, allow_pickle=True)
        return {k: z[k] for k in z.files}
    out = {}
    for tag, name, label in A.SESSIONS:
        d = A.load_npz(name)
        sfreq, eeg, raw = d["sfreq"], d["eeg"], d["raw"]
        for suffix, arr in [("", eeg), ("_raw", raw)]:
            if arr is None:
                continue
            ts, ra, lt, sa, sth, dba, dbt, dbb = [], [], [], [], [], [], [], []
            noise = []
            for k, t, blk in A.epoch_iter(arr, sfreq):
                r = A.analyse_block(blk, sfreq)
                if not r:
                    continue
                ts.append(t); ra.append(r["rel_alpha"]); lt.append(r["lt"])
                sa.append(r["S_a"]); sth.append(r["S_th"])
                dba.append(r["db"]["Alpha"]); dbt.append(r["db"]["Theta"])
                dbb.append(r["db"]["Beta"]); noise.append(r["noise"])
            p = f"{tag}{suffix}"
            out[f"{p}_t"] = np.array(ts); out[f"{p}_ra"] = np.array(ra)
            out[f"{p}_lt"] = np.array(lt); out[f"{p}_sa"] = np.array(sa)
            out[f"{p}_sth"] = np.array(sth); out[f"{p}_dba"] = np.array(dba)
            out[f"{p}_dbt"] = np.array(dbt); out[f"{p}_dbb"] = np.array(dbb)
            out[f"{p}_noise"] = np.array(noise)
        # 全程平均 PSD（滤波后 vs 原始）
        for suffix, arr in [("", eeg), ("_raw", raw)]:
            if arr is None:
                continue
            f, p_ = welch(arr, sfreq, nperseg=int(sfreq), axis=0)
            out[f"{tag}{suffix}_psdf"] = f
            out[f"{tag}{suffix}_psd"] = 10 * np.log10(np.maximum(p_.mean(axis=1), 1e-12))
    np.savez_compressed(CACHE, **out)
    print("序列已缓存 series.npz")
    return out


def fig_psd(S):
    fig, axes = plt.subplots(1, 2, figsize=(15, 5.2))
    for ax, tag, title in [(axes[0], "121639", "会话A（22分钟）"),
                           (axes[1], "130105", "会话B（42分钟）")]:
        ax.plot(S[f"{tag}_psdf"], S[f"{tag}_psd"], label="滤波后 1–40Hz（实际驱动 VR）",
                color="#2b8a3e", lw=1.8)
        ax.plot(S[f"{tag}_raw_psdf"], S[f"{tag}_raw_psd"], label="原始未滤波（eeg_pre_filter）",
                color="#c92a2a", lw=1.4, alpha=.75)
        for lo, hi, nm, c in [(0.5, 4, "δ", "#888"), (4, 8, "θ", "#f0a500"),
                              (8, 12, "α", "#2b8a3e"), (12, 30, "β", "#c92a2a"),
                              (30, 45, "γ", "#8e44ad")]:
            ax.axvspan(lo, hi, color=c, alpha=.07)
            ax.text((lo + hi) / 2, ax.get_ylim()[1] * .98, nm, ha="center", va="top",
                    fontsize=11, color=c)
        ax.axvline(1, color="k", ls=":", lw=1)
        ax.axvline(40, color="k", ls=":", lw=1)
        ax.axvline(50, color="#e67700", ls="--", lw=1)
        ax.text(50, ax.get_ylim()[0], " 50Hz工频", color="#e67700", fontsize=8, va="bottom")
        ax.set_xlim(0, 45); ax.set_xlabel("频率 (Hz)"); ax.set_ylabel("功率 (dB re μV²/Hz)")
        ax.set_title(f"{title} 全程平均 PSD", fontsize=12)
        ax.legend(fontsize=9, loc="upper right"); ax.grid(alpha=.25)
    fig.suptitle("图1  滤波前后 PSD 对照：1Hz 高通削掉次慢波、40Hz 低通截断 Gamma 与工频",
                 fontsize=13, y=1.0)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "图1_PSD滤波前后对照.png"), dpi=130, bbox_inches="tight")
    plt.close(fig)
    print("图1 完成")


def fig_timeseries(S):
    fig, axes = plt.subplots(4, 1, figsize=(15, 12), sharex=False)
    specs = [("ra", "相对 Alpha 占比（驱动 S.a 的原料）", "#2b8a3e"),
             ("lt", "log10(θ/β) 沉掉轴（驱动 S.th 的原料）", "#1864ab"),
             ("sa", "S.a 安定度（VR 光球亮度/水波幅度实际输入）", "#e8590c"),
             ("sth", "S.th 沉掉轴（VR 雾/粒子密度实际输入）", "#862e9c")]
    for i, (key, title, color) in enumerate(specs):
        ax = axes[i]
        for tag, name, label in A.SESSIONS:
            t = S[f"{tag}_t"] / 60.0
            v = S[f"{tag}_{key}"]
            nz = S[f"{tag}_noise"]
            ax.plot(t[nz], v[nz], ".", color="#adb5bd", ms=3, alpha=.5,
                    label=("噪声 epoch（剔除）" if i == 0 else None))
            ax.plot(t[~nz], v[~nz], "-", color=color, lw=.9, alpha=.85, label=label)
            med = np.median(v[~nz])
            ax.axhline(med, color=color, ls="--", lw=1, alpha=.6)
            ax.text(.995, med, f" 中位 {med:.3f}", color=color, fontsize=8,
                    transform=ax.get_yaxis_transform(), ha="right", va="bottom")
        if key in ("sa", "sth"):
            ax.set_ylim(-0.05, 1.05)
            ax.axhspan(0, .2, color="#c92a2a", alpha=.06)
            ax.text(.005, .1, "视觉死区（几乎无变化）", color="#c92a2a", fontsize=8, va="center")
        ax.set_ylabel(title.split("（")[0], fontsize=10)
        ax.set_title(title, fontsize=10.5, loc="left")
        ax.grid(alpha=.25); ax.legend(fontsize=8, loc="upper right")
        ax.set_xlabel("时间（分钟）", fontsize=9)
    fig.suptitle("图2  两次采集的时间演化：S.a 长期贴地是「亮度变化不明显」的直接原因",
                 fontsize=13, y=1.0)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "图2_时间演化.png"), dpi=130, bbox_inches="tight")
    plt.close(fig)
    print("图2 完成")


def fig_cal(S, cal):
    """CAL 标定诊断：实测数据落在 0–1 量程的哪里，以及三种重标定方案对比。"""
    ra_all = np.concatenate([S[f"{t}_ra"][~S[f"{t}_noise"]] for t, _, _ in A.SESSIONS])
    lt_all = np.concatenate([S[f"{t}_lt"][~S[f"{t}_noise"]] for t, _, _ in A.SESSIONS])

    plans = {
        "当前 CAL（V1模板在用）": (cal["relALo"], cal["relASpan"]),
        "建议① p5~p95": (float(np.percentile(ra_all, 5)),
                       float(np.percentile(ra_all, 95) - np.percentile(ra_all, 5))),
        "建议② q1~q3（最灵敏）": (float(np.percentile(ra_all, 25)),
                            float(np.percentile(ra_all, 75) - np.percentile(ra_all, 25))),
    }
    fig, axes = plt.subplots(1, 2, figsize=(15, 5.6))

    ax = axes[0]
    ax.hist(ra_all, bins=60, color="#2b8a3e", alpha=.55, density=True)
    for nm, (lo, span) in plans.items():
        hi = lo + span
        med = np.median(ra_all)
        sm = np.clip((med - lo) / span, 0, 1)
        ax.axvline(lo, color="#c92a2a", ls="--", lw=1.2)
        ax.axvline(hi, color="#c92a2a", ls="--", lw=1.2)
        ax.annotate(f"{nm}\n区间[{lo:.4f},{hi:.4f}]\n中位→S.a={sm:.2f}",
                    xy=(lo, ax.get_ylim()[1] * .92), fontsize=8.5, color="#c92a2a",
                    ha="left", va="top")
    ax.axvline(np.median(ra_all), color="k", lw=1.6)
    ax.set_xlabel("相对 Alpha 占比 relα"); ax.set_ylabel("密度")
    ax.set_title("relα 实测分布 vs CAL 映射区间", fontsize=11)
    ax.grid(alpha=.25)

    ax = axes[1]
    for nm, (lo, span) in plans.items():
        mapped = np.clip((ra_all - lo) / span, 0, 1)
        ax.hist(mapped, bins=40, alpha=.45, label=f"{nm}  中位={np.median(mapped):.2f}",
                density=True)
    ax.axvline(0, color="k", lw=1); ax.axvline(1, color="k", lw=1)
    ax.set_xlabel("映射后 S.a（0–1，VR 实际吃到的值）"); ax.set_ylabel("密度")
    ax.set_title("三种标定下 S.a 的分布：当前标定把数据压在左下角", fontsize=11)
    ax.legend(fontsize=9); ax.grid(alpha=.25)
    fig.suptitle("图3  CAL 标定诊断与重标定方案对比", fontsize=13, y=1.0)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "图3_CAL标定诊断.png"), dpi=130, bbox_inches="tight")
    plt.close(fig)
    print("图3 完成")

    # S.th 同法
    plans_t = {"当前 CAL": (cal["ltBLo"], cal["ltBSpan"]),
               "建议 p5~p95": (float(np.percentile(lt_all, 5)),
                            float(np.percentile(lt_all, 95) - np.percentile(lt_all, 5)))}
    fig, ax = plt.subplots(figsize=(9, 5))
    for nm, (lo, span) in plans_t.items():
        mapped = np.clip((lt_all - lo) / span, 0, 1)
        ax.hist(mapped, bins=40, alpha=.45, density=True,
                label=f"{nm} [{lo:+.3f},{lo+span:+.3f}]  中位={np.median(mapped):.2f} "
                      f"IQR={np.percentile(mapped,25):.2f}~{np.percentile(mapped,75):.2f}")
    ax.set_xlabel("S.th（0–1）"); ax.set_ylabel("密度")
    ax.set_title("图4  沉掉轴 S.th 标定诊断（当前标定已较合理，分布居中）", fontsize=11.5)
    ax.legend(fontsize=9); ax.grid(alpha=.25)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "图4_Sth标定诊断.png"), dpi=130, bbox_inches="tight")
    plt.close(fig)
    print("图4 完成")


def fig_bands(S):
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    bands = [("Alpha", "#2b8a3e"), ("Theta", "#f0a500"), ("Beta", "#c92a2a")]
    for ax, tag, title in [(axes[0], "121639", "会话A（22分钟）"),
                           (axes[1], "130105", "会话B（42分钟）")]:
        t = S[f"{tag}_t"] / 60.0
        nz = ~S[f"{tag}_noise"]
        for b, c in bands:
            key = {"Alpha": "dba", "Theta": "dbt", "Beta": "dbb"}[b]
            ax.plot(t[nz], S[f"{tag}_{key}"][nz], lw=.8, alpha=.8, color=c, label=b)
        ax.set_xlabel("时间（分钟）"); ax.set_ylabel("功率 (dB)")
        ax.set_title(f"{title} 三频段绝对功率", fontsize=11.5)
        ax.legend(fontsize=9); ax.grid(alpha=.25)
    fig.suptitle("图5  Alpha/Theta/Beta 绝对功率时间演化", fontsize=13, y=1.0)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "图5_三频段时间演化.png"), dpi=130, bbox_inches="tight")
    plt.close(fig)
    print("图5 完成")


if __name__ == "__main__":
    S = build_series()
    cal = A.CAL
    fig_psd(S)
    fig_timeseries(S)
    fig_cal(S, cal)
    fig_bands(S)
    print("\n全部图表完成 →", FIG)
