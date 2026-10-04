// Executable DOM-harness regression, NOT real-browser/layout acceptance.
// node SCRIPT PROJECT_ROOT ; only reads explicit existing HTML, no network.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=process.argv[2];if(!root)throw Error('project root required');
const html=fs.readFileSync(path.join(root,'01_项目管理/任务关系图/20261004_W3只读协作接触面_v1.html'),'utf8');
const js=html.match(/<script>([\s\S]*?)<\/script>/)[1];
class Element {
 constructor(tag='div'){this.tag=tag;this.children=[];this.value='';this.textContent='';this.attributes={};this.listeners={};}
 appendChild(child){this.children.push(child);return child;}
 replaceChildren(...c){this.children=c;}
 setAttribute(k,v){this.attributes[k]=v;}
 addEventListener(k,fn){this.listeners[k]=fn;}
 fire(k){if(this.listeners[k])this.listeners[k]({target:this});}
 click(){if(this.onclick)this.onclick();this.fire('click');}
}
const tick=()=>new Promise(r=>setImmediate(r));
async function run(pages){
 const ids={};for(const id of ['query','filter','tasks','lanes','shown','status','notice','retrieved','modified'])ids[id]=new Element();ids.filter.value='all';
 let calls=0;const document={getElementById:id=>ids[id],createElement:tag=>new Element(tag)};
 const window={cowork:{callMcpTool:async(name,args)=>{assert.equal(name,'mcp__feishu__bitable_v1_appTableRecord_search');assert.equal(args.useUAT,false);assert(!args.data.field_names.includes('承担者'));const p=pages[calls++];if(p instanceof Error)throw p;if(p===undefined)throw Error('unexpected page request');return {structuredContent:p};}}};
 const context=vm.createContext({window,document,console,Date,Set,Map,Error});vm.runInContext(js,context);for(let i=0;i<6;i++)await tick();return {ids,calls,window,context};
}
const rows=[
 {record_id:'r1',fields:{任务编号:'ZG-SYN-1',任务名:[{text:'<img src=x onerror=alert(1)>协作测试',type:'text'}],状态:'进行中',裁决确认:false,依赖任务:{},更新时间:1790702480000}},
 {record_id:'r2',fields:{任务编号:'ZG-SYN-2',任务名:[{text:'已完成但待核',type:'text'}],状态:'已完成',裁决确认:true,依赖任务:{link_record_ids:['r1']},更新时间:1790702480000}},
 {record_id:'r3',fields:{任务编号:'ZG-SYN-3',任务名:[{text:'待启动',type:'text'}],状态:'待启动',依赖任务:{},更新时间:1790702480000}}
];
const page=(items,more=false,token='')=>({items,has_more:more,total:3,...(token?{page_token:token}:{})});
(async()=>{
 let r=await run([page(rows)]);assert.match(r.ids.status.textContent,/3 条/);assert.equal(r.ids.tasks.children.length,3);
 // Real listeners in harness, not merely model predicates.
 r.ids.query.value='ZG-SYN-2';r.ids.query.fire('input');assert.equal(r.ids.tasks.children.length,1);
 r.ids.query.value='';r.ids.query.fire('input');r.ids.filter.value='open';r.ids.filter.fire('change');assert.equal(r.ids.tasks.children.length,2);
 r.ids.filter.value='candidate';r.ids.filter.fire('change');assert.equal(r.ids.tasks.children.length,1);
 let article=r.ids.tasks.children[0],button=article.children[1].children[2];assert.equal(button.attributes['aria-expanded'],'false');button.click();article=r.ids.tasks.children[0];assert.equal(article.children.length,3);assert.equal(article.children[1].children[2].attributes['aria-expanded'],'true');assert(article.children[2].children.some(x=>x.textContent.includes('ZG-SYN-1')));article.children[1].children[2].click();assert.equal(r.ids.tasks.children[0].children.length,2);
 r.ids.filter.value='all';r.ids.filter.fire('change');assert.equal(r.ids.tasks.children[0].children[1].children[0].textContent,rows[0].fields.任务名[0].text);assert(!r.ids.tasks.children[0].children[1].children[0].children.length);
 r=await run([page([rows[0]],true,'next'),page(rows.slice(1))]);assert.equal(r.calls,2);assert.match(r.ids.status.textContent,/3 条，2 页/);
 for(const pages of [[{code:999,msg:'scope denied'}],[page([rows[0]],true,'same'),page([rows[1]],true,'same')],[page([rows[0]],true,'next'),page([rows[0],rows[2]])],[page([rows[0]],true,'next'),new Error('network failed')],[{items:rows,total:3}],[{items:rows,has_more:false,total:4}]]){
  r=await run(pages);assert.equal(r.ids.status.textContent,'读取未完成');assert(!r.ids.tasks.children.some(e=>e.className==='task'));assert.match(r.ids.notice.textContent,/未展示局部记录/);
 }
 console.log('PASS: DOM harness event search/filter/open/close, safe literal text, 2-page success; permission/repeating token/duplicate ID/midpage network/missing pagination/count failure hide partial rows.');
 console.log('LIMIT: no browser engine, CSS layout, native focus, accessibility tree or connector network verified by this harness.');
})().catch(e=>{console.error(e);process.exitCode=1;});
