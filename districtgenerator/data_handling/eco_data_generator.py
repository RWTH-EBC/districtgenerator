from typing import Any, Dict, List
from districtgenerator.data_handling.config import EcoConfig

class EcoDataGenerator:
    def __init__(self, eco_config: EcoConfig):
        self.config = eco_config
        
    def generate_eco_data(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "price_supply_el",
                "value": self.config.price_supply_el,
                "unit": "€/kWh",
                "description": "Electricity price."
            },
            {
                "name": "revenue_feed_in_el",
                "value": self.config.revenue_feed_in_el,
                "unit": "EUR/kWh",
                "description": "Feed-in electricity price."
            },
            {
                "name": "price_supply_gas",
                "value": self.config.price_supply_gas,
                "unit": "€/kWh",
                "description": "Gas price."
            },
            {
                "name": "price_hydrogen",
                "value": self.config.price_hydrogen,
                "unit": "€/kWh",
                "description": "Hydrogen price."
            },
            {
                "name": "price_waste",
                "value": self.config.price_waste,
                "unit": "€/kWh",
                "description": "Waste price."
            },
            {
                "name": "price_biomass",
                "value": self.config.price_biomass,
                "unit": "€/kWh",
                "description": "Biomass price."
            },
            {
                "name": "co2_el_grid",
                "value": self.config.co2_el_grid,
                "unit": "kg/kWh",
                "description": "CO2 emissions for electricity import (grid mix)."
            },
            {
                "name": "co2_gas",
                "value": self.config.co2_gas,
                "unit": "kg/kWh",
                "description": "CO2 emissions by burning natural gas."
            },
            {
                "name": "co2_biom",
                "value": self.config.co2_biom,
                "unit": "kg/kWh",
                "description": "CO2 emissions by burning biomass."
            },
            {
                "name": "co2_waste",
                "value": self.config.co2_waste,
                "unit": "kg/kWh",
                "description": "CO2 emissions by burning waste."
            },
            {
                "name": "co2_hydrogen",
                "value": self.config.co2_hydrogen,
                "unit": "kg/kWh",
                "description": "CO2 emissions by burning hydrogen."
            }
        ]
