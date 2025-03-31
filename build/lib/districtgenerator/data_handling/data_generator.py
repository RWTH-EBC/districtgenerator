#
#
# OLD DO NOT USE. IS REDUNDANT. 
# WILL BE DELETED AFTER I MAKE SURE EVERYTHING WORKS
#
#
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List
import pandas as pd

from dataclasses import dataclass, field
from typing import Any, Dict, List


# ----- Configuration Classes ----- #
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
    time_resolution: int = 3600  # seconds
    cluster_length: int = 604800  # seconds (default: one week)
    cluster_number: int = 4
    data_resolution: int = 3600  # seconds
    data_length: int = 31536000  # seconds (default: one year)


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
class BuildingConfig:
    buildings: List[Dict[str, Any]]  # List of individual building configurations
    heater_types: List[str]
    night_setback: bool = False
    PV: bool = False
    STC: bool = False
    EV: bool = False
    BAT: bool = False
    # Storage parameters with default values.
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
        # Validate charging modes
        for mode in self.charging_modes:
            if mode not in self.ALLOWED_CHARGING_MODES:
                raise ValueError(f"Invalid charging mode: {mode}")

        # Validate storage parameter ranges
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


# ----- JSON Data Adapter with Extended Get Methods ----- #
class JSONDataAdapter:
    def __init__(self, json_data: Dict):
        self.data = json_data

    def get_location_config(self) -> LocationConfig:
        location_data = self.data.get("location_config", {})
        return LocationConfig(
            time_zone=location_data.get("time_zone", 1),
            albedo=location_data.get("albedo", 0.2),
            try_year=location_data.get("try_year", "TRY2015"),
            try_type=location_data.get("try_type", "Jahr"),
            zip_code=location_data.get("zip_code", "52064")
        )

    def get_building_config(self) -> BuildingConfig:
        building_data = self.data.get("building_config", {})
        return BuildingConfig(
            buildings=building_data.get("buildings", []),
            heater_types=building_data.get("heater_types", ["HP", "BOI"]),
            night_setback=building_data.get("night_setback", False),
            PV=building_data.get("PV", False),
            STC=building_data.get("STC", False),
            EV=building_data.get("EV", False),
            BAT=building_data.get("BAT", False),
            storage={
                "f_TES": building_data.get("f_TES", 35.0),
                "f_BAT": building_data.get("f_BAT", 1.0),
                "f_EV": building_data.get("f_EV", 6000.0),
                "f_PV": building_data.get("f_PV", 0.4),
                "f_STC": building_data.get("f_STC", 0.04)
            },
            charging_modes=building_data.get("charging_modes", ["on_demand"])
        )

    def get_time_config(self) -> TimeConfig:
        time_data = self.data.get("time_config", {})
        return TimeConfig(
            time_resolution=time_data.get("time_resolution", 3600),
            cluster_length=time_data.get("cluster_length", 604800),
            cluster_number=time_data.get("cluster_number", 4),
            data_resolution=time_data.get("data_resolution", 3600),
            data_length=time_data.get("data_length", 31536000)
        )

    def get_design_building_config(self) -> DesignBuildingConfig:
        design_data = self.data.get("design_building_config", {})
        return DesignBuildingConfig(
            T_set_min=design_data.get("T_set_min", 20.0),
            T_set_min_night=design_data.get("T_set_min_night", 18.0),
            T_set_max=design_data.get("T_set_max", 23.0),
            T_set_max_night=design_data.get("T_set_max_night", 28.0),
            T_bivalent=design_data.get("T_bivalent", -2.0),
            T_heatlimit=design_data.get("T_heatlimit", 15.0),
            ventilation_rate=design_data.get("ventilation_rate", 0.5)
        )

    def get_eco_config(self) -> EcoConfig:
        eco_data = self.data.get("eco_config", {})
        return EcoConfig(
            price_supply_el=eco_data.get("price_supply_el", 0.32),
            revenue_feed_in_el=eco_data.get("revenue_feed_in_el", 0.0811),
            price_supply_gas=eco_data.get("price_supply_gas", 0.12),
            price_hydrogen=eco_data.get("price_hydrogen", 0.1),
            price_waste=eco_data.get("price_waste", 0.1),
            price_biomass=eco_data.get("price_biomass", 0.05),
            co2_el_grid=eco_data.get("co2_el_grid", 0.49),
            co2_gas=eco_data.get("co2_gas", 0.25),
            co2_biom=eco_data.get("co2_biom", 0.35),
            co2_waste=eco_data.get("co2_waste", 0.0),
            co2_hydrogen=eco_data.get("co2_hydrogen", 0.0)
        )


