#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
attribution_v0.py —— 止观AI 自归因器 v0（最小可跑原型）

配套蓝图：20260919_止观AI最小可行自进化闭环实施蓝图_v1.md §5 / §7 / §11
方法论来源：Astar（surrogate RM 思想，arXiv:2608.27287）＋ AgentEvolver
            （Self-Attributing，arXiv:2511.10395）。只取方法论，不照搬工程。

红线（对齐蓝图 §0 / §9）：
  * 纯 Python + numpy，无 GPU、不训练任何模型（D28 不买显卡路线）；
  * 大模型不进实时环（判语001）——本脚本只做"对配置的元学习"离线分析；
  * AI 无提案自动生效权：输出仅供法师闸门校准参考，不得直接采信。

用法：
  python attribution_v0.py                     # 内置合成样本，开箱即跑
  python attribution_v0.py --data sessions.jsonl   # 读真实四元组 JSONL（蓝图 §7 schema）
  python attribution_v0.py --json              # 结果以 JSON 输出（供经验池落库）

输入记录字段（JSONL，每行一条；缺失字段自动跳过该条并计数）：
  session_id, config{...}, proposal{L1,L2,L3}, outcome{alpha_power,theta_power,beta_power,...}
  proxy_label / human_d_label 可选（缺省则由本脚本按三态规则重算代理分）

归因方法（蓝图 §5，MVP 只用规则+统计，不用真 GRPO）：
  ① 组间差异法：同一参数"改后 vs 未改"两组平均深放松占比之差（effect size, Cohen's d）；
  ② 方向一致性法：应用了某提案的会话成功率是否高于未应用者，并检查改动幅度与得分单调性。

置信度纪律（蓝图 §9 "数据太少"风险对策）：
  * 任一组样本 <3 → 该参数自动降置信并告警；
  * 总样本 <5   → 全局低置信模式，所有结论降级为"仅供法师校准参考"。
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

try:
    import numpy as np
except ImportError:  # pragma: no cover
    print("[FATAL] 需要 numpy：pip install numpy", file=sys.stderr)
    raise

# ---------------------------------------------------------------------------
# 1. 代理打分（surrogate label）——依据 neuradock_simulator.py 三态定义
# ---------------------------------------------------------------------------
# _STATES（neuradock_simulator.py:59-65，幅值权重）：
#   relax    (alpha=1.00, theta=0.35, beta=0.25)  闭眼放松：Alpha 主导
#   focus    (alpha=0.35, theta=0.30, beta=0.90)  睁眼专注：Alpha 阻滞、Beta 抬升
#   drowsy   (alpha=0.55, theta=1.00, beta=0.20)  昏沉欲睡：Theta 主导
#   meditate (alpha=0.80, theta=0.60, beta=0.20)  禅定：Alpha+Theta 俱高、Beta 低
#
# 代理分设计（v0，可解释优先）：
#   * 用"谱占比"而非绝对 µV² —— 跨设备/跨人尺度不变；
#   * meditate 目标占比 A*=0.50, T*=0.375, B*=0.125（由上表归一化）；
#   * alpha_fit / theta_fit：占比偏离目标的相对距离，线性衰减到 0；
#   * beta_fit：Beta ≤ 目标不罚（记 1），高于目标后线性衰减、达 3 倍目标记 0。
# 期望排序：meditate(1.0) > relax ≈ drowsy > focus(≈0)。

A_STAR, T_STAR, B_STAR = 0.50, 0.375, 0.125


