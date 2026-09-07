# 判语 006：MoE 优于 Dense（带宽受限）

> 判决日期：2026-09-05 | 状态：已定 | 影响范围：本地模型选型

## 判决

在本机（AMD Ryzen AI MAX+ 395，64GB 统一内存，无 NVIDIA 独显）上，MoE 架构模型（如 Qwen3-30B-A3B）推理速度显著优于 Dense 架构模型（如 Qwen3.8-27B）。

## 依据（可核验的事实）

- 本机瓶颈是内存带宽（约 215-256 GB/s），不是显存容量
- 带宽受限的机器上，决定推理速度的是**每生成一个字真正参与计算的激活参数量**，而非总参数量
- Qwen3-30B-A3B（Q4 约 18.6GB）：Strix Halo 同类实测短上下文约 100 tok/s，20K 上下文约 50 tok/s
- Qwen3.8-27B（Dense）：本机实测约 11-24 tok/s
- 速度差 2-6 倍，是体验级差别

## 被否方案

- 继续用 Qwen3.8-27B（Dense）：速度慢，禅修引导场景会明显卡顿
- 购买 NVIDIA 独显：本机是统一内存架构，无需购卡

## 可复用教训

选模型不能只看参数量，要看架构。带宽受限的机器上，MoE 的激活参数量优势远大于 Dense 的总参数量优势。

## 关联

- 方案稿：01_项目管理\止观AI多模态反馈系统落地方案讨论稿.md §七
- 对话来源：2026-09-05 本机算力核实

---

## English Summary

**Decision:** On this machine (AMD Ryzen AI MAX+ 395, 64GB unified memory, no NVIDIA discrete GPU), MoE-architecture models (e.g. Qwen3-30B-A3B) infer significantly faster than Dense-architecture models (e.g. Qwen3.8-27B).

**Evidence (verifiable facts):**
- The machine's bottleneck is memory bandwidth (~215–256 GB/s), not memory capacity
- On bandwidth-limited machines, inference speed is determined by the **activated parameter count per generated token**, not total parameter count
- Qwen3-30B-A3B (Q4 ~18.6GB): ~100 tok/s short context, ~50 tok/s at 20K context (Strix Halo-class measurements)
- Qwen3.8-27B (Dense): ~11–24 tok/s measured locally
- A 2–6x speed difference—an experience-level gap

**Rejected Alternatives:**
- Keep using Qwen3.8-27B (Dense): slow, noticeably laggy in guided-meditation scenarios
- Buy an NVIDIA discrete GPU: unnecessary on a unified-memory machine

**Reusable Lesson:**
When choosing models, look at architecture, not just parameter count. On bandwidth-limited hardware, MoE's activated-parameter advantage far outweighs Dense's total-parameter advantage.
