# `participant` 为何全空——两处 `enqueue` 调用点只读盘查（W3 派工⑤·法师已准）

2026-10-09 20:02｜**W1 工程线**（AI-019／Session `W1-QODER-20261008-A`／物理会话 `b8729a7a…`）
派工：`信箱/engine/20261009-W3-AI014-派工W1_participant全空只读盘查.md`（协调正本 §27.7 ⑤，法师 10-09 裁「**③甲，其他同意**」）
性质：**纯只读盘查**。未改 `console_server.py`、未改 `congci_pipeline.py`（其 +51／−6 在途一字节未动）、未跑真实数据、未入队、未喂脑、未重启生产、零出网。

---

## 〇、基准声明与复跑命令

| 项 | 实测值（命令产出） |
|---|---|
| HEAD | `8124cced831f8c03acba0759e4f50d26f6ec6f6e`（2026-10-09 17:59:54 +0800） |
| `console_server.py` 基线 | **HEAD＝工作区，未在途**（`git diff --numstat` 输出为空；两侧均 **3238 行**）⇒ 本件对该文件的引用**单基线即可**，无需双列 |
| `congci_pipeline.py` 基线 | **在途 +51／−6**（HEAD 945 行／工作区 990 行）⇒ 本件凡引该文件**一律标明是哪一侧**，锚点见 §八 双列表 |
| `AI-开工入口.md` | mtime **19:49:46**、**未提交**（`git diff --numstat` ＝ 1 插入／0 删除）⇒ 本件已重读新增的 §二.3 **⑧⑨** 两条并照办 |
| 索引件（取值式） | `cp.index_path()` ⇒ 实测解析为 `output\cadence_replay\congci\processed_index.json`；**24 行**，全 `committed` |
| 登记表目录（取值式） | `os.path.join(_CFG["zen_root"], "01_registry")` ⇒ 实测 `D:\Project\Zen-EEG\01_registry` |
| ⚠ 同区留底 | `output/cadence_replay/_bak_20261008_*` 两份 `processed_index.json` **一律未用**（规约 §二.3 ⑨：旧账不得当现势）。本件结论**无一条**据其推出 |

**本件所有数字与行号的产出方式**（遵 §二.3 ⑧「每格须由命令产出、禁手填，尾行同受此约」）：

- 行号 → `grep -n` 原样 ＋ Python `ast` 取 `lineno`／`end_lineno`（§八 整表由 AST 生成，双基线各跑一次）
- 计数／分布 → 直读 `cp.index_path()` 与两个 CSV 后 `collections.Counter` 原样打印
- 文件事实 → `os.path.getsize`／`getmtime`／`hashlib.sha256`／BOM 与 CR 字节计数
- **无一处照记忆填**；§八 表尾附"不一致"标记列，两基线不等者自动标出

---

## 一、结论摘要（三问三答）

| 问 | 答（一句话） |
|---|---|
| **①调用方有没有 participant 可传** | **有，而且两处都传了**——断点不在调用点，在再上一跳：`session_info["participant"]` 本身是空串。且**服务端进程内就存着一个可用值**（`console_profiles.json` 的 `default_participant='P001'`），**但保存路径从不读它** |
| **②两类是否同因** | **不同因**。归档 9 坐＝**归属确实存在**（ZEN-ID 第 3 段＋`session_registry.csv` 18/18＝P001），只是从没被送进 `enqueue` 实参；暂存 15 坐＝**盘上根本没有任何逐会话归属记录**，无从可传 |
| **③正源有无可读通路** | **`participant_registry.csv` 生产代码零读方、零写方、零接线**（`git grep` 命中全在 `.md` 文档与一份 09-19 取证脚本）。且⚠**盘上有两个 CSV、`status` 语义完全不同**，"CSV 为正源"这条裁定**须点名到文件与列**（§六） |

⭐**另有一条限定全部结论效力范围的事实，必须先说**：索引 24 行**没有一行来自生产保存路径**，全部出自 10-08 那次离线回灌（§三）。⇒ 本件能证的是"**回灌调用没传 participant**"，**不能**证"前端在生产路径上不传"。后者今天**无在盘证据可答**。

---

## 二、问1：两处 `enqueue` 调用点到底传了什么

### 2.1 两处调用的实参逐格对照（`grep -n "enqueue" console_server.py` 原样命中 `699:`／`1152:`）

| 实参 | 调用点一·监测保存收口 | 调用点二·闭环实验收口 |
|---|---|---|
| 调用语句行 | `console_server.py:699-705` | `console_server.py:1152-1158` |
| `npz_path` | `data_path`（`:700`） | `self.saved["npz"]`（`:1153`） |
| `qc` | **传** `qc=qc`（`:700`） | **不传**（由 `enqueue` 内 `admit` 自判） |
| `session_type` | `(self.session_info or {}).get("session_type") or ""`（`:701-702`） | 同式（`:1154-1155`） |
| **`participant`** | **`(self.session_info or {}).get("participant") or ""`（`:703-704`）** | **同式（`:1156-1157`）** |
| `scene` | **硬编码 `"monitor"`（`:705`）** | **硬编码 `"closedloop"`（`:1158`）** |
| 异常处置 | `:706-707` 裸捕＋`[warn]` 打印，不挡保存 | `:1159-1160` 同 |

