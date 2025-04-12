from districtgenerator.data_handling.config import LocationConfig, BuildingConfig, TimeConfig, DesignBuildingConfig, EcoConfig, PhysicsConfig, EHDOConfig, GurobiConfig, HeatGridConfig
from districtgenerator.data_handling.site_data_generator import SiteDataGenerator
from districtgenerator.data_handling.time_data_generator import TimeDataGenerator
from districtgenerator.data_handling.design_building_data_generator import DesignBuildingDataGenerator
from districtgenerator.data_handling.building_data_generator import BuildingDataGenerator
from districtgenerator.data_handling.eco_data_generator import EcoDataGenerator
from districtgenerator.data_handling.physics_data_generator import PhysicsDataGenerator
from districtgenerator.data_handling.EHDO_generator import EHDOGenerator
from districtgenerator.data_handling.gurobi_generator import GurobiGenerator
from districtgenerator.data_handling.heat_grid_data_generator import HeatGridDataGenerator
from districtgenerator.data_handling.central_device_config import CentralDeviceConfig
from districtgenerator.data_handling.central_device_generator import CentralDeviceDataGenerator
from districtgenerator.data_handling.decentral_device_config import DecentralDeviceConfig
from districtgenerator.data_handling.decentral_device_data_generator import DecentralDeviceDataGenerator
from districtgenerator.data_handling.json_adapter import JSONDataAdapter
from typing import Dict, Any
import json
import pandas as pd
import os

class DataGenerator:
    def __init__(self,
                 location_config: LocationConfig,
                 building_config: BuildingConfig,
                 time_config: TimeConfig = None,
                 design_building_config: DesignBuildingConfig = None,
                 eco_config: EcoConfig = None,
                 EHDO_config: EHDOConfig = None,
                 physics_config: PhysicsConfig = None,
                 gurobi_config: GurobiConfig = None,
                 heat_grid_config: HeatGridConfig = None,
                 central_device_config: CentralDeviceConfig = None,
                 decentral_device_config = None):
        self.location_config = location_config
        self.building_config = building_config
        self.time_config = time_config if time_config is not None else TimeConfig()
        self.design_building_config = design_building_config if design_building_config is not None else DesignBuildingConfig()
        self.eco_config = eco_config if eco_config is not None else EcoConfig()
        self.physics_config = physics_config if physics_config is not None else PhysicsConfig()
        self.EHDO_config = EHDO_config if EHDO_config is not None else EHDOConfig()  
        self.gurobi_config = gurobi_config if gurobi_config is not None else GurobiConfig()
        self.heat_grid_config = heat_grid_config if heat_grid_config is not None else HeatGridConfig()
        self.central_device_config = central_device_config if central_device_config is not None else CentralDeviceConfig()
        self.decentral_device_config = decentral_device_config if decentral_device_config is not None else DecentralDeviceConfig()
        self.decentral_device_data_gen = DecentralDeviceDataGenerator(self.decentral_device_config)

        self.site_data_gen = SiteDataGenerator(self.location_config)
        self.time_data_gen = TimeDataGenerator(self.time_config)
        self.design_data_gen = DesignBuildingDataGenerator(self.design_building_config)
        self.eco_data_gen = EcoDataGenerator(self.eco_config)
        self.building_data_gen = BuildingDataGenerator(self.building_config)
        self.physics_data_gen = PhysicsDataGenerator(self.physics_config)
        self.EHDO_data_gen = EHDOGenerator(self.EHDO_config)
        self.gurobi_data_gen = GurobiGenerator(self.gurobi_config)
        self.heat_grid_data_gen = HeatGridDataGenerator(self.heat_grid_config)
        self.central_device_data_gen = CentralDeviceDataGenerator(self.central_device_config)

    def save_files(self, output_path: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "files/")):
        # Save site data to JSON
        site_data = self.site_data_gen.generate_site_data()
        with open(f"{output_path}site_data.json", "w", encoding='utf-8') as f:
            json.dump(site_data, f, indent=2, ensure_ascii=False)

        # Save time data to JSON
        time_data = self.time_data_gen.generate_time_data()
        with open(f"{output_path}time_data.json", "w", encoding='utf-8') as f:
            json.dump(time_data, f, indent=2, ensure_ascii=False)

        # Save design building data to JSON
        design_building_data = self.design_data_gen.generate_design_building_data()
        with open(f"{output_path}design_building_data.json", "w", encoding='utf-8') as f:
            json.dump(design_building_data, f, indent=2, ensure_ascii=False)

        # Save eco data to JSON
        eco_data = self.eco_data_gen.generate_eco_data()
        with open(f"{output_path}eco_data.json", "w", encoding='utf-8') as f:
            json.dump(eco_data, f, indent=2, ensure_ascii=False)

        # Save physics data to JSON
        physics_data = self.physics_data_gen.generate_physics_data()
        with open(f"{output_path}physics_data.json", "w", encoding='utf-8') as f:
            json.dump(physics_data, f, indent=2, ensure_ascii=False)

        # Save energy data to JSON
        EHDO_data = self.EHDO_data_gen.generate_energy_data()
        with open(f"{output_path}model_parameters_EHDO.json", "w", encoding='utf-8') as f:
            json.dump(EHDO_data, f, indent=2, ensure_ascii=False)
        
        # Save heat grid data to JSON
        heat_grid_data = self.heat_grid_data_gen.generate_heat_grid_data()
        with open(f"{output_path}heat_grid_data.json", "w", encoding='utf-8') as f:
            json.dump(heat_grid_data, f, indent=2, ensure_ascii=False)

        # Save optimization data
        gurobi_data = self.gurobi_data_gen.generate_optimization_data()
        with open(f"{output_path}gurobi_settings.json", "w", encoding='utf-8') as f:
            json.dump(gurobi_data, f, indent=2, ensure_ascii=False)
        # Save building data to CSV
        building_data = self.building_data_gen.generate_building_data()
        df = pd.DataFrame(building_data)
        df.to_csv(f"{output_path}scenarios/example.csv", sep=";", index=False)

        # Save central device data to JSON
        cd_data = self.central_device_data_gen.generate_tech_data()
        with open(f"{output_path}central_device_data.json", "w", encoding="utf-8") as f:
            json.dump(cd_data, f, indent=2, ensure_ascii=False)

        # Save decentral device data to JSON
        dd_data = self.decentral_device_data_gen.generate_tech_data()
        with open(f"{output_path}decentral_device_data.json", "w", encoding="utf-8") as f:
            json.dump(dd_data, f, indent=2, ensure_ascii=False)

