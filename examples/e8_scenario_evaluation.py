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
    data.generateDistrictComplete(scenario_name='Typquartier_1', calcUserProfiles=False, saveUserProfiles=False,
                                  fileName_centralSystems="BF_Strategie_central_devices", saveGenProfiles=True)

    centralEnergySupply = False
    # Sizing of the selected devices
    # data.designDevicesComplete(fileName_centralSystems="BF_Strategie_central_devices", saveGenerationProfiles=True)
    if centralEnergySupply == True:
        data.initializeCentralDevices(fileName_centralSystems="BF_Strategie_central_devices")
        data.designDecentralDevices(saveGenerationProfiles=True)
        data.designCentralDevices(saveGenerationProfiles=True)
    else:
        data.initializeCentralDevices(fileName_centralSystems="BF_Strategie_central_devices")
        data.designDecentralDevices(saveGenerationProfiles=True)
        data.designCentralDevices(saveGenerationProfiles=True)

    # Within a clustered time series, data points are aggregated across different time periods
    # based on the k-medoids method
    data.clusterProfiles()

    # Calculation of the devices' optimal operation
    data.optimizationClusters(centralEnergySupply)


    # Calculation of the key performance indicators using the devices' operation profiles of clustered time periods
    data.calulateKPIs()


    print("Congratulations! You calculated an optimized device operation for the selected neighborhood!")

    import time
    AA = time.time()

    return data


if __name__ == '__main__':
    data = example8_scenario_evaluation()


