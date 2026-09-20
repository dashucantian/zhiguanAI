import sys,os
sys.stdout.reconfigure(encoding="utf-8")
root=r"D:\Project\zhiguanAI"
needles=["噪声段数","干净数据比例"]
skip=("\\venv\\","site-packages","\\.git\\","node_modules")
for dp,dn,fn in os.walk(root):
    if any(s in dp for s in skip): continue
    for f in fn:
        if not f.endswith((".py",".js",".json",".html",".md")): continue
        p=os.path.join(dp,f)
        try: t=open(p,encoding="utf-8",errors="ignore").read()
        except Exception: continue
        for n in needles:
            if n in t:
                print(f"{n} <- {os.path.relpath(p,root)}  (x{t.count(n)})")
