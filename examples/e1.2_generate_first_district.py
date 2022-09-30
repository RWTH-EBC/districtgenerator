# -*- coding: utf-8 -*-

"""
Now let's add our buildings to the district.
"""

# Import classes of the districtgenerator to be able to use the district generator.
from classes import *

def example1_2_generate_first_district():

    # Initialize District
    data = Datahandler()

    # Generate Environment for the District
    data.generateEnvironment()

    # We initialize the buildings in our district. As input the name of a scenario file is required.
    # In this example we use the existing example-file example.csv.
    # This file distributes the basic information about the buildings including the type of building and its area.

    # Initialize buildings of the district
    data.initializeBuildings(scenario_name="example")

    print("\nThe district now looks like this:")
    print("District:" + str(data.district) + "\n")
    print("Our district now holds two buildings with id 0 and 1.\n"
          "We can see the input information like the floor area ant the building type")

    print("Lets try the next example e1.3_generate_first_district to specify our buildings data.")

    return data


if __name__ == '__main__':
    data = example1_2_generate_first_district()


