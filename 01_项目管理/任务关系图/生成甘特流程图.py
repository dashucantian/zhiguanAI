# -*- coding: utf-8 -*-
"""甘特＋状态流程图 生成器（W3·F2·2026-09-23）

同源数据：读 任务关系图\_records_raw.json（lark-cli base +record-list 拉取）。
产出：本目录 视图甘特流程图.html（单文件、零依赖、离线可开）。

规则（法师 09-23 批 F2）：
- 甘特：仅画填了「计划开始＋计划截止」的任务；未填者归入"无排期"侧栏计数，不硬画；
- 流程图：状态六列泳道，任务按当前状态入道；「依赖任务」画箭头（依赖方→本方）；
  依赖指向"被依赖于"反查（依赖列存对侧 rid，本任务排在被依赖任务之后为顺流）；
- 状态色与关系图一致；日期为毫秒时间戳（field_type_list 实测 date 型）。
"""
import io
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "_records_raw.json")
OUT = os.path.join(HERE, "视图甘特流程图.html")


def load_tasks():
    raw = open(SRC, "rb").read()
    txt = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8-sig")
    d = json.loads(txt)["data"]
    cols = d["fields"]
    rids = d["record_id_list"]
    out = []
    for rid, arr in zip(rids, d["data"]):
        m = dict(zip(cols, arr))
        def cell(v):
            if v is None:
                return ""
            if isinstance(v, list):
                return "/".join(str(x.get("text") or x.get("name") or x.get("id") or x) if isinstance(x, dict) else str(x) for x in v)
            return str(v)
        def ms(v):
            # 实测：看板 datetime 读出为 ISO 串（如 2026-09-23T00:00:00.000+08:00）；兼容毫秒数
            if isinstance(v, (int, float)) and v > 1e12:
                return int(v)
            if isinstance(v, str) and len(v) >= 10:
                try:
                    from datetime import datetime
                    s = v.replace("Z", "+00:00")
                    return int(datetime.fromisoformat(s).timestamp() * 1000)
                except ValueError:
                    return None
            return None
        links = []
        lv = m.get("依赖任务")
        if isinstance(lv, list):
            for x in lv:
                if isinstance(x, dict) and x.get("id"):
                    links.append(x["id"])
                elif isinstance(x, str) and x.startswith("rec"):
                    links.append(x)
        out.append({
            "rid": rid,
            "name": cell(m.get("任务名")),
            "zg": cell(m.get("任务编号")),
            "status": cell(m.get("状态")),
            "start": ms(m.get("计划开始")),
            "end": ms(m.get("计划截止")),
            "dep": links,
        })

    # 依赖名映射：link 单元格存记录 ID 不可读，换成任务编号
    zmap = {t["rid"]: t["zg"] or t["name"][:8] for t in out}
    for t in out:
        t["dep_names"] = "、".join(zmap.get(x, "（外部/已删）") for x in t["dep"])
    return out


