# -*- coding: utf-8 -*-

"""
We reached the final step, to generate our first district: Generate demand profiles for our buildings.
"""

# Import classes of the districtgenerator to be able to use the district generator.
from districtgenerator.classes import *



def example8_scenario_evaluation():

    # Initialize District
    data = Datahandler(scenario_name = "example")

    data.initializeBuildings()
    data.generateEnvironment()
    data.generateBuildings()
    data.generateDemands(calcUserProfiles=False, saveUserProfiles=False)

    centralEnergySupply = False
    # Sizing of the selected devices
    if centralEnergySupply == True:
        data.designCentralDevices(saveGenerationProfiles=False)
    else:
        data.designDecentralDevices(saveGenerationProfiles=True)
        data.centralDevices = {}

    # Within a clustered time series, data points are aggregated across different time periods
    # based on the k-medoids method
    data.clusterProfiles(centralEnergySupply)

    # Calculation of the devices' optimal operation
    data.optimizationClusters(centralEnergySupply)

    # Calculation of the key performance indicators using the devices' operation profiles of clustered time periods
    data.calulateKPIs()
    # Create a certificate (PDF) which summarizes the district parameters and calculated KPIs
    data.KPIs.create_certificate(data=data, result_path=data.resultPath)

    # TODO: erzeuge Energieausweis


    print("Congratulations! You calculated an optimized device operation for the selected neighborhood!")

    return data


if __name__ == '__main__':
    data = example8_scenario_evaluation()


