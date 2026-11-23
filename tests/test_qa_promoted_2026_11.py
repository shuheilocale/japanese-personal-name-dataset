"""2026-11 の運用から取り込んだスクリプトのテスト。

prior_decisions.py（以前の判断の引き継ぎ）・foreign_names.py（外国人名の音読みの検出）・
sync_full_popular.py（完全版と最適化版の判断の同期）・review_result.py（判定ファイル → 結果ファイル）。
"""
import json
import os
import subprocess
import sys

import findings_io
import foreign_names
import prior_decisions
import review_result
import sync_full_popular

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


def _f(file, entry, action, value="", status="pending", evidence="NDL 2人", fid=None, check="missing_entry", **kw):
    reading = entry.split(",")[0]
    d = {
        "id": fid or ("%s:%s:%s:%s" % (file, reading, check, action) + (":" + value if action == "add_kanji" else "")),
        "file": file, "entry": entry, "check": check, "severity": "warning", "confidence": "high",
        "evidence": evidence, "proposed_fix": {"action": action, "value": value}, "status": status,
        "detected_at": "2026-11-22", "detected_by": "qa-update v1",
    }
    d.update(kw)
    return d


MAN = "first_name_man_org.csv"


class TestPriorDecisions:
    def test_rejects_previously_rejected_id(self):
        prev = [_f(MAN, "あき,aki,秋", "add_kanji", "亜希", status="rejected")]
        new = [_f(MAN, "あき,aki,秋", "add_kanji", "亜希")]
        log = prior_decisions.apply_rules(new, prev)
        assert new[0]["status"] == "rejected"
        assert log == [(new[0]["id"], prior_decisions.REASON_PREV_REJECTED)]

    def test_rejects_spelling_narrowed_out_of_applied_row(self):
        prev = [_f(MAN, "げんさく,gensaku,源作", "add_row", status="applied",
                   evidence="NDL 3人（レビューで表記を絞り込み: 除外 玄作。号らしい）")]
        new = [_f(MAN, "げんさく,gensaku,源作", "add_kanji", "玄作"),
               _f(MAN, "げんさく,gensaku,源作", "add_kanji", "元作")]
        prior_decisions.apply_rules(new, prev)
        assert [d["status"] for d in new] == ["rejected", "pending"]

    def test_rejects_gender_conflict_and_keeps_others(self):
        new = [_f(MAN, "かおる,kaoru,薫", "add_kanji", "香織", evidence="NDL 5人（索引の性別 female と追加先が矛盾）"),
               _f(MAN, "かおる,kaoru,薫", "add_kanji", "馨", status="approved"),
               _f(MAN, "かおる,kaoru,薫", "add_kanji", "郁", status="applied", evidence="矛盾")]
        prior_decisions.apply_rules(new, [])
        assert [d["status"] for d in new] == ["rejected", "approved", "applied"]

    def test_idempotent(self):
        new = [_f(MAN, "かおる,kaoru,薫", "add_kanji", "香織", evidence="矛盾")]
        prior_decisions.apply_rules(new, [])
        ev = new[0]["evidence"]
        assert prior_decisions.apply_rules(new, []) == []
        assert new[0]["evidence"] == ev


