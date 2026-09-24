# -*- coding: utf-8 -*-
"""P1a 会话契约最小闭环：session_manifest.json + session_events.jsonl。

设计稿：`01_项目管理/20260918_P1统一会话数据契约设计_Session中心_讨论稿_v1.md`
- P1 指针不复制：manifest 只含定位/追溯/指针，不含数据本体；
- P2 追加不改写：事件流只追加（P1a 阶段在采集端一次写成，P1b 起随会话逐条追加）；
- P7 Session 最小主义：manifest 顶层字段白名单即机制（出现白名单外字段＝校验失败，防膨胀）；
- 契约是附属物：任何写契约的失败都不得中断数据保存主流程（调用方一律容错）。

本模块不依赖 numpy 之外的第三方库；供 muse_local_server / console_server /
closedloop_experiment / ingest_session 共用（红线5：单一实现）。
"""
import json
import os
from datetime import datetime

CONTRACT_VERSION = "1.0"
MANIFEST_SUFFIX = ".session_manifest.json"
EVENTS_SUFFIX = ".session_events.jsonl"

# P7 白名单：manifest 顶层只允许这三类字段（定位／追溯／指针）
_MANIFEST_ALLOWED_KEYS = {
    "schema_version", "session_id", "participant_id", "scene", "practice_id",
    "consent_version", "protocol", "files", "device", "signal_chain",
    "software", "config_snapshot", "qc", "labels",
}


def _now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def manifest_path_for(npz_path):
    """采集端暂存期：manifest 与 npz 同名（同目录多会话不互踩）。"""
    return os.path.splitext(npz_path)[0] + MANIFEST_SUFFIX


def events_path_for(npz_path):
    return os.path.splitext(npz_path)[0] + EVENTS_SUFFIX


def _build_manifest(session_id, participant_id, scene, meta, report_path,
                    consent_version="", practice_id="", protocol=""):
    return {
        "schema_version": CONTRACT_VERSION,
        "session_id": session_id,        # 暂存期为 local_* 名；入库定稿时改为 Zen-ID
        "participant_id": participant_id or "",
        "scene": scene or "",
        "practice_id": practice_id,      # 待裁 §八-11：Practice 主键可选字段
        "consent_version": consent_version,  # 待裁 §八-3：暂存空，定稿如实标缺失
        "protocol": protocol,
        "files": {
            "eeg_npz": os.path.basename(str(session_id))
                       + ("" if str(session_id).endswith(".npz") else ".npz"),
            "report_html": os.path.basename(report_path) if report_path else "",
        },
        "device": {
            "model": str(meta.get("device") or meta.get("device_model") or ""),
            "sfreq": float(meta.get("sfreq") or 0.0),
            "channels": list(meta.get("channels") or []),
        },
        "signal_chain": meta.get("signal_chain") or {},
        "software": {"session_contract": CONTRACT_VERSION},
        "config_snapshot": None,
        "qc": None,                      # qc_done 走事件流；阈值版本由调用方补
        "labels": list(meta.get("zx_phase") or []) if meta.get("zx_phase") else [],
    }


def write_manifest(npz_path, meta, report_path, session_id=None,
                   participant_id="", scene="", consent_version="",
                   practice_id="", protocol=""):
    """采集端暂存期落盘 manifest。返回路径；失败抛异常（调用方容错）。"""
    sid = session_id or os.path.splitext(os.path.basename(npz_path))[0]
    m = _build_manifest(sid, participant_id, scene, meta, report_path,
                        consent_version=consent_version,
                        practice_id=practice_id, protocol=protocol)
    errs = validate_manifest_dict(m, base_dir=os.path.dirname(npz_path))
    if errs:
        raise ValueError("manifest 校验失败: " + "；".join(errs))
    p = manifest_path_for(npz_path)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)
    return p


def make_event(type_, actor, kind, payload=None, note="", ts=None):
    """ts 可选：补记**过去时刻**的事件（如采集期手打 marker 在会话结束时才落盘，
    须用按下那一刻的挂钟时间，而非写盘时刻）。缺省仍取当前时刻（旧行为不变）。"""
    return {"schema_version": CONTRACT_VERSION, "ts": ts or _now(),
            "type": type_, "actor": actor, "kind": kind,
            "payload": payload or {}, "note": note}


