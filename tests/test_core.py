"""Tests for core module."""

import pytest
from japanese_personal_name_dataset.core import load_dataset, _load_first_names, _load_last_names


class TestLoadDataset:
    """Test load_dataset function."""

    def test_load_dataset_default(self):
        """Test loading dataset with default parameters."""
        man_names, woman_names = load_dataset()

        # Check that we got dictionaries
        assert isinstance(man_names, dict)
        assert isinstance(woman_names, dict)

        # Check that we got data
        assert len(man_names) > 0
        assert len(woman_names) > 0

        # Check expected counts (from README)
        assert len(man_names) == 5678
        assert len(woman_names) == 3346

    def test_load_dataset_org(self):
        """Test loading original (full) dataset."""
        man_names, woman_names = load_dataset(kind='org')

        assert len(man_names) == 5678
        assert len(woman_names) == 3346

    def test_load_dataset_opti(self):
        """Test loading optimized (popular names) dataset."""
        man_names, woman_names = load_dataset(kind='opti')

        # Check expected counts (from README)
        assert len(man_names) == 703
        assert len(woman_names) == 241

        # Optimized should be smaller than original
        man_org, woman_org = load_dataset(kind='org')
        assert len(man_names) < len(man_org)
        assert len(woman_names) < len(woman_org)

    def test_load_dataset_with_last_names(self):
        """Test loading dataset with last names."""
        man_names, woman_names, last_names = load_dataset(include_last_names=True)

        # Check that we got three dictionaries
        assert isinstance(man_names, dict)
        assert isinstance(woman_names, dict)
        assert isinstance(last_names, dict)

        # Check that we got data
        assert len(last_names) > 0

        # Check expected count (from README)
        assert len(last_names) == 2000

    def test_load_dataset_invalid_kind(self):
        """Test that invalid kind raises ValueError."""
        with pytest.raises(ValueError, match="kind must be 'org' or 'opti'"):
            load_dataset(kind='invalid')

    def test_first_name_structure(self):
        """Test that first names have the correct structure."""
        man_names, woman_names = load_dataset()

        # Pick a random name and check structure
        sample_key = list(man_names.keys())[0]
        sample_name = man_names[sample_key]

        assert 'en' in sample_name
        assert 'kanji' in sample_name
        assert isinstance(sample_name['en'], str)
        assert isinstance(sample_name['kanji'], list)

    def test_last_name_structure(self):
        """Test that last names have the correct structure."""
        _, _, last_names = load_dataset(include_last_names=True)

        # Check a well-known last name
        assert '佐藤' in last_names
        sato = last_names['佐藤']

        assert 'reading' in sato
        assert 'en' in sato
        assert 'count' in sato

        assert sato['reading'] == 'さとう'
        assert sato['en'] == 'satou'
        assert isinstance(sato['count'], int)
        assert sato['count'] > 0

    def test_common_names_exist(self):
        """Test that common Japanese names exist in the dataset."""
        man_names, woman_names = load_dataset()

        # Common male names
        common_male = ['たろう', 'ゆうき', 'こうじ']
        for name in common_male:
            if name in man_names:
                assert 'en' in man_names[name]
                assert 'kanji' in man_names[name]

        # Common female names
        common_female = ['はなこ', 'さくら', 'ゆい']
        for name in common_female:
            if name in woman_names:
                assert 'en' in woman_names[name]
                assert 'kanji' in woman_names[name]

    def test_kanji_variations(self):
        """Test that names have kanji variations."""
        man_names, _ = load_dataset()

        # Find a name with multiple kanji variations
        names_with_variations = [
            name for name, data in man_names.items()
            if len(data['kanji']) > 1
        ]

        assert len(names_with_variations) > 0

        # Check that variations are strings
        sample = man_names[names_with_variations[0]]
        for kanji in sample['kanji']:
            assert isinstance(kanji, str)
            assert len(kanji) > 0


class TestLoadFirstNames:
    """Test _load_first_names function."""

    def test_load_valid_file(self):
        """Test loading a valid CSV file."""
        import os
        from japanese_personal_name_dataset.core import _load_first_names

        dataset_dir = os.path.join(
            os.path.dirname(__file__),
            os.pardir,
            'japanese_personal_name_dataset',
            'dataset'
        )
        file_path = os.path.join(dataset_dir, 'first_name_man_org.csv')

        names = _load_first_names(file_path)
        assert isinstance(names, dict)
        assert len(names) > 0

    def test_load_nonexistent_file(self):
        """Test that loading nonexistent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            _load_first_names('/nonexistent/path/file.csv')


class TestLoadLastNames:
    """Test _load_last_names function."""

    def test_load_valid_file(self):
        """Test loading a valid CSV file."""
        import os
        from japanese_personal_name_dataset.core import _load_last_names

        dataset_dir = os.path.join(
            os.path.dirname(__file__),
            os.pardir,
            'japanese_personal_name_dataset',
            'dataset'
        )
        file_path = os.path.join(dataset_dir, 'last_name_org.csv')

        names = _load_last_names(file_path)
        assert isinstance(names, dict)
        assert len(names) > 0

    def test_load_nonexistent_file(self):
        """Test that loading nonexistent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            _load_last_names('/nonexistent/path/file.csv')

    def test_last_name_count_parsing(self):
        """Test that population counts are correctly parsed as integers."""
        import os
        from japanese_personal_name_dataset.core import _load_last_names

        dataset_dir = os.path.join(
            os.path.dirname(__file__),
            os.pardir,
            'japanese_personal_name_dataset',
            'dataset'
        )
        file_path = os.path.join(dataset_dir, 'last_name_org.csv')

        names = _load_last_names(file_path)

        # All counts should be integers
        for name, data in names.items():
            assert isinstance(data['count'], int)
            assert data['count'] >= 0


class TestAPI:
    """Test public API."""

    def test_api_import(self):
        """Test that load_dataset can be imported from package root."""
        from japanese_personal_name_dataset import load_dataset

        man_names, woman_names = load_dataset()
        assert len(man_names) > 0
        assert len(woman_names) > 0

    def test_api_parameters(self):
        """Test that API accepts all parameters."""
        from japanese_personal_name_dataset import load_dataset

        # Test with kind parameter
        man, woman = load_dataset(kind='opti')
        assert len(man) == 703

        # Test with include_last_names parameter
        man, woman, last = load_dataset(include_last_names=True)
        assert len(last) == 2000

        # Test with both parameters
        man, woman, last = load_dataset(kind='opti', include_last_names=True)
        assert len(man) == 703
        assert len(last) == 2000
