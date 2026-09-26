/* 语法闸门（本窗可用的 node --check 替身）：抽出面板内联脚本 → vm.Script **只解析不执行** → 失败时二分定位首个破坏解析的行
   用法：node "01_项目管理/测试台验收工具/parse_check_panel_script.js" [--src <html路径>] */
const fs = require('fs'), path = require('path'), vm = require('vm');
const argIdx = process.argv.indexOf('--src');
const HTML = argIdx > 0 ? process.argv[argIdx + 1]
  : path.join(__dirname, '..', '20260925_NeuraDock设备性能测试流程表_v1.html');
const raw = fs.readFileSync(HTML, 'utf8');
const m = raw.match(/<script>([\s\S]*?)<\/script>/);
if (!m) { console.log('✗ 找不到内联脚本'); process.exit(2); }
const js = m[1].split(/\r\n|\n/);
try {
  new vm.Script(js.join('\n'), { filename: 'nd_panel_inline.js' });
  console.log('✓ 面板内联脚本纯解析通过（' + js.length + ' 行；vm.Script 只解析不执行）');
  process.exit(0);
} catch (e) {
  console.log('✗ 面板内联脚本语法错：' + e.message);
}
/* 前缀二分在语法上非单调，故逐行"扩展式"扫描：从报错可能性最高的新增块找起 */
const lines = js;
let lo = 0, hi = lines.length - 1, bad = -1;
const p = n => { try { new vm.Script(lines.slice(0, n).join('\n')); return true; } catch (_) { return false; } };
while (lo <= hi) { const mid = (lo + hi) >> 1; if (!p(mid)) { bad = mid; hi = mid - 1; } else lo = mid + 1; }
if (bad < 0) { console.log('（前缀二分未能定位：报错可能在文件尾部或非行级结构）'); process.exit(1); }
console.log('首个不可解析前缀结束于行 ' + (bad + 1) + '：');
for (let i = Math.max(0, bad - 10); i < Math.min(lines.length, bad + 6); i++)
  console.log((i + 1) + (i === bad ? ' >> ' : '    ') + lines[i]);
process.exit(1);
