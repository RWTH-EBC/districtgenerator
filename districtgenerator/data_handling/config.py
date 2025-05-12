from dataclasses import dataclass, field
import os
from typing import Any, Dict, List, ClassVar, Set, Optional
from pydantic import BaseModel, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict
from districtgenerator.data_handling.central_device_config import CentralDeviceConfig
from districtgenerator.data_handling.decentral_device_config import DecentralDeviceConfig
from pathlib import Path


class LocationConfig(BaseSettings):
    timeZone: float = 10 #1
    albedo: float = 0.2
    TRYYear: str = 'TRY2015'
    TRYType: str = 'Jahr'
    zip: str = '52078'

    ALLOWED_TRY_YEARS: ClassVar[Set[str]] = {"TRY2015", "TRY2045"}
    ALLOWED_TRY_TYPES: ClassVar[Set[str]] ={"Jahr", "Somm", "Wint"}

    model_config = SettingsConfigDict(
        env_file= ".locationconfig",
        extra="allow" 
    )

    def __post_init__(self):
        if self.TRYYear not in self.ALLOWED_TRY_YEARS:
            raise ValueError(f"try_year must be one of {self.ALLOWED_TRY_YEARS}, got '{self.TRYYear}'")
        if self.TRYType not in self.ALLOWED_TRY_TYPES:
            raise ValueError(f"try_type must be one of {self.ALLOWED_TRY_TYPES}, got '{self.TRYType}'")
        if not (0.0 <= self.albedo <= 1.0):
            raise ValueError("albedo must be between 0.0 and 1.0.")

class TimeConfig(BaseSettings):
    timeResolution: int = 3600
    clusterLength: int = 604800
    clusterNumber: int = 4
    dataResolution: int = 3600
    dataLength: int = 31536000
    holidays2015: list = field(default_factory=lambda: [1, 93, 96, 121, 134, 145, 155, 275, 305, 358, 359, 360, 365],)
    holidays2045: list = field(default_factory=lambda: [1, 97, 100, 121, 138, 149, 159, 276, 305, 358, 359, 360, 365],)
    initial_day_2015: list = field(default_factory=lambda: [4])
    initial_day_2045: list = field(default_factory=lambda: [6])
    model_config = SettingsConfigDict(
        env_file= ".timeconfig",
        extra="allow" 
    )

class DesignBuildingConfig(BaseSettings):
    T_set_min: float = 20.0
    T_set_min_night: float = 18.0
    T_set_max: float = 23.0
    T_set_max_night: float = 28.0
    T_bivalent: float = -2.0
    T_heatlimit: float = 15.0
    ventilation_rate: float = 0.5
    buildings_short: list = field(default_factory=lambda: ['SFH', 'MFH', 'TH', 'AB'])
    buildings_long: list = field(default_factory=lambda: ['single_family_house', 'multi_family_house', 'terraced_house', 'apartment_block'])
    retrofit_short: list = field(default_factory=lambda: [0, 1, 2])
    retrofit_long: list = field(default_factory=lambda: ['tabula_standard', 'tabula_retrofit', 'tabula_adv_retrofit'])
    dhwload: list = field(default_factory=lambda: [4662.1, 4662.1, 4662.1, 3999.8])
    mean_drawoff_vol_per_day: list = field(default_factory=lambda: [40, 40, 40, 40])
    model_config = SettingsConfigDict(
        env_file= ".designbuildingconfig",
        extra="allow" 
    )

class EcoConfig(BaseSettings):
    price_supply_el: float = 0.32
    revenue_feed_in_el: float = 0.0811
    price_supply_gas: float = 0.12
    price_hydrogen: float = 0.1
    price_waste: float = 0.1
    price_biomass: float = 0.05
    co2_el_grid: float = 0.49
    co2_gas: float = 0.25
    co2_biom: float = 0.35
    co2_waste: float = 0.0
    co2_hydrogen: float = 0.0
    model_config = SettingsConfigDict(
        env_file= ".ecoconfig",
        extra="allow" 
    )

class PhysicsConfig(BaseSettings):
    rho_air: float = 1.2 # kg/m3
    c_p_air: float = 1000.0
    rho_water: float = 1000.0
    c_p_water: float = 4.18
    model_config = SettingsConfigDict(
        env_file= ".physicsconfig",
        extra="allow" 
    )

