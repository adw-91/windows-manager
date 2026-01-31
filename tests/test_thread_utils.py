"""Unit tests for thread utilities."""

import unittest
import time
from unittest.mock import MagicMock
from PySide6.QtCore import QThreadPool, QCoreApplication
from PySide6.QtWidgets import QApplication

from src.utils.thread_utils import (
    WorkerSignals,
    SingleRunWorker,
    LoopingWorker,
    CancellableWorker,
)

# Need QApplication for Qt event loop
app = None


def setUpModule():
    global app
    if QCoreApplication.instance() is None:
        app = QApplication([])


class TestWorkerSignals(unittest.TestCase):
    """Tests for WorkerSignals class."""

    def test_signals_exist(self):
        """Verify all expected signals are defined."""
        signals = WorkerSignals()
        self.assertTrue(hasattr(signals, 'finished'))
        self.assertTrue(hasattr(signals, 'result'))
        self.assertTrue(hasattr(signals, 'error'))
        self.assertTrue(hasattr(signals, 'progress'))


class TestSingleRunWorker(unittest.TestCase):
    """Tests for SingleRunWorker class."""

    def test_successful_execution(self):
        """Worker should emit result on success."""
        def add(a, b):
            return a + b

        worker = SingleRunWorker(add, 2, 3)
        result_handler = MagicMock()
        error_handler = MagicMock()
        finished_handler = MagicMock()

        worker.signals.result.connect(result_handler)
        worker.signals.error.connect(error_handler)
        worker.signals.finished.connect(finished_handler)

        pool = QThreadPool.globalInstance()
        pool.start(worker)
        pool.waitForDone(1000)

        # Process pending events
        QCoreApplication.processEvents()

        result_handler.assert_called_once_with(5)
        error_handler.assert_not_called()
        finished_handler.assert_called_once()

    def test_error_handling(self):
        """Worker should emit error on exception."""
        def failing_func():
            raise ValueError("Test error")

        worker = SingleRunWorker(failing_func)
        result_handler = MagicMock()
        error_handler = MagicMock()
        finished_handler = MagicMock()

        worker.signals.result.connect(result_handler)
        worker.signals.error.connect(error_handler)
        worker.signals.finished.connect(finished_handler)

        pool = QThreadPool.globalInstance()
        pool.start(worker)
        pool.waitForDone(1000)

        QCoreApplication.processEvents()

        result_handler.assert_not_called()
        error_handler.assert_called_once()
        self.assertIn("Test error", error_handler.call_args[0][0])
        finished_handler.assert_called_once()

    def test_kwargs_support(self):
        """Worker should pass kwargs to function."""
        def greet(name, greeting="Hello"):
            return f"{greeting}, {name}!"

        worker = SingleRunWorker(greet, "World", greeting="Hi")
        result_handler = MagicMock()

        worker.signals.result.connect(result_handler)

        pool = QThreadPool.globalInstance()
        pool.start(worker)
        pool.waitForDone(1000)

        QCoreApplication.processEvents()

        result_handler.assert_called_once_with("Hi, World!")


class TestLoopingWorker(unittest.TestCase):
    """Tests for LoopingWorker class."""

    def test_repeated_execution(self):
        """Worker should execute function multiple times."""
        call_count = [0]

        def counter():
            call_count[0] += 1
            return call_count[0]

        worker = LoopingWorker(50, counter)  # 50ms interval
        result_handler = MagicMock()

        worker.signals.result.connect(result_handler)
        worker.start()

        # Let it run for ~200ms (should get 3-4 calls)
        time.sleep(0.2)
        worker.stop()

        QCoreApplication.processEvents()

        # Should have been called multiple times
        self.assertGreaterEqual(result_handler.call_count, 2)

    def test_stop_emits_finished(self):
        """Worker should emit finished signal when stopped."""
        def noop():
            return None

        worker = LoopingWorker(100, noop)
        finished_handler = MagicMock()

        worker.signals.finished.connect(finished_handler)
        worker.start()

        time.sleep(0.05)
        worker.stop()

        QCoreApplication.processEvents()

        finished_handler.assert_called_once()

    def test_error_handling_continues(self):
        """Worker should continue running after errors."""
        call_count = [0]

        def sometimes_fails():
            call_count[0] += 1
            if call_count[0] == 1:
                raise ValueError("First call fails")
            return call_count[0]

        worker = LoopingWorker(50, sometimes_fails)
        error_handler = MagicMock()
        result_handler = MagicMock()

        worker.signals.error.connect(error_handler)
        worker.signals.result.connect(result_handler)
        worker.start()

        time.sleep(0.2)
        worker.stop()

        QCoreApplication.processEvents()

        # Should have one error and multiple successes
        error_handler.assert_called_once()
        self.assertGreaterEqual(result_handler.call_count, 1)


class TestCancellableWorker(unittest.TestCase):
    """Tests for CancellableWorker class."""

    def test_normal_execution(self):
        """Worker should complete normally if not cancelled."""
        def task(worker):
            total = 0
            for i in range(10):
                if worker.is_cancelled:
                    return None
                total += i
            return total

        worker = CancellableWorker(task)
        result_handler = MagicMock()

        worker.signals.result.connect(result_handler)

        pool = QThreadPool.globalInstance()
        pool.start(worker)
        pool.waitForDone(1000)

        QCoreApplication.processEvents()

        result_handler.assert_called_once_with(45)

    def test_cancellation(self):
        """Worker should stop early when cancelled."""
        iterations = [0]

        def slow_task(worker):
            for i in range(100):
                if worker.is_cancelled:
                    return "cancelled"
                iterations[0] += 1
                time.sleep(0.01)
            return "completed"

        worker = CancellableWorker(slow_task)
        result_handler = MagicMock()

        worker.signals.result.connect(result_handler)

        pool = QThreadPool.globalInstance()
        pool.start(worker)

        time.sleep(0.05)
        worker.cancel()
        pool.waitForDone(1000)

        QCoreApplication.processEvents()

        # Should have stopped early
        self.assertLess(iterations[0], 50)


if __name__ == '__main__':
    unittest.main()
