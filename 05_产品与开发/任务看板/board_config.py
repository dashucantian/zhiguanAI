"""看板配置正源（模型注册表＋窗口登记表）。

为什么是 .py 而不是 config/*.json：本仓 .gitignore 第 77 行 `*.json`  blanket 拦截，
JSON 配置进不了库（C3 的 20261004 导出样例同病）。此处用 Python 字典作正源，可入库、可追溯。
如需临时覆盖，可另建 config/models.json、config/windows.json（本机生效、不入库）。

密钥永不写在这里——只写环境变量名。
"""
from __future__ import annotations

MODELS = [
    {
        "id": "board-local",
        "label": "本机规则应答（不出网·无需密钥）",
        "provider": "看板内置",
        "kind": "local",
        "baseUrl": "",
        "model": "rule-based",
        "keyEnv": "",
        "egress": "一级可用（本机不出网）",
        "isDefault": True,
        "note": "按关键词从看板本地数据作答（窗口／任务／积压／资源／作业）。不是大模型，答不了开放问题——但零出网、零密钥、当下可用。",
    },
    {
        "id": "qwen-flash",
        "label": "千问 Flash（法师自有密钥）",
        "provider": "千问AI 平台（maas.qianwenaiapi.com）",
        "kind": "chat",
        "baseUrl": "https://maas.qianwenaiapi.com/compatible-mode/v1",
        "model": "qwen-flash",
        "keyEnv": "QIANWEN_API_KEY",
        "egress": "三级（可出网）",
        "note": "端点依平台官方文档《OpenAI 兼容接口》。2026-10-07 实测：本机 QIANWEN_API_KEY（sk-sp- 开头·Token Plan·115 字）被平台判 401 invalid_api_key，需重新取密钥。",
    },
    {
        "id": "qwen-plus",
        "label": "千问 Plus（法师自有密钥）",
        "provider": "千问AI 平台（maas.qianwenaiapi.com）",
        "kind": "chat",
        "baseUrl": "https://maas.qianwenaiapi.com/compatible-mode/v1",
        "model": "qwen-plus",
        "keyEnv": "QIANWEN_API_KEY",
        "egress": "三级（可出网）",
        "note": "复杂规划时手动切换；同上，密钥未通前不可用。",
    },
    {
        "id": "lmstudio-local",
        "label": "LM Studio 本地（不出网）",
        "provider": "LM Studio",
        "kind": "chat",
        "baseUrl": "http://127.0.0.1:1234/v1",
        "model": "local-model",
        "keyEnv": "",
        "egress": "一级可用（本机不出网）",
        "note": "2026-10-07 复测：1234 已起，/v1/models 列 qwen3.8-27b 等四个，本看板探活 200 通。model 用 local-model 别名即指向当前装载的模型，不必改名。⚠ max_tokens 预算含 reasoning_tokens——qwen3.8-27b 一句短答实吃 43~78，预算给小了会 HTTP 200 而 content 空（别误判成模型不可用）；本文件的探活用 max_tokens=4 只判通断。",
    },
]

VOICE = {
    "stt": "浏览器 Web Speech API（识别经浏览器厂商云端，属出网）",
    "tts": "浏览器 speechSynthesis（本机合成，不出网）",
    "lang": "zh-CN",
    "warning": "一级内容（修道班资料／学员信息／机密文件）禁止使用语音识别与云端模型对话。",
}

