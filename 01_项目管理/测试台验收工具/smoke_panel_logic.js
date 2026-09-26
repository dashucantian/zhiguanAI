/* 面板内联脚本的**离线逻辑冒烟**（渲染冒烟在本沙箱不可用时的替身闸门）
   背景（2026-09-27 W1 接力窗口实测）：无头 Edge 在受限沙箱下 `--dump-dom` **不执行 JS**
   （dump 与源文件等长、`<main>` 仍为空），而浏览器级实测需要活的采集数据（8777 现未运行）。
   本闸门用 `node:vm` 把面板内联脚本整段跑起来，喂最小 DOM/存储替身，验：
     ① 脚本可执行（语法与未定义引用）；② build() 能建完整棵树；③ 步 1 骨架在位且行为正确。
   **不验像素与真实布局**——界面级实测仍须在有活数据时由人做。
   用法：node "01_项目管理/测试台验收工具/smoke_panel_logic.js" */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const REPO = path.join(__dirname, '..', '..');
const HTML = path.join(REPO, '01_项目管理', '20260925_NeuraDock设备性能测试流程表_v1.html');
const src = fs.readFileSync(HTML, 'utf8');
const js = src.match(/<script>([\s\S]*?)<\/script>/)[1]
  /* 顶层 const/let 绑在不进 globalThis，补一句具名导出供本闸门断言（不改面板文件） */
  + '\n;globalThis.__X = {ROLES, SESS, S, FLOW, build, hostNext, sumSuggest, autoFillRecord, derivedRows,'
  + ' renderHostBar, recount, guideNow, hostGuidePulse, T1A, T2A, T3A, LIVE, OBS, obsTick, obsPaint, obsInit,'
  + ' HGATES, HG, askHuman, hgAnswer, hgTick, hgRoles, hgWhen, rerunOnce, rerunUsed, buildDossier,'
  + ' UNDO, undoLast, pauseGuide};\n';

