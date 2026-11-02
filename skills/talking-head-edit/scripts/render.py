# /// script
# dependencies = ["pillow"]
# ///
import json
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

PROJECT, OUT = os.path.abspath(sys.argv[1]), sys.argv[2]
W, H, FPS, CRF = int(sys.argv[3]), int(sys.argv[4]), sys.argv[5], sys.argv[6]
RATE = sys.argv[7:]
HERE = os.path.dirname(os.path.abspath(__file__))
S = W / 1080
EDIT = json.load(open(os.path.join(PROJECT, "edit.json")))
SOURCES = EDIT["sources"]
KEEP = [tuple(k) for k in EDIT["keep"]]
CARDS = EDIT.get("cards", [])
SPRITE = EDIT.get("sprite")
LOOK = subprocess.run(
    ["bash", os.path.join(HERE, "looks.sh"), EDIT.get("look", "film")],
    env={**os.environ, "SMOOTH_S": f"{8 * S:.0f}", "SKIN_KEY": EDIT.get("skin_key", "0xE2A096")},
    capture_output=True, text=True, check=True,
).stdout.strip()
TAG = os.path.splitext(os.path.basename(OUT))[0]
HOLD, FADE = 0.12, 0.16
GAP = 2 * HOLD - FADE
RED = "#FF4D4D"
asset = lambda name: os.path.join(PROJECT, name)


def to_out(src, t):
    acc = 0.0
    for s, a, b in KEEP:
        if s == src and t <= b:
            return acc + max(t, a) - a
        acc += b - a + GAP
    raise ValueError((src, t))


CAPTIONS = sorted(json.load(open(asset("captions.json"))), key=lambda c: to_out(c.get("src", 0), c["start"]))
TOTAL = sum(b - a for _, a, b in KEEP) + GAP * (len(KEEP) - 1)

font = ImageFont.truetype(asset(EDIT.get("font", "Satoshi-Variable.ttf")), round(84 * S))
font.set_variation_by_name("Black")


def wrap(text, draw):
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial.replace("~", ""), font=font) > 860 * S and cur:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    return lines + [cur]


n_src = len(SOURCES)
SPRITE_IN = 2 * n_src
FIRST_CARD = SPRITE_IN + (1 if SPRITE else 0)
FIRST_CAP = FIRST_CARD + len(CARDS)
inputs, filters, prev = [], [], "[v]"
sprite_path = None
for i, cap in enumerate(CAPTIONS):
    a = to_out(cap.get("src", 0), cap["start"])
    b = to_out(CAPTIONS[i + 1].get("src", 0), CAPTIONS[i + 1]["start"]) if i + 1 < len(CAPTIONS) else TOTAL + 1
    text = cap["text"]
    img = Image.new("RGBA", (W, H))
    draw = ImageDraw.Draw(img)
    lines = wrap(text, draw)
    y = (1330 - len(lines) * 50) * S
    for line in lines:
        x = W / 2 - draw.textlength(line.replace("~", ""), font=font) / 2
        for j, word in enumerate(line.split()):
            text_word = word.replace("~", "") + (" " if j < len(line.split()) - 1 else "")
            draw.text((x, y + font.getmetrics()[0]), text_word, font=font, fill=RED if "~" in word else "white", anchor="ls", stroke_width=round(7 * S), stroke_fill="black")
            if SPRITE and text == SPRITE["caption"] and word.strip(",.") == SPRITE["word"]:
                sprite_path = (x, x + draw.textlength(word, font=font), y + font.getmetrics()[0] * 0.55, a, b)
            x += draw.textlength(text_word, font=font)
        y += 106 * S
    path = os.path.join(PROJECT, f"cap-{TAG}-{i:02d}.png")
    img.save(path)
    inputs += ["-i", path]
    filters.append(f"{prev}[{FIRST_CAP + i}:v]overlay=enable='between(t,{a:.3f},{b - 0.001:.3f})'[c{i}]")
    prev = f"[c{i}]"

