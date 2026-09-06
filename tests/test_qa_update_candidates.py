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


class TestPairGender:
    """性別矛盾の判定は pair 単位の Wikidata クラスを優先し、無ければ読み単位へフォールバック。"""

    def test_pair_level_female_blocks_auto_approve_for_man_file(self, tmp_path):
        # かおる は男女両ファイルにある（読み単位では unisex）が、表記 香留 の Wikidata クラスは female。
        ds = gc.load_dataset(_dataset(tmp_path))
        index = si.build_index([
            sc.record("wikidata", "given", "薫", "かおる", gender="male", count=3),
            sc.record("wikidata", "given", "香留", "かおる", gender="female", count=1),
            sc.record("ndl", "given", "香留", "かおる", count=7),
        ])
        fs, _ = gc.generate(index, ds, ALLOWED | {"留"}, today="2026-09-06")
        by_id = {f["id"]: f for f in fs}
        man = by_id["first_name_man_org.csv:かおる:missing_entry:add_kanji:香留"]
        woman = by_id["first_name_woman_org.csv:かおる:missing_entry:add_kanji:香留"]
        assert man["status"] == "pending" and "（索引の性別 female と追加先が矛盾）" in man["evidence"]
        assert woman["status"] == "approved" and "矛盾" not in woman["evidence"]

    def test_falls_back_to_reading_level_when_pair_has_no_class(self, tmp_path):
        # 表記 香留 には Wikidata クラスが無い（NDL のみ）→ 読み単位（仮名項目 female）で判定する。
        ds = gc.load_dataset(_dataset(tmp_path))
        index = si.build_index([
            sc.record("wikidata", "given", "", "かおる", gender="female", count=2),
            sc.record("wikidata", "given", "香留", "かおる", gender=None, count=1),
            sc.record("ndl", "given", "香留", "かおる", count=7),
        ])
        fs, _ = gc.generate(index, ds, ALLOWED | {"留"}, today="2026-09-06")
        by_id = {f["id"]: f for f in fs}
        assert by_id["first_name_man_org.csv:かおる:missing_entry:add_kanji:香留"]["status"] == "pending"
        assert by_id["first_name_woman_org.csv:かおる:missing_entry:add_kanji:香留"]["status"] == "approved"

    def test_add_row_with_conflicting_pair_is_not_auto_approved(self, tmp_path):
        # 新規読み いつき（読み単位 unisex → 両ファイル）で、表記 樹 は male クラス:
        # 女性ファイル向け add_row は矛盾を注記して pending、男性ファイル向けは approved。
        ds = gc.load_dataset(_dataset(tmp_path))
        index = si.build_index([
            sc.record("wikidata", "given", "", "いつき", gender="female", count=1),
            sc.record("wikidata", "given", "樹", "いつき", gender="male", count=3),
            sc.record("ndl", "given", "樹", "いつき", count=7),
        ])
        fs, _ = gc.generate(index, ds, ALLOWED, today="2026-09-06")
        by_id = {f["id"]: f for f in fs}
        assert by_id["first_name_man_org.csv:いつき:missing_entry:add_row"]["status"] == "approved"
        woman = by_id["first_name_woman_org.csv:いつき:missing_entry:add_row"]
        assert woman["status"] == "pending" and "（索引の性別 male と追加先が矛盾: 樹）" in woman["evidence"]


def _surname_dataset(tmp_path, last_rows):
    d = tmp_path / "dataset_s"
    d.mkdir()
    for fn in ("first_name_man_org.csv", "first_name_man_opti.csv",
               "first_name_woman_org.csv", "first_name_woman_opti.csv"):
        (d / fn).write_text("", encoding="utf-8")
    (d / "last_name_org.csv").write_text(last_rows, encoding="utf-8")
    return gc.load_dataset(str(d))


