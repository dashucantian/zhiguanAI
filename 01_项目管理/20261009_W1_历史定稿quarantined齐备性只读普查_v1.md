# 历史定稿 `quarantined` 齐备性只读普查（W3 派工 10-09·法师已准）

2026-10-09 17:56｜**W1 工程线**（AI-019／Session `W1-QODER-20261008-A`／物理会话 `b8729a7a…`）
派工：`信箱/engine/20261009-W3-AI014-派工W1_历史定稿quarantined齐备性只读普查.md`（协调正本 §24.6 问题 4／§26.3 第 9 项，法师 10-09 裁**同意**并明示可立即放行）
性质：**纯只读取证**。未改任何 `qc.json`、未写 `03_quality_control/`、未动 `refresh_qc.py`／`write_qc_json`、未跑 `--drain`／未入队／未喂脑／未重启生产；判据与阈值一字未动（`QC_VERSION=1.1`、`THRESHOLD_VERSION=20260920`），本件不评阈值合理性；零出网。

---

## 〇、基准声明与复跑命令

| 项 | 实测值 |
|---|---|
| 出件时 HEAD | `ae28d4856b6e9593bc6430ebba5479280269364c`（2026-10-09 17:10:46 +0800） |
| ⚠ 定稿时 HEAD 已前移 | `8124cced831f8c03acba0759e4f50d26f6ec6f6e`（17:59:54，`docs(W3): 「一名多手」立规两处入规约＋坑卡 019＋批 B 前置普查派工（5 件）`）——**本件写作期间 HEAD 动了一次**。<br>已核：`git diff --name-only ae28d48 HEAD -- congci_pipeline.py` **输出为空＝未碰该文件**，故 §十 锚点表的 HEAD 列值**仍然成立、不必重出**；该笔 5 件全为 W3 侧文档（协调正本、本普查派工函、W3 己档、坑卡 019、`AI-开工入口.md`），与本普查的取证面无交集。<br>**这正是回执件 §六 提请第 6 项（「锚点表每格须由命令产出、禁手填；出件到施工间基准移动即作废重出」）的现场实例**：基准会在写作中途移动，"表头声明一个基准"与"每一格都对那个基准取值"是两件事。 |
| 工作区 `congci_pipeline.py` | 含本窗缺陷②④正修**在途未提交**（+51／−6，净 +45 行）；本普查**不依赖**该在途改动 |
| 扫描根 | `D:\Project\Zen-EEG\03_quality_control\`（**仅此一处**，禁从项目根递归） |
| 索引权威路径 | `cp.index_path()` ＝ `D:\Project\zhiguanAI\output\cadence_replay\congci\processed_index.json` |
| ⚠ 派工函所述索引路径 | `output/congci/processed_index.json` — **实测不在盘**（`os.path.exists` → `False`），已改取 `cp.index_path()` 权威值 |
| ⚠ 同区两个留底 | `output/cadence_replay/_bak_20261008_裁定1喂15坐前留底/`、`_bak_20261008_裁定4清空前留底/` 各有一份 `processed_index.json` — **一律不用**（清空前旧账，会把已作废的行数报成现势） |

**复跑命令**（原样，可独立复现全部数字）：

```
cd /d/Project/zhiguanAI
PY="C:/Users/tiand/AppData/Local/Programs/Python/Python312/python.exe"
PYTHONIOENCODING=utf-8 "$PY" "_analysis_tmp/_qc_census.py"
```

普查脚本＝`_analysis_tmp/_qc_census.py`（临时件，不入库；`_analysis_tmp/` 已被 `.gitignore` 忽略）。**下方所有表格均为该命令的原样输出，无一处预估**（规约 §二.3）。

---

## 一、主交付：计数表

```
  分区  | 件数 | 有 quarantined 键 | 值=True | 值=False | 键缺失 | 键在但值非法(非bool) | 不可读/JSON坏
  ----+----+-----------------+--------+---------+-----+---------------+----------
  归档位 | 9  | 4               | 0      | 4       | 5   | 0             | 0
  隔离位 | 8  | 8               | 8      | 0       | 0   | 0             | 0
  合计  | 17 | 12              | 8      | 4       | 5   | 0             | 0
