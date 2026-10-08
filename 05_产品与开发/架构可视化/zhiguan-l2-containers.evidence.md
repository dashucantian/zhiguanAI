# 止观AI 架构可视化 — 证据与实测记录

产出方：Qoder `architecture-visualization` 0.1.0（路由 `explore` → 场景 `system-modeler`，格式基座 `c4model` + `graphviz`）
生成日期：2026-10-07　视图状态：**current（现状）**

## 一、本目录文件

| 文件 | 回答什么问题 | 怎么看 |
| --- | --- | --- |
| `zhiguan.structurizr.dsl` | L1 系统上下文 + L2 容器：止观AI 与外部世界的边界、内部四个可部署单元 | 在 Qoder 里直接打开该文件，插件自带 Structurizr 查看器会渲染两张视图 |
| `zhiguan-l2-containers.dot` | 模块级依赖与数据流：谁调谁、谁写谁、哪里出网、哪里过硬件 | 在 Qoder 里直接打开该文件，插件自带 Graphviz 查看器出 SVG |
| `architecture-model.json` | 上面两张图的证据底账：每个节点/边都带 `sourceRefs` 与 `confidence` | 机器可读，用于回归校验与差异对比 |
| `validate-model.mjs` | 回归闸门：校验上面那份底账（schemaVersion／id 唯一／端点存在／sourceRefs 可解析／current 节点 confidence 达标） | `node validate-model.mjs`，不过 exit 1 |
| `zhiguan-l2-containers.evidence.md` | 本文件：证据来源、假设、缺口、实测数据、重生成办法、裁定记录 | 人读 |
| `zhiguan-source-of-truth.dot` | 六面「正源→投影」映射：哪类事实以谁为准、谁只是派生视图（协调正本 §16.2） | 在 Qoder 里直接打开该文件，插件自带 Graphviz 查看器出 SVG |
| `qgraphflow\zhiguan-console-architecture\index.html` | 控制台＋闭环链那一张：谁调谁、证据落在哪个文件哪一行 | **双击即开**（离线自包含，无需服务、不出网） |
| `qgraphflow\zhiguan-board-architecture\index.html` | 任务看板那一张：法师↔看板↔MCP↔AI 窗口 | 同上 |
| `qgraphflow\congci-feed-sequence\index.html` | 从此线那一张：一坐数据按什么顺序进脑（时序图） | 同上 |
| `qgraphflow\source-of-truth-map\index.html` | 六面正源映射那一张：与上面 DOT 同源，交付面版本 | 同上 |
| `qgraphflow\*.graph.json` | 上面几张 HTML 的图数据源（QGraphFlow 格式，自带行区间级 `source`） | 改这里再重跑三条命令 |

## 二、证据来源（已逐条抽查行号属实）

核心运行时：
- `console_server.py:174`（FastAPI 实例）、`:3174`/`:3178`（端口 8777/8778）、`:3234`（uvicorn 启动）
- `console_server.py:71,72,76,80,125,193,666`（导入 closedloop / controller / qc_pipeline / nd_routes / registry_tx / muse_local_server / session_contract）
- `console_server.py:60-64`（sys.path 注入 muse2 子仓）
- `console_server.py:2224,2236,2249,3167`（FileResponse 出 vr_feedback / vr_mandala / focus / console 页面）
- `closedloop_experiment.py:38,43`、`zhiguan_cadence_bridge.py:69,46,509`（34→69 类声明、45→46 `from cadence import Brain`，2026-10-08 行级复核订正）、`qc_pipeline.py`
- `muse2-repo/muse2-master/nd_routes.py:30`（原记 `:20` 是空行）、`nd_hub.py`、`neuradock_receiver.py:54`、`muse_local_server.py`

看板子系统：
- `05_产品与开发/任务看板/board_server.py:39`（HOST/PORT=127.0.0.1:8848）、`:42`（FastAPI）、`:81-147`（JobQueue）、`:184-192`（采样器注册）、`:35`（`SCREEN_DIR = STATE/"screen"`）、`:221`（`PROBE_FILE.write_text(...)`，state 唯一真实写盘点）、`:700-711`（SSE /api/stream）、`:718-729`（MCP_TOOLS）、`:736-751`（分发）、`:754-785`（POST /mcp）、`:788-796`（GET/DELETE→405）
- `board_sources.py:19-22`（扫描 ~/.qoder-cn）、`:28`（`WEINA_SOURCE` 单一正源常量；原 `:25` 的 `WEINA_DIRS` 已于 2026-10-08 `a006d32` 废除）、`:268`（`_find_weina_snapshot` 只认该路径，原 `:264-272` 的 rglob 按 mtime 择源已废）、`:302`（正源缺失明确报错含全路径，不回退不猜）
- `board_privacy.py`、`board_config.py:29`（千问）、`board_config.py:74,79`（WINDOWS 映射表与本窗标准名行；2026-10-09 由 `:73,78` 顺延 1 行＝看板窗在途注释插行，非本目录改动）

