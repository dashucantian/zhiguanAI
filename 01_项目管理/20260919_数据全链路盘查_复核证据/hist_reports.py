import re,glob,os,sys
sys.stdout.reconfigure(encoding="utf-8")
r=r"D:\Project\zhiguanAI\muse2-repo\muse2-master\report"
files=sorted(glob.glob(os.path.join(r,"*.report.html")))
ok=[];bad=[]
pat=re.compile(r'干净数据比例</span><br>\s*<span class="value"[^>]*>([^<]+)</span>')
loose=re.compile(r'干净数据比例')
for f in files:
    t=open(f,encoding="utf-8",errors="ignore").read()
    if loose.search(t):
        m=pat.search(t); ok.append((os.path.basename(f), m.group(1) if m else "LABEL-BUT-NO-STRICT-MATCH"))
    else: bad.append(os.path.basename(f))
print(f"total reports={len(files)}  has-label={len(ok)}  missing-label={len(bad)}")
print("\n-- has label (first/last 5) --")
for x in ok[:5]+ok[-5:]: print("  ",x)
print("\n-- missing label: date histogram --")
from collections import Counter
c=Counter(f.split("_")[1][:8] for f in bad)
for k in sorted(c): print(f"   {k}: {c[k]}")
print("\n-- has label: date histogram --")
c2=Counter(f.split("_")[1][:8] for f,_ in ok)
for k in sorted(c2): print(f"   {k}: {c2[k]}")
print("\n-- strict regex failures among has-label --")
for f,v in ok:
    if v=="LABEL-BUT-NO-STRICT-MATCH": print("   ",f)
