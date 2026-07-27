"""romaji.py（ひらがな→ローマ字候補生成）のテスト。"""
import pytest

import romaji


class TestTokenize:
    def test_basic(self):
        assert romaji.tokenize("あい") == ["あ", "い"]

    def test_youon(self):
        assert romaji.tokenize("きょうこ") == ["きょ", "う", "こ"]

    def test_sokuon_hatsuon_chouon(self):
        assert romaji.tokenize("いっき") == ["い", "Q", "き"]
        assert romaji.tokenize("けんいち") == ["け", "N", "い", "ち"]
        assert romaji.tokenize("あーさ") == ["あ", "H", "さ"]

    def test_unknown_char_raises(self):
        with pytest.raises(ValueError):
            romaji.tokenize("あゃ")  # 拗音の小書きが単独で出現（不正データ）


class TestCandidatesBasic:
    def test_simple(self):
        assert "ai" in romaji.romaji_candidates("あい")

    def test_hepburn_specials(self):
        assert "shinji" in romaji.romaji_candidates("しんじ")
        assert "tsutomu" in romaji.romaji_candidates("つとむ")
        assert "fumio" in romaji.romaji_candidates("ふみお")

    def test_sokuon_doubles_consonant(self):
        assert "ikki" in romaji.romaji_candidates("いっき")
        # っち はヘボン式 tchi とワープロ式 cchi の両方を許容
        c = romaji.romaji_candidates("えっちゅう")
        assert "etchu" in c or "etchuu" in c
        assert "ecchu" in c or "ecchuu" in c

    def test_hatsuon_variants(self):
        # ん + b/m/p は n / m 両方許容
        c = romaji.romaji_candidates("じゅんぺい")
        assert "junpei" in c
        assert "jumpei" in c
        # ん + 母音 は n / n' 両方許容
        c = romaji.romaji_candidates("けんいち")
        assert "kenichi" in c
        assert "ken'ichi" in c


class TestLongVowelsAndStyle:
    def test_long_vowel_variants(self):
        c = romaji.romaji_candidates("さとう")
        assert "satou" in c and "sato" in c
        c = romaji.romaji_candidates("ああす")
        assert "aasu" in c and "asu" in c
        c = romaji.romaji_candidates("いっしゅう")
        assert "isshuu" in c and "isshu" in c

    def test_mixed_style_accepted(self):
        # 実データ: あいいちろう,aichirou（いい は省略、ろう は保持）
        assert "aichirou" in romaji.romaji_candidates("あいいちろう")

    def test_classify(self):
        assert romaji.classify_style("あい", "ai") == "neutral"
        assert romaji.classify_style("さとう", "satou") == "wapuro"
        assert romaji.classify_style("いっしゅう", "isshu") == "shortened"
        assert romaji.classify_style("あいいちろう", "aichirou") == "mixed"
        assert romaji.classify_style("さとう", "satoh") == "unknown"
        assert romaji.classify_style("あゃ", "aya") == "unknown"  # 分割不能
