# basic-memory 源码精读笔记（2026-09-24 · v1）

> 性质：只读调研。未安装、未引入任何代码或依赖。basic-memory 为 AGPL-3.0 传染许可证项目，本笔记**借策略不并码**——所有可借点均为纪律/协议层面，不涉及代码复用。
> 一手源：GitHub API 抓取 main 分支（2026-09-24，4032 stars，Python，主分支 `main`，经 `api.github.com/repos/basicmachines-co/basic-memory` 确认）。下文仓库路径均相对 `https://github.com/basicmachines-co/basic-memory`。

## 0. 总览与结论先行

- 定位：local-first 知识基座。三个入口（FastAPI / MCP server / CLI）共享一套服务层，各自有 composition root；MCP 工具是薄适配器，经类型化 client 调 API（本地走进程内 ASGI，云走 HTTP+API key）。〔`docs/ARCHITECTURE.md`〕
- 核心哲学与我方同构：**Markdown 字节是正典（canonical），SQLite/FTS/向量只是派生投影**；派生状态"设计上最终一致"，可由正典随时重建，正典绝不由投影反推。〔`docs/DOMAIN_MODEL.md`、`CLAUDE.md` "Consistency Model"〕
- 一个有趣旁证：该项目**自身治理也用我方同款体系**——仓库根有 CLAUDE.md/AGENTS.md（开工规约）、`.claude/skills/adversarial-review`（对抗评审技能）、`.github/basic-memory/SOUL.md`+memory-ci-capture.md（CI 里跑记忆捕获）、代码注释强制"Trigger/Why/Outcome"三段式判语（CLAUDE.md "Literate Programming"）。说明"规约成文、判语随行注释、评审技能化"在多 agent 工程里可长期运转。
- 一句话结论：它把"人审正典、机器重建视图"做成了带形式的工程纪律（解析器防御、写盘护栏、锁注、失效链接可见化、一致性评审条文），这正是我方治理最缺的"机制化"一环。

## 1. 数据模型：MD 里如何表达实体/观察/关系

### 文法（README 原话："这就是全部文法"）〔`README.md` "The Markdown format"〕

- **frontmatter**：`title/type/tags/permalink/created/modified/schema`；自定义键入 `entity_metadata` 并可检索；所有值归一化为安全类型（日期→ISO 串、布尔→`"True"` 字符串）防下游崩溃。〔`markdown/entity_parser.py::normalize_frontmatter_value`〕
- **observation**：`- [类别] 正文 #标签 (语境)`。类别自由文本；`## Observations` 标题仅是惯例，**解析器按行文法在全文任意位置识别**。无类别但带 `#标签` 的行也升格（默认类别 `note`）。
- **relation**：显式 `- 关系类型 [[目标]] (语境)`（多词类型须引号）；裸 `- [[目标]]` 与行文中任意 wiki 链接→隐式 `links_to`；`#bm:links_to` 指令可强制把"散文+链接"行降级为 links_to。

### 解析器的防御性排除（每条都对应一次真实脏数据事故）〔`markdown/plugins.py`〕

- 时间码 `[00:00:11]` 不算类别（防转录稿每行造垃圾观察，#1219）；任务框 `[ ]/[x]/[-]` 及 Obsidian 扩展词汇 `[/][>][?]` 排除（#1241）；行内代码中的 `[[ ]]` 掩码不解析；引用块（`> [!info]` callout）内不解析；带散文尾巴的伪显式关系整行降级为 links_to（#1260：旧版会拿链接前单词造垃圾关系类型并吞掉同行后续链接）。
- YAML frontmatter 畸形→整块按 body 处理并告警（不吞文本，#1451）；非法语义时间戳=该文件索引报错，**不静默回退**；BOM/NUL 字节/Windows 路径渲染各有显式处理。

### MD→SQLite 映射〔`models/knowledge.py`〕

