import pytest

from japanese_personal_name_dataset.core import load_dataset

class TestCore:


    def test_load_dataset(self):
        dataset = load_dataset()
        assert len(dataset) != 0
