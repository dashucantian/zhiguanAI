# -*- coding: utf-8 -*-
"""8779 场景控制台静态闸（方案A「莲池夜观」线）2026-11-03 Qoder 窗 c73afab0

依据：W3 任务书 TASK-20261103-02 丙案四条判据。全静态：不起服务、不连头显、不出网。

判据（每条附证伪句；读不到一律 FAIL，不许写成 PASS）：
 1. 三预设资产齐
    vr_assets/models/presets/A-静坐.json／A-观想.json／A-空境.json 三件在盘，
    params 下必需字段 scene／dist／breath／groundMode／fog／bloom 齐且类型对。
    证伪句：任一文件缺失、JSON 解析失败、必需字段缺失或类型不符 → FAIL。
 2. 金线主调
    环线材质颜色由 cGrid 驱动（ringMat 以 R.cGrid 初始化 ＋ c_grid→cGrid 绑定），
    且三件 A 预设的 cGrid 均等于 #d4af5a。
    证伪句：代码中找不到这两处绑定，或任一预设 cGrid ≠ #d4af5a → FAIL。
    说明（观察项、不作 PASS 依据）：控制台自身默认 cGrid 为 #3b4666；
    金线主调是「载入 A 预设后」的效果——此口径差已如实打印，待 W3 定。
 3. 上限纪律
    三预设 fog ≤ 0.045、orbit == 0；控制台 grain 滑杆上限 ≤ 0.30 且默认值 ≤ 0.30。
    证伪句：任一预设 fog 越界或 orbit ≠ 0，或 grain 上限/默认越界，或任一值读不到 → FAIL。
 4. 后处理不进 XR
    渲染分支中后处理开关须带 renderer.xr.isPresenting 的否定条件（XR 内跳过）。
    证伪句：找不到带 !renderer.xr.isPresenting 的后处理开关判断 → FAIL。

⚠ 覆盖限制（必须保留）：本闸读的两处都不入库——
  output/_scene_env.html（.gitignore:75）
  vr_assets/models/presets/*.json（.gitignore:77）
⇒ 只在有这两处的本机能跑，clone 后不可复现。主树根默认取
  `git worktree list --porcelain` 首项（即在 worktree 内运行也能定位素材），--root 可覆盖。

用法：python vr_gates/verify_scene_env.py [--root D:\\Project\\zhiguanAI]
退出码：0 四判据全过 / 1 任一 FAIL
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

PRESETS = ["A-静坐", "A-观想", "A-空境"]
REQUIRED = ["scene", "dist", "breath", "groundMode", "fog", "bloom"]
NUMERIC = {"dist", "breath", "fog", "bloom"}
FOG_MAX = 0.045
GRAIN_MAX = 0.30
GOLD = "#d4af5a"

fails = []


def check(cond, ok, bad):
    print(("  ✅ " if cond else "  ❌ ") + (ok if cond else bad))
    if not cond:
        fails.append(bad)


def main_root(explicit):
    if explicit:
        return Path(explicit)
    try:
        out = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            capture_output=True, text=True, timeout=15, check=True
        ).stdout
        for line in out.splitlines():
            if line.startswith("worktree "):
                return Path(line[len("worktree "):].strip())
    except Exception as e:  # noqa: BLE001
        print(f"  ❌ 无法经 git 定位主树：{e}")
        fails.append("主树定位失败")
    return None


def load_presets(root):
    data = {}
    for name in PRESETS:
        p = root / "vr_assets" / "models" / "presets" / f"{name}.json"
        if not p.is_file():
            print(f"  ❌ 缺件：{p}")
            fails.append(f"缺预设 {name}")
            continue
        try:
            data[name] = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            print(f"  ❌ 解析失败：{p}：{e}")
            fails.append(f"预设 {name} 解析失败")
    return data


def j1(presets):
    print("[判据1] 三预设资产齐")
    for name in PRESETS:
        d = presets.get(name)
        if d is None:
            continue
        params = d.get("params") or {}
        missing = [k for k in REQUIRED if k not in params]
        bad_type = [k for k in REQUIRED if k in params and (
            (k in NUMERIC and not isinstance(params[k], (int, float))) or
            (k not in NUMERIC and not isinstance(params[k], str)))]
        check(not missing and not bad_type,
              f"{name}：六字段齐、类型对",
              f"{name}：缺 {missing}／类型错 {bad_type}")


def j2(presets, html):
    print("[判据2] 金线主调")
    ring = re.search(r"ringMat\s*=\s*new\s+THREE\.MeshBasicMaterial\(\{[^}]*new\s+THREE\.Color\(R\.cGrid\)", html)
    bind = re.search(r"col\('c_grid'\s*,\s*'cGrid'", html)
    check(bool(ring), "ringMat 以 R.cGrid 初始化", "找不到 ringMat 颜色由 R.cGrid 驱动")
    check(bool(bind), "c_grid 滑杆绑定 cGrid", "找不到 col('c_grid','cGrid',…) 绑定")
    for name in PRESETS:
        d = presets.get(name)
        if d is None:
            continue
        c = ((d.get("params") or {}).get("cGrid") or "").lower()
        check(c == GOLD, f"{name} cGrid={c or '缺'}", f"{name} cGrid={c or '缺'}，应为 {GOLD}")
    m = re.search(r"cGrid:\s*'([^']+)'", html)
    if m:
        print(f"  ⓘ 观察：控制台默认 cGrid={m.group(1)}（金线主调仅在载入 A 预设后生效）")


def j3(presets, html):
    print("[判据3] 上限纪律")
    for name in PRESETS:
        d = presets.get(name)
        if d is None:
            continue
        params = d.get("params") or {}
        fog, orbit = params.get("fog"), params.get("orbit")
        check(isinstance(fog, (int, float)) and fog <= FOG_MAX,
              f"{name} fog={fog} ≤ {FOG_MAX}", f"{name} fog={fog} 越界或读不到（上限 {FOG_MAX}）")
        check(isinstance(orbit, (int, float)) and abs(orbit) < 1e-9,
              f"{name} orbit={orbit} == 0", f"{name} orbit={orbit} ≠ 0 或读不到")
    m = re.search(r'id="grain"[^>]*max="([\d.]+)"[^>]*value="([\d.]+)"', html)
    if not m:
        check(False, "", "找不到 grain 滑杆 max/value")
    else:
        mx, dv = float(m.group(1)), float(m.group(2))
        check(mx <= GRAIN_MAX + 1e-9, f"控制台 grain 上限={mx} ≤ {GRAIN_MAX}", f"控制台 grain 上限={mx} 越界（上限 {GRAIN_MAX}）")
        check(dv <= GRAIN_MAX + 1e-9, f"控制台 grain 默认={dv} ≤ {GRAIN_MAX}", f"控制台 grain 默认={dv} 越界（上限 {GRAIN_MAX}）")


def j4(html):
    print("[判据4] 后处理不进 XR")
    m = re.search(r"wantPost\s*=\s*[^\n]*!renderer\.xr\.isPresenting", html)
    check(bool(m), "后处理开关含 !renderer.xr.isPresenting（XR 内跳过）",
          "找不到带 !renderer.xr.isPresenting 的后处理开关")
    check("renderer.xr.enabled" in html, "renderer.xr.enabled 在位", "找不到 renderer.xr.enabled")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None, help="主树根（默认取 git worktree list 首项）")
    args = ap.parse_args()

    root = main_root(args.root)
    if root is None or not root.is_dir():
        print("❌ 主树根不可用，全闸不作数")
        return 1
    print(f"主树：{root}")
    scene = root / "output" / "_scene_env.html"
    if not scene.is_file():
        print(f"  ❌ 缺件：{scene}")
        print("结论：FAIL（读不到控制台件，按判据不许写成 PASS）")
        return 1
    html = scene.read_text(encoding="utf-8", errors="replace")
    print(f"控制台件：{scene}（{len(html)} 字符）")

    presets = load_presets(root)
    j1(presets)
    j2(presets, html)
    j3(presets, html)
    j4(html)

    ok = not fails
    print("结论：" + ("PASS（四判据全过）" if ok else f"FAIL（{len(fails)} 项）"))
    print("覆盖限制：本闸读 output/_scene_env.html 与 vr_assets/models/presets/*.json，"
          "二者均不入库（.gitignore:75／:77）⇒ 只在本机可跑，clone 后不可复现。")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())