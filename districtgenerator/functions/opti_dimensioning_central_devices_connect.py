# -*- coding: utf-8 -*-
"""
EHDO - ENERGY HUB DESIGN OPTIMIZATION Tool
Pyomo Version

This script is a Pyomo-based translation of the original Gurobi model.
"""



from xml.parsers.expat import model

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
from districtgenerator.functions.debug_optimization import run_pre_solve_checks
from pyomo.opt import TerminationCondition as TC


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
        A dictionary that will be filled with the optimization results for all districts.

    Returns
    -------
    dict
        The populated result dictionary, or the original dict if no solution is found.
    """
    # Set start_time 
    start_time = time.time()

    # Build the model
    model = pyo.ConcreteModel(name="Energy_Hub_Design_Optimization_Network")
    model, all_devs_list = build_model(model=model, dataCon=dataCon, devsCon=devsCon, paramCon=paramCon, demCon=demCon)
    model_building_time = time.time() - start_time
    
    print(f"Precalculation and model set up done in {model_building_time:.2f} seconds.")

    # Solve the model and extract results
    result_dictCon = solve_model_and_extract_results(dataCon, model, devsCon, paramCon,
                                                  result_dictCon, demCon)
    
    # Folder to save model and results
    result_dir = "optimization_results"
    if not os.path.exists(result_dir):
        os.makedirs(result_dir)

    for district in model.districts:
        scenario_name = district
        result_dict = result_dictCon[scenario_name]
        param = paramCon[scenario_name]
        dem= demCon[scenario_name]
        # Save results to csv
        save_results_csv(model, result_dict, scenario_name, result_dir, all_devs_list, param=param)
        save_results_csv_short(model, result_dict, scenario_name, result_dir, all_devs_list, param=param)
        save_demand_heat_timeseries_csv(dem, model, district, result_dir)
        save_demand_power_timeseries_csv(dem, model, district, result_dir)

    # # Save network power timeseries for all districts
    # save_network_power_timeseries_csv(model, result_dir)
    
    model_solve_time = time.time() - start_time - model_building_time

    # Total time needed
    total_time = time.time() - start_time

    # Maybe record the times into a log file

    print(f"\n Time needed for building the model: {model_building_time:.2f} seconds.")
    print(f" Time needed for solving the model: {model_solve_time:.2f} seconds.")
    print(f" Total time needed: {total_time:.2f} seconds.")

    return result_dictCon

def build_model(model, dataCon, devsCon, paramCon, demCon):
    # %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    # 1. Initialize Pyomo Model and Define Sets
    # %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

    # Load data for one district for clustering
    # calculate cluster time horizon
    data=dataCon[list(dataCon.keys())[0]]
    param=paramCon[list(paramCon.keys())[0]]

    # Model Parameters
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
    
    # Create a set for all districts
    district_names = [district.scenario_name for district in dataCon.values()]
    model.districts = pyo.Set(initialize=district_names)

    # Create sets for all device types
    all_devs_list = ["PV", "WT", "STC", "WAT", "HP", "EB", "CC", "AC", "CHP", "BOI", "GHP",
                     "BCHP", "BBOI", "WCHP", "WBOI", "ELYZ", "FC", "H2S", "SAB", "TES",
                     "CTES", "BAT", "GS"]

    gas_devs_list = ["CHP", "BOI", "GHP", "SAB", "from_grid", "to_grid"]
    power_devs_list = ["PV", "WT", "WAT", "HP", "EB", "CC", "CHP", "BCHP", "WCHP", "ELYZ", "FC", "from_grid", "to_grid", "from_main_grid", "to_main_grid", "from_network", "to_network"] # for network
    heat_devs_list = ["STC", "HP", "EB", "AC", "CHP", "BOI", "GHP", "BCHP", "BBOI", "WCHP", "WBOI", "FC"]
    cool_devs_list = ["CC", "AC"]
    hydrogen_devs_list = ["ELYZ", "FC", "SAB", "import"]
    biom_devs_list = ["BCHP", "BBOI", "import"]
    waste_devs_list = ["WCHP", "WBOI", "import"]
    storage_devs_list = ["TES", "CTES", "BAT", "H2S", "GS"]
    area_devs_list = ["PV", "STC"]
    grid_flows_list = ["from_grid", "to_grid"] # for network
    segments = ["small", "medium","large"]  # new TJA
    segment_devs=["HP","TES","STC","EB", "BBOI", "BCHP","PV"]  # new TJA

    

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
    model.segments = pyo.Set(initialize=segments) # new TJA
    model.segment_devs = pyo.Set(initialize=segment_devs) # new TJA
    model.heat_cap_devs = pyo.Set(initialize=["STC", "EB", "HP", "BOI", "GHP", "BBOI", "WBOI"])
    model.power_cap_devs = pyo.Set(initialize=["PV", "WT", "WAT", "CHP", "BCHP", "WCHP", "ELYZ", "FC"])
    model.cool_cap_devs = pyo.Set(initialize=["CC", "AC"])
    model.gas_cap_devs = pyo.Set(initialize=["SAB"])
    # %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    # 2. Create Pyomo Variables
    # %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    # Capacity variables (same for all years - single investment decision) but indexed by district
    model.cap = pyo.Var( model.all_devs, model.districts, within=pyo.NonNegativeReals, name="nominal_capacity")
    model.area = pyo.Var(model.area_devs, model.districts, within=pyo.NonNegativeReals, name="roof_area")

    # Operational variables for EACH support year and district
    # Gas/Power/Heat... to/from devices
    model.gas = pyo.Var(model.gas_devs, model.districts, model.support_years, model.clusters, model.time_steps, within=pyo.NonNegativeReals)
    model.power = pyo.Var(model.power_devs, model.districts, model.support_years, model.clusters, model.time_steps, within=pyo.NonNegativeReals)
    model.heat = pyo.Var(model.heat_devs, model.districts, model.support_years, model.clusters, model.time_steps, within=pyo.NonNegativeReals)
    model.cool = pyo.Var(model.cool_devs, model.districts, model.support_years, model.clusters, model.time_steps, within=pyo.NonNegativeReals)
    model.hydrogen = pyo.Var(model.hydrogen_devs, model.districts, model.support_years, model.clusters, model.time_steps, within=pyo.NonNegativeReals)
    model.biom = pyo.Var(model.biom_devs, model.districts, model.support_years, model.clusters, model.time_steps, within=pyo.NonNegativeReals)
    model.waste = pyo.Var(model.waste_devs, model.districts, model.support_years, model.clusters, model.time_steps, within=pyo.NonNegativeReals)
    model.ch = pyo.Var(model.storage_devs, model.districts, model.support_years, model.clusters, model.time_steps, within=pyo.Reals)

    # Heat generation of each devive per year
    model.heat_gen = pyo.Var(model.heat_devs, model.districts, model.support_years, within=pyo.NonNegativeReals) #new for network
    model.heat_sum = pyo.Var(model.districts, model.support_years, within=pyo.NonNegativeReals) #new for network

    # Storage SOC uses weekly tracking but indexed by support year and district
    model.soc = pyo.Var(model.storage_devs, model.districts, model.support_years, model.year, model.time_steps,
                        within=pyo.NonNegativeReals)
    
    # Investment costs (same for all years) indexed by district
    model.inv = pyo.Var(model.all_devs, model.districts, within=pyo.NonNegativeReals)    # subsidized investment costs payed by the investor
    model.inv_base = pyo.Var(model.all_devs, model.districts, within=pyo.NonNegativeReals)  # unsubsidized investment costs
    model.inv_sub_1tes = pyo.Var(model.districts, within=pyo.NonNegativeReals)  # subsidy amount for TES based on KWKG subsidy, new for network
    model.c_inv = pyo.Var(model.all_devs, model.districts, within=pyo.NonNegativeReals)
    model.c_inv_base = pyo.Var(model.all_devs, model.districts, within=pyo.NonNegativeReals)  # unsubsidized annualized investment costs
    model.c_om = pyo.Var(model.all_devs, model.districts, within=pyo.NonNegativeReals)
    model.c_total = pyo.Var(model.all_devs, model.districts, within=pyo.NonNegativeReals)

    # Grid limits (same for all years - infrastructure decision) indexed by district
    model.grid_limit_el = pyo.Var(model.districts, within=pyo.NonNegativeReals)
    model.grid_limit_gas = pyo.Var(model.districts, within=pyo.NonNegativeReals)

    # Variable to make sure that feed in and withdrawal from the grid are mutually exclusive in each time step
    model.grid_import_binary = pyo.Var(model.districts, model.support_years, model.clusters, model.time_steps, within=pyo.Binary) # new for network

    # Binary Variable to decide if capacity of a device is small, medium or large for cost calculation (new TJA)
    model.cap_bin = pyo.Var(model.segments, model.all_devs, model.districts, within=pyo.Binary)  # new for network
    # Segment devices

    # Continuous variable one for each segment to determine the capacity in each segment for cost calculation (new TJA)
    model.cap_seg = pyo.Var(model.segments, model.segment_devs, model.districts, within=pyo.NonNegativeReals)  # new for network

    ## Binary variable to decide if size if TES > 250 m² for KWKG subsidy
    model.tes_kwkg_binary = pyo.Var(model.districts, within=pyo.Binary)  # new for network

    # Yearly total energy flows - indexed by support year and district
    model.from_el_grid_total = pyo.Var(model.districts, model.support_years, within=pyo.NonNegativeReals) 
    model.to_el_grid_total = pyo.Var(model.districts, model.support_years, within=pyo.NonNegativeReals) 
    model.from_el_main_grid_total = pyo.Var(model.districts, model.support_years, within=pyo.NonNegativeReals) # for network
    model.to_el_main_grid_total = pyo.Var(model.districts, model.support_years, within=pyo.NonNegativeReals) # for network
    model.from_network_total = pyo.Var(model.districts, model.support_years, within=pyo.NonNegativeReals) # for network
    model.to_network_total = pyo.Var(model.districts, model.support_years, within=pyo.NonNegativeReals) # for network
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
    model.heat_grid_costs_base = pyo.Var(model.districts,within=pyo.NonNegativeReals)               # Total annual costs for heat grid (inv and om) without subsidy
    model.total_energy_costs = pyo.Var(model.districts, model.support_years, within=pyo.NonNegativeReals)    # Total energy costs per year
    model.annualized_energy_costs = pyo.Var(model.districts, within=pyo.NonNegativeReals)                    # Annualized energy costs
    model.misc_costs = pyo.Var(model.districts, model.support_years, within=pyo.NonNegativeReals)            # e.g., CO2 costs, insurance, other taxes etc.
    model.annualized_misc_costs = pyo.Var(model.districts, within=pyo.NonNegativeReals)                      # Annualized miscellaneous costs
    model.total_connection_costs = pyo.Var(model.districts, within=pyo.NonNegativeReals)                     # Total annual costs for connection to grids
    model.total_annual_costs = pyo.Var(model.districts, model.support_years, within=pyo.NonNegativeReals)           # Total annual costs 
    
    # Objective variables
    model.obj_tac = pyo.Var(within=pyo.Reals)
    model.obj_co2 = pyo.Var(within=pyo.Reals)

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
                # For devices with linear cost segments, the capacity is determined by the sum of the capacities in each segment
                if devs[dev]["lin_feasible"]== True:
                    model.constraints.add(model.cap[dev,district] == sum(model.cap_seg[seg,dev,district] for seg in model.segments))
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
    

    # Add constraints for the device operation based on the device capacity
    # Limited operation based on installed capacity
    def heat_cap_rule(m, district, dev, y, d, t):
        return m.heat[dev, district, y, d, t] <= m.cap[dev, district]

    def power_cap_rule(m, district, dev, y, d, t):
        return m.power[dev, district, y, d, t] <= m.cap[dev, district]

    def cool_cap_rule(m, district, dev, y, d, t):
        return m.cool[dev, district, y, d, t] <= m.cap[dev, district]

    def gas_cap_rule(m, district, dev, y, d, t):
        return m.gas[dev, district, y, d, t] <= m.cap[dev, district]

    model.c_heat_cap = pyo.Constraint(
        model.districts, model.heat_cap_devs, model.support_years, model.clusters, model.time_steps,
        rule=heat_cap_rule
    )
    model.c_power_cap = pyo.Constraint(
        model.districts, model.power_cap_devs, model.support_years, model.clusters, model.time_steps,
        rule=power_cap_rule
    )
    model.c_cool_cap = pyo.Constraint(
        model.districts, model.cool_cap_devs, model.support_years, model.clusters, model.time_steps,
        rule=cool_cap_rule
    )
    model.c_gas_cap = pyo.Constraint(
        model.districts, model.gas_cap_devs, model.support_years, model.clusters, model.time_steps,
        rule=gas_cap_rule
    )
    # ---------- Grid flow constraints ----------
     # Limitation of power from and to the grid
    def from_grid_el_limit_rule(m, district, y, d, t):
        return m.power["from_grid", district, y, d, t] <= m.grid_limit_el[district]

    def to_grid_el_limit_rule(m, district, y, d, t):
        return m.power["to_grid", district, y, d, t] <= m.grid_limit_el[district]
    
    # Network decomposition: to_grid = to_main_grid + to_network
    def to_grid_decomp_rule(m, district, y, d, t):
        return m.power["to_grid", district, y, d, t] == \
            m.power["to_main_grid", district, y, d, t] + m.power["to_network", district, y, d, t]
    
    # Network decomposition: from_grid = from_main_grid + from_network
    def from_grid_decomp_rule(m, district, y, d, t):
        return m.power["from_grid", district, y, d, t] == \
            m.power["from_main_grid", district, y, d, t] + m.power["from_network", district, y, d, t]

    def from_grid_gas_limit_rule(m, district, y, d, t):
        return m.gas["from_grid", district, y, d, t] <= m.grid_limit_gas[district]

    def to_grid_gas_limit_rule(m, district, y, d, t):
        return m.gas["to_grid", district, y, d, t] <= m.grid_limit_gas[district]

    model.c_from_grid_el_limit = pyo.Constraint(model.districts, model.support_years, model.clusters, model.time_steps, rule=from_grid_el_limit_rule)
    model.c_to_grid_el_limit = pyo.Constraint(model.districts, model.support_years, model.clusters, model.time_steps, rule=to_grid_el_limit_rule)
    model.c_to_grid_decomp = pyo.Constraint(model.districts, model.support_years, model.clusters, model.time_steps, rule=to_grid_decomp_rule)
    model.c_from_grid_decomp = pyo.Constraint(model.districts, model.support_years, model.clusters, model.time_steps, rule=from_grid_decomp_rule)
    model.c_from_grid_gas_limit = pyo.Constraint(model.districts, model.support_years, model.clusters, model.time_steps, rule=from_grid_gas_limit_rule)
    model.c_to_grid_gas_limit = pyo.Constraint(model.districts, model.support_years, model.clusters, model.time_steps, rule=to_grid_gas_limit_rule)

    # Correlation area -> capacity for PV/STC
    def pv_area_cap_rule(m, district):
        devs = devsCon[district]
        return m.cap["PV", district] == m.area["PV", district] * devs["PV"]["G_stc"] * devs["PV"]["eta"]

    def stc_area_cap_rule(m, district):
        devs = devsCon[district]
        return m.cap["STC", district] == m.area["STC", district] * devs["STC"]["G_stc"] * devs["STC"]["eta"]

    model.c_pv_area_cap = pyo.Constraint(model.districts, rule=pv_area_cap_rule)
    model.c_stc_area_cap = pyo.Constraint(model.districts, rule=stc_area_cap_rule)

    # SOC <= storage capacity
    def soc_cap_rule(m, district, dev, y, day_y, t):
        return m.soc[dev, district, y, day_y, t] <= m.cap[dev, district]

    model.c_soc_cap = pyo.Constraint(
        model.districts, model.storage_devs, model.support_years, model.year, model.time_steps,
        rule=soc_cap_rule
    )

    #################################################################################
    # Energy Conversion Constraints (vectorized)
    #################################################################################

    def pv_limit_rule(m, district, y, d, t):
        devs = devsCon[district]
        return m.power["PV", district, y, d, t] <= devs["PV"]["norm_power_clustered"][d][t] / 1000 * m.area["PV", district]

    def wt_limit_rule(m, district, y, d, t):
        devs = devsCon[district]
        return m.power["WT", district, y, d, t] <= devs["WT"]["norm_power_clustered"][d][t] * m.cap["WT", district]

    def stc_limit_rule(m, district, y, d, t):
        devs = devsCon[district]
        return m.heat["STC", district, y, d, t] <= devs["STC"]["norm_power_clustered"][d][t] / 1000 * m.area["STC", district]

    def wat_limit_rule(m, district, y, d, t):
        devs = devsCon[district]
        return m.power["WAT", district, y, d, t] <= devs["WAT"]["potential"]

    def hp_rule(m, district, y, d, t):
        devs = devsCon[district]
        return m.heat["HP", district, y, d, t] == m.power["HP", district, y, d, t] * devs["HP"]["COP"][y][d][t]

    def eb_rule(m, district, y, d, t):
        devs = devsCon[district]
        return m.heat["EB", district, y, d, t] == m.power["EB", district, y, d, t] * devs["EB"]["eta_th"]

    def ghp_rule(m, district, y, d, t):
        devs = devsCon[district]
        return m.heat["GHP", district, y, d, t] == m.gas["GHP", district, y, d, t] * devs["GHP"]["COP"]

    def cc_rule(m, district, y, d, t):
        devs = devsCon[district]
        return m.cool["CC", district, y, d, t] == m.power["CC", district, y, d, t] * devs["CC"]["COP"][y][d][t]

    def ac_rule(m, district, y, d, t):
        devs = devsCon[district]
        return m.cool["AC", district, y, d, t] == m.heat["AC", district, y, d, t] * devs["AC"]["eta_th"]

    def chp_el_rule(m, district, y, d, t):
        devs = devsCon[district]
        return m.power["CHP", district, y, d, t] == m.gas["CHP", district, y, d, t] * devs["CHP"]["eta_el"]

    def chp_th_rule(m, district, y, d, t):
        devs = devsCon[district]
        return m.heat["CHP", district, y, d, t] == m.gas["CHP", district, y, d, t] * devs["CHP"]["eta_th"]

    def bchp_el_rule(m, district, y, d, t):
        devs = devsCon[district]
        return m.power["BCHP", district, y, d, t] == m.biom["BCHP", district, y, d, t] * devs["BCHP"]["eta_el"]

    def bchp_th_rule(m, district, y, d, t):
        devs = devsCon[district]
        return m.heat["BCHP", district, y, d, t] == m.biom["BCHP", district, y, d, t] * devs["BCHP"]["eta_th"]

    def wchp_el_rule(m, district, y, d, t):
        devs = devsCon[district]
        return m.power["WCHP", district, y, d, t] == m.waste["WCHP", district, y, d, t] * devs["WCHP"]["eta_el"]

    def wchp_th_rule(m, district, y, d, t):
        devs = devsCon[district]
        return m.heat["WCHP", district, y, d, t] == m.waste["WCHP", district, y, d, t] * devs["WCHP"]["eta_th"]

    def boi_rule(m, district, y, d, t):
        devs = devsCon[district]
        return m.heat["BOI", district, y, d, t] == m.gas["BOI", district, y, d, t] * devs["BOI"]["eta_th"]

    def bboi_rule(m, district, y, d, t):
        devs = devsCon[district]
        return m.heat["BBOI", district, y, d, t] == m.biom["BBOI", district, y, d, t] * devs["BBOI"]["eta_th"]

    def wboi_rule(m, district, y, d, t):
        devs = devsCon[district]
        return m.heat["WBOI", district, y, d, t] == m.waste["WBOI", district, y, d, t] * devs["WBOI"]["eta_th"]

    def elyz_rule(m, district, y, d, t):
        devs = devsCon[district]
        return m.hydrogen["ELYZ", district, y, d, t] == m.power["ELYZ", district, y, d, t] * devs["ELYZ"]["eta_el"]

    def fc_el_rule(m, district, y, d, t):
        devs = devsCon[district]
        return m.power["FC", district, y, d, t] == m.hydrogen["FC", district, y, d, t] * devs["FC"]["eta_el"]

    def fc_th_rule(m, district, y, d, t):
        devs = devsCon[district]
        if devs["FC"]["enable_heat_diss"]:
            return m.heat["FC", district, y, d, t] <= m.hydrogen["FC", district, y, d, t] * devs["FC"]["eta_th"]
        return m.heat["FC", district, y, d, t] == m.hydrogen["FC", district, y, d, t] * devs["FC"]["eta_th"]

    def sab_rule(m, district, y, d, t):
        devs = devsCon[district]
        return m.gas["SAB", district, y, d, t] == m.hydrogen["SAB", district, y, d, t] * devs["SAB"]["eta"]

    idx5 = (model.districts, model.support_years, model.clusters, model.time_steps)
    model.c_pv_limit = pyo.Constraint(*idx5, rule=pv_limit_rule)
    model.c_wt_limit = pyo.Constraint(*idx5, rule=wt_limit_rule)
    model.c_stc_limit = pyo.Constraint(*idx5, rule=stc_limit_rule)
    model.c_wat_limit = pyo.Constraint(*idx5, rule=wat_limit_rule)
    model.c_hp = pyo.Constraint(*idx5, rule=hp_rule)
    model.c_eb = pyo.Constraint(*idx5, rule=eb_rule)
    model.c_ghp = pyo.Constraint(*idx5, rule=ghp_rule)
    model.c_cc = pyo.Constraint(*idx5, rule=cc_rule)
    model.c_ac = pyo.Constraint(*idx5, rule=ac_rule)
    model.c_chp_el = pyo.Constraint(*idx5, rule=chp_el_rule)
    model.c_chp_th = pyo.Constraint(*idx5, rule=chp_th_rule)
    model.c_bchp_el = pyo.Constraint(*idx5, rule=bchp_el_rule)
    model.c_bchp_th = pyo.Constraint(*idx5, rule=bchp_th_rule)
    model.c_wchp_el = pyo.Constraint(*idx5, rule=wchp_el_rule)
    model.c_wchp_th = pyo.Constraint(*idx5, rule=wchp_th_rule)
    model.c_boi = pyo.Constraint(*idx5, rule=boi_rule)
    model.c_bboi = pyo.Constraint(*idx5, rule=bboi_rule)
    model.c_wboi = pyo.Constraint(*idx5, rule=wboi_rule)
    model.c_elyz = pyo.Constraint(*idx5, rule=elyz_rule)
    model.c_fc_el = pyo.Constraint(*idx5, rule=fc_el_rule)
    model.c_fc_th = pyo.Constraint(*idx5, rule=fc_th_rule)
    model.c_sab = pyo.Constraint(*idx5, rule=sab_rule)

    ################################################################################
    # Energy balances for each time step (vectorized)
    ################################################################################

    def heat_balance_rule(m, district, y, d, t):
        dem = demCon[district]
        return (
            sum(m.heat[dev, district, y, d, t] for dev in ["STC", "HP", "EB", "CHP", "BOI", "GHP", "BCHP", "BBOI", "WCHP", "WBOI", "FC"])
            == dem["heat"][y][d][t] + m.heat["AC", district, y, d, t] + m.ch["TES", district, y, d, t]
        )

    def power_balance_rule(m, district, y, d, t):
        dem = demCon[district]
        return (
            sum(m.power[dev, district, y, d, t] for dev in ["PV", "WT", "WAT", "CHP", "BCHP", "WCHP", "FC", "from_main_grid", "from_network"])
            == dem["power"][y][d][t]
            + sum(m.power[dev, district, y, d, t] for dev in ["HP", "EB", "CC", "ELYZ", "to_main_grid", "to_network"])
            + m.ch["BAT", district, y, d, t]
        )

    def cool_balance_rule(m, district, y, d, t):
        dem = demCon[district]
        return (
            m.cool["AC", district, y, d, t] + m.cool["CC", district, y, d, t]
            == dem["cool"][y][d][t] + m.ch["CTES", district, y, d, t]
        )

    def gas_balance_rule(m, district, y, d, t):
        return (
            m.gas["from_grid", district, y, d, t] + m.gas["SAB", district, y, d, t]
            == sum(m.gas[dev, district, y, d, t] for dev in ["CHP", "BOI", "GHP", "to_grid"])
            + m.ch["GS", district, y, d, t]
        )

    def h2_balance_rule(m, district, y, d, t):
        return (
            m.hydrogen["ELYZ", district, y, d, t] + m.hydrogen["import", district, y, d, t]
            == sum(m.hydrogen[dev, district, y, d, t] for dev in ["FC", "SAB"])
            + m.ch["H2S", district, y, d, t]
        )

    def biom_balance_rule(m, district, y, d, t):
        return (
            m.biom["import", district, y, d, t]
            == m.biom["BCHP", district, y, d, t] + m.biom["BBOI", district, y, d, t]
        )

    def waste_balance_rule(m, district, y, d, t):
        return (
            m.waste["import", district, y, d, t]
            == m.waste["WCHP", district, y, d, t] + m.waste["WBOI", district, y, d, t]
        )

    model.c_heat_balance = pyo.Constraint(*idx5, rule=heat_balance_rule)
    model.c_power_balance = pyo.Constraint(*idx5, rule=power_balance_rule)
    model.c_cool_balance = pyo.Constraint(*idx5, rule=cool_balance_rule)
    model.c_gas_balance = pyo.Constraint(*idx5, rule=gas_balance_rule)
    model.c_h2_balance = pyo.Constraint(*idx5, rule=h2_balance_rule)
    model.c_biom_balance = pyo.Constraint(*idx5, rule=biom_balance_rule)
    model.c_waste_balance = pyo.Constraint(*idx5, rule=waste_balance_rule)

    # Network power balance
    def network_balance_rule(m, y, d, t):
        return (
            sum(m.power["to_network", district, y, d, t] for district in m.districts)
            == sum(m.power["from_network", district, y, d, t] for district in m.districts)
        )

    model.c_network_balance = pyo.Constraint(model.support_years, model.clusters, model.time_steps, rule=network_balance_rule)

    # Enforcing mutual exclusivity of grid import/export in each time step using Big M method
    max_from_grid = max(param["cap_limit_el"] for param in paramCon.values())
    max_to_grid = max(param["cap_limit_el"] for param in paramCon.values())
    Big_M = max(max_from_grid, max_to_grid) * 2  

    def grid_binary_rule1(model, district, y, d, t):
        return model.power["from_grid", district, y, d, t] <= Big_M * model.grid_import_binary[district, y, d, t]
    
    def grid_binary_rule2(model, district, y, d, t):
        return model.power["to_grid", district, y, d, t] <= Big_M * (1 - model.grid_import_binary[district, y, d, t])
    
    model.grid_binary1 = pyo.Constraint(model.districts, model.support_years, model.clusters, model.time_steps, rule=grid_binary_rule1)
    model.grid_binary2 = pyo.Constraint(model.districts, model.support_years, model.clusters, model.time_steps, rule=grid_binary_rule2)
     
                    
    # SOS1 Constraint: Nur from_grid ODER to_grid darf > 0 sein, nicht beide
    # Läuft sehr lang
    # def sos_rule(model, district, y, d, t):
    #     return [model.power["from_grid", district, y, d, t], model.power["to_grid", district, y, d, t]]
    
    # model.grid_logic = pyo.SOSConstraint(
    #     model.districts, model.support_years, model.clusters, model.time_steps,
    #     rule= sos_rule,
    #     sos=1
    # )

    ################################################################################
    # Meet peak demands of unclustered demands to ensure the design can handle peak loads
    ################################################################################
    for district in model.districts:
        for y in model.support_years:
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
                                    >= param["peak_heat"][y]) # New TJA

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
                                    >= param["peak_heat"][y]) # New TJA

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
                    model.power["from_main_grid", district, y, d, t] * param["cluster_weights"][d] # for network
                    for d in model.clusters for t in model.time_steps))
            
            model.constraints.add(
                model.from_el_grid_total[district, y] == dt * sum(
                    model.power["from_grid", district, y, d, t] * param["cluster_weights"][d]
                    for d in model.clusters for t in model.time_steps))

            model.constraints.add(
                model.to_gas_grid_total[district, y] == dt * sum(
                    model.gas["to_grid", district, y, d, t] * param["cluster_weights"][d]
                    for d in model.clusters for t in model.time_steps))

            model.constraints.add(
                model.to_el_main_grid_total[district, y] == dt * sum(
                    model.power["to_main_grid", district, y, d, t] * param["cluster_weights"][d] # for network
                    for d in model.clusters for t in model.time_steps))
            
            model.constraints.add(
                model.to_el_grid_total[district, y] == dt * sum(
                    model.power["to_grid", district, y, d, t] * param["cluster_weights"][d]
                    for d in model.clusters for t in model.time_steps))
            
            model.constraints.add(
                model.from_network_total[district, y] == dt * sum(
                    model.power["from_network", district, y, d, t] * param["cluster_weights"][d] # for network
                    for d in model.clusters for t in model.time_steps))
            
            model.constraints.add(
                model.to_network_total[district, y] == dt * sum(
                    model.power["to_network", district, y, d, t] * param["cluster_weights"][d] # for network
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
                model.constraints.add(model.to_el_main_grid_total[district, y] == 0) # for network
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
                model.constraints.add(model.from_el_main_grid_total[district, y] <= param["supply_limit_el"])

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
    # Legal constraints 
    ################################################################################
    if param["enable_legal_requirements"] == True:
        for district in model.districts: # new for network
            param = paramCon[district]
            devs = devsCon[district]
            for y in model.support_years:
                # Enforce legal heating contraints for each device, district, and year
                for dev in model.heat_devs:
                    # Calculate total heat generation per device and district per year
                    model.constraints.add(model.heat_gen[dev, district,y] == dt * sum(
                        model.heat[dev,district,y,d,t] *param["cluster_weights"][d]
                        for d in model.clusters for t in model.time_steps))
                    
                # Calculate the sum of heat generation of all devices per district and year
                model.constraints.add(model.heat_sum[district,y] == sum(model.heat_gen[dev,district, y] for dev in model.heat_devs))
                # Enforce that the renewable share of heat generation is above the minimum required share
                renewable_heat_technologies = ["STC", "HP", "BCHP", "BBOI","WCHP", "WBOI"]  # Define which devices are considered renewable for heat generation
                model.constraints.add(
                    sum(model.heat_gen[dev, district, y] for dev in renewable_heat_technologies)
                    +model.heat_gen["EB", district, y] * param["renewable_el_grid_share"][y]
                    >= param["renewable_heat_share"][y] * model.heat_sum[district,y]
                )
            

        # Enforce that the total installed capacity of heat generation technologies is sufficient to meet the peak heat demand
        # considering the renewable share requirement
        for district in model.districts: # new for network
            param = paramCon[district]
            devs = devsCon[district]
            for y in model.support_years:
                model.constraints.add(
                    model.cap["STC", district] + model.cap["HP", district] + model.cap["EB", district] * param["renewable_el_grid_share"][y]
                    + model.cap["BCHP", district]/ devs["BCHP"]["eta_el"]*devs["BCHP"]["eta_th"]
                    + model.cap["BBOI", district] 
                    + model.cap["WCHP", district]/ devs["WCHP"]["eta_el"]*devs["WCHP"]["eta_th"] 
                    + model.cap["WBOI", district] >= param["peak_heat"][y])


                    
                # Make sure that biomass share is below the maximum allowed share
                # Define which devices are considered biomass-based for heat generation
                biomass_heat_technologies = ["BCHP", "BBOI"]  
                model.constraints.add(sum(model.heat_gen[dev, district, y] for dev in biomass_heat_technologies) <= param["max_biomass_share"][y] * model.heat_sum[district,y])
    

    ################################################################################
    # Economic constraints - according to VDI 2067 Blatt 1 - annuity method
    ################################################################################
    for district in model.districts:
        param = paramCon[district]
        # Electricity costs and revenues (per support year with year-specific prices)
        for y in model.support_years:
            model.constraints.add(model.supply_costs_el[district, y] == model.from_el_main_grid_total[district, y] * param["price_supply_el_eh"][y]+ model.from_network_total[district,y]*param["price_supply_el_network"][y]) # for network
            model.constraints.add(model.rev_feed_in_el[district, y] == model.to_el_main_grid_total[district, y] * param["revenue_feed_in_el_eh"][y]+ model.to_network_total[district,y]*param["revenue_feed_in_el_network"][y]) # for network

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
    # New TJA
    # Linearization of investment costs for devices with piecewise linear cost functions (e.g., heat pumps, boilers) based on selected capacity segments
    for district in model.districts:
        devs = devsCon[district]
        for dev in model.all_devs:
            if devs[dev]["lin_feasible"]== True:
                # Enforce that only one segment can be selected for linearized devices
                model.constraints.add(sum(model.cap_bin[seg, dev, district] for seg in model.segments) == 1)
                # Define upper boundries of each segment
                model.constraints.add(model.cap_seg["small",dev, district]<=model.cap_bin["small",dev, district] * devs[dev]["inv_size2"])
                model.constraints.add(model.cap_seg["medium",dev, district]<=model.cap_bin["medium",dev, district] * devs[dev]["inv_size3"])
                # model.constraints.add(model.cap_seg["large",dev, district]<=model.cap_bin["large",dev, district] * devs[dev]["inv_size4"]) # No upper limit
                # Define lower boundries of each segment
                # model.constraints.add(model.cap_seg["small",dev, district]>=model.cap_bin["small",dev, district] * devs[dev]["inv_size1"]) # No lower limit for the first segment
                model.constraints.add(model.cap_seg["medium",dev, district]>=model.cap_bin["medium",dev, district] * devs[dev]["inv_size2"])
                model.constraints.add(model.cap_seg["large",dev, district]>=model.cap_bin["large",dev, district] * devs[dev]["inv_size3"])
                # Caluclate slope of cost function for each segment
                slope_small= (devs[dev]["inv_cost2"] - devs[dev]["inv_cost1"]) / (devs[dev]["inv_size2"] - devs[dev]["inv_size1"])
                slope_medium= (devs[dev]["inv_cost3"] - devs[dev]["inv_cost2"]) / (devs[dev]["inv_size3"] - devs[dev]["inv_size2"])
                slope_large= (devs[dev]["inv_cost4"] - devs[dev]["inv_cost3"]) / (devs[dev]["inv_size4"] - devs[dev]["inv_size3"])
                # Define base investment costs based on selected segment and capacity
                model.constraints.add(model.inv_base[dev, district]== 
                                      model.cap_bin["small",dev, district]*devs[dev]["inv_cost1"] + slope_small*(model.cap_seg["small",dev, district]-model.cap_bin["small",dev, district] * devs[dev]["inv_size1"]) +
                                      model.cap_bin["medium",dev, district]*devs[dev]["inv_cost2"] + slope_medium*(model.cap_seg["medium",dev, district]-model.cap_bin["medium",dev, district] * devs[dev]["inv_size2"]) +
                                      model.cap_bin["large",dev, district]*devs[dev]["inv_cost3"] + slope_large*(model.cap_seg["large",dev, district]-model.cap_bin["large",dev, district] * devs[dev]["inv_size3"]))

            else:
                model.constraints.add(model.inv_base[dev, district] == devs[dev]["inv_base"] * model.cap[dev, district])  # unsubsidized investment costs
    
    # New TJA
    # Subsidies for TES according to KWKG (Germany) - subsidy based on capacity segments (<= 50 m^3, > 50 m^3)
    Big_M = 1e8  
    EPS= 1e-6
    
    # b= 0 => vol_TES <= 50
    # b=1 => vol_TES > 50
    def con_vol_upper_rule(model, district):
        devs = devsCon[district]
        param = paramCon[district]
        # vol_TES <= 50 + M * b
        # If b=0: vol_TES <= 50 (boundary), if b=1: vol_TES <= 50+ M * b
        vol_TES = model.cap["TES", district] / (param["c_w"] * param["rho_w"] * devs["TES"]["delta_T"]) * 3600
        if not devs["TES"]["inv_kwkg_feasible"]:
            return pyo.Constraint.Skip
        return vol_TES <= devs["TES"]["inv_subsidy_cap"] + Big_M * (model.tes_kwkg_binary[district])
    def con_vol_lower_rule(model, district):
        devs = devsCon[district]
        param = paramCon[district]
        # vol_TES >= 50 - M * (1 - b)
        # If b=0: vol_TES > 50 - M , if b=1: vol_TES > 50 (boundary)
        vol_TES = model.cap["TES", district] / (param["c_w"] * param["rho_w"] * devs["TES"]["delta_T"]) * 3600
        if not devs["TES"]["inv_kwkg_feasible"]:
            return pyo.Constraint.Skip
        return vol_TES >=(devs["TES"]["inv_subsidy_cap"]+EPS) - Big_M * (1 - model.tes_kwkg_binary[district])
    
    # Case 1: vol_TES <= 50
    # Only active, if b= 0 
    # inv = inv_base - 250* vol_TES <=> inv- inv_base = - 250*vol_TES
    def con_inv_case1_upper_rule(model, district):
        devs = devsCon[district]
        param = paramCon[district]
        # inv- inv_base <= - 250 * vol_TES + M * b
        # If b=0 => inv- inv_base <= - 250 * vol_TES
        # If b= 1 => inv- inv_base <= - 250 * vol_TES + M (no constraint)
        vol_TES = model.cap["TES", district] / (param["c_w"] * param["rho_w"] * devs["TES"]["delta_T"]) * 3600
        if not devs["TES"]["inv_kwkg_feasible"]:
            return pyo.Constraint.Skip
        return model.inv_sub_1tes[district] - model.inv_base["TES", district] <= - devs["TES"]["inv_subsidy_abs"] * vol_TES + Big_M * model.tes_kwkg_binary[district]
    
    def con_inv_case1_lower_rule(model, district):
        devs = devsCon[district]
        param = paramCon[district]
        # inv- inv_base >= - 250 * vol_TES - M * b
        # If b=0 => inv- inv_base >= - 250 * vol_TES
        # If b= 1 => inv- inv_base >= - 250 * vol_TES - M (no constraint)
        vol_TES = model.cap["TES", district] / (param["c_w"] * param["rho_w"] * devs["TES"]["delta_T"]) * 3600
        if not devs["TES"]["inv_kwkg_feasible"]:
            return pyo.Constraint.Skip
        return model.inv_sub_1tes[district] - model.inv_base["TES", district] >= - devs["TES"]["inv_subsidy_abs"] * vol_TES - Big_M * model.tes_kwkg_binary[district]

    # Case 2: vol_TES > 50
    # Only active, if b= 1
    # inv= inv_base*(1-"inv_subsidy_rate_g50") <=> inv - inv_base*(1-"inv_subsidy_rate_g50") = 0
    def con_inv_case2_upper_rule(model, district):
        devs = devsCon[district]
        # inv - inv_base*(1-"inv_subsidy_rate_g50") <= M * (1 - b)
        if not devs["TES"]["inv_kwkg_feasible"]:
            return pyo.Constraint.Skip
        return model.inv_sub_1tes[district] - model.inv_base["TES", district] * (1 - devs["TES"]["inv_subsidy_rate_g50"]) <= Big_M * (1 - model.tes_kwkg_binary[district])
    
    def con_inv_case2_lower_rule(model, district):
        devs = devsCon[district]
        if not devs["TES"]["inv_kwkg_feasible"]:
            return pyo.Constraint.Skip
        # inv - inv_base*(1-"inv_subsidy_rate_g50") >= - M * (1 - b)
        return model.inv_sub_1tes[district] - model.inv_base["TES", district] * (1 - devs["TES"]["inv_subsidy_rate_g50"]) >= - Big_M * (1 - model.tes_kwkg_binary[district])
    
    # Add constraints to the model
    model.con_inv_case1_upper = pyo.Constraint(model.districts, rule=con_inv_case1_upper_rule)
    model.con_inv_case1_lower = pyo.Constraint(model.districts, rule=con_inv_case1_lower_rule)
    model.con_vol_upper = pyo.Constraint(model.districts, rule=con_vol_upper_rule)
    model.con_vol_lower = pyo.Constraint(model.districts, rule=con_vol_lower_rule)
    model.con_inv_case2_upper = pyo.Constraint(model.districts, rule=con_inv_case2_upper_rule)
    model.con_inv_case2_lower = pyo.Constraint(model.districts, rule=con_inv_case2_lower_rule)

    # Finale TES-investmentequation per district
    def con_inv_tes_rule(model, district):
        devs = devsCon[district]
        if devs["TES"]["inv_kwkg_feasible"]:
            if "inv_subsidy_rate" in devs["TES"] and devs["TES"]["inv_subsidy_rate"] is not None:
                return model.inv["TES", district] == model.inv_sub_1tes[district] * (1 - devs["TES"]["inv_subsidy_rate"])  # New TJA
            return model.inv["TES", district] == model.inv_sub_1tes[district]

        if (devs["TES"]["inv_kwkg_feasible"]== False and 
            "inv_subsidy_rate" in devs["TES"] and devs["TES"]["inv_subsidy_rate"] is not None):
            return model.inv["TES", district] == model.inv_base["TES", district] * (1 - devs["TES"]["inv_subsidy_rate"])  # subsidy term New TJA

        return model.inv["TES", district] == model.inv_base["TES", district]
    
    model.con_inv_tes = pyo.Constraint(model.districts, rule=con_inv_tes_rule)

    for district in model.districts:
        devs = devsCon[district]
        param = paramCon[district]

        for dev in model.all_devs:
            if dev == "TES":
                continue  # TES investment costs are already defined in the previous constraints based on the subsidy regimes
            if "inv_subsidy_rate" in devs[dev] and devs[dev]["inv_subsidy_rate"] is not None:
                model.constraints.add( model.inv[dev, district] == model.inv_base[dev, district] * (1 - devs[dev]["inv_subsidy_rate"]))  # subsidy term New TJA
            else:
                model.constraints.add(model.inv[dev, district] == model.inv_base[dev, district])  # No subsidy, investment cost equals base cost


    for district in model.districts:
        devs = devsCon[district]
        param = paramCon[district]
        data = dataCon[district]
        for dev in model.all_devs:
            model.constraints.add(model.c_inv[dev, district] == model.inv[dev, district] * devs[dev]["ann_factor"])  # annualized investment costs
            model.constraints.add(model.c_inv_base[dev, district] == model.inv_base[dev, district] * devs[dev]["ann_factor"])  # unsubsidized annualized investment costs
            model.constraints.add(model.c_om[dev, district] == devs[dev]["cost_om"] * model.inv_base[dev, district])  # operation and maintenance costs. Use the unsubsidized costs for O&M calculation
            model.constraints.add(model.c_total[dev, district] == model.c_inv[dev, district] + model.c_om[dev, district])  # total annualized costs for investment and O&M

        # Combined total annualized investment and O&M costs for all devices
        model.constraints.add(model.total_annual_costs_devices[district] == sum(model.c_total[dev, district] for dev in model.all_devs))

        # Heat grid costs
        if param["enable_subsidy_for_heat_grid"]== True:
            model.constraints.add(model.heat_grid_costs_base[district] == data.heat_grid_data["ann_costs"] + data.heat_grid_data["om_costs"])
            model.constraints.add(model.heat_grid_costs[district] == data.heat_grid_data["ann_costs"] *(1-param["subsidy_rate_heat_grid"])+ data.heat_grid_data["om_costs"])
        else:
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

    # Initialize dictionaries to store weights for each support year based on the intervals they cover        
    weights = {}
    for district in model.districts:
        param = paramCon[district]
        weights[district]={}
        # Anualize Energy costs and miscellaneous costs over all support years by calculating Sum of the NPV of each support year/intervall and then annualizing it
        i = param["interest_rate"]
        q = 1 + i
        n = param["observation_time"]
        support_years = model.support_years
        sorted_years = sorted(support_years)

        # Calculate the weights for each support year based on the intervals they cover
        for idx, year in enumerate(sorted_years):
            if idx < len(sorted_years) - 1:
                weights[district][year] = sorted_years[idx + 1] - year # time until next support year
            else:
                weights[district][year] = n - year # time from last support year to end of observation period

    # Calculate the NPV for energy and miscellaneous costs
    # Use geometric series formula for efficiency: sum(1/q^(year+k) for k in 0..n-1) = (1/q^year) * (1 - (1/q)^n) / (1 - 1/q)
    npv_energy = {}
    npv_misc = {}
    for district in model.districts:
        # Initialize NPVs for this district
        npv_energy[district] = 0
        npv_misc[district] = 0
        for idx, year in enumerate(sorted_years):
            interval_length = weights[district][year]
            # Calculate discount factor for this interval using geometric series formula
            if i != 0:  # If interest rate is not zero
                # base_discount = 1 / (q ** year) # old
                base_discount = 1 / (q ** (year+1)) # new TJA
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
        model.constraints.add(model.annualized_misc_costs[district] == npv_misc[district] * annuity_factor)

    #%% DIFINE VARIBALES FOR OBJECTIVE FUNCTIONS
    tac_sum_total = 0
    co2_sum_total = 0

    # Total annual costs (According to VDI 2067 Blatt 1:)
    # obj_tac = capital_cost + om_cost + supply_costs + taxes and other costs - revenues
    for district in model.districts:
        param = paramCon[district]
        tac_sum_distr = (model.total_annual_costs_devices[district]  # Cost associated with devices (inv and om)
                        + model.total_connection_costs[district]  # Cost for connection to el and gas grid
                        + model.heat_grid_costs[district]  # Cost for heat grid inv and om
                        + model.annualized_energy_costs[district]  # Energy supply costs minus revenues from feed-in
                        + model.annualized_misc_costs[district])  # Miscellaneous costs minus revenues
        
        # Sum up total annualized costs for all districts
        tac_sum_total += tac_sum_distr
        
        co2_sum_distr = sum(
        (
            model.from_el_main_grid_total[district, y] * param["co2_el_grid"][y] # for network
            + model.from_gas_grid_total[district, y] * param["co2_gas"][y]
            + model.biom_import_total[district, y] * param["co2_biom"][y]
            + model.waste_import_total[district, y] * param["co2_waste"][y]
            + model.hydrogen_import_total[district, y] * param["co2_hydrogen"][y]
            - model.to_el_main_grid_total[district, y] * param["co2_el_feed_in"][y] # for network
            - model.to_gas_grid_total[district, y] * param["co2_gas_feed_in"][y]
        ) * weights[district][y] for y in model.support_years
        )
        # Sum up total CO2 emissions for all districts
        co2_sum_total += co2_sum_distr

        # Enforce CO2-Neutrality 2045
        if param["enable_legal_requirements"] == True:
            co2_em={}
            for y in model.support_years:
                co2_em[y] = (model.from_el_main_grid_total[district, y] * param["co2_el_grid"][y] # for network
                    + model.from_gas_grid_total[district, y] * param["co2_gas"][y]
                    + model.biom_import_total[district, y] * param["co2_biom"][y]
                    + model.waste_import_total[district, y] * param["co2_waste"][y]
                    + model.hydrogen_import_total[district, y] * param["co2_hydrogen"][y]
                    - model.to_el_main_grid_total[district, y] * param["co2_el_feed_in"][y] # for network
                    - model.to_gas_grid_total[district, y] * param["co2_gas_feed_in"][y]
                ) * weights[district][y]

                model.constraints.add(co2_em[y] <= param["max_co2_emissions"][y]) # New TJA
    
    # Total annualized costs for the whole observation period (sum of all districts)
    model.constraints.add(model.obj_tac == tac_sum_total)  

    model.constraints.add(model.obj_co2 == co2_sum_total)

    # ################################################################################
    # Define Objective Function
    ################################################################################
    
    objective_rule=(1 - param["optimization_focus"]) * model.obj_tac + param["optimization_focus"] * model.obj_co2 # 1 = co2 minimization, 0 = cost minimization

    model.objective = pyo.Objective(rule=objective_rule, sense=pyo.minimize)

    return model, all_devs_list


def solve_model_and_extract_results(dataCon, model, devsCon, paramCon, result_dictCon, demCon):
    """
    Function to capsle solving the Pyomo model and extracting results.
    """

    # Folder to save model and results
    result_dir = "optimization_results"
    if not os.path.exists(result_dir):
        os.makedirs(result_dir)

    lp_filename = os.path.join(result_dir, f"ehdo_model_network.lp")
    model.write(lp_filename, io_options={"symbolic_solver_labels": True})

    # temporary log-file for the solver
    solver_log_path = os.path.join(result_dir, "solver_output_ehdo.log")
    # Path for error file
    errorfile_path = os.path.join(result_dir, 'errorfile_ehdo.txt')

    ################################################################################
    # Solve the Model
    ################################################################################
    # Assumption: The solver configuration is the same for all districts, so the first one from the dictionary is taken. 
    # If needed, this can be adjusted to allow for different solvers per district.
    data=dataCon[list(dataCon.keys())[0]]

    # Start new code TJA
    solver, solver_options = solver_config.create_solver(pyomo_config=data.pyomo_config)
    if str(getattr(solver, "name", "")).lower() != "gurobi_persistent":
        print("Switching solver to gurobi_persistent for IIS support.")
        solver = pyo.SolverFactory("gurobi_persistent")

    if solver_options is None:
        solver_options = {}

    pyomo_cfg = data.pyomo_config if isinstance(data.pyomo_config, dict) else {}
    cfg_options = pyomo_cfg.get("solver_options", {})
    if isinstance(cfg_options, dict):
        merged_options = dict(cfg_options)
        merged_options.update(solver_options)
        solver_options = merged_options

    # Optional numeric stabilizers
    solver_options.setdefault("NumericFocus", 1)
    solver_options.setdefault("Presolve", 2)
    solver_options["LogFile"] = solver_log_path
    solver_options["Method"] = 3

    # Required for persistent interface
    solver.set_instance(model, symbolic_solver_labels=True)

    solve_start_time = time.time()
    results = solver.solve(tee=True, options=solver_options)
    tc = results.solver.termination_condition
    print(f"Optimization finished in {(time.time() - solve_start_time):.2f} seconds.")
    # End new code TJA

    # Original Version
    # solver, solver_options = solver_config.create_solver(pyomo_config=data.pyomo_config) # Adjucst Model
    # solve_start_time = time.time()
    # results = solver.solve(model, tee=True, options=solver_options)
    # tc = results.solver.termination_condition # New TJA
    # print(f"Optimization done. ({(time.time() - solve_start_time):.2f} seconds.)")

    ################################################################################
    # Find error if model is infeasible or out of bounds and write error file # New TJA
    ################################################################################
       
    # Disambiguate infeasible or unbounded
    if tc == TC.infeasibleOrUnbounded:
        print("Termination is infeasibleOrUnbounded -> re-solving with DualReductions=0")
        solver_options = dict(solver_options)
        solver_options["DualReductions"] = 0
        results = solver.solve(tee=True, options=solver_options)
        tc = results.solver.termination_condition

    # IIS analysis
    if tc == TC.infeasible:
        print("Model is infeasible. Computing IIS ...")
        grb_model = getattr(solver, "_solver_model", None)
        if grb_model is not None:
            iis_path = os.path.join(result_dir, "ehdo_model_network.iis.ilp")
            grb_model.computeIIS()
            grb_model.write(iis_path)
            print(f"IIS written to '{iis_path}'.")

            print("\nConstraints in IIS:")
            for c in grb_model.getConstrs():
                if c.IISConstr:
                    print(f"  [LIN] {c.ConstrName}")
            for qc in grb_model.getQConstrs():
                if qc.IISQConstr:
                    print(f"  [QUAD] {qc.QCName}")
            for sc in grb_model.getSOSs():
                if sc.IISSOS:
                    print(f"  [SOS] {sc.SOSName}")

            print("\nVariable bounds in IIS:")
            for v in grb_model.getVars():
                if v.IISLB:
                    print(f"  [LB] {v.VarName} >= {v.LB}")
                if v.IISUB:
                    print(f"  [UB] {v.VarName} <= {v.UB}")
        else:
            print("Could not access underlying Gurobi model for IIS extraction.")


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
                #os.remove(solver_log_path)
            except Exception as e:
                f.write(f"\nCould not read solver log: {e}\n")

        # IIS-Analysis #TODO: Needs a rework to capture the error source correctly
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

        # Using Gurobi to compute a better IIS if Gurobi is available
        import gurobipy as gp
        gurobi_available = True
        try: _ = gp.Env.getEnv()
        except: gurobi_available = False

        if gurobi_available:
            model.write("debug_model.lp", io_options={'symbolic_solver_labels': True})
            m = gp.read("debug_model.lp")
            m.optimize()
            if m.status == gp.GRB.INFEASIBLE or m.status == 4:
                m.computeIIS()
                m.write("debug_model.ilp")
                print("IIS written to debug_model.ilp")
                raise Exception("Model is infeasible, see errorfile for details.")
            raise Exception(f"Model is infeasible, but gurobi could solve it. {m.status}")

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
    #if os.path.exists(solver_log_path):
        #os.remove(solver_log_path)
        

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

    solution_path = os.path.join(result_dir, "solution_ehdo_file.txt")
    write_solution_file(model, solution_path)

    ################################################################################
    # Post-processing and Result Extraction #! This needs to be adapted to multi-year optimization
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

    # Process results for the whole network and store them in result_dictCon
    result_dictCon["network"] = {}
    result_dictCon["network"]["tac"] = int(safe_value_single(model.obj_tac))  # EUR/a
    result_dictCon["network"]["co2"] = int(safe_value_single(model.obj_co2) / 1000)  # t/a

    # Define the output file path
    csv_file_path = os.path.join(result_dir, "network_results.csv")

    # Prepare the data to be written to the CSV file
    data_to_save = [
        ["Variable", "Value"],  # Header row
        ["tac_total", result_dictCon.get("network", "").get("tac","")],  # Total annualized costs
        ["co2_total", result_dictCon.get("network", "").get("co2","")]  # Total CO2 emissions
   
        ]

    # Write the data to the CSV file
    with open(csv_file_path, mode="w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file, delimiter=";")
        writer.writerows(data_to_save)

    print(f"Network-results saved to {csv_file_path}")

    # Initialise weights
    weights = {}
    for district in model.districts:
        result_dict = result_dictCon[district]
        data = dataCon[district]
        devs = devsCon[district]
        param = paramCon[district]
        dem = demCon[district]
        weights[district]={}
        result_dict["devs"] = devs

        for k in model.all_devs:
            result_dict[k] = {
                "cap": round(safe_value(model.cap, (k, district)), 1),
                "inv": round(safe_value(model.inv, (k, district)), 2),
                "inv_unsubsidized": round(safe_value(model.inv_base, (k, district)), 2),
                "ann_inv": round(safe_value(model.c_inv, (k, district)), 2),
                "ann_inv_unsubsidized": round(safe_value(model.c_inv_base, (k, district)), 2),
                "om_cost": round(safe_value(model.c_om, (k, district)), 2)
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

        result_dict["total_inv_cost"] = int(sum(safe_value(model.inv, (k, district)) for k in model.all_devs) + heat_grid_costs)
        result_dict["total_inv_cost_unsubsidized"] = int(sum(safe_value(model.inv_base, (k, district)) for k in model.all_devs) + heat_grid_costs)
        result_dict["total_ann_inv_cost"] = int(
            sum(safe_value(model.c_inv, (k, district)) for k in model.all_devs) + heat_grid_ann_costs)
        result_dict["total_ann_inv_cost_unsubsidized"] = int(
            sum(safe_value(model.c_inv_base, (k, district)) for k in model.all_devs) + heat_grid_ann_costs)
        result_dict["total_om_cost"] = int(sum(safe_value(model.c_om, (k, district)) for k in model.all_devs) + heat_grid_om_costs)

        # Total annualized costs for the district new for network

        result_dict["tac_sum_distr"] = int(
            safe_value(model.total_annual_costs_devices, district)
            + safe_value(model.total_connection_costs, district)
            + safe_value(model.heat_grid_costs, district)
            + safe_value(model.annualized_energy_costs, district)
            + safe_value(model.annualized_misc_costs, district)
        )
        result_dict["total_annual_costs_devices"] = int(safe_value(model.total_annual_costs_devices, district))
        result_dict["total_connection_costs"] = int(safe_value(model.total_connection_costs, district))
        result_dict["heat_grid_costs"] = int(safe_value(model.heat_grid_costs, district))
        result_dict["heat_grid_costs_base"] = int(safe_value(model.heat_grid_costs_base, district))
        result_dict["annualized_energy_costs"] = int(safe_value(model.annualized_energy_costs, district))
        result_dict["annualized_misc_costs"] = int(safe_value(model.annualized_misc_costs, district))

        # Total annual costs per support year
            # Total annualized costs for one year per district
        result_dict["tac_per_distr_year"] = {}
        for y in model.support_years:
            result_dict["tac_per_distr_year"][y] = int(
                safe_value(model.total_annual_costs_devices, district)  # Cost associated with devices (inv and om)
                + safe_value(model.total_connection_costs, district)  # Cost for connection to el and gas
                + safe_value(model.heat_grid_costs, district)  # Cost for heat grid inv and om
                + safe_value(model.total_energy_costs, (district, y))  # Energy supply costs minus revenues from feed-in
                + safe_value(model.misc_costs, (district, y))  # Miscellaneous costs minus revenues
                )

        # Total energy imports and exports - per support year
        result_dict["from_el_grid_total_by_year"] = {y: int(safe_value(model.from_el_grid_total, (district, y)) / 1000) for y in model.support_years} #MWh 
        result_dict["from_el_main_grid_total_by_year"] = {y: int(safe_value(model.from_el_main_grid_total, (district, y)) / 1000) for y in model.support_years} #MWh # new for network
        result_dict["from_network_total_by_year"] = {y: int(safe_value(model.from_network_total, (district, y)) / 1000) for y in model.support_years} #MWh # new for network
        result_dict["to_el_main_grid_total_by_year"] = {y: int(safe_value(model.to_el_main_grid_total, (district, y)) / 1000) for y in model.support_years}       #MWh # new for network
        result_dict["to_el_grid_total_by_year"] = {y: int(safe_value(model.to_el_grid_total, (district, y)) / 1000) for y in model.support_years} #MWh
        result_dict["to_network_total_by_year"] = {y: int(safe_value(model.to_network_total, (district, y)) / 1000) for y in model.support_years} #MWh # new for network
        result_dict["from_gas_grid_total_by_year"] = {y: int(safe_value(model.from_gas_grid_total, (district, y)) / 1000) for y in model.support_years}  #MWh
        result_dict["to_gas_grid_total_by_year"] = {y: int(safe_value(model.to_gas_grid_total, (district, y)) / 1000) for y in model.support_years}       #MWh
        result_dict["biom_import_total_by_year"] = {y: int(safe_value(model.biom_import_total, (district, y)) / 1000) for y in model.support_years}      #MWh
        result_dict["waste_import_total_by_year"] = {y: int(safe_value(model.waste_import_total, (district, y)) / 1000) for y in model.support_years}        #MWh
        result_dict["hydrogen_import_total_by_year"] = {y: int(safe_value(model.hydrogen_import_total, (district, y)) / 1000) for y in model.support_years}    #MWh

        # Grid timeseries new for network
        result_dict["from_main_grid_timeseries"] = {
            y: [[safe_value(model.power, ("from_main_grid", district, y, d, t)) for t in model.time_steps]
                for d in model.clusters]
            for y in model.support_years
        }
        result_dict["to_main_grid_timeseries"] = {
            y: [[safe_value(model.power, ("to_main_grid", district, y, d, t)) for t in model.time_steps]
                for d in model.clusters]
            for y in model.support_years
        }

        result_dict["from_network_timeseries"] = {
            y: [[safe_value(model.power, ("from_network", district, y, d, t)) for t in model.time_steps]
                for d in model.clusters]
            for y in model.support_years
        }
        result_dict["to_network_timeseries"] = {
            y: [[safe_value(model.power, ("to_network", district, y, d, t)) for t in model.time_steps]
                for d in model.clusters]
            for y in model.support_years
        }

        result_dict["from_grid_timeseries"] = {
            y: [[safe_value(model.power, ("from_grid", district, y, d, t)) for t in model.time_steps]
                for d in model.clusters]
            for y in model.support_years
        }
        result_dict["to_grid_timeseries"] = {
            y: [[safe_value(model.power, ("to_grid", district, y, d, t)) for t in model.time_steps]
                for d in model.clusters]
            for y in model.support_years
        }


        # Calculate weights for each support year (same logic as in build_model)
        sorted_years = sorted(model.support_years)
        n = param["observation_time"]
        for idx, year in enumerate(sorted_years):
            if idx < len(sorted_years) - 1:
                weights[district][year] = sorted_years[idx + 1] - year
            else:
                weights[district][year] = n - year

        co2_sum_distr = sum(
            (
                safe_value(model.from_el_main_grid_total, (district, y)) * param["co2_el_grid"][y]
                + safe_value(model.from_gas_grid_total, (district, y)) * param["co2_gas"][y]
                + safe_value(model.biom_import_total, (district, y)) * param["co2_biom"][y]
                + safe_value(model.waste_import_total, (district, y)) * param["co2_waste"][y]
                + safe_value(model.hydrogen_import_total, (district, y)) * param["co2_hydrogen"][y]
                - safe_value(model.to_el_main_grid_total, (district, y)) * param["co2_el_feed_in"][y]
                - safe_value(model.to_gas_grid_total, (district, y)) * param["co2_gas_feed_in"][y]
            ) * weights[district][y] for y in model.support_years
        )
        result_dict["co2_sum_distr"] = int(co2_sum_distr / 1000)

        # CO2 emissions per support year # New TJA
        result_dict["co2_sum_distr_by_year"] = {}
        for y in model.support_years:
            result_dict["co2_sum_distr_by_year"][y] = {}
            co2_sum_distr_year = (
                safe_value(model.from_el_main_grid_total, (district, y)) * param["co2_el_grid"][y]
                + safe_value(model.from_gas_grid_total, (district, y)) * param["co2_gas"][y]
                + safe_value(model.biom_import_total, (district, y)) * param["co2_biom"][y]
                + safe_value(model.waste_import_total, (district, y)) * param["co2_waste"][y]
                + safe_value(model.hydrogen_import_total, (district, y)) * param["co2_hydrogen"][y]
                - safe_value(model.to_el_main_grid_total, (district, y)) * param["co2_el_feed_in"][y]
                - safe_value(model.to_gas_grid_total, (district, y)) * param["co2_gas_feed_in"][y]
            ) * weights[district][y]
            result_dict["co2_sum_distr_by_year"][y] = int(co2_sum_distr_year / 1000)

        # Total energy imports and exports over the whole observation period (weighted sum)
        result_dict["from_el_grid_total"] = int(sum(safe_value(model.from_el_grid_total, (district, y)) * weights[district][y] for y in model.support_years) / 1000)  # MWh # for network
        result_dict["to_el_grid_total"] = int(sum(safe_value(model.to_el_grid_total, (district, y)) * weights[district][y] for y in model.support_years) / 1000)  # MWh # for network
        result_dict["from_el_main_grid_total"] = int(sum(safe_value(model.from_el_main_grid_total, (district, y)) * weights[district][y] for y in model.support_years) / 1000)  # MWh # for network
        result_dict["to_el_main_grid_total"] = int(sum(safe_value(model.to_el_main_grid_total, (district, y)) * weights[district][y] for y in model.support_years) / 1000)  # MWh # for network
        result_dict["from_network_total"] = int(sum(safe_value(model.from_network_total, (district, y)) * weights[district][y] for y in model.support_years) / 1000)  # MWh # for network
        result_dict["to_network_total"] = int(sum(safe_value(model.to_network_total, (district, y)) * weights[district][y] for y in model.support_years) / 1000)  # MWh # for network
        result_dict["from_gas_grid_total"] = int(sum(safe_value(model.from_gas_grid_total, (district, y)) * weights[district][y] for y in model.support_years) / 1000)  # MWh
        result_dict["to_gas_grid_total"] = int(sum(safe_value(model.to_gas_grid_total, (district, y)) * weights[district][y] for y in model.support_years) / 1000)  # MWh
        result_dict["biom_import_total"] = int(sum(safe_value(model.biom_import_total, (district, y)) * weights[district][y] for y in model.support_years) / 1000)  # MWh
        result_dict["waste_import_total"] = int(sum(safe_value(model.waste_import_total, (district, y)) * weights[district][y] for y in model.support_years) / 1000)  # MWh
        result_dict["hydrogen_import_total"] = int(sum(safe_value(model.hydrogen_import_total,(district, y)) * weights[district][y] for y in model.support_years) / 1000)  # MWh

        # CO2 emissions breakdown - calculate weighted average based on first support year for backward compatibility
        result_dict["co2_onsite_emissions"] = int((sum(safe_value(model.from_gas_grid_total, (district, y)) * param["co2_gas"][y] for y in model.support_years) +
                                                sum(safe_value(model.biom_import_total, (district, y)) * param["co2_biom"][y] for y in model.support_years) +
                                                sum(safe_value(model.waste_import_total, (district, y)) * param["co2_waste"][y] for y in model.support_years)) / 1000)
        # result_dict["co2_global_emissions"] = int(result_dict["co2"] / 1000) # Already saved in result_dictCon["network"]["co2"]
        result_dict["co2_credit_feedin"] = int((sum(safe_value(model.to_el_main_grid_total, (district, y)) * param["co2_el_feed_in"][y] for y in model.support_years) + # for network
                                                sum(safe_value(model.to_gas_grid_total,(district, y)) * param["co2_gas_feed_in"][y] for y in model.support_years)) / 1000)
        # CO2 tax: Use weighted average
        result_dict["co2_tax_total"] = int(sum(safe_value(model.misc_costs,(district, y)) for y in model.support_years) / len(model.support_years))  # EUR

        # Maximum grid flows (electricity and gas) - check across all support years
        for grid_type in ["from_grid", "to_grid", "from_network", "to_network", "from_main_grid", "to_main_grid"]:
            max_el = max(safe_value(model.power, (grid_type, district, y, d, t)) for y in model.support_years for d in model.clusters for t in model.time_steps)
            result_dict[f"max_el_{grid_type}"] = int(max_el)

            max_gas = max(safe_value(model.gas, (grid_type, district, y, d, t)) for y in model.support_years for d in model.clusters for t in model.time_steps)
            result_dict[f"max_gas_{grid_type}"] = int(max_gas)

        # Maximum import flows for other resources - check across all support years
        result_dict["max_biom"] = int(
            max(safe_value(model.biom, ("import", district, y, d, t)) for y in model.support_years for d in model.clusters for t in model.time_steps))
        result_dict["max_waste"] = int(
            max(safe_value(model.waste, ("import", district, y, d, t)) for y in model.support_years for d in model.clusters for t in model.time_steps))
        result_dict["max_hydrogen"] = int(
            max(safe_value(model.hydrogen, ("import", district, y, d, t)) for y in model.support_years for d in model.clusters for t in model.time_steps))
        
        # Maximum heat and power demand in the clusterd time series - check across all support years
        result_dict["max_heat_demand"] = max(dem["heat"][y][d][t] for y in model.support_years for d in model.clusters for t in model.time_steps)
        result_dict["max_power_demand"] = max(dem["power"][y][d][t] for y in model.support_years for d in model.clusters for t in model.time_steps)

        # Energy costs and revenues - per year and total (annualized)
        result_dict["supply_costs_el_by_year"] = {y: int(safe_value(model.supply_costs_el, (district, y))) for y in model.support_years}
        result_dict["supply_costs_gas_by_year"] = {y: int(safe_value(model.supply_costs_gas, (district, y))) for y in model.support_years}
        result_dict["supply_costs_biom_by_year"] = {y: int(safe_value(model.supply_costs_biom, (district, y))) for y in model.support_years}
        result_dict["supply_costs_waste_by_year"] = {y: int(safe_value(model.supply_costs_waste, (district, y))) for y in model.support_years}
        result_dict["supply_costs_hydrogen_by_year"] = {y: int(safe_value(model.supply_costs_hydrogen, (district, y))) for y in model.support_years}
        result_dict["rev_feed_in_el_by_year"] = {y: int(safe_value(model.rev_feed_in_el, (district, y))) for y in model.support_years}
        result_dict["rev_feed_in_gas_by_year"] = {y: int(safe_value(model.rev_feed_in_gas, (district, y))) for y in model.support_years}

        # Totals (annualized values for backward compatibility)
        result_dict["supply_costs_el"] = int(safe_value_single(model.annualized_energy_costs[district]))  # Annualized over all years
        result_dict["cap_costs_el"] = int(safe_value_single(model.cap_costs_el[district]))
        result_dict["total_el_costs"] = result_dict["supply_costs_el"] + result_dict["cap_costs_el"]
        result_dict["rev_feed_in_el"] = int(sum(safe_value(model.rev_feed_in_el, (district, y)) for y in model.support_years) / len(model.support_years))  # Average annual electricity feed-in revenue

        result_dict["supply_costs_gas"] = int(sum(safe_value(model.supply_costs_gas, (district, y)) for y in model.support_years) / len(model.support_years))
        result_dict["cap_costs_gas"] = int(safe_value_single(model.cap_costs_gas[district]))
        result_dict["total_gas_costs"] = result_dict["supply_costs_gas"] + result_dict["cap_costs_gas"]
        result_dict["rev_feed_in_gas"] = int(sum(safe_value(model.rev_feed_in_gas, (district, y)) for y in model.support_years) / len(model.support_years))

        result_dict["supply_costs_biom"] = int(sum(safe_value(model.supply_costs_biom, (district, y)) for y in model.support_years) / len(model.support_years))
        result_dict["supply_costs_waste"] = int(sum(safe_value(model.supply_costs_waste, (district, y)) for y in model.support_years) / len(model.support_years))
        result_dict["supply_costs_hydrogen"] = int(sum(safe_value(model.supply_costs_hydrogen, (district, y)) for y in model.support_years) / len(model.support_years))

        # Renewable generation potential (without curtailment)
        result_dict["PV_generation_uncl"] = [x / 1000 * safe_value(model.area, ("PV", district)) for x in
                                            devs["PV"]["norm_power"]]  # in kW
        result_dict["WT_generation_uncl"] = [x * safe_value(model.cap, ("WT", district)) for x in devs["WT"]["norm_power"]]  # in kW
        result_dict["STC_generation_uncl"] = [x / 1000 * safe_value(model.area, ("STC", district)) for x in
                                            devs["STC"]["norm_power"]]  # in kW

        # Calculate curtailment for renewable sources
        dt = data.time["timeResolution"] / data.time["dataResolution"]

        # PV curtailment - sum over all support years - average per year
        pv_curtailed = 0
        for y in model.support_years:
            for d in model.clusters:
                for t in model.time_steps:
                    potential = devs["PV"]["norm_power_clustered"][d][t] / 1000 * safe_value(model.area, ("PV", district))
                    actual = safe_value(model.power, ("PV", district, y, d, t))
                    pv_curtailed += (potential - actual) * param["cluster_weights"][d]
        result_dict["PV"]["curtailed"] = int(dt * pv_curtailed / len(model.support_years))

        # STC curtailment - sum over all support years - average per year
        stc_curtailed = 0
        for y in model.support_years:
            for d in model.clusters:
                for t in model.time_steps:
                    potential = devs["STC"]["norm_power_clustered"][d][t] / 1000 * safe_value(model.area, ("STC", district))
                    actual = safe_value(model.heat, ("STC", district, y, d, t))
                    stc_curtailed += (potential - actual) * param["cluster_weights"][d]
        result_dict["STC"]["curtailed"] = int(dt * stc_curtailed / len(model.support_years))

        # WT curtailment - sum over all support years - average per year
        wt_curtailed = 0
        for y in model.support_years:
            for d in model.clusters:
                for t in model.time_steps:
                    potential = devs["WT"]["norm_power_clustered"][d][t] * safe_value(model.cap, ("WT", district))
                    actual = safe_value(model.power, ("WT", district, y, d, t))
                    wt_curtailed += (potential - actual) * param["cluster_weights"][d]
        result_dict["WT"]["curtailed"] = int(dt * wt_curtailed / len(model.support_years))

        # WAT curtailment - sum over all support years - average per year
        wat_curtailed = 0
        for y in model.support_years:
            for d in model.clusters:
                for t in model.time_steps:
                    potential = min(safe_value(model.cap, (district, "WAT")), devs["WAT"]["potential"])
                    actual = safe_value(model.power, ("WAT", district, y, d, t))
                    wat_curtailed += (potential - actual) * param["cluster_weights"][d]
        result_dict["WAT"]["curtailed"] = int(dt * wat_curtailed / len(model.support_years))

        # Power profiles and maximum power - store for each support year - multi-year adaptation
        result_dict["power_profile_devs_by_year"] = {}
        result_dict["power_devs_kW_by_year"] = {}
        result_dict["power_profile_devs_kwh_by_year"] = {}
        result_dict["total_power_supply_by_year"] = {} # new  TJA
        for y in model.support_years:
            result_dict["power_profile_devs_by_year"][y] = {}
            result_dict["power_devs_kW_by_year"][y] = {}
            result_dict["power_profile_devs_kwh_by_year"][y] = {}
            result_dict["total_power_supply_by_year"][y] = {}
            for device in ["PV", "WT", "WAT", "HP", "EB", "CC", "CHP", "BCHP", "WCHP", "ELYZ", "FC", "from_grid", "to_grid", "from_network", "to_network", "from_main_grid", "to_main_grid"]: # new for network
                profile = []
                weighted_kwh = 0.0
                for d in model.clusters:
                    for t in model.time_steps:
                        val = safe_value(model.power, (device, district, y, d, t))
                        profile.append(val)
                        weighted_kwh += val * param["cluster_weights"][d]
                result_dict["power_profile_devs_by_year"][y][device] = profile
                result_dict["power_devs_kW_by_year"][y][device] = int(max(profile)) if profile else 0
                result_dict["power_profile_devs_kwh_by_year"][y][device] = round(weighted_kwh * dt, 3) # new for test reasons TJA
            result_dict["total_power_supply_by_year"][y] = sum(result_dict["power_profile_devs_kwh_by_year"][y][device]/1000 for device in ["PV", "WT", "WAT", "CHP", "BCHP", "WCHP", "FC", "from_main_grid", "from_network"]) # in MWh, new TJA

        # Heat profiles and maximum heat - store for each support year
        result_dict["heat_profile_devs_by_year"] = {}
        result_dict["heat_devs_kW_by_year"] = {}
        result_dict["heat_profile_devs_kwh_by_year"] = {} # new for test reasons TJA
        result_dict["total_heat_supply_by_year"] = {} # new  TJA
        for y in model.support_years:
            result_dict["heat_profile_devs_by_year"][y] = {}
            result_dict["heat_devs_kW_by_year"][y] = {}
            result_dict["heat_profile_devs_kwh_by_year"][y] = {}  # new for test reasons TJA
            result_dict["heat_profile_devs_by_year"][y] = {} # New TJA
            for device in ["STC", "HP", "EB", "AC", "CHP", "BOI", "GHP", "BCHP", "BBOI", "WCHP", "WBOI", "FC"]:
                profile = []
                weighted_kwh = 0.0
                for d in model.clusters:
                    for t in model.time_steps:
                        # profile.append(safe_value(model.heat, (device, district, y, d, t))) # original
                        val = safe_value(model.heat, (device, district, y, d, t)) # New TJA - for weighted sum
                        profile.append(val)
                        weighted_kwh += val * param["cluster_weights"][d]
                result_dict["heat_profile_devs_by_year"][y][device] = profile
                result_dict["heat_devs_kW_by_year"][y][device] = int(max(profile)) if profile else 0
                result_dict["heat_profile_devs_kwh_by_year"][y][device] = round(weighted_kwh * dt, 3) # new for test reasons TJA
            # Total heat generation is the sum of all device generation in MWh, new TJA 
            result_dict["total_heat_supply_by_year"][y] = sum(
                result_dict["heat_profile_devs_kwh_by_year"][y][device]/1000 
                for device in ["STC", "HP", "EB", "AC", "CHP", "BOI", "GHP", "BCHP", "BBOI", "WCHP", "WBOI", "FC"]) # in MWh, new TJA

        
        # Calculate total demand profiles (heat and power) for each support year - new TJA
        result_dict["total_heat_demand_by_year"] = {}
        result_dict["total_heat_demand_by_year_only_dem"] = {}
        result_dict["total_heat_demand_by_year_only_tes"] = {}
        result_dict["total_power_demand_by_year"] = {}
        for y in model.support_years:
            result_dict["total_heat_demand_by_year"][y] = {}
            result_dict["total_heat_demand_by_year_only_dem"][y] = {}
            result_dict["total_heat_demand_by_year_only_tes"][y] = {}
            result_dict["total_power_demand_by_year"][y] = {}
            heat_demand_for_dem = float(sum(dem["heat"][y][d][t]* param["cluster_weights"][d]/1000 for d in model.clusters for t in model.time_steps)) # in MWh, new TJA
            heat_demand_for_tes= float(sum(safe_value(model.ch, ("TES", district, y, d, t)) * param["cluster_weights"][d]/1000 for d in model.clusters for t in model.time_steps)) # in MWh, new TJA
            heat_demand_ac = float(sum(safe_value(model.heat, ("AC", district, y, d, t)) * param["cluster_weights"][d]/1000 for d in model.clusters for t in model.time_steps)) # in MWh, new TJA
            result_dict["total_heat_demand_by_year_only_dem"][y] = heat_demand_for_dem
            result_dict["total_heat_demand_by_year_only_tes"][y] = heat_demand_for_tes
            result_dict["total_heat_demand_by_year"][y] = heat_demand_for_dem + heat_demand_for_tes + heat_demand_ac

            power_demand_for_dem= float(sum(dem["power"][y][d][t]* param["cluster_weights"][d]/1000 for d in model.clusters for t in model.time_steps)) # in MWh, new TJA
            power_demand_for_devs = float(sum(result_dict["power_profile_devs_kwh_by_year"][y][device]/1000 for device in ["HP", "EB", "CC", "ELYZ", "to_network", "to_main_grid"])) # in MWh, new TJA
            power_battery_charging = float(sum(safe_value(model.ch, ("BAT", district, y, d, t)) * param["cluster_weights"][d]/1000 for d in model.clusters for t in model.time_steps)) # in MWh, new TJA
            result_dict["total_power_demand_by_year"][y] = power_demand_for_dem +power_demand_for_devs + power_battery_charging

        # # Calculate LCOE - new TJA
        result_dict["LCOE_by_year"] = {}
        for y in model.support_years:
            result_dict["LCOE_by_year"][y] = {}
            result_dict["LCOE_by_year"][y] = (
                result_dict["tac_per_distr_year"][y] / 
                (result_dict["total_power_supply_by_year"][y] + result_dict["total_heat_supply_by_year"][y])) # EUR/MWh, new TJA

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
                        profile.append(safe_value(model.cool, (device, district, y, d, t)))
                result_dict["cool_profile_by_year"][y][device] = profile
                result_dict["cool_kW_by_year"][y][device] = int(max(profile)) if profile else 0

        # Area usage
        result_dict["area"] = {}
        for device in ["PV", "STC"]:
            result_dict["area"][device] = int(safe_value(model.area, (device, district)))

        # Calculate annual generation for each device type
        eps = 0.01

        # Heat generation
        for k in model.heat_devs:
            gen_kwh = dt * sum(safe_value(model.heat, (k, district, d, t)) * param["cluster_weights"][d]
                            for d in model.clusters for t in model.time_steps)
            result_dict[k]["gen_kWh"] = gen_kwh
            result_dict[k]["gen"] = int(gen_kwh / 1000)  # MWh

        # Cooling generation
        for k in ["CC", "AC"]:
            gen_kwh = dt * sum(safe_value(model.cool, (k, district, d, t)) * param["cluster_weights"][d]
                            for d in model.clusters for t in model.time_steps)
            result_dict[k]["gen_kWh"] = gen_kwh
            result_dict[k]["gen"] = int(gen_kwh / 1000)  # MWh

        # Power generation
        for k in ["PV", "WT", "WAT", "CHP", "BCHP", "WCHP", "ELYZ", "FC"]:
            gen_kwh = dt * sum(safe_value(model.power, (k, district, d, t)) * param["cluster_weights"][d]
                            for d in model.clusters for t in model.time_steps)
            result_dict[k]["gen_kWh"] = gen_kwh
            result_dict[k]["gen"] = int(gen_kwh / 1000)  # MWh

        # Special: Hydrogen generation for ELYZ
        h2_gen = dt * sum(safe_value(model.power, ("ELYZ", district, d, t)) * devs["ELYZ"]["eta_el"] * param["cluster_weights"][d]
                        for d in model.clusters for t in model.time_steps)
        result_dict["ELYZ"]["gen_H2"] = int(h2_gen / 1000)  # MWh

        # Gas generation for SAB
        for k in ["SAB"]:
            gen_kwh = dt * sum(safe_value(model.gas, (k, district, d, t)) * param["cluster_weights"][d]
                            for d in model.clusters for t in model.time_steps)
            result_dict[k]["gen_kWh"] = gen_kwh
            result_dict[k]["gen"] = int(gen_kwh / 1000)  # MWh


        # Calculate full load hours
        for k in ["PV", "WT", "WAT", "STC", "HP", "EB", "CC", "AC", "CHP", "BOI", "GHP", "BCHP", "BBOI", "WCHP", "WBOI",
                "ELYZ", "FC", "SAB"]:
            cap_k = safe_value(model.cap, (k, district))
            if cap_k > eps:
                result_dict[k]["hrs"] = int(result_dict[k]["gen_kWh"] / cap_k)
            else:
                result_dict[k]["hrs"] = 0

        # Select technologies that are installed
        for k in model.all_devs:
            result_dict[k]["inst"] = safe_value(model.cap, (k, district)) > eps

        # Calculate charge cycles of storages
        for k in ["TES", "CTES", "BAT", "H2S", "GS"]:
            cap_k = safe_value(model.cap, (k, district))
            if cap_k > eps:
                charge_cycles = dt * sum(abs(safe_value(model.ch, (k, district, d, t))) / 2 * param["cluster_weights"][d]
                                        for d in model.clusters for t in model.time_steps)
                result_dict[k]["chc"] = int(charge_cycles / cap_k)
            else:
                result_dict[k]["chc"] = 0

        # Calculate volume of thermal storages
        for k in ["TES", "CTES"]:
            cap_k = safe_value(model.cap, (k, district))
            if cap_k > eps:
                result_dict[k]["vol_liter"] = round(
                    cap_k / (param["c_w"] * param["rho_w"] * devs[k]["delta_T"]) * 3600 * 1000, 1)
            else:
                result_dict[k]["vol_liter"] = 0

            # Storage state of charge and charging power
        for dev in model.storage_devs:
            # Maximum SOC (across all support years)
            max_soc = max(safe_value(model.soc, (dev, district, y, day_y, t)) for y in model.support_years for day_y in model.year for t in model.time_steps)
            result_dict[dev]["soc"] = int(max_soc)

            # Maximum charging power (across all support years)
            max_ch = max(safe_value(model.ch, (dev, district, y, d, t)) for y in model.support_years for d in model.clusters for t in model.time_steps)
            result_dict[dev]["ch"] = int(max_ch)

        # Calculate detailed CO2 emissions by source (weighted sum over all support years with year-specific factors)
        result_dict["total_co2_el"] = sum(safe_value(model.from_el_main_grid_total, (y, district)) * param["co2_el_grid"][y] * weights[district][y] for y in model.support_years) / 1000 # t/a # new for network
        result_dict["total_co2_el_feed_in"] = sum(safe_value(model.to_el_main_grid_total, (y, district)) * param["co2_el_feed_in"][y] * weights[district][y] for y in model.support_years) / 1000  # t/a # new for network
        result_dict["total_co2_gas"] = int(sum(safe_value(model.from_gas_grid_total, (y, district)) * param["co2_gas"][y] * weights[district][y] for y in model.support_years) / 1000)  # t/a
        result_dict["total_co2_gas_feed_in"] = int(sum(safe_value(model.to_gas_grid_total, (y, district)) * param["co2_gas_feed_in"][y] * weights[district][y] for y in model.support_years) / 1000)  # t/a
        result_dict["total_co2_biom"] = int(sum(safe_value(model.biom_import_total, (y, district)) * param["co2_biom"][y] * weights[district][y] for y in model.support_years) / 1000)  # t/a
        result_dict["total_co2_waste"] = int(sum(safe_value(model.waste_import_total, (y, district)) * param["co2_waste"][y] * weights[district][y] for y in model.support_years) / 1000)  # t/a
        result_dict["total_co2_hydrogen"] = int(sum(safe_value(model.hydrogen_import_total, (y, district)) * param["co2_hydrogen"][y] * weights[district][y] for y in model.support_years) / 1000)  # t/a

    return result_dictCon


def save_results_csv_short(model, result_dict, scenario_name, result_dir, all_devs_list, param):
    """
    Save results to CSV file in a long format for easier analysis and visualization.
    """
    os.makedirs(result_dir, exist_ok=True)
    csv_file_path = os.path.join(result_dir, f"{scenario_name}_network_results_short.csv")

    rows = []

    def add(category, metric, value, unit="", device="", year=""):
        rows.append({
            "scenario": scenario_name,
            "category": category,
            "metric": metric,
            "device": device,
            "year": year,
            "value": value if value is not None else "",
            "unit": unit
        })
    # 1) Optimization results
    add("optimization", "tac_distr", result_dict.get("tac_sum_distr", ""), "EUR/a")
    add("optimization", "co2_distr", result_dict.get("co2_sum_distr", ""), "t/a")
    for y in model.support_years:
        add("optimization", "tac_per_distr_year", result_dict.get("tac_per_distr_year", {}).get(y, ""), "EUR/a", year=y)
        add("optimization", "co2_sum_distr_year", result_dict.get("co2_sum_distr_by_year", {}).get(y, ""), "t/a", year=y) 

    # 2) Cost parameters
    add("cost", "total_annual_costs_devices", result_dict.get("total_annual_costs_devices", ""), "EUR/a")
    add("cost", "total_connection_costs", result_dict.get("total_connection_costs", ""), "EUR/a")
    add("cost", "heat_grid_costs", result_dict.get("heat_grid_costs", ""), "EUR/a")
    add("cost", "heat_grid_costs_base", result_dict.get("heat_grid_costs_base", ""), "EUR/a")
    add("cost", "annualized_energy_costs", result_dict.get("annualized_energy_costs", ""), "EUR/a")
    add("cost", "annualized_misc_costs", result_dict.get("annualized_misc_costs", ""), "EUR/a")

    # 3) Devices parameters
    for device in all_devs_list:
        if result_dict.get(device, {}).get("inst", False):
            cap = result_dict.get(device, {}).get("cap", "")
            if device in ["WT", "WAT", "CHP", "BOI", "HP", "EB", "CC", "AC", "GHP", "BCHP", "BBOI", "WCHP", "WBOI", "ELYZ", "FC", "SAB", "PV", "STC"]:
                add("device", "capacity", cap, "kW", device=device)
            elif device in ["TES", "CTES", "BAT", "H2S", "GS"]:
                add("device", "capacity", cap, "kWh", device=device)
     # 4) Yearly totals (all carriers)
    yearly_maps = [
        ("from_el_grid_total_by_year", "from_el_grid_total", "MWh"),
        ("to_el_grid_total_by_year", "to_el_grid_total", "MWh"),
        ("from_el_main_grid_total_by_year", "from_el_main_grid_total", "MWh"),
        ("to_el_main_grid_total_by_year", "to_el_main_grid_total", "MWh"),
        ("from_network_total_by_year", "from_network_total", "MWh"),
        ("to_network_total_by_year", "to_network_total", "MWh"),
        ("from_gas_grid_total_by_year", "from_gas_grid_total", "MWh"),
        ("to_gas_grid_total_by_year", "to_gas_grid_total", "MWh"),
    ]
    for map_key, metric, unit in yearly_maps:
        for y in model.support_years:
            add("yearly_totals", metric, result_dict.get(map_key, {}).get(y, ""), unit, year=y)

    # Write CSV
    with open(csv_file_path, mode="w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=["scenario", "category", "metric", "device", "year", "value", "unit"],
            delimiter=";"
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"Results saved to {csv_file_path}")


def save_results_csv(model, result_dict, scenario_name, result_dir, all_devs_list, param):
    """
    Save results to CSV file in a long format for easier analysis and visualization.
    """
    os.makedirs(result_dir, exist_ok=True)
    csv_file_path = os.path.join(result_dir, f"{scenario_name}_network_results.csv")

    rows = []

    def add(category, metric, value, unit="", device="", year=""):
        rows.append({
            "scenario": scenario_name,
            "category": category,
            "metric": metric,
            "device": device,
            "year": year,
            "value": value if value is not None else "",
            "unit": unit
        })

    # 1) Optimization results
    add("optimization", "tac_distr", result_dict.get("tac_sum_distr", ""), "EUR/a")
    add("optimization", "co2_distr", result_dict.get("co2_sum_distr", ""), "t/a")
    for y in model.support_years:
        add("optimization", "tac_per_distr_year", result_dict.get("tac_per_distr_year", {}).get(y, ""), "EUR/a", year=y)
        add("optimization", "co2_sum_distr_year", result_dict.get("co2_sum_distr_by_year", {}).get(y, ""), "t/a", year=y) 
        add("optimization", "LCOE_year", result_dict.get("LCOE_by_year", {}).get(y, ""), "EUR/MWh", year=y)

    # 2) Cost parameters
    for k, u in [
        ("co2_tax_total", "EUR/a"),
        ("total_inv_cost", "EUR/a"),
        ("total_inv_cost_unsubsidized", "EUR/a"),
        ("total_ann_inv_cost", "EUR/a"),
        ("total_ann_inv_cost_unsubsidized", "EUR/a"),
        ("total_om_cost", "EUR/a"),
        ("supply_costs_el", "EUR/a"),
        ("cap_costs_el", "EUR/a"),
        ("total_el_costs", "EUR/a"),
        ("rev_feed_in_el", "EUR/a"),
        ("supply_costs_gas", "EUR/a"),
        ("cap_costs_gas", "EUR/a"),
        ("total_gas_costs", "EUR/a"),
        ("rev_feed_in_gas", "EUR/a"),
        ("supply_costs_biom", "EUR/a"),
        ("supply_costs_waste", "EUR/a"),
        ("supply_costs_hydrogen", "EUR/a"),
    ]:
        add("cost", k, result_dict.get(k, ""), u)

    # 3) CO2 parameters
    for k, u in [
        ("co2_onsite_emissions", "t/a"),
        ("co2_credit_feedin", "t/a"),
        ("total_co2_el", "t/a"),
        ("total_co2_el_feed_in", "t/a"),
        ("total_co2_gas", "t/a"),
        ("total_co2_gas_feed_in", "t/a"),
        ("total_co2_biom", "t/a"),
        ("total_co2_waste", "t/a"),
        ("total_co2_hydrogen", "t/a"),
    ]:
        add("co2", k, result_dict.get(k, ""), u)

    # 4) Grid flows + maxima
    for k, u in [
        ("from_el_grid_total", "MWh"),
        ("to_el_grid_total", "MWh"),
        ("from_el_main_grid_total", "MWh"),
        ("to_el_main_grid_total", "MWh"),
        ("from_network_total", "MWh"),
        ("to_network_total", "MWh"),
        ("from_gas_grid_total", "MWh"),
        ("to_gas_grid_total", "MWh"),
        ("biom_import_total", "MWh"),
        ("waste_import_total", "MWh"),
        ("hydrogen_import_total", "MWh"),
        ("max_el_from_grid", "kW"),
        ("max_el_to_grid", "kW"),
        ("max_el_from_main_grid", "kW"),
        ("max_el_to_main_grid", "kW"),
        ("max_el_from_network", "kW"),
        ("max_el_to_network", "kW"),
        ("max_gas_from_grid", "kW"),
        ("max_gas_to_grid", "kW"),
        ("max_biom", ""),
        ("max_waste", ""),
        ("max_hydrogen", ""),
    ]:
        add("grid", k, result_dict.get(k, ""), u)

    # 5) Areas
    add("area", "PV", result_dict.get("area", {}).get("PV", ""), "qm", device="PV")
    add("area", "STC", result_dict.get("area", {}).get("STC", ""), "qm", device="STC")

    # 6) Storage volumes
    add("storage_volume", "vol_liter", result_dict.get("TES", {}).get("vol_liter", ""), "l", device="TES")
    add("storage_volume", "vol_liter", result_dict.get("CTES", {}).get("vol_liter", ""), "l", device="CTES")

    # 7) Device capacity + costs 
    for device in all_devs_list:
        if result_dict.get(device, {}).get("inst", False):
            cap = result_dict.get(device, {}).get("cap", "")
            if device in ["WT", "WAT", "CHP", "BOI", "HP", "EB", "CC", "AC", "GHP", "BCHP", "BBOI", "WCHP", "WBOI", "ELYZ", "FC", "SAB", "PV", "STC"]:
                add("device", "capacity", cap, "kW", device=device)
            elif device in ["TES", "CTES", "BAT", "H2S", "GS"]:
                add("device", "capacity", cap, "kWh", device=device)

            add("device_cost", "inv", result_dict.get(device, {}).get("inv", ""), "EUR", device=device)
            add("device_cost", "inv_unsubsidized", result_dict.get(device, {}).get("inv_unsubsidized", ""), "EUR", device=device)
            add("device_cost", "ann_inv", result_dict.get(device, {}).get("ann_inv", ""), "EUR/a", device=device)
            add("device_cost", "ann_inv_unsubsidized", result_dict.get(device, {}).get("ann_inv_unsubsidized", ""), "EUR/a", device=device)
            add("device_cost", "om_cost", result_dict.get(device, {}).get("om_cost", ""), "EUR/a", device=device)


    # 8) Peak demands
    add("peak", "peak_heat_uncl", param.get("peak_heat", ""), "kW")
    add("peak", "peak_power_uncl", param.get("peak_power", ""), "kW")
    add("peak", "peak_heat_cl", result_dict.get("max_heat_demand", 0), "kW")
    add("peak", "peak_power_cl", result_dict.get("max_power_demand", 0), "kW")

    # 9) Heat profile energy by year
    for y in model.support_years:
        for dev in model.heat_devs:
            add("heat_profile_energy_by_year", "heat_profile_energy_kwh",
                result_dict.get("heat_profile_devs_kwh_by_year", {}).get(y, {}).get(dev, ""),
                "kWh", device=dev, year=y)
            add("heat_profile_devs_by_year", "heat_kW",
                result_dict.get("heat_devs_kW_by_year", {}).get(y, {}).get(dev, ""),
                "kW", device=dev, year=y)
        add("tes_charge_loss_by_year", "tes_charge_loss_kwh",
             result_dict.get("tes_charge_loss_by_year", {}).get(y, ""),             
             "MWh", device="TES", year=y)

            
    # 10) Power profile energy + peak by year
    for y in model.support_years:
        for dev in model.power_devs:
            add("power_profile_devs_by_year", "power_profile_energy_kwh",
                result_dict.get("power_profile_devs_kwh_by_year", {}).get(y, {}).get(dev, ""),
                "kWh", device=dev, year=y)
            add("power_profile_devs_by_year", "power_kW",
                result_dict.get("power_devs_kW_by_year", {}).get(y, {}).get(dev, ""),
                "kW", device=dev, year=y)

    # 11) Yearly totals (all carriers)
    yearly_maps = [
        ("from_el_grid_total_by_year", "from_el_grid_total", "MWh"),
        ("to_el_grid_total_by_year", "to_el_grid_total", "MWh"),
        ("from_el_main_grid_total_by_year", "from_el_main_grid_total", "MWh"),
        ("to_el_main_grid_total_by_year", "to_el_main_grid_total", "MWh"),
        ("from_network_total_by_year", "from_network_total", "MWh"),
        ("to_network_total_by_year", "to_network_total", "MWh"),
        ("from_gas_grid_total_by_year", "from_gas_grid_total", "MWh"),
        ("to_gas_grid_total_by_year", "to_gas_grid_total", "MWh"),
        ("biom_import_total_by_year", "biom_import_total", "MWh"),
        ("waste_import_total_by_year", "waste_import_total", "MWh"),
        ("hydrogen_import_total_by_year", "hydrogen_import_total", "MWh"),
        ("total_heat_demand_by_year", "total_heat_demand_by_year", "MWh"),
        ("total_heat_demand_by_year_only_dem", "total_heat_demand_by_year_only_dem", "MWh"),
        ("total_heat_demand_by_year_only_tes", "total_heat_demand_by_year_only_tes", "MWh"),
        ("total_power_demand_by_year", "total_power_demand_by_year", "MWh"),
        ("total_heat_supply_by_year", "total_heat_supply_by_year", "MWh"),
        ("total_power_supply_by_year", "total_power_supply_by_year", "MWh"),
        
    ]
    for map_key, metric, unit in yearly_maps:
        for y in model.support_years:
            add("yearly_totals", metric, result_dict.get(map_key, {}).get(y, ""), unit, year=y)

    # Write CSV
    with open(csv_file_path, mode="w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=["scenario", "category", "metric", "device", "year", "value", "unit"],
            delimiter=";"
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"Results saved to {csv_file_path}")



 


def save_heat_timeseries_csv(model, result_dict, district, device, result_dir):    
    # Ensure the result directory exists
    os.makedirs(result_dir, exist_ok=True)
    
    # Define the output file path
    csv_file_path = os.path.join(result_dir, f"{district}_{device}_heat_timeseries.csv")
    
    # Helper function for safe value retrieval
    def safe_value(var_container, index):
        try:
            val = pyo.value(var_container[index])
            return val if val is not None else 0
        except (KeyError, ValueError):
            return 0
    
    # Prepare the data
    data_to_save = [
        ["Support_Year", "Cluster", "Timestep", "Heat_kW"]  # Header row
    ]
    
    # Iterate over all support years, clusters, and timesteps
    for y in model.support_years:
        for d in model.clusters:
            for t in model.time_steps:
                heat_value = safe_value(model.heat, (device, district, y, d, t))
                data_to_save.append([y, d, t, round(heat_value, 3)])
    
    # Write the data to the CSV file
    with open(csv_file_path, mode="w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file, delimiter=";")
        writer.writerows(data_to_save)
    
    print(f"Heat timeseries for {device} in {district} saved to {csv_file_path}")

def save_demand_heat_timeseries_csv(dem, model, district, result_dir):
        # Ensure the result directory exists
    os.makedirs(result_dir, exist_ok=True)
    
    
    # Define the output file path
    csv_file_path = os.path.join(result_dir, f"{district}_demand_heat_timeseries.csv")
    
    # Prepare the data
    data_to_save = [
        ["Support_Year", "Cluster", "Timestep", "Heat_Demand_kW"]  # Header row
    ]
    
    # Iterate over all support years, clusters, and timesteps
    for y in model.support_years:
        for d in model.clusters:
            for t in model.time_steps:
                heat_demand = dem["heat"][y][d][t]
                data_to_save.append([y, d, t, round(heat_demand, 3)])
    
    # Write the data to the CSV file
    with open(csv_file_path, mode="w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file, delimiter=";")
        writer.writerows(data_to_save)
    
    print(f"Heat demand timeseries for {district} saved to {csv_file_path}")
    
def save_demand_power_timeseries_csv(dem, model, district, result_dir):
        # Ensure the result directory exists
    os.makedirs(result_dir, exist_ok=True)
    
    
    # Define the output file path
    csv_file_path = os.path.join(result_dir, f"{district}_demand_power_timeseries.csv")
    
    # Prepare the data
    data_to_save = [
        ["Support_Year", "Cluster", "Timestep", "Power_Demand_kW"]  # Header row
    ]
    
    # Iterate over all support years, clusters, and timesteps
    for y in model.support_years:
        for d in model.clusters:
            for t in model.time_steps:
                power_demand = dem["power"][y][d][t]
                data_to_save.append([y, d, t, round(power_demand, 3)])
    
    # Write the data to the CSV file
    with open(csv_file_path, mode="w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file, delimiter=";")
        writer.writerows(data_to_save)
    
    print(f"Power demand timeseries for {district} saved to {csv_file_path}")


# def save_network_power_timeseries_csv(model, result_dir):
#     """
#     Saves power timeseries for to_network and from_network for all districts.
    
