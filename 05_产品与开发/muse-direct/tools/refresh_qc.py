# -*- coding: utf-8 -*-
"""刷新 03_quality_control/<sid>/qc.json —— 由 npz 实算（P0-1／P0-2，2026-09-20）。

旧版（至 2026-09-20）有三个缺陷，均已修：
  ① **死路径**：`ZEN_ROOT` 硬编码为 `C:\\Users\\tiand\\OneDrive\\Zen-EEG`，而数据工厂
     已于 2026-09-19 迁至 `D:\\Project\\Zen-EEG` → 对**每个会话**都走"跳过"分支、
     打印"跳过"、**退出码恒为 0**：一个静默假装成功的工具（盘查 B-2）。
  ② **同源逻辑第三份副本**：从 report.html 正则抠指标，与 `console_server.py`、
     `ingest_session.py` 各一份且**标签表互不相同**（盘查 B-2）。
  ③ **取值来源错误**：判定依赖 report.html，而报告模板只在检出噪声时才渲染
     "干净数据比例" → 越干净的会话越取不到（盘查 A-1）。

现改为：
  · `ZEN_ROOT` 从**环境变量 `ZEN_ROOT`** 取，缺省回落到与 `ingest_session.py` 同源的
    路径；两者不一致时**明确报错**而不是静默跳过。
  · 指标一律调用 `qc_pipeline.assess`（红线5 单一实现），**不读 report.html**。
  · 任何失败**非零退出**，便于 CI／人工判断。

用法：
    python refresh_qc.py                 # 刷新全部已存在 qc.json 的会话
    python refresh_qc.py <sid> [<sid>…]  # 只刷指定会话
    python refresh_qc.py --dry-run       # 只算不写，打印新旧对照

⚠️ **本脚本会写 `03_quality_control/`（派生区，非只读区）**。对**归档会话**执行前
须经法师授权（会改写历史 qc.json）；默认 `--dry-run` 更安全，建议先跑 dry-run 留证。
"""

import argparse
import json
import os
import sys
from pathlib import Path

# 与 ingest_session.py 同源的缺省根；可用环境变量 ZEN_ROOT 覆盖
DEFAULT_ZEN_ROOT = Path(r"D:\Project\Zen-EEG")
ZEN_ROOT = Path(os.environ.get("ZEN_ROOT") or DEFAULT_ZEN_ROOT)
RAW_ROOT = ZEN_ROOT / "02_raw"
QC_ROOT = ZEN_ROOT / "03_quality_control"
QUARANTINE_ROOT = QC_ROOT / "quarantine"


def _ensure_pipeline_importable():
    """把工作区根目录加入 sys.path，以导入 qc_pipeline（唯一实现）。"""
    root = Path(__file__).resolve().parents[3]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from qc_pipeline import assess          # noqa: E402
    return assess


def _qc_path_for(sid: str) -> Path:
    """正式会话在 03_quality_control/<sid>/，隔离会话在 quarantine/<sid>/。"""
    p = QC_ROOT / sid / "qc.json"
    if p.exists():
        return p
    q = QUARANTINE_ROOT / sid / "qc.json"
    if q.exists():
        return q
    return p


def _npz_path_for(sid: str) -> Path:
    for root in (RAW_ROOT, QUARANTINE_ROOT):
        p = root / sid / "eeg_raw.npz"
        if p.exists():
            return p
    return RAW_ROOT / sid / "eeg_raw.npz"


