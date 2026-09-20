import sys,os
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0,r"D:\Project\zhiguanAI\muse2-repo\muse2-master")
sys.path.insert(0,r"D:\Project\zhiguanAI\muse2-repo\muse2-master\muse-cloud-server")
try:
    import report_generator as rg
    print("report_generator OK ->",rg.__file__)
    print("  BANDS:",rg.BANDS)
    print("  CHANNELS:",rg.CHANNELS)
    print("  SFREQ:",rg.SFREQ)
    print("  EPOCH_SECONDS/STEP:",rg.EPOCH_SECONDS,rg.EPOCH_STEP)
except Exception as ex:
    print("import failed:",type(ex).__name__,ex)
# what does muse_local_server do to path?
p=r"D:\Project\zhiguanAI\muse2-repo\muse2-master\muse_local_server.py"
t=open(p,encoding="utf-8",errors="ignore").read().splitlines()
for i,l in enumerate(t,1):
    if "sys.path" in l or "muse-cloud-server" in l or "cloud" in l.lower() and "path" in l.lower():
        print(f"  muse_local_server:{i}: {l.strip()}")
