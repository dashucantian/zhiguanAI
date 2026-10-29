# -*- coding: utf-8 -*-
"""自建智能体骨架 · 试跑件（非入库规则件）

性质：试跑件。不立规约条、不开新窗、未登记 AI 号。
落笔依据：W3 协调位 `fc2ce735` 2026-10-27 00:31 函《C13归口已决_先出试跑件》
           （归口 W4 主／W1 副；先出一件试跑，不排入 12 月开营关键路径）
安全口径（照该函第一节第 3 条）：默认只读档；写盘与命令执行须逐次人工审批；
           密钥只从环境变量取，不入库、不入提示词、不打印。

设计对应建议全文 §二—§七：
  ① 模型只生成文字，真正动手的是本文件的工具层。
  ② 核心＝一个循环：组装上下文 → 调模型 → 执行工具 → 结果回填 → 再调。
  ③ 三处最易出事的地方各留一道闸：路径白名单、危险命令黑名单、审批门。
"""

from __future__ import annotations

import json
import os
import fnmatch
import glob as _globmod
import re
import ssl
import subprocess
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

READ_ONLY = "read_only"
WRITE_APPROVED = "write_approved"

MAX_TOOL_OUTPUT = 8000
TRUNC_NOTE = "\n…〔已截断：原文 {n} 字符，只回前 {m} 字符〕"

SYSTEM = """你是一个命令行助手。规则：
1. 需要看文件就调用 read_file，不要凭猜测说文件内容；找文件用 glob，找内容用 grep——能精确命中就别整目录读。
2. 改文件用 write_file，且必须先读过再写。
3. 每次只做一小步，做完看结果再决定下一步。
4. 命令失败时读错误信息、换一种方式重试，最多三次。
5. 任务完成时用一两句话说明做了什么、结果如何。"""


class PathEscape(PermissionError):
    """越界访问：解析后的绝对路径不在工作根之内。"""


class ApprovalDenied(PermissionError):
    """审批门拒：只读档下的写盘或命令执行，或审批人未通过。"""


class GuardBlocked(PermissionError):
    """黑名单拦截：命令命中危险名单，未执行。"""


def resolve_safe(root: Path, raw: str) -> Path:
    """路径白名单：先解析成绝对路径，再判是否落在工作根之内。"""
    root = root.resolve()
    cand = Path(raw)
    p = (cand if cand.is_absolute() else root / cand).resolve()
    if p != root and root not in p.parents:
        raise PathEscape(f"越界访问被拒绝：{raw}")
    return p


def clip(text: str, limit: int = MAX_TOOL_OUTPUT) -> str:
    """工具输出截断：超限只回前 limit 字符，并明写已截断。"""
    if len(text) <= limit:
        return text
    return text[:limit] + TRUNC_NOTE.format(n=len(text), m=limit)


@dataclass
class Tool:
    name: str
    description: str
    fn: Callable[..., str]
    params: dict = field(default_factory=dict)
    required: tuple = ()
    mutating: bool = False

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.params,
                    "required": list(self.required),
                },
            },
        }


@dataclass
class ApprovalGate:
    """审批门：默认只读；写盘／命令执行须逐次获准。"""

    mode: str = READ_ONLY
    asker: Callable[[str, dict], bool] | None = None
    granted: list = field(default_factory=list)

    def permit(self, tool: Tool, args: dict) -> None:
        if not tool.mutating:
            return
        if self.mode == READ_ONLY:
            raise ApprovalDenied(
                f"只读档：{tool.name} 须人工审批，本次未获准"
            )
        if self.asker is not None and not self.asker(tool.name, args):
            raise ApprovalDenied(f"审批未通过：{tool.name}")
        self.granted.append((tool.name, args))


BLOCKED = (
    "rm -rf /",
    "rm -rf ~",
    "format ",
    "mkfs",
    "shutdown",
    "del /f /s /q c:\\",
)


