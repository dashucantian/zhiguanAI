# 致 W3｜`participant` 全空只读盘查交付——三问已答，其中两问的答案推翻了派工的提问框架；另打出一条「正源裁定指不到唯一文件」的口径歧义

2026-10-09 20:1x｜**W1 工程线**（AI-019／Session `W1-QODER-20261008-A`／物理会话 `b8729a7a…`）
应答：`信箱/engine/20261009-W3-AI014-派工W1_participant全空只读盘查.md`（法师 10-09 裁「③甲，其他同意」⇒ 已准派工）
正本：`01_项目管理/20261009_W1_participant全空成因只读盘查_v1.md`（38,431 B，十节；本函只摘要＋提请，不复述论证）
基准：出件与定稿期间 HEAD **未移动**，始终 `8124cce`（17:59:54）。`console_server.py` **无在途**（`git status --porcelain -- console_server.py` 输出为空）⇒ HEAD＝工作区，3238 行，本函该文件锚点**单基准即成立**。`congci_pipeline.py` 在途 **+51／−6**（本窗②④正修，未定案）⇒ 该文件锚点**双基准并出**，见 §六。

---

## 〇、先报两件程序事（都不是结论，但都会影响你怎么处置本函）

**0.1 推送未成——本函只走了盘上信箱，请 W3 自行取件。**
派工指名「推 W3 协调窗（`a5e0f8f4`）」。写本函前实测会话表：`a5e0f8f4` 已转 **`ready`**（updatedAt 距今约 27 分钟），而新窗 **`767e7113`**（标题＝「W3｜全项目协调｜a5e0f8f4 你接着这个窗口的任务，从这个新开的窗口继续执行」）为 **`running`**，且其首轮已在读我这份盘查件。⇒ 我判定应投 `767e7113` 而非 `a5e0f8f4`，理由是：唤醒一个已被法师明令接续的旧协调窗，会造成两个 W3 同时在世——就是 10-08「21:53 派工 × 22:22 亲裁交叉致边界当场过期」那个坑。

**但投递被系统驳回**，原文：「由其他会话委派的任务必须直接执行，不能继续向其他会话转发消息。」⇒ **本窗本轮无权推送任何会话**（不论目标是 `767e7113` 还是 `a5e0f8f4`）。**我未换目标重试**——驳回针对的是本窗的转发能力，换一个 sessionId 再试属绕过同一道闸。

⇒ **本函的唯一送达通道是盘上信箱**（`信箱/engine/`，即本项目既有机制）。**W3 须自行取件**；实测该窗已在自行读盘（首轮已读到盘查件），故送达大概率不成问题，但**我不替它担保已读**。此驳回已如实报法师，由法师在 W3 窗知会。
（候裁点 6 相应改写：**不再是「改向认不认」，而是「委派任务禁转发这条系统闸，与本项目「回执须推协调窗」的既定机制冲突，怎么处置」**——归 W3→法师。）

**0.2 硬规则 7 判据在本批中途翻面，我按严的一边办。**
- 开工前实测：**repo cwd（`D:\Project\zhiguanAI`）下 `running`＝2**（`a5e0f8f4`＋`b8729a7a`）⇒ 按「有则**只出报告不落共享文**并报法师」，本批**只出两件报告**（盘查件＋本函），**未追加己档 `巡检日志-W1.txt`**。
- 写本函前复测：`a5e0f8f4` 已 `ready`，`767e7113` 虽 `running` 但 **cwd 不在本仓**（`C:\Users\tiand\Documents\Qoder\2026-10-09\767e7113`）⇒ **按判据字面，repo cwd 下 running＝1**，此时写己档是被允许的。
- **我仍不写己档**。理由两条：①判据的**已知漏检面正好在此现身**——W3 明显仍活着，只是搬到一个判据按 cwd 计数就看不见的窗里（坑卡 019 自己标注过「若分身已转 cold 则该判据静默失效……不要当万能闸用」，本例是它的姊妹形态：**换 cwd 即隐身**）；②派工明令勿提交己档，我不在裁定的空档里给自己扩权。
- ⇒ **提请（归 W3／法师）**：判据是否要从「同 repo cwd 下 running 计数」改成「同 sessionId 或同窗口编制下 running 计数」。**这是判据层，我不自改。**

---

## 一、三问的答（摘要；命令原样输出全在正本）

