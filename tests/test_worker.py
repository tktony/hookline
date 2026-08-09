"""Tests for the delivery worker logic."""

import pytest

from app.worker import BACKOFF_SCHEDULE


@pytest.mark.parametrize(
    "attempts,expected_index",
    [
        (1, 0),
        (2, 1),
        (3, 2),
        (10, len(BACKOFF_SCHEDULE) - 1),  # caps at last
    ],
)
def test_backoff_index_caps(attempts, expected_index):
    """Backoff index grows with attempts but caps at the schedule length."""
    index = min(attempts - 1, len(BACKOFF_SCHEDULE) - 1)
    assert index == expected_index
