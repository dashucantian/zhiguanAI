#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
20261006_W1_congci_pipeline_test.py — 批 C1 轻量自测：从此养脑管线事务化
=========================================================================

法师金口 2026-10-05「七项通过，继续施工」批 C1；两层闸门 adopted（轻量每批，
完整 bridge 自测仅批收口、法师在场——宿主曾于其中内核崩溃 bugcheck 0x3D）。

对应施工正本《20261005_驾驶舱×从此接入方案稿_v2.md》§二.2 六反例＋恢复注入：
  两路同 npz（认领件）／不同 npz 共脑（脑锁）／脑存索引败（恢复扫描补登）／
  索引先写脑败（顺序已杜绝——结构断言）／同内容换路径（source_hash 幂等）／
  处理版本变化（algo_version 入键＝新单元）。
另加：准入拒绝三路（类型/QC/撤回者）合成断言、failed→可重试（attempt 计数）、
  弃权 abstained 与 duplicate 严格分列、四态事件入会话事件流、失败不动正式脑
  （持久脑字节不变）、脑锁争用超时＝跳过不改判。

测试件头（契约 v0.2 变更纪律：源码 hash＋函数＋时刻）：运行时打印
  congci_pipeline.py／zhiguan_cadence_bridge.py 的 SHA-256 首 16 位，
  并断言被测函数在位（防测试件与源码失配）。

纪律：全程合成件（npz 白噪声 30s 会话），configure(tmp_root) 全隔离，
  **不触真实脑目录/登记表/03_qc**；auto_worker=False 由 drain() 同步消化。
