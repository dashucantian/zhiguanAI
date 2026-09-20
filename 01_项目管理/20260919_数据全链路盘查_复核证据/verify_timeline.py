import numpy as np,json,os,sys,csv
from datetime import datetime,timezone,timedelta
sys.stdout.reconfigure(encoding="utf-8")
Z=r"D:\Project\Zen-EEG"; TZ=timezone(timedelta(hours=8))
reg={r["session_id"]:r for r in csv.DictReader(open(os.path.join(Z,"01_registry","session_registry.csv"),encoding="utf-8-sig"))}
print(f"{'session':<24}{'reg_type':<10}{'meta.session_type':<19}{'ts[0]local':<21}{'meta.ts':<21}{'gap_s':<9}{'dur':<9}{'gap-dur':<9}")
for sid in reg:
    d=os.path.join(Z,"02_raw",sid)
    if not os.path.isdir(d): d=os.path.join(Z,"03_quality_control","quarantine",sid)
    p=os.path.join(d,"eeg_raw.npz")
    if not os.path.exists(p): print(f"{sid:<24}(no npz)"); continue
    with np.load(p,allow_pickle=True) as z:
        m=z["meta"].item(); ts=z["timestamps"]
    t0=datetime.fromtimestamp(float(ts[0]),TZ).replace(tzinfo=None)
    mts=datetime.fromisoformat(str(m["timestamp"])).replace(tzinfo=None)
    gap=(mts-t0).total_seconds(); dur=float(m["duration"])
    print(f"{sid:<24}{reg[sid]['session_type']:<10}{str(m.get('session_type','<ABSENT>')):<19}{t0.strftime('%m-%d %H:%M:%S'):<21}{mts.strftime('%m-%d %H:%M:%S'):<21}{gap:<9.1f}{dur:<9.1f}{gap-dur:<9.1f}")
    di=os.path.join(d,"device_info.json")
    if os.path.exists(di):
        dj=json.load(open(di,encoding="utf-8"))
        note=open(os.path.join(d,"session_note.txt"),encoding="utf-8").read()
        nq=[l for l in note.splitlines() if l.startswith("contact_quality")]
        print(f"{'':24}collection_start_utc={dj.get('collection_start_utc')}  nkeys={len(dj)}  meta.contact_quality={m.get('contact_quality','<ABSENT>')}  note={nq}")