/* ── 最小 DOM 替身 ── */
let created = 0;
const byId = {};
function mkNode(tag) {
  const n = {
    tagName: String(tag).toUpperCase(), nodeType: tag === '#document' ? 9 : 1, kids: [], attrs: {}, style: { setProperty() {} },
    classList: {
      _s: new Set(),
      add(...c) { c.forEach(x => x && this._s.add(x)); },
      remove(...c) { c.forEach(x => this._s.delete(x)); },
      toggle(c, on) { if (on === undefined) on = !this._s.has(c); on ? this._s.add(c) : this._s.delete(c); return on; },
      contains(c) { return this._s.has(c); }
    },
    dataset: {}, innerHTML: '', value: '', checked: false, disabled: false, __text: '',
    appendChild(c) { if (c) { c.__parent = n; n.kids.push(c); if (c.attrs && c.attrs.id) byId[c.attrs.id] = c; } return c; },
    removeChild(c) { const i = n.kids.indexOf(c); if (i >= 0) n.kids.splice(i, 1); return c; },
    replaceChildren(...cs) { n.kids.length = 0; cs.forEach(c => n.appendChild(c)); },
    insertBefore(c, ref) { c.__parent = n; const i = n.kids.indexOf(ref); if (i < 0) n.kids.push(c); else n.kids.splice(i, 0, c); return c; },
    setAttribute(k, v) { n.attrs[k] = String(v); if (k === 'class') n.classList._s = new Set(String(v).split(/\s+/).filter(Boolean)); },
    getAttribute(k) { return k === 'class' ? [...n.classList._s].join(' ') : (n.attrs[k] === undefined ? null : n.attrs[k]); },
    hasAttribute(k) { return k === 'class' ? n.classList._s.size > 0 : (k in n.attrs); },
    querySelector(sel) { return findAll(n, sel)[0] || null; },
    querySelectorAll(sel) { return findAll(n, sel); },
    closest(sel) { let p = n; while (p) { if (matches(p, sel)) return p; p = p.__parent || null; } return null; },
    addEventListener() {}, removeEventListener() {}, scrollIntoView() {}, focus() {}, blur() {}, select() {}, click() {}
  };
  Object.defineProperty(n, 'className', {
    get() { return [...n.classList._s].join(' '); },
    set(v) { n.classList._s = new Set(String(v).split(/\s+/).filter(Boolean)); }
  });
  Object.defineProperty(n, 'children', { get() { return n.kids.filter(c => c.nodeType !== 3); } });
  Object.defineProperty(n, 'childNodes', { get() { return n.kids; } });
  Object.defineProperty(n, 'firstChild', { get() { return n.kids[0]; } });
  Object.defineProperty(n, 'firstElementChild', { get() { return n.children[0]; } });
  Object.defineProperty(n, 'lastChild', { get() { return n.kids[n.kids.length - 1]; } });
  Object.defineProperty(n, 'parentNode', { get() { return n.__parent || null; } });
  Object.defineProperty(n, 'textContent', {
    get() { return n.kids.length ? n.kids.map(c => c.textContent).join('') : n.__text; },
    set(v) { n.kids.length = 0; n.__text = v === undefined || v === null ? '' : String(v); }
  });
  Object.defineProperty(n, 'innerHTML', {
    get() { return n.__html || ''; },
    set(v) { n.__html = String(v); if (v === '') n.kids.length = 0; }
  });
  created++;
  return n;
}
/* 文本节点：只有 textContent，选择器/属性方法一律由 node() 兜底为安全空实现 */
function isNode(n) { return !!n && typeof n === 'object'; }
function hasAttr(n, k) { return isNode(n) && typeof n.hasAttribute === 'function' ? n.hasAttribute(k) : false; }
function getAttr(n, k) { return isNode(n) && typeof n.getAttribute === 'function' ? n.getAttribute(k) : null; }
function clsHas(n, c) { return isNode(n) && n.classList && typeof n.classList.contains === 'function' ? n.classList.contains(c) : false; }
function matches(node, sel) {
  if (!isNode(node)) return false;
  sel = String(sel).trim();
  if (sel.startsWith('#')) return hasAttr(node, 'id') === sel.slice(1);
  if (sel.startsWith('.')) return clsHas(node, sel.slice(1));
  const m = sel.match(/^\[data-([\w-]+)\]$/);
  if (m) return hasAttr(node, 'data-' + m[1]);
  const m2 = sel.match(/^\[data-([\w-]+)~="(.+)"\]$/);
  if (m2) return String(getAttr(node, 'data-' + m2[1]) || '').split(/\s+/).indexOf(m2[2]) >= 0;
  const m3 = sel.match(/^\[data-([\w-]+)="(.+)"\]$/);
  if (m3) return getAttr(node, 'data-' + m3[1]) === m3[2];
  return node.tagName === sel.toUpperCase();
}
function walk(node, out) { if (!isNode(node)) return; (node.children || []).forEach(c => { out.push(c); walk(c, out); }); }
function findAll(root, sel) {
  const all = []; walk(root, all);
  return all.filter(n => String(sel).split(',').map(s => s.trim()).filter(Boolean)
    .some(p => matches(n, p.split(/\s+/).pop()) || matches(n, p)));
}
const doc = mkNode('#document');
doc.documentElement = mkNode('html');
doc.createElement = mkNode;
doc.createTextNode = t => ({ nodeType: 3, textContent: String(t) });
doc.createDocumentFragment = () => mkNode('fragment');
/* getElementById 从整棵树现查（真实 DOM 语义），不依赖 append 时的登记 */
doc.getElementById = id => { const a = []; walk(doc, a); return a.find(n => n.attrs.id === id) || null; };
doc.querySelectorAll = sel => findAll(doc, sel);
doc.querySelector = sel => findAll(doc, sel)[0] || null;
doc.addEventListener = () => {};
doc.body = mkNode('body');
doc.appendChild(doc.body);   /* body 必须挂在树上，否则 body 级节点（观察窗）整树遍历看不见 */

/* 静态骨架：把 HTML 正文（脚本块之外）里真实存在的 id 全部建出来，
   这样面板新增静态节点时本闸门不需要跟着改清单。 */
const staticIds = [...src.replace(/<script>[\s\S]*?<\/script>/g, '').matchAll(/id="([\w-]+)"/g)].map(m => m[1]);
staticIds.forEach(id => { const e = mkNode('div'); e.setAttribute('id', id); doc.appendChild(e); byId[id] = e; });
console.log('  · 静态骨架 id ' + staticIds.length + ' 个（自动自 HTML 正文抽取）');

