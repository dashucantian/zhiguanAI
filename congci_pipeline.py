#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
congci_pipeline.py — 从此养脑管线（批 C1·会话收口事务化·2026-10-06）
======================================================================

把正式会话 npz 离线回放进「从此」持久脑（跨坐续修），事务化幂等：
同一会话内容＋同一算法版本＋同一脑谱系永不重复学习。

授权链：法师 2026-10-05 金口七项（「七项通过，继续施工」）——
  · 批序 C0→C1→C2→C3（C0＝registry_tx 账本事务化 f1ce65e，本件为 C1）；
  · 学习用途＝既有正式会话 npz 养脑，限 QC 通过（recommend=ingest）的
    非 test/smoke/replay 会话，逐批报数；
  · 撤回者不入队（过渡：participant status=withdrawn 的新会话不入队；
    派生脑深度处置候后续裁）；
  · 轻·重两层闸门：本件轻量自测（合成数据）每批必跑；完整 bridge 自测
    仅批收口、法师在场（宿主曾于其中内核崩溃 bugcheck 0x3D，禁无人值守）。

设计承诺（施工正本＝20261005_驾驶舱×从此接入方案稿_v2.md §二）：
  幂等键四元组 session_key＋source_hash＋algo_version＋brain_lineage，
  任一变＝新处理单元，不静默复用旧判定；
  四态 pending/committed/failed/abstained（duplicate＝committed 子态，
  与 abstained 严格分列）；
  提交顺序 trace/record → 候选脑 → 验证载入 → 提升（os.replace）
  → 索引原子提交（**索引最后写**：「脑存索引败」可恢复、「索引先写脑败」
  不可能发生）；
  恢复扫描（worker 启动时＋每次入队前）：pending 行＋候选脑可载入→
  提升补 committed；候选损坏→failed 带原因，**不重学**；
  脑级串行锁＋npz 认领件防两窗/两进程竞处理。

纪律（与项目规约同向）：
  · 锁与原子写原语单一实现＝registry_tx（批 C0；红线5：本模块只复用
    registry_tx.locked/_pid_status，禁另写第二份锁逻辑；认领件与锁件同款
    安全语义＝DEAD-only 接管＋owner token 释放比对，W3 反例消费）。JSON
    原子替换依 registry_tx.write_rows_atomic 同一模式（tmp→flush→fsync→
    读回校验→os.replace），系本域产物写手（processed_index 非 CSV，不能
    直接复用 CSV DictWriter 版），非第二份登记表写逻辑；
  · 事件单一出口：session_contract.append_event，type=experience /
    actor=pipeline / kind=congci_brain，单 kind＋status 字段（仅 committed
    在全部一致产物落定后发；queued/failed/duplicate/abstained 各自可观察）；
    契约是附属物，事件失败不影响管线主流程；
  · 落点分域 output/cadence_replay/congci/（与 W4 演示旧件分域）；
  · 无学员名入档；脑档案访问域比照 02_raw 读域；
  · 弃权是一等值（桥件纪律）：不可算→abstained，不硬造。

CLI：
  python congci_pipeline.py --status                 查索引现势
  python congci_pipeline.py --enqueue <npz> [npz…]   入队既有会话（逐批报数用）
  python congci_pipeline.py --drain                  同步消化全部 pending
  python congci_pipeline.py --recover                仅恢复扫描

自测：01_项目管理/测试台验收工具/20261006_W1_congci_pipeline_test.py
（合成数据，不触真实脑目录/登记表——测试须先 configure(tmp_root)。）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import threading
import time
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import registry_tx  # 批 C0 单一事务原语（锁/进程探测）；红线5：不另写第二份

# ── 可配置根（生产默认真实分域；测试先 configure(tmp_root) 隔离）──────────
# CONGCI_PIPELINE_ROOT 环境变量＝服务实例级覆写（C2 浏览器验收用测试根，
# 生产 8777 不设即用真实分域；与 configure() 同源，后者优先）
_CFG = {
    "root": os.environ.get("CONGCI_PIPELINE_ROOT")
    or os.path.join(SCRIPT_DIR, "output", "cadence_replay", "congci"),
    "zen_root": os.environ.get("CONGCI_PIPELINE_ZEN_ROOT")
    or registry_tx.ZEN_ROOT,
    "index_lock_timeout": registry_tx.LOCK_TIMEOUT_S,   # 索引 RMW（短临界区）
    "brain_lock_timeout": 15.0,     # 脑级长临界区获取等待（处理中=持有方在跑）
    "claim_stale_s": 6 * 3600,      # 〔2026-10-06 安全修订〕已弃用（DEAD-only 接管
                                    #  不再按 mtime 夺活锁），保留键位防配置方传参报错
    "poll_s": 2.0,                  # worker 轮询间隔
    "auto_worker": True,            # enqueue 后是否懒启动后台 worker（测试置 False）
}

