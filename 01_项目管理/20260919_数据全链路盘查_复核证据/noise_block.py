import re,glob,os,sys,collections
sys.stdout.reconfigure(encoding="utf-8")
r=r"D:\Project\zhiguanAI\muse2-repo\muse2-master\report"
files=sorted(glob.glob(os.path.join(r,"*.report.html")))
has=[];no=[]
for f in files:
    t=open(f,encoding="utf-8",errors="ignore").read()
    m=re.search(r'噪声段数</span><br>\s*<span class="value"[^>]*>([^<]+)</span>',t)
    if m: has.append((os.path.basename(f),m.group(1)))
    else: no.append(os.path.basename(f))
print("total",len(files),"has-noise-block",len(has),"no-block",len(no))
print("\nnoise-block values (count of X/Y):")
for f,v in has: print(f"   {f}  ->  {v}")
print("\n-- no-block: confirm they are the NEW template (only 4 labels) --")
for f in no[:6]:
    t=open(os.path.join(r,f),encoding="utf-8",errors="ignore").read()
    n=len(re.findall(r'<span class="label">',t))
    print(f"   {f}  labels={n}")
