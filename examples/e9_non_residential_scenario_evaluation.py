# -*- coding: utf-8 -*-

"""
This is the ninth example, which demonstrates an examplatory scenario evaliation containing both residential and 
non-residential buildings, as well as mixed-use buildings.
"""

# Import classes of the districtgenerator to be able to use the district generator.
from districtgenerator.classes import *

def example9_non_residential_scenario_evaluation():

    # Initialize District for the chosen scenario.
    # To use specific parameters, you can provide your own .env.CONFIG file in the data/env folder (see e6)
    # Refer to it like this: Datahandler(env_path=".env.CONFIG.EXAMPLE") and put it in ./data
    data = Datahandler(scenario_name = "example_non_residential", env_path=".env.CONFIG.EXAMPLE")

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


