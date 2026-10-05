#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
20261005_W1_registry_tx_test.py — 批 C0 轻量自测：登记表事务原语五反例转守卫
=============================================================================

法师金口 2026-10-05「七项通过，继续施工」批 C0；两层闸门 adopted（轻量每批）。
对应 W3 合成五反例（engine/20261005-W3-AI014-共享登记合成交错验证回执.md）：
  丢更新／状态回退（finished→planned）／编号复用（双 S02）／截空（writeheader
  失败）／旧快照恢复——本件以 registry_tx 候选事务实现复现同型场景，期望由
  「反例可复现」转为「冲突被拒／串行保留全部增量／失败保留旧有效文件」。
另加：陈旧锁接管／活锁超时／真实双进程并发（跨进程互斥实证）。

纪律：全程 TemporaryDirectory 合成件，**不触真实登记表**；退出码 0=全过。
"""

import csv
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, r"D:\Project\zhiguanAI")
import registry_tx as tx

PASS = 0


def ok(name):
    global PASS
    PASS += 1
    print(f"[ok] {name}")


def seed(tmp, rows):
    p = os.path.join(tmp, "session_registry.csv")
    with open(p, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=tx.FIELDNAMES)
        w.writeheader()
        w.writerows(rows)
    return p


def row(sid, st="planned", dur="", date="2026-10-05", pid="P001"):
    return dict(session_id=sid, participant_id=pid, date=date,
                session_type="training", duration_seconds=dur, status=st,
                manifest_path="")


def main() -> int:
    # DSH 托管 %TEMP% 对子进程不可写（坑档既有教训：临时件落仓库内）
    tmp = str(Path(r"D:\Project\zhiguanAI\_analysis_tmp")
              / f"registry_tx_test_{os.getpid()}")
    os.makedirs(tmp, exist_ok=True)
    try:
        # ── 反例①丢更新→守卫：旧快照不回抹，锁内重读合并 ──
        csvp = seed(tmp, [row("ZEN-20261005-P001-S01")])
        _stale = tx.read_rows(csvp)                     # 模拟数分钟前旧快照
        tx.ingest_append_locked(row("ZEN-20261005-P001-S02", st="finished",
                                    dur="300"), csvp)   # 他人插入新行
        tx.ingest_backfill_locked("ZEN-20261005-P001-S01", 300, "finished",
                                  "02_raw/ZEN-20261005-P001-S01/session_manifest.json",
                                  csvp)                 # 持旧快照的写方走临界区
        rows = tx.read_rows(csvp)
        sids = [r["session_id"] for r in rows]
        assert len(rows) == 2, f"行数异常：{sids}"
        assert "ZEN-20261005-P001-S02" in sids, "他人新行被旧快照回抹（反例①复现！）"
        assert rows[0]["status"] == "finished", "回填未生效"
        ok("反例①丢更新：旧快照不回抹，他人新行保留＋回填生效")

        # ── 反例②状态回退→守卫：finished 不可退回 planned ──
        try:
            tx.ingest_backfill_locked("ZEN-20261005-P001-S01", 999, "finished",
                                      "", csvp)
            raise AssertionError("非 planned 回填未被拒（反例②复现！）")
        except ValueError as ex:
            assert "planned" in str(ex)
        # 反例②续：永不复用守卫（append 路径）——同 sid 二次插入必拒
        try:
            tx.ingest_append_locked(row("ZEN-20261005-P001-S01"), csvp)
            raise AssertionError("重复 Zen-ID 未被拒（反例②复现！）")
        except ValueError as ex:
            assert "永不复用" in str(ex)
        assert tx.read_rows(csvp)[0]["status"] == "finished", "状态被回退（反例②复现！）"
        ok("反例②状态回退：finished 拒绝降级，Zen-ID 拒绝复写")

        # ── 反例③编号复用→守卫：两线程并发预登记（旧实现=同算 S02 互抹）──
        import threading
        results = {}

        def _preg(k):
            results[k] = tx.preregister_locked("P001", "training",
                                               "2026-10-05", csvp)
        ths = [threading.Thread(target=_preg, args=(k,)) for k in ("a", "b")]
        [t.start() for t in ths]
        [t.join(15) for t in ths]
        sa, sb = results["a"], results["b"]
        assert sa != sb, f"并发预登记产生同号：{sa}（反例③复现！）"
        sids = [r["session_id"] for r in tx.read_rows(csvp)]
        assert sids.count(sa) == 1 and sids.count(sb) == 1, \
            "并发预登记产生重复/丢失行（反例③复现！）"
        ok("反例③编号复用：并发预登记串行化，两号不同、各落一行")

        # ── 反例④截空→守卫：写失败原文件完整 ──
        n_before = len(tx.read_rows(csvp))
        real_replace = os.replace
        try:
            os.replace = lambda *a, **k: (_ for _ in ()).throw(OSError("注入失败"))
            try:
                tx.write_rows_atomic(tx.read_rows(csvp), csvp)
                raise AssertionError("注入失败未被抛出")
            except OSError:
                pass
            assert len(tx.read_rows(csvp)) == n_before, "原文件被破坏（反例④复现！）"
        finally:
            os.replace = real_replace
        # 读回校验路径：行数不符不替换（先取行、后 patch——patch 只裹写调用）
        rows_now = tx.read_rows(csvp)
        real_dr = tx.csv.DictReader
        try:
            tx.csv.DictReader = lambda *a, **k: iter([{}])  # 写内读回恒 1 行
            try:
                tx.write_rows_atomic(rows_now, csvp)
                raise AssertionError("校验失败未被抛出")
            except IOError:
                pass
        finally:
            tx.csv.DictReader = real_dr
        assert len(tx.read_rows(csvp)) == n_before, "校验失败仍替换（反例④复现！）"
        assert not [f for f in os.listdir(tmp) if f.endswith(".tmp-tx")], "临时件残留"
        ok("反例④截空：注入失败原文件完整，临时件清理")

        # ── 反例⑤锁件：死 pid 接管／活锁超时 ──
        lp = tx.lock_path_for(csvp)
        with open(lp, "w", encoding="utf-8") as f:
            f.write("holder_pid=999999999\ntime=2026-10-05T00:00:00\npurpose=ghost\n")
        t0 = __import__("time").monotonic()
        with tx.locked(purpose="takeover-test", lock_path=lp):
            took = __import__("time").monotonic() - t0
        assert took < 2.0, f"死 pid 接管过慢：{took:.2f}s"
        ok("反例⑤锁件：死 pid 陈旧锁即时接管")
        import threading
        held = threading.Event()
        release = threading.Event()

        def hold():
            with tx.locked(purpose="holder", lock_path=lp):
                held.set()
                release.wait(20)
        th = threading.Thread(target=hold)
        th.start()
        held.wait(5)
        try:
            tx.ingest_append_locked(row("ZEN-20261005-P001-S99"), csvp)
            raise AssertionError("活锁未超时")
        except TimeoutError:
            pass
        finally:
            release.set()
            th.join(5)
        tx.ingest_append_locked(row("ZEN-20261005-P001-S99"), csvp)  # 释放后可获锁
        ok("锁件：活锁按超时拒绝（TimeoutError），释放后恢复")

        # ── 批 C0 锁族安全修订（2026-10-06·W3 反例消费）──
        # ① 三态存活：自身=alive／不存在 pid=dead／空 pid=unknown
        assert tx._pid_status(os.getpid()) == "alive", "自身 pid 应 alive"
        assert tx._pid_status(999999999) == "dead", "不存在 pid 应 dead"
        assert tx._pid_status(0) == "unknown", "空 pid 应 unknown"
        # ② 活持有者锁不可夺（即便 mtime 极旧）：本进程 pid＋1 小时前时间戳
        #    → 短超时锁定被拒（DEAD-only 接管，W3 反例①）
        lp2 = lp + ".alive-old"
        with open(lp2, "w", encoding="utf-8") as f:
            f.write(f"holder_pid={os.getpid()}\nowner_token=ghost\npurpose=old\n")
        old = __import__("time").time() - 3600
        os.utime(lp2, (old, old))
        t0 = __import__("time").monotonic()
        try:
            with tx.locked(purpose="no-steal-alive", lock_path=lp2, timeout=0.6):
                raise AssertionError("活持有者锁被夺（W3 反例①复现！）")
        except TimeoutError:
            pass
        assert __import__("time").monotonic() - t0 < 5, "活锁判定异常慢"
        ok("锁族安全①：活持有者锁不可夺（mtime 旧亦然，DEAD-only 接管）")
        # ③ owner token 释放比对：H1 释放不得删 H2 的新锁（W3 反例②）
        lp3 = lp + ".token"
        held3, rel3 = threading.Event(), threading.Event()

        def hold3():
            with tx.locked(purpose="h1", lock_path=lp3):
                held3.set()
                rel3.wait(10)
        th3 = threading.Thread(target=hold3)
        th3.start()
        held3.wait(5)
        with open(lp3, encoding="utf-8", errors="ignore") as f:
            assert "owner_token=" in f.read(), "锁件缺 owner_token"
        with open(lp3, "w", encoding="utf-8") as f:   # 模拟 H2 接管（不同 token）
            f.write("holder_pid=999999999\nowner_token=H2-token\npurpose=h2\n")
        rel3.set()
        th3.join(5)
        assert os.path.exists(lp3), "H1 释放误删了 H2 的新锁（W3 反例②复现！）"
        os.remove(lp3)
        ok("锁族安全②：owner token 比对，H1 释放不删 H2 新锁")

        # ── 真实双进程并发（跨进程互斥实证）：2×30 append，零丢失零重复 ──
        worker = (
            "import sys; sys.path.insert(0, r'D:\\Project\\zhiguanAI');"
            "import registry_tx as tx;"
            "k=sys.argv[1]; csvp=sys.argv[2];"
            "[tx.ingest_append_locked(dict(session_id=f'W{k}-S{i:02d}',"
            " participant_id='P999', date='2026-10-05', session_type='training',"
            " duration_seconds='', status='planned', manifest_path=''), csvp)"
            " for i in range(30)]"
        )
        procs = [subprocess.Popen(
            [sys.executable, "-c", worker, str(k), csvp],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            for k in ("A", "B")]
        for p in procs:
            _, err = p.communicate(timeout=120)
            assert p.returncode == 0, f"并发 worker 失败：{err.decode('utf-8', 'ignore')[:200]}"
        rows = tx.read_rows(csvp)
        sids = [r["session_id"] for r in rows]
        w_rows = [s for s in sids if s.startswith("W")]
        assert len(w_rows) == 60 and len(w_rows) == len(set(w_rows)), \
            f"并发丢失/重复：W 行 {len(w_rows)}/60"
        ok("真实双进程并发：2×30 append 全部落表，零丢失零重复")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"[selftest OK] {PASS} checks passed（批 C0 轻量自测）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
