# Kikusan Bug Fixes TODO

This file tracks identified bugs and technical debt that need to be addressed.

## Critical Priority

### 1. KeyError in State Loading
**File**: `kikusan/cron/state.py:72-78`, `kikusan/plugins/state.py:72-78`

**Problem**: In `load_state()`, required keys are accessed without validation. If a state file is corrupted or missing required keys, a `KeyError` is raised instead of gracefully returning `None`.

```python
return PlaylistState(
    playlist_name=data["playlist_name"],  # KeyError if missing
    url=data["url"],                       # KeyError if missing
    last_check=data["last_check"],         # KeyError if missing
    tracks=tracks,
)
```

**How to Fix**:
- Wrap the dictionary access in a try-except block
- On `KeyError`, log a warning and return `None` (consistent with other error cases)
- Alternative: Use `data.get()` with validation for required fields

```python
try:
    return PlaylistState(
        playlist_name=data["playlist_name"],
        url=data["url"],
        last_check=data["last_check"],
        tracks=tracks,
    )
except KeyError as e:
    logger.error("Corrupted state file missing key %s: %s", e, state_file)
    return None
```

### 2. Unsafe List Indexing
**Files**: Multiple locations, particularly `kikusan/search.py:422`, `kikusan/web/app.py:396`

**Problem**: Several code paths access list elements without checking if the list is empty, which could cause `IndexError`.

**Examples**:
- `search.py:422`: `if MTRIR_KEY not in results[0]:` (assumes results is non-empty)
- `web/app.py:396`: `audio_formats[0]['url']` (checked with `if audio_formats` but pattern inconsistent)

**How to Fix**:
- Add explicit length checks before indexing
- Use patterns like: `if results and len(results) > 0:`
- Consider using `next(iter(list), default)` for safer first-element access

```python
# Before
if MTRIR_KEY not in results[0]:

# After
if not results or MTRIR_KEY not in results[0]:
```

## High Priority

### 3. Confusing None Logic in download_new_tracks()
**File**: `kikusan/cron/sync.py:313-327`

**Problem**: The code checks if `audio_path` is in the state tracks list, but `audio_path` could be `None`. Comparing `None` to `Path` objects will never match, creating potential duplicate track entries.

```python
if audio_path:
    # Check if it was skipped (already existed)
    if audio_path in [Path(t.file_path) for t in state.tracks]:
        skipped += 1
    else:
        # Add to state
```

**How to Fix**:
- Clarify the logic: if `audio_path` is `None`, the download failed completely
- The check `audio_path in [...]` is redundant; the download function already handles duplicates
- Simplify to:

```python
if audio_path:
    track_state = TrackState(...)
    state.tracks.append(track_state)
    downloaded += 1
else:
    failed += 1
```

### 4. TOCTOU Race in File Deletion
**File**: `kikusan/cron/sync.py:393-395`

**Problem**: Between checking if `.lrc` file exists and deleting it, another process could delete it, causing an exception.

```python
lrc_path = file_path.with_suffix(".lrc")
if lrc_path.exists():  # TOCTOU: file could be deleted between check and use
    try:
        lrc_path.unlink()
```

**How to Fix**:
- Use try-except instead of checking existence
- Handle `FileNotFoundError` gracefully

```python
lrc_path = file_path.with_suffix(".lrc")
try:
    lrc_path.unlink()
except FileNotFoundError:
    pass  # Already deleted, that's fine
```

## Medium Priority

### 5. Path Traversal Vulnerability
**File**: `kikusan/web/app.py:351`

**Problem**: String comparison for path validation is not sufficient. Symlinks or edge cases could bypass the check.

```python
abs_requested = requested_path.resolve()
abs_download_dir = config.download_dir.resolve()

# Security: ensure path is within download_dir
if not str(abs_requested).startswith(str(abs_download_dir)):
    raise HTTPException(status_code=403, detail="Access denied")
```

**How to Fix**:
- Use `Path.is_relative_to()` (Python 3.9+) for proper path validation
- Or use `Path.resolve()` with proper relative path checking

```python
abs_requested = requested_path.resolve()
abs_download_dir = config.download_dir.resolve()

# Security: ensure path is within download_dir
try:
    abs_requested.relative_to(abs_download_dir)
except ValueError:
    raise HTTPException(status_code=403, detail="Access denied")
```

### 6. Cookie Mode Configuration Crashes
**File**: `kikusan/config.py:68-74`

**Problem**: Invalid `KIKUSAN_COOKIE_MODE` causes application crash at initialization. No graceful fallback.

```python
cookie_mode = os.getenv("KIKUSAN_COOKIE_MODE", "auto").lower()
if cookie_mode not in ("auto", "always", "never"):
    raise ValueError(f"Invalid KIKUSAN_COOKIE_MODE: {cookie_mode}...")
```

**How to Fix**:
- Log warning and fall back to "auto" mode instead of crashing
- Allow application to start with safe defaults

