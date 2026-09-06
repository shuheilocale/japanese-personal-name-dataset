"""rebase_findings.py（findings entry の現行行への再ベース）のテスト。"""
import os
import sys

import findings_io
import rebase_findings
import triage_server

MAN = "first_name_man_org.csv"
LAST = "last_name_org.csv"
KAZUMA = "かづま,kazuma,一真,克真,克麻,勝真,和真"


def _dataset(tmp_path):
    d = tmp_path / "dataset"
    d.mkdir()
    (d / MAN).write_text(
        "あきお,akio,明男\n" + KAZUMA + "\nだぶ,dabu,重\nだぶ,dabu,複\nすみ,sumi,済\n",
        encoding="utf-8")
    (d / "first_name_man_opti.csv").write_text("あきら,akira,明\n", encoding="utf-8")
    (d / "first_name_woman_org.csv").write_text("さくら,sakura,桜\n", encoding="utf-8")
    (d / "first_name_woman_opti.csv").write_text("さくら,sakura,桜\n", encoding="utf-8")
    (d / LAST).write_text("佐藤,1887000,さとう,satou\n", encoding="utf-8")
    return str(d)


def _finding(id_, file, entry, action, value, status="pending", check="kanji_reading_mismatch"):
    return {"id": id_, "file": file, "entry": entry, "check": check, "severity": "error",
            "confidence": "medium", "evidence": "根拠", "proposed_fix": {"action": action, "value": value},
            "status": status, "detected_at": "2026-07-27", "detected_by": "qa-review v1"}


def _index(tmp_path):
    return triage_server.load_dataset_index(_dataset(tmp_path))


class TestRebase:
    def test_unique_match_rebases_entry_and_keeps_id(self, tmp_path):
        f = _finding("x", MAN, "あきお,akio,明男,旧", "remove_kanji", "旧")
        r = rebase_findings.rebase([f], _index(tmp_path))
        assert r == {"rebased": ["x"], "reopened": [], "unresolved": []}
        assert f["entry"] == "あきお,akio,明男"
        assert f["id"] == "x" and f["status"] == "pending" and f["evidence"] == "根拠"

    def test_approved_is_rebased_too(self, tmp_path):
        f = _finding("x", MAN, "あきお,akio,明男,旧", "remove_kanji", "旧", status="approved")
        r = rebase_findings.rebase([f], _index(tmp_path))
        assert r["rebased"] == ["x"] and f["entry"] == "あきお,akio,明男" and f["status"] == "approved"

    def test_current_entry_is_untouched(self, tmp_path):
        f = _finding("x", MAN, "あきお,akio,明男", "remove_kanji", "明男")
        r = rebase_findings.rebase([f], _index(tmp_path))
        assert r == {"rebased": [], "reopened": [], "unresolved": []}
        assert f["entry"] == "あきお,akio,明男"

    def test_multiple_key_matches_are_unresolved(self, tmp_path):
        f = _finding("x", MAN, "だぶ,dabu,重,複", "remove_kanji", "複")
        r = rebase_findings.rebase([f], _index(tmp_path))
        assert r["unresolved"] == ["x"] and r["rebased"] == []
        assert f["entry"] == "だぶ,dabu,重,複"

    def test_no_key_match_is_unresolved(self, tmp_path):
        f = _finding("x", MAN, "きえた,kieta,消", "remove_row", "")
        r = rebase_findings.rebase([f], _index(tmp_path))
        assert r["unresolved"] == ["x"]
        assert f["entry"] == "きえた,kieta,消"

    def test_rejected_and_applied_are_not_rebased(self, tmp_path):
        rej = _finding("r", MAN, "あきお,akio,明男,旧", "remove_kanji", "旧", status="rejected")
        app = _finding("a", MAN, "あきお,akio,明男,旧", "fix_romaji", "akio2", status="applied")
        r = rebase_findings.rebase([rej, app], _index(tmp_path))
        assert r == {"rebased": [], "reopened": [], "unresolved": []}
        assert rej["entry"] == "あきお,akio,明男,旧" and app["entry"] == "あきお,akio,明男,旧"

    def test_last_name_is_keyed_by_kanji(self, tmp_path):
        f = _finding("x", LAST, "佐藤,1000,さとう,sato", "fix_romaji", "satou", check="romaji_reading_mismatch")
        r = rebase_findings.rebase([f], _index(tmp_path))
        assert r["rebased"] == ["x"] and f["entry"] == "佐藤,1887000,さとう,satou"

    def test_unknown_file_is_ignored(self, tmp_path):
        f = _finding("x", "unknown.csv", "a,b,c", "remove_kanji", "c")
        r = rebase_findings.rebase([f], _index(tmp_path))
        assert r == {"rebased": [], "reopened": [], "unresolved": []}