def proxy_score(alpha: float, theta: float, beta: float) -> Optional[float]:
    """由三频段功率算"禅定接近度"代理分 ∈ [0,1]。任一非正/全零 → None（无法打分）。"""
    try:
        a, t, b = float(alpha), float(theta), float(beta)
    except (TypeError, ValueError):
        return None
    total = a + t + b
    if total <= 0 or min(a, t, b) < 0:
        return None
    sa, st, sb = a / total, t / total, b / total
    a_fit = max(0.0, 1.0 - abs(sa - A_STAR) / A_STAR)
    t_fit = max(0.0, 1.0 - abs(st - T_STAR) / T_STAR)
    if sb <= B_STAR:
        b_fit = 1.0
    else:  # Beta 高于禅定目标才罚：B_STAR→3*B_STAR 线性衰减到 0
        b_fit = max(0.0, 1.0 - (sb - B_STAR) / (2.0 * B_STAR))
    return round(a_fit * t_fit * b_fit, 4)


def _f(x: Any, default: float = 0.0) -> float:
    """宽松转 float（JSON 里可能混入 None/字符串）。"""
    try:
        v = float(x)
        return v if math.isfinite(v) else default
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# 2. 记录加载与清洗
# ---------------------------------------------------------------------------

@dataclass
class Session:
    session_id: str
    config: Dict[str, Any] = field(default_factory=dict)
    proposal: Optional[Dict[str, Any]] = None      # {L1,L2,L3}，L3 形如 "变化率限幅0.5→0.2"
    outcome: Dict[str, Any] = field(default_factory=dict)
    proxy_label: float = 0.0                        # 机器代理分（自动）
    human_d_label: Optional[float] = None           # 法师 D 级标签（稀疏、贵）
    success: bool = False                           # 归因后标记（v0：proxy ≥ 阈值）


def parse_change(l3_text: str) -> Tuple[Optional[str], Optional[float], Optional[float]]:
    """从提案 L3 文本解析 (参数名, 旧值, 新值)。

    支持："变化率限幅0.5→0.2" / "tau_ema 10→20" / "alpha_threshold 60→70"。
    解析失败返回 (None, None, None)——该提案不参与数值归因，只参与方向一致性计数。
    """
    if not l3_text or not isinstance(l3_text, str):
        return None, None, None
    for arrow in ("→", "->", "=>"):
        if arrow in l3_text:
            left, right = l3_text.split(arrow, 1)
            break
    else:
        return None, None, None
    # \w 在 Python3 str 模式下含 CJK，故"变化率限幅0.5"这类中文参数名也能解析
    m_left = re.search(r"(\w+)\s*[:：]?\s*(-?\d+(?:\.\d+)?)\s*$", left)
    m_right = re.search(r"(-?\d+(?:\.\d+)?)\s*$", right)
    if not (m_left and m_right):
        return None, None, None
    name = m_left.group(1).strip()
    old_v, new_v = float(m_left.group(2)), float(m_right.group(1))
    if name in ("变化率限幅", "vol_ramp"):      # 中文别名归一（蓝图 §7 示例）
        name = "vol_ramp"
    return name, old_v, new_v


def load_sessions(path: str) -> Tuple[List[Session], Dict[str, int]]:
    """读四元组 JSONL。返回 (有效记录, 跳过计数)。"""
    sessions: List[Session] = []
    skipped = {"missing_bands": 0, "bad_json": 0}
    with open(path, "r", encoding="utf-8") as fh:
        for ln, line in enumerate(fh, 1):
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                skipped["bad_json"] += 1
                print(f"[WARN] {path}:{ln} JSON 解析失败，跳过", file=sys.stderr)
                continue
            out = rec.get("outcome") or {}
            alpha, theta, beta = out.get("alpha_power"), out.get("theta_power"), out.get("beta_power")
            if alpha is None and theta is None and beta is None:
                skipped["missing_bands"] += 1
                print(f"[WARN] {path}:{ln} outcome 缺三频段功率，无法代理打分，跳过", file=sys.stderr)
                continue
            score = proxy_score(alpha, theta, beta) if (alpha is not None and theta is not None and beta is not None) else None
            if rec.get("proxy_label") is not None:
                score = _f(rec["proxy_label"], default=score or 0.0)
            if score is None:
                skipped["missing_bands"] += 1
                print(f"[WARN] {path}:{ln} 频段不全且无 proxy_label，跳过", file=sys.stderr)
                continue
            sessions.append(Session(
                session_id=str(rec.get("session_id") or f"line{ln}"),
                config=rec.get("config") or {},
                proposal=rec.get("proposal"),
                outcome=out,
                proxy_label=score,
                human_d_label=_f(rec["human_d_label"]) if rec.get("human_d_label") is not None else None,
                success=bool(rec.get("success", False)),
            ))
    return sessions, skipped


