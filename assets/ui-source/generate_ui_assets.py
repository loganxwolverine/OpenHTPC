#!/usr/bin/env python3
"""Generate original OPENHTPC public-candidate UI assets from primitives.

Copyright 2026 OPENHTPC contributors
Licensed under the Apache License, Version 2.0.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "assets" / "ui"
WHITE = (244, 248, 255, 255)
CYAN = (70, 210, 230, 255)
BLUE = (70, 125, 230, 255)
GOLD = (244, 184, 70, 255)
VIOLET = (155, 105, 230, 255)
MUTED = (135, 160, 180, 255)

SPECS = {
    "affichage.png": ((512, 512), "display"),
    "audio.png": ((512, 512), "audio"),
    "compatibilite_video.png": ((600, 600), "video"),
    "diagnostic.png": ((512, 512), "diagnostic"),
    "eject.png": ((768, 768), "eject"),
    "folder.png": ((768, 768), "folder"),
    "logodvd.png": ((1299, 709), "optical-banner"),
    "media.png": ((768, 768), "media"),
    "media_optique.png": ((512, 512), "media-optical"),
    "optical-bluray.png": ((768, 768), "optical-blue"),
    "optical-dvd.png": ((768, 768), "optical-gold"),
    "optical-empty.png": ((768, 768), "optical-empty"),
    "optical-uhd.png": ((768, 768), "optical-violet"),
    "power.png": ((768, 768), "power"),
    "quit.png": ((768, 768), "exit"),
    "retour.png": ((980, 984), "back"),
    "system-audio.png": ((512, 512), "audio"),
    "system-back.png": ((980, 984), "back"),
    "system-diagnostics.png": ((512, 512), "diagnostic"),
    "system-display.png": ((512, 512), "display"),
    "system-media-optical.png": ((512, 512), "media-optical"),
    "system-overview.png": ((513, 305), "overview"),
    "system-processing.png": ((2400, 2218), "processing"),
    "system-video.png": ((600, 600), "video"),
    "traitement_video.png": ((2400, 2218), "processing"),
    "vue_ensemble.png": ((513, 305), "overview"),
}

def line(draw, points, fill, width):
    draw.line(points, fill=fill, width=max(1, width), joint="curve")

def disc(draw, cx, cy, radius, color, rings=1):
    w = max(5, radius // 12)
    draw.ellipse((cx-radius, cy-radius, cx+radius, cy+radius), outline=color, width=w)
    draw.ellipse((cx-radius//6, cy-radius//6, cx+radius//6, cy+radius//6), outline=WHITE, width=w)
    for n in range(1, rings):
        rr = radius * (n + 1) // (rings + 1)
        draw.arc((cx-rr, cy-rr, cx+rr, cy+rr), 205, 335, fill=color, width=max(3, w//2))

def font(size):
    source = ROOT / "flex/assets/fonts/OpenSans-Regular.ttf"
    return ImageFont.truetype(str(source), size=size)

def centered_text(draw, box, value, size, fill=WHITE):
    face = font(size)
    left, top, right, bottom = box
    bounds = draw.textbbox((0, 0), value, font=face)
    tw, th = bounds[2] - bounds[0], bounds[3] - bounds[1]
    draw.text(((left + right - tw) / 2, (top + bottom - th) / 2 - bounds[1]), value, font=face, fill=fill)

def render(size, kind):
    w, h = size; s = min(w, h); img = Image.new("RGBA", size, (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    sw = max(4, s // 24); cx, cy = w // 2, h // 2
    if kind == "display":
        d.rounded_rectangle((w*.14,h*.18,w*.86,h*.70), radius=s*.05, outline=CYAN, width=sw)
        line(d, [(cx,h*.70),(cx,h*.82)], WHITE, sw); line(d, [(w*.34,h*.82),(w*.66,h*.82)], WHITE, sw)
    elif kind == "audio":
        d.polygon([(w*.17,h*.42),(w*.34,h*.42),(w*.52,h*.25),(w*.52,h*.75),(w*.34,h*.58),(w*.17,h*.58)], fill=WHITE)
        d.arc((w*.43,h*.30,w*.78,h*.70), -55, 55, fill=CYAN, width=sw)
        d.arc((w*.38,h*.20,w*.92,h*.80), -48, 48, fill=BLUE, width=sw)
    elif kind == "video":
        d.rounded_rectangle((w*.14,h*.18,w*.86,h*.82), radius=s*.05, outline=CYAN, width=sw)
        d.polygon([(w*.40,h*.34),(w*.40,h*.66),(w*.68,h*.50)], fill=WHITE)
        for x in (.23,.77):
            for y in (.27,.50,.73): d.ellipse((w*x-sw/2,h*y-sw/2,w*x+sw/2,h*y+sw/2), fill=GOLD)
    elif kind == "diagnostic":
        line(d, [(w*.12,h*.55),(w*.28,h*.55),(w*.38,h*.30),(w*.52,h*.72),(w*.64,h*.43),(w*.88,h*.43)], CYAN, sw)
        d.ellipse((w*.15,h*.15,w*.85,h*.85), outline=WHITE, width=max(3,sw//2))
    elif kind == "eject":
        d.polygon([(cx,h*.18),(w*.22,h*.60),(w*.78,h*.60)], fill=WHITE)
        d.rounded_rectangle((w*.22,h*.70,w*.78,h*.79), radius=sw, fill=CYAN)
    elif kind == "power":
        d.arc((w*.19,h*.19,w*.81,h*.81), -48, 228, fill=CYAN, width=sw*2)
        line(d, [(cx,h*.12),(cx,h*.48)], WHITE, sw*2)
    elif kind == "exit":
        # Original OPENHTPC exit glyph: an open door frame and outgoing arrow.
        d.rounded_rectangle((w*.16,h*.16,w*.56,h*.84), radius=s*.035, outline=CYAN, width=sw)
        line(d, [(w*.31,h*.27),(w*.31,h*.73)], WHITE, sw)
        d.ellipse((w*.46,h*.48,w*.50,h*.52), fill=GOLD)
        line(d, [(w*.39,cy),(w*.84,cy)], WHITE, sw*2)
        d.polygon([(w*.84,cy),(w*.67,h*.34),(w*.67,h*.66)], fill=WHITE)
    elif kind == "folder":
        # Classic folder silhouette with a large upper tab and distinct front flap.
        d.rounded_rectangle((w*.10,h*.24,w*.54,h*.47), radius=s*.045, fill=GOLD)
        d.rounded_rectangle((w*.10,h*.34,w*.90,h*.82), radius=s*.055, fill=(32,105,145,255), outline=CYAN, width=sw)
        d.polygon([(w*.12,h*.45),(w*.88,h*.45),(w*.81,h*.79),(w*.18,h*.79)], fill=(49,151,181,255))
        line(d, [(w*.18,h*.49),(w*.82,h*.49)], WHITE, max(3,sw//2))
    elif kind == "optical-empty":
        color=MUTED
        d.rounded_rectangle((w*.17,h*.67,w*.83,h*.88), radius=s*.04, fill=(18,42,62,235), outline=WHITE, width=sw)
        disc(d,cx,int(h*.37),int(s*.29),color,1)
        d.ellipse((w*.75,h*.75,w*.80,h*.80), fill=color)
        centered_text(d,(w*.20,h*.69,w*.70,h*.86),"DISC",max(34,int(s*.11)),WHITE)
    elif kind in {"optical-gold","optical-blue","optical-violet"}:
        # Premium OPENHTPC optical family: generic disc plus original media pill.
        color={"optical-gold":GOLD,"optical-blue":CYAN,"optical-violet":VIOLET}[kind]
        label={"optical-gold":"DVD","optical-blue":"BLU-RAY","optical-violet":"UHD"}[kind]
        rings={"optical-gold":1,"optical-blue":2,"optical-violet":3}[kind]
        disc(d,cx,int(h*.34),int(s*.27),color,rings)
        d.arc((w*.25,h*.08,w*.75,h*.59),205,332,fill=WHITE,width=max(3,sw//2))
        d.rounded_rectangle((w*.10,h*.64,w*.90,h*.90),radius=s*.065,fill=(11,30,47,245),outline=color,width=sw)
        d.rounded_rectangle((w*.14,h*.69,w*.31,h*.85),radius=s*.08,outline=WHITE,width=max(3,sw//2))
        d.ellipse((w*.195,h*.745,w*.255,h*.805),outline=color,width=max(3,sw//3))
        text_size=max(38,int(s*(.072 if label == "BLU-RAY" else .115)))
        centered_text(d,(w*.33,h*.67,w*.86,h*.87),label,text_size,WHITE)
        d.rounded_rectangle((w*.19,h*.915,w*.81,h*.94),radius=s*.012,fill=color)
    elif kind == "media":
        d.rounded_rectangle((w*.14,h*.23,w*.86,h*.77), radius=s*.05, outline=CYAN, width=sw)
        d.polygon([(w*.39,h*.36),(w*.39,h*.64),(w*.66,h*.50)], fill=WHITE)
    elif kind == "media-optical":
        d.rounded_rectangle((w*.10,h*.25,w*.62,h*.72), radius=s*.04, outline=CYAN, width=sw)
        d.polygon([(w*.29,h*.37),(w*.29,h*.60),(w*.48,h*.485)], fill=WHITE)
        disc(d,int(w*.72),int(h*.60),int(s*.17),GOLD,1)
    elif kind == "back":
        d.arc((w*.25,h*.24,w*.86,h*.80), 205, 355, fill=CYAN, width=sw*2)
        d.polygon([(w*.12,h*.46),(w*.46,h*.18),(w*.46,h*.74)], fill=WHITE)
    elif kind == "overview":
        for x,y,c in ((.28,.36,CYAN),(.50,.36,BLUE),(.72,.36,GOLD),(.39,.68,VIOLET),(.61,.68,CYAN)):
            d.rounded_rectangle((w*x-s*.08,h*y-s*.08,w*x+s*.08,h*y+s*.08),radius=s*.025,fill=c)
    elif kind == "processing":
        for rr,c in ((.31,CYAN),(.21,WHITE),(.10,GOLD)):
            d.ellipse((cx-s*rr,cy-s*rr,cx+s*rr,cy+s*rr),outline=c,width=sw)
        for a in range(0,360,45):
            import math
            x1=cx+math.cos(math.radians(a))*s*.34; y1=cy+math.sin(math.radians(a))*s*.34
            x2=cx+math.cos(math.radians(a))*s*.43; y2=cy+math.sin(math.radians(a))*s*.43
            line(d,[(x1,y1),(x2,y2)],BLUE,sw)
    elif kind == "optical-banner":
        disc(d,int(w*.27),cy,int(s*.30),GOLD,2)
        d.arc((w*.11,h*.18,w*.43,h*.82),205,332,fill=WHITE,width=max(3,sw//2))
        d.rounded_rectangle((w*.48,h*.24,w*.93,h*.76),radius=s*.075,fill=(11,30,47,245),outline=GOLD,width=sw)
        d.rounded_rectangle((w*.52,h*.34,w*.65,h*.66),radius=s*.05,outline=WHITE,width=max(3,sw//2))
        d.ellipse((w*.56,h*.44,w*.61,h*.54),outline=GOLD,width=max(3,sw//3))
        centered_text(d,(w*.66,h*.28,w*.90,h*.68),"DVD",max(48,int(s*.17)),WHITE)
        d.rounded_rectangle((w*.56,h*.79,w*.87,h*.82),radius=s*.012,fill=GOLD)
    return img

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (size, kind) in SPECS.items():
        image = render(size, kind)
        if name == "logodvd.png":
            image.save(OUT / name, compress_level=6)
        else:
            image.save(OUT / name, optimize=True)

if __name__ == "__main__":
    main()
