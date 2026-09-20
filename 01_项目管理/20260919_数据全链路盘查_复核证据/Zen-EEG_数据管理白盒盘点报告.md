# 止观AI · Zen-EEG 脑电禅修研究项目 —— 数据管理现状白盒盘点

**审计对象**：`D:\Project\Zen-EEG`（数据工厂，只读遍历，排除 `.git`）+ `D:\Project\zhiguanAI\muse2-repo\muse2-master\report\`（暂存区）
**审计日期口径**：所有数字取自本次实际命令输出；报告不修改任何被审计文件。
**临时脚本**：`D:\Project\zhiguanAI\_analysis_tmp\`（`npz_probe.ps1`、`pickle_vm.ps1`、`scan_all_npz.ps1`、`npz_rows.xml/csv`、`npz_scan.txt`）

---

## 0. 方法与工具限制（影响可复现性，必须声明）

| 项 | 事实 |
|---|---|
| Python 执行 | **被沙箱拒绝**。`C:\Users\tiand\AppData\Local\Numbers\Programs\Python\Python312\python.exe` 不存在；实际可用解释器为 `%LOCALAPPDATA%\Programs\Python\Python312\python.exe`（Python 3.12.10 / numpy 2.5.2，首次调用成功）。此后**全部外部进程调用（python.exe / py.exe / cmd.exe / whoami.exe / git.cmd）均被 `Access is denied` 拒绝**，本会话审批提示已禁用，无法提权。 |
| 替代方案 | npz 结构改用 **.NET `System.IO.Compression` 直接解析 `.npy` 头**（只读头部，不解压数据体）；`meta` 为 numpy 0-d object 数组（pickle 流），改用**自建 PowerShell pickle 虚拟机**（`pickle_vm.ps1`）完整还原字典。所有 114 个 npz 无一失败。 |
| git 命令 | `git -C D:\Project\zhiguanAI rev-parse --show-toplevel` 曾成功返回 `D:/Project/zhiguanAI`；后续 `git log/status` 被拒绝。git 相关结论改由**文件系统证据**（`.git` 存在性、`.gitignore` 内容、`.git/logs/HEAD`、路径前缀）得出。 |
| npz 覆盖 | **114 个**：02_raw 8 + 03_quality_control 4 + 暂存区 102，全部扫描成功，0 错误。 |

---

## 1. 目录结构现状

### 1.1 十目录统计（实际命令输出）

| 目录 | 文件数 | 总字节 | MB | 实际内容 | 是否空壳 |
|---|---:|---:|---:|---|---|
| `00_governance` | 8 | 67,046 | 0.06 | 8 份治理文档 | 否（纯文档） |
| `01_registry` | 7 | 196,632 | 0.19 | 2 张 CSV + 1 份 .bak + README + P001/ 3 文件 | 否 |
| `02_raw` | 41 | **151,229,383** | 144.22 | 8 个会话包 × 5 文件 + README | 否 |
| `03_quality_control` | 33 | **17,652,899** | 16.84 | README + 8×qc.json + 4 个隔离包×6 文件 | 否 |
| `04_clean` | 1 | 459 | 0.00 | **仅 README.md** | **是** |
| `05_annotation` | 1 | 510 | 0.00 | **仅 README.md** | **是** |
| `06_features` | 1 | 352 | 0.00 | **仅 README.md** | **是** |
| `07_dataset_release` | 1 | 405 | 0.00 | **仅 README.md** | **是** |
| `08_models` | 1 | 548 | 0.00 | **仅 README.md** | **是** |
| `09_reports` | 1 | 374 | 0.00 | **仅 README.md** | **是** |
| （根）`README.md` | 1 | 2,194 | — | — | — |
| **合计（excl .git）** | **97** | **169,150,802** | **161.31** | | |

**空壳判定**：`04_clean`—`09_reports` **6 个目录共 6 个文件、2,648 字节，全部只有 README.md，无任何子目录**（`subdirs=0`）。README 均写于 2026-08-30 23:39:40，此后从未落过任何数据。

### 1.2 逐目录文件清单（文件名 / 字节 / 修改时间）

**`00_governance`（8）**

| 文件 | 字节 | 修改时间 |
|---|---:|---|
| Collection_SOP_V0.1.md | 5,781 | 2026-08-30 23:44:41 |
| Collection_SOP_V0.2.md | 7,275 | 2026-08-31 20:59:47 |
| Muse_BrainFlow_接入验证手册_V0.1.md | 8,597 | 2026-08-25 06:19:11 |
| Muse_muse-direct_接入验证手册_V0.2.md | 11,519 | 2026-09-01 07:48:58 |
| ZEN_EEG_Data_Dictionary_V1.md | 5,682 | 2026-08-25 06:09:59 |
| ZEN_EEG_Data_Dictionary_V1_1.md | 8,390 | 2026-08-31 20:48:20 |
| ZEN_EEG_Data_Dictionary_V1_2.md | 9,652 | 2026-09-01 01:01:03 |
| 入定状态标注规范_V1_初稿.md | 10,150 | 2026-08-25 08:11:42 |

**`01_registry`（7）**

| 文件 | 字节 | 修改时间 |
|---|---:|---|
| participant_registry.csv | 109 | 2026-08-25 01:42:41 |
| README.md | 665 | 2026-08-30 23:39:40 |
| session_registry.csv | 1,572 | **2026-09-19 04:17:01** |
| session_registry.csv.bak-20260919 | 853 | **2026-09-19 04:17:01** |
| P001/consent_v1.pdf | 178,205 | 2026-08-23 00:25:55 |
| P001/consent_v1.1.docx | 14,882 | 2026-08-31 20:09:34 |
| P001/profile.md | 346 | 2026-09-01 07:47:37 |

**`02_raw`（41 = README + 8×5）** —— 每个会话目录**恰好 5 个文件**（无 `session_events.jsonl`、无 `qc.json`）：

| 会话目录 | device_info.json | eeg_raw.npz | report.html | session_manifest.json | session_note.txt |
|---|---:|---:|---:|---:|---:|
| ZEN-20260830-P001-S02 | 386 | 5,325,674 | 219,494 | 645 | 465 |
| ZEN-20260830-P001-S03 | 386 | 7,537,994 | 243,537 | 645 | 465 |
| ZEN-20260830-P001-S04 | 386 | 37,935,514 | 383,667 | 645 | 465 |
| ZEN-20260831-P001-S05 | 386 | 3,235,754 | 194,346 | 645 | 535 |
| ZEN-20260901-P001-S06 | 386 | 7,211,114 | 209,425 | 645 | 1,188 |
| ZEN-20260905-P001-S08 | 434 | 37,128,974 | 312,804 | 652 | 430 |
| ZEN-20260906-P001-S12 | 434 | 2,737,148 | 191,317 | 652 | 394 |
| ZEN-20260911-P001-S13 | 876 | 47,996,647 | 351,427 | 1,075 | 430 |
| 02_raw/README.md | — | — | — | 897 | — |

**`03_quality_control`（33）** —— 见第 4 节。

**`04_clean`—`09_reports`（各 1）**：`README.md` 459 / 510 / 352 / 405 / 548 / 374 字节，全部 2026-08-30 23:39:40。

---

## 2. 登记表 `01_registry/session_registry.csv`

### 2.1 列结构

`session_id, participant_id, date, session_type, duration_seconds, status, manifest_path` = **7 列**。

> **口径问题**：`00_governance\ZEN_EEG_Data_Dictionary_V1_2.md` §2 只定义 **6 个字段**（session_id / participant_id / date / session_type / duration_seconds / status），**`manifest_path` 未在字典任何版本中定义**。备份文件 `session_registry.csv.bak-20260919` 只有 6 列，证明该列是 2026-09-19 新增而未升字典版本（最高版本仍为 V1.2，2026-09-01）。违反 README「字典先行」铁律。

### 2.2 全 13 行逐行

| # | session_id | participant_id | date | session_type | duration_seconds | status | manifest_path |
|---|---|---|---|---|---|---|---|
| 1 | ZEN-20260825-P001-S01 | P001 | 2026-08-25 | baseline | **(空)** | finished | **(空)** |
| 2 | ZEN-20260830-P001-S02 | P001 | 2026-08-30 | test | 520 | finished | 02_raw/ZEN-20260830-P001-S02/session_manifest.json |
| 3 | ZEN-20260830-P001-S03 | P001 | 2026-08-30 | test | 736 | finished | 02_raw/ZEN-20260830-P001-S03/session_manifest.json |
| 4 | ZEN-20260830-P001-S04 | P001 | 2026-08-30 | test | 3797 | finished | 02_raw/ZEN-20260830-P001-S04/session_manifest.json |
| 5 | ZEN-20260831-P001-S05 | P001 | 2026-08-31 | baseline | 316 | finished | 02_raw/ZEN-20260831-P001-S05/session_manifest.json |
| 6 | ZEN-20260901-P001-S06 | P001 | 2026-09-01 | training | 705 | finished | 02_raw/ZEN-20260901-P001-S06/session_manifest.json |
| 7 | ZEN-20260905-P001-S07 | P001 | 2026-09-05 | baseline | 1164 | quarantined | 03_quality_control/quarantine/ZEN-20260905-P001-S07/session_manifest.json |
| 8 | ZEN-20260905-P001-S08 | P001 | 2026-09-05 | baseline | 3631 | finished | 02_raw/ZEN-20260905-P001-S08/session_manifest.json |
| 9 | ZEN-20260905-P001-S09 | P001 | 2026-09-05 | test | 71 | quarantined | 03_quality_control/quarantine/ZEN-20260905-P001-S09/session_manifest.json |
| 10 | ZEN-20260905-P001-S10 | P001 | 2026-09-05 | test | 284 | quarantined | 03_quality_control/quarantine/ZEN-20260905-P001-S10/session_manifest.json |
| 11 | ZEN-20260905-P001-S11 | P001 | 2026-09-05 | test | 142 | quarantined | 03_quality_control/quarantine/ZEN-20260905-P001-S11/session_manifest.json |
| 12 | ZEN-20260906-P001-S12 | P001 | 2026-09-06 | baseline | 268 | finished | 02_raw/ZEN-20260906-P001-S12/session_manifest.json |
| 13 | ZEN-20260911-P001-S13 | P001 | 2026-09-11 | training | 4693 | finished | 02_raw/ZEN-20260911-P001-S13/session_manifest.json |

### 2.3 逐项检查结论

| 检查项 | 结果 |
|---|---|
| 行数 / 列数 | 13 数据行 / 7 列（含表头 14 行） |
| **重复 Zen-ID** | **无**。13 个 session_id 全部唯一；S01–S13 连续无缺号 |
| **participant 编号复用/冲突** | **无复用**。但 **13/13 全部是 P001**（单受试者）。`participant_registry.csv` 登记了 **P002（导师A，2026-08-25，active）却 0 个会话**，且 `01_registry\` 下**只有 P001 文件夹**，P002 无档案、无同意书。 |
| **缺失字段** | 仅 1 行 2 个空单元格：`ZEN-20260825-P001-S01` 的 `duration_seconds` 与 `manifest_path` |
| **日期 vs session_id** | **13/13 一致**（逐行比对 id 内嵌 YYYYMMDD 与 date 列） |
| **participant_id vs id 内嵌 PXXX** | **13/13 一致** |
| **status 取值合法性** | `finished`×9、`quarantined`×4。**`quarantined` 不在字典枚举 `planned/finished/aborted/rejected` 内**（字典 V1.2 §2）；SOP V0.2 异常处理规定质量否决应记 `rejected` |
| **session_type 取值合法性** | `baseline`×5、`test`×6、`training`×2，均在字典枚举内 |
| **manifest_path 指向有效性** | 12 个非空路径**全部指向磁盘上真实存在的文件**（已逐一验证） |
| **登记 vs 落盘** | 13 条登记 → 磁盘上 **12 个会话目录**；`ZEN-20260825-P001-S01` **全库无任何文件**（02_raw、隔离区、暂存区均无）。反向：磁盘无未登记目录。 |

### 2.4 `participant_registry.csv`

| participant_id | nickname | join_date | status |
|---|---|---|---|
| P001 | 发起人 | 2026-08-25 | active |
| P002 | 导师A | 2026-08-25 | active |

无真实姓名/身份证/手机号/住址（全库 PII 正则扫描仅命中治理文档中的规则文本本身）。**但 `01_registry\P001\profile.md` 写明 `Role: Project Founder`，昵称「发起人」——单人可识别，匿名强度极弱。**

---

## 3. 归档区 `02_raw/` 与「会话 × 应有文件」缺失矩阵

### 3.1 缺失矩阵

图例：`✓`=存在；`—`=按设计不在本目录（有替代位置）；`✗`=**缺失**

| 会话 ID | session_manifest.json | session_events.jsonl | eeg_raw.npz | report.html | device_info.json | session_note.txt | qc.json | 文件数 |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| ZEN-20260825-P001-S01 | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | **0** |
| ZEN-20260830-P001-S02 | ✓ | **✗** | ✓ | ✓ | ✓ | ✓ | —¹ | 5 |
| ZEN-20260830-P001-S03 | ✓ | **✗** | ✓ | ✓ | ✓ | ✓ | —¹ | 5 |
| ZEN-20260830-P001-S04 | ✓ | **✗** | ✓ | ✓ | ✓ | ✓ | —¹ | 5 |
| ZEN-20260831-P001-S05 | ✓ | **✗** | ✓ | ✓ | ✓ | ✓ | —¹ | 5 |
| ZEN-20260901-P001-S06 | ✓ | **✗** | ✓ | ✓ | ✓ | ✓ | —¹ | 5 |
| ZEN-20260905-P001-S07 | ✓ | **✗** | ✓ | ✓ | ✓ | ✓ | ✓ | 6 |
| ZEN-20260905-P001-S08 | ✓ | **✗** | ✓ | ✓ | ✓ | ✓ | —¹ | 5 |
| ZEN-20260905-P001-S09 | ✓ | **✗** | ✓ | ✓ | ✓ | ✓ | ✓ | 6 |
| ZEN-20260905-P001-S10 | ✓ | **✗** | ✓ | ✓ | ✓ | ✓ | ✓ | 6 |
| ZEN-20260905-P001-S11 | ✓ | **✗** | ✓ | ✓ | ✓ | ✓ | ✓ | 6 |
| ZEN-20260906-P001-S12 | ✓ | **✗** | ✓ | ✓ | ✓ | ✓ | —¹ | 5 |
| ZEN-20260911-P001-S13 | ✓ | **✗** | ✓ | ✓ | ✓ | ✓ | —¹ | 5 |

¹ `qc.json` 按 `ingest_session.py:330` 设计落在 `03_quality_control/<session_id>/qc.json`（8 个，均存在）；隔离会话落在包内。

### 3.2 结论

- **`session_events.jsonl` 在 `D:\Project\Zen-EEG` 全树 0 个**（`-Filter '*session_events*'` 递归全库搜索，仅暂存区有 5 个）。
- `session_manifest.json` **12/12 全部存在，但全部是 2026-09-19 04:17:01 由回填脚本生成的骨架**：`"protocol": "历史会话回填骨架（2026-09-19 裁定 P1§八-8）"`、`"consent_version": "缺失（回填，采集端未记录）"`。12 份中 **11 份 `signal_chain` 为空对象 `{}`**，仅 S13 有真实链标注。
- **`eeg_raw.npz` 8/8 存在但全部不含 `eeg_pre_filter`**（见第 6 节）。

---

## 4. 隔离区 / 质控区 `03_quality_control/`

### 4.1 全部内容（33 文件 / 17,652,899 字节）

| 路径 | 文件数 | 字节 | 内容 |
|---|---:|---:|---|
| `03_quality_control/README.md` | 1 | 528 | 说明文档 |
| `03_quality_control/ZEN-2026...-S02/S03/S04/S05/S06/S08/S12/S13/qc.json` | 8 | 2,839 | **仅一个 qc.json**，无 npz、无 html |
| `03_quality_control/quarantine/ZEN-20260905-P001-S07/` | 6 | 13,440,011 | device_info 433 / eeg_raw.npz 11,904,597 / qc.json 394 / report.html 263,300 / session_manifest.json 652 / session_note.txt 435 |
| `03_quality_control/quarantine/ZEN-20260905-P001-S09/` | 6 | 814,841 | 433 / 705,782 / 394 / 106,933 / 652 / 1,073 |
| `03_quality_control/quarantine/ZEN-20260905-P001-S10/` | 6 | 3,099,246 | 433 / 2,908,264 / 394 / 187,505 / 652 / 586 |
| `03_quality_control/quarantine/ZEN-20260905-P001-S11/` | 6 | 1,545,264 | 436 / 1,438,315 / 397 / 125,638 / 655 / 1,076 |

隔离区 npz 合计 **16,956,958 字节**（4 个）。

### 4.2 与 `02_raw` 的关系 / 是否重复存储

1. **对 8 个正式会话：不重复**。`03_quality_control/<sid>/` 只放 `qc.json`（约 350 字节），EEG 数据体不存在副本。关系是「派生指标 ← 读取 02_raw」，符合 README 声明。
2. **对 4 个隔离会话：是完整数据包**，包含 npz+html+device_info+note+manifest+qc。它们**不在 02_raw 中**，因此 02_raw 与隔离区之间对同一会话**不构成重复**。
3. **真正的重复存储发生在归档区与暂存区之间**：**6 个会话的 npz 与暂存区文件字节级完全相同（MD5 一致）**，见第 5.4 节。

### 4.3 `qc.json` 结构一致性

| 字段集 | 出现次数 |
|---|---:|
| `session_id, scene, quarantined, effective_sample_rate_hz, packet_loss_rate, noise_epochs, clean_ratio, channel_quality, report_source, generated_by`（10 字段） | 7（S07–S13） |
| `session_id, effective_sample_rate_hz, packet_loss_rate, noise_epochs, clean_ratio, channel_quality, report_source, generated_by`（8 字段，**无 scene / quarantined**） | 5（S02–S06） |

| 会话 | eff_Hz | packet_loss | noise_epochs | clean_ratio | quarantined | 生成者 |
|---|---:|---:|---|---:|---|---|
| S02 | 255.77 | 0.0009 | 1/102 | 0.99 | **ABSENT** | ingest_session@2026-08-30 |
| S03 | 255.86 | 0.0005 | 1/146 | 0.99 | **ABSENT** | ingest_session@2026-08-30 |
| S04 | 249.80 | 0.0242 | 9/739 | 0.99 | **ABSENT** | ingest_session@2026-08-30 |
| S05 | 255.62 | 0.0015 | **EMPTY** | **null** | **ABSENT** | ingest_session@2026-08-30 |
| S06 | 255.69 | 0.0012 | **EMPTY** | **null** | **ABSENT** | ingest_session@2026-08-30 |
| S07 | 255.59 | 0.0016 | **EMPTY** | **null** | True | ingest_session@2026-09-03 |
| S08 | 255.63 | 0.0014 | 2/724 | 1.0 | False | ingest_session@2026-09-03 |
| S09 | 247.84 | 0.0319 | **EMPTY** | **null** | True | ingest_session@2026-09-03 |
| S10 | 255.47 | 0.0021 | **EMPTY** | **null** | True | ingest_session@2026-09-03 |
| S11 | 252.62 | 0.0132 | **EMPTY** | **null** | True | ingest_session@2026-09-03 |
| S12 | 255.56 | 0.0017 | **EMPTY** | **null** | False | ingest_session@2026-09-03 |
| S13 | 255.67 | 0.0013 | 4/936 | 1.0 | False | ingest_session@2026-09-03 |

- `effective_sample_rate_hz` 与 `samples/duration` **12/12 复算一致**（最大误差 <0.02 Hz）——这一项口径可靠。
- 但 **7/12 的 `noise_epochs` 为空字符串、`clean_ratio` 为 `null`**（从 report.html 解析失败），即半数以上会话**没有可用的噪声/干净片段结论**。
- 隔离原因未记录在 `qc.json` 内（无 `quarantine_reason` 字段），只能从 session_note 反推。
- **S09/S11 的 `channel_quality` 全部为 `"ok"`**，与实际 `data_origin: simulator` 及 3.19%/1.32% 丢包的事实不匹配。

---

## 5. 暂存区 `D:\Project\zhiguanAI\muse2-repo\muse2-master\report\`

### 5.1 总量

| 指标 | 实测值 |
|---|---|
| 文件总数 | **223** |
| 总大小 | **900,635,013 字节 = 858.91 MB** |
| `.npz` | **102 个 / 883,030,962 字节 / 842.12 MB** |
| `.html` | 103 个 / 17,510,925 字节 |
| `.json` | 13 个 / 87,954 字节 |
| `.jsonl` | 5 个 / 5,172 字节 |
| 子目录 | **0**（完全扁平） |

### 5.2 命名模式与时间跨度

- 命名模式：**102/102 严格匹配 `local_YYYYMMDD_HHMMSS.npz`**，无例外（正则 `^local_\d{8}_\d{6}$` 通过率 100%）。
- 报告命名：`local_YYYYMMDD_HHMMSS.report.html`（103 个）。
- **文件名日期分布**（102 个）：20260830×3、20260831×4、20260901×25、20260902×3、20260903×22、20260904×2、20260905×14、20260906×4、20260907×1、20260908×1、20260909×2、20260910×10、20260911×4、20260912×1、20260913×1、20260919×5（共 16 个日期）。
- **跨度**：最早 `local_20260830_183343.npz`（mtime 2026-08-30 18:33:43）→ 最新 `local_20260919_222226.npz`（mtime 2026-09-19 22:22:27），跨 **20 天**。
- 单文件大小：7,751 字节（最小）～ 86,393,003 字节（最大）；0 字节文件 0 个。

### 5.3 非 npz 附加物

- **5 个会话自带完整契约**（仅 2026-09-19 的 5 个）：`local_20260919_050129 / 050845 / 055248 / 215617 / 222226`，各含 `.session_manifest.json` + `.session_events.jsonl` + `.report.html` + `.npz`。
- **8 个分析产物 JSON**（与信号数据同目录混放）：`b2_mapping_v2.json`、`b3_replay_local_20260906_011204.json`(70,759 B)、`crosscheck_brainflow_result.json`、`crosscheck_live_stage2_result.json`、`crosscheck_stage2_live_consumer_20260907_224418/231226.json`、`crosscheck_stage2_sim_consumer_20260907_223227/225412.json`。
- 孤儿：**2 个 report 无对应 npz**（`local_20260913_201423.report.html`、`local_20260913_201711.report.html`，各 104,013 B）；**1 个 npz 无对应 report**（`local_20260901_090308.npz`，1,321,992 B）。

### 5.4 是否已在 registry 登记

| 分类 | 数量 | 证据 |
|---|---:|---|
| **与归档区字节级完全相同（MD5 一致）** | **6** | S08=`local_20260905_192147.npz`；S12=`local_20260906_011204.npz`；S07=`local_20260905_180927.npz`；S09=`local_20260905_205502.npz`；S10=`local_20260905_210052.npz`；S11=`local_20260905_210448.npz` |
| **同一录制但归档时被改写**（大小/行数/meta.timestamp/source_file 对应） | 6 | S05=`local_20260831_233025.npz`；S06=`local_20260901_001855.npz`；S13=`local_20260911_232300.npz`；S02=`local_20260830_183343.npz`；S03=`local_20260830_183719.npz`；S04=`local_20260830_202946.npz` |
| **未在任何登记表中出现** | **90** | 无 Zen-ID、无 participant、无 session_note、无 qc |

- **重复存储（MD5 证实）合计 56,823,080 字节 = 54.19 MB**（S08 37,128,974 + S07 11,904,597 + S10 2,908,264 + S12 2,737,148 + S11 1,438,315 + S09 705,782）。
- **暂存区内部**：3 组同字节数文件（`090308/093000` 各 1,321,992；`0901_001719/001855` 各 7,211,114；`0903_135148/135149` 各 21,328,234），但 **MD5 两两不同**；其中 **2 组是同一录制的重复保存**（行数与 duration 完全一致）：
  - `local_20260901_001719.npz` 与 `local_20260901_001855.npz`：均 **180252 行 / 704.970992088318 s**，MD5 不同（`4CDE214B…` vs `3A9B083A…`）→ 违反字典 V1.2「同一次录制的保存必须幂等」。
  - `local_20260903_135148.npz` 与 `local_20260903_135149.npz`：均 **533180 行 / duration 相同**，MD5 不同。
- 暂存区**无任何治理文档、无 README、无版本标记、无清理策略**；`ingest_session.py:234` 用 `shutil.copy2` **复制而非移动**，因此入库后源文件永久留存 → 重复存储是流水线设计结果，不是偶发。

---

## 6. npz 结构一致性表

### 6.1 抽样与全量方法

- 全量扫描 **114 个 npz**（02_raw 8 + 03_quality_control 4 + 暂存区 102），**0 失败**。
- 解析方式：`.npy` 头直读（magic/version/header-len/dict）取 shape+dtype+fortran；`meta` 用自建 pickle VM 完整还原。
- 以下抽样明细覆盖三类来源共 12 个（全部已归档 npz 逐个体列出）。

### 6.2 已归档 npz 逐文件结构（12/12）

| 会话 | 来源 | 大小(B) | 键集合 | `eeg` shape | dtype | `timestamps` | `meta` 字段数 | `eeg_pre_filter` |
|---|---|---:|---|---|---|---:|:--:|
| ZEN-20260830-P001-S02 | 02_raw | 5,325,674 | eeg+meta+timestamps | (133116, 4) | `<f8` | (133116,) | 5 | **无** |
| ZEN-20260830-P001-S03 | 02_raw | 7,537,994 | eeg+meta+timestamps | (188424, 4) | `<f8` | (188424,) | 5 | **无** |
| ZEN-20260830-P001-S04 | 02_raw | 37,935,514 | eeg+meta+timestamps | (948362, 4) | `<f8` | (948362,) | 5 | **无** |
| ZEN-20260831-P001-S05 | 02_raw | 3,235,754 | eeg+meta+timestamps | (80868, 4) | `<f8` | (80868,) | 5 | **无** |
| ZEN-20260901-P001-S06 | 02_raw | 7,211,114 | eeg+meta+timestamps | (180252, 4) | `<f8` | (180252,) | 5 | **无** |
| ZEN-20260905-P001-S08 | 02_raw | 37,128,974 | eeg+meta+timestamps | (928194, 4) | `<f8` | (928194,) | 12 | **无** |
| ZEN-20260906-P001-S12 | 02_raw | 2,737,148 | eeg+meta+timestamps | (68400, 4) | `<f8` | (68400,) | 11 | **无** |
| ZEN-20260911-P001-S13 | 02_raw | 47,996,647 | eeg+meta+timestamps | (1199878, 4) | `<f8` | (1199878,) | 13 | **无**（源有，见 6.5） |
| ZEN-20260905-P001-S07 | 03_qc/quarantine | 11,904,597 | eeg+meta+timestamps | (297586, 4) | `<f8` | (297586,) | 11 | **无** |
| ZEN-20260905-P001-S09 | 03_qc/quarantine | 705,782 | eeg+meta+timestamps | (17616, 4) | `<f8` | (17616,) | 11 | **无** |
| ZEN-20260905-P001-S10 | 03_qc/quarantine | 2,908,264 | eeg+meta+timestamps | (72678, 4) | `<f8` | (72678,) | 11 | **无** |
| ZEN-20260905-P001-S11 | 03_qc/quarantine | 1,438,315 | eeg+meta+timestamps | (35928, 4) | `<f8` | (35928,) | 13 | **无** |

**基础结构 12/12 一致**：三键 `eeg / timestamps / meta`，全部 `<f8`，`eeg` 列数 4，`timestamps` 一维与 `eeg` 行数相等，`meta` 为 `|O` 0-d 对象数组。

### 6.3 `meta` 字段一致性

**字典 V1.2 §3.1 冻结的 meta schema 恰好 5 个键**：`timestamp, sfreq, channels, samples, duration`。

| 会话 | meta 键集合 | 字段数 | 超出字典的键 |
|---|---|---:|---|
| S02 / S03 / S04 / S05 / S06 | channels, duration, samples, sfreq, timestamp | 5 | **无（合规）** |
| S12 | channels, contact_quality, duration, note, participant, pre_state, samples, scene, session_type, sfreq, timestamp | 11 | +6 |
| S07 / S09 / S10 | 同上 | 11 | +6 |
| S08 | 同上 **+ post_state** | 12 | +7 |
| S13 | 11 键 **+ device + signal_chain** | 13 | +8 |
| S11 | channels, contact_quality, duration, **experiment_mode, experiment_tag**, note, participant, post_state, pre_state, samples, scene, sfreq, timestamp | 13 | +8（且**无 session_type**，改用未定义键 `experiment_mode/experiment_tag`） |

**结论**：
- 归档区内部就有 **5 套不同的 meta schema**；**7/12 的 npz 携带 6–8 个字典未定义的键**（`participant / session_type / scene / pre_state / post_state / contact_quality / note / device / signal_chain / experiment_mode / experiment_tag`）。字典 V1.2 的总原则是「任何字段必须先在本字典中定义，才能进入 02_raw」——这些键**从未被任何字典版本定义**。
- `meta.channels` 12/12 均为 `[TP9,AF7,AF8,TP10]`，`meta.sfreq` 12/12 为 256，`samples` 与 `eeg` 行数 12/12 相等（符合「行数为唯一权威」要求）。
- `duration` 与 registry `duration_seconds` **12/12 四舍五入后一致**。

### 6.4 时间戳口径（三种并存）

| 口径 | 会话 | `timestamps[0]` | 实际含义 |
|---|---|---|---|
| **A. 相对秒（0 起点）** | S02, S03, S04 | `0.0` | 0 → 520.45 / 736.43 / 3796.51。**字典 V1.2 §3.1 规定 2026-09-01 前保存的录制须换算为纪元秒**；这 3 个未换算（字典另设「历史例外」条款承认不回改，但其 session_note **缺少 `timestamps_epoch_normalized` 行**，与字典 §3.3 要求的字段清单不符） |
| **B. 原始纪元秒** | S07–S13（7 个） | 1.788e9 量级 | 采集端直出 |
| **C. 由错误锚点换算的纪元秒** | S05, S06 | 1.788e9 量级 | 见 6.6 |

### 6.5 `eeg_pre_filter` 覆盖情况

| 存储层 | 有 `eeg_pre_filter` | 无 `eeg_pre_filter` | 合计 |
|---|---:|---:|---:|
| `02_raw`（归档区） | **0** | 8 | 8 |
| `03_quality_control`（隔离区） | **0** | 4 | 4 |
| 暂存区 | **20** | 82 | 102 |
| **合计** | **20（全部在无治理的暂存区）** | 94 | 114 |

- **归档区 0% 覆盖**。`ingest_session.py:219-232` 明确写着 2026-09-18 起「eeg_pre_filter 若有必随档」，但**没有任何一个归档 npz 被重新入库**。
- **可证实的单点数据丢失**：`ZEN-20260911-P001-S13` 的源文件 `local_20260911_232300.npz`（86,393,003 B）**含 `eeg_pre_filter`**，其归档副本 `02_raw\ZEN-20260911-P001-S13\eeg_raw.npz`（47,996,647 B）**不含**。两者行数相同（1,199,878）、`meta.timestamp` 相同。滤波前原始波形只存在于暂存区。
- 20 个含 pre_filter 的暂存 npz 中，**2 个是 7 通道 NeuraDock 数据**（`local_20260919_215617` 9,685 行 / `local_20260919_222226` 249,084 行，`channels=[CP5,CP6,PO3,PO4,O1,Oz,O2]`，`sfreq=250`）——与 Muse 4 通道 256 Hz 完全不同的设备与导联，**未登记、未隔离，与 Muse 数据同目录混放**。

### 6.6 时间轴错位（本次盘点新发现的系统性缺陷）

用暂存区源文件名时间戳反推可严格证明：**`local_YYYYMMDD_HHMMSS` 与 `meta.timestamp` 记录的都是「录制结束/存盘时刻」，不是字典 §3.1 定义的「采集开始时刻」。**

| 暂存源文件 | 文件名时刻 | duration | 反推开始时刻 | 该 npz 实际 `timestamps[0]`（本地） |
|---|---|---:|---|---|
| local_20260905_192147 | 19:21:47 | 3631.0 s | 18:21:16 | **18:21:16 ✓完全吻合** |
| local_20260911_232300 | 23:23:00 | 4693.0 s | 22:04:46 | **22:04:48 ✓** |
| local_20260906_011204 | 01:12:04 | 267.6 s | 01:07:36 | **01:07:27 ✓** |

由此推出的两组后果：

**(a) 全部 12 个 `device_info.json` 的 `collection_start_utc` 都是结束时刻**
`ingest_session.py:200-201,251` 用 `meta.timestamp` 当地时刻 `.astimezone(utc)` 生成该字段。实测 `gap = (meta.timestamp→UTC) − timestamps[0]`：

| 会话 | meta.timestamp(本地) | duration | gap | gap − duration |
|---|---|---:|---:|---:|
| S07 | 2026-09-05 18:09:27 | 1164.3 s | 1164.1 s | −0.2 |
| S08 | 2026-09-05 19:21:47 | 3631.0 s | 3631.0 s | 0.0 |
| S09 | 2026-09-05 20:55:02 | 71.1 s | 71.4 s | +0.4 |
| S10 | 2026-09-05 21:00:52 | 284.5 s | 284.8 s | +0.3 |
| S11 | 2026-09-05 21:04:48 | 142.2 s | 142.6 s | +0.4 |
| S12 | 2026-09-06 01:12:04 | 267.6 s | 277.5 s | +9.9 |
| S13 | 2026-09-11 23:23:00 | 4693.0 s | 4692.8 s | −0.2 |

`gap ≈ duration`（6/7 误差 <1 s）→ **`collection_start_utc` 实为结束时刻**，与字典 §3.2「采集开始时刻（UTC）」的定义相反。例：S08 `device_info.json` 写 `2026-09-05T11:21:47Z`，而首样本真实时刻为 `2026-09-05T10:21:16Z`，**早 60 分 31 秒**。

**(b) S05/S06 的纪元时间轴整体后移一个完整会话时长**
这两条无原生时间戳，入库脚本以 `meta.timestamp`（实为结束时刻）为起点做 `start_epoch + arange(n)/sfreq`：

| 会话 | gap = (meta.ts→UTC) − ts[0] | duration | 结论 |
|---|---:|---:|---|
| S05 | **0.1 s** | 316.4 s | 时间轴被整体后移 **316.2 s** |
| S06 | **0.4 s** | 705.0 s | 时间轴被整体后移 **704.5 s** |

即 S05/S06 归档数据自称为「结束那一刻才开始录」。

### 6.7 S02/S03/S04 的时间戳是合成值

三个源 npz（`local_20260830_183343 / 183719 / 202946`）**只有 `eeg + meta` 两个键，根本没有 `timestamps` 数组**。归档副本却带 `timestamps`，`session_note.txt` 自述 `timestamps_backfilled: linear_interpolation`，且 `timestamps[0] = 0.0`、`timestamps[-1]` 恰等于 `meta.duration`。**该时间轴完全由 `arange(n)/256` 生成，不含任何真实到达时刻信息，无法用于丢包定位或跨会话对齐**——而字典 §3.1 正是把这两个用途写为该字段的存在理由。

---

## 7. 历史数据完整性

### 7.1 会话可用性分级

| 分类 | 数量 | 会话 |
|---|---:|---|
| 已登记会话 | 13 | S01–S13 |
| **有完整原始脑电（npz 存在）** | **12** | S02–S13 |
| **登记但零文件**（无 npz / 无 report / 无任何旁证） | **1** | **S01**（2026-08-25 baseline，13 条中唯一 `duration_seconds` 与 `manifest_path` 皆空） |
| 其中在正式归档区 `02_raw` | 8 | S02–S06, S08, S12, S13 |
| 其中在隔离区 | 4 | S07, S09, S10, S11 |
| **只有报告、没有数据** | **0** | 无任何会话存在 report.html 而缺 npz |
| **只有登记、报告与数据都没有** | **1** | S01 |

### 7.2 「可用」的进一步收窄（按 registry 语义）

| 筛法 | 数量 | 明细 |
|---|---:|---|
| `status = finished` | 9 | S02–S06, S08, S12, S13（+S01 也是 finished 但无数据） |
| finished **且** `session_type ≠ test` | **5** | S05(baseline, 316 s)、S06(training, 705 s)、S08(baseline, 3631 s)、S12(baseline, 268 s)、S13(training, 4693 s) |
| 其中满足 SOP「正式训练不少于 25 分钟(1500 s)」的 training | **1** | **仅 S13**（4693 s）。S06 = 705 s（11 分 45 秒），session_note 自述「蓝牙断连自动截断…实际采集11分45秒，短于不少于25分钟标准，正式训练待补采」 |
| `session_type = test`（字典：不进研究数据集） | 6 | S02–S04, S09–S11 |
| baseline 会话中符合 SOP「约 5 分钟基线」的 | **2** | S05(316 s)、S12(268 s)。**S07 = 1164 s（19.4 分钟）、S08 = 3631 s（60.5 分钟）被登记为 baseline，长度超出基线定义 4–12 倍** |

**净结论**：13 条登记中，**真正可进入研究建模的会话最多 1 条（S13）**，另有 4 条处于「非 test 但类型/时长存疑」状态。

### 7.3 模拟器 / 测试数据混在真实数据里

| 证据来源 | 数量 | 明细 |
|---|---:|---|
| `session_note.txt` 中 `data_origin: simulator`（显式标注为**非真实人脑采集**） | **2** | `03_quality_control\quarantine\ZEN-20260905-P001-S09\session_note.txt`、`...\ZEN-20260905-P001-S11\session_note.txt`。原文：「MonitorSimulator 合成信号，未真实走过采集链路…峰值 10.00Hz／次峰 20.00Hz／Alpha 相对功率 0.9564／通道 std 5.81µV，四项逐项吻合 console_server.py:341-346 的合成信号理论值…**取数时不得作为真实样本使用**」 |
| `session_type = test` 且 note 声明「链路测试录制，不进入研究数据集」 | 6 | S02, S03, S04, S09, S10, S11 |
| 暂存区 `meta.experiment_mode = 模拟` | **4** | `local_20260903_213644`、`local_20260903_214100`、`local_20260905_162636`、`local_20260905_210448`（后者即 S11 的来源） |
| 暂存区 `meta.experiment_mode = 真机蓝牙` | 9 | 真实链路 |
| 暂存区无 `experiment_mode` 字段（来源不可判定） | **89** | 87.3% 的暂存 npz 无法从元数据判断是真人还是模拟 |
| **时间戳为纯合成（线性插值）** | **3** | S02, S03, S04（见 6.7） |
| 分析脚本回放/回归产物与数据混放 | 8 个 JSON | `b3_replay_local_20260906_011204.json`、`crosscheck_stage2_sim_consumer_*.json`（合成信号 α 峰 10.01 / 9.99 Hz）、`local_20260905_162636.npz`（`experiment_tag=bled112regress`） |

**关键风险**：模拟器数据 **S09/S11 与真实数据形式上完全无法区分**——同样是 4 通道 `<f8` npz、`meta.sfreq=256`、`channels=[TP9,AF7,AF8,TP10]`、有 device_info/report/qc，且 `qc.json` 里 4 个通道全部标 `"ok"`。唯一的区分依据是 `session_note.txt` 里的一段中文散文。**若下游按 `status != quarantined` 或按 `channel_quality == ok` 取数，S09/S11 会被当成真实样本。**

### 7.4 标注 / 受试者信息 / 同意书

| 项 | 状态 |
|---|---|
| **`05_annotation/` 内容** | **仅 `README.md`（510 字节），0 个子目录、0 个标注文件** |
| 全库标注文件（`*annotation*` / `*label*` / `*标注*`） | 只命中 `00_governance\入定状态标注规范_V1_初稿.md`（**规范本身**，非标注数据） |
| 规范要求的 6 类标注文件（`annotation_self.md` / `annotation_operator.md` / `annotation_master_A.md` / `annotation_master_B.md` / `annotation_arbitration.md` / `quality_ref.txt`） | **0/6 类、0/12 会话** |
| 唯一的「类标注」信息 | 暂存区 5 个 npz 的 `meta.zx_phase`：`[入]` / `[入,照]` / `[入,照,运]`。**该字段不在任何字典版本中定义、不在 `05_annotation`、不在版本控制内、只存在于无治理的暂存区** |
| `meta.labels`（manifest 字段） | 12 份回归骨架 manifest 全部为 `"labels": []` |
| 受试者登记 | 2 行（P001 发起人 / P002 导师A）；**P002 无档案目录、无同意书、无会话** |
| **同意书记录** | **仅 P001**：`01_registry\P001\consent_v1.pdf`(178,205 B, 2026-08-23)、`consent_v1.1.docx`(14,882 B, 2026-08-31)、`profile.md` 记有版本与升版日期 |
| **会话级同意书绑定** | **0/12**。12 份 `session_manifest.json` 的 `consent_version` 字段**全部为字符串 `"缺失（回填，采集端未记录）"`** |
| 人口学 / 练习史 / 睡眠 / 出坡等协变量 | **无任何结构化记录**；`session_note.txt` 的 `pre_state` / `post_state` 为自由文本，且 **9/12 两个字段都是「unknown（补登记，未当场记录）」**（仅 S05、S06、S07 有真实内容） |
| `contact_quality` 记录 | `session_note.txt` 中 **10/12 为 unknown**（S07=medium, S12=good 例外）；**但同一会话的 npz `meta.contact_quality` 8/12 写作 `good`** —— 两处直接冲突（见 7.5） |

### 7.5 跨文件元数据自相矛盾清单

| 会话 | `session_registry.csv` session_type | npz `meta.session_type` | 冲突 |
|---|---|---|---|
| S08 | `baseline` | **`custom`** | **直接冲突** |
| S02–S06 | 有值 | **字段不存在** | 无法交叉校验（5 条） |
| S11 | `test` | 字段不存在（只有 `experiment_tag=closedloop`、`scene=closedloop`） | 无法交叉校验 |

| 会话 | `session_note.txt` contact_quality | npz `meta.contact_quality` | 冲突 |
|---|---|---|---|
| S02, S03, S04, S05, S06 | unknown（补登记/待补记） | 字段不存在 | — |
| S07 | **medium** | **good** | **冲突** |
| S08 | **unknown（补登记）** | **good** | **冲突** |
| S09, S10, S11 | **unknown（补登记）** | **good** | **冲突** |
| S12 | good | good | 一致 |
| S13 | **unknown（补登记）** | **good** | **冲突** |

→ **8 个含 `meta.contact_quality` 的会话中，5 个与 session_note 冲突**；另有 S08 的 `pre_state`（note=unknown vs meta=良好）、S12/S13 的 `pre_state`（note=unknown vs meta=空）同样不一致。

`device_info.json` 字段集也不统一：S02–S06 为 **11 字段**，S07–S13 为 **13 字段**（多 `scene`、`quarantined`）；12/12 全部**缺少** `ingest_session.py:269-273` 已实现的 `signal_chain`（除 S13）、`pre_filter_archived`、`contract_carried` —— 说明这 12 个包由**至少 3 个不同版本的入库脚本**产出。

---

## 8. 版本控制覆盖

| 检查项 | 实测结果 |
|---|---|
| `D:\Project\Zen-EEG` 是否 git 仓库 | **否**。`Test-Path .git` → `False`；全树递归搜索 `.git` 目录 → **0 个** |
| 是否有 `.gitignore` / `.gitattributes` | **否**（根目录无任何 `.git*` 文件） |
| 是否被工作区仓库覆盖 | **否**。工作区仓库根为 `D:/Project/zhiguanAI`（`git rev-parse --show-toplevel` 实测输出），而 `D:\Project\Zen-EEG` **不在该路径前缀之下**（`.StartsWith("D:\Project\zhiguanAI\")` → `False`），是同级目录，**物理上不可能被跟踪** |
| `.gitignore` 是否排除了这类数据 | 是（第 44 行 `*.npz`、第 73 行 `Zen-EEG/`）。即使把 Zen-EEG 移入工作区，`.gitignore` 仍会排除 `Zen-EEG/`、`*.npz`、`*.npy`、`*.bin`、`*.json`、`*.html`、`*.ps1`、`*.bat` |
| **未受版本控制的数据量** | **169,150,802 字节（161.31 MB）/ 97 个文件**，其中原始脑电 **151,229,383 字节** |
| 备份策略证据（`.bak` / snapshot / `.old` / `.orig` / `~`） | **全树仅 1 个**：`01_registry\session_registry.csv.bak-20260919`（**853 字节**）。**0 个快照目录、0 个 `.old`/`.orig`/`~` 文件** |
| 备份覆盖率 | 唯一被备份的是 **853 字节的登记表**；**151 MB 原始脑电 + 17 MB 质控数据 + 8 份治理文档零备份** |
| 校验和 / 完整性清单 | 无。全树无 `*.sha256`、`*.md5`、`checksums*`、`MANIFEST*` 等完整性清单文件 |

### 8.1 「raw 不可变」铁律已被实际违反（时间戳证据）

`README.md`「三条铁律」第 2 条、`02_raw/README.md`、`Collection_SOP_V0.2.md` Step 6、字典 V1.2 §3.1 均声明：**`02_raw` 落盘后任何人、任何工具不得修改、重命名、删除**。

实测文件系统证据：

| 修改时间 | 文件 | 位置 |
|---|---|---|
| **2026-09-19 04:17:01** | `session_manifest.json`（8 个，645/652/1075 字节） | **`02_raw/<sid>/`** |
| **2026-09-19 04:17:01** | `session_manifest.json`（4 个，652/655 字节） | **`03_quality_control/quarantine/<sid>/`** |
| **2026-09-19 04:17:01** | `session_registry.csv`（1,572 B）、`session_registry.csv.bak-20260919`（853 B） | `01_registry/` |

**12 个 manifest 与登记表在同 1 秒内被写入**，且 manifest 内容自称「历史会话回填骨架（2026-09-19 裁定 P1§八-8）」。这是**对声明为只读区的 02_raw 的事后写入**，全库 02_raw 内最新的其余文件止于 2026-09-11 23:33:33。

---

## 9. 最严重的 10 个数据管理问题（按风险排序）

| # | 问题 | 风险 | 证据路径 |
|---|---|---|---|
| **1** | **整个数据工厂零版本控制、零备份。** 161.31 MB / 97 文件（含 151.23 MB 原始脑电）既不在任何 git 仓库内（`D:\Project\Zen-EEG` 是 `D:\Project\zhiguanAI` 的同级目录，物理上无法被该仓库跟踪，自身也无 `.git`），也**只有一个 853 字节的 CSV 备份**，无快照、无校验和。任一磁盘故障即永久失去全部研究数据。 | **致命** | `D:\Project\Zen-EEG\.git` 不存在；`D:\Project\Zen-EEG\02_raw\`（151,229,383 B）；`D:\Project\zhiguanAI\.gitignore:44,73`；`D:\Project\Zen-EEG\01_registry\session_registry.csv.bak-20260919`(853 B) |
| **2** | **模拟器/合成数据与真人数据在物理与格式上不可区分。** S09、S11 是 `MonitorSimulator` 合成信号，但具备与真实会话完全相同的 npz 结构、4 通道、256 Hz、device_info、report.html，且 `qc.json` 4 通道全部 `"ok"`。唯一标识是 session_note 里的一段中文说明。真实链路录制 S11 甚至被同时登记为 `session_type=test`。 | **致命（研究结论可被污染）** | `D:\Project\Zen-EEG\03_quality_control\quarantine\ZEN-20260905-P001-S09\session_note.txt:12`；`...\ZEN-20260905-P001-S11\session_note.txt:12`；`...\ZEN-20260905-P001-S09\qc.json`（`channel_quality` 全 ok） |
| **3** | **`meta.timestamp` 实为「结束时刻」，却被当作「开始时刻」使用**，导致 12/12 `device_info.json` 的 `collection_start_utc` 全部错标为结束时间（字典 §3.2 定义为采集开始）；S08 错标 60 分 31 秒。 | **严重** | 字典 `00_governance\ZEN_EEG_Data_Dictionary_V1_2.md:109`；`ingest_session.py:200-201,251`；`02_raw\ZEN-20260905-P001-S08\device_info.json`(`11:21:47Z`) vs 实测首样本 `10:21:16Z` |
| **4** | **S05/S06 的纪元时间轴被整体后移一个完整会话时长**（316.2 s / 704.5 s），因为归一化锚点用了上述错误的「开始时刻」。任何跨会话对齐、事件时序、睡眠/昼夜分析都会系统性偏移。 | **严重** | 实测 gap−duration = −316.2 s / −704.5 s；`02_raw\ZEN-20260831-P001-S05\session_note.txt:9`（`timestamps_epoch_normalized: from_relative`）；`ingest_session.py:213-216` |
| **5** | **S02/S03/S04 的 timestamps 是 `arange(n)/256` 合成的，不含任何真实到达时刻。** 三个源 npz 根本没有 `timestamps` 键。字典把该字段的存在理由写明为「定位蓝牙丢包与跨会话对齐」——这三条数据在此用途上完全失效，但字段名与结构看起来完全正常。 | **严重** | 暂存区 `local_20260830_183343/183719/202946.npz`（keys = `eeg+meta`，无 timestamps）；`02_raw\ZEN-20260830-P001-S02\session_note.txt:8`（`timestamps_backfilled: linear_interpolation`）；归档 `timestamps[0]=0.0` |
| **6** | **846 MB 暂存区完全无治理，90/102 个 npz 未登记，并与归档区字节级重复。** 目录扁平、无 README、无版本标记、无保留策略；`ingest_session.py:234` 用 `shutil.copy2` 复制而非移动，使源文件永久滞留。6 个会话的 npz 与归档副本 **MD5 完全相同**（重复 54.19 MB）；2 组同录制文件被重复保存（180252 行/704.970992088318 s；533180 行）。 | **严重** | `D:\Project\zhiguanAI\muse2-repo\muse2-master\report\`（223 文件 / 900,635,013 B）；MD5 对比：S08/S12/S07/S09/S10/S11；`ingest_session.py:234` |
| **7** | **归档数据的字段与文件结构大面积不受字典约束，「字典先行」铁律实质失效。** 归档区内部存在 **5 套不同的 meta schema**，7/12 的 npz 携带 6–8 个字典从未定义的键；`session_registry.csv` 多出未定义的 `manifest_path` 列；`session_manifest.json` 整个文件类型（12 个）在字典中不存在；`session_note.txt` 有 3 套字段集（9/10/12–13 键）。 | **高** | 字典 `ZEN_EEG_Data_Dictionary_V1_2.md`（§2 六列、§3.1 五键）；`01_registry\session_registry.csv`（7 列）；`02_raw\*\session_manifest.json`；`02_raw\*\session_note.txt` |
| **8** | **raw 只读铁律被实际打破，且无审计追踪。** 2026-09-19 04:17:01 同一秒内向 12 个「只读」会话目录写入 `session_manifest.json` 并改写登记表，目录内其余文件最新止于 2026-09-11。由于无版本控制（问题 1），被改写前的原始状态**不可恢复**。 | **高** | `02_raw\*\session_manifest.json`(mtime 2026-09-19 04:17:01，共 8 个)；`03_quality_control\quarantine\*\session_manifest.json`(同秒，共 4 个)；`README.md:13,24`；`02_raw\README.md:13` |
| **9** | **标注体系完全空白，唯一的专业标签游离在治理之外。** `05_annotation/` 只有 README，规范要求的 6 类标注文件 0 存在；12 份 manifest 的 `labels` 全为 `[]`。仅有的「入/照/运」标签以 `meta.zx_phase` 形式存在于 5 个暂存 npz 中——**未定义、未登记、不受版本控制、且随时可能被暂存区清理**。 | **高** | `D:\Project\Zen-EEG\05_annotation\`（仅 README.md 510 B）；`00_governance\入定状态标注规范_V1_初稿.md:106-114`；暂存区 `local_20260919_222226.npz`(`zx_phase=[入,照,运]`) |
| **10** | **同意书与会话无绑定，受试者协变量缺失，且唯一的训练级会话数据在归档时丢失了滤波前原始波形。** 12/12 manifest 的 `consent_version` 为 `"缺失（回填，采集端未记录）"`；9/12 会话的 `pre_state`/`post_state` 为 unknown；`contact_quality` 在 session_note 与 npz meta 之间 5/8 冲突；S08 的 `session_type` 在登记表（baseline）与数据（custom）之间冲突；S13 的源文件含 `eeg_pre_filter` 而归档副本丢失（47,996,647 B vs 源 86,393,003 B），归档区 `eeg_pre_filter` 覆盖率 0/12。 | **高** | `02_raw\*\session_manifest.json`(`consent_version`)；`02_raw\ZEN-20260911-P001-S13\eeg_raw.npz` vs 暂存区 `local_20260911_232300.npz`；`01_registry\session_registry.csv`(S08=baseline) vs `02_raw\ZEN-20260905-P001-S08\eeg_raw.npz`(meta `session_type=custom`) |

---

## 附录 A：审计脚本与原始输出（均在 `D:\Project\zhiguanAI\_analysis_tmp\`）

| 文件 | 说明 |
|---|---|
| `npz_probe.ps1` | .NET `.npy` 头解析 + zip 成员读取 |
| `pickle_vm.ps1` | PowerShell pickle 虚拟机（还原 numpy 0-d object 数组形式的 `meta`） |
| `scan_all_npz.ps1` | 114 个 npz 全量扫描主脚本 |
| `npz_rows.xml` / `npz_rows.csv` | 逐个 npz 的 keys / shape / dtype / meta 全字段结构化结果 |
| `npz_scan.txt` | 首次 Python 方案的输出目录（该方案因沙箱拒绝执行 Python 而放弃） |
| `audit_npz.py` | 原定 Python 脚本（**未能执行**，仅留存） |

## 附录 B：未修改声明

本次审计对 `D:\Project\Zen-EEG` 与 `D:\Project\zhiguanAI\muse2-repo` **全程只读**（`Get-ChildItem` / `Get-Content` / `Get-FileHash` / `ZipFile.OpenRead` / `Select-String`）。所有新写入仅发生在 `D:\Project\zhiguanAI\_analysis_tmp\`。
