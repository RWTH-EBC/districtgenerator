# -*- coding: utf-8 -*-

from districtgenerator.classes import Network
from pathlib import Path

if __name__ == '__main__':
    # This helper code finds the 'data' directory relative to this script's location.
    # Adjust the path if your directory structure is different.
    script_path = Path(__file__).resolve()
    project_root = script_path.parent.parent
    configs_directory_path = project_root / "districtgenerator" / "data"

    network = Network()

    network.initializeDistricts(configs_dir=configs_directory_path, calcUserProfiles=False, saveUserProfiles=False)
    network.optimize_network()


    #print(network.interconnected_districts)
    for district in network.interconnected_districts:
        # Print capacities of central devices
        if "capacities" in district.centralDevices:
            capacities = district.centralDevices["capacities"]
            print(f"\nCapacities of the central devices in the energy hub of: {district.scenario_name}")
            for device, details in capacities.items():
                if isinstance(details, dict) and "cap" in details and details["cap"] > 0:
                    print(f"  {device}: {details['cap']}")
        else:
            print(f"No capacities defined in energy hub of: {district.scenario_name}")  
        #print(f"District: {district.scenario_name}, CentralDevices: {district.centralDevices}")

        # Print parameters form heating_network
        net_heating_demand = district.heat_grid_data.get("net_heating_demand", None)
        print(f"Net heating demand: {net_heating_demand} kW")

    # Print parameters form load params
    # for district in network.interconnected_districts:
    #     params = district.centralDevices.get("params", None)
    #     devs = district.centralDevices.get("devs", None)
    #     dem = district.centralDevices.get("dem", None)
    #     result_dict = district.centralDevices.get("result_dict", None)

    #     print(f"District: {district.scenario_name}")
    #     # print(f"  Params: {params}")
    #     print(f"  Devices: {devs}")
    #     # print(f"  Demands: {dem}")
    #     # print(f"  Result Dict: {result_dict}")    