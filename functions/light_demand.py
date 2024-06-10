# Function to calculate the light demand for non-residential buildings
# in Residential Buildings this has been solved by RichardsonPy 
# Check whether lighning demand is given, with checking for occupancy, 
# irridance and window area of a building
# Code is orginally written for DIBS and adjusted here 

import os
import pandas as pd
import functions.schedule_reader as schedule_reader




def get_lighntning_load(building_type):
    """
    Get the lighning load from data\consumption_data\internal_loads.csv
    In 18599 loads are calculated per zone. In file 09, there is an approach to calculate lighning demand.
    However, at urban scale this is not feasibale, due to lack of information. 
    For example kind of lighning. Hence, we use the factors from CEA, El_Wm2. 
    """

    #data_type = _assignment.get(building_type)
    data_type = schedule_reader.get_building_type(kind='18599', term=building_type)
    if data_type is None:
        print(f"No schedule for building type {building_type}")
        return None, None
   
    data_dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

    load_data_path = os.path.join(data_dir_path, 'data', 'consumption_data', 'internal_loads.csv')


    try:
        print(f"This is the path: {load_data_path}"
              )
        load_data = pd.read_csv(load_data_path, sep=';', decimal=',')
        print(load_data, "Tjtit")
        lighntning_control = load_data[load_data["building_type"] == data_type]["El_Wm2"].iloc[0]

        return  lighntning_control
    except FileNotFoundError:
        print(f"File not found: {load_data_path}")
        return None
    except IndexError:
        print(f"No data available for {building_type}")
        return None



def get_lightning_control(building_type):
    """
    Get Lichtausnutzungsgrad der Verglasung (lighting_control), 
    Lux threshold at which the light turns on
    Map 'E_m' from data_18599_10_4 to building_data

    """ 

    # data_type = _assignment.get(building_type)
    data_type = schedule_reader.get_building_type(kind='18599', term=building_type)
    if data_type is None:
        print(f"No schedule for building type {building_type}")
        return None, None
   
    data_dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    maintenance_data_path = os.path.join(data_dir_path, 'data', 'norm_profiles', '18599_10_4_data.csv')


    try:
        maintenance_data_schedule = pd.read_csv(maintenance_data_path, sep=';')

        lighntning_control = maintenance_data_schedule[maintenance_data_schedule["typ_18599"] == data_type]["E_m"].iloc[0]

        return  lighntning_control
    except FileNotFoundError:
        print(f"File not found: {maintenance_data_path}")
        return None
    except IndexError:
        print(f"No data available for {building_type}")
        return None

def calculate_light_demand(building_type, 
                           occupancy, 
                           illuminance,
                           area,
                           ):
       """
        Calculates the lighting demand for a series. 
        
        Daylighting is based on methods in 
        Szokolay, S.V. (1980): Environmental Science Handbook vor architects and builders. Unknown Edition, The Construction Press, Lancaster/London/New York, ISBN: 0-86095-813-2, p. 105ff.
        respectively
        Szokolay, S.V. (2008): Introduction to Architectural Science. The Basis of Sustainable Design. 2nd Edition, Elsevier/Architectural Press, Oxford, ISBN: 978-0-7506-8704-1, p. 154ff.

        Idea is taken and adapted from DIBS by vectorization and adoption of variables.

        :param illuminance: Illuminance transmitted through the window [Lumens]
        :type illuminance: float
        :param occupancy: Probability of full occupancy
        :type occupancy: float

        :return: self.lighting_demand, Lighting Energy Required for the timestep
        :rtype: float

        """
       # | `El_Wm2` |  Peak specific electrical load due to artificial lighting (refers to “code”)| DIN V 18599-4 Anhang B (Abbildung B.12) =  6,4 W/m²  |
       # lighting_load = data_schedule[data_schedule["TEK"] == data_type]["TEK Warmwasser"].iloc[0]
       # To-Do: figure better assumptions for lighning-load 
       # To-Do: figure lighning_control
       lighting_load = get_lighntning_load(building_type) # W/m2 get_lighning_control
       lighting_utilisation_factor = 0.45 # According to DIBS and Jayathissa, P. (2020). 5R1C Building Simulation Model. url: https://github.com/architecture-building-systems/RC_BuildingSimulator (besucht am 22. 03. 2020)
       #To-Do: dobule check, whether lighting_control or 
       lighting_control = get_lightning_control(building_type=building_type)
       lightning_maintenance_factor  = get_lighting_maintenance_factor(building_type=building_type)
       print(occupancy)
       
       lighting_demand = pd.Series(0, index=occupancy.index)
       lux = (illuminance * lighting_utilisation_factor * lightning_maintenance_factor) / area
       mask = (lux < lighting_control) & (occupancy > 0)
       lighting_demand[mask] = lighting_load * area * occupancy[mask]
       return lighting_demand




# Wartungsfaktor der Fensterflächen (lighting_maintenance_factor) 
##############################################################################
# See Szokolay (1980): Environmental Science Handbook for Architects and Builders, p. 109
def get_lighting_maintenance_factor(building_type):
    """
    Wartungsfaktor der Fensterflächen (lighting_maintenance_factor) 
    See Szokolay (1980): Environmental Science Handbook for Architects and Builders, p. 109
    Taken from DIBS, where dirty is assumed for every production related building type 
    and clean is assumed for all other building types
    """
    _assignment = {
        "oag": "Bürogebäude",
        "IWU Research and University Teaching": "Hochschule und Forschung (allgemein)",
        "IWU Health and Care": "Beherbergungsstätten (allgemein)",
        "IWU School, Day Nursery and other Care": "Schulen",
        "IWU Culture and Leisure": "Ausstellungsgebäude",
        "IWU Sports Facilities": "Sporthallen",
        "IWU Hotels, Boarding, Restaurants or Catering": "Hotels / Pensionen",
        "IWU Production, Workshop, Warehouse or Operations": "Gewerbliche und industrielle Gebäude – Mischung aus leichter u. schwerer Arbeit",
        "IWU Trade Buildings": "Verkaufsstätten (allgemein)",
        "IWU Generalized (1) Services building": "Verwaltungsgebäude (allgemein)",
        "IWU Generalized (2) Production buildings": "Gewerbliche und industrielle Gebäude – Mischung aus leichter u. schwerer Arbeit"
    }
    data_type = _assignment.get(building_type)
    if data_type == 'Produktions-, Werkstatt-, Lager- oder Betriebsgebäude' or '"IWU Generalized (2) Production buildings"':
        lighting_maintenance_factor = 0.8
    else:
        lighting_maintenance_factor = 0.9
    return lighting_maintenance_factor 

