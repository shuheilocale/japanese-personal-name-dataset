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

    def test_language_case_insensitive(self):
        # NDL endpoint returns lowercase "ja-kana" instead of "ja-Kana"
        bindings = [
            _b("a", "山田, 太郎", "ヤマダ, タロウ", "ja-kana"),  # lowercase
            _b("b", "山田, 花子", "ヤマダ, ハナコ", "ja-Kana"),   # mixed case
            _b("c", "山田, 次郎", "ヤマダ, ジロウ", "ja-latn"),   # excluded
        ]
        recs = fn.bindings_to_records(bindings)
        # Both ja-kana and ja-Kana should be accepted
        assert len(recs) == 4  # 2 records × 2 names each

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

    def test_manifest_persists_across_interruption(self, tmp_path):
        work = str(tmp_path / "work")
        call_count_1 = [0]

        def fetch_with_failure(url, params=None, headers=None):
            call_count_1[0] += 1
            # 最初の2つは成功、その後の3番目以降は失敗
            if call_count_1[0] <= 2:
                bindings = [_b("x", "山田, 太郎", "ヤマダ, タロウ", "ja-Kana")]
                body = {"results": {"bindings": bindings}}
                return json.dumps(body).encode("utf-8")
            else:
                raise RuntimeError("Network error")

        # 最初の実行：00, 01 は成功、02 で例外が発生
        try:
            fn.fetch_prefixes(["00", "01", "02"], work, fetch=fetch_with_failure)
        except RuntimeError:
            pass

        # manifest を確認：00, 01 は done に記録されている
        manifest = json.load(open(os.path.join(work, "manifest.json"), encoding="utf-8"))
        assert "00" in manifest["done"]
        assert "01" in manifest["done"]
        assert "02" not in manifest["done"]

        # 2回目の実行で 00, 01 はスキップされ、02 のみ再実行される
        call_count_2 = [0]
        def fetch_success(url, params=None, headers=None):
            call_count_2[0] += 1
            bindings = [_b("x", "山田, 太郎", "ヤマダ, タロウ", "ja-Kana")]
            body = {"results": {"bindings": bindings}}
            return json.dumps(body).encode("utf-8")

        fn.fetch_prefixes(["00", "01", "02"], work, fetch=fetch_success)
        # 00, 01 はスキップされるため、fetch は 02 に対してのみ呼び出される
        assert call_count_2[0] == 1

    def test_resume_fetches_unfetched_children_of_split_prefix(self, tmp_path):
        # split 済み接頭辞 "0" の子のうち 00〜02 だけが done の状態で中断した manifest から
        # 再実行すると、未取得の 03〜09 が取得され、00〜02 と "0" 自身は再取得されない。
        work = str(tmp_path / "work")
        os.makedirs(work)
        with open(os.path.join(work, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"done": ["00", "01", "02"], "split": ["0"], "saturated": []}, f)
        calls = []

        def fetch(url, params=None, headers=None):
            prefix = params["query"].split("ndlna/")[1].split("\"")[0]
            calls.append(prefix)
            body = {"results": {"bindings": [_b("x", "山田, 太郎", "ヤマダ, タロウ", "ja-Kana")]}}
            return json.dumps(body).encode("utf-8")

        fn.fetch_prefixes(["0"], work, fetch=fetch)
        assert calls == ["0%d" % i for i in range(3, 10)]
        manifest = json.load(open(os.path.join(work, "manifest.json"), encoding="utf-8"))
        assert manifest["done"] == ["0%d" % i for i in range(10)]
        assert manifest["split"] == ["0"]
        for i in range(3, 10):
            assert os.path.exists(os.path.join(work, "prefix-0%d.jsonl" % i))

    def test_resume_recurses_into_nested_split_prefixes(self, tmp_path):
        # 2 段階 split（"0" → "05" も split 済み）でも、孫の未取得分まで再帰して取得する。
        work = str(tmp_path / "work")
        os.makedirs(work)
        done = ["0%d" % i for i in range(10) if i != 5] + ["050", "051"]
        with open(os.path.join(work, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"done": done, "split": ["0", "05"], "saturated": []}, f)
        calls = []

        def fetch(url, params=None, headers=None):
            calls.append(params["query"].split("ndlna/")[1].split("\"")[0])
            body = {"results": {"bindings": [_b("x", "山田, 太郎", "ヤマダ, タロウ", "ja-Kana")]}}
            return json.dumps(body).encode("utf-8")

        fn.fetch_prefixes(["0"], work, fetch=fetch)
        assert calls == ["05%d" % i for i in range(2, 10)]
