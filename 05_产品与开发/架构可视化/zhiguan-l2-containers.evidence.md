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
| `qgraphflow\zhiguan-console-architecture\index.html` | 控制台＋闭环链那一张：谁调谁、证据落在哪个文件哪一行 | **双击即开**（离线自包含，无需服务、不出网） |
| `qgraphflow\zhiguan-board-architecture\index.html` | 任务看板那一张：法师↔看板↔MCP↔AI 窗口 | 同上 |
| `qgraphflow\*.graph.json` | 上面两张 HTML 的图数据源（QGraphFlow 格式，自带行区间级 `source`） | 改这里再重跑三条命令 |

## 二、证据来源（已逐条抽查行号属实）

核心运行时：
- `console_server.py:174`（FastAPI 实例）、`:3174`/`:3178`（端口 8777/8778）、`:3234`（uvicorn 启动）
- `console_server.py:71,72,76,80,125,193,666`（导入 closedloop / controller / qc_pipeline / nd_routes / registry_tx / muse_local_server / session_contract）
- `console_server.py:60-64`（sys.path 注入 muse2 子仓）
- `console_server.py:2224,2236,2249,3167`（FileResponse 出 vr_feedback / vr_mandala / focus / console 页面）
- `closedloop_experiment.py:38,43`、`zhiguan_cadence_bridge.py:34,45,509`、`qc_pipeline.py`
- `muse2-repo/muse2-master/nd_routes.py:20`、`nd_hub.py`、`neuradock_receiver.py:54`、`muse_local_server.py`

看板子系统：
- `05_产品与开发/任务看板/board_server.py:39`（HOST/PORT=127.0.0.1:8848）、`:42`（FastAPI）、`:81-147`（JobQueue）、`:184-192`（采样器注册）、`:700-711`（SSE /api/stream）、`:718-729`（MCP_TOOLS）、`:736-751`（分发）、`:754-785`（POST /mcp）、`:788-796`（GET/DELETE→405）
- `board_sources.py:19-22`（扫描 ~/.qoder-cn）、`:25`（WEINA_DIRS=01_项目管理/任务关系图）、`:264-272`（rglob `_records_raw.json`）
- `board_privacy.py`、`board_config.py:29`（千问）

## 三、假设与缺口（confidence 未达 high 的部分）

| 项 | 状态 | 说明 |
| --- | --- | --- |
| `closedloop` → `cadence-bridge` 直接调用点 | **medium（inferred）** | 只确证 `congci_pipeline.py:564,642` 同时导入 cadence 与 bridge；闭环到桥的直接调用未逐行确认。补证办法：在 `closedloop_controller.py` 中搜 bridge/cadence 调用点 |
| `registry_tx` → Zen-EEG CSV 读写 | **medium** | 依据 docstring，未实测跨盘写入 |
| `board_sources` → 飞书 | **low（未入模型）** | 证据在 `01_项目管理/任务关系图/20261007_W3_维那快照拉取_v1.py:45`，是**离线拉取脚本**而非看板进程内调用；DOT 图里画成虚线，模型 JSON 里**故意不建边**，避免把批处理伪装成运行时依赖 |
| 看板 → LM Studio :1234 | **low（未入模型）** | 证据在 `01_项目管理/评测集黄金任务集_运行/run_eval.py:38`，同属评测脚本而非看板进程；DOT 里虚线，模型不建边 |
| `congci_pipeline` 归属 | **unknown** | 与 console_server 的关系未确证，DOT 中只画到 registry/qc/bridge，未画与驾驶舱的边 |
| arxiv 出网 | **not found** | 子代理未找到证据，未入图 |

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

**入库口径未变**：法师 2026-10-07 裁「暂不入库，留本地」，本目录整片仍在 `.gitignore` 的 `05_产品与开发/*` 排除内，`.gitignore` 未动，本目录任何文件均未提交。是否开例外入库，候法师另令。

**§七 四项建议仍候裁，未执行。**
