# 工作台骨架（OpenCode 只读最小闭环）v1.2

- 任务：`TASK-20261031-05`｜授权包 v1.1／⑯ 工作台骨架
- 性质：程序件骨架；默认只读；不接真实任务。
- 写面：`01_项目管理/工作台骨架/`（`05_产品与开发/*` 被 `.gitignore` 遮盖，新目录会静默不入库，故不落那里）。

## 〇、解释器与执行位置（先读）

- 自测与运行统一用 **Python 3.12**：
  `C:\Users\tiand\AppData\Local\Programs\Python\Python312\python.exe`
- **在骨架根目录执行**（即本 README 所在目录）：
  `python tests/selftest_s1.py`、`python run_workbench.py health`。
- `run_workbench.py` 顶部已加 `sys.path` 兜底（把自身目录插入 `sys.path`），嵌入式／zip 发行（如 DSH 内置 Python 3.14）也能 `import workbench`；但仍以 3.12 为准（3.14 复跑曾报 `ModuleNotFoundError: No module named 'workbench'`，属解释器环境差异，不是代码缺陷）。

## 一、契约映射

| 段 | 契约 | 代码 | CLI | 自测 | 状态 |
|---|---|---|---|---|---|
| S1 | 读配置（服务地址／端口／口令来源）→ Basic Auth → `/global/health` → 一行八段日志 | `workbench/config.py`、`workbench/client.py` | `python run_workbench.py health` | `python tests/selftest_s1.py` | 已实现 |
| S2 | `GET /session` 只解析元数据允许字段，拒收 `title`／`summary`；错误留原句 | `workbench/sessions.py` | `python run_workbench.py sessions` | `python tests/selftest_s2.py` | 已实现 |
| S3 | 连接既有端口（不代起服务）、端口探测与健康检查各 5 秒、退出码与端口确认、`--dry-run` 只打印 | `workbench/lifecycle.py` | `python run_workbench.py lifecycle --dry-run` | `python tests/selftest_s3.py` | 已实现 |
| — | `GET /session/:id` 会话详情 | — | — | — | **未实现**（候下一段，接线草案列为下一步只读路由） |

## 二、配置与口令来源

只从环境变量读，不读任何配置文件正文：

| 变量 | 默认 | 说明 |
|---|---|---|
| `WORKBENCH_OPENCODE_URL`（或 `OPENCODE_URL`） | `http://127.0.0.1:4096` | 只允许回环主机：`127.0.0.1`／`localhost`／`::1`；非回环在构造配置时即拒 |
| `OPENCODE_SERVER_USERNAME` | `opencode` | Basic Auth 用户名 |
| `OPENCODE_SERVER_PASSWORD` | 无（必填） | **只从环境变量读，禁止写进命令行参数**；不落盘、不进日志 |
| `WORKBENCH_TIMEOUT` | `5.0` | 秒；必须为有限数且大于 0；大于 5 一律压到 5；单次请求按 5 秒总预算执行（含读体） |
| `WORKBENCH_TASK_ID` | `TASK-20261031-05` | 日志任务号；仅 `[A-Za-z0-9_.:-]`，最长 64 |
| `WORKBENCH_LEVEL` | `L3_EGRESS` | 分级标签：真实调用用 `L3_EGRESS`，本机假服务自测用 `L0_LOCAL` |
| `WORKBENCH_APPROVER` | `-` | 审批人（日志第八段）；空值写 `-` |

## 三、用法（PowerShell）

```powershell
$env:OPENCODE_SERVER_PASSWORD = "<本轮一次性口令>"
python run_workbench.py health
python run_workbench.py health --no-auth
python run_workbench.py sessions
python run_workbench.py sessions --show-directory
python run_workbench.py lifecycle
python run_workbench.py lifecycle --dry-run
```

- `health`：带凭据调 `/global/health`，成功打印 `version=...` 与一行日志；退出码 0。
- `health --no-auth`：不带凭据，期望 401；退出码 2。
- `sessions`：带凭据调 `/session`，只输出元数据允许字段（`id／parentID／projectID／directory／version／time`），**不输出 title／summary**；`directory` **默认掩码为 `<masked>`**，确需真值加 `--show-directory`。
- `lifecycle`：只连既有端口，**不代起服务**；端口探测与健康检查各受 5 秒限制（三段串行，整体时长另计）；打印 `port_before／port_after／exit_code`。
- `lifecycle --dry-run`：只打印计划，**不发任何网络请求**。

### 退出码

| 码 | 含义 |
|---|---|
| 0 | 成功 |
| 2 | HTTP 失败（含 401／403 鉴权失败） |
| 3 | 连接失败／超时／健康检查后端口关闭 |
| 4 | 配置被本地拒绝（非回环、缺口令、非法端口、超时非法等） |
| 5 | 协议异常（JSON 解析失败、结构不符、响应体超 1 MiB） |
| 6 | 目标端口未开（仅 `lifecycle`） |

