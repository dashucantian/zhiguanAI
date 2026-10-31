# OpenCode 外连用途文档核（接线执行授权包 v1·B 项）v1

- 任务：`TASK-20261031-05`｜授权包 B 项（原派 Claude 窗，现并派本窗）
- 出：Qoder 窗 `c73afab0`（本机接线执行位）｜2026-10-31 21:13（本机 `date` 现取；文档读取 21:07—21:11）
- 依据：`20261031-DSH-4ef78b3e-致Qoder窗c73afab0_接线执行授权包_v1.md` B 项；法师 17:1x「外连核查走官方文档路径」
- 性质：只读公开文档核；不探测远端、不登录、不上传、不读密钥或配置正文。
- 证据口径：「文档支持」＝官方文档原文；文档未覆盖＝「未验」，不推测、不把第三方说法当官方结论。

## 一、三问逐条

### 问 1：`serve` 起后是否发起联网行为？

**答：官方文档没有描述 `serve` 启动时的自发出网清单，不能从文档确认，也不能把两次 443 归因到某一项。标未验。**

官方 `serve` 文档只讲 API、鉴权与端口/主机参数，未描述启动时是否检查更新、校验登录态或拉取模型列表。官方文档能确认的“产品级联网能力”有：

- 更新检查：`autoupdate` 会检查新版本并提示（不自动安装）；
- 模型目录：使用 Models.dev，`opencode models --refresh` 从 models.dev 刷新缓存；
- LSP 自动下载：可用 `OPENCODE_DISABLE_LSP_DOWNLOAD` 关闭；
- 联网搜索工具：`OPENCODE_ENABLE_EXA`／`OPENCODE_ENABLE_PARALLEL` 为“启用”语义；
- 会话分享：`share` 可设 manual／auto／disabled；
- 对配置的 AI 提供方发起直接 API 调用（企业页自述“processing ... through direct API calls to your AI provider”）。

但这些能力是否在 `serve` 启动时自动触发、触发哪几项，文档没有逐项绑定。**因此两次远端 443（`104.20.32.17`／`172.66.173.149`）在文档层无法归因。**

### 问 2：哪些默认开／关？可用什么 env／config 关掉？

| 行为 | 官方 config／env | 默认口径 | 关法 | 出处 |
|---|---|---|---|---|
| 更新检查 | `autoupdate`；`OPENCODE_DISABLE_AUTOUPDATE` | 文档称 `true`／`notify` 即“默认行为”：提示但不自动装 | config `"autoupdate": false`；或设 `OPENCODE_DISABLE_AUTOUPDATE` | config 文档（21:10:40）、CLI 文档（21:10:43） |
| 模型目录拉取 | `OPENCODE_DISABLE_MODELS_FETCH`；`OPENCODE_MODELS_PATH`；`OPENCODE_MODELS_URL` | 变量名为“Disable fetching”，未设即允许远端拉取 | 设 `OPENCODE_DISABLE_MODELS_FETCH`；或 `OPENCODE_MODELS_PATH` 指向本地 JSON；或 `OPENCODE_MODELS_URL` 自定义 | CLI 文档（21:10:43） |
| 模型缓存刷新 | `opencode models --refresh` | 手动触发，从 models.dev 刷新 | 不运行该命令；需要时用本地目录 | CLI 文档（21:10:43） |
| LSP 自动下载 | `OPENCODE_DISABLE_LSP_DOWNLOAD` | 变量名为“Disable automatic”，未设即自动下载 | 设该变量 | CLI 文档（21:10:43） |
| 联网搜索 | `OPENCODE_ENABLE_EXA`；`OPENCODE_ENABLE_PARALLEL` | 变量名为“Enable”，未设即不开（语义推断，文档未明示默认值） | 不设即可 | CLI 文档（21:10:43） |
| 会话分享 | `share`（manual／auto／disabled） | **文档未明示默认值** | 设 `"share": "disabled"` | config schema（21:09:38） |
| 遥测 | **未找到官方关闭项** | 未明示 | 无官方 env／config 可关 | config schema、CLI 文档、隐私政策（21:09—21:10） |
| 代理 | `HTTPS_PROXY`／`HTTP_PROXY`／`NO_PROXY`；`NODE_EXTRA_CA_CERTS` | 未设即直连 | 设代理或证书 | network 文档（21:08） |

**遥测这一格是硬缺口**：官方 config schema 有 `username` 字段，原文说它“used for telemetry identity”；另有 `experimental.openTelemetry` 用于 AI SDK 调用的 OpenTelemetry spans（已标记 deprecated）。但官方 CLI 环境变量表里**没有** `OPENCODE_DISABLE_TELEMETRY` 一类开关；隐私政策只泛述网站/服务的 analytics 与 IP 数据，没有给 CLI 遥测的关闭方法。**结论：文档层不能保证“零遥测”；若要零出网，须网络层封堵或另做最小探测（由法师定，不由本窗申请）。**

### 问 3：两次 443 的两个 IP 有无官方说明？

**答：没有。官方文档与隐私政策均未出现 `104.20.32.17`／`172.66.173.149`，也没有把任何 IP 映射到 OpenCode 的具体功能。标未验。**

