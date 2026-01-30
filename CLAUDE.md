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
- `kikusan/search.py`: Uses ytmusicapi to search YouTube Music, extracts view_count from search results
- `kikusan/web/app.py`: FastAPI backend with search and download endpoints
- `kikusan/web/templates/index.html`: Single-page frontend with embedded JavaScript
- `kikusan/web/static/style.css`: Responsive CSS with dark/light themes
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
- `kikusan/plugins/sync.py`: Plugin synchronization with reference-aware deletion and Navidrome protection
- `kikusan/hooks.py`: Generic hook system for running commands on events
  - Supports `playlist_updated` and `sync_completed` events
  - Configured via `hooks` section in `cron.yaml`
  - Passes context data via environment variables (KIKUSAN_*)
  - Supports timeout and run_on_error options
- `kikusan/cron/scheduler.py`: Orchestrates sync jobs and triggers hooks after completion
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

**cron command:**
- `--format`: Audio format
- `--organization-mode`: File organization
- `--use-primary-artist / --no-use-primary-artist`: Use primary artist for folder names

**plugins run command:**
- `--format`: Audio format
- `--organization-mode`: File organization
- `--use-primary-artist / --no-use-primary-artist`: Use primary artist for folder names

CLI flags take precedence over environment variables. Options with `envvar` attribute automatically read from the corresponding environment variable if not specified on the command line.
