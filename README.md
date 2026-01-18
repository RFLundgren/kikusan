# Kikusan

Search and download music from YouTube Music with lyrics.

## Features

- Search YouTube Music
- Download audio in OPUS/MP3/FLAC format
- Playlist support (download entire playlists)
- Quick download (search and download first match)
- Automatic lyrics fetching from lrclib.net (LRC format)
- CLI and web interface
- Docker support

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

# Download entire playlist
kikusan download --url "https://music.youtube.com/playlist?list=..."

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

### Docker

```bash
docker compose up -d
# Open http://localhost:8000
```

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `KIKUSAN_DOWNLOAD_DIR` | `./downloads` | Download directory |
| `KIKUSAN_AUDIO_FORMAT` | `opus` | Audio format (opus, mp3, flac) |
| `KIKUSAN_FILENAME_TEMPLATE` | `%(artist,uploader)s - %(title)s` | Filename template (yt-dlp format) |
| `KIKUSAN_WEB_PORT` | `8000` | Web server port |
| `KIKUSAN_WEB_PLAYLIST` | `None` | M3U playlist name for web downloads (optional) |

## Requirements

- Python 3.12+
- ffmpeg (for audio processing)
