#!/usr/bin/env python3
"""
Вычищает неиспользуемые поля, освобождая слоты в таблице field_ids dex.

В classes.dex исходного приложения таблица field_ids забита ровно под
предел (65536 записей). Из-за этого добавление нового класса роняет
пересборку dex: индекс 65536 не влезает в ushort.

Поля, на которые нет ни одной ссылки вида L<класс>;-><поле>:, можно
удалить — R8 оставил их мёртвым грузом (в основном R-классы рекламных SDK).
Каждое удалённое поле освобождает один слот.

Проверка строго по паре (класс, имя): одинаковые имена в разных классах не
путаются.

    python3 prune_fields.py <дерево apktool> [--dry-run]
"""

import re
import sys
from collections import Counter
from pathlib import Path

CLASS_RE = re.compile(r"^\.class\s+.*?->(\S+;)", re.M)
FIELD_RE = re.compile(
    r"^\.field\s+(?:(?:public|private|protected|static|final|synthetic|volatile|transient|enum)\s+)*([\w$]+):")
REF_RE = re.compile(r"->([\w$]+):")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    tree = Path(sys.argv[1]).resolve()
    dry = "--dry-run" in sys.argv

    smali_dirs = [tree / "smali", tree / "smali_classes2"]
    files = [f for d in smali_dirs if d.exists() for f in d.rglob("*.smali")]

    texts = {f: f.read_text(encoding="utf-8", errors="ignore") for f in files}
    blob = "\n".join(texts.values())

    # ссылки вида L<class>;-><field>:  — считаем по полному имени класса
    refs = Counter()
    for m in re.finditer(r"(L[\w/$]+;)->([\w$]+):", blob):
        refs[(m.group(1), m.group(2))] += 1

    removed = 0
    freed = Counter()
    for f, text in texts.items():
        m = CLASS_RE.search(text)
        if not m:
            continue
        cls = m.group(1)
        lines = text.split("\n")
        keep = []
        for line in lines:
            fm = FIELD_RE.match(line)
            if fm:
                name = fm.group(1)
                if refs[(cls, name)] == 0:
                    removed += 1
                    freed[f] += 1
                    continue
            keep.append(line)
        if freed.get(f):
            if not dry:
                f.write_text("\n".join(keep), encoding="utf-8")

    print(f"удалено полей: {removed}")
    for f, c in freed.most_common(8):
        print(f"  {c:5}  {f.relative_to(tree)}")
    print(f"освобождено слотов в field_ids: ~{removed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
