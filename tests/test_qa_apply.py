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
    (d / "last_name_org.csv").write_text(
        "佐藤,1887000,さとう,satou\n", encoding="utf-8")
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

    def test_remove_kanji_with_multiple_values_removes_all(self, tmp_path):
        # value が "克真, 克麻, 勝真" のように複数漢字を含む場合（`、` 区切りも可）、
        # 分割して全漢字を除去する。空白は無視し、行に無い漢字は無視される。
        ds = _write_dataset(tmp_path)
        (tmp_path / "dataset" / "first_name_man_org.csv").write_text(
            "かづま,kazuma,一真,克真,克麻,勝真,和真\n", encoding="utf-8")
        fp = str(tmp_path / "f.jsonl")
        findings_io.append_findings(fp, [
            _finding("first_name_man_org.csv", "かづま,kazuma,一真,克真,克麻,勝真,和真",
                     "remove_kanji", "克真, 克麻、勝真, 無い", check="kanji_reading_mismatch"),
        ])
        result = apply_findings.apply(fp, ds, str(tmp_path / "qa"))
        assert result["applied"] == 1
        content = open(os.path.join(ds, "first_name_man_org.csv"),
                       encoding="utf-8").read()
        assert content == "かづま,kazuma,一真,和真\n"

    def test_split_values_rules(self):
        assert apply_findings._split_values("克真, 克麻, 勝真") == ["克真", "克麻", "勝真"]
        assert apply_findings._split_values("克真、克麻") == ["克真", "克麻"]
        assert apply_findings._split_values(" 愛 ,, ") == ["愛"]
        assert apply_findings._split_values("") == []

    def test_remove_kanji_then_fix_romaji_on_same_row_both_applied(self, tmp_path):
        # 同一行に対する remove_kanji と fix_romaji の組み合わせも、
        # 進化した行を追跡して両方適用される。
        ds = _write_dataset(tmp_path)
        fp = str(tmp_path / "f.jsonl")
        findings_io.append_findings(fp, [
            _finding("first_name_man_org.csv", "あい,ai,藍,愛", "remove_kanji", "愛",
                     check="kanji_reading_mismatch"),
            _finding("first_name_man_org.csv", "あい,ai,藍,愛", "fix_romaji", "aix",
                     check="romaji_reading_mismatch"),
        ])
        result = apply_findings.apply(fp, ds, str(tmp_path / "qa"))
        assert result["applied"] == 2
        content = open(os.path.join(ds, "first_name_man_org.csv"),
                       encoding="utf-8").read()
        assert "愛" not in content
        assert "あい,aix,藍\n" in content
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

    def test_fix_romaji_on_last_name_csv_keeps_population_column(self, tmp_path):
        # last_name_org.csv は 漢字,推定人数,ひらがな,ローマ字 の列順。
        # fix_romaji は col3（ローマ字）を書き換え、col1（推定人数）は不変であること。
        ds = _write_dataset(tmp_path)
        fp = str(tmp_path / "f.jsonl")
        findings_io.append_findings(fp, [
            _finding("last_name_org.csv", "佐藤,1887000,さとう,satou", "fix_romaji",
                     "sato", check="romaji_reading_mismatch"),
        ])
        result = apply_findings.apply(fp, ds, str(tmp_path / "qa"))
        assert result["applied"] == 1
        content = open(os.path.join(ds, "last_name_org.csv"),
                       encoding="utf-8").read()
        assert "佐藤,1887000,さとう,sato\n" in content

    def test_fix_reading_on_last_name_csv_changes_only_hiragana_column(self, tmp_path):
        # fix_reading は col2（ひらがな）を書き換え、漢字・推定人数・ローマ字は不変。
        ds = _write_dataset(tmp_path)
        fp = str(tmp_path / "f.jsonl")
        findings_io.append_findings(fp, [
            _finding("last_name_org.csv", "佐藤,1887000,さとう,satou", "fix_reading",
                     "さとお", check="romaji_reading_mismatch"),
        ])
        result = apply_findings.apply(fp, ds, str(tmp_path / "qa"))
        assert result["applied"] == 1
        content = open(os.path.join(ds, "last_name_org.csv"),
                       encoding="utf-8").read()
        assert "佐藤,1887000,さとお,satou\n" in content

    def test_remove_kanji_on_last_name_csv_is_skipped(self, tmp_path):
        # remove_kanji は名CSV固有の概念（複数の漢字表記からの除外）であり、
        # 姓CSVには適用できないため、承認済みでも適用せずスキップ扱いにする。
        ds = _write_dataset(tmp_path)
        fp = str(tmp_path / "f.jsonl")
        f = _finding("last_name_org.csv", "佐藤,1887000,さとう,satou", "remove_kanji",
                     "佐藤", check="kanji_reading_mismatch")
        findings_io.append_findings(fp, [f])
        result = apply_findings.apply(fp, ds, str(tmp_path / "qa"))
        assert result["applied"] == 0
        assert result["skipped"] == [f["id"]]
        content = open(os.path.join(ds, "last_name_org.csv"),
                       encoding="utf-8").read()
        assert content == "佐藤,1887000,さとう,satou\n"
        # スキップされた finding は approved のまま残る
        assert findings_io.load_findings(fp)[0]["status"] == "approved"

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

    def test_fix_reading_merges_into_existing_row(self, tmp_path):
        # 変更後の読みと同じ読みの行が既に存在する場合、漢字をマージして
        # 元の行は消える。ローマ字は既存行のものを維持する。
        ds = _write_dataset(tmp_path)
        fp = str(tmp_path / "f.jsonl")
        findings_io.append_findings(fp, [
            _finding("first_name_man_org.csv", "かおる,kaoru,薫", "fix_reading", "あい",
                     check="romaji_reading_mismatch"),
        ])
        result = apply_findings.apply(fp, ds, str(tmp_path / "qa"))
        assert result["applied"] == 1
        content = open(os.path.join(ds, "first_name_man_org.csv"),
                       encoding="utf-8").read()
        assert "あい,ai,藍,愛,薫\n" in content
        assert "かおる" not in content
        statuses = [d["status"] for d in findings_io.load_findings(fp)]
        assert statuses == ["applied"]

    def test_fix_reading_merge_dedupes_overlapping_kanji(self, tmp_path):
        # マージ先に既にある漢字は重複追加されない。
        ds = tmp_path / "dataset"
        ds.mkdir()
        (ds / "first_name_man_org.csv").write_text(
            "あい,ai,藍,愛\nめぐみ,megumi,愛\n", encoding="utf-8")
        (ds / "first_name_woman_org.csv").write_text("さくら,sakura,桜\n", encoding="utf-8")
        (ds / "last_name_org.csv").write_text("佐藤,1887000,さとう,satou\n", encoding="utf-8")
        fp = str(tmp_path / "f.jsonl")
        findings_io.append_findings(fp, [
            _finding("first_name_man_org.csv", "めぐみ,megumi,愛", "fix_reading", "あい"),
        ])
        result = apply_findings.apply(fp, str(ds), str(tmp_path / "qa"))
        assert result["applied"] == 1
        content = open(os.path.join(str(ds), "first_name_man_org.csv"),
                       encoding="utf-8").read()
        assert content == "あい,ai,藍,愛\n"

    def test_fix_reading_without_existing_row_behaves_as_before(self, tmp_path):
        # 変更後の読みと同じ読みの行が無い場合は、従来どおり読みを書き換えるだけ。
        ds = _write_dataset(tmp_path)
        fp = str(tmp_path / "f.jsonl")
        findings_io.append_findings(fp, [
            _finding("first_name_man_org.csv", "かおる,kaoru,薫", "fix_reading", "かをる"),
        ])
        result = apply_findings.apply(fp, ds, str(tmp_path / "qa"))
        assert result["applied"] == 1
        content = open(os.path.join(ds, "first_name_man_org.csv"),
                       encoding="utf-8").read()
        assert "かをる,kaoru,薫\n" in content
        assert "かおる" not in content

    def test_move_to_file_merges_into_existing_row(self, tmp_path):
        # 移動先に同じ読みの行が既にある場合、新規行を挿入せず既存行へ漢字をマージする。
        ds = tmp_path / "dataset"
        ds.mkdir()
        (ds / "first_name_man_org.csv").write_text("さくら,sakura,咲良\n", encoding="utf-8")
        (ds / "first_name_woman_org.csv").write_text("さくら,sakura,桜\n", encoding="utf-8")
        (ds / "last_name_org.csv").write_text("佐藤,1887000,さとう,satou\n", encoding="utf-8")
        fp = str(tmp_path / "f.jsonl")
        findings_io.append_findings(fp, [
            _finding("first_name_man_org.csv", "さくら,sakura,咲良", "move_to_file",
                     "first_name_woman_org.csv", check="wrong_gender_file"),
        ])
        result = apply_findings.apply(fp, str(ds), str(tmp_path / "qa"))
        assert result["applied"] == 1
        man = open(os.path.join(str(ds), "first_name_man_org.csv"), encoding="utf-8").read()
        woman = open(os.path.join(str(ds), "first_name_woman_org.csv"), encoding="utf-8").read()
        assert man == ""
        # 移動先に新規行が増えず、既存行に漢字がマージされる（ローマ字は既存を維持）
        assert woman == "さくら,sakura,桜,咲良\n"

    def test_fix_reading_merge_composite_evolution(self, tmp_path):
        # 2件の fix_reading が同じ既存行へ順にマージされ、さらにその既存行の
        # 元テキストを対象とする別findingも、完全マージ後の行に正しく適用される
        # （evolution マップの整合性）。
        ds = _write_dataset(tmp_path)
        (tmp_path / "dataset" / "first_name_man_org.csv").write_text(
            "あい,ai,藍\nかおる,kaoru,薫\nまみ,mami,真美\nみちる,michiru,美知留\n",
            encoding="utf-8")
        fp = str(tmp_path / "f.jsonl")
        findings_io.append_findings(fp, [
            _finding("first_name_man_org.csv", "まみ,mami,真美", "fix_reading", "あい"),
            _finding("first_name_man_org.csv", "みちる,michiru,美知留", "fix_reading", "あい"),
            _finding("first_name_man_org.csv", "あい,ai,藍", "fix_romaji", "aix"),
        ])
        result = apply_findings.apply(fp, ds, str(tmp_path / "qa"))
        assert result["applied"] == 3
        assert result["skipped"] == []
        content = open(os.path.join(ds, "first_name_man_org.csv"),
                       encoding="utf-8").read()
        assert "あい,aix,藍,真美,美知留\n" in content
        assert "まみ" not in content
        assert "みちる" not in content
        statuses = [d["status"] for d in findings_io.load_findings(fp)]
        assert statuses == ["applied", "applied", "applied"]

    def test_fix_reading_on_last_name_does_not_merge(self, tmp_path):
        # 姓CSVでは「同じ読みの別の姓」が正当なため、マージせず従来どおり単純書き換え。
        ds = tmp_path / "dataset"
        ds.mkdir()
        (ds / "first_name_man_org.csv").write_text("かおる,kaoru,薫\n", encoding="utf-8")
        (ds / "first_name_woman_org.csv").write_text("さくら,sakura,桜\n", encoding="utf-8")
        (ds / "last_name_org.csv").write_text(
            "佐藤,1887000,さとう,satou\n鈴木,1730000,すずき,suzuki\n", encoding="utf-8")
        fp = str(tmp_path / "f.jsonl")
        findings_io.append_findings(fp, [
            _finding("last_name_org.csv", "鈴木,1730000,すずき,suzuki", "fix_reading",
                     "さとう", check="romaji_reading_mismatch"),
        ])
        result = apply_findings.apply(fp, str(ds), str(tmp_path / "qa"))
        assert result["applied"] == 1
        content = open(os.path.join(str(ds), "last_name_org.csv"),
                       encoding="utf-8").read()
        assert content == "佐藤,1887000,さとう,satou\n鈴木,1730000,さとう,suzuki\n"

    def test_dry_run_shows_merge_note_for_fix_reading(self, tmp_path, capsys):
        ds = _write_dataset(tmp_path)
        fp = str(tmp_path / "f.jsonl")
        findings_io.append_findings(fp, [
            _finding("first_name_man_org.csv", "かおる,kaoru,薫", "fix_reading", "あい"),
        ])
        apply_findings.apply(fp, ds, str(tmp_path / "qa"), dry_run=True)
        out = capsys.readouterr().out
        assert "（既存行 あい に統合）" in out

    def test_dry_run_shows_merge_note_for_move_to_file(self, tmp_path, capsys):
        ds = tmp_path / "dataset"
        ds.mkdir()
        (ds / "first_name_man_org.csv").write_text("さくら,sakura,咲良\n", encoding="utf-8")
        (ds / "first_name_woman_org.csv").write_text("さくら,sakura,桜\n", encoding="utf-8")
        (ds / "last_name_org.csv").write_text("佐藤,1887000,さとう,satou\n", encoding="utf-8")
        fp = str(tmp_path / "f.jsonl")
        findings_io.append_findings(fp, [
            _finding("first_name_man_org.csv", "さくら,sakura,咲良", "move_to_file",
                     "first_name_woman_org.csv"),
        ])
        apply_findings.apply(fp, str(ds), str(tmp_path / "qa"), dry_run=True)
        out = capsys.readouterr().out
        assert "（既存行 さくら に統合）" in out


