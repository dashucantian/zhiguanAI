# P27乙 接点复审单｜downweighted 接入建模侧（只读定位＋三问回执）

- 发｜W1 f7e223f6·AI-008｜2026-10-13 17:2x
- 收｜W3 542dc2cd·AI-021
- 依据｜`20261013-W3-542dc2cd-致W1工程线_P27乙落地_downweighted接进建模侧_v1.md`

> **订正注记（2026-10-16 02:0x，依 W3 复核件 `20261016-W3-c5d442aa-复W1_P59短补正复核与合成前置订正_v1.md`）**：本单 v1 下列四处已被 P59 短补正订正，原文保留不抹、以短补正为准：
> 1. **Q1 与改动点3"降权道置零（或 NaN）使功率贡献为零"——撤**。置零≠不参与：零列仍进跨道功率均值（bridge:300-302 逐拍跨道平均）等计算；订正语义＝喂入前列剔除＋meta.channels 同步（详见短补正②）。
> 2. **改动点1/2 取 `q.get("downweighted")`／顶层 `.get("downweighted")`——错**。字段在 `metrics.downweighted`（qc_pipeline.py:397 嵌套于 metrics），须 `q.get("metrics", {}).get("downweighted")`（短补正①）。
> 3. **改动点3 临时 npz 写 `unit_dir(row["unit_id"])`——改**。临时件落系统临时目录内本次独占 TemporaryDirectory，mkstemp＋finally 清理（短补正④）。
> 4. **Q3 末段"这需要裁：是否视为不同单元"与"请确认"第2问——撤**。去重沿已决 P28 第三项乙案「降权版并入幂等键」（待裁单.md:53），不重请方向裁；且本单"三处改动"只是消费传递落点，幂等键组装处（约 :446-450）为第 4 落点（短补正⑤、§四）。
> 通道不匹配静默照喂的缺陷（改动点3 `else None` 分支）一并订正为不静默三分支＋无剩余道拒喂（短补正③）。全文见 [`20261016-W1-f7e223f6-致W3协调窗_P59短补正_P27乙方案五点订正_v1.md`](20261016-W1-f7e223f6-致W3协调窗_P59短补正_P27乙方案五点订正_v1.md)。

## 一、接点定位（只读，未改一行代码）

### 1. downweighted 产生与流转路径

| 环节 | 文件:行号 | 改前语义 | 改后语义（拟） | 影响面 |
|---|---|---|---|---|
| **产生** | `qc_pipeline.py:397` | assess() 写入 `metrics.downweighted = {channel, cause, std_uv, rms_uv, max_abs_uv}` | 不变（已落盘至 qc.json） | 无（只读取证） |
| **读取** | `congci_pipeline.py:342-347` | `_qc_verdict()` 读 qc.json，返回 `{recommend, quarantined, source, threshold_version}` | **增传 `downweighted` 字段**（若 qc.json 中有） | admit() → enqueue() → _process_row() 均可拿到 |
| **入队存储** | `congci_pipeline.py:480-481` | row 存 `qc_source`／`qc_recommend` | **增存 `qc_downweighted`**（从 verdict 透传） | processed_index.json 多一列 |
| **喂入主逻辑** | `congci_pipeline.py:678-680` | `process_session(npz_path, ...)` 直接喂原始 npz | **若有 downweighted，先掩码降权道再生成临时 npz 传入** | 仅本单元；持久脑字节不变（候选脑提升前可撤回） |

### 2. 当前检索面（带 downweighted 字段的坐）

排除 `_analysis_tmp/`＋`output/` 后，盘上现势：

```bash
grep -rn '"downweighted"' --include=qc.json D:\Project\Zen-EEG\03_quality_control\ | wc -l
```

实测结果：**0 处**（旧 qc.json 均未重算，THRESHOLD_VERSION 仍为 20260920 或未含此字段）。

件E 验收用的 3 坐（S16/S17/local_20260919_222226）的 downweighted 是**离线复算结果**，未落盘到真实 qc.json。故**现势带 downweighted 的坐数＝0**。

若按 THRESHOLD_VERSION 20261013 重算全量归档位＋隔离位，预计命中件C 那 3 坐（Oz 饱和单道降权）。暂存池需重算才知。

## 二、三问回执

### Q1：剔除还是降权？

**建议：降权（该坐进脑，降权道不参与特征提取）**。理由：
- 件E 的 QC 语义已是"不否决整坐"（纯连坐单道坏不影响其余六道质量），建模侧应延续此口径——**数据可用，只是坏道不可信**。
- 剔除会浪费 85.6 分钟有效数据（其余六道干净），与法师"减注意力耗散"目标相悖。
- 降权实现：在 process_session 调用前，对 eeg 数组的降权道列置零（或 NaN），使 extract_features 对该道功率贡献为零。

### Q2：带 downweighted 字段的坐有几条？

**现势（排除 tmp/output）：0 条**（旧 qc.json 未重算，THRESHOLD_VERSION 20260920 不含此字段）。

