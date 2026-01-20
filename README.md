# Kikusan

Search and download music from YouTube Music with lyrics.

## Features

- **Search & Download**: Search YouTube Music and download audio in OPUS/MP3/FLAC format
- **Playlist Support**: Download entire playlists from YouTube Music, YouTube, and Spotify
- **Quick Download**: Search and download first match with a single command
- **Automatic Lyrics**: Fetch and embed synchronized lyrics from lrclib.net (LRC format)
- **Web Interface**: Modern web UI with search, download, theme toggle, and format selection
- **Docker Support**: Easy deployment with Docker and docker-compose
- **Plugin System**: Extensible architecture for custom music sources
- **Scheduled Sync**: Automated playlist monitoring with cron scheduling
- **M3U Playlists**: Automatic playlist file generation for downloads

## Plugin System

Kikusan supports plugins for syncing music from various sources beyond standard playlists:

**Built-in Plugins:**
- **`listenbrainz`** - Weekly recommendations from listenbrainz.org
  - Required: `user` (listenbrainz username)
  - Optional: `recommendation_type` (weekly-exploration, weekly-jams)

- **`rss`** - Generic RSS/Atom feed parser for music podcasts, blogs, etc.
  - Required: `url` (RSS/Atom feed URL)
  - Optional: `artist_field`, `title_field`, `timeout`, `user_agent`

- **`reddit`** - Fetch songs from music subreddits (r/listentothis, r/Music, r/IndieHeads, etc.)
  - Required: `subreddit` (subreddit name)
  - Optional: `sort` (hot/new/top/rising), `time_filter`, `limit`, `min_score`

- **`billboard`** - Fetch songs from Billboard charts (hot-100, pop-songs, etc.)
  - Required: `chart_name` (e.g., 'hot-100', 'pop-songs')
  - Optional: `date` (YYYY-MM-DD), `year` (for year-end charts), `limit`

**Usage:**

```bash
# List available plugins
kikusan plugins list

# Run a plugin once
kikusan plugins run listenbrainz --config '{"user": "myuser"}'
kikusan plugins run reddit --config '{"subreddit": "listentothis", "limit": 25}'
kikusan plugins run billboard --config '{"chart_name": "hot-100", "limit": 50}'

# Schedule in cron.yaml
# See cron.example.yaml for configuration examples
```

**Creating Third-Party Plugins:**

See [`examples/third-party-plugin/`](examples/third-party-plugin/) for a complete example of creating your own plugin. Plugins are distributed as Python packages and automatically discovered via entry points.

## Installation

```bash
uv sync
```

## Usage

### CLI

```bash
# Search for music
kikusan search "Bohemian Rhapsody"

# Download by video ID
kikusan download bSnlKl_PoQU

# Download by URL
kikusan download --url "https://music.youtube.com/watch?v=bSnlKl_PoQU"

# Search and download first match
kikusan download --query "Bohemian Rhapsody Queen"

# Download entire playlist (YouTube Music, YouTube, or Spotify)
kikusan download --url "https://music.youtube.com/playlist?list=..."
kikusan download --url "https://open.spotify.com/playlist/..."

# Custom filename format
kikusan download bSnlKl_PoQU --filename "%(title)s"

# Options
kikusan download bSnlKl_PoQU --output ~/Music --format mp3
```

### Web Interface

```bash
kikusan web
# Open http://localhost:8000
```

**Features:**
- Search YouTube Music with real-time results
- Download individual tracks with format selection (OPUS/MP3/FLAC)
- Dark/light theme toggle with automatic system preference detection
- View counts displayed for each track
- Responsive design for mobile and desktop

### Scheduled Sync (Cron)

Automatically monitor and sync playlists or plugins on a schedule:

```bash
# Run continuously with cron.yaml configuration
kikusan cron

# Run all syncs once and exit
kikusan cron --once

# Use custom config file
kikusan cron --config /path/to/cron.yaml
```

Create a `cron.yaml` file to configure:
- **Playlists**: YouTube Music, YouTube, or Spotify playlists
- **Plugins**: Listenbrainz, Reddit, Billboard, RSS feeds
- **Schedule**: Standard cron expressions (e.g., "0 9 * * *" for daily at 9am)
- **Sync Mode**: Keep or delete files when removed from source

See `cron.example.yaml` for detailed configuration examples.

### Docker

```bash
docker compose up -d
# Open http://localhost:8000
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KIKUSAN_DOWNLOAD_DIR` | `./downloads` | Download directory |
| `KIKUSAN_AUDIO_FORMAT` | `opus` | Audio format (opus, mp3, flac) |
| `KIKUSAN_FILENAME_TEMPLATE` | `%(artist,uploader)s - %(title)s` | Filename template (yt-dlp format) |
| `KIKUSAN_WEB_PORT` | `8000` | Web server port |
| `KIKUSAN_WEB_PLAYLIST` | `None` | M3U playlist name for web downloads (optional) |

### State Files & Playlists

Kikusan tracks downloaded files and generates M3U playlists automatically:

- **State Files**: Stored in `{download_dir}/.kikusan/state/` (for playlists) and `{download_dir}/.kikusan/plugin_state/` (for plugins)
- **M3U Playlists**: Generated at `{download_dir}/{name}.m3u` for each sync configuration

## Requirements

- Python 3.12+
- ffmpeg (for audio processing)
