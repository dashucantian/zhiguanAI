# DSH Super-agent 原型对止观AI的调研分析 v1

- 任务：`TASK-20261103-01`
- 出具：2026-11-03 14:53 起核，写毕时刻待补实取
- 发件窗：Qoder 执行位 `c73afab0`；复核：W3 `4ef78b3e`；验收：法师
- 范围：只读公开资料＋本项目现势文件；未 clone、未运行原型代码、未改项目规约或他窗文件
- 重要限缩：GitHub 页面和 raw README 的 WebFetch 本轮失败；以下仓库内容依 GitHub 搜索索引摘录，长文依转载页面摘录。未经原始页面直接打开的结论均标出来源强度，不冒充一手读取。

## 一、收件与依据

收到法师转贴，经 W3 派工函 `20261103-DSH-4ef78b3e-致Qoder窗c73afab0_SuperAgent调研任务书_v1.md` 执行。调研对象为 `deepseek-ai/dsh-superagent-prototype` 及《Super-agent 设计探索：迈向更自主的 Agent 系统》。核实尺按任务书五项；结论按「对本项目的意义／可借结构／三档落地」组织。

项目内基线：
- 六客户端表：`01_项目管理/20261101_中枢v0一页纸_呈批_v1.md:7-17`；其中 Qoder 为执行位，OpenCode 是被接的服务而非协作窗，Codex CLI／千问当时未接线。
- 四主线最新空单：`01_项目管理/20261102_四主线派工空单_v2.md:6-52`；脑电待派、VR 已交待验、AI 复刻中环已跑而外环候数据／内环待补、12.8 营 P1 待开工。注意该件是 11-02 时点快照，不冒充 11-03 实时状态。
- 分工：协调位—执行位—判读位，见 `01_项目管理/20261101_中枢v0一页纸_呈批_v1.md:62-65`；当前任务登记又明定本任务执行 Qoder、复核 W3、验收法师，见 `01_项目管理/任务登记.md:11-20`。
- 已有相关研究：`01_项目管理/20261029_数字员工与内中外循环对照研究_v1.md:12-24,30-50,95-115,160-173`。

## 二、逐条对任务书判据

### 1. 仓库是否真实、路径、创建日期

- **判：符合（存在、路径）；创建日期未验。**
- 可观测源：GitHub 搜索结果《GitHub - deepseek-ai/dsh-superagent-prototype》，地址 `https://github.com/deepseek-ai/dsh-superagent-prototype`，本轮 2026-11-03 14:5x 搜索；摘要显示仓库标题、路径与 README 片段。GitHub 页面直接读取失败，故不声称亲自读取仓库页。
- 关于创建日期：检索到二手分析称仓库记录创建于 2026-10-31；GitHub 元数据/API 本轮未能直接取得，故 **10-31 创建未验**。首提交时间也不等于创建时间。
- **证伪句**：若该路径返回 404、组织/仓库名不同，存在性结论即不成立；若 GitHub API 的 `created_at` 不是 2026-10-31，则该日期主张不成立。

### 2. 「接近一万三千行 TypeScript」

- **判：未验。**
- 搜索到第三方文章分别称「约 14k 行」或约 13k；没有本轮从仓库快照对受控文件集合计数的证据，数值互相不齐，不能将转贴数字写成事实。语言为 TypeScript 的线索来自 GitHub 搜索摘要及多篇二手报道，但行数仍未核。
- **证伪句**：若固定 commit 后按明确扩展名、是否含生成物与测试的同一口径计数，结果明显不接近 13,000，则转贴说法不成立。

### 3. 《Super-agent 设计探索》长文及发布方

- **判：文章存在、题名可交叉核实；DeepSeek Harness 团队发布有二手转载支持，原始官方发布页本轮未验。**
- 搜索索引列出题名《Super-agent 设计探索：迈向更自主的 Agent 系统》及 Bilibili 专栏页面 `https://www.bilibili.com/opus/1265361021143351318`。该页转载摘要说明：「本文的部分设计已在 dsh-superagent-prototype 中实现。该插件只是一种为了验证技术路线而提供的原型，并非 DeepSeek 的正式产品。」并列作者／致谢为 Yujia Qiao 与 DeepSeek Harness 团队。该页面非 DeepSeek 官方域，故只证明转载内容存在，不当作原始发布方的独立证明。
- 可交叉查验的原文出处线索：DeepSeekHarness X 帖子 `https://x.com/DeepSeekHarness/status/2116857257245987236`（搜索结果列出）；X 页面未直接打开。
- **证伪句**：若上述原文链接实际指向另一篇文章，或作者／发布主体与转载摘要不符，则题名／归属需撤回重核。

