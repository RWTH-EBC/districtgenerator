# -*- coding: utf-8 -*-

"""
In this second example we will learn how to create a custom district.
"""


# Import classes of the districtgenerator to be able to use the district generator.
from classes import *

# For this example we need to make same PREPARATIONS:

# 1. Custom district file:

# At first, we will create a new custom district. Therefor you have to open the prepared CSV-file with the name
# "example2.csv" in the "data/scenarios/" directory of the districtgenerator. You can open the file with a text editor
# or a spreadsheet software as Microsoft Excel. Make sure that the separation signs stay semicolons!
# Except for the header in the first line (with information to each column), each row represents a building. In the
# first column the IDs of the buildings are stored. They start with zero. Just add an ongoing ID to each building
# you add. The "building"-column shows the short versions of the building types.
# You can choose "SFH", "MFH", "TH" and  "AB" for "single_family_house", "multi_family_house", "terraced_house"
# and "apartment_block". Next comes the construction year.
# It follows a code for status of modernisation (retrofit level) and the size of the living space.
# For more information about the possible settings in this central CSV-file, have a look into the ReadMe file.

# Now it is your turn! Add or delete some building to the CSV-file. Have in mind that more buildings need more
# computation time. Try to use some different options. Then save the file.

# 2. Changing the time resolution:

# Now the user profiles are generated for a resolution of 15 minutes. Because it could take some
# time to compute if you added a lot of buildings, we will change the time resolution to three hours.
# Therefor open the json-file with the name "time_data" in the directory "data/" of the districtgenerator.
# Change the value of "timeResolution" to "10800" seconds.
# Be careful to not delete the coma behind the value! Safe and close the file.

# The preparations are complete. You may run the second example now.


def example_generate_custom_district():

    # The name of the scenario file is now "example2". So the file from the preparations is used.
    # We want to use the computed user profiles of the first example in the following examples. So to compute the
    # profiles in this example but do not overwrite the old ones, we use for the initialization of the Datahandler the
    # parameter "saveUserProfiles" and set it to "False".

    # Generate district with energy profiles
    # We now use the function generateDistrictComplete() to generate a complete district all at once.
    data = Datahandler()
    data.generateDistrictComplete(scenario_name='example2', calcUserProfiles=True, saveUserProfiles=False)

    # Let's look into our custom district:

    # Again get our time step length in hours by:
    len_timestep = data.time["timeResolution"] / 3600

    # As we now have a custom number of buildings,
    # we can compare the annual heating demand of them all by creating a loop:
    for id in range(len(data.district)):
        total_heating_demand = sum(
            data.district[id]['user'].heat[t] for t in range(len(data.district[0]['user'].heat))) * len_timestep
        print(
            "The annual heating demand of building "+str(id)+ " is " + str(round(total_heating_demand) / 1000) + "kWh.")

    # And some more output for the first building:
    print("\nThe heating power of building 0 in timestep 0 is " + str(round(data.district[0]['user'].heat[0])) + "W.")
    print("The electricity power for plug-in devices of building 0 in timestep 0 is " + str(
        round(data.district[0]['user'].elec[0])) + "W.\n")
    max_heating_power_0 = max(data.district[0]['user'].heat)
    print("The maximum heating power of building 0 is " + str(round(max_heating_power_0)) + "W.")
    max_electricity_power = max(data.district[0]['user'].elec)
    print("The maximum electricity power of building 0 is " + str(round(max_electricity_power)) + "W.\n")

    return data


if __name__ == '__main__':
    data = example_generate_custom_district()

    print("This was the second example!")

    # Now you can compare scenarios with each other. How about investigating the impact of district size,
    # building types or the impact of the building year of your district?