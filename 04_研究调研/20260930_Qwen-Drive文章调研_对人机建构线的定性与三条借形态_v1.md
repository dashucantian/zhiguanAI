# Qwen-Drive-1.0 文章调研：对人机建构方法论线的定性与三条借形态（2026-09-30 · v1.1 已试跑收口）

> 性质：调研存档，只读结论、不装程序、不引数据、不并码。
> 缘起：法师 09-30 派单，W3·人机建构方法论新开窗口办理（原文仅一条链接，无附加口径）。
> **v1.1（10-01 追记）**：法师二次指令——"3D 感知形成反馈循环与我们 VR 脑电闭环接近；如真实开源可下载、可测试、多方了解"。据此完成下载（13.8GB 全量）与本机 CPU 试跑（VQA＋规划两环实测通过），见 §七、§八；§2.2/§2.3 两处结论随之订正。
> 源件：`https://mp.weixin.qq.com/s/fnIP66KISsjk0wubZmp2Ng`
> 前件：`20260930_Muse三Watch项即时盘点_v1.md`（Watch §三"国内跟进者"）、`20260924_四方向横向调研_人机建构相关生态盘点_v1.md`（三借三不借口径）、`20260924_个人人机建构方法论_一页纸_v1_定稿.md`（v1.1 对照基线）。
> 判据沿用：单源不采信（一页纸 §五红线第3条）；〔已校〕＝一手源直取，〔待校〕＝未取到一手源，〔查无〕＝检索无果。

---

## 一、文章本体与源级定性

| 项 | 值 |
|---|---|
| 标题 | 阿里开源 Qwen-Drive-1.0-4B：把 3D 感知、VQA 与轨迹规划塞进一个 4B 多模态模型，迈向自动驾驶视觉。 |
| 公众号 | AIGC Studio |
| 发布时间 | 2026年9月27日 23:46 |
| 正文量 | 约 3101 字（浏览器实取，非搜索摘要） |
| **源级** | **自媒体二手源**。首尾均为导流（关注名片／知识星球二维码／小助手 AIGC_Tech），非阿里官方口径 |

**定性一句话：这是一篇自动驾驶垂直模型的技术解读稿，与我方脑电线、人机建构线均无产品级交集；其价值不在"赛道"，在"配方"——它把我方模板包 v1.1 已在做的那套架构选择，用一个 4B 模型的实测跑了一遍。**

## 二、事实核实（一手源逐项）

### 2.1 〔已校〕论文真实存在，且文章架构描述与摘要逐条相符

一手源：arXiv 摘要页（浏览器直取，非二手转述）。

- **arXiv:2609.00111 (cs.CV)**，标题 *Qwen-Drive-1.0: An Initial Step towards a Vision-Language Foundation Model for Autonomous Driving*
- **提交日 2026-08-31**（v1，17:59:54 UTC，31,142 KB），投稿人 Zhibo Yang
- **作者 16 人**：Xin Zhou、Zongchuang Zhao、Zhibo Yang、Mingsheng Li、Humen Zhong、Shuai Bai、Du Chu、Ruizhe Chen、Zhaohai Li、Jun Tang、Qiuyue Wang、Mingkun Yang、Jiazhao Zhang、**Dayiheng Liu**、**Dingkang Liang**、**Xiang Bai**
  - → 文章称"阿里 Qwen 团队与华中科技大学"**成立**：Dayiheng Liu／Shuai Bai 系 Qwen 侧，Dingkang Liang／Xiang Bai 系华中科大侧（Xiang Bai 为 HUST 白翔团队常用署名）。

摘要原话四条，对文章核心声称的支撑关系：

