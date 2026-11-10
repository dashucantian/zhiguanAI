#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""关系场域二维活看板：只读四源，生成 field-model.json / field-model.js。

四源（工作树，side=working-tree）：
  1. 身份登记  01_项目管理/AI代理身份登记.md
  2. 任务看板  01_项目管理/任务登记.md（任务登记正本；看板 board_server 的服务层不读）
  3. 待裁单    01_项目管理/待裁单.md
  4. 架构模型  05_产品与开发/架构可视化/architecture-model.json

本脚本只读上述四件，不写任何源件；输出只落 --out 目录。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_ROOT = HERE.parent.parent
DEFAULT_OUT = HERE / "data"

SRC_REL = {
    "identity": "01_项目管理/AI代理身份登记.md",
    "tasks": "01_项目管理/任务登记.md",
    "rulings": "01_项目管理/待裁单.md",
    "arch": "05_产品与开发/架构可视化/architecture-model.json",
}
SRC_LABEL = {
    "identity": "身份登记",
    "tasks": "任务看板（任务登记正本）",
    "rulings": "待裁单",
    "arch": "架构证据模型",
}

TASK_FIELD_KEYS = ["来源", "触发来源", "最近活动", "需求原句", "主线回指", "责任位",
                   "状态", "权限级", "时限", "验收句", "证伪句", "证据链接", "复核者"]


def status_key(s: str) -> str:
    s = s or ""
    if re.search(r"已销|已归档", s):
        return "已销"
    if re.search(r"已验收|已完成|已交|已办|已生效|已升为", s):
        return "已完成/已交"
    if re.search(r"进行中|中环已跑|待验收", s):
        return "进行中"
    if re.search(r"待派|待办|待审|候法师|候裁", s):
        return "待办/待裁"
    return "其他"


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\t", "  ")).strip()


def plain(s: str) -> str:
    """去掉 markdown 粗体/代码符号，保留文字。"""
    s = s or ""
    s = s.replace("**", "").replace("`", "")
    s = re.sub(r"^〔[^〕]*〕", "", s)
    return norm(s)


def short(s: str, n: int) -> str:
    s = plain(s)
    return s if len(s) <= n else s[: n - 1] + "…"


def read_lines(p: Path):
    text = p.read_text(encoding="utf-8")
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def make_anchor(file_rel: str, line_no: int, line_text: str, note: str = "",
                section: str = "", raw_limit: int = 420):
    raw = norm(line_text)
    return {
        "file": file_rel,
        "line": int(line_no),
        "fp": raw[:60],
        "side": "working-tree",
        "note": note,
        "section": section,
        "raw": raw[:raw_limit],
        "rawLen": len(raw),
    }


def split_md_row(line: str):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def window_key(text: str) -> str:
    m = re.search(r"W([1-4])", text or "")
    return f"W{m.group(1)}" if m else "候核"


def short_ai_name(name: str) -> str:
    name = plain(name)
    m = re.search(r"（([^）]+)）", name)
    if m:
        inner = m.group(1)
        if "｜" in inner:
            inner = inner.split("｜", 1)[1]
        inner = re.split(r"[；;]", inner)[0]
        if inner:
            return short(inner, 24)
    return short(name, 24)


