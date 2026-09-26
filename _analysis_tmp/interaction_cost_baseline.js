/* 交互成本基线（一次性分析，_ 前缀不入库）
   目的：把"现在很机械"变成可核对的数字——今天这套面板要人动手多少次、其中多少其实机器能自己填。 */
const fs = require('fs');
const HTML = '01_项目管理/20260925_NeuraDock设备性能测试流程表_v1.html';
const src = fs.readFileSync(HTML, 'utf8');
const js = src.match(/<script>([\s\S]*?)<\/script>/)[1];
const i0 = js.indexOf('const FLOW ='), i1 = js.indexOf('const GATES =');
let FLOW; const s0 = js.indexOf('{', i0);
let d = 0, end = -1;
for (let k = s0; k < js.length; k++) { if (js[k] === '{') d++; else if (js[k] === '}') { d--; if (!d) { end = k; break; } } }
FLOW = eval('(' + js.slice(s0, end + 1) + ')');

/* 机器能自己填的字段前缀（来自面板内的自动跑器：T1A / T2A / T3A / posthoc） */
const AUTO = [/^t1a\d$/, /^t1t?\d$/, /^t2(s|p|f|q)_/, /^t3(a|b|c)\d$/, /^ph/, /^t5c\d$/, /^t6/, /^t7/, /^t8/];
const isAuto = f => AUTO.some(r => r.test(f));

let totalF = 0, autoF = 0, ck = 0, vd = 0;
const rows = [];
FLOW.secs.forEach(sec => {
  let f = 0, a = 0, c = 0, v = 0;
  sec.blocks.forEach(b => {
    if (b.k === 'grid') (b.rows || []).forEach(r => r.forEach(cell => {
      if (cell && typeof cell === 'object' && cell.f) { f++; if (isAuto(cell.f)) a++; }
    }));
    if (b.k === 'fields') (b.items || []).forEach(it => { f++; if (isAuto(it[0])) a++; });
    if (b.k === 'check') c += (b.items || []).length;
    if (b.v) v++;
  });
  totalF += f; autoF += a; ck += c; vd += v;
  rows.push([sec.name, f, a, f - a, c, v]);
});
console.log('小节'.padEnd(22) + '输入位  机器可自动填  仍需人手填  勾选  判定');
rows.forEach(r => console.log(String(r[0]).padEnd(24) + String(r[1]).padStart(4) + String(r[2]).padStart(12) + String(r[3]).padStart(12) + String(r[4]).padStart(6) + String(r[5]).padStart(6)));
console.log('-'.repeat(72));
console.log('合计'.padEnd(24) + String(totalF).padStart(4) + String(autoF).padStart(12) + String(totalF - autoF).padStart(12) + String(ck).padStart(6) + String(vd).padStart(6));
console.log('');
console.log('人的动作总量（勾选＋需手填＋判定）＝ ' + (ck + (totalF - autoF) + vd) + ' 次');
console.log('其中机器本可代劳的输入位 ＝ ' + autoF + ' 次（占输入位 ' + Math.round(100 * autoF / totalF) + '%）');