隐私政策只有泛述：“Device/IP Data such as IP address, device ID, domain server, type of device/operating system/browser used to access the Services.”，以及“We may use analytics providers...”。这不构成对两个 IP 的说明。

前次二跑记录称两地址属 Cloudflare 段；本窗按授权包边界**未做 DNS／PTR／whois 或任何 IP 探测**，故不把它写成已核事实。若要确认，只能另批一次最小探测。

## 二、对工作台的直接含义

- 文档能支持的“可关项”：更新检查、模型远端拉取、LSP 下载；这三项都有官方 env／config。
- 文档不能支持的：`serve` 启动时零出网、零遥测。官方没有给遥测关闭项，也没有把 `serve` 启动与具体联网动作逐一绑定。
- 因此，若阶段三接线要求“serve 只绑回环、零出网”，仅靠文档与现有开关**不够**；需要网络层封堵（防火墙／hosts／代理白名单）或一次最小探测来定性。这是提出，不是裁定。

## 三、旁证（非官方，不采信为结论）

- 有第三方 fork 在公开 README 中宣称 OpenCode 会向 PostHog／Honeycomb／opncd.ai／models.dev 等发送数据；本窗未核其源码、未用它作结论，只作后续最小探测的线索。该说法与官方文档的沉默不一致，不能当官方事实。

## 四、出处与原文短句

| 出处 | 读取时点 | 原文短句 |
|---|---|---|
| <https://opencode.ai/docs/server/> | 21:07 | “Set `OPENCODE_SERVER_PASSWORD` to protect the server with HTTP basic auth. The username defaults to `opencode`, or set `OPENCODE_SERVER_USERNAME` to override it.” |
| <https://opencode.ai/docs/cli/> | 21:10:43 | “OPENCODE_DISABLE_MODELS_FETCH boolean Disable fetching models from remote sources”；“OPENCODE_MODELS_PATH string Load the model catalog from a local JSON file”；“OPENCODE_DISABLE_AUTOUPDATE boolean Disable automatic update checks”；“OPENCODE_DISABLE_LSP_DOWNLOAD boolean Disable automatic LSP server downloads” |
| <https://opencode.ai/docs/cli/> | 21:10:43 | “Use the `--refresh` flag to update the cached model list. This is useful when new models have been added to a provider and you want to see them in OpenCode.” |
| <https://opencode.ai/docs/config/> | 21:10:40 | “OpenCode checks for new versions and shows a notice when one is available. Updates are never installed automatically.”；“Setting autoupdate to true or 'notify' keeps the default behavior: you're notified, but nothing is installed until you choose to update.” |
| <https://opencode.ai/config.json> | 21:09:38 | `share`: “Control whether sessions may be shared manually, automatically, or not at all”；`username`: “Username displayed in conversations and used for telemetry identity”；`experimental.openTelemetry`: “Enable OpenTelemetry spans for AI SDK calls (using the 'experimental_telemetry' flag)” |
| <https://opencode.ai/docs/models/> | 21:08 | “OpenCode uses the AI SDK and Models.dev to support 75+ LLM providers.” |
| <https://opencode.ai/docs/network/> | 21:08 | “OpenCode respects `HTTPS_PROXY`, `HTTP_PROXY`, and `NO_PROXY` env vars. Use `NODE_EXTRA_CA_CERTS` for custom certs.” |
| <https://opencode.ai/docs/enterprise/> | 21:08 | “OpenCode operates securely inside your organization with no data or context stored”；“All processing happens locally or through direct API calls to your AI provider.” |
| <https://opencode.ai/legal/privacy-policy> | 21:10:36 | 生效日 Mar 6, 2026；“Device/IP Data such as IP address, device ID, domain server, type of device/operating system/browser used to access the Services.”；“Performance/Analytical Cookies allow us to understand how visitors use our Services.” |

## 五、未验项

- `serve` 启动时是否自动检查更新、拉取模型目录、验证登录态：未验（文档未逐项绑定）。
- 两次 443 的具体用途与两个 IP 的归属：未验（未做 IP 探测；官方文档无对应说明）。
- 官方是否另有未公开的遥测关闭项：未验（现有文档无）。
- `share` 的默认值：未验（schema 有枚举，文档未明示默认）。

## 六、边界

- 未探测远端、未登录、未上传、未读密钥或配置正文；未改配置、未起服务。
- 本文只作文档核；不构成“可以接线”或“必须断网”的裁定。接线条件由 W3 判定、法师验收。

Author-Role: Qoder 窗 c73afab0（本机接线执行位）
Proposal-by: AI-026·DSH 接棒窗 4ef78b3e（接线执行授权包 v1·B 项）
Approved-by: 宗国法师（2026-10-31 21:0x 授权升级：本机接线执行位、授权包内连续推进）
Verified-by: 未验（候 W3 复核、法师阶段验收）
Model: 未录（会话 runtime-config 显示 GPT 6 Luna；官方标识未验）
Session: Qoder 会话 c73afab0-52dc-487a-aff3-c59bc25560dc
Window: Qoder-c73afab0（不入编制）
