# 坑 013：浏览器被拦不等于本机不可达——先 curl 探活再定性

## 现象

2026-09-30～10-01 Qwen-Drive 调研试跑期间，三处"网络不通"的初判后来全部被推翻：

| 初判 | 依据 | 实况 |
|------|------|------|
| "本机 curl 出外网断" | `curl github.com` exit 56 | **github.com 主站被断**，但 `api.github.com`／`codeload.github.com`／`modelscope.cn` curl 全通（200／206） |
| "GitHub 仓库够不着" | browser-use 打开仓库页 ERR_CONNECTION_RESET | 同一时刻 curl 走 api.github.com 正常列出仓库树、codeload 正常拉 zip（60MB，重试 2 次成） |
| "微信文章抓不到" | WebFetch 只回"环境异常"校验页 | browser-use 真浏览器一次取到正文（`#js_content`） |

## 根因

用**单一工具的失败**代表**整机的通路状态**。浏览器渲染栈、WebFetch 代理层、curl 直连三者走的是不同通路，任何一层被拦都不等于其他层不通：

- **github.com 主站**：被断（连浏览器带 curl 都难）；**api.github.com／codeload**：curl 直连通
- **modelscope.cn**：curl 通、直链 `resolve/master` 可断点续传下载；浏览器打开 SPA 页反而超时（页面重，不是网络断）
- **微信公众号**：WebFetch 被安全校验拦；真浏览器（browser-use）通
- **curl 8MB 测速 1.67MB/s ≠ 实际全程速度**：长连接跑起来约 6MB/s——短样本测速会低估

## 解法

1. 判"通不通"前，**至少换两种工具探活**：`curl -s -o /dev/null -w "%{http_code}" --max-time 10 <url>` 打头，浏览器作对照
2. **分域名记通路地图**，不记"网断了"这种整句话：本机现势＝github 主站断／github API＋codeload 通／modelscope 通／arxiv 通／pypi 通（pip 可装件）
3. 大文件下载一律 `curl -C - --retry 3` 断点续传＋后台挂；codeload zip 这类不支持续传的加大 `--retry` 重试
4. 微信公众号正文**只走 browser-use**（WebFetch 必被"环境异常"拦死）

## 排障顺序（可复用）

1. curl 探活目标 URL，记 HTTP 码
2. 不通→换同域其他入口（主站↔API↔镜像 codeload/resolve）
3. curl 通浏览器不通→按"页面重/渲染层问题"处理，别再报"网络断"
4. 浏览器通 curl 不通→按"代理/凭据层"处理
5. 结论里写**具体哪个入口哪条路**，不写"外网不通"

## 教训

**"不通"必须落到具体的工具×入口×协议上，否则就是误报。** 本轮若照初判执行，13.8GB 权重下载和代码仓获取会被整体放弃，法师要的"真下载真试跑"直接落空。与坑 006（GitHub HTTPS 阻断改走 SSH）同族但更细一层：006 是"换协议"，本坑是"先探活、分入口，再定性"。AI 报网络问题时的纪律＝报通路地图，不报绝望结论。

## 关联

- 坑 006：GitHub_HTTPS阻断改走SSH
- 坑 004：本机无N卡的算力误判（同族："先实测再下结论"）
- 调研件：`04_研究调研\20260930_Qwen-Drive文章调研_对人机建构线的定性与三条借形态_v1.md` §7.4（提交 1f31a08）

---

## English Summary

**Symptom:** During the Qwen-Drive research test run (2026-09-30～10-01), three "network unreachable" first judgments were all overturned: raw `curl github.com` exit 56 turned out to be main-site-only blocking while api.github.com/codeload/modelscope.cn all worked via curl; the browser failing to open GitHub did not mean the API path was dead; WebFetch being blocked by WeChat's "environment anomaly" page did not mean a real browser couldn't fetch the article.

**Root cause:** Taking one tool's failure as the machine's whole connectivity status. Browser, WebFetch proxy, and raw curl use different paths; also a short 8MB speed sample (1.67MB/s) underestimated the sustained rate (≈6MB/s).

**Solution / reusable order:** (1) probe with curl HTTP-code + a browser before declaring anything unreachable; (2) keep a per-domain path map (github main site blocked / github API + codeload OK / modelscope OK / arxiv OK / pypi OK); (3) big downloads via `curl -C - --retry`; (4) WeChat article bodies only via browser-use.

**Lesson:** "Unreachable" must be pinned to tool × endpoint × protocol. The wrong first judgment would have abandoned the entire authorized download-and-test task. Related: card 006 (switch protocol) and card 004 (measure before concluding).
