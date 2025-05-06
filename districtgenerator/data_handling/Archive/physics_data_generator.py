from typing import Any, Dict, List
from districtgenerator.data_handling.config import PhysicsConfig

class PhysicsDataGenerator:
    def __init__(self, physics_config: PhysicsConfig):
        self.config = physics_config
        
    def generate_physics_data(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "rho_air",
                "value": self.config.rho_air,
                "unit": "kg/m3",
                "description": "Densitiy of air"
            },
            {
                "name": "c_p_air",
                "value": self.config.c_p_air,
                "unit": "J/kgK",
                "description": "Specific heat capacity of air"
            },
            {
                "name": "rho_water",
                "value": self.config.rho_water,
                "unit": "kg/m3",
                "description": "Density of water"
            },
            {
                "name": "c_p_water",
                "value": self.config.c_p_water,
                "unit": "kJ/kgK",
                "description": "Specific heat capacity of water"
            }
        ]
