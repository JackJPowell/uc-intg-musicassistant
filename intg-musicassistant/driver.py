"""
Music Assistant Integration Driver.

Entry point for the Unfolded Circle Remote Two/3 integration.
Registers all entity classes, configures logging, and starts the API server.

:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

from __future__ import annotations

import asyncio
import logging
import os

from const import DeviceConfig
from device import Device
from discover import DeviceDiscovery
from media_player import MusicAssistantMediaPlayer
from select_entity import SourceSelect
from sensor import ActivePlayersSensor, NowPlayingSensor, QueuePositionSensor
from setup import MusicAssistantSetupFlow
from ucapi_framework import BaseConfigManager, BaseIntegrationDriver, get_config_path

_LOG = logging.getLogger("driver")


async def main() -> None:
    """Start the Music Assistant integration driver."""
    logging.basicConfig()

    level = os.getenv("UC_LOG_LEVEL", "INFO").upper()
    for name in (
        "driver",
        "device",
        "media_player",
        "select_entity",
        "sensor",
        "setup",
    ):
        logging.getLogger(name).setLevel(level)

    _LOG.info("Starting Music Assistant integration driver")

    # BaseIntegrationDriver manages one Device per configured MA server and
    # auto-registers entity instances as they are created.
    # require_connection_before_registry=True ensures entities are only registered
    # after establish_connection() succeeds and device.players is populated.
    #
    # Factory lambdas iterate over device.players so that one set of entities is
    # created per MA player discovered on the server.
    driver = BaseIntegrationDriver(
        device_class=Device,
        entity_classes=[
            # One media player entity per MA player
            lambda cfg, dev: [
                MusicAssistantMediaPlayer(cfg, dev, p.player_id, p.name)
                for p in dev.players
            ],
            # One source-select per player that has sources
            lambda cfg, dev: [
                SourceSelect(cfg, dev, p.player_id, p.name)
                for p in dev.players
                if dev.get_source_list(p.player_id)
            ],
            # "Artist – Title" sensor per player
            lambda cfg, dev: [
                NowPlayingSensor(cfg, dev, p.player_id, p.name) for p in dev.players
            ],
            # Queue position sensor per player
            lambda cfg, dev: [
                QueuePositionSensor(cfg, dev, p.player_id, p.name) for p in dev.players
            ],
            # One server-level sensor: how many players are currently playing
            ActivePlayersSensor,
        ],
        require_connection_before_registry=True,
    )

    driver.config_manager = BaseConfigManager(
        get_config_path(driver.api.config_dir_path),
        driver.on_device_added,
        driver.on_device_removed,
        config_class=DeviceConfig,
    )

    # Load any previously configured MA servers
    await driver.register_all_configured_devices()

    # Discover Music Assistant servers on the local network via Zeroconf (_mass._tcp.local.)
    discovery = DeviceDiscovery(timeout=4)
    setup_handler = MusicAssistantSetupFlow.create_handler(driver, discovery=discovery)

    await driver.api.init("driver.json", setup_handler)

    # Run forever
    await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
