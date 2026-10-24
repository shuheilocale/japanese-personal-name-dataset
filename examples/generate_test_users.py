"""テスト・シード用のダミーユーザーを生成する。

    python examples/generate_test_users.py --count 5 --format json --seed 42
    python examples/generate_test_users.py --count 100 --format csv > users.csv

姓は推定人数で重み付けして選ぶので、実際の分布に近い名簿になる。
"""
import argparse
import csv
import json
import random
import sys
from typing import Dict, List

from japanese_personal_name_dataset import load_dataset


def generate_users(count: int, seed: int, kind: str = "opti") -> List[Dict[str, str]]:
    rng = random.Random(seed)
    man, woman, last = load_dataset(kind=kind, include_last_names=True)  # type: ignore[call-overload]
    surnames = list(last.items())
    weights = [max(info["count"], 1) for _, info in surnames]
    users = []
    for i in range(1, count + 1):
        gender = rng.choice(["male", "female"])
        names = man if gender == "male" else woman
        reading = rng.choice(sorted(names))
        given_kanji = rng.choice(names[reading]["kanji"])
        family_kanji, family = rng.choices(surnames, weights=weights)[0]
        users.append({
            "id": str(i),
            "family_name": family_kanji,
            "given_name": given_kanji,
            "family_name_kana": family["reading"],
            "given_name_kana": reading,
            "romaji": "%s %s" % (names[reading]["en"].capitalize(), family["en"].capitalize()),
            "gender": gender,
            "email": "%s.%s%d@example.com" % (names[reading]["en"], family["en"], i),
        })
    return users


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--format", choices=["csv", "json"], default="csv")
    args = parser.parse_args()
    users = generate_users(args.count, args.seed)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.format == "json":
        print(json.dumps(users, ensure_ascii=False, indent=2))
    else:
        writer = csv.DictWriter(sys.stdout, fieldnames=list(users[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(users)
    return 0


if __name__ == "__main__":
    sys.exit(main())