### 4. README「绝大部分由 AI 写」是否确有其文

- **判：符合（GitHub 搜索索引中的 README 原文）；不是本轮直接打开 README。**
- 源：GitHub README 搜索结果及 raw README 搜索摘要 `https://raw.githubusercontent.com/deepseek-ai/dsh-superagent-prototype/main/README.md`，本轮 2026-11-03 14:5x。逐字原文：
  > “This code grew out of our team's day-to-day development work, with much of the engineering done by coding agents.”
- 同一 README 摘要还写：
  > “Research prototype for reference only, not an official DeepSeek product.”
  > “Treat it as research code, not production-ready software.”
  > “Some designs discussed in the article are directions for future development and are not implemented in this prototype.”
- 转贴「绝大部分是 AI 自己写的」是较宽泛的中文转述；原句精确含义是「大量工程工作由编码代理完成」，不是逐字的「绝大部分代码」。
- **证伪句**：若原始 README 不含该英文句，或其限定语将“much of the engineering”改成了别的主体／范围，则该摘录失效；对「绝大部分代码」这一更强说法，若原句仅为 much of the engineering，该说法本身即不成立。

### 5. 与我们 DSH 的关系

- **判：符合（仓库定位可从 README 搜索索引核到；不是同一项目）。**
- README 摘要原文称它是 “a proactive coding agent for one GitHub repository, packaged as a bundle for DeepSeek Harness”；也说明公开版“not identical to our internal version”，部分设计未在原型实现。即它是挂在 DeepSeek Harness（DSH）上的单仓库编码 Agent 原型，不等于 DeepSeek Harness 本体，也不是本项目止观AI的 DSH 协调窗。
- **证伪句**：若 README/package 元数据表明该仓库是 Harness 核心本体而非其 bundle，或与 DeepSeek Harness 无关，则上述关系结论不成立。

## 三、五块机制及它对我们具体解决／未解决什么

### 原型与文章能确认的机制

- 原型范围：面向**一个 GitHub 仓库**；监听 GitHub，可选接 Feishu；被允许的人提出请求后创建 work item，在独立 agent session 和目录中执行，结果回原讨论串；只在被请求或团队规则允许时行动。来源为 GitHub README 搜索摘要，属于公开文本索引，不是代码执行验证。
- 文章描述的系统方向：Router／Worker 双层、事件驱动、异步多信道、存算分离、外部 Watchdog。该列表由转载文章摘要给出；README 明说文章中的部分设计尚未在原型中实现，所以不能把架构全貌等同于仓库已具备功能。
- 风险边界：README 明确称非正式产品、非生产就绪、可能有 bug，要求使用者审查和适配；公开版与内部版及文章实现不同。

### 对止观AI的意义

**能对准的具体问题**：止观AI中环的需求归类、任务状态、执行与验收衔接仍有人工拼接；单任务运行轨迹与触发去重是既有研究稿列出的缺口。Super-agent 值得借的是把“事件→可追踪任务→隔离执行→回原处交付”的机制作为一条可研究的路线，不是换掉现有模型或治理体系。

**它没解决的**：它是单 GitHub 仓库的主动编码原型，不覆盖脑电真机与真实数据、VR 体验、12.8 营运营、社区复刻闭环，也不替本项目建立六客户端共同任务真值、法师裁定／验收、禁写边界和审计归因。其宣传／文章中的持续运行或性能数字不证明在止观AI环境有效；公开原型自己也提示非生产就绪。

**与既有数字员工研究三格对照**（基准 `20261029_数字员工与内中外循环对照研究_v1.md:30-50,95-115,160-173`）：

