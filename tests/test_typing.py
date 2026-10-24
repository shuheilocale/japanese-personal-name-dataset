"""型ヒント・パッケージメタデータのテスト（#11）。"""
import os
import re

import japanese_personal_name_dataset as jpnd
from japanese_personal_name_dataset import core

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _pyproject_version():
    with open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8") as f:
        return re.search(r'^version = "([^"]+)"', f.read(), re.M).group(1)


def test_version_matches_pyproject():
    assert jpnd.__version__ == _pyproject_version()


def test_py_typed_marker_is_shipped():
    assert os.path.exists(os.path.join(os.path.dirname(jpnd.__file__), "py.typed"))


def test_entry_types_describe_loaded_data():
    man, _woman, last = core.load_dataset(include_last_names=True)
    entry = next(iter(man.values()))
    assert set(entry) == set(core.FirstNameEntry.__annotations__)
    assert set(next(iter(last.values()))) == set(core.LastNameEntry.__annotations__)
