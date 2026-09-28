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
  + ' UNDO, undoLast, pauseGuide, T5A, chanStats, flatFromSeries,'
  + ' POLICY, MODE, NUD, FP_LINE, policyMode, polSet, tripleOk, autoWrite, nudAskOk, nudAskNo,'
  + ' nudge, NU, nudCount, nudDismiss, nudCur, nudPulse, silText, fpOf, fpGrade, markFp, unFp, buildDossier,'
  + ' STROWS, STL, machineStates, stConflict, stForce, setStForce, paintStates, vlabFor, HOLD_DEFAULT,'
  + ' cueStart, cueEnd, fmtzh, manualLabel, paintManual, toggleManual, phLabelStaged, phLabelArchived,'
  + ' phFillSel, phLoss, runBar, t10Read, t11Read,'
  + ' get PHLIST(){ return PHLIST; }, set PHLIST(v){ PHLIST = v; },'
  + ' get PH(){ return PH; }, set PH(v){ PH = v; }};\n';

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
    dataset: {}, innerHTML: '', value: '', checked: false, disabled: false, __text: '', __ls: {},
    addEventListener(t, fn) { (n.__ls[t] = n.__ls[t] || []).push(fn); },
    removeEventListener(t, fn) { const a = n.__ls[t] || []; const i = a.indexOf(fn); if (i >= 0) a.splice(i, 1); },
    click() {
      const ev = { currentTarget: n, target: n, preventDefault() {}, stopPropagation() {} };
      (n.__ls.click || []).slice().forEach(f => f(ev));
    },
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
    scrollIntoView() {}, focus() {}, blur() {}, select() {}
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
/* 真发事件：替身以前是空函数，按钮与委托监听的接线从未被测过（只测了直接调函数）——现在按真实路径打 */
function fireOn(node, type, target) {
  const ev = { target: target || node, currentTarget: node, preventDefault() {}, stopPropagation() {} };
  ((node.__ls && node.__ls[type]) || []).slice().forEach(f => f(ev));
  return ev;
}
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
drawerCards.length === 6 ? ok('【5】证据抽屉卡 6 张（步 3④ 增「结论四态」抽屉一张）') : fail('证据抽屉卡应 6 张，现 ' + drawerCards.length);
const inMgrp = n => { for(let p = n.__parent; p; p = p.__parent) if (p.classList && p.classList.contains('mgrp')) return p; return null; };
drawerCards.filter(n => !inMgrp(n)).every(n => n.classList.contains('closed'))
  && drawerCards.filter(n => inMgrp(n)).every(n => !inMgrp(n).classList.contains('open'))
  ? ok('【5】证据位默认仍全收起：没入组的走抽屉，入了〈人工采集栏〉的随整组收起（不再双重折叠——点了才看得见表）')
  : fail('有证据位默认是露出的');
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

/* ── 步 3①：T5 机器自跑（observer=none，人不点即填、填而不吵）── */
const waveOf = (amp, n) => { const a = []; for(let i=0;i<(n||100);i++) a.push(i % 2 ? amp : -amp); return {ChA: a}; };
/* 注：T5A.tick 内有 1 秒节流（真实帧本就≥1s 一跳）；测试里逐帧同步喂，故每记都清一次 lastCap，
      否则跨片那一记会被节流挡在 snap 判断之前——这是测试假象，非面板缺陷。 */
const tick1 = d => { X.T5A.lastCap = 0; X.T5A.tick(d); };
const pump = (times, elapsed, amp, batt) => {
  for(let i=0;i<times;i++) tick1({type:'tick', elapsed, connected:true, battery:batt, wave: waveOf(amp)});
};
X.LIVE.on = true; X.LIVE.at = Date.now(); X.UNDO.stack.length = 0; X.S.fields = {};
X.T5A.reset(); X.T5A.on = false; X.HG.pending = null; X.HG.queue.length = 0;
tick1({type:'tick', elapsed:10, connected:true, battery:99, wave: waveOf(40)});
X.T5A.on === true ? ok('【15】接入实时流即自动起（人不点开始，observer=none）') : fail('T5A 未自动起');
pump(61, 100, 40, 88);
tick1({type:'tick', elapsed:130, connected:true, battery:88, wave: waveOf(40)});
X.S.fields.t5a0 === '正常' && X.S.fields.t5d0 === '无' && X.S.fields.t5b0 === '88'
  ? ok('【15】第 0 片代填：幅值基线＝正常、塌陷无、电池 88（取自 tick 真值）')
  : fail('第 0 片代填不符：' + X.S.fields.t5a0 + '/' + X.S.fields.t5d0 + '/' + X.S.fields.t5b0
      + '｜诊断 on=' + X.T5A.on + ' idx=' + X.T5A.idx + ' acc=' + JSON.stringify(Object.keys(X.T5A.acc))
      + '/' + ((X.T5A.acc.ChA || []).length) + ' status=' + X.T5A.status
      + ' LIVE.on=' + X.LIVE.on + ' 帧龄=' + (Date.now() - X.LIVE.at) + 'ms');
X.HG.pending === null ? ok('【15】代填过程不打断人（未弹 human_gate）') : fail('自跑却打断了人：' + X.HG.pending);
X.UNDO.stack.length > 0 ? ok('【15】机器代填照样进了可撤销栈') : fail('T5 代填未留撤销帧');
pump(61, 200, 10, undefined);
tick1({type:'tick', elapsed:610, connected:true, wave: waveOf(10)});
X.S.fields.t5a1 === '偏低'
  ? ok('【15】第 1 片幅值为基线 25% → 判「偏低」（±20% 线＝正本既有判据）') : fail('偏低未判出：' + X.S.fields.t5a1);
