from typing import Any, Dict, List
from districtgenerator.data_handling.config import DesignBuildingConfig

class DesignBuildingDataGenerator:
    def __init__(self, design_building_config: DesignBuildingConfig):
        self.config = design_building_config
        
    def generate_design_building_data(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "T_set_min",
                "value": self.config.T_set_min,
                "unit": "degree Celsius",
                "description": "Required minimum indoor temperature (for heating load calculation)"
            },
            {
                "name": "T_set_min_night",
                "value": self.config.T_set_min_night,
                "unit": "degree Celsius",
                "description": "Required minimum indoor temperature at night (for heating load calculation)"
            },
            {
                "name": "T_set_max",
                "value": self.config.T_set_max,
                "unit": "degree Celsius",
                "description": "Required maximum indoor temperature (for cooling load calculation)"
            },
            {
                "name": "T_set_max_night",
                "value": self.config.T_set_max_night,
                "unit": "degree Celsius",
                "description": "Required maximum indoor temperature at night (for cooling load calculation)"
            },
            {
                "name": "T_bivalent",
                "value": self.config.T_bivalent,
                "unit": "degree Celsius",
                "description": "Dual mode temperature (for heat pump design)"
            },
            {
                "name": "T_heatlimit",
                "value": self.config.T_heatlimit,
                "unit": "degree Celsius",
                "description": "Limit temperature (for heat pump design)"
            },
            {
                "name": "ventilation_rate",
                "value": self.config.ventilation_rate,
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
