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

    # Generate Environment for the District
    data.generateEnvironment()

    # Initialize Buildings to the District
    data.initializeBuildings()

    # Generate a more detailed Building
    data.generateBuildings()

    # Now we generate building specific demand profiles with the adjusted assumptions
    data.generateDemands(calcUserProfiles=False, saveUserProfiles=False)

    # Then we can initialize the network topology and optimize it
    data.generateNetwork(topology_option = "road")

    data.designDecentralDevices(saveGenerationProfiles=True)
    data.clusterProfiles(centralEnergySupply=False)
    # If sliding_temperature=True, the supply and return temperatures are adjusted according to the air temperature;
    # if False, constant supply and return water temperatures are employed.
    data.optimization_heatingnetwork(sliding_temperature=True)

    ### =====================================  Output  ===================================== ###
    # The solution of the Gurobi optimizer (diameters, pump capacity, heat loss and so on)
    # plot 5 Pipeline Maps with id, diameters, Maximum velocity (m/s), Maximum pressure drop (Pa/m) and Energy_density (MWh/m)

if __name__ == '__main__':
    data = example7_optimize_heatingnetwork()


