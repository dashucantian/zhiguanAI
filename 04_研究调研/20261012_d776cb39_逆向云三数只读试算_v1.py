# -*- coding: utf-8 -*-
"""
5.3 只读离线试算：逆向云三数（Ex/En/He）在止观AI现成特征上的适配度实测
窗别：W3｜人机建构｜d776cb39（AI-020）　日期：2026-10-12
依据：法师 10-11 给「5.3 只读离线试算开工号」；W3 协调窗 10-12 15:4x 开工令转达

硬界（越线即停）：
  · 只读：不写数据根 D:\\Project\\Zen-EEG，不跑入库，不改 qc_pipeline／congci_pipeline
  · 产物只落本窗名下件（04_研究调研／己档）
  · 不为跑出好看的数调参；跑成什么样报什么样，包括"假设不成立"
护栏（本窗件三 §1.6 已定三条）：
  ①不用"样本均值当 Ex、一阶绝对中心矩当 En"的经典公式出结论——本脚本把经典版与四阶矩版**并列跑**，
    正是为了把两版的差实测出来，而非择一好看者
  ②He 出现无解（var < En²）时如实报"退化为无厚度云"，不硬造数
  ③三数只作档案特征描述，不进判定链（本脚本无任何判定输出）
"""
import glob, json, math, os, re, sys, datetime
import numpy as np

ROOT = r"D:/Project/Zen-EEG"
EPS = 1e-12


def sbct_1stm(a):
    """经典逆向云（一阶绝对中心矩）。逐式来源：本窗件三 §1.6（博客转录，标丙级）。
       En = mean(|A-Ex|)*sqrt(pi/2) ; He = sqrt(var(A) - En^2)"""
    ex = float(np.mean(a))
    en = float(np.mean(np.abs(a - ex))) * math.sqrt(math.pi / 2.0)
    var = float(np.var(a))
    inner = var - en * en
    if inner < -EPS:
        return ex, en, None, f"无解（var={var:.4g} < En^2={en*en:.4g}）"
    return ex, en, math.sqrt(max(inner, 0.0)), ("退化为 0（无厚度云）" if inner <= EPS else "")


def sbct_4stm(a):
    """四阶矩版。En = ((9*S2^2 - mu4)/6)^(1/4) ; He = sqrt(S2 - En^2)（同样可能无解）"""
    s2 = float(np.var(a))
    mu4 = float(np.mean((a - np.mean(a)) ** 4))
    inner_en = (9.0 * s2 * s2 - mu4) / 6.0
    if inner_en < -EPS:
        return None, None, None, f"En 无解（9*S2^2-mu4<0）"
    en = inner_en ** 0.25
    inner_he = s2 - en * en
    if inner_he < -EPS:
        return float(np.mean(a)), en, None, "He 无解（var < En^2）"
    return float(np.mean(a)), en, math.sqrt(max(inner_he, 0.0)), ("退化为 0（无厚度云）" if inner_he <= EPS else "")


def shape(a):
    """分布形态：偏度／超额峰度／有限区间（最大最小）／Jarque-Bera 卡方粗判"""
    n = len(a)
    m = float(np.mean(a))
    s = float(np.std(a))
    if s < EPS or n < 3:
        return dict(n=n, skew=None, exkurt=None, lo=None, hi=None, jb=None)
    skew = float(np.mean((a - m) ** 3) / s ** 3)
    kurt = float(np.mean((a - m) ** 4) / s ** 4) - 3.0
    jb = n / 6.0 * (skew * skew + kurt * kurt / 4.0)  # JB>5.99 ⇒ 5% 水平下拒绝正态
    return dict(n=n, skew=round(skew, 3), exkurt=round(kurt, 3),
                lo=round(float(np.min(a)), 4), hi=round(float(np.max(a)), 4),
                jb=round(jb, 2))


