"""CSV（正本）から JSON と SQLite を生成する（#3, #15）。標準ライブラリのみ。

    python scripts/build_formats.py --out build/

出力:
    build/japanese_names.json     名（男女）・姓・生年代を 1 ファイルに
    build/japanese_names.sqlite   同じ内容を SQL で引けるテーブルに

生成後に読み戻して CSV と件数・内容が一致するか検証し、不一致なら終了コード 1。
リリース時に CI がこれを実行して GitHub Releases に添付する（PyPI パッケージには含めない）。
"""
import argparse
import csv
import datetime
import json
import os
import re
import sqlite3
import sys
from typing import Any, Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DATASET = os.path.join(ROOT, "japanese_personal_name_dataset", "dataset")
DEFAULT_METADATA = os.path.join(ROOT, "qa", "metadata", "birth_decades.csv")
JSON_NAME = "japanese_names.json"
SQLITE_NAME = "japanese_names.sqlite"
GENDERS = ("male", "female")
FILES = {"male": "first_name_man", "female": "first_name_woman"}
SOURCES = {
    "first_names": "japanese-personal-name-dataset (MIT), cross-checked with Wikidata (CC0) and Web NDL Authorities",
    "last_name_counts": "名字由来net (https://myoji-yurai.net/)",
    "birth_decades": "Birth years of people in Web NDL Authorities and Wikidata. "
                     "Distribution of notable people, not birth statistics.",
}

SCHEMA = """
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE first_names (
    id INTEGER PRIMARY KEY, gender TEXT NOT NULL, reading TEXT NOT NULL,
    romaji TEXT NOT NULL, popular INTEGER NOT NULL, UNIQUE (gender, reading));
CREATE TABLE first_name_kanji (
    first_name_id INTEGER NOT NULL REFERENCES first_names(id), position INTEGER NOT NULL,
    kanji TEXT NOT NULL, PRIMARY KEY (first_name_id, position));
CREATE INDEX first_name_kanji_kanji ON first_name_kanji(kanji);
CREATE TABLE last_names (kanji TEXT PRIMARY KEY, reading TEXT NOT NULL, romaji TEXT NOT NULL, count INTEGER NOT NULL);
CREATE TABLE birth_decades (
    kind TEXT NOT NULL, reading TEXT NOT NULL, kanji TEXT NOT NULL, decade INTEGER NOT NULL,
    count INTEGER NOT NULL, PRIMARY KEY (kind, reading, kanji, decade));
"""


def _rows(path):
    # type: (str) -> List[List[str]]
    with open(path, encoding="utf-8") as f:
        return [r for r in csv.reader(f) if r]


def _load_birth_decades(path):
    # type: (Optional[str]) -> Dict[tuple, Dict[str, int]]
    out = {}  # type: Dict[tuple, Dict[str, int]]
    if not path or not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out.setdefault((r["kind"], r["reading"], r["kanji"]), {})[r["decade"]] = int(r["count"])
    return out


def build_data(dataset_dir, metadata_path, version):
    # type: (str, Optional[str], str) -> Dict[str, Any]
    births = _load_birth_decades(metadata_path)
    first = {}  # type: Dict[str, List[Dict[str, Any]]]
    for g in GENDERS:
        popular = {r[0] for r in _rows(os.path.join(dataset_dir, FILES[g] + "_opti.csv"))}
        entries = []
        for r in _rows(os.path.join(dataset_dir, FILES[g] + "_org.csv")):
            e = {"reading": r[0], "romaji": r[1], "kanji": r[2:], "popular": r[0] in popular}  # type: Dict[str, Any]
            if ("given", r[0], "") in births:
                e["birth_decades"] = births[("given", r[0], "")]
            per_kanji = {k: births[("given", r[0], k)] for k in r[2:] if ("given", r[0], k) in births}
            if per_kanji:
                e["kanji_birth_decades"] = per_kanji
            entries.append(e)
        first[g] = entries
    last = []
    for r in _rows(os.path.join(dataset_dir, "last_name_org.csv")):
        e = {"kanji": r[0], "reading": r[2], "romaji": r[3], "count": int(r[1]) if r[1].isdigit() else 0}
        if ("surname", r[2], r[0]) in births:
            e["birth_decades"] = births[("surname", r[2], r[0])]
        last.append(e)
    return {
        "version": version,
        "generated_at": datetime.date.today().isoformat(),
        "sources": SOURCES,
        "first_names": first,
        "last_names": last,
    }


def write_json(data, path):
    # type: (Dict[str, Any], str) -> None
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")