⇒ **两处都显式传了 `participant=`，写法完全一致。**派工函问的"是有 participant 可传而没传，还是手里就没这个字段"——**在调用点这一层，答案是"传了"**。断点在再上一跳。

### 2.2 再上一跳：`session_info["participant"]` 的唯一来源＝HTTP 请求体，且服务端零校验

`session_info` 在全文件只有两个构造点（`grep -n "session_info" console_server.py` 原样，共 24 处命中，构造点为 `:1860`／`:2104`）：

```
1860:    session_info = {"participant": payload.participant or "",      ← 监测入口
2104:    session_info = {"participant": payload.participant or "",      ← 闭环入口
```

两个 payload 模型里 `participant` 都是**可选、缺省 None、无校验**：

```
1488:    participant: Optional[str] = None      ← MonitorStartPayload（AST: 1482-1494）
2082:    participant: Optional[str] = None      ← StartPayload（AST: 2073-2088）
```

**同一个文件里，另有两个端点对同一字段做了硬校验**（对照即见落差）：

```
2606:    if not re.fullmatch(r"P\d{3}", p):                    ← /api/registry/preregister
2607-2608:  raise HTTPException(status_code=400, detail="受试者编号格式应为 P001 形式")
2650:    if not re.fullmatch(r"P\d{3}", payload.participant.strip()):   ← /api/ingest
2651-2652:  raise HTTPException(status_code=400, detail="受试者编号格式应为 P001 形式")
```

⇒ **入库与预登记两条路都强制 `P\d{3}`；两个采集启动端点一处校验都没有。**

`:1858-1859` 的注释自己写着这条假设：

```
1858:    # 数据诚实（2026-09-24 裁定6）：未选即 null，不写成空串冒充"登记过但为空"；
1859:    # 唯一例外 participant/session_type（入库必需要素，前端本就必填）。
```

⚠ **这是一条写在注释里的假设，没有任何代码强制它。**且 `or ""` 的处置**恰恰与同一行援引的裁定6 相反**：裁定6 要求"未选即 null，不写空串冒充登记过但为空"，该原则对 `pre_state`／`contact_quality`／`intent`／`note`／`post_state` 全部生效（`:1862-1865`、`:2106-2110` 都是裸 `payload.x`，None 就留 None），**唯独把 `participant`／`session_type` 排除在外、压成 `""`**。⇒ 索引里的 `participant=''` **无法区分**"前端明确传了空"与"前端根本没传"——这正是本次盘查之所以要绕一大圈的原因。

### 2.3 ⭐服务端手里其实有 participant，只是没接到采集路径上

```
89:PROFILES_PATH = os.path.join(SCRIPT_DIR, "console_profiles.json")
107:def load_profiles():                       ← AST: 107-117
108:    """读取本机测试者档案：{profiles:[...], default_participant:str}。"""
113-114:  return {"profiles": data.get("profiles", []),
                  "default_participant": data.get("default_participant", "")}
```

实测该文件**在盘**（`os.path.exists(PROFILES_PATH)` → `True`）：

```
顶层键 = ['profiles', 'default_participant']
default_participant = 'P001'
profiles 条数 = 1
  （该条档案含真实姓名，依隐私口径本件不复现；该文件已被 .gitignore:77 的 *.json
    规则忽略、git 未跟踪 —— git check-ignore -v 与 git ls-files --error-unmatch 双验）
```

**`load_profiles()` 的全部调用点（`grep -n` 原样）＝只有两处，都是档案管理端点：**

```
2574:    return load_profiles()                 ← GET  /api/profiles（AST: get_profiles）
2581:            else load_profiles()["profiles"],   ← POST /api/profiles（AST: set_profiles）
```

⇒ **两个 start 端点不调它，两处 `enqueue` 不调它，`session_info` 构造不调它。**

**准确表述**：服务端进程内**就存着一个可用的 participant（一次函数调用之隔）**，但采集路径从不读它；它只被 `/api/profiles` 回吐给前端，**指望前端再传回来**。前端传不传、传什么，服务端**既不校验也不兜底**。

---

## 三、⭐限定本件全部结论效力范围的事实：索引 24 行无一来自生产保存路径

直读 `cp.index_path()` 后 `Counter` 原样输出：

```
索引 = D:\Project\zhiguanAI\output\cadence_replay\congci\processed_index.json   行数 = 24

queued_at   日期分布 = {'2026-10-08': 24}
finished_at 日期分布 = {'2026-10-08': 24}
algo_version 分布    = {'congci-feed-1.1.0': 24}
status 取值分布      = {'committed': 24}
scene 取值分布       = {'': 24}          ← 关键
session_type 分布    = {'': 24}          ← 关键
participant 取值分布 = {'': 24}
qc_source 分布       = {'03_quality_control/qc.json': 9, 'assess_cached': 15}
ZEN-* 键 = 9 行   非 ZEN = 15 行
```

**推理（一步，可复验）**：两处生产调用点分别**硬编码** `scene="monitor"`（`:705`）与 `scene="closedloop"`（`:1158`），而 `enqueue` 的签名是 `scene: str = ""`（`congci_pipeline.py:414`，HEAD／工作区同值）⇒ **任何经生产路径入队的行，`scene` 必非空**。实测 24 行 `scene` **全空**，`session_type` 亦全空 ⇒ **24 行全部由 10-08 那次离线回灌直接调 `enqueue` 产生，且该调用未传 `scene`、未传 `session_type`、未传 `participant`。**