INDEX_SCHEMA = "1.0"
LINEAGE_ID = "congci-main"          # 持久脑谱系 id（幂等键第四元·谱系段）
SESSION_TYPES_NEVER_FEED = {"test", "smoke", "replay"}
ALGO_VERSION = None  # 延迟自桥件取（见 _algo_version()），保持桥为单一声明处

_WORKER = None
_WORKER_LOCK = threading.Lock()


def configure(root=None, zen_root=None, brain_lock_timeout=None,
              claim_stale_s=None, poll_s=None, auto_worker=None) -> dict:
    """测试隔离/部署覆写。返回当前配置（不触盘）。"""
    if root is not None:
        _CFG["root"] = root
    if zen_root is not None:
        _CFG["zen_root"] = zen_root
    if brain_lock_timeout is not None:
        _CFG["brain_lock_timeout"] = brain_lock_timeout
    if claim_stale_s is not None:
        _CFG["claim_stale_s"] = claim_stale_s
    if poll_s is not None:
        _CFG["poll_s"] = poll_s
    if auto_worker is not None:
        _CFG["auto_worker"] = auto_worker
    return dict(_CFG)


def _algo_version() -> str:
    """幂等键第三元＝桥件声明的算法版本常量（单一声明处）。

    **读取方式＝源码静态提取，不 import 桥件**：桥件顶层 `from cadence
    import Brain` 在 8777 解释器（P312）首跑会阻塞数分钟（numba JIT 缓存
    编译，沙箱实证）；若本函数走 import，则挂点 enqueue 的同步调用会被
    卡死（保存主流程连带阻塞）。常量文本读取同样服从"随桥件声明"（单一
    声明处＝zhiguan_cadence_bridge.py），只免去重型依赖导入。
    """
    import re
    global ALGO_VERSION
    if ALGO_VERSION is None:
        try:
            with open(os.path.join(SCRIPT_DIR, "zhiguan_cadence_bridge.py"),
                      encoding="utf-8") as _f:
                _m = re.search(r'^ALGO_VERSION\s*=\s*"([^"]+)"', _f.read(),
                               re.M)
            ALGO_VERSION = _m.group(1) if _m else "unknown"
        except Exception:
            ALGO_VERSION = "unknown"
    return ALGO_VERSION


# ── 路径 ────────────────────────────────────────────────────────────────

def _root() -> str:
    return _CFG["root"]


def brain_path() -> str:
    return os.path.join(_root(), "congci.brain.npz")


def index_path() -> str:
    return os.path.join(_root(), "processed_index.json")


def brain_lock_path() -> str:
    return registry_tx.lock_path_for(brain_path())      # congci.brain.npz.lock


def index_lock_path() -> str:
    return registry_tx.lock_path_for(index_path())


def claims_dir() -> str:
    return os.path.join(_root(), "claims")


def unit_dir(unit_id: str) -> str:
    return os.path.join(_root(), "records", unit_id)


# ── 原子 JSON 写（registry_tx.write_rows_atomic 同一模式，非 CSV 域）──────

def _write_json_atomic(path: str, obj) -> None:
    """tmp→flush→fsync→读回校验→os.replace。失败删临时件并抛异常（原文件不动）。"""
    tmp = path + ".tmp-tx"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        with open(tmp, "r", encoding="utf-8") as f:
            back = json.load(f)
        if not isinstance(back, dict) or "rows" not in back:
            raise IOError("原子写校验失败：读回非索引结构")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _read_index():
    """读索引（不存在返回空账）。调用方做 RMW 时须持 index 锁。"""
    p = index_path()
    if not os.path.exists(p):
        return {"schema_version": INDEX_SCHEMA, "lineage_id": LINEAGE_ID,
                "algo_version": _algo_version(), "rows": []}
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_index(doc) -> None:
    _write_json_atomic(index_path(), doc)


# ── 小工具 ──────────────────────────────────────────────────────────────

def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _safe_name(s: str) -> str:
    """文件名/目录名安全化（Zen-ID 与 hex 天然安全；其余字符收敛）。"""
    keep = []
    for ch in str(s):
        keep.append(ch if (ch.isalnum() or ch in "._-") else "_")
    return "".join(keep) or "unnamed"


def _session_events_path(npz_path: str) -> str:
    """会话事件流路径——循 console_server.py:2716 既有口径：
    归档（父目录 ZEN-*）＝session_events.jsonl；暂存＝同名派生件。"""
    d = os.path.dirname(os.path.abspath(npz_path))
    sid = os.path.basename(d)
    if sid.startswith("ZEN-"):
        return os.path.join(d, "session_events.jsonl")
    stem = os.path.splitext(os.path.basename(npz_path))[0]
    return os.path.join(d, stem + ".session_events.jsonl")