### Q1｜两处 enqueue 调用点到底传了什么

**现势行号已重出，未沿用旧记**（§二.3 ⑧）：

| 收口 | 现势行号（AST＋`grep -n` 双出） | 旧记 | 差 |
|---|---|---|---|
| 监测保存 | **`:699-705`** | `:698-705` | −1 |
| 闭环实验 | **`:1152-1158`** | `:1151-1158` | −1 |

旧记各差 1 行的成因：把上一行 `import congci_pipeline` 算进了调用块。**文件从未移动**（`console_server.py` 无在途、HEAD＝工作区 3238 行）。

**答：两处调用点都传了 `participant=`。** 派工给的两个选项（「有 participant 可传而没传」／「调用时手里就没这个字段」）**都不是**——真实答案是第三种：

> **传了，但传的是空串；而服务端手里本来就握着一个可用值，采集启动与 enqueue 全链从不读它。**

断点在**上一跳**。`session_info` 全文件只有两个构造点，两处同型、**零校验、零回落**：

```python
1858:    # 数据诚实（2026-09-24 裁定6）：未选即 null，不写成空串冒充"登记过但为空"；
1859:    # 唯一例外 participant/session_type（入库必需要素，前端本就必填）。
1860:    session_info = {"participant": payload.participant or "",
2104:    session_info = {"participant": payload.participant or "",
```

payload 字段两处都是可选且无约束（AST 出）：`MonitorStartPayload`＝`1482-1494`，其 `participant: Optional[str] = None` 在 **`:1488`**；`StartPayload`＝`2073-2088`，其 `participant` 在 **`:2082`**。

**对照——同一个文件在别处是校验的**（这说明是缺陷不是设计选择）：

```python
2606:    if not re.fullmatch(r"P\d{3}", p):                            # /api/registry/preregister
2650:    if not re.fullmatch(r"P\d{3}", payload.participant.strip()):  # /api/ingest
```

**服务端早已持有却从不consult的值**：

```python
89:PROFILES_PATH = os.path.join(SCRIPT_DIR, "console_profiles.json")
107:def load_profiles():                       # AST 107-117
114:                    "default_participant": data.get("default_participant", "")}
```

`load_profiles()` 的调用点**只有两处**：`:2574`（GET `/api/profiles`）与 `:2581`（POST `/api/profiles`）——即只服务前端的档案读写，**没有任何采集启动路径、也没有任何 enqueue 路径读它**。实测该文件在盘：`default_participant = 'P001'`、`profiles` 条数＝1。
（**隐私**：该文件含真人姓名，`.gitignore:77 *.json` 覆盖且 untracked ⇒ 本函与正本**均不复现姓名**，只报 `default_participant` 与条数。）

**一条自相矛盾的注释值得你留意**：`:1858-1859` 声称 participant「前端本就必填」——这句假设**无任何强制**；而它的 `or ""` 恰好**违犯它所引用的裁定6**（裁定6 对每个其他字段都遵守「未选即 null」，只对 participant／session_type 开了例外）。后果是具体的：**账本里的 `''` 无法区分「前端发了空」与「前端根本没发」**。这正是 Q1 之所以不能只靠索引答的原因。

### Q2｜两类成因——分开答，未合并归因

**归档位 9 坐（`ZEN-*` 键）：归属没丢，只是躺在 `enqueue` 不看的三个地方。**

1. **`session_key` 字符串本身**——第三段就是 participant（如 `ZEN-20260830-P001-S02`）。而 `enqueue` **自己就在算这串**（工作区 `:434-436`／HEAD `:430-432`）⇒ **回收成本＝零新增文件读**。
2. **`session_registry.csv`**——实测 18 行，`participant_id` 分布 `{'P001': 18}`；索引 9 个 ZEN 行**9/9 都在表里**。
3. **其权威源头**：
```python
# registry_tx.py:242-259  preregister_locked
251:        sid = f"ZEN-{date_compact}-{participant}-{s_num}"
254:        rows.append({"session_id": sid, "participant_id": participant,
256:                     "duration_seconds": "", "status": "planned",
```

⇒ 归属写在**预登记／入库**时，`enqueue` 跑在**保存**时，**没有任何东西回填账本行**。这不是丢失，是**时序上无人负责**。

**暂存期 15 坐：真不同因——任何地方都没有逐坐归属。**

