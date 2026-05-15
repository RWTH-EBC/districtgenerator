from dataclasses import field
from pathlib import Path
import os

from typing import Any, Dict, Optional, Set, Tuple, Type, ClassVar

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict
from pydantic_settings.sources import PydanticBaseSettingsSource

from dotenv import dotenv_values


### Helper functions ###
def parse_float_list(value: any) -> list[float]:
    """
    Parses a comma-separated string of floats into a list of floats.
    If the input is already a list, it returns it directly.

    Parameters
    ----------
    value : any
        The input value to parse. It can be a list of floats, a comma-separated string
        of floats, or an empty string.

    Returns
    -------
    list[float]
        A list of floats parsed from the input value.
    """
    if isinstance(value, list):
        try:
            return [float(x) for x in value]
        except ValueError as e:
            raise ValueError(f"Error parsing list elements of {value} into floats: {e}")

    if isinstance(value, str):
        # Remove whitespaces
        value = value.strip()
        # Remove [] at front and back if present
        if value.startswith('[') and value.endswith(']'):
            value = value[1:-1]
        if not value:
            return []
        return [float(x.strip()) for x in value.split(',')]

    if isinstance(value, (int, float)):
        return [float(value)]
    raise ValueError(f"Cannot parse {type(value)} into a list of floats")

### Configuration Classes ###
class LocationConfig(BaseSettings):
    """
    LocationConfig class to manage location-related parameters for the district generator.
    This class contains parameters related to the geographical location, time zone, albedo,
    and TRY (Test Reference Year) data used in the district generator.
    """
    timeZone: float = 1         # Shift between the location's time and GMT in hours. CET would be 1.
    albedo: float = 0.2         # Ground reflectance. 0 refers to 0% and 1 refers to 100%.
    TRYYear: str = 'TRY2015'    # Test reference year of DWD. Possible entries are TRY2015 and TRY2045.
    TRYType: str = 'Jahr'       # Test reference conditions of DWD. Possible entries are Jahr, Somm, Wint.
    district_area: float = 1.0   # Area of the district in ha (hectare)
    zip: str = '10115'          # Zip code of the location.
    enable_trafoMax_W: bool = False  # Consider active power cap for the district transformer. If set, it is used for BOTH import and export at the GNP.
    trafoMax_W: float = 500000.0 # Active power cap for the district transformer. If set, it is used for BOTH import and export at the GNP. (Watt)
    enable_buildingMax_W: bool = False # Consider per-building maximum import/export at the building PCC.
    buildingMax_W: float = 50000.0  # Per-building maximum import/export at the building PCC. (Watt)


    ALLOWED_TRY_YEARS: ClassVar[Set[str]] = {"TRY2015", "TRY2045"}
    ALLOWED_TRY_TYPES: ClassVar[Set[str]] = {"Jahr", "Somm", "Wint"}

    model_config = SettingsConfigDict(
        extra = 'ignore' # Ignores all other variables in the .env.CONFIG file
    )

    @field_validator('albedo')
    def validate_albedo(cls, v: float) -> float:
        """Validate that albedo is between 0.0 and 1.0."""
        if not (0.0 <= v <= 1.0):
            raise ValueError("albedo must be between 0.0 and 1.0.")
        return v

    @model_validator(mode='after')
    def check_try_settings(self) -> 'LocationConfig':
        """Validate TRYYear and TRYType against their allowed values."""
        if self.TRYYear not in self.ALLOWED_TRY_YEARS:
            raise ValueError(f"TRYYear must be one of {self.ALLOWED_TRY_YEARS}, got '{self.TRYYear}'")

        if self.TRYType not in self.ALLOWED_TRY_TYPES:
            raise ValueError(f"TRYType must be one of {self.ALLOWED_TRY_TYPES}, got '{self.TRYType}'")

        return self

class TimeConfig(BaseSettings):
    """
    TimeConfig class to manage time-related parameters for the district generator.
    This class contains parameters related to time resolution, cluster length, and data length
    used in the district generator.
    """
    timeResolution: int = 3600  # Required time resolution in seconds. Tip: 3600 refers to an hourly resolution. 900 to a 15min resolution.
    clusterLength: int = 604800 # Length of cluster. Tip: 604800 refers to one week. 86400 for one day.
    clusterNumber: int = 4      # Number of clusters
    dataResolution: int = 3600  # Time resolution of input data in seconds. (If you don't change weather data, here is no need to change).
    dataLength: int = 31536000  # Length of input data in seconds. (If you don't change weather data, here is no need to change).
    #TODO: Move Project Time here
    #TODO: Add index of interpolation years for multiyear simulations


    model_config = SettingsConfigDict(
        extra = 'ignore' # Ignores all other variables in the .env.CONFIG file
    )

class DesignBuildingConfig(BaseSettings):
    """
    DesignBuildingConfig class to manage design parameters for all buildings in the district generator.
    This class contains parameters related to building design, such as temperature settings, ventilation rates,
    building types, retrofit options, and domestic hot water (DHW) load.
    """
    T_set_min: float = 21.0         # Required minimum indoor temperature (for heating load calculation) in degrees Celsius
    T_set_min_night: float = 18.0   # Required minimum indoor temperature at night (for heating load calculation) in degrees Celsius
    T_set_min_free_day: float = 18.0 # Minimum required indoor temperature on a non-working day in a non-residential building (for heating load calculations)
    T_set_max: float = 24.0         # Required maximum indoor temperature (for cooling load calculation) in degrees Celsius
    T_set_max_night: float = 28.0   # Required maximum indoor temperature at night (for cooling load calculation) in degrees Celsius
    T_bivalent: float = -2.0        # Dual mode temperature (for heat pump design) in degrees Celsius
    T_heatlimit: float = 15.0       # Limit temperature (for heat pump design)
    ventilation_rate: float = 0.5  # Room ventilation rate in 1/h (per hour)
    thermal_model_type: str = '7R2C'  # Thermal building model type. Possible entries are '5R1C' and '7R2C'

    # --- Decentral HPs sink temperature (mean of supply & return) by age class and retrofit level ---
    # retrofit: 0=standard, 1=retrofit, 2=advanced retrofit
    # Source:
    # Wüllhorst et al. (2025), "Impact of hybrid heat pump shares and building envelope
    # retrofit rates on load penetration in German low-voltage grids",
    # DOI: 10.1016/j.apenergy.2025.125530
    # Temperature levels represent supply/return temperatures

    hp_sink_temp_levels: Dict[str, Dict[int, Tuple[float, float]]] = Field(
        default_factory=lambda: {
            "2010-": {0: (35.0, 30.0), 1: (35.0, 30.0), 2: (35.0, 30.0)},
            "1984-2009": {0: (52.5, 42.5), 1: (40.05, 34.35), 2: (36.55, 31.55)},
            "1979-1983": {0: (70.0, 55.0), 1: (45.1, 38.7), 2: (38.1, 33.1)},
            "1969-1978": {0: (70.0, 55.0), 1: (42.8, 37.2), 2: (36.9, 31.9)},
            "1958-1968": {0: (70.0, 55.0), 1: (41.4, 36.2), 2: (35.0, 30.0)},
            "-1957": {0: (70.0, 55.0), 1: (39.6, 34.6), 2: (35.0, 30.0)},
        }
    )

    # Optional "low-temperature measures" (geringinvasive Maßnahmen) are assumed to
    # reduce the required sink temperature (e.g. hydraulic balancing, radiator
    # optimization, control adjustments), improving HP efficiency without full
    # building refurbishment. If enabled, the sink temperature is capped at 45 °C.
    # Source:
    # KWW-Technikkatalog Wärmeplanung
    hp_sink_temp_measures_cap: float = 45.0

    # Currently not in .env.CONFIG as info is static:
    # Abbreviations of the selectable building types.
    buildings_short: list = field(default_factory=lambda: ["SFH", "MFH", "TH", "AB","OB","SC","GS", "RE", "MFH+GR", "AB+GR", "MFH+RE", "AB+RE"])
    # Names of the four selectable building types.
    buildings_long: list = field(default_factory=lambda: ["single_family_house", "multi_family_house", "terraced_house", "apartment_block", "office", "school", "grocery_store", "restaurant", "multi_family_house+grocery_store", "apartment_block+grocery_store", "multi_family_house+restaurant", "apartment_block+restaurant"])
    # Abbreviations of the retrofit levels.
    retrofit_short: list = field(default_factory=lambda: [0, 1, 2])
    # Names of the retrofit levels.
    retrofit_long: list = field(default_factory=lambda: ['tabula_standard', 'tabula_retrofit', 'tabula_adv_retrofit'])
    # Abbreviations of the retrofit levels of the non residential buildings.
    retrofit_short_non_residential: list = field(default_factory=lambda: [0, 1, 2])
    # Names of the retrofit levels of the non residential buildings
    retrofit_long_non_residential: list = field(default_factory=lambda: ["not retrofitted", "partially retrofitted", "completely retrofitted"])
    # Abbreviations of the construction types of the non residential buildings
    construction_type_short: list = field(default_factory=lambda: [0, 1, 2])
    # Names of the construction types of the non residential buildings
    construction_type_long: list = field(default_factory=lambda: ["Light", "Medium", "Heavy"])
    # The additional power required by the heating system to meet the domestic hot water demand per square meter in the building types:
    # SFH, MFH, TH, AB, OB, SC, GS, and RE.
    # Source: SIA2024 Standard-Nutzungsbedingungen für die Energie- und Gebäudetechnik"
    dhwpower: list = field(default_factory=lambda: [3, 3, 3, 3, 7.1, 8.6, 7.2, 24])
    # Mean drawoff DHW volume per day and person for each building type (SFH, MFH, TH, AB, OB, SC, GS, RE).
    # Source: 12831-3/A100 Table NA.4 for residential buildings and SIA2024 Standard-Nutzungsbedingungen für die Energie- und Gebäudetechnik for non-residential buildings
    mean_drawoff_vol_per_day: list = field(default_factory=lambda: [40, 40, 40, 40, 6, 1.5, 1.5, 8])

    model_config = SettingsConfigDict(
        extra = 'ignore' # Ignores all other variables in the .env.CONFIG file
    )

