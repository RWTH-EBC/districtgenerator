# -*- coding: utf-8 -*-

"""
This is the fourth example. Here we change the site of the district.
"""

# Import classes of the districtgenerator to be able to use the district generator.
from classes import *

# PREPARATION

# 1. site_data.json:
# Again we have to make changes in a JSON-file. This time it is the file with the name "site-data.json" in the "data/"
# directory of the distictgenerator. Open the file (e.g. with a text editor). We change the location of the district
# from Aachen to Garmisch Patenkirchen in the alps. Both are cities in Germany. The available weather data is restricted
# to sites in Germany. To change the location we set the values of the "location" in the JSON-file to "[47.49, 11.09]",
# the value of the "climateZone" to "15" and the "altitude" to "700". Than save the file.
# Which climate zone belongs to which city is listed in design_weather_data.json in the folder '\data\weather'.

# 2. time_data.json:
# You may set the timeResolution back to "900" seconds, if you changed that in the last examples.
# Now you should be ready to run the code.


def example_change_site():

    # We use the first example file as district scenario.

    # Generate district with existing energy profiles
    data = Datahandler()
    data.generateDistrictComplete(scenario_name='example', calcUserProfiles=True, saveUserProfiles=False)

    # Now we create again plots of the user profile with a unique file name.
    data.plot(mode="heatDemand", timeStamp=True, show=True)

    # We also can compare the design heat load of our buildings. As they are based on the design outside temperature,
    # they vary with the location.

    print("\nThe design heat load of building 0 at location " + str(data.site["location"])
          + " is " + str(round(data.district[0]["heatload"])) + "W.")

    # After the first computation, you can set the site back to Aachen (location: [51.0,6.55], climateZone: 0,
    # altitude: 0) and run the example again. Afterwards you can compare the plots and see the differences based on the
    # site change.

    return data


if __name__ == '__main__':
    data = example_change_site()

    print("This is like beaming! Directly from Aachen to Bavaria. And you finished example four!")