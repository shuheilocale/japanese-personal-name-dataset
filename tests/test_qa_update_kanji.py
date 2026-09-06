"""build_kanji_list.py（常用漢字・人名用漢字の抽出）のテスト。"""
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