# sessionId → 项目自己的窗口坐标。执行类别依 AI-开工入口.md §四bis ⑦ 一律先「未验」，
# 各窗自证后方可改标。
# 标准名格式＝窗别｜工作线｜会话短号（协调正本 §15）；正源＝本表，界面只做投影；
# 候核＝归属无据不推定，升为 W? 须法师裁定；已归档＝历史会话，不进编制登记表
# （01_项目管理\AI代理身份登记.md），仅看板留名以免退回编号显示；登记键＝完整 sessionId（同窗别同日可
# 多会话并存，已实测 10-08 W3 名下 a5e0f8f4／c2f3267e／6c7d4751 三会并存），不得以
# 窗别作键；历史行系 scan_sessions 按 45 天 mtime 扫 .qoder-cn jsonl 所得，桌面端
# 已无对应会话，会自然老化出窗。
WINDOWS = [
    # ── A. live·已核（20 行）──
    ("a5e0f8f4-8c9e-47ef-84f7-929f9fc4bd7a", "W3｜全项目协调｜a5e0f8f4", "W3", "W3-QODER-20261008-COORD-A"),
    ("b8729a7a-9d38-48b7-84f0-6fced4fa7722", "W1｜从此工程｜b8729a7a", "W1", "W1-QODER-20261008-A"),
    ("467608a2-b3cf-4beb-b23d-2d930d872dfb", "W3｜看板勘察｜467608a2", "W3", ""),
    ("6c7d4751-b76f-452c-a3e4-d93de1ee2a39", "W3｜图谱双轨｜6c7d4751", "W3", "W3-QODER-20261008-QGFSEQ-A"),
    ("c2f3267e-81d0-4df6-8b91-abf29d352f02", "W3｜架构可视化选型｜c2f3267e", "W3", "W3-QODER-20261008-A"),
    ("021bd0ea-f7e5-45f8-93b1-61c9efaf0554", "W3｜看板建造·接续｜021bd0ea", "W3", ""),
    ("a595afbe-7cbd-4292-9437-749ae0f00c4d", "W2｜ZG-075收口提交｜a595afbe", "W2", "W2-QODER-20260929-A"),
    ("2fcdb277-fb47-4527-828e-106285debb66", "W3｜制度与机动·看板建造｜2fcdb277", "W3", "W3-QODER-20261007-F"),
    ("53fef66f-baaf-4feb-aa69-79533f61321e", "W3｜制度线｜53fef66f", "W3", ""),
    ("39d35c36-58c4-4498-aca4-7c4e46810553", "W3｜学习线·微信课程｜39d35c36", "W3", ""),
    ("fa45d5a0-4e04-407e-bc35-0afa52b67b53", "W3｜方法论调研｜fa45d5a0", "W3", ""),
    ("01d65eb5-6332-4495-a450-1bf8f6a55348", "W3｜对话简洁性优化｜01d65eb5", "W3", ""),
    ("8b74852f-f0d6-44d0-81f0-788304a127d5", "W3｜人机建构论文分析｜8b74852f", "W3", ""),
    ("d98db51a-f638-47d0-8c45-e1ed91a9af16", "W3｜人机建构法解读｜d98db51a", "W3", ""),
    ("8e40f780-4cd0-465d-b64c-4b3159b31776", "W1｜工程线·候开工｜8e40f780", "W1", ""),
    ("f7e223f6-9096-4f95-a73d-bacccdb96a1a", "W1｜工程线·AI-008｜f7e223f6", "W1", ""),
    ("bbf8ca9d-fea1-4fd2-8d90-75e62ace132a", "W1｜测试台交互重构｜bbf8ca9d", "W1", ""),
    ("0ff1ecbf-88ba-4363-b64e-f48cac282ad6", "W2｜文档线·接手｜0ff1ecbf", "W2", ""),
    ("50af1e96-fb4c-43da-9093-62d869587b3b", "W4｜模型线｜50af1e96", "W4", ""),
    ("114be5b7-aef7-4a8b-bca8-4685e72148ca", "W4｜已转窗｜114be5b7", "W4", ""),
    # ── B. live·已核（2 行；ce059cf9 归 W2 系法师 2026-10-09 亲裁；bf54cc05 窗别系
    #    W3 协调窗代裁·候法师驳正，理由＝实质工作为跨全线只读整体复盘，属 W3 制度与机动线性质）──
    ("ce059cf9-a730-4230-a542-fe62ce6b6432", "W2｜行者无疆续写｜ce059cf9", "W2", ""),
    ("bf54cc05-b7a7-4935-b65b-1ab64a9b56aa", "W3｜全线只读复盘｜bf54cc05", "W3", ""),
    # ── C. 历史·已核（7 行）──
    ("59bbfd58-8278-4424-a1c4-cae22b774f9c", "C3｜常驻巡检·暂停｜59bbfd58", "W3-CRON-C3", "W3-CRON-C3"),
    ("526ef46c-0540-4eae-b174-fe9360e40aa1", "C3｜巡检cron载体·历史｜526ef46c", "W3-CRON-C3", "W3-CRON-C3"),
    ("b9f1881d-3e12-4310-81f7-9577b911ff96", "C3｜巡检cron载体·历史｜b9f1881d", "W3-CRON-C3", "W3-CRON-C3"),
    ("cc62fe2a-2cec-4b46-a20d-5fc3b57fa9fc", "C3｜巡检cron载体·历史｜cc62fe2a", "W3-CRON-C3", "W3-CRON-C3"),
    ("b9d3748d-dd64-4f32-98f0-975c870cc14c", "C3｜巡检cron载体·历史｜b9d3748d", "W3-CRON-C3", "W3-CRON-C3"),
    ("673e42ad-dd63-483a-811b-bad0f58c9b36", "C3｜巡检cron载体·历史｜673e42ad", "W3-CRON-C3", "W3-CRON-C3"),
    ("1192ec26-82ef-492f-84c4-089a0cd7e587", "L｜EEG101对照审计·已停｜1192ec26", "L", ""),
    # ── D. 历史·已归档（11 行；法师 2026-10-09 裁一律「已归档·不入登记表」，仅看板留名）──
    ("51afc647-9c57-8e6b-b89d-be8f154fa39a", "已归档｜草料二维码分析｜51afc647", "", ""),
    ("158d69fc-08a0-4a53-ac20-d35c56db658f", "已归档｜测试残窗｜158d69fc", "", ""),
    ("a5851674-e1e6-4029-a865-c1c1beafb45c", "已归档｜工具失败残窗｜a5851674", "", ""),
    ("4cffdd4a-9b2e-4691-a7a4-840cf27adabc", "已归档｜沟通协作规范文档批｜4cffdd4a", "", ""),
    ("fec98ac2-9f90-4c28-aedd-3152a2cfb423", "已归档｜沟通协作规范文档批｜fec98ac2", "", ""),
    ("2a1beca6-55c4-4350-ad41-7ccf0d4428ac", "已归档｜任务管理机制文档批｜2a1beca6", "", ""),
    ("947c5632-b3f3-41d2-bf30-e3d3b580ea9c", "已归档｜任务管理机制文档批｜947c5632", "", ""),
    ("089c7747-f285-4aa3-b746-7a194ad4d423", "已归档｜工作日志系统文档批｜089c7747", "", ""),
    ("3b927448-7ef2-43d5-83a8-2b94be204a63", "已归档｜工作日志系统文档批｜3b927448", "", ""),
    ("ef004592-bc01-4e7c-8341-d588cf46a914", "已归档｜案例库管理文档批｜ef004592", "", ""),
    ("9cb0cc24-e21b-4234-94e0-0150bf24958f", "已归档｜案例库管理文档批｜9cb0cc24", "", ""),
]


def windows_registry() -> dict:
    return {
        "windows": [
            {"sessionId": sid, "label": label, "window": win, "session": sess, "execClass": "未验"}
            for sid, label, win, sess in WINDOWS
        ]
    }


def models_registry_raw() -> dict:
    return {"models": MODELS, "voice": VOICE}