| 格 | 结论 | 证据与限度 |
|---|---|---|
| 新增 | 提供一个具体的单仓库编码原型作为阅读对象：授权来源、work item、独立会话／目录、回原讨论串；可以把既有稿中的「触发＋任务板＋交接＋长任务」从概念对照推进为逐模块核源码的研究候选 | 目前只按 README 搜索摘要与二手文章核实，尚未读代码，不能说已验证其安全性或完整实现 |
| 重复 | Router/Worker 角色分立、任务显态、分段交接、权限闸、失败恢复／运行轨迹，均已在既有研究稿列为建议；本项目已有 TASK ID／六态登记、协调—执行—判读分工、独立复验和授权边界 | 项目已有机制仍有“多处真值”和单任务轨迹缺口，重复不代表已完全落地 |
| 冲突 | 若照搬“主动监听＋自动分派/执行/回帖或 PR”，会与本项目四件须字、对外发送／共享台账写入须审批、一个文件一个写者、判定权归法师等红线冲突；编码 Agent 的并行 worktree 也不能自动免除提交身份、共享工作树和他窗件归属核对 | 原型的具体授权／执行实现还未逐文件审，故这是**条件性冲突分析**，不是断言原型已越权 |

### 回照四个已踩坑

| 坑 | 若借鉴该原型时的同类风险 | 本项目对应防线 |
|---|---|---|
| 074 执行方定错 | 起草者因手头有工具就自认执行方；“Router 派给 Worker”也不能替代先定承接责任窗 | 判语 032：执行归承接线；任务登记逐项写责任位 |
| 076 件内署名≠提交归因 | Worker 文书写了身份，git author/committer、PR 操作者仍可能是服务账号或共用身份 | 提交层核 author/committer/%B；PR 与提交逐层归因，不以文内署名代替 |
| 077 自测 PASS≠约束成立 | 原型测试覆盖自身设计路径，不证明权限、隔离、回滚等性质在本机部署成立 | 每个验收项写外部可观测证据和证伪句；复核者独立造探针 |
| 080 远端动了≠某窗推了 | 自动 Router/Worker 或后台任务可能提交／推送；远端前进不能证明由哪窗、哪 worker 操作 | 以时刻、进程、提交/推送日志归因；远端状态不作行为证据 |

## 四、可落地性三档

### 现在就能借（无需接入新执行器）

1. **任务入口统一关联**：只在任务登记/来函里加一个“外部触发来源＋原线程/仓库链接”记录约定；约 0.5 天；验收：抽 10 条新任务，每条均能从 TASK ID 回到原始触发材料，缺一即不成立。注意任务登记由协调位维护，执行位不直接改其真值文件。
2. **隔离执行回件格式**：在本窗自己的交付函里试行“输入摘要／独立执行目录或会话／产物／复核者／失败与恢复点”五项；约 0.5 天；验收：下一件长任务中断后，接手者只凭回件能恢复到最后一个可复核步骤；若还须问执行者关键状态，则不成立。
3. **安静不等于成功**：给长任务增加显式终态（运行／待人／失败／已交待验）和最近活动时刻；约 0.5 天；验收：模拟中断和无事件两种状态，外部观察者能区分“无事可做”与“执行失联”；分不出即不成立。

### 有条件才能借

- **接 GitHub／飞书事件并自动开任务、并行编码**：依赖法师逐项授权出网、凭据与权限白名单、明确单仓库范围、可隔离 worktree、提交身份和外发规则、独立监督/监管、回滚与事故停止手段；卡在当前授权边界和中枢任务真值/单任务运行记录尚未完全统一。现有研究稿 §八明确触发器与 connector 先限「信箱来函读取＋盘上件读写」，IM／日程／hook／API／外发默认关闭；不能因原型开源而自动扩权。
- **借其性能结论作本项目收益预测**：依赖原始论文、可复现负载、任务定义与质量指标；现有搜索到的数字属二手转述且为合成负载，未测真实代码质量，不能作为本项目预算或 KPI。

### 暂不适用

- **直接安装公开原型到止观AI并常驻运行**：README 自述研究原型、非生产就绪、公开版与内部/文章实现不同；本任务只授权只读调研，未授权 clone、依赖安装、运行或接 GitHub/飞书。
- **把 Router/Worker 作为新的裁定者或自动提交者**：与判定权归法师、共享写入须审批、一个文件一个写者、提交归因必须可核等原则冲突；该冲突不能靠 prompt 解决。
- **拿它替代全项目中枢**：公开范围是一个 GitHub 仓库的编码流程，不是六客户端、四主线、内外环治理系统。

## 五、外部证据与取数时刻

