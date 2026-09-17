"""V2 步骤1b 验收：JS 移植 ↔ Python 验证基准 等价性回归测试

移植最大的风险不是语法错，而是 JS 实现与已验证的 Python 算法**逻辑不等价**。
本测试三层对比：
  ① algo_verify_2s.runq_time 的 s_val（验证基准，已确认达标）
  ② 从 vr_feedback.html 提取的**真实 JS 代码**（median/pushRA/ALGO）用 node 跑
两者对同一真机 rel_alpha 序列逐点比对，最大偏差须 < 1e-9（应完全一致）。

做法：正则从 html 抽出 ALGO/RA/median/pushRA 原样拼成 node 脚本，喂真机数据，
不重写、不简化——测的就是实机将运行的那份代码。
"""
import os, sys, json, re, subprocess
import numpy as np

RG_DIR = r"C:\Users\tiand\OneDrive\zhiguanAI\muse2-repo\muse2-master\muse-cloud-server"
sys.path.insert(0, RG_DIR)
BASE = r"C:\Users\tiand\OneDrive\zhiguanAI"
OUT = os.path.join(BASE, "output", "20260910_VR标准模板三重分析")
HTML = os.path.join(BASE, "vr_feedback.html")
CACHE = os.path.join(OUT, "_ra_2s_cache.npz")

SESSIONS = ["A_0910_22min", "B_0910_42min", "C_0911_43min"]
SHORT_SEC, HIST_SEC, TAU, WARM_SEC, MIN_HIST = 60.0, 300.0, 12.0, 90.0, 15
NOISE_BG = 0.65

# ── ① Python 验证基准（与 algo_verify_2s.runq_time 同逻辑，逐样本 s_val）──
def median_py(a):
    if not len(a):
        return float("nan")
    s = sorted(a); m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m-1] + s[m]) / 2

def py_sval_series(t_arr, ra_arr, nz_arr):
    """逐样本分位值（对应 JS pushRA 的返回，未展 tick、未 EMA）。"""
    hist = []           # (t, v, noise)
    out = []
    for i in range(len(ra_arr)):
        t, ra, nz = float(t_arr[i]), float(ra_arr[i]), bool(nz_arr[i])
        hist.append((t, ra, nz))
        cut = t - HIST_SEC
        while hist and hist[0][0] < cut:
            hist.pop(0)
        def vals(frm, to):
            all_ = [x for x in hist if frm <= x[0] <= to]
            good = [x[1] for x in all_ if not x[2]]
            return good if len(good) >= 3 else [x[1] for x in all_]
        cur = median_py(vals(t - SHORT_SEC, t))
        if not np.isfinite(cur):
            out.append(0.5); continue
        if t < WARM_SEC:
            out.append(0.5); continue
        hs = []
        for p in hist:
            if p[2]:
                continue
            m = median_py(vals(p[0] - SHORT_SEC, p[0]))
            if np.isfinite(m):
                hs.append(m)
        if len(hs) < MIN_HIST:
            out.append(0.5); continue
        le = sum(1 for h in hs if h <= cur)
        out.append(le / len(hs))
    return np.asarray(out)

# ── ② 从 html 提取真实 JS ──
html = open(HTML, encoding="utf-8").read()
def grab(pattern, label):
    m = re.search(pattern, html, re.S)
    if not m:
        raise SystemExit(f"❌ 无法从 html 提取 {label}")
    return m.group(0)

js_algo = grab(r"const ALGO = \{[\s\S]*?\n\};", "ALGO")
js_ra   = grab(r"const RA = \{[^\n]*\};", "RA")
js_med  = grab(r"function median\(a\)\{[\s\S]*?\n\}", "median")
js_push = grab(r"function pushRA\(t, ra, noise\)\{[\s\S]*?return le/hist\.length;\n\}", "pushRA")

print("提取到的真实 JS 片段：")
for lbl, code in [("ALGO", js_algo), ("RA", js_ra), ("median", js_med), ("pushRA", js_push)]:
    print(f"  {lbl}: {len(code.splitlines())} 行")

# ── 载入真机数据 ──
with np.load(CACHE, allow_pickle=True) as c:
    data = {tag: (c[tag+"_ra"], c[tag+"_ts"], c[tag+"_nz"]) for tag in SESSIONS if tag+"_ra" in c.files}

# 导出输入给 node
inputs = {}
for tag, (ra, ts, nz) in data.items():
    inputs[tag] = {"t": ts.tolist(), "ra": ra.tolist(), "nz": nz.tolist()}
in_path = os.path.join(OUT, "_equiv_input.json")
with open(in_path, "w", encoding="utf-8") as f:
    json.dump(inputs, f)

# ── node 脚本：原样拼接提取的 JS + 驱动 ──
node_src = f"""
{js_algo}
{js_ra}
{js_med}
{js_push}
const fs = require('fs');
const inputs = JSON.parse(fs.readFileSync({json.dumps(in_path)}, 'utf8'));
const out = {{}};
for (const tag of Object.keys(inputs)) {{
  RA.raw = [];                       // 每段重置状态
  const d = inputs[tag], res = [];
  for (let i = 0; i < d.t.length; i++) {{
    res.push(pushRA(d.t[i], d.ra[i], d.nz[i]));
  }}
  out[tag] = res;
}}
fs.writeFileSync({json.dumps(os.path.join(OUT, "_equiv_js_out.json"))}, JSON.stringify(out));
console.log("node done");
"""
node_path = os.path.join(OUT, "_equiv_test.cjs")
with open(node_path, "w", encoding="utf-8") as f:
    f.write(node_src)

r = subprocess.run(["node", node_path], capture_output=True, text=True)
if r.returncode != 0:
    print("❌ node 执行失败："); print(r.stderr[:800]); raise SystemExit(1)

js_out = json.load(open(os.path.join(OUT, "_equiv_js_out.json"), encoding="utf-8"))

# ── 对比 ──
print("\n" + "=" * 76)
print("等价性对比：Python 验证基准 vs 实机 JS 代码（逐样本分位值）")
print("=" * 76)
all_ok = True
for tag in SESSIONS:
    if tag not in data:
        continue
    ra, ts, nz = data[tag]
    py = py_sval_series(ts, ra, nz)
    js = np.asarray(js_out[tag], dtype=float)
    if py.shape != js.shape:
        print(f"  ❌ {tag}: 长度不一致 py={py.shape} js={js.shape}"); all_ok = False; continue
    diff = np.abs(py - js)
    maxd = float(diff.max())
    ok = maxd < 1e-9
    all_ok = all_ok and ok
    post = py[ts >= HIST_SEC]
    print(f"  {'✅' if ok else '❌'} {tag}: 样本 {len(py)}  最大偏差 {maxd:.2e}  "
          f"[基准段中位 {np.median(post):.3f} 触顶 {np.mean(post>=0.999)*100:.1f}%]")

# 清理临时文件（agent 自产物，显式列出）
for p in [in_path, node_path, os.path.join(OUT, "_equiv_js_out.json")]:
    if os.path.exists(p):
        os.remove(p)

print("\n" + "=" * 76)
print("结论：" + ("✅ JS 移植与 Python 验证基准逐点一致，移植可信" if all_ok
                 else "❌ 存在偏差，移植有逻辑错误，禁止交付实机"))
print("=" * 76)
sys.exit(0 if all_ok else 1)