- `Entity`：一行一文件；`permalink` 项目内唯一（仅 Markdown 类型）、`file_path` 项目内唯一；`checksum/mtime/size` 为同步簿记字段。
- `Observation`：每行有合成 permalink（`笔记permalink/observations/类别/内容slug`），同身份重复行按文档序加 `duplicate_index` 序号——曾发生观察静默去重事故（#1214），现存迁移 `v5o6b7s8d9e0_add_observation_duplicate_index` 与专用索引。
- `Relation`：唯一约束 `from_id+relation_type+to_id` 与 `from_id+relation_type+to_name` 双保险；`generation` 字段把关系行钉在"某一次被接受的笔记版本"上（fence），重建期旧代写入自动作废。
- 前向引用：指向不存在目标的链接保留 `to_name` 成未解析态，目标创建时自动重连；**目标被删时入边 `to_id` 置 NULL 而非级联删**——源码注释原话："一个悄悄丢边的图会在断链之上报告一切健康"。〔`models/knowledge.py` 注释、`docs/DOMAIN_MODEL.md`〕
- 时间两层分离：frontmatter `created/modified` 是笔记语义时间；文件系统 mtime 只是"物理同步簿记"；移动/物化不改语义时间；被动索引永不补写时间戳。
- 进阶投影（了解即可，均可从 MD 全量重建）：`@effective[2026-06-10,2026-07-27)` 时间限定符→`MemoryTimeIndex` 有效时间区间索引（边界存成定宽文本、字典序即时间序，兼容 SQLite/PG 两方言）；`NoteSection` 存标题→行号/字节偏移，供分段读。

## 2. 同步机制：哪些真相同步、哪些异步

- **本地主路径 = 文件为正（file-first）**。〔`docs/DOMAIN_MODEL.md` "Local File-First Flow"〕
  - 人改文件→异步 watcher 收敛：watchfiles `awatch` 递归监视项目根，**去抖 `index_delay` 默认 1000ms**（config 旧名 `sync_delay`，有迁移兼容层）；gitignore 式忽略模式过滤；监视器状态落 `watch_status.json` 可观测。〔`index/watch_service.py`、`config_models.py`〕
  - 容错分层：按项目分批，**单项目批失败只隔离该项目**（`gather`+`_handle_changes_isolated`，注释明说防止一个坏文件拖死全部项目）；项目清单每 300s 周期重载（`watch_project_reload_interval`），启动后已删除的项目不再被后台索引（`_project_is_configured` 重读实时配置）。
- **AI 经 MCP 写入 = 同步索引**：`write_note` 同一请求内写文件、解析、落 entity/observation/relation/search 行，响应直接回报观察分类计数与 resolved/unresolved 关系数——写方当场自检，不等异步收敛。未解析关系附提示"目标创建后自动解析"。〔`mcp/tools/write_note.py`〕
- **云/DB-first = 受纳-物化两段**：先 accept 生成最终 MD 字节存 `NoteContent`（`db_version/db_checksum`），worker 把同一字节物化落盘并记 `file_write_status ∈ pending/writing/synced/failed/external_change_detected`；`external_change_detected` 是"库内受纳版本与磁盘人手改动冲突"的显式状态。并发用乐观 CAS（条件 UPDATE+RETURNING 验证 db_version/db_checksum），固定锁序 NoteContent→Entity，**文件系统/网络 I/O 一律在事务外**，删目录用"快照→事务外探针→按快照等值删除"三段式防 ABA。〔`docs/TRANSACTION_ISOLATION.md`、`docs/DOMAIN_MODEL.md`〕
- **变更日志（journal）与投影分层**：DB-first 接受的每次笔记变更写 `RuntimeAcceptedProjectNoteChange` + 项目级 `partition_position` 单调水位；wiki 投影、检索投影、时间线读都追这个水位、允许滞后；外部文件变更的 reconcile 路径**尚未**进 journal（文档明说是过渡态）。投递类事件（webhook/SSE）"证明投递、不证明接受"，永不当语义日志用。〔`docs/DOMAIN_MODEL.md` "Accepted Change Journal / Event Surfaces"〕
- 一致性评审纪律（`CLAUDE.md` 成文）：正典字节损坏/误重写/误删**永远是真实缺陷**；投影滞后/瞬态陈旧**默认不是 bug**（下次写、索引、`reindex`、孤儿清扫自愈）；禁止为自愈竞态加锁加补偿，"死锁永远比暂时陈旧更糟"——把最终一致写成了 code review 可执行条文。

