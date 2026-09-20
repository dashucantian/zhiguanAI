import re,os,sys,glob,collections
sys.stdout.reconfigure(encoding="utf-8")
r=r"D:\Project\zhiguanAI\muse2-repo\muse2-master\report"
rows=[]
for f in sorted(glob.glob(os.path.join(r,"*.report.html"))):
    t=open(f,encoding="utf-8",errors="ignore").read()
    b=os.path.basename(f); d=b.split("_")[1][:8]
    lang = "EN" if "Noise epochs" in t else ("ZH" if "噪声段数" in t or "干净数据比例" in t else "ZH-4label")
    rows.append((d,lang,b))
byday=collections.defaultdict(collections.Counter)
for d,l,b in rows: byday[d][l]+=1
print(f"{'date':<10}{'ZH-4label':<11}{'ZH':<6}{'EN':<6}")
for d in sorted(byday):
    c=byday[d]; print(f"{d:<10}{c['ZH-4label']:<11}{c['ZH']:<6}{c['EN']:<6}")
print("\n-- EN files --")
for d,l,b in rows:
    if l=="EN": print("  ",b)
