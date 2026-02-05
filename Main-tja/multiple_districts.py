# -*- coding: utf-8 -*-

"""
This is a skript to generate multiple districts with different configurations.
It should enable the optimationation of different districts in one run.
There is no connection between the districts, they are calculated independently.

"""

# Import the Datahandler class to use the district generator.
from districtgenerator.classes import Datahandler
from pathlib import Path
from districtgenerator.classes import Datahandler

def multiple_districts(configs_dir: Path) -> list[Datahandler]:
    ### This function uses all files ending with .env in the given directory.
    # Safe all the building-inforamtions in different .env.CONFIG.<name> files in the data folder.

    all_data = []

    scenario_files = [f for f in configs_dir.iterdir() if f.is_file() and f.name.startswith(".env")]

    print(f"Found {len(scenario_files)} scenario files in {configs_dir}:")
    for f in scenario_files:
        print(f" - {f.name}")

    for scenario_file in scenario_files:

        # Initialize District for the current scenario.
        data = Datahandler(env_path=scenario_file)

        # Get topology option either node or road based from heat grid data
        topology_option = data.heat_grid_data["topology_option"]

        # Generate a complete district. 
        # Use calcUserProfiles=False to speed up the calculation if user profiles are already calculated
        data.generateDistrictComplete(calcUserProfiles=True, saveUserProfiles=True, topology_option = topology_option)

        all_data.append(data)

    return all_data

  ### ===========================================  Output  =========================================== ###
    # During the run, check the Terminal, it shows the found config files and also indicates which file it is
    # currently computing.
    # After running, check your results folder. You will find the demands for each defined scenario.
    # In the results folder where the main function is stored you will find the model_<scenario_name> files.
    # These files stroe the results of the lp solver for each scenario.

if __name__ == '__main__':
    # This helper code finds the 'data' directory relative to this script's location.
    # Adjust the path if your directory structure is different.
    script_path = Path(__file__).resolve()
    project_root = script_path.parent.parent
    configs_directory_path = project_root / "districtgenerator" / "data"

    results = multiple_districts(configs_directory_path)