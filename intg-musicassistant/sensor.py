"""
Music Assistant Sensor Entities.

Provides informational sensors derived from the Music Assistant player/queue
state.  These are read-only entities; they have no command handler.

Current sensors (one per MA player):
* ``QueueSizeSensor`` — number of tracks in the player's queue.

:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

from __future__ import annotations

import logging

from ucapi import EntityTypes, sensor

import device as _device_module
from const import DeviceConfig
from ucapi_framework import SensorEntity, create_entity_id

_LOG = logging.getLogger(__name__)


class QueueSizeSensor(SensorEntity):
    """
    Sensor reporting the number of items in an MA player's queue.

    Updated on every Device push_update so the value stays current
    as tracks are added, removed, or played.
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
            EntityTypes.SENSOR, f"{config_device.identifier}_{safe_player}_queue_size"
        )

        _LOG.debug("Creating QueueSizeSensor entity %s for player %s", entity_id, player_id)

        super().__init__(
            entity_id,
            f"{player_name} – Queue Size",
            features=[],
            attributes={
                sensor.Attributes.STATE: sensor.States.ON,
                sensor.Attributes.VALUE: 0,
                sensor.Attributes.UNIT: "tracks",
            },
            device_class=sensor.DeviceClasses.CUSTOM,
        )

        self.subscribe_to_device(device)

    # =========================================================================
    # State sync
    # =========================================================================

    async def sync_state(self) -> None:
        """Update the queue size from the Device's current queue snapshot."""
        queue = self._device.get_queue(self._player_id)

        if queue is None:
            self.set_state(sensor.States.UNAVAILABLE, update=True)
            return

        size = queue.items  # items is an int count in the MA model
        self.set_state(sensor.States.ON)
        self.set_value(size)
        self.update(self.attributes)
