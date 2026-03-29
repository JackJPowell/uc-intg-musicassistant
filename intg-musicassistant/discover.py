"""
Device Discovery Module.

Music Assistant servers advertise themselves on the local network using Zeroconf
under the service type ``_mass._tcp.local.``.  The service record contains the
server's properties dict (same data as the REST /api/server_info endpoint),
including the ``server_id`` used as our device identifier.

:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

import logging
from typing import Any
from zeroconf import IPVersion

from ucapi_framework import DiscoveredDevice
from ucapi_framework.discovery import MDNSDiscovery

_LOG = logging.getLogger(__name__)

# Music Assistant broadcasts on this service type (see music_assistant/controllers/discovery)
MA_MDNS_SERVICE_TYPE = "_mass._tcp.local."


class DeviceDiscovery(MDNSDiscovery):
    """
    Discover Music Assistant servers on the local network via mDNS.

    MA registers a ``_mass._tcp.local.`` Zeroconf record containing:
    - address / port  → used to build the WebSocket URL
    - ``server_id``   → used as the device identifier
    - ``friendly_name`` or ``server_name`` → human-readable label

    The default timeout of 5 seconds is usually sufficient; increase it on
    slow or heavily-loaded networks.
    """

    def __init__(self, timeout: int = 5) -> None:
        super().__init__(service_type=MA_MDNS_SERVICE_TYPE, timeout=timeout)

    def parse_mdns_service(self, service_info: Any) -> DiscoveredDevice | None:
        """
        Convert a zeroconf ServiceInfo for ``_mass._tcp.local.`` into a
        DiscoveredDevice.

        :param service_info: zeroconf ServiceInfo object
        :return: DiscoveredDevice or None if the record is incomplete
        """
        # Resolve the first usable IPv4 address
        addresses = service_info.parsed_addresses(IPVersion.V4Only)
        ip = next(
            (
                a
                for a in addresses
                if not a.startswith("127.") and not a.startswith("169.254.")
            ),
            None,
        )
        if not ip:
            _LOG.debug("MA mDNS record has no usable IPv4 address – skipping")
            return None

        port: int = service_info.port or 8095

        # Properties are bytes-encoded; decode defensively
        props: dict[str, str] = {}
        for k, v in (service_info.properties or {}).items():
            try:
                key = k.decode() if isinstance(k, bytes) else str(k)
                val = v.decode() if isinstance(v, bytes) else str(v)
                props[key] = val
            except Exception:  # pylint: disable=broad-except
                pass

        server_id = props.get("server_id") or props.get("id")
        if not server_id:
            # Fall back to the service name (strip the service type suffix)
            server_id = service_info.name.replace(
                f".{MA_MDNS_SERVICE_TYPE}", ""
            ).replace("-", "_")

        # MA's TXT record is ServerInfoMessage.to_dict() which has no friendly_name field.
        # The service instance name (before the first dot) is the server_id — not human-readable.
        # Build a friendly label from base_url host or fall back to "Music Assistant @ <ip>".
        base_url = props.get("base_url", "")
        if base_url:
            # e.g. "http://myserver.local:8095" → "myserver.local"
            host = base_url.split("//")[-1].split(":")[0]
            name = f"Music Assistant ({host})"
        else:
            name = f"Music Assistant ({ip})"

        # Prefer https if the server advertises it, fall back to http
        scheme = "https" if props.get("use_ssl") == "true" else "http"
        address = f"{scheme}://{ip}:{port}"

        _LOG.debug(
            "Discovered MA server: %s  id=%s  address=%s", name, server_id, address
        )

        return DiscoveredDevice(
            identifier=server_id.replace("-", "_"),
            name=name,
            address=address,
            extra_data={"port": port, "props": props},
        )