_UI_CALLBACK = None          # 批 C3：console_server 注册的 UI/声带回调（附属物）


def set_ui_callback(fn) -> None:
    """注册 UI 回调：console_server 启动时挂声带＋上屏 SSE（金口#3/#4）。
    fn(payload_dict) 在每次状态事件（queued/committed/failed/duplicate/
    abstained）时被调；回调抛错不影响管线主流程（契约是附属物纪律）。"""
    global _UI_CALLBACK
    _UI_CALLBACK = fn


def _emit_event(npz_path, status: str, row: dict, note: str = "") -> bool:
    """congci_brain 事件（单 kind＋status 字段）入会话事件流。
    契约是附属物：文件缺失/写失败一律返回 False，不影响管线。"""
    try:
        from session_contract import append_event
        payload = {"status": status,
                   "session_key": row.get("session_key"),
                   "unit_id": row.get("unit_id"),
                   "source_hash16": row.get("source_hash16"),
                   "algo_version": row.get("algo_version"),
                   "lineage_id": row.get("lineage_id"),
                   "brain_version": row.get("result_brain_version")
                   or row.get("brain_base_version"),
                   "duplicate_of": row.get("duplicate_of"),
                   "epochs": row.get("epochs"),
                   "reason": row.get("reason")}
        ok = append_event(_session_events_path(npz_path),
                          "experience", "pipeline", "congci_brain",
                          payload, note or f"从此脑收口：{status}")
    except Exception:
        ok = False
    # 批 C3：UI/声带回调（附属物，失败静默；上屏与发声不阻断管线）
    if _UI_CALLBACK is not None:
        try:
            _UI_CALLBACK({"status": status,
                          "session_key": row.get("session_key"),
                          "unit_id": row.get("unit_id"),
                          "reason": row.get("reason"),
                          "brain_version": row.get("result_brain_version")
                          or row.get("brain_base_version")})
        except Exception:
            pass
    return ok


# ── npz 解析（暂存→入库移动的兜底）──────────────────────────────────────

def _resolve_npz(row: dict) -> str:
    """行内 npz 路径不存在时按 source_hash16 反查归档位（qc.json 指纹）。
    返回可用路径；解析不到抛 FileNotFoundError。"""
    p = row.get("npz_path") or ""
    if p and os.path.exists(p):
        return p
    p2 = row.get("npz_resolved") or ""
    if p2 and os.path.exists(p2):
        return p2
    h16 = row.get("source_hash16") or ""
    qc_root = os.path.join(_CFG["zen_root"], "03_quality_control")
    if h16 and os.path.isdir(qc_root):
        for sid in sorted(os.listdir(qc_root)):
            if not sid.startswith("ZEN-"):
                continue
            qj = os.path.join(qc_root, sid, "qc.json")
            if not os.path.exists(qj):
                continue
            try:
                with open(qj, "r", encoding="utf-8") as f:
                    if json.load(f).get("eeg_sha256_16") == h16:
                        cand = os.path.join(_CFG["zen_root"], "02_raw", sid,
                                            "eeg_raw.npz")
                        if os.path.exists(cand):
                            return cand
            except Exception:
                continue
    raise FileNotFoundError(f"源 npz 缺失且指纹反查未命中：{p}")


# ── 准入（金口七项#2/#6；入队前现查）────────────────────────────────────

def _qc_verdict(npz_path: str, qc=None) -> dict:
    """QC 判定现查：定稿判定按会话所在区取——归档位（02_raw/<sid>/）读
    03_quality_control/<sid>/qc.json，隔离位（03_quality_control/quarantine/<sid>/）
    读同目录 qc.json；暂存位/两处均无定稿走 qc_pipeline.assess_cached（同管线现算）。
    定稿存在但读不进一律抛出，不静默回落现算。返回
    {recommend, quarantined, source, threshold_version} 或抛异常。"""
    if isinstance(qc, dict) and qc.get("recommend"):
        return {"recommend": qc.get("recommend"),
                "quarantined": bool(qc.get("quarantined")),
                "source": "fresh", "threshold_version": qc.get("threshold_version")}
    d = os.path.dirname(os.path.abspath(npz_path))
    if os.path.basename(d).startswith("ZEN-"):
        sid = os.path.basename(d)
        # 定稿落点随会话所在区不同：归档位在 03_quality_control/<sid>/，隔离位比它深
        # 一级，定稿就在自己目录里。此处按序探两处，命中即读——隔离标志只存在于定稿，
        # 现算无从得知人工隔离。归档位表达式保持第一位，其既有行为不变。
        qj = None
        for cand in (os.path.normpath(os.path.join(d, "..", "..",
                                                   "03_quality_control", sid, "qc.json")),
                     os.path.join(d, "qc.json")):
            if os.path.exists(cand):
                qj = cand
                break
        if qj is not None:
            with open(qj, "r", encoding="utf-8") as f:
                q = json.load(f)
            return {"recommend": q.get("recommend"),
                    "quarantined": bool(q.get("quarantined")),
                    "source": "03_quality_control/qc.json",
                    "threshold_version": q.get("threshold_version")}
    import qc_pipeline
    r = qc_pipeline.assess_cached(npz_path)
    return {"recommend": r.get("recommend"),
            "quarantined": r.get("recommend") == "quarantine",
            "source": "assess_cached",
            "threshold_version": getattr(qc_pipeline, "THRESHOLD_VERSION", None)}


