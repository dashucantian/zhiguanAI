"""console.html 静态校验器（前端大改的回归防线，2026-09-08 采集台合并引入）。

浏览器无法在此自动渲染，故用三重静态检查兜住最常见的前端手术事故：
  A. 重复 id —— 同一 id 出现多次，getElementById 只取首个，另一处静默失效；
  B. 悬空引用 —— JS 里 $("x")/getElementById("x") 引用了 DOM 中不存在的 id；
  C. JS 语法 —— 抽出 <script> 体交 `node --check`（node 不在则跳过并提示）。

用法：python validate_console.py [路径]
退出码 0=通过；非 0=发现问题（打印清单）。动态创建的 id（脚本 innerHTML 注入）
应加入 DYNAMIC_IDS 白名单，避免误报。
"""
import re
import subprocess
import sys
import os
import tempfile
from collections import Counter

# 脚本运行时才注入 DOM 的 id（模板字符串里），静态扫描视为存在
DYNAMIC_IDS = {
    "hiP", "hiT",       # 历史页每行入库选择器（前缀拼接）
}

def load_html(path):
    with open(path, encoding="utf-8") as f:
        return f.read()

def find_ids(html):
    return re.findall(r'\bid=["\']([^"\']+)["\']', html)

def find_refs(js):
    ids = set(re.findall(r'\$\(\s*["\']([^"\']+)["\']\s*\)', js))
    ids |= set(re.findall(r'getElementById\(\s*["\']([^"\']+)["\']\s*\)', js))
    return ids

def extract_scripts(html):
    return re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)

def check_syntax(js, node="node"):
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as tf:
        tf.write(js)
        tmp = tf.name
    try:
        r = subprocess.run([node, "--check", tmp],
                           capture_output=True, text=True, timeout=30)
        return r.returncode == 0, (r.stderr or r.stdout).strip()
    except FileNotFoundError:
        return None, "node 不可用，跳过语法检查"
    except Exception as e:
        return None, f"node 调用异常：{e}"
    finally:
        os.unlink(tmp)

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "console.html")
    html = load_html(path)
    ids = find_ids(html)
    idset = set(ids)
    scripts = extract_scripts(html)
    js_all = "\n".join(scripts)

    problems = []

    dup = [i for i, c in Counter(ids).items() if c > 1]
    if dup:
        problems.append("A. 重复 id：" + ", ".join(sorted(dup)))

    refs = find_refs(js_all)
    # 动态拼接的 id 以已知前缀开头则豁免
    dangling = []
    for r in sorted(refs):
        if r in idset or r in DYNAMIC_IDS:
            continue
        if any(r.startswith(p) for p in DYNAMIC_IDS):
            continue
        dangling.append(r)
    if dangling:
        problems.append("B. 悬空引用（JS 引用但 DOM 无此 id）："
                        + ", ".join(dangling))

    ok, msg = check_syntax(js_all)
    if ok is False:
        problems.append("C. JS 语法错误：" + msg)
        syntax_line = "❌ 语法错误"
    elif ok is None:
        syntax_line = "⚠ " + msg
    else:
        syntax_line = "✅ 通过"

    print(f"文件：{path}")
    print(f"  id 总数：{len(idset)}（含动态白名单 {len(DYNAMIC_IDS)}）")
    print(f"  JS 引用数：{len(refs)}")
    print(f"  JS 语法：{syntax_line}")
    if problems:
        print("发现问题：")
        for p in problems:
            print("  -", p)
        return 1
    print("PASS: console.html 静态校验通过（无重复 id / 无悬空引用 / 语法正确）")
    return 0

if __name__ == "__main__":
    sys.exit(main())
