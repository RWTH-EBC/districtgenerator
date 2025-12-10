from dataclasses import field
import os
from typing import ClassVar, Set, Optional
from pydantic import BaseModel, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from districtgenerator.data_handling.central_device_config import CentralDeviceConfig
from districtgenerator.data_handling.decentral_device_config import DecentralDeviceConfig
from pathlib import Path

### Helper functions ###
def parse_int_list(value: any) -> list[int]:
    """
    Parses a comma-separated string of integers into a list of integers.
    If the input is already a list, it returns it directly.

    Parameters
    ----------
    value : any
        The input value to parse. It can be a list of integers, a comma-separated string
        of integers, or an empty string.

    Returns
    -------
    list[int]
        A list of integers parsed from the input value.
    """
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        if not value:
            return []
        return [int(x.strip()) for x in value.split(',')]
    raise ValueError(f"Cannot parse {type(value)} into a list of integers")

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
    zip: str = '52062'          # Zip code of the location.

    ALLOWED_TRY_YEARS: ClassVar[Set[str]] = {"TRY2015", "TRY2045"}
    ALLOWED_TRY_TYPES: ClassVar[Set[str]] = {"Jahr", "Somm", "Wint"}

    model_config = SettingsConfigDict(
        extra="allow"
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

    model_config = SettingsConfigDict(
        extra="allow" 
    )

class DesignBuildingConfig(BaseSettings):
    """
    DesignBuildingConfig class to manage design parameters for all buildings in the district generator.
    This class contains parameters related to building design, such as temperature settings, ventilation rates,
    building types, retrofit options, and domestic hot water (DHW) load.
    """
    T_set_min: float = 20.0         # Required minimum indoor temperature (for heating load calculation) in degrees Celsius
    T_set_min_night: float = 18.0   # Required minimum indoor temperature at night (for heating load calculation) in degrees Celsius
    T_set_min_free_day: float = 16.0 # Minimum required indoor temperature on a non-working day in a non-residential building (for heating load calculations)
    T_set_max: float = 23.0         # Required maximum indoor temperature (for cooling load calculation) in degrees Celsius
    T_set_max_night: float = 28.0   # Required maximum indoor temperature at night (for cooling load calculation) in degrees Celsius
    T_bivalent: float = -2.0        # Dual mode temperature (for heat pump design) in degrees Celsius
    T_heatlimit: float = 15.0       # Limit temperature (for heat pump design)
    ventilation_rate: float = 0.5   # Room ventilation rate in 1/h (per hour)

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
        extra="allow" 
    )

class EcoConfig(BaseSettings):
    """ EcoConfig class to manage economic parameters for the district generator.
    This class contains parameters related to energy prices, CO2 emissions, and other economic factors
    used in the district generator.
    """

    price_supply_el: float = 0.3969         # Electricity price in €/kWh
    revenue_feed_in_el: float = 0.0794      # Feed-in electricity price in €/kWh
    price_supply_el_network: float = 0.0    # Electricity price for selling to network in €/kWh
    revenue_feed_in_el_network: float = 0.0 # Revenue for buying from network in €/kWh
    price_supply_gas: float = 0.1236        # Gas price in €/kWh
    price_hydrogen: float = 0.1             # Hydrogen price in €/kWh
    price_waste: float = 0.1                # Waste price in €/kWh
    price_biomass: float = 0.05             # Biomass price in €/kWh
    co2_el_grid: float = 0.363              # Co2 emissions for electricity import (grid mix) in kg/kWh
    co2_gas: float = 0.201                  # Co2 emissions for burning natural gas in kg/kWh
    co2_biom: float = 0.35                  # Co2 emissions for burning biomass in kg/kWh
    co2_waste: float = 0.0                  # Co2 emissions for burning waste in kg/kWh
    co2_hydrogen: float = 0.0               # Co2 emissions for burning hydrogen in kg/kWh

    model_config = SettingsConfigDict(
        extra="allow" 
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
        extra="allow" 
    )

class GurobiConfig(BaseSettings):
    """
    GurobiConfig class to manage the configuration of the Gurobi optimization solver.
    """
    ModelName: str = "Central_Operational_Optimization" # Name of the model
    TimeLimit: int = 3600                               # The time limit for the optimization in seconds
    MIPGap: float = 0.01                                # acceptable MIP gap, Default: 1%
    MIPFocus: int = 3                                   # focus of the MIP solver, Default: 3 (balance between speed and solution quality)
    NonConvex: int = 2                                  # non-convexity setting, Default: 2
    NumericFocus: int = 3                               # numeric focus, Default: 3
    PoolSolution: int = 3                               # number of solutions to pool, Default: 3
    DualReductions: int = 0                             # level of dual reductions to apply, Default: 0

    model_config = SettingsConfigDict(
        extra="allow" 
    )

