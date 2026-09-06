"""triage_server.py（保留 findings の判断 UI）のテスト。"""
import http.client
import json
import os
import sys
import threading
import time
import urllib.parse

import pytest

import findings_io
import source_index as si
import sources_common as sc
import triage_server


def _dataset(tmp_path):
    d = tmp_path / "dataset"
    d.mkdir()
    (d / "first_name_man_org.csv").write_text(
        "あきお,akio,明男,風雅\nあきら,akira,明,晃\nふうが,fuuga,風雅\nたろう,tarou,太郎\n"
        "かづま,kazuma,一真,克真,克麻,勝真,和真\nかつま,katsuma,勝真\n"
        "だぶ,dabu,重\nだぶ,dabu,複\n",
        encoding="utf-8")
    (d / "first_name_man_opti.csv").write_text("あきら,akira,明\n", encoding="utf-8")
    (d / "first_name_woman_org.csv").write_text("さくら,sakura,桜\n", encoding="utf-8")
    (d / "first_name_woman_opti.csv").write_text("さくら,sakura,桜\n", encoding="utf-8")
    (d / "last_name_org.csv").write_text("佐藤,1887000,さとう,satou\n", encoding="utf-8")
    return str(d)


def _finding(id_, file, entry, action, value, check="kanji_reading_mismatch",
             status="pending", confidence="medium"):
    return {"id": id_, "file": file, "entry": entry, "check": check, "severity": "error",
            "confidence": confidence, "evidence": "テスト", "proposed_fix": {"action": action, "value": value},
            "status": status, "detected_at": "2026-08-30", "detected_by": "qa-review v1"}


def _types(signals):
    return [s["type"] for s in signals]


class TestSplitValues:
    def test_comma_and_ideographic_comma(self):
        assert triage_server.split_values("克真, 克麻, 勝真") == ["克真", "克麻", "勝真"]
        assert triage_server.split_values("克真、克麻") == ["克真", "克麻"]
        assert triage_server.split_values("克真,克麻、勝真") == ["克真", "克麻", "勝真"]

    def test_strip_and_drop_empty(self):
        assert triage_server.split_values(" 克真 ,, 克麻 ,") == ["克真", "克麻"]
        assert triage_server.split_values("") == []
        assert triage_server.split_values(None) == []
        assert triage_server.split_values("明男") == ["明男"]


