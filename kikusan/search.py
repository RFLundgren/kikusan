"""YouTube Music search and explore functionality using ytmusicapi."""

import logging
from dataclasses import dataclass, field

from ytmusicapi import YTMusic

logger = logging.getLogger(__name__)


@dataclass
class Track:
    """Represents a music track from YouTube Music."""

    video_id: str
    title: str
    artist: str
    artists: list[str]
    album: str | None
    duration_seconds: int
    thumbnail_url: str | None
    view_count: str | None

    @property
    def duration_display(self) -> str:
        """Format duration as MM:SS."""
        minutes = self.duration_seconds // 60
        seconds = self.duration_seconds % 60
        return f"{minutes}:{seconds:02d}"


@dataclass
class Album:
    """Represents an album from YouTube Music."""

    browse_id: str
    title: str
    artist: str
    year: int | None
    track_count: int | None
    thumbnail_url: str | None


@dataclass
class MoodCategory:
    """A single mood/genre category with a params identifier for fetching playlists."""

    title: str
    params: str


@dataclass
class MoodSection:
    """A section of mood/genre categories (e.g., 'Genres', 'Moods & moments')."""

    title: str
    categories: list[MoodCategory] = field(default_factory=list)


@dataclass
class MoodPlaylist:
    """A playlist from a mood/genre category."""

    playlist_id: str
    title: str
    thumbnail_url: str | None
    author: str | None


@dataclass
class ChartTrack:
    """A track from the music charts."""

    video_id: str
    title: str
    artist: str
    artists: list[str]
    album: str | None
    thumbnail_url: str | None
    rank: str | None
    trend: str | None
    view_count: str | None = None
    duration_seconds: int = 0

    @property
    def duration_display(self) -> str:
        """Format duration as MM:SS."""
        minutes = self.duration_seconds // 60
        seconds = self.duration_seconds % 60
        return f"{minutes}:{seconds:02d}"


@dataclass
class ChartArtist:
    """An artist from the music charts."""

    browse_id: str
    title: str
    thumbnail_url: str | None
    rank: str | None
    trend: str | None


@dataclass
class Charts:
    """Chart data for a country."""

    country: str
    tracks: list[ChartTrack] = field(default_factory=list)
    artists: list[ChartArtist] = field(default_factory=list)


def search(query: str, limit: int = 20) -> list[Track]:
    """
    Search YouTube Music for tracks.

    Args:
        query: Search query string
        limit: Maximum number of results to return

    Returns:
        List of Track objects matching the query

    Raises:
        Exception: If YouTube Music API fails (e.g., JSONDecodeError, network error)
    """
    yt = YTMusic()
    try:
        results = yt.search(query, filter="songs", limit=limit)
    except Exception as e:
        logger.error("YouTube Music search failed for query '%s': %s", query, e)
        raise

    tracks = []
    for item in results:
        if item.get("resultType") != "song":
            continue

        # Extract artist name(s) - keep full list for multi-value tags
        artist_objects = item.get("artists", [])
        artist_names = [a["name"] for a in artist_objects] if artist_objects else ["Unknown Artist"]
        artist_name = artist_names[0]  # Primary artist for display/compatibility

        # Extract album name
        album = item.get("album")
        album_name = album["name"] if album else None

        # Extract duration in seconds
        duration_text = item.get("duration", "0:00")
        duration_seconds = _parse_duration(duration_text)

        # Extract thumbnail URL (prefer larger size)
        thumbnails = item.get("thumbnails", [])
        thumbnail_url = thumbnails[-1]["url"] if thumbnails else None

        # Extract view count (formatted string like "1.9B", "47M", etc.)
        view_count = item.get("views")

        tracks.append(
            Track(
                video_id=item["videoId"],
                title=item.get("title", "Unknown Title"),
                artist=artist_name,
                artists=artist_names,
                album=album_name,
                duration_seconds=duration_seconds,
                thumbnail_url=thumbnail_url,
                view_count=view_count,
            )
        )

    logger.info("Found %d tracks for query: %s", len(tracks), query)
    return tracks