HTML = r"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>止观AI · 甘特与流程</title>
<style>
 body{margin:0;font-family:"Microsoft YaHei",system-ui,sans-serif;background:#0f172a;color:#e2e8f0;font-size:13px}
 #bar{position:fixed;top:0;left:0;right:0;height:44px;background:#1e293b;display:flex;align-items:center;gap:12px;padding:0 14px;z-index:9;border-bottom:1px solid #334155}
 #bar b{font-size:14px}
 .tab{background:#0f172a;color:#e2e8f0;border:1px solid #475569;border-radius:6px;padding:5px 14px;cursor:pointer}
 .tab.on{background:#7c3aed;border-color:#7c3aed}
 h2{font-size:14px;margin:14px 0 6px;color:#a78bfa}
 .wrap{margin-top:56px;padding:0 16px 40px}
 svg{background:#0b1220;border:1px solid #1e293b;border-radius:8px}
 .lane{fill:#111a2e}
 .laneline{stroke:#334155;stroke-width:1}
 .stitle{fill:#94a3b8;font-size:12px;font-weight:700}
 .bar{cursor:pointer;stroke:#0f172a}
 .bar:hover{stroke:#f8fafc}
 .blabel{fill:#e2e8f0;font-size:11px;pointer-events:none}
 .today{stroke:#f43f5e;stroke-width:2;stroke-dasharray:4 3}
 .axtxt{fill:#64748b;font-size:10px}
 .edge{stroke:#64748b;stroke-width:1.4;fill:none;marker-end:url(#arr)}
 #tip{position:fixed;max-width:420px;max-height:70vh;overflow:auto;background:#1e293b;border:1px solid #475569;border-radius:8px;padding:10px 12px;display:none;z-index:20;box-shadow:0 8px 24px rgba(0,0,0,.5)}
 #note{color:#94a3b8;font-size:12px;margin:6px 2px}
</style></head><body>
<div id="bar"><b>止观AI · 视图族（F2）</b>
 <button class="tab on" id="tG">甘特图</button><button class="tab" id="tF">状态流程图</button>
 <span id="note"></span></div>
<div class="wrap" id="root"></div>
<div id="tip"></div>
<script>
const T = __DATA__;
const HUE = {"待启动":"#9ca3af","进行中":"#3b82f6","待法师审定":"#f59e0b","待法师决策":"#ef4444","已完成":"#22c55e","已搁置":"#6b7280"};
const LANES = ["待启动","进行中","待法师决策","待法师审定","已完成","已搁置"];
const root=document.getElementById('root'), TIP=document.getElementById('tip'), NOTE=document.getElementById('note');
const esc=s=>(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
const dstr=ms=>{const d=new Date(ms);return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0')};

function bindTips(node,t){
  node.addEventListener('mouseenter',e=>{
    TIP.innerHTML=`<b style="color:#fbbf24">${esc(t.zg)}</b> ${esc(t.name)}<br>状态：${esc(t.status)}`
      +(t.start?`<br>计划：${dstr(t.start)} → ${t.end?dstr(t.end):'未填'}`:'<br>计划：未填')
      +(t.dep_names?`<br>依赖：${esc(t.dep_names)}`:'');
    TIP.style.display='block'; place(e);
  });
  node.addEventListener('mousemove',place);
  node.addEventListener('mouseleave',()=>TIP.style.display='none');
}
function place(e){const r=TIP.getBoundingClientRect();let x=e.clientX+12,y=e.clientY+12;
 if(x+r.width>innerWidth-8)x=e.clientX-r.width-12; if(y+r.height>innerHeight-8)y=Math.max(50,e.clientY-r.height-12);
 TIP.style.left=x+'px'; TIP.style.top=y+'px';}

function gantt(){
  const has=T.tasks.filter(t=>t.start&&t.end&&t.end>=t.start).sort((a,b)=>a.start-b.start);
  const no=T.tasks.length-has.length;
  NOTE.textContent=`有排期 ${has.length} 条 · 未填计划 ${no} 条（不硬画）`;
  if(!has.length){root.innerHTML='<p style="color:#94a3b8">尚无任何任务填了「计划开始＋计划截止」。在看板卡片填日期后重跑生成器即可见。当前示例：ZG-053。</p>';return;}
  const min=Math.min(...has.map(t=>t.start)), max=Math.max(...has.map(t=>t.end));
  const day=86400000, pad=(max-min)*0.06+day;
  const x0=170,W=Math.min(innerWidth-60,1000),H=has.length*34+70;
  const X=ms=>x0+(ms-min+pad)/((max-min)+2*pad)*(W-x0-20);
  let s=`<svg width="${W}" height="${H}">`;
  // 周刻度
  for(let k=0;k<=14;k++){const ms=min-pad+((max-min)+2*pad)*k/14; s+=`<line x1="${X(ms)}" y1="34" x2="${X(ms)}" y2="${H-10}" class="laneline" opacity="0.25"/><text x="${X(ms)}" y="${H-2}" class="axtxt" text-anchor="middle">${dstr(ms).slice(5)}</text>`;}
  const now=Date.now();
  if(now>=min-pad&&now<=max+pad) s+=`<line x1="${X(now)}" y1="30" x2="${X(now)}" y2="${H-10}" class="today"/><text x="${X(now)+3}" y="26" fill="#f43f5e" font-size="10">今日</text>`;
  has.forEach((t,i)=>{
    const y=44+i*34, x=X(t.start), w=Math.max(4,X(t.end)-X(t.start));
    s+=`<text x="6" y="${y+13}" class="blabel">${esc(t.zg)}</text>`;
    s+=`<text x="${x0-4}" y="${y+13}" text-anchor="end" class="blabel">${esc(t.name.slice(0,10))}${t.name.length>10?'…':''}</text>`;
    s+=`<rect class="bar" x="${x}" y="${y}" width="${w}" height="20" rx="4" fill="${HUE[t.status]||'#9ca3af'}" data-i="${t.i}"/>`;
    s+=`<text x="${x+w+6}" y="${y+14}" class="axtxt">${dstr(t.start).slice(5)}~${dstr(t.end).slice(5)}</text>`;
  });
  s+='</svg>'; root.innerHTML='<h2>甘特（计划起止）</h2>'+s;
  root.querySelectorAll('.bar').forEach(b=>bindTips(b,T.tasks[+b.dataset.i]));
}

function flow(){
  NOTE.textContent='泳道＝状态六列 · 箭头＝依赖（指向本任务为"它挡着我"）· 点击色块看详情';
  const W=Math.min(innerWidth-40,1200);
  const byL={}; LANES.forEach(l=>byL[l]=[]);
  T.tasks.forEach(t=>{(byL[t.status]=byL[t.status]||[]).push(t);});
  const maxN=Math.max(...LANES.map(l=>(byL[l]||[]).length));
  const colw=W/LANES.length, rowh=34, Hh=maxN*rowh+70;
  let s=`<svg width="${W}" height="${Hh}"><defs><marker id="arr" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0,0 L7,3.5 L0,7 z" fill="#64748b"/></marker></defs>`;
  const pos={};
  LANES.forEach((l,ci)=>{
    const cx=ci*colw+colw/2;
    s+=`<text x="${cx}" y="22" class="stitle" text-anchor="middle">${l}（${(byL[l]||[]).length}）</text>`;
    s+=`<line x1="${ci*colw}" y1="30" x2="${ci*colw}" y2="${Hh-6}" class="laneline"/>`;
    (byL[l]||[]).forEach((t,ri)=>{
      const x=cx-10,y=44+ri*rowh; pos[t.rid]={x,y};
      s+=`<circle class="bar" cx="${x}" cy="${y}" r="7" fill="${HUE[t.status]||'#9ca3af'}" data-i="${t.i}"/>`;
      s+=`<text x="${x+12}" y="${y+4}" class="blabel">${esc(t.zg||t.name.slice(0,8))}</text>`;
    });
  });
  // 依赖边：dep 列存"对侧任务"（=本任务被其对侧阻塞？法师填的是挡着我的任务）→ 画 对侧→本 箭头
  T.tasks.forEach(t=>t.dep.forEach(dd=>{const a=pos[dd],b=pos[t.rid];if(a&&b){
    const dy=b.y-a.y, cx1=a.x+30, cx2=b.x-30;
    s+=`<path class="edge" d="M${a.x+9},${a.y} C ${cx1},${a.y+dy/2} ${cx2},${b.y-dy/2} ${b.x-9},${b.y}"/>`;}else if(b&&!a){
    s+=`<text x="${b.x+12}" y="${b.y+14}" fill="#f43f5e" font-size="9">依赖出图外</text>`;}}));
  s+='</svg>';
  root.innerHTML='<h2>状态流程图（泳道＋依赖）</h2>'+s;
  root.querySelectorAll('.bar').forEach(b=>bindTips(b,T.tasks[+b.dataset.i]));
}

const pack={tasks:T.tasks, hasPlan:T.tasks.some(t=>t.start&&t.end)};
let view='G';
document.getElementById('tG').onclick=()=>{view='G';document.getElementById('tG').classList.add('on');document.getElementById('tF').classList.remove('on');gantt();};
document.getElementById('tF').onclick=()=>{view='F';document.getElementById('tF').classList.add('on');document.getElementById('tG').classList.remove('on');flow();};
gantt();
</script></body></html>
"""


def main():
    tasks = load_tasks()
    for i, t in enumerate(tasks):
        t["i"] = i
    payload = json.dumps({"tasks": tasks}, ensure_ascii=False)
    html = HTML.replace("__DATA__", payload)
    io.open(OUT, "w", encoding="utf-8").write(html)
    planned = [t["zg"] for t in tasks if t["start"] and t["end"]]
    deps = [t["zg"] for t in tasks if t["dep"]]
    print("已生成:", OUT)
    print("任务数:", len(tasks), "| 有起止排期:", planned or "无", "| 有依赖边:", deps or "无")


if __name__ == "__main__":
    main()
