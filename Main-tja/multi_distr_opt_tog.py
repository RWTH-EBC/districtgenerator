# -*- coding: utf-8 -*-

"""
This is a skript to generate multiple districts with different configurations.
It should enable the optimationation of different districts in one run.
The skript should enable one optimatization for the interconnected districts.
"""

# Import the Datahandler class to use the district generator.
from districtgenerator.classes import Datahandler
from pathlib import Path
from districtgenerator.classes import Datahandler
from pprint import pprint
from districtgenerator.data_handling.config import GlobalConfig, load_global_config, LocationConfig, TimeConfig, DesignBuildingConfig, EcoConfig, PhysicsConfig, EHDOConfig, GurobiConfig, HeatGridConfig, CalendarConfig

def multi_distr_dem(configs_dir: Path) -> list[Datahandler]:
    ### This function caluclates the demands of multiple districts. It uses all files ending with .env in the given directory.
    # Yqu should safe all the building-inforamtions in different .env.CONFIG.<name> files in the data folder to use this function.

    all_data = []

    scenario_files = [f for f in configs_dir.iterdir() if f.is_file() and f.name.startswith(".env")]

    print(f"Found {len(scenario_files)} scenario files in {configs_dir}:")
    for f in scenario_files:
        print(f" - {f.name}")

    for scenario_file in scenario_files:

        # Initialize District for the current scenario.
        data = Datahandler(env_path=scenario_file)
        model_param_eh = data.params_ehdo_model
        print(f"\nOptim_dimension of: {data.scenario_name} is {model_param_eh['optim_dimension']}")

        # Generate Environment for the District
        data.generateEnvironment()

        # Initialize Buildings to the District
        data.initializeBuildings()

        # Generate more detailed Building models
        data.generateBuildings()

        # Now we generate building specific demand profiles with the adjusted assumptions
        # Use calcUserProfiles=False to speed up the calculation if user profiles are already calculated
        data.generateDemands(calcUserProfiles=False, saveUserProfiles=False)

        all_data.append(data)
        
    return all_data

  ### ===========================================  Output  =========================================== ###
    # During the run, check the Terminal, it shows the found config files and also indicates which file it is
    # currently computing.
    # After running, check your results folder. You will find the demands for each defined scenario.


def multi_distr_data_safe(configs_directory_path): 
# Multi-district-data-safe function
# This functions optimizes the decentral and central devices for all districts that are NOT interconnected (optim_dimension=0).
# For the districts that are interconnected (optim_dimension=1), it saves the data in the list all_data_connect for further processing.
    all_data = multi_distr_dem(configs_directory_path)
    all_data_connect = []

    for i, data in enumerate(all_data):
        print(f"Scenario Name: {data.scenario_name}")
        print(f"Optim_dimension: {data.params_ehdo_model['optim_dimension']}")
        # If optim_dimension is 0, do district optimization
        if data.params_ehdo_model['optim_dimension'] == 0:
            print("This scenario is set for district optimization.")
            data.designDevicesComplete(saveGenerationProfiles=True)
            print(f"Congratulations! You generated your energy central for: {data.scenario_name}")
        # If optim_dimension is 1 save the data for interconnected districts in all_data_connect
        elif data.params_ehdo_model['optim_dimension'] == 1:
            print("This scenario is set for interconnected district optimization.")
            all_data_connect.append(data)
        else:
            print("Unknown optim_dimension value.")

    return all_data_connect  

# TODO: Add the central device optimization for interconnected districts.

def optimize_interconnected_districts(configs_directory_path):
    # This function should optimize the central devices for interconnected districts.
    # Currently, it is a placeholder and needs to be implemented.
    print("Optimizing interconnected districts is not yet implemented.")
    all_data_connect = multi_distr_data_safe(configs_directory_path)

    # Choose one of the datahandler instances to call the designDevicesComplete method
    datahandler_instance = all_data_connect[0]
    
    # Call designDevicesComplete for interconnected districts
    datahandler_instance.designDevicesComplete(
        saveGenerationProfiles=True,
        all_data_connect=all_data_connect
    )

    # for i, data in enumerate(all_data_connect):
    #     print(f"Scenario Name: {data.scenario_name}")
    #     print(f"Site Data: {data.site}")    

    return 

if __name__ == '__main__':
    # This helper code finds the 'data' directory relative to this script's location.
    # Adjust the path if your directory structure is different.
    script_path = Path(__file__).resolve()
    project_root = script_path.parent.parent
    configs_directory_path = project_root / "districtgenerator" / "data"

    results = optimize_interconnected_districts(configs_directory_path)