```

扫描范围自证（原样输出）：

```
  扫描根          = D:\Project\Zen-EEG\03_quality_control
  os.walk 命中 qc.json = 17 件
  命中 .qc_cache 子树  = 0 处（已 dirnames[:]=[] 跳过，不读）
  索引权威路径    = D:\Project\zhiguanAI\output\cadence_replay\congci\processed_index.json
    派工函所述 output/congci/processed_index.json 在盘 = False
    索引 exists   = True
```

**一句话结论**：17 件定稿**全部可读、JSON 全部合法、无一件值非法**；键缺失 **5 件，全在归档位**；隔离位 **8 件全 `True`**。

---

## 二、逐件明细（`qc_version`／`threshold_version`／`generated_at` 三元组）

```
  分区  | sid                   | quarantined | 键在 | qc_version | threshold_version | generated_at              | recommend  | nkeys
  归档位 | ZEN-20260830-P001-S02 | —           | N  | 1.0        | 20260920          | 2026-09-20T22:56:38+08:00 | ingest     | 21
  归档位 | ZEN-20260830-P001-S03 | —           | N  | 1.0        | 20260920          | 2026-09-20T22:56:38+08:00 | ingest     | 21
  归档位 | ZEN-20260830-P001-S04 | —           | N  | 1.0        | 20260920          | 2026-09-20T22:56:38+08:00 | ingest     | 21
  归档位 | ZEN-20260831-P001-S05 | —           | N  | 1.0        | 20260920          | 2026-09-20T22:56:39+08:00 | ingest     | 21
  归档位 | ZEN-20260901-P001-S06 | —           | N  | 1.0        | 20260920          | 2026-09-20T22:56:39+08:00 | ingest     | 21
  归档位 | ZEN-20260905-P001-S08 | False       | Y  | 1.0        | 20260920          | 2026-09-20T22:56:39+08:00 | ingest     | 23
  归档位 | ZEN-20260906-P001-S12 | False       | Y  | 1.0        | 20260920          | 2026-09-20T22:56:40+08:00 | ingest     | 23
  归档位 | ZEN-20260911-P001-S13 | False       | Y  | 1.0        | 20260920          | 2026-09-20T22:56:40+08:00 | ingest     | 23
  归档位 | ZEN-20261006-P001-S18 | False       | Y  | 1.1        | 20260920          | 2026-10-06T20:37:11+08:00 | ingest     | 27
  隔离位 | ZEN-20260905-P001-S07 | True        | Y  | 1.0        | 20260920          | 2026-09-20T22:56:39+08:00 | ingest     | 23
  隔离位 | ZEN-20260905-P001-S09 | True        | Y  | 1.0        | 20260920          | 2026-09-20T22:56:40+08:00 | ingest     | 23
  隔离位 | ZEN-20260905-P001-S10 | True        | Y  | 1.0        | 20260920          | 2026-09-20T22:56:40+08:00 | ingest     | 23
  隔离位 | ZEN-20260905-P001-S11 | True        | Y  | 1.0        | 20260920          | 2026-09-20T22:56:40+08:00 | ingest     | 23
  隔离位 | ZEN-20260920-P001-S14 | True        | Y  | 1.0        | 20260920          | 2026-09-20T22:57:38+08:00 | ingest     | 23
  隔离位 | ZEN-20260920-P001-S15 | True        | Y  | 1.0        | 20260920          | 2026-09-20T22:57:38+08:00 | quarantine | 23
  隔离位 | ZEN-20260925-P001-S16 | True        | Y  | 1.0        | 20260920          | 2026-09-25T23:40:15+08:00 | quarantine | 26
  隔离位 | ZEN-20261002-P001-S17 | True        | Y  | 1.1        | 20260920          | 2026-10-02T01:57:47+08:00 | quarantine | 27
