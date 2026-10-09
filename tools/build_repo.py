#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a beautified Sileo/Zebra APT repo from debs/.
Reads the Packages file produced by dpkg-scanpackages, then:
  - generates a 120x120 rounded icon per package
  - generates a 1023x575 featured banner per package
  - generates a native Sileo depiction (json) + web depiction (html)
  - injects Icon / Depiction / SileoDepiction fields into Packages
  - builds featured.json / sileo-featured.json
  - builds a dark, modern index.html landing page
Optional per-package overrides live in meta/<pkgid>.json:
  { "tagline": "...", "long": "markdown", "changelog": "markdown", "color": "#4ea1ff" }
"""
import os, json, hashlib, colorsys, html
from PIL import Image, ImageDraw, ImageFont, ImageFilter

BASE   = "https://judegor1129.github.io/repo"
ROOT   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKGS   = os.path.join(ROOT, "Packages")
ICONS  = os.path.join(ROOT, "icons")
BANNERS= os.path.join(ROOT, "banners")
DEPS   = os.path.join(ROOT, "depictions")
META   = os.path.join(ROOT, "meta")
for d in (ICONS, BANNERS, DEPS):
    os.makedirs(d, exist_ok=True)

FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/System/Library/Fonts/PingFang.ttc",
]
def font(size):
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            try: return ImageFont.truetype(p, size)
            except Exception: pass
    return ImageFont.load_default()

# ---------- parse Packages ----------
def parse_packages(text):
    stanzas, cur, lastkey = [], {}, None
    for line in text.split("\n"):
        if not line.strip():
            if cur: stanzas.append(cur); cur, lastkey = {}, None
            continue
        if line[0] in " \t" and lastkey:
            cur[lastkey] += "\n" + line.strip(); continue
        if ":" in line:
            k, v = line.split(":", 1)
            cur[k.strip()] = v.strip(); lastkey = k.strip()
    if cur: stanzas.append(cur)
    return stanzas

def dump_stanza(d, order):
    keys = [k for k in order if k in d] + [k for k in d if k not in order]
    return "\n".join(f"{k}: {d[k]}" for k in keys)

ORDER = ["Package","Name","Version","Architecture","Section","Maintainer","Author",
         "Depends","Installed-Size","Description","Icon","Depiction","SileoDepiction",
         "Tag","Filename","Size","MD5sum","SHA1","SHA256"]

# ---------- colors ----------
def colors_for(pid, override=None):
    if override:
        base = override.lstrip("#")
        r,g,b = int(base[0:2],16),int(base[2:4],16),int(base[4:6],16)
        h,s,v = colorsys.rgb_to_hsv(r/255,g/255,b/255)
    else:
        h = int(hashlib.md5(pid.encode()).hexdigest(), 16) % 360 / 360.0
        s, v = 0.55, 0.95
    c1 = tuple(int(x*255) for x in colorsys.hsv_to_rgb(h, s, v))
    c2 = tuple(int(x*255) for x in colorsys.hsv_to_rgb((h+0.08)%1.0, min(s+0.2,1), v*0.6))
    return c1, c2

def hexc(c): return "#%02x%02x%02x" % c

def gradient(w, h, c1, c2):
    base = Image.new("RGB", (w, h), c1)
    top  = Image.new("RGB", (w, h), c2)
    mask = Image.new("L", (w, h))
    md = mask.load()
    for y in range(h):
        for x in range(0, w, 4):
            v = int(255 * ((x + y) / (w + h)))
            for dx in range(4):
                if x+dx < w: md[x+dx, y] = v
    base.paste(top, (0,0), mask)
    return base

def rounded(img, rad):
    w,h = img.size
    mask = Image.new("L",(w,h),0)
    ImageDraw.Draw(mask).rounded_rectangle([0,0,w,h], rad, fill=255)
    out = Image.new("RGBA",(w,h),(0,0,0,0))
    out.paste(img,(0,0),mask)
    return out

# ---------- asset generation ----------
def make_icon(pid, name, c1, c2):
    path = os.path.join(ICONS, pid + ".png")
    g = gradient(240,240,c1,c2)
    d = ImageDraw.Draw(g)
    ch = next((x for x in name if x.strip()), "?")
    f = font(140)
    try:
        bb = d.textbbox((0,0), ch, font=f); tw,th = bb[2]-bb[0], bb[3]-bb[1]
        d.text(((240-tw)/2-bb[0], (240-th)/2-bb[1]), ch, font=f, fill=(255,255,255))
    except Exception:
        d.text((90,70), ch, fill=(255,255,255))
    rounded(g.resize((120,120), Image.LANCZOS), 27).save(path)

def make_banner(pid, name, author, c1, c2):
    path = os.path.join(BANNERS, pid + ".png")
    W,H = 1023,575
    g = gradient(W,H,c1,c2).convert("RGBA")
    # soft glow circle
    glow = Image.new("RGBA",(W,H),(0,0,0,0))
    ImageDraw.Draw(glow).ellipse([W-520,-200,W+120,440], fill=(255,255,255,28))
    g = Image.alpha_composite(g, glow.filter(ImageFilter.GaussianBlur(60)))
    d = ImageDraw.Draw(g)
    # icon tile
    ic = gradient(300,300,(255,255,255),c1)
    ic = Image.blend(ic, Image.new("RGB",(300,300),c2), 0.0)
    icd = ImageDraw.Draw(ic)
    ch = next((x for x in name if x.strip()), "?")
    f = font(170)
    try:
        bb = icd.textbbox((0,0),ch,font=f); tw,th=bb[2]-bb[0],bb[3]-bb[1]
        icd.text(((300-tw)/2-bb[0],(300-th)/2-bb[1]),ch,font=f,fill=hexc(c2))
    except Exception: pass
    g.paste(rounded(ic,66),(70,138),rounded(ic,66))
    fa = font(40)
    # auto-fit title into available width
    avail = W - 420 - 50
    size = 80
    disp = name if len(name) <= 22 else name[:21]+"…"
    while size > 34:
        fn = font(size)
        bb = d.textbbox((0,0), disp, font=fn)
        if bb[2]-bb[0] <= avail: break
        size -= 4
    fn = font(size)
    d.text((420, 258-size//2), disp, font=fn, fill=(255,255,255))
    d.text((422,320), author or "", font=fa, fill=(255,255,255,220))
    g.convert("RGB").save(path)

def build_depiction(p, c1, meta):
    pid, name = p["Package"], p.get("Name", p["Package"])
    author = p.get("Author", p.get("Maintainer",""))
    ver, sec = p.get("Version",""), p.get("Section","Tweaks")
    desc = p.get("Description","").replace("\n"," ")
    tint = meta.get("color", hexc(c1))
    tagline = meta.get("tagline", desc)
    longmd  = meta.get("long", desc)
    changelog = meta.get("changelog", f"### {ver}\n\n首次收录到源。")
    banner = f"{BASE}/banners/{pid}.png"
    dep = {
        "minVersion":"0.1","class":"DepictionTabView","headerImage":banner,"tintColor":tint,
        "tabs":[
            {"tabname":"详情","class":"DepictionStackView","views":[
                {"class":"DepictionSubheaderView","title":tagline},
                {"class":"DepictionMarkdownView","markdown":longmd},
                {"class":"DepictionSpacerView","spacing":12},
                {"class":"DepictionHeaderView","title":"信息"},
                {"class":"DepictionTableTextView","title":"开发者","text":author},
                {"class":"DepictionTableTextView","title":"版本","text":ver},
                {"class":"DepictionTableTextView","title":"标识符","text":pid},
                {"class":"DepictionTableTextView","title":"区段","text":sec},
                {"class":"DepictionSpacerView","spacing":8},
                {"class":"DepictionLabelView","text":"来自 Jude's Repo","textColor":"#888888","fontSize":12,"alignment":1}
            ]},
            {"tabname":"更新","class":"DepictionStackView","views":[
                {"class":"DepictionMarkdownView","markdown":changelog}
            ]}
        ]
    }
    with open(os.path.join(DEPS, pid+".json"),"w",encoding="utf-8") as f:
        json.dump(dep,f,ensure_ascii=False,indent=2)
    # web depiction (Zebra/Cydia fallback)
    htmlpage = f"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{{margin:0;font-family:-apple-system,sans-serif;background:#0d0d10;color:#eee}}
.hero{{background:linear-gradient(135deg,{hexc(c1)},{tint});padding:28px 20px}}
.hero h1{{margin:0;font-size:24px}}.hero p{{margin:4px 0 0;opacity:.85}}
.body{{padding:20px}}.k{{color:#8aa;font-size:13px}}.r{{display:flex;justify-content:space-between;
padding:10px 0;border-bottom:1px solid #222}}</style></head>
<body><div class="hero"><h1>{html.escape(name)}</h1><p>{html.escape(author)} · v{html.escape(ver)}</p></div>
<div class="body"><p>{html.escape(longmd)}</p>
<div class="r"><span class="k">标识符</span><span>{html.escape(pid)}</span></div>
<div class="r"><span class="k">区段</span><span>{html.escape(sec)}</span></div>
<div class="r"><span class="k">来源</span><span>Jude's Repo</span></div></div></body></html>"""
    with open(os.path.join(DEPS, pid+".html"),"w",encoding="utf-8") as f:
        f.write(htmlpage)

