"""
Battery information widget for displaying detailed power status.

Shows battery percentage, charging status, time remaining, power plan,
and detailed battery health information similar to powercfg /batteryreport.
"""

import logging
import winreg

import psutil
from typing import Optional, Dict

from src.utils.win32.registry import read_string
from src.utils.win32.wmi import WmiConnection

logger = logging.getLogger(__name__)
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QProgressBar,
    QFrame,
    QSizePolicy,
)
from PySide6.QtCore import Qt, Slot, QTimer

from src.ui.theme import Colors
from src.utils.thread_utils import LoopingWorker, SingleRunWorker


class BatteryWidget(QWidget):
    """
    Widget displaying comprehensive battery status information.

    Features:
    - Battery percentage with progress bar
    - Charging/Discharging/Plugged in status
    - Time remaining estimate
    - Current power plan
    - Battery health information (design vs full charge capacity)
    - Battery chemistry and manufacturer
    - Cycle count estimation
    - Auto-refresh every 30 seconds
    """

    UPDATE_INTERVAL_MS = 30000  # 30 seconds

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._worker: Optional[LoopingWorker] = None
        self._detailed_info: Dict = {}
        self._init_ui()
        self._start_worker()
        self._load_detailed_info()

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

        # Basic details section
        basic_frame = QFrame()
        basic_frame.setFrameShape(QFrame.Shape.StyledPanel)
        basic_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {Colors.WIDGET.name()};
                border: 1px solid {Colors.BORDER.name()};
                border-radius: 4px;
            }}
        """)
        basic_layout = QVBoxLayout(basic_frame)
        basic_layout.setContentsMargins(12, 8, 12, 8)
        basic_layout.setSpacing(6)

        # Time remaining
        self._time_label = QLabel("Time remaining: --")
        self._time_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY.name()};")
        basic_layout.addWidget(self._time_label)

        # Power plan
        self._power_plan_label = QLabel("Power plan: --")
        self._power_plan_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY.name()};")
        basic_layout.addWidget(self._power_plan_label)

        layout.addWidget(basic_frame)

        # Detailed battery info section (powercfg style)
        detailed_frame = QFrame()
        detailed_frame.setFrameShape(QFrame.Shape.StyledPanel)
        detailed_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {Colors.WIDGET.name()};
                border: 1px solid {Colors.BORDER.name()};
                border-radius: 4px;
            }}
        """)
        detailed_layout = QVBoxLayout(detailed_frame)
        detailed_layout.setContentsMargins(12, 10, 12, 10)
        detailed_layout.setSpacing(8)

        # Section header
        header_label = QLabel("Battery Details")
        header_label.setStyleSheet(
            f"font-weight: bold; font-size: 12px; color: {Colors.TEXT_PRIMARY.name()};"
        )
        detailed_layout.addWidget(header_label)

        # Grid for detailed info
        details_grid = QGridLayout()
        details_grid.setSpacing(8)
        details_grid.setColumnStretch(1, 1)

        self._detail_labels = {}
        detail_items = [
            ("Manufacturer", "manufacturer"),
            ("Chemistry", "chemistry"),
            ("Design Capacity", "design_capacity"),
            ("Full Charge Capacity", "full_charge_capacity"),
            ("Battery Health", "health"),
            ("Cycle Count", "cycle_count"),
            ("Voltage", "voltage"),
            ("Wear Level", "wear_level"),
        ]

        for row, (label_text, key) in enumerate(detail_items):
            label = QLabel(f"{label_text}:")
            label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY.name()};")
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            value = QLabel("--")
            value.setStyleSheet(f"color: {Colors.TEXT_PRIMARY.name()};")
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

            details_grid.addWidget(label, row, 0)
            details_grid.addWidget(value, row, 1)
            self._detail_labels[key] = value

        detailed_layout.addLayout(details_grid)

        layout.addWidget(detailed_frame)

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

        # Get power plan from registry
        try:
            guid = read_string(
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\Power\User\PowerSchemes",
                "ActivePowerScheme",
            )
            if guid:
                name = read_string(
                    winreg.HKEY_LOCAL_MACHINE,
                    rf"SYSTEM\CurrentControlSet\Control\Power\User\PowerSchemes\{guid}",
                    "FriendlyName",
                )
                if name and not name.startswith("@"):
                    result["power_plan"] = name
                else:
                    # Map well-known GUIDs
                    known_plans = {
                        "381b4222-f694-41f0-9685-ff5bb260df2e": "Balanced",
                        "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c": "High performance",
                        "a1841308-3541-4fab-bc81-f71556f20b4a": "Power saver",
                    }
                    result["power_plan"] = known_plans.get(guid.lower(), guid)
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

    def _load_detailed_info(self) -> None:
        """Load detailed battery info using WMI in background."""
        from PySide6.QtCore import QThreadPool
        worker = SingleRunWorker(self._collect_detailed_info)
        worker.signals.result.connect(self._update_detailed_display)
        QThreadPool.globalInstance().start(worker)

    def _collect_detailed_info(self) -> Dict:
        """Collect detailed battery information via WMI COM (runs in worker thread)."""
        result = {
            "manufacturer": "Unknown",
            "chemistry": "Unknown",
            "design_capacity": "Unknown",
            "full_charge_capacity": "Unknown",
            "health": "Unknown",
            "cycle_count": "Unknown",
            "voltage": "Unknown",
            "wear_level": "Unknown",
        }

        try:
            # Win32_Battery from root\cimv2
            cimv2 = WmiConnection()
            battery = cimv2.query_single(
                "SELECT Name, DeviceID, DesignCapacity, DesignVoltage, Chemistry "
                "FROM Win32_Battery"
            )
            if battery:
                if battery.get("DesignCapacity"):
                    result["design_capacity"] = f"{battery['DesignCapacity']} mWh"
                if battery.get("DesignVoltage"):
                    result["voltage"] = f"{battery['DesignVoltage'] / 1000:.2f} V"

                chem_map = {
                    1: "Other", 2: "Unknown", 3: "Lead Acid",
                    4: "Nickel Cadmium", 5: "Nickel Metal Hydride",
                    6: "Lithium-ion", 7: "Zinc Air", 8: "Lithium Polymer",
                }
                if battery.get("Chemistry"):
                    result["chemistry"] = chem_map.get(battery["Chemistry"], "Unknown")

                if battery.get("Name") and result["manufacturer"] == "Unknown":
                    result["manufacturer"] = battery["Name"]

            # root\WMI namespace for detailed battery data
            try:
                wmi_ns = WmiConnection(r"root\WMI")

                # BatteryStaticData
                static = wmi_ns.query_single(
                    "SELECT DesignedCapacity, ManufactureName FROM BatteryStaticData"
                )
                if static:
                    if static.get("DesignedCapacity"):
                        result["design_capacity"] = f"{static['DesignedCapacity']} mWh"
                    mfr = static.get("ManufactureName")
                    if mfr:
                        if isinstance(mfr, (list, tuple)):
                            mfr = "".join(chr(c) for c in mfr if c > 0)
                        if isinstance(mfr, str) and mfr.strip():
                            result["manufacturer"] = mfr.strip()

                # BatteryFullChargedCapacity
                full = wmi_ns.query_single(
                    "SELECT FullChargedCapacity FROM BatteryFullChargedCapacity"
                )
                if full and full.get("FullChargedCapacity"):
                    full_cap = full["FullChargedCapacity"]
                    result["full_charge_capacity"] = f"{full_cap} mWh"

                    # Calculate health
                    if result["design_capacity"] != "Unknown":
                        try:
                            design_val = int(result["design_capacity"].replace(" mWh", ""))
                            if design_val > 0:
                                health = (full_cap / design_val) * 100
                                health = min(health, 100)
                                result["health"] = f"{health:.1f}%"
                                result["wear_level"] = f"{max(0, 100 - health):.1f}%"

                                if health < 50:
                                    result["health_color"] = Colors.ERROR
                                elif health < 80:
                                    result["health_color"] = Colors.WARNING
                                else:
                                    result["health_color"] = Colors.SUCCESS
                        except ValueError:
                            pass

                # BatteryCycleCount
                cycle = wmi_ns.query_single(
                    "SELECT CycleCount FROM BatteryCycleCount"
                )
                if cycle and cycle.get("CycleCount"):
                    result["cycle_count"] = str(cycle["CycleCount"])

                # BatteryStatus for current voltage
                status = wmi_ns.query_single(
                    "SELECT Voltage FROM BatteryStatus"
                )
                if status and status.get("Voltage") and status["Voltage"] > 0:
                    result["voltage"] = f"{status['Voltage'] / 1000:.2f} V"

            except Exception as e:
                logger.debug("root\\WMI battery query failed: %s", e)

        except Exception as e:
            result["error"] = str(e)

        return result

    @Slot(object)
    def _update_detailed_display(self, data: Dict) -> None:
        """Update detailed battery info display."""
        self._detailed_info = data

        for key, label in self._detail_labels.items():
            value = data.get(key, "--")
            label.setText(str(value))

            # Apply color coding for health
            if key == "health" and "health_color" in data:
                label.setStyleSheet(f"color: {data['health_color'].name()};")
            elif key == "wear_level" and "health_color" in data:
                # Inverse color for wear (high wear = bad)
                health_color = data.get("health_color", Colors.TEXT_PRIMARY)
                if health_color == Colors.SUCCESS:
                    label.setStyleSheet(f"color: {Colors.SUCCESS.name()};")
                elif health_color == Colors.WARNING:
                    label.setStyleSheet(f"color: {Colors.WARNING.name()};")
                else:
                    label.setStyleSheet(f"color: {Colors.ERROR.name()};")

    def cleanup(self) -> None:
        """Stop worker - call when removing widget."""
        if self._worker:
            self._worker.stop()
            self._worker = None

    def closeEvent(self, event) -> None:
        """Clean up on close."""
        self.cleanup()
        event.accept()
