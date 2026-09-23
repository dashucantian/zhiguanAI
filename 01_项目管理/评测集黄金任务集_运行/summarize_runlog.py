# -*- coding: utf-8 -*-
"""只读汇总：读正式轮 results/正式/*__runlog.jsonl，打印每任务体量表。"""
import json
from pathlib import Path

BASE = Path(r"D:\Project\zhiguanAI\01_项目管理\评测集黄金任务集_运行\results\正式")
CTX = {"ornith-eval": 32768, "qwen36-eval": 32768, "qwen38-eval": 32768}

rows = []
for fp in sorted(BASE.glob("*__runlog.jsonl")):
    for line in fp.read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        if rec.get("_meta"):
            continue
        u = rec.get("usage", {}) or {}
        pt = u.get("prompt_tokens")
        ct = u.get("completion_tokens")
        rt = (u.get("completion_tokens_details", {}) or {}).get("reasoning_tokens")
        rows.append({
            "model": rec.get("model"), "mid": rec.get("model_id"), "task": rec.get("task"),
            "note": rec.get("note", ""), "finish": rec.get("finish_reason"),
            "prompt_tok": pt, "compl_tok": ct, "reason_tok": rt,
            "content_len": rec.get("content_len"), "err": rec.get("error"),
            "ctx_room": (CTX.get(rec.get("model_id"), 0) - (pt or 0)) if pt else None,
        })

print(f"{'model':<22}{'task':<9}{'note':<10}{'finish':<7}{'ptok':>6}{'ctok':>6}{'rtok':>6}{'clen':>6}{'ctx余量':>9}")
for r in rows:
    print(f"{str(r['model'])[:21]:<22}{str(r['task']):<9}{str(r['note'])[:9]:<10}"
          f"{str(r['finish']):<7}{str(r['prompt_tok']):>6}{str(r['compl_tok']):>6}"
          f"{str(r['reason_tok']):>6}{str(r['content_len']):>6}{str(r['ctx_room']):>9}")

for r in rows:
    if r["task"] == "L4-02b" and (r["content_len"] == 0):
        print(f"\n[02b 正文空] model={r['model']} prompt_tok={r['prompt_tok']} "
              f"reason吃满={r['reason_tok']} ctx余量={r['ctx_room']} → 02b 单任务重跑可将 "
              f"max_tokens 提至≈{r['ctx_room']}（仍在 ctx 内）")
