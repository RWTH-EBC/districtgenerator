# -*- coding: utf-8 -*-

"""
We reached the final step, to generate our first district: Generate demand profiles for our buildings.
"""

# Import classes of the districtgenerator to be able to use the district generator.
from districtgenerator.classes import *



def example8_scenario_evaluation():

    # Initialize District
    data = Datahandler()

    data.initializeBuildings(scenario_name='example')
    data.generateEnvironment(plz="52064")
    data.generateBuildings()
    data.generateDemands(calcUserProfiles=False, saveUserProfiles=False)

    centralEnergySupply = True
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
    webtool = {}
    data.calulateKPIs()

    # TODO: erzeuge Energieausweis


    print("Congratulations! You calculated an optimized device operation for the selected neighborhood!")

    return data


if __name__ == '__main__':
    data = example8_scenario_evaluation()