def _participant_withdrawn(participant_id: str) -> bool:
    """撤回者不入队（金口#6 过渡）。判定源＝00_governance/participant_status.json
    （{"P00X": "withdrawn"}）。撤回流程本体系数据盘查 P4-4 候法师项，现无数据——
    文件不存在时恒 False（如实：当前无人处于撤回态）。"""
    if not participant_id:
        return False
    p = os.path.join(_CFG["zen_root"], "00_governance",
                     "participant_status.json")
    if not os.path.exists(p):
        return False
    try:
        with open(p, "r", encoding="utf-8") as f:
            status = json.load(f)
        return str(status.get(participant_id, "")).lower() == "withdrawn"
    except Exception:
        return False    # 判定源不可读时不拦截（不猜测定论），如实留待人工


def admit(npz_path: str, *, qc=None, session_type: str = "",
          participant: str = "") -> dict:
    """养脑准入。通过→{"admitted": True, "qc": 判定}；拒绝→{"admitted": False,
    "reason": ...}。拒绝者不入队（合成断言面）。"""
    if (session_type or "").strip().lower() in SESSION_TYPES_NEVER_FEED:
        return {"admitted": False,
                "reason": f"会话类型 {session_type} 不养脑（test/smoke/replay）"}
    try:
        verdict = _qc_verdict(npz_path, qc=qc)
    except FileNotFoundError:
        raise
    except Exception as e:
        return {"admitted": False, "reason": f"QC 判定不可得（{e}）"}
    if verdict.get("recommend") != "ingest" or verdict.get("quarantined"):
        return {"admitted": False,
                "reason": f"QC 未通过（recommend={verdict.get('recommend')}"
                          f"{'，quarantined' if verdict.get('quarantined') else ''}）",
                "qc": verdict}
    if _participant_withdrawn(participant):
        return {"admitted": False, "reason": "撤回者不入队（金口#6 过渡）",
                "qc": verdict}
    return {"admitted": True, "qc": verdict}


# ── 索引行 ──────────────────────────────────────────────────────────────

def _base_lineage(doc) -> tuple:
    """当前持久脑谱系基线：(version, sha16)。version＝已 committed 单元数。"""
    v = sum(1 for r in doc["rows"] if r.get("status") == "committed"
            and not r.get("duplicate_of"))
    bp = brain_path()
    s16 = sha256_file(bp)[:16] if os.path.exists(bp) else ""
    return v, s16


