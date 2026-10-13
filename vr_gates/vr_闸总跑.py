# -*- coding: utf-8 -*-
"""VR 线验收闸总跑器（2026-09-30 W1 造·只读·零外联）

为什么要有：三件 mandala 闸与 verify_guided 散在 `output/` 各日期目录里，而
`output/*` 被 `.gitignore` 忽略 ⇒ **验收能力本身不入库**，清一次盘这条线就没有
任何闸了（09-30 实测发现）。正本已收拢到 `vr_gates/`，本脚本把它们串成一条命令。

顺带修掉两个实测发现的缺口：
  · `verify_mandala_variants.py` 不带参数时**默认只跑 3 个变体**（旧 :166 写死），
    而 `vr_mandala.html` 注册表在册 4 个／共 6 个——本脚本从注册表**读出键名与状态**再传入，
    不再靠第二份硬编码清单（单一正源，防再漏）。⚠**闸自己的裸跑缺省已于 10-12 同批改掉**
    （W3 领号·改4：现在裸跑从注册表读全量，读不到就 `raise`，不再静默只测 3／6）。
  · 09-19 裁"丙"时明写六变体一起进 Pico 体感终审，跑三个等于漏判两个。
  · 10-10 法师准"日常只跑在册"⇒ PLAN 分两档：`mandala-变体·日常`（在册 4）与
    `mandala-变体·收口轮`（全量 6，含 v5/v6 两个已裁留档）。`--only mandala-变体·日常` 即日常面。

用法：
    python vr_gates/vr_闸总跑.py              # 全跑
    python vr_gates/vr_闸总跑.py --only 备场   # 只跑某一项（名字前缀匹配）
前置：console_server 在 8777 运行（先 `python vr_备场.py --start`）。
退出码：全通过 0；任一不过 1。产物：`output/VR闸总跑_YYYYMMDD_HHMM.txt`。
"""
import datetime
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATES = os.path.join(ROOT, "vr_gates")
PY = sys.executable
OUT_DIR = os.path.join(ROOT, "output")
os.makedirs(OUT_DIR, exist_ok=True)


def variant_registry():
    """从注册表读 (键, 在册状态)。单一正源，日常档按状态过滤——不在注册表外另立清单。"""
    src = open(os.path.join(ROOT, "vr_mandala.html"), encoding="utf-8").read()
    m = re.search(r"const VARIANTS\s*=\s*\{(.*?)\n\};", src, re.S)
    if not m:
        raise RuntimeError("读不到 VARIANTS 注册表——页面结构变了，请同步本脚本")
    body = m.group(1)
    marks = [(x.start(), x.group(1)) for x in
             re.finditer(r"^  ([A-Za-z0-9]+):\s*\{", body, re.M)]
    out = []
    for i, (pos, key) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(body)
        st = "留档" if re.search(r"status:\s*'留档'", body[pos:end]) else "在册"
        out.append((key, st))
    if len(out) < 2:
        raise RuntimeError(f"注册表解析异常，只解析出 {out}")
    return out


PLAN = [
    ("备场", [os.path.join(ROOT, "vr_备场.py")],
     "服务在不在、六变体可达否、头显该填哪个地址（只读）"),
    ("交互锚定", [os.path.join(GATES, "..", "vr_交互锚定闸.py")],
     "P0-1：VR/专注页交互是否带时间锚落进契约事件流（会起一次模拟会话并自清）"),
    ("mandala-S1", [os.path.join(GATES, "verify_mandala_s1.py")],
     "S1 运行时 11 判据：黑底/金色占比/暖金方向/两帧差≤1.0（绝对安静）/纵深可复算"),
    ("mandala-静态纪律", [os.path.join(GATES, "verify_mandala_static.py")],
     "S1 反向断言：无粒子/无 bloom/无数据流/无音视频/无定时器＋钩子禁字面量自述"),
    ("mandala-变体·日常", ["__VARIANTS_DAILY__"],
     "在册变体逐像素与帧差（键与状态均从注册表读；法师 10-10 准日常只跑在册）"),
    ("mandala-变体·收口轮", ["__VARIANTS_ALL__"],
     "全量六变体——含 留档 两个（v5/v6 那条 0.22%/0.06% 系已裁预期 FAIL），收口轮才跑"),
    ("mandala-五段骨架", [os.path.join(GATES, "verify_mandala_stage.py")],
     "件3 五段路径骨架判据 1-13（默认关闭未破／段序／红线5 退出即时／三值分层／无评分／"
     "进入段后不遮场景／段时钟以会话为零点／张力层零介入与动力学／收束真归位／"
     "系统退出同样归位／首摆幅＝名义）——补丁原文写「七判据」，10-12 已增至 13，按实数改口"),
    ("mandala-S2呼吸", [os.path.join(GATES, "verify_mandala_breath.py")],
     "S2 三通道呼吸（?breath=on）：回归锚 off ＋ 呼吸存在/无跳变/周期可检出（规格 §四 1~4）"),
    ("引导版零后端", [os.path.join(GATES, "verify_guided.py")],
     "09-12 裁定回归：引导版零 WS 零模型列表；脑电版行为不变（CDP 网络域取证）"),
]


