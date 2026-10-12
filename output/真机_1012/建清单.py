"""生成 output/真机_1012/取证据清单.md——含入库件与留盘原片的 SHA-256。

用法：python output/真机_1012/建清单.py（在仓库根跑）
原片不入库（519MB 屏摄会让 16.4MB 的 pack 永久膨胀），但逐件哈希入册：
换机后若原片仍在，可 sha256sum -c 逐件复验；不在，则清单本身即"取过证"的凭据。
"""
import glob
import hashlib
import io
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(ROOT, "..", ".."))

TRACKED = (sorted(glob.glob(os.path.join(ROOT, "实录", "*.gz")))
           + sorted(glob.glob(os.path.join(ROOT, "退出报告", "*.json")))
           + sorted(glob.glob(os.path.join(ROOT, "屏摄", "*.png"))))
RAW = (sorted(glob.glob(os.path.join(ROOT, "frames", "*.png")))
       + sorted(glob.glob(os.path.join(ROOT, "pos", "*.png")))
       + sorted(glob.glob(os.path.join(ROOT, "neg", "*.png")))
       + sorted(f for f in glob.glob(os.path.join(ROOT, "*.png"))))


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def rel(p):
    return os.path.relpath(p, REPO).replace("\\", "/")


lines = [
    "# 真机取证据清单 · 段 3 张力层首跑（2026-10-12）",
    "",
    "> 窗＝W1｜VR场景设计｜73336324｜AI-022｜Session `W1-QODER-20261012-VR-A`",
    "> 设备＝PICO 4 Ultra `PA921FMGK6230020G`／A9210／OS 5.15.7／WebLayer Chrome/125",
    "> 通道＝`adb reverse tcp:8777` ⇒ `http://localhost:8777/mandala?stage=1[&tension=pos|neg]`",
    "> 取证＝CDP `adb forward tcp:9223 localabstract:weblayer_devtools_remote_6719`，0.5 秒一拍",
    "> 帧率＝全息态 72.1fps／窗口态 72.3fps（各实测一次，rAF 计数 3 秒）",
    "",
    "## 一、五段时线（真机，秒；自会话起点）",
    "",
    "| 跑次 | session_begin | dwell | change | 合成四步 | tension_begin | gather | tension_end | base_returned | exit |",
    "|---|---|---|---|---|---|---|---|---|---|",
    "| ③对照·首跑 | 0 | 2.989 | 23.000 | 23.014／43.002／63.002／83.002 | — | 103.002 | — | **无（D1 缺陷态）** | 报告丢失（页面被重载覆盖） |",
    "| ①正向 | 0 | 2.989 | 23.000 | 23.013／43.002／63.002／83.002 | 23.013 | 103.002 | 103.002 | 无（同上） | 系统键 → **FAIL 9.57%（D2）** |",
    "| ②负向 | 0 | 2.990 | 23.001 | 23.014／43.001／63.002／83.002 | 23.014 | 103.003 | 103.003 | 无（同上） | 按钮 → PASS（硬锁），退出瞬间真读数 **10.9%** |",
    "| ③对照·补跑（修后） | 0 | 2.992 | 23.000 | 23.015／43.001／63.002／83.002 | — | 103.003 | — | **106.058** | 系统键 → **PASS，cur 逐位＝base** |",
    "| ①正向（修后） | 0 | 2.990 | 23.001 | 23.015／43.001／63.002／83.002 | 23.014 | 103.003 | 103.003 | **105.906** | 系统键 → PASS，收束末 live＝{0.025, 1, [0.85,0.55,0.7]} |",
    "",
    "张力层动力学（真机）：段末 `t=0`；符号翻转 **4 次**（＝2N）；末速镜像 +0.0022／−0.0022；",
    "首摆 **0.7983**（旧 `v0=0.2078`）→ **0.8489**（补 `sin(ω_d·τp)` 后 `v0=0.2210`）。",
    "72fps 欧拉复算给 0.79830／0.84887 —— 与两次实测四位对上 ⇒ D4 归因坐实（**不是帧率**）。",
    "",
    "## 二、体感读数分解（法师亲答\"没看出变化\"之后，由真机实录算得，非纸面）",
    "",
    "| 通道 | 呼吸自身摆幅（安住段实测峰谷） | 张力叠加摆幅 | 张力／呼吸 |",
    "|---|---|---|---|",
    "| 雾（阴阳） | 0.00453 | 0.00279 | 0.62 |",
    "| 光晕（明暗） | 0.05517 | 0.04789 | 0.87 |",
    "| 内层显隐 | 0.04337 | 0.06784 | 1.56 |",
    "| 中层显隐 | 0.03024 | 0.04390 | 1.45 |",
    "| 外层显隐 | 0.03860 | 0.05587 | 1.45 |",
    "",
    "叠加周期 **40s** vs 三路呼吸 **13／26／34s** ⇒ 同一时间尺度、幅值仅 0.62～1.56 倍，肉眼不可辨是**结构性**结论。",
    "另：把三轴贡献剥掉后残差仍是纯呼吸的 1.24～2.25 倍 ⇒ **动静轴改的就是呼吸本身速率，与呼吸层不可分**。",
    "",
    "## 三、入库件（本目录内，随 `.gitignore` 显式例外放行）",
    "",
    "| 文件 | 字节 | SHA-256 |",
    "|---|---|---|",
]
for p in TRACKED:
    lines.append("| `{0}` | {1:,} | `{2}` |".format(rel(p), os.path.getsize(p), sha(p)))

lines += [
    "",
    "实录为 gzip（21.5MB → 219KB），`gunzip -c 实录/xxx.jsonl.gz` 即还原逐拍原文。",
    "",
    "## 四、留盘原片（**不入库**，仅在此入册；换机即失）",
    "",
    "不入库的理由：屏摄 100 帧共约 519MB，而本仓 `.git` pack 现仅 16.4MB——收进去会让历史永久膨胀且不可逆。",
    "比照 09-23 W4 先例「脚本可入库、数据不入库」与 10-08 架构可视化「显式例外、按件放行」。",
    "",
    "| 文件 | 字节 | SHA-256 |",
    "|---|---|---|",
]
for p in RAW:
    lines.append("| `{0}` | {1:,} | `{2}` |".format(rel(p), os.path.getsize(p), sha(p)))

lines += [
    "",
    "复验：`cd` 到仓库根，`sha256sum -c` 下面这份逐件表即可（原片在盘上时才有效）：",
    "",
    "```",
]
for p in RAW:
    lines.append("{0}  {1}".format(sha(p), rel(p)))
lines.append("```")
lines.append("")
lines.append("*生成：`python output/真机_1012/建清单.py`（哈希由脚本实算，不手抄）。*")

out = os.path.join(ROOT, "取证据清单.md")
io.open(out, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
print("wrote", rel(out), os.path.getsize(out), "bytes;",
      "入库", len(TRACKED), "件 / 留盘", len(RAW), "件")
