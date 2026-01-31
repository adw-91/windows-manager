"""Enterprise and Domain Information Service - Fetches Windows domain and enterprise information"""

import subprocess
import socket
import os
from typing import Dict, Optional, List


class EnterpriseInfo:
    """Retrieve Windows enterprise, domain, and network information"""

    def __init__(self):
        self._cache = {}

    def get_domain_info(self) -> Dict[str, str]:
        """
        Get domain information using Win32_ComputerSystem WMI class.

        Returns:
            Dictionary with keys:
                - domain_name: Name of the domain
                - domain_controller: Primary domain controller
                - is_domain_joined: True if computer is domain-joined
        """
        result = {
            "domain_name": "Unknown",
            "domain_controller": "Unknown",
            "is_domain_joined": False
        }

        try:
            # Query Win32_ComputerSystem for domain info
            wmic_result = subprocess.run(
                ['wmic', 'computersystem', 'get', 'domain,partofdomainbynet'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if wmic_result.returncode == 0:
                lines = [line.strip() for line in wmic_result.stdout.strip().split('\n') if line.strip()]
                if len(lines) > 1:
                    # Parse domain information
                    parts = lines[1].split()
                    if len(parts) >= 1:
                        domain = parts[0]
                        if domain and domain.upper() != 'WORKGROUP':
                            result["domain_name"] = domain
                            result["is_domain_joined"] = True
                            # Try to get domain controller
                            result["domain_controller"] = self._get_domain_controller()
        except Exception:
            pass

        return result

    def get_computer_info(self) -> Dict[str, any]:
        """
        Get computer system information including name and domain status.

        Returns:
            Dictionary with keys:
                - computer_name: NetBIOS name of the computer
                - workgroup: Workgroup or domain name
                - part_of_domain: Boolean indicating domain membership
        """
        result = {
            "computer_name": socket.gethostname(),
            "workgroup": "Unknown",
            "part_of_domain": False
        }

        try:
            # Query Win32_ComputerSystem
            wmic_result = subprocess.run(
                ['wmic', 'computersystem', 'get', 'name,workgroup,partofdomainbynet'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if wmic_result.returncode == 0:
                lines = [line.strip() for line in wmic_result.stdout.strip().split('\n') if line.strip()]
                if len(lines) > 1:
                    parts = lines[1].split()
                    if len(parts) >= 3:
                        result["computer_name"] = parts[0]
                        result["workgroup"] = parts[1]
                        result["part_of_domain"] = parts[2].lower() == 'true'
        except Exception:
            pass

        return result

    def get_current_user(self) -> Dict[str, str]:
        """
        Get current user information including username, domain, SID, and admin status.

        Returns:
            Dictionary with keys:
                - username: Current user's username
                - user_domain: User's domain (or computer name for local users)
                - sid: User's Security Identifier
                - is_admin: Boolean indicating if user has admin privileges
                - full_user: Full username in DOMAIN\\username format
        """
        result = {
            "username": "Unknown",
            "user_domain": "Unknown",
            "sid": "Unknown",
            "is_admin": False,
            "full_user": "Unknown"
        }

        try:
            # Get current user from environment
            username = os.getenv('USERNAME')
            userdomain = os.getenv('USERDOMAIN')

            if username:
                result["username"] = username
            if userdomain:
                result["user_domain"] = userdomain

            if username and userdomain:
                result["full_user"] = f"{userdomain}\\{username}"

            # Get SID using PowerShell
            ps_result = subprocess.run(
                ['powershell', '-Command',
                 "[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value"],
                capture_output=True,
                text=True,
                timeout=5
            )

            if ps_result.returncode == 0:
                sid = ps_result.stdout.strip()
                if sid:
                    result["sid"] = sid

            # Check admin status using PowerShell
            admin_result = subprocess.run(
                ['powershell', '-Command',
                 '[Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent() | '
                 'ForEach-Object { $_.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator) }'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if admin_result.returncode == 0:
                is_admin = admin_result.stdout.strip().lower() == 'true'
                result["is_admin"] = is_admin
        except Exception:
            pass

        return result

    def get_network_info(self) -> Dict[str, str]:
        """
        Get primary network adapter information including IP address and DNS servers.

        Returns:
            Dictionary with keys:
                - primary_ip: Primary IPv4 address
                - adapter_name: Name of the primary network adapter
                - dns_servers: List of DNS servers
                - ipv6_address: Primary IPv6 address (if available)
        """
        result = {
            "primary_ip": "Unknown",
            "adapter_name": "Unknown",
            "dns_servers": [],
            "ipv6_address": "Unknown"
        }

        try:
            # Get network configuration using PowerShell
            ps_result = subprocess.run(
                ['powershell', '-Command',
                 'Get-NetIPAddress -AddressFamily IPv4 -PrefixLength 24 | '
                 'Select-Object IPAddress,InterfaceAlias | ConvertTo-Json'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if ps_result.returncode == 0:
                import json
                try:
                    data = json.loads(ps_result.stdout)
                    if isinstance(data, list) and len(data) > 0:
                        result["primary_ip"] = data[0].get("IPAddress", "Unknown")
                        result["adapter_name"] = data[0].get("InterfaceAlias", "Unknown")
                    elif isinstance(data, dict):
                        result["primary_ip"] = data.get("IPAddress", "Unknown")
                        result["adapter_name"] = data.get("InterfaceAlias", "Unknown")
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass

        # Get DNS servers
        try:
            dns_result = subprocess.run(
                ['powershell', '-Command',
                 'Get-DnsClientServerAddress -AddressFamily IPv4 | '
                 'Where-Object { $_.ServerAddresses } | Select-Object -ExpandProperty ServerAddresses'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if dns_result.returncode == 0:
                dns_servers = [line.strip() for line in dns_result.stdout.strip().split('\n') if line.strip()]
                if dns_servers:
                    result["dns_servers"] = dns_servers
        except Exception:
            pass

        # Try to get IPv6 address
        try:
            ipv6_result = subprocess.run(
                ['powershell', '-Command',
                 'Get-NetIPAddress -AddressFamily IPv6 | '
                 'Where-Object { $_.PrefixLength -eq 64 } | '
                 'Select-Object -First 1 -ExpandProperty IPAddress'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if ipv6_result.returncode == 0:
                ipv6 = ipv6_result.stdout.strip()
                if ipv6:
                    result["ipv6_address"] = ipv6
        except Exception:
            pass

        return result

    def get_azure_ad_info(self) -> Dict[str, any]:
        """
        Check if computer is Azure AD joined using dsregcmd /status.

        Returns:
            Dictionary with keys:
                - is_azure_ad_joined: Boolean indicating Azure AD membership
                - tenant_id: Azure AD tenant ID (if available)
                - device_id: Azure AD device ID (if available)
                - device_name: Azure AD device name (if available)
                - tenant_name: Azure AD tenant name (if available)
        """
        result = {
            "is_azure_ad_joined": False,
            "tenant_id": "Unknown",
            "device_id": "Unknown",
            "device_name": "Unknown",
            "tenant_name": "Unknown"
        }

        try:
            # Run dsregcmd /status to get Azure AD join status
            dsreg_result = subprocess.run(
                ['dsregcmd', '/status'],
                capture_output=True,
                text=True,
                timeout=10
            )

            if dsreg_result.returncode == 0:
                output = dsreg_result.stdout
                # Parse the output
                for line in output.split('\n'):
                    line = line.strip()
                    if ':' in line:
                        key, value = line.split(':', 1)
                        key = key.strip()
                        value = value.strip()

                        if key == 'AzureAdJoined' or key == 'Joined' and 'Azure' in output:
                            result["is_azure_ad_joined"] = value.lower() == 'yes'
                        elif key == 'TenantId':
                            result["tenant_id"] = value
                        elif key == 'DeviceId':
                            result["device_id"] = value
                        elif key == 'DeviceName':
                            result["device_name"] = value
                        elif key == 'TenantName':
                            result["tenant_name"] = value
        except FileNotFoundError:
            # dsregcmd might not be available on non-domain machines
            pass
        except Exception:
            pass

        return result

    def get_group_policy_info(self) -> Dict[str, any]:
        """
        Check if Group Policy Objects (GPOs) are applied using gpresult.

        Returns:
            Dictionary with keys:
                - gpos_applied: Boolean indicating if GPOs are applied
                - applied_gpo_count: Number of applied GPOs
                - gpresult_available: Boolean indicating if gpresult is available
                - computer_policies: List of applied computer policies
                - user_policies: List of applied user policies
        """
        result = {
            "gpos_applied": False,
            "applied_gpo_count": 0,
            "gpresult_available": True,
            "computer_policies": [],
            "user_policies": []
        }

        try:
            # Run gpresult /h to get detailed GPO information (exports to HTML)
            # For now, use gpresult /scope:user /scope:computer to check if GPOs exist
            gpresult_user = subprocess.run(
                ['gpresult', '/scope:user'],
                capture_output=True,
                text=True,
                timeout=10
            )

            gpresult_computer = subprocess.run(
                ['gpresult', '/scope:computer'],
                capture_output=True,
                text=True,
                timeout=10
            )

            if gpresult_user.returncode == 0 or gpresult_computer.returncode == 0:
                result["gpos_applied"] = True

                # Parse user policies
                if gpresult_user.returncode == 0:
                    user_policies = self._parse_gpresult_output(gpresult_user.stdout)
                    result["user_policies"] = user_policies

                # Parse computer policies
                if gpresult_computer.returncode == 0:
                    computer_policies = self._parse_gpresult_output(gpresult_computer.stdout)
                    result["computer_policies"] = computer_policies

                # Total GPO count
                result["applied_gpo_count"] = len(result["user_policies"]) + len(result["computer_policies"])
        except FileNotFoundError:
            result["gpresult_available"] = False
        except Exception:
            pass

        return result

    def _get_domain_controller(self) -> str:
        """
        Get the primary domain controller name using PowerShell.

        Returns:
            Domain controller name or "Unknown" if not available
        """
        try:
            ps_result = subprocess.run(
                ['powershell', '-Command',
                 '[System.DirectoryServices.ActiveDirectory.Domain]::GetCurrentDomain().FindClosestDomainController().Name'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if ps_result.returncode == 0:
                dc_name = ps_result.stdout.strip()
                if dc_name and dc_name.lower() != 'exception':
                    return dc_name
        except Exception:
            pass

        return "Unknown"

    def _parse_gpresult_output(self, output: str) -> List[str]:
        """
        Parse gpresult command output to extract GPO names.

        Args:
            output: Output from gpresult command

        Returns:
            List of GPO names found in the output
        """
        policies = []
        try:
            for line in output.split('\n'):
                line = line.strip()
                # Look for "Applied Group Policy Objects" section
                if line.startswith('\\') and '\\' in line:
                    # Extract GPO name (typically in \\DOMAIN\CN=...\ format)
                    parts = line.split('\\')
                    if len(parts) > 0:
                        gpo_name = parts[-1] if parts[-1] else parts[-2]
                        if gpo_name and gpo_name not in policies:
                            policies.append(gpo_name)
        except Exception:
            pass

        return policies

    def get_all_enterprise_info(self) -> Dict[str, any]:
        """Get all enterprise information as a comprehensive dictionary"""
        return {
            "Domain": self.get_domain_info(),
            "Computer": self.get_computer_info(),
            "Current User": self.get_current_user(),
            "Network": self.get_network_info(),
            "Azure AD": self.get_azure_ad_info(),
            "Group Policy": self.get_group_policy_info(),
        }
