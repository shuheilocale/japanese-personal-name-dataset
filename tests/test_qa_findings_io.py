"""findings_io.py（疑義台帳・検証済みキャッシュ）のテスト。"""
import os

import pytest

import findings_io


def _valid_finding():
    return {
        "id": "fn-man-org:あいいちろう",
        "file": "first_name_man_org.csv",
        "entry": "あいいちろう,aichirou,愛一朗,愛一郎",
        "check": "kanji_reading_mismatch",
        "severity": "error",
        "confidence": "high",
        "evidence": "愛一朗を「あいいちろう」と読む用例が確認できない",
        "proposed_fix": {"action": "remove_kanji", "value": "愛一朗"},
        "status": "pending",
        "detected_at": "2026-07-27",
        "detected_by": "qa-review v1",
    }


class TestValidateFinding:
    def test_valid(self):
        assert findings_io.validate_finding(_valid_finding()) == []

    def test_missing_field(self):
        f = _valid_finding()
        del f["evidence"]
        assert findings_io.validate_finding(f)

    def test_bad_enum_values(self):
        for key, bad in [
            ("check", "spelling"), ("severity", "fatal"),
            ("confidence", "certain"), ("status", "done"),
        ]:
            f = _valid_finding()
            f[key] = bad
            assert findings_io.validate_finding(f), key

    def test_bad_action(self):
        f = _valid_finding()
        f["proposed_fix"] = {"action": "delete_everything", "value": ""}
        assert findings_io.validate_finding(f)

    def test_file_path_traversal_rejected(self):
        f = _valid_finding()
        f["file"] = "../x.csv"
        assert findings_io.validate_finding(f)

    def test_file_not_in_whitelist_rejected(self):
        f = _valid_finding()
        f["file"] = "not_a_real_file.csv"
        assert findings_io.validate_finding(f)

    def test_move_to_file_target_must_be_first_name_file(self):
        f = _valid_finding()
        f["proposed_fix"] = {"action": "move_to_file", "value": "last_name_org.csv"}
        assert findings_io.validate_finding(f)

    def test_move_to_file_path_traversal_rejected(self):
        f = _valid_finding()
        f["proposed_fix"] = {"action": "move_to_file", "value": "../x.csv"}
        assert findings_io.validate_finding(f)

    def test_move_to_file_to_valid_first_name_file_ok(self):
        f = _valid_finding()
        f["proposed_fix"] = {"action": "move_to_file",
                             "value": "first_name_woman_org.csv"}
        assert findings_io.validate_finding(f) == []


class TestJsonlRoundtrip:
    def test_append_and_load(self, tmp_path):
        p = str(tmp_path / "sub" / "f.jsonl")
        findings_io.append_findings(p, [_valid_finding()])
        findings_io.append_findings(p, [_valid_finding()])
        assert len(findings_io.load_findings(p)) == 2

    def test_append_rejects_invalid(self, tmp_path):
        p = str(tmp_path / "f.jsonl")
        bad = _valid_finding()
        bad["status"] = "???"
        with pytest.raises(ValueError):
            findings_io.append_findings(p, [bad])
        assert not os.path.exists(p)

    def test_save_replaces(self, tmp_path):
        p = str(tmp_path / "f.jsonl")
        f = _valid_finding()
        findings_io.append_findings(p, [f])
        f2 = dict(f)
        f2["status"] = "approved"
        findings_io.save_findings(p, [f2])
        assert findings_io.load_findings(p)[0]["status"] == "approved"

    def test_append_and_save_use_lf_only(self, tmp_path):
        p = str(tmp_path / "f.jsonl")
        f = _valid_finding()
        findings_io.append_findings(p, [f])
        findings_io.save_findings(p, [f, f])
        raw = open(p, "rb").read()
        assert b"\r\n" not in raw
        assert raw.count(b"\n") == 2


class TestVerifiedCache:
    def test_hash_is_stable_and_content_sensitive(self):
        h1 = findings_io.entry_hash("a.csv", "あい,ai,藍")
        assert h1 == findings_io.entry_hash("a.csv", "あい,ai,藍")
        assert h1 != findings_io.entry_hash("b.csv", "あい,ai,藍")
        assert h1 != findings_io.entry_hash("a.csv", "あい,ai,愛")
        assert len(h1) == 16

    def test_load_missing_returns_empty(self, tmp_path):
        assert findings_io.load_verified(str(tmp_path / "v.json")) == {}

    def test_roundtrip(self, tmp_path):
        p = str(tmp_path / "v.json")
        findings_io.save_verified(p, {"abc": {"file": "a.csv", "reading": "あい",
                                              "verified_at": "2026-07-27"}})
        assert "abc" in findings_io.load_verified(p)

    def test_save_verified_uses_lf_only(self, tmp_path):
        p = str(tmp_path / "v.json")
        findings_io.save_verified(p, {"abc": {"file": "a.csv", "reading": "あい",
                                              "verified_at": "2026-07-27"}})
        raw = open(p, "rb").read()
        assert b"\r\n" not in raw
        assert "abc" in findings_io.load_verified(p)
