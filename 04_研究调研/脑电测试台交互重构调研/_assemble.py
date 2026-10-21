import os, re, io, sys

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "20260926_国际EEG-BCI测试平台_流程组织与人机分工_调研报告_v1.md")

PARTS = [
    ("_partA_BCI平台.md", "Part A · BCI/EEG 实验平台（BCI2000 / OpenViBE / Timeflux / LSL / BCILAB / BciPy）"),
    ("_partB_实验呈现软件.md", "Part B · 实验呈现与编排软件（PsychoPy / OpenSesame / Presentation / jsPsych / Expyriment）"),
    ("_partC_分析侧质控.md", "Part C · 分析侧质控工具（MNE-Python / autoreject / MNE-ICALabel / EEGLAB / Brainstorm / PREP / EEG-qualities）"),
    ("_partD_商业采集软件.md", "Part D · 商业采集软件与引导式佩戴（BrainVision Recorder / g.tec / NeuroPype / iMotions / Curry 等）"),
    ("_partE_消费级设备引导.md", "Part E · 消费级设备佩戴与信号质量引导（Muse / Emotiv / OpenBCI / Neurosity / IDUN / BrainCo）"),
    ("_partF_自动化与闭环.md", "Part F · 自动化管线、闭环与自适应校准（Automagic / BeMoBIL / brainlife / BrainFlow / BciPy / Perdikis 2018 / Zanini 2018）"),
    ("_partG_临床标准与设备验证.md", "Part G · 临床标准与设备验证（ACNS / ASET / FASTER / 信号质量指标 / 设备对比研究）"),
    ("_H_跨案例提炼与启示.md", "Part H · 跨案例提炼 与 对「脑电设备性能测试台」的启示"),
]

