# -*- coding: utf-8 -*-
"""口径一致校验 v1（脑电主线 · 机械验收件）

用途：把《口径唯一表》里能机械核的两条（CuD-01 通道/采样率、CuD-02 入口）＋判据 13 执行式，
      对着**三个真实源**交叉校验，一次跑出 PASS/WARN/FAIL 与退码。
      设计纪律：取不到值一律 WARN「未验」，不写通过；不一致即 FAIL（退码 1）。

跑法：python 01_项目管理\验证_口径一致_v1.py
退出码：0＝无 FAIL；1＝至少一条 FAIL。
"""
import json
import re
import sys
from pathlib import Path

try:  # 本机控制台默认 GBK，统一改 UTF-8 免中文崩
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

ROOT = Path(__file__).resolve().parents[1]
RECV = ROOT / "muse2-repo" / "muse2-master" / "neuradock_receiver.py"
PROF = ROOT / "05_产品与开发" / "NeuraDock" / "参考仓库" / "eeg-workstation-agent" / "configs" / "neuradock-v1.json"
GATE = ROOT / "vr_gates" / "verify_mandala_stage.py"

ok, warn, fail = [], [], []


def o(m):
    ok.append(m); print("[OK] " + m)


def w(m):
    warn.append(m); print("[WARN] " + m)


def f(m):
    fail.append(m); print("[FAIL] " + m)


def read(p):
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001
        w(f"{p.name} 读不到 ⇒ 未验：{type(e).__name__}")
        return None


print("[GATE] 口径一致校验 v1（CuD-01／CuD-02／判据 13）")

# ── 源 1：我方接收器常量 ───────────────────────────────────────────────
t = read(RECV)
ch, sf, port = [], None, None
if t:
    m = re.search(r"ND_CHANNELS\s*=\s*\[(.*?)\]", t)
    if m:
        ch = [c.strip().strip("\"'") for c in m.group(1).split(",") if c.strip()]
    m = re.search(r"ND_SFREQ\s*=\s*([\d.]+)", t)
    if m:
        sf = float(m.group(1))
    m = re.search(r"port\s*=\s*(\d+)", t)
    if m:
        port = int(m.group(1))
    if ch and sf and port:
        o(f"我方接收器：{len(ch)} 通道／{sf:g} Hz／端口 {port}")
    else:
        w("我方接收器三常量未全取到 ⇒ 未验")

# ── 源 2：对方公开 profile ────────────────────────────────────────────
p = read(PROF)
pj = None
if p:
    try:
        pj = json.loads(p)
        o(f"对方 profile：v{pj.get('profile_version','?')}／{pj.get('channel_count','?')} 通道／"
          f"{pj.get('sampling_rate_hz','?')} Hz／端口 {pj.get('tcp',{}).get('default_port','?')}／单位 {pj.get('amplitude_unit','?')}")
    except Exception as e:  # noqa: BLE001
        w(f"对方 profile 解析失败 ⇒ 未验：{type(e).__name__}")

# ── 交叉 1：通道与采样率（CuD-01）─────────────────────────────────────
if pj and ch and sf:
    if list(pj.get("channels", [])) == ch:
        o("CuD-01 通道一致：双方同为 " + " ".join(ch))
    else:
        f(f"CuD-01 通道不一：我方 {ch} vs 对方 {pj.get('channels')}")
    if float(pj.get("sampling_rate_hz", -1)) == sf:
        o(f"CuD-01 采样率一致：{sf:g} Hz")
    else:
        f(f"CuD-01 采样率不一：我方 {sf} vs 对方 {pj.get('sampling_rate_hz')}")
    if str(pj.get("amplitude_unit", "")).lower() in ("uv", "µv", "μv"):
        o("CuD-01 幅值单位一致：µV")
    else:
        w(f"CuD-01 单位未对齐（对方写 {pj.get('amplitude_unit')!r}）⇒ 未验")

# ── 交叉 2：入口端口（CuD-02）──────────────────────────────────────────
if pj and port:
    dport = pj.get("tcp", {}).get("default_port")
    if dport == port:
        o(f"CuD-02 端口一致：{port}")
    else:
        f(f"CuD-02 端口不一：我方 {port} vs 对方 {dport}")
    tp, uc = pj.get("tcp", {}).get("total_packet_channels"), pj.get("tcp", {}).get("used_channels")
    if tp and uc:
        note = f"（总包 {tp} 通道只用 {uc}）"
        if uc == len(ch):
            o("CuD-02 包结构自洽" + note)
        else:
            f(f"CuD-02 包结构矛盾：用 {uc} 而通道 {len(ch)}" + note)

# ── 源 3：判据 13 执行式（CuD-03）─────────────────────────────────────
g = read(GATE)
if g:
    if "check(0.96 <= r <= 1.02" in g:
        ln = g[: g.find("check(0.96 <= r <= 1.02")].count("\n") + 1
        o(f"CuD-03 判据 13 执行式在：0.96 ≤ r ≤ 1.02（第 {ln} 行）")
    else:
        f("CuD-03 判据 13 执行式未按 0.96–1.02 出现 ⇒ 口径变了，须重取")
    if "±4%" in g:
        w("CuD-03 文件内仍存「±4%」字样（头注留痕，已裁“以执行式为准”）——引用时不得写成对称 ±4%")

print("[END] fail=%d warn=%d ok=%d" % (len(fail), len(warn), len(ok)))
sys.exit(1 if fail else 0)