```

**缺键非解析假象**——用原样字节独立复核（不经 `json` 模块）：

```
  ZEN-20260830-P001-S02: 字节含 b'quarantined' = False  文件大小=1,533B  行尾CRLF=True  BOM=False
  ZEN-20260830-P001-S03: 字节含 b'quarantined' = False  文件大小=1,537B  行尾CRLF=True  BOM=False
  ZEN-20260830-P001-S04: 字节含 b'quarantined' = False  文件大小=1,438B  行尾CRLF=True  BOM=False
  ZEN-20260831-P001-S05: 字节含 b'quarantined' = False  文件大小=1,428B  行尾CRLF=True  BOM=False
  ZEN-20260901-P001-S06: 字节含 b'quarantined' = False  文件大小=1,429B  行尾CRLF=True  BOM=False
  ZEN-20260905-P001-S08: 字节含 b'quarantined' = True   文件大小=1,524B  行尾CRLF=True  BOM=False
  ZEN-20260906-P001-S12: 字节含 b'quarantined' = True   文件大小=1,502B  行尾CRLF=True  BOM=False
  ZEN-20260911-P001-S13: 字节含 b'quarantined' = True   文件大小=1,491B  行尾CRLF=True  BOM=False
```

⇒ 顺带坐实：**17 件定稿全部无 BOM**。W3 复核函 §4.3 提的 BOM 地雷（`registry_tx.py:206` 写 `utf-8-sig` vs `congci_pipeline.py:367` 读 `utf-8`）落点是**撤回者判定源**，**不落在 `qc.json` 读路径**（`_qc_verdict:342` 同为 `encoding="utf-8"`，但被读件无 BOM ⇒ 现势不咬）。

---

## 三、附报①：缺键件的版本分布 —— ⭐**无版本分界，版本豁免条款不可实现**

```
【附报①】缺键件 = 5 件；按版本三元组分布
  归档位: 5 件
    qc_version='1.0' / threshold_version='20260920' → 5 件
  隔离位: 0 件
  缺键件 generated_at 分布：
    2026-09-20 → 5 件
  全库（17 件）版本三元组分布，供切齐备率：
    qc_version='1.0' / threshold_version='20260920' → 15 件，其中有键 10 件
    qc_version='1.1' / threshold_version='20260920' → 2 件，其中有键 2 件
```

**派工函问的是「缺键是否集中在早期版本——若是，须给 `qc_version`／`threshold_version` 的分界」。实测答案是：不集中在任何版本，给不出分界。**

| 候选分界键 | 能否分开「缺键 5」与「有键 12」 | 实测依据 |
|---|---|---|
| `qc_version` | ❌ **不能** | `1.0` 同时覆盖缺键 5 件与有键 10 件 |
| `threshold_version` | ❌ **不能** | 全 17 件一律 `20260920`，零区分度 |
| `generated_at` | ❌ **不能** | 缺键 5 件（22:56:38–39）与有键 7 件（22:56:39–40）**在同一批次同一两秒窗口内交错**，区间重叠 |
| 目录分区 | ◐ 部分 | 缺键全在归档位；但归档位内部 5 缺／4 有，仍分不开 |
| **`scene` 键是否在** | ✅ **能，且完全等价** | 见下 |

**真正的判别键**（21 键 vs 23 键的差集，实测）：

```
  缺键件键集大小 = 21   有键件键集大小 = 23
  有键件独有（缺键件没有）= ['quarantined', 'scene']
  缺键件独有（有键件没有）= []
