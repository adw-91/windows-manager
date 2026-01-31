"""
Windows Drivers Information Service.

Queries Windows drivers using WMI Win32_SystemDriver class to get system driver information.
"""

import subprocess
from typing import List, Dict, Optional


class DriverInfo:
    """Retrieve Windows system driver information using WMI."""

    def __init__(self):
        """Initialize the service."""
        pass

    def get_all_drivers(self) -> List[Dict[str, str]]:
        """
        Get list of all Windows system drivers from WMI.

        Returns:
            List of dicts with keys: Name, DisplayName, PathName, State, StartMode, Description
        """
        drivers = []

        try:
            # Query drivers using PowerShell and WMI
            ps_command = (
                "Get-WmiObject -Class Win32_SystemDriver | "
                "Select-Object Name,DisplayName,PathName,State,StartMode,Description | "
                "ConvertTo-Csv -NoTypeInformation"
            )

            result = subprocess.run(
                ['powershell', '-Command', ps_command],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0 and result.stdout.strip():
                drivers = self._parse_csv_output(result.stdout)
            else:
                # Fallback: try simpler query
                drivers = self._query_drivers_fallback()

        except subprocess.TimeoutExpired:
            # Query timed out, try fallback
            drivers = self._query_drivers_fallback()
        except Exception as e:
            # Any other error, try fallback
            drivers = self._query_drivers_fallback()

        return drivers

    def _parse_csv_output(self, output: str) -> List[Dict[str, str]]:
        """
        Parse CSV output from PowerShell ConvertTo-Csv command.

        Args:
            output: CSV formatted output from PowerShell

        Returns:
            List of driver dicts
        """
        drivers = []
        lines = output.strip().split('\n')

        if len(lines) < 2:
            return drivers

        # First line is header with field names
        header_line = lines[0]
        # Remove quotes and split by comma
        headers = [h.strip().strip('"') for h in header_line.split(',')]

        # Find indices of our required fields
        field_indices = {}
        for idx, header in enumerate(headers):
            if header in ['Name', 'DisplayName', 'PathName', 'State', 'StartMode', 'Description']:
                field_indices[header] = idx

        # Parse data lines
        for line in lines[1:]:
            if not line.strip():
                continue

            try:
                # Parse CSV line (handle quoted values)
                fields = self._parse_csv_line(line)

                # Build driver dict with available fields
                driver = {
                    'Name': fields[field_indices['Name']].strip('"') if 'Name' in field_indices and field_indices['Name'] < len(fields) else '',
                    'DisplayName': fields[field_indices['DisplayName']].strip('"') if 'DisplayName' in field_indices and field_indices['DisplayName'] < len(fields) else '',
                    'PathName': fields[field_indices['PathName']].strip('"') if 'PathName' in field_indices and field_indices['PathName'] < len(fields) else '',
                    'State': fields[field_indices['State']].strip('"') if 'State' in field_indices and field_indices['State'] < len(fields) else '',
                    'StartMode': fields[field_indices['StartMode']].strip('"') if 'StartMode' in field_indices and field_indices['StartMode'] < len(fields) else '',
                    'Description': fields[field_indices['Description']].strip('"') if 'Description' in field_indices and field_indices['Description'] < len(fields) else '',
                }

                # Only add if Name is not empty
                if driver['Name']:
                    drivers.append(driver)

            except (IndexError, ValueError):
                # Skip malformed lines
                continue

        return drivers

    def _parse_csv_line(self, line: str) -> List[str]:
        """
        Parse a CSV line handling quoted values.

        Args:
            line: CSV line to parse

        Returns:
            List of field values
        """
        fields = []
        current_field = ''
        in_quotes = False

        for char in line:
            if char == '"':
                in_quotes = not in_quotes
                current_field += char
            elif char == ',' and not in_quotes:
                fields.append(current_field)
                current_field = ''
            else:
                current_field += char

        fields.append(current_field)
        return fields

    def _query_drivers_fallback(self) -> List[Dict[str, str]]:
        """
        Fallback method to query drivers with simpler PowerShell query.

        Returns:
            List of driver dicts
        """
        drivers = []

        try:
            # Simpler PowerShell query with Format-List output
            ps_command = (
                "Get-WmiObject -Class Win32_SystemDriver | "
                "ForEach-Object { "
                "'Name: ' + $_.Name + '|DisplayName: ' + $_.DisplayName + '|PathName: ' + $_.PathName + "
                "'|State: ' + $_.State + '|StartMode: ' + $_.StartMode + '|Description: ' + $_.Description "
                "}"
            )

            result = subprocess.run(
                ['powershell', '-Command', ps_command],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0 and result.stdout.strip():
                drivers = self._parse_pipe_delimited_output(result.stdout)

        except Exception:
            # If even fallback fails, return empty list
            pass

        return drivers

    def _parse_pipe_delimited_output(self, output: str) -> List[Dict[str, str]]:
        """
        Parse pipe-delimited output from PowerShell fallback query.

        Args:
            output: Pipe-delimited formatted output from PowerShell

        Returns:
            List of driver dicts
        """
        drivers = []
        lines = output.strip().split('\n')

        for line in lines:
            if not line.strip():
                continue

            try:
                # Parse pipe-delimited format: "Name: X|DisplayName: Y|..."
                driver = {
                    'Name': '',
                    'DisplayName': '',
                    'PathName': '',
                    'State': '',
                    'StartMode': '',
                    'Description': '',
                }

                # Split by pipe and parse each field
                fields = line.split('|')
                for field in fields:
                    if ':' in field:
                        key, value = field.split(':', 1)
                        key = key.strip()
                        value = value.strip()

                        if key in driver:
                            driver[key] = value

                # Only add if Name is not empty
                if driver['Name']:
                    drivers.append(driver)

            except (ValueError, IndexError):
                # Skip malformed lines
                continue

        return drivers


# Global instances
_driver_info_instance: Optional[DriverInfo] = None


def get_driver_info() -> DriverInfo:
    """
    Get the global DriverInfo instance (singleton).

    Returns:
        Singleton DriverInfo instance
    """
    global _driver_info_instance
    if _driver_info_instance is None:
        _driver_info_instance = DriverInfo()
    return _driver_info_instance
