# vr_gates 正本·2026-09-30 W1 造（ZG-078 S2 空间呼吸施工配套闸）
"""曼荼罗场域 · S2 空间呼吸验收（CDP 无头 Edge）

规格：01_项目管理/20260917_曼荼罗场域S2空间呼吸规格_v1.md §四 判据 1~4
（判据 5~7＝去视觉/心率/D 级体感，唯一判据源是法师 Pico 真机，脚本不可替代——
 如实不判，见末尾"未验证项"）。

判据（本脚本）：
  1. 回归锚未破：?breath=off（S1"绝对安静"显式关断）stage=S1/static=true，
     两帧差（2.5s）≤ 1.0/255 —— S1 判据照规格 §三.4 保持可复跑；
     另断言默认 URL（不带参数）breath.enabled=true——默认翻转（2026-10-01
     法师真机验收后金口「翻为开」）如实生效
  2. 呼吸存在：?breath=on 时 stage=S2/static=false/breath.enabled=true，
     三对帧差（各 2.5s，取最大）∈ [0.008, 0.30]/255
     （〔校准追认〕规格原提案下限 0.02 对 2.5s 采样窗反推有误，首跑实测 0.0150，
      依规格 §七"提案值实测后可调、调整须留痕"条款校准为 0.008；
      2026-10-01 法师金口「是」追认）
  3. 无跳变：?breath=on 连续 12 帧（约 0.6s 间隔）相邻帧差全部 ≤ 0.05/255
  4. 周期可检出：?breath=on 全帧平均亮度序列（≥50s 实测时间戳）自相关峰
     落在雾通道设定周期 ±15%（证"是呼吸不是噪声"）

用法：python vr_gates/verify_mandala_breath.py
前置：console_server 在 8777 运行（/mandala 路由）
产物：output/20260930_S2呼吸/（off/on 两对帧＋亮度序列 CSV）
"""
import asyncio
import base64
import csv
import json
import os
import subprocess
import sys
import time

