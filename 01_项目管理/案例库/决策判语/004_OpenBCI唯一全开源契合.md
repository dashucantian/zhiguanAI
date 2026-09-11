# 判语 004：OpenBCI 唯一全开源契合

> 判决日期：2026-09-05 | 状态：已定（主结论不变，适用范围收窄） | 影响范围：硬件选型
> **依据修订：2026-09-08** —— NeuraDock 开源状态由"不可验证"改为分层实测表述，其否决范围收窄为"不能作自研复刻蓝本"；主判决与 OpenBCI 的四条全契合结论均未变动。修订处见下方"被否方案"内嵌订正块。
> **选型定版修订：2026-09-09** —— 采购层已另判并执行：09-08 晚法师付清 NeuraDock 全款 6800 元（日志 011、ZG-019 结项）；选型理由定版＝契合度（视觉定位、枕顶布点）＋共同探索意愿 > OpenBCI 的"成熟但已固化"（09-08 夜会决策 2）。**本判语主结论的适用范围由此收窄为"工程/自研蓝本层"**：OpenBCI 仍为唯一四条全契合项（含制造文件），作将来自研复刻参考蓝本；采购层不再以本判语为唯一依据。两层不冲突：现在买 NeuraDock 拿数据、共探索，OpenBCI 留作复刻蓝本与开源基准。

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
- NeuraDock：截至 2026-09-06，其 Crowd Supply 众筹页显示 Coming Soon，开源资源（Python SDK、机械 CAD）页面标注为"计划提供"，尚未公开可下载验证。【2026-09-08 补充】厂商直供通道已落地：软件+TCP 教程 SDK 实际可得（eeg-workstation-python 仓库 + JunwenLuo/NeuraDock-Tutorials），核心板 Pinout 开源（白皮书 5.3，FPC 解耦可换形态）——自研蓝本地位实际强于 OpenBCI 整机参考，待组织仓库 Neuradock 正式兑现后修订本判语权重。
  - **【依据修订 2026-09-08】上条"尚未公开可下载验证"已过期，须改为分层表述。** 经抽查其 GitHub 组织 8 个公开仓库（2026-06~07 持续提交，实测非据承诺）：**软件层已开源可验证**——`eeg-workstation-python` 仓含 `Neuradock_library.py`＋6 个教程 notebook，MIT 许可，数据格式公开（250Hz、7 通道、.txt 逗号分隔、实时流走 TCP）；**硬件仅接口级开放**——公开 16 针电极连接器与 MCU 调试口 pin 定义；**制造级仍不开源**——同仓明确声明不含原理图、PCB、Gerber、BOM、制造文件，"currently not publishing a full open-hardware manufacturing package"，许可栏虽写 CERN-OHL-W／CC BY-SA 4.0 但**对应文件未在仓库内**（许可是承诺，文件才是事实）。众筹页至今仍为 launching soon，本条观察依然成立。
  - **故 NeuraDock 的否决范围应收窄，而非取消**：它**仍不能作为自研复刻蓝本**（无制造文件），这一点不变；但"开源资源不可验证"不再是否决理由——其软件层已可验证开放，且方向与本项目社区愿景同向（正在建开源社区）。采购定位由"被否方案"转为"合作验证伙伴＋当下拿到枕顶区数据的唯一现货路径"，详见 ZG-019 记录⑧–⑮。
  - **本判语主结论不受影响**：OpenBCI 仍是唯一满足"现货＋软硬件全开源（含制造文件）＋许可允许复刻再分发＋BrainFlow/LSL/Unity 全通"四条全契合项者。NeuraDock 现满足前三条中的软件部分，缺制造文件；Unity 插件"正在开发中"、LSL 未提及，第四条亦未全通。
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
  - **[Evidence revised 2026-09-08]** The "not yet publicly verifiable" clause above is **stale**; replace it with a layered statement. Inspection of its GitHub org (8 public repos, commits through 2026-06~07, measured not promised): **software layer is open and verifiable**—`eeg-workstation-python` ships `Neuradock_library.py` + 6 tutorial notebooks under MIT, with public data format (250 Hz, 7 channels, comma-delimited .txt, real-time over TCP); **hardware open only at interface level**—16-pin electrode connector and MCU debug port pinouts; **manufacturing layer still closed**—the same repo explicitly excludes schematics, PCB, Gerber, BOM and manufacturing files ("currently not publishing a full open-hardware manufacturing package"), and although the license field reads CERN-OHL-W / CC BY-SA 4.0, **no such files are in the repo** (a license is a promise; files are the fact). The Crowd Supply page remains "launching soon".
  - **So the rejection scope narrows rather than lifts**: NeuraDock **still cannot serve as a blueprint for in-house replication** (no manufacturing files)—that part is unchanged. But "open-source resources unverifiable" is no longer a valid ground for rejection. Its purchasing role shifts from "rejected alternative" to "collaboration/validation partner + the only in-stock route to occipito-parietal data today"; see ZG-019 items ⑧–⑮.
  - **The main verdict is unaffected**: OpenBCI remains the only option satisfying all four criteria—in stock, fully open hardware and software *including manufacturing files*, license permitting reproduction and redistribution, and native BrainFlow/LSL/Unity support. NeuraDock now meets the software half of the first three but lacks manufacturing files; its Unity plugin is "in development" and LSL is unmentioned, so criterion four is not fully met either.
- Muse: closed-source SDK—fine for personal use, unusable as a self-development blueprint

**Reusable Lesson:**
"Open source" is not one dimension—check three: hardware, software, and license. OpenBCI is open on all three, which makes it the only reproducible option.
