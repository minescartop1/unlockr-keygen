#!/usr/bin/env python3
"""
Освобождает место в таблице field_ids файла classes.dex.

В исходном classes.dex таблица field_ids забита ровно под предел (65536
записей). Поэтому добавление даже одного нового класса роняет пересборку dex:
`dexlib2` не может записать индекс поля 65536 в ushort.

Лимит действует на каждый dex отдельно. Классы переносятся из smali/
(classes.dex) в smali_classes2/ (classes2.dex), и таблица field_ids первого
файла сжимается — появляется запас под новые классы.

Переносятся только классы без статического инициализатора: ART грузит все
dex-файлы одним class loader, но так меньше риска с порядком инициализации.

    python3 rebalance_dex.py <дерево apktool> [сколько слотов освободить]
"""

import re
import shutil
import sys
from pathlib import Path

CLINIT = re.compile(r"^\.method static constructor <clinit>\(\)V", re.M)
FIELDS = re.compile(r"^\.field\s+(?:(?:public|private|protected|static|final|synthetic|volatile|transient|enum)\s+)*([\w$]+):", re.M)
CLASS_HDR = re.compile(r"^\.class\s+.*?->(\S+;)", re.M)
FIELD_REF = re.compile(r"->(\w+):")


def collect(tree: Path) -> list[tuple[int, Path, str]]:
    """Классы без <clinit>, отсортированные по убыванию числа полей.

    Классы без статического инициализатора переносятся безопаснее: ART
    грузит все dex-файлы одним class loader, но так меньше риска с порядком
    инициализации.
    """
    out = []
    for smali in (tree / "smali").rglob("*.smali"):
        text = smali.read_text(encoding="utf-8", errors="ignore")
        if CLINIT.search(text):
            continue
        names = FIELDS.findall(text)
        if not names:
            continue
        m = CLASS_HDR.search(text)
        name = m.group(1) if m else smali.stem
        out.append((len(names), smali, name))
    out.sort(key=lambda x: (-x[0], str(x[1])))
    return out


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    tree = Path(sys.argv[1]).resolve()
    want = int(sys.argv[2]) if len(sys.argv) > 2 else 800
    move_count = int(sys.argv[3]) if len(sys.argv) > 3 else 0

    candidates = collect(tree)
    if not candidates:
        print("кандидатов не найдено")
        return 1

    moved = 0
    freed = 0
    for fields, smali, name in candidates:
        if freed >= want:
            break
        if move_count and moved >= move_count:
            break
        rel = smali.relative_to(tree / "smali")
        dest = tree / "smali_classes2" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(smali), str(dest))
        moved += 1
        freed += fields
        print(f"  перенесён {name} ({fields} полей)")

    print(f"перенесено классов: {moved}, освобождено полей: ~{freed}")
    print(f"полей перенесено: ~{freed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
