"""Thread-safe WMI COM connection wrapper using win32com.client."""
import logging
import pythoncom
import win32com.client
from typing import Any, Optional

logger = logging.getLogger(__name__)


class WmiConnection:
    """WMI COM connection wrapper. Initialize once per thread.

    Uses win32com.client.Dispatch to connect to WMI.
    Handles COM initialization per-thread via pythoncom.CoInitialize.
    """

    def __init__(self, namespace: str = r"root\cimv2"):
        pythoncom.CoInitialize()
        locator = win32com.client.Dispatch("WbemScripting.SWbemLocator")
        self._conn = locator.ConnectServer(".", namespace)

    def query(self, wql: str) -> list[dict[str, Any]]:
        """Execute WQL query, return list of dicts."""
        results = []
        try:
            for obj in self._conn.ExecQuery(wql):
                row = {}
                for prop in obj.Properties_:
                    row[prop.Name] = prop.Value
                results.append(row)
        except Exception as e:
            logger.warning("WMI query failed: %s — %s", wql, e)
        return results

    def query_single(self, wql: str) -> Optional[dict[str, Any]]:
        """Execute WQL query, return first result or None."""
        results = self.query(wql)
        return results[0] if results else None