class TestSurnameMatching:
    """姓の照合に使う読み集合は NDL/Wikidata の pair に限定し、JMnedict は照合（存在確認）専用。"""

    def test_jmnedict_only_reading_not_in_value_or_evidence(self, tmp_path):
        ds = _surname_dataset(tmp_path, "金子,100,きんす,kinsu\n")
        index = si.build_index([
            sc.record("ndl", "surname", "金子", "かねこ", count=50),
            sc.record("jmnedict", "surname", "金子", "かなこ"),
        ])
        fs, _ = gc.generate(index, ds, ALLOWED, today="2026-09-06")
        assert len(fs) == 1
        assert fs[0]["proposed_fix"]["value"] == "かねこ"
        assert "かなこ" not in json.dumps(fs, ensure_ascii=False)
        assert "（索引の読み: かねこ。現データの読み きんす は索引に無い）" in fs[0]["evidence"]

    def test_jmnedict_only_surname_yields_no_finding(self, tmp_path):
        ds = _surname_dataset(tmp_path, "長谷川,379000,はせがわ,hasegawa\n")
        index = si.build_index([sc.record("jmnedict", "surname", "長谷川", "はせかわ")])
        fs, _ = gc.generate(index, ds, ALLOWED, today="2026-09-06")
        assert fs == []

    def test_current_reading_confirmed_only_by_jmnedict_yields_no_finding(self, tmp_path):
        # 現データの読みが JMnedict にだけ一致する場合は「照合できず」として finding を出さない
        # （JMnedict の値を転記しないまま存在確認にだけ使う）。
        ds = _surname_dataset(tmp_path, "神谷,88900,かみや,kamiya\n")
        index = si.build_index([
            sc.record("ndl", "surname", "神谷", "かみたに", count=30),
            sc.record("ndl", "surname", "神谷", "かべや", count=5),
            sc.record("jmnedict", "surname", "神谷", "かみや"),
        ])
        fs, _ = gc.generate(index, ds, ALLOWED, today="2026-09-06")
        assert fs == []

    def test_wikidata_only_surname_picks_most_supported_reading(self, tmp_path):
        ds = _surname_dataset(tmp_path, "新井,204000,しんい,shini\n")
        index = si.build_index([
            sc.record("wikidata", "surname", "新井", "あらい", count=3),
            sc.record("wikidata", "surname", "新井", "にい", count=5),
        ])
        fs, _ = gc.generate(index, ds, ALLOWED, today="2026-09-06")
        assert len(fs) == 1 and fs[0]["proposed_fix"]["value"] == "にい"
        assert fs[0]["sources"] == {"ndl": 0, "wikidata": 5, "jmnedict": False}
        assert "（索引の読み: あらい・にい。" in fs[0]["evidence"]

    def test_best_uses_ndl_plus_wikidata_and_breaks_ties_by_reading(self, tmp_path):
        ds = _surname_dataset(tmp_path, "東,100,とう,tou\n")
        index = si.build_index([
            sc.record("ndl", "surname", "東", "ひがし", count=10),
            sc.record("wikidata", "surname", "東", "ひがし", count=1),
            sc.record("ndl", "surname", "東", "あずま", count=8),
            sc.record("wikidata", "surname", "東", "あずま", count=3),
        ])
        fs, _ = gc.generate(index, ds, ALLOWED, today="2026-09-06")
        assert fs[0]["proposed_fix"]["value"] == "あずま"  # 8+3 = 11 = 10+1 → 読み順で あずま


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
        d = _f("x", "pending", entry="e", action="add_row", value="")
        d["check"] = "missing_entry"
        assert gc._finding_key(d) == ("x", "missing_entry", "e", "add_row", "")
        # add_kanji は提案内容（読み・追加漢字）が id に含まれるので entry をキーから外す
        k = _f("x", "pending", entry="e", action="add_kanji", value="v")
        k["check"] = "missing_entry"
        assert gc._finding_key(k) == ("x", "missing_entry", None, "add_kanji", "v")

    def test_add_kanji_keeps_status_when_only_row_changed(self):
        # 同じ行に別候補を適用して entry が変わっただけの add_kanji は rejected / approved を維持する
        # （CHANGED_NOTE で再浮上しない）。
        rej_old = _f("k", "rejected", entry="けんいち,kenichi,健一", action="add_kanji", value="権市")
        rej_new = _f("k", "pending", entry="けんいち,kenichi,健一,兼市", action="add_kanji", value="権市",
                     today="2026-10-01")
        out = gc.carry_over([rej_new], [rej_old])[0]
        assert out["status"] == "rejected" and out["detected_at"] == "2026-09-06"
        assert out["entry"] == "けんいち,kenichi,健一,兼市" and gc.CHANGED_NOTE not in out["evidence"]
        app_old = _f("a", "approved", entry="けんいち,kenichi,健一", action="add_kanji", value="建市")
        app_new = _f("a", "pending", entry="けんいち,kenichi,健一,兼市", action="add_kanji", value="建市")
        assert gc.carry_over([app_new], [app_old])[0]["status"] == "approved"

    def test_add_kanji_value_change_still_resets(self):
        # value（追加漢字）は id に含まれるので通常は変わらないが、変わればキー不一致として pending に戻る
        old = _f("k", "rejected", entry="e", action="add_kanji", value="権市")
        new = _f("k", "pending", entry="e", action="add_kanji", value="建市")
        out = gc.carry_over([new], [old])[0]
        assert out["status"] == "pending" and out["evidence"].endswith(gc.CHANGED_NOTE)


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

    def _unregenerated(self):
        approved = _f("first_name_man_org.csv:けんいち:missing_entry:add_kanji:兼市", "approved",
                      entry="けんいち,kenichi,健一", action="add_kanji", value="兼市")
        applied = _f("first_name_woman_org.csv:さくら:missing_entry:add_kanji:咲空", "applied",
                     entry="さくら,sakura,桜", action="add_kanji", value="咲空", file="first_name_woman_org.csv")
        rejected = _f("first_name_man_org.csv:けんいち:missing_entry:add_kanji:権市", "rejected",
                      entry="けんいち,kenichi,健一", action="add_kanji", value="権市")
        llm_pending = _f("first_name_woman_org.csv:りりあ:missing_entry:add_row", "pending",
                         entry="りりあ,riria,莉里亜", file="first_name_woman_org.csv")
        llm_pending["detected_by"] = "qa-update/gender_batch v1"
        llm_approved = _f("first_name_man_org.csv:りく:missing_entry:add_row", "approved", entry="りく,riku,陸")
        llm_approved["detected_by"] = "qa-update/gender_batch v1"
        return [approved, applied, rejected, llm_pending, llm_approved]

    def test_unregenerated_own_approved_is_demoted_to_pending_with_note(self):
        # 索引更新・閾値上げ・cap 外れで根拠が消えた事前承認は、そのまま適用されないよう pending に戻す。
        out = gc.merge_ledger([_f("z", "pending", entry="れんと,rento,蓮斗")], self._unregenerated())
        by_id = {d["id"]: d for d in out}
        demoted = by_id["first_name_man_org.csv:けんいち:missing_entry:add_kanji:兼市"]
        assert demoted["status"] == "pending"
        assert demoted["evidence"] == "NDL 7人 / Wikidata 1人 / JMnedict -" + gc.DROPPED_NOTE
        assert demoted["detected_at"] == "2026-09-06"
        # applied / rejected / 他出自（pending・approved とも）は不変
        assert by_id["first_name_woman_org.csv:さくら:missing_entry:add_kanji:咲空"]["status"] == "applied"
        assert by_id["first_name_man_org.csv:けんいち:missing_entry:add_kanji:権市"]["status"] == "rejected"
        assert by_id["first_name_woman_org.csv:りりあ:missing_entry:add_row"]["status"] == "pending"
        assert by_id["first_name_man_org.csv:りく:missing_entry:add_row"]["status"] == "approved"
        assert gc.DROPPED_NOTE not in json.dumps([d for d in out if d["id"] != demoted["id"]], ensure_ascii=False)
        assert [d["id"] for d in out][-1] == "z"

    def test_demoted_finding_is_kept_until_decided_and_stable(self):
        # 候補外で pending に戻した finding は判断されるまで残り、再実行しても注記は重複しない（バイト一致）。
        new = lambda: [_f("z", "pending", entry="れんと,rento,蓮斗")]  # noqa: E731
        first = gc.merge_ledger(new(), self._unregenerated())
        second = gc.merge_ledger(new(), first)
        assert json.dumps(first, ensure_ascii=False) == json.dumps(second, ensure_ascii=False)
        assert "first_name_man_org.csv:けんいち:missing_entry:add_kanji:兼市" in [d["id"] for d in second]

    def test_demoted_finding_regenerated_later_is_normal_pending(self):
        # 候補に戻れば通常の pending として再生成され、候補外注記は消える。
        demoted = gc.merge_ledger([], self._unregenerated())[0]
        assert demoted["status"] == "pending" and demoted["evidence"].endswith(gc.DROPPED_NOTE)
        regen = _f("first_name_man_org.csv:けんいち:missing_entry:add_kanji:兼市", "pending",
                   entry="けんいち,kenichi,健一", action="add_kanji", value="兼市", today="2026-10-01")
        out = gc.merge_ledger([regen], [demoted])
        assert [d["id"] for d in out] == [regen["id"]]
        assert out[0]["status"] == "pending" and gc.DROPPED_NOTE not in out[0]["evidence"]

    def test_re_approved_demoted_finding_is_demoted_again(self):
        # 候補外のまま UI で再承認しても、次の生成で再び pending に戻る（根拠なしの適用を防ぐ）。
        demoted = gc.merge_ledger([], self._unregenerated())[0]
        demoted["status"] = "approved"
        out = gc.merge_ledger([], [demoted])
        assert out[0]["status"] == "pending" and out[0]["evidence"].count(gc.DROPPED_NOTE) == 1


