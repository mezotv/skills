#!/bin/bash
SMOOTH_S=${SMOOTH_S:-8}
smooth="format=gbrp,split=3[s0][s1][s2];[s1]bilateral=sigmaS=${SMOOTH_S}:sigmaR=0.07[sm];[s2]format=rgba,colorkey=${SKIN_KEY:-0xE2A096}:similarity=0.14:blend=0.12,alphaextract,negate,gblur=sigma=${SMOOTH_S},format=gbrp[mk];[s0][sm][mk]maskedmerge"

clean="$smooth,curves=all='0/0.015 0.5/0.48 0.85/0.80 1/0.95',huesaturation=colors=r:saturation=-0.18,colorbalance=rm=0.015:bm=-0.02,vibrance=intensity=0.08"
film="$smooth,curves=all='0/0.06 0.25/0.235 0.5/0.49 0.8/0.76 1/0.92',huesaturation=colors=r:saturation=-0.06,huesaturation=colors=g:hue=-14:saturation=-0.3,colorbalance=rs=-0.02:bs=0.035:rm=0.04:bm=-0.045,eq=saturation=0.95"
moody="$smooth,curves=all='0/0.03 0.3/0.255 0.6/0.59 0.85/0.79 1/0.93',huesaturation=colors=r:saturation=-0.03,huesaturation=colors=g:hue=-16:saturation=-0.35:intensity=-0.08,colorbalance=rs=-0.03:gs=0.015:bs=0.05:rm=0.045:bm=-0.05,vignette=angle=PI/5"

case "$1" in
  clean) echo "$clean" ;;
  film) echo "$film" ;;
  moody) echo "$moody" ;;
esac
