#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
registry_tx.py — Zen-EEG 会话登记表跨进程事务原语（批 C0·账本事务化）
=====================================================================

背景（W3 合成五反例实证，engine/20261005-W3-AI014-共享登记合成交错验证回执.md；
法师金口 2026-10-05「七项通过，继续施工」批 C0）：

  登记表 `D:\Project\Zen-EEG\01_registry\session_registry.csv` 有两个写方——
  console_server.py 预登记（/api/registry/preregister）与
  ingest_session.py 入库回填/补登记。旧实现均为「读全表 → 改 → open("w")
  全表重写」，无锁无原子性，交错下产生：丢更新（预登记新行被旧 ingest
  快照重写抹掉）、状态回退（finished 被旧预登记快照退回 planned）、
  编号复用（两份旧快照同算 S02）、截空（writeheader 失败时目标已被
  open("w") 截断）。

本模块三件套（W1 设计承诺，消费回执在案）：
  1. 跨进程锁件（O_CREAT|O_EXCL 原子创建；内容=pid/owner_token/时刻/用途；
     陈旧接管=**仅持锁 pid 确证已死**〔2026-10-06 批 C0 锁族安全修订·W3
     反例消费〕；释放前 owner_token 比对，防误删接管者新锁；unknown 不接管）；
  2. 原子替换（临时件写入→flush→读回校验→os.replace）；
  3. 写时锁内重读合并（append/回填都基于锁内最新表查重——旧快照
     不再被写回，丢更新与状态回退反例在机制上消除）。

纪律：
  · Zen-ID 永不复用（数据字典 V1.2 冻结规则）；已存在即报错，不覆盖；
  · 口径单一：S 号分配规则与 console_server 旧实现逐字同源（跨日期递增）；
  · 失败保留原文件不动（临时件删除后抛异常）；
  · 不拿内存快照当备份（恢复以磁盘最新完整版为准）。