def band_ratio(x, sfreq, lo, hi, blo, bhi):
    """单窗带功率比：[lo,hi] 相对 [blo,bhi]，取 log2 便于对称化"""
    n = len(x)
    if n < 16:
        return float("nan")
    w = np.hanning(n)
    sp = np.abs(np.fft.rfft((x - np.mean(x)) * w)) ** 2
    fr = np.fft.rfftfreq(n, d=1.0 / sfreq)

    def bp(a, b):
        msk = (fr >= a) & (fr <= b)
        return float(sp[msk].sum()) if msk.any() else 0.0
    num, den = bp(lo, hi), bp(blo, bhi)
    if den <= EPS:
        return float("nan")
    return math.log2((num + EPS) / (den + EPS))


def window_features(eeg, sfreq, ch_names, win_s=10.0, step_s=5.0):
    """我方现行 QC 同参数：10 秒窗／5 秒步（qc_pipeline.py:41-42 只读引用）"""
    win = int(round(win_s * sfreq))
    stp = int(round(step_s * sfreq))
    if win < 16 or eeg.shape[0] < win:
        return {}
    out = {k: [] for k in ["alpha_rel", "abs_mean_uv", "std_uv", "maxabs_uv", "rms_uv"]}
    for ci in range(eeg.shape[1]):
        col = eeg[:, ci].astype(np.float64)
        for i in range(0, len(col) - win + 1, stp):
            w = col[i:i + win]
            out["alpha_rel"].append(band_ratio(w, sfreq, 8.0, 12.0, 1.0, 40.0))
            out["abs_mean_uv"].append(float(np.mean(np.abs(w))))
            out["std_uv"].append(float(np.std(w)))
            out["maxabs_uv"].append(float(np.max(np.abs(w))))
            out["rms_uv"].append(float(np.sqrt(np.mean(w ** 2))))
    return {k: np.asarray(v, dtype=np.float64) for k, v in out.items()}


def line(s=""):
    print(s, flush=True)


def g6(x):
    """None 安全的六位有效数打印；无解一律打「无解」，不静默跳过、不代拟数值"""
    return "无解" if x is None else ("%.6g" % x)


