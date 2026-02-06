# -*- coding: utf-8 -*-

"""

EHDO - ENERGY HUB DESIGN OPTIMIZATION Tool

Developed by:   E.ON Energy Research Center,
                Institute for Energy Efficient Buildings and Indoor Climate,
                RWTH Aachen University,
                Germany

Contact:        Marco Wirtz
                marco.wirtz@eonerc.rwth-aachen.de

"""
import pyomo.environ as pyo
import gurobipy as gp
from pyomo.util.infeasible import log_infeasible_constraints
import sys
from io import StringIO
import numpy as np
import time
from datetime import datetime
import os
import matplotlib.pyplot as plt
import textwrap
import json
import districtgenerator.functions.solver_config as solver_config
import numpy as np
import csv

#from optim_app.help_functions import create_excel_file

def run_optim_connect(dataCon, devsCon, paramCon, demCon, result_dictCon):
    """
    Runs the Energy Hub Design Optimization using Pyomo for several districts.

    Parameters
    ----------
    dataCon : object
        Contains time series information for all districts.
    devsCon : dict
        Contains device-specific parameters and investment data for all districts.
    paramCon : dict
        Contains economic parameters, prices, and other model settings for all districts.
    demCon : dict
        Contains demand profiles (heat, power, cool) for all districts.
    result_dictCon : dict
        A dictionary that will be populated with the optimization results for all districts.

    Returns
    -------
    dict
        The populated result dictionary, or the original dict if no solution is found.
    """
   
    # Load data for one district for test reasons
    data=dataCon[list(dataCon.keys())[0]]
    param=paramCon[list(paramCon.keys())[0]]

    # Set start_time 
    start_time = time.time()

    #%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    # Build the model
    model = pyo.ConcreteModel(name="Energy_Hub_Design_Optimization_Network")
    model_building_time = time.time() - start_time

    #%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    # Cluster
    # Calculate cluster time horizon
    cluster_horizon = int(data.time["clusterLength"] / data.time["timeResolution"])
    dt = data.time["timeResolution"] / data.time["dataResolution"]

    model.clusters = pyo.RangeSet(0, data.time["clusterNumber"] - 1)
    model.time_steps = pyo.RangeSet(0, cluster_horizon - 1)
    model.year = pyo.RangeSet(0, 51)  # 52 weeks

    # Get sigma function that assigns each time period (day or week) to a design period
    model.sigma = pyo.Param(model.year, initialize=param["sigma"])

    # Support years for multi-year optimization
    support_years = sorted(param["interpolation_points"])  # z.B. [0, 5, 10, 15, 20]
    model.support_years = pyo.Set(initialize=support_years)

    # Store observation time
    model.observation_time = pyo.Param(initialize=param["observation_time"])

    #%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    # Initialize lists of devices for each district 

    # Call setup_devices and store the results
    setup_devices(model, dataCon)

    # Print scenario_name for test reasons
    # TODO: Change for several districts
    print(f"Scenario name for optimization: {dataCon[0].scenario_name}")

    # Set up model and create variables
    model = add_variables(model)

    # Add constraints for each district
    # Call add_constraints to add constraints to the model
    model = add_constraints_per_district(model, devsCon, demCon, paramCon, dt, cluster_horizon, dataCon)

    # Solve the model and extract results
    result_dict= process_results_per_district(model, dataCon, devsCon, paramCon, result_dict)

def setup_devices(model, dataCon):
    # Create a set for all districts
    district_names = [district.scenario_name for district in dataCon]
    model.districts = pyo.Set(initialize=district_names)

    # Create sets for all device types
    all_devs_list = ["PV", "WT", "STC", "WAT", "HP", "EB", "CC", "AC", "CHP", "BOI", "GHP",
                         "BCHP", "BBOI", "WCHP", "WBOI", "ELYZ", "FC", "H2S", "SAB", "TES",
                         "CTES", "BAT", "GS"]

    gas_devs_list = ["CHP", "BOI", "GHP", "SAB", "from_grid", "to_grid"]
    power_devs_list = ["PV", "WT", "WAT", "HP", "EB", "CC", "CHP", "BCHP", "WCHP", "ELYZ", "FC", "from_grid", "to_grid","from_main_grid", "to_main_grid", "from_network", "to_network"]
    heat_devs_list = ["STC", "HP", "EB", "AC", "CHP", "BOI", "GHP", "BCHP", "BBOI", "WCHP", "WBOI", "FC"]
    cool_devs_list = ["CC", "AC"]
    hydrogen_devs_list = ["ELYZ", "FC", "SAB", "import"]
    biom_devs_list = ["BCHP", "BBOI", "import"]
    waste_devs_list = ["WCHP", "WBOI", "import"]
    storage_devs_list = ["TES", "CTES", "BAT", "H2S", "GS"]
    area_devs_list = ["PV", "STC"]

    # Add sets to the model for this district
    model.all_devs = pyo.Set(initialize=all_devs_list)
    model.gas_devs = pyo.Set(initialize=gas_devs_list)
    model.power_devs = pyo.Set(initialize=power_devs_list)
    model.heat_devs = pyo.Set(initialize=heat_devs_list)
    model.cool_devs = pyo.Set(initialize=cool_devs_list)
    model.hydrogen_devs = pyo.Set(initialize=hydrogen_devs_list)
    model.biom_devs = pyo.Set(initialize=biom_devs_list)
    model.waste_devs = pyo.Set(initialize=waste_devs_list)
    model.storage_devs = pyo.Set(initialize=storage_devs_list)
    model.area_devs = pyo.Set(initialize=area_devs_list)

 
