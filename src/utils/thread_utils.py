"""
Threading utilities for async operations in the UI.

Provides reusable worker classes for one-shot and recurring background tasks,
with proper signal handling and cleanup.
"""

from typing import Any, Callable, Optional
from PySide6.QtCore import QRunnable, QObject, Signal, QThread, QMutex, QMutexLocker


class WorkerSignals(QObject):
    """
    Signals for worker communication.

    Signals:
        finished: Emitted when the worker completes (success or failure).
        result: Emitted with the return value on success.
        error: Emitted with exception info on failure.
        progress: Emitted for progress updates (optional use).
    """
    finished = Signal()
    result = Signal(object)
    error = Signal(str)
    progress = Signal(int)


class SingleRunWorker(QRunnable):
    """
    Executes a function once in a thread pool.

    Usage:
        worker = SingleRunWorker(my_function, arg1, arg2, kwarg1=value)
        worker.signals.result.connect(handle_result)
        worker.signals.error.connect(handle_error)
        QThreadPool.globalInstance().start(worker)
    """

    def __init__(self, func: Callable, *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self.setAutoDelete(True)

    def run(self) -> None:
        """Execute the function and emit appropriate signals."""
        try:
            result = self.func(*self.args, **self.kwargs)
            self.signals.result.emit(result)
        except Exception as e:
            self.signals.error.emit(str(e))
        finally:
            self.signals.finished.emit()


class LoopingWorker(QThread):
    """
    Executes a function repeatedly at a fixed interval.

    Improvements over Admin App version:
    - Does not block signals on stop (allows finished to emit)
    - Uses mutex for thread-safe state access
    - Checks running state before and after sleep
    - No forced termination

    Usage:
        worker = LoopingWorker(500, get_cpu_usage)  # 500ms interval
        worker.signals.result.connect(update_graph)
        worker.start()
        # Later...
        worker.stop()
    """

    def __init__(
        self,
        interval_ms: int,
        func: Callable,
        *args: Any,
        **kwargs: Any
    ) -> None:
        super().__init__()
        self.interval_ms = interval_ms
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

        self._running = True
        self._mutex = QMutex()

    @property
    def is_running(self) -> bool:
        """Thread-safe check of running state."""
        with QMutexLocker(self._mutex):
            return self._running

    def run(self) -> None:
        """Execute the function repeatedly until stopped."""
        while self.is_running:
            try:
                result = self.func(*self.args, **self.kwargs)
                if self.is_running:
                    self.signals.result.emit(result)
            except Exception as e:
                if self.is_running:
                    self.signals.error.emit(str(e))

            # Sleep in small chunks to allow responsive stopping
            elapsed = 0
            chunk = 50  # Check every 50ms
            while elapsed < self.interval_ms and self.is_running:
                self.msleep(min(chunk, self.interval_ms - elapsed))
                elapsed += chunk

        # Always emit finished - don't block signals
        self.signals.finished.emit()

    def stop(self) -> None:
        """
        Request the worker to stop.

        Does not block signals, allowing finished to emit properly.
        Waits up to 1 second for graceful shutdown.
        """
        with QMutexLocker(self._mutex):
            self._running = False

        # Wait for thread to finish gracefully
        if not self.wait(1000):
            # If still running after 1s, terminate (last resort)
            self.terminate()
            self.wait(100)


class CancellableWorker(QRunnable):
    """
    A worker that can be cancelled mid-execution.

    The function must periodically check worker.is_cancelled and exit early.

    Usage:
        def long_running_task(worker):
            for i in range(100):
                if worker.is_cancelled:
                    return None
                # do work...
            return result

        worker = CancellableWorker(long_running_task)
        worker.signals.result.connect(handle_result)
        QThreadPool.globalInstance().start(worker)
        # Later...
        worker.cancel()
    """

    def __init__(self, func: Callable[['CancellableWorker'], Any]) -> None:
        super().__init__()
        self.func = func
        self.signals = WorkerSignals()
        self._cancelled = False
        self._mutex = QMutex()
        self.setAutoDelete(True)

    @property
    def is_cancelled(self) -> bool:
        """Thread-safe check of cancellation state."""
        with QMutexLocker(self._mutex):
            return self._cancelled

    def cancel(self) -> None:
        """Request cancellation. Function must check is_cancelled to respond."""
        with QMutexLocker(self._mutex):
            self._cancelled = True

    def run(self) -> None:
        """Execute the function, passing self for cancellation checks."""
        try:
            if not self.is_cancelled:
                result = self.func(self)
                if not self.is_cancelled:
                    self.signals.result.emit(result)
        except Exception as e:
            if not self.is_cancelled:
                self.signals.error.emit(str(e))
        finally:
            self.signals.finished.emit()
