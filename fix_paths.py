# Required for PyInstaller macOS builds
import sys
import os
from PyQt6 import QtCore

def fix_paths():
    if hasattr(sys, '_MEIPASS'):
        os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = os.path.join(
            sys._MEIPASS, 'PyQt6', 'Qt6', 'plugins'
        )

fix_paths()
