#!/usr/bin/env python3
"""
Чтение logcat телефона напрямую через logd.

На этом устройстве /dev/socket/logdr доступен контейнеру и говорит по
SOCK_SEQPACKET — обычного /system/bin/logcat в контейнере нет, а Android SDK
logcat требует adb. Протокол logd: шлём android_log_reader (20 байт), читаем
последовательность logger_entry (len/hdrlen/...).

    python3 logcat.py            # вывалить последние записи
    python3 logcat.py --grep PI  # только строки, где есть подстрока
"""

import argparse
import socket
import struct
import sys
import time

READER_LIST = struct.Struct("<IIIII")  # len, mode, tail, logrd_mask, pid
MODE_RDONLY = 1
MODE_NONBLOCK = 2


def read_entries(tail=0, mask=0xFFFFFFFF, pid=0, seconds=3.0):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    s.settimeout(1.0)
    s.connect("/dev/socket/logdr")
    s.send(READER_LIST.pack(20, MODE_RDONLY | MODE_NONBLOCK, tail, mask, pid))
    out = []
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            buf = s.recv(1 << 16)
        except socket.timeout:
            continue
        except OSError:
            break
        if not buf:
            break
        off = 0
        while off + 4 <= len(buf):
            length, hdrlen = struct.unpack_from("<HH", buf, off)
            if length < hdrlen or off + length > len(buf):
                break
            payload = buf[off + hdrlen:off + length]
            try:
                text = payload.decode("utf-8", "replace")
            except Exception:
                text = repr(payload)
            out.append(text)
            off += length
    s.close()
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--grep", help="подстрока-фильтр")
    ap.add_argument("--tail", type=int, default=0, help="сколько последних записей")
    ap.add_argument("--seconds", type=float, default=3.0)
    ap.add_argument("--pid", type=int, default=0)
    args = ap.parse_args()

    entries = read_entries(tail=args.tail, pid=args.pid, seconds=args.seconds)
    if args.grep:
        entries = [e for e in entries if args.grep.lower() in e.lower()]
    for e in entries:
        print(e.rstrip())
    print(f"--- записей: {len(entries)} ---", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
