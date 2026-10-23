"""Per-principal fixed-window rate limit (default 300 requests/minute), backed by Valkey.

If Valkey is unreachable the limiter fails open and logs: losing the cache must not take the platform down, and
authentication still gates every request."""
import logging
import time

from fastapi import HTTPException

from .config import get_settings

log = logging.getLogger("medguard.ratelimit")
_memory: dict[str, tuple[int, int]] = {}
_valkey = None


def reset_memory() -> None:
    _memory.clear()


async def check(key: str) -> None:
    s = get_settings()
    limit = s.rate_limit_per_minute
    window = int(time.time() // 60)
    if s.rate_limit_backend == "memory":
        w, n = _memory.get(key, (window, 0))
        n = n + 1 if w == window else 1
        _memory[key] = (window, n)
        count = n
    else:
        global _valkey
        try:
            if _valkey is None:
                import valkey.asyncio as vk
                _valkey = vk.from_url(s.valkey_url, socket_connect_timeout=0.5, socket_timeout=0.5)
            k = f"rl:{key}:{window}"
            count = await _valkey.incr(k)
            if count == 1:
                await _valkey.expire(k, 70)
        except Exception as e:  # noqa: BLE001
            log.warning("rate limiter unavailable (%s); failing open", type(e).__name__)
            return
    if count > limit:
        raise HTTPException(429, "Rate limit exceeded", headers={"Retry-After": str(60 - int(time.time()) % 60)})