def enqueue(npz_path: str, *, session_key: str = None, qc=None,
            session_type: str = "", participant: str = "", scene: str = "",
            source_label: str = "") -> dict:
    """会话收口→只入队（挂点唯一入口；不学习不写脑）。

    返回 {"queued": bool, "status": queued|rejected|duplicate|already_pending,
          "unit_id", "reason", "row"}。duplicate＝幂等命中已 committed/abstained
    单元（无新增行）；already_pending＝同一单元已在队（防两路同 npz）。
    """
    npz_path = os.path.abspath(npz_path)
    if not os.path.exists(npz_path):
        return {"queued": False, "status": "rejected",
                "reason": f"npz 不存在：{npz_path}"}
    adm = admit(npz_path, qc=qc, session_type=session_type,
                participant=participant)
    if not adm.get("admitted"):
        return {"queued": False, "status": "rejected",
                "reason": adm.get("reason"), "qc": adm.get("qc")}

    source_hash = sha256_file(npz_path)
    h16 = source_hash[:16]
    if session_key is None:
        sid = os.path.basename(os.path.dirname(npz_path))
        session_key = sid if sid.startswith("ZEN-") else source_hash  # 未入库期＝内容 hash
    session_key = _safe_name(session_key)
    av = _algo_version()

    lp = index_lock_path()
    with registry_tx.locked(purpose="congci_enqueue", lock_path=lp):
        doc = _read_index()                      # 锁内重读（写时合并纪律）
        rows = doc["rows"]
        # 幂等命中：同 hash＋同算法＋同谱系已 committed/abstained（任意 base 版本
        # ——同内容已进过此谱系即不再学，宁严勿松；换算法版本＝新单元不受此限）
        for r in rows:
            if (r.get("status") in ("committed", "abstained")
                    and r.get("source_hash16") == h16
                    and r.get("algo_version") == av
                    and r.get("lineage_id") == LINEAGE_ID):
                _emit_event(npz_path, "duplicate", {**r, "duplicate_of": r["unit_id"]},
                            "幂等命中已收口单元，不重复学习")
                return {"queued": False, "status": "duplicate",
                        "duplicate_of": r["unit_id"], "row": r}
        # 在队命中：同一 session_key＋hash 已 pending（反例1 第二路）
        for r in rows:
            if (r.get("status") == "pending"
                    and r.get("session_key") == session_key
                    and r.get("source_hash16") == h16):
                return {"queued": False, "status": "already_pending",
                        "unit_id": r["unit_id"], "row": r}
        base_v, base_s16 = _base_lineage(doc)
        n_attempt = 1 + sum(1 for r in rows
                            if r.get("session_key") == session_key
                            and r.get("source_hash16") == h16)
        base_id = f"{session_key}--{h16[:12]}"
        unit_id = base_id if n_attempt == 1 else f"{base_id}--a{n_attempt}"
        row = {"unit_id": unit_id, "session_key": session_key,
               "source_hash": source_hash, "source_hash16": h16,
               "algo_version": av, "lineage_id": LINEAGE_ID,
               "brain_base_version": base_v, "brain_base_sha16": base_s16,
               "status": "pending", "duplicate_of": None,
               "npz_path": npz_path, "npz_resolved": None,
               "participant": participant or "", "scene": scene or "",
               "session_type": session_type or "",
               "qc_source": (adm.get("qc") or {}).get("source"),
               "qc_recommend": (adm.get("qc") or {}).get("recommend"),
               "queued_at": _now(), "picked_at": None, "finished_at": None,
               "worker_pid": None, "epochs": None,
               "record_path": None, "trace_path": None,
               "result_brain_version": None, "result_brain_sha16": None,
               "reason": None}
        rows.append(row)
        _write_index(doc)
    _emit_event(npz_path, "queued", row, "会话收口→从此养脑入队")
    ensure_worker()
    return {"queued": True, "status": "queued", "unit_id": unit_id, "row": row}


# ── 认领件（反例1：两路/两进程同 npz 竞处理）────────────────────────────
# 〔2026-10-06 批 C0 锁族安全修订·W3 反例消费〕认领件与 registry_tx 锁件
# 同款安全语义：仅持认领 pid **确证已死**才可接管（活持有者无论持有多久
# 不可夺）；owner token 记账比对后才释放（防误删接管者新认领）；unknown
# 不接管（泄漏由人工按坑 018 口径核持有者处置）。

_CLAIM_TOKENS = {}          # session_key -> owner_token（本进程认领记账）


def _claim_path(session_key: str) -> str:
    return os.path.join(claims_dir(), _safe_name(session_key) + ".claim")


def _claim_acquire(session_key: str) -> bool:
    """O_CREAT|O_EXCL 原子认领；陈旧接管＝持认领 pid 确证已死（registry_tx
    同一三态探测实现）；活持有者/unknown 一律不接管。成功 True；他人持有 False。"""
    import secrets
    os.makedirs(claims_dir(), exist_ok=True)
    cp = _claim_path(session_key)
    token = secrets.token_hex(8)
    try:
        fd = os.open(cp, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, (f"holder_pid={os.getpid()}\nowner_token={token}\n"
                      f"time={_now()}\npurpose=congci_feed\n").encode("utf-8"))
        os.close(fd)
        _CLAIM_TOKENS[session_key] = token
        return True
    except FileExistsError:
        pass
    try:
        pid = 0
        with open(cp, encoding="utf-8", errors="ignore") as f:
            for line in f:
                if line.startswith("holder_pid="):
                    pid = int(line.split("=", 1)[1].strip() or 0)
                    break
        if pid and registry_tx._pid_status(pid) == "dead":
            os.remove(cp)               # 陈旧接管（确证死 pid，证据在件内）
            return _claim_acquire(session_key)
    except (FileNotFoundError, ValueError, OSError):
        pass
    return False


def _claim_release(session_key: str) -> None:
    """owner token 记账比对后才删除——误删接管者（新主）的认领件会破互斥
    （W3 反例②同款语义）。"""
    cp = _claim_path(session_key)
    token = _CLAIM_TOKENS.pop(session_key, None)
    try:
        with open(cp, encoding="utf-8", errors="ignore") as f:
            content = f.read()
        if token and f"owner_token={token}" in content:
            os.remove(cp)
    except FileNotFoundError:
        pass


# ── 索引行提交（锁内重读合并——C0 同款纪律）─────────────────────────────

