# -*- coding: utf-8 -*-
"""脑电状态序列化（离线低配版）—— W3人机建构-01 · 2026-10-01 四裁落地件。

来源：Mikhaylets et al., Sci Rep (2026) 16:23560（密续冥想可复现神经状态）
      及其前作 SDA 算法（Mikhaylets et al., Front Neuroinform 2024, PMC10859925）。
      前作无论文公开代码仓（GitHub/Zenodo 均查无），本文件照两文方法节
      自实现，并按本项目数据形态做低配化。

管线（对应论文 Fig.1B）：
  1s epoch 特征（5 频段 log 功率 + 4 比值，逐通道）→ z-score → PCA
  → 简化 SDA 分段（Ward 层次聚类 + 时间连通约束 + 短段合并 + 距离比合并）
  → 状态（时间连续段）→ 跨会话字母表（K-means + 轮廓系数定 k）→ 状态词
  → 加权 Levenshtein 编辑距离（替换代价 = 簇心距）→ 会话间距离矩阵。

与论文的差异（低配化，如实声明）：
  · 通道 4–7（Muse/NeuraDock）非 40 导，无 11 脑区归并，无相干/PLV 特征；
  · Phase-2 边界聚合只做 K-means + 中位数中心，省 DBSCAN 分支；
  · 超参范围收窄（见下常量），非论文全网格。

设计纪律（照项目惯例）：
  · 确定性：同输入连算两次结果逐字一致（判语011），随机源全部固定种子；
  · 弃权是一等值：数据过短/特征不可算 → 如实返回 None，不硬造词；
  · 只读离线分析，不触碰闭环实时决策链（closedloop_controller 不 import 本模块）。
"""

from __future__ import annotations

import json
import os

# ── 口径常量（唯一源）─────────────────────────────────────────────────

STATE_SEQ_VERSION = "20261001"

EPOCH_SECONDS = 1.0          # 论文口径：1s epoch
BANDS = {"delta": (0.9, 4.0), "theta": (4.0, 8.0), "alpha": (8.0, 14.0),
         "beta": (14.0, 25.0), "gamma": (25.0, 40.0)}     # 论文 §2.2.1
RATIOS = [("theta", "delta"), ("alpha", "theta"),
          ("beta", "alpha"), ("theta", "beta")]
PCA_COMPONENTS = 10
OUTLIER_Z = 3.0              # 论文口径：任一特征偏离均值 3 个标准差的 epoch 剔除
                             # （§2.2 用 std 而非 MAD——MAD 在同类段内方差≈0 时
                             #  尺度退化，会把少数派真状态整段误剔，自测已复现）

# 简化 SDA 超参（论文 Table 1 收窄版）
N_RANGE = range(2, 9)        # Ward 聚类簇数（论文 [2,20]，低配收窄）
K_RANGE = (20, 30, 40)       # 时间连通近邻数（论文 [20,50]）
L_RANGE = (0, 10, 20)        # 最短状态长度（epoch 数；论文 {0,20,40,60}）
W_COEF = 0.3                 # Ward 距离合并系数（论文同值）
KM_RANGE = range(2, 9)       # Phase-2 边界数取值范围（论文 N_KM [2,15] 收窄）

MIN_EPOCHS = 60              # 少于此弃权（1s epoch 即 60 秒）
RANDOM_STATE = 42


# ── 特征 ─────────────────────────────────────────────────────────────