class TestAddActions:
    def _ds(self, tmp_path):
        d = tmp_path / "dataset"
        d.mkdir()
        (d / "first_name_man_org.csv").write_text("あい,ai,藍\nかおる,kaoru,薫\n", encoding="utf-8")
        (d / "first_name_woman_org.csv").write_text("さくら,sakura,桜\n", encoding="utf-8")
        return str(d)

    def _add(self, file, action, entry, value=""):
        return {"id": "%s:%s:%s" % (file, entry.split(",")[0], action), "file": file, "entry": entry,
                "check": "missing_entry", "severity": "warning", "confidence": "high",
                "evidence": "NDL 3人", "proposed_fix": {"action": action, "value": value},
                "status": "approved", "detected_at": "2026-09-06", "detected_by": "qa-update v1"}

    def test_add_kanji_appends_dedup(self, tmp_path):
        ds = self._ds(tmp_path)
        fp = str(tmp_path / "f.jsonl")
        findings_io.append_findings(fp, [self._add("first_name_man_org.csv", "add_kanji", "あい,ai,藍", "愛,藍")])
        apply_findings.apply(fp, ds, str(tmp_path / "qa"))
        assert "あい,ai,藍,愛\n" in open(os.path.join(ds, "first_name_man_org.csv"), encoding="utf-8").read()

    def test_add_row_inserts_sorted(self, tmp_path):
        ds = self._ds(tmp_path)
        fp = str(tmp_path / "f.jsonl")
        findings_io.append_findings(fp, [self._add("first_name_man_org.csv", "add_row", "いつき,itsuki,樹,一樹")])
        apply_findings.apply(fp, ds, str(tmp_path / "qa"))
        assert open(os.path.join(ds, "first_name_man_org.csv"), encoding="utf-8").read() == \
            "あい,ai,藍\nいつき,itsuki,樹,一樹\nかおる,kaoru,薫\n"

    def test_add_row_merges_when_reading_exists(self, tmp_path):
        ds = self._ds(tmp_path)
        fp = str(tmp_path / "f.jsonl")
        findings_io.append_findings(fp, [self._add("first_name_man_org.csv", "add_row", "あい,ai,愛,藍")])
        result = apply_findings.apply(fp, ds, str(tmp_path / "qa"))
        assert result["applied"] == 1
        assert open(os.path.join(ds, "first_name_man_org.csv"), encoding="utf-8").read() == \
            "あい,ai,藍,愛\nかおる,kaoru,薫\n"