# ---------------------------------------------------------------------------
# 3. 归因方法（蓝图 §5）
# ---------------------------------------------------------------------------

MIN_GROUP_N = 3          # 任一组样本下限：低于此自动降置信并告警
GLOBAL_MIN_N = 5         # 全局低置信阈值


def _cohens_d(x: List[float], y: List[float]) -> float:
    """Cohen's d（pooled SD）。任一组 n<2 或方差为 0 → 返回带符号的保守值。"""
    xa, ya = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    if len(xa) < 1 or len(ya) < 1:
        return 0.0
    mx, my = float(xa.mean()), float(ya.mean())
    vx = float(xa.var(ddof=1)) if len(xa) > 1 else 0.0
    vy = float(ya.var(ddof=1)) if len(ya) > 1 else 0.0
    n1, n2 = len(xa), len(ya)
    pooled_sq = ((n1 - 1) * vx + (n2 - 1) * vy) / max(n1 + n2 - 2, 1)
    if pooled_sq <= 0:
        return 0.0 if mx == my else math.copysign(1.0, mx - my)
    d = (mx - my) / math.sqrt(pooled_sq)
    # 小样本收缩：n 小时把 |d| 往 0 拉（避免 2 vs 2 的极端值被当成强证据）
    shrink = min(1.0, (min(n1, n2)) / MIN_GROUP_N)
    return float(d * shrink)


def _mean(xs: List[float]) -> Optional[float]:
    return round(float(np.mean(xs)), 4) if xs else None


@dataclass
class ParamAttribution:
    param: str
    method: str                       # "between_group" | "direction_consistency"
    n_treated: int = 0                # 应用了该提案的会话数
    n_control: int = 0                # 未应用的会话数
    mean_proxy_treated: Optional[float] = None
    mean_proxy_control: Optional[float] = None
    effect_size_d: float = 0.0        # 组间差异法：Cohen's d（改后 - 未改）
    success_rate_treated: Optional[float] = None   # 方向一致性法
    success_rate_control: Optional[float] = None
    direction_ok: bool = False        # 成功率是否"应用者 ≥ 未应用者"
    monotonic_ok: Optional[bool] = None  # 改动幅度与得分是否同向（可解析数值时）
    confidence: float = 0.0           # [0,1]，样本少自动降档
    warnings: List[str] = field(default_factory=list)


def _confidence(n_t: int, n_c: int, direction_ok: bool, monotonic_ok: Optional[bool]) -> Tuple[float, List[str]]:
    """置信度纪律：组内 <3 降档；两法一致加分，矛盾减分。"""
    warns: List[str] = []
    base = 0.5
    if n_t < MIN_GROUP_N or n_c < MIN_GROUP_N:
        small = min(n_t, n_c)
        base *= max(0.2, small / MIN_GROUP_N)          # 样本不足 → 降置信
        warns.append(f"样本<{MIN_GROUP_N}（treated={n_t}, control={n_c}）：自动降置信，仅供法师校准参考")
    if direction_ok:
        base += 0.25
    else:
        base -= 0.15
        warns.append("方向不一致：应用提案者成功率未高于未应用者")
    if monotonic_ok is True:
        base += 0.15
    elif monotonic_ok is False:
        base -= 0.2
        warns.append("改动幅度与得分不同向（单调性检查失败）")
    conf = round(min(0.9, max(0.05, base)), 3)
    return conf, warns


