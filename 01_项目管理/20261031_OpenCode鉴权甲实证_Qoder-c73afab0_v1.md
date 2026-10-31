# OpenCode 鉴权甲实证（接线执行授权包 v1·A 项）v1

- 任务：`TASK-20261031-05`｜授权包 A 项（原候编号⑭）
- 出：Qoder 窗 `c73afab0`（本机接线执行位）｜2026-10-31 21:13（本机 `date` 现取；实测 21:07:55—21:07:59）
- 依据：`20261031-DSH-4ef78b3e-致Qoder窗c73afab0_接线执行授权包_v1.md` A 项；`20261031_统一工作台任务中枢_接线最小验证方案_v1.md`
- 性质：执行记录；边界内自办；四值留证；不裁定、不写共享台账。

## 一、命令与口令面

- 命令：`opencode serve --port 0 --hostname 127.0.0.1 --pure --print-logs --log-level INFO`
- 口令：一次性随机口令，只存在本轮进程环境变量 `OPENCODE_SERVER_PASSWORD`；**未落盘、未写入本件、未进日志**。本件只记「已设／长度 32」。
- 鉴权方式：HTTP Basic，用户名 `opencode`（官方文档：`OPENCODE_SERVER_PASSWORD` 保护 serve，用户名默认 `opencode`，可用 `OPENCODE_SERVER_USERNAME` 覆盖）。

## 二、四值

| 项 | 结果 | 证据 |
|---|---|---|
| 起止时刻 | 起 **2026-10-31 21:07:55.294**；监听行出现 **21:07:56.179**；止 **21:07:59.477** | 启动脚本 T0；stdout 原句 `opencode server listening on http://127.0.0.1:4096`；停止脚本 T1 |
| PID | **34180** | 启动进程对象；端口监听行 OwningProcess＝34180 |
| 退码 | **未取得退出码**；由本窗 `Stop-Process -Force` 终止 | 停止后 `alive_after_stop=false`；`exit_code=null` |
| 响应摘录 | 无凭据 `/global/health` → **401**（空体）；带凭据 → **200**，体 `{"healthy":true,"version":"1.19.5"}` | 同一端口 4096、同一路由；详见下 |
| 端口现查 | 停前 `127.0.0.1:4096` LISTENING（PID 34180）；停后监听列表为空 | `Get-NetTCPConnection -LocalPort 4096 -State Listen` 现查 |

## 三、判据

- **401 与 200 双成立 ⇒ 甲成立**。无凭据被拒，带凭据可读版本；版本回读 `1.19.5`，与本机 npm 包 `opencode-ai` 一致。
- 口令设置后，启动 stdout 不再出现上轮无口令时的 `server is unsecured` 告警；stderr 只有三条配置加载路径（未读配置正文）。
- 未创建会话、未发消息、未写项目数据；只调了 `/global/health` 一个只读路由。

## 四、边界与未验

- 未改任何配置、未动 `.git`、未探测远端、未登录、未上传、未读密钥或配置正文。
- 本轮进程存续约 4 秒，**未在存续期抓外连快照**，故不写「无外连」；外连性质按授权包 B 项的官方文档路径核（见同日《OpenCode 外连用途文档核》件）。
- 只停本测试 PID 34180；未触碰其他 opencode 进程。
- 证据临时件（gitignored，未入库）：
  - `_analysis_tmp/oc_auth_result_20261031_210755.json`
  - `_analysis_tmp/oc_auth_stdout_20261031_210755.log`
  - `_analysis_tmp/oc_auth_stderr_20261031_210755.log`

## 五、结论

- 甲案**成立**，可进入接线草案；接线前仍守「鉴权＋回环绑定」双条件。
- 候 W3 复核四值与结论；法师阶段验收。

Author-Role: Qoder 窗 c73afab0（本机接线执行位）
Proposal-by: AI-026·DSH 接棒窗 4ef78b3e（接线执行授权包 v1·A 项）
Approved-by: 宗国法师（2026-10-31 21:0x 授权升级：本机接线执行位、授权包内连续推进）
Verified-by: 未验（候 W3 复核、法师阶段验收）
Model: 未录（会话 runtime-config 显示 GPT 6 Luna；官方标识未验）
Session: Qoder 会话 c73afab0-52dc-487a-aff3-c59bc25560dc
Window: Qoder-c73afab0（不入编制）
