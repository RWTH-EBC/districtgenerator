# -*- coding: utf-8 -*-

"""
This is the third example to initialize the buildings and to add them to the district.

If you run the examples with Python console, you can see the output file.
To do this right-hand click the example.py file (e3_initialize_buildings.py).
Then choose 'Modify Run Configuration' and tick 'Run with Python Console'.
"""

# Import classes of the districtgenerator to be able to use the district generator.
from districtgenerator.classes import *

def example3_initialize_buildings():

    # Initialize District
    data = Datahandler(scenario_name = "example")

    # Generate Environment for the District
    data.generateEnvironment()

    # We initialize the buildings of the district.
    data.initializeBuildings()

    ### =====================================  Output  ===================================== ###
    # The district consists of a list of four buildings with id 0 to 3 (see "data.district").
    # To every building the building features from example.csv are added.

    return data


if __name__ == '__main__':
    data = example3_initialize_buildings()


