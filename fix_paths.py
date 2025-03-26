import sys, os
if getattr(sys, "frozen", False):
    os.environ["QT_MAC_WANTS_LAYER"] = "1"
    os.environ["RESOURCES_DIR"] = sys._MEIPASS
