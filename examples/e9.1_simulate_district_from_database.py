# -*- coding: utf-8 -*-

"""
Next step: create an environment.
"""

# Import classes of the districtgenerator to be able to use the district generator.
from districtgenerator import *

def example9_1simulate_district_from_database():

    # Initialize District
    data = Datahandler()

     # Set a custom weather file 
    # This need to be EPW, if used with Non-Residential Buildings. 
    #weather_file = os.path.join(os.path.dirname(__file__), 'data', 'weather', 'EWP' , 'DEU_BE_Berlin-Schonefeld.AP.103850_TMYx.2004-2018.epw')
    data.setWeatherFile('data/weather/EPW/DEU_BE_Berlin-Schonefeld.AP.103850_TMYx.2004-2018.epw')

    # Next we generate an environment.
    # Based on the location of the district this includes outside temperatures and sun radiation.
    # The location can be changed in the site_data.json file. You find it in \data.
    # We create our first district in Aachen. When you open the site_data.json file, you should see, the "location"
    # is [51.0,6.55], the "climateZone" 0 and the "altitude" 0.
    # The time resolution can be changed in time_data.json. You also find it in \data.
    # For this example it should be 900 seconds, which equals 15 Minutes.
    # The weather data is taken from a Test Reference Year Database from the DWD.

    # Generate Environment for the District
    
    data.generateEnvironment()

    data.initializeBuildings('example_mix_used')
    data.generateBuildings()

    # Now Analyze the data that is returned
    print(vars(data))
    #data.generateDemands()
    breakpoint()
    

  
  
    return data 



if __name__ == '__main__':
     print("Let's generate a mixed use district!")
     
     data = example9_1simulate_district_from_database()
