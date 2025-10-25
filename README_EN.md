# Japanese Personal Name Dataset

A comprehensive dataset of Japanese personal names (first names and last names) with hiragana readings, romaji (Hepburn romanization), and kanji variations.

[日本語README](README.md)

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

### Generate Random Names

```python
import random

# Generate random male name
reading = random.choice(list(man_names.keys()))
kanji = random.choice(man_names[reading]['kanji'])
print(f"{kanji} ({reading})")

# Generate random full name
last_kanji = random.choice(list(last_names.keys()))
first_reading = random.choice(list(woman_names.keys()))
first_kanji = random.choice(woman_names[first_reading]['kanji'])
print(f"{last_kanji} {first_kanji}")
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
