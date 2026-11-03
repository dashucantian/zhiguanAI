# 致 W3：隔离执行实验（丙案）交付——两笔提交在 worktree，待复核合并

- 发件窗：Qoder `c73afab0`｜2026-11-03 17:53 现取
- 任务：`TASK-20261103-02`（丙案：载体＝`vr_gates/verify_scene_env.py`）
- 结论：**实验完成、判据全过、主树零冲突**；未 merge、未 push，候 W3 收尾

## 一、四值

| 项 | 读数 |
|---|---|
| 起止 | 17:50:11—17:52:25（`date` 两次现取） |
| 退码 | `worktree add`＝0｜首笔 commit＝0｜记录 commit＝0 |
| 摘录 | 树 `_analysis_tmp\wt\scene-gate`｜分支 `wt/20261103-scene-gate`｜起点 `2705109e`｜提交 `5982e58`（闸）＋`db3959c`（记录） |
| 主树 | HEAD 仍 `2705109e`；新增未跟踪仅 `_analysis_tmp/wt/`（另加本函）；**冲突 0**；W2 那 56 行原样未动（diff 仍 56＋／5−） |

## 二、身份回执（按来函 §四原文贴出）

提交前实测：`git config user.name` → **zhiguanAI-agent**；`user.email` → `agent@zhiguanai.local`。
⇒ **仓库级默认就是占位身份**，`a44d1e2` 落占位即由此而来；本次两笔均显式 `-c user.name='Qoder-c73afab0' -c user.email='agent@zhiguanai.local'`。

提交后回执：

```
5982e58 | Qoder-c73afab0 <agent@zhiguanai.local> | Qoder-c73afab0 <agent@zhiguanai.local> | feat(Qoder-c73afab0·8779静态闸): 四判据落地-隔离实验首笔
db3959c | Qoder-c73afab0 | Qoder-c73afab0 | docs(Qoder-c73afab0·worktree实验): 四值+三证据+反证记录 1/0/1 件
```

`%B` 七字段尾注两笔均齐（Author-Role／Proposal-by／Approved-by／Verified-by／Model／Session／Window）。

## 三、闸结果与反证

- 正跑：**PASS 四判据全过、RC=0**（三预设六字段齐；ringMat 由 cGrid 驱动且三预设 `#d4af5a`；fog≤0.045／orbit=0／grain 上限 0.3；`wantPost` 带 `!renderer.xr.isPresenting`）。
- 反证：坏素材根（fog 0.9／orbit 0.2／cGrid 改色／grain 上限 0.6／删 XR 否定条件）→ **报红 5 项、RC=1**。
- 自解一个坑：闸首跑踩 GBK 编码崩，已在脚本内 `sys.stdout.reconfigure(encoding="utf-8")` 自解，不靠外部环境变量。

## 四、两处须你定/知

1. **口径差**：控制台**默认** `cGrid=#3b4666`，金线是载入 A 预设后生效；闸按预设值判，默认值作观察行打印。若要求控制台默认即金线，属改控制台，另裁。
2. **覆盖限制已写死**：闸读的 `output/_scene_env.html`、`vr_assets/models/presets/*.json` 均 ignore，只在本机可跑，clone 不可复现（docstring＋输出末行各一句）。

## 五、实验本身的一句话

**隔离要成立，先有可隔离的基线。** 原载体被 W2 在途改动挡住，换载体才满足起点干净；worktree 本身只解决了「写」的隔离，没解决「基线是否干净」。合并请你在主树做，`git merge --no-ff wt/20261103-scene-gate`；预期无冲突（两笔均为新增件）。记录全文在 worktree 内 `01_项目管理\20261103_隔离执行实验worktree_8779静态闸_Qoder-c73afab0_v1.md`，合并后即在主树同名路径。

边界：未出网、未碰飞书/学员数据/宣传内容、未碰他窗件、未 push、未 merge。