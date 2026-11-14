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

    invoke-virtual {p0, v9, v10}, Landroid/webkit/WebView;->evaluateJavascript(Ljava/lang/String;Landroid/webkit/ValueCallback;)V
"""

LICENSE_CALL = """    invoke-static {p1}, Lcom/pairip/licensecheck/LicenseClient;->checkLicense(Landroid/content/Context;)V
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


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    root = Path(sys.argv[1]).resolve()
    if not (root / "AndroidManifest.xml").exists():
        raise SystemExit(f"не похоже на apktool-дерево: {root}")

    js = smali_string((HERE / "badge.js").read_text(encoding="utf-8"))

    print("1/3 баланс -> 99999 (wc/d.smali)")
    patch_tokens(root / "smali" / "wc" / "d.smali")

    print("2/3 надпись (pg/g.smali, pg/h.smali)")
    for name in ("g.smali", "h.smali"):
        patch_badge(root / "smali_classes2" / "pg" / name, js)

    print("3/3 проверка лицензии Play (pairip)")
    patch_license(root / "smali" / "com" / "pairip" / "application" / "Application.smali")

    print("\nготово. собирай: bash build.sh <каталог> <выходной apk>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
