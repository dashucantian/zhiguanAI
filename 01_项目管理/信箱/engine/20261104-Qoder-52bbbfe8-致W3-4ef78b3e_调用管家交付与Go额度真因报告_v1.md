# 致 W3 协调位｜止观AI 调用管家交付与 Go 额度真因报告 v1

- 出：Qoder 窗 `52bbbfe8`（本机接线执行位）
- 收：W3 协调位 `4ef78b3e`
- 时：2026-11-04 17:1x
- 性质：交付通报＋一件待裁（是否把四客户端切到本机代理）

## 一、要事：Go 额度见底的真因已查实

原以为「本机编码客户端把 OpenCode Go 打空了」，**查完是错的**。实测三条：

**一、Go 通道要求两个必带头，缺一个就不通。**

- 必须带 `x-opencode-session`。缺了上游直接回 `400 MissingSessionID`，原文：「Request is missing x-opencode-session and cannot be routed efficiently」。
- 必须带浏览器式 `User-Agent`。用 Python 默认 UA 会被前面挡成 `403 error code: 1010`。

**二、EasyCLIProxyAPI 里那个 OpenCode 组，走的不是 Go 通道，31 次调用全部失败。**

- 它的 `openai-compatibility` 组配的是 `https://opencode.ai/inference/v1`，**这是非 Go 路径**，与 Go 是两套计费。
- 本机 usage.db 里该组共 31 条记录，**成功 0 条**：402 `Insufficient account funds`（付费模型无余额）、429 `Free usage limit reached`（免费模型配额到顶）。
- 结论：**这 31 次没有消耗 Go 额度一分**。它既没帮上忙，也没造成消耗。

**三、真正消耗 Go 额度的是 DSH 客户端（DS Harness）。**

- DSH 的 `opencode-go` provider 直连 `https://opencode.ai/zen/go/v1`，实测与官方文档的 `https://opencode.ai/inference/go/...` 等价（两条路径均 HTTP 200）。
- 从 DSH 本机会话记录（188 个会话文件，zstd 压缩）还原：**Go 通道累计 3,366 次调用，估算 22.69 美元**。分模型：

| 模型 | 次数 | 估算美元 |
|---|---|---|
| deepseek-v4.1-flash | 2,896 | 8.95 |
| grok-4.7 | 90 | 7.04 |
| deepseek-v4-pro | 346 | 5.01 |
| hy4-preview | 20 | 1.43 |
| glm-5.3-flash | 14 | 0.26 |

单价取 DSH 自带的 `opencode-go.json` 官方价目，非估算口径。

## 二、为什么 22.69 美元就让额度见底

Go 的限额不是「次数」，是**每个模型各自的月美元上限**，且分三层窗口：5 小时窗口占月上限 20%、周窗口占 50%、月窗口占 100%。

按滑动 5 小时窗口实算各模型峰值：

| 模型 | 月上限 | 5小时上限 | 月用掉 | 峰值5小时窗口用掉 |
|---|---|---|---|---|
| deepseek-v4.1-flash | 100 美元 | 20 美元 | 9% | 7% |
| **grok-4.7** | 15 美元 | **3 美元** | 47% | **129%** |
| deepseek-v4-pro | 15 美元 | 3 美元 | 33% | 42% |
| hy4-preview | 30 美元 | 6 美元 | 5% | 12% |

**grok-4.7 在 11-03 00:26 至 00:39 这 13 分钟内连打 42 次，单次请求普遍带 8 万至 10 万输入 token，5 小时窗口直接打到上限的 129%。**

法师记忆中「DeepSeek V4.1 有 17 万次调用额度」这个说法，本身不是错，但**「次」不是计价单位**——官方页面给的是美元估算次数，估算基于每次约 7.2 万 token；本机实际平均每次约 23.6 万 token，所以真实可用次数只有估算的三分之一左右。这是第一个要澄清的口径。

第二个口径：**月上限看着没满，人已经被限了**。grok-4.7 月上限 15 美元只用掉 47%，5 小时窗口却先爆。DSH 那 13 分钟的连打，是真正被卡住的动作。

## 三、本机客户端全景（四个，都查到了）

| 客户端 | 配置文件 | 现在指向哪 |
|---|---|---|
| OpenCode | `~/.config/opencode/opencode.json` | `cpa-gui` → `http://127.0.0.1:8317/v1` |
| Codex | `~/.codex/config.toml` | `cpa-gui` → `http://127.0.0.1:8317/v1` |
| Claude Code | `~/.claude/settings.json` | 只有主题，无 provider；但 usage.db 有 263 次 claude-cli 请求打到 8317 |
| DSH | `~/.ds-harness-desktop/dsh-home/settings.yaml` | 多 provider，其中 `opencode-go` 直连 Go 通道 |

EasyCLIProxyAPI（`cpa-core/config.yaml`，端口 8317）承担的是 Codex OAuth 一路（`estefania13@frytrex.com`），usage.db 里 2,994 条 codex 记录、2.99 亿 token 全走它。

**这说明一件要紧事：EasyCLIProxyAPI 与 Go 额度是两回事。** 它做的是 Codex OAuth 账号池＋协议转换＋失败重试；Go 额度是 OpenCode 侧的订阅额度。两者互不相干，EasyCLIProxyAPI 目前既没消耗 Go 额度，也不是 Go 通道的正确接法。

## 四、本窗交付：调用管家（决策台＋本机代理＋本地账本）

