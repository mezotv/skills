# /// script
# dependencies = ["pillow"]
# ///
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

EMOJI, OUT = sys.argv[1], sys.argv[2]
font = ImageFont.truetype("/System/Library/Fonts/Apple Color Emoji.ttc", 160)
img = Image.new("RGBA", (200, 200))
ImageDraw.Draw(img).text((100, 100), EMOJI, font=font, embedded_color=True, anchor="mm")
img = img.crop(img.getbbox())
pad = 12
canvas = Image.new("RGBA", (img.width + 2 * pad, img.height + 2 * pad))
canvas.paste(img, (pad, pad))
alpha = canvas.getchannel("A").point(lambda v: 255 if v > 40 else 0).filter(ImageFilter.MaxFilter(13))
sticker = Image.new("RGBA", canvas.size, (255, 255, 255, 0))
sticker.putalpha(alpha)
sticker.alpha_composite(canvas)
sticker.save(OUT)
