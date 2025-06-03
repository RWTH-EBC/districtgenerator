# -*- coding: utf-8 -*-

"""
We reached the final step, to generate our first district: Generate demand profiles for our buildings.
"""

# Import classes of the districtgenerator to be able to use the district generator.
from districtgenerator.classes import *



def example8_scenario_evaluation():

    # Initialize District
#    data = Datahandler(scenario_name = "example")
    data = Datahandler(scenario_name = "Decentral_BOI_f_EV05_intelligent")


    # We directly generate a complete district.
    data.generateDistrictComplete(calcUserProfiles=False, saveUserProfiles=False)

    # Calculation of the devices' optimal operation
    data.optimizationClusters()

    # Calculation of the key performance indicators using the devices' operation profiles of clustered time periods
    data.calulateKPIs()

    # Create a certificate (PDF) which summarizes the district parameters and calculated KPIs
    data.KPIs.create_certificate(data=data, result_path=data.resultPath)

    print("Congratulations! You calculated an optimized device operation for the selected neighborhood!")

    return data


if __name__ == '__main__':
    data = example8_scenario_evaluation()


