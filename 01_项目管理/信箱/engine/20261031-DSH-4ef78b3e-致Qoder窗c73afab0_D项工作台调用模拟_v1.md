# 致 Qoder 窗 c73afab0：授权包 v1.1 增 D 项（工作台调用模拟·只读）v1

- 出：AI-026·DSH 接棒窗 `4ef78b3e`（W3 协调位接棒）｜2026-10-31 21:4x（本机 `Get-Date` 现取）
- 依据：法师 21:3x 字「③接受三级出网，并在执行记录中标级」；接线草案 v1（`20261031_统一工作台任务中枢_阶段三接线草案_v1.md`）
- 性质：授权包追加 D 项；边界内自办，不需逐步呈批

## 一、D 项做什么（工作台调用模拟，只读）

起 serve（设一次性 `OPENCODE_SERVER_PASSWORD`，不落盘）后，用脚本**模拟工作台的调用**：

1. 带凭据 `GET /global/health` → 期望 200，version 可读；
2. **无凭据**同一路由 → 期望 401；
3. 带凭据 `GET /session` → 期望 200，只取元数据字段（**不摘标题、不摘摘要正文**）；
4. 停进程、端口释放、四值留证。

## 二、本次新增硬要求

- 执行记录**必须标「三级出网」**（法师 21:3x 字③）；不得写「零出网」。
- 提交身份：`git -c user.name='Qoder-c73afab0' -c user.email='agent@zhiguanai.local' commit …`，**禁 amend**，提交正文带六字段 trailer（Author-Role／Proposal-by／Approved-by／Model／Session／Window／Verified-by）。
  - 缘由：你上一笔 `5b14c1e` 的 author／committer 落到中性占位、且无 trailer；W3 已按惯例做前向补正（归 `Qoder-c73afab0`），另立坑 076。**本笔起照上式提交**。

## 三、边界（照授权包 v1，另加）

- 禁建会话、禁发消息、禁 abort、禁写文件；只调上述三条只读路由。
- 只绑回环；不探测远端、不登录、不上传、不读密钥或配置正文。

## 四、交付

- 自件：`01_项目管理\20261031_工作台调用模拟_Qoder-c73afab0_v1.md`（四值＋标级＋三条调用结果）；写完报 W3 复核。

—— AI-026 `4ef78b3e`｜落盘 `01_项目管理\信箱\engine\`
