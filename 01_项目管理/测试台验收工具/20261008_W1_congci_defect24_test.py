#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
20261008_W1_congci_defect24_test.py — 缺陷②（修法甲）＋缺陷④（base 谱系移进
临界区）正修的纯合成回归，供 W3 独立复现验收
==============================================================================

法师 2026-10-08 22:22 在 W1 窗亲裁「对提请 2、3 的『准修』」⇒ 解除禁改。
本件只验两处正修，**不含缺陷①（makedirs，未被裁定提及，仍不准修）**，
**不含修法丙（本窗当轮自撤，见下 §D）**。

四组断言：
  A 缺陷④ 批量入队：base 谱系严格 0,1,2…N-1 且 sha 逐环相扣（before/after 对照）
  B 缺陷② 甲：CLI 无 --auto-worker ⇒ auto_worker 落 False 且不起线程；
              显式给旗标 ⇒ 保持 True 且起线程（因果链，非碰运气）
  C 端到端：真跑 CLI 子进程 --enqueue，事后根目录零残留 *.lock
  D 残留（如实报，不修）：0 字节孤儿锁仍不可接管 ⇒ 非 CLI 泄漏源未闭环；
              并核 registry_tx.py 与 HEAD 逐字节一致（丙 未夹带的字节级证明）

纪律：全程合成 npz（白噪声）、configure(tmp_root) 全隔离、**不触真实脑目录／
登记表／03_qc／02_raw，不喂任何真实数据**；auto_worker=False 由 drain() 同步消化。
before 侧用 `git show HEAD:congci_pipeline.py` 落到 _analysis_tmp 后按模块加载，
**不改工作区任何文件**。退出码 0＝全过。

跑法：
  "C:/Users/tiand/AppData/Local/Programs/Python/Python312/python.exe" \
      "01_项目管理/测试台验收工具/20261008_W1_congci_defect24_test.py"
