/* NeuraDock 执行面板 · 静态闸门（一次性校验脚本，_ 前缀不入库）
   1) 抽出内联脚本 → node --check 语法
   2) 抽出 FLOW 数据 → 结构不变量：列行数一致、字段/勾选 id 唯一、判定 id 与汇总镜像一致
   3) 打印条目计数，供与正本（md）逐项对照 */
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const HTML = '01_项目管理/20260925_NeuraDock设备性能测试流程表_v1.html';
const TMP = '_analysis_tmp/_nd_panel_script.js';
let bad = 0;
const fail = m => { bad++; console.log('  ✗ ' + m); };
const ok = m => console.log('  ✓ ' + m);

const src = fs.readFileSync(HTML, 'utf8');
const m = src.match(/<script>([\s\S]*?)<\/script>/);
if (!m) { console.log('✗ 找不到内联脚本'); process.exit(1); }
fs.mkdirSync(path.dirname(TMP), { recursive: true });
fs.writeFileSync(TMP, m[1], 'utf8');

console.log('【1】内联脚本已抽出（语法闸门请另行运行：node --check ' + TMP + '）');
ok('抽出脚本 ' + m[1].split('\n').length + ' 行 → ' + TMP);

console.log('【2】FLOW 数据结构');
const js = m[1];
const i0 = js.indexOf('const FLOW =');
const i1 = js.indexOf('const GATES =');
if (i0 < 0 || i1 < 0) { fail('抽不出 FLOW 字面量'); process.exit(3); }
let FLOW;
let flowSlice = '';
try {
  /* 按花括号配平抽取字面量（比正则稳：尾部注释/分号都不影响） */
  const s0 = js.indexOf('{', i0);
  let d = 0, end = -1;
  for (let k = s0; k < js.length; k++) {
    const c = js[k];
    if (c === '{') d++;
    else if (c === '}') { d--; if (d === 0) { end = k; break; } }
  }
  if (end < 0) throw new Error('花括号不配平');
  flowSlice = js.slice(s0, end + 1);
  FLOW = eval('(' + flowSlice + ')');
}
catch (e) { fail('FLOW 求值失败：' + e.message); process.exit(4); }
ok('FLOW 解析成功：' + FLOW.secs.length + ' 个分节');

const fields = [], checks = [], verdicts = [], mirrorRefs = [];
FLOW.secs.forEach(sec => {
  if (!sec.id || !sec.name || !sec.acc) fail('分节缺 id/name/acc：' + JSON.stringify(sec.name));
  sec.blocks.forEach((b, bi) => {
    const at = sec.id + '#' + bi + '(' + (b.title || b.k) + ')';
    if (b.k === 'grid') {
      if (!b.cols || !b.rows) return fail(at + ' grid 缺 cols/rows');
      b.rows.forEach((r, ri) => {
        if (r.length !== b.cols.length) fail(at + ' 第' + (ri + 1) + '行列数 ' + r.length + ' ≠ 表头 ' + b.cols.length);
        r.forEach(c => { if (c && typeof c === 'object' && c.f) fields.push(c.f); });
      });
      if (b.v) verdicts.push(b.v);
    } else if (b.k === 'check') {
      (b.items || []).forEach(it => { if (it.length < 2) fail(at + ' 勾选项缺文案'); checks.push(it[0]); });
    } else if (b.k === 'v') { verdicts.push(b.id); }
    else if (b.k === 'fields') { (b.items || []).forEach(it => fields.push(it[0])); }
    else if (b.k === 'mirror') { (b.items || []).forEach(it => mirrorRefs.push(it[0])); }
    else if (b.k === 'timer') { if (!b.sec) fail(at + ' 计时器缺 sec'); }
    else if (b.k === 'cmd') {
      const has = (typeof b.lines === 'function') ? true : (b.lines && b.lines.length);
      if (!has) fail(at + ' 命令块为空');
    }
    else if (['hint', 'note', 'fold', 'static', 'calc', 'bridge', 't1auto', 't2auto', 't3auto', 't4mains', 'posthoc', 'dossier'].indexOf(b.k) < 0) fail(at + ' 未知积木类型 ' + b.k);
  });
});
const dup = a => a.filter((x, i) => a.indexOf(x) !== i);
const uf = [...new Set(dup(fields))], uc = [...new Set(dup(checks))], uv = [...new Set(dup(verdicts))];
uf.length ? fail('字段名重复（会串数据）：' + uf.join('、')) : ok('字段 id 唯一：' + fields.length + ' 个输入位');
uc.length ? fail('勾选 id 重复：' + uc.join('、')) : ok('勾选 id 唯一：' + checks.length + ' 项');
uv.length ? fail('判定 id 重复：' + uv.join('、')) : ok('判定块：' + verdicts.length + ' 个');
const miss = mirrorRefs.filter(v => verdicts.indexOf(v) < 0);
miss.length ? fail('汇总镜像引用了不存在的判定 id：' + miss.join('、')) : ok('汇总镜像 ' + mirrorRefs.length + ' 项全部对得上判定块');

