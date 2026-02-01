"""
Battery information widget for displaying detailed power status.

Shows battery percentage, charging status, time remaining, power plan,
and detailed battery health information similar to powercfg /batteryreport.
"""

import psutil
import subprocess
import os
import tempfile
import xml.etree.ElementTree as ET
from typing import Optional, Dict
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

    def _load_detailed_info(self) -> None:
        """Load detailed battery info using WMI in background."""
        from PySide6.QtCore import QThreadPool
        worker = SingleRunWorker(self._collect_detailed_info)
        worker.signals.result.connect(self._update_detailed_display)
        QThreadPool.globalInstance().start(worker)

    def _collect_detailed_info(self) -> Dict:
        """Collect detailed battery information (runs in worker thread)."""
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
            # Use PowerShell to get battery info more reliably
            # Get Win32_Battery info
            battery_ps = self._run_powershell(
                "Get-CimInstance -ClassName Win32_Battery | "
                "Select-Object -Property Name,DeviceID,EstimatedChargeRemaining,"
                "DesignCapacity,DesignVoltage,Chemistry | ConvertTo-Json"
            )
            if battery_ps:
                import json
                try:
                    battery_data = json.loads(battery_ps)
                    if isinstance(battery_data, list):
                        battery_data = battery_data[0] if battery_data else {}

                    if battery_data.get('DesignCapacity'):
                        result["design_capacity"] = f"{battery_data['DesignCapacity']} mWh"
                    if battery_data.get('DesignVoltage'):
                        result["voltage"] = f"{battery_data['DesignVoltage'] / 1000:.2f} V"

                    # Chemistry type
                    chem_map = {
                        1: "Other", 2: "Unknown", 3: "Lead Acid",
                        4: "Nickel Cadmium", 5: "Nickel Metal Hydride",
                        6: "Lithium-ion", 7: "Zinc Air", 8: "Lithium Polymer",
                    }
                    if battery_data.get('Chemistry'):
                        result["chemistry"] = chem_map.get(battery_data['Chemistry'], "Unknown")
                except json.JSONDecodeError:
                    pass

            # Try to get more detailed info from WMI root\WMI namespace
            static_ps = self._run_powershell(
                "Get-CimInstance -Namespace root/WMI -ClassName BatteryStaticData | "
                "Select-Object -Property DesignedCapacity,ManufactureName,SerialNumber,UniqueID | ConvertTo-Json"
            )
            if static_ps:
                import json
                try:
                    static_data = json.loads(static_ps)
                    if isinstance(static_data, list):
                        static_data = static_data[0] if static_data else {}

                    if static_data.get('DesignedCapacity'):
                        result["design_capacity"] = f"{static_data['DesignedCapacity']} mWh"
                    if static_data.get('ManufactureName'):
                        # ManufactureName comes as array of char codes
                        mfr = static_data['ManufactureName']
                        if isinstance(mfr, list):
                            mfr = ''.join(chr(c) for c in mfr if c > 0)
                        if mfr and mfr.strip():
                            result["manufacturer"] = mfr.strip()
                except json.JSONDecodeError:
                    pass

            # Get full charge capacity
            full_ps = self._run_powershell(
                "Get-CimInstance -Namespace root/WMI -ClassName BatteryFullChargedCapacity | "
                "Select-Object -Property FullChargedCapacity | ConvertTo-Json"
            )
            if full_ps:
                import json
                try:
                    full_data = json.loads(full_ps)
                    if isinstance(full_data, list):
                        full_data = full_data[0] if full_data else {}

                    if full_data.get('FullChargedCapacity'):
                        full_cap = full_data['FullChargedCapacity']
                        result["full_charge_capacity"] = f"{full_cap} mWh"

                        # Calculate health if we have design capacity
                        if result["design_capacity"] != "Unknown":
                            try:
                                design_val = int(result["design_capacity"].replace(" mWh", ""))
                                if design_val > 0:
                                    health = (full_cap / design_val) * 100
                                    health = min(health, 100)  # Cap at 100%
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
                except json.JSONDecodeError:
                    pass

            # Get cycle count
            cycle_ps = self._run_powershell(
                "Get-CimInstance -Namespace root/WMI -ClassName BatteryCycleCount | "
                "Select-Object -Property CycleCount | ConvertTo-Json"
            )
            if cycle_ps:
                import json
                try:
                    cycle_data = json.loads(cycle_ps)
                    if isinstance(cycle_data, list):
                        cycle_data = cycle_data[0] if cycle_data else {}

                    if cycle_data.get('CycleCount'):
                        result["cycle_count"] = str(cycle_data['CycleCount'])
                except json.JSONDecodeError:
                    pass

            # Get current voltage from BatteryStatus
            status_ps = self._run_powershell(
                "Get-CimInstance -Namespace root/WMI -ClassName BatteryStatus | "
                "Select-Object -Property Voltage | ConvertTo-Json"
            )
            if status_ps:
                import json
                try:
                    status_data = json.loads(status_ps)
                    if isinstance(status_data, list):
                        status_data = status_data[0] if status_data else {}

                    if status_data.get('Voltage') and status_data['Voltage'] > 0:
                        result["voltage"] = f"{status_data['Voltage'] / 1000:.2f} V"
                except json.JSONDecodeError:
                    pass

            # Fallback: try to get manufacturer from device name
            if result["manufacturer"] == "Unknown":
                name_ps = self._run_powershell(
                    "(Get-CimInstance -ClassName Win32_Battery).Name"
                )
                if name_ps and name_ps.strip():
                    result["manufacturer"] = name_ps.strip()

        except Exception as e:
            result["error"] = str(e)

        return result

    def _run_powershell(self, command: str) -> str:
        """Run a PowerShell command and return output."""
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", command],
                capture_output=True,
                text=True,
                timeout=10,
                encoding='utf-8',
                errors='replace'
            )
            return result.stdout.strip()
        except:
            return ""

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
