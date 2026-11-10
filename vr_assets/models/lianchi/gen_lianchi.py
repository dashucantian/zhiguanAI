# -*- coding: utf-8 -*-
"""程序化生成「莲池夜观」观想模型（纯 Python+PIL，零出网）。先方案后代码之代码面。"""
import json, struct, math, os, random, shutil
from PIL import Image

_here = os.path.abspath(__file__)
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(_here))))
OUT_DIR = os.path.join(ROOT, "output", "20261111_莲池生成")
TEX = 1024

random.seed(42)

# ---------- 几何累积器 ----------
class Mesh:
    def __init__(self):
        self.pos=[]; self.nor=[]; self.col=[]; self.uv=[]; self.idx=[]
    def vert(self,p,n,c,uv=(0,0)):
        self.pos.append(p); self.nor.append(n); self.col.append(c); self.uv.append(uv)
        return len(self.pos)-1
    def tri(self,a,b,c):
        self.idx.append((a,b,c))

water = Mesh()
plants = Mesh()

# ---------- 夜水盘 ----------
RINGS, SEGS = 64, 128
RAD = 1.0
grid={}
for r in range(RINGS+1):
    rr = RAD*r/RINGS
    for s in range(SEGS):
        th = 2*math.pi*s/SEGS
        x=rr*math.cos(th); z=rr*math.sin(th)
        y = 0.012*math.sin(rr*22.0)* (1.0-rr/RAD)
        u=0.5+0.5*x/RAD; v=0.5+0.5*z/RAD
        grid[(r,s)]=water.vert((x,y,z),(0,1,0),(1,1,1),(u,v))
for r in range(RINGS):
    for s in range(SEGS):
        a=grid[(r,s)]; b=grid[(r,s+1 if s+1<SEGS else 0)]
        c=grid[(r+1,s)]; d=grid[(r+1,s+1 if s+1<SEGS else 0)]
        water.tri(a,c,b); water.tri(b,c,d)

# ---------- 莲叶（带缺口浮叶） ----------
def leaf(cx,cz,rad,rot):
    segs=24; notch=0.5
    center=plants.vert((cx,0.03,cz),(0,1,0),(0.10,0.30,0.14))
    ring=[]
    for i in range(segs+1):
        t=notch/2 + (2*math.pi-notch)*i/segs + rot
        x=cx+rad*math.cos(t); z=cz+rad*math.sin(t)
        y=0.03+0.02*math.sin(math.pi*i/segs)
        g=0.28+0.10*math.sin(i*1.7)
        ring.append(plants.vert((x,y,z),(0,1,0),(0.08,g,0.15)))
    for i in range(segs):
        plants.tri(center,ring[i],ring[i+1])

for (cx,cz,rad) in [(-0.45,0.2,0.22),(0.4,0.35,0.26),(0.15,-0.45,0.2),
                    (-0.3,-0.4,0.24),(0.6,-0.1,0.18),(-0.6,-0.05,0.17),(0.0,0.55,0.2)]:
    leaf(cx,cz,rad,random.uniform(0,6.28))

# ---------- 莲花（层叠花瓣） ----------
def flower(cx,cz,scale):
    base_y=0.05
    # 花心
    cy=base_y+0.10*scale
    c0=plants.vert((cx,cy,cz),(0,1,0),(0.95,0.8,0.2))
    whorls=[(8,0.16,0.10,(0.95,0.6,0.7)),(6,0.11,0.14,(0.98,0.8,0.85))]
    for (count,plen,pup,col) in whorls:
        for k in range(count):
            th=2*math.pi*k/count + (0.3 if count==6 else 0)
            dx,dz=math.cos(th),math.sin(th)
            px,pz=-dz,dx
            along,across=4,1
            vids=[]
            for a in range(along+1):
                t=a/along
                w=math.sin(math.pi*t)*0.05*scale
                for sgn in (-1,1):
                    x=cx+dx*plen*scale*t + px*w*sgn
                    z=cz+dz*plen*scale*t + pz*w*sgn
                    y=base_y + pup*scale*math.sin(math.pi*t*0.9)+0.02*t
                    vids.append(plants.vert((x,y,z),(0,1,0),col))
            for a in range(along):
                i0=a*2; i1=i0+1; i2=i0+2; i3=i0+3
                plants.tri(vids[i0],vids[i2],vids[i1]); plants.tri(vids[i1],vids[i2],vids[i3])
            plants.tri(c0,vids[0],vids[1])

for (cx,cz,sc) in [(0.0,0.0,1.2),(-0.45,0.2,0.8),(0.4,0.35,0.9),(0.15,-0.45,0.7),(-0.3,-0.4,0.8)]:
    flower(cx,cz,sc)

# ---------- 水面贴图（夜水+月影+涟漪） ----------
img=Image.new("RGB",(TEX,TEX))
px=img.load()
for j in range(TEX):
    for i in range(TEX):
        x=(i/TEX-0.5)*2; y=(j/TEX-0.5)*2
        r=math.sqrt(x*x+y*y)
        # 深蓝夜水
        b=18+10*max(0.0,1-r)
        g=10+8*max(0.0,1-r)
        rr=6+4*max(0.0,1-r)
        # 涟漪环
        ring=0.5+0.5*math.sin(r*40)
        add=6*ring*max(0.0,1-r)
        # 中心月影亮斑
        moon=math.exp(-((x-0.05)**2+(y+0.05)**2)/0.02)
        m=120*moon
        n=random.uniform(-3,3)
        px[i,j]=(int(min(255,rr+add+m+n)),int(min(255,g+add+m+n)),int(min(255,b+add*1.5+m+n)))
