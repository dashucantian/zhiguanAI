"""V2 步骤4 验收：四维分工落地核查 + 周期互质量化

对齐方案 §3.2 映射架构要求「四者周期须互质或成简单整数比，避免同步造成的
机械感与拍频闪动」。本脚本不靠目测，直接从 vr_feedback.html 提取真实参数算：
  ① 四维是否都已落地（底色/中程/短程/现实锚）
  ② 各维实际周期
  ③ 两两周期比是否为无理数附近（互质判据：比值远离简单整数比）
  ④ 帧率无关性（VR 90fps vs 桌面 60fps 是否同效）
"""
import os, re, sys, json
from fractions import Fraction
import numpy as np

BASE = r"C:\Users\tiand\OneDrive\zhiguanAI"
HTML = os.path.join(BASE, "vr_feedback.html")
OUT = os.path.join(BASE, "output", "20260910_VR标准模板三重分析")
html = open(HTML, encoding="utf-8").read()

def num(pattern, label, default=None):
    m = re.search(pattern, html)
    if not m:
        print(f"  ⚠️ 未提取到 {label}")
        return default
    return float(m.group(1))

print("=" * 78)
print("V2 步骤4 验收：四维分工 + 周期互质量化")
print("=" * 78)

# ── ① 提取四维参数 ──
theme_tau = num(r"const THEME = \{ tau: ([\d.]+)", "THEME.tau")
algo_tau = num(r"tau: ([\d.]+),\s*// EMA 时间常数", "ALGO.tau")
guide_bpm = num(r"bpm: (\d+),", "GUIDE.bpm")
anchor_period = num(r"period: (\d+),", "ANCHOR.period")
water_speed = num(r"waterU\.uT\.value = .*?: t\*([\d.]+)", "水面速度系数")

print("\n【维度落地核查】")
dims = [
    ("① 底色（状态色调/空间氛围）", theme_tau, "THEME.tau", "最慢层，分钟级"),
    ("② 中程（S.a/S.th 脑电）", algo_tau, "ALGO.tau", "境随心转"),
    ("③ 短程（引导所缘节律）", 60.0/guide_bpm if guide_bpm else None, "60/GUIDE.bpm", "所缘"),
    ("④ 现实锚（真实会话时长）", anchor_period, "ANCHOR.period", "身在此处"),
]
ok_dims = True
for name, period, src, role in dims:
    if period is None:
        print(f"  ❌ {name}: 未落地（缺 {src}）"); ok_dims = False
    else:
        print(f"  ✅ {name}: 周期 {period:.1f} 秒  [{src}]  角色＝{role}")

# ── ② 水面分量周期（着色器内 uT 乘不同系数）──
print("\n【水面分量周期】（uT = t × %.2f，着色器内再乘各系数）" % (water_speed or 0.4))
shader_coeffs = re.findall(r"uT\*([\d.]+)", html)
water_periods = []
for c in sorted(set(shader_coeffs), key=float):
    c = float(c)
    # uT*coef 的相位完成 2π 需要 t*speed*coef = 2π → 周期 = 2π/(speed*coef)
    per = 2*np.pi/((water_speed or 0.4)*c)
    water_periods.append(per)
    print(f"  uT*{c}: 周期 {per:.1f} 秒")

