# -*- coding: utf-8 -*-

"""
We reached the final step, to generate our first district: Generate demand profiles for our buildings.
"""

# Import classes of the districtgenerator to be able to use the district generator.
from districtgenerator import *


def example1_4_generate_first_district():

    # Initialize District
    data = Datahandler()

    # Generate Environment for the District
    data.generateEnvironment()

    # Initialize Buildings to the District
    data.initializeBuildings(scenario_name="example")

    # Generate a more detailed Building
    data.generateBuildings()

    # As last step we generate individual demand profiles for our buildings.
    # The computation can take a few minutes, because energy profiles for a hole year are computed.
    # As input we tell the program, if we want to calculate/save new demand profiles.
    # If True, the datahandler generates user profiles for one year and saves them in the directory
    # "results/demands/". We calculate profiles for the presents of occupants (occ), for electricity demand of
    # appliances and lighting (elec), for heat demand of space heating (heat) and domestic hot water (dhw), internal
    # heat gains (gains) and the electricity demand of electric vehicles (car).
    # Alternatively we can use profiles, that we calculated before. To do so, we put "calcUserProfiles=False".
    # This helps to speed up calculation and to compare different districts.
    # But for now we want to get new profiles.

    # Generate demand profiles
    data.generateDemands(calcUserProfiles=True, saveUserProfiles=True)

    # We now have a complete district. Instead of using all the steps separately, like we have done in this example,
    # we can also generate a complete district with the following commands:
    # data= Datahandler()
    # data.generateDistrictComplete(scenario_name="example", calcUserProfiles=True, saveUserProfiles=True)

    # We can access demand profiles through data.district[(insert building id)].user[(insert profile type)].
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
    print("The annual heating demand of building 1 is " + str(round(total_heating_demand_1)/1000) + "kWh.\n")
    print("The maximum heating power of building 0 is " + str(round(max_heating_power_0)) + "W.")

    max_electricity_power = max(data.district[0]['user'].elec)
    print("The maximum electricity power of building 0 is " + str(round(max_electricity_power)) + "W.\n")

    print("Congratulations! You generated your first complete district!")

    return data


if __name__ == '__main__':
    data = example1_4_generate_first_district()

