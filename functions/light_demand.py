# Function to calculate the light demand for non-residential buildings
# in Residential Buildings this has been solved by RichardsonPy 
# Check whether lighning demand is given, with checking for occupancy, 
# irridance and window area of a building
# Code is orginally written for DIBS and adjusted here 

import os
import pandas as pd
import numpy as np
import functions.schedule_reader as schedule_reader




def get_lightning_load(building_type):
    """
    Get the lighning load from data\consumption_data\internal_loads.csv
    In 18599 loads are calculated per zone. In file 09, there is an approach to calculate lighning demand.
    However, at urban scale this is not feasibale, due to lack of information. 
    For example kind of lighning. Hence, we use the factors from CEA, El_Wm2. 
    """

    #data_type = _assignment.get(building_type)
    data_type = schedule_reader.getBuildingType(kind='CEA', term=building_type)
    if data_type is None:
        print(f"No schedule for building type {building_type}")
        return None, None
   
    data_dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

    load_data_path = os.path.join(data_dir_path, 'data', 'consumption_data', 'internal_loads.csv')


    try:
        load_data = pd.read_csv(load_data_path, sep=';', decimal=',')
        lighntning_control = load_data[load_data["cea_code"] == data_type]["El_Wm2"].iloc[0]

        return  lighntning_control
    except FileNotFoundError:
        print(f"File not found: {load_data_path}")
        return None
    except IndexError:
        print(f"No data about lighntning load available for {building_type}")
        return None



def get_lightning_control(building_type):
    """
    Get Lichtausnutzungsgrad der Verglasung (lighting_control), 
    Lux threshold at which the light turns on
    Map 'E_m' from data_18599_10_4 to building_data

    """ 

    # data_type = _assignment.get(building_type)
    data_type = schedule_reader.getBuildingType(kind='18599', term=building_type)
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
        print(f"No data for light demand available for {building_type}")
        return None


def calculate_light_demand(building_type, occupancy_schedule, illuminance, area):
    """
    Calculates the lighting demand for a building based on illuminance, occupancy, and area.
    
    References:
    Szokolay, S.V. (1980): Environmental Science Handbook for Architects and Builders. 
    Unknown Edition, The Construction Press, Lancaster/London/New York, ISBN: 0-86095-813-2, p. 105ff.
    Szokolay, S.V. (2008): Introduction to Architectural Science. The Basis of Sustainable Design. 
    2nd Edition, Elsevier/Architectural Press, Oxford, ISBN: 978-0-7506-8704-1, p. 154ff.

    :param building_type: The type of building (affects lighting load and control)
    :type building_type: str
    :param occupancy_schedule: Probability of full occupancy at each time step
    :type occupancy_schedule: pd.Series
    :param illuminance: Illuminance transmitted through the window [Lumens] for each side of the building
    :type illuminance: list of pd.Series
    :param area: Area of the space [m^2]
    :type area: float
    
    :return: Lighting Energy Required for the timestep
    :rtype: pd.Series
    """
    # This code calculates the lighting demand for a building based on various factors:

    # If illuminance is a list of Series (representing different facades), it's combined.
    # If it's a numpy array, it's summed and converted to a pandas Series.
    if isinstance(illuminance, list):
        illuminance = pd.concat(illuminance, axis=1).sum(axis=1)
    if isinstance(illuminance, np.ndarray):
        total_illuminance = np.sum(illuminance, axis=0)
        illuminance = pd.Series(total_illuminance, index=occupancy_schedule.index)

    lighting_load = get_lightning_load(building_type)  # Lighting power density (W/m2)
    lighting_control = schedule_reader.get_lightning_control(building_type)  # Illuminance threshold (lux)
    lighting_maintenance_factor = get_lighting_maintenance_factor(building_type)  # Maintenance factor

    # 0.45 is a light utilization factor according to Jayathissa 2020 and DIBS
    # Jayathissa, D. (2020): https://github.com/architecture-building-systems/RC_BuildingSimulator
    lux = (illuminance * 0.45 * lighting_maintenance_factor) / area

    # Lighting is needed when lux is below the threshold and the space is occupied
    mask = (lux < lighting_control) & (occupancy_schedule["OCCUPANCY"] > 0)

    lighting_demand = pd.Series(0.0, index=occupancy_schedule.index)
    # Calculate demand only when lighting is needed (mask is True)
    lighting_demand[mask] = lighting_load * area * occupancy_schedule["OCCUPANCY"][mask]
    lighting_demand[~mask] = 0

    return lighting_demand  # Return the calculated lighting demand (in watts)


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
        "IWU Office, Administrative or Government Buildings": "Bürogebäude",
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
    if (data_type == 'Produktions-, Werkstatt-, Lager- oder Betriebsgebäude' or
        data_type == 'IWU Generalized (2) Production buildings' or
        data_type == 'Gewerbliche und industrielle Gebäude – Mischung aus leichter u. schwerer Arbeit'):
        lighting_maintenance_factor = 0.8
    else:
        lighting_maintenance_factor = 0.9
    return lighting_maintenance_factor
