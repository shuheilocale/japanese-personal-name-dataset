"""Tests for helper utilities."""

import pytest
from japanese_personal_name_dataset import (
    generate_random_name,
    generate_random_full_name,
    search_by_reading,
    search_by_kanji,
    search_last_name,
    get_last_names,
    get_popular_names,
    is_valid_name,
    get_readings_for_kanji,
)


class TestRandomGeneration:
    """Test random name generation functions."""

    def test_generate_random_name_male(self):
        """Test generating random male name."""
        name = generate_random_name(gender='male')
        assert isinstance(name, str)
        assert len(name) > 0

    def test_generate_random_name_female(self):
        """Test generating random female name."""
        name = generate_random_name(gender='female')
        assert isinstance(name, str)
        assert len(name) > 0

    def test_generate_random_name_with_reading(self):
        """Test generating random name with reading."""
        kanji, reading = generate_random_name(gender='male', return_reading=True)
        assert isinstance(kanji, str)
        assert isinstance(reading, str)
        assert len(kanji) > 0
        assert len(reading) > 0

    def test_generate_random_name_opti(self):
        """Test generating random name from optimized dataset."""
        name = generate_random_name(gender='female', kind='opti')
        assert isinstance(name, str)
        assert len(name) > 0

    def test_generate_random_full_name(self):
        """Test generating random full name."""
        full_name = generate_random_full_name(gender='male')
        assert isinstance(full_name, str)
        assert ' ' in full_name  # Should contain space between last and first name

    def test_generate_random_full_name_with_reading(self):
        """Test generating random full name with reading."""
        kanji, reading = generate_random_full_name(gender='female', return_reading=True)
        assert isinstance(kanji, str)
        assert isinstance(reading, str)
        assert ' ' in kanji
        assert ' ' in reading


class TestSearchByReading:
    """Test search_by_reading function."""

    def test_search_exact_match(self):
        """Test exact match search by reading."""
        results = search_by_reading('たろう', gender='male')
        assert len(results) > 0
        assert results[0]['reading'] == 'たろう'
        assert results[0]['gender'] == 'male'
        assert 'kanji' in results[0]
        assert 'romaji' in results[0]

    def test_search_partial_match(self):
        """Test partial match (LIKE) search by reading."""
        results = search_by_reading('こう', partial=True, gender='male')
        assert len(results) > 0
        # All results should contain 'こう'
        for r in results:
            assert 'こう' in r['reading']

    def test_search_no_results(self):
        """Test search with no results."""
        results = search_by_reading('zzzzzzz')
        assert len(results) == 0

    def test_search_both_genders(self):
        """Test search without gender filter."""
        results = search_by_reading('ゆう', partial=True)
        # Should have both male and female names
        genders = {r['gender'] for r in results}
        assert len(genders) > 0  # At least one gender


class TestSearchByKanji:
    """Test search_by_kanji function."""

    def test_search_exact_match(self):
        """Test exact match search by kanji."""
        results = search_by_kanji('太郎')
        assert len(results) > 0
        for r in results:
            assert r['kanji'] == '太郎'
            assert 'reading' in r
            assert 'romaji' in r

    def test_search_partial_match(self):
        """Test partial match (LIKE) search by kanji."""
        results = search_by_kanji('子', partial=True, gender='female')
        assert len(results) > 0
        # All results should contain '子'
        for r in results:
            assert '子' in r['kanji']
            assert r['gender'] == 'female'

    def test_search_no_results(self):
        """Test search with no results."""
        results = search_by_kanji('鬱鬱鬱')
        assert len(results) == 0


