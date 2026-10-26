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
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

READ_ONLY = "read_only"
WRITE_APPROVED = "write_approved"

MAX_TOOL_OUTPUT = 8000
TRUNC_NOTE = "\n…〔已截断：原文 {n} 字符，只回前 {m} 字符〕"

SYSTEM = """你是一个命令行助手。规则：
1. 需要看文件就调用 read_file，不要凭猜测说文件内容。
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


class OpenAIClient:
    """真实模型客户端。密钥只从环境变量取；本类不打印、不落盘密钥。"""

    def __init__(self, model: str = "deepseek-chat", base_url: str = "https://api.deepseek.com"):
        key = os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            raise RuntimeError(
                "未取到环境变量 DEEPSEEK_API_KEY；本试跑件不内置密钥（W3 判语第 3 条）"
            )
        from openai import OpenAI  # 延迟导入：离线自测不需要装包

        self._c = OpenAI(api_key=key, base_url=base_url)
        self.model = model

    def chat(self, messages: Sequence[dict], tools: Sequence[dict]) -> dict:
        r = self._c.chat.completions.create(
            model=self.model, messages=list(messages), tools=list(tools), temperature=0
        )
        return r.choices[0].message.model_dump(exclude_none=True)


def main(argv: Iterable[str] | None = None) -> int:
    args = list(argv if argv is not None else [])
    if not args:
        print("用法：python agent_skeleton.py \"<任务一句话>\"")
        print("注意：需先设环境变量 DEEPSEEK_API_KEY；默认只读档，写盘须改 ApprovalGate。")
        return 2
    root = Path.cwd()
    gate = ApprovalGate(mode=READ_ONLY)
    tools = build_tools(root, gate)
    try:
        client = OpenAIClient()
    except RuntimeError as e:
        print(f"未取到可用模型客户端：{e}")
        return 3
    result = run(args[0], client, tools, gate, on_event=print)
    print("\n" + result["final"])
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv[1:]))