if SPRITE:
    sx0, sx1, sy, sa, sb = sprite_path
    size = round(80 * S)
    filters.append(
        f"[{SPRITE_IN}:v]scale={size}:-1,format=rgba,rotate=a='PI/2+0.14*sin(45*t)':c=none:ow=hypot(iw\\,ih):oh=ow[sp];"
        f"{prev}[sp]overlay=x='{sx0 - size:.0f}+{sx1 - sx0 + 2 * size:.0f}*(t-{sa:.3f})/{sb - sa:.3f}-overlay_w/2':"
        f"y='{sy:.0f}-overlay_h/2+{3 * S:.1f}*sin(70*t)':enable='between(t,{sa:.3f},{sb:.3f})'[csp]"
    )
    prev = "[csp]"

for k, card in enumerate(CARDS):
    la, lb = to_out(card["src"], card["start"]), to_out(card["src"], card["end"])
    filters.append(
        f"[{FIRST_CARD + k}:v]scale=iw*{S * 0.95:.3f}:-1,format=rgba,fade=t=in:st={la:.3f}:d=0.15:alpha=1,fade=t=out:st={lb - 0.15:.3f}:d=0.15:alpha=1[lg{k}];"
        f"{prev}[lg{k}]overlay=x=(W-w)/2:y={330 * S:.0f}:enable='between(t,{la:.3f},{lb:.3f})'[clg{k}]"
    )
    prev = f"[clg{k}]"

n = len(KEEP)
segs = []
for i, (src, a, b) in enumerate(KEEP):
    vpad = (f",tpad=start_mode=clone:start_duration={HOLD}" if i else "") + (f",tpad=stop_mode=clone:stop_duration={HOLD}" if i < n - 1 else "")
    apad = (f",adelay={HOLD * 1000:.0f}:all=1" if i else "") + (f",apad=pad_dur={HOLD}" if i < n - 1 else "")
    pre = SOURCES[src].get("pre", "null")
    segs.append(f"[{src}:v]trim={a}:{b},setpts=PTS-STARTPTS,fps={FPS},scale={W}:{H}:flags=lanczos,format=yuv420p,{pre},format=yuv420p{vpad}[v{i}];")
    segs.append(f"[{n_src + src}:a:0]atrim={a}:{b},asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo{apad}[a{i}];")
length = KEEP[0][2] - KEEP[0][1] + HOLD
vchain, achain = "[v0]", "[a0]"
for i in range(1, n):
    _, a, b = KEEP[i]
    seg_len = b - a + HOLD + (HOLD if i < n - 1 else 0)
    segs.append(f"{vchain}[v{i}]xfade=transition=fade:duration={FADE}:offset={length - FADE:.3f}[vx{i}];")
    segs.append(f"{achain}[a{i}]acrossfade=d={FADE}:c1=tri:c2=tri[ax{i}];")
    vchain, achain = f"[vx{i}]", f"[ax{i}]"
    length += seg_len - FADE
graph = (
    "".join(segs)
    + f"{vchain}{LOOK},format=rgb24[v];"
    + ";".join(filters)
    + f";{prev}scale=out_color_matrix=bt709:out_range=tv,format=yuv420p[out];"
    + f"{achain}anull[aout]"
)

loop = lambda name: ["-loop", "1", "-framerate", FPS, "-t", f"{TOTAL:.3f}", "-i", asset(name)]
subprocess.run(
    ["ffmpeg", "-v", "error", "-stats", "-y",
     *[x for s in SOURCES for x in ("-i", asset(s["video"]))],
     *[x for s in SOURCES for x in ("-i", asset(s["audio"]))],
     *(loop(SPRITE["image"]) if SPRITE else []),
     *[x for c in CARDS for x in loop(c["image"])],
     *inputs, "-filter_complex", graph,
     "-map", "[out]", "-map", "[aout]",
     "-c:v", "libx264", "-preset", "slow", "-crf", CRF, *RATE, "-profile:v", "high", "-level", "5.2" if W > 1920 else "4.2",
     "-r", FPS, "-g", str(int(FPS) * 2), "-x264-params", "aq-mode=3",
     "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
     "-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-movflags", "+faststart", OUT],
    check=True,
)
