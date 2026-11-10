# Token Plan 接入与两处 astra 清理：实测证据（2026-11-06）

- 授权：法师 2026-11-06 字「我授权本窗去读 DSH 的凭据，搞清楚到底是百炼、千问，还是 token plan，并且配置到位。」「要删剩下那两处吗？如果是错误的，或者是没有必要的，那就删除。」
- 任务号：TASK-20261105-01
- 时刻：2026-11-06 14:24:34

## 一、密钥归属：三把都真打过两家入口

检索面：DSH 家目录 `.credentials.yaml` 的全部 refs 条目（只出名字、长度、sha256 前 12，**不打印值**）
＋ 用户级环境变量注册表 `HKEY_CURRENT_USER\Environment` 全部值名。

| 凭据 | 长度 | sha256 前 12 | Token Plan 入口 | 百炼 DashScope 入口 | 结论 |
|---|---|---|---|---|---|
| DSH `DSH_API_KEY` | 114 | 271ecd8b4efd | **HTTP 200「通了」** | HTTP 401 | **Token Plan 的密钥** |
| 用户级 `QIANWEN_API_KEY` | 115 | 408534951260 | HTTP 401 | HTTP 401 | 两边都不认，不可用 |
| DSH `OPENCODE_GO_API_KEY` | 51 | 9c0d2e45f159 | HTTP 401 | HTTP 401 | Go 的（`oc_` 开头），已另记在用户级 `OPENCODE_API_KEY` |

**那把用户级的密钥不是复制时多带了字符**：与 DSH 那把**逐位比对到第 16 位就分岔**；
三种修正式（去末位／去首位／去末位空白）真打**全是 401**。

## 二、配置到位的落点

- 管家读的变量名是 `TOKEN_PLAN_API_KEY`（`plans.POOLS["bailian"]["密钥变量"]`），用户级原先没有。
- 本窗把 DSH 那把 Token Plan 密钥写入用户级环境变量 `TOKEN_PLAN_API_KEY`；
  **回读长度 114、哈希与 DSH 凭据逐位一致**。**密钥值全程只在注册表与内存里流转，未打印、未落盘、未进日志。**
- 端到端真打（经本机代理 8791，点名 `deepseek-v4.1-flash-1017`）：**HTTP 200，回「通了」**，
  用量 `{"prompt_tokens": 35, "completion_tokens": 29, "reasoning_tokens": 26}`；
  账本落一行：渠道=bailian、入口=Token Plan、模型=deepseek-v4.1-flash-1017、美元 0、客户端=ai028-verify。

## 三、三个池的状态（14:12 实测）

| 池 | 状态 | 说明 |
|---|---|---|
| 本地 Qwen3.8-27B | 用不了 | 127.0.0.1:8080 上没服务 |
| 百炼／Token Plan | **能用** | 有额度（43,020 Credits）＋ 密钥已设 |
| OpenCode Go | 能用 | 按月总额度已用尽，走超额按量余额（剩 5.54 美元） |

**本地池为什么不开**：物理内存 31.6 GB、当时可用仅 7.3 GB，而 qwen3.8-27b 是 17.7 GB，
硬装会把整机拖垮（连着跑的 DSH、Qoder 一起卡）。**属于伤机器的动作，本窗不擅做**，候法师腾出内存后一键开。

## 四、CPA「止观百炼组」：让客户端真能点到 Token Plan

**缘由**：管家 `/v1/models` 的 29 条全是 Go 池模型（唯一真值源 `plans.CAP_GO`），百炼的模型名客户端点不着——
池通了却摸不到。

| 别名 | 背后的模型 | 入口 | 实测 | 账本 |
|---|---|---|---|---|
| 止观-百炼-轻活 | deepseek-v4.1-flash-1017 | 8317 → 8791 → Token Plan | HTTP 200 | 渠道=bailian、入口=Token Plan、美元 0 |
| 止观-百炼-重活 | deepseek-v4-pro-0813 | 同上 | HTTP 200 | 同上 |

`plans.py` 的 `CPA_CHAIN` 同步加两条（**唯一真值源**，自测第 17 组会把 CPA 真配置与它比对）。

**同名模型的归池规则**：名字先在哪个池里出现就归哪个池（`plans.POOL_ORDER` ＝ 本地 → 百炼 → Go）。
所以 `glm-5.3`、`qwen3.8-max` 两池都有 ⇒ **走百炼**（Credits）；`deepseek-v4.1-flash`、`deepseek-v4-pro`
只有 Go 有 ⇒ **走 Go**（美元余额）。想省美元就用带「百炼」字样的别名。

## 五、两处 astra 已清（先证死，再删）

**证死**：真打 `gpt-6-astra` 与 `GPT6-astra` 都回 `HTTP 400 unknown provider for model`；
CPA 活模型表 17 条里没有任何含 astra 的条目；管家 `plans.py` 的 `CAP_GO`／`CAP_GO_PLUS`／`model_ids()` 也都没有。

**删的两处**：
1. DSH web 出货层 `cordis.patch.yml` 的 `chatgpt` 模型表第 86–87 行；
2. CPA 真配置 `oauth.model-alias.codex` 段的 `- alias: "GPT6-astra"`、`fork: true`、`name: "gpt-6-astra"` 三行。

**保留**：CPA 第 1668 行还有一行 astra，整段是**注释掉的示例块**（文档），不动。

**备份**：`cordis.patch.yml.bak_AI028_20261106_141730`、`config.yaml.bak_20261106_141730_ai028`、
`config.yaml.bak_20261106_142204_ai028_bailian`（加百炼组前那份）。

**改后必验**：CPA 重启（新 PID 74104，起于 14:22:04）→ 模型表 19 条（含两个新别名）→
五个原别名（止观-日常／止观-重活／deepseek-v4.1-flash-free／claude-haiku-5-5／glm-5.3）逐个真打全 200。

## 六、自测与连带改动

- 自测 **258 → 263 项全过、退码 0**（`tests/selftest.py`）。
- 连带改两处：① CPA 别名清单加了百炼两条 ⇒ `CPA_CHAIN` 与「模型管家接得了」判据同步（判据改为
  「在 Go 表里或在百炼表里」）；② **「三个池都接不了退 503」那组用例原是靠「本机恰好没密钥」触发**——
  密钥一设上就变 200，自测当场变红。已改为把三池显式按下（`pools.pool_ready` 临时替身，用完复原），
  **不再依赖机器状态**。

## 七、未做与候裁

- 百炼超额按量付费余额未开（法师 11-05 字「有需要再说」；Token Plan 现可用、剩 43,020 Credits，暂时够用）。
- 本地 Qwen 池未开（内存不够，见第三节）。
- **DSH 默认模型未改**（现 ai-router／glm-5.3-flash；改默认是选型决定，且那次改动是法师自己在
  11-05 14:44–15:42 之间做的）—— 候法师一个字：要不要改到 `deepseek-v4.1-flash-1017`（吃 Credits，不烧 Go 余额）。
- Go 余额剩 5.54 美元，仍在消耗。
- **本轮未提交、未推送**。
