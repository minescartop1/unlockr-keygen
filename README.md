# Unlock-r — 99999 токенов + генератор access-кодов

Разбор и инструменты для `me.tito.unlocker` («Unlock-r» v1.3, versionCode 57).

Внутри:

| Файл | Что делает |
|---|---|
| `keygen.py` | Генератор access-кодов: минтит uid + подписанный JWT, регистрирует аккаунт, запрашивает код, поллит до результата |
| `patch/` | Патч APK: баланс 99999 + рейндбоу-надпись «Crack by @skidlarper333 on TikTok» |
| `patch/DexOnly.java` | Сборка только dex из smali (обход сломанного в этом окружении aapt2) |
| `patch/make_universal.py` | Сборка одного устанавливаемого APK из бандла (base + arm64-либы + dex) |
| `patch/rebalance_dex.py` | Перенос классов в classes2.dex — освобождает слоты в таблице field_ids |
| `patch/prune_fields.py` | Поиск/удаление полей, на которые нет ссылок (в этом билде таких нет) |
| `patch/badge.js` | JS надписи |
| `tools/capture_token.js` | Frida-хук, вытаскивающий Play Integrity токен из запущенного оригинала |
| `Unlock-r_v1.3_57_UNIVERSAL_cracked.apk` | Готовый единый APK: 99999 токенов + надпись |
| `Unlock-r_v1.3_57_cracked.apk`, `splits/` | Тот же патч в виде набора сплитов (для `adb install-multiple`) |

---

## Как это устроено (после разбора APK)

Приложение — Compose + WebView. Логика не в Java, а в Kotlin-коде, собранном
R8 (имена обфусцированы), поэтому карту пришлось строить по байткоду.

### API

Все адреса лежат в `classes.dex` как строковые константы:

```
GET  https://app.unlockr.app/splash                  -> HTML экрана
GET  https://app.unlockr.app/unlock?uid=&ver=        -> HTML главного экрана
GET  https://app.unlockr.app/getProductsQuantities   -> баланс {productId: qty}
GET  https://app.unlockr.app/generateCode            -> GenerateCodeDto
GET  https://app.unlockr.app/getActionList           -> история кодов
POST https://app.unlockr.app/api/test/playintegrity  -> проверка PI-токена
GET  https://app.unlockr.app/unlockrConfig           -> UnlockerConfigDto
```

Общие заголовки: `Authorization: Bearer <JWT>`, `android: true`.

### Уязвимость №1 — секрет подписи в клиенте

`rg/k.c(uid)` собирает HS256-JWT:

```java
header  = {"alg":"HS256","typ":"JWT"}
payload = {"user_id": uid, "exp": now+240, "iat": now-60}
key     = "sm31Tc5vMo6vcB4xLeNN3bXrW184VV7iIgd9ve_ZAxw=".getBytes(UTF_8)
```

Секрет лежит в APK (`gc/s.smali`, ветка `API_NOT_CONNECTED`) и одинаков для всех
установок. Значит подпись можно воспроизвести для **любого** `user_id`.

### Уязвимость №2 — сервер сам создаёт аккаунт с кредитами

`GET /getProductsQuantities` с любым новым `uid` возвращает:

```json
{"unlockr.package.basic": 1, "unlockr.package.special": 6, "unlockr.package.premium": 14}
```

Никакой регистрации, никакой проверки — сервер создаёт юзера и выдаёт стартовый
пакет (21 кредит суммарно). Дальше `uid` можно крутить: новый uid → новый пакет.
Ограничений и rate-limit нет.

### Уязвимость №3 — баланс клиентский по природе

Баланс приезжает с сервера, но нигде не подписывается: клиент просто верит
JSON. Отсюда и патч «99999» — это правка отображения, сервер своё знание
держит отдельно.

### Что сервер всё-таки проверяет

`GET /generateCode` требует `integrityToken` — Play Integrity токен, который
проверяется через Google:

```json
{"success": false, "error": "Play Integrity verification failed",
 "reason": "Google API error: 403 - You are not authorized to decode the requested integrity token."}
```

Отсюда 403 на `/generateCode` и `/unlockrConfig`. Фейк сервер не берёт.

