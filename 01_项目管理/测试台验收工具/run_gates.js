/* 验收闸门总跑器（W1 工程线·2026-09-27 起用）
    purpose：把「改完 → 逐条手工跑闸门 → 手写复审单」压成一条命令，
            每次运行自动产出一份**可直接阅读的复审单**，供法师随时单独介入复核。
   usage ：node "01_项目管理/测试台验收工具/run_gates.js" --tag S3 --desc "步 1 只读骨架收口"
   产出 ：_analysis_tmp/W1D_复审/<tag>_<时间戳>.md   （本轮复审单，含每条闸门命令＋结果＋关键数字）
          _analysis_tmp/W1D_复审/LATEST.md          （始终指向最近一轮，法师只看这一份也行）
   纪律 ：本脚本**只跑不改**——不写面板、不写判据；退出码非 0 即本步不得收口。 */
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const REPO = path.join(__dirname, '..', '..');
const TOOL = __dirname;
const HTML = path.join(REPO, '01_项目管理', '20260925_NeuraDock设备性能测试流程表_v1.html');
const OUT_DIR = path.join(REPO, '_analysis_tmp', 'W1D_复审');

const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf('--' + k); return i >= 0 && argv[i + 1] ? argv[i + 1] : d; };
const TAG = arg('tag', 'RUN');
const DESC = arg('desc', '（未填本步说明）');

/* Python 解释器：按项目既定的全路径优先，取不到再退回 PATH 上的 python */
const PYPATHS = [path.join(process.env.LOCALAPPDATA || '', 'Programs', 'Python', 'Python312', 'python.exe'), 'python'];
const PY = PYPATHS.find(p => { const r = spawnSync(p, ['--version'], { encoding: 'utf8' }); return !r.error && r.status === 0; }) || 'python';
const SCAN = path.join(REPO, '05_产品与开发', 'muse-direct', 'tools', 'scan_device_hardcode.py');

