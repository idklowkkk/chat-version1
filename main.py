import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.ui.app import CespoApp

if __name__ == "__main__":
    CespoApp().run()
