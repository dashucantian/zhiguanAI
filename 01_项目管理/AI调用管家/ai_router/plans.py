"""订阅额度与单价数据（唯一真值源）。

数字来源：
- OpenCode Go 与 Go Plus 的每模型月度美元封顶、每百万 token 单价：opencode.ai/v2/docs/console/go
- 百炼 Token Plan 各档 Credits 限额与价格：help.aliyun.com/zh/model-studio/token-plan-overview
- Qoder 各模式 Credits 参考消耗：docs.qoder.com/zh/Credits

凡属估算或转述的数字都在「口径」字段里写明，不得当官方定价引用。
"""

from __future__ import annotations

from dataclasses import dataclass, field

# 每百万 token 单价：输入、输出、缓存读取、缓存写入。None 表示该模型该档免费。
PRICE: dict[str, dict[str, float]] = {
    "deepseek-v4.1-flash": {"input": 0.30, "output": 1.20, "cache_read": 0.006, "cache_write": 0.0},
    "deepseek-v4.1-flash-offpeak": {"input": 0.15, "output": 0.60, "cache_read": 0.003, "cache_write": 0.0},
    "deepseek-v4-pro": {"input": 1.32, "output": 3.96, "cache_read": 0.044, "cache_write": 0.0},
    "deepseek-v4-pro-offpeak": {"input": 0.66, "output": 1.98, "cache_read": 0.022, "cache_write": 0.0},
    "grok-4.7": {"input": 2.00, "output": 6.00, "cache_read": 0.50, "cache_write": 0.0},
    "grok-4.7-long": {"input": 4.00, "output": 12.00, "cache_read": 1.00, "cache_write": 0.0},
    "glm-5.3-flash": {"input": 0.15, "output": 0.50, "cache_read": 0.03, "cache_write": 0.0},
    "glm-5.3": {"input": 1.40, "output": 4.40, "cache_read": 0.26, "cache_write": 0.0},
    "glm-5.2": {"input": 1.40, "output": 4.40, "cache_read": 0.26, "cache_write": 0.0},
    "kimi-k3.1-pro": {"input": 2.00, "output": 10.00, "cache_read": 0.20, "cache_write": 2.00},
    "kimi-k3": {"input": 3.00, "output": 15.00, "cache_read": 0.30, "cache_write": 3.00},
    "kimi-k2.7-code": {"input": 0.95, "output": 4.00, "cache_read": 0.19, "cache_write": 0.0},
    "longcat-2.0": {"input": 0.30, "output": 1.20, "cache_read": 0.006, "cache_write": 0.0},
    "step-5-preview": {"input": 1.00, "output": 2.70, "cache_read": 0.10, "cache_write": 0.0},
    "mimo-v2.6-flash": {"input": 0.14, "output": 0.28, "cache_read": 0.0028, "cache_write": 0.0},
    "mimo-v2.6-pro": {"input": 0.435, "output": 0.87, "cache_read": 0.003625, "cache_write": 0.0},
    "mimo-v2.5-flash": {"input": 0.14, "output": 0.28, "cache_read": 0.0028, "cache_write": 0.0},
    "mimo-v2.5-pro": {"input": 0.435, "output": 0.87, "cache_read": 0.003625, "cache_write": 0.0},
    "minimax-m3.1-flash": {"input": 0.15, "output": 0.60, "cache_read": 0.015, "cache_write": 0.0},
    "minimax-m3": {"input": 0.30, "output": 1.20, "cache_read": 0.06, "cache_write": 0.0},
    "muse-spark-1.3-contributor": {"input": 0.10, "output": 0.20, "cache_read": 0.002, "cache_write": 0.0},
    "qwen3.8-max": {"input": 2.00, "output": 6.00, "cache_read": 0.25, "cache_write": 2.50},
    "qwen3.8-flash": {"input": 0.15, "output": 0.47, "cache_read": 0.016, "cache_write": 0.20},
    "qwen3.7-plus": {"input": 0.40, "output": 1.60, "cache_read": 0.04, "cache_write": 0.50},
    "hy4-preview": {"input": 0.834, "output": 2.501, "cache_read": 0.042, "cache_write": 0.0},
    "hy3": {"input": 0.14, "output": 0.58, "cache_read": 0.035, "cache_write": 0.0},
    "gpt-6-luna": {"input": 0.10, "output": 0.50, "cache_read": 0.01, "cache_write": 0.125},
    "gpt-5.6-luna": {"input": 0.20, "output": 1.20, "cache_read": 0.02, "cache_write": 0.25},
    "claude-haiku-5-5": {"input": 0.10, "output": 0.50, "cache_read": 0.01, "cache_write": 0.125},
    "gemini-4-argon": {"input": 2.00, "output": 10.00, "cache_read": 0.10, "cache_write": 0.0},
    "beam-free": {"input": 0.0, "output": 0.0, "cache_read": 0.0, "cache_write": 0.0},
    "iceman-contributor-free": {"input": 0.0, "output": 0.0, "cache_read": 0.0, "cache_write": 0.0},
}