# ── ③ 互质判据（2026-09-11 修正：原判据物理上错误）──
# 错误1：把 THEME.tau / ALGO.tau 当振荡周期参与互质比对。
#        它们是**低通滤波时间常数**（指数趋近目标值），不是振荡器，
#        不存在"相位对齐/拍频"问题 → 不得参与互质核查。
# 错误2：对齐方案原话是「须互质**或成简单整数比**」，脚本却把简单整数比
#        判为失败，自相矛盾。
# 修正后判据：只对**真振荡器**（sin 驱动）核查，且只在**同一视觉通道**上
#        接近简单整数比才算问题（不同通道不竞争，不构成可感拍频）。
print("\n【周期互质核查】（修正判据：只查同通道真振荡器）")
print("  排除项：THEME.tau(60s)/ALGO.tau(12s) 是低通滤波时间常数，非振荡器")
# 真振荡器 → 所属视觉通道（按着色器阶段与空间频率精确分组，2026-09-11 二次修正）
# 原判据把四个水面分量笼统归为"同为水面视觉"，过粗：
#   uT*0.30 → 顶点位移 sin(p.x*0.8)   空间频率 0.8（宏观方向波，振幅 .03*uTh）
#   uT*0.50 → 顶点位移 sin(r*1.6)     空间频率 1.6（宏观径向环，振幅 .05+.16*uA）
#   uT*0.45 → 片元颜色 sin(vUv.x*60)  空间频率 60（微观细纹理，振幅 .06*uTh）
#   uT*0.55 → 片元颜色 sin(r*22)      空间频率 22（微观环形纹，振幅 .5+.5*）
# 顶点位移与片元颜色是**不同渲染阶段**，空间频率相差最多 75 倍 → 不竞争同一
# 感知通道，不构成可感拍频。只有同阶段且空间频率相近者才真正叠加。
CHANNELS = {
    0.30: ("顶点位移", 0.8, "宏观方向波"),
    0.50: ("顶点位移", 1.6, "宏观径向环"),
    0.45: ("片元颜色", 60.0, "微观细纹理"),
    0.55: ("片元颜色", 22.0, "微观环形纹"),
}
oscillators = {
    "引导锚": (60.0/guide_bpm if guide_bpm else None, "orb.scale 光球胀缩"),
    "现实锚": (anchor_period, "water.position.y 水面高度"),
}
for i, p in enumerate(water_periods):
    oscillators[f"水面{i+1}"] = (p, "water shader")

bad = []

# ③a 同阶段同尺度的真叠加对才核查拍频
print("\n  ── 真叠加对核查（同渲染阶段 + 空间频率同量级）──")
coeffs = sorted(set(float(c) for c in shader_coeffs))
found_pair = False
for i in range(len(coeffs)):
    for j in range(i+1, len(coeffs)):
        c1, c2 = coeffs[i], coeffs[j]
        if c1 not in CHANNELS or c2 not in CHANNELS:
            continue
        stage1, sf1, d1 = CHANNELS[c1]
        stage2, sf2, d2 = CHANNELS[c2]
        if stage1 != stage2:
            continue                       # 不同渲染阶段，不叠加
        if max(sf1, sf2)/min(sf1, sf2) > 5:
            continue                       # 空间频率差一个量级以上，不同感知尺度
        found_pair = True
        p1, p2 = water_periods[i], water_periods[j]
        # 拍频周期＝两者相位重新对齐所需时间
        beat = 2*np.pi/abs(c1 - c2)/(water_speed or 0.4)
        r = max(p1, p2)/min(p1, p2)
        fr = Fraction(r).limit_denominator(8)
        print(f"    {stage1} {d1}({p1:.1f}s) vs {d2}({p2:.1f}s)："
              f"周期比 {r:.3f} ≈ {fr.numerator}/{fr.denominator}，拍频周期 {beat:.1f}s")
        # 拍频周期须远长于人类注意窗（~60秒），否则会被感知为规律脉动
        if beat < 60:
            bad.append((d1, d2, beat))
            print(f"      ❌ 拍频周期 {beat:.1f}s < 60s，会被感知为规律脉动")
        else:
            print(f"      ✅ 拍频周期远长于注意窗，不构成可感脉动")
if not found_pair:
    print("    （无同阶段同尺度的叠加对 → 各分量分属不同感知通道）")

# ③b 水面图样的完整重复周期＝各分量周期的最小公倍（"机械感"的物理实质）
print("\n  ── 水面图样完整重复周期（机械感的物理实质）──")
# 分量周期 P_i = 2π/(speed*c_i)；图样重复周期 = 2π/speed × LCM(1/c_i)
from math import gcd
# 有理数 LCM 公式：LCM(a/b, c/d) = LCM(a,c) / GCD(b,d)
# 修正 bug：分母须取 GCD 而非 LCM —— 对 10/3,20/9,2,20/11，
# 分母若取 LCM 会误得 20/99≈0.202 → 重复周期 3.2s（假报警）；
# 正确为分母 GCD → 20/1=20 → 重复周期 314s。
def lcm_frac(vals):
    """有理数列表的最小公倍：LCM(分子) / GCD(分母)"""
    fr = [Fraction(v).limit_denominator(1000) for v in vals]
    num = fr[0].numerator
    den = fr[0].denominator
    for f in fr[1:]:
        num = num * f.numerator // gcd(num, f.numerator)      # 分子 LCM
        den = gcd(den, f.denominator)                          # 分母 GCD
    return num / den