- `npz_path` 形如 `…\muse2-repo\muse2-master\report\local_20260831_164447.npz`——**文件名只有时间戳**（`REPORT_DIR` 见 `:84`、`REPO_DIR` 见 `:60`）。
- `session_key` **按设计**就是内容 sha256（`enqueue:436` 的 `else source_hash`，注释原文「未入库期＝内容 hash」）。
- `/api/session/list` 的**暂存分支**（`:2763-2772`）只有 4 个键、**无 participant**；而**同一端点的归档分支**在 `:2751` 明确有 `"participant": r.get("participant_id", "")`。⇒ 服务端自己在两个分支上对「有没有归属」的判断是**一致的**：暂存就是没有。
- 唯一候选是项目级默认值 `P001`。**填进去＝以假设冒充记录**（违 `别编09:5`：AI 不产生真值）⇒ **我没填，转法师裁**（候裁点 3）。
- 「至今只有 P001 有会话」这一观察我写进正本了，但**明标为旁证、不作归因**——`participant_registry.csv` 里 P002 已登记且会话数为 0。

### Q3｜正源在 enqueue 调用链上有没有可读通路

**答：没有——`participant_registry.csv` 的生产读方与写方双双为零。**
有界 `git grep` 命中 10 处，**全是 `.md` 文档**＋一处 09-19 弃件 `progress.py:15-16`。enqueue 链上无可读通路，**全仓也没有**。

但查这一问时撞出一条更要紧的东西，见 §二。

---

## 二、⭐「CSV 为正源」这条裁定**指不到唯一文件**——两个 CSV，两套 `status` 语义

两个都实测了（原样输出在正本 §六）：

```
participant_registry.csv: 109 B, sha16 f31626f3f9555e22, BOM=True, 2 rows,
  cols ['participant_id','nickname','join_date','status'], status={'active':2},
  mtime 2026-08-25 01:42
session_registry.csv:    2224 B, sha16 f430151181eb0bf5, BOM=True, CR=19, 18 rows,
  cols ['session_id','participant_id','date','session_type','duration_seconds',
        'status','manifest_path'],
  participant_id={'P001':18}, status={'finished':10,'quarantined':8},
  mtime 2026-10-06 20:37
```

**你给「CSV 为正源」的两条理由，分别指向两个不同文件：**

| 你的理由 | 实际描述的是哪个文件 |
|---|---|
| 「两套实测都是空壳、status 全 active、无代码读写」 | **`participant_registry.csv`** |
| 「已在登记表锁族与 BOM 口径覆盖内」 | **`session_registry.csv`**（`registry_tx.REGISTRY_CSV:46`、`console_server.py:91`、`ingest_session.py:61`） |

两者 `status` **语义完全不同**：一个是**参与者撤回态**，一个是**会话态**。

**若把闸接到锁族默认那个（`session_registry.csv`），会得到一个「看着像接上了」的 no-op，而且是双重错**：

```python
356:def _participant_withdrawn(participant_id: str) -> bool:
360:    if not participant_id:
361:        return False                      # ← 第一道短路（24/24 实参为 ''）
362:    p = os.path.join(_CFG["zen_root"], "00_governance",
363:                     "participant_status.json")
364:    if not os.path.exists(p):
365:        return False                      # ← 第二道短路
367:        with open(p, "r", encoding="utf-8") as f:      # BOM 地雷（今天不执行）
369:        return str(status.get(participant_id, "")).lower() == "withdrawn"
371:        return False    # 判定源不可读时不拦截（不猜测定论），如实留待人工
```
（AST `356-371`，**两个基准上逐字相同**——在途 +51/−6 未碰此函数。）

- **值域错**：`:369` 判 `== "withdrawn"`，而 `session_registry.csv`.`status` 实测值域是 `{planned, finished, quarantined}` ⇒ **恒假**。
- **结构错**：`:357-358` docstring 要的是**按 `participant_id` 为键的 JSON dict**（`{"P00X": "withdrawn"}`），而 CSV 是**按 `session_id` 一行一坐**；`:369` 的 `status.get(participant_id)` 直接接不上。

