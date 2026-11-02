---
name: talking-head-edit
description: Dominik's workflow for editing a phone-shot talking-head or founder video (iPhone selfie, launch announcement, product update) into a polished vertical post for X, TikTok and Instagram Reels. Use whenever the user wants to edit a selfie or talking-to-camera clip, cut out fumbles, filler words, pauses or tongue/lip-lick frames, colour grade it, add burned-in subtitles or captions, add logos or emoji overlays when a product is mentioned, splice in another section, or export platform versions. Also use when they send a video from their phone and want it "ready for Twitter/TikTok/Instagram".
---

# talking-head-edit

Turns raw iPhone selfie footage into a captioned, graded vertical video with
soft jump cuts, then exports an X version and a 4K TikTok/Instagram version.
Every default below is a preference the user stated while editing; follow them
unless they say otherwise.

Scripts live in `scripts/`. A project is one folder holding `edit.json`,
`captions.json` and the assets they name (see `references/*.example.json`).

## 1. Get the footage

The user is often away from their computer. Offer a phone upload link:

```bash
PHONE_TOKEN=$(openssl rand -hex 12) UPLOAD_DIR=<project>/incoming bun scripts/phone.ts   # background
cloudflared tunnel --url http://localhost:8787                                          # background
```

Send `https://<quick-tunnel>.trycloudflare.com/<token>`. The page uploads in
20 MB chunks because quick tunnels reject single requests over 100 MB. Check
the logged size matches, then stop both processes. To deliver finished files,
run it again with `SERVE_DIR=<out>` and link `/<token>/f/<file>.mp4`. Kill the
tunnel as soon as the user has the files.

## 2. Transcribe and find the cuts

- Words: `npx hyperframes transcribe <audio.wav> --engine parakeet --json`
  (`hyperframes models install parakeet` once). Whisper.cpp word timestamps
  drift by up to 0.4 s and are only good for slice checks.
- Map the waveform with 20 ms RMS bars and `silencedetect`. Confirm what a
  range contains by transcribing just that slice.
- Cut: filler ("and, um, yeah"), false starts, long breath gaps, words the user
  names ("cut out per person"), and dead air at the head and tail.
- Before fixing any cut point, tile the mouth region at 15 fps around it. The
  user does not want tongue-out or lip-licking frames on screen; end the cut
  on the last clean frame even if the audio pause is shorter.
- Keep about 0.1 to 0.25 s of natural pause on each side. Cuts that are too
  tight were rejected as "too aggressive".
- Inserting another clip: split the main clip at a waveform dip between
  sentences and put the new section there.

Write the result as `keep: [[source, start, end], ...]` in output order.
`render.py` joins every cut with a 0.16 s dissolve over held frames plus an
audio crossfade, so cut-out frames never bleed into the blend.

## 3. Colour

- iPhone footage is HDR (HLG, BT.2020). Never hand-roll the HDR to SDR
  conversion; a custom LUT blew out the face. Use Apple's tone mapping on the
  Mac, then grade on top:
  `avconvert -s in.MOV -p Preset3840x2160 -o sdr.mov --multiPass` (outputs 4K
  30 fps H.264 SDR; HEVC and ProRes presets keep HDR).
- Default look: `film` in `scripts/looks.sh` (faded blacks, olive greens, warm
  mids, cool shadows). `clean` and `moody` exist; when the user is unsure,
  render one frame of each side by side and let them pick.
- Every look includes skin-only smoothing: a bilateral blur masked by a
  `colorkey` on the skin tone. Sample the skin hex from the SDR frame and set
  `skin_key` in `edit.json`. The user wanted less skin detail and a less
  bright face, never a globally soft image.
- A clip shot somewhere else (warm indoor light) gets a per-source `pre`
  filter that matches it before the look, e.g.
  `colortemperature=temperature=8200:mix=1,huesaturation=colors=r+y:saturation=-0.2`.

## 4. Audio

Use the original audio. Noise reduction, EQ, de-essing, compression and
loudness normalisation were tried and rejected as worse. The only processing
is the crossfade at each cut. If two clips differ a lot in level, ask before
matching volume.

## 5. Captions and overlays

- `captions.json` entries: `{"src", "start", "text"}`; each runs until the next
  one starts. Two to five words, split at natural phrases; never let a caption
  wrap into an orphan like "for you and much / more."
- Time starts from Parakeet word starts snapped to waveform onsets:
  `uv run scripts/timing.py transcript.json audio.wav keys.json out.json [src]`
  where `keys.json` is `[["firstword", "Caption text"], ...]`. Read the printed
  waveform strip for every caption and override any that land mid-word.
- Style (built into `render.py`): Satoshi Black, 84 px at 1080 wide, white
  with a 7 px black stroke, centred around y = 1330 of 1920, which is clear
  of platform UI. Copy `Satoshi-Variable.ttf` into the project.
- Fix the transcript's spelling of names and products (Dominik, Notra,
  Mintlify, c15t in lowercase), but keep the words as spoken.
- On-screen corrections: wrap a word in `~` to draw it in red (#FF4D4D), e.g.
  `"~*is~ our managed solution"` over audio that says "will be".
- Product mentions: show the logo as a white rounded card with a flat 1 px
  border (`uv run scripts/logo_card.py <logo.svg|Logo.tsx> card.png`). Take
  logos from the product's own repo before searching the web. Cards sit at the
  top of the frame (y = 330), never over the face, and fade in and out over
  0.15 s, cross-fading when two products are mentioned back to back.
- A playful sprite can walk across one word: `uv run scripts/emoji_sprite.py 🕷 spider.png`
  (white sticker outline so it reads on the black stroke), then set `sprite`
  in `edit.json` to the caption text and word.

## 6. Render

```bash
uv run scripts/render.py <project> out/x.mp4 1080 1920 30 14 -maxrate 25M -bufsize 50M
uv run scripts/render.py <project> out/4k.mp4 2160 3840 30 12
```

- X: 1080x1920, 30 fps, CRF 14, peaks capped at 25 Mbps.
- TikTok and Instagram Reels: 4K 2160x3840, 30 fps, CRF 12, no bitrate cap,
  because the user wants the highest quality. The file lands around 400 to
  500 MB; TikTok's phone app has historically capped uploads near 287 MB, so
  say to upload there from the web or offer a smaller copy.
- Always do a 270x480 local test render first; it catches graph errors in
  seconds.
- The user's MacBook struggles with 4K. Offload full renders to a boat.dev
  sandbox via `scripts/boat.sh` (key in `$BOAT_KEY_FILE`, default
  `~/.config/boat/key`, never on a command line or in the repo): `create large`,
  `put` a tar of the project and scripts, `detach` the renders one after
  another (two parallel `uv run` calls race on env creation), poll for a
  `.done` file, `fetch`, then `delete`. Sandboxes auto-stop after an hour, so
  start a fresh one rather than racing the TTL. `avconvert` must still run on
  the Mac.

## 7. Review before handing back

You cannot watch the video, so say so and check what you can:

- Transcribe the final file's audio and read it end to end.
- Contact sheet of stills across the timeline, plus mouth crops at every cut.
- Compare each caption start against the final file's word timings.

Show the user screenshots, not just file paths. They review on their phone.