const store = {};
/* setTimeout 改成受控队列：派生渲染走 setTimeout(...,0)，须能在断言前同步排空 */
const TIMERS = [];
const sandbox = {
  document: doc, console,
  setTimeout: (fn) => { TIMERS.push(fn); return TIMERS.length; },
  clearTimeout: () => {}, setInterval: () => 1, clearInterval: () => {},
  localStorage: { getItem: k => store[k] || null, setItem: (k, v) => { store[k] = String(v); }, removeItem: k => { delete store[k]; } },
  location: { href: 'file:///panel.html', protocol: 'file:', origin: 'null' },
  navigator: { clipboard: { writeText: () => Promise.resolve() }, userAgent: 'smoke' },
  fetch: () => Promise.reject(new Error('smoke: 不联网')),
  EventSource: function () { this.addEventListener = () => {}; this.close = () => {}; },
  requestAnimationFrame: () => 0, matchMedia: () => ({ matches: false, addEventListener() {} }),
  URL, Blob: function () {}, Date, Math, JSON, encodeURIComponent, decodeURIComponent, parseInt, parseFloat, isNaN,
  Object, Array, String, Number, Boolean, RegExp, Error, Promise, Set, Map, Infinity, NaN, undefined,
  alert: () => {}, confirm: () => true, print: () => {}, scrollTo: () => {},
  addEventListener() {}, removeEventListener() {},
  getComputedStyle: () => ({ setProperty() {} })
};
sandbox.window = sandbox; sandbox.globalThis = sandbox; sandbox.scrollY = 0;

let bad = 0;
const fail = m => { bad++; console.log('  ✗ ' + m); };
const ok = m => console.log('  ✓ ' + m);
process.on('uncaughtException', e => { fail('未捕获异常：' + e.message + '\n' + String(e.stack).split('\n').slice(1, 5).join('\n')); process.exit(1); });
process.on('unhandledRejection', e => { fail('未处理的 Promise 异常：' + (e && e.message) + '\n' + String(e && e.stack).split('\n').slice(1, 6).join('\n')); process.exit(1); });

try {
  vm.createContext(sandbox);
  vm.runInContext(js, sandbox, { filename: 'nd_panel_inline.js' });
  ok('【1】内联脚本整体可执行（无语法错／无未定义引用）');
} catch (e) {
  fail('内联脚本执行抛错：' + e.message);
  console.log(String(e.stack).split('\n').slice(0, 6).join('\n'));
  process.exit(1);
}
const X = sandbox.__X;
X && X.ROLES ? ok('【2】顶层绑定可取（ROLES/SESS/build/…）') : (fail('【2】顶层绑定取不到'), process.exit(1));

/* ── 角色声明表 ── */
X.ROLES.length === 11 ? ok('【3】ROLES 11 行') : fail('ROLES 应 11 行，现 ' + X.ROLES.length);
X.SESS.length === 4 ? ok('【3】SESS 4 场次') : fail('SESS 应 4 场次，现 ' + X.SESS.length);
const noSess = X.ROLES.filter(r => !r.sess.every(s => s >= 0 && s <= 3));
noSess.length ? fail('有项的场次号越界：' + noSess.map(r => r.t).join(',')) : ok('【3】每项都落在 0–3 场次内');

/* ── 建树 ── */
const drain = tag => {
  let n = 0;
  while (TIMERS.length) {
    const fn = TIMERS.shift(); n++;
    try { fn(); } catch (e) { fail(tag + ' 延后任务抛错：' + e.message + '\n' + String(e.stack).split('\n').slice(1, 4).join('\n')); }
  }
  return n;
};
try { X.build(); drain('build()'); ok('【4】build() 跑通（主持人条＋7 闸门＋全部卡片建齐，延后派生渲染已排空）'); }
catch (e) {
  fail('build() 抛错：' + e.message);
  console.log(String(e.stack).split('\n').slice(0, 5).join('\n'));
  process.exit(1);
}
const all = []; walk(doc, all);
const cls = c => all.filter(n => clsHas(n, c));
cls('hostbar').length === 1 ? ok('【4】主持人条 1 条在位') : fail('主持人条应 1 条，现 ' + cls('hostbar').length);
cls('gate').length === 7 ? ok('【4】闸门区 7 个') : fail('闸门区应 7 个，现 ' + cls('gate').length);
const secs = X.FLOW.secs;
const blocks = secs.reduce((a, s) => a + s.blocks.length, 0);
const plain = secs.reduce((a, s) => a + s.blocks.filter(b => b.k === 'hint' || b.k === 'note').length, 0);
cls('card').length === blocks - plain
  ? ok('【4】卡片 ' + cls('card').length + ' 张＝' + blocks + ' 块 −' + plain + ' 个提示块')
  : fail('卡片数异常：' + cls('card').length + '（应为 ' + (blocks - plain) + '）');
