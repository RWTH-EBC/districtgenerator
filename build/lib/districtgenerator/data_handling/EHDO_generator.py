from typing import Any, Dict, List
from districtgenerator.data_handling.config import EHDOConfig  # Import the config dataclass

class EHDOGenerator:
    def __init__(self, EHDO_config: EHDOConfig):
        self.config = EHDO_config

    def generate_energy_data(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "enable_supply_el",
                "value": self.config.enable_supply_el,
                "description": "Enable electricity supply."
            },
            {
                "name": "enable_feed_in_el",
                "value": self.config.enable_feed_in_el,
                "description": "Enable electricity supply."
            },
            {
                "name": "enable_price_cap_el",
                "value": self.config.enable_price_cap_el,
                "unit": self.config.unit_placeholder,
                "description": "Enable electricity capacity price."
            },
            {
                "name": "price_cap_el",
                "value": self.config.price_cap_el,
                "unit": "€/kW",
                "description": "Electricity capacity price."
            },
            {
                "name": "enable_cap_limit_el",
                "value": self.config.enable_cap_limit_el,
                "unit": self.config.unit_placeholder,
                "description": "Consider capacity of grid connection."
            },
            {
                "name": "cap_limit_el",
                "value": self.config.cap_limit_el,
                "unit": "kW",
                "description": "Capacity of grid connection."
            },
            {
                "name": "enable_supply_limit_el",
                "value": self.config.enable_supply_limit_el,
                "unit": self.config.unit_placeholder,
                "description": "Enable restriction of electricity demand from grid."
            },
            {
                "name": "supply_limit_el",
                "value": self.config.supply_limit_el,
                "unit": "MWh/year",
                "description": "Restrict electricity demand from grid."
            },
            {
                "name": "enable_supply_gas",
                "value": self.config.enable_supply_gas,
                "description": "Enable gas supply."
            },
            {
                "name": "enable_price_cap_gas",
                "value": self.config.enable_price_cap_gas,
                "unit": self.config.unit_placeholder,
                "description": "Enable gas capacity price."
            },
            {
                "name": "price_cap_gas",
                "value": self.config.price_cap_gas,
                "unit": "€/kWh",
                "description": "Gas capacity price."
            },
            {
                "name": "enable_feed_in_gas",
                "value": self.config.enable_feed_in_gas,
                "unit": self.config.unit_dash,
                "description": "Enable natural gas feed-in."
            },
            {
                "name": "revenue_feed_in_gas",
                "value": self.config.revenue_feed_in_gas,
                "unit": "€/kWh",
                "description": "Revenue for natural gas feed-in ."
            },
            {
                "name": "enable_cap_limit_gas",
                "value": self.config.enable_cap_limit_gas,
                "unit": self.config.unit_dash,
                "description": "Restrict gas demand from grid."
            },
            {
                "name": "cap_limit_gas",
                "value": self.config.cap_limit_gas,
                "unit": "MWh/year",
                "description": "Maximum annual energy drawn from the gas grid."
            },
            {
                "name": "enable_supply_biomass",
                "value": self.config.enable_supply_biomass,
                "unit": self.config.unit_dash,
                "description": "Restrict available biomass."
            },
            {
                "name": "enable_supply_limit_biomass",
                "value": self.config.enable_supply_limit_biomass,
                "unit": self.config.unit_dash,
                "description": "Enable limit annual biomass import."
            },
            {
                "name": "supply_limit_biomass",
                "value": self.config.supply_limit_biomass,
                "unit": "MWh/year",
                "description": "Maximum available biomass."
            },
            {
                "name": "enable_supply_hydrogen",
                "value": self.config.enable_supply_hydrogen,
                "unit": self.config.unit_dash,
                "description": "Restrict available hydrogen."
            },
            {
                "name": "enable_supply_limit_hydrogen",
                "value": self.config.enable_supply_limit_hydrogen,
                "unit": self.config.unit_dash,
                "description": "Enable limit annual hydrogen import."
            },
            {
                "name": "supply_limit_hydrogen",
                "value": self.config.supply_limit_hydrogen,
                "unit": "MWh/year",
                "description": "Maximum available Hydrogen."
            },
            {
                "name": "enable_supply_waste",
                "value": self.config.enable_supply_waste,
                "unit": self.config.unit_dash,
                "description": "Restrict available waste."
            },
            {
                "name": "enable_supply_limit_waste",
                "value": self.config.enable_supply_limit_waste,
                "unit": self.config.unit_dash,
                "description": "Enable limit annual waste import."
            },
            {
                "name": "supply_limit_waste",
                "value": self.config.supply_limit_waste,
                "unit": "MWh/year",
                "description": "Maximum available waste."
            },
            {
                "name": "supply_limit_gas",
                "value": self.config.supply_limit_gas,
                "unit": "MWh/year",
                "description": "Maximum available gas."
            },
            {
                "name": "enable_supply_limit_gas",
                "value": self.config.enable_supply_limit_gas,
                "unit": self.config.unit_dash,
                "description": "Enable limit annual gas import."
            },
            {
                "name": "peak_dem_met_conv",
                "value": self.config.peak_dem_met_conv,
                "unit": self.config.unit_dash,
                "description": "Meet peak demands of unclustered demands"
            },
            {
                "name": "co2_tax",
                "value": self.config.co2_tax,
                "unit": "€/t_CO2",
                "description": "CO2 tax. Tax on CO2 emissions due to burning natural gas, biomass or waste."
            },
            {
                "name": "co2_el_feed_in",
                "value": self.config.co2_el_feed_in,
                "unit": "kg/kWh",
                "description": "CO₂ emission credit for electricity feed-in."
            },
            {
                "name": "co2_gas_feed_in",
                "value": self.config.co2_gas_feed_in,
                "unit": "kg/kWh",
                "description": "CO₂ emission credit for gas feed-in."
            },
            {
                "name": "optim_focus",
                "value": self.config.optim_focus,
                "unit": self.config.unit_dash,
                "description": "Optimization focus. Annual costs vs CO2 emissions. '0' means only cost optimization; '1' means only CO2 optimization."
            },
            {
                "name": "interest_rate",
                "value": self.config.interest_rate,
                "unit": self.config.unit_dash,
                "description": "Interest rate. The interest rate affects the annualization of the investments according to VDI 2067."
            },
            {
                "name": "observation_time",
                "value": self.config.observation_time,
                "unit": "years",
                "description": "Project lifetime. The project lifetime affects annualization of investments according to VDI 2067."
            },
            {
                "name": "n_clusters",
                "value": self.config.n_clusters,
                "unit": "days",
                "description": "Number of design days."
            },
        ]