⚠ **由此产生的效力边界（本件不越过它）**：

- 索引证明的是"**回灌调用没传 participant**"，**不能**证明"前端在生产路径上不传 participant"。
- 后者今天**无任何在盘证据可答**：生产路径若曾入队，其行已随裁定④「清空重喂」被清除；同区两份 `_bak_20261008_*` 依规约 §二.3 ⑨ **不得当现势用**，本件亦未据其下任何结论。
- 10-08 那个回灌脚本本身**已不在盘**（`ls -1 _analysis_tmp/*.py` 一层列举，40 件内无其名；未做递归搜索）⇒ 本件不引"脚本里怎么写的"，只引**它落下的持久结果**（索引字段），后者证据强度更高。

⇒ **§二 的结论（调用点传了、上游无校验、profiles 未被读）全部由 `console_server.py` 源码直接坐实，不依赖索引**；索引只用于回答"这 24 行的空值是哪一次调用留下的"。两条证据链**分开成立**，不互相借证。

---

## 四、问2：两类成因分开答（派工函明令不许合并归因）

### 4.1 归档位 9 坐（`ZEN-*` 键）——**归属确实存在，就在 `enqueue` 读不到的两个地方**

**归属在盘上的三处实证：**

**(1) `session_key` 字符串自身就含 `P001`**（原样，9/9）：

```
ZEN-20260830-P001-S02   在登记表=True  participant=''  scene=''
ZEN-20260830-P001-S03   在登记表=True  participant=''  scene=''
ZEN-20260830-P001-S04   在登记表=True  participant=''  scene=''
ZEN-20260831-P001-S05   在登记表=True  participant=''  scene=''
ZEN-20260901-P001-S06   在登记表=True  participant=''  scene=''
ZEN-20260905-P001-S08   在登记表=True  participant=''  scene=''
ZEN-20260906-P001-S12   在登记表=True  participant=''  scene=''
ZEN-20260911-P001-S13   在登记表=True  participant=''  scene=''
ZEN-20261006-P001-S18   在登记表=True  participant=''  scene=''
交集 = 9／ZEN 行 9／登记表 18
```

而 **`enqueue` 自己就计算这个串**（`congci_pipeline.py:434-436`，工作区侧；HEAD 侧为 `:430-432`）：

```
434:    if session_key is None:
435:        sid = os.path.basename(os.path.dirname(npz_path))
436:        session_key = sid if sid.startswith("ZEN-") else source_hash  # 未入库期＝内容 hash
```

**(2) `session_registry.csv`（＝代码实际读写的那张表）18 行全部 `participant_id=P001`**（原样）：

```
===== session_registry.csv 全 18 行 =====
  ZEN-20260825-P001-S01   P001  2026-08-25  baseline   finished
  ZEN-20260830-P001-S02   P001  2026-08-30  test       finished
  ZEN-20260830-P001-S03   P001  2026-08-30  test       finished
  ZEN-20260830-P001-S04   P001  2026-08-30  test       finished
  ZEN-20260831-P001-S05   P001  2026-08-31  baseline   finished
  ZEN-20260901-P001-S06   P001  2026-09-01  training   finished
  ZEN-20260905-P001-S07   P001  2026-09-05  baseline   quarantined
  ZEN-20260905-P001-S08   P001  2026-09-05  baseline   finished
  ZEN-20260905-P001-S09   P001  2026-09-05  test       quarantined
  ZEN-20260905-P001-S10   P001  2026-09-05  test       quarantined
  ZEN-20260905-P001-S11   P001  2026-09-05  test       quarantined
  ZEN-20260906-P001-S12   P001  2026-09-06  baseline   finished
  ZEN-20260911-P001-S13   P001  2026-09-11  training   finished
  ZEN-20260920-P001-S14   P001  2026-09-20  test       quarantined
  ZEN-20260920-P001-S15   P001  2026-09-20  test       quarantined
  ZEN-20260925-P001-S16   P001  2026-09-25  test       quarantined
  ZEN-20261002-P001-S17   P001  2026-10-02  baseline   quarantined
  ZEN-20261006-P001-S18   P001  2026-10-06  baseline   finished

  session_id 去重数 = 18   participant_id 去重 = ['P001']
  列名 = ['session_id','participant_id','date','session_type','duration_seconds','status','manifest_path']
  status 分布 = {'finished': 10, 'quarantined': 8}
```

**(3) 那个 `P001` 的权威产地**（`registry_tx.preregister_locked`，AST: 242-259）：

```
246:    lp = lock_path_for(csv_path)
247:    with locked(purpose="preregister", lock_path=lp):
248:        rows = read_rows(csv_path)               # 锁内最新表（非调用方旧快照）
250:        s_num = next_session_number(rows, participant)
251:        sid = f"ZEN-{date_compact}-{participant}-{s_num}"      ← P001 在此拼进 ID
254:        rows.append({"session_id": sid, "participant_id": participant,
255:                     "date": date, "session_type": session_type,
256:                     "duration_seconds": "", "status": "planned",
257:                     "manifest_path": ""})
258:        write_rows_atomic(rows, csv_path)
```

