# -*- coding: utf-8 -*-

"""
This is the first example to initialize a district.

If you run the examples with Python console, you can see the output file.
To do this right-hand click the example.py file (e1.0_generate_first_district.py).
Then choose 'Modify Run Configuration' and tick 'Run with Python Console'.
"""

# Import classes of the districtgenerator to be able to use the district generator.
from districtgenerator.classes import *

def example1_0_generate_first_district():

    # To create a district we initialize the Datahandler.
    # No input is required for this step.
    data = Datahandler()

    # This creates empty files for information about the environment, the buildings and the district.


    print("\nOur District now looks like this: \n")
    print("District:" + str(data.district))
    print("Site:" + str(data.site))
    print("There is no data yet.\n"
          "Lets try the next example e1.1_generate_first_district "
          "to add information about the environment of our district.")

    return data


if __name__ == '__main__':
    data = example1_0_generate_first_district()