def parse_identity(lines, rel):
    nodes = []
    ai_rows = []
    window_rows = {}
    human_row = None
    for i, ln in enumerate(lines, 1):
        m = re.match(r"^\| \*\*(AI-\d{3})\*\* \|", ln)
        if m:
            cells = split_md_row(ln)
            if len(cells) < 8:
                cells += [""] * (8 - len(cells))
            aid = m.group(1)
            name = cells[1]
            model = plain(cells[2])
            win_raw = cells[3]
            purpose = plain(cells[4])
            first = plain(cells[5])
            exec_class = plain(cells[7]) if len(cells) > 7 else ""
            wk = window_key(win_raw)
            nid = f"subject.ai.{aid}"
            nodes.append({
                "id": nid,
                "layer": "subject",
                "kind": "ai",
                "label": f"{aid} {short_ai_name(name)}",
                "desc": short(name, 90),
                "attrs": {
                    "AI 号": aid,
                    "模型": short(model, 60),
                    "窗口": short(plain(win_raw), 70),
                    "用途": short(purpose, 90),
                    "首次参与": short(first, 60),
                    "执行类别": short(exec_class, 40),
                },
                "window": wk,
                "anchors": [make_anchor(rel, i, ln, f"{aid} 登记行")],
            })
            ai_rows.append((aid, i, wk, ln))
        m2 = re.match(r"^\| \*\*(W[1-4])\*\* \|", ln)
        if m2:
            cells = split_md_row(ln)
            wk = m2.group(1)
            scope = plain(cells[2]) if len(cells) > 2 else ""
            basis = plain(cells[4]) if len(cells) > 4 else ""
            window_rows[wk] = {"line": i, "scope": scope, "basis": basis}
        if ln.startswith("| **宗国法师** |"):
            human_row = (i, ln)
    # 主体：法师
    if human_row:
        i, ln = human_row
        nodes.append({
            "id": "subject.human.fashi",
            "layer": "subject",
            "kind": "human",
            "label": "宗国法师（唯一决策人）",
            "desc": "内容归属人、最终批准者、判定权归属（身份登记 §二）",
            "attrs": {"角色": "唯一决策人", "判定权": "裁定候裁项／放行提交（身份登记 §二）"},
            "window": "—",
            "anchors": [make_anchor(rel, i, ln, "身份登记 §二 人类身份")],
        })
    # 主体：四个窗口
    for wk in ["W1", "W2", "W3", "W4"]:
        info = window_rows.get(wk)
        if not info:
            continue
        nodes.append({
            "id": f"subject.window.{wk}",
            "layer": "subject",
            "kind": "window",
            "label": f"{wk} 窗口",
            "desc": info["scope"],
            "attrs": {"窗口": wk, "负责范围": info["scope"], "划分依据": info["basis"]},
            "window": wk,
            "anchors": [make_anchor(rel, info["line"], lines[info["line"] - 1], "窗口编制表")],
        })
    return nodes, ai_rows, window_rows


def parse_tasks(lines, rel):
    blocks = []
    cur = None
    for i, ln in enumerate(lines, 1):
        m = re.match(r"^### (TASK-\d{8}-\d{2})\s*$", ln)
        if m:
            cur = {"id": m.group(1), "line": i, "fields": {}, "field_lines": {}}
            blocks.append(cur)
        elif ln.startswith("## "):
            cur = None
        elif cur is not None:
            m2 = re.match(r"^- ([^：]{1,12})：(.+)$", ln)
            if m2:
                key = m2.group(1).strip()
                if key in TASK_FIELD_KEYS:
                    cur["fields"][key] = m2.group(2).strip()
                    cur["field_lines"][key] = i
    nodes = []
    for b in blocks:
        tid = b["id"]
        f = b["fields"]
        status_raw = plain(f.get("状态", ""))
        status = re.split(r"[（(]", status_raw)[0] if status_raw else "未记"
        resp = plain(f.get("责任位", ""))
        mains = sorted(set(re.findall(r"W[1-4]", resp))) or ["—"]
        title = plain(f.get("需求原句") or f.get("来源") or "")
        label = f"{tid} {short(title, 28)}"
        anchors = [make_anchor(rel, b["line"], lines[b["line"] - 1], f"{tid} 任务块头")]
        for key, note in [("状态", "任务状态"), ("责任位", "责任位"), ("权限级", "权限级"),
                          ("最近活动", "最近活动")]:
            if key in b["field_lines"]:
                li = b["field_lines"][key]
                anchors.append(make_anchor(rel, li, lines[li - 1], note))
        nodes.append({
            "id": f"task.{tid}",
            "layer": "task",
            "kind": "task",
            "label": label,
            "desc": short(title, 120),
            "attrs": {
                "任务号": tid,
                "状态": short(status_raw, 80),
                "状态类": status_key(status_raw),
                "责任位": short(resp, 90),
                "主线回指": short(plain(f.get("主线回指", "")), 40),
                "权限级": short(plain(f.get("权限级", "")), 100),
                "最近活动": short(plain(f.get("最近活动", "")), 100),
            },
            "windows": mains,
            "status": status,
            "anchors": anchors,
        })
    return nodes


def parse_rulings(lines, rel):
    relation = None
    rows = 0
    decided = 0
    for i, ln in enumerate(lines, 1):
        if ln.startswith("| **候编号**") or ln.startswith("| **C-"):
            rows += 1
            cells = split_md_row(ln)
            if cells and "已决" in cells[0]:
                decided += 1
            if "关系场域" in ln:
                relation = (i, ln)
    nodes = []
    if relation:
        i, ln = relation
        cells = split_md_row(ln)
        flag_cell = cells[0] if cells else ""
        title = plain(cells[1]) if len(cells) > 1 else "关系场域活看板"
        nodes.append({
            "id": "boundary.ruling.relation-domain",
            "layer": "boundary",
            "kind": "ruling",
            "label": "⚑ 关系场域立项（已决）",
            "desc": short(title, 120),
            "attrs": {
                "裁定": "已决·法师 2026-11-08 字「要」",
                "号列标记": short(flag_cell, 100),
                "作用": "本任务授权边界：只做二维最小验证；后续新程序件与提交放行须法师字",
            },
            "anchors": [make_anchor(rel, i, ln, "待裁单 §一 关系场域条")],
        })
    return nodes, {"rows": rows, "decided": decided, "live": rows - decided}