class EcoConfig(BaseSettings):
    """ EcoConfig class to manage economic parameters for the district generator.
    This class contains parameters related to energy prices, CO2 emissions, and other economic factors
    used in the district generator.
    """
    # General economic parameters
    interest_rate: float = 0.05  # Interest rate for the device operational optimization analysis. The interest rate affects the annualization of the investments according to VDI 2067.
    observation_time: int = 20  # Project lifetime, for the device operational optimization analysis. The project lifetime affects annualization of investments according to VDI 2067 in years
    optimization_focus: int = 0  # Optimization focus. Annual costs vs CO2 emissions. '0' means only cost optimization; '1' means only CO2 optimization.

    # The interpolation points can be either defined by specifying the exact years in interpolation_points or by choosing a number of interpolation points num_interpolation_points.
    # *Warning: num_interpolation_points overrides interpolation_points if both are specified.
    num_interpolation_points: Optional[int] = None # Number of interpolation points if not None these are used, otherwise the exact position is used
    interpolation_points: str | list[int] = [0,5,10,15] # Exact interpolation points if num_interpolation_points is None, these points are used for interpolation


    # electricity prices and feed-in revenue in €/kWh
    price_supply_el: str | list = [0.3969]    # Electricity price in €/kWh
    revenue_feed_in_el: str | list = [0.0794]  # Feed-in electricity price in €/kWh

    price_supply_el_eh: str | list = [0.1590]  # Electricity price for the energy hub in €/kWh
    revenue_feed_in_el_eh: str | list = [0.0794] # Feed-in electricity price for the energy hub in €/kWh

    # gas and other fuel prices in €/kWh
    price_supply_gas: str | list = [0.1236]   # Gas price in €/kWh
    price_supply_gas_eh: str | list = [0.0820] # Gas price for the energy hub in €/kWh
    revenue_feed_in_gas: str | list = [0.02]  # Revenue for natural gas feed-in €/kWh
    price_gasoline_liter: str | list = [1.70]  # Gasoline price in €/liter
    price_hydrogen: str | list = [0.1]         # Hydrogen price in €/kWh
    price_waste: str | list = [0.1]            # Waste price in €/kWh
    price_biomass: str | list = [0.05]         # Biomass price in €/kWh
    price_oil: str | list = [0.90]           # Oil price in €/kWh
    price_district_heat: str | list = [0.16385]  # Gross district heat price in €/kWh

    # CO2 emission factors in kg/kWh
    co2_el_grid: str | list = [0.363]          # CO2 emissions for electricity import (grid mix) in kg/kWh
    co2_gas: str | list = [0.201]              # CO2 emissions for burning natural gas in kg/kWh
    co2_biom: str | list = [0.35]              # CO2 emissions for burning biomass in kg/kWh
    co2_hydrogen: str | list = [0.0402]           # CO2 emissions for burning hydrogen in kg/kWh
    co2_oil: str | list = [0.310]              # CO2 emissions for burning oil in kg/kWh
    co2_waste: str | list = [0.02]              # CO2 emissions for burning waste in kg/kWh
    co2_district_heat: str | list = [0.200]    # CO2 emissions for district heat in kg/kWh

    # Co2 tax in €/t_CO2
    co2_tax: str | list = [0]              # CO2 tax. Tax on CO2 emissions due to burning natural gas, biomass or waste in €/t_CO2 if relevant for consumer

    @field_validator('interpolation_points','price_supply_el', 'revenue_feed_in_el', 'price_supply_el_eh',
                     'revenue_feed_in_el_eh', 'price_supply_gas', 'price_supply_gas_eh', 'revenue_feed_in_gas',
                     'price_gasoline_liter', 'price_hydrogen', 'price_waste',
                     'price_biomass', 'price_oil', 'price_district_heat',
                     'co2_el_grid', 'co2_gas', 'co2_biom', 'co2_hydrogen',
                     'co2_oil', 'co2_waste', 'co2_district_heat', 'co2_tax', mode='before')
    @classmethod
    def parse_to_float_list(cls, v):
        """Convert input to list of floats"""
        return parse_float_list(v)

    @field_validator('num_interpolation_points', mode='before')
    @classmethod
    def parse_none_string(cls, v):
        """Convert string 'None' to Python None"""
        if v == "None" or v == "null" or v == "" or v is None:
            return None
        return int(v)

    @model_validator(mode='after')
    def expand_lists_to_observation_time(self) -> 'EcoConfig':
        """
        Expand all price and CO2 lists to match observation_time.
        If list has only 1 element, repeat it observation_time times.
        If list is shorter than observation_time, repeat the last value, and give a console warning.
        If list is longer, truncate to observation_time, and give a console warning.
        """
        # List of all time dependent parameters
        params_to_expand = [
            'price_supply_el', 'revenue_feed_in_el', 'price_supply_el_eh', 'revenue_feed_in_el_eh',
            'price_supply_gas', 'price_supply_gas_eh', 'revenue_feed_in_gas', 'price_gasoline_liter', 'price_hydrogen',
            'price_waste', 'price_biomass', 'price_oil', 'price_district_heat',
            'co2_el_grid', 'co2_gas', 'co2_biom', 'co2_hydrogen', 'co2_oil', 'co2_waste', 'co2_district_heat', 'co2_tax'
        ]

        for param_name in params_to_expand:
            current_list = getattr(self, param_name)

            if not type(current_list) == list:
                raise ValueError(f"{param_name} must be a list")

            if len(current_list) == 0:
                raise ValueError(f"{param_name} cannot be an empty list")
            elif len(current_list) == 1:
                # Single value - repeat for all years
                setattr(self, param_name, current_list * self.observation_time)
            elif len(current_list) < self.observation_time:
                # List too short - extend with last value
                last_value = current_list[-1]
                extended_list = current_list + [last_value] * (self.observation_time - len(current_list))
                setattr(self, param_name, extended_list)
                print(f"Warning: {param_name} list was shorter than observation_time. Extended with last value to match length.")
            elif len(current_list) > self.observation_time:
                # List too long - truncate
                setattr(self, param_name, current_list[:self.observation_time])
                print(f"Warning: {param_name} list was longer than observation_time. Truncated to match length.")
            # else: length matches exactly, no change needed

        return self

    @model_validator(mode='after')
    def select_interpolation_points(self) -> 'EcoConfig':
        """Select interpolation points based on num_interpolation_points if specified."""
        if self.num_interpolation_points is not None:
            # Validate num_interpolation_points value
#            print(self.num_interpolation_points)
#            print(type(self.num_interpolation_points))
            if self.num_interpolation_points < 1:
                raise ValueError("num_interpolation_points must be at least 1.")
            if self.num_interpolation_points > self.observation_time:
                raise ValueError(f"num_interpolation_points cannot be greater than observation_time. Max is one per year {self.observation_time}.")

            # First interpolation point is always year 0
            selected_points = [0]

            # Assign the remaining points evenly, to generate time windows of equal length
            if self.num_interpolation_points > 1:
                step = self.observation_time / (self.num_interpolation_points)
                for i in range(1, self.num_interpolation_points):
                    point = round(i * step)
                    selected_points.append(point)

            # Override interpolation_points with selected points
            self.interpolation_points = selected_points

        else: # Validate if the interpolation points are within the observation time
            invalid_points = []
            for point in self.interpolation_points:
                if point < 0 or point >= self.observation_time:
                    invalid_points.append(point)

            if invalid_points:
                raise ValueError(f"The following interpolation points are invalid for the given observation time of {self.observation_time} years: {invalid_points} (Max is {self.observation_time - 1})")

        return self

    model_config = SettingsConfigDict(
        extra = 'allow' # Ignores all other variables in the .env.CONFIG file
    )

class PhysicsConfig(BaseSettings):
    """
    PhysicsConfig class to manage physical constants and parameters used in the district generator.
    """
    rho_air: float = 1.2        # kg/m3
    c_p_air: float = 1000.0     # J/(kg*K)
    rho_water: float = 1000.0   # kg/m3
    c_p_water: float = 4.18     # J/(kg*K)

    model_config = SettingsConfigDict(
        extra = 'ignore' # Ignores all other variables in the .env.CONFIG file
    )

