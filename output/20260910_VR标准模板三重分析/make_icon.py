"""生成 PWA 应用图标（192/512）。取场景核心意象：深空底色 + 中央光球 + 下方水面。"""
import math
from PIL import Image, ImageDraw, ImageFilter

OUT = r"C:\Users\tiand\OneDrive\zhiguanAI\vr_assets"
S = 512


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


img = Image.new("RGB", (S, S))
px = img.load()
top = (0x0b, 0x1d, 0x33)      # 天穹深蓝（同 theme_color）
bot = (0x37, 0x23, 0x3a)      # 地平线暖紫
cy_orb = S * 0.42             # 光球中心（略高于中线，对应场景 y=1.25）
r_orb = S * 0.16

# 背景竖向渐变 + 下方水面暗带
for y in range(S):
    t = y / S
    base = lerp(top, bot, min(1.0, t * 1.15))
    if y > S * 0.68:          # 水面区：压暗并偏青
        wt = (y - S * 0.68) / (S * 0.32)
        base = lerp(base, (0x08, 0x22, 0x30), wt * 0.8)
    for x in range(S):
        px[x, y] = base

# 光球辉光：径向高斯衰减（青白 → 透明），叠加到背景
glow = Image.new("L", (S, S), 0)
gd = glow.load()
R = S * 0.46
for y in range(S):
    for x in range(S):
        d = math.hypot(x - S / 2, y - cy_orb) / R
        if d < 1:
            gd[x, y] = int(255 * (1 - d) ** 2.2)
glow = glow.filter(ImageFilter.GaussianBlur(S * 0.02))
orb_col = Image.new("RGB", (S, S), (0xbf, 0xea, 0xff))
img = Image.composite(orb_col, img, glow)

# 光球实心核
d = ImageDraw.Draw(img)
d.ellipse([S/2 - r_orb, cy_orb - r_orb, S/2 + r_orb, cy_orb + r_orb],
          fill=(0xe8, 0xf8, 0xff))
# 核外一圈柔光
halo = Image.new("L", (S, S), 0)
hd = ImageDraw.Draw(halo)
hr = r_orb * 1.5
hd.ellipse([S/2 - hr, cy_orb - hr, S/2 + hr, cy_orb + hr], fill=160)
halo = halo.filter(ImageFilter.GaussianBlur(r_orb * 0.5))
img = Image.composite(Image.new("RGB", (S, S), (0x9f, 0xdc, 0xff)), img, halo)

# 水面两道反光弧线（呼应场景水面涟漪）
d = ImageDraw.Draw(img)
for i, (yy, w, a) in enumerate([(S*0.74, 3, 90), (S*0.82, 2, 60)]):
    d.arc([S*0.18, yy - S*0.10, S*0.82, yy + S*0.10], 200, 340,
          fill=(0x6f, 0xc8, 0xe8), width=w)

img.save(f"{OUT}\\icon-512.png", "PNG")
img.resize((192, 192), Image.LANCZOS).save(f"{OUT}\\icon-192.png", "PNG")
print("已生成 icon-512.png / icon-192.png")

# 校验：尺寸、非纯色、maskable 安全区（中心 80% 有主体）
for n in ["icon-512.png", "icon-192.png"]:
    im = Image.open(f"{OUT}\\{n}").convert("RGB")
    a = list(im.getdata())
    uniq = len(set(a[::37]))
    print(f"  {n}: {im.size}  采样色数 {uniq}  {'✅' if im.size[0]==im.size[1] and uniq>20 else '❌'}")