调用它的是 `/api/registry/preregister`（`console_server.py:2602-2623`，`:2606` 强校验 `P\d{3}`）。

⇒ **归档 9 坐的 participant 不是"丢了"，是"从没被送进 `enqueue` 的实参"**。它由**预登记**那刻写进 ZEN-ID 与 `session_registry.csv`，而 `enqueue` 走的是**采集保存**那条线，两条线在时间上前后相隔、在代码上互不相通，**且没有任何一处把归属回填进账本行**。

**取回代价＝零新增文件读取**：切 `session_key` 第 3 段（可用 `P\d{3}` 正则自验），或按 `session_id` 查 `session_registry.csv`（`registry_tx.read_rows` 已接线、已在锁族内）。

### 4.2 暂存期 15 坐（64 位 sha256 键）——**盘上根本没有任何逐会话归属记录**

- `npz_path` 实测样例（原样）：
  ```
  key=e229941442230fa7928a…  npz_path=D:\Project\zhiguanAI\muse2-repo\muse2-master\report\local_20260831_164447.npz
  key=82fb376ce3f1a881099a…  npz_path=D:\Project\zhiguanAI\muse2-repo\muse2-master\report\local_20260901_084353.npz
  ```
  ⇒ **文件名只有时间戳，无参与者段**；`session_key` ＝源文件 sha256，出自 `enqueue:436` 的 `else source_hash` 分支（代码注释「未入库期＝内容 hash」＝**设计如此，不是缺陷**）。
- **暂存区就是这里**（取值式，非写死）：`REPORT_DIR = os.path.join(REPO_DIR, "report")`（`console_server.py:84`），`REPO_DIR = os.path.join(SCRIPT_DIR, "muse2-repo", "muse2-master")`（`:60`）⇒ 与索引里 15 行的 npz 落点**同一处**，坐实这 15 坐出自暂存区。
- **控制台自己的暂存清单也不带 participant**（`/api/session/list`，AST: `session_list` 2744-2773；`:2758-2772` 原样）：
  ```
  2763:                staged.append({
  2764:                    "session_id": stem,
  2765:                    "npz": name,
  2766-2768:               "manifest": (os.path.exists(...)),
  2769-2771:               "events": (os.path.exists(...)),
  2772:                })
  ```
  ⇒ **每条只有四个键，没有 participant 字段。**同函数的归档分支（`:2749-2757`）**却有** `"participant": r.get("participant_id", "")`（`:2751`）——**同一个端点里，归档带归属、暂存不带**，这正是两类不同因的界面级证据。
- 未入库 ⇒ **不在 `session_registry.csv`**（该表 18 行全为 `ZEN-*`，实测无一条 `local_*`）。

⇒ **这一类可用的只有项目级缺省 `console_profiles.json:default_participant='P001'`。但那是"本机默认测试者"，不是"这一坐是谁"的记录。**

⛔ **把它填进这 15 行＝用假设冒充记录，属 AI 产生真值（违 `别编09:5`）⇒ 本件不填、不建议径填，列为候法师裁。**

> **旁证，明确不作归因**：`participant_registry.csv` 登记了 P001／P002 两人，而 `session_registry.csv` 18/18 全 P001、`console_profiles.json` 只有 P001 一条档案 ⇒ 迄今全部**已入库**会话事实上都属 P001。但"迄今只有一人"**推不出**"这 15 坐属 P001"——尤其 P002 已登记却 0 会话（此点为 09-19 白盒盘点报告既有记载，本件未独立复核，标**未核**）。

### 4.3 两类成因并列对照（按派工函要求，不合并）

| | 归档位 9 坐 | 暂存期 15 坐 |
|---|---|---|
| 逐会话归属记录 | **有**（ZEN-ID 第 3 段 ＋ `session_registry.csv.participant_id`） | **无任何** |
| 索引行为何空 | 回灌调用未传实参（归属在盘但没人递过去） | 回灌调用未传实参 **且** 盘上无从可传 |
| 生产路径若重跑会不会仍空 | **会**——`session_info` 上游无校验无兜底（§2.2／§2.3） | **会**——同上，且无归属可兜 |
| 取回代价 | **零新增读取**（切串，或查已接线的表） | **须先有归属来源**，否则只能填项目级缺省＝假设 |
| 可否机器判定 | **可**（`P\d{3}` 正则能验 session_key 第 3 段） | **不可**（无判据） |
| 与撤回闸的关系 | 修好取数即可让闸**有意义** | 闸对其**永远无从判起** |
| 界面级旁证 | `/api/session/list:2751` 归档分支**有** participant | `:2763-2772` 暂存分支**无** participant |

---

## 五、问3：正源 `participant_registry.csv` 在 `enqueue` 链上有无可读通路

### 5.1 答：**生产代码零读方、零写方、零接线**

`git grep -n "participant_registry" -- "*.py" "*.js" "*.html" "*.md" "*.json" "*.ps1"`（**限已跟踪文件，非递归扫盘**）命中 **10 处，全部分布如下**：

