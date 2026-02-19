# -*- coding: utf-8 -*-

"""
This is the ninth example, which explains how to automatically run the generator
for multiple configuration files in a sequence.

This approach can be used for comparing different scenarios, as each configuration
file represents a unique set of assumptions. The script will loop through all
valid config files in a specified directory and generate a complete set of
results for each one. You can reuse these configuration files for future runs
or share them with others to ensure consistent results across different setups.

If you run the examples with Python console, you can see the output files being
generated for each scenario. To do this right-hand click the example.py file
(e9_multiple_configs.py). Then choose 'Modify Run Configuration' and tick
'Run with Python Console'.
"""

from pathlib import Path
from districtgenerator.classes import Datahandler

def example9_multiple_configs(configs_dir: Path) -> list[Datahandler]:
    ### To run this example, you will need to set up a directory with configuration files.

    # 1. Go to the folder 'districtgenerator/data' (default location).

    # 2. Inside the 'data' folder, place / use your configuration files. For this
    #    example, you could reuse both configs '.env.CONFIG.EXAMPLE' and '.env.CONFIG.FREIBURG'
    #    or create another one, e.g., '.env.CONFIG.SCENARIO1'.

    # The script will find all files in the 'data' folder that start with
    # '.env' and process them one by one.

    # IMPORTANT: Make sure the configuration files are named correctly, starting with '.env'.

    # You can also place them elsewhere, but you will need to adjust the
    # 'configs_directory_path' variable below to point to the correct directory.

    all_data = []

    scenario_files = [f for f in configs_dir.iterdir() if f.is_file() and f.name.startswith(".env")]

    print(f"Found {len(scenario_files)} scenario files in {configs_dir}:")
    for f in scenario_files:
        print(f" - {f.name}")

    for scenario_file in scenario_files:

        # Initialize District for the current scenario.
        data = Datahandler(env_path=scenario_file)

        # Generate Environment for the District
        data.generateEnvironment()

        # Initialize Buildings to the District
        data.initializeBuildings()

        # Generate more detailed Building models
        data.generateBuildings()

        # Generate building-specific demand profiles with the adjusted assumptions
        data.generateDemands(calcUserProfiles=True, saveUserProfiles=True)

        all_data.append(data)

    ### ===========================================  Output  =========================================== ###
    # During the run, check the Terminal, it shows the found config files and also indicates which file it is
    # currently computing.
    # After running, check your results folder. You will find the demands for each defined scenario.

    return all_data


if __name__ == '__main__':
    # This helper code finds the 'data' directory relative to this script's location.
    # Adjust the path if your directory structure is different.
    script_path = Path(__file__).resolve()
    project_root = script_path.parent.parent
    configs_directory_path = project_root / "districtgenerator" / "data"

    results = example9_multiple_configs(configs_directory_path)