六面正源映射（2026-10-08 依协调正本 §16.2 新增，法师裁「1–4 的建议我同意」转生效；节点族 `soT.*`／`proj.*`）：
- 正源①业务任务＝飞书多维表格：`board_sources.py:28`、`01_项目管理/任务关系图/生成关系图.py:19`（本机 `_records_raw.json` 只是快照，不是正源）
- 正源②窗口身份与授权＝`01_项目管理/AI代理身份登记.md:31`（§三 登记表）、`:97`（§三bis 窗口分类与认领）；投影＝`board_config.py:74,79`（只承载物理地址与显示名）
- 正源③架构事实＝`architecture-model.json:3`（metadata／sourceRefPolicy）＋本文件 `:19`（§二）；投影＝图谱双轨（`zhiguan-l2-containers.dot:1`、`qgraphflow/congci-feed-sequence.graph.json:1`）
- 正源④数据准入与判定＝`qc_pipeline.py:432`（`write_qc_json` 定稿写手）＋`05_产品与开发/muse-direct/tools/ingest_session.py:2`（02_raw 唯一合法写入入口）＋`congci_pipeline.py:149`（`processed_index.json` 账本路径；HEAD 与工作区同行同文，已用 `git show HEAD:` 对过）
- 正源⑤运行巡检＝C3（暂停中）：`AI-开工入口.md:100`（§二.9 暂停＋停催令注记与替代动作；2026-10-09 由 `:99` 顺延 1 行＝他窗在 §二bis 第 3 条下补了一行「自报数必须来自命令原样输出」，非本目录改动）、`01_项目管理/20261007_C3任务运行态只读快照_候裁_v1.md`
- 正源⑥会话运行态＝MCP `list_chat_sessions` 快照：`05_产品与开发/任务看板/需求与隐私原则_v1.md:53`（180 秒新鲜度口径）、`board_sources.py:118`（读 `state/live_sessions.json`）
- 投影侧另三条：`01_项目管理/任务关系图/生成甘特流程图.py:18`（甘特与思维导图同源同快照）、`01_项目管理/20261008_QC入库乱象只读筛查与裁定123执行_v1.md:153,162`（从此线报告只读消费正源）、`01_项目管理/信箱/engine/巡检日志-W3.txt:1`（C3 暂停期的己档留痕面）

## 三、假设与缺口（confidence 未达 high 的部分）