def main():
    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1]
    REG = variant_registry()
    keys = [k for k, _s in REG]
    daily = [k for k, s in REG if s == "在册"]
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    log_path = os.path.join(OUT_DIR, f"VR闸总跑_{stamp}.txt")
    lines = [f"VR 线验收闸总跑 · {stamp} · 变体键（注册表实读）：{keys}"
             f"｜在册 {len(daily)} 个＝日常档面：{daily}", ""]
    print("=" * 70)
    print(f"VR 线验收闸总跑｜注册表实读 {len(keys)} 个变体：{' '.join(keys)}")
    print(f"        其中在册 {len(daily)}（日常档）／留档 {len(keys) - len(daily)}（仅收口轮跑）")
    print("=" * 70)
    results = []
    for name, argv, why in PLAN:
        if only and not name.startswith(only):
            results.append((name, "SKIP", "未选"))
            print(f"  － {name:<18} 跳过（--only）")
            continue
        args = ([os.path.join(GATES, "verify_mandala_variants.py")] + [k for k, s in REG]
                if argv == ["__VARIANTS_ALL__"] else
                [os.path.join(GATES, "verify_mandala_variants.py")] + [k for k, s in REG if s == "在册"]
                if argv == ["__VARIANTS_DAILY__"] else
                [os.path.join(GATES, "verify_mandala_variants.py")] + [k for k, s in REG]
                if argv == ["__VARIANTS__"] else argv)
        # __VARIANTS__ 保留＝全量：向后兼容，不改任何既有调用（补丁原案 §四 改3）
        print(f"  ▶ {name:<18} {why}")
        try:
            p = subprocess.run([PY, "-X", "utf8"] + args, cwd=ROOT,
                               capture_output=True, text=True,
                               encoding="utf-8", errors="ignore", timeout=600)
            out = (p.stdout or "") + (p.stderr or "")
            ok = p.returncode == 0
            results.append((name, "PASS" if ok else "FAIL", ""))
            lines.append(f"########## {name}（{'PASS' if ok else 'FAIL'} rc={p.returncode}）"
                         f"##########\n{out}")
            tail = [x for x in out.splitlines() if x.strip()][-3:]
            for t in tail:
                print("      " + t[:96])
        except subprocess.TimeoutExpired:
            results.append((name, "FAIL", "超时 600s"))
            lines.append(f"########## {name}（超时）##########\n")
            print("      ✗ 超时 600 秒")
        except Exception as e:
            results.append((name, "FAIL", f"{type(e).__name__}"))
            lines.append(f"########## {name}（异常）##########\n{e}\n")
            print(f"      ✗ 跑不起来：{e}")
    bad = [r for r in results if r[1] == "FAIL"]
    print("-" * 70)
    for name, st, note in results:
        print(f"  {'✅' if st == 'PASS' else ('－' if st == 'SKIP' else '✗')} "
              f"{name:<18} {st} {note}")
    # 已裁留档的 FAIL：如实点出来，但**不因此改判、不因此把退出码抹平**——
    # 判据不挪（09-19 裁"丙"），S1 未收口就不许说"全绿"。
    ARCHIVED = {
        # ⚠键名须与 PLAN 里的**当前**名字逐字一致——PLAN 拆两档后旧名 "mandala-六变体" 已不存在，
        # 不改这里的话这条已裁说明会**静默不打印**（补丁原案 §四 未覆盖这一处，本窗补上）。
        "mandala-变体·收口轮":
            "v5stupa 金色 0.22%／v6void 金色 0.06%，均低于判据下限 0.3%——"
            "此即 09-19 法师裁「丙」所指：**判据不挪、参数不改、FAIL 原样留档**，"
            "随六变体进 Pico 体感终审。属**预期内留档项**，非本轮回归；"
            "但本闸仍按未过计（exit 1），S1 未收口不说全绿。",
    }
    for name, st, _ in results:
        if st == "FAIL" and name in ARCHIVED:
            print(f"\n  ⓘ 已裁留档说明｜{name}：{ARCHIVED[name]}")
    npass = sum(1 for r in results if r[1] == "PASS")
    nskip = sum(1 for r in results if r[1] == "SKIP")
    summary = (f"\n结果：**{npass}/{len(results) - nskip} 闸通过**"
               + (f"（另跳过 {nskip} 项）" if nskip else "")
               + ("" if not bad else f"，{len(bad)} 项未过（见日志）"))
    print(summary)
    lines.append("汇总：" + "，".join(f"{n}={s}" for n, s, _ in results) + summary)
    for name, st, _ in results:
        if st == "FAIL" and name in ARCHIVED:
            lines.append(f"已裁留档说明｜{name}：{ARCHIVED[name]}")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"日志：{log_path}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
