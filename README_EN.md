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

```python
from japanese_personal_name_dataset import load_dataset

# Load the dataset
man_names, woman_names = load_dataset()

# Access male names
print(man_names['たろう'])
# Output: {'en': 'tarou', 'kanji': ['太郎', '太朗', '大郎', ...]}

# Access female names
print(woman_names['はなこ'])
# Output: {'en': 'hanako', 'kanji': ['花子', '華子', ...]}

# Get a random name
import random
random_reading = random.choice(list(woman_names.keys()))
name_data = woman_names[random_reading]
print(f"Reading: {random_reading}")
print(f"Romaji: {name_data['en']}")
print(f"Kanji options: {', '.join(name_data['kanji'][:5])}")
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
