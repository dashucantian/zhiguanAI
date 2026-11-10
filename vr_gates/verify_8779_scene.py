# -*- coding: utf-8 -*-
"""8779 莲池夜观（方案A）运行时闸——服务、三态交互、资产三样都拿外部信号验
   2026-11-11 W1·VR 场景设计窗（协调位 W3 `e12943a8` 派工 A 项，法师 11-11 字「要」）

【这份闸补的是哪一格】
   `vr_gates/verify_scene_env.py`（11-03 `5982e58`，Qoder 窗 c73afab0，TASK-20261103-02 丙案）
   已覆盖四道**静态**判据：不起服务、不连头显、只读文件与源码。本闸与之**不重叠**：
   本闸**起服务、开真浏览器、逐态加载预设、读回参数、截帧比像素**。两份都要，缺一格就是瞎的。

【判据（每条附证伪句；读不到一律 FAIL，不许写成 PASS）】
 1. 场景能起、端口对
    /api/ping 200 且 ok=true；/env 200 且字节数 ≥ ENV_MIN 且正文含 `window.__sceneEnv`；
    本闸自起的服务进程到收尾仍活着。
    证伪句：端口不通、ping 非 200、页面小于下限、钩子不在正文、子进程中途退出 → 任一即 FAIL。
 2. 三预设齐且可服务
    /api/presets 列表含 A-静坐／A-观想／A-空境；逐个 /api/preset?name= 200 且 JSON 可解析，
    关键字段 scene／dist／breath／groundMode／fog／bloom／cGrid 齐且类型对。
    证伪句：列表缺名、单件 404、JSON 抛错、任一关键字段缺失或类型不符 → FAIL。
    （文件层"齐不齐"归静态闸判据 1，本条验的是**能不能经服务取到**——两格分开，不互替。）
 3. 三态关键交互各有外部可观测信号
    真浏览器里逐态 `await __loadPreset(name)`，每态验三件事：
      (a) `__snapshot().params` 的七个关键字段与该预设逐键相等 ⇒ 交互真落到状态；
      (b) 两次采样 `__sceneEnv.frames` 差 > 0 ⇒ 场景在出帧，不是死页；
      (c) 三态的参数字典两两不全等 ⇒ "三态"确实是三态，不是一个态换三个名字。
    证伪句：参数不落地（预设改了 R 没改）、帧数不动（渲染循环断）、三态参数全同 → FAIL。
    ⚠ 口径：(b) 的帧数差是**两次采样的差值**，不是"看到有帧"——单拍不算证据。
 4. 三态观感互异（光度统计，不用裸像素差）
    每态连采三张（隔约 1.2s），逐张算 lum_mean／亮部占比／暖冷偏置(R−B) 取中位；
    同态三张的极差＝该态本底抖动（场景在呼吸：实测同态两张隔 2s 变化像素达 54–58%，
    与三态之间的 74–78% 同一量级 ⇒ 裸像素差分不出"像不像"，只测得出"动没动"）。
    断言 (a) 每态 lum_mean > DARK_MIN（不全黑）；(b) 任两态三项统计的距离 >
    3 ×（两态本底抖动之和）；(c) 三态的 (lum_mean, 暖冷偏置) 不存在两态全同。
    证伪句：三态归一成同一预设 → (b)(c) 同红；任一态全黑 → (a) 红。
    裸像素差照旧写进读数表，但**只作观察项，不作 PASS 依据**。
 5. 资产可达且不是占位
    三态所用 scene 的候选路径逐条 HEAD：须至少一条 200、Content-Length ≥ ASSET_MIN，
    再 GET 取回验前 4 字节 == b"glTF"。
    证伪句：候选全 404、体积低于占位线、魔数不是 glTF → FAIL。
    ⚠ 本窗不替法师判"多大的模型才够看"——占位线是**可配置的工程下限**（`--asset-min`），
      判红时读数表里给出实测字节数与原路径，够不够由人定。

【用法】
    python vr_gates/verify_8779_scene.py            # 正跑（五判据）
    python vr_gates/verify_8779_scene.py --both     # 正跑＋四路反证（须反证报红才算有牙）
    python vr_gates/verify_8779_scene.py --no-start # 复用别处已在跑的 8779，不自起服务
    退出码：0 全过 ／ 1 任一 FAIL

【边界（照派工与红线）】
    不起头显、不连真机、不出网（只 127.0.0.1）；不改共用程序件；不动 `vr_闸总跑.py`；
    反证一律在 `output/` 下做**副本**，真预设目录一个字节不写不删。
"""
import argparse
import asyncio
import base64
import json
import os
import random
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request