| 项 | 状态 | 说明 |
| --- | --- | --- |
| `closedloop` → `cadence-bridge` 直接调用点 | **撤边（原 medium/inferred；2026-10-08 行级复核）** | 复核结论＝**该边不成立**。原三条 refs 全在养脑侧（订正后 `congci_pipeline.py:574`／`652` 导入、`653` 调用），只证到 `congci._process_row → bridge.process_session`；`closedloop_controller.py`／`closedloop_experiment.py`／`closedloop_engine.py` 三件对 `cadence|bridge|Bridge` **零命中**，controller 自持 `beat_*`／`volume`（`closedloop_controller.py:35-60`），节拍是它自己算的。按本表下方纪律（模型 JSON 只收 high/medium）⇒ **模型删边、DOT 删线并留注释**；有据的那条是 `congci → bridge`（DOT 第 94 行）。轨二 `zhiguan-console-architecture` 里的 `e_ctrl_bridge` 当时已如实标 `inference`，非假边，但同样缺据，随下次重生成一并处理（丙案）。 |
| `registry_tx` → Zen-EEG CSV 读写 | **medium** | 依据 docstring，未实测跨盘写入 |
| `board_sources` → 飞书 | **low（未入模型）** | 证据在 `01_项目管理/任务关系图/20261007_W3_维那快照拉取_v1.py:45`，是**离线拉取脚本**而非看板进程内调用；DOT 图里画成虚线，模型 JSON 里**故意不建边**，避免把批处理伪装成运行时依赖 |
| 看板 → LM Studio :1234 | **low（未入模型）** | 证据在 `01_项目管理/评测集黄金任务集_运行/run_eval.py:38`，同属评测脚本而非看板进程；DOT 里虚线，模型不建边 |
| `congci_pipeline` 归属 | **已确证（原 unknown）** | 2026-10-08 行级复核补上：`console_server.py:699`（在 `_do_save` 584-708 之内）直调 `congci_pipeline.enqueue`，闭环路径同挂点 `console_server.py:1152`（`ExperimentSession` 收口）。DOT 已补 `console -> congci` 一条。⚠ 模型 JSON 侧仍**没有从此线节点族**（`congci_pipeline` 函数级／`ingest_session.py`／`processed_index.json` 均未建节点），本条只确证"挂点"，不覆盖整条从此线 ⇒ 补节点＝`D-1008-W3b` §八.1 丙案，候裁。 |
| arxiv 出网 | **not found** | 子代理未找到证据，未入图 |
| 「窗口身份」疑似两个正源 | **已分辨（非缺口，2026-10-08）** | 协调正本 §16.2 定『身份与授权』正源＝`AI代理身份登记.md`；§15 试点契约定『标准显示名』正源＝`board_config.py` 的 WINDOWS 表（`:68` 注释自述「正源＝本表，界面只做投影」）。两者管辖**不同事实**，不冲突；但**显示名不得当授权依据** ⇒ 模型里 `soT.window-identity → proj.identity-map` 只标「投影」，不标「授权」。 |
| 正源①（飞书多维表格）本机不可直证 | **medium 语义（节点仍记 high）** | 正源真身在飞书云端，本机只有快照 `_records_raw.json`。该节点 confidence=high 指的是**「映射关系有据」**（裁定＋三处代码消费点可解析），**不是「已核云端现势」**；本窗未联网核验（出网须另裁）。快照新鲜度以件内 `query_context.pulled_at` 为准，看板界面须显示来源时间。 |
| 正源⑥单写方尚未落地 | **medium** | §16.1 已裁『`state/live_sessions.json` 改为单写方（建议看板窗）、他窗只读』，但写方归属未落文件、该文件无锁 ⇒ 现势仍多窗可写。模型 `soT.session-runtime` 记 medium，不记 high。 |
| 正源④权威性未定案 | **medium** | 定稿 `qc.json` 与人工隔离／撤回状态谁优先＝协调正本 §13.8 批B 草案，仍候裁 ⇒ `soT.data-admission` 记 medium（正源身份已定、权威性未定）。 |

> 纪律说明：DOT 图里虚线＝「有文件证据但不是运行时进程内调用」。模型 JSON 只收 high/medium。两者故意不一致，是为了让图能表达「疑似」而模型不背书。

## 四、插件性能实测（本机：Windows，Node v24.19.0，无 graphviz 二进制）

三套渲染器全部**内置于插件**（`canvases/dot|dsl|mermaid/scripts/index.mjs`），**不需要装 graphviz / structurizr / mermaid-cli**。本机 `dot` 命令不存在，插件照样出图。

官方 smoke test：`node examples/basic-architecture/run-smoke.mjs` → **status passed，总耗时 1.25 s**

单件渲染耗时：

| 用例 | 规模 | 耗时 | 结果 |
| --- | --- | --- | --- |
| 官方示例 DOT | 小 | 148 ms | SVG 10 KB |
| 官方示例 Mermaid | 小 | 332 ms | SVG 13 KB |
| 官方示例 Structurizr DSL | 2 视图 | 228 ms | 解析成功 |
| **本项目 L2 容器图 DOT** | 21 节点/含 5 个 cluster | **142 ms** | SVG 36 KB，1580×866 |
| **本项目 C4 DSL** | L1 9元/9关系，L2 12元/12关系 | **191 ms** | 两视图全解析，中文工作区名正常 |
| 分层树 DOT | 50 节点 | 140 ms | SVG 28 KB |
| 分层树 DOT | 150 节点 | 141 ms | SVG 89 KB |
| 分层树 DOT | 400 节点 | 175 ms | SVG 249 KB |
| 稀疏 DAG DOT | 200 节点×3 边 | 198 ms | SVG 243 KB |
| 稀疏 DAG DOT | 500 节点×3 边 | 344 ms | SVG 621 KB |
| 稠密带环 DOT | 100 节点×3 边 | 2 952 ms | SVG 163 KB |
| 稠密带环 DOT | 200 节点×2 边 | 3 629 ms | SVG 226 KB |
| **稠密带环 DOT** | **200 节点×3 边** | **>60 000 ms 超时** | **未完成** |

