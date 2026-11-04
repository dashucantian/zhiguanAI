"""中文面板：一条命令看懂「这个活该走哪、还剩多少、今天花了多少」。

命令一览（全部中文，直接在命令行敲）：
    面板                 打开本菜单
    状态                 看本月各渠道花了多少、各模型还剩多少
    设当前任务           把接下来这些调用挂到某个任务号上
    按任务看账           本月每条任务各花了多少、走的是哪些模型
    对账                 账本里的任务号跟任务登记对一遍，出合／未标记／外部号／笔误四态
    选型                 回答几个问题，告诉你这个活该走哪个渠道哪个模型
    派工选型             派工前问一次：走哪条通道、预计花多少（产出一段可贴的话）
    记一笔               手动补记一笔用量（比如你从官网页面看到的数字）
    录额度               把某个渠道的剩余额度抄进来
    探针                 读本机 opencode 的真实用量并回填账本
    代理                 启动本机自动分流代理
    配置                 打印接到代理的客户端配置片段
    自测                 跑一遍自带检查
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai_router import dispatch, plans, probe, proxy, registry, router, store

PLANS = ("go", "go-plus")


# ── 打印小工具 ────────────────────────────────────────────────

def _hr(char: str = "─") -> str:
    return char * 58


def _table(rows: list[list[str]], headers: list[str]) -> str:
    if not rows:
        return "（暂无记录）"
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], _width(cell))
    out = ["　".join(_pad(h, widths[i]) for i, h in enumerate(headers)),
           "　".join("─" * widths[i] for i in range(len(headers)))]
    for row in rows:
        out.append("　".join(_pad(cell, widths[i]) for i, cell in enumerate(row)))
    return "\n".join(out)


def _width(text: str) -> int:
    return sum(2 if ord(ch) > 0x2E80 else 1 for ch in text)


def _pad(text: str, width: int) -> str:
    return text + " " * max(0, width - _width(text))


def _bar(ratio: float, width: int = 20) -> str:
    filled = int(max(0.0, min(1.0, ratio)) * width)
    return "█" * filled + "░" * (width - filled)


def _money(value: float) -> str:
    return f"{value:.2f} 美元"


# ── 状态 ─────────────────────────────────────────────────────

def cmd_status(args: argparse.Namespace) -> int:
    month = store.month_key()
    quota = store.load_quota()

    print(_hr())
    print(f"本月（{month}）用得怎么样")
    print(_hr())

    by_channel = store.spend_by_channel(month)
    rows = []
    for channel, bucket in by_channel.items():
        rows.append([
            store.CHANNEL_LABEL.get(channel, channel),
            str(int(bucket["次数"])),
            _money(bucket["美元"]),
            f"{bucket['Credits']:.0f}",
        ])
    print(_table(rows, ["渠道", "次数", "花了", "积分"]))
    print()

    print("OpenCode Go 各模型：封顶、已用、还剩")
    used = store.spend_by_model(month)
    rows = []
    for model, cap in sorted(plans.CAP_GO.items(), key=lambda kv: (kv[1] is None, -(kv[1] or 0))):
        if cap is None:
            rows.append([model, "不限", _money(used.get(model, 0.0)), "不限", ""])
            continue
        spent = used.get(model, 0.0)
        ratio = spent / cap
        rows.append([
            model,
            f"{cap:.0f} 美元",
            _money(spent),
            _money(max(0.0, cap - spent)),
            f"{_bar(ratio)} {ratio:.0%}",
        ])
    print(_table(rows, ["模型", "本月封顶", "已用", "还剩", "进度"]))
    print()

    print("其他渠道的剩余额度（手工录入，见「录额度」）")
    for channel in ("bailian", "qoder"):
        pools = store.get_pools(channel)
        if not pools:
            print(f"　{store.CHANNEL_LABEL[channel]}：还没录入")
            continue
        for pool in pools:
            total = pool.get("总额")
            remaining = pool.get("剩余")
            unit = pool.get("单位", "Credits")
            line = f"　{store.CHANNEL_LABEL[channel]}／{pool.get('名称')}：剩 {remaining} {unit}"
            if total:
                line += f"（共 {total}，已用 {total - remaining}）"
            if pool.get("到期"):
                line += f"，{pool['到期']}"
            if pool.get("重置"):
                line += f"，{pool['重置']} 重置"
            if pool.get("备注"):
                line += f"（{pool['备注']}）"
            print(line)
    print()
    print(f"账本文件：{store.LEDGER_FILE}")
    return 0


# ── 选型 ─────────────────────────────────────────────────────

def cmd_pick(args: argparse.Namespace) -> int:
    if args.任务:
        task = args.任务
    else:
        print("这个活是哪一类？直接敲序号。")
        for i, key in enumerate(plans.TASK_CANDIDATES, 1):
            print(f"　{i}. {key}")
        raw = input("序号：").strip()
        task = list(plans.TASK_CANDIDATES)[int(raw) - 1] if raw.isdigit() else raw

    if args.上下文:
        context = args.上下文
    else:
        print("上下文大概多大？")
        for i, key in enumerate(("小", "中", "大"), 1):
            print(f"　{i}. {key}")
        raw = input("序号：").strip()
        context = ("小", "中", "大")[int(raw) - 1] if raw.isdigit() else raw

    unattended = args.无人值守
    if not unattended and not args.任务:
        answer = input("要你在旁边盯着吗？输入 y 表示盯着：").strip().lower()
        unattended = answer in ("n", "no", "否")

    profile = plans.TaskProfile(task=task, context=context, unattended=unattended)
    decision = router.decide(profile, context_tokens=_guess_context_tokens(context))

    print()
    print(_hr())
    print("结论")
    print(_hr())
    print(f"走哪里：{store.CHANNEL_LABEL.get(decision.channel, decision.channel)}")
    print(f"用哪个：{decision.model}")
    print(f"为什么：{decision.why}")
    if decision.estimated_usd:
        print(f"预计花：约 {_money(decision.estimated_usd)}")
    if decision.estimated_credits:
        print(f"预计耗：约 {decision.estimated_credits:.0f} 积分")
    if decision.fallback:
        print(f"备选：{'、'.join(decision.fallback)}")
    for item in decision.warnings:
        print(f"注意：{item}")
    print()
    return 0


def _guess_context_tokens(context: str) -> int:
    return {"小": 30_000, "中": 80_000, "大": 180_000}.get(context, 30_000)


# ── 派工选型 ─────────────────────────────────────────────────

def cmd_dispatch(args: argparse.Namespace) -> int:
    """派工前问一次：这活走哪条通道、预计花多少。产出可贴进派工单的一段话。"""
    task = args.任务
    if not task:
        print("这个活是哪一类？直接敲序号。")
        for i, key in enumerate(plans.TASK_CANDIDATES, 1):
            print(f"　{i}. {key}")
        raw = input("序号：").strip()
        task = list(plans.TASK_CANDIDATES)[int(raw) - 1] if raw.isdigit() else raw

    context = args.上下文
    if not context:
        print("上下文大概多大？")
        for i, key in enumerate(("小", "中", "大"), 1):
            print(f"　{i}. {key}")
        raw = input("序号：").strip()
        context = ("小", "中", "大")[int(raw) - 1] if raw.isdigit() else raw

    unattended = args.无人值守
    if not unattended and not args.任务:
        answer = input("要你在旁边盯着吗？输入 y 表示盯着：").strip().lower()
        unattended = answer in ("n", "no", "否")

    plan = dispatch.build_plan(task, context, unattended,
                              task_id=args.任务号 or "",
                              need_harness=args.要联网搜索)
    print()
    if args.一行:
        print(dispatch.render_one_line(plan))
    else:
        print(dispatch.render_text(plan))
    print()
    return 0


# ── 记一笔 / 录额度 ──────────────────────────────────────────

def cmd_record(args: argparse.Namespace) -> int:
    model = args.模型 or input("模型名（比如 grok-4.7）：").strip()
    if not model:
        print("没有模型名，记不了。")
        return 2
    usd = args.美元
    if usd is None:
        raw = input("花了多少美元：").strip()
        usd = float(raw) if raw else 0.0
    count = args.次数 if args.次数 is not None else 1
    record = {
        "渠道": args.渠道 or "opencode",
        "模型": model,
        "美元": float(usd),
        "次数": int(count),
        "任务号": store.clean_task_id(args.任务号) or store.get_current_task().get("任务号") or store.UNTAGGED,
        "说明": args.说明 or "手工补记",
    }
    store.append_ledger(record)
    print(f"已记一笔：{record['模型']}　{_money(record['美元'])}　{record['说明']}")
    print(f"任务号：{record['任务号']}")
    print(f"账本文件：{store.LEDGER_FILE}")
    return 0


def cmd_quota(args: argparse.Namespace) -> int:
    channel = args.渠道
    if not channel:
        print("录哪个渠道？")
        print("　1. bailian（百炼 Token Plan）")
        print("　2. qoder（Qoder 积分）")
        raw = input("序号：").strip()
        channel = {"1": "bailian", "2": "qoder"}.get(raw, raw)
    if not channel:
        print("没有渠道，录不了。")
        return 2

    existing = store.get_pools(channel)
    print(f"这个渠道现在有 {len(existing)} 个池子。")
    for pool in existing:
        print(f"　· {pool.get('名称')}：剩 {pool.get('剩余')} {pool.get('单位')}"
              + (f"，到期 {pool['到期']}" if pool.get("到期") else ""))

    pool = args.池
    if not pool:
        raw = input("这是哪个池子（直接回车＝默认）：").strip()
        pool = raw or "默认"
    remaining = args.剩余
    if remaining is None:
        raw = input("还剩多少：").strip()
        remaining = float(raw) if raw else 0.0
    total = args.总额
    if total is None:
        raw = input("一共多少（没有就回车跳过）：").strip()
        total = float(raw) if raw else None
    expires = args.到期
    if expires is None:
        raw = input("哪天到期（没有就回车跳过）：").strip()
        expires = raw or ""
    resets = args.重置
    if resets is None:
        raw = input("哪天重置（没有就回车跳过）：").strip()
        resets = raw or ""

    store.set_pool(channel, pool, float(remaining),
                   float(total) if total is not None else None,
                   args.单位 or "Credits", args.说明 or "", expires, resets)
    print(f"已录入 {store.CHANNEL_LABEL.get(channel, channel)} 的「{pool}」池。")
    print(f"文件：{store.QUOTA_FILE}")
    return 0


# ── 当前任务 / 按任务看账 ─────────────────────────────────────

def cmd_current_task(args: argparse.Namespace) -> int:
    current = store.get_current_task()
    if args.设置:
        workspace = args.工作区 or ""
        auto = False
        if not workspace:
            # 没指定就去查这个任务号的隔离树在不在盘，在盘才填真路径。
            workspace = registry.expected_workspace(args.设置)
            auto = bool(workspace)
        data = store.set_current_task(args.设置, workspace)
        print(f"当前任务号已设为：{data['任务号']}")
        if data["工作区"]:
            label = "工作区（自动取隔离树真路径）：" if auto else "工作区："
            print(f"{label}{data['工作区']}")
        else:
            print("工作区：没填——这个任务号的隔离树不在盘，要填就加 --工作区 <路径>")
        print("从此走本代理的调用都记在这个任务号下；客户端自带 x-task-id 头的，以客户端带的为准。")
        print(f"文件：{store.TASK_FILE}")
        return 0
    print("当前任务设定")
    print(_hr())
    print(f"　任务号：{current.get('任务号') or '（没设）'}")
    print(f"　工作区：{current.get('工作区') or '（没设）'}")
    print(f"　设定时刻：{current.get('设定时刻') or '-'}")
    print()
    print("要设就敲：设当前任务 --设置 <任务号>（可加 --工作区 <路径>）")
    print(f"文件：{store.TASK_FILE}")
    return 0


def cmd_by_task(args: argparse.Namespace) -> int:
    month = args.月 or store.month_key()
    data = store.spend_by_task(month)
    print(f"本月（{month}）按任务看账")
    print(_hr())
    if not data:
        print("（本月还没有记账）")
        return 0
    rows = []
    for task, bucket in sorted(data.items(), key=lambda kv: -kv[1]["美元"]):
        rows.append([
            task,
            str(int(bucket["次数"])),
            _money(bucket["美元"]),
            f"{int(bucket['输入'] + bucket['输出']):,}",
            bucket["模型"],
        ])
    print(_table(rows, ["任务号", "次数", "花了", "token", "模型"]))
    print()
    print("客户端带了 x-task-id 头的按头走；没带的都归到「未标记」，一眼看出哪些活没挂上任务。")
    return 0


# ── 对账 ─────────────────────────────────────────────────────

def cmd_reconcile(args: argparse.Namespace) -> int:
    """账本里的任务号跟任务登记对一遍，出三态分布。"""
    month = args.月 or store.month_key()
    report = registry.reconcile(month)
    known = report["号集来源"]
    print(f"本月（{month}）任务号对账")
    print(_hr())
    print(f"号集来源：{known}（{report['号集大小']} 个号）")
    print()
    rows = []
    for kind in ("合", "未标记", "外部号", "笔误"):
        bucket = report["分布"][kind]
        rows.append([
            kind,
            str(int(bucket["次数"])),
            _money(bucket["美元"]),
            "、".join(bucket["任务号"]) if bucket["任务号"] else "—",
        ])
    print(_table(rows, ["判定", "次数", "花了", "任务号"]))
    print()
    print("口径：合＝这个号在任务登记里；未标记＝允许但要看得见；")
    print("　　　外部号／笔误＝不猜、不改、不丢，只是先记着。")
    print()

    workspaces = registry.workspace_rows(month)
    print("工作区栏")
    if not workspaces:
        print("（本月账本里还没填过工作区）")
    else:
        rows = []
        for item in workspaces:
            rows.append([
                item["工作区"],
                str(int(item["次数"])),
                _money(item["美元"]),
                "在盘" if item["在盘"] else "不在盘",
                "是隔离树" if item["是worktree"] else "不是隔离树",
            ])
        print(_table(rows, ["路径", "次数", "花了", "在盘", "隔离树"]))
    print()
    print(f"账本文件：{store.LEDGER_FILE}")
    return 0


# ── 探针 ─────────────────────────────────────────────────────

def cmd_probe(args: argparse.Namespace) -> int:
    stats = probe.read_stats(models=args.数量)
    if not stats.get("可用"):
        print(f"探针没跑通：{stats.get('原因')}")
        return 3
    totals = stats.get("总计", {})
    print(f"本机 opencode 用量（读数时刻 {stats.get('读数时刻')}）")
    print(_hr())
    for key, value in totals.items():
        print(f"　{key}：{value}")
    written = probe.import_to_ledger(stats)
    print()
    print(f"回填进账本 {written} 笔（同模型同月只补差额，不重复记）。")
    print(f"账本文件：{store.LEDGER_FILE}")
    return 0


# ── 代理 ─────────────────────────────────────────────────────

def cmd_proxy(args: argparse.Namespace) -> int:
    port = args.端口 or int(os.environ.get("AI_ROUTER_PORT", proxy.DEFAULT_PORT))
    print("本机代理只绑 127.0.0.1，上游密钥只从环境变量 OPENCODE_API_KEY 读。")
    if not os.environ.get("OPENCODE_API_KEY"):
        print("提示：当前没有 OPENCODE_API_KEY 环境变量，代理能起但转发会退 503。")
    proxy.serve(port)
    return 0


# ── 配置片段 ─────────────────────────────────────────────────

def cmd_config(args: argparse.Namespace) -> int:
    port = args.端口 or int(os.environ.get("AI_ROUTER_PORT", proxy.DEFAULT_PORT))
    base = f"http://127.0.0.1:{port}"
    print("把客户端的接口地址指到本机代理，模型名留 auto 就会自动选。")
    print("密钥仍放环境变量，本代理不落盘、不进日志。")
    print()
    print("【一】OpenCode　改 ~/.config/opencode/opencode.json")
    print(f'　provider 里加一段：{{"npm":"@ai-sdk/openai-compatible","options":{{"baseURL":"{base}/v1","apiKey":"<你的 AI_ROUTER_TOKEN>"}}}}')
    print("　再加 model 与 provider 两行，模型名写 auto")
    print()
    print("【二】Codex　改 ~/.codex/config.toml")
    print("　[model_providers.ai-router]")
    print(f'　base_url = "{base}/v1"')
    print('　wire_api = "responses"')
    print("　再把 model_provider 指向 ai-router")
    print()
    print("【三】Claude Code　改 ~/.claude/settings.json")
    print(f'　env 里加 ANTHROPIC_BASE_URL="{base}"、ANTHROPIC_AUTH_TOKEN="<你的 AI_ROUTER_TOKEN>"')
    print("　模型名写 auto")
    print()
    print("【四】DSH（DS Harness）　改 dsh-home/settings.yaml")
    print("　在某个 provider 下加 baseURL，指到本机代理的 /v1")
    print("　apiKeyEnv 仍指环境变量名，不写明文")
    print()
    print("【五】Kilo Code、Kilo、JCode 等 OpenAI 兼容客户端")
    print(f"　接口地址：{base}/v1　　密钥：AI_ROUTER_TOKEN 的值　　模型：auto")
    print()
    print("Anthropic 兼容写法：")
    print(f"　接口地址：{base}")
    print(f"　路径：/v1/messages")
    print("　模型：auto")
    print()
    print("Windows 上临时设置（只对当前窗口有效，不落盘）：")
    print(f"　set AI_ROUTER_TOKEN=你自己定的一串字符")
    print(f"　set OPENCODE_API_KEY=你的Go密钥")
    print(f"　set AI_ROUTER_PORT={port}")
    print()
    print("Go 通道要带 x-opencode-session 头，代理已经自动补上，你不用管。")
    print()
    print("【六】把调用挂到任务号上（这样才能按任务看账）")
    print("　最省事：面板里选「设当前任务」设一次，所有走本代理的调用都记在这个任务号下。")
    print("　想让每个客户端各挂各的，就在客户端配置里加一个头 x-task-id：")
    print("　　OpenCode　provider 的 options 里加 \"headers\": {\"x-task-id\": \"TASK-20261104-02\"}")
    print("　　Codex　　 [model_providers.ai-router] 里加 http_headers = { \"x-task-id\" = \"TASK-20261104-02\" }")
    print("　　DSH　　　 settings.yaml 的 provider 下加 headers: {\"x-task-id\": \"...\"}")
    print("　　Claude Code　settings.json 的 env 里加 ANTHROPIC_CUSTOM_HEADERS=\"x-task-id: TASK-20261104-02\"")
    print("　　　　　　　　这一条以你手上版本为准；不认这个变量就退回「设当前任务」，效果一样。")
    print("　代理端的优先级：客户端的头 > 设当前任务 > AI_ROUTER_TASK_ID > 未标记。")
    print("　AI_ROUTER_TASK_ID 是启动代理那个窗口里的环境变量，等于给整台机器定一个默认任务号。")
    return 0


# ── 自测 ─────────────────────────────────────────────────────

def cmd_selftest(args: argparse.Namespace) -> int:
    here = Path(__file__).resolve().parent.parent / "tests" / "selftest.py"
    import subprocess
    completed = subprocess.run([sys.executable, str(here)], cwd=str(here.parent))
    return completed.returncode


# ── 菜单 ─────────────────────────────────────────────────────

MENU = [
    ("状态", "看本月花了多少、各模型还剩多少", cmd_status, {}),
    ("设当前任务", "把调用挂到某个任务号上", cmd_current_task, {"设置": None, "工作区": None}),
    ("按任务看账", "本月每条任务各花了多少", cmd_by_task, {"月": None}),
    ("对账", "账本里的任务号跟任务登记对一遍", cmd_reconcile, {"月": None}),
    ("选型", "这个活该走哪个渠道、哪个模型", cmd_pick, {"任务": None, "上下文": None, "无人值守": False}),
    ("派工选型", "派工前问一次：走哪条通道、预计多少", cmd_dispatch, {"任务": None, "上下文": None, "无人值守": False, "任务号": None, "要联网搜索": False, "一行": False}),
    ("记一笔", "手工补记一笔用量", cmd_record, {"渠道": "opencode", "模型": None, "美元": None, "次数": None, "说明": None, "任务号": None}),
    ("录额度", "把百炼／Qoder 的剩余额度抄进来", cmd_quota, {"渠道": None, "池": None, "剩余": None, "总额": None, "单位": "Credits", "到期": None, "重置": None, "说明": None}),
    ("探针", "读本机 opencode 真实用量并回填", cmd_probe, {"数量": 20}),
    ("代理", "启动本机自动分流代理", cmd_proxy, {"端口": None}),
    ("配置", "打印接到代理的客户端配置", cmd_config, {"端口": None}),
    ("自测", "跑一遍自带检查", cmd_selftest, {}),
]


def cmd_panel(args: argparse.Namespace) -> int:
    while True:
        print()
        print(_hr("═"))
        print("AI 调用管家")
        print(_hr("═"))
        for i, (_, desc, _, _) in enumerate(MENU, 1):
            print(f"　{i}. {MENU[i - 1][0]}　—— {desc}")
        print("　0. 退出")
        try:
            raw = input("请选：").strip()
        except EOFError:
            print("输入没了，退出。")
            return 0
        if raw in ("0", "q", "Q", "退出", ""):
            print("再见。")
            return 0
        if not raw.isdigit() or not (1 <= int(raw) <= len(MENU)):
            print("没有这个序号。")
            continue
        name, _, func, defaults = MENU[int(raw) - 1]
        print()
        try:
            func(argparse.Namespace(**defaults))
        except KeyboardInterrupt:
            print("已取消。")
        except EOFError:
            print("输入没了，退出。")
            return 0
        except Exception as exc:  # noqa: BLE001
            print(f"出了点问题：{exc}")
    return 0


# ── 入口 ─────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="AI调用管家", description="三个订阅的调用分流管家")
    sub = parser.add_subparsers(dest="命令")

    sub.add_parser("面板", aliases=["panel"], help="打开中文菜单").set_defaults(func=cmd_panel)
    sub.add_parser("状态", aliases=["status"], help="看本月用量与剩余").set_defaults(func=cmd_status)

    p = sub.add_parser("设当前任务", aliases=["current-task"], help="设定当前任务号")
    p.add_argument("--设置", help="任务号，比如 TASK-20261104-02")
    p.add_argument("--工作区", help="工作区或 worktree 路径（可选）")
    p.set_defaults(func=cmd_current_task)

    p = sub.add_parser("按任务看账", aliases=["by-task"], help="按任务号看本月花费")
    p.add_argument("--月", help="月份，比如 2026-11")
    p.set_defaults(func=cmd_by_task)

    p = sub.add_parser("对账", aliases=["reconcile"], help="账本任务号与任务登记对账")
    p.add_argument("--月", help="月份，比如 2026-11")
    p.set_defaults(func=cmd_reconcile)

    p = sub.add_parser("选型", aliases=["pick"], help="选渠道与模型")
    p.add_argument("--任务", help="短问／写作／改码／批处理／推理")
    p.add_argument("--上下文", help="小／中／大")
    p.add_argument("--无人值守", action="store_true", help="不需要你在旁边盯")
    p.set_defaults(func=cmd_pick)

    p = sub.add_parser("派工选型", aliases=["dispatch"], help="派工前问一次走哪条通道、预计多少")
    p.add_argument("--任务", help="短问／写作／改码／批处理／推理")
    p.add_argument("--上下文", help="小／中／大")
    p.add_argument("--无人值守", action="store_true", help="不需要你在旁边盯")
    p.add_argument("--任务号", help="挂到哪个任务号上（不给就取本机当前任务）")
    p.add_argument("--要联网搜索", action="store_true", help="要联网搜索等 Harness 能力")
    p.add_argument("--一行", action="store_true", help="只打印一行，适合塞进表格")
    p.set_defaults(func=cmd_dispatch)

    p = sub.add_parser("记一笔", aliases=["record"], help="手工补记一笔")
    p.add_argument("--渠道", default="opencode")
    p.add_argument("--模型")
    p.add_argument("--美元", type=float)
    p.add_argument("--次数", type=int)
    p.add_argument("--说明")
    p.add_argument("--任务号")
    p.set_defaults(func=cmd_record)

    p = sub.add_parser("录额度", aliases=["quota"], help="录入剩余额度")
    p.add_argument("--渠道")
    p.add_argument("--池")
    p.add_argument("--剩余", type=float)
    p.add_argument("--总额", type=float)
    p.add_argument("--单位", default="Credits")
    p.add_argument("--到期")
    p.add_argument("--重置")
    p.add_argument("--说明")
    p.set_defaults(func=cmd_quota)

    p = sub.add_parser("探针", aliases=["probe"], help="读本机 opencode 用量")
    p.add_argument("--数量", type=int, default=20)
    p.set_defaults(func=cmd_probe)

    p = sub.add_parser("代理", aliases=["serve"], help="启动本机代理")
    p.add_argument("--端口", type=int)
    p.set_defaults(func=cmd_proxy)

    p = sub.add_parser("配置", aliases=["config"], help="打印客户端配置片段")
    p.add_argument("--端口", type=int)
    p.set_defaults(func=cmd_config)

    sub.add_parser("自测", aliases=["selftest"], help="跑自带检查").set_defaults(func=cmd_selftest)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        args = parser.parse_args(["面板"])
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
