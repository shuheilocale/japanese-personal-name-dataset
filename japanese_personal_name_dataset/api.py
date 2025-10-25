"""Public API for Japanese personal name dataset."""

from typing import Literal
from . import core


def load_dataset(
    kind: Literal['org', 'opti'] = 'org',
    include_last_names: bool = False
):
    """
    Load Japanese personal name dataset.

    This is a convenience wrapper around core.load_dataset().

    Args:
        kind: Dataset type to load. 'org' for original (full dataset),
              'opti' for optimized (curated popular names only).
              Default is 'org'.
        include_last_names: If True, also return last names data.
                           Default is False.

    Returns:
        If include_last_names is False:
            Tuple of (man_names, woman_names)
        If include_last_names is True:
            Tuple of (man_names, woman_names, last_names)

    Examples:
        >>> from japanese_personal_name_dataset import load_dataset
        >>> man_names, woman_names = load_dataset()
        >>> print(man_names['たろう'])
        {'en': 'tarou', 'kanji': ['太郎', '太朗', ...]}

        >>> # Load only popular names
        >>> man_names, woman_names = load_dataset(kind='opti')

        >>> # Include last names
        >>> man_names, woman_names, last_names = load_dataset(include_last_names=True)
        >>> print(last_names['佐藤'])
        {'reading': 'さとう', 'en': 'satou', 'count': 1887000}
    """
    return core.load_dataset(kind=kind, include_last_names=include_last_names)
