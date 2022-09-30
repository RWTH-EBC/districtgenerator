# -*- coding: utf-8 -*-

"""
Example six will show you the impact of the minimum indoor temperature.
"""


# Import classes of the districtgenerator to be able to use the district generator.
from classes import *

#PREPARATION: Change the minimum indoor temperature

# In this example, we will choose a different indoor temperature.
# As saving energy is now more important than ever, people may be happy with only 18°C indoor temperature in summer.
# So let's see, if that makes a difference to our heat demand.
# To change the minimum indoor Temperature, we open the file 'design_building_data.json' in the folder '\data'.
# Change "T_set_min" to 18,0°C.

def example_change_indoor_temperature():

    # Generate district
    data = Datahandler()
    data.generateDistrictComplete(scenario_name='example', calcUserProfiles=False, saveUserProfiles=False)

    # We can compare our results. For example can we have a look at the heat demand profile.
    # Generate Plots
    data.plot(mode="heatDemand", timeStamp=True, show=True)

    # Or we check the design heat load of our first building.
    print("\nThe design heat load of building 0  now is "
          + str(round(data.district[0]["heatload"])) + "W.")

    return data


if __name__ == '__main__':
    data = example_change_indoor_temperature()