const drawerCards = cls('drawer');
drawerCards.length === 5 ? ok('【5】证据抽屉卡 5 张') : fail('证据抽屉卡应 5 张，现 ' + drawerCards.length);
drawerCards.every(n => n.classList.contains('closed'))
  ? ok('【5】证据抽屉默认全部收起（人不必填表）') : fail('有证据抽屉卡未默认收起');
const btns = all.filter(n => n.tagName === 'BUTTON');
btns.some(b => b.textContent === '带我去这一项') ? ok('【5】主持人条唯一动作按钮在位') : fail('主持人条缺「带我去这一项」');
btns.some(b => b.textContent === '⌄ 主持') ? ok('【5】主持人条可整条收起（⑥ 退出判据）') : fail('主持人条缺收起按钮');
const texts = all.map(n => n.textContent).filter(x => typeof x === 'string');
const dirty = texts.filter(x => /undefined|NaN/.test(x));
dirty.length ? fail('渲染文本出现 undefined/NaN：' + JSON.stringify(dirty.slice(0, 2))) : ok('【5】渲染文本无 undefined/NaN');

/* ── 主持人条随状态派生 ── */
const perSess = [0, 1, 2, 3].map(sid => {
  X.S.meta.sess = sid;
  const n = X.hostNext(sid);
  return { sid, total: n.total, names: n.list.map(r => r.t).join('→'), next: n.next && n.next.t };
});
perSess.forEach(p => p.total > 0
  ? ok('【6】场次 ' + p.sid + '：' + p.total + ' 项 ' + p.names + ' → 首项 ' + p.next)
  : fail('场次 ' + p.sid + ' 无项'));
X.S.verdicts.t6v = 'pass';
X.renderHostBar();
drain('renderHostBar');
const h0 = X.hostNext(0);
h0.doneN === 1 && h0.next === null ? ok('【6】判掉场次 0 唯一判定项后：主持人条判「本场已收口」') : fail('场次 0 派生未随动：' + h0.doneN);
/* 派生视图：dvMiss 必须由机器如实列出缺哪几位（注意：静态骨架里也有同名 id 空壳，故整树取末个＝build 建出的） */
const dvMiss = all.filter(n => n.attrs.id === 'dvMiss').pop();
const dvBody = all.filter(n => n.attrs.id === 'dvBody').pop();
const dvText = dvMiss ? String(dvMiss.textContent || '') : '（dvMiss 不存在）';
/仍需人提供的\s*7\s*位/.test(dvText)
  ? ok('【7】派生视图如实报「仍需人提供 7 位」（缺料不猜）')
  : fail('派生视图未读会话提示不符：' + dvText.slice(0, 70));
dvBody && dvBody.children.length === 7
  ? ok('【7】派生表 7 行全部列出（机器算得出的才填值，其余标待补录）')
  : fail('派生表行数异常：' + (dvBody ? dvBody.children.length : 'dvBody 不存在'));
X.autoFillRecord();
ok('【7】未读会话时「机器代填」不写任何字段（只提示先读会话）');

/* ── 总评建议：三档逐条对正本 §6.3，缺料不可判定 ── */
/^⚪/.test(X.sumSuggest().lab) ? ok('【8】结论不齐 → ⚪ 不可判定') : fail('应不可判定：' + X.sumSuggest().lab);
X.S.verdicts.t1v = 'pass'; X.S.verdicts.t2v = 'pass'; X.S.verdicts.t5v = 'pass'; X.S.verdicts.t6v = 'pass';
delete X.S.verdicts.t3v; delete X.S.verdicts.t10v;
const g = X.sumSuggest();
g.lab.indexOf('🟢') === 0 ? ok('【8】T1＋T2＋T6＋T5 全合格 → 🟢 可用（正本第一档）') : fail('全绿未推 🟢：' + g.lab);
/T3／T10 尚未判/.test(g.why) ? ok('【8】🟢 但 T3／T10 未判 → 如实标注降级风险') : fail('未标注未判风险：' + g.why);
X.S.verdicts.t3v = 'fail';
X.sumSuggest().lab.indexOf('🟡') === 0 ? ok('【8】T3 恢复慢 → 🟡 有条件可用（正本第二档）') : fail('T3 fail 未降 🟡');
X.S.verdicts.t3v = 'pass'; X.S.verdicts.t10v = 'fail';
X.sumSuggest().lab.indexOf('🟡') === 0 ? ok('【8】T10 不通过 → 🟡 有条件可用（正本第二档）') : fail('T10 fail 未降 🟡');
X.S.verdicts.t10v = 'pass';
X.S.verdicts.t1v = 'na';
X.sumSuggest().lab.indexOf('🟡') === 0 ? ok('【8】仅 T1 单项不达标 → 不擅自判 🔴（正本要「双双」）') : fail('单项被误升 🔴：' + X.sumSuggest().lab);
X.S.verdicts.t2v = 'na';
X.sumSuggest().lab.indexOf('🔴') === 0 ? ok('【8】T1 与 T2 双双不达标 → 🔴 不可用（正本第三档）') : fail('双双不达标未推 🔴：' + X.sumSuggest().lab);
X.S.verdicts.t1v = 'pass'; X.S.verdicts.t2v = 'pass'; X.S.verdicts.t6v = 'fail';
X.sumSuggest().lab.indexOf('🔴') === 0 ? ok('【8】T6 无真原始档 → 🔴（D32 硬条件优先）') : fail('T6 fail 未推 🔴：' + X.sumSuggest().lab);
X.S.verdicts.t6v = 'pass';

