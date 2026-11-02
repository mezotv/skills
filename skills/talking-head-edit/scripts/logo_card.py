# /// script
# dependencies = ["resvg-py", "pillow"]
# ///
import io
import re
import sys

import resvg_py
from PIL import Image, ImageDraw

SRC, OUT = sys.argv[1], sys.argv[2]
CARD_H, PAD_X, PAD_Y = 220, 70, 56

svg = re.search(r"<svg.*?</svg>", open(SRC).read(), re.S).group(0)
svg = svg.replace("{...props}", "").replace("clipRule", "clip-rule").replace("fillRule", "fill-rule").replace("currentColor", "#111111")
vb = [float(v) for v in re.search(r'viewBox="([^"]+)"', svg).group(1).split()]
logo_h = CARD_H - 2 * PAD_Y
logo_w = round(logo_h * vb[2] / vb[3])
png = resvg_py.svg_to_bytes(svg_string=svg, width=logo_w * 2, height=logo_h * 2)
logo = Image.open(io.BytesIO(bytes(png))).convert("RGBA").resize((logo_w, logo_h), Image.LANCZOS)
card_w = logo_w + 2 * PAD_X
card = Image.new("RGBA", (card_w + 4, CARD_H + 4))
ImageDraw.Draw(card).rounded_rectangle((2, 2, card_w + 1, CARD_H + 1), radius=44, fill="white", outline=(0, 0, 0, 40), width=2)
card.alpha_composite(logo, (PAD_X + 2, PAD_Y + 2))
card.save(OUT)
