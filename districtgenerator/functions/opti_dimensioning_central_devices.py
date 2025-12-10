# -*- coding: utf-8 -*-
"""
EHDO - ENERGY HUB DESIGN OPTIMIZATION Tool
Pyomo Version

This script is a Pyomo-based translation of the original Gurobi model.
"""

import pyomo.environ as pyo
from pyomo.util.infeasible import log_infeasible_constraints
import sys
from io import StringIO
import numpy as np
import time
from datetime import datetime
import os
import matplotlib.pyplot as plt
import textwrap
import districtgenerator.functions.solver_config as solver_config


def run_optim(data, devs, param, dem, result_dict):
    """
    Runs the Energy Hub Design Optimization using Pyomo.

    Parameters
    ----------
    data : object
        Contains time series information.
    devs : dict
        Contains device-specific parameters and investment data.
    param : dict
        Contains economic parameters, prices, and other model settings.
    dem : dict
        Contains demand profiles (heat, power, cool).
    result_dict : dict
        A dictionary that will be populated with the optimization results.

    Returns
    -------
    dict
        The populated result dictionary, or the original dict if no solution is found.
    """
    start_time = time.time()

    # Build the model
    model = build_model(data=data, devs=devs, param=param, dem=dem)
    model_building_time = time.time() - start_time

    print(f"Precalculation and model set up done in {model_building_time:.2f} seconds.")

    # Solve the model and extract results
    result_dict = solve_model_and_extract_results(data=data, model=model, devs=devs, param=param,
                                                  result_dict=result_dict)
    model_solve_time = time.time() - start_time - model_building_time

    # Total time needed
    total_time = time.time() - start_time

    # Maybe record the times into a log file

    # print(f"\n Time needed for building the model: {model_building_time:.2f} seconds.")
    # print(f" Time needed for solving the model: {model_solve_time:.2f} seconds.")
    # print(f" Total time needed: {total_time:.2f} seconds.")

    return result_dict