# ----- Data Generator ----- #
class DataGenerator:
    def __init__(self, 
                 location_config: LocationConfig, 
                 building_config: BuildingConfig,
                 time_config: TimeConfig = None,
                 design_building_config: DesignBuildingConfig = None,
                 eco_config: EcoConfig = None):
        self.location = location_config
        self.building = building_config
        self.time_config = time_config or TimeConfig()
        self.design_building_config = design_building_config or DesignBuildingConfig()
        self.eco_config = eco_config or EcoConfig()

    def generate_site_data(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "timeZone",
                "value": self.location.time_zone,
                "unit": "h",
                "description": "Time zone offset from GMT (e.g. CET is 1)."
            },
            {
                "name": "albedo",
                "value": self.location.albedo,
                "unit": "",
                "description": "Ground reflectance (0 = 0%, 1 = 100%)."
            },
            {
                "name": "TRYYear",
                "value": self.location.try_year,
                "unit": "",
                "description": "Test reference year (e.g. TRY2015 or TRY2045)."
            },
            {
                "name": "TRYType",
                "value": self.location.try_type,
                "unit": "",
                "description": "Test reference condition (e.g. Jahr, Somm, Wint)."
            },
            {
                "name": "zip",
                "value": self.location.zip_code,
                "unit": "",
                "description": "Zip code of the location."
            }
        ]
    
    def generate_time_data(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "timeResolution",
                "value": self.time_config.time_resolution,
                "unit": "sec",
                "description": ("Required time resolution. For example, 3600 refers to an hourly resolution "
                                "and 900 to a 15min resolution.")
            },
            {
                "name": "clusterLength",
                "value": self.time_config.cluster_length,
                "unit": "sec",
                "description": ("Length of cluster. For example, 604800 refers to one week and 86400 to one day.")
            },
            {
                "name": "clusterNumber",
                "value": self.time_config.cluster_number,
                "unit": "-",
                "description": "Number of clusters"
            },
            {
                "name": "dataResolution",
                "value": self.time_config.data_resolution,
                "unit": "sec",
                "description": "Time resolution of input data."
            },
            {
                "name": "dataLength",
                "value": self.time_config.data_length,
                "unit": "sec",
                "description": "Length of input data."
            },
            {
                "name": "holidays2015",
                "value": [1, 93, 96, 121, 134, 145, 155, 275, 305, 358, 359, 360, 365],
                "unit": "",
                "description": "Julian day number of the holidays in NRW in 2015."
            },
            {
                "name": "holidays2045",
                "value": [1, 97, 100, 121, 138, 149, 159, 276, 305, 358, 359, 360, 365],
                "unit": "",
                "description": "Julian day number of the holidays in NRW in 2045."
            },
            {
                "name": "initial_day_2015",
                "value": [4],
                "unit": "",
                "description": "Thursday"
            },
            {
                "name": "initial_day_2045",
                "value": [6],
                "unit": "",
                "description": "Saturday"
            }
        ]
    
    def generate_design_building_data(self) -> List[Dict[str, Any]]:
        design_building_data = [
            {
                "name": "T_set_min",
                "value": self.design_building_config.T_set_min,
                "unit": "degree Celsius",
                "description": "Required minimum indoor temperature (for heating load calculation)"
            },
            {
                "name": "T_set_min_night",
                "value": self.design_building_config.T_set_min_night,
                "unit": "degree Celsius",
                "description": "Required minimum indoor temperature at night (for heating load calculation)"
            },
            {
                "name": "T_set_max",
                "value": self.design_building_config.T_set_max,
                "unit": "degree Celsius",
                "description": "Required maximum indoor temperature (for cooling load calculation)"
            },
            {
                "name": "T_set_max_night",
                "value": self.design_building_config.T_set_max_night,
                "unit": "degree Celsius",
                "description": "Required maximum indoor temperature at night (for cooling load calculation)"
            },
            {
                "name": "T_bivalent",
                "value": self.design_building_config.T_bivalent,
                "unit": "degree Celsius",
                "description": "Dual mode temperature (for heat pump design)"
            },
            {
                "name": "T_heatlimit",
                "value": self.design_building_config.T_heatlimit,
                "unit": "degree Celsius",
                "description": "Limit temperature (for heat pump design)"
            },
            {
                "name": "ventilation_rate",
                "value": self.design_building_config.ventilation_rate,
                "unit": "1/h",
                "description": "Room ventilation rate"
            },
            {
                "name": "buildings_short",
                "value": ["SFH", "MFH", "TH", "AB"],
                "unit": "-",
                "description": "Abbreviations of the selectable building types."
            },
            {
                "name": "buildings_long",
                "value": ["single_family_house", "multi_family_house", "terraced_house", "apartment_block"],
                "unit": "-",
                "description": "Names of the four selectable building types."
            },
            {
                "name": "retrofit_short",
                "value": [0, 1, 2],
                "unit": "-",
                "description": "Abbreviations of the retrofit levels."
            },
            {
                "name": "retrofit_long",
                "value": ["tabula_standard", "tabula_retrofit", "tabula_adv_retrofit"],
                "unit": "-",
                "description": "Names of the retrofit levels."
            },
            {
                "name": "dhwload",
                "value": [4662.1, 4662.1, 4662.1, 3999.8],
                "unit": "Watt",
                "description": "Maximal power for domestic hot water for each of the four building types (SFH, MFH, TH and AB)"
            },
            {
                "name": "mean_drawoff_vol_per_day",
                "value": [40, 40, 40, 40],
                "unit": "Liter",
                "description": ("Mean drawoff DHW volume per day for each of the four building types "
                                "(SFH, MFH, TH and AB). Source: 12831-3/A100 Table NA.4")
            }
        ]
        return design_building_data
    
    def generate_eco_data(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "price_supply_el",
                "value": self.eco_config.price_supply_el,
                "unit": "€/kWh",
                "description": "Electricity price."
            },
            {
                "name": "revenue_feed_in_el",
                "value": self.eco_config.revenue_feed_in_el,
                "unit": "EUR/kWh",
                "description": "Feed-in electricity price."
            },
            {
                "name": "price_supply_gas",
                "value": self.eco_config.price_supply_gas,
                "unit": "€/kWh",
                "description": "Gas price."
            },
            {
                "name": "price_hydrogen",
                "value": self.eco_config.price_hydrogen,
                "unit": "€/kWh",
                "description": "Hydrogen price."
            },
            {
                "name": "price_waste",
                "value": self.eco_config.price_waste,
                "unit": "€/kWh",
                "description": "Waste price."
            },
            {
                "name": "price_biomass",
                "value": self.eco_config.price_biomass,
                "unit": "€/kWh",
                "description": "Biomass price."
            },
            {
                "name": "co2_el_grid",
                "value": self.eco_config.co2_el_grid,
                "unit": "kg/kWh",
                "description": "CO2 emissions for electricity import (grid mix)."
            },
            {
                "name": "co2_gas",
                "value": self.eco_config.co2_gas,
                "unit": "kg/kWh",
                "description": "CO2 emissions by burning natural gas."
            },
            {
                "name": "co2_biom",
                "value": self.eco_config.co2_biom,
                "unit": "kg/kWh",
                "description": "CO2 emissions by burning biomass."
            },
            {
                "name": "co2_waste",
                "value": self.eco_config.co2_waste,
                "unit": "kg/kWh",
                "description": "CO2 emissions by burning waste."
            },
            {
                "name": "co2_hydrogen",
                "value": self.eco_config.co2_hydrogen,
                "unit": "kg/kWh",
                "description": "CO2 emissions by burning hydrogen."
            }
        ]

    def generate_building_data(self) -> List[Dict[str, Any]]:
        buildings_out = []
        for idx, b in enumerate(self.building.buildings):
            building = {
                "id": idx,
                "building": b.get("building_type"),
                "year": b.get("construction_year"),
                "construction_type": b.get("construction_type"),
                "night_setback": int(b.get("night_setback", self.building.night_setback)),
                "retrofit": b.get("retrofit", 0),
                "area": b.get("area"),
                "number_of_floors": b.get("number_of_floors"),
                "elec": b.get("elec"),
                "height": b.get("height"),
                "heater": b.get("heater_type"),
                "PV": int(b.get("PV", self.building.PV)),
                "STC": int(b.get("STC", self.building.STC)),
                "EV": int(b.get("EV", self.building.EV)),
                "BAT": int(b.get("BAT", self.building.BAT)),
                "f_TES": b.get("f_TES", self.building.storage.get("f_TES")),
                "f_BAT": b.get("f_BAT", self.building.storage.get("f_BAT")),
                "f_EV": b.get("f_EV", self.building.storage.get("f_EV")),
                "f_PV": b.get("f_PV", self.building.storage.get("f_PV")),
                "f_STC": b.get("f_STC", self.building.storage.get("f_STC")),
                "gamma_PV": b.get("gamma_PV", 0),
                "ev_charging": b.get("ev_charging", self.building.charging_modes[0])
            }
            buildings_out.append(building)
        return buildings_out

    def save_files(self, output_path: str = "/home/ubuntu/daten_modell/examples/files/"):
        # Save site data to JSON
        site_data = self.generate_site_data()
        with open(f"{output_path}site_data.json", "w", encoding='utf-8') as f:
            json.dump(site_data, f, indent=2, ensure_ascii=False)
        # Save time data to JSON
        time_data = self.generate_time_data()
        with open(f"{output_path}time_data.json", "w", encoding='utf-8') as f:
            json.dump(time_data, f, indent=2, ensure_ascii=False)
        # Save indoor data to JSON
        design_building_data = self.generate_design_building_data()
        with open(f"{output_path}design_building_data.json", "w", encoding='utf-8') as f:
            json.dump(design_building_data, f, indent=2, ensure_ascii=False)
        # Save eco data
        eco_data = self.generate_eco_data()
        with open(f"{output_path}eco_data.json", "w", encoding='utf-8') as f:
            json.dump(eco_data, f, indent=2, ensure_ascii=False)
        # Save building data to CSV
        building_data = self.generate_building_data()
        df = pd.DataFrame(building_data)
        df.to_csv(f"{output_path}example.csv", sep=";", index=False)