class HeatGridConfig(BaseSettings):
    """
    Manages the configuration for the district heating network.

    This class defines the default parameters for the physical, thermal, and economic
    properties of a heating grid. It includes settings for operating temperatures,
    physical dimensions, material properties, and costs.
    """

    # District and Network Layout Parameters
    FAR: float = 1.17                   # Floor area ratio (German: Geschossflächenzahl); Source: Dettmar, J.,et al., 2020. Energetische Stadtraumtypen
    D_heating_network: float = 1.0      # Distance between the centerlines of supply and return pipelines in meters.
    D_cooling_network: float = 1.0      # Distance between the centerlines of supply and return pipelines in meters.
    grid_depth: float = 1.0             # Installation depth of the grid beneath the surface in meters.
    life_time: int = 40                 # Lifetime of the heating network and its components in years.

    # Thermal Operating Parameters
    T_hot_heating_network: float = 80.0  # Flow temperature of the heating network in degrees Celsius.
    T_cold_heating_network: float = 60.0 # Return temperature of the heating network in degrees Celsius.
    T_hot_cooling_network: float = 12.0  # Flow temperature of the cooling network in degrees Celsius.
    T_cold_cooling_network: float = 6.0  # Return temperature of the cooling network in degrees Celsius.
    delta_T_heatTransfer: float = 5.0    # Temperature difference in heat exchangers in Kelvin.

    # Material and Environmental Properties
    asphaltlayer: int = 1               # Consideration of asphalt layer (1 = yes, 0 = no).
    d_asphalt: float = 0.18             # Asphalt layer thickness in meters.
    k_soil: float = 1.52                # Soil heat conductivity in W/(m*K). Source: Median value from table 4.1 Wessolek, G. (2022). Parametrisierung thermischer Bodeneigenschaften: Endbericht
    k_PUF: float = 0.03                 # Polyurethane foam heat conductivity. Source: VDI Wärmeatlas

    # Economic and Loss Parameters
    h_loss_substation: float = 4.5      # Heat losses at the substation as a percentage (%). Source: Technikkatalog Wärmeplanung 2024
    C_substation: float = 277.79        # Investment costs for the substation in €/kW_th. Source: Technikkatalog Wärmeplanung 2024
    C_om: float = 1.44                  # Variable Operation & Maintenance (O&M) costs in €/MWh_th. Source: Technikkatalog Wärmeplanung 2024

    model_config = SettingsConfigDict(
        extra="allow"
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
    revenue_feed_in_gas: float = 0.02       # Revenue for natural gas feed-in €/kWh
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

    # Additional gas supply limit (duplicate naming in JSON template - adjust if needed)
    supply_limit_gas: float = 1000000       # Maximum available gas in MWh/year
    enable_supply_limit_gas: bool = False   # Enable limit annual gas import, bool.

    # Other options
    peak_dem_met_conv: bool = True  # Meet peak demands of unclustered demands, bool.
    co2_tax: float = 0              # CO2 tax. Tax on CO2 emissions due to burning natural gas, biomass or waste in €/t_CO2
    co2_el_feed_in: float = 0       # CO₂ emission credit for electricity feed-in kg/kWh
    co2_gas_feed_in: float = 0      # CO₂ emission credit for gas feed-in kg/kWh
    optim_focus: int = 0            # Optimization focus. Annual costs vs CO2 emissions. '0' means only cost optimization; '1' means only CO2 optimization.
    optim_dimension: int = 0        # NEW: Optimization dimension. '0' means single-district optimization; '1' means interconnected optimization of several districts.
    interest_rate: float = 0.05     # Interest rate. The interest rate affects the annualization of the investments according to VDI 2067.
    observation_time: int = 20      # Project lifetime. The project lifetime affects annualization of investments according to VDI 2067 in years
    n_clusters: int = 12            # Number of design days.

    # Helper attributes for unit formatting
    unit_placeholder: str = " - "   # used for cases where unit is a placeholder
    unit_dash: str = "-"            # used for cases where unit is a dash

    model_config = SettingsConfigDict(
        extra="allow"
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
        extra="allow"
    )

class ScenarioName(BaseSettings):
    """
    ScenarioName class to manage the scenario name for the district generator.
    """
    scenario_name: str = 'base_scenario' # default value for scenario name

    model_config = SettingsConfigDict(
        extra="allow"
    )



### General GlobalConfig class ###

class GlobalConfig(BaseModel):
    """
    GlobalConfig class to manage all configurations for the district generator.
    This class aggregates all individual configuration classes and provides a unified interface
    to access them. It is designed to be initialized with an environment file that contains
    configuration parameters for each component.

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
    gurobi : GurobiConfig
        Configuration parameters for the Gurobi optimization solver.
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
    gurobi: 'GurobiConfig'
    heatgrid: 'HeatGridConfig'
    ehdo: 'EHDOConfig'
    decentral: 'DecentralDeviceConfig'
    central: 'CentralDeviceConfig'
    calendar: 'CalendarConfig'
    scenario_name: ScenarioName

class Settings(BaseSettings):
    """
    Settings class to manage global configuration parameters.
    This class is used to load configuration parameters from an environment file.
    """
    env_file: str = '.env.CONFIG.EXAMPLE'

    class Config:
        env_file = '.env.CONFIG.EXAMPLE'  # Default .env file if no env_file is provided
        env_file_encoding = 'utf-8'
        extra = 'allow'


def load_global_config(env_file: Optional[str] = None) -> GlobalConfig:
    """
    Load the global configuration from the specified environment file.
    If no environment file is provided, it defaults to standard parameters defined in the config classes.
    For error handling, it prints the used environment file path.

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
        gurobi=GurobiConfig(_env_file=env_file_path),
        heatgrid=HeatGridConfig(_env_file=env_file_path),
        ehdo=EHDOConfig(_env_file=env_file_path),
        decentral=DecentralDeviceConfig(_env_file=env_file_path),
        central=CentralDeviceConfig(_env_file=env_file_path),
        calendar=CalendarConfig(_env_file=env_file_path),
        scenario_name = ScenarioName(_env_file=env_file_path)
    )


if __name__ == "__main__":
    # Example usage
    try:
        config = load_global_config(env_file=".env.CONFIG.EXAMPLe") # replace with your actual env file path
        print(config.location.timeZone, config.calendar.holidays2015, config.scenario_name.scenario_name)
    except ValidationError as e:
        print("Error loading configuration:", e)