# Integration Music Assistant Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

_Changes in the next release_

---

## v0.3.0 - 2026-04-25

### Added
- Source select entity re-enabled: one standalone select widget per MA player that exposes sources (Spotify, AirPlay, local library, etc.), allowing source switching directly from the Remote UI.

### Fixed
- Source select entity caused a connection timeout when the Remote fetched available entities. The `SelectEntity.options` property was returning the select options list (a `list[str]`) into the entity-level config field that ucapi expects to be a `dict` or absent — the Remote rejected the malformed definition and timed out. The fix ensures `options` returns `None` and the list is accessed via `select_options`.
- Bundled (PyInstaller) build crashed silently on startup due to missing dependencies. `aiohttp` (used directly in setup for authentication), `orjson`, and `mashumaro` (C-extension / dynamic deps of `music-assistant-models`) were absent from `requirements.txt` and not collected by PyInstaller.
- PyInstaller build now includes `--collect-all` for `aiohttp`, `orjson`, and `mashumaro` alongside the existing `zeroconf`, ensuring native extensions and dynamically-imported submodules are bundled correctly.

---

## v0.2.6 - 2026-04-23

### Fixed
- `ImportError` on startup caused by `BrowseMediaItem`, `BrowseOptions`, `BrowseResults`, `MediaClass`, `MediaContentType`, `SearchOptions`, and `SearchResults` moving from `ucapi.api_definitions` to `ucapi.media_player` in ucapi 0.6.0.

---

## v0.2.5 - 2026-04-18

### Changed
- Updated dependency from a local ucapi dev wheel to the published `ucapi==0.6.0` release.
- Updated project metadata: author name and repository URLs.

---

## v0.2.4 - 2026-04-04

### Fixed
- Browse drill-down into artists and albums now correctly returns results. Previously, tapping an artist or album produced an empty page
- Setup flow is now a two-step process: step one collects the server address, step two collects credentials. All recoverable failures return a correctable form instead of a hard error.
- You can now authenticate with your username and password and a long lived access token will be generated on your behalf. Your credentials are not stored

---

## v0.2.0 - 2026-03-29

### Added
- Full Music Assistant integration replacing the template skeleton.
- Media player entities for every MA player discovered on the server, with play/pause, stop, next, previous, seek, volume, mute, repeat, and shuffle support.
- Media browsing and search: navigate the MA library by artists, albums, tracks, playlists, and radio stations with paginated results.
- Play media from browse and search results directly on any player.
- Source and sound mode selection per player where the MA server reports them.
- Now Playing sensor showing the current artist and track title per player.
- Queue Position sensor showing the current track position within the active queue.
- Active Players sensor showing how many players are currently playing across the server.
- mDNS discovery of Music Assistant servers on the local network via the `_mass._tcp.local.` service type.
- Optional access token field in setup for password-protected MA servers.
- Persistent WebSocket connection with automatic reconnect and a watchdog that detects dropped connections.
- Initial state sync on connection so player state is correct immediately without waiting for a server push event.

### Changed
- Browse pagination now correctly signals when more pages are available, allowing the remote to load additional items beyond the first page.
- Idle players report state ON rather than OFF, reflecting that the player is connected and ready rather than powered down.
- Browser no longer cycles endlessly on leaf-level screens (track lists, radio stations) that have no further children to browse into.

### Fixed
- Player state showed UNAVAILABLE on first load until a server push event arrived.
- Browse results did not advance past the first page of artists, albums, tracks, playlists, or radio stations.

---

## v0.1.0 - 2025-12-03
### Added
- Initial template release based on ucapi-framework.
- Media player entity template with common features.
- Device communication template with connection management.
- Setup flow with manual device entry.
- mDNS device discovery template.
- Docker and Docker Compose configurations.
- Development environment with core-simulator.