#     Parameters
#     ----------
#     model : pyomo.ConcreteModel
#         The solved optimization model.
#     result_dir : str
#         Directory where the CSV files will be saved.
        
#     Returns
#     -------
#     None
#     """
#     # Ensure the result directory exists
#     os.makedirs(result_dir, exist_ok=True)
    
#     # Helper function for safe value retrieval
#     def safe_value(var_container, index):
#         try:
#             val = pyo.value(var_container[index])
#             return val if val is not None else 0
#         except (KeyError, ValueError):
#             return 0
    
#     # Save timeseries for each district
#     for district in model.districts:
#         # Define the output file path
#         csv_file_path = os.path.join(result_dir, f"{district}_network_and_main_grid_power_timeseries.csv")
        
#         # Prepare the data
#         data_to_save = [
#             ["Support_Year", "Cluster", "Timestep", "to_network_kW", "from_network_kW", "to_main_grid_kW", "from_main_grid_kW", "to_grid_kW", "from_grid_kW"]  # Header row
#         ]
        
#         # Iterate over all support years, clusters, and timesteps
#         for y in model.support_years:
#             for d in model.clusters:
#                 for t in model.time_steps:
#                     to_network_value = safe_value(model.power, ("to_network", district, y, d, t))
#                     from_network_value = safe_value(model.power, ("from_network", district, y, d, t))
#                     to_main_grid_value = safe_value(model.power, ("to_main_grid", district, y, d, t))
#                     from_main_grid_value = safe_value(model.power, ("from_main_grid", district, y, d, t))
#                     to_grid_value = safe_value(model.power, ("to_grid", district, y, d, t))
#                     from_grid_value = safe_value(model.power, ("from_grid", district, y, d, t))
#                     data_to_save.append([y, d, t, round(to_network_value, 3), round(from_network_value, 3), round(to_main_grid_value, 3), round(from_main_grid_value, 3), round(to_grid_value, 3), round(from_grid_value, 3)])
        
#         # Write the data to the CSV file
#         with open(csv_file_path, mode="w", newline="", encoding="utf-8") as csv_file:
#             writer = csv.writer(csv_file, delimiter=";")
#             writer.writerows(data_to_save)
        
#         print(f"Network and main grid power timeseries for {district} saved to {csv_file_path}")

