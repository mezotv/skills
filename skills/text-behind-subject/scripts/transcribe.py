"""Speech -> cues.json (1-2 word punchy captions) using whisper.cpp word timings.

usage: python transcribe.py INPUT_VIDEO OUT_CUES.json [--lang auto|en|de] [--max-words 2]
"""
import argparse, json, os, re, subprocess, sys, tempfile

C = os.environ.get("TBS_HOME", os.path.expanduser("~/.cache/text-behind-subject"))


def whisper_words(video, lang):
    model = next((os.path.join(C, m) for m in ("ggml-small.bin", "ggml-base.bin") if os.path.exists(os.path.join(C, m))), None)
    if not model:
        sys.exit("no whisper model in %s - run setup.sh" % C)
    with tempfile.TemporaryDirectory() as td:
        wav = os.path.join(td, "a.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", video, "-ar", "16000", "-ac", "1", wav], check=True)
        subprocess.run(["whisper-cli", "-m", model, "-f", wav, "-l", lang, "-ml", "1", "-sow", "-oj",
                        "-of", os.path.join(td, "w"), "-np"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        data = json.load(open(os.path.join(td, "w.json")))
    words = []
    for seg in data["transcription"]:
        t = seg["text"].strip()
        if not t or t.startswith("[") or t.startswith("("):
            continue
        words.append({"text": t, "start": seg["offsets"]["from"] / 1000, "end": seg["offsets"]["to"] / 1000})
    return words


def group(words, max_words, max_chars=12, gap=0.25):
    cues, cur = [], []
    for w in words:
        clean = re.sub(r"[^\w'?!.,-]", "", w["text"]).upper()
        if not clean:
            continue
        w = dict(w, text=clean)
        if cur and (len(cur) >= max_words or w["start"] - cur[-1]["end"] > gap
                    or len(" ".join(x["text"] for x in cur + [w])) > max_chars
                    or re.search(r"[.?!,]$", cur[-1]["text"])):
            cues.append(cur); cur = []
        cur.append(w)
    if cur:
        cues.append(cur)
    out = []
    for i, c in enumerate(cues):
        end = c[-1]["end"] + 0.3
        if i + 1 < len(cues):
            end = min(end, cues[i + 1][0]["start"])
        out.append({"text": " ".join(x["text"] for x in c).rstrip(","), "start": round(c[0]["start"], 2), "end": round(end, 2)})
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("video"); ap.add_argument("out")
    ap.add_argument("--lang", default="auto"); ap.add_argument("--max-words", type=int, default=2)
    a = ap.parse_args()
    words = whisper_words(a.video, a.lang)
    cues = group(words, a.max_words)
    json.dump({"cues": cues}, open(a.out, "w"), indent=1)
    print("%d words -> %d cues -> %s" % (len(words), len(cues), a.out))