### 日志行（契约八段＋两个工程字段）

`task=… time=… channel=… action=… http=… summary=… level=… approver=… target=… elapsed_ms=…`

前八段对应契约：任务号｜时刻｜渠道｜动作｜HTTP 码｜响应摘要（元数据级）｜分级｜审批人；`target`／`elapsed_ms` 为工程附加。不含口令、标题、摘要正文；`summary` 只放 `version=1.19.5`、`sessions=3` 一类短串。

## 四、只读由代码强制（v1.1）

- **回环校验下沉**：`WorkbenchConfig.__post_init__` 复用校验，直接构造也拒非回环／缺口令。
- **禁代理**：`build_opener(ProxyHandler({}), ...)`，忽略 `HTTP(S)_PROXY` 环境变量。
- **拒重定向**：`_NoRedirectHandler` 对任何 3xx 直接抛错，Authorization 不会随 302 离开回环。
- **GET-only＋路径白名单**：`request()` 只收 `GET`，path 仅 `/global/health`、`/session`；越界立即抛 `ClientError`，**不发请求**。
- **响应体硬上限**：1 MiB；超限报错，不解析。
- **超时预算**：单次请求以 5 秒为**总预算**（连接、响应头、读体合计），读循环逐轮核剩余预算并重设 socket 超时，余量耗尽即中止；构造时 `timeout > 5` 自动压到 `5.0`。不说「硬顶」——预算是墙钟，不是单次 I/O。
- **空分隔符**：原始基础地址含 `?` 或 `#`（包括空的 `?`／`#`）一律拒绝，防请求目标被改写成 `/` 或 `/?/global/health`。
- **有限超时**：`nan`／`inf` 在配置层拒绝，CLI 退码 4、无 traceback。
- **日志字段白名单＋截断**：`task_id`／`level` 过正则，`action`／`summary`／`approver`／`version` 统一清洗换行与竖线并截断，防拼接伪造。
- **directory 默认不出**：CLI 默认掩码，`--show-directory` 显式开关。

## 五、边界

- 只绑／只连回环；非回环地址在配置层直接拒绝。
- 不建会话、不发消息、不 abort、不写项目数据；只读。
- 不读密钥或配置正文；口令只从环境变量取。
- 不接真实任务；一级内容不入任何出网路径。
- 不碰 `console_server.py`、看板件、已有镜像脚本。

## 六、分级

- `L0_LOCAL`：自测桩／本机假服务，不出网。
- `L3_EGRESS`：真实调用 `opencode serve`，按**三级出网（一般工程元数据）**记录；**不得称「零出网」**。
- 日志同时带 `level=` 与 `target=`，假服务跑出的行不会被误读成真实出网。

## 七、自测

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python tests/selftest_s1.py
python tests/selftest_s2.py
python tests/selftest_s3.py
python tests/selftest_v11.py
python tests/selftest_v12.py
```

- `selftest_s1/s2/s3`：原三段功能回归（鉴权 200／401、元数据白名单、端口生命周期）。
- `selftest_v11.py`：v1.1 专项 14 项——代理绕过、跨主机 302 拒绝、GET-only 与路径白名单、直接构造拒非回环、2 MiB 响应拒绝、超时压到 5s、`directory` 掩码、退出码 6／3／2／5／4、`L0_LOCAL`／`L3_EGRESS` 与 `target=`、日志八段与注入截断、非法端口、`python -P` 下的 `sys.path` 兜底、README 口径。
- `selftest_v12.py`：v1.2 批甲 4 项——总预算 deadline（滴灌 12 字节、1 秒一字节，墙钟须 ≤6 秒）、空 `?`／`#` 本地拒且假服务零新请求、`nan`／`inf` 配置层拒（CLI 退码 4 无栈）、常规健康检查回归。
- 全部只连 `127.0.0.1` 假服务（`tests/fake_server.py`），不出网。

### `.pyc` 与 `__pycache__`

跑 Python 会在 `workbench/`、`tests/` 下生成 `__pycache__`；这些 `.pyc` **不入库**。收尾清理：

```powershell
Get-ChildItem -Path . -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
```

先设 `PYTHONDONTWRITEBYTECODE=1` 再跑测试，可避免再生。

## 八、未实现（明确不做）

- 真实任务派工、路由闸、UI／看板、会话创建／发消息／abort。
- `GET /session/:id` 详情（契约表已列，标「未实现·候下一段」）。
- v2 `@opencode/cli` 线兼容（本骨架按 v1 `opencode-ai` 1.19.5 的 serve API 写）。