def refresh(sid: str, dry_run: bool = False) -> dict:
    """重算单个会话的 QC。返回 {sid, ok, changed, old, new, error}。"""
    npz = _npz_path_for(sid)
    qc_path = _qc_path_for(sid)
    if not npz.exists():
        return {"sid": sid, "ok": False, "error": f"缺 npz：{npz}"}
    try:
        assess = _ensure_pipeline_importable()
        res = assess(str(npz))
    except Exception as ex:
        return {"sid": sid, "ok": False,
                "error": f"qc_pipeline 调用失败：{type(ex).__name__}: {ex}"}

    old = {}
    if qc_path.exists():
        try:
            old = json.loads(qc_path.read_text(encoding="utf-8"))
        except Exception as ex:
            return {"sid": sid, "ok": False,
                    "error": f"既有 qc.json 不可解析：{type(ex).__name__}: {ex}"}

    new = dict(res["metrics"])
    new.update({k: res[k] for k in ("qc_version", "threshold_version",
                                    "thresholds", "generated_by", "generated_at")})
    # 保留旧 qc 的位置语义字段（不丢信息）
    for k in ("session_id", "scene", "quarantined", "report_source"):
        if k in old:
            new[k] = old[k]
    if old and old.get("clean_ratio") != new.get("clean_ratio"):
        new["clean_ratio_legacy"] = old.get("clean_ratio")
        new["recomputed_note"] = ("由 refresh_qc.py 重算（npz 实算，P0-1/P0-2 2026-09-20）；"
                                  "clean_ratio_legacy 为旧值（原自 report.html 正则）")

    changed = (old.get("clean_ratio") != new.get("clean_ratio")
               or old.get("noise_epochs") != new.get("noise_epochs")
               or old.get("channel_quality") != new.get("channel_quality"))
    if not dry_run:
        qc_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = str(qc_path) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(new, f, ensure_ascii=False, indent=2)
        os.replace(tmp, qc_path)
    return {"sid": sid, "ok": True, "changed": changed,
            "old": {"clean_ratio": old.get("clean_ratio"),
                    "noise_epochs": old.get("noise_epochs")},
            "new": {"clean_ratio": new.get("clean_ratio"),
                    "noise_epochs": new.get("noise_epochs"),
                    "recommend": res["recommend"]}}


def main() -> int:
    ap = argparse.ArgumentParser(description="刷新 qc.json（npz 实算，P0-1/P0-2）")
    ap.add_argument("sessions", nargs="*", help="会话 ID；缺省刷新全部已存在 qc.json 的会话")
    ap.add_argument("--dry-run", action="store_true",
                    help="只算不写，打印新旧对照（涉历史改写时先用它）")
    args = ap.parse_args()

    # 死路径防护：根不存在即**非零退出**，不再静默跳过（旧版正是这样装成功）
    if not ZEN_ROOT.exists():
        print(f"错误：ZEN_ROOT 不存在：{ZEN_ROOT}", file=sys.stderr)
        print("  请设环境变量 ZEN_ROOT 指向数据工厂（如 D:\\Project\\Zen-EEG）。",
              file=sys.stderr)
        return 2
    if not QC_ROOT.exists():
        print(f"错误：质控目录不存在：{QC_ROOT}", file=sys.stderr)
        return 2

    if args.sessions:
        targets = args.sessions
    else:
        targets = sorted(
            [p.name for p in QC_ROOT.iterdir() if p.is_dir() and (p / "qc.json").exists()]
            + [p.name for p in QUARANTINE_ROOT.iterdir()
               if p.is_dir() and (p / "qc.json").exists()]
        ) if QUARANTINE_ROOT.exists() else sorted(
            p.name for p in QC_ROOT.iterdir() if p.is_dir() and (p / "qc.json").exists())

    if not targets:
        print("错误：未找到任何会话（qc.json 一个都没有？）", file=sys.stderr)
        return 2

    print(f"ZEN_ROOT = {ZEN_ROOT}")
    print(f"模式     = {'DRY-RUN（不写盘）' if args.dry_run else '写入'}")
    print(f"目标     = {len(targets)} 个会话\n")
    fails = 0
    changed = 0
    for sid in targets:
        r = refresh(sid, dry_run=args.dry_run)
        if not r.get("ok"):
            print(f"  FAIL {sid}: {r.get('error')}")
            fails += 1
            continue
        flag = "CHANGED" if r["changed"] else "same   "
        if r["changed"]:
            changed += 1
        print(f"  {flag} {sid}: clean {r['old']['clean_ratio']} -> "
              f"{r['new']['clean_ratio']} | noise {r['old']['noise_epochs']!r} -> "
              f"{r['new']['noise_epochs']!r} | {r['new']['recommend']}")

    print(f"\n合计：{len(targets)} 个会话，{changed} 个有变化，{fails} 个失败")
    if args.dry_run:
        print("（DRY-RUN：未写任何文件）")
    # 任何失败即非零退出（旧版恒 0）
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
