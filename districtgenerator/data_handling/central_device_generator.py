from typing import Any, Dict, List
from districtgenerator.data_handling.central_device_config import CentralDeviceConfig

class CentralDeviceDataGenerator:
    def __init__(self, tech_config: CentralDeviceConfig):
        self.config = tech_config

    def generate_tech_data(self) -> Dict[str, Dict[str, Any]]:
        tech_data = {}

        # Define a list of technology prefixes that we expect in TechConfig.
        techs = [
            "PV", "WT", "WAT", "STC", "CHP", "BOI", "GHP",
            "HP", "EB", "CC", "AC", "BCHP", "BBOI", "WCHP",
            "WBOI", "ELYZ", "FC", "H2S", "SAB", "TES", "CTES",
            "BAT", "GS"
        ]

        # For each technology prefix, we go through all attributes in the config
        # that start with that prefix and build a dictionary.
        for tech in techs:
            tech_params = {}
            for field_name, value in self.config.__dict__.items():
                if field_name.startswith(f"{tech}_"):
                    # Remove the prefix and underscore to get the parameter name.
                    param_name = field_name[len(tech) + 1:]
                    tech_params[param_name] = value

            # Only add the tech if it has any parameters, to avoid adding empty entries.
            if tech_params:
                tech_data[tech] = tech_params

        return tech_data

