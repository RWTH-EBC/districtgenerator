# -*- coding: utf-8 -*-

"""
Example five will show you the impact of the weather.
"""


# Import classes of the districtgenerator to be able to use the district generator.
from classes import *

# PREPARATION: Change the weather data base

# In this example, we will our "Test Reference Year". That means, we change the Database for the weather data.
# To do this, we go site_data.json. The value under "TRYYear" we change to TRY2045 and the value under "TRYType",
# we change to warm. Therefor we use a warm reference year from 2045. What do you expect to happen to the heat demand
# of the district?

# To compare the results, we use the profiles from our first example by setting scenario_name='example'
# and calcUserProfiles=False. Also check, if you undid all changes, you did in the previous examples.
# Location should be Aachen, and the timeResolution=900.

def example_change_TRYyear():

    # Generate district
    data = Datahandler()
    data.generateDistrictComplete(scenario_name='example', calcUserProfiles=False, saveUserProfiles=False)

    # We can compare our results. For example can we have a look at the heat demand profile.
    # Generate Plots
    data.plot(mode="heatDemand", timeStamp=True, show=True)

    # Or we compare the design heat load of our first building. Anything different?
    print("\nThe design heat load of building 0 in a warm Test Reference Year 2045 is "
          + str(round(data.district[0]["heatload"])) + "W.")

    return data


if __name__ == '__main__':
    data = example_change_TRYyear()

    # Remember to undo your changes for further comparisons.
