"""
Music Assistant Media Player Entity.

One instance per MA player.  Subscribes to push updates from the Device and
maps all ucapi media player commands to the corresponding MA API calls.

:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

from __future__ import annotations

import logging
from typing import Any

import browser as ma_browser
import device as _device_module
import ucapi
from const import DeviceConfig, SimpleCommands
from ucapi import EntityTypes, media_player
from ucapi.api_definitions import (
    BrowseOptions,
    BrowseResults,
    SearchOptions,
    SearchResults,
)
from ucapi.media_player import Attributes, Commands, DeviceClasses, Features
from ucapi_framework import MediaPlayerAttributes, MediaPlayerEntity, create_entity_id

_LOG = logging.getLogger(__name__)

# Features supported by every MA player
_BASE_FEATURES = [
    Features.ON_OFF,
    Features.TOGGLE,
    Features.PLAY_PAUSE,
    Features.STOP,
    Features.NEXT,
    Features.PREVIOUS,
    Features.SEEK,
    Features.REPEAT,
    Features.SHUFFLE,
    Features.VOLUME,
    Features.VOLUME_UP_DOWN,
    Features.MUTE,
    Features.MUTE_TOGGLE,
    Features.MEDIA_DURATION,
    Features.MEDIA_POSITION,
    Features.MEDIA_TITLE,
    Features.MEDIA_ARTIST,
    Features.MEDIA_ALBUM,
    Features.MEDIA_IMAGE_URL,
    Features.MEDIA_TYPE,
    Features.BROWSE_MEDIA,
    Features.SEARCH_MEDIA,
    Features.PLAY_MEDIA,
]


class MusicAssistantMediaPlayer(MediaPlayerEntity):
    """
    Media Player entity for a single Music Assistant player.

    One instance is created for each MA player discovered on the server.
    The entity manages its own attribute state using the ucapi-framework
    1.9.x pattern (setter methods, no get_device_attributes).
    """

    def __init__(
        self,
        config_device: DeviceConfig,
        device: _device_module.Device,
        player_id: str,
        player_name: str,
    ) -> None:
        """
        Initialize the MA media player entity.

        :param config_device: Server-level DeviceConfig (for the server identifier/name)
        :param device: The Device instance managing the MA connection
        :param player_id: MA player_id (e.g. "spotify_player")
        :param player_name: Human-readable player name
        """
        self._device = device
        self._player_id = player_id

        # Build a deterministic entity ID from server + player
        entity_id = create_entity_id(
            EntityTypes.MEDIA_PLAYER, config_device.identifier, player_id
        )

        # Determine features based on what this player supports at creation time
        features = list(_BASE_FEATURES)

        ma_player = device.get_player(player_id)
        if ma_player is not None:
            if device.get_source_list(player_id):
                features.append(Features.SELECT_SOURCE)
            if device.get_sound_mode_list(player_id):
                features.append(Features.SELECT_SOUND_MODE)

        _LOG.debug("Creating MediaPlayer entity %s for player %s", entity_id, player_id)

        super().__init__(
            entity_id,
            player_name,
            features,
            attributes={Attributes.STATE: ""},
            device_class=DeviceClasses.SPEAKER,
            options={
                media_player.Options.SIMPLE_COMMANDS: [c.value for c in SimpleCommands]
            },
            cmd_handler=self.handle_command,
        )

        self.subscribe_to_device(device)

    # =========================================================================
    # State synchronisation (called on push_update from Device)
    # =========================================================================

    async def sync_state(self) -> None:
        """Pull current state from the Device and push all attributes to Remote."""
        if self._device is None:
            self.update(MediaPlayerAttributes(STATE=media_player.States.UNAVAILABLE))
            return

        ma_player = self._device.get_player(self._player_id)
        media_info = self._device.get_media_info(self._player_id)
        source_list = self._device.get_source_list(self._player_id)
        sound_mode_list = self._device.get_sound_mode_list(self._player_id)

        self.update(
            MediaPlayerAttributes(
                STATE=self._device.get_ucapi_state(self._player_id),
                VOLUME=int(ma_player.volume_level)
                if ma_player and ma_player.volume_level is not None
                else None,
                MUTED=ma_player.volume_muted if ma_player else None,
                REPEAT=self._device.get_repeat_mode(self._player_id),
                SHUFFLE=self._device.get_shuffle(self._player_id),
                SOURCE=self._device.get_active_source(self._player_id),
                SOURCE_LIST=source_list if source_list else None,
                SOUND_MODE=self._device.get_active_sound_mode(self._player_id),
                SOUND_MODE_LIST=sound_mode_list if sound_mode_list else None,
                MEDIA_TITLE=media_info.get("media_title"),
                MEDIA_ARTIST=media_info.get("media_artist"),
                MEDIA_ALBUM=media_info.get("media_album"),
                MEDIA_DURATION=media_info.get("media_duration"),
                MEDIA_POSITION=media_info.get("media_position"),
                MEDIA_IMAGE_URL=media_info.get("media_image_url"),
                MEDIA_TYPE=media_info.get("media_type"),
            )
        )

    # =========================================================================
    # Media browsing / searching
    # =========================================================================

    async def browse(self, options: BrowseOptions) -> BrowseResults | ucapi.StatusCodes:
        """Browse media library hierarchy or a specific path."""
        if self._device is None or self._device.client is None:
            return ucapi.StatusCodes.SERVICE_UNAVAILABLE
        try:
            return await ma_browser.browse(self._device.client, options)
        except Exception as exc:  # pylint: disable=broad-except
            _LOG.error("[%s] Browse error: %s", self._player_id, exc)
            return ucapi.StatusCodes.SERVER_ERROR

    async def search(self, options: SearchOptions) -> SearchResults | ucapi.StatusCodes:
        """Search the Music Assistant library."""
        if self._device is None or self._device.client is None:
            return ucapi.StatusCodes.SERVICE_UNAVAILABLE
        try:
            return await ma_browser.search(self._device.client, options)
        except Exception as exc:  # pylint: disable=broad-except
            _LOG.error("[%s] Search error: %s", self._player_id, exc)
            return ucapi.StatusCodes.SERVER_ERROR

    # =========================================================================
    # Command handler
    # =========================================================================

    async def handle_command(
        self,
        _entity: MusicAssistantMediaPlayer,
        cmd_id: str,
        params: dict[str, Any] | None,
        _: Any | None = None,
    ) -> ucapi.StatusCodes:
        """Route ucapi media player commands to Device methods."""
        if self._device is None:
            _LOG.warning("Command %s: device not available", cmd_id)
            return ucapi.StatusCodes.SERVICE_UNAVAILABLE

        _LOG.debug("[%s] Command: %s %s", self._player_id, cmd_id, params or "")

        try:
            match cmd_id:
                # ── Power ────────────────────────────────────────────────────
                case Commands.ON:
                    await self._device.power_on(self._player_id)
                case Commands.OFF:
                    await self._device.power_off(self._player_id)
                case Commands.TOGGLE:
                    state = self._device.get_ucapi_state(self._player_id)
                    if state == media_player.States.OFF:
                        await self._device.power_on(self._player_id)
                    else:
                        await self._device.power_off(self._player_id)

                # ── Playback ─────────────────────────────────────────────────
                case Commands.PLAY_PAUSE:
                    await self._device.play_pause(self._player_id)
                case Commands.STOP:
                    await self._device.stop(self._player_id)
                case Commands.NEXT:
                    await self._device.next_track(self._player_id)
                case Commands.PREVIOUS:
                    await self._device.previous_track(self._player_id)
                case Commands.SEEK:
                    pos = int((params or {}).get("media_position", 0))
                    await self._device.seek(self._player_id, pos)

                # ── Volume ───────────────────────────────────────────────────
                case Commands.VOLUME:
                    vol = int((params or {}).get("volume", 50))
                    await self._device.volume_set(self._player_id, vol)
                case Commands.VOLUME_UP:
                    await self._device.volume_up(self._player_id)
                case Commands.VOLUME_DOWN:
                    await self._device.volume_down(self._player_id)
                case Commands.MUTE_TOGGLE:
                    muted = self.muted
                    await self._device.mute(
                        self._player_id, not muted if muted is not None else True
                    )
                case Commands.MUTE:
                    await self._device.mute(self._player_id, True)
                case Commands.UNMUTE:
                    await self._device.mute(self._player_id, False)

                # ── Repeat / Shuffle ─────────────────────────────────────────
                case Commands.REPEAT:
                    repeat_val = (params or {}).get("repeat", "OFF")
                    await self._device.set_repeat(self._player_id, repeat_val)
                case Commands.SHUFFLE:
                    shuffle_val = bool((params or {}).get("shuffle", False))
                    await self._device.set_shuffle(self._player_id, shuffle_val)

                # ── Source / Sound Mode ──────────────────────────────────────
                case Commands.SELECT_SOURCE:
                    source = (params or {}).get("source", "")
                    await self._device.select_source(self._player_id, source)
                case Commands.SELECT_SOUND_MODE:
                    mode = (params or {}).get("mode", "")
                    await self._device.select_sound_mode(self._player_id, mode)

                # ── Simple Commands ──────────────────────────────────────────
                case SimpleCommands.CLEAR_QUEUE:
                    await self._device.clear_queue(self._player_id)
                case SimpleCommands.ADD_TO_FAVORITES:
                    await self._device.add_to_favorites(self._player_id)

                # ── Media Browsing ───────────────────────────────────────────
                case Commands.PLAY_MEDIA:
                    media_id = (params or {}).get("media_id", "")
                    if media_id:
                        await self._device.play_uri(self._player_id, media_id)
                    else:
                        return ucapi.StatusCodes.BAD_REQUEST

                case _:
                    _LOG.warning("[%s] Unhandled command: %s", self._player_id, cmd_id)
                    return ucapi.StatusCodes.NOT_IMPLEMENTED

            return ucapi.StatusCodes.OK

        except (ConnectionError, ValueError) as exc:
            _LOG.error("[%s] Command %s error: %s", self._player_id, cmd_id, exc)
            return ucapi.StatusCodes.BAD_REQUEST
        except Exception as exc:  # pylint: disable=broad-except
            _LOG.error(
                "[%s] Unexpected error in command %s: %s", self._player_id, cmd_id, exc
            )
            return ucapi.StatusCodes.SERVER_ERROR