| 落点 | 性质 |
|---|---|
| `01_项目管理/20260919_数据全链路整体盘查与解决方案_讨论稿_v1.md:78`、`:119` | 文档 |
| `01_项目管理/20260919_数据全链路盘查_复核证据/Zen-EEG_数据管理白盒盘点报告.md:60`、`:120`、`:129` | 文档 |
| `01_项目管理/20260919_数据全链路盘查_复核证据/progress.py:15-16` | **一次性取证脚本**（`print(open(...).read())`，非生产） |
| `01_项目管理/20261008_W1_批B准入事务只读设计与写方清单_v1.md:92`、`:131`、`:173`、`:185` | 文档（本窗旧件） |
| `01_项目管理/20261008_W3_全项目协同整合基础与首批施工契约_v0.1.md:1091` | 文档（W3 协调正本） |

⇒ **生产代码（`console_server.py`／`congci_pipeline.py`／`registry_tx.py`／`ingest_session.py`）零命中。**`grep -n "participant_registry" console_server.py` 原样输出＝**空**。

对照：`participant_status.json`（`_participant_withdrawn` 现在读的那个）的命中＝`congci_pipeline.py:357`（docstring）、`:363`（路径拼接），加 `01_项目管理/测试台验收工具/20261006_W1_congci_pipeline_test.py:379`、`:384`（**测试夹具写 tmp，非生产写方**）⇒ 与 W3 §二.E 结论一致，**生产写方为零**。

### 5.2 两个 CSV 的现势实测（原样）

```
登记表目录 = D:\Project\Zen-EEG\01_registry    isdir = True
       665 B  2026-08-30 23:39  README.md
       109 B  2026-08-25 01:42  participant_registry.csv
      2224 B  2026-10-06 20:37  session_registry.csv
       853 B  2026-09-19 04:17  session_registry.csv.bak-20260919

===== participant_registry.csv =====
  size = 109 B   sha16 = f31626f3f9555e22
  有 BOM = True   CR 数 = 1
  数据行数 = 2
  列名 = ['participant_id', 'nickname', 'join_date', 'status']
  列 'participant_id' 取值分布 = {'P001': 1, 'P002': 1}
  列 'status' 取值分布 = {'active': 2}

===== session_registry.csv =====
  size = 2224 B   sha16 = f430151181eb0bf5
  有 BOM = True   CR 数 = 19
  数据行数 = 18
  列名 = ['session_id','participant_id','date','session_type','duration_seconds','status','manifest_path']
  列 'participant_id' 取值分布 = {'P001': 18}
  列 'status' 取值分布 = {'finished': 10, 'quarantined': 8}
```

`session_registry.csv` 的接线（`git grep -n "session_registry" -- "*.py"` 原样，生产件部分）：

```
console_server.py:91:REGISTRY_CSV = os.path.join(ZEN_ROOT, "01_registry", "session_registry.csv")
registry_tx.py:46:REGISTRY_CSV = os.path.join(ZEN_ROOT, "01_registry", "session_registry.csv")
05_产品与开发/muse-direct/tools/ingest_session.py:61:REGISTRY = ZEN_ROOT / "01_registry" / "session_registry.csv"
```

---

## 六、⭐由此必须报的一条口径歧义：盘上有两个 CSV，`status` 语义完全不同

法师已裁「CSV 为正源」。**但盘上有两个 CSV，而 W3 §五.1 给的两条理由分别指向两个不同文件：**

| W3 §五.1 的理由（原文摘） | 实际描述的是哪个文件 | 本件实测 |
|---|---|---|
| 「CSV `status` 列**现值全 `active`**、无任何代码读写」 | **`participant_registry.csv`** | ✅ 坐实：2 行全 `active`；生产代码零读写（§5.1） |
| 「已在**登记表锁族**与 BOM 口径覆盖内、已在 `registry_tx` 覆盖内」 | **`session_registry.csv`** | ✅ 坐实：`registry_tx.REGISTRY_CSV:46`、`console_server.py:91`、`ingest_session.py:61` 三处接线 |

**而两张表的 `status` 列语义完全不同：**

| 文件 | `status` 实测取值 | 语义 | 是金口#6 要的那个吗 |
|---|---|---|---|
| `participant_registry.csv` | `{active}`（2/2） | **参与者**是否撤回 | **是** |
| `session_registry.csv` | `{finished: 10, quarantined: 8}` | **会话**的状态 | **不是**（`quarantined` ＝"这一坐被隔离"，与"这个人撤回了"无关） |

### 6.1 ⚠ 若按错的那条理由施工，会产出一个"看起来接好了"的 no-op

`_participant_withdrawn` 的判定式（AST: 356-371，**HEAD 与工作区同值**，原样）：

```
356:def _participant_withdrawn(participant_id: str) -> bool:
357:    """撤回者不入队（金口#6 过渡）。判定源＝00_governance/participant_status.json
358:    （{"P00X": "withdrawn"}）。撤回流程本体系数据盘查 P4-4 候法师项，现无数据——
359:    文件不存在时恒 False（如实：当前无人处于撤回态）。"""
360:    if not participant_id:
361:        return False                      ← 第一道短路
362:    p = os.path.join(_CFG["zen_root"], "00_governance",
363:                     "participant_status.json")
364:    if not os.path.exists(p):
365:        return False                      ← 第二道短路
366:    try:
367:        with open(p, "r", encoding="utf-8") as f:      ← BOM 地雷所在（今天不执行）
368:            status = json.load(f)
369:        return str(status.get(participant_id, "")).lower() == "withdrawn"
370:    except Exception:
371:        return False    # 判定源不可读时不拦截（不猜测定论），如实留待人工
```