```

⇒ **`quarantined` 与 `scene` 是同时被加进 schema 的一对**；缺 `quarantined` 的件必然也缺 `scene`，反之亦然（本 17 件population 内**完全等价**，可互为代理判据）。

### ⚠ 由此得到一条新事实：`qc_version` 在 schema 变更时未升版

`quarantined`／`scene` 两键被加进定稿 schema，但 `qc_version` 仍是 `1.0`、`threshold_version` 仍是 `20260920`。⇒ **版本字段失职**：它无法区分两代 schema。

**对乙案的直接后果**：派工函设想的「历史豁免条款」若按 `qc_version`／`threshold_version` 写（这是最自然的写法），**写不出来**——按 `qc_version<'1.1'` 豁免会把 10 件本来有键的件一起豁免掉（过度豁免），按 `=='1.0'` 同样过度；而不豁免则 5 件真坐翻 unknown。**唯一可用的豁免判据是「键在不在」本身，即逐件点查，不能用版本代理。**

---

## 四、附报②：缺键件里有多少已喂进持久脑 —— ⭐**5 件全部已喂**

```
【附报②】缺键件里有多少已喂进持久脑（按 id 点查索引，不整树扫 02_raw）
  索引行数 = 24；不同 session_key = 24
  状态分布 = {'committed': 24}
  点查对象 = 缺键件 5 件
    归档位 ZEN-20260830-P001-S02: 已喂 → v1
    归档位 ZEN-20260830-P001-S03: 已喂 → v2
    归档位 ZEN-20260830-P001-S04: 已喂 → v3
    归档位 ZEN-20260831-P001-S05: 已喂 → v5
    归档位 ZEN-20260901-P001-S06: 已喂 → v6
  ⇒ 缺键且已 committed 入持久脑 = 5 件
```

**5／5，零例外。** 且它们占的是谱系链最前端（v1、v2、v3、v5、v6）——**脑体最早的 6 个版本里有 5 个的准入依据缺 `quarantined` 记录**。

**对「回灌一律一坐一喂」口径的影响：无。** 一坐一喂约束的是**喂序与基线推进**（缺陷④ 的成因），与定稿字段齐备性是两条正交的轴；本次 ④ 正修已把 base 谱系落定移进脑锁内，24 行账本的 `base[i]==result[i-1]` 已实测逐环相扣。**这 5 坐已在链上、已沉定，不追溯、无须重喂**（「从此」路径依赖，重喂会换脑 sha、白丢 24 坐沉降顺序）。

⇒ 但这 5 坐**留下一个不可自愈的审计缺口**：它们的准入当时读的是定稿，而定稿里没有 `quarantined` 字段，`_qc_verdict:345` 的 `bool(q.get("quarantined"))` 把 `None` **静默转成 `False`**。也就是说——

> **现势代码无法区分「明确记录为不隔离」与「从未记录」**：S08/S12/S13/S18 四坐是定稿明写 `False`，S02–S06 五坐是缺键被 `bool(None)` 兜成 `False`，两者在索引与准入结果上**完全同形、事后不可分辨**。乙案的三态（有键／缺键＝unknown／隔离）正是要拆开这一对，**而拆开就会让这 5 坐失去既有准入依据**。

---

## 五、附报③：隔离位里 `quarantined` 缺失或为 False 的件 —— **零反例**

```
【附报③】隔离位 = 8 件；其中 quarantined 缺失或不为 True = 0 件
  （零反例 ⇒ 『人工挪目录但定稿没跟上』这一新事实**不成立**）
  隔离位全件 quarantined 实值逐行：
    ZEN-20260905-P001-S07: True (bool)
    ZEN-20260905-P001-S09: True (bool)
    ZEN-20260905-P001-S10: True (bool)
    ZEN-20260905-P001-S11: True (bool)
    ZEN-20260920-P001-S14: True (bool)
    ZEN-20260920-P001-S15: True (bool)
    ZEN-20260925-P001-S16: True (bool)
    ZEN-20261002-P001-S17: True (bool)
