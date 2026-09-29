# NeuraDock 开发者指标平台 HTTP API · 旁证源接入说明与数据字典 v1

日期：2026-09-29 ｜ 编写：W1（AI-008·Qoder，Session `W1-QODER-20260924-B`）｜ 依据：法师派单 `信箱/inbox/20260929-ZG076.md` §二-③
平台版本：`app_version 3.2.0`／`api_version v1`（API 自报）｜ 实抓存证：`01_项目管理\20260929_ZG076存证\`

## 一、三句边界（写死，勿靠记忆）

1. **该源只输出对方算好的分数与质量，不含原始脑电**（返回值自带 `raw_eeg_exposed: false`，
   平台页面亦写明"外部客户端只能读取结果，不能启动设备、绕过校准或取得原始脑电"）
   ⇒ **不参与 `qc_pipeline.py` 任何判定、不替代原始流入库、不进 Zen-EEG 数据工厂**。
2. **其指标公式与权重对方未完整公开**（体验类指标 `formula_version`／`baseline_z` 为 null）
   ⇒ 我方只作**并排旁证与差异观察**，**不采信为真值、不据此改我方阈值**。
3. **该 API 随对方桌面程序生命周期浮动、端口不固定**（09-29 实测先后见 55005／52413／63170）
   ⇒ 任何会话存档**同时记下当次端口与 `app_version`**，否则事后无法复现。

## 二、我方实现落点（指路，不贴代码）

| 层 | 落点 | 说明 |
|---|---|---|
| 后端 | `console_server.py` §NeuraDock 指标平台旁证源 | 常量 `ND_METRICS_PATH`、`_parse_hostport`、`_normalize_nd_target`、`nd_metrics_fetch`、`_nd_side_stamp` |
| 后端·推送 | 同上 §SSE 实时推送订阅 | `ND_STREAM_PATH="/api/v1/stream"`、`_nd_sse_worker`（长连接读帧＋1→2→4→5 秒退避重连＋45 秒无人取数自退订）、`_nd_sse_ensure`（懒启动／换址切换）、`_nd_sse_publish`／`_nd_sse_owner`（迟到帧丢弃＋非在册线程不许写状态） |
| 端点 | `GET /api/ndmetrics?target=IP:端口` | **只读代理**；拼路径由我方负责（基路径 `/api/v1` 实测 404）；地址非法→400 中文，连不上→502 中文；**优先取 ≤3 秒新鲜推送帧（`via:"sse"`），否则自动回落单次拉取（`via:"poll"`）**；响应带 `sse{state,target,frames,age_sec,err,reconnects}` |
| 端点 | `POST /api/ndmetrics/stop` | 前端关栏／离开页面即退订对方推送，不长期占对方资源 |
| 存档 | `session_info["nd_side"]` → npz `meta.nd_side` | 只记当次地址／`app_version`／`api_version`／`session_id`／`raw_eeg_exposed`／首取结果，**不记指标数值**（P1 契约 P7「Session 最小主义」） |
| 前端 | `console.html` 旁证栏 `#ndSideMode`/`#ndSideAddr` ＋ 读数卡 `#ndSideCard` | 与「NeuraDock 数据服务地址」**分栏**；可叠加在任一数据源之上；1 秒节奏读我方本地端点；**只显数字与状态、不画曲线**；meta 行如实标出取数通道（推送SSE·第N帧·龄Xs／轮询JSON＋回落原因），**换路不许悄悄换** |

**为什么 SSE 走后端订阅而不是浏览器直连（09-30 实测）**：平台推送口响应头只有
`Server`／`Date`／`Content-Type`／`Cache-Control`／`X-Content-Type-Options`，
**没有 `Access-Control-Allow-Origin`**；驾驶舱(8777)与平台(随机端口)不同源，
浏览器直连必被 CORS 挡下 ⇒ 只能后端订阅、前端读本地端点。

**怎么用（双击即得）**：① 打开 NeuraDock 开发者指标平台 → 复制页面上显示的地址；
② 驾驶舱「连接与采集」卡里把「旁证源（只读·不入库）」选成 *NeuraDock 指标 API（HTTP）*；
③ 整条地址直接粘进新出现的栏位（带 `http://` 也认，我方自动剥成 `IP:端口` 并回显）；
④ 读数卡出现在自研频段图正下方，金色字是**对方算的**、青色字是**我方算的**。

## 三、数据字典（`GET /api/v1/metrics` 顶层）

> `GET /api/v1/stream`（SSE）的 `data:` 帧与此表**完全同构**（09-30 实测：1.01 秒一帧、
> 1168 字节、失源时也照推），故两条路共用同一套字段解释与同一套诚实规则。

