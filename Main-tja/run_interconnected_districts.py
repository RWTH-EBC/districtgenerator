from districtgenerator.classes import Network
from pathlib import Path
import os


"""
This is a script to generate multiple districts with different configurations.
It should enable the optimization of different districts in one run.
The parameter OPTIM_DIMENSION defines if the districts are interconnected or calculated independently.

"""

if __name__ == '__main__':
    # This helper code finds the 'data' directory relative to this script's location.
    # Adjust the path if your directory structure is different.
    script_path = Path(__file__).resolve()
    project_root = script_path.parent.parent
    configs_directory_path = project_root / "districtgenerator" / "data"

    # Initialize the network object
    network = Network()

    # Initialize the districts with the decentralized devices and generate the user profiles if needed.
    network.initializeDistrictsWithDecentralDevs(
        configs_dir=configs_directory_path, 
        calcUserProfiles=False, 
        saveUserProfiles=True)
    
    # Optimize the network and save the generation profiles
    result_dictCon=network.optimize_network(saveGenerationProfiles= True)

    # Print the capacities of the central devices in the energy hub for each district
    for district in network.interconnected_districts.values():
        # Print capacities of central devices
        if "capacities" in district.centralDevices:
            capacities = district.centralDevices["capacities"]
            print(f"\nCapacities of the central devices of in the energy hub of: {district.scenario_name}")
            for device, details in capacities.items():
                if isinstance(details, dict) and "cap" in details and details["cap"] > 0:
                    print(f"  {device}: {details['cap']}")
        else:  
            print(f"No capacities defined in energy hub of: {district.scenario_name}")


    # Folder to save model and results
    result_dir = "optimization_results"



