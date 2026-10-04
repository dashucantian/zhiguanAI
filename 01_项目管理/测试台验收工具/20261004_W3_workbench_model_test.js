const assert=require("node:assert/strict");global.window={W3_TEST:true};

const TOOL='mcp__feishu__bitable_v1_appTableRecord_search';
const BASE='X4xXbTF57acOnZs1ZzZcF4P2nJg', TABLE='tblLf45tgSgBoLue';
const FIELDS=['任务编号','任务名','所属阶段','状态','AI执行窗口','裁决确认','受理戳','承接状态','依赖任务','计划开始','计划截止','更新时间'];
const text=v=>v==null?'':Array.isArray(v)?v.map(text).join(' / '):typeof v==='object'?text(v.text??v.name??''):String(v);
function normalize(items){
 if(!Array.isArray(items))throw Error('记录列表形态未知');
 const seen=new Set(), nums=new Set();
 return items.map(it=>{
  if(!it||typeof it.record_id!=='string'||!it.record_id||!it.fields||typeof it.fields!=='object')throw Error('记录缺ID或字段');
  if(seen.has(it.record_id))throw Error('分页出现重复记录；不标为完整');seen.add(it.record_id);
  const f=it.fields,n=text(f['任务编号']);if(!n||nums.has(n))throw Error('任务编号缺失或重复');nums.add(n);
  let deps=null;if(Object.hasOwn(f,'依赖任务')){const d=f['依赖任务'];if(d&&typeof d==='object'&&!Array.isArray(d)&&Object.keys(d).length===0)deps=[];else if(d&&Array.isArray(d.link_record_ids)&&d.link_record_ids.every(x=>typeof x==='string'&&x))deps=d.link_record_ids.slice();else throw Error('依赖格式未知');}
  const check=Object.hasOwn(f,'裁决确认')?f['裁决确认']:null;if(check!==null&&typeof check!=='boolean')throw Error('确认字段不是明确布尔');
  const ms=k=>{if(!Object.hasOwn(f,k))return null;const v=f[k];if(typeof v!=='number'||!Number.isFinite(v)||v<=0)throw Error('日期格式未知');return v;};
  return {rid:it.record_id,num:n,name:text(f['任务名']),phase:text(f['所属阶段']),state:text(f['状态'])||'未返回',window:text(f['AI执行窗口']),check,stamp:text(f['受理戳']),stampReturned:Object.hasOwn(f,'受理戳'),accept:text(f['承接状态']),deps,start:ms('计划开始'),end:ms('计划截止'),modified:ms('更新时间')};
 });
}
function summarize(rows){const counts={},ids=new Set(rows.map(r=>r.rid));let edges=0,dangling=0,partial=0,full=0;for(const r of rows){counts[r.state]=(counts[r.state]||0)+1;edges+=(r.deps||[]).length;dangling+=(r.deps||[]).filter(d=>!ids.has(d)).length;partial+=(r.start===null)!==(r.end===null)?1:0;full+=r.start!==null&&r.end!==null?1:0;}return {counts,edges,dangling,partial,full,candidate:rows.filter(r=>r.check===true&&!r.stamp).length,unknownCheck:rows.filter(r=>r.check===null).length,latest:Math.max(0,...rows.map(r=>r.modified||0))};}
function unwrap(r){if(r.isError)throw Error('连接器返回错误');let p=r.structuredContent;if(p==null){const t=(r.content||[]).filter(c=>c.type==='text').map(c=>c.text).join('\n');try{p=JSON.parse(t);}catch{throw Error('连接器响应无法解析');}}if(typeof p==='string')p=JSON.parse(p);if(!p||p.errorMessage||(p.code!==undefined&&p.code!==0))throw Error(p?.msg||p?.errorMessage||'接口拒绝');if(!Array.isArray(p.items)||typeof p.has_more!=='boolean')throw Error('响应或分页信息不完整');return p;}
let rows=[],complete=false,selected=null;
const el=id=>document.getElementById(id),fmt=ms=>ms?new Date(ms).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false})+'（北京时间）':'未返回';
function add(parent,tag,value,cls){const e=document.createElement(tag);if(cls)e.className=cls;e.textContent=value;parent.appendChild(e);return e;}
function render(){
 const stats=summarize(rows);el('lanes').replaceChildren();for(const s of ['进行中','待法师审定','待启动','已搁置','已完成']){const d=document.createElement('div');d.className='lane';add(d,'strong',String(stats.counts[s]||0));add(d,'span',s);el('lanes').appendChild(d);}for(const [s,n] of Object.entries(stats.counts))if(!['进行中','待法师审定','待启动','已搁置','已完成'].includes(s)){const d=document.createElement('div');d.className='lane';add(d,'strong',String(n));add(d,'span',s);el('lanes').appendChild(d);}
 const q=el('query').value.trim().toLowerCase(),filter=el('filter').value;
 const list=rows.filter(r=>(!q||(r.num+' '+r.name).toLowerCase().includes(q))&&(filter==='all'||filter==='open'&&!['已完成','已搁置'].includes(r.state)||filter==='candidate'&&r.check===true&&!r.stamp||r.state===filter));
 el('shown').textContent=`显示 ${list.length} / ${rows.length} 条。依赖 ${stats.edges} 条，完整排期 ${stats.full} 条，部分排期 ${stats.partial} 条。`;
 el('tasks').replaceChildren();const map=new Map(rows.map(r=>[r.rid,r.num]));
 for(const r of list){const article=document.createElement('article');article.className='task';add(article,'div',r.num,'num');const main=document.createElement('div');add(main,'p',r.name||'任务名未返回','name');const meta=document.createElement('div');meta.className='meta';add(meta,'span',r.state,'badge');add(meta,'span',(r.window||'执行窗口未返回')+'；承接：'+(r.accept||'未返回'));main.appendChild(meta);const b=add(main,'button',selected===r.rid?'收起信息':'查看依赖与承接');b.type='button';b.setAttribute('aria-expanded',String(selected===r.rid));b.onclick=()=>{selected=selected===r.rid?null:r.rid;render();};article.appendChild(main);
 if(selected===r.rid){const detail=document.createElement('div');detail.className='detail';add(detail,'p','确认：'+(r.check===null?'未返回':r.check?'已勾选':'未勾选')+'；受理戳：'+(r.stamp?'已存在（内容不展示）':r.stampReturned?'空':'未返回'));add(detail,'p','依赖：'+(r.deps===null?'未返回':r.deps.length?r.deps.map(id=>map.get(id)||'外部／当前未读到').join('、'):'已返回空依赖'));add(detail,'p','计划开始：'+fmt(r.start)+'；截止：'+fmt(r.end));add(detail,'p','记录修改：'+fmt(r.modified));if(r.check===true&&!r.stamp)add(detail,'p','待核候选，不等于已获施工授权；已完成任务也可能有未承接裁决。');article.appendChild(detail);}el('tasks').appendChild(article);}
 if(!list.length)add(el('tasks'),'p',rows.length?'没有匹配任务。':'尚无成功读取的数据。','empty');
}
async function boot(){
 try{if(!window.cowork?.callMcpTool)throw Error('本页需要在Cowork持久视图中打开；文件预览不能调用连接器');
 const all=[],tokens=new Set();let token='',expected=null,pages=0;for(;;){
  const r=await window.cowork.callMcpTool(TOOL,{data:{view_id:'',field_names:FIELDS,sort:[],filter:{conjunction:'and',conditions:[]},automatic_fields:false},params:{user_id_type:'open_id',page_token:token,page_size:100},path:{app_token:BASE,table_id:TABLE},useUAT:false});const p=unwrap(r);pages++;if(typeof p.total==='number'){if(expected!==null&&expected!==p.total)throw Error('分页期间总数改变，请重新读取');expected=p.total;}all.push(...p.items);if(!p.has_more)break;if(typeof p.page_token!=='string'||!p.page_token||tokens.has(p.page_token)||pages>=20)throw Error('分页未能完整结束');token=p.page_token;tokens.add(token);
 }
 if(expected!==null&&expected!==all.length)throw Error('总数与返回条数不符');rows=normalize(all);complete=true;const s=summarize(rows);el('status').textContent=`只读查询成功：${rows.length} 条，${pages} 页完整返回`;el('retrieved').textContent=fmt(Date.now());el('modified').textContent=fmt(s.latest);const warnings=[];if(s.latest&&Date.now()-s.latest>86400000)warnings.push('任务最近修改早于本次读取：通道已刷新，不表示看板已同步所有本地进展。');warnings.push(`确认且空戳候选 ${s.candidate} 条；确认未返回 ${s.unknownCheck} 条。不据此自动派工。`);if(s.dangling)warnings.push(`依赖有 ${s.dangling} 条指向本次未读到的记录。`);el('notice').textContent=warnings.join(' ');render();
 }catch(e){complete=false;el('status').textContent='读取未完成';el('notice').textContent='未展示局部记录。'+(e.message||'连接失败')+'。检查权限或稍后用顶部Reload重试。';el('retrieved').textContent='未完成，不标为当前数据';render();}
}
if(typeof window!=='undefined'){window.W3ReadModel={normalize,summarize,unwrap};if(!window.W3_TEST){el('query').addEventListener('input',render);el('filter').addEventListener('change',render);boot();}}

