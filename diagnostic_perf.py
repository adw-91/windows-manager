"""Performance diagnostic for Windows Manager.

Run this to identify which operations are slow on this machine.
Helps differentiate enterprise vs home machine bottlenecks.
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))


def timed(label, func, *args, **kwargs):
    """Run func and print elapsed time."""
    start = time.perf_counter()
    try:
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        flag = " *** SLOW ***" if elapsed > 2.0 else (" * moderate *" if elapsed > 0.5 else "")
        print(f"  {label}: {elapsed:.3f}s{flag}")
        return result
    except Exception as e:
        elapsed = time.perf_counter() - start
        print(f"  {label}: {elapsed:.3f}s [ERROR: {e}]")
        return None


def main():
    import psutil

    print("=" * 60)
    print("Windows Manager Performance Diagnostic")
    print("=" * 60)
    print(f"CPU cores: {psutil.cpu_count(logical=False)} physical, {psutil.cpu_count()} logical")
    print(f"RAM: {psutil.virtual_memory().total / (1024**3):.1f} GB")
    print(f"Process count: {len(psutil.pids())}")
    print()

    # --- psutil basics ---
    print("[1] psutil basics")
    timed("cpu_percent(interval=None)", psutil.cpu_percent, interval=None)
    timed("cpu_percent(interval=0.1)  <-- current code uses this", psutil.cpu_percent, interval=0.1)
    timed("cpu_times_percent(interval=None)", psutil.cpu_times_percent, interval=None)
    timed("cpu_stats()", psutil.cpu_stats)
    timed("virtual_memory()", psutil.virtual_memory)
    timed("disk_io_counters()", psutil.disk_io_counters)
    timed("net_io_counters()", psutil.net_io_counters)
    timed("disk_partitions()", psutil.disk_partitions)
    timed("sensors_battery()", psutil.sensors_battery)
    print()

    # --- Process enumeration ---
    print("[2] Process enumeration")
    timed("process_iter (all)", lambda: list(psutil.process_iter(['pid', 'name', 'memory_info', 'status'])))
    timed("pids()", psutil.pids)

    # Handle/thread counting - THE LIKELY BOTTLENECK
    print()
    print("[3] Per-process handle/thread counting (the suspected bottleneck)")
    pids = psutil.pids()
    print(f"  Total PIDs: {len(pids)}")

    # Time 10 processes
    start = time.perf_counter()
    count = 0
    for pid in pids[:10]:
        try:
            proc = psutil.Process(pid)
            proc.num_threads()
            count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    elapsed_10 = time.perf_counter() - start
    print(f"  num_threads() x10 processes: {elapsed_10:.3f}s ({elapsed_10/max(count,1)*1000:.1f}ms avg)")

    start = time.perf_counter()
    count = 0
    for pid in pids[:10]:
        try:
            proc = psutil.Process(pid)
            if hasattr(proc, 'num_handles'):
                proc.num_handles()
                count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    elapsed_10h = time.perf_counter() - start
    print(f"  num_handles() x10 processes: {elapsed_10h:.3f}s ({elapsed_10h/max(count,1)*1000:.1f}ms avg)")

    # Extrapolate for 100 processes (what _collect_details does)
    estimated_100 = (elapsed_10 + elapsed_10h) * 10
    print(f"  Estimated for 100 processes (threads+handles): {estimated_100:.1f}s")
    if estimated_100 > 2.0:
        print(f"  *** This exceeds the 2s refresh interval! Worker will never keep up. ***")
    print()

    # --- WMI ---
    print("[4] WMI connection + query (memory sticks)")
    def wmi_test():
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        locator = win32com.client.Dispatch("WbemScripting.SWbemLocator")
        conn = locator.ConnectServer(".", r"root\cimv2")
        results = []
        for obj in conn.ExecQuery("SELECT Capacity FROM Win32_PhysicalMemory"):
            row = {}
            for prop in obj.Properties_:
                row[prop.Name] = prop.Value
            results.append(row)
        pythoncom.CoUninitialize()
        return results
    timed("WMI connect + PhysicalMemory query", wmi_test)
    print()

    # --- Registry (software enumeration) ---
    print("[5] Registry software enumeration")
    def registry_software_test():
        import winreg
        count = 0
        for hive, path in [
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        ]:
            try:
                with winreg.OpenKey(hive, path) as key:
                    idx = 0
                    while True:
                        try:
                            winreg.EnumKey(key, idx)
                            count += 1
                            idx += 1
                        except OSError:
                            break
            except OSError:
                pass
        return count
    count = timed("Registry key enumeration (3 paths)", registry_software_test)
    if count:
        print(f"  Found {count} registry entries to scan")
    print()

    # --- Services ---
    print("[6] Service enumeration")
    def service_enum_test():
        import win32service
        scm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_ENUMERATE_SERVICE)
        try:
            svc_list = win32service.EnumServicesStatusEx(
                scm, win32service.SERVICE_WIN32, win32service.SERVICE_STATE_ALL, None
            )
            # Also time individual config queries (what the app does for each service)
            query_count = 0
            for svc in svc_list[:20]:  # Sample 20
                try:
                    handle = win32service.OpenService(scm, svc["ServiceName"], win32service.SERVICE_QUERY_CONFIG)
                    try:
                        win32service.QueryServiceConfig(handle)
                        query_count += 1
                    finally:
                        win32service.CloseServiceHandle(handle)
                except Exception:
                    pass
            return len(svc_list), query_count
        finally:
            win32service.CloseServiceHandle(scm)

    result = timed("SCM enumerate + 20 config queries", service_enum_test)
    if result:
        total_svcs, queried = result
        print(f"  Total services: {total_svcs}")
        # Extrapolate full config query time
    print()

    # --- psutil.win_service_iter (used in system_tab) ---
    print("[7] psutil.win_service_iter (used in SystemTab)")
    def win_service_iter_test():
        services = list(psutil.win_service_iter())
        running = sum(1 for s in services if s.status() == 'running')
        return len(services), running
    result = timed("win_service_iter + status check", win_service_iter_test)
    if result:
        total, running = result
        print(f"  {running} running / {total} total")
    print()

    # --- Network info ---
    print("[8] Network info")
    timed("net_if_addrs()", psutil.net_if_addrs)
    timed("net_if_stats()", psutil.net_if_stats)
    import socket
    timed("gethostname()", socket.gethostname)
    timed("getfqdn()", socket.getfqdn)
    print()

    # --- Domain lookup ---
    print("[9] Domain/workgroup lookup")
    def domain_test():
        import win32net
        return win32net.NetGetJoinInformation(None)
    timed("NetGetJoinInformation", domain_test)
    print()

    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print("Items marked *** SLOW *** (>2s) are primary bottlenecks.")
    print("Items marked * moderate * (>0.5s) contribute to sluggishness.")
    print()
    print("On enterprise machines, common bottlenecks are:")
    print("  - num_handles() per-process (EDR interception)")
    print("  - WMI queries (management software overhead)")
    print("  - win_service_iter (many services)")
    print("  - Service config queries (hundreds of services)")


if __name__ == "__main__":
    main()