| 字段 | 类型 | 含义与我方处置 |
|---|---|---|
| `api_version` | str | 接口版本（`v1`）→ 记入 `meta.nd_side` |
| `app_version` | str | 对方程序版本（`3.2.0`）→ **必记**（边界 3） |
| `session_id` / `session_state` | int / str | 对方自己的会话号与阶段（`calibrating`／`measuring`…）→ 记入 meta，仅追溯 |
| `message` | str | 人读状态句 |
| `generated_at_unix` | float | 对方生成时刻 |
| `raw_eeg_exposed` | bool | **原始脑电是否经 API 暴露**（当前恒 `false`）；若变 `true` 我方界面直接红字自曝"边界已破" |
| `scientific_scope` | str | 对方自陈适用边界（本人／本次／同协议／非医学诊断） |
| `measurement` | obj | `elapsed_sec`、`sample_index`、`window_sec:4`、`step_sec:1`、**`last_sample_age_sec`**（数据龄，我方 >8 秒标"陈旧"） |
| `source` | obj | `mode`（`direct_bluetooth`…）、`state`（`streaming`／`error`…）、`synthetic_not_human_eeg`（仿真标记） |
| `quality` | obj | `grade`／`grade_label`（四档）、`usable_channel_count`／`usable_channels`、`bad_channel_candidates`、`reliable_channel_count`、`posterior_retention`、`qc_bandpass_hz`、`qc_signal_basis`、`quality_policy`、`status`、`experience_allowed` |
| `selected_metrics` | [str] | 平台页面上勾选输出的指标名 |
| `metrics.<name>` | obj | `name`（中文名）、`value`（0–100 分，**质量不足为 null**）、`unit`、`raw_value`、**`baseline_z`**（实测 null）、**`confidence_percent`**、`status`（`evaluated`／`accumulating`／`blocked`／**`awaiting_source`**，后者＝对方无数据源，09-30 实抓）、`method`（算法名，公开）、**`formula_version`**（体验类 null；客观状态类自报 `objective-state-v2.0.0`）、`reason_codes`、`note` |

## 四、我方不做什么（红线对照）

- 不把该源数值写入 npz 数据数组、会话事件流或入库登记表；
- 不参与 `qc_pipeline.py` 任何判定，不影响 `contact_quality`／通道好坏结论；
- 不画时间序列曲线——对方 4 秒窗／1 秒步，跨窗补点即等于我方补值；
- 不据此调整我方 α/θ/β 阈值、闭环音量节拍决策或任何判据；
- `status:"blocked"`／`value:null` 一律如实显示"blocked·原因码"／"无值（累积中）"，不补值、不插值；
- **`source.mode` 必显**（不得只显 `state`——真机与仿真都是 `streaming`，只看 state 分不出来）；
  `mode:"simulation"` 或 `synthetic_not_human_eeg:true` 时整栏红字自曝"仿真数据、不是人脑电、
  不作旁证、不存档"，**质量等级再高也不采信**（09-30 00:23 实抓：仿真态下对方仍报
  `grade:high`／7 路可用／`status:pass`）；
- 对方 `session_state:"error"` 或 `source.state:"error"` 时，界面须把**对方 `message` 原话**
  一并显示（例："TimeoutError: 蓝牙保持连接但已超过3秒未收到新通知"），让人一眼看出是谁坏了。

## 五、实测口径两条（与派单不符或派单未记，如实登记）

1. `formula_version` **并非全为 null**：体验类（如 `focus`）为 null，客观状态类
   （`spectral_complexity`／`global_integration`）自报 `objective-state-v2.0.0`
   ⇒ 回函厂商问"七项固定公式与权重"时应**按类区分**，客观状态类其实已给版本。
2. **平台会持续返回陈旧读数而不显式失效**：实测 `source.state:"error"` 且
   `last_sample_age_sec` 从 259 秒涨到 1656 秒，`focus` 仍标 `status:"evaluated"` 带数值
   ⇒ 我方以数据龄 >8 秒红字标注"陈旧读数、只作参考、未补值"；建议请厂商在 API 语义中
   增加 `stale` 状态或让 `status` 随之转 `blocked`。
3. **对方失源时的完整形态（09-30 00:27 实抓，与 09-29 陈旧读数态不同）**：BLE 直连超时后
   `session_state:"error"`、`source:{mode:"direct_bluetooth",state:"error"}`、
   `quality.grade:"pending"`／可用 0 路／`experience_allowed:false`、四项指标全 `status:"blocked"`
   且 `value:null`、`message` 带故障原话 ⇒ **这一态对方语义是干净的**（不补值、不给分），
   我方照实转显即可；反倒是第 2 条那种"陈旧仍 evaluated"更危险。
4. **端口每次重启即变，本条已二次实证**：09-29 见 55005→52413→63170，09-30 00:21 平台重启后
   变 **50061**，旧口 62836 立即 ConnectionRefused ⇒ 界面提示"到平台页面复制当次地址"是必需的，
   任何写死／收藏都无效（边界 3）。
5. **SSE 推送口可用，但必须后端订阅**（09-30 00:39 实测）：`/api/v1/stream` → 200、
   `text/event-stream`、`event: metrics` ＋ `data:{…}`、1.01 秒一帧、结构与 `/metrics` 同构；
   响应头**无 `Access-Control-Allow-Origin`** ⇒ 浏览器跨端口直连必被 CORS 挡，
   我方改为后端长连接订阅、前端仍读本地端点。**已知限制**：订阅槽是全局单槽，
   多个页面填**同一地址**共用一条订阅（不冲突）；填**不同地址**会互相切换，
   最终双方都回落单次拉取——数据仍正确，界面上会写明"推送被其他页面占用"。
   一人一面板的正常使用不会遇到。

## 六、待厂商回函（派单 §三，本单不设依赖）

① 端口能否固定／有无命令行无界面模式；② 七项指标的固定公式与权重能否书面给出（按类区分）；
③ 原始 250 Hz×7ch 全量流是否开放（**T6 红线**）。
另加本窗新提第④问：`last_sample_age_sec` 增大而 `status` 仍 `evaluated` 是否为设计行为。
