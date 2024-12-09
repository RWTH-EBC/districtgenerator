# -*- coding: utf-8 -*-

"""
We reached the final step, to generate our first district: Generate demand profiles for our buildings.
"""

# Import classes of the districtgenerator to be able to use the district generator.
from classes import *



def example8_scenario_evaluation():

    # Initialize District
    data = Datahandler()

    # We directly generate a complete district.
    #data.generateDistrictComplete(scenario_name='Quartier_3', calcUserProfiles=False, saveUserProfiles=False,
    #                              fileName_centralSystems="BF_Strategie_central_devices", saveGenProfiles=False)
    data.initializeBuildings(scenario_name='example')
    data.generateEnvironment(plz=50672)
    data.generateBuildings()
    data.generateDemands(calcUserProfiles=True, saveUserProfiles=False)


    centralEnergySupply = False
    # Sizing of the selected devices
    # data.designDevicesComplete(fileName_centralSystems="BF_Strategie_central_devices", saveGenerationProfiles=True)
    #input_Quartiersausweis = dataframe
    if centralEnergySupply == True:
        data.designDecentralDevices(saveGenerationProfiles=True)
        data.designCentralDevices()

    else:
        data.designDecentralDevices(saveGenerationProfiles=True)
        data.centralDevices = {}
        # data.designDecentralDevices(saveGenerationProfiles=True, input_webtool)


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


