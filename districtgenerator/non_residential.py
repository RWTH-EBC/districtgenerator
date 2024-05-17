# created May 2024 
# by Felix Rehmann 

import os
import json


class NonResidential(object):
    """Base class for each non-residential archetype.

    This is the base class for all non-residential archetype buildings according to data NWG.
    The setup is similiar to TEASER, considering that there are no information about layers and 
    details about material available. The class provides the necessary information for the districtgenerator. 

    These are:
        - prj.data.material_bind -> No data available for non-residential Archetypes
        - prj.data.element_bind - -> No data available for non-residential Archetypes
        - prj.buildings[self.id].volume 
        - prj.buildings[self.id].outer_area
        - prj.buildings[self.id].window_area -> has to be caculated, as it is not present in data NWG.

    Teasers uses typical layers and material for the build envrionment according to MASEA ( https://www.masea-ensan.de/ ). 
    Currently, the gathering and combinatory selection of this is not feasible. 

    Several parameters are are obligatory: name, year_of_construction, net_leased_area, type.
    
    Other parameters are optional, and are implemented to provide further options for configuration. 

    In accordance with TEASER it is assumed, that each building has four orientations of outer walls and windows (north,
    east, south and west), two orientations for rooftops (south and north), 
    with tilt of 35 degree and one orientation for ground floors and one door (default orientation is west).

    In TEASER it is assumed,  thath the surface is the product of the given net_leased_area and specific estimation factors. These
    estimation factors where build by dividing the given 'surface area' by the 'reference floor area' in TABULA. The same approach is followed here. 
    The factors are given in: 
        - 

    Obliagotry Parameters
    ----------

    name : str
        Individual name
    year_of_construction : int
        Year of first construction
    net_leased_area : float [m2]
        Total net leased area of building. This is area is NOT the footprint
        of a building
    usage: str 
        Type of the building, according to Data NWG. Options are: "oag", "rnt", "hlc", "sdc", "clt", "spf", "hbr", "pwo", "trd", "tud", "trs", "gs1", "gs2"
    
        
    Optional Parameters
    ------------- 

    street_name : string
        Name of the street the building is located at. (optional)
    city : string
        Name of the city the building is located at. (optional)
    longitude : float [degree]
        Longitude of building location.
    latitude : float [degree]
        Latitude of building location.

    Attributes
    ----------
    central_ahu : instance of BuildingAHU
        Teaser Instance of BuildingAHU if a central AHU is embedded into the
        building (currently mostly needed for AixLib simulation).
    number_of_floors : int
        number of floors above ground (default: None)
    height_of_floors : float [m]
        Average height of the floors (default: None)
    internal_id : float
        Random id for the distinction between different buildings.
    year_of_retrofit : int
        Year of last retrofit.
    type_of_building : string
        Type of a Building (e.g. Building (unspecified), Office etc.).
    building_id : None
        ID of building, can be set by the user to keep track of a building
        even outside of TEASER, e.g. in a simulation or in post-processing.
        This is not the same as internal_id, as internal_id is e.g. not
        exported to Modelica models!
   
    thermal_zones : list
        List with instances of ThermalZone(), that are located in this building.
    outer_area : dict [degree: m2]
        Dictionary with orientation as key and sum of outer wall areas of
        that direction as value.
    window_area : dict [degree: m2]
        Dictionary with orientation as key and sum of window areas of
        that direction as value.
    bldg_height : float [m]
        Total building height.
    volume : float [m3]
        Total volume of all thermal zones.
    sum_heat_load : float [W]
        Total heating load of all thermal zones.
    sum_cooling_load : float [W]
        Total heating load of all thermal zones. (currently not supported)
    number_of_elements_calc : int
        Number of elements that are used for thermal zone calculation in this
        building.

        1. OneElement
        2. TwoElement
        3. ThreeElement
        4. FourElement

    merge_windows_calc : boolean
        True for merging the windows into the outer wall's RC-combination,
        False for separate resistance for window, default is False
    used_library_calc : str
        'AixLib' for https://github.com/RWTH-EBC/AixLib
        'IBPSA' for https://github.com/ibpsa/modelica
    library_attr : Annex() or AixLib() instance
        Classes with specific functions and attributes for building models in
        IBPSA and AixLib. Python classes can be found in calculation package.

        self.volume = volume
        

    """

    def __init__(
        self,
        name,
        year_of_construction,
        net_leased_area,
        usage,  
        number_of_floors,
        height_of_floors,
        construction_type = "Tabula", 
    ):
        self.name = name 
        self.year_of_construction = year_of_construction
        self.net_leased_area = float(net_leased_area)
        self.usage = usage 
        self.height = None
        self.number_of_floors=float(number_of_floors)
        self.height_of_floors=float(height_of_floors)

        # Validate construction_type
        valid_construction_types = ["Light", "Medium", "Heavy", "Tabula"]
        if construction_type and construction_type not in valid_construction_types:
            raise ValueError(f"Invalid construction_type '{construction_type}'. Must be one of {valid_construction_types}.")
        
        # check Orientation 
        


        self.volume = self.calculate_volume()
        self.parameters = self.load_building_data()
        self.facade_estimation_factors = self.load_surface_estimation_factors()

        self.outer_wall_names = {
            "Exterior Facade North": [90.0, 0.0],
            "Exterior Facade East": [90.0, 90.0],
            "Exterior Facade South": [90.0, 180.0],
            "Exterior Facade West": [90.0, 270.0],
        }
        # [tilt, orientation]

        self.roof_names = {"Rooftop": [0, -1]}  # [0, -1]

        self.ground_floor_names = {"Ground Floor": [0, -2]}  # [0, -2]

        self.window_names = {
            "Window Facade North": [90.0, 0.0],
            "Window Facade East": [90.0, 90.0],
            "Window Facade South": [90.0, 180.0],
            "Window Facade West": [90.0, 270.0],
        }
    
    def generate_archetype(self):
        """Generates an archetype building.

        
        If you want to define you own archetype methodology please use this
        function call to do so.

        """

        pass

    def calculate_volume(self):
        self.volume = self.net_leased_area * self.number_of_floors * self.height_of_floors

    def load_surface_estimation_factors(self):
        """
        Load surface estimation factors data from a JSON file

       
        Returns
        -------
        dict
            Dictionary with the surface estimation factors:
            {
                'rt1': 0.625,
                'ow1': 0.77604,
                'gf1': 0.625,
                'win1': 0.18854
                }
        """
        DATA_DIR_PATH = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        DATA_PATH = os.path.join(DATA_DIR_PATH, 'data', 'non_residential_envelope', 'suface_estimation_factors.json')
        with open(DATA_PATH, 'r', encoding='utf-8') as file:
            data = json.load(file)
    
        # Validate if the archetype exists in the data
        if self.usage not in data:
            raise ValueError(f"Archetype '{self.usage}' not found in the data.")
    
        # Get the building age groups for the specified archetype
        age_groups = data[self.usage]["building_age_group"]
        
        # Validate if the year_of_construction falls within any age group
        for age_range, parameters in age_groups.items():
            start_year, end_year = map(int, age_range.split(' - '))
            if start_year <= self.year_of_construction <= end_year:
                return parameters

    
    def load_building_data(self):
        """
        Load building data from a JSON file

        Parameters
        ----------
        file_path : str
            Path to the JSON file

        Returns
        -------
        dict
            Dictionary with the building data
        """
        DATA_DIR_PATH = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        DATA_PATH = os.path.join(DATA_DIR_PATH, 'data', 'non_residential_envelope', 'non_residential_envelope.json')
        with open(DATA_PATH, 'r', encoding='utf-8') as file:
            data = json.load(file)
    
        # Validate if the archetype exists in the data
        if self.usage not in data:
            raise ValueError(f"Archetype '{self.usage}' not found in the data.")
    
        # Get the building age groups for the specified archetype
        age_groups = data[self.usage]["building_age_group"]
        
        # Validate if the year_of_construction falls within any age group
        for age_range, parameters in age_groups.items():
            start_year, end_year = map(int, age_range.split(' - '))
            if start_year <= self.year_of_construction <= end_year:
                return parameters

          # If no matching age group is found
        raise ValueError(f"Year of construction '{self.year_of_construction}' not found in any age group for archetype '{self.bldg_type}'.")
                