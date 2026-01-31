"""
Generic data caching infrastructure for slow operations.

Provides thread-safe caching with background loading, manual refresh,
and loading state tracking for registry queries, WMI calls, etc.
"""

from typing import Any, Callable, Optional, Generic, TypeVar
from enum import Enum
from PySide6.QtCore import QObject, QThreadPool, QMutex, QMutexLocker, Signal

from src.utils.thread_utils import SingleRunWorker


T = TypeVar('T')


class CacheState(Enum):
    """State of cached data."""
    IDLE = "idle"           # Not yet loaded
    LOADING = "loading"     # Currently loading
    LOADED = "loaded"       # Data available
    ERROR = "error"         # Load failed


class DataCache(QObject, Generic[T]):
    """
    Generic cache for slow-loading data with background refresh.

    Features:
    - Thread-safe cache access
    - Background loading using SingleRunWorker
    - Manual refresh trigger
    - Loading state tracking
    - Error handling with fallback

    Usage:
        cache = DataCache(get_installed_software)
        cache.state_changed.connect(update_ui)
        cache.data_loaded.connect(populate_table)
        cache.load()  # Start background load

        # Later...
        data = cache.get_data()  # Get cached data
        cache.refresh()  # Reload in background
    """

    # Signals
    state_changed = Signal(CacheState)  # Emitted when state changes
    data_loaded = Signal(object)        # Emitted when data is loaded
    error_occurred = Signal(str)        # Emitted on error

    def __init__(
        self,
        loader_func: Callable[[], T],
        fallback_value: Optional[T] = None
    ) -> None:
        """
        Initialize the cache.

        Args:
            loader_func: Function to call to load data (must be thread-safe)
            fallback_value: Value to return if loading fails (default: None)
        """
        super().__init__()
        self._loader_func = loader_func
        self._fallback_value = fallback_value

        self._data: Optional[T] = None
        self._state = CacheState.IDLE
        self._error_message: Optional[str] = None
        self._mutex = QMutex()

        self._thread_pool = QThreadPool.globalInstance()

    @property
    def state(self) -> CacheState:
        """Get current cache state (thread-safe)."""
        with QMutexLocker(self._mutex):
            return self._state

    @property
    def is_loaded(self) -> bool:
        """Check if data is loaded."""
        return self.state == CacheState.LOADED

    @property
    def is_loading(self) -> bool:
        """Check if currently loading."""
        return self.state == CacheState.LOADING

    @property
    def has_error(self) -> bool:
        """Check if last load had an error."""
        return self.state == CacheState.ERROR

    def get_data(self, use_fallback: bool = True) -> Optional[T]:
        """
        Get cached data (thread-safe).

        Args:
            use_fallback: Return fallback value if not loaded (default: True)

        Returns:
            Cached data, fallback value, or None
        """
        with QMutexLocker(self._mutex):
            if self._data is not None:
                return self._data
            elif use_fallback:
                return self._fallback_value
            else:
                return None

    def get_error(self) -> Optional[str]:
        """Get last error message (thread-safe)."""
        with QMutexLocker(self._mutex):
            return self._error_message

    def load(self) -> None:
        """Start loading data in background (if not already loading)."""
        if self.is_loading:
            return  # Already loading

        self._set_state(CacheState.LOADING)

        # Create worker to load data
        worker = SingleRunWorker(self._loader_func)
        worker.signals.result.connect(self._on_data_loaded)
        worker.signals.error.connect(self._on_load_error)

        self._thread_pool.start(worker)

    def refresh(self) -> None:
        """
        Reload data in background.

        Clears current data and reloads. Use this for manual refresh.
        """
        with QMutexLocker(self._mutex):
            self._data = None
            self._error_message = None

        self.load()

    def clear(self) -> None:
        """Clear cached data and reset state."""
        with QMutexLocker(self._mutex):
            self._data = None
            self._error_message = None
            self._state = CacheState.IDLE

        self.state_changed.emit(CacheState.IDLE)

    def _set_state(self, new_state: CacheState) -> None:
        """Set state and emit signal (internal use)."""
        with QMutexLocker(self._mutex):
            self._state = new_state

        self.state_changed.emit(new_state)

    def _on_data_loaded(self, data: T) -> None:
        """Handle successful data load (runs in UI thread)."""
        with QMutexLocker(self._mutex):
            self._data = data
            self._error_message = None

        self._set_state(CacheState.LOADED)
        self.data_loaded.emit(data)

    def _on_load_error(self, error_msg: str) -> None:
        """Handle load error (runs in UI thread)."""
        with QMutexLocker(self._mutex):
            self._error_message = error_msg
            # Keep existing data if available

        self._set_state(CacheState.ERROR)
        self.error_occurred.emit(error_msg)
