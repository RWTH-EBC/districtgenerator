# -*- coding: utf-8 -*-

"""
This is the fourth example to add more information the the building models.

If you run the examples with Python console, you can see the output file.
To do this right-hand click the example.py file (e4_generate_buildings.py).
Then choose 'Modify Run Configuration' and tick 'Run with Python Console'.
"""

# Import classes of the districtgenerator to be able to use the district generator.
from districtgenerator.classes import *

def example4_generate_buildings():
    # Initialize District
    data = Datahandler()

    # Generate Environment for the District
    data.generateEnvironment()

    # Initialize Buildings to the District
    data.initializeBuildings(scenario_name="example")

    # Next we generate more information and add them to the building models.
    # To do this we use the TEASER tool. This tool returns more detailed information about an archetype building
    # according to the web database "Tabula". This includes window- and wall sizes, materials and more.
    # Based on this and in combination with the weather data from the environment we calculate e.g. the heat flow
    # through walls and internal gains.
    data.generateBuildings()

    ### ===========================================  Output  =========================================== ###
    # For every building the envelope class is added (e.g. see data.district.0.envelope). Within this class
    # all information about components of the building and their materials are given.
    # Furthermore the user class is added to every building which contains at this point information about
    # the total annual electrical demand, the number of flats and occupants within the building.


    return data


if __name__ == '__main__' :
    data = example4_generate_buildings()
