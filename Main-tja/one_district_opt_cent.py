# -*- coding: utf-8 -*-

"""
In this example we use the EHDO tool to generate central devices"""

# Import classes of the districtgenerator to be able to use the district generator.
from districtgenerator.classes import *


def one_district_opt_cent():

    # Initialize District
    data = Datahandler(env_path=".env.CONFIG.DISTRICT1")
    model_param_eh = data.params_ehdo_model
    print(f"\nOptim_dimension of: {data.scenario_name} is {model_param_eh["optim_dimension"]}")

    # Generate Environment for the District
    data.generateEnvironment()

    # Initialize Buildings to the District
    data.initializeBuildings()

    # Generate more detailed Building models
    data.generateBuildings()

    # Now we generate building specific demand profiles with the adjusted assumptions
    # Use calcUserProfiles=False to speed up the calculation if user profiles are already calculated
    data.generateDemands(calcUserProfiles=False, saveUserProfiles=False)    
    
    # Design decentral and central devices for the current district.
    data.designDevicesComplete(saveGenerationProfiles=True, all_data_connect="All_data_connect_can_be_used_in_run_optim_connect)")
    
    
    print("Congratulations! You generated your energy central for the selected neighborhood!")

    return data

if __name__ == '__main__':
    data = one_district_opt_cent()