class TestReopenUnapplied:
    def test_reopens_when_target_kanji_remains(self, tmp_path):
        f = _finding("x", MAN, KAZUMA, "remove_kanji", "克真, 克麻, 勝真", status="applied")
        r = rebase_findings.rebase([f], _index(tmp_path), reopen_unapplied=True, today="2026-08-30")
        assert r == {"rebased": [], "reopened": ["x"], "unresolved": []}
        assert f["status"] == "approved" and f["entry"] == KAZUMA and f["id"] == "x"
        assert f["evidence"] == "根拠（再オープン: 未適用を検出 2026-08-30）"

    def test_reopen_updates_stale_entry_to_current(self, tmp_path):
        f = _finding("x", MAN, KAZUMA + ",旧", "remove_kanji", "克真、勝真", status="applied")
        r = rebase_findings.rebase([f], _index(tmp_path), reopen_unapplied=True)
        assert r["reopened"] == ["x"] and f["entry"] == KAZUMA and f["status"] == "approved"

    def test_reopens_when_only_some_targets_remain(self, tmp_path):
        f = _finding("x", MAN, KAZUMA, "remove_kanji", "消えた, 勝真", status="applied")
        r = rebase_findings.rebase([f], _index(tmp_path), reopen_unapplied=True)
        assert r["reopened"] == ["x"]

    def test_no_reopen_when_kanji_already_removed(self, tmp_path):
        f = _finding("x", MAN, "すみ,sumi,済,済無", "remove_kanji", "済無", status="applied")
        r = rebase_findings.rebase([f], _index(tmp_path), reopen_unapplied=True)
        assert r == {"rebased": [], "reopened": [], "unresolved": []}
        assert f["status"] == "applied" and f["entry"] == "すみ,sumi,済,済無" and f["evidence"] == "根拠"

    def test_no_reopen_without_flag(self, tmp_path):
        f = _finding("x", MAN, KAZUMA, "remove_kanji", "克真", status="applied")
        r = rebase_findings.rebase([f], _index(tmp_path))
        assert r["reopened"] == [] and f["status"] == "applied"

    def test_no_reopen_for_other_actions(self, tmp_path):
        f = _finding("x", MAN, KAZUMA, "fix_romaji", "kazuma2", status="applied", check="romaji_reading_mismatch")
        r = rebase_findings.rebase([f], _index(tmp_path), reopen_unapplied=True)
        assert r["reopened"] == [] and f["status"] == "applied"

    def test_no_reopen_when_current_row_ambiguous_or_gone(self, tmp_path):
        dup = _finding("d", MAN, "だぶ,dabu,重,複", "remove_kanji", "複", status="applied")
        gone = _finding("g", MAN, "きえた,kieta,消", "remove_kanji", "消", status="applied")
        r = rebase_findings.rebase([dup, gone], _index(tmp_path), reopen_unapplied=True)
        assert r == {"rebased": [], "reopened": [], "unresolved": []}
        assert dup["status"] == "applied" and gone["status"] == "applied"

    def test_reopen_is_idempotent(self, tmp_path):
        f = _finding("x", MAN, KAZUMA, "remove_kanji", "克真", status="applied")
        idx = _index(tmp_path)
        rebase_findings.rebase([f], idx, reopen_unapplied=True, today="2026-08-30")
        r2 = rebase_findings.rebase([f], idx, reopen_unapplied=True, today="2026-08-31")
        assert r2 == {"rebased": [], "reopened": [], "unresolved": []}
        assert f["evidence"] == "根拠（再オープン: 未適用を検出 2026-08-30）"