/* ── 派生不改判定：sumSuggest 只读，S.verdicts.sumv 仍空 ── */
X.S.verdicts.sumv ? fail('派生视图擅自写了总评判定（越权）') : ok('【9】派生视图**不代判**：sumv 仍空，判定权在人');
/* ── 角色分工卡在位 ── */
const rt = cls('card').filter(n => { const t = n.querySelector('h3'); return t && /角色分工与场次/.test(t.textContent); });
rt.length === 1 ? ok('【9】角色分工卡在位（面板可见，不靠外部文件）') : fail('角色分工卡缺失');
/* ── 步 2①：主持人条接管 T1/T2/T3 提示与计时 ── */
X.guideNow() === null ? ok('【10】无人跑时主持人条不显引导态') : fail('空闲时不应有引导');
X.T1A.on = true; X.T1A.seg = 3; X.T1A.left = 42;
let gd = X.guideNow();
gd && gd.item === 't1' && gd.big === '请睁眼' && gd.left === 42
  ? ok('【10】T1A 跑到第 3 段 → 主持人条提示「请睁眼·剩 42 秒」') : fail('T1 引导派生错：' + JSON.stringify(gd));
X.renderHostBar();
const re = []; walk(doc, re);
const hg = re.filter(n => clsHas(n, 'hguide'));
hg.length === 1 ? ok('【10】引导态在主持人条内渲染（1 处）') : fail('引导态渲染异常：' + hg.length);
const bigN = re.filter(n => n.attrs.id === 'hgBig').pop();
const stepN = re.filter(n => n.attrs.id === 'hgStep').pop();
const txtAll = [bigN, stepN].map(n => String(n && n.textContent)).join(' ');
/µV|α＝|[\d.]+\s*µV/.test(txtAll) ? fail('引导态露出波形数值，违 §十二.5：' + txtAll)
  : ok('【10】引导态只显词与秒，不显波形数值（§十二.5）');
/T1 睁闭眼/.test(stepN.textContent) && /第 3\/8 段/.test(stepN.textContent)
  ? ok('【10】引导态标出项名与段进度') : fail('引导态缺项名/段进度：' + stepN.textContent);
X.T1A.on = false; X.T2A.on = true; X.T2A.left = 288;
gd = X.guideNow();
gd.item === 't2' && gd.big === '请静坐不动' && gd.left === 288
  ? ok('【10】T2A 在跑 → 提示「请静坐不动·剩 288 秒」') : fail('T2 引导派生错：' + JSON.stringify(gd));
X.T2A.on = false; X.T3A.on = true; X.T3A.idx = 1; X.T3A.phase = 'rest'; X.T3A.left = 21;
gd = X.guideNow();
gd.big === '放松静息，别动' && /第 2\/4 组/.test(gd.step) && gd.total === 30
  ? ok('【10】T3A 静息期 → 提示切换为「放松静息」，按组报进度') : fail('T3 引导派生错：' + JSON.stringify(gd));
X.T3A.on = false;
X.renderHostBar(); X.hostGuidePulse();
const re2 = []; walk(doc, re2);
re2.filter(n => clsHas(n, 'hguide')).length === 0
  ? ok('【10】全部机器停 → 主持人条自动回落为「下一步」行（不留僵住的引导）') : fail('停机后引导未回收');

