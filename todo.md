# Kikusan Bug Fixes TODO

This file tracks identified bugs and technical debt that need to be addressed.

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