```

**8／8 全 `True`、全 `bool` 类型 ⇒ 派工函设想的那条反例（人工挪了目录但定稿没跟上）不成立。** 隔离位的定稿与目录位置**完全一致**。

### 但同一张明细表里读到一条独立事实：`recommend` 与 `quarantined` 在 5 件上不一致

隔离位 8 件中，`recommend=ingest` 的有 **5 件**（S07、S09、S10、S11、S14），`recommend=quarantine` 的只有 **3 件**（S15、S16、S17）——而这 8 件的 `quarantined` 全是 `True`。

⇒ **QC 判据本身认为这 5 坐可以入库，把它们放进隔离区的不是 QC，是操作员手打的旗标。** 这与本窗 10-08 只读筛查的结论（`20261008_QC入库乱象只读筛查与裁定123执行_v1.md`：「落隔离纯靠操作员手打 `--type test`，非 QC 之功」）**互为独立佐证**——那次是从合成信号签名侧看，这次是从定稿字段侧看，两条路撞到同一事实。

⇒ 对乙案的意义：**隔离位不是「QC 拒件区」，是「人工否决区」**，两者语义不同。乙的三态若把 `quarantined=True` 一律当「QC 判拒」处理，会把这 5 坐的成因记错。建议乙的 unknown／拒 两态在留痕里**分记 `recommend` 与 `quarantined` 两个来源**，不要合成一个布尔。

---

## 六、⭐范围外承重发现：24 坐已喂里 **15 坐根本没有定稿**（派工函未预见）

派工函把风险框定为「历史**归档位**定稿缺 `quarantined` 字段」。实测发现**主要风险不在这里**。

按 `npz_path` 点查索引 24 行 committed（不整树扫，逐件 `os.path.exists`）：

```
=== 索引 24 行 committed 的 npz_path 分区（点查索引，不扫树）===
  committed 行数 = 24
    其他：D:/Project/zhiguanAI/muse2-repo/muse2-master → 15 行
    02_raw 归档位 → 9 行
```

两类坐的准入来源**完全不同**（索引侧留痕，原样）：

```
=== 非ZEN 15 行的准入字段 ===
  qc_source      分布 = {'assess_cached': 15}
  qc_recommend   分布 = {'ingest': 15}
  participant    分布 = {'': 15}
  scene          分布 = {'': 15}
  session_type   分布 = {'': 15}
  ZEN 9 行对照：
  qc_source      分布 = {'03_quality_control/qc.json': 9}
  qc_recommend   分布 = {'ingest': 9}

=== 非ZEN 15 行的 npz 同目录是否存在 qc.json（仅逐件 os.path.exists 点查，零递归）===
  ⇒ 同目录/同 sid 点查命中 qc.json = 0/15
=== npz 是否仍在盘 ===
  在盘 = 15/15      ZEN 9 行在盘 = 9/9
```

且这 15 行的 `session_key` 不是 `ZEN-*` 而是 **64 位 sha256**（如 `0f0c92b2a3101e41…`），逐行原样：

```
  v4,v7,v8,v9,v10,v11,v14,v15,v16,v17,v18,v19,v20,v22,v23 ← 目录均为 muse2-master/report
  v1,v2,v3,v5,v6,v12,v13,v21,v24 ← ZEN-2026083…S02/S03/S04、…S05、…S06、…S08、…S12、…S13、ZEN-20261006-P001-S18
```

### 这 15 坐是怎么被准入的（源码坐实，非推断）

`congci_pipeline.py` 工作区 `_qc_verdict`（HEAD 与工作区同为 `318-353`）：

```python
    d = os.path.dirname(os.path.abspath(npz_path))
    if os.path.basename(d).startswith("ZEN-"):        # :329
        ...两处探针...                                 # :335-340
        if qj is not None:
            ...return {..., "quarantined": bool(q.get("quarantined")),   # :345
                    "source": "03_quality_control/qc.json", ...}
    import qc_pipeline
    r = qc_pipeline.assess_cached(npz_path)            # :349
    return {"recommend": r.get("recommend"),
            "quarantined": r.get("recommend") == "quarantine",   # :351
            "source": "assess_cached", ...}            # :352