class TestSignals:
    def test_dup_elsewhere(self, tmp_path):
        idx = triage_server.load_dataset_index(_dataset(tmp_path))
        f = _finding("a", "first_name_man_org.csv", "あきお,akio,明男,風雅", "remove_kanji", "風雅")
        sig = triage_server.compute_signals(f, idx)
        assert {"type": "dup_elsewhere", "kanji": "風雅", "readings": ["ふうが"]} in sig

    def test_no_dup_signal_when_only_here(self, tmp_path):
        idx = triage_server.load_dataset_index(_dataset(tmp_path))
        f = _finding("a", "first_name_man_org.csv", "あきお,akio,明男,風雅", "remove_kanji", "明男")
        assert not [s for s in triage_server.compute_signals(f, idx) if s["type"] == "dup_elsewhere"]

    def test_suffix_rule(self, tmp_path):
        idx = triage_server.load_dataset_index(_dataset(tmp_path))
        f = _finding("a", "first_name_man_org.csv", "あきお,akio,明男,太郎", "remove_kanji", "太郎")
        sig = triage_server.compute_signals(f, idx)
        assert {"type": "suffix_rule", "kanji": "太郎", "suffix": "郎", "expected": "ろう"} in sig
        ok = _finding("b", "first_name_man_org.csv", "たろう,tarou,太郎", "remove_kanji", "太郎")
        assert not [s for s in triage_server.compute_signals(ok, idx) if s["type"] == "suffix_rule"]

    def test_fix_reading_dup(self, tmp_path):
        idx = triage_server.load_dataset_index(_dataset(tmp_path))
        f = _finding("a", "first_name_man_org.csv", "あきお,akio,明男", "fix_reading", "あきら")
        assert {"type": "fix_reading_dup"} in triage_server.compute_signals(f, idx)
        g = _finding("b", "first_name_man_org.csv", "あきお,akio,明男", "fix_reading", "あきひこ")
        assert not [s for s in triage_server.compute_signals(g, idx) if s["type"] == "fix_reading_dup"]

    def test_fix_reading_dup_suppressed_for_last_name(self, tmp_path):
        # 姓CSVでは「同じ読みの別の姓」が正当なため、fix_reading_dup は出さない。
        ds = _dataset(tmp_path)
        with open(os.path.join(ds, "last_name_org.csv"), "w", encoding="utf-8") as f:
            f.write("佐藤,1887000,さとう,satou\n鈴木,1730000,すずき,suzuki\n")
        idx = triage_server.load_dataset_index(ds)
        f = _finding("a", "last_name_org.csv", "鈴木,1730000,すずき,suzuki", "fix_reading", "さとう")
        assert "fix_reading_dup" not in _types(triage_server.compute_signals(f, idx))

    def test_fix_reading_dup_still_shown_for_first_name(self, tmp_path):
        idx = triage_server.load_dataset_index(_dataset(tmp_path))
        f = _finding("a", "first_name_man_org.csv", "あきお,akio,明男", "fix_reading", "あきら")
        assert "fix_reading_dup" in _types(triage_server.compute_signals(f, idx))

    def test_multi_kanji_value_signals_per_kanji(self, tmp_path):
        # "克真, 克麻, 勝真" のような複数漢字 value は漢字ごとに判定する。
        idx = triage_server.load_dataset_index(_dataset(tmp_path))
        entry = "かづま,kazuma,一真,克真,克麻,勝真,和真"
        f = _finding("a", "first_name_man_org.csv", entry, "remove_kanji", "克真, 克麻, 勝真")
        sig = triage_server.compute_signals(f, idx)
        dups = [s for s in sig if s["type"] == "dup_elsewhere"]
        assert dups == [{"type": "dup_elsewhere", "kanji": "勝真", "readings": ["かつま"]}]
        assert "value_not_in_row" not in _types(sig)
        assert "entry_stale" not in _types(sig)

    def test_multi_kanji_suffix_rule_per_kanji(self, tmp_path):
        idx = triage_server.load_dataset_index(_dataset(tmp_path))
        f = _finding("a", "first_name_man_org.csv", "あきお,akio,明男,太郎,花子",
                     "remove_kanji", "太郎、花子")
        sig = [s for s in triage_server.compute_signals(f, idx) if s["type"] == "suffix_rule"]
        assert sig == [
            {"type": "suffix_rule", "kanji": "太郎", "suffix": "郎", "expected": "ろう"},
            {"type": "suffix_rule", "kanji": "花子", "suffix": "子", "expected": "こ"},
        ]

    def test_value_not_in_row(self, tmp_path):
        idx = triage_server.load_dataset_index(_dataset(tmp_path))
        f = _finding("a", "first_name_man_org.csv", "あきお,akio,明男,風雅",
                     "remove_kanji", "風雅, 幻影, 幽霊")
        sig = triage_server.compute_signals(f, idx)
        assert {"type": "value_not_in_row", "kanji": ["幻影", "幽霊"]} in sig
        ok = _finding("b", "first_name_man_org.csv", "あきお,akio,明男,風雅", "remove_kanji", "風雅")
        assert "value_not_in_row" not in _types(triage_server.compute_signals(ok, idx))

    def test_entry_stale_with_unique_current(self, tmp_path):
        idx = triage_server.load_dataset_index(_dataset(tmp_path))
        # 現行行は "あきお,akio,明男,風雅"。finding の entry は古い形。
        f = _finding("a", "first_name_man_org.csv", "あきお,akio,明男,風雅,旧字", "remove_kanji", "旧字")
        sig = triage_server.compute_signals(f, idx)
        assert {"type": "entry_stale", "current": "あきお,akio,明男,風雅"} in sig

    def test_entry_stale_without_unique_current(self, tmp_path):
        idx = triage_server.load_dataset_index(_dataset(tmp_path))
        gone = _finding("a", "first_name_man_org.csv", "きえた,kieta,消", "remove_kanji", "消")
        assert {"type": "entry_stale", "current": None} in triage_server.compute_signals(gone, idx)
        dup = _finding("b", "first_name_man_org.csv", "だぶ,dabu,重,複", "remove_kanji", "複")
        assert {"type": "entry_stale", "current": None} in triage_server.compute_signals(dup, idx)

    def test_entry_stale_last_name_keyed_by_kanji(self, tmp_path):
        idx = triage_server.load_dataset_index(_dataset(tmp_path))
        f = _finding("a", "last_name_org.csv", "佐藤,1000,さとう,satou", "fix_romaji", "sato")
        assert {"type": "entry_stale", "current": "佐藤,1887000,さとう,satou"} in triage_server.compute_signals(f, idx)
        ok = _finding("b", "last_name_org.csv", "佐藤,1887000,さとう,satou", "fix_romaji", "sato")
        assert "entry_stale" not in _types(triage_server.compute_signals(ok, idx))

    def test_no_entry_stale_when_current(self, tmp_path):
        idx = triage_server.load_dataset_index(_dataset(tmp_path))
        f = _finding("a", "first_name_man_org.csv", "あきお,akio,明男,風雅", "remove_kanji", "風雅")
        assert "entry_stale" not in _types(triage_server.compute_signals(f, idx))


