"""generate_candidates.py のテスト。"""
import json
import os

import generate_candidates as gc
import source_index as si
import sources_common as sc


def _dataset(tmp_path):
    d = tmp_path / "dataset"
    d.mkdir()
    (d / "first_name_man_org.csv").write_text("あい,ai,藍\nかおる,kaoru,薫\n", encoding="utf-8")
    (d / "first_name_man_opti.csv").write_text("", encoding="utf-8")
    (d / "first_name_woman_org.csv").write_text("かおる,kaoru,香\nさくら,sakura,桜\n", encoding="utf-8")
    (d / "first_name_woman_opti.csv").write_text("", encoding="utf-8")
    (d / "last_name_org.csv").write_text("金子,100,きんす,kinsu\n佐藤,200,さとう,satou\n", encoding="utf-8")
    return str(d)


def _index():
    return si.build_index([
        sc.record("ndl", "given", "愛", "あい", count=9),           # add_kanji（強根拠）
        sc.record("wikidata", "given", "愛", "あい", gender="female", count=2),
        sc.record("ndl", "given", "哀", "あい", count=1),           # 根拠不足
        sc.record("ndl", "given", "樹", "いつき", count=7),          # add_row（性別は wikidata）
        sc.record("wikidata", "given", "", "いつき", gender="male", count=3),
        sc.record("wikidata", "given", "樹", "いつき", gender="male", count=3),
        sc.record("ndl", "given", "凛", "りん", count=6),            # add_row（性別不明 → pending 判定へ）
        sc.record("ndl", "given", "龘", "たつ", count=9),            # 人名用漢字外 → 除外
        sc.record("ndl", "surname", "金子", "かねこ", count=50),      # 姓の照合
        sc.record("ndl", "surname", "佐藤", "さとう", count=90),
    ])


ALLOWED = {"愛", "哀", "樹", "凛", "藍", "薫", "香", "桜"}


class TestGenerate:
    def test_add_kanji_and_thresholds(self, tmp_path):
        ds = gc.load_dataset(_dataset(tmp_path))
        fs, pending = gc.generate(_index(), ds, ALLOWED, min_ndl=2, auto_ndl=5, today="2026-09-06")
        by_id = {f["id"]: f for f in fs}
        f = by_id["first_name_man_org.csv:あい:missing_entry:add_kanji:愛"]
        assert f["proposed_fix"] == {"action": "add_kanji", "value": "愛"}
        assert f["status"] == "pending"  # female と man ファイルが矛盾 → 事前承認しない
        assert f["sources"] == {"ndl": 9, "wikidata": 2, "jmnedict": False}
        assert "哀" not in json.dumps(fs, ensure_ascii=False)

    def test_add_kanji_ids_unique_when_multiple_candidates_share_reading(self, tmp_path):
        # 同一読み「あい」に2つの add_kanji 候補（愛・哀）がある場合、id が衝突しないこと。
        ds = gc.load_dataset(_dataset(tmp_path))
        index = si.build_index([
            sc.record("ndl", "given", "愛", "あい", count=9),
            sc.record("ndl", "given", "哀", "あい", count=3),
        ])
        fs, _ = gc.generate(index, ds, ALLOWED, min_ndl=2, auto_ndl=5, today="2026-09-06")
        ids = [f["id"] for f in fs if f["proposed_fix"]["action"] == "add_kanji"]
        assert len(ids) == 2 and len(set(ids)) == 2
        assert set(ids) == {
            "first_name_man_org.csv:あい:missing_entry:add_kanji:愛",
            "first_name_man_org.csv:あい:missing_entry:add_kanji:哀",
        }

    def test_add_row_with_wikidata_gender_is_auto_approved(self, tmp_path):
        ds = gc.load_dataset(_dataset(tmp_path))
        fs, pending = gc.generate(_index(), ds, ALLOWED, today="2026-09-06")
        f = next(x for x in fs if x["proposed_fix"]["action"] == "add_row" and x["entry"].startswith("いつき,"))
        assert f["file"] == "first_name_man_org.csv"
        assert f["entry"] == "いつき,itsuki,樹"
        assert f["status"] == "approved"

    def test_gender_unknown_goes_to_pending_list(self, tmp_path):
        ds = gc.load_dataset(_dataset(tmp_path))
        fs, pending = gc.generate(_index(), ds, ALLOWED, today="2026-09-06")
        assert not [x for x in fs if x["entry"].startswith("りん,")]
        assert pending == [{"reading": "りん", "kanji": ["凛"], "sources": {"ndl": 6, "wikidata": 0, "jmnedict": False}}]

    def test_disallowed_kanji_excluded(self, tmp_path):
        ds = gc.load_dataset(_dataset(tmp_path))
        fs, pending = gc.generate(_index(), ds, ALLOWED, today="2026-09-06")
        assert "龘" not in json.dumps(fs, ensure_ascii=False) and not [p for p in pending if p["reading"] == "たつ"]

    def test_surname_mismatch(self, tmp_path):
        ds = gc.load_dataset(_dataset(tmp_path))
        fs, _ = gc.generate(_index(), ds, ALLOWED, today="2026-09-06")
        s = next(x for x in fs if x["file"] == "last_name_org.csv")
        assert s["entry"] == "金子,100,きんす,kinsu" and s["proposed_fix"] == {"action": "fix_reading", "value": "かねこ"}
        assert not [x for x in fs if x["file"] == "last_name_org.csv" and "佐藤" in x["entry"]]

    def test_surname_mismatch_ids_unique_for_shared_current_reading(self, tmp_path):
        # 阿部・安部のように別の漢字が同じ（誤った）現行読みを持つ場合でも id が衝突しないこと。
        d = tmp_path / "dataset2"
        d.mkdir()
        (d / "first_name_man_org.csv").write_text("", encoding="utf-8")
        (d / "first_name_man_opti.csv").write_text("", encoding="utf-8")
        (d / "first_name_woman_org.csv").write_text("", encoding="utf-8")
        (d / "first_name_woman_opti.csv").write_text("", encoding="utf-8")
        (d / "last_name_org.csv").write_text(
            "阿部,100,きんす,kinsu\n安部,50,きんす,kinsu\n", encoding="utf-8")
        ds = gc.load_dataset(str(d))
        index = si.build_index([
            sc.record("ndl", "surname", "阿部", "あべ", count=80),
            sc.record("ndl", "surname", "安部", "あべ", count=40),
        ])
        fs, _ = gc.generate(index, ds, ALLOWED, today="2026-09-06")
        assert len(fs) == 2
        ids = [f["id"] for f in fs]
        assert len(ids) == len(set(ids)) == 2
        assert set(ids) == {
            "last_name_org.csv:阿部:kanji_reading_mismatch:fix_reading",
            "last_name_org.csv:安部:kanji_reading_mismatch:fix_reading",
        }

    def test_max_candidates(self, tmp_path):
        ds = gc.load_dataset(_dataset(tmp_path))
        fs, _ = gc.generate(_index(), ds, ALLOWED, max_candidates=1, today="2026-09-06")
        adds = [x for x in fs if x["proposed_fix"]["action"].startswith("add_")]
        assert len(adds) == 1 and adds[0]["sources"]["ndl"] == 9  # 根拠最大のもの

    def test_carry_over(self):
        old = [_f("a", "rejected"), _f("b", "applied")]
        new = [_f("a", "pending", today="2026-10-01"), _f("b", "approved", today="2026-10-01"),
               _f("c", "pending", today="2026-10-01")]
        out = gc.carry_over(new, old)
        assert [x["status"] for x in out] == ["rejected", "applied", "pending"]
        # 完全一致なら detected_at も引き継ぐ（同じ索引での再実行がバイト一致するため）
        assert [x["detected_at"] for x in out] == ["2026-09-06", "2026-09-06", "2026-10-01"]
        assert gc.CHANGED_NOTE not in json.dumps(out, ensure_ascii=False)


