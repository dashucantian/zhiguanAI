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

# ── 交叉 4：共享 .ps1 的 BOM（K-11；10-24 补，机核条数 4→5）──────────────
KH = ROOT / "01_项目管理" / "交接面检查.ps1"
try:
    head3 = KH.read_bytes()[:3]
    if head3 == b"\xef\xbb\xbf":
        o("K-11 共享脚本 BOM 在：交接面检查.ps1 前三字节 EF BB BF")
    else:
        f(f"K-11 共享脚本 BOM 丢失（前三字节 {head3.hex()}）⇒ PS 5.1 会按 GBK 解析崩")
except Exception as e:  # noqa: BLE001
    w(f"K-11 读不到共享脚本 ⇒ 未验：{type(e).__name__}")

# ── ML-3：我方设备剖面自检（结构完整／与 CuD-01 02 一致／差异显式）──────────
OURP = ROOT / "01_项目管理" / "configs" / "neuradock-v1.md"
op = read(OURP)
oj = None
if op:
    try:
        m = re.search(r"```json\s*(\{.*?\})\s*```", op, re.S)
        if not m:
            f("ML-3 剖面 md 里未找到 ```json 块")
        else:
            oj = json.loads(m.group(1))
    except Exception as e:  # noqa: BLE001
        f(f"ML-3 我方剖面解析失败：{type(e).__name__}")

if oj:
    sig = oj.get("signal", {})
    ok_ours = (
        sig.get("sampling_rate_hz") == 250
        and sig.get("channel_count") == 7
        and list(sig.get("channels", [])) == ["CP5", "CP6", "PO3", "PO4", "O1", "Oz", "O2"]
        and str(sig.get("amplitude_unit", "")).lower() == "uv"
    )
    if ok_ours:
        o("ML-3 我方剖面 signal 段与 CuD-01 一致（7 通道／250 Hz／µV）")
    else:
        f(f"ML-3 我方剖面 signal 段与 CuD-01 不一：{sig}")
    tcp = oj.get("tcp", {})
    if tcp.get("default_port") == 9600:
        o("ML-3 我方剖面入口与 CuD-02 一致（9600）")
    else:
        f(f"ML-3 我方剖面端口与 CuD-02 不一：{tcp.get('default_port')}")
    gates = oj.get("quality_gates_ours", {})
    if gates.get("thresholds_version") == "20261013":
        o("ML-3 我方剖面质量阈值版本与 CuD-04 一致（20261013）")
    else:
        f(f"ML-3 质量阈值版本与 CuD-04 不一：{gates.get('thresholds_version')}")
    diffs = oj.get("diff_vs_reference", [])
    bad = [d for d in diffs if not d.get("source")]
    if len(diffs) < 3:
        f(f"ML-3 差异节过少（{len(diffs)} 条，应 ≥3）⇒ 疑为『无差异』式偷懒")
    elif bad:
        f(f"ML-3 差异节有 {len(bad)} 条缺 source（无法回源）")
    else:
        o(f"ML-3 差异节 {len(diffs)} 条、条条带 source")
    alpha = gates.get("bands_hz", {}).get("alpha")
    if alpha == [8.0, 12.0]:
        w("ML-3 提示：我方 alpha 用 8–12 Hz，对方用 8–13 Hz（差异已列，引用须带带宽）")

print("[END] fail=%d warn=%d ok=%d" % (len(fail), len(warn), len(ok)))
sys.exit(1 if fail else 0)