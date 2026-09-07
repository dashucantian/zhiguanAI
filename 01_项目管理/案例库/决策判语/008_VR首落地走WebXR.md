# 判语 008：VR 首落地走 WebXR

> 判决日期：2026-09-05 | 状态：已定 | 影响范围：VR 技术路线

## 判决

本机未装 Unity，改走零安装 WebXR 路线。three.js 已本地化至 vr_assets/（离线可用），浏览器实测 canvas 渲染成功。

## 依据（可核验的事实）

- 本机未安装 Unity，等 Unity 安装和学习是几周的事
- WebXR 规范规定 navigator.xr 仅在安全上下文（HTTPS 或 localhost）暴露
- 局域网 HTTP 地址下浏览器直接隐藏 VR 能力，电脑用 localhost 看不出来，一到头显就暴露
- 解法为双端口：8777 HTTP（本机控制台）＋ 8778 HTTPS（Pico 进 VR 必经），自签证书幂等生成
- 页面 ws/wss 随 location.protocol 自适应

## 被否方案

- 等 Unity 工程化：周期过长，与"最快速度用起来"冲突
- 纯 HTTP 方案：WebXR 不支持，Pico 无法进入 VR

## 可复用教训

本机 localhost 正常 ≠ 局域网正常 ≠ 头显浏览器正常。三者是三个不同的运行环境，其中头显浏览器还多一层安全上下文限制。涉及 XR 的功能，必须真机验证，模拟与本机测试都不能替代。

## 关联

- 方案稿：01_项目管理\止观AI多模态反馈系统落地方案讨论稿.md §八
- 对话来源：2026-09-05/09-06 VR 攻坚与 HTTPS 排障

---

## English Summary

**Decision:** Unity is not installed on this machine, so we take the zero-install WebXR route. three.js has been localized into vr_assets/ (works offline), and browser testing confirmed canvas rendering succeeds.

**Evidence (verifiable facts):**
- Unity is not installed locally; waiting for installation and learning would take weeks
- The WebXR spec mandates that navigator.xr is only exposed in secure contexts (HTTPS or localhost)
- Over a LAN HTTP address, browsers hide XR capabilities entirely—localhost testing masks this, headsets expose it
- Solution: dual ports—8777 HTTP (local console) + 8778 HTTPS (required for headset VR entry), with idempotent self-signed certificate generation
- The page's ws/wss protocol auto-adapts to location.protocol

**Rejected Alternatives:**
- Waiting for the Unity pipeline: too slow, conflicts with "get it running as fast as possible"
- Pure HTTP: WebXR unavailable, headset cannot enter VR

**Reusable Lesson:**
Working on localhost ≠ working on LAN ≠ working in a headset browser. These are three different runtime environments, and the headset browser adds a secure-context requirement on top. Anything involving XR must be verified on real hardware—simulation and local tests cannot substitute.