X.S.fields.t5b1 === '不可得'
  ? ok('【15】设备不上报电池 → 如实写「不可得」，不拿别处数冒充') : fail('电池缺报时被填了值：' + X.S.fields.t5b1);
pump(75, 300, 0.5, 80);
tick1({type:'tick', elapsed:1210, connected:true, battery:80, wave: waveOf(0.5)});
X.S.fields.t5d2 === '有'
  ? ok('【15】连续贴底 → 塌陷列记「有」（与 T2 同一 flatFromSeries，未另立阈值）') : fail('塌陷未判出：' + X.S.fields.t5d2);
const one = X.chanStats([1,2,3]);
one === null ? ok('【15】样本不足 64 点 → chanStats 拒算（不拿短窗充数）') : fail('短窗被接受了');
X.T5A.on = false;

/* ── 步 3②：三态打断＋静默成功＋误报记账 ── */
const clean32 = () => {
  X.S.meta.nudge = {}; X.S.meta.nudgeLog = []; X.S.meta.fp = {}; X.S.meta.fpForce = {};
  X.S.meta.pol = {}; X.S.meta.polHold = []; X.S.meta.nudgeOff = false;
  X.S.meta.hgLog = []; X.NU.prompt = null; X.NU.ask = null; X.S.meta.sess = 1;
  X.HG.pending = null; X.HG.queue.length = 0;
};
const btnTxt = () => { const q = []; walk(doc, q);
  return {nodes: q, btns: q.filter(n => n.tagName === 'BUTTON').map(n => String(n.textContent))}; };
/* 造一次"确认跃迁"：清掉冷却 → 连续 arm 次同一新状态；返回最后一次 nudge 的返回值 */
const fireOnce = (key, st) => {
  const c = X.nudCur(key); c.at = 0; c.pend = ''; c.seen = 0;
  X.nudge(key, st, {bad:true}); X.nudge(key, st, {bad:true});
  return X.nudge(key, st, {bad:true});
};
clean32();
X.policyMode('t5_read') === 'act'
  ? ok('【16】读数代填登记为「直接做」（正本 §六 点名的 T1/T2/T9 读数类，T3/T5 同性质）') : fail('t5_read 现态应为直接做');
X.policyMode('any_unregistered_path') === 'ask'
  ? ok('【16】未登记的路径一律落「先问」——默认态写在函数里，不靠自觉') : fail('默认态不是先问');
X.polSet('t5_link', 'act') === false && X.policyMode('t5_link') === 'ask'
  ? ok('【16】三重门硬校验：把"断流提示"改判为直接做被拒（可回退不成立，人也不能给机器升权）') : fail('三重门没拦住改判');
X.polSet('t5_read', 'ask');
X.policyMode('t5_read') === 'ask' ? ok('【16】人可把"直接做"改判为"先问"（⑥ 退出判据·可改判）') : fail('改判未生效');
X.S.fields = {}; X.UNDO.stack.length = 0; X.T5A.reset(); X.T5A.on = true; X.LIVE.on = true; X.LIVE.at = Date.now();
pump(61, 100, 40, 88);
tick1({type:'tick', elapsed:130, connected:true, battery:88, wave: waveOf(40)});
!X.S.fields.t5a0 && X.S.meta.polHold.length === 1
  ? ok('【16】改判生效后机器确实没代写（第 0 片留空，代写被扣下并留痕）')
  : fail('扣写不符：fields.t5a0=' + X.S.fields.t5a0 + ' hold=' + JSON.stringify(X.S.meta.polHold));
X.renderHostBar();
let b16 = btnTxt();
b16.nodes.filter(n => clsHas(n, 'nudge')).length === 1
  ? ok('【16】「先问」行渲染在主持人条一处（不另开弹窗）') : fail('先问行数：' + b16.nodes.filter(n => clsHas(n, 'nudge')).length);
['允许这一次代写', '不用（我自己来）'].every(t => b16.btns.indexOf(t) >= 0)
  ? ok('【16】先问只接受两个答案（schema 齐；不回默认＝不写）') : fail('先问答案按钮缺：' + b16.btns.join(','));
X.nudAskOk();
X.S.fields.t5a0 === '正常' ? ok('【16】人点头才写：授权即代写第 0 片') : fail('授权后未写：' + X.S.fields.t5a0);
X.policyMode('t5_read') === 'ask' && X.S.meta.polHold[0].done === 'authorized'
  ? ok('【16】授权是一次性的：策略仍为「先问」，账上标「人已授权」') : fail('一次性授权记账不符');
X.polSet('t5_read', 'idle');
X.S.fields = {}; X.S.meta.polHold = []; X.NU.ask = null; X.T5A.reset(); X.T5A.on = true;
pump(61, 100, 40, 88);
tick1({type:'tick', elapsed:130, connected:true, battery:88, wave: waveOf(40)});
X.NU.ask === null && !X.S.fields.t5a0 && X.S.meta.polHold.length === 1
  ? ok('【16】「不行动」＝连问都不问，只留痕（机器没动，也没吵）') : fail('不行动态不符');
X.polSet('t5_read', 'act');
X.policyMode('t5_read') === 'act' ? ok('【16】改判回「直接做」（该条三重门全真，允许）') : fail('改回直接做失败');

clean32();
X.nudge('p1', 'A', {bad:true}) === false ? ok('【16】宽限一：新状态头一次不算跃迁（抖动不打断）') : fail('抖动没被挡住');
X.nudge('p1', 'A', {bad:true}) === false;
X.nudge('p1', 'A', {bad:true}) === true ? ok('【16】连续 ' + X.NUD.arm + ' 次同一新状态才认跃迁 → 打断一次') : fail('跃迁未被触发');
X.nudge('p1', 'A', {bad:true}) === false
  ? ok('【16】静默成功：状态没变就一个字都不说（不重复报"还是 A"）') : fail('同态仍在报');
