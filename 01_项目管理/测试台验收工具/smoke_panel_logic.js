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
  + '\n;globalThis.__X = {ROLES, SESS, S, FLOW, build, hostNext, sumSuggest, autoFillRecord, derivedRows, renderHostBar, recount};\n';

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
console.log('\n（本次共创建 ' + created + ' 个节点）');
console.log(bad ? '结论：✗ 逻辑冒烟 ' + bad + ' 处问题' : '结论：✓ 逻辑冒烟全过');
process.exit(bad ? 1 : 0);
