#!/usr/bin/env bash
# Сборка пропатченного Unlock-r.
#
#   bash build.sh <дерево после apktool d> <исходный base.apk> <выходной apk> \
#                 [каталог сплитов] [каталог для подписанных сплитов]
#
# Что происходит:
#   1. smali -> dex через DexOnly (apktool в этом окружении роняет aapt2,
#      но ресурсы патчем не меняются, поэтому пересборка ресурсов не нужна);
#   2. dex подставляются в исходный APK, остальные записи не трогаются;
#   3. zipalign + apksigner (v1+v2+v3);
#   4. сплиты подписываются тем же ключом — иначе набор не установится.
#
set -euo pipefail

SRC="${1:?нужен каталог после apktool d}"
ORIG="${2:?нужен исходный base.apk}"
OUT="${3:?нужен путь выходного apk}"
SPLITS_SRC="${4:-}"
SPLITS_OUT="${5:-}"

BT="${BUILD_TOOLS:-/root/android-sdk/build-tools/35.0.0}"
APKTOOL="${APKTOOL:-/tmp/opencode/apktool.jar}"
KS="${KS:-$HOME/.android/unlockr_cracks.keystore}"
KS_PASS="${KS_PASS:-unlockr}"
ALIAS="${KS_ALIAS:-unlockr}"
API_LEVEL="${API_LEVEL:-35}"
REBALANCE_CLASSES="${REBALANCE_CLASSES:-400}"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

if [ ! -f "$KS" ]; then
  echo "==> генерирую ключ для подписи"
  mkdir -p "$(dirname "$KS")"
  keytool -genkeypair -v -keystore "$KS" -alias "$ALIAS" \
    -keyalg RSA -keysize 2048 -validity 10950 \
    -storepass "$KS_PASS" -keypass "$KS_PASS" \
    -dname "CN=Unlockr Crack, OU=Crack, O=Crack, C=US" >/dev/null 2>&1
fi

sign_one() {
  local in_apk="$1" out_apk="$2"
  "$BT/zipalign" -p -f 4 "$in_apk" "$out_apk.aligned"
  "$BT/apksigner" sign \
    --ks "$KS" --ks-pass "pass:$KS_PASS" --key-pass "pass:$KS_PASS" \
    --ks-key-alias "$ALIAS" \
    --v1-signing-enabled true --v2-signing-enabled true --v3-signing-enabled true \
    --v4-signing-enabled false \
    --out "$out_apk" "$out_apk.aligned"
  rm -f "$out_apk.aligned"
}

echo "==> smali -> dex"
if [ "$REBALANCE_CLASSES" -gt 0 ]; then
  echo "    ребаланс dex: переношу $REBALANCE_CLASSES классов в classes2.dex"
  echo "    (в classes.dex таблица field_ids забита под 65536, нужен запас)"
  python3 "$HERE/rebalance_dex.py" "$SRC" 999999 "$REBALANCE_CLASSES" | tail -3
fi
java -cp "$APKTOOL" "$HERE/DexOnly.java" "$SRC/smali" "$WORK/classes.dex" "$API_LEVEL"
java -cp "$APKTOOL" "$HERE/DexOnly.java" "$SRC/smali_classes2" "$WORK/classes2.dex" "$API_LEVEL"

echo "==> подстановка dex в исходный APK"
python3 "$HERE/inject_dex.py" "$ORIG" "$WORK/patched.apk" \
  "$WORK/classes.dex" "$WORK/classes2.dex"

echo "==> zipalign + подпись"
sign_one "$WORK/patched.apk" "$OUT"

if [ -n "$SPLITS_SRC" ] && [ -d "$SPLITS_SRC" ]; then
  echo "==> подпись сплитов"
  mkdir -p "$SPLITS_OUT"
  for apk in "$SPLITS_SRC"/split_config.*.apk; do
    [ -e "$apk" ] || continue
    name="$(basename "$apk")"
    sign_one "$apk" "$SPLITS_OUT/$name"
    echo "    $name"
  done
fi

echo "==> проверка"
"$BT/apksigner" verify --print-certs "$OUT" | head -4
ls -la "$OUT"
[ -n "$SPLITS_OUT" ] && ls -la "$SPLITS_OUT"
echo "==> готово"
