"""
Music Assistant Device Module.

Manages the WebSocket connection to a Music Assistant server and keeps local
state for all MA players and queues.  Entity classes subscribe to this device
and receive push updates via the ucapi-framework DeviceEvents.UPDATE event
whenever player or queue state changes.

:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

from __future__ import annotations

import asyncio
import logging
from asyncio import AbstractEventLoop
from typing import Any

from music_assistant_client import MusicAssistantClient
from music_assistant_models.enums import EventType
from music_assistant_models.player import Player
from music_assistant_models.player_queue import PlayerQueue

from const import DeviceConfig, MA_REPEAT_MAP, MA_STATE_MAP, UC_REPEAT_MAP
from ucapi import media_player
from ucapi_framework import BaseConfigManager, PersistentConnectionDevice

_LOG = logging.getLogger(__name__)


class Device(PersistentConnectionDevice):
    """
    Represents one Music Assistant server.

    One Device instance is created per configured MA server.  It maintains a
    persistent WebSocket connection via ``music-assistant-client`` and keeps a
    live snapshot of all player and queue objects.

    Entity instances (MediaPlayer, Select, Sensor…) call the helpers defined
    here to read current state and issue commands.

    PersistentConnectionDevice lifecycle:
      establish_connection() → connects, returns client as "connection"
      maintain_connection()  → runs start_listening() which blocks until disconnect
      close_connection()     → calls client.disconnect()
    """

    def __init__(
        self,
        device_config: DeviceConfig,
        loop: AbstractEventLoop | None,
        config_manager: BaseConfigManager | None = None,
        driver=None,
    ) -> None:
        super().__init__(
            device_config=device_config,
            loop=loop,
            config_manager=config_manager,
            driver=driver,
        )

        self._client: MusicAssistantClient | None = None
        self._init_ready: asyncio.Event = asyncio.Event()

        # Snapshot dicts – updated by MA event callbacks
        self._players: dict[str, Player] = {}
        self._queues: dict[str, PlayerQueue] = {}

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def identifier(self) -> str:
        """Return the server identifier."""
        return self._device_config.identifier

    @property
    def name(self) -> str:
        """Return the server friendly name."""
        return self._device_config.name

    @property
    def address(self) -> str | None:
        """Return the server URL."""
        return self._device_config.address

    @property
    def log_id(self) -> str:
        """Return a log identifier."""
        return self.name or self.identifier

    @property
    def players(self) -> list[Player]:
        """Return all known MA players."""
        return list(self._players.values())

    @property
    def player_ids(self) -> list[str]:
        """Return all known MA player IDs."""
        return list(self._players.keys())

    @property
    def client(self) -> MusicAssistantClient | None:
        """Return the underlying MA client (for browser use)."""
        return self._client

    def get_player(self, player_id: str) -> Player | None:
        """Return a Player by its MA player_id."""
        return self._players.get(player_id)

    def get_queue(self, queue_id: str) -> PlayerQueue | None:
        """Return a PlayerQueue by queue_id (usually == player_id)."""
        return self._queues.get(queue_id)

    # =========================================================================
    # PersistentConnectionDevice hooks
    # =========================================================================

    async def establish_connection(self) -> MusicAssistantClient:
        """
        Open a WebSocket connection to the Music Assistant server.

        Called by the framework's _connection_loop.  Returns the client object
        which is stored as self._connection.
        """
        _LOG.info("[%s] Connecting to %s", self.log_id, self.address)

        if not self.address:
            raise ValueError("No server address configured")

        token = self._device_config.token or None
        client = MusicAssistantClient(self.address, None, token=token)

        self._init_ready.clear()

        # Subscribe to relevant MA events before connecting
        client.subscribe(
            self._on_player_event,
            (EventType.PLAYER_ADDED, EventType.PLAYER_UPDATED, EventType.PLAYER_REMOVED),
        )
        client.subscribe(
            self._on_queue_event,
            (EventType.QUEUE_ADDED, EventType.QUEUE_UPDATED),
        )

        # Connect (handshake) without starting the full listener loop yet
        await client.connect()

        # Snapshot initial state
        for player in client.players:
            self._players[player.player_id] = player
        for queue in client.player_queues:
            self._queues[queue.queue_id] = queue

        self._client = client

        _LOG.info("[%s] Connected – %d players found", self.log_id, len(self._players))
        self.push_update()

        return client

    async def maintain_connection(self) -> None:
        """
        Keep the connection alive by running the MA message listener.

        start_listening() is a blocking coroutine that processes incoming
        WebSocket messages until the connection drops.
        """
        if self._client is None:
            return
        try:
            await self._client.start_listening()
        except Exception as exc:  # pylint: disable=broad-except
            _LOG.debug("[%s] start_listening exited: %s", self.log_id, exc)
            raise  # re-raise so _connection_loop can handle reconnect

    async def close_connection(self) -> None:
        """Close the WebSocket connection and clear state."""
        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception as exc:  # pylint: disable=broad-except
                _LOG.debug("[%s] Disconnect error: %s", self.log_id, exc)
            self._client = None
        self._players.clear()
        self._queues.clear()

    # =========================================================================
    # MA event handlers
    # =========================================================================

    def _on_player_event(self, event: Any) -> None:
        """Handle player_added / player_updated / player_removed events."""
        if event.event == EventType.PLAYER_REMOVED:
            self._players.pop(event.object_id, None)
        elif event.data:
            try:
                player = Player.from_dict(event.data)
                self._players[player.player_id] = player
            except Exception as exc:  # pylint: disable=broad-except
                _LOG.warning("[%s] Failed to parse player event: %s", self.log_id, exc)
        self.push_update()

    def _on_queue_event(self, event: Any) -> None:
        """Handle queue_added / queue_updated events."""
        if event.data:
            try:
                queue = PlayerQueue.from_dict(event.data)
                self._queues[queue.queue_id] = queue
            except Exception as exc:  # pylint: disable=broad-except
                _LOG.warning("[%s] Failed to parse queue event: %s", self.log_id, exc)
        self.push_update()

    # =========================================================================
    # Derived state helpers (used by entity sync_state)
    # =========================================================================

    def get_ucapi_state(self, player_id: str) -> media_player.States:
        """Map an MA player's state to a ucapi media_player.States value."""
        player = self._players.get(player_id)
        if player is None:
            return media_player.States.UNAVAILABLE
        if not player.available or not player.enabled:
            return media_player.States.UNAVAILABLE
        if player.powered is False:
            return media_player.States.OFF

        queue = self._queues.get(player_id)
        if queue is not None:
            state_str = MA_STATE_MAP.get(queue.state.value, "UNKNOWN")
        else:
            state_str = MA_STATE_MAP.get(player.playback_state.value, "UNKNOWN")

        return media_player.States(state_str)

    def get_media_info(self, player_id: str) -> dict[str, Any]:
        """
        Return a dict of current media metadata for a player.

        Keys correspond to ucapi MediaPlayer Attribute names.
        """
        info: dict[str, Any] = {}
        queue = self._queues.get(player_id)
        if queue is None:
            return info

        current = queue.current_item
        if current is None:
            return info

        media_item = current.media_item
        if media_item is not None:
            info["media_title"] = getattr(media_item, "name", current.name) or current.name
            artists = getattr(media_item, "artists", None)
            if artists:
                info["media_artist"] = "/".join(a.name for a in artists if a.name)
            album = getattr(media_item, "album", None)
            if album:
                info["media_album"] = getattr(album, "name", None)
            duration = getattr(media_item, "duration", None) or current.duration
            if duration:
                info["media_duration"] = int(duration)
        else:
            info["media_title"] = current.name

        elapsed = queue.corrected_elapsed_time
        if elapsed is not None:
            info["media_position"] = int(elapsed)

        image = current.image
        if image is None and media_item is not None:
            image = getattr(media_item, "image", None)
        if image is not None and self._client is not None:
            try:
                info["media_image_url"] = self._client.get_image_url(image)
            except Exception:  # pylint: disable=broad-except
                pass

        try:
            mt = current.media_type.value.upper()
            _mt_map = {
                "TRACK": "MUSIC",
                "RADIO": "RADIO",
                "PODCAST_EPISODE": "MUSIC",
                "AUDIOBOOK": "MUSIC",
                "UNKNOWN": "MUSIC",
            }
            info["media_type"] = _mt_map.get(mt, "MUSIC")
        except Exception:  # pylint: disable=broad-except
            pass

        return info

    def get_repeat_mode(self, player_id: str) -> media_player.RepeatMode:
        """Return the ucapi RepeatMode for the given player's queue."""
        queue = self._queues.get(player_id)
        if queue is None:
            return media_player.RepeatMode.OFF
        ucapi_repeat = MA_REPEAT_MAP.get(queue.repeat_mode.value, "OFF")
        return media_player.RepeatMode(ucapi_repeat)

    def get_shuffle(self, player_id: str) -> bool:
        """Return shuffle state for the given player's queue."""
        queue = self._queues.get(player_id)
        return queue.shuffle_enabled if queue else False

    def get_source_list(self, player_id: str) -> list[str]:
        """Return the list of available sources for a player."""
        player = self._players.get(player_id)
        if player is None:
            return []
        return [s.name for s in player.source_list if not s.passive]

    def get_active_source(self, player_id: str) -> str | None:
        """Return the active source name for a player."""
        player = self._players.get(player_id)
        if player is None:
            return None
        if player.active_source is None:
            return None
        for src in player.source_list:
            if src.id == player.active_source:
                return src.name
        return player.active_source

    def get_sound_mode_list(self, player_id: str) -> list[str]:
        """Return available sound modes for a player."""
        player = self._players.get(player_id)
        if player is None:
            return []
        return [sm.name for sm in player.sound_mode_list if not sm.passive]

    def get_active_sound_mode(self, player_id: str) -> str | None:
        """Return active sound mode name for a player."""
        player = self._players.get(player_id)
        if player is None:
            return None
        if player.active_sound_mode is None:
            return None
        for sm in player.sound_mode_list:
            if sm.id == player.active_sound_mode:
                return sm.name
        return player.active_sound_mode

    def get_all_player_names(self) -> list[str]:
        """Return a list of all available MA player display names."""
        return [p.name for p in self._players.values() if p.available and p.enabled]

    def get_player_id_by_name(self, name: str) -> str | None:
        """Look up a player's ID by its display name."""
        for p in self._players.values():
            if p.name == name:
                return p.player_id
        return None

    # =========================================================================
    # Commands – Power
    # =========================================================================

    async def power_on(self, player_id: str) -> None:
        """Turn on a player."""
        _LOG.debug("[%s] power_on: %s", self.log_id, player_id)
        await self._send("players/cmd/power", player_id=player_id, powered=True)

    async def power_off(self, player_id: str) -> None:
        """Turn off a player."""
        _LOG.debug("[%s] power_off: %s", self.log_id, player_id)
        await self._send("players/cmd/power", player_id=player_id, powered=False)

    # =========================================================================
    # Commands – Playback
    # =========================================================================

    async def play_pause(self, player_id: str) -> None:
        """Toggle play/pause."""
        await self._send("player_queues/play_pause", queue_id=player_id)

    async def stop(self, player_id: str) -> None:
        """Send STOP command."""
        await self._send("players/cmd/stop", player_id=player_id)

    async def next_track(self, player_id: str) -> None:
        """Skip to the next track."""
        await self._send("players/cmd/next", player_id=player_id)

    async def previous_track(self, player_id: str) -> None:
        """Go to the previous track."""
        await self._send("players/cmd/previous", player_id=player_id)

    async def seek(self, player_id: str, position: int) -> None:
        """Seek to position (seconds)."""
        await self._send("player_queues/seek", queue_id=player_id, position=position)

    # =========================================================================
    # Commands – Volume
    # =========================================================================

    async def volume_set(self, player_id: str, volume: int) -> None:
        """Set volume (0-100)."""
        await self._send("players/cmd/volume_set", player_id=player_id, volume_level=volume)

    async def volume_up(self, player_id: str) -> None:
        """Increase volume by one step."""
        await self._send("players/cmd/volume_up", player_id=player_id)

    async def volume_down(self, player_id: str) -> None:
        """Decrease volume by one step."""
        await self._send("players/cmd/volume_down", player_id=player_id)

    async def mute(self, player_id: str, muted: bool) -> None:
        """Set mute state."""
        await self._send("players/cmd/volume_mute", player_id=player_id, muted=muted)

    # =========================================================================
    # Commands – Repeat / Shuffle / Queue
    # =========================================================================

    async def set_repeat(self, player_id: str, repeat_mode: str) -> None:
        """Set repeat mode (ucapi RepeatMode string → MA RepeatMode)."""
        ma_mode = UC_REPEAT_MAP.get(repeat_mode, "off")
        await self._send("player_queues/repeat", queue_id=player_id, repeat_mode=ma_mode)

    async def set_shuffle(self, player_id: str, enabled: bool) -> None:
        """Enable or disable shuffle."""
        await self._send("player_queues/shuffle", queue_id=player_id, shuffle_enabled=enabled)

    async def clear_queue(self, player_id: str) -> None:
        """Clear the player queue."""
        await self._send("player_queues/clear", queue_id=player_id)

    async def add_to_favorites(self, player_id: str) -> None:
        """Add currently playing item to favorites."""
        if self._client:
            await self._client.players.add_currently_playing_to_favorites(player_id)

    # =========================================================================
    # Commands – Media Browsing / Play URI
    # =========================================================================

    async def play_uri(self, player_id: str, uri: str) -> None:
        """
        Play a media item identified by its MA URI on the given player.

        MA URIs are returned by the browser and have the form:
        ``library://track/123``, ``spotify://album/xyz``, etc.
        They are passed directly to ``player_queues/play_media``.
        """
        _LOG.debug("[%s] play_uri: %s → %s", self.log_id, player_id, uri)
        if self._client is None:
            raise ConnectionError("Not connected to Music Assistant")
        await self._client.player_queues.play_media(queue_id=player_id, media=uri)

    # =========================================================================
    # Commands – Source / Sound Mode
    # =========================================================================

    async def select_source(self, player_id: str, source_name: str) -> None:
        """Select a source by its display name."""
        player = self._players.get(player_id)
        if player is None:
            raise ValueError(f"Unknown player: {player_id}")
        source_id = source_name
        for src in player.source_list:
            if src.name == source_name:
                source_id = src.id
                break
        await self._send("players/cmd/select_source", player_id=player_id, source=source_id)

    async def select_sound_mode(self, player_id: str, mode_name: str) -> None:
        """Select a sound mode by its display name."""
        player = self._players.get(player_id)
        if player is None:
            raise ValueError(f"Unknown player: {player_id}")
        mode_id = mode_name
        for sm in player.sound_mode_list:
            if sm.name == mode_name:
                mode_id = sm.id
                break
        await self._send(
            "players/cmd/select_sound_mode", player_id=player_id, sound_mode=mode_id
        )

    # =========================================================================
    # Internal helpers
    # =========================================================================

    async def _send(self, command: str, **kwargs: Any) -> Any:
        """Send a command to the MA server via the WebSocket client."""
        if self._client is None:
            raise ConnectionError("Not connected to Music Assistant")
        return await self._client.send_command(command, **kwargs)

    @property
    def state(self) -> media_player.States:
        """Return a generic device state used by the framework for health checks."""
        if self._client is not None and self._client.connection.connected:
            return media_player.States.ON
        return media_player.States.OFF
