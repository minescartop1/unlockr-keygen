#!/usr/bin/env python3
"""
Собирает единый устанавливаемый APK из бандла.

Исходный Unlock-r разложен по сплитам (base + arm64_v8a + en + ru + xxhdpi).
base.apk сам по себе не ставится: нет нативных библиотек, а установщик
набора требует все сплиты сразу — отсюда «несовместимо с вашим устройством».

Здесь собирается один APK:
  * base.apk целиком (манифест, resources.arsc, res/, assets — байт-в-байт,
    идентификаторы ресурсов не едут);
  * нативные библиотеки из arm64-сплита;
  * classes.dex / classes2.dex из аргументов (пропатченные);
  * подписи разработчика выкидываются, ставится своя.

    python3 make_universal.py <base.apk> <arm64 split> <out apk> <classes.dex> <classes2.dex>
"""

import shutil
import sys
import zipfile
from pathlib import Path

SIGNATURE_MARKERS = (
    "META-INF/MANIFEST.MF",
    "META-INF/UNLOCKR.RSA",
    "META-INF/UNLOCKR.SF",
    "META-INF/UNLOCKR.DSA",
    "META-INF/UNLOCKR.EC",
)


def is_signature_entry(name: str) -> bool:
    upper = name.upper()
    if upper in {m.upper() for m in SIGNATURE_MARKERS}:
        return True
    if upper.startswith("META-INF/") and upper.endswith((".SF", ".RSA", ".DSA", ".EC")):
        return True
    return False


def main() -> int:
    if len(sys.argv) != 6:
        print(__doc__)
        return 1
    base = Path(sys.argv[1])
    arm64 = Path(sys.argv[2])
    out = Path(sys.argv[3])
    dexes = {Path(p).name: Path(p).read_bytes() for p in sys.argv[4:]}

    tmp = out.with_suffix(out.suffix + ".tmp")
    written = set()

    with zipfile.ZipFile(base, "r") as zin, zipfile.ZipFile(tmp, "w") as zout:
        for info in zin.infolist():
            name = info.filename
            if is_signature_entry(name):
                print(f"  выкинут {name}")
                continue
            if name in dexes:
                zout.writestr(info, dexes[name], compress_type=info.compress_type)
                written.add(name)
                print(f"  заменён {name} ({len(dexes[name])} байт)")
                continue
            zout.writestr(info, zin.read(name), compress_type=info.compress_type)

        with zipfile.ZipFile(arm64, "r") as zsplit:
            for info in zsplit.infolist():
                name = info.filename
                if not name.startswith("lib/") or name in written:
                    continue
                if is_signature_entry(name):
                    continue
                zout.writestr(info, zsplit.read(name), compress_type=info.compress_type)
                written.add(name)
                print(f"  добавлен {name} ({info.file_size} байт)")

    shutil.move(str(tmp), str(out))
    print(f"  готово: {out} ({out.stat().st_size} байт)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