def test_detected_by_constant():
    assert gc._finding("first_name_man_org.csv", "あ,a,亜", "add_kanji", "阿", SUP, "pending",
                       "2026-09-06")["detected_by"] == gc.DETECTED_BY == "qa-update v1"


def test_romaji_for():
    assert gc.romaji_for("いつき") == "itsuki"
    assert gc.romaji_for("けんいち") == "kenichi"
    assert gc.romaji_for("さとう") == "satou"


def test_romaji_for_normalizes_small_ka_ke():
    # NDL の ヵ/ヶ 転写由来の ゕ/ゖ はモーラ分割できないので か/け に正規化してから変換する。
    assert gc.romaji_for("ゆゕ") == "yuka"
    assert gc.romaji_for("ゆゖ") == "yuke"


def test_generate_survives_small_ka_in_new_reading(tmp_path):
    ds = gc.load_dataset(_dataset(tmp_path))
    index = si.build_index([
        sc.record("wikidata", "given", "由佳", "ゆゕ", gender="female", count=1),
        sc.record("ndl", "given", "由佳", "ゆゕ", count=6),
    ])
    fs, _ = gc.generate(index, ds, ALLOWED | {"由", "佳"}, today="2026-09-06")
    assert [f["entry"] for f in fs] == ["ゆゕ,yuka,由佳"]


