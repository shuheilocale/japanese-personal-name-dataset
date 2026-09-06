"""build_kanji_list.py（常用漢字・人名用漢字の抽出）のテスト。"""
import json

import build_kanji_list as bk

WIKITEXT = """
{| class="sortable wikitable"
|-
! # || 通用字体 || 旧字体
|-
| {{0|000}}1 || style="font-size:180%" | [[wikt:亜|亜]] || style="font-size:180%" | [[wikt:亞|亞]] || 7
|-
| {{0|000}}2 || style="font-size:180%" | [[wikt:哀|哀]] || || 9
|-
| {{0|000}}3 || '''[[wikt:丑|丑]]''' || 表外人名
|}
"""


class TestExtract:
    def test_extract_in_order_unique(self):
        assert bk.extract_kanji(WIKITEXT) == ["亜", "亞", "哀", "丑"]

    def test_first_per_row_skips_old_forms(self):
        assert bk.extract_kanji(WIKITEXT, first_per_row=True) == ["亜", "哀", "丑"]

    def test_ignores_non_kanji_links(self):
        assert bk.extract_kanji("[[wikt:ab|ab]] [[wikt:一|一]]") == ["一"]


class TestAllowed:
    def test_kanji_allowed(self, tmp_path):
        p = tmp_path / "jinmei.txt"
        p.write_text("亜\n哀\n", encoding="utf-8")
        allowed = bk.load_allowed(str(p))
        assert bk.kanji_allowed("亜哀", allowed)
        assert bk.kanji_allowed("あい亜々", allowed)
        assert not bk.kanji_allowed("亜龍", allowed)
        assert bk.kanji_allowed("ゆき", allowed)


class TestResolveDisplay:
    """_resolve_link（span 包み・&#NNNN; 数値文字参照）の解決を検証する。"""

    def test_span_wrapped_display_resolves_to_target_char(self):
        # 常用漢字一覧 第1978項「猶」の実例（表示側が <span> で装飾されている）
        text = "[[wikt:猶|<span style=\"font-family:'x','y';\">猶</span>]]"
        assert bk.extract_kanji(text) == ["猶"]

    def test_numeric_entity_display_resolves_to_referenced_char(self):
        # 人名用漢字一覧「一の表」人2欄の実例（表示側が数値文字参照）。
        # &#64070; は U+FA46（見た目は「渚」U+6E1A と同一だが別コードポイント）
        text = "[[wikt:渚|&#64070;]]"
        assert bk.extract_kanji(text) == [chr(64070)]
        assert bk.extract_kanji(text) != ["渚"]

    def test_numeric_entity_target_resolves_to_referenced_char(self):
        # 人名用漢字一覧「一の表」人1欄の実例（リンク先・表示側の両方が
        # 数値文字参照で書かれている行）
        text = "[[wikt:&#20465;|&#20465;]]"
        assert bk.extract_kanji(text) == [chr(20465)]


class TestReferenceRowExclusion:
    """_has_row_number（行番号のない参考行の除外）を検証する。"""

    DELETED_ROW_WIKITEXT = """
{| class="sortable wikitable"
|-
! # || 通用字体 || 旧字体
|-
| {{0}}854 || [[wikt:蛇|蛇]] || || 1981
|- style="background-color:light-dark(#dddddd,#223); color:inherit;"
| {{0}} || [[wikt:勺|勺]] || || 2010
|-
| {{0}}855 || [[wikt:尺|尺]] || || 6
|}
"""

    def test_row_without_number_is_excluded(self):
        # 「勺」は2010年改定で常用漢字から削除された字の参考行（行番号なし）
        # であり、first_per_row=True では拾わない
        result = bk.extract_kanji(self.DELETED_ROW_WIKITEXT, first_per_row=True)
        assert result == ["蛇", "尺"]
        assert "勺" not in result


class TestRemarksColumnIgnored:
    """_row_links（最終セル＝備考欄の除外）を検証する。"""

    REMARKS_WIKITEXT = """
{| class="sortable wikitable"
|-
! # || 部首 || 人1 || 種別 || 年-月 || 出典 || 人2 || 種別 || 年-月 || 出典 || 備考
|-
| {{0}}28 || [[人部|人]] || '''[[wikt:倶|倶]]''' || 表外印標 || 2004-9 || 出典 || || || || || 「[[wikt:比|比]]」はデザイン差
|}
"""

    def test_remarks_column_link_is_ignored(self):
        # 備考欄の「比」はデザイン差の注記であり、人1・人2 欄のリンクではない
        result = bk.extract_kanji(self.REMARKS_WIKITEXT)
        assert result == ["倶"]
        assert "比" not in result


def _fake_fetch(wikitext):
    def fetch(url, params=None, **_):
        return json.dumps({"parse": {"wikitext": {"*": wikitext}}}).encode("utf-8")
    return fetch


class TestBuildJoyo:
    JOYO_SAMPLE = """
{| class="sortable wikitable"
|-
! # || 通用字体 || 旧字体
|-
| {{0}}1 || [[wikt:亜|亜]] || [[wikt:亞|亞]] || 7
|}
"""

    def test_takes_only_shinjitai_column(self):
        # 旧字体列（亞）は拾わず、通用字体列（亜）のみ採用する
        result = bk.build_joyo(fetch=_fake_fetch(self.JOYO_SAMPLE))
        assert result == ["亜"]


class TestBuildJinmei:
    JINMEI_ICHI = """
{| class="sortable wikitable"
|-
! # || 部首 || 人1 || 種別 || 年-月 || 出典 || 人2 || 種別 || 年-月 || 出典 || 備考
|-
| {{0}}1 || [[部首|部]] || '''[[wikt:亘|亘]]''' || 表外人名 || 1951-5 || 出典 || ［[[wikt:亙|亙]]］ || 人名康熙 || 1951-5 || 出典 ||
|-
| {{0}}2 || [[部首|部]] || '''[[wikt:也|也]]''' || 表外人名 || 1951-5 || 出典 || || || || ||
|}
"""

    JINMEI_NI = """
{| class="sortable wikitable"
|-
! # || 部首 || 通用 || 種別 || 年-月 || 出典 || 異体 || 種別 || 年-月 || 出典
|-
| {{0}}1 || [[部首|部]] || '''[[wikt:亜|亜]]''' || 1946当用 || 出典 || 出典 || ［[[wikt:亞|亞]]］ || 康熙別掲 || 1948 || 出典
|}
"""

    def test_combines_ichi_and_ni_tables(self):
        # 一の表（人1・人2）と二の表（異体のみ、通用は常用漢字と重複するため
        # 除外）の両方を合算する。二の表の「亜」（通用）は含まれない。
        wikitext = self.JINMEI_ICHI + "\n" + self.JINMEI_NI
        result = bk.build_jinmei(fetch=_fake_fetch(wikitext))
        assert set(result) == {"亘", "亙", "也", "亞"}
        assert "亜" not in result
