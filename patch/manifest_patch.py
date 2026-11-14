#!/usr/bin/env python3
"""
Патчит бинарный AndroidManifest.xml: убирает требование сплитов.

У base.apk из бандла в манифесте стоит

    android:requiredSplitTypes="base__abi,base__density"

Из-за этого PackageParser считает APK частью набора и отказывается ставить его
одного: INSTALL_FAILED_MISSING_SPLIT (на части устройств так и показывают —
«несовместимо с вашим устройством»).

Строка правится прямо в string pool бинарного AXML: длину записи обнуляем,
байты оставляем на месте. Смещения остальных строк в пуле абсолютные, поэтому
ничего не едет.

    python3 manifest_patch.py <AndroidManifest.xml> [значение для замены]
"""

import struct
import sys
from pathlib import Path

CHUNK_STRING_POOL = 0x0001
UTF8_FLAG = 1 << 8
TARGET = "base__abi,base__density"


def patch(data: bytes, target: str, replacement: str = "") -> tuple[bytes, int]:
    if data[:4] != b"\x03\x00\x08\x00":
        raise SystemExit("это не бинарный AXML")

    # заголовок файла: magic+size, затем chunks
    off = 8
    if struct.unpack_from("<H", data, off)[0] != CHUNK_STRING_POOL:
        raise SystemExit("string pool не первый chunk")
    pool_off = off
    header_size, chunk_size = struct.unpack_from("<HH", data, pool_off + 4)[0], \
        struct.unpack_from("<I", data, pool_off + 8)[0]
    string_count, style_count, flags = struct.unpack_from("<III", data, pool_off + 8)[0], \
        struct.unpack_from("<I", data, pool_off + 12)[0], \
        struct.unpack_from("<I", data, pool_off + 16)[0]
    strings_start = struct.unpack_from("<I", data, pool_off + 20)[0]
    is_utf8 = bool(flags & UTF8_FLAG)

    offsets = []
    base = pool_off + strings_start
    for i in range(string_count):
        offsets.append(struct.unpack_from("<I", data, pool_off + 28 + i * 4)[0])

    patched = 0
    out = bytearray(data)

    for rel in offsets:
        p = base + rel
        if is_utf8:
            # u8 len (bytes), u8 len (chars), bytes, 0x00
            nbytes, nchars = struct.unpack_from("<HH", data, p)
            raw = data[p + 2 + nbytes:p + 2 + nbytes + nchars]
            text = raw.decode("utf-8", errors="replace")
            if text == target:
                new = replacement.encode("utf-8")
                if len(new) > nbytes:
                    raise SystemExit("замена длиннее оригинала — не влезет")
                struct.pack_into("<HH", out, p, len(new), len(new))
                out[p + 2:p + 2 + len(new)] = new
                out[p + 2 + len(new)] = 0x00
                patched += 1
        else:
            nchars = struct.unpack_from("<H", data, p)[0]
            raw = data[p + 2:p + 2 + nchars * 2]
            text = raw.decode("utf-16-le", errors="replace")
            if text == target:
                new = replacement.encode("utf-16-le")
                if len(new) > nchars * 2:
                    raise SystemExit("замена длиннее оригинала")
                struct.pack_into("<H", out, p, len(new) // 2)
                out[p + 2:p + 2 + len(new)] = new
                out[p + 2 + len(new)] = 0x00
                out[p + 3 + len(new)] = 0x00
                patched += 1

    return bytes(out), patched


def rename_strings(data: bytes, mapping: dict) -> tuple[bytes, int]:
    """Переименовывает строки в string pool по ТОЧНОМУ совпадению.

    Важно: менять можно только те записи, которые не являются именами
    классов (значение package и authorities). Глобальная замена префикса
    «me.tito.unlocker» ломает android:name у activity (me.tito.unlocker.MainActivity
    -> m.tito.unlockr.x.MainActivity), а такого класса в dex нет — приложение
    падает сразу при старте.
    """
    if data[:4] != b"\x03\x00\x08\x00":
        raise SystemExit("это не бинарный AXML")

    pool_off = 8
    if struct.unpack_from("<H", data, pool_off)[0] != CHUNK_STRING_POOL:
        raise SystemExit("string pool не первый chunk")
    string_count = struct.unpack_from("<I", data, pool_off + 8)[0]
    flags = struct.unpack_from("<I", data, pool_off + 16)[0]
    strings_start = struct.unpack_from("<I", data, pool_off + 20)[0]
    is_utf8 = bool(flags & UTF8_FLAG)
    base = pool_off + strings_start
    out = bytearray(data)
    patched = 0

    for i in range(string_count):
        rel = struct.unpack_from("<I", data, pool_off + 28 + i * 4)[0]
        p = base + rel
        if is_utf8:
            nbytes, nchars = struct.unpack_from("<HH", data, p)
            raw = data[p + 2 + nbytes:p + 2 + nbytes + nchars]
            text = raw.decode("utf-8", "replace")
            if text in mapping:
                new = mapping[text].encode("utf-8")
                if len(new) > nbytes:
                    raise SystemExit(f"новая строка длиннее: {text}")
                struct.pack_into("<HH", out, p, len(new), len(new))
                out[p + 2:p + 2 + len(new)] = new
                out[p + 2 + len(new)] = 0x00
                patched += 1
        else:
            nchars = struct.unpack_from("<H", data, p)[0]
            raw = data[p + 2:p + 2 + nchars * 2]
            text = raw.decode("utf-16-le", "replace")
            if text in mapping:
                new = mapping[text].encode("utf-16-le")
                if len(new) > nchars * 2:
                    raise SystemExit(f"новая строка длиннее: {text}")
                struct.pack_into("<H", out, p, len(new) // 2)
                out[p + 2:p + 2 + len(new)] = new
                out[p + 2 + len(new)] = 0x00
                out[p + 3 + len(new)] = 0x00
                patched += 1

    return bytes(out), patched


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    path = Path(sys.argv[1])
    replacement = sys.argv[2] if len(sys.argv) > 2 else ""
    data = path.read_bytes()
    new, n = patch(data, TARGET, replacement)
    if n == 0:
        print(f"строка '{TARGET}' не найдена")
        return 1
    path.write_bytes(new)
    print(f"исправлено записей: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
