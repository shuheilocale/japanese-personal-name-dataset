"""正規化レコードから (kind, kanji, reading) の統一索引を作る。

pairs:    "given|漱石|そうせき" → {"ndl": 12, "wikidata": 3, "jmnedict": true, "gender": {...}}
readings: "given||そうせき"    → 同形（漢字を問わない読みレベルの根拠。仮名のみの Wikidata 項目もここに入る）
"""
import json
import os
from typing import Iterable, Optional

COUNT_SOURCES = ("ndl", "wikidata")


def pair_key(kind, kanji, reading):
    # type: (str, str, str) -> str
    return "%s|%s|%s" % (kind, kanji, reading)


def reading_key(kind, reading):
    # type: (str, str) -> str
    return "%s||%s" % (kind, reading)


def _empty():
    # type: () -> dict
    return {"ndl": 0, "wikidata": 0, "jmnedict": False, "gender": {}}


def _merge_gender(slot, source, gender):
    # type: (dict, str, Optional[str]) -> None
    if not gender:
        return
    cur = slot["gender"].get(source)
    if cur is None or cur == gender:
        slot["gender"][source] = gender
    else:
        slot["gender"][source] = "unisex"


def _add(slot, r):
    # type: (dict, dict) -> None
    if r["source"] in COUNT_SOURCES:
        slot[r["source"]] += r["count"]
    elif r["source"] == "jmnedict":
        slot["jmnedict"] = True
    _merge_gender(slot, r["source"], r.get("gender"))


def build_index(records):
    # type: (Iterable[dict]) -> dict
    index = {"pairs": {}, "readings": {}}
    for r in records:
        rk = reading_key(r["kind"], r["reading"])
        _add(index["readings"].setdefault(rk, _empty()), r)
        if r["kanji"]:
            pk = pair_key(r["kind"], r["kanji"], r["reading"])
            _add(index["pairs"].setdefault(pk, _empty()), r)
    return index


def support(index, kind, kanji, reading):
    # type: (dict, str, str, str) -> dict
    slot = index["pairs"].get(pair_key(kind, kanji, reading))
    if not slot:
        return {"ndl": 0, "wikidata": 0, "jmnedict": False}
    return {"ndl": slot["ndl"], "wikidata": slot["wikidata"], "jmnedict": slot["jmnedict"]}


def gender_of(index, kind, reading):
    # type: (dict, str, str) -> Optional[str]
    slot = index["readings"].get(reading_key(kind, reading))
    if not slot:
        return None
    for source in ("wikidata", "jmnedict"):
        if slot["gender"].get(source):
            return slot["gender"][source]
    return None


def save_index(path, index):
    # type: (str, dict) -> None
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(index, f, ensure_ascii=False, sort_keys=True)
        f.write("\n")


def load_index(path):
    # type: (str) -> dict
    with open(path, encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    import argparse
    import sys

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import sources_common as sc

    sc.force_utf8_output()
    parser = argparse.ArgumentParser(description="正規化 JSONL から統一索引を作る")
    parser.add_argument("--sources", nargs="+", required=True, help="正規化 JSONL ファイル")
    parser.add_argument("--out", default=os.path.join("qa", "sources", "index.json"))
    args = parser.parse_args()
    recs = []
    for p in args.sources:
        recs.extend(sc.read_jsonl(p))
    idx = build_index(recs)
    save_index(args.out, idx)
    print("索引: pairs %d / readings %d → %s" % (len(idx["pairs"]), len(idx["readings"]), args.out))
