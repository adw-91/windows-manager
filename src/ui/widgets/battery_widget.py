"""
Battery information widget for displaying power status.

Shows battery percentage, charging status, time remaining, and power plan.
"""

import psutil
import subprocess
from typing import Optional, Dict
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QFrame,
)
from PySide6.QtCore import Qt, Slot, QTimer

from src.ui.theme import Colors
from src.utils.thread_utils import LoopingWorker


class BatteryWidget(QWidget):
    """
    Widget displaying battery status information.

    Features:
    - Battery percentage with progress bar
    - Charging/Discharging/Plugged in status
    - Time remaining estimate
    - Current power plan
    - Auto-refresh every 30 seconds
    """

    UPDATE_INTERVAL_MS = 30000  # 30 seconds

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._worker: Optional[LoopingWorker] = None
        self._init_ui()
        self._start_worker()

    def _init_ui(self) -> None:
        """Initialize the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # Battery percentage section
        percent_layout = QHBoxLayout()
        percent_layout.setSpacing(12)

        # Battery icon and percentage
        self._percent_label = QLabel("--")
        self._percent_label.setStyleSheet(
            f"font-size: 28px; font-weight: bold; color: {Colors.TEXT_PRIMARY.name()};"
        )
        percent_layout.addWidget(self._percent_label)

        # Progress bar
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(20)
        self._progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {Colors.PROGRESS_BG.name()};
                border: 1px solid {Colors.BORDER.name()};
                border-radius: 4px;
            }}
            QProgressBar::chunk {{
                background-color: {Colors.SUCCESS.name()};
                border-radius: 3px;
            }}
        """)
        percent_layout.addWidget(self._progress_bar)

        layout.addLayout(percent_layout)

        # Status label
        self._status_label = QLabel("Checking battery status...")
        self._status_label.setStyleSheet(
            f"font-size: 13px; color: {Colors.TEXT_PRIMARY.name()};"
        )
        layout.addWidget(self._status_label)

        # Details section
        details_frame = QFrame()
        details_frame.setFrameShape(QFrame.Shape.StyledPanel)
        details_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {Colors.WIDGET.name()};
                border: 1px solid {Colors.BORDER.name()};
                border-radius: 4px;
            }}
        """)
        details_layout = QVBoxLayout(details_frame)
        details_layout.setContentsMargins(12, 8, 12, 8)
        details_layout.setSpacing(6)

        # Time remaining
        self._time_label = QLabel("Time remaining: --")
        self._time_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY.name()};")
        details_layout.addWidget(self._time_label)

        # Power plan
        self._power_plan_label = QLabel("Power plan: --")
        self._power_plan_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY.name()};")
        details_layout.addWidget(self._power_plan_label)

        layout.addWidget(details_frame)

        layout.addStretch()

    def _start_worker(self) -> None:
        """Start background worker for battery updates."""
        self._worker = LoopingWorker(
            self.UPDATE_INTERVAL_MS,
            self._collect_battery_info,
        )
        self._worker.signals.result.connect(self._update_display)
        self._worker.start()

        # Trigger immediate first update
        QTimer.singleShot(100, self._trigger_immediate_update)

    def _trigger_immediate_update(self) -> None:
        """Trigger an immediate battery update."""
        try:
            data = self._collect_battery_info()
            self._update_display(data)
        except Exception:
            pass

    def _collect_battery_info(self) -> Dict:
        """Collect battery information (runs in worker thread)."""
        result = {
            "percent": None,
            "plugged": False,
            "status": "Unknown",
            "time_remaining": None,
            "power_plan": "Unknown",
        }

        try:
            battery = psutil.sensors_battery()
            if battery:
                result["percent"] = battery.percent
                result["plugged"] = battery.power_plugged

                if battery.power_plugged:
                    if battery.percent >= 100:
                        result["status"] = "Fully charged"
                    else:
                        result["status"] = "Charging"
                else:
                    result["status"] = "On battery"

                # Time remaining (in seconds)
                if battery.secsleft != psutil.POWER_TIME_UNLIMITED and battery.secsleft != psutil.POWER_TIME_UNKNOWN:
                    result["time_remaining"] = battery.secsleft
        except Exception:
            pass

        # Get power plan
        try:
            proc = subprocess.run(
                ['powercfg', '/getactivescheme'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if proc.returncode == 0:
                output = proc.stdout.strip()
                # Parse output like: "Power Scheme GUID: xxx  (Balanced)"
                if '(' in output and ')' in output:
                    start = output.rfind('(') + 1
                    end = output.rfind(')')
                    result["power_plan"] = output[start:end]
        except Exception:
            pass

        return result

    @Slot(object)
    def _update_display(self, data: Dict) -> None:
        """Update display with battery data (runs in UI thread)."""
        percent = data.get("percent")

        if percent is not None:
            # Update percentage
            self._percent_label.setText(f"{percent:.0f}%")
            self._progress_bar.setValue(int(percent))

            # Update progress bar color based on level
            if percent <= 20:
                chunk_color = Colors.ERROR.name()
            elif percent <= 40:
                chunk_color = Colors.WARNING.name()
            else:
                chunk_color = Colors.SUCCESS.name()

            self._progress_bar.setStyleSheet(f"""
                QProgressBar {{
                    background-color: {Colors.PROGRESS_BG.name()};
                    border: 1px solid {Colors.BORDER.name()};
                    border-radius: 4px;
                }}
                QProgressBar::chunk {{
                    background-color: {chunk_color};
                    border-radius: 3px;
                }}
            """)
        else:
            self._percent_label.setText("N/A")
            self._progress_bar.setValue(0)

        # Update status
        status = data.get("status", "Unknown")
        plugged = data.get("plugged", False)

        if plugged:
            status_icon = "🔌"
        else:
            status_icon = "🔋"

        self._status_label.setText(f"{status_icon} {status}")

        # Update time remaining
        time_remaining = data.get("time_remaining")
        if time_remaining is not None:
            hours = int(time_remaining // 3600)
            minutes = int((time_remaining % 3600) // 60)

            if hours > 0:
                time_str = f"{hours}h {minutes}m remaining"
            else:
                time_str = f"{minutes} minutes remaining"

            self._time_label.setText(f"Time remaining: {time_str}")
        elif plugged:
            if percent is not None and percent >= 100:
                self._time_label.setText("Fully charged")
            else:
                self._time_label.setText("Charging...")
        else:
            self._time_label.setText("Time remaining: Calculating...")

        # Update power plan
        power_plan = data.get("power_plan", "Unknown")
        self._power_plan_label.setText(f"Power plan: {power_plan}")

    def cleanup(self) -> None:
        """Stop worker - call when removing widget."""
        if self._worker:
            self._worker.stop()
            self._worker = None

    def closeEvent(self, event) -> None:
        """Clean up on close."""
        self.cleanup()
        event.accept()
