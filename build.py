"""Build WinManager with Nuitka."""

import shutil
import subprocess
import sys
from pathlib import Path

NUITKA_CMD = [
    sys.executable, "-m", "nuitka",

    # --- Mode ---
    "--standalone",
    "--assume-yes-for-downloads",

    # --- Output ---
    "--output-dir=dist",
    "--output-filename=WinManager.exe",

    # --- Windows GUI ---
    "--windows-console-mode=disable",

    # --- Plugins ---
    "--enable-plugin=pyside6",

    # --- Explicit includes (pywin32 COM, psutil backends, pyqtgraph) ---
    "--include-module=pythoncom",
    "--include-module=pywintypes",
    "--include-module=win32com",
    "--include-module=win32com.client",
    "--include-module=win32com.client.gencache",
    "--include-module=win32com.shell",
    "--include-module=win32service",
    "--include-module=win32net",
    "--include-module=win32api",
    "--include-module=win32security",
    "--include-module=win32process",
    "--include-module=win32timezone",
    "--include-module=psutil",
    "--include-module=psutil._pswindows",
    "--include-package=pyqtgraph",
    "--include-module=numpy",
    "--include-module=PySide6.QtOpenGL",
    "--include-module=PySide6.QtOpenGLWidgets",

    # --- Exclude unused Qt modules (size optimization) ---
    "--nofollow-import-to=PySide6.QtNetwork",
    "--nofollow-import-to=PySide6.QtQml",
    "--nofollow-import-to=PySide6.QtQuick",
    "--nofollow-import-to=PySide6.QtSvg",
    "--nofollow-import-to=PySide6.QtXml",
    "--nofollow-import-to=PySide6.QtTest",
    "--nofollow-import-to=PySide6.QtMultimedia",
    "--nofollow-import-to=PySide6.QtBluetooth",
    "--nofollow-import-to=PySide6.QtDesigner",
    "--nofollow-import-to=PySide6.QtHelp",
    "--nofollow-import-to=PySide6.QtSql",
    "--nofollow-import-to=PySide6.QtWebEngine",
    "--nofollow-import-to=PySide6.QtWebEngineWidgets",
    "--nofollow-import-to=PySide6.Qt3DCore",
    "--nofollow-import-to=PySide6.Qt3DRender",
    "--nofollow-import-to=PySide6.Qt3DInput",
    "--nofollow-import-to=PySide6.QtCharts",
    "--nofollow-import-to=PySide6.QtDataVisualization",

    # --- Exclude unused stdlib / pyqtgraph subpackages ---
    "--nofollow-import-to=tkinter",
    "--nofollow-import-to=unittest",
    "--nofollow-import-to=test",
    "--nofollow-import-to=pytest",
    "--nofollow-import-to=pyqtgraph.opengl",
    "--nofollow-import-to=pyqtgraph.examples",

    # --- Entry point ---
    "run_app.py",
]


def main():
    print("Building WinManager with Nuitka...")
    print(f"Command:\n  {' '.join(NUITKA_CMD)}\n")
    result = subprocess.run(NUITKA_CMD)

    if result.returncode != 0:
        print(f"\nBuild failed with exit code {result.returncode}")
        sys.exit(result.returncode)

    # Rename output from run_app.dist to WinManager for drop-in compatibility
    src_dir = Path("dist") / "run_app.dist"
    dst_dir = Path("dist") / "WinManager"
    if dst_dir.exists():
        shutil.rmtree(dst_dir)
    if src_dir.exists():
        src_dir.rename(dst_dir)
        print(f"\nBuild successful! Output in {dst_dir}\\")
    else:
        print("\nBuild successful! Output in dist\\")


if __name__ == "__main__":
    main()
