// 独立视图契约测试；只读现有HTML，Node vm执行信任的项目渲染脚本。
// 不联网、不回写，不等同真实浏览器交互验收。
const fs=require('fs'), vm=require('vm'), assert=require('assert').strict, path=require('path');
const file=process.argv[2]||path.join(__dirname,'../任务关系图/视图甘特流程图.html');
const html=fs.readFileSync(file,'utf8');
const src=html.slice(html.indexOf('<script>')+8,html.indexOf('</script>'));
const lanes=['待启动','进行中','待法师决策','待法师审定','已完成','已搁置'];
function render(tasks){
 const nodes={};function element(id){return nodes[id]||(nodes[id]={innerHTML:'',textContent:'',style:{},classList:{add(){},remove(){}},addEventListener(){},getBoundingClientRect(){return {width:300,height:200}},querySelectorAll(){return [...this.innerHTML.matchAll(/class="bar"[^>]*data-i="(\d+)"/g)].map(m=>({dataset:{i:m[1]},addEventListener(){}}))}})}
 const context=vm.createContext({innerWidth:1440,innerHeight:900,document:{getElementById:element},addEventListener(){},console});
 const code=src.replace(/const T = .*?;\s*\n/,'const T = '+JSON.stringify({tasks})+';\n');
 vm.runInContext(code,context,{timeout:2000});
 vm.runInContext('gantt()',context,{timeout:2000});const gantt=nodes.root.innerHTML;
 vm.runInContext('flow()',context,{timeout:2000});const flow=nodes.root.innerHTML;
 return {gantt,flow};
}
function validate(output,tasks){
 const planned=tasks.filter(t=>t.start&&t.end&&t.end>=t.start);
 assert.equal((output.gantt.match(/<rect class="bar"/g)||[]).length,planned.length,'甘特节点数');
 for(const t of planned)assert(output.gantt.includes(t.zg),'甘特缺任务编号');
 assert.equal((output.flow.match(/<circle class="bar"/g)||[]).length,tasks.length,'流程节点数');
 for(const l of lanes)assert(output.flow.includes(l+'（'),'流程缺泳道');
 const ids=new Set(tasks.map(t=>t.rid));
 const edges=tasks.reduce((n,t)=>n+t.dep.filter(d=>ids.has(d)).length,0);
 assert.equal((output.flow.match(/<path class="edge"/g)||[]).length,edges,'依赖边数');
 const outside=tasks.reduce((n,t)=>n+t.dep.filter(d=>!ids.has(d)).length,0);
 assert.equal((output.flow.match(/依赖出图外/g)||[]).length,outside,'悬空依赖提示');
}
const fixture=lanes.map((status,i)=>({i,rid:'r'+i,zg:'SYN-'+i,name:'合成任务',status,start:i<2?1790985600000+i*86400000:null,end:i<2?1791072000000+i*86400000:null,dep:i===1?['r0']:i===2?['outside']:[],dep_names:''}));
const output=render(fixture);validate(output,fixture);
let rejected=0;
for(const mutation of [o=>o.gantt=o.gantt.replace('<rect class="bar"','<rect class="removed"'),o=>o.flow=o.flow.replace('待法师决策（','删除泳道（'),o=>o.flow=o.flow.replace('<path class="edge"','<path class="removed"')]){
 const bad={...output};mutation(bad);assert.throws(()=>validate(bad,fixture));rejected++;
}
const m=src.match(/const T = (.*?);\s*\n/);const actual=JSON.parse(m[1]).tasks;validate(render(actual),actual);
console.log(JSON.stringify({synthetic_pass:true,negative_mutations_rejected:rejected,local_snapshot_task_count:actual.length,scope:'渲染结构与硬断言，不证明远端新鲜或真实浏览器事件'},null,2));
