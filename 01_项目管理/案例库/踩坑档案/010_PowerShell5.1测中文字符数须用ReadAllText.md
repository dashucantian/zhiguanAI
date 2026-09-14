# 坑 010：PowerShell 5.1 测中文字符数用 `Get-Content -Raw` 致数值虚高约 25%，险把正确文档改错

> 发现日期：2026-09-14 ｜ 发现窗口：W3（制度与机动）｜ 建卡：AI-001（W3 兼 W2 文档职责，法师 2026-09-14 指令入档）
> 类型：环境类（Windows PowerShell 5.1 编码）｜ 危害等级：**高**——不是报错，而是**静默给出错误数字**，且错误方向会诱导 AI「更正」一份本来正确的文档

## 现象

2026-09-14 复核《上下文管理落地方案分析稿》§二 的「开工必读体量」实测表时，用 PowerShell 重测七份必读文档字符数，结果与方案稿（09-13 撰写）记载**全部不符**：

| 文档 | 方案稿记载 | 本轮 `Get-Content -Raw` 测得 | 偏差 |
|---|---|---|---|
| 分工与决策日志 | 27,266 | 34,036 | +6,770（+24.8%） |
| 书稿勘误与订正台账 | 9,881 | 12,310 | +2,429（+24.6%） |
| AI代理身份登记 | 6,472 | 8,022 | +1,550（+24.0%） |
| 词汇命名映射表 | 5,687 | 7,209 | +1,522（+26.8%） |
| AI-开工入口 | 3,221 | 4,122 | +901（+28.0%） |
| 模型与工具路由表 | 2,798 | 3,402 | +604（+21.6%） |
| 判语 13 条合计 | 31,101 | 34,773 | +3,672（+11.8%） |

七项**无一例外全部偏大 12%–28%**，合计虚高 17,448 字符（约 +20%）。

**最危险的地方**：数字「整齐地全偏大」，看起来像「方案稿当初系统性少算了 20%」，于是我据此判断方案稿数字错误，**准备动手把正确的数字改成错误的**。

## 根因

Windows PowerShell 5.1 的 `Get-Content -Raw` **不假定 UTF-8**。对**无 BOM 的 UTF-8** 文件，它按系统 ANSI 代码页（简中 Windows 为 **GBK/936**）解码。UTF-8 编码的一个汉字占 3 字节，被 GBK 按 2 字节一组切分 → **一个汉字被拆成 1.5 个「字符」**，字符数虚高约 25%（3÷2＝1.5，即 +50% 的字节数被误读为字符；实测偏差 12%–28% 与文件中西文、标点、数字占比相关——纯中文段落偏差趋近 +50%，含大量 ASCII 的表格与代码块偏差较小，这正是七项偏差率不一致的原因）。

项目内的 `.md` 文件**绝大多数无 BOM**，故全线中招。

**为什么 09-13 的方案稿数字是对的**：当时用的是 `[System.IO.File]::ReadAllText()`（.NET 默认按 UTF-8 探测解码），口径正确。

## 决定性验证方法（可复用）

同一文件用两种口径并测，看差值方向：

```powershell
$p = "01_项目管理\止观AI项目分工与决策日志.md"
$full = (Resolve-Path $p).Path

# 错误口径（ANSI/GBK 解码，虚高）
(Get-Content -LiteralPath $full -Raw).Length

# 正确口径（.NET 默认 UTF-8 探测）
[System.IO.File]::ReadAllText($full).Length

# 交叉锚：字节数（不受解码影响，最硬的证据）
(Get-Item -LiteralPath $full).Length
```

实测该文件：`Get-Content -Raw` → 34,036；`ReadAllText` → **27,268**；字节数 → 55,984。

**字节数是最强判据**：55,984 字节 ÷ 27,268 字符 ≈ **2.05 字节/字符**。中文 UTF-8 是 3 字节/字、ASCII 是 1 字节/字，中英混排文档落在 2.0 附近完全合理；而 55,984 ÷ 34,036 ≈ 1.64 字节/字符，**对 UTF-8 中文文档物理上不可能**（除非全篇 ASCII，但那样就不该有偏差）。一条除法即可判死。

