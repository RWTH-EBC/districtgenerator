# -*- coding: utf-8 -*-

"""
This is the example to optimize the heating network diameter.
"""

# Import classes of the districtgenerator to be able to use the district generator.
from districtgenerator.classes import *

def example9_network_diameter_optimize():
    # Initialize District
    # Enter the name of the scenario you wish to use in the folder: data/scenarios
    # The scenario can be first generated with e0_generate_scenario.py
    data = Datahandler(scenario_name="district_A_buildings_10")

    # Generate Environment for the District
    data.generateEnvironment()

    # Initialize Buildings to the District
    data.initializeBuildings()

    # Generate a more detailed Building
    data.generateBuildings()

    # Now we generate building specific demand profiles with the adjusted assumptions
    data.generateDemands(calcUserProfiles=False, saveUserProfiles=False)
    data.designDecentralDevices(saveGenerationProfiles=True)
    data.clusterProfiles(centralEnergySupply=False)

    # data.generateDistrictComplete(calcUserProfiles=False, saveUserProfiles=False)

    # Then we can initialize the network topology and optimize of the diameter
    data.generateNetwork("road", calcUserProfiles=True)
    # If sliding_temperature=True, the supply and return temperatures are adjusted according to the air temperature;
    # if False, constant supply and return water temperatures are employed.
    data.optimizationDiameter(sliding_temperature=True)

    ### =====================================  Output  ===================================== ###
    # The solution of the Gurobi optimizer (diameters, pump capacity, heat loss and so on)
    # plot 5 Pipeline Maps with id, diameters, Maximum velocity (m/s), Maximum pressure drop (Pa/m) and Energy_density (MWh/m)

if __name__ == '__main__':
    data = example9_network_diameter_optimize()


