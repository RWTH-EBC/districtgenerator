# -*- coding: utf-8 -*-

"""
In this step, we fill our buildings with more informations.
"""

# Import classes of the districtgenerator to be able to use the district generator.
from classes import *


def example1_3_generate_first_district() :
    # Initialize District
    data = Datahandler()

    # Generate Environment for the District
    data.generateEnvironment()

    # Initialize Buildings to the District
    data.initializeBuildings(scenario_name="example")

    # Next we generate more information about the buildings.
    # To do this we use the TEASER tool. This tool returns more detailed information about an archetype building
    # according to the web database "Tabula". This includes window- and wall sizes, materials and more.
    # Based on this and in combination with the weather data from the environment we calculate e.g. the heat flow
    # through walls and internal gains. With this information we can e.g. calculate information about the buildings
    # design heat load. The design heat load is calculated with DIN EN 12831.
    # The number of occupants is between 1 and 5.

    # Generate a more detailed Building
    data.generateBuildings()

    # We can access the specified data. Here are some examples:
    print("\nThe number of occupants in building 0 is " + str(data.district[0]['user'].nb_occ[0]) + ".")
    print("The roof area of building 0 is " + str(round(data.district[0]['envelope'].A['opaque']['roof']))
          + " m\N{SUPERSCRIPT TWO}")
    print(str(round(data.district[0]['envelope'].A['window']['sum']))
          + " m\N{SUPERSCRIPT TWO} of building 0 is covered with windows.")
    print("The design heat load of building 0 is " + str(round(data.district[0]['heatload'])) + "W.")

    print("\nTo finish our example with the last step of adding demand profiles, "
          "go to example e1.4_generate_fist_district")

    return data


if __name__ == '__main__' :
    data = example1_3_generate_first_district()
