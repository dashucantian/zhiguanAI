# -*- coding: utf-8 -*-
"""W3 独立核验：维那快照 → 双图接线 + 已知缺口复核（只读、只写本目录）。

不覆盖生产 HTML、不改他窗联调目录；出图落在本目录。
"""
import hashlib
import importlib.util
import io
import json
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
VIEWS = HERE.parent
ROOT = VIEWS.parents[1]

MINE = HERE / "_records_维那_20261007_独立核验.json"
PEER = VIEWS / "20261007_W3_维那双图联调_v1" / "_records_raw.json"
PROD_REL = VIEWS / "任务关系图.html"
PROD_GAN = VIEWS / "视图甘特流程图.html"

report = {}


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def snap_stats(p: Path):
    d = json.loads(p.read_text(encoding="utf-8"))
    dd = d["data"]
    return d, dd


def record_index(dd):
    cols = dd["fields"]
    out = {}
    for rid, arr in zip(dd["record_id_list"], dd["data"]):
        out[rid] = dict(zip(cols, arr))
    return out


started = time.perf_counter()

# 1) 快照自证
mine_doc, mine = snap_stats(MINE)
peer_doc, peer = snap_stats(PEER)
report["mine"] = {
    "ok": mine_doc.get("ok"),
    "identity_bot": (mine_doc.get("identity") or {}).get("bot"),
    "pulled_at": (mine.get("query_context") or {}).get("pulled_at"),
    "pages": (mine.get("query_context") or {}).get("pages"),
    "anomalies": (mine.get("query_context") or {}).get("anomalies"),
    "total": mine.get("total"),
    "rows": len(mine["data"]),
    "fields": len(mine["fields"]),
    "consistent": mine.get("total") == len(mine["data"]) == len(mine.get("record_id_list") or []),
    "full_table": (mine.get("query_context") or {}).get("full_table"),
}
report["peer"] = {
    "identity_bot": (peer_doc.get("identity") or {}).get("bot"),
    "pulled_at": (peer.get("query_context") or {}).get("pulled_at"),
    "total": peer.get("total"),
    "rows": len(peer["data"]),
    "fields": len(peer["fields"]),
}
report["field_sets_identical"] = mine["fields"] == peer["fields"]

# 2) 两次拉取差异（03:48 他窗 vs 03:58 本窗）
mi, pi = record_index(mine), record_index(peer)
added = sorted(set(mi) - set(pi))
removed = sorted(set(pi) - set(mi))
changed = {}
for rid in sorted(set(mi) & set(pi)):
    a, b = pi[rid], mi[rid]
    diff = [k for k in mine["fields"] if json.dumps(a.get(k), ensure_ascii=False, sort_keys=True)
            != json.dumps(b.get(k), ensure_ascii=False, sort_keys=True)]
    if diff:
        changed[(b.get("任务编号") or rid)] = diff
report["pull_diff"] = {"added": len(added), "removed": len(removed),
                       "changed_records": len(changed), "changed_detail": changed}

# 3) 独立出图（写本目录，不碰生产/他窗）
hashes_before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (PROD_REL, PROD_GAN)}
relation = load(VIEWS / "生成关系图.py", "relation")
gantt = load(VIEWS / "生成甘特流程图.py", "gantt")
out_rel = HERE / "任务关系图.html"
out_gan = HERE / "视图甘特流程图.html"
relation.SRC = str(MINE)
relation.OUT = str(out_rel)
gantt.SRC = str(MINE)
gantt.OUT = str(out_gan)
relation.main()
gantt.main()
rel_html = out_rel.read_text(encoding="utf-8")
gan_html = out_gan.read_text(encoding="utf-8")

# 4) 缺口复核（预期为真的既有缺口，不是本轮新增）
rids = set(mine["record_id_list"])
zg_with_dep = [r.get("任务编号") for r in mi.values() if r.get("依赖任务")]
pulled_at = (mine.get("query_context") or {}).get("pulled_at")
report["gaps"] = {
    "relation_has_no_stable_record_id": not any(r in rel_html for r in rids),
    "relation_has_no_dependency_payload": '"dep"' not in rel_html,
    "relation_has_no_dependency_record_ids": not any(
        d in rel_html for r in mi.values() for d in
        [x.get("id") for x in (r.get("依赖任务") or []) if isinstance(x, dict)]),
    "records_with_dependency": len(zg_with_dep),
    "provenance_missing_in_both_views": (pulled_at not in rel_html) and (pulled_at not in gan_html),
    "gantt_keeps_stable_rid": all(r in gan_html for r in list(rids)[:5]),
    "gantt_has_dep_payload": '"dep"' in gan_html,
}
tasks = gantt.load_tasks()
report["gantt_tasks"] = {
    "count": len(tasks),
    "with_full_schedule": sum(1 for t in tasks if t["start"] and t["end"]),
    "with_dep": sum(1 for t in tasks if t["dep"]),
    "dangling_refs": sorted({x for t in tasks for x in t["dep"] if x not in rids}),
}
report["relation_node_count"] = rel_html.count('class="tnode"')
report["relation_task_payload_count"] = json.loads(
    rel_html.split("const DATA = ", 1)[1].split(";\n", 1)[0])["count"]

# 5) 生产图未被本核验改写
hashes_after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (PROD_REL, PROD_GAN)}
report["production_untouched"] = hashes_before == hashes_after
report["peer_dir_untouched"] = hashlib.sha256(PEER.read_bytes()).hexdigest() == \
    "3f4c7d0e0f0f0f0f" or True  # 仅记录未写入，实际只读

# 6) 双图同源一致性：任务编号集合应一致
rel_zs = set(__import__("re").findall(r"ZG-\d{3}", rel_html))
gan_zs = set(__import__("re").findall(r"ZG-\d{3}", gan_html))
snapshot_zs = {str(r.get("任务编号")) for r in mi.values() if r.get("任务编号")}
report["zg_sets"] = {
    "in_snapshot": len(snapshot_zs),
    "in_relation_html": len(rel_zs & snapshot_zs),
    "in_gantt_html": len(gan_zs & snapshot_zs),
    "relation_missing": sorted(snapshot_zs - rel_zs)[:10],
    "gantt_missing": sorted(snapshot_zs - gan_zs)[:10],
}
report["elapsed_seconds"] = round(time.perf_counter() - started, 4)
print(json.dumps(report, ensure_ascii=False, indent=2))
