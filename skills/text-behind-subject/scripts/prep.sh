#!/usr/bin/env bash
# Phone clip -> SDR H.264 working file (BT.709, CFR, rotation baked in).
# iPhone HLG/BT.2020 is tone mapped by Apple's VideoToolbox (scale_vt); SDR input is just normalised.
# usage: prep.sh IN.MOV OUT.mp4 [HEIGHT=1080] [FPS=30]
set -euo pipefail
in="$1"; out="$2"; h="${3:-1080}"; fps="${4:-30}"

trc=$(ffprobe -v error -select_streams v:0 -show_entries stream=color_transfer -of default=nw=1:nk=1 "$in" | head -1)
rot=$(ffprobe -v error -select_streams v:0 -show_entries stream_side_data=rotation -of default=nw=1:nk=1 "$in" | head -1)
rot=${rot:-0}
case "$rot" in
  -90|270) turn="transpose=clock," ;;
  90|-270) turn="transpose=cclock," ;;
  180|-180) turn="hflip,vflip," ;;
  *) turn="" ;;
esac
# scale to the short side = $h whatever the orientation
fit="scale='if(gt(iw,ih),-2,$h)':'if(gt(iw,ih),$h,-2)':flags=lanczos"
enc=(-r "$fps" -c:v libx264 -crf 14 -preset fast -pix_fmt yuv420p
     -color_primaries bt709 -color_trc bt709 -colorspace bt709 -c:a aac -b:a 192k -map 0:v:0 -map 0:a:0?)
tmp="${out%.*}.tmp.mp4"

if [[ "$trc" == "arib-std-b67" || "$trc" == "smpte2084" ]]; then
  echo "HDR ($trc), rotation $rot -> tone mapping with VideoToolbox"
  # hw frames skip autorotate, so rotate by hand and drop the copied display matrix afterwards
  ffmpeg -v error -y -noautorotate -hwaccel videotoolbox -hwaccel_output_format videotoolbox_vld -i "$in" \
    -vf "scale_vt=color_matrix=bt709:color_primaries=bt709:color_transfer=bt709,hwdownload,format=p010le,${turn}${fit},format=yuv420p" \
    "${enc[@]}" "$tmp"
  ffmpeg -v error -y -display_rotation 0 -i "$tmp" -c copy "$out" && rm -f "$tmp"
else
  echo "SDR ($trc) -> normalising"
  ffmpeg -v error -y -i "$in" -vf "${fit},format=yuv420p" "${enc[@]}" "$out"
fi
ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 "$out"
