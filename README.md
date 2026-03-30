# Unfolded Circle Integration for Music Assistant

Control [Music Assistant](https://music-assistant.io/) players from an [Unfolded Circle Remote Two or Remote 3](https://www.unfoldedcircle.com/).

Music Assistant is a free, open-source media player manager that lets you play music from streaming services and local libraries through network-connected speakers. This integration exposes each MA player as a media player entity on the remote, with full playback control, library browsing, and search.

## Features

- One media player entity per Music Assistant player, automatically discovered on connection
- Play, pause, stop, next/previous track, and seek
- Volume and mute control
- Repeat and shuffle toggle
- Source selection (where supported by the player)
- Browse the MA library by artists, albums, tracks, playlists, and radio stations with full pagination
- Search the MA library by keyword
- Play any browse or search result directly on a player
- Now Playing sensor showing the current artist and track title per player
- Queue Position sensor showing the track number within the active queue
- Active Players sensor showing how many players are currently playing
- Automatic mDNS discovery of Music Assistant servers on the local network
- Persistent WebSocket connection with automatic reconnect

## Requirements

- [Music Assistant](https://music-assistant.io/) server 2.x running on your network
- [Unfolded Circle Remote Two or Remote 3](https://www.unfoldedcircle.com/) with firmware supporting custom integrations

## Setup

### Automatic Discovery

The integration advertises itself over mDNS. If your remote and MA server are on the same network segment, the remote should discover the integration automatically.

### Manual Setup

Open the remote's web configurator, navigate to **Integrations**, and add the integration manually using the server URL:

```
http://<host>:<port>
```

The default Music Assistant port is `8095`.

### Access Token

If your Music Assistant server requires authentication, enter the access token during setup. Leave it blank if authentication is not enabled.

## Running the Integration

### Docker

```bash
docker run -d \
  --name=uc-intg-musicassistant \
  --network host \
  -v $(pwd)/config:/config \
  --restart unless-stopped \
  ghcr.io/jackjpowell/uc-intg-musicassistant:latest
```

### Docker Compose

```yaml
services:
  uc-intg-musicassistant:
    image: ghcr.io/jackjpowell/uc-intg-musicassistant:latest
    container_name: uc-intg-musicassistant
    network_mode: host
    volumes:
      - ./config:/config
    restart: unless-stopped
```

### Running Directly

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 intg-musicassistant/driver.py
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `UC_LOG_LEVEL` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `DEBUG` |
| `UC_CONFIG_HOME` | Configuration directory path | `/config` |
| `UC_INTEGRATION_INTERFACE` | Network interface to bind | `0.0.0.0` |
| `UC_INTEGRATION_HTTP_PORT` | HTTP port for the integration | `9090` |
| `UC_DISABLE_MDNS_PUBLISH` | Disable mDNS advertisement | `false` |

## Project Structure

```
intg-musicassistant/
├── browser.py        # Library browse and search handlers
├── const.py          # Constants, state maps, and configuration dataclass
├── device.py         # WebSocket connection lifecycle and MA command dispatch
├── discover.py       # mDNS discovery of MA servers
├── driver.py         # Main entry point
├── media_player.py   # Media player entity (one per MA player)
├── select_entity.py  # Select entities (repeat, shuffle, source)
├── sensor.py         # Sensor entities (now playing, queue position, active players)
└── setup.py          # Setup flow and user configuration forms
```

## License

Mozilla Public License Version 2.0 — see [LICENSE](LICENSE) for details.
