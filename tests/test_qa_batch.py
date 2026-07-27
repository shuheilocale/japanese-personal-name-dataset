"""qa_batch.py（LLM レビューのバッチ準備・結果マージ）のテスト。"""
import json
import os
import subprocess
import sys

import pytest

import findings_io
import qa_batch


def _write_dataset(tmp_path):
    d = tmp_path / "dataset"
    d.mkdir()
    (d / "first_name_man_org.csv").write_text(
        "あい,ai,藍\nかおる,kaoru,薫\n", encoding="utf-8")
    (d / "first_name_man_opti.csv").write_text("あい,ai,藍\n", encoding="utf-8")
    (d / "first_name_woman_org.csv").write_text("さくら,sakura,桜\n", encoding="utf-8")
    (d / "first_name_woman_opti.csv").write_text("さくら,sakura,桜\n", encoding="utf-8")
    (d / "last_name_org.csv").write_text("佐藤,1887000,さとう,satou\n", encoding="utf-8")
    return str(d)


def _finding_for(file, raw, reading):
    return {
        "id": "%s:%s" % (file, reading), "file": file, "entry": raw,
        "check": "not_a_name", "severity": "error", "confidence": "high",
        "evidence": "テスト用", "proposed_fix": {"action": "remove_row", "value": ""},
        "status": "pending", "detected_at": "2026-07-27", "detected_by": "qa-review v1",
    }


class TestPrep:
    def test_prep_writes_batches_and_manifest(self, tmp_path):
        ds = _write_dataset(tmp_path)
        work = str(tmp_path / "work")
        qa_batch.prep(ds, str(tmp_path / "qa"), work, batch_size=2)
        manifest = json.load(open(os.path.join(work, "manifest.json"), encoding="utf-8"))
        # 全6エントリ（4ファイル5行 + 姓1行）が2件ずつのバッチに分かれる
        assert manifest["total_entries"] == 6
        assert len(manifest["batch_ids"]) == 3
        assert manifest["style_stats"]["first_name_man_org.csv"]["neutral"] == 2
        b1 = json.load(open(os.path.join(work, "batch_001.json"), encoding="utf-8"))
        e = b1["entries"][0]
        assert set(e) >= {"file", "line", "raw", "reading", "romaji", "kanji", "hash"}

    def test_prep_skips_verified(self, tmp_path):
        ds = _write_dataset(tmp_path)
        qa_dir = str(tmp_path / "qa")
        h = findings_io.entry_hash("first_name_man_org.csv", "あい,ai,藍")
        findings_io.save_verified(os.path.join(qa_dir, "verified.json"),
                                  {h: {"file": "first_name_man_org.csv",
                                       "reading": "あい", "verified_at": "2026-07-27"}})
        work = str(tmp_path / "work")
        qa_batch.prep(ds, qa_dir, work, batch_size=100)
        manifest = json.load(open(os.path.join(work, "manifest.json"), encoding="utf-8"))
        assert manifest["total_entries"] == 5
        assert manifest["skipped_verified"] == 1

    def test_prep_missing_dataset_file_raises(self, tmp_path):
        # dataset ディレクトリ自体が存在しない（＝必須 CSV が欠落）場合は
        # 明示的な日本語エラーを送出し、トレースバックを見せてはならない
        # （main() 側で捕捉して exit 1 にする。CLI レベルの検証は別テストで行う）。
        missing_ds = str(tmp_path / "no_such_dataset_dir")
        with pytest.raises(FileNotFoundError) as exc_info:
            qa_batch.prep(missing_ds, str(tmp_path / "qa"), str(tmp_path / "work"))
        assert "見つかりません" in str(exc_info.value)


class TestPrepCli:
    def test_missing_dataset_exits_1_without_traceback(self, tmp_path):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
        script = os.path.join(
            repo_root, ".claude", "skills", "qa-review", "scripts", "qa_batch.py")
        result = subprocess.run(
            [sys.executable, script, "prep",
             "--dataset-dir", str(tmp_path / "no_such_dataset_dir"),
             "--qa-dir", str(tmp_path / "qa"),
             "--out-dir", str(tmp_path / "work")],
            capture_output=True, text=True, cwd=repo_root,
        )
        assert result.returncode == 1
        assert "Traceback" not in result.stderr
        assert "見つかりません" in result.stderr


