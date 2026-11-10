"""路由决策：给一个任务画像，选出该走哪个渠道、哪个模型，并给出理由与预计消耗。"""

from __future__ import annotations

import time

from . import plans, store

SOFT_STOP = 0.90
WARN_AT = 0.80

# Go 的限额不只看月上限，还有 5 小时窗口（占月上限 20%）与周窗口（50%）。
# 实测教训：grok-4.7 在 11-03 00:26 的 5 小时窗口里打到月上限的 129%，当场被限。
WINDOW_5H_SECONDS = 5 * 3600
WINDOW_5H_RATIO = 0.20
WINDOW_WEEK_RATIO = 0.50


def spend_in_window(model: str, hours: float, now: float | None = None) -> float:
    """模型在最近 N 小时窗口内的花费。账本行带时刻，按窗口左边界滑。"""
    now = now if now is not None else time.time()
    left = now - hours * 3600
    total = 0.0
    for row in store.read_ledger():
        if row.get("渠道") != "opencode" or row.get("模型") != model:
            continue
        stamp = row.get("时刻")
        if not isinstance(stamp, str):
            continue
        try:
            moment = time.mktime(time.strptime(stamp, "%Y-%m-%d %H:%M:%S"))
        except ValueError:
            continue
        if left <= moment <= now:
            total += float(row.get("美元") or 0.0)
    return total


def _model_used_ratio(model: str, month: str | None = None) -> float | None:
    cap = plans.cap_for(model)
    if not cap:
        return None
    used = store.spend_by_model(month, exclude_balance=True).get(model, 0.0)
    return used / cap


def _window_warnings(model: str) -> list[str]:
    """5 小时窗口快满时提前喊。这是 Go 最容易踩的坑：月上限没到就被限。"""
    cap = plans.cap_for(model)
    if not cap:
        return []
    out: list[str] = []
    five_hour_cap = cap * WINDOW_5H_RATIO
    spent = spend_in_window(model, 5)
    if five_hour_cap > 0:
        ratio = spent / five_hour_cap
        if ratio >= SOFT_STOP:
            out.append(f"{model} 最近 5 小时已用掉窗口上限的 {ratio:.0%}，再打就会被限流，换模型或隔一阵再用")
        elif ratio >= WARN_AT:
            out.append(f"{model} 最近 5 小时已用掉窗口上限的 {ratio:.0%}，快到 5 小时上限了")
    week_cap = cap * WINDOW_WEEK_RATIO
    if week_cap > 0:
        week_ratio = spend_in_window(model, 24 * 7) / week_cap
        if week_ratio >= WARN_AT:
            out.append(f"{model} 最近一周已用掉周上限的 {week_ratio:.0%}，周上限只占月上限的一半")
    return out


def _peak_warning(model: str, utc_hour: int | None = None) -> str:
    if model not in plans.DEEPSEEK_MODELS:
        return ""
    utc_hour = time.gmtime().tm_hour if utc_hour is None else utc_hour
    if not plans.is_deepseek_peak(utc_hour):
        return ""
    return (
        f"现在正撞上 {model} 的峰值时段（UTC 01 至 04 点、06 至 10 点），价格翻倍；"
        "改成谷时或换用非峰模型更省。"
    )


def window_status(model: str) -> dict[str, float]:
    """某模型离 5 小时窗口与周窗口还有多远。用于派工单里写「别打这个模型」。"""
    cap = plans.cap_for(model)
    if not cap:
        return {}
    out: dict[str, float] = {}
    five_hour_cap = cap * WINDOW_5H_RATIO
    if five_hour_cap > 0:
        out["5 小时"] = spend_in_window(model, 5) / five_hour_cap
    week_cap = cap * WINDOW_WEEK_RATIO
    if week_cap > 0:
        out["一周"] = spend_in_window(model, 24 * 7) / week_cap
    return out