## 3. MCP 工具面：暴露什么、如何引导 AI 写记忆

- 全量清单〔`mcp/tools/__init__.py`、`README.md`〕：
  - 内容：`write_note / read_note / edit_note / move_note / delete_note / read_content / view_note`
  - 检索发现：`search_notes / recent_activity / list_directory`；图导航：`build_context`（沿 `memory://` URI 按深度取实体+观察+关系，支持分页与 compact）
  - 项目：`list_memory_projects / list_workspaces / create_memory_project / delete_project`
  - schema：`schema_infer / schema_validate / schema_diff`；兼容位：`search / fetch`（ChatGPT 面）；诊断：`basic_memory_diagnostics`；POSIX 只读全家桶：`cat / find / grep / ls / tail / man`（每工具有对应手册页，`man` 即工具文档入口）
- **每工具带 MCP 行为标注** `readOnlyHint/destructiveHint/idempotentHint/openWorldHint`（write_note 标 destructive、search 类标 readOnly），agent 免试错选对工具。〔`write_note.py` 装饰器〕
- AI 写记忆的引导机制（重点核实）：
  - 引导主要靠**超长 docstring + 服务端响应回读**，不是外部 prompt：write_note 文档串内嵌观察/关系语法示例与目录说明；`directory` 参数接受 `dir/folder/path` 别名（源码注释："这些词在模型训练数据里混用"——**为 LLM 直觉容错**是设计决定）。
  - 近重复合并引导：新建成功后服务端自动语义近邻探测，响应附 "Similar existing notes" 段建议合并而非留孤儿（#1259）；探测失败绝不误报写失败。**覆盖写默认禁止**，冲突响应是一张"你的目标→对应操作"选择表（见第 4 节）。
  - 行为准则：MCP resource `ai_assistant_guide`——"先 `recent_activity` 定位→先 search 后 create→匹配先 read→用 edit_note 做针对性修改→有意义写入先向人确认→优先用 project_id 而非名字（会撞名）"；`getting_started` prompt 明文 **offer-not-act**：只*提议*第一条笔记、等用户同意才写，"无近期活动不能推断库是空的"。〔`mcp/resources/ai_assistant_guide.md`、`mcp/prompts/getting_started.py`〕
  - 上下文经济性：`--compact`/`compact=True` 去正文留标签与路径，文档明说"降的是模型可见输出，不降数据库工作量，也不承诺 token 上限"——把上下文成本当成工具参数显式管理。〔`docs/COMPACT_DISCOVERY.md`〕
- **未证实项**：任务书提到的 `dir_hints`、write 模板（templates）在现 main 及抽查的 v0.12.0/v0.15.0 的 `write_note.py`、`schemas/base.py` 中均无踪迹（现仓库 Handlebars templates 仅渲染 conversation/search prompt）；疑为旧文档或二手文章混入，〔单源待校〕。观察"类型推理"也不存在——类别词表只是 docstring/AI 指南中的约定（fact/decision/insight/...），服务端不校验不推断。

## 4. "记忆即文档"的编辑纪律：防 AI 写坏文件

