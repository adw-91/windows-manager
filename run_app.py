"""Application launcher - Run this file to start Windows Manager"""

import sys
import os

# Detect packaged executable: PyInstaller sets sys.frozen, Nuitka sets __compiled__
_is_frozen = getattr(sys, 'frozen', False) or "__compiled__" in dir()

if _is_frozen:
    import tempfile

    # Redirect win32com gen_py cache to a writable temp directory.
    # In frozen/compiled builds the bundle is read-only, so gencache can't write there.
    import win32com
    _gen_py = os.path.join(tempfile.gettempdir(), 'winmanager_gen_py')
    os.makedirs(_gen_py, exist_ok=True)
    win32com.__gen_path__ = _gen_py

    # Send logging output to a file so errors are visible when console=False.
    import logging
    _log_path = os.path.join(tempfile.gettempdir(), 'winmanager.log')
    logging.basicConfig(
        filename=_log_path,
        level=logging.WARNING,
        format='%(asctime)s %(name)s %(levelname)s: %(message)s',
    )

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.main import main

if __name__ == "__main__":
    main()