def attribute(sessions: List[Session], success_threshold: float = 0.4) -> List[ParamAttribution]:
    """对每个被提案过的参数跑两种归因，返回按置信度降序的排名。

    success 判定：记录自带 success 优先；否则 proxy_label ≥ success_threshold。
    （蓝图 §10-2："成功"机器判据 v0 = 代理分过阈；后续可换 deep_state_ratio>基线+X%。）
    """
    if not sessions:
        return []

    def is_success(s: Session) -> bool:
        return s.success or (s.proxy_label >= success_threshold and s.human_d_label is None) \
            or (s.human_d_label is not None and s.human_d_label >= 0.5)

    # 收集每个参数的 treated / control 会话
    params: Dict[str, List[Session]] = {}
    for s in sessions:
        if not s.proposal:
            continue
        name, old_v, new_v = parse_change(s.proposal.get("L3", ""))
        if not name:
            # 提案存在但解析不出参数名：仍计入"方向一致性"的粗粒度（按 L2 层）
            layer = s.proposal.get("L2") or "unknown_layer"
            params.setdefault(layer, []).append(s)
            continue
        params.setdefault(name, []).append(s)

    results: List[ParamAttribution] = []
    for name, treated in params.items():
        control = [s for s in sessions if s not in treated]   # 未应用该提案的会话
        n_t, n_c = len(treated), len(control)

        # ---- ① 组间差异法：平均代理分（深放松占比的机器代理）----
        d = _cohens_d([s.proxy_label for s in treated], [s.proxy_label for s in control]) if control else 0.0

        # ---- ② 方向一致性法：成功率对比 + 单调性 ----
        sr_t = sum(1 for s in treated if is_success(s)) / n_t
        sr_c = (sum(1 for s in control if is_success(s)) / n_c) if control else None
        direction_ok = bool(sr_c is not None and sr_t >= sr_c)

        # 单调性：改动幅度（|new-old|）与代理分是否同向（仅当 ≥2 条可解析数值且方向一致时才有意义）
        monotonic_ok: Optional[bool] = None
        pairs = []
        for s in treated:
            _, old_v, new_v = parse_change((s.proposal or {}).get("L3", ""))
            if old_v is not None and new_v is not None:
                pairs.append((abs(new_v - old_v), s.proxy_label))
        if len(pairs) >= 2:
            xs = np.array([p[0] for p in pairs], dtype=float)
            ys = np.array([p[1] for p in pairs], dtype=float)
            if xs.std() > 0 and ys.std() > 0:
                r = float(np.corrcoef(xs, ys)[0, 1])
                # "改得越多越好"或"改得越少越好"都算单调；符号不定才算失败
                monotonic_ok = abs(r) >= 0.5

        conf, warns = _confidence(n_t, n_c, direction_ok, monotonic_ok)
        results.append(ParamAttribution(
            param=name,
            method="between_group+direction_consistency",
            n_treated=n_t,
            n_control=n_c,
            mean_proxy_treated=_mean([s.proxy_label for s in treated]),
            mean_proxy_control=_mean([s.proxy_label for s in control]) if control else None,
            effect_size_d=round(d, 3),
            success_rate_treated=round(sr_t, 3),
            success_rate_control=round(sr_c, 3) if sr_c is not None else None,
            direction_ok=direction_ok,
            monotonic_ok=monotonic_ok,
            confidence=conf,
            warnings=warns,
        ))

    results.sort(key=lambda r: (r.confidence, abs(r.effect_size_d)), reverse=True)
    return results


# ---------------------------------------------------------------------------
# 4. 内置合成样本（开箱即跑；数值刻意构造出"tau_ema 有效、vol_ramp 无效"）
# ---------------------------------------------------------------------------