- **默认拒覆盖**：`write_note` 撞名默认返回错误（可配 `write_note_overwrite_default`）；错误正文即操作迁移表：追加→`edit_note(append)`、改节→`replace_section`、先看→`read_note`、确要整体替换→显式 `overwrite=True`。`edit_note` 操作集：`append/prepend/find_replace/replace_section/insert_before_section/insert_after_section/edit_item`。**AI 日常写被引导为增量行操作，全量重写是例外且须显式**。〔`write_note.py::_format_overwrite_error`、`edit_note.py`〕
- **锁注（"审查权不离人"的最强工程先例）**：frontmatter `locked: true`（仅 YAML 布尔）后，一切 API/MCP/CLI 写、编辑、覆盖、删返回 HTTP 423；**提案内容不能顺手去锁**（校验读磁盘现有正典字节，不看你想写成什么）；移动保留锁；含锁定文件的目录整体删除被拒；解锁唯一途径=人直接编辑 MD。文档坦承边界：这不是文件系统访问控制，绕过 API 直接改文件=人的物理权威，索引照单 reconcile。〔`docs/LOCKED_NOTES.md`〕
- **schema 校验但不作茧**：Picoschema 写在 frontmatter（不引入新语法），schema 字段映射到既有 observation/relation 行文法；未覆盖的观察/关系合法（"schema 描述子集，不是紧身衣"）；两档模式 `warn`（默认提示）/ `strict`（阻塞同步，供 CI）。schema 本身也是一篇普通笔记（`type: schema`，惯例放 `schema/`）——**规范即文档**，可搜索、可带关系。附 `schema infer`（100% 出现→必填、≥25%→可选、<25%→不采）与 `schema diff` 漂移检测。〔`docs/NOTE-FORMAT.md` "Schemas"〕
- 校验与写路径刻意解耦：现 main 中 **schema 校验不在写路径上自动执行**（`services/schema_validation_hooks.py` 模块注释原话："没有任何写路径运行它，实体上也不存校验状态"），只作为独立命令/托管侧观察钩子。〔单源：该文件头注释；与其 docs "strict 阻塞同步"的表述存在张力，孰为现行为**待校**〕
- 路径与身份护栏：目录参数须落在项目根内（越界拒绝+告警日志）；非 Markdown 实体 permalink 恒为 NULL（"库内地址不能往返回文件，就不许冒充正典"）；`external_id` 跨更新与移动保持稳定，`title` 明示"是可变显示元数据，不是身份"。〔`write_note.py`、`docs/DOMAIN_MODEL.md`〕

## 5. 我方取舍：借什么、落到哪、明确不借什么

**明确不借**：

1. 任何代码/依赖——AGPL-3.0，连"参考实现级"抄写都不做；本笔记只取策略。
2. DB-first 受纳-物化双段写、CAS 锁序、Postgres/pgvector/embedding——为云多租户设计；我方单机、文件为正一路径已够。
3. importer/auto-capture 类旁路人审通道（Claude/ChatGPT 会话批量导入、`hooks/inbox` 会话归档钩子）——我方红线"经验必成文、成文必经人"，自动落库不引入。
4. 云端 workspace/计费/Team 面——与个人项目无关的复杂度。
5. 注：任务书给的文档站 basic-memory.ai 未在本次一手源出现，仓库引用的文档域是 `docs.basicmemory.com`，〔单源待校〕。

## 对我方可借清单（按收益排序）

