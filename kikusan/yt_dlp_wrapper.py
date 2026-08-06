"""Intelligent yt-dlp wrapper with conditional cookie usage.

This module wraps yt-dlp operations with smart retry logic that only uses
cookies when authentication is required (age-restricted, private content, etc.).
This prevents unnecessary cookie usage that could lead to account bans.

Responsibilities:
- Detect auth/age-restriction errors from yt-dlp
- Automatically retry with cookies when needed
- Log cookie usage for debugging
- Provide metrics on cookie necessity
"""

import logging
import re
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from typing import Any, Optional

import yt_dlp
from yt_dlp.postprocessor.common import PostProcessor
from yt_dlp.utils import DownloadError, ExtractorError
try:
    from yt_dlp.version import __version__ as YT_DLP_VERSION
except Exception:  # pragma: no cover - defensive import
    YT_DLP_VERSION = "unknown"

logger = logging.getLogger(__name__)


class _SetFieldsPP(PostProcessor):
    """Force specific info_dict fields to known-correct values.

    yt-dlp's own per-video metadata extraction is often missing fields (album,
    track number) that are reliably known from search/browse instead. Plain
    dict-based postprocessors like MetadataParser can only edit a field that
    already has a value — they can't inject one into a missing field — so this
    runs as a real pre_process hook on the YoutubeDL instance actually used for
    the download, guaranteeing the override reaches both the filename
    templating and the embedded tags.
    """

    def __init__(self, downloader, fields: dict[str, Any]):
        super().__init__(downloader)
        self._fields = fields

    def run(self, info):
        info.update(self._fields)
        return [], info

# Patterns indicating authentication/cookies are required
# These are matched case-insensitively against exception messages
AUTH_REQUIRED_PATTERNS = [
    # Age restrictions
    r"age[- ]restricted",
    r"inappropriate.*content",
    r"sign in.*confirm.*age",
    r"content.*warning",
    # Authentication required
    r"sign in",
    r"log[- ]?in.*required",
    r"members[- ]only",
    r"private.*video",
    r"join.*channel",
    # Premium content
    r"premium.*members",
    r"music premium",
    r"requires.*payment",
    r"subscribers.*only",
    # Private/unlisted with auth
    r"granted.*access",
    r"unlisted.*video",
    # Not a real auth error, but authenticated requests are markedly less
    # likely to hit YouTube's anti-bot format-stripping (SABR) than anonymous
    # ones, so it's worth an automatic cookie-retry rather than failing outright.
    r"requested format is not available",
]


class CookieUsageStats:
    """Track cookie usage statistics for observability."""

    _lock = threading.Lock()
    total_requests: int = 0
    cookie_fallback_count: int = 0
    always_cookie_count: int = 0

    @classmethod
    def increment_total(cls):
        """Thread-safe increment of total requests counter."""
        with cls._lock:
            cls.total_requests += 1

    @classmethod
    def increment_cookie_fallback(cls):
        """Thread-safe increment of cookie fallback counter."""
        with cls._lock:
            cls.cookie_fallback_count += 1

    @classmethod
    def increment_always_cookie(cls):
        """Thread-safe increment of always cookie counter."""
        with cls._lock:
            cls.always_cookie_count += 1

    @classmethod
    def log_summary(cls):
        """Log summary of cookie usage statistics."""
        with cls._lock:
            if cls.total_requests == 0:
                return

            fallback_pct = (cls.cookie_fallback_count / cls.total_requests) * 100
            logger.info(
                "Cookie usage stats: %d/%d requests (%.1f%%) required cookie fallback",
                cls.cookie_fallback_count,
                cls.total_requests,
                fallback_pct,
            )


# Only log the stale-cookie warning at most this often, so a batch of
# downloads all hitting the same stale file doesn't spam the log.
_STALE_COOKIE_WARNING_INTERVAL_SECONDS = 3600
_last_stale_cookie_warning: float = 0.0
_stale_cookie_warning_lock = threading.Lock()


def is_cookie_file_stale(cookie_file: Optional[str], max_age_hours: int) -> bool:
    """Check whether a cookie file is older than the configured max age.

    A stale exported cookies.txt can be actively harmful rather than just
    unhelpful: YouTube treats a replayed/expired session as more suspicious
    than an anonymous request, which is what caused every download to fail
    with "Requested format is not available" once, until cookies were
    disabled. Once a file crosses this age, treat it as if it weren't
    configured at all rather than forcing it onto every request.

    Args:
        cookie_file: Path to the cookie file, or None
        max_age_hours: Maximum age before the file is considered stale
            (0 disables the check entirely)

    Returns:
        True if the file exists and is older than max_age_hours
    """
    if not cookie_file or max_age_hours <= 0:
        return False

    try:
        age_seconds = time.time() - Path(cookie_file).stat().st_mtime
    except OSError:
        return False

    stale = age_seconds > max_age_hours * 3600
    if stale:
        global _last_stale_cookie_warning
        with _stale_cookie_warning_lock:
            now = time.time()
            if now - _last_stale_cookie_warning > _STALE_COOKIE_WARNING_INTERVAL_SECONDS:
                _last_stale_cookie_warning = now
                logger.warning(
                    "Cookie file is %.1f days old (max age: %d hours) - "
                    "treating as not configured. Re-upload a fresh export "
                    "via Settings if you need cookie authentication.",
                    age_seconds / 86400,
                    max_age_hours,
                )
    return stale


