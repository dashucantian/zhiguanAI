"""隐私闸门：屏幕共享／权限控制／数据脱敏一律本机实现，不上云端。

法师 2026-10-07 金口（语音）：「屏幕共享和隐私保护功能将在本地实现，不上传到云端」
「可以把这条优先原则加进去」「这一部分可以放在本地吗？不上云端 → 完全可以」。
同日续令：「过闸2 拦一级，就发现有敏感内容的地方做打码，然后还是送……上云端」→ 加闸4。
本模块把该原则写成**服务端强制**，不是界面提示——绕过前端也拦得住。

四道闸：
  闸1 出网判定   只有 egress 标为「不出网」的模型才允许收到原文。
  闸2 一级内容拦截 命中一级关键词（学员／修道班／督导／声纹／原始脑电…）→ 云端一律拒发，不脱敏后照发。
  闸3 个人标识脱敏 手机号／身份证／邮箱／银行卡／微信号 → 就地替换为〔已脱敏〕，并回报处数。
  闸4 图像脱敏   截图先本机 OCR 定位敏感行、整行实心遮盖；未打码原图绝不出网；OCR 失效即整图拒发。

计数只记次数与类别，**不记原文**（闸门自身不得变成新的泄漏面）。
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import tempfile
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
        "闸4 图像脱敏：截图先经本机 OCR 定位敏感行，整行实心黑块遮盖（不模糊，模糊可被还原）；"
        "只有打码后的图才可能出网，未打码原图一律拒；OCR 不可用或读不出文字时整图拒发（fail-closed）",
    ],
    "screen": "截屏只写 state/screen/（该目录已 .gitignore 全排除），只经 127.0.0.1 回环显示；不入库。"
              "未打码原图一律不出网；只有闸4 脱敏后的图才可能送云端（法师 10-07 续令）",
    "network": "服务只听 127.0.0.1，不对局域网开放",
    "secrets": "密钥只从环境变量读，不存盘、不显示、不入模型上下文",
    "logs": "闸门只记次数与类别，不记原文",
    "residual": "闸4 只能遮 OCR 认得出的文字。照片／手写／人脸／脑电波形／艺术字／低对比小字遮不到——"
                "需要看这类内容时，本机模型或人工遮挡，别指望这道闸",
}

_LOCK = threading.Lock()
COUNTERS = {
    "blockedTier1": 0, "redacted": 0, "screenCaptured": 0,
    "screenRefusedCloud": 0, "cloudCalls": 0, "localCalls": 0,
    "imageRedacted": 0, "imageRefusedRaw": 0, "imageRefusedNoOcr": 0,
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


# ─────────────── 闸4 图像脱敏（法师 2026-10-07 续令） ───────────────
# 令：「过闸2 拦一级，就发现有敏感内容的地方做打码，然后还是送……上云端。」
# 落地口径三条，不许自行放宽：
#   ① 出网的只能是**打码后的图**，未打码原图一张都不出网；
#   ② 遮盖用**实心黑块**不用模糊——高斯模糊有被超分还原的风险；
#   ③ **fail-closed**：本机 OCR 不可用、或读不出任何文字 ⇒ 整图拒发。
#      认不出＝没资格说它不敏感，这是本闸唯一诚实的默认值。
# 残余风险（必须在界面写明白）：OCR 只能遮"它认得出的文字"。
#   照片、手写、人脸、脑电波形、低对比小字、艺术字——一律遮不到。

_OCR_PS = pathlib.Path(__file__).resolve().parent / "ocr_lines.ps1"
_SQUASH = re.compile(r"\s+")


def _squash(s: str) -> str:
    """OCR 会在中文字之间插空格（实测「学 员 张 三」），匹配前必须先压掉空白。"""
    return _SQUASH.sub("", s or "")


def ocr_lines(png) -> dict | None:
    """调 Windows 自带 OCR（零安装）。任何失败一律返回 None，不猜测成功。"""
    if not _OCR_PS.is_file():
        return None
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as fh:
        out = fh.name
    env = dict(os.environ, OCIN=str(png), OCOUT=out)
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                            "-File", str(_OCR_PS)], capture_output=True, env=env, timeout=90)
        if r.returncode != 0:
            return None
        data = json.loads(pathlib.Path(out).read_text(encoding="utf-8"))
        return data if data.get("ok") else None
    except Exception:
        return None
    finally:
        try:
            os.unlink(out)
        except OSError:
            pass


def find_sensitive(text: str) -> tuple[list[str], list[str]]:
    flat = _squash(text)
    keys = [k for k in TIER1_KEYWORDS if k.lower() in flat.lower()]
    nums = []
    for label, pat in PATTERNS:
        if pat.search(flat):
            nums.append(label)
    return sorted(set(keys)), sorted(set(nums))


def redact_image(png, out_dir) -> dict:
    """本机 OCR → 命中行整行实心遮盖 → 另存打码图。未打码原件不动、不出网。"""
    src = pathlib.Path(png)
    scan = ocr_lines(src)
    if scan is None:
        _bump("imageRefusedNoOcr")
        return {"allowed": False, "reason":
                "闸4 拒发：本机 OCR 不可用，无法确认图上文字，整图不发。"
                "（认不出＝没资格说它不敏感）", "residual": ""}
    lines = scan.get("lines") or []
    if not lines:
        _bump("imageRefusedNoOcr")
        return {"allowed": False, "reason":
                "闸4 拒发：OCR 未读出任何文字，无法判断图上有什么，整图不发。", "residual": ""}

    hits, cats = [], set()
    for ln in lines:
        keys, nums = find_sensitive(ln.get("text") or "")
        if keys or nums:
            hits.append(ln)
            cats.update(keys)
            cats.update(nums)

    from PIL import Image, ImageDraw
    img = Image.open(src).convert("RGB")
    dm = ImageDraw.Draw(img)
    masked_words = 0
    for ln in hits:
        # 整行遮盖：只盖关键词会留下上下文，姓名与号码可被反推
        for w in ln.get("words") or []:
            dm.rectangle([w["x"] - 4, w["y"] - 4, w["x"] + w["w"] + 4, w["y"] + w["h"] + 4], fill="black")
            masked_words += 1

    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / (src.stem + ".masked.png")
    img.save(dst, "PNG")
    _bump("imageRedacted")
    _bump("redacted", masked_words)
    return {"allowed": True, "maskedPath": str(dst), "maskedName": dst.name,
            "hitLines": len(hits), "maskedWords": masked_words,
            "categories": sorted(cats), "ocrLines": len(lines), "engine": scan.get("engine") or "?",
            "note": ("已遮盖 %d 行／%d 个词" % (len(hits), masked_words)) if hits else "OCR 未命中一级内容"}


def guard_image_outbound(masked: bool, model: dict | None) -> dict:
    """图像出网判定：未打码一律拒；打码后按模型物理位置分流。"""
    if not masked:
        _bump("imageRefusedRaw")
        return {"allowed": False, "reason":
                "闸4 拦截：未打码的原图一律不出网。请先做本机脱敏（闸4）。"}
    if model is None or is_local(model):
        return {"allowed": True, "scope": "local",
                "note": "打码图供本机使用"}
    return {"allowed": True, "scope": "cloud-masked",
            "note": "打码图送云端（残余风险：照片／手写／人脸／波形图等 OCR 认不出的内容遮不到）"}

