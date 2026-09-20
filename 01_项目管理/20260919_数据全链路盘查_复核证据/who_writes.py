import os,sys,re
sys.stdout.reconfigure(encoding="utf-8")
root=r"D:\Project\zhiguanAI"
pats=["干净数据比例","噪声段数","干净数据占比","⚠ 噪声 epoch","Noise epochs"]
skip=("\\venv\\","site-packages","\\.git\\","node_modules")
hits={p:[] for p in pats}
for dp,dn,fn in os.walk(root):
    if any(s in dp for s in skip): continue
    if "\\.git" in dp: continue
    for f in fn:
        if not f.endswith((".py",".js",".mjs",".html",".md",".json",".txt")): continue
        p=os.path.join(dp,f)
        try: t=open(p,encoding="utf-8",errors="ignore").read()
        except Exception: continue
        for pat in pats:
            if pat in t and "\\report\\" not in p:
                hits[pat].append(os.path.relpath(p,root))
for pat in pats:
    print(f"\n=== {pat!r} ({len(hits[pat])} files, report/ excluded) ===")
    for x in hits[pat][:25]: print("   ",x)
