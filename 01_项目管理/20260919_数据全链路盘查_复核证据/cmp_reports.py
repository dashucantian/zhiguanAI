import re,sys,os
sys.stdout.reconfigure(encoding="utf-8")
r=r"D:\Project\zhiguanAI\muse2-repo\muse2-master\report"
for f in ["local_20260911_232300.report.html","local_20260919_222226.report.html","local_20260913_190636.report.html"]:
    p=os.path.join(r,f)
    if not os.path.exists(p):
        cand=[x for x in os.listdir(r) if x.startswith(f[:20])]
        print(f,"-> not found, cand:",cand[:3]); continue
    t=open(p,encoding="utf-8",errors="ignore").read()
    pairs=re.findall(r'<span class="label">(.*?)</span><br>\s*<span class="value"[^>]*>(.*?)</span>',t)
    print(f"\n=== {f}  (len {len(t)}) labels={len(pairs)}")
    for k,v in pairs: print(f"   {k} = {v}")
    print("   <title>:",re.search(r'<title>(.*?)</title>',t).group(1) if re.search(r'<title>(.*?)</title>',t) else None)
