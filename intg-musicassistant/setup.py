"""
Music Assistant Setup Flow.

Two-step setup:
  Step 1 – Server URL (port 8095 assumed if omitted)
  Step 2 – Authentication: either username + password (we obtain a long-lived
            token on the user's behalf) or a pre-existing long-lived token.

On successful authentication the flow connects briefly to verify the server
and retrieve the server_id, then returns a DeviceConfig.

:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import urlparse, urlunparse

from const import DeviceConfig
import aiohttp
from music_assistant_client import MusicAssistantClient
from music_assistant_client.exceptions import CannotConnect
from ucapi import RequestUserInput, SetupError
from ucapi_framework import BaseSetupFlow

_LOG = logging.getLogger(__name__)

_DEFAULT_PORT = 8095


class MusicAssistantSetupFlow(BaseSetupFlow[DeviceConfig]):
    """Two-step setup flow for a Music Assistant server."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Persists the validated address between step 1 and step 2
        self._pending_address: str = ""

    # -------------------------------------------------------------------------
    # Step 1 – Server URL
    # -------------------------------------------------------------------------

    def get_manual_entry_form(self) -> RequestUserInput:
        """Return the first setup screen: just the server address."""
        return RequestUserInput(
            {"en": "Music Assistant – Server Address"},
            [
                {
                    "id": "info",
                    "label": {"en": "Step 1 of 2 – Server address"},
                    "field": {
                        "label": {
                            "value": {
                                "en": (
                                    "Enter the address of your Music Assistant server. "
                                    "If you omit the port, 8095 will be used."
                                ),
                            }
                        }
                    },
                },
                {
                    "field": {"text": {"value": "http://"}},
                    "id": "address",
                    "label": {
                        "en": "Server URL (e.g. http://192.168.1.10 or http://192.168.1.10:8095)"
                    },
                },
            ],
        )

    # -------------------------------------------------------------------------
    # Step 2 – Credentials
    # -------------------------------------------------------------------------

    def _credentials_form(self, address: str) -> RequestUserInput:
        """Return the second setup screen: username/password or token."""
        return RequestUserInput(
            {"en": "Music Assistant – Authentication"},
            [
                {
                    "id": "info",
                    "label": {"en": "Step 2 of 2 – Authentication"},
                    "field": {
                        "label": {
                            "value": {
                                "en": (
                                    f"Connecting to: {address}\n\n"
                                    "Music Assistant requires authentication. "
                                    "Enter your username and password and a long-lived "
                                    "token will be created automatically. "
                                    "Alternatively, paste an existing long-lived access token."
                                ),
                            }
                        }
                    },
                },
                {
                    "field": {"text": {"value": ""}},
                    "id": "username",
                    "label": {"en": "Username"},
                },
                {
                    "field": {"text": {"value": ""}},
                    "id": "password",
                    "label": {"en": "Password"},
                },
                {
                    "id": "divider",
                    "label": {"en": "— or —"},
                    "field": {
                        "label": {
                            "value": {
                                "en": "Paste an existing long-lived access token:"
                            }
                        }
                    },
                },
                {
                    "field": {"text": {"value": ""}},
                    "id": "token",
                    "label": {"en": "Access Token"},
                },
            ],
        )

    # -------------------------------------------------------------------------
    # query_device – called for both steps
    # -------------------------------------------------------------------------

    async def query_device(
        self, input_values: dict[str, Any]
    ) -> DeviceConfig | SetupError | RequestUserInput:
        """
        Route between the two setup steps.

        * If ``address`` is present in *input_values* and ``token``/``username``
          are not, validate the address and show the credentials screen.
        * If credentials are present, obtain/verify a token and connect.
        """
        # ── Step 1: address only ────────────────────────────────────────────
        if (
            "address" in input_values
            and "token" not in input_values
            and "username" not in input_values
        ):
            raw = input_values.get("address", "")
            address = _normalise_address(raw)

            if not address or address == _normalise_address("http://"):
                _LOG.warning("No server URL provided – re-displaying form")
                return self.get_manual_entry_form()

            self._pending_address = address
            return self._credentials_form(address)

        # ── Step 2: credentials ─────────────────────────────────────────────
        address = self._pending_address or _normalise_address(
            input_values.get("address", "")
        )
        token = input_values.get("token", "").strip() or None
        username = input_values.get("username", "").strip() or None
        password = input_values.get("password", "").strip() or None

        if not address:
            return self.get_manual_entry_form()

        # Obtain a long-lived token from username+password if no token given
        if token is None:
            if not username or not password:
                _LOG.warning("No credentials provided – re-showing credentials form")
                return self._credentials_form(address)

            _LOG.info("Logging in to MA at %s as %s", address, username)
            try:
                login_url = address.rstrip("/") + "/auth/login"
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        login_url,
                        json={
                            "credentials": {"username": username, "password": password}
                        },
                    ) as resp:
                        if resp.status == 401:
                            _LOG.warning(
                                "Login failed for %s at %s – wrong credentials?",
                                username,
                                address,
                            )
                            return self._credentials_form(address)
                        if resp.status != 200:
                            _LOG.error(
                                "Login error at %s: HTTP %s", address, resp.status
                            )
                            return self._credentials_form(address)
                        data = await resp.json()
                        short_token = data.get("token")

                # Upgrade to a long-lived token so credentials aren't stored
                async with MusicAssistantClient(
                    address, None, token=short_token
                ) as client:
                    token = await client.auth.create_token("Unfolded Circle Remote")
                    _LOG.info("Long-lived token created for %s", address)

            except CannotConnect as exc:
                _LOG.error("Cannot connect to MA at %s: %s", address, exc)
                return self._credentials_form(address)
            except Exception as exc:  # pylint: disable=broad-except
                _LOG.error(
                    "Unexpected login error at %s (%s): %s",
                    address,
                    type(exc).__name__,
                    exc,
                )
                return self._credentials_form(address)

        return await self._verify_and_build_config(address, token)

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    async def _verify_and_build_config(
        self, address: str, token: str
    ) -> DeviceConfig | SetupError | RequestUserInput:
        """Connect to MA, verify the server, and return a DeviceConfig."""
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
                token=token,
            )

        except ConnectionError as exc:
            _LOG.error(
                "Connection refused to MA at %s: %s – re-showing address form",
                address,
                exc,
            )
            self._pending_address = ""
            return self.get_manual_entry_form()

        except TimeoutError:
            _LOG.error(
                "Timeout connecting to MA at %s – re-showing address form", address
            )
            self._pending_address = ""
            return self.get_manual_entry_form()

        except Exception as exc:  # pylint: disable=broad-except
            _LOG.error(
                "Unexpected error connecting to MA at %s: %s – re-showing address form",
                address,
                exc,
            )
            self._pending_address = ""
            return self.get_manual_entry_form()

        finally:
            try:
                await client.disconnect()
            except Exception:  # pylint: disable=broad-except
                pass


def _normalise_address(raw: str) -> str:
    """
    Ensure the address has a scheme and a port.

    * Adds ``http://`` if no scheme is present.
    * Appends ``:8095`` if no port is specified.
    """
    raw = raw.strip().rstrip("/")
    if not raw:
        return raw
    if "://" not in raw:
        raw = f"http://{raw}"
    parsed = urlparse(raw)
    if not parsed.port:
        parsed = parsed._replace(netloc=f"{parsed.hostname}:{_DEFAULT_PORT}")
    return urlunparse(parsed)