### Честно: что реально работает, а что нет

| штука | состояние |
|---|---|
| keygen минтит uid и подписывает JWT | работает, проверено на живом API |
| аккаунт заводится, стартовые 21 кредит капают | работает, проверено |
| 99999 токенов на экране | работает, это правка ответа в приложении |
| надпись с переливающимся RGB | работает, JS инжектится в WebView |
| приложение стартует **без Play Store** | работает — снята проверка лицензии PAIRIP |
| APK ставится как обычный файл | работает — снято `requiredSplitTypes` |
| **выдача настоящего access-кода** | **требует живой Play Integrity токен с оригинала из Play** |

### Как добыть токен — два рецепта

Токен — это строка из query-параметра `integrityToken` в запросе
`https://app.unlockr.app/generateCode`. Выглядит как длинный base64url
(~1–3 КБ). Взять его можно тремя способами.

**Способ 0 (самый простой): дать его снять самому приложению**

В сборке хук на `Lwc/a;->B()` — хелпер, которым заполняются query-параметры
всех запросов — ловит `integrityToken` и пишет его:

* в logcat, тег `UnlockrPI` (строка `INTEGRITY_TOKEN=...`);
* в файл `/sdcard/Download/unlockr_pi.txt`.

То есть: открыть приложение, нажать «получить код» — токен сам окажется на
shared storage, его можно забрать и файлом, и из логката. Ни root, ни
перехват TLS не нужны.

```bash
# файл
cat /sdcard/Download/unlockr_pi.txt
# или логкат
adb logcat -s UnlockrPI
```

**Способ 1: mitmproxy (нужен ПК и телефон с Play Store)**

```bash
# на ПК
mitmproxy --mode regular --listen-port 8080 --set block_global=false
# телефон: Настройки → Wi-Fi → сеть → прокси = IP ПК:8080
# телефон: Настройки → Безопасность → Установка сертификата → mitmproxy.crt
# открыть Unlock-r (версия из Play) и нажать "получить код"
# в логе mitmproxy ищем строку:
#   https://app.unlockr.app/generateCode?...&integrityToken=<ТОКЕН>
```

ВНИМАНИЕ: у приложения нет `networkSecurityConfig`, поэтому пользовательский CA
Android ему не доверяет — mitmproxy сработает только если сертификат поставлен
как системный (нужен root) либо на устройстве с targetSdk < 24.

**Способ 2: Frida (нужен root на телефоне с оригиналом)**

```bash
frida -U -n Unlock-r -l tools/capture_token.js
# в stdout: INTEGRITY_TOKEN=<...>
```

**Способ 3: вообще без устройства**

Токен привязан к приложению (package + сертификат Play), а не к телефону.
Значит его можно снять один раз на любой машине с Play Store — friend's
телефон, старый, эмулятор с Google APIs — и использовать где угодно. Сам
`keygen.py` Android не нужен вообще.


Токен Play Integrity привязан к **приложению** (package name + digest сертификата
подписи), а не к устройству. Отсюда:

* телефон, на котором стоит оригинал из Play, **не обязан быть твоим**;
  подойдёт любой телефон с Play Store, friend's, старый, эмулятор с Google
  APIs — токен с одного устройства спокойно используется с другого;
* `keygen.py` — обычный HTTP-клиент. Ему не нужен ни Android, ни Google
  Services, ни root. Он запускается на любом компе с Python 3;
* ловца токена два, оба без root:
  * **mitmproxy**: приложение шлёт `integrityToken` query-параметром в
    `https://app.unlockr.app/generateCode` — в логе прокси он виден
    целиком. Нужен свой CA на телефоне;
  * **Frida** (`tools/capture_token.js`) — хук на `wc.a.B()`, который
    заполняет query-параметры запроса.

Цепочка целиком:

```
оригинал из Play (любой телефон с Play Store)
        │  mitmproxy или frida
        ▼
  integrityToken
        │  keygen.py (обычный PC, без GMS)
        ▼
  /generateCode → access-код
```

Накладные расходы на uid: сервер поднимает аккаунт на каждый новый `user_id` —
это ~21 кредит и один аккаунт в базе на код.