def init_events(npz_path, events):
    """P1a：采集端一次写成事件文件（created/started/saved 由调用方组装）。"""
    p = events_path_for(npz_path)
    with open(p, "w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    return p


def append_event(events_path, type_, actor, kind, payload=None, note="", ts=None):
    """只追加（P2）。文件不存在则跳过并返回 False（契约是附属物）。"""
    if not events_path or not os.path.exists(events_path):
        return False
    with open(events_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(make_event(type_, actor, kind, payload, note, ts=ts),
                           ensure_ascii=False) + "\n")
    return True


# ── 校验（P7 白名单机制化）─────────────────────────────────────────────────

def validate_manifest_dict(m, base_dir=None):
    errs = []
    if not isinstance(m, dict):
        return ["manifest 非 JSON 对象"]
    if m.get("schema_version") != CONTRACT_VERSION:
        errs.append(f"schema_version={m.get('schema_version')} 应为 {CONTRACT_VERSION}")
    if not m.get("session_id"):
        errs.append("缺 session_id")
    extra = sorted(set(m) - _MANIFEST_ALLOWED_KEYS)
    if extra:
        errs.append(f"P7 白名单外字段: {extra}（分析/解释/知识结果不得进 manifest）")
    if base_dir:
        files = m.get("files") or {}
        for key in ("eeg_npz", "report_html"):
            v = files.get(key)
            if v and not os.path.exists(os.path.join(base_dir, v)):
                errs.append(f"files.{key} 指针不存在: {v}")
    return errs


def validate_contract_files(base_dir, require_events=False):
    """入库前校验（ingest 用）。返回错误列表（空＝通过）。"""
    errs = []
    mp = os.path.join(base_dir, "session_manifest.json")
    ep = os.path.join(base_dir, "session_events.jsonl")
    if not os.path.exists(mp):
        errs.append("缺 session_manifest.json")
        return errs
    try:
        with open(mp, encoding="utf-8") as f:
            m = json.load(f)
    except Exception as ex:
        return [f"manifest 不可解析: {type(ex).__name__}"]
    errs.extend(validate_manifest_dict(m, base_dir=base_dir))
    if require_events and not os.path.exists(ep):
        errs.append("缺 session_events.jsonl")
    if os.path.exists(ep):
        with open(ep, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    json.loads(line)
                except Exception as ex:
                    errs.append(f"events 第 {i} 行不可解析: {type(ex).__name__}")
                    break
    return errs


def carry_contract(npz_path, dest_dir, zen_id, operator="",
                   dest_npz_name="eeg_raw.npz", dest_report_name="report.html"):
    """入库定稿：把采集端两份契约搬到归档目录并定稿（session_id 改 Zen-ID、
    文件指针改为归档名、追加 ingested 事件）。源契约缺失则返回 carried=False
    （老会话，如实跳过）。返回 {"carried": bool, "errors": [..]}。
    """
    src_m = manifest_path_for(npz_path)
    src_e = events_path_for(npz_path)
    if not os.path.exists(src_m):
        return {"carried": False, "errors": []}
    errs = []
    try:
        with open(src_m, encoding="utf-8") as f:
            m = json.load(f)
    except Exception as ex:
        return {"carried": False, "errors": [f"manifest 不可解析: {type(ex).__name__}"]}
    errs.extend(validate_manifest_dict(m, base_dir=os.path.dirname(npz_path)))
    # 定稿：session_id 换为 Zen-ID；文件指针换归档名；consent 空则如实标缺失
    m["session_id"] = zen_id
    m["files"]["eeg_npz"] = dest_npz_name
    if m["files"].get("report_html") and os.path.exists(
            os.path.join(dest_dir, dest_report_name)):
        m["files"]["report_html"] = dest_report_name
    elif not os.path.exists(os.path.join(dest_dir, dest_report_name)):
        m["files"]["report_html"] = ""
    if not m.get("consent_version"):
        m["consent_version"] = "缺失（采集端未记录，待补登记）"
    errs.extend(validate_manifest_dict(m, base_dir=dest_dir))
    if errs:
        return {"carried": False, "errors": errs}
    os.makedirs(dest_dir, exist_ok=True)
    with open(os.path.join(dest_dir, "session_manifest.json"), "w",
              encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)
    if os.path.exists(src_e):
        shutil_copy(src_e, os.path.join(dest_dir, "session_events.jsonl"))
        append_event(os.path.join(dest_dir, "session_events.jsonl"),
                     "ingested", operator or "operator", "ruled",
                     {"session_id": zen_id, "scene": m.get("scene", "")},
                     "归档定稿：session_id 由暂存名改为 Zen-ID")
    return {"carried": True, "errors": []}


def shutil_copy(src, dst):
    import shutil
    shutil.copy2(src, dst)


# ── 自测（含反例检验：篡改必须被抓住）────────────────────────────────────

def _selftest():
    import os as _os
    import numpy as np
    # 沙箱限制：系统临时目录内建子文件可能被拒（本机实测），
    # 自测临时目录落在脚本所在工作树内（_analysis_tmp 已被 .gitignore 排除）
    root = _os.path.dirname(_os.path.abspath(__file__))
    tmp = _os.path.join(root, "_analysis_tmp",
                        "contract_selftest_" + _os.urandom(4).hex())
    _os.makedirs(tmp, exist_ok=False)
    fails = []
    try:
        npz = os.path.join(tmp, "local_20260918_120000.npz")
        meta = {"timestamp": "2026-09-18T12:00:00", "sfreq": 256.0,
                "channels": ["TP9", "AF7", "AF8", "TP10"], "device": "muse",
                "samples": 512, "duration": 2.0, "scene": "monitor",
                "signal_chain": {"chain_tag": "v12_bp_1_40",
                                 "pre_filter_available": True},
                "zx_phase": ["入", "照"]}
        np.savez(npz, eeg=np.zeros((512, 4)), timestamps=np.arange(512) / 256.0,
                 meta=meta)
        rep = os.path.join(tmp, "local_20260918_120000.report.html")
        open(rep, "w", encoding="utf-8").write("<html></html>")
        mp = write_manifest(npz, meta, rep, participant_id="P001",
                            scene="monitor")
        ep = init_events(npz, [make_event("created", "system", "ruled"),
                               make_event("started", "operator", "measured",
                                          {"mode": "模拟"}),
                               make_event("saved", "system", "measured")])
        append_event(ep, "qc_done", "system", "derived",
                     {"clean_ratio": 0.9})
        append_event(ep, "closed", "operator", "measured")
        if not os.path.exists(mp) or not os.path.exists(ep):
            fails.append("契约文件未落盘")
        # 事件行可解析
        n = sum(1 for line in open(ep, encoding="utf-8") if line.strip())
        if n != 5:
            fails.append(f"事件数 {n} != 5")
        # 反例检验 1：白名单外字段必须被拒
        m = json.load(open(mp, encoding="utf-8"))
        m["analysis_result"] = {"alpha": 1.0}
        if not validate_manifest_dict(m, base_dir=tmp):
            fails.append("反例1 未抓住白名单外字段")
        # 反例检验 2：schema_version 篡改必须被拒
        m2 = json.load(open(mp, encoding="utf-8"))
        m2["schema_version"] = "0.9"
        if not validate_manifest_dict(m2, base_dir=tmp):
            fails.append("反例2 未抓住 schema_version 篡改")
        # 反例检验 3：文件指针被篡改必须被拒
        m3 = json.load(open(mp, encoding="utf-8"))
        m3["files"]["eeg_npz"] = "不存在.npz"
        if not validate_manifest_dict(m3, base_dir=tmp):
            fails.append("反例3 未抓住指针篡改")
        # carry：定稿改名 + ingested 事件追加（按真实调用次序：ingest 先落
        # eeg_raw.npz/report.html 到归档目录，再 carry 契约）
        dest = os.path.join(tmp, "ZEN-20260918-P001-S99")
        os.makedirs(dest, exist_ok=True)
        import shutil as _s2
        _s2.copy2(npz, os.path.join(dest, "eeg_raw.npz"))
        _s2.copy2(rep, os.path.join(dest, "report.html"))
        res = carry_contract(npz, dest, "ZEN-20260918-P001-S99",
                             operator="tiand")
        if not res["carried"] or res["errors"]:
            fails.append(f"carry 失败: {res}")
        mf = json.load(open(os.path.join(dest, "session_manifest.json"),
                            encoding="utf-8"))
        if mf["session_id"] != "ZEN-20260918-P001-S99":
            fails.append("carry 未改名 session_id")
        if mf["consent_version"] != "缺失（采集端未记录，待补登记）":
            fails.append("carry 未补 consent 缺失标注")
        n2 = sum(1 for line in open(os.path.join(dest, "session_events.jsonl"),
                                    encoding="utf-8") if line.strip())
        if n2 != 6:
            fails.append(f"carry 后事件数 {n2} != 6（应含 ingested）")
        errs = validate_contract_files(dest, require_events=True)
        if errs:
            fails.append(f"入库后校验未过: {errs}")
    finally:
        import shutil as _s
        _s.rmtree(tmp, ignore_errors=True)
    if fails:
        for x in fails:
            print("FAIL:", x)
        return 1
    print("PASS: session_contract 自测通过（含 3 条反例检验 + carry 定稿 + 入库校验）")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_selftest())
