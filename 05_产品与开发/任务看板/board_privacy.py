"""隐私闸门：屏幕共享／权限控制／数据脱敏一律本机实现，不上云端。

法师 2026-10-07 金口（语音）：「屏幕共享和隐私保护功能将在本地实现，不上传到云端」
「可以把这条优先原则加进去」「这一部分可以放在本地吗？不上云端 → 完全可以」。
本模块把该原则写成**服务端强制**，不是界面提示——绕过前端也拦得住。

三道闸：
  闸1 出网判定   只有 egress 标为「不出网」的模型才允许收到原文与截图。
  闸2 一级内容拦截 命中一级关键词（学员／修道班／督导／声纹／原始脑电…）→ 云端一律拒发，不脱敏后照发。
  闸3 个人标识脱敏 手机号／身份证／邮箱／银行卡／微信号 → 就地替换为〔已脱敏〕，并回报处数。

计数只记次数与类别，**不记原文**（闸门自身不得变成新的泄漏面）。
"""
from __future__ import annotations

import re
import threading
import time

# ── 一级内容关键词：命中即禁出网（AI-开工入口.md §四bis ①–⑦、零出网三级制）──
TIER1_KEYWORDS = [
    "学员", "修道班", "督导", "面试评分", "声纹", "原始脑电", "人格档案",
    "录音转写", "逐字稿", "居士", "戒名", "皈依", "健康档案", "病历",
    "身份证", "银行卡", "密码", "密钥", "api_key", "api key", "token",
]

# ── 个人标识正则：命中即脱敏（不外发原文）──
PATTERNS = [
    ("手机号", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("身份证", re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")),
    ("邮箱", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("银行卡", re.compile(r"(?<!\d)\d{16,19}(?!\d)")),
    ("微信号", re.compile(r"(?:微信|wx|weixin)\s*[:：]?\s*[A-Za-z0-9_-]{6,20}", re.I)),
]

REDACTED = "〔已脱敏〕"

POLICY = {
    "principle": "屏幕共享／权限控制／数据脱敏一律本机实现，不上云端（法师 2026-10-07 金口）",
    "gates": [
        "闸1 出网判定：只有 egress 标注「不出网」的模型才收得到原文与截图",
        "闸2 一级内容拦截：命中学员／修道班／督导／声纹／原始脑电等关键词，云端一律拒发（不脱敏后照发）",
        "闸3 个人标识脱敏：手机号／身份证／邮箱／银行卡／微信号就地替换为〔已脱敏〕",
    ],
    "screen": "截屏只写 state/screen/（该目录已 .gitignore 全排除），只经 127.0.0.1 回环显示；不入库、不出网、不送云端模型",
    "network": "服务只听 127.0.0.1，不对局域网开放",
    "secrets": "密钥只从环境变量读，不存盘、不显示、不入模型上下文",
    "logs": "闸门只记次数与类别，不记原文",
}

_LOCK = threading.Lock()
COUNTERS = {
    "blockedTier1": 0, "redacted": 0, "screenCaptured": 0,
    "screenRefusedCloud": 0, "cloudCalls": 0, "localCalls": 0,
    "lastBlockAt": 0, "lastBlockCategory": "",
}


def counters() -> dict:
    with _LOCK:
        return dict(COUNTERS)


def _bump(key: str, n: int = 1):
    with _LOCK:
        COUNTERS[key] = COUNTERS.get(key, 0) + n


def is_local(model: dict) -> bool:
    """判定该模型是否「不出网」。判据＝推理发生的物理位置，不看客户端在哪。"""
    if not model:
        return False
    if model.get("kind") == "local":
        return True
    egress = model.get("egress") or ""
    base = (model.get("baseUrl") or "").lower()
    return ("不出网" in egress) and (base.startswith("http://127.0.0.1") or base.startswith("http://localhost"))


def find_tier1(text: str) -> list[str]:
    low = (text or "").lower()
    return sorted({kw for kw in TIER1_KEYWORDS if kw.lower() in low})


def desensitize(text: str) -> tuple[str, dict[str, int]]:
    hits: dict[str, int] = {}
    out = text or ""
    for label, pat in PATTERNS:
        out, n = pat.subn(REDACTED, out)
        if n:
            hits[label] = n
    return out, hits


def guard_outbound(text: str, model: dict) -> dict:
    """外发前的强制闸门。返回 {allowed, reason, text, hits, tier1, local}。"""
    local = is_local(model)
    tier1 = find_tier1(text)
    if local:
        _bump("localCalls")
        clean, hits = desensitize(text)
        if hits:
            _bump("redacted", sum(hits.values()))
        return {"allowed": True, "local": True, "reason": "", "text": text,
                "hits": hits, "tier1": tier1,
                "note": "本机模型（不出网）：原文放行，仅统计个人标识处数"}

    _bump("cloudCalls")
    if tier1:
        _bump("blockedTier1")
        with _LOCK:
            COUNTERS["lastBlockAt"] = int(time.time() * 1000)
            COUNTERS["lastBlockCategory"] = "、".join(tier1)[:60]
        return {"allowed": False, "local": False, "tier1": tier1, "hits": {}, "text": "",
                "reason": f"闸2 拦截：文本含一级内容关键词（{'、'.join(tier1)}），禁止发往云端模型。"
                          f"请改用本机模型，或删去该部分内容。"}

    clean, hits = desensitize(text)
    if hits:
        _bump("redacted", sum(hits.values()))
    return {"allowed": True, "local": False, "reason": "", "text": clean, "hits": hits, "tier1": [],
            "note": f"闸3 已脱敏 {sum(hits.values())} 处：{'、'.join(f'{k}{v}' for k, v in hits.items())}"
            if hits else "闸3 无命中，原文放行"}


def guard_screen(model: dict | None) -> dict:
    """屏幕共享闸门：截图只能留在本机，只有本机模型才可能取用。"""
    if model is None:
        return {"allowed": True, "reason": "", "scope": "local-display",
                "note": "仅本机回环显示，不送任何模型"}
    if is_local(model):
        return {"allowed": True, "reason": "", "scope": "local-model",
                "note": "本机模型可取用（不出网）"}
    _bump("screenRefusedCloud")
    return {"allowed": False, "scope": "refused",
            "reason": "闸1 拦截：屏幕截图属本机数据，禁止送云端模型。请切到本机模型（LM Studio）。"}