def build_model(data, devs, param, dem):
    model = pyo.ConcreteModel("Energy_Hub_Model")

    # %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    # 1. Initialize Pyomo Model and Define Sets
    # %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

    # Model Parameters

    # calculate cluster time horizon
    cluster_horizon = int(data.time["clusterLength"] / data.time["timeResolution"])
    dt = data.time["timeResolution"] / data.time["dataResolution"]

    model.clusters = pyo.RangeSet(0, data.time["clusterNumber"] - 1)
    model.time_steps = pyo.RangeSet(0, cluster_horizon - 1)
    model.year = pyo.RangeSet(0, 51)  # 52 weeks

    # Get sigma function that assigns each time period (day or week) of the year to a design period
    model.sigma = pyo.Param(model.year, initialize=param["sigma"])

    # Create sets for all device types
    all_devs_list = ["PV", "WT", "STC", "WAT", "HP", "EB", "CC", "AC", "CHP", "BOI", "GHP",
                     "BCHP", "BBOI", "WCHP", "WBOI", "ELYZ", "FC", "H2S", "SAB", "TES",
                     "CTES", "BAT", "GS"]

    gas_devs_list = ["CHP", "BOI", "GHP", "SAB", "from_grid", "to_grid"]
    power_devs_list = ["PV", "WT", "WAT", "HP", "EB", "CC", "CHP", "BCHP", "WCHP", "ELYZ", "FC", "from_grid", "to_grid"]
    heat_devs_list = ["STC", "HP", "EB", "AC", "CHP", "BOI", "GHP", "BCHP", "BBOI", "WCHP", "WBOI", "FC"]
    cool_devs_list = ["CC", "AC"]
    hydrogen_devs_list = ["ELYZ", "FC", "SAB", "import"]
    biom_devs_list = ["BCHP", "BBOI", "import"]
    waste_devs_list = ["WCHP", "WBOI", "import"]
    storage_devs_list = ["TES", "CTES", "BAT", "H2S", "GS"]
    area_devs_list = ["PV", "STC"]

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

    # %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    # 2. Create Pyomo Variables
    # %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

    model.cap = pyo.Var(model.all_devs, within=pyo.NonNegativeReals, name="nominal_capacity")
    model.area = pyo.Var(model.area_devs, within=pyo.NonNegativeReals, name="roof_area")
    model.gas = pyo.Var(model.gas_devs, model.clusters, model.time_steps, within=pyo.NonNegativeReals)
    model.power = pyo.Var(model.power_devs, model.clusters, model.time_steps, within=pyo.NonNegativeReals)
    model.heat = pyo.Var(model.heat_devs, model.clusters, model.time_steps, within=pyo.NonNegativeReals)
    model.cool = pyo.Var(model.cool_devs, model.clusters, model.time_steps, within=pyo.NonNegativeReals)
    model.hydrogen = pyo.Var(model.hydrogen_devs, model.clusters, model.time_steps, within=pyo.NonNegativeReals)
    model.biom = pyo.Var(model.biom_devs, model.clusters, model.time_steps, within=pyo.NonNegativeReals)
    model.waste = pyo.Var(model.waste_devs, model.clusters, model.time_steps, within=pyo.NonNegativeReals)
    model.ch = pyo.Var(model.storage_devs, model.clusters, model.time_steps, within=pyo.Reals)
    model.soc = pyo.Var(model.storage_devs, model.year, model.time_steps, within=pyo.NonNegativeReals)
    model.inv = pyo.Var(model.all_devs, within=pyo.NonNegativeReals)
    model.c_inv = pyo.Var(model.all_devs, within=pyo.NonNegativeReals)
    model.c_om = pyo.Var(model.all_devs, within=pyo.NonNegativeReals)
    model.c_total = pyo.Var(model.all_devs, within=pyo.NonNegativeReals)
    model.grid_limit_el = pyo.Var(within=pyo.NonNegativeReals)
    model.grid_limit_gas = pyo.Var(within=pyo.NonNegativeReals)
    model.from_el_grid_total = pyo.Var(within=pyo.NonNegativeReals)
    model.to_el_grid_total = pyo.Var(within=pyo.NonNegativeReals)
    model.from_gas_grid_total = pyo.Var(within=pyo.NonNegativeReals)
    model.to_gas_grid_total = pyo.Var(within=pyo.NonNegativeReals)
    model.biom_import_total = pyo.Var(within=pyo.NonNegativeReals)
    model.waste_import_total = pyo.Var(within=pyo.NonNegativeReals)
    model.hydrogen_import_total = pyo.Var(within=pyo.NonNegativeReals)
    model.rev_feed_in_gas = pyo.Var(within=pyo.NonNegativeReals)
    model.rev_feed_in_el = pyo.Var(within=pyo.NonNegativeReals)
    model.supply_costs_el = pyo.Var(within=pyo.NonNegativeReals)
    model.cap_costs_el = pyo.Var(within=pyo.NonNegativeReals)
    model.supply_costs_gas = pyo.Var(within=pyo.NonNegativeReals)
    model.cap_costs_gas = pyo.Var(within=pyo.NonNegativeReals)
    model.supply_costs_biom = pyo.Var(within=pyo.NonNegativeReals)
    model.supply_costs_waste = pyo.Var(within=pyo.Reals)
    model.supply_costs_hydrogen = pyo.Var(within=pyo.NonNegativeReals)
    model.obj_tac = pyo.Var(within=pyo.Reals)
    model.obj_co2 = pyo.Var(within=pyo.Reals)

    ################################################################################
    # Define maximum Capacity of devices Constraints
    ################################################################################
    model.constraints = pyo.ConstraintList()

    # Add capacity constraints for all devices as specified in devs
    for dev in model.all_devs:
        if not devs[dev]["feasible"]:  # if device is not feasible, set capacity to 0
            model.constraints.add(model.cap[dev] == 0)
        else:
            if dev in model.area_devs:
                continue  # Area constraints are handled separately and no capacity constraints are needed
            min_cap = devs[dev].get("min_cap")
            max_cap = devs[dev].get("max_cap")
            if min_cap is not None: model.constraints.add(model.cap[dev] >= min_cap)
            if max_cap is not None: model.constraints.add(model.cap[dev] <= max_cap)

    # Set area constraints for devices that require area as specified in devs
    for dev in model.area_devs:
        if devs[dev]["feasible"]:
            min_area = devs[dev].get("min_area")
            max_area = devs[dev].get("max_area")
            if min_area is not None: model.constraints.add(model.area[dev] >= min_area)
            if max_area is not None: model.constraints.add(model.area[dev] <= max_area)

    # Set the capacities of the devices if they are feasible
    for d in model.clusters:
        for t in model.time_steps:
            # Add constraints for the device operation based on the device capacity
            for dev in ["STC", "EB", "HP", "BOI", "GHP", "BBOI", "WBOI"]:  # Heat devices
                model.constraints.add(model.heat[dev, d, t] <= model.cap[dev])
            for dev in ["PV", "WT", "WAT", "CHP", "BCHP", "WCHP", "ELYZ", "FC"]:  # Power devices
                model.constraints.add(model.power[dev, d, t] <= model.cap[dev])
            for dev in ["CC", "AC"]:  # Cooling devices
                model.constraints.add(model.cool[dev, d, t] <= model.cap[dev])
            for dev in ["SAB"]:  # Gas devices
                model.constraints.add(model.gas[dev, d, t] <= model.cap[dev])

            # Limitation of power and gas from and to the grid
            model.constraints.add(model.power["from_grid", d, t] <= model.grid_limit_el)
            model.constraints.add(model.power["to_grid", d, t] <= model.grid_limit_el)
            model.constraints.add(model.gas["from_grid", d, t] <= model.grid_limit_gas)
            model.constraints.add(model.gas["to_grid", d, t] <= model.grid_limit_gas)

    # Correlation to translate area to capacity for PV and STC
    model.constraints.add(model.cap["PV"] == model.area["PV"] * devs["PV"]["G_stc"] * devs["PV"]["eta"])
    model.constraints.add(model.cap["STC"] == model.area["STC"] * devs["STC"]["G_stc"] * devs["STC"]["eta"])

    # state of charge < storage capacity
    for dev in model.storage_devs:
        for day_y in model.year:
            for t in model.time_steps:
                model.constraints.add(model.soc[dev, day_y, t] <= model.cap[dev])

    #################################################################################
    # Energy Conversion Constraints (Input / Output Relations)
    #################################################################################

    for d in model.clusters:
        for t in model.time_steps:
            # Photovoltaics power limited by clustered norm power
            model.constraints.add(
                model.power["PV", d, t] <= devs["PV"]["norm_power_clustered"][d][t] / 1000 * model.area["PV"])
            # Wind turbine power limited by clustered norm power
            model.constraints.add(model.power["WT", d, t] <= devs["WT"]["norm_power_clustered"][d][t] * model.cap["WT"])
            # Hydropower power limited by potential
            model.constraints.add(model.power["WAT", d, t] <= devs["WAT"]["potential"])
            # Solar thermal collector heat limited by clustered norm power
            model.constraints.add(
                model.heat["STC", d, t] <= devs["STC"]["norm_power_clustered"][d][t] / 1000 * model.area["STC"])
            # Electric heat pump correlation between heat and electric power
            model.constraints.add(model.heat["HP", d, t] == model.power["HP", d, t] * devs["HP"]["COP"][d][t])
            # Electric boiler correlation between heat and electric power
            model.constraints.add(model.heat["EB", d, t] == model.power["EB", d, t] * devs["EB"]["eta_th"])
            # Compression chiller correlation between cooling and electric power (time-dependent COP)
            model.constraints.add(model.cool["CC", d, t] == model.power["CC", d, t] * devs["CC"]["COP"][d][t])
            # Absorption chiller correlation between cooling and heat power
            model.constraints.add(model.cool["AC", d, t] == model.heat["AC", d, t] * devs["AC"]["eta_th"])
            # Gas CHP correlation between production of power and heat and gas consumption
            model.constraints.add(model.power["CHP", d, t] == model.gas["CHP", d, t] * devs["CHP"]["eta_el"])
            model.constraints.add(model.heat["CHP", d, t] == model.gas["CHP", d, t] * devs["CHP"]["eta_th"])
            # Gas boiler correlation between heat and gas consumption
            model.constraints.add(model.heat["BOI", d, t] == model.gas["BOI", d, t] * devs["BOI"]["eta_th"])
            # Gas heat pump correlation between heat and gas consumption
            model.constraints.add(model.heat["GHP", d, t] == model.gas["GHP", d, t] * devs["GHP"]["COP"])
            # Biomass CHP correlation between production of power and heat and biomass consumption
            model.constraints.add(model.power["BCHP", d, t] == model.biom["BCHP", d, t] * devs["BCHP"]["eta_el"])
            model.constraints.add(model.heat["BCHP", d, t] == model.biom["BCHP", d, t] * devs["BCHP"]["eta_th"])
            # Biomass boiler correlation between heat and biomass consumption
            model.constraints.add(model.heat["BBOI", d, t] == model.biom["BBOI", d, t] * devs["BBOI"]["eta_th"])
            # Waste CHP correlation between production of power and heat and waste consumption
            model.constraints.add(model.power["WCHP", d, t] == model.waste["WCHP", d, t] * devs["WCHP"]["eta_el"])
            model.constraints.add(model.heat["WCHP", d, t] == model.waste["WCHP", d, t] * devs["WCHP"]["eta_th"])
            # Waste boiler correlation between heat and waste consumption
            model.constraints.add(model.heat["WBOI", d, t] == model.waste["WBOI", d, t] * devs["WBOI"]["eta_th"])
            # Electrolyzer correlation between hydrogen production and electric power consumption
            model.constraints.add(model.hydrogen["ELYZ", d, t] == model.power["ELYZ", d, t] * devs["ELYZ"]["eta_el"])
            # Fuel cell correlation between hydrogen consumption and electric power production
            model.constraints.add(model.power["FC", d, t] == model.hydrogen["FC", d, t] * devs["FC"]["eta_el"])
            if devs["FC"]["enable_heat_diss"]:  # Heat can also be dissipated
                model.constraints.add(model.heat["FC", d, t] <= model.hydrogen["FC", d, t] * devs["FC"]["eta_th"])
            else:  # Heat must be used
                model.constraints.add(model.heat["FC", d, t] == model.hydrogen["FC", d, t] * devs["FC"]["eta_th"])
            # Sabatier reactor correlation between hydrogen consumption and gas production
            model.constraints.add(model.gas["SAB", d, t] == model.hydrogen["SAB", d, t] * devs["SAB"]["eta"])

    ################################################################################
    # Energy balances
    ################################################################################

    for d in model.clusters:
        for t in model.time_steps:
            # Heat supply and demand balance
            heat_supply = sum(model.heat[dev, d, t] for dev in
                              ["STC", "HP", "EB", "CHP", "BOI", "GHP", "BCHP", "BBOI", "WCHP", "WBOI", "FC"])
            heat_demand = dem["heat"][d][t] + model.heat["AC", d, t] + model.ch["TES", d, t]
            model.constraints.add(heat_supply == heat_demand)

            # Electric power supply and demand balance
            power_supply = sum(
                model.power[dev, d, t] for dev in ["PV", "WT", "WAT", "CHP", "BCHP", "WCHP", "FC", "from_grid"])
            power_demand = dem["power"][d][t] + sum(
                model.power[dev, d, t] for dev in ["HP", "EB", "CC", "ELYZ", "to_grid"]) + model.ch["BAT", d, t]
            model.constraints.add(power_supply == power_demand)

            # Cooling supply and demand balance
            cool_supply = model.cool["AC", d, t] + model.cool["CC", d, t]
            cool_demand = dem["cool"][d][t] + model.ch["CTES", d, t]
            model.constraints.add(cool_supply == cool_demand)

            # Gas supply and demand balance
            gas_supply = model.gas["from_grid", d, t] + model.gas["SAB", d, t]
            gas_demand = sum(model.gas[dev, d, t] for dev in ["CHP", "BOI", "GHP", "to_grid"]) + model.ch["GS", d, t]
            model.constraints.add(gas_supply == gas_demand)

            # Hydrogen supply and demand balance
            h2_supply = model.hydrogen["ELYZ", d, t] + model.hydrogen["import", d, t]
            h2_demand = sum(model.hydrogen[dev, d, t] for dev in ["FC", "SAB"]) + model.ch["H2S", d, t]
            model.constraints.add(h2_supply == h2_demand)

            # Biomass supply and demand balance
            model.constraints.add(model.biom["import", d, t] == model.biom["BCHP", d, t] + model.biom["BBOI", d, t])

            # Waste supply and demand balance
            model.constraints.add(model.waste["import", d, t] == model.waste["WCHP", d, t] + model.waste["WBOI", d, t])

    ################################################################################
    # Meet peak demands of unclustered demands to ensure the design can handle peak loads
    ################################################################################

    if param["peak_dem_met_conv"] == False:
        # Heating (conventional - only controllable devices)
        model.constraints.add(model.cap["HP"] + model.cap["EB"]
                              + model.cap["CHP"] / devs["CHP"]["eta_el"] * devs["CHP"]["eta_th"]
                              + model.cap["BOI"]
                              + model.cap["GHP"]
                              + model.cap["BCHP"] / devs["BCHP"]["eta_el"] * devs["BCHP"]["eta_th"]
                              + model.cap["BBOI"]
                              + model.cap["WCHP"] / devs["WCHP"]["eta_el"] * devs["WCHP"]["eta_th"]
                              + model.cap["WBOI"]
                              + model.cap["FC"] / devs["FC"]["eta_el"] * devs["FC"]["eta_th"]
                              >= param["peak_heat"])

        # Cooling
        model.constraints.add(model.cap["CC"] + model.cap["AC"] >= param["peak_cool"])

        # Power
        model.constraints.add(
            model.cap["CHP"] + model.cap["BCHP"] + model.cap["WCHP"] + model.cap["FC"] + model.grid_limit_el >= param[
                "peak_power"])

        # Hydrogen
        if (param["enable_supply_hydrogen"] == False) and devs["ELYZ"]["feasible"]:
            model.constraints.add(model.cap["ELYZ"] >= param["peak_hydrogen"])

    else:  # With STC, PV, WIND, HYDROPOWER (WAT)
        # Heating (with renewable sources)
        model.constraints.add(model.cap["STC"] + model.cap["HP"] + model.cap["EB"]
                              + model.cap["CHP"] / devs["CHP"]["eta_el"] * devs["CHP"]["eta_th"]
                              + model.cap["BOI"]
                              + model.cap["GHP"]
                              + model.cap["BCHP"] / devs["BCHP"]["eta_el"] * devs["BCHP"]["eta_th"]
                              + model.cap["BBOI"]
                              + model.cap["WCHP"] / devs["WCHP"]["eta_el"] * devs["WCHP"]["eta_th"]
                              + model.cap["WBOI"]
                              + model.cap["FC"] / devs["FC"]["eta_el"] * devs["FC"]["eta_th"]
                              >= param["peak_heat"])

        # Cooling
        model.constraints.add(model.cap["CC"] + model.cap["AC"] >= param["peak_cool"])

        # Power (with renewable sources)
        model.constraints.add(
            model.cap["PV"] + model.cap["WT"] + model.cap["WAT"] + model.cap["CHP"] + model.cap["BCHP"] + model.cap[
                "WCHP"] + model.cap["FC"] + model.grid_limit_el >= param["peak_power"])

        # Hydrogen
        if (param["enable_supply_hydrogen"] == False) and devs["ELYZ"]["feasible"]:
            model.constraints.add(model.cap["ELYZ"] >= param["peak_hydrogen"])

    ################################################################################
    # Storage devices
    ################################################################################

    for dev in model.storage_devs:
        for day_y in model.year:
            for t in range(1, len(model.time_steps)):
                # Energy balance for storage devices: soc(t) = soc(t-1) * (1 - sto_loss)^dt + charge * dt
                soc_prev = model.soc[dev, day_y, t - 1]
                model.constraints.add(
                    model.soc[dev, day_y, t] == soc_prev * (1 - devs[dev]["sto_loss"]) ** dt + model.ch[
                        dev, model.sigma[day_y], t] * dt)
            if day_y > 0:
                # For the first time step of each day, the state of charge is based on the previous day's last time step
                # Equation: soc(t=0) = soc(t=last) * (1 - sto_loss)^dt + charge * dt
                soc_prev_day = model.soc[dev, day_y - 1, len(model.time_steps) - 1]
                model.constraints.add(
                    model.soc[dev, day_y, 0] == soc_prev_day * (1 - devs[dev]["sto_loss"]) ** dt + model.ch[
                        dev, model.sigma[day_y], 0] * dt)

        # For the last time step of the last day, the state of charge is based on the first time step of the first day
        soc_last = model.soc[dev, 51, cluster_horizon - 1]
        model.constraints.add(model.soc[dev, 0, 0] == soc_last * (1 - devs[dev]["sto_loss"]) ** dt + model.ch[
            dev, model.sigma[0], 0] * dt)

    ################################################################################
    # Grid limits
    ################################################################################

    model.constraints.add(model.from_gas_grid_total == dt * sum(
        model.gas["from_grid", d, t] * param["cluster_weights"][d] for d in model.clusters for t in model.time_steps))
    model.constraints.add(model.to_gas_grid_total == dt * sum(
        model.gas["to_grid", d, t] * param["cluster_weights"][d] for d in model.clusters for t in model.time_steps))
    model.constraints.add(model.from_el_grid_total == dt * sum(
        model.power["from_grid", d, t] * param["cluster_weights"][d] for d in model.clusters for t in model.time_steps))
    model.constraints.add(model.to_el_grid_total == dt * sum(
        model.power["to_grid", d, t] * param["cluster_weights"][d] for d in model.clusters for t in model.time_steps))
    model.constraints.add(model.biom_import_total == dt * sum(
        model.biom["import", d, t] * param["cluster_weights"][d] for d in model.clusters for t in model.time_steps))
    model.constraints.add(model.waste_import_total == dt * sum(
        model.waste["import", d, t] * param["cluster_weights"][d] for d in model.clusters for t in model.time_steps))
    model.constraints.add(model.hydrogen_import_total == dt * sum(
        model.hydrogen["import", d, t] * param["cluster_weights"][d] for d in model.clusters for t in model.time_steps))

    ################################################################################
    # Supply limitations (User input)
    ################################################################################

    # Forbid/allow feed-in
    if not param.get("enable_feed_in_el", True): model.constraints.add(model.to_el_grid_total == 0)
    if not param.get("enable_feed_in_gas", True): model.constraints.add(model.to_gas_grid_total == 0)

    if param["enable_supply_el"] != True:
        model.constraints.add(model.from_el_grid_total == 0)
    if param["enable_cap_limit_el"] == True:
        model.constraints.add(model.grid_limit_el <= param["cap_limit_el"])
    if param["enable_supply_limit_el"] == True:
        model.constraints.add(model.from_el_grid_total <= param["supply_limit_el"])

    # Limitation of gas supply
    if param["enable_supply_gas"] != True:
        model.constraints.add(model.from_gas_grid_total == 0)
    if param["enable_cap_limit_gas"] == True:
        model.constraints.add(model.grid_limit_gas <= param["cap_limit_gas"])
    if param["enable_supply_limit_gas"] == True:
        model.constraints.add(model.from_gas_grid_total <= param["supply_limit_gas"])

    # Limitation of biomass supply
    if param["enable_supply_biomass"] != True:
        model.constraints.add(model.biom_import_total == 0)
    if param["enable_supply_limit_biomass"] == True:
        model.constraints.add(model.biom_import_total <= param["supply_limit_biomass"])

    # Limitation of waste supply
    if param["enable_supply_waste"] != True:
        model.constraints.add(model.waste_import_total == 0)
    if param["enable_supply_limit_waste"] == True:
        model.constraints.add(model.waste_import_total <= param["supply_limit_waste"])

    # Limitation of hydrogen supply
    if param["enable_supply_hydrogen"] != True:
        model.constraints.add(model.hydrogen_import_total == 0)
    if param["enable_supply_limit_hydrogen"] == True:
        model.constraints.add(model.hydrogen_import_total <= param["supply_limit_hydrogen"])

    ################################################################################
    # Economic constraints
    ################################################################################

    # Electricity costs and revenues
    model.constraints.add(model.supply_costs_el == model.from_el_grid_total * param["price_supply_el_eh"])
    # Conditional capacity costs for electricity
    if param["enable_price_cap_el"]:
        model.constraints.add(model.cap_costs_el == model.grid_limit_el * param["price_cap_el"])
    else:
        model.constraints.add(model.cap_costs_el == 0)
    model.constraints.add(model.rev_feed_in_el == model.to_el_grid_total * param["revenue_feed_in_el_eh"])

    # Gas costs and revenues
    model.constraints.add(model.supply_costs_gas == model.from_gas_grid_total * param["price_supply_gas_eh"])
    model.constraints.add(model.cap_costs_gas == model.grid_limit_gas * param["price_cap_gas"])
    model.constraints.add(model.rev_feed_in_gas == model.to_gas_grid_total * param["revenue_feed_in_gas"])

    # Biomass, waste, and hydrogen costs
    model.constraints.add(model.supply_costs_biom == model.biom_import_total * param["price_biomass"])
    model.constraints.add(model.supply_costs_waste == model.waste_import_total * param["price_waste"])
    model.constraints.add(model.supply_costs_hydrogen == model.hydrogen_import_total * param["price_hydrogen"])

    # Investment and operational costs for each device
    for dev in model.all_devs:
        model.constraints.add(model.inv[dev] == devs[dev]["inv_var"] * model.cap[dev])  # investment costs
        model.constraints.add(model.c_inv[dev] == model.inv[dev] * devs[dev]["ann_factor"])  # annual investment costs
        model.constraints.add(
            model.c_om[dev] == devs[dev]["cost_om"] * model.inv[dev])  # operation and maintenance costs
        model.constraints.add(model.c_total[dev] == model.c_inv[dev] + model.c_om[dev])  # total annual costs

    # CO2 tax term for emissions from gas, biomass, waste
    co2_tax_term = (model.from_gas_grid_total * param["co2_gas"] + model.biom_import_total * param[
        "co2_biom"] + model.waste_import_total * param["co2_waste"]) * param["co2_tax"]

    # Heat grid costs
    heat_grid_costs = data.heat_grid_data["ann_costs"] + data.heat_grid_data["om_costs"]

    ################################################################################
    # Define Objective Function
    ################################################################################

    def objective_rule(model):
        return (1 - param["optim_focus"]) * model.obj_tac + param["optim_focus"] * model.obj_co2

    model.objective = pyo.Objective(rule=objective_rule, sense=pyo.minimize)

    # Total annual costs
    model.constraints.add(model.obj_tac == sum(model.c_total[dev] for dev in model.all_devs)
                          + heat_grid_costs
                          + model.supply_costs_gas + model.cap_costs_gas
                          + model.supply_costs_el + model.cap_costs_el
                          - model.rev_feed_in_el - model.rev_feed_in_gas
                          + model.supply_costs_biom + model.supply_costs_waste + model.supply_costs_hydrogen
                          + co2_tax_term)

    # CO2 emissions calculation
    model.constraints.add(model.obj_co2 == model.from_el_grid_total * param["co2_el_grid"]
                          + model.from_gas_grid_total * param["co2_gas"]
                          + model.biom_import_total * param["co2_biom"]
                          + model.waste_import_total * param["co2_waste"]
                          + model.hydrogen_import_total * param["co2_hydrogen"]
                          - model.to_el_grid_total * param["co2_el_feed_in"]
                          - model.to_gas_grid_total * param["co2_gas_feed_in"])

    return model