SUP = {"ndl": 7, "wikidata": 1, "jmnedict": False}


def _f(fid, status, entry="いつき,itsuki,樹", action="add_row", value="", today="2026-09-06",
       file="first_name_man_org.csv"):
    d = gc._finding(file, entry, action, value, SUP, status, today)
    d["id"] = fid
    return d


class TestCarryOverKey:
    def test_surname_value_change_resets_to_pending_with_note(self):
        old = _f("s", "approved", entry="神谷,88900,かみや,kamiya", action="fix_reading", value="かみたに",
                 file="last_name_org.csv")
        new = _f("s", "pending", entry="神谷,88900,かみや,kamiya", action="fix_reading", value="かべや",
                 file="last_name_org.csv", today="2026-10-01")
        out = gc.carry_over([new], [old])
        assert out[0]["status"] == "pending" and out[0]["proposed_fix"]["value"] == "かべや"
        assert out[0]["evidence"].endswith(gc.CHANGED_NOTE)
        assert out[0]["detected_at"] == "2026-10-01"

    def test_add_row_entry_change_resets_to_pending_with_note(self):
        old = _f("r", "approved", entry="つむぎ,tsumugi,紬,紬希")
        new = _f("r", "pending", entry="つむぎ,tsumugi,紬,紬希,紬葵", today="2026-10-01")
        out = gc.carry_over([new], [old])
        assert out[0]["status"] == "pending" and out[0]["entry"] == "つむぎ,tsumugi,紬,紬希,紬葵"
        assert out[0]["evidence"].endswith(gc.CHANGED_NOTE)

    def test_exact_match_keeps_status(self):
        old = _f("r", "approved", entry="つむぎ,tsumugi,紬,紬希")
        new = _f("r", "pending", entry="つむぎ,tsumugi,紬,紬希", today="2026-10-01")
        out = gc.carry_over([new], [old])
        assert out[0]["status"] == "approved" and out[0]["detected_at"] == "2026-09-06"
        assert gc.CHANGED_NOTE not in out[0]["evidence"]

    def test_rejected_add_kanji_with_same_content_stays_rejected(self):
        old = _f("k", "rejected", entry="けんいち,kenichi,健一", action="add_kanji", value="権市")
        new = _f("k", "pending", entry="けんいち,kenichi,健一", action="add_kanji", value="権市")
        assert gc.carry_over([new], [old])[0]["status"] == "rejected"

    def test_note_persists_while_pending_and_drops_once_decided(self):
        # 内容変更で pending+注記になった finding は、同じ索引で再実行しても注記を保つ
        # （バイト一致）。承認/却下されたあとの再実行では注記を引き継がない。
        changed = _f("r", "pending", entry="つむぎ,tsumugi,紬,紬希,紬葵")
        changed["evidence"] += gc.CHANGED_NOTE
        again = _f("r", "pending", entry="つむぎ,tsumugi,紬,紬希,紬葵")
        assert gc.carry_over([again], [changed])[0]["evidence"] == changed["evidence"]
        decided = dict(changed, status="approved")
        again2 = _f("r", "pending", entry="つむぎ,tsumugi,紬,紬希,紬葵")
        out = gc.carry_over([again2], [decided])[0]
        assert out["status"] == "approved" and gc.CHANGED_NOTE not in out["evidence"]

    def test_key_matches_qa_batch_rule(self):
        d = _f("x", "pending", entry="e", action="add_kanji", value="v")
        d["check"] = "missing_entry"
        assert gc._finding_key(d) == ("x", "missing_entry", "e", "add_kanji", "v")


