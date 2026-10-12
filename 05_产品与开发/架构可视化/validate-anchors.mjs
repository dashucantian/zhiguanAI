#!/usr/bin/env node
// 空行探针（图谱双轨线内部作业序，谁改台账谁跑）：
// 展开 architecture-model.json 全部 sourceRefs，逐条取其「末行」内容；落在空行＝该行号必不对应任何声明。
// 为什么需要它：现有两道闸都抓不到这一类——validate-model.mjs 剥掉行号只验文件存在；
// QGraphFlow 只验行区间落在文件长度内，锚点被插行顺延后照样 passed，实则指向空行。
// 只读，不写任何文件。退出码 0＝CLEAN，1＝NEEDS-RECHECK。
// 用法：node 05_产品与开发/架构可视化/validate-anchors.mjs   （任意 cwd 皆可，仓库根由本件位置推出）
import { existsSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));   // 05_产品与开发/架构可视化
const ROOT = path.resolve(HERE, '../..');                     // 仓库根
const MODEL = path.join(HERE, 'architecture-model.json');

const model = JSON.parse(readFileSync(MODEL, 'utf8'));
const refs = [];
for (const [kind, list] of [['节点', model.nodes], ['边', model.edges]])
  for (const item of list) for (const r of item.sourceRefs || []) refs.push([`${kind} ${item.id}`, r]);

const cache = new Map();
const linesOf = abs => {
  if (!cache.has(abs)) cache.set(abs, readFileSync(abs, 'utf8').split(/\r?\n/));
  return cache.get(abs);
};
const TEXTUAL = /\.(py|md|json|dot|dsl|mjs|js|ts|ps1|csv|html|txt|toml|cfg|ini|yml|yaml)$/;

let missing = 0, outOfRange = 0, blank = 0, sectionAnchored = 0, dirRefs = 0, skipped = 0;
for (const [who, ref] of refs) {
  if (ref.includes('#')) { sectionAnchored++; continue; }        // 章节锚＝有意不用行号
  const colon = ref.indexOf(':');
  const file = colon < 0 ? ref : ref.slice(0, colon);
  const loc = colon < 0 ? '' : ref.slice(colon + 1);
  const abs = path.join(ROOT, file);
  if (!existsSync(abs)) { console.log(`★缺文件 ${ref}  ← ${who}`); missing++; continue; }
  if (statSync(abs).isDirectory()) { dirRefs++; continue; }      // 目录类锚（如 state/）无行号语义
  if (!TEXTUAL.test(file)) { skipped++; continue; }
  const lines = linesOf(abs);
  const last = Math.max(...loc.split(/[-,]/).map(x => parseInt(x, 10) || 0));
  if (!last) { skipped++; continue; }
  if (last > lines.length) { console.log(`★越界 ${ref}（文件 ${lines.length} 行）  ← ${who}`); outOfRange++; continue; }
  if ((lines[last - 1] || '').trim() === '') { console.log(`★空行 ${ref}  ← ${who}`); blank++; }
}
const verdict = missing || outOfRange || blank ? 'NEEDS-RECHECK' : 'CLEAN';
console.log(JSON.stringify({ refs: refs.length, sectionAnchored, dirRefs, skipped, missing, outOfRange, blankLine: blank, verdict }));
process.exit(verdict === 'CLEAN' ? 0 : 1);
