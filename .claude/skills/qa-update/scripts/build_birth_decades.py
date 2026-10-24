"""NDL・Wikidata の人物の生年から、現行データの読み・表記ごとの「生年代の分布」を集計する（#10, #16）。

    python3 .claude/skills/qa-update/scripts/build_birth_decades.py \
      --ndl-work qa/sources/ndl-work-2026-10 \
      --sources qa/sources/wikidata-births-2026-10-24.jsonl \
      --dataset-dir japanese_personal_name_dataset/dataset \
      --out qa/metadata/birth_decades.csv

出力 CSV: kind,reading,kanji,decade,count
- kind は given / surname。kanji が空の行は読み単位（表記を問わない）の集計。
- decade は 10 年刻みの開始年。count はその年代に生まれた人物数（NDL と Wikidata の合計。重複を含みうる）。
- 現行データに載っている読み・表記だけを出し、count が min-count 未満の年代は出さない。
- 名は男女を区別しない（性別は推定しない）。読みがどちらのファイルにあっても同じ値を使う。
これはその名を持つ「典拠・百科事典に載る人物」の分布で、出生数のランキングではない。
"""
import argparse
import csv
import glob
import os
import sys
from typing import Dict, Iterable, List, Optional, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sources_common as sc  # noqa: E402

FIRST_NAME_FILES = ("first_name_man_org.csv", "first_name_woman_org.csv")
LAST_NAME_FILE = "last_name_org.csv"
HEADER = ["kind", "reading", "kanji", "decade", "count"]

Key = Tuple[str, str, str]          # (kind, reading, kanji)  kanji="" は読み単位
Row = Tuple[str, str, str, int, int]


def load_targets(dataset_dir):
    # type: (str) -> Set[Key]
    targets = set()  # type: Set[Key]
    for fn in FIRST_NAME_FILES:
        with open(os.path.join(dataset_dir, fn), encoding="utf-8") as f:
            for row in csv.reader(f):
                if len(row) < 2:
                    continue
                targets.add(("given", row[0], ""))
                for k in row[2:]:
                    targets.add(("given", row[0], k))
    with open(os.path.join(dataset_dir, LAST_NAME_FILE), encoding="utf-8") as f:
        for row in csv.reader(f):
            if len(row) >= 4:
                targets.add(("surname", row[2], row[0]))
    return targets


def aggregate(records, targets, min_count=3):
    # type: (Iterable[dict], Set[Key], int) -> List[Row]
    counts = {}  # type: Dict[Tuple[str, str, str, int], int]
    for r in records:
        year = r.get("birth_year")
        if year is None:
            continue
        decade = int(year) // 10 * 10
        n = int(r.get("count", 1))
        keys = [(r["kind"], r["reading"], r["kanji"])]
        if r["kind"] == "given":
            keys.append(("given", r["reading"], ""))   # 読み単位にも積む
        for key in keys:
            if key in targets:
                k = key + (decade,)
                counts[k] = counts.get(k, 0) + n
    return sorted((k[0], k[1], k[2], k[3], n) for k, n in counts.items() if n >= min_count)


def _iter_records(ndl_work, sources):
    # type: (Optional[str], List[str]) -> Iterable[dict]
    if ndl_work:
        for p in sorted(glob.glob(os.path.join(ndl_work, "prefix-*.jsonl"))):
            for r in sc.read_jsonl(p):
                yield r
    for p in sources:
        for r in sc.read_jsonl(p):
            yield r


def main(argv=None):
    # type: (Optional[List[str]]) -> int
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ndl-work", help="fetch_ndl.py の --work（人物単位の prefix-*.jsonl）")
    parser.add_argument("--sources", nargs="*", default=[], help="生年付き正規化 JSONL（Wikidata 等）")
    parser.add_argument("--dataset-dir", default=os.path.join("japanese_personal_name_dataset", "dataset"))
    parser.add_argument("--out", default=os.path.join("qa", "metadata", "birth_decades.csv"))
    parser.add_argument("--min-count", type=int, default=3)
    args = parser.parse_args(argv)
    rows = aggregate(_iter_records(args.ndl_work, args.sources), load_targets(args.dataset_dir), args.min_count)
    parent = os.path.dirname(args.out)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(HEADER)
        w.writerows(rows)
    keys = {(r[0], r[1], r[2]) for r in rows}
    print("生年代: %d 行 / %d 件の読み・表記 → %s" % (len(rows), len(keys), args.out))
    return 0


if __name__ == "__main__":
    sc.force_utf8_output()
    sys.exit(main())