```python
cookie_mode = os.getenv("KIKUSAN_COOKIE_MODE", "auto").lower()
if cookie_mode not in ("auto", "always", "never"):
    logger.warning(
        "Invalid KIKUSAN_COOKIE_MODE '%s', falling back to 'auto'",
        cookie_mode
    )
    cookie_mode = "auto"
```

### 7. Incomplete Metadata Extraction
**File**: `kikusan/search.py:609-654`

**Problem**: `get_song_metadata()` can return duration=0 if `length_seconds_str` is not a valid number, which will cause lyrics matching to fail.

```python
duration_seconds = int(length_seconds_str) if length_seconds_str.isdigit() else 0
```

**How to Fix**:
- Return `None` instead of creating metadata with duration=0
- Let caller handle the failure appropriately

```python
if not length_seconds_str or not length_seconds_str.isdigit():
    logger.warning("Invalid duration for video %s", video_id)
    return None
duration_seconds = int(length_seconds_str)
```

### 8. Navidrome Protection Inconsistent State
**File**: `kikusan/reference_checker.py:331-334`

**Problem**: On error, returns `enabled=True` with empty protection lists, creating inconsistent state.

```python
except Exception as e:
    logger.warning("Failed to load Navidrome protection: %s", e)
    # Fail-safe: return empty cache but mark as enabled (will block deletions)
    return NavidromeProtectionCache([], [], True)
```

**How to Fix**:
- Return `enabled=False` on error so code falls back to checking Navidrome on-demand
- Or retry logic before giving up

```python
except Exception as e:
    logger.warning("Failed to load Navidrome protection: %s", e)
    # Disable protection on error, will fall back to on-demand checks
    return NavidromeProtectionCache([], [], False)
```

## Low Priority

### 9. Inconsistent Error Handling Patterns
**File**: `kikusan/search.py:127-195`

**Problem**: Search functions have different error handling patterns. Some re-raise, others catch and return empty lists. Makes error handling unpredictable for callers.

**How to Fix**:
- Standardize on one pattern (recommend: let exceptions propagate, handle at API boundary)
- Document the error handling strategy in each function

### 10. Uses Private ytmusicapi Method
**File**: `kikusan/search.py:360-367`

**Problem**: `_get_mood_playlists_fallback()` uses private `yt._send_request()` method, not documented as part of public API.

**How to Fix**:
- Monitor ytmusicapi updates for breaking changes
- Consider submitting PR to ytmusicapi to make this a public method
- Add comment documenting the risk

## Architectural Issues

### 11. CookieUsageStats Not Thread-Safe
**File**: `kikusan/yt_dlp_wrapper.py:49-68`

**Problem**: Static class variables are modified without synchronization in a multi-threaded context.

```python
class CookieUsageStats:
    total_requests: int = 0  # Class variable
    cookie_fallback_count: int = 0
    always_cookie_count: int = 0
```

**How to Fix**:
- Add `threading.Lock` to synchronize counter increments
- Or use `threading.local()` for per-thread counters
- Or use atomic operations from `multiprocessing.Value`

```python
import threading

class CookieUsageStats:
    _lock = threading.Lock()
    total_requests: int = 0

    @classmethod
    def increment_total(cls):
        with cls._lock:
            cls.total_requests += 1
```

### 12. No Validation of Numeric Config Values
**File**: `kikusan/config.py:77, 87`

**Problem**: Float and int configuration values are parsed without bounds checking. Could accept negative or invalid values.

```python
cookie_retry_delay = float(os.getenv("KIKUSAN_COOKIE_RETRY_DELAY", "1.0"))  # Could be -5.0
unavailable_cooldown_hours = int(os.getenv("KIKUSAN_UNAVAILABLE_COOLDOWN_HOURS", "168"))  # Could be -100
```

**How to Fix**:
- Add validation after parsing
- Raise `ValueError` or log warning and use default

```python
cookie_retry_delay = float(os.getenv("KIKUSAN_COOKIE_RETRY_DELAY", "1.0"))
if cookie_retry_delay < 0:
    raise ValueError(f"KIKUSAN_COOKIE_RETRY_DELAY must be non-negative, got {cookie_retry_delay}")

unavailable_cooldown_hours = int(os.getenv("KIKUSAN_UNAVAILABLE_COOLDOWN_HOURS", "168"))
if unavailable_cooldown_hours < 0:
    logger.warning("KIKUSAN_UNAVAILABLE_COOLDOWN_HOURS is negative, using 0 (disabled)")
    unavailable_cooldown_hours = 0
```

---

## Completed Fixes ✅

1. ✅ QueueManager thread safety - Added asyncio.Lock for concurrent access
2. ✅ Cross-platform file writes - Replaced rename() with replace()
3. ✅ Duration parsing crash - Added exception handling in _parse_duration()
4. ✅ Cookie file validation - Strict UTF-8 + Netscape format validation
5. ✅ Country code validation - Added regex validation to web endpoint
6. ✅ Memory leak in QueueManager - Automatic cleanup of old jobs (max 100)