1. **默认拒覆盖 + 冲突即引导表**（收益最高，改动最小）：AI 对 L1 状态文件、登记分片、决策日志一律禁止全文重写；变更只走"追加条目/改节/替换单条"三种增量操作，整体重写须人明示。落点：`AI-开工入口/开工规约`增"文件写入纪律"一节，照其冲突表写"目标→操作"映射。〔第 4 节〕
2. **locked 单向锁惯例**：`00_当前状态.md`、决策日志、判语库定稿条目 frontmatter 加 `locked: true`；各窗口开工先查锁，锁内只读；解锁=人直接改文件，AI 无权经任何工具路径解锁。这是"审查权不离人"的机制化，不是口号化。〔`docs/LOCKED_NOTES.md`〕
3. **观察/关系行式登记**：一事一文件不变，正文条目采 `- [判语|决定|教训|待办|事实] 内容 #标签 (出处)` 行法 + `- 依据/导致 [[目标]]` 关系行；纯文本无损、不依赖工具，但可按类别检索、引用成图。落点：登记分片模板、案例判语库条目格式。〔第 1 节〕
4. **近重复先探测、人裁决合并**：新开分片前先关键词/语义检索，报告附最近 3 条既有条目+"合并还是新建"建议，裁决权在人。借其 similar-notes 思路但保留人审闸。〔第 3 节〕
5. **正典/派生两层分离**：明示 `00_当前状态.md` 与各类看板是**派生视图**——可随时从分片重建、审查不针对它、滞后不是 bug；分片/判语原文是正典，损坏即最高级事故。这条纪律同时防两个方向：AI 拿视图当真相、人也别再手工维护视图。落点：L1 文件头声明+规约仲裁规则。〔第 0、2 节〕
6. **语义时间与簿记时间分离 + 非法即阻塞**：登记时间写进各文件 frontmatter（语义时间），文件 mtime 只作同步簿记；移动/整理不改语义时间；时间/编号格式非法=开工阻塞项，不静默回退。落点：分片编号与日期窗号规范。〔第 1 节〕
7. **断链可见化**：分片引用不存在的事号/窗口号时保留原文并标 `未解析`，目标建立后回填；禁止为"干净"静默删失效引用（"丢边的图=对断链报告健康"）。落点：登记分片引用规范。〔第 1 节〕
8. **规则带事故编号**：其解析器每条防御规则都注 issue 号与事故机理；我方判语库/规约条目增设"源自事故：xxx"字段，规则可溯源、将来可复审废除。连代码注释都强制 Trigger/Why/Outcome 三段式——形式可直借。〔第 1 节、`.claude` 旁证〕
9. **操作三性标注**：给 W1-W4 的常行动作逐项标注 只读/破坏性/幂等，写进分工表，并行窗口免试错选对动作。〔第 3 节〕
10. **规范即笔记 + warn→strict 两步走**：格式规范本身存为普通 MD（可搜索可引用）；新格式先 `warn` 试行、沉淀后对关键文件升 `strict` 阻塞开工。落点：判语库格式规范。〔第 4 节〕

## 附：关键源文件速查（main@2026-09-24，供后续复审定位）

| 主题 | 路径 | 看点 |
|------|------|------|
| 笔记文法权威文档 | `docs/NOTE-FORMAT.md` | observation/relation/picoschema 全参考 |
| 域模型与真相源规则 | `docs/DOMAIN_MODEL.md` | canonical/derived、journal、写流 7 步 |
| 一致性评审纪律 | `CLAUDE.md`（Consistency Model 节） | "死锁比暂时陈旧更糟"条文 |
| 解析器与假阳性防御 | `src/basic_memory/markdown/plugins.py` | 每条排除规则注 issue 号 |
| 锁注纪律 | `docs/LOCKED_NOTES.md` | 单向锁、人编辑是唯一解锁 |
| 写入护栏 | `src/basic_memory/mcp/tools/write_note.py` | 冲突表、similar-notes、别名容错 |
| watcher 与去抖 | `src/basic_memory/index/watch_service.py` | 批隔离、项目重载、状态可观测 |
| DB 表映射 | `src/basic_memory/models/knowledge.py` | duplicate_index、SET NULL 入边 |
| AI 行为准则 | `src/basic_memory/mcp/resources/ai_assistant_guide.md` | offer-not-act、search-before-create |
| 冲突/并发 | `docs/TRANSACTION_ISOLATION.md` | CAS、锁序、事务外 I/O |

未能核实（均已在正文标注）：`dir_hints`/write 模板是否存在于历史版本（抽查 v0.12/v0.15 无果）；文档站域名（basic-memory.ai vs docs.basicmemory.com）；schema strict 模式在当前写路径上的实际强制执行程度。

---

*精读：W3·Qoder（Session W3-QODER-20260924-F），只读调研未装未并码。*
