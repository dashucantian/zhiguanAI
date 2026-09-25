# -*- coding: utf-8 -*-
"""设备无关化扫描器 v3（可复用闸门）——把"设备专属硬编码"逐个列出并分类。

用法：python scan_device_hardcode.py [目标文件] [报告输出路径]
退出码：发现 A 类（真正需要改的硬编码条件）→ 1；否则 0。
v3 变更：
  ① 通道名收窄——本台子的脑电通道只有 NeuraDock 7ch 与 Muse 4ch，
     去掉 T5/T6（本面板里 T5/T6 是**测试项编号**，不是颞区通道）与 Fp1/Fp2/Pz/POz（未使用），
     消除"T5 十分钟稳定性"一类的大面积误伤。
  ② 报告可落盘（第二参数）——控制台是 GBK，中文会打花；落 UTF-8 文件供核对。

分类（v3 细分，避免误伤）：
  A 硬编码条件  —— 通道名/标称采样率/厂商端口被当作**通用条件** → 必须改"按档案取"
  B 正当举例    —— 同行含 例／举例／前科／替代／预设 → 保留
  C 已带条件    —— 同行含 仅／若厂商软件／蓝牙设备／按档案 → 已条件化，保留
  D 本机服务    —— 8777／console_server.py／Python 3.12 等（与设备无关）→ 保留
  E 命名层      —— 页面标题/文件名/正本互指等"这套台子叫什么" → 需法师定（非硬编码错误）
  F 设备专属正当—— T11 双设备对照、场③ 描述、NeuraDock 预设内容、T2 静态兜底行 → 保留
  G 注释/说明   —— 纯注释行（/* * // 开头）→ 不影响运行，仅文档，不计入 A
  X 推断区豁免  —— 落在 /* DEV-INFER-BEGIN */ … /* DEV-INFER-END */ 之间的行
                   （该区就是"把设备事实收在一处"的实现，按标记整区豁免）
"""
import io
import re
import sys

try:
    sys.stdout.reconfigure(errors='replace')      # 坑010 同族：GBK 控制台打不出 emoji
except Exception:
    pass

TARGET = sys.argv[1] if len(sys.argv) > 1 else '01_项目管理/20260925_NeuraDock设备性能测试流程表_v1.html'
REPORT = sys.argv[2] if len(sys.argv) > 2 else ''

# 只认**本台子真实用到**的通道名；T5/T6 在本面板是测试项编号，故意不收
CH = r'(?:CP5|CP6|PO3|PO4|O1|O2|Oz|TP9|TP10|AF7|AF8)'
PATTERNS = [
    ('通道名', re.compile(r'(?<![A-Za-z0-9])' + CH + r'(?![A-Za-z0-9])')),
    ('标称采样率', re.compile(r'250(?:\.0)?\s*Hz|256\s*Hz')),
    ('厂商端口/软件', re.compile(r'9600|打开数据服务|模拟器')),
    ('设备名', re.compile(r'NeuraDock|OpenBCI|Muse')),
    # v3 增补：**非 token 型**的设备事实词（电量/耳夹/佩戴/线材）——正是这类最容易被漏掉
    ('设备事实词', re.compile(r'3500\s*mAh|2\.5\s*mm|三段式|耳夹|模拟器\.bat|USB 隔离线|头环')),
]
RULE_E = ('<title>', 'class="htitle"', 'foot', '正本', '止观AI工作日志', '20260925_NeuraDock设备性能测试流程表_v1.md')
RULE_F = ('presets:', 'dp_name', 'dp_ch', 'dp_sf', 'dp_rule', 'dp_weak', '专属', 'T11', '双设备', 'Muse vs',
          't2s_cp5', 't2s_cp6', 't2s_po3', 't2s_po4', 't2s_o1', 't2s_oz', 't2s_o2',
          'T2 静息噪声底与贴底复查', '重点盯',
          # v3 增补：设备推断实现与其正当文案
          'DEV-INFER', 'devShortName', 'devTag', 'devPort', 'devLinkKind', 'devHelpText',
          'deviceChannels', 'alphaPickFrom', 'alphaKindText', 'mainAlphaText', 'mainsCh',
          'pickAlphaChannels', 'refreshDevHints', 'ALPHA_OCC', 'ALPHA_POST',
          '尚未识别设备', '兜底行', '不写死', '降级规则', '属替代')
