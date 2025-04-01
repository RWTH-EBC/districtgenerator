import json
from typing import Any, Dict, List
from districtgenerator.data_handling.config import LocationConfig, TimeConfig, DesignBuildingConfig, EcoConfig, BuildingConfig, PhysicsConfig, EHDOConfig, GurobiConfig, HeatGridConfig
from districtgenerator.data_handling.central_device_config import CentralDeviceConfig
from districtgenerator.data_handling.decentral_device_config import DecentralDeviceConfig

class JSONDataAdapter:
    def __init__(self, json_data: Dict[str, Any]):
        self.data = json_data

    def get_location_config(self) -> LocationConfig:
        location_data = self.data.get("location_config", {})
        return LocationConfig(
            time_zone=location_data.get("time_zone", 1),
            albedo=location_data.get("albedo", 0.2),
            try_year=location_data.get("try_year", "TRY2015"),
            try_type=location_data.get("try_type", "Jahr"),
            zip_code=location_data.get("zip_code", "52064")
        )
    
    def get_physics_config(self) -> PhysicsConfig:
        physics_data = self.data.get("physics_config", {})
        return PhysicsConfig(
            rho_air=physics_data.get("rho_air", 1.2),
            c_p_air=physics_data.get("c_p_air", 1000.0),
            rho_water=physics_data.get("rho_water", 1000.0),
            c_p_water=physics_data.get("c_p_water", 4.18),
        )
    
    def get_EHDO_config(self) -> EHDOConfig:
        EHDO_data = self.data.get("EHDO_config", {})
        return EHDOConfig(
            enable_supply_el=EHDO_data.get("enable_supply_el", True),
            enable_feed_in_el=EHDO_data.get("enable_feed_in_el", True),
            enable_price_cap_el=EHDO_data.get("enable_price_cap_el", False),
            price_cap_el=EHDO_data.get("price_cap_el", 60),
            enable_cap_limit_el=EHDO_data.get("enable_cap_limit_el", False),
            cap_limit_el=EHDO_data.get("cap_limit_el", 100000),
            enable_supply_limit_el=EHDO_data.get("enable_supply_limit_el", False),
            supply_limit_el=EHDO_data.get("supply_limit_el", 100000),
            
            enable_supply_gas=EHDO_data.get("enable_supply_gas", False),
            enable_price_cap_gas=EHDO_data.get("enable_price_cap_gas", False),
            price_cap_gas=EHDO_data.get("price_cap_gas", 0.04),
            enable_feed_in_gas=EHDO_data.get("enable_feed_in_gas", False),
            revenue_feed_in_gas=EHDO_data.get("revenue_feed_in_gas", 0.02),
            enable_cap_limit_gas=EHDO_data.get("enable_cap_limit_gas", False),
            cap_limit_gas=EHDO_data.get("cap_limit_gas", 1000000),
            
            enable_supply_biomass=EHDO_data.get("enable_supply_biomass", False),
            enable_supply_limit_biomass=EHDO_data.get("enable_supply_limit_biomass", False),
            supply_limit_biomass=EHDO_data.get("supply_limit_biomass", 1000000),
            
            enable_supply_hydrogen=EHDO_data.get("enable_supply_hydrogen", False),
            enable_supply_limit_hydrogen=EHDO_data.get("enable_supply_limit_hydrogen", False),
            supply_limit_hydrogen=EHDO_data.get("supply_limit_hydrogen", 1000000),
            
            enable_supply_waste=EHDO_data.get("enable_supply_waste", False),
            enable_supply_limit_waste=EHDO_data.get("enable_supply_limit_waste", False),
            supply_limit_waste=EHDO_data.get("supply_limit_waste", 1000000),
            
            supply_limit_gas=EHDO_data.get("supply_limit_gas", 1000000),
            enable_supply_limit_gas=EHDO_data.get("enable_supply_limit_gas", False),
            
            peak_dem_met_conv=EHDO_data.get("peak_dem_met_conv", True),
            co2_tax=EHDO_data.get("co2_tax", 0),
            co2_el_feed_in=EHDO_data.get("co2_el_feed_in", 0),
            co2_gas_feed_in=EHDO_data.get("co2_gas_feed_in", 0),
            optim_focus=EHDO_data.get("optim_focus", 0),
            interest_rate=EHDO_data.get("interest_rate", 0.05),
            observation_time=EHDO_data.get("observation_time", 20),
            n_clusters=EHDO_data.get("n_clusters", 12),
        )
    
    def get_gurobi_config(self) -> GurobiConfig:
        opt_data = self.data.get("optimization_config", {})
        return GurobiConfig(
            ModelName = opt_data.get("ModelName", "Central_Operational_Optimization"),
            TimeLimit = opt_data.get("TimeLimit", 3600),
            MIPGap = opt_data.get("MIPGap", 0.01),
            MIPFocus = opt_data.get("MIPFocus", 3),
            NonConvex = opt_data.get("NonConvex", 2),
            NumericFocus = opt_data.get("NumericFocus", 3),
            PoolSolution = opt_data.get("PoolSolution", 3),
            DualReductions = opt_data.get("DualReductions", 0)
        )
    
    def get_heat_grid_config(self) -> HeatGridConfig:
        heat_grid_data = self.data.get("heat_grid_config", {})
        return HeatGridConfig(
            T_hot=heat_grid_data.get("T_hot", 332.15),
            T_cold=heat_grid_data.get("T_cold", 323.15),
            delta_T_heatTransfer=heat_grid_data.get("delta_T_heatTransfer", 5)
        )

    def get_building_config(self) -> BuildingConfig:
        building_data = self.data.get("building_config", {})
        return BuildingConfig(
            buildings=building_data.get("buildings", []),
            heater_types=building_data.get("heater_types", ["HP", "BOI"]),
            night_setback=building_data.get("night_setback", False),
            PV=building_data.get("PV", False),
            STC=building_data.get("STC", False),
            EV=building_data.get("EV", False),
            BAT=building_data.get("BAT", False),
            storage={
                "f_TES": building_data.get("f_TES", 35.0),
                "f_BAT": building_data.get("f_BAT", 1.0),
                "f_EV": building_data.get("f_EV", 6000.0),
                "f_PV": building_data.get("f_PV", 0.4),
                "f_STC": building_data.get("f_STC", 0.04)
            },
            charging_modes=building_data.get("charging_modes", ["on_demand"])
        )

    def get_time_config(self) -> TimeConfig:
        time_data = self.data.get("time_config", {})
        return TimeConfig(
            time_resolution=time_data.get("time_resolution", 3600),
            cluster_length=time_data.get("cluster_length", 604800),
            cluster_number=time_data.get("cluster_number", 4),
            data_resolution=time_data.get("data_resolution", 3600),
            data_length=time_data.get("data_length", 31536000)
        )

    def get_design_building_config(self) -> DesignBuildingConfig:
        design_data = self.data.get("design_building_config", {})
        return DesignBuildingConfig(
            T_set_min=design_data.get("T_set_min", 20.0),
            T_set_min_night=design_data.get("T_set_min_night", 18.0),
            T_set_max=design_data.get("T_set_max", 23.0),
            T_set_max_night=design_data.get("T_set_max_night", 28.0),
            T_bivalent=design_data.get("T_bivalent", -2.0),
            T_heatlimit=design_data.get("T_heatlimit", 15.0),
            ventilation_rate=design_data.get("ventilation_rate", 0.5)
        )

    def get_eco_config(self) -> EcoConfig:
        eco_data = self.data.get("eco_config", {})
        return EcoConfig(
            price_supply_el=eco_data.get("price_supply_el", 0.32),
            revenue_feed_in_el=eco_data.get("revenue_feed_in_el", 0.0811),
            price_supply_gas=eco_data.get("price_supply_gas", 0.12),
            price_hydrogen=eco_data.get("price_hydrogen", 0.1),
            price_waste=eco_data.get("price_waste", 0.1),
            price_biomass=eco_data.get("price_biomass", 0.05),
            co2_el_grid=eco_data.get("co2_el_grid", 0.49),
            co2_gas=eco_data.get("co2_gas", 0.25),
            co2_biom=eco_data.get("co2_biom", 0.35),
            co2_waste=eco_data.get("co2_waste", 0.0),
            co2_hydrogen=eco_data.get("co2_hydrogen", 0.0)
        )

    def get_central_device_config(self) -> CentralDeviceConfig:
        tech_data = self.data.get("central_device_config", {})
        kwargs = {}
        for key, value in tech_data.items():
            # Replace the dot with underscore to match our dataclass field names.
            new_key = key.replace(".", "_")
            kwargs[new_key] = value
        return CentralDeviceConfig(**kwargs)

    def get_decentral_device_config(self) -> DecentralDeviceConfig:
        tech_data = self.data.get("decentral_device_config", {})
        kwargs = {}
        for key, value in tech_data.items():
            # Replace dots with underscores to match the dataclass field names.
            new_key = key.replace(".", "_")
            kwargs[new_key] = value
        return DecentralDeviceConfig(**kwargs)