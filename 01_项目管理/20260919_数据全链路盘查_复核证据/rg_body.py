import sys,re
sys.stdout.reconfigure(encoding="utf-8")
p=r"D:\Project\zhiguanAI\muse2-repo\muse2-master\muse-cloud-server\report_generator.py"
t=open(p,encoding="utf-8",errors="ignore").read()
print("lines:",t.count(chr(10))+1)
print("has <!DOCTYPE:", "<!DOCTYPE" in t, " has class=\"label\":", 'class="label"' in t)
print("has 噪声:", "噪声" in t, " has clean_pct:", "clean_pct" in t)
i=t.find("def generate_report")
print("\n=== generate_report body ===")
print(t[i:i+2000])
