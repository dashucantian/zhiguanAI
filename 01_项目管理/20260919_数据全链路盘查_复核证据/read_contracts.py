import json,glob,os
r=r"D:\Project\zhiguanAI\muse2-repo\muse2-master\report"
for f in sorted(glob.glob(os.path.join(r,"*.session_manifest.json"))):
    m=json.load(open(f,encoding="utf-8"))
    print(os.path.basename(f))
    print("   sid=",m.get("session_id"),"scene=",m.get("scene"),"dev=",m.get("device"),"chain=",m.get("signal_chain"),"labels=",m.get("labels"),"consent=",repr(m.get("consent_version")))
for f in sorted(glob.glob(os.path.join(r,"*.session_events.jsonl"))):
    print("---",os.path.basename(f))
    for line in open(f,encoding="utf-8"):
        if line.strip():
            e=json.loads(line); print("   ",e.get("type"),e.get("actor"),e.get("kind"),json.dumps(e.get("payload"),ensure_ascii=False)[:110])
