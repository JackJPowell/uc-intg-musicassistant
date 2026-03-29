"""
Device Communication Module.

This module handles all communication with your device. It manages connections,
sends commands, and tracks device state.

TODO: Implement the actual device communication logic for your specific device.

:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

import logging
from asyncio import AbstractEventLoop
from typing import Any

from const import DeviceConfig
from ucapi import media_player
from ucapi_framework import (
    BaseConfigManager,
    StatelessHTTPDevice,
)
from ucapi_framework.helpers import MediaPlayerAttributes

_LOG = logging.getLogger(__name__)


class Device(StatelessHTTPDevice):
    """
    Device class representing your physical device.

    This class handles all communication with the device and maintains
    its current state. Extend this class with methods specific to your device.

    The base class StatelessHTTPDevice is suitable for devices that don't
    maintain a persistent connection. If your device uses a persistent
    connection (like TCP sockets or WebSockets), consider using a different
    base class or implementing your own connection management.
    """

    def __init__(
        self,
        device_config: DeviceConfig,
        loop: AbstractEventLoop | None,
        config_manager: BaseConfigManager | None = None,
        driver=None,
    ) -> None:
        """
        Initialize the device.

        :param device_config: Configuration for this device
        :param loop: Event loop for async operations
        :param config_manager: Configuration manager instance
        """
        super().__init__(
            device_config=device_config,
            loop=loop,
            config_manager=config_manager,
            driver=driver,
        )

        # TODO: Initialize your device client/connection here
        # Example:
        # self._client = YourDeviceClient(
        #     host=device_config.address,
        #     port=device_config.port,
        # )

        # State dicts keyed by device_id (identifier), not entity_id.
        # Seed with defaults so accessors always return a valid object.
        self._media_player_attributes: dict[str, MediaPlayerAttributes] = {
            device_config.identifier: MediaPlayerAttributes(
                STATE=None,
                # TODO: Add other attributes your device supports
                # VOLUME=None,
                # MUTED=None,
                # SOURCE=None,
                # SOURCE_LIST=None,
            )
        }

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def identifier(self) -> str:
        """Return the device identifier."""
        return self._device_config.identifier

    @property
    def name(self) -> str:
        """Return the device name."""
        return self._device_config.name

    @property
    def address(self) -> str | None:
        """Return the device address."""
        return self._device_config.address

    @property
    def state(self) -> media_player.States | None:
        """Return the current power state."""
        attrs = self._media_player_attributes.get(self.identifier)
        return attrs.STATE if attrs else None

    @property
    def log_id(self) -> str:
        """Return a log identifier for debugging."""
        return self.name if self.name else self.identifier

    def get_media_player_attributes(self, device_id: str) -> MediaPlayerAttributes | None:
        """
        Return media player attributes for the given device_id.

        Called by the entity's sync_state() after push_update() fires.

        :param device_id: Device identifier (DeviceConfig.identifier)
        :return: Current MediaPlayerAttributes, or None if unknown
        """
        return self._media_player_attributes.get(device_id)

    # =========================================================================
    # Connection Management
    # =========================================================================

    async def verify_connection(self) -> None:
        """
        Verify connection to the device and emit current state.

        This method is called by the framework to check device connectivity
        and retrieve the current state. State updates are emitted via DeviceEvents.UPDATE.

        :raises: Exception if connection verification fails
        """
        _LOG.debug(
            "[%s] Verifying connection to device at %s", self.log_id, self.address
        )

        try:
            # TODO: Implement connection verification
            # This should:
            # 1. Connect to the device
            # 2. Query the current state
            # 3. Update internal state tracking
            # 4. Emit state update event

            # Example implementation:
            # state = await self._client.get_power_state()
            # self._power_state = media_player.States(state)

            _LOG.debug(
                "[%s] Connection verified, state: %s", self.log_id, self.state
            )

        except Exception as err:
            _LOG.error("[%s] Connection verification failed: %s", self.log_id, err)
            raise

    # =========================================================================
    # Power Control
    # =========================================================================

    async def power_on(self) -> None:
        """
        Turn on the device.

        TODO: Implement power on command for your device.
        """
        _LOG.debug("[%s] Powering on", self.log_id)
        # TODO: Send power on command
        # await self._client.power_on()

        if self.identifier in self._media_player_attributes:
            self._media_player_attributes[self.identifier].STATE = media_player.States.ON
        self.push_update()

    async def power_off(self) -> None:
        """
        Turn off the device.

        TODO: Implement power off command for your device.
        """
        _LOG.debug("[%s] Powering off", self.log_id)
        # TODO: Send power off command
        # await self._client.power_off()

        if self.identifier in self._media_player_attributes:
            self._media_player_attributes[self.identifier].STATE = media_player.States.OFF
        self.push_update()

    async def power_toggle(self) -> None:
        """
        Toggle the device power state.

        TODO: Implement power toggle or use power_on/power_off based on state.
        """
        _LOG.debug("[%s] Toggling power", self.log_id)

        if self.state == media_player.States.ON:
            await self.power_off()
        else:
            await self.power_on()

    # =========================================================================
    # Command Sending
    # =========================================================================

    async def send_command(self, command: str, **_kwargs: Any) -> None:
        """
        Send a command to the device.

        This is a generic command method that can be used for various operations.

        :param command: Command to send
        :param kwargs: Keyword arguments for the command
        """
        _LOG.debug("[%s] Sending command: %s", self.log_id, command)

        # TODO: Implement command routing, update _media_player_attributes, then call push_update()
        # Example:
        # match command:
        #     case "volume_up":
        #         await self._client.volume_up()
        #         self._media_player_attributes[self.identifier].VOLUME += 5
        #         self.push_update()
        #     case "volume_down":
        #         await self._client.volume_down()
        #         self._media_player_attributes[self.identifier].VOLUME -= 5
        #         self.push_update()
        #     case _:
        #         _LOG.warning("Unknown command: %s", command)

