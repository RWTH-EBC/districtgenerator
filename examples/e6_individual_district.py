# -*- coding: utf-8 -*-

"""
This is the sixth example to change specific assumptions about the district.

If you run the examples with Python console, you can see the output file.
To do this right-hand click the example.py file (e6_individual_district.py).
Then choose 'Modify Run Configuration' and tick 'Run with Python Console'.
"""

# Import classes of the districtgenerator to be able to use the district generator.
from districtgenerator.classes import *

def example6_individual_district():

    ### For this example we have to change some data in the json-files within the "data/" folder.

    # 1. Changing the location of the district:
    # We have to adjust data in "site_data.json". Open the file (e.g. with a text editor). We change
    # the location of the district from Aachen to Garmisch Patenkirchen. To change the location we
    # set the values of the "location" in the JSON-file to "[47.49, 11.09]", the value of the "climateZone"
    # to "15" and the "altitude" to "700". Than save the file.
    # Which climate zone belongs to which city is listed in design_weather_data.json in the folder '\data\weather'.

    # 2. Change the weather data base
    # Next, we change the database of the weather data. To do this, we change "site_data.json".
    # The value under "TRYYear" to "TRY2045" and the value under "TRYType", we change to "warm".
    # Now we calculate the profiles for a warm reference year from 2045.

    # 3. Change the minimum indoor temperature
    # To change the minimum indoor temperature, we open the file "design_building_data.json"
    # in the folder '\data' and change "T_set_min" to 18,0°C.

    # 4. Changing the time resolution:
    # To change the time resolution of the profiles open the json-file with the name "time_data"
    # in the directory "data/" of the districtgenerator. Change the value of "timeResolution" to
    # "10800" seconds. That is equal to a time resolution of three hours.
    # Be careful to not delete the coma behind the value! Safe and close the file.

    # Initialize District
    data = Datahandler()

    # Generate Environment for the District
    data.generateEnvironment()

    # Initialize Buildings to the District
    data.initializeBuildings(scenario_name="example")

    # Generate a more detailed Building
    data.generateBuildings()

    # Now we generate building specific demand profiles with the adjusted assumptions
    data.generateDemands(calcUserProfiles=True, saveUserProfiles=True)

    return data


if __name__ == '__main__':
    data = example6_individual_district()