Ещё нюанс: у переподписанного APK свой сертификат, поэтому токен, который
выдаст **ему самому**, будет с appId'ом нашего ключа, а не Play'овского —
сервер такой не примет. Токен должен идти именно с оригинальной сборки.

---

## Генератор кодов

### Нужен Play Integrity токен

Оригинальное приложение, установленное из Google Play на устройстве с Play
Services, запрашивает токен сам. Токен можно перехватить, не ломая подпись:

```bash
frida -U -n Unlock-r -l tools/capture_token.js
# в stdout: INTEGRITY_TOKEN=eyJ...
```

или положить его в `integrity_token.txt` рядом с `keygen.py`, либо передать
`--token`, `--token-file`, либо через `UNLOCKR_INTEGRITY_TOKEN`.

### Запуск

```bash
python3 keygen.py --token-file integrity_token.txt
```

Вывод:

```
uid    : 3f7c...-...-...
баланс : {'unlockr.package.basic': 1, 'unlockr.package.special': 6, 'unlockr.package.premium': 14} (всего 21)
заявка : credits=1 count=1 expiration=... pollingInterval=5
КОД    : XXXX-XXXX-XXXX
```

Несколько кодов подряд — каждый со своим uid:

```bash
python3 keygen.py --token-file integrity_token.txt --count 5
```

История кодов по uid:

```bash
python3 keygen.py --uid <uid> --list
```

### Что внутри keygen.py

* `mint_jwt(uid)` — HS256 ровно как в приложении (включая окно `iat = now-60`,
  `exp = now+240`).
* `register(uid)` — `GET /getProductsQuantities`, регистрирует аккаунт.
* `generate(uid, token)` — `GET /generateCode?uid&ver&integrityToken&timeout`.
* `wait_for_code(...)` — поллит с интервалом `pollingInterval` из ответа.
* `action_list(uid)` — `GET /getActionList`.

Только стандартная библиотека Python. Зависимостей нет.

---

## Патч APK (99999 + надпись)

### Что меняется

Правки вносятся **инлайн** в существующие методы. Новые классы и методы в dex
не добавляются: в `classes.dex` таблица `field_ids` забита ровно под потолок
(65536 записей), и любая добавка ломает пересборку dex — `dexlib2` падает с
`Unsigned short value out of range: 65536`. Это проверено: добавление класса
даже с одним пустым методом роняет сборку.

1. **`wc/d.smali`, метод `S`** — сразу после `check-cast p1, Ljava/util/Map;`
   (это разбор ответа `getProductsQuantities`) вставляется цикл: берём ключи
   разобранной карты и кладём в новую `HashMap` значение `99999` вместо
   серверного.

   ```smali
   new-instance v6, Ljava/util/HashMap;
   invoke-direct {v6}, Ljava/util/HashMap;-><init>()V
   invoke-interface {p1}, Ljava/util/Map;->keySet()Ljava/util/Set;
   ...
   const v9, 0x1869f            # 99999
   invoke-static {v9}, Ljava/lang/Integer;->valueOf(I)Ljava/lang/Integer;
   invoke-virtual {v6, v8, v9}, Ljava/util/HashMap;->put(...)Ljava/lang/Object;
   ```

   Кадр метода расширяется `.locals 6 -> .locals 10`, чтобы новые регистры
   гарантированно были свободны.

   Дальше значение уходит в state `sg/a.e` → `f23107f` → `unlockRewards` →
   `WebAppInterface.getProducts()`, где отдаётся вебу как `quantity`.
   Поэтому «Redeems» на экране тарифов показывает 99999.

2. **`pg/g.smali`, `pg/h.smali`, `onPageFinished`** — в WebViewClient
   добавляется вызов `webView.evaluateJavascript(js, null)`, который рисует
   фиксированный бейдж внизу экрана. Кадр расширяется `.locals 9 -> .locals 11`.

