---
name: text-behind-subject
description: Put big bold caption words BEHIND a person in a video, the Instagram/TikTok "text behind subject" edit where the head and hair cover part of each word. Use when the user wants text behind them or behind their head, the "DO I HATE IT? / YEAH I DO" reel style, punchy word-by-word captions layered behind a talking or selfie clip, or wants to replicate a reel like that from a link. Covers getting the clip (phone upload link), iPhone HDR to SDR, a colour grade picked with the media-use LUT tools, transcription, and the render.
---

# text-behind-subject

Reference look: huge white uppercase condensed type (Bebas Neue), 1-3 words at
a time, hard cuts between cues, a quick scale-in pop, a soft drop shadow, and
the person composited **over** the text so their head or hair covers part of
it. Variants:

- **behind**: one line behind the head: `DO I [head] IT?`, `RUN`, `NO.`
- **split**: words flank the head: `YEAH [head] I DO`
- **front**: plain caption over everything, small and left-aligned, for the
  outro (`K, BYE`)
- semi-transparent text (`opacity` about 0.85) for a quieter line

Everything runs locally on a Mac CPU. A 15 s 1080x1920 clip renders in about
30 s; no GPU is needed.

```bash
SK=<this skill>/scripts
PY=~/.cache/text-behind-subject/venv/bin/python
bash $SK/setup.sh      # once: venv, RVM matting model, Bebas Neue, whisper small
```

## 1. Get the clip

Reference reel from a link: `yt-dlp -o ref.mp4 <url>`, then
`ffmpeg -i ref.mp4 -vf "fps=1,scale=360:-1,tile=4x2" sheet_%02d.jpg` and look
at the sheets to read the style.

The user's own clip is usually on their phone. Offer an upload link:

```bash
python3 -I $SK/upload_server.py ./uploads --port 8765 &            # prints TOKEN_PATH /<secret>
cloudflared tunnel --no-autoupdate --url http://localhost:8765 &    # prints https://<x>.trycloudflare.com
```

Send `https://<x>.trycloudflare.com/<secret>`, the bare tunnel URL 404s. The
page has a file picker and an Upload button and sends 32 MB chunks, because
quick tunnels reject request bodies over 100 MB. The server logs `UPLOADED
<path>`. Pass `--token <secret>` to keep the same URL across restarts. Kill both
processes once the file is in.

## 2. HDR to SDR

iPhone video is HLG/BT.2020 10-bit HDR, often 4K60 with a rotation flag.
Grading it raw looks washed out. Run:

```bash
$SK/prep.sh IN.MOV sdr.mp4 [1080] [30]
```

This tone maps with Apple's VideoToolbox (`scale_vt`), bakes in the rotation,
outputs BT.709 H.264 at 30 fps CFR with the short side at 1080, and passes SDR
input straight through. VideoToolbox frames skip ffmpeg's autorotate, and the
copied display matrix must then be stripped, otherwise the clip plays sideways.
The script handles both.

## 3. Colour grade (media-use / HyperFrames LUTs)

```bash
$SK/grade.sh candidates sdr.mp4 grade/      # 3 LUTs + grade/compare.png
$SK/grade.sh apply sdr.mp4 grade/.media/luts/lut_001.cube graded.mp4
```

The candidates are the `teal-orange-blockbuster` look, a warm punchy reel
look, and a soft golden look, all rendered on one frame with `hyperframes
grade-compare`. Look at `compare.png` and pick one. On a bright white indoor
room, teal-orange won: punchy, cleaner walls, natural skin. The warm punchy
look turned skin red, and the golden one read as washed out. Apply LUTs with
`lut3d` at full strength. A `split` + `blend` opacity mix left the frame
unchanged.

## 4. Words

- Speech: `$PY -I $SK/transcribe.py graded.mp4 cues.json --lang auto` gives
  1-2 word cues from whisper.cpp word timings. Then edit them: keep the hook
  words, fix misheard words, merge or split cues.
- Music only (like the reference reel): the user gives the words and the
  timing, cut on the beat.
- 1-3 words per cue, 0.4-2 s each. Caption hooks, punchlines, numbers and
  one-word reactions, not every filler word.

```json
{"style": {"color": "#FFFFFF", "width_frac": 0.9, "max_h_frac": 0.30, "shadow": 0.35, "pop": true},
 "cues": [
  {"text": "DO I HATE IT?", "start": 1.8, "end": 3.4},
  {"text": "YEAH I DO", "start": 4.8, "end": 6.6, "layout": "split"},
  {"text": "ICH MUSS RAUS", "start": 6.8, "end": 8.0, "opacity": 0.85},
  {"text": "K, BYE", "start": 8.9, "end": 10.0, "layout": "front", "align": "left", "x": 0.07, "y": 0.08, "width_frac": 0.45}
 ]}
```

Per-cue overrides: `layout` (behind|split|front), `y` (0-1, top of the text,
skips the auto search), `x`, `align`, `size` (px), `color`, `opacity`,
`width_frac`, `shadow`, `font`.

## 5. Render

```bash
$PY -I $SK/render.py graded.mp4 cues.json out.mp4 --stills stills/
ffmpeg -v error -y -pattern_type glob -i 'stills/*.jpg' -vf "scale=-2:300,tile=4x2" sheet.jpg
```

How it works:

1. **Matte**: Robust Video Matting (ONNX on the CPU, uses previous frames so it
   stays stable, handles hair) builds a per-frame person alpha.
2. **Place**: for each cue, take the average subject mask over the cue and
   search size, x and y so the person covers about 18% of the text, so it reads
   as "behind", while every letter stays legible. At most len/5 glyphs may be
   more than 55% hidden: `DA KR[head]T MAN` passes, `R[U]N` does not.
3. **Composite**: frame, then the text layer (pop-in, shadow), then the person
   pasted back on top, then any `front` captions. The original audio is muxed
   back in.

## QA: always look at the stills

- `warn: ... too little headroom` means the face fills the top of the frame.
  Fix it with `y`, a smaller `size`, `layout: front`, or by asking the user to
  frame wider with space above the head.
- `split` silently falls back to `behind` when there's under 15% of the width
  on either side of the head. Two separate cues usually read better than a
  shrunken fallback.
- A hand raised in front of a word (counting fingers on "DREI") is a feature.
  The matte keeps hands in front.
- Landscape clips meant for Reels or TikTok: crop to 9:16 around the subject
  **before** rendering so the placement uses the final frame.

## Notes

- Homebrew ffmpeg has no `drawtext`, so all text is drawn with PIL.
- Matting runs on ONNX Runtime's CPU provider. For long or 4K jobs, switch to
  `CoreMLExecutionProvider` (Mac) or `CUDAExecutionProvider` (NVIDIA) in
  `matte_all`.
- CorridorKey and other green-screen keyers don't fit this: they need a
  green-screen plate. RVM handles normal backgrounds.
