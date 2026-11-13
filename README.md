# Unlock-r — 99999 токенов + генератор access-кодов

Разбор и инструменты для `me.tito.unlocker` («Unlock-r» v1.3, versionCode 57).

Внутри:

| Файл | Что делает |
|---|---|
| `keygen.py` | Генератор access-кодов: минтит uid + подписанный JWT, регистрирует аккаунт, запрашивает код, поллит до результата |
| `patch/` | Патч APK: баланс 99999 + рейндбоу-надпись «Crack by @skidlarper333 on TikTok» |
| `patch/DexOnly.java` | Сборка только dex из smali (обход сломанного в этом окружении aapt2) |
| `patch/inject_dex.py` | Подстановка dex в исходный APK без пересборки ресурсов |
| `patch/badge.js` | JS надписи |
| `tools/capture_token.js` | Frida-хук, вытаскивающий Play Integrity токен из запущенного оригинала |
| `Unlock-r_v1.3_57_cracked.apk`, `splits/` | Готовый пропатченный APK и подписанные сплиты |

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

# 3. собрать и подписать
bash patch/build.sh base Unlock-r_v1.3_57/base.apk out/Unlock-r_cracked.apk \
     Unlock-r_v1.3_57 out/splits
```

`build.sh` делает:

1. `DexOnly.java` → `classes.dex` и `classes2.dex` (только smali-стадия);
2. `inject_dex.py` → подмена dex в исходном APK, остальные записи байт-в-байт;
3. `zipalign -p 4` + `apksigner` (v1+v2+v3);
4. подпись сплитов тем же ключом — иначе набор не установится.

Ключ для подписи генерируется автоматически в
`~/.android/unlockr_cracks.keystore` (пароль `unlockr`).

### Установка

Набор ставится через `adb install-multiple`:

```bash
adb install-multiple \
  Unlock-r_v1.3_57_cracked.apk \
  splits/split_config.arm64_v8a.apk \
  splits/split_config.en.apk \
  splits/split_config.ru.apk \
  splits/split_config.xxhdpi.apk
```

Сплиты обязательны: `base.apk` не содержит нативных библиотек
(`libtapjoy.so`, `libandroidx.graphics.path.so`), они лежат в arm64-сплите.

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