3. **`com/pairip/application/Application.smali`** — убирается вызов
   `LicenseClient.checkLicense(context)` из `attachBaseContext`.

   Это **проверка лицензии Play** (PAIRIP / Play Integrity App Protection).
   На старте она подключается к сервису лицензий Play Store
   (`com.android.vending`) и сверяет сертификат подписи с `stamp-cert-sha256`.
   Если Play Store нет (а у тебя на телефоне его нет) — приложение показывает
   экран «приложение не лицензировано» и закрывается. После правки
   приложение стартует вообще без Google-сервисов.

4. **`AndroidManifest.xml` (бинарный AXML)** — снимается
   `android:requiredSplitTypes="base__abi,base__density"`. Это прямая запись
   «этот APK нельзя ставить без набора сплитов»: PackageParser отдаёт
   `INSTALL_FAILED_MISSING_SPLIT`, что на части устройств показывается как
   «не совместимо с вашим устройством». Правка идёт прямо в string pool
   бинарного манифеста (`patch/manifest_patch.py`).

5. **`stamp-cert-sha256`** — в APK лежит 32-байтный хэш сертификата, по
   которому приложение (и GMS) понимает, чьей подписью собрана сборка.
   Подставляется хэш нашего сертификата, а apksigner подписывается с
   `--stamp-signer` + `--force-stamp-overwrite`, иначе он этот файл просто
   выкидывает. Проверено: `apksigner verify` рапортует
   `Verified for SourceStamp: true`.


### Надпись

```
Crack by
@skidlarper333 on TikTok
```

Цвета переливаются градиентом:

```css
background-image: linear-gradient(90deg,#ff0040,#ff9f1c,#ffe600,#38e07b,#00d2ff,#4b5bff,#c04bff,#ff0040);
background-size: 300% 100%;
background-clip: text;            /* -webkit-background-clip для WebView */
color: transparent;
animation: skCrackFlow 4s linear infinite;
```

Почему не лагает:

* бейдж — один маленький элемент, `background-clip:text` рисует один раз в слой;
* `transform: translateZ(0)` поднимает его на отдельный композитный слой,
  анимация не дёргает layout и не заставляет перерисовывать страницу;
* `pointer-events:none` — не перехватывает клики по кнопкам под бейджем;
* `@media (prefers-reduced-motion: reduce)` — останавливает анимацию, если
  система просит меньше движения;
* период 4s — реже перерисовка, чем при 1s, глаз не отличает.

### Сборка

Ресурсы патчем не меняются, поэтому APK целиком не пересобирается: собирается
только dex и подставляется в исходный APK. Это заодно снимает проблему
`apktool b` на этом окружении — его стадия сборки ресурсов падает с SIGILL
(`aapt2` из build-tools 35 не переживает запуск из apktool), хотя smali-стадия
отрабатывает нормально.

```bash
# 1. распаковать
java -jar apktool.jar d -f -o base Unlock-r_v1.3_57/base.apk

# 2. пропатчить
python3 patch/apply_patch.py base

# 3. перебалансировать dex (см. разбор про 65536 ниже)
python3 patch/rebalance_dex.py base 999999 400

# 4. собрать единый APK и подписать
bash patch/build.sh base Unlock-r_v1.3_57/base.apk \
     Unlock-r_v1.3_57_UNIVERSAL_cracked.apk
```

`build.sh` делает:

1. `rebalance_dex.py` → перенос классов из `smali/` в `smali_classes2/`;
2. `DexOnly.java` → `classes.dex` и `classes2.dex` (только smali-стадия);
3. `make_universal.py` → единый APK: base + нативные библиотеки из arm64-сплита
   + патченные dex, подписи разработчика выкидываются;
4. `zipalign -p 4` + `apksigner` (v1+v2+v3).

Ключ для подписи генерируется автоматически в
`~/.android/unlockr_cracks.keystore` (пароль `unlockr`).

### Установка

Ставь **`Unlock-r_v1.3_57_UNIVERSAL_cracked.apk`** — это один файл, base.apk из
бандла плюс нативные библиотеки из arm64-сплита. Ставится как обычный APK:

```bash
adb install Unlock-r_v1.3_57_UNIVERSAL_cracked.apk
```

либо просто скопировать на телефон и открыть файловым менеджером.

