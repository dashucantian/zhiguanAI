/* 角色声明表导出器（步 1·只读骨架 之 ①）
   方向：**面板内 ROLES 块是唯一权威源**（正本），本脚本把它导出为 `角色声明表.json` 供外部消费者读取。
   用法：node "01_项目管理/测试台验收工具/export_roles_config.js" [--write]
     · 不带 --write ＝ 只打印并做一致性自查（闸门用）；带 --write ＝ 覆盖写出 JSON（派生视图，勿手改）。
   依据：施工方案 §三「唯一权威配置；面板、脚本、报告一律从它派生」＋ D-0926-W1c ①③④⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮ 甲。 */
const fs = require('fs');
const path = require('path');

const REPO = path.join(__dirname, '..', '..');
const HTML = path.join(REPO, '01_项目管理', '20260925_NeuraDock设备性能测试流程表_v1.html');
const OUT = path.join(__dirname, '角色声明表.json');

/* 从 JS 源码里按花括号配平抽出一个字面量（与结构闸门同一手法：比正则稳） */
function sliceLiteral(src, declAt, openChar, closeChar) {
  const s0 = src.indexOf(openChar, declAt);
  let d = 0, end = -1;
  for (let k = s0; k < src.length; k++) {
    const c = src[k];
    if (c === openChar) d++;
    else if (c === closeChar) { d--; if (!d) { end = k; break; } }
  }
  if (end < 0) throw new Error('花括号/方括号不配平：' + openChar);
  return src.slice(s0, end + 1);
}

const src = fs.readFileSync(HTML, 'utf8');
const crypto = require('crypto');
const sha256 = s => crypto.createHash('sha256').update(s, 'utf8').digest('hex').slice(0, 16);
const js = src.match(/<script>([\s\S]*?)<\/script>/)[1];
const iR = js.indexOf('const ROLES ='), iS = js.indexOf('const SESS =');
if (iR < 0 || iS < 0) { console.log('✗ 面板里找不到 ROLES / SESS 声明'); process.exit(2); }
let ROLES, SESS;
try {
  ROLES = eval(sliceLiteral(js, iR, '[', ']'));
  SESS = eval(sliceLiteral(js, iS, '[', ']'));
} catch (e) { console.log('✗ 求值失败：' + e.message); process.exit(3); }

/* ── 三条硬约束自查（施工方案 §三表下注；违一条即退出码 4） ── */
const bad = [];
const r = t => ROLES.filter(x => x.t === t)[0];
if (r('t5').observer !== 'none') bad.push('T5 的 observer 必须是 none（场次 2 陪着坐＝不许盯屏）');
if (r('t6').judge !== 'human_signoff') bad.push('T6 的 judge 必须是 human_signoff（给不给原始档机器无法自证）');
if (!/两分|生理性伪迹/.test(r('t3').note || '')) bad.push('T3 必须带 ⑬ 伪迹两分口径');
ROLES.forEach(x => {
  ['t', 'name', 'sess', 'order', 'card', 'vid', 'actor', 'observer', 'judge', 'minAct', 'gateWhen', 'retry', 'resume']
    .forEach(k => { if (x[k] === undefined || x[k] === null || x[k] === '') bad.push(x.t + ' 缺字段 ' + k); });
  if (['human', 'machine', 'both'].indexOf(x.actor) < 0) bad.push(x.t + ' actor 取值非法：' + x.actor);
  if (['focused', 'ambient', 'none'].indexOf(x.observer) < 0) bad.push(x.t + ' observer 取值非法：' + x.observer);
});
if (ROLES.length !== 11) bad.push('ROLES 应为 11 行，现 ' + ROLES.length);
if (SESS.length !== 4) bad.push('SESS 应为 4 场次，现 ' + SESS.length);
if (bad.length) { console.log('✗ 硬约束自查未过：\n  ' + bad.join('\n  ')); process.exit(4); }

const doc = {
  _来源: '面板内 ROLES 块（唯一权威源）；本文件为导出的派生视图，**勿手改**——改面板后重跑本脚本 --write',
  _依据: '施工方案 §三 ＋ 登记分片/D-0926-W1c（法师 2026-09-26「①至⑮皆选甲」）',
  _判据说明: '本表只声明角色与处置，不含判据、不含阈值；判据权威仍是 qc_pipeline.py（阈值版本 20260920）',
  _源指纹: sha256(JSON.stringify(ROLES)),
  场次: SESS,
  角色声明: ROLES
};
const body = JSON.stringify(doc, null, 2) + '\n';
if (process.argv.indexOf('--write') >= 0) {
  fs.writeFileSync(OUT, body, 'utf8');
  console.log('✓ 已写出 ' + path.relative(REPO, OUT) + '（' + ROLES.length + ' 项／' + SESS.length + ' 场次，源指纹 ' + doc._源指纹 + '）');
} else {
  if (!fs.existsSync(OUT)) { console.log('✗ 派生文件不存在，请先跑：node export_roles_config.js --write'); process.exit(5); }
  let cur;
  try { cur = JSON.parse(fs.readFileSync(OUT, 'utf8')); }
  catch (e) { console.log('✗ 派生文件不是合法 JSON：' + e.message); process.exit(6); }
  const diff = [];
  if (JSON.stringify(cur.角色声明) !== JSON.stringify(ROLES)) diff.push('角色声明与面板 ROLES 不一致');
  if (JSON.stringify(cur.场次) !== JSON.stringify(SESS)) diff.push('场次表与面板 SESS 不一致');
  if (cur._源指纹 !== doc._源指纹) diff.push('源指纹不符（' + cur._源指纹 + ' ≠ ' + doc._源指纹 + '）');
  if (diff.length) { console.log('✗ ' + diff.join('；\n✗ ') + '\n  → 请在仓库根跑：node "01_项目管理/测试台验收工具/export_roles_config.js" --write'); process.exit(6); }
  console.log('✓ 派生文件与面板 ROLES 一致（' + ROLES.length + ' 项／' + SESS.length + ' 场次，源指纹 ' + doc._源指纹 + '）');
}