def add_variables(model):
    
    # Capacity variables (same for all years - single investment decision) but indexed by district
    model.cap = pyo.Var( model.all_devs, model.districts, within=pyo.NonNegativeReals, name="nominal_capacity")
    model.area = pyo.Var(model.area_devs, model.districts, within=pyo.NonNegativeReals, name="roof_area")

    # Operational variables for EACH support year and district
    model.gas = pyo.Var(model.gas_devs, model.districts, model.support_years, model.clusters, model.time_steps, within=pyo.NonNegativeReals)
    model.power = pyo.Var(model.power_devs, model.districts, model.support_years, model.clusters, model.time_steps, within=pyo.NonNegativeReals)
    model.heat = pyo.Var(model.heat_devs, model.districts, model.support_years, model.clusters, model.time_steps, within=pyo.NonNegativeReals)
    model.cool = pyo.Var(model.cool_devs, model.districts, model.support_years, model.clusters, model.time_steps, within=pyo.NonNegativeReals)
    model.hydrogen = pyo.Var(model.hydrogen_devs, model.districts, model.support_years, model.clusters, model.time_steps, within=pyo.NonNegativeReals)
    model.biom = pyo.Var(model.biom_devs, model.districts, model.support_years, model.clusters, model.time_steps, within=pyo.NonNegativeReals)
    model.waste = pyo.Var(model.waste_devs, model.districts, model.support_years, model.clusters, model.time_steps, within=pyo.NonNegativeReals)
    model.ch = pyo.Var(model.storage_devs, model.districts, model.support_years, model.clusters, model.time_steps, within=pyo.Reals)

    # Storage SOC uses weekly tracking but indexed by support year and district
    model.soc = pyo.Var(model.storage_devs, model.districts, model.support_years, model.year, model.time_steps,
                        within=pyo.NonNegativeReals)
    
    # Investment costs (same for all years) indexed by district
    model.inv = pyo.Var(model.all_devs, model.districts, within=pyo.NonNegativeReals)    # subsidized investment costs payed by the investor
    model.inv_base = pyo.Var(model.all_devs, model.districts, within=pyo.NonNegativeReals)  # unsubsidized investment costs
    model.c_inv = pyo.Var(model.all_devs, model.districts, within=pyo.NonNegativeReals)
    model.c_inv_base = pyo.Var(model.all_devs, model.districts, within=pyo.NonNegativeReals)  # unsubsidized annualized investment costs
    model.c_om = pyo.Var(model.all_devs, model.districts, within=pyo.NonNegativeReals)
    model.c_total = pyo.Var(model.all_devs, model.districts, within=pyo.NonNegativeReals)

    # Grid limits (same for all years - infrastructure decision) indexed by district
    model.grid_limit_el = pyo.Var(model.districts, within=pyo.NonNegativeReals)
    model.grid_limit_gas = pyo.Var(model.districts, within=pyo.NonNegativeReals)

    # Yearly total energy flows - indexed by support year and district
    model.from_el_main_grid_total = pyo.Var(model.districts, model.support_years, within=pyo.NonNegativeReals)
    model.to_el_main_grid_total = pyo.Var(model.districts, model.support_years, within=pyo.NonNegativeReals)
    model.from_network_total = pyo.Var(model.districts, model.support_years, within=pyo.NonNegativeReals)
    model.to_network_total = pyo.Var(model.districts, model.support_years, within=pyo.NonNegativeReals)
    model.from_gas_grid_total = pyo.Var(model.districts, model.support_years, within=pyo.NonNegativeReals)
    model.to_gas_grid_total = pyo.Var(model.districts, model.support_years, within=pyo.NonNegativeReals)
    model.biom_import_total = pyo.Var(model.districts, model.support_years, within=pyo.NonNegativeReals)
    model.waste_import_total = pyo.Var(model.districts, model.support_years, within=pyo.NonNegativeReals)
    model.hydrogen_import_total = pyo.Var(model.districts, model.support_years, within=pyo.NonNegativeReals)

    # Revenues and costs per support year and district
    model.rev_feed_in_gas = pyo.Var(model.districts, model.support_years, within=pyo.NonNegativeReals)
    model.rev_feed_in_el = pyo.Var(model.districts, model.support_years, within=pyo.NonNegativeReals)
    model.supply_costs_el = pyo.Var(model.districts, model.support_years, within=pyo.NonNegativeReals)
    model.cap_costs_el = pyo.Var(model.districts, within=pyo.NonNegativeReals)  # Same for all years
    model.supply_costs_gas = pyo.Var(model.districts, model.support_years, within=pyo.NonNegativeReals)
    model.cap_costs_gas = pyo.Var(model.districts, within=pyo.NonNegativeReals)  # Same for all years
    model.supply_costs_biom = pyo.Var(model.districts, model.support_years, within=pyo.NonNegativeReals)
    model.supply_costs_waste = pyo.Var(model.districts, model.support_years, within=pyo.Reals)
    model.supply_costs_hydrogen = pyo.Var(model.districts, model.support_years, within=pyo.NonNegativeReals)

    # Annualized costs and total costs per support year and district
    model.total_annual_costs_devices = pyo.Var(model.districts,within=pyo.NonNegativeReals)                 # Total annual costs for devices (inv and om)
    model.heat_grid_costs = pyo.Var(model.districts,within=pyo.NonNegativeReals)                            # Total annual costs for heat grid (inv and om)
    model.total_energy_costs = pyo.Var(model.districts, model.support_years, within=pyo.NonNegativeReals)    # Total energy costs per year
    model.annualized_energy_costs = pyo.Var(model.districts, within=pyo.NonNegativeReals)                    # Annualized energy costs
    model.misc_costs = pyo.Var(model.districts, model.support_years, within=pyo.NonNegativeReals)            # e.g., CO2 costs, insurance, other taxes etc.
    model.annualized_misc_costs = pyo.Var(model.districts, within=pyo.NonNegativeReals)                      # Annualized miscellaneous costs
    model.total_connection_costs = pyo.Var(model.districts, within=pyo.NonNegativeReals)                     # Total annual costs for connection to grids

    # Objective variables
    model.obj_tac = pyo.Var(within=pyo.Reals)
    model.obj_co2 = pyo.Var(within=pyo.Reals)

    return model