/* 闸门清单：一条命令一道闸，scope 说明它守什么 */
const GATES = [
  { id: '语法', cmd: [process.execPath, path.join(TOOL, 'parse_check_panel_script.js')],
    what: '面板内联脚本能否被完整解析（本窗 node --check 替身）',
    grab: [/面板内联脚本纯解析通过（(\d+) 行/] },
  { id: '结构', cmd: [process.execPath, path.join(TOOL, 'check_nd_panel.js')],
    what: 'FLOW/字段 id 唯一·DOM 引用·CSS 配平·实时联动·G0–G5 覆盖·设备无关行为·条目计数',
    grab: [/字段 id 唯一：(\d+) 个输入位/, /勾选 id 唯一：(\d+) 项/, /判定块：(\d+) 个/,
           /花括号配平：\{ (\d+)/, /(\d+) 闸门覆盖 (\d+) 块/] },
  { id: '设备无关', cmd: [PY, SCAN, HTML, path.join(REPO, '_analysis_tmp', 'scan_W1D.txt')],
    env: { PYTHONIOENCODING: 'utf-8' },
    what: '全表硬编码扫描（A 类＝写死一台设备，须为 0 行）',
    grab: [/需改 A 类 (\d+) 行/, /== A 硬编码条件（必须改）：(\d+) 行/] },
  { id: '动作数', cmd: [process.execPath, path.join(TOOL, 'interaction_cost_baseline.js')],
    what: '人的动作总量（施工方案 §九 指标：129 → ≤60 → ≤20）',
    grab: [/动作总量（勾选＋需手填＋判定）＝ (\d+) 次/] },
  { id: '角色表一致', cmd: [process.execPath, path.join(TOOL, 'export_roles_config.js'), 'verify'],
    what: '派生文件《角色声明表.json》是否仍等于面板 ROLES（防双头分叉）',
    grab: [/(\d+) 项／(\d+) 场次，源指纹 ([0-9a-f]+)/] },
  { id: '逻辑冒烟', cmd: [process.execPath, path.join(TOOL, 'smoke_panel_logic.js')],
    what: '整段脚本可执行＋build() 建树＋步 1 骨架行为（主持人条/抽屉/派生视图/三档建议）',
    grab: [/共创建 (\d+) 个节点/] },
];

function run(g) {
  const r = spawnSync(g.cmd[0], g.cmd.slice(1),
    { cwd: REPO, encoding: 'utf8', maxBuffer: 32 * 1024 * 1024, env: Object.assign({}, process.env, g.env || {}) });
  const out = (r.stdout || '') + (r.stderr || '');
  return { code: r.status === null ? -1 : r.status, out, err: r.error ? String(r.error.message || r.error) : '' };
}

const rows = [];
let failed = 0;
console.log('══ W1 验收闸门总跑 · ' + TAG + ' ══');
GATES.forEach(g => {
  const r = run(g);
  const pass = r.code === 0;
  if (!pass) failed++;
  const nums = g.grab.map(re => { const m = r.out.match(re); return m ? m.slice(1).join('/') : null; }).filter(Boolean);
  const label = nums.join(' ｜ ');
  console.log((pass ? '  ✓ ' : '  ✗ ') + g.id.padEnd(6, ' ') + (label ? label : (pass ? '通过' : '见下方输出')));
  rows.push({ g, pass, code: r.code, out: r.out, label });
});

/* ── 复审单 ── */
if (!fs.existsSync(OUT_DIR)) fs.mkdirSync(OUT_DIR, { recursive: true });
const now = new Date();
const p2 = n => String(n).padStart(2, '0');
const ts = now.getFullYear() + '-' + p2(now.getMonth() + 1) + '-' + p2(now.getDate())
  + ' ' + p2(now.getHours()) + ':' + p2(now.getMinutes()) + ':' + p2(now.getSeconds());   /* 本机时钟，避免 UTC 与法师作息错八个钟头 */
const stamp = ts.replace(/[-: ]/g, '').slice(0, 12);
const lines = [];
lines.push('# 复审单 ' + TAG + ' · ' + DESC, '');
lines.push('- 生成：' + ts + '（`run_gates.js` 自动产出，本窗 AI-012·Qoder）');
lines.push('- 结论：**' + (failed ? '✗ ' + failed + ' 道闸门未过，本步不得收口' : '✓ 全部闸门通过，本步可收口（收口仍须法师放行）') + '**');
lines.push('- 被验文件：`' + path.relative(REPO, HTML).replace(/\\/g, '/') + '`');
lines.push('');
lines.push('| 闸门 | 守什么 | 结果 | 关键数字 |');
lines.push('|---|---|---|---|');
rows.forEach(r => lines.push('| ' + r.g.id + ' | ' + r.g.what + ' | ' + (r.pass ? '✓' : '✗ 退出码 ' + r.code) + ' | ' + (r.label || '—') + ' |'));
lines.push('');
lines.push('## 复审方法（法师单独介入用）', '');
lines.push('要单独复看任何一道闸，直接跑它自己的命令（均在仓库根执行；`$NODE` 为本窗 node 替代入口）：', '');
lines.push('```powershell');
lines.push('$NODE = "$env:LOCALAPPDATA\\deno\\node_compat_bin\\node.exe"');
lines.push('$PY  = "$env:LOCALAPPDATA\\Programs\\Python\\Python312\\python.exe"');
rows.forEach(r => {
  const exe = r.g.cmd[0] === process.execPath ? '$NODE' : (r.g.cmd[0] === PY ? '$PY' : '"' + r.g.cmd[0] + '"');
  const args = r.g.cmd.slice(1).map(a => '"' + path.relative(REPO, a).replace(/\\/g, '\\') + '"').join(' ');
  lines.push(exe + ' ' + args);
});
lines.push('```', '');
lines.push('## 各闸门原始输出（逐字，未删节）', '');
rows.forEach(r => {
  lines.push('### ' + r.g.id + (r.pass ? '（通过）' : '（未过）'));
  lines.push('```text');
  lines.push((r.out || '(无输出)').replace(/\r\n/g, '\n').trimEnd());
  lines.push('```', '');
});
lines.push('## 本窗边界自陈', '');
lines.push('- 只读校验，不改任何判据／阈值；`qc_pipeline.py` 阈值版本仍 **20260920**。');
lines.push('- 浏览器级渲染冒烟在本沙箱不可用（无头 Edge 不执行 JS），界面级实测须待 8777 有活数据时由人做。');
lines.push('- 本单一式两份：同目录 `LATEST.md` 恒为最近一轮。');
const md = lines.join('\n') + '\n';
const f1 = path.join(OUT_DIR, TAG + '_' + stamp + '.md');
fs.writeFileSync(f1, md, 'utf8');
fs.writeFileSync(path.join(OUT_DIR, 'LATEST.md'), md, 'utf8');
console.log('\n复审单：' + path.relative(REPO, f1).replace(/\\/g, '/'));
console.log('总结论：' + (failed ? '✗ 未过 ' + failed + ' 道' : '✓ 全过'));
process.exit(failed ? 1 : 0);
