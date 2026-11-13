#!/usr/bin/env python3
"""
Подставляет dex-файлы в исходный APK, не трогая остальные записи.

Ресурсы приложения патчем не меняются, поэтому пересобирать APK целиком не
нужно: достаточно заменить classes*.dex. Так сохраняются оригинальные
resources.arsc, манифест, ассеты и метод сжатия каждой записи.

    python3 inject_dex.py <исходный apk> <выходной apk> classes.dex classes2.dex
"""

import shutil
import sys
import zipfile
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 4:
        print(__doc__)
        return 1
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])
    replacements = {Path(p).name: Path(p) for p in sys.argv[3:]}

    tmp = dst.with_suffix(dst.suffix + ".tmp")
    with zipfile.ZipFile(src, "r") as zin, zipfile.ZipFile(tmp, "w") as zout:
        for info in zin.infolist():
            name = info.filename
            if name in replacements:
                data = replacements[name].read_bytes()
                zout.writestr(info, data, compress_type=info.compress_type)
                print(f"  заменён {name} ({len(data)} байт)")
            else:
                zout.writestr(info, zin.read(name), compress_type=info.compress_type)

    shutil.move(str(tmp), str(dst))
    print(f"  готово: {dst} ({dst.stat().st_size} байт)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
