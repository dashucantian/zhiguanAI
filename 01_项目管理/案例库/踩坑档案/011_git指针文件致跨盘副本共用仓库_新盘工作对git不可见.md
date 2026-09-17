# 坑 011：`.git` 是指针文件而非目录，跨盘复制项目致多副本共用一个仓库、新盘工作对 git 不可见

> 发现日期：2026-09-18 ｜ 发现窗口：W3（迁移执行）｜ 建卡：AI-007（W2 文档线，2026-09-18 续接窗口，依职责入档）
> 类型：环境类（git 仓库结构 + OneDrive）｜ 危害等级：**极高**——不是报错，而是**静默地让整整两天的多窗口工作在版本控制里"不存在"**，且三副本共享同一 index，随时可能互相覆盖

## 现象

2026-09-17～18，W1／W2／W3 三个窗口在 `D:\Project\zhiguanAI` 连续作业两天，产出了 S1 缺陷修复、书稿补骨架五件、评审材料等大量文件。期间在 D 盘跑 `git status`：

```
On branch master
nothing to commit, working tree clean
```

**"干净"是假的。** D 盘那 3.2 GB 内容（含三个窗口两天的全部产出）在 git 眼里根本不存在——不是"未跟踪"，是 git 压根没在看这棵树。直到 09-18 排查迁移，才查出 09-17 起的所有工作从未进入版本控制。

更危险的隐藏面：D 盘当时有三份从 C 盘复制来的副本（`zhiguanAI`／`zhiguanAI_backup_20260917`／还有一份），它们**共用同一个仓库、同一个 index**。任一份里跑 `git add`/`commit`，改的是同一份暂存区，彼此会静默打架。

## 根因

项目的 `.git` **从来不是一个目录，而是一个 51 字节的纯文本指针文件**（git 术语叫 gitfile），内容形如：

```
gitdir: C:/Users/tiand/zg-git-repos/zhiguanAI.git
```

真实仓库被单独放在 `C:\Users\tiand\zg-git-repos\zhiguanAI.git`，且它的 config 写死了：

```
[core]
    worktree = C:/Users/tiand/OneDrive/zhiguanAI
```

于是把项目目录**复制**到 D 盘时，复制走的是那 51 字节的指针文件，不是仓库本体。三份 D 盘副本的指针全指向 C 盘同一个仓库，而那个仓库认定自己的工作树（worktree）是 C 盘那个目录。结果：

- 在 D 盘跑 `git status` → git 顺着指针找到 C 盘仓库 → 仓库按 config 比较的是 **C 盘** 的文件 → **D 盘的改动看不见，还报"clean"**；
- 三份 D 盘副本共享同一 index → 并发提交互相污染（后来 09-18 的 KZ-021 代提交事故，正是这种"共享暂存区"土壤的延伸）。

一句话：**复制一个含 `.git` 的目录 ≠ 复制一个仓库。** 如果 `.git` 是 gitfile，复制出去的只是一个"遥控器"，仓库本体和它认定的目标目录还留在原地。

## 决定性判据（可复用——三步确诊）

在可疑的项目根目录跑，任何一步异常即中招：

```powershell
# 1. 工作树顶层是不是当前目录？（中招时会返回别的盘符路径）
git rev-parse --show-toplevel
git rev-parse --show-prefix

# 2. 仓库本体在哪？（中招时 --git-common-dir 指向外部绝对路径，而非本地 .git）
git rev-parse --git-dir
git rev-parse --git-common-dir

# 3. .git 是目录还是指针文件？core.worktree 有没有被写死？
(Get-Item -LiteralPath '.git').PSIsContainer     # 正常=True；中招=False 且 Length≈51
git config core.worktree                          # 正常=空；中招=某个绝对路径
```

**最强的一条**：`(Get-Item '.git').PSIsContainer` 为 `False` 且大小仅几十字节 → `.git` 是 gitfile；再看 `git config core.worktree` 非空 → 仓库的工作树被钉死在别处。**两条件同时成立，则本目录的一切文件对 git 不可见，且这份"不可见"是复制带来的。**

## 解法（迁移到自包含仓库）

本次由 W3 按法师裁定的六阶段执行（要点）：