def _commit_row(unit_id: str, mutate) -> dict:
    """锁内重读索引→按 unit_id 定位→mutate(row)→原子写。返回更新后行。
    行已消失（他进程已处置）→抛 LookupError（调用方按竞处理放弃）。"""
    with registry_tx.locked(purpose="congci_commit", lock_path=index_lock_path()):
        doc = _read_index()
        hit = None
        for r in doc["rows"]:
            if r.get("unit_id") == unit_id:
                hit = r
                break
        if hit is None:
            raise LookupError(f"unit {unit_id} 已不在索引（他进程已处置）")
        mutate(hit)
        _write_index(doc)
        return dict(hit)


# ── 处理一单元（脑级串行临界区）─────────────────────────────────────────

def _brain_lock():
    return registry_tx.locked(purpose="congci_brain_process",
                              lock_path=brain_lock_path(),
                              timeout=_CFG["brain_lock_timeout"])


def _brain_loads(path: str) -> bool:
    """候选脑可载入校验（恢复扫描/提交前验证用）。"""
    try:
        from cadence import Brain
        Brain.load(path)
        return True
    except SystemError:
        raise
    except Exception:
        return False


def _sha16(path: str) -> str:
    return sha256_file(path)[:16] if path and os.path.exists(path) else ""


def _record_path(unit_id: str) -> str:
    return os.path.join(unit_dir(unit_id), "record.json")


def _write_record_atomic(unit_id: str, record: dict) -> str:
    p = _record_path(unit_id)
    tmp = p + ".tmp-tx"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        with open(tmp, "r", encoding="utf-8") as f:
            json.load(f)
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    return p


def _process_row(row: dict, *, inject_fail: str = None) -> dict:
    """消化一个 pending 行（worker/ drain 共用）。返回终态行快照。

    inject_fail（恢复注入测试钩子，仅合成测试用）：
      "candidate_save" —— 候选脑写出前抛错（事务①前中断→failed）；
      "index_write"    —— 提升后、索引提交前抛错（事务③中断→可恢复）。
    """
    unit_id = row["unit_id"]
    sk = row["session_key"]
    if not _claim_acquire(sk):
        return {"skipped": True, "unit_id": unit_id,
                "reason": "认领件被他人新鲜持有（另一进程在处理）"}
    try:
        try:
            npz_path = _resolve_npz(row)
        except FileNotFoundError as e:
            return _finish_failed(row, str(e))
        if row.get("npz_resolved") != npz_path:
            _commit_row(unit_id, lambda r: r.update(
                {"npz_resolved": npz_path}))
            row["npz_resolved"] = npz_path

        with _brain_lock():
            # 脑锁内重读索引：他进程可能已把该行处置（竞处理收敛）
            try:
                cur = _commit_row(unit_id, lambda r: r.update(
                    {"picked_at": _now(), "worker_pid": os.getpid()}))
            except LookupError:
                return {"skipped": True, "unit_id": unit_id,
                        "reason": "他进程已处置（脑锁内重读发现）"}
            if cur.get("status") != "pending":
                return {"skipped": True, "unit_id": unit_id,
                        "reason": f"状态已为 {cur.get('status')}"}

            udir = unit_dir(unit_id)
            os.makedirs(udir, exist_ok=True)
            bp = brain_path()
            base_sha = _sha16(bp)

            if inject_fail == "candidate_save":
                raise RuntimeError("注入失败：candidate_save（事务①前中断）")
            from zhiguan_cadence_bridge import process_session
            res = process_session(npz_path, brain_path=bp, out_dir=udir,
                                  session_key=row.get("session_key"))
            if res.get("abstained"):
                record = {"schema": INDEX_SCHEMA, "unit_id": unit_id,
                          "status": "abstained", "reason": res.get("reason"),
                          "session_key": row.get("session_key"),
                          "source_hash16": row.get("source_hash16"),
                          "algo_version": row.get("algo_version"),
                          "lineage_id": LINEAGE_ID,
                          "brain_base_version": row.get("brain_base_version"),
                          "brain_base_sha16": row.get("brain_base_sha16"),
                          "npz": npz_path, "abstained_at": _now()}
                rp = _write_record_atomic(unit_id, record)

                def _m(r):
                    r.update({"status": "abstained", "reason": res.get("reason"),
                              "finished_at": _now(), "record_path": rp,
                              "trace_path": None, "epochs": None,
                              "result_brain_version": None,
                              "result_brain_sha16": None})
                fin = _commit_row(unit_id, _m)
                _emit_event(npz_path, "abstained", fin,
                            f"从此脑弃权：{res.get('reason')}")
                return fin

            cand = res.get("candidate_path")
            if not cand or not os.path.exists(cand):
                return _finish_failed(row, "候选脑件缺失（process_session 未落盘）")
            result_sha16 = _sha16(cand)
            record = {"schema": INDEX_SCHEMA, "unit_id": unit_id,
                      "status": "committed",
                      "session_key": row.get("session_key"),
                      "source_hash": row.get("source_hash"),
                      "source_hash16": row.get("source_hash16"),
                      "algo_version": row.get("algo_version"),
                      "lineage_id": LINEAGE_ID,
                      "brain_base_version": row.get("brain_base_version"),
                      "brain_base_sha16": row.get("brain_base_sha16"),
                      "result_brain_sha16": result_sha16,
                      "npz": npz_path, "summary": res.get("summary"),
                      "trace_path": res.get("trace_path"),
                      "committed_at": _now()}
            rp = _write_record_atomic(unit_id, record)
            # 候选脑可载入校验（写坏不提升）
            if not _brain_loads(cand):
                try:
                    os.remove(cand)
                except OSError:
                    pass
                return _finish_failed(row, "候选脑载入校验失败（已删除候选，不提升）")

            def _pre_promote(r):
                r.update({"epochs": (res.get("summary") or {}).get("epochs"),
                          "trace_path": res.get("trace_path"),
                          "record_path": rp})
            _commit_row(unit_id, _pre_promote)

            os.replace(cand, bp)                 # 事务②：候选提升为正式脑
            if inject_fail == "index_write":
                raise RuntimeError("注入失败：index_write（事务③中断，模拟脑存索引败）")

            def _m(r):
                r.update({"status": "committed", "finished_at": _now(),
                          "record_path": rp,
                          "result_brain_version":
                              (r.get("brain_base_version") or 0) + 1,
                          "result_brain_sha16": result_sha16})
            fin = _commit_row(unit_id, _m)
            _emit_event(npz_path, "committed", fin,
                        f"从此脑已收口（v{fin.get('result_brain_version')}）")
            return fin
    except Exception as e:
        if inject_fail == "index_write":
            raise          # 恢复注入：模拟提升后、索引提交前进程死亡——行保持
                           # pending 交恢复扫描补登 committed（不在此处标 failed）
        if isinstance(e, TimeoutError):
            # 脑锁/索引锁争用超时＝他进程正在处理，不是本单元失败——保持
            # pending 待下轮重试（改判 failed 会把瞬时争用记成永久失败）
            return {"skipped": True, "unit_id": unit_id, "reason": str(e)}
        try:
            return _finish_failed(row, f"{type(e).__name__}: {e}")
        except Exception as e2:
            return {"unit_id": row.get("unit_id"), "status": "failed",
                    "reason": f"{e}（且失败登记再失败：{e2}）"}
    finally:
        _claim_release(sk)


