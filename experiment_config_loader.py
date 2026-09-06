#!/usr/bin/env python3
"""
闭环实验系统 —— 配置管理

职责：
  1. 读取 experiment_config.json（集中配置）
  2. 校验关键参数的合理范围，越界直接报错而不是带病运行
  3. 支持命令行参数覆盖配置文件（命令行优先）
  4. 实验开始时把实际生效的配置快照保存进日志目录，保证可复现

用法:
    from experiment_config_loader import load_experiment_config, save_snapshot
    cfg = load_experiment_config(cli_overrides={"baseline_seconds": 180})
    save_snapshot(cfg, experiments_dir, tag)
"""

import os
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "experiment_config.json")

DEFAULT_CONFIG = {
    "experiment": {
        "baseline_seconds": 120,
        "duration_seconds": 600,
        "tag": "closedloop",
        "device_address": None,
    },
    "controller": {
        "target_band": "alpha",
        "reward_threshold_db": 1.0,
        "vol_max": 0.35,
        "vol_idle": 0.05,
        "vol_smooth_step": 0.05,
        "reward_detect_ratio": 0.7,
        "beat_default": 10.0,
        "beat_drowsy": 12.0,
        "beat_tense": 8.0,
        "beat_min": 6.0,
        "beat_max": 14.0,
        "beat_step": 0.5,
        "tb_high": 4.0,
        "tb_low": 1.5,
        "maintain_band_db": -0.5,
    },
    "audio": {
        "carrier_hz": 220.0,
    },
    "device": {
        "sampling_rate": 256,
        "decision_interval_seconds": 2.0,
    },
}

# 关键参数合法范围（越界即报错）
RANGE_CHECKS = [
    ("experiment", "baseline_seconds", 30, 3600),
    ("experiment", "duration_seconds", 120, 7200),
    ("controller", "reward_threshold_db", 0.2, 10.0),
    ("controller", "vol_max", 0.05, 0.8),
    ("controller", "vol_idle", 0.0, 0.3),
    ("controller", "beat_min", 1.0, 20.0),
    ("controller", "beat_max", 4.0, 30.0),
    ("controller", "beat_step", 0.1, 5.0),
    ("audio", "carrier_hz", 100.0, 1000.0),
    ("device", "decision_interval_seconds", 0.5, 10.0),
]


def load_experiment_config(path=CONFIG_PATH, cli_overrides=None):
    """
    读取配置文件并与内置默认值合并；cli_overrides（dict）中的键覆盖
    experiment 段的同名项（如 baseline_seconds / duration_seconds / tag）。
    """
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))  # 深拷贝

    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            user_cfg = json.load(f)
        for section, values in user_cfg.items():
            if section.startswith("_") or not isinstance(values, dict):
                continue
            # 段内以 _ 开头的键视为注释，跳过
            cleaned = {k: v for k, v in values.items() if not k.startswith("_")}
            cfg.setdefault(section, {}).update(cleaned)
    else:
        print(f"⚠️ 未找到配置文件 {path}，使用内置默认值")

    if cli_overrides:
        for key, val in cli_overrides.items():
            if val is not None:
                cfg["experiment"][key] = val

    validate_config(cfg)
    return cfg


def validate_config(cfg):
    """校验参数范围与逻辑一致性，发现问题立即抛错。"""
    errors = []
    for section, key, lo, hi in RANGE_CHECKS:
        val = cfg.get(section, {}).get(key)
        if val is None:
            continue
        try:
            val = float(val)
        except (TypeError, ValueError):
            errors.append(f"{section}.{key} 不是数字: {val!r}")
            continue
        if not (lo <= val <= hi):
            errors.append(f"{section}.{key}={val} 超出合理范围 [{lo}, {hi}]")

    c = cfg["controller"]
    if c["beat_min"] >= c["beat_max"]:
        errors.append("beat_min 必须小于 beat_max")
    if c["vol_idle"] >= c["vol_max"]:
        errors.append("vol_idle 必须小于 vol_max")
    if c["vol_smooth_step"] > c["vol_max"]:
        errors.append("vol_smooth_step 不应大于 vol_max")
    if not (c["beat_min"] <= c["beat_default"] <= c["beat_max"]):
        errors.append("beat_default 必须在 [beat_min, beat_max] 区间内")

    e = cfg["experiment"]
    if e["duration_seconds"] <= e["baseline_seconds"] + 60:
        errors.append("duration_seconds 需比 baseline_seconds 至少多 60 秒")

    if errors:
        raise ValueError("配置校验失败:\n  - " + "\n  - ".join(errors))


def save_snapshot(cfg, experiments_dir, tag="closedloop"):
    """把本次实验实际生效的配置保存到日志目录，返回文件路径。"""
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    snap_path = os.path.join(experiments_dir, f"{ts}_{tag}_config.json")
    with open(snap_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return snap_path


if __name__ == "__main__":
    cfg = load_experiment_config()
    print("✅ 配置加载并通过校验:")
    print(json.dumps(cfg, ensure_ascii=False, indent=2))

    # 校验越界检测
    bad = load_experiment_config.__wrapped__ if False else None
    try:
        import copy
        bad_cfg = copy.deepcopy(cfg)
        bad_cfg["controller"]["vol_max"] = 5.0
        validate_config(bad_cfg)
        print("❌ 越界校验未生效")
    except ValueError as ex:
        print(f"✅ 越界参数被正确拦截: {str(ex).splitlines()[0]}")