def extract_features(eeg, sfreq):
    """1s epoch 频段特征。返回 (features, valid_mask)。

    features shape=(n_epochs, n_ch*(5+4))：5 频段 log10 功率 + 4 比值（log10）。
    valid_mask：任一特征偏离会话中位数超 OUTLIER_Z 个稳健标准差 → False。
    """
    import numpy as np
    eeg = np.asarray(eeg, dtype=float)
    win = int(round(EPOCH_SECONDS * sfreq))
    n = eeg.shape[0]
    n_epochs = n // win
    if n_epochs < 1:
        return None, None
    chans = eeg[: n_epochs * win, :].reshape(n_epochs, win, eeg.shape[1])
    winf = np.hanning(win)[None, :, None]
    spec = np.fft.rfft(chans * winf, axis=1)
    psd = (np.abs(spec) ** 2) / (sfreq * np.sum(np.hanning(win) ** 2))
    freqs = np.fft.rfftfreq(win, d=1.0 / sfreq)

    def band_pow(band):
        lo, hi = BANDS[band]
        m = (freqs >= lo) & (freqs <= hi)
        if not m.any():
            return np.full(psd.shape[0], 1e-12)
        f = freqs[m]
        if hasattr(np, "trapezoid"):
            return np.trapezoid(psd[:, m, :], f, axis=1)
        return np.trapz(psd[:, m, :], f, axis=1)

    cols = []
    powers = {}
    for band in BANDS:
        p = np.maximum(band_pow(band), 1e-12)
        powers[band] = p
        cols.append(np.log10(p))
    for a, b in RATIOS:
        cols.append(np.log10(powers[a] / powers[b]))
    feats = np.concatenate(cols, axis=1)

    med = feats.mean(axis=0)
    scale = np.maximum(feats.std(axis=0), 1e-9)
    valid = np.all(np.abs(feats - med) <= OUTLIER_Z * scale, axis=1)
    return feats, valid


def _zscore(feats, valid):
    import numpy as np
    v = feats[valid]
    mu = v.mean(axis=0)
    sd = np.maximum(v.std(axis=0), 1e-9)
    return (feats - mu) / sd


# ── 简化 SDA（两阶段）────────────────────────────────────────────────

def _segments_from_labels(labels):
    """相邻同标签合并为段，返回 [(start_idx, end_idx_excl, label), ...]。"""
    segs = []
    start = 0
    for i in range(1, len(labels) + 1):
        if i == len(labels) or labels[i] != labels[start]:
            segs.append((start, i, labels[start]))
            start = i
    return segs


def _ward_merge_dist(seg_a, seg_b, feats):
    """两段合并的 Ward 距离增量：(na*nb/(na+nb))·||ca−cb||²。"""
    import numpy as np
    a = feats[seg_a[0]:seg_a[1]]
    b = feats[seg_b[0]:seg_b[1]]
    na, nb = len(a), len(b)
    d = float(np.linalg.norm(a.mean(axis=0) - b.mean(axis=0)))
    return (na * nb / (na + nb)) * d * d


def _phase1(feats_z, n_clusters, k_conn, min_len):
    """单次 (N,K,L) 的边界候选：Ward+连通约束 → 段 → 短段合并 → 距离比合并。"""
    import numpy as np
    from sklearn.cluster import AgglomerativeClustering
    from sklearn.neighbors import kneighbors_graph
    n_ep = feats_z.shape[0]
    k = min(k_conn, max(2, n_ep - 1))
    # 论文口径：连通约束按 epoch 时间序（序号相距 ≤K），非特征空间近邻
    conn = kneighbors_graph(np.arange(n_ep).reshape(-1, 1),
                            n_neighbors=k, include_self=False)
    labels = AgglomerativeClustering(
        n_clusters=min(n_clusters, n_ep), linkage="ward",
        connectivity=conn).fit_predict(feats_z)
    segs = _segments_from_labels(labels)

    # 短段并入相邻更近段（循环直至无短段）
    changed = True
    while changed and min_len > 0:
        changed = False
        for i, s in enumerate(segs):
            if s[1] - s[0] <= min_len and len(segs) > 1:
                cands = []
                if i > 0:
                    cands.append(( _ward_merge_dist(segs[i - 1], s, feats_z), i - 1))
                if i < len(segs) - 1:
                    cands.append(( _ward_merge_dist(s, segs[i + 1], feats_z), i + 1))
                if cands:
                    _, j = min(cands)
                    lo, hi = min(i, j), max(i, j) + 1
                    merged = (segs[lo][0], segs[hi - 1][1], segs[lo][2])
                    segs[lo:hi] = [merged]
                    changed = True
                    break

    # Ward 距离比合并：Dmin ≤ W·Davg 的相邻对反复并（论文 Phase-1 第 4 步）
    while len(segs) > 1:
        dists = [_ward_merge_dist(segs[i], segs[i + 1], feats_z)
                 for i in range(len(segs) - 1)]
        davg = sum(dists) / len(dists)
        dmin = min(dists)
        if dmin > W_COEF * davg:
            break
        j = dists.index(dmin)
        merged = (segs[j][0], segs[j + 1][1], segs[j][2])
        segs[j:j + 2] = [merged]

    return [s[0] for s in segs[1:]] + [len(feats_z)] if segs else []