def synthetic_sessions() -> List[Session]:
    """8 条合成会话：
    - tau_ema 10→20 的 4 条：代理分整体更高（模拟"EMA 窗口放宽 → 深放松占比↑"）；
    - vol_ramp 0.5→0.2 的 3 条：代理分无稳定提升（模拟"音量限幅改动无效"）；
    - 1 条无提案基线。
    频段功率按 neuradock_simulator._STATES 量级构造（µV²）。
    """
    raw = [
        # session_id, config, proposal, (alpha, theta, beta) µV²
        ("syn_s01", {"tau_ema": 20, "vol_ramp": 0.5}, {"L1": "反馈环层", "L2": "EMA窗口", "L3": "tau_ema 10→20"}, (9.6, 7.2, 2.4)),
        ("syn_s02", {"tau_ema": 20, "vol_ramp": 0.5}, {"L1": "反馈环层", "L2": "EMA窗口", "L3": "tau_ema 10→20"}, (8.8, 6.4, 2.8)),
        ("syn_s03", {"tau_ema": 20, "vol_ramp": 0.5}, {"L1": "反馈环层", "L2": "EMA窗口", "L3": "tau_ema 10→20"}, (9.2, 6.8, 2.6)),
        ("syn_s04", {"tau_ema": 20, "vol_ramp": 0.5}, {"L1": "反馈环层", "L2": "EMA窗口", "L3": "tau_ema 10→20"}, (7.9, 5.6, 3.4)),
        ("syn_s05", {"vol_ramp": 0.2}, {"L1": "音频层", "L2": "音量包络", "L3": "变化率限幅0.5→0.2"}, (8.9, 6.1, 2.7)),
        ("syn_s06", {"vol_ramp": 0.2}, {"L1": "音频层", "L2": "音量包络", "L3": "变化率限幅0.5→0.2"}, (4.2, 3.9, 8.1)),   # focus 态：改动无效
        ("syn_s07", {"vol_ramp": 0.2}, {"L1": "音频层", "L2": "音量包络", "L3": "变化率限幅0.5→0.2"}, (6.6, 12.0, 2.4)), # drowsy：改动无效
        ("syn_s08", {"tau_ema": 10, "vol_ramp": 0.5}, None, (7.0, 4.2, 3.0)),   # 无提案基线（relax 偏 focus）
    ]
    out = []
    for sid, cfg, prop, bands in raw:
        a, t, b = bands
        score = proxy_score(a, t, b) or 0.0
        out.append(Session(
            session_id=sid, config=cfg, proposal=prop,
            outcome={"alpha_power": a, "theta_power": t, "beta_power": b},
            proxy_label=score, human_d_label=None, success=False,
        ))
    return out


# ---------------------------------------------------------------------------
# 5. 报告输出
# ---------------------------------------------------------------------------