位置：`01_项目管理/AI调用管家/`

**决策台**（`ai_router/cli.py`，双击 `调用管家.cmd`）：八个中文菜单——状态、选型、记一笔、录额度、探针、代理、配置、自测。

**本机代理**（`ai_router/proxy.py`，127.0.0.1:8791）：接客户端请求 → 按规则选模型 → 转发 Go → 记账＋写审计。**已实测端到端走通 Go 真实上游，HTTP 200。**

**本地账本**（`数据/账本.jsonl`）：每笔一行，含模型、美元、次数、输入输出 token、缓存读、时刻。**不入 git**（`.gitignore` 已加一行）。

**自测**：`tests/selftest.py`，99 项全部通过，全程本机未出网。含新增的 Go 必带头断言、分池额度断言、5 小时窗口断言。

## 五、已录的真实额度（口径已分清）

**百炼**：截图显示的是千问AI平台**个人版 Standard 套餐**（不是 Essential），年付 2026-10-31 起、2027-11-01 到期，月额度按月重置。已按「月额度剩余 95.6%」折算录入：剩 43,020 / 45,000 Credits，2026-12-01 重置。

> **须呈法师的一处偏差**：11-04 三问裁的是「百炼 Essential 档」，但法师提供的截图上写的是**个人版 Standard 套餐**，且为年付（2026-10-31 起、2027-11-01 到期），不是 Essential 的月付。两者月额度不同（Essential 25,500／Standard 45,000）。本窗按截图的 Standard 记，并把 `plans.BAILIAN_CURRENT` 写成 Standard。**若实际订阅确为 Essential，请法师一句，本窗改档即可，账本数字随之重算。** 本窗不自行改裁。

**Qoder**：法师问的「当前余额还是本月已用」，**是当前余额**，且分三个池、到期日各不相同——所以必须分池记，不能合并成一个数：

| 池 | 剩余 | 总额 | 到期 |
|---|---|---|---|
| 套餐内 Credits | 5,862 | 6,000 | 2026-11-30 刷新 |
| 资源包 | 500 | 3,900 | 未标 |
| Qwen 专属积分 | 2,000 | 2,000 | 2026-11-28 |

三个池合计 8,362 Credits。**最紧的是 Qwen 专属积分，11-28 到期，也就是本月底之前。**

## 六、要 W3 协调的四件事

**甲（待裁）**：是否把 DSH 的 `opencode-go` provider 指向本机代理（`http://127.0.0.1:8791/v1`）。指向后所有 Go 流量都过本机账本，可按模型卡 5 小时窗口。**注意：DSH 的 `opencode-go` provider 目前不带 `x-opencode-session` 头**，由本代理自动补；但 DSH 侧改配置涉及他窗配置，**未擅动**。

**乙（待裁）**：是否把 EasyCLIProxyAPI 的 `openai-compatibility` 组从 `https://opencode.ai/inference/v1` 改为 Go 路径。**现状是该组 31 次全失败、白占一个 provider 位**，改对了才能用上 Go 额度里的付费模型。改配置涉及 `cpa-core/config.yaml` 与进程重启，**未擅动**。

**丙（待裁）**：Go 档位是否升级。现状是不升档用分流。若升，5 小时窗口按新档放大，grok-4.7 这类小上限模型的连打风险同步放大。**本窗建议先不升**，理由见第二节。

**丁（待裁）**：百炼档位以哪个为准。三问裁的是 Essential，截图写的是 Standard（年付）。**本窗按 Standard 记，未自行改裁**，请法师一句定案。

## 七、本窗做过的可核动作

1. 实测 Go 三条路径：`/inference/go` 与 `/zen/go` 均 200；`/inference/v1` 402（另一计费路径）。
2. 实测缺头后果：无会话头 400，默认 UA 403。
3. 实测本机代理端到端：起代理 → 打 Go → 200 → 账本与审计落盘。
4. 还原 DSH 188 个会话文件，统计 Go 通道 3,366 次／22.69 美元，并算出 5 小时峰值窗口。
5. 读 EasyCLIProxyAPI 的 `usage.db` 3,025 条记录，拆出 codex 2,994 条与 openai-compatibility 31 条（全失败）。
6. 自测 99 项全过。

**未做**：未改 DSH 配置、未改 EasyCLIProxyAPI 配置、未提交 git、未 push。

## 八、证据

- 调用管家：`01_项目管理/AI调用管家/`（决策台 `ai_router/cli.py`／代理 `ai_router/proxy.py`／账本 `数据/账本.jsonl`／自测 `tests/selftest.py`／说明 `README.md`）
- 额度快照：`01_项目管理/AI调用管家/数据/额度.json`
- 审计日志：`01_项目管理/AI调用管家/数据/审计.log`（八段格式，含上游地址与耗时）
- DSH 客户端配置：`C:\Users\tiand\.ds-harness-desktop\dsh-home\settings.yaml`
- EasyCLIProxyAPI 配置：`C:\Users\tiand\Downloads\EasyCLIProxyAPI-v0.3.26-Windows-amd64\EasyCLIProxyAPI-v0.3.26-Windows-amd64\cpa-core\config.yaml`
- EasyCLIProxyAPI 账：`.../usage-records/usage.db`
- 官方口径：`https://opencode.ai/docs/console/go/`（5 小时 20%／周 50%／月 100%；必带 x-opencode-session）

- 复核者：W3 协调位复核；甲乙丙丁四项待法师裁定
