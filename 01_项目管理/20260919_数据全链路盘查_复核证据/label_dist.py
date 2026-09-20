import re,os,sys,glob,collections
sys.stdout.reconfigure(encoding="utf-8")
r=r"D:\Project\zhiguanAI\muse2-repo\muse2-master\report"
t=open(os.path.join(r,"local_20260830_202946.report.html"),encoding="utf-8",errors="ignore").read()
print("=== 20260830_202946 labels ===")
for k,v in re.findall(r'<span class="label">(.*?)</span><br>\s*<span class="value"[^>]*>(.*?)</span>',t): print("  ",k,"=",v)
# distribution of label counts + noise block presence by month
cnt=collections.Counter()
block=collections.Counter()
for f in sorted(glob.glob(os.path.join(r,"*.report.html"))):
    tt=open(f,encoding="utf-8",errors="ignore").read()
    n=len(re.findall(r'<span class="label">',tt))
    d=os.path.basename(f).split("_")[1][:6]
    cnt[(d,n)]+=1
    if "噪声段数" in tt: block[d]+=1
print("\n=== (month,label-count): files ===")
for k in sorted(cnt): print("  ",k,cnt[k])
print("\n=== month: reports WITH noise block ===")
for k in sorted(block): print("  ",k,block[k])
