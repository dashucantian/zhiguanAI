import sys,os,re
sys.stdout.reconfigure(encoding="utf-8")
root=r"D:\Project\zhiguanAI"
for dp,dn,fn in os.walk(root):
    if any(s in dp for s in ("\\venv\\","site-packages","\\.git\\","node_modules")): continue
    for f in fn:
        if f in ("neuradock_receiver.py","ble_receiver.py","report_generator.py"):
            p=os.path.join(dp,f)
            t=open(p,encoding="utf-8",errors="ignore").read()
            print(f"\n##### {os.path.relpath(p,root)} lines={t.count(chr(10))+1}")
            for m in re.finditer(r'(butter|filtfilt|lfilter|SIGNAL_CHAIN|highpass|lowpass|notch|ema|alpha\s*=|SFREQ|sfreq\s*=)',t):
                ln=t[:m.start()].count("\n")+1
                line=t.splitlines()[ln-1].strip()
                print(f"   {ln}: {line[:150]}")