class PyomoConfig(BaseSettings):
    """
    PyomoConfig class to manage the configuration of the Pyomo optimization solver.
    """
    solver_name: str = "gurobi"     # Name of the solver to be used. Options: 'gurobi', 'highs', 'cbc' etc. highs does not require any additional download or license. Already available if all packages in requirements.txt are installed.
    solver_executable: Optional[str] = None   # Path to solver executable, if needed
    solver_options__time_limit: int = 600          # Time limit in seconds for each optimization run
    solver_options__mip_gap: float = 0.01            # Acceptable MIP gap from optimal solution
    solver_options__threads: int = 4               # Number of threads to use for solving
    solver_options__nonconvex: int = 2            # Allow non-convex problems
    solver_options__dual_reductions: int = 1        # Try to reduce the model size before solving 1 = yes, 0 = no -> May slightly change results
    solver_options: dict = {}

    @field_validator('solver_executable', mode='before')
    @classmethod
    def parse_none_string(cls, v):
        """Convert string 'None' to Python None"""
        if v == "None" or v == "null" or v == "":
            return None
        return v

    @model_validator(mode='after')
    def build_device_dicts(self) -> 'DecentralDeviceConfig':
        """Build all device dictionaries from individual parameters."""

        # Create a list of field names to avoid RuntimeError during iteration
        field_names = list(self.__dict__.keys())

        # Get all field names from the model
        for field_name in field_names:
            # Check if this is a dictionary field (uppercase device name)
            if isinstance(getattr(self, field_name), dict):
                # Only build if the dictionary is empty
                if getattr(self, field_name) == {}:
                    device_dict = {}
                    prefix = f"{field_name}__"

                    # Find all attributes that start with this device prefix
                    for attr_name in field_names:  # Use the snapshot here too
                        if attr_name.startswith(prefix):
                            # Remove the prefix to get the dictionary key
                            dict_key = attr_name[len(prefix):]
                            device_dict[dict_key] = getattr(self, attr_name)

                    # Set the dictionary first
                    setattr(self, field_name, device_dict)

                    # Now delete the individual attributes
                    for attr_name in field_names:
                        if attr_name.startswith(prefix):
                            delattr(self, attr_name)

        return self

    model_config = SettingsConfigDict(
        extra = 'ignore' # Ignores all other variables in the .env.CONFIG file
    )

class HeatGridConfig(BaseSettings):
    """
    Manages the configuration for the district heating network.

    This class defines the default parameters for the physical, thermal, and economic
    properties of a heating grid. It includes settings for operating temperatures,
    physical dimensions, material properties, and costs.
    """

    generation: str = "4th"      # Heating network generation, selected between:"3rd", "4th" and "5th"
    topology_option: str = "node"  # Whether consider road constraints in pipeline topology optimization, selected between:"node" and "road"
    temperature_mode: str = "constant" # selected between: "constant" and "heating_curve"(controlled within limits depending on the outdoor temperature)
    heuristic: bool = True # selected between: True (heuristic method) and False (optimization method)
    D_heating_network: float = 1.0      # Distance between the centerlines of the supply and return pipelines in meters.
    T_hot_cooling_network: float = 12.0  # Flow temperature of the cooling network in degrees Celsius.
    T_cold_cooling_network: float = 6.0  # Return temperature of the cooling network in degrees Celsius.
    D_cooling_network: float = 1.0      # Distance between the centerlines of supply and return pipelines in meters.
    delta_T_heatTransfer: float = 5.0    # Temperature difference in heat exchangers in Kelvin.
    life_time: int = 40                 # Lifetime of the heating network and its components in years.
    asphaltlayer: int = 1               # Consideration of asphalt layer (1 = yes, 0 = no).
    d_asph: float = 0.18             # Asphalt layer thickness in meters.
    grid_depth: float = 1.0             # Installation depth of the grid beneath the surface in meters.
    k_soil: float = 1.52                # Soil heat conductivity in W/(m*K). Source: Median value from table 4.1 Wessolek, G. (2022). Parametrisierung thermischer Bodeneigenschaften: Endbericht
    k_PUF: float = 0.03                 # Polyurethane foam heat conductivity. Source: VDI Wärmeatlas
    k_PE: float = 0.4                 # Polyethylene heat conductivity. Source: VDI Wärmeatlas
    h_loss_subst: float = 5      # Heat losses at the substation as a percentage (%). Source: Technikkatalog Wärmeplanung 2024
    dp_substation: float = 75000.0        # Pressure drop at the substation in Pascal (Pa). Source: Technikkatalog Wärmeplanung 2024
    dp_energy_hub: float = 100000.0        # Pressure drop at the energy hub in Pascal (Pa). Source: Technikkatalog Wärmeplanung 2024
    C_subst: float = 584        # Investment costs for the substation in €/kW_th. Source: Technikkatalog Wärmeplanung 2024
    cost_om_subst: float = 50                  #Operation & Maintenance (O&M) costs in €/MWh_th. Source: Technikkatalog Wärmeplanung 2024
    lifetime_subst: int = 25                 # Lifetime of the substation in years. Source: Technikkatalog Wärmeplanung 2024
    C_OM: float = 1.44               # Annual fixed Operation & Maintenance (O&M) costs in % of the investment costs.

    T_hot_heating_network__constant__3rd: float = 80.0  # Supply temperature of 3rd generation heat grid in degrees Celsius.
    T_hot_heating_network__constant__4th: float = 55.0  # Supply temperature of 4th generation heat grid in degrees Celsius.
    T_hot_heating_network__constant__5th: float = 18.0  # Supply temperature of 5th generation heat grid in degrees Celsius.
    T_hot_heating_network__heating_curve__max__3rd: float = 75.0  # Supply temperature of 3rd generation heat grid when outdoor temperature is high in degrees Celsius.
    T_hot_heating_network__heating_curve__max__4th: float = 50.0  # Supply temperature of 4th generation heat grid when outdoor temperature is high in degrees Celsius.
    T_hot_heating_network__heating_curve__max__5th: float = 18.0  # Supply temperature of 5th generation heat grid when outdoor temperature is high in degrees Celsius.
    T_hot_heating_network__heating_curve__min__3rd: float = 85.0  # Supply temperature of 3rd generation heat grid when outdoor temperature is low in degrees Celsius.
    T_hot_heating_network__heating_curve__min__4th: float = 65.0  # Supply temperature of 4th generation heat grid when outdoor temperature is low in degrees Celsius.
    T_hot_heating_network__heating_curve__min__5th: float = 14.0  # Supply temperature of 5th generation heat grid when outdoor temperature is low in degrees Celsius.
    T_hot_heating_network: dict = {}

    T_cold_heating_network__constant__3rd: float = 50.0  # Return temperature of 3rd generation heat grid in degrees Celsius.
    T_cold_heating_network__constant__4th: float = 35.0  # Return temperature of 4th generation heat grid in degrees Celsius.
    T_cold_heating_network__constant__5th: float = 11.0  # Return temperature of 5th generation heat grid in degrees Celsius.
    T_cold_heating_network__heating_curve__max__3rd: float = 45.0  # Return temperature of 3rd generation heat grid when outdoor temperature is high in degrees Celsius.
    T_cold_heating_network__heating_curve__max__4th: float = 30.0  # Return temperature of 4th generation heat grid when outdoor temperature is high in degrees Celsius.
    T_cold_heating_network__heating_curve__max__5th: float = 11.0  # Return temperature of 5th generation heat grid when outdoor temperature is high in degrees Celsius.
    T_cold_heating_network__heating_curve__min__3rd: float = 50.0  # Return temperature of 3rd generation heat grid when outdoor temperature is low in degrees Celsius.
    T_cold_heating_network__heating_curve__min__4th: float = 40.0  # Return temperature of 4th generation heat grid when outdoor temperature is low in degrees Celsius.
    T_cold_heating_network__heating_curve__min__5th: float = 7.0   # Return temperature of 5th generation heat grid when outdoor temperature is low in degrees Celsius.
    T_cold_heating_network: dict = {}


    fluid__c_f: float = 4180.0      # Specific heat capacity of the fluid in J/(kg*K).
    fluid__rho_f: float = 1000.0    # Density of the fluid in kg/m3.
    fluid__nu_f: float = 0.66e-6    # Kinematic viscosity of the fluid in m2/s at 40°C.
    fluid: dict = {}

    pump__eta_pump: float = 0.65        # Electric pump efficiency (0 < eta_pump <= 1).
    pump__inv_pump: float = 700.0       # Investment costs of the pump in €/kW.
    pump__pump_lifetime: int = 10       # Pump lifetime in years.
    pump__cost_om_pump: float = 0.03    # Pump O&M share (fraction of investment cost per year).
    pump: dict = {}

    pipe__f_fric: float = 0.025         # Friction factor (dimensionless). (Initial friction factor for iteration)
    pipe__dp_pipe_max: float = 400.0    # Max pressure gradient in Pa/m.
    pipe__dp_pipe_min: float = 30.0     # Min pressure gradient in Pa/m.
    pipe__pipe_lifetime: int = 30       # Pipe lifetime in years.
    pipe__cost_om_pipe: float = 0.005    # Pipe O&M share (fraction of investment cost per year).
    pipe: dict = {}


    @model_validator(mode='after')
    def build_device_dicts(self) -> 'HeatGridConfig':
        """Build all device dictionaries from individual parameters, supporting nested structure."""

        field_names = list(self.__dict__.keys())

        for field_name in field_names:
            if isinstance(getattr(self, field_name), dict):
                if getattr(self, field_name) == {}:
                    device_dict = {}
                    prefix = f"{field_name}__"

                    # Find all attributes that start with this device prefix
                    for attr_name in field_names:
                        if attr_name.startswith(prefix):
                            # Remove the prefix to get the key path
                            key_path = attr_name[len(prefix):]

                            # Split by __ to support nested structure
                            keys = key_path.split('__')

                            # Navigate/create nested dict structure
                            current_dict = device_dict
                            for i, key in enumerate(keys):
                                if i == len(keys) - 1:
                                    # Last key: set the value
                                    current_dict[key] = getattr(self, attr_name)
                                else:
                                    # Intermediate key: ensure nested dict exists
                                    if key not in current_dict:
                                        current_dict[key] = {}
                                    current_dict = current_dict[key]

                    # Set the dictionary
                    setattr(self, field_name, device_dict)

                    # Now delete the individual attributes
                    for attr_name in field_names:
                        if attr_name.startswith(prefix):
                            delattr(self, attr_name)

        return self


    model_config = SettingsConfigDict(
        extra = 'ignore' # Ignores all other variables in the .env.CONFIG file
    )

