#!/bin/bash
set -euo pipefail
API=https://boat.dev/api/v1
KEY=$(cat "${BOAT_KEY_FILE:-$HOME/.config/boat/key}")
call() { curl -sS -X "$1" "$API$2" -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" ${3:+-d "$3"}; }

case "$1" in
  create) call POST /sandboxes "{\"ttlSeconds\":3600,\"type\":\"${2:-large}\"}" ;;
  get) call GET "/sandboxes/$2" ;;
  run) call POST "/sandboxes/$2/commands" "$(jq -n --arg c "$3" --argjson t "${4:-600}" '{command:$c,timeoutSeconds:$t}')" ;;
  detach) call POST "/sandboxes/$2/commands" "$(jq -n --arg c "$3" '{command:$c,detached:true}')" ;;
  put)
    url=$(call POST "/sandboxes/$2/files/upload-url" "$(jq -n --arg p "$4" '{path:$p,ttlSeconds:3600}')" | jq -r .url)
    curl -sS -X PUT --data-binary @"$3" "$url" -o /dev/null -w '%{http_code}\n' ;;
  fetch)
    url=$(call POST "/sandboxes/$2/files/download-url" "$(jq -n --arg p "$3" '{path:$p,ttlSeconds:3600}')" | jq -r .url)
    curl -sS -o "$4" "$url" -w '%{http_code}\n' ;;
  delete) curl -sS -X DELETE "$API/sandboxes/$2" -H "Authorization: Bearer $KEY" -H "X-Ascii-Confirm-Delete: $2" ;;
esac
