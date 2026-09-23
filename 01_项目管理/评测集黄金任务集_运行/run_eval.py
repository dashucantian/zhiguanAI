# -*- coding: utf-8 -*-
"""
W4 评测集黄金任务集 · L4 线正式跑批（仅本机，连接 LM Studio 1234）

设计（据 2026-09-14 选项B + D47 留证口径 + §5.1 B 忠实背景）：
- 统一背景 = §5.1 选项B 忠实口径：AI-开工入口.md 全文 ＋ 决策日志 D22–D26 条目。
  （非 L4 任务卡头部旧表述"D3、D22 两条"；缘由见 README 运行说明：§三bis 较新胜出＋
   专门优先，且三模型逐字一致不损可比性。此为运行时拼装，不改动任何冻结素材。）
- 参数 = 各模型生产值（§8.3）＋ seed=42（请求层统一）＋ max_tokens=8192（裁定甲）＋ system 空。
- 留证 = 每请求落 JSONL：时间戳/模型/任务/请求参数/usage(prompt/completion/reasoning)/
  finish_reason/正文 sha256/正文全文/reasoning 全文。JSONL 即 D47① 主证据「运行日志」。
- seed 一致性复现检查：对每模型的 L4-02a 额外用相同请求再跑一次（标 repro_check，不计入评分）。

轨道与出网纪律：全程 localhost，不触碰任何线上服务。L4-02a/b 属轨道B（原始脑电衍生），
本脚本只连本机 → 天然满足"绝不出网"。

〔2026-09-22 裁定甲（D49）〕max_tokens 4096→**8192**：试跑实测 4096 在
thinking-ON 模型上被推理耗尽（Ornith reasoning 实测 3590–4096、无 2048 硬顶），
5 次调用 4 次正文全空。§8.3 记实际值并标偏离缘由。

用法：py -3.12 run_eval.py <model_identifier> <model_key> [round]
  round 缺省 正式（输出入 results/正式/）；试跑轮已在 results/ 平铺留证不再复跑。
  例：py -3.12 run_eval.py ornith-eval Ornith-1.5-35B-A3B
"""
import hashlib
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(r"D:\Project\zhiguanAI")
RUN = ROOT / "01_项目管理" / "评测集黄金任务集_运行"
MAT = ROOT / "01_项目管理" / "评测集黄金任务集_素材"
OUT = RUN / "results" / "正式"
OUT.mkdir(parents=True, exist_ok=True)
BASE_URL = "http://localhost:1234/v1/chat/completions"
MAX_TOKENS = 8192  # 2026-09-22 裁定甲：原 4096 实测被 thinking 耗尽（见试跑发现文件）

# 各模型生产参数（§8.3 预填值，一手源 模型调参-分工.txt 2026-09-14 01:46）
PROD = {
    "ornith-eval":      {"temperature": 0.15, "top_p": 0.9,  "top_k": 40, "repeat_penalty": 1.1,  "thinking": "ON(budget2048)"},
    "qwen36-eval":      {"temperature": 0.25, "top_p": 0.92, "top_k": 40, "repeat_penalty": 1.05, "thinking": "未记录(budget2048)"},
    "qwen38-eval":      {"temperature": 0.20, "top_p": 0.9,  "top_k": 40, "repeat_penalty": 1.08, "thinking": "ON(budget1024)"},
}


def sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def build_background():
    """§5.1 选项B 忠实口径：开工入口全文 ＋ 决策日志 D22–D26 条目。"""
    entry = (ROOT / "AI-开工入口.md").read_text(encoding="utf-8")
    log = (ROOT / "01_项目管理" / "止观AI项目分工与决策日志.md").read_text(encoding="utf-8")
    picked = {}
    for line in log.splitlines():
        # 每条决策日志为 markdown 表格单行。行首不一定形如 **D2x：
        # （D23 行首是"⚠️【本条已被取代】"声明，D23：字样在行内后部），
        # 故在整行内找首个 D2x： 并按编号去重（保留首次命中行）。
        if not line.startswith("| 20"):
            continue
        m = re.search(r"(D2[2-6])[：:]", line)
        if m and m.group(1) not in picked:
            picked[m.group(1)] = line.rstrip()
    found = sorted(picked.keys())
    missing = [d for d in ["D22", "D23", "D24", "D25", "D26"] if d not in found]
    decision = "\n\n".join(picked[d] for d in found)
    return entry, decision, found, missing


def read_mat(name):
    return (MAT / name).read_text(encoding="utf-8")


def make_prompt(bg_entry, bg_decision, task_body, material):
    parts = [
        "你是止观AI项目的AI助理。以下是本项目的关键背景，请先读取再作答。",
        "",
        "【项目背景】",
        bg_entry,
        "",
        "【项目决策日志相关条目（D22–D26）】",
        bg_decision,
        "",
        "【本次任务】",
        task_body,
    ]
    if material:
        parts += ["", "【输入素材】", material]
    return "\n".join(parts)


def call(model_id, params, prompt, max_tokens=None, timeout=900):
    if max_tokens is None:
        max_tokens = MAX_TOKENS
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": params["temperature"],
        "top_p": params["top_p"],
        "top_k": params["top_k"],
        "repeat_penalty": params["repeat_penalty"],
        "max_tokens": max_tokens,
        "seed": 42,
        "stream": False,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(BASE_URL, data=data,
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        j = json.loads(resp.read().decode("utf-8"))
    return payload, j, round(time.time() - t0, 2)


def log_record(fh, rec):
    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    fh.flush()


def run_one(fh, model_id, model_key, params, task_id, track, prompt, note="", max_tokens=None):
    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    try:
        payload, j, elapsed = call(model_id, params, prompt, max_tokens=max_tokens)
        ch = j["choices"][0]
        msg = ch.get("message", {})
        content = msg.get("content") or ""
        reasoning = msg.get("reasoning_content") or ""
        usage = j.get("usage", {})
        rec = {
            "ts": ts, "model": model_key, "model_id": model_id, "task": task_id,
            "track": track, "note": note, "elapsed_s": elapsed,
            "request_params": {k: payload[k] for k in
                               ("temperature", "top_p", "top_k", "repeat_penalty",
                                "max_tokens", "seed")},
            "thinking_prod": params["thinking"],
            "usage": usage,
            "finish_reason": ch.get("finish_reason"),
            "prompt_chars": len(prompt),
            "content_sha": sha(content), "content_len": len(content),
            "reasoning_len": len(reasoning),
            "content": content, "reasoning": reasoning,
            "error": None,
        }
    except Exception as e:  # noqa
        rec = {"ts": ts, "model": model_key, "model_id": model_id, "task": task_id,
               "track": track, "note": note, "error": repr(e)[:500],
               "prompt_chars": len(prompt)}
    log_record(fh, rec)
    # 每任务响应正文单独存文件（人读）
    tag = f"{task_id}" + (f"_{note}" if note else "")
    (OUT / f"{model_key}__{tag}.md").write_text(
        f"# {model_key} · {task_id} {note}\n\n"
        f"- finish_reason: {rec.get('finish_reason')}\n"
        f"- usage: {json.dumps(rec.get('usage'), ensure_ascii=False)}\n"
        f"- prompt_chars: {rec.get('prompt_chars')}  content_len: {rec.get('content_len')}\n\n"
        f"## 正文\n\n{rec.get('content','')}\n\n---\n\n## reasoning\n\n{rec.get('reasoning','')}\n",
        encoding="utf-8")
    summ = (f"[{model_key} {task_id}{('/'+note) if note else ''}] "
            f"err={bool(rec.get('error'))} finish={rec.get('finish_reason')} "
            f"ctok={rec.get('usage',{}).get('completion_tokens')} "
            f"rtok={rec.get('usage',{}).get('completion_tokens_details',{}).get('reasoning_tokens')} "
            f"sha={rec.get('content_sha')} {rec.get('elapsed_s','')}s")
    print(summ, flush=True)
    return rec


def main():
    model_id = sys.argv[1]
    model_key = sys.argv[2]
    params = PROD[model_id]
    bg_entry, bg_decision, found, missing = build_background()
    print(f"背景：决策日志命中 {found}，缺失 {missing}", flush=True)
    if missing:
        print("!! 背景拼装不完整，中止", flush=True)
        sys.exit(2)

    # 冻结题面（逐字，来自素材目录，不改动）
    # ⚠️修正（2026-09-22）：L4-01 素材此前误贴**全文**，把"参考锚点（裁判专用，
    # 不给被测模型）"一并泄露（该文件 §使用说明明文警告）。现只取
    # "输入素材"＋"产出要求"两节的代码块内容，锚点不进题面。
    l401_full = read_mat("L4-01_虚构采集描述.md")

    def extract_codeblocks(card, headers):
        blocks = []
        for h in headers:
            seg = card[card.index(h):]
            m = re.search(r"```\n(.*?)```", seg, re.S)
            blocks.append(m.group(1).strip())
        return "\n\n".join(blocks)

    l401_mat = extract_codeblocks(l401_full, ["## 输入素材", "## 产出要求"])
    l401_task = ("请按上方素材与产出要求作答。")

    # L4-02a 题面：取自任务卡冻结"题面（逐字贴入）"代码块
    task_card = read_mat("L4-02ab_任务卡与锚点.md")

    def extract_frozen(card, header):
        i = card.index(header)
        seg = card[i:]
        m = re.search(r"```\n(.*?)```", seg, re.S)
        return m.group(1).strip()

    l402a_q = extract_frozen(task_card, "## 题面（逐字贴入）")
    l402b_q = None
    # 两个"题面（逐字贴入）"：第二次出现在 L4-02b 节，取之
    idx_first = task_card.index("## 题面（逐字贴入）")
    idx_second = task_card.index("## 题面（逐字贴入）", idx_first + 1)
    seg = task_card[idx_second:]
    m = re.search(r"```\n(.*?)```", seg, re.S)
    l402b_q = m.group(1).strip()
    l402b_mat = read_mat("L4-02b_题面输入.json")

    # L4-03：需初稿全文（本地模型不能自读文件系统，按 §5 贴入）
    l403_task = ("下方是《入定状态标注规范 V1 初稿》全文。请只撰写其中『样本纳入标准』一节的初稿，"
                 "逐条标注【可采信】或【存疑】。凡引用外部文献须为真实存在者；不确定即标【存疑】，"
                 "不得编造引用、版本号或机构政策。")
    l403_mat = (ROOT.parent / "Zen-EEG" / "00_governance" / "入定状态标注规范_V1_初稿.md").read_text(encoding="utf-8")

    jsonl = OUT / f"{model_key}__runlog.jsonl"
    with jsonl.open("w", encoding="utf-8") as fh:
        log_record(fh, {"_meta": True, "model": model_key, "model_id": model_id,
                        "prod_params": params, "seed": 42, "max_tokens": MAX_TOKENS,
                        "background_scope": "§5.1 B忠实口径: 开工入口全文 + D22-D26",
                        "bg_decision_hit": found,
                        "note": "运行时统一背景用§5.1 B口径非任务卡头部旧表述(D3/D22)，§三bis较新胜出",
                        "ts": time.strftime("%Y-%m-%dT%H:%M:%S")})
        # 建议顺序：L4-02a → L4-02b → L4-01 → L4-03
        run_one(fh, model_id, model_key, params, "L4-02a", "B",
                make_prompt(bg_entry, bg_decision, l402a_q, None))
        # seed 复现检查（同请求再跑一次，不计入评分）
        run_one(fh, model_id, model_key, params, "L4-02a", "B",
                make_prompt(bg_entry, bg_decision, l402a_q, None), note="seedrepro")
        run_one(fh, model_id, model_key, params, "L4-02b", "B",
                make_prompt(bg_entry, bg_decision, l402b_q, l402b_mat))
        run_one(fh, model_id, model_key, params, "L4-01", "A",
                make_prompt(bg_entry, bg_decision, l401_task, l401_mat))
        run_one(fh, model_id, model_key, params, "L4-03", "A",
                make_prompt(bg_entry, bg_decision, l403_task, l403_mat))
    print(f"→ {jsonl}", flush=True)


if __name__ == "__main__":
    main()