"""

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = r"D:\Project\zhiguanAI"
SCRATCH = os.path.join(ROOT, "_analysis_tmp", "defect24")
PY = sys.executable
N_BATCH = 4                      # 批量入队坐数（缺陷④ 的触发条件＝>1）

sys.path.insert(0, ROOT)
import congci_pipeline as cp          # noqa: E402  after sys.path 设置
import registry_tx as tx              # noqa: E402

PASS = []
FAIL = []


def ok(name):
    PASS.append(name)
    print(f"[ok] {name}")


def bad(name, why):
    FAIL.append(f"{name}: {why}")
    print(f"[FAIL] {name} — {why}")


def check(cond, name, why=""):
    if cond:
        ok(name)
    else:
        bad(name, why)


def sha16(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def make_npz(path, epochs=60, seed=1, sfreq=256, channels=4):
    """30s→60s 白噪声合成会话，meta 与真机同形（QC 判 ingest、feed 有有效 epoch）。
    与 20261006_W1_congci_pipeline_test.py::make_npz 同构，仅 epochs 调小提速。"""
    np = __import__("numpy")
    rng = np.random.default_rng(seed)
    n = epochs * sfreq
    eeg = rng.standard_normal((n, channels))
    t = np.arange(n) / sfreq
    eeg[:, 1] += 0.6 * np.sin(2 * np.pi * 6.0 * t)
    meta = {"timestamp": "2026-10-08T00:00:00+08:00", "sfreq": sfreq,
            "channels": ["TP9", "AF7", "AF8", "TP10"],
            "samples": n, "duration": float(n / sfreq),
            "scene": "test-synthetic"}
    np.savez(path, eeg=eeg, timestamps=t, meta=meta)
    return path


def touch_events(mod, npz_path):
    ep = mod._session_events_path(npz_path)
    os.makedirs(os.path.dirname(ep), exist_ok=True)
    if not os.path.exists(ep):
        with open(ep, "w", encoding="utf-8") as f:
            f.write(json.dumps({"schema_version": "1.0",
                                "ts": "2026-10-08T00:00:00+08:00",
                                "type": "created", "actor": "system",
                                "kind": "ruled", "payload": {},
                                "note": "synthetic"}) + "\n")
    return ep


def fresh_root(tag):
    """隔离根。⚠ 必须手工 mkdir：缺陷①（enqueue 不建根目录）未获准修，
    virgin 树首跑必崩——本件照现行口径绕开，不代修。"""
    root = os.path.join(SCRATCH, f"root_{tag}")
    zen = os.path.join(SCRATCH, f"zen_{tag}")
    shutil.rmtree(root, ignore_errors=True)
    shutil.rmtree(zen, ignore_errors=True)
    os.makedirs(root, exist_ok=True)
    os.makedirs(zen, exist_ok=True)
    return root, zen


def run_batch(mod, tag):
    """一次性批量入队 N 坐（不逐坐 drain）——缺陷④ 的确切触发用法。
    返回 (入队后行快照, 消化后行快照, 脑 sha16, drain 实测秒)。"""
    root, zen = fresh_root(tag)
    mod.configure(root=root, zen_root=zen, auto_worker=False,
                  brain_lock_timeout=5.0)
    npz_dir = os.path.join(SCRATCH, f"npz_{tag}")
    shutil.rmtree(npz_dir, ignore_errors=True)
    os.makedirs(npz_dir, exist_ok=True)

    units = []
    for i in range(N_BATCH):
        p = os.path.join(npz_dir, f"s{i}.npz")
        make_npz(p, seed=100 + i)
        touch_events(mod, p)
        r = mod.enqueue(p, session_type="training", participant="P001",
                        scene="test")
        assert r.get("queued"), f"{tag} 第{i}坐未入队：{r}"
        units.append(r["unit_id"])

    def snapshot():
        by = {r["unit_id"]: r for r in mod._read_index()["rows"]}
        return [by[u] for u in units]

    at_enqueue = snapshot()
    t0 = time.monotonic()
    mod.drain()
    elapsed = time.monotonic() - t0
    brain = sha16(mod.brain_path()) if os.path.exists(mod.brain_path()) else ""
    return at_enqueue, snapshot(), brain, elapsed


def load_head_module():
    """把 HEAD 版 congci_pipeline 落成独立模块（before 侧对照），不改工作区。"""
    out = subprocess.run(["git", "show", "HEAD:congci_pipeline.py"],
                         cwd=ROOT, capture_output=True)
    assert out.returncode == 0, f"git show 失败：{out.stderr[:200]!r}"
    os.makedirs(SCRATCH, exist_ok=True)
    head_path = os.path.join(SCRATCH, "congci_pipeline_HEAD.py")
    with open(head_path, "wb") as f:
        f.write(out.stdout)
    spec = importlib.util.spec_from_file_location("congci_head", head_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # HEAD 副本的 SCRIPT_DIR＝scratch，静态取 ALGO_VERSION 会读不到桥件而落
    # "unknown"；对齐成与工作区同值，使两侧幂等键第三元一致（否则不可比）。
    mod.ALGO_VERSION = cp._algo_version()
    return mod, head_path, hashlib.sha256(out.stdout).hexdigest()


# ── A 缺陷④：批量入队 base 谱系 ─────────────────────────────────────────

def test_A():
    print("\n=== A 缺陷④ 批量入队 base 谱系（before/after 对照）===")
    head, head_path, head_sha = load_head_module()
    print(f"[header] HEAD congci_pipeline.py sha256={head_sha[:16]} "
          f"｜工作区 sha16={sha16(os.path.join(ROOT, 'congci_pipeline.py'))}")

    # ── before（HEAD）：复现缺陷 ──
    b_enq, b_fin, b_brain, _ = run_batch(head, "head")
    b_bases = [r["brain_base_version"] for r in b_fin]
    b_bsha = [r["brain_base_sha16"] for r in b_fin]
    print(f"[before] 入队时 base_version={[r['brain_base_version'] for r in b_enq]}")
    print(f"[before] 消化后 base_version={b_bases}")
    print(f"[before] 消化后 base_sha16 ={b_bsha}")
    print(f"[before] result_version={[r['result_brain_version'] for r in b_fin]}")
    check(len(set(b_bases)) == 1 and b_bases[0] == 0,
          "A1 before 侧确证缺陷④复现（N 行 base 全同为 0）",
          f"未复现，before 侧不成立：{b_bases}")
    check(len(set(b_bsha)) == 1,
          "A2 before 侧确证 sha 审计链断裂（N 行 base_sha16 全同）",
          f"未复现：{b_bsha}")
    check(len({r["result_brain_version"] for r in b_fin}) == 1,
          "A3 before 侧确证版本号碰撞（result 全同）",
          f"未复现：{[r['result_brain_version'] for r in b_fin]}")

    # ── after（工作区）：正修生效 ──
    a_enq, a_fin, a_brain, elapsed = run_batch(cp, "fixed")
    print(f"[after ] 入队时 base_version={[r['brain_base_version'] for r in a_enq]}"
          f"（应全 None＝「未定，待处理时定」）")
    print(f"[after ] 消化后 base_version={[r['brain_base_version'] for r in a_fin]}")
    print(f"[after ] 消化后 base_sha16 ={[r['brain_base_sha16'] for r in a_fin]}")
    print(f"[after ] result_version={[r['result_brain_version'] for r in a_fin]}")
    print(f"[after ] {N_BATCH} 坐 drain 实测 {elapsed:.1f}s（暖缓存·合成件）")

    check(all(r["brain_base_version"] is None for r in a_enq),
          "A4 after 入队时两字段留 None（未定）",
          f"入队即落值：{[r['brain_base_version'] for r in a_enq]}")
    check(all(r["brain_base_sha16"] is None for r in a_enq),
          "A5 after 入队时 base_sha16 留 None",
          f"{[r['brain_base_sha16'] for r in a_enq]}")

    comm = sorted([r for r in a_fin if r["status"] == "committed"],
                  key=lambda r: r["brain_base_version"])
    check(len(comm) == N_BATCH, "A6 after 全部 committed",
          f"committed {len(comm)}/{N_BATCH}：{[r['status'] for r in a_fin]}")
    check([r["brain_base_version"] for r in comm] == list(range(N_BATCH)),
          "A7 base 版本严格 0,1,2…N-1（原碰撞已消）",
          f"{[r['brain_base_version'] for r in comm]}")
    check([r["result_brain_version"] for r in comm] == list(range(1, N_BATCH + 1)),
          "A8 result 版本严格 1,2,3…N（逐环 +1）",
          f"{[r['result_brain_version'] for r in comm]}")
    check(all(r["result_brain_version"] == r["brain_base_version"] + 1
              for r in comm), "A9 每行 result == base+1",
          f"{[(r['brain_base_version'], r['result_brain_version']) for r in comm]}")

    # sha 链：首行无基脑（""），此后每行 base_sha16 == 前一行 result_sha16
    chain_ok = comm[0]["brain_base_sha16"] == "" and all(
        comm[i]["brain_base_sha16"] == comm[i - 1]["result_brain_sha16"]
        for i in range(1, len(comm)))
    check(chain_ok, "A10 sha 审计链逐环相扣（base[i]==result[i-1]，首环空）",
          f"{[(r['brain_base_sha16'], r['result_brain_sha16']) for r in comm]}")
    check(len({r["brain_base_sha16"] for r in comm}) == N_BATCH,
          "A11 N 行 base_sha16 互异（原「N 坐同出一个基脑」假象已消）",
          f"{[r['brain_base_sha16'] for r in comm]}")
    check(a_brain and a_brain == comm[-1]["result_brain_sha16"],
          "A12 末行 result == 当前正式脑（提升恒先于索引提交）",
          f"brain={a_brain} last={comm[-1]['result_brain_sha16']}")
    check(cp._base_lineage(cp._read_index())[0] == N_BATCH,
          "A13 _base_lineage 版本账 == committed 数",
          f"{cp._base_lineage(cp._read_index())}")

    # 单坐一喂路径不得回退（长期口径仍须成立）
    one_root, one_zen = fresh_root("onebyone")
    cp.configure(root=one_root, zen_root=one_zen, auto_worker=False,
                 brain_lock_timeout=5.0)
    npz1 = os.path.join(SCRATCH, "npz_one")
    shutil.rmtree(npz1, ignore_errors=True)
    os.makedirs(npz1, exist_ok=True)
    ids = []
    for i in range(3):
        p = os.path.join(npz1, f"o{i}.npz")
        make_npz(p, seed=200 + i)
        touch_events(cp, p)
        r = cp.enqueue(p, session_type="training", participant="P001",
                       scene="test")
        cp.drain()
        ids.append(r["unit_id"])
    rows = {r["unit_id"]: r for r in cp._read_index()["rows"]}
    seq = [rows[u] for u in ids]
    check([r["brain_base_version"] for r in seq] == [0, 1, 2],
          "A14 一坐一喂路径 base 仍 0,1,2（长期口径未回退）",
          f"{[r['brain_base_version'] for r in seq]}")
    return head_path


# ── B 缺陷② 甲：CLI 因果链 ──────────────────────────────────────────────

_SHIM = r'''
import json, os, sys, types, threading
sys.path.insert(0, r"D:\Project\zhiguanAI")
import congci_pipeline as cp
STARTED = []
class FakeThread:
    def __init__(self, target=None, daemon=None, name=None):
        self.name, self.daemon = name, daemon
    def start(self):
        STARTED.append(self.name)
    def is_alive(self):
        return False
shim = types.ModuleType("threading")
shim.Thread, shim.Lock = FakeThread, threading.Lock
cp.threading = shim
cp._WORKER = None
# argv 约定：[本 shim] <CLI 旗标…> <隔离根>——根恒在末位，旗标全在其前。
# （初版误写 sys.argv[2]／[1:2]，把 --auto-worker 当成根路径，既吞了旗标又在
#   仓库根建出一个名为 "--auto-worker" 的空目录；已改末位取根并删除该空目录。）
root = sys.argv[-1]
cli_args = sys.argv[1:-1]
os.makedirs(root, exist_ok=True)
cp.configure(root=root, zen_root=root, auto_worker=True)   # 生产默认＝True
before = cp._CFG["auto_worker"]
sys.argv = ["congci_pipeline.py"] + cli_args
rc = cp.main()
cp.ensure_worker()          # 甲 生效则此处必空转
print("RESULT" + json.dumps({
    "argv": cli_args, "auto_worker_before_main": before,
    "auto_worker_after_main": cp._CFG["auto_worker"],
    "threads_started": list(STARTED), "worker_obj": cp._WORKER is not None,
    "rc": rc}))
'''


def test_B():
    print("\n=== B 缺陷② 修法甲：CLI 默认不留常驻 worker（因果链）===")
    shim_path = os.path.join(SCRATCH, "_shim_cli.py")
    os.makedirs(SCRATCH, exist_ok=True)
    with open(shim_path, "w", encoding="utf-8") as f:
        f.write(_SHIM)

    for extra, want_false in (([], True), (["--auto-worker"], False)):
        argv = ["--status"] + extra
        out = subprocess.run([PY, shim_path] + argv +
                             [os.path.join(SCRATCH, "root_cli" +
                                           ("_aw" if extra else ""))],
                             capture_output=True, text=True, encoding="utf-8",
                             errors="replace", cwd=ROOT)
        line = [l for l in (out.stdout or "").splitlines() if l.startswith("RESULT")]
        tag = "无旗标" if want_false else "有 --auto-worker"
        if not line:
            bad(f"B[{tag}]", f"无 RESULT 输出：{out.stderr[:400]}")
            continue
        d = json.loads(line[0][len("RESULT"):])
        print(f"[{tag}] {json.dumps(d, ensure_ascii=False)}")
        check(d["auto_worker_before_main"] is True,
              f"B1[{tag}] 进 main 前 auto_worker＝True（生产默认未被改动）",
              f"{d['auto_worker_before_main']}")
        check((d["auto_worker_after_main"] is False) == want_false,
              f"B2[{tag}] main 后 auto_worker ＝ {not want_false}",
              f"{d['auto_worker_after_main']}")
        check(bool(d["threads_started"]) != want_false,
              f"B3[{tag}] ensure_worker 起线程与否 ＝ {not want_false}",
              f"{d['threads_started']}")

    # B4 生产 in-process 路径未受甲影响：auto_worker=True 时 ensure_worker 仍起
    #    worker（8777 宿主靠这条懒启动消化，甲 只治 CLI，不得外溢）
    import threading as _th
    import types as _ty
    started = []

    class _Spy:
        def __init__(self, target=None, daemon=None, name=None):
            self.name, self.daemon = name, daemon

        def start(self):
            started.append(self.name)

        def is_alive(self):
            return False

    shim = _ty.ModuleType("threading")
    shim.Thread, shim.Lock = _Spy, _th.Lock
    real_tm, real_w = cp.threading, cp._WORKER
    try:
        cp.threading = shim
        cp._WORKER = None
        cp.configure(auto_worker=True)
        cp.ensure_worker()
        check(started == ["congci-feeder"],
              "B4 生产路径未受甲影响：auto_worker=True 时 ensure_worker 仍起 worker",
              f"{started}")
        cp._WORKER = None
        cp.configure(auto_worker=False)
        cp.ensure_worker()
        check(started == ["congci-feeder"],
              "B5 auto_worker=False 时 ensure_worker 空转（甲 的因果环节）",
              f"{started}")
    finally:
        cp.threading, cp._WORKER = real_tm, real_w


# ── C 端到端：真 CLI 子进程 --enqueue 后零残留锁 ────────────────────────

def test_C():
    print("\n=== C 端到端：真 CLI 子进程 --enqueue，事后根目录零残留 *.lock ===")
    root, zen = fresh_root("cli_e2e")
    npz_dir = os.path.join(SCRATCH, "npz_cli_e2e")
    shutil.rmtree(npz_dir, ignore_errors=True)
    os.makedirs(npz_dir, exist_ok=True)
    p = os.path.join(npz_dir, "e2e.npz")
    make_npz(p, seed=300)
    touch_events(cp, p)

    env = dict(os.environ, CONGCI_PIPELINE_ROOT=root,
               CONGCI_PIPELINE_ZEN_ROOT=zen, PYTHONIOENCODING="utf-8")
    out = subprocess.run([PY, os.path.join(ROOT, "congci_pipeline.py"),
                          "--enqueue", p], cwd=ROOT, capture_output=True,
                         text=True, encoding="utf-8", errors="replace", env=env)
    print(f"[cli] rc={out.returncode}\n{out.stdout.strip()}")
    if out.stderr.strip():
        print(f"[cli stderr] {out.stderr.strip()[:600]}")
    check(out.returncode == 0, "C1 CLI --enqueue 退出码 0", f"rc={out.returncode}")
    check("hint=已入队未消化" in (out.stdout or ""),
          "C2 打印未消化提示（防「入队即已喂」误读）", out.stdout[:300])
    time.sleep(1.0)                     # 给可能的残留线程留退出窗口
    locks = sorted(Path(root).rglob("*.lock"))
    check(not locks, "C3 根目录零残留 *.lock（0 字节孤儿锁未产生）",
          f"{[str(x) for x in locks]}")
    rows = json.loads(Path(root, "processed_index.json").read_text(
        encoding="utf-8"))["rows"]
    check(len(rows) == 1 and rows[0]["status"] == "pending",
          "C4 行已入队且仍 pending（甲 只去 worker，不吞入队）",
          f"{[(r['unit_id'], r['status']) for r in rows]}")
    check(rows and rows[0]["brain_base_version"] is None,
          "C5 端到端亦见 base 未定（④ 在真 CLI 路径生效）",
          f"{rows[0].get('brain_base_version') if rows else None}")
    out2 = subprocess.run([PY, os.path.join(ROOT, "congci_pipeline.py"),
                           "--drain"], cwd=ROOT, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", env=env)
    print(f"[cli --drain] rc={out2.returncode} {out2.stdout.strip()[:300]}")
    check(out2.returncode == 0, "C6 续跑 --drain 退出码 0（文档化同步路径可用）",
          f"rc={out2.returncode} {out2.stderr[:300]}")
    locks2 = sorted(Path(root).rglob("*.lock"))
    check(not locks2, "C7 --drain 后仍零残留 *.lock", f"{[str(x) for x in locks2]}")


# ── D 残留与未夹带证明 ──────────────────────────────────────────────────

def test_D():
    print("\n=== D 残留（如实报，不修）＋ registry_tx.py 未夹带证明 ===")
    # D1 registry_tx.py 与 HEAD 逐字节一致 ⇒ 修法丙 确未施工
    r = subprocess.run(["git", "diff", "--exit-code", "HEAD", "--",
                        "registry_tx.py"], cwd=ROOT, capture_output=True)
    check(r.returncode == 0,
          "D1 registry_tx.py 与 HEAD 零差异（丙未夹带·字节级证明）",
          f"diff 非空 rc={r.returncode}：{r.stdout[:300]!r}")

    # D2 复现「0 字节孤儿锁不可接管」——非 CLI 泄漏源仍未闭环
    root, _ = fresh_root("orphan")
    lp = os.path.join(root, "orphan.json.lock")
    open(lp, "wb").close()                       # 0 字节，无 holder_pid
    assert os.path.getsize(lp) == 0
    tx._try_stale_takeover(lp)
    check(os.path.exists(lp),
          "D2 0 字节锁件不被接管（W3 规范验收 missing_holder_old 期望＝保留，本窗不改）",
          "被接管了？若如此则 registry_tx 行为已变，须复核 D1")
    t0 = time.monotonic()
    try:
        with tx.locked(timeout=1.0, purpose="orphan_probe", lock_path=lp):
            pass
        timed_out = False
    except TimeoutError:
        timed_out = True
    check(timed_out, "D3 有 0 字节孤儿锁时 locked() 必超时（缺陷②仍活）",
          f"未超时（{time.monotonic() - t0:.2f}s）")
    print(f"[残留] 0 字节孤儿锁实测 {time.monotonic() - t0:.2f}s 超时且不可接管："
          f"甲 只堵住 CLI 泄漏源；8777 宿主 daemon 线程在进程关闭时仍可留同款空锁件。")

    # D4 认领件同类残留（本窗未获授权，只报不修）
    ck_root, _ = fresh_root("claim_orphan")
    cp.configure(root=ck_root, zen_root=ck_root, auto_worker=False)
    cdir = cp.claims_dir()
    os.makedirs(cdir, exist_ok=True)
    cpath = cp._claim_path("orphan-claim")
    open(cpath, "wb").close()
    check(not cp._claim_acquire("orphan-claim"),
          "D4 0 字节认领件同样不可接管 ⇒ 该单元永久 skipped（同类残留，未获授权修）",
          "被接管了？与 _claim_acquire 现实现不符，须复核")
    os.remove(cpath)


def main():
    print(f"[header] {time.strftime('%Y-%m-%d %H:%M:%S')} python={PY}")
    print(f"[header] 工作区 src sha16="
          f"{ {p: sha16(os.path.join(ROOT, p)) for p in ('congci_pipeline.py', 'registry_tx.py')} }")
    shutil.rmtree(SCRATCH, ignore_errors=True)
    os.makedirs(SCRATCH, exist_ok=True)
    # 自证隔离（前后各取一次）：真实持久脑全程字节不变＝本件未喂任何真实数据
    # 〔规约 §二.3 ⑨〕路径走取值式，不写死。**必须在此处（configure(tmp_root) 之前）
    # 绑定**：若在 finally 里再调 cp.brain_path()，读到的会是 tmp 根 ⇒ Z1 恒真。
    real_brain = cp.brain_path()
    real_root = os.path.dirname(real_brain)
    assert os.path.exists(real_brain), \
        (f"Z1 会假通过：真实脑件不存在（{real_brain}）⇒ before/after 都会是空串。"
         "本件的「未喂真实数据」自证依赖该件在场，不在场即无证明力。")
    brain_before = sha16(real_brain)
    head_path = None
    try:
        head_path = test_A()
        test_B()
        test_C()
        test_D()
    finally:
        brain_after = sha16(real_brain) if os.path.exists(real_brain) else ""
        check(brain_before == brain_after,
              "Z1 真实持久脑字节未变（本件未喂真实数据·隔离自证）",
              f"before={brain_before} after={brain_after}")
        assert not cp._root().startswith(real_root), \
            f"隔离破防：_root 指向真实脑目录 {cp._root()}"
    print("\n" + "=" * 70)
    print(f"[selftest] PASS={len(PASS)} FAIL={len(FAIL)}")
    for f in FAIL:
        print(f"  - {f}")
    # 〔2026-10-10 更正〕原写「gitignored」不成立：.gitignore:287 是 /_analysis_tmp/*.py
    # 只盖深度 1，本件写在深度 2；且 .gitignore:91 的 !*.py 会把嵌套 .py 请回跟踪面。
    # ⇒ 不宣称忽略状态，直接报现势未跟踪计数（由 git 自取，不靠推断）。
    try:
        n_un = subprocess.run(
            ["git", "-C", ROOT, "ls-files", "--others", "--exclude-standard",
             "--", os.path.relpath(SCRATCH, ROOT)],
            capture_output=True, text=True, encoding="utf-8").stdout.splitlines()
    except Exception as e:
        n_un = [f"<git 取数失败：{type(e).__name__}: {e}>"]
    print(f"[scratch] {SCRATCH}｜本目录未跟踪且**未被忽略**件数＝{len(n_un)}"
          f"｜before 侧 HEAD 副本 {head_path}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
