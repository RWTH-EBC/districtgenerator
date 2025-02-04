# -*- coding: utf-8 -*-

"""
This is the fifth example to generate the demand profiles of the buildings.

If you run the examples with Python console, you can see the output file.
To do this right-hand click the example.py file (e5_generate_demands.py).
Then choose 'Modify Run Configuration' and tick 'Run with Python Console'.
"""

# Import classes of the districtgenerator to be able to use the district generator.
from districtgenerator.classes import *
import pandas as pd
import matplotlib.pyplot as plt

def example5_generate_demands():

    # Initialize District
    data = Datahandler()

    # Generate Environment for the District
    data.generateEnvironment()

    # Initialize Buildings to the District
    data.initializeBuildings(scenario_name="example")

    # Generate a more detailed Building
    data.generateBuildings()

    # Now we generate building specific demand profiles. The computation can take a few minutes,
    # because energy profiles for a hole year are computed. As input we tell the program,
    # if we want to calculate and save the demand profiles: If "calcUserProfiles=True", the datahandler
    # generates the profiles and saves them in the directory "results/demands/".
    # Alternatively we can load existing profiles. To do so, we put "calcUserProfiles=False".
    # The Richardson tool is used to generate stochastic occupancy, internal heat gain and electric load profiles.
    # With an 5R1C thermal building model the space heat profiles and a stochastic model the drinking hot water
    # profiles are calculated.
    data.generateDemands(calcUserProfiles=True, saveUserProfiles=True)

    ### ===========================================  Output  =========================================== ###
    # The (demand) profiles for electricity demand of appliances and lighting (elec),
    # for heat demand of space heating (heat),domestic hot water (dhw), internal heat gains (gains)
    # and the time series for the presents of occupants (occ) are now calculated
    # We can access them under data.district.id.user or in the results folder.

    # We can now use the profiles for exemplary analyses like monthly demands or peak loads.
    # We plot the district space heat demand in kWh
    exemplary_plot(data)

    return data

def exemplary_plot(data):

    # Sum heat demand of buildings
    heat = data.district[0]["user"].heat + data.district[1]["user"].heat
    # Unit conversion [kWh]
    heat = heat / (data.time["dataResolution"] / data.time["timeResolution"]) / 1000

    # Create a dataframe that contains the timestamps
    date_range = pd.date_range(start='2023-01-01', periods=data.time["timeSteps"], freq='15T')
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
    data = example5_generate_demands()