def solve_model_and_extract_results(data, model, devs, param, result_dict):
    """
    Function to capsle solving the Pyomo model and extracting results.
    """
    # Folder to save model and results
    result_dir = "results"
    if not os.path.exists(result_dir):
        os.makedirs(result_dir)

    lp_filename = os.path.join(result_dir, "ehdo_model.lp")
    model.write(lp_filename, io_options={"symbolic_solver_labels": True})

    # temporary log-file for the solver
    solver_log_path = os.path.join(result_dir, "solver_output_ehdo.log")
    # Path for error file
    errorfile_path = os.path.join(result_dir, 'errorfile_ehdo.txt')

    ################################################################################
    # Solve the Model
    ################################################################################

    solver, solver_options = solver_config.create_solver()
    solve_start_time = time.time()
    results = solver.solve(model, tee=False, options=solver_options)
    print(f"Optimization done. ({(time.time() - solve_start_time):.2f} seconds.)")

    ################################################################################
    # Check and Save Results
    ################################################################################

    # Check if solution is optimal, otherwise write an error file to help find errors
    if results.solver.termination_condition == pyo.TerminationCondition.infeasible:
        print(f"Model is infeasible for further analysis see {errorfile_path}")
        n_vars = sum(1 for _ in model.component_data_objects(pyo.Var, active=True))
        n_cons = sum(1 for _ in model.component_data_objects(pyo.Constraint, active=True))
        with open(errorfile_path, 'w') as f:
            f.write('Error: Model is infeasible\n')
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"Model Statistics:\n")
            f.write(f"  - Variables: {n_vars}\n")
            f.write(f"  - Constraints: {n_cons}\n\n")
            f.write(f"  - LP File: {lp_filename}\n\n")
            try:
                with open(solver_log_path, 'r', encoding='utf-8') as log_file:
                    f.write("\nSolver Log:\n")
                    f.write("-" * 40 + "\n")
                    f.write(log_file.read())
                    f.write("-" * 40 + "\n")
                # Remove temporary solver log file
                os.remove(solver_log_path)
            except Exception as e:
                f.write(f"\nCould not read solver log: {e}\n")

        # IIS-Analysis
        try:
            import logging
            # Create string buffer to capture logging
            logging_buffer = StringIO()

            # Store original logging handlers
            root_logger = logging.getLogger()
            original_handlers = root_logger.handlers[:]
            original_level = root_logger.level

            # Clear existing handlers temporarily
            for handler in original_handlers:
                root_logger.removeHandler(handler)

            # Add string handler to capture only IIS output
            string_handler = logging.StreamHandler(logging_buffer)
            string_handler.setLevel(logging.INFO)
            root_logger.addHandler(string_handler)
            root_logger.setLevel(logging.INFO)

            # Run IIS analysis - output goes to buffer
            log_infeasible_constraints(model, log_expression=True, log_variables=True)

            # Get captured content
            iis_content = logging_buffer.getvalue()

            # Restore logging
            root_logger.removeHandler(string_handler)
            for handler in original_handlers:
                root_logger.addHandler(handler)
            root_logger.setLevel(original_level)

            # Write to error file
            with open(errorfile_path, 'a', encoding='utf-8') as f:
                f.write("INFEASIBLE CONSTRAINTS:\n")
                f.write("-" * 40 + "\n")
                if iis_content.strip():
                    f.write(iis_content)
                else:
                    f.write("No IIS details captured\n")
                f.write("-" * 40 + "\n")

            print(f"Infeasibility analysis saved to {errorfile_path}")

        except Exception as e:
            # Ensure logging is restored
            try:
                if 'original_handlers' in locals():
                    root_logger.removeHandler(string_handler)
                    for handler in original_handlers:
                        if handler not in root_logger.handlers:
                            root_logger.addHandler(handler)
                    root_logger.setLevel(original_level)
            except:
                pass

            print(f"IIS analysis failed: {e}")

            with open(errorfile_path, 'a') as f:
                f.write(f"IIS analysis failed: {e}\n")

        return None

    elif results.solver.termination_condition == pyo.TerminationCondition.unbounded:
        print("Model is unbounded")
        with open(errorfile_path, 'w') as f:
            f.write('Model is unbounded\n')
        return None
    elif results.solver.termination_condition == pyo.TerminationCondition.optimal:
        print("Model solved to optimality")
    else:
        print(f"Solver status: {results.solver.termination_condition}")
        with open(errorfile_path, 'w') as f:
            f.write(f'Solver status: {results.solver.termination_condition}\n')
        return None

    # Remove temporary solver log file
    if os.path.exists(solver_log_path):
        os.remove(solver_log_path)

    # Save all variable values in a solution file:
    def write_solution_file(model, filename):
        """
        Write solution values to a file in a format similar to Gurobi's .sol files
        """
        try:
            with open(filename, 'w') as f:
                f.write("# Solution file\n")
                f.write(f"# Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"# Objective value: {pyo.value(model.objective)}\n")
                f.write("# Variable values\n")

                # Write all variable values
                for var in model.component_objects(pyo.Var, active=True):
                    if var.is_indexed():
                        for index in var:
                            if var[index].value is not None:
                                f.write(f"{var.name}[{index}] {var[index].value:.6f}\n")
                    else:
                        if var.value is not None:
                            f.write(f"{var.name} {var.value:.6f}\n")

                f.write("# End of solution\n")
            print(f"Solution written to {filename}")

        except Exception as e:
            print(f"Warning: Could not write solution file {filename}: {e}")
        return None

    solution_path = os.path.join(result_dir, 'solution_ehdo_file.txt')
    write_solution_file(model, solution_path)

    ################################################################################
    # Post-processing and Result Extraction
    ################################################################################

    # --- Robust helper functions for safe value queries ---
    def safe_value(var_container, index):  # Safe value retrieval for indexed variables
        try:
            val = pyo.value(var_container[index])
            return val if val is not None else 0
        except (KeyError, ValueError):
            return 0

    def safe_value_single(var):  # Safe value retrieval for single variables
        try:
            val = pyo.value(var)
            return val if val is not None else 0
        except ValueError:
            return 0

    # --- Complete and original filling of the result_dict ---
    result_dict["devs"] = devs
    result_dict["tac"] = int(safe_value_single(model.obj_tac))  # EUR/a
    result_dict["co2"] = int(safe_value_single(model.obj_co2) / 1000)  # t/a

    for k in model.all_devs:
        result_dict[k] = {"cap": round(safe_value(model.cap, k), 1)}

    # Add 'from_grid' and 'to_grid' capacity information if the option is enabled
    if param.get("enable_cap_limit_el", True):
        result_dict["from_grid"] = {"cap": param["cap_limit_el"]}
        result_dict["to_grid"] = {"cap": param["cap_limit_el"]}
    else:
        result_dict["from_grid"] = {"cap": float("inf")}
        result_dict["to_grid"] = {"cap": float("inf")}

    # Investment and operational costs
    heat_grid_costs = data.heat_grid_data.get("costs", 0)
    heat_grid_ann_costs = data.heat_grid_data.get("ann_costs", 0)
    heat_grid_om_costs = data.heat_grid_data.get("om_costs", 0)

    result_dict["total_inv_cost"] = int(sum(safe_value(model.inv, k) for k in model.all_devs) + heat_grid_costs)
    result_dict["total_ann_inv_cost"] = int(
        sum(safe_value(model.c_inv, k) for k in model.all_devs) + heat_grid_ann_costs)
    result_dict["total_om_cost"] = int(sum(safe_value(model.c_om, k) for k in model.all_devs) + heat_grid_om_costs)

    # Total energy imports and exports
    result_dict["from_el_grid_total"] = int(safe_value_single(model.from_el_grid_total) / 1000)  # MWh
    result_dict["to_el_grid_total"] = int(safe_value_single(model.to_el_grid_total) / 1000)  # MWh
    result_dict["from_gas_grid_total"] = int(safe_value_single(model.from_gas_grid_total) / 1000)  # MWh
    result_dict["to_gas_grid_total"] = int(safe_value_single(model.to_gas_grid_total) / 1000)  # MWh
    result_dict["biom_import_total"] = int(safe_value_single(model.biom_import_total) / 1000)  # MWh
    result_dict["waste_import_total"] = int(safe_value_single(model.waste_import_total) / 1000)  # MWh
    result_dict["hydrogen_import_total"] = int(safe_value_single(model.hydrogen_import_total) / 1000)  # MWh

    # CO2 emissions breakdown
    result_dict["co2_onsite_emissions"] = int((safe_value_single(model.from_gas_grid_total) * param["co2_gas"] +
                                               safe_value_single(model.biom_import_total) * param["co2_biom"] +
                                               safe_value_single(model.waste_import_total) * param["co2_waste"]) / 1000)
    result_dict["co2_global_emissions"] = int(result_dict["co2"] / 1000)
    result_dict["co2_credit_feedin"] = int((safe_value_single(model.to_el_grid_total) * param["co2_el_feed_in"] +
                                            safe_value_single(model.to_gas_grid_total) * param[
                                                "co2_gas_feed_in"]) / 1000)
    result_dict["co2_tax_total"] = int(result_dict["co2_onsite_emissions"] * param["co2_tax"] * 1000)  # EUR

    # Maximum grid flows (electricity and gas)
    for grid_type in ["from_grid", "to_grid"]:
        max_el = max(safe_value(model.power, (grid_type, d, t)) for d in model.clusters for t in model.time_steps)
        result_dict[f"max_el_{grid_type}"] = int(max_el)

        max_gas = max(safe_value(model.gas, (grid_type, d, t)) for d in model.clusters for t in model.time_steps)
        result_dict[f"max_gas_{grid_type}"] = int(max_gas)

    # Maximum import flows for other resources
    result_dict["max_biom"] = int(
        max(safe_value(model.biom, ("import", d, t)) for d in model.clusters for t in model.time_steps))
    result_dict["max_waste"] = int(
        max(safe_value(model.waste, ("import", d, t)) for d in model.clusters for t in model.time_steps))
    result_dict["max_hydrogen"] = int(
        max(safe_value(model.hydrogen, ("import", d, t)) for d in model.clusters for t in model.time_steps))

    # Energy costs and revenues
    result_dict["supply_costs_el"] = int(safe_value_single(model.supply_costs_el))
    result_dict["cap_costs_el"] = int(safe_value_single(model.cap_costs_el))
    result_dict["total_el_costs"] = result_dict["supply_costs_el"] + result_dict["cap_costs_el"]
    result_dict["rev_feed_in_el"] = int(safe_value_single(model.rev_feed_in_el))

    result_dict["supply_costs_gas"] = int(safe_value_single(model.supply_costs_gas))
    result_dict["cap_costs_gas"] = int(safe_value_single(model.cap_costs_gas))
    result_dict["total_gas_costs"] = result_dict["supply_costs_gas"] + result_dict["cap_costs_gas"]
    result_dict["rev_feed_in_gas"] = int(safe_value_single(model.rev_feed_in_gas))

    result_dict["supply_costs_biom"] = int(safe_value_single(model.supply_costs_biom))
    result_dict["supply_costs_waste"] = int(safe_value_single(model.supply_costs_waste))
    result_dict["supply_costs_hydrogen"] = int(safe_value_single(model.supply_costs_hydrogen))

    # Renewable generation potential (without curtailment)
    result_dict["PV_generation_uncl"] = [x / 1000 * safe_value(model.area, "PV") for x in
                                         devs["PV"]["norm_power"]]  # in kW
    result_dict["WT_generation_uncl"] = [x * safe_value(model.cap, "WT") for x in devs["WT"]["norm_power"]]  # in kW
    result_dict["STC_generation_uncl"] = [x / 1000 * safe_value(model.area, "STC") for x in
                                          devs["STC"]["norm_power"]]  # in kW

    # Calculate curtailment for renewable sources
    dt = data.time["timeResolution"] / data.time["dataResolution"]

    # PV curtailment
    pv_curtailed = 0
    for d in model.clusters:
        for t in model.time_steps:
            potential = devs["PV"]["norm_power_clustered"][d][t] / 1000 * safe_value(model.area, "PV")
            actual = safe_value(model.power, ("PV", d, t))
            pv_curtailed += (potential - actual) * param["cluster_weights"][d]
    result_dict["PV"]["curtailed"] = int(dt * pv_curtailed)

    # STC curtailment
    stc_curtailed = 0
    for d in model.clusters:
        for t in model.time_steps:
            potential = devs["STC"]["norm_power_clustered"][d][t] / 1000 * safe_value(model.area, "STC")
            actual = safe_value(model.heat, ("STC", d, t))
            stc_curtailed += (potential - actual) * param["cluster_weights"][d]
    result_dict["STC"]["curtailed"] = int(dt * stc_curtailed)

    # WT curtailment
    wt_curtailed = 0
    for d in model.clusters:
        for t in model.time_steps:
            potential = devs["WT"]["norm_power_clustered"][d][t] * safe_value(model.cap, "WT")
            actual = safe_value(model.power, ("WT", d, t))
            wt_curtailed += (potential - actual) * param["cluster_weights"][d]
    result_dict["WT"]["curtailed"] = int(dt * wt_curtailed)

    # WAT curtailment
    wat_curtailed = 0
    for d in model.clusters:
        for t in model.time_steps:
            potential = min(safe_value(model.cap, "WAT"), devs["WAT"]["potential"])
            actual = safe_value(model.power, ("WAT", d, t))
            wat_curtailed += (potential - actual) * param["cluster_weights"][d]
    result_dict["WAT"]["curtailed"] = int(dt * wat_curtailed)

    # Power profiles and maximum power
    result_dict["power_profile"] = {}
    result_dict["power_kW"] = {}
    for device in ["PV", "WT", "WAT", "HP", "EB", "CC", "CHP", "BCHP", "WCHP", "ELYZ", "FC", "from_grid", "to_grid"]:
        profile = []
        for d in model.clusters:
            for t in model.time_steps:
                profile.append(safe_value(model.power, (device, d, t)))
        result_dict["power_profile"][device] = profile
        result_dict["power_kW"][device] = int(max(profile)) if profile else 0

    # Heat profiles and maximum heat
    result_dict["heat_profile"] = {}
    result_dict["heat_kW"] = {}
    for device in ["STC", "HP", "EB", "AC", "CHP", "BOI", "GHP", "BCHP", "BBOI", "WCHP", "WBOI", "FC"]:
        profile = []
        for d in model.clusters:
            for t in model.time_steps:
                profile.append(safe_value(model.heat, (device, d, t)))
        result_dict["heat_profile"][device] = profile
        result_dict["heat_kW"][device] = int(max(profile)) if profile else 0

    # Cooling profiles and maximum cooling
    result_dict["cool_profile"] = {}
    result_dict["cool_kW"] = {}
    for device in ["CC", "AC"]:
        profile = []
        for d in model.clusters:
            for t in model.time_steps:
                profile.append(safe_value(model.cool, (device, d, t)))
        result_dict["cool_profile"][device] = profile
        result_dict["cool_kW"][device] = int(max(profile)) if profile else 0

    # Area usage
    result_dict["area"] = {}
    for device in ["PV", "STC"]:
        result_dict["area"][device] = int(safe_value(model.area, device))

    # Calculate annual generation for each device type
    eps = 0.01

    # Heat generation
    for k in ["STC", "HP", "EB", "BOI", "GHP", "BBOI", "WBOI"]:
        gen_kwh = dt * sum(safe_value(model.heat, (k, d, t)) * param["cluster_weights"][d]
                           for d in model.clusters for t in model.time_steps)
        result_dict[k]["gen_kWh"] = gen_kwh
        result_dict[k]["gen"] = int(gen_kwh / 1000)  # MWh

    # Cooling generation
    for k in ["CC", "AC"]:
        gen_kwh = dt * sum(safe_value(model.cool, (k, d, t)) * param["cluster_weights"][d]
                           for d in model.clusters for t in model.time_steps)
        result_dict[k]["gen_kWh"] = gen_kwh
        result_dict[k]["gen"] = int(gen_kwh / 1000)  # MWh

    # Power generation
    for k in ["PV", "WT", "WAT", "CHP", "BCHP", "WCHP", "ELYZ", "FC"]:
        gen_kwh = dt * sum(safe_value(model.power, (k, d, t)) * param["cluster_weights"][d]
                           for d in model.clusters for t in model.time_steps)
        result_dict[k]["gen_kWh"] = gen_kwh
        result_dict[k]["gen"] = int(gen_kwh / 1000)  # MWh

    # Special: Hydrogen generation for ELYZ
    h2_gen = dt * sum(safe_value(model.power, ("ELYZ", d, t)) * devs["ELYZ"]["eta_el"] * param["cluster_weights"][d]
                      for d in model.clusters for t in model.time_steps)
    result_dict["ELYZ"]["gen_H2"] = int(h2_gen / 1000)  # MWh

    # Gas generation for SAB
    for k in ["SAB"]:
        gen_kwh = dt * sum(safe_value(model.gas, (k, d, t)) * param["cluster_weights"][d]
                           for d in model.clusters for t in model.time_steps)
        result_dict[k]["gen_kWh"] = gen_kwh
        result_dict[k]["gen"] = int(gen_kwh / 1000)  # MWh

    # Calculate full load hours
    for k in ["PV", "WT", "WAT", "STC", "HP", "EB", "CC", "AC", "CHP", "BOI", "GHP", "BCHP", "BBOI", "WCHP", "WBOI",
              "ELYZ", "FC", "SAB"]:
        cap_k = safe_value(model.cap, k)
        if cap_k > eps:
            result_dict[k]["hrs"] = int(result_dict[k]["gen_kWh"] / cap_k)
        else:
            result_dict[k]["hrs"] = 0

    # Select technologies that are installed
    for k in model.all_devs:
        result_dict[k]["inst"] = safe_value(model.cap, k) > eps

    # Calculate charge cycles of storages
    for k in ["TES", "CTES", "BAT", "H2S", "GS"]:
        cap_k = safe_value(model.cap, k)
        if cap_k > eps:
            charge_cycles = dt * sum(abs(safe_value(model.ch, (k, d, t))) / 2 * param["cluster_weights"][d]
                                     for d in model.clusters for t in model.time_steps)
            result_dict[k]["chc"] = int(charge_cycles / cap_k)
        else:
            result_dict[k]["chc"] = 0

    # Calculate volume of thermal storages
    for k in ["TES", "CTES"]:
        cap_k = safe_value(model.cap, k)
        if cap_k > eps:
            result_dict[k]["vol_liter"] = round(
                cap_k / (param["c_w"] * param["rho_w"] * devs[k]["delta_T"]) * 3600 * 1000, 1)
        else:
            result_dict[k]["vol_liter"] = 0

        # Storage state of charge and charging power
    for dev in model.storage_devs:
        # Maximum SOC
        max_soc = max(safe_value(model.soc, (dev, day_y, t)) for day_y in model.year for t in model.time_steps)
        result_dict[dev]["soc"] = int(max_soc)

        # Maximum charging power
        max_ch = max(safe_value(model.ch, (dev, d, t)) for d in model.clusters for t in model.time_steps)
        result_dict[dev]["ch"] = int(max_ch)

    # Calculate detailed CO2 emissions by source
    result_dict["total_co2_el"] = int(safe_value_single(model.from_el_grid_total) * param["co2_el_grid"] / 1000)  # t/a
    result_dict["total_co2_el_feed_in"] = int(
        safe_value_single(model.to_el_grid_total) * param["co2_el_feed_in"] / 1000)  # t/a
    result_dict["total_co2_gas"] = int(safe_value_single(model.from_gas_grid_total) * param["co2_gas"] / 1000)  # t/a
    result_dict["total_co2_gas_feed_in"] = int(
        safe_value_single(model.to_gas_grid_total) * param["co2_gas_feed_in"] / 1000)  # t/a
    result_dict["total_co2_biom"] = int(safe_value_single(model.biom_import_total) * param["co2_biom"] / 1000)  # t/a
    result_dict["total_co2_waste"] = int(safe_value_single(model.waste_import_total) * param["co2_waste"] / 1000)  # t/a
    result_dict["total_co2_hydrogen"] = int(
        safe_value_single(model.hydrogen_import_total) * param["co2_hydrogen"] / 1000)  # t/a

    # draw stacked plot of system costs
    # Extract non-zero ann/o&m costs of devices
    plot_data = []  # list of (label, value)

    for dev in model.all_devs:
        ann = safe_value(model.c_inv, dev)
        om = safe_value(model.c_om, dev)

        if ann == 0 and om == 0:
            continue  # skip unused devices

        # append ann then o&m costs
        plot_data.append((f"Annualized investment for the {dev}", ann))
        plot_data.append((f"Operation and maintenance cost for the {dev}", om))

    # Add heat grid
    plot_data.append(("Annualized investment for Heat Grid", heat_grid_ann_costs))
    plot_data.append(("Operation and maintenance cost for Heat Grid", heat_grid_om_costs))

    # --- Prepare stacked values ---
    labels = [item[0] for item in plot_data]
    values = [item[1] for item in plot_data]

    cmap = plt.get_cmap("tab20")  # 20 distinct colors
    colors = [cmap(i) for i in range(len(labels))]

    fig, ax = plt.subplots(figsize=(10, 14))

    x = [0]  # only ONE bar
    bottom = 0

    # plot each pair layer
    for label, val, col in zip(labels, values, colors):
        ax.bar(x, val, bottom=bottom, color=col, label=label, width=0.6)
        bottom += val

    # Automatic line wrapping
    wrapped_labels = ['\n'.join(textwrap.wrap(lbl, 20)) for lbl in labels]

    # X-axis cleanup
    ax.set_ylabel("Annual Costs [EUR/a]")
    ax.set_title("Annual Cost Stacked Chart")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{data.scenario_name}"])
    ax.legend(
        wrapped_labels,
        bbox_to_anchor=(1.05, 1),
        loc="upper left",
        labelspacing=0.7,  # control vertical spacing
        handletextpad=0.5,
        borderpad=0.6
    )

    plt.tight_layout()

    plot_filename = f"system_cost_stack_{data.scenario_name}.png"
    plot_path = os.path.join(data.resultPath, plot_filename)
    plt.savefig(plot_path)

    plt.show()

    return result_dict