def _ndl_work(tmp_path, people):
    work = tmp_path / "ndl-work"
    work.mkdir()
    lines = []
    for (s, sr), (g, gr) in people:
        lines.append(json.dumps({"source": "ndl", "kind": "surname", "kanji": s, "reading": sr, "gender": None, "count": 1}))
        lines.append(json.dumps({"source": "ndl", "kind": "given", "kanji": g, "reading": gr, "gender": None, "count": 1}))
    (work / "prefix-000001.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(work)


class TestForeignNames:
    def test_flags_only_when_japanese_bearers_fall_short(self, tmp_path):
        work = _ndl_work(tmp_path, [
            (("張", "ちょう"), ("憲文", "けんぶん")), (("佐藤", "さとう"), ("憲文", "けんぶん")),
            (("王", "おう"), ("健一", "けんいち")), (("佐藤", "さとう"), ("健一", "けんいち")),
            (("鈴木", "すずき"), ("健一", "けんいち")),
        ])
        bearers = foreign_names.load_bearers(work)
        findings = [_f(MAN, "けんぶん,kenbun,建文", "add_kanji", "憲文", status="approved"),
                    _f(MAN, "けんいち,kenichi,健市", "add_kanji", "健一", status="approved"),
                    _f(MAN, "けんぶん,kenbun,建文", "add_kanji", "憲文", status="pending", fid="other")]
        hits = foreign_names.check(findings, bearers, {}, set())
        assert [(h[0]["proposed_fix"]["value"], h[1]) for h in hits] == [("憲文", ["憲文"])]

    def test_wikidata_support_and_japanese_surname_reading_exempt(self, tmp_path):
        work = _ndl_work(tmp_path, [(("張", "ちょう"), ("永清", "えいせい")),
                                    (("林", "はやし"), ("正元", "せいげん"))])
        bearers = foreign_names.load_bearers(work)
        findings = [_f(MAN, "えいせい,eisei,英世", "add_kanji", "永清", status="approved"),
                    _f(MAN, "せいげん,seigen,清元", "add_kanji", "正元", status="approved")]
        pairs = {"given|永清|えいせい": {"wikidata": 1}}
        assert foreign_names.check(findings, bearers, pairs, set()) == []

    def test_apply_rejects_kanji_and_narrows_rows(self, tmp_path):
        work = _ndl_work(tmp_path, [(("陳", "ちん"), ("道平", "どうへい")), (("周", "しゅう"), ("一平", "いつへい"))])
        bearers = foreign_names.load_bearers(work)
        row_all = _f(MAN, "どうへい,douhei,道平", "add_row", status="approved")
        row_part = _f(MAN, "いつへい,itsuhei,一平,逸平", "add_row", status="approved")
        counts = foreign_names.apply(foreign_names.check([row_all, row_part], bearers, {}, set()))
        assert counts == {"rejected": 1, "narrowed": 1}
        assert row_all["status"] == "rejected"
        assert row_part["status"] == "approved" and row_part["entry"] == "いつへい,itsuhei,逸平"
        assert not findings_io.validate_finding(row_part)


def _dataset(tmp_path, man_org, man_opti):
    d = tmp_path / "dataset"
    d.mkdir()
    (d / "first_name_man_org.csv").write_text(man_org, encoding="utf-8")
    (d / "first_name_man_opti.csv").write_text(man_opti, encoding="utf-8")
    (d / "first_name_woman_org.csv").write_text("さくら,sakura,桜\n", encoding="utf-8")
    (d / "first_name_woman_opti.csv").write_text("さくら,sakura,桜\n", encoding="utf-8")
    return str(d)


def _rk(file, entry, value, status="approved", action="remove_kanji"):
    return _f(file, entry, action, value, status=status, check="kanji_reading_mismatch",
              fid="%s:%s:kanji_reading_mismatch" % (file, entry.split(",")[0]))


class TestSyncFullPopular:
    def test_union_both_directions(self, tmp_path):
        ds = _dataset(tmp_path, "たかお,takao,隆夫,祟夫,孝雄,高男\n", "たかお,takao,隆夫,祟夫,孝雄\n")
        fs = [_rk("first_name_man_org.csv", "たかお,takao,隆夫,祟夫,孝雄,高男", "祟夫"),
              _rk("first_name_man_opti.csv", "たかお,takao,隆夫,祟夫,孝雄", "孝雄")]
        out = sync_full_popular.sync(fs, ds, today="2026-11-23")
        added = {f["file"]: f["proposed_fix"] for f in out if f.get("detected_by") == sync_full_popular.DETECTED_BY}
        assert added == {"first_name_man_opti.csv": {"action": "remove_kanji", "value": "祟夫"},
                         "first_name_man_org.csv": {"action": "remove_kanji", "value": "孝雄"}}
        assert all(not findings_io.validate_finding(f) for f in out)

    def test_ignores_pending_and_is_idempotent(self, tmp_path):
        ds = _dataset(tmp_path, "たかお,takao,隆夫,祟夫\n", "たかお,takao,隆夫,祟夫\n")
        fs = [_rk("first_name_man_org.csv", "たかお,takao,隆夫,祟夫", "祟夫"),
              _rk("first_name_man_org.csv", "たかお,takao,隆夫,祟夫", "隆夫", status="pending")]
        fs[1]["id"] += "x"
        once = sync_full_popular.sync(fs, ds, today="2026-11-23")
        twice = sync_full_popular.sync(once, ds, today="2026-11-23")
        assert once == twice
        assert [f["proposed_fix"]["value"] for f in once if f.get("detected_by") == sync_full_popular.DETECTED_BY] == ["祟夫"]

    def test_row_removal_and_full_overlap_become_remove_row(self, tmp_path):
        ds = _dataset(tmp_path, "えさお,esao,江雄\nしおん,shion,志遠,史臣\n", "えさお,esao,江雄\nしおん,shion,史臣\n")
        fs = [_rk("first_name_man_org.csv", "えさお,esao,江雄", "", action="remove_row"),
              _rk("first_name_man_org.csv", "しおん,shion,志遠,史臣", "史臣")]
        out = sync_full_popular.sync(fs, ds, today="2026-11-23")
        added = sorted((f["entry"], f["proposed_fix"]["action"]) for f in out
                       if f.get("detected_by") == sync_full_popular.DETECTED_BY)
        assert added == [("えさお,esao,江雄", "remove_row"), ("しおん,shion,史臣", "remove_row")]


def _batch():
    entries = [
        {"file": MAN, "line": 1, "raw": "あいじろう,aijirou,愛慈郎,愛二郎,愛次郎", "reading": "あいじろう",
         "romaji": "aijirou", "kanji": ["愛慈郎", "愛二郎", "愛次郎"], "deterministic_error": None},
        {"file": MAN, "line": 2, "raw": "えさお,esao,江雄", "reading": "えさお", "romaji": "esao",
         "kanji": ["江雄"], "deterministic_error": None},
    ]
    for e in entries:
        e["hash"] = findings_io.entry_hash(e["file"], e["raw"])
    return {"batch_id": "batch_001", "entries": entries}


def _dec(*findings):
    return {"batch_id": "batch_001", "findings": list(findings)}


class TestReviewResult:
    def test_builds_entry_and_ok_hashes(self):
        b = _batch()
        res, errors = review_result.build_result(b, _dec(
            {"hash": b["entries"][0]["hash"], "check": "kanji_reading_mismatch", "confidence": "low",
             "evidence": "慈 は じ と読めるが…", "action": "remove_kanji", "value": "愛慈郎, 愛二郎"}), today="2026-11-23")
        assert errors == []
        f = res["findings"][0]
        assert f["entry"] == b["entries"][0]["raw"] and f["proposed_fix"]["value"] == "愛慈郎、愛二郎"
        assert res["ok_hashes"] == [b["entries"][1]["hash"]]

    def test_rejects_unknown_kanji_all_kanji_and_duplicates(self):
        b = _batch()
        h0, h1 = b["entries"][0]["hash"], b["entries"][1]["hash"]
        base = {"check": "kanji_reading_mismatch", "confidence": "low", "evidence": "根拠"}
        _, errors = review_result.build_result(b, _dec(
            dict(base, hash=h0, action="remove_kanji", value="存在しない"),
            dict(base, hash=h1, action="remove_kanji", value="江雄"),
            dict(base, hash=h0, action="remove_kanji", value="愛二郎"),
            dict(base, hash=h0, action="remove_kanji", value="愛次郎")))
        assert len(errors) == 3
        assert "表記でない" in errors[0] and "remove_row" in errors[1] and "2 つある" in errors[2]

    def test_jmnedict_leak_detection(self):
        assert review_result.jmnedict_leak("NDL・Wikidata・JMnedict のいずれにも用例がない") is None
        assert review_result.jmnedict_leak("JMnedict に同型の用例があるため判断保留") is None
        assert review_result.jmnedict_leak("桜=え は JMnedict の 李桜=りえ 1 件のみ") is not None
        assert review_result.jmnedict_leak("沙都子 の読みは JMnedict も さとこ") is not None
        b = _batch()
        _, errors = review_result.build_result(b, _dec(
            {"hash": b["entries"][1]["hash"], "check": "kanji_reading_mismatch", "confidence": "low",
             "evidence": "JMnedict では えお と読む", "action": "remove_row", "value": ""}))
        assert errors and "JMnedict" in errors[0]

    def test_cli_writes_result_only_when_valid(self, tmp_path):
        b = _batch()
        work = tmp_path / "work"
        (work / "decisions").mkdir(parents=True)
        (work / "batch_001.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
        script = os.path.join(ROOT, ".claude", "skills", "qa-review", "scripts", "review_result.py")
        (work / "decisions" / "batch_001.json").write_text(json.dumps(_dec(
            {"hash": "nope", "check": "not_a_name", "confidence": "low", "evidence": "x",
             "action": "none", "value": ""})), encoding="utf-8")
        r = subprocess.run([sys.executable, script, "--work-dir", str(work), "batch_001"],
                           capture_output=True, text=True, encoding="utf-8")
        assert r.returncode == 1 and not (work / "results" / "batch_001.json").exists()
        (work / "decisions" / "batch_001.json").write_text(json.dumps(_dec()), encoding="utf-8")
        r = subprocess.run([sys.executable, script, "--work-dir", str(work), "batch_001"],
                           capture_output=True, text=True, encoding="utf-8")
        assert r.returncode == 0 and "OK: batch_001 疑義 0 件" in r.stdout
        res = json.loads((work / "results" / "batch_001.json").read_text(encoding="utf-8"))
        assert len(res["ok_hashes"]) == 2
