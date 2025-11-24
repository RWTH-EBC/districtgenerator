# -*- coding: utf-8 -*-

"""
In this example we use the EHDO tool to generate central devices"""

# Import classes of the districtgenerator to be able to use the district generator.
from districtgenerator.classes import *
import pandas as pd
import matplotlib.pyplot as plt


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
    data.generateDemands(calcUserProfiles=True, saveUserProfiles=True)    
    
    # Design decentral and central devices for the current district.
    data.designDevicesComplete(saveGenerationProfiles=True)
    
    #data.generateDistrictComplete(calcUserProfiles=True, saveUserProfiles=True)

    print("Congratulations! You generated your energy central for the selected neighborhood!")
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

    #exemplary_plot(data)

    return data

def exemplary_plot(data):

    # Sum heat demand of buildings
    heat = data.district[0]["user"].heat
    # Unit conversion [kWh]
    heat = heat / (data.time["dataResolution"] / data.time["timeResolution"]) / 1000

    # Calculate frequency in hours
    freq_hours = data.time["timeResolution"] / 3600
    freq_str = f'{freq_hours}H'

    # Create a dataframe that contains the timestamps
    date_range = pd.date_range(start='2023-01-01', periods=data.time["timeSteps"], freq=freq_str)
    df = pd.DataFrame(heat, index=date_range, columns=['Value'])

    # Aggregate the data on a monthly basis (totalled value per month)
    monthly_data = df.resample('M').sum()

    # Plot as bar chart
    plt.figure(figsize=(10, 6))
    plt.bar(monthly_data.index.strftime('%b'), monthly_data['Value'])
    plt.ylabel('District space heat demand in kWh')
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.show()

if __name__ == '__main__':
    data = one_district_opt_cent()