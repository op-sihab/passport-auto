"""Render passport_auto.svg to PNGs (16..512) via headless Chrome, then build a
multi-resolution Windows .ico with Pillow. All local — no network, no API cost."""
import os
import subprocess
import sys
import tempfile
from PIL import Image

BASE = os.path.dirname(os.path.abspath(__file__))
SVG = os.path.join(BASE, "passport_auto.svg")
OUT = os.path.join(BASE, "icon")
os.makedirs(OUT, exist_ok=True)

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
SIZES = [16, 32, 48, 64, 128, 256, 512]


def render(size: int) -> str:
    """Render the SVG at exactly `size` px with a transparent background."""
    svg = open(SVG, encoding="utf-8").read()
    svg = svg.replace('width="512" height="512"', f'width="{size}" height="{size}"', 1)
    html = ("<!doctype html><meta charset='utf-8'>"
            "<style>html,body{margin:0;padding:0;background:transparent;"
            "overflow:hidden}svg{display:block}</style>" + svg)
    tmp_html = os.path.join(tempfile.gettempdir(), f"_icon_{size}.html")
    with open(tmp_html, "w", encoding="utf-8") as f:
        f.write(html)
    out_png = os.path.join(OUT, f"icon_{size}.png")
    prof = os.path.join(tempfile.gettempdir(), f"_iconprof_{size}")
    cmd = [
        CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
        "--no-first-run", "--no-default-browser-check", "--disable-extensions",
        f"--user-data-dir={prof}",
        "--default-background-color=00000000",
        f"--window-size={size},{size}",
        "--force-device-scale-factor=1",
        f"--screenshot={out_png}",
        "file:///" + tmp_html.replace("\\", "/"),
    ]
    subprocess.run(cmd, capture_output=True, timeout=90)
    return out_png


imgs = []
for s in SIZES:
    p = render(s)
    if not os.path.exists(p):
        print(f"  size {s}: FAILED (no screenshot)")
        continue
    im = Image.open(p).convert("RGBA")
    if im.size != (s, s):
        im = im.resize((s, s), Image.Resampling.LANCZOS)
    imgs.append(im)
    print(f"  size {s}: ok {im.size}")

if not imgs:
    sys.exit("no renders produced")

ico = os.path.join(BASE, "passport_auto.ico")
imgs[-1].save(ico, format="ICO",
              sizes=[(i.width, i.height) for i in imgs])
print("\nICO ->", ico, os.path.getsize(ico), "bytes")

imgs[-1].save(os.path.join(BASE, "passport_auto_512.png"))
print("PNG ->", os.path.join(BASE, "passport_auto_512.png"))