**两重不匹配**（若把正源接到 `registry_tx.REGISTRY_CSV` ＝ `session_registry.csv`）：

1. **值域不匹配**：`:369` 判 `== "withdrawn"`，而该表 `status` 的值域是 `{planned, finished, quarantined}`（`planned` 见 `registry_tx:256`）⇒ **永不成立**，闸仍是 no-op，**但这次是"看起来接好了"的 no-op，比现在更难发现**。
2. **结构不匹配**：`:369` 读的是 `status.get(participant_id)`，即**以 `participant_id` 为键的 JSON 字典**（`:357-358` docstring 明写形状 `{"P00X": "withdrawn"}`）；`session_registry.csv` 是**一行一会话、以 `session_id` 为主键**的表 ⇒ 直接喂进去**键就对不上**，`.get("P001")` 恒 `None`。

### 6.2 锁族覆盖：**能力上真、接线上假**

`registry_tx` 的四个原语**全部以 `csv_path` 为参数**，`locked` 以 `lock_path` 为参数，`lock_path_for` 是纯路径函数：

```
56:def lock_path_for(csv_path: str) -> str:
57:    """登记表对应的锁件路径（与 csv 同目录同名 + .lock）。"""
58:    return csv_path + ".lock"

111:def locked(timeout: float = LOCK_TIMEOUT_S, purpose: str = "",
112:           lock_path: str = None):
129:    lp = lock_path or lock_path_for(REGISTRY_CSV)      ← 缺省才落到 session_registry

189:def read_rows(csv_path: str = REGISTRY_CSV):
198:def write_rows_atomic(rows, csv_path: str = REGISTRY_CSV) -> None:
242:def preregister_locked(participant: str, session_type: str, date: str,
243:                       csv_path: str = REGISTRY_CSV) -> str:
286:def ingest_append_locked(row: dict, csv_path: str = REGISTRY_CSV) -> None:
```

⇒ **技术上完全可以覆盖 `participant_registry.csv`**（调用时传 `csv_path=` 与 `lock_path=lock_path_for(...)` 即可），**但今天没有任何一处这样传**——所有缺省值都指向 `session_registry.csv`。

**故 W3 那句「已在登记表锁族覆盖内」须理解为：能力已具备、接线为零。**

### 6.3 提请：正源裁定须点名到**文件与列**

**本件不代裁。**只把裁定所需的实测事实摆齐：

| 候选 | 语义对否 | 有读方 | 有写方 | 在锁族接线内 | 结论 |
|---|---|---|---|---|---|
| `00_governance/participant_status.json`（代码现读） | 对（形状即 `{"P00X": "withdrawn"}`） | 有（`:367`，但双重不可达） | **无** | 无 | 盘上**不存在** |
| `01_registry/participant_registry.csv`.`status` | **对**（`active` ↔ 撤回态） | **无** | **无** | **能力有、接线无** | 在盘、109 B、2 行、45 天未动（mtime 2026-08-25） |
| `01_registry/session_registry.csv`.`status` | **错**（会话状态） | 有 | 有 | **有** | 在盘、18 行；**语义不可用于撤回** |

⇒ **三条里只有中间一条语义正确，而它恰好是读写方与接线全为零的那条。**"选 CSV 成本更低"这个判断，**在选对 CSV 的前提下不成立**——`participant_registry.csv` 需要新建写方＋新建读方＋新建锁接线**三件**，不是一件（§七 跳4）。

---

## 七、要拿到 `participant`／让撤回闸有意义，需要新增哪几跳

按"最小到最大"排。**本件只列跳与代价，不择案、不施工。**

| # | 跳 | 目标 | 代价与约束 | 今天能否只读验证 |
|---|---|---|---|---|
| **跳1** | `enqueue` 侧：归档位从 `session_key` 切第 3 段（`P\d{3}` 自验），或按 `session_id` 查 `session_registry.csv`（`registry_tx.read_rows` 已接线） | 让**归档位**的 participant 落地 | **零新增文件**；不碰判据／阈值；但改的是 `congci_pipeline.py`＝**四窗共用脚本，且其 +51／−6 在途未定案** ⇒ 须排在②④入库之后 | **可**（纯函数，能写出会红的反例） |
| **跳2** | 保存路径：两个 start 端点对 participant 加 `P\d{3}` 校验，或缺省兜底 `load_profiles()["default_participant"]` | 让**新采集**的会话从源头带归属 | 改 `console_server.py`（**本批禁改**）。⚠**兜底＝把项目级缺省当逐会话记录**，与 §4.2 同一性质 ⇒ **属判据层，须法师裁**；且加校验会**改变采集启动的失败行为**（原本静默通过 → 变成 400），影响面须法师认 | **可** |
| **跳3** | 暂存期：先定"暂存会话到底有没有归属"这件事本身 | 让**暂存 15 坐**可判 | **无来源可接**。只有两条路：新建记录（采集时把 participant 写进 `local_*.session_manifest.json`），或**明认"暂存期无归属"**并据此定乙案对它的处置 | **不可**（无判据 ⇒ 写不出反例） |
| **跳4** | `participant_registry.csv`：新建**写方**＋**读方**＋**锁接线**（**三件，不是一件**） | 让撤回闸真正可判 | 写方今天**不存在**——`/api/registry/preregister` 只写 `session_registry.csv`（实测 `registry_tx.preregister_locked:254-258` 的 append 字典里没有参与者表写入）⇒ **新参与者只能手改一个没有代码读的文件**（P002 即此况：已登记、0 会话、无档案） | **建了才可** |