def _finish_failed(row: dict, reason: str) -> dict:
    """failed（可重试，带原因）。失败不动正式脑（持久脑字节不变）。"""
    unit_id = row["unit_id"]
    try:
        cand = os.path.join(unit_dir(unit_id), "brain.candidate.npz")
        if os.path.exists(cand):
            os.remove(cand)                      # 残候选删除（防恢复误提升）
    except OSError:
        pass
    try:
        fin = _commit_row(unit_id, lambda r: r.update(
            {"status": "failed", "reason": reason[:500],
             "finished_at": _now()}))
    except LookupError:
        fin = {"unit_id": unit_id, "status": "failed", "reason": reason}
    npz = row.get("npz_resolved") or row.get("npz_path")
    if npz:
        _emit_event(npz, "failed", fin, f"从此脑收口失败：{reason[:120]}")
    return fin


# ── 恢复扫描（worker 启动时＋每次入队前；不重学）────────────────────────

def recover_pending() -> dict:
    """pending 行恢复：候选可载入＋record 在→提升补 committed；
    候选损坏/缺失→failed 带原因。索引提交恒最后（事务顺序自证）。

    **只处理「已开工」行**（picked_at 非空）——2026-10-06 自验实测缺陷修复：
    新入队的在队行尚未开工、天然无 record；旧实现把这类行当「事务②前中断」
    直接标 failed，致生产模式（auto_worker=True，worker 启动即先跑恢复扫描）
    下每次入队都被误判失败、C1 主路径不可用。未开工行一律留给正常 worker
    路径消化（不在此判死）。
    """
    out = {"committed": [], "failed": []}
    lp = index_lock_path()
    with registry_tx.locked(purpose="congci_recover_scan", lock_path=lp):
        doc = _read_index()
        pending = [r for r in doc["rows"] if r.get("status") == "pending"
                   and r.get("picked_at")]      # ← 仅已开工（见 docstring）
    if not pending:
        return out
    for row in pending:
        unit_id = row["unit_id"]
        udir = unit_dir(unit_id)
        rp = _record_path(unit_id)
        cand = os.path.join(udir, "brain.candidate.npz")
        bp = brain_path()
        try:
            with _brain_lock():
                if not os.path.exists(rp):
                    _finish_failed(row, "恢复扫描：record 缺失（事务②前中断），不重学")
                    out["failed"].append(unit_id)
                    continue
                with open(rp, "r", encoding="utf-8") as f:
                    record = json.load(f)
                if os.path.exists(cand):
                    if not _brain_loads(cand):
                        _finish_failed(row, "恢复扫描：候选脑损坏（不可载入），不重学")
                        out["failed"].append(unit_id)
                        continue
                    result_sha16 = _sha16(cand)
                    os.replace(cand, bp)
                else:
                    result_sha16 = record.get("result_brain_sha16") or ""
                    if not result_sha16 or result_sha16 != _sha16(bp):
                        _finish_failed(row, "恢复扫描：候选缺失且正式脑不匹配（恢复歧义）")
                        out["failed"].append(unit_id)
                        continue

                def _m(r):
                    r.update({"status": "committed", "finished_at": _now(),
                              "record_path": rp,
                              "trace_path": record.get("trace_path"),
                              "epochs": (record.get("summary") or {}).get("epochs"),
                              "result_brain_version":
                                  (r.get("brain_base_version") or 0) + 1,
                              "result_brain_sha16": result_sha16})
                fin = _commit_row(unit_id, _m)
                npz = fin.get("npz_resolved") or fin.get("npz_path")
                if npz:
                    _emit_event(npz, "committed", fin,
                                f"恢复扫描补登 committed（v{fin.get('result_brain_version')}）")
                out["committed"].append(unit_id)
        except Exception as e:
            try:
                _finish_failed(row, f"恢复扫描异常：{type(e).__name__}: {e}")
            except Exception:
                pass
            out["failed"].append(unit_id)
    return out