def main():
    line("=== 5.3 只读离线试算　启动时刻 %s ===" % datetime.datetime.now().isoformat(timespec="seconds"))
    line("数据根以只读方式打开；本脚本无任何写盘动作（结果由调用方捕获）")

    # ---------- 第一查：概念侧到底有没有可配对的样本（决定假设成不成立） ----------
    line("\n【一】概念侧（主观标注）可配对性")
    notes = sorted(glob.glob(f"{ROOT}/02_raw/*/session_note.txt"))
    pat = re.compile(r"^\s*(pre_state|post_state|contact_quality)\s*[:：]\s*(.*)$", re.M)
    tally = {"pre_state": {}, "post_state": {}, "contact_quality": {}}
    for p in notes:
        txt = open(p, encoding="utf-8", errors="replace").read()
        for k, v in pat.findall(txt):
            v = v.strip()
            kind = "unknown/未记录" if ("unknown" in v.lower()) else "有实值"
            tally[k][kind] = tally[k].get(kind, 0) + 1
        line("  %-26s %s" % (os.path.basename(os.path.dirname(p)),
                             " | ".join(f"{k}={dict(pat.findall(txt)).get(k,'<缺键>')[:26]}"
                                         for k in ["pre_state", "post_state", "contact_quality"])))
    line("  汇总：")
    for k in tally:
        line(f"    {k:<16} {tally[k]}")
    ann = glob.glob(f"{ROOT}/05_annotation/**", recursive=True)
    ann_files = [x for x in ann if os.path.isfile(x)]
    line(f"  `05_annotation/` 文件数＝{len(ann_files)}（{[os.path.basename(x) for x in ann_files]}）")

    # ---------- 第二查：会话级三数（n 极小，就是要看它多不稳） ----------
    line("\n【二】会话级特征 n=9 的逆向云三数（经典版 vs 四阶矩版并列，不择好看者）")
    qcs = []
    for p in sorted(glob.glob(f"{ROOT}/03_quality_control/*/qc.json")):
        try:
            qcs.append(json.load(open(p, encoding="utf-8")))
        except Exception as e:
            line(f"  读失败 {p}: {e}")
    for feat in ["clean_ratio", "effective_hz", "packet_loss_rate"]:
        vals = np.asarray([q[feat] for q in qcs if isinstance(q.get(feat), (int, float))], dtype=np.float64)
        if vals.size < 3:
            line(f"  {feat}: 有效值 {vals.size} 个 → 不足以算三数，如实报")
            continue
        e1, n1, h1, f1 = sbct_1stm(vals)
        e4, n4, h4, f4 = sbct_4stm(vals)
        sh = shape(vals)
        line(f"  {feat} (n={vals.size})")
        line(f"     经典一阶矩 Ex={e1:.5g} En={n1:.5g} He={h1 if h1 is None else round(h1,5)}  {f1}")
        line(f"     四阶矩　Ex={e4:.5g} En={n4 if n4 is None else round(n4,5)} He={h4 if h4 is None else round(h4,5)}  {f4}")
        line(f"     两版 En 相对差＝{abs((n1-n4)/n1):.1%}（n4 有效时）" if n4 else "     四阶矩版 En 无解")

    # ---------- 第三查：窗级大样本——真正考验云模型合身性 ----------
    line("\n【三】窗级特征（10s 窗／5s 步，与我方 QC 同参数）三数与形态实测")
    pool = {k: [] for k in ["alpha_rel", "abs_mean_uv", "std_uv", "maxabs_uv", "rms_uv"]}
    per_sess = []
    for p in sorted(glob.glob(f"{ROOT}/02_raw/*/eeg_raw.npz")):
        sid = os.path.basename(os.path.dirname(p))
        try:
            z = np.load(p, allow_pickle=True)
            eeg = z["eeg"]
            meta = z["meta"].item()
            sfreq = float(meta.get("sfreq", 256.0))
            chs = list(meta.get("channels", []))
        except Exception as e:
            line(f"  {sid} 读失败：{e}")
            continue
        if eeg.ndim != 2:
            line(f"  {sid} 形状异常 {eeg.shape}")
            continue
        feats = window_features(eeg, sfreq, chs)
        if not feats:
            line(f"  {sid} 窗数不足（样本 {eeg.shape[0]}）")
            continue
        nwin = len(feats["std_uv"])
        per_sess.append((sid, nwin, eeg.shape[1], sfreq))
        line(f"  {sid}: 窗数={nwin} 通道={eeg.shape[1]} sfreq={sfreq}")
        for k in pool:
            pool[k].extend(feats[k].tolist())

    line(f"  合计窗数（并所有坐所有通道）＝{len(pool['std_uv'])}")
    for k in ["alpha_rel", "abs_mean_uv", "std_uv", "maxabs_uv", "rms_uv"]:
        a = np.asarray(pool[k], dtype=np.float64)
        a = a[np.isfinite(a)]
        if a.size < 30:
            line(f"  {k}: 有限值仅 {a.size} 个，不算三数")
            continue
        e1, n1, h1, f1 = sbct_1stm(a)
        e4, n4, h4, f4 = sbct_4stm(a)
        sh = shape(a)
        line(f"  {k} (n={a.size}) 形态：偏度={sh['skew']} 超额峰度={sh['exkurt']} "
             f"界=[{sh['lo']},{sh['hi']}] JB={sh['jb']}（>5.99 即在 5% 水平拒绝正态）")
        line(f"     经典 Ex={g6(e1)} En={g6(n1)} He={g6(h1)} {f1}")
        line(f"     四阶 Ex={g6(e4)} En={g6(n4)} He={g6(h4)} {f4}")
        if n1 and n4:
            line(f"     ⇒ 两版 En 相对差＝{abs((n1 - n4) / n1):.1%}｜He/En 有一版无解＝{h1 is None or n4 is None or h4 is None}")

    line("\n=== 试算结束 %s ===" % datetime.datetime.now().isoformat(timespec="seconds"))
    line("本脚本未写任何文件、未调用入库、未修改任何判据；结论由执笔窗如实转录")


if __name__ == "__main__":
    main()
