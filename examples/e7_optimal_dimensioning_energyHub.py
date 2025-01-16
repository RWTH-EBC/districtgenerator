# -*- coding: utf-8 -*-

"""
In this example we use the EHDO tool to """

# Import classes of the districtgenerator to be able to use the district generator.
from districtgenerator.classes import *


def example7_optiEnergyCentral_EHDO():

    # Initialize District
    data = Datahandler()

    # We directly generate a complete district.
    data.generateDistrictComplete(scenario_name='example', calcUserProfiles=False, saveUserProfiles=False,
                                  saveGenProfiles=False)

    # As last step we use the EHDO tool to get an optimized energy central for neighborhoods. EHDO is a tool for
    # planning and designing complex energy systems. The central feature is coupling of different
    # sectors (e.g. electricity, heating, cooling). In early planning phases of energy supply concepts for
    # neighborhoods, the tool provides an initial assessment of the optimal system configuration, dimensioning
    # and economic efficiency.
    # As Input the EHDO needs data of the demands and location (weather), which are given directly from the output of
    # the district generator. Further information about the technologies to be considered for the dimensioning of
    # the energy central and economic parameters are read in from further .csv and . json. data sources

    data.designCentralDevices(saveGenerationProfiles=True)
    # Within data the results of EHDO are given. For each device the annual generated amount of
    # electricity or heat as well as the nominal power or storage capacity are calculate.
    # Furthermore, ecological and economic indicatoers are calculated.

    print("Congratulations! You generated your energy central for the selected neighborhood!")

    return data

if __name__ == '__main__':
    data = example7_optiEnergyCentral_EHDO()