另一条独立锚：`git cat-file -s "HEAD:<path>"` 给出已提交版本字节数（实测 51,032），与工作区 55,984 同量级、差异可由未提交改动解释——**若字符数真差 20%，字节数不可能只差 10%**。

## 解法

**规则：在本项目测任何含中文的文件字符数，一律用 `[System.IO.File]::ReadAllText($绝对路径)`，禁用 `(Get-Content -Raw).Length`。**

```powershell
# ✅ 正确
$chars = [System.IO.File]::ReadAllText((Resolve-Path $rel).Path).Length

# ✅ 更明确（强制 UTF-8，不依赖 .NET 探测）
$chars = [System.IO.File]::ReadAllText($abs, [System.Text.Encoding]::UTF8).Length

# ❌ 禁用：无 BOM 的 UTF-8 会被按 GBK 解码
$chars = (Get-Content -LiteralPath $rel -Raw).Length
```

若要继续用 `Get-Content`，必须显式指定编码：

```powershell
# ⚠️ 可用但易漏：PS 5.1 支持 -Encoding UTF8
$chars = (Get-Content -LiteralPath $rel -Raw -Encoding UTF8).Length
```

**更稳的做法**：测字符数的脚本写成 `.py` 文件用 Python 跑（`open(p, encoding='utf-8')`），绕开 PowerShell 编码层——与坑 005／交接说明 §7.2「内联 `python -c` 引号会被吞 → 一律写 .py 脚本」是同一处置思路。

## 排障顺序（可复用）

数字与既有记载不符时，**先怀疑自己的测量口径，再怀疑记载**：

1. **换一种独立口径重测**（字节数 / .NET ReadAllText / Python len）——三口径若不一致，问题在工具不在数据；
2. **算字节数÷字符数**，看是否落在该编码的物理合理区间（UTF-8 中英混排 ≈ 1.8–2.6）；
3. **查文件有无 BOM**（`[System.IO.File]::ReadAllBytes($p)[0..2]`，EF BB BF 为有）；
4. **看偏差是否有规律**——「全部同向偏大/偏小」几乎必然是系统性口径问题，**不是**数据被改过（数据被改通常是零星几项变动）；
5. 以上都排除后，才查文件是否真的变了（`git diff --stat`、`LastWriteTime`）。

⚠️ 反面教训：**偏差「整齐」不是可信度的加分项，恰恰是口径错误的指纹。** 本轮我最初把「七项全偏大约 20%」当成「方案稿系统性算错」的证据，方向完全反了。

## 教训

**① 同一批数字「整齐地全错」，优先怀疑测量口径，不怀疑数据源。** 系统性偏差是工具问题的特征，随机偏差才是数据变动的特征。本轮若顺着「方案稿错了 20%」去改，会把一份经 GPT 评审、已交付的文档改坏，且错误会被后续所有窗口继承。

**② 任何数值断言都要有独立第二口径。** 这正是开工规约 §五.4「凡通篇无一处存疑、每个数字都精确的方案，默认有问题、优先核校」的**反向**用法：核校是必要的，但**核校本身也要被核校**——本轮的错误不在「没核校」，而在「核校用了错的尺子」。方案稿当初数字精确，不是可疑，是因为用了正确口径。

**③ 静默错误比报错危险一个量级。** `Get-Content -Raw` 不抛异常、不警告，返回一个「看起来正常」的整数。这类故障无法靠 try/catch 或退出码发现，只能靠**预期值比对**与**多口径交叉**。同型：坑 009 的「status 正常但界面空白」、交接说明 §7.1 的九个判据 bug、D26 的「DictWriter 静默抹掉新增列」——本项目「静默错误」已累计十余例。

**④ 编码问题是 Windows PowerShell 5.1 的系统性风险面，不止字符数。** 同一根因（不假定 UTF-8）还会影响：`Select-String` 中文匹配失效、`Out-File` 默认写出 UTF-16 LE、中文文件名在 git 输出里被转义成 `\351\241\271` 八进制（须 `git config core.quotepath false`）。凡在 PS 5.1 下处理中文文本，**先问一句「这里的编码假定是什么」**。

