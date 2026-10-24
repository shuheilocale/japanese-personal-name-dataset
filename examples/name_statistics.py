"""データセットの簡単な分析。

- 名によく使われる漢字（男女別）
- 男女どちらの名にもある読み
- 漢字表記が多い読み

    python examples/name_statistics.py
"""
import sys
from collections import Counter

from japanese_personal_name_dataset import load_dataset


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    man, woman = load_dataset()
    for label, names in (("男性", man), ("女性", woman)):
        chars = Counter(ch for entry in names.values() for k in entry["kanji"] for ch in set(k))
        print("%sの名によく使われる漢字: %s" % (label, " ".join(c for c, _ in chars.most_common(15))))

    shared = sorted(set(man) & set(woman))
    print("\n男女どちらの名にもある読み: %d 件（例: %s）" % (len(shared), "、".join(shared[:12])))

    print("\n漢字表記が多い読み（男女合計）:")
    totals = Counter()
    for names in (man, woman):
        for reading, entry in names.items():
            totals[reading] += len(entry["kanji"])
    for reading, n in totals.most_common(5):
        print("  %s: %d 通り" % (reading, n))


if __name__ == "__main__":
    main()
