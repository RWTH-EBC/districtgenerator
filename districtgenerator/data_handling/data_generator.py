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
    buildings: List[Dict[str, any]]  # List of individual building configurations
    heater_types: List[str]
    night_setback: bool = False
    tech_params: TechnologyParams = field(default_factory=TechnologyParams)
    storage_params: StorageParams = field(default_factory=StorageParams)
    charging_modes: ChargingModes = field(default_factory=ChargingModes)

class JSONDataAdapter:
    def __init__(self, json_data: Dict):
        self.data = json_data

    def get_location_config(self) -> LocationConfig:
        location_data = self.data.get("location", {})
        return LocationConfig(
            time_zone=location_data.get("time_zone", 1),
            albedo=location_data.get("albedo", 0.2),
            try_year=location_data.get("try_year", "TRY2015"),
            try_type=location_data.get("try_type", "Jahr"),
            zip_code=location_data.get("zip_code", "52064")
        )

    def get_building_config(self) -> BuildingConfig:
        building_data = self.data.get("building", {})
        return BuildingConfig(
            buildings=building_data.get("buildings", []),
            heater_types=building_data.get("heater_types", ["HP", "BOI"]),
            night_setback=building_data.get("night_setback", False),
            tech_params=TechnologyParams(
                PV=building_data.get("PV", False),
                STC=building_data.get("STC", False),
                EV=building_data.get("EV", False),
                BAT=building_data.get("BAT", False)
            ),
            storage_params=StorageParams(
                f_TES=building_data.get("f_TES", 35.0),
                f_BAT=building_data.get("f_BAT", 1.0),
                f_EV=building_data.get("f_EV", 6000.0),
                f_PV=building_data.get("f_PV", 0.4),
                f_STC=building_data.get("f_STC", 0.04)
            ),
            charging_modes=ChargingModes(
                modes=building_data.get("charging_modes", ["on_demand"])
            )
        )

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
        """Generate building data based on individual configurations"""
        buildings = []

        for idx, building_config in enumerate(self.building.buildings):
            building = {
                "id": idx,
                "building": building_config.get("building_type"),
                "year": building_config.get("construction_year"),
                "construction_type": building_config.get("construction_type"),
                "night_setback": int(building_config.get("night_setback", self.building.night_setback)),
                "retrofit": building_config.get("retrofit", 0),
                "area": building_config.get("area"),
                "heater": building_config.get("heater_type"),
                "PV": int(building_config.get("PV", self.building.tech_params.PV)),
                "STC": int(building_config.get("STC", self.building.tech_params.STC)),
                "EV": int(building_config.get("EV", self.building.tech_params.EV)),
                "BAT": int(building_config.get("BAT", self.building.tech_params.BAT)),
                "f_TES": building_config.get("f_TES", self.building.storage_params.f_TES),
                "f_BAT": building_config.get("f_BAT", self.building.storage_params.f_BAT),
                "f_EV": building_config.get("f_EV", self.building.storage_params.f_EV),
                "f_PV": building_config.get("f_PV", self.building.storage_params.f_PV),
                "f_STC": building_config.get("f_STC", self.building.storage_params.f_STC),
                "gamma_PV": building_config.get("gamma_PV", 0),
                "ev_charging": building_config.get("ev_charging", self.building.charging_modes.modes[0])
            }
            buildings.append(building)

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
        try_year="TRY2015",  # Possible entries are TRY2015 and TRY2045
        try_type="Jahr",  # Possible entries are Jahr, Somm, Wint.
        zip_code="52064"
    )

    # Building configuration with individual buildings
    building_config = BuildingConfig(
        buildings=[
            {
                "building_type": "SFH",
                "construction_year": 1980,
                "construction_type": None,
                "area": 140,
                "heater_type": "HP",
                "retrofit": 0
            },
            {
                "building_type": "MFH",
                "construction_year": 1960,
                "construction_type": None,
                "area": 300,
                "heater_type": "BOI",
                "retrofit": 1
            }
        ],
        heater_types=["HP", "BOI"],
        night_setback=False,
        tech_params=TechnologyParams(PV=False, STC=False, EV=False, BAT=False),
        storage_params=StorageParams(),
        charging_modes=ChargingModes()
    )

    # Generate district
    generator = DataGenerator(location_config, building_config)
    generator.save_files()