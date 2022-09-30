# -*- coding: utf-8 -*-

"""
Next step: create an environment.
"""

# Import classes of the districtgenerator to be able to use the district generator.
from classes import *

def example1_1_generate_first_district():

    # Initialize District
    data = Datahandler()


    # Next we generate an environment.
    # Based on the location of the district this includes outside temperatures and sun radiation.
    # The location can be changed in the site_data.json file. You find it in \data.
    # We create our first district in Aachen. When you open the site_data.json file, you should see, the "location"
    # is [51.0,6.55], the "climateZone" 0 and the "altitude" 0.
    # The time resolution can be changed in time_data.json. You also find it in \data.
    # For this example it should be 900 seconds, which equals 15 Minutes.
    # The weather data is taken from a Test Reference Year Database from the DWD.

    # Generate Environment for the District
    data.generateEnvironment()

    print("\nOur district now looks like this:")
    print("District:" + str(data.district))
    print("There is still no information about our district.\n")
    print("But we added information about our environment into 'site'.\n"
          "For example we can see the location, the outside temperatures over one year and the solar radiation.")
    print("Location:" + str(data.site['location']))
    print("Outside Temperature:" + str(data.site['T_e']))
    print("Solar Radiation:" + str(data.site["SunTotal"]))
    print("The time resolution of the weather data is " + str(data.time["timeResolution"]/60) + " Minutes.")
    print("\nNow lets add buildings to our district.\n"
          "Start the next example e1.2_generate_first_district.")

    return data


if __name__ == '__main__':
    data = example1_1_generate_first_district()

    print("Let's add some buildings!")


