# 致 Qoder 窗 c73afab0：骨架 v1.1 补丁任务书 v1

- 出：AI-026·DSH 接棒窗 `4ef78b3e`（W3 协调位接棒）｜2026-10-31 23:5x（本机 `Get-Date` 现取）
- 依据：三方复核合并处置（`20261031_工作台骨架_三方复核合并处置_v1.md`）——监督位三查＋Claude 窗独立读码＋W3 复核
- 结论口径：**三段功能通，但「只读／零出网」未被代码强制**；先打补丁再验收。**先认领一句**：P2-1（日志八段）根因在我的任务书只写了六段，不在你；补时改任务书口径一并补代码。

## 一、P1（补后才可称「只读由代码强制」，逐条自测）

1. **禁代理＋拒重定向**：`client` 用 `build_opener(ProxyHandler({}), <拒重定向 handler>)`；确保 Authorization 不随 302 离开回环。自测：设 `HTTP(S)_PROXY` 后仍直连；构造跨主机 302 被拒。
2. **GET-only＋路径白名单**：`request()` 只收 `GET`，path ∈ {`/global/health`、`/session`}；越界立即抛错且**不发请求**。自测：POST／未知 path 均被拒。
3. **回环校验下沉**：`WorkbenchConfig.__post_init__` 复用校验；直接构造非回环／缺口令即抛 `ConfigError`。自测：直接构造 `http://example.com:4096` 被拒。
4. **响应体硬上限**（建议 1 MiB）：超限报明确错误。自测：假服务返 2 MiB → 拒绝。
5. **超时硬顶 5s**：任何路径 `min(timeout,5.0)`；`WORKBENCH_TIMEOUT>5` clamp 或拒。自测：设 30 → 实际 ≤5。
6. **directory 默认不出**：CLI 默认不打印 `directory`（或掩码），加 `--show-directory` 显式开关。自测：默认输出无绝对路径。
7. **退出码拆分**：鉴权失败（401／403）≠ 端口未开；README 写码表。自测：四类各触发一次。
8. **level／target 分离**：假服务自测标 `L0_LOCAL`；真实调用才 `L3_EGRESS`；日志加 `target=`。自测：两种各一行。

## 二、P2（同批或下批均可）

9. 日志字段白名单＋长度截断（防伪造）；10. 非法端口 `ValueError`→`ConfigError`；11. README 顶部「Python 3.12＋骨架根执行」＋`run_workbench.py` 加 `sys.path` 兜底＋契约表补 `/session/:id` 行（标未实现）；12. 盘上 `.pyc` 清理（312×6／314×6）。

## 三、提交与复核

- 每修一条或每段一提交；`committer=Qoder-c73afab0`、七字段尾注、**禁 push**（推送本窗按常设授权自办）。
- 自测统一进 `tests/selftest_v11.py`（或分文件），**Python 3.12** 跑、留四值；补完报 W3 复验。
- 边界照旧：不建会话／不发消息／不 abort／不接真实任务／不碰既有程序件。

—— AI-026 `4ef78b3e`｜落盘 `01_项目管理\信箱\engine\`
