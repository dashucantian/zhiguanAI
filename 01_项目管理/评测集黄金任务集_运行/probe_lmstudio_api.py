# -*- coding: utf-8 -*-
"""
W4 评测集开跑前 API 探测（仅本机，连接 LM Studio 1234）
目的：确认三件事，决定统一口径能否落地
  1. /v1/chat/completions 是否接受 seed 参数（不接受则按 §4 标【弱可复现】）
  2. thinking / reasoning 如何控制（chat_template_kwargs.thinking_enabled？
     响应是否含 reasoning_content 字段）——用于 §8.3 逐模型如实记录
  3. usage 字段是否回传 prompt_tokens / completion_tokens（§8.3 主留证来源）
产物：只打印精简 JSON 到 stdout，不写任何数据文件，不触碰冻结素材。
"""
import json
import time
import urllib.request

BASE = "http://localhost:1234/v1/chat/completions"


def post(payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(BASE, data=data,
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            body = resp.read().decode("utf-8")
            return {"http": resp.status, "elapsed": round(time.time() - t0, 2),
                    "json": json.loads(body), "err": None}
    except urllib.error.HTTPError as e:
        return {"http": e.code, "elapsed": round(time.time() - t0, 2),
                "json": None, "err": e.read().decode("utf-8", "replace")[:600]}
    except Exception as e:  # noqa
        return {"http": None, "elapsed": round(time.time() - t0, 2),
                "json": None, "err": repr(e)[:600]}


def summarize(tag, r):
    out = {"tag": tag, "http": r["http"], "elapsed": r["elapsed"], "err": r["err"]}
    j = r["json"]
    if j:
        try:
            ch = j["choices"][0]
            msg = ch.get("message", {})
            out["message_keys"] = sorted(msg.keys())
            out["content_head"] = (msg.get("content") or "")[:80]
            rc = msg.get("reasoning_content")
            out["has_reasoning_content"] = bool(rc)
            out["reasoning_len"] = len(rc) if rc else 0
            out["usage"] = j.get("usage")
            out["finish_reason"] = ch.get("finish_reason")
        except Exception as e:  # noqa
            out["parse_err"] = repr(e)[:200]
    return out


results = []

# A. 基础调用：带 seed=42，temp 用 Ornith 生产值 0.15
r = post({"model": "ornith-eval",
          "messages": [{"role": "user", "content": "只回复两个字：收到"}],
          "temperature": 0.15, "max_tokens": 64, "seed": 42})
results.append(summarize("A_basic_with_seed", r))

# B. 显式尝试关闭 thinking（不同后端字段名不同，先试 chat_template_kwargs）
r = post({"model": "ornith-eval",
          "messages": [{"role": "user", "content": "只回复两个字：收到"}],
          "temperature": 0.15, "max_tokens": 64, "seed": 42,
          "chat_template_kwargs": {"thinking_enabled": False, "enable_thinking": False}})
results.append(summarize("B_thinking_off_kwargs", r))

# C. 尝试开启 thinking（对照 B 是否影响 reasoning_content / usage）
r = post({"model": "ornith-eval",
          "messages": [{"role": "user", "content": "只回复两个字：收到"}],
          "temperature": 0.15, "max_tokens": 64, "seed": 42,
          "chat_template_kwargs": {"thinking_enabled": True, "enable_thinking": True}})
results.append(summarize("C_thinking_on_kwargs", r))

# D. 复读一致性：与 A 完全相同参数，看 content/usage 是否一致（可复现性初判）
r = post({"model": "ornith-eval",
          "messages": [{"role": "user", "content": "只回复两个字：收到"}],
          "temperature": 0.15, "max_tokens": 64, "seed": 42})
results.append(summarize("D_repeat_of_A", r))

print(json.dumps(results, ensure_ascii=False, indent=2))
