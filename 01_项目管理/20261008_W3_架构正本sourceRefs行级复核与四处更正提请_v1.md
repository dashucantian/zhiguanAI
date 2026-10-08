# 20261008 W3｜架构证据正本 sourceRefs 行级复核与四处更正提请

日期：2026-10-08。窗口：W3（制度与机动）｜身份：AI-014（Qoder 桌面端）｜Session：`W3-QODER-20261008-QGFSEQ-A`。
缘起：写 `D-1008-W3b` 时顺手回查正本，发现 `congci_pipeline.py:564` 已不指着它声称的那件事 ⇒ 法师令「继续」⇒ 对正本做一次**全量行级复核**。本文是**提请件**，正本一字未动。

## 一、范围与方法（可复跑）

- 对象＝`05_产品与开发\架构可视化\architecture-model.json`：**21 节点／20 边／75 条 sourceRefs／涉 19 个文件**；其中**带行号 64 条**、仅到文件级 11 条（去重 9 个文件）。
- 方法＝逐条取**现势该行内容**＋该行近 ±4 行的声明，判"还指着那件事"吗。全量清单产出在本窗临时件 `_analysis_tmp\_w3_src_ref_audit.txt`（203 行，不入 git）。
- **为什么这道复核此前不存在**：`validate-model.mjs` 第 27 行是 `existsSync(path.join(ROOT, filePart))`，而 `filePart` ＝**剥掉 `:行号` 之后的路径**⇒ **行号根本不进校验**，只验文件在不在；它另有一道 confidence 闸（第 40 行）但**只卡"现状节点"必须 high/medium，边不卡**。QGraphFlow 的 `--repo-root` 闸核到"文件存在＋区间贴合＋不越界"，**空行也算贴合**。⇒ 64 条行号级锚点**从未被任何一道闸回核过**。

## 二、结论：4 条须更正（其中 2 条挂在 `confidence: high` 上）

| # | 现记 ref | 挂在谁 | 现势该行 | 真身 | 性质 |
|---|---|---|---|---|---|
| 1 | `congci_pipeline.py:564` | `edge.closedloop-to-bridge`（medium） | **空行**（563 是分区注释、565 才是 `def _brain_lock():`） | **574** `from cadence import Brain`（在 `_brain_loads` 内） | 漂移 **+10 行** |
| 2 | `congci_pipeline.py:642` | 同一条边 | `return {"skipped": True, …` | **652** `from zhiguan_cadence_bridge import process_session`／**653** 调用 | 漂移 **+10 行** |
| 3 | `zhiguan_cadence_bridge.py:45` | `module.cadence-bridge`＋同一条边 | `try:` | **46** `from cadence import Brain` | 弱锚（+1，指到语法壳不是声明） |
| 4 | `muse2-repo/muse2-master/nd_routes.py:20` | `module.nd-routes`＋`edge.console-to-ndroutes`，**两条都 high** | **空行** | **30** `def start_hub(listen_port=0, …)`（或 22 `_hub = None`） | 弱锚／空行 |

⚠ 第 1、2 条**各低 10 行且同向**⇒ 不是编错，是该文件后来插了约 10 行、正本从未回头核。⇒ **凡行号级 sourceRefs 都是会过期的存证**，改完代码要顺手回核被它引用的那几条。

## 三、另三条弱锚（不算错，建议顺手改准）

1. `console_server.py:3178`（`edge.fashi-to-console`，high）现势是 `ap.add_argument("--https-port", …)`——证的是端口参数，不是"法师调用驾驶舱"。建议改指 `584`（`_do_save`，点保存真正进的那道）或 `3234`（`uvicorn.run`）。
2. `05_产品与开发/任务看板/board_server.py:81`（`edge.board-to-state`，writes，high）现势是 `class JobQueue:`，与"写 state"无直接关系；同边另一条 `:184`（`QUEUE.add(Job(...))`）才贴。建议删前者或换成真正落盘 state 的那行。
3. `zhiguan_cadence_bridge.py:34` 现势是 docstring 里的 `自测：python zhiguan_cadence_bridge.py --selftest`——勉强算"带 --selftest"的据，可留，但建议换成 `69` 行 `class ZhiGuanCadenceBridge`（轨二那张图用的正是 69-82，已对）。

## 四、更要紧的一条：那条边**方向记错**，不是行号问题

- `edge.closedloop-to-bridge`（`closedloop → cadence-bridge`，medium）的两条 congci 侧 refs 证的是 **养脑 → 桥**，**证不到 闭环 → 桥**。
- 反向取证：`closedloop_controller.py`／`closedloop_experiment.py`／`closedloop_engine.py` 三件对 `cadence|bridge|Bridge` **零命中**；controller 自持 `beat_default`／`beat_min`／`volume` 等参数（`closedloop_controller.py:35-60`），节拍是它自己算的。
- 轨二 `zhiguan-console-architecture` 里那条 `e_ctrl_bridge`（controller→bridge）**当时已如实标 `evidence:"inference"`** ⇒ 没有假边，但 medium 这个档也撑不住。
- 轨一 `zhiguan-l2-containers.dot` 第 82 行 `closedloop -> bridge [label="阈值决策"]` 同样缺据；**第 94 行 `congci -> bridge` 才是有据的那条**。

## 五、提请裁定（三案择一）

| 案 | 做什么 | 代价 |
|---|---|---|
| 甲·最小 | 只改 §二 4 条行号 | 锚点变有效，但**边方向仍是错的**——不推荐 |
| **乙·建议** | §二 4 条＋§三 3 条行号更正；`edge.closedloop-to-bridge` confidence **medium→low**、description 改记"据仅及养脑侧，闭环侧反向取证为零"；`evidence.md` §二 第 38 行同步更正（并把第 42 行 `congci_pipeline 归属＝unknown` **销案**，补 `console_server.py:699` 直调 `enqueue`）；DOT 第 82 行改虚线注 inferred 或删，并**补 `console -> congci` 一条** | 动 3 个已跟踪正本文件；DOT 变了要重出 SVG（亚秒级） |
| 丙·彻底 | 乙之上，给正本**补从此线节点族**（`congci_pipeline` 函数级、`ingest_session.py`、`processed_index.json`），把 `D-1008-W3b` 那张 sequence 的 9 个行级锚点收进正本，做到轨一轨二真同源；随后重生成 DOT／DSL／两张 architecture 图 | 除乙的代价外，**还要重生成已入库的轨二产物**（`d2069bd` 里 6 件），须重新放行 |

**共同风险如实报**：无论乙丙，改完行号后**旧 commit 里那份正本仍指向当时的行号**——正本 `metadata` 未记"复核于哪个 commit"。建议顺手加一个 `refsVerifiedAt: <commit>` 字段，否则这道复核半年后又会漂。

## 六、未动声明

本轮**只读**。`architecture-model.json`／`evidence.md`／`zhiguan-l2-containers.dot`／两张轨二图**一字未改**，本文是新件。未 staged、未提交、未 push；`.gitignore` 与他窗在途件未动。