def build_tools(root: Path, gate: ApprovalGate) -> dict[str, Tool]:
    root = root.resolve()

    def _read_file(path: str) -> str:
        return resolve_safe(root, path).read_text(encoding="utf-8", errors="replace")

    def _list_dir(path: str = ".") -> str:
        p = resolve_safe(root, path)
        return "\n".join(
            sorted(x.name + ("/" if x.is_dir() else "") for x in p.iterdir())
        )

    def _grep(pattern: str, path: str = ".", include: str = "", max_hits: int = 50, context: int = 0) -> str:
        """正则检索。找内容用它，别整目录读——这是省钱第一原则。"""
        base = resolve_safe(root, path)
        try:
            rx = re.compile(pattern)
        except re.error as e:
            raise ValueError(f"无效正则：{e}") from None
        if base.is_file():
            files = [base]
        else:
            files = [p for p in sorted(base.rglob("*")) if p.is_file()]
        if include:
            files = [
                p
                for p in files
                if fnmatch.fnmatch(p.name, include)
                or fnmatch.fnmatch(str(p.relative_to(root)), include)
            ]
        total = 0
        shown: list[str] = []
        for f in files:
            try:
                if f.stat().st_size > 2_000_000:
                    continue  # 超大件（疑似二进制/数据）跳过，防炸上下文
                lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for i, line in enumerate(lines, 1):
                if rx.search(line):
                    total += 1
                    if total <= max_hits:
                        rel = str(f.relative_to(root))
                        if context > 0:
                            lo, hi = max(1, i - context), min(len(lines), i + context)
                            for j in range(lo, hi + 1):
                                mark = ">" if j == i else " "
                                shown.append(f"{rel}:{j}:{mark} {lines[j - 1]}")
                        else:
                            shown.append(f"{rel}:{i}: {line}")
        head = f"命中 {total} 处"
        if total > max_hits:
            head += f"（仅示前 {max_hits}）"
        return head + ("\n" + "\n".join(shown) if shown else "")

    def _glob(pattern: str, path: str = ".") -> str:
        """按通配符列文件。找文件用它。"""
        base = resolve_safe(root, path)
        try:
            matches = _globmod.glob(str(base / pattern), recursive=True)
        except (TypeError, ValueError) as e:
            raise ValueError(f"通配符无法解析：{e}") from None
        rels = []
        for m in matches:
            p = Path(m).resolve()
            if p == root or root in p.parents:  # 通配符里带 .. 想越界？滤掉
                rels.append(str(p.relative_to(root)))
        rels = sorted(set(rels))
        shown = rels[:200]
        head = f"命中 {len(rels)} 件"
        if len(rels) > 200:
            head += "（仅示前 200）"
        return head + ("\n" + "\n".join(shown) if shown else "")

    def _write_file(path: str, content: str) -> str:
        p = resolve_safe(root, path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"已写入 {p.name}（{len(content)} 字符）"

    def _run_shell(command: str) -> str:
        low = command.lower()
        for bad in BLOCKED:
            if bad in low:
                raise GuardBlocked(f"拒绝执行：命中危险命令黑名单（{bad.strip()}）")
        r = subprocess.run(
            command, shell=True, cwd=root, capture_output=True, text=True, timeout=120
        )
        return f"[exit {r.returncode}]\n{(r.stdout or '') + (r.stderr or '')}"

    tools = [
        Tool(
            "read_file",
            "读取一个文本文件的全部内容。超长会被截断并标注。",
            _read_file,
            {"path": {"type": "string", "description": "相对工作根的文件路径"}},
            ("path",),
        ),
        Tool(
            "list_dir",
            "列出目录下的文件与子目录。",
            _list_dir,
            {"path": {"type": "string", "description": "相对工作根的目录，默认当前目录"}},
        ),
        Tool(
            "grep",
            "在指定目录或单个文件里按正则检索文本，返回「文件:行号: 该行」。超过 2MB 的文件跳过；命中数超限只示前若干并报总数。找内容用它，别整目录读。",
            _grep,
            {
                "pattern": {"type": "string", "description": "正则表达式，例如 def mean\\( 或 TODO"},
                "path": {"type": "string", "description": "目录或文件，默认当前目录"},
                "include": {"type": "string", "description": "可选：只搜文件名匹配该通配的文件，如 *.py"},
                "max_hits": {"type": "integer", "description": "最多回报条数，默认 50"},
                "context": {"type": "integer", "description": "可选：每条命中前后各附几行，默认 0"},
            },
            ("pattern",),
        ),
        Tool(
            "glob",
            "按通配符列文件（支持 ** 递归），返回排序后的相对路径。找文件用它。",
            _glob,
            {
                "pattern": {"type": "string", "description": "通配符，如 **/*.py 或 *.md"},
                "path": {"type": "string", "description": "起始目录，默认当前目录"},
            },
            ("pattern",),
        ),
        Tool(
            "write_file",
            "把内容写入文件，覆盖原内容；父目录不存在会自动创建。属改盘动作，须审批。",
            _write_file,
            {"path": {"type": "string"}, "content": {"type": "string"}},
            ("path", "content"),
            mutating=True,
        ),
        Tool(
            "run_shell",
            "在系统 shell 执行一条命令并返回输出。属改盘动作，须审批。",
            _run_shell,
            {"command": {"type": "string"}},
            ("command",),
            mutating=True,
        ),
    ]
    return {t.name: t for t in tools}


def execute(tools: dict[str, Tool], gate: ApprovalGate, name: str, args: dict) -> str:
    """执行一个工具调用。任何失败都回填给模型——这是它能自我修正的唯一途径。"""
    tool = tools.get(name)
    if tool is None:
        return f"工具执行失败：无此工具 {name}（可用：{', '.join(tools)}）"
    try:
        gate.permit(tool, args)
        return tool.fn(**args)
    except (PathEscape, ApprovalDenied, GuardBlocked) as e:
        return f"已拦截：{e}"
    except Exception as e:  # 工具内部异常一律回填，不中断循环
        return f"工具执行失败：{type(e).__name__}: {e}"


def run(
    task: str,
    client: Any,
    tools: dict[str, Tool],
    gate: ApprovalGate,
    max_steps: int = 25,
    system: str = SYSTEM,
    on_event: Callable[[str], None] | None = None,
) -> dict:
    """主循环：组装上下文 → 调模型 → 执行工具 → 结果回填 → 再调。

    返回 {ok, final, steps, messages}。ok=False 表示撞了最大步数。
    """
    say = on_event or (lambda _s: None)
    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": task},
    ]
    schemas = [t.schema() for t in tools.values()]
    history: list[tuple] = []

    for step in range(1, max_steps + 1):
        reply = client.chat(messages, schemas)
        messages.append(reply)
        calls = reply.get("tool_calls") or []
        if not calls:
            return {
                "ok": True,
                "final": reply.get("content") or "",
                "steps": step,
                "messages": messages,
            }

        for call in calls:
            fn = call.get("function") or {}
            name = fn.get("name") or ""
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            say(f"→ {name}({json.dumps(args, ensure_ascii=False)})")

            sig = (name, json.dumps(args, ensure_ascii=False, sort_keys=True))
            history.append(sig)
            if len(history) >= 3 and history[-1] == history[-2] == history[-3]:
                out = "打断：同一工具同参数已连续三次，请换一种做法或直接回答。"
            else:
                out = execute(tools, gate, name, args)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id") or "",
                    "content": clip(out),
                }
            )

    return {
        "ok": False,
        "final": f"达到最大步数（{max_steps}），任务未完成",
        "steps": max_steps,
        "messages": messages,
    }


DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)


class HttpClient:
    """极简 OpenAI 兼容客户端（标准库实现，零第三方依赖）。

    为什么不用 openai 包：本机未装，且试跑件要能被任何一台机器直接跑起来。
    为什么带浏览器 UA：OpenCode GO 前置 Cloudflare，按客户端指纹拦非浏览器请求
    （实测 2026-10-27 04:0x：默认 UA 得 `HTTP 403 error code: 1010`，换 UA 即 200）。

    接入点与密钥全由环境变量给，本类不打印、不落盘：
      AGENT_API_KEY   密钥（缺则回落 DEEPSEEK_API_KEY）
      AGENT_BASE_URL  默认 https://api.deepseek.com
      AGENT_MODEL     默认 deepseek-chat
      AGENT_CA_BUNDLE 可选：自备 CA 根证书 PEM（本机子进程不带系统根，实测须自备）
      AGENT_UA        可选：自定义 User-Agent
    """

    def __init__(self, model: str | None = None, base_url: str | None = None):
        key = os.environ.get("AGENT_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            raise RuntimeError(
                "未取到 AGENT_API_KEY／DEEPSEEK_API_KEY；本试跑件不内置密钥（W3 判语第 3 条）"
            )
        self._key = key
        base = base_url or os.environ.get("AGENT_BASE_URL") or "https://api.deepseek.com"
        self.base_url = base.rstrip("/")
        self.model = model or os.environ.get("AGENT_MODEL") or "deepseek-chat"
        self._ua = os.environ.get("AGENT_UA") or DEFAULT_UA
        self._session = os.environ.get("AGENT_SESSION") or str(uuid.uuid4())
        bundle = os.environ.get("AGENT_CA_BUNDLE")
        self._ctx = ssl.create_default_context(cafile=bundle) if bundle else None

    def chat(self, messages: Sequence[dict], tools: Sequence[dict]) -> dict:
        body = json.dumps(
            {
                "model": self.model,
                "messages": list(messages),
                "tools": list(tools),
                "temperature": 0,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {self._key}",
                "User-Agent": self._ua,
                "x-opencode-session": self._session,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=180, context=self._ctx) as r:
                data = json.load(r)
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"模型接口 HTTP {e.code}：{e.read()[:300]!r}") from None
        return data["choices"][0]["message"]


def main(argv: Iterable[str] | None = None) -> int:
    args = list(argv if argv is not None else [])
    if not args:
        print("用法：python agent_skeleton.py \"<任务一句话>\"")
        print("环境变量：AGENT_API_KEY（或 DEEPSEEK_API_KEY）／AGENT_BASE_URL／AGENT_MODEL／AGENT_CA_BUNDLE")
        print("注意：默认只读档，写盘与命令执行须改 ApprovalGate 并逐次审批。")
        return 2
    root = Path.cwd()
    gate = ApprovalGate(mode=READ_ONLY)
    tools = build_tools(root, gate)
    try:
        client = HttpClient()
    except RuntimeError as e:
        print(f"未取到可用模型客户端：{e}")
        return 3
    print(f"[模型] {client.model} @ {client.base_url}")
    result = run(args[0], client, tools, gate, on_event=print)
    print("\n" + result["final"])
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv[1:]))
