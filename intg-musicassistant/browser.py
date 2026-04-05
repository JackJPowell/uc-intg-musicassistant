"""
Music Assistant Media Browser.

Translates Music Assistant library/browse/search results into the ucapi
BrowseMediaItem / BrowseResults / SearchResults types consumed by the Remote.

Browse hierarchy:
  ROOT
  ├── Artists    (ARTIST, can_browse)
  │   └── <artist>  (ARTIST, can_browse → album list)
  │       └── <album> (ALBUM, can_browse → track list)
  │           └── <track> (TRACK, can_play)
  ├── Albums     (ALBUM, can_browse → track list)
  ├── Tracks     (TRACK, can_play)
  ├── Playlists  (PLAYLIST, can_browse → track list)
  └── Radio      (RADIO, can_play)

Search returns artists, albums, tracks, playlists, and radio stations.

:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from music_assistant_models.enums import MediaType
from music_assistant_models.media_items import (
    Album,
    Artist,
    ItemMapping,
    Playlist,
    Radio,
    Track,
)
from ucapi.api_definitions import (
    BrowseMediaItem,
    BrowseOptions,
    BrowseResults,
    MediaClass,
    MediaContentType,
    Pagination,
    SearchOptions,
    SearchResults,
)

if TYPE_CHECKING:
    from music_assistant_client import MusicAssistantClient

_LOG = logging.getLogger(__name__)

_DEFAULT_LIMIT = 50

# Well-known browse path prefixes
_ROOT_ID = "root"
_ARTISTS_ID = "library:artists"
_ALBUMS_ID = "library:albums"
_TRACKS_ID = "library:tracks"
_PLAYLISTS_ID = "library:playlists"
_RADIO_ID = "library:radio"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _paging(options: BrowseOptions) -> tuple[int, int]:
    """Return (offset, limit) from BrowseOptions paging field."""
    p = options.paging
    if p is None:
        return 0, _DEFAULT_LIMIT
    page = p.page or 1
    limit = min(max(p.limit or _DEFAULT_LIMIT, 1), _DEFAULT_LIMIT)
    return (page - 1) * limit, limit


def _pagination(page: int, limit: int, count: int, offset: int = 0) -> Pagination:
    """
    Build a Pagination object for the remote.

    ``count`` is the number of items returned on this page.  MA library calls
    don't expose a total-item count, so we infer whether more pages exist: if
    the page came back full we report one extra item beyond the current page so
    the remote knows to request the next page; if it came back short we're on
    the last page.
    """
    if count == limit:
        # Page is full — there may be more; report total as one beyond this page
        total = offset + limit + 1
    else:
        # Short page — this is the last one
        total = offset + count
    return Pagination(page=page, limit=limit, count=total)


def _image_url(client: MusicAssistantClient, item: Any) -> str | None:
    """Try to get a thumbnail URL for a media item."""
    try:
        image = getattr(item, "image", None)
        if image is None:
            metadata = getattr(item, "metadata", None)
            if metadata and getattr(metadata, "images", None):
                image = metadata.images[0]
        if image is not None:
            return client.get_image_url(image)
    except Exception:  # pylint: disable=broad-except
        pass
    return None


def _item_uri(item: Any) -> str:
    """Return the MA URI for any media item."""
    return getattr(item, "uri", None) or str(getattr(item, "item_id", ""))


def _track_item(client: MusicAssistantClient, track: Track | ItemMapping) -> BrowseMediaItem:
    artist_str: str | None = None
    album_str: str | None = None
    if isinstance(track, Track):
        artist_str = track.artist_str or None
        album_str = track.album.name if isinstance(track.album, Album) else (track.album.name if track.album else None)
    return BrowseMediaItem(
        title=track.name,
        media_class=MediaClass.TRACK,
        media_type=MediaContentType.TRACK,
        media_id=_item_uri(track),
        can_play=True,
        subtitle=artist_str,
        artist=artist_str,
        album=album_str,
        duration=getattr(track, "duration", None),
        thumbnail=_image_url(client, track),
    )


def _album_item(client: MusicAssistantClient, album: Album | ItemMapping, *, can_browse: bool = True) -> BrowseMediaItem:
    artist_str: str | None = None
    if isinstance(album, Album):
        artist_str = "/".join(a.name for a in album.artists) if album.artists else None
    return BrowseMediaItem(
        title=album.name,
        media_class=MediaClass.ALBUM,
        media_type=MediaContentType.ALBUM,
        media_id=_item_uri(album),
        can_browse=can_browse,
        can_play=True,
        subtitle=artist_str,
        artist=artist_str,
        thumbnail=_image_url(client, album),
    )


def _artist_item(client: MusicAssistantClient, artist: Artist | ItemMapping) -> BrowseMediaItem:
    return BrowseMediaItem(
        title=artist.name,
        media_class=MediaClass.ARTIST,
        media_type=MediaContentType.ARTIST,
        media_id=_item_uri(artist),
        can_browse=True,
        can_play=True,
        thumbnail=_image_url(client, artist),
    )


def _playlist_item(client: MusicAssistantClient, playlist: Playlist | ItemMapping) -> BrowseMediaItem:
    return BrowseMediaItem(
        title=playlist.name,
        media_class=MediaClass.PLAYLIST,
        media_type=MediaContentType.PLAYLIST,
        media_id=_item_uri(playlist),
        can_browse=True,
        can_play=True,
        thumbnail=_image_url(client, playlist),
    )


def _radio_item(client: MusicAssistantClient, radio: Radio | ItemMapping) -> BrowseMediaItem:
    return BrowseMediaItem(
        title=radio.name,
        media_class=MediaClass.RADIO,
        media_type=MediaContentType.RADIO,
        media_id=_item_uri(radio),
        can_play=True,
        thumbnail=_image_url(client, radio),
    )


def _parse_ma_uri(uri: str) -> tuple[MediaType, str, str]:
    """
    Parse a Music Assistant URI into (media_type, provider, item_id).

    MA URIs have the form: ``{provider}://{media_type}/{item_id}``
    e.g. ``library://artist/123``  ``spotify://album/xyz``

    Raises ``ValueError`` if the URI cannot be parsed.
    """
    # Split off the provider (everything before "://")
    if "://" not in uri:
        raise ValueError(f"Not an MA URI: {uri!r}")
    provider, rest = uri.split("://", 1)
    # rest is "{media_type}/{item_id}" — item_id may itself contain slashes
    parts = rest.split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"Cannot parse MA URI path: {uri!r}")
    media_type_str, item_id = parts
    try:
        media_type = MediaType(media_type_str)
    except ValueError as exc:
        raise ValueError(f"Unknown media_type {media_type_str!r} in URI: {uri!r}") from exc
    return media_type, provider, item_id


def _generic_item(client: MusicAssistantClient, item: Any) -> BrowseMediaItem:
    """Fallback for ItemMappings and unknown types coming from MA browse."""
    mt = getattr(item, "media_type", None)
    if mt == MediaType.TRACK:
        return _track_item(client, item)
    if mt == MediaType.ALBUM:
        return _album_item(client, item)
    if mt == MediaType.ARTIST:
        return _artist_item(client, item)
    if mt == MediaType.PLAYLIST:
        return _playlist_item(client, item)
    if mt in (MediaType.RADIO, MediaType.PLUGIN_SOURCE):
        return _radio_item(client, item)
    # Generic folder / unknown — only allow browsing if it has an item_id that looks like a container
    return BrowseMediaItem(
        title=getattr(item, "name", str(item)),
        media_class=MediaClass.DIRECTORY,
        media_type=MediaContentType.MUSIC,
        media_id=_item_uri(item),
        can_browse=True,
        can_play=getattr(item, "is_playable", False),
        thumbnail=_image_url(client, item),
    )


# ---------------------------------------------------------------------------
# Browse
# ---------------------------------------------------------------------------


async def browse(client: MusicAssistantClient, options: BrowseOptions) -> BrowseResults:
    """
    Return browse results for the given options.

    The ``media_id`` field selects what to return:
    - ``None`` / ``"root"``        → library root directories
    - ``"library:artists"``        → paginated artist list
    - ``"library:albums"``         → paginated album list
    - ``"library:tracks"``         → paginated track list
    - ``"library:playlists"``      → paginated playlist list
    - ``"library:radio"``          → paginated radio list
    - any MA URI (``provider://…``) → delegate to MA browse, return children
    """
    media_id = options.media_id or _ROOT_ID
    offset, limit = _paging(options)
    p = options.paging
    page = (p.page or 1) if p else 1

    # ── Root ────────────────────────────────────────────────────────────────
    if media_id == _ROOT_ID:
        root = BrowseMediaItem(
            title="Music Library",
            media_class=MediaClass.DIRECTORY,
            media_type=MediaContentType.MUSIC,
            media_id=_ROOT_ID,
            can_browse=True,
            items=[
                BrowseMediaItem(title="Artists", media_class=MediaClass.ARTIST, media_type=MediaContentType.ARTIST, media_id=_ARTISTS_ID, can_browse=True),
                BrowseMediaItem(title="Albums", media_class=MediaClass.ALBUM, media_type=MediaContentType.ALBUM, media_id=_ALBUMS_ID, can_browse=True),
                BrowseMediaItem(title="Tracks", media_class=MediaClass.TRACK, media_type=MediaContentType.TRACK, media_id=_TRACKS_ID, can_browse=True),
                BrowseMediaItem(title="Playlists", media_class=MediaClass.PLAYLIST, media_type=MediaContentType.PLAYLIST, media_id=_PLAYLISTS_ID, can_browse=True),
                BrowseMediaItem(title="Radio", media_class=MediaClass.RADIO, media_type=MediaContentType.RADIO, media_id=_RADIO_ID, can_browse=True),
            ],
        )
        return BrowseResults(media=root, pagination=_pagination(1, 5, 5, 0))

    # ── Library sections ─────────────────────────────────────────────────────
    if media_id == _ARTISTS_ID:
        items = await client.music.get_library_artists(limit=limit, offset=offset)
        children = [_artist_item(client, a) for a in items]
        root = BrowseMediaItem(title="Artists", media_class=MediaClass.ARTIST, media_type=MediaContentType.ARTIST, media_id=_ARTISTS_ID, can_browse=True, items=children)
        return BrowseResults(media=root, pagination=_pagination(page, limit, len(children), offset))

    if media_id == _ALBUMS_ID:
        items = await client.music.get_library_albums(limit=limit, offset=offset)
        children = [_album_item(client, a) for a in items]
        root = BrowseMediaItem(title="Albums", media_class=MediaClass.ALBUM, media_type=MediaContentType.ALBUM, media_id=_ALBUMS_ID, can_browse=True, items=children)
        return BrowseResults(media=root, pagination=_pagination(page, limit, len(children), offset))

    if media_id == _TRACKS_ID:
        items = await client.music.get_library_tracks(limit=limit, offset=offset)
        children = [_track_item(client, t) for t in items]
        root = BrowseMediaItem(title="Tracks", media_class=MediaClass.TRACK, media_type=MediaContentType.TRACK, media_id=_TRACKS_ID, can_browse=True, items=children)
        return BrowseResults(media=root, pagination=_pagination(page, limit, len(children), offset))

    if media_id == _PLAYLISTS_ID:
        items = await client.music.get_library_playlists(limit=limit, offset=offset)
        children = [_playlist_item(client, p) for p in items]
        root = BrowseMediaItem(title="Playlists", media_class=MediaClass.PLAYLIST, media_type=MediaContentType.PLAYLIST, media_id=_PLAYLISTS_ID, can_browse=True, items=children)
        return BrowseResults(media=root, pagination=_pagination(page, limit, len(children), offset))

    if media_id == _RADIO_ID:
        items = await client.music.get_library_radios(limit=limit, offset=offset)
        children = [_radio_item(client, r) for r in items]
        root = BrowseMediaItem(title="Radio", media_class=MediaClass.RADIO, media_type=MediaContentType.RADIO, media_id=_RADIO_ID, can_browse=True, items=children)
        return BrowseResults(media=root, pagination=_pagination(page, limit, len(children), offset))

    # ── MA URI → artist detail / album detail / generic MA browse ─────────────
    # MA URIs have the form: {provider}://{media_type}/{item_id}
    # e.g. library://artist/123  or  spotify://album/xyz
    # For artist and album pages we use the dedicated API calls so the remote
    # gets a properly populated list; falling back to client.music.browse() for
    # everything else (provider root folders, etc.).
    _LEAF_TYPES = (MediaType.TRACK, MediaType.RADIO, MediaType.PLUGIN_SOURCE)
    try:
        parsed_type, parsed_provider, parsed_item_id = _parse_ma_uri(media_id)
    except ValueError:
        parsed_type = parsed_provider = parsed_item_id = None

    try:
        if parsed_type == MediaType.ARTIST and parsed_item_id and parsed_provider:
            # Artist detail → show albums for that artist
            _LOG.debug("browse artist %s / %s", parsed_provider, parsed_item_id)
            albums = await client.music.get_artist_albums(
                item_id=parsed_item_id,
                provider_instance_id_or_domain=parsed_provider,
            )
            # Also fetch the artist object so we can use its name as title
            try:
                artist_obj = await client.music.get_artist(
                    item_id=parsed_item_id,
                    provider_instance_id_or_domain=parsed_provider,
                )
                title = artist_obj.name
            except Exception:  # pylint: disable=broad-except
                title = media_id.split("/")[-1] or media_id
            all_items = albums
            children = [_album_item(client, a) for a in all_items[offset: offset + limit]]
            root = BrowseMediaItem(
                title=title,
                media_class=MediaClass.ARTIST,
                media_type=MediaContentType.ARTIST,
                media_id=media_id,
                can_browse=True,
                items=children,
            )
            return BrowseResults(media=root, pagination=_pagination(page, limit, len(children), offset))

        if parsed_type == MediaType.ALBUM and parsed_item_id and parsed_provider:
            # Album detail → show tracks for that album
            _LOG.debug("browse album %s / %s", parsed_provider, parsed_item_id)
            tracks = await client.music.get_album_tracks(
                item_id=parsed_item_id,
                provider_instance_id_or_domain=parsed_provider,
            )
            # Fetch album object for the title
            try:
                album_obj = await client.music.get_album(
                    item_id=parsed_item_id,
                    provider_instance_id_or_domain=parsed_provider,
                )
                title = album_obj.name
            except Exception:  # pylint: disable=broad-except
                title = media_id.split("/")[-1] or media_id
            all_items = tracks
            children = [_track_item(client, t) for t in all_items[offset: offset + limit]]
            root = BrowseMediaItem(
                title=title,
                media_class=MediaClass.ALBUM,
                media_type=MediaContentType.ALBUM,
                media_id=media_id,
                can_browse=True,
                items=children,
            )
            return BrowseResults(media=root, pagination=_pagination(page, limit, len(children), offset))

        if parsed_type == MediaType.PLAYLIST and parsed_item_id and parsed_provider:
            # Playlist detail → show tracks for that playlist
            _LOG.debug("browse playlist %s / %s", parsed_provider, parsed_item_id)
            tracks = await client.music.get_playlist_tracks(
                item_id=parsed_item_id,
                provider_instance_id_or_domain=parsed_provider,
            )
            try:
                playlist_obj = await client.music.get_playlist(
                    item_id=parsed_item_id,
                    provider_instance_id_or_domain=parsed_provider,
                )
                title = playlist_obj.name
            except Exception:  # pylint: disable=broad-except
                title = media_id.split("/")[-1] or media_id
            all_items = tracks
            children = [_track_item(client, t) for t in all_items[offset: offset + limit]]
            root = BrowseMediaItem(
                title=title,
                media_class=MediaClass.PLAYLIST,
                media_type=MediaContentType.PLAYLIST,
                media_id=media_id,
                can_browse=True,
                items=children,
            )
            return BrowseResults(media=root, pagination=_pagination(page, limit, len(children), offset))

        # Generic fallback: delegate to MA browse (handles provider root folders, etc.)
        ma_items = await client.music.browse(path=media_id)
        children = [_generic_item(client, i) for i in ma_items[offset: offset + limit]]
        # Don't mark the wrapper as browsable if all children are leaf items
        # (tracks/radio) — doing so causes the remote to cycle on an empty
        # directory when it tries to browse into the same URI again.
        has_containers = any(
            getattr(i, "media_type", None) not in _LEAF_TYPES
            for i in ma_items
        )
        title = media_id.split("/")[-1] or media_id
        root = BrowseMediaItem(
            title=title,
            media_class=MediaClass.DIRECTORY,
            media_type=MediaContentType.MUSIC,
            media_id=media_id,
            can_browse=bool(children) and has_containers,
            items=children,
        )
        return BrowseResults(media=root, pagination=_pagination(page, limit, len(children), offset))
    except Exception as exc:  # pylint: disable=broad-except
        _LOG.warning("MA browse failed for %s: %s", media_id, exc)
        # can_browse=False prevents the remote from retrying the same path in a loop
        empty = BrowseMediaItem(title=media_id, media_class=MediaClass.DIRECTORY, media_type=MediaContentType.MUSIC, media_id=media_id, can_browse=False, items=[])
        return BrowseResults(media=empty, pagination=_pagination(1, 0, 0, 0))


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


async def search(client: MusicAssistantClient, options: SearchOptions) -> SearchResults:
    """
    Search the MA library for the given query.

    Returns tracks, albums, artists, playlists, and radio stations that
    contain the query string (case-insensitive, handled by MA server).
    """
    query = (options.query or "").strip()
    if not query:
        return SearchResults(media=[], pagination=_pagination(1, 0, 0, 0))

    limit = _DEFAULT_LIMIT
    if options.paging and options.paging.limit:
        limit = min(options.paging.limit, _DEFAULT_LIMIT)

    _LOG.debug("MA search: %r (limit=%d)", query, limit)

    ma_results = await client.music.search(
        search_query=query,
        media_types=[MediaType.TRACK, MediaType.ALBUM, MediaType.ARTIST, MediaType.PLAYLIST, MediaType.RADIO],
        limit=limit,
    )

    items: list[BrowseMediaItem] = []

    for track in ma_results.tracks:
        items.append(_track_item(client, track))
    for album in ma_results.albums:
        items.append(_album_item(client, album, can_browse=True))
    for artist in ma_results.artists:
        items.append(_artist_item(client, artist))
    for playlist in ma_results.playlists:
        items.append(_playlist_item(client, playlist))
    for radio in ma_results.radio:
        items.append(_radio_item(client, radio))

    _LOG.debug("MA search %r → %d results", query, len(items))
    return SearchResults(media=items, pagination=_pagination(1, len(items), len(items)))