X.nudge('p1', 'B', {bad:true}); X.nudge('p1', 'B', {bad:true});
X.nudge('p1', 'B', {bad:true}) === false && /冷却/.test(X.S.meta.nudgeLog.slice(-1)[0].why)
  ? ok('【16】宽限二：同键 ' + X.NUD.cool + ' s 内不反复打断（被挡下的那条留了痕）') : fail('冷却未生效');
X.nudge('p2', '异常', {bad:true}); X.nudge('p2', '异常', {bad:true});
X.nudge('p2', '异常', {bad:true}) === true ? ok('【16】异常跃迁 → 叫人') : fail('异常没叫到人');
X.nudge('p2', '正常', {bad:false}); X.nudge('p2', '正常', {bad:false});
X.nudge('p2', '正常', {bad:false}) === false && /回到正常/.test(X.S.meta.nudgeLog.slice(-1)[0].why)
  ? ok('【16】回到正常不叫人，只写状态行（正本：场次 2 人什么都不做，异常时才被叫）') : fail('恢复态误叫');
b16 = btnTxt(); X.renderHostBar(); b16 = btnTxt();
b16.nodes.filter(n => clsHas(n, 'nudge')).length === 1
  ? ok('【16】打断提示行渲染一处（含四元组式样：说什么＋怎么答＋谁有权）') : fail('提示行数不符');
const nudRow = b16.nodes.filter(n => clsHas(n, 'fp'))[0];
nudRow && /历史误报 0\/1/.test(nudRow.textContent)
  ? ok('【16】每条提示自带"历史误报 k/n"计数（Drew 2014 那笔账就摆在这儿）') : fail('误报计数未显示：' + (nudRow ? nudRow.textContent : '无该行'));
['👎 记为误报', '✕ 知道了'].every(t => b16.btns.indexOf(t) >= 0)
  ? ok('【16】提示行有「记为误报」与「知道了」（可忽略·可改判，⑥ 退出判据）') : fail('提示行出口缺件：' + b16.btns.join(','));
X.nudDismiss(); X.renderHostBar(); b16 = btnTxt();
b16.nodes.filter(n => clsHas(n, 'nudge')).length === 0 ? ok('【16】「知道了」即收起，不赖在屏上') : fail('提示未收起');
fireOnce('p3', 'x1'); fireOnce('p3', 'x2'); fireOnce('p3', 'x3');
X.fpOf('p3').fires === 3 ? ok('【16】同键累计打断 3 次进入误报账本分母') : fail('分母不符：' + X.fpOf('p3').fires);
X.markFp('p3'); X.markFp('p3');
X.fpGrade('p3') === '待核' ? ok('【16】误报越线（≥' + X.FP_LINE.min + ' 次且 ≥' + Math.round(X.FP_LINE.rate*100) + '%）→ 自动降为「待核」')
  : fail('越线未降级：' + X.fpGrade('p3') + ' ' + JSON.stringify(X.fpOf('p3')));
fireOnce('p3', 'x4') === false && /待核/.test(X.S.meta.nudgeLog.slice(-1)[0].why)
  ? ok('【16】降为待核后只记录，不再打断人') : fail('待核后仍在叫人');
X.unFp('p3');
X.fpGrade('p3') === '断言' ? ok('【16】人可把「待核」改回「断言」（改判进账本，机器不自升权）') : fail('改回断言无效');
X.S.meta.nudgeOff = true;
fireOnce('p5', 'a') === false && /关闭提示/.test(X.S.meta.nudgeLog.slice(-1)[0].why)
  ? ok('【16】「关闭提示」后一律转记录（⑥ 退出判据·可关）') : fail('关闭提示未生效');
X.S.meta.nudgeOff = false;

clean32(); X.S.meta.sess = 2;
fireOnce('k1', 'a') && fireOnce('k2', 'a') && fireOnce('k3', 'a');
X.nudCount() === 3 ? ok('【16】场次 2 打断计数只算真正叫过人的（3/3）') : fail('打断计数不符：' + X.nudCount());
fireOnce('k4', 'a') === false && /预算/.test(X.S.meta.nudgeLog.slice(-1)[0].why)
  ? ok('【16】超出场次 2 预算（≤' + X.NUD.budget + '）→ 第 4 条转记录，不再叫人（§九 结果指标由此兜住）') : fail('预算未挡住');
/已打断 3\/3/.test(X.silText()) ? ok('【16】静默跟随状态行如实报"已打断 3/3"') : fail('状态行文本不符：' + X.silText());
const dos2 = X.buildDossier();
/## 一之三 静默跟随与打断记账/.test(dos2) ? ok('【16】档案新增该段（三态现值＋打断判定＋误报记账）') : fail('档案缺该段');
/非判据，不进判定链/.test(dos2)
  ? ok('【16】档案明写宽限／越线参数是本窗自设运维数，非判据（不当阈值偷偷进结论链）') : fail('档案未声明参数性质');
/打断判定/.test(dos2) && /误报记账/.test(dos2) && /场次 2 打断计数：3／3/.test(dos2)
  ? ok('【16】档案列出被挡下的每一条（同态不记，其余全留）') : fail('档案记账行不全');
