"""Helper utilities for Japanese personal name dataset."""

import random
from typing import List, Dict, Literal, Optional, Tuple
from .core import load_dataset, NameDict, LastNameDict


# Cache for loaded datasets to avoid repeated file reads
_CACHE = {}


def _get_cached_dataset(kind: Literal['org', 'opti'] = 'org', include_last_names: bool = False):
    """Get dataset from cache or load it."""
    cache_key = (kind, include_last_names)
    if cache_key not in _CACHE:
        _CACHE[cache_key] = load_dataset(kind=kind, include_last_names=include_last_names)
    return _CACHE[cache_key]


# Random Generation Functions

def generate_random_name(
    gender: Literal['male', 'female'] = 'male',
    kind: Literal['org', 'opti'] = 'org',
    return_reading: bool = False
) -> str | Tuple[str, str]:
    """
    Generate a random Japanese first name.

    Args:
        gender: 'male' or 'female'
        kind: 'org' for full dataset, 'opti' for popular names only
        return_reading: If True, return (kanji, reading) tuple

    Returns:
        Random name in kanji, or (kanji, reading) tuple if return_reading=True

    Examples:
        >>> name = generate_random_name(gender='male')
        >>> print(name)
        'Taro'

        >>> kanji, reading = generate_random_name(gender='female', return_reading=True)
        >>> print(f"{kanji} ({reading})")
        'Hanako (hanako)'
    """
    man_names, woman_names = _get_cached_dataset(kind=kind)
    names = man_names if gender == 'male' else woman_names

    reading = random.choice(list(names.keys()))
    kanji = random.choice(names[reading]['kanji'])

    if return_reading:
        return kanji, reading
    return kanji


def generate_random_full_name(
    gender: Literal['male', 'female'] = 'female',
    kind: Literal['org', 'opti'] = 'org',
    return_reading: bool = False
) -> str | Tuple[str, str]:
    """
    Generate a random Japanese full name (last name + first name).

    Args:
        gender: 'male' or 'female' for the first name
        kind: 'org' for full dataset, 'opti' for popular names only
        return_reading: If True, return (kanji, reading) tuple

    Returns:
        Random full name in kanji, or (kanji, reading) tuple if return_reading=True
    """
    man_names, woman_names, last_names = _get_cached_dataset(kind=kind, include_last_names=True)
    first_names = man_names if gender == 'male' else woman_names

    # Get random last name
    last_kanji = random.choice(list(last_names.keys()))
    last_reading = last_names[last_kanji]['reading']

    # Get random first name
    first_reading = random.choice(list(first_names.keys()))
    first_kanji = random.choice(first_names[first_reading]['kanji'])

    full_name_kanji = f"{last_kanji} {first_kanji}"

    if return_reading:
        full_name_reading = f"{last_reading} {first_reading}"
        return full_name_kanji, full_name_reading
    return full_name_kanji


# Search Functions

def search_by_reading(
    reading: str,
    gender: Optional[Literal['male', 'female']] = None,
    kind: Literal['org', 'opti'] = 'org',
    partial: bool = False
) -> List[Dict[str, any]]:
    """
    Search names by hiragana reading.

    Args:
        reading: Hiragana reading to search for
        gender: If specified, search only male or female names
        kind: 'org' for full dataset, 'opti' for popular names only
        partial: If True, performs LIKE search (partial match)

    Returns:
        List of matching names with their data
    """
    man_names, woman_names = _get_cached_dataset(kind=kind)
    results = []

    def search_in_dict(names: NameDict, gender_label: str):
        for name_reading, data in names.items():
            if partial:
                if reading in name_reading:
                    results.append({
                        'reading': name_reading,
                        'romaji': data['en'],
                        'kanji': data['kanji'],
                        'gender': gender_label
                    })
            else:
                if name_reading == reading:
                    results.append({
                        'reading': name_reading,
                        'romaji': data['en'],
                        'kanji': data['kanji'],
                        'gender': gender_label
                    })

    if gender is None or gender == 'male':
        search_in_dict(man_names, 'male')
    if gender is None or gender == 'female':
        search_in_dict(woman_names, 'female')

    return results


def search_by_kanji(
    kanji: str,
    gender: Optional[Literal['male', 'female']] = None,
    kind: Literal['org', 'opti'] = 'org',
    partial: bool = False
) -> List[Dict[str, any]]:
    """
    Search names by kanji.

    Args:
        kanji: Kanji to search for
        gender: If specified, search only male or female names
        kind: 'org' for full dataset, 'opti' for popular names only
        partial: If True, performs LIKE search (partial match)

    Returns:
        List of matching names with their data
    """
    man_names, woman_names = _get_cached_dataset(kind=kind)
    results = []

    def search_in_dict(names: NameDict, gender_label: str):
        for reading, data in names.items():
            for k in data['kanji']:
                if partial:
                    if kanji in k:
                        results.append({
                            'reading': reading,
                            'romaji': data['en'],
                            'kanji': k,
                            'gender': gender_label
                        })
                else:
                    if k == kanji:
                        results.append({
                            'reading': reading,
                            'romaji': data['en'],
                            'kanji': k,
                            'gender': gender_label
                        })

    if gender is None or gender == 'male':
        search_in_dict(man_names, 'male')
    if gender is None or gender == 'female':
        search_in_dict(woman_names, 'female')

    return results


