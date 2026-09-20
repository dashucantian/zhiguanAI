import csv,os,sys,json
sys.stdout.reconfigure(encoding="utf-8")
Z=r"D:\Project\Zen-EEG"
rows=list(csv.DictReader(open(os.path.join(Z,"01_registry","session_registry.csv"),encoding="utf-8-sig")))
print(f"{'session':<24}{'type':<10}{'dur_s':<8}{'min':<7}{'status':<13}{'>=25min?'}")
tot=0
for r in rows:
    d=r["duration_seconds"]
    try: m=float(d)/60
    except: m=None
    ok = ("YES" if m and m>=25 else ("NO" if m else "-"))
    if m: tot+=m
    print(f"{r['session_id']:<24}{r['session_type']:<10}{d:<8}{(f'{m:.1f}' if m else '-'):<7}{r['status']:<13}{ok}")
print("\ntotal recorded minutes:",round(tot,1))
print("\n=== participant_registry.csv ===")
print(open(os.path.join(Z,"01_registry","participant_registry.csv"),encoding="utf-8-sig").read())
print("=== P001/profile.md ===")
print(open(os.path.join(Z,"01_registry","P001","profile.md"),encoding="utf-8-sig").read())
