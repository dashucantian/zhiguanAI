#!/usr/bin/env node
// 双键锚点探针（图谱双轨线内部作业序，谁改台账谁跑）：
// 展开 architecture-model.json 全部 sourceRefs，逐条取其「末行」内容，两道判据：
//   ① 空行判据（10-10 原探针）：锚行是空行 ⇒ 该行号必不对应任何声明。
//   ② 双键判据（10-13 依 542dc2cd 总单 TP-2 放行落码）：起始行＋符号名。
//      · 对象形态 ref {"ref":"file:line","symbol":"…"} ⇒ 符号比对（代码类抽声明名，其余抽行指纹）。
//      · 字符串 ref 以「（…）」结尾 ⇒ 宽松锥检（去节号后取最长前缀 ≥3 字须命中锚行）；
//        存量双锥 `file:line（§节 名）` 由此免回改即受检（协调窗 542dc2cd 边界②：存量零回改）。
// 为什么需要它：validate-model.mjs 剥掉行号只验文件存在；QGraphFlow 只验区间落在文件长度内；
// 门9 只判指空／越界——「非空但错行」这一类此前两道闸都放行（协调正本 §31.3）。
// 只读，不写任何文件。退出码 0＝CLEAN，1＝NEEDS-RECHECK。
// 用法：node 05_产品与开发/架构可视化/validate-anchors.mjs   （任意 cwd 皆可，仓库根由本件位置推出）
import { existsSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));   // 05_产品与开发/架构可视化
const ROOT = path.resolve(HERE, '../..');                     // 仓库根
const MODEL = path.join(HERE, 'architecture-model.json');

const norm = s => s.replace(/\t/g, '  ').trim().replace(/\s+/g, ' ');
const PY_DECL = /^\s*(?:async\s+)?(def|class)\s+([A-Za-z_]\w*)/;
const JS_DECL = /^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(function\*?|class|const|let|var)\s+([A-Za-z_$][\w$]*)/;
const JSON_KEY = /^\s*"([^"]+)"\s*:/;

// 声明侧与验证侧共用同一抽取器（禁手抄，10-12 假告警的另一半根因即「照旧值抄」）。
// 抽不到声明名（如锚在函数体内）⇒ 退行指纹：归一化后前 48 字。
export function extractSymbol(file, lineText) {
  if (/\.py$/.test(file)) { const m = lineText.match(PY_DECL); if (m) return { kind: 'decl', symbol: m[2] }; }
  else if (/\.(mjs|js|ts)$/.test(file)) { const m = lineText.match(JS_DECL); if (m) return { kind: 'decl', symbol: m[2] }; }
  else if (/\.json$/.test(file)) { const m = lineText.match(JSON_KEY); if (m) return { kind: 'decl', symbol: m[1] }; }
  return { kind: 'fp', symbol: norm(lineText).slice(0, 48) };
}

// 验证侧：MATCH｜'MISMATCH:blank'｜'MISMATCH:decl'｜'MISMATCH:fp'（冒号后＝失配理由）。
export function verifySymbol(file, lineText, sym) {
  if (norm(lineText) === '') return 'MISMATCH:blank';
  if (/\.py$/.test(file)) { const m = lineText.match(PY_DECL); return m && m[2] === sym ? 'MATCH' : 'MISMATCH:decl'; }
  if (/\.(mjs|js|ts)$/.test(file)) {
    const m = lineText.match(JS_DECL);
    if (m) return m[2] === sym ? 'MATCH' : 'MISMATCH:decl';
  } else if (/\.json$/.test(file)) {
    const m = lineText.match(JSON_KEY);
    if (m) return m[1] === sym ? 'MATCH' : 'MISMATCH:decl';
  }
  return norm(lineText).startsWith(sym) ? 'MATCH' : 'MISMATCH:fp';
}