def search_last_name(
    query: str,
    search_by: Literal['kanji', 'reading'] = 'kanji',
    partial: bool = False,
    limit: Optional[int] = None
) -> List[Dict[str, any]]:
    """
    Search last names.

    Args:
        query: Search query (kanji or hiragana)
        search_by: 'kanji' or 'reading'
        partial: If True, performs LIKE search (partial match)
        limit: Maximum number of results to return

    Returns:
        List of matching last names with their data
    """
    _, _, last_names = _get_cached_dataset(include_last_names=True)
    results = []

    for kanji, data in last_names.items():
        match = False

        if search_by == 'kanji':
            if partial:
                match = query in kanji
            else:
                match = kanji == query
        else:  # search_by == 'reading'
            if partial:
                match = query in data['reading']
            else:
                match = data['reading'] == query

        if match:
            results.append({
                'kanji': kanji,
                'reading': data['reading'],
                'romaji': data['en'],
                'count': data['count']
            })

    # Sort by population count (descending)
    results.sort(key=lambda x: x['count'], reverse=True)

    if limit:
        results = results[:limit]

    return results


# Getter Functions

def get_last_names(
    limit: Optional[int] = None,
    min_count: Optional[int] = None
) -> List[Dict[str, any]]:
    """
    Get last names sorted by population count.

    Args:
        limit: Maximum number of results to return
        min_count: Minimum population count filter

    Returns:
        List of last names sorted by population (descending)
    """
    _, _, last_names = _get_cached_dataset(include_last_names=True)
    results = []

    for kanji, data in last_names.items():
        if min_count and data['count'] < min_count:
            continue

        results.append({
            'kanji': kanji,
            'reading': data['reading'],
            'romaji': data['en'],
            'count': data['count']
        })

    # Sort by population count (descending)
    results.sort(key=lambda x: x['count'], reverse=True)

    if limit:
        results = results[:limit]

    return results


def get_popular_names(
    gender: Literal['male', 'female'] = 'male',
    top: int = 50
) -> List[Dict[str, any]]:
    """
    Get popular names from the optimized dataset.

    Args:
        gender: 'male' or 'female'
        top: Number of names to return

    Returns:
        List of popular names
    """
    man_names, woman_names = _get_cached_dataset(kind='opti')
    names = man_names if gender == 'male' else woman_names

    results = []
    for reading, data in list(names.items())[:top]:
        results.append({
            'reading': reading,
            'romaji': data['en'],
            'kanji': data['kanji']
        })

    return results


# Validation Functions

def is_valid_name(
    kanji: str,
    reading: str,
    gender: Optional[Literal['male', 'female']] = None,
    kind: Literal['org', 'opti'] = 'org'
) -> bool:
    """
    Validate if a kanji-reading pair exists in the dataset.

    Args:
        kanji: Kanji to validate
        reading: Hiragana reading to validate
        gender: If specified, check only male or female names
        kind: 'org' for full dataset, 'opti' for popular names only

    Returns:
        True if the kanji-reading pair exists, False otherwise
    """
    man_names, woman_names = _get_cached_dataset(kind=kind)

    def check_in_dict(names: NameDict) -> bool:
        if reading in names:
            return kanji in names[reading]['kanji']
        return False

    if gender is None:
        return check_in_dict(man_names) or check_in_dict(woman_names)
    elif gender == 'male':
        return check_in_dict(man_names)
    else:
        return check_in_dict(woman_names)


def get_readings_for_kanji(
    kanji: str,
    gender: Optional[Literal['male', 'female']] = None,
    kind: Literal['org', 'opti'] = 'org'
) -> List[Dict[str, str]]:
    """
    Get all possible readings for a given kanji name.

    Args:
        kanji: Kanji name
        gender: If specified, search only male or female names
        kind: 'org' for full dataset, 'opti' for popular names only

    Returns:
        List of possible readings with romaji
    """
    results = search_by_kanji(kanji, gender=gender, kind=kind, partial=False)

    # Deduplicate by reading
    seen = set()
    unique_results = []
    for r in results:
        if r['reading'] not in seen:
            seen.add(r['reading'])
            unique_results.append({
                'reading': r['reading'],
                'romaji': r['romaji']
            })

    return unique_results
