"""Locations inside the installed districtgenerator package."""
import os

#: Root folder of the districtgenerator package.
PACKAGE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Folder with all input data, such as weather, scenarios and device data.
DATA_DIR = os.path.join(PACKAGE_DIR, "data")