1. **先把仓库本体收回目录内**——把外部 `zg-git-repos\zhiguanAI.git` 变成项目内的自包含 `.git` **目录**，去掉指针文件；
2. **删掉 config 里的 `core.worktree = ...` 覆盖行**——让仓库的工作树默认就是 `.git` 所在目录；
3. **重建 index**——`git status` 重新以本目录文件为准比对；
4. 迁移前用 `Move`/复制做全量备份（本次备份在 `D:\_迁移备份_20260918\`，可完整回退），且**保留原仓库与原指针文件原件**（指针改名留存，不删）；
5. 迁移后**必跑上面"三步判据"复验**：`--show-toplevel` = 当前目录、`.git` 为目录、`core.worktree` 为空、`git fsck` 无新增异常。

**本卡建卡时（09-18）已在新工作区实测四项判据全绿**：`--show-toplevel` = `D:/Project/zhiguanAI`、`.git` 为容器目录、`core.worktree` 为空、HEAD 计数与迁移后一致。

## 排障顺序（可复用）

新盘/复制来的目录里 `git status` 报 clean，可你明明改了文件时：

1. **别信"clean"**——先 `git rev-parse --show-toplevel`，看它指的是不是你脚下这个目录；
2. **查 `.git` 是目录还是文件**（`PSIsContainer` + 字节数），几十字节即指针；
3. **查 `core.worktree`**，非空即被钉死到别处；
4. 确认中招后**不要在任一份副本里 `git add`**（会污染共享 index），先停手、查清有几份副本共用同一仓库；
5. 报法师，按"备份→收回仓库→删 worktree 覆盖→重建 index→复验"迁移，**迁移动作涉仓库结构，属破坏性范畴，AI 不擅自执行**。

## 教训

**① "目录复制 = 仓库复制"是错觉。** 只要 `.git` 是 gitfile（外部仓库、worktree 覆盖、`GIT_DIR`/`GIT_WORK_TREE` 环境变量、submodule 里的 `.git` 文件都是这个形态），复制目录只带走遥控器。团队把项目从一处拷到另一处开工前，第一件事应是跑一遍 `--show-toplevel` 确认仓库跟着走了。

**② 静默的"clean"比报错危险一个量级。** 本次错误不抛异常、不警告，返回一个"一切正常"的 `nothing to commit`。这正是本项目"静默错误"家族的新成员（同族：坑 009 后端 recording 而前端空白、坑 010 字符数静默虚高、KZ-021 提交归因静默错误）——**判据"看起来通过了"不等于判据在测你想测的那个对象**。

**③ 测量作用域与被测对象不一致，就把结果当事实——与坑 010 同源，第三次复现。** `git status` 没错，错的是"我以为它在检查 D 盘"。凡是"检查/校验/计数"类结论，先问一句：**它的执行上下文（cwd / worktree / 解码口径 / 进程启动目录）真的是我以为的那个吗？** 同族还有坑 010 附记的 `.NET ReadAllText` 相对路径解析到进程启动目录（不受 PowerShell `cd` 影响）。

**④ 云同步目录（OneDrive/iCloud/Dropbox）放 git 仓库是隐患温床。** 占位符水合失败会让 git 读到空壳、文件"被提供程序取消"；本次仓库长期住在 `OneDrive\` 下、又叠了个外部 git-dir + worktree 覆盖，双重脆弱。教训：**git 仓库放纯本地、非云同步目录**（本次迁至 `D:\Project\zhiguanAI` 即为纠偏）。

## 关联

- 坑 010（PowerShell 字符数口径）／开工规约 §五 数值测量口径 —— **同一根因家族：测量作用域/口径与被测对象不一致**，本坑是该模式的 git 版本
- 坑 009（SSE 静默黑屏）—— 同属"静默错误"家族（见教训②）
- KZ-021（共享 index 下的代提交事故）—— 本坑"三副本共用一仓库一 index"是其土壤
- `01_项目管理\20260911_版本控制归因与OneDrive隔离方案分析稿.md` —— 迁移方案的完整论证与本坑的六阶段处置
- 项目记忆《🔴项目已迁出OneDrive至D盘》—— 本次迁移全过程记录
- 决策 D1（文档真源）—— 迁移后真源由 `OneDrive\zhiguanAI` 变更为 `D:\Project\zhiguanAI`

---

## English Summary

**Symptom:** For two days (09-17 to 09-18) three agent windows worked inside `D:\Project\zhiguanAI`, yet `git status` there reported a clean tree. None of the ~3.2 GB of work had actually entered version control. Worse, three copies on D: silently shared one repo and one index.

**Root cause:** The project's `.git` was never a directory — it was a 51-byte gitfile (`gitdir: C:/Users/tiand/zg-git-repos/zhiguanAI.git`), and that external repo's config hard-set `core.worktree = C:/Users/tiand/OneDrive/zhiguanAI`. Copying the project directory copied only the pointer file, so every D: copy pointed back at the C: repo, which compared C:'s files. D:'s files were invisible to git, and "clean" was a lie.

**Decisive checks (reusable):** `git rev-parse --show-toplevel` (should be your current dir), `--git-common-dir` (should be a local `.git`, not an external path), `(Get-Item .git).PSIsContainer` + `.Length` (~51 bytes ⇒ gitfile), and `git config core.worktree` (non-empty ⇒ worktree pinned elsewhere). If PSIsContainer is False and core.worktree is set, this directory's files are invisible to git.

**Fix:** Move the git object store back inside the project as a self-contained `.git/` directory, delete the `core.worktree` override line, rebuild the index, and re-verify all four judgments. Back up first; treat the repo restructure as a destructive, master-approved operation. As of this card's writing (09-18), all four checks pass on the new workspace (`--show-toplevel` = D:\Project\zhiguanAI, `.git` is a directory, no worktree override).

**Lessons:** (1) Copying a folder containing `.git` does not copy a repository if `.git` is a gitfile — you copy the remote control, not the TV. (2) A silent "clean" is far more dangerous than an error — this belongs to the project's growing family of silent failures (see pitfalls 009/010, KZ-021): a check "passing" doesn't mean it checks the object you intended. (3) A measurement whose execution scope (cwd / worktree / decoding) differs from the assumed target yields false facts reported as truth — the third recurrence of the same root cause as pitfall 010. (4) Keeping a git repo inside a cloud-synced folder (OneDrive/iCloud) is a latent hazard (placeholder hydration failures, "provider cancelled"); repos belong in a purely local, non-synced directory — which this migration corrected.
