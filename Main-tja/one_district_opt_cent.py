# -*- coding: utf-8 -*-

"""
In this example we use the EHDO tool to generate central devices"""

# Import classes of the districtgenerator to be able to use the district generator.
from districtgenerator.classes import *
import pandas as pd
import matplotlib.pyplot as plt


def one_district_opt_cent():

    # Initialize District
    data = Datahandler(env_path=".env.CONFIG.EXAMPLE")
    model_param_eh = data.params_ehdo_model
    
    #ToDo: add Opitm_dimension to config.py
    #print(f"\nOptim_dimension of: {data.scenario_name} is {model_param_eh["optim_dimension"]}")

    # Generate Environment for the District
    data.generateEnvironment()

    # Initialize Buildings to the District
    data.initializeBuildings()

    # Generate more detailed Building models
    data.generateBuildings()

    # Now we generate building specific demand profiles with the adjusted assumptions
    # Use calcUserProfiles=False to speed up the calculation if user profiles are already calculated
    data.generateDemands(calcUserProfiles=True, saveUserProfiles=True)    

    # Get topology option either node or road based from heat grid data
    topology_option = data.heat_grid_data["topology_option"]
    
    # Design decentral and central devices for the current district.
    #data.designDevicesComplete(saveGenerationProfiles=True)
    if data.district[0]["buildingFeatures"]["heater"] == "heat_grid":
        centralEnergySupply = True
        data.designDecentralDevices()
        data.designCentralDevices()
    else:
        centralEnergySupply = False
        data.designDecentralDevices()
        data.centralDevices = {}
    
    #data.generateDistrictComplete(calcUserProfiles=True, saveUserProfiles=True)

    print("Congratulations! You generated your energy central for the selected neighborhood!")

    # Get the result of heating_network
    net_heating_demand = data.heat_grid_data.get("net_heating_demand", None)

    if net_heating_demand is not None:
        print(f"Net heating demand: {net_heating_demand} kW")
    else:
        print("Net heating demand not calculated.")

    # Capacities of the decentral devices in one  district
    for device, capacity in data.district[0]["capacities"].items():
        print(f"  {device}: {capacity}")
    
    #print(data.district[0]["capacities"].items())
    print("Capacities of the decentral devices in the buildings:")
    
    for building in data.district:
        if "capacities" in building:
            print(f"Building: {building['unique_name']}")
            print("Capacities:")
            for device, capacity in building["capacities"].items():
                print(f"  {device}: {capacity}")
        else:
            print(f"Building: {building['unique_name']} has no capacities defined.")


    if "capacities" in data.centralDevices:
        capacities = data.centralDevices["capacities"]
        print("Capacities of the central devices in energy hub:")
        for device, details in capacities.items():
            if isinstance(details, dict) and "cap" in details and details["cap"] > 0:
                print(f"  {device}: {details['cap']}")

    else:
        print("No capacities defined in energy hub.")  


    return data

if __name__ == '__main__':
    data = one_district_opt_cent()