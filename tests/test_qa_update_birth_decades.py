"""build_birth_decades.py のテスト（#10, #16）。"""
import csv
import json
import os

import build_birth_decades as bbd
import sources_common as sc


def _dataset(tmp_path):
    d = tmp_path / "dataset"
    d.mkdir()
    (d / "first_name_man_org.csv").write_text("ひろし,hiroshi,博,宏\n", encoding="utf-8")
    (d / "first_name_woman_org.csv").write_text("はなこ,hanako,花子\n", encoding="utf-8")
    (d / "last_name_org.csv").write_text("佐藤,1887000,さとう,satou\n", encoding="utf-8")
    return str(d)


def _records():
    recs = []
    recs += [sc.record("ndl", "given", "博", "ひろし", birth_year=1943) for _ in range(3)]
    recs += [sc.record("ndl", "given", "宏", "ひろし", birth_year=1951) for _ in range(2)]
    recs.append(sc.record("wikidata", "given", "宏", "ひろし", count=2, birth_year=1950))
    recs.append(sc.record("ndl", "given", "寛", "ひろし", birth_year=1955))        # データに無い表記
    recs += [sc.record("ndl", "given", "太郎", "たろう", birth_year=1950) for _ in range(5)]  # 無い読み
    recs += [sc.record("ndl", "surname", "佐藤", "さとう", birth_year=1980) for _ in range(4)]
    recs.append(sc.record("ndl", "given", "花子", "はなこ"))                        # 生年なし
    return recs


def test_aggregate_by_decade_with_threshold(tmp_path):
    rows = bbd.aggregate(_records(), bbd.load_targets(_dataset(tmp_path)), min_count=3)
    assert ("given", "ひろし", "博", 1940, 3) in rows
    assert ("given", "ひろし", "宏", 1950, 4) in rows           # NDL 2 + Wikidata 2（1951 → 1950 年代）
    assert ("given", "ひろし", "", 1950, 5) in rows             # 読み単位: 宏 4 + 寛 1
    assert ("given", "ひろし", "", 1940, 3) in rows
    assert ("surname", "さとう", "佐藤", 1980, 4) in rows
    assert not [r for r in rows if r[1] == "たろう"]
    assert not [r for r in rows if r[2] == "寛"]
    assert not [r for r in rows if r[1] == "はなこ"]


def test_main_writes_csv_from_ndl_work_and_sources(tmp_path):
    work = tmp_path / "ndl-work"
    work.mkdir()
    sc.write_jsonl(str(work / "prefix-000.jsonl"), [r for r in _records() if r["source"] == "ndl"])
    wd = tmp_path / "wd.jsonl"
    sc.write_jsonl(str(wd), [r for r in _records() if r["source"] == "wikidata"])
    out = tmp_path / "birth_decades.csv"
    assert bbd.main(["--ndl-work", str(work), "--sources", str(wd), "--dataset-dir", _dataset(tmp_path),
                     "--out", str(out)]) == 0
    with open(str(out), encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["kind", "reading", "kanji", "decade", "count"]
    assert ["given", "ひろし", "宏", "1950", "4"] in rows