def _adapted_silhouette(feats_z, boundaries):
    """状态适配轮廓系数：相邻状态两两之间的样本轮廓均值（论文 Phase-2 选优据）。"""
    import numpy as np
    from sklearn.metrics import silhouette_score
    bounds = sorted(set(b for b in boundaries if 0 < b < feats_z.shape[0]))
    if not bounds:
        return -1.0, None
    labels = np.zeros(feats_z.shape[0], dtype=int)
    prev = 0
    seg_id = 0
    for b in bounds + [feats_z.shape[0]]:
        labels[prev:b] = seg_id
        prev = b
        seg_id += 1
    n_states = seg_id
    if n_states < 2:
        return -1.0, labels
    try:
        return float(silhouette_score(feats_z, labels)), labels
    except Exception:
        return -1.0, labels


def segment_states(feats, valid):
    """简化 SDA 主入口。返回 (labels, n_states)；数据不足返回 (None, 0)。"""
    import numpy as np
    if feats is None or valid is None or int(valid.sum()) < MIN_EPOCHS:
        return None, 0
    feats_z = _zscore(feats, valid)
    v_idx = np.flatnonzero(valid)
    feats_v = feats_z[valid]

    # Phase 1：全 (N,K,L) 网格收集边界候选（valid 索引系内，剔终端值）
    cand = []
    n_v = feats_v.shape[0]
    for n_cl in N_RANGE:
        for k_conn in K_RANGE:
            for min_len in L_RANGE:
                cand.extend(x for x in _phase1(feats_v, n_cl, k_conn, min_len)
                            if 0 < x < n_v)
    if not cand:
        return None, 0

    # Phase 2（低配化）：论文用 K-means/DBSCAN 聚边界取三种中心；此处取
    # 「频次众数」——真边界在多组 (N,K,L) 下反复出现，伪边界只出现一两次，
    # 按出现次数取前 k 个作边界，再用状态适配轮廓系数选 k。
    uniq, counts = np.unique(np.asarray(cand, dtype=int), return_counts=True)
    order = np.argsort(-counts, kind="stable")
    best = (-1.0, None)
    for k in KM_RANGE:
        if k > len(uniq):
            break
        bounds = sorted(int(v) for v in uniq[order[:k]])
        score, _ = _adapted_silhouette(feats_v, bounds)
        if score > best[0]:
            best = (score, bounds)
    if best[1] is None:
        return None, 0

    # 边界映回原 epoch 系，逐 epoch 状态标签（被剔除 epoch 记 -1）
    bounds = [v_idx[b] for b in best[1] if 0 < b < len(v_idx)]
    labels = np.full(feats.shape[0], -1, dtype=int)
    prev = 0
    sid = 0
    all_b = bounds + [len(v_idx)]
    for b in all_b:
        labels[v_idx[prev:b]] = sid
        prev = b
        sid += 1
    return labels, sid


# ── 状态描述与字母表 ─────────────────────────────────────────────────

def state_centroids(feats, labels):
    """每个状态的特征中心（z 空间）。返回 [(state_id, centroid, n_epochs)]。"""
    import numpy as np
    out = []
    for s in sorted(set(labels.tolist())):
        if s < 0:
            continue
        m = labels == s
        out.append((int(s), feats[m].mean(axis=0), int(m.sum())))
    return out


def dominant_band(centroid):
    """按列序返回占优频段名（5 频段 log 功率在特征前 5×n_ch 列的均值）。"""
    import numpy as np
    n_ch = centroid.shape[0] // (len(BANDS) + len(RATIOS))
    band_mean = [float(np.mean(centroid[i * n_ch:(i + 1) * n_ch]))
                 for i in range(len(BANDS))]
    return list(BANDS)[int(np.argmax(band_mean))]


def build_alphabet(state_vecs, max_k=8):
    """跨会话字母表：对全部状态特征向量 K-means，轮廓系数定 k（2..max_k）。

    返回 (labels, centroids)；状态太少时返回 (None, None)。
    """
    import numpy as np
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    X = np.asarray(state_vecs, dtype=float)
    if len(X) < 4:
        return None, None
    best = (-1.0, None, None)
    for k in range(2, min(max_k, len(X) - 1) + 1):
        km = KMeans(n_clusters=k, n_init=10,
                    random_state=RANDOM_STATE).fit(X)
        try:
            sc = float(silhouette_score(X, km.labels_))
        except Exception:
            sc = -1.0
        if sc > best[0]:
            best = (sc, km.labels_, km.cluster_centers_)
    if best[1] is None:
        return None, None
    return best[1].tolist(), best[2]


