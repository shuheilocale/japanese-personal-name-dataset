"""fetch_wikidata.py のテスト（ネットワークはフィクスチャで代替）。"""
import json

import fetch_wikidata as fw


class TestQuery:
    def test_query_mentions_class_and_kana(self):
        q = fw.build_query("given", "Q12308941")
        assert "wd:Q12308941" in q and "wdt:P1814" in q and "wdt:P735" in q
        q2 = fw.build_query("surname", "Q101352")
        assert "wdt:P734" in q2


class TestRows:
    def test_kanji_and_kana_rows(self):
        rows = [{"label": "博", "kana": "ひろし", "people": "423"},
                {"label": "まさとし", "kana": "まさとし", "people": "190"},
                {"label": "宏", "kana": "ヒロシ", "people": "0"}]
        recs = fw.rows_to_records("given", "male", rows)
        assert recs[0] == {"source": "wikidata", "kind": "given", "kanji": "博", "reading": "ひろし",
                           "gender": "male", "count": 423}
        assert recs[1]["kanji"] == "" and recs[1]["reading"] == "まさとし"
        assert recs[2]["reading"] == "ひろし" and recs[2]["count"] == 1

    def test_skips_invalid(self):
        rows = [{"label": "John", "kana": "ジョン", "people": "1"},
                {"label": "博", "kana": "hiroshi", "people": "1"}]
        assert fw.rows_to_records("given", "male", rows) == []

    def test_parse_sparql_json(self):
        body = json.dumps({"results": {"bindings": [
            {"label": {"value": "博"}, "kana": {"value": "ひろし"}, "people": {"value": "3"}}]}})
        assert fw.parse_bindings(body.encode("utf-8")) == [{"label": "博", "kana": "ひろし", "people": "3"}]
