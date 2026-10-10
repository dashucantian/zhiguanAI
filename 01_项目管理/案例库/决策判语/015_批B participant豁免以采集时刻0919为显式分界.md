# 判语 015：批 B 的 participant 豁免以「采集时刻 2026-09-19」为显式分界，档位结论不变但理由必须换

> 〔取号留证〕入档前实测 `ls 01_项目管理/案例库/决策判语/`，现势末号＝**014**（本窗同轮所建），001–014 连续无缺号 ⇒ 按规约 §二.5「编号先查后取」取 **015**。
>
> 判决日期：2026-10-10 ｜ 状态：**已定**（宗国法师 2026-10-10 亲裁「判据一条（非您裁不可）：同意建议。」）｜ 立卡：AI-014（W3 协调窗）依法师同日常设派工
> 影响范围：从此线批 B（准入事务只读设计与写方清单）／participant 归属判据／数据豁免条款的写法

## 判决

批 B 契约的 participant 豁免档位，**以「采集时刻 2026-09-19」作一条显式分界写进契约**，且该分界**只管暂存区**：

- **归档位（`02_raw/`）**：**自入库起就有源**，与 0919 无关——`session_manifest.json` **9/9 在场、全 `P001`**，最早一件属 `ZEN-20260830-P001-S02`（**远早于 0919**），连晚于分界的 S18（`20261006`）也有源。**0919 分界不适用于归档位。**
- **暂存位·0919 之前采集**：无配对 manifest，**天然无源**，豁免成立（实测 **13 坐**，采集于 0831–0911）。
- **暂存位·0919 及以后采集**：**有配对件、有源可读**（实测 **2 坐**，其中 1 坐 `P001`、1 坐空串），字段值为空串即属**写侧缺陷**，不得一并豁免。

⇒ **精确表述（契约 §1.3 采此）**：**0919 只决定「暂存位有无配对 manifest」；判据表的"无源"档必须按分区（zone）定，时间只决定暂存区内有无配对件。**

⚠**关键限定：档位结论不变，但理由必须换。** 旧理由「暂存期本就无归属」已作废；若继续照它施工，会把 0919 之后那些**有归属可读**的新暂存坐一起豁免掉，从而把一个真实的写侧缺陷藏进一条看似合理的通则里。

> 〔2026-10-10 13:5x 订正注记｜W3·AI-014｜**本卡首稿有错，W1·AI-019 抓到**〕首稿把分界写成**跨全区的时间轴**（"0919 之前采集的会话——归属源尚不存在"）。**这句对归档位是假的**：归档位 9 坐全有 manifest，最早的采集于 **2026-08-30**，远早于 0919。照字面画档位表，会把这 **9 坐有源的归档坐一起豁免掉**——**与本判决要防的那个错完全同型，只是方向相反**（旧理由误伤 0919 **后**的暂存坐，字面新理由误伤 0919 **前**的归档坐）。W1 的定性一针见血：**两次都是"拿一个轴当总管"。** 现按 zone 限定改写如上。**这条订正与本卡同批入库、不回改首稿措辞以外的任何裁定内容——法师裁的是"要有显式分界"，分界的管辖范围属实测事实，不在裁定文本里。**

## 依据（可核验的数字）