```

⇒ 这 15 坐的 npz 目录名是 `report`，**不以 `ZEN-` 开头**，`:329` 的判断直接不成立 ⇒ **两处定稿探针连走都不会走**，径直落到 `:349` 的 `assess_cached` 现算回落。而回落口径 `:351` 把 `quarantined` 由 `recommend` **派生**（`ingest == quarantine` → `False`）。

**⇒ 这 15 坐的 `quarantined=False` 是派生默认值，不是任何人工判定的记录。** 它比归档位那 5 坐缺键**更弱一档**：那 5 坐至少有一份真定稿，只是少一个字段；这 15 坐**连定稿都不存在于本次普查的扫描根内**。

### ⚠ 边界声明（如实划界，请 W3 定是否扩权）

- 本次**未扫** `muse2-repo/muse2-master/` 树：派工函授权的扫描根只有 `03_quality_control/`，`02_raw/` 只许按 id 点查。上面对 muse2 侧的三次查询**全部是点查**（`os.path.exists` 于索引给出的 `npz_path` 及其同目录 `qc.json`），**零 `os.walk`、零 `glob`、零目录列举**。
- ⇒ 因此**「这 15 坐在别处是否有定稿」本件判为『未核』**，不声称无。要答这一问须扩权到 muse2 树（10-08 筛查件 §一 记该池为「暂存池 135 件」，是否即此路径**本件未核**，不敢代认）。
- 该 15 行的 `qc_source='assess_cached'` 恰好是派工函边界 ④ 明令**禁用**的派生值路径。本件**没有**用任何 `.qc_cache` 值做判定（附报①②③ 全部直读 `qc.json` 原文件）；这里引用 `assess_cached` 只是**如实报告索引里记着的准入来源字符串**，不是采信其派生结论。

---

## 七、对乙案的量化影响（普查的实际交付）

乙案三态规则（有键→用其值／缺键→unknown／unknown 不喂）落到现势数据上的**逐坐结果**：

| 群体 | 坐数 | 有定稿 | 定稿有 `quarantined` 键 | 乙案判定 | 占比 |
|---|---|---|---|---|---|
| 归档位（`02_raw`，`qc_source=03_quality_control/qc.json`） | 9 | 9 | 4（全 `False`） | 4 通过／**5 unknown** | — |
| 隔离位（`quarantine/`） | 8 | 8 | 8（全 `True`） | 8 拒（正确） | — |
| **已喂持久脑合计** | **24** | **9** | **4** | **4 通过／20 unknown** | **unknown 83.3%** |
| ├ 归档位缺键 | 5 | 5 | 0 | unknown | 20.8% |
| └ 无定稿（`assess_cached`） | 15 | **0** | — | **unknown（构造上必然）** | 62.5% |

**只有 4 坐（S08、S12、S13、S18）能在乙案下干净通过。**

### 三条结论（按承重排序）

1. ⭐**版本豁免条款不可实现**（§三）：`qc_version`／`threshold_version`／`generated_at` 三个候选分界键**全部零区分度**，唯一可用判据是「键在不在」的逐件点查。乙案若打算写历史豁免，**必须写成键级白名单（点名 5 个 sid）或写成「无定稿即豁免」的态级规则，不能写成版本条件**。
2. ⭐**豁免范围必须扩到「无定稿」这一态**（§六）：派工函设想的风险面是 9 坐归档位，实测**主要风险面是 15 坐无定稿**，占已喂 62.5%。乙案只处理「缺键」不处理「无定稿」，落地即让 24 坐里 20 坐失去准入依据 ⇒ **正是派工函担心的「全线停摆」，且比预估严重**。
3. **隔离位是干净的**（§五）：8/8 全 `True`，无反例，乙案在隔离位这一侧**不需要任何豁免**；但需按 §五 建议**分记 `recommend` 与 `quarantined` 两个来源**，否则会把 5 坐「人工否决」误记成「QC 判拒」。

---

## 八、只读边界自证（原样输出）

```
【只读自证】
  命中件数 before=17 after=17
  (size, mtime_ns, sha256_16) 逐件比对：变更件数 = 0
  结论 = ✓ 全部逐字节未变，零写入
  本次运行未 import refresh_qc（sys.modules 含 refresh_qc = False）
  本脚本全部 open() 模式： ['', '"rb"', 'encoding="utf-8"']
