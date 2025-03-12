import json
import csv
import pandas as pd
from typing import Dict, List, Tuple
from dataclasses import dataclass, asdict, field
import itertools

# Data classes for configuration
# Location
@dataclass
class ValidAlbedo:
    min_val: float = 0.0
    max_val: float = 1.0

    @classmethod
    def get_valid_range(cls) -> Tuple[float, float]:
        return (cls.min_val, cls.max_val)


@dataclass
class TRYYears:
    years: List[str] = field(default_factory=lambda: ["TRY2015", "TRY2045"])

    @classmethod
    def get_valid_years(cls) -> List[str]:
        return ["TRY2015", "TRY2045"]


@dataclass
class TRYTypes:
    types: List[str] = field(default_factory=lambda: ["Jahr", "Somm", "Wint"])

    @classmethod
    def get_valid_types(cls) -> List[str]:
        return ["Jahr", "Somm", "Wint"]

# Building
@dataclass
class TechnologyParams:
    PV: bool = False
    STC: bool = False
    EV: bool = False
    BAT: bool = False

    @classmethod
    def get_valid_ranges(cls) -> Dict[str, Tuple[int, int]]:
        return {
            "PV": (0, 1),
            "STC": (0, 1),
            "EV": (0, 1),
            "BAT": (0, 1)
        }

@dataclass
class StorageParams:
    f_TES: float = 35.0
    f_BAT: float = 1.0
    f_EV: float = 6000.0
    f_PV: float = 0.4
    f_STC: float = 0.04

    @classmethod
    def get_valid_ranges(cls) -> Dict[str, Tuple[float, float]]:
        return {
            "f_TES": (20.0, 50.0),
            "f_BAT": (0.5, 2.0),
            "f_EV": (3000.0, 9000.0),
            "f_PV": (0.2, 1.0),
            "f_STC": (0.02, 0.08)
        }

@dataclass
class ChargingModes:
    modes: List[str] = field(default_factory=lambda: ["on_demand"])

    @classmethod
    def get_valid_modes(cls) -> List[str]:
        return ["on_demand", "night_charge", "pv_optimized"]

#Config
@dataclass
class LocationConfig:
    time_zone: float
    albedo: float
    try_year: str
    try_type: str
    zip_code: str

    def __post_init__(self):
        allowed_try_years = TRYYears.get_valid_years()
        allowed_try_types = TRYTypes.get_valid_types()
        if self.try_year not in allowed_try_years:
            raise ValueError(f"try_year must be one of {allowed_try_years}, got '{self.try_year}'")
        if self.try_type not in allowed_try_types:
            raise ValueError(f"try_type must be one of {allowed_try_types}, got '{self.try_type}'")

@dataclass
class BuildingConfig:
    building_types: List[str]
    construction_years: List[int]
    construction_types: List[str]
    retrofit_options: List[int]
    area_ranges: Dict[str, List[float]]
    heater_types: List[str]
    night_setback: bool = False
    tech_params: TechnologyParams = field(default_factory=TechnologyParams)
    storage_params: StorageParams = field(default_factory=StorageParams)
    charging_modes: ChargingModes = field(default_factory=ChargingModes)


