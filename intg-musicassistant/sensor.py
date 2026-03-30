"""
Music Assistant Sensor Entities.

Provides informational sensors derived from the Music Assistant player/queue
state.  These are read-only entities; they have no command handler.

Sensors (one per MA player unless noted):
* ``NowPlayingSensor``        — "Artist – Title" for the current track (or stream title).
* ``QueuePositionSensor``     — Current track position within the queue, e.g. "3 / 12".
* ``ActivePlayersSensor``     — (one per server) count of players currently playing.

:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

from __future__ import annotations

import logging

from ucapi import EntityTypes, sensor

import device as _device_module
from const import DeviceConfig
from ucapi_framework import SensorAttributes, SensorEntity, create_entity_id
from music_assistant_models.enums import PlaybackState

_LOG = logging.getLogger(__name__)


class NowPlayingSensor(SensorEntity):
    """
    Sensor showing the currently playing track as "Artist – Title".

    Falls back to just the title if no artist is available (e.g. radio streams).
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

        entity_id = create_entity_id(
            EntityTypes.SENSOR, config_device.identifier, f"{player_id}_now_playing"
        )

        _LOG.debug(
            "Creating NowPlayingSensor entity %s for player %s", entity_id, player_id
        )

        super().__init__(
            entity_id,
            f"{player_name} – Now Playing",
            features=[],
            attributes={
                sensor.Attributes.STATE: sensor.States.ON,
                sensor.Attributes.VALUE: "",
                sensor.Attributes.UNIT: "",
            },
            device_class=sensor.DeviceClasses.CUSTOM,
        )

        self.subscribe_to_device(device)

    async def sync_state(self) -> None:
        """Update the now-playing text from the Device's current queue snapshot."""
        queue = self._device.get_queue(self._player_id)

        if queue is None or queue.current_item is None:
            self.update(SensorAttributes(STATE=sensor.States.UNAVAILABLE, VALUE=""))
            return

        current = queue.current_item
        media_item = current.media_item

        title: str = ""
        if media_item is not None:
            title = getattr(media_item, "name", "") or current.name or ""
            artists = getattr(media_item, "artists", None)
            if artists:
                artist_str = ", ".join(a.name for a in artists if a.name)
                if artist_str:
                    title = f"{artist_str} – {title}"
        else:
            title = current.name or ""

        self.update(SensorAttributes(STATE=sensor.States.ON, VALUE=title))


class QueuePositionSensor(SensorEntity):
    """
    Sensor reporting the current queue position as "current / total".

    e.g. "3 / 12" means the third track out of twelve in the queue.
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

        entity_id = create_entity_id(
            EntityTypes.SENSOR, config_device.identifier, f"{player_id}_queue_pos"
        )

        _LOG.debug(
            "Creating QueuePositionSensor entity %s for player %s", entity_id, player_id
        )

        super().__init__(
            entity_id,
            f"{player_name} – Queue Position",
            features=[],
            attributes={
                sensor.Attributes.STATE: sensor.States.ON,
                sensor.Attributes.VALUE: "",
                sensor.Attributes.UNIT: "",
            },
            device_class=sensor.DeviceClasses.CUSTOM,
        )

        self.subscribe_to_device(device)

    async def sync_state(self) -> None:
        """Update the queue position indicator."""
        queue = self._device.get_queue(self._player_id)

        if queue is None:
            self.update(SensorAttributes(STATE=sensor.States.UNAVAILABLE, VALUE=""))
            return

        total: int = queue.items
        index = queue.current_index  # None when nothing is queued

        if index is None or total == 0:
            value = "–"
        else:
            # current_index is 0-based; display as 1-based
            value = f"{index + 1} / {total}"

        self.update(SensorAttributes(STATE=sensor.States.ON, VALUE=value))


class ActivePlayersSensor(SensorEntity):
    """
    Server-level sensor: count of MA players that are currently playing.

    One instance per MA server (not per player).
    """

    def __init__(
        self,
        config_device: DeviceConfig,
        device: _device_module.Device,
    ) -> None:
        self._device = device

        entity_id = create_entity_id(
            EntityTypes.SENSOR, f"{config_device.identifier}_active_players"
        )

        _LOG.debug("Creating ActivePlayersSensor entity %s", entity_id)

        super().__init__(
            entity_id,
            f"{config_device.name} – Active Players",
            features=[],
            attributes={
                sensor.Attributes.STATE: sensor.States.ON,
                sensor.Attributes.VALUE: 0,
                sensor.Attributes.UNIT: "playing",
            },
            device_class=sensor.DeviceClasses.CUSTOM,
        )

        self.subscribe_to_device(device)

    async def sync_state(self) -> None:
        """Count players whose queue is currently in PLAYING state."""
        count = sum(
            1
            for p in self._device.players
            if (q := self._device.get_queue(p.player_id)) is not None
            and q.state == PlaybackState.PLAYING
        )

        self.update(SensorAttributes(STATE=sensor.States.ON, VALUE=count))