def parse_arch(lines, model, rel):
    id_lines = {}
    for i, ln in enumerate(lines, 1):
        m = re.search(r'"id":\s*"([^"]+)"', ln)
        if m and m.group(1) not in id_lines:
            id_lines[m.group(1)] = i
    nodes = []
    for n in model.get("nodes", []):
        nid = n.get("id", "")
        li = id_lines.get(nid)
        anchors = []
        if li:
            anchors.append(make_anchor(rel, li, lines[li - 1], f"架构节点 {nid}"))
        nodes.append({
            "id": f"model.node.{nid}",
            "layer": "model",
            "kind": "arch-node",
            "archId": nid,
            "archType": n.get("type", ""),
            "label": n.get("label", nid),
            "desc": short(n.get("description", ""), 140),
            "attrs": {
                "架构 ID": nid,
                "类型": n.get("type", ""),
                "置信度": n.get("confidence", ""),
                "sourceRefs 数": str(len(n.get("sourceRefs") or [])),
                "sourceRefs": short("；".join(str(x.get("ref", x)) if isinstance(x, dict) else str(x)
                                               for x in (n.get("sourceRefs") or [])) or "—", 160),
            },
            "anchors": anchors,
        })
    edges = []
    skipped = 0
    node_ids = {n.get("id") for n in model.get("nodes", [])}
    for e in model.get("edges", []):
        eid = e.get("id", "")
        frm, to = e.get("from", ""), e.get("to", "")
        if frm not in node_ids or to not in node_ids:
            skipped += 1
            continue
        li = id_lines.get(eid)
        anchors = []
        if li:
            anchors.append(make_anchor(rel, li, lines[li - 1], f"架构边 {eid}"))
        edges.append({
            "id": f"edge.model.{eid}",
            "from": f"model.node.{frm}",
            "to": f"model.node.{to}",
            "type": "架构",
            "desc": short(e.get("description", ""), 100),
            "anchors": anchors,
        })
    hub_line = 2
    hub_fp_line = lines[hub_line - 1] if len(lines) >= 2 else lines[0]
    nodes.append({
        "id": "model.hub",
        "layer": "model",
        "kind": "arch-hub",
        "label": "架构证据模型 v1",
        "desc": "37 节点／34 边／149 条 sourceRefs；本任务只读其登记件，不读它指向的代码文件。",
        "attrs": {
            "schemaVersion": str(model.get("schemaVersion", "")),
            "generatedAt": str(model.get("metadata", {}).get("generatedAt", "")),
            "nodes": str(len(model.get("nodes", []))),
            "edges": str(len(model.get("edges", []))),
        },
        "anchors": [make_anchor(rel, hub_line, hub_fp_line, "架构模型 schemaVersion")],
    })
    return nodes, edges, {"skipped_edges": skipped}