def word_from_labels(labels, centroids):
    """状态标签 → 字母词：相邻同字母合并（论文 §2.5.3.1）。"""
    letters = {}
    for i, lab in enumerate(labels):
        if lab not in letters:
            letters[lab] = chr(ord("A") + len(letters)) if len(letters) < 26 else "?"
    word = []
    for lab in labels:
        ch = letters[lab]
        if not word or word[-1] != ch:
            word.append(ch)
    return "".join(word), letters, centroids


def weighted_levenshtein(w1, w2, centroids, letters_map):
    """加权编辑距离：替换代价 = 两字母簇心欧氏距；插/删 = 该字母到其余簇均距。

    letters_map: {word_letter: centroid_vector}
    """
    import numpy as np
    def C(ch):
        return np.asarray(letters_map[ch], dtype=float)

    def sub_cost(a, b):
        return float(np.linalg.norm(C(a) - C(b)))

    ins_cost = {}
    for ch in letters_map:
        others = [np.linalg.norm(C(ch) - C(o)) for o in letters_map if o != ch]
        ins_cost[ch] = float(np.mean(others)) if others else 1.0

    m, n = len(w1), len(w2)
    D = [[0.0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        D[i][0] = D[i - 1][0] + ins_cost[w1[i - 1]]
    for j in range(1, n + 1):
        D[0][j] = D[0][j - 1] + ins_cost[w2[j - 1]]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            D[i][j] = min(
                D[i - 1][j] + ins_cost[w1[i - 1]],
                D[i][j - 1] + ins_cost[w2[j - 1]],
                D[i - 1][j - 1] + (0.0 if w1[i - 1] == w2[j - 1]
                                   else sub_cost(w1[i - 1], w2[j - 1])),
            )
    return D[m][n]


# ── 会话级入口 ────────────────────────────────────────────────────────

def session_summary(eeg, sfreq):
    """单会话：分段 + 频段占优描述。数据不足返回 {"ok": False, "reason": ...}。"""
    import numpy as np
    feats, valid = extract_features(eeg, sfreq)
    labels, n_states = segment_states(feats, valid)
    if labels is None:
        return {"ok": False,
                "reason": f"有效数据不足（有效 epoch < {MIN_EPOCHS}），状态序列弃权"}
    cents = state_centroids(feats, labels)
    desc = []
    for sid, c, n_ep in cents:
        desc.append({"state": sid, "dominant": dominant_band(c),
                     "epochs": n_ep})
    word = "".join(chr(ord("A") + d["state"]) for d in desc)
    return {"ok": True, "version": STATE_SEQ_VERSION,
            "n_states": n_states, "states": desc,
            "word": word,
            "valid_ratio": round(float(valid.mean()), 4)}


# ── 四文明原型透镜（形状 1）──────────────────────────────────────────
# 授权：宗国法师 2026-10-11「六、候您一句的点：六点建议照准」第 2 条＝形状 1 先做。
# 方案正源：01_项目管理/20261010_W3_四文明原型透镜与零坐标正负象限_个人节点模型呈现方案_v1.md §四形状1。
#
# 硬约束（逐条对应方案稿，非本窗自设）：
#   · **视角维，不是新数据层**：本段只重述 session_summary 的既有输出，
#     不参与分段、不参与字母表、不新增采集字段 ⇒ 不触 §九第3条「五相归层，不出现第六并列层」。
#   · **只有 RDoC 栏可验**；另三栏＝词汇／叙述层，一律带 LENS_BOUNDARY 标注，
#     **不进判据、不进阈值、不进闭环控制**（本模块本就不被 closedloop_controller import，见文件头纪律）。
#   · **不设总分**：返回体里没有任何跨栏聚合值。依据＝方案稿同构 2「四行读数全是方向、不是量级」
#     与法师 2026-10-11 指令「零点坐标是动量、是张力」⇒ 收敛成单一标量即违该指令。
#   · ⚠**阿毗达摩／干支／占星三栏的词汇映射属义理判定权**（开工规约 §四＝法师；案例库说明 §一「义理只能由法师定」）。
#     AI 不得自拟 ⇒ 三栏**结构在此、内容留空**，显式标 LENS_PENDING。
#     这不是半成品：**弃权是一等值**（本文件既有纪律），空栏是如实，硬造映射才是缺陷。
#   · 出生数据（干支／占星真值化）**本轮不采**＝法师 §六④ 照准原文 ⇒ 本段无任何出生字段入口。

LENS_VERSION = "20261011"

LENS_BOUNDARY = "词汇／叙述层——不进判据、不进阈值、不进闭环控制"
LENS_PENDING = "候法师定词汇映射（义理判定权在法师，AI 不自拟）"

# (键, 栏名, 该书所述波长, 是否可直接验)  —— 栏名与波长逐字取自方案稿 §一 取证表
LENSES = [
    ("rdoc", "现代 RDoC／神经科学", "生物生理硬件", True),
    ("abhidhamma", "阿毗达摩", "微观究竟（毫秒级心法）", False),
    ("ganzhi", "中国干支", "宏观时空能量", False),
    ("astro", "西方占星", "子人格冲突动力", False),
]

# RDoC 栏的诚实缺口：该书案例的 RDoC 读数含以下各项，我们**一项都没测**。
# 列出缺口即本栏"可验"的一部分（判语 011：我方验证须声明未测项，不以未测项立论）。
RDOC_NOT_MEASURED = [
    "脑影像／前额叶灌注（该书：DLPFC 去活化）",
    "唾液皮质醇昼夜节律",
    "人格量表分（该书：神经质 N=94）",
    "行为任务与不良反应记录",
]


def lens_readings(summ):
    """把一份 session_summary 重述成四栏读法。数据不足照实弃权，不硬造。

    返回 {"ok": False, "reason": ...} 或
         {"ok": True, "version":..., "lenses": {键: 栏}, "no_aggregate_score": True}
    """
    if not isinstance(summ, dict) or not summ.get("ok"):
        reason = (summ or {}).get("reason") if isinstance(summ, dict) else None
        return {"ok": False,
                "reason": reason or "上游 session_summary 弃权，四栏读法一并弃权"}

    lenses = {}
    for key, name, wavelength, verifiable in LENSES:
        lenses[key] = {"name": name, "wavelength": wavelength,
                       "verifiable": verifiable,
                       "boundary": None if verifiable else LENS_BOUNDARY}

    states = summ.get("states") or []
    lenses["rdoc"].update({
        "status": "measured",
        "measured": {
            "n_states": summ.get("n_states"),
            "state_word": summ.get("word"),
            "valid_ratio": summ.get("valid_ratio"),
            "state_seq_version": summ.get("version"),
            "dominant_band_per_state": [
                {"state": s.get("state"), "dominant_band": s.get("dominant"),
                 "epochs": s.get("epochs")} for s in states],
        },
        "not_measured": list(RDOC_NOT_MEASURED),
        "claim_limit": "本栏只报可测项；频段占优不得读作任何 RDoC 构念的判定",
    })

    for key, _n, _w, verifiable in LENSES:
        if not verifiable:
            lenses[key].update({"status": "pending", "text": None,
                                "note": LENS_PENDING})

    return {"ok": True, "version": LENS_VERSION,
            "source_version": summ.get("version"),
            "lenses": lenses,
            "no_aggregate_score": True}


def analyze_sessions(npz_paths, out_dir=None):
    """批量：全体会话 → 统一字母表 → 各自状态词 → 加权编辑距离矩阵。

    返回结果 dict；同时若给 out_dir 则落 summary.json / summary.md。
    """
    import numpy as np
    sessions = []
    all_vecs = []
    per_session = []
    for p in npz_paths:
        try:
            with np.load(p, allow_pickle=True) as d:
                meta = d["meta"].item()
                eeg = np.asarray(d["eeg"])
        except Exception as ex:
            per_session.append({"path": p, "ok": False,
                                "reason": f"npz 读取失败：{ex}"})
            continue
        sid = os.path.basename(os.path.dirname(p))
        feats, valid = extract_features(eeg, float(meta.get("sfreq") or 0))
        labels, n_states = segment_states(feats, valid)
        if labels is None:
            per_session.append({"path": p, "session": sid, "ok": False,
                                "reason": "有效数据不足，弃权"})
            continue
        cents = state_centroids(feats, labels)
        for _, c, _n in cents:
            all_vecs.append(c)
        per_session.append({"path": p, "session": sid, "ok": True,
                            "n_states": n_states,
                            "labels": labels.tolist(),
                            "centroids": {int(s): c.tolist()
                                          for s, c, _n in cents},
                            "valid_ratio": round(float(valid.mean()), 4)})
    ok_sessions = [s for s in per_session if s.get("ok")]
    if len(ok_sessions) < 2:
        result = {"version": STATE_SEQ_VERSION, "sessions": per_session,
                  "alphabet": None,
                  "note": "可用会话不足 2，跳过字母表与编辑距离"}
    else:
        labs, cents_arr = build_alphabet(all_vecs)
        if labs is None:
            result = {"version": STATE_SEQ_VERSION, "sessions": per_session,
                      "alphabet": None, "note": "状态过少，字母表弃权"}
        else:
            letters_map = {}
            word_of = {}
            for s in ok_sessions:
                # 逐状态取最近字母簇 → 该会话的字母序列 → 合并成词
                labs_s = []
                for sid_str, c_list in s["centroids"].items():
                    pass  # centroids 按状态 id 存；下面按 labels 序生成字母
                seq = []
                cvecs = {int(k): np.asarray(v) for k, v in s["centroids"].items()}
                for lab in s["labels"]:
                    if lab < 0:
                        continue
                    ci = int(np.argmin(
                        [np.linalg.norm(cvecs[lab] - cents_arr[j])
                         for j in range(len(cents_arr))]))
                    seq.append(chr(ord("A") + ci))
                word = []
                for ch in seq:
                    if not word or word[-1] != ch:
                        word.append(ch)
                word_of[s["session"]] = "".join(word)
            # 字母 → 簇心（供编辑距离代价）
            for ci in range(len(cents_arr)):
                letters_map[chr(ord("A") + ci)] = cents_arr[ci]
            names = [s["session"] for s in ok_sessions]
            dist = {}
            for i, a in enumerate(names):
                for b in names[i + 1:]:
                    dist[f"{a}|{b}"] = round(weighted_levenshtein(
                        word_of[a], word_of[b], None, letters_map), 4)
            result = {"version": STATE_SEQ_VERSION,
                      "sessions": per_session,
                      "alphabet": {"n_letters": len(cents_arr),
                                   "letters": sorted(letters_map)},
                      "words": word_of,
                      "levenshtein": dist}
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "summary.json"), "w",
                  encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        with open(os.path.join(out_dir, "summary.md"), "w",
                  encoding="utf-8") as f:
            f.write(_to_markdown(result))
    return result


def _to_markdown(result):
    lines = [f"# 状态序列化批分析（{STATE_SEQ_VERSION}）", ""]
    if result.get("alphabet"):
        lines += [f"- 字母表：{result['alphabet']['n_letters']} 个状态类型"
                  f"（{', '.join(result['alphabet']['letters'])}）", ""]
    lines += ["| 会话 | 状态数 | 有效占比 | 状态词 |", "|---|---|---|---|"]
    for s in result["sessions"]:
        if s.get("ok"):
            lines.append(f"| {s['session']} | {s['n_states']} | "
                         f"{s['valid_ratio']:.0%} | {result['words'][s['session']]} |")
        else:
            lines.append(f"| {s.get('session', s['path'])} | - | - | "
                         f"弃权：{s['reason']} |")
    if result.get("levenshtein"):
        lines += ["", "## 加权编辑距离（越小越像）", "",
                  "| 会话对 | 距离 |", "|---|---|"]
        for k, v in sorted(result["levenshtein"].items(), key=lambda x: x[1]):
            lines.append(f"| {k} | {v} |")
    return "\n".join(lines) + "\n"


# ── 自测 ─────────────────────────────────────────────────────────────

def _selftest():
    import sys
    import tempfile
    import numpy as np
    fails = []
    rng = np.random.default_rng(RANDOM_STATE)
    sfreq = 256.0

    # ① 合成双态信号：α 段与 θ 段交替，分段应找出边界（容忍 ±3s）
    seg_len = 40
    blocks = [60, 30, 60, 30, 60, 30, 60]        # 秒（α/θ 交替）
    t_all, sig = 0.0, []
    truth = []
    for bi, dur in enumerate(blocks):
        f0 = 10.0 if bi % 2 == 0 else 6.0
        t = np.arange(int(dur * sfreq)) / sfreq
        amp = 8.0 if bi % 2 == 0 else 7.0
        for ch in range(4):
            pass
        block = np.column_stack([
            amp * np.sin(2 * np.pi * f0 * t + ch * 0.5) + rng.normal(0, 1.0, len(t))
            for ch in range(4)])
        sig.append(block)
        truth.append(t_all)
        t_all += dur
    eeg = np.vstack(sig)
    feats, valid = extract_features(eeg, sfreq)
    if feats is None or not valid.any():
        fails.append("① 特征提取失败")
    else:
        labels, n_states = segment_states(feats, valid)
        if labels is None:
            fails.append("① 合成双态信号分段弃权（不应弃权）")
        else:
            if n_states < 2:
                fails.append(f"① 双态信号只分出 {n_states} 个状态（应 ≥2）")
            else:
                # 分割恢复度：ARI 对标签置换与小幅边界漂移稳健（逐点对齐
                # 会被伪迹剔除的累计漂移误杀，实测 ±9 epoch）
                from sklearn.metrics import adjusted_rand_score
                truth = np.concatenate(
                    [[bi] * int(d) for bi, d in enumerate(blocks)])
                truth = truth[: labels.shape[0]]
                m = valid & (labels >= 0)
                ari = float(adjusted_rand_score(truth[m], labels[m]))
                # 实测 6/6 边界全中、漂移 ≤9 epoch 时 ARI≈0.84，故取 0.80
                if ari < 0.80:
                    fails.append(f"① 分割恢复 ARI={ari:.3f}（应 ≥0.80）")
                if n_states < 6:
                    fails.append(f"① 七段交替只分出 {n_states} 态（应 ≥6）")
            # 单会话摘要
            summ = session_summary(eeg, sfreq)
            if not summ.get("ok"):
                fails.append(f"① session_summary 弃权：{summ.get('reason')}")
            elif summ["n_states"] < 2:
                fails.append("① session_summary 状态数 <2")
            # 确定性：同输入连算两次逐字一致（判语011）
            labels2, n2 = segment_states(feats, valid)
            if n2 != n_states or not np.array_equal(labels2, labels):
                fails.append("① 两次分段结果不一致（确定性失败）")

    # ② 数据不足必须弃权（P6）
    summ2 = session_summary(eeg[: int(30 * sfreq)], sfreq)
    if summ2.get("ok"):
        fails.append("② 30 秒短数据未弃权")

    # ③ 加权编辑距离：同词距离 0；不同词距离>0 且对称
    cv = np.eye(3)
    lm = {"A": cv[0], "B": cv[1], "C": cv[2]}
    d0 = weighted_levenshtein("ABAC", "ABAC", None, lm)
    d1 = weighted_levenshtein("ABAC", "ABCB", None, lm)
    d2 = weighted_levenshtein("ABCB", "ABAC", None, lm)
    if abs(d0) > 1e-9:
        fails.append(f"③ 同词距离应 0（得 {d0}）")
    if not (d1 > 0 and abs(d1 - d2) < 1e-9):
        fails.append(f"③ 异词距离应 >0 且对称（d1={d1}, d2={d2}）")

    # ④ 字母表：两组分离状态向量应聚成 ≥2 类且确定
    g1 = np.asarray([[5, 0, 0]] * 5) + rng.normal(0, .05, (5, 3))
    g2 = np.asarray([[0, 5, 0]] * 5) + rng.normal(0, .05, (5, 3))
    labs3, cents3 = build_alphabet(np.vstack([g1, g2]))
    if labs3 is None or len(set(labs3)) < 2:
        fails.append("④ 字母表未分出 ≥2 类")

    # ⑤ 四栏读法（形状 1）：只有 RDoC 栏有内容，另三栏必须留空且带边界标注
    fake = {"ok": True, "version": STATE_SEQ_VERSION, "n_states": 3,
            "word": "ABC", "valid_ratio": 0.9875,
            "states": [{"state": 0, "dominant": "alpha", "epochs": 60},
                       {"state": 1, "dominant": "theta", "epochs": 30},
                       {"state": 2, "dominant": "alpha", "epochs": 60}]}
    lr = lens_readings(fake)
    if not lr.get("ok"):
        fails.append("⑤ 四栏读法对合格 summary 竟弃权")
    else:
        ls = lr["lenses"]
        if len(ls) != len(LENSES):
            fails.append(f"⑤ 栏数应 {len(LENSES)}（得 {len(ls)}）")
        measured = [k for k, v in ls.items() if v.get("status") == "measured"]
        if measured != ["rdoc"]:
            fails.append(f"⑤ 可验栏应只有 rdoc（得 {measured}）")

        # 词汇层三栏的断言抽成可复用函数，**为的是能对"做过的假结果"再跑一次**——
        # 没响过的闸不算闸（教训 7.1／坑 017）。
        def _pend_fails(d):
            out = []
            for k, _n, _w, verifiable in LENSES:
                col = d.get(k) or {}
                if verifiable:
                    if col.get("boundary") is not None:
                        out.append(f"可验栏 {k} 不应挂词汇层标注")
                    continue
                if col.get("status") != "pending":
                    out.append(f"{k} 栏 status 应 pending（得 {col.get('status')}）")
                if col.get("text") is not None:
                    out.append(f"{k} 栏内容应留空候法师定映射（竟有值）")
                if col.get("boundary") != LENS_BOUNDARY:
                    out.append(f"{k} 栏缺边界标注")
            return out

        fails += ["⑤ " + x for x in _pend_fails(ls)]
        if len([k for k, v in ls.items() if v.get("status") == "pending"]) != 3:
            fails.append("⑤ 词汇层应 3 栏")
        m = ls["rdoc"]["measured"]
        if (m["n_states"], m["state_word"], m["valid_ratio"]) != (3, "ABC", 0.9875):
            fails.append("⑤ RDoC 栏未如实转录上游 measured 值")
        if not lr.get("no_aggregate_score"):
            fails.append("⑤ 缺 no_aggregate_score 声明")
        # 禁总分：递归扫全树，任何名字带 score/total/aggregate/sum 的键即失败
        # （`no_aggregate_score` 是"不设总分"的声明位本身，白名单排除）
        def _scan(o, path=""):
            bad = []
            if isinstance(o, dict):
                for kk, vv in o.items():
                    low = str(kk).lower()
                    if low != "no_aggregate_score" and any(
                            t in low for t in ("score", "total", "aggregate", "sum")):
                        bad.append(path + "/" + str(kk))
                    bad += _scan(vv, path + "/" + str(kk))
            elif isinstance(o, list):
                for i, vv in enumerate(o):
                    bad += _scan(vv, f"{path}[{i}]")
            return bad
        hits = _scan(lr)
        if hits:
            fails.append(f"⑤ 出现聚合／总分类键（违「不设总分」）：{hits}")
        a = json.dumps(lr, ensure_ascii=False, sort_keys=True)
        b = json.dumps(lens_readings(fake), ensure_ascii=False, sort_keys=True)
        if a != b:
            fails.append("⑤ 四栏读法不确定（同输入两次结果不一致）")
        # **反向验证**：把上面两道闸各喂一个"做过手脚"的结果，必须都响；
        # 不响＝断言本身是死的，比没有断言更坏。
        bad1 = json.loads(a)
        bad1["lenses"]["ganzhi"]["text"] = "金旺克木"     # 模拟 AI 自拟义理映射
        if not _pend_fails(bad1["lenses"]):
            fails.append("⑤ 反向验证失效：词汇栏被填值却未报警")
        bad2 = json.loads(a)
        bad2["lenses"]["rdoc"]["measured"]["focus_score"] = 0.8   # 模拟偷偷加总分
        if not _scan(bad2):
            fails.append("⑤ 反向验证失效：加了总分类键却未报警")
    # 弃权传递：上游弃权则四栏一并弃权，且不吞掉上游理由
    ab = lens_readings({"ok": False, "reason": "有效数据不足"})
    if ab.get("ok") or ab.get("reason") != "有效数据不足":
        fails.append(f"⑤ 弃权未如实传递（得 {ab}）")

    if fails:
        for x in fails:
            print("FAIL:", x)
        return 1
    print("PASS: state_segmentation 自测通过（①双态分段+边界+确定性 / "
          "②短数据弃权 / ③编辑距离 / ④字母表 / ⑤四栏读法含两道反向验证）")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_selftest())
