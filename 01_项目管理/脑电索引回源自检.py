"""脑电主线 · 知识索引回源自检 v1（协调位自建，只读、零外联）

目的：索引 v1 只声明「有一条回源法」，但**没有一道自动检查**——10-23 立的 K-02／K-03
      到 11-02 已因 `.gitignore:77`（`*.json`）把被引文件挡在库外而**静默失效**，
      两个月没人发现（本窗 2026-11-02 抽检时才发现）。

做法：把每条可机核事实的「源路径 + 正则 + 期望值」写死在本脚本里，一条命令出退码。
      ⚠ 写死路径不是「第二真值」——它只是「这条引用还在不在」的**探针**；
      真值仍在源文件里，探针只回答「按这条回源法，现在还核不核得到」。

跑法：python 01_项目管理/脑电索引回源自检.py
退码：0＝全部可机核条目命中；1＝至少一条失效（须改索引或改真源）
      2＝索引文件本身读不到
纪律：取不到值一律记 FAIL（不是 WARN）——回源失效就是失效，不能写「未验」蒙过去。
"""
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "01_项目管理" / "交接试跑_20261019" / "DSH-24e5b510" / "20261023_DSH-24e5b510_脑电主线知识索引_v1.md"

# (条号, 说明, 源文件, 正则, 期望值或 None=只要命中)
CHECKS = [
    ("K-01", "通道表 7 路",
     "muse2-repo/muse2-master/neuradock_receiver.py",
     r'ND_CHANNELS\s*=\s*\[(.*?)\]', "CP5"),
    ("K-01", "采样率 250",
     "muse2-repo/muse2-master/neuradock_receiver.py",
     r'ND_SFREQ\s*=\s*([\d.]+)', "250"),
    ("K-02", "默认端口 9600（我方接收器）",
     "muse2-repo/muse2-master/neuradock_receiver.py",
     r'port\s*=\s*(\d+)', "9600"),
    # ⚠ 这一条就是 10-23 版失效的地方：原索引指向 01_项目管理/configs/neuradock-v1.json，
    #   而该路径被 .gitignore:77 挡住、从未入库。改用参考仓库那份（9-08 入库）。
    ("K-02", "对方 profile 端口（参考仓库真源）",
     "05_产品与开发/NeuraDock/参考仓库/eeg-workstation-agent/configs/neuradock-v1.json",
     r'"default_port"\s*:\s*(\d+)', "9600"),
    ("K-03", "总包 8 通道",
     "05_产品与开发/NeuraDock/参考仓库/eeg-workstation-agent/configs/neuradock-v1.json",
     r'"total_packet_channels"\s*:\s*(\d+)', "8"),
    ("K-03", "实用 7 通道",
     "05_产品与开发/NeuraDock/参考仓库/eeg-workstation-agent/configs/neuradock-v1.json",
     r'"used_channels"\s*:\s*(\d+)', "7"),
    ("K-03", "每包 5 样本",
     "05_产品与开发/NeuraDock/参考仓库/eeg-workstation-agent/configs/neuradock-v1.json",
     r'"samples_per_bluetooth_packet"\s*:\s*(\d+)', "5"),
    ("K-05", "判据 13 执行式 0.96–1.02",
     "vr_gates/verify_mandala_stage.py",
     r'check\(0\.96 <= r <= 1\.02', None),
    ("K-06", "QC 阈值版本 20261013",
     "qc_pipeline.py",
     r'THRESHOLD_VERSION\s*=\s*"(\d+)"', "20261013"),
]

fails, oks = [], []


def main():
    if not INDEX.exists():
        print(f"[FAIL] 索引文件不存在：{INDEX}")
        return 2

    idx_text = INDEX.read_text(encoding="utf-8", errors="replace")

    for kid, desc, rel, pat, want in CHECKS:
        p = ROOT / rel
        if not p.exists():
            fails.append(f"{kid} {desc}｜源不存在：{rel}")
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        m = re.search(pat, text)
        if not m:
            fails.append(f"{kid} {desc}｜正则未命中：{rel} /{pat}/")
            continue
        got = m.group(1) if m.groups() else (m.group(0))
        if want is not None and want not in (got or ""):
            fails.append(f"{kid} {desc}｜值变了：期望含 {want!r}，实取 {got!r}")
            continue
        line = text[: m.start()].count("\n") + 1
        oks.append(f"{kid} {desc}｜{rel}:{line} → {got if m.groups() else '命中'}")

    # 反向：索引里若仍写着已失效的旧路径，必须报出来
    stale = "01_项目管理\\configs\\neuradock-v1.json" in idx_text or \
            "01_项目管理/configs/neuradock-v1.json" in idx_text
    if stale:
        fails.append("索引正文仍含已失效旧路径 `01_项目管理\\configs\\neuradock-v1.json`"
                     "（该件从未入库，`.gitignore:77` 挡 `*.json`）")

    for x in oks:
        print("[OK] " + x)
    for x in fails:
        print("[FAIL] " + x)
    print(f"[END] ok={len(oks)} fail={len(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