# ---------- main ----------
def main():
    text = open(PKGS, encoding="utf-8").read()
    pkgs = parse_packages(text)
    cards, banners = [], []
    for p in pkgs:
        pid = p["Package"]; name = p.get("Name", pid)
        author = p.get("Author", p.get("Maintainer",""))
        meta = {}
        mp = os.path.join(META, pid+".json")
        if os.path.exists(mp):
            meta = json.load(open(mp, encoding="utf-8"))
        c1,c2 = colors_for(pid, meta.get("color"))
        if not os.path.exists(os.path.join(ICONS,pid+".png")):   make_icon(pid,name,c1,c2)
        if not os.path.exists(os.path.join(BANNERS,pid+".png")): make_banner(pid,name,author,c1,c2)
        build_depiction(p, c1, meta)
        p["Icon"]           = f"{BASE}/icons/{pid}.png"
        p["SileoDepiction"] = f"{BASE}/depictions/{pid}.json"
        p["Depiction"]      = f"{BASE}/depictions/{pid}.html"
        tag = meta.get("tagline", p.get("Description","").replace("\n"," "))
        cards.append((pid,name,author,p.get("Version",""),tag,hexc(c1),hexc(c2)))
        banners.append({"title":name,"package":pid,"url":f"{BASE}/banners/{pid}.png","hideShadow":False})

    # rewrite Packages
    out = "\n\n".join(dump_stanza(p, ORDER) for p in pkgs) + "\n"
    open(PKGS,"w",encoding="utf-8").write(out)

    # featured carousels
    feat = {"class":"FeaturedBannersView","itemCornerRadius":12,
            "itemSize":"{263, 148}","banners":banners}
    for fn in ("sileo-featured.json","featured.json"):
        json.dump(feat, open(os.path.join(ROOT,fn),"w",encoding="utf-8"),
                  ensure_ascii=False, indent=2)

    # index.html
    card_html = "\n".join(f"""
      <a class="card" href="depictions/{html.escape(pid)}.html" style="--c1:{c1};background:linear-gradient(135deg,{c1}26,{c2}26),#14141b">
        <img src="icons/{html.escape(pid)}.png" alt="">
        <div class="meta"><div class="n">{html.escape(name)}</div>
        <div class="a">{html.escape(author)} · v{html.escape(ver)}</div>
        <div class="t">{html.escape(tag)}</div></div></a>""" for pid,name,author,ver,tag,c1,c2 in cards)
    page = f"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Jude's Repo</title><style>
