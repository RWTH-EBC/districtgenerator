from districtgenerator.classes import Network, KPIs
from pathlib import Path
from districtgenerator.functions.plot_results import plot_device_capacities, plot_grid_flows
import os

if __name__ == '__main__':
    # This helper code finds the 'data' directory relative to this script's location.
    # Adjust the path if your directory structure is different.
    script_path = Path(__file__).resolve()
    project_root = script_path.parent.parent
    configs_directory_path = project_root / "districtgenerator" / "data"

    network = Network()

    network.initializeDistrictsWithDecentralDevs(
        configs_dir=configs_directory_path, 
        calcUserProfiles=False, 
        saveUserProfiles=True)
    
    result_dictCon=network.optimize_network(saveGenerationProfiles= True)

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


    # Folder to save model and results
    result_dir = "optimization_results"

    # if not os.path.exists(result_dir):
    #     os.makedirs(result_dir)
    # plot_grid_flows(result_dictCon=result_dictCon, y=0, result_dir=result_dir, show=True)

    # Plot device capacities for each district

    plot_device_capacities(result_dictCon=result_dictCon, result_dir=result_dir, show=True)


    # Can be used if I update opti_central for the network optimization
    # for district in network.interconnected_districts.values():
    #     district.optimizationClusters()
    #     district.calculateKPIs()  
    #     print(f"\n{district.scenario_name}")
    #     print("  Grid demand (kWh/a):", district.KPIs.W_dem_GCP_year)
    #     print("  Grid injection (kWh/a):", district.KPIs.W_inj_GCP_year)
    #     print("  Gas (kWh/a):", district.KPIs.gas_year)

