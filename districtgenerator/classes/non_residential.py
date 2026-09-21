# created Sep 2024
"""Non-residential building archetypes and behavior configuration.

This module provides two complementary representations used by
DistrictGenerator:

* :class:`NonResidential` creates a simplified non-residential building
  archetype from use type, construction year, retrofit level, and floor area.
* :class:`GenericNonResidential` exposes use-specific behavioral assumptions
  loaded from ``non_residential_behavior.json``.

Envelope properties and surface-estimation factors are loaded from the
packaged JSON data in ``data/non_residential``. The implementation follows the
DistrictGenerator non-residential archetype approach and provides the geometry
and use-specific parameters required by the building, profile, and thermal
models.
"""
import os
import json
from dataclasses import dataclass
from typing import List

# This Class is responsible for non-residential envelope generation
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

    Parameters
    ----------
    name : str
        Individual building or building-part name.
    year_of_construction : int
        Year of first construction.
    net_leased_area : float
        Net leased area represented by this archetype in m². For a
        mixed-use building this can be the area of only the
        non-residential part.
    total_building_area : float
        Total net leased area of the complete building in m².
    usage : str
        Non-residential archetype identifier used to select packaged
        envelope and surface-estimation data.
    construction_type : {"Light", "Medium", "Heavy", "Tabula"}
        Construction type used by downstream thermal calculations.
    retrofit_level : str
        Retrofit-state identifier used to select envelope parameters
        for the applicable building-age group.
    number_of_floors : int or None, optional
        Number of building floors. If omitted, the ground-floor
        estimation factor is used to derive a representative
        one-floor area.
    is_mixed_part : bool, optional
        Whether the archetype represents the non-residential part of a
        mixed-use building. If ``True``, the roof area of this part is
        set to zero because another building part is assumed above it.
    """

    def __init__(self, name, year_of_construction, net_leased_area, total_building_area, usage,
                 construction_type, retrofit_level, number_of_floors = None, is_mixed_part = False):
        """
        Constructor of NonResidential class.

        """
        self.name = name 
        self.year_of_construction = year_of_construction
        self.net_leased_area = float(net_leased_area)
        self.total_building_area = float(total_building_area)
        self.usage = usage 
        self.construction_type = construction_type
        self.retrofit_level = retrofit_level
        self.number_of_floors = number_of_floors
        self.is_mixed_part = is_mixed_part

        # Validate construction_type
        valid_construction_types = ["Light", "Medium", "Heavy", "Tabula"]
        if construction_type and construction_type not in valid_construction_types:
            raise ValueError(f"Invalid construction_type '{construction_type}'. Must be one of {valid_construction_types}.")
        
        # Validate number_of_floors
        if number_of_floors is not None and (not isinstance(number_of_floors, int) or number_of_floors <= 0):
            raise ValueError(f"number_of_floors must be a positive integer.")

        # check Orientation
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
        Generate simplified external surface geometry for the archetype. Adaption of TEASER archetype
        generation for Non-Residential Building Typology.

        Populate ``outer_area`` and ``window_area`` from the loaded
        surface-estimation factors. External wall and window areas are
        distributed equally among four cardinal orientations; one ground
        floor and one roof surface are generated when the respective
        estimation factors are non-zero.

        Returns
        -------
        None
            The method modifies the instance in place.
        """

        if self.number_of_floors is None:
            one_floor_area = self.facade_estimation_factors["gf1"] * self.total_building_area # Use the ground floor estimation factor
        else:
            one_floor_area = self.total_building_area / self.number_of_floors # If the number of floors is given, calculate the area

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
                self.outer_area[key]["area"] = (one_floor_area) / len(self._ground_floor_names)

        # Rooftop
        if self.facade_estimation_factors["rt1"] != 0:
            for key, value in self._roof_names.items():
                self.outer_area[key] = {}
                self.outer_area[key]["name"] = key
                self.outer_area[key]["tilt"] = value[0]
                self.outer_area[key]["orientation"] = value[1]
                if self.is_mixed_part:
                    # If the building part is a mixed-use part, it is assumed that there is no roof area, as the residential part is located on top of the non-residential part.
                    self.outer_area[key]["area"] = 0.0
                else:
                    self.outer_area[key]["area"] = (self.facade_estimation_factors["rt1"]/self.facade_estimation_factors["gf1"] * one_floor_area) / len(self._roof_names)

    def load_surface_estimation_factors(self):
        """
        Load use- and age-specific surface-estimation factors.
        Read ``data/non_residential/surface_estimation_factors.json`` and
        select the parameter set corresponding to ``usage`` and
        ``year_of_construction``.

        Returns
        -------
        dict or None
            Surface-estimation factors for the matching building-age
            interval. Expected entries include ``rt1`` (roof), ``ow1``
            (outer wall), ``gf1`` (ground floor), and ``win1`` (window).
            ``None`` is returned implicitly if the archetype exists but no
            configured age interval contains ``year_of_construction``.
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
        Load envelope parameters for the selected archetype.
        Read ``data/non_residential/non_residential_envelope.json`` and
        select parameters matching ``usage``, ``year_of_construction``,
        and ``retrofit_level``.

        Returns
        -------
        dict
            Envelope-parameter mapping for the matching archetype,
            building-age interval, and retrofit level.
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
    
    def get_number_of_floors(self):
        """Get the number of floors for the non-residential building. Only relevant to determine the number of floors for mixed-use buildings."""
        if self.number_of_floors is None:
            # If number of floors is not provided the avg floor number is used which can be calculated utilizing gf1 which describes the ratio of the ground floor area to the total building area.
            # As the ground floor area is measured as a gross floor area the factor 0.85 is applied to account for the difference between gross and net floor area.
            # Factor sourced from the guideline "Bekanntmachung der Regeln für Energieverbrauchswerte und der Vergleichswerte im Nichtwohngebäudebestand" (15. April 2021) - Sec. 4 Ermittlung der Energiebezugsfläche
            avg_nfloors = 1/(self.facade_estimation_factors["gf1"]*0.85)

            number_of_floors = round(avg_nfloors) # TODO: Check if statistical distribution should be used instead of fixed value for each building archetype

            return number_of_floors

        return self.number_of_floors

# This class is responsible for the behavior configuration for non-residential buildings
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