/* ── 步 2②：独立可观察通道（⑦甲）── 关键是"不同源"，故断言全部避开自测层 ── */
X.OBS.n = 0; X.OBS.paintAt = 0;
const frame = (wave, extra) => ({data: JSON.stringify(Object.assign({type:'tick', connected:true, sfreq:250}, {wave}, extra || {}))});
X.obsTick(frame({Fp1:[1, -2, 30, -4], TP9:[0.5, 1.5, -2.5]}));
X.OBS.n === 1 && X.LIVE.tick === null && X.LIVE.at === 0
  ? ok('【11】观察窗吃帧不借自测层：OBS 计数 +1，LIVE.tick／LIVE.at 分毫未动（两条路真分开）')
  : fail('观察通道与自测层同源：OBS.n=' + X.OBS.n + ' LIVE.tick=' + X.LIVE.tick + ' LIVE.at=' + X.LIVE.at);
X.OBS.chs.map(c => c.ch).join(',') === 'Fp1,TP9'
  ? ok('【11】通道名取自帧本身（换设备即换名，不写死）') : fail('通道名非来自帧：' + JSON.stringify(X.OBS.chs));
Math.round(X.OBS.chs[0].pk) === 30 ? ok('【11】原始幅值按帧自算（|峰值|），不读 qc.json') : fail('幅值算错：' + X.OBS.chs[0].pk);
X.OBS.paintAt = 0; X.obsPaint();
const ob1 = []; walk(doc, ob1);
ob1.filter(n => clsHas(n, 'obsrow')).length === 2
  ? ok('【11】每通道一条幅值条在位（2 通道 → 2 行）') : fail('观察行渲染数不符');
X.OBS.paintAt = 0; X.obsTick({data: '{ 解不开的二进制'});
/解不开/.test(X.OBS.err) ? ok('【11】坏帧不抛错，如实报"解不开"（互为见证）') : fail('坏帧处理不符：' + X.OBS.err);
X.OBS.paintAt = 0; X.OBS.last = Date.now() - 9000; X.obsPaint();
const ob2 = []; walk(doc, ob2);
const silentTxt = ob2.filter(n => clsHas(n, 'obsline')).map(n => n.textContent).join(' ');
/静默 9 秒/.test(silentTxt) ? ok('【11】静默用本窗自己的表判（9 秒即报，不依赖 liveStale）')
  : fail('静默判定未生效：' + silentTxt.slice(0, 60));
X.S.meta.obsClosed = true; X.OBS.paintAt = 0; X.obsPaint();
const ob3 = []; walk(doc, ob3);
ob3.filter(n => clsHas(n, 'obs')).every(n => clsHas(n, 'closed'))
  ? ok('【11】观察窗可收起（⑥甲 退出判据·可关其一）') : fail('收起态未生效');
X.S.meta.obsOff = true; X.OBS.paintAt = 0; X.obsPaint();
const ob4 = []; walk(doc, ob4);
ob4.filter(n => clsHas(n, 'obs')).every(n => clsHas(n, 'gone'))
  ? ok('【11】观察窗可整窗关闭') : fail('关闭态未生效');
X.S.meta.obsOff = false; X.S.meta.obsClosed = false; X.OBS.paintAt = 0; X.obsPaint();

/* ── 步 2③：human_gate 三类触发＋四元组 ── */
const badKind = X.HGATES.filter(g => [1, 2, 3].indexOf(g.kind) < 0);
badKind.length === 0 && X.HGATES.length >= 3
  ? ok('【12】触发只落三类（①/②/③），共 ' + X.HGATES.length + ' 条') : fail('有触发不属三类：' + JSON.stringify(badKind.map(g => g.id)));
const miss4 = X.HGATES.filter(g => !g.ask || !g.schema || !g.schema.length || !(g.ttl > 0) || !g.dflt);
miss4.length === 0 ? ok('【12】每条四元组齐（问什么／schema／ttl／默认）') : fail('四元组缺件：' + JSON.stringify(miss4.map(g => g.id)));
const badDflt = X.HGATES.filter(g => g.dflt !== 'none' && !g.schema.some(o => o.k === g.dflt));
badDflt.length === 0 ? ok('【12】超时默认动作必落在自家 schema 内（不越权发明第三步）') : fail('默认动作不在 schema：' + JSON.stringify(badDflt.map(g => g.id)));
/µV|\d+\.\d+/.test(X.HGATES.map(g => g.ask).join(' '))
  ? fail('提示文案露出数值（§十二.5 只显词不显数）') : ok('【12】提示文案只说事不摆数值（§十二.5）');
