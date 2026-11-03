# 隔离执行实验（worktree）·8779 静态闸执行记录 v1

- 任务：`TASK-20261103-02`（丙案：换载体为 `vr_gates/verify_scene_env.py`）
- 执行窗：Qoder `c73afab0`｜复核：W3 `4ef78b3e`｜验收：法师
- 起止：2026-11-03 17:50:11—17:52:25（本机 `date` 两次现取；worktree 建于其间）
- 性质：**实验记录**——验的是「隔离执行」这条路，不是脚本本身多重要

## 一、四值＋三证据

| 项 | 读数 |
|---|---|
| 起止 | 17:50:11 → 17:52:25 |
| 退码 | `git worktree add`＝0｜`git commit`（首笔）＝0｜身份核验＝见下（仓库级默认是占位，已用 `-c` 显式覆盖） |
| 摘录 | worktree `D:\Project\zhiguanAI\_analysis_tmp\wt\scene-gate`｜分支 `wt/20261103-scene-gate`｜起点 HEAD `2705109eb534bd4d7f01c8dc635221d4a56c2e56`｜首笔提交 `5982e58` |
| 主树零污染 | 主树新增未跟踪仅 `_analysis_tmp/wt/` 一项（另加本函自身，属信箱投递）；主树 HEAD 仍 `2705109e`，未动 |
| 冲突计数 | **0**（全程未读写主树任何他窗文件；`06_宣发素材` 一字节未碰） |
| 归因三层 | `5982e58 \| Qoder-c73afab0 <agent@zhiguanai.local> \| Qoder-c73afab0 <agent@zhiguanai.local> \| feat(Qoder-c73afab0·8779静态闸): 四判据落地-隔离实验首笔`；`%B` 七字段尾注齐（Author-Role／Proposal-by／Approved-by／Verified-by／Model／Session／Window） |

**身份核验（提交前实测）**：`git config user.name` → `zhiguanAI-agent`，`git config user.email` → `agent@zhiguanai.local`。**仓库级默认就是占位身份**——这正是 `a44d1e2` 落占位的根因；本次提交显式 `-c user.name='Qoder-c73afab0' -c user.email='agent@zhiguanai.local'`，提交后回执如上。

## 二、闸的四条判据与实跑结果

正跑（worktree 内，默认自动定位主树）：**PASS 四判据全过，RC=0**。

| 判据 | 实测读数 |
|---|---|
| ①三预设资产齐 | A-静坐／A-观想／A-空境 三件在盘；`scene/dist/breath/groundMode/fog/bloom` 六字段齐、类型对 |
| ②金线主调 | `ringMat` 由 `R.cGrid` 初始化＋`c_grid→cGrid` 绑定；三预设 `cGrid=#d4af5a` |
| ③上限纪律 | fog：0.03／0.045／0.0 ≤0.045；orbit：三件全 0；grain 滑杆上限 0.3、默认 0.06 |
| ④后处理不进 XR | `wantPost = … && !renderer.xr.isPresenting && …` 在位；`renderer.xr.enabled` 在位 |

**反证（同一脚本，坏素材根）**：把 A-静坐 fog 改 0.9、orbit 改 0.2、cGrid 改 `#3b4666`，grain 上限改 0.6，删掉 `!renderer.xr.isPresenting` → **实测报红 5 项、RC=1**。⇒ 四条判据都会咬人，不是恒绿。

**口径差（观察项，请 W3 定）**：控制台**默认** `cGrid=#3b4666`，金线主调是「载入 A 预设后」才生效；10-30 开工记录「地面环线统一用金线主色」指的是预设值。闸已按预设值判，并把默认值作为观察行打印；若认为控制台默认也该是金线，须另裁并改控制台，不属本闸范围。

## 三、覆盖限制（写死，防误以为可移植）

本闸读 `output/_scene_env.html`（`.gitignore:75`）与 `vr_assets/models/presets/*.json`（`.gitignore:77`），**两者都不入库** ⇒ 只在本机可跑，clone 后不可复现。脚本 docstring 与输出末行均已写明；在 worktree 内运行时靠 `git worktree list --porcelain` 首项定位主树，`--root` 可覆盖。

另：闸首版运行时踩 GBK `UnicodeEncodeError`（与 VR 总跑器同型），已在脚本内 `sys.stdout.reconfigure(encoding="utf-8")` 自解，不依赖外部环境变量。

## 四、实验本身的结论（判据 4「可合回」）

- worktree 与主树完全隔离：`git rev-parse --show-toplevel` 在树内返回 `…\_analysis_tmp\wt\scene-gate`。
- 首笔为**新文件**，主树 `vr_gates/` 干净、无人改同名件，预期 `merge --no-ff` 无冲突；**合回由 W3 做**，本窗未合并、未推送。
- 起点干净这个前提，本轮是**靠换载体**才满足的（原载体被 W2 在途改动挡住）——这本身是第一轮实验给出的真结论：**隔离要成立，先有可隔离的基线。**

## 五、边界自报

未出网、未碰飞书、未动学员数据、未改宣传内容、未碰他窗件（特别是 `06_宣发素材` 一个字节未动）、未 push、未 merge；worktree 内只放本任务产物（脚本＋本记录）。