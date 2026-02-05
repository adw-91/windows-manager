"""
Windows Services Management Service.

Provides functionality to list, query, and control Windows services
using the Win32 Service Control Manager API (win32service).
"""

import logging
import time
from typing import List, Dict, Optional
from enum import Enum

import win32service

logger = logging.getLogger(__name__)

# Map win32service state constants to status strings
_STATE_MAP = {
    win32service.SERVICE_STOPPED: "Stopped",
    win32service.SERVICE_START_PENDING: "Start Pending",
    win32service.SERVICE_STOP_PENDING: "Stop Pending",
    win32service.SERVICE_RUNNING: "Running",
    win32service.SERVICE_CONTINUE_PENDING: "Continue Pending",
    win32service.SERVICE_PAUSE_PENDING: "Pause Pending",
    win32service.SERVICE_PAUSED: "Paused",
}

# Map win32service start type constants to start mode strings
_START_TYPE_MAP = {
    win32service.SERVICE_BOOT_START: "Boot",
    win32service.SERVICE_SYSTEM_START: "System",
    win32service.SERVICE_AUTO_START: "Auto",
    win32service.SERVICE_DEMAND_START: "Demand",
    win32service.SERVICE_DISABLED: "Disabled",
}


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
    """Manage and retrieve Windows services information via Win32 SCM API."""

    def __init__(self):
        """Initialize the service."""
        pass

    def get_all_services(self) -> List[Dict[str, str]]:
        """Get list of all Windows services.

        Returns:
            List of dicts with keys: Name, DisplayName, Status, StartMode, PathName, Description
        """
        services = []
        try:
            scm = win32service.OpenSCManager(
                None, None, win32service.SC_MANAGER_ENUMERATE_SERVICE
            )
            try:
                # EnumServicesStatusEx returns list of dicts with keys:
                # ServiceName, DisplayName, ServiceType, CurrentState, etc.
                svc_list = win32service.EnumServicesStatusEx(
                    scm,
                    win32service.SERVICE_WIN32,
                    win32service.SERVICE_STATE_ALL,
                    None,  # group name
                )
                for svc_info in svc_list:
                    svc_name = svc_info["ServiceName"]
                    display_name = svc_info["DisplayName"]
                    state = svc_info["CurrentState"]
                    status_str = _STATE_MAP.get(state, "Unknown")

                    # Get config for start mode, path, description
                    start_mode = "Unknown"
                    path_name = ""
                    description = ""
                    try:
                        svc_handle = win32service.OpenService(
                            scm, svc_name, win32service.SERVICE_QUERY_CONFIG
                        )
                        try:
                            config = win32service.QueryServiceConfig(svc_handle)
                            # config is tuple: (svc_type, start_type, error_control, binary_path, load_order, tag_id, deps, svc_start_name, display_name)
                            start_mode = _START_TYPE_MAP.get(config[1], "Unknown")
                            path_name = config[3] or ""
                            try:
                                desc = win32service.QueryServiceConfig2(
                                    svc_handle, win32service.SERVICE_CONFIG_DESCRIPTION
                                )
                                description = desc or ""
                            except Exception:
                                pass
                        finally:
                            win32service.CloseServiceHandle(svc_handle)
                    except Exception:
                        pass

                    services.append({
                        "Name": svc_name,
                        "DisplayName": display_name or svc_name,
                        "Status": status_str,
                        "StartMode": start_mode,
                        "PathName": path_name,
                        "Description": description,
                    })
            finally:
                win32service.CloseServiceHandle(scm)
        except Exception as e:
            logger.warning("Failed to enumerate services: %s", e)
        return services

    def get_service_info(self, name: str) -> Optional[Dict[str, str]]:
        """Get detailed information about a specific service.

        Args:
            name: Service name (e.g., "Spooler", "wuauserv")

        Returns:
            Dict with service details, or None if service not found
        """
        try:
            scm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_CONNECT)
            try:
                svc_handle = win32service.OpenService(
                    scm, name,
                    win32service.SERVICE_QUERY_STATUS | win32service.SERVICE_QUERY_CONFIG
                )
                try:
                    # Get status
                    status = win32service.QueryServiceStatusEx(svc_handle)
                    state = status["CurrentState"]
                    status_str = _STATE_MAP.get(state, "Unknown")

                    # Get config
                    config = win32service.QueryServiceConfig(svc_handle)
                    start_mode = _START_TYPE_MAP.get(config[1], "Unknown")
                    path_name = config[3] or ""
                    display_name = config[8] or name

                    # Get description
                    description = ""
                    try:
                        desc = win32service.QueryServiceConfig2(
                            svc_handle, win32service.SERVICE_CONFIG_DESCRIPTION
                        )
                        description = desc or ""
                    except Exception:
                        pass

                    return {
                        "Name": name,
                        "DisplayName": display_name,
                        "Status": status_str,
                        "StartMode": start_mode,
                        "PathName": path_name,
                        "Description": description,
                    }
                finally:
                    win32service.CloseServiceHandle(svc_handle)
            finally:
                win32service.CloseServiceHandle(scm)
        except Exception:
            return None

    def start_service(self, name: str) -> bool:
        """Start a Windows service.

        Args:
            name: Service name (e.g., "Spooler")

        Returns:
            True if service started successfully, False otherwise
        """
        try:
            scm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_CONNECT)
            try:
                svc_handle = win32service.OpenService(
                    scm, name, win32service.SERVICE_START | win32service.SERVICE_QUERY_STATUS
                )
                try:
                    # Check if already running
                    status = win32service.QueryServiceStatusEx(svc_handle)
                    if status["CurrentState"] == win32service.SERVICE_RUNNING:
                        return True
                    win32service.StartService(svc_handle, None)
                    return True
                finally:
                    win32service.CloseServiceHandle(svc_handle)
            finally:
                win32service.CloseServiceHandle(scm)
        except Exception as e:
            logger.warning("Failed to start service '%s': %s", name, e)
            return False

    def stop_service(self, name: str) -> bool:
        """Stop a Windows service.

        Args:
            name: Service name (e.g., "Spooler")

        Returns:
            True if service stopped successfully, False otherwise
        """
        try:
            scm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_CONNECT)
            try:
                svc_handle = win32service.OpenService(
                    scm, name, win32service.SERVICE_STOP | win32service.SERVICE_QUERY_STATUS
                )
                try:
                    status = win32service.QueryServiceStatusEx(svc_handle)
                    if status["CurrentState"] == win32service.SERVICE_STOPPED:
                        return True
                    win32service.ControlService(svc_handle, win32service.SERVICE_CONTROL_STOP)
                    return True
                finally:
                    win32service.CloseServiceHandle(svc_handle)
            finally:
                win32service.CloseServiceHandle(scm)
        except Exception as e:
            logger.warning("Failed to stop service '%s': %s", name, e)
            return False

    def restart_service(self, name: str) -> bool:
        """Restart a Windows service.

        Args:
            name: Service name (e.g., "Spooler")

        Returns:
            True if both stop and start succeeded
        """
        stopped = self.stop_service(name)
        if stopped:
            time.sleep(0.5)
        return self.start_service(name)


# Global instances
_service_info_instance: Optional[ServiceInfo] = None


def get_service_info() -> ServiceInfo:
    """Get the global ServiceInfo instance (singleton)."""
    global _service_info_instance
    if _service_info_instance is None:
        _service_info_instance = ServiceInfo()
    return _service_info_instance
