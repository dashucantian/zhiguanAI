import json,glob,os,sys,re
sys.stdout.reconfigure(encoding="utf-8")
Z=r"D:\Project\Zen-EEG"
print(f"{'session':<24}{'status':<12}{'clean_ratio':<13}{'noise_epochs':<14}{'report_has_block':<17}{'eff_hz':<9}{'loss'}")
reg={}
import csv
for r in csv.DictReader(open(os.path.join(Z,"01_registry","session_registry.csv"),encoding="utf-8-sig")):
    reg[r["session_id"]]=r
for sid,r in reg.items():
    qp=os.path.join(Z,"03_quality_control",sid,"qc.json")
    if not os.path.exists(qp): qp=os.path.join(Z,"03_quality_control","quarantine",sid,"qc.json")
    qc=json.load(open(qp,encoding="utf-8")) if os.path.exists(qp) else {}
    rp=os.path.join(Z,"02_raw",sid,"report.html")
    if not os.path.exists(rp): rp=os.path.join(Z,"03_quality_control","quarantine",sid,"report.html")
    blk="n/a"
    if os.path.exists(rp):
        t=open(rp,encoding="utf-8",errors="ignore").read()
        blk = "YES" if "噪声段数" in t or "Noise epochs" in t else "NO"
    print(f"{sid:<24}{r['status']:<12}{str(qc.get('clean_ratio')):<13}{str(qc.get('noise_epochs',''))[:13]:<14}{blk:<17}{str(qc.get('effective_sample_rate_hz','')):<9}{qc.get('packet_loss_rate','')}")
