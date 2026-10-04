# -*- coding: utf-8 -*-
"""qc_done 两路事件契约测试（P0-6 v2·合成夹具，非完整服务/真机验收）。

接 W3 snapshot_contract_test.py 延长线（AI-014 评审指出的夹具缺口：
「qc_done 两路事件测试未被现有元数据夹具覆盖」）。

覆盖三层：
  T1 静态契约：console_server.py 恰有 2 个 qc_done 发射位点（监测/闭环），
     payload 均含 reasons / threshold_version / qc_version（源码级守卫）；
     消费位点（e.get("type")=="qc_done"）不计入发射数；
  T2 行为夹具：session_contract.append_event 真函数——
     T2a 文件不存在→返回 False 且不建文件（「契约是附属物」跳过语义）；
     T2b 预建文件→写 qc_done→读回，payload 契约键在位；
  T3 行为夹具：qc_pipeline.assess_cached 对合成 npz（d["eeg"]）返回
     recommend / reasons（上游数据源契约；console_server.qc_assess 为薄委托层）。

诚实边界：T1 静态断言；T2/T3 真实函数＋合成数据；不导入 console_server 全模块；
真机验收不在本件范围。v1→v3 修订：v1 三败根因＝消费位点误计／append_event
跳过语义未预建文件／DSH 沙箱 %TEMP% 受限改项目内临时区；v3＝T3 改用真实现 assess_cached（qc_assess 系薄委托）＋合成时长 36s 越 MIN_DURATION_S。
红线：零真机数据，零出网；临时区用后即清。
"""
import json
import os
import shutil
import sys

import numpy as np

ROOT = r"D:\Project\zhiguanAI"
sys.path.insert(0, ROOT)
SCRATCH = os.path.join(ROOT, "_analysis_tmp", "qcdone_p06_run")

results = []


def check(name, passed, detail):
    results.append({"test": name, "passed": bool(passed), "detail": detail})
    print(("[PASS] " if passed else "[FAIL] ") + name + " — " + detail)


# ── T1 静态契约（发射位点 ≠ 消费位点）──
src = open(os.path.join(ROOT, "console_server.py"), encoding="utf-8").read()
lines = src.splitlines()
emit, consume = [], []
for i, l in enumerate(lines):
    if '"qc_done"' in l:
        (consume if ('e.get("type")' in l or "e.get('type')" in l) else emit).append(i)
check("T1a_two_emit_sites", len(emit) == 2,
      f"发射位点={len(emit)}（行 {[s + 1 for s in emit]}），消费位点={len(consume)}（行 {[s + 1 for s in consume]}，不计入）")
names = ["监测路径", "闭环路径"]
for idx, s in enumerate(emit[:2]):
    window = "\n".join(lines[s:s + 16])
    ok = all(k in window for k in ("reasons", "threshold_version", "qc_version"))
    check(f"T1b_site{idx + 1}_contract_keys", ok,
          f"{names[idx]}位点 payload 三键{'齐' if ok else '缺'}")

# ── T2 行为夹具：append_event 真函数 ──
try:
    import session_contract as sc
    os.makedirs(SCRATCH, exist_ok=True)
    ev_missing = os.path.join(SCRATCH, "events_absent.jsonl")
    r = sc.append_event(ev_missing, "qc_done", "system", "derived", {"a": 1})
    ok = (r is False) and (not os.path.exists(ev_missing))
    check("T2a_skip_when_absent", ok,
          f"文件不存在→返回 {r}（契约期望 False）且不建文件：{'是' if not os.path.exists(ev_missing) else '否'}")
    ev = os.path.join(SCRATCH, "events.jsonl")
    open(ev, "w", encoding="utf-8").close()  # 预建（生产语义：会话初始化建文件）
    payload = {"recommend": "keep", "clean_ratio": 0.9, "packet_loss_rate": 0.0,
               "reasons": ["合成夹具无原因"],
               "threshold_version": "SYNTH", "qc_version": "SYNTH"}
    r2 = sc.append_event(ev, "qc_done", "system", "derived", payload,
                         "闭环路径质检完成（夹具）")
    back = [json.loads(l) for l in open(ev, encoding="utf-8") if l.strip()]
    hit = [e for e in back if e.get("type") == "qc_done"]
    ok = (r2 is True) and len(hit) == 1 and all(k in (hit[0].get("payload") or {}) for k in payload)
    check("T2b_roundtrip_and_keys", ok,
          f"返回 {r2}；读回 {len(back)} 事件，qc_done={len(hit)}，payload 键{'齐' if ok else '缺'}")
except Exception as e:
    check("T2a_skip_when_absent", False, f"异常：{type(e).__name__}: {e}")
    check("T2b_roundtrip_and_keys", False, f"异常：{type(e).__name__}: {e}")

# ── T3 行为夹具：qc_assess 对合成 npz ──
try:
    import qc_pipeline as qp
    os.makedirs(SCRATCH, exist_ok=True)
    npz = os.path.join(SCRATCH, "eeg_raw_synth.npz")
    rng = np.random.default_rng(7)
    eeg = rng.normal(0, 5.0, size=(7, 9000))  # 7ch × 36s @250Hz，µV 量级合成（越 MIN_DURATION_S=30）
    np.savez(npz, eeg=eeg, sfreq=np.array(250))
    qc = qp.assess_cached(npz)
    ok = ("recommend" in qc) and ("reasons" in qc)
    check("T3_qc_assess_synthetic", ok,
          f"recommend={qc.get('recommend')} reasons={len(qc.get('reasons') or [])} 条"
          f" THRESHOLD_VERSION={qp.THRESHOLD_VERSION}")
except Exception as e:
    check("T3_qc_assess_synthetic", False, f"异常：{type(e).__name__}: {e}")

# 清理临时区
try:
    shutil.rmtree(SCRATCH, ignore_errors=True)
except Exception:
    pass

n_pass = sum(1 for r in results if r["passed"])
print(f"\n== P0-6 qc_done 契约测试 v3：{n_pass}/{len(results)} 过 ==")
here = os.path.dirname(os.path.abspath(__file__))
out = os.path.join(here, "20261004_W1_qcdone_contract_test_result.txt")
with open(out, "w", encoding="utf-8") as f:
    json.dump({"source": "console_server.py 两位点＋session_contract.append_event＋qc_pipeline.qc_assess",
               "method": "静态断言＋真实函数合成夹具，非完整服务/真机验收",
               "version": "v2（v1 三败根因已修：消费位点误计/跳过语义预建/沙箱 TEMP 受限改项目内临时区）",
               "results": results}, f, ensure_ascii=False, indent=2)
print("结果落盘：" + out)
sys.exit(0 if n_pass == len(results) else 1)