class TestSearchLastName:
    """Test search_last_name function."""

    def test_search_by_kanji_exact(self):
        """Test exact match search by kanji."""
        results = search_last_name('佐藤', search_by='kanji')
        assert len(results) == 1
        assert results[0]['kanji'] == '佐藤'
        assert results[0]['reading'] == 'さとう'
        assert results[0]['romaji'] == 'satou'
        assert results[0]['count'] > 0

    def test_search_by_reading_exact(self):
        """Test exact match search by reading."""
        results = search_last_name('さとう', search_by='reading')
        assert len(results) > 0
        for r in results:
            assert r['reading'] == 'さとう'

    def test_search_partial_with_limit(self):
        """Test partial search with limit."""
        results = search_last_name('さ', search_by='reading', partial=True, limit=5)
        assert len(results) <= 5
        for r in results:
            assert 'さ' in r['reading']

    def test_results_sorted_by_count(self):
        """Test that results are sorted by population count."""
        results = search_last_name('た', search_by='reading', partial=True, limit=10)
        if len(results) > 1:
            # Check that results are in descending order of count
            for i in range(len(results) - 1):
                assert results[i]['count'] >= results[i + 1]['count']


class TestGetLastNames:
    """Test get_last_names function."""

    def test_get_all_last_names(self):
        """Test getting all last names."""
        results = get_last_names()
        assert len(results) == 2000

    def test_get_top_10(self):
        """Test getting top 10 last names."""
        results = get_last_names(limit=10)
        assert len(results) == 10
        # First one should be 佐藤 (most common)
        assert results[0]['kanji'] == '佐藤'

    def test_sorted_by_count(self):
        """Test that results are sorted by count."""
        results = get_last_names(limit=100)
        for i in range(len(results) - 1):
            assert results[i]['count'] >= results[i + 1]['count']

    def test_min_count_filter(self):
        """Test filtering by minimum count."""
        results = get_last_names(min_count=1000000)
        assert len(results) > 0
        for r in results:
            assert r['count'] >= 1000000


class TestGetPopularNames:
    """Test get_popular_names function."""

    def test_get_popular_male_names(self):
        """Test getting popular male names."""
        results = get_popular_names(gender='male', top=50)
        assert len(results) <= 50
        for r in results:
            assert 'reading' in r
            assert 'romaji' in r
            assert 'kanji' in r

    def test_get_popular_female_names(self):
        """Test getting popular female names."""
        results = get_popular_names(gender='female', top=30)
        assert len(results) <= 30


class TestValidation:
    """Test validation functions."""

    def test_is_valid_name_true(self):
        """Test valid name combination."""
        # We know たろう has 太郎 as one of its kanji
        result = is_valid_name('太郎', 'たろう')
        assert result is True

    def test_is_valid_name_false(self):
        """Test invalid name combination."""
        # 太郎 is not read as はなこ
        result = is_valid_name('太郎', 'はなこ')
        assert result is False

    def test_is_valid_name_with_gender(self):
        """Test validation with gender filter."""
        # Check if we can find any valid combination
        from japanese_personal_name_dataset.core import load_dataset
        man_names, _ = load_dataset()

        # Get first name
        first_reading = list(man_names.keys())[0]
        first_kanji = man_names[first_reading]['kanji'][0]

        # Should be valid for male
        assert is_valid_name(first_kanji, first_reading, gender='male') is True


class TestGetReadingsForKanji:
    """Test get_readings_for_kanji function."""

    def test_get_readings(self):
        """Test getting readings for a kanji."""
        # 太郎 should have at least one reading
        results = get_readings_for_kanji('太郎', gender='male')
        assert len(results) > 0
        for r in results:
            assert 'reading' in r
            assert 'romaji' in r

    def test_deduplicated_results(self):
        """Test that readings are deduplicated."""
        results = get_readings_for_kanji('太郎')
        readings = [r['reading'] for r in results]
        # No duplicates
        assert len(readings) == len(set(readings))


class TestCaching:
    """Test dataset caching."""

    def test_cache_works(self):
        """Test that caching doesn't break functionality."""
        # Call functions multiple times to test caching
        name1 = generate_random_name(gender='male')
        name2 = generate_random_name(gender='male')

        # Both should be valid strings
        assert isinstance(name1, str)
        assert isinstance(name2, str)

        # Search should work with cached data
        results = search_by_reading('たろう')
        assert len(results) > 0
