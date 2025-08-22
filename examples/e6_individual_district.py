# -*- coding: utf-8 -*-

"""
This is the sixth example to change specific assumptions about the district.

This method allows for storing and managing separate, versionable configurations without altering the tool's
default data. How to use multiple configurations will be explained in example nine.

If you run the examples with Python console, you can see the output file.
To do this right-hand click the example.py file (e6_individual_district.py).
Then choose 'Modify Run Configuration' and tick 'Run with Python Console'.
"""

# Import the Datahandler class to use the district generator.
from districtgenerator.classes import Datahandler

def example6_config_file_loading():
    ###  To run this example, you will need to edit an existing configuration file.

    # In the data-Folder should be a file called '.env.CONFIG.FREIBURG'. Open this file and ensure the following
    # parameters are set to run the desired scenario. The default file which you should not alter or delete is the
    # '.env.CONFIG.EXAMPLE'. Use this only as a reference for the parameters you can change, always create a new file
    # to store your custom configuration, such as '.env.CONFIG.FREIBURG'. You can store this file in a different
    # location, but you will need to provide the absolute path to it when initializing the Datahandler.

    # Changes are to be made in the '.env.CONFIG.FREIBURG' file. You can delete all other parameters that
    # are not relevant. Try searching the parameters in the file to find the ones you need to change.
    # If you need a description of the parameters, refer to the documentation in the config.py,
    # decentral_devices_config.py, or central_devices_config.py files.

    # In this example we use the existing example-file freiburg.csv with four buildings.

    # 1. Changing the location and weather data:
    #    To set the district's location to Freiburg im Breisgau and use the warm
    #    test reference year for 2045, adjust the following parameters:
    #    - zip=79100
    #    - TRYYear=TRY2045
    #    - TRYType=warm

    # 2. Change the minimum indoor temperature:
    #    To modify the building's thermal properties, locate the T_set_min
    #    parameter and set its value:
    #    - T_set_min=18.0

    # 3. Changing the time resolution:
    #    To change the time resolution of the generated profiles to three hours,
    #    set the timeResolution parameter in seconds:
    #    - timeResolution=10800
    # That is equal to a time resolution of three hours.
    # Be careful to not delete the coma behind the value! Safe and close the file.

    # Initialize District
    data = Datahandler(env_path=".env.CONFIG.FREIBURG")
    # Alternative if you need an absolute path:
    # data = Datahandler(env_path="/path/to/your/.env.CONFIG.FREIBURG")

    # Generate Environment for the District
    data.generateEnvironment()

    # Initialize Buildings to the District
    data.initializeBuildings()

    # Generate more detailed Building models
    data.generateBuildings()

    # Now we generate building specific demand profiles with the adjusted assumptions
    data.generateDemands(calcUserProfiles=True, saveUserProfiles=True)

    ### ===========================================  Output  =========================================== ###
    # Have a look at the results, e.g. in data.site you can see the changed zip code.

    return data


if __name__ == '__main__':
    data = example6_config_file_loading()