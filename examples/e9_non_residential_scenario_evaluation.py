# -*- coding: utf-8 -*-

"""
This is the ninth example, which demonstrates an examplatory scenario evaliation containing both residential and 
non-residential buildings, as well as mixed-use buildings.
"""

# Import classes of the districtgenerator to be able to use the district generator.
from districtgenerator.classes import *

def example9_non_residential_scenario_evaluation():

    # Initialize District for the chosen scenario.
    # Runs with the defaults from config.py. To change parameters, create your own file in districtgenerator/data
    # (see e6 and .env.CONFIG.EXAMPLE) and load it with Datahandler(env_path=".env.CONFIG.MYPROJECT").
    data = Datahandler(scenario_name = "example_non_residential")

    # We directly generate a complete district. For further information refer to example 7 and 8.
    data.generateDistrictComplete(calcUserProfiles=True, saveUserProfiles=True)

    # Calculation of the devices' optimal operation
    data.optimizationClusters()

    # Calculation of the key performance indicators using the devices' operation profiles of clustered time periods
    data.calculateKPIs()
    # Create a certificate (PDF) which summarizes the district parameters and calculated KPIs
    data.KPIs.create_certificate(data=data, result_path=data.resultPath)

    print("Congratulations! You calculated an optimized device operation for the selected neighborhood!")
    return data


if __name__ == '__main__':
    data = example9_non_residential_scenario_evaluation()


