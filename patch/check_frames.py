#!/usr/bin/env python3
"""
Проверяет, что в smali-методах не вылезают за пределы кадра регистров.

smali не всегда ругается на `v2` при объявленном `.registers 4` и двух
параметрах (доступны только v0,v1) — а ART на этапе верификации даёт
VerifyError, и приложение падает на старте. Этот скрипт ловит такое
до сборки.

    python3 check_frames.py файл.smali [файл.smali ...]
"""

import re
import sys
from pathlib import Path

METHOD_RE = re.compile(r"^\.method\b.*$")
END_RE = re.compile(r"^\.end method\s*$")
REGS_RE = re.compile(r"^\s*\.registers\s+(\d+)\s*$")
LOCALS_RE = re.compile(r"^\s*\.locals\s+(\d+)\s*$")
PARAM_RE = re.compile(r"\(([^)]*)\)")
REG_USE_RE = re.compile(r"\b([vp]\d+)\b")
INSTR_RE = re.compile(r"^\s*(invoke-\S+|iget\S*|iput\S*|move\S*|const\S*|new-instance|check-cast|instance-of|new-array|fill-array-data|aget|aput|iget|iput)\b(.*)$")

# инструкции, где операнды — не регистры
SKIP_TOKENS = ("Ljava/", "Landroid/", "Lkotlin/", "Lcom/", "Lio/", "Lokhttp", "->", "Lme/", "Lorg/", "Lsk/")


def params_count(desc: str, is_static: bool) -> int:
    m = PARAM_RE.search(desc)
    if not m:
        return 0
    types = [t for t in m.group(1).split(";") if t]
    # long/double занимают два регистра
    return sum(2 if t in ("J", "D") else 1 for t in types)


def check(path: Path) -> int:
    text = path.read_text(encoding="utf-8", errors="ignore").split("\n")
    problems = 0
    i = 0
    while i < len(text):
        if not METHOD_RE.match(text[i]):
            i += 1
            continue
        header = text[i]
        is_static = " static " in header or header.strip().startswith(".method static")
        regs = None
        locals_ = None
        desc = header[header.find("("):header.rfind(")") + 1] if "(" in header else "()"
        body = []
        j = i + 1
        while j < len(text) and not END_RE.match(text[j]):
            body.append(text[j])
            j += 1
        for line in body:
            m = REGS_RE.match(line)
            if m:
                regs = int(m.group(1))
                continue
            m = LOCALS_RE.match(line)
            if m:
                locals_ = int(m.group(1))
                continue
        if regs is None and locals_ is None:
            i = j + 1
            continue
        nparams = params_count(desc, is_static)
        if not is_static:
            nparams += 1  # p0 = this
        if regs is not None:
            nlocals = regs - nparams
        else:
            nlocals = locals_
        if nlocals < 0:
            nlocals = 0
        for off, line in enumerate(body):
            if not INSTR_RE.match(line):
                continue
            if any(t in line for t in SKIP_TOKENS):
                # всё равно вычистим регистры после типа
                pass
            operand = line.split("}", 1)
            operand = operand[-1] if "}" in line else line
            operand = operand.split(",", 1)[-1] if "{" in line else operand
            for tok in REG_USE_RE.findall(operand):
                if tok[0] == "p":
                    idx = int(tok[1:])
                    if idx >= nparams:
                        print(f"{path}:{i+2+off}  {tok} (p{nparams}) выходит за параметры "
                              f"в методе {header.strip()[:70]}")
                        problems += 1
                else:
                    idx = int(tok[1:])
                    if idx >= nlocals:
                        print(f"{path}:{i+2+off}  {tok} при доступных v0..v{nlocals-1} "
                              f"в методе {header.strip()[:70]}")
                        problems += 1
        i = j + 1
    return problems


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    total = 0
    for arg in sys.argv[1:]:
        p = Path(arg)
        total += check(p)
    if total:
        print(f"\nПРОБЛЕМ: {total}")
        return 1
    print("кадры регистров в порядке")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