def add_constraints_per_district(model, devsCon, demCon, paramCon, dt, cluster_horizon, dataCon):
    # Add constraints for each district
    ################################################################################
    # Define maximum Capacity of devices Constraints
    ################################################################################
     
    model.constraints = pyo.ConstraintList()

    # Add capacity constraints for all devices as specified in devs
    for district in model.districts:
        devs = devsCon[district]
        for dev in model.all_devs:
            if not devs[dev]["feasible"]:  # if device is not feasible, set capacity to 0
                model.constraints.add(model.cap[dev, district] == 0)
            else:
                if dev in model.area_devs:
                    continue  # Area constraints are handled separately and no capacity constraints are needed
                min_cap = devs[dev].get("min_cap")
                max_cap = devs[dev].get("max_cap")
                if min_cap is not None: model.constraints.add(model.cap[dev, district] >= min_cap)
                if max_cap is not None: model.constraints.add(model.cap[dev, district] <= max_cap)
    
        # Set area constraints for devices that require area as specified in devs
        devs = devsCon[district]
        for dev in model.area_devs:
            if devs[dev]["feasible"]:
                min_area = devs[dev].get("min_area")
                max_area = devs[dev].get("max_area")
                if min_area is not None: model.constraints.add(model.area[dev, district] >= min_area)
                if max_area is not None: model.constraints.add(model.area[dev, district] <= max_area)
    
        # Limited operation based on installed capacity
        for y in model.support_years:
            for d in model.clusters:
                for t in model.time_steps:
                    # Add constraints for the device operation based on the device capacity
                    for dev in ["STC", "EB", "HP", "BOI", "GHP", "BBOI", "WBOI"]:  # Heat devices
                        model.constraints.add(model.heat[dev, district, y, d, t] <= model.cap[dev, district])
                    for dev in ["PV", "WT", "WAT", "CHP", "BCHP", "WCHP", "ELYZ", "FC"]:  # Power devices
                        model.constraints.add(model.power[dev, district, y, d, t] <= model.cap[dev, district])
                    for dev in ["CC", "AC"]:  # Cooling devices
                        model.constraints.add(model.cool[dev, district, y, d, t] <= model.cap[dev, district])
                    for dev in ["SAB"]:  # Gas devices
                        model.constraints.add(model.gas[dev, district, y, d, t] <= model.cap[dev, district])

                    # Limitation of power and gas from and to the grid
                    model.constraints.add(model.power["from_grid", district, y, d, t] <= model.grid_limit_el[district])
                    model.constraints.add(model.power["to_grid", district, y, d, t] <= model.grid_limit_el[district])

                    # model.constraints.add(model.power["to_grid", district, y, d, t] == model.to_el_main_grid_total[district, y, d, t] + model.to_network_total[district, y, d, t])
                    # model.constraints.add(model.power["from_grid", district, y, d, t] == model.from_el_main_grid_total[district, d, y] + model.from_network_total[district, d, y]) 

                    model.constraints.add(model.gas["from_grid", district, y, d, t] <= model.grid_limit_gas[district])
                    model.constraints.add(model.gas["to_grid", district, y, d, t] <= model.grid_limit_gas[district])
        
        # Correlation to translate area to capacity for PV and STC
        model.constraints.add(model.cap["PV", district] == model.area["PV", district] * devs["PV"]["G_stc"] * devs["PV"]["eta"])
        model.constraints.add(model.cap["STC", district]  == model.area["STC", district] * devs["STC"]["G_stc"] * devs["STC"]["eta"])

        # state of charge < storage capacity
        for y in model.support_years:
            for dev in model.storage_devs:
                for day_y in model.year:
                    for t in model.time_steps:
                        model.constraints.add(model.soc[dev, district, y, day_y, t] <= model.cap[dev, district])

    #################################################################################
    # Energy Conversion Constraints (Input / Output Relations) (for every time step)
    #################################################################################        

    for district in model.districts:
        devs = devsCon[district]
        for y in model.support_years:
            for d in model.clusters:
                for t in model.time_steps:
                    # Photovoltaics power limited by clustered norm power
                    model.constraints.add(
                        model.power["PV", district, y, d, t] <= devs["PV"]["norm_power_clustered"][d][t] / 1000 * model.area["PV", district])
                    # Wind turbine power limited by clustered norm power
                    model.constraints.add(model.power["WT", district, y, d, t] <= devs["WT"]["norm_power_clustered"][d][t] * model.cap["WT",district])
                    # Hydropower power limited by potential
                    model.constraints.add(model.power["WAT", district, y, d, t] <= devs["WAT"]["potential"])
                    # Solar thermal collector heat limited by clustered norm power
                    model.constraints.add(model.heat["STC", district, y, d, t] <= devs["STC"]["norm_power_clustered"][d][t] / 1000 * model.area["STC", district])
                    # Electric heat pump correlation between heat and electric power
                    model.constraints.add(model.heat["HP", district, y, d, t] == model.power["HP", district, y, d, t] * devs["HP"]["COP"][y][d][t])
                    # Electric boiler correlation between heat and electric power
                    model.constraints.add(model.heat["EB", district, y, d, t] == model.power["EB",district,  y, d, t] * devs["EB"]["eta_th"])
                    # Compression chiller correlation between cooling and electric power (time-dependent COP)
                    model.constraints.add(model.cool["CC", district, y, d, t] == model.power["CC", district, y, d, t] * devs["CC"]["COP"][y][d][t])
                    # Absorption chiller correlation between cooling and heat power
                    model.constraints.add(model.cool["AC", district, y, d, t] == model.heat["AC", district, y, d, t] * devs["AC"]["eta_th"])
                    # Gas CHP correlation between production of power and heat and gas consumption
                    model.constraints.add(model.power["CHP", district, y, d, t] == model.gas["CHP", district, y, d, t] * devs["CHP"]["eta_el"])
                    model.constraints.add(model.heat["CHP", district , y, d, t] == model.gas["CHP", district, y, d, t] * devs["CHP"]["eta_th"])
                    # Gas boiler correlation between heat and gas consumption
                    model.constraints.add(model.heat["BOI", district, y, d, t] == model.gas["BOI", district, y, d, t] * devs["BOI"]["eta_th"])
                    # Gas heat pump correlation between heat and gas consumption
                    model.constraints.add(model.heat["GHP", district, y, d, t] == model.gas["GHP", district, y, d, t] * devs["GHP"]["COP"])
                    # Biomass CHP correlation between production of power and heat and biomass consumption
                    model.constraints.add(model.power["BCHP", district, y, d, t] == model.biom["BCHP", district, y, d, t] * devs["BCHP"]["eta_el"])
                    model.constraints.add(model.heat["BCHP", district, y, d, t] == model.biom["BCHP", district, y, d, t] * devs["BCHP"]["eta_th"])
                    # Biomass boiler correlation between heat and biomass consumption
                    model.constraints.add(model.heat["BBOI", district, y, d, t] == model.biom["BBOI", district, y, d, t] * devs["BBOI"]["eta_th"])
                    # Waste CHP correlation between production of power and heat and waste consumption
                    model.constraints.add(model.power["WCHP", district, y, d, t] == model.waste["WCHP", district, y, d, t] * devs["WCHP"]["eta_el"])
                    model.constraints.add(model.heat["WCHP", district, y, d, t] == model.waste["WCHP", district, y, d, t] * devs["WCHP"]["eta_th"])
                    # Waste boiler correlation between heat and waste consumption
                    model.constraints.add(model.heat["WBOI", district, y, d, t] == model.waste["WBOI", district, y, d, t] * devs["WBOI"]["eta_th"])
                    # Electrolyzer correlation between hydrogen production and electric power consumption
                    model.constraints.add(model.hydrogen["ELYZ", district, y, d, t] == model.power["ELYZ", district, y, d, t] * devs["ELYZ"]["eta_el"])
                    # Fuel cell correlation between hydrogen consumption and electric power production
                    model.constraints.add(model.power["FC", district, y, d, t] == model.hydrogen["FC", district, y, d, t] * devs["FC"]["eta_el"])
                    if devs["FC"]["enable_heat_diss"]:  # Heat can also be dissipated
                        model.constraints.add(model.heat["FC", district, y, d, t] <= model.hydrogen["FC", district, y, d, t] * devs["FC"]["eta_th"])
                    else:  # Heat must be used
                        model.constraints.add(model.heat["FC", district, y, d, t] == model.hydrogen["FC", district, y, d, t] * devs["FC"]["eta_th"])
                    # Sabatier reactor correlation between hydrogen consumption and gas production
                    model.constraints.add(model.gas["SAB", district, y, d, t] == model.hydrogen["SAB", district, y, d, t] * devs["SAB"]["eta"])

    ################################################################################
    # Energy balances for each time step
    ################################################################################
    for district in model.districts:
        devs = devsCon[district]
        dem = demCon[district]
        for y in model.support_years:
            for d in model.clusters:
                for t in model.time_steps:
                    # Heat balance
                    heat_supply = sum(model.heat[dev, district, y, d, t] for dev in
                                    ["STC", "HP", "EB", "CHP", "BOI", "GHP", "BCHP", "BBOI", "WCHP", "WBOI", "FC"])
                    heat_demand = dem["heat"][y][d][t] + model.heat["AC", district, y, d, t] + model.ch["TES", district, y, d, t]
                    model.constraints.add(heat_supply == heat_demand)

                    # Electric power supply and demand balance
                    power_supply = sum(
                        model.power[dev, district, y, d, t] for dev in ["PV", "WT", "WAT", "CHP", "BCHP", "WCHP", "FC", "from_grid"])
                    power_demand = dem["power"][y][d][t] + sum(
                        model.power[dev, district, y, d, t] for dev in ["HP", "EB", "CC", "ELYZ", "to_grid"]) + model.ch["BAT", district, y, d, t]
                    model.constraints.add(power_supply == power_demand)

                    # Cooling supply and demand balance
                    cool_supply = model.cool["AC", district, y, d, t] + model.cool["CC", district, y, d, t]
                    cool_demand = dem["cool"][y][d][t] + model.ch["CTES", district, y, d, t]
                    model.constraints.add(cool_supply == cool_demand)

                    # Gas supply and demand balance
                    gas_supply = model.gas["from_grid", district, y, d, t] + model.gas["SAB", district, y, d, t]
                    gas_demand = sum(model.gas[dev, district, y, d, t] for dev in ["CHP", "BOI", "GHP", "to_grid"]) + model.ch["GS", district, y, d, t]
                    model.constraints.add(gas_supply == gas_demand)

                    # Hydrogen supply and demand balance
                    h2_supply = model.hydrogen["ELYZ", district, y, d, t] + model.hydrogen["import", district, y, d, t]
                    h2_demand = sum(model.hydrogen[dev,district,  y, d, t] for dev in ["FC", "SAB"]) + model.ch["H2S", district, y, d, t]
                    model.constraints.add(h2_supply == h2_demand)

                    # Biomass supply and demand balance
                    model.constraints.add(model.biom["import", district, y, d, t] == model.biom["BCHP", district, y, d, t] + model.biom["BBOI", district, y, d, t])

                    # Waste supply and demand balance
                    model.constraints.add(model.waste["import", district, y, d, t] == model.waste["WCHP", district, y, d, t] + model.waste["WBOI", district, y, d, t])


    ################################################################################
    # Meet peak demands of unclustered demands to ensure the design can handle peak loads
    ################################################################################
    for district in model.districts:
        devs = devsCon[district]
        param = paramCon[district]
        if param["peak_dem_met_conv"] == False:
            # Heating (conventional - only controllable devices)
            model.constraints.add(model.cap["HP", district] + model.cap["EB", district]
                                + model.cap["CHP", district] / devs["CHP"]["eta_el"] * devs["CHP"]["eta_th"]
                                + model.cap["BOI", district]
                                + model.cap["GHP", district]
                                + model.cap["BCHP", district] / devs["BCHP"]["eta_el"] * devs["BCHP"]["eta_th"]
                                + model.cap["BBOI", district]
                                + model.cap["WCHP", district] / devs["WCHP"]["eta_el"] * devs["WCHP"]["eta_th"]
                                + model.cap["WBOI", district]
                                + model.cap["FC", district] / devs["FC"]["eta_el"] * devs["FC"]["eta_th"]
                                >= param["peak_heat"])

            # Cooling
            model.constraints.add(model.cap["CC", district] + model.cap["AC", district] >= param["peak_cool"])

            # Power
            model.constraints.add(
                model.cap["CHP", district] + model.cap["BCHP", district] + model.cap["WCHP", district] + model.cap["FC", district] + model.grid_limit_el[district] >= param[
                    "peak_power"])

            # Hydrogen
            if (param["enable_supply_hydrogen"] == False) and devs["ELYZ"]["feasible"]:
                model.constraints.add(model.cap["ELYZ", district] >= param["peak_hydrogen"])

        else:  # With STC, PV, WIND, HYDROPOWER (WAT)
            # Heating (with renewable sources)
            model.constraints.add(model.cap["STC", district] + model.cap["HP", district] + model.cap["EB", district]
                                + model.cap["CHP", district] / devs["CHP"]["eta_el"] * devs["CHP"]["eta_th"]
                                + model.cap["BOI", district]
                                + model.cap["GHP", district]
                                + model.cap["BCHP", district] / devs["BCHP"]["eta_el"] * devs["BCHP"]["eta_th"]
                                + model.cap["BBOI", district]
                                + model.cap["WCHP", district] / devs["WCHP"]["eta_el"] * devs["WCHP"]["eta_th"]
                                + model.cap["WBOI", district]
                                + model.cap["FC", district] / devs["FC"]["eta_el"] * devs["FC"]["eta_th"]
                                >= param["peak_heat"])

            # Cooling
            model.constraints.add(model.cap["CC", district] + model.cap["AC", district] >= param["peak_cool"])

            # Power (with renewable sources)
            model.constraints.add(
                model.cap["PV", district] + model.cap["WT", district] + model.cap["WAT", district] + model.cap["CHP", district] + model.cap["BCHP", district] + model.cap[
                    "WCHP", district] + model.cap["FC", district] + model.grid_limit_el[district] >= param["peak_power"])

            # Hydrogen
            if (param["enable_supply_hydrogen"] == False) and devs["ELYZ"]["feasible"]:
                model.constraints.add(model.cap["ELYZ", district] >= param["peak_hydrogen"])


    ################################################################################
    # Storage devices
    ################################################################################
    for district in model.districts:
        devs = devsCon[district]
        for dev in model.storage_devs:
            for y in model.support_years:
                for day_y in model.year:
                    for t in range(1, len(model.time_steps)):
                        # Energy balance for storage devices: soc(t) = soc(t-1) * (1 - sto_loss)^dt + charge * dt
                        soc_prev = model.soc[dev, district, y, day_y, t - 1]
                        model.constraints.add(
                            model.soc[dev, district, y, day_y, t] == soc_prev * (1 - devs[dev]["sto_loss"]) ** dt + model.ch[
                                dev, district, y, model.sigma[day_y], t] * dt)
                    if day_y > 0:
                        # For the first time step of each day, the state of charge is based on the previous day's last time step
                        # Equation: soc(t=0) = soc(t=last) * (1 - sto_loss)^dt + charge * dt
                        soc_prev_day = model.soc[dev, district, y, day_y - 1, len(model.time_steps) - 1]
                        model.constraints.add(
                            model.soc[dev, district, y, day_y, 0] == soc_prev_day * (1 - devs[dev]["sto_loss"]) ** dt + model.ch[
                                dev, district, y, model.sigma[day_y], 0] * dt)

                # Cyclic year condition: For the last time step of the last day, the state of charge is based on the first time step of the first day
                soc_last = model.soc[dev, district, y, 51, cluster_horizon - 1]
                model.constraints.add(model.soc[dev, district, y, 0, 0] == soc_last * (1 - devs[dev]["sto_loss"]) ** dt + model.ch[
                    dev, district, y, model.sigma[0], 0] * dt)
                
    ################################################################################
    # Total energy import/feed-in #
    # Total amount of energy carrier taken from and to grid
    ################################################################################
    for district in model.districts:
        param = paramCon[district]
        for y in model.support_years:
            model.constraints.add(
                model.from_gas_grid_total[district, y] == dt * sum(
                    model.gas["from_grid", district, y, d, t] * param["cluster_weights"][d]
                    for d in model.clusters for t in model.time_steps))

            model.constraints.add(
                model.from_el_main_grid_total[district, y] == dt * sum(
                    model.power["from_main_grid", district, y, d, t] * param["cluster_weights"][d]
                    for d in model.clusters for t in model.time_steps))

            model.constraints.add(
                model.to_gas_grid_total[district, y] == dt * sum(
                    model.gas["to_grid", district, y, d, t] * param["cluster_weights"][d]
                    for d in model.clusters for t in model.time_steps))

            model.constraints.add(
                model.to_el_main_grid_total[district, y] == dt * sum(
                    model.power["to_main_grid", district, y, d, t] * param["cluster_weights"][d]
                    for d in model.clusters for t in model.time_steps))
            
            model.constraints.add(
                model.from_network_total[district, y] == dt * sum(
                    model.power["from_network", district, y, d, t] * param["cluster_weights"][d]
                    for d in model.clusters for t in model.time_steps))
            
            model.constraints.add(
                model.to_network_total[district, y] == dt * sum(
                    model.power["to_network", district, y, d, t] * param["cluster_weights"][d]
                    for d in model.clusters for t in model.time_steps))

            model.constraints.add(
                model.biom_import_total[district, y] == dt * sum(
                    model.biom["import", district, y, d, t] * param["cluster_weights"][d]
                    for d in model.clusters for t in model.time_steps))

            model.constraints.add(
                model.waste_import_total[district, y] == dt * sum(
                    model.waste["import", district, y, d, t] * param["cluster_weights"][d]
                    for d in model.clusters for t in model.time_steps))

            model.constraints.add(
                model.hydrogen_import_total[district, y] == dt * sum(
                    model.hydrogen["import", district, y, d, t] * param["cluster_weights"][d]
                    for d in model.clusters for t in model.time_steps))




    ################################################################################
    # Supply limitations (User input)
    ################################################################################
    for district in model.districts:
        param = paramCon[district]
        # Forbid/allow feed-in
        if not param.get("enable_feed_in_el", True):
            for y in model.support_years:
                model.constraints.add(model.to_el_main_grid_total[district, y] == 0)
        if not param.get("enable_feed_in_gas", True):
            for y in model.support_years:
                model.constraints.add(model.to_gas_grid_total[district, y] == 0)

        if param["enable_supply_el"] != True:
            for y in model.support_years:
                model.constraints.add(model.from_el_main_grid_total[district, y] == 0)
        if param["enable_cap_limit_el"] == True:
            model.constraints.add(model.grid_limit_el[district] <= param["cap_limit_el"])
        if param["enable_supply_limit_el"] == True:
            for y in model.support_years:
                model.constraints.add(model.from_el_grid_total[district, y] <= param["supply_limit_el"])

        # Limitation of gas supply
        if param["enable_supply_gas"] != True:
            for y in model.support_years:
                model.constraints.add(model.from_gas_grid_total[district, y] == 0)
        if param["enable_cap_limit_gas"] == True:
            model.constraints.add(model.grid_limit_gas[district] <= param["cap_limit_gas"])
        if param["enable_supply_limit_gas"] == True:
            for y in model.support_years:
                model.constraints.add(model.from_gas_grid_total[district, y] <= param["supply_limit_gas"])

        # Limitation of biomass supply
        if param["enable_supply_biomass"] != True:
            for y in model.support_years:
                model.constraints.add(model.biom_import_total[district, y] == 0)
        if param["enable_supply_limit_biomass"] == True:
            for y in model.support_years:
                model.constraints.add(model.biom_import_total[district, y] <= param["supply_limit_biomass"])

        # Limitation of waste supply
        if param["enable_supply_waste"] != True:
            for y in model.support_years:
                model.constraints.add(model.waste_import_total[district, y] == 0)
        if param["enable_supply_limit_waste"] == True:
            for y in model.support_years:
                model.constraints.add(model.waste_import_total[district, y] <= param["supply_limit_waste"])

        # Limitation of hydrogen supply
        if param["enable_supply_hydrogen"] != True:
            for y in model.support_years:
                model.constraints.add(model.hydrogen_import_total[district, y] == 0)
        if param["enable_supply_limit_hydrogen"] == True:
            for y in model.support_years:
                model.constraints.add(model.hydrogen_import_total[district, y] <= param["supply_limit_hydrogen"])

    ################################################################################
    # Economic constraints - according to VDI 2067 Blatt 1 - annuity method
    ################################################################################
    for district in model.districts:
        devs = devsCon[district]
        param = paramCon[district]
        data = dataCon[district]
        # Electricity costs and revenues (per support year with year-specific prices)
        for y in model.support_years:
            model.constraints.add(model.supply_costs_el[district, y] == model.from_el_main_grid_total[district, y] * param["price_supply_el_eh"][y])
            model.constraints.add(model.rev_feed_in_el[district, y] == model.to_el_main_grid_total[district, y] * param["revenue_feed_in_el_eh"][y])

            # Gas costs and revenues (per support year with year-specific prices)
            model.constraints.add(model.supply_costs_gas[district, y] == model.from_gas_grid_total[district,y] * param["price_supply_gas_eh"][y])
            model.constraints.add(model.rev_feed_in_gas[district, y] == model.to_gas_grid_total[district, y] * param["revenue_feed_in_gas"][y])

            # Biomass, waste, and hydrogen costs (per support year with year-specific prices)
            model.constraints.add(model.supply_costs_biom[district,y] == model.biom_import_total[district,y] * param["price_biomass"][y])
            model.constraints.add(model.supply_costs_waste[district, y] == model.waste_import_total[district, y] * param["price_waste"][y])
            model.constraints.add(model.supply_costs_hydrogen[district, y] == model.hydrogen_import_total[district, y] * param["price_hydrogen"][y])

        # Conditional capacity costs for electricity (same for all years)
        if param["enable_price_cap_el"]:
            model.constraints.add(model.cap_costs_el[district] == model.grid_limit_el[district] * param["price_cap_el"])
        else:
            model.constraints.add(model.cap_costs_el[district] == 0)

        # Gas capacity costs (same for all years)
        model.constraints.add(model.cap_costs_gas[district] == model.grid_limit_gas[district] * param["price_cap_gas"])

        # Investment and operational costs for each device (Annualized)
        for dev in model.all_devs:
            model.constraints.add(model.inv[dev, district] == devs[dev]["inv_var"] * model.cap[dev, district])  # investment costs
            model.constraints.add(model.inv_base[dev, district] == devs[dev]["inv_base"] * model.cap[dev, district])  # unsubsidized investment costs
            model.constraints.add(model.c_inv[dev, district] == model.inv[dev, district] * devs[dev]["ann_factor"])  # annualized investment costs
            model.constraints.add(model.c_inv_base[dev, district] == model.inv_base[dev, district] * devs[dev]["ann_factor"])  # unsubsidized annualized investment costs
            model.constraints.add(model.c_om[dev, district] == devs[dev]["cost_om"] * model.inv_base[dev, district])  # operation and maintenance costs. Use the unsubsidized costs for O&M calculation
            model.constraints.add(model.c_total[dev, district] == model.c_inv[dev, district] + model.c_om[dev, district])  # total annualized costs for investment and O&M

        # Combined total annualized investment and O&M costs for all devices
        model.constraints.add(model.total_annual_costs_devices[district] == sum(model.c_total[dev, district] for dev in model.all_devs))

        # Heat grid costs
        model.constraints.add(model.heat_grid_costs[district] == data.heat_grid_data["ann_costs"] + data.heat_grid_data["om_costs"])

        # Connection costs to electricity and gas grid (currently assumed to be a constant annual cost)
        model.constraints.add(model.total_connection_costs[district] == model.cap_costs_el[district] + model.cap_costs_gas[district])

        # Energy costs and revenues
        for y in model.support_years:
            model.constraints.add(model.total_energy_costs[district, y] ==
                                model.supply_costs_el[district, y]
                                + model.supply_costs_gas[district, y]
                                + model.supply_costs_biom[district, y]
                                + model.supply_costs_waste[district, y]
                                + model.supply_costs_hydrogen[district, y]
                                - model.rev_feed_in_el[district, y]
                                - model.rev_feed_in_gas[district, y])

        # CO2 tax term for emissions from gas, biomass, waste for each support year (Usually not paid by consumers, already included in energy prices)
        co2_tax_term={}
        for y in model.support_years:
            co2_tax_term[district, y] = (model.from_gas_grid_total[district, y] * param["co2_gas"][y] + model.biom_import_total[district, y] * param[
                "co2_biom"][y] + model.waste_import_total[district, y] * param["co2_waste"][y]) * param["co2_tax"][y]

        # additional costs and revenues can be added here if needed
        for y in model.support_years:
            model.constraints.add(model.misc_costs[district, y] == co2_tax_term[district, y])

        # Anualize Energy costs and miscellaneous costs over all support years by calculating Sum of the NPV of each support year/intervall and then annualizing it
        i = param["interest_rate"]
        q = 1 + i
        n = param["observation_time"]
        support_years = model.support_years
        sorted_years = sorted(support_years)

        # Calculate the weights for each support year based on the intervals they cover
        weights = {}
        for idx, year in enumerate(sorted_years):
            if idx < len(sorted_years) - 1:
                weights[year] = sorted_years[idx + 1] - year # time until next support year
            else:
                weights[year] = n - year # time from last support year to end of observation period

        # Calculate the NPV for energy and miscellaneous costs
        # Use geometric series formula for efficiency: sum(1/q^(year+k) for k in 0..n-1) = (1/q^year) * (1 - (1/q)^n) / (1 - 1/q)
        npv_energy[district] = {}
        npv_misc[district] = {}
        for idx, year in enumerate(sorted_years):
            interval_length = weights[year]
            # Calculate discount factor for this interval using geometric series formula
            if i != 0:  # If interest rate is not zero
                base_discount = 1 / (q ** year)
                interval_factor = (1 - (1/q) ** interval_length) / (1 - 1/q)
                discount_factor = base_discount * interval_factor
            else:  # If interest rate is zero, discount factor is simply the interval length
                discount_factor = interval_length
            
            npv_energy[district] += model.total_energy_costs[district,year] * discount_factor
            npv_misc[district] += model.misc_costs[district,year] * discount_factor

        # Annualize the NPV over the observation period using the annuity factor
        if i != 0:
            annuity_factor = (i * q**n) / (q**n - 1)
        else:
            annuity_factor = 1 / n  # If interest rate is 0, simply divide by number of years

        model.constraints.add(model.annualized_energy_costs[district] == npv_energy[district] * annuity_factor)
        model.constraints.add(model.annualized_misc_costs[district] == npv_energy[district] * annuity_factor)

        # Total annual costs (According to VDI 2067 Blatt 1:)
        # obj_tac = capital_cost + om_cost + supply_costs + taxes and other costs - revenues

    #%% DIFINE VARIBALES FOR OBJECTIVE FUNCTIONS
    tac_sum_total = 0
    co2_sum_total = 0

    for district in model.districts:
        tac_sum_distr = (model.total_annual_costs_devices  # Cost associated with devices (inv and om)
                        + model.total_connection_costs  # Cost for connection to el and gas grid
                        + model.heat_grid_costs  # Cost for heat grid inv and om
                        + model.annualized_energy_costs  # Energy supply costs minus revenues from feed-in
                        + model.annualized_misc_costs)  # Miscellaneous costs minus revenues
        
        # Sum up total annualized costs for all districts
        tac_sum_total += tac_sum_distr
        
        co2_sum_distr = sum(
        (
            model.from_el_grid_total[y] * param["co2_el_grid"][y]
            + model.from_gas_grid_total[y] * param["co2_gas"][y]
            + model.biom_import_total[y] * param["co2_biom"][y]
            + model.waste_import_total[y] * param["co2_waste"][y]
            + model.hydrogen_import_total[y] * param["co2_hydrogen"][y]
            - model.to_el_grid_total[y] * param["co2_el_feed_in"][y]
            - model.to_gas_grid_total[y] * param["co2_gas_feed_in"][y]
        ) * weights[y] for y in model.support_years
        )
    
        # Sum up total CO2 emissions for all districts
        co2_sum_total += co2_sum_distr

    # Total annualized costs for the whole observation period (sum of all districts)
    model.constraints.add(model.obj_tac == tac_sum_total)  

    model.constraints.add(model.obj_co2 == co2_sum_total)

    ################################################################################
    # Define Objective Function
    ################################################################################
    
    objective_rule=(1 - param["optimization_focus"]) * model.obj_tac + param["optimization_focus"] * model.obj_co2 # 1 = co2 minimization, 0 = cost minimization

    model.objective = pyo.Objective(rule=objective_rule, sense=pyo.minimize)

    return model


