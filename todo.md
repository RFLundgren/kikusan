# Kikusan Bug Fixes TODO

This file tracks identified bugs and technical debt that need to be addressed.

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
10. ✅ Inconsistent error handling patterns - Documented error handling strategy in all search functions (propagate vs. return None/empty)
