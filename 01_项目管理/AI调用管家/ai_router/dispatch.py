"""派工前的一次问：这个活走哪条通道、预计花多少。

只读出口：产出一段能贴进派工单的结论文本。它不写中枢、不改源表、不动账本，
只把路由层已有的判断整理成「人可以直接抄走」的字。
"""

from __future__ import annotations

import time

from . import plans, router, store

CONTEXT_TOKENS = {"小": 30_000, "中": 80_000, "大": 180_000}

# 预计花费的输出口径：输出 token 按这个数算，实际用量以账本为准。
OUTPUT_TOKEN_ESTIMATE = 2000


def build_plan(task: str, context: str, unattended: bool, task_id: str = "",
               need_harness: bool = False, context_tokens: int = 0) -> dict:
    tokens = context_tokens or CONTEXT_TOKENS.get(context, 30_000)
    profile = plans.TaskProfile(task=task, context=context, unattended=unattended,
                                 need_harness=need_harness)
    decision = router.decide(profile, context_tokens=tokens)

    tagged = (store.clean_task_id(task_id)
              or store.clean_task_id(store.get_current_task().get("任务号", ""))
              or store.UNTAGGED)

    plan = {
        "任务号": tagged,
        "活类": task_label(profile.task),
        "上下文": context,
        "上下文token": tokens,
        "无人值守": bool(profile.unattended),
        "通道": decision.channel,
        "通道名": store.CHANNEL_LABEL.get(decision.channel, decision.channel),
        "模型": decision.model,
        "预计美元": decision.estimated_usd,
        "预计积分": decision.estimated_credits,
        "理由": decision.why,
        "备选": list(decision.fallback),
        # 「候选：某模型」是路由内部的挑选痕迹，结论里已有「用哪个模型」一行，去掉免得重复。
        "注意": [w for w in decision.warnings if not w.startswith("候选：")],
        "封顶余量": _cap_room(decision.model),
        "窗口占用": router.window_status(decision.model),
        "生成时刻": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    return plan


def task_label(name: str) -> str:
    return {"短问": "短问", "写作": "写作", "改码": "改码",
            "批处理": "批处理", "推理": "推理"}.get(name, name)


def _cap_room(model: str) -> dict:
    """Go 侧模型的本月封顶余量；别的渠道给空字典。"""
    cap = plans.cap_for(model)
    if not cap:
        return {}
    used = store.spend_by_model().get(model, 0.0)
    return {"封顶": cap, "已用": used, "还剩": max(0.0, cap - used)}


def render_text(plan: dict) -> str:
    """给派工单用的一段话：每行一件事，能直接抄走。"""
    lines = []
    lines.append(f"【调用安排】{plan['任务号']}")
    lines.append(f"活类：{plan['活类']}｜上下文：{plan['上下文']}（约 {plan['上下文token']} token）"
                 f"｜无人值守：{'是' if plan['无人值守'] else '否'}")
    lines.append(f"走哪条通道：{plan['通道名']}")
    lines.append(f"用哪个模型：{plan['模型']}")
    if plan["预计美元"]:
        lines.append(f"预计花费：约 {plan['预计美元']:.2f} 美元"
                     f"（按输入 {plan['上下文token']} token、输出 {OUTPUT_TOKEN_ESTIMATE} token 估，实际以账本为准）")
    if plan["预计积分"]:
        lines.append(f"预计消耗：约 {plan['预计积分']:.0f} 积分")
    lines.append(f"为什么：{plan['理由']}")

    room = plan["封顶余量"]
    if room:
        lines.append(f"本月封顶余量：{plan['模型']} 封顶 {room['封顶']:.0f} 美元，"
                     f"已用 {room['已用']:.2f}，还剩 {room['还剩']:.2f} 美元")

    for name, ratio in plan["窗口占用"].items():
        lines.append(f"{name}窗口占用：{ratio:.0%}"
                     + ("（已过闸，换模型或隔一阵再用）" if ratio >= router.SOFT_STOP else ""))

    for item in plan["注意"]:
        lines.append(f"注意：{item}")
    if plan["备选"]:
        lines.append(f"备选：{'、'.join(plan['备选'])}")
    if plan["任务号"] == store.UNTAGGED:
        lines.append("提醒：这次没挂上任务号，事后按任务看账时分不出来。"
                     "派工前先设一次「设当前任务」或用 x-task-id 头。")
    lines.append(f"（生成时刻 {plan['生成时刻']}；本段由本机调用管家生成，不写中枢、不改源表）")
    return "\n".join(lines)


def render_one_line(plan: dict) -> str:
    """一行版：塞进表格或对话里用。"""
    cost = ""
    if plan["预计美元"]:
        cost = f"｜预计 {plan['预计美元']:.2f} 美元"
    elif plan["预计积分"]:
        cost = f"｜预计 {plan['预计积分']:.0f} 积分"
    warn = ""
    for name, ratio in plan["窗口占用"].items():
        if ratio >= router.SOFT_STOP:
            warn = f"｜{name}窗口 {ratio:.0%} 已过闸"
    return (f"{plan['任务号']}｜{plan['通道名']}｜{plan['模型']}{cost}{warn}")
