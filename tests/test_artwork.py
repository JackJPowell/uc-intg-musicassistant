"""Tests for Music Assistant artwork URL compatibility."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "intg-musicassistant"))

from artwork import get_image_url  # noqa: E402  pylint: disable=wrong-import-position


class FakeClient:  # pylint: disable=too-few-public-methods
    """Minimal Music Assistant client used by the artwork tests."""

    def __init__(self, schema_version: int) -> None:
        """Initialize a fake client for the requested server schema."""
        self.server_info = SimpleNamespace(
            schema_version=schema_version,
            base_url="http://music-assistant:8095",
        )

    @staticmethod
    def get_image_url(image: object, size: int = 0) -> str:
        """Return a recognizable legacy-client result."""
        path = getattr(image, "path")
        return f"legacy:{path}:{size}"


class ArtworkUrlTest(unittest.TestCase):
    """Verify schema-aware artwork URL generation."""

    def test_schema_31_reconstructs_proxy_id(self) -> None:
        """Schema 31 derives the proxy ID dropped by the old model package."""
        image = SimpleNamespace(
            path="provider://album/cover",
            provider="plex",
            remotely_accessible=False,
        )

        result = get_image_url(FakeClient(31), image, size=512)

        self.assertEqual(
            result,
            "http://music-assistant:8095/imageproxy/"
            "ab6473c9ad162a866e61d4beae056b7ded45a2801eb699f78b894fc8605910e6"
            "?size=512",
        )

    def test_schema_31_prefers_server_proxy_id(self) -> None:
        """A server-provided proxy ID takes precedence when available."""
        image = SimpleNamespace(
            path="provider://album/cover",
            provider="plex",
            proxy_id="opaque-id",
            remotely_accessible=False,
        )

        self.assertEqual(
            get_image_url(FakeClient(31), image),
            "http://music-assistant:8095/imageproxy/opaque-id?size=0",
        )

    def test_older_schema_delegates_to_client(self) -> None:
        """Older servers retain the client library's legacy behavior."""
        image = SimpleNamespace(
            path="provider://album/cover",
            provider="plex",
            proxy_id="opaque-id",
            remotely_accessible=False,
        )

        self.assertEqual(
            get_image_url(FakeClient(30), image),
            "legacy:provider://album/cover:0",
        )

    def test_remote_image_delegates_to_client(self) -> None:
        """Publicly reachable images retain the client's direct URL handling."""
        image = SimpleNamespace(
            path="https://example.com/cover.jpg",
            provider="url",
            proxy_id="opaque-id",
            remotely_accessible=True,
        )

        self.assertEqual(
            get_image_url(FakeClient(31), image),
            "legacy:https://example.com/cover.jpg:0",
        )


if __name__ == "__main__":
    unittest.main()