HEADER = """# 国际脑电（EEG）/BCI 实验与设备测试平台的「流程组织方式」与「人机分工设计」调研

> **调研目的**：为「脑电设备性能测试台」（网页执行面板）的交互重构提供国际参考案例。
> **委托背景**：现有测试台用于验收脑电采集设备（受测：NeuraDock 7 通道 / 250Hz / 有线 TCP；Muse 4 通道 / 256Hz / 蓝牙），
> 测试项共 11 项（T1 睁闭眼 α 阻断、T2 静息噪声底、T3 耐受性、T4 工频噪声、T5 长时程稳定性、T6 原始数据流核验、
> T7 时钟与对齐、T8 采集→入库→质检端到端、T9 端到端延迟、T10 VR 同场共存、T11 双设备对照）。
> **现状痛点**：11 项是串行罗列的卡片清单，操作者要在 11 张卡之间自己判断"现在该干嘛"。
> **重构目标**：改为三种协作模式——**AI 引导 / 人配合**、**AI 测试 / 人跟随**、**AI 自测**，并整合流程。

---

## 关于本报告的可信度约定（请先读）

1. **本报告不编造。** 每个对象的每条结论均附可点击链接；凡本次未能取得可核实来源者，一律写明「**未证实／未找到**」，并常附「已尝试但失败的 URL」清单。宁可少写。
2. **区分证据强度**：部分条目注明「【官方】＝官方文档/源码原文明写」「【推断】＝调研者从页面结构推理」「（论文声称）＝仅取得摘要级信息」。请注意不要把「论文声称」当成官方文档事实。
3. **本轮检索环境异常，已在方法上留痕**：调研期间 `web_search` / `read_page` 的默认搜索引擎因无密钥额度耗尽（HTTP 429，退避窗口约 24 小时）全程不可用；Google / Bing / Brave / DuckDuckGo / Startpage / Mojeek 在本机网络下被墙或 403。因此取证改由以下通道完成：`web_fetch` 直抓官方文档与 PDF、GitHub `raw.githubusercontent.com` 与 `api.github.com`、Crossref / OpenAlex / Europe PMC / PubMed E-utilities API、以及部分厂商站点的 WordPress `wp-json` 接口。**这意味着本报告更依赖"已知官方 URL 直取"而非"搜索发现"，覆盖面上可能存在遗漏；若某对象你关心的细节未出现，请按「未证实」理解，而不是「不存在」。**
4. **分工**：本报告由 7 路并行调研 + 1 路综合归纳完成（Part A–G 为分工调研，Part H 为跨案例归纳与启示）。

---

## 覆盖对象总览

| Part | 覆盖对象数 | 对象 |
|---|---|---|
| A | 6 | BCI2000、OpenViBE、Timeflux、Lab Streaming Layer（LSL/LabRecorder/pylsl）、BCILAB、BciPy |
| B | 5 | PsychoPy、OpenSesame、Presentation（Neurobehavioral Systems）、jsPsych、Expyriment |
| C | 7 | MNE-Python（含 `annotate_*`）、autoreject、MNE-ICALabel、EEGLAB（history/clean_rawdata/ICLabel/Adjust）、Brainstorm、PREP pipeline、EEG-qualities |
| D | 7 | BrainVision Recorder、g.tec（g.Recorder/g.HIsys/g.HIamp/g.USBamp）、NeuroPype、iMotions、Compumedics/Curry（NeuroScan），＋附加对象 BioSemi ActiveTwo/ActiView、Wearable Sensing DSI-24/DSI-Streamer |
| E | 6 | Muse（Interaxon）、Emotiv、OpenBCI GUI、Neurosity Crown、IDUN Guardian、BrainCo（FocusEDU/FocusCalm） |
| F | 9 | Automagic、BeMoBIL Pipeline、brainlife.io / EEG-IP、BrainFlow、BciPy、MNE-LSL+Timeflux 闭环、Perdikis 2018（互学习）、Zanini 2018（黎曼迁移）、pylossless |
| G | 7 | ACNS Guideline 1/2 与重症连续 EEG 共识声明、ASET 技师能力标准、FASTER pipeline、EEG 信号质量指标（SQI：Radüntz 2018 / Witteveen 2020 / MELF 2026）、消费级设备验证对比研究（Sensors 2024 / Front Neurosci 2024）、设备验收与体模法（phantom head / Sci Rep 2026 三层框架）、自动质量门禁（Emotiv EQ gate） |
| H | — | 6 种流程组织范式 ＋ T1–T11 的机器/人分工建议 ＋ 三种协作模式的"零件清单" ＋ 5 组一手实证 |

> 说明：`EEG-qualities` 经四个包注册表入口与 Crossref/GitHub 检索，**未证实**其存在（详见 Part C 末节，含逐条尝试记录）。
> 三条工具性更正如实保留在正文中：① `arxiv.org/abs/1703.08019` 并非 Zanini 的论文（实为音频源分离论文）；② Expyriment 数据文件扩展名官方页面写的是 `.xpd`，`.hdd` 未证实；③ **ACNS 指南编号**——"Guideline 5 = 电极命名"是 2016 改版前的**旧编号**，现行 **Guideline 2 = 电极命名**、**Guideline 5 = 儿科 EEG**（ACNS 原文："Guideline 2 … was previously published as Guideline 5"）。
>
> **关于"电极阻抗应低于多少"这一常见说法**：本轮**未证实** ACNS Guideline 1 推荐 "5 kΩ"（该指南原文在付费墙后，且官网 PDF 文本层为 CID 字体无法解析）。可核实的权威口径是 **ACNS 重症连续 EEG 共识声明的 "electrode impedances less than 10,000 ohms are acceptable"（< 10 kΩ）**，且 ACNS 另提示 Guideline 1 修订后已允许"用非传统电极、以略高的阻抗记录合格信号"。真实实践中凝胶电极常控在 **<30–50 kΩ**、干电极 **<300–500 kΩ**——**相差一个数量级，绝不可套用同一门槛**。详见 Part G 与 Part H。

---

## 建议阅读顺序

- **只有 15 分钟** → 直接读 **Part H**（跨案例提炼 + 对 T1–T11 的分工建议）。
- **关心"别人怎么组织流程"** → Part A（状态机/声明式管线）、Part B（试跑态 vs 正式态）、Part F（自治批处理）。
- **关心"信号质量怎么呈现给人"** → Part E（Emotiv / Neurosity / OpenBCI 最具体）、Part D（商业采集软件的阻抗引导）、Part G（临床阈值依据）。
- **关心"哪些能全自动"** → Part C（自动阈值与自动标注的成熟度与边界）、Part F（全自动管线与报告）。
- **关心"审计留痕"** → Part C（EEGLAB history / PREP log / clean_rawdata_log）、Part F（Automagic 评级留痕、brainlife 溯源）。

---

"""


def demote(text):
    # 先 H2 -> H3（让每个 Part 内部的"附/速答"等小节与其对象小节同级），
    # 再把 Part 自己的 H1 -> H2，避免与报告标题冲突。
    lines = text.split("\n")
    out = []
    for ln in lines:
        if ln.startswith("## ") and not ln.startswith("### "):
            out.append("#" + ln)
        else:
            out.append(ln)
    for i, ln in enumerate(out):
        if ln.startswith("# "):
            out[i] = "#" + ln
            break
    return "\n".join(out)


def main():
    chunks = [HEADER]
    missing = []
    for fn, title in PARTS:
        p = os.path.join(BASE, fn)
        if not os.path.exists(p):
            missing.append(fn)
            chunks.append("## %s\n\n> ⚠️ 本 Part 交付文件缺失：`%s`\n\n---\n\n" % (title, fn))
            continue
        with io.open(p, "r", encoding="utf-8") as f:
            body = f.read().strip()
        body = demote(body)
        chunks.append(body + "\n\n---\n\n")
    text = "\n".join(chunks)
    with io.open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    print("WROTE %s" % OUT)
    print("chars=%d  lines=%d" % (len(text), text.count("\n") + 1))
    if missing:
        print("MISSING PARTS: %s" % ", ".join(missing))


main()
