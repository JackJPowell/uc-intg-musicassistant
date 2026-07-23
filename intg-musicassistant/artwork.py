"""
Music Assistant artwork URL compatibility helpers.

:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from music_assistant_client import MusicAssistantClient


def get_image_url(client: MusicAssistantClient, image: Any, size: int = 0) -> str:
    """
    Return an artwork URL supported by the connected Music Assistant server.

    Music Assistant schema 31 removed the legacy query-based image proxy.
    ``music-assistant-client`` 1.4.3 supports the replacement endpoint but
    requires Python 3.12, while Unfolded Circle's release builder uses 3.11.
    This backports its canonical proxy URL handling and delegates all other
    cases to the client library.
    """
    server_info = client.server_info
    schema_version = getattr(server_info, "schema_version", 0)

    if not getattr(image, "remotely_accessible", False) and schema_version >= 31:
        proxy_id = getattr(image, "proxy_id", None)
        if not proxy_id:
            provider = getattr(image, "provider")
            path = getattr(image, "path")
            raw_image_id = f"{provider}/{path}".encode()
            proxy_id = hashlib.sha256(raw_image_id, usedforsecurity=False).hexdigest()
        base_url = server_info.base_url.rstrip("/")
        return f"{base_url}/imageproxy/{proxy_id}?size={size}"

    return client.get_image_url(image, size)
