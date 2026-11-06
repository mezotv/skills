#!/usr/bin/env bash
# One-time setup: python venv + models + font in ~/.cache/text-behind-subject. Safe to re-run.
set -euo pipefail
C="${TBS_HOME:-$HOME/.cache/text-behind-subject}"
mkdir -p "$C"

command -v ffmpeg >/dev/null || { echo "need ffmpeg (brew install ffmpeg)"; exit 1; }
command -v uv >/dev/null || { echo "need uv (brew install uv)"; exit 1; }
command -v whisper-cli >/dev/null || echo "warn: whisper-cli missing (brew install whisper-cpp) - only needed for auto captions"

fetch() { [ -s "$C/$1" ] || { echo "downloading $1"; curl -fsSL -o "$C/$1" "$2"; }; }
fetch rvm_mobilenetv3_fp32.onnx https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0/rvm_mobilenetv3_fp32.onnx
fetch BebasNeue-Regular.ttf https://github.com/google/fonts/raw/main/ofl/bebasneue/BebasNeue-Regular.ttf
fetch ggml-small.bin https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin

if [ ! -x "$C/venv/bin/python" ]; then
  uv venv -q -p 3.11 "$C/venv"
fi
VIRTUAL_ENV="$C/venv" uv pip install -q onnxruntime numpy pillow
echo "ok: $C"