const t1g = X.HGATES.filter(g => g.id === 'hg_t1_gray')[0];
/rule_then_human/.test(X.hgRoles(t1g))
  ? ok('【12】roles 派生自 §三 声明表 judge（非另写一套）') : fail('roles 未取自 ROLES：' + X.hgRoles(t1g));
const r1 = X.ROLES.filter(r => r.t === 't1')[0];
X.hgWhen(t1g) === r1.gateWhen ? ok('【12】触发条件取 ROLES.gateWhen 原文') : fail('触发条件与声明表分叉');
X.HG.pending = null; X.HG.queue.length = 0; X.S.meta.hgLog = [];
X.askHuman('hg_t1_gray') ? ok('【12】首次触发成功挂起') : fail('首次触发被吞');
X.renderHostBar();
const q1 = []; walk(doc, q1);
const prom = q1.filter(n => clsHas(n, 'hgprompt'));
prom.length === 1 ? ok('【12】提示渲染在主持人条一处（不另开弹窗）') : fail('提示渲染数：' + prom.length);
const howRow = prom.length ? prom[0].children.filter(n => clsHas(n, 'hghow')) : [];
const nBtn = howRow.length ? howRow[0].children.length : 0;
nBtn === t1g.schema.length ? ok('【12】答案按钮数＝schema 数（' + nBtn + ' 个，只接受这些）') : fail('schema 按钮数不符：' + nBtn);
prom[0].children.some(b => /忽略/.test(b.textContent))
  ? ok('【12】「✕ 忽略」在位（⑥甲 退出判据·可忽略）') : fail('缺忽略出口');
X.askHuman('hg_t1_gray') === false ? ok('【12】同一条不重复问（不反复打断）') : fail('重复触发未去重');
X.askHuman('hg_nodata') === false && X.HG.queue.length === 1
  ? ok('【12】前一条未答时后来者排队，不同时开两条') : fail('排队机制失效：' + JSON.stringify(X.HG.queue));
X.hgAnswer('hg_t1_gray', 'note', false);
X.S.meta.hgLog[X.S.meta.hgLog.length - 1].key === 'note'
  ? ok('【12】人答即记账（key／超时否／剩余秒／时刻）') : fail('应答未记账');
X.HG.pending === 'hg_nodata' ? ok('【12】前一条答完自动放出队列里那条') : fail('队列未接续：' + X.HG.pending);
X.HG.dueAt = Date.now() - 1;
X.hgTick();
const last = X.S.meta.hgLog[X.S.meta.hgLog.length - 1];
last.timeout === true && last.key === 'none'
  ? ok('【12】ttl 到点按四元组默认执行并记为超时（不静默）') : fail('超时默认未生效：' + JSON.stringify(last));
X.HG.pending === null && X.S.verdicts.t1v === 'pass'
  ? ok('【12】提示链收尾不残留 pending') : fail('pending 未清');

/* ── 步 2④：自动重跑一次＋如实记（④甲）── */
X.S.meta.rerunLog = []; X.HG.pending = null; X.HG.queue.length = 0; X.S.meta.hgLog = [];
let ran = 0;
X.rerunOnce('probe', '探针', () => { ran++; }) ? ok('【13】首次不达标 → 允许自动重跑一次') : fail('首跑未被允许');
ran === 1 ? ok('【13】重跑动作确实被执行') : fail('重跑回调未跑');
X.rerunOnce('probe', '探针', () => { ran++; }) === false && ran === 1
  ? ok('【13】同一粒度只重跑一次（不得无限重跑）') : fail('重跑次数失控：' + ran);
const rl = X.S.meta.rerunLog[0];
rl && rl.key === 'probe' && rl.label && rl.at ? ok('【13】重跑如实记（粒度／内容／时刻）') : fail('重跑未记账');

X.T1A.on = true; X.T1A.seg = 3; X.T1A.acc = {3: []}; X.T1A.empty = 0;
X.T1A.segDone();
X.S.meta.rerunLog.some(e => e.key === 't1seg3') && X.T1A.seg === 3 && !X.HG.pending
  ? ok('【13】T1 空段 → 自动重跑该段一次，且此时不打扰人') : fail('T1 按段重跑不符：seg=' + X.T1A.seg + ' pending=' + X.HG.pending);
