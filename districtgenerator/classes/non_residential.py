# created Sep 2024

import os
import json
from dataclasses import dataclass
from typing import List

# This Class is responsible for the envelope generation + behavior configuration for non-residential buildings

class NonResidential(object):
    """Base class for each non-residential archetype.

    This is the base class for all non-residential archetype buildings.
    The setup is similiar to TEASER, considering that there are no information about layers and 
    details about material available. The class provides the necessary information for the districtgenerator.

    Teaser uses typical layers and material for the build environment according to MASEA ( https://www.masea-ensan.de/ ).
    Currently, the gathering and combinatory selection of this is not feasible. 

    Several parameters are obligatory: name, year_of_construction, net_leased_area, type.

    In accordance with TEASER it is assumed, that each building has four orientations of outer walls and windows (north,
    east, south and west)

    In TEASER it is assumed,  that the surface is the product of the given net_leased_area and specific estimation factors. These
    estimation factors where build by dividing the given 'surface area' by the 'reference floor area' in TABULA. The same approach is followed here. 

    Obliagotry Parameters
    ----------

    name : str
        Individual name
    year_of_construction : int
        Year of first construction
    net_leased_area : float [m2]
            Total net leased area of the building, or of the building part if it is a mixed-use building. This is area is NOT the footprint of a building
    total_building_area : float [m2]
            Total net leased area of building. This is area is NOT the footprint of a building
    usage: str 
        Type of the building, according to Data NWG. Options are: "oag", "rnt", "hlc", "sdc", "clt", "spf", "hbr", "pwo", "trd", "tud", "trs", "gs1", "gs2"

    Attributes
    ----------
    height_of_floors : float [m]
        Average height of the floors (default: None)
    outer_area : dict [degree: m2]
        Dictionary with orientation as key and sum of outer wall areas of
        that direction as value.
    window_area : dict [degree: m2]
        Dictionary with orientation as key and sum of window areas of
        that direction as value.
    volume : float [m3]
        Total volume.
    """

    def __init__(
        self,
        name,
        year_of_construction,
        net_leased_area,
        total_building_area,
        usage,  
        height_of_floors,
        construction_type,
        retrofit_level,
    ):
        self.name = name 
        self.year_of_construction = year_of_construction
        self.net_leased_area = float(net_leased_area)
        self.total_building_area = float(total_building_area)
        self.usage = usage 
        self.height_of_floors=float(height_of_floors)
        self.construction_type = construction_type
        self.retrofit_level = retrofit_level

        # Validate construction_type
        valid_construction_types = ["Light", "Medium", "Heavy", "Tabula"]
        if construction_type and construction_type not in valid_construction_types:
            raise ValueError(f"Invalid construction_type '{construction_type}'. Must be one of {valid_construction_types}.")
        
        # check Orientation
        self.volume = self.calculate_volume()
        self.parameters = self.load_building_data()
        self.facade_estimation_factors = self.load_surface_estimation_factors()

        # [tilt, orientation]
        self._outer_wall_names = {
            "Exterior Facade North": [90.0, 0.0],
            "Exterior Facade East": [90.0, 90.0],
            "Exterior Facade South": [90.0, 180.0],
            "Exterior Facade West": [90.0, 270.0],
        }

        self._roof_names = {"Rooftop": [0, -1]}

        self._ground_floor_names = {"Ground Floor": [0, -2]}

        self._window_names = {
            "Window Facade North": [90.0, 0.0],
            "Window Facade East": [90.0, 90.0],
            "Window Facade South": [90.0, 180.0],
            "Window Facade West": [90.0, 270.0],
        }
        # no information about the door, inner walls, or ceiling in the archetype
        # Hence No self.door_names, self.inner_wall_names, self.ceiling_names are given
        # As there is no TABULA Classes present
        
        self.outer_area = {}
        self.window_area = {}
        self.outer_wall = {}
        self.generate_archetype()

    def generate_archetype(self):
        """
        Generates an archetype building.

        Adaption of TEASER archetype generation for Non-Residential Building Typology.
        """

        # Outer walls
        if self.facade_estimation_factors["ow1"] != 0:
            for key, value in self._outer_wall_names.items():
                self.outer_area[key] = {}  
                self.outer_area[key]["name"] = key
                self.outer_area[key]["tilt"] = value[0]
                self.outer_area[key]["orientation"] = value[1]
                self.outer_area[key]["area"] = (self.facade_estimation_factors["ow1"] * self.net_leased_area) / len(self._outer_wall_names)

        # Windows
        if self.facade_estimation_factors["win1"] != 0:
            for key, value in self._window_names.items():
               self.window_area[key] = {}
               self.window_area[key]["name"] = key
               self.window_area[key]["tilt"] = value[0]
               self.window_area[key]["orientation"] = value[1]
               self.window_area[key]["area"] = (self.facade_estimation_factors["win1"] * self.net_leased_area) / len(self._window_names)

        # Ground floor
        if self.facade_estimation_factors["gf1"] != 0:
            for key, value in self._ground_floor_names.items():
                self.outer_area[key] = {}
                self.outer_area[key]["name"] = key
                self.outer_area[key]["tilt"] = value[0]
                self.outer_area[key]["orientation"] = value[1]
                self.outer_area[key]["area"] = (self.facade_estimation_factors["gf1"] * self.total_building_area) / len(self._ground_floor_names)

        # Rooftop
        if self.facade_estimation_factors["rt1"] != 0:
            for key, value in self._roof_names.items():
                self.outer_area[key] = {}
                self.outer_area[key]["name"] = key
                self.outer_area[key]["tilt"] = value[0]
                self.outer_area[key]["orientation"] = value[1]
                self.outer_area[key]["area"] = (self.facade_estimation_factors["rt1"] * self.total_building_area) / len(self._roof_names)

    def calculate_volume(self):
        return self.net_leased_area * self.height_of_floors

    def load_surface_estimation_factors(self):
        """
        Load surface estimation factors data from a JSON file
        # rt - rooftop
        # ow - outer wall 
        # gf - ground floor
        # win - window 
       
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
        DATA_PATH = os.path.join(DATA_DIR_PATH, 'data', 'non_residential', 'surface_estimation_factors.json')
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
        DATA_PATH = os.path.join(DATA_DIR_PATH, 'data', 'non_residential', 'non_residential_envelope.json')
        with open(DATA_PATH, 'r', encoding='utf-8') as file:
            data = json.load(file)

        # Validate if the archetype exists in the data
        if self.usage not in data:
            raise ValueError(f"Archetype '{self.usage}' not found in the data.")
    
        # Get the building age groups for the specified archetype
        age_groups = data[self.usage]["building_age_group"]

        # Validate if the year_of_construction falls within any age group
        for age_range, retrofit_data in age_groups.items():
            start_year, end_year = map(int, age_range.split(' - '))
            if start_year <= self.year_of_construction <= end_year:
                for retrofit_level, parameters in retrofit_data.items():
                    if self.retrofit_level == retrofit_level:
                        return parameters

          # If no matching age group is found
        raise ValueError(f"Year of construction '{self.year_of_construction}' not found in any age group for archetype '{self.usage}'.")
    
@dataclass
class NonResidentialConfig:
    # Basic configuration parameters to be provided for the generation of a non-residential building
    working_days: List[int] # List of integers representing the working days of the week (0 for Monday, 1 for Tuesday, ..., 6 for Sunday)
    main_zone_name: str
    main_room_zones: List[str] # List of zone names that are considered as main zones for occupancy calculations.
    affected_by_holidays: bool # if the building schedule is affected by holidays or not.
    app_gain_factor: float | None # If not specified, the standard value is used. This factor represents the fraction of the electrical power of appliances that is converted into internal heat gains
    car_commute_ratio: float | None # If not specified, the standard value for Germany is used. This ratio represents the fraction (0–1) of occupants who commute to the building by car. This factor is multiplied by the number of occupants to estimate the number of cars associated with commuting to the building
    has_ventilation: bool # Indicates whether the building has mechanical ventilation.
    min_illuminance: int # Minimum required illuminance in lux.
    max_illuminance: int # Maximum required illuminance in lux.
    affected_by_school_holidays: bool # if the building occupancy drops during school holidays.
    lighting_irradiance_threshold_mean: float | None # Mean global irradiance (W/m²) below which lighting is likely to be switched on.
    lighting_irradiance_threshold_std_dev: float | None  # Standard deviation of the irradiance threshold, representing variability in lighting behavior.

class GenericNonResidential:
    """
    Function to handle non-residential buildings. This class defines how a non-residential building behaves.
    """

    _behavior_data_cache = None


    def __init__(self, usage_string: str):
        self.usage_string = usage_string
        self.config = self._load_config()

    def _load_config(self) -> NonResidentialConfig:
        """Load behavior config from cache or file."""
        DATA_DIR_PATH = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        data_path = os.path.join(DATA_DIR_PATH, 'data', 'non_residential', 'non_residential_behavior.json')
        if GenericNonResidential._behavior_data_cache is None:
            with open(data_path, 'r', encoding='utf-8') as file:
                GenericNonResidential._behavior_data_cache = json.load(file) # Cache the data after loading it for the first time to avoid redundant file reads in subsequent calls.

        data = GenericNonResidential._behavior_data_cache

        if self.usage_string not in data:
            raise ValueError(f"NWG '{self.usage_string}' not found in JSON. path: {data_path}")

        return NonResidentialConfig(**data[self.usage_string])

    def get_working_days(self) -> List[int]:
        """Get the working days for the non-residential building."""
        return self.config.working_days

    def get_main_zone_name(self) -> str:
        """Get the main zone name for occupancy calculations."""
        return self.config.main_zone_name

    def is_affected_by_holidays(self) -> bool:
        """Check if the building schedule is affected by holidays."""
        return self.config.affected_by_holidays

    def get_app_gain_factor(self) -> float:
        """Get the appliance heat gain factor."""
        return self.config.app_gain_factor

    def get_car_commute_ratio(self) -> float | None:
        """Get the car commute ratio for non-residential buildings, if specified."""
        return getattr(self.config, 'car_commute_ratio', None)

    def get_main_room_zones(self) -> List[str]:
        """Get the list of main room zones for occupancy calculations."""
        return self.config.main_room_zones

    def get_ventilation(self) -> bool:
        """Get if building is ventilated"""
        return self.config.has_ventilation

    def get_min_illuminance(self) -> int:
        """Get the minimum required illuminance in lux."""
        return self.config.min_illuminance

    def get_max_illuminance(self) -> int:
        """Get the maximum required illuminance in lux."""
        return self.config.max_illuminance

    def is_affected_by_school_holidays(self) -> bool:
        """Check if the building occupancy drops during school holidays."""
        return self.config.affected_by_school_holidays

    def get_lighting_irradiance_threshold(self) -> tuple[float, float]:
        """Get the mean and standard deviation of the global irradiance threshold for lighting in W/m2."""
        return self.config.lighting_irradiance_threshold_mean, self.config.lighting_irradiance_threshold_std_dev
