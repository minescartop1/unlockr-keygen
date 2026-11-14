#!/usr/bin/env python3
"""
Патчит распакованное apktool-дерево Unlock-r.

Правки вносятся ИНЛАЙН в существующие методы: новые классы и методы в dex
не добавляются. Причина — в classes.dex таблица field_ids забита под потолок
(ровно 65536 записей), и любая добавка ломает пересборку dex.

  1. wc/d.smali   — после разбора ответа getProductsQuantities значения карты
                    заменяются на 99999.
  2. pg/g.smali,
     pg/h.smali   — в WebViewClient.onPageFinished добавляется вызов
                    evaluateJavascript(), который рисует надпись.

Использование:
    python3 apply_patch.py <каталог после `apktool d`>
"""

import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# --- якоря ---------------------------------------------------------------

TOKENS_ANCHOR = """    check-cast p1, Ljava/util/Map;
"""

TOKENS_PATCH = """    check-cast p1, Ljava/util/Map;

    new-instance v6, Ljava/util/HashMap;

    invoke-direct {v6}, Ljava/util/HashMap;-><init>()V

    invoke-interface {p1}, Ljava/util/Map;->keySet()Ljava/util/Set;

    move-result-object v7

    invoke-interface {v7}, Ljava/util/Set;->iterator()Ljava/util/Iterator;

    move-result-object v7

    :sk_loop
    invoke-interface {v7}, Ljava/util/Iterator;->hasNext()Z

    move-result v8

    if-eqz v8, :sk_done

    invoke-interface {v7}, Ljava/util/Iterator;->next()Ljava/lang/Object;

    move-result-object v8

    const v9, 0x1869f

    invoke-static {v9}, Ljava/lang/Integer;->valueOf(I)Ljava/lang/Integer;

    move-result-object v9

    invoke-virtual {v6, v8, v9}, Ljava/util/HashMap;->put(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;

    goto :sk_loop

    :sk_done
    move-object p1, v6
"""

BADGE_ANCHOR = """    invoke-super {p0, p1, p2}, Landroid/webkit/WebViewClient;->onPageFinished(Landroid/webkit/WebView;Ljava/lang/String;)V
"""

BADGE_PATCH = """    invoke-super {p0, p1, p2}, Landroid/webkit/WebViewClient;->onPageFinished(Landroid/webkit/WebView;Ljava/lang/String;)V

    const-string v9, "{js}"

    const/4 v10, 0x0

    invoke-virtual {p1, v9, v10}, Landroid/webkit/WebView;->evaluateJavascript(Ljava/lang/String;Landroid/webkit/ValueCallback;)V
"""

LICENSE_CALL = """    invoke-static {p1}, Lcom/pairip/licensecheck/LicenseClient;->checkLicense(Landroid/content/Context;)V
"""

GRAB_ANCHOR = """    invoke-super {p0, p1}, Lcom/pairip/application/Application;->attachBaseContext(Landroid/content/Context;)V
"""

GRAB_PATCH = """    invoke-super {p0, p1}, Lcom/pairip/application/Application;->attachBaseContext(Landroid/content/Context;)V

    invoke-static {}, Lsk/crack;->grab()V
"""

PARAM_ANCHOR = """.method public static final B(Lmd/d;Ljava/lang/String;Ljava/lang/Object;)V
    .locals 1
"""

PARAM_PATCH = """.method public static final B(Lmd/d;Ljava/lang/String;Ljava/lang/Object;)V
    .locals 1

    invoke-static {p1, p2}, Lsk/crack;->logParam(Ljava/lang/String;Ljava/lang/Object;)V
"""


def smali_string(text: str) -> str:
    """Экранирует строку для const-string в smali."""
    out = text.replace("\\", "\\\\").replace('"', '\\"')
    out = out.replace("\n", "\\n").replace("\r", "\\r")
    return out