def is_auth_error(exception: Exception) -> bool:
    """Determine if exception indicates auth/cookies are needed.

    Args:
        exception: Exception raised by yt-dlp

    Returns:
        True if exception indicates cookies would help, False otherwise
    """
    # Get error message from exception
    error_msg = str(exception).lower()

    # Check each pattern
    for pattern in AUTH_REQUIRED_PATTERNS:
        if re.search(pattern, error_msg, re.IGNORECASE):
            logger.debug("Auth error detected with pattern '%s': %s", pattern, error_msg[:100])
            return True

    return False


def _is_ambiguous_youtube_unavailable_error(exception: Exception) -> bool:
    """Detect Docker-prone generic YouTube unavailable errors worth retrying."""
    message = str(exception).lower()
    if "youtube" not in message and "video is not available" not in message:
        return False
    return "this video is not available" in message and "video unavailable" not in message


def _is_youtube_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    return host in {"youtube.com", "www.youtube.com", "music.youtube.com", "youtu.be"}


def _to_canonical_youtube_watch_url(url: str) -> str | None:
    """Convert music.youtube.com/youtu.be URLs to youtube.com watch URL when possible."""
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()

    if host in {"youtube.com", "www.youtube.com"}:
        return None

    if host == "music.youtube.com":
        video_id = parse_qs(parsed.query).get("v", [None])[0]
        if video_id:
            return f"https://www.youtube.com/watch?v={video_id}"
        return None

    if host == "youtu.be":
        video_id = parsed.path.lstrip("/")
        if video_id:
            return f"https://www.youtube.com/watch?v={video_id}"

    return None


def _with_youtube_player_clients(
    ydl_opts: dict[str, Any], player_clients: list[str]
) -> dict[str, Any]:
    """Return a copy of ydl_opts with youtube player_client override merged in."""
    opts = ydl_opts.copy()
    extractor_args = dict(opts.get("extractor_args") or {})
    youtube_args = dict(extractor_args.get("youtube") or {})
    youtube_args["player_client"] = list(player_clients)
    extractor_args["youtube"] = youtube_args
    opts["extractor_args"] = extractor_args
    return opts


