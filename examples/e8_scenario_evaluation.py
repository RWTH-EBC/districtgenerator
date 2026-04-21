# -*- coding: utf-8 -*-

"""
We reached the final step, to generate our first district: Generate demand profiles for our buildings.
"""

# Import classes of the districtgenerator to be able to use the district generator.
from districtgenerator.classes import *
import warnings



def example8_scenario_evaluation():
    warnings.filterwarnings("ignore", category=FutureWarning)

    # Initialize District
    data = Datahandler(scenario_name = "district_F_buildings_20", env_path=".env.CONFIG.EXAMPLE")

    # We directly generate a complete district.
    # This includes the use of the EHDO tool to obtain an optimized energy central for neighborhoods.
    # EHDO is a tool for planning and designing complex energy systems.
    # Its key feature is the coupling of different sectors (e.g., electricity, heating, cooling).
    # In the early planning phases of energy supply concepts for neighborhoods,
    # the tool provides an initial assessment of the optimal system configuration, sizing,
    # and economic efficiency.
    # As input, EHDO requires data on energy demands and location (weather),
    # which are provided directly from the output of the district generator.
    # Additional information about the technologies to be considered for the dimensioning
    # of the energy central and the economic parameters are read from additional
    # .csv and .json data sources.

    topology_option = data.heat_grid_data["topology_option"]
    data.generateEnvironment()

    # choose between "Papierindustrie", "Baustoff", "Rechenzentrum" and "Kläranlage"
    data.generate_waste_heat_source(waste_heat_source="Baustoff", distance=100)

    data.generateDistrictComplete(calcUserProfiles=False, saveUserProfiles=True, topology_option = topology_option)

    # Calculation of the devices' optimal operation
    data.optimizationClusters()

    # Calculation of the key performance indicators using the devices' operation profiles of clustered time periods
    data.calculateKPIs()

    # Create a certificate (PDF) which summarizes the district parameters and calculated KPIs
    #data.KPIs.create_certificate(data=data, result_path=data.resultPath)

    print("Congratulations! You calculated an optimized device operation for the selected neighborhood!")
    return data



if __name__ == '__main__':
    data = example8_scenario_evaluation()





