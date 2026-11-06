"""Text-behind-subject renderer.

Big condensed caption words are composited *between* the background and the person:
  frame -> RVM person matte -> text layer over frame -> person pasted back on top.

usage: venv/bin/python render.py INPUT.mp4 CUES.json OUT.mp4 [--stills DIR] [--width-frac 0.9]

CUES.json:
{
  "style": {"font": "...ttf", "color": "#FFFFFF", "width_frac": 0.9, "max_h_frac": 0.30,
            "shadow": 0.35, "opacity": 1.0, "pop": true},
  "cues": [
    {"text": "RUN", "start": 0.0, "end": 0.8},                 # layout defaults to "behind"
    {"text": "YEAH I DO", "start": 1.0, "end": 2.0, "layout": "split"},   # words flank the head
    {"text": "K, BYE", "start": 3.0, "end": 4.0, "layout": "front", "y": 0.1, "x": 0.08,
     "size": 140, "align": "left"}                            # plain caption on top
  ]
}
Per-cue optional overrides: layout, y (0-1, top of text), x (0-1, left, only with align=left),
size (px cap height-ish font size), color, opacity, width_frac.
"""
import argparse, json, os, subprocess, sys, tempfile

import numpy as np
import onnxruntime as ort
from PIL import Image, ImageDraw, ImageFilter, ImageFont

C = os.environ.get("TBS_HOME", os.path.expanduser("~/.cache/text-behind-subject"))
DS = 4  # downsample factor for placement search


# ---------------------------------------------------------------- video io
def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,avg_frame_rate:stream_side_data=rotation:format=duration",
                          "-of", "json", path], capture_output=True, text=True, check=True).stdout
    d = json.loads(out)
    s = d["streams"][0]
    w, h = s["width"], s["height"]
    rot = 0
    for sd in s.get("side_data_list", []) or []:
        rot = int(sd.get("rotation", 0) or 0)
    if abs(rot) % 180 == 90:
        w, h = h, w
    num, den = s["avg_frame_rate"].split("/")
    fps = float(num) / float(den) if float(den) else 30.0
    return w, h, fps, float(d["format"]["duration"])


def has_audio(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                          "-of", "csv=p=0", path], capture_output=True, text=True).stdout
    return bool(out.strip())


def frames(path, w, h, fps):
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", path, "-vf", "fps=%f" % fps, "-pix_fmt", "rgb24",
                          "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
    n = w * h * 3
    while True:
        buf = p.stdout.read(n)
        if len(buf) < n:
            break
        yield np.frombuffer(buf, np.uint8).reshape(h, w, 3)
    p.wait()


# ---------------------------------------------------------------- matting
def matte_all(path, w, h, fps, tmpdir):
    sess = ort.InferenceSession(os.path.join(C, "rvm_mobilenetv3_fp32.onnx"), providers=["CPUExecutionProvider"])
    dr = np.array([min(1.0, 512 / max(w, h))], np.float32)
    rec = [np.zeros((1, 1, 1, 1), np.float32)] * 4
    mm_path = os.path.join(tmpdir, "alpha.u8")
    count = 0
    with open(mm_path, "wb") as f:
        for fr in frames(path, w, h, fps):
            src = (fr.astype(np.float32) / 255.0).transpose(2, 0, 1)[None]
            fgr, pha, *rec = sess.run(None, {"src": src, "r1i": rec[0], "r2i": rec[1], "r3i": rec[2],
                                             "r4i": rec[3], "downsample_ratio": dr})
            f.write((np.clip(pha[0, 0], 0, 1) * 255).astype(np.uint8).tobytes())
            count += 1
            if count % 30 == 0:
                print("  matte %d frames" % count, end="\r", file=sys.stderr)
    print("  matte %d frames done" % count, file=sys.stderr)
    return np.memmap(mm_path, np.uint8, "r", shape=(count, h, w))