// 宽松锥检：锥名去节号（§…空格）后，取最长前缀（降至 3 字）须命中锚行；全字面引用直接命中。
// 这是存量双锥的增量保护（挡空行与整行换脸），严格保证由新锚的对象形态 fp／decl 承担。
export function coneHit(lineText, cone) {
  if (lineText.includes(cone)) return true;
  const name = cone.replace(/^§\S*\s*/, '');
  for (let L = name.length; L >= 3; L--) if (lineText.includes(name.slice(0, L))) return true;
  return false;
}

function main() {
  const model = JSON.parse(readFileSync(MODEL, 'utf8'));
  const refs = [];
  for (const [kind, list] of [['节点', model.nodes], ['边', model.edges]])
    for (const item of list) for (const r of item.sourceRefs || []) {
      if (typeof r === 'string') refs.push([`${kind} ${item.id}`, { ref: r }]);
      else refs.push([`${kind} ${item.id}`, { ref: r.ref, symbol: r.symbol }]);
    }

  const cache = new Map();
  const linesOf = abs => {
    if (!cache.has(abs)) cache.set(abs, readFileSync(abs, 'utf8').split(/\r?\n/));
    return cache.get(abs);
  };
  const TEXTUAL = /\.(py|md|json|dot|dsl|mjs|js|ts|ps1|csv|html|txt|toml|cfg|ini|yml|yaml)$/;

  let missing = 0, outOfRange = 0, blank = 0, sectionAnchored = 0, dirRefs = 0, skipped = 0;
  let symTotal = 0, symMatch = 0, symFail = 0, symUnsupported = 0;
  for (const [who, { ref, symbol }] of refs) {
    if (ref.includes('#')) { sectionAnchored++; continue; }        // 章节锚＝有意不用行号
    const cone = (ref.match(/（([^）]+)）\s*$/) || [])[1];
    const colon = ref.indexOf(':');
    const file = colon < 0 ? ref : ref.slice(0, colon);
    const loc = colon < 0 ? '' : ref.slice(colon + 1);
    const abs = path.join(ROOT, file);
    if (!existsSync(abs)) { console.log(`★缺文件 ${ref}  ← ${who}`); missing++; continue; }
    if (statSync(abs).isDirectory()) { dirRefs++; continue; }      // 目录类锚（如 state/）无行号语义
    if (!TEXTUAL.test(file)) { skipped++; if (symbol) symUnsupported++; continue; }
    const lines = linesOf(abs);
    const last = Math.max(...loc.split(/[-,]/).map(x => parseInt(x, 10) || 0));
    if (!last) { skipped++; continue; }
    if (last > lines.length) { console.log(`★越界 ${ref}（文件 ${lines.length} 行）  ← ${who}`); outOfRange++; continue; }
    const lineText = lines[last - 1] || '';
    if ((lineText).trim() === '') { console.log(`★空行 ${ref}  ← ${who}`); blank++; if (cone || symbol) symFail++; continue; }
    if (cone) {
      symTotal++;
      if (coneHit(lineText, cone)) symMatch++;
      else { console.log(`★锥失配 ${ref}（锥「${cone}」未命中该行）  ← ${who}`); symFail++; }
    }
    if (symbol) {
      symTotal++;
      const v = verifySymbol(file, lineText, symbol);
      if (v === 'MATCH') symMatch++;
      else { console.log(`★错行 ${ref}（声明符号「${symbol}」现判 ${v}）  ← ${who}`); symFail++; }
    }
  }
  const verdict = missing || outOfRange || blank || symFail ? 'NEEDS-RECHECK' : 'CLEAN';
  console.log(JSON.stringify({
    refs: refs.length, sectionAnchored, dirRefs, skipped, missing, outOfRange, blankLine: blank,
    symTotal, symMatch, symFail, symUnsupported, coverage: `${symTotal}/${refs.length}`, verdict,
  }));
  process.exit(verdict === 'CLEAN' ? 0 : 1);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main();
