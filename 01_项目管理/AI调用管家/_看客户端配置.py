"""只读出编码客户端配置里的非密钥字段，用来确认「实际在用哪个客户端、指向哪个地址」。

只输出白名单键；任何名字里带 key/token/secret/password 的值一律不打印、不落盘。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

SAFE_KEYS = {
    "provider", "providers", "model", "models", "baseURL", "baseUrl", "url",
    "endpoint", "api", "anthropic", "openai", "name", "type", "enabled",
    "small_model", "smallModel", "defaultModel", "agent", "plugin",
    "mcp", "mcpServers", "httpproxy", "httpProxy", "proxy",
}
SENSITIVE = ("key", "token", "secret", "password", "credential", "auth")


def walk(node, path="", out=None):
    if out is None:
        out = []
    if isinstance(node, dict):
        for key, value in node.items():
            lowered = str(key).lower()
            if any(word in lowered for word in SENSITIVE):
                out.append((f"{path}.{key}", "<已略去，不打印>"))
                continue
            if isinstance(value, (dict, list)):
                walk(value, f"{path}.{key}", out)
            elif lowered in SAFE_KEYS or path.count(".") >= 1:
                out.append((f"{path}.{key}", value))
    elif isinstance(node, list):
        for i, item in enumerate(node):
            walk(item, f"{path}[{i}]", out)
    return out


def show(label: str, path: Path) -> None:
    print(f"\n=== {label} :: {path} ===")
    if not path.exists():
        print("  （不在盘）")
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        print(f"  读不了：{exc}")
        return
    for key, value in walk(data):
        text = str(value)
        if len(text) > 160:
            text = text[:160] + "…"
        print(f"  {key} = {text}")


def main() -> None:
    home = Path(os.environ.get("USERPROFILE", Path.home()))
    show("opencode", home / ".config" / "opencode" / "opencode.json")
    show("Claude Code settings", home / ".claude" / "settings.json")
    for name in ("config.toml", "auth.json"):
        show(f"Codex {name}", home / ".codex" / name)
    show("Codex global state", home / ".codex" / ".codex-global-state.json")


if __name__ == "__main__":
    main()