class EHDOConfig(BaseSettings):
    """
    EHDOConfig class to manage the configuration of the Energy and Heat Distribution Optimization (EHDO) system.
    This class contains parameters relevant for the central optimization of energy and heat distribution in the
    district generator. It configures e.g. the use of certain technologies (electricity, gas, biomass, hydrogen, etc.)
    and their respective prices, CO2 emissions, and supply limits.
    """

    # Electricity configuration
    enable_supply_el: bool = True           # Enable electricity supply, bool.
    enable_feed_in_el: bool = True          # Enable feed-in tariff for electricity, bool.
    enable_price_cap_el: bool = False       # Enable electricity capacity price, bool.
    price_cap_el: float = 60                # Electricity capacity price in €/kWh.
    enable_cap_limit_el: bool = False       # Consider capacity of grid connection, bool.
    cap_limit_el: float = 100000  # in kW   # Capacity of grid connection in kW.
    enable_supply_limit_el: bool = False    # Enable restriction of electricity demand from grid, bool.
    supply_limit_el: float = 100000         # Restrict electricity demand from grid in MWh/year

    # Gas configuration
    enable_supply_gas: bool = False         # Enable gas supply, bool.
    enable_price_cap_gas: bool = False      # Enable gas capacity price, bool.
    price_cap_gas: float = 0.04             # Gas capacity price in €/kWh
    enable_feed_in_gas: bool = False        # Enable natural gas feed-in, bool.
    enable_cap_limit_gas: bool = False      # Restrict gas demand from grid, bool.
    cap_limit_gas: float = 1000000          # Maximum annual energy drawn from the gas grid in MWh/year

    # Biomass configuration
    enable_supply_biomass: bool = False         # Restrict available biomass, bool.
    enable_supply_limit_biomass: bool = False   # Enable limit annual biomass import, bool.
    supply_limit_biomass: float = 1000000       # Maximum available biomass in MWh/year

    # Hydrogen configuration
    enable_supply_hydrogen: bool = False        # Restrict available hydrogen, bool.
    enable_supply_limit_hydrogen: bool = False  # Enable limit annual hydrogen import, bool.
    supply_limit_hydrogen: float = 1000000      # Maximum available Hydrogen in MWh/year

    # Waste configuration
    enable_supply_waste: bool = False           # Restrict available waste, bool.
    enable_supply_limit_waste: bool = False     # Enable limit annual waste import, bool.
    supply_limit_waste: float = 1000000         # Maximum available waste in MWh/year

    #! Additional gas supply limit (duplicate naming in JSON template - adjust if needed)
    supply_limit_gas: float = 1000000       # Maximum available gas in MWh/year
    enable_supply_limit_gas: bool = False   # Enable limit annual gas import, bool.

    # Other options
    peak_dem_met_conv: bool = True  # Meet peak demands of unclustered demands, bool.
    co2_el_feed_in: float = 0       #! CO₂ emission credit for electricity feed-in kg/kWh (Move to EcoConfig)
    co2_gas_feed_in: float = 0      #! CO₂ emission credit for gas feed-in kg/kWh (Move to EcoConfig)
    n_clusters: int = 12            # Number of design days.

    # Helper attributes for unit formatting (Remove?)
    unit_placeholder: str = " - "   # used for cases where unit is a placeholder
    unit_dash: str = "-"            # used for cases where unit is a dash

    model_config = SettingsConfigDict(
        extra = 'ignore' # Ignores all other variables in the .env.CONFIG file
    )

class CalendarConfig(BaseSettings):
    """
    CalenderConfig class to manage calendar-related parameters for the district generator.
    This class contains parameters related to holidays and initial days for different years.
    """
    consider_heating_period: bool = True    # Consider heating period in the clustering (True) or calculate whole year (False)
    consider_cooling_period: bool = True    # Consider cooling period in the clustering (True) or calculate whole year (False)
    # If heating period considered:
    heating_period_start: int = 259  # Julian day number of the start of the heating period (default: 15th September)
    heating_period_end: int = 135    # Julian day number of the end of the heating period (default: 15th May)
    # If cooling period considered:
    cooling_period_start: int = 105  # Julian day number of the start of the cooling period (default: 15th April)
    cooling_period_end: int = 273    # Julian day number of the end of the cooling period (default: 1st October)


    model_config = SettingsConfigDict(
        extra = 'ignore' # Ignores all other variables in the .env.CONFIG file
    )

class ScenarioName(BaseSettings):
    """
    ScenarioName class to manage the scenario name for the district generator.
    """
    scenario_name: str = 'base_scenario' # default value for scenario name

    model_config = SettingsConfigDict(
        extra = 'ignore' # Ignores all other variables in the .env.CONFIG file
    )

class flags(BaseSettings):
    calcThick: bool = False
    save_occ_prof: bool = False
    model_config = SettingsConfigDict(
        extra="ignore"
    )