- **manifest 存在硬起点（暂存区）**：`report/` 目录 npz **135** 件、manifest **33** 件；manifest 时间跨度 **最早 `local_20260919_050129`**／最晚 `20261006_203610`，而 npz 跨度最早 **`20260830_183343`**。⇒ 起点差 **20 天**，不是采样稀疏。
- **逐坐配对**：**13 坐无任一 manifest 引用**＋2 坐命中；存在性直测三例坐实（`local_20260831_164447` **absent**／`local_20260928_131637` **EXISTS**／`local_20260928_174054` **EXISTS**）。那 13 坐采集于 **0831–0911**，全部早于 0919。
- **「有该字段」≠「有值」**：33 件 manifest 的 `participant_id` 值分布＝`{'P001': 21, '': 12}` ⇒ 填充率 **63.6%**。空串与「根本没发」在文件里**仍不可区分**——与 `console_server.py:1860` 的 `payload.participant or ""` 同一个病，只是这次病在写侧。
- **归档位另有源（订正注记的证据）**：`02_raw/<sid>/session_manifest.json` **9/9 在场、全 `P001`**；逐坐归属**四源俱在**（`session_key` 第三段／`session_registry.csv`／`registry_tx.preregister_locked:251`／manifest）。
- **⭐两轴不等价（W1 §3.1 实测）**：按**采集时刻**重切 24 坐 ＝ **21 早于／3 及以后**；而 **13／15** 那两个数属 **`qc_source` 轴**。⇒ **时间轴与来源轴不是同一条**，档位表若混用即错。分区×分界交叉表：归档位 9 全有值／暂存位早于 0919 者 13 全无 manifest／暂存位 0919 及以后者 2（1 有值＋1 空串）。
- **⭐「通过 4」是乙案假想值，现势真值＝9（W1 §3.2 实测）**：归档位 9 坐 `admit()` **全 True／拦 0／不可测 0**。旧「4」的来历查清＝`quarantined` **键齐只有 4 坐**（S08/S12/S13/S18 显式 `False`），另 **5 坐键缺**（S02–S06＝`None`）；旧「4」是**乙案（缺键即 unknown 拒喂）口径下的假想值**，而法师 10-09 已裁**甲案**（`sha=None` 记 unknown 但**不作拒喂条件**）⇒ 缺键 5 坐不拒 ⇒ **现势＝9**。
- **据此档位表由四档改五档**：**A 通过 4（键齐）／B 缺键豁免 5／C 无定稿豁免 13／D 隔离位 8（拒）／E 新增「有源未采」2**。**E 档的存在意义就是让"旧理由误伤"变成一个可红反例**——把它单列，下次谁再用一个轴当总管，E 档立刻报警。
- **一条让跳1 变便宜的现发现（W1 §四）**：`session_registry.csv` 有 **`manifest_path` 列，17/18 已填且全部可解析**（唯一空值＝`ZEN-20260825-P001-S01`）⇒ 台账里**早就有指向 manifest 的活指针**，跳1 不需新读目录。⚠**该列存的是相对 `zen_root` 的相对路径**：`os.path.exists(原值)` 会**全 False**，必须 `os.path.join(_CFG["zen_root"], manifest_path)`（实测 join 后 **17/17 存在**）。
- **归因另案（勿混记）**：participant 全空的真因不在 enqueue——两处 enqueue **都传了**（`console_server.py:699-705`／`:1152-1158`），断在上一跳（`payload.participant or ""` 零校验零回落，而同文件 `:2606`／`:2650` 有 `P\d{3}`＋400 校验）；且 `default_participant='P001'` 采集链从不读。
- **隐私硬约束**：`participant_registry.csv` 含 **`nickname` 列（真人姓名）** ⇒ 契约 §四 已立：**日志／回执／契约一律不复制该列值，只报 `participant_id` 代号。**
- 出处：W1·AI-019 `信箱/engine/20261010-W1-AI019-致W3_②④复核与manifest更正_v1.md` §3.1–3.2、`…_致W3_批B契约出稿与两处现势更正_v1.md` §二–§四；契约正本 `01_项目管理/20261010_W1_批B施工契约_v1.md`（21,980 B／九节）；协调正本 §31.7、§32.3。

## 被否方案

- **甲｜沿用旧理由「暂存期本就无归属」**：会把 0919 之后的有源坐一起豁免，掩盖写侧缺陷。**否——这是本判语要防的那一件事。**
- **乙｜按"版本"划豁免**（某 `THRESHOLD_VERSION` 之前一律豁免）：2026-10-09 对 **17 件**历史 `quarantined` 的普查已证**无版本分界**（归档位缺键 5／隔离位 8 全 True）⇒ **版本豁免条款结构上不可实现**。否。
- **丙｜不写分界，只写"无源者豁免"**：判据层留模糊，下一窗复算时无法判断某坐属哪一档，下次普查还得重查一遍。否。
- **丁｜把分界写成"manifest 文件是否存在"的运行时判断**：等价于把 0919 这个日期藏进代码，比写进契约更难核；且现存 13 坐本就 absent，判据与结论同义反复。**候另议**（若将来需要机器判定，正解是显式常量＋注释指向本判语）。

## 可复用教训

**豁免条款必须钉在可核验的物理量上，不能钉在"当时的理由"上。** 理由会随实测作废（本案例：一句"任何地方都没有逐坐归属"被一次配对实测推翻），而"采集时刻早于 2026-09-19"是一条谁都能复算的物理边界。

更普适的一条：**当一条豁免的理由被证伪、但结论仍然正确时，最危险的动作是"结论对就不改理由"**——旧理由的覆盖面通常比新理由**宽**，宽出来的那部分正是缺陷的藏身处（本案＝0919 之后 36.4% 的空串件）。

**⭐但换理由时还有第二道坑（本卡首稿就栽在这里）：新理由自己也可能有越界的覆盖面，而且方向常常与旧理由相反。** 旧理由误伤 0919 **之后**的暂存坐，字面新理由误伤 0919 **之前**的归档坐——**两次都是"拿一个轴当总管"**。正解是把管辖范围写死在条款里（本案：0919 **只管暂存区**，归档位另有源），并**为"被误伤的那一类"单列一个档位**（本案的 E 档「有源未采」），让它成为**可红反例**而不是沉默的受害者。