def render_report(sessions: List[Session], results: List[ParamAttribution], source: str) -> str:
    lines: List[str] = []
    n = len(sessions)
    low_conf_mode = n < GLOBAL_MIN_N
    lines.append("=" * 72)
    lines.append("止观AI 自归因器 v0 · 结果报告（仅供法师校准参考，不得直接采信）")
    lines.append(f"数据来源：{source}　|　有效会话数：{n}")
    if low_conf_mode:
        lines.append(f"[警告] 全局低置信模式：总样本 {n} < {GLOBAL_MIN_N}，所有结论降级为参考级。")
    lines.append("-" * 72)

    # 代理分分布速览
    scores = [s.proxy_label for s in sessions]
    if scores:
        arr = np.asarray(scores, dtype=float)
        lines.append(f"代理分：mean={arr.mean():.3f}  min={arr.min():.3f}  max={arr.max():.3f}")
    d_labeled = [s for s in sessions if s.human_d_label is not None]
    if d_labeled:
        lines.append(f"法师 D 级标签：{len(d_labeled)} 条（稀疏、贵，优先用于校准代理分）")
    else:
        lines.append("法师 D 级标签：0 条 —— 建议按蓝图 §10-3 补 5 条人工标注以校准代理分。")

    if not results:
        lines.append("\n[空] 没有可归因的提案记录（proposal.L3 缺失或无法解析）。")
        lines.append("=" * 72)
        return "\n".join(lines)

    lines.append("")
    lines.append("参数有效性排名（置信度降序）：")
    for i, r in enumerate(results, 1):
        verdict = "√ 方向一致" if (r.direction_ok and r.confidence >= 0.5) else \
                  ("! 证据不足/方向存疑" if r.confidence < 0.5 else "× 方向不一致")
        lines.append("")
        lines.append(f"{i}. {r.param}　{verdict}")
        lines.append(f"   组间差异法：treated n={r.n_treated} mean={r.mean_proxy_treated}"
                     f" | control n={r.n_control} mean={r.mean_proxy_control}"
                     f" | Cohen's d={r.effect_size_d:+.3f}")
        lines.append(f"   方向一致性：成功率 treated={r.success_rate_treated}"
                     f" vs control={r.success_rate_control}"
                     + (f" | 单调性={'通过' if r.monotonic_ok else '未通过'}" if r.monotonic_ok is not None else ""))
        lines.append(f"   confidence={r.confidence:.3f}")
        for w in r.warnings:
            lines.append(f"   [!] {w}")

    # 经验池四元组样例（蓝图 §6/§7）：把归因写回记录，供落库检索
    top = results[0]
    if top.confidence >= 0.5 and top.direction_ok:
        lines.append("")
        lines.append(f"建议写入经验池（待法师闸门确认后才生效）："
                     f'{{"key_step": "{top.param}", "confidence": {top.confidence}}}')
    else:
        lines.append("")
        lines.append("本轮无参数达到可写经验池的置信门槛 —— 保持现状，继续积累样本。")

    lines.append("=" * 72)
    lines.append("纪律提醒：AI 无提案自动生效权；所有改动经法师闸门确认（§四ter 红线）。")
    return "\n".join(lines)


def to_json(sessions: List[Session], results: List[ParamAttribution]) -> str:
    payload = {
        "tool": "attribution_v0",
        "version": "0.1",
        "disclaimer": "仅供法师校准参考，不得直接采信；AI 无提案自动生效权。",
        "n_sessions": len(sessions),
        "low_confidence_mode": len(sessions) < GLOBAL_MIN_N,
        "sessions": [
            {"session_id": s.session_id, "proxy_label": s.proxy_label,
             "human_d_label": s.human_d_label, "proposal": s.proposal}
            for s in sessions
        ],
        "attribution": [
            {k: getattr(r, k) for k in (
                "param", "n_treated", "n_control", "mean_proxy_treated",
                "mean_proxy_control", "effect_size_d", "success_rate_treated",
                "success_rate_control", "direction_ok", "monotonic_ok",
                "confidence", "warnings")}
            for r in results
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 6. CLI
# ---------------------------------------------------------------------------

def _force_utf8_stdio() -> None:
    """Windows 下重定向输出默认走 locale(GBK)，统一改 UTF-8 便于管道/落库；
    真实控制台仍走宽字符 API（WriteConsoleW），显示不受影响。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):  # pragma: no cover
            pass


def main(argv: Optional[List[str]] = None) -> int:
    _force_utf8_stdio()
    ap = argparse.ArgumentParser(description="止观AI 自归因器 v0（纯 Python+numpy，无 GPU）")
    ap.add_argument("--data", help="四元组 JSONL 路径（蓝图 §7 schema）。缺省用内置合成样本。")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出结果（供经验池落库）。")
    ap.add_argument("--success-threshold", type=float, default=0.4,
                    help="代理分成功阈值（v0 默认 0.4；蓝图 §10-2 后续可换 deep_state_ratio 判据）")
    args = ap.parse_args(argv)

    if args.data:
        sessions, skipped = load_sessions(args.data)
        source = args.data
        if any(skipped.values()):
            print(f"[INFO] 跳过记录：{skipped}", file=sys.stderr)
    else:
        sessions = synthetic_sessions()
        source = "内置合成样本（synthetic，仅演示输出格式）"

    results = attribute(sessions, success_threshold=args.success_threshold)

    if args.json:
        print(to_json(sessions, results))
    else:
        print(render_report(sessions, results, source))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
