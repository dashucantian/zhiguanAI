import numpy as np,glob,os,sys,json
sys.stdout.reconfigure(encoding="utf-8")
print(f"{'session':<26}{'keys':<44}{'shape':<16}{'sfreq':<8}{'dev':<11}{'scene':<11}{'dur_s':<9}{'dup_ts':<8}{'zx'}")
for root,dirs,files in os.walk(r"D:\Project\Zen-EEG"):
    for f in files:
        if not f.endswith(".npz"): continue
        p=os.path.join(root,f)
        try:
            with np.load(p,allow_pickle=True) as d:
                keys=list(d.files)
                m=d["meta"].item() if "meta" in keys else {}
                eeg=d["eeg"] if "eeg" in keys else None
                ts=d["timestamps"] if "timestamps" in keys else None
                dup=""
                if ts is not None and ts.size>1:
                    dts=np.diff(ts.astype(float))
                    dup=str(int((dts<=0).sum()))
                rel=os.path.relpath(p,r"D:\Project\Zen-EEG")
                print(f"{rel[:25]:<26}{','.join(keys)[:43]:<44}{str(getattr(eeg,'shape','')):<16}{str(m.get('sfreq','')):<8}{str(m.get('device',''))[:10]:<11}{str(m.get('scene',''))[:10]:<11}{str(round(float(m.get('duration',0)),1)):<9}{dup:<8}{m.get('zx_phase','')}")
        except Exception as ex:
            print(f"{f}  ERROR {type(ex).__name__}: {ex}")
