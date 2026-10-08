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
| 1 | `congci_pipeline.py:564` | `edge.closedloop-to-bridge`（medium） | **空行**（563 是分区注释、565 才是 `def _brain_lock():`） | **574** `from cadence import Brain`（在 `_brain_loads` 内） | ⚠**非正本错**：HEAD 上就是 564，10 行是他窗未提交改动 |
| 2 | `congci_pipeline.py:642` | 同一条边 | `return {"skipped": True, …` | **652** `from zhiguan_cadence_bridge import process_session`／**653** 调用 | ⚠同上：HEAD 上 642／643 正确 |
| 3 | `zhiguan_cadence_bridge.py:45` | `module.cadence-bridge`＋同一条边 | `try:` | **46** `from cadence import Brain` | 弱锚（+1，指到语法壳不是声明） |
| 4 | `muse2-repo/muse2-master/nd_routes.py:20` | `module.nd-routes`＋`edge.console-to-ndroutes`，**两条都 high** | **空行** | **30** `def start_hub(listen_port=0, …)`（或 22 `_hub = None`） | 弱锚／空行 |

⚠ **本条定性已在 §七.自曝③ 推翻（10-08 15:5x）**：当时写的是"第 1、2 条各低 10 行且同向⇒文件后来插了约 10 行、正本从未回头核⇒凡行号级 sourceRefs 都是会过期的存证"。**核对 HEAD 后：`git show HEAD:congci_pipeline.py` 里 `from cadence import Brain` 就在 564、`process_session` 导入在 642、调用在 643——正本在 HEAD 上完全正确，一个字都没漂。** 那 10 行是**他窗此刻未提交的改动**（工作区 945 行 vs HEAD 935 行）。⇒ 真问题不是"正本过期"，而是**锚点基准从未定义**：同一份正本无法同时贴合 HEAD 与工作区，而 `validate-model.mjs` 与 QGraphFlow 的 `--repo-root` 都只查**工作区**。第 3、4 条（`cadence_bridge.py:45` 指到 `try:`、`nd_routes.py:20` 是空行）**HEAD 上也是错的**，那两条才是真缺陷。

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

## 七、执行回执（2026-10-08 15:4x｜法师裁「乙」＋「顺手加一个 refsVerifiedAt 字段」）

**已执行**（工作区，候放行）：

| 项 | 改法 | 结果 |
|---|---|---|
| §二 4 条 | `congci_pipeline.py:564→574`、`:642→652`＋补 `:653`、`zhiguan_cadence_bridge.py:45→46`、`nd_routes.py:20→30`（节点＋边两处） | 锚点全部改到真实声明行 |
| §三 3 条 | `zhiguan_cadence_bridge.py:34→69`（类声明）；`console_server.py:3178→584`（`_do_save`）；`board_server.py` **保留** `:81/:184`、**补** `:35`（`SCREEN_DIR`）与 `:221`（`PROBE_FILE.write_text`，state 唯一真实写盘点） | 见下方自曝① |
| §四 那条边 | **从模型 JSON 删边**（边数 20→19），evidence.md §三 第 38 行改记「撤边」并写明反向取证结论；DOT 第 82 行改注释留痕、DOT 补 `console -> congci`（现势 30 条边、括号平衡、端点全声明） | 见下方自曝② |
| §三 第 42 行 | `congci_pipeline 归属` 由 **unknown → 已确证**，补 `console_server.py:699`（监测）与 `:1152`（闭环）两挂点；同时如实标出"模型仍无从此线节点族"⇒ 那部分留在丙案 | 挂点已确证，整条线未建模 |
| `refsVerifiedAt` | 加进 `metadata`（at／commit／by／method／note 五项），并让 `validate-model.mjs` 的回执多打一行 `refs_verified_at`——**MISSING 即视为待复核**，字段不会烂在文件里没人看 | 闸现况 `PASSED`，`refs_verified_at: 2026-10-08` |

**回归闸**：`node validate-model.mjs` ⇒ `PASSED`，21 节点／**19 边**，high 19/18、medium 2/1、low 0/0，errors 空。DOT **未重出 SVG**——该目录本就没有 SVG 产物（轨一只存文本源），提请件 §五 里"要重出 SVG"这一代价项**当场作废**。

**两处自曝**：
1. **本文 §三.2 我自己判错了**。我写"`board_server.py:81` 与写 state 无直接关系，建议换掉"——回读该边 description 才发现它写的是「**JobQueue** 定期把运行态写快照」，而 `:81` 正是 `class JobQueue:`、`:184` 正是带 `interval=5/20` 的注册行 ⇒ **原锚点是对的，不该换**。实际改法是**补**真实写盘点 `:35/:221`、原两条保留。提请件里那句建议照原文留着不删，以免后窗以为它一开始就是对的。
2. **执行时偏离法师所裁字面一处**：乙案写的是"confidence **medium→low**"，但 `evidence.md` §三 末尾的既有纪律明写「**模型 JSON 只收 high/medium**，low 的东西不建边」（第 40/41 行那两条 low 项就是这么处理的）。降 low 会自相矛盾，故按纪律**删边**、把结论留在 evidence.md §三 与 DOT 注释里。信息不丢，但**这一处是我不照字面办**，请法师追认或改回。

**未动**：两张轨二图（其锚点经核本就正确：`nd_routes.py:26-43`、`bridge 69-82`，未受本次更正影响）；规约；`.gitignore`；他窗在途件。未 push。

3. **本文主结论之一当场证伪（最重要的一条自曝）**：我把"§二 第 1、2 条各低 10 行"归因为**正本过期未回核**，并以此立了"行号级存证会过期"这条纪律。**核对 HEAD 后不成立**——`git show HEAD:congci_pipeline.py` 里 564／642／643 就是那两件事，**正本一字没错**；那 10 行是**他窗此刻未提交的改动**（工作区 945 行／HEAD 935 行）。我只查了工作区就下"过期"判断，**漏掉了"工作区≠HEAD"这个前提**，而本仓四窗共用一个工作树、常年有他窗在途改动，这个前提**必须先查**。
   - **仍然成立的**：`cadence_bridge.py:45`（指到 `try:`）与 `nd_routes.py:20`（空行）在 **HEAD 上也是错的**，那两条是真缺陷，已更正；"闸不验行号语义"（§一）与"那条边方向记错"（§四）与 HEAD／工作区之争无关，也都成立。
   - **改出的新纪律（替换原那条）**：锚点必须**声明基准**。已在 `metadata.refsVerifiedAt` 加 `tree: "working-tree"`＋`baseCommit: "7a553b5"`＋`inFlight`（点名 `congci_pipeline.py` 带他窗未提交 +10 行，并写明"那 10 行若回退须同步回改 564／642／643"）。⚠**副作用如实报**：我按工作区改的 574／652／653，在 W1 那批提交之前**与 HEAD 不一致**——这是"基准＝工作区"的必然代价，不是新错。