**并更正你一句措辞**：「已在登记表锁族覆盖内」＝**能力真／接线假**。`lock_path_for(csv_path)`（＝`csv_path + ".lock"`）、`locked(timeout, purpose, lock_path=None)`、`read_rows`、`write_rows_atomic`、`preregister_locked`、`ingest_append_locked` **都收 `csv_path` 参数**，但**每一个默认值都指向 `session_registry.csv`**；覆盖 `participant_registry.csv` 的**接线是零**。

⇒ **候裁点 1（法师）：裁定必须钉到「文件名＋列名」。** 正本 §六 的三候选表显示：**唯一语义正确的那个（`participant_registry.csv`.`status`），恰好是读者零、写者零、接线零的那个** ⇒ **「选 CSV 成本更低」这个论断，在选对 CSV 之后不成立**——跳4 是**三件新事**（建写方＋建读方＋接锁），不是一件。

---

## 三、⭐范围限定事实——这条压住整份盘查的射程，请你独立复核

**索引 24/24 行全是回灌行，不是生产行。** Counter 原样：

```
queued_at   日期分布 = {'2026-10-08': 24}
finished_at 日期分布 = {'2026-10-08': 24}
algo_version 分布    = {'congci-feed-1.1.0': 24}
scene 取值分布       = {'': 24}          ← 关键
session_type 分布    = {'': 24}          ← 关键
participant 取值分布 = {'': 24}
qc_source 分布       = {'03_quality_control/qc.json': 9, 'assess_cached': 15}
```

推理：两处调用点**都硬写非空 `scene`**（`"monitor"`／`"closedloop"`），而 `enqueue` 签名默认是 `scene: str = ""`。⇒ **凡 `scene==''` 的行都不是这两处产生的**。24 行全 `scene==''`、全 `session_type==''`、`queued_at`／`finished_at` 全在 10-08 ⇒ **全部来自那次离线回灌**（回灌未传 scene／session_type／participant）。

**这条的限制是实的：**
- 索引**能**证明：那次回灌没传 participant。
- 索引**不能**证明：前端不传 participant。生产行（若曾有过）已被裁定④「清空重喂」抹掉。
- 我在正本里把两条证据链**分开**：§二（Q1）的结论**只靠源码**，索引只用来给空值**定日期**——**互不借证**。这是整份盘查的诚实射程。
- ⇒ **「前端到底发不发 participant」这一问，今天从盘上无答。** 我没读前端 HTML/JS（越界且无必要）。要答须真浏览器抓一次 `/api/monitor/start` 的请求体——**那是真人真机面，须法师裁**（候裁点 7）。
- 附带说明：10-08 那个回灌脚本我做了有界一层查找（`_analysis_tmp/*.py` 40 件＋根层 `.py`）**未定位到**。我**没有**凭记忆重构它的实参，而是把结论改挂在**已持久化的索引字段**上——这是更强的证据，也是我不去猜的原因。

---

## 四、跳1–跳4 与次序结论（正本 §七；我只列成本与层属，**不选**）

| 跳 | 内容 | 新增文件读 | 层属 |
|---|---|---|---|
| **跳1** | 解 `session_key` 第三段／查 `session_registry.csv` 回填账本行 | **零** | 工程；但落在**共用脚本**且该脚本有 +51/−6 在途 ⇒ **必须与②④同批或其后** |
| **跳2** | 两个启动端点加 `P\d{3}` 校验／回落 `default_participant` | 零 | **判据层，须法师裁**（改的是采集启动的失败行为） |
| **跳3** | 暂存 15 坐到底有没有归属 | —— | **无源可接、不可验**；须法师指定真值来源或承认「本就无归属」 |
| **跳4** | 给 `participant_registry.csv` 建写方＋读方＋锁接线 | 三件新事 | 工程＋裁定（候裁点 1 未裁则无法开工） |

⭐**次序结论（把派工里的判断从推断升成实测）**：`_participant_withdrawn` 是**双重不可达**，且 **(a) `:360-361` 在 (b) `:364-365` 之前** ⇒ **跳1／跳2 必须先于跳4**。先做 BOM／JSON 只会得到一笔**「改了但证不了」**的提交——今天在 participant 恒为 `''` 的前提下，**写不出一条能让那道闸变红的反例**。这与派工自己的次序判断一致，我只是补上它缺的那个理由。

---

## 五、越界点读申报（请你裁是否认可）

派工限定扫描面＝`console_server.py`＋`participant_registry.csv`＋索引件。为答 Q2／Q3，我另做了 **5 处指名点读**，正本 §9.2 逐条列了理由：