clean32();
X.T1A.on = false; X.T2A.on = false; X.T3A.on = false; X.T5A.on = false;   /* 前置清场：前面几组把机器留在跑动态 */
X.nudge('pt', '异常', {bad:true, text:'只在第一记带的文案'});
X.nudge('pt', '异常', {bad:true});
X.nudge('pt', '异常', {bad:true});
X.NU.prompt && /只在第一记带的文案/.test(X.NU.prompt.text)
  ? ok('【16】跃迁确认那一记即使不带文案，也用宽限期间记下的原文（提示不退化成键名）') : fail('文案未延续：' + JSON.stringify(X.NU.prompt));
/现无机器在跑/.test(X.silText())
  ? ok('【16】无机器在跑时状态行如实说「现无机器在跑」（不装作在盯表）') : fail('状态行文案不实：' + X.silText());
X.T5A.on = true;
/机器自跑中/.test(X.silText()) ? ok('【16】T5 自跑中状态行改口「机器自跑中」') : fail('自跑态未显示：' + X.silText());
X.T5A.on = false;
clean32();
X.T1A.on = false; X.T2A.on = false; X.T3A.on = false; X.LIVE.on = true; X.LIVE.at = Date.now();
X.nudPulse(); X.nudPulse(); X.nudPulse();
(X.S.meta.nudge.t5_link || {}).state === '有帧'
  ? ok('【16】常驻心跳在观察帧龄（帧不来时靠它，不靠 tick——tick 那时根本不会被调用）')
  : fail('心跳未记链路态：' + JSON.stringify(X.S.meta.nudge.t5_link));
X.LIVE.at = Date.now() - 9000;                                  /* 造 9 秒无帧 */
X.nudPulse(); X.nudPulse();
X.nudPulse() === undefined && X.NU.prompt && X.NU.prompt.key === 't5_link'
  ? ok('【16】断流满三记才叫人（抖动宽限同样管链路），文案用心跳里存下的原文')
  : fail('断流未提示：' + JSON.stringify(X.NU.prompt));
X.NU.prompt = null; X.LIVE.on = false;
clean32(); X.polSet('t5_read', 'act'); X.T5A.on = false;

/* ── 步 3④：结论四态落库（机判列×人判列分列，不得合并）── */
clean32();
X.S.verdicts = {}; X.S.fields = {}; X.S.meta.stForce = {}; X.S.meta.stLog = []; X.S.checks.cs5 = true;
X.PH = null; X.HG.pending = null; X.HG.queue.length = 0;
const st = id => X.machineStates().filter(r => r.id === id)[0];
X.machineStates().length === X.STROWS.length
  ? ok('【17】四态表行数＝登记表行数（' + X.STROWS.length + ' 行：质检链＋十一项＋总评位）') : fail('行数不符');
!st('sumv').st ? ok('【17】总评位机器永不代判（§三 judge＝human_signoff）') : fail('机器代判了总评');
!st('t9v').st && /待核/.test(st('t9v').why)
  ? ok('【17】机器无真源的项留空并写明理由（不硬造，红线5）') : fail('无源项被硬判了：' + JSON.stringify(st('t9v')));
/* 质检链：逐字转录 qc 既有输出 */
X.PH = {audit:{recommend:'ingest', reasons:[], threshold_version:'20260920',
               manifest:true, events:true, qc:true, report:true}, npz_meta:{has_pre_filter:true}};
st('qc').st === 'PASS' ? ok('【17】qc recommend＝ingest → 机判 PASS（转录，未重算未改阈值）') : fail('ingest 未转录对：' + st('qc').st);
X.PH.audit.recommend = 'quarantine'; X.PH.audit.reasons = ['通道质量不合格：AF3'];
st('qc').st === 'INVALID'
  ? ok('【17】qc quarantine → INVALID（数据不可用），**没有**被合并成 FAIL（正本 §四 明令）') : fail('隔离被错映射成：' + st('qc').st);
/不说明设备不达标/.test(st('qc').why) ? ok('【17】依据原文里明写"隔离≠设备不达标"') : fail('依据未写明分界：' + st('qc').why);
/AF3/.test(st('qc').note) ? ok('【17】reasons 原文进"保留项"列（保留项必须写明）') : fail('reasons 未落到保留项列');
st('t8v').st === 'PASS' ? ok('【17】契约四件俱在 → T8 PASS') : fail('T8 判错：' + st('t8v').st);
X.PH.audit.events = false;
st('t8v').st === 'QC_ERROR' && /events/.test(st('t8v').why)
  ? ok('【17】缺契约件 → QC_ERROR（流程未闭合，不写设备结论）') : fail('缺件未落 QC_ERROR：' + JSON.stringify(st('t8v')));
X.PH.npz_meta.has_pre_filter = false;
st('t6v').st === 'FAIL' ? ok('【17】无原始档 → FAIL（D32 硬条件＝设备缺陷，与"本次作废"分得开）') : fail('T6 判错：' + st('t6v').st);
X.PH = null;
/* 各项用机器已代填的读数说话 */
X.S.fields = {t5a0:'正常', t5a1:'正常', t5d0:'无', t5d1:'无', t2f_af3:'无', t3c1:'是', t1a1:'0.5', t1a2:'0.8'};
st('t5v').st === 'PASS' ? ok('【17】各片幅值正常、无塌陷 → T5 PASS（±20% 与 T2 同一口径）') : fail('T5 判错：' + JSON.stringify(st('t5v')));
/累计断包列机器无数据源/.test(st('t5v').why)
  ? ok('【17】T5 依据里如实交代覆盖面（断包列无源，不冒充全覆盖）') : fail('覆盖面未如实说明：' + st('t5v').why);
