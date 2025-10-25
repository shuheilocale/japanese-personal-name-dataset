# Japanese Personal Name Dataset

[![Tests](https://github.com/shuheilocale/japanese-personal-name-dataset/actions/workflows/test.yml/badge.svg)](https://github.com/shuheilocale/japanese-personal-name-dataset/actions/workflows/test.yml)
[![PyPI version](https://badge.fury.io/py/japanese-personal-name-dataset.svg)](https://badge.fury.io/py/japanese-personal-name-dataset)
[![Python Versions](https://img.shields.io/pypi/pyversions/japanese-personal-name-dataset.svg)](https://pypi.org/project/japanese-personal-name-dataset/)
[![codecov](https://codecov.io/gh/shuheilocale/japanese-personal-name-dataset/branch/main/graph/badge.svg)](https://codecov.io/gh/shuheilocale/japanese-personal-name-dataset)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A comprehensive dataset of Japanese personal names (first names and last names) with hiragana readings, romaji (Hepburn romanization), and kanji variations.

[日本語README](https://github.com/shuheilocale/japanese-personal-name-dataset/blob/main/README.md)

## Features

- 5,678 male first names (703 optimized/popular names)
- 3,346 female first names (241 optimized/popular names)
- 2,000 last names with estimated population data
- Multiple kanji variations for each reading
- Romaji (Hepburn) transliterations
- Easy-to-use Python API

## Installation

```bash
pip install japanese-personal-name-dataset
```

Or install from source:

```bash
git clone https://github.com/shuheilocale/japanese-personal-name-dataset.git
cd japanese-personal-name-dataset
pip install -e .
```

## Dataset Structure

The dataset consists of the following CSV files:

1. `first_name_man_org.csv` - Male first names (original)
2. `first_name_man_opti.csv` - Male first names (optimized/popular)
3. `first_name_woman_org.csv` - Female first names (original)
4. `first_name_woman_opti.csv` - Female first names (optimized/popular)
5. `last_name_org.csv` - Last names

**Optimized** datasets contain curated popular names only.

## CSV Format

### First Names

Each row represents one name reading:
- Column 1: Hiragana reading
- Column 2: Romaji (Hepburn)
- Column 3+: Kanji variations (variable number)

Example:
```
あい,ai,藍,愛,亜衣
```

### Last Names

Each row represents one last name:
- Column 1: Kanji
- Column 2: Estimated population
- Column 3: Hiragana reading
- Column 4: Romaji (Hepburn)

Example:
```
佐藤,1887000,さとう,satou
```

## Usage

### Basic Usage

```python
from japanese_personal_name_dataset import load_dataset

# Load the dataset (default: full version)
man_names, woman_names = load_dataset()

# Access male names
print(man_names['たろう'])
# Output: {'en': 'tarou', 'kanji': ['多朗', '多郎', '太朗', '太郎', '大郎']}

# Access female names
print(woman_names['はなこ'])
# Output: {'en': 'hanako', 'kanji': ['花子', '華子', ...]}
```

### Load Optimized Dataset (Popular Names Only)

```python
# Load only popular names
man_names, woman_names = load_dataset(kind='opti')
print(f"Male names: {len(man_names)} types")    # 703 types
print(f"Female names: {len(woman_names)} types")  # 241 types
```

### Include Last Names

```python
# Load with last names
man_names, woman_names, last_names = load_dataset(include_last_names=True)

# Access last name data
print(last_names['佐藤'])
# Output: {'reading': 'さとう', 'en': 'satou', 'count': 1887000}
```

### Using Utility Functions

```python
from japanese_personal_name_dataset import (
    generate_random_name,
    generate_random_full_name,
    search_by_reading,
    search_by_kanji,
    get_last_names,
    is_valid_name,
)

# Generate random name
name = generate_random_name(gender='male')
print(name)  # Example: Taro

# Generate random full name with reading
full_name, reading = generate_random_full_name(gender='female', return_reading=True)
print(f"{full_name} ({reading})")  # Example: Sato Hanako (satou hanako)

# Search by reading (partial match / LIKE search)
results = search_by_reading('kou', partial=True, gender='male')
for r in results[:3]:
    print(f"{r['reading']} ({r['romaji']}): {', '.join(r['kanji'][:3])}")
# Example: kouji (kouji): Koji, Takaji, Yukiharu

# Search by kanji (names containing '子')
results = search_by_kanji('子', partial=True, gender='female')
print(f"Names containing '子': {len(results)} results")

# Get top 10 most common last names
top_10 = get_last_names(limit=10)
for i, name in enumerate(top_10, 1):
    print(f"{i}. {name['kanji']} ({name['reading']}) - {name['count']:,} people")

# Validate name
if is_valid_name('太郎', 'たろう'):
    print("太郎 (tarou) is a valid combination")
```

## Use Cases

- Test data generation for web applications
- Name validation and normalization
- Japanese language learning tools
- Data science and statistical analysis
- Game development (character name generation)

## Dataset Statistics

### Number of Names

| Type | Count |
|------|-------|
| Male first names (original) | 5,678 |
| Male first names (optimized) | 703 |
| Female first names (original) | 3,346 |
| Female first names (optimized) | 241 |
| Last names | 2,000 |

### Kanji Variations (per reading)

For original datasets:
- Male names: avg 10 variations, max 447
- Female names: avg 11 variations, max 398

For optimized datasets:
- Male names: avg 45 variations, max 447
- Female names: avg 51 variations, max 291

## Data Format

- File format: CSV
- Character encoding: UTF-8
- Line endings: LF
- Romaji system: Hepburn romanization

## License

MIT License

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## References

- [名字由来net (Myoji Yurai Net)](https://myoji-yurai.net/prefectureRanking.htm)

## Disclaimer

While we strive for accuracy, there may be errors in the romanization or kanji variations. This dataset is provided as-is for informational purposes.
