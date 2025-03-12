import json
import csv
import pandas as pd
from typing import Dict, List, Tuple
from dataclasses import dataclass, asdict
import itertools


@dataclass
class TechnologyParams:
    PV: bool = False
    STC: bool = False
    EV: bool = False
    BAT: bool = False

    # Class method to get valid ranges for binary parameters
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
    f_TES: float = 35.0  # Default thermal energy storage factor
    f_BAT: float = 1.0  # Default battery storage factor
    f_EV: float = 6000.0  # Default EV storage factor
    f_PV: float = 0.4  # Default PV sizing factor
    f_STC: float = 0.04  # Default solar thermal collector factor

    # Class method to get valid ranges for continuous parameters
    @classmethod
    def get_valid_ranges(cls) -> Dict[str, Tuple[float, float]]:
        # TODO: check if valid
        return {
            "f_TES": (20.0, 50.0),  # Thermal storage 20-50 L/m²
            "f_BAT": (0.5, 2.0),  # Battery sizing factor 0.5-2
            "f_EV": (3000.0, 9000.0),  # EV storage 3-9 kWh
            "f_PV": (0.2, 1.0),  # PV sizing factor 20-100%
            "f_STC": (0.02, 0.08)  # Solar thermal collector sizing 2-8%
        }

@dataclass
class ChargingModes:
    modes: List[str] = None

    def __post_init__(self):
        if self.modes is None:
            self.modes = ["on_demand"]

    @classmethod
    def get_valid_modes(cls) -> List[str]:
        return ["on_demand", "night_charge", "pv_optimized"]  # Todo: Example future modes


@dataclass
class LocationConfig:
    time_zone: float
    albedo: float
    try_year: str
    try_type: str
    zip_code: str


@dataclass
class BuildingConfig:
    building_types: List[str]
    construction_years: List[int]
    retrofit_options: List[int]
    area_ranges: Dict[str, List[float]]
    heater_types: List[str]
    tech_params: TechnologyParams = TechnologyParams()
    storage_params: StorageParams = StorageParams()
    charging_modes: ChargingModes = ChargingModes()


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
                "description": "Shift between the location's time and GMT in hours"
            },
            {
                "name": "albedo",
                "value": self.location.albedo,
                "unit": "-",
                "description": "Ground reflectance"
            },
            {
                "name": "TRYYear",
                "value": self.location.try_year,
                "unit": "-",
                "description": "Test reference year"
            },
            {
                "name": "TRYType",
                "value": self.location.try_type,
                "unit": "-",
                "description": "Test reference conditions"
            },
            {
                "name": "zip",
                "value": self.location.zip_code,
                "unit": "-",
                "description": "Zip code of the location"
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
        try_year="TRY2015",
        try_type="Jahr",
        zip_code="52064"
    )

    # Building configuration with default parameters
    building_config = BuildingConfig(
        building_types=["SFH"],
        construction_years=[1980],
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