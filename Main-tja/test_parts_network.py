from districtgenerator.classes import Network
from pathlib import Path

if __name__ == '__main__':
    # This helper code finds the 'data' directory relative to this script's location.
    # Adjust the path if your directory structure is different.
    script_path = Path(__file__).resolve()
    project_root = script_path.parent.parent
    configs_directory_path = project_root / "districtgenerator" / "data"

    network = Network()

    network.initializeDistrictsWithDecentralDevs(configs_dir=configs_directory_path, calcUserProfiles=False, saveUserProfiles=False)
    network.optimize_network(saveGenerationProfiles= True)

    #print(network.interconnected_districts)
    for district in network.interconnected_districts.values():
        # Print capacities of central devices
        if "capacities" in district.centralDevices:
            capacities = district.centralDevices["capacities"]
            print(f"\nCapacities of the central devices in the energy hub of: {district.scenario_name}")
            for device, details in capacities.items():
                if isinstance(details, dict) and "cap" in details and details["cap"] > 0:
                    print(f"  {device}: {details['cap']}")
        else:
            print(f"No capacities defined in energy hub of: {district.scenario_name}")  

