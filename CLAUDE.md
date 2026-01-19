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

### Architecture Notes
- `kikusan/search.py`: Uses ytmusicapi to search YouTube Music, extracts view_count from search results
- `kikusan/web/app.py`: FastAPI backend with search and download endpoints
- `kikusan/web/templates/index.html`: Single-page frontend with embedded JavaScript
- `kikusan/web/static/style.css`: Responsive CSS with dark/light themes
