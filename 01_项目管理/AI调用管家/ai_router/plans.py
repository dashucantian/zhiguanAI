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

# Go Plus（40 美元/月）档封顶。2026-11-09 按官方页逐模型复核，订正四处：
# gemini-4-argon 90→120、glm-5.3 60→120、hy4-preview 90→120、muse-spark-1.3-contributor 180→120。
# 来源 opencode.ai/docs/console/go 的 Go Plus 表；同页 Go 表与本机 CAP_GO 逐项相符，未改。
CAP_GO_PLUS: dict[str, float | None] = {
    "deepseek-v4.1-flash": 200.0,
    "deepseek-v4-pro": 60.0,
    "grok-4.7": 60.0,
    "glm-5.3-flash": 180.0,
    "glm-5.3": 120.0,
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
    "muse-spark-1.3-contributor": 120.0,
    "qwen3.8-max": 60.0,
    "qwen3.8-flash": 90.0,
    "qwen3.7-plus": 180.0,
    "hy4-preview": 120.0,
    "hy3": 240.0,
    "gpt-6-luna": 60.0,
    "gpt-5.6-luna": 60.0,
    "claude-haiku-5-5": 60.0,
    "gemini-4-argon": 120.0,
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

# Go 的两个计费池（额度表里的池名）。
# 按月总额度＝订阅内的额度，用完后上游自动改走充值余额（2026-11-05 实测：
# usage.opencode.billing_source 变成 balance），此时按量价计费，不受每模型订阅封顶约束。
GO_PLAN_POOL = "按月总额度"
GO_BALANCE_POOL = "超额按量余额"

# 百炼／千问 Token Plan 个人版各档（官方文档数字）。
# 本机实订阅＝千问AI平台个人版 Standard（年付 2026-10-31 起，2027-11-01 到期，月额度按月重置）。
# 2026-11-05 法师定案：档位＝Standard 年付 139 元；并要开超额按量付费余额作缓冲。
BAILIAN_TIERS: dict[str, dict[str, object]] = {
    "lite": {"价格元每月": 39, "月Credits": 11500, "并发Agent": "1-2", "备注": "原价 60 元"},
    "essential": {"价格元每月": 79, "月Credits": 25500, "并发Agent": "2-3", "备注": "未订阅"},
    "standard": {"价格元每月": 139, "月Credits": 45000, "并发Agent": "3-4",
                 "备注": "本机订阅档（年付 139 元）；2026-11-05 法师定案"},
    "pro": {"价格元每月": 499, "月Credits": 180000, "并发Agent": "6-8", "备注": "含 Harness 权益"},
}

# 本机实际订阅的套餐（面板「录额度」时按这个口径报）。
# 限额口径以官方现行文档为准（2026-11-09 现读 help.aliyun.com/zh/model-studio/token-plan-personal-faq）：
#   · 个人版采用月限额，无周额度使用限制；旧文档的「7 天固定窗口」已作废，5 小时窗口官方现行页未列。
#   · 额度按订阅月刷新，重置日取决于订阅日期，不是每月 1 日。
#   · 额度用尽即阻断调用，不会转按量计费；恢复靠等下个订阅月、升级套餐、或买用量包
#     （100 元／20,000 Credits，最多同时持有 5 个）。这一点与 Go 相反：Go 开了 Extra Usage 会回落到余额。
BAILIAN_CURRENT = {
    "档": "standard",
    "平台": "千问AI平台 个人版",
    "开始": "2026-10-31",
    "到期": "2027-11-01",
    "月额度重置": "按订阅月（订阅日 2026-10-31 起算），非每月 1 日",
    "备注": "年付订阅；额度按订阅月重置，到期日是订阅年而非额度月；月内未用完不结转",
    "定案": "2026-11-05 法师定案：Standard 年付 139 元",
    "超额": "2026-11-05 法师令：开超额按量付费余额（余额与付款方式由法师在官网页面操作）",
    "超额口径冲突": "官方 FAQ 现行原文：个人版限额用完后调用会被阻断、不会按量计费。"
                    "法师那道令预期的「按量缓冲」在 Token Plan 专属通道上不成立，候法师裁（2026-11-09 记）",
}

# Token Plan 个人版的两条官方红线（2026-11-09 现读官方页逐字取，选池前必读）：
#   一、使用场景。FAQ 原文：「Token Plan 个人版仅供个人通过官方指定工具（如 Cursor、Claude Code、
#       Windsurf 等）进行交互式开发。不允许将 API Key 用于生产环境的自动化服务、批量脚本或后台定时
#       任务等非交互场景。」概述页列的适配工具含 Qoder／Qoder CN。
#       ⇒ 交互式走 Qoder 窗口在适配清单内；批量脚本与后台定时任务不在。
#   二、数据使用授权。概述页原文：「使用 Token Plan 个人版期间，模型输入以及模型生成的内容将用于
#       服务改进与模型优化。停止使用 Token Plan 个人版服务可终止后续数据授权，但终止授权的范围不
#       涵盖已授权使用的数据。」（阿里云百炼服务协议第 5.2 条）
#       ⇒ 这一池整体带数据授权，不只 muse-spark／iceman 那两个模型；项目内部件进这一池前须先脱敏。
# 两条都属法师裁定面，本模块不自行开关池子。
BAILIAN_RED_LINES = {
    "使用场景": "仅官方指定工具内交互式开发；禁生产自动化服务、批量脚本、后台定时任务",
    "数据授权": "输入与生成内容用于服务改进与模型优化；停用可终止后续授权，不含已授权数据",
    "来源": "help.aliyun.com/zh/model-studio/token-plan-personal-faq 与 token-plan-personal-overview",
    "现读时刻": "2026-11-09",
}

# Credits 折成人民币的参考：按官方用量包 100 元 / 20000 Credits 算，不是抵扣价。
CREDIT_CNY_REFERENCE = 0.005

# 百炼／Token Plan 的两个入口：不是同一份计费。
# 官方 FAQ 原文：误用百炼通用 dashscope.aliyuncs.com（或 Coding Plan 的 Key）会让请求走按量计费
# 通道，不抵扣套餐 Credits，且已产生的按量费用无法事后用 Credits 抵扣或退款。
# ⇒ 只有「Token Plan」这个入口＋专属 sk-sp- Key 才吃套餐额度；「百炼」那个入口花的是真钱。
BAILIAN_ENTRANCES = {
    "百炼": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "Token Plan": "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
}

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

# 免费兜底模型：名义上的退路，本机实际为空，别把它当绿灯。
#   · beam-free：官方页明文不在中国（含港澳）提供；2026-11-09 00:34 本机真调回 HTTP 403
#     RegionError「This model is not available in your country」，坐实不可用。
#   · iceman-contributor-free：在 TRAIN_ON_REQUEST 里，项目内容一律不走。
# 所以额度打穿后 Go 侧没有免费退路，只能回落到本地 Qwen 或百炼／Token Plan。
FREE_FALLBACK = ["beam-free", "iceman-contributor-free"]

# 官方页明文对本机所在地区不提供的模型（挑模型时直接跳过，不要发出去等 403）。
GO_REGION_BLOCKED = {"beam-free"}

CHANNELS = ("opencode", "bailian", "tokenplan", "local-qwen", "qoder")

# ── 跨池兜底（2026-11-05 法师准）────────────────────────────────
# 顺序＝同一件事有多个池能接时先走哪个：本地 Qwen → 百炼／Token Plan → OpenCode Go。
# 理由：本地与百炼不限量或按量计价，Go 最贵（按模型美元封顶＋三层窗口）。
POOL_ORDER = ("local-qwen", "bailian", "opencode")

# 只在客户端点名时才走的池：Qoder 客户端窗口不是通用兜底，它是「带工具、能看本机文件」
# 的那一路，得明确点名才切过去（自动兜底不经过它，见 pools.choose）。
POOL_NAMED_ONLY = ("qoder-window",)

# 每个池：接口、密钥环境变量名、能接的模型、以及客户端模型名到本池模型名的对应。
# 密钥只从环境变量读，不落盘、不进日志；本机没有该变量的池直接判为不可用。
POOLS: dict[str, dict[str, object]] = {
    "local-qwen": {
        "名称": "本地 Qwen3.8-27B",
        "接口": "http://127.0.0.1:8080/v1",
        "密钥变量": "",
        "候选": ["qwen-27b-512k"],
        "模型": {"qwen-27b-512k": "本地 Qwen3.8-27B 512K（llama.cpp Q4_K_M）"},
        "等价模型": {"qwen3.8-27b-local": "qwen-27b-512k"},
        "备注": "本机离线不花钱；服务没起就跳过这一池",
    },
    "bailian": {
        "名称": "百炼／Token Plan",
        "接口": BAILIAN_ENTRANCES["Token Plan"],
        "密钥变量": "TOKEN_PLAN_API_KEY",
        "候选": ["deepseek-v4.1-flash-1017", "glm-5.3", "qwen3.8-max", "deepseek-v4-pro-0813"],
        "模型": {
            "deepseek-v4.1-flash-1017": "DeepSeek-V4.1-Flash",
            "deepseek-v4-pro-0813": "DeepSeek-V4-Pro",
            "glm-5.3": "GLM-5.3",
            "qwen3.8-max": "Qwen3.8-Max",
            "wan2.7-image-pro": "Wan2.7-Image-Pro",
        },
        "等价模型": {
            "deepseek-v4.1-flash": "deepseek-v4.1-flash-1017",
            "deepseek-v4-pro": "deepseek-v4-pro-0813",
            "glm-5.3-flash": "glm-5.3",
            "qwen3.8-max": "qwen3.8-max",
        },
        "备注": "同一家产品同一份 Credits（千问AI平台个人版 Standard 年付 139 元）；与 tokenplan 是同一池两个入口",
    },
    "opencode": {
        "名称": "OpenCode Go",
        "接口": "",  # 代理里按 GO_BASE 现拼，Go 还要带专有头
        "密钥变量": "OPENCODE_API_KEY",
        "候选": [],  # Go 的候选从 TASK_CANDIDATES 取
        "模型": {},
        "等价模型": {},
        "备注": "Go 档；每模型美元封顶＋5 小时／周／月三层窗口",
    },
    "qoder-window": {
        "名称": "Qoder 客户端窗口",
        "接口": "http://127.0.0.1:8792/v1",
        "密钥变量": "",
        "候选": ["qoder-window"],
        "模型": {"qoder-window": "Qoder 客户端窗口（带工具，能看本机文件）"},
        "等价模型": {"qoder": "qoder-window", "qoder-客户端窗口": "qoder-window"},
        "备注": "本机 Qoder 客户端的无头工作进程；只点名才走；客户端要已登录（个人访问令牌或命令行登录态）",
    },
}

# 官方 Go 页列了、本机价目表没收的模型（2026-11-09 现读官方页点的差，不硬补进路由）。
GO_CONSOLE_GAPS = {
    "muse-spark-1.2-contributor": "官方页有：输入 0.10／输出 0.20／缓存读 0.002 美元每百万 token，"
                                  "Go 封顶 60、Go Plus 120；属 Contributor（会拿内容训练）且限地区，故不入路由",
    "crouton-alpha-free": "官方页有：免费、限时、Unlimited；明文不在中国（含港澳）等 22 个国家地区提供，故不入路由",
    "hy4": "官方页有（与 hy4-preview 并列）：输入 0.834／输出 2.501／缓存读 0.042，Go 封顶 60、Plus 240；未实测，暂不入路由",
    "mimo-v2.5": "官方页写作 MiMo-V2.5，本机价目表写作 mimo-v2.5-flash；是否同一个型号未核，暂不改名",
}

# EasyCLIProxyAPI（8317）里 OpenCode 那几组：一条组一个别名，都指本机管家（8791）。
# 管家按 POOL_ORDER 决定实际走哪个池，CPA 这一侧不持有任何上游密钥。
# 实测（旧版 CPA v8.0.47）：api-key 里不展开环境变量，keys 必填，组级 headers 会透传给上游，
# alias 会解析成上游的 name；同一个 name 在一组里只露一个别名，所以不同别名要分到不同组。
CPA_BASE_URL = "http://127.0.0.1:8791/v1"
CPA_CHAIN: tuple[dict[str, str], ...] = (
    {"组": "止观日常组", "模型": "deepseek-v4.1-flash", "别名": "止观-日常"},
    # 「止观-重活」原来指 gpt-6-luna，2026-11-05 实测那条被上游按地区挡回
    # （403 unsupported_country_region_territory），怎么调都调不通；
    # 换成同属「重活」定位的 deepseek-v4-pro，本机实测 HTTP 200。
    {"组": "止观重活组", "模型": "deepseek-v4-pro", "别名": "止观-重活"},
    {"组": "免费档组", "模型": "deepseek-v4.1-flash", "别名": "deepseek-v4.1-flash-free"},
    {"组": "通用组", "模型": "claude-haiku-5-5", "别名": "claude-haiku-5-5"},
    {"组": "通用组", "模型": "glm-5.3", "别名": "glm-5.3"},
    # 2026-11-06：Token Plan 通了以后加的一组。这两个模型不在 Go 的表里，
    # 走的是百炼／Token Plan 那一池（额度是 Credits，不吃 Go 的美元封顶）。
    {"组": "止观百炼组", "模型": "deepseek-v4.1-flash-1017", "别名": "止观-百炼-轻活"},
    {"组": "止观百炼组", "模型": "deepseek-v4-pro-0813", "别名": "止观-百炼-重活"},
)


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


def model_ids() -> list[str]:
    """Go 通道可调的模型清单：就是 CAP_GO 那把键，别处不再另立一份。"""
    return sorted(CAP_GO)


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
