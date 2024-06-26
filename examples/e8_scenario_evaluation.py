# -*- coding: utf-8 -*-

"""
We reached the final step, to generate our first district: Generate demand profiles for our buildings.
"""

# Import classes of the districtgenerator to be able to use the district generator.
from classes import *



def example8_scenario_evaluation():


    import time
    A_1 = time.time()

    # Initialize District
    data = Datahandler()

    # We directly generate a complete district.
    data.generateDistrictComplete(scenario_name='Quartier_3', calcUserProfiles=True, saveUserProfiles=False,
                                  fileName_centralSystems="BF_Strategie_central_devices", saveGenProfiles=False)


    centralEnergySupply = False
    # Sizing of the selected devices
    # data.designDevicesComplete(fileName_centralSystems="BF_Strategie_central_devices", saveGenerationProfiles=True)
    #input_Quartiersausweis = dataframe
    if centralEnergySupply == True:
        data.initializeCentralDevices(fileName_centralSystems="BF_Strategie_central_devices")
        data.designDecentralDevices(saveGenerationProfiles=True)
        data.designCentralDevices(saveGenerationProfiles=True)

    else:
        data.designDecentralDevices(saveGenerationProfiles=True)
        # data.designDecentralDevices(saveGenerationProfiles=True, input_webtool)

    # Within a clustered time series, data points are aggregated across different time periods
    # based on the k-medoids method
    data.clusterProfiles(centralEnergySupply)

    # Calculation of the devices' optimal operation
    data.optimizationClusters(centralEnergySupply)


    # Calculation of the key performance indicators using the devices' operation profiles of clustered time periods
    data.calulateKPIs()

    # TODO: erzeuge Energieausweis


    print("Congratulations! You calculated an optimized device operation for the selected neighborhood!")

    A_2 = time.time()
    print(str(A_1))
    print(str(A_2))

    return data


if __name__ == '__main__':
    data = example8_scenario_evaluation()


