import re,os,sys,glob
sys.stdout.reconfigure(encoding="utf-8")
root=r"D:\Project\zhiguanAI"
for dp,dn,fn in os.walk(root):
    if any(s in dp for s in ("\\venv\\","site-packages","\\.git\\","node_modules","\\output\\","\\report\\")): continue
    for f in fn:
        if not f.endswith((".py",".js",".html")): continue
        p=os.path.join(dp,f)
        try: t=open(p,encoding="utf-8",errors="ignore").read()
        except Exception: continue
        for pat in ("Noise epochs","Avg T/B Ratio","generate_report("):
            if pat in t:
                print(f"{pat!r:22} <- {os.path.relpath(p,root)}  x{t.count(pat)}")
