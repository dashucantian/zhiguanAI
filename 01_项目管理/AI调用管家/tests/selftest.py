"""自带检查：全部在本机跑，不出网、不碰密钥。

用假的本机服务冒充上游，验证四件事：
一、代理会把请求转给假上游，并按规则选模型；
二、每笔调用都记进账本，审计行字段齐全；
三、某模型用满九成封顶后，代理改走免费模型；
四、没密钥、口令不对、路径不对这三种情况都退对码，不把请求发出去。
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TMP_DIR = tempfile.mkdtemp(prefix="airouter_selftest_")
os.environ["AI_ROUTER_DATA_DIR"] = TMP_DIR
os.environ["AI_ROUTER_TOKEN"] = "selftest-token"
os.environ["OPENCODE_API_KEY"] = "selftest-key"
os.environ.pop("OPENCODE_GO_BASE", None)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai_router import cli, dispatch, plans, proxy, registry, router, store  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0


def check(condition: bool, label: str) -> None:
    global CHECKS
    CHECKS += 1
    if condition:
        print(f"  通过　{label}")
    else:
        print(f"  失败　{label}")
        FAILURES.append(label)


# ── 假上游 ───────────────────────────────────────────────────

class FakeUpstream(BaseHTTPRequestHandler):
    received: list[dict] = []
    received_headers: list[dict] = []

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        FakeUpstream.received.append(payload)
        FakeUpstream.received_headers.append(dict(self.headers))
        body = json.dumps({
            "id": "fake",
            "choices": [{"message": {"role": "assistant", "content": "好"}}],
            "usage": {
                "prompt_tokens": 10000,
                "completion_tokens": 500,
                "prompt_tokens_details": {"cached_tokens": 8000},
            },
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def start_fake() -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeUpstream)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def post(base: str, path: str, payload: dict, token: str = "selftest-token",
         extra_headers: dict | None = None) -> tuple[int, dict, dict]:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    headers.update(extra_headers or {})
    request = urllib.request.Request(
        base + path,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers=headers,
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=20) as response:
            return response.status, json.loads(response.read().decode("utf-8")), dict(response.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8")), dict(exc.headers)


# ── 各段检查 ─────────────────────────────────────────────────

def test_prices() -> None:
    print("一、单价与封顶表自检")
    for model, price in plans.PRICE.items():
        check(price["input"] >= 0 and price["output"] >= 0, f"{model} 单价非负")
    check(plans.CAP_GO["deepseek-v4.1-flash"] == 100.0, "DeepSeek V4.1 Flash 封顶 100 美元")
    check(plans.CAP_GO_PLUS["deepseek-v4.1-flash"] == 200.0, "Go Plus 档翻倍到 200 美元")
    check(plans.price_for("grok-4.7", 250_000)["input"] == 4.00, "Grok 超长上下文走更贵的一档")
    check(plans.price_for("deepseek-v4.1-flash", 0, off_peak=True)["input"] == 0.15, "DeepSeek 谷时半价")
    check(plans.is_deepseek_peak(2) and not plans.is_deepseek_peak(12), "DeepSeek 峰谷判定")


def test_router() -> None:
    print("二、路由决策自检")
    decision = router.decide(plans.TaskProfile(task="短问", context="小", unattended=False))
    check(decision.channel == "qoder", "有人在旁 → 走 Qoder")
    check(0 < decision.estimated_credits <= 4, "Qoder 估出积分")

    decision = router.decide(plans.TaskProfile(task="改码", context="大", unattended=True))
    check(decision.channel == "opencode", "无人值守 → 走 OpenCode Go")
    check(decision.model not in plans.BIG_CONTEXT_BANNED, "大上下文避开 15 美元封顶的模型")

    model, reasons = router.pick_model("短问", 30_000)
    check(model is not None and model not in plans.TRAIN_ON_REQUEST, "不挑会拿内容训练的模型")

    decision = router.decide(plans.TaskProfile(task="推理", context="小", unattended=True, need_harness=True))
    check(decision.channel == "bailian", "要联网搜索等 → 走百炼 Harness")


def test_budget_gate() -> None:
    print("三、预算闸自检")
    model = "mimo-v2.6-flash"
    cap = plans.cap_for(model)
    store.append_ledger({"渠道": "opencode", "模型": model, "美元": cap * 0.95, "次数": 1, "说明": "自测灌数"})
    chosen, notes = proxy.choose_model(model, 10_000)
    check(chosen == plans.FREE_FALLBACK[0], "用满九成后改走免费模型")
    check(any("改走免费模型" in n for n in notes), "闸门在理由里留痕")
    chosen, notes = proxy.choose_model("auto", 10_000)
    check(chosen != model, "自动选型也绕开打满的模型")


def test_proxy_roundtrip(fake_base: str, proxy_base: str) -> None:
    print("四、代理转发与记账自检")
    FakeUpstream.received.clear()
    before = len(store.read_ledger())
    code, body, headers = post(proxy_base, "/v1/chat/completions", {
        "model": "auto",
        "messages": [{"role": "user", "content": "写一段中文说明。"}],
    })
    check(code == 200, f"代理转发到假上游（拿到 {code}）")
    check(len(FakeUpstream.received) == 1, "假上游收到一次请求")
    sent_model = FakeUpstream.received[0]["model"] if FakeUpstream.received else ""
    check(sent_model not in ("", "auto"), f"代理替客户端定好了模型：{sent_model}")
    check(headers.get("x-ai-router-model") == sent_model, "响应头回带所选模型")
    check(bool(headers.get("x-ai-router-note")), "响应头带选型理由")

    rows = store.read_ledger()
    check(len(rows) == before + 1, f"账本多写一笔（{before} → {len(rows)}）")
    row = rows[-1] if rows else {}
    check(row.get("模型") == sent_model, "账本记的模型与实际一致")
    check(row.get("美元", 0) > 0, f"账本记了金额（{row.get('美元')}）")
    check(row.get("输入") == 10000 and row.get("缓存读") == 8000, "账本记了 token 数")

    log_file = store.DATA_DIR / "审计.log"
    check(log_file.exists(), "审计日志有文件")
    if log_file.exists():
        line = log_file.read_text(encoding="utf-8").strip().splitlines()[-1]
        for field in ("task=", "time=", "channel=", "action=", "http=", "summary=", "level=", "approver=", "target=", "elapsed_ms="):
            check(field in line, f"审计行含 {field[:-1]}")
        check("OPENCODE_API_KEY" not in line and "selftest-key" not in line, "审计行不含密钥")


def test_proxy_guards(proxy_base: str) -> None:
    print("五、代理护栏自检")
    code, body, _ = post(proxy_base, "/v1/chat/completions", {"model": "auto", "messages": []}, token="wrong")
    check(code == 401, f"口令不对退 401（实际 {code}）")

    code, body, _ = post(proxy_base, "/v1/not-allowed", {"model": "auto"})
    check(code == 404, f"路径不在白名单退 404（实际 {code}）")

    saved = os.environ.pop("OPENCODE_API_KEY")
    try:
        code, body, _ = post(proxy_base, "/v1/chat/completions", {"model": "auto", "messages": []})
        check(code == 503, f"没有密钥退 503（实际 {code}）")
        check("OPENCODE_API_KEY" in json.dumps(body, ensure_ascii=False), "503 提示里点明缺哪个环境变量")
    finally:
        os.environ["OPENCODE_API_KEY"] = saved


def test_store_roundtrip() -> None:
    print("六、账本读写自检")
    store.set_quota("bailian", 18000, 25500, "Credits", "自测")
    quota = store.load_quota()
    check(quota["bailian"]["剩余"] == 18000, "额度快照写进去了")
    check(quota["bailian"]["总额"] == 25500, "总额也记下了")
    by_channel = store.spend_by_channel(store.month_key())
    check("opencode" in by_channel, "按渠道能算出花费")
    check(by_channel["opencode"]["次数"] >= 1, "按渠道能算出次数")


def test_pool_quota() -> None:
    print("七、分池额度自检")
    store.set_pool("qoder", "套餐内 Credits", 5862, 6000, "Credits", "自测", "2026-11-30")
    store.set_pool("qoder", "Qwen 专属积分", 2000, 2000, "Credits", "自测", "2026-11-28")
    pools = store.get_pools("qoder")
    check(len(pools) == 2, f"两个池子都记下了（实际 {len(pools)}）")
    names = {p["名称"] for p in pools}
    check(names == {"套餐内 Credits", "Qwen 专属积分"}, "池名各归各位")
    check(store.pool_remaining("qoder") == 7862, f"两个池剩余能加总（实际 {store.pool_remaining('qoder')}）")
    expires = {p["名称"]: p["到期"] for p in pools}
    check(expires["套餐内 Credits"] == "2026-11-30", "各池到期日分开记")
    check(expires["Qwen 专属积分"] == "2026-11-28", "各池到期日分开记")
    store.set_pool("qoder", "套餐内 Credits", 100, 6000, "Credits", "改录", "2026-11-30")
    check(len(store.get_pools("qoder")) == 2, "同名池改录是覆盖不是追加")
    check(store.pool_remaining("qoder") == 2100, f"覆盖后余额正确（实际 {store.pool_remaining('qoder')}）")


def test_go_channel_facts() -> None:
    print("八、Go 通道事实自检")
    check("x-opencode-session" in plans.GO_REQUIRED_HEADERS, "Go 必须带 x-opencode-session")
    check("User-Agent" in plans.GO_REQUIRED_HEADERS, "Go 必须带浏览器式 User-Agent")
    check("inference/go" in plans.GO_ENDPOINTS["官方"], "Go 官方入口是 inference/go")
    check(plans.GO_ENDPOINTS["非Go_另一计费路径"].endswith("/inference/v1"), "非 Go 路径单列，不会混用")
    check(plans.BAILIAN_CURRENT["档"] == "standard", "本机百炼档位是 standard")
    check(plans.BAILIAN_CURRENT["到期"] == "2027-11-01", "百炼到期日记的是订阅年")


def test_window_guard() -> None:
    print("九、5 小时窗口自检")
    model = "grok-4.7"
    cap = plans.cap_for(model)
    five_hour_cap = cap * router.WINDOW_5H_RATIO
    before = router.spend_in_window(model, 5)
    check(before >= 0, "窗口花费读得到")
    # 记一笔超窗口上限的账，再看预警是否触发
    store.append_ledger({"渠道": "opencode", "模型": model, "美元": five_hour_cap * 1.2,
                         "说明": "自测：模拟 5 小时窗口打爆"})
    after = router.spend_in_window(model, 5)
    check(after > before, "新记的一笔进了窗口统计")
    warnings = router._window_warnings(model)
    check(any("5 小时" in w for w in warnings), f"窗口打爆有预警（实际 {warnings}）")
    # 别人的模型不受影响
    check(not any("5 小时" in w for w in router._window_warnings("glm-5.3-flash")), "别的模型不误报")
    # 周窗口上限是月上限的一半
    check(router.WINDOW_WEEK_RATIO == 0.50, "周上限占月上限一半")


def test_proxy_go_headers(proxy_base: str) -> None:
    print("十、代理 Go 头自检")
    FakeUpstream.received_headers.clear()
    code, _body, _hdr = post(proxy_base, "/v1/chat/completions",
                             {"model": "deepseek-v4.1-flash", "messages": [{"role": "user", "content": "hi"}]})
    check(code == 200, f"代理转发成功（实际 {code}）")
    sent = FakeUpstream.received_headers[-1] if FakeUpstream.received_headers else {}
    lower = {k.lower(): v for k, v in sent.items()}
    check(bool(lower.get("x-opencode-session")), "上游请求带上了 x-opencode-session")
    check("Mozilla" in (lower.get("user-agent") or ""), "上游请求带上了浏览器式 User-Agent")
    check(lower.get("authorization") == "Bearer selftest-key", "上游只带环境变量里的密钥")
    leaked = [k for k, v in lower.items() if k != "authorization" and "sk-" in str(v)]
    check(not leaked, f"没有别的密钥混进去（发现 {leaked}）")
    check(bool(proxy.USER_AGENT), "代理默认 UA 常量在位")


def test_task_threading(proxy_base: str) -> None:
    print("十一、任务号贯穿自检")
    log_file = store.DATA_DIR / "审计.log"

    def send(headers: dict | None = None) -> None:
        code, _body, _hdr = post(proxy_base, "/v1/chat/completions",
                                 {"model": "deepseek-v4.1-flash",
                                  "messages": [{"role": "user", "content": "hi"}]},
                                 extra_headers=headers)
        check(code == 200, f"转发成功（实际 {code}）")

    send({proxy.TASK_HEADER: "TASK-TEST-001"})
    rows = store.read_ledger()
    check(rows[-1].get("任务号") == "TASK-TEST-001", f"账本记了任务号（实际 {rows[-1].get('任务号')}）")
    lines = log_file.read_text(encoding="utf-8").strip().splitlines() if log_file.exists() else []
    check("task=TASK-TEST-001" in (lines[-1] if lines else ""), "审计行的 task 是真任务号")

    before_lines = len(lines)
    # 客户端库本身就拦换行，所以脏值在服务端这一侧单测
    dirty = "bad-id\ntask=fake|x" + "L" * 80
    cleaned = store.clean_task_id(dirty)
    check("\n" not in cleaned and "|" not in cleaned and " " not in cleaned, "脏任务号里的危险字符被清掉")
    check(len(cleaned) <= 64, f"任务号截到 64 字符（实际 {len(cleaned)}）")
    check("task=fake" not in cleaned, "伪造字段没留下")
    resolved, _ws = proxy.resolve_task({proxy.TASK_HEADER: dirty})
    check(resolved == cleaned and "\n" not in resolved, "代理侧也是清洗后的值")
    check(store.clean_task_id("坏号 task=伪造") == "坏号-task-伪造", "清洗只换掉危险字符，中文保留")

    send({proxy.TASK_HEADER: "TASK-TEST-002"})
    lines2 = log_file.read_text(encoding="utf-8").strip().splitlines()
    check(len(lines2) == before_lines + 1, f"一次调用只留一行日志（{before_lines} → {len(lines2)}）")
    check("task=TASK-TEST-002" in lines2[-1], "第二个任务号也记上了")
    check(len(re.findall(r"(?:^|\s)(?:task|time|channel|action|http|summary|level|approver|target|elapsed_ms)=",
                         lines2[-1])) == 10, "审计行还是那十个字段，没多出别的字段")

    store.set_current_task("TASK-CURRENT-9")
    send()
    check(store.read_ledger()[-1].get("任务号") == "TASK-CURRENT-9", "没带头就用当前任务设定")

    send({proxy.TASK_HEADER: "TASK-HEADER-2"})
    check(store.read_ledger()[-1].get("任务号") == "TASK-HEADER-2", "客户端的头压过当前任务设定")

    store.set_current_task("")
    send()
    check(store.read_ledger()[-1].get("任务号") == store.UNTAGGED, "没有来源就写未标记，不编任务号")

    by_task = store.spend_by_task(store.month_key())
    check("TASK-TEST-001" in by_task, "按任务聚合能查到那个任务")
    check(by_task.get("TASK-TEST-001", {}).get("次数", 0) >= 1, "按任务聚合算得出次数")
    check(by_task.get("TASK-TEST-001", {}).get("美元", 0) > 0, "按任务聚合算得出钱")
    check(store.UNTAGGED in by_task, "没挂上任务的另归一档")


def test_dispatch_plan() -> None:
    print("十二、派工选型出口自检")
    import argparse

    store.set_current_task("TASK-DISPATCH-7")
    args = argparse.Namespace(任务="改码", 上下文="中", 无人值守=True, 任务号=None,
                              要联网搜索=False, 一行=False)
    plan = dispatch.build_plan("改码", "中", True, task_id="TASK-DISPATCH-7")
    check(plan["任务号"] == "TASK-DISPATCH-7", f"结论文本带任务号（实际 {plan['任务号']}）")
    check(plan["通道"] in plans.CHANNELS, f"通道在已知范围（实际 {plan['通道']}）")
    check(plan["通道"] == "opencode", "无人值守的改码活走 OpenCode Go")
    check(bool(plan["模型"]), "给了具体模型")
    check(plan["预计美元"] > 0, f"给了预计美元（{plan['预计美元']}）")
    check(plan["上下文token"] == 80_000, "中上下文按 8 万 token 估")

    text = dispatch.render_text(plan)
    for field in ("【调用安排】", "走哪条通道：", "用哪个模型：", "为什么：", "生成时刻"):
        check(field in text, f"结论文本含「{field}」")
    check("TASK-DISPATCH-7" in text, "结论文本里就是那个任务号")
    check("不写中枢" in text, "结论文本自报只读出口")
    one = dispatch.render_one_line(plan)
    check(one.startswith("TASK-DISPATCH-7｜"), f"一行版以任务号开头（实际 {one}）")
    check("｜" in one and one.count("｜") >= 2, "一行版用竖杠分栏")

    # 有人在环的活走 Qoder，消耗记成积分
    plan_q = dispatch.build_plan("写作", "小", False, task_id="TASK-DISPATCH-8")
    check(plan_q["通道"] == "qoder", "有人在旁走 Qoder")
    check(plan_q["预计积分"] > 0, "Qoder 那条给的是积分不是美元")
    check("预计消耗" in dispatch.render_text(plan_q), "积分那条措辞是「预计消耗」")

    # 没挂上任务号时要提醒，不能悄悄出单
    store.set_current_task("")
    plan_u = dispatch.build_plan("短问", "小", True, task_id="")
    check(plan_u["任务号"] == store.UNTAGGED, "没任务号就是未标记")
    check("提醒" in dispatch.render_text(plan_u), "未挂任务号时结论文本里会提醒")

    # 要联网搜索的能力走百炼 Harness
    plan_h = dispatch.build_plan("写作", "小", True, task_id="TASK-DISPATCH-9", need_harness=True)
    check(plan_h["通道"] == "bailian", "要 Harness 能力走百炼")

    # 派工选型是只读出口：不写账本、不写额度
    before_rows = len(store.read_ledger())
    before_quota = store.QUOTA_FILE.read_text(encoding="utf-8") if store.QUOTA_FILE.exists() else ""
    dispatch.build_plan("推理", "大", True, task_id="TASK-DISPATCH-10")
    check(len(store.read_ledger()) == before_rows, "选型不往账本写任何东西")
    after_quota = store.QUOTA_FILE.read_text(encoding="utf-8") if store.QUOTA_FILE.exists() else ""
    check(after_quota == before_quota, "选型不改额度快照")

    # 面板命令跑得起来，且能出文本
    out = io.StringIO()
    saved = sys.stdout
    sys.stdout = out
    try:
        rc = cli.cmd_dispatch(args)
    finally:
        sys.stdout = saved
    check(rc == 0, f"面板命令退码 0（实际 {rc}）")
    check("走哪条通道" in out.getvalue(), "面板命令打印了结论文本")


def test_reconcile_and_workspace() -> None:
    print("十三、账本对账与工作区真值自检")
    known = registry.registry_ids()
    check(bool(known), f"读得到任务登记的号集（{len(known)} 个号）")
    check("TASK-20261104-02" in known, "本窗这条任务号在任务登记里")

    check(registry.classify("TASK-20261104-02", known) == "合", "在登记里的号判「合」")
    check(registry.classify(store.UNTAGGED, known) == "未标记", "未标记判自己")
    check(registry.classify("", known) == "未标记", "空值算未标记")
    check(registry.classify("TASK-2026110402", known) == "笔误", "只差分隔符的判「笔误」")
    check(registry.classify("ZG-047", known) == "外部号", "飞书号判「外部号」")
    check(registry.classify("AI-026", known) == "外部号", "窗口号判「外部号」")
    check(registry.classify("完全不相干的字", known) == "外部号", "认不出的也不丢，归外部号待查")

    store.append_ledger({"渠道": "opencode", "模型": "deepseek-v4.1-flash", "美元": 0.5,
                         "次数": 1, "任务号": "TASK-20261104-02", "说明": "自测：合规号"})
    store.append_ledger({"渠道": "opencode", "模型": "deepseek-v4.1-flash", "美元": 0.4,
                         "次数": 1, "任务号": "ZG-999", "说明": "自测：外部号"})
    store.append_ledger({"渠道": "opencode", "模型": "deepseek-v4.1-flash", "美元": 0.3,
                         "次数": 1, "任务号": store.UNTAGGED, "说明": "自测：未标记"})
    report = registry.reconcile(store.month_key())
    dist = report["分布"]
    check(dist["合"]["次数"] >= 1, f"合类有数（{dist['合']['次数']}）")
    check(dist["外部号"]["次数"] >= 1, f"外部号类有数（{dist['外部号']['次数']}）")
    check(dist["未标记"]["次数"] >= 1, f"未标记类有数（{dist['未标记']['次数']}）")
    check(dist["合"]["任务号"] and "TASK-20261104-02" in dist["合"]["任务号"], "合类里能看见号")
    check("ZG-999" in dist["外部号"]["任务号"], "外部号原样列出，没被丢掉")
    total = sum(dist[k]["次数"] for k in dist)
    check(total == len([r for r in store.read_ledger() if r.get("月") == store.month_key()]),
          "四态次数加起来等于本月总笔数")

    # 工作区栏：填了不存在的路径要能看出来；隔离树判定认 _worktrees 且在盘
    rows = registry.workspace_rows(store.month_key())
    check(isinstance(rows, list), "工作区栏能读出列表")
    check(registry.is_worktree("") is False, "空路径不算隔离树")
    check(registry.is_worktree("D:/nonexistent/_worktrees/TASK-X") is False, "不在盘的目录不算隔离树")
    expect = registry.expected_worktree("TASK-20261104-02")
    check(expect.name == "TASK-20261104-02", f"隔离树路径按任务号命名（{expect.name}）")
    check(expect.parent.name == "_worktrees" and expect.parent.parent == registry.REPO_ROOT,
          f"隔离树在仓根 _worktrees 之下（{expect.parent}）")

    # 代理侧：没有来源时工作区栏为空，不编路径
    task, ws = proxy.resolve_task({})
    check(task == store.UNTAGGED and ws == "", "没有来源时任务号与工作区都不编")
    # 客户端带工作区就照用
    task2, ws2 = proxy.resolve_task({proxy.TASK_HEADER: "TASK-20261104-02",
                                     proxy.WORKSPACE_HEADER: "D:/Project/zhiguanAI"})
    check(ws2 == "D:/Project/zhiguanAI", "客户端带的工作区照用")

    # 隔离树真路径：不在盘不给，在盘才给
    check(registry.expected_workspace("") == "", "空任务号不给工作区")
    check(registry.expected_workspace(store.UNTAGGED) == "", "未标记不给工作区")
    check(registry.expected_workspace("TASK-20261104-02") == "", "隔离树不在盘时不填工作区")
    saved_root = registry.REPO_ROOT
    try:
        registry.REPO_ROOT = Path(TMP_DIR) / "repo"
        (registry.REPO_ROOT / "_worktrees" / "TASK-IN-DISK").mkdir(parents=True)
        got = registry.expected_workspace("TASK-IN-DISK")
        check(got.endswith("TASK-IN-DISK"), f"隔离树在盘时给出真路径（{got}）")
        check(registry.expected_workspace("TASK-NOT-THERE") == "", "隔离树不在盘仍不给路径")
    finally:
        registry.REPO_ROOT = saved_root

    # 面板「设当前任务」：隔离树不在盘时不编路径，人指定了照用
    import argparse
    rc = cli.cmd_current_task(argparse.Namespace(设置="TASK-20261104-02", 工作区=None))
    data = store.get_current_task()
    check(rc == 0, "面板「设当前任务」退码 0")
    check(data["任务号"] == "TASK-20261104-02", "设当前任务写进了任务号")
    check(data["工作区"] == "", "隔离树不在盘时工作区留空，不编路径")
    cli.cmd_current_task(argparse.Namespace(设置="TASK-20261104-02", 工作区="D:/Project/zhiguanAI"))
    check(store.get_current_task()["工作区"] == "D:/Project/zhiguanAI", "人指定的工作区照用")


def main() -> int:
    fake_server, fake_base = start_fake()
    os.environ["OPENCODE_GO_BASE"] = fake_base
    import importlib
    importlib.reload(proxy)

    router_server = ThreadingHTTPServer(("127.0.0.1", 0), proxy.Handler)
    threading.Thread(target=router_server.serve_forever, daemon=True).start()
    proxy_base = f"http://127.0.0.1:{router_server.server_address[1]}"

    try:
        test_prices()
        test_router()
        test_budget_gate()
        test_proxy_roundtrip(fake_base, proxy_base)
        test_proxy_guards(proxy_base)
        test_store_roundtrip()
        test_pool_quota()
        test_go_channel_facts()
        test_window_guard()
        test_proxy_go_headers(proxy_base)
        test_task_threading(proxy_base)
        test_dispatch_plan()
        test_reconcile_and_workspace()
    finally:
        router_server.shutdown()
        router_server.server_close()
        fake_server.shutdown()
        fake_server.server_close()
        shutil.rmtree(TMP_DIR, ignore_errors=True)

    print()
    print(_hr())
    if FAILURES:
        print(f"共 {CHECKS} 项，失败 {len(FAILURES)} 项：")
        for item in FAILURES:
            print(f"　· {item}")
        return 1
    print(f"共 {CHECKS} 项，全部通过。全程本机，未出网。")
    return 0


def _hr() -> str:
    return "─" * 58


if __name__ == "__main__":
    raise SystemExit(main())