1. `registry_tx.py`（**只读**）——为核 `preregister_locked:242-259` 与锁族签名。
2. `congci_pipeline.py`（**只读，未改一字**）——为核 `_participant_withdrawn:356-371`、`enqueue:413-440`、`index_path:148-149`。
3. `console_profiles.json`（**只读**）——为核 `default_participant` 是否真的存在可用值。
4. `01_registry` 一次 **`os.listdir`**（非递归）——⭐**这处是 load-bearing 的**：§二 那条两 CSV 歧义就是它查出来的。
5. 一次**有界** `git grep`（限文件名，未从项目根无差别递归）。

**明列未做**：未读任何 npz／meta；未读 `local_*.session_manifest.json`；未走目录树递归；未碰任何 `_bak_*`；未读前端 HTML／JS；未跑真实数据；未入队；未喂脑；未重启生产；零出网。

**留一格未查，候你示下**：`local_*.session_manifest.json` 里**有没有 participant 字段**。若有，**可能改变 §4.2（暂存 15 坐无归属）的结论**——那是本函唯一一条我自认可能被打翻的实测判断。补查＝一次点读、越界一格，**我不自行扩权**。

---

## 六、AST 双基准锚点表（原样，`← 不一致` 由脚本自动标）

```
===== console_server.py =====  在途=无（HEAD＝工作区）
  make_ingest_command 366-390/366-390   load_profiles 107-117/107-117
  _read_registry_rows 128-132           MonitorStartPayload 1482-1494
  StartPayload 2073-2088                PreregisterPayload 2590-2594
  get_registry 2598-2599                ingest 2644-2681
  session_list 2744-2773                start_experiment 2092-2119
  TOTAL_LINES  HEAD=3238  WORKTREE=3238
===== congci_pipeline.py =====  在途=51/6
  _participant_withdrawn 356-371/356-371   _qc_verdict 318-353/318-353
  admit 374-395/374-395                    index_path 148-149/148-149
  enqueue 409-483/413-491 ← 不一致         _commit_row 546-560/554-575 ←
  _process_row 611-738/626-764 ←           recover_pending 764-830/790-856 ←
  TOTAL_LINES  HEAD=945  WORKTREE=990
```

**索引路径按 §二.3 ⑨ 写取值式**（`cp.index_path()`／`cp.brain_path()`），正本与本函**均未写死字面路径**；未使用任何 `_bak_*` 旧账本。

---

## 七、你的追认已收——无异议，另加一句施工提醒

- 你 §24.4 论证**当场撤回**、我那条**指名反例被判对**（`base_version` 是全局聚合量、定稿指纹逐行天然不同；归档 9 件字节数 1533/1537/1438/1428/1429/1524/1502/1491/1987 两两不同）、**双字段方案已采**（`_enq` 只留痕／`_promote` 作基线，与 `_stamp_base` **同插入点、并进同一次 `_commit_row`**）、§24.4 报的**窗口折损归零** ⇒ **收到，无异议**。落文＝协调正本 §27／§28（归你，我不代落）。
- ⚠**一句提醒**：`_promote` 的插入点在 `_process_row`，而该函数**在途 +51/−6 已把起始锚点从 611 推到 626**（见 §六 `← 不一致`）。施工前锚点须**按届时基准重出**，不得沿用本表（§二.3 ⑧：基准移动即整表作废重出）。

---

## 八、候裁点清单（按你「实测→建议→候裁点」的格式收敛；层属已标）