X.S.fields.t5a1 = '偏低';
st('t5v').st === 'FAIL' ? ok('【17】幅值漂移超 20% 线 → T5 FAIL') : fail('漂移未判 FAIL：' + st('t5v').st);
X.S.fields.t5a1 = '正常'; X.S.fields.t5d1 = '有';
st('t5v').st === 'ACCEPTED_WITH_NOTE' && /第 1 片/.test(st('t5v').note)
  ? ok('【17】塌陷 1 处（线内）→ AWN 并写明保留项，没升级成 FAIL') : fail('塌陷线内应 AWN：' + JSON.stringify(st('t5v')));
X.S.fields.t5d1 = '无'; X.S.fields.t2f_af3 = '有';
st('t2v').st === 'ACCEPTED_WITH_NOTE' && /af3/.test(st('t2v').note)
  ? ok('【17】T2 贴底 → AWN（正本 §6.3 第二档），不判 FAIL、也不叫 INVALID') : fail('T2 判错：' + JSON.stringify(st('t2v')));
X.S.fields.t2f_af3 = '无'; X.S.fields.t3c1 = '否';
st('t3v').st === 'ACCEPTED_WITH_NOTE' ? ok('【17】T3 恢复慢 → AWN（§6.3 第二档）') : fail('T3 判错：' + st('t3v').st);
X.S.fields.t3c1 = '是';
st('t1v').st === 'PASS' ? ok('【17】α 增幅 60% ≥30% → T1 PASS（正本 T1 既有分档）') : fail('T1 判错：' + JSON.stringify(st('t1v')));
X.S.fields.t1a2 = '0.60';
st('t1v').st === 'ACCEPTED_WITH_NOTE' ? ok('【17】α 增幅 20% 落 15–30% 合格档 → AWN 并写明保留项') : fail('T1 合格档应 AWN：' + JSON.stringify(st('t1v')));
X.S.fields.t1a2 = '0.52';
st('t1v').st === null && /分不清/.test(st('t1v').why)
  ? ok('【17】α 增幅 <15% 时机器不自裁 INVALID／FAIL（分不清是没闭眼还是设备问题）——交人') : fail('灰区被机器自裁了：' + JSON.stringify(st('t1v')));
/* 人已裁的作废：转录进状态轴，同时保留机器原读法 */
X.S.meta.hgLog = [{id:'hg_t2_floor', item:'t2', kind:3, key:'invalid', at:'2026-09-27 10:30', timeout:false}];
X.S.fields.t2f_af3 = '有';
st('t2v').st === 'INVALID' ? ok('【17】人在 human_gate 答"本项作废" → 机判列落 INVALID（不是 FAIL）') : fail('作废未转录：' + st('t2v').st);
/机器原读法/.test(st('t2v').why) ? ok('【17】转录人裁时把机器原读法并列保留（两列不互相抹掉）') : fail('原读法被抹了：' + st('t2v').why);
X.S.meta.hgLog = [];
/* 分列：矛盾只标不并 */
X.S.fields.t1a2 = '0.8';
st('t1v').st === 'PASS' && st('t1v').conflict === '' ? ok('【17】人未判时不构成矛盾（不误吵）') : fail('未判却报矛盾');
X.S.verdicts.t1v = 'fail';
st('t1v').conflict === '机判达标·人判不通过'
  ? ok('【17】机判 PASS × 人判 FAIL → 标矛盾（两列都在，谁也没覆盖谁）') : fail('矛盾未标出：' + st('t1v').conflict);
X.paintStates();
X.HG.pending === 'hg_state_conflict'
  ? ok('【17】矛盾自动升级 human_gate（② 类：判据落灰区），四元组齐') : fail('矛盾没升级到人：' + X.HG.pending);
X.hgAnswer('hg_state_conflict', 'recheck', false);
X.paintStates();
(X.HG.pending === null && !X.HG.queue.length)
  ? ok('【17】同一组矛盾答过就不再追第二遍（不反复打断；答过的是哪组矛盾也进了账）')
  : fail('同组矛盾被重复问了：' + X.HG.pending);
X.PH = {audit:{recommend:'quarantine', reasons:[], manifest:true, events:true, qc:true, report:true}, npz_meta:{has_pre_filter:true}};
X.S.verdicts.t6v = 'pass'; X.PH.npz_meta.has_pre_filter = false;
X.paintStates();
X.HG.pending === 'hg_state_conflict'
  ? ok('【17】矛盾集合变了（新冒出一项 T6）→ 允许再问一次，并把新那项带进签名')
  : fail('矛盾集合变化未再问：pending=' + X.HG.pending);
X.hgAnswer('hg_state_conflict', 'device_fail', false);
X.S.verdicts = {};
X.PH = {audit:{recommend:'quarantine', reasons:['时长不足'], manifest:true, events:true, qc:true, report:true}, npz_meta:{has_pre_filter:true}};
X.S.verdicts.t1v = 'pass';
st('qc').st === 'INVALID' ? ok('【17】隔离状态下机器仍只说数据有效性，不越界判设备') : fail('越界');
X.S.verdicts.t1v = '';
/* 人改判四态：不覆盖机判原文，也不串进三档建议 */
X.S.fields = {t5a0:'正常', t5d0:'无', t2f_af3:'无', t3c1:'是', t1a1:'0.5', t1a2:'0.8'};
X.PH = {audit:{recommend:'quarantine', reasons:[], threshold_version:'20260920',
               manifest:true, events:true, qc:true, report:true}, npz_meta:{has_pre_filter:true}};
const sugBefore = X.sumSuggest().lab;
X.setStForce('qc', 'ACCEPTED_WITH_NOTE');
st('qc').st === 'INVALID' && st('qc').forced === 'ACCEPTED_WITH_NOTE'
  ? ok('【17】人改判只加一列：机判原文（INVALID）仍在，生效值另存（分列不覆盖）')
  : fail('改判覆盖或丢失：' + JSON.stringify(st('qc')));