EDGE = next((p for p in [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"]
    if os.path.exists(p)), None)
PORT = 9347
BASE = "http://127.0.0.1:8777/mandala"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.environ.get("MANDALA_OUT") or os.path.join(_ROOT, "output", "20260930_S2呼吸")
os.makedirs(OUT, exist_ok=True)

fails = []


def check(cond, ok_msg, fail_msg):
    if cond:
        print(f"  ✅ {ok_msg}")
    else:
        print(f"  ❌ {fail_msg}")
        fails.append(fail_msg)


_id = 0


async def send(ws, method, params=None):
    global _id
    _id += 1
    await ws.send(json.dumps({"id": _id, "method": method,
                              "params": params or {}}))
    while True:
        msg = json.loads(await ws.recv())
        if msg.get("id") == _id:
            return msg


async def evaluate(ws, expr):
    r = await send(ws, "Runtime.evaluate",
                   {"expression": expr, "returnByValue": True, "awaitPromise": True})
    return r.get("result", {}).get("result", {}).get("value")


async def navigate_wait(ws, url):
    await send(ws, "Page.navigate", {"url": url})
    for _ in range(60):
        await asyncio.sleep(0.5)
        if await evaluate(ws, "document.getElementById('load').style.display") == "none":
            break
    await asyncio.sleep(2.0)


async def shot(ws, name):
    r = await send(ws, "Page.captureScreenshot", {"format": "png"})
    import numpy as np
    from PIL import Image
    raw = base64.b64decode(r["result"]["data"])
    return np.asarray(Image.open(io_bytes(raw)).convert("RGB")).astype(np.int16)


def io_bytes(b):
    import io
    return io.BytesIO(b)


async def main():
    print("=" * 70)
    print("S2 曼荼罗空间呼吸验收 · CDP 无头 Edge（规格 §四 判据 1~4）")
    print("=" * 70)

    proc = subprocess.Popen([
        EDGE, "--headless=new", f"--remote-debugging-port={PORT}",
        "--window-size=1280,800", "--use-gl=swiftshader",
        "--enable-unsafe-swiftshader", "--no-first-run",
        "--user-data-dir=" + os.path.join(OUT, "_profile"),
        "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        import urllib.request
        targets = None
        for _ in range(60):
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{PORT}/json", timeout=1) as rq:
                    targets = json.loads(rq.read())
                break
            except Exception:
                time.sleep(0.5)
        if not targets:
            print("FAIL: Edge DevTools 未就绪")
            return 1
        page = next((t for t in targets if t["type"] == "page"), targets[0])
        import websockets
        import numpy as np
        ws = await websockets.connect(page["webSocketDebuggerUrl"],
                                      max_size=64 * 1024 * 1024)
        await send(ws, "Page.enable")
        await send(ws, "Runtime.enable")

        # ── 判据 1：回归锚（显式 ?breath=off＝S1 绝对安静，规格 §三.4）──
        print("\n── 判据 1：回归锚未破（?breath=off 显式关断）────────────")
        await navigate_wait(ws, BASE + "?variant=s1&breath=off")
        d = json.loads(await evaluate(ws, "JSON.stringify(window.__mandalaDiag||null)") or "null")
        check(bool(d) and d.get("stage") == "S1", "stage=S1（关断后静态自声明）",
              f"breath=off stage 异常：{d and d.get('stage')}")
        check(bool(d) and d.get("static") is True, "static=true（回归锚自声明）",
              "breath=off static 非 true")
        check(bool(d) and (d.get("breath") or {}).get("enabled") is False,
              "breath.enabled=false（显式关断，诊断钩子如实）", "breath=off 但钩子报开启")
        a1 = await shot(ws, "off_a")
        await asyncio.sleep(2.5)
        a2 = await shot(ws, "off_b")
        mad1 = float(np.abs(a1 - a2).mean())
        check(mad1 <= 1.0, f"breath=off 两帧差 {mad1:.4f}/255 ≤1.0（绝对安静保持）",
              f"回归锚破坏：off 两帧差 {mad1:.4f}")

        # 默认翻转断言（2026-10-01 法师金口「翻为开」）：裸 URL 应呼吸着
        print("\n── 判据 1b：默认翻转（裸 URL 缺省＝呼吸开）────────────")
        await navigate_wait(ws, BASE + "?variant=s1")
        d0 = json.loads(await evaluate(ws, "JSON.stringify(window.__mandalaDiag||null)") or "null")
        check(bool(d0) and (d0.get("breath") or {}).get("enabled") is True,
              "裸 URL breath.enabled=true（默认已翻为开，法师 2026-10-01 金口）",
              "裸 URL breath 仍是关——默认翻转未生效")
        check(bool(d0) and d0.get("static") is False,
              "裸 URL static=false（缺省即 S2）", "裸 URL static 仍为 true")

        # ── 判据 2：呼吸存在 ─────────────────────────────────────────
        print("\n── 判据 2：呼吸存在（?breath=on，两帧差双边界）────────────")
        await navigate_wait(ws, BASE + "?variant=s1&breath=on")
        d2 = json.loads(await evaluate(ws, "JSON.stringify(window.__mandalaDiag||null)") or "null")
        b = (d2 or {}).get("breath") or {}
        check((d2 or {}).get("stage") == "S2", "stage=S2（呼吸开启自声明）",
              f"breath=on stage 异常：{d2 and d2.get('stage')}")
        check((d2 or {}).get("static") is False, "static=false（S2 不再静态）",
              "breath=on static 仍为 true——呼吸未生效")
        check(b.get("enabled") is True, "breath.enabled=true（钩子如实）",
              "breath=on 但钩子报 enabled=false")
        # 钩子参数对规格逐值复算（防钩子自述漂移）
        if b.get("enabled"):
            fog_c = b.get("fog") or {}
            op_c = b.get("opacity") or {}
            gl_c = b.get("glow") or {}
            spec_ok = (abs(fog_c.get("amp", -1) - 0.0040) < 1e-9
                       and fog_c.get("period") == 34
                       and abs(op_c.get("amp", -1) - 0.04) < 1e-9
                       and op_c.get("period") == 26
                       and (op_c.get("layerPhasesDeg") or []) == [0, 120, 240]
                       and abs(gl_c.get("amp", -1) - 0.04) < 1e-9
                       and gl_c.get("period") == 13)
            check(spec_ok,
                  f"三通道参数与规格逐值一致（雾 ±{fog_c.get('amp')}／{fog_c.get('period')}s · "
                  f"明暗 ±{op_c.get('amp')}／{op_c.get('period')}s 错相 {op_c.get('layerPhasesDeg')}° · "
                  f"光晕 ±{gl_c.get('amp')}／{gl_c.get('period')}s）",
                  f"呼吸参数与规格不符：fog={fog_c} opacity={op_c} glow={gl_c}")
        b1 = await shot(ws, "on_a")
        await asyncio.sleep(2.5)
        b2 = await shot(ws, "on_b")
        # 相位去运气：三对采样（间隔 ~7s，各对内 2.5s）取最大——正弦斜率随相位变，
        # 单对会受相位 luck 支配（理论单对上限 ≈ 全摆幅 0.08 × sin(π·2.5/26) ≈ 0.024）
        mad_pairs = [float(np.abs(b1 - b2).mean())]
        for _ in range(2):
            await asyncio.sleep(7.0)
            c1 = await shot(ws, "on_c")
            await asyncio.sleep(2.5)
            c2 = await shot(ws, "on_d")
            mad_pairs.append(float(np.abs(c1 - c2).mean()))
        mad2 = max(mad_pairs)
        # 〔判据校准·已追认〕规格 §七"提案值实测后可调"条款：下限 0.02→0.008；
        # 规格自己的量级论证给全周期峰谷 0.08/255（通道乙 ±4%），2.5s 采样窗
        # 单对理论上限 ≈0.024（sin(π·2.5/26)×0.08），随机相位下 0.01x 属正常——
        # 首跑实测 0.0150 被旧下限误杀，呼吸本体已由判据 4 自相关 r=0.91 独立证实。
        # 上限 0.30 不动。校准已由法师 2026-10-01 金口「是」追认（D 分片登记）。
        check(0.008 <= mad2 <= 0.30,
              f"breath=on 三对帧差最大 {mad2:.4f}/255 ∈ [0.008, 0.30]（呼吸存在且不过头）",
              f"呼吸存在判据失败：三对帧差 {['%.4f' % m for m in mad_pairs]}"
              + ("（低于下限——幅度被吃掉或通道未生效）" if mad2 < 0.008
                 else "（高于上限——违反'稳'）"))

        # ── 判据 3：无跳变（连续 12 帧相邻帧差）──────────────────────
        print("\n── 判据 3：无跳变（连续帧序列）────────────────────────")
        anchor = await shot(ws, "seq_anchor")   # 现抓锚点：参照帧必须与序列连续，
        prev = anchor                           # 不得复用判据 2 的旧帧（中间隔数十秒，
        prev_t = time.time()                    # 会被误判成"跳变"——首跑 0.0656 即此因）
        max_adj = 0.0
        pair_log = []
        for i in range(11):
            await asyncio.sleep(0.6)
            cur = await shot(ws, f"seq_{i:02d}")
            now = time.time()
            dt_gap = now - prev_t
            adj = float(np.abs(prev - cur).mean())
            pair_log.append((i, dt_gap, adj))
            max_adj = max(max_adj, adj)
            prev, prev_t = cur, now
        for i, dt_gap, adj in pair_log:
            print(f"      对{i:02d} Δt={dt_gap:.2f}s MAD={adj:.4f}")
        check(max_adj <= 0.05,
              f"连续 12 帧相邻帧差最大 {max_adj:.4f}/255 ≤0.05（连续无跳变）",
              f"检出跳变：相邻帧差 {max_adj:.4f} > 0.05（相位重置类代码错误）")

        # ── 判据 4：周期可检出（亮度序列自相关）──────────────────────
        print("\n── 判据 4：周期可检出（≥50s 亮度序列自相关，雾通道 34s±15%）──")
        expect_period = (b.get("fog") or {}).get("period") or 34
        ts, lum_series = [], []
        t0 = time.time()
        while time.time() - t0 < 55.0:
            img = await shot(ws, "series")
            lum_series.append(float(img.mean()))
            ts.append(time.time() - t0)
            await asyncio.sleep(0.35)
        # 实测时间戳 → 归一化自相关（滞后按真实秒计，容采集抖动）
        n = len(lum_series)
        x = np.asarray(lum_series)
        x = (x - x.mean()) / (x.std() + 1e-12)
        lo, hi = expect_period * 0.85, expect_period * 1.15
        band_r, band_lag = [], []
        for lag_s in [s for s in [i * 0.5 for i in range(10, 110)] if s <= ts[-1] - 6]:
            pairs = [(x[i], x[j]) for i in range(n) for j in range(n)
                     if 0 < ts[j] - ts[i] and abs((ts[j] - ts[i]) - lag_s) <= 0.35]
            if len(pairs) < 30:
                continue
            aa = np.asarray([p[0] for p in pairs])
            bb = np.asarray([p[1] for p in pairs])
            r = float((aa * bb).mean())
            if lo <= lag_s <= hi:
                band_r.append(r)
                band_lag.append(lag_s)
        r_best = max(band_r) if band_r else 0.0
        lag_best = band_lag[band_r.index(r_best)] if band_r else 0.0
        peak_in_band = r_best > 0.2   # 带内显著峰（SNR 论证见规格 §二量级；判据＝落在带内且显著）
        check(peak_in_band,
              f"自相关峰 lag≈{lag_best:.1f}s（r={r_best:.2f}）落在设定周期 "
              f"{expect_period}s±15%（{lo:.1f}~{hi:.1f}s）——是呼吸不是噪声",
              f"带内 [{lo:.1f}~{hi:.1f}s] 未检出显著自相关峰（带内最大 r={r_best:.3f}）"
              f"——周期不可检出，序列长 {ts[-1]:.0f}s/{n} 样本")
        # 亮度序列留档（证据产物，可复算）
        with open(os.path.join(OUT, "亮度序列.csv"), "w", newline="", encoding="utf-8") as f:
            wcsv = csv.writer(f)
            wcsv.writerow(["t_s", "mean_lum"])
            wcsv.writerows(zip([f"{t:.2f}" for t in ts],
                               [f"{v:.4f}" for v in lum_series]))

        await ws.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

    print("\n" + "=" * 70)
    if fails:
        print(f"❌ FAIL {len(fails)} 项：")
        for f in fails:
            print(f"   - {f}")
        return 1
    print("✅ PASS：S2 呼吸脚本判据 1~4 全通过")
    print(f"   产物：{OUT}\\（off/on 帧对＋亮度序列.csv）")
    print("\n⚠️ 如实标注的未验证项（规格 §四 判据 5~7，脚本不可替代）：")
    print("   ⑤ 去视觉测试 ⑥ 心率原则（更安静） ⑦ D 级体感「说不出哪里在动，但觉得活着」")
    print("   —— 唯一判据源＝法师 Pico 真机（2026-10-01 真机三格全过：A 还在／B 更安静／C 原话留档）")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