class DecentralDeviceConfig(BaseSettings):
    """Configuration for decentralized devices in a district energy system.

    This class defines the default parameters for various decentralized devices such as
    heat pumps (HP), electric heaters (EH), gas boilers (BOI),
    combined heat and power plants (CHP), fuel cells (FC), photovoltaics (PV),
    solar thermal collectors (STC), thermal energy storage (TES),
    battery storage (BAT), and electric vehicles (EV).

    Each device has parameters such as efficiency, lifetime, investment costs,
    and operational characteristics.
    """

    # CC Parameters (Air-to-Water Compression Chiller)
    CC__grade: float = 0.4  # Quality grade. Ratio of the achieved coefficient of performance to the Carnot coefficient of performance.
    CC__life_time: int = 20  # Maximum life time in years.
    CC__inv_base: float = 700.0  # Unsubsidized investment in €/kW.
    CC__cost_om: float = 0.02  # Operation and maintenance costs as a fraction of investment costs in 1/year.
    CC__inv_subsidy_rate: float = 0.0  # Investment subsidy rate as a fraction of investment cost (0 to 1).
    CC: dict = {}

    # HP parameters (Air Source Heat Pump)
    HP__grade: float = 0.4  # Quality grade. Ratio of the achieved coefficient of performance to the Carnot coefficient of performance.
    HP__life_time: int = 20  # Maximum life time in years.
    HP__inv_base: float = 1660.0  # Unsubsidized investment in €/kWth.
    HP__cost_om: float = 0.02  # Operation and maintenance costs as a fraction of investment costs in 1/year.
    HP__inv_subsidy_rate: float = 0.0  # Investment subsidy rate as a fraction of investment cost (0 to 1).
    HP__enable_measures: bool = False # "geringinvestive Maßnahmen": extra cost, can reduce supply/return temps to 50/40 °C (only if lower than the original system temperatures).
    HP__measures_inv_fix: float = 226.0  # €/kW_th, additional investment if these measures are applied.
    HP: dict = {}

    # EH parameters (Electric Heater)
    EH__eta_th: float = 1.0  # Thermal efficiency.
    EH__life_time: int = 25  # Maximum life time in years.
    EH__inv_base: float = 620.0  # Unsubsidized investment in €/kW.
    EH__cost_om: float = 0.0096  # Operation and maintenance costs as a fraction of investment costs in 1/year.
    EH__inv_subsidy_rate: float = 0.0  # Investment subsidy rate as a fraction of investment cost (0 to 1).
    EH: dict = {}

    # BOI parameters (Gas Boiler)
    BOI__eta_th: float = 0.99  # Thermal efficiency.
    BOI__life_time: int = 20  # Maximum life time in years.
    BOI__inv_base: float = 527.0  # Unsubsidized investment in €/kW.
    BOI__cost_om: float = 0.031  # Operation and maintenance costs as a fraction of investment costs in 1/year.
    BOI__inv_subsidy_rate: float = 0.0  # Investment subsidy rate as a fraction of investment cost (0 to 1).
    BOI: dict = {}

    # BBOI parameters (Biomass Boiler)
    BBOI__eta_th: float = 0.90  # Thermal efficiency.
    BBOI__life_time: int = 20  # Maximum life time in years.
    BBOI__inv_base: float = 2724.0  # Unsubsidized investment in €/kW
    BBOI__cost_om: float = 0.0095  # Operation and maintenance costs as a fraction of investment costs in 1/year.
    BBOI__inv_subsidy_rate: float = 0.0  # Investment subsidy rate as a fraction of investment cost (0 to 1).
    BBOI: dict = {}

    # OBOI parameters (Oil Boiler)
    OBOI__eta_th: float = 0.92  # Thermal efficiency.
    OBOI__life_time: int = 20  # Maximum life time in years.
    OBOI__inv_base: float = 770.0  # Unsubsidized investment in €/kW.
    OBOI__cost_om: float = 0.036  # Operation and maintenance costs as a fraction of investment costs in 1/year.
    OBOI__inv_subsidy_rate: float = 0.0  # Investment subsidy rate as a fraction of investment cost (0 to 1).
    OBOI: dict = {}

    # H2BOI parameters (Hydrogen Boiler)
    H2BOI__eta_th: float = 0.994  # Thermal efficiency.
    H2BOI__life_time: int = 20  # Maximum life time in years.
    H2BOI__inv_base: float = 597.0  # Unsubsidized investment in €/kW.
    H2BOI__cost_om: float = 0.03  # Operation and maintenance costs as a fraction of investment costs in 1/year.
    H2BOI__inv_subsidy_rate: float = 0.0  # Investment subsidy rate as a fraction of investment cost (0 to 1).
    H2BOI: dict = {}

    # CHP parameters (Combined Heat and Power)
    CHP__eta_th: float = 0.62  # Thermal efficiency.
    CHP__eta_el: float = 0.30  # Electrical efficiency.
    CHP__life_time: int = 15  # Maximum life time in years.
    CHP__inv_base: float = 3338.0  # Unsubsidized investment in €/kW.
    CHP__cost_om: float = 0.05  # Operation and maintenance costs as a fraction of total investment costs (percentage).
    CHP__inv_subsidy_rate: float = 0.0  # Investment subsidy rate as a fraction of investment cost (0 to 1).
    CHP: dict = {}

    # DH parameters (District Heating Connection)
    DH__eta_th: float = 1.0  # Thermal efficiency.
    DH__life_time: int = 30  # Maximum life time in years.
    DH__inv_base: float = 60.93  # (Baukostenzuschuss) Unsubsidized investment in €/kW.
    DH__cap_fee: float = 0.0  # Capacity fee in €/kW/year.
    DH__inv_subsidy_rate: float = 0.0  # Investment subsidy rate as a fraction of investment cost (0 to 1).
    DH: dict = {}

    # FC parameters (Fuel Cell)
    FC__eta_th: float = 0.53  # Thermal efficiency.
    FC__eta_el: float = 0.39  # Electrical efficiency.
    FC__life_time: int = 20  # Maximum life time in years.
    FC__inv_base: float = 2900.0  # Unsubsidized investment in €/kW.
    FC__cost_om: float = 0.03  # Operation and maintenance costs as a fraction of total investment costs (percentage).
    FC__inv_subsidy_rate: float = 0.0  # Investment subsidy rate as a fraction of investment cost (0 to 1).
    FC: dict = {}

    # PV parameters (Photovoltaics)
    PV__area_real: float = 1.6  # Module area in squaremeters.
    PV__eta_el_ref: float = 0.199  # Electrical efficiency under reference conditions.
    PV__t_cell_ref: int = 25  # Reference cell temperature in degree Celsius.
    PV__G_ref: int = 1000  # Reference solar irradiance in Watt per squaremeter.
    PV__t_cell_noct: int = 44  # Cell temperature under normal operating cell temperature (NOCT) conditions in degree Celsius.
    PV__t_air_noct: int = 20  # Ambient air temperature under normal operating cell temperature (NOCT) conditions in degree Celsius.
    PV__G_noct: int = 800  # Irradiance under normal operating cell temperature (NOCT) conditions in Watt per squaremeter.
    PV__gamma: float = 0.003  # Temperature coefficient of power loss in Percent per Kelvin.
    PV__eta_inv: float = 0.96  # Inverter efficiency.
    PV__eta_opt: float = 0.9  # Optical efficiency.
    PV__P_nominal: float = 220.0  # Reference power per squaremeter, used for Battery sizing, in Watt per squaremeter.
    PV__life_time: int = 25  # Maximum life time in years.
    PV__inv_base: int = 250  # Unsubsidized investment in €/m^2.
    PV__cost_om: float = 0.015  # Operation and maintenance costs as a fraction of investment costs in 1/year.
    PV__kappa_inverter: float = 0.02  # Correction factor for inverter losses
    PV__kappa_wiring: float = 0.015  # Correction factor for wiring losses
    PV__kappa_connections: float = 0.005  # Correction factor for all losses in connectors
    PV__kappa_soiling: float = 0.02  # Correction factor for losses due to soiling
    PV__kappa_shading: float = 0.03  # Correction factor for losses due to shading
    PV__kappa_mismatch: float = 0.02  # Correction factor for mismatch losses (production deviations between modules)
    PV__kappa_NPR: float = 0.01  # Correction factor for name plate rating losses (deviation of the power rating from the actual power)
    PV__kappa_av: float = 0.025  # Correction factor for losses to to non-availability of the system (e.g. maintenance, redispatch, etc.)
    PV__kappa_LID: float = 0.015  # Correction factor for mismatch losses (production deviations between modules)
    PV__inv_subsidy_rate: float = 0.0  # Investment subsidy rate as a fraction of investment cost (0 to 1).
    PV: dict = {}

    # STC parameters (Solar Thermal Collector)
    STC__T_flow: int = 50  # Flow temperature in degree Celsius.
    STC__zero_loss: float = 0.786  # Optical efficiency (zero loss collector efficiency).
    STC__first_order: float = 0.003345  # First order loss coefficient (linear thermal losses) in Watt per squaremeter per Kelvin.
    STC__second_order: float = 0.0000142  # Second order loss coefficient (quadratic thermal losses) in Watt per squaremeter per Kelvin square.
    STC__life_time: int = 20  # Maximum life time in years.
    STC__inv_base: int = 600  # Unsubsidized investment in €/m^2.
    STC__cost_om: float = 0.05  # Operation and maintenance costs as a fraction of total investment costs (percentage).
    STC__inv_subsidy_rate: float = 0.0  # Investment subsidy rate as a fraction of investment cost (0 to 1).
    STC: dict = {}

    # TES parameters (Thermal Energy Storage)
    TES__soc_min: float = 0.0  # Minimum state of charge.
    TES__soc_max: float = 1.0  # Maximum state of charge.
    TES__eta_standby: float = 0.998  # Standby hourly efficiency (accounts for self-discharge).
    TES__eta_ch: float = 1.0  # Charging and discharging efficiency.
    TES__coeff_ch: float = 10000.0  # Charging and discharging coefficient in Watt per Watthour.
    TES__init: float = 0.5  # Initial state of charge.
    TES__T_diff_max: int = 35  # Maximum temperature difference in degree Celsius.
    TES__life_time: int = 20  # Maximum life time in years.
    TES__inv_base: float = 11.0  # Unsubsidized investment in €/liter.
    TES__cost_om: float = 0.013  # Operation and maintenance costs as a fraction of investment costs in 1/year.
    TES__inv_subsidy_rate: float = 0.0  # Investment subsidy rate as a fraction of investment cost (0 to 1).
    TES: dict = {}

    # BAT parameters (Battery Storage)
    BAT__soc_min: float = 0.1  # Minimum state of charge.
    BAT__soc_max: float = 0.95  # Maximum state of charge.
    BAT__eta_standby: float = 0.99999  # Standby hourly efficiency (accounts for self-discharge).
    BAT__eta_ch: float = 0.97  # Charging and discharging efficiency.
    BAT__coeff_ch: float = 0.8  # Charging and discharging coefficient in Watt per Watthour.
    BAT__init: float = 0.5  # Initial state of charge.
    BAT__life_time: int = 15  # Maximum life time in years.
    BAT__inv_base: float = 850.0  # Unsubsidized investment in €/kWh.
    BAT__cost_om: float = 0.05  # Operation and maintenance costs as a fraction of total investment costs (percentage).
    BAT__inv_subsidy_rate: float = 0.0  # Investment subsidy rate as a fraction of investment cost (0 to 1).
    BAT: dict = {}

    # EV parameters (Electric Vehicle)
    EV__soc_min: float = 0.05  # Minimum state of charge.
    EV__soc_max: float = 0.95  # Maximum state of charge.
    EV__eta_standby: float = 1.0  # Standby hourly efficiency (accounts for self-discharge).
    EV__eta_ch: float = 0.97  # Charging and discharging efficiency.
    EV__coeff_ch: float = 0.15  # Charging and discharging coefficient in Watt per Watthour.
    EV__init: float = 0.9  # Initial state of charge.
    EV__life_time: int = 20  # Maximum life time in years.
    EV__inv_base: float = 0.0  # Unsubsidized investment in €/kWh.
    EV__cost_om: float = 0.0  # Operation and maintenance costs as a fraction of total investment costs (percentage).
    EV__inv_subsidy_rate: float = 0.0  # Investment subsidy rate as a fraction of investment cost (0 to 1).
    EV: dict = {}

    @model_validator(mode='after')
    def build_device_dicts(self) -> 'DecentralDeviceConfig':
        """Build all device dictionaries from individual parameters."""

        # Create a list of field names to avoid RuntimeError during iteration
        field_names = list(self.__dict__.keys())

        # Get all field names from the model
        for field_name in field_names:
            # Check if this is a dictionary field (uppercase device name)
            if isinstance(getattr(self, field_name), dict):
                # Only build if the dictionary is empty
                if getattr(self, field_name) == {}:
                    device_dict = {}
                    prefix = f"{field_name}__"

                    # Find all attributes that start with this device prefix
                    for attr_name in field_names:  # Use the snapshot here too
                        if attr_name.startswith(prefix):
                            # Remove the prefix to get the dictionary key
                            dict_key = attr_name[len(prefix):]
                            device_dict[dict_key] = getattr(self, attr_name)

                    # Calculate inv_var from inv_base and inv_subsidy_rate
                    if 'inv_base' in device_dict and 'inv_subsidy_rate' in device_dict:
                        device_dict['inv_var'] = device_dict['inv_base'] * (1 - device_dict['inv_subsidy_rate'])

                    # Set the dictionary first
                    setattr(self, field_name, device_dict)

                    # Now delete the individual attributes
                    for attr_name in field_names:
                        if attr_name.startswith(prefix):
                            delattr(self, attr_name)

        return self


    model_config = SettingsConfigDict(
        env_prefix="D_",  # Prefix for environment variables
        env_file=".decentraldeviceconfig",
        extra="ignore"
    )