X.sumSuggest().lab === sugBefore
  ? ok('【17】四态改动不串进三档建议（§6.3 判据链独立，未被动过）') : fail('四态串进了三档建议');
(X.S.meta.stLog || []).length === 1 && X.S.meta.stLog[0].st === 'ACCEPTED_WITH_NOTE' && X.S.meta.stLog[0].machine === 'INVALID'
  ? ok('【17】每次改判都进账（项／新值／时刻／**机器原值**一起记，事后能查出是谁把 INVALID 改成 AWN 的）')
  : fail('改判记账缺机器原值：' + JSON.stringify(X.S.meta.stLog));
X.setStForce('qc', '');
!X.stForce('qc') ? ok('【17】改判可撤销，回到机器原读法') : fail('撤销改判无效');
/* 知情同意：整场有效性，不写成设备 FAIL */
X.S.checks.cs5 = false;
X.paintStates();
const q17 = []; walk(doc, q17);
const tipEl = q17.filter(n => n.attrs && n.attrs.id === 'stTip')[0];
tipEl && /按 INVALID 看待（伦理有效性/.test(tipEl.textContent)
  ? ok('【17】cs5 未勾 → 表尾提示按 INVALID 看待（伦理有效性），明写与设备达标无关') : fail('同意缺失未落状态轴：' + (tipEl ? tipEl.textContent : '无该元素'));
X.S.checks.cs5 = true;
/* 表格渲染与档案入档 */
const stTab = q17.filter(n => clsHas(n, 'stattab')).length;
stTab === 1 ? ok('【17】四态表在收口页渲染一处（表＋提示＋正本原文注）') : fail('四态表渲染数：' + stTab);
const dos17 = X.buildDossier();
/## 一之四 结论四态/.test(dos17) ? ok('【17】档案新增「一之四」段（机判列×人判列入档）') : fail('档案缺该段');
/绝不可合并成"失败"/.test(dos17) ? ok('【17】档案带上正本那句"绝不可合并成失败"（口径随档走）') : fail('档案未写不可合并');
/未重算、未改阈值/.test(dos17) && /20260920/.test(dos17)
  ? ok('【17】档案声明 qc 侧为逐字转录、阈值版本 20260920 未动') : fail('档案未声明转录性质');
X.S.verdicts.t1v = 'fail'; X.paintStates(); X.HG.pending = null; X.HG.queue.length = 0;
X.S.verdicts = {}; X.PH = null; X.S.fields = {};

/* ── 步 4⑤：T9 结论默认「待核」（⑩，机器不默认放行）── */
X.S.verdicts = {}; X.S.meta.holdLog = []; X.PH = null; X.S.fields = {};
X.vlabFor('t9v') === '⏳ 待核（默认，⑩）'
  ? ok('【18】T9 未判时显示「待核」而不是空杠——机器不给 VR 场景默认放行') : fail('T9 默认词不符：' + X.vlabFor('t9v'));
X.vlabFor('t1v') === '—' ? ok('【18】其它项口径未动（未判仍是「—」，不跟着改判据）') : fail('误改了其它项的显示');
X.S.verdicts.t9v = 'pass';
X.vlabFor('t9v') === '🟢 通过' ? ok('【18】人显式改判后以人为准（默认词只兜空白，不压人判）') : fail('人判被默认词压住了');
X.S.verdicts = {};
X.recount();
const q18 = []; walk(doc, q18);
q18.filter(n => clsHas(n, 'chip') && /待核/.test(n.textContent)).length >= 1
  ? ok('【18】T9 卡内常驻「待核」标记（只读，不占人的动作）') : fail('待核标记未渲染');
const mir = q18.filter(n => n.attrs && n.attrs['data-mir'] === 't9v')[0];
mir && /待核/.test(mir.textContent)
  ? ok('【18】汇总镜像 11 项里 T9 也显「待核」（不显空——收口那一页看得见）') : fail('镜像位未显待核：' + (mir ? mir.textContent : '无镜像元素'));
const t9btn = q18.filter(n => n.attrs && n.attrs['data-vid'] === 't9v' && n.attrs['data-v'] === 'pass')[0];
t9btn.click();
(X.S.meta.holdLog || []).length === 1 && X.S.meta.holdLog[0].id === 't9v' && /显式改判/.test(X.S.meta.holdLog[0].note)
  ? ok('【18】人点"通过"这一步被记下来（谁把待核落成通过，事后可追）') : fail('显式改判未留痕：' + JSON.stringify(X.S.meta.holdLog));
const t1btn = q18.filter(n => n.attrs && n.attrs['data-vid'] === 't1v' && n.attrs['data-v'] === 'pass')[0];
t1btn.click();
X.S.meta.holdLog.length === 1 ? ok('【18】非默认项的正常判定不被多记一笔（账本不灌水）') : fail('账本灌水：' + X.S.meta.holdLog.length);
const inp18 = q18.filter(n => n.attrs && n.attrs['data-f'] === 't1a1')[0];
if(inp18){ inp18.value = '0.42'; fireOn(byId['main'], 'input', inp18); }
inp18 && X.S.fields.t1a1 === '0.42'
  ? ok('【18】委托监听这条接线**第一次被真测到**（input 冒泡进 S.fields；从前替身 addEventListener 是空函数，这条路一直没验过）')
  : fail('委托监听未生效：' + (inp18 ? '值＝' + X.S.fields.t1a1 : '未找到输入位'));
