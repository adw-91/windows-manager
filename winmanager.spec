# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Windows Manager."""

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

# Let the built-in hook handle pyqtgraph — it has many internal imports
pyqtgraph_hidden = collect_submodules('pyqtgraph')

# Filter out examples and opengl (we don't use them, and opengl needs PyOpenGL)
pyqtgraph_hidden = [
    m for m in pyqtgraph_hidden
    if not m.startswith(('pyqtgraph.examples', 'pyqtgraph.opengl'))
]

a = Analysis(
    ['run_app.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        # pywin32 core
        'pythoncom',
        'pywintypes',
        'win32com',
        'win32com.client',
        'win32com.client.gencache',
        'win32com.shell',
        'win32service',
        'win32net',
        'win32api',
        'win32security',
        'win32process',
        'win32timezone',

        # psutil backends
        'psutil',
        'psutil._pswindows',

        # numpy (pyqtgraph dependency)
        'numpy',
    ] + pyqtgraph_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Unused Qt modules — trim bundle size
        'PySide6.QtNetwork',
        'PySide6.QtQml',
        'PySide6.QtQuick',
        'PySide6.QtSvg',
        'PySide6.QtXml',
        'PySide6.QtTest',
        'PySide6.QtMultimedia',
        'PySide6.QtBluetooth',
        'PySide6.QtDesigner',
        'PySide6.QtHelp',
        'PySide6.QtSql',
        'PySide6.QtWebEngine',
        'PySide6.QtWebEngineWidgets',
        'PySide6.Qt3DCore',
        'PySide6.Qt3DRender',
        'PySide6.Qt3DInput',
        'PySide6.QtCharts',
        'PySide6.QtDataVisualization',
        # Unused pyqtgraph subpackages
        'pyqtgraph.opengl',
        'pyqtgraph.examples',
        # Unused stdlib/test
        'tkinter',
        'unittest',
        'test',
        'pytest',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='WinManager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='WinManager',
)