# 上下文分档后的加价档（超阈按更贵的一档算）
LONG_CONTEXT_TIER = {
    "grok-4.7": ("grok-4.7-long", 200_000),
    "gpt-6-luna": (None, 272_000),
    "gpt-5.6-luna": (None, 272_000),
    "claude-haiku-5-5": (None, 100_000),
    "qwen3.7-plus": (None, 256_000),
    "minimax-m3": (None, 512_000),
}

# 每模型每月美元封顶：Go 档与 Go Plus 档。None 表示不限量。
CAP_GO: dict[str, float | None] = {
    "deepseek-v4.1-flash": 100.0,
    "deepseek-v4-pro": 15.0,
    "grok-4.7": 15.0,
    "glm-5.3-flash": 60.0,
    "glm-5.3": 15.0,
    "glm-5.2": 60.0,
    "kimi-k3.1-pro": 15.0,
    "kimi-k3": 15.0,
    "kimi-k2.7-code": 60.0,
    "longcat-2.0": 60.0,
    "step-5-preview": 15.0,
    "mimo-v2.6-flash": 60.0,
    "mimo-v2.6-pro": 15.0,
    "mimo-v2.5-flash": 60.0,
    "mimo-v2.5-pro": 15.0,
    "minimax-m3.1-flash": 20.0,
    "minimax-m3": 60.0,
    "muse-spark-1.3-contributor": 60.0,
    "qwen3.8-max": 15.0,
    "qwen3.8-flash": 30.0,
    "qwen3.7-plus": 60.0,
    "hy4-preview": 30.0,
    "hy3": 60.0,
    "gpt-6-luna": 15.0,
    "gpt-5.6-luna": 15.0,
    "claude-haiku-5-5": 15.0,
    "gemini-4-argon": 30.0,
    "beam-free": None,
    "iceman-contributor-free": None,
}

CAP_GO_PLUS: dict[str, float | None] = {
    "deepseek-v4.1-flash": 200.0,
    "deepseek-v4-pro": 60.0,
    "grok-4.7": 60.0,
    "glm-5.3-flash": 180.0,
    "glm-5.3": 60.0,
    "glm-5.2": 180.0,
    "kimi-k3.1-pro": 60.0,
    "kimi-k3": 60.0,
    "kimi-k2.7-code": 180.0,
    "longcat-2.0": 240.0,
    "step-5-preview": 60.0,
    "mimo-v2.6-flash": 120.0,
    "mimo-v2.6-pro": 60.0,
    "mimo-v2.5-flash": 120.0,
    "mimo-v2.5-pro": 60.0,
    "minimax-m3.1-flash": 80.0,
    "minimax-m3": 180.0,
    "muse-spark-1.3-contributor": 180.0,
    "qwen3.8-max": 60.0,
    "qwen3.8-flash": 90.0,
    "qwen3.7-plus": 180.0,
    "hy4-preview": 90.0,
    "hy3": 240.0,
    "gpt-6-luna": 60.0,
    "gpt-5.6-luna": 60.0,
    "claude-haiku-5-5": 60.0,
    "gemini-4-argon": 90.0,
    "beam-free": None,
    "iceman-contributor-free": None,
}

# 训练与留存：True 表示对方会用你的内容训练模型，项目内容一律不走这些。
TRAIN_ON_REQUEST: set[str] = {"muse-spark-1.3-contributor", "iceman-contributor-free"}

# Go 通道实测事实（本机 2026-11-04 实测，非推测）：
#   · Go 入口是 https://opencode.ai/inference/go/... ，官方文档另写 https://opencode.ai/zen/go/v1 ，两者等价（实测均 HTTP 200）。
#   · 必须带 x-opencode-session 头，否则上游回 400 MissingSessionID。
#   · 必须带浏览器式 User-Agent，否则被 Cloudflare 拦成 403 1010。
#   · 非 Go 的 https://opencode.ai/inference/v1 是另一条计费路径：本机 key 在其上 31 次调用全部失败
#     （402 Insufficient account funds / 429 Free usage limit），不消耗 Go 额度。
GO_ENDPOINTS = {
    "官方": "https://opencode.ai/inference/go/openai/v1/chat/completions",
    "官方_Anthropic": "https://opencode.ai/inference/go/anthropic/v1/messages",
    "等价别名": "https://opencode.ai/zen/go/v1/chat/completions",
    "非Go_另一计费路径": "https://opencode.ai/inference/v1",
}
GO_REQUIRED_HEADERS = ("x-opencode-session", "User-Agent")

