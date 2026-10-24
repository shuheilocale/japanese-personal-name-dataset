"""基本的な使い方: データの読み込み、参照、ヘルパー関数。

    python examples/basic_usage.py
"""
from japanese_personal_name_dataset import (
    generate_random_full_name,
    get_last_names,
    get_readings_for_kanji,
    is_valid_name,
    load_dataset,
    search_by_reading,
)


def main() -> None:
    man, woman, last = load_dataset(include_last_names=True)
    print("男性の名: %d 読み / 女性の名: %d 読み / 姓: %d 種類" % (len(man), len(woman), len(last)))

    print("\nたろう ->", man["たろう"])
    print("佐藤   ->", last["佐藤"])

    print("\n「こう」で始まる男性の名（先頭 5 件）:")
    for r in [r for r in search_by_reading("こう", partial=True, gender="male") if r["reading"].startswith("こう")][:5]:
        print("  %s (%s): %s" % (r["reading"], r["romaji"], "・".join(r["kanji"][:4])))

    print("\n「翔」と書く名の読み:", [r["reading"] for r in get_readings_for_kanji("翔")])
    print("太郎=たろう は存在する？", is_valid_name("太郎", "たろう"))

    print("\n人数の多い姓トップ 5:")
    for i, n in enumerate(get_last_names(limit=5), 1):
        print("  %d. %s（%s）%s 人" % (i, n["kanji"], n["reading"], format(n["count"], ",")))

    name, reading = generate_random_full_name(gender="female", return_reading=True)
    print("\nランダムな女性のフルネーム: %s（%s）" % (name, reading))


if __name__ == "__main__":
    main()
