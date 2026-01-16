"""Screenshot cache for reducing redundant ADB calls."""

import time
from typing import Any, Callable


class ScreenshotCache:
    """Caches screenshots to reduce ADB calls.
    
    The cache is valid for a time window (max_age seconds). If a screenshot
    is requested within this window, the cached version is returned.
    """

    def __init__(self, get_screenshot_fn: Callable, max_age: float = 1.0):
        """
        Args:
            get_screenshot_fn: Function to capture screenshot (device_id already bound).
            max_age: Cache validity in seconds (default: 1.0).
        """
        self._get_screenshot_fn = get_screenshot_fn
        self._max_age = max_age
        self._cached: Any = None
        self._cached_time: float = 0

    def get(self, force_refresh: bool = False):
        """Get cached screenshot or capture a new one.
        
        Args:
            force_refresh: If True, always capture a new screenshot.
            
        Returns:
            Screenshot object.
        """
        current_time = time.time()
        
        if not force_refresh and self._cached is not None:
            age = current_time - self._cached_time
            if age < self._max_age:
                return self._cached
        
        self._cached = self._get_screenshot_fn()
        self._cached_time = current_time
        return self._cached

    def invalidate(self) -> None:
        """Invalidate the cache, forcing next get() to capture a new screenshot."""
        self._cached = None
        self._cached_time = 0

