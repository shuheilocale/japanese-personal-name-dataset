"""triage_server.py（保留 findings の判断 UI）のテスト。"""
import http.client
import json
import os
import threading
import urllib.parse

import pytest

import findings_io
import triage_server


def _dataset(tmp_path):
    d = tmp_path / "dataset"
    d.mkdir()
    (d / "first_name_man_org.csv").write_text(
        "あきお,akio,明男,風雅\nあきら,akira,明,晃\nふうが,fuuga,風雅\nたろう,tarou,太郎\n",
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


class TestSignals:
    def test_dup_elsewhere(self, tmp_path):
        idx = triage_server.load_dataset_index(_dataset(tmp_path))
        f = _finding("a", "first_name_man_org.csv", "あきお,akio,明男,風雅", "remove_kanji", "風雅")
        sig = triage_server.compute_signals(f, idx)
        assert {"type": "dup_elsewhere", "readings": ["ふうが"]} in sig

    def test_no_dup_signal_when_only_here(self, tmp_path):
        idx = triage_server.load_dataset_index(_dataset(tmp_path))
        f = _finding("a", "first_name_man_org.csv", "あきお,akio,明男,風雅", "remove_kanji", "明男")
        assert not [s for s in triage_server.compute_signals(f, idx) if s["type"] == "dup_elsewhere"]

    def test_suffix_rule(self, tmp_path):
        idx = triage_server.load_dataset_index(_dataset(tmp_path))
        f = _finding("a", "first_name_man_org.csv", "あきお,akio,明男,太郎", "remove_kanji", "太郎")
        sig = triage_server.compute_signals(f, idx)
        assert {"type": "suffix_rule", "suffix": "郎", "expected": "ろう"} in sig
        ok = _finding("b", "first_name_man_org.csv", "たろう,tarou,太郎", "remove_kanji", "太郎")
        assert not [s for s in triage_server.compute_signals(ok, idx) if s["type"] == "suffix_rule"]

    def test_fix_reading_dup(self, tmp_path):
        idx = triage_server.load_dataset_index(_dataset(tmp_path))
        f = _finding("a", "first_name_man_org.csv", "あきお,akio,明男", "fix_reading", "あきら")
        assert {"type": "fix_reading_dup"} in triage_server.compute_signals(f, idx)
        g = _finding("b", "first_name_man_org.csv", "あきお,akio,明男", "fix_reading", "あきひこ")
        assert not [s for s in triage_server.compute_signals(g, idx) if s["type"] == "fix_reading_dup"]


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

    def _req(self, srv, method, path, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=5)
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        conn.request(method, path, body=payload, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        data = resp.read().decode("utf-8")
        conn.close()
        return resp.status, data

    def _req_with_headers(self, srv, method, path, body=None, headers=None):
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
            srv.shutdown()

    def test_malformed_content_length(self, tmp_path):
        srv, _ = self._start(tmp_path)
        try:
            status, _ = self._req_with_headers(srv, "POST", "/api/decide", {"ids": ["a"], "status": "approved"}, {"Content-Length": "abc"})
            assert status == 400
        finally:
            srv.shutdown()

    def test_non_object_json_body(self, tmp_path):
        srv, _ = self._start(tmp_path)
        try:
            status, _ = self._req(srv, "POST", "/api/decide", [1, 2, 3])
            assert status == 400
        finally:
            srv.shutdown()
