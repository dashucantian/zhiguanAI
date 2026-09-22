# -*- coding: utf-8 -*-
"""任务看板 → 关系图 HTML 生成器（W3·2026-09-22）

用法：
  1) 先拉数据（PowerShell，输出 UTF-16/UTF-8 自适应）：
     lark-cli base +record-list --base-token X4xXbTF57acOnZs1ZzZcF4P2nJg `
       --table-id tblLf45tgSgBoLue --limit 200 --json --as user | Out-File -Encoding utf8 _records_raw.json
  2) python 生成关系图.py   （读本目录下 _records_raw.json，产出 任务关系图.html）

布局：中心=止观AI 项目 → 一级分组环（默认按「所属阶段」，可切「承担者」）→ 任务叶子。
纯静态 SVG + 原生 JS，无外部依赖，离线可开。状态着色见页内图例。
「关联原则」字段回填后，分组下拉自动出现「按原则」（多值任务在每个原则下重复出现）。
"""
import io
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "_records_raw.json")
OUT = os.path.join(HERE, "任务关系图.html")

STATUS_HUE = {
    "待启动": "#9ca3af", "进行中": "#3b82f6", "待法师审定": "#f59e0b",
    "待法师决策": "#ef4444", "已完成": "#22c55e", "已搁置": "#6b7280",
}


def load_rows():
    raw = open(SRC, "rb").read()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        txt = raw.decode("utf-16")
    else:
        txt = raw.decode("utf-8-sig")
    d = json.loads(txt)
    if not d.get("ok"):
        raise SystemExit("源数据不是成功响应，请重新拉取：" + str(d.get("error"))[:200])
    dd = d["data"]
    cols = dd["fields"]
    rows = []
    for arr in dd["data"]:
        m = dict(zip(cols, arr))
        rows.append(m)
    return rows


def cell(v):
    """字段值归一为字符串列表（人员/多选为数组，富文本可能为段列表）。"""
    if v is None:
        return []
    if isinstance(v, list):
        out = []
        for x in v:
            if isinstance(x, dict):
                out.append(x.get("text") or x.get("name") or x.get("en_name") or str(x))
            else:
                out.append(str(x))
        return out
    if isinstance(v, dict):
        return [v.get("text") or str(v)]
    return [str(v)]


def main():
    rows = load_rows()
    tasks = []
    for i, m in enumerate(rows):
        tasks.append({
            "id": i,
            "name": (cell(m.get("任务名")) or ["(无名)"])[0],
            "zg": (cell(m.get("任务编号")) or [""])[0],
            "status": (cell(m.get("状态")) or ["待启动"])[0],
            "owners": cell(m.get("承担者")),
            "stages": cell(m.get("所属阶段")),
            "criteria": (cell(m.get("验收标准")) or [""])[0],
            "files": (cell(m.get("关联文件")) or [""])[0],
            "ai": (cell(m.get("AI执行记录")) or [""])[0],
            "principles": cell(m.get("关联原则")),
        })

    def group_key(task, mode):
        if mode == "owner":
            return task["owners"] or ["(未填承担者)"]
        if mode == "principle":
            return task["principles"] or ["(未回填)"]
        return task["stages"] or ["(无阶段)"]

    data = {
        "tasks": tasks,
        "hue": STATUS_HUE,
    }
    data["count"] = len(tasks)
    data["hasPrinciple"] = any(t["principles"] for t in tasks)

    payload = json.dumps(data, ensure_ascii=False)
    html = HTML_TMPL.replace("__DATA__", payload)
    io.open(OUT, "w", encoding="utf-8").write(html)
    print("已生成:", OUT, "| 任务数:", len(tasks), "| 原则字段:", "有数据" if data["hasPrinciple"] else "空/无")


