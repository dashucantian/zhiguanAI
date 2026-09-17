"""删除前只读预检：逐个核验待删文件确为本次测试产物（agent 自产物）

纪律依据：
- 红线7 / feedback_cleanup_explicit_list：清理数据目录**只许显式文件名**，禁 glob 或
  时间前缀模式（2026-09-09 曾用 local_20260909_2* 误删法师 2.7 小时真机会话）
- 删除前须只读证明其为 agent 自产物，不得凭文件名猜测
判据：meta.participant 含 TEST 标记 且 note 含"勿入库" → 确认为本次测试产物
"""
import os
import sys
import numpy as np

BASE = r"C:\Users\tiand\OneDrive\zhiguanAI\muse2-repo\muse2-master\report"

# 法师明确授权删除的两个文件（显式清单，逐个列名，无通配）
TARGETS = [
    "local_20260913_201423.npz",
    "local_20260913_201711.npz",
]
# 必须原封不动保护的文件（法师真机采集数据）
PROTECT = "local_20260913_190636.npz"

print("=" * 78)
print("删除前只读预检")
print("=" * 78)

all_ok = True
abs_paths = []
for name in TARGETS:
    p = os.path.join(BASE, name)
    print(f"\n【{name}】")
    if not os.path.exists(p):
        print("  ⚠️ 文件不存在，跳过（不视为失败）")
        continue
    ap = os.path.abspath(p)
    with np.load(p, allow_pickle=True) as z:
        meta = z["meta"].item() if "meta" in z.files else {}
        eeg = np.asarray(z["eeg"])
    part = meta.get("participant")
    note = meta.get("note")
    stype = meta.get("session_type")
    dev = meta.get("device")
    print(f"  绝对路径    : {ap}")
    print(f"  大小        : {os.path.getsize(p)/1024/1024:.2f} MB   样本 {eeg.shape[0]}")
    print(f"  participant : {part!r}")
    print(f"  session_type: {stype!r}")
    print(f"  device      : {dev!r}")
    print(f"  note        : {note!r}")
    is_test = bool(part and "TEST" in str(part).upper()) and bool(note and "勿入库" in str(note))
    print(f"  判定        : {'✅ 确认为测试产物（participant含TEST且note含勿入库）' if is_test else '❌ 不符合测试产物特征，禁止删除'}")
    if not is_test:
        all_ok = False
    else:
        abs_paths.append(ap)

print(f"\n【保护区核验】{PROTECT}（法师真机数据，不在删除清单内）")
pp = os.path.join(BASE, PROTECT)
if os.path.exists(pp):
    print(f"  ✅ 存在，{os.path.getsize(pp)/1024/1024:.2f} MB —— 本次操作不会触碰它")
else:
    print(f"  ⚠️ 未找到该文件（请人工确认法师数据是否已在别处）")

# 附带发现：同名 report.html 伴生文件（法师未点名，不擅自删除）
print("\n【附带发现：伴生 report.html（法师未点名授权，本轮不删）】")
for name in TARGETS:
    html = name.replace(".npz", ".report.html")
    hp = os.path.join(BASE, html)
    print(f"  {html}: {'存在' if os.path.exists(hp) else '不存在'}"
          f"{f'  {os.path.getsize(hp)/1024:.1f}KB' if os.path.exists(hp) else ''}")

print("\n" + "=" * 78)
if all_ok and abs_paths:
    print(f"预检通过：{len(abs_paths)} 个文件确认为测试产物，可送回收站")
    for ap in abs_paths:
        print(f"  → {ap}")
else:
    print("预检未通过，禁止删除")
print("=" * 78)
sys.exit(0 if (all_ok and abs_paths) else 1)