class TestPhase2Signals:
    def _idx(self, tmp_path):
        return triage_server.load_dataset_index(_dataset(tmp_path))

    def test_add_actions_have_no_stale_signals(self, tmp_path):
        idx = self._idx(tmp_path)
        f = _finding("a", "first_name_man_org.csv", "いつき,itsuki,樹", "add_row", "", check="missing_entry")
        types = {s["type"] for s in triage_server.compute_signals(f, idx)}
        assert "entry_stale" not in types and "value_not_in_row" not in types

    def test_source_support_from_index(self, tmp_path):
        idx = self._idx(tmp_path)
        src = si.build_index([sc.record("ndl", "given", "風雅", "あきお", count=4)])
        f = _finding("a", "first_name_man_org.csv", "あきお,akio,明男,風雅", "remove_kanji", "風雅")
        sig = [s for s in triage_server.compute_signals(f, idx, source_index=src) if s["type"] == "source_support"]
        assert sig == [{"type": "source_support", "kanji": "風雅", "ndl": 4, "wikidata": 0, "jmnedict": False}]

    def test_source_support_prefers_finding_sources(self, tmp_path):
        idx = self._idx(tmp_path)
        f = _finding("a", "first_name_man_org.csv", "いつき,itsuki,樹", "add_row", "", check="missing_entry")
        f["sources"] = {"ndl": 7, "wikidata": 3, "jmnedict": True}
        sig = [s for s in triage_server.compute_signals(f, idx, source_index={"pairs": {}, "readings": {}})
               if s["type"] == "source_support"]
        assert sig[0]["ndl"] == 7 and sig[0]["jmnedict"] is True

    def test_add_kanji_without_sources_uses_candidate_kanji(self, tmp_path):
        # sources 無しの add_kanji は行の先頭漢字ではなく候補漢字（value）の根拠を索引から引く。
        idx = self._idx(tmp_path)
        src = si.build_index([sc.record("ndl", "given", "彰夫", "あきお", count=6),
                              sc.record("ndl", "given", "明男", "あきお", count=2)])
        f = _finding("a", "first_name_man_org.csv", "あきお,akio,明男,風雅", "add_kanji", "彰夫",
                     check="missing_entry")
        sig = [s for s in triage_server.compute_signals(f, idx, source_index=src) if s["type"] == "source_support"]
        assert sig == [{"type": "source_support", "kanji": "彰夫", "ndl": 6, "wikidata": 0, "jmnedict": False}]

    def test_search_url_for_add_kanji_includes_candidate(self, tmp_path):
        idx = self._idx(tmp_path)
        fs = [_finding("a", "first_name_man_org.csv", "あきお,akio,明男,風雅", "add_kanji", "彰夫",
                       check="missing_entry")]
        items = triage_server.build_items(fs, idx)
        q = urllib.parse.unquote(items[0]["search_url"])
        assert "彰夫 あきお 名前" in q
        assert items[0]["targets"] == []  # 削除対象のハイライトには使わない

    def test_ui_does_not_double_escape_source_support_label(self):
        with open(triage_server.UI_PATH, encoding="utf-8") as f:
            html = f.read()
        label = next(ln for ln in html.splitlines() if "case 'source_support'" in ln)
        assert "esc(" not in label  # 呼び出し側で esc 済み


class TestDatasetIndex:
    def test_rows_and_by_key(self, tmp_path):
        idx = triage_server.load_dataset_index(_dataset(tmp_path))
        man = idx["first_name_man_org.csv"]
        assert "あきお,akio,明男,風雅" in man["rows"]
        assert man["by_key"]["あきお"] == ["あきお,akio,明男,風雅"]
        assert man["by_key"]["だぶ"] == ["だぶ,dabu,重", "だぶ,dabu,複"]
        last = idx["last_name_org.csv"]
        assert last["by_key"]["佐藤"] == ["佐藤,1887000,さとう,satou"]
        assert last["readings"] == {"さとう"}