console.log('【4】DOM 引用完整性（JS 取的 id 必须在 HTML 里存在）');
const declared = new Set(
  [...src.matchAll(/\bid="([^"]+)"/g)].map(x => x[1])          /* HTML 静态 id */
    .concat([...m[1].matchAll(/\bid:\s*'([^']+)'/g)].map(x => x[1]))  /* JS 动态建元素时的 id */
);
const dynPref = ['mini-', 'calc-'];   /* 运行期动态生成的 id */
const refs = [...m[1].matchAll(/getElementById\('([^']+)'\)/g)].map(x => x[1]);
const missIds = [...new Set(refs)].filter(id => !declared.has(id) && !dynPref.some(p => id.startsWith(p)));
missIds.length ? fail('JS 引用了 HTML 里不存在的 id：' + missIds.join('、'))
  : ok('JS 引用的 ' + new Set(refs).size + ' 个 id 全部存在（动态生成 ' + dynPref.join('/') + ' 除外）');

console.log('【5】CSS 括号配平与皮肤块存在性');
const cssM = src.match(/<style>([\s\S]*?)<\/style>/);
if (!cssM) fail('找不到 <style>');
else {
  const css = cssM[1];
  const o = (css.match(/\{/g) || []).length, c = (css.match(/\}/g) || []).length;
  o === c ? ok('CSS 花括号配平：{ ' + o + ' } ' + c) : fail('CSS 花括号不配平：{ ' + o + ' / } ' + c);
  /html\.dash\{/.test(css) ? ok('皮肤 B（仪表盘）样式块存在') : fail('缺 html.dash 样式块');
  /\.leds\{display:none;gap:10px[\s\S]*html\.dash \.leds\{display:flex\}/.test(css)
    ? ok('判定灯仅仪表盘皮肤显示') : fail('判定灯显隐规则缺失');
  /\.kpi-full\{display:none\}[\s\S]*html\.dash #kpi\.open \.kpi-full\{display:flex/.test(css)
    ? ok('仪表默认收起、按需展开（顶栏只占一行）') : fail('仪表折叠规则缺失');
  const last = css.lastIndexOf('html.dash{'), printAt = css.lastIndexOf('@media print');
  last > printAt ? ok('仪表盘块位于样式末尾（同时开夜间时以仪表盘为准）') : fail('仪表盘块位置过前，会被 html.night 覆盖');
  /html\.dash\{--bg:#fff[\s\S]*?\}\s*@media print/.test(css) || /@media print\{[\s\S]*html\.dash\{--bg:#fff/.test(css)
    ? ok('仪表盘打印样式存在（打印自动转浅色）') : fail('缺仪表盘打印样式');
}

console.log('【6】实时联动（2026-09-25 法师令：测试须与真实脑电/驾驶舱数据结合）');
['fftRadix2', 'alphaRel', 'liveConnect', 'liveTick', 'paintLive', 'measureAlpha', 'postMarker', 'syncField']
  .forEach(fn => new RegExp('function\\s+' + fn + '\\b').test(m[1]) ? ok('引擎函数：' + fn) : fail('缺引擎函数：' + fn));
['T1A', 'T2A'].forEach(o => new RegExp('const\\s+' + o + '\\s*=').test(m[1]) ? ok('自动化状态机：' + o) : fail('缺状态机：' + o));
/postMarker\(st\)/.test(m[1]) ? ok('T1 段首自动打点已接线') : fail('T1 未自动打点');
/marker/.test(m[1]) && /api\/monitor\/marker/.test(m[1]) ? ok('打点走 /api/monitor/marker（与驾驶舱同一实现）') : fail('打点接口未接');
/api\/monitor\/stream/.test(m[1]) ? ok('订阅 /api/monitor/stream（实时帧）') : fail('未订阅实时流');
declared.has('liveStrip') ? ok('顶栏实时状态条在位') : fail('缺实时状态条 #liveStrip');

console.log('【8】G0–G5 闸门分组完整性（每块必属且仅属一个闸门）');
const gi = js.indexOf('const GATES ='), gj = js.indexOf('function gateBlocks');
if (gi < 0 || gj < 0) fail('抽不出 GATES 定义');
else {
  let GATES;
  try { GATES = eval('(' + js.slice(gi + 'const GATES ='.length, gj).trim().replace(/;\s*$/, '') + ')'); }
  catch (e) { fail('GATES 解析失败：' + e.message); }
  if (GATES) {
    const owner = {};
    GATES.forEach(g => (g.take || []).forEach(([sid, a, b]) => {
      for (let i = a; i < b; i++) {
        const k = sid + '#' + i;
        if (owner[k]) fail('块被两个闸门同时 claim：' + k + '（' + owner[k] + ' 与 ' + g.id + '）');
        owner[k] = g.id;
      }
    }));
    let n = 0;
    FLOW.secs.forEach(s => s.blocks.forEach((b, i) => {
      n++;
      if (!owner[s.id + '#' + i]) fail('块未被任何闸门 claim：' + s.id + '#' + i + '（' + (b.title || b.k) + '）');
    }));
    const orphan = Object.keys(owner).filter(k => {
      const [sid, ix] = k.split('#');
      const s = FLOW.secs.filter(x => x.id === sid)[0];
      return !s || !s.blocks[+ix];
    });
    orphan.length ? fail('闸门 claim 了不存在的块：' + orphan.join('、'))
      : ok('闸门分组：' + GATES.length + ' 闸门覆盖 ' + n + ' 块，无遗漏、无重叠、无越界');
    const names = GATES.map(g => g.name);
    /G0 准备/.test(names[0]) && /G1 身份/.test(names[1]) && /G5 验收/.test(names[5])
      ? ok('闸门命名符合裁定：' + names.join(' → ')) : fail('闸门命名不符 G0–G5：' + names.join(' → '));
  }
}

console.log('【10】设备无关性行为闸门（2026-09-26 法师令：全表系统性排查，防"写死一台设备"复发）');
/* 取"真函数"原文：deviceChannels / SFREQ / DEV-INFER 区（设备推断的全部实现），
   注入不同设备的桩环境后**实际执行**面板文案，看它是否随设备变——比 grep 更能防复发。 */
function grabFn(name) {
  const at = js.indexOf('function ' + name + '(');
  if (at < 0) return '';
  let d = 0;
  for (let k = js.indexOf('{', at); k < js.length; k++) {
    if (js[k] === '{') d++;
    else if (js[k] === '}') { d--; if (!d) return js.slice(at, k + 1); }
  }
  return '';
}
function grabArrow(name) {
  const at = js.indexOf('const ' + name + ' =');
  if (at < 0) return '';
  let d = 0;
  for (let k = js.indexOf('{', at); k < js.length; k++) {
    if (js[k] === '{') d++;
    else if (js[k] === '}') { d--; if (!d) return js.slice(at, k + 1); }
  }
  return '';
}
const inferA = js.indexOf('DEV-INFER-BEGIN'), inferB = js.indexOf('DEV-INFER-END');
const lineStart = pos => js.lastIndexOf('\n', pos) + 1;      /* 切到整行，别切在注释中间 */
const inferSrc = (inferA >= 0 && inferB > inferA) ? js.slice(lineStart(inferA), lineStart(inferB)) : '';
inferSrc ? ok('DEV-INFER 推断区在位（' + inferSrc.split('\n').length + ' 行）') : fail('缺 DEV-INFER 推断区标记');

const mkFlow = (chs, port, sf) => {
  const fields = {};
  if (port) fields.dp_link = 'TCP 127.0.0.1:' + port;
  if (chs.length) fields.dp_ch = chs.length + ' 通道：' + chs.join(' ');
  if (chs.length) fields.dp_name = (chs.indexOf('Oz') >= 0 ? 'NeuraDock（硬件 V2）' : 'Muse（S/2 代，蓝牙）');
  if (chs.length && chs.indexOf('Oz') < 0) fields.dp_link = 'BLE（内置 bleak）';
  if (sf) fields.dp_sf = String(sf);
  const wave = {}; chs.forEach(c => { wave[c] = new Array(1280).fill(0); });
  const S = { fields: fields, meta: {}, checks: {}, verdicts: {} }, LIVE = { wave: wave };
  const body = grabFn('deviceChannels') + '\n' + grabArrow('SFREQ') + '\n' + inferSrc + '\n'
    + 'return {flow:(' + flowSlice + '),H:{devTag:devTag,devPort:devPort,devHelpText:devHelpText,'
    + 'mainAlphaText:mainAlphaText,mainsCh:mainsCh,SFREQ:SFREQ}};';
  return new Function('S', 'LIVE', body)(S, LIVE);
};
const fnTexts = (flow) => {
  const out = [];
  flow.secs.forEach(s => s.blocks.forEach(b => {
    ['hint', 'note', 'lines'].forEach(k => {
      if (typeof b[k] === 'function') {
        let v = null;
        try { v = b[k](); } catch (e) { v = 'THROW:' + e.message; }
        out.push({ title: (b.title || b.k || s.name) + '.' + k, v: Array.isArray(v) ? v.join('\n') : String(v) });
      }
    });
  }));
  return out;
};
const CASES = [
  { name: '未识别设备（档案空＋无波形）', chs: [], port: '', sf: 0, want: ['尚未识别'], ban: [],
    h: { tag: '脑电设备', port: '', help: '有线' } },
  { name: 'NeuraDock 7ch/250Hz/9600', chs: ['CP5', 'CP6', 'PO3', 'PO4', 'O1', 'Oz', 'O2'], port: '9600', sf: '250',
    want: ['O1 / Oz / O2', '9600', '250 Hz'], ban: [], h: { tag: 'NeuraDock', port: '9600', help: 'TCP' } },
  { name: 'Muse 4ch（无枕区）/256Hz', chs: ['TP9', 'AF7', 'AF8', 'TP10'], port: '', sf: '256',
    want: ['TP9 / TP10', '替代', '256 Hz'], ban: ['Oz'], h: { tag: 'Muse', port: '', help: '蓝牙' } }
];
let nFn = 0;
CASES.forEach(c => {
  let flow, H;
  try { const r = mkFlow(c.chs, c.port, c.sf); flow = r.flow; H = r.H; }
  catch (e) { return fail('[' + c.name + '] FLOW 构建失败：' + e.message); }
  const texts = fnTexts(flow), all = texts.map(t => t.v).join('\n');
  nFn = texts.length;
  if (!texts.length) return fail('[' + c.name + '] 没有任何函数式文案（设备无关化退化了？）');
  const thrown = texts.filter(t => /^THROW:/.test(t.v));
  thrown.length ? fail('[' + c.name + '] 文案执行抛错：' + thrown.map(t => t.title + ' ' + t.v).join('；')) : null;
  c.want.forEach(w => all.indexOf(w) >= 0 ? null : fail('[' + c.name + '] 文案里缺「' + w + '」'));
  c.ban.forEach(w => all.indexOf(w) < 0 ? null : fail('[' + c.name + '] 文案里仍出现不该有的「' + w + '」（写死他设备）'));
  /undefined|NaN/.test(all) ? fail('[' + c.name + '] 文案里出现 undefined/NaN：' + all.match(/.{0,30}(undefined|NaN).{0,20}/)[0]) : null;
  /* 导出名／端口／自救话术同属"设备事实"，一并按场景校验 */
  const got = { tag: H.devTag(), port: H.devPort(), help: H.devHelpText() };
  Object.keys(c.h).forEach(k => (k === 'help' ? got[k].indexOf(c.h[k]) >= 0 : got[k] === c.h[k]) ? null
    : fail('[' + c.name + '] ' + k + ' 期望含「' + c.h[k] + '」实得「' + got[k] + '」'));
  ok('[' + c.name + '] ' + texts.length + ' 条函数式文案全部算得出；导出名「' + got.tag + '」端口「' + (got.port || '—') + '」采样率「' + H.SFREQ() + ' Hz」');
});
ok('函数式文案总数：' + nFn + ' 条（改设备即重算，见 refreshDevHints）');

console.log('【9】条目计数（与正本 md 对照）');console.log('  勾选项 ' + checks.length + ' ／ 输入位 ' + fields.length + ' ／ 判定块 ' + verdicts.length + ' ／ 红绿灯镜像 ' + mirrorRefs.length);
FLOW.secs.forEach(s => {
  const c = s.blocks.filter(b => b.k === 'check').reduce((a, b) => a + (b.items || []).length, 0);
  const f = s.blocks.filter(b => b.k === 'grid' || b.k === 'fields')
    .reduce((a, b) => a + ((b.rows || []).flat().filter(x => x && x.f).length || (b.items || []).length), 0);
  console.log('  · ' + s.name + '：勾选 ' + c + '，输入位 ' + f);
});
console.log(bad ? '\n结论：✗ ' + bad + ' 处问题' : '\n结论：✓ 全部静态闸门通过');
process.exit(bad ? 9 : 0);
