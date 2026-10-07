#!/usr/bin/env node
// 架构证据模型回归闸：校验 architecture-model.json 的结构与 sourceRefs 可解析性。
// 规则来源：Qoder architecture-visualization 插件 examples/basic-architecture/run-smoke.mjs 的 validateModel()，
// 差异仅在 sourceRefs 基准路径改为本仓库根。退出码 0＝通过，1＝失败。
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '../..');
const MODEL = path.join(HERE, 'architecture-model.json');
const CONF = ['high', 'medium', 'low', 'unknown'];

const errors = [];
const assert = (c, m) => { if (!c) errors.push(m); };

const model = JSON.parse(readFileSync(MODEL, 'utf8'));
assert(model.schemaVersion === 1, 'schemaVersion 必须为 1');
assert(Array.isArray(model.nodes) && model.nodes.length > 0, 'nodes 不能为空');
assert(Array.isArray(model.edges) && model.edges.length > 0, 'edges 不能为空');

// sourceRef 形如 path/to/file.py:10-80 或 path#anchor，取冒号/井号前的文件部分
const checkRefs = (item, label) => {
  assert(Array.isArray(item.sourceRefs) && item.sourceRefs.length > 0, `${label} 缺 sourceRefs`);
  for (const ref of item.sourceRefs || []) {
    const filePart = ref.split('#')[0].split(':')[0];
    assert(existsSync(path.join(ROOT, filePart)), `${label} sourceRef 无法解析: ${ref}`);
  }
  assert(CONF.includes(item.confidence), `${label} confidence 非法: ${item.confidence}`);
};

const nodeIds = new Set();
for (const n of model.nodes) {
  assert(typeof n.id === 'string' && n.id.length > 0, '存在无 id 的节点');
  assert(!nodeIds.has(n.id), `节点 id 重复: ${n.id}`);
  nodeIds.add(n.id);
  checkRefs(n, `节点 ${n.id}`);
  // 现状节点须有 high/medium 证据；target/proposed 可无代码证据但必须标明
  if (n.state === 'current') {
    assert(['high', 'medium'].includes(n.confidence), `现状节点 ${n.id} 证据不足（confidence=${n.confidence}）`);
  }
}

const edgeIds = new Set();
for (const e of model.edges) {
  assert(typeof e.id === 'string' && e.id.length > 0, '存在无 id 的边');
  assert(!edgeIds.has(e.id), `边 id 重复: ${e.id}`);
  edgeIds.add(e.id);
  assert(nodeIds.has(e.from), `边 ${e.id} 起点不存在: ${e.from}`);
  assert(nodeIds.has(e.to), `边 ${e.id} 终点不存在: ${e.to}`);
  checkRefs(e, `边 ${e.id}`);
}

const tally = k => `${model.nodes.filter(n => n.confidence === k).length}/${model.edges.filter(e => e.confidence === k).length}`;
const report = {
  status: errors.length ? 'FAILED' : 'PASSED',
  model: path.relative(ROOT, MODEL),
  nodes: model.nodes.length,
  edges: model.edges.length,
  confidence_high: tally('high'),
  confidence_medium: tally('medium'),
  confidence_low: tally('low'),
  errors,
};
console.log(JSON.stringify(report, null, 2));
process.exit(errors.length ? 1 : 0);