| 文章声称 | 摘要原话（一手） | 核校结论 |
|---|---|---|
| 保持预训练 VLM 架构无改动 | "retains the architecture of the pretrained vision-language model (VLM)" | **相符** |
| BEV 头＝显式可检视 3D 探针 | "serves as a **probe** of the 3D information accessible from the shared representations and provides an **explicit, inspectable interface** to 3D scene structure" | **相符**（"探针"与"可检视接口"均为论文自述用词，非文章加工） |
| 规划专家基于流匹配生成轨迹 | "A Planning Expert conditions on shared VLM representations to generate future ego trajectories" | **部分相符**：摘要未提"流匹配"，该细节〔待校〕 |
| 分阶段训练保通用能力 | "A staged training recipe combines driving supervision with general-purpose vision-language data … while **helping preserve** broad visual understanding and instruction-following capabilities" | **相符但强度有差**：论文用 "helping preserve"／"largely preserving"（留有余地），文章写"基本保留""大体未损"（口径相近）；文章另处写"**显著提升**了通用 VLM 的自动驾驶能力"则属加码 |

### 2.2 〔v1.1 订正〕"首个"系官方声称，文章丢了限定语

文章两处称 Qwen-Drive-1.0 是"**首个**在预训练阶段统一 3D 感知与视觉问答，并进一步扩展到运动规划的自动驾驶视觉-语言基础模型"。

v1 时因未取到全文，判"摘要无 first 表述、系自媒体加码"——**该判断此轮被证伪，主动撤**：官方 GitHub 仓库 README 原话即 "Qwen-Drive-1.0 **is the first** vision-language foundation model for autonomous driving that unifies 3D perception and visual question answering at the pretraining stage and further extends to motion planning"。

→ 订正后的判定："首个"是**官方声称**（单源，阿里自述）；文章转述基本忠实，但把官方限定语（"在预训练阶段统一 3D 感知与 VQA 的那类模型中"）弄丢了，扩大了覆盖面。引用时须带全限定语并标〔官方自称·单源〕。

### 2.3 〔v1.1 全部落实〕原四项待校，此轮三项已校实、一项不再承重

| 项 | v1 状态 | v1.1 状态 |
|---|---|---|
| 基座型号 Qwen3.5-4B | 〔待校〕 | **〔已校〕** ModelScope README frontmatter `base_model: Qwen/Qwen3.5-4B`，且正文确认"natively multimodal Qwen3.5-4B serves as the shared VLM" |
| 许可证 Apache-2.0 | 〔待校〕 | **〔已校〕** ModelScope API 元数据字段 `apache-2.0`＋README frontmatter＋GitHub API `license.spdx_id=Apache-2.0`，三源一致 |
| benchmark 数字 | 〔待校〕 | 仍未校（不承重，见下行）；官方 cookbook 明示各榜完整复现需数据集官方验证集与 NAVSIM/Waymo 度量包 |
| 权重页 ModelScope | 〔待校〕 | **〔已校〕** 存在且全量下载成功（13,779,473,722B 与元数据 StorageSize 一致） |

### 2.4 检索环境留痕（供后窗复用）

- WebFetch 直取微信链接：**被"环境异常"安全校验拦截**，只回校验页前端源码 → 微信公众号正文一律改走 browser-use 真浏览器＋`evaluate_script` 取 `#activity-name`／`#js_name`／`#publish_time`／`#js_content`，一次成功。
- 本机 `curl` 出外网：**exit 56（连接被断）**，不可用于探活。
- `github.com`：ERR_CONNECTION_RESET；`modelscope.cn`：超时；`arxiv.org/abs/`：**通**；`arxiv.org/html/`：通但正文空。

## 三、定性：与我方三线的关系

### 3.1 脑电线（W1／NeuraDock／Muse）——**无关**

无 EEG、无 sEMG、无任何生理信号入口；输入侧是车载相机。与 `project-neuradock-data-access` 两扇门、Muse Watch §一神经输入 SDK 均不同层。**不登记、不观察。**

### 3.2 人机建构方法论线——**非竞品、非新 Watch 项**

- 它是**垂直领域模型**，不是个人智能体，不含任何"人机协作规约／状态仲裁／验收权"面。
- 不占我方"规约与方法论位"，也不占 QwenPaw 的"工具位"。
- → **"规约层首个公开模板＝全网空白位"判定本期未被触碰**（该判定本身仍依 09-24 四方向调研，本文无关）。
- **三借三不借照旧**：本件属"**借形态**"（只读架构配方），不属借生态／借渠道，更不属"接管"。