class GurobiConfig(BaseSettings):
    ModelName: str = "Central_Operational_Optimization" # Name of the model
    TimeLimit: int = 3600         # seconds
    MIPGap: float = 0.01
    MIPFocus: int = 3 #
    NonConvex: int = 2
    NumericFocus: int = 3
    PoolSolution: int = 3
    DualReductions: int = 0
    model_config = SettingsConfigDict(
        env_file= ".gurobiconfig",
        extra="allow" 
    )

class HeatGridConfig(BaseSettings):
    T_hot: float = 332.15           # Flow temperature in Kelvin
    T_cold: float = 323.15          # Return temperature in Kelvin
    delta_T_heatTransfer: float = 5 # Temperature difference in heat exchangers (K)
    model_config = SettingsConfigDict(
        env_file= ".heatgridconfig",
        extra="allow" 
    )

class EHDOConfig(BaseSettings):
    # Electricity configuration
    enable_supply_el: bool = True
    enable_feed_in_el: bool = True
    enable_price_cap_el: bool = False
    price_cap_el: float = 60
    enable_cap_limit_el: bool = False
    cap_limit_el: float = 100000  # in kW
    enable_supply_limit_el: bool = False
    supply_limit_el: float = 100000  # in MWh/year

    # Gas configuration
    enable_supply_gas: bool = False
    enable_price_cap_gas: bool = False
    price_cap_gas: float = 0.04  # €/kWh
    enable_feed_in_gas: bool = False
    revenue_feed_in_gas: float = 0.02  # €/kWh
    enable_cap_limit_gas: bool = False
    cap_limit_gas: float = 1000000  # in MWh/year

    # Biomass configuration
    enable_supply_biomass: bool = False
    enable_supply_limit_biomass: bool = False
    supply_limit_biomass: float = 1000000  # in MWh/year

    # Hydrogen configuration
    enable_supply_hydrogen: bool = False
    enable_supply_limit_hydrogen: bool = False
    supply_limit_hydrogen: float = 1000000  # in MWh/year

    # Waste configuration
    enable_supply_waste: bool = False
    enable_supply_limit_waste: bool = False
    supply_limit_waste: float = 1000000  # in MWh/year

    # Additional gas supply limit (duplicate naming in JSON template - adjust if needed)
    supply_limit_gas: float = 1000000  # in MWh/year
    enable_supply_limit_gas: bool = False

    # Other options
    peak_dem_met_conv: bool = True
    co2_tax: float = 0  # €/t_CO2
    co2_el_feed_in: float = 0  # kg/kWh
    co2_gas_feed_in: float = 0  # kg/kWh
    optim_focus: int = 0  # 0 = cost only; 1 = CO2 only
    interest_rate: float = 0.05
    observation_time: int = 20  # years
    n_clusters: int = 12  # days

    # Helper attributes for unit formatting
    unit_placeholder: str = " - "  # used for cases where unit is a placeholder
    unit_dash: str = "-"         # used for cases where unit is a dash
    model_config = SettingsConfigDict(
        env_file= ".ehdoonfig",
        extra="allow" 
    )


class GlobalConfig(BaseModel):
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

class Settings(BaseSettings):
    env_file: str = '.env.CONFIG'

    class Config:
        env_file = '.env.CONFIG'  # Default .env file
        env_file_encoding = 'utf-8'
        extra = 'allow'


def load_global_config(env_file: Optional[str] = None) -> GlobalConfig:
    if env_file is None:
        settings = Settings()  # Load settings from the .env file
        env_file = settings.env_file

    os.environ["ENV_FILE"] = env_file
    print(f'Using config: {os.environ["ENV_FILE"]}')

    return GlobalConfig(
        location=LocationConfig(_env_file=env_file),
        time=TimeConfig(_env_file=env_file),
        design_building=DesignBuildingConfig(_env_file=env_file),
        eco=EcoConfig(_env_file=env_file),
        physics=PhysicsConfig(_env_file=env_file),
        gurobi=GurobiConfig(_env_file=env_file),
        heatgrid=HeatGridConfig(_env_file=env_file),
        ehdo=EHDOConfig(_env_file=env_file),
        decentral=DecentralDeviceConfig(_env_file=env_file),
        central=CentralDeviceConfig(_env_file=env_file)
    )

if __name__ == "__main__":
    # Example usage Works
    try:
        config = load_global_config()
        print(config.location.albedo)
    except ValidationError as e:
        print("Error loading configuration:", e)