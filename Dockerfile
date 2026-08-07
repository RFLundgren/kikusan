FROM python:3.14-slim@sha256:6a27522252aef8432841f224d9baaa6e9fce07b07584154fa0b9a96603af7456

# Install ffmpeg for audio processing, rsgain for ReplayGain tagging, and
# unzip (required by the Deno install script below)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg jq curl rsgain unzip && \
    rm -rf /var/lib/apt/lists/*

# Install Deno: yt-dlp's EJS challenge solver needs a JS runtime to decode
# signature/n-parameter obfuscated formats (YouTube increasingly strips the
# plain, pre-signed ones). Deno is yt-dlp's recommended/default runtime for this.
RUN curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh -s -- -y

# Install uv for fast package management
COPY --from=ghcr.io/astral-sh/uv:latest@sha256:10902f58a1606787602f303954cea099626a4adb02acbac4c69920fe9d278f82 /uv /usr/local/bin/uv

# Create non-root user for security
ARG UID=1000
ARG GID=1000
RUN groupadd -g ${GID} kikusan && \
    useradd -u ${UID} -g ${GID} -m -s /bin/bash kikusan

WORKDIR /app

# Copy project files
COPY README.md pyproject.toml uv.lock ./
COPY kikusan/ ./kikusan/

# Install dependencies
RUN uv sync --frozen

# Create downloads directory and set permissions
RUN mkdir -p /downloads /app/data && \
    chown -R kikusan:kikusan /app /downloads

ENV KIKUSAN_DOWNLOAD_DIR=/downloads
ENV KIKUSAN_WEB_PORT=8000
ENV KIKUSAN_WEB_PLAYLIST=web-downloads
ENV KIKUSAN_REPLAYGAIN=false

# Switch to non-root user
USER kikusan

EXPOSE 8000

# Run the web server
CMD ["uv", "run", "kikusan", "web", "--host", "0.0.0.0"]