inv_c = [1.0/c for c in coeffs]
repeat = 2*np.pi/(water_speed or 0.4) * lcm_frac(inv_c)
print(f"    分量系数 1/c: {', '.join(f'{v:.4f}' for v in inv_c)}")
print(f"    各分量周期: {', '.join(f'{p:.1f}s' for p in water_periods)}")
print(f"    完整重复周期 = {repeat:.1f} 秒 ≈ {repeat/60:.2f} 分钟")
ATTENTION = 60.0     # 人类注意窗约 60 秒
if repeat > ATTENTION * 4:
    print(f"    ✅ 重复周期 > 注意窗 4 倍（{ATTENTION*4:.0f}s）→ 不会被感知为机械重复")
else:
    bad.append(("水面图样", "重复周期过短", repeat))
    print(f"    ❌ 重复周期仅 {repeat:.0f}s，会被感知为机械循环")

# ③c 跨通道比值（不同通道不竞争，仅记录）
print("\n  ── 跨通道比值（仅记录；不同通道不竞争，不构成可感拍频）──")
cross = [("引导锚", 60.0/guide_bpm if guide_bpm else None)]
for i, p in enumerate(water_periods):
    cross.append((f"水面{i+1}", p))
cross.append(("现实锚", anchor_period))
for i in range(len(cross)):
    for j in range(i+1, len(cross)):
        n1, a = cross[i]; n2, b = cross[j]
        if not a or not b:
            continue
        r = max(a, b)/min(a, b)
        fr = Fraction(r).limit_denominator(8)
        if abs(r - float(fr)) < 0.02 and fr.denominator <= 4:
            print(f"    {n1} / {n2} = {r:.3f} ≈ {fr.numerator}/{fr.denominator}（跨通道，可接受）")

# 排除项声明（THEME.tau/ALGO.tau 是低通时间常数，非振荡器，不参与互质）
print(f"\n  排除项：THEME.tau({theme_tau:.0f}s)、ALGO.tau({algo_tau:.0f}s) 为低通滤波"
      f"时间常数（指数趋近目标值），非振荡器，不存在相位对齐问题")

if bad:
    print(f"\n  ⚠️ {len(bad)} 项同通道拍频/重复周期问题：")
    for b in bad:
        print(f"      {b}")
else:
    print("\n  ✅ 同通道无可感拍频，水面图样重复周期远长于注意窗")

# 引导锚 10 秒是法师依止的节律，重点看它与水面的关系
if guide_bpm:
    g = 60.0/guide_bpm
    print(f"\n【引导锚({g:.0f}秒) 与各水面分量之比】")
    for i, p in enumerate(water_periods):
        print(f"  水面{i+1}({p:.1f}s) / 引导锚 = {p/g:.3f}")

# ── ④ 帧率无关性核查（2026-09-11 三次修正）──
print("\n【帧率无关性】（VR 90fps vs 桌面 60fps 须同效）")
# 修正1：原写法扫描含注释的 html，会把历史注释里的 .04 误报为残留代码。
# 修正2：原判据"suspect＝排除 inhale/0.35"过于粗糙，靠字符串碰运气。正确判据：
#   累积型 lerp —— 目标对象跨帧保留状态（curCol、uniforms.uX.value），
#                  每帧 X.lerp(target,k) 的结果依赖帧率 → **必须**用 dt 形式
#   静态混合   —— X.copy(base).lerp(target,k)，copy() 每帧重置基准，
#                  结果是当前输入的纯函数，与帧率无关 → 固定系数**无害**
code_only = re.sub(r"/\*[\s\S]*?\*/", "", html)      # 剥离块注释
code_only = re.sub(r"//[^\n]*", "", code_only)        # 剥离行注释

n_dt = code_only.count("1 - Math.exp(-Math.min(dt")
print(f"  帧率无关形式 1-exp(-dt/τ) 出现 {n_dt} 处（EMA + 主题色）")

