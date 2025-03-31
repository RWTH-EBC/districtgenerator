from typing import Any, Dict, List
from districtgenerator.data_handling.config import HeatGridConfig

class HeatGridDataGenerator:
    def __init__(self, config: HeatGridConfig):
        self.config = config

    def generate_heat_grid_data(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "T_hot",
                "value": self.config.T_hot,
                "unit": "K",
                "description": "flow temperature of heat grid"
            },
            {
                "name": "T_cold",
                "value": self.config.T_cold,
                "unit": "K",
                "description": "return temperature of heat grid"
            },
            {
                "name": "delta_T_heatTransfer",
                "value": self.config.delta_T_heatTransfer,
                "unit": "K",
                "description": "temperature difference in heat exchangers"
            }
        ]

