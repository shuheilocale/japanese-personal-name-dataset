"""apply_findings.py（承認済み修正の一括適用）のテスト。"""
import os

import apply_findings
import findings_io


def _write_dataset(tmp_path):
    d = tmp_path / "dataset"
    d.mkdir()
    (d / "first_name_man_org.csv").write_text(
        "ああす,asu,亜明日\nあい,ai,藍,愛\nかおる,kaoru,薫\n", encoding="utf-8")
    (d / "first_name_woman_org.csv").write_text("さくら,sakura,桜\n", encoding="utf-8")
    return str(d)


def _finding(file, entry, action, value, status="approved", check="not_a_name"):
    return {
        "id": "%s:%s" % (file, entry.split(",")[0]), "file": file, "entry": entry,
        "check": check, "severity": "error", "confidence": "high",
        "evidence": "テスト用", "proposed_fix": {"action": action, "value": value},
        "status": status, "detected_at": "2026-07-27", "detected_by": "qa-review v1",
    }


class TestApply:
    def test_remove_row_and_remove_kanji(self, tmp_path):
        ds = _write_dataset(tmp_path)
        fp = str(tmp_path / "f.jsonl")
        findings_io.append_findings(fp, [
            _finding("first_name_man_org.csv", "ああす,asu,亜明日", "remove_row", ""),
            _finding("first_name_man_org.csv", "あい,ai,藍,愛", "remove_kanji", "愛",
                     check="kanji_reading_mismatch"),
        ])
        result = apply_findings.apply(fp, ds, str(tmp_path / "qa"))
        assert result["applied"] == 2
        content = open(os.path.join(ds, "first_name_man_org.csv"),
                       encoding="utf-8").read()
        assert "ああす" not in content
        assert "あい,ai,藍\n" in content
        # 適用済み finding は applied になる
        statuses = [d["status"] for d in findings_io.load_findings(fp)]
        assert statuses == ["applied", "applied"]

    def test_fix_romaji_and_reading(self, tmp_path):
        ds = _write_dataset(tmp_path)
        fp = str(tmp_path / "f.jsonl")
        findings_io.append_findings(fp, [
            _finding("first_name_man_org.csv", "かおる,kaoru,薫", "fix_romaji", "kaworu",
                     check="romaji_reading_mismatch"),
        ])
        apply_findings.apply(fp, ds, str(tmp_path / "qa"))
        content = open(os.path.join(ds, "first_name_man_org.csv"),
                       encoding="utf-8").read()
        assert "かおる,kaworu,薫\n" in content

    def test_move_to_file_keeps_sort_order(self, tmp_path):
        ds = _write_dataset(tmp_path)
        fp = str(tmp_path / "f.jsonl")
        findings_io.append_findings(fp, [
            _finding("first_name_man_org.csv", "かおる,kaoru,薫", "move_to_file",
                     "first_name_woman_org.csv", check="wrong_gender_file"),
        ])
        apply_findings.apply(fp, ds, str(tmp_path / "qa"))
        man = open(os.path.join(ds, "first_name_man_org.csv"), encoding="utf-8").read()
        woman = open(os.path.join(ds, "first_name_woman_org.csv"), encoding="utf-8").read()
        assert "かおる" not in man
        # 読みの昇順で挿入される（かおる < さくら）
        assert woman == "かおる,kaoru,薫\nさくら,sakura,桜\n"

    def test_pending_not_applied_and_rejected_goes_to_verified(self, tmp_path):
        ds = _write_dataset(tmp_path)
        fp = str(tmp_path / "f.jsonl")
        findings_io.append_findings(fp, [
            _finding("first_name_man_org.csv", "ああす,asu,亜明日", "remove_row", "",
                     status="pending"),
            _finding("first_name_man_org.csv", "あい,ai,藍,愛", "remove_kanji", "愛",
                     status="rejected"),
        ])
        result = apply_findings.apply(fp, ds, str(tmp_path / "qa"))
        assert result["applied"] == 0
        assert result["rejected_verified"] == 1
        content = open(os.path.join(ds, "first_name_man_org.csv"),
                       encoding="utf-8").read()
        assert "ああす" in content and "愛" in content
        verified = findings_io.load_verified(
            str(tmp_path / "qa" / "verified.json"))
        h = findings_io.entry_hash("first_name_man_org.csv", "あい,ai,藍,愛")
        assert h in verified

    def test_entry_not_found_is_skipped(self, tmp_path):
        ds = _write_dataset(tmp_path)
        fp = str(tmp_path / "f.jsonl")
        findings_io.append_findings(fp, [
            _finding("first_name_man_org.csv", "存在しない,nai,無", "remove_row", ""),
        ])
        result = apply_findings.apply(fp, ds, str(tmp_path / "qa"))
        assert result["applied"] == 0
        assert len(result["skipped"]) == 1
        # 見つからなかった finding は approved のまま残る
        assert findings_io.load_findings(fp)[0]["status"] == "approved"

    def test_dry_run_writes_nothing(self, tmp_path):
        ds = _write_dataset(tmp_path)
        fp = str(tmp_path / "f.jsonl")
        findings_io.append_findings(fp, [
            _finding("first_name_man_org.csv", "ああす,asu,亜明日", "remove_row", ""),
        ])
        before = open(os.path.join(ds, "first_name_man_org.csv"),
                      encoding="utf-8").read()
        apply_findings.apply(fp, ds, str(tmp_path / "qa"), dry_run=True)
        after = open(os.path.join(ds, "first_name_man_org.csv"),
                     encoding="utf-8").read()
        assert before == after
        assert findings_io.load_findings(fp)[0]["status"] == "approved"

    def test_prints_planned_application_breakdown(self, tmp_path, capsys):
        # dry-run・通常適用のどちらでも、適用予定の内訳（id/action/value/file）
        # を1件ずつ日本語で印字する。
        ds = _write_dataset(tmp_path)
        fp = str(tmp_path / "f.jsonl")
        f = _finding("first_name_man_org.csv", "かおる,kaoru,薫", "fix_romaji",
                     "kaworu", check="romaji_reading_mismatch")
        findings_io.append_findings(fp, [f])
        apply_findings.apply(fp, ds, str(tmp_path / "qa"), dry_run=True)
        out = capsys.readouterr().out
        assert "適用予定" in out
        assert f["id"] in out
        assert "fix_romaji" in out
        assert "kaworu" in out
        assert "first_name_man_org.csv" in out

    def test_prints_planned_application_breakdown_on_real_apply(self, tmp_path, capsys):
        ds = _write_dataset(tmp_path)
        fp = str(tmp_path / "f.jsonl")
        f = _finding("first_name_man_org.csv", "ああす,asu,亜明日", "remove_row", "")
        findings_io.append_findings(fp, [f])
        apply_findings.apply(fp, ds, str(tmp_path / "qa"))
        out = capsys.readouterr().out
        assert "適用予定" in out
        assert f["id"] in out
        assert "remove_row" in out

    def test_two_remove_kanji_on_same_row_both_applied(self, tmp_path):
        # 同一行の漢字リストから2件の remove_kanji が承認された場合、
        # 1件目適用後の行を土台に2件目も適用され、両漢字とも消える。
        ds = _write_dataset(tmp_path)
        fp = str(tmp_path / "f.jsonl")
        findings_io.append_findings(fp, [
            _finding("first_name_man_org.csv", "あい,ai,藍,愛", "remove_kanji", "藍",
                     check="kanji_reading_mismatch"),
            _finding("first_name_man_org.csv", "あい,ai,藍,愛", "remove_kanji", "愛",
                     check="kanji_reading_mismatch"),
        ])
        result = apply_findings.apply(fp, ds, str(tmp_path / "qa"))
        assert result["applied"] == 2
        assert result["skipped"] == []
        content = open(os.path.join(ds, "first_name_man_org.csv"),
                       encoding="utf-8").read()
        assert "藍" not in content
        assert "愛" not in content
        assert "あい,ai\n" in content
        statuses = [d["status"] for d in findings_io.load_findings(fp)]
        assert statuses == ["applied", "applied"]

    def test_remove_kanji_then_fix_romaji_on_same_row_both_applied(self, tmp_path):
        # 同一行に対する remove_kanji と fix_romaji の組み合わせも、
        # 進化した行を追跡して両方適用される。
        ds = _write_dataset(tmp_path)
        fp = str(tmp_path / "f.jsonl")
        findings_io.append_findings(fp, [
            _finding("first_name_man_org.csv", "あい,ai,藍,愛", "remove_kanji", "愛",
                     check="kanji_reading_mismatch"),
            _finding("first_name_man_org.csv", "あい,ai,藍,愛", "fix_romaji", "ai2",
                     check="romaji_reading_mismatch"),
        ])
        result = apply_findings.apply(fp, ds, str(tmp_path / "qa"))
        assert result["applied"] == 2
        content = open(os.path.join(ds, "first_name_man_org.csv"),
                       encoding="utf-8").read()
        assert "愛" not in content
        assert "あい,ai2,藍\n" in content
        statuses = [d["status"] for d in findings_io.load_findings(fp)]
        assert statuses == ["applied", "applied"]

    def test_remove_row_then_other_finding_on_same_row_is_skipped(self, tmp_path):
        # remove_row が先に適用されて行が消えた後、同じ元の行を対象とする
        # 別の finding は「行が見つかりません」でスキップされ approved のまま残る。
        ds = _write_dataset(tmp_path)
        fp = str(tmp_path / "f.jsonl")
        findings_io.append_findings(fp, [
            _finding("first_name_man_org.csv", "あい,ai,藍,愛", "remove_row", "",
                     check="not_a_name"),
            _finding("first_name_man_org.csv", "あい,ai,藍,愛", "remove_kanji", "愛",
                     check="kanji_reading_mismatch"),
        ])
        result = apply_findings.apply(fp, ds, str(tmp_path / "qa"))
        assert result["applied"] == 1
        assert len(result["skipped"]) == 1
        content = open(os.path.join(ds, "first_name_man_org.csv"),
                       encoding="utf-8").read()
        assert "あい" not in content
        statuses = [d["status"] for d in findings_io.load_findings(fp)]
        assert statuses == ["applied", "approved"]

    def test_from_report_promotes_checked(self, tmp_path):
        ds = _write_dataset(tmp_path)
        fp = str(tmp_path / "f.jsonl")
        f = _finding("first_name_man_org.csv", "ああす,asu,亜明日", "remove_row", "",
                     status="pending")
        findings_io.append_findings(fp, [f])
        report = tmp_path / "r.md"
        report.write_text("- [x] `%s` **not_a_name** ..." % f["id"], encoding="utf-8")
        result = apply_findings.apply(fp, ds, str(tmp_path / "qa"),
                                      report_path=str(report))
        assert result["applied"] == 1
