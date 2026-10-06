"""Synthetic only; imports reviewed local modules; outputs into TemporaryDirectory."""
import importlib.util, json, tempfile, re, hashlib, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
TOOLS=Path(__file__).resolve().parent
VIEWS=ROOT/"01_项目管理/任务关系图"
def load(path, name):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
def main():
    started=time.perf_counter()
    adapter=load(TOOLS/"20261003_W3_task_export_adapter.py","adapter")
    checker=load(TOOLS/"20261003_W3_task_snapshot_check.py","checker")
    relation=load(VIEWS/"生成关系图.py","relation")
    gantt=load(VIEWS/"生成甘特流程图.py","gantt")
    items=[{"record_id":"recSYN_A","fields":{"任务编号":"ZG-SYN-A","任务名":"synthetic A","状态":"待启动","验收标准":"synthetic","依赖任务":[],"计划开始":"2026-10-07T09:00:00+08:00","计划截止":"2026-10-07T10:00:00+08:00"}},{"record_id":"recSYN_B","fields":{"任务编号":"ZG-SYN-B","任务名":"synthetic B","状态":"待启动","验收标准":"synthetic","依赖任务":["recSYN_A"]}}]
    source={"ok":True,"schema":"record-export-v1","data":{"items":items,"has_more":False}}
    normalized=adapter.normalize(source,"synthetic only, not remote")
    audit=checker.audit(normalized)
    assert audit["record_count"]==2 and audit["dependency_edge_count"]==1
    assert audit["with_full_schedule"]==1 and not audit["issues"]
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [VIEWS/"任务关系图.html",VIEWS/"视图甘特流程图.html"]}
    with tempfile.TemporaryDirectory(prefix="w3-dual-view-") as folder:
        base=Path(folder); src=base/"synthetic.json"
        src.write_text(json.dumps(normalized,ensure_ascii=False),encoding="utf-8")
        relation.SRC=str(src); relation.OUT=str(base/"relation.html")
        gantt.SRC=str(src); gantt.OUT=str(base/"gantt.html")
        relation.main(); gantt.main()
        a=Path(relation.OUT).read_text(encoding="utf-8")
        b=Path(gantt.OUT).read_text(encoding="utf-8")
        assert all(z in a and z in b for z in ["ZG-SYN-A","ZG-SYN-B"])
        tasks=gantt.load_tasks()
        assert tasks[1]["rid"]=="recSYN_B" and tasks[1]["dep"]==["recSYN_A"]
        assert tasks[1]["start"] is None and tasks[1]["end"] is None
        gaps={"relation_stable_record_id_missing":"recSYN_A" not in a,"relation_dependency_not_serialized":"\"dep\"" not in a,"provenance_not_serialized":normalized["provenance"]["normalized_at_utc"] not in a and normalized["provenance"]["normalized_at_utc"] not in b}
        assert all(gaps.values()), "Observed gaps changed; review expected baseline"
    assert all(hashlib.sha256((VIEWS/name).read_bytes()).hexdigest()==digest for name,digest in hashes.items())
    print(json.dumps({"synthetic_integration":"PASS","observed_open_gaps":gaps,"existing_outputs_unchanged":True,"elapsed_seconds":round(time.perf_counter()-started,4),"scope":"serialization only; no browser, remote access, acceptance or permissions tested"},ensure_ascii=False))
if __name__=="__main__": main()