def build(root: Path, out_dir: Path):
    now = datetime.now().astimezone()
    src_paths = {k: root / v for k, v in SRC_REL.items()}
    for k, p in src_paths.items():
        if not p.exists():
            raise SystemExit(f"缺源件：{p}")
    text_lines = {k: read_lines(p) for k, p in src_paths.items()}
    meta = {}
    version_parts = []
    sources = []
    for k in ["identity", "tasks", "rulings", "arch"]:
        p = src_paths[k]
        st = p.stat()
        h = sha256_file(p)
        version_parts.append(f"{SRC_REL[k]}:{h}")
        sources.append({
            "key": k,
            "label": SRC_LABEL[k],
            "path": SRC_REL[k],
            "bytes": st.st_size,
            "lines": len(text_lines[k]),
            "mtime": datetime.fromtimestamp(st.st_mtime).astimezone().isoformat(timespec="seconds"),
            "sha256": h,
        })
        meta[k] = h
    version = hashlib.sha256("\n".join(version_parts).encode("utf-8")).hexdigest()[:12]

    subject_nodes, ai_rows, window_rows = parse_identity(text_lines["identity"], SRC_REL["identity"])
    task_nodes = parse_tasks(text_lines["tasks"], SRC_REL["tasks"])
    ruling_nodes, ruling_stats = parse_rulings(text_lines["rulings"], SRC_REL["rulings"])
    arch_model = json.loads(src_paths["arch"].read_text(encoding="utf-8"))
    arch_nodes, arch_edges, arch_stats = parse_arch(text_lines["arch"], arch_model, SRC_REL["arch"])

    nodes = subject_nodes + task_nodes + ruling_nodes + arch_nodes
    node_ids = {n["id"] for n in nodes}
    edges = []

    # AI → 窗口（隶属）
    for aid, line_no, wk, ln in ai_rows:
        wid = f"subject.window.{wk}"
        if wid in node_ids:
            edges.append({
                "id": f"edge.member.{aid}",
                "from": f"subject.ai.{aid}",
                "to": wid,
                "type": "隶属",
                "desc": f"{aid} 归属 {wk}",
                "anchors": [make_anchor(SRC_REL["identity"], line_no, ln, f"{aid} 窗口列")],
            })

    # 窗口 → 边界（职责边界）
    for wk, info in window_rows.items():
        wid = f"subject.window.{wk}"
        bid = f"boundary.window.{wk}"
        nodes.append({
            "id": bid,
            "layer": "boundary",
            "kind": "window-boundary",
            "label": f"{wk} 职责边界",
            "desc": info["scope"],
            "attrs": {"窗口": wk, "职责范围": info["scope"], "划分依据": info["basis"]},
            "anchors": [make_anchor(SRC_REL["identity"], info["line"], text_lines["identity"][info["line"] - 1],
                                    "窗口编制表（边界）")],
        })
        node_ids.add(bid)
        if wid in node_ids:
            edges.append({
                "id": f"edge.boundary.{wk}",
                "from": wid,
                "to": bid,
                "type": "边界",
                "desc": f"{wk} 的职责范围",
                "anchors": [make_anchor(SRC_REL["identity"], info["line"],
                                        text_lines["identity"][info["line"] - 1], "窗口编制表")],
            })

    # 任务 → 窗口（责任）
    for tn in task_nodes:
        tid = tn["attrs"]["任务号"]
        for wk in tn.get("windows", []):
            wid = f"subject.window.{wk}"
            if wid in node_ids:
                li = None
                for a in tn["anchors"]:
                    if a["note"] == "责任位":
                        li = a["line"]
                        break
                anchor = make_anchor(SRC_REL["tasks"], li, text_lines["tasks"][li - 1], "责任位") if li else tn["anchors"][0]
                edges.append({
                    "id": f"edge.resp.{tid}.{wk}",
                    "from": f"task.{tid}",
                    "to": wid,
                    "type": "责任",
                    "desc": f"{tid} 责任位提到 {wk}",
                    "anchors": [anchor],
                })

    # 法师 → 关系场域边界（裁定）
    fashi = "subject.human.fashi"
    ruling = "boundary.ruling.relation-domain"
    if fashi in node_ids and ruling in node_ids:
        human_anchor = next(a for n in nodes if n["id"] == fashi for a in n["anchors"])
        edges.append({
            "id": "edge.ruling.fashi",
            "from": fashi,
            "to": ruling,
            "type": "裁定",
            "desc": "法师 2026-11-08 字「要」＝准立项",
            "anchors": [human_anchor],
        })

    # 本任务 → 待裁单边界、→ 架构模型 hub
    our_task = "task.TASK-20261108-01"
    if our_task in node_ids:
        tn = next(n for n in task_nodes if n["id"] == our_task)
        status_anchor = next((a for a in tn["anchors"] if a["note"] == "任务状态"), tn["anchors"][0])
        if ruling in node_ids:
            edges.append({
                "id": "edge.our.ruling",
                "from": our_task,
                "to": ruling,
                "type": "授权",
                "desc": "本任务由该裁定授权，按最小验证四条判据执行",
                "anchors": [status_anchor],
            })
        if "model.hub" in node_ids:
            edges.append({
                "id": "edge.our.arch",
                "from": our_task,
                "to": "model.hub",
                "type": "读取",
                "desc": "本任务读取架构证据模型（只读登记件）",
                "anchors": [status_anchor],
            })
        perm_anchor = next((a for a in tn["anchors"] if a["note"] == "权限级"), tn["anchors"][0])
        task_bnd = "boundary.task.TASK-20261108-01"
        nodes.append({
            "id": task_bnd,
            "layer": "boundary",
            "kind": "task-boundary",
            "label": "本任务边界（低—中权限）",
            "desc": short(tn["attrs"]["权限级"], 150),
            "attrs": {
                "任务号": "TASK-20261108-01",
                "权限级": short(tn["attrs"]["权限级"], 150),
                "边界要点": "只做二维；只读四源；不出网；不监视整机整网；不先上三维；不碰 pdf2game",
            },
            "anchors": [perm_anchor],
        })
        node_ids.add(task_bnd)
        edges.append({
            "id": "edge.our.boundary",
            "from": our_task,
            "to": task_bnd,
            "type": "边界",
            "desc": "本任务的权限与范围边界",
            "anchors": [perm_anchor],
        })

    edges.extend(arch_edges)

    # 校验边端点
    clean_edges = []
    dangling = 0
    for e in edges:
        if e["from"] in node_ids and e["to"] in node_ids:
            clean_edges.append(e)
        else:
            dangling += 1
    edges = clean_edges

    model = {
        "schema": "field-model/1",
        "generatedAt": now.isoformat(timespec="seconds"),
        "generatedAtLocal": now.strftime("%Y-%m-%d %H:%M:%S"),
        "root": str(root).replace("\\", "/"),
        "version": version,
        "sources": sources,
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "nodes": len(nodes),
            "edges": len(edges),
            "subjects": sum(1 for n in nodes if n["layer"] == "subject"),
            "tasks": sum(1 for n in nodes if n["layer"] == "task"),
            "boundaries": sum(1 for n in nodes if n["layer"] == "boundary"),
            "models": sum(1 for n in nodes if n["layer"] == "model"),
            "aiRows": len(ai_rows),
            "taskBlocks": len(task_nodes),
            "rulingRows": ruling_stats["rows"],
            "rulingDecided": ruling_stats["decided"],
            "archNodes": len(arch_model.get("nodes", [])),
            "archEdges": len(arch_model.get("edges", [])),
            "archSkippedEdges": arch_stats["skipped_edges"],
            "danglingEdges": dangling,
            "anchors": sum(len(n.get("anchors") or []) for n in nodes)
                       + sum(len(e.get("anchors") or []) for e in edges),
        },
        "notes": [
            "四源均按工作树读取，锚点 side=working-tree；行号由本脚本现算，不手填。",
            "任务看板源取任务登记正本；board_server 服务层与整机数据不读（派工函边界：不监视整机整网）。",
            "架构模型只读其登记件本身，不读它 sourceRefs 指向的代码文件。",
            "本页零网络请求：只经 file:// 加载本地脚本与 data/field-model.js。",
        ],
        "sourceMeta": meta,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "field-model.json"
    js_path = out_dir / "field-model.js"
    tmp_json = json_path.with_suffix(".json.tmp")
    tmp_js = js_path.with_suffix(".js.tmp")
    tmp_json.write_text(json.dumps(model, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    js_body = json.dumps(model, ensure_ascii=True, separators=(",", ":"))
    tmp_js.write_text("// generated by build_field_model.py at " + model["generatedAt"] + "\n"
                      "window.FIELD_MODEL = " + js_body + ";\n", encoding="utf-8", newline="\n")
    os.replace(tmp_json, json_path)
    os.replace(tmp_js, js_path)
    return model, json_path, js_path


def watch(root: Path, out_dir: Path, interval: float):
    src_paths = {k: root / v for k, v in SRC_REL.items()}
    last = {}
    while True:
        try:
            sig = {}
            for k, p in src_paths.items():
                st = p.stat()
                sig[k] = (st.st_mtime_ns, st.st_size)
            if sig != last:
                model, jp, js = build(root, out_dir)
                last = sig
                print(f"[{datetime.now().strftime('%H:%M:%S')}] built {jp.name} "
                      f"version={model['version']} nodes={model['stats']['nodes']} "
                      f"edges={model['stats']['edges']}", flush=True)
        except Exception as exc:
            print(f"[watch] error: {exc}", flush=True)
        time.sleep(interval)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(DEFAULT_ROOT), help="仓库根（四源按相对路径读取）")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="输出目录")
    ap.add_argument("--watch", action="store_true", help="监视四源 mtime，变化即重建")
    ap.add_argument("--interval", type=float, default=2.0)
    args = ap.parse_args()
    root = Path(args.root).resolve()
    out_dir = Path(args.out).resolve()
    if args.watch:
        watch(root, out_dir, args.interval)
        return
    model, jp, js = build(root, out_dir)
    print(f"OK {jp}")
    print(f"OK {js}")
    print(json.dumps(model["stats"], ensure_ascii=False))
    print(f"version={model['version']} generatedAt={model['generatedAt']}")


if __name__ == "__main__":
    main()