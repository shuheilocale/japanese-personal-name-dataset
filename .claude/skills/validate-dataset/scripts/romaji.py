"""ひらがな→ローマ字候補生成（検証用）。

単一の正解を生成するのではなく、データセットで許容される複数方式
（ワープロ式・長音省略式・その混合）の候補集合を生成する。
実データで方式の混在が確認されているため（例: あいいちろう→aichirou、
いっしゅう→isshu）、どの候補にも一致しない行だけを疑義とする。
"""
import itertools
from typing import List, Optional, Set

BASIC = {
    "あ": "a", "い": "i", "う": "u", "え": "e", "お": "o",
    "か": "ka", "き": "ki", "く": "ku", "け": "ke", "こ": "ko",
    "さ": "sa", "し": "shi", "す": "su", "せ": "se", "そ": "so",
    "た": "ta", "ち": "chi", "つ": "tsu", "て": "te", "と": "to",
    "な": "na", "に": "ni", "ぬ": "nu", "ね": "ne", "の": "no",
    "は": "ha", "ひ": "hi", "ふ": "fu", "へ": "he", "ほ": "ho",
    "ま": "ma", "み": "mi", "む": "mu", "め": "me", "も": "mo",
    "や": "ya", "ゆ": "yu", "よ": "yo",
    "ら": "ra", "り": "ri", "る": "ru", "れ": "re", "ろ": "ro",
    "わ": "wa", "ゐ": "i", "ゑ": "e", "を": "o",
    "が": "ga", "ぎ": "gi", "ぐ": "gu", "げ": "ge", "ご": "go",
    "ざ": "za", "じ": "ji", "ず": "zu", "ぜ": "ze", "ぞ": "zo",
    "だ": "da", "ぢ": "ji", "づ": "zu", "で": "de", "ど": "do",
    "ば": "ba", "び": "bi", "ぶ": "bu", "べ": "be", "ぼ": "bo",
    "ぱ": "pa", "ぴ": "pi", "ぷ": "pu", "ぺ": "pe", "ぽ": "po",
    "ぁ": "a", "ぃ": "i", "ぅ": "u", "ぇ": "e", "ぉ": "o",
    "ゔ": "vu",
}

YOUON = {
    "きゃ": "kya", "きゅ": "kyu", "きょ": "kyo",
    "しゃ": "sha", "しゅ": "shu", "しょ": "sho",
    "ちゃ": "cha", "ちゅ": "chu", "ちょ": "cho",
    "にゃ": "nya", "にゅ": "nyu", "にょ": "nyo",
    "ひゃ": "hya", "ひゅ": "hyu", "ひょ": "hyo",
    "みゃ": "mya", "みゅ": "myu", "みょ": "myo",
    "りゃ": "rya", "りゅ": "ryu", "りょ": "ryo",
    "ぎゃ": "gya", "ぎゅ": "gyu", "ぎょ": "gyo",
    "じゃ": "ja", "じゅ": "ju", "じょ": "jo",
    "ぢゃ": "ja", "ぢゅ": "ju", "ぢょ": "jo",
    "びゃ": "bya", "びゅ": "byu", "びょ": "byo",
    "ぴゃ": "pya", "ぴゅ": "pyu", "ぴょ": "pyo",
}

_SMALL_YOUON = "ゃゅょ"
_VOWELS = "aiueo"
_LIMIT = 4096  # 候補集合の上限（人名の長さでは実質届かない安全弁）


def tokenize(hira):
    # type: (str) -> List[str]
    """ひらがなをモーラ単位に分割する。促音="Q"、撥音="N"、長音記号="H"。"""
    tokens = []  # type: List[str]
    i = 0
    while i < len(hira):
        ch = hira[i]
        if ch == "っ":
            tokens.append("Q")
            i += 1
        elif ch == "ん":
            tokens.append("N")
            i += 1
        elif ch == "ー":
            tokens.append("H")
            i += 1
        elif i + 1 < len(hira) and hira[i:i + 2] in YOUON:
            tokens.append(hira[i:i + 2])
            i += 2
        elif ch in _SMALL_YOUON or ch not in BASIC:
            raise ValueError("モーラ分割できないかな: %r（%r 内）" % (ch, hira))
        else:
            tokens.append(ch)
            i += 1
    return tokens