中文渲染：SVG 内 `font-family="Microsoft YaHei"`，「宗国法师」「看板」「头环」等标签**原样进 SVG，未见豆腐块**。

**结论（可用边界）**：分层/DAG 形态到 500 节点仍是亚秒级，完全够用；但**一旦图稠密且成环，内置 graphviz 布局超线性劣化，200 节点即可打爆 60 秒**。项目里真实的依赖图（几十个模块、稀疏、分层）落在安全区。画大图时须：`rankdir=TB`、拆 cluster/子图、控制回边数量。

## 五、证据模型校验

按插件 `run-smoke.mjs` 的 `validateModel()` 规则改写校验器（sourceRefs 基准改为仓库根）跑本项目模型：

- 首轮 **FAILED，5 条错误**：`nd_routes.py:20`、`neuradock_receiver.py:54` 写成仓库根路径，实际在 `muse2-repo/muse2-master/` 下；另 1 条是本文件当时尚未落盘。
- 修正后 **PASSED**：21 节点 / 20 边，confidence 分布 high 19/18、medium 2/2、low 0/0，**所有 sourceRefs 均可解析**。

> 这一轮失败本身是插件最有价值的地方：它不接受「看起来对」的路径。子代理给的行号有真有假，校验器当场抓出。

## 六、重新生成 / 回归校验

```bash
# 1. 证据模型校验（sourceRefs 必须可解析）
node <本目录>/validate-model.mjs

# 2. 三套渲染器官方 smoke test
node "C:/Users/tiand/.qoder-cn/plugins/cache/qoder-marketplace/architecture-visualization/0.1.0/examples/basic-architecture/run-smoke.mjs"

# 3. QGraphFlow 离线 HTML（改完 graph.json 后重跑；SKILL 目录＝qgraphflow/0.0.5/skills/q-flow）
node <SKILL>/scripts/validate-graph.mjs "<本目录>/qgraphflow/zhiguan-console-architecture.graph.json" --input-only --repo-root "D:/Project/zhiguanAI"
node <SKILL>/scripts/generate-viewer.mjs "<本目录>/qgraphflow/zhiguan-console-architecture.graph.json" "<本目录>/qgraphflow/zhiguan-console-architecture" --repo-root "D:/Project/zhiguanAI"
node <SKILL>/scripts/validate-graph.mjs "<本目录>/qgraphflow/zhiguan-console-architecture/graph.json" --repo-root "D:/Project/zhiguanAI"
# board 那张同法，把文件名换成 zhiguan-board-architecture
# 从此线时序图同法，换成 congci-feed-sequence
# 六面正源映射同法，换成 source-of-truth-map（改台账 soT.*／proj.* 后必须重跑这三条）

# 4. 轨一 DOT 渲染（六面正源映射）。插件的 dot 渲染器不是 CLI，靠两个环境变量传参
#    （签名取自 examples/basic-architecture/run-smoke.mjs:78-93 的 runViewer()，勿臆造 --out）：
PLUGIN="C:/Users/tiand/.qoder-cn/plugins/cache/qoder-marketplace/architecture-visualization/0.1.0"
QODER_CANVAS_SCRIPT_ARGS='{"targetFilePath":"D:/Project/zhiguanAI/05_产品与开发/架构可视化/zhiguan-source-of-truth.dot"}' \
QODER_CANVAS_DATA="$TEMP/sot.canvas.data.json" \
  node "$PLUGIN/canvases/dot/scripts/index.mjs"
# 产物在 $TEMP/sot.canvas.data.json 的 .["aicoding.formatViewer.dot"].svg；SVG 只落临时目录，不入库
```

> **重跑必读（2026-10-08 实测踩到的坑）**：QGraphFlow 有**版面硬闸**——`route.shared-segment`（两线共用 >12px 走廊）与 `route.parallel-channels`（并行线间距 <24px）算错误，**拒绝写任何产物**。`groups`（进程边界框）会把两条外部边挤进同一走廊，**4 节点小图也照炸**；本目录两张图的 `groups` 已清空（代价＝丢掉「同属一个进程」这一事实）。要恢复边界，只能拆更多视图，不能加回 group。

