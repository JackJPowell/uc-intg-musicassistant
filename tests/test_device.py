"""Tests for Music Assistant device state translation."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "intg-musicassistant"))

# pylint: disable=import-error,wrong-import-position
from device import Device  # noqa: E402


class FakeDevice:  # pylint: disable=too-few-public-methods
    """Minimal Device stand-in for media information tests."""

    def __init__(self, queue: object) -> None:
        """Initialize the fake with a player queue."""
        self._queue = queue
        self._client = None

    def get_queue(self, _player_id: str) -> object:
        """Return the configured queue."""
        return self._queue


class MediaInfoTest(unittest.TestCase):
    """Verify Music Assistant queue timing translation."""

    def test_position_includes_source_timestamp(self) -> None:
        """Position and update time remain a consistent extrapolation pair."""
        queue = SimpleNamespace(
            current_item=SimpleNamespace(
                media_item=None,
                name="Test track",
                image=None,
                media_type=SimpleNamespace(value="track"),
            ),
            elapsed_time=125.9,
            elapsed_time_last_updated=1767225600.125,
        )

        info = Device.get_media_info(FakeDevice(queue), "player-id")

        self.assertEqual(info["media_position"], 125)
        self.assertEqual(
            info["media_position_updated_at"],
            "2026-01-01T00:00:00.125Z",
        )


if __name__ == "__main__":
    unittest.main()
