# 止观AI工作日志 063 · R3′ 专注模式 overlay（浏览器端·V3 虚空单境）

日期：2026-09-24 ｜ 窗口：W1 工程线（AI-008·Qoder，Session `W1-QODER-20260924-B`）

## 一、承接与裁定源

整合稿 §五 分期 R3′ 行（1–2 天）＋ §六-3/4 两项裁定（法师 09-24 批）：
- **裁定④**：专注模式先浏览器端，Pico 侧随 S1 收口后另议——本轮只做 `console.html` 前端，不动采集主链路、不动后端；
- **裁定③**：「引导体验」页签独立保留至 R4，R3′ 时与专注模式**一并设计**（体验层设计语言统一）；
- 理念＝V3「虚空单境」哲学：采集时隐藏复杂度（研究者看数据、行者不盯数据，两态并存不二选一）。

## 二、施工（全部在 console.html 单文件内）

1. **overlay 组件 `.fx-overlay`（z-index 90）**：全屏极简态——中心**呼吸光点**（`fxBreath` 7s 缓吸缓呼 keyframes，径向青光）、**时长**（mm:ss，读主链路 `monElapsed` 每秒镜像）、**事件打点**、**结束钮**，其余波形/数值/仪表全折叠；深色径向渐变底。
2. **单一实现复用（红线5）**：结束钮＝`$("monStop").click()`，打点＝既有 `sendMarker()` 管道（`/api/monitor/marker`），打点钮复用 `.mon-marker`/`data-label` 全局绑定与 `setMarkerButtons` 开关（仅扩一处：同步 `fxMarkerCustom` 禁用态）。**不建平行停止/打点路径。**
3. **自评必弹不破（裁定7）**：专注层 z90 **压在自评卡 sr-overlay z98 之下**——「结束这一坐」→ 停采主链路先弹自评卡浮于专注层之上；实测 `srShown=flex` 时 `focusStillOpen=flex`，跳过/提交后会话 end 事件回主界面。
4. **入口与退出**：采集工作台工具条「🧘 专注模式」钮（`pollStatus` 里随 `busy` 启停，非采集中禁用）；`fxExit` 钮与 **Esc** 收起回全仪表（采集后台照跑）；会话 `end` 事件自动收起专注层（`fxOn` 时）；`body.fx-lock` 锁滚动、退出解锁。
5. **引导体验对齐（裁定③）**：页签新增「🧘 体验专注模式」钮，以**预览态** `fxOpen(true)` 借用同一组件（隐藏打点/结束/打点回执行，只演示呼吸光点体验层），零采集会话误入风险。体验层设计语言与采集端同源。

## 三、验收（浏览器实测·simulate 模式）

- 静态：`validate_console.py` PASS；node `vm.Script` 解析整段 JS OK（71,617 字符）；控制台零报错。
- 预览态：`btnFxPreview` → overlay flex、打点行/结束行 none、`fx-lock` 上锁；`fxExit` → 收起、解锁。
- 实采态（simulate）：`monStart` → `btnFocus` 解禁 → 开专注层，`elapsed` 同步到 00:36、三枚打点 chip 随 `setMarkerButtons(true)` 解禁 → 点「睁眼」→ `fxMsg`＝"📍 睁眼（第 1 个）已记"（走服务端真 marker）→ 点「结束这一坐」→ 自评卡浮于其上 → 跳过 → 会话 end → 专注层自动收起、解锁。全链绿。

## 四、边界（不做／留后续）

1. **Pico/头显端不做**——裁定④明示随 S1 收口后另议；本轮仅浏览器端 overlay。
2. **专注态无波形/数值一屏极简**＝设计本意（隐藏复杂度），非缺陷；如需"专注态余光看波形"候法师另裁。
3. 呼吸光点为**装饰性 CSS 动画**，不与实时 Alpha/HRV 联动（联动属 R4 分析层议题）。
4. 引导体验页签仍独立保留至 R4（裁定③），本轮只加"体验层预览"入口，**未合并、未撤页签**。
5. 取号声明：日志末行 062 ∪ 当日实体标题号（最大 062）→ 取 **063**；文中 063/064 命中经辨系 ZG-063/064 任务号，非日志号，已避开。

## 五、变更文件

- `console.html`（M）——专注模式 overlay 组件（CSS `.fx-*` ＋ HTML `#fxOverlay` ＋ JS `fxOpen/fxClose/fxSyncElapsed/fxStamp` 与入口/预览绑定）；`setMarkerButtons` 扩 `fxMarkerCustom`；`pollStatus` 加 `btnFocus` 启停；`end` 事件加自动收起；引导页签加预览钮。
- 本日志实体（?? 新增）。

> 提交状态：**候法师放行**（并发纪律：仅 `git add console.html 本日志` 两显式路径，禁 add .）。
