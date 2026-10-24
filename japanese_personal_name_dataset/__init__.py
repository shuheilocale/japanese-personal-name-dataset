from .api import load_dataset
from .helpers import (
    # Random generation
    generate_random_name,
    generate_random_full_name,
    # Search functions
    search_by_reading,
    search_by_kanji,
    search_last_name,
    # Getter functions
    get_last_names,
    get_popular_names,
    # Validation functions
    is_valid_name,
    get_readings_for_kanji,
)

from .core import clear_cache as _clear_core_cache
from .core import FirstNameEntry, LastNameEntry, NameDict, LastNameDict


def _package_version() -> str:
    try:
        from importlib.metadata import PackageNotFoundError, version
    except ImportError:  # pragma: no cover
        return "0.0.0"
    try:
        return version("japanese-personal-name-dataset")
    except PackageNotFoundError:  # pragma: no cover - ソースから直接 import した場合
        return "0.0.0"



def clear_cache() -> None:
    """読み込み済みデータのキャッシュをすべて破棄する。"""
    from . import helpers

    _clear_core_cache()
    helpers._CACHE.clear()


__version__ = _package_version()

__all__ = [
    'clear_cache',
    'FirstNameEntry',
    'LastNameEntry',
    'NameDict',
    'LastNameDict',
    'load_dataset',
    'generate_random_name',
    'generate_random_full_name',
    'search_by_reading',
    'search_by_kanji',
    'search_last_name',
    'get_last_names',
    'get_popular_names',
    'is_valid_name',
    'get_readings_for_kanji',
]