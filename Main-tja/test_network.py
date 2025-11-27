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
    for district in network.interconnected_districts:
        print(f"District: {district.scenario_name}, CentralDevices: {district.centralDevices}")
        net_heating_demand = district.heat_grid_data.get("net_heating_demand", None)
        print(f"Net heating demand: {net_heating_demand} kW")