配套三条：**多个轴不可混用**（采集时刻轴 ≠ `qc_source` 轴，24 坐按前者切是 21／3、按后者是 13／15）；**旧数须查清来历再弃用**（"通过 4"是乙案假想值，甲案下真值＝9，不查来历就会把一个口径差当成现势值）；**表的原始出处是命令输出，不是转述**——凡文字与命令输出冲突，以命令输出为准（W1 契约 §1.3 口径，其首稿正是被自己的加法错造出一个假缺口）。

## 关联

- 批 B 正本：`01_项目管理/…/20261008_W1_批B准入事务只读设计与写方清单_v1.md`
- 前置普查：2026-10-09 历史 `quarantined` 17 件普查（无版本分界的证据源）
- 同源缺陷：`console_server.py:1860` `payload.participant or ""`（写侧）／`:2606`、`:2650`（有校验，形成对照）
- 坑卡：无（本条系判据裁定，非故障）；关联 JP-011（同轮我另一处归因错误）
- 入库笔：批 C `0b11650`（②④ 正修，7 件）；批 B 契约稿候出
- 对话来源：法师 2026-10-10「判据一条（非您裁不可）：同意建议。」

---

## English Summary

**Decision:** Batch B's contract draws an explicit boundary at **collection time 2026-09-19** for the participant-attribution exemption — and that boundary **governs the staging zone only**. Archived sessions (`02_raw/`) have had a source since ingest (9/9 carry `session_manifest.json`, all `P001`, the earliest belonging to `ZEN-20260830-P001-S02`, well before 0919), so the boundary does not apply to them. Staged sessions collected **before** 0919 have no paired manifest at all (13 sessions, collected 08-31 to 09-11) — exemption stands. Staged sessions collected **on/after** 0919 *do* have a readable source (2 sessions: one `P001`, one empty string), so an empty `participant_id` is a **write-side defect** and must not be swept into the same exemption. **The tier conclusion is unchanged; only the reason changes** — and changing the reason is the whole point.

> *Correction note: this card's first draft stated the boundary as a global time axis ("sessions collected before 0919 have no attribution source"). That is false for the archived zone and, applied literally, would have exempted 9 archived sessions that do have a source — the exact error the ruling exists to prevent, only pointing the other way. W1·AI-019 caught it. Both errors are the same shape: **treating one axis as the master axis**.*

**Evidence:** In `report/`, 135 npz vs 33 manifests; manifest span starts `local_20260919_050129` while npz span starts `20260830_183343` — a 20-day gap, not sparse sampling. Per-session pairing: 13 sessions have no manifest reference; existence probes confirm it. Of the 33 manifests, `participant_id` distribution is `{'P001': 21, '': 12}` → **63.6% fill rate**; empty string remains indistinguishable from "never sent," the same defect as `console_server.py:1860`'s `payload.participant or ""`, only on the write side. **Two axes are not equivalent**: splitting the 24 fed sessions by *collection time* gives 21 before / 3 on-or-after, whereas 13/15 belongs to the *`qc_source`* axis. **"Passing = 4" was a hypothetical value under the rejected 乙 option** (missing key ⇒ unknown ⇒ refuse); under the ruled 甲 option (missing key recorded as unknown but *not* a refusal condition) the current truth is **9** — 4 sessions have an explicit `quarantined` key, 5 have it absent. The tier table therefore goes from four tiers to **five**: A pass 4 (key present) / B key-absent exempt 5 / C no-finalized exempt 13 / D quarantine 8 (refuse) / **E new "has source, not collected" 2** — tier E exists precisely so that "the old reason over-reaches" becomes a *detectable counterexample*. Also: `session_registry.csv` already carries a live `manifest_path` pointer (17/18 filled), but the values are **relative to `zen_root`**, so `os.path.exists(raw)` returns all-False and must be joined first (17/17 exist after join).

**Rejected alternatives:** keeping the old reason ("staged sessions simply have no attribution") — it exempts post-0919 sessions that *do* have a source, hiding a real defect; version-based exemption — a 17-record historical `quarantined` census on 2026-10-09 proved **no version boundary exists**, making the clause structurally unimplementable; writing no boundary at all — leaves the criterion ambiguous for the next window; encoding the date as a runtime "does the manifest exist" check — hides the date in code and is tautological.

**Reusable lesson:** Exemption clauses must be pinned to a **verifiable physical quantity**, not to "the reason we believed at the time." And when a justification is disproven but the conclusion survives, the most dangerous move is leaving the reason alone — the old reason's coverage is usually *wider*, and that extra width is where defects hide. **But the replacement reason has a second trap: its own coverage can also over-reach, usually in the opposite direction.** The fix is to state the jurisdiction inside the clause (here: 0919 governs *staging only*) and to give the over-reached class **its own tier** (tier E) so it becomes a falsifiable counterexample rather than a silent victim. Supporting rules: never mix axes; trace an old number's provenance before discarding it ("4" was an option-dependent hypothetical, not a stale measurement); and treat **command output, not prose, as the table's source of truth**.
