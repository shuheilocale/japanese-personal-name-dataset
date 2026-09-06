"""gender_batch.py のテスト。"""
import json
import os
import subprocess
import sys

import findings_io
import gender_batch as gb
import generate_candidates as gc


def _pending(tmp_path):
    p = str(tmp_path / "gender_pending.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump([{"reading": "りん", "kanji": ["凛", "鈴"], "sources": {"ndl": 6, "wikidata": 0, "jmnedict": False}},
                   {"reading": "ひなた", "kanji": ["陽向"], "sources": {"ndl": 3, "wikidata": 0, "jmnedict": True}}], f, ensure_ascii=False)
    return p


def test_prep_and_merge(tmp_path):
    p = _pending(tmp_path)
    out = str(tmp_path / "work")
    m = gb.prep(p, out, batch_size=1)
    assert m["batch_ids"] == ["gbatch_001", "gbatch_002"]
    os.makedirs(os.path.join(out, "results"))
    with open(os.path.join(out, "results", "gbatch_001.json"), "w", encoding="utf-8") as f:
        json.dump({"batch_id": "gbatch_001", "decisions": {"りん": "female"}}, f, ensure_ascii=False)
    fp = str(tmp_path / "f.jsonl")
    findings_io.save_findings(fp, [])
    summary = gb.merge(out, fp, today="2026-09-06")
    fs = findings_io.load_findings(fp)
    assert len(fs) == 1 and fs[0]["file"] == "first_name_woman_org.csv"
    assert fs[0]["entry"] == "りん,rin,凛,鈴" and fs[0]["status"] == "pending"
    assert "LLM" in fs[0]["evidence"] and fs[0]["sources"]["ndl"] == 6
    assert summary["missing_batches"] == ["gbatch_002"]
    # generate_candidates の再実行で保持されるよう、detected_by で出自を区別する
    assert fs[0]["detected_by"] == gb.DETECTED_BY == "qa-update/gender_batch v1"
    assert gb.DETECTED_BY != gc.DETECTED_BY
    assert findings_io.validate_finding(fs[0]) == []


def test_unisex_and_unknown(tmp_path):
    p = _pending(tmp_path)
    out = str(tmp_path / "work")
    gb.prep(p, out, batch_size=10)
    os.makedirs(os.path.join(out, "results"))
    with open(os.path.join(out, "results", "gbatch_001.json"), "w", encoding="utf-8") as f:
        json.dump({"batch_id": "gbatch_001", "decisions": {"りん": "unisex", "ひなた": "unknown"}}, f, ensure_ascii=False)
    fp = str(tmp_path / "f.jsonl")
    findings_io.save_findings(fp, [])
    gb.merge(out, fp, today="2026-09-06")
    fs = findings_io.load_findings(fp)
    assert sorted(f["file"] for f in fs) == ["first_name_man_org.csv", "first_name_woman_org.csv"]
    assert not [f for f in fs if f["entry"].startswith("ひなた")]


def test_cli_standalone_help():
    """conftest の sys.path 注入に頼らず、単体スクリプト実行として --help が動くことを確認する。

    gender_batch.py は findings_io（validate-dataset/scripts）に依存するため、
    自身で当該ディレクトリを sys.path に追加していないと `python3 gender_batch.py ...`
    が ModuleNotFoundError で落ちる。subprocess で新しい Python プロセスから実行し、
    pytest 経由の import では検出できない回帰を捕捉する。
    """
    script = os.path.abspath(gb.__file__)
    for argv in (["--help"], ["prep", "--help"], ["merge", "--help"]):
        result = subprocess.run([sys.executable, script] + argv,
                                capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