def _execute_ydl_once(
    ydl_opts: dict[str, Any],
    url: str,
    download: bool,
    cookie_file: Optional[str],
    use_cookies: bool,
    field_overrides: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Single yt-dlp execution attempt."""
    opts = ydl_opts.copy()

    if use_cookies and cookie_file:
        opts["cookiefile"] = cookie_file

    with yt_dlp.YoutubeDL(opts) as ydl:
        if field_overrides:
            ydl.add_post_processor(_SetFieldsPP(ydl, field_overrides), when="pre_process")
        return ydl.extract_info(url, download=download)


def _retry_ambiguous_youtube_unavailable(
    original_error: Exception,
    ydl_opts: dict[str, Any],
    url: str,
    download: bool,
    cookie_file: Optional[str],
    use_cookies: bool,
    field_overrides: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Retry ambiguous YouTube unavailable errors with alternate client strategies."""
    if use_cookies:
        raise original_error
    if not _is_youtube_url(url):
        raise original_error
    if not _is_ambiguous_youtube_unavailable_error(original_error):
        raise original_error

    alternate_url = _to_canonical_youtube_watch_url(url)
    strategies: list[tuple[str, str, dict[str, Any]]] = [
        (
            "youtube_client_fallback_tv",
            url,
            _with_youtube_player_clients(ydl_opts, ["tv_simply", "tv_downgraded", "android", "web"]),
        ),
        (
            "youtube_client_fallback_ios",
            url,
            _with_youtube_player_clients(ydl_opts, ["ios", "android", "web"]),
        ),
    ]
    if alternate_url:
        strategies.extend(
            [
                ("youtube_canonical_url_retry", alternate_url, ydl_opts),
                (
                    "youtube_canonical_url_tv_client_retry",
                    alternate_url,
                    _with_youtube_player_clients(
                        ydl_opts, ["tv_simply", "tv_downgraded", "android", "web"]
                    ),
                ),
            ]
        )

    logger.debug(
        "Ambiguous YouTube unavailable error; retrying with fallback strategies "
        "(yt-dlp=%s, url=%s): %s",
        YT_DLP_VERSION,
        url,
        str(original_error)[:160],
    )

    last_error: Exception = original_error
    for strategy_name, retry_url, retry_opts in strategies:
        try:
            logger.debug("yt-dlp fallback retry strategy=%s url=%s", strategy_name, retry_url)
            result = _execute_ydl_once(
                retry_opts, retry_url, download, cookie_file, use_cookies, field_overrides
            )
            logger.info(
                "Recovered from ambiguous YouTube unavailable error using fallback strategy=%s",
                strategy_name,
            )
            return result
        except (ExtractorError, DownloadError) as retry_error:
            last_error = retry_error
            logger.debug(
                "yt-dlp fallback retry failed strategy=%s error=%s",
                strategy_name,
                str(retry_error)[:160],
            )

    logger.warning(
        "All yt-dlp fallback strategies failed for ambiguous YouTube unavailable error "
        "(yt-dlp=%s, url=%s, attempts=%d)",
        YT_DLP_VERSION,
        url,
        len(strategies),
    )
    raise last_error


def extract_info_with_retry(
    ydl_opts: dict[str, Any],
    url: str,
    download: bool = True,
    cookie_file: Optional[str] = None,
    config: Optional[Any] = None,
    field_overrides: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Extract info with intelligent cookie fallback.

    This is the core wrapper function that replaces direct yt-dlp calls.
    It implements smart retry logic based on the configured cookie mode.

    Args:
        ydl_opts: Base yt-dlp options dict (without cookies)
        url: URL to extract/download
        download: Whether to download (True) or just extract info (False)
        cookie_file: Path to cookie file (if available)
        config: Config object with cookie_mode, cookie_retry_delay, etc.
        field_overrides: Known-correct info_dict fields (e.g. album, track_number)
            to force via a real pre_process hook, since yt-dlp's own extraction
            often lacks them even when this specific video does belong to one.

    Returns:
        yt-dlp info dict

    Raises:
        DownloadError: If download fails
        ExtractorError: If extraction fails
        Exception: Other yt-dlp errors
    """
    # Import here to avoid circular dependency
    if config is None:
        from kikusan.config import get_config

        config = get_config()

    # Track statistics
    CookieUsageStats.increment_total()

    # Determine cookie usage based on mode
    cookie_mode = getattr(config, "cookie_mode", "auto")
    retry_delay = getattr(config, "cookie_retry_delay", 1.0)
    log_cookie_usage = getattr(config, "log_cookie_usage", True)
    cookie_max_age_hours = getattr(config, "cookie_max_age_hours", 720)

    if is_cookie_file_stale(cookie_file, cookie_max_age_hours):
        cookie_file = None

    # Mode: always - use cookies immediately
    if cookie_mode == "always":
        if log_cookie_usage:
            logger.debug("Cookie mode=always: Using cookies for all requests")
        CookieUsageStats.increment_always_cookie()
        return _execute_ydl(ydl_opts, url, download, cookie_file, use_cookies=True, field_overrides=field_overrides)

    # Mode: never - never use cookies
    if cookie_mode == "never":
        if log_cookie_usage:
            logger.debug("Cookie mode=never: Never using cookies")
        return _execute_ydl(ydl_opts, url, download, cookie_file, use_cookies=False, field_overrides=field_overrides)

    # Mode: auto - try without cookies first, fallback on auth errors
    if log_cookie_usage:
        logger.debug("Cookie mode=auto: Trying without cookies first")

    try:
        # First attempt: no cookies
        return _execute_ydl(ydl_opts, url, download, cookie_file, use_cookies=False, field_overrides=field_overrides)

    except (ExtractorError, DownloadError) as e:
        # Check if this is an auth error that cookies might fix
        if not is_auth_error(e):
            # Not an auth error, re-raise
            raise

        # Auth error detected - retry with cookies
        if not cookie_file:
            logger.warning(
                "Auth error detected but no cookie file available: %s", str(e)[:100]
            )
            raise

        if log_cookie_usage:
            logger.info("Cookie fallback for: %s", url)
            logger.debug("Retrying with cookies after %.1fs delay", retry_delay)

        CookieUsageStats.increment_cookie_fallback()

        # Wait before retrying
        time.sleep(retry_delay)

        # Retry with cookies
        return _execute_ydl(ydl_opts, url, download, cookie_file, use_cookies=True, field_overrides=field_overrides)


def _execute_ydl(
    ydl_opts: dict[str, Any],
    url: str,
    download: bool,
    cookie_file: Optional[str],
    use_cookies: bool,
    field_overrides: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Execute yt-dlp with or without cookies.

    Args:
        ydl_opts: Base yt-dlp options
        url: URL to process
        download: Whether to download or just extract info
        cookie_file: Path to cookie file
        use_cookies: Whether to use cookies
        field_overrides: See extract_info_with_retry

    Returns:
        yt-dlp info dict
    """
    try:
        return _execute_ydl_once(ydl_opts, url, download, cookie_file, use_cookies, field_overrides)
    except (ExtractorError, DownloadError) as e:
        return _retry_ambiguous_youtube_unavailable(
            e, ydl_opts, url, download, cookie_file, use_cookies, field_overrides
        )
