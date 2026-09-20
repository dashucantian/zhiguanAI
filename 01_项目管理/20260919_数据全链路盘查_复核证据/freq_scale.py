import numpy as np,sys,os
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0,r"D:\Project\zhiguanAI\muse2-repo\muse2-master")
sys.path.insert(0,r"D:\Project\zhiguanAI\muse2-repo\muse2-master\muse-cloud-server")
import report_generator as rg
p=r"D:\Project\zhiguanAI\muse2-repo\muse2-master\report\local_20260919_222226.npz"
with np.load(p,allow_pickle=True) as d:
    eeg=d["eeg"]; m=d["meta"].item()
    true_sf=float(m["sfreq"])
print("shape",eeg.shape,"true sfreq",true_sf,"channels",m["channels"])
chunk=eeg[:int(true_sf*10),:]
for label,sf in (("TRUE 250Hz (correct)",true_sf),("HARDCODED 256Hz (what report uses)",256.0)):
    bp=rg.compute_band_power_chunk(chunk,sf)
    rel=bp["rel"]
    print(f"\n-- {label} --")
    for b in rg.BANDS: print(f"    {b:6} rel={float(rel[b].mean()):.4f}")
    print(f"    noise flags={bp['noise']}  -> all_noisy={bool(np.all(bp['noise']))}")
# frequency mapping demo
print("\n-- freq axis convention demo --")
for f_true in (10.0,):
    print(f"   a true {f_true} Hz rhythm read at sfreq=256 -> appears at {f_true*256.0/true_sf:.2f} Hz in the analysis")
    print(f"   => lands in band:", [b for b,(lo,hi) in rg.BANDS.items() if lo<=f_true*256.0/true_sf<=hi])
