import json
import math
import struct
import sys
import wave

TRANSCRIPT, AUDIO, KEYS, OUT = sys.argv[1:5]
SRC = int(sys.argv[5]) if len(sys.argv) > 5 else 0
CAPTIONS = [tuple(x) for x in json.load(open(KEYS))]
data = json.load(open(TRANSCRIPT))
words = data if isinstance(data, list) else data["words"]
norm = lambda s: "".join(c for c in s.lower() if c.isalnum() or c == "'")

w = wave.open(AUDIO)
sr = w.getframerate()
samples = struct.unpack(f"<{w.getnframes()}h", w.readframes(w.getnframes()))
hop = sr // 100
env = []
for i in range(0, len(samples) - hop, hop):
    chunk = samples[i : i + hop]
    env.append(20 * math.log10(math.sqrt(sum(x * x for x in chunk) / hop) / 32768 + 1e-9))


def snap(est):
    lo, hi = max(6, int((est - 0.35) * 100)), min(len(env) - 1, int((est + 0.35) * 100))
    onsets = [f for f in range(lo, hi) if env[f] > -32 and env[f] - min(env[f - 8 : f]) > 9 and max(env[f - 4 : f]) < -34]
    if onsets:
        return min(onsets, key=lambda f: abs(f / 100 - est)) / 100, "onset"
    lo, hi = int((est - 0.25) * 100), int((est + 0.25) * 100)
    return min(range(lo, hi), key=lambda f: env[f]) / 100, "dip"


result, wi = [], 0
for key, text in CAPTIONS:
    while norm(words[wi]["text"]) != key:
        wi += 1
    est = words[wi]["start"]
    t, how = snap(est)
    result.append({"src": SRC, "start": round(max(0.0, t - 0.04), 2), "text": text})
    bars = "".join(" .:-=+*#%@"[max(0, min(9, int((env[f] + 55) / 4)))] for f in range(int(t * 100) - 30, int(t * 100) + 30))
    print(f"{key:>8} {est:5.2f}->{t:5.2f} {how:5} [{bars[:30]}|{bars[30:]}] {text}")
    wi += 1

json.dump(result, open(OUT, "w"), indent=1)
