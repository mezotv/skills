#!/usr/bin/env bash
# Pick and apply a colour grade with the media-use (HyperFrames) LUT tools.
#   grade.sh candidates IN.mp4 WORKDIR      -> WORKDIR/compare.png with lut_001.. (teal-orange, warm-punchy, golden)
#   grade.sh apply IN.mp4 LUT.cube OUT.mp4  -> LUT baked into every frame (full strength)
set -euo pipefail
cmd="$1"; shift

if [[ "$cmd" == candidates ]]; then
  in="$1"; wd="$2"; mkdir -p "$wd"
  ffmpeg -v error -y -ss 1 -i "$in" -frames:v 1 -update 1 "$wd/frame.png"
  cd "$wd"
  npx -y hyperframes media-use resolve --type lut --intent "teal orange blockbuster" --project . | tail -1
  npx -y hyperframes media-use resolve --type lut --intent "warm punchy instagram reel" --project . \
    --params '{"contrast":0.22,"saturation":0.18,"vibrance":0.28,"temperature":0.22,"tint":0.02,"blacks":-0.03,"highlights":-0.18,"whites":-0.08,"splitTone":{"intensity":0.35,"balance":0.55,"shadows":[-0.02,0.02,0.06],"highlights":[0.08,0.04,-0.04]}}' | tail -1
  npx -y hyperframes media-use resolve --type lut --intent "golden hour warm soft" --project . \
    --params '{"contrast":0.12,"saturation":0.1,"vibrance":0.2,"temperature":0.35,"blacks":0.02,"highlights":-0.22,"splitTone":{"intensity":0.4,"balance":0.6,"shadows":[0.02,0.0,0.04],"highlights":[0.1,0.05,-0.05]}}' | tail -1
  luts=$(ls .media/luts/*.cube | tr '\n' ',' | sed 's/,$//')
  npx -y hyperframes grade-compare --for frame.png --luts "$luts" --project . --out compare.png --json >/dev/null
  echo "look at $wd/compare.png, then: grade.sh apply IN.mp4 $wd/.media/luts/lut_00N.cube OUT.mp4"
elif [[ "$cmd" == apply ]]; then
  in="$1"; lut="$2"; out="$3"
  # lut3d straight, no blend: a split+blend opacity mix silently dropped the grade
  ffmpeg -v error -y -i "$in" -vf "lut3d=file='$lut':interp=tetrahedral,format=yuv420p" \
    -c:v libx264 -crf 14 -preset fast -color_primaries bt709 -color_trc bt709 -colorspace bt709 -c:a copy "$out"
  echo "wrote $out"
else
  echo "usage: grade.sh candidates IN WORKDIR | grade.sh apply IN LUT OUT"; exit 1
fi
