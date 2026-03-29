"""
Music Assistant Setup Flow.

Presents a form asking for:
  - Music Assistant server URL  (e.g. http://192.168.1.10:8095)
  - Optional long-lived authentication token

On submission the setup flow connects briefly to the MA server to verify the
connection and retrieve the server_id, then returns a DeviceConfig.

:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from const import DeviceConfig
from music_assistant_client import MusicAssistantClient
from ucapi import IntegrationSetupError, RequestUserInput, SetupError
from ucapi_framework import BaseSetupFlow

_LOG = logging.getLogger(__name__)


class MusicAssistantSetupFlow(BaseSetupFlow[DeviceConfig]):
    """Setup flow for a Music Assistant server."""

    def get_additional_discovery_fields(self) -> list[dict]:
        """Add an optional auth token field to the discovery selection screen."""
        return [
            {
                "field": {"text": {"value": ""}},
                "id": "token",
                "label": {"en": "Access Token (leave blank if not required)"},
            }
        ]

    def get_manual_entry_form(self) -> RequestUserInput:
        """Return the setup form shown to the user."""
        return RequestUserInput(
            {"en": "Music Assistant Server Setup"},
            [
                {
                    "id": "info",
                    "label": {"en": "Connect to Music Assistant"},
                    "field": {
                        "label": {
                            "value": {
                                "en": (
                                    "Enter the URL of your Music Assistant server and, "
                                    "if authentication is enabled, a long-lived access token."
                                ),
                            }
                        }
                    },
                },
                {
                    "field": {"text": {"value": "http://"}},
                    "id": "address",
                    "label": {"en": "Server URL (e.g. http://192.168.1.10:8095)"},
                },
                {
                    "field": {"text": {"value": ""}},
                    "id": "token",
                    "label": {"en": "Access Token (leave blank if not required)"},
                },
            ],
        )

    async def query_device(
        self, input_values: dict[str, Any]
    ) -> DeviceConfig | SetupError | RequestUserInput:
        """
        Validate user input, connect to MA, and return a DeviceConfig.

        :param input_values: Form values submitted by the user
        :return: DeviceConfig on success, SetupError on failure
        """
        address = input_values.get("address", "").strip().rstrip("/")
        token = input_values.get("token", "").strip() or None

        if not address or address == "http://":
            _LOG.warning("No server URL provided – re-displaying form")
            return self.get_manual_entry_form()

        _LOG.info("Verifying Music Assistant connection: %s", address)

        client = MusicAssistantClient(address, None, token=token)
        try:
            init_ready = asyncio.Event()
            task = asyncio.ensure_future(client.start_listening(init_ready=init_ready))
            try:
                await asyncio.wait_for(init_ready.wait(), timeout=15)
            except asyncio.TimeoutError as exc:
                task.cancel()
                _LOG.error("Timeout connecting to MA at %s", address)
                raise TimeoutError from exc

            server_info = client.server_info
            if server_info is None:
                raise ConnectionError("No server info received")

            server_id = server_info.server_id.replace("-", "_")
            name = f"Music Assistant ({address})"

            _LOG.info("Connected to MA server %s (id=%s)", address, server_id)

            return DeviceConfig(
                identifier=server_id,
                name=name,
                address=address,
                token=token or "",
            )

        except ConnectionError as exc:
            _LOG.error("Connection refused to MA at %s: %s", address, exc)
            return SetupError(IntegrationSetupError.CONNECTION_REFUSED)

        except TimeoutError:
            _LOG.error("Timeout connecting to MA at %s", address)
            return SetupError(IntegrationSetupError.TIMEOUT)

        except Exception as exc:  # pylint: disable=broad-except
            _LOG.error("Unexpected error connecting to MA at %s: %s", address, exc)
            return SetupError(IntegrationSetupError.CONNECTION_REFUSED)

        finally:
            try:
                await client.disconnect()
            except Exception:  # pylint: disable=broad-except
                pass
