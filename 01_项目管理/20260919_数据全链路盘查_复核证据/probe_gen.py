import re,sys
sys.stdout.reconfigure(encoding="utf-8")
p=r"D:\Project\zhiguanAI\muse2-repo\muse2-master\muse-cloud-server\report_generator.py"
t=open(p,encoding="utf-8",errors="ignore").read()
for lab in ("噪声段数","干净数据比例","记录时长","Noise epochs","Clean data"):
    print(f"{lab!r}: count={t.count(lab)}")
i=t.find("记录时长")
print("\n--- summary template slice ---")
print(t[max(0,i-1500):i+900])