class TestBuildItems:
    def test_row_and_targets(self, tmp_path):
        idx = triage_server.load_dataset_index(_dataset(tmp_path))
        fs = [_finding("a", "first_name_man_org.csv", "あきお,akio,明男,風雅", "remove_kanji", "風雅"),
              _finding("b", "last_name_org.csv", "佐藤,1887000,さとう,satou", "fix_reading", "さと")]
        items = triage_server.build_items(fs, idx)
        assert items[0]["row"] == {"reading": "あきお", "romaji": "akio", "kanji": ["明男", "風雅"], "population": None}
        assert items[0]["targets"] == ["風雅"]
        assert items[1]["row"] == {"reading": "さとう", "romaji": "satou", "kanji": ["佐藤"], "population": "1887000"}
        assert "風雅" in urllib.parse.unquote(items[0]["search_url"])

    def test_multi_kanji_targets(self, tmp_path):
        idx = triage_server.load_dataset_index(_dataset(tmp_path))
        fs = [_finding("a", "first_name_man_org.csv", "かづま,kazuma,一真,克真,克麻,勝真,和真",
                       "remove_kanji", "克真, 克麻、勝真")]
        items = triage_server.build_items(fs, idx)
        assert items[0]["targets"] == ["克真", "克麻", "勝真"]
        q = urllib.parse.unquote(items[0]["search_url"])
        assert "克真 克麻 勝真 かづま 名前" in q

    def test_search_url_falls_back_to_row_kanji(self, tmp_path):
        idx = triage_server.load_dataset_index(_dataset(tmp_path))
        fs = [_finding("a", "first_name_man_org.csv", "かづま,kazuma,一真,克真,克麻,勝真,和真",
                       "fix_romaji", "kaduma")]
        items = triage_server.build_items(fs, idx)
        assert items[0]["targets"] == []
        q = urllib.parse.unquote(items[0]["search_url"])
        assert "一真 克真 克麻 かづま 名前" in q
        assert "勝真" not in q and "和真" not in q

    def test_counts(self):
        fs = [_finding("a", "f", "x,y", "none", "", status="pending"),
              _finding("b", "f", "x,y", "none", "", status="applied")]
        assert triage_server.count_statuses(fs) == {"pending": 1, "approved": 0, "rejected": 0, "applied": 1}


class TestDecision:
    def test_apply_and_save(self, tmp_path):
        p = str(tmp_path / "f.jsonl")
        fs = [_finding("a", "f", "x,y", "none", ""), _finding("b", "f", "x,y", "none", "")]
        findings_io.save_findings(p, fs)
        n = triage_server.apply_decision(fs, ["a"], "approved")
        assert n == 1 and fs[0]["status"] == "approved"
        triage_server.save_atomic(p, fs)
        assert findings_io.load_findings(p)[0]["status"] == "approved"
        assert not [x for x in os.listdir(str(tmp_path)) if x.endswith(".tmp")]

    def test_rejects_bad_input(self):
        fs = [_finding("a", "f", "x,y", "none", "", status="applied")]
        with pytest.raises(ValueError):
            triage_server.apply_decision(fs, ["a"], "approved")
        with pytest.raises(ValueError):
            triage_server.apply_decision(fs, ["zzz"], "approved")
        with pytest.raises(ValueError):
            triage_server.apply_decision(fs, [], "done")

    def test_state_restores_status_when_save_fails(self, tmp_path, monkeypatch):
        ds = _dataset(tmp_path)
        p = str(tmp_path / "f.jsonl")
        findings_io.save_findings(p, [_finding("a", "first_name_man_org.csv", "あきお,akio,明男,風雅", "remove_kanji", "風雅")])
        state = triage_server.TriageState(p, ds)

        def boom(path, findings):
            raise OSError("disk full")
        monkeypatch.setattr(triage_server, "save_atomic", boom)
        with pytest.raises(OSError):
            state.decide(["a"], "approved")
        assert state.findings[0]["status"] == "pending"
        assert findings_io.load_findings(p)[0]["status"] == "pending"

    def test_state_serializes_concurrent_decides(self, tmp_path, monkeypatch):
        ds = _dataset(tmp_path)
        p = str(tmp_path / "f.jsonl")
        findings_io.save_findings(p, [
            _finding("a", "first_name_man_org.csv", "あきお,akio,明男,風雅", "remove_kanji", "風雅"),
            _finding("b", "first_name_man_org.csv", "あきお,akio,明男,風雅", "remove_kanji", "明男"),
        ])
        state = triage_server.TriageState(p, ds)
        real_save = triage_server.save_atomic
        active = {"n": 0, "max": 0}
        guard = threading.Lock()

        def slow_save(path, findings):
            with guard:
                active["n"] += 1
                active["max"] = max(active["max"], active["n"])
            time.sleep(0.05)
            real_save(path, findings)
            with guard:
                active["n"] -= 1
        monkeypatch.setattr(triage_server, "save_atomic", slow_save)
        ts = [threading.Thread(target=state.decide, args=(["a"], "approved")),
              threading.Thread(target=state.decide, args=(["b"], "rejected"))]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        assert active["max"] == 1
        saved = {d["id"]: d["status"] for d in findings_io.load_findings(p)}
        assert saved == {"a": "approved", "b": "rejected"}


