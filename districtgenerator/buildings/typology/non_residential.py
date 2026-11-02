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
from districtgenerator.utilities.paths import PACKAGE_DIR

# This Class is responsible for non-residential envelope generation
class NonResidential(object):
    """Represent a non-residential envelope with use- and age-specific properties.

    Surface areas are estimated from floor area and packaged archetype factors;
    walls and windows are distributed equally across four cardinal directions.
    The model supplies aggregate U-values and geometry rather than material layers.

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
        """Initialize envelope data and generate the archetype surfaces.

        Parameters
        ----------
        name : str
            Identifier for this building or building part.
        year_of_construction : int
            Construction year within an age interval in the packaged archetype data.
        net_leased_area : float
            Net floor area of the represented use in m²; for mixed use, only this part.
        total_building_area : float
            Net floor area of the entire building in m², used to estimate its footprint.
        usage : str
            Use code in the packaged envelope and surface data, for example ``"OB"``
            (office) or ``"SC"`` (school).
        construction_type : {"Light", "Medium", "Heavy", "Tabula"}
            Thermal-mass category passed to the downstream thermal model.
        retrofit_level : str
            Envelope state: ``"not retrofitted"``, ``"partially retrofitted"``,
            or ``"completely retrofitted"``.
        number_of_floors : int or None, optional
            Positive floor count. If None, estimate the footprint from archetype data.
        is_mixed_part : bool, optional
            Set True for a non-residential part below another use; its exposed roof
            area is then zero.

        Returns
        -------
        None
            Sets envelope parameters and surface dictionaries on this instance.
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
            Factors are dimensionless surface-area-to-net-floor-area ratios.
            ``None`` is returned implicitly if the archetype exists but no
            configured age interval contains ``year_of_construction``.
        """
        DATA_DIR_PATH = PACKAGE_DIR
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
        """Select envelope properties for this use, construction year, and retrofit.

        Returns
        -------
        dict
            U-values in W/(m² K): ``u_aw`` (wall), ``u_fen`` (window), ``u_d_opak``
            (roof), and ``u_ug`` (ground floor); plus the dimensionless window solar
            transmittance ``g_gl_fen``.
        """
        DATA_DIR_PATH = PACKAGE_DIR
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
        """Return the supplied or estimated floor count for mixed-use geometry.

        Returns
        -------
        int
            Supplied floor count, or rounded estimate from the ground-floor-to-total-
            area ratio. The estimate converts gross footprint to net area using 0.85.
        """
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
    """Store use-specific inputs for non-residential demand generation.

    Parameters
    ----------
    working_days : list of int
        Regular operating weekdays: 0 is Monday, 6 is Sunday.
    main_zone_name : str
        Principal activity-zone name used for occupancy scheduling.
    main_room_zones : list of str
        Room-zone names included in the main occupancy calculation.
    affected_by_holidays : bool
        Whether public holidays reduce occupancy.
    app_gain_factor : float or None
        Fraction of appliance electricity becoming heat; None uses model defaults.
    car_commute_ratio : float or None
        Share commuting by car (0–1); None uses the profile model's German default.
    has_ventilation : bool
        Whether mechanical ventilation is present.
    min_illuminance : int
        Lower indoor illuminance target in lux.
    max_illuminance : int
        Upper indoor illuminance target in lux.
    affected_by_school_holidays : bool
        Whether school holidays reduce occupancy.
    lighting_irradiance_threshold_mean : float or None
        Mean outdoor lighting activation threshold in W/m², if configured.
    lighting_irradiance_threshold_std_dev : float or None
        Standard deviation of that threshold in W/m², if configured.
    """
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
    """Provide use-specific assumptions for occupancy and demand profiles.

    Parameters
    ----------
    usage_string : str
        Use code in ``non_residential_behavior.json``, for example ``"OB"``
        (office) or ``"SC"`` (school).

    Attributes
    ----------
    config : NonResidentialConfig
        Schedule, lighting, ventilation, and commuting assumptions for this use.
    """

    _behavior_data_cache = None


    def __init__(self, usage_string: str):
        """Load the behavioral assumptions for a building use.

        Parameters
        ----------
        usage_string : str
            Use code in the packaged behavior data, such as ``"OB"`` for offices.

        Returns
        -------
        None
            Stores the selected assumptions in ``config``.
        """
        self.usage_string = usage_string
        self.config = self._load_config()

    def _load_config(self) -> NonResidentialConfig:
        """Select behavioral assumptions, reading the shared JSON only once.

        Returns
        -------
        NonResidentialConfig
            Use-specific settings; optional None values leave fallback selection to
            the consuming profile model.
        """
        DATA_DIR_PATH = PACKAGE_DIR
        data_path = os.path.join(DATA_DIR_PATH, 'data', 'non_residential', 'non_residential_behavior.json')
        if GenericNonResidential._behavior_data_cache is None:
            with open(data_path, 'r', encoding='utf-8') as file:
                GenericNonResidential._behavior_data_cache = json.load(file) # Cache the data after loading it for the first time to avoid redundant file reads in subsequent calls.

        data = GenericNonResidential._behavior_data_cache

        if self.usage_string not in data:
            raise ValueError(f"NWG '{self.usage_string}' not found in JSON. path: {data_path}")

        return NonResidentialConfig(**data[self.usage_string])

    def get_working_days(self) -> List[int]:
        """Return the regular operating weekdays.

        Returns
        -------
        list of int
            Weekdays with regular activity, numbered 0 (Monday) to 6 (Sunday).
        """
        return self.config.working_days

    def get_main_zone_name(self) -> str:
        """Return the principal activity zone.

        Returns
        -------
        str
            Activity-zone name used to determine the main occupancy schedule.
        """
        return self.config.main_zone_name

    def is_affected_by_holidays(self) -> bool:
        """Return whether public holidays affect occupancy.

        Returns
        -------
        bool
            True when the occupancy model should apply public-holiday reductions.
        """
        return self.config.affected_by_holidays

    def get_app_gain_factor(self) -> float:
        """Return the appliance heat-gain fraction.

        Returns
        -------
        float or None
            Fraction of appliance electricity released as internal heat (dimensionless).
            None requests the profile model's default gain calculation.
        """
        return self.config.app_gain_factor

    def get_car_commute_ratio(self) -> float | None:
        """Return the car-commuting share.

        Returns
        -------
        float or None
            Fraction of occupants commuting by car, from 0 to 1. Zero means no
            commuting cars; None requests the profile model's German default.
        """
        return getattr(self.config, 'car_commute_ratio', None)

    def get_main_room_zones(self) -> List[str]:
        """Return the zones contributing to main occupancy.

        Returns
        -------
        list of str
            Room-zone names included in the main occupancy calculation.
        """
        return self.config.main_room_zones

    def get_ventilation(self) -> bool:
        """Return the mechanical-ventilation assumption.

        Returns
        -------
        bool
            True if mechanical ventilation is assumed for this building use.
        """
        return self.config.has_ventilation

    def get_min_illuminance(self) -> int:
        """Return the lower lighting target.

        Returns
        -------
        int
            Lower bound of the required indoor illuminance in lux for lighting demand.
        """
        return self.config.min_illuminance

    def get_max_illuminance(self) -> int:
        """Return the upper lighting target.

        Returns
        -------
        int
            Upper bound of the required indoor illuminance in lux for lighting demand.
        """
        return self.config.max_illuminance

    def is_affected_by_school_holidays(self) -> bool:
        """Return whether school holidays affect occupancy.

        Returns
        -------
        bool
            True when occupancy should be reduced during school holidays.
        """
        return self.config.affected_by_school_holidays

    def get_lighting_irradiance_threshold(self) -> tuple[float, float]:
        """Return the lighting activation threshold distribution.

        Returns
        -------
        tuple of float or None
            Mean and standard deviation, in that order, of the outdoor irradiance
            threshold in W/m² used to trigger lighting. Entries may be None when
            no use-specific threshold is configured.
        """
        return self.config.lighting_irradiance_threshold_mean, self.config.lighting_irradiance_threshold_std_dev


def create_non_residential_building(building, bldgs, total_building_area):
    """Create an envelope archetype from a district building record.

    Parameters
    ----------
    building : dict
        Record with ``buildingFeatures`` containing ``building`` (use code),
        ``year``, ``area`` (net m²), ``retrofit`` and ``construction_type``
        (scenario short codes). Optional ``fixed_floors`` sets the floor count;
        ``is_mixed_part`` suppresses an exposed roof for a lower building part.
    bldgs : dict
        Design configuration mapping scenario codes to archetype names via
        ``retrofit_short_non_residential``, ``retrofit_long_non_residential``,
        ``construction_type_short``, and ``construction_type_long``.
    total_building_area : float or None
        Entire building's net area in m² for mixed-use footprint estimation.
        None uses the area of the supplied building record.

    Returns
    -------
    archetype : NonResidential
        Selected envelope properties and oriented surface areas for thermal modeling.
    construction_type : str
        Expanded thermal-mass category for the downstream building model.
    """
    retrofit_level = bldgs["retrofit_long_non_residential"][bldgs["retrofit_short_non_residential"].index(building["buildingFeatures"]["retrofit"])]
    construction_type = bldgs["construction_type_long"][bldgs["construction_type_short"].index(building["buildingFeatures"]["construction_type"])]

    if "fixed_floors" in building["buildingFeatures"]:
        number_of_floors = building["buildingFeatures"]["fixed_floors"]
    else:
        number_of_floors = None # No information about the number of floors is given

    nrb_prj = NonResidential(
            usage=building["buildingFeatures"]["building"],
            name="NonResidentialBuilding",
            year_of_construction=building["buildingFeatures"]["year"],
            net_leased_area=building["buildingFeatures"]["area"],          # Total net leased area of the building, or of the building part if it is a mixed-use building.
            total_building_area=(                                          # Total net leased area of building
                building["buildingFeatures"]["area"] if total_building_area is None
                else total_building_area),
            construction_type=construction_type,
            retrofit_level=retrofit_level,
            number_of_floors=number_of_floors,
            is_mixed_part=building["buildingFeatures"].get("is_mixed_part", False)
            )

    return nrb_prj, construction_type