def search_albums(query: str, limit: int = 20) -> list[Album]:
    """
    Search YouTube Music for albums.

    Args:
        query: Search query string
        limit: Maximum number of results to return

    Returns:
        List of Album objects matching the query

    Raises:
        Exception: If YouTube Music API fails (e.g., JSONDecodeError, network error)
    """
    yt = YTMusic()
    try:
        results = yt.search(query, filter="albums", limit=limit)
    except Exception as e:
        logger.error("YouTube Music album search failed for query '%s': %s", query, e)
        raise

    albums = []
    for item in results:
        if item.get("resultType") != "album":
            continue

        # Extract artist name(s)
        artists = item.get("artists", [])
        artist_name = artists[0]["name"] if artists else "Unknown Artist"

        # Extract year
        year_str = item.get("year")
        year = int(year_str) if year_str else None

        # Extract track count
        track_count = item.get("trackCount")

        # Extract thumbnail URL (prefer larger size)
        thumbnails = item.get("thumbnails", [])
        thumbnail_url = thumbnails[-1]["url"] if thumbnails else None

        albums.append(
            Album(
                browse_id=item["browseId"],
                title=item.get("title", "Unknown Album"),
                artist=artist_name,
                year=year,
                track_count=track_count,
                thumbnail_url=thumbnail_url,
            )
        )

    logger.info("Found %d albums for query: %s", len(albums), query)
    return albums


def get_album_tracks(browse_id: str) -> list[Track]:
    """
    Get all tracks for an album.

    Args:
        browse_id: YouTube Music album browse ID

    Returns:
        List of Track objects from the album

    Raises:
        Exception: If YouTube Music API fails (e.g., JSONDecodeError, network error)
    """
    yt = YTMusic()
    try:
        album_info = yt.get_album(browse_id)
    except Exception as e:
        logger.error("YouTube Music get_album failed for browse_id '%s': %s", browse_id, e)
        raise

    tracks = []
    for item in album_info.get("tracks", []):
        # Extract artist name(s) - keep full list for multi-value tags
        artist_objects = item.get("artists", [])
        artist_names = [a["name"] for a in artist_objects] if artist_objects else ["Unknown Artist"]
        artist_name = artist_names[0]  # Primary artist for display/compatibility

        # Extract duration in seconds
        duration_text = item.get("duration", "0:00")
        duration_seconds = _parse_duration(duration_text)

        # Extract thumbnail URL from album info (prefer larger size)
        thumbnails = album_info.get("thumbnails", [])
        thumbnail_url = thumbnails[-1]["url"] if thumbnails else None

        tracks.append(
            Track(
                video_id=item["videoId"],
                title=item.get("title", "Unknown Title"),
                artist=artist_name,
                artists=artist_names,
                album=album_info.get("title"),
                duration_seconds=duration_seconds,
                thumbnail_url=thumbnail_url,
                view_count=None,
            )
        )

    logger.info("Found %d tracks in album: %s", len(tracks), album_info.get("title"))
    return tracks


def get_mood_categories() -> list[MoodSection]:
    """Fetch mood & genre categories from YouTube Music.

    Returns:
        List of MoodSection objects, each containing a section title and list of categories.
    """
    yt = YTMusic()
    try:
        raw = yt.get_mood_categories()
    except Exception as e:
        logger.error("YouTube Music get_mood_categories failed: %s", e)
        raise

    sections = []
    for section_title, categories in raw.items():
        items = [
            MoodCategory(title=c.get("title", "Unknown"), params=c.get("params", ""))
            for c in categories
        ]
        sections.append(MoodSection(title=section_title, categories=items))

    logger.info("Found %d mood/genre sections", len(sections))
    return sections


def get_mood_playlists(params: str) -> list[MoodPlaylist]:
    """Fetch playlists for a mood/genre category.

    Some mood/genre categories return mixed content: some sections contain
    playlist items (musicTwoRowItemRenderer) while others contain song items
    (musicResponsiveListItemRenderer). The upstream ytmusicapi library crashes
    with a KeyError when it encounters the unexpected renderer type.

    This function first attempts the standard ytmusicapi call. If it fails
    with a KeyError (the musicTwoRowItemRenderer issue), it falls back to
    manual response parsing that skips sections with incompatible renderers
    and handles individual item parse failures gracefully.

    Args:
        params: Category params string from get_mood_categories()

    Returns:
        List of MoodPlaylist objects for the given category.
    """
    yt = YTMusic()
    try:
        raw = yt.get_mood_playlists(params)
    except KeyError as e:
        logger.warning(
            "ytmusicapi get_mood_playlists KeyError for params '%s': %s. "
            "Falling back to manual parsing.",
            params,
            e,
        )
        raw = _get_mood_playlists_fallback(yt, params)
    except Exception as e:
        logger.error("YouTube Music get_mood_playlists failed for params '%s': %s", params, e)
        raise

    playlists = []
    for item in raw:
        thumbnails = item.get("thumbnails", [])
        thumbnail_url = thumbnails[-1]["url"] if thumbnails else None
        playlists.append(
            MoodPlaylist(
                playlist_id=item.get("playlistId", ""),
                title=item.get("title", "Unknown"),
                thumbnail_url=thumbnail_url,
                author=item.get("author", None),
            )
        )

    logger.info("Found %d playlists for mood/genre params", len(playlists))
    return playlists