### 7.1 ⭐次序结论（坐实派工函 §一 的判断，并给出其理由）

`_participant_withdrawn:356-371` 今天**双重不可达**，且**两道短路的先后顺序决定了施工次序**：

- **(a) `:360-361`** `if not participant_id: return False` ——实参 **24/24 为 `''`**（索引原样 `{'': 24}`）⇒ **恒在此返回**
- **(b) `:364-365`** 判定源 `00_governance/participant_status.json` 盘上不存在

**(a) 在 (b) 之前** ⇒ **即使把判定源建出来（跳4），只要 participant 还是空串，`:366-369` 那几行永不执行。**

⇒ **跳1（或跳2）必须先于跳4。**跳过它去修 BOM／建 JSON，产出的是**"改了但无法用任何测试证明"的一笔**——今天写不出一条能红的反例（`:367` 的 BOM 问题同理：那行永不执行）。这与本窗上轮回执 C 点的结论一致，本件把它从"设计推断"升级为"实参实测"。

### 7.2 与已定口径的关系（派工函 §四，本件不越界）

法师已择 **甲**（无定稿＝`sha=None` 记 unknown 语义位，**不作拒喂条件**，豁免含无定稿 15 坐）；**丙已否**；**乙未采**。

⇒ **本件未动回灌口径一字**，未改 `enqueue`／`admit`／`_qc_verdict` 的任何判据，未评阈值合理性（`QC_VERSION=1.1`、`THRESHOLD_VERSION=20260920` 一字未动）。**跳1–跳4 全部是"待裁的候选跳"，不是建议施工项**；其中跳2 的兜底与跳3 的归属认定**属判据层，AI 不产生真值**（`别编09:5`）。

---

## 八、锚点表（Python `ast` 双基线产出，遵 §二.3 ⑧：每格命令产出、禁手填、尾行同受此约）

生成方式＝`ast.parse` 后遍历 `FunctionDef`／`ClassDef`，取 `lineno` 与 `end_lineno`；HEAD 侧用 `git show HEAD:<file>` 取源，工作区侧直读文件。**两列不等者由脚本自动标 `← 不一致`，非人工挑。**

```
===== console_server.py =====  在途=无（HEAD＝工作区）
  符号                              HEAD           工作区
  make_ingest_command              366-390       366-390
  load_profiles                    107-117       107-117
  _read_registry_rows              128-132       128-132
  MonitorStartPayload             1482-1494     1482-1494
  StartPayload                    2073-2088     2073-2088
  PreregisterPayload              2590-2594     2590-2594
  get_registry                    2598-2599     2598-2599
  ingest                          2644-2681     2644-2681
  session_list                    2744-2773     2744-2773
  start_experiment                2092-2119     2092-2119
  TOTAL_LINES  HEAD=3238  WORKTREE=3238

===== congci_pipeline.py =====  在途=51	6	congci_pipeline.py
  符号                              HEAD           工作区
  _participant_withdrawn           356-371       356-371
  _qc_verdict                      318-353       318-353
  admit                            374-395       374-395
  enqueue                          409-483       413-491   ← 不一致
  _commit_row                      546-560       554-575   ← 不一致
  _process_row                     611-738       626-764   ← 不一致
  recover_pending                  764-830       790-856   ← 不一致
  index_path                       148-149       148-149
  TOTAL_LINES  HEAD=945  WORKTREE=990
```

**本件引用 `congci_pipeline.py` 时一律标侧**：`:356-371`（`_participant_withdrawn`）与 `:318-353`（`_qc_verdict`）**两基线同值**，可直接引；`:434-436`（`session_key` 计算）为**工作区侧**，HEAD 侧对应 `:430-432`；`:414`（`enqueue` 签名 `scene: str = ""`）为**工作区侧**。

**派工函点名的两处调用点，现势行号（`grep -n` 原样，非沿用旧记）**：

| 处 | 派工函嘱勿沿用的旧记 | **现势实测** | HEAD 侧 |
|---|---|---|---|
| 监测保存收口 | `:698-705` | **`:699-705`**（`699: congci_pipeline.enqueue(`） | 同值 |
| 闭环实验收口 | `:1151-1158` | **`:1152-1158`**（`1152: congci_pipeline.enqueue(`） | 同值 |

⇒ **旧记各差 1 行**（把 `import congci_pipeline` 那行 `:698`／`:1151` 算进了调用语句）。因 `console_server.py` **HEAD＝工作区**，本次不存在基准漂移，两处旧记的偏差属**当初取范围口径不同**，不是文件动过。

---

## 九、只读边界自证与范围外点读申报

### 9.1 边界自证