class DataGenerator:
    def __init__(self, location_config: LocationConfig, building_config: BuildingConfig):
        self.location = location_config
        self.building = building_config
        self.validate_parameters()

    def validate_parameters(self):
        """Validate that all parameters are within their allowed ranges"""
        # Validate technology parameters
        tech_ranges = TechnologyParams.get_valid_ranges()
        for param, (min_val, max_val) in tech_ranges.items():
            value = getattr(self.building.tech_params, param)
            if not isinstance(value, bool) and (value < min_val or value > max_val):
                raise ValueError(f"{param} must be between {min_val} and {max_val}")

        # Validate storage parameters
        storage_ranges = StorageParams.get_valid_ranges()
        for param, (min_val, max_val) in storage_ranges.items():
            value = getattr(self.building.storage_params, param)
            if value < min_val or value > max_val:
                raise ValueError(f"{param} must be between {min_val} and {max_val}")

        # Validate charging modes
        valid_modes = ChargingModes.get_valid_modes()
        for mode in self.building.charging_modes.modes:
            if mode not in valid_modes:
                raise ValueError(f"Invalid charging mode: {mode}")

    def generate_site_data(self) -> List[Dict]:
        """Generate site-specific JSON data"""
        return [
            {
                "name": "timeZone",
                "value": self.location.time_zone,
                "unit": "h",
                "description": "Shift between the location's time and GMT in hours. CET would be 1."
            },
            {
                "name": "albedo",
                "value": self.location.albedo,
                "unit": "-",
                "description": "Ground reflectance. 0 refers to 0% and 1 refers to 100%."
            },
            {
                "name": "TRYYear",
                "value": self.location.try_year,
                "unit": "-",
                "description": "Test reference year of DWD. Possible entries are TRY2015 and TRY2045."
            },
            {
                "name": "TRYType",
                "value": self.location.try_type,
                "unit": "-",
                "description": "Test reference conditions of DWD. Possible entries are Jahr, Somm, Wint."
            },
            {
                "name": "zip",
                "value": self.location.zip_code,
                "unit": "-",
                "description": "Zip code of the location."
            }
        ]

    def generate_building_combinations(self) -> List[Dict]:
        """Generate building combinations based on config"""
        buildings = []
        id_counter = 0

        # Generate all possible combinations
        for btype, year, area, heater in itertools.product(
                self.building.building_types,
                self.building.construction_years,
                self.building.area_ranges[self.building.building_types[0]],
                self.building.heater_types
        ):
            building = {
                "id": id_counter,
                "building": btype,
                "year": year,
                "construction_type": self.building.construction_types[0],
                "night_setback": int(self.building.night_setback),
                "retrofit": self.building.retrofit_options[0],
                "area": area,
                "heater": heater,
                "PV": int(self.building.tech_params.PV),
                "STC": int(self.building.tech_params.STC),
                "EV": int(self.building.tech_params.EV),
                "BAT": int(self.building.tech_params.BAT),
                "f_TES": self.building.storage_params.f_TES,
                "f_BAT": self.building.storage_params.f_BAT,
                "f_EV": self.building.storage_params.f_EV,
                "f_PV": self.building.storage_params.f_PV,
                "f_STC": self.building.storage_params.f_STC,
                "gamma_PV": 0,
                "ev_charging": self.building.charging_modes.modes[0]
            }
            buildings.append(building)
            id_counter += 1

        return buildings

    def save_files(self, output_path: str = "./files/"):
        """Save generated data to files"""
        # Save site data
        site_data = self.generate_site_data()
        with open(f"{output_path}site_data.json", 'w') as f:
            json.dump(site_data, f, indent=2)

        # Save building data
        building_data = self.generate_building_combinations()
        df = pd.DataFrame(building_data)
        df.to_csv(f"{output_path}example.csv", sep=';', index=False)


# Example usage
if __name__ == "__main__":
    # Location configuration
    location_config = LocationConfig(
        time_zone=1,
        albedo=0.2,
        try_year="TRY2015", # Possible entries are TRY2015 and TRY2045
        try_type="Jahr", # Possible entries are Jahr, Somm, Wint.
        zip_code="52064"
    )

    # Building configuration with default parameters
    building_config = BuildingConfig(
        building_types=["SFH"],
        construction_years=[1980],
        construction_types=[None],
        night_setback=False,
        retrofit_options=[0],
        area_ranges={"SFH": [140, 300]},
        heater_types=["HP", "BOI"],
        tech_params=TechnologyParams(PV=False, STC=False, EV=False, BAT=False),
        storage_params=StorageParams(),
        charging_modes=ChargingModes()
    )

    # Generate district
    generator = DataGenerator(location_config, building_config)
    generator.save_files()