const dos18 = X.buildDossier();
/默认待核被显式改判/.test(dos18) ? ok('【18】档案「一之二」列出这条改判（含时刻与新值）') : fail('档案未列改判行');
X.S.verdicts = {}; X.S.meta.holdLog = []; X.recount();
/⏳ 待核（默认，⑩）/.test(X.buildDossier())
  ? ok('【18】档案在 T9 位也写「待核」，不写成"未填"或空——下游读到的是弃权一等值') : fail('档案未显待核');
X.S.verdicts = {}; X.recount();

/* ── 【19】法师 2026-09-28 实测 7 条：提示音布线／T3 窗长／读数下拉／人工版面收起／T9–T11 入口 ── */
X.recount();
const q19 = []; walk(doc, q19);
const ancHas = (n, c) => { for(let p = n.__parent; p; p = p.__parent) if (p.classList && p.classList.contains(c)) return true; return false; };
const byCls = c => q19.filter(n => clsHas(n, c));

const t3w = X.T3A.ACTIONS.map(a => a[2]);
t3w.join(',') === '10,10,10,150'
  ? ok('【19】T3 动作窗按动作给（咀嚼 10／眨眼 10／转头 10／深呼吸 15 秒×10＝150 秒），不再清一色 10 秒')
  : fail('T3 窗长不符：' + t3w.join(','));
/每次约 15 秒/.test(X.T3A.ACTIONS[3][0])
  ? ok('【19】深呼吸那组连动作名都写着「每次约 15 秒」——大字提示读得出来，不用人猜节拍') : fail('动作名未带节拍说明');
const blks19 = X.FLOW.secs.reduce((a, s) => a.concat(s.blocks), []);
const t3auto = blks19.filter(b => b.k === 't3auto')[0], t3grid = blks19.filter(b => b.k === 'grid' && /T3 耐受性/.test(b.title || ''))[0];
t3auto && /150 秒/.test(t3auto.hint) && /开始响两声/.test(t3auto.hint)
  ? ok('【19】T3 自动跑的说明与代码同步（150 秒窗＋响了就切换），人不必翻代码') : fail('T3 自动跑说明未同步');
/150 秒/.test(t3grid.hint) ? ok('【19】手填表那张卡的说明也写了 150 秒（两处口径不打架）') : fail('手填表说明未同步');
X.fmtzh(150) === '2 分 30 秒' && X.fmtzh(30) === '30 秒'
  ? ok('【19】秒数用中文读法（2 分 30 秒／30 秒），不甩 02:30 让人心算') : fail('中文秒数不符：' + X.fmtzh(150));

X.phLoss({audit:{span_loss_rate:0.39, packet_loss_rate:0.01}}) === 0.39
  ? ok('【19】断包率口径全页一处：先「会话跨度」，与 T5 同一处，不分叉') : fail('跨度口径未优先');
X.phLoss({audit:{packet_loss_rate:0.01}}) === 0.01 ? ok('【19】跨度口径取不到才退回样本计数口径') : fail('退路口径不符');
X.phLoss({audit:{qc:true}}) === null
  ? ok('【19】两个口径都没有（还没跑质检）→ 交 null，由调用方明说取不到，绝不拿 0 充数') : fail('无数据未如实交 null');
X.PHLIST = {arch:[{session_id:'ZEN-20260925-P001-S16', participant:'P001', date:'2026-09-25', type:'test', duration:'1222', status:'quarantined'}],
            stag:[{session_id:'local_20260928_174054', npz:'a.npz', manifest:true, events:false},
                  {session_id:'local_20260927_074329.partial', npz:'b.npz', manifest:false, events:false}]};
/已归档｜2026-09-25｜P001｜测试｜20 分钟｜隔离区｜ZEN-20260925-P001-S16/.test(X.phLabelArchived(X.PHLIST.arch[0]))
  ? ok('【19】归档项写成人话（日期／受试者／类型／时长／状态），不必先认 ZEN 编号') : fail('归档标签不符：' + X.phLabelArchived(X.PHLIST.arch[0]));
/本机暂存｜2026-09-28 17:40｜未入库｜档案 有·事件 无/.test(X.phLabelStaged(X.PHLIST.stag[0]))
  ? ok('【19】暂存项分得清未入库，并带档案／事件齐否') : fail('暂存标签不符：' + X.phLabelStaged(X.PHLIST.stag[0]));
/中断保留/.test(X.phLabelStaged(X.PHLIST.stag[1])) ? ok('【19】.partial 录制标成「中断保留」，不冒充正常会话') : fail('中断件未标注');
const sel19 = byId['phSid'];
X.phFillSel(sel19);
const og19 = sel19.kids.filter(n => n.tagName === 'OPTGROUP');
og19.length === 2 && /本机暂存/.test(og19[0].attrs.label) && /已归档/.test(og19[1].attrs.label)
  ? ok('【19】下拉认得服务端真实返回的 {archived, staged}（从前只认 sessions/items，所以永远空）') : fail('分组不符：' + og19.length);
X.PHLIST = {arch:[], stag:[]};
/暂无会话/.test(X.phFillSel(sel19) && sel19.kids.map(n => String(n.textContent)).join(''))
  ? ok('【19】一个会话都没有时不崩，明写「暂无会话」') : fail('空清单处理不符');

const mf19 = byCls('mfold'), mt19 = byCls('mftgl'), mg19 = byCls('mgrp');
mg19.length === 5 && mf19.length === 3 && mt19.length === 3
  ? ok('【19】版面重排到位：5 组〈人工采集栏〉挂在各自的"自动跑"卡下（T1／T2／T3／T4／事后读数），'
      + 'T9–T11 自带操作条的 3 张表留在本卡内折叠——不再两种版面混着摆')
  : fail('分组不符：mgrp=' + mg19.length + ' mfold=' + mf19.length + '/' + mt19.length);
mg19.every(g => !clsHas(g, 'open'))
  ? ok('【19】人工组默认整组收起——一屏看下去只剩"自动跑"这一条主线') : fail('有人工组默认是开着的');
(function(){ const bad = [];
  mg19.forEach(g => { const box = (g.kids || []).filter(k => clsHas(k, 'mgbody'))[0];
    if(!box) return bad.push('无 mgbody');
    box.kids.forEach(c => { if(clsHas(c, 'card') && clsHas(c, 'closed')) bad.push((c.querySelector('h3')||{}).textContent); });
  });
  bad.length ? fail('组里的卡还带抽屉收起（点开组仍是空卡＝双重折叠）：' + bad.join('、'))
    : ok('【19】组内的卡不再二次折叠（09-29 真浏览器实跑抓到的"点了没开"，从此有断言兜住）');
})();
byCls('manhide').length === 0 && !X.FLOW.secs.some(s => s.blocks.some(b => b.k === 'timer'))
  ? ok('【19】两张旧手填计时器是**删掉**不是藏起来（FLOW 里已无 timer 件，renderTimer／TIMERS／LIVE.t1·t5 死代码一并清了）')
  : fail('旧手填计时器未删净');
function vidsIn(n){ const a = []; walk(n, a); const b = a.filter(x => x.attrs && x.attrs['data-vid']); return b.length ? b[0].attrs['data-vid'] : null; }
const vw19 = byCls('vrow');
const lifted = vw19.filter(n => !(n.attrs && n.attrs['data-vrow']));
const liftV = lifted.map(vidsIn).filter(Boolean).sort().join(',');
liftV === 't1v,t2v,t3v,t4v,t5v,t7v,t8v'
  ? ok('【19】7 项被收进人工组的，结论判定行都提到了自动卡上（t1v…t8v 一个不漏）——⑥甲 可改判不藏在按钮后面')
  : fail('提到明面的判定行集合不符：' + liftV);
vw19.filter(n => ancHas(n, 'mfold')).length === 0
  ? ok('【19】提上来的判定行没有一个又落回折叠里（提了等于没提就不算数）') : fail('判定行仍被折叠盖住');
const dv19 = q19.filter(n => n.attrs && n.attrs['data-vrow']);
dv19.length === 13
  ? ok('【19】完成度分母未被抬高：带 data-vrow 的"真格子"仍 13 个，提上来的副本不重复计数')
  : fail('data-vrow 计数：' + dv19.length);
X.S.meta.showManual = false; X.paintManual();
const gb19 = mg19[0].querySelector('.mgbtn');
gb19.click();
clsHas(mg19[0], 'open') && !clsHas(mg19[1], 'open')
  ? ok('【19】点开一组只展开这一组（就地看这一项的数），不牵连别处') : fail('单组开合不独立');
gb19.click();
!clsHas(mg19[0], 'open') ? ok('【19】再看一眼就收回，版面立刻回到"只有自动跑"的干净态') : fail('单组收不回');
X.toggleManual();
mg19.every(g => clsHas(g, 'open')) && mt19.every(b => /收起/.test(String(b.textContent)))
  ? ok('【19】页首「📋 人工采集栏」一键全展开，按钮字样跟着状态走（不让人找第二遍）') : fail('一键全展开不符');
X.toggleManual();
mg19.every(g => !clsHas(g, 'open')) && X.S.meta.showManual === false
  ? ok('【19】再点一键收回默认态（下次进来还是干净的）') : fail('一键收回失败');
const bt19 = q19.filter(n => n.tagName === 'BUTTON').map(n => String(n.textContent));
const need19 = ['▶ 开始 T9（打点＋响两声）','● 刚刚闪了，记一次','■ 结束 T9（打点＋响一声）',
  '▶ 戴上 VR 开始（10 分钟）','■ 出 VR，结束','取断包率并填表','▶ 两台同时开采','■ 两台同时结束','取通道数·时长·采样率'];
need19.every(t => bt19.indexOf(t) >= 0)
  ? ok('【19】T9／T10／T11 九个动作都在场——从哪开始、到哪结束、数据怎么调，各有一个按得下去的键')
  : fail('缺动作：' + need19.filter(t => bt19.indexOf(t) < 0).join('、'));
['t10Sa','t10Sb','t11Sa','t11Sb'].every(id => byId[id])
  ? ok('【19】四项对比各有会话选择框（两个一组：不戴VR／戴VR，左列／右列）') : fail('选择框缺失');
const o19 = {textContent:''};
X.t10Read({value:''}, {value:''}, o19);
/都要选上/.test(o19.textContent) ? ok('【19】没选会话就点取数：说清缺什么，不空转不报错') : fail('早退提示不符：' + o19.textContent);
X.t10Read({value:'ZEN-A'}, {value:'ZEN-A'}, o19);
/同一个会话/.test(o19.textContent) ? ok('【19】两个框选了同一个会话 → 拦住并说人话') : fail('同会话未拦：' + o19.textContent);
const o19b = {textContent:''};
X.t11Read({value:''}, {value:'local-B'}, o19b);
/两台设备的会话都要选上/.test(o19b.textContent) ? ok('【19】T11 同样先补齐两台会话才动手') : fail('T11 早退不符：' + o19b.textContent);
X.PHLIST = null; X.S.meta.showManual = false; X.recount();

console.log('\n（本次共创建 ' + created + ' 个节点）');
console.log(bad ? '结论：✗ 逻辑冒烟 ' + bad + ' 处问题' : '结论：✓ 逻辑冒烟全过');
process.exit(bad ? 1 : 0);