def process_results_per_district(model, dataCon, devsCon, paramCon, result_dic):
    """
    Function to capsle extracting the results from the Pyomo model.

    """

    # Folder to save model and results
    result_dir = "optimization_results"
    if not os.path.exists(result_dir):
        os.makedirs(result_dir)

    lp_filename = os.path.join(result_dir, f"ehdo_model_{data.scenario_name}.lp")
    model.write(lp_filename, io_options={"symbolic_solver_labels": True})

    # temporary log-file for the solver
    solver_log_path = os.path.join(result_dir, "solver_output_ehdo.log")
    # Path for error file
    errorfile_path = os.path.join(result_dir, 'errorfile_ehdo.txt')
        
        ##### For further analysis
    for district in model.districts:
        for k in all_devs:
            result_dict[k] = {}

        result_dict["devs"] = devs

        # Moved to run_optim_connect()
        # result_dict["tac"] = int(obj["tac"].X)      # EUR/a 
        # result_dict["co2"] = int(obj["co2"].X/1000) # t/a

        for k in cap.keys():
            result_dict[k] = {"cap": round(cap[k].X, 1)}

        # Add 'from_grid' capacity if the option is enabled
        if param["enable_cap_limit_el"]:
            result_dict["from_grid"] = {"cap": param["cap_limit_el"]}
            result_dict["to_grid"] = {"cap": param["cap_limit_el"]}
        else:
            result_dict["from_grid"] = {"cap": float("inf")}
            result_dict["to_grid"] = {"cap": float("inf")}
            

        result_dict["total_inv_cost"]        = int(sum(inv[k].X for k in cap.keys()) + data.heat_grid_data["costs"])
        result_dict["total_ann_inv_cost"]    = int(sum(c_inv[k].X for k in cap.keys()) + data.heat_grid_data["ann_costs"])
        result_dict["total_om_cost"]         = int(sum(c_om[k].X  for k in cap.keys()) + data.heat_grid_data["om_costs"])

        result_dict["from_el_main_grid_total"]    = int(from_el_main_grid_total.X / 1000)    # MWh
        result_dict["to_el_main_grid_total"]      = int(to_el_main_grid_total.X / 1000)      # MWh
        result_dict["from_network_total"]        = int(from_network_total.X / 1000)        # MWh
        result_dict["to_network_total"]          = int(to_network_total.X / 1000)          # MWh
        result_dict["from_gas_grid_total"]   = int(from_gas_grid_total.X / 1000)   # MWh
        result_dict["to_gas_grid_total"]     = int(to_gas_grid_total.X / 1000)     # MWh
        result_dict["biom_import_total"]     = int(biom_import_total.X / 1000)     # MWh
        result_dict["waste_import_total"]    = int(waste_import_total.X / 1000)    # MWh
        result_dict["hydrogen_import_total"] = int(hydrogen_import_total.X / 1000) # MWh

        # CO2 emissions
        result_dict["co2_onsite_emissions"] = int((from_gas_grid_total.X * param["co2_gas"] + biom_import_total.X * param["co2_biom"] + waste_import_total.X * param["co2_waste"])/1000)
        #result_dict["co2_global_emissions"] = int(result_dict["co2"]/1000)  # Moved to run_optim_connect()
        result_dict["co2_credit_feedin"] = int((to_el_main_grid_total.X * param["co2_el_feed_in"] + to_gas_grid_total.X * param["co2_gas_feed_in"])/1000)
        result_dict["co2_tax_total"] = int(result_dict["co2_onsite_emissions"] * param["co2_tax"] * 1000)  # EUR, only gas, biomass and waste.

        # Calculate maximum grid flows (electricity and gas)
        for k in ["from_grid", "to_grid", "from_main_grid", "to_main_grid", "from_network", "to_network"]:
            result_dict["max_el_" + k] = 0
            for d in clusters:
                for t in time_steps:
                    if power[k][d][t].X > result_dict["max_el_" + k]:
                        result_dict["max_el_" + k] = power[k][d][t].X
            result_dict["max_el_" + k] = int(result_dict["max_el_" + k])

        for k in ["from_grid", "to_grid"]:
            result_dict["max_gas_" + k] = 0
            for d in clusters:
                for t in time_steps:
                    if gas[k][d][t].X > result_dict["max_gas_" + k]:
                        result_dict["max_gas_" + k] = gas[k][d][t].X
            result_dict["max_gas_" + k] = int(result_dict["max_gas_" + k])

        result_dict["max_biom"] = 0
        for d in clusters:
            for t in time_steps:
                if biom["import"][d][t].X > result_dict["max_biom"]:
                    result_dict["max_biom"] = biom["import"][d][t].X
        result_dict["max_biom"] = int(result_dict["max_biom"])

        result_dict["max_waste"] = 0
        for d in clusters:
            for t in time_steps:
                if waste["import"][d][t].X > result_dict["max_waste"]:
                    result_dict["max_waste"] = waste["import"][d][t].X
        result_dict["max_waste"] = int(result_dict["max_waste"])

        result_dict["max_hydrogen"] = 0
        for d in clusters:
            for t in time_steps:
                if hydrogen["import"][d][t].X > result_dict["max_hydrogen"]:
                    result_dict["max_hydrogen"] = hydrogen["import"][d][t].X
        result_dict["max_hydrogen"] = int(result_dict["max_hydrogen"])

        # Costs
        result_dict["supply_costs_el"] = int(supply_costs_el.X)
        result_dict["cap_costs_el"] = int(cap_costs_el.X)
        result_dict["total_el_costs"] = int(supply_costs_el.X + cap_costs_el.X)
        result_dict["rev_feed_in_el"] = int(rev_feed_in_el.X)

        result_dict["supply_costs_gas"] = int(supply_costs_gas.X)
        result_dict["cap_costs_gas"] = int(cap_costs_gas.X)
        result_dict["total_gas_costs"] = int(supply_costs_gas.X + cap_costs_gas.X)
        result_dict["rev_feed_in_gas"] = int(rev_feed_in_gas.X)

        result_dict["supply_costs_biom"] = int(supply_costs_biom.X)
        result_dict["supply_costs_waste"] = int(supply_costs_waste.X)
        result_dict["supply_costs_hydrogen"] = int(supply_costs_hydrogen.X)

        # Prepare time series of renewable generation (without curtailment)
        
        result_dict["PV_generation_uncl"] = devs["PV"]["norm_power"] / 1000 * area["PV"].X          # in kW
        result_dict["WT_generation_uncl"] = devs["WT"]["norm_power"] * cap["WT"].X                  # in kW
        result_dict["STC_generation_uncl"] = devs["STC"]["norm_power"] / 1000 * area["STC"].X       # in kW

        # Prepare time series of renewable curtailment
        power["PV_curtail"] = {}
        power["WT_curtail"] = {}
        power["WAT_curtail"] = {}
        heat["STC_curtail"] = {}
        for d in clusters:
            power["PV_curtail"][d] = {}
            power["WT_curtail"][d] = {}
            power["WAT_curtail"][d] = {}
            heat["STC_curtail"][d] = {}
            for t in time_steps:
                power["PV_curtail"][d][t] = devs["PV"]["norm_power_clustered"][d][t]/1000 * area["PV"].X - power["PV"][d][t].X
                power["WT_curtail"][d][t] = devs["WT"]["norm_power_clustered"][d][t] * cap["WT"].X - power["WT"][d][t].X
                power["WAT_curtail"][d][t] = np.min([cap["WAT"].X, devs["WAT"]["potential"]]) - power["WAT"][d][t].X
                heat["STC_curtail"][d][t] = devs["STC"]["norm_power_clustered"][d][t]/1000  * area["STC"].X - heat["STC"][d][t].X

        result_dict["PV"]["curtailed"]  = int(dt * (sum(sum(power["PV_curtail"][d][t] for t in time_steps) * param["cluster_weights"][d] for d in clusters)))
        result_dict["STC"]["curtailed"] = int(dt * (sum(sum(heat["STC_curtail"][d][t] for t in time_steps) * param["cluster_weights"][d] for d in clusters)))
        result_dict["WT"]["curtailed"]  = int(dt * (sum(sum(power["WT_curtail"][d][t] for t in time_steps) * param["cluster_weights"][d] for d in clusters)))
        result_dict["WAT"]["curtailed"] = int(dt * (sum(sum(power["WAT_curtail"][d][t] for t in time_steps) * param["cluster_weights"][d] for d in clusters)))

        result_dict["power_profile"] = {}
        result_dict["power_kW"] = {}
        for device in ["PV", "WT", "WAT", "HP", "EB", "CC", "CHP", "BCHP", "WCHP", "ELYZ", "FC", "from_grid",
                       "to_grid"]:
            result_dict["power_profile"][device] = []
            for d in clusters:
                for t in time_steps:
                    result_dict["power_profile"][device].append(power[device][d][t].X)
            result_dict["power_kW"][device] = int(max(result_dict["power_profile"][device]))

        # Heat to/from devices
        result_dict["heat_profile"] = {}
        result_dict["heat_kW"] = {}
        for device in ["STC", "HP", "EB", "AC", "CHP", "BOI", "GHP", "BCHP", "BBOI", "WCHP", "WBOI", "FC"]:
            result_dict["heat_profile"][device] = []
            for d in clusters:
                for t in time_steps:
                    result_dict["heat_profile"][device].append(heat[device][d][t].X)
            result_dict["heat_kW"][device] = int(max(result_dict["heat_profile"][device]))

        result_dict["area"] = {}
        for device in ["PV", "STC"]:
            result_dict["area"][device] = int(area[device].X)

        # Calculate generation
        eps = 0.01
        for k in ["STC", "HP", "EB", "BOI", "GHP", "BBOI", "WBOI"]:
            result_dict[k]["gen_kWh"] = dt * sum(sum(heat[k][d][t].X for t in time_steps) * param["cluster_weights"][d] for d in clusters)  # in kWh
            result_dict[k]["gen"] = int(dt * sum(sum(heat[k][d][t].X for t in time_steps) * param["cluster_weights"][d] for d in clusters)/1000)  # in MWh

        for k in ["CC", "AC"]:
            result_dict[k]["gen_kWh"] = dt * sum(sum(cool[k][d][t].X for t in time_steps) * param["cluster_weights"][d] for d in clusters)  # in kWh
            result_dict[k]["gen"] = int(dt * sum(sum(cool[k][d][t].X for t in time_steps) * param["cluster_weights"][d] for d in clusters)/1000)  # in MWh

        for k in ["PV", "WT", "WAT", "CHP", "BCHP", "WCHP", "ELYZ", "FC"]:
            result_dict[k]["gen_kWh"] = dt * sum(sum(power[k][d][t].X for t in time_steps) * param["cluster_weights"][d] for d in clusters)  # in kWh
            result_dict[k]["gen"] = int(dt * sum(sum(power[k][d][t].X for t in time_steps) * param["cluster_weights"][d] for d in clusters)/1000)  # in MWh

        # Calculate hydrogen generation for ELYZ
        result_dict["ELYZ"]["gen_H2"] = int(dt * sum(sum(power["ELYZ"][d][t].X * devs["ELYZ"]["eta_el"]for t in time_steps) * param["cluster_weights"][d] for d in clusters)/1000)  # in MWh

        for k in ["SAB"]:
            result_dict[k]["gen_kWh"] = dt * sum(sum(gas[k][d][t].X for t in time_steps) * param["cluster_weights"][d] for d in clusters)  # in kWh
            result_dict[k]["gen"] = int(dt * sum(sum(gas[k][d][t].X for t in time_steps) * param["cluster_weights"][d] for d in clusters)/1000)  # in MWh

        # Calculate full load hours
        for k in ["PV", "WT", "WAT", "STC", "HP", "EB", "CC", "AC", "CHP", "BOI", "GHP", "BCHP", "BBOI", "WCHP", "WBOI", "ELYZ", "FC", "SAB"]:
            if cap[k].X > eps:
                result_dict[k]["hrs"] = int(result_dict[k]["gen_kWh"] / cap[k].X)
            else:
                result_dict[k]["hrs"] = 0


        # Select technologies that are installed (to list only these in results)
        for k in all_devs:
            if cap[k].X > eps:
                result_dict[k]["inst"] = True
            else:
                result_dict[k]["inst"] = False

        # Calculate charge cycles of storages
        for k in ["TES", "CTES", "BAT", "H2S", "GS"]:
            if cap[k].X > eps:
                result_dict[k]["chc"] = int(dt * sum(sum(abs(ch[k][d][t].X)/2 for t in time_steps) * param["cluster_weights"][d] for d in clusters) / cap[k].X)
            else:
                result_dict[k]["chc"] = 0

        # Calculate volume of thermal storages
        for k in ["TES", "CTES"]:
            result_dict[k]["vol_liter"] = round(cap[k].X / (param["c_w"] * param["rho_w"] * devs[k]["delta_T"]) * 3600 * 1000, 1)

        # Calculate emissions
        result_dict["total_co2_el"] = int(from_el_main_grid_total.X * param["co2_el_grid"]/1000) # t/a
        result_dict["total_co2_el_feed_in"] = int(to_el_main_grid_total.X * param["co2_el_feed_in"]/1000) # t/a
        result_dict["total_co2_gas"] = int(from_gas_grid_total.X * param["co2_gas"]/1000) # t/a
        result_dict["total_co2_gas_feed_in"] = int(to_gas_grid_total.X * param["co2_gas_feed_in"]/1000) # t/a
        result_dict["total_co2_biom"] = int(biom_import_total.X * param["co2_biom"]/1000) # t/a
        result_dict["total_co2_waste"] = int(waste_import_total.X * param["co2_waste"]/1000) # t/a
        result_dict["total_co2_hydrogen"] = int(hydrogen_import_total.X * param["co2_hydrogen"]/1000) # t/a

        return result_dict