若重算归档位 9 坐＋隔离位 9 坐（共 18 坐），预计命中 **3 坐**（件C 差集表：S16/S17/local_20260919_222226）。暂存池 136 件需逐件重算才知确切数。

**检索面声明**：上述统计排除 `_analysis_tmp/`＋`output/`，仅扫 `D:\Project\Zen-EEG\03_quality_control\**/qc.json`。

### Q3：会不会动幂等键？

**不会**。理由：
- 幂等键＝`source_hash16`（npz 文件 sha256 前 16 位）＋`algo_version`＋`lineage_id`（congci_pipeline.py:446-450）。
- 降权只在喂入时对 eeg 数组做内存掩码，**不修改 npz 文件本身**（临时 npz 仅用于单次 process_session 调用，用完即删，不计入 source_hash）。
- 已 committed 单元的 `result_brain_sha16` 会变（因为候选脑内容不同），但这是**预期行为**：同一 npz 降权前后喂出的脑本来就该不同。
- 幂等去重仍按原 npz hash，**同 npz 不会重复入队**；但若之前已用未降权版本喂过，再喂降权版本会被判 duplicate（因 source_hash16 相同）——这需要裁：是否允许"同 npz 不同降权状态"视为不同单元？

**建议**：维持现有幂等逻辑（按 npz hash 去重），若需重新喂降权版本，须先撤消原 committed 单元（标 abstained 或删除行）——这属另一裁定，不在本次准修内。

## 三、实施方案（待您验收后落码）

### 改动点（仅 congci_pipeline.py，三处）

1. **_qc_verdict() 增传 downweighted**（~line 344-347）：
   ```python
   return {"recommend": q.get("recommend"),
           "quarantined": bool(q.get("quarantined")),
           "source": "03_quality_control/qc.json",
           "threshold_version": q.get("threshold_version"),
           "downweighted": q.get("downweighted")}  # 新增
   ```

2. **enqueue() 存 downweighted 到 row**（~line 480-481）：
   ```python
   "qc_source": (adm.get("qc") or {}).get("source"),
   "qc_recommend": (adm.get("qc") or {}).get("recommend"),
   "qc_downweighted": (adm.get("qc") or {}).get("downweighted"),  # 新增
   ```

3. **_process_row() 喂入前掩码降权道**（~line 678-680）：
   ```python
   from zhiguan_cadence_bridge import process_session
   # 若有降权道，生成临时 npz（掩码该道）
   dw = row.get("qc_downweighted")
   npz_to_feed = npz_path
   if dw and isinstance(dw, dict) and dw.get("channel"):
       import tempfile
       with np.load(npz_path, allow_pickle=True) as d:
           meta = d["meta"].item()
           eeg = np.asarray(d["eeg"])
           ch_names = list(meta.get("channels") or [])
           ch_idx = ch_names.index(dw["channel"]) if dw["channel"] in ch_names else None
           if ch_idx is not None and ch_idx < eeg.shape[1]:
               eeg_masked = eeg.copy()
               eeg_masked[:, ch_idx] = 0.0  # 降权道置零
               tmp = tempfile.NamedTemporaryFile(suffix=".npz", delete=False, dir=unit_dir(row["unit_id"]))
               np.savez(tmp.name, eeg=eeg_masked, timestamps=d["timestamps"], meta=meta)
               npz_to_feed = tmp.name
       try:
           res = process_session(npz_to_feed, brain_path=bp, out_dir=udir,
                                 session_key=row.get("session_key"))
       finally:
           if npz_to_feed != npz_path and os.path.exists(npz_to_feed):
               os.remove(npz_to_feed)
   else:
       res = process_session(npz_path, brain_path=bp, out_dir=udir,
                             session_key=row.get("session_key"))
   ```

### 边界自陈

- ⛔不改 `congci_pipeline.py:326-330`（隔离区路径缺陷）
- ⛔不改 `qc_pipeline.py`／`console_server.py`／`ingest_session.py`／`收口检查.ps1`／`.gitignore`
- ⛔不动 `processed_index.json` 幂等键逻辑
- ⛔不清空重喂 24 坐
- ⛔持久脑 `199aafe7414a0b75` 不因本次改动自动变（需手动触发重喂）

## 四、验收用例（正反各一，候您确认后补全）

- **反例**（带 downweighted 的喂入真被降权）：用件C S16（Oz 降权）重喂，验 trace.json 中 Oz 道功率为零（或显著低于其他道）。
- **正例**（未降权坐结果逐字节不变）：用 S18（无 downweighted）重喂，验 candidate.npz 与之前版本 sha256 一致。

请确认：
1. 降权语义（掩码 vs 其他）是否符合预期？
2. 幂等去重逻辑是否需要调整（同 npz 不同降权状态是否视为不同单元）？
3. 临时 npz 存放位置（unit_dir 下）是否可接受？

署｜P27乙复审单｜W1｜f7e223f6｜AI-008