HTML_TMPL = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>止观AI 任务关系图</title>
<style>
  body{margin:0;font-family:"Microsoft YaHei",system-ui,sans-serif;background:#0f172a;color:#e2e8f0}
  #bar{position:fixed;top:0;left:0;right:0;height:52px;background:#1e293b;display:flex;align-items:center;gap:14px;padding:0 16px;z-index:10;border-bottom:1px solid #334155}
  #bar b{font-size:15px}
  select,button{background:#0f172a;color:#e2e8f0;border:1px solid #475569;border-radius:6px;padding:4px 10px;font-size:13px}
  #legend{margin-left:auto;display:flex;gap:10px;font-size:12px;align-items:center;flex-wrap:wrap}
  .lg{display:flex;align-items:center;gap:4px}
  .dot{width:10px;height:10px;border-radius:50%}
  svg{display:block;width:100vw;height:calc(100vh - 52px);margin-top:52px}
  .link{stroke:#334155;stroke-width:1}
  .gnode{cursor:pointer}
  .glabel{fill:#cbd5e1;font-size:12px;font-weight:600}
  .tnode{cursor:pointer;stroke:#0f172a;stroke-width:1.5}
  .tnode:hover{stroke:#f8fafc;stroke-width:2.5}
  #tip{position:fixed;max-width:460px;max-height:72vh;overflow:auto;background:#1e293b;border:1px solid #475569;border-radius:8px;padding:12px 14px;font-size:13px;line-height:1.55;display:none;z-index:20;box-shadow:0 8px 30px rgba(0,0,0,.5)}
  #tip h3{margin:0 0 6px;font-size:14px;color:#fbbf24}
  #tip .k{color:#94a3b8}
  #stat{font-size:12px;color:#94a3b8}
</style>
</head>
<body>
<div id="bar">
  <b>止观AI · 任务关系图</b>
  <label>分组 <select id="mode">
    <option value="stage">按阶段</option>
    <option value="owner">按承担者</option>
    <option value="principle" id="optP">按关联原则</option>
  </select></label>
  <label>状态 <select id="fstatus"><option value="">全部</option></select></label>
  <span id="stat"></span>
  <div id="legend"></div>
</div>
<svg id="svg"></svg>
<div id="tip"></div>
<script>
const DATA = __DATA__;
if (!DATA.hasPrinciple) document.getElementById('optP').disabled = true;
const S = document.getElementById('svg'), TIP = document.getElementById('tip');
const W = () => innerWidth, H = () => innerHeight - 52;
let tFilter = '';

function groupKey(t, mode){
  if(mode==='owner') return t.owners.length? t.owners : ['(未填承担者)'];
  if(mode==='principle') return t.principles.length? t.principles : ['(未回填)'];
  return t.stages.length? t.stages : ['(无阶段)'];
}

function render(){
  const mode = document.getElementById('mode').value;
  const tasks = DATA.tasks.filter(t => !tFilter || t.status===tFilter);
  const groups = {};
  tasks.forEach(t => groupKey(t,mode).forEach(g => (groups[g]=groups[g]||[]).push(t)));
  const gn = Object.keys(groups).sort((a,b)=>groups[b].length-groups[a].length);
  const cx = W()/2, cy = H()/2, r1 = Math.min(W(),H())*0.22;
  const MM = Math.min(W(),H());

  // —— 第一轮：算枢纽位置 + 叶初始位置（扇形弧）——
  const hubs = [], leaves = [];
  gn.forEach((g,i)=>{
    const a = -Math.PI/2 + i*2*Math.PI/gn.length;
    const gx = cx + r1*Math.cos(a), gy = cy + r1*Math.sin(a);
    const list = groups[g];
    hubs.push({g, gx, gy, list});
    // 弧半径随组大小外扩 + 弧展开角保证相邻叶弧长≥26px
    const r2 = r1 + MM*0.16 + list.length*6;
    const spread = Math.min(Math.PI*0.96, list.length>1 ? (list.length-1)*26/r2 : 0.3);
    list.forEach((t,j)=>{
      const frac = list.length===1? 0 : (j/(list.length-1)-0.5);
      const a2 = a + frac*spread;
      const rr = r2 + (j%3)*22;                       // 三圈错位防同弧相切
      leaves.push({t, gx, gy, gsize: list.length, ix: cx+rr*Math.cos(a2), iy: cy+rr*Math.sin(a2)});
    });
  });

  // —— 第二轮：防重叠松弛（推开<28px 的点对；每轮同步收边界/避中心，防收拢再重叠）——
  const clamp = (L)=>{
    L.ix = Math.max(14, Math.min(W()-14, L.ix));
    L.iy = Math.max(14, Math.min(H()-14, L.iy));
    const dc = Math.hypot(L.ix-cx, L.iy-cy);
    if(dc < r1*0.55){ const k=(r1*0.55)/(dc||1); L.ix = cx+(L.ix-cx)*k; L.iy = cy+(L.iy-cy)*k; }
  };
  for(let it=0; it<90; it++){
    for(let i=0;i<leaves.length;i++){
      const A = leaves[i];
      for(let k=i+1;k<leaves.length;k++){
        const B = leaves[k];
        let dx = B.ix-A.ix, dy = B.iy-A.iy;
        let d = Math.hypot(dx,dy);
        if(d < 0.5){ dx = (i-k)*0.7+0.3; dy = 0.9; d = Math.hypot(dx,dy); }  // 完全重合时给确定性扰动
        if(d < 28){
          const push = (28-d)/2, ux = dx/d, uy = dy/d;
          A.ix -= ux*push; A.iy -= uy*push;
          B.ix += ux*push; B.iy += uy*push;
        }
      }
    }
    leaves.forEach(clamp);
  }
  leaves.forEach(L=>{ L.x = L.ix; L.y = L.iy; });

  // —— 第三轮：绘制 ——
  let svg = `<g id="zoom">`;
  hubs.forEach(h=>{
    svg += `<line class="link" x1="${cx}" y1="${cy}" x2="${h.gx}" y2="${h.gy}"/>`;
  });
  leaves.forEach(L=>{
    const col = DATA.hue[L.t.status]||'#9ca3af';
    svg += `<line class="link" x1="${L.gx}" y1="${L.gy}" x2="${L.x}" y2="${L.y}"/>`;
  });
  leaves.forEach(L=>{
    const col = DATA.hue[L.t.status]||'#9ca3af';
    svg += `<circle class="tnode" cx="${L.x}" cy="${L.y}" r="7" fill="${col}" data-i="${L.t.id}"/>`;
    if(L.gsize<=14){   // 标签只给小组画，防字堆字
      svg += `<text x="${L.x+10}" y="${L.y+4}" font-size="10" fill="#94a3b8" pointer-events="none">${esc(L.t.zg||L.t.name.slice(0,10))}</text>`;
    }
  });
  hubs.forEach(h=>{
    svg += `<g class="gnode"><circle cx="${h.gx}" cy="${h.gy}" r="16" fill="#334155" stroke="#64748b"/>`;
    svg += `<text x="${h.gx}" y="${h.gy+4}" text-anchor="middle" font-size="9" fill="#fbbf24">${h.list.length}</text>`;
    svg += `<text class="glabel" x="${h.gx}" y="${h.gy-24}" text-anchor="middle">${esc(h.g.length>12? h.g.slice(0,12)+'…':h.g)}</text></g>`;
  });
  svg += `<circle cx="${cx}" cy="${cy}" r="30" fill="#7c3aed" stroke="#a78bfa" stroke-width="2"/>`;
  svg += `<text x="${cx}" y="${cy+4}" text-anchor="middle" font-size="11" fill="#fff" font-weight="700">止观AI</text></g>`;
  S.innerHTML = svg;
  document.getElementById('stat').textContent = `任务 ${tasks.length} / ${DATA.tasks.length} 条`;
  bind();
}

function esc(s){return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}

function bind(){
  let cur = null;          // 当前钉住的节点
  let hideT = null;        // 延迟隐藏定时器（防相邻节点间移动时闪断）
  S.querySelectorAll('.tnode').forEach(n=>{
    const t = DATA.tasks[+n.dataset.i];
    n.addEventListener('mouseenter',e=>{ if(hideT){clearTimeout(hideT);hideT=null;} cur=n; showTip(t,e); });
    n.addEventListener('mousemove',e=>{ if(cur===n) place(e); });
    n.addEventListener('mouseleave',()=>{ if(cur===n){ cur=null; hideT=setTimeout(()=>{TIP.style.display='none';},160); } });
  });
  // 鼠标移入卡片本身：保持显示，允许滚动翻看
  TIP.addEventListener('mouseenter',()=>{ if(hideT){clearTimeout(hideT);hideT=null;} });
  TIP.addEventListener('mouseleave',()=>{ TIP.style.display='none'; });

  function showTip(t,e){
    TIP.innerHTML = `<h3>${esc(t.zg)} ${esc(t.name)}</h3>`
      + `<div><span class="k">状态：</span>${esc(t.status)}</div>`
      + `<div><span class="k">承担者：</span>${esc(t.owners.join('、'))}</div>`
      + `<div><span class="k">阶段：</span>${esc(t.stages.join('、'))}</div>`
      + (t.principles.length?`<div><span class="k">原则：</span>${esc(t.principles.join('、'))}</div>`:'')
      + (t.criteria?`<div><span class="k">验收：</span>${esc(t.criteria)}</div>`:'')
      + (t.files?`<div><span class="k">文件：</span>${esc(t.files)}</div>`:'')
      + (t.ai?`<div style="margin-top:6px;color:#94a3b8;font-size:12px">${esc(t.ai).slice(0,800)}</div>`:'');
    TIP.style.display='block';
    place(e);
  }
  function place(e){
    const r = TIP.getBoundingClientRect();
    let x = e.clientX + 14, y = e.clientY + 14;
    if(x + r.width  > innerWidth  - 8) x = e.clientX - r.width  - 14;   // 右缘翻转
    if(y + r.height > innerHeight - 8) y = Math.max(60, e.clientY - r.height - 14); // 下缘翻转
    TIP.style.left = Math.max(8, x) + 'px';
    TIP.style.top  = Math.max(8, y) + 'px';
  }
}

// init controls
const fs=document.getElementById('fstatus');
[...new Set(DATA.tasks.map(t=>t.status))].forEach(s=>{const o=document.createElement('option');o.value=s;o.textContent=s;fs.appendChild(o);});
fs.onchange=()=>{tFilter=fs.value;render();};
document.getElementById('mode').onchange=render;
document.getElementById('legend').innerHTML = Object.entries(DATA.hue).map(([k,v])=>`<span class="lg"><span class="dot" style="background:${v}"></span>${k}</span>`).join('');
addEventListener('resize',render);
render();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
