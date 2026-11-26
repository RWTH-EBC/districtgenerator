# -*- coding: utf-8 -*-

"""
This is the eleventh example to work with an own project folder outside the districtgenerator.

There are two ways to provide own configuration and scenario files:

1. Working directly in the repository (e1 to e10):
   Put your files into districtgenerator/data/inputs/configs and districtgenerator/data/inputs/scenarios.
   Own files there are ignored by git, only the shipped examples are tracked.
   To adapt an example, copy it under a new name instead of editing it.

2. Working with an own project folder (this example), e.g. when the districtgenerator is installed with pip:
   Create a folder for the districtgenerator anywhere in your project and pass it to the Datahandler as project_path.
   It does not have to be the top level of your project, a subfolder keeps it apart from your other data:

       your_project/
         data/
           ...                        (other data of your project)
           districtgenerator/         <- project_path
             configs/     .env.CONFIG.MYPROJECT
             scenarios/   my_district.csv
             results/     (created automatically)

   The subfolders correspond to these folders in the repository:

       districtgenerator/data/inputs/configs     ->  <project_path>/configs
       districtgenerator/data/inputs/scenarios   ->  <project_path>/scenarios
       districtgenerator/results                 ->  <project_path>/results

   A relative env_path is searched first in <project_path>/configs and then in data/inputs/configs, so the shipped
   configs (e.g. .env.CONFIG.FREIBURG) can still be used. Configuration files directly in <project_path> are not
   found by name.
"""

import os
import shutil

# Import classes of the districtgenerator to be able to use the district generator.
from districtgenerator import Datahandler
from districtgenerator.utilities.paths import CONFIGS_DIR, SCENARIOS_DIR


def create_project(project_path):
    """
    Create a project folder and copy an example scenario and the configuration template into it.
    Existing files are not overwritten, so own changes in the project folder are kept.
    """
    configs_path = os.path.join(project_path, "configs")
    scenarios_path = os.path.join(project_path, "scenarios")
    os.makedirs(configs_path, exist_ok=True)
    os.makedirs(scenarios_path, exist_ok=True)

    # The scenario file describes the buildings of the district (see example_decentral.csv and info.txt)
    scenario_file = os.path.join(scenarios_path, "my_district.csv")
    if not os.path.isfile(scenario_file):
        shutil.copyfile(os.path.join(SCENARIOS_DIR, "example_decentral.csv"), scenario_file)

    # The configuration file overrides the defaults of config/settings.py. The template lists all parameters,
    # uncomment and change the ones you need.
    config_file = os.path.join(configs_path, ".env.CONFIG.MYPROJECT")
    if not os.path.isfile(config_file):
        shutil.copyfile(os.path.join(CONFIGS_DIR, ".env.CONFIG.EXAMPLE"), config_file)


def example11_own_project(project_path=None):

    # By default the project folder is created as data/districtgenerator in the current working directory,
    # i.e. the top level of your project when you run the script from there
    if project_path is None:
        project_path = os.path.join(os.getcwd(), "data", "districtgenerator")
    create_project(project_path)

    # Initialize District with the project folder.
    # Without project_path the Datahandler would use data/inputs/scenarios and data/inputs/configs of the package.
    data = Datahandler(project_path=project_path, scenario_name="my_district", env_path=".env.CONFIG.MYPROJECT")

    # Generate the district and the demand profiles (see e2 to e5)
    data.generateEnvironment()
    data.initializeBuildings()
    data.generateBuildings()
    data.generateDemands(calcUserProfiles=True, saveUserProfiles=True)

    print(f"Scenario read from: {data.scenario_file_path}")
    print(f"Results saved in:   {data.resultPath}")
    return data


if __name__ == '__main__':
    data = example11_own_project()