def test_rebase_skips_add_actions(tmp_path):
    # ブリーフ記載の呼び出し形（rebase(findings_path, dataset_dir, dry_run=...)）は
    # 現行の rebase(findings, index, ...) シグネチャと合わないため、既存の呼び出し規約
    # （findings リスト + load_dataset_index の結果）に合わせて検証する。戻り値の
    # "unresolved" も現行実装どおりリスト（0件なら空リスト）でアサートする。
    f = _finding("x", MAN, "いつき,itsuki,樹", "add_row", "", status="pending", check="missing_entry")
    r = rebase_findings.rebase([f], _index(tmp_path))
    assert f["entry"] == "いつき,itsuki,樹"
    assert r["unresolved"] == []


def test_rebase_does_not_look_up_current_row_for_add_actions(tmp_path, monkeypatch):
    # add_* は対象外なので current_row_for（同キー行の検索）を呼ばない。
    calls = []
    real = triage_server.current_row_for

    def spy(entry, info):
        calls.append(entry)
        return real(entry, info)
    monkeypatch.setattr(triage_server, "current_row_for", spy)
    fs = [_finding("r", MAN, "いつき,itsuki,樹", "add_row", "", status="pending", check="missing_entry"),
          _finding("k", MAN, "あきお,akio,明男,旧", "add_kanji", "新", status="approved", check="missing_entry"),
          _finding("s", MAN, "あきお,akio,明男,旧", "remove_kanji", "旧")]
    r = rebase_findings.rebase(fs, _index(tmp_path))
    assert calls == ["あきお,akio,明男,旧"] and r["rebased"] == ["s"]


class TestMain:
    def _run(self, tmp_path, monkeypatch, extra):
        ds = _dataset(tmp_path)
        p = str(tmp_path / "f.jsonl")
        findings_io.save_findings(p, [
            _finding("stale", MAN, "あきお,akio,明男,旧", "remove_kanji", "旧"),
            _finding("unapplied", MAN, KAZUMA, "remove_kanji", "克真, 克麻", status="applied"),
            _finding("lost", MAN, "きえた,kieta,消", "remove_row", ""),
        ])
        monkeypatch.setattr(sys, "argv", ["rebase_findings.py", "--findings", p, "--dataset-dir", ds] + extra)
        assert rebase_findings.main() == 0
        return p

    def test_dry_run_reports_counts_and_writes_nothing(self, tmp_path, monkeypatch, capsys):
        p = self._run(tmp_path, monkeypatch, ["--dry-run", "--reopen-unapplied"])
        out = capsys.readouterr().out
        assert "再ベース 1 件 / 再オープン 1 件 / 未解決 1 件" in out
        assert "dry-run" in out and "lost" in out and "unapplied" in out
        saved = {d["id"]: d for d in findings_io.load_findings(p)}
        assert saved["stale"]["entry"] == "あきお,akio,明男,旧"
        assert saved["unapplied"]["status"] == "applied"
        assert not [x for x in os.listdir(str(tmp_path)) if x.endswith(".tmp")]

    def test_writes_atomically(self, tmp_path, monkeypatch, capsys):
        p = self._run(tmp_path, monkeypatch, ["--reopen-unapplied"])
        out = capsys.readouterr().out
        assert "再ベース 1 件 / 再オープン 1 件 / 未解決 1 件" in out and "dry-run" not in out
        saved = {d["id"]: d for d in findings_io.load_findings(p)}
        assert saved["stale"]["entry"] == "あきお,akio,明男"
        assert saved["unapplied"]["status"] == "approved"
        assert "再オープン: 未適用を検出" in saved["unapplied"]["evidence"]
        assert saved["lost"]["entry"] == "きえた,kieta,消"
        assert not [x for x in os.listdir(str(tmp_path)) if x.endswith(".tmp")]

    def test_without_reopen_flag_leaves_applied(self, tmp_path, monkeypatch, capsys):
        p = self._run(tmp_path, monkeypatch, [])
        out = capsys.readouterr().out
        assert "再ベース 1 件 / 再オープン 0 件 / 未解決 1 件" in out
        assert findings_io.load_findings(p)[1]["status"] == "applied"