# ── worker（单 worker 串行消化；队列先行，挂点零等待）────────────────────

def _pick_pending():
    with registry_tx.locked(purpose="congci_pick", lock_path=index_lock_path()):
        doc = _read_index()
        pend = [r for r in doc["rows"] if r.get("status") == "pending"]
        if not pend:
            return None
        pend.sort(key=lambda r: r.get("queued_at") or "")
        return dict(pend[0])


def _worker_loop():
    while True:
        try:
            recover_pending()
            row = _pick_pending()
            if row:
                _process_row(row)
        except Exception as e:
            print(f"[warn] congci worker 轮询异常（继续）：{type(e).__name__}: {e}")
        time.sleep(_CFG["poll_s"])


def ensure_worker() -> None:
    """懒启动单 worker 守护线程（幂等）。随宿主进程存亡（daemon）。
    测试（auto_worker=False）不启后台线程，由 drain() 同步消化。"""
    if not _CFG["auto_worker"]:
        return
    global _WORKER
    with _WORKER_LOCK:
        if _WORKER is not None and _WORKER.is_alive():
            return
        _WORKER = threading.Thread(target=_worker_loop, daemon=True,
                                   name="congci-feeder")
        _WORKER.start()


def drain(limit: int = None) -> list:
    """同步消化全部 pending（CLI/测试用；生产路径＝worker 线程）。"""
    done = []
    while True:
        row = _pick_pending()
        if row is None:
            break
        fin = _process_row(row)
        done.append(fin)
        if limit and len(done) >= limit:
            break
        if fin.get("skipped"):
            break                            # 认领/竞态受阻，避免空转
    return done


# ── CLI ─────────────────────────────────────────────────────────────────

def _cli_status() -> int:
    doc = _read_index()
    rows = doc.get("rows", [])
    by = {}
    for r in rows:
        by[r.get("status")] = by.get(r.get("status"), 0) + 1
    bp = brain_path()
    print(json.dumps({
        "root": _root(), "rows": len(rows), "by_status": by,
        "brain": {"exists": os.path.exists(bp),
                  "sha16": _sha16(bp) or None,
                  "version": sum(1 for r in rows
                                 if r.get("status") == "committed"
                                 and not r.get("duplicate_of"))},
        "last": [{k: r.get(k) for k in
                  ("unit_id", "status", "queued_at", "finished_at",
                   "result_brain_version", "reason")}
                 for r in rows[-5:]],
    }, ensure_ascii=False, indent=1))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="从此养脑管线（批 C1）")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--enqueue", nargs="+", metavar="NPZ")
    ap.add_argument("--drain", action="store_true")
    ap.add_argument("--recover", action="store_true")
    a = ap.parse_args()
    if a.status:
        return _cli_status()
    if a.enqueue:
        n = 0
        for p in a.enqueue:
            r = enqueue(p)
            print(json.dumps({"npz": p, **{k: r.get(k) for k in
                                           ("queued", "status", "unit_id",
                                            "duplicate_of", "reason")}},
                             ensure_ascii=False))
            n += 1 if r.get("queued") else 0
        print(f"enqueued={n}")
        return 0
    if a.recover:
        print(json.dumps(recover_pending(), ensure_ascii=False))
        return 0
    if a.drain:
        res = drain()
        print(json.dumps([{k: f.get(k) for k in
                           ("unit_id", "status", "result_brain_version",
                            "reason")} for f in res], ensure_ascii=False, indent=1))
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())