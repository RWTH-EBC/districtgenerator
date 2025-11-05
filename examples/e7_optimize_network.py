# -*- coding: utf-8 -*-

"""
This is the example to optimize the heating network.
"""

# Import classes of the districtgenerator to be able to use the district generator.
from districtgenerator.classes import *

def example7_optimize_heatingnetwork():
    # Initialize District
    # Enter the name of the scenario you wish to use in the folder: data/scenarios
    # The scenario can be first generated with e0_generate_scenario.py
    data = Datahandler(scenario_name="district_F_buildings_30")

    # --- Check if building positions are available and valid ---
    missing_positions = (
            "position" not in data.scenario.columns
            or data.scenario["position"].isnull().any()
            or any(
        not isinstance(p, tuple) or len(p) != 2 or not all(isinstance(x, (int, float)) for x in p)
        for p in data.scenario["position"]))
    if missing_positions:
        raise FileNotFoundError(
            "The district heating network cannot be optimized because no building positions are defined.\n"
            "The scenario CSV contains invalid or missing coordinates in the 'position' column.\n"
            "Please add the scenario geometry first."
        )

    # Generate Environment for the District
    data.generateEnvironment()

    # Initialize Buildings to the District
    data.initializeBuildings()

    # Generate a more detailed Building
    data.generateBuildings()

    # Now we generate building specific demand profiles with the adjusted assumptions
    data.generateDemands(calcUserProfiles=False, saveUserProfiles=False)

    # --- Design decentral devices and pre-cluster data ---
    data.designDecentralDevices(saveGenerationProfiles=True)
    data.clusterProfiles(centralEnergySupply=False)

    # --- Check if the geometry JSON exists ---
    if "district_parameters" not in data.site:
        print(
            "The district geometry JSON ('<scenario_name>.json') was not found.\n"
            "The district layout (roads) is not defined, only building positions are available.\n"
            "Switching to topology_option='node' instead of 'road'."
        )
        topology_option = "node"
    else:
        topology_option = "road"

    data.generateNetwork(topology_option = topology_option)
    # If sliding_temperature=True, the supply and return temperatures are adjusted according to the air temperature;
    # if False, constant supply and return water temperatures are employed.
    data.optimization_heatingnetwork(sliding_temperature=True)

    ### =====================================  Output  ===================================== ###
    # The solution of the Gurobi optimizer (diameters, pump capacity, heat loss and so on)
    # plot 5 Pipeline Maps with id, diameters, Maximum velocity (m/s), Maximum pressure drop (Pa/m) and Energy_density (MWh/m)

if __name__ == '__main__':
    data = example7_optimize_heatingnetwork()