def save_results_csv(result_dict, scenario_name, result_dir, all_devs):
    """
    Saves specific results from result_dict into a CSV file.

    Parameters
    ----------
    result_dict : dict
        Dictionary containing the results of the optimization.
    scenario_name : str
        Name of the scenario, used to name the CSV file.
    result_dir : str
        Directory where the CSV file will be saved.

    Returns
    -------
    None
    """
    # Ensure the result directory exists
    os.makedirs(result_dir, exist_ok=True)

    # Define the output file path
    csv_file_path = os.path.join(result_dir, f"{scenario_name}_results.csv")

    # Prepare the data to be written to the CSV file
    data_to_save = [
        ["Cost_parameter", "Value", "Unit"],                                              # Header row cost-parameters
        ["co2_tax_total", result_dict.get("co2_tax_total", ""), "EUR/a"],                   # CO2 tax total
        ["total_inv_cost", result_dict.get("total_inv_cost", ""),"EUR/a"],                  # Total investment cost
        ["total_ann_inv_cost", result_dict.get("total_ann_inv_cost", ""),"EUR/a"],          # Total annual investment cost
        ["total_om_cost", result_dict.get("total_om_cost", ""),"EUR/a"],                    # Total operation and maintenance cost
        ["supply_costs_el", result_dict.get("supply_costs_el", ""),"EUR/a"],                # Supply costs for electricity
        ["cap_costs_el", result_dict.get("cap_costs_el", ""),"EUR/a"],                      # Capacity costs for electricity
        ["total_el_costs", result_dict.get("total_el_costs", ""),"EUR/a"],                  # Total electricity costs
        ["rev_feed_in_el", result_dict.get("rev_feed_in_el", ""),"EUR/a"],                  # Revenue from electricity feed-in
        ["supply_costs_gas", result_dict.get("supply_costs_gas", ""),"EUR/a"],              # Supply costs for gas
        ["cap_costs_gas", result_dict.get("cap_costs_gas", ""),"EUR/a"],                    # Capacity costs for gas
        ["total_gas_costs", result_dict.get("total_gas_costs", ""),"EUR/a"],                # Total gas costs
        ["rev_feed_in_gas", result_dict.get("rev_feed_in_gas", ""),"EUR/a"],                # Revenue from gas feed-in
        ["supply_costs_biom", result_dict.get("supply_costs_biom", ""),"EUR/a"],            # Supply costs for biomass
        ["supply_costs_waste", result_dict.get("supply_costs_waste", ""),"EUR/a"],          # Supply costs for waste
        ["supply_costs_hydrogen", result_dict.get("supply_costs_hydrogen", ""),"EUR/a"],    # Supply costs for hydrogen
        [],                                                                               # Empty row for separation
        ["Co2_parameter", "Value", "Unit"],                                               # Header row co2-parameters
        ["co2_onsite_emissions", result_dict.get("co2_onsite_emissions", ""),"t/a"],    # Onsite CO2 emissions
        ["co2_credit_feedin", result_dict.get("co2_credit_feedin", ""),"t/a"],          # CO2 credit from feed-in
        ["total_co2_el", result_dict.get("total_co2_el", ""),"t/a"],                    # Total CO2 emissions from electricity
        ["total_co2_el_feed_in", result_dict.get("total_co2_el_feed_in", ""),"t/a"],    # Total CO2 emissions from electricity feed-in
        ["total_co2_gas", result_dict.get("total_co2_gas", ""),"t/a"],                  # Total CO2 emissions from gas
        ["total_co2_gas_feed_in", result_dict.get("total_co2_gas_feed_in", ""),"t/a"],  # Total CO2 emissions from gas feed-in
        ["total_co2_biom", result_dict.get("total_co2_biom", ""),"t/a"],                # Total CO2 emissions from biomass
        ["total_co2_waste", result_dict.get("total_co2_waste", ""),"t/a"],              # Total CO2 emissions from waste
        ["total_co2_hydrogen", result_dict.get("total_co2_hydrogen", ""),"t/a"],        # Total CO2 emissions from hydrogen
        [],                                                                             # Empty row for separation
        ["Grid_flows", "Value", "Unit"],                                                # Header row grid flows
        ["from_el_main_grid_total", result_dict.get("from_el_main_grid_total", ""),"MWh"],  # Total electricity from grid
        ["to_el_main_grid_total", result_dict.get("to_el_main_grid_total", ""),"MWh"],      # Total electricity to grid
        ["from_network_total", result_dict.get("from_network_total", ""),"MWh"],            # Total electricity from network
        ["to_network_total", result_dict.get("to_network_total", ""),"MWh"],                # Total electricity to network
        ["from_gas_grid_total", result_dict.get("from_gas_grid_total", ""),"MWh"],          # Total gas from grid
        ["to_gas_grid_total", result_dict.get("to_gas_grid_total", ""),"MWh"],              # Total gas to grid
        ["biom_import_total", result_dict.get("biom_import_total", ""),"MWh"],              # Total biomass imported
        ["waste_import_total", result_dict.get("waste_import_total", ""),"MWh"],            # Total waste imported
        ["hydrogen_import_total", result_dict.get("hydrogen_import_total", ""),"MWh"],      # Total hydrogen imported
        ["max_el_from_grid", result_dict.get("max_el_from_grid", ""),"kW"],                 # Maximum electricity from grid
        ["max_el_to_grid", result_dict.get("max_el_to_grid", ""),"kW"],                     # Maximum electricity to grid
        ["max_el_from_main_grid", result_dict.get("max_el_from_main_grid", ""),"kW"],       # Maximum electricity from main grid
        ["max_el_to_main_grid", result_dict.get("max_el_to_main_grid", ""),"kW"],           # Maximum electricity to main grid
        ["max_el_from_network", result_dict.get("max_el_from_network", ""),"kW"],           # Maximum electricity from network
        ["max_el_to_network", result_dict.get("max_el_to_network", ""),"kW"],               # Maximum electricity to network
        ["max_gas_from_grid", result_dict.get("max_gas_from_grid", ""),"kW"],               # Maximum gas from grid
        ["max_gas_to_grid", result_dict.get("max_gas_to_grid", ""),"kW"],                   # Maximum gas to grid
        ["max_biom", result_dict.get("max_biom", ""),""],                                   # Maximum biomass import
        ["max_waste", result_dict.get("max_waste", ""),""],                                 # Maximum waste import
        ["max_hydrogen", result_dict.get("max_hydrogen", ""),""],                           # Maximum hydrogen import
        [],                                                                                 # Empty row for separation
        ["Areas PV and STC", "Value", "Unit"],                                              # Header row generation parameters
        ["PV", result_dict.get("area", {}).get("PV", ""),"qm"],                             # Area for PV
        ["STC", result_dict.get("area", {}).get("STC", ""),"qm"],                           # Area for STC
        [],                                                                                 # Empty row for separation
        ["volumes of thermal storages", "Value","Unit"],                                    # Header row for storage volumes
        ["TES", result_dict.get("TES", {}).get("vol_liter", ""),"l"],                       # Volume of TES in liters
        ["CTES", result_dict.get("CTES", {}).get("vol_liter", ""),"l"],                     # Volume of CTES in liters
        ["", ""],                                                                           # Empty row for separation
        ["Device-capacity", "Value", "Unit"],                                               # Header row for device capacities

    ]
    # Add devices to the CSV file if they are installed
    for device in all_devs:
        if result_dict.get(device, {}).get("inst", False):  # Check if the device is installed
            capacity = result_dict.get(device, {}).get("cap", "")  # Get the capacity of the device
            data_to_save.append([device, capacity,"kW"])  # Add the device name to the CSV file

    # Write the data to the CSV file
    with open(csv_file_path, mode="w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file, delimiter=";")
        writer.writerows(data_to_save)

    print(f"Results saved to {csv_file_path}")
    