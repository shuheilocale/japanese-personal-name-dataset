"""generate_candidates.py のテスト。"""
import json
import os

import generate_candidates as gc
import source_index as si
import sources_common as sc


def _dataset(tmp_path):
    d = tmp_path / "dataset"
    d.mkdir()
    (d / "first_name_man_org.csv").write_text("あい,ai,藍\nかおる,kaoru,薫\n", encoding="utf-8")
    (d / "first_name_man_opti.csv").write_text("", encoding="utf-8")
    (d / "first_name_woman_org.csv").write_text("かおる,kaoru,香\nさくら,sakura,桜\n", encoding="utf-8")
    (d / "first_name_woman_opti.csv").write_text("", encoding="utf-8")
    (d / "last_name_org.csv").write_text("金子,100,きんす,kinsu\n佐藤,200,さとう,satou\n", encoding="utf-8")
    return str(d)


def _index():
    return si.build_index([
        sc.record("ndl", "given", "愛", "あい", count=9),           # add_kanji（強根拠）
        sc.record("wikidata", "given", "愛", "あい", gender="female", count=2),
        sc.record("ndl", "given", "哀", "あい", count=1),           # 根拠不足
        sc.record("ndl", "given", "樹", "いつき", count=7),          # add_row（性別は wikidata）
        sc.record("wikidata", "given", "", "いつき", gender="male", count=3),
        sc.record("wikidata", "given", "樹", "いつき", gender="male", count=3),
        sc.record("ndl", "given", "凛", "りん", count=6),            # add_row（性別不明 → pending 判定へ）
        sc.record("ndl", "given", "龘", "たつ", count=9),            # 人名用漢字外 → 除外
        sc.record("ndl", "surname", "金子", "かねこ", count=50),      # 姓の照合
        sc.record("ndl", "surname", "佐藤", "さとう", count=90),
    ])


ALLOWED = {"愛", "哀", "樹", "凛", "藍", "薫", "香", "桜"}


class TestGenerate:
    def test_add_kanji_and_thresholds(self, tmp_path):
        ds = gc.load_dataset(_dataset(tmp_path))
        fs, pending = gc.generate(_index(), ds, ALLOWED, min_ndl=2, auto_ndl=5, today="2026-09-06")
        by_id = {f["id"]: f for f in fs}
        f = by_id["first_name_man_org.csv:あい:missing_entry:add_kanji"]
        assert f["proposed_fix"] == {"action": "add_kanji", "value": "愛"}
        assert f["status"] == "pending"  # female と man ファイルが矛盾 → 事前承認しない
        assert f["sources"] == {"ndl": 9, "wikidata": 2, "jmnedict": False}
        assert "哀" not in json.dumps(fs, ensure_ascii=False)

    def test_add_row_with_wikidata_gender_is_auto_approved(self, tmp_path):
        ds = gc.load_dataset(_dataset(tmp_path))
        fs, pending = gc.generate(_index(), ds, ALLOWED, today="2026-09-06")
        f = next(x for x in fs if x["proposed_fix"]["action"] == "add_row" and x["entry"].startswith("いつき,"))
        assert f["file"] == "first_name_man_org.csv"
        assert f["entry"] == "いつき,itsuki,樹"
        assert f["status"] == "approved"

    def test_gender_unknown_goes_to_pending_list(self, tmp_path):
        ds = gc.load_dataset(_dataset(tmp_path))
        fs, pending = gc.generate(_index(), ds, ALLOWED, today="2026-09-06")
        assert not [x for x in fs if x["entry"].startswith("りん,")]
        assert pending == [{"reading": "りん", "kanji": ["凛"], "sources": {"ndl": 6, "wikidata": 0, "jmnedict": False}}]

    def test_disallowed_kanji_excluded(self, tmp_path):
        ds = gc.load_dataset(_dataset(tmp_path))
        fs, pending = gc.generate(_index(), ds, ALLOWED, today="2026-09-06")
        assert "龘" not in json.dumps(fs, ensure_ascii=False) and not [p for p in pending if p["reading"] == "たつ"]

    def test_surname_mismatch(self, tmp_path):
        ds = gc.load_dataset(_dataset(tmp_path))
        fs, _ = gc.generate(_index(), ds, ALLOWED, today="2026-09-06")
        s = next(x for x in fs if x["file"] == "last_name_org.csv")
        assert s["entry"] == "金子,100,きんす,kinsu" and s["proposed_fix"] == {"action": "fix_reading", "value": "かねこ"}
        assert not [x for x in fs if x["file"] == "last_name_org.csv" and "佐藤" in x["entry"]]

    def test_max_candidates(self, tmp_path):
        ds = gc.load_dataset(_dataset(tmp_path))
        fs, _ = gc.generate(_index(), ds, ALLOWED, max_candidates=1, today="2026-09-06")
        adds = [x for x in fs if x["proposed_fix"]["action"].startswith("add_")]
        assert len(adds) == 1 and adds[0]["sources"]["ndl"] == 9  # 根拠最大のもの

    def test_carry_over(self):
        old = [{"id": "a", "status": "rejected"}, {"id": "b", "status": "applied"}]
        new = [{"id": "a", "status": "pending"}, {"id": "b", "status": "approved"}, {"id": "c", "status": "pending"}]
        out = gc.carry_over(new, old)
        assert [x["status"] for x in out] == ["rejected", "applied", "pending"]


def test_romaji_for():
    assert gc.romaji_for("いつき") == "itsuki"
    assert gc.romaji_for("けんいち") == "kenichi"
    assert gc.romaji_for("さとう") == "satou"