class CentralDeviceConfig(BaseSettings):
    """Configuration for central devices in a district energy system.

    This class defines the default parameters for various central devices such as
    photovoltaic systems (PV), wind turbines (WT), water turbines (WAT),
    solar thermal collectors (STC), combined heat and power systems (CHP),
    boilers (BOI), heat pumps (HP), electric boilers (EB), chillers (CC),
    and various storage systems like TES, BAT, and GS.

    Each device has parameters such as feasibility, efficiency, lifetime, investment costs,
    and operational characteristics.
    """

    # PV parameters (Photovoltaic System)
    PV__feasible: bool = False  # Should this be considered for the central optimization.
    PV__eta: float = 0.199  # Electrical efficiency between 0 and 1.
    PV__beta: float = 35.0  # Tilt angle of the solar collectors in degrees.
    PV__gamma: float = 0  # Azimuth angle (orientation) of the collectors in degrees (0=South, -90=East, 90=West).
    PV__life_time: int = 25  # Maximum life time in years.
    PV__inv_base: float = 1000  # Unsubsidized investment in €/kW.
    PV__cost_om: float = 0.02  # Cost of operation and maintenance as a percentage of investment.
    PV__max_area: float = 10000  # Maximum installation area in square meters.
    PV__min_area: float = 0  # Minimum installation area in square meters.
    PV__G_stc: float = 1  # Global horizontal irradiance under STC in kW/m^2.
    PV__inv_subsidy_rate: float = 0.0  # Investment subsidy rate as a fraction of investment cost (0 to 1).
    PV: dict = {}

    # WT parameters (Wind Turbine)
    WT__feasible: bool = False  # Should this be considered for the central optimization.
    WT__inv_base: float = 1500  # Unsubsidized investment in €/kW.
    WT__life_time: int = 20  # Maximum life time in years.
    WT__cost_om: float = 0.015  # Cost of operation and maintenance as a percentage of investment.
    WT__min_cap: float = 0  # Minimum capacity in kW.
    WT__max_cap: float = 3000  # Maximum capacity in kW.
    WT__h_coeff: float = 0.2  # Hellmann exponent for wind speed correction.
    WT__hub_h: float = 100  # Hub height of the wind turbine in meters.
    WT__ref_h: float = 10  # Reference height for wind speed data in meters.
    WT__norm_power: float = 0.85  # Normalized power output.
    WT__inv_subsidy_rate: float = 0.0  # Investment subsidy rate as a fraction of investment cost (0 to 1).
    WT: dict = {}

    # WAT parameters (Water Turbine)
    WAT__feasible: bool = False  # Should this be considered for the central optimization.
    WAT__inv_base: float = 2000  # Unsubsidized investment in €/kW.
    WAT__life_time: int = 30  # Maximum life time in years.
    WAT__cost_om: float = 0.01  # Cost of operation and maintenance as a percentage of investment.
    WAT__min_cap: float = 0  # Minimum capacity in kW.
    WAT__max_cap: float = 2000  # Maximum capacity in kW.
    WAT__potential: float = 50000  # Maximum available potential in kW.
    WAT__inv_subsidy_rate: float = 0.0  # Investment subsidy rate as a fraction of investment cost (0 to 1).
    WAT: dict = {}

    # STC parameters (Solar Thermal Collector)
    STC__feasible: bool = False  # Should this be considered for the central optimization.
    STC__eta: float = 0.7  # Thermal efficiency between 0 and 1.
    STC__beta: float = 35.0  # Tilt angle of the solar collectors in degrees.
    STC__gamma: float = 0  # Azimuth angle (orientation) of the collectors in degrees (0=South, -90=East, 90=West).
    STC__inv_base: float = 800  # Unsubsidized investment in €/kW.
    STC__life_time: int = 20  # Maximum life time in years.
    STC__cost_om: float = 0.02  # Cost of operation and maintenance as a percentage of investment.
    STC__max_area: float = 5000  # Maximum installation area in square meters.
    STC__min_area: float = 0  # Minimum installation area in square meters.
    STC__g_stc: float = 1  # Global horizontal irradiance under STC in kW/m^2.
    STC__inv_subsidy_rate: float = 0.0  # Investment subsidy rate as a fraction of investment cost (0 to 1).
    STC: dict = {}

    # CHP parameters (Combined Heat and Power)
    CHP__feasible: bool = True  # Should this be considered for the central optimization.
    CHP__inv_base: float = 1200  # Unsubsidized investment in €/kW.
    CHP__eta_el: float = 0.4  # Electrical efficiency between 0 and 1.
    CHP__eta_th: float = 0.5  # Thermal efficiency between 0 and 1.
    CHP__life_time: int = 20  # Maximum life time in years.
    CHP__cost_om: float = 0.03  # Cost of operation and maintenance as a percentage of investment.
    CHP__min_cap: float = 0  # Minimum capacity in kW.
    CHP__max_cap: float = 1000  # Maximum capacity in kW.
    CHP__inv_subsidy_rate: float = 0.0  # Investment subsidy rate as a fraction of investment cost (0 to 1).
    CHP: dict = {}

    # BOI parameters (Boiler)
    BOI__feasible: bool = True  # Should this be considered for the central optimization.
    BOI__inv_base: float = 138  # Unsubsidized investment in €/kW.
    BOI__eta_th: float = 0.99  # Thermal efficiency between 0 and 1.
    BOI__life_time: int = 25  # Maximum life time in years.
    BOI__cost_om: float = 0.014  # Cost of operation and maintenance as a percentage of investment.
    BOI__min_cap: float = 0  # Minimum capacity in kW.
    BOI__max_cap: float = 500  # Maximum capacity in kW.
    BOI__inv_subsidy_rate: float = 0.0  # Investment subsidy rate as a fraction of investment cost (0 to 1).
    BOI: dict = {}

    # GHP parameters (Gas Heat Pump)
    GHP__feasible: bool = False  # Should this be considered for the central optimization.
    GHP__inv_base: float = 1000  # Unsubsidized investment in €/kW.
    GHP__COP: float = 3.5  # Coefficient of Performance (COP).
    GHP__life_time: int = 20  # Maximum life time in years.
    GHP__cost_om: float = 0.02  # Cost of operation and maintenance as a percentage of investment.
    GHP__min_cap: float = 0  # Minimum capacity in kW.
    GHP__max_cap: float = 500  # Maximum capacity in kW.
    GHP__inv_subsidy_rate: float = 0.0  # Investment subsidy rate as a fraction of investment cost (0 to 1).
    GHP: dict = {}

    # HP parameters (Heat Pump)
    HP__feasible: bool = False  # Should this be considered for the central optimization.
    HP__CCOP_feasible: bool = True  # Should this be considered for the central optimization (constant COP).
    HP__ASHP_feasible: bool = False  # Should this be considered for the central optimization (air source).
    HP__CSV_feasible: bool = False  # Should this be considered for the central optimization (CSV data).
    HP__inv_base: float = 1110  # Unsubsidized investment in €/kW.
    HP__life_time: int = 20  # Maximum life time in years.
    HP__cost_om: float = 0.033  # Cost of operation and maintenance as a percentage of investment.
    HP__min_cap: float = 0  # Minimum capacity in kW.
    HP__max_cap: float = 500  # Maximum capacity in kW.
    HP__ASHP_carnot_eff: float = 0.4  # Carnot efficiency of the Air Source Heat Pump between 0 and 1.
    HP__ASHP_supply_temp: float = 60  # Supply temperature of the Air Source Heat Pump in Celsius.
    HP__COP_const: float = 4  # Constant Coefficient of Performance (COP).
    HP__inv_subsidy_rate: float = 0.0  # Investment subsidy rate as a fraction of investment cost (0 to 1).
    HP: dict = {}

    # AirHP parameters (Air Source Heat Pump)
    AirHP__feasible: bool = True  # Should this be considered for the central optimization.
    AirHP__life_time: int = 25  # Maximum life time in years.
    AirHP__inv_base: float = 1110  # Unsubsidized investment in €/kWth.
    AirHP__cost_om: float = 0.033  # Cost of operation and maintenance as a percentage of investment.
    AirHP__min_cap: float = 0  # Minimum capacity in kWth.
    AirHP__max_cap: float = 20000  # Maximum capacity in kWth.
    AirHP__inv_subsidy_rate: float = 0.0  # Investment subsidy rate as a fraction of investment cost (0 to 1).
    AirHP: dict = {}

    # GroundHP parameters (Ground Source Heat Pump)
    GroundHP__feasible: bool = False  # Should this be considered for the central optimization.
    GroundHP__life_time: int = 20  # Maximum life time in years.
    GroundHP__inv_base: float = 1000  # Unsubsidized investment in €/kWth.
    GroundHP__cost_om: float = 0.025  # Cost of operation and maintenance as a percentage of investment.
    GroundHP__min_cap: float = 0  # Minimum capacity in kWth.
    GroundHP__max_cap: float = 500  # Maximum capacity in kWth.
    GroundHP__inv_subsidy_rate: float = 0.0  # Investment subsidy rate as a fraction of investment cost (0 to 1).
    GroundHP: dict = {}

    # EB parameters (Electric Boiler)
    EB__feasible: bool = True  # Should this be considered for the central optimization.
    EB__inv_base: float = 32.73  # Unsubsidized investment in €/kW.
    EB__eta_th: float = 0.99  # Thermal efficiency between 0 and 1.
    EB__life_time: int = 25  # Maximum life time in years.
    EB__cost_om: float = 0.01  # Cost of operation and maintenance as a percentage of investment.
    EB__min_cap: float = 0  # Minimum capacity in kW.
    EB__max_cap: float = 10000  # Maximum capacity in kW.
    EB__inv_subsidy_rate: float = 0.0  # Investment subsidy rate as a fraction of investment cost (0 to 1).
    EB: dict = {}

    # CC parameters (Chiller)
    CC__feasible: bool = False  # Should this be considered for the central optimization.
    CC__inv_base: float = 700  # Unsubsidized investment in €/kW.
    CC__COP: float = 3.5  # Coefficient of Performance (COP).
    CC__life_time: int = 20  # Maximum life time in years.
    CC__cost_om: float = 0.02  # Cost of operation and maintenance as a percentage of investment.
    CC__min_cap: float = 0  # Minimum capacity in kW.
    CC__max_cap: float = 500  # Maximum capacity in kW.
    CC__inv_subsidy_rate: float = 0.0  # Investment subsidy rate as a fraction of investment cost (0 to 1).
    CC: dict = {}

    # AirCC parameters (Air Cooled Chiller)
    AirCC__feasible: bool = False  # Should this be considered for the central optimization.
    AirCC__life_time: int = 20  # Maximum life time in years.
    AirCC__inv_base: float = 700  # Unsubsidized investment in €/kW.
    AirCC__cost_om: float = 0.02  # Cost of operation and maintenance as a percentage of investment.
    AirCC__min_cap: float = 0  # Minimum capacity in kW.
    AirCC__max_cap: float = 500  # Maximum capacity in kW.
    AirCC__inv_subsidy_rate: float = 0.0  # Investment subsidy rate as a fraction of investment cost (0 to 1).
    AirCC: dict = {}

    # AC parameters (Absorption Chiller)
    AC__feasible: bool = False  # Should this be considered for the central optimization.
    AC__inv_base: float = 1000  # Unsubsidized investment in €/kW.
    AC__eta_th: float = 0.75  # Thermal efficiency between 0 and 1.
    AC__life_time: int = 20  # Maximum life time in years.
    AC__cost_om: float = 0.02  # Cost of operation and maintenance as a percentage of investment.
    AC__min_cap: float = 0  # Minimum capacity in kW.
    AC__max_cap: float = 500  # Maximum capacity in kW.
    AC__inv_subsidy_rate: float = 0.0  # Investment subsidy rate as a fraction of investment cost (0 to 1).
    AC: dict = {}

    # BCHP parameters (Biomass Combined Heat and Power)
    BCHP__feasible: bool = False  # Should this be considered for the central optimization.
    BCHP__inv_base: float = 1140  # Unsubsidized investment in €/kW.
    BCHP__eta_el: float = 0.35  # Electrical efficiency between 0 and 1.
    BCHP__eta_th: float = 0.55  # Thermal efficiency between 0 and 1.
    BCHP__life_time: int = 20  # Maximum life time in years.
    BCHP__cost_om: float = 0.03  # Cost of operation and maintenance as a percentage of investment.
    BCHP__min_cap: float = 0  # Minimum capacity in kW.
    BCHP__max_cap: float = 1000  # Maximum capacity in kW.
    BCHP__inv_subsidy_rate: float = 0.0  # Investment subsidy rate as a fraction of investment cost (0 to 1).
    BCHP: dict = {}

    # BBOI parameters (Biomass Boiler)
    BBOI__feasible: bool = False  # Should this be considered for the central optimization.
    BBOI__inv_base: float = 570  # Unsubsidized investment in €/kW.
    BBOI__eta_th: float = 0.85  # Thermal efficiency between 0 and 1.
    BBOI__life_time: int = 20  # Maximum life time in years.
    BBOI__cost_om: float = 0.02  # Cost of operation and maintenance as a percentage of investment.
    BBOI__min_cap: float = 0  # Minimum capacity in kW.
    BBOI__max_cap: float = 500  # Maximum capacity in kW.
    BBOI__inv_subsidy_rate: float = 0.0  # Investment subsidy rate as a fraction of investment cost (0 to 1).
    BBOI: dict = {}

    # WCHP parameters (Waste Combined Heat and Power)
    WCHP__feasible: bool = False  # Should this be considered for the central optimization.
    WCHP__inv_base: float = 2000  # Unsubsidized investment in €/kW.
    WCHP__eta_el: float = 0.3  # Electrical efficiency between 0 and 1.
    WCHP__eta_th: float = 0.6  # Thermal efficiency between 0 and 1.
    WCHP__life_time: int = 20  # Maximum life time in years.
    WCHP__cost_om: float = 0.03  # Cost of operation and maintenance as a percentage of investment.
    WCHP__min_cap: float = 0  # Minimum capacity in kW.
    WCHP__max_cap: float = 1000  # Maximum capacity in kW.
    WCHP__inv_subsidy_rate: float = 0.0  # Investment subsidy rate as a fraction of investment cost (0 to 1).
    WCHP: dict = {}

    # WBOI parameters (Waste Boiler)
    WBOI__feasible: bool = False  # Should this be considered for the central optimization.
    WBOI__inv_base: float = 700  # Unsubsidized investment in €/kW.
    WBOI__eta_th: float = 0.8  # Thermal efficiency between 0 and 1.
    WBOI__life_time: int = 20  # Maximum life time in years.
    WBOI__cost_om: float = 0.02  # Cost of operation and maintenance as a percentage of investment.
    WBOI__min_cap: float = 0  # Minimum capacity in kW.
    WBOI__max_cap: float = 500  # Maximum capacity in kW.
    WBOI__inv_subsidy_rate: float = 0.0  # Investment subsidy rate as a fraction of investment cost (0 to 1).
    WBOI: dict = {}

    # ELYZ parameters (Electrolyzer)
    ELYZ__feasible: bool = False  # Should this be considered for the central optimization.
    ELYZ__inv_base: float = 1500  # Unsubsidized investment in €/kW.
    ELYZ__eta_el: float = 0.7  # Electrical efficiency between 0 and 1.
    ELYZ__life_time: int = 20  # Maximum life time in years.
    ELYZ__cost_om: float = 0.03  # Cost of operation and maintenance as a percentage of investment.
    ELYZ__min_cap: float = 0  # Minimum capacity in kW.
    ELYZ__max_cap: float = 1000  # Maximum capacity in kW.
    ELYZ__inv_subsidy_rate: float = 0.0  # Investment subsidy rate as a fraction of investment cost (0 to 1).
    ELYZ: dict = {}

    # FC parameters (Fuel Cell)
    FC__feasible: bool = False  # Should this be considered for the central optimization.
    FC__inv_base: float = 1800  # Unsubsidized investment in €/kW.
    FC__eta_el: float = 0.5  # Electrical efficiency between 0 and 1.
    FC__eta_th: float = 0.4  # Thermal efficiency between 0 and 1.
    FC__life_time: int = 20  # Maximum life time in years.
    FC__cost_om: float = 0.03  # Cost of operation and maintenance as a percentage of investment.
    FC__min_cap: float = 0  # Minimum capacity in kW.
    FC__max_cap: float = 1000  # Maximum capacity in kW.
    FC__enable_heat_diss: bool = True  # Enable/disable heat dissipation for the fuel cell.
    FC__inv_subsidy_rate: float = 0.0  # Investment subsidy rate as a fraction of investment cost (0 to 1).
    FC: dict = {}

    # H2S parameters (Hydrogen Storage)
    H2S__feasible: bool = False  # Should this be considered for the central optimization.
    H2S__inv_base: float = 1200  # Unsubsidized investment in €/kWh.
    H2S__sto_loss: float = 0.0  # Storage loss as a fraction.
    H2S__life_time: int = 20  # Maximum life time in years.
    H2S__cost_om: float = 0.02  # Cost of operation and maintenance as a percentage of investment.
    H2S__min_cap: float = 0  # Minimum capacity in kWh.
    H2S__max_cap: float = 5000  # Maximum capacity in kWh.
    H2S__inv_subsidy_rate: float = 0.0  # Investment subsidy rate as a fraction of investment cost (0 to 1).
    H2S: dict = {}

    # SAB parameters (Sabatier Reactor)
    SAB__feasible: bool = False  # Should this be considered for the central optimization.
    SAB__inv_base: float = 2000  # Unsubsidized investment in €/kW.
    SAB__eta: float = 0.6  # Round-trip efficiency between 0 and 1.
    SAB__life_time: int = 20  # Maximum life time in years.
    SAB__cost_om: float = 0.03  # Cost of operation and maintenance as a percentage of investment.
    SAB__min_cap: float = 0  # Minimum capacity in kW.
    SAB__max_cap: float = 1000  # Maximum capacity in kW.
    SAB__inv_subsidy_rate: float = 0.0  # Investment subsidy rate as a fraction of investment cost (0 to 1).
    SAB: dict = {}

    # TES parameters (Thermal Energy Storage)
    TES__feasible: bool = True  # Should this be considered for the central optimization.
    TES__inv_base: float = 640  # Unsubsidized investment in €/m^3.
    TES__sto_loss: float = 0.01  # Storage loss per hour as a fraction.
    TES__life_time: int = 20  # Maximum life time in years.
    TES__cost_om: float = 0.013  # Cost of operation and maintenance as a percentage of investment.
    TES__min_vol: float = 0  # Minimum storage volume in cubic meters.
    TES__max_vol: float = 5000  # Maximum storage volume in cubic meters.
    TES__delta_T: float = 30  # Temperature difference between charged and discharged state in Celsius.
    TES__soc_init: float = 0.5  # Initial state of charge between 0 and 1.
    TES__inv_subsidy_rate: float = 0.0  # Investment subsidy rate as a fraction of investment cost (0 to 1).
    TES: dict = {}

    # CTES parameters (Cold Thermal Energy Storage)
    CTES__feasible: bool = False  # Should this be considered for the central optimization.
    CTES__inv_base: float = 1300  # Unsubsidized investment in €/m^3.
    CTES__sto_loss: float = 0.01  # Storage loss per hour as a fraction.
    CTES__life_time: int = 20  # Maximum life time in years.
    CTES__cost_om: float = 0.01  # Cost of operation and maintenance as a percentage of investment.
    CTES__min_vol: float = 0  # Minimum storage volume in cubic meters.
    CTES__max_vol: float = 5000  # Maximum storage volume in cubic meters.
    CTES__delta_T: float = 30  # Temperature difference between charged and discharged state in Celsius.
    CTES__inv_subsidy_rate: float = 0.0  # Investment subsidy rate as a fraction of investment cost (0 to 1).
    CTES: dict = {}

    # BAT parameters (Battery Storage)
    BAT__feasible: bool = False  # Should this be considered for the central optimization.
    BAT__inv_base: float = 200  # Unsubsidized investment in €/kWh.
    BAT__life_time: int = 15  # Maximum life time in years.
    BAT__cost_om: float = 0.02  # Cost of operation and maintenance as a percentage of investment.
    BAT__min_cap: float = 0  # Minimum capacity in kWh.
    BAT__max_cap: float = 200  # Maximum capacity in kWh.
    BAT__sto_loss: float = 0.0  # Storage loss as a fraction.
    BAT__soc_init: float = 0.5  # Initial state of charge between 0 and 1.
    BAT__inv_subsidy_rate: float = 0.0  # Investment subsidy rate as a fraction of investment cost (0 to 1).
    BAT: dict = {}

    # GS parameters (Gas Storage)
    GS__feasible: bool = False  # Should this be considered for the central optimization.
    GS__inv_base: float = 150  # Unsubsidized investment in €/kWh.
    GS__life_time: int = 20  # Maximum life time in years.
    GS__cost_om: float = 0.01  # Cost of operation and maintenance as a percentage of investment.
    GS__min_cap: float = 0  # Minimum capacity in kWh.
    GS__max_cap: float = 10000  # Maximum capacity in kWh.
    GS__sto_loss: float = 0.0  # Storage loss as a fraction.
    GS__soc_init: float = 0.5  # Initial state of charge between 0 and 1.
    GS__inv_subsidy_rate: float = 0.0  # Investment subsidy rate as a fraction of investment cost (0 to 1).
    GS: dict = {}

    @model_validator(mode='after')
    def build_device_dicts(self) -> 'DecentralDeviceConfig':
        """Build all device dictionaries from individual parameters."""

        # Create a list of field names to avoid RuntimeError during iteration
        field_names = list(self.__dict__.keys())

        # Get all field names from the model
        for field_name in field_names:
            # Check if this is a dictionary field (uppercase device name)
            if isinstance(getattr(self, field_name), dict):
                # Only build if the dictionary is empty
                if getattr(self, field_name) == {}:
                    device_dict = {}
                    prefix = f"{field_name}__"

                    # Find all attributes that start with this device prefix
                    for attr_name in field_names:  # Use the snapshot here too
                        if attr_name.startswith(prefix):
                            # Remove the prefix to get the dictionary key
                            dict_key = attr_name[len(prefix):]
                            device_dict[dict_key] = getattr(self, attr_name)

                    # Calculate inv_var from inv_base and inv_subsidy_rate
                    if 'inv_base' in device_dict and 'inv_subsidy_rate' in device_dict:
                        device_dict['inv_var'] = device_dict['inv_base'] * (1 - device_dict['inv_subsidy_rate'])

                    # Set the dictionary first
                    setattr(self, field_name, device_dict)

                    # Now delete the individual attributes
                    for attr_name in field_names:
                        if attr_name.startswith(prefix):
                            delattr(self, attr_name)

        return self

    model_config = SettingsConfigDict(
        env_prefix="C_",
        env_file=".centraldeviceconfig",
        extra="ignore"
    )

