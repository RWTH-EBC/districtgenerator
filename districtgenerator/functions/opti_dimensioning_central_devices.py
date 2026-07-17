# -*- coding: utf-8 -*-
"""
EHDO - ENERGY HUB DESIGN OPTIMIZATION Tool
Pyomo Version

This script is a Pyomo-based translation of the original Gurobi model.
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
from contextlib import redirect_stdout

EH_HEAT_PRODUCERS = ("STC", "HP", "GroundHP", "EB", "CHP", "BOI", "GHP", "BCHP", "BBOI", "WCHP", "WBOI", "FC")
EH_RENEWABLE_HEAT = ("STC", "HP", "GroundHP", "EB", "BCHP", "BBOI", "WCHP", "WBOI", "FC")


def _get_renewable_heat_share_schedule(config):
    target_years = config.get("renewable_heat_share_years")
    target_shares = config.get("renewable_heat_share_targets")

    if target_years or target_shares:
        if len(target_years) != len(target_shares):
            raise ValueError("renewable_heat_share_years and renewable_heat_share_targets must have the same length.")
        schedule = [(int(target_year), float(target_share))
                    for target_year, target_share in zip(target_years, target_shares)]
    else:
        return []

    return sorted(schedule, key=lambda item: item[0])


def _get_active_renewable_heat_share(config, year):
    if not config.get("renewable_heat_share_enabled"):
        return 0.0

    active_target = 0.0

    for target_year, target_share in _get_renewable_heat_share_schedule(config):
        if year >= target_year:
            active_target = max(active_target, target_share)

    return active_target

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
    print("Starting Energy Hub Design Optimization...")
    # build the model
    model = pyo.ConcreteModel(name="Energy_Hub_Design_Optimization")
    build_model(model=model, data=data, devs=devs, param=param, dem=dem)
    model_building_time = time.time() - start_time
    print(f"Pyomo model built successfully in {model_building_time:.2f} seconds.")
    # solve the model and extract results
    result_dict = solve_model_and_extract_results(data=data, model=model, devs=devs, param=param,
                                                  result_dict=result_dict)
    model_solve_time = time.time() - start_time - model_building_time
    if result_dict is not None:
        print(f"Model solved to optimality in {model_solve_time:.2f} seconds.")
    # calculate total time
    total_time = time.time() - start_time

    return result_dict

def build_model(model, data, devs, param, dem):

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

    # Get sigma function that assigns each time period (day or week) to a design period
    model.sigma = pyo.Param(model.year, initialize=param["sigma"])

    # Support years for multi-year optimization
    support_years = sorted(param["interpolation_points"])  # For example [0, 5, 10, 15, 20]
    model.support_years = pyo.Set(initialize=support_years)

    # Store observation time
    model.observation_time = pyo.Param(initialize=param["observation_time"])

    # Create sets for all device types
    all_devs_list = ["PV", "WT", "STC", "WAT", "HP", "GroundHP", "EB", "CC", "AC", "CHP", "BOI", "GHP",
                     "BCHP", "BBOI", "WCHP", "WBOI", "ELYZ", "FC", "H2S", "SAB", "TES",
                     "CTES", "BAT", "GS"]

    gas_devs_list = ["CHP", "BOI", "GHP", "SAB", "from_grid", "to_grid"]
    power_devs_list = ["PV", "WT", "WAT", "HP", "GroundHP", "EB", "CC", "CHP", "BCHP", "WCHP", "ELYZ", "FC", "from_grid", "to_grid"]
    heat_devs_list = ["STC", "HP", "GroundHP", "EB", "AC", "CHP", "BOI", "GHP", "BCHP", "BBOI", "WCHP", "WBOI", "FC"]
    cool_devs_list = ["CC", "AC"]
    hydrogen_devs_list = ["ELYZ", "FC", "SAB", "import"]
    biom_devs_list = ["BCHP", "BBOI", "import"]
    biomethane_devs_list = ["CHP", "BOI", "GHP", "import"]
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
    model.biomethane_devs = pyo.Set(initialize=biomethane_devs_list)
    model.waste_devs = pyo.Set(initialize=waste_devs_list)
    model.storage_devs = pyo.Set(initialize=storage_devs_list)
    model.area_devs = pyo.Set(initialize=area_devs_list)

    # %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    # 2. Create Pyomo Variables
    # %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

    # Capacity variables (same for all years - single investment decision)
    model.cap = pyo.Var(model.all_devs, within=pyo.NonNegativeReals, name="nominal_capacity")
    model.area = pyo.Var(model.area_devs, within=pyo.NonNegativeReals, name="roof_area")

    # Operational variables for EACH SUPPORT YEAR
    model.gas = pyo.Var(model.gas_devs, model.support_years, model.clusters, model.time_steps, within=pyo.NonNegativeReals)
    model.power = pyo.Var(model.power_devs, model.support_years, model.clusters, model.time_steps, within=pyo.NonNegativeReals)
    model.heat = pyo.Var(model.heat_devs, model.support_years, model.clusters, model.time_steps, within=pyo.NonNegativeReals)
    model.cool = pyo.Var(model.cool_devs, model.support_years, model.clusters, model.time_steps, within=pyo.NonNegativeReals)
    model.hydrogen = pyo.Var(model.hydrogen_devs, model.support_years, model.clusters, model.time_steps, within=pyo.NonNegativeReals)
    model.biom = pyo.Var(model.biom_devs, model.support_years, model.clusters, model.time_steps, within=pyo.NonNegativeReals)
    model.biomethane = pyo.Var(model.biomethane_devs, model.support_years, model.clusters, model.time_steps, within=pyo.NonNegativeReals)
    model.waste = pyo.Var(model.waste_devs, model.support_years, model.clusters, model.time_steps, within=pyo.NonNegativeReals)
    model.ch = pyo.Var(model.storage_devs, model.support_years, model.clusters, model.time_steps, within=pyo.Reals)

    # Storage SOC uses weekly tracking but indexed by support year
    model.soc = pyo.Var(model.storage_devs, model.support_years, model.year, model.time_steps,
                        within=pyo.NonNegativeReals)

    # Investment costs (same for all years)
    model.inv = pyo.Var(model.all_devs, within=pyo.NonNegativeReals)    # subsidized investment costs payed by the investor
    model.inv_base = pyo.Var(model.all_devs, within=pyo.NonNegativeReals)  # unsubsidized investment costs
    model.c_inv = pyo.Var(model.all_devs, within=pyo.NonNegativeReals)
    model.c_inv_base = pyo.Var(model.all_devs, within=pyo.NonNegativeReals)  # unsubsidized annualized investment costs
    model.c_om = pyo.Var(model.all_devs, within=pyo.NonNegativeReals)
    model.c_total = pyo.Var(model.all_devs, within=pyo.NonNegativeReals)

    # Grid limits (same for all years - infrastructure decision)
    model.grid_limit_el = pyo.Var(within=pyo.NonNegativeReals)
    model.grid_limit_gas = pyo.Var(within=pyo.NonNegativeReals)

    # Yearly totals - indexed by support year
    model.from_el_grid_total = pyo.Var(model.support_years, within=pyo.NonNegativeReals)
    model.to_el_grid_total = pyo.Var(model.support_years, within=pyo.NonNegativeReals)
    model.from_gas_grid_total = pyo.Var(model.support_years, within=pyo.NonNegativeReals)
    model.to_gas_grid_total = pyo.Var(model.support_years, within=pyo.NonNegativeReals)
    model.biom_import_total = pyo.Var(model.support_years, within=pyo.NonNegativeReals)
    model.biomethane_import_total = pyo.Var(model.support_years, within=pyo.NonNegativeReals)
    model.waste_import_total = pyo.Var(model.support_years, within=pyo.NonNegativeReals)
    model.hydrogen_import_total = pyo.Var(model.support_years, within=pyo.NonNegativeReals)

    # Revenues and costs per support year
    model.rev_feed_in_gas = pyo.Var(model.support_years, within=pyo.NonNegativeReals)
    model.rev_feed_in_el = pyo.Var(model.support_years, within=pyo.NonNegativeReals)
    model.supply_costs_el = pyo.Var(model.support_years, within=pyo.NonNegativeReals)
    model.cap_costs_el = pyo.Var(within=pyo.NonNegativeReals)  # Same for all years
    model.supply_costs_gas = pyo.Var(model.support_years, within=pyo.NonNegativeReals)
    model.cap_costs_gas = pyo.Var(within=pyo.NonNegativeReals)  # Same for all years
    model.supply_costs_biom = pyo.Var(model.support_years, within=pyo.NonNegativeReals)
    model.supply_costs_biomethane = pyo.Var(model.support_years, within=pyo.NonNegativeReals)
    model.supply_costs_waste = pyo.Var(model.support_years, within=pyo.Reals)
    model.supply_costs_hydrogen = pyo.Var(model.support_years, within=pyo.NonNegativeReals)

    model.total_annual_costs_devices = pyo.Var(within=pyo.NonNegativeReals)                 # Total annual costs for devices (inv and om)
    model.heat_grid_costs = pyo.Var(within=pyo.NonNegativeReals)                            # Total annual costs for heat grid (inv and om)
    model.total_energy_costs = pyo.Var(model.support_years, within=pyo.NonNegativeReals)    # Total energy costs per year
    model.annualized_energy_costs = pyo.Var(within=pyo.NonNegativeReals)                    # Annualized energy costs
    model.misc_costs = pyo.Var(model.support_years, within=pyo.NonNegativeReals)            # e.g., CO2 costs, insurance, other taxes etc.
    model.annualized_misc_costs = pyo.Var(within=pyo.NonNegativeReals)                      # Annualized miscellaneous costs
    model.total_connection_costs = pyo.Var(within=pyo.NonNegativeReals)                     # Total annual costs for connection to grids

    # Objective variables
    model.obj_tac = pyo.Var(within=pyo.Reals)
    model.obj_co2 = pyo.Var(within=pyo.Reals)

    ################################################################################
    # Define maximum Capacity of devices Constraints
    ################################################################################
    model.constraints = pyo.ConstraintList()

    network_model = str(data.heat_grid_data.get("network_model", "2leiter")).lower()
    is_5g_fixed = network_model == "5g_fixed"
    rev_cool_cap_ratio = 1.0    #Todo: erstmal nur provisorisch hier lokal hinterlegt

    # Add capacity constraints for all devices as specified in devs
    for dev in model.all_devs:
        if is_5g_fixed and dev == "CC":
            continue
        if not devs[dev]["feasible"]:  # if device is not feasible, set capacity to 0
            model.constraints.add(model.cap[dev] == 0)
        else:
            if dev in model.area_devs:
                continue  # Area constraints are handled separately and no capacity constraints are needed
            min_cap = devs[dev].get("min_cap")
            max_cap = devs[dev].get("max_cap")
            if min_cap is not None: model.constraints.add(model.cap[dev] >= min_cap)
            if max_cap is not None: model.constraints.add(model.cap[dev] <= max_cap)

    if is_5g_fixed:
        model.constraints.add(model.cap["CC"] == rev_cool_cap_ratio * model.cap["HP"])  # CC ist nur noch der interne Kühlmodus der reversiblen HP

    # Set area constraints for devices that require area as specified in devs
    for dev in model.area_devs:
        if devs[dev]["feasible"]:
            min_area = devs[dev].get("min_area")
            max_area = devs[dev].get("max_area")
            if min_area is not None: model.constraints.add(model.area[dev] >= min_area)
            if max_area is not None: model.constraints.add(model.area[dev] <= max_area)

    # Limited operation based on installed capacity
    for y in model.support_years:
        for d in model.clusters:
            for t in model.time_steps:
                # Add constraints for the device operation based on the device capacity
                for dev in ["STC", "EB", "HP", "GroundHP", "BOI", "GHP", "BBOI", "WBOI"]:  # Heat devices
                    model.constraints.add(model.heat[dev, y, d, t] <= model.cap[dev])
                for dev in ["PV", "WT", "WAT", "CHP", "BCHP", "WCHP", "ELYZ", "FC"]:  # Power devices
                    model.constraints.add(model.power[dev, y, d, t] <= model.cap[dev])
                for dev in ["CC", "AC"]:  # Cooling devices
                    model.constraints.add(model.cool[dev, y, d, t] <= model.cap[dev])
                for dev in ["SAB"]:  # Gas devices
                    model.constraints.add(model.gas[dev, y, d, t] <= model.cap[dev])

                # Limitation of power and gas from and to the grid
                model.constraints.add(model.power["from_grid", y, d, t] <= model.grid_limit_el)
                model.constraints.add(model.power["to_grid", y, d, t] <= model.grid_limit_el)
                model.constraints.add(model.gas["from_grid", y, d, t] <= model.grid_limit_gas)
                model.constraints.add(model.gas["to_grid", y, d, t] <= model.grid_limit_gas)

                if is_5g_fixed:
                    model.constraints.add(model.heat["HP", y, d, t] + model.cool["CC", y, d, t] / rev_cool_cap_ratio <= model.cap["HP"])

    # Correlation to translate area to capacity for PV and STC
    model.constraints.add(model.cap["PV"] == model.area["PV"] * devs["PV"]["G_stc"] * devs["PV"]["eta"])
    model.constraints.add(model.cap["STC"] == model.area["STC"] * devs["STC"]["G_stc"] * devs["STC"]["eta"])

    # state of charge < storage capacity
    for y in model.support_years:
        for dev in model.storage_devs:
            for day_y in model.year:
                for t in model.time_steps:
                    model.constraints.add(model.soc[dev, y, day_y, t] <= model.cap[dev])

    #################################################################################
    # Energy Conversion Constraints (Input / Output Relations) (for every time step)
    #################################################################################

    for y in model.support_years:
        for d in model.clusters:
            for t in model.time_steps:
                # Photovoltaics power limited by clustered norm power
                model.constraints.add(
                    model.power["PV", y, d, t] <= devs["PV"]["norm_power_clustered"][d][t] / 1000 * model.area["PV"])
                # Wind turbine power limited by clustered norm power
                model.constraints.add(model.power["WT", y, d, t] <= devs["WT"]["norm_power_clustered"][d][t] * model.cap["WT"])
                # Hydropower power limited by potential
                model.constraints.add(model.power["WAT", y, d, t] <= devs["WAT"]["potential"])
                # Solar thermal collector heat limited by clustered norm power
                model.constraints.add(model.heat["STC", y, d, t] <= devs["STC"]["norm_power_clustered"][d][t] / 1000 * model.area["STC"])
                # Electric heat pump correlation between heat and electric power
                model.constraints.add(model.heat["HP", y, d, t] == model.power["HP", y, d, t] * devs["HP"]["COP"][y][d][t])
                model.constraints.add(model.heat["GroundHP", y, d, t] == model.power["GroundHP", y, d, t] * devs["GroundHP"]["COP"][y][d][t])
                # Electric boiler correlation between heat and electric power
                model.constraints.add(model.heat["EB", y, d, t] == model.power["EB", y, d, t] * devs["EB"]["eta_th"])
                # Compression chiller correlation between cooling and electric power (time-dependent COP)
                model.constraints.add(model.cool["CC", y, d, t] == model.power["CC", y, d, t] * devs["CC"]["COP"][y][d][t])
                # Absorption chiller correlation between cooling and heat power
                model.constraints.add(model.cool["AC", y, d, t] == model.heat["AC", y, d, t] * devs["AC"]["eta_th"])
                # Gas CHP correlation between production of power and heat and gas consumption
                model.constraints.add(model.power["CHP", y, d, t] == model.gas["CHP", y, d, t] * devs["CHP"]["eta_el"])
                model.constraints.add(model.heat["CHP", y, d, t] == model.gas["CHP", y, d, t] * devs["CHP"]["eta_th"])
                # Gas boiler correlation between heat and gas consumption
                model.constraints.add(model.heat["BOI", y, d, t] == model.gas["BOI", y, d, t] * devs["BOI"]["eta_th"])
                # Gas heat pump correlation between heat and gas consumption
                model.constraints.add(model.heat["GHP", y, d, t] == model.gas["GHP", y, d, t] * devs["GHP"]["COP"])
                # Biomethane can replace part or all of the gaseous fuel used by gas-based heat technologies.
                model.constraints.add(model.biomethane["CHP", y, d, t] <= model.gas["CHP", y, d, t])
                model.constraints.add(model.biomethane["BOI", y, d, t] <= model.gas["BOI", y, d, t])
                model.constraints.add(model.biomethane["GHP", y, d, t] <= model.gas["GHP", y, d, t])
                # Biomass CHP correlation between production of power and heat and biomass consumption
                model.constraints.add(model.power["BCHP", y, d, t] == model.biom["BCHP", y, d, t] * devs["BCHP"]["eta_el"])
                model.constraints.add(model.heat["BCHP", y, d, t] == model.biom["BCHP", y, d, t] * devs["BCHP"]["eta_th"])
                # Biomass boiler correlation between heat and biomass consumption
                model.constraints.add(model.heat["BBOI", y, d, t] == model.biom["BBOI", y, d, t] * devs["BBOI"]["eta_th"])
                # Waste CHP correlation between production of power and heat and waste consumption
                model.constraints.add(model.power["WCHP", y, d, t] == model.waste["WCHP", y, d, t] * devs["WCHP"]["eta_el"])
                model.constraints.add(model.heat["WCHP", y, d, t] == model.waste["WCHP", y, d, t] * devs["WCHP"]["eta_th"])
                # Waste boiler correlation between heat and waste consumption
                model.constraints.add(model.heat["WBOI", y, d, t] == model.waste["WBOI", y, d, t] * devs["WBOI"]["eta_th"])
                # Electrolyzer correlation between hydrogen production and electric power consumption
                model.constraints.add(model.hydrogen["ELYZ", y, d, t] == model.power["ELYZ", y, d, t] * devs["ELYZ"]["eta_el"])
                # Fuel cell correlation between hydrogen consumption and electric power production
                model.constraints.add(model.power["FC", y, d, t] == model.hydrogen["FC", y, d, t] * devs["FC"]["eta_el"])
                if devs["FC"]["enable_heat_diss"]:  # Heat can also be dissipated
                    model.constraints.add(model.heat["FC", y, d, t] <= model.hydrogen["FC", y, d, t] * devs["FC"]["eta_th"])
                else:  # Heat must be used
                    model.constraints.add(model.heat["FC", y, d, t] == model.hydrogen["FC", y, d, t] * devs["FC"]["eta_th"])
                # Sabatier reactor correlation between hydrogen consumption and gas production
                model.constraints.add(model.gas["SAB", y, d, t] == model.hydrogen["SAB", y, d, t] * devs["SAB"]["eta"])

    ################################################################################
    # Energy balances for each time step
    ################################################################################

    for y in model.support_years:
        for d in model.clusters:
            for t in model.time_steps:
                # Heat balance
                heat_supply = sum(model.heat[dev, y, d, t] for dev in
                                  ["STC", "HP", "GroundHP", "EB", "CHP", "BOI", "GHP", "BCHP", "BBOI", "WCHP", "WBOI", "FC"])
                heat_demand = dem["heat"][y][d][t] + model.heat["AC", y, d, t] + model.ch["TES", y, d, t]
                model.constraints.add(heat_supply == heat_demand)

                # Electric power supply and demand balance
                power_supply = sum(
                    model.power[dev, y, d, t] for dev in ["PV", "WT", "WAT", "CHP", "BCHP", "WCHP", "FC", "from_grid"])
                power_demand = dem["power"][y][d][t] + sum(
                    model.power[dev, y, d, t] for dev in ["HP", "GroundHP", "EB", "CC", "ELYZ", "to_grid"]) + model.ch["BAT", y, d, t]
                model.constraints.add(power_supply == power_demand)

                # Cooling supply and demand balance
                cool_supply = model.cool["AC", y, d, t] + model.cool["CC", y, d, t]
                cool_demand = dem["cool"][y][d][t] + model.ch["CTES", y, d, t]
                model.constraints.add(cool_supply == cool_demand)

                # Gas supply and demand balance
                gas_supply = model.gas["from_grid", y, d, t] + model.gas["SAB", y, d, t]
                gas_demand = (
                    sum(model.gas[dev, y, d, t] - model.biomethane[dev, y, d, t] for dev in ["CHP", "BOI", "GHP"])
                    + model.gas["to_grid", y, d, t]
                    + model.ch["GS", y, d, t]
                )
                model.constraints.add(gas_supply == gas_demand)

                # Hydrogen supply and demand balance
                h2_supply = model.hydrogen["ELYZ", y, d, t] + model.hydrogen["import", y, d, t]
                h2_demand = sum(model.hydrogen[dev, y, d, t] for dev in ["FC", "SAB"]) + model.ch["H2S", y, d, t]
                model.constraints.add(h2_supply == h2_demand)

                # Biomass supply and demand balance
                model.constraints.add(model.biom["import", y, d, t] == model.biom["BCHP", y, d, t] + model.biom["BBOI", y, d, t])
                model.constraints.add(model.biomethane["import", y, d, t] == model.biomethane["CHP", y, d, t] + model.biomethane["BOI", y, d, t] + model.biomethane["GHP", y, d, t])

                # Waste supply and demand balance
                model.constraints.add(model.waste["import", y, d, t] == model.waste["WCHP", y, d, t] + model.waste["WBOI", y, d, t])

    ################################################################################
    # Renewable heat share target
    ################################################################################

    for y in model.support_years:
        target_share = _get_active_renewable_heat_share(
            param,
            year=int(y))

        if target_share > 0:
            renewable_heat = sum(
                model.heat[dev, y, d, t] * param["cluster_weights"][d]
                for dev in EH_RENEWABLE_HEAT
                for d in model.clusters
                for t in model.time_steps
            ) + sum(
                (
                    model.biomethane["CHP", y, d, t] * devs["CHP"]["eta_th"]
                    + model.biomethane["BOI", y, d, t] * devs["BOI"]["eta_th"]
                    + model.biomethane["GHP", y, d, t] * devs["GHP"]["COP"]
                ) * param["cluster_weights"][d]
                for d in model.clusters
                for t in model.time_steps
            )
            total_heat = sum(
                model.heat[dev, y, d, t] * param["cluster_weights"][d]
                for dev in EH_HEAT_PRODUCERS
                for d in model.clusters
                for t in model.time_steps
            )
            model.constraints.add(renewable_heat >= target_share * total_heat)

    ################################################################################
    # Meet peak demands of unclustered demands to ensure the design can handle peak loads
    ################################################################################

    if param["peak_dem_met_conv"]:
        # Heating (conventional - only controllable devices)
        model.constraints.add(model.cap["HP"] + model.cap["GroundHP"] + model.cap["EB"]
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
        model.constraints.add(model.cap["STC"] + model.cap["HP"] + model.cap["GroundHP"] + model.cap["EB"]
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
        for y in model.support_years:
            for day_y in model.year:
                for t in range(1, len(model.time_steps)):
                    # Energy balance for storage devices: soc(t) = soc(t-1) * (1 - sto_loss)^dt + charge * dt
                    soc_prev = model.soc[dev, y, day_y, t - 1]
                    model.constraints.add(
                        model.soc[dev, y, day_y, t] == soc_prev * (1 - devs[dev]["sto_loss"]) ** dt + model.ch[
                            dev, y, model.sigma[day_y], t] * dt)
                if day_y > 0:
                    # For the first time step of each day, the state of charge is based on the previous day's last time step
                    # Equation: soc(t=0) = soc(t=last) * (1 - sto_loss)^dt + charge * dt
                    soc_prev_day = model.soc[dev, y, day_y - 1, len(model.time_steps) - 1]
                    model.constraints.add(
                        model.soc[dev, y, day_y, 0] == soc_prev_day * (1 - devs[dev]["sto_loss"]) ** dt + model.ch[
                            dev, y, model.sigma[day_y], 0] * dt)

            # Cyclic year condition: For the last time step of the last day, the state of charge is based on the first time step of the first day
            soc_last = model.soc[dev, y, 51, cluster_horizon - 1]
            model.constraints.add(model.soc[dev, y, 0, 0] == soc_last * (1 - devs[dev]["sto_loss"]) ** dt + model.ch[
                dev, y, model.sigma[0], 0] * dt)

    ################################################################################
    # Grid limits
    ################################################################################

    for y in model.support_years:
        model.constraints.add(
            model.from_gas_grid_total[y] == dt * sum(
                model.gas["from_grid", y, d, t] * param["cluster_weights"][d]
                for d in model.clusters for t in model.time_steps))

        model.constraints.add(
            model.from_el_grid_total[y] == dt * sum(
                model.power["from_grid", y, d, t] * param["cluster_weights"][d]
                for d in model.clusters for t in model.time_steps))

        model.constraints.add(
            model.to_gas_grid_total[y] == dt * sum(
                model.gas["to_grid", y, d, t] * param["cluster_weights"][d]
                for d in model.clusters for t in model.time_steps))

        model.constraints.add(
            model.to_el_grid_total[y] == dt * sum(
                model.power["to_grid", y, d, t] * param["cluster_weights"][d]
                for d in model.clusters for t in model.time_steps))

        model.constraints.add(
            model.biom_import_total[y] == dt * sum(
                model.biom["import", y, d, t] * param["cluster_weights"][d]
                for d in model.clusters for t in model.time_steps))

        model.constraints.add(
            model.biomethane_import_total[y] == dt * sum(
                model.biomethane["import", y, d, t] * param["cluster_weights"][d]
                for d in model.clusters for t in model.time_steps))

        model.constraints.add(
            model.waste_import_total[y] == dt * sum(
                model.waste["import", y, d, t] * param["cluster_weights"][d]
                for d in model.clusters for t in model.time_steps))

        model.constraints.add(
            model.hydrogen_import_total[y] == dt * sum(
                model.hydrogen["import", y, d, t] * param["cluster_weights"][d]
                for d in model.clusters for t in model.time_steps))

    ################################################################################
    # Supply limitations (User input)
    ################################################################################

    # Forbid/allow feed-in
    if not param.get("enable_feed_in_el", True):
        for y in model.support_years:
            model.constraints.add(model.to_el_grid_total[y] == 0)
    if not param.get("enable_feed_in_gas", True):
        for y in model.support_years:
            model.constraints.add(model.to_gas_grid_total[y] == 0)

    if param["enable_supply_el"] != True:
        for y in model.support_years:
            model.constraints.add(model.from_el_grid_total[y] == 0)
    if param["enable_cap_limit_el"] == True:
        model.constraints.add(model.grid_limit_el <= param["cap_limit_el"])
    if param["enable_supply_limit_el"] == True:
        for y in model.support_years:
            model.constraints.add(model.from_el_grid_total[y] <= param["supply_limit_el"])

    # Limitation of gas supply
    if param["enable_supply_gas"] != True:
        for y in model.support_years:
            model.constraints.add(model.from_gas_grid_total[y] == 0)
    if param["enable_cap_limit_gas"] == True:
        model.constraints.add(model.grid_limit_gas <= param["cap_limit_gas"])
    if param["enable_supply_limit_gas"] == True:
        for y in model.support_years:
            model.constraints.add(model.from_gas_grid_total[y] <= param["supply_limit_gas"])

    # Limitation of biomethane supply
    if param.get("enable_supply_biomethane") != True:
        for y in model.support_years:
            model.constraints.add(model.biomethane_import_total[y] == 0)
    if param.get("enable_supply_limit_biomethane") == True:
        for y in model.support_years:
            model.constraints.add(model.biomethane_import_total[y] <= param.get("supply_limit_biomethane"))

    # Limitation of biomass supply
    if param["enable_supply_biomass"] != True:
        for y in model.support_years:
            model.constraints.add(model.biom_import_total[y] == 0)
    if param["enable_supply_limit_biomass"] == True:
        for y in model.support_years:
            model.constraints.add(model.biom_import_total[y] <= param["supply_limit_biomass"])

    # Limitation of waste supply
    if param["enable_supply_waste"] != True:
        for y in model.support_years:
            model.constraints.add(model.waste_import_total[y] == 0)
    if param["enable_supply_limit_waste"] == True:
        for y in model.support_years:
            model.constraints.add(model.waste_import_total[y] <= param["supply_limit_waste"])

    # Limitation of hydrogen supply
    if param["enable_supply_hydrogen"] != True:
        for y in model.support_years:
            model.constraints.add(model.hydrogen_import_total[y] == 0)
    if param["enable_supply_limit_hydrogen"] == True:
        for y in model.support_years:
            model.constraints.add(model.hydrogen_import_total[y] <= param["supply_limit_hydrogen"])

    ################################################################################
    # Economic constraints - according to VDI 2067 Blatt 1 - annuity method
    ################################################################################

    # Electricity costs and revenues (per support year with year-specific prices)
    for y in model.support_years:
        model.constraints.add(model.supply_costs_el[y] == model.from_el_grid_total[y] * param["price_supply_el_eh"][y])
        model.constraints.add(model.rev_feed_in_el[y] == model.to_el_grid_total[y] * param["revenue_feed_in_el_eh"][y])

        # Gas costs and revenues (per support year with year-specific prices)
        model.constraints.add(model.supply_costs_gas[y] == model.from_gas_grid_total[y] * param["price_supply_gas_eh"][y])
        model.constraints.add(model.rev_feed_in_gas[y] == model.to_gas_grid_total[y] * param["revenue_feed_in_gas"][y])

        # Biomass, waste, and hydrogen costs (per support year with year-specific prices)
        model.constraints.add(model.supply_costs_biomethane[y] == model.biomethane_import_total[y] * param["price_biomethane"][y])
        model.constraints.add(model.supply_costs_biom[y] == model.biom_import_total[y] * param["price_biomass"][y])
        model.constraints.add(model.supply_costs_waste[y] == model.waste_import_total[y] * param["price_waste"][y])
        model.constraints.add(model.supply_costs_hydrogen[y] == model.hydrogen_import_total[y] * param["price_hydrogen"][y])

    # Conditional capacity costs for electricity (same for all years)
    if param["enable_price_cap_el"]:
        model.constraints.add(model.cap_costs_el == model.grid_limit_el * param["price_cap_el"])
    else:
        model.constraints.add(model.cap_costs_el == 0)

    # Gas capacity costs (same for all years)
    model.constraints.add(model.cap_costs_gas == model.grid_limit_gas * param["price_cap_gas"])

    # Investment and operational costs for each device (Annualized)
    for dev in model.all_devs:
        if is_5g_fixed and dev == "CC":     #da durch reversible HP bereits abgedeckt
            model.constraints.add(model.inv[dev] == 0)
            model.constraints.add(model.inv_base[dev] == 0)
            model.constraints.add(model.c_inv[dev] == 0)
            model.constraints.add(model.c_inv_base[dev] == 0)
            model.constraints.add(model.c_om[dev] == 0)
            model.constraints.add(model.c_total[dev] == 0)
            continue

        model.constraints.add(model.inv[dev] == devs[dev]["inv_var"] * model.cap[dev])  # investment costs
        model.constraints.add(model.inv_base[dev] == devs[dev]["inv_base"] * model.cap[dev])  # unsubsidized investment costs
        model.constraints.add(model.c_inv[dev] == model.inv[dev] * devs[dev]["ann_factor"])  # annualized investment costs
        model.constraints.add(model.c_inv_base[dev] == model.inv_base[dev] * devs[dev]["ann_factor"])  # unsubsidized annualized investment costs
        model.constraints.add(model.c_om[dev] == devs[dev]["cost_om"] * model.inv_base[dev])  # operation and maintenance costs. Use the unsubsidized costs for O&M calculation
        model.constraints.add(model.c_total[dev] == model.c_inv[dev] + model.c_om[dev])  # total annualized costs for investment and O&M



    # Combined total annualized investment and O&M costs for all devices
    model.constraints.add(model.total_annual_costs_devices == sum(model.c_total[dev] for dev in model.all_devs))

    # Heat grid costs
    model.constraints.add(model.heat_grid_costs == data.heat_grid_data["ann_costs"] + data.heat_grid_data["om_costs"])

    # Connection costs to electricity and gas grid (currently assumed to be a constant annual cost)
    model.constraints.add(model.total_connection_costs == model.cap_costs_el + model.cap_costs_gas)

    # Energy costs and revenues
    for y in model.support_years:
        model.constraints.add(model.total_energy_costs[y] ==
                              model.supply_costs_el[y]
                              + model.supply_costs_gas[y]
                              + model.supply_costs_biomethane[y]
                              + model.supply_costs_biom[y]
                              + model.supply_costs_waste[y]
                              + model.supply_costs_hydrogen[y]
                              - model.rev_feed_in_el[y]
                              - model.rev_feed_in_gas[y])

    # CO2 tax term for emissions from gas, biomass, waste for each support year (Usually not paid by consumers, already included in energy prices)
    co2_tax_term={}
    for y in model.support_years:
        co2_tax_term[y] = (
            model.from_gas_grid_total[y] * param["co2_gas"][y]
            + model.biomethane_import_total[y] * param["co2_biomethane"][y]
            + model.biom_import_total[y] * param["co2_biom"][y]
            + model.waste_import_total[y] * param["co2_waste"][y]
        ) * param["co2_tax"][y]

    # additional costs and revenues can be added here if needed
    for y in model.support_years:
        model.constraints.add(model.misc_costs[y] == co2_tax_term[y])

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

    # Calculate the NPV for energy and miscellaneous costs (According to VDI 2067 Blatt 1)
    # Use geometric series formula: sum(1/q^(year+k) for k in 0..n-1) = (1/q^year) * (1 - (1/q)^n) / (1 - 1/q)
    npv_energy = 0
    npv_misc = 0
    for idx, year in enumerate(sorted_years):
        interval_length = weights[year]
        # Calculate discount factor for this interval using geometric series formula
        if i != 0:
            base_discount = 1 / (q ** (year+1)) # Use year+1 as norm refers to the first year with index 1, but here the index starts with 0. This means that the year i refers to the year i+1 in the norm and an index shift of 1 is needed
            interval_factor = (1 - (1/q) ** interval_length) / (1 - 1/q)
            discount_factor = base_discount * interval_factor
        else:  # If interest rate is zero, discount factor is simply the interval length
            discount_factor = interval_length

        npv_energy += model.total_energy_costs[year] * discount_factor
        npv_misc += model.misc_costs[year] * discount_factor

    # Annualize the NPV over the observation period using the annuity factor
    if i != 0:
        annuity_factor = (i * q**n) / (q**n - 1)
    else:
        annuity_factor = 1 / n  # If interest rate is 0, simply divide by number of years

    model.constraints.add(model.annualized_energy_costs == npv_energy * annuity_factor)
    model.constraints.add(model.annualized_misc_costs == npv_misc * annuity_factor)

    # Total annual costs (According to VDI 2067 Blatt 1)
    # obj_tac = capital_cost + om_cost + supply_costs + taxes and other costs - revenues
    model.constraints.add(model.obj_tac == model.total_annual_costs_devices  # Cost associated with devices (inv and om)
                          + model.total_connection_costs  # Cost for connection to el and gas grid
                          + model.heat_grid_costs  # Cost for heat grid inv and om
                          + model.annualized_energy_costs  # Energy supply costs minus revenues from feed-in
                          + model.annualized_misc_costs)  # Miscellaneous costs minus revenues

    # CO2 emissions calculation (Sum over the whole observation period)
    model.constraints.add(model.obj_co2 == sum(
    (
        model.from_el_grid_total[y] * param["co2_el_grid"][y]
        + model.from_gas_grid_total[y] * param["co2_gas"][y]
        + model.biomethane_import_total[y] * param["co2_biomethane"][y]
        + model.biom_import_total[y] * param["co2_biom"][y]
        + model.waste_import_total[y] * param["co2_waste"][y]
        + model.hydrogen_import_total[y] * param["co2_hydrogen"][y]
        - model.to_el_grid_total[y] * param["co2_el_feed_in"][y]
        - model.to_gas_grid_total[y] * param["co2_gas_feed_in"][y]
    ) * weights[y] for y in model.support_years
    ))

    ################################################################################
    # Define Objective Function
    ################################################################################

    def objective_rule(model):
        return (1 - param["optimization_focus"]) * model.obj_tac + param["optimization_focus"] * model.obj_co2 # 1 = co2 minimization, 0 = cost minimization

    model.objective = pyo.Objective(rule=objective_rule, sense=pyo.minimize)

    return model


def solve_model_and_extract_results(data, model, devs, param, result_dict):
    """
    Function to capsle solving the Pyomo model and extracting results.
    """

    result_dir = "optimization_results"
    if not os.path.exists(result_dir):
        os.makedirs(result_dir)

    model_name = f"ehdo_model"

    results = solver_config.execute_and_diagnose(model = model,
                                   pyomo_config = data.pyomo_config,
                                   model_name = model_name,
                                   result_dir = result_dir)

    if results.solver.termination_condition != pyo.TerminationCondition.optimal:
        return None

    solver_config.write_solution_file(model = model,
                                      model_name = model_name,
                                      result_dir = result_dir)

    ################################################################################
    # Post-processing and Result Extraction #! This needs to be adapted to multi-year optimization
    ################################################################################

    # --- Robust helper functions for safe value queries ---
    def safe_value(var_container, index):
        try:
            v = var_container[index]
        except KeyError as e:
            raise KeyError(
                f"Invalid index for {var_container.name}: {index}. "
                f"Valid index example: (dev, y, d, t) depending on variable."
            ) from e

        val = pyo.value(v)
        if val is None:
            raise RuntimeError(f"Variable {var_container.name}{index} has no value")
        return val

    def safe_value_single(var):
        val = pyo.value(var)
        if val is None:
            raise RuntimeError(f"Variable {var.name} has no value.")
        return val

    # --- Complete and original filling of the result_dict ---
    result_dict["devs"] = devs
    result_dict["tac"] = int(safe_value_single(model.obj_tac))  # EUR/a
    result_dict["co2"] = int(safe_value_single(model.obj_co2))  #  kg over full horizon

    for k in model.all_devs:
        result_dict[k] = {
            "cap": round(safe_value(model.cap, k), 1),
            "ann_inv_cost": round(safe_value(model.c_inv, k), 2),
            "ann_inv_cost_unsubsidized": round(safe_value(model.c_inv_base, k), 2),
            "om_cost": round(safe_value(model.c_om, k), 2)
        }

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
    result_dict["total_inv_cost_unsubsidized"] = int(sum(safe_value(model.inv_base, k) for k in model.all_devs) + heat_grid_costs)
    result_dict["total_ann_inv_cost"] = int(
        sum(safe_value(model.c_inv, k) for k in model.all_devs) + heat_grid_ann_costs)
    result_dict["total_ann_inv_cost_unsubsidized"] = int(
        sum(safe_value(model.c_inv_base, k) for k in model.all_devs) + heat_grid_ann_costs)
    result_dict["total_om_cost"] = int(sum(safe_value(model.c_om, k) for k in model.all_devs) + heat_grid_om_costs)

    # Total energy imports and exports - per support year
    result_dict["from_el_grid_total_by_year"] = {y: int(safe_value(model.from_el_grid_total, y) / 1000) for y in model.support_years} #MWh
    result_dict["to_el_grid_total_by_year"] = {y: int(safe_value(model.to_el_grid_total, y) / 1000) for y in model.support_years}       #MWh
    result_dict["from_gas_grid_total_by_year"] = {y: int(safe_value(model.from_gas_grid_total, y) / 1000) for y in model.support_years}  #MWh
    result_dict["to_gas_grid_total_by_year"] = {y: int(safe_value(model.to_gas_grid_total, y) / 1000) for y in model.support_years}       #MWh
    result_dict["biomethane_import_total_by_year"] = {y: int(safe_value(model.biomethane_import_total, y) / 1000) for y in model.support_years}  #MWh
    result_dict["biom_import_total_by_year"] = {y: int(safe_value(model.biom_import_total, y) / 1000) for y in model.support_years}      #MWh
    result_dict["waste_import_total_by_year"] = {y: int(safe_value(model.waste_import_total, y) / 1000) for y in model.support_years}        #MWh
    result_dict["hydrogen_import_total_by_year"] = {y: int(safe_value(model.hydrogen_import_total, y) / 1000) for y in model.support_years}    #MWh

    # Calculate weights for each support year (same logic as in build_model)
    sorted_years = sorted(model.support_years)
    n = param["observation_time"]
    weights = {}
    for idx, year in enumerate(sorted_years):
        if idx < len(sorted_years) - 1:
            weights[year] = sorted_years[idx + 1] - year
        else:
            weights[year] = n - year

    # Total energy imports and exports over the whole observation period (weighted sum)
    result_dict["from_el_grid_total"] = int(sum(safe_value(model.from_el_grid_total, y) * weights[y] for y in model.support_years) / 1000)  # MWh
    result_dict["to_el_grid_total"] = int(sum(safe_value(model.to_el_grid_total, y) * weights[y] for y in model.support_years) / 1000)  # MWh
    result_dict["from_gas_grid_total"] = int(sum(safe_value(model.from_gas_grid_total, y) * weights[y] for y in model.support_years) / 1000)  # MWh
    result_dict["to_gas_grid_total"] = int(sum(safe_value(model.to_gas_grid_total, y) * weights[y] for y in model.support_years) / 1000)  # MWh
    result_dict["biomethane_import_total"] = int(sum(safe_value(model.biomethane_import_total, y) * weights[y] for y in model.support_years) / 1000)  # MWh
    result_dict["biom_import_total"] = int(sum(safe_value(model.biom_import_total, y) * weights[y] for y in model.support_years) / 1000)  # MWh
    result_dict["waste_import_total"] = int(sum(safe_value(model.waste_import_total, y) * weights[y] for y in model.support_years) / 1000)  # MWh
    result_dict["hydrogen_import_total"] = int(sum(safe_value(model.hydrogen_import_total, y) * weights[y] for y in model.support_years) / 1000)  # MWh

    # CO2 emissions breakdown - calculate weighted average based on first support year for backward compatibility
    result_dict["co2_onsite_emissions"] = int((sum(safe_value(model.from_gas_grid_total, y) * param["co2_gas"][y] for y in model.support_years) +
                                               sum(safe_value(model.biomethane_import_total, y) * param["co2_biomethane"][y] for y in model.support_years) +
                                               sum(safe_value(model.biom_import_total, y) * param["co2_biom"][y] for y in model.support_years) +
                                               sum(safe_value(model.waste_import_total, y) * param["co2_waste"][y] for y in model.support_years)) / 1000)
    result_dict["co2_global_emissions"] = int(result_dict["co2"] / 1000) # t over full observation period
    result_dict["co2_credit_feedin"] = int((sum(safe_value(model.to_el_grid_total, y) * param["co2_el_feed_in"][y] for y in model.support_years) +
                                            sum(safe_value(model.to_gas_grid_total, y) * param["co2_gas_feed_in"][y] for y in model.support_years)) / 1000)
    # CO2 tax: Use weighted average
    result_dict["co2_tax_total"] = int(sum(safe_value(model.misc_costs, y) for y in model.support_years) / len(model.support_years))  # EUR

    # Maximum grid flows (electricity and gas) - check across all support years
    for grid_type in ["from_grid", "to_grid"]:
        max_el = max(safe_value(model.power, (grid_type, y, d, t)) for y in model.support_years for d in model.clusters for t in model.time_steps)
        result_dict[f"max_el_{grid_type}"] = int(max_el)

        max_gas = max(safe_value(model.gas, (grid_type, y, d, t)) for y in model.support_years for d in model.clusters for t in model.time_steps)
        result_dict[f"max_gas_{grid_type}"] = int(max_gas)

    # Maximum import flows for other resources - check across all support years
    result_dict["max_biomethane"] = int(
        max(safe_value(model.biomethane, ("import", y, d, t)) for y in model.support_years for d in model.clusters for t in model.time_steps))
    result_dict["max_biom"] = int(
        max(safe_value(model.biom, ("import", y, d, t)) for y in model.support_years for d in model.clusters for t in model.time_steps))
    result_dict["max_waste"] = int(
        max(safe_value(model.waste, ("import", y, d, t)) for y in model.support_years for d in model.clusters for t in model.time_steps))
    result_dict["max_hydrogen"] = int(
        max(safe_value(model.hydrogen, ("import", y, d, t)) for y in model.support_years for d in model.clusters for t in model.time_steps))

    # Energy costs and revenues - per year and total (annualized)
    result_dict["supply_costs_el_by_year"] = {y: int(safe_value(model.supply_costs_el, y)) for y in model.support_years}
    result_dict["supply_costs_gas_by_year"] = {y: int(safe_value(model.supply_costs_gas, y)) for y in model.support_years}
    result_dict["supply_costs_biomethane_by_year"] = {y: int(safe_value(model.supply_costs_biomethane, y)) for y in model.support_years}
    result_dict["supply_costs_biom_by_year"] = {y: int(safe_value(model.supply_costs_biom, y)) for y in model.support_years}
    result_dict["supply_costs_waste_by_year"] = {y: int(safe_value(model.supply_costs_waste, y)) for y in model.support_years}
    result_dict["supply_costs_hydrogen_by_year"] = {y: int(safe_value(model.supply_costs_hydrogen, y)) for y in model.support_years}
    result_dict["rev_feed_in_el_by_year"] = {y: int(safe_value(model.rev_feed_in_el, y)) for y in model.support_years}
    result_dict["rev_feed_in_gas_by_year"] = {y: int(safe_value(model.rev_feed_in_gas, y)) for y in model.support_years}

    # Totals (annualized values for backward compatibility)
    result_dict["supply_costs_el"] = int(safe_value_single(model.annualized_energy_costs))  # Annualized over all years
    result_dict["cap_costs_el"] = int(safe_value_single(model.cap_costs_el))
    result_dict["total_el_costs"] = result_dict["supply_costs_el"] + result_dict["cap_costs_el"]
    result_dict["rev_feed_in_el"] = int(sum(safe_value(model.rev_feed_in_el, y) for y in model.support_years) / len(model.support_years))  # Average annual electricity feed-in revenue

    result_dict["supply_costs_gas"] = int(sum(safe_value(model.supply_costs_gas, y) for y in model.support_years) / len(model.support_years))
    result_dict["supply_costs_biomethane"] = int(sum(safe_value(model.supply_costs_biomethane, y) for y in model.support_years) / len(model.support_years))
    result_dict["cap_costs_gas"] = int(safe_value_single(model.cap_costs_gas))
    result_dict["total_gas_costs"] = result_dict["supply_costs_gas"] + result_dict["supply_costs_biomethane"] + result_dict["cap_costs_gas"]
    result_dict["rev_feed_in_gas"] = int(sum(safe_value(model.rev_feed_in_gas, y) for y in model.support_years) / len(model.support_years))

    result_dict["supply_costs_biom"] = int(sum(safe_value(model.supply_costs_biom, y) for y in model.support_years) / len(model.support_years))
    result_dict["supply_costs_waste"] = int(sum(safe_value(model.supply_costs_waste, y) for y in model.support_years) / len(model.support_years))
    result_dict["supply_costs_hydrogen"] = int(sum(safe_value(model.supply_costs_hydrogen, y) for y in model.support_years) / len(model.support_years))

    # Renewable generation potential (without curtailment)
    result_dict["PV_generation_uncl"] = [x / 1000 * safe_value(model.area, "PV") for x in
                                         devs["PV"]["norm_power"]]  # in kW
    result_dict["WT_generation_uncl"] = [x * safe_value(model.cap, "WT") for x in devs["WT"]["norm_power"]]  # in kW
    result_dict["STC_generation_uncl"] = [x / 1000 * safe_value(model.area, "STC") for x in
                                          devs["STC"]["norm_power"]]  # in kW

    # Calculate curtailment for renewable sources
    dt = data.time["timeResolution"] / data.time["dataResolution"]

    # PV curtailment - sum over all support years - average per year
    pv_curtailed = 0
    for y in model.support_years:
        for d in model.clusters:
            for t in model.time_steps:
                potential = devs["PV"]["norm_power_clustered"][d][t] / 1000 * safe_value(model.area, "PV")
                actual = safe_value(model.power, ("PV", y, d, t))
                pv_curtailed += (potential - actual) * param["cluster_weights"][d]
    result_dict["PV"]["curtailed"] = int(dt * pv_curtailed / len(model.support_years))

    # STC curtailment - sum over all support years - average per year
    stc_curtailed = 0
    for y in model.support_years:
        for d in model.clusters:
            for t in model.time_steps:
                potential = devs["STC"]["norm_power_clustered"][d][t] / 1000 * safe_value(model.area, "STC")
                actual = safe_value(model.heat, ("STC", y, d, t))
                stc_curtailed += (potential - actual) * param["cluster_weights"][d]
    result_dict["STC"]["curtailed"] = int(dt * stc_curtailed / len(model.support_years))

    # WT curtailment - sum over all support years - average per year
    wt_curtailed = 0
    for y in model.support_years:
        for d in model.clusters:
            for t in model.time_steps:
                potential = devs["WT"]["norm_power_clustered"][d][t] * safe_value(model.cap, "WT")
                actual = safe_value(model.power, ("WT", y, d, t))
                wt_curtailed += (potential - actual) * param["cluster_weights"][d]
    result_dict["WT"]["curtailed"] = int(dt * wt_curtailed / len(model.support_years))

    # WAT curtailment - sum over all support years - average per year
    wat_curtailed = 0
    for y in model.support_years:
        for d in model.clusters:
            for t in model.time_steps:
                potential = min(safe_value(model.cap, "WAT"), devs["WAT"]["potential"])
                actual = safe_value(model.power, ("WAT", y, d, t))
                wat_curtailed += (potential - actual) * param["cluster_weights"][d]
    result_dict["WAT"]["curtailed"] = int(dt * wat_curtailed / len(model.support_years))

    # Power profiles and maximum power - store for each support year - multi-year adaptation
    result_dict["power_profile_by_year"] = {}
    result_dict["power_kW_by_year"] = {}
    for y in model.support_years:
        result_dict["power_profile_by_year"][y] = {}
        result_dict["power_kW_by_year"][y] = {}
        for device in ["PV", "WT", "WAT", "HP", "GroundHP", "EB", "CC", "CHP", "BCHP", "WCHP", "ELYZ", "FC", "from_grid", "to_grid"]:
            profile = []
            for d in model.clusters:
                for t in model.time_steps:
                    profile.append(safe_value(model.power, (device, y, d, t)))
            result_dict["power_profile_by_year"][y][device] = profile
            result_dict["power_kW_by_year"][y][device] = int(max(profile)) if profile else 0

    # Heat profiles and maximum heat - store for each support year
    result_dict["heat_profile_by_year"] = {}
    result_dict["heat_kW_by_year"] = {}
    for y in model.support_years:
        result_dict["heat_profile_by_year"][y] = {}
        result_dict["heat_kW_by_year"][y] = {}
        for device in ["STC", "HP", "GroundHP", "EB", "AC", "CHP", "BOI", "GHP", "BCHP", "BBOI", "WCHP", "WBOI", "FC"]:
            profile = []
            for d in model.clusters:
                for t in model.time_steps:
                    profile.append(safe_value(model.heat, (device, y, d, t)))
            result_dict["heat_profile_by_year"][y][device] = profile
            result_dict["heat_kW_by_year"][y][device] = int(max(profile)) if profile else 0

    # Cooling profiles and maximum cooling - store for each support year
    result_dict["cool_profile_by_year"] = {}
    result_dict["cool_kW_by_year"] = {}
    for y in model.support_years:
        result_dict["cool_profile_by_year"][y] = {}
        result_dict["cool_kW_by_year"][y] = {}
        for device in ["CC", "AC"]:
            profile = []
            for d in model.clusters:
                for t in model.time_steps:
                    profile.append(safe_value(model.cool, (device, y, d, t)))
            result_dict["cool_profile_by_year"][y][device] = profile
            result_dict["cool_kW_by_year"][y][device] = int(max(profile)) if profile else 0

    # Area usage
    result_dict["area"] = {}
    for device in ["PV", "STC"]:
        result_dict["area"][device] = int(safe_value(model.area, device))

    # Calculate annual generation for each device type structure result_dict[device]["gen_kWh"]["energy_type"] and result_dict[device]["gen"]["energy_type"]

    # Heat generation
    for k in ["STC", "HP", "GroundHP", "EB", "BOI", "GHP", "BBOI", "WBOI", "CHP", "BCHP", "WCHP", "FC"]:
        gen_kwh = dt * sum(safe_value(model.heat, (k, y, d, t)) * param["cluster_weights"][d] * weights[y]
                    for y in model.support_years for d in model.clusters for t in model.time_steps)
        if k not in result_dict:
            result_dict[k] = {}
        if "gen_kWh" not in result_dict[k]:
            result_dict[k]["gen_kWh"] = {}
        if "gen" not in result_dict[k]:
            result_dict[k]["gen"] = {}
        result_dict[k]["gen_kWh"]["heat"] = gen_kwh
        result_dict[k]["gen"]["heat"] = int(gen_kwh / 1000)  # MWh over full horizon

    # Cooling generation
    for k in ["CC", "AC"]:
        gen_kwh = dt * sum(safe_value(model.cool, (k, y, d, t)) * param["cluster_weights"][d] * weights[y]
                    for y in model.support_years for d in model.clusters for t in model.time_steps)
        if k not in result_dict:
            result_dict[k] = {}
        if "gen_kWh" not in result_dict[k]:
            result_dict[k]["gen_kWh"] = {}
        if "gen" not in result_dict[k]:
            result_dict[k]["gen"] = {}
        result_dict[k]["gen_kWh"]["cooling"] = gen_kwh
        result_dict[k]["gen"]["cooling"] = int(gen_kwh / 1000)  # MWh over full horizon

    # Power generation
    for k in ["PV", "WT", "WAT", "CHP", "BCHP", "WCHP", "ELYZ", "FC"]:
        gen_kwh = dt * sum(safe_value(model.power, (k, y, d, t)) * param["cluster_weights"][d] * weights[y]
                    for y in model.support_years for d in model.clusters for t in model.time_steps)
        if k not in result_dict:
            result_dict[k] = {}
        if "gen_kWh" not in result_dict[k]:
            result_dict[k]["gen_kWh"] = {}
        if "gen" not in result_dict[k]:
            result_dict[k]["gen"] = {}
        result_dict[k]["gen_kWh"]["power"] = gen_kwh
        result_dict[k]["gen"]["power"] = int(gen_kwh / 1000)  # MWh over full horizon

    # Special: Hydrogen generation for ELYZ
    h2_gen = dt * sum(safe_value(model.power, ("ELYZ", y, d, t)) * devs["ELYZ"]["eta_el"] * param["cluster_weights"][d] * weights[y]
                    for y in model.support_years for d in model.clusters for t in model.time_steps)
    if "ELYZ" not in result_dict:
        result_dict["ELYZ"] = {}
    if "gen_kWh" not in result_dict["ELYZ"]:
        result_dict["ELYZ"]["gen_kWh"] = {}
    if "gen" not in result_dict["ELYZ"]:
        result_dict["ELYZ"]["gen"] = {}
    result_dict["ELYZ"]["gen_kWh"]["hydrogen"] = h2_gen
    result_dict["ELYZ"]["gen"]["hydrogen"] = int(h2_gen / 1000)  # MWh over full horizon

    # Gas generation for SAB
    for k in ["SAB"]:
        gen_kwh = dt * sum(safe_value(model.gas, (k, y, d, t)) * param["cluster_weights"][d] * weights[y]
                    for y in model.support_years for d in model.clusters for t in model.time_steps)
        if k not in result_dict:
            result_dict[k] = {}
        if "gen_kWh" not in result_dict[k]:
            result_dict[k]["gen_kWh"] = {}
        if "gen" not in result_dict[k]:
            result_dict[k]["gen"] = {}
        result_dict[k]["gen_kWh"]["gas"] = gen_kwh
        result_dict[k]["gen"]["gas"] = int(gen_kwh / 1000)  # MWh over full horizon

    eps = 0.01
    # Calculate full load hours
    for k in ["PV", "WT", "WAT", "STC", "HP", "GroundHP", "EB", "CC", "AC", "CHP", "BOI", "GHP", "BCHP", "BBOI",
              "WCHP", "WBOI", "ELYZ", "FC", "SAB"]:
        cap_k = safe_value(model.cap, k)
        if cap_k > eps:
            # Decide which energy to use as the base for full load hours
            if k in ["PV", "WT", "WAT", "CHP", "BCHP", "WCHP", "FC"]:
                base_gen_kwh = result_dict[k]["gen_kWh"]["power"]
            elif k in ["STC", "HP", "GroundHP", "EB", "BOI", "GHP", "BBOI", "WBOI"]:
                base_gen_kwh = result_dict[k]["gen_kWh"]["heat"]
            elif k in ["CC", "AC"]:
                base_gen_kwh = result_dict[k]["gen_kWh"]["cooling"]
            elif k == "ELYZ":
                base_gen_kwh = result_dict[k]["gen_kWh"]["hydrogen"]
            elif k == "SAB":
                base_gen_kwh = result_dict[k]["gen_kWh"]["gas"]
            else:
                base_gen_kwh = 0

            result_dict[k]["hrs"] = int((base_gen_kwh / param["observation_time"]) / cap_k)
        else:
            result_dict[k]["hrs"] = 0

    # Select technologies that are installed
    for k in model.all_devs:
        result_dict[k]["inst"] = safe_value(model.cap, k) > eps

    # Calculate charge cycles of storages
    for k in ["TES", "CTES", "BAT", "H2S", "GS"]:
        cap_k = safe_value(model.cap, k)
        if cap_k > eps:
            charge_cycles = dt * sum(abs(safe_value(model.ch, (k, y, d, t))) / 2 * param["cluster_weights"][d] * weights[y]
                                     for y in model.support_years for d in model.clusters for t in model.time_steps)
            annual_throughput = charge_cycles / param["observation_time"]
            result_dict[k]["chc"] = int(annual_throughput / cap_k)
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
        # Maximum SOC (across all support years)
        max_soc = max(safe_value(model.soc, (dev, y, day_y, t)) for y in model.support_years for day_y in model.year for t in model.time_steps)
        result_dict[dev]["soc"] = int(max_soc)

        # Maximum charging power (across all support years)
        max_ch = max(safe_value(model.ch, (dev, y, d, t)) for y in model.support_years for d in model.clusters for t in model.time_steps)
        result_dict[dev]["ch"] = int(max_ch)

    # Calculate detailed CO2 emissions by source (weighted sum over all support years with year-specific factors)
    result_dict["total_co2_el"] = int(sum(safe_value(model.from_el_grid_total, y) * param["co2_el_grid"][y] * weights[y] for y in model.support_years) / 1000)  # t over full horizon
    result_dict["total_co2_el_feed_in"] = int(sum(safe_value(model.to_el_grid_total, y) * param["co2_el_feed_in"][y] * weights[y] for y in model.support_years) / 1000)  # t over full horizon
    result_dict["total_co2_gas"] = int(sum(safe_value(model.from_gas_grid_total, y) * param["co2_gas"][y] * weights[y] for y in model.support_years) / 1000)  # t over full horizon
    result_dict["total_co2_gas_feed_in"] = int(sum(safe_value(model.to_gas_grid_total, y) * param["co2_gas_feed_in"][y] * weights[y] for y in model.support_years) / 1000)  # t over full horizon
    result_dict["total_co2_biomethane"] = int(sum(safe_value(model.biomethane_import_total, y) * param["co2_biomethane"][y] * weights[y] for y in model.support_years) / 1000)  # t over full horizon
    result_dict["total_co2_biom"] = int(sum(safe_value(model.biom_import_total, y) * param["co2_biom"][y] * weights[y] for y in model.support_years) / 1000)  # t over full horizon
    result_dict["total_co2_waste"] = int(sum(safe_value(model.waste_import_total, y) * param["co2_waste"][y] * weights[y] for y in model.support_years) / 1000)  # t over full horizon
    result_dict["total_co2_hydrogen"] = int(sum(safe_value(model.hydrogen_import_total, y) * param["co2_hydrogen"][y] * weights[y] for y in model.support_years) / 1000)  # t over full horizon

    return result_dict
