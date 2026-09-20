import re,glob,os
r=r"D:\Project\zhiguanAI\muse2-repo\muse2-master\report"
def probe(p,label):
    t=open(p,encoding="utf-8",errors="ignore").read()
    for lab in ("Noise epochs","噪声段数","Clean data","干净数据比例","Duration","记录时长"):
        idx=t.find(lab)
        print(f"  [{label}] {lab!r} found={idx>=0}")
        if idx>=0:
            print("      ctx:",repr(t[idx:idx+180]))
    for lab in ("Clean data","干净数据比例"):
        m=re.search(re.escape(lab)+r'</span><br>\s*<span class="value"[^>]*>([^<]+)</span>',t)
        print(f"  [{label}] regex {lab!r} ->",m.group(1) if m else None)
newest=sorted(glob.glob(os.path.join(r,"*.report.html")))[-1]
print("NEWEST:",os.path.basename(newest)); probe(newest,"new")
old=r"D:\Project\Zen-EEG\02_raw\ZEN-20260911-P001-S13\report.html"
print("\nARCHIVED:",os.path.basename(old)); probe(old,"old")
