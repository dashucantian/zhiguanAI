// 重叠验证桩：在 node 里跑 HTML 内嵌的**真实**布局代码，输出三种分组模式下的叶间距统计。
// 桩件仅补齐 render 依赖的 DOM 接口，算法本体逐字取自带产物。
const fs = require('fs');
const html = fs.readFileSync(process.argv[2], 'utf8');
const js = html.slice(html.indexOf('<script>') + 8, html.indexOf('</' + 'script>'));

// 截出 DATA 行
const m = js.match(/const DATA = (.*?);\s*\n/);
if(!m) { console.error('DATA行未匹配，前120字：', js.slice(0,120)); process.exit(1); }
const DATA = JSON.parse(m[1]);

// —— DOM/环境桩 ——
global.innerWidth = +(process.argv[4] || 1920); global.innerHeight = +(process.argv[5] || 1080);
const captures = [];
const elStub = (name) => ({
  value: name === 'mode' ? (process.argv[3] || 'stage') : '',
  textContent: '', innerHTML: '', disabled: false, appendChild(){}, addEventListener(){},
  getBoundingClientRect: () => ({ width: 420, height: 300 }),
  style: {},
});
global.document = {
  getElementById: (n) => (n === 'svg' ? { set innerHTML(v){ captures.push(v); }, querySelectorAll(){ return []; } } : elStub(n)),
  createElement: () => elStub('opt'),
};
global.addEventListener = () => {};

// 从真实 JS 里取需要的函数体：render 及其依赖（bind/esc/groupKey/tFilter/DATA）
const src = js
  .replace(/const DATA = .*?;\s*\n/, '')              // DATA 已单独注入
  .replace(/if \(!DATA\.hasPrinciple\)[^\n]*\n?/, '')
  .replace(/const S = document[^\n]*\n?/, 'const S = document.getElementById("svg"); const TIP = document.getElementById("tip");\n')
  .replace(/^[ \t]*bind\(\);/m, '/*bind跳过*/')        // 事件绑定无 DOM 可跳
  .replace(/\/\/ init controls[\s\S]*$/, '\n');       // 控件初始化段整体跳过

eval(src);   // 定义 render/esc/groupKey 等到本作用域
render();

// 从捕获的 SVG 提取叶坐标
const coords = [...captures[0].matchAll(/class="tnode" cx="([\d.]+)" cy="([\d.]+)"/g)].map(x => [+x[1], +x[2]]);
let minD = 1e9, pairs = 0, hist = {};
for (let i = 0; i < coords.length; i++)
  for (let k = i + 1; k < coords.length; k++) {
    const d = Math.hypot(coords[i][0] - coords[k][0], coords[i][1] - coords[k][1]);
    minD = Math.min(minD, d);
    const b = d < 8 ? '<8(遮挡)' : d < 14 ? '<14(贴挤)' : d < 20 ? '<20(近)' : '>=20';
    hist[b] = (hist[b] || 0) + 1;
    if (d < 14) pairs++;
  }
console.log(process.argv[3] || 'stage', '叶=' + coords.length, '最小间距=' + minD.toFixed(1), '对<14px=' + pairs, JSON.stringify(hist));
