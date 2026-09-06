"""sources_common.py（qa-update 共通ユーティリティ）のテスト。"""
import io
import os
import subprocess
import sys

import pytest

import sources_common as sc


class TestKana:
    def test_kata_to_hira(self):
        assert sc.kata_to_hira("ナツメ") == "なつめ"
        assert sc.kata_to_hira("ソウセキ") == "そうせき"
        assert sc.kata_to_hira("ヴィ") == "ゔぃ"
        assert sc.kata_to_hira("タロー") == "たろー"
        assert sc.kata_to_hira("漱石") == "漱石"


class TestNamePart:
    def test_accepts_japanese(self):
        for s in ["漱石", "たろう", "佐々木", "一ノ瀬", "凛"]:
            assert sc.is_japanese_name_part(s), s

    def test_rejects_foreign_or_garbage(self):
        for s in ["", "ジョン", "山田・太郎", "John", "太郎2", "六文字以上の名前です"]:
            assert not sc.is_japanese_name_part(s), s


class TestRecord:
    def test_valid(self):
        r = sc.record("ndl", "given", "漱石", "そうせき", count=3)
        assert r == {"source": "ndl", "kind": "given", "kanji": "漱石", "reading": "そうせき",
                     "gender": None, "count": 3}

    def test_kana_only_kanji_allowed_for_reading_evidence(self):
        r = sc.record("wikidata", "given", "", "まさとし", gender="male")
        assert r["kanji"] == "" and r["gender"] == "male"

    def test_invalid(self):
        with pytest.raises(ValueError):
            sc.record("ndl", "given", "漱石", "ソウセキ")  # 読みがひらがなでない
        with pytest.raises(ValueError):
            sc.record("ndl", "place", "漱石", "そうせき")
        with pytest.raises(ValueError):
            sc.record("ndl", "given", "漱石", "そうせき", gender="boy")


class TestJsonl:
    def test_roundtrip(self, tmp_path):
        p = str(tmp_path / "x.jsonl")
        recs = [sc.record("ndl", "given", "漱石", "そうせき"), sc.record("ndl", "surname", "夏目", "なつめ")]
        sc.write_jsonl(p, recs)
        assert sc.read_jsonl(p) == recs
        assert b"\r\n" not in open(p, "rb").read()


class TestHttpGet:
    def test_retries_then_succeeds(self):
        calls = []

        class Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def opener(req, timeout=0):
            calls.append(req.get_header("User-agent"))
            if len(calls) < 3:
                raise OSError("boom")
            return Resp(b"ok")

        data = sc.http_get("http://example.invalid/x", params={"q": "1"}, opener=opener, sleep=0)
        assert data == b"ok" and len(calls) == 3
        assert calls[0] == sc.USER_AGENT

    def test_gives_up(self):
        def opener(req, timeout=0):
            raise OSError("boom")
        with pytest.raises(RuntimeError):
            sc.http_get("http://example.invalid/x", opener=opener, sleep=0, retries=2)


CLI_SCRIPTS = [
    "build_kanji_list.py", "fetch_jmnedict.py", "fetch_ndl.py", "fetch_wikidata.py",
    "gender_batch.py", "generate_candidates.py", "source_index.py",
]


@pytest.mark.parametrize("script", CLI_SCRIPTS)
def test_cli_help_survives_non_utf8_stdout(script):
    """Windows の cp1252 コンソールを PYTHONIOENCODING で模し、日本語ヘルプが落ちないことを確認する。

    CI の windows-latest では stdout が cp1252 になり、argparse の日本語 help が
    UnicodeEncodeError で終了コード 1 になった。各 CLI は起動時に stdout/stderr を
    UTF-8 に再設定する必要がある。subprocess で素の Python プロセスから実行する。
    """
    scripts_dir = os.path.dirname(os.path.abspath(sc.__file__))
    env = dict(os.environ, PYTHONIOENCODING="cp1252")
    result = subprocess.run([sys.executable, os.path.join(scripts_dir, script), "--help"],
                            capture_output=True, env=env)
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert "usage" in result.stdout.decode("utf-8", "replace")