## 七、下一步建议（候法师裁定，未执行）

1. 把 `validate-model.mjs` 收进 `收口检查.ps1` 或 `vr_gates` 总跑器，成为一道闸——改动 console_server/board_server 后，架构图与代码不一致就报错。对应插件的 `architecture-health` 场景。
2. 补 `flow-visualizer`：画一张「一次闭环会话」的时序/数据流（采集→质检→阈值→节拍→VR→落盘→登记册），这是目前最缺的一张图。
3. 补 `dependency-impact-analyzer`：以 `console_server.py` 为根出爆炸半径图。注意该文件常有他窗在途改动，正是最需要影响面的地方。
4. 缺口补证：`closedloop`→`bridge` 直接调用点（medium 升 high）。

## 八、裁定记录

**2026-10-08　法师令「同意」→ 两插件双轨制成立**（提请见本轮对跑报告 §七）

| 轨 | 用什么 | 定位 | 产物 |
| --- | --- | --- | --- |
| 轨一·源头 | `architecture-visualization` 0.1.0 | 架构图的**可维护文本源**：能进 git、能 diff、能随代码改 | `.dot`／`.structurizr.dsl`／`architecture-model.json` |
| 轨二·交付面 | `qgraphflow` 0.0.5 | **给人看的那一份**：双击即开的离线 HTML，零概念、不出网 | `qgraphflow\*\index.html` |

**共用一份证据台账，不重复采证**：台账正本＝本文件 §二 ＋ `architecture-model.json`。QGraphFlow 的 `graph.json` **不另立台账**，其 `source` 锚点必须与本文件 §二 同源；日后架构有变，**先改台账、再重生成两侧**（命令见 §六）。

**入库口径已变（2026-10-08 法师令「架构可视化目录入库／放行。」）**：本目录已在 `.gitignore` 开显式例外并分批入库——`7be1ff8`（轨二第三视图 congci-feed-sequence）、`d2069bd`（本目录 11 件）、`7cb4a84`（`.gitignore` 例外三块，W3 代提）。**三笔均未 push。** 上一版「暂不入库，留本地，本目录任何文件均未提交」一句作废。

**2026-10-08　协调正本 §16.2「六面正源映射」→ 本台账新增 `soT.*`／`proj.*` 节点族**（法师裁「1–4 的建议我同意」，§17.1 转生效；协调窗派单执行）。台账侧：12 节点＋8 边，`node validate-model.mjs` PASSED（全模型 33 节点／27 边，high 28/26、medium 5/1）。两侧同源重生成：

| 轨 | 产物 | 规模 | 与另一轨的差异 |
| --- | --- | --- | --- |
| 轨一 | `zhiguan-source-of-truth.dot` | 17 节点／11 边，无回边 | 把两处「缝」画成独立节点（飞书云端不可直证、显示名不得当授权依据），并把图谱双轨拆成轨一／轨二两节点 |
| 轨二 | `qgraphflow\source-of-truth-map\{index.html,graph.json}` | 14 节点／9 边，`architecture` 类型 | 两处缝折进节点 `facts`，双轨并成一节点；`groups` **留空**以避开版面硬闸（代价＝丢掉「同属一个进程」这一事实，与已入库两张图同处置） |

两侧锚点即本文件 §二 末「六面正源映射」那 7 条＋台账 `sourceRefs`，轨二 `sourceEvidence` 14/14 passed（working-tree 基准）。轨二仅 2 条 `module.slot-collision` 信息级警告（业务任务／身份授权同紫色槽、架构事实／数据准入同梅色槽）——按 QGraphFlow 规约**不得为配色改模块名**，原样保留。

**同批订正一处错锚**：台账 `edge.sot-arch-to-graphdual` 原记 `evidence.md:84`，该处实为 §四 插件性能表、与本边无关；已改为 `:115`（§六 六面重生成命令行）＋`:144`（本节双轨制条款）。属行号级锚点漂移＋初记未核，非代码变更所致。

**边界（协调窗派单原文）**：本件**未改**规约正本 `AI-开工入口.md`、**未改** L1、**未** push、**未** `git add .`；`board_config.py`／`congci_pipeline.py` 等他窗在途件只读未动。

**§七 四项建议仍候裁，未执行。**
