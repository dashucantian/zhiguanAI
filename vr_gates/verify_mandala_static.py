# 〔VR 闸正本·2026-09-30 起〕自 output/ 收拢进 vr_gates/（output/* 被 .gitignore 忽略，
#  验收能力本身不入库＝随时可被清盘丢掉）。证据产物仍写 output/（大图不入库）。
# 原位置：output/20260914_W1两项待裁定核查/verify_mandala_static.py
"""曼荼罗场域 · 静态验收（不需浏览器，受限沙箱内亦可跑）——AI-005 2026-09-17

由来：`verify_mandala_s1.py` 依赖 CDP 无头 Edge，而受限沙箱下 Edge 的多进程
mojo IPC（命名管道）被拒，浏览器主进程能起、真要渲染即断（六种启动参数组合
实测全失败）。但 S1 的 11 项判据里有一半**本就不需要浏览器**——HTTP 回归、
纪律反向断言、色板、素材依赖、语法、钩子口径。本脚本把这些固化下来，使
"受限环境下也能产出可核的验收证据"，与像素类判据互补，不互相替代。

判据：
  1. HTTP 回归：/mandala、/vr、/ 三路 200（新增路由不伤既有）
  2. 页面可服务且含诊断钩子 window.__mandalaDiag
  3. 内联 module 语法（抽取后 node --check；node 不可用则如实标 SKIP）
  4. S1 纪律反向断言（源码级）：无粒子／无 bloom／无数据流／无音视频／无定时器
  5. 3D 场景颜色必须全部由 PALETTE 派生（DOM/CSS 颜色另列，不判失败）
  6. 外部素材零依赖：场景内不引用任何图片／模型／音视频文件
  7. **钩子口径回归**：layers 必须由 2k 实算得出，**禁止出现字面量数字**
     —— S1 那次"8/16/8 PASS"的成因正是该字段被写成字面量 8（几何实为 16 瓣）
  8. draw call 预算：scene.add 次数 ≤ 6

用法：python verify_mandala_static.py [--url http://127.0.0.1:8777] [--file ..\\vr_mandala.html]
退出码：0 全过 / 1 有失败项
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile
import urllib.request

FAILS = []
WARNS = []


def check(cond, ok_msg, fail_msg):
    if cond:
        print(f"  [PASS] {ok_msg}")
    else:
        print(f"  [FAIL] {fail_msg}")
        FAILS.append(fail_msg)


def note(msg):
    print(f"  [注意] {msg}")
    WARNS.append(msg)


def get(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return r.status, r.read().decode("utf-8", "replace")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8777")
    ap.add_argument("--file", default=None,
                    help="vr_mandala.html 路径（默认由脚本位置推）")
    args = ap.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    html_path = args.file or os.path.join(root, "vr_mandala.html")

    print("=" * 72)
    print("曼荼罗场域 · 静态验收（无浏览器）")
    print(f"  服务 {args.url} · 文件 {html_path}")
    print("=" * 72)

    # ── 1. HTTP 回归 ─────────────────────────────────────────────
    print("\n── 判据 1：HTTP 回归（三路 200）")
    for path in ("/mandala", "/vr", "/"):
        try:
            st, _ = get(args.url + path)
            check(st == 200, f"{path} → HTTP {st}", f"{path} → HTTP {st}（非 200）")
        except Exception as e:
            check(False, "", f"{path} 请求失败：{e}")

    # ── 2. 页面与钩子 ────────────────────────────────────────────
    print("\n── 判据 2：页面可服务且含诊断钩子")
    served = ""
    try:
        st, served = get(args.url + "/mandala")
        check(st == 200 and "__mandalaDiag" in served,
              f"/mandala 可服务且含 __mandalaDiag（{len(served)} 字符）",
              "/mandala 未返回诊断钩子——页面可能不是曼荼罗场域")
    except Exception as e:
        check(False, "", f"/mandala 取页失败：{e}")

    src = open(html_path, encoding="utf-8").read()

    # ── 3. module 语法 ──────────────────────────────────────────
    print("\n── 判据 3：内联 module 语法")
    m = re.search(r'<script type="module">(.*?)</script>', src, re.S)
    if not m:
        check(False, "", "未找到内联 module 脚本")
    else:
        js = m.group(1)
        try:
            subprocess.run(["node", "--version"], capture_output=True, check=True)
            tf = os.path.join(tempfile.gettempdir(), "mandala_static_check.mjs")
            with open(tf, "w", encoding="utf-8") as f:
                f.write(js)
            r = subprocess.run(["node", "--check", tf], capture_output=True, text=True)
            check(r.returncode == 0,
                  f"node --check 通过（{len(js)} 字符）",
                  f"node --check 失败：{r.stderr.strip()[:200]}")
        except Exception as e:
            note(f"node 不可用，语法检查 SKIP（{e}）——如实标注，未通过不等于通过")

    # ── 4. S1 纪律反向断言 ──────────────────────────────────────
    print("\n── 判据 4：S1 纪律反向断言（源码级）")
    forbidden = [
        ("粒子", r"\bPoints\b|PointsMaterial|THREE\.Points"),
        ("bloom/后处理", r"UnrealBloomPass|EffectComposer|ShaderPass"),
        ("数据流", r"WebSocket|EventSource|/ws/|fetch\(|XMLHttpRequest"),
        ("音视频", r"<audio|<video|new Audio|\.mp3|\.wav|AudioContext|AudioWorklet"),
        ("定时器", r"setInterval|setTimeout"),
    ]
    for name, pat in forbidden:
        hits = re.findall(pat, src)
        check(not hits, f"无{name}", f"检出{name}：{sorted(set(hits))[:5]}")

    # ── 5. 色板 ─────────────────────────────────────────────────
    print("\n── 判据 5：3D 场景颜色必须全部由 PALETTE 派生")
    pal = dict(re.findall(r"(\w+):\s*0x([0-9a-fA-F]{6})", re.search(
        r"const PALETTE = \{(.*?)\};", src, re.S).group(1)))
    pal_hex = {k: v.lower() for k, v in pal.items()}
    pal_vals = set(pal_hex.values())
    js_src = m.group(1) if m else ""
    scene_hex = [h.lower() for h in re.findall(r"0x([0-9a-fA-F]{6})", js_src)]
    stray = sorted({h for h in scene_hex if h not in pal_vals})
    check(not stray, f"场景十六进制颜色字面量全部属 PALETTE（{sorted(pal_vals)}）",
          f"场景引入 PALETTE 外颜色：{stray}")
    rgba = re.findall(r"rgba\((\d+),\s*(\d+),\s*(\d+)", js_src)
    rgba_stray = [f"{r},{g},{b}" for r, g, b in rgba
                  if f"{int(r):02x}{int(g):02x}{int(b):02x}" not in pal_vals | {"000000"}]
    check(not rgba_stray, f"场景 rgba 字面量亦为 PALETTE 派生（{len(rgba)} 处）",
          f"场景引入 PALETTE 外 rgba：{rgba_stray}")
    css_hex = [h.lower() for h in re.findall(r"#[0-9a-fA-F]{3,6}", src.split("</style>")[0])]
    css_stray = sorted({h for h in css_hex if h.lstrip("#").rjust(6, "0") not in pal_vals})
    if css_stray:
        note(f"DOM/CSS 层另有 {len(css_stray)} 个非 PALETTE 颜色 {css_stray}"
             f"——HUD/按钮等界面层，非 3D 场域；是否纳入色板纪律由法师定（SOP §二 原文只约束场景）")

    # ── 6. 外部素材零依赖 ───────────────────────────────────────
    print("\n── 判据 6：外部素材零依赖")
    ext = re.findall(r"\.(?:png|jpe?g|webp|gif|glb|gltf|fbx|obj|mp3|wav|ogg|mp4)\b", js_src, re.I)
    check(not ext, "场景代码不引用任何外部素材文件",
          f"检对外部素材引用：{sorted(set(ext))}")
    img = re.findall(r"<img\b", src.split("<script type=\"module\">")[0])
    check(not img, "页面无 <img> 标签", "页面含 <img> 标签")

    # ── 7. 钩子口径回归（S1 事故成因的直接断言）──────────────────
    print("\n── 判据 7：钩子口径回归（禁止字面量图层数）")
    check("const petalsOf" in src, "钩子由 petalsOf（2k）实算得出",
          "未找到 petalsOf——钩子可能又写回字面量")
    blk = re.search(r"layers:\s*\{(.*?)\}", src, re.S)
    if not blk:
        check(False, "", "未找到 layers 定义")
    else:
        body = blk.group(1)
        lits = re.findall(r":\s*(\d+)\b", body)
        check(not lits, "layers 内无字面量数字（全由注册表实算）",
              f"layers 内检出现字面量数字 {lits}——正是 S1「8/16/8 PASS」的成因"
              f"（钩子自述与几何不符而判据只信钩子）")

    # ── 8. draw call 预算 ───────────────────────────────────────
    print("\n── 判据 8：draw call 预算")
    n_add = len(re.findall(r"scene\.add\(", js_src))
    check(n_add <= 6, f"scene.add 共 {n_add} 处（≤6）", f"scene.add {n_add} 处 > 6，超 Pico 预算")

    print("\n" + "=" * 72)
    if WARNS:
        print(f"注意项 {len(WARNS)} 条（不判失败，须人判断）：")
        for w in WARNS:
            print(f"   - {w}")
    if FAILS:
        print(f"[FAIL] {len(FAILS)} 项未过：")
        for f in FAILS:
            print(f"   - {f}")
        print("\n说明：本脚本只覆盖**不需浏览器**的判据；像素类（黑底占比/金色占比/"
              "帧差/中心光点）仍须 verify_mandala_s1.py 在可用 Edge 的环境下跑，"
              "两者互补不互替。")
        return 1
    print("[PASS] 静态判据全通过")
    print("\n仍须另行验证的项（如实标注）：")
    print("   ① 像素判据（黑底≥85%/金色0.3~15%/两帧差≤1.0/中心光点）——须 Edge 可用环境")
    print("   ② 道场感（D 级）——法师 Pico 真机体感，任何脚本无法替代")
    return 0


if __name__ == "__main__":
    sys.exit(main())