class TestThresholdBoundaries:
    """add_kanji の閾値境界: 候補化は ndl >= min_ndl(2) or wikidata >= 1、事前承認は ndl >= auto_ndl(5) かつ wikidata >= 1。"""

    def _run(self, tmp_path, ndl, wikidata):
        ds = gc.load_dataset(_dataset(tmp_path))
        recs = []
        if ndl:
            recs.append(sc.record("ndl", "given", "愛", "あい", count=ndl))
        if wikidata:
            recs.append(sc.record("wikidata", "given", "愛", "あい", gender="male", count=wikidata))
        fs, _ = gc.generate(si.build_index(recs), ds, ALLOWED, min_ndl=2, auto_ndl=5, today="2026-09-06")
        return {f["id"]: f["status"] for f in fs}.get("first_name_man_org.csv:あい:missing_entry:add_kanji:愛")

    def test_ndl_2_is_candidate(self, tmp_path):
        assert self._run(tmp_path, ndl=2, wikidata=0) == "pending"

    def test_ndl_1_without_wikidata_is_excluded(self, tmp_path):
        assert self._run(tmp_path, ndl=1, wikidata=0) is None

    def test_ndl_5_with_wikidata_is_approved(self, tmp_path):
        assert self._run(tmp_path, ndl=5, wikidata=1) == "approved"

    def test_ndl_5_without_wikidata_is_pending(self, tmp_path):
        assert self._run(tmp_path, ndl=5, wikidata=0) == "pending"

    def test_ndl_4_with_wikidata_is_pending(self, tmp_path):
        assert self._run(tmp_path, ndl=4, wikidata=1) == "pending"