class TestHostAllowed:
    @pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.1:8765", "localhost", "localhost:1", "LOCALHOST:8765"])
    def test_allowed(self, host):
        assert triage_server.host_allowed(host)

    @pytest.mark.parametrize("host", ["", "evil.example", "evil.example:8765", "127.0.0.1.evil", "localhost:abc", "0.0.0.0:8765"])
    def test_denied(self, host):
        assert not triage_server.host_allowed(host)


class TestHttp:
    def _start(self, tmp_path):
        ds = _dataset(tmp_path)
        p = str(tmp_path / "f.jsonl")
        findings_io.save_findings(p, [
            _finding("a", "first_name_man_org.csv", "あきお,akio,明男,風雅", "remove_kanji", "風雅"),
            _finding("b", "first_name_man_org.csv", "あきお,akio,明男,風雅", "remove_kanji", "明男"),
        ])
        srv = triage_server.make_server(p, ds, port=0)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        return srv, p

    @staticmethod
    def _stop(srv):
        srv.shutdown()
        srv.server_close()

    def _req(self, srv, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=5)
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        h = {"Content-Type": "application/json"}
        if headers:
            h.update(headers)
        conn.request(method, path, body=payload, headers=h)
        resp = conn.getresponse()
        data = resp.read().decode("utf-8")
        conn.close()
        return resp.status, data

    def test_items_and_decide(self, tmp_path):
        srv, p = self._start(tmp_path)
        try:
            status, data = self._req(srv, "GET", "/api/items")
            assert status == 200
            body = json.loads(data)
            assert body["counts"]["pending"] == 2
            assert body["items"][0]["signals"][0]["type"] == "dup_elsewhere"
            status, data = self._req(srv, "POST", "/api/decide", {"ids": ["a"], "status": "approved"})
            assert status == 200 and json.loads(data)["counts"]["approved"] == 1
            assert findings_io.load_findings(p)[0]["status"] == "approved"
            status, _ = self._req(srv, "POST", "/api/decide", {"ids": ["zzz"], "status": "approved"})
            assert status == 400
            status, data = self._req(srv, "GET", "/")
            assert status == 200 and "<html" in data.lower()
        finally:
            self._stop(srv)

    def test_favicon_no_content(self, tmp_path):
        srv, _ = self._start(tmp_path)
        try:
            status, data = self._req(srv, "GET", "/favicon.ico")
            assert status == 204 and data == ""
        finally:
            self._stop(srv)

    def test_malformed_content_length(self, tmp_path):
        srv, _ = self._start(tmp_path)
        try:
            status, _ = self._req(srv, "POST", "/api/decide", {"ids": ["a"], "status": "approved"}, {"Content-Length": "abc"})
            assert status == 400
        finally:
            self._stop(srv)

    def test_negative_content_length(self, tmp_path):
        srv, p = self._start(tmp_path)
        try:
            status, _ = self._req(srv, "POST", "/api/decide", {"ids": ["a"], "status": "approved"}, {"Content-Length": "-1"})
            assert status == 400
            assert findings_io.load_findings(p)[0]["status"] == "pending"
        finally:
            self._stop(srv)

    def test_non_object_json_body(self, tmp_path):
        srv, _ = self._start(tmp_path)
        try:
            status, _ = self._req(srv, "POST", "/api/decide", [1, 2, 3])
            assert status == 400
        finally:
            self._stop(srv)

    def test_foreign_host_header_is_forbidden(self, tmp_path):
        srv, p = self._start(tmp_path)
        try:
            status, data = self._req(srv, "POST", "/api/decide", {"ids": ["a"], "status": "approved"},
                                     {"Host": "evil.example:%d" % srv.server_address[1]})
            assert status == 403 and "error" in json.loads(data)
            assert findings_io.load_findings(p)[0]["status"] == "pending"
            status, _ = self._req(srv, "POST", "/api/decide", {"ids": ["a"], "status": "approved"},
                                  {"Host": "localhost:%d" % srv.server_address[1]})
            assert status == 200
            status, _ = self._req(srv, "POST", "/api/decide", {"ids": ["a"], "status": "pending"},
                                  {"Host": "127.0.0.1"})
            assert status == 200
        finally:
            self._stop(srv)

    def test_concurrent_decides_both_saved(self, tmp_path):
        srv, p = self._start(tmp_path)
        results = {}
        try:
            def post(id_, status):
                results[id_] = self._req(srv, "POST", "/api/decide", {"ids": [id_], "status": status})
            ts = [threading.Thread(target=post, args=("a", "approved")),
                  threading.Thread(target=post, args=("b", "rejected"))]
            for t in ts:
                t.start()
            for t in ts:
                t.join()
            assert results["a"][0] == 200 and results["b"][0] == 200
            saved = {d["id"]: d["status"] for d in findings_io.load_findings(p)}
            assert saved == {"a": "approved", "b": "rejected"}
            assert not [x for x in os.listdir(str(tmp_path)) if x.endswith(".tmp")]
            status, data = self._req(srv, "GET", "/api/items")
            assert json.loads(data)["counts"] == {"pending": 0, "approved": 1, "rejected": 1, "applied": 0}
        finally:
            self._stop(srv)

    def test_save_failure_returns_500_and_restores_status(self, tmp_path, monkeypatch):
        srv, p = self._start(tmp_path)
        try:
            def boom(path, findings):
                raise OSError("disk full")
            monkeypatch.setattr(triage_server, "save_atomic", boom)
            status, data = self._req(srv, "POST", "/api/decide", {"ids": ["a"], "status": "approved"})
            assert status == 500
            assert "disk full" in json.loads(data)["error"]
            status, data = self._req(srv, "GET", "/api/items")
            assert status == 200
            assert json.loads(data)["counts"] == {"pending": 2, "approved": 0, "rejected": 0, "applied": 0}
            assert [d["status"] for d in findings_io.load_findings(p)] == ["pending", "pending"]
            assert not [x for x in os.listdir(str(tmp_path)) if x.endswith(".tmp")]
        finally:
            self._stop(srv)

    def test_items_reflect_stale_entry(self, tmp_path):
        ds = _dataset(tmp_path)
        p = str(tmp_path / "f.jsonl")
        findings_io.save_findings(p, [
            _finding("a", "first_name_man_org.csv", "あきお,akio,明男,風雅,旧", "remove_kanji", "旧"),
        ])
        srv = triage_server.make_server(p, ds, port=0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            status, data = self._req(srv, "GET", "/api/items")
            item = json.loads(data)["items"][0]
            assert {"type": "entry_stale", "current": "あきお,akio,明男,風雅"} in item["signals"]
            assert {"type": "value_not_in_row", "kanji": ["旧"]} not in item["signals"]
        finally:
            self._stop(srv)


class TestMain:
    def test_port_in_use_exits_1_with_message(self, tmp_path, monkeypatch, capsys):
        def boom(findings_path, dataset_dir, port=0):
            raise OSError(48, "Address already in use")
        monkeypatch.setattr(triage_server, "make_server", boom)
        monkeypatch.setattr(sys, "argv", ["triage_server.py", "--findings", "x.jsonl",
                                          "--dataset-dir", "d", "--port", "8765", "--no-browser"])
        assert triage_server.main() == 1
        err = capsys.readouterr().err
        assert "ポート 8765" in err and "使用中" in err

    @pytest.mark.skipif(sys.platform == "win32", reason="Windows は SO_REUSEADDR で二重 bind が成功しうる")
    def test_real_bind_conflict_raises_oserror(self, tmp_path):
        ds = _dataset(tmp_path)
        p = str(tmp_path / "f.jsonl")
        findings_io.save_findings(p, [])
        first = triage_server.make_server(p, ds, port=0)
        try:
            with pytest.raises(OSError):
                triage_server.make_server(p, ds, port=first.server_address[1])
        finally:
            first.server_close()
