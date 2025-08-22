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

# Import the Datahandler class and the os module for file path operations.
import os
from districtgenerator.classes import Datahandler

def example9_multiple_configs():
    ### To run this example, you will need to set up a directory with configuration files.

    # 1. Go to the folder 'data'.
    #
    # 2. Inside the 'data' folder, place / use your configuration files. For this
    #    example, you could just reuse both configs '.env.CONFIG.EXAMPLE' and '.env.CONFIG.FREIBURG'
    #    or create another one, e.g., '.env.CONFIG.GARMISCH'.
    #
    # The script will find all files in the 'scenarios' folder that start with
    # '.env' and process them one by one.
    #
    # 3. Make sure the configuration files are named correctly, starting with '.env'.
    #
    # You can also place them elsewhere, but you will need to adjust the
    # 'scenarios_path' variable below to point to the correct directory.

    # Define the path to the folder containing your scenario configuration files.
    scenarios_path = "districtgenerator/data"
    # Find all scenario files in the target folder that start with ".env".
    # This assumes the scenario files are named like ".env.CONFIG.FREIBURG".
    scenario_files = [os.path.join(scenarios_path, f) for f in os.listdir(scenarios_path) if f.startswith(".env")]
    # kann man das relativ machen?
    # Loop through each scenario file found in the directory.
    for scenario_file in scenario_files:

        # Initialize District for the current scenario.
        # The 'env_path' points to the configuration file for this specific iteration.
        # The 'scenario_name' ensures that results are saved in a unique directory.
        data = Datahandler(env_path=scenario_file)

        # Generate Environment for the District
        data.generateEnvironment()

        # Initialize Buildings to the District
        data.initializeBuildings()

        # Generate more detailed Building models
        data.generateBuildings()

        # Generate building-specific demand profiles with the adjusted assumptions
        data.generateDemands(calcUserProfiles=True, saveUserProfiles=True)

    ### ===========================================  Output  =========================================== ###
    # After running, check your results folder. You will find subdirectories named
    # after each scenario (e.g., 'FREIBURG', 'GARMISCH'), each containing the
    # complete set of output files for that specific configuration.

    return data


if __name__ == '__main__':
    # The 'results' variable will be a list containing the final 'data' object
    # from each scenario run.
    results = example9_multiple_configs()