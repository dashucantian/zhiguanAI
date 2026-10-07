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
# 各窗自证后方可改标；未登记者界面显示「未登记窗口 xxxxxxxx」。
WINDOWS = [
    ("2fcdb277-fb47-4527-828e-106285debb66", "W3 制度与机动（本看板建造窗）", "W3", "W3-QODER-20261007-F"),
    ("53fef66f-baaf-4feb-aa69-79533f61321e", "W3 制度线", "W3", ""),
    ("39d35c36-58c4-4498-aca4-7c4e46810553", "W3 学习线（微信课程）", "W3", ""),
    ("fa45d5a0-4e04-407e-bc35-0afa52b67b53", "W3 方法论调研", "W3", ""),
    ("01d65eb5-6332-4495-a450-1bf8f6a55348", "W3 对话简洁性优化", "W3", ""),
    ("8b74852f-f0d6-44d0-81f0-788304a127d5", "W3 人机建构论文分析", "W3", ""),
    ("d98db51a-f638-47d0-8c45-e1ed91a9af16", "W3 人机建构法解读", "W3", ""),
    ("8e40f780-4cd0-465d-b64c-4b3159b31776", "W1 工程线（提交任务与候开工）", "W1", ""),
    ("f7e223f6-9096-4f95-a73d-bacccdb96a1a", "W1 工程线-008", "W1", ""),
    ("bbf8ca9d-fea1-4fd2-8d90-75e62ace132a", "W1 测试台交互重构", "W1", ""),
    ("0ff1ecbf-88ba-4363-b64e-f48cac282ad6", "W2 文档线（接手 W2 任务）", "W2", ""),
    ("50af1e96-fb4c-43da-9093-62d869587b3b", "W4 模型线", "W4", ""),
    ("114be5b7-aef7-4a8b-bca8-4685e72148ca", "W4 已转窗", "W4", ""),
    ("a595afbe-7cbd-4292-9437-749ae0f00c4d", "ZG-075 收口提交", "", ""),
    ("59bbfd58-8278-4424-a1c4-cae22b774f9c", "C3 巡检（cron 载体·现暂停）", "W3-CRON-C3", "W3-CRON-C3"),
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