accum_bad, static_ok = [], []
for ln in code_only.splitlines():
    s = ln.strip()
    for m in re.finditer(r"(\S+?)\.lerp\(\s*([^,]+),\s*([^)]+)\)", s):
        target, arg, factor = m.group(1), m.group(2).strip(), m.group(3).strip()
        is_dt = ("Math.exp" in factor) or ("kt" in factor) or factor.endswith("k")
        prefix = s[:m.start()] + target          # lerp 之前对同一对象的操作
        is_static = ".copy(" in prefix            # 同帧先 copy 重置基准 → 静态混合
        if is_static:
            static_ok.append(s[:88])
        elif is_dt:
            pass                                  # 累积型但已帧率无关 ✅
        else:
            accum_bad.append(f"{target}.lerp(…, {factor})  →  {s[:70]}")

if accum_bad:
    print(f"  ❌ 存在帧率相关的累积型 lerp {len(accum_bad)} 处（VR 下过渡会变快）：")
    for x in accum_bad:
        print(f"      {x}")
    ok_dims = False
else:
    print(f"  ✅ 无帧率相关的累积型 lerp")
    for s in static_ok:
        print(f"     静态混合（每帧从基准重算，帧率无关，固定系数无害）: {s}")

# ── ⑤ 分工正确性：周期须单调分层 ──
print("\n【分工分层核查】（周期须 底色 > 中程 > 短程，否则层级错位）")
if theme_tau and algo_tau and guide_bpm:
    g = 60.0/guide_bpm
    if theme_tau > algo_tau > g:
        print(f"  ✅ {theme_tau:.0f}s(底色) > {algo_tau:.0f}s(中程) > {g:.0f}s(短程) 分层正确")
    else:
        print(f"  ❌ 分层错位: 底色{theme_tau:.0f}s / 中程{algo_tau:.0f}s / 短程{g:.0f}s")
        ok_dims = False

# ── ⑥ 四维变量分工无重叠 ──
print("\n【变量分工核查】（各维须驱动不同视觉通道，避免同向叠加过亮过吵）")
# 修正：原写法把正则串当字面量做 `in html` 判断，含反斜杠的串永不匹配 → 全假阴性。
# 改用 re.search 正确匹配；并对纯字面串用 in。
def has(pattern, literal=False):
    return (pattern in html) if literal else bool(re.search(pattern, html))

checks = {
    "底色→色调/天穹": has(r"curCol\.lerp\(_cCol,\s*kt\)") and has(r"uTop\.value\.lerp\(_cTop"),
    "中程→水面辉光/粒子透明度": has(r"uGlow\.value\s*=\s*\.2\s*\+\s*\.8\*S\.a")
                                and has(r"pMat\.opacity\s*=\s*\.35\s*\+\s*\.55\*S\.a"),
    "中程→雾/粒子漂移(S.th)": has(r"fog\.density\s*=\s*\.020\s*\+\s*\.030\*S\.th"),
    "短程→光球胀缩/明暗": has(r"orb\.scale\.setScalar\(GUIDE\.scale\s*\*\s*pulse\)"),
    "现实锚→水面高度": has(r"water\.position\.y\s*=\s*Math\.sin\(S\.elapsed"),
    # VR 安全：相机位移须仅在非 VR 模式（沉浸式头显下动相机会致晕动）
    "现实锚未动相机(VR安全)": has(r"!renderer\.xr\.isPresenting")
                              and has(r"camera\.position\.y\s*=\s*1\.6"),
    # 帧率无关：剥离注释后须恰有 2 处连续形式（EMA + 主题色）
    "平滑帧率无关(EMA+主题色)": code_only.count("1 - Math.exp(-Math.min(dt") == 2,
}
for name, ok in checks.items():
    print(f"  {'✅' if ok else '❌'} {name}")
    if not ok:
        ok_dims = False

# 注：累积型固定系数 lerp 的残留检查已在 ④ 帧率无关性核查完成（accum_bad
# 列表，且已剥离注释避免误报历史注释里的 .04），此处不再重复扫描。

print("\n" + "=" * 78)
print("结论：" + ("✅ 四维分工落地、周期互质、分层正确、帧率无关" if ok_dims and not bad
                 else "❌ 存在问题，须修正"))
print("=" * 78)
sys.exit(0 if (ok_dims and not bad) else 1)