- **未改任何文件**（本件与本批回执两件新文档除外）。`git diff --numstat -- console_server.py` 输出**为空**；`congci_pipeline.py` 仍是 **+51／−6**，与本批开工前**逐字节相同**，本件未加一字节。
- **未跑真实数据、未入队、未喂脑、未跑 `--drain`、未重启生产、未起 8777、零出网。**
- **未打开任何 npz**：本件对 npz 的全部认知来自**索引里已记的 `npz_path` 字符串**，未 `np.load`、未读任何波形数值序列（故本件无任何数值序列可粘贴）。
- **判据／阈值一字未动**（`QC_VERSION=1.1`、`THRESHOLD_VERSION=20260920`）；未改 `qc_pipeline.py`／`refresh_qc.py`／`registry_tx.py`／`ingest_session.py`。
- **未从项目根无差别递归**：唯一一次目录列举是 `os.listdir` 于**派工函点名的那一个目录** `D:\Project\Zen-EEG\01_registry`（为发现"代码读的其实是另一个 CSV"）；其余全为**具名文件点读**与 `git grep`（限已跟踪文件）。
- **未动共享文**：协调正本与 `AI-开工入口.md` 一字节未改（后者 mtime 19:49:46 系 W3 所留，本件只读）。
- ⚠ **本窗己档 `巡检日志-W1.txt` 本批未追加**——落笔前实测本仓 `runtimeState=="running"` 会话计数＝**2**（`a5e0f8f4` W3 ＋ `b8729a7a` 本窗），按 `AI-开工入口.md` §二bis **硬规则 7**「有则只出报告不落共享文」，本批**只出报告**。己档属规则明列的共享文（「他人己档与本窗己档」）；本件与回执两件**不在**共享文枚举内，属规则允许的"只出报告"产出。**此事已另报法师。**
- **批 B 主体未开工**（派工函 §三 ⚠／两窗共证 §27.6）。本件纯只读、未碰 `congci_pipeline.py`，与之并行无害。

### 9.2 范围外点读申报（如实划界，候 W3 定是否扩权）

派工函 §三 限定扫描范围为「`console_server.py`＋`01_registry\participant_registry.csv`＋索引件」。本件**超出该清单做了 5 处具名点读**，逐条申报理由：

| 超范围对象 | 读法 | 为何非读不可 |
|---|---|---|
| `registry_tx.py` | 具名点读 `:46`／`:56-58`／`:111-135`／`:189`／`:198`／`:242-259`／`:262-283`／`:286-290` | 问3 问"锁族覆盖"，而 `console_server.py:91`／`:128-132` 把读写全权委托给它；不读它就无法回答"锁族覆不覆盖得到" |
| `congci_pipeline.py` | **只读、未改**；AST 重出锚点；点读 `:356-371`／`:413-440` | 问2 须知道 `enqueue` 拿到实参后做了什么、`session_key` 怎么算；且 §八 锚点表须双基线 |
| `console_profiles.json` | 具名点读（`PROFILES_PATH`，`console_server.py:89`） | 它是**进程内唯一的 participant 现存来源**，不读就无法回答"调用方手里到底有没有"。⚠**内含真实姓名，本件不复现**；已双验该文件被 `.gitignore:77` 忽略且 git 未跟踪 |
| `D:\Project\Zen-EEG\01_registry\`（一次 `os.listdir`）＋ `session_registry.csv` | 单目录列举＋具名点读 | ⭐**正是这一步查出"代码读的是 `session_registry.csv` 而非派工函点名的 `participant_registry.csv`"**——若不列目录，§六 那条口径歧义就漏了 |
| `git grep`（`participant_registry`／`participant_status`／`session_registry`） | 限已跟踪文件，非文件系统递归 | 问3 要答"有没有可读通路"，须证读写方为零；`git grep` 是**有界**查询，不构成"从项目根无差别递归" |

**未做的超范围动作**（明确划界）：未读任何 npz 或其 `meta`；未读 `local_*.session_manifest.json`（**若需坐实"暂存期 manifest 里也没有 participant"，这是唯一还没查的一格，候 W3 决定是否放行**）；未 walk `02_raw`／muse2 树；未读 `_bak_20261008_*`；未读前端 HTML/JS（⇒ **"前端到底传不传 participant"本件无答**，见 §三 效力边界）。

---

## 十、本件不做（划界，防越权）

1. **不代裁**任何一条：跳1–跳4 的择案、暂存期归属的认定、正源点到哪个文件哪一列——**全部候法师**，本件只摆实测事实与代价。
2. **不填** 15 坐暂存会话的 participant（＝用假设冒充记录，违 `别编09:5`）。
3. **不改**任何代码，包括看起来"一行就能修"的跳1。
4. **不评**阈值／判据合理性，不动 `QC_VERSION`／`THRESHOLD_VERSION`。
5. **不据** `_bak_*` 旧账下任何结论（规约 §二.3 ⑨）。
6. **不声称**"前端不传 participant"——今天无在盘证据（§三）。
7. **不动**回灌口径（法师已择甲，本件不顺手改）。

---

*W1 工程线·AI-019 敬上。本件全部数字与行号可由 §〇 所述方式独立复现；若 W3 复算出任一格与本件不符，请指名，本窗按「先证伪再撤」当场订正——上一轮本窗已自撤两条、自曝锚点手填一条，不差这一条。*
