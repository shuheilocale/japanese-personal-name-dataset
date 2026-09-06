"""国立国会図書館典拠データ（Web NDL Authorities）から人名を取得して正規化 JSONL に書く。

SPARQL の ORDER BY + OFFSET は大きなオフセットでサーバエラーになるため、
典拠 ID（http://id.ndl.go.jp/auth/ndlna/NNNNNNNN）の接頭辞でチャンク分割する。
接頭辞ごとの結果を作業ディレクトリに保存し、manifest.json で再開できる。
"""
import argparse
import datetime
import json
import os
import re
import sys
from typing import List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sources_common as sc  # noqa: E402

ENDPOINT = "https://id.ndl.go.jp/auth/ndla/sparql"
_DATE_RE = re.compile(r"^[0-9]{3,4}-?([0-9]{3,4})?$")


def build_query(prefix):
    # type: (str) -> str
    return (
        "PREFIX xl: <http://www.w3.org/2008/05/skos-xl#> "
        "PREFIX skos: <http://www.w3.org/2004/02/skos/core#> "
        "PREFIX ndl: <http://ndl.go.jp/dcndl/terms/> "
        "SELECT ?s ?label ?yomi WHERE { "
        "?s skos:inScheme <http://id.ndl.go.jp/auth#personalNames> ; xl:prefLabel ?pl . "
        "?pl xl:literalForm ?label ; ndl:transcription ?yomi . "
        "FILTER(STRSTARTS(STR(?s), \"http://id.ndl.go.jp/auth/ndlna/%s\")) }" % prefix)


def _split(label):
    # type: (str) -> List[str]
    return [p.strip() for p in label.split(",")]


def parse_label(label):
    # type: (str) -> Optional[Tuple[str, str]]
    parts = _split(label)
    if len(parts) < 2:
        return None
    surname, given = parts[0], parts[1]
    if not (sc.is_japanese_name_part(surname) and sc.is_japanese_name_part(given)):
        return None
    return surname, given


def parse_yomi(yomi):
    # type: (str) -> Optional[Tuple[str, str]]
    parts = _split(yomi)
    if len(parts) < 2:
        return None
    s, g = sc.kata_to_hira(parts[0]), sc.kata_to_hira(parts[1])
    if not (sc.checks.HIRAGANA_RE.match(s) and sc.checks.HIRAGANA_RE.match(g)):
        return None
    return s, g


def bindings_to_records(bindings):
    # type: (List[dict]) -> List[dict]
    out = []
    for b in bindings:
        if b.get("yomi", {}).get("xml:lang") != "ja-Kana":
            continue
        names = parse_label(b["label"]["value"])
        yomis = parse_yomi(b["yomi"]["value"])
        if not names or not yomis:
            continue
        out.append(sc.record("ndl", "surname", names[0], yomis[0]))
        out.append(sc.record("ndl", "given", names[1], yomis[1]))
    return out


def aggregate(records):
    # type: (List[dict]) -> List[dict]
    totals = {}
    for r in records:
        k = (r["source"], r["kind"], r["kanji"], r["reading"])
        totals[k] = totals.get(k, 0) + r["count"]
    return [sc.record(s, kind, kanji, reading, count=n)
            for (s, kind, kanji, reading), n in sorted(totals.items())]


def fetch_prefixes(prefixes, work, fetch=None):
    # type: (List[str], str, object) -> None
    os.makedirs(work, exist_ok=True)
    mpath = os.path.join(work, "manifest.json")
    manifest = {"done": []}
    if os.path.exists(mpath):
        with open(mpath, encoding="utf-8") as f:
            manifest = json.load(f)
    for prefix in prefixes:
        if prefix in manifest["done"]:
            continue
        data = (fetch or sc.http_get)(ENDPOINT, params={"query": build_query(prefix)},
                                      headers={"Accept": "application/sparql-results+json"})
        bindings = json.loads(data.decode("utf-8"))["results"]["bindings"]
        sc.write_jsonl(os.path.join(work, "prefix-%s.jsonl" % prefix), bindings_to_records(bindings))
        manifest["done"].append(prefix)
        with open(mpath, "w", encoding="utf-8", newline="\n") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=1)
        print("prefix %s: %d 行" % (prefix, len(bindings)))


def main():
    # type: () -> int
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=os.path.join(
        "qa", "sources", "ndl-%s.jsonl" % datetime.date.today().isoformat()))
    parser.add_argument("--work", default=os.path.join("qa", "sources", "ndl-work"))
    parser.add_argument("--prefix-len", type=int, default=3)
    args = parser.parse_args()
    prefixes = ["%0*d" % (args.prefix_len, i) for i in range(10 ** args.prefix_len)]
    fetch_prefixes(prefixes, args.work)
    records = []
    for prefix in prefixes:
        records.extend(sc.read_jsonl(os.path.join(args.work, "prefix-%s.jsonl" % prefix)))
    agg = aggregate(records)
    sc.write_jsonl(args.out, agg)
    print("書き込み: %s（%d 件）" % (args.out, len(agg)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
