"""Wikidata から日本語の名・姓（仮名表記 P1814 付き）を取得して正規化 JSONL に書く。

クラス: 男性名 Q12308941 / 女性名 Q11879590 / 中性名 Q3409032 / 姓 Q101352。
count はその名を持つ人物数（P735 / P734 の参照数、項目が存在すれば最低 1）。
"""
import argparse
import datetime
import json
import os
import sys
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sources_common as sc  # noqa: E402
import checks  # noqa: E402

ENDPOINT = "https://query.wikidata.org/sparql"
CLASSES = {
    "given": {"male": "Q12308941", "female": "Q11879590", "unisex": "Q3409032"},
    "surname": {None: "Q101352"},
}


def build_query(kind, qid):
    # type: (str, str) -> str
    prop = "wdt:P735" if kind == "given" else "wdt:P734"
    return (
        "SELECT ?label ?kana (COUNT(?h) AS ?people) WHERE { "
        "?item wdt:P31 wd:%s ; wdt:P407 wd:Q5287 ; wdt:P1814 ?kana ; rdfs:label ?label . "
        "FILTER(LANG(?label)=\"ja\") OPTIONAL { ?h %s ?item } } "
        "GROUP BY ?label ?kana" % (qid, prop))


def build_birth_query(kind, qid):
    # type: (str, str) -> str
    """名・姓の項目ごとに、その名を持つ人物の生年を 10 年刻みで数える（生年代メタデータ用）。"""
    prop = "wdt:P735" if kind == "given" else "wdt:P734"
    return (
        "SELECT ?label ?kana ?decade (COUNT(DISTINCT ?h) AS ?people) WHERE { "
        "?item wdt:P31 wd:%s ; wdt:P407 wd:Q5287 ; wdt:P1814 ?kana ; rdfs:label ?label . "
        "FILTER(LANG(?label)=\"ja\") ?h %s ?item ; wdt:P569 ?born . "
        "BIND(FLOOR(YEAR(?born) / 10) * 10 AS ?decade) } "
        "GROUP BY ?label ?kana ?decade" % (qid, prop))


def parse_bindings(data):
    # type: (bytes) -> List[dict]
    body = json.loads(data.decode("utf-8"))
    return [{k: v["value"] for k, v in b.items()} for b in body["results"]["bindings"]]


def rows_to_records(kind, gender, rows):
    # type: (str, str, List[dict]) -> List[dict]
    out = []
    for r in rows:
        reading = sc.kata_to_hira(r.get("kana", ""))
        if not checks.HIRAGANA_RE.match(reading):
            continue
        label = r.get("label", "")
        if checks.HIRAGANA_RE.match(sc.kata_to_hira(label)):
            kanji = ""  # 仮名ラベル項目は読みだけの根拠
        elif sc.is_japanese_name_part(label):
            kanji = label
        else:
            continue
        try:
            people = int(r.get("people", "0") or 0)
        except ValueError:
            people = 0
        out.append(sc.record("wikidata", kind, kanji, reading, gender=gender, count=max(1, people)))
    return out


MIN_DECADE = 1800


def rows_to_birth_records(kind, gender, rows):
    # type: (str, Optional[str], List[dict]) -> List[dict]
    """生年代の行を record に変換する。birth_year は年代の開始年、count はその年代の人数。"""
    out = []
    this_year = datetime.date.today().year
    for rec, r in zip(rows_to_records(kind, gender, rows), rows):
        try:
            decade = int(float(r.get("decade", "")))
        except ValueError:
            continue
        if decade < MIN_DECADE or decade > this_year:
            continue
        rec["birth_year"] = decade
        out.append(rec)
    return out


def fetch_birth_decades(fetch=None):
    # type: (object) -> List[dict]
    records = []
    for kind, classes in CLASSES.items():
        for gender, qid in classes.items():
            data = (fetch or sc.http_get)(
                ENDPOINT, params={"query": build_birth_query(kind, qid)},
                headers={"Accept": "application/sparql-results+json"})
            rows = parse_bindings(data)
            recs = rows_to_birth_records(kind, gender, rows)
            print("生年代 %s/%s: %d 行 → %d レコード" % (kind, gender, len(rows), len(recs)))
            records.extend(recs)
    return records


def fetch_all(fetch=None):
    # type: (object) -> List[dict]
    records = []
    for kind, classes in CLASSES.items():
        for gender, qid in classes.items():
            data = (fetch or sc.http_get)(
                ENDPOINT, params={"query": build_query(kind, qid)},
                headers={"Accept": "application/sparql-results+json"})
            rows = parse_bindings(data)
            recs = rows_to_records(kind, gender, rows)
            print("%s/%s: %d 行 → %d レコード" % (kind, gender, len(rows), len(recs)))
            records.extend(recs)
    return records


def main():
    # type: () -> int
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=os.path.join(
        "qa", "sources", "wikidata-%s.jsonl" % datetime.date.today().isoformat()))
    parser.add_argument("--birth-decades-out", default=None,
                        help="指定すると、人物の生年代（10 年刻み）の集計も別ファイルに書く")
    args = parser.parse_args()
    records = fetch_all()
    sc.write_jsonl(args.out, records)
    print("書き込み: %s（%d 件）" % (args.out, len(records)))
    if args.birth_decades_out:
        births = fetch_birth_decades()
        sc.write_jsonl(args.birth_decades_out, births)
        print("書き込み: %s（%d 件）" % (args.birth_decades_out, len(births)))
    return 0


if __name__ == "__main__":
    sc.force_utf8_output()
    sys.exit(main())