# ---------------------------------------------------------------- text
def hex_rgb(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def text_img(text, size, font_path, color, shadow, opacity):
    """Tight RGBA image of `text` (shadow baked in). Returns (img, pad) where pad = shadow margin."""
    font = ImageFont.truetype(font_path, size)
    l, t, r, b = font.getbbox(text)
    pad = max(4, size // 12)
    im = Image.new("RGBA", (r - l + 2 * pad, b - t + 2 * pad), (0, 0, 0, 0))
    if shadow > 0:
        sh = Image.new("L", im.size, 0)
        ImageDraw.Draw(sh).text((pad - l + size // 40, pad - t + size // 30), text, font=font, fill=int(255 * shadow))
        sh = sh.filter(ImageFilter.GaussianBlur(size / 25))
        im.paste((0, 0, 0, 255), (0, 0), sh)
    txt = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(txt).text((pad - l, pad - t), text, font=font, fill=color + (255,))
    im = Image.alpha_composite(im, txt)
    if opacity < 1:
        a = np.array(im)
        a[..., 3] = (a[..., 3] * opacity).astype(np.uint8)
        im = Image.fromarray(a)
    return im, pad


def fit_size(text, font_path, max_w, max_h):
    lo, hi = 10, 2000
    while lo < hi:
        mid = (lo + hi + 1) // 2
        l, t, r, b = ImageFont.truetype(font_path, mid).getbbox(text)
        if r - l <= max_w and b - t <= max_h:
            lo = mid
        else:
            hi = mid - 1
    return lo


def mean_mask(alpha, i0, i1):
    i1 = max(i0 + 1, min(i1, len(alpha)))
    idx = np.linspace(i0, i1 - 1, num=min(8, i1 - i0)).astype(int)
    m = np.mean([alpha[i][::DS, ::DS].astype(np.float32) / 255 for i in idx], axis=0)
    return m


def char_spans(text, font_path, size, pad):
    """x-ranges (in text_img coords) of each non-space glyph."""
    font = ImageFont.truetype(font_path, size)
    l0 = font.getbbox(text)[0]
    spans = []
    for k, ch in enumerate(text):
        if ch.isspace():
            continue
        a = font.getlength(text[:k]) - l0 + pad
        spans.append((int(a), int(a + font.getlength(ch))))
    return spans


def place_behind(text, base_size, font, color, shadow, opacity, mask, W, H, cue):
    """Search scale/x/y so the subject covers some of the text (it reads as 'behind') while every
    glyph stays legible: at most len/5 glyphs may be >55% hidden (so 'DO I [HATE] IT?' is allowed,
    'R[U]N' is not). Returns (img, x, y)."""
    if "y" in cue:
        img, _ = text_img(text, base_size, font, color, shadow, opacity)
        return img, (W - img.size[0]) // 2, int(cue["y"] * H)
    P = 2000 // DS  # zero-pad the mask so text images wider than the frame still get scored
    mask = np.pad(mask, P)
    n_glyphs = sum(not c.isspace() for c in text)
    allowed = n_glyphs // 5
    best = None
    for s in (1.0, 0.85, 0.7, 0.55, 0.42):
        size = max(10, int(base_size * s))
        img, pad = text_img(text, size, font, color, shadow, opacity)
        tw, th = img.size
        ta = (np.array(img)[::DS, ::DS, 3] > 128).astype(np.float32)
        area = ta.sum() + 1e-6
        spans = [(a // DS, max(a // DS + 1, b // DS)) for a, b in char_spans(text, font, size, pad)]
        margin = int(0.03 * W) - pad
        xs_opts = sorted({(W - tw) // 2} | {int(v) for v in np.linspace(margin, W - tw - margin, 7)})
        for x in xs_opts:
            for y in range(int(0.03 * H), max(int(0.03 * H) + 1, int(0.75 * H) - th), max(DS, H // 100)):
                sub = mask[P + y // DS:P + y // DS + ta.shape[0], P + x // DS:P + x // DS + ta.shape[1]]
                if sub.shape != ta.shape:
                    continue
                cov = sub * ta
                occ = float(cov.sum() / area)
                if occ > 0.45:
                    continue
                hidden = sum(cov[:, a:b].sum() / (ta[:, a:b].sum() + 1e-6) > 0.55 for a, b in spans)
                # over-budget hidden glyphs dominate the key, so a crowded frame still gets the most legible spot
                score = (max(0, hidden - allowed), abs(occ - 0.18) + 0.2 * (y / H) + 0.5 * (1 - s)
                         + 0.1 * abs(x + tw / 2 - W / 2) / W)
                if best is None or score < best[0]:
                    best = (score, img, x, y)
    if best is None:
        img, _ = text_img(text, base_size, font, color, shadow, opacity)
        return img, (W - img.size[0]) // 2, int(0.05 * H)
    if best[0][0] > 0:
        print("  warn: '%s' can't sit behind the subject fully legible (too little headroom)" % text, file=sys.stderr)
    return best[1], best[2], best[3]


def build_layers(cue, style, alpha, fps, W, H):
    """Returns list of (rgba_img, x, y) for this cue."""
    font = cue.get("font", style["font"])
    color = hex_rgb(cue.get("color", style["color"]))
    opacity = cue.get("opacity", style["opacity"])
    shadow = cue.get("shadow", style["shadow"])
    wf = cue.get("width_frac", style["width_frac"])
    text = cue["text"].upper() if style.get("uppercase", True) else cue["text"]
    layout = cue.get("layout", "behind")
    i0, i1 = int(cue["start"] * fps), int(cue["end"] * fps) + 1
    mask = mean_mask(alpha, i0, i1)

    if layout == "split":
        words = text.split()
        if len(words) >= 2:
            k = (len(words) + 1) // 2
            left, right = " ".join(words[:k]), " ".join(words[k:])
            cols = np.where(mask[: int(0.6 * mask.shape[0])].max(axis=0) > 0.5)[0]
            if len(cols):
                sl, sr = cols.min() * DS, cols.max() * DS
                ov = int(0.04 * W)  # tuck a little behind the subject edge
                lw, rw = sl + ov - int(0.03 * W), W - (sr - ov) - int(0.03 * W)
                if min(lw, rw) > 0.15 * W:
                    size = cue.get("size") or min(fit_size(left, font, lw, style["max_h_frac"] * H),
                                                  fit_size(right, font, rw, style["max_h_frac"] * H))
                    li, _ = text_img(left, size, font, color, shadow, opacity)
                    ri, _ = text_img(right, size, font, color, shadow, opacity)
                    rows = np.where(mask.max(axis=1) > 0.5)[0]
                    head_top = rows.min() * DS if len(rows) else int(0.2 * H)
                    y = int(cue["y"] * H) if "y" in cue else min(H - li.size[1], head_top + int(0.06 * H))
                    return [(li, sl + ov - li.size[0], y), (ri, sr - ov, y)], False
        layout = "behind"  # fallback

    size = cue.get("size") or fit_size(text, font, wf * W, style["max_h_frac"] * H)
    if layout == "behind":
        img, x, y = place_behind(text, size, font, color, shadow, opacity, mask, W, H, cue)
        return [(img, x, y)], False
    img, pad = text_img(text, size, font, color, shadow, opacity)
    # "front": plain caption drawn over the subject
    if cue.get("align") == "left":
        x = int(cue.get("x", 0.06) * W) - pad
    else:
        x = (W - img.size[0]) // 2
    y = int(cue.get("y", 0.72) * H)
    return [(img, x, y)], True


def pop(img, t, dur=0.14):
    """Scale-in 1.15 -> 1.0 with ease-out; returns (img, dx, dy) relative offset."""
    if t >= dur:
        return img, 0, 0
    k = t / dur
    s = 1.0 + 0.15 * (1 - k) ** 3
    w, h = img.size
    nw, nh = max(1, int(w * s)), max(1, int(h * s))
    im = img.resize((nw, nh), Image.BILINEAR)
    a = min(1.0, k * 2.5)
    if a < 1:
        arr = np.array(im)
        arr[..., 3] = (arr[..., 3] * a).astype(np.uint8)
        im = Image.fromarray(arr)
    return im, -(nw - w) // 2, -(nh - h) // 2


def blend(canvas, img, x, y):
    """Alpha-over an RGBA PIL image onto float canvas (H,W,3) in place, with clipping."""
    H, W = canvas.shape[:2]
    a = np.asarray(img).astype(np.float32) / 255
    h, w = a.shape[:2]
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
    if x0 >= x1 or y0 >= y1:
        return
    sub = a[y0 - y:y1 - y, x0 - x:x1 - x]
    al = sub[..., 3:4]
    canvas[y0:y1, x0:x1] = canvas[y0:y1, x0:x1] * (1 - al) + sub[..., :3] * al


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input"); ap.add_argument("cues"); ap.add_argument("output")
    ap.add_argument("--stills", help="dir to dump a still at each cue midpoint for QA")
    ap.add_argument("--crf", type=int, default=18)
    a = ap.parse_args()

    spec = json.load(open(a.cues))
    style = {"font": os.path.join(C, "BebasNeue-Regular.ttf"), "color": "#FFFFFF", "width_frac": 0.9,
             "max_h_frac": 0.30, "shadow": 0.35, "opacity": 1.0, "pop": True, "uppercase": True}
    style.update(spec.get("style", {}))
    cues = sorted(spec["cues"], key=lambda c: c["start"])

    W, H, fps, dur = probe(a.input)
    print("input %dx%d @ %.2ffps %.1fs, %d cues" % (W, H, fps, dur, len(cues)), file=sys.stderr)
    with tempfile.TemporaryDirectory() as td:
        alpha = matte_all(a.input, W, H, fps, td)
        layers = [build_layers(c, style, alpha, fps, W, H) for c in cues]

        audio = has_audio(a.input)
        cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % (W, H),
               "-r", "%f" % fps, "-i", "-"]
        if audio:
            cmd += ["-i", a.input, "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "192k", "-shortest"]
        cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", str(a.crf), "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", a.output]
        enc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

        for i, fr in enumerate(frames(a.input, W, H, fps)):
            if i >= len(alpha):
                break
            t = i / fps
            active = [(c, l) for c, l in zip(cues, layers) if c["start"] <= t < c["end"]]
            if not active:
                enc.stdin.write(fr.tobytes()); continue
            f32 = fr.astype(np.float32) / 255
            behind = f32.copy()
            front_layers = []
            for c, (ls, is_front) in active:
                for img, x, y in ls:
                    im, dx, dy = pop(img, t - c["start"]) if style["pop"] else (img, 0, 0)
                    (front_layers.append((im, x + dx, y + dy)) if is_front else blend(behind, im, x + dx, y + dy))
            al = (alpha[i].astype(np.float32) / 255)[..., None]
            out = f32 * al + behind * (1 - al)
            for im, x, y in front_layers:
                blend(out, im, x, y)
            enc.stdin.write((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8).tobytes())
            if i % 30 == 0:
                print("  render %.1fs / %.1fs" % (t, dur), end="\r", file=sys.stderr)
        enc.stdin.close(); enc.wait()
        print("\nwrote %s" % a.output, file=sys.stderr)

    if a.stills:
        os.makedirs(a.stills, exist_ok=True)
        for k, c in enumerate(cues):
            ts = c["start"] + min(0.3, (c["end"] - c["start"]) * 0.6)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "%.3f" % ts, "-i", a.output, "-frames:v", "1",
                            "-vf", "scale=-2:720", os.path.join(a.stills, "cue_%02d.jpg" % k)], check=True)
        print("stills in %s" % a.stills, file=sys.stderr)


if __name__ == "__main__":
    main()
