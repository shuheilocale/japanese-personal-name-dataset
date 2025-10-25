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

__version__ = '0.1.1'

__all__ = [
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