# Japanese Personal Name Dataset

[![Tests](https://github.com/shuheilocale/japanese-personal-name-dataset/actions/workflows/test.yml/badge.svg)](https://github.com/shuheilocale/japanese-personal-name-dataset/actions/workflows/test.yml)
[![PyPI version](https://badge.fury.io/py/japanese-personal-name-dataset.svg)](https://badge.fury.io/py/japanese-personal-name-dataset)
[![Python Versions](https://img.shields.io/pypi/pyversions/japanese-personal-name-dataset.svg)](https://pypi.org/project/japanese-personal-name-dataset/)
[![codecov](https://codecov.io/gh/shuheilocale/japanese-personal-name-dataset/branch/main/graph/badge.svg)](https://codecov.io/gh/shuheilocale/japanese-personal-name-dataset)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**English** | [日本語](https://github.com/shuheilocale/japanese-personal-name-dataset/blob/main/README_ja.md)

A dataset of Japanese personal names — first names and last names — with hiragana readings, romaji (Hepburn) and kanji spellings, plus a small, dependency-free Python API.

```python
>>> from japanese_personal_name_dataset import load_dataset
>>> man_names, woman_names = load_dataset()
>>> man_names['たろう']
{'en': 'tarou', 'kanji': ['多朗', '多郎', '太朗', '太郎', '大郎']}
```

## Contents

- [Features](#features)
- [Installation](#installation)
- [Quick start](#quick-start)
- [API reference](#api-reference)
- [Dataset](#dataset)
- [Data sources and quality](#data-sources-and-quality)
- [Examples](#examples)
- [Contributing](#contributing)
- [License](#license)

## Features

- **6,120 male** and **3,343 female** first-name readings, each with every known kanji spelling
- **1,999 last names** with estimated population
- Curated "optimized" subsets of popular names (702 male / 241 female)
- Romaji in Hepburn romanization
- Pure Python, no runtime dependencies, Python 3.8+
- Fully typed (`py.typed`), with results cached after the first load

## Installation

```bash
pip install japanese-personal-name-dataset
```

## Quick start

### Load the data

```python
from japanese_personal_name_dataset import load_dataset

# Full dataset (default)
man_names, woman_names = load_dataset()
print(woman_names['はなこ']['kanji'][:4])   # ['羽奈子', '羽那子', '英子', '花菜子']

# Popular names only
man_opti, woman_opti = load_dataset(kind='opti')
print(len(man_opti), len(woman_opti))      # 702 241

# Include last names
man_names, woman_names, last_names = load_dataset(include_last_names=True)
print(last_names['佐藤'])
# {'reading': 'さとう', 'en': 'satou', 'count': 1887000}
```

### Generate random names

```python
from japanese_personal_name_dataset import generate_random_name, generate_random_full_name

generate_random_name(gender='male')                       # e.g. '健一'
generate_random_full_name(gender='female', return_reading=True)
# e.g. ('川瀬 梅乃', 'かわせ うめの')
```

### Search and validate

```python
from japanese_personal_name_dataset import (
    search_by_reading, search_by_kanji, get_last_names, is_valid_name,
)

# Readings are hiragana; partial=True does a substring match
for r in search_by_reading('こう', partial=True, gender='male')[:3]:
    print(r['reading'], r['romaji'], r['kanji'][:3])
# いっこう ikkou ['一興', '一光', '一公'] ...

search_by_kanji('翔', partial=True, gender='male')       # names whose kanji contain 翔

for name in get_last_names(limit=3):                       # most common last names
    print(name['kanji'], name['reading'], f"{name['count']:,}")
# 佐藤 さとう 1,887,000 / 鈴木 すずき 1,806,000 / 高橋 たかはし 1,421,000

is_valid_name('太郎', 'たろう')                            # True
```

## API reference

| Function | Description |
| --- | --- |
| `load_dataset(kind='org', include_last_names=False)` | Returns `(man, woman)` or `(man, woman, last)` dictionaries |
| `generate_random_name(gender, kind, return_reading)` | Random first name |
| `generate_random_full_name(gender, kind, return_reading)` | Random "last first" full name |
| `search_by_reading(reading, gender, kind, partial)` | Find first names by hiragana reading |
| `search_by_kanji(kanji, gender, kind, partial)` | Find first names by kanji |
| `search_last_name(query, search_by='kanji', partial, limit)` | Find last names by kanji or reading |
| `get_last_names(limit, min_count)` | Last names ordered by estimated population |
| `get_popular_names(gender, top=50)` | Names from the optimized subset |
| `is_valid_name(kanji, reading, gender, kind)` | Whether a kanji/reading pair exists |
| `get_readings_for_kanji(kanji, gender, kind)` | All readings for a kanji spelling |
| `clear_cache()` | Drop cached data so the next call reloads the CSV files |

Return types are exported for type checkers: `FirstNameEntry`, `LastNameEntry`, `NameDict` and `LastNameDict`.

```python
from japanese_personal_name_dataset import load_dataset, NameDict

man, woman, last = load_dataset(include_last_names=True)  # typed as a 3-tuple
```

`load_dataset()` reads the CSV files once per process and returns fresh dictionaries on every call, so you can modify the results without affecting later calls.

## Dataset

The CSV files live in `japanese_personal_name_dataset/dataset/` (UTF-8, LF line endings).

| File | Contents | Rows |
| --- | --- | --- |
| `first_name_man_org.csv` | Male first names | 6,120 |
| `first_name_man_opti.csv` | Male first names, popular subset | 702 |
| `first_name_woman_org.csv` | Female first names | 3,343 |
| `first_name_woman_opti.csv` | Female first names, popular subset | 241 |
| `last_name_org.csv` | Last names | 1,999 |

### First names

`reading,romaji,kanji1,kanji2,...` — one row per reading, with a variable number of kanji spellings.

```csv
あい,ai,藍,愛,亜衣
```

### Last names

`kanji,estimated_population,reading,romaji`

```csv
佐藤,1887000,さとう,satou
```

### Kanji spellings per reading

| File | Mean | Median | Max |
| --- | --- | --- | --- |
| Male (full) | 9 | 2 | 446 |
| Male (popular) | 45 | 26 | 446 |
| Female (full) | 11 | 2 | 394 |
| Female (popular) | 50 | 32 | 287 |

## Data sources and quality

- Last-name population estimates are based on [名字由来net](https://myoji-yurai.net/prefectureRanking.htm).
- Since v0.3.0, first names are cross-checked and extended with [Wikidata](https://www.wikidata.org/) (CC0) and the [National Diet Library Web NDL Authorities](https://id.ndl.go.jp/auth/ndla/). [JMnedict](https://www.edrdg.org/enamdict/enamdict_doc.html) is used for verification only and is not redistributed.
- Every change goes through deterministic checks (format, duplicates, reading↔romaji consistency) and a reviewed findings ledger under [`qa/`](https://github.com/shuheilocale/japanese-personal-name-dataset/tree/main/qa/). Candidates that look like pen names, posthumous names or titles are excluded.

Romaji follows Hepburn romanization. Long vowels are written as in the kana (`ou`, `oo`), and the shortened form is also accepted by the checks.

The data is provided as is. If you find a wrong reading, romaji or spelling, please [open an issue](https://github.com/shuheilocale/japanese-personal-name-dataset/issues/new/choose).

## Examples

Runnable scripts are in [`examples/`](https://github.com/shuheilocale/japanese-personal-name-dataset/tree/main/examples/):

| Script | What it shows |
| --- | --- |
| [`basic_usage.py`](https://github.com/shuheilocale/japanese-personal-name-dataset/blob/main/examples/basic_usage.py) | Loading, lookups and the helper functions |
| [`generate_test_users.py`](https://github.com/shuheilocale/japanese-personal-name-dataset/blob/main/examples/generate_test_users.py) | Realistic fake user records as CSV or JSON for tests and seed data |
| [`form_validation.py`](https://github.com/shuheilocale/japanese-personal-name-dataset/blob/main/examples/form_validation.py) | Checking a name entered in a sign-up form and suggesting readings |
| [`name_statistics.py`](https://github.com/shuheilocale/japanese-personal-name-dataset/blob/main/examples/name_statistics.py) | Simple analysis: most common kanji, readings shared by both genders |
| [`web_api.py`](https://github.com/shuheilocale/japanese-personal-name-dataset/blob/main/examples/web_api.py) | A tiny JSON API with the standard library only |

Typical uses: test data and seed data for web apps, input validation, Japanese learning tools, games and data analysis.

## Contributing

Issues and pull requests are welcome. See [CONTRIBUTING.md](https://github.com/shuheilocale/japanese-personal-name-dataset/blob/main/CONTRIBUTING.md) for the development setup and how data corrections are reviewed.

## License

MIT License. See [LICENSE](https://github.com/shuheilocale/japanese-personal-name-dataset/blob/main/LICENSE).