def pick_model(task: str, context_tokens: int, month: str | None = None) -> tuple[str | None, list[str]]:
    """在 OpenCode Go 内部按规则挑模型。返回（模型, 理由列表）。"""
    reasons: list[str] = []
    candidates = list(plans.TASK_CANDIDATES.get(task, plans.TASK_CANDIDATES["短问"]))
    big = context_tokens > 120_000
    if big:
        blocked = [m for m in candidates if m in plans.BIG_CONTEXT_BANNED]
        candidates = [m for m in candidates if m not in plans.BIG_CONTEXT_BANNED]
        if blocked:
            reasons.append("上下文很大，已避开单价高、封顶只有 15 美元的模型：" + "、".join(blocked))
    balance_mode = store.go_billing_mode() == plans.GO_BALANCE_POOL
    if balance_mode:
        reasons.append("按月总额度已用尽，现在走充值余额按量计费，不吃订阅的每模型封顶与窗口")
    for model in candidates:
        if model in plans.TRAIN_ON_REQUEST:
            continue
        if not balance_mode:
            ratio = _model_used_ratio(model, month)
            if ratio is not None and ratio >= SOFT_STOP:
                reasons.append(f"{model} 本月已用掉封顶的 {ratio:.0%}，不再推荐")
                continue
            if ratio is not None and ratio >= WARN_AT:
                reasons.append(f"{model} 本月已用掉封顶的 {ratio:.0%}，快满了")
            reasons.extend(_window_warnings(model))
        reasons.append(f"候选：{model}")
        return model, reasons
    for model in plans.FREE_FALLBACK:
        if model in plans.GO_REGION_BLOCKED:
            reasons.append(f"免费档 {model} 官方明文不在中国提供（本机真调回 403 RegionError），退不了")
            continue
        if model in plans.TRAIN_ON_REQUEST and "iceman" in model:
            reasons.append("免费档 iceman 会拿你的内容训练模型，项目内容不要用")
            continue
        reasons.append(f"额度都紧了，退到免费模型：{model}")
        return model, reasons
    reasons.append("Go 侧已无可用退路：免费档一个地区不可用、一个会拿内容训练；请回落本地 Qwen 或百炼")
    return None, reasons


def decide(profile: plans.TaskProfile, context_tokens: int = 40_000, month: str | None = None) -> plans.Decision:
    warnings: list[str] = []
    if profile.need_harness:
        return plans.Decision(
            channel="bailian",
            model="Harness 内置工具（联网搜索、图像、语音、知识库）",
            why="这类能力在百炼 Harness 里，订阅即享、不占 Credits；其他渠道要单买。",
            fallback=["OpenCode Go（联网搜索需另配 MCP）"],
            warnings=["Harness 的具体额度官方只写「订阅即享」，未给数字，用量另计。"],
        )

    if not profile.unattended:
        mode = {
            "短问": ("问答模式", 4 if profile.context != "小" else 3),
            "写作": ("问答模式", 4),
            "改码": ("编辑器代理模式", 12 if profile.context != "小" else 7),
            "推理": ("智能体代理模式", 50),
            "批处理": ("问答模式", 4),
        }.get(profile.task, ("问答模式", 4))
        decision = plans.Decision(
            channel="qoder",
            model=f"{mode[0]}（{profile.task}）",
            why="要人在环里过一遍的活，走 Qoder 最省来回；日常咨询用问答模式比代理模式省三到四倍。",
            estimated_credits=float(mode[1]),
            fallback=["OpenCode Go（本机代理）", "百炼 Token Plan"],
        )
        if profile.task == "批处理":
            decision.warnings.append("批量活不该在 Qoder 里手工做，放到无人值守通道更省。")
        if profile.context == "大":
            decision.warnings.append("大上下文在 Qoder 里积分涨得快，先把上下文压下来再问。")
        return decision

    model, reasons = pick_model(profile.task, context_tokens, month)
    if model is None:
        return plans.Decision(
            channel="qoder",
            model="问答模式",
            why="OpenCode 侧额度都到顶了，剩下的活改走 Qoder。",
            estimated_credits=4.0,
            fallback=["百炼 Token Plan"],
            warnings=reasons,
        )
    cap = plans.cap_for(model)
    price = plans.price_for(model, context_tokens)
    est = plans.estimate_usd(model, context_tokens)
    peak = _peak_warning(model)
    if peak:
        warnings.append(peak)
    if cap:
        warnings.append(f"{model} 这个月的封顶是 {cap:.0f} 美元，这是 OpenCode 侧最宽的几个上限之一。")
    return plans.Decision(
        channel="opencode",
        model=model,
        why="无人值守的活走 OpenCode Go 的本机代理，按规则选最省的模型。",
        estimated_usd=est,
        fallback=["beam-free", "iceman-contributor-free", "qoder", "bailian"],
        warnings=reasons + warnings,
    )