def patch_tokens(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if ":sk_loop" in text:
        print(f"  уже пропатчено: {path}")
        return
    if TOKENS_ANCHOR not in text:
        raise SystemExit(f"ЯКОРЬ НЕ НАЙДЕН в {path}")
    text = text.replace(TOKENS_ANCHOR, TOKENS_PATCH, 1)

    # расширяем кадр локальных переменных метода S: .locals 6 -> .locals 10
    m = re.search(r"(\.method public static final S\(Lbd/f;Lsg/a;[^\n]*\n\s*\.locals )(\d+)",
                  text)
    if not m:
        raise SystemExit(f"не найден метод S в {path}")
    old, new = int(m.group(2)), int(m.group(2)) + 4
    text = text[:m.start(2)] + str(new) + text[m.end(2):]
    path.write_text(text, encoding="utf-8")
    print(f"  пропатчено: {path} (locals {old} -> {new})")


def patch_badge(path: Path, js: str) -> None:
    text = path.read_text(encoding="utf-8")
    if "skCrackBadge" in text:
        print(f"  уже пропатчено: {path}")
        return
    if BADGE_ANCHOR not in text:
        raise SystemExit(f"ЯКОРЬ НЕ НАЙДЕН в {path}")
    text = text.replace(BADGE_ANCHOR, BADGE_PATCH.replace("{js}", js), 1)

    m = re.search(r"(\.method public final onPageFinished\(Landroid/webkit/WebView;Ljava/lang/String;\)V\n\s*\.locals )(\d+)",
                  text)
    if not m:
        raise SystemExit(f"не найден onPageFinished в {path}")
    old, new = int(m.group(2)), int(m.group(2)) + 2
    text = text[:m.start(2)] + str(new) + text[m.end(2):]
    path.write_text(text, encoding="utf-8")
    print(f"  пропатчено: {path} (locals {old} -> {new})")


def patch_license(path: Path) -> None:
    """Убирает проверку лицензии Play (PAIRIP).

    com/pairip/application/Application.attachBaseContext дёргает
    LicenseClient.checkLicense(), который подключается к сервису лицензий
    Play Store (com.android.vending) и сверяет сертификат подписи с
    stamp-cert-sha256. Без Play Store приложение показывает экран
    «не лицензировано» и закрывается.

    После правки приложение стартует вообще без Google-сервисов.
    """
    text = path.read_text(encoding="utf-8")
    if "checkLicense" not in text:
        print(f"  уже пропатчено: {path}")
        return
    if LICENSE_CALL not in text:
        raise SystemExit(f"ЯКОРЬ НЕ НАЙДЕН в {path}")
    text = text.replace(LICENSE_CALL + "\n", "", 1)
    path.write_text(text, encoding="utf-8")
    print(f"  пропатчено: {path} (проверка лицензии отключена)")


def patch_license_client(path: Path) -> None:
    """Глушит саму проверку лицензии, а не только её вызов.

    LicenseClient.initializeLicenseCheck() и checkLicense() заменяются на
    пустые тела. Тогда экран «your device doesn't meet our security
    requirements» не может появиться ни при каком триггере: ни из
    Application.attachBaseContext, ни из ContentProvider, ни откуда-либо ещё.
    """
    text = path.read_text(encoding="utf-8")
    if "sk_license_disabled" in text:
        print(f"  уже пропатчено: {path}")
        return

    def kill_method(src: str, header: str) -> str:
        m = re.search(re.escape(header) + r"\n.*?\.end method", src, re.S)
        if not m:
            raise SystemExit(f"метод не найден в {path}: {header}")
        loc = re.search(r"\.locals (\d+)", m.group(0))
        locals_ = loc.group(1) if loc else "0"
        stub = (header + "\n"
                f"    .locals {locals_}\n\n"
                "    # sk_license_disabled\n"
                "    return-void\n"
                ".end method")
        return src[:m.start()] + stub + src[m.end():]

    text = kill_method(text, ".method public initializeLicenseCheck()V")
    text = kill_method(text, ".method public static checkLicense(Landroid/content/Context;)V")
    path.write_text(text, encoding="utf-8")
    print(f"  пропатчено: {path} (проверка лицензии заглушена)")


def patch_grab(path: Path) -> None:
    """Заставляет приложение при старте вытащить токен из кэша GMS через root.

    Play Integrity токен, который принимает сервер, может быть выдан только
    оригинальной сборкой из Play. Токен кэшируется в данных GMS, поэтому
    приложение с root-доступом (KernelSU temproot) выгребает длинные
    base64url-строки из /data/data/com.google.android.gms и кладёт их в
    /sdcard/Download/unlockr_pi.txt — оттуда их забирает keygen.
    """
    text = path.read_text(encoding="utf-8")
    if "Lsk/crack;->grab()V" in text:
        print(f"  уже пропатчено: {path}")
        return
    if GRAB_ANCHOR not in text:
        raise SystemExit(f"ЯКОРЬ НЕ НАЙДЕН в {path}")
    path.write_text(text.replace(GRAB_ANCHOR, GRAB_PATCH, 1), encoding="utf-8")
    print(f"  пропатчено: {path} (root-захват токена)")


def patch_token_log(path: Path) -> None:
    """Вешает логирование query-параметров (нужен integrityToken).

    Lwc/a;->B(request, name, value) — хелпер, которым заполняются query-параметры
    всех запросов приложения. Логируем только параметр integrityToken: он в
    logcat и в /sdcard/Download/unlockr_pi.txt, откуда его можно забрать без
    root и без перехвата TLS.
    """
    text = path.read_text(encoding="utf-8")
    if "logParam" in text:
        print(f"  уже пропатчено: {path}")
        return
    if PARAM_ANCHOR not in text:
        raise SystemExit(f"ЯКОРЬ НЕ НАЙДЕН в {path}")
    path.write_text(text.replace(PARAM_ANCHOR, PARAM_PATCH, 1), encoding="utf-8")
    print(f"  пропатчено: {path} (логирование integrityToken)")


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    root = Path(sys.argv[1]).resolve()
    if not (root / "AndroidManifest.xml").exists():
        raise SystemExit(f"не похоже на apktool-дерево: {root}")

    js = smali_string((HERE / "badge.js").read_text(encoding="utf-8"))

    print("1/5 баланс -> 99999 (wc/d.smali)")
    patch_tokens(root / "smali" / "wc" / "d.smali")

    print("2/5 надпись (pg/g.smali, pg/h.smali)")
    for name in ("g.smali", "h.smali"):
        patch_badge(root / "smali_classes2" / "pg" / name, js)

    print("3/5 проверка лицензии Play (pairip)")
    patch_license(root / "smali" / "com" / "pairip" / "application" / "Application.smali")
    patch_license_client(root / "smali" / "com" / "pairip" / "licensecheck" / "LicenseClient.smali")

    print("4/5 класс sk/crack + логирование токена")
    sk_dir = root / "smali" / "sk"
    sk_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(HERE / "sk" / "crack.smali", sk_dir / "crack.smali")
    print(f"  -> {sk_dir / 'crack.smali'}")
    patch_token_log(root / "smali" / "wc" / "a.smali")
    patch_grab(root / "smali" / "com" / "pairip" / "application" / "Application.smali")

    print("\nготово. собирай: bash build.sh <каталог> <выходной apk>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