Windows 注意：进程存活探测用 ctypes OpenProcess，**禁用 os.kill(pid,0)**
（Windows 语义是无条件 TerminateProcess，会杀死无辜进程）。
自测见 test_registry_tx.py（合成 TemporaryDirectory；不触真实登记表）。
"""

from __future__ import annotations

import csv
import os
import time
from contextlib import contextmanager
from datetime import datetime

ZEN_ROOT = r"D:\Project\Zen-EEG"
REGISTRY_CSV = os.path.join(ZEN_ROOT, "01_registry", "session_registry.csv")

FIELDNAMES = ["session_id", "participant_id", "date", "session_type",
              "duration_seconds", "status", "manifest_path"]

LOCK_TIMEOUT_S = 10.0     # 获取锁最长等待（忙重试，不无限挂）
LOCK_STALE_S = 120.0      # 〔2026-10-06 安全修订·W3 反例〕已弃用：DEAD-only
                          # 接管不再按 mtime 夺活锁；常量保留防外部引用告警


def lock_path_for(csv_path: str) -> str:
    """登记表对应的锁件路径（与 csv 同目录同名 + .lock）。"""
    return csv_path + ".lock"


# ── 进程存活探测（Windows 安全）─────────────────────────────────────────

if os.name == "nt":
    import ctypes
    _K32 = ctypes.WinDLL("kernel32", use_last_error=True)  # 保 last-error 供错误码判定
else:
    _K32 = None


def _pid_status(pid) -> str:
    """进程存活三态：alive（确证存在）／dead（确证不存在）／unknown（无法判定）。

    〔2026-10-06 批 C0 锁族安全修订·W3 反例消费〕旧 `_pid_alive` 返回 bool 时，
    Windows OpenProcess 失败（拒绝访问 5 或探测失败）与进程不存在（87）都被
    折叠成 False＝"已死"→ 活进程锁可被误夺；且 `age>LOCK_STALE_S` 分支可夺
    活持有者锁。本函数把「无法判定」与「确证已死」严格分列——**unknown 一律
    不当死**（W3 反例结论：无法判定存活时保留 unknown/超时拒绝，不自动接管）。
    """
    if not pid:
        return "unknown"
    if os.name == "nt":
        try:
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            h = _K32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False,
                                 int(pid))
            if not h:
                # 87=ERROR_INVALID_PARAMETER（进程不存在，确证 dead）；
                # 5=拒绝访问／其它＝unknown（不得当死）
                return "dead" if _K32.GetLastError() == 87 else "unknown"
            try:
                code = ctypes.c_ulong()
                if not _K32.GetExitCodeProcess(h, ctypes.byref(code)):
                    return "unknown"
                return "alive" if code.value == STILL_ACTIVE else "dead"
            finally:
                _K32.CloseHandle(h)
        except Exception:
            return "unknown"
    # POSIX 退路（本项目主力 Windows；保留跨平台语义）
    try:
        os.kill(pid, 0)
        return "alive"
    except ProcessLookupError:
        return "dead"
    except Exception:
        return "unknown"


@contextmanager
def locked(timeout: float = LOCK_TIMEOUT_S, purpose: str = "",
           lock_path: str = None):
    """登记表跨进程互斥。用法：
        lp = registry_tx.lock_path_for(csv)
        with registry_tx.locked(purpose="preregister", lock_path=lp):
            rows = registry_tx.read_rows(csv)
            ...  # 锁内改
            registry_tx.write_rows_atomic(rows, csv)

    〔2026-10-06 批 C0 锁族安全修订·W3 反例消费〕：
      · 锁件内容含 owner_token（本获锁唯一令牌）；释放前比对令牌，令牌不符
        不删除——新主锁不被旧持有者 finally 误删（W3 反例②）；
      · 陈旧接管＝**仅当持锁 pid 确证已死（_pid_status=="dead"）**；活持有者
        锁无论持有多久都不可夺（age 分支已删除，W3 反例①）；
      · unknown（拒绝访问/无法判定）一律不接管——锁泄漏由调用方超时
        TimeoutError＋人工按坑 018 口径核持有者处置。
    """
    import secrets
    lp = lock_path or lock_path_for(REGISTRY_CSV)
    token = secrets.token_hex(8)
    deadline = time.monotonic() + timeout
    fd = None
    while True:
        try:
            fd = os.open(lp, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            _try_stale_takeover(lp)
            if time.monotonic() >= deadline:
                raise TimeoutError(f"registry 锁等待超时（{timeout}s）：{lp}")
            time.sleep(0.05)
    try:
        os.write(fd, (
            f"holder_pid={os.getpid()}\n"
            f"owner_token={token}\n"
            f"time={datetime.now().isoformat(timespec='seconds')}\n"
            f"purpose={purpose}\n").encode("utf-8"))
        os.close(fd)
        yield
    finally:
        # owner token 比对后才删除：防把接管者（新主）的锁件误删。
        # 注意：句柄须先关再删（Windows 下打开中的文件不可删，WinError 32）。
        try:
            with open(lp, encoding="utf-8", errors="ignore") as _f:
                _content = _f.read()
            if f"owner_token={token}" in _content:
                os.remove(lp)
        except FileNotFoundError:
            pass


def _try_stale_takeover(lp: str) -> None:
    """陈旧锁接管：**仅持锁 pid 确证已死**（_pid_status=="dead"）才移除。
    活持有者锁不可夺（无论持有多久）；unknown（无法判定）不接管——
    证据在锁件内，判据在进程状态（W3 反例消费）。"""
    try:
        st = os.stat(lp)
    except FileNotFoundError:
        return
    pid = 0
    try:
        with open(lp, encoding="utf-8", errors="ignore") as f:
            for line in f:
                if line.startswith("holder_pid="):
                    pid = int(line.split("=", 1)[1].strip() or 0)
                    break
    except Exception:
        return
    del st  # 不再用 mtime 判接管（age 分支已按 W3 反例删除）
    if pid and _pid_status(pid) == "dead":
        try:
            os.remove(lp)
        except FileNotFoundError:
            pass


# ── 读 / 原子写 ──────────────────────────────────────────────────────────

def read_rows(csv_path: str = REGISTRY_CSV):
    """读登记表（不存在返回空列表；utf-8-sig 兼容既有 BOM 口径）。
    原子替换保证读方要么见旧完整版要么见新完整版，无需读锁。"""
    if not os.path.exists(csv_path):
        return []
    with open(csv_path, "r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_rows_atomic(rows, csv_path: str = REGISTRY_CSV) -> None:
    """临时件写入→flush→读回校验→os.replace 原子替换。

    校验失败/写失败一律删除临时件并抛异常——原文件保持原样（不截空）。
    调用方须已持 locked()（本函数不重复加锁，保持组合自由）。
    """
    tmp = csv_path + ".tmp-tx"
    try:
        with open(tmp, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
            f.flush()
            os.fsync(f.fileno())
        # 读回校验：行数一致且可解析（写坏了不替换）
        with open(tmp, "r", newline="", encoding="utf-8-sig") as f:
            back = list(csv.DictReader(f))
        if len(back) != len(rows):
            raise IOError(f"原子写校验失败：读回 {len(back)} 行 ≠ 预期 {len(rows)} 行")
        os.replace(tmp, csv_path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def next_session_number(rows, participant_id: str) -> str:
    """该受试者下一个 S 序号（跨日期递增；与 console_server 旧实现同源口径）。
    必须在 locked() 临界区内用锁内新读 rows 调用（锁外调用=编号复用反例）。"""
    max_n = 0
    for row in rows:
        sid = row.get("session_id", "")
        if f"-{participant_id}-S" in sid:
            try:
                max_n = max(max_n, int(sid.split("-S")[-1]))
            except (ValueError, AttributeError):
                pass
    return f"S{max_n + 1:02d}"


# ── 两写方的临界区操作（写时锁内重读合并）───────────────────────────────

def preregister_locked(participant: str, session_type: str, date: str,
                       csv_path: str = REGISTRY_CSV) -> str:
    """预登记：锁内 读最新表→分配 S 号→查重→append→原子写。返回 session_id。
    Zen-ID 已存在即抛 ValueError（永不复用，不覆盖不回退）。"""
    lp = lock_path_for(csv_path)
    with locked(purpose="preregister", lock_path=lp):
        rows = read_rows(csv_path)               # 锁内最新表（非调用方旧快照）
        date_compact = date.replace("-", "")
        s_num = next_session_number(rows, participant)
        sid = f"ZEN-{date_compact}-{participant}-{s_num}"
        if any(r.get("session_id") == sid for r in rows):
            raise ValueError(f"{sid} 已在登记表，Zen-ID 永不复用")
        rows.append({"session_id": sid, "participant_id": participant,
                     "date": date, "session_type": session_type,
                     "duration_seconds": "", "status": "planned",
                     "manifest_path": ""})
        write_rows_atomic(rows, csv_path)
        return sid


def ingest_backfill_locked(session_id: str, duration_seconds: int,
                           final_status: str, manifest_rel: str,
                           csv_path: str = REGISTRY_CSV) -> None:
    """入库回填（--sid 预登记匹配模式）：锁内重读，找到该行更新三列。
    行不存在抛 LookupError；状态非 planned 抛 ValueError（校验口径与
    ingest_session.py 既有预登记校验一致，不在此放宽）。"""
    lp = lock_path_for(csv_path)
    with locked(purpose="ingest_backfill", lock_path=lp):
        rows = read_rows(csv_path)
        hit = None
        for r in rows:
            if r.get("session_id") == session_id:
                hit = r
                break
        if hit is None:
            raise LookupError(f"{session_id} 不在登记表")
        if hit.get("status") != "planned":
            raise ValueError(f"{session_id} 状态为 {hit.get('status')}（应为 planned）")
        hit["duration_seconds"] = str(duration_seconds)
        hit["status"] = final_status
        hit["manifest_path"] = manifest_rel
        write_rows_atomic(rows, csv_path)


def ingest_append_locked(row: dict, csv_path: str = REGISTRY_CSV) -> None:
    """补登记模式：锁内重读，按 Zen-ID 查重后 append（永不复用）。
    已存在即抛 ValueError。row 缺列如实留空（write_rows_atomic ignore 兜底）。"""
    lp = lock_path_for(csv_path)
    sid = row.get("session_id", "")
    with locked(purpose="ingest_append", lock_path=lp):
        rows = read_rows(csv_path)
        if any(r.get("session_id") == sid for r in rows):
            raise ValueError(f"{sid} 已在登记表，Zen-ID 永不复用")
        rows.append({k: row.get(k, "") for k in FIELDNAMES})
        write_rows_atomic(rows, csv_path)