以下链接均为本轮 **2026-11-03 14:5x（本机日期读数 14:53:37）** 检索到的公开搜索结果或页面；GitHub 页面/README 直取失败的明示为搜索索引证据。

| 来源 | 可核原文／摘录 | 用途与证据强度 |
|---|---|---|
| GitHub 仓库 `https://github.com/deepseek-ai/dsh-superagent-prototype` | 搜索索引标题指向该仓库；README 摘要含 “Research prototype for reference only, not an official DeepSeek product.”、“This code grew out of our team's day-to-day development work, with much of the engineering done by coding agents.” | 官方仓库文本的搜索索引摘录；页面本轮 WebFetch 失败，故未直接读取 |
| README raw `https://raw.githubusercontent.com/deepseek-ai/dsh-superagent-prototype/main/README.md` | 搜索索引还含 “Treat it as research code, not production-ready software.”；“Some designs discussed in the article are directions for future development and are not implemented in this prototype.” | 同上，非本轮直接读取 |
| 原文转载页 `https://www.bilibili.com/opus/1265361021143351318` | 摘录：“本文的部分设计已在 dsh-superagent-prototype 中实现。该插件只是一种为了验证技术路线而提供的原型，并非 DeepSeek 的正式产品。”；列 Yujia Qiao 与 Harness 团队致谢 | 转载页面摘要；非 DeepSeek 官方原始发布面，原始页面 WebFetch 只返回验证码，故归属仍是二手证据 |
| X 发布线索 `https://x.com/DeepSeekHarness/status/2116857257245987236` | 搜索结果将其列作文章《Exploring Super-agent Design: Towards a More Autonomous Agent System》的发布链接 | X 页面本轮未直接读取；只能作原始出处线索 |
| GitHub 搜索结果 | README 描述其为 “a proactive coding agent for one GitHub repository… packaged as a bundle for DeepSeek Harness”；监听 GitHub、可选 Feishu | 仓库定位；搜索索引摘录 |
| 二手技术拆解 `https://m.blog.csdn.net/gitblog_00269/article/details/169748351` | 称约 14k 行 TS；称首提交时间 2026-10-31 20:05:39 +0800 | 二手线索，无法替代本轮固定 commit 统计；仓库创建时间与行数均仍未验 |
| 项目自身研究稿 | `20261029_数字员工与内中外循环对照研究_v1.md:95-115`（强项/缺口）；`:160-173`（能/须审批/不能） | 项目内基线，文件行号可本地复核 |

### 逐条证伪句（汇总）

- 仓库：目标 GitHub 路径不存在或改名即推翻。
- 行数：固定 commit 与固定文件筛选规则复算不接近 13,000 即推翻转贴数字。
- 长文：原始发布页题名/作者/发布时间不匹配即撤回对应结论。
- AI 编写比例：README 不含所引英文句即推翻；若只写 “much of the engineering”，就不能改述成“绝大部分代码”。
- DSH 关系：官方 README/package 元数据若显示它不是 Harness bundle 而是 Harness 核心，当前关系判断即撤回。
- 对本项目的收益：若一项借鉴不能指出现有具体缺口、责任位和外部可观测验收，则不算“解决了我们的问题”。

## 六、四值与失败面

- 起止：2026-11-03 14:53:37—14:59:27（本机 `date` 两次现取）。
- 退网码：不适用（公开网页搜索/读取；未 clone、未执行命令访问远端）。
- 摘录：见 §二与§五；README 英文保留原文，长文中文摘录标为转载。
- 出网级别：L3_EGRESS·只读公开资料；只发起公开网页搜索/读取，无上传项目内容。

**失败面／未验项**：GitHub 页面与 raw README 直接抓取失败；GitHub API 元数据未取得；TypeScript 行数未独立计数；仓库 `created_at` 未验；DeepSeek 官方长文原始页未直取，作者/发布方依据搜索索引和转载，不作一手确认；未读仓库源码，故不评价代码实现质量、测试覆盖或实际权限强度；“绝大部分代码由 AI 写”是比 README 原句更强的转述，不成立为已核事实。

**边界自报**：未 clone／下载依赖／运行代码／fork／star／提 issue；未写规约、台账或任务登记；未动 `vr_gates/`、骨架件及他窗件；未 push。交付后候 W3 复核。
