# Kikusan Bug Fixes TODO

This file tracks identified bugs and technical debt that need to be addressed.

## Low Priority

### 9. Inconsistent Error Handling Patterns
**File**: `kikusan/search.py:127-195`

**Problem**: Search functions have different error handling patterns. Some re-raise, others catch and return empty lists. Makes error handling unpredictable for callers.

**How to Fix**:
- Standardize on one pattern (recommend: let exceptions propagate, handle at API boundary)
- Document the error handling strategy in each function

---

## Completed Fixes ✅

1. ✅ QueueManager thread safety - Added asyncio.Lock for concurrent access
2. ✅ Cross-platform file writes - Replaced rename() with replace()
3. ✅ Duration parsing crash - Added exception handling in _parse_duration()
4. ✅ Cookie file validation - Strict UTF-8 + Netscape format validation
5. ✅ Country code validation - Added regex validation to web endpoint
6. ✅ Memory leak in QueueManager - Automatic cleanup of old jobs (max 100)
7. ✅ CookieUsageStats thread safety - Added threading.Lock with class methods for atomic counter operations
8. ✅ Numeric config validation - Added bounds checking for cookie_retry_delay, unavailable_cooldown_hours, and web_port
9. ✅ Private ytmusicapi method documentation - Added comprehensive warning comment about _send_request() usage risks
