# -*- coding: utf-8 -*-


"""
This is the second example to create the environment of the district.

If you run the examples with Python console, you can see the output file.
To do this right-hand click the example.py file (e2_generate_environment.py).
Then choose 'Modify Run Configuration' and tick 'Run with Python Console'.
"""

# Import classes of the districtgenerator to be able to use the district generator.
from districtgenerator.classes import *

def example2_generate_environment():

    # Initialize District (description in the first example)
    data = Datahandler()

    # Generate Environment for the District with Data from districtgenerator/data/site_data.json
    # and districtgenerator/data/time_data.json
    data.generateEnvironment()

    ### =====================================  Output  ===================================== ###
    # Based on the location of the district the environment includes outside temperatures and
    # sun radiation. When you open "data.site" (data from districtgenerator/data/site_data.json),
    # you see the "location" is [51.0,6.55], the "climateZone" 0 and the "altitude" 0. The weather
    # data is taken from a test reference year database from the DWD. You find the time resolution
    # in "data.time" (data from districtgenerator/data/time_data.json).
    # For this example it is 900 seconds, which is equal to 15 Minutes.

    print("The environment for the district is generated.")
    print("In data.site['T_e'] for example you find the outside temperature. Get the first 10 values:")
    print(data.site['T_e'][:10])
    print("In data.time['timeSteps'] you find the number of time steps in a year:")
    print(data.time['timeSteps'])
    print("The list for the buildings is still empty:")
    print(data.district)

    return data


if __name__ == '__main__':
    data = example2_generate_environment()