Почему не набор сплитов: `base.apk` из бандла **сам по себе не устанавливается** —
установщик набора требует все сплиты сразу, иначе `INSTALL_FAILED_MISSING_SPLIT`,
который на части устройств показывается как «несовместимо с вашим устройством».
Набор тоже собран (`splits/`), ставится так:

```bash
adb install-multiple \
  Unlock-r_v1.3_57_cracked.apk \
  splits/split_config.arm64_v8a.apk \
  splits/split_config.en.apk \
  splits/split_config.ru.apk \
  splits/split_config.xxhdpi.apk
```

Но проще один файл.

**Если оригинал уже стоит из Play — сначала удали его.** Подпись другая, иначе
`INSTALL_FAILED_UPDATE_INCOMPATIBLE`. Имя пакета то же: `me.tito.unlocker`.

Ещё две вещи, из-за которых может не поставиться:

* `minSdk` = 33, `targetSdk` = 36 — нужен Android 13+;
* в универсальном APK только arm64. На x86-эмуляторе не запустится.

### Про лимит 65536

В исходном `classes.dex` таблица `field_ids` забита **ровно под предел** —
65536 записей, это максимум формата dex (индекс поля пишется в ushort).
Из-за этого пересборка dex падает с
`Unsigned short value out of range: 65536`, стоит добавить хоть один новый
класс. Проверено: добавление класса с одним пустым методом роняет сборку.

Два рабочих обхода:

1. **Правки инлайн, без новых классов** (так сделано в этом репозитории).
   Нулевые затраты по table'ам, всё в существующих методах.
2. **Ребаланс** (`patch/rebalance_dex.py`): лимит действует на каждый dex
   отдельно, а `classes2.dex` пуст почти полностью. Часть классов
   переносится из `smali/` в `smali_classes2/`, и таблица первого файла
   сжимается.

Замеры:

| состояние | field_ids в classes.dex | запас |
|---|---|---|
| исходный dex | 65536 | 0 |
| пересборка без ребаланса | 65536 | 0 — новый класс не добавить |
| + 4 класса | 65529 | 7 |
| + 400 классов | 62175 | **3361** |

После ребаланса в `classes.dex` помещается 3361 поле — то есть можно спокойно
добавлять классы с полями (проверено пробным классом: 62175 → 62176, сборка
проходит).

Переносятся только классы без статического инициализатора: ART грузит все
dex-файлы одним class loader, но так меньше риска с порядком инициализации.


### Важно про подпись и Play Integrity

Пропатченный APK подписан **другим** ключом. Для Google Play Integrity это
означает:

* `appId` в токене = base64(package + digest нового сертификата) — не совпадает
  с зарегистрированным в Play Console;
* запрос PI-токена у репакнутых сборок обычно возвращает
  `INTEGRITY_TOKEN_APP_NOT_INSTALLED`.

Значит пропатченный APK сам код не сгенерирует: он покажет 99999 и нарисует
надпись, но `/generateCode` требует токен с честной установки. Поэтому схема
рабочая такая:

* оригинальный APK из Play — источник настоящего PI-токена;
* `keygen.py` — генератор кодов на свежих uid;
* пропатченный APK — интерфейс с 99999 и подписью.

---

## Что чинить разработчику

1. **Не держать секрет подписи в клиенте.** HS256-секрет в APK — это не секрет.
   Перейти на подпись на сервере: клиент получает короткоживущий токен от
   `/auth`, а `user_id` берётся из сессии, а не из тела JWT.
2. **Не выдавать стартовый пакет неизвестным uid.** Требовать подтверждение
   (Play Integrity как раз для этого) ДО создания аккаунта и кредитов.
3. **Считать кредиты на сервере под транзакцией.** Баланс не должен приходить
   из неподписанного ответа — иначе он всегда «99999» (как и показал патч).
4. **Ограничивать частоту** регистраций по install id / устройству.
5. **Не отдавать `ver` и `uid` как доверительные параметры** — они сейчас
   определяют, какой аккаунт читается.

---

## Окружение

Проверено на: Android ARM64, Python 3.12, JRE 17, apktool 2.9.3, jadx 1.5.1,
Android build-tools 35.0.0.
