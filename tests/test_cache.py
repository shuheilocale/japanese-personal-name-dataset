"""読み込みキャッシュのテスト（#12）。"""
import builtins

import japanese_personal_name_dataset as jpnd
from japanese_personal_name_dataset import core


def test_second_load_does_not_reopen_files(monkeypatch):
    core.clear_cache()
    core.load_dataset(include_last_names=True)
    opened = []
    real_open = builtins.open

    def spy(*args, **kwargs):
        opened.append(args[0])
        return real_open(*args, **kwargs)

    monkeypatch.setattr(builtins, "open", spy)
    core.load_dataset(include_last_names=True)
    assert [p for p in opened if str(p).endswith(".csv")] == []


def test_mutating_result_does_not_leak_into_cache():
    man, _ = core.load_dataset()
    reading = next(iter(man))
    man[reading]["kanji"].append("改変")
    del man[next(iter(man))]
    man2, _ = core.load_dataset()
    assert "改変" not in man2[reading]["kanji"]
    assert reading in man2


def test_clear_cache_is_public_and_reloads():
    jpnd.clear_cache()
    man, _ = jpnd.load_dataset(kind="opti")
    assert len(man) > 0