class TestMerge:
    def _prep(self, tmp_path):
        ds = _write_dataset(tmp_path)
        qa_dir = str(tmp_path / "qa")
        work = str(tmp_path / "work")
        qa_batch.prep(ds, qa_dir, work, batch_size=100)
        return ds, qa_dir, work

    def test_merge_appends_findings_and_verifies_ok(self, tmp_path):
        ds, qa_dir, work = self._prep(tmp_path)
        batch = json.load(open(os.path.join(work, "batch_001.json"), encoding="utf-8"))
        target = batch["entries"][0]
        ok_hashes = [e["hash"] for e in batch["entries"][1:]]
        os.makedirs(os.path.join(work, "results"))
        with open(os.path.join(work, "results", "batch_001.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"batch_id": "batch_001",
                       "findings": [_finding_for(target["file"], target["raw"],
                                                 target["reading"])],
                       "ok_hashes": ok_hashes}, f, ensure_ascii=False)
        summary = qa_batch.merge(qa_dir, work, "test-run")
        fs = findings_io.load_findings(
            os.path.join(qa_dir, "findings", "test-run.jsonl"))
        assert len(fs) == 1
        verified = findings_io.load_verified(os.path.join(qa_dir, "verified.json"))
        assert len(verified) == len(ok_hashes)
        assert target["hash"] not in verified  # 疑義ありは verified に入らない
        assert summary["missing_batches"] == []
        assert summary["invalid_batches"] == []
        assert summary["incomplete_batches"] == []  # 全エントリが判定済み
        assert summary["verified_added"] == len(ok_hashes)
        report = open(os.path.join(qa_dir, "reports", "test-run.md"),
                      encoding="utf-8").read()
        assert "test-run" in report and target["reading"] in report

    def test_merge_reports_missing_batches(self, tmp_path):
        ds, qa_dir, work = self._prep(tmp_path)
        os.makedirs(os.path.join(work, "results"))  # 結果ファイルなし
        summary = qa_batch.merge(qa_dir, work, "test-run2")
        assert summary["missing_batches"] == ["batch_001"]
        report = open(os.path.join(qa_dir, "reports", "test-run2.md"),
                      encoding="utf-8").read()
        assert "batch_001" in report

    def test_merge_rejects_invalid_finding(self, tmp_path):
        ds, qa_dir, work = self._prep(tmp_path)
        os.makedirs(os.path.join(work, "results"))
        with open(os.path.join(work, "results", "batch_001.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"batch_id": "batch_001",
                       "findings": [{"id": "broken"}], "ok_hashes": []}, f)
        summary = qa_batch.merge(qa_dir, work, "test-run3")
        # 不正な結果ファイルは取り込まず、未処理扱いにする
        assert summary["invalid_batches"] == ["batch_001"]
        assert not os.path.exists(os.path.join(qa_dir, "findings", "test-run3.jsonl"))

    def test_merge_reports_incomplete_batch_coverage(self, tmp_path):
        # findings にも ok_hashes にも入っていないエントリが残っている場合、
        # そのバッチは incomplete として扱われ、結果を取り込まない。
        ds, qa_dir, work = self._prep(tmp_path)
        batch = json.load(open(os.path.join(work, "batch_001.json"), encoding="utf-8"))
        entries = batch["entries"]
        assert len(entries) == 6
        target = entries[0]
        # entries[0] は finding、entries[1:4] は ok、entries[4:] は判定漏れ
        ok_hashes = [e["hash"] for e in entries[1:4]]
        os.makedirs(os.path.join(work, "results"))
        with open(os.path.join(work, "results", "batch_001.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"batch_id": "batch_001",
                       "findings": [_finding_for(target["file"], target["raw"],
                                                 target["reading"])],
                       "ok_hashes": ok_hashes}, f, ensure_ascii=False)
        summary = qa_batch.merge(qa_dir, work, "test-run-incomplete")
        assert summary["missing_batches"] == []
        assert summary["invalid_batches"] == []
        assert summary["incomplete_batches"] == [
            {"batch_id": "batch_001", "missing": 2}]
        # incomplete バッチの findings/ok_hashes は取り込まれない
        assert summary["findings"] == 0
        assert not os.path.exists(
            os.path.join(qa_dir, "findings", "test-run-incomplete.jsonl"))
        verified = findings_io.load_verified(os.path.join(qa_dir, "verified.json"))
        assert verified == {}
        report = open(os.path.join(qa_dir, "reports", "test-run-incomplete.md"),
                      encoding="utf-8").read()
        assert "batch_001" in report and "未判定エントリ 2 件" in report

    def test_merge_duplicate_id_marks_batch_invalid(self, tmp_path):
        ds, qa_dir, work = self._prep(tmp_path)
        batch = json.load(open(os.path.join(work, "batch_001.json"), encoding="utf-8"))
        entries = batch["entries"]
        f1 = _finding_for(entries[0]["file"], entries[0]["raw"], entries[0]["reading"])
        f2 = _finding_for(entries[1]["file"], entries[1]["raw"], entries[1]["reading"])
        f2["id"] = f1["id"]  # 意図的に id を衝突させる
        ok_hashes = [e["hash"] for e in entries[2:]]
        os.makedirs(os.path.join(work, "results"))
        with open(os.path.join(work, "results", "batch_001.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"batch_id": "batch_001", "findings": [f1, f2],
                       "ok_hashes": ok_hashes}, f, ensure_ascii=False)
        summary = qa_batch.merge(qa_dir, work, "test-run-dupid")
        assert summary["invalid_batches"] == ["batch_001"]
        assert summary["findings"] == 0
        assert not os.path.exists(
            os.path.join(qa_dir, "findings", "test-run-dupid.jsonl"))

    def test_merge_verified_added_excludes_flagged_and_fabricated(self, tmp_path):
        # verified_added は実際に verified.json に新規登録された件数のみを
        # 数える（flagged（findings 対象）や存在しない捏造 hash は数えない）。
        ds, qa_dir, work = self._prep(tmp_path)
        batch = json.load(open(os.path.join(work, "batch_001.json"), encoding="utf-8"))
        entries = batch["entries"]
        target = entries[0]
        real_ok = entries[1:]  # 5件
        ok_hashes = ([e["hash"] for e in real_ok]
                    + [target["hash"], "0" * 16])  # flagged 重複 + 捏造 hash
        os.makedirs(os.path.join(work, "results"))
        with open(os.path.join(work, "results", "batch_001.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"batch_id": "batch_001",
                       "findings": [_finding_for(target["file"], target["raw"],
                                                 target["reading"])],
                       "ok_hashes": ok_hashes}, f, ensure_ascii=False)
        summary = qa_batch.merge(qa_dir, work, "test-run-vadd")
        assert summary["incomplete_batches"] == []
        assert summary["verified_added"] == len(real_ok)
        verified = findings_io.load_verified(os.path.join(qa_dir, "verified.json"))
        assert len(verified) == len(real_ok)