CENSUS_OK
```

逐条对派工函 §四 六项硬边界：

| # | 边界 | 本件实况 |
|---|---|---|
| 1 | 只读 | 跑前跑后对全部 17 件取 `(size, mtime_ns, sha256_16)` 快照，**变更件数 = 0**；全部 `open()` 仅读模式；未 import `refresh_qc`、未调 `write_qc_json`、未跑 `--drain`／未入队／未喂脑 |
| 2 | 判据/阈值一字不动 | 未改 `qc_pipeline.py`；`QC_VERSION=1.1`／`THRESHOLD_VERSION=20260920` 全程只读引用；本件不评阈值合理性 |
| 3 | 禁从项目根无差别递归 | `os.walk` **只对** `D:\Project\Zen-EEG\03_quality_control\` 调用一次；`02_raw`／muse2 侧**仅逐件 `os.path.exists` 点查**（§六 已划界） |
| 4 | 禁走 `.qc_cache` 派生值 | `命中 .qc_cache 子树 = 0 处`，且脚本对该目录名 `dirnames[:]=[]` 显式跳过；全部判定直读 `qc.json` 原文件 |
| 5 | 不粘波形数值序列、零出网 | 全文只有计数、版本三元组、sid、路径尾段；**无任何 EEG 数值序列**；无网络调用 |
| 6 | 勿动共享文 | 未改协调正本、未改 `AI-开工入口.md`、未改 `refresh_qc.py`；**未提交 `巡检日志-W1.txt`**（见 §九） |
| 7 | 批 B 主体禁开工 | 本件**纯只读**，未改 `congci_pipeline.py` 一个字节（该文件在途 +45 行系上一批②④正修，与本普查无关且未定案入库） |

---

## 九、本件不做（划界，防越权读）

- **不改** 任何 `qc.json`、不补写缺失的 `quarantined`／`scene` 键（补写＝改历史定稿，属不可逆动作，须法师明示）。
- **不动** `refresh_qc.py`／`qc_pipeline.py`／`write_qc_json`；不升 `THRESHOLD_VERSION`。
- **不裁定** 乙案要不要豁免、豁免怎么写——按协调正本 §19.4，本件只交**实测事实**，收敛与提请归 W3。
- **不扩权扫** `muse2-repo/muse2-master/` 树；那 15 坐「别处是否有定稿」判为**未核**，候 W3 定是否另派。
- **不提交、不 push**。本件与回执件候法师逐批放行；`巡检日志-W1.txt` 按派工函 §四.5 **本批不提交**（该档现有非本次会话的在途行，须先逐行读 diff 认署名——本窗只追加自己署名的一行，不代提交他窗在途件）。
- **不宣称** 乙案前置已收口；本件是**输入**，不是结论。

---

## 十、附：本次一并复算的锚点（供回执 A 点引用，双基线 AST 取函数体首末行）

```
锚点                                HEAD 区间         工作区 区间  位移
_resolve_npz                      286-313        286-313
_qc_verdict                       318-353        318-353
_participant_withdrawn            356-371        356-371
admit                             374-395        374-395
enqueue                           409-483        413-491  +4
_claim_acquire                    499-527        507-535  +8
_claim_release                    530-541        538-549  +8
_commit_row                       546-560        554-575  +8
_brain_lock                       565-568        580-583  +15
_process_row                      611-738        626-764  +15
recover_pending                   764-830        790-856  +26
main                              911-941        937-986  +26
TOTAL_LINES                          945            990   +45
```

脑锁区段实测（我原设计件声明「工作区 633–710／HEAD 623–700」，现势）：

```
  HEAD   :565  def _brain_lock():          工作区 :580
  HEAD   :633  with _brain_lock():         工作区 :648
  HEAD   :710  os.replace(cand, bp)        工作区 :736      # 事务②：候选提升为正式脑
  HEAD   :789  with _brain_lock():         工作区 :815      # recover_pending 内
  HEAD   :802  os.replace(cand, bp)        工作区 :828
```

*W1·AI-019 敬上。数字全部原样贴出、可一条命令复现；三条结论只报实测事实与量化影响，**乙案怎么写由 W3 收口后报法师**。*
