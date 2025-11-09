# -*- coding: utf-8 -*-

"""
In this example we use the EHDO tool to generate central devices"""

# Import classes of the districtgenerator to be able to use the district generator.
from districtgenerator.classes import *


def one_district_opt_cent():

    # Initialize District
    data = Datahandler(env_path=".env.CONFIG.DISTRICT1")

    # Generate Environment for the District
    data.generateEnvironment()

    # Initialize Buildings to the District
    data.initializeBuildings()

    # Generate more detailed Building models
    data.generateBuildings()

    # Now we generate building specific demand profiles with the adjusted assumptions
    data.generateDemands(calcUserProfiles=True, saveUserProfiles=True)    
    
    # Design decentral and central devices for the current district.
    data.designDevicesComplete(saveGenerationProfiles=True)
    
    
    print("Congratulations! You generated your energy central for the selected neighborhood!")

    return data

if __name__ == '__main__':
    data = one_district_opt_cent()