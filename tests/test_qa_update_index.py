"""source_index.py のテスト。"""
import source_index as si
import sources_common as sc


def _recs():
    return [
        sc.record("ndl", "given", "漱石", "そうせき", count=12),
        sc.record("wikidata", "given", "漱石", "そうせき", gender="male", count=3),
        sc.record("wikidata", "given", "", "そうせき", gender="male", count=5),
        sc.record("jmnedict", "given", "漱石", "そうせき", gender="male"),
        sc.record("ndl", "surname", "夏目", "なつめ", count=40),
        sc.record("jmnedict", "given", "薫", "かおる", gender="unisex"),
        sc.record("wikidata", "given", "", "かおる", gender="male", count=1),
        sc.record("wikidata", "given", "", "かおる", gender="female", count=1),
    ]


class TestBuild:
    def test_pairs_and_readings(self):
        idx = si.build_index(_recs())
        p = idx["pairs"][si.pair_key("given", "漱石", "そうせき")]
        assert p["ndl"] == 12 and p["wikidata"] == 3 and p["jmnedict"] is True
        assert p["gender"]["wikidata"] == "male"
        r = idx["readings"][si.reading_key("given", "そうせき")]
        assert r["wikidata"] == 8 and r["ndl"] == 12  # 漢字付き 3 + 仮名のみ 5

    def test_support_default(self):
        idx = si.build_index(_recs())
        assert si.support(idx, "given", "無い", "ない") == {"ndl": 0, "wikidata": 0, "jmnedict": False}
        assert si.support(idx, "surname", "夏目", "なつめ")["ndl"] == 40

    def test_gender_of(self):
        idx = si.build_index(_recs())
        assert si.gender_of(idx, "given", "そうせき") == "male"
        assert si.gender_of(idx, "given", "かおる") == "unisex"  # wikidata で male/female 両方
        assert si.gender_of(idx, "given", "ない") is None

    def test_roundtrip(self, tmp_path):
        idx = si.build_index(_recs())
        p = str(tmp_path / "index.json")
        si.save_index(p, idx)
        assert si.load_index(p) == idx