class TestMergeRerun:
    def _prep_with_result(self, tmp_path):
        ds = _write_dataset(tmp_path)
        qa_dir = str(tmp_path / "qa")
        work = str(tmp_path / "work")
        qa_batch.prep(ds, qa_dir, work, batch_size=100)
        batch = json.load(open(os.path.join(work, "batch_001.json"), encoding="utf-8"))
        target = batch["entries"][0]
        ok_hashes = [e["hash"] for e in batch["entries"][1:]]
        os.makedirs(os.path.join(work, "results"))
        with open(os.path.join(work, "results", "batch_001.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"batch_id": "batch_001",
                       "findings": [_finding_for(target["file"], target["raw"],
                                                 target["reading"])],
                       "ok_hashes": ok_hashes}, f, ensure_ascii=False)
        return qa_dir, work

    def test_remerge_does_not_duplicate_findings(self, tmp_path):
        qa_dir, work = self._prep_with_result(tmp_path)
        summary1 = qa_batch.merge(qa_dir, work, "test-run-remerge")
        findings_path = os.path.join(qa_dir, "findings", "test-run-remerge.jsonl")
        fs1 = findings_io.load_findings(findings_path)
        # 手順6を模して同じ結果でもう一度マージ（欠落バッチ補完のシナリオ）
        summary2 = qa_batch.merge(qa_dir, work, "test-run-remerge")
        fs2 = findings_io.load_findings(findings_path)
        assert len(fs1) == 1
        assert len(fs2) == 1  # 重複していない
        assert summary1["findings"] == summary2["findings"] == 1
        assert [d["id"] for d in fs1] == [d["id"] for d in fs2]
        verified = findings_io.load_verified(os.path.join(qa_dir, "verified.json"))
        assert summary1["verified_added"] == summary2["verified_added"]
        assert len(verified) == summary2["verified_added"]

    def test_remerge_preserves_human_edited_status(self, tmp_path):
        qa_dir, work = self._prep_with_result(tmp_path)
        qa_batch.merge(qa_dir, work, "test-run-status")
        findings_path = os.path.join(qa_dir, "findings", "test-run-status.jsonl")
        fs = findings_io.load_findings(findings_path)
        assert fs[0]["status"] == "pending"
        fs[0]["status"] = "approved"  # 人間がレポート経由で承認したことを模す
        findings_io.save_findings(findings_path, fs)
        # 同じ結果ファイルのまま再マージしても、承認済みの status は保持される
        qa_batch.merge(qa_dir, work, "test-run-status")
        fs_after = findings_io.load_findings(findings_path)
        assert len(fs_after) == 1
        assert fs_after[0]["status"] == "approved"