import numpy as np
from PIL import Image
import io

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
SCENE_SERVER = os.path.join(ROOT, "01_项目管理", "测试台验收工具",
                            "20261022_W1VR_场景服务_8779_v1.py")
PAGE = os.path.join(ROOT, "output", "_scene_env.html")
OUT = os.path.join(ROOT, "output", "20261111_8779闸")
CNT = os.path.join(ROOT, "output", "20261111_8779闸_反证")
SERVICE_PORT = 8779
PRESETS = ["A-静坐", "A-观想", "A-空境"]
KEY_FIELDS = ["scene", "dist", "breath", "groundMode", "fog", "bloom", "cGrid"]
TYPE_OF = {"scene": str, "dist": (int, float), "breath": (int, float),
           "groundMode": str, "fog": (int, float), "bloom": (int, float), "cGrid": str}
SCENE_GLB = {  # 页面 :366-369 的候选路径表（现读，非记忆）
    "yujia": ["/models/yujia.glb", "/vr_assets/models/yujia.glb",
              "/vr_assets/yujia.glb", "/models/4.glb"],
    "lianchi": ["/vr_assets/models/lianchi/lianchi.glb", "/models/lianchi.glb"],
    "yunhai": ["/vr_assets/models/yunhai/yunhai.glb", "/models/yunhai.glb"],
    "jingshi": ["/vr_assets/models/jingshi/jingshi.glb", "/models/jingshi.glb"],
}
ENV_MIN = 20000
PIXEL_MIN_DIFF = 0.02
DARK_MIN = 3.0
FAILS, SKIPS, READINGS = [], [], []


def close_browser(proc, ws=None):
    """杀掉这一路起的 Edge，并回收**它自己**留的 user-data-dir（一份 25–65 MB，不收尾一次闸跑就堆 340 MB）。
       只删本次进程带来的那个目录——并发时有别的浏览器还开着，不能一把清。"""
    try:
        if ws:
            ws.close()
    except Exception:
        pass
    prof = getattr(proc, "_prof", None)
    if proc:
        # 只 kill 父进程会留下一串孤儿渲染进程（实测 12 个）占着 profile，rmtree 只能删一半。
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        proc.kill()
    if prof:
        import shutil
        time.sleep(0.6)
        shutil.rmtree(prof, ignore_errors=True)

EDGE = next((p for p in [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]
    if os.path.exists(p)), None)


def note(tag="read", **kw):
    READINGS.append(dict(tag=tag, **kw))


def check(ok, good, bad):
    print(("  [PASS] " if ok else "  [FAIL] ") + (good if ok else bad))
    if not ok:
        FAILS.append(good if ok else bad)
    return ok


def free_port():
    # 端口一律现取，不写死——写死过 9355／8806，残留进程占着时下一轮会连到陈旧 target。
    for _ in range(40):
        p = random.randint(20000, 29999)
        s = socket.socket()
        try:
            s.bind(("127.0.0.1", p))
            return p
        except OSError:
            pass
        finally:
            s.close()
    raise RuntimeError("取不到空闲端口")


def port_open(port, timeout=0.4):
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def get(url, timeout=6):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.getcode(), r.read(), dict(r.headers)
    except Exception as e:
        body = getattr(getattr(e, "fp", None), "read", lambda: b"")()
        return getattr(e, "code", 0), body, {}


def head_len(url, timeout=6):
    req = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            cl = r.headers.get("Content-Length")
            return r.getcode(), int(cl) if cl else -1
    except Exception as e:
        return getattr(e, "code", 0), -1