### Global Config Classes ###

class GlobalConfig(BaseModel):
    """
    GlobalConfig class to manage all configurations for the district generator.
    This class aggregates all individual configuration classes and provides a unified interface
    to access them. It is designed to be initialized with an environment file that contains
    configuration parameters for each component.
    Note: All parameters defined in this '.env.CONFIG.' will override the default values in config.py

    Attributes
    ----------
    location : LocationConfig
        Configuration parameters related to the location of the buildings.
    time : TimeConfig
        Configuration parameters related to time settings, such as time resolution and cluster length.
    design_building : DesignBuildingConfig
        Configuration parameters for design aspects of buildings in the district.
    eco : EcoConfig
        Economic parameters, including prices and CO2 emissions for various energy sources.
    physics : PhysicsConfig
        Physical constants and parameters used in the districtgenerator.
    pyomo : PyomoConfig
        Configuration parameters for the Pyomo optimization solver.
    heatgrid : HeatGridConfig
        Configuration parameters for the heat grid, including temperatures and heat transfer.
    ehdo : EHDOConfig
        Configuration parameters for the EHDO (Energy and Heat Distribution Optimization) system.
    decentral : DecentralDeviceConfig
        Configuration parameters for decentralized devices in the district.
    central : CentralDeviceConfig
        Configuration parameters for central devices in the district.
    calendar : CalendarConfig
        Configuration parameters for calendar settings, such as holidays and initial days.
    scenario_name : ScenarioName
        The name of the scenario being configured, used for identification and output purposes.

    """
    location: 'LocationConfig'
    time: 'TimeConfig'
    design_building: 'DesignBuildingConfig'
    eco: 'EcoConfig'
    physics: 'PhysicsConfig'
    pyomo: 'PyomoConfig'
    heatgrid: 'HeatGridConfig'
    ehdo: 'EHDOConfig'
    decentral: 'DecentralDeviceConfig'
    central: 'CentralDeviceConfig'
    calendar: 'CalendarConfig'
    scenario_name: ScenarioName
    flags: flags