import io
tb=io.BytesIO(); img.save(tb,format="PNG"); tex_bytes=tb.getvalue()

# ---------- GLB 打包 ----------
blobs=[]; bufferViews=[]; accessors=[]
def add_view(data,target=None):
    # align 4
    off=sum(len(b) for b in blobs)
    pad=(-off)%4
    if pad: blobs.append(b"\0"*pad); off+=pad
    bufferViews.append({"buffer":0,"byteOffset":off,"byteLength":len(data),**({"target":target} if target else {})})
    blobs.append(data)
    return len(bufferViews)-1
def add_acc(view,ctype,count,typ,minmax=None):
    a={"bufferView":view,"componentType":ctype,"count":count,"type":typ}
    if minmax: a["min"],a["max"]=minmax
    accessors.append(a); return len(accessors)-1

def pack_mesh(m,use_uv):
    pos=b"".join(struct.pack("<3f",*p) for p in m.pos)
    nor=b"".join(struct.pack("<3f",*n) for n in m.nor)
    col=b"".join(struct.pack("<3f",*c) for c in m.col)
    idx=b"".join(struct.pack("<3I",*t) for t in m.idx)
    mn=[min(p[k] for p in m.pos) for k in range(3)]; mx=[max(p[k] for p in m.pos) for k in range(3)]
    vp=add_view(pos,34962); vn=add_view(nor,34962); vc=add_view(col,34962); vi=add_view(idx,34963)
    ap=add_acc(vp,5126,len(m.pos),"VEC3",(mn,mx))
    an=add_acc(vn,5126,len(m.nor),"VEC3")
    ac=add_acc(vc,5126,len(m.col),"VEC3")
    ai=add_acc(vi,5125,len(m.idx)*3,"SCALAR")
    attrs={"POSITION":ap,"NORMAL":an,"COLOR_0":ac}
    if use_uv:
        uv=b"".join(struct.pack("<2f",*u) for u in m.uv)
        vu=add_view(uv,34962); attrs["TEXCOORD_0"]=add_acc(vu,5126,len(m.uv),"VEC2")
    return {"attributes":attrs,"indices":ai}

prim_water=pack_mesh(water,True)
prim_plants=pack_mesh(plants,False)
prim_water["material"]=0; prim_plants["material"]=1

tex_view=add_view(tex_bytes)
bin_data=b"".join(blobs)
pad=(-len(bin_data))%4
if pad: bin_data+=b"\0"*pad

gltf={
 "asset":{"version":"2.0","generator":"zhiguan-W1-procedural-lianchi"},
 "scene":0,"scenes":[{"nodes":[0,1]}],
 "nodes":[{"mesh":0,"name":"night-water"},{"mesh":1,"name":"lotus"}],
 "meshes":[{"primitives":[prim_water]},{"primitives":[prim_plants]}],
 "materials":[
   {"name":"night-water","pbrMetallicRoughness":{"baseColorTexture":{"index":0},"metallicFactor":0.6,"roughnessFactor":0.25}},
   {"name":"lotus","pbrMetallicRoughness":{"baseColorFactor":[1,1,1,1],"metallicFactor":0.0,"roughnessFactor":0.7}}],
 "textures":[{"sampler":0,"source":0}],
 "samplers":[{"magFilter":9729,"minFilter":9729,"wrapS":10497,"wrapT":10497}],
 "images":[{"bufferView":tex_view,"mimeType":"image/png"}],
 "accessors":accessors,"bufferViews":bufferViews,
 "buffers":[{"byteLength":len(bin_data)}],
}
json_bytes=json.dumps(gltf,separators=(",",":")).encode("utf-8")
json_bytes+=b" " * ((-len(json_bytes))%4)
total=12+8+len(json_bytes)+8+len(bin_data)
glb=struct.pack("<4sII",b"glTF",2,total)
glb+=struct.pack("<I4s",len(json_bytes),b"JSON")+json_bytes
glb+=struct.pack("<I4s",len(bin_data),b"BIN\0")+bin_data

os.makedirs(OUT_DIR,exist_ok=True)
gen_path=os.path.join(OUT_DIR,"lianchi_gen.glb")
open(gen_path,"wb").write(glb)

tris=len(water.idx)+len(plants.idx)
print(json.dumps({"字节":len(glb),"tris":tris,"贴图":1,"贴图字节":len(tex_bytes),
  "water_verts":len(water.pos),"plants_verts":len(plants.pos),"产物":gen_path},ensure_ascii=False))

# 备份占位＋落 lianchi 路径（可逆）
target=os.path.join(ROOT,"vr_assets","models","lianchi","lianchi.glb")
bak=os.path.join(ROOT,"_analysis_tmp","lianchi_placeholder_backup.glb")
if os.path.exists(target) and not os.path.exists(bak):
    shutil.copyfile(target,bak)
shutil.copyfile(gen_path,target)
print("已落",target,"备份",bak)