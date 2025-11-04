# -*- coding: utf-8 -*-

"""
We reached the final step, to generate our first district: Generate demand profiles for our buildings.
"""

# Import classes of the districtgenerator to be able to use the district generator.
from districtgenerator.classes import *



def example8_scenario_evaluation():

    # Initialize District
    data = Datahandler(scenario_name = "district_F_buildings_30")

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

    # As last step we use the EHDO tool to get an optimized energy central for neighborhoods. EHDO is a tool for
    # planning and designing complex energy systems. The central feature is coupling of different
    # sectors (e.g. electricity, heating, cooling). In early planning phases of energy supply concepts for
    # neighborhoods, the tool provides an initial assessment of the optimal system configuration, dimensioning
    # and economic efficiency.
    # As Input the EHDO needs data of the demands and location (weather), which are given directly from the output of
    # the district generator. Further information about the technologies to be considered for the dimensioning of
    # the energy central and economic parameters are read in from further .csv and . json. data sources


    # Within data the results of EHDO are given. For each device the annual generated amount of
    # electricity or heat as well as the nominal power or storage capacity are calculate.
    # Furthermore, ecological and economic indicatoers are calculated.