"""load_dataset() の初回（CSV 読み込み）とキャッシュ後の所要時間を測る（#12）。

    python benchmarks/bench_load.py
"""
import os
import sys
import timeit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from japanese_personal_name_dataset import clear_cache, load_dataset  # noqa: E402


def main() -> None:
    n = 20
    cold = timeit.timeit(lambda: (clear_cache(), load_dataset(include_last_names=True)), number=n) / n
    load_dataset(include_last_names=True)
    warm = timeit.timeit(lambda: load_dataset(include_last_names=True), number=n) / n
    print("初回（CSV 読み込み込み）: %.1f ms" % (cold * 1000))
    print("2 回目以降（キャッシュ）: %.1f ms" % (warm * 1000))
    print("短縮率: %.0f%%" % ((1 - warm / cold) * 100))


if __name__ == "__main__":
    main()
