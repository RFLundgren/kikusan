# Project description

Kikusan is a tool to search and download music from youtube music. It must use yt-dlp in the background. It must be usable through CLI and also have a web app (subcommand "web"). The web app should be really simple, but must support search functionality. It should be deployable with docker and have an example docker-compose file. It must add lyrics via lrc files to the downloaded files (via https://lrclib.net/).

## Features

### Web UI
- Search functionality with results display
- View counts displayed for each song (e.g., "1.9B views", "47M views")
  - View counts are retrieved from ytmusicapi search results (no additional API calls needed)
  - Displayed alongside duration in the track metadata section
- Download button for each track
- Dark/light theme toggle
- Version display in header (dynamically loaded from `pyproject.toml` via `importlib.metadata`)
- **Explore tab**: Browse moods, genres, and music charts from YouTube Music
  - Three-level navigation: Categories -> Playlists -> Tracks (with breadcrumb nav)
  - Mood/genre categories displayed as clickable grid cards
  - Charts with country selector (11 countries + global)
  - View counts displayed for chart tracks and playlist tracks (when available from API)
  - Play preview button and Copy URL button on all explore track listings (charts and playlists)
  - Duration displayed alongside view counts in chart track metadata
  - "Download All" buttons for bulk queueing of playlist tracks and chart tracks
  - Reuses existing download queue infrastructure (`/api/queue/add`)
- **Multi-user playlist support**: When `KIKUSAN_MULTI_USER=true` (or `--multi-user` flag), parses the `Remote-User` header (set by reverse proxy SSO like Authelia) and prefixes the M3U playlist name with the username (e.g., `alice-webplaylist.m3u`)
  - Opt-in: requires `KIKUSAN_MULTI_USER=true` env var or `--multi-user` CLI flag
  - Falls back to shared playlist when header is absent or feature is disabled
  - Username sanitization: only `[a-zA-Z0-9._-]` allowed, max 64 chars
  - Implementation: `_get_remote_user()` in `kikusan/web/app.py`, `Config.effective_playlist_name()` in `kikusan/config.py`
  - Playlist name is resolved at request time and stored on `DownloadJob.playlist_name` for queue-based downloads

### Sync Safety Features
- **Cross-Reference Protection**: When `sync=True` for a playlist/plugin, songs are only deleted from disk if they are not referenced by any other playlist or plugin
- Implementation in `kikusan/reference_checker.py`: Scans all playlist and plugin state files before deletion
- Each deletion operation checks both `.kikusan/state/*.json` (playlists) and `.kikusan/plugin_state/*.json` (plugins)
- Songs are removed from the current playlist/plugin state even if the file is preserved due to other references

- **Navidrome Protection**: Prevents deletion of songs starred in Navidrome or in designated "keep" playlist
- Real-time API checks during sync operations via Subsonic API
- Batch caching for performance (fetches once per sync, not per file)
- Two-tier matching: path-based (fast/accurate) + metadata-based (fallback)
- Fail-safe behavior: keeps files if Navidrome is unreachable
- Opt-in via environment variables: NAVIDROME_URL, NAVIDROME_USER, NAVIDROME_PASSWORD, NAVIDROME_KEEP_PLAYLIST

### Filename Length Safety
- Filenames are truncated to `MAX_FILENAME_BYTES` (200 bytes) to prevent `[Errno 36] File name too long` errors
- Two layers of protection:
  1. **yt-dlp level**: `trim_file_name` option in `_get_ydl_opts()` and `_compute_filename()` truncates rendered filenames
  2. **Path component level**: `_sanitize_path_component()` truncates directory names (artist, album) in album mode
- `_truncate_to_bytes()` handles UTF-8 safely (never splits multi-byte characters)
- The constant `MAX_FILENAME_BYTES` is defined in `kikusan/config.py`

### Unavailable Video Cooldown
- When a video returns "Video unavailable" during download, the video ID is recorded with a timestamp
- Subsequent sync/download attempts skip that video until the cooldown period expires
- Storage: `.kikusan/unavailable.json` - maps video_id to failure record (timestamp, error, title, artist)
- Default cooldown: 168 hours (7 days), configurable via `KIKUSAN_UNAVAILABLE_COOLDOWN_HOURS` env var or `--unavailable-cooldown` CLI flag
- Set cooldown to 0 to disable the feature entirely
- Only "Video unavailable" errors trigger cooldown (not auth errors, network errors, etc.)
- Integrated into ALL download paths:
  - `kikusan/download.py`: `download()` (single video - checks cooldown + records on failure), `_download_single()` (URL-based single track), `_download_playlist()` (playlist entries), `download_url()` (URL info extraction)
  - `kikusan/cron/sync.py`: `download_new_tracks()` (additional pre-check before calling `download()`)
  - `kikusan/plugins/sync.py`: `_download_songs()` (additional pre-check before calling `download()`)
- `UnavailableCooldownError`: Custom exception raised by `download()` when a video is on cooldown, caught by CLI for user-friendly output
- `_extract_video_id_from_url()`: Helper to extract video ID from YouTube URLs for recording in `download_url()` path
- Implementation in `kikusan/unavailable.py`: Pattern matching, JSON persistence with atomic writes, cooldown logic
- Corrupted unavailable files are backed up and reset (same pattern as state files)

### Architecture Notes
- `kikusan/search.py`: Uses ytmusicapi to search and explore YouTube Music
  - Search: `search()`, `search_albums()`, `get_album_tracks()` — song/album search with view_count extraction
  - Explore: `get_mood_categories()`, `get_mood_playlists()`, `get_charts()`, `get_playlist_tracks()` — mood/genre browsing and chart data
  - `get_mood_playlists()`: Has fallback parsing (`_get_mood_playlists_fallback()`) for when ytmusicapi crashes with KeyError on `musicTwoRowItemRenderer`. Some mood/genre categories return mixed content: some sections contain playlist items (`musicTwoRowItemRenderer`) while others contain song items (`musicResponsiveListItemRenderer`). The fallback manually parses the raw YouTube Music API response, skipping incompatible sections and handling individual item parse failures gracefully.
  - `get_charts()`: ytmusicapi returns `videos` as a list of playlist references (not individual tracks) and `artists` as a flat list. The function fetches tracks from the first working video playlist via `get_playlist()`, with fallback to subsequent playlists if one fails (e.g. album-style IDs like `OLAK5uy_...` are not fetchable via `get_playlist`).
  - `ChartTrack` includes `view_count` (str|None) and `duration_seconds` (int) with a `duration_display` property (MM:SS format), extracted from playlist data in `get_charts()`
  - Metadata: `get_song_metadata()` — fetches clean title/artist/album/duration from `YTMusic().get_song()` and `get_watch_playlist()` for lyrics lookup enhancement
  - `SongMetadata` dataclass: title, artist, album (optional), duration_seconds — used by `lyrics.py` for lrclib.net lookups
  - `_get_album_from_watch_playlist()`: Extracts album name from watch playlist (not available in `get_song()` videoDetails)
  - `_get_metadata_from_watch_playlist()`: Full fallback when `get_song()` returns incomplete videoDetails
  - Data classes: `Track`, `Album`, `MoodCategory`, `MoodSection`, `MoodPlaylist`, `ChartTrack`, `ChartArtist`, `Charts`, `SongMetadata`
- `kikusan/web/app.py`: FastAPI backend with search, download, and explore endpoints
  - Explore endpoints: `GET /api/explore/moods`, `GET /api/explore/mood-playlists`, `GET /api/explore/charts`, `GET /api/explore/playlist/{playlist_id}/tracks`
- `kikusan/web/templates/index.html`: Single-page frontend with embedded JavaScript (Songs, Albums, Explore tabs)
- `kikusan/web/static/style.css`: Responsive CSS with dark/light themes, explore grid layouts
- `kikusan/reference_checker.py`: Cross-playlist/plugin reference checking for safe file deletion
  - Includes metadata extraction using mutagen
  - Navidrome protection checks via batch caching
  - Fail-safe deletion logic (keeps files on errors)
- `kikusan/navidrome.py`: Subsonic API client for Navidrome integration
  - Token-based authentication (MD5 hash per Subsonic API spec)
  - Fetches starred songs and playlist contents
  - Two-tier song matching (path-based + metadata-based)
  - Environment-based configuration: NAVIDROME_URL, NAVIDROME_USER, NAVIDROME_PASSWORD
- `kikusan/cron/sync.py`: Playlist synchronization with reference-aware deletion and Navidrome protection
- `kikusan/cron/explore_sync.py`: Explore (charts/moods/genres) synchronization for cron mode
  - `sync_explore()`: Main entry point, reuses `download_new_tracks`, `remove_old_tracks`, `update_m3u_playlist` from `sync.py`. Applies `limit` truncation after fetching tracks (before compare/download).
  - `fetch_explore_tracks()`: Routes to `_fetch_chart_tracks()` or `_fetch_mood_tracks()` based on type
  - `_fetch_chart_tracks()`: Fetches tracks from YouTube Music charts via `get_charts()`
  - `_fetch_mood_tracks()`: Fetches playlists for a mood/genre category, then fetches tracks from each playlist, deduplicating by video_id
  - State is stored using the same `PlaylistState` model in `.kikusan/state/`
  - All safety features apply: cross-reference protection, Navidrome protection, unavailable cooldown
- `kikusan/cron/config.py`: Cron configuration loading with support for `playlists`, `plugins`, `explore`, and `hooks` sections
  - `ExploreConfig`: Dataclass for explore entries (type, country, params, sync, schedule, limit)
  - `validate_country_code()`: Validates ISO 3166-1 Alpha-2 country codes
- `kikusan/plugins/sync.py`: Plugin synchronization with reference-aware deletion and Navidrome protection
- `kikusan/hooks.py`: Generic hook system for running commands on events
  - Supports `playlist_updated` and `sync_completed` events
  - Configured via `hooks` section in `cron.yaml`
  - Passes context data via environment variables (KIKUSAN_*)
  - Supports timeout and run_on_error options
- `kikusan/cron/scheduler.py`: Orchestrates sync jobs (playlists, plugins, explore) and triggers hooks after completion
  - `_schedule_explore()` / `_explore_sync_job()`: Schedule and execute explore sync jobs
  - `sync_all_once()`: Runs all playlists, plugins, and explore sources once immediately
- `kikusan/lyrics.py`: Lyrics fetching from lrclib.net with multi-strategy lookup
  - `get_lyrics_for_video()`: Primary function — fetches clean metadata from ytmusicapi, then tries multiple lrclib.net strategies:
    1. Exact match (`/api/get`) with ytmusicapi metadata (clean title/artist/duration)
    2. Search (`/api/search`) with ytmusicapi metadata (fuzzy match, includes album)
    3. Exact match (`/api/get`) with yt-dlp fallback metadata (original behavior)
  - `get_lyrics()`: Original function preserved for backward compatibility, delegates to `_get_lyrics_exact()`
  - `_search_lyrics()`: Uses `/api/search` endpoint with duration-based filtering (3s tolerance)
  - `save_lyrics()`: Saves LRC file alongside audio file
  - The ytmusicapi metadata enhancement dramatically improves lyrics hit rate because yt-dlp often extracts metadata from video titles (e.g., "Artist - Song (Official Video)") rather than clean music metadata
- `kikusan/download.py`: Core download logic with unavailable video protection
  - `download()`: Single video download with cooldown check at entry and error recording on failure
  - `UnavailableCooldownError`: Raised when video is on cooldown (avoids hitting YouTube)
  - `_extract_video_id_from_url()`: Extracts video ID from YouTube URLs for error recording
  - All download paths (`download()`, `_download_single()`, `download_url()`, `_download_playlist()`) record unavailable errors
- `kikusan/unavailable.py`: Unavailable video cooldown management
  - Tracks video IDs that returned "Video unavailable" errors
  - JSON persistence in `.kikusan/unavailable.json` with atomic writes
  - Configurable cooldown period (default: 168 hours / 7 days)
  - Pattern matching for unavailable-specific errors (distinct from auth/network errors)
  - Functions: `is_unavailable_error()`, `record_unavailable()`, `is_on_cooldown()`, `clear_expired()`

### CLI Flags
All major configuration variables have corresponding CLI flags:

**Global flags (apply to all subcommands):**
- `--cookie-mode`: Cookie usage mode (auto, always, never)
- `--cookie-retry-delay`: Delay before retrying with cookies
- `--no-log-cookie-usage`: Disable cookie usage logging
- `--unavailable-cooldown`: Hours to wait before retrying unavailable videos (0 = disabled, default: 168)

**download command:**
- `--organization-mode`: File organization (flat, album)
- `--use-primary-artist / --no-use-primary-artist`: Use primary artist for folder names

**web command:**
- `--cors-origins`: CORS allowed origins
- `--web-playlist`: M3U playlist name for web downloads
- `--multi-user / --no-multi-user`: Enable per-user M3U playlists via Remote-User header (env: `KIKUSAN_MULTI_USER`)

**cron command:**
- `--format`: Audio format
- `--organization-mode`: File organization
- `--use-primary-artist / --no-use-primary-artist`: Use primary artist for folder names
- Supports `explore` section in `cron.yaml` for syncing charts and moods/genres:
  - `type: charts` with optional `country` (ISO 3166-1 Alpha-2, default ZZ)
  - `type: mood` with required `params` (from `explore moods` command)
  - Each entry has `sync` (bool) and `schedule` (cron expression)
  - Optional `limit` (int, default 0 = no limit): Maximum number of tracks to sync. Tracks are truncated from the end, preserving the top-ranked entries (e.g., `limit: 10` keeps the top 10 chart tracks).
  - State stored in `.kikusan/state/` using same format as playlist state

**plugins run command:**
- `--format`: Audio format
- `--organization-mode`: File organization
- `--use-primary-artist / --no-use-primary-artist`: Use primary artist for folder names

**explore command group:**
- `explore moods` — list available mood & genre categories
- `explore mood-playlists <PARAMS>` — list playlists for a category (PARAMS from `explore moods`)
  - `--download/-d`: Download all tracks from all playlists in the category
  - `--output/-o`: Output directory
  - `--format/-f`: Audio format (opus, mp3, flac)
  - `--add-to-playlist/-p`: Add to M3U playlist
- `explore charts` — show current music charts
  - `--country/-c <CODE>`: ISO 3166-1 Alpha-2 country code (default: ZZ for global)
  - `--download/-d`: Download all chart tracks
  - `--output/-o`: Output directory
  - `--format/-f`: Audio format (opus, mp3, flac)
  - `--add-to-playlist/-p`: Add to M3U playlist

CLI flags take precedence over environment variables. Options with `envvar` attribute automatically read from the corresponding environment variable if not specified on the command line.