*{{box-sizing:border-box}}body{{margin:0;font-family:-apple-system,"PingFang SC",sans-serif;
background:#0b0b0f;color:#f2f2f5}}
.hd{{text-align:center;padding:64px 20px 40px;background:radial-gradient(120% 100% at 50% 0,#1b2740,#0b0b0f)}}
.hd img{{width:92px;height:92px;border-radius:21px;box-shadow:0 10px 40px #0008}}
.hd h1{{margin:16px 0 4px;font-size:30px}}.hd p{{margin:0;color:#9aa}}
.btns{{display:flex;gap:10px;justify-content:center;flex-wrap:wrap;margin-top:22px}}
.btns a{{text-decoration:none;color:#fff;padding:11px 20px;border-radius:12px;font-weight:600;font-size:15px}}
.sileo{{background:#2d7dff}}.zebra{{background:#d6336c}}.copy{{background:#333}}
.wrap{{max-width:860px;margin:0 auto;padding:26px 16px 70px}}
.wrap h2{{font-size:15px;color:#8aa;letter-spacing:1px;margin:10px 6px}}
.grid{{display:grid;grid-template-columns:1fr;gap:12px}}
@media(min-width:620px){{.grid{{grid-template-columns:1fr 1fr}}}}
.card{{display:flex;gap:14px;align-items:center;padding:14px;border-radius:16px;
background:#14141b;border:1px solid #ffffff10;text-decoration:none;color:inherit;transition:.15s}}
.card:hover{{transform:translateY(-2px);border-color:var(--c1)}}
.card img{{width:58px;height:58px;border-radius:14px;flex:none}}
.n{{font-weight:700;font-size:16px}}.a{{color:#9aa;font-size:12px;margin:2px 0 4px}}
.t{{color:#cfd3da;font-size:13px;line-height:1.35;
display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
.ft{{text-align:center;color:#556;font-size:12px;padding:30px}}
</style></head><body>
<div class="hd"><img src="CydiaIcon.png" alt="">
<h1>Jude's Repo</h1><p>个人越狱源 · rootless · iOS 15+</p>
<div class="btns">
  <a class="sileo" href="sileo://source/{BASE}/">添加到 Sileo</a>
  <a class="zebra" href="zbra://sources/add/{BASE}/">添加到 Zebra</a>
  <a class="copy" href="javascript:navigator.clipboard&&navigator.clipboard.writeText('{BASE}/')">复制源地址</a>
</div></div>
<div class="wrap"><h2>插件 ({len(cards)})</h2><div class="grid">{card_html}</div></div>
<div class="ft">{BASE}/</div></body></html>"""
    open(os.path.join(ROOT,"index.html"),"w",encoding="utf-8").write(page)
    print(f"built {len(pkgs)} packages, icons/banners/depictions/featured/index done")

if __name__ == "__main__":
    main()
