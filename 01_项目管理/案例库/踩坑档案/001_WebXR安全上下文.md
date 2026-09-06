# 坑 001：WebXR 安全上下文——HTTP 下浏览器隐藏 VR 能力

## 现象（用户视角，原话）

- 第一轮："Pico 上这个网址打不开啊，显示已离线"
- 第二轮："已经打开了网页，看到了跟电脑上一样的场景，但是无法进入 VR。跟电脑上显示的一样，提示'当前浏览器不支持，请用 Pico 浏览器打开本页'。为什么会这样？"

## 根因（多个坑容易混为一谈，这里其实只有一个）

WebXR 规范规定：`navigator.xr`（进入 VR 的能力）**只在"安全上下文"里暴露**——即 HTTPS 或本机 localhost。

- 电脑上用 `localhost:8777` 打开 → 算安全上下文 → VR 按钮可用
- Pico 走 `http://192.168.1.100:8777` → 纯 HTTP 局域网地址**不算**安全上下文 → 浏览器直接把 WebXR 能力藏掉，`navigator.xr` 为 undefined

所以页面报"不支持"，不是 Pico 浏览器不行，换任何浏览器走 HTTP 都一样。**电脑本地测不出来，一到头显就暴露**——这正是"涉及 XR 的功能必须真机验证"的铁律来源。

## 解法

给控制台加 HTTPS 服务（自签证书，局域网自用足够），Pico 改走 https：

1. 新增 `local_tls.py`：用 cryptography 幂等生成自签证书至 `vr_assets/tls/`（cert.pem + key.pem），有效期 825 天，已存在则跳过
2. `console_server.py` 改双端口：**8777 HTTP（电脑控制台照旧）＋ 8778 HTTPS（头显进 VR 必经）**，同一 app、`asyncio.gather` 并行 serve
3. 页面 ws/wss 随协议自适应：`const wsURL = ${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/vr`
4. Pico 首次访问 https 会弹"证书不受信任"，选"高级 → 继续访问"

## 排障顺序（可复用）

看到"无法进入 VR / navigator.xr 不存在"，先按这个顺序排，**不要一上来就改代码**：

1. 先确认页面**是否连到了正确的新服务**（见坑 002，端口占用会让新代码根本没生效）
2. 再确认**协议是不是 HTTPS**（这是本坑的根因，最常见）
3. 再确认设备与电脑**是否同一局域网段**（见 Wi-Fi 排查）
4. 最后才怀疑浏览器/引擎本身

## 教训

本机 localhost 正常 ≠ 局域网正常 ≠ 头显浏览器正常。三者是三个不同的运行环境，其中头显浏览器还多一层 WebXR 安全上下文限制。安全上下文这类约束在文档里一行带过，但在真机上是决定性的——**HTTPS 不是"锦上添花"，是 WebXR 的入场券**。

## 关联

- 工作日志 005（2026-09-06）§2.6 第三轮排障
- 判语 008：VR 首落地走 WebXR
- 相关文件：`local_tls.py`、`console_server.py`、`vr_feedback.html`