def _mora_romaji(token):
    # type: (str) -> str
    if token in YOUON:
        return YOUON[token]
    return BASIC[token]


def _prev_vowel(tokens, idx):
    # type: (List[str], int) -> Optional[str]
    """idx の直前の（マーカーでない）モーラの末尾母音を返す。"""
    j = idx - 1
    while j >= 0 and tokens[j] in ("Q", "H"):
        j -= 1
    if j < 0 or tokens[j] == "N":
        return None
    r = _mora_romaji(tokens[j])
    return r[-1] if r[-1] in _VOWELS else None


def _next_real(tokens, idx):
    # type: (List[str], int) -> Optional[str]
    """idx の直後の（マーカーでない）モーラを返す。"""
    j = idx + 1
    while j < len(tokens) and tokens[j] in ("Q", "H", "N"):
        j += 1
    return tokens[j] if j < len(tokens) else None


def _alternatives(tokens, long_mode):
    # type: (List[str], str) -> List[List[str]]
    """モーラごとのローマ字候補リストを返す。long_mode: 'keep' | 'drop' | 'both'"""
    alts = []  # type: List[List[str]]
    for idx, tok in enumerate(tokens):
        if tok == "Q":
            nxt = _next_real(tokens, idx)
            if nxt is None:
                alts.append([""])  # 語末の促音（不正に近いが落とさない）
            else:
                r = _mora_romaji(nxt)
                if r.startswith("ch"):
                    alts.append(["t", "c"])  # っち→tchi / cchi
                else:
                    alts.append([r[0]])
        elif tok == "N":
            nxt = tokens[idx + 1] if idx + 1 < len(tokens) else None
            options = ["n"]
            if nxt is not None and nxt not in ("Q", "H", "N"):
                r = _mora_romaji(nxt)
                if r[0] in "bmp":
                    options.append("m")
                if r[0] in _VOWELS or r[0] == "y":
                    options.append("n'")
            alts.append(options)
        elif tok == "H":
            pv = _prev_vowel(tokens, idx)
            alts.append(_long_options(pv if pv else "", long_mode))
        else:
            base = _mora_romaji(tok)
            pv = _prev_vowel(tokens, idx)
            is_long = (
                tok in ("あ", "い", "う", "え", "お")
                and pv is not None
                and (base == pv or (tok == "う" and pv == "o") or (tok == "い" and pv == "e"))
            )
            if is_long:
                alts.append(_long_options(base, long_mode))
            else:
                alts.append([base])
    return alts


def _long_options(vowel, long_mode):
    # type: (str, str) -> List[str]
    if long_mode == "keep":
        return [vowel] if vowel else [""]
    if long_mode == "drop":
        return [""]
    return [vowel, ""] if vowel else [""]


def _combine(alts):
    # type: (List[List[str]]) -> Set[str]
    out = set()  # type: Set[str]
    for combo in itertools.product(*alts):
        out.add("".join(combo))
        if len(out) >= _LIMIT:
            break
    return out


def romaji_candidates(hira):
    # type: (str) -> Set[str]
    """許容される全ローマ字候補（ワープロ式・長音省略式・混合）を返す。"""
    return _combine(_alternatives(tokenize(hira), "both"))


def classify_style(hira, romaji_str):
    # type: (str, str) -> str
    """ローマ字表記が長音をどう扱っているかを判定する。"""
    try:
        tokens = tokenize(hira)
    except ValueError:
        return "unknown"
    keep = _combine(_alternatives(tokens, "keep"))
    drop = _combine(_alternatives(tokens, "drop"))
    if keep == drop:  # 長音を含まない
        return "neutral" if romaji_str in keep else "unknown"
    in_keep = romaji_str in keep
    in_drop = romaji_str in drop
    if in_keep and in_drop:
        return "neutral"
    if in_keep:
        return "wapuro"
    if in_drop:
        return "shortened"
    if romaji_str in _combine(_alternatives(tokens, "both")):
        return "mixed"
    return "unknown"
