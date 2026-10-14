#!/usr/bin/env node
// 自检（正反用例与落码同批交，依协调窗 542dc2cd 边界③）。只读，不写任何文件。
// 正例＝a3cef49 三处双锥＋声明名往返；反例＝销账白名单 7 条锚按双键逐条报 MISMATCH
// （复现 10-13 事故形态：正本档头插 2 行 ⇒ 锚全体顺移，in-memory 模拟、确定性、不随他窗提交而烂）。
// 用法：node 05_产品与开发/架构可视化/validate-anchors.selftest.mjs
import { execSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { extractSymbol, verifySymbol, coneHit } from './validate-anchors.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '../..');
const MD = '01_项目管理/20261008_W3_全项目协同整合基础与首批施工契约_v0.1.md';
const WL = '01_项目管理/登记分片/悬案已销.txt';

let pass = 0, fail = 0;
const ok = (name, cond, detail = '') => {
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${name}${detail ? '  ／ ' + detail : ''}`);
  cond ? pass++ : fail++;
};

const gitShow = f => execSync(`git show HEAD:${f}`, { cwd: ROOT, maxBuffer: 1 << 24 }).toString('utf8').split(/\r?\n/);
const readWT = f => readFileSync(path.join(ROOT, f), 'utf8').split(/\r?\n/);

// ---- 正例 A：a3cef49 三处双锥 ----
const entry = readWT('AI-开工入口.md')[111 - 1];
ok('正例A1 台账:245 双锥（宽松锥检）', coneHit(entry, '§二.9 停催令注记'), `命中词=「停催令」`);
ok('正例A2 台账:632 双锥（宽松锥检）', coneHit(entry, '§二.9 停催令注记'), '同上');
const evLines = readWT('05_产品与开发/架构可视化/zhiguan-l2-containers.evidence.md');
ok('正例A3 evidence.md:45 全字面双锥', evLines[45 - 1].includes('AI-开工入口.md:111（§二.9 停催令注记）'));

// ---- 正例 B：声明名往返（同一抽取器 mint → verify）----
const vmLines = readWT('05_产品与开发/架构可视化/validate-model.mjs');
const declIdx = vmLines.findIndex(l => /^\s*const\s+MODEL\b/.test(l));
const mintB = extractSymbol('05_产品与开发/架构可视化/validate-model.mjs', vmLines[declIdx]);
ok('正例B1 js 声明名往返', verifySymbol('05_产品与开发/架构可视化/validate-model.mjs', vmLines[declIdx], mintB.symbol) === 'MATCH', `symbol=${mintB.symbol}`);
const PY_RE = /^\s*def\s+[A-Za-z_]\w*\(/;
const pyFile = 'qc_pipeline.py'; // 模型所引代码件之一
const pyLines = readWT(pyFile);
const pyIdx = pyLines.findIndex(l => PY_RE.test(l));
const mintB2 = extractSymbol(pyFile, pyLines[pyIdx]);
ok('正例B2 py 声明名往返', verifySymbol(pyFile, pyLines[pyIdx], mintB2.symbol) === 'MATCH', `:${pyIdx + 1} symbol=${mintB2.symbol}`);

// ---- 反例：销账白名单 7 条锚，档头插 2 行 ⇒ 逐条 MISMATCH ----
const wlHead = gitShow(WL).filter(l => /^[^#].*契约_v0.1:\d+｜/.test(l));
const headMd = gitShow(MD);
ok('反例前置 锚条数=7', wlHead.length === 7, `实取 ${wlHead.length}`);
const anchors = wlHead.map(row => {
  const line = parseInt(row.match(/:(\d+)｜/)[1], 10);
  return { line, sym: extractSymbol(MD, headMd[line - 1]) };
});
// 事故形态复现：正本档头插 2 行（C3-值守-1013-15 实测 @@ -1 +1,3 @@）
const shifted = ['（模拟插入行一）', '（模拟插入行二）', ...headMd];
const results = anchors.map(a => verifySymbol(MD, shifted[a.line - 1], a.sym));
ok('反例 7/7 逐条 MISMATCH', results.every(r => r.startsWith('MISMATCH')),
  `空行 ${results.filter(r => r === 'MISMATCH:blank').length}／错行 ${results.filter(r => r === 'MISMATCH:fp').length}`);

// ---- 零假警：现势工作区（协调窗已顺移锚）同法 mint→verify 应 7/7 MATCH ----
const wlWt = readWT(WL).filter(l => /^[^#].*契约_v0.1:\d+｜/.test(l));
const wtMd = readWT(MD);
const wtResults = wlWt.map(row => {
  const line = parseInt(row.match(/:(\d+)｜/)[1], 10);
  return verifySymbol(MD, wtMd[line - 1], extractSymbol(MD, wtMd[line - 1]).symbol);
});
ok('零假警 工作区 7/7 MATCH', wtResults.length === 7 && wtResults.every(r => r === 'MATCH'), `实取 ${wtResults.length}`);

// ---- 跨侧现势（信息面，不硬断言）：HEAD mint → 工作区 verify ----
const cross = anchors.map(a => verifySymbol(MD, wtMd[a.line - 1], a.sym));
console.log(`INFO  跨侧（HEAD 锚 → 工作区正本）：MATCH ${cross.filter(r => r === 'MATCH').length}／blank ${cross.filter(r => r === 'MISMATCH:blank').length}／fp ${cross.filter(r => r === 'MISMATCH:fp').length}（协调窗落库后应归零）`);

console.log(`----\n自检 ${pass} 过／${fail} 挂`);
process.exit(fail ? 1 : 0);
