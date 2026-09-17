"""V2 步骤3 验收：Worklet 源码独立语法校验 + 合成等价性验证

两个必查项：
① WORKLET_SRC 是字符串数组 join 成的 JS，页面级 node --check 覆盖不到它
   （字符串内容不参与外层语法解析）。若其语法错，运行时会静默失败（无声音）。
② 合成结果须与后端 IsoEngine 等价——否则"复用决策层"就名不副实，
   法师听到的声音会与闭环实验路径不一致。
"""
import os, re, json, subprocess, sys
import numpy as np

BASE = r"C:\Users\tiand\OneDrive\zhiguanAI"
OUT = os.path.join(BASE, "output", "20260910_VR标准模板三重分析")
HTML = os.path.join(BASE, "vr_feedback.html")
sys.path.insert(0, BASE)

html = open(HTML, encoding="utf-8").read()

# ── ① 提取 WORKLET_SRC 并求值成真实 JS 源码 ──
m = re.search(r"const WORKLET_SRC = \[([\s\S]*?)\]\.join\('\\n'\);", html)
if not m:
    print("❌ 无法提取 WORKLET_SRC")
    sys.exit(1)
body = m.group(1)
# 解析 JS 字符串数组为 Python 列表（每行是 'xxx',）
lines = re.findall(r"^\s*'((?:[^'\\]|\\.)*)',?\s*$", body, re.M)
if not lines:
    print("❌ WORKLET_SRC 字符串数组解析失败")
    sys.exit(1)
worklet_js = "\n".join(lines)
print(f"提取到 Worklet 源码 {len(lines)} 行，{len(worklet_js)} 字符")

# 语法校验（AudioWorkletProcessor/sampleRate 是 worklet 全局，node 不认识但只查语法）
wrap = ("class AudioWorkletProcessor { constructor(){} }\n"
        "const sampleRate = 48000;\n"
        "function registerProcessor(){}\n" + worklet_js)
tmp = os.path.join(OUT, "_worklet_check.cjs")
open(tmp, "w", encoding="utf-8").write(wrap)
r = subprocess.run(["node", "--check", tmp], capture_output=True, text=True)
if r.returncode != 0:
    print("❌ Worklet 语法错误（运行时会静默无声音）：")
    print(r.stderr[:900])
    os.remove(tmp)
    sys.exit(1)
print("✅ Worklet 源码语法通过")

# ── ② 合成等价性：JS Worklet vs 后端 IsoEngine 逐样本对比 ──
# 用 node 跑 Worklet 的 process()，用 Python 跑 IsoEngine 的 _callback 逻辑
SR = 48000
CARRIER = 220.0
BEAT = 10.0
VOL = 0.30
LIMIT = 0.0002
NBUF = 128          # AudioWorklet 标准 render quantum
NBUF_PY = 128       # 后端回调块大小同取 128，保证可比
NBLOCKS = 384       # 384×128 = 49152 样本 ≈ 1.02 秒 ≈ 10 个节拍周期
                    # （原先只取 8 块＝1024 样本＝21ms，不足半个 10Hz 周期，
                    #  致"占空比应≈50%"判据失效——窗口内 sin 恒正属正常）

# JS 侧：驱动 Worklet 处理 8 个 buffer（1024 样本）
driver = f"""
const fs = require('fs');
// 真实 AudioWorkletProcessor 基类提供 this.port（MessagePort），测试桩须模拟
class AudioWorkletProcessor {{
  constructor() {{ this.port = {{ onmessage: null, postMessage: function(){{}} }}; }}
}}
const sampleRate = {SR};
function registerProcessor(name, cls) {{ global.__P = cls; }}
{worklet_js}
const p = new global.__P();
// 直接设定合成参数（等价于 onmessage 收到 audioPush 的 postMessage）
p.beat = {BEAT}; p.carrier = {CARRIER}; p.vol = {VOL}; p.limit = {LIMIT};
const out = [];
for (let b = 0; b < {NBLOCKS}; b++) {{
  const ch0 = new Float64Array({NBUF});
  const outputs = [[ch0]];
  p.process([], outputs);
  for (let i = 0; i < {NBUF}; i++) out.push(ch0[i]);
}}
fs.writeFileSync({json.dumps(os.path.join(OUT, "_wl_out.json"))}, JSON.stringify(out));
console.log("js samples:", out.length);
"""
drv = os.path.join(OUT, "_wl_drive.cjs")
open(drv, "w", encoding="utf-8").write(driver)
r = subprocess.run(["node", drv], capture_output=True, text=True)
if r.returncode != 0:
    print("❌ Worklet 驱动失败："); print(r.stderr[:900])
    for p in (tmp, drv):
        if os.path.exists(p): os.remove(p)
    sys.exit(1)
