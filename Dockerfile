FROM python:3.14-slim@sha256:486b8092bfb12997e10d4920897213a06563449c951c5506c2a2cfaf591c599f

# Install ffmpeg for audio processing and rsgain for ReplayGain tagging
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg jq curl rsgain && \
    rm -rf /var/lib/apt/lists/*

# Install uv for fast package management
COPY --from=ghcr.io/astral-sh/uv:latest@sha256:94a23af2d50e97b87b522d3cea24aaf8a1faedec1344c952767434f69585cbf9 /uv /usr/local/bin/uv

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
RUN mkdir -p /downloads /data && \
    chown -R kikusan:kikusan /app /downloads /data

ENV KIKUSAN_DOWNLOAD_DIR=/downloads
ENV KIKUSAN_WEB_PORT=8000
ENV KIKUSAN_WEB_PLAYLIST=web-downloads
ENV KIKUSAN_REPLAYGAIN=false

# Switch to non-root user
USER kikusan

EXPOSE 8000

# Run the web server
CMD ["uv", "run", "kikusan", "web", "--host", "0.0.0.0"]