class Scene:
    """8779 场景服务：优先复用已在听的；否则自起、收尾自杀。"""

    def __init__(self, port, autostart=True, env_page=None, presets_dir=None):
        self.port = port
        self.autostart = autostart
        self.proc = None
        self.reused = False
        self.env_page = env_page
        self.presets_dir = presets_dir

    def __enter__(self):
        if port_open(self.port):
            if self.env_page or self.presets_dir:
                raise RuntimeError(f"端口 {self.port} 已被占用，反证跑不起来（须独占才敢改路由）")
            self.reused = True
            return self
        if not self.autostart:
            raise RuntimeError(f"端口 {self.port} 未在听，且本闸按 --no-start 不许自起")
        os.makedirs(CNT, exist_ok=True)
        self.proc = subprocess.Popen([PY, self._runner()], stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
        for _ in range(50):
            if port_open(self.port):
                return self
            time.sleep(0.15)
        self.proc.kill()
        raise RuntimeError(f"场景服务 {self.port} 未起")

    def _runner(self):
        fn = os.path.join(CNT, "_serve_%d.py" % self.port)
        with open(fn, "w", encoding="utf-8", newline="") as f:
            f.write(
                "import importlib.util, sys\n"
                "from http.server import ThreadingHTTPServer\n"
                "spec = importlib.util.spec_from_file_location('svc8779', %r)\n"
                "m = importlib.util.module_from_spec(spec)\n"
                "spec.loader.exec_module(m)\n"      # 只 exec 模块，__main__ 守卫不触发
                % SCENE_SERVER +
                ("m.ROUTES['/env'] = %r\n" % self.env_page if self.env_page else "") +
                ("m.PRESET_DIR = %r\n" % self.presets_dir if self.presets_dir else "") +
                "ThreadingHTTPServer(('127.0.0.1', %d), m.Handler).serve_forever()\n" % self.port)
        return fn

    def __exit__(self, *exc):
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
        return False

    @property
    def base(self):
        return "http://127.0.0.1:%d" % self.port

    def alive(self):
        return self.proc is None or self.proc.poll() is None


def browser(port):
    prof = os.path.join(OUT, "_p%d" % port)
    proc = subprocess.Popen(
        [EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars",
         "--window-size=1280,720", "--user-data-dir=" + prof,
         "--no-first-run", "--remote-debugging-port=%d" % port, "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    proc._prof = prof
    targets = None
    for _ in range(60):
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d/json" % port, timeout=2) as r:
                targets = json.load(r)
            break
        except Exception:
            time.sleep(0.4)
    if not targets:
        proc.kill()
        raise RuntimeError("Edge 调试端口未就绪")
    page = next(t for t in targets if t["type"] == "page")
    import websockets.sync.client as wsc
    ws = wsc.connect(page["webSocketDebuggerUrl"], max_size=64 * 1024 * 1024, legacy=True)
    return proc, ws


def send(ws, method, params=None):
    ws.send(json.dumps({"id": 1, "method": method, "params": params or {}}))
    while True:
        msg = json.loads(ws.recv(timeout=90))
        if msg.get("id") == 1:
            if "error" in msg:
                raise RuntimeError("%s → %s" % (method, msg["error"]))
            return msg.get("result") or {}


def ev(ws, expr, awaitp=True):
    r = send(ws, "Runtime.evaluate", {"expression": expr, "returnByValue": True,
                                      "awaitPromise": awaitp})
    if r.get("exceptionDetails"):
        return "EXC:" + str(r["exceptionDetails"].get("text"))[:160]
    return r.get("result", {}).get("value")


def grab(ws):
    """截一帧：返回 (RGB 数组, PNG 字节)。"""
    d = send(ws, "Page.captureScreenshot", {"format": "png"})
    b = base64.b64decode(d["data"])
    return np.asarray(Image.open(io.BytesIO(b)).convert("RGB")), b


def photometry(a):
    """光度三统计：亮度中位、亮部占比、暖冷偏置（R−B）。场景在呼吸，故取多帧中位。"""
    lum = a.mean(axis=2)
    return dict(lum_mean=round(float(lum.mean()), 2),
                bright_pct=round(float((lum > 60).mean()) * 100, 2),
                warm_bias=round(float(a[:, :, 0].mean() - a[:, :, 2].mean()), 2))


# ── 判据 1 ────────────────────────────────────────────────────────
def judge_service(scene):
    print("\n── 判据 1：场景能起、端口对 ──────────────────────────────")
    code, body, _ = get(scene.base + "/api/ping")
    ok = check(code == 200 and json.loads(body or b"{}").get("ok") is True,
               "端口 %d 在听且 /api/ping ok" % scene.port,
               "/api/ping 非 200 或 ok≠true（实得 code=%s body=%r）" % (code, body[:60]))
    code2, html, _ = get(scene.base + "/env")
    size = len(html or b"")
    note(env_code=code2, env_bytes=size)
    check(code2 == 200 and size >= ENV_MIN and b"window.__sceneEnv" in (html or b""),
          "/env 200／%d B／含 window.__sceneEnv 钩子" % size,
          "/env 不可用：code=%s 字节=%d（下限 %d）钩子%s" % (
              code2, size, ENV_MIN, "在" if b"window.__sceneEnv" in (html or b"") else "缺"))
    check(scene.alive(), "服务进程到收尾仍活着" if scene.reused else
          "自起的服务进程活着（非起来了就崩）",
          "服务进程中途退出（退码 %s）⇒ 场景其实起不来" % (scene.proc.poll() if scene.proc else None))


# ── 判据 2 ────────────────────────────────────────────────────────
def judge_presets(scene):
    print("\n── 判据 2：三预设齐且可经服务取到 ────────────────────────")
    code, body, _ = get(scene.base + "/api/presets")
    lst = (json.loads(body or b"{}").get("presets") or []) if code == 200 else []
    miss = [p for p in PRESETS if p not in lst]
    check(not miss, "列表含三预设（现读 %d 件）" % len(lst),
          "服务侧预设列表缺 %s（实得 %s）" % (miss, lst))
    for name in PRESETS:
        c, b, _ = get(scene.base + "/api/preset?name=" + urllib.parse.quote(name))
        if c != 200:
            check(False, "", "%s HTTP 非 200（实得 %s）" % (name, c))
            continue
        try:
            j = json.loads(b.decode("utf-8"))
        except Exception as e:
            check(False, "", "%s JSON 解析失败：%s" % (name, e))
            continue
        par = j.get("params", j)
        bad = [k for k in KEY_FIELDS if k not in par or not isinstance(par[k], TYPE_OF[k])]
        note(preset=name, **{k: par.get(k) for k in KEY_FIELDS})
        check(not bad, "%s 七关键字段齐且类型对" % name,
              "%s 字段缺失或类型不符：%s（实得 %s）" % (name, bad, {k: par.get(k) for k in KEY_FIELDS}))


# ── 判据 3 ────────────────────────────────────────────────────────
def judge_states(scene, ws):
    print("\n── 判据 3：三态关键交互各有外部可观测信号 ────────────────")
    send(ws, "Page.enable")
    send(ws, "Runtime.enable")
    send(ws, "Page.navigate", {"url": scene.base + "/env"})
    ready = ""
    for _ in range(60):
        ready = ev(ws, "typeof window.__loadPreset + '/' + typeof window.__snapshot")
        if ready.startswith("function"):
            break
        time.sleep(0.4)
    if not ready.startswith("function"):
        check(False, "", "页面钩子未就绪（实得 %r）⇒ 判据 3、4 都没跑成，不是通过" % ready)
        return None
    shots = {}
    per = {}
    for name in PRESETS:
        ret = ev(ws, "window.__loadPreset(%r).then(j=>JSON.stringify(j&&j.name||j&&'ok'||'null'))" % name)
        got = json.loads(ev(ws, "JSON.stringify((()=>{const s=__snapshot();"
                               "return {params:s.params, frames:__sceneEnv.frames};})())"))
        f2 = ev(ws, "__sceneEnv.frames")
        time.sleep(1.2)
        f1 = ev(ws, "__sceneEnv.frames")
        want = {r["preset"]: r for r in READINGS if "preset" in r}.get(name, {})
        diffkeys = [k for k in KEY_FIELDS if got["params"].get(k) != want.get(k)]
        arrs, first = [], None
        for i in range(3):                       # 同态连采三张：极差＝本底抖动
            if i:
                time.sleep(1.2)
            a, b = grab(ws)
            arrs.append(a)
            first = first or b
        shots[name] = arrs
        with open(os.path.join(OUT, "态_%s.png" % name), "wb") as f:
            f.write(first)
        per[name] = dict(params={k: got["params"].get(k) for k in KEY_FIELDS},
                         frame_delta=(f1 or 0) - (f2 or 0), load_ret=ret)
        note(state=name, **per[name])
        ok_a = check(not diffkeys, "%s 参数落地（七键回读与预设逐键相同）" % name,
                     "%s 交互没落到状态：不一致键 %s｜页面回读 %s｜预设 %s" % (
                         name, diffkeys, {k: got["params"].get(k) for k in KEY_FIELDS},
                         {k: want.get(k) for k in KEY_FIELDS}))
        check(per[name]["frame_delta"] > 0,
              "%s 两拍帧差 %d > 0（场景在出帧）" % (name, per[name]["frame_delta"]),
              "%s 两拍帧差 %s ⇒ 渲染循环没跑，屏上是死页" % (name, per[name]["frame_delta"]))
        if not ok_a:
            continue
    if len(per) == len(PRESETS):
        same = [(a, b) for i, a in enumerate(PRESETS) for b in PRESETS[i + 1:]
                if per[a]["params"] == per[b]["params"]]
        check(not same, "三态参数字典两两不全等（确是三态）",
              "有两态参数完全相同：%s ⇒「三态」是假的" % same)
    return shots


# ── 判据 4 ────────────────────────────────────────────────────────
STATS = ["lum_mean", "bright_pct", "warm_bias"]


def _drift(a0, a1):
    return round(float((np.abs(a0.astype(np.int16) - a1.astype(np.int16)).max(axis=2) > 6).mean()) * 100, 2)


def judge_look(shots):
    print("\n── 判据 4：三态观感互异（光度统计，不用裸像素差）────────")
    if not shots or len(shots) < len(PRESETS):
        check(False, "", "截帧不足 %d 态（实得 %s）⇒ 本判据没跑成，不是通过" % (
            len(PRESETS), list(shots or {})))
        return
    med, jit = {}, {}
    for name in PRESETS:
        arrs = shots[name]
        ph = [photometry(a) for a in arrs]
        med[name] = {k: float(np.median([p[k] for p in ph])) for k in STATS}
        jit[name] = {k: float(max(p[k] for p in ph) - min(p[k] for p in ph)) for k in STATS}
        drift = [_drift(arrs[0], arrs[i]) for i in range(1, len(arrs))]
        note(look_state=name, **{k: round(med[name][k], 2) for k in STATS},
             jitter={k: round(jit[name][k], 2) for k in STATS},
             同态裸像素漂移=drift)
        print("  [读数] %s 中位 lum %.2f／亮部 %.2f%%／暖冷 %+0.2f｜同态抖动 %s｜同态裸像素漂移 %s%%" % (
            name, med[name]["lum_mean"], med[name]["bright_pct"], med[name]["warm_bias"],
            {k: round(jit[name][k], 2) for k in STATS}, drift))
        check(med[name]["lum_mean"] > DARK_MIN,
              "%s 中位亮度 %.2f > %.1f（不是全黑）" % (name, med[name]["lum_mean"], DARK_MIN),
              "%s 中位亮度 %.2f ⇒ 场景没画出来，观感比对无意义" % (name, med[name]["lum_mean"]))
    weak = []
    for i, a in enumerate(PRESETS):
        for b in PRESETS[i + 1:]:
            sep = [k for k in STATS
                   if abs(med[a][k] - med[b][k]) > 3.0 * (jit[a][k] + jit[b][k]) + 1e-9]
            note(pair="%s↔%s" % (a, b), 分开项=sep,
                 距离={k: round(med[a][k] - med[b][k], 2) for k in STATS})
            print("  [读数] %s ↔ %s 三项距离 %s／超抖动项 %s（须 ≥2 项）" % (
                a, b, {k: round(med[a][k] - med[b][k], 2) for k in STATS}, sep))
            if len(sep) < 2:
                weak.append((a, b, sep))
    check(not weak,
          "三对态在至少两项光度统计上分开得比本底抖动远（≥3×）",
          "有两对在抖动之内的差距都撑不开（观感分不开）：%s——须 ≥2 项统计超 3× 抖动" % weak)


# ── 判据 5 ────────────────────────────────────────────────────────
def judge_assets(scene):
    print("\n── 判据 5：资产可达且不是占位 ────────────────────────────")
    scenes_used = sorted({r.get("scene") for r in READINGS if r.get("preset")} - {None})
    if not scenes_used:
        check(False, "", "判据 2 没取到任何 scene 值 ⇒ 本判据没跑成")
        return
    for sc in scenes_used:
        cands = SCENE_GLB.get(sc)
        if not cands:
            check(False, "", "scene=%s 不在页面候选表（现读 :366-369）⇒ 页面改了本闸要跟" % sc)
            continue
        hit = None
        for p in cands:
            code, ln = head_len(scene.base + p)
            note(asset="%s|%s" % (sc, p), code=code, length=ln)
            if code == 200 and ln > 0:
                hit = (p, ln)
                break
        if not check(hit is not None,
                     "scene=%s 资产可取（%s，%s B）" % (sc, hit[0], hit[1]) if hit else "",
                     "scene=%s 四条候选路径全 404：%s" % (sc, cands)):
            continue
        code, body, _ = get(scene.base + hit[0])
        magic = (body or b"")[:4]
        ok_magic = check(magic == b"glTF", "魔数 glTF 对",
                         "前 4 字节不是 glTF（实得 %r）⇒ 取到的不是 GLB" % magic)
        small = hit[1] < scene.asset_min
        check(not small,
              "体积 %s B ≥ 占位线 %d B" % (hit[1], scene.asset_min),
              "体积 %s B 低于占位线 %d B（scene=%s，路径 %s）⇒ 按「资产无缺失」判红。"
              "本窗不替法师判多大的模型才够看：线是可调工程下限，够不够由人定；"
              "若判定 2KB 级占位可用，调 --asset-min 即绿。" % (
                  hit[1], scene.asset_min, sc, hit[0]) if ok_magic else "魔数已错，体积不再判")


# ── 反证：故意弄坏，要求对应判据报红 ──────────────────────────────
def judge_pair(scene, ws):
    """反证专用：判据 3＋4 连着跑（"三态归一"要两格同时红）。"""
    return judge_look(judge_states(scene, ws)) or {}


def build_mutants():
    os.makedirs(CNT, exist_ok=True)
    src = open(PAGE, encoding="utf-8").read()
    made = []
    # c2：加载预设但不落地
    a2 = "    const j = await r.json(); applyPreset(j); return j;"
    if a2 in src:
        fn = os.path.join(CNT, "env_noapply.html")
        open(fn, "w", encoding="utf-8", newline="").write(src.replace(a2, "    const j = await r.json(); return j;", 1))
        made.append(("预设加载不落地", judge_states, dict(env_page=fn)))
    else:
        SKIPS.append("预设加载不落地")
    # c3：渲染循环不推帧
    a3 = "  const t=(performance.now()-t0)/1000; R.frames++; window.__fc=R.frames;"
    if a3 in src:
        fn = os.path.join(CNT, "env_noframes.html")
        open(fn, "w", encoding="utf-8", newline="").write(
            src.replace(a3, "  const t=(performance.now()-t0)/1000; window.__fc=R.frames;", 1))
        made.append(("场景不出帧", judge_states, dict(env_page=fn)))
    else:
        SKIPS.append("场景不出帧")
    # c4：三态归一（加载谁都取 A-静坐）——要求判据 3 的"三态不全等"与判据 4 的光度分开同时红
    a4 = "    const j = await r.json(); applyPreset(j); return j;"
    if a4 in src:
        fn = os.path.join(CNT, "env_all_same.html")
        open(fn, "w", encoding="utf-8", newline="").write(src.replace(
            a4,
            "    const j = await (await fetch('/api/preset?name=' + encodeURIComponent('A-静坐'))).json();"
            " applyPreset(j); return j;", 1))
        made.append(("三态归一成同一预设", judge_pair, dict(env_page=fn)))
    else:
        SKIPS.append("三态归一成同一预设")
    # c1：预设目录缺 A-空境（**副本**，真目录一字不动）
    d = os.path.join(CNT, "presets_missing")
    os.makedirs(d, exist_ok=True)
    have = [x for x in os.listdir(os.path.join(ROOT, "vr_assets", "models", "presets"))
            if x.endswith(".json")]
    for x in have:
        if x != "A-空境.json":
            open(os.path.join(d, x), "wb").write(
                open(os.path.join(ROOT, "vr_assets", "models", "presets", x), "rb").read())
    made.append(("预设缺 A-空境", judge_presets, dict(presets_dir=d)))
    return made


def run_counter(asset_min):
    print("\n" + "=" * 68)
    print("反证：故意弄坏，要求对应判据报红")
    print("=" * 68)
    for name, judge, kw in build_mutants():
        print("\n反证「%s」（端口另取，改路由须独占）" % name)
        global FAILS
        before = len(FAILS)
        port = free_port()
        scene = Scene(port, **kw)
        scene.asset_min = asset_min
        wproc = None
        ws = None
        try:
            with scene:
                if judge in (judge_states, judge_pair):
                    wproc, ws = browser(free_port())
                    judge(scene, ws)
                else:
                    judge(scene)
        except Exception as e:
            print("  [err] 反证跑挂：%s" % e)
        finally:
            close_browser(wproc, ws)
        caught = len(FAILS) > before
        if caught:
            FAILS = FAILS[:before]      # 反证的 FAIL 是预期的，不并进正跑账面
        print("  [%s] %s → %s" % ("反证成立" if caught else "反证失灵",
                                  name, "判据确实 FAIL" if caught else
                                  "该判据没抓到这次破坏——形同虚设"))
        if not caught:
            FAILS.append("反证「%s」未报红 ⇒ 这道闸没有牙" % name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--both", action="store_true", help="正跑＋四路反证")
    ap.add_argument("--no-start", action="store_true", help="不自起服务，只连已在听的 8779")
    ap.add_argument("--asset-min", type=int, default=1048576, help="GLB 占位线（字节，默认 1 MiB；协调位 11-11 准提，堵 6.8KB 级假绿）")
    a = ap.parse_args()
    if EDGE is None:
        print("[FAIL] 找不到 Edge，本闸的判据 3／4 全靠真浏览器")
        return 1
    os.makedirs(OUT, exist_ok=True)
    print("=" * 68)
    print("8779 莲池夜观（方案A）运行时闸　正跑　端口 %d" % SERVICE_PORT)
    print("=" * 68)
    ws = wproc = None
    code_ret = 1
    try:
        scene = Scene(SERVICE_PORT, autostart=not a.no_start)
        scene.asset_min = a.asset_min
        with scene:
            print("（服务：%s）" % ("复用别处已在跑的 8779，本闸没起它" if scene.reused
                                    else "本闸自起，收尾即杀"))
            judge_service(scene)
            judge_presets(scene)
            wproc, ws = browser(free_port())
            shots = judge_states(scene, ws)
            judge_look(shots)
            judge_assets(scene)
    except Exception as e:
        FAILS.append("闸自身异常：%s" % e)
    finally:
        close_browser(wproc, ws)
    print("\n" + "=" * 68)
    if SKIPS:
        print("跳过的反证（锚文本不在页面）：%s——须同步本脚本" % SKIPS)
    if a.both:
        run_counter(a.asset_min)
    print("\n" + "=" * 68)
    with open(os.path.join(OUT, "读数表.json"), "w", encoding="utf-8") as f:
        json.dump(READINGS, f, ensure_ascii=False, indent=1)
    print("读数表 %d 条 → %s" % (len(READINGS), os.path.join(OUT, "读数表.json")))
    if FAILS:
        print("[FAIL] 未过 %d 项：" % len(FAILS))
        for x in FAILS:
            print("   - " + x)
        return 1
    print("[PASS] 五判据全过（反证另有 --both 验牙）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
