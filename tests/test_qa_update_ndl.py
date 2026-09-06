"""fetch_ndl.py のテスト（ネットワークはフィクスチャで代替）。"""
import json
import os

import fetch_ndl as fn


def _b(s, label, yomi, lang):
    return {"s": {"value": s}, "label": {"value": label},
            "yomi": {"value": yomi, "xml:lang": lang}}


class TestParse:
    def test_label(self):
        assert fn.parse_label("夏目, 漱石, 1867-1916") == ("夏目", "漱石")
        assert fn.parse_label("内藤, 英憲") == ("内藤", "英憲")
        assert fn.parse_label("夏目漱石") is None
        assert fn.parse_label("スミス, ジョン") is None
        assert fn.parse_label("山田, 太郎 (1950-)") is None

    def test_yomi(self):
        assert fn.parse_yomi("ナツメ, ソウセキ, 1867-1916") == ("なつめ", "そうせき")
        assert fn.parse_yomi("Natsume, Soseki") is None


class TestRecords:
    def test_only_kana_lang_and_both_kinds(self):
        bindings = [
            _b("http://id.ndl.go.jp/auth/ndlna/1", "夏目, 漱石, 1867-1916", "Natsume, Soseki", "ja-latn"),
            _b("http://id.ndl.go.jp/auth/ndlna/1", "夏目, 漱石, 1867-1916", "ナツメ, ソウセキ, 1867-1916", "ja-Kana"),
            _b("http://id.ndl.go.jp/auth/ndlna/2", "スミス, ジョン", "スミス, ジョン", "ja-Kana"),
        ]
        recs = fn.bindings_to_records(bindings)
        assert {"source": "ndl", "kind": "given", "kanji": "漱石", "reading": "そうせき",
                "gender": None, "count": 1} in recs
        assert {"source": "ndl", "kind": "surname", "kanji": "夏目", "reading": "なつめ",
                "gender": None, "count": 1} in recs
        assert len(recs) == 2

    def test_aggregate(self):
        recs = fn.bindings_to_records([
            _b("a", "山田, 太郎", "ヤマダ, タロウ", "ja-Kana"),
            _b("b", "山田, 太郎", "ヤマダ, タロウ", "ja-Kana"),
            _b("c", "山田, 花子", "ヤマダ, ハナコ", "ja-Kana"),
        ])
        agg = {(r["kind"], r["kanji"], r["reading"]): r["count"] for r in fn.aggregate(recs)}
        assert agg[("surname", "山田", "やまだ")] == 3
        assert agg[("given", "太郎", "たろう")] == 2


class TestResume:
    def test_fetch_prefixes_resumes(self, tmp_path):
        work = str(tmp_path / "work")
        calls = []

        def fetch(url, params=None, headers=None):
            calls.append(params["query"])
            body = {"results": {"bindings": [
                _b("x", "山田, 太郎", "ヤマダ, タロウ", "ja-Kana")]}}
            return json.dumps(body).encode("utf-8")

        fn.fetch_prefixes(["00", "01"], work, fetch=fetch)
        assert len(calls) == 2
        fn.fetch_prefixes(["00", "01", "02"], work, fetch=fetch)
        assert len(calls) == 3  # 完了済み接頭辞はスキップ
        manifest = json.load(open(os.path.join(work, "manifest.json"), encoding="utf-8"))
        assert manifest["done"] == ["00", "01", "02"]

    def test_adaptive_subdivision(self, tmp_path):
        work = str(tmp_path / "work")
        calls = []

        def fetch(url, params=None, headers=None):
            query = params["query"]
            calls.append(query)
            # "0" に対しては cap (1000) 件を返す
            # "00".."09" に対しては 3 件ずつを返す
            prefix = query.split("ndlna/")[1].split("\"")[0]
            if prefix == "0":
                bindings = [_b("x%d" % i, "山田, 太郎", "ヤマダ, タロウ", "ja-Kana")
                           for i in range(1000)]
            else:
                bindings = [_b("x%d" % i, "山田, 太郎", "ヤマダ, タロウ", "ja-Kana")
                           for i in range(3)]
            body = {"results": {"bindings": bindings}}
            return json.dumps(body).encode("utf-8")

        fn.fetch_prefixes(["0"], work, fetch=fetch, cap=1000, max_depth=9)
        manifest = json.load(open(os.path.join(work, "manifest.json"), encoding="utf-8"))
        # "0" は split に入り、"00".."09" が done に入る
        assert "0" in manifest["split"]
        assert set(manifest["done"]) == {"00", "01", "02", "03", "04", "05", "06", "07", "08", "09"}
        assert not manifest.get("saturated")

    def test_saturated_prefix(self, tmp_path):
        work = str(tmp_path / "work")

        def fetch(url, params=None, headers=None):
            # 常に cap (1000) 件を返す
            bindings = [_b("x%d" % i, "山田, 太郎", "ヤマダ, タロウ", "ja-Kana")
                       for i in range(1000)]
            body = {"results": {"bindings": bindings}}
            return json.dumps(body).encode("utf-8")

        fn.fetch_prefixes(["0"], work, fetch=fetch, cap=1000, max_depth=1)
        manifest = json.load(open(os.path.join(work, "manifest.json"), encoding="utf-8"))
        # max_depth=1 で "0" が cap に達しているため saturated に入る
        assert "0" in manifest["saturated"]
