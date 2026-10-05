#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
20261006_W1_congci_brain_endpoint_test.py — 批 C2 轻量自测：窄读端点
=========================================================================

施工正本《20261005_驾驶舱×从此接入方案稿_v2.md》§三（L2 窄读）＋契约 v0.3：
  路径白名单（session_key 仅字母数字._-，≤128，禁路径分隔）／无遍历（档案
  一律索引行解析，禁借 /api/file）／三态（no_record 失联、no_file 无文件、
  stale＋非终态明示）／trace 并入／归档路径兜底（hash 键行按 npz 路径匹配）。

运行环境：8777 解释器（Python312，有 fastapi；不经 cadence import——测试
  只测端点，不动脑）。前置：先跑 _analysis_tmp/_c2_setup.py（cadence 可用
  解释器）装配 tmp 夹具（含 committed 的 ZEN-20261006-P001-S99），本件读
  _c2_env.json 设环境变量后直调 handler。

测试件头（契约 v0.2 纪律）：运行时打印源码 sha16＋被测函数名＋时刻。

纪律：全程 tmp 夹具（env 指向），**不触真实脑目录/登记表/03_qc**；退出码 0=全过。
"""
import hashlib
import json
import os
import sys
import time

sys.path.insert(0, r"D:\Project\zhiguanAI")

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


def main() -> int:
    env = json.load(open(r"D:\Project\zhiguanAI\_analysis_tmp\_c2_env.json",
                         encoding="utf-8"))
    os.environ["CONGCI_PIPELINE_ROOT"] = env["congci_root"]
    os.environ["CONGCI_PIPELINE_ZEN_ROOT"] = env["zen_root"]
    SK = env["sk"]

    # 测试件头：源码 hash＋函数＋时刻（契约 v0.2 纪律）
    srcs = {p: sha16(os.path.join(r"D:\Project\zhiguanAI", p))
            for p in ("console_server.py", "congci_pipeline.py",
                      "zhiguan_cadence_bridge.py")}
    print(f"[header] 2026-10-06 {time.strftime('%H:%M:%S')} src_sha16={srcs}")

    import console_server as cs
    from fastapi import HTTPException

    def call(key, include_trace=True):
        return cs.get_congci_brain_record(key, include_trace=include_trace)

    def call_err(key, include_trace=True):
        try:
            call(key, include_trace=include_trace)
            return None
        except HTTPException as e:
            return e

    try:
        # ── 1. 有效读：committed 行 + record + trace 并入 ──
        d = call(SK)
        assert d["session_key"] == SK, f"回显 key 不一致：{d['session_key']}"
        assert d["status"] == "committed" and d["stale"] is False, \
            f"状态/stale 异常：{d}"
        assert d["brain_version"] == env["brain_version"], "brain_version 不符"
        assert d["record"].get("summary", {}).get("epochs") == 120, "record 摘要缺 epochs"
        assert d["trace"] and d["trace"]["trace"] and len(d["trace"]["trace"]) >= 100, \
            "trace 未并入或过短"
        assert d["trace_missing"] is False
        ok("有效读：committed＋record＋trace 并入＋回显一致")

        # ── 2. include_trace=False 不返回 trace ──
        d2 = call(SK, include_trace=False)
        assert "trace" not in d2, "include_trace=False 仍返回 trace"
        assert d2["record"]["summary"]["epochs"] == 120, "record 仍应在"
        ok("include_trace=False：只读 record 不随带 trace")

        # ── 3. bad_key：路径分隔/超长/空 ──
        for bad in ("../../etc/passwd", "a/b", "a\\b", "a" * 129, ""):
            e = call_err(bad)
            assert e is not None and e.status_code == 400, f"bad_key 未拒：{bad!r}"
            assert e.detail.get("error") == "bad_key", f"bad_key 码异常：{bad!r}"
        ok("路径白名单：/、\\、..、超长、空 全拒 400 bad_key（禁遍历）")

        # ── 4. no_record：未入队会话（S98 已装配未入队）──
        e = call_err("ZEN-20261006-P001-S98")
        assert e is not None and e.status_code == 404, "S98 应 no_record"
        assert e.detail.get("error") == "no_record", f"错误码异常：{e.detail}"
        ok("no_record（失联）：未入队会话 404，卡内可明示")

        # ── 5. no_file：索引有行但档案缺失 ──
        import congci_pipeline as cp
        with cp.registry_tx.locked(purpose="test-no_file",
                                   lock_path=cp.index_lock_path()):
            doc = cp._read_index()
            doc["rows"].append({"unit_id": "u-nofile",
                                "session_key": "ZEN-20261006-P001-S97",
                                "source_hash16": "0" * 16,
                                "algo_version": cp._algo_version(),
                                "lineage_id": cp.LINEAGE_ID,
                                "brain_base_version": 0,
                                "status": "committed",
                                "npz_path": os.path.join(env["zen_root"],
                                                         "02_raw",
                                                         "ZEN-20261006-P001-S97",
                                                         "eeg_raw.npz"),
                                "queued_at": "2026-10-06T00:00:00+08:00"})
            cp._write_index(doc)
        e = call_err("ZEN-20261006-P001-S97")
        assert e is not None and e.status_code == 404, "S97 应 no_file"
        assert e.detail.get("error") == "no_file", f"错误码异常：{e.detail}"
        ok("no_file（无文件）：索引有行档案缺失 404，卡内可明示")

        # ── 6. 归档路径兜底：hash 键行按 npz 路径匹配（C1 未入库入队）──
        sk98 = "ZEN-20261006-P001-S98"
        udir = cp.unit_dir("u-fallback")
        os.makedirs(udir, exist_ok=True)
        with open(cp._record_path("u-fallback"), "w", encoding="utf-8") as f:
            json.dump({"schema_version": cp.INDEX_SCHEMA, "unit_id": "u-fallback",
                       "status": "committed", "session_key": "fabricated-hash",
                       "summary": {"epochs": 120, "npz": "x"},
                       "trace_path": os.path.join(udir, "trace.json")}, f)
        with open(os.path.join(udir, "trace.json"), "w", encoding="utf-8") as f:
            json.dump({"summary": {"epochs": 120},
                       "trace": [{"t": i + 1, "action": 0, "beat": 10.0,
                                  "volume": 0.25, "residual": 0.0,
                                  "in_state": False, "z_at": 0.0}
                                 for i in range(120)]}, f)
        with cp.registry_tx.locked(purpose="test-fallback",
                                   lock_path=cp.index_lock_path()):
            doc = cp._read_index()
            doc["rows"].append({"unit_id": "u-fallback",
                                "session_key": "fabricated-hash",
                                "source_hash16": "1" * 16,
                                "algo_version": cp._algo_version(),
                                "lineage_id": cp.LINEAGE_ID,
                                "brain_base_version": 99,
                                "result_brain_version": 100,
                                "status": "committed",
                                "npz_path": os.path.join(env["zen_root"],
                                                         "02_raw", sk98,
                                                         "eeg_raw.npz"),
                                "queued_at": "2026-10-06T00:00:00+08:00"})
            cp._write_index(doc)
        d = call(sk98)
        assert d["session_key"] == sk98, f"兜底回显 key 异常：{d['session_key']}"
        assert d["unit_id"] == "u-fallback", "兜底未命中 fallback 行"
        assert d["brain_version"] == 100, "兜底行版本异常"
        assert d["trace"]["trace"], "兜底行 trace 未并入"
        ok("归档路径兜底：hash 键行按 npz 路径匹配命中，回显请求 key")

        # ── 7. stale：算法版本≠当前 → stale 标记 ──
        import congci_pipeline as cp2
        cp2.ALGO_VERSION = "congci-feed-9.9.9-test"
        d = call(SK)
        assert d["stale"] is True, f"stale 未标记：{d.get('stale')}"
        assert d["algo_version"] != d["current_algo_version"]
        cp2.ALGO_VERSION = None
        ok("stale：旧算法产物如实标记（卡内明示不判好坏）")

        # ── 8. /cadence-mandala 专用路由：单文件 FileResponse ──
        fr = cs.get_cadence_mandala()
        assert os.path.exists(fr.path) and fr.path.endswith("cadence_mandala.html"), \
            f"专用路由异常：{fr.path}"
        ok("/cadence-mandala：iframe 来源白名单单文件路由在位")

        print(f"[selftest OK] {PASS} checks passed（批 C2 端点轻量自测）")
        return 0
    finally:
        # 自清理：移除本件装配的测试行（u-nofile／u-fallback），保证夹具可重跑幂等
        import congci_pipeline as _cp
        try:
            with _cp.registry_tx.locked(purpose="test-cleanup",
                                        lock_path=_cp.index_lock_path()):
                _doc = _cp._read_index()
                _before = len(_doc["rows"])
                _doc["rows"] = [r for r in _doc["rows"]
                                if r.get("unit_id") not in ("u-nofile", "u-fallback")]
                if len(_doc["rows"]) != _before:
                    _cp._write_index(_doc)
        except Exception:
            pass
        _cp.ALGO_VERSION = None
        os.environ.pop("CONGCI_PIPELINE_ROOT", None)
        os.environ.pop("CONGCI_PIPELINE_ZEN_ROOT", None)


if __name__ == "__main__":
    sys.exit(main())
