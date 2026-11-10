"""验百炼密钥：把用户级环境变量里的百炼／Token Plan 密钥真打一次两个入口。

只报：变量名、长度、形状、HTTP 码、模型回话。密钥值一律不打印、不落盘。
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ai_router import plans  # noqa: E402
from ai_router.store import user_env  # noqa: E402

# 管家读的那个名字，和常见的另外几个候选名字。
管家要的名字 = "TOKEN_PLAN_API_KEY"
候选名字 = ["TOKEN_PLAN_API_KEY", "DASHSCOPE_API_KEY", "QIANWEN_API_KEY", "BAILIAN_API_KEY"]

探针模型 = "deepseek-v4.1-flash-1017"


def 用户级所有变量名() -> list[str]:
    """把用户级环境变量里的名字全列出来（只列名字，不看值）。"""
    if os.name != "nt":
        return []
    try:
        import winreg
    except ImportError:
        return []
    names: list[str] = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ) as key:
            index = 0
            while True:
                try:
                    name, _, _ = winreg.EnumValue(key, index)
                except OSError:
                    break
                names.append(str(name))
                index += 1
    except OSError:
        return []
    return names


def 形状(值: str) -> str:
    if not 值:
        return "空的"
    前缀 = "sk- 开头" if 值.startswith("sk-") else "不是 sk- 开头"
    return f"{前缀}｜{len(值)} 字｜首尾空白={'有' if 值 != 值.strip() else '没有'}｜含引号={'有' if ('\"' in 值 or "'" in 值) else '没有'}"


def 打一次(接口: str, 密钥: str, 模型: str) -> tuple[str, str]:
    """真打一次，只回状态码和一句回答。"""
    体 = json.dumps(
        {"model": 模型, "messages": [{"role": "user", "content": "只回答两个字：通了"}], "max_tokens": 64},
        ensure_ascii=False,
    ).encode("utf-8")
    请求 = urllib.request.Request(
        接口.rstrip("/") + "/chat/completions",
        data=体,
        headers={"Authorization": f"Bearer {密钥}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(请求, timeout=60) as resp:
            数据 = json.loads(resp.read().decode("utf-8", "replace"))
            回答 = ((数据.get("choices") or [{}])[0].get("message") or {}).get("content")
            if not 回答:
                理由 = (数据.get("choices") or [{}])[0].get("message", {}).get("reasoning_content")
                回答 = 理由 or ""
            return f"HTTP {resp.status}", str(回答).strip()[:80]
    except urllib.error.HTTPError as exc:
        正文 = exc.read().decode("utf-8", "replace")
        try:
            错 = json.loads(正文)
            消息 = (错.get("error") or {}).get("message") or 正文
        except json.JSONDecodeError:
            消息 = 正文
        return f"HTTP {exc.code}", str(消息)[:120]
    except Exception as exc:  # noqa: BLE001
        return "没打通", repr(exc)[:120]


def 主() -> int:
    时刻 = time.strftime("%Y-%m-%d %H:%M:%S")
    print("=" * 60)
    print("百炼／Token Plan 密钥自检")
    print(f"时刻：{时刻}")
    print("=" * 60)

    全部名 = 用户级所有变量名()
    像百炼的 = [n for n in 全部名 if any(k in n.upper() for k in ("TOKEN_PLAN", "DASHSCOPE", "QIANWEN", "BAILIAN"))]

    print("\n一、用户级环境变量里跟百炼有关的变量（只看名字，不看值）")
    if 像百炼的:
        for 名 in 像百炼的:
            值 = user_env(名)
            print(f"  {名}｜{形状(值)}")
    else:
        print("  一个都没有。")

    print(f"\n二、管家要读的是 {管家要的名字}：")
    值 = user_env(管家要的名字)
    if 值:
        print(f"  有，长度 {len(值)}")
    else:
        print("  没有。管家会把这个池判成不可用。")

    print("\n三、真打两个入口（每个候选变量都试一遍）")
    试过的 = []
    for 名 in 候选名字:
        值 = user_env(名)
        if not 值 or 名 in 试过的:
            continue
        试过的.append(名)
        print(f"\n  变量 {名}：")
        for 入口名, 接口 in plans.BAILIAN_ENTRANCES.items():
            码, 答 = 打一次(接口, 值, 探针模型)
            print(f"    {入口名}（{接口}）→ {码}")
            print(f"      回话：{答 if 答 else '（空）'}")

    print("\n四、怎么算过")
    print("  两个入口都出现 HTTP 200 且回话有字，这把密钥才算能用。")
    print("  只在这台机器的环境变量里，全程没有复制到别处。")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(主())
