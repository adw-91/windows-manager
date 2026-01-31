"""
Windows Services Management Service.

Provides functionality to list, query, and control Windows services using WMI.
Services can be started, stopped, and restarted with proper error handling.
"""

import subprocess
from typing import List, Dict, Optional
from enum import Enum


class ServiceStatus(Enum):
    """Windows service status constants."""
    RUNNING = "Running"
    STOPPED = "Stopped"
    START_PENDING = "Start Pending"
    STOP_PENDING = "Stop Pending"
    CONTINUE_PENDING = "Continue Pending"
    PAUSE_PENDING = "Pause Pending"
    PAUSED = "Paused"
    UNKNOWN = "Unknown"


class ServiceStartMode(Enum):
    """Windows service start mode constants."""
    BOOT = "Boot"
    SYSTEM = "System"
    AUTO = "Auto"
    DEMAND = "Demand"
    DISABLED = "Disabled"
    UNKNOWN = "Unknown"


class ServiceInfo:
    """Manage and retrieve Windows services information."""

    def __init__(self):
        """Initialize the service."""
        pass

    def get_all_services(self) -> List[Dict[str, str]]:
        """
        Get list of all Windows services.

        Returns:
            List of dicts with keys: Name, DisplayName, Status, StartMode, PathName, Description
            Returns empty list if query fails.
        """
        services = []

        try:
            # Query all services using wmic with specific fields
            result = subprocess.run(
                [
                    'wmic',
                    'service',
                    'get',
                    'name,displayname,state,startmode,pathname,description',
                    '/format:list'
                ],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                return []

            # Parse output format: Key=Value pairs with blank lines between services
            # wmic outputs blank lines between each property and multiple blanks between records
            current_service = {}
            blank_count = 0

            for line in result.stdout.split('\n'):
                line_stripped = line.strip()

                if not line_stripped:
                    blank_count += 1
                    # If we have 2+ consecutive blank lines and collected a service, save it
                    if blank_count >= 2 and current_service and 'Name' in current_service:
                        services.append(self._normalize_service(current_service))
                        current_service = {}
                else:
                    blank_count = 0
                    # Parse key=value
                    if '=' in line_stripped:
                        key, value = line_stripped.split('=', 1)
                        current_service[key.strip()] = value.strip()

            # Don't forget the last service
            if current_service and 'Name' in current_service:
                services.append(self._normalize_service(current_service))

        except subprocess.TimeoutExpired:
            # Timeout getting services
            pass
        except Exception:
            # Other errors - return empty list
            pass

        return services

    def get_service_info(self, name: str) -> Optional[Dict[str, str]]:
        """
        Get detailed information about a specific service.

        Args:
            name: Service name (e.g., "Spooler", "wuauserv")

        Returns:
            Dict with service details, or None if service not found
        """
        try:
            # Query specific service (note: wmic where clause uses single quotes)
            result = subprocess.run(
                [
                    'wmic',
                    'service',
                    'where',
                    f"name='{name}'",
                    'get',
                    'name,displayname,state,startmode,pathname,description',
                    '/format:list'
                ],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                return None

            # Parse output
            service_data = {}
            for line in result.stdout.split('\n'):
                line_stripped = line.strip()
                if '=' in line_stripped:
                    key, value = line_stripped.split('=', 1)
                    service_data[key.strip()] = value.strip()

            if not service_data or 'Name' not in service_data:
                return None

            return self._normalize_service(service_data)

        except subprocess.TimeoutExpired:
            return None
        except Exception:
            return None

    def start_service(self, name: str) -> bool:
        """
        Start a Windows service.

        Args:
            name: Service name (e.g., "Spooler")

        Returns:
            True if command executed successfully, False otherwise
        """
        try:
            result = subprocess.run(
                ['net', 'start', name],
                capture_output=True,
                text=True,
                timeout=10
            )
            # net start returns 0 on success or if service already running
            return result.returncode in (0, 2)
        except Exception:
            return False

    def stop_service(self, name: str) -> bool:
        """
        Stop a Windows service.

        Args:
            name: Service name (e.g., "Spooler")

        Returns:
            True if command executed successfully, False otherwise
        """
        try:
            result = subprocess.run(
                ['net', 'stop', name],
                capture_output=True,
                text=True,
                timeout=10
            )
            # net stop returns 0 on success or if service already stopped
            return result.returncode in (0, 2)
        except Exception:
            return False

    def restart_service(self, name: str) -> bool:
        """
        Restart a Windows service.

        Args:
            name: Service name (e.g., "Spooler")

        Returns:
            True if both stop and start commands executed successfully
        """
        try:
            # Stop the service
            stop_result = subprocess.run(
                ['net', 'stop', name],
                capture_output=True,
                text=True,
                timeout=10
            )

            # Start the service
            start_result = subprocess.run(
                ['net', 'start', name],
                capture_output=True,
                text=True,
                timeout=10
            )

            # Consider success if both commands completed (even if already stopped/running)
            return stop_result.returncode in (0, 2) and start_result.returncode in (0, 2)

        except Exception:
            return False

    def _normalize_service(self, service_data: Dict[str, str]) -> Dict[str, str]:
        """
        Normalize service data to standard format.

        Args:
            service_data: Raw service data from wmic

        Returns:
            Normalized service dict with standard keys
        """
        # Note: wmic uses 'State' for current status, 'StartMode' for start type
        status = service_data.get('State', service_data.get('Status', 'Unknown'))
        start_mode = service_data.get('StartMode', 'Unknown')

        return {
            "Name": service_data.get('Name', ''),
            "DisplayName": service_data.get('DisplayName', service_data.get('Name', '')),
            "Status": status if status else 'Unknown',
            "StartMode": start_mode if start_mode else 'Unknown',
            "PathName": service_data.get('PathName', service_data.get('Pathname', '')),
            "Description": service_data.get('Description', ''),
        }


# Global instances
_service_info_instance: Optional[ServiceInfo] = None


def get_service_info() -> ServiceInfo:
    """Get the global ServiceInfo instance (singleton)."""
    global _service_info_instance
    if _service_info_instance is None:
        _service_info_instance = ServiceInfo()
    return _service_info_instance