def _get_mood_playlists_fallback(yt: YTMusic, params: str) -> list[dict]:
    """Manually parse mood playlists from the raw YouTube Music API response.

    This fallback handles cases where the upstream ytmusicapi get_mood_playlists
    crashes because some response sections contain musicResponsiveListItemRenderer
    items (individual songs) instead of musicTwoRowItemRenderer items (playlists).

    The function skips sections with incompatible renderers and handles individual
    item parse failures within valid sections.

    Args:
        yt: YTMusic instance (reused from caller to avoid re-initialization)
        params: Category params string from get_mood_categories()

    Returns:
        List of raw playlist dictionaries (same format as ytmusicapi output).
    """
    from ytmusicapi.navigation import nav, SINGLE_COLUMN_TAB, SECTION_LIST
    from ytmusicapi.parsers.browsing import (
        CAROUSEL_CONTENTS,
        GRID_ITEMS,
        parse_playlist,
    )

    MTRIR_KEY = "musicTwoRowItemRenderer"

    response = yt._send_request(
        "browse",
        {"browseId": "FEmusic_moods_and_genres_category", "params": params},
    )

    playlists: list[dict] = []

    try:
        sections = nav(response, SINGLE_COLUMN_TAB + SECTION_LIST)
    except Exception as e:
        logger.error("Fallback: failed to navigate mood playlists response: %s", e)
        return []

    for section_idx, section in enumerate(sections):
        # Determine content path based on section renderer type
        path: list[str] = []
        if "gridRenderer" in section:
            path = list(GRID_ITEMS)
        elif "musicCarouselShelfRenderer" in section:
            path = list(CAROUSEL_CONTENTS)
        elif "musicImmersiveCarouselShelfRenderer" in section:
            path = ["musicImmersiveCarouselShelfRenderer", "contents"]

        if not path:
            continue

        try:
            results = nav(section, path)
        except Exception:
            logger.debug("Fallback: failed to navigate section %d, skipping", section_idx)
            continue

        if not results:
            continue

        # Skip sections that don't contain playlist items (musicTwoRowItemRenderer)
        if MTRIR_KEY not in results[0]:
            logger.debug(
                "Fallback: section %d uses %s, skipping (not playlist items)",
                section_idx,
                list(results[0].keys()),
            )
            continue

        # Parse each item individually, skipping items that fail
        for item_idx, result in enumerate(results):
            if MTRIR_KEY not in result:
                continue
            try:
                parsed = parse_playlist(result[MTRIR_KEY])
                playlists.append(parsed)
            except Exception as e:
                logger.debug(
                    "Fallback: failed to parse playlist item %d in section %d: %s",
                    item_idx,
                    section_idx,
                    e,
                )

    logger.info(
        "Fallback parsing recovered %d playlists for mood/genre params '%s'",
        len(playlists),
        params,
    )
    return playlists


