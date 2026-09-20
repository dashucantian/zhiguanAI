import re,glob,os,io,sys
sys.stdout.reconfigure(encoding="utf-8")
r=r"D:\Project\zhiguanAI\muse2-repo\muse2-master\report"
newest=sorted(glob.glob(os.path.join(r,"*.report.html")))[-1]
t=open(newest,encoding="utf-8",errors="ignore").read()
print("FILE",os.path.basename(newest),"len",len(t))
# all label/value pairs
pairs=re.findall(r'<span class="label">(.*?)</span><br>\s*<span class="value"[^>]*>(.*?)</span>',t)
print("\n-- label/value pairs (new report) --")
for k,v in pairs[:30]: print(f"   {k!r} = {v!r}")
print("\n-- raw summary div slice --")
i=t.find('summary')
print(repr(t[i-200:i+1500]))
