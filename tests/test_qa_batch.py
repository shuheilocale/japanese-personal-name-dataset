"""qa_batch.py（LLM レビューのバッチ準備・結果マージ）のテスト。"""
import json
import os

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