def get_charts(country: str = "ZZ") -> Charts:
    """Fetch chart data (top songs, artists) for a country.

    ytmusicapi get_charts returns:
      - videos: list of playlist references [{title, playlistId, thumbnails}, ...]
      - artists: flat list of artist objects [{title, browseId, rank, trend, ...}, ...]
      - genres: (country-specific) list of genre playlist references
      - countries: {selected, options}

    We fetch tracks from the first video playlist to populate chart tracks.

    Args:
        country: ISO 3166-1 Alpha-2 country code. Default 'ZZ' for global charts.

    Returns:
        Charts object with tracks and artists.
    """
    yt = YTMusic()
    try:
        raw = yt.get_charts(country)
    except Exception as e:
        logger.error("YouTube Music get_charts failed for country '%s': %s", country, e)
        raise

    # Videos section is a list of playlist references -- try each until one succeeds.
    # Some entries use album-style IDs (OLAK5uy_...) that fail with get_playlist,
    # so we iterate through all playlist references and use the first that works.
    tracks = []
    video_playlists = raw.get("videos", [])
    if isinstance(video_playlists, list):
        for playlist_ref in video_playlists:
            playlist_id = playlist_ref.get("playlistId", "")
            if not playlist_id:
                continue
            try:
                playlist_data = yt.get_playlist(playlist_id, limit=100)
                for rank_idx, item in enumerate(playlist_data.get("tracks", []), 1):
                    video_id = item.get("videoId", "")
                    if not video_id:
                        continue
                    artist_objects = item.get("artists", [])
                    artist_names = [a["name"] for a in artist_objects] if artist_objects else ["Unknown Artist"]
                    thumbnails = item.get("thumbnails", [])
                    album_obj = item.get("album")

                    # Extract duration
                    duration_text = item.get("duration", "0:00")
                    duration_seconds = item.get("duration_seconds") or _parse_duration(duration_text)

                    # Extract view count (ytmusicapi playlist tracks may have views)
                    view_count = item.get("views")

                    tracks.append(
                        ChartTrack(
                            video_id=video_id,
                            title=item.get("title", "Unknown"),
                            artist=artist_names[0],
                            artists=artist_names,
                            album=album_obj.get("name") if isinstance(album_obj, dict) else None,
                            thumbnail_url=thumbnails[-1]["url"] if thumbnails else None,
                            rank=str(rank_idx),
                            trend=None,
                            view_count=view_count,
                            duration_seconds=duration_seconds,
                        )
                    )
                break  # Successfully fetched tracks, stop trying other playlists
            except Exception as e:
                logger.warning("Failed to fetch chart playlist '%s': %s, trying next", playlist_id, e)

    # Artists section is a flat list of artist objects (not a dict with 'items')
    artists = []
    artist_list = raw.get("artists", [])
    if isinstance(artist_list, list):
        for item in artist_list:
            thumbnails = item.get("thumbnails", [])
            artists.append(
                ChartArtist(
                    browse_id=item.get("browseId", ""),
                    title=item.get("title", "Unknown"),
                    thumbnail_url=thumbnails[-1]["url"] if thumbnails else None,
                    rank=item.get("rank"),
                    trend=item.get("trend"),
                )
            )

    logger.info("Found %d chart tracks and %d chart artists for %s", len(tracks), len(artists), country)
    return Charts(country=country, tracks=tracks, artists=artists)


def get_playlist_tracks(playlist_id: str) -> list[Track]:
    """Get tracks from a YouTube Music playlist.

    Args:
        playlist_id: YouTube Music playlist ID

    Returns:
        List of Track objects from the playlist.
    """
    yt = YTMusic()
    try:
        raw = yt.get_playlist(playlist_id)
    except Exception as e:
        logger.error("YouTube Music get_playlist failed for playlist_id '%s': %s", playlist_id, e)
        raise

    tracks = []
    for item in raw.get("tracks", []):
        video_id = item.get("videoId")
        if not video_id:
            continue

        artist_objects = item.get("artists", [])
        artist_names = [a["name"] for a in artist_objects] if artist_objects else ["Unknown Artist"]
        artist_name = artist_names[0]

        album_obj = item.get("album")
        album_name = album_obj.get("name") if isinstance(album_obj, dict) else None

        duration_text = item.get("duration", "0:00")
        duration_seconds = item.get("duration_seconds") or _parse_duration(duration_text)

        thumbnails = item.get("thumbnails", [])
        thumbnail_url = thumbnails[-1]["url"] if thumbnails else None

        tracks.append(
            Track(
                video_id=video_id,
                title=item.get("title", "Unknown Title"),
                artist=artist_name,
                artists=artist_names,
                album=album_name,
                duration_seconds=duration_seconds,
                thumbnail_url=thumbnail_url,
                view_count=None,
            )
        )

    logger.info("Found %d tracks in playlist: %s", len(tracks), raw.get("title", playlist_id))
    return tracks


def _parse_duration(duration_text: str) -> int:
    """Parse duration string (e.g., '3:45') to seconds."""
    parts = duration_text.split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    elif len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    return 0