def write_sqlite(data, path):
    # type: (Dict[str, Any], str) -> None
    if os.path.exists(path):
        os.remove(path)
    con = sqlite3.connect(path)
    try:
        con.executescript(SCHEMA)
        con.executemany("INSERT INTO metadata VALUES (?, ?)", [
            ("version", data["version"]), ("generated_at", data["generated_at"]),
            ("sources", json.dumps(data["sources"], ensure_ascii=False))])
        for g in GENDERS:
            for e in data["first_names"][g]:
                cur = con.execute("INSERT INTO first_names (gender, reading, romaji, popular) VALUES (?, ?, ?, ?)",
                                  (g, e["reading"], e["romaji"], int(e["popular"])))
                con.executemany("INSERT INTO first_name_kanji VALUES (?, ?, ?)",
                                [(cur.lastrowid, i, k) for i, k in enumerate(e["kanji"])])
        con.executemany("INSERT INTO last_names VALUES (?, ?, ?, ?)",
                        [(e["kanji"], e["reading"], e["romaji"], e["count"]) for e in data["last_names"]])
        births = set()
        for g in GENDERS:
            for e in data["first_names"][g]:
                for d, n in e.get("birth_decades", {}).items():
                    births.add(("given", e["reading"], "", int(d), n))
                for k, dec in e.get("kanji_birth_decades", {}).items():
                    births.update(("given", e["reading"], k, int(d), n) for d, n in dec.items())
        for e in data["last_names"]:
            births.update(("surname", e["reading"], e["kanji"], int(d), n) for d, n in e.get("birth_decades", {}).items())
        con.executemany("INSERT INTO birth_decades VALUES (?, ?, ?, ?, ?)", sorted(births))
        con.commit()
        con.execute("VACUUM")
    finally:
        con.close()


def verify(out_dir, dataset_dir):
    # type: (str, str) -> List[str]
    """生成物を読み戻し、CSV と一致しない点を返す（空なら一致）。"""
    problems = []
    with open(os.path.join(out_dir, JSON_NAME), encoding="utf-8") as f:
        data = json.load(f)
    con = sqlite3.connect(os.path.join(out_dir, SQLITE_NAME))
    try:
        for g in GENDERS:
            csv_rows = [(r[0], r[1], r[2:]) for r in _rows(os.path.join(dataset_dir, FILES[g] + "_org.csv"))]
            json_rows = [(e["reading"], e["romaji"], e["kanji"]) for e in data["first_names"][g]]
            if json_rows != csv_rows:
                problems.append("json: %s の名が CSV と一致しません（%d / %d 件）" % (g, len(json_rows), len(csv_rows)))
            sql = {}  # type: Dict[str, List[str]]
            for reading, kanji in con.execute(
                    "SELECT f.reading, k.kanji FROM first_names f LEFT JOIN first_name_kanji k "
                    "ON k.first_name_id = f.id WHERE f.gender = ? ORDER BY f.id, k.position", (g,)):
                sql.setdefault(reading, [])
                if kanji is not None:
                    sql[reading].append(kanji)
            if sql != {r: k for r, _, k in csv_rows}:
                problems.append("sqlite: %s の名が CSV と一致しません" % g)
            opti = {r[0] for r in _rows(os.path.join(dataset_dir, FILES[g] + "_opti.csv"))}
            if {e["reading"] for e in data["first_names"][g] if e["popular"]} != opti:
                problems.append("json: %s の popular が opti CSV と一致しません" % g)
        last_csv = [(r[0], r[2], r[3]) for r in _rows(os.path.join(dataset_dir, "last_name_org.csv"))]
        if [(e["kanji"], e["reading"], e["romaji"]) for e in data["last_names"]] != last_csv:
            problems.append("json: 姓が CSV と一致しません")
        if con.execute("SELECT COUNT(*) FROM last_names").fetchone()[0] != len(last_csv):
            problems.append("sqlite: 姓の件数が CSV と一致しません")
    finally:
        con.close()
    return problems


def _project_version():
    # type: () -> str
    with open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8") as f:
        m = re.search(r'^version = "([^"]+)"', f.read(), re.M)
    return m.group(1) if m else "0.0.0"


def main(argv=None):
    # type: (Optional[List[str]]) -> int
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset-dir", default=DEFAULT_DATASET)
    parser.add_argument("--metadata", default=DEFAULT_METADATA, help="生年代 CSV（無ければ省略）")
    parser.add_argument("--out", default=os.path.join(ROOT, "build"))
    parser.add_argument("--version", default=None, help="既定は pyproject.toml の version")
    args = parser.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    data = build_data(args.dataset_dir, args.metadata, args.version or _project_version())
    write_json(data, os.path.join(args.out, JSON_NAME))
    write_sqlite(data, os.path.join(args.out, SQLITE_NAME))
    problems = verify(args.out, args.dataset_dir)
    for name in (JSON_NAME, SQLITE_NAME):
        print("%-24s %8.1f KB" % (name, os.path.getsize(os.path.join(args.out, name)) / 1024))
    print("名: 男性 %d / 女性 %d、姓 %d、生年代つき %d 件" % (
        len(data["first_names"]["male"]), len(data["first_names"]["female"]), len(data["last_names"]),
        sum("birth_decades" in e for g in GENDERS for e in data["first_names"][g])
        + sum("birth_decades" in e for e in data["last_names"])))
    if problems:
        for p in problems:
            print("検証エラー: " + p, file=sys.stderr)
        return 1
    print("検証: CSV と一致")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