RULE_B = ('例：', '举例', '前科', '替代', '（例', '例如', '预设')
RULE_C = ('仅', '若厂商软件', '蓝牙设备', '按档案', '按《设备档案》')
RULE_D = ('8777', 'console_server.py', 'Python 3.12', 'localStorage', 'posthoc', 'qc_pipeline')

buckets = {k: [] for k in 'ABCDEFGX'}


def code_of(ln, in_block):
    """剥掉块注释与行注释，返回 (该行真正的代码文本, 新的块注释状态)。
    只用来判断"这行有没有代码"——注释里提到设备名不算硬编码条件。
    注意 '//' 前是 ':' 时视为 URL（http://…），不当行注释。"""
    out, i, n = [], 0, len(ln)
    while i < n:
        if in_block:
            j = ln.find('*/', i)
            if j < 0:
                return ''.join(out), True
            in_block = False
            i = j + 2
            continue
        j = ln.find('/*', i)
        k = ln.find('//', i)
        if k > 0 and ln[k - 1] == ':':
            k = -1
        if k >= 0 and (j < 0 or k < j):
            out.append(ln[i:k])
            return ''.join(out), False
        if j < 0:
            out.append(ln[i:])
            return ''.join(out), False
        out.append(ln[i:j])
        i = j + 2
        in_block = True
    return ''.join(out), in_block


lines = io.open(TARGET, encoding='utf-8').read().split('\n')
infer = False
in_block = False
for i, ln in enumerate(lines, 1):
    code, in_block = code_of(ln, in_block)
    if 'BEGIN' in ln and ('DEV-INFER' in ln or 'PRESET-ROWS' in ln):
        infer = True
    if not any(p.search(ln) for _, p in PATTERNS):
        if 'END' in ln and ('DEV-INFER' in ln or 'PRESET-ROWS' in ln):
            infer = False
        continue
    tags = [name for name, p in PATTERNS if p.search(ln)]
    if infer:
        buckets['X'].append((i, tags, ln.strip()))
        if 'END' in ln and ('DEV-INFER' in ln or 'PRESET-ROWS' in ln):
            infer = False
        continue
    if not code.strip():                       # 纯注释／空行 → 不影响运行
        buckets['G'].append((i, tags, ln.strip()))
    elif ln.lstrip().startswith('# '):         # markdown 一级标题 = 命名层
        buckets['E'].append((i, tags, ln.strip()))
    elif any(k in ln for k in RULE_E):
        buckets['E'].append((i, tags, ln.strip()))
    elif any(k in ln for k in RULE_F):
        buckets['F'].append((i, tags, ln.strip()))
    elif any(k in ln for k in RULE_D):
        buckets['D'].append((i, tags, ln.strip()))
    elif any(k in ln for k in RULE_C):
        buckets['C'].append((i, tags, ln.strip()))
    elif any(k in ln for k in RULE_B):
        buckets['B'].append((i, tags, ln.strip()))
    else:
        buckets['A'].append((i, tags, ln.strip()))
    if 'END' in ln and ('DEV-INFER' in ln or 'PRESET-ROWS' in ln):
        infer = False

TITLES = [('A', 'A 硬编码条件（必须改）'), ('E', 'E 命名层（请法师定）'), ('B', 'B 正当举例'),
          ('C', 'C 已带条件'), ('D', 'D 本机服务'), ('F', 'F 设备专属正当'),
          ('G', 'G 注释/说明（不影响运行）'), ('X', 'X 推断区豁免')]
out = []
out.append('目标：' + TARGET)
for k, title in TITLES:
    out.append('')
    out.append('== ' + title + '：' + str(len(buckets[k])) + ' 行 ==')
    for i, tags, ln in buckets[k]:
        out.append('  行%-5d [%s] %s' % (i, '/'.join(tags), ln))
    if not buckets[k]:
        out.append('  （无）')
out.append('')
out.append('结论：需改 A 类 ' + str(len(buckets['A'])) + ' 行；命名层 E ' + str(len(buckets['E']))
           + ' 行待法师定；B/C/D/F/G/X 共 ' + str(sum(len(buckets[x]) for x in 'BCDFGX')) + ' 行为允许/豁免项')
text = '\n'.join(out)
print(text)
if REPORT:
    io.open(REPORT, 'w', encoding='utf-8', newline='\n').write(text + '\n')
    print('[报告已落盘] ' + REPORT)
sys.exit(1 if buckets['A'] else 0)
