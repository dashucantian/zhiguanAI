# -*- coding: utf-8 -*-
"""ZG-087 人读报告卡样张自检（W1 f7e223f6 独占，只读）。

⚠ 覆盖面声明（W3 复核 05:48）：本脚本**仅检查当前交付件里的三个样张**，
不是 assess 实跑、不是生产报告/UI 验收、更不是完整 QC 判定器——
rebuild_reasons 只重建干净度与通道两闸（:359/:399），**未含**时长闸（:343）、
丢包闸（:345）与单坏道降权分支（:389-395）；当前两例未触发不等于这些分支已核，
不得外推。

三轮整改（W3 复核 10-15 03:36）后口径：
  ① 常量实提取（import qc_pipeline）
  ② 字段驱动：逐样张用其 metrics.samples/sfreq/channels 构造合成数组
     实跑 _epochs 核 total_epochs；按 samples/duration/sfreq 重算
     effective_hz／packet_loss_rate；按 noise_epochs 字符串重算 clean_ratio。
     不再自造数据自证。
  ③ 展示层样张（_display_layer_only=true）只查展示口径，不冒充 assess 输出复算
  ④ 文案断言：撤回的绝对断言与旧错值不得回流正文

只读本件 md 与 qc_pipeline.py；不读写数据根、不装依赖、不提交。
运行末尾报告实际覆盖面。
"""
import json
import re
import sys

sys.path.insert(0, r"D:\Project\zhiguanAI")
import qc_pipeline as qp

MD = r"D:\Project\zhiguanAI\01_项目管理\信箱\engine\20261015-W1-f7e223f6-ZG087人读报告卡字段映射与合成样张_v1.md"

fails = []
oks = []
coverage = []


def check(name, cond, detail=""):
    (oks if cond else fails).append(f"{'PASS' if cond else 'FAIL'}  {name}  {detail}")


# ── ① 常量实提取 ────────────────────────────────────────────────────
check("MIN_CLEAN_RATIO==0.60", qp.MIN_CLEAN_RATIO == 0.60, f"实值={qp.MIN_CLEAN_RATIO}")
check("CH_FLAT_STD_UV==0.5", qp.CH_FLAT_STD_UV == 0.5, f"实值={qp.CH_FLAT_STD_UV}")
check("CH_RAIL_UV==1800", qp.CH_RAIL_UV == 1800.0, f"实值={qp.CH_RAIL_UV}")
check("CH_MAINS_RATIO==0.35", qp.CH_MAINS_RATIO == 0.35, f"实值={qp.CH_MAINS_RATIO}")
check("EPOCH_SECONDS==10", qp.EPOCH_SECONDS == 10.0, f"实值={qp.EPOCH_SECONDS}")
check("EPOCH_STEP==5", qp.EPOCH_STEP == 5.0, f"实值={qp.EPOCH_STEP}")
check("QC_VERSION=='1.1'", qp.QC_VERSION == "1.1", f"实值={qp.QC_VERSION}")
check("THRESHOLD_VERSION=='20261013'", qp.THRESHOLD_VERSION == "20261013",
      f"实值={qp.THRESHOLD_VERSION}")

# ── ② + ③ 逐样张字段驱动核验 ────────────────────────────────────────
import numpy as np

text = open(MD, encoding="utf-8").read()
blocks = re.findall(r"```json\s*(\{.*?\})\s*```", text, re.S)
check("md 含 3 个 json 样张", len(blocks) == 3, f"实抽={len(blocks)}")
samples = [json.loads(b) for b in blocks] if len(blocks) == 3 else []


def rebuild_reasons(clean_ratio, bad_names):
    """按 qc_pipeline.py:359/:399 同式重建 reasons（顺序同源码）。"""
    out = []
    if clean_ratio is not None and clean_ratio < qp.MIN_CLEAN_RATIO:
        out.append(f"干净数据 {clean_ratio:.0%} 低于下限 {qp.MIN_CLEAN_RATIO:.0%}")
    if bad_names:
        out.append(f"通道质量不合格：{'、'.join(bad_names)}")
    return out