退出码 0=全过。
"""

import hashlib
import json
import os
import shutil
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, r"D:\Project\zhiguanAI")
import congci_pipeline as cp
import registry_tx as tx

PASS = 0


def ok(name):
    global PASS
    PASS += 1
    print(f"[ok] {name}")


def sha16(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def make_npz(path, epochs=120, seed=1, sfreq=256, channels=4):
    """30s（120×1s epoch）白噪声会话——QC 判 ingest、feed 有有效 epoch。
    meta 与真机同形（qc_pipeline.assess 从 meta 读 sfreq/samples/duration）。"""
    np = __import__("numpy")
    rng = np.random.default_rng(seed)
    n = epochs * sfreq
    eeg = rng.standard_normal((n, channels))
    # 注入 θ 带慢振荡，让 z(α−θ) 有漂移（产生 in_state 时段，练习双 reward 路径）
    t = np.arange(n) / sfreq
    eeg[:, 1] += 0.6 * np.sin(2 * np.pi * 6.0 * t)
    meta = {"timestamp": "2026-10-06T00:00:00+08:00", "sfreq": sfreq,
            "channels": (["TP9", "AF7", "AF8", "TP10"] if channels == 4
                         else [f"ch{i}" for i in range(channels)]),
            "samples": n, "duration": float(n / sfreq),
            "scene": "test-synthetic"}
    np.savez(path, eeg=eeg, timestamps=t, meta=meta)
    return path


def touch_events(npz_path):
    """模拟采集端 save_bin 已 init_events（暂存期 sidecar 在位）。"""
    ep = cp._session_events_path(npz_path)
    os.makedirs(os.path.dirname(ep), exist_ok=True)
    if not os.path.exists(ep):
        with open(ep, "w", encoding="utf-8") as f:
            f.write(json.dumps({"schema_version": "1.0", "ts": "2026-10-06T00:00:00+08:00",
                                "type": "created", "actor": "system", "kind": "ruled",
                                "payload": {}, "note": "synthetic"}) + "\n")
    return ep


def read_events(npz_path):
    ep = cp._session_events_path(npz_path)
    if not os.path.exists(ep):
        return []
    return [json.loads(l) for l in open(ep, encoding="utf-8") if l.strip()]


def index_rows():
    return cp._read_index()["rows"]


def by_status():
    rows = index_rows()
    out = {}
    for r in rows:
        out[r["status"]] = out.get(r["status"], 0) + 1
    return out


def row_of(unit_id):
    for r in index_rows():
        if r["unit_id"] == unit_id:
            return r
    raise AssertionError(f"unit {unit_id} 不在索引")


def main() -> int:
    tmp = str(Path(r"D:\Project\zhiguanAI\_analysis_tmp")
              / f"congci_pipeline_test_{os.getpid()}")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)
    root = os.path.join(tmp, "congci_root")
    zen = os.path.join(tmp, "zen_root")
    os.makedirs(root, exist_ok=True)
    os.makedirs(zen, exist_ok=True)
    cp.configure(root=root, zen_root=zen, auto_worker=False,
                 brain_lock_timeout=1.0)

    # ── 测试件头：源码 hash＋函数在位（契约 v0.2 纪律）────────────────
    srcs = {p: sha16(os.path.join(r"D:\Project\zhiguanAI", p))
            for p in ("congci_pipeline.py", "zhiguan_cadence_bridge.py")}
    print(f"[header] 2026-10-06 {time.strftime('%H:%M:%S')} "
          f"src_sha16={srcs}")
    for fn in ("enqueue", "drain", "recover_pending", "_process_row",
               "admit", "process_session"):
        assert hasattr(cp, fn) or fn == "process_session", f"被测函数缺失：{fn}"
    from zhiguan_cadence_bridge import process_session, IN_STATE_Z, ALGO_VERSION
    assert IN_STATE_Z == 0.8 and ALGO_VERSION, "桥件常量失配"

    try:
        # ── 反例①两路同 npz（认领件＋在队幂等）────────────────────────
        pA = os.path.join(tmp, "sA.npz")
        make_npz(pA, seed=1)
        epA = touch_events(pA)
        r1 = cp.enqueue(pA, session_type="training", participant="P001",
                        scene="test")
        assert r1["queued"] and r1["status"] == "queued", f"首入队失败：{r1}"
        r2 = cp.enqueue(pA, session_type="training", participant="P001",
                        scene="test")
        assert r2["status"] == "already_pending" and not r2["queued"], \
            f"两路同 npz 未拦（反例①复现）：{r2}"
        # 认领件被活进程新鲜持有→worker 跳过不改判
        skA = r1["row"]["session_key"]
        assert cp._claim_acquire(skA), "认领件应可获取"
        res = cp.drain()
        assert res and res[0].get("skipped"), f"认领持有未跳过：{res}"
        cp._claim_release(skA)
        res = cp.drain()
        assert len(res) == 1 and res[0]["status"] == "committed", f"释放后未消化：{res}"
        ok("反例①两路同 npz：在队幂等拦第二路＋认领件挡并发处理，释放后单次收口")

        # ── 认领件安全（批 C0 锁族安全修订·W3 反例消费同款语义）──
        ck2 = "dead-claim-test"
        cp2 = cp._claim_path(ck2)
        os.makedirs(os.path.dirname(cp2), exist_ok=True)
        with open(cp2, "w", encoding="utf-8") as f:
            f.write("holder_pid=999999999\nowner_token=ghost\n")
        assert cp._claim_acquire(ck2), "死 pid 认领未接管（同款缺陷复现！）"
        cp._claim_release(ck2)
        assert not os.path.exists(cp2), "认领释放未删除"
        # 活持有者认领不可夺（自身 pid 在持）＋owner token 释放
        assert cp._claim_acquire(skA), "认领应可获取"
        assert not cp._claim_acquire(skA), "活持有者认领被夺（同款缺陷复现！）"
        cp._claim_release(skA)
        ok("认领件安全：死 pid 接管＋活持有者不可夺＋token 释放")

        # ── 反例②不同 npz 共脑（脑锁串行）＋脑锁争用＝跳过 ────────────
        pB = os.path.join(tmp, "sB.npz")
        make_npz(pB, seed=2)
        rb = cp.enqueue(pB, session_type="training", participant="P001",
                        scene="test")
        # 脑锁被活线程持有 → drain 超时跳过（不改判不失败）
        held = threading.Event()
        release = threading.Event()

        def hold_lock():
            with tx.locked(purpose="test-holder", lock_path=cp.brain_lock_path()):
                held.set()
                release.wait(30)
        th = threading.Thread(target=hold_lock)
        th.start()
        assert held.wait(5), "脑锁持有线程未就绪"
        t0 = time.monotonic()
        res = cp.drain()
        assert time.monotonic() - t0 < 10, "脑锁争用未按超时跳过"
        assert res and res[0].get("skipped"), f"脑锁争用应跳过：{res}"
        release.set()
        th.join(5)
        res = cp.drain()
        assert len(res) == 1 and res[0]["status"] == "committed", f"释放后未消化：{res}"
        rows = [r for r in index_rows() if r["status"] == "committed"]
        assert len(rows) == 2, f"共脑串行后 committed 数 {len(rows)} != 2"
        vb = row_of(rb["unit_id"])
        va = row_of(r1["unit_id"])
        assert vb["brain_base_version"] == va["result_brain_version"] == 1 and \
            vb["result_brain_version"] == 2, f"脑版本链断裂：{va} {vb}"
        ok("反例②不同 npz 共脑：脑锁串行版本链 1→2，争用＝跳过不改判")

        # ── 反例③脑存索引败→恢复扫描补登（提升后、索引前进程死亡）────
        pC = os.path.join(tmp, "sC.npz")
        make_npz(pC, seed=3)
        rc = cp.enqueue(pC, session_type="training", participant="P001",
                        scene="test")
        try:
            cp._process_row(rc["row"], inject_fail="index_write")
            raise AssertionError("注入 index_write 未抛（进程死亡应中断）")
        except RuntimeError as ex:
            assert "index_write" in str(ex)
        # 死亡窗口态：索引仍 pending，但正式脑已是 C 的候选（提升先于索引）
        rc_row = row_of(rc["unit_id"])
        assert rc_row["status"] == "pending", "注入后行不应被标 failed"
        rec = json.load(open(cp._record_path(rc["unit_id"]), encoding="utf-8"))
        assert cp._sha16(cp.brain_path()) == rec["result_brain_sha16"], \
            "死亡窗口正式脑 ≠ 记录结果脑（恢复无依据）"
        rec = cp.recover_pending()
        assert rc["unit_id"] in rec["committed"], f"恢复未补登：{rec}"
        rcc = row_of(rc["unit_id"])
        assert rcc["status"] == "committed" and \
            rcc["result_brain_version"] == 3, f"恢复后状态/版本异常：{rcc}"
        ok("反例③脑存索引败：提升后进程死亡→恢复扫描按 record 补登 committed（不重学）")

        # ── 反例④索引先写脑败不可能（顺序结构断言）───────────────────
        # 终态可验三条：①版本链连续（committed 行 result=base+1，base=0,1,2…）
        # ②每 committed 行都记录结果脑（无空 sha，防止"索引先写脑败"悬空）
        # ③最新 committed 行结果脑＝当前正式脑（提升恒先于索引提交）
        comm = sorted([r for r in index_rows()
                       if r["status"] == "committed" and not r.get("duplicate_of")],
                      key=lambda r: r["brain_base_version"])
        assert [r["result_brain_version"] for r in comm] == \
            [r["brain_base_version"] + 1 for r in comm], "版本链断裂"
        assert [r["brain_base_version"] for r in comm] == \
            list(range(len(comm))), \
            f"base 版本不连续：{[r['brain_base_version'] for r in comm]}"
        assert all(r.get("result_brain_sha16") for r in comm), "committed 行缺结果脑"
        assert cp._sha16(cp.brain_path()) == comm[-1]["result_brain_sha16"], \
            "最新 committed 结果脑与正式脑不符（提升未先于索引）"
        ok("反例④索引先写脑败不可能：版本链连续＋结果脑齐备＋末行脑体一致")

        # ── 反例⑤同内容换路径（source_hash 幂等）──────────────────────
        pA2 = os.path.join(tmp, "copy_of_sA.npz")
        shutil.copy2(pA, pA2)
        r5 = cp.enqueue(pA2, session_type="training", participant="P001",
                        scene="test")
        assert r5["status"] == "duplicate", f"换路径未幂等（反例⑤复现）：{r5}"
        # 换 session_key 亦幂等（去重按 source_hash，不按身份）
        r5b = cp.enqueue(pA, session_key="ANOTHER-KEY",
                         session_type="training", participant="P001",
                         scene="test")
        assert r5b["status"] == "duplicate", f"换 key 未幂等：{r5b}"
        assert by_status().get("committed", 0) == 3, "换路径后不应新增行"
        ok("反例⑤同内容换路径：source_hash 幂等命中 duplicate，零新增零重学")

        # ── 反例⑥处理版本变化（algo_version 入键＝新单元）─────────────
        cp.ALGO_VERSION = "congci-feed-2.0.0-test"     # 桥件常量在测试中注入变更
        r6 = cp.enqueue(pA, session_type="training", participant="P001",
                        scene="test")
        assert r6["queued"] and r6["status"] == "queued", \
            f"算法版本变化应视为新单元（反例⑥复现）：{r6}"
        res = cp.drain()
        assert len(res) == 1 and res[0]["status"] == "committed"
        rows6 = [r for r in index_rows()
                 if r.get("source_hash16") == cp.sha256_file(pA)[:16]
                 and r.get("status") == "committed"]
        algos = {r["algo_version"] for r in rows6}
        assert len(algos) == 2, f"同内容两算法版本应各留一行：{algos}"
        cp.ALGO_VERSION = None
        ok("反例⑥处理版本变化：algo_version 入键，同内容异版本＝新单元")

        # ── 恢复注入·候选损坏/候选缺失 → failed 不重学 ────────────────
        # 注：崩溃行必是「已开工」行（picked_at 非空）——恢复扫描只认已开工行
        # （2026-10-06 自验缺陷修复，见下方未开工行回归用例）
        bad = {"schema_version": cp.INDEX_SCHEMA, "unit_id": "u-corrupt",
               "session_key": "u-corrupt", "source_hash16": "0" * 16,
               "algo_version": cp._algo_version(), "lineage_id": cp.LINEAGE_ID,
               "brain_base_version": 0, "brain_base_sha16": "",
               "status": "pending", "npz_path": pB,
               "picked_at": "2026-10-06T00:00:01+08:00",
               "queued_at": "2026-10-06T00:00:00+08:00"}
        with tx.locked(purpose="test-fabricate", lock_path=cp.index_lock_path()):
            doc = cp._read_index()
            doc["rows"].append(bad)
            cp._write_index(doc)
        udir = cp.unit_dir("u-corrupt")
        os.makedirs(udir, exist_ok=True)
        with open(os.path.join(udir, "brain.candidate.npz"), "wb") as f:
            f.write(b"not-a-brain")
        with open(cp._record_path("u-corrupt"), "w", encoding="utf-8") as f:
            json.dump({"schema_version": "1.0", "unit_id": "u-corrupt",
                       "result_brain_sha16": "0" * 16}, f)
        rec = cp.recover_pending()
        assert "u-corrupt" in rec["failed"], f"损坏候选应转 failed：{rec}"
        assert row_of("u-corrupt")["status"] == "failed", "损坏候选未标 failed"
        ok("恢复注入·候选损坏：pending＋损坏候选→failed 带原因，不重学不提升")

        # ── 自验缺陷修复回归（2026-10-06 端到端自验实捉）──────────────
        # 生产模式（auto_worker=True）下 worker 启动即先跑恢复扫描：新入队的
        # 在队行尚未开工（picked_at 空、天然无 record），旧实现当「事务②前
        # 中断」直接标 failed → 每次入队都失败、C1 主路径不可用。修复＝恢复
        # 扫描只处理已开工行；本用例锁死该语义。
        fresh = {"schema_version": cp.INDEX_SCHEMA, "unit_id": "u-fresh",
                 "session_key": "u-fresh", "source_hash16": "2" * 16,
                 "algo_version": cp._algo_version(),
                 "lineage_id": cp.LINEAGE_ID,
                 "brain_base_version": 0, "brain_base_sha16": "",
                 "status": "pending", "npz_path": pB,
                 "queued_at": "2026-10-06T00:00:02+08:00"}   # picked_at 缺省＝未开工
        with tx.locked(purpose="test-fresh", lock_path=cp.index_lock_path()):
            doc = cp._read_index()
            doc["rows"].append(fresh)
            cp._write_index(doc)
        rec2 = cp.recover_pending()
        assert "u-fresh" not in rec2["failed"], \
            f"未开工在队行被误判 failed（生产缺陷复现！）：{rec2}"
        assert row_of("u-fresh")["status"] == "pending", "未开工行应保持 pending 待消化"
        with tx.locked(purpose="test-fresh-clean", lock_path=cp.index_lock_path()):
            doc = cp._read_index()
            doc["rows"] = [r for r in doc["rows"] if r["unit_id"] != "u-fresh"]
            cp._write_index(doc)
        ok("自验缺陷修复回归：未开工在队行不被恢复扫描判死（保持 pending）")

        # ── failed→可重试（attempt 计数）＋失败不动正式脑 ──────────────
        brain_before = cp.sha256_file(cp.brain_path())
        pG = os.path.join(tmp, "sG.npz")
        make_npz(pG, seed=7)
        rg = cp.enqueue(pG, session_type="training", participant="P001",
                        scene="test")
        fin = cp._process_row(rg["row"], inject_fail="candidate_save")
        assert fin["status"] == "failed", f"注入候选写失败应标 failed：{fin}"
        assert cp.sha256_file(cp.brain_path()) == brain_before, \
            "失败后正式脑字节被改（持久脑 diff=0 纪律破）"
        r7 = cp.enqueue(pG, session_type="training", participant="P001",
                        scene="test")
        assert r7["queued"] and r7["unit_id"].endswith("--a2"), \
            f"failed 后重试应开新 attempt：{r7}"
        res = cp.drain()
        assert len(res) == 1 and res[0]["status"] == "committed", f"重试未成功：{res}"
        ok("failed→可重试：attempt 计数 +1 新单元收口；失败不动正式脑（字节不变）")

        # ── 弃权 abstained（无效输入）与 duplicate 严格分列 ────────────
        pH = os.path.join(tmp, "sH.npz")
        make_npz(pH, seed=8)
        touch_events(pH)
        rh = cp.enqueue(pH, session_type="training", participant="P001",
                        scene="test")
        with open(pH, "wb") as f:
            f.write(b"garbage-not-an-npz")            # 入队后源件损坏＝无效输入
        res = cp.drain()
        assert len(res) == 1 and res[0]["status"] == "abstained", \
            f"无效输入应弃权：{res}"
        rh_row = row_of(rh["unit_id"])
        assert "不可解析" in (rh_row["reason"] or ""), f"弃权原因未记：{rh_row}"
        # duplicate 与 abstained 不得混淆：恢复原内容（确定性同字节）重入→duplicate
        make_npz(pH, seed=8)                      # 同一 seed＝同字节→同 source_hash
        r8 = cp.enqueue(pH, session_type="training", participant="P001",
                        scene="test")
        assert r8["status"] == "duplicate", f"abstained 后重入应 duplicate：{r8}"
        assert by_status()["abstained"] == 1, "abstained 行数异常"
        assert "duplicate" not in by_status(), \
            "duplicate 不应在索引新增行（系返回判定，非持久状态）"
        ok("弃权 abstained：无效输入整坐弃权带原因；与 duplicate 严格分列")

        # ── 准入拒绝三路合成断言 ───────────────────────────────────────
        pT = os.path.join(tmp, "sT.npz")
        make_npz(pT, seed=9)
        assert not cp.admit(pT, session_type="test")["admitted"], "test 类型未拒"
        assert not cp.admit(pT, session_type="smoke")["admitted"], "smoke 类型未拒"
        assert not cp.admit(pT, session_type="replay")["admitted"], "replay 类型未拒"
        assert not cp.admit(pT, qc={"recommend": "quarantine",
                                    "quarantined": True})["admitted"], "QC 未拒"
        gov = os.path.join(zen, "00_governance")
        os.makedirs(gov, exist_ok=True)
        with open(os.path.join(gov, "participant_status.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"P001": "withdrawn"}, f)
        assert not cp.admit(pT, session_type="training",
                            participant="P001")["admitted"], "撤回者未拒"
        with open(os.path.join(gov, "participant_status.json"), "w",
                  encoding="utf-8") as f:
            json.dump({}, f)
        assert cp.admit(pT, session_type="training",
                        participant="P001")["admitted"], "非撤回者误拒"
        assert not cp.enqueue(pT, session_type="test")["queued"], "入队未拦拒绝面"
        ok("准入拒绝三路：类型（test/smoke/replay）／QC／撤回者——合成断言全过")

        # ── 四态事件入会话事件流（queued/committed/duplicate/abstained）──
        evs = [e for e in read_events(pA)
               if e.get("kind") == "congci_brain"]
        statuses = {e["payload"].get("status") for e in evs}
        assert {"queued", "committed", "duplicate"} <= statuses, \
            f"sA 事件流缺态：{statuses}"
        evh = [e for e in read_events(pH)
               if e.get("kind") == "congci_brain"]
        st_h = {e["payload"].get("status") for e in evh}
        assert {"queued", "abstained", "duplicate"} <= st_h, \
            f"sH 事件流缺态：{st_h}"
        ok("四态事件：congci_brain 单 kind＋status 逐态入会话事件流")

        # ── 收尾：终态一致性断言 ───────────────────────────────────────
        by = by_status()
        assert by.get("pending", 0) == 0, f"残留 pending：{by}"
        assert len([r for r in index_rows() if r["status"] == "committed"
                    and not r.get("duplicate_of")]) == \
            int(json.load(open(os.path.join(root, "processed_index.json"),
                               encoding="utf-8"))["rows"]
                and cp._base_lineage(cp._read_index())[0]), "版本账不符"
        print(f"[selftest OK] {PASS} checks passed（批 C1 轻量自测：六反例＋恢复注入＋准入＋事件）")
        return 0
    finally:
        cp.configure(auto_worker=True)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
