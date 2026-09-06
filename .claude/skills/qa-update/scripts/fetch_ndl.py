"""国立国会図書館典拠データ（Web NDL Authorities）から人名を取得して正規化 JSONL に書く。

典拠 ID（http://id.ndl.go.jp/auth/ndlna/NNNNNNNN）の接頭辞でチャンク分割する。
NDL SPARQL エンドポイントは 1 クエリあたり最大 1,000 行で結果を打ち切るため、
1,000 行に達した接頭辞は自動的に 10 個の部分接頭辞に再分割される（適応分割）。
接頭辞ごとの結果を作業ディレクトリに保存し、manifest.json で再開できる。
"""
import argparse
import datetime
import json
import os
import sys
from typing import List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sources_common as sc  # noqa: E402

ENDPOINT = "https://id.ndl.go.jp/auth/ndla/sparql"


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


def fetch_prefixes(prefixes, work, fetch=None, cap=1000, max_depth=9):
    # type: (List[str], str, object, int, int) -> None
    os.makedirs(work, exist_ok=True)
    mpath = os.path.join(work, "manifest.json")
    manifest = {"done": [], "split": [], "saturated": []}
    if os.path.exists(mpath):
        with open(mpath, encoding="utf-8") as f:
            manifest = json.load(f)

    def _process(prefix):
        # type: (str) -> None
        # 既に done または split に含まれている場合はスキップ
        if prefix in manifest["done"] or prefix in manifest["split"]:
            return

        data = (fetch or sc.http_get)(ENDPOINT, params={"query": build_query(prefix)},
                                      headers={"Accept": "application/sparql-results+json"})
        bindings = json.loads(data.decode("utf-8"))["results"]["bindings"]
        count = len(bindings)

        # 1000 行に達した場合の処理
        if count >= cap:
            if len(prefix) < max_depth:
                # 接頭辞をさらに分割して再帰的に処理
                manifest["split"].append(prefix)
                for digit in "0123456789":
                    _process(prefix + digit)
                print("prefix %s: %d 行（分割）" % (prefix, count))
                return
            else:
                # max_depth に達しても cap 以上の場合は saturated に記録
                manifest["saturated"].append(prefix)
                print("警告: prefix %s: %d 行（飽和・データ欠損の可能性）" % (prefix, count))

        # 記録を保存
        sc.write_jsonl(os.path.join(work, "prefix-%s.jsonl" % prefix), bindings_to_records(bindings))
        manifest["done"].append(prefix)
        print("prefix %s: %d 行" % (prefix, count))

    for prefix in prefixes:
        _process(prefix)
        with open(mpath, "w", encoding="utf-8", newline="\n") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=1)


def main():
    # type: () -> int
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=os.path.join(
        "qa", "sources", "ndl-%s.jsonl" % datetime.date.today().isoformat()))
    parser.add_argument("--work", default=os.path.join("qa", "sources", "ndl-work"))
    parser.add_argument("--prefix-len", type=int, default=3)
    parser.add_argument("--cap", type=int, default=1000,
                        help="結果上限（デフォルト 1000）")
    parser.add_argument("--max-depth", type=int, default=9,
                        help="最大接頭辞深度（デフォルト 9）")
    args = parser.parse_args()
    prefixes = ["%0*d" % (args.prefix_len, i) for i in range(10 ** args.prefix_len)]
    fetch_prefixes(prefixes, args.work, cap=args.cap, max_depth=args.max_depth)

    # work ディレクトリ内の全 prefix-*.jsonl ファイルを読み込む
    records = []
    work_dir = args.work
    if os.path.exists(work_dir):
        for fname in sorted(os.listdir(work_dir)):
            if fname.startswith("prefix-") and fname.endswith(".jsonl"):
                fpath = os.path.join(work_dir, fname)
                records.extend(sc.read_jsonl(fpath))

    agg = aggregate(records)
    sc.write_jsonl(args.out, agg)
    print("書き込み: %s（%d 件）" % (args.out, len(agg)))

    # manifest を確認して saturated があれば exit 1
    mpath = os.path.join(args.work, "manifest.json")
    if os.path.exists(mpath):
        with open(mpath, encoding="utf-8") as f:
            manifest = json.load(f)
        if manifest.get("saturated"):
            print("エラー: 飽和接頭辞 %d 個（%s）- データ欠損の可能性があります" %
                  (len(manifest["saturated"]), ", ".join(manifest["saturated"][:3]) +
                   ("..." if len(manifest["saturated"]) > 3 else "")))
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