for idx, s in enumerate(samples, 1):
    if s.get("_display_layer_only"):
        # 展示层样张：只查展示口径，不做 assess 复算
        coverage.append(f"S{idx}=展示层缺失输入示意（跳过 assess 复算）")
        check(f"S{idx} 带 _display_layer_only 标记", s.get("_display_layer_only") is True)
        check(f"S{idx} human_conclusion=='证据不足，无法确认'",
              s.get("human_conclusion") == "证据不足，无法确认")
        f = s.get("fields", {})
        check(f"S{idx} clean_ratio 为 null", f.get("clean_ratio", "x") is None)
        check(f"S{idx} channel_quality 为空 dict", f.get("channel_quality") == {})
        dr = " ".join(str(v) for v in s.get("display_rules", {}).values())
        check(f"S{idx} 展示文案含'未提供'", "未提供" in dr)
        check(f"S{idx} 展示文案不含'未达'（IAF 来源不作推断）", "未达" not in dr)
        continue

    # assess 结构样张：全部由样张自身字段驱动
    m = s["metrics"]
    coverage.append(f"S{idx}=assess 结构（samples={m.get('samples')}）")

    # 窗数：按样张自己的 samples/sfreq/channels 构造数组实跑
    eeg = np.zeros((int(m["samples"]), len(m["channels"])))
    spans = qp._epochs(eeg, float(m["sfreq"]))
    check(f"S{idx} total_epochs==实跑_epochs(样张samples)",
          m["total_epochs"] == len(spans),
          f"样张={m['total_epochs']} 实跑={len(spans)}")

    # 有效率/丢包：按样张 samples/duration/sfreq 重算（assess :316-321 同式——
    # loss 先用未舍入 eff 计算，effective_hz 再单独 round 展示）
    if m["duration"] > 0:
        eff_raw = m["samples"] / m["duration"]
        eff = round(eff_raw, 2)
        loss = round(1.0 - eff_raw / m["sfreq"], 4) if m["sfreq"] > 0 else None
    else:
        eff, loss = 0.0, None
    check(f"S{idx} effective_hz==重算", m["effective_hz"] == eff,
          f"样张={m['effective_hz']} 重算={eff}")
    check(f"S{idx} packet_loss_rate==重算", m["packet_loss_rate"] == loss,
          f"样张={m['packet_loss_rate']} 重算={loss}")

    # noise_epochs 字符串内部一致性（分子=noise_epochs_n，分母=total_epochs）
    n_str = m.get("noise_epochs", "")
    if "/" in n_str:
        nz, tt = (int(x) for x in n_str.split("/"))
        check(f"S{idx} noise_epochs 分子==noise_epochs_n",
              m.get("noise_epochs_n") == nz,
              f"串={n_str} 键={m.get('noise_epochs_n')}")
        check(f"S{idx} noise_epochs 分母==total_epochs", tt == m["total_epochs"],
              f"串={n_str} total={m['total_epochs']}")
        check(f"S{idx} 0<=noise<=total", 0 <= nz <= tt, f"noise={nz} total={tt}")

    # 干净度：按样张 noise_epochs 字符串重算（:263/:357 同式）
    n_str = m.get("noise_epochs", "")
    if "/" in n_str:
        nz, tt = (int(x) for x in n_str.split("/"))
        cr = round(1.0 - nz / tt, 4) if tt else None
        check(f"S{idx} clean_ratio==按noise_epochs重算",
              m["clean_ratio"] == cr, f"样张={m['clean_ratio']} 重算={cr}")

    # 阈值组与源常量一致
    th = s.get("thresholds", {})
    check(f"S{idx} thresholds==源常量组",
          th.get("min_duration_s") == qp.MIN_DURATION_S
          and th.get("max_packet_loss") == qp.MAX_PACKET_LOSS
          and th.get("min_clean_ratio") == qp.MIN_CLEAN_RATIO)

    # reasons 重建比对
    cq = m.get("channel_quality", {})
    bad_names = [ch for ch, v in cq.items()
                 if isinstance(v, dict) and v.get("state") == "bad"]
    expect = rebuild_reasons(m.get("clean_ratio"), bad_names)
    check(f"S{idx} reasons==源码同式重建",
          s["reasons"] == expect, f"应={expect} 实={s['reasons']}")
    check(f"S{idx} recommend 一致",
          s["recommend"] == ("quarantine" if expect else "ingest"))

    # 通道阈值逐项
    for ch, v in cq.items():
        st = v.get("state")
        if st == "bad" and "max_abs_uv" in v and v["max_abs_uv"] > 900:
            check(f"S{idx} {ch} 饱和判据==CH_RAIL_UV",
                  v["max_abs_uv"] > qp.CH_RAIL_UV,
                  f"max={v['max_abs_uv']} 阈={qp.CH_RAIL_UV}")
        if st == "bad" and v.get("std_uv", 1) < 0.4:
            check(f"S{idx} {ch} 平线判据==CH_FLAT_STD_UV",
                  v["std_uv"] < qp.CH_FLAT_STD_UV,
                  f"std={v['std_uv']} 阈={qp.CH_FLAT_STD_UV}")
        if st == "warn":
            check(f"S{idx} {ch} 工频判据==CH_MAINS_RATIO",
                  v.get("mains_ratio", 0) > qp.CH_MAINS_RATIO,
                  f"mains={v.get('mains_ratio')} 阈={qp.CH_MAINS_RATIO}")
    if len(bad_names) >= 2:
        check(f"S{idx} bad>=2 ⇒ 无 downweighted 键", "downweighted" not in m)

# ── ④ 文案断言（正文层；二/三轮更正记表格为错误留痕，豁免）─────────
cut = text.find("### 二轮更正记")
body = text[:cut] + text[text.find("## 二、", cut):] if cut >= 0 else text
for banned in ["无PPG", "0.70", "默认2000", "默认0.01", "30s 窗",
               "不可能同时成立", "76770", "255.9", "0.0004", "46080"]:
    check(f"正文禁'{banned}'", banned not in body)
check("正文含'未提供'", "未提供" in body)
check("全文禁'法师 10-15 02:3x 令'", "法师 10-15 02:3x 令" not in text)

# ── 汇总与覆盖面报告 ───────────────────────────────────────────────
print(f"\n共 {len(oks) + len(fails)} 项：PASS {len(oks)}／FAIL {len(fails)}")
print("实际覆盖面（仅限当前样张，不外推）：")
for line in coverage:
    print(f"  · {line}")
print("  · rebuild_reasons 未含时长/丢包闸与单坏道降权分支（当前两例未触发，未核）")
for line in fails:
    print(line)
sys.exit(1 if fails else 0)
