"""checks.py（決定的チェック関数）のテスト。"""
import checks


def _findings_by_check(findings, check):
    return [f for f in findings if f.check == check]


class TestFirstNameChecks:
    def test_clean_rows_no_findings(self):
        rows = [["あい", "ai", "藍"], ["かおる", "kaoru", "薫", "香"]]
        assert checks.check_first_name_rows("f.csv", rows) == []

    def test_bad_charset(self):
        rows = [["アイ", "ai", "藍"], ["あい", "AI!", "藍"]]
        fs = checks.check_first_name_rows("f.csv", rows)
        assert len(_findings_by_check(fs, "format_error")) == 2
        assert all(f.severity == "error" for f in fs)
        assert fs[0].file == "f.csv" and fs[0].line == 1

    def test_too_few_columns(self):
        fs = checks.check_first_name_rows("f.csv", [["あい"]])
        assert _findings_by_check(fs, "format_error")

    def test_kanji_contamination_and_blank(self):
        rows = [["あい", "ai", "藍1"], ["かい", "kai", " 快"]]
        fs = checks.check_first_name_rows("f.csv", rows)
        assert len(_findings_by_check(fs, "format_error")) == 2

    def test_duplicates(self):
        rows = [["あい", "ai", "藍", "藍"], ["あい", "ai", "愛"]]
        fs = checks.check_first_name_rows("f.csv", rows)
        dup = _findings_by_check(fs, "duplicate")
        # 行内漢字重複 + 読み重複
        assert len(dup) == 2
        assert all(f.severity == "warning" for f in dup)

    def test_empty_row_and_no_kanji_are_warnings(self):
        fs = checks.check_first_name_rows("f.csv", [[], ["あい", "ai"]])
        assert all(f.severity == "warning" for f in fs)
        assert len(fs) == 2


class TestLastNameChecks:
    def test_clean(self):
        rows = [["佐藤", "1887000", "さとう", "satou"]]
        assert checks.check_last_name_rows("l.csv", rows) == []

    def test_wrong_columns_and_population(self):
        fs = checks.check_last_name_rows(
            "l.csv", [["佐藤", "さとう", "satou"], ["鈴木", "多い", "すずき", "suzuki"]]
        )
        assert len(_findings_by_check(fs, "format_error")) == 2

    def test_duplicate_surname(self):
        rows = [["佐藤", "1", "さとう", "satou"], ["佐藤", "2", "さとう", "satou"]]
        fs = checks.check_last_name_rows("l.csv", rows)
        assert _findings_by_check(fs, "duplicate")


class TestLoadRows:
    def test_load(self, tmp_path):
        p = tmp_path / "x.csv"
        p.write_text("あい,ai,藍\n\nかい,kai,快\n", encoding="utf-8")
        rows = checks.load_rows(str(p))
        assert rows == [["あい", "ai", "藍"], [], ["かい", "kai", "快"]]


class TestValidateScriptOutput:
    def test_file_missing_error_format(self, tmp_path):
        """validate.py のファイル欠落エラーが line == 0 の Finding として
        'ERROR   filename: message' 形式で出力されることを検証（`:0` を含まない）。
        """
        import subprocess
        # 空のディレクトリで validate.py を実行
        result = subprocess.run(
            ["python3", "./.claude/skills/validate-dataset/scripts/validate.py", str(tmp_path)],
            capture_output=True,
            text=True,
            cwd="/Users/shuhei/99_private/japanese-personal-name-dataset/.claude/worktrees/qa-foundation"
        )
        # ファイル欠落エラーが出力される
        assert "ファイルが存在しません" in result.stderr or "ファイルが存在しません" in result.stdout
        # 出力に :0 が含まれていないことを確認（行番号なし形式であることを検証）
        output = result.stderr + result.stdout
        # "first_name_man_org.csv:" で始まり、その直後が `:0:` ではなく `: ` であることを確認
        import re
        lines_with_error = [l for l in output.split('\n') if 'first_name_man_org.csv:' in l]
        assert lines_with_error, "ファイル欠落エラーが見つかりません"
        # `:0:` を含まないことを確認
        for line in lines_with_error:
            assert ":0:" not in line, f"エラー形式が不正（:0: を含む）: {line}"