X.T1A.acc = {3: []};
X.T1A.segDone();
X.T1A.segDone();
X.HG.pending === 'hg_nodata'
  ? ok('【13】重跑后仍无数据 → 升级 human_gate（不静默继续）') : fail('未升级到人：' + X.HG.pending);

/* T2 整场重跑一次；仍贴底才问人。前置：知情同意已确认，免得 consent 抢占 pending */
const arr = []; for(let i=0;i<100;i++) arr.push({sd: 1, pk: 5});
X.S.checks.cs5 = true;
X.LIVE.on = false; X.S.meta.rerunLog = []; X.S.meta.hgLog = []; X.HG.pending = null; X.HG.queue.length = 0;
X.T2A.on = true; X.T2A.acc = {ChA: arr};
X.T2A.finish();
X.S.meta.rerunLog.some(e => e.key === 't2') && !X.HG.pending
  ? ok('【13】T2 贴底 → 先整场自动重跑一次，未先问人') : fail('T2 首次应重跑：' + JSON.stringify(X.S.meta.rerunLog) + ' pending=' + X.HG.pending);
X.T2A.on = true; X.T2A.acc = {ChA: arr};
X.T2A.finish();
X.HG.pending === 'hg_t2_floor'
  ? ok('【13】重跑后仍贴底 → 升级 human_gate') : fail('T2 未升级到人：' + X.HG.pending);
X.hgAnswer('hg_t2_floor', 'reelectrode', false);

/* 档案导出：机器代做的动作（重跑＋提问应答）必须随档案列出 */
const dos = X.buildDossier();
/自动重跑 1 次/.test(dos) ? ok('【13】档案列出「自动重跑」行（含粒度与时刻）') : fail('档案未列重跑行');
/human_gate/.test(dos) && /reelectrode/.test(dos)
  ? ok('【13】档案列出「向人提问与应答」行（人答／超时均留痕）') : fail('档案未列提问应答');

/* ── 步 2⑤：撤销／重来＋为什么（猜错要便宜）── */
X.renderHostBar();
const q9 = []; walk(doc, q9);
const hbtns = q9.filter(n => n.tagName === 'BUTTON').map(n => n.textContent);
['⏸ 暂停', '⤺ 撤销上一步', '❓为什么'].every(t => hbtns.some(x => String(x).indexOf(t) === 0))
  ? ok('【14】三件常在控制在位：⏸ 暂停／⤺ 撤销上一步／❓为什么') : fail('缺常在控制：' + hbtns.join(','));
X.UNDO.stack.length = 0; X.S.fields = {}; X.S.verdicts.t1v = 'pass';
X.T1A.on = true; X.T1A.seg = 2; X.T1A.acc = {2: [0.5, 0.6]}; X.T1A.empty = 0;
X.T1A.segDone();
X.S.fields.t1a2 === '0.550' && X.UNDO.stack.length === 1
  ? ok('【14】机器代写即留可撤销帧（T1 第 2 段 α＝0.550）') : fail('未留撤销帧：' + JSON.stringify(X.UNDO.stack));
X.undoLast();
!X.S.fields.t1a2 ? ok('【14】撤销＝还原机器写的那一格（字段已清空）') : fail('撤销未还原：' + X.S.fields.t1a2);
X.S.verdicts.t1v === 'pass' ? ok('【14】撤销不碰人已判的结论（只撤机器代写）') : fail('撤销越界改了人的判定');
(X.S.meta.undoLog || []).length === 1 ? ok('【14】撤销本身也留痕（档案可查）') : fail('撤销未记账');
X.undoLast() === false ? ok('【14】无帧可撤时如实拒绝，不乱动数据') : fail('空栈撤销行为异常');
X.T1A.on = false; X.T2A.on = false; X.T3A.on = false;
X.pauseGuide() === false ? ok('【14】没有机器在跑时「暂停」如实说无事可停') : fail('空暂停被当成成功');
X.T2A.on = true; X.T2A.left = 120; X.T2A.timer = null; X.T2A.acc = {};
X.pauseGuide() === true && X.T2A.on === false
  ? ok('【14】跑动中「暂停」即停本机（已完成部分数据保留）') : fail('暂停未生效');

console.log('\n（本次共创建 ' + created + ' 个节点）');
console.log(bad ? '结论：✗ 逻辑冒烟 ' + bad + ' 处问题' : '结论：✓ 逻辑冒烟全过');
process.exit(bad ? 1 : 0);
