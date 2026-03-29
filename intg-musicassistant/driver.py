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
from media_player import MusicAssistantMediaPlayer
from select_entity import ActivePlayerSelect, SourceSelect
from sensor import QueueSizeSensor
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
    # after the Device.connect() succeeds and player data is available.
    driver = BaseIntegrationDriver(
        device_class=Device,
        entity_classes=[  # type: ignore[arg-type]
            MusicAssistantMediaPlayer,
            ActivePlayerSelect,
            SourceSelect,
            QueueSizeSensor,
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

    # Setup handler — no mDNS discovery; user always enters the server URL manually
    setup_handler = MusicAssistantSetupFlow.create_handler(driver)

    await driver.api.init("driver.json", setup_handler)

    # Run forever
    await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
