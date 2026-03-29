"""
Music Assistant Select Entities.

Two kinds of select entities:

* ``ActivePlayerSelect`` — one per MA server.  Lets the user choose which MA
  player receives playback commands (useful when a single integration is
  connected to multiple physical devices).

* ``SourceSelect`` — one per MA player that exposes sources (e.g. Spotify,
  AirPlay, local library).  Wraps the same source-selection already exposed on
  the MediaPlayer entity as a standalone select for quick access.

:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

from __future__ import annotations

import logging
from typing import Any

import ucapi
from ucapi import EntityTypes, select

import device as _device_module
from const import DeviceConfig
from ucapi_framework import SelectEntity, create_entity_id

_LOG = logging.getLogger(__name__)


class ActivePlayerSelect(SelectEntity):
    """
    Server-level select: choose which MA player is the "active" target.

    The current option reflects the most recently selected player name.
    Selecting a new option does *not* issue a playback command; it simply
    records the target player so that driver-level actions (e.g. "play
    something on the currently selected player") know which player to use.

    The options list is refreshed every time the Device emits a push_update,
    so newly discovered or removed players are reflected automatically.
    """

    def __init__(
        self,
        config_device: DeviceConfig,
        device: _device_module.Device,
    ) -> None:
        self._device = device
        self._server_id = config_device.identifier

        entity_id = create_entity_id(
            EntityTypes.SELECT, f"{config_device.identifier}_active_player"
        )

        initial_names = device.get_all_player_names()

        _LOG.debug("Creating ActivePlayerSelect entity %s", entity_id)

        super().__init__(
            entity_id,
            f"{config_device.name} – Active Player",
            attributes={
                select.Attributes.STATE: select.States.ON,
                select.Attributes.OPTIONS: initial_names,
                select.Attributes.CURRENT_OPTION: initial_names[0] if initial_names else None,
            },
            cmd_handler=self.handle_command,
        )

        self.subscribe_to_device(device)

    # =========================================================================
    # State sync
    # =========================================================================

    async def sync_state(self) -> None:
        """Refresh the options list from the Device."""
        names = self._device.get_all_player_names()

        current = self.current_option
        if current not in names:
            current = names[0] if names else None

        self.set_options(names)
        self.set_current_option(current)
        self.set_state(select.States.ON if names else select.States.UNAVAILABLE)
        self.update(self.attributes)

    # =========================================================================
    # Command handler
    # =========================================================================

    async def handle_command(
        self,
        _entity: ActivePlayerSelect,
        cmd_id: str,
        params: dict[str, Any] | None,
        _: Any | None = None,
    ) -> ucapi.StatusCodes:
        """Handle SELECT_OPTION (and convenience navigation commands)."""
        _LOG.debug("[ActivePlayerSelect] Command: %s %s", cmd_id, params or "")

        options = self.select_options or []
        if not options:
            return ucapi.StatusCodes.SERVICE_UNAVAILABLE

        try:
            match cmd_id:
                case select.Commands.SELECT_OPTION:
                    option = (params or {}).get("option", "")
                    if option not in options:
                        return ucapi.StatusCodes.BAD_REQUEST
                    self.set_current_option(option, update=True)

                case select.Commands.SELECT_FIRST:
                    self.set_current_option(options[0], update=True)

                case select.Commands.SELECT_LAST:
                    self.set_current_option(options[-1], update=True)

                case select.Commands.SELECT_NEXT:
                    idx = options.index(self.current_option) if self.current_option in options else -1
                    self.set_current_option(options[(idx + 1) % len(options)], update=True)

                case select.Commands.SELECT_PREVIOUS:
                    idx = options.index(self.current_option) if self.current_option in options else 0
                    self.set_current_option(options[(idx - 1) % len(options)], update=True)

                case _:
                    _LOG.warning("[ActivePlayerSelect] Unhandled command: %s", cmd_id)
                    return ucapi.StatusCodes.NOT_IMPLEMENTED

            return ucapi.StatusCodes.OK

        except Exception as exc:  # pylint: disable=broad-except
            _LOG.error("[ActivePlayerSelect] Command error: %s", exc)
            return ucapi.StatusCodes.SERVER_ERROR


class SourceSelect(SelectEntity):
    """
    Per-player select: choose the active input source.

    Only created for players that advertise at least one (non-passive) source.
    This provides a standalone select widget in the Remote UI alongside the
    full MediaPlayer card.
    """

    def __init__(
        self,
        config_device: DeviceConfig,
        device: _device_module.Device,
        player_id: str,
        player_name: str,
    ) -> None:
        self._device = device
        self._player_id = player_id

        safe_player = player_id.replace(".", "_").replace("-", "_")
        entity_id = create_entity_id(
            EntityTypes.SELECT, f"{config_device.identifier}_{safe_player}_source"
        )

        sources = device.get_source_list(player_id)
        active = device.get_active_source(player_id)

        _LOG.debug("Creating SourceSelect entity %s for player %s", entity_id, player_id)

        super().__init__(
            entity_id,
            f"{player_name} – Source",
            attributes={
                select.Attributes.STATE: select.States.ON,
                select.Attributes.OPTIONS: sources,
                select.Attributes.CURRENT_OPTION: active,
            },
            cmd_handler=self.handle_command,
        )

        self.subscribe_to_device(device)

    # =========================================================================
    # State sync
    # =========================================================================

    async def sync_state(self) -> None:
        """Refresh sources and active source from the Device."""
        sources = self._device.get_source_list(self._player_id)
        active = self._device.get_active_source(self._player_id)

        self.set_options(sources)
        self.set_current_option(active)
        self.set_state(select.States.ON if sources else select.States.UNAVAILABLE)
        self.update(self.attributes)

    # =========================================================================
    # Command handler
    # =========================================================================

    async def handle_command(
        self,
        _entity: SourceSelect,
        cmd_id: str,
        params: dict[str, Any] | None,
        _: Any | None = None,
    ) -> ucapi.StatusCodes:
        """Handle SELECT_OPTION and navigation commands."""
        _LOG.debug("[SourceSelect/%s] Command: %s %s", self._player_id, cmd_id, params or "")

        options = self.select_options or []

        try:
            match cmd_id:
                case select.Commands.SELECT_OPTION:
                    option = (params or {}).get("option", "")
                    if option not in options:
                        return ucapi.StatusCodes.BAD_REQUEST
                    await self._device.select_source(self._player_id, option)
                    self.set_current_option(option, update=True)

                case select.Commands.SELECT_FIRST:
                    if options:
                        await self._device.select_source(self._player_id, options[0])
                        self.set_current_option(options[0], update=True)

                case select.Commands.SELECT_LAST:
                    if options:
                        await self._device.select_source(self._player_id, options[-1])
                        self.set_current_option(options[-1], update=True)

                case select.Commands.SELECT_NEXT:
                    if options:
                        idx = options.index(self.current_option) if self.current_option in options else -1
                        nxt = options[(idx + 1) % len(options)]
                        await self._device.select_source(self._player_id, nxt)
                        self.set_current_option(nxt, update=True)

                case select.Commands.SELECT_PREVIOUS:
                    if options:
                        idx = options.index(self.current_option) if self.current_option in options else 0
                        prev = options[(idx - 1) % len(options)]
                        await self._device.select_source(self._player_id, prev)
                        self.set_current_option(prev, update=True)

                case _:
                    _LOG.warning("[SourceSelect/%s] Unhandled command: %s", self._player_id, cmd_id)
                    return ucapi.StatusCodes.NOT_IMPLEMENTED

            return ucapi.StatusCodes.OK

        except (ConnectionError, ValueError) as exc:
            _LOG.error("[SourceSelect/%s] Command error: %s", self._player_id, exc)
            return ucapi.StatusCodes.BAD_REQUEST
        except Exception as exc:  # pylint: disable=broad-except
            _LOG.error("[SourceSelect/%s] Unexpected error: %s", self._player_id, exc)
            return ucapi.StatusCodes.SERVER_ERROR