**⑤ 差点连带误判「文件不存在」——凭记忆核查的又一次再现。** 本轮我同时误报「3 项必读文件不存在」，实为拿**记忆里的旧版规约路径**（`02_架构与理论\理论纳入\判语档案.md`、根目录 `MEMORY.md`）去测，而现行规约 §一 实际指向 `案例库\决策判语\`（13 个分散文件，命名 `001_…`）与《分工与决策日志》，**全部存在**。与 KZ-009（误信 `attrib +P` 能防上传）、KZ-010（Edit 吞标题）同型：**核查前必须先读现行原文，不得凭记忆构造被核查对象。**

## 关联

- 坑 005（PowerShell 5.1 引号丢失）—— 同属 PS 5.1 环境类坑，不同现象（005 是引号被吞致命令失败、**会报错**；010 是编码误判致数值虚高、**静默**）
- `01_项目管理\20260914_控制台窗口交接说明.md` §7.2「环境类坑（Windows PowerShell 5.1）」—— W1 窗口独立积累的五条同类经验，本坑为第六条
- 坑 009（SSE 静默黑屏）—— 同属「静默错误」家族，见教训③
- 开工规约 §五.4（数字精确性优先核校）—— 见教训②的反向用法
- 方案稿 §10.3（`01_项目管理\模型管理\20260913_上下文管理落地方案分析稿.md`）—— 本坑的完整自我纠错记录与七项复核对照表
- KZ-009／KZ-010 —— 凭记忆核查的同型先例，见教训⑤
- 受影响文档：方案稿 §二 实测表（**经复核确认原数字正确，未作任何修改**）

---

## English Summary

**Symptom:** While re-verifying the "required-reading volume" table in a delivered analysis doc, all seven measured files came out **12%–28% larger** than the doc's recorded figures (total +17,448 chars, ≈+20%). The uniformity made it look like the original doc had systematically undercounted — so I was about to "correct" a document whose numbers were actually right.

**Root cause:** Windows PowerShell 5.1's `Get-Content -Raw` does **not** assume UTF-8. For **BOM-less UTF-8** files it decodes using the system ANSI code page (**GBK/936** on Simplified-Chinese Windows). A Chinese character occupies 3 UTF-8 bytes but gets sliced into 2-byte GBK units, inflating the character count by roughly 25%. Most `.md` files in this project have no BOM, so every file was affected. The doc's original numbers were correct because they were taken with `[System.IO.File]::ReadAllText()`, which probes for UTF-8.

**Decisive verification:** measure with three independent means and compare. For the decision log: `Get-Content -Raw` → 34,036; `ReadAllText` → **27,268**; file size → 55,984 bytes. Bytes ÷ chars = 2.05 for the correct figure (physically sensible for mixed CJK/ASCII UTF-8) versus 1.64 for the wrong one (**impossible** for a UTF-8 Chinese document). `git cat-file -s HEAD:<path>` (51,032) provided a fourth anchor: a real 20% content change cannot coexist with a 10% byte change.

**Fix:** always use `[System.IO.File]::ReadAllText($path)` (or explicitly `…, [System.Text.Encoding]::UTF8`) for character counts; never `(Get-Content -Raw).Length`. If `Get-Content` must be used, pass `-Encoding UTF8`. Most robust: write the measurement as a `.py` script (same workaround as pitfall 005 for inline `python -c` quote-swallowing).

**Lessons:** (1) When a batch of numbers is *uniformly* wrong, suspect the measuring instrument, not the data — systematic deviation fingerprints a tooling problem, random deviation fingerprints data change. (2) Verification itself must be verified: the failure here was not "didn't cross-check" but "cross-checked with a broken ruler". (3) Silent errors are an order of magnitude more dangerous than exceptions — this one returns a plausible-looking integer with no warning, so it can only be caught by expected-value comparison and multi-method cross-checking (this project has now logged 10+ such cases). (4) Encoding assumptions are a systemic risk surface across all of PowerShell 5.1's text handling (`Select-String` CJK matching, `Out-File` defaulting to UTF-16 LE, git escaping CJK filenames — set `core.quotepath false`). (5) In the same round I also falsely reported "3 required files missing" because I tested **paths recalled from an outdated version of the rules** instead of reading the current text first — a recurrence of the KZ-009/KZ-010 pattern: never construct the object of a check from memory.
