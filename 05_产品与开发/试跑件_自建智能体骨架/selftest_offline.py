# -*- coding: utf-8 -*-
"""离线自测：不联网、不调模型，用脚本化客户端把主循环与三道闸跑一遍。

为什么要离线自测（照实说）：
  本机未取到环境变量 DEEPSEEK_API_KEY，联网实跑做不了；而照 W3 判语第 3 条
  与 `信箱\\engine\\README.txt` 第⑤条零出网三级制，拿一级资料去试也不许。
  故本件只验「循环＋工具分发＋三道闸＋截断＋步数」，不验模型判断力。

退出码：全过 0；有失败 1；环境异常 2。
"""

from __future__ import annotations

import json
import shutil
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:  # 本机 python 不带脚本目录入 sys.path，显式补
    sys.path.insert(0, str(HERE))

import agent_skeleton as sk

ROOT = HERE
TMP = ROOT / "_selftest_tmp"
RESULTS: list[tuple[str, bool, str]] = []


def call(name: str, args: dict, cid: str = "c1") -> dict:
    """造一条 OpenAI 形状的 assistant 消息（带一次工具调用）。"""
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": cid,
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": json.dumps(args, ensure_ascii=False),
                },
            }
        ],
    }


def final(text: str) -> dict:
    return {"role": "assistant", "content": text}


class ScriptedClient:
    """脚本化客户端：按预排顺序返回消息，用来替掉真模型。"""

    def __init__(self, script: list[dict]):
        self.script = list(script)
        self.i = 0
        self.seen_tools: list = []

    def chat(self, messages, tools):
        self.seen_tools = list(tools)
        if self.i >= len(self.script):
            return final("（脚本用尽）")
        msg = self.script[self.i]
        self.i += 1
        return msg


def tool_outputs(result: dict) -> list[str]:
    return [m.get("content", "") for m in result["messages"] if m.get("role") == "tool"]


def check(name: str, fn) -> None:
    try:
        fn()
        RESULTS.append((name, True, ""))
    except AssertionError as e:
        RESULTS.append((name, False, str(e)))
    except Exception:
        RESULTS.append((name, False, traceback.format_exc(limit=2).replace("\n", " ")))


def new_run(script: list[dict], mode: str = sk.READ_ONLY, asker=None, max_steps: int = 25):
    gate = sk.ApprovalGate(mode=mode, asker=asker)
    tools = sk.build_tools(ROOT, gate)
    client = ScriptedClient(script)
    result = sk.run("自测任务", client, tools, gate, max_steps=max_steps)
    return result, gate, client


# ---------- 十项 ----------

def t1_path_escape():
    r, _, _ = new_run([call("read_file", {"path": "../外面.txt"}), final("结束")])
    outs = tool_outputs(r)
    assert outs and "已拦截" in outs[0] and "越界" in outs[0], outs
    assert r["ok"] is True, "拦截后应继续循环并正常收尾"


def t2_dangerous_command():
    r, _, _ = new_run([call("run_shell", {"command": "rm -rf / --no-preserve-root"}), final("结束")],
                      mode=sk.WRITE_APPROVED, asker=lambda n, a: True)
    outs = tool_outputs(r)
    assert outs and "已拦截" in outs[0] and "危险命令" in outs[0], outs


def t3_readonly_write_blocked():
    r, _, _ = new_run([call("write_file", {"path": "_selftest_tmp/x.txt", "content": "hi"}), final("结束")])
    outs = tool_outputs(r)
    assert outs and "只读档" in outs[0], outs
    assert not (ROOT / "_selftest_tmp" / "x.txt").exists(), "只读档竟然写出了文件"


def t4_approved_write():
    target = TMP / "hello.txt"
    r, gate, _ = new_run(
        [call("write_file", {"path": "_selftest_tmp/hello.txt", "content": "你好"}), final("结束")],
        mode=sk.WRITE_APPROVED, asker=lambda n, a: True)
    outs = tool_outputs(r)
    assert outs and "已写入" in outs[0], outs
    assert target.exists() and target.read_text(encoding="utf-8") == "你好", "审批通过但文件不对"
    assert gate.granted, "审批记录为空"


def t5_approval_denied():
    r, _, _ = new_run(
        [call("write_file", {"path": "_selftest_tmp/y.txt", "content": "hi"}), final("结束")],
        mode=sk.WRITE_APPROVED, asker=lambda n, a: False)
    outs = tool_outputs(r)
    assert outs and "审批未通过" in outs[0], outs


def t6_tool_error_filled_back():
    r, _, _ = new_run([call("read_file", {"path": "根本不存在的文件.txt"}), final("结束")])
    outs = tool_outputs(r)
    assert outs and "工具执行失败" in outs[0], outs
    assert r["ok"] is True, "工具报错不该打断循环"


def t7_duplicate_interrupt():
    same = call("list_dir", {"path": "."})
    r, _, _ = new_run([same, same, same, final("结束")])
    outs = tool_outputs(r)
    assert len(outs) == 3, outs
    assert "打断" in outs[2], outs


def t8_max_steps():
    script = [call("read_file", {"path": f"无{n}.txt"}) for n in range(5)] + [final("不该到这里")]
    r, _, _ = new_run(script, max_steps=3)
    assert r["ok"] is False, "撞步数应返回 ok=False"
    assert "最大步数" in r["final"], r["final"]
    assert r["steps"] == 3, r["steps"]


def t9_truncation():
    big = TMP / "big.txt"
    big.parent.mkdir(parents=True, exist_ok=True)
    big.write_text("甲" * 20000, encoding="utf-8")
    r, _, _ = new_run([call("read_file", {"path": "_selftest_tmp/big.txt"}), final("结束")])
    outs = tool_outputs(r)
    assert outs and "已截断" in outs[0], outs[:1]
    assert len(outs[0]) < 20000, "截断没生效"


def t10_normal_finish():
    r, _, client = new_run([call("list_dir", {"path": "."}), final("完成")])
    assert r["ok"] is True and r["steps"] == 2, r
    assert r["final"] == "完成", r["final"]
    assert client.seen_tools, "工具清单没传给模型"


CHECKS = [
    ("T1 路径越界被拦", t1_path_escape),
    ("T2 危险命令被拦", t2_dangerous_command),
    ("T3 只读档写盘被拦", t3_readonly_write_blocked),
    ("T4 审批通过可写", t4_approved_write),
    ("T5 审批否决被拦", t5_approval_denied),
    ("T6 工具异常回填", t6_tool_error_filled_back),
    ("T7 重复调用打断", t7_duplicate_interrupt),
    ("T8 最大步数生效", t8_max_steps),
    ("T9 超长输出截断", t9_truncation),
    ("T10 正常两步行收尾", t10_normal_finish),
]


def main() -> int:
    if TMP.exists():
        shutil.rmtree(TMP)
    TMP.mkdir(parents=True, exist_ok=True)
    try:
        for name, fn in CHECKS:
            check(name, fn)
    finally:
        shutil.rmtree(TMP, ignore_errors=True)

    print("=" * 58)
    print("离线自测 · 自建智能体骨架试跑件")
    print("=" * 58)
    for name, ok, detail in RESULTS:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ← {detail}" if detail else ""))
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print("-" * 58)
    print(f"合计 {passed}/{total} 通过")
    return 0 if passed == total else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        raise SystemExit(2)
