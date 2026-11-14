#!/usr/bin/env bash
# Ждёт, пока приложение выложит Play Integrity токен на shared storage,
# и кладёт его рядом с keygen.py.
SRC=/storage/emulated/0/Download/unlockr_pi.txt
DST="$(dirname "$0")/../integrity_token.txt"
for _ in $(seq 1 "${1:-400}"); do
  if [ -s "$SRC" ]; then
    cp "$SRC" "$DST"
    echo "токен получен -> $DST ($(wc -c < "$DST") байт)"
    exit 0
  fi
  sleep 3
done
echo "токен не появился"
exit 1
