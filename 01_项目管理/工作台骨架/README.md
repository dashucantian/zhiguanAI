# 工作台骨架（OpenCode 只读最小闭环）

- 任务：`TASK-20261031-05`｜授权包 v1.1／⑯ 工作台骨架
- 性质：程序件骨架；默认只读；不接真实任务。
- 写面：`01_项目管理/工作台骨架/`（`05_产品与开发/*` 被 `.gitignore` 遮盖，新目录会静默不入库，故不落那里）。

## 一、契约映射

| 段 | 契约 | 代码 | CLI | 自测 | 状态 |
|---|---|---|---|---|---|
| S1 | 读配置（服务地址／端口／口令来源）→ Basic Auth → `/global/health` → 一行日志 | `workbench/config.py`、`workbench/client.py` | `python run_workbench.py health` | `python tests/selftest_s1.py` | 已实现 |
| S2 | `GET /session` 只解析元数据允许字段，拒收 `title`／`summary`；错误留原句 | `workbench/sessions.py` | `python run_workbench.py sessions` | `python tests/selftest_s2.py` | 待做 |
| S3 | 连接既有端口（不代起服务）、超时 5s、退出码与端口确认、`--dry-run` 只打印 | `workbench/lifecycle.py` | `python run_workbench.py lifecycle --dry-run` | `python tests/selftest_s3.py` | 待做 |

## 二、配置与口令来源

只从环境变量读，不读任何配置文件正文：

| 变量 | 默认 | 说明 |
|---|---|---|
| `WORKBENCH_OPENCODE_URL`（或 `OPENCODE_URL`） | `http://127.0.0.1:4096` | 只允许回环主机：`127.0.0.1`／`localhost`／`::1` |
| `OPENCODE_SERVER_USERNAME` | `opencode` | Basic Auth 用户名 |
| `OPENCODE_SERVER_PASSWORD` | 无（必填） | **只从环境变量读，禁止写进命令行参数**；不落盘、不进日志 |
| `WORKBENCH_TIMEOUT` | `5.0` | 秒；必须大于 0 |
| `WORKBENCH_TASK_ID` | `TASK-20261031-05` | 日志行任务号 |
| `WORKBENCH_LEVEL` | `L3_EGRESS` | 分级标签；`L3_EGRESS` 即「三级出网」 |

## 三、用法（PowerShell）

```powershell
$env:OPENCODE_SERVER_PASSWORD = "<本轮一次性口令>"
python run_workbench.py health
python run_workbench.py health --no-auth
```

- `health`：带凭据调 `/global/health`，成功打印 `version=...` 与一行日志；退出码 0。
- `health --no-auth`：不带凭据，期望 401；退出码 2。
- 退出码：0 成功；2 HTTP／鉴权失败；3 连接／超时；4 配置错误。
- 日志行字段：`task=... time=... channel=... action=... http=... elapsed_ms=... level=...`；不含口令、标题、摘要。

## 四、边界

- 只绑／只连回环；非回环地址在配置层直接拒绝。
- 不建会话、不发消息、不 abort、不写项目数据；只读。
- 不读密钥或配置正文；口令只从环境变量取。
- 不接真实任务；一级内容不入任何出网路径。
- 不碰 `console_server.py`、看板件、已有镜像脚本。

## 五、分级

`L3_EGRESS` ＝ **三级出网（一般工程元数据）**。真实调用 `opencode serve` 时按三级出网记录；**不得称「零出网」**。本骨架的自测使用本机假服务，不出网。

## 六、自测

```powershell
python tests/selftest_s1.py
```

自测使用 `tests/fake_server.py`（只绑 `127.0.0.1`），覆盖：带凭据 200、无凭据 401、非回环拒绝、缺口令拒绝、日志不含口令。

## 七、未实现（明确不做）

- 真实任务派工、路由闸、UI／看板、会话创建／发消息／abort。
- `GET /session/:id` 详情（接线草案列为下一步只读路由，本骨架暂不实现）。
- v2 `@opencode/cli` 线兼容（本骨架按 v1 `opencode-ai` 1.19.5 的 serve API 写）。