# 百炼／千问 Token Plan 个人版各档（官方文档数字）。
# 本机实订阅＝千问AI平台个人版 Standard（年付 2026-10-31 起，2027-11-01 到期，月额度按月重置）。
BAILIAN_TIERS: dict[str, dict[str, object]] = {
    "lite": {"价格元每月": 39, "月Credits": 11500, "并发Agent": "1-2", "备注": "原价 60 元"},
    "essential": {"价格元每月": 79, "月Credits": 25500, "并发Agent": "2-3", "备注": "未订阅"},
    "standard": {"价格元每月": 139, "月Credits": 45000, "并发Agent": "3-4", "备注": "当前订阅档（年付）"},
    "pro": {"价格元每月": 499, "月Credits": 180000, "并发Agent": "6-8", "备注": "含 Harness 权益"},
}

# 本机实际订阅的套餐（面板「录额度」时按这个口径报）。
BAILIAN_CURRENT = {
    "档": "standard",
    "平台": "千问AI平台 个人版",
    "开始": "2026-10-31",
    "到期": "2027-11-01",
    "月额度重置": "每月 1 日 00:00",
    "备注": "年付订阅；额度按月重置，到期日是订阅年而非额度月",
}

# Credits 折成人民币的参考：按官方用量包 100 元 / 20000 Credits 算，不是抵扣价。
CREDIT_CNY_REFERENCE = 0.005

# Qoder 各模式 Credits 参考消耗（官方文档的统计估算值）
QODER_CREDIT_REFERENCE = {
    "问答_小上下文": 3,
    "问答_大上下文": 4,
    "编辑器代理_小上下文": 7,
    "编辑器代理_大上下文": 12,
    "智能体代理": 50,
    "知识库": 50,
}

# DeepSeek 峰值时段（UTC 小时区间），价格翻倍；其余时段含周末为谷时。
DEEPSEEK_PEAK_UTC = ((1, 4), (6, 10))
DEEPSEEK_MODELS = ("deepseek-v4.1-flash", "deepseek-v4-pro")

# 任务画像到候选模型的候选顺序。顺序即优先级，越前越省。
TASK_CANDIDATES: dict[str, list[str]] = {
    "短问": ["mimo-v2.6-flash", "glm-5.3-flash", "hy3", "deepseek-v4.1-flash"],
    "写作": ["mimo-v2.6-flash", "deepseek-v4.1-flash", "glm-5.3-flash", "hy3"],
    "改码": ["deepseek-v4.1-flash", "mimo-v2.6-flash", "glm-5.3-flash", "kimi-k2.7-code"],
    "批处理": ["deepseek-v4.1-flash", "mimo-v2.6-flash", "hy3", "longcat-2.0"],
    "推理": ["gpt-6-luna", "glm-5.3", "deepseek-v4-pro", "deepseek-v4.1-flash"],
}

# 大上下文时禁用的模型：单价高且月度封顶只有 15 美元。
BIG_CONTEXT_BANNED = {"grok-4.7", "gemini-4-argon", "kimi-k3.1-pro", "qwen3.8-max", "deepseek-v4-pro"}

# 免费兜底模型（额度打穿后仍可用）
FREE_FALLBACK = ["beam-free", "iceman-contributor-free"]

CHANNELS = ("opencode", "bailian", "qoder")


@dataclass(frozen=True)
class TaskProfile:
    task: str = "短问"
    context: str = "小"
    unattended: bool = False
    need_harness: bool = False

    @property
    def context_rank(self) -> int:
        return {"小": 0, "中": 1, "大": 2}.get(self.context, 0)


@dataclass
class Decision:
    channel: str
    model: str
    why: str
    estimated_usd: float = 0.0
    estimated_credits: float = 0.0
    fallback: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def cap_for(model: str, plan: str = "go") -> float | None:
    table = CAP_GO_PLUS if plan == "go-plus" else CAP_GO
    return table.get(model)


def price_for(model: str, context_tokens: int = 0, off_peak: bool = False) -> dict[str, float]:
    key = model
    if off_peak and model in DEEPSEEK_MODELS:
        key = f"{model}-offpeak"
    price = PRICE.get(key) or PRICE.get(model) or {"input": 0.0, "output": 0.0, "cache_read": 0.0, "cache_write": 0.0}
    tier = LONG_CONTEXT_TIER.get(model)
    if tier and context_tokens > tier[1]:
        alt = tier[0]
        if alt and alt in PRICE:
            price = PRICE[alt]
    return price


def estimate_usd(model: str, context_tokens: int, output_tokens: int = 2000, off_peak: bool = False) -> float:
    price = price_for(model, context_tokens, off_peak)
    return round(
        (context_tokens * price["input"] + output_tokens * price["output"] + context_tokens * 0.8 * price["cache_read"]) / 1_000_000,
        4,
    )


def is_deepseek_peak(utc_hour: int) -> bool:
    return any(start <= utc_hour < end for start, end in DEEPSEEK_PEAK_UTC)
