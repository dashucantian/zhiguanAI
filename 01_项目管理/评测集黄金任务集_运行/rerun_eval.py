# -*- coding: utf-8 -*-
"""
W4 评测 · 补跑轮（2026-09-22 两项裁定落地）

背景：
1) L4-01 泄露修正重跑——正式轮脚本缺陷把 L4-01 素材"参考锚点（裁判专用，不给
   被测模型）"整节贴进题面（该文件 §使用说明明文禁止），三模型均被泄露，
   L4-01 全部作废。现按修正逻辑只贴"输入素材＋产出要求"两节，三模型重跑。
2) Ornith L4-02b 截断重跑——法师裁定 02b 不重跑只评第二问（D25 背景污染第一问），
   但 Ornith 的 02b 在 8192 下 reasoning 吃满、正文全空，裁定单题提至 14000
   （ctx 32768 − prompt 18100 ≈ 14668 余量内）重跑一次，让其正文产出后可评第二问。
   若仍截断则如实记为生存性发现。

用法：py -3.12 rerun_eval.py <model_identifier> <model_key> [with02b]
  with02b 仅 Ornith 补跑时传。
结果：追加到 results/正式/<model_key>__runlog.jsonl（note=重跑 / 重跑02b14000），
      响应文件带 _重跑 后缀独立保存，旧污染版保留不删（runlog 与文件双留可核）。
"""
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import run_eval as R  # noqa: E402


def build_tasks():
    """与 run_eval.main 相同的冻结题面拼装（含 L4-01 去锚点修正）。"""
    l401_full = R.read_mat("L4-01_虚构采集描述.md")

    def extract_codeblocks(card, headers):
        blocks = []
        for h in headers:
            seg = card[card.index(h):]
            m = re.search(r"```\n(.*?)```", seg, re.S)
            blocks.append(m.group(1).strip())
        return "\n\n".join(blocks)

    l401_mat = extract_codeblocks(l401_full, ["## 输入素材", "## 产出要求"])
    # 自检：确保锚点字样不在贴入内容中
    assert "参考锚点" not in l401_mat and "裁判专用" not in l401_mat, "L4-01 锚点仍泄露！"

    task_card = R.read_mat("L4-02ab_任务卡与锚点.md")
    idx_first = task_card.index("## 题面（逐字贴入）")
    idx_second = task_card.index("## 题面（逐字贴入）", idx_first + 1)
    seg = task_card[idx_second:]
    m = re.search(r"```\n(.*?)```", seg, re.S)
    l402b_q = m.group(1).strip()
    l402b_mat = R.read_mat("L4-02b_题面输入.json")
    assert "标准答案" not in l402b_mat, "02b 答案泄露！"

    return {
        "L4-01": ("A", "请按上方素材与产出要求作答。", l401_mat),
        "L4-02b": ("B", l402b_q, l402b_mat),
    }


def main():
    model_id = sys.argv[1]
    model_key = sys.argv[2]
    with02b = len(sys.argv) > 3 and sys.argv[3] == "with02b"
    params = R.PROD[model_id]
    bg_entry, bg_decision, found, missing = R.build_background()
    assert not missing, f"背景缺失 {missing}"
    tasks = build_tasks()

    jsonl = R.OUT / f"{model_key}__runlog.jsonl"   # 追加模式！
    with jsonl.open("a", encoding="utf-8") as fh:
        R.log_record(fh, {"_meta": True, "round": "补跑", "model": model_key,
                          "model_id": model_id,
                          "note": ("L4-01泄露修正重跑"
                                   + ("＋02b提至14000" if with02b else "")),
                          "max_tokens": {"L4-01": 14000,
                                         "L4-02b": 14000 if with02b else None},
                          "mt_note": "L4-01重跑统一14000：Qwen3.8正式轮该项8192下finish=length，去锚点后防再截断；三模型同值保公平",
                          "ts": time.strftime("%Y-%m-%dT%H:%M:%S")})
        R.run_one(fh, model_id, model_key, params, "L4-01", "A",
                  R.make_prompt(bg_entry, bg_decision,
                                tasks["L4-01"][1], tasks["L4-01"][2]),
                  note="重跑", max_tokens=14000)
        if with02b:
            R.run_one(fh, model_id, model_key, params, "L4-02b", "B",
                      R.make_prompt(bg_entry, bg_decision,
                                    tasks["L4-02b"][1], tasks["L4-02b"][2]),
                      note="重跑02b14000", max_tokens=14000)
    print(f"→ 已追加 {jsonl}", flush=True)


if __name__ == "__main__":
    main()
