# 坑 014：CPU 环境跑新开源模型的连环坑——flash_attn 硬编码／Windows spawn 序列化／依赖清单对不上

## 现象

2026-10-01 在无 N 卡的本机（AMD 8060S 核显＋CPU 版 torch 2.14）试跑 Qwen-Drive-1.0-4B，三个脚本三种死法：

1. **demo.py**：`ImportError: FlashAttention2 has been toggled on, but it cannot be used`——VQA 脚本（run_vqa.py）刚跑通，官方演示脚本一跑就炸
2. **run_planning.py**：`AttributeError: Can't get local object '_make_resolver.<locals>.<lambda>.<locals>.<lambda>'`＋子进程 `EOFError: Ran out of input`——模型还没载入就死
3. **首个脚本 run_vqa.py**：`ModuleNotFoundError: No module named 'torchvision'`；demo.py 二跑：`No module named 'pyarrow'`——官方 requirements.txt 里明明都列着

## 根因

三个坑三层：

1. **同仓脚本间默认值不一致**：run_vqa.py 显式 `attn_implementation="sdpa"`（CPU 可用），demo.py 却硬编码 `"flash_attention_2"` 且**无命令行开关**——CUDA-only 的注意力实现被写死在演示脚本里，作者只在 N 卡机上测过
2. **Windows spawn 进程模型 vs 开发者的 Linux fork 假设**：DataLoader 多进程在 Windows 走 spawn（重新 import＋pickle 传参），代码里 `_make_resolver` 返回的闭包含 lambda，pickle 不了——Linux 上能跑的代码 Windows 上起不来
3. **"requirements 能跑通官方环境"≠"装了 torch 就够"**：torchvision、pyarrow 不随 torch 自动装；仓库自带 demo 数据是 parquet 格式，读它必须 pyarrow

## 解法

1. **注意力实现找带开关的脚本**：run_vqa.py／run_planning.py 均有 `--attn-implementation sdpa`，绕过 demo.py；判断口诀＝"哪个脚本能 `--device cpu`，哪个脚本就是 CPU 入口"
2. **`--num-workers 0` 杀多进程**：Windows 上 DataLoader 一律单进程，慢一点但对
3. **装依赖以脚本 import 为准，不以 requirements 已装过为凭**：报 ModuleNotFoundError 就地补装（torchvision 用 `--index-url https://download.pytorch.org/whl/cpu` 拿 CPU 版）

## 排障顺序（可复用）

CPU 环境跑新开源模型（仓库带脚本型）：

1. 先读 requirements.txt 对齐 Python 版本，再**全量 pip 补齐**，不等报错
2. 首选带 `--device`／`--attn-implementation` 开关的脚本；无开关的演示脚本先 grep `from_pretrained` 看写死了什么
3. 报 pickle／spawn／EOFError→第一反应查多进程，`--num-workers 0`
4. flash_attn／causal_conv1d／flash-linear-attention 三件是 CUDA／Triton 件，CPU 上**不必装**——transformers 自动回落参考实现，慢但正确（本轮实测：回落只拖速度，不出错）
5. 每步留存 exit code 与末 20 行日志，三个坑都是尾部日志定位的

## 教训

**新开源模型库的"官方演示"默认按 N 卡＋Linux 写，CPU/Windows 用户要自带绕行包。** 三坑全是环境差异而非模型问题——模型本体（4B 权重）在 CPU 上完整可跑。判断"能不能跑"前先把"哪个脚本、什么开关、哪些回落"查清；fallback 提示（"falling back to its reference PyTorch implementation"）是**慢但正确**的信号，不是错误信号，看见不必慌着装 CUDA 件。

## 关联

- 坑 004：本机无N卡的算力误判（同机判定）
- 坑 013：浏览器被拦不等于本机不可达（同战役通路坑）
- 调研件：`04_研究调研\20260930_Qwen-Drive文章调研_对人机建构线的定性与三条借形态_v1.md` §7.3/§7.4（提交 1f31a08）

---

## English Summary

**Symptom:** Running the newly open-sourced Qwen-Drive-1.0-4B on a CUDA-less Windows box (AMD 8060S iGPU, CPU torch 2.14), three scripts failed three ways: demo.py hard-codes `flash_attention_2` with no CLI switch (ImportError); run_planning.py died on Windows spawn pickling a nested lambda (`_make_resolver`) before loading the model; both torchvision and pyarrow were missing despite being listed in requirements.txt.

**Root cause:** (1) inconsistent defaults across scripts in the same repo — the demo was only ever tested on NVIDIA GPUs; (2) Windows spawn process model vs the author's Linux fork assumption — closures containing lambdas cannot pickle; (3) "requirements says so" ≠ "installed" — torchvision never ships with torch, and the bundled demo data (parquet) requires pyarrow.

**Solution:** use the scripts that expose `--attn-implementation sdpa` / `--device cpu`; set `--num-workers 0` on Windows; pip-install per actual imports (torchvision from the CPU wheel index). The CUDA/Triton trio (flash-attn, causal_conv1d, flash-linear-attention) is **not needed** — transformers falls back to reference implementations, slower but correct.

**Lesson:** official demos assume NVIDIA + Linux; on CPU/Windows, find the switch-equipped scripts first. Fallback notices mean "slow but correct", not "broken".
