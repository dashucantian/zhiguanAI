// F2 渲染冒烟：桩 DOM 跑 gantt()/flow() 全路径，捕获运行时异常。
const fs = require('fs');
const html = fs.readFileSync(process.argv[2], 'utf8');
const js = html.slice(html.indexOf('<script>') + 8, html.indexOf('</' + 'script>'));

const m = js.match(/const T = (.*?);\s*\n/);
if (!m) { console.error('T 行未匹配'); process.exit(1); }
const DATA = JSON.parse(m[1]);

global.innerWidth = 1440; global.innerHeight = 900;
const caps = {};
function el(id) {
  return {
    id, _html: '', textContent: '', style: {}, classList: { add() {}, remove() {} },
    set innerHTML(v) { this._html = v; caps[id] = v; },
    get innerHTML() { return this._html; },
    appendChild() {}, addEventListener() {},
    getBoundingClientRect: () => ({ width: 300, height: 200 }),
    querySelectorAll: (sel) => {
      const n = (caps[id] || '').split('class="bar"').length - 1;
      return Array.from({ length: n }, (_, k) => ({ dataset: { i: String(k) }, addEventListener() {} }));
    },
  };
}
const nodes = {};
global.document = { getElementById: (id) => (nodes[id] = nodes[id] || el(id)), createElement: () => el('tmp') };
global.addEventListener = () => {};

const src = js
  .replace(/const T = .*?;\s*\n/, '');   // 其余原样跑：桩节点可承载 onclick 赋值与末行 gantt()
eval('const T = ' + JSON.stringify(DATA) + ';\n' + src);

try { gantt(); console.log('gantt OK svg长度=', (caps.root || '').length); }
catch (e) { console.log('gantt FAIL:', e.message); process.exit(1); }
try { flow(); console.log('flow OK svg长度=', (caps.root || '').length); }
catch (e) { console.log('flow FAIL:', e.message); process.exit(1); }

// 语义断言
const g = caps.root || '';
if (!g.includes('ZG-053')) { console.log('FAIL: 甘特未见 ZG-053 条'); process.exit(1); }
flow();
const f = caps.root;
const lanes = ['待启动', '进行中', '待法师决策', '待法师审定', '已完成', '已搁置'].every(l => f.includes(l));
console.log('泳道六列齐=', lanes, '| 流程图节点数=', (f.match(/class="bar"/g) || []).length);
