#!/usr/bin/env python3
"""
Unlock-r access code generator.

Работает напрямую с API app.unlockr.app:
  1. минтит uid + подписанный HS256-токен (секрет лежит в самом APK),
  2. регистрирует аккаунт через /getProductsQuantities,
  3. запрашивает код через /generateCode,
  4. поллит ответ до появления поля code.

Токен целостности (Play Integrity) обязателен для /generateCode — сервер
проверяет его через Google. Брать его надо с честно установленного оригинала
приложения: файл integrity_token.txt рядом со скриптом, переменная окружения
UNLOCKR_INTEGRITY_TOKEN или аргумент --token.

Использование:
    python3 keygen.py --token <play_integrity_token>
    python3 keygen.py --token-file integrity_token.txt --count 3
    python3 keygen.py --uid <существующий uid> --token <token>
"""

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

API = "https://app.unlockr.app"

# Секрет подписи HS256, извлечённый из APK (gc.s -> case API_NOT_CONNECTED).
JWT_SECRET = b"sm31Tc5vMo6vcB4xLeNN3bXrW184VV7iIgd9ve_ZAxw="

DEFAULT_VER = "1.3"
USER_AGENT = "Unlockr/1.3 (Linux; Android 14)"


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def mint_jwt(uid: str) -> str:
    """HS256 JWT ровно так, как собирает приложение: user_id / exp / iat."""
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"user_id": uid, "exp": now + 240, "iat": now - 60}
    part_h = b64url(json.dumps(header, separators=(",", ":")).encode())
    part_p = b64url(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{part_h}.{part_p}".encode("ascii")
    signature = hmac.new(JWT_SECRET, signing_input, hashlib.sha256).digest()
    return f"{part_h}.{part_p}.{b64url(signature)}"


def request(method: str, path: str, uid: str, params: dict | None = None,
            body: bytes | None = None) -> tuple[int, bytes, dict]:
    url = API + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", "Bearer " + mint_jwt(uid))
    req.add_header("android", "true")
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Accept", "application/json, text/html;q=0.9")
    if body is not None:
        req.add_header("Content-Type", "application/json; charset=UTF-8")
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            return resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as err:
        return err.code, err.read(), dict(err.headers)
    except urllib.error.URLError as err:
        raise SystemExit(f"сеть недоступна: {err}")


def parse_json(raw: bytes):
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def register(uid: str) -> dict:
    """GET /getProductsQuantities — баланс по пакетам; сервер сам создаёт аккаунт."""
    status, raw, _ = request("GET", "/getProductsQuantities", uid)
    if status != 200:
        raise SystemExit(f"getProductsQuantities -> HTTP {status}: {raw[:200]!r}")
    data = parse_json(raw) or {}
    return {k: int(v) for k, v in data.items()}


def generate(uid: str, integrity_token: str, ver: str = DEFAULT_VER) -> dict:
    """GET /generateCode — заявка на код."""
    params = {
        "uid": uid,
        "ver": ver,
        "integrityToken": integrity_token,
        "timeout": 5,
    }
    status, raw, _ = request("GET", "/generateCode", uid, params)
    if status == 403:
        raise PermissionError(
            "сервер отклонил Play Integrity токен (HTTP 403). "
            "Нужен живой токен с оригинального приложения."
        )
    if status != 200:
        raise RuntimeError(f"generateCode -> HTTP {status}: {raw[:300]!r}")
    data = parse_json(raw)
    if data is None:
        raise RuntimeError(f"generateCode вернул не-JSON: {raw[:300]!r}")
    return data


def action_list(uid: str) -> list:
    """GET /getActionList — история полученных кодов (RedeemedCode[])."""
    status, raw, _ = request("GET", "/getActionList", uid, {"uid": uid})
    if status != 200:
        return []
    data = parse_json(raw)
    return data if isinstance(data, list) else []


def wait_for_code(uid: str, dto: dict, integrity_token: str, ver: str,
                  deadline_s: int = 300) -> dict:
    """Поллинг: код может прийти не сразу, сервер отдаёт pollingInterval."""
    interval = int(dto.get("pollingInterval") or 0) or 5
    expires = int(dto.get("expiration") or 0)
    started = time.time()

    while time.time() - started < deadline_s:
        code = dto.get("code")
        if code:
            return dto
        if expires and time.time() > expires:
            raise RuntimeError("истёк срок ожидания кода (expiration)")
        time.sleep(min(max(interval, 2), 30))
        try:
            dto = generate(uid, integrity_token, ver)
        except PermissionError:
            raise
        except RuntimeError:
            pass

    raise TimeoutError("код не появился за отведённое время")


def read_token(args) -> list[str]:
    """Возвращает список кандидатов токенов (файл может содержать их много)."""
    raw = ""
    if args.token:
        raw = args.token
    elif args.token_file:
        with open(args.token_file, "r", encoding="utf-8") as fh:
            raw = fh.read()
    else:
        env = os.environ.get("UNLOCKR_INTEGRITY_TOKEN")
        if env:
            raw = env
        else:
            default = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "integrity_token.txt")
            if os.path.exists(default):
                with open(default, "r", encoding="utf-8") as fh:
                    raw = fh.read()
            else:
                shared = "/sdcard/Download/unlockr_pi.txt"
                if os.path.exists(shared):
                    with open(shared, "r", encoding="utf-8") as fh:
                        raw = fh.read()
    if not raw.strip():
        raise SystemExit(
            "нет Play Integrity токена.\n"
            "Передай --token <значение>, --token-file <путь> или положи файл "
            "integrity_token.txt рядом со скриптом.\n"
            "Либо открой приложение и нажми «получить код» — оно само выложит "
            "токен в /sdcard/Download/unlockr_pi.txt.\n"
            "Токен берётся с оригинального приложения (см. README, раздел «Токен»)."
        )
    out = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if "=" in line and not line.startswith("ey") and "INTEGRITY_TOKEN" in line:
            line = line.split("=", 1)[1].strip()
        if len(line) > 40 and line not in out:
            out.append(line)
    if not out:
        raise SystemExit("в файле токенов нет подходящих строк")
    return out


