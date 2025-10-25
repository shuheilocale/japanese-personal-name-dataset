"""Core module for loading Japanese personal name dataset."""

import csv
import os
from typing import Dict, List, Tuple, Literal, Union


NameDict = Dict[str, Dict[str, any]]
LastNameDict = Dict[str, Dict[str, any]]


def load_dataset(
    kind: Literal['org', 'opti'] = 'org',
    include_last_names: bool = False
) -> Union[Tuple[NameDict, NameDict], Tuple[NameDict, NameDict, LastNameDict]]:
    """
    Load Japanese personal name dataset.

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

        Each name dict has the structure:
        {
            'reading': {
                'en': 'romaji',
                'kanji': ['kanji1', 'kanji2', ...]
            }
        }

        Last names dict has the structure:
        {
            'kanji': {
                'reading': 'hiragana',
                'en': 'romaji',
                'count': estimated_population
            }
        }

    Examples:
        >>> man_names, woman_names = load_dataset()
        >>> print(man_names['たろう'])
        {'en': 'tarou', 'kanji': ['太郎', '太朗', ...]}

        >>> man_names, woman_names = load_dataset(kind='opti')
        >>> # Returns only popular names

        >>> man_names, woman_names, last_names = load_dataset(include_last_names=True)
        >>> print(last_names['佐藤'])
        {'reading': 'さとう', 'en': 'satou', 'count': 1887000}

    Raises:
        ValueError: If kind is not 'org' or 'opti'.
        FileNotFoundError: If dataset files are not found.
    """
    if kind not in ('org', 'opti'):
        raise ValueError(f"kind must be 'org' or 'opti', got '{kind}'")

    # Determine file suffix based on kind
    suffix = 'org' if kind == 'org' else 'opti'

    # Get dataset directory path
    dataset_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'dataset'
    )

    # Load male names
    man_names = _load_first_names(
        os.path.join(dataset_dir, f'first_name_man_{suffix}.csv')
    )

    # Load female names
    woman_names = _load_first_names(
        os.path.join(dataset_dir, f'first_name_woman_{suffix}.csv')
    )

    if include_last_names:
        # Load last names
        last_names = _load_last_names(
            os.path.join(dataset_dir, 'last_name_org.csv')
        )
        return man_names, woman_names, last_names

    return man_names, woman_names


def _load_first_names(file_path: str) -> NameDict:
    """
    Load first names from CSV file.

    Args:
        file_path: Path to the CSV file.

    Returns:
        Dictionary mapping hiragana reading to name data.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Dataset file not found: {file_path}")

    names = {}
    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 2:
                continue  # Skip invalid rows
            names[row[0]] = {
                'en': row[1],
                'kanji': row[2:] if len(row) > 2 else []
            }
    return names


def _load_last_names(file_path: str) -> LastNameDict:
    """
    Load last names from CSV file.

    Args:
        file_path: Path to the CSV file.

    Returns:
        Dictionary mapping kanji to last name data.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Dataset file not found: {file_path}")

    last_names = {}
    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 4:
                continue  # Skip invalid rows
            last_names[row[0]] = {
                'reading': row[2],
                'en': row[3],
                'count': int(row[1]) if row[1].isdigit() else 0
            }
    return last_names


if __name__ == '__main__':
    # Test loading
    print("Testing load_dataset()...")
    man, woman = load_dataset()
    print(f"Loaded {len(man)} male names, {len(woman)} female names")

    print("\nTesting load_dataset(kind='opti')...")
    man_opti, woman_opti = load_dataset(kind='opti')
    print(f"Loaded {len(man_opti)} male names (opti), {len(woman_opti)} female names (opti)")

    print("\nTesting load_dataset(include_last_names=True)...")
    man, woman, last = load_dataset(include_last_names=True)
    print(f"Loaded {len(last)} last names")

    print("\nSample data:")
    if 'たろう' in man:
        print(f"たろう: {man['たろう']}")
    if '佐藤' in last:
        print(f"佐藤: {last['佐藤']}")
