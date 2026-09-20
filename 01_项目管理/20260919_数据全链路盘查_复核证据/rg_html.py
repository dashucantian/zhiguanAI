import sys,re
sys.stdout.reconfigure(encoding="utf-8")
p=r"D:\Project\zhiguanAI\muse2-repo\muse2-master\muse-cloud-server\report_generator.py"
t=open(p,encoding="utf-8",errors="ignore").read()
for pat in ("clean_pct","噪声","<!DOCTYPE"):
    for m in re.finditer(re.escape(pat),t):
        ln=t[:m.start()].count(chr(10))+1
        print(f"[{pat}] line {ln}: {t.splitlines()[ln-1].strip()[:170]}")
