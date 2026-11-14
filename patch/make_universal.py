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

import os
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from manifest_patch import patch as patch_axml  # noqa: E402
from manifest_patch import rename_strings  # noqa: E402

SIGNATURE_MARKERS = (
    "META-INF/MANIFEST.MF",
    "META-INF/UNLOCKR.RSA",
    "META-INF/UNLOCKR.SF",
    "META-INF/UNLOCKR.DSA",
    "META-INF/UNLOCKR.EC",
)


OLD_PKG = "me.tito.unlocker"
NEW_PKG = "m.tito.unlockr.x"  # ровно 16 символов, как OLD_PKG — замена байт-в-байт
OLD_BYTES = (OLD_PKG.encode("ascii"), OLD_PKG.encode("utf-16-le"))
NEW_BYTES = (NEW_PKG.encode("ascii"), NEW_PKG.encode("utf-16-le"))

# Замены в манифесте той же длины (иначе едут оффсеты string pool).
# 1) LicenseActivity -> класс, которого нет: ActivityNotFound вместо экрана
#    «your device doesn't meet our security requirements».
# 2) com.android.vending.derived.apk.id -> Play Store перестаёт слать
#    CHECK_LICENSE на переподписанную сборку.
MANIFEST_PATCHES = (
    ("com.pairip.licensecheck.LicenseActivity",
     "com.pairip.licensecheck.LicenseActivitY"),
    ("com.android.vending.derived.apk.id",
     "com.android.vending.derived.apk.iD"),
)

# Точечное переименование: только package и authorities. Имена классов
# (me.tito.unlocker.MainActivity) трогать нельзя — в dex они прежние.
PKG_RENAME = {
    "me.tito.unlocker": "m.tito.unlockr.x",
    "me.tito.unlocker.IronsourceLifecycleProvider":
        "m.tito.unlockr.x.IronsourceLifecycleProvider",
    "me.tito.unlocker.firebaseinitprovider":
        "m.tito.unlockr.x.firebaseinitprovider",
    "me.tito.unlocker.androidx-startup":
        "m.tito.unlockr.x.androidx-startup",
    "me.tito.unlocker.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION":
        "m.tito.unlockr.x.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION",
}


def is_signature_entry(name: str) -> bool:
    upper = name.upper()
    if upper in {m.upper() for m in SIGNATURE_MARKERS}:
        return True
    if upper.startswith("META-INF/") and upper.endswith((".SF", ".RSA", ".DSA", ".EC")):
        return True
    return False


def main() -> int:
    if len(sys.argv) < 6:
        print(__doc__)
        return 1
    base = Path(sys.argv[1])
    arm64 = Path(sys.argv[2])
    out = Path(sys.argv[3])
    dexes = {Path(p).name: Path(p).read_bytes() for p in sys.argv[4:]}
    # SHA-256 сертификата подписи новой сборки (hex, без пробелов).
    # Им подменяется stamp-cert-sha256, который приложение сверяет со своим.
    stamp_hex = os.environ.get("STAMP_CERT_SHA256", "").strip().replace(":", "")
    stamp = bytes.fromhex(stamp_hex) if stamp_hex else None
    # для варианта-набора сплитов requiredSplitTypes должен остаться
    keep_required_splits = bool(os.environ.get("KEEP_REQUIRED_SPLITS"))
    no_libs = bool(os.environ.get("NO_LIBS"))

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
            payload = zin.read(name)
            if name == "AndroidManifest.xml":
                if os.environ.get("RENAME_PKG") == "1":
                    payload, cnt = rename_strings(payload, PKG_RENAME)
                    print(f"  манифест: точечно переименовано строк: {cnt}")
                if not keep_required_splits:
                    payload, n = patch_axml(payload, "base__abi,base__density", "")
                    if n:
                        print("  манифест: снято требование сплитов "
                              "(android:requiredSplitTypes)")
                for old_s, new_s in MANIFEST_PATCHES:
                    for enc in ("ascii", "utf-16-le"):
                        ob, nb = old_s.encode(enc), new_s.encode(enc)
                        if ob in payload:
                            payload = payload.replace(ob, nb)
                            print(f"  манифест: '{old_s}' -> '{new_s}'")
            elif name == "stamp-cert-sha256" and stamp is not None:
                if len(stamp) != len(payload):
                    raise SystemExit("размер stamp не совпал")
                payload = stamp
                print("  stamp-cert-sha256: подставлен хэш нового сертификата")
            zout.writestr(info, payload, compress_type=info.compress_type)

        with zipfile.ZipFile(arm64, "r") as zsplit:
            for info in (() if no_libs else zsplit.infolist()):
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