print(r.stdout.strip())
js_out = np.asarray(json.load(open(os.path.join(OUT, "_wl_out.json"), encoding="utf-8")))

# Python 侧：复刻 IsoEngine._callback 的数学（不启动音频设备）
# carry 参数区分两种相位携带方式：
#   'iso'   = 后端 IsoEngine 原样：ph_c = ph_c[-1]（index n-1）→ 每块重复一个样本
#   'exact' = 相位连续：下块从 index n 开始（Worklet 采用的方式）
def py_iso(n_total, sr, carrier, beat, vol, limit, frames, carry='iso'):
    TWO_PI = 2.0 * np.pi
    ph_c = ph_m = 0.0
    cur = 0.0
    sig_all = []
    produced = 0
    step_c = TWO_PI * carrier / sr
    step_m = TWO_PI * beat / sr
    while produced < n_total:
        n = min(frames, n_total - produced)
        idx = np.arange(n)
        pc = ph_c + step_c * idx
        pm = ph_m + step_m * idx
        mod = np.maximum(np.sin(pm), 0.0)
        env = np.power(mod, 0.6)
        dv = vol - cur
        mx = limit * n
        if abs(dv) > mx:
            dv = mx if dv > 0 else -mx
        vt = cur + dv * (idx + 1) / n
        sig_all.append(np.sin(pc) * env * vt)
        if carry == 'iso':
            ph_c = float(pc[-1]) % TWO_PI      # 后端原样：丢一个样本的相位
            ph_m = float(pm[-1]) % TWO_PI
        else:
            ph_c = float(pc[-1] + step_c) % TWO_PI   # 相位连续
            ph_m = float(pm[-1] + step_m) % TWO_PI
        cur += dv
        produced += n
    return np.concatenate(sig_all)

py_iso_like = py_iso(len(js_out), SR, CARRIER, BEAT, VOL, LIMIT, NBUF_PY, 'iso')
py_exact = py_iso(len(js_out), SR, CARRIER, BEAT, VOL, LIMIT, NBUF_PY, 'exact')

d_iso = float(np.abs(js_out - py_iso_like).max())
d_exact = float(np.abs(js_out - py_exact).max())
rms_js = float(np.sqrt(np.mean(js_out ** 2)))
print(f"\n逐样本对比 {len(js_out)} 个样本（≈{len(js_out)/SR:.2f} 秒）：")
print(f"  vs 后端 IsoEngine 原样复刻 : 最大偏差 {d_iso:.3e}")
print(f"  vs 相位连续参考实现        : 最大偏差 {d_exact:.3e}")
print(f"  JS 信号 RMS {rms_js:.4f}，值域 [{js_out.min():.4f}, {js_out.max():.4f}]（应在 ±{VOL} 内）")

# 关键特性核查（窗口已加长，占空比判据此时有效）
nz = float(np.mean(np.abs(js_out) > 1e-6))
print(f"  包络非零占比 {nz*100:.1f}%（等时节拍 50% 占空比 → 应≈50%，含爬升期）")
from scipy.signal import find_peaks
pk, _ = find_peaks(np.abs(js_out), distance=int(SR / BEAT * 0.7))
if len(pk) > 2:
    period = float(np.median(np.diff(pk)))
    print(f"  检出节拍峰 {len(pk)} 个，实测周期 {period:.0f} 样本 = {SR/period:.3f}Hz（设定 {BEAT}Hz）")
    beat_ok = abs(SR / period - BEAT) < 0.15
else:
    beat_ok = False
    print(f"  ⚠️ 节拍峰检出不足({len(pk)})")

# 判定：与相位连续参考一致 + RMS 非空 + 节拍频率正确
ok = d_exact < 1e-9 and rms_js > 0.01 and beat_ok
print("\n" + "=" * 70)
if ok:
    print("结论：✅ Worklet 与「相位连续」参考逐样本一致，节拍频率准确")
    if d_iso > 1e-6:
        print(f"⚠️ 但与后端 IsoEngine 原样实现存在偏差 {d_iso:.3e}")
        print("   根因：IsoEngine 写 ph_c[-1]（index n-1）作下一块起点，")
        print("   等于每块重复一个样本 → 载波被轻微降频并产生块边界相位不连续。")
        print("   Worklet 采用相位连续（正确做法）。这是后端既有实现的 off-by-one，")
        print("   非本次移植引入；是否回改 IsoEngine 须法师裁定（改动影响闭环实验路径）。")
else:
    print(f"结论：❌ 未通过（d_exact={d_exact:.3e}, rms={rms_js:.4f}, beat_ok={beat_ok}），禁止交付")
print("=" * 70)

for p in [tmp, drv, os.path.join(OUT, "_wl_out.json")]:
    if os.path.exists(p):
        os.remove(p)
sys.exit(0 if ok else 1)
