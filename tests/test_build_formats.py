"""scripts/build_formats.py のテスト（#3, #15）。"""
import json
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import build_formats as bf  # noqa: E402


def _dataset(tmp_path):
    d = tmp_path / "dataset"
    d.mkdir()
    (d / "first_name_man_org.csv").write_text("ひろし,hiroshi,博,宏\nたろう,tarou,太郎\n", encoding="utf-8")
    (d / "first_name_man_opti.csv").write_text("ひろし,hiroshi,博,宏\n", encoding="utf-8")
    (d / "first_name_woman_org.csv").write_text("はなこ,hanako,花子\n", encoding="utf-8")
    (d / "first_name_woman_opti.csv").write_text("", encoding="utf-8")
    (d / "last_name_org.csv").write_text("佐藤,1887000,さとう,satou\n", encoding="utf-8")
    return str(d)


def _metadata(tmp_path):
    p = tmp_path / "birth_decades.csv"
    p.write_text("kind,reading,kanji,decade,count\n"
                 "given,ひろし,,1940,5\ngiven,ひろし,博,1940,3\nsurname,さとう,佐藤,1980,4\n", encoding="utf-8")
    return str(p)


def test_build_json_structure(tmp_path):
    data = bf.build_data(_dataset(tmp_path), _metadata(tmp_path), version="9.9.9")
    assert data["version"] == "9.9.9"
    hiroshi = [e for e in data["first_names"]["male"] if e["reading"] == "ひろし"][0]
    assert hiroshi == {"reading": "ひろし", "romaji": "hiroshi", "kanji": ["博", "宏"], "popular": True,
                       "birth_decades": {"1940": 5}, "kanji_birth_decades": {"博": {"1940": 3}}}
    taro = [e for e in data["first_names"]["male"] if e["reading"] == "たろう"][0]
    assert taro["popular"] is False and "birth_decades" not in taro
    assert data["last_names"] == [{"kanji": "佐藤", "reading": "さとう", "romaji": "satou", "count": 1887000,
                                   "birth_decades": {"1980": 4}}]


def test_build_without_metadata(tmp_path):
    data = bf.build_data(_dataset(tmp_path), None, version="0")
    assert all("birth_decades" not in e for e in data["first_names"]["male"])


def test_write_and_verify_round_trip(tmp_path):
    out = tmp_path / "build"
    assert bf.main(["--dataset-dir", _dataset(tmp_path), "--metadata", _metadata(tmp_path),
                    "--out", str(out), "--version", "1.0.0"]) == 0
    with open(str(out / "japanese_names.json"), encoding="utf-8") as f:
        data = json.load(f)
    assert len(data["first_names"]["male"]) == 2
    con = sqlite3.connect(str(out / "japanese_names.sqlite"))
    try:
        assert con.execute("SELECT COUNT(*) FROM first_names").fetchone()[0] == 3
        assert con.execute(
            "SELECT k.kanji FROM first_names f JOIN first_name_kanji k ON k.first_name_id = f.id "
            "WHERE f.gender='male' AND f.reading='ひろし' ORDER BY k.position").fetchall() == [("博",), ("宏",)]
        assert con.execute("SELECT count FROM last_names WHERE kanji='佐藤'").fetchone()[0] == 1887000
        assert con.execute("SELECT count FROM birth_decades WHERE kind='given' AND reading='ひろし' AND kanji=''"
                           ).fetchone()[0] == 5
        assert con.execute("SELECT value FROM metadata WHERE key='version'").fetchone()[0] == "1.0.0"
    finally:
        con.close()


def test_verify_detects_mismatch(tmp_path):
    out = tmp_path / "build"
    ds = _dataset(tmp_path)
    bf.main(["--dataset-dir", ds, "--out", str(out), "--version", "1"])
    p = out / "japanese_names.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    data["first_names"]["male"].pop()
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    problems = bf.verify(str(out), ds)
    assert problems and "json" in problems[0]


def test_real_dataset_builds(tmp_path):
    out = tmp_path / "build"
    assert bf.main(["--out", str(out), "--version", "test"]) == 0
