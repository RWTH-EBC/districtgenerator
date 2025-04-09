from dataclasses import dataclass, field
from typing import Any, Dict, List
# dict = {
#     "location_config": {
#         "time_zone": 1, #hgrrg
# }

# dictonary class?

@dataclass
class LocationConfig:
    time_zone: float
    albedo: float
    try_year: str
    try_type: str
    zip_code: str

    ALLOWED_TRY_YEARS = {"TRY2015", "TRY2045"}
    ALLOWED_TRY_TYPES = {"Jahr", "Somm", "Wint"}

    def __post_init__(self):
        if self.try_year not in self.ALLOWED_TRY_YEARS:
            raise ValueError(f"try_year must be one of {self.ALLOWED_TRY_YEARS}, got '{self.try_year}'")
        if self.try_type not in self.ALLOWED_TRY_TYPES:
            raise ValueError(f"try_type must be one of {self.ALLOWED_TRY_TYPES}, got '{self.try_type}'")
        if not (0.0 <= self.albedo <= 1.0):
            raise ValueError("albedo must be between 0.0 and 1.0.")

@dataclass
class TimeConfig:
    time_resolution: int = 3600
    cluster_length: int = 604800
    cluster_number: int = 4
    data_resolution: int = 3600
    data_length: int = 31536000

@dataclass
class DesignBuildingConfig:
    T_set_min: float = 20.0
    T_set_min_night: float = 18.0
    T_set_max: float = 23.0
    T_set_max_night: float = 28.0
    T_bivalent: float = -2.0
    T_heatlimit: float = 15.0
    ventilation_rate: float = 0.5

@dataclass
class EcoConfig:
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

@dataclass
class PhysicsConfig:
    rho_air: float = 1.2 # kg/m3
    c_p_air: float = 1000.0
    rho_water: float = 1000.0
    c_p_water: float = 4.18

@dataclass
class GurobiConfig:
    ModelName: str = "Central_Operational_Optimization" # Name of the model
    TimeLimit: int = 3600         # seconds
    MIPGap: float = 0.01
    MIPFocus: int = 3 #
    NonConvex: int = 2
    NumericFocus: int = 3
    PoolSolution: int = 3
    DualReductions: int = 0

@dataclass
class HeatGridConfig:
    T_hot: float = 332.15           # Flow temperature in Kelvin
    T_cold: float = 323.15          # Return temperature in Kelvin
    delta_T_heatTransfer: float = 5 # Temperature difference in heat exchangers (K)


@dataclass
class EHDOConfig:
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


@dataclass
class BuildingConfig:
    buildings: List[Dict[str, Any]]
    heater_types: List[str]
    night_setback: bool = False
    PV: bool = False
    STC: bool = False
    EV: bool = False
    BAT: bool = False
    storage: Dict[str, float] = field(
        default_factory=lambda: {
            "f_TES": 35.0,
            "f_BAT": 1.0,
            "f_EV": 6000.0,
            "f_PV": 0.4,
            "f_STC": 0.04
        }
    )
    charging_modes: List[str] = field(default_factory=lambda: ["on_demand"])

    ALLOWED_CHARGING_MODES = {"on_demand", "night_charge", "pv_optimized"}

    def __post_init__(self):
        for mode in self.charging_modes:
            if mode not in self.ALLOWED_CHARGING_MODES:
                raise ValueError(f"Invalid charging mode: {mode}")

        storage_ranges = {
            "f_TES": (20.0, 50.0),
            "f_BAT": (0.5, 2.0),
            "f_EV": (3000.0, 9000.0),
            "f_PV": (0.2, 1.0),
            "f_STC": (0.02, 0.08)
        }
        for key, (low, high) in storage_ranges.items():
            if key in self.storage:
                value = self.storage[key]
                if not (low <= value <= high):
                    raise ValueError(f"{key} must be between {low} and {high}.")

# New Config Class for Device Data
#@dataclass
#class CentralDeviceConfig:

#@dataclass
#class DecentralDeviceConfig:

#@dataclass
#class PhysicsConfig:
