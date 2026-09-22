r"""
转写校对.py —— 用本机大模型对转写稿做「只改错字」的二次校对（全程离线）

设计要点（硬性安全阀）：
  1. 按行送审，逐行比对。模型只能改字，不能改措辞。
  2. 只接受「等长的短替换」或命中术语表的替换对；模型一旦增删内容、改写句子、
     合并行，该行立即驳回，保留原文，并记为"驳回"。
  3. 原始转写稿只读不改；结果写到 -校对稿.md 与 -校对改动对照表.md。

两种范围：
  默认  只校对命中可疑术语的行（快，覆盖已知问题）
  --all 全部行都送审（慢，但能发现未知错字）

用法：
  python 转写校对.py                       # 只校可疑行
  python 转写校对.py --all                 # 全量校对
  python 转写校对.py --limit 3             # 只跑前 3 批（试跑）
  python 转写校对.py --model qwen3.8-27b
"""
import os
import re
import json
import time
import argparse
import urllib.request
import difflib

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_IN = os.path.join(HERE, "20260919PM183158-大圆满前行-宗国法师.md")
GLOSSARY = os.path.join(HERE, "佛教术语表.md")
API = "http://127.0.0.1:1234/v1/chat/completions"
LINE_RE = re.compile(r"^-\s+`\[(\d{2}:\d{2}:\d{2})\]`\s+(.*)$")
BATCH = 12
EXTRA_SUSPECT = ["﹑", "　"]


def load_glossary(path):
    """返回 (允许替换对集合, 可疑词列表)。"""
    pairs, suspects = set(), []
    if not os.path.exists(path):
        return pairs, suspects
    with open(path, encoding="utf-8") as f:
        for ln in f:
            s = ln.strip()
            if not s.startswith("|"):
                continue
            cells = [c.strip() for c in s.strip("|").split("|")]
            if len(cells) < 2 or cells[0] in ("转写常错为", "") or set(cells[0]) <= set("-: "):
                continue
            wrongs = [w.strip() for w in cells[0].split("/") if w.strip()]
            suspects.extend(wrongs)
            right = cells[1].strip()
            if not right or "？" in right:
                continue
            rights = [w.strip() for w in right.split("/") if w.strip()]
            for w in wrongs:
                for r in rights:
                    pairs.add((w, r))
    suspects = [x for x in suspects if len(x) >= 2] + EXTRA_SUSPECT
    return pairs, sorted(set(suspects), key=len, reverse=True)


def build_system(glossary_text):
    return (
        "你是佛教录音转写的校对员。任务只有一个：把明显的同音/近音错别字改成正确写法，"
        "以及修正明显错误的标点符号。\n\n"
        "【绝对禁止】改写句子、调整语序、润色、补内容、删内容、合并或拆分行、"
        "把口语改成书面语、改动数字、删除语气词或重复。宁可漏改，不可多改。\n\n"
        "【术语依据】只参考下面的术语表与本行上下文；表内没有且无把握的，一律原样返回。\n"
        + glossary_text
        + "\n\n【输出格式】只输出一个 JSON 对象：键是给你的行号（字符串），值是校对后的该行正文。"
        "不需要改的行，也必须把原文一字不差地返回。"
        "不得输出解释、不得输出 markdown 代码块、不得输出上下文行。\n"
        "示例：{\"0\":\"你也学了很多操作的方法、技巧。\",\"1\":\"尤其我们多数都是没太有这方面学修的基础。\"}"
    )


def post(payload, timeout=600):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(API, data=data,
                                headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def parse_reply(text):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    s, e = text.find("{"), text.rfind("}")
    if s >= 0 and e > s:
        try:
            obj = json.loads(text[s:e + 1])
            if isinstance(obj, dict):
                return {int(k): str(v) for k, v in obj.items()}
        except Exception:
            pass
    return None


def diff_regions(a, b):
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag != "equal":
            out.append((tag, a[i1:i2], b[j1:j2]))
    return out


def accept(orig, new, gloss_pairs):
    """安全阀：只放行等长短替换或术语表内的替换。返回 (是否接受, 替换列表或驳回原因)"""
    if orig == new:
        return True, []
    regions = diff_regions(orig, new)
    changes = []
    for tag, o, n in regions:
        if tag in ("delete", "insert"):
            return False, "模型增删了内容(%s:%r)" % (tag, (o or n)[:14])
        if len(o) != len(n) and (o, n) not in gloss_pairs:
            return False, "替换长度不等且不在术语表(%r→%r)" % (o[:14], n[:14])
        if len(o) > 6 and (o, n) not in gloss_pairs:
            return False, "替换跨度过大(%r→%r)" % (o[:18], n[:18])
        changes.append((o, n))
    return True, changes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="infile", default=DEFAULT_IN)
    ap.add_argument("--model", default="qwen3.8-27b")
    ap.add_argument("--all", action="store_true", help="全部行送审（默认只送可疑行）")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 批，用于试跑")
    ap.add_argument("--out-suffix", default="", help="产物文件后缀（三模型对比时区分输出）")
    args = ap.parse_args()

    head, items = [], []
    with open(args.infile, encoding="utf-8") as f:
        for ln in f.read().splitlines():
            m = LINE_RE.match(ln)
            if m:
                items.append({"ts": m.group(1), "text": m.group(2)})
            else:
                head.append(ln)
    if not items:
        print("没有解析到任何 `- [时间戳]` 行")
        return

    gloss_pairs, suspects = load_glossary(GLOSSARY)
    with open(GLOSSARY, encoding="utf-8") as f:
        gloss_text = f.read()
    sysmsg = build_system(gloss_text)

    if args.all:
        targets = list(range(len(items)))
        mode = "全量（每一行都送审）"
    else:
        targets = [i for i, it in enumerate(items)
                   if any(s in it["text"] for s in suspects)]
        mode = "可疑行（命中 %d 个术语线索）" % len(suspects)

    base = os.path.splitext(args.infile)[0]
    suf = args.out_suffix
    out_md = base + "-校对稿%s.md" % ("-" + suf.lstrip("-") if suf else suf)
    out_log = base + "-校对改动对照表%s.md" % ("-" + suf.lstrip("-") if suf else suf)
    ckpt_path = base + ((".ckpt" + suf + ".json") if suf else ".ckpt.json")

    done = {}
    if os.path.exists(ckpt_path):
        try:
            with open(ckpt_path, encoding="utf-8") as f:
                done = {int(k): v for k, v in json.load(f).items()}
            print("[续跑] 已有 %d 行结果" % len(done))
        except Exception:
            done = {}

    todo = [i for i in targets if i not in done]
    batches = [todo[i:i + BATCH] for i in range(0, len(todo), BATCH)]
    if args.limit:
        batches = batches[:args.limit]

    print("源文件：%s" % os.path.basename(args.infile))
    print("模型   ：%s（本机 LM Studio）" % args.model)
    print("范围   ：%s ｜ 需送审 %d 行 / 全文 %d 行，分 %d 批"
          % (mode, len(targets), len(items), len(batches)))
    print("=" * 60)

    t0 = time.time()
    stats = {"changed_lines": 0, "rejected": 0, "missing": 0, "changes": []}

    for bi, batch in enumerate(batches, 1):
        blocks, keys = [], []
        for gi in batch:
            prev = items[gi - 1]["text"] if gi > 0 else ""
            nxt = items[gi + 1]["text"] if gi + 1 < len(items) else ""
            blocks.append("〔上下文·前〕%s\n〔待校 %d〕%s\n〔上下文·后〕%s"
                          % (prev, len(keys), items[gi]["text"], nxt))
            keys.append(gi)
        keymap = {str(k): items[keys[k]]["text"] for k in range(len(keys))}
        user = ("请按上下文逐行校对下列行号（上下文行仅供判断，不要输出它们）：\n"
                + "\n\n".join(blocks)
                + "\n\nJSON 形式重述待校行：\n"
                + json.dumps(keymap, ensure_ascii=False))
        got = None
        try:
            resp = post({"model": args.model, "temperature": 0.0, "max_tokens": 4000,
                         "messages": [{"role": "system", "content": sysmsg},
                                      {"role": "user", "content": user}]})
            got = parse_reply(resp["choices"][0]["message"]["content"])
        except Exception as e:
            print("  批 %d/%d 调用失败：%s" % (bi, len(batches), e))
        if not got:
            stats["missing"] += len(batch)
            print("  批 %d/%d 无法解析返回，本批保留原文" % (bi, len(batches)))
            continue
        for k, gi in enumerate(keys):
            orig = items[gi]["text"]
            new = str(got.get(k, "")).strip()
            if not new:
                stats["missing"] += 1
                done[gi] = {"text": orig, "note": "模型未返回该行，保留原文"}
                continue
            ok, note = accept(orig, new, gloss_pairs)
            if ok:
                done[gi] = {"text": new}
                if note:
                    stats["changed_lines"] += 1
                    for o, n in note:
                        stats["changes"].append((items[gi]["ts"], o, n))
            else:
                stats["rejected"] += 1
                done[gi] = {"text": orig, "note": "驳回：" + note}

        with open(ckpt_path, "w", encoding="utf-8") as f:
            json.dump({str(k): v for k, v in done.items()}, f, ensure_ascii=False)
        el = time.time() - t0
        print("  批 %d/%d 完成，累计 %s｜改动 %d 行、替换 %d 处、驳回 %d 行"
              % (bi, len(batches), time.strftime("%H:%M:%S", time.gmtime(el)),
                 stats["changed_lines"], len(stats["changes"]), stats["rejected"]))

    covered = len([i for i in targets if i in done])
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(head[:1]) + "\n\n")
        f.write("> 源转写稿：%s\n" % os.path.basename(args.infile))
        f.write("> 二次校对：本机 LM Studio · %s · temperature=0 · 术语表 %d 组替换对\n"
                % (args.model, len(gloss_pairs)))
        f.write("> 本次校对范围：%s，覆盖 %d / %d 段（未覆盖段落原样保留，未作任何改动）\n"
                % (mode, covered, len(items)))
        f.write("> 校对用时：%s\n" % time.strftime("%H:%M:%S", time.gmtime(time.time() - t0)))
        f.write("> ⚠️ 校对器设有安全阀：仅接受同音/近音的等长替换或术语表内替换；"
                "模型改写句子的行为已全部驳回并保留原文。\n")
        f.write("> ⚠️ 仍属机器产物，正式引用前须法师过目。\n\n")
        for i, it in enumerate(items):
            rec = done.get(i, {"text": it["text"]})
            f.write("- `[%s]` %s\n" % (it["ts"], rec["text"]))
            if rec.get("note"):
                f.write("  <!-- %s -->\n" % rec["note"])

    with open(out_log, "w", encoding="utf-8") as f:
        f.write("# 校对改动对照表\n\n")
        f.write("> 源：%s ｜ 模型：%s ｜ 范围：%s ｜ 生成：%s\n\n"
                % (os.path.basename(args.infile), args.model, mode,
                   time.strftime("%Y-%m-%d %H:%M")))
        f.write("- 本次覆盖行数：**%d / %d**\n- 改动的行数：**%d**\n"
                "- 具体替换次数：**%d**\n- 被安全阀驳回（模型想改写，已保留原文）：**%d**\n"
                "- 未获返回而保留原文：**%d**\n\n"
                % (covered, len(items), stats["changed_lines"], len(stats["changes"]),
                   stats["rejected"], stats["missing"]))
        f.write("## 逐条替换（时间 / 原文 / 改为）\n\n| 时间 | 原 | 改 |\n|---|---|---|\n")
        for ts, o, n in stats["changes"]:
            f.write("| %s | %s | %s |\n" % (ts, o, n))
        notes = [(done[i]["note"], items[i]["ts"]) for i in sorted(done) if done[i].get("note")]
        if notes:
            f.write("\n## 保留原文但需注意的行\n\n| 时间 | 说明 |\n|---|---|\n")
            for nt, ts in notes:
                f.write("| %s | %s |\n" % (ts, nt))

    print("=" * 60)
    print("完成！覆盖 %d/%d 段，改动 %d 行 / 替换 %d 处，驳回 %d 行，未返回 %d 行"
          % (covered, len(items), stats["changed_lines"], len(stats["changes"]),
             stats["rejected"], stats["missing"]))
    print("  校对稿    ：%s" % out_md)
    print("  改动对照表：%s" % out_log)


if __name__ == "__main__":
    main()
