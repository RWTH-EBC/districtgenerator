# -*- coding: utf-8 -*-

"""
This is the first example to initialize a district.

If you run the examples with Python console, you can see the output file.
To do this right-hand click the example.py file (e1_initialize_datahandler.py).
Then choose 'Modify Run Configuration' and tick 'Run with Python Console'.
"""

# Import classes of the districtgenerator to be able to use the district generator.
from districtgenerator.classes import *

def example1_initialize_datahandler():

    # To create a district we initialize the datahandler.
    # No input is required for this step.
    data = Datahandler()

    ### =====================================  Output  ===================================== ###
    # This creates the datahandler object and empty files for information about the environment,
    # the buildings and the district.

    return data


if __name__ == '__main__':
    data = example1_initialize_datahandler()


