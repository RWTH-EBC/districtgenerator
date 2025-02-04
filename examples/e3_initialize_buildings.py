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
    data = Datahandler()

    # Generate Environment for the District
    data.generateEnvironment()

    # We initialize the buildings of the district. As input the name of a scenario file is required.
    # In this example we use the existing example-file example.csv with two buildings.
    # This file contains the basic information about the buildings: building type, construction year, retrofit level
    # and floor area. This file is the only required input that the user must provide.
    # The following four building types can be used: Single-family house (SFH), multi-family house (MFH),
    # apartment block (AB) and terraced house (TH). Important to note that the abbreviations must be entered.
    # The retrofit level can be 0 (original construction state), 1 (Retrofit according to EnEV 2016)
    # or 2 (Retrofit according to KfW 55).
    # The construction year can be chosen between 1860 and 2024.
    # The floor area can be freely selected.
    data.initializeBuildings(scenario_name="example")

    ### =====================================  Output  ===================================== ###
    # The district consists of a list of two buildings with id 0 and 1 (see "data.district").
    # To every building the building features from example.csv are added.

    return data


if __name__ == '__main__':
    data = example3_initialize_buildings()


