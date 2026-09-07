# 判语 004：OpenBCI 唯一全开源契合

> 判决日期：2026-09-05 | 状态：已定 | 影响范围：硬件选型

## 判决

OpenBCI 是唯一满足"现货＋软硬件全开源＋许可允许复刻再分发＋BrainFlow/LSL/Unity 全通"四条全契合项。约 $625/套＋电极。亦是将来自研复刻的参考蓝本。

## 依据（可核验的事实）

- 硬件开源：CERN-OHL 许可，BOM/PCB/CAD 全公开
- 软件开源：固件 GPLv3，GUI MIT
- 生态完整：BrainFlow 原生支持，LSL 原生支持，Unity 集成成熟
- 现货可购：Ganglion $625，Cyton $1,249，Cyton+Daisy $2,499
- 许可允许复刻：遵守互惠条款即可再分发

## 被否方案

- BrainBit：EULA 禁止再分发（见判语 002）
- NeuraDock：截至 2026-09-06，其 Crowd Supply 众筹页显示 Coming Soon，开源资源（Python SDK、机械 CAD）页面标注为"计划提供"，尚未公开可下载验证
- Muse：闭源 SDK，个人自用足够但不可作为自研蓝本

## 可复用教训

"开源"不是单一维度，要看硬件、软件、许可三层。OpenBCI 三层全开，是唯一可复刻的选项。

## 关联

- 方案稿：01_项目管理\止观AI多模态反馈系统落地方案讨论稿.md §三
- 对话来源：2026-09-05 硬件全系对比调研

---

## English Summary

**Decision:** OpenBCI is the only hardware option satisfying all four criteria: in stock, fully open-source hardware and software, license permits reproduction and redistribution, and native BrainFlow/LSL/Unity support. Approximately $625 per set plus electrodes. It also serves as the reference blueprint for future self-developed hardware.

**Evidence (verifiable facts):**
- Hardware open source: CERN-OHL license, BOM/PCB/CAD fully public
- Software open source: firmware GPLv3, GUI MIT
- Complete ecosystem: native BrainFlow, native LSL, mature Unity integration
- In stock: Ganglion $625, Cyton $1,249, Cyton+Daisy $2,499
- License permits reproduction and redistribution under reciprocity clauses

**Rejected Alternatives:**
- BrainBit: EULA prohibits redistribution (see Decision 002)
- NeuraDock: as of 2026-09-06 its Crowd Supply page shows "Coming Soon"; open-source resources (Python SDK, CAD) are marked "plan to provide" and not yet publicly verifiable
- Muse: closed-source SDK—fine for personal use, unusable as a self-development blueprint

**Reusable Lesson:**
"Open source" is not one dimension—check three: hardware, software, and license. OpenBCI is open on all three, which makes it the only reproducible option.