class Settings(BaseSettings):
    """
    Settings class to manage global configuration parameters.
    This class is used to load configuration parameters from an environment file.
    """
    env_file: str = '.env.CONFIG.EXAMPLE'

    class Config:
        env_file = '.env.CONFIG.EXAMPLE'  # Default .env file if no env_file is provided
        env_file_encoding = 'utf-8'
        extra = 'ignore' # Ignores all other variables in the .env.CONFIG file


def load_global_config(env_file: Optional[str] = None) -> GlobalConfig:
    """
    Load the global configuration from the specified environment file.
    If no environment file is provided, it defaults to standard parameters defined in the config classes.
    For error handling, it prints the used environment file path.
    Note: All parameters defined in '.env.CONFIG.' will override the default values in config.py

    Parameters
    ----------
    env_file : Optional[str]
        The path to the environment file. If None, it uses the default from Settings.
        Place config in the data folder of the districtgenerator package to use ".env.NAME" or use
        absolute paths "c:/path/to/.env.CONFIG.EXAMPLE" or "/path/to/.env.CONFIG.EXAMPLE".

    Returns
    -------
    GlobalConfig
        An instance of GlobalConfig containing all configurations loaded from the environment file.

    """
    if env_file is None:
        settings = Settings()  # Load settings from the .env file
        env_file = settings.env_file

    script_path = Path(__file__).resolve()
    project_root = script_path.parent.parent

    env_file_path = str(project_root / "data" / env_file)

    if not os.path.exists(env_file_path):
        raise FileNotFoundError(
            f"Configuration file not found. \n"
            f"  - Looked for: {env_file_path}\n"
            f"  - Based on script location: {script_path}"
        )

    os.environ["ENV_FILE"] = env_file_path
    print(f'Using config: {os.environ["ENV_FILE"]}')

    return GlobalConfig(
        location=LocationConfig(_env_file=env_file_path),
        time=TimeConfig(_env_file=env_file_path),
        design_building=DesignBuildingConfig(_env_file=env_file_path),
        eco=EcoConfig(_env_file=env_file_path),
        physics=PhysicsConfig(_env_file=env_file_path),
        pyomo=PyomoConfig(_env_file=env_file_path),
        heatgrid=HeatGridConfig(_env_file=env_file_path),
        ehdo=EHDOConfig(_env_file=env_file_path),
        decentral=DecentralDeviceConfig(_env_file=env_file_path),
        central=CentralDeviceConfig(_env_file=env_file_path),
        calendar=CalendarConfig(_env_file=env_file_path),
        scenario_name = ScenarioName(_env_file=env_file_path),
        flags=flags(_env_file=env_file_path)
    )
