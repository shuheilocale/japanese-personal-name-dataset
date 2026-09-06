"""JMnedict（EDRDG、CC BY-SA 3.0）を取得して正規化 JSONL に書く。

ライセンスの share-alike 条項のため、このソースは索引での「存在確認」にだけ
使い、漢字・読みをデータセットや findings の値に転記してはならない。
"""
import argparse
import datetime
import gzip
import os
import sys
import xml.etree.ElementTree as ET
from typing import Iterator, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sources_common as sc  # noqa: E402

URL = "http://ftp.edrdg.org/pub/Nihongo/JMnedict.xml.gz"


def iter_entries(fileobj):
    # type: (object) -> Iterator[dict]
    for _event, elem in ET.iterparse(fileobj, events=("end",)):
        if elem.tag != "entry":
            continue
        yield {
            "kanji": [k.text for k in elem.iter("keb") if k.text],
            "readings": [r.text for r in elem.iter("reb") if r.text],
            "types": [t.text or "" for t in elem.iter("name_type")],
        }
        elem.clear()


def _classify(types):
    # type: (List[str]) -> List[tuple]
    kinds = []
    joined = " | ".join(types)
    male = "male given" in joined
    female = "female given" in joined
    if male and female:
        kinds.append(("given", "unisex"))
    elif male:
        kinds.append(("given", "male"))
    elif female:
        kinds.append(("given", "female"))
    elif "given name" in joined:
        kinds.append(("given", None))
    if "surname" in joined:
        kinds.append(("surname", None))
    return kinds


def entries_to_records(entries):
    # type: (Iterator[dict]) -> List[dict]
    out = []
    for e in entries:
        kinds = _classify(e["types"])
        if not kinds or not e["kanji"]:
            continue
        for kanji in e["kanji"]:
            for reb in e["readings"]:
                reading = sc.kata_to_hira(reb)
                if not sc.checks.HIRAGANA_RE.match(reading) or not sc.is_japanese_name_part(kanji):
                    continue
                for kind, gender in kinds:
                    out.append(sc.record("jmnedict", kind, kanji, reading, gender=gender))
    return out


def main():
    # type: () -> int
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=os.path.join(
        "qa", "sources", "jmnedict-%s.jsonl" % datetime.date.today().isoformat()))
    parser.add_argument("--cache", default=os.path.join("qa", "sources", "JMnedict.xml.gz"))
    args = parser.parse_args()
    if not os.path.exists(args.cache):
        os.makedirs(os.path.dirname(args.cache), exist_ok=True)
        with open(args.cache, "wb") as f:
            f.write(sc.http_get(URL, timeout=600))
        print("ダウンロード: %s" % args.cache)
    with gzip.open(args.cache, "rb") as f:
        records = entries_to_records(iter_entries(f))
    sc.write_jsonl(args.out, records)
    print("書き込み: %s（%d 件）" % (args.out, len(records)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
