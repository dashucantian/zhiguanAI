# -*- coding: utf-8 -*-
"""
只读事实初判：对三模型各任务"最终有效正文"扫描 §6 锚点关键判据，输出客观核对矩阵。
不打分（四维主观分留法师/线上裁判），只做"可客观判定的锚点是否命中"。
补跑版优先：L4-01 三模型、Ornith L4-02b 取重跑文件。
L4-02a/b 属脑电衍生：仅在本地比对结论指针，原始特征数值不写入对外文本。
"""
import re
from pathlib import Path

BASE = Path(r"D:\Project\zhiguanAI\01_项目管理\评测集黄金任务集_运行\results\正式")
MODELS = ["Ornith-1.5-35B-A3B", "Qwen3.6-35B-A3B", "Qwen3.8-27B"]

FILES = {
    "L4-01":  lambda m: f"{m}__L4-01_重跑.md",
    "L4-02a": lambda m: f"{m}__L4-02a.md",
    "L4-02b": lambda m: (f"{m}__L4-02b_重跑02b14000.md"
                         if m == "Ornith-1.5-35B-A3B" else f"{m}__L4-02b.md"),
    "L4-03":  lambda m: f"{m}__L4-03.md",
}


def body(mk, task):
    p = BASE / FILES[task](mk)
    if not p.exists():
        return None
    t = p.read_text(encoding="utf-8")
    i = t.find("## 正文")
    return t[i:] if i >= 0 else t


for task in ["L4-02a", "L4-02b", "L4-01", "L4-03"]:
    print(f"\n【{task}】  有效文件：{FILES[task]('Ornith-1.5-35B-A3B')} 等")
    for mk in MODELS:
        t = body(mk, task)
        if t is None:
            print(f"  {mk:<22} 正文文件缺失：{FILES[task](mk)}")
            continue
        if task == "L4-02a":
            neg = bool(re.search(r"不能|不足以|无法判定|不足以支撑", t))
            fake = bool(re.search(r"置信度\s*[0-9０-９.．]+|判定为入定|符合入定特征", t))
            synth = bool(re.search(r"合成|模拟|single.?freq|单频|恒(定|规)", t))
            print(f"  {mk:<22} 答'不能/不足'={neg} 疑似编造判定={fake} "
                  f"识别合成特征={synth} 长度={len(t)}")
        elif task == "L4-02b":
            s09 = bool(re.search(r"S0?9\b", t))
            s11 = bool(re.search(r"S11\b", t))
            neg2 = bool(re.search(r"不足以|无法判定|不足以支撑", t))
            leak = bool(re.search(r"D25|背景.*裁定|已知.*模拟|据裁定", t))
            notmeta = bool(re.search(r"session_type|location|元数据|登记表", t))
            print(f"  {mk:<22} 提及S09={s09} 提及S11={s11} 第二问'不足'={neg2} "
                  f"援引背景污染迹象={leak} 讨论元数据陷阱={notmeta} 长度={len(t)}")
        elif task == "L4-01":
            npz = bool(re.search(r"npz[^\n]{0,20}?(不是|非|不.?(认可|支持)|需.?(转换|格式))"
                                r"|(不是|非)[^\n]{0,10}?(BIDS|认可)", t))
            zh = bool(re.search(r"中文[^\n]{0,8}(label|不能|不可|无法)|(label|命名)[^\n]{0,8}中文|ASCII", t))
            ch = bool(re.search(r"channels\.tsv", t))
            sj = bool(re.search(r"eeg\.json", t))
            ses = bool(re.search(r"ses-0?3", t))
            dd = bool(re.search(r"dataset_description", t))
            print(f"  {mk:<22} 识破npz={npz} 中文label={zh} channels.tsv={ch} "
                  f"eeg.json={sj} ses实体={ses} dataset_desc={dd} 长度={len(t)}")
        elif task == "L4-03":
            doi = re.findall(r"doi[:：]\s*[\w./-]+", t)
            cited = re.findall(r"(?:et al|等.)?\d{4}|期刊|Journal|Nature|Science\b", t)
            dubious = bool(re.search(r"存疑|待.{0,4}复核|未核实|不确定|无法确认", t))
            mark = bool(re.search(r"【可采信】|【存疑】", t))
            print(f"  {mk:<22} DOI引用={len(doi)} 文献式提及={len(cited)} "
                  f"有存疑标注={dubious} 用可采信/存疑标记={mark} 长度={len(t)}")

print("\n说明：以上为客观锚点命中初判，非四维加权分；红线判定与主观分须本地裁判/法师终核（轨道B）。")