# ----- Example Usage ----- #
if __name__ == "__main__":

    with open('/home/ubuntu/daten_modell/examples/files/intermediate_output.json', 'r') as file:
        data = json.load(file)

    loc_config = LocationConfig(
        time_zone=data['location_config']['time_zone'],
        albedo=data['location_config']['albedo'],
        try_year=data['location_config']['try_year'],
        try_type=data['location_config']['try_type'],
        zip_code=data['location_config']['zip_code'],
    )

    # Optionally, you can provide custom time configuration parameters.
    time_config = TimeConfig(
        time_resolution=3600,
        cluster_length=604800,
        cluster_number=4,
        data_resolution=3600,
        data_length=31536000
    )

    # Set custom indoor configuration parameters.
    design_building_config = DesignBuildingConfig(
        T_set_min=20.0,
        T_set_min_night=18.0,
        T_set_max=23.0,
        T_set_max_night=28.0,
        T_bivalent=-2.0,
        T_heatlimit=15.0,
        ventilation_rate=0.5
    )

    eco_config = EcoConfig(
        price_supply_el=0.32,
        revenue_feed_in_el=0.0811,
        price_supply_gas=0.12,
        price_hydrogen=0.1,
        price_waste=0.1,
        price_biomass=0.05,
        co2_el_grid=0.49,
        co2_gas=0.25,
        co2_biom=0.35,
        co2_waste=0.0,
        co2_hydrogen=0.0
    )
    
    bld_config = BuildingConfig(
        buildings = data['building_config']['buildings'],
        heater_types=["HP", "BOI"],
        night_setback=False,
        PV=False,
        STC=False,
        EV=False,
        BAT=False,
        storage={
            "f_TES": 35.0,
            "f_BAT": 0.5,
            "f_EV": 6000.0,
            "f_PV": 0.6,
            "f_STC": 0.05
        },
        charging_modes=["on_demand"]
    )

    generator = DataGenerator(loc_config, bld_config, time_config, design_building_config, eco_config)
    generator.save_files()