def run_one(uid: str, token: str, ver: str) -> dict:
    balance = register(uid)
    total = sum(balance.values())
    print(f"uid    : {uid}")
    print(f"баланс : {balance} (всего {total})")

    dto = generate(uid, token, ver)
    print(f"заявка : credits={dto.get('credits')} "
          f"count={dto.get('count')} "
          f"expiration={dto.get('expiration')} "
          f"pollingInterval={dto.get('pollingInterval')}")

    dto = wait_for_code(uid, dto, token, ver)
    print(f"КОД    : {dto.get('code')}")
    if dto.get("redeem"):
        print(f"redeem : {dto.get('redeem')}")
    return dto


def try_tokens(uid: str, tokens: list[str], ver: str) -> tuple[dict, str]:
    """Перебирает кандидатов: сервер принимает только токен от сборки из Play."""
    last = None
    for i, tok in enumerate(tokens, 1):
        print(f"\n-- кандидат {i}/{len(tokens)} ({len(tok)} симв.) --")
        try:
            return run_one(uid, tok, ver), tok
        except PermissionError as err:
            last = err
            print(f"  отказ: {err}")
        except Exception as err:  # noqa: BLE001
            last = err
            print(f"  ошибка: {err}")
    raise SystemExit(f"ни один токен не подошёл. последняя ошибка: {last}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Unlock-r code generator")
    ap.add_argument("--uid", help="использовать существующий uid вместо нового")
    ap.add_argument("--token", help="Play Integrity токен")
    ap.add_argument("--token-file", help="файл с Play Integrity токеном(ами)")
    ap.add_argument("--ver", default=DEFAULT_VER, help="версия приложения (ver)")
    ap.add_argument("--count", type=int, default=1, help="сколько кодов получить")
    ap.add_argument("--list", action="store_true",
                    help="показать историю кодов для uid")
    args = ap.parse_args()

    if args.list:
        uid = args.uid or input("uid: ").strip()
        for item in action_list(uid):
            print(json.dumps(item, ensure_ascii=False))
        return 0

    tokens = read_token(args)

    for n in range(args.count):
        if args.count > 1:
            print(f"\n=== код {n + 1}/{args.count} ===")
        uid = args.uid or str(uuid.uuid4())
        try:
            try_tokens(uid, tokens, args.ver)
        except SystemExit as err:
            print(str(err), file=sys.stderr)
            return 2
        except Exception as err:  # noqa: BLE001 — CLI, показываем причину
            print(f"ОШИБКА: {err}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