const m=window.W3ReadModel;
const src=[{record_id:"r1",fields:{任务编号:"ZG-T1",状态:"进行中",裁决确认:false,依赖任务:{},计划开始:1790438400000}},{record_id:"r2",fields:{任务编号:"ZG-T2",状态:"已完成",裁决确认:true,依赖任务:{link_record_ids:["r1"]}}},{record_id:"r3",fields:{任务编号:"ZG-T3",状态:"待启动",依赖任务:{}}}];
const r=m.normalize(src), s=m.summarize(r);assert.equal(r[0].check,false);assert.equal(r[2].check,null);assert.equal(s.edges,1);assert.equal(s.partial,1);assert.equal(s.full,0);assert.equal(s.candidate,1);assert.equal(s.unknownCheck,1);assert.equal(s.dangling,0);assert.throws(()=>m.normalize([...src,src[0]]));assert.throws(()=>m.normalize([{record_id:"x",fields:{任务编号:"x",裁决确认:[false]}}]));assert.throws(()=>m.unwrap({structuredContent:{code:999,msg:"denied"}}));assert.throws(()=>m.unwrap({structuredContent:{items:[]}}));assert.deepEqual(m.unwrap({content:[{type:"text",text:JSON.stringify({items:[],has_more:false,total:0})}]}),{items:[],has_more:false,total:0});console.log("PASS: false/missing checkbox, dependencies, partial schedule, duplicate IDs, invalid checkbox, errors/missing pagination, wrapped text response");
