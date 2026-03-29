"""
Constants for the Music Assistant Integration.

This module contains configuration dataclasses and constants used throughout
the integration.

:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

from dataclasses import dataclass
from enum import StrEnum


@dataclass
class DeviceConfig:
    """
    Device configuration dataclass for a Music Assistant server.

    Holds all the configuration needed to connect to a Music Assistant server.
    The "device" in this integration is the MA server itself; individual MA
    players are represented as separate ucapi entities.
    """

    identifier: str
    """Unique identifier for this MA server instance (derived from server URL)."""

    name: str
    """Friendly name for this MA server (shown in the integration list)."""

    address: str
    """Base URL of the Music Assistant server (e.g. http://192.168.1.10:8095)."""

    token: str = ""
    """Long-lived access token for authentication (required for schema >= 28)."""


class SimpleCommands(StrEnum):
    """
    Additional simple commands not covered by standard media-player features.

    These appear in the UC Remote UI as pressable buttons.
    """

    CLEAR_QUEUE = "Clear Queue"
    ADD_TO_FAVORITES = "Add to Favorites"


# Map Music Assistant PlaybackState values to ucapi media_player States
MA_STATE_MAP: dict[str, str] = {
    "idle": "OFF",       # idle → treated as OFF (no active playback)
    "paused": "PAUSED",
    "playing": "PLAYING",
    "unknown": "UNKNOWN",
}

# Map Music Assistant RepeatMode values to ucapi RepeatMode values
MA_REPEAT_MAP: dict[str, str] = {
    "off": "OFF",
    "one": "ONE",
    "all": "ALL",
    "unknown": "OFF",
}

# Reverse map for ucapi → MA repeat
UC_REPEAT_MAP: dict[str, str] = {
    "OFF": "off",
    "ONE": "one",
    "ALL": "all",
}
