# -*- coding: utf-8 -*-

"""
This is the fifth example to generate the demand profiles of the buildings.

If you run the examples with Python console, you can see the output file.
To do this right-hand click the example.py file (e1.0_generate_first_district.py).
Then choose 'Modify Run Configuration' and tick 'Run with Python Console'.
"""

# Import classes of the districtgenerator to be able to use the district generator.
from districtgenerator.classes import *

def example1_4_generate_first_district():

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
    data.generateDemands(calcUserProfiles=True, saveUserProfiles=True)

    ### ===========================================  Output  =========================================== ###
    # The (demand) profiles for electricity demand of appliances and lighting (elec),
    # for heat demand of space heating (heat),domestic hot water (dhw), internal heat gains (gains)
    # and the time series for the presents of occupants (occ) are now calculated
    # We can access them under data.district.id.user.



    # Here are some examples:

    print("\nThe heating power of building 0 in timestep 0 is "+ str(round(data.district[0]['user'].heat[0])) + "W.")
    print("The electricity power for plug-in devices of building 0 in timestep 0 is "
          + str(round(data.district[0]['user'].elec[0])) + "W.\n")

    # We can also use the profiles, to get the total demand or the maximun power.
    # The given numbers in the demand profile are the power in that timestep. So if we have 15 Minute timesteps,
    # the demand in each timestep equals the given power times 1/4 hour.
    # To get the right units, we see how long one timestep is defined. As this value had to be inserted in seconds,
    # we convert it into hours:
    len_timestep = data.time["timeResolution"]/3600
    total_heating_demand_0 = sum(
        data.district[0]['user'].heat[t] for t in range(len(data.district[0]['user'].heat))) * len_timestep
    total_heating_demand_1 = sum(
        data.district[1]['user'].heat[t] for t in range(len(data.district[1]['user'].heat))) * len_timestep
    max_heating_power_0 = max(data.district[0]['user'].heat)
    print("The annual heating demand of building 0 is " + str(round(total_heating_demand_0)/1000) + "kWh.")
    print("The maximum heating power of building 0 is " + str(round(max_heating_power_0)) + "W.")

    print("The maximum electricity power of building 0 is " + str(round(max(data.district[0]['user'].elec))) + "W.\n")


    return data


if __name__ == '__main__':
    data = example1_4_generate_first_district()


