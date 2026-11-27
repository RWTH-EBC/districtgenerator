"""Locations inside the installed districtgenerator package."""
import os

#: Root folder of the districtgenerator package.
PACKAGE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Folder with all data of the package.
DATA_DIR = os.path.join(PACKAGE_DIR, "data")

#: User inputs: configuration files and scenario files. A project folder (``Datahandler(project_path=...)``)
#: has the same subfolders.
INPUTS_DIR = os.path.join(DATA_DIR, "inputs")

#: Configuration files (``.env.CONFIG.*``) that override the defaults of ``config/settings.py``.
CONFIGS_DIR = os.path.join(INPUTS_DIR, "configs")

#: Scenario files (.csv) with the buildings of a district.
SCENARIOS_DIR = os.path.join(INPUTS_DIR, "scenarios")

#: Reference data that is read by the package and usually not changed, such as weather, site and device data.
REFERENCE_DIR = os.path.join(DATA_DIR, "reference")

#: Default folder for all results, such as profiles, plots, KPIs and the certificate.
RESULTS_DIR = os.path.join(PACKAGE_DIR, "results")

#: Subfolder names inside a project folder.
PROJECT_CONFIGS = "configs"
PROJECT_SCENARIOS = "scenarios"
PROJECT_RESULTS = "results"