class TestMergeLedger:
    def _existing(self):
        llm = _f("first_name_woman_org.csv:りりあ:missing_entry:add_row", "pending",
                 entry="りりあ,riria,莉里亜", file="first_name_woman_org.csv")
        llm["detected_by"] = "qa-update/gender_batch v1"
        applied = _f("first_name_woman_org.csv:さくら:missing_entry:add_kanji:咲空", "applied",
                     entry="さくら,sakura,桜", action="add_kanji", value="咲空", file="first_name_woman_org.csv")
        stale = _f("first_name_man_org.csv:けんいち:missing_entry:add_kanji:建市", "pending",
                   entry="けんいち,kenichi,健一", action="add_kanji", value="建市")
        regen = _f("first_name_man_org.csv:けんいち:missing_entry:add_kanji:兼市", "rejected",
                   entry="けんいち,kenichi,健一", action="add_kanji", value="兼市")
        return [llm, applied, stale, regen]

    def test_keeps_foreign_pending_and_non_pending_drops_stale_own_pending(self):
        existing = self._existing()
        new = [_f("first_name_man_org.csv:けんいち:missing_entry:add_kanji:兼市", "pending",
                  entry="けんいち,kenichi,健一", action="add_kanji", value="兼市", today="2026-10-01"),
               _f("first_name_man_org.csv:れんと:missing_entry:add_row", "approved",
                  entry="れんと,rento,蓮斗", today="2026-10-01")]
        out = gc.merge_ledger(new, existing)
        ids = [d["id"] for d in out]
        assert ids == [
            "first_name_woman_org.csv:りりあ:missing_entry:add_row",          # LLM 由来 pending は保持
            "first_name_woman_org.csv:さくら:missing_entry:add_kanji:咲空",    # applied は保持
            "first_name_man_org.csv:けんいち:missing_entry:add_kanji:兼市",    # 再生成分（status 引き継ぎ）
            "first_name_man_org.csv:れんと:missing_entry:add_row",            # 新規
        ]
        assert out[2]["status"] == "rejected" and out[2]["detected_at"] == "2026-09-06"
        assert out[0]["detected_by"] == "qa-update/gender_batch v1"
        assert len({d["id"] for d in out}) == len(out)

    def test_rerun_with_same_input_is_stable(self):
        new = [_f("a", "pending"), _f("b", "approved", entry="れんと,rento,蓮斗")]
        first = gc.merge_ledger([dict(d, proposed_fix=dict(d["proposed_fix"])) for d in new], self._existing())
        second = gc.merge_ledger([dict(d, proposed_fix=dict(d["proposed_fix"])) for d in new], first)
        assert json.dumps(first, ensure_ascii=False) == json.dumps(second, ensure_ascii=False)

    def test_regenerated_id_replaces_kept_copy(self):
        # 保持対象（applied 等）と同 id が再生成された場合も id は重複しない。
        existing = [_f("a", "approved")]
        out = gc.merge_ledger([_f("a", "pending", entry="いつき,itsuki,樹,一樹")], existing)
        assert [d["id"] for d in out] == ["a"]
        assert out[0]["status"] == "pending" and out[0]["entry"] == "いつき,itsuki,樹,一樹"


def test_detected_by_constant():
    assert gc._finding("first_name_man_org.csv", "あ,a,亜", "add_kanji", "阿", SUP, "pending",
                       "2026-09-06")["detected_by"] == gc.DETECTED_BY == "qa-update v1"


def test_romaji_for():
    assert gc.romaji_for("いつき") == "itsuki"
    assert gc.romaji_for("けんいち") == "kenichi"
    assert gc.romaji_for("さとう") == "satou"
