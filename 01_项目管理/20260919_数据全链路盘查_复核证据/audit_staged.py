import numpy as np,glob,os,sys
sys.stdout.reconfigure(encoding="utf-8")
r=r"D:\Project\zhiguanAI\muse2-repo\muse2-master\report"
fs=sorted(glob.glob(os.path.join(r,"*.npz")))
print("staged npz total:",len(fs))
for tag in ("20260913_190636","20260911_232300"):
    hit=[os.path.basename(x) for x in fs if tag in x]
    print(f"  {tag}: {hit}")
sel=[f for f in fs if any(k in os.path.basename(f) for k in ("20260919_222226","20260919_215617","20260919_055248"))]
for f in sel:
    with np.load(f,allow_pickle=True) as d:
        keys=list(d.files); m=d["meta"].item()
        print("\n==",os.path.basename(f))
        print("   keys:",keys," eeg:",d["eeg"].shape, d["eeg"].dtype)
        if "eeg_pre_filter" in keys: print("   pre_filter:",d["eeg_pre_filter"].shape)
        ts=d["timestamps"]
        print("   ts[0]=",ts[0]," span=",round(float(ts[-1]-ts[0]),2))
        print("   meta keys:",sorted(m.keys()))
        for k in sorted(m):
            print("      ",k,"=",str(m[k])[:160])
