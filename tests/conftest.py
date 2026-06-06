"""Shared test fixtures."""
import pytest

@pytest.fixture
def sample_entity():
    return {
        "type": "core:Organization",
        "label": "Test Organization",
        "properties": {"revenue": "100M"},
    }
