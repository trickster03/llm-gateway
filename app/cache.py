import threading
import time
from collections import OrderedDict
from typing import Any, Optional


class TTLCache:
    """Small thread-safe LRU cache with per-entry TTL, for identical completions."""

    def __init__(self, maxsize: int, ttl: float):
        self.maxsize = maxsize
        self.ttl = ttl
        self._data: "OrderedDict[str, tuple[float, Any]]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            ts, val = item
            if time.monotonic() - ts > self.ttl:
                del self._data[key]
                return None
            self._data.move_to_end(key)
            return val

    def set(self, key: str, val: Any) -> None:
        with self._lock:
            self._data[key] = (time.monotonic(), val)
            self._data.move_to_end(key)
            while len(self._data) > self.maxsize:
                self._data.popitem(last=False)