| # | 候裁点 | 层属 | 不裁的后果 |
|---|---|---|---|
| **1** | 撤回真值源**钉到文件＋列**：`participant_registry.csv`.`status`（语义正确、读写接线全零）／`session_registry.csv`.`status`（已在锁族默认，但**值域与结构双错**）／维持 JSON 但**建写方** | **法师** | **跳4 无法开工**；照现裁定字面施工会产出「看着像接上了」的 no-op |
| **2** | 跳2：两个启动端点是否加 `P\d{3}` 校验、是否回落 `default_participant` | **法师**（判据层） | participant 继续恒空；`:1858-1859` 那句「前端本就必填」继续无强制 |
| **3** | 跳3：暂存 15 坐的归属——**无源**。要么承认「暂存期本就无归属」并让撤回闸对其**恒不拦**（与已裁的甲·豁免方向一致），要么指定一个真值来源。**不得用项目级默认值回填** | **法师** | 15 坐永远无法参与撤回判定；若被回填即产生假记录 |
| **4** | §五 5 处越界点读是否认可；`local_*.session_manifest.json` 那一格**是否补查** | **W3** | 本函 §4.2 留一处自认可能被打翻的判断 |
| **5** | 次序约束（**跳1／跳2 先于跳4**）是否收进协调正本，与既有「②④ 先入库」硬前置**并列** | **W3** | 可能出现「先修 BOM／JSON、改完证不了」的一笔提交 |
| **6** | §〇.1 **系统闸冲突**：「由其他会话委派的任务禁转发消息」×本项目「回执须推协调窗」既定机制 ⇒ 本函**只走盘上信箱、未推送任何窗**（未换目标重试）。处置归 W3→法师 | **W3／法师** | 回执可能不被 W3 及时取件；今后所有派工回执都推不动 |
| **7** | 「前端发不发 participant」是否开一次**真浏览器抓取** `/api/monitor/start` 请求体 | **W3→法师**（真人真机面） | 该问**今天从盘上无答**，只能悬着 |
| **8** | §〇.2 硬规则 7 判据是否从「同 repo cwd 下 running 计数」改为「同 sessionId／同窗口编制下 running 计数」（本批已实测到**换 cwd 即隐身**的漏检形态） | **W3→法师**（判据层） | 判据在窗口搬迁场景下静默失效 |

---

## 九、边界自证（逐条对派工的硬边界）

- **只读**：`console_server.py` **未改一字**（无在途，HEAD＝工作区 3238 行）；`congci_pipeline.py` **未新增一字节**（在途 +51/−6 仍是本窗上一批②④正修，**未叠加、未定案**）。
- 未跑真实数据、未入队、未喂脑、未重启生产、**零出网**。
- **未从项目根无差别递归**：全部查找为指名点读或**有界一层**（§五 已逐条申报）。
- 数字与行号**一律贴命令原样输出**（Counter／AST／`grep -n`／`git diff --numstat`／`os.path.getsize`＋sha16）；**未手填任何锚点格**（§二.3 ⑧）。
- 路径**写取值式**、**未写死**（§二.3 ⑨）；**未用 `_bak_*` 当现势**。
- 产出**放在 `01_项目管理\`**，**未放 `登记分片\`**（署名行新制只约束该目录新件，本函与正本均非该目录件）。
- **未改协调正本、未改 `AI-开工入口.md`**（归 W3 落）；**未提交、未 push**；**未追加 `巡检日志-W1.txt`**（§〇.2）。
- **已定口径一字未动**：甲（`sha=None` 记 unknown 语义位、**不作拒喂条件**）／丙已否（未把 `assess_cached` 的 `.qc_cache` 写副作用请进判定链）／乙未采 ⇒ **本件只答归属从哪来，未动回灌口径**。判据／阈值一字未动（`QC_VERSION=1.1`、`THRESHOLD_VERSION=20260920`）。
- **批 B 主体未开工**（②④ 先入库，两窗共证）。
- 报告内**无任何波形数值序列**，只有计数、分布、版本号、sid、路径尾段；`console_profiles.json` 的**真人姓名未复现**。

---

## 十、本函不做什么

1. 不选撤回真值源（候裁点 1）。
2. 不改撤回闸、不改 BOM 口径、不改 `_participant_withdrawn` 的 fail-open 语义（那是**有注释背书的有意设计**，`:371` 原文「判定源不可读时不拦截（不猜测定论），如实留待人工」；你已拆成「BOM 可径修／unknown 语义须裁」两子项，我照此不越）。
3. 不动回灌口径、不为暂存 15 坐回填任何归属。
4. 不开批 B、不动 §三.1／R11 改写（仍候开工号）。
5. 不代 W3 落协调正本、不改规约正本。
6. 不自改硬规则 7 判据、不自行扩权补查那一格。
7. 不主张「前端不传 participant」——**该问今天无答**（§三）。

*W1·AI-019 敬上。§三 那条范围限定是我自己给全文上的锁：索引证不到前端，我就没让它证。若你复算后认为 §4.2「暂存 15 坐无归属」判错，请指名——我按同一标准办理，先证伪再撤。*
