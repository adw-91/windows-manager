"""Enterprise and Domain Information Service - via native Win32 APIs."""

import logging
import os
import socket
import winreg
from typing import Any, Dict, Optional, List

import psutil
import win32api
import win32net

from src.utils.win32.security import get_current_user_sid, is_user_admin, get_current_username, get_current_domain
from src.utils.win32.gpo import get_applied_gpos
from src.utils.win32.registry import read_string, read_dword, enumerate_subkeys

logger = logging.getLogger(__name__)


class EnterpriseInfo:
    """Retrieve Windows enterprise, domain, and network information via native APIs."""

    def __init__(self):
        self._cache: Dict[str, Any] = {}

    def get_domain_info(self) -> Dict[str, str]:
        """Get domain information via NetGetJoinInformation."""
        result = {
            "domain_name": "Unknown",
            "domain_controller": "Unknown",
            "is_domain_joined": False,
        }

        try:
            name, join_status = win32net.NetGetJoinInformation(None)
            # join_status: 0=Unknown, 1=Unjoined, 2=Workgroup, 3=Domain
            if join_status == 3:
                result["domain_name"] = name
                result["is_domain_joined"] = True
                result["domain_controller"] = self._get_domain_controller()
            elif name:
                result["domain_name"] = name
        except Exception as e:
            logger.debug("Failed to get join info: %s", e)

        return result

    def get_computer_info(self) -> Dict[str, Any]:
        """Get computer system information."""
        result = {
            "computer_name": socket.gethostname(),
            "workgroup": "Unknown",
            "part_of_domain": False,
        }

        try:
            name, join_status = win32net.NetGetJoinInformation(None)
            if join_status == 3:
                result["workgroup"] = name
                result["part_of_domain"] = True
            elif join_status == 2:
                result["workgroup"] = name
        except Exception as e:
            logger.debug("Failed to get computer info: %s", e)

        return result

    def get_current_user(self) -> Dict[str, str]:
        """Get current user information via Win32 security APIs."""
        username = get_current_username()
        user_domain = get_current_domain()
        sid = get_current_user_sid() or "Unknown"
        admin = is_user_admin()

        return {
            "username": username,
            "user_domain": user_domain,
            "sid": sid,
            "is_admin": admin,
            "full_user": f"{user_domain}\\{username}",
        }

    def get_network_info(self) -> Dict[str, str]:
        """Get primary network adapter information via psutil."""
        result = {
            "primary_ip": "Unknown",
            "adapter_name": "Unknown",
            "dns_servers": [],
            "ipv6_address": "Unknown",
        }

        try:
            addrs = psutil.net_if_addrs()
            stats = psutil.net_if_stats()

            for interface, addr_list in addrs.items():
                if interface in stats and stats[interface].isup:
                    ipv4 = None
                    ipv6 = None
                    for addr in addr_list:
                        if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                            ipv4 = addr.address
                        elif addr.family == socket.AF_INET6 and not addr.address.startswith("::1"):
                            if not ipv6:
                                ipv6 = addr.address
                    if ipv4:
                        result["primary_ip"] = ipv4
                        result["adapter_name"] = interface
                        if ipv6:
                            result["ipv6_address"] = ipv6
                        break
        except Exception as e:
            logger.debug("Failed to get network info: %s", e)

        # Get DNS servers from WMI COM
        try:
            from src.utils.win32.wmi import WmiConnection
            conn = WmiConnection()
            rows = conn.query(
                "SELECT DNSServerSearchOrder FROM Win32_NetworkAdapterConfiguration "
                "WHERE IPEnabled = True"
            )
            dns_list = []
            for row in rows:
                servers = row.get("DNSServerSearchOrder")
                if servers:
                    for s in servers:
                        if s and s not in dns_list:
                            dns_list.append(s)
            if dns_list:
                result["dns_servers"] = dns_list
        except Exception:
            pass

        return result

    def get_azure_ad_info(self) -> Dict[str, Any]:
        """Check if computer is Azure AD joined via registry."""
        result = {
            "is_azure_ad_joined": False,
            "tenant_id": "Unknown",
            "device_id": "Unknown",
            "device_name": "Unknown",
            "tenant_name": "Unknown",
        }

        try:
            # Check registry for Azure AD join info
            join_info_path = r"SYSTEM\CurrentControlSet\Control\CloudDomainJoin\JoinInfo"
            subkeys = enumerate_subkeys(winreg.HKEY_LOCAL_MACHINE, join_info_path)

            if subkeys:
                result["is_azure_ad_joined"] = True
                # First subkey contains join details
                sk = subkeys[0]
                full_path = f"{join_info_path}\\{sk}"

                tenant_id = read_string(winreg.HKEY_LOCAL_MACHINE, full_path, "TenantId")
                if tenant_id:
                    result["tenant_id"] = tenant_id

                device_id = read_string(winreg.HKEY_LOCAL_MACHINE, full_path, "DeviceId")
                # Fallback: TenantInfo path may have the canonical device ID
                if not device_id and tenant_id:
                    device_id = read_string(
                        winreg.HKEY_LOCAL_MACHINE,
                        rf"SYSTEM\CurrentControlSet\Control\CloudDomainJoin\TenantInfo\{tenant_id}",
                        "DeviceId",
                    )
                if device_id:
                    result["device_id"] = device_id

                # TenantName — try CDJ\AAD first, then TenantInfo fallback
                tenant_name = read_string(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\Microsoft\Windows\CurrentVersion\CDJ\AAD",
                    "TenantName",
                )
                if not tenant_name and tenant_id:
                    tenant_name = read_string(
                        winreg.HKEY_LOCAL_MACHINE,
                        rf"SYSTEM\CurrentControlSet\Control\CloudDomainJoin\TenantInfo\{tenant_id}",
                        "DisplayName",
                    )
                if tenant_name:
                    result["tenant_name"] = tenant_name

                result["device_name"] = socket.gethostname()
        except Exception as e:
            logger.debug("Failed to get Azure AD info: %s", e)

        return result

    def get_group_policy_info(self) -> Dict[str, Any]:
        """Get applied GPOs via GetAppliedGPOListW."""
        computer_policies = get_applied_gpos(machine=True)
        user_policies = get_applied_gpos(machine=False)

        total = len(computer_policies) + len(user_policies)
        return {
            "gpos_applied": total > 0,
            "applied_gpo_count": total,
            "gpresult_available": True,
            "computer_policies": computer_policies,
            "user_policies": user_policies,
        }

    def _get_domain_controller(self) -> str:
        """Get the primary domain controller name via NetGetDCName.

        Falls back to cached DC from Group Policy History registry when
        the live DC is unreachable (e.g. off-network / VPN disconnected).
        """
        # Try live DC first
        try:
            dc_name = win32net.NetGetDCName(None, None)
            if dc_name:
                return dc_name.lstrip("\\")
        except Exception:
            pass

        # Fallback: cached DC from Group Policy History
        cached_dc = read_string(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Group Policy\History",
            "DCName",
        )
        if cached_dc:
            return f"{cached_dc.lstrip(chr(92))} (offline)"

        return "Unknown"

    def get_intune_info(self) -> Dict[str, Any]:
        """Check Intune/MDM enrollment and policy status via registry."""
        result: Dict[str, Any] = {
            "is_enrolled": False,
            "provider": "Unknown",
            "upn": "Unknown",
            "enrollment_state": 0,
            "policy_count": 0,
            "policy_areas": [],
        }

        try:
            # Find MDM enrollment under HKLM\SOFTWARE\Microsoft\Enrollments\*
            enrollments_path = r"SOFTWARE\Microsoft\Enrollments"
            enrollment_guids = enumerate_subkeys(winreg.HKEY_LOCAL_MACHINE, enrollments_path)

            mdm_providers = ("MS DM Server", "Microsoft Device Management")
            best_enrollment = None
            for guid in enrollment_guids:
                full_path = f"{enrollments_path}\\{guid}"
                provider_id = read_string(
                    winreg.HKEY_LOCAL_MACHINE, full_path, "ProviderID",
                )
                if provider_id and provider_id in mdm_providers:
                    upn = read_string(winreg.HKEY_LOCAL_MACHINE, full_path, "UPN")
                    # Prefer enrollment with a UPN (active user enrollment)
                    if best_enrollment is None or (upn and not best_enrollment.get("upn")):
                        best_enrollment = {
                            "provider": provider_id,
                            "upn": upn,
                            "path": full_path,
                        }

            if best_enrollment:
                result["is_enrolled"] = True
                result["provider"] = best_enrollment["provider"]

                upn = best_enrollment.get("upn")
                if upn:
                    # Strip trailing @GUID suffix from enrollment UPN
                    parts = upn.split("@")
                    if len(parts) >= 3:
                        upn = "@".join(parts[:2])
                    result["upn"] = upn

                state = read_dword(
                    winreg.HKEY_LOCAL_MACHINE, best_enrollment["path"], "EnrollmentState",
                )
                if state is not None:
                    result["enrollment_state"] = state

            # Policy areas from PolicyManager
            policy_path = r"SOFTWARE\Microsoft\PolicyManager\current\device"
            policy_areas = enumerate_subkeys(winreg.HKEY_LOCAL_MACHINE, policy_path)
            if policy_areas:
                result["policy_count"] = len(policy_areas)
                result["policy_areas"] = sorted(policy_areas)

        except Exception as e:
            logger.debug("Failed to get Intune info: %s", e)

        return result

    def get_all_enterprise_info(self) -> Dict[str, Any]:
        """Get all enterprise information as a comprehensive dictionary."""
        return {
            "Domain": self.get_domain_info(),
            "Computer": self.get_computer_info(),
            "Current User": self.get_current_user(),
            "Network": self.get_network_info(),
            "Azure AD": self.get_azure_ad_info(),
            "Group Policy": self.get_group_policy_info(),
            "Intune": self.get_intune_info(),
        }


_enterprise_info: Optional[EnterpriseInfo] = None


def get_enterprise_info() -> EnterpriseInfo:
    """Get the global EnterpriseInfo instance."""
    global _enterprise_info
    if _enterprise_info is None:
        _enterprise_info = EnterpriseInfo()
    return _enterprise_info
