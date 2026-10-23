# 脑电主线 × NeuraDock 可对接面差距表 v1（T1＋T2）

出具：2026-10-23 12:2x（本机 `Get-Date` 现取；各读数带出处行，无出处者标"未验"）｜盘上复核：HEAD `bbcaeff`（10-22 02:14）、`@{u}..HEAD`＝0、此后无新提交｜窗：`DSH·24e5b510`（W1 工程线接续窗，取证甲级，未领号）
依据（法师本轮三字，落在本窗 2026-10-23 12:1x 这一拍，逐字）：
①「要以"复现反馈/案例互换"的形式与 NeuraDock 建立正式通道」
②「课程仓 §3 非商业证下，我们的复现件能进自家仓库、能对外，因为我们正是非商业机构，非商业目的」
③「NeuraDock 平台既是"参考实现"同时是"合作方平台"」
性质：**盘点件**（一张表＋九条借鉴物），非裁定、非方案。方法源＝NeuraDock 团队公开文《做脑电AI应用，别急着买硬件，先让 Agent 带你跑通一遍》（页面元数据 2026-10-22 06:06，按出处原样记）＋本方盘上资产。

## 一、十二个可对接面（我方有／对方有／差距／借鉴动作）

| # | 面 | 我方有（出处） | 对方有（出处） | 差距 | 借鉴动作（T3–T5 用） |
|---|---|---|---|---|---|
| 1 | 通道·采样率·单位 | 7 通道 `CP5 CP6 PO3 PO4 O1 Oz O2`、250 Hz（`muse2-repo\muse2-master\neuradock_receiver.py:30-31`） | 同 7 通道／250 Hz，另给 `sample_axis`、`amplitude_unit:"uV"`、`line_frequency_hz:50`、总包 8 通道只用 7（`05_产品与开发\NeuraDock\参考仓库\eeg-workstation-agent\configs\neuradock-v1.json:5-19`） | **半有**：数值同，**设备剖面件没有** | 建我方 `configs\neuradock-v1.json`，字段照其形制、值取我方实测 |
| 2 | 传输·协议 | TCP `127.0.0.1:9600`、transport auto、设备相对秒 `t_rel` 防积压突发失真（`neuradock_receiver.py:13`／`:54`／`:293`） | 协议文档＋`start` 启动命令、每蓝牙包 5 样本、版本差异（同 profile `:12-19`；`docs\data-protocol.md`） | **半有**：有实现、缺"协议文档化＋版本差异" | 把我们的 TCP 口径写成对等协议文档，差异列一栏 |
| 3 | 录制·落盘 | `.npz`＋`meta.signal_chain`；⚠ NeuraDock 落盘链标注仍可能套 Muse 常量＝**未验**（旧账见 `20260919_数据全链路整体盘查…v1.md:454/458`） | `DATASET.md`／`RELEASE_MANIFEST.md`／`docs\release-checklist.md` | **半有**：形制可借，我方标注待核 | 先核 `signal_chain` 现势，再定落盘字段表 |
| 4 | 质量·质检 | `qc_pipeline.py`：阈值版本 `20261013`（`:38`）、测不出写 `unknown` 不写 `ok`（`:20`）、同 npz 两算逐字节一致（`:21`）、`clean_ratio` 由 npz 直算脱离 report.html（`:14`）；"QC 五闸"为转述（`20261004_实践驾驶舱整体架构复盘与迭代规划_方案稿v1.md:12`） | 六项阈值（线噪 10／EMG 20／超幅 100 µV／坏道比 0.4／邻道相关 0.15／每秒离群 2）＋`retention_rate`、`bad_channel_candidates`、`spatial_quality`（profile `:20-27`；`context\result-fields.md:13-22`） | **有，但口径不同**（我方 clean_ratio＋弃权；对方 retention_rate＋阈值组） | 出一张"指标映射表"：我方指标 ↔ 对方字段，逐条写等价性（等／近似／不等） |
| 5 | 特征·Alpha | 相对功率／IAF（`qc_pipeline.py:180` `compute_iaf`） | `posterior_log_alpha_power`、`alpha_suppression_from_baseline`、`alpha_peak_hz`（8–13）、不对称度（`result-fields.md:24-39`） | **半有**：定义可借（后部通道＋会话基线相对） | 借其"基线相对"定义，写进我方特征口径 |
| 6 | 指标 API | `/api/ndmetrics` SSE 旁证源＋`nd_hub` 扇出中转（`nd_routes.py:14-15`），`/api/nd/status` | Online Visual Load API：`visual_load_index`（0–100 相对）、`alpha_state`（initializing/weak/baseline/strong）、`quality` 三闸、`baseline.history_count`（`result-fields.md:72-81`） | **半有**：有通道、**字段语义与解释边界缺** | 借其字段名＋"每字段一句不得当"的写法 |
| 7 | Agent·知识层 | 坑档／判语／卡／登记分片／L1 各自成账（碎片，无单一入口） | 六维知识（设备／数据／质量／软件接口／使用上下文／案例证据）＋45 篇 K 资料＋21 页 Wiki，案例绑固定 commit（文章§一） | **真无** | 建我方索引，每条带编号·一句话·出处·适用面·失效条件 |
| 8 | 案例·证据 | `_research_src\neuradock-eeg-101\lesson01-04` 复现脚本＋`outputs\` | `context\cases\`（eyes-open／rest-task／signal-quality／visual-cog）＋固定 commit＋失败记录与待办（文章§二/§三） | **半有**：有实物、无"绑版本＋失败记录＋待办"案例卡 | 案例卡形制照抄，内容用我方真实跑过的四条 |
| 9 | 验收·闸 | 判据 9/10/13（执行式 `vr_gates\verify_mandala_stage.py:558-559`，10-16 已裁"以执行式为准"）＋交接四查＋提交前数核 | `docs\release-checklist.md`、`.github\workflows\ci.yml`、`SHA256SUMS.txt`；三步证据分层（维护文档／用户报告／工具核验，文章§二） | **半有**：判据在，**"证据三分"字段没有** | T3 核心：八段式交付＋三分字段 |
| 10 | 边界声明 | 判语 009（镜子非训练器）、011（结论可重算） | `context\scientific-boundaries.md`／`docs\scientific-boundaries.md`；`result-fields.md` 逐段"不得当 absolute cognitive load／attention／clinical"（`:38-39`／`:80-81`） | **有（同族）**，可互证 | 互证清单：两侧各引三句，查是否同义 |
| 11 | 许可·合规 | 判语 004（全开源立场）；厂商件 P15 禁入库（`待裁单_证据附页_20261013.md:27`）；课程仓 §3 非商业 | agent 仓 MIT（本地快照 `参考仓库\eeg-workstation-agent\LICENSE`）；课程仓自拟非商业证 | **已解**：法师②裁"我们非商业机构、非商业目的"⇒复现件可进库可对外 | 对外件加"非商业·研究教育用途"声明＋出处与版本 |
| 12 | 协作通道 | **无对外通道** | GitHub 主页／Discussions／Issues＋两固定 commit（SSVEP `0d35016…`、认知负荷 agent `5b3357ae…`）＋案例互换机制（文章§四） | **真无** | 法师①已准：出"复现反馈/案例互换"形制一案，对外稿候签 |

## 二、九条可借物（T2 清点，全部在本地 MIT 快照内，未新增出网）

1. `configs\neuradock-v1.json`（857 B）— 设备剖面形制：版本＋通道＋单位＋50 Hz＋TCP＋六项质量阈值。
2. `context\result-fields.md`（3,980 B）— **最有价值的一件**：每个指标字段一句定义＋一句"不得当什么"。
3. `context\scientific-boundaries.md`＋`docs\scientific-boundaries.md` — 声明层写法。
4. `docs\data-protocol.md`（785 B）— 协议层最短写法。
5. `docs\release-checklist.md`＋`.github\workflows\ci.yml` — 发布清单与 CI 闸形制。
6. `COMMANDS.md`（15,460 B）＋`Claude_code_SKILL.md`（18,584 B）— 命令八段式与技能包结构（对应文章"当前目标→目录→前置→命令→预期→完成检查→失败下一步→贴回物"）。
7. `context\cases\`（4 张案例卡）— 案例卡形制。
8. `SHA256SUMS.txt`＋`RELEASE_MANIFEST.md` — 锚件与发布清单（与我方 `.sha256`／`.filled.sha256` 体例可对齐）。
9. `context\workflows.md`（5,199 B）＋`docs\architecture.md`（2,790 B）— 流程与架构叙述。

## 三、三条法师字改变了什么（口径变更，记录在案）

- **①建正式通道**：T6 由"候裁"转"可办"。形制取**一案双轨**＝复现反馈为主（我们贴回：卡住的步骤／贴回的输出／走过的弯路）＋案例互换为辅；先出"我方给什么／拿什么／脱敏规则"三张单，**对外发出仍候你签**（对外是动作，不是判断）。
- **②非商业许可**：许可面由"红格"转"可办"。课程仓 §3 不再阻我方复现件入库与对外；**他人代码与资料仍按各自许可**（MIT 保留版权与出处、版本号），对外件加"非商业·研究教育用途"声明。P15 厂商件（含真人姓名与付款）**仍禁入库**——那是隐私面，不因非商业而开。
- **③双重定位**：知识索引每条须带标签 `ref`（参考实现，出处 commit/文件行）或 `partner`（合作方平台，接口/路线），**不许混写**；同一物既作参考又作接口时，写两行、不合并。

## 四、差距归并（下一步只按这个次序做）

1. **T3 验收形制**（面 9）：八段式交付＋"证据三分"字段——**投入最小、立刻可用**，且能直接改善我们每次交接与跑闸的记录。
2. **T4 知识索引**（面 7）：先 10–15 条，全部带 `ref`／`partner` 标签与出处。
3. **T5 四层验收台账**（面 1/4/5/6/8）：把"合成可验／回放可验／须真机"三档落到每层。
4. **T6 通道形制**（面 12）：三张单＋对外稿（候签）。
5. T7 许可清单随②简化；T8 节律挂既有四拍，不新增自动件。

## 五、不足与未验（本件自曝）

- 不足：② `docs\data-protocol.md`／`docs\release-checklist.md` 只读目录与同类件推断要点，**未逐字读全文**。
- 不足：③ 我方 `meta.signal_chain` 对 NeuraDock 是否仍套 Muse 常量＝**未验**（旧账在 `20260919…:454/458`，未现查复算）。
- 不足：④ "QC 五闸"是转述（出处 `20261004…方案稿v1.md:12`），本件未逐闸现点。
- 不足：⑨ 对方**在线**面（`neuradock.com/agent` 交互、45 K／21 Wiki 实际条目）未逐一核，仅据文章转述；本地 MIT 快照为 09-08 版，与文中固定 commit 可能不同版。