### 3.3 Watch 线——**建议加一行旁证，不改判语**

阿里 Qwen 团队在 Watch §三已坐实为"国内跟进者"（QwenPaw，个人数字分身框架）。本次是其**同组织在另一垂直方向的又一次开源动作**（08-31 论文／09-27 媒体扩散）。

- 可作**动作密度旁证**：同一团队一个月内被观察到两条不同方向的开源线（个人分身框架＋驾驶 VLM），说明其"本地优先／开源可自托管"是**组织级路线**而非单点试水。
- **三判语无一变更**，不接不装不引数据照旧。
- 是否正式写入 Watch 台账，候师裁（见 §五.1）。

## 四、核心收获：三条借形态（架构配方与我方方法论同构）

这是本调研对本窗真正的价值面。论文解的问题——**如何给一个通用底座注入领域能力，而不牺牲通用性、不把系统变成黑盒**——与我方模板包和输出分层正在解的问题，是同一道题的不同层。

### 借形态一：**外挂不改主干** ← → 模板包"母包一字未动＋外挂两包"

| 论文侧 | 我方侧（v1.1 实证） |
|---|---|
| 保留预训练 VLM 架构无改动，LLM Decoder 不动 | `07_模板包\` 六包空壳（10~60）**一字未动** |
| 外挂 BEV 感知头＋规划专家两个外部模块 | 外挂 `00_居士白话包`＋`01_入门30分钟包` |
| 同一套权重既承接通用 VQA 又承接驾驶 VQA | 同一母包既走"自建者空壳路线"又走"居士白话路线" |

**可借之处：** 论文用 4B 规模的实测给"外挂优于改主干"提供了一条跨域工程证据——**领域适配应当做成可插拔外挂，主干保持稳定，通用能力才不会被吃掉**。我方 09-30 升 v1.1 时正是这样做的（两条起步路线分界，六包本体不动），但当时依据是 ZG-073 三轮 AI 干跑实测（内部证据）。今后可补一条外部同构佐证。

**边界：** 这是**类比背书，不是技术依据**。不可写成"阿里证明了我们的做法对"——两者问题域不同，只能说"同一架构选择在另一域亦被采用并奏效"。

### 借形态二：**分阶段配方缓解灾难性遗忘** ← → 改母本的程序护栏

| 论文侧 | 我方侧 |
|---|---|
| 统一跨数据集标签，映射到共享标签空间 | **单一正源**（内嵌指令单正源归 `00`，01 内副本已删） |
| 重标驾驶 VQA 回答，按语义一致性过滤样本 | 外发件**零内部坐标**＋脱敏复扫 |
| 分阶段训练，避免新能力覆盖旧能力 | 改母本须走 **v1.2 修订程序**（AI 不自行改定义措辞）；**脱敏复扫在前、打包在后** |
| 目标：acquire driving-specific competence while preserving broad capability | 目标：加居士白话不伤自建者空壳路线 |

**可借之处：** "灾难性遗忘"在方法论层的同构物是**改一处伤全局**。论文的解法结构（统一标签空间→重标→过滤→分阶段）与我方护栏结构（单一正源→零内部坐标→脱敏复扫→修订程序）**逐项对得上**。

**直接可用的教训：** 09-30 本窗曾把顺序颠倒一次（首包打在脱敏复扫之前，已原地重打并留痕 KZ-0930-W3a）。论文侧的对应纪律是"分阶段"——**阶段之间有检查点，不是一锅煮**。这为"是否把『脱敏复扫在前、打包在后』升为规约条目"（原已候裁）添了一条外部同构论据。

### 借形态三：**可检视性做成旁路探针，不做成主干负担** ← → 输出分层（对本窗最硬的一条）

论文原话（一手摘要）：BEV 头 "serves as a **probe** … and provides an **explicit, inspectable interface** to 3D scene structure"，而文章补充其用意是"方便调试和可视化，**而不只是黑盒输出**"。

关键在于它的**架构位置**：可检视接口是**外挂旁路**，主干照常输出轨迹；需要核查时读探针，不需要时探针不拖累主干。

**这正是本窗 09-30 起试跑的「输出分层」所要解的同一道题。** 法师指出的痛点是"各窗输出实为审计文体——审计要全、人读要省，两层未分离"（`feedback-output-layering`）。论文的解法结构给出一个干净的架构表述：

> **可审计性不应是主干输出的属性，而应是旁路探针的属性。**
> 主干＝首屏三行（结论／位置／请求），给人读；
> 探针＝证据区下沉（命令／闸门／编号链／diff／逐条对账），要核时读，一个字节不删。

两者**并存不互损**——正如 BEV 头存在却不伤通用 VQA 性能。这比"精简输出"的提法更准确：不是删证据，是**把证据移到旁路**。

**→ 建议作为 10-03 复看单的一条候选论据**（不是候选规条本身；规条仍须法师裁定后立）。

## 五、提请裁定（三条，AI 不自写规则）

1. **Watch 台账是否加一行旁证？** 拟在 `20260930_Muse三Watch项即时盘点_v1.md` §三"国内跟进者"下加一行：阿里 Qwen 团队另有 Qwen-Drive-1.0（arXiv:2609.00111，08-31），同组织多方向开源，**判语不变**。
   - 甲：加，作为动作密度旁证。乙：不加，垂直驾驶模型与个人智能体不同赛道，加进去反而稀释 Watch 焦点。
   - **AI 倾向乙**（Watch 项应按"是否触碰我方判语"筛，本件不触碰）；候师裁。

2. **借形态三是否入 10-03 复看单？** 拟把"可审计性做成旁路探针而非主干属性"作为**论据**（附 arXiv:2609.00111 摘要原话指针）写入复看单的候选规条论证段，不改已试跑的四条拟稿。
   - **AI 倾向：入。** 理由：复看单要求"每条附证据指针"，此条提供了内部先例之外的一个外部同构指针。

3. **借形态一／二是否补入一页纸或母包 README？**
   - 一页纸 v1.1 已定稿（D-0927-W3a），再订须走 v1.2 程序；母包 README 立"两条起步路线"分界处可加一句外部同构脚注。
   - **AI 倾向：暂不动。** 理由：一页纸 §五红线要求"对外权威声称须独立核校"，而本件的基座／许可／跑分四项仍〔待校〕；类比背书不足以进定稿正文。**建议仅留在本调研件内备查**，待日后若有多例同构再议。

## 七、下载与试跑实录（10-01 凌晨，法师"可下载、可测试、多方了解"指令的直接执行）

### 7.1 环境账（本机）

| 项 | 值 | 影响 |
|---|---|---|
| GPU | AMD Radeon 8060S 核显，**无 N 卡** | 感知端锁死（见 7.4） |
| torch / transformers | 2.14.0+cpu ／ 5.17.0（官方钉版 2.8.0／5.14.1，Python 3.12 一致） | 偏差小，实测兼容 |
| 内存／磁盘 | 31.6GB ／ 250G 余 | 够装 4B bf16（≈9GB） |

### 7.2 下载（全部字节级验收）

ModelScope 直链 `resolve/master`（curl 断点续传，实测约 6MB/s），13.8GB 全量：
`model.safetensors` 9,078,630,512B＋`perception/` 500,368,384B＋`planner-sft/` 2,079,739,550B＋`planner-rl/` 2,079,739,550B＋配置词表——**四件 safetensors 与官方 API 元数据逐字节相等**；代码仓经 codeload zip 拉取（链路不稳，重试 2 次成）。落 `_research_src\qwen-drive\`（gitignore 区）。

> **清理追记（10-01，法师裁"只删大权重"）**：13.8GB 四件 safetensors 已删，仅留代码仓＋demo 数据＋试跑存证（`predictions_direct.jsonl`）约 65MB——理由：权重照本节命令约 40 分钟可全量复原，试跑存证与两坑账现场不可复原。日后若上 N 卡复测感知环或跑分，复原本节命令即可。

### 7.3 试跑结果（CPU，全部用仓库自带 demo 数据，零外部素材）

| 环 | 命令要点 | 结果 |
|---|---|---|
| **VQA（理解环）** | `run_vqa.py --device cpu --attn-implementation sdpa`（真驾驶帧 CAM_FRONT，问红绿灯状态） | **✅ 通过**。723 个权重张量载入，答 "The traffic light ahead is green." |
| **规划（决策环）** | `run_planning.py --mode direct_planning --planner planner-sft --num-workers 0 --device cpu` | **✅ 通过**。50.7s/场景，输出 2 条 50 点×3 维轨迹（平滑前行 x:0→6.7m、微侧偏）＋真值对照＋偏好轨迹评分（8.0/4.0/6.0）——**输出件本身即审计友好结构**（token／trajectories／gt／preference_scores 分字段可查） |
| 推理式规划 | 未跑（planner-rl 需先长文本推理，CPU 数十分钟级） | 直推已足证通路，留待 N 卡环境 |
| **感知（感知环）** | — | **❌ 本机锁死**：BEV 头依赖自定义 CUDA 算子（ms_deform_attn／voxel_pool 的 .cu 文件），无 N 卡无法编译 |

**闭环回应法师的"反馈循环同构"**：模型单帧内是"感知→理解→规划"**开环前向**，"闭环"发生在仿真评测侧；我方是真人生理闭环。可参考的硬核在：①显式可检视探针（BEV 头）②外挂模块即插即用（三个 safetensors 分件存）③输出件天生带审计字段。

### 7.4 踩坑三条（供后窗复用，已可入坑账候裁）

1. **demo.py 硬编码 `attn_implementation="flash_attention_2"`**（无开关）——CPU 环境必炸；走 `run_vqa.py`／`run_planning.py`（二者带 `--attn-implementation sdpa`）绕过。
2. **Windows spawn 无法 pickle lambda**（`_make_resolver` 内嵌 lambda）——多进程 DataLoader 起不来；`--num-workers 0` 绕过。
3. **依赖缺口两个**：torchvision（CPU 版 `--index-url download.pytorch.org/whl/cpu`）＋pyarrow——官方 requirements 均列了，属本机环境自补。
4. **通路坑**（v1 已记，此轮续证）：codeload zip 大件传输不稳（curl 18/28，重试可过）；浏览器直连 github/modelscope 挂，但 **curl 到 api.github.com／codeload／modelscope.cn 反而通**——"浏览器被拦"≠"本机不可达"，先 curl 探活再下结论。

## 八、结论（v1.1 更新）

1. 文章主体**真实且已本机实证**：官方开源（Apache-2.0 三源一致）、权重全量字节级验收、CPU 上 VQA＋规划两环实测跑通；"首个"为官方声称带限定语，文章丢了限定语。
2. 对我方三线定性不变：非竞品、非新 Watch 项、借形态；"规约层全网空白位"判定未被触碰。
3. **借形态三条款升级为"已实证"**：本机试跑亲眼验证了"主干不动＋外挂模块＋旁路探针"这条架构在 4B 规模真实可运行——尤其**输出件分字段自带审计结构**，是"证据区下沉"论据的实物样本。
4. 复现边界如实申报：感知环需 N 卡；推理式规划与 benchmark 复现需 N 卡＋官方数据集；**本机验证仅覆盖"真实、开源、能跑、输出可检视"四点，不构成性能复现**。

---

*方法留痕（v1.1 续记）：此轮关键反转一条——v1 判"本机 curl 出网断"，实为**github 主站被断而 api.github.com／codeload／modelscope.cn 均通**；"浏览器被拦"≠"本机不可达"，先 curl 探活再下结论。全程检索/下载仅公开件（微信文章页、arXiv、GitHub 公开仓、ModelScope 公开权重），无项目内部数据出本机；经法师明示授权，本机新装 torchvision(CPU)／pyarrow 两依赖并下载公开权重 13.8GB 至 gitignore 区，未引任何外部数据入项目库。*

*成稿：W3·人机建构方法论窗（Qoder），2026-09-30；v1.1 试跑收口 2026-10-01。本件依 `.gitignore:199` `04_研究调研/` 豁免惯例落盘存档不入库；如需入库另候法师裁。*
