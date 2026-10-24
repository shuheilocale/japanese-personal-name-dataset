"""会員登録フォームの氏名チェック。

入力された「漢字」と「ふりがな」の組み合わせがデータセットにあるかを調べ、
無ければ漢字から読みの候補を、読みから漢字の候補を提示する。

    python examples/form_validation.py 翔太 しょうた
    python examples/form_validation.py 翔太 しょうだ
"""
import sys
from typing import List

from japanese_personal_name_dataset import get_readings_for_kanji, is_valid_name, search_by_reading


def check_given_name(kanji: str, reading: str) -> List[str]:
    """問題が無ければ空リスト、あれば利用者に見せるメッセージのリストを返す。"""
    if is_valid_name(kanji, reading):
        return []
    messages = ["「%s（%s）」はデータセットにありません。" % (kanji, reading)]
    readings = sorted({r["reading"] for r in get_readings_for_kanji(kanji)})
    if readings:
        messages.append("「%s」の読みの候補: %s" % (kanji, "、".join(readings[:10])))
    spellings = [k for r in search_by_reading(reading) for k in r["kanji"]]
    if spellings:
        messages.append("「%s」と読む表記の候補: %s" % (reading, "、".join(spellings[:10])))
    if len(messages) == 1:
        messages.append("珍しい名前の可能性があります。入力内容をご確認ください。")
    return messages


def main(argv: List[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    kanji, reading = argv[:2] if len(argv) >= 2 else ("翔太", "しょうだ")
    problems = check_given_name(kanji, reading)
    print("OK: %s（%s）" % (kanji, reading) if not problems else "\n".join(problems))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
