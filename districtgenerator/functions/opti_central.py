#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created 26.02.2024
@author: Joel Schölzel
ORIGINAL GUROBI VERSION ADJUSTED FOR PYOMO USAGE
"""

import pyomo.environ as pyo
from pyomo.util.infeasible import log_infeasible_constraints
import sys
import os
from io import StringIO
import time
import districtgenerator.functions.solver_config as solver_config
from datetime import datetime
import logging

# Sets of energy conversion systems in the buildings
ECS_HEAT = ("HP", "EH", "CHP", "BOI", "BBOI", "OBOI", "H2BOI", "STC", "DH", "heat_grid", "DHW_dem", "Heating_dem", "FC")
ECS_COOL = ("CC", "heat_grid", "Cooling_dem") #! heat_grid correct? Should this be cooling grid for better understanding?
ECS_POWER = ("HP", "EH", "CC", "CHP", "PV", "Elec_dem", "FC")  # power consuming/producing devices
ECS_GAS = ("CHP", "BOI")  # gas consuming devices
ECS_BIOMASS = ("BBOI",)  # biomass consuming devices
ECS_HYDROGEN = ("H2BOI", "FC")  # hydrogen consuming devices
ECS_OIL = ("OBOI",)  # oil consuming devices
ECS_STORAGE = ("BAT", "TES")  # battery (BAT), thermal energy storage (TES)
HP_MODI = ("HP35", "HP55")  # modi of the HP with different HP supply temperatures in °C

# Create set for energy hub devices
EH_DEVS = ["PV", "WT", "STC", "WAT",
           "HP", "EB", "CC", "AC",
           "CHP", "BOI", "GHP",
           "BCHP", "BBOI", "WCHP", "WBOI",
           "ELYZ", "FC", "H2S", "SAB",
           "TES", "CTES", "BAT", "GS",
           ]

EH_ECS_HEAT = ("STC", "HP", "EB", "AC", "CHP", "BOI", "GHP", "BCHP", "BBOI", "WCHP", "WBOI", "FC", "to_grid")
EH_ECS_COOL = ("CC", "AC", "to_grid")
EH_ECS_POWER = ("PV", "WT", "WAT", "HP", "EB", "CC", "CHP", "BCHP", "WCHP", "ELYZ", "FC", "from_grid", "to_grid")
EH_ECS_GAS = ("CHP", "BOI", "GHP", "SAB")
EH_ECS_BIOMASS = ("BCHP", "BBOI")
EH_ECS_HYDROGEN = ("ELYZ", "FC", "SAB", "from_neighborhood", "to_neighborhood")
EH_ECS_OIL = ()
EH_ECS_STORAGE = ("TES", "CTES", "BAT", "H2S", "GS")
EH_ECS_WASTE = ("WCHP", "WBOI", "import")

BIG_M = 1e8  # big M for linearization of product of binary and continuous variable


def run_opti_central(model, data, cluster):
    """
    This function runs the optimization for the clusters to determine the optimal operation of the energy devices in a district.
    """

    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s - %(name)s - %(message)s',
        handlers=[
            logging.StreamHandler(),  # Console output
            # Optional: logging.FileHandler('optimization_debug.log')  # File output
        ]
    )

    start_time = time.time()
    # build the model
    build_model(model, data, cluster)
    model_building_time = time.time() - start_time
    # solve the model and extract results
    results_dict = solve_model_and_extract_results(model, data)
    model_solve_time = time.time() - start_time - model_building_time
    # calculate total time
    total_time = time.time() - start_time

    # maybe record the times into a log file

    # print(f"\n Time needed for building the model: {model_building_time:.2f} seconds.")
    # print(f" Time needed for solving the model: {model_solve_time:.2f} seconds.")
    # print(f" Total time needed: {total_time:.2f} seconds.")

    return results_dict


def build_model(model, data, cluster):
    """
    Builds the Pyomo model for the optimization of energy systems in a district.
    """
    timeData = data.time
    ecoData = data.ecoData
    siteData = data.site
    param_dec_devs = data.decentral_device_data
    model_param_eh = data.params_ehdo_model
    central_device_data = data.central_device_data
    buildingData = data.district
    energyHubData = data.centralDevices
    heatingNetworkData = data.heat_grid_data

    ################################################################################
    # Setting up the model
    ################################################################################

    # number of buildings in neighborhood
    nbuildings = len(buildingData)
    time_steps = range(int(timeData["clusterLength"] / timeData["timeResolution"]))
    dt = timeData["timeResolution"] / timeData["dataResolution"]
    last_time_step = len(time_steps) - 1

    T_e = siteData["T_e_cluster"][cluster]  # ambient temperature [°C]

    try:
        network_losses_heating = heatingNetworkData["total_losses_heating_network_cluster"][cluster] * 1000  # W
        network_losses_cooling = heatingNetworkData["total_losses_cooling_network_cluster"][cluster] * 1000  # W
    except:
        network_losses_heating = [0] * T_e
        network_losses_cooling = [0] * T_e

    Q_DHW = {}  # DHW (domestic hot water) demand [W]
    Q_heating = {}  # space heating [W]
    Q_cooling = {}  # space cooling [W]
    PV_gen = {}  # electricity generation of PV [W]
    STC_heat = {}  # electricity generation of PV [W]
    elec_dem = {}  # electricity demand for appliances and lighting [W]
    occ = {}

    # Load the time series for each building
    for n in range(nbuildings):
        Q_DHW[n] = buildingData[n]["user"].dhw_cluster[cluster]
        Q_heating[n] = buildingData[n]["user"].heat_cluster[cluster]
        Q_cooling[n] = buildingData[n]["user"].cooling_cluster[cluster]
        elec_dem[n] = buildingData[n]["user"].elec_cluster[cluster]
        occ[n] = buildingData[n]["user"].occ_cluster[cluster]
        try:
            PV_gen[n] = buildingData[n]["generationPV_cluster"][cluster]
            STC_heat[n] = buildingData[n]["generationSTC_cluster"][cluster]
        except:
            PV_gen[n] = [0] * len(elec_dem[n])
            STC_heat[n] = [0] * len(elec_dem[n])

    # INITIAL STATE OF CHARGE OF THE STORAGES (Wh) for all buildings
    soc_init = {}
    for dev in ECS_STORAGE:
        soc_init[dev] = {}
        for n in range(nbuildings):
            soc_init[dev][n] = buildingData[n]["capacities"][dev] * param_dec_devs[dev]["init"]  # Wh

    # Extracting the data for each individual evs in the buildings
    all_individual_evs = []
    all_individual_ices = []
    ev_counter = 0
    ice_counter = 0

    for n in range(nbuildings):
        building = buildingData[n]
        charging_type = building["buildingFeatures"]["ev_charging"]

        if hasattr(building["user"], 'individual_car_profiles_cluster'):
            for car_cluster_profile in building["user"].individual_car_profiles_cluster:
                if car_cluster_profile["type"] == "EV":
                    availability_profile = car_cluster_profile["availability_profile_cluster"][cluster]
                    driving_demand_wh = car_cluster_profile["consumption_profile_wh_cluster"][cluster]
                    battery_capacity_wh = car_cluster_profile["battery_capacity_wh"]
                    on_demand_charging_profile = car_cluster_profile["on_demand_charging_profile_w_cluster"][cluster]

                    all_individual_evs.append({
                        'id': ev_counter,
                        'building_id': n,
                        'car_id_str': car_cluster_profile.get("car_id", f"ev_{ev_counter}"),
                        'charging_type': charging_type,
                        'availability': availability_profile,
                        "driving_demand_wh": driving_demand_wh,
                        "on_demand_charging_profile": on_demand_charging_profile,
                        "battery_capacity_wh": battery_capacity_wh,
                        "max_ch_power": battery_capacity_wh * param_dec_devs["EV"]["coeff_ch"],
                        "max_dch_power": battery_capacity_wh * param_dec_devs["EV"]["coeff_ch"]
                    })
                    ev_counter += 1

                elif car_cluster_profile["type"] == "ICE":
                    #TODO: add ICE vehicles if needed in the future -> Needs to be included for emission calculations and Fuel cost.
                    pass

    ev_data = {ev['id']: ev for ev in all_individual_evs}

    # initial SOC for each EV
    soc_init_ev = {
        ev["id"]: ev["battery_capacity_wh"] * param_dec_devs["EV"]["init"]
        for ev in all_individual_evs
    }

    # TODO: HERE noch einmal überarbeiten

    ################################################################################
    # CREATE SETS
    ################################################################################

    model.t = pyo.Set(initialize=time_steps, doc="")
    model.n = pyo.Set(initialize=range(nbuildings), doc="Buildings in the neighborhood")
    model.days = pyo.Set(initialize=[0, 1, 2, 3, 4, 5, 6], doc="")

    # Buildings
    model.ecs_heat = pyo.Set(initialize=ECS_HEAT, doc="Heat generating or consuming devices in the buildings")
    model.ecs_cool = pyo.Set(initialize=ECS_COOL, doc="Cooling generating or consuming devices in the buildings")
    model.ecs_power = pyo.Set(initialize=ECS_POWER, doc="Power generating or consuming devices in the buildings")
    model.ecs_gas = pyo.Set(initialize=ECS_GAS, doc="Gas generating or consuming devices in the buildings")
    model.ecs_biomass = pyo.Set(initialize=ECS_BIOMASS, doc="Biomass generating or consuming devices in the buildings")
    model.ecs_hydrogen = pyo.Set(initialize=ECS_HYDROGEN, doc="Hydrogen generating or consuming devices in the buildings")
    model.ecs_oil = pyo.Set(initialize=ECS_OIL, doc="Oil generating or consuming devices in the buildings")
    model.ecs_storage = pyo.Set(initialize=ECS_STORAGE, doc="Storage devices in the buildings")
    model.hp_modi = pyo.Set(initialize=HP_MODI, doc="Heat pump modi with different supply temperatures for domestic heatpumps")
    model.EVs = pyo.Set(initialize=ev_data.keys(), doc="Individual electric vehicles in the buildings")

    # Energy hub
    model.eh_devs = pyo.Set(initialize=EH_DEVS, doc="Energy hub devices")
    model.eh_ecs_heat = pyo.Set(initialize=EH_ECS_HEAT, doc="Heat generating or consuming devices in the energy hub")
    model.eh_ecs_cool = pyo.Set(initialize=EH_ECS_COOL, doc="Cooling generating or consuming devices in the energy hub")
    model.eh_ecs_power = pyo.Set(initialize=EH_ECS_POWER, doc="Power generating or consuming devices in the energy hub")
    model.eh_ecs_gas = pyo.Set(initialize=EH_ECS_GAS, doc="Gas generating or consuming devices in the energy hub")
    model.eh_ecs_biomass = pyo.Set(initialize=EH_ECS_BIOMASS, doc="Biomass generating or consuming devices in the energy hub")
    model.eh_ecs_hydrogen = pyo.Set(initialize=EH_ECS_HYDROGEN, doc="Hydrogen generating or consuming devices in the energy hub")
    model.eh_ecs_oil = pyo.Set(initialize=EH_ECS_OIL, doc="Oil generating or consuming devices in the energy hub")
    model.eh_ecs_storage = pyo.Set(initialize=EH_ECS_STORAGE, doc="Storage devices in the energy hub")
    model.eh_ecs_waste = pyo.Set(initialize=EH_ECS_WASTE, doc="Waste generating or consuming devices in the energy hub")

    ################################################################################
    # CREATE VARIABLES
    ################################################################################

    ################################################################################
    # OPERATIONAL BUILDING VARIABLES
    ################################################################################
    model.power_dom = pyo.Var(model.ecs_power, model.n, model.t, within=pyo.NonNegativeReals,
                              doc="Electrical power to/from domestic devices")
    model.heat_dom = pyo.Var(model.ecs_heat, model.n, model.t, within=pyo.NonNegativeReals,
                             doc="Heat to/from domestic devices")
    model.cool_dom = pyo.Var(model.ecs_cool, model.n, model.t, within=pyo.NonNegativeReals,
                             doc="Cooling to/from domestic devices")
    model.gas_dom = pyo.Var(model.ecs_gas, model.n, model.t, within=pyo.NonNegativeReals,
                            doc="Gas to/from domestic devices")
    model.biomass_dom = pyo.Var(model.ecs_biomass, model.n, model.t, within=pyo.NonNegativeReals,
                                doc="Biomass to/from domestic devices")
    model.hydrogen_dom = pyo.Var(model.ecs_hydrogen, model.n, model.t, within=pyo.NonNegativeReals,
                                 doc="Hydrogen to/from domestic devices")
    model.oil_dom = pyo.Var(model.ecs_oil, model.n, model.t, within=pyo.NonNegativeReals,
                            doc="Oil to/from domestic devices")
    model.dh_heat_supply = pyo.Var(model.n, model.t, within=pyo.NonNegativeReals, doc="Heat supplied by the district heating network to the buildings") # Heat supplied by district heating network

    # Heat pump modi
    model.power_mode = pyo.Var(model.hp_modi, model.n, model.t, within=pyo.NonNegativeReals)
    model.heat_mode = pyo.Var(model.hp_modi, model.n, model.t, within=pyo.NonNegativeReals)

    # Storage variables
    model.soc_dom = pyo.Var(model.ecs_storage, model.n, model.t, within=pyo.NonNegativeReals,
                            doc="State of charge of domestic storage devices")  # State of charge of storage devices
    model.ch_dom = pyo.Var(model.ecs_storage, model.n, model.t, within=pyo.NonNegativeReals,
                           doc="Charging power of domestic storage devices")  # Charging power of storage devices
    model.dch_dom = pyo.Var(model.ecs_storage, model.n, model.t, within=pyo.NonNegativeReals,
                            doc="Discharging power of domestic storage devices")  # Discharging power of storage devices

    # Residual building demands (in kW)  [Sum for each building of all devices]
    model.res_dom_power = pyo.Var(model.n, model.t, within=pyo.NonNegativeReals,
                                  doc="Residual power demand of buildings")  # Only pos demand allowed
    model.res_dom_feed = pyo.Var(model.n, model.t, within=pyo.NonNegativeReals,
                                 doc="Residual feed-in of buildings")  # Only pos feed-in allowed

    # binary variable for each house to avoid simultaneous feed-in and purchase of electric energy
    model.binary_HLINE = pyo.Var(model.n, model.t, within=pyo.Binary)
    model.binary_BAT = pyo.Var(model.n, model.t, within=pyo.Binary)
    model.binary_TES = pyo.Var(model.n, model.t, within=pyo.Binary)

    # Electric vehicle variables
    model.soc_ev = pyo.Var(model.EVs, model.t, within=pyo.NonNegativeReals, doc="State of charge of electric vehicles")
    model.ch_ev = pyo.Var(model.EVs, model.t, within=pyo.NonNegativeReals, doc="Charging power of electric vehicles")
    model.dch_ev = pyo.Var(model.EVs, model.t, within=pyo.NonNegativeReals, doc="Discharging power of electric vehicles")
    model.binary_EV = pyo.Var(model.EVs, model.t, within=pyo.Binary, doc="Binary variable for electric vehicle charging/discharging")

    # Residual network demand
    model.residual_power = pyo.Var(model.t, within=pyo.NonNegativeReals,
                                   doc="Residual power demand of the neighborhood")  # Only pos demand allowed
    model.residual_feed = pyo.Var(model.t, within=pyo.NonNegativeReals, doc="Residual feed-in of the neighborhood")

    # activation variable for trafo load
    model.yTrafo = pyo.Var(model.t, within=pyo.Binary)

    ################################################################################
    # Energyhub variables #! Organise in the same structure as for the buildings to improve readability
    ################################################################################

    # Gas flow to/from devices
    model.eh_gas_CHP = pyo.Var(model.t, within=pyo.NonNegativeReals,
                               doc="Gas consumption by a combined heat and power unit (EH)")
    model.eh_gas_BOI = pyo.Var(model.t, within=pyo.NonNegativeReals, doc="Gas consumption by a gas boiler (EH)")
    model.eh_gas_GHP = pyo.Var(model.t, within=pyo.NonNegativeReals, doc="Gas consumption by a gas heat pump (EH)")
    model.eh_gas_SAB = pyo.Var(model.t, within=pyo.NonNegativeReals, doc="Gas produced by a sabatier reactor (EH)")
    model.eh_gas_from_grid = pyo.Var(model.t, within=pyo.NonNegativeReals, doc="Gas flow from grid to EH")
    model.eh_gas_to_grid = pyo.Var(model.t, within=pyo.NonNegativeReals, doc="Gas flow to grid from EH")

    # Electric power to/from devices
    model.eh_power_PV = pyo.Var(model.t, within=pyo.NonNegativeReals,
                                doc="Electricity produced by a photovoltaik unit (EH)")
    model.eh_power_WT = pyo.Var(model.t, within=pyo.NonNegativeReals, doc="Electricity produced by a wind turbine (EH)")
    model.eh_power_WAT = pyo.Var(model.t, within=pyo.NonNegativeReals, doc="")
    model.eh_power_HP = pyo.Var(model.t, within=pyo.NonNegativeReals, doc="Electricity consumed by an heat pump (EH)")
    model.eh_power_EB = pyo.Var(model.t, within=pyo.NonNegativeReals,
                                doc="Electricity consumed by a electric boiler (EH)")
    model.eh_power_CC = pyo.Var(model.t, within=pyo.NonNegativeReals,
                                doc="Electricity consumed by a compression chiller (EH)")
    model.eh_power_CHP = pyo.Var(model.t, within=pyo.NonNegativeReals,
                                 doc="Electricity produced by a gas combined heat and power unit (EH)")
    model.eh_power_BCHP = pyo.Var(model.t, within=pyo.NonNegativeReals,
                                  doc="Electricity produced by a biomass combined heat and power unit (EH)")
    model.eh_power_WCHP = pyo.Var(model.t, within=pyo.NonNegativeReals,
                                  doc="Electricity produced by a waste combined heat and power unit (EH)")
    model.eh_power_ELYZ = pyo.Var(model.t, within=pyo.NonNegativeReals,
                                  doc="Electricity consumed by an electrolyser (EH)")
    model.eh_power_FC = pyo.Var(model.t, within=pyo.NonNegativeReals, doc="Electricity produced by a fuel cell (EH)")
    model.eh_power_from_grid = pyo.Var(model.t, within=pyo.NonNegativeReals,
                                       doc="Electricity imported from the grid by the Energy Hub")
    model.eh_power_to_grid = pyo.Var(model.t, within=pyo.NonNegativeReals,
                                     doc="Electricity exported to the grid by the Energy Hub")

    # Heat to/from devices
    model.eh_heat_STC = pyo.Var(model.t, within=pyo.NonNegativeReals,
                                doc="Heat produced by a solar thermal collector (EH)")
    model.eh_heat_HP = pyo.Var(model.t, within=pyo.NonNegativeReals, doc="Heat produced by an heat pump (EH)")
    model.eh_heat_EB = pyo.Var(model.t, within=pyo.NonNegativeReals, doc="Heat produced by an electric boiler (EH)")
    model.eh_heat_AC = pyo.Var(model.t, within=pyo.NonNegativeReals, doc="Heat used by an adsorption chiller (EH)")
    model.eh_heat_CHP = pyo.Var(model.t, within=pyo.NonNegativeReals,
                                doc="Heat produced by a gas combined heat and power unit (EH)")
    model.eh_heat_BOI = pyo.Var(model.t, within=pyo.NonNegativeReals, doc="Heat produced by a gas boiler (EH)")
    model.eh_heat_GHP = pyo.Var(model.t, within=pyo.NonNegativeReals, doc="Heat produced by a gas heat pump (EH)")
    model.eh_heat_BCHP = pyo.Var(model.t, within=pyo.NonNegativeReals,
                                 doc="Heat produced by a biomass combined heat and power unit (EH)")
    model.eh_heat_BBOI = pyo.Var(model.t, within=pyo.NonNegativeReals, doc="Heat produced by a biomass boiler (EH)")
    model.eh_heat_WCHP = pyo.Var(model.t, within=pyo.NonNegativeReals,
                                 doc="Heat produced by a waste combined heat and power unit (EH)")
    model.eh_heat_WBOI = pyo.Var(model.t, within=pyo.NonNegativeReals, doc="Heat produced by a waste boiler (EH)")
    model.eh_heat_FC = pyo.Var(model.t, within=pyo.NonNegativeReals, doc="Heat produced by a fuel cell (EH)")
    model.eh_heat_to_grid = pyo.Var(model.t, within=pyo.NonNegativeReals,
                                    doc="Heat from the Energy Hub to the heat grid")

    # Cooling power to/from devices
    model.eh_cool_CC = pyo.Var(model.t, within=pyo.NonNegativeReals,
                               doc="Cooling produced by a compression chiller (EH)")
    model.eh_cool_AC = pyo.Var(model.t, within=pyo.NonNegativeReals,
                               doc="Cooling produced by an adsorption chiller (EH)")
    model.eh_cool_to_grid = pyo.Var(model.t, within=pyo.NonNegativeReals,
                                    doc="Cooling from the Energy Hub to the cooling grid")

    # Hydrogen to/from devices
    model.eh_hydrogen_ELYZ = pyo.Var(model.t, within=pyo.NonNegativeReals)
    model.eh_hydrogen_FC = pyo.Var(model.t, within=pyo.NonNegativeReals)
    model.eh_hydrogen_SAB = pyo.Var(model.t, within=pyo.NonNegativeReals)
    model.eh_hydrogen_from_neighborhood = pyo.Var(model.t, within=pyo.NonNegativeReals)
    model.eh_hydrogen_to_neighborhood = pyo.Var(model.t, within=pyo.NonNegativeReals)

    # Biomass to devices
    model.eh_biom_BCHP = pyo.Var(model.t, within=pyo.NonNegativeReals)
    model.eh_biom_BBOI = pyo.Var(model.t, within=pyo.NonNegativeReals)
    model.eh_biom_import = pyo.Var(model.t, within=pyo.NonNegativeReals)

    # Waste to devices
    model.eh_waste_WCHP = pyo.Var(model.t, within=pyo.NonNegativeReals)
    model.eh_waste_WBOI = pyo.Var(model.t, within=pyo.NonNegativeReals)
    model.eh_waste_import = pyo.Var(model.t, within=pyo.NonNegativeReals)

    # Energyhub Storage variables
    # TES
    model.eh_ch_TES = pyo.Var(model.t, within=pyo.NonNegativeReals)
    model.eh_dch_TES = pyo.Var(model.t, within=pyo.NonNegativeReals)
    model.eh_binary_TES = pyo.Var(model.t, within=pyo.Binary)
    model.eh_soc_TES = pyo.Var(model.t, within=pyo.NonNegativeReals)
    # CTES
    model.eh_ch_CTES = pyo.Var(model.t, within=pyo.NonNegativeReals)
    model.eh_dch_CTES = pyo.Var(model.t, within=pyo.NonNegativeReals)
    model.eh_binary_CTES = pyo.Var(model.t, within=pyo.Binary)
    model.eh_soc_CTES = pyo.Var(model.t, within=pyo.NonNegativeReals)
    # BAT
    model.eh_ch_BAT = pyo.Var(model.t, within=pyo.NonNegativeReals)
    model.eh_dch_BAT = pyo.Var(model.t, within=pyo.NonNegativeReals)
    model.eh_binary_BAT = pyo.Var(model.t, within=pyo.Binary)
    model.eh_soc_BAT = pyo.Var(model.t, within=pyo.NonNegativeReals)
    # H2S
    model.eh_ch_H2S = pyo.Var(model.t, within=pyo.NonNegativeReals)
    model.eh_dch_H2S = pyo.Var(model.t, within=pyo.NonNegativeReals)
    model.eh_binary_H2S = pyo.Var(model.t, within=pyo.Binary)
    model.eh_soc_H2S = pyo.Var(model.t, within=pyo.NonNegativeReals)
    # GS
    model.eh_ch_GS = pyo.Var(model.t, within=pyo.NonNegativeReals)
    model.eh_dch_GS = pyo.Var(model.t, within=pyo.NonNegativeReals)
    model.eh_binary_GS = pyo.Var(model.t, within=pyo.Binary)
    model.eh_soc_GS = pyo.Var(model.t, within=pyo.NonNegativeReals)

    ################################################################################
    # BALANCING UNIT VARIABLES
    ################################################################################

    # Electrical power to/from grid at GNP, gas from grid #TODO: Rename variables
    model.power_from_grid = pyo.Var(model.t, within=pyo.NonNegativeReals)
    model.power_to_grid = pyo.Var(model.t, within=pyo.NonNegativeReals)
    model.power_gas_from_grid = pyo.Var(model.t, within=pyo.NonNegativeReals)
    model.power_hydrogen_grid_import = pyo.Var(model.t, within=pyo.NonNegativeReals)
    model.power_biomass_import = pyo.Var(model.t, within=pyo.NonNegativeReals)
    model.power_oil_import = pyo.Var(model.t, within=pyo.NonNegativeReals)
    model.power_waste_import = pyo.Var(model.t, within=pyo.NonNegativeReals)
    model.power_district_heating_import = pyo.Var(model.t, within=pyo.NonNegativeReals)

    # total energy amounts taken from grid
    model.from_grid_total_el = pyo.Var(within=pyo.NonNegativeReals)
    model.to_grid_total_el = pyo.Var(within=pyo.NonNegativeReals)
    model.to_grid_total_el_buildings = pyo.Var(within=pyo.NonNegativeReals)
    model.from_grid_total_el_buildings = pyo.Var(within=pyo.NonNegativeReals)
    model.to_grid_total_el_eh = pyo.Var(within=pyo.NonNegativeReals)
    model.from_grid_total_el_eh = pyo.Var(within=pyo.NonNegativeReals)
    model.from_grid_total_gas = pyo.Var(within=pyo.NonNegativeReals)
    model.from_grid_total_hydrogen = pyo.Var(within=pyo.NonNegativeReals)
    model.total_biomass_used = pyo.Var(within=pyo.NonNegativeReals)
    model.total_waste_used = pyo.Var(within=pyo.NonNegativeReals)
    model.total_oil_used = pyo.Var(within=pyo.NonNegativeReals)
    model.total_district_heat_used = pyo.Var(within=pyo.NonNegativeReals)

    # daily peak
    model.daily_peak = pyo.Var(model.days, within=pyo.Reals)
    model.peaksum = pyo.Var(within=pyo.Reals)
    model.is_daily_peak = pyo.Var(model.days, model.t, within=pyo.Binary)

    # Total operational costs
    model.operational_costs = pyo.Var(within=pyo.Reals)
    # Total gross CO2 emissions
    model.co2_total = pyo.Var(within=pyo.Reals)

    # Objective function
    model.obj = pyo.Var(within=pyo.Reals)

    ################################################################################
    # Fixed Demand Constraints for the building demands (electricity, heating, cooling, DHW)
    ################################################################################

    # Electricity demand
    def elec_demand_rule(model, n, t):
        """Electrical demand is a known fixed value from building data"""
        return model.power_dom["Elec_dem", n, t] == elec_dem[n][t]

    # Heating demand
    def heating_demand_constraint_rule(model, n, t):
        """Space heating demand is a known fixed value from building data"""
        return model.heat_dom["Heating_dem", n, t] == Q_heating[n][t]

    # DHW demand
    def dhw_demand_constraint_rule(model, n, t):
        """Domestic hot water demand is a known fixed value from building data"""
        return model.heat_dom["DHW_dem", n, t] == Q_DHW[n][t]

    # Cooling demand
    def cooling_demand_constraint_rule(model, n, t):
        """Cooling demand is a known fixed value from building data"""
        return model.cool_dom["Cooling_dem", n, t] == Q_cooling[n][t]

    model.elec_demand_constraint = pyo.Constraint(model.n, model.t, rule=elec_demand_rule)
    model.heating_demand_constraint = pyo.Constraint(model.n, model.t, rule=heating_demand_constraint_rule)
    model.dhw_demand_constraint = pyo.Constraint(model.n, model.t, rule=dhw_demand_constraint_rule)
    model.cooling_demand_constraint = pyo.Constraint(model.n, model.t, rule=cooling_demand_constraint_rule)

    ################################################################################
    # Define capacity of devices as parameters from input data (Energy Hub)
    ################################################################################

    def create_eh_heat_capacity_constraint(device_name):
        """Factory-function für EH Heat Capacity Constraints"""

        def constraint_rule(model, t):
            if energyHubData == {}:
                return getattr(model, f"eh_heat_{device_name}")[t] == 0
            else:
                return getattr(model, f"eh_heat_{device_name}")[t] <= energyHubData["capacities"][device_name][
                    "cap"] * 1000  # kW to W

        return constraint_rule

    def create_eh_power_capacity_constraint(device_name):
        """Factory-function für EH Power Capacity Constraints"""

        def constraint_rule(model, t):
            if energyHubData == {}:
                return getattr(model, f"eh_power_{device_name}")[t] == 0
            else:
                return getattr(model, f"eh_power_{device_name}")[t] <= energyHubData["capacities"][device_name][
                    "cap"] * 1000  # kW to W

        return constraint_rule

    def create_eh_cool_capacity_constraint(device_name):
        """Factory-function für EH Cool Capacity Constraints"""

        def constraint_rule(model, t):
            if energyHubData == {}:
                return getattr(model, f"eh_cool_{device_name}")[t] == 0
            else:
                return getattr(model, f"eh_cool_{device_name}")[t] <= energyHubData["capacities"][device_name][
                    "cap"] * 1000  # kW to W

        return constraint_rule

    def create_eh_storage_soc_max_constraint(device_name):
        """Factory-function für EH Storage SOC Maximum Constraints"""

        def constraint_rule(model, t):
            if energyHubData == {}:
                return getattr(model, f"eh_soc_{device_name}")[t] == 0
            else:
                return getattr(model, f"eh_soc_{device_name}")[t] <= energyHubData["capacities"][device_name][
                    "cap"] * 1000  # kWh to Wh

        return constraint_rule

    # STC, PV and WT generation constraints for energy hub: power/heat production needs to be less than or equal to the possible production

    def eh_stc_generation_rule(model, t):
        if energyHubData == {}:
            return model.eh_heat_STC[t] == 0
        else:
            return model.eh_heat_STC[t] <= energyHubData["generation"]["STC_cluster"][cluster][t] * 1000

    def eh_pv_generation_rule(model, t):
        if energyHubData == {}:
            return model.eh_power_PV[t] == 0
        else:
            return model.eh_power_PV[t] <= energyHubData["generation"]["PV_cluster"][cluster][t] * 1000

    def eh_wt_generation_rule(model, t):
        if energyHubData == {}:
            return model.eh_power_WT[t] == 0
        else:
            return model.eh_power_WT[t] == energyHubData["generation"]["Wind_cluster"][cluster][t] * 1000

    for device in ["EB", "HP", "BOI", "GHP", "BBOI", "WBOI"]:
        constraint_rule = create_eh_heat_capacity_constraint(device)
        setattr(model, f"eh_heat_cap_{device}", pyo.Constraint(model.t, rule=constraint_rule))

    for device in ["WAT", "CHP", "BCHP", "WCHP", "ELYZ", "FC", "from_grid", "to_grid"]:
        constraint_rule = create_eh_power_capacity_constraint(device)
        setattr(model, f"eh_power_cap_{device}", pyo.Constraint(model.t, rule=constraint_rule))

    for device in ["CC", "AC"]:
        constraint_rule = create_eh_cool_capacity_constraint(device)
        setattr(model, f"eh_cool_cap_{device}", pyo.Constraint(model.t, rule=constraint_rule))

    for device in ["TES", "CTES", "BAT", "H2S", "GS"]:
        constraint_rule_soc_max = create_eh_storage_soc_max_constraint(device)
        setattr(model, f"eh_storage_soc_max_{device}", pyo.Constraint(model.t, rule=constraint_rule_soc_max))

    model.eh_stc_generation = pyo.Constraint(model.t, rule=eh_stc_generation_rule)
    model.eh_pv_generation = pyo.Constraint(model.t, rule=eh_pv_generation_rule)
    model.eh_wt_generation = pyo.Constraint(model.t, rule=eh_wt_generation_rule)

    ################################################################################
    # Define capacity of devices as parameters from input data (Buildings)
    ################################################################################

    # Heating and cooling devices capacity constraints
    def create_dom_heat_capacity_constraint(device_name):
        """Factory-function that creates a constraint function"""

        def constraint_rule(model, n, t):
            """Constraint rule"""
            return model.heat_dom[device_name, n, t] <= buildingData[n]["capacities"][device_name]

        return constraint_rule

    def create_dom_cool_capacity_constraint(device_name):
        """Factory-function that creates a constraint function"""

        def constraint_rule(model, n, t):
            """Constraint rule"""
            return model.cool_dom[device_name, n, t] <= buildingData[n]["capacities"][device_name]

        return constraint_rule

    # Storage devices charging, discharging and soc constraints
    def create_dom_storage_ch_capacity_constraint(device_name):
        """Factory-function für Storage Charging Capacity Constraints"""

        def constraint_rule(model, n, t):
            return model.ch_dom[device_name, n, t] <= buildingData[n]["capacities"][device_name] * \
                param_dec_devs[device_name]["coeff_ch"]

        return constraint_rule

    def create_dom_storage_dch_capacity_constraint(device_name):
        """Factory-function für Storage Discharging Capacity Constraints"""

        def constraint_rule(model, n, t):
            return model.dch_dom[device_name, n, t] <= buildingData[n]["capacities"][device_name] * \
                param_dec_devs[device_name]["coeff_ch"]

        return constraint_rule

    def create_dom_storage_soc_max_constraint(device_name):
        """Factory-function für Storage SOC Maximum Constraints"""

        def constraint_rule(model, n, t):
            return model.soc_dom[device_name, n, t] <= param_dec_devs[device_name]["soc_max"] * \
                buildingData[n]["capacities"][device_name]

        return constraint_rule

    def create_dom_storage_soc_min_constraint(device_name):
        """Factory-function für Storage SOC Minimum Constraints"""

        def constraint_rule(model, n, t):
            return model.soc_dom[device_name, n, t] >= param_dec_devs[device_name]["soc_min"] * \
                buildingData[n]["capacities"][device_name]

        return constraint_rule

    # STC and PV generation constraints
    def stc_capacity_rule(model, n,
                          t):  # STC generation below or equal to potential stc generation (Allows curtailment of STC)
        return model.heat_dom["STC", n, t] <= STC_heat[n][t]

    def pv_capacity_rule(model, n,
                         t):  # PV generation below or equal to potential pv generation (Allows curtailment of PV)
        return model.power_dom["PV", n, t] <= PV_gen[n][t]

    # heat from local heat grid
    def heat_grid_capacity_rule(model, n, t):
        if buildingData[n]["capacities"]["heat_grid"] == 1: # no limit on the amount of heat taken from local heat grid
            return pyo.Constraint.Skip
        else:
            return model.heat_dom["heat_grid", n, t] == 0 # if no local heat grid connection, no heat can be used

    # Aplication of the constraints for each device

    # Heat generating devices
    for device in ["HP", "CHP", "BOI", "BBOI", "OBOI", "H2BOI", "FC", "EH", "DH"]: # Devices which capacity is defined by thermal capacity
        constraint_rule = create_dom_heat_capacity_constraint(device)
        setattr(model, f"heat_cap_{device}", pyo.Constraint(model.n, model.t, rule=constraint_rule))

    # Cooling generating devices
    for device in ["CC", ]:
        constraint_rule = create_dom_cool_capacity_constraint(device)  # Devices which capacity is defined by cooling capacity
        setattr(model, f"cool_cap_{device}", pyo.Constraint(model.n, model.t, rule=constraint_rule))

    # Storage devices
    for device in ECS_STORAGE:
        constraint_rule_ch = create_dom_storage_ch_capacity_constraint(device)
        setattr(model, f"storage_ch_cap_{device}", pyo.Constraint(model.n, model.t, rule=constraint_rule_ch))
        constraint_rule_dch = create_dom_storage_dch_capacity_constraint(device)
        setattr(model, f"storage_dch_cap_{device}", pyo.Constraint(model.n, model.t, rule=constraint_rule_dch))
        constraint_rule_soc_max = create_dom_storage_soc_max_constraint(device)
        setattr(model, f"storage_soc_max_{device}", pyo.Constraint(model.n, model.t, rule=constraint_rule_soc_max))
        constraint_rule_soc_min = create_dom_storage_soc_min_constraint(device)
        setattr(model, f"storage_soc_min_{device}", pyo.Constraint(model.n, model.t, rule=constraint_rule_soc_min))

    model.stc_cap = pyo.Constraint(model.n, model.t, rule=stc_capacity_rule, doc="Solar thermal collector heat generation limit")
    model.pv_capacity = pyo.Constraint(model.n, model.t, rule=pv_capacity_rule, doc="PV electrical generation limit")
    model.heat_grid_capacity = pyo.Constraint(model.n, model.t, rule=heat_grid_capacity_rule, doc="Local heat grid capacity constraint")

    ################################################################################
    # Energy Conversion for Energyhub devices
    ################################################################################

    def eh_hp_conversion_rule(model, t):
        if energyHubData == {}:
            return model.eh_heat_HP[t] == 0
        else:
            COP_HP_eh = energyHubData["capacities"]["devs"]["HP"]["COP"][cluster][t]
            return model.eh_heat_HP[t] == model.eh_power_HP[t] * COP_HP_eh

    def eh_eb_conversion_rule(model, t):
        return model.eh_heat_EB[t] == model.eh_power_EB[t] * central_device_data["EB"]["eta_th"]

    def eh_cc_conversion_rule(model, t):
        if energyHubData == {}:
            return model.eh_cool_CC[t] == 0
        else:
            COP_CC_eh = energyHubData["capacities"]["devs"]["CC"]["COP"][cluster][t]
            return model.eh_cool_CC[t] == model.eh_power_CC[t] * COP_CC_eh

    def eh_ac_conversion_rule(model, t):
        return model.eh_cool_AC[t] == model.eh_heat_AC[t] * central_device_data["AC"]["eta_th"]

    def eh_chp_power_conversion_rule(model, t):
        return model.eh_power_CHP[t] == model.eh_gas_CHP[t] * central_device_data["CHP"]["eta_el"]

    def eh_chp_heat_conversion_rule(model, t):
        return model.eh_heat_CHP[t] == model.eh_gas_CHP[t] * central_device_data["CHP"]["eta_th"]

    def eh_boi_conversion_rule(model, t):
        return model.eh_heat_BOI[t] == model.eh_gas_BOI[t] * central_device_data["BOI"]["eta_th"]

    def eh_ghp_conversion_rule(model, t):
        return model.eh_heat_GHP[t] == model.eh_gas_GHP[t] * central_device_data["GHP"]["COP"]

    def eh_bchp_power_conversion_rule(model, t):
        return model.eh_power_BCHP[t] == model.eh_biom_BCHP[t] * central_device_data["BCHP"]["eta_el"]

    def eh_bchp_heat_conversion_rule(model, t):
        return model.eh_heat_BCHP[t] == model.eh_biom_BCHP[t] * central_device_data["BCHP"]["eta_th"]

    def eh_bboi_conversion_rule(model, t):
        return model.eh_heat_BBOI[t] == model.eh_biom_BBOI[t] * central_device_data["BBOI"]["eta_th"]

    def eh_wchp_power_conversion_rule(model, t):
        return model.eh_power_WCHP[t] == model.eh_waste_WCHP[t] * central_device_data["WCHP"]["eta_el"]

    def eh_wchp_heat_conversion_rule(model, t):
        return model.eh_heat_WCHP[t] == model.eh_waste_WCHP[t] * central_device_data["WCHP"]["eta_th"]

    def eh_wboi_conversion_rule(model, t):
        return model.eh_heat_WBOI[t] == model.eh_waste_WBOI[t] * central_device_data["WBOI"]["eta_th"]

    def eh_elyz_conversion_rule(model, t):
        return model.eh_hydrogen_ELYZ[t] == model.eh_power_ELYZ[t] * central_device_data["ELYZ"]["eta_el"]

    def eh_fc_power_conversion_rule(model, t):
        return model.eh_power_FC[t] == model.eh_hydrogen_FC[t] * central_device_data["FC"]["eta_el"]

    def eh_fc_heat_conversion_rule(model, t):
        return model.eh_heat_FC[t] == model.eh_hydrogen_FC[t] * central_device_data["FC"]["eta_th"]

    def eh_sab_conversion_rule(model, t):
        return model.eh_gas_SAB[t] == model.eh_hydrogen_SAB[t] * central_device_data["SAB"]["eta"]

    model.eh_hp_conversion = pyo.Constraint(model.t, rule=eh_hp_conversion_rule)
    model.eh_eb_conversion = pyo.Constraint(model.t, rule=eh_eb_conversion_rule)
    model.eh_cc_conversion = pyo.Constraint(model.t, rule=eh_cc_conversion_rule)
    model.eh_ac_conversion = pyo.Constraint(model.t, rule=eh_ac_conversion_rule)
    model.eh_chp_power_conversion = pyo.Constraint(model.t, rule=eh_chp_power_conversion_rule)
    model.eh_chp_heat_conversion = pyo.Constraint(model.t, rule=eh_chp_heat_conversion_rule)
    model.eh_boi_conversion = pyo.Constraint(model.t, rule=eh_boi_conversion_rule)
    model.eh_ghp_conversion = pyo.Constraint(model.t, rule=eh_ghp_conversion_rule)
    model.eh_bchp_power_conversion = pyo.Constraint(model.t, rule=eh_bchp_power_conversion_rule)
    model.eh_bchp_heat_conversion = pyo.Constraint(model.t, rule=eh_bchp_heat_conversion_rule)
    model.eh_bboi_conversion = pyo.Constraint(model.t, rule=eh_bboi_conversion_rule)
    model.eh_wchp_power_conversion = pyo.Constraint(model.t, rule=eh_wchp_power_conversion_rule)
    model.eh_wchp_heat_conversion = pyo.Constraint(model.t, rule=eh_wchp_heat_conversion_rule)
    model.eh_wboi_conversion = pyo.Constraint(model.t, rule=eh_wboi_conversion_rule)
    model.eh_elyz_conversion = pyo.Constraint(model.t, rule=eh_elyz_conversion_rule)
    model.eh_fc_power_conversion = pyo.Constraint(model.t, rule=eh_fc_power_conversion_rule)
    model.eh_fc_heat_conversion = pyo.Constraint(model.t, rule=eh_fc_heat_conversion_rule)
    model.eh_sab_conversion = pyo.Constraint(model.t, rule=eh_sab_conversion_rule)

    ################################################################################
    # Energy Conversion for domestic devices
    ################################################################################

    # Energy balance heat pump
    def hp_heat_balance_rule(model, n, t):
        return model.heat_dom["HP", n, t] == model.heat_mode["HP35", n, t] + model.heat_mode["HP55", n, t]

    def hp_power_balance_rule(model, n, t):
        return model.power_dom["HP", n, t] == model.power_mode["HP35", n, t] + model.power_mode["HP55", n, t]

    # heat generation of heat pump for each modus
    def hp_mode_constraint_new_rule(model, n, t):
        if buildingData[n]["envelope"].construction_year >= 1995 and buildingData[n]["capacities"]["HP"] > 0:
            return model.power_mode["HP55", n, t] == 0
        else:
            return pyo.Constraint.Skip  # Maybe problems when both rules are skipped?

    def hp_mode_constraint_old_rule(model, n, t):
        if buildingData[n]["envelope"].construction_year < 1995 and buildingData[n]["capacities"]["HP"] > 0:
            return model.power_mode["HP35", n, t] == 0
        else:
            return pyo.Constraint.Skip  # Maybe problems when both rules are skipped?

    # Energy conversion heat pump modus 35
    def hp35_conversion_rule(model, n, t):
        return model.heat_mode["HP35", n, t] == model.power_mode["HP35", n, t] * param_dec_devs["HP"]["grade"] * (
                273.15 + 35) / (35 - T_e[t])

    # Energy conversion heat pump modus 55
    def hp55_conversion_rule(model, n, t):
        return model.heat_mode["HP55", n, t] == model.power_mode["HP55", n, t] * param_dec_devs["HP"]["grade"] * (
                273.15 + 55) / (55 - T_e[t])

    # Electric heater
    def eh_conversion_rule(model, n, t):
        return model.heat_dom["EH", n, t] == param_dec_devs["EH"]["eta_th"] * model.power_dom["EH", n, t]

    # CHP
    def chp_heat_conversion_rule(model, n, t):
        return model.heat_dom["CHP", n, t] == param_dec_devs["CHP"]["eta_th"] * model.gas_dom["CHP", n, t]

    def chp_power_conversion_rule(model, n, t):
        return model.power_dom["CHP", n, t] == param_dec_devs["CHP"]["eta_el"] * model.gas_dom["CHP", n, t]

    # BOILER
    def boiler_conversion_rule(model, n, t):
        return model.heat_dom["BOI", n, t] == param_dec_devs["BOI"]["eta_th"] * model.gas_dom["BOI", n, t]

    # Biomass boiler
    def bboi_conversion_rule(model, n, t):
        return model.heat_dom["BBOI", n, t] == param_dec_devs["BBOI"]["eta_th"] * model.biomass_dom["BBOI", n, t]

    # Oil Boiler
    def oboi_conversion_rule(model, n, t):
        return model.heat_dom["OBOI", n, t] == param_dec_devs["OBOI"]["eta_th"] * model.oil_dom["OBOI", n, t]

    # hydrogen boiler
    def h2boi_conversion_rule(model, n, t):
        return model.heat_dom["H2BOI", n, t] == param_dec_devs["H2BOI"]["eta_th"] * model.hydrogen_dom["H2BOI", n, t]

    # district heating
    def dh_conversion_rule(model, n, t):
        return model.heat_dom["DH", n, t] == model.dh_heat_supply[n, t] * param_dec_devs["DH"]["eta_th"]

    # Fuel Cell
    def fc_building_heat_conversion_rule(model, n, t):
        return model.heat_dom["FC", n, t] == param_dec_devs["FC"]["eta_th"] * model.hydrogen_dom["FC", n, t]

    def fc_building_power_conversion_rule(model, n, t):
        return model.power_dom["FC", n, t] == param_dec_devs["FC"]["eta_el"] * model.hydrogen_dom["FC", n, t]

    # Compression Chiller
    def cc_building_conversion_rule(model, n, t):
        return model.cool_dom["CC", n, t] == model.power_dom["CC", n, t] * param_dec_devs["CC"]["grade"] * (
                    273.15 + 5) / max(T_e[t] - 5, 0.1)

    # Constraints for building devices conversion
    model.hp_heat_balance = pyo.Constraint(model.n, model.t, rule=hp_heat_balance_rule,
                                           doc="Heat pump total heat output balance between HP35 and HP55 modes")
    model.hp_power_balance = pyo.Constraint(model.n, model.t, rule=hp_power_balance_rule,
                                            doc="Heat pump total power consumption balance between HP35 and HP55 modes")
    model.hp_mode_new = pyo.Constraint(model.n, model.t, rule=hp_mode_constraint_new_rule,
                                       doc="Heat pump mode restriction for new buildings (≥1995): only HP35 mode allowed")
    model.hp_mode_old = pyo.Constraint(model.n, model.t, rule=hp_mode_constraint_old_rule,
                                       doc="Heat pump mode restriction for old buildings (<1995): only HP55 mode allowed")
    model.hp35_conversion = pyo.Constraint(model.n, model.t, rule=hp35_conversion_rule,
                                           doc="Heat pump HP35 mode: converts electricity to heat with COP dependent on ambient temperature (35°C supply)")
    model.hp55_conversion = pyo.Constraint(model.n, model.t, rule=hp55_conversion_rule,
                                           doc="Heat pump HP55 mode: converts electricity to heat with COP dependent on ambient temperature (55°C supply)")
    model.eh_conversion = pyo.Constraint(model.n, model.t, rule=eh_conversion_rule,
                                         doc="Electric heater: converts electricity to heat for space heating and DHW")
    model.chp_heat_conversion = pyo.Constraint(model.n, model.t, rule=chp_heat_conversion_rule,
                                               doc="CHP thermal conversion: gas to heat with thermal efficiency")
    model.chp_power_conversion = pyo.Constraint(model.n, model.t, rule=chp_power_conversion_rule,
                                                doc="CHP electrical conversion: gas to electricity with electrical efficiency")
    model.boiler_conversion = pyo.Constraint(model.n, model.t, rule=boiler_conversion_rule,
                                             doc="Gas boiler conversion: natural gas to heat with thermal efficiency")
    model.bboi_conversion = pyo.Constraint(model.n, model.t, rule=bboi_conversion_rule,
                                           doc="Biomass boiler conversion: biomass to heat with thermal efficiency")
    model.oboi_conversion = pyo.Constraint(model.n, model.t, rule=oboi_conversion_rule,
                                           doc="Oil boiler conversion: oil to heat with thermal efficiency")
    model.h2boi_conversion = pyo.Constraint(model.n, model.t, rule=h2boi_conversion_rule,
                                            doc="Hydrogen boiler conversion: hydrogen to heat with thermal efficiency")
    model.dh_conversion = pyo.Constraint(model.n, model.t, rule=dh_conversion_rule, doc="District heating conversion: district heat to usable heat with thermal efficiency")
    model.fc_building_heat_conversion = pyo.Constraint(model.n, model.t, rule=fc_building_heat_conversion_rule,
                                                       doc="Fuel cell thermal conversion: hydrogen to waste heat with thermal efficiency")
    model.fc_building_power_conversion = pyo.Constraint(model.n, model.t, rule=fc_building_power_conversion_rule,
                                                        doc="Fuel cell electrical conversion: hydrogen to electricity with electrical efficiency")
    model.cc_building_conversion = pyo.Constraint(model.n, model.t, rule=cc_building_conversion_rule,
                                                  doc="Compression chiller conversion: electricity to cooling with temperature-dependent COP")

    ################################################################################
    # %% EV CONSTRAINTS #! This Code currently views all EVs connected to a building as one single EV storage device. This is not realistic and should probably be changed. Especially if bidirectional or intelligentcharging is considered.
    ################################################################################

    # Modelling of the EV charging process and storage
    def ev_energy_balance_rule(model, ev_id, t):
        ev = ev_data[ev_id]
        if ev["charging_type"] == "on_demand":
            return pyo.Constraint.Skip  # on-demand EVs do not need an energy balance constraint because they are directly charged the same amount as they consume. Calculation in profiles.py
        if t == 0:
            soc_prev = soc_init_ev[ev_id]
        else:
            soc_prev = model.soc_ev[ev_id, t - 1]

        driving_demand = ev["driving_demand_wh"][t]
        return model.soc_ev[ev_id, t] == soc_prev * param_dec_devs["EV"]["eta_standby"] ** dt + \
               (model.ch_ev[ev_id, t] * param_dec_devs["EV"]["eta_ch"] - \
                model.dch_ev[ev_id, t] / param_dec_devs["EV"]["eta_ch"]) * dt - \
               driving_demand

    # SOC at end of time horizon needs to be the same as initial SOC
    def ev_final_soc_rule(model, ev_id):
        """Final SOC of EV needs to be the same as initial SOC"""
        if ev_data[ev_id]["charging_type"] == "on_demand":
            return pyo.Constraint.Skip
        return model.soc_ev[ev_id, last_time_step] == soc_init_ev[ev_id]

    # SOC limited by max/min soc
    def ev_soc_max_rule(model, ev_id, t):
        if ev_data[ev_id]["charging_type"] == "on_demand":
            return pyo.Constraint.Skip
        return model.soc_ev[ev_id, t] <= ev_data[ev_id]["battery_capacity_wh"] * param_dec_devs["EV"]["soc_max"]

    def ev_soc_min_rule(model, ev_id, t):
        if ev_data[ev_id]["charging_type"] == "on_demand":
            return pyo.Constraint.Skip
        return model.soc_ev[ev_id, t] >= ev_data[ev_id]["battery_capacity_wh"] * param_dec_devs["EV"]["soc_min"]

    # Charging rules

    def ev_on_demand_charging_rule(model, ev_id, t):
        ev = ev_data[ev_id]
        if ev["charging_type"] == "on_demand":
            return model.ch_ev[ev_id, t] == ev["on_demand_charging_profile"][t]
        else:
            return pyo.Constraint.Skip

    def ev_charging_rule(model, ev_id, t):
        ev = ev_data[ev_id]
        if ev["charging_type"] == "on_demand":
            return pyo.Constraint.Skip  # on-demand EVs do not have charging constraints
        else:
            charging_possible = ev["availability"][t] # True if charging possible, False otherwise
            if not charging_possible:
                return model.ch_ev[ev_id, t] == 0
            else:
                return model.ch_ev[ev_id, t] <= ev["max_ch_power"]  # Max charging power constraint

    # Discharging rules
    def ev_discharging_rule(model, ev_id, t):
        ev = ev_data[ev_id]

        if ev["charging_type"] != "bi_directional":
            return model.dch_ev[ev_id, t] == 0 # Only bi-directional EVs can discharge
        is_available = ev["availability"][t]
        if not is_available:
            return model.dch_ev[ev_id, t] == 0
        else:
            return model.dch_ev[ev_id, t] <= ev["max_dch_power"]  # Max discharging power constraint

    # Binary rules for preventing simultaneous charging and discharging
    def ev_binary1_rule(model, ev_id, t):
        return model.dch_ev[ev_id, t] <= model.binary_EV[ev_id, t] * BIG_M

    def ev_binary2_rule(model, ev_id, t):
        return model.ch_ev[ev_id, t] <= (1 - model.binary_EV[ev_id, t]) * BIG_M

    # Constraints for individual EVs
    model.ev_energy_balance = pyo.Constraint(model.EVs, model.t, rule=ev_energy_balance_rule)
    model.ev_final_soc = pyo.Constraint(model.EVs, rule=ev_final_soc_rule)
    model.ev_charging = pyo.Constraint(model.EVs, model.t, rule=ev_charging_rule)
    model.ev_on_demand_charging = pyo.Constraint(model.EVs, model.t, rule=ev_on_demand_charging_rule)
    model.ev_discharging = pyo.Constraint(model.EVs, model.t, rule=ev_discharging_rule)
    model.ev_soc_max = pyo.Constraint(model.EVs, model.t, rule=ev_soc_max_rule)
    model.ev_soc_min = pyo.Constraint(model.EVs, model.t, rule=ev_soc_min_rule)
    model.ev_binary1 = pyo.Constraint(model.EVs, model.t, rule=ev_binary1_rule)
    model.ev_binary2 = pyo.Constraint(model.EVs, model.t, rule=ev_binary2_rule)

    ################################################################################
    # %% Building storage balances and constraints #! Here a similar factory function to the energy hub storages might be useful
    ################################################################################

    # SOC coupled over all times steps (Energy amount balance, kWh)
    def tes_energy_balance_rule(model, n, t):
        if t == 0:
            soc_prev = soc_init["TES"][n]
        else:
            soc_prev = model.soc_dom["TES", n, t - 1]

        return model.soc_dom["TES", n, t] == soc_prev * param_dec_devs["TES"]["eta_standby"] ** dt + (
                model.ch_dom["TES", n, t] * param_dec_devs["TES"]["eta_ch"] - model.dch_dom["TES", n, t] /
                param_dec_devs["TES"]["eta_ch"]) * dt

    def tes_final_soc_rule(model, n):
        return model.soc_dom["TES", n, last_time_step] == soc_init["TES"][n]

    def tes_binary1_rule(model, n, t):
        return model.dch_dom["TES", n, t] <= model.binary_TES[n, t] * BIG_M

    def tes_binary2_rule(model, n, t):
        return model.ch_dom["TES", n, t] <= (1 - model.binary_TES[n, t]) * BIG_M

    def bat_energy_balance_rule(model, n, t):
        if t == 0:
            soc_prev = soc_init["BAT"][n]
        else:
            soc_prev = model.soc_dom["BAT", n, t - 1]

        return model.soc_dom["BAT", n, t] == soc_prev * param_dec_devs["BAT"]["eta_standby"] ** dt + (
                model.ch_dom["BAT", n, t] * param_dec_devs["BAT"]["eta_ch"] - model.dch_dom["BAT", n, t] /
                param_dec_devs["BAT"]["eta_ch"]) * dt

    def bat_final_soc_rule(model, n):
        return model.soc_dom["BAT", n, last_time_step] == soc_init["BAT"][n]

    # Binary constraints for batteries
    def bat_binary1_rule(model, n, t):
        return model.dch_dom["BAT", n, t] <= model.binary_BAT[n, t] * BIG_M

    def bat_binary2_rule(model, n, t):
        return model.ch_dom["BAT", n, t] <= (1 - model.binary_BAT[n, t]) * BIG_M

    # Binary constraints for household line
    def hline_binary1_rule(model, n, t):
        return model.res_dom_power[n, t] <= model.binary_HLINE[n, t] * (siteData["buildingMax_W"] if siteData["enable_buildingMax_W"] else BIG_M)

    def hline_binary2_rule(model, n, t):
        return model.res_dom_feed[n, t] <= (1 - model.binary_HLINE[n, t]) * (siteData["buildingMax_W"] if siteData["enable_buildingMax_W"] else BIG_M)

    # Residual loads of the district
    def residual_power_rule(model, t):
        return model.residual_power[t] == sum(model.res_dom_power[n, t] for n in model.n)

    def residual_feed_rule(model, t):
        return model.residual_feed[t] == sum(model.res_dom_feed[n, t] for n in model.n)

    # TES
    model.tes_energy_balance = pyo.Constraint(model.n, model.t, rule=tes_energy_balance_rule)
    model.tes_final_soc = pyo.Constraint(model.n, rule=tes_final_soc_rule)
    model.tes_binary1 = pyo.Constraint(model.n, model.t, rule=tes_binary1_rule)
    model.tes_binary2 = pyo.Constraint(model.n, model.t, rule=tes_binary2_rule)
    # Battery
    model.bat_energy_balance = pyo.Constraint(model.n, model.t, rule=bat_energy_balance_rule)
    model.bat_final_soc = pyo.Constraint(model.n, rule=bat_final_soc_rule)
    model.bat_binary1 = pyo.Constraint(model.n, model.t, rule=bat_binary1_rule)
    model.bat_binary2 = pyo.Constraint(model.n, model.t, rule=bat_binary2_rule)

    # Binary constraints for household line
    model.hline_binary1 = pyo.Constraint(model.n, model.t, rule=hline_binary1_rule)
    model.hline_binary2 = pyo.Constraint(model.n, model.t, rule=hline_binary2_rule)
    # Residual loads constraints
    model.residual_power_balance = pyo.Constraint(model.t, rule=residual_power_rule)
    model.residual_feed_balance = pyo.Constraint(model.t, rule=residual_feed_rule)

    ################################################################################
    # Energy Hub Storage balances and constraints
    ################################################################################

    def create_eh_storage_balance_constraint(device_name):
        """Factory-function für EH Storage Balance Constraints"""

        def constraint_rule(model, t):
            if energyHubData == {}:
                return getattr(model, f"eh_soc_{device_name}")[t] == 0
            else:
                if t == 0:
                    eh_soc_prev = energyHubData["capacities"][device_name]["cap"] * 1000 * 0.5  # 50% initial SOC
                else:
                    eh_soc_prev = getattr(model, f"eh_soc_{device_name}")[t - 1]

                return (getattr(model, f"eh_soc_{device_name}")[t] ==
                        eh_soc_prev * (1 - central_device_data[device_name]["sto_loss"]) ** dt +
                        (getattr(model, f"eh_ch_{device_name}")[t] -
                         getattr(model, f"eh_dch_{device_name}")[t]) * dt)

        return constraint_rule

    def create_eh_storage_final_soc_constraint(device_name):
        """Factory-function für EH Storage Final SOC Constraints"""

        def constraint_rule(model):
            if energyHubData == {}:
                return pyo.Constraint.Skip
            else:
                initial_soc = energyHubData["capacities"][device_name]["cap"] * 1000 * 0.5
                return getattr(model, f"eh_soc_{device_name}")[last_time_step] == initial_soc

        return constraint_rule

    def create_eh_storage_binary1_constraint(device_name):
        """Factory-function für EH Storage Binary Constraint 1 (Discharging)"""

        def constraint_rule(model, t):
            if energyHubData == {}:
                return getattr(model, f"eh_dch_{device_name}")[t] == 0
            else:
                return getattr(model, f"eh_dch_{device_name}")[t] <= getattr(model, f"eh_binary_{device_name}")[
                    t] * BIG_M

        return constraint_rule

    def create_eh_storage_binary2_constraint(device_name):
        """Factory-function für EH Storage Binary Constraint 2 (Charging)"""

        def constraint_rule(model, t):
            if energyHubData == {}:
                return getattr(model, f"eh_ch_{device_name}")[t] == 0
            else:
                return getattr(model, f"eh_ch_{device_name}")[t] <= (
                            1 - getattr(model, f"eh_binary_{device_name}")[t]) * BIG_M

        return constraint_rule

    for device in EH_ECS_STORAGE:
        balance_rule = create_eh_storage_balance_constraint(device)
        final_soc_rule = create_eh_storage_final_soc_constraint(device)
        binary1_rule = create_eh_storage_binary1_constraint(device)
        binary2_rule = create_eh_storage_binary2_constraint(device)

        setattr(model, f"eh_{device.lower()}_storage_balance", pyo.Constraint(model.t, rule=balance_rule))
        setattr(model, f"eh_{device.lower()}_final_soc", pyo.Constraint(rule=final_soc_rule))
        setattr(model, f"eh_{device.lower()}_binary1", pyo.Constraint(model.t, rule=binary1_rule))
        setattr(model, f"eh_{device.lower()}_binary2", pyo.Constraint(model.t, rule=binary2_rule))

    ################################################################################
    # %% BUILDINGS ENERGY BALANCES (Power balance, kW)
    ################################################################################

    # Electricity balance
    def electricity_balance_rule(model, n, t):
        """Electricity demand must be met by power producing devices and/or residual load"""
        # Calculate total charging and discharging for EVs connected to building n
        total_ev_charge = sum(model.ch_ev[ev_id, t] for ev_id in model.EVs if ev_data[ev_id]["building_id"] == n)
        total_ev_discharge = sum(model.dch_ev[ev_id, t] for ev_id in model.EVs if ev_data[ev_id]["building_id"] == n)

        return (model.res_dom_power[n, t] + model.power_dom["PV", n, t] + model.power_dom["CHP", n, t] + model.power_dom["FC", n, t]
                + model.dch_dom["BAT", n, t] + total_ev_discharge
                == model.power_dom["Elec_dem", n, t] + total_ev_charge + model.power_dom["HP", n, t] +
                model.power_dom["EH", n, t] + model.ch_dom["BAT", n, t] + model.res_dom_feed[n, t])

    # Heating Balance
    def heating_balance_rule(model, n, t):
        """Heating demand must be met by heat producing devices and/or heat grid"""
        return (model.heat_dom["CHP", n, t] + model.heat_dom["HP", n, t] + model.heat_dom["BOI", n, t] + model.heat_dom["BBOI", n, t]
                + model.heat_dom["OBOI", n, t] + model.heat_dom["H2BOI", n, t] + model.heat_dom["EH", n, t] + model.heat_dom["STC", n, t]
                + model.heat_dom["FC", n, t] + model.dch_dom["TES", n, t] + model.heat_dom["heat_grid", n, t] + model.heat_dom["DH", n, t]
                ) == model.heat_dom["Heating_dem", n, t] + model.heat_dom["DHW_dem", n, t] + model.ch_dom["TES", n, t]

    # Cooling balance
    def cooling_balance_rule(model, n, t):
        """Cooling demand must be met by compression chiller and/or heat grid"""
        return model.cool_dom["CC", n, t] + model.cool_dom["heat_grid", n, t] == model.cool_dom["Cooling_dem", n, t]

    model.electricity_balance = pyo.Constraint(model.n, model.t, rule=electricity_balance_rule,
                                               doc="Electricity balance for each building")
    model.heating_balance = pyo.Constraint(model.n, model.t, rule=heating_balance_rule,
                                           doc="Heating balance for each building")
    model.cooling_balance = pyo.Constraint(model.n, model.t, rule=cooling_balance_rule,
                                           doc="Cooling balance for each building")

    ################################################################################
    # %% ENERGY HUB ENERGY BALANCES
    ################################################################################
    # Heat balance
    def eh_heating_balance_rule(model, t):
        return (model.eh_heat_STC[t] + model.eh_heat_HP[t] + model.eh_heat_EB[t] + model.eh_heat_CHP[t]
                + model.eh_heat_BOI[t] + model.eh_heat_GHP[t] + model.eh_heat_BCHP[t] + model.eh_heat_BBOI[t]
                + model.eh_heat_WCHP[t] + model.eh_heat_WBOI[t] + model.eh_heat_FC[t] + model.eh_dch_TES[
                    t]  # Heat supply
                == model.eh_heat_to_grid[t] + model.eh_heat_AC[t] + model.eh_ch_TES[t]  # Heat demand
                )

    # The EH must supply the heat demand of the buildings connected to the grid and the loss of the network #! TODO: Combined Heat balance for the neighborhood that includs network losses?
    def eh_heat_supply_rule(model, t):
        return model.eh_heat_to_grid[t] >= sum(model.heat_dom["heat_grid", n, t] for n in model.n) + \
            network_losses_heating[t]

    # The EH must supply the cooling demand of the buildings connected to the grid
    def eh_cool_supply_rule(model, t):
        return model.eh_cool_to_grid[t] >= sum(model.cool_dom["heat_grid", n, t] for n in model.n) + \
            network_losses_cooling[t]

    # Electricity balance
    def eh_electricity_balance_rule(model, t):
        return (model.eh_power_PV[t] + model.eh_power_WT[t] + model.eh_power_WAT[t] + model.eh_power_CHP[t]
                + model.eh_power_BCHP[t] + model.eh_power_WCHP[t] + model.eh_power_FC[t] + model.eh_dch_BAT[t] +
                model.eh_power_from_grid[t]
                == model.eh_power_HP[t] + model.eh_power_EB[t] + model.eh_power_CC[t]
                + model.eh_power_ELYZ[t] + model.eh_ch_BAT[t] + model.eh_power_to_grid[t])

    # Cooling balance
    def eh_cooling_balance_rule(model, t):
        return (model.eh_cool_AC[t] + model.eh_cool_CC[t] + model.eh_dch_CTES[t]  # Cooling supply
                == model.eh_cool_to_grid[t] + model.eh_ch_CTES[t]  # Cooling demand
                )

    # gas balance
    def eh_gas_balance_rule(model, t):
        return (model.eh_gas_from_grid[t] + model.eh_gas_SAB[t] + model.eh_dch_GS[t]  # Gas supply
                == model.eh_gas_CHP[t] + model.eh_gas_BOI[t] + model.eh_gas_GHP[t] + model.eh_ch_GS[t] +
                model.eh_gas_to_grid[t])  # Gas demand

    # hydrogen balance
    def eh_hydrogen_balance_rule(model, t):
        return (model.eh_hydrogen_ELYZ[t] + model.eh_hydrogen_from_neighborhood[t] + model.eh_dch_H2S[t]
                == model.eh_hydrogen_FC[t] + model.eh_hydrogen_SAB[t] + model.eh_ch_H2S[t] +
                model.eh_hydrogen_to_neighborhood[t])

    # biomass balance
    def eh_biomass_balance_rule(model, t):
        return model.eh_biom_import[t] == model.eh_biom_BCHP[t] + model.eh_biom_BBOI[t]

    # Waste balance
    def eh_waste_balance_rule(model, t):
        return model.eh_waste_import[t] == model.eh_waste_WCHP[t] + model.eh_waste_WBOI[t]

    model.eh_heating_balance = pyo.Constraint(model.t, rule=eh_heating_balance_rule, doc="EnergyHub_heat_balance")
    model.eh_heat_supply = pyo.Constraint(model.t, rule=eh_heat_supply_rule, doc="EnergyHub_heat_supply_to_buildings")
    model.eh_cool_supply = pyo.Constraint(model.t, rule=eh_cool_supply_rule,
                                          doc="EnergyHub_cooling_supply_to_buildings")
    model.eh_electricity_balance = pyo.Constraint(model.t, rule=eh_electricity_balance_rule,
                                                  doc="EnergyHub_electricity_balance")
    model.eh_cooling_balance = pyo.Constraint(model.t, rule=eh_cooling_balance_rule, doc="EnergyHub_cooling_balance")
    model.eh_gas_balance = pyo.Constraint(model.t, rule=eh_gas_balance_rule, doc="EnergyHub_gas_balance")
    model.eh_hydrogen_balance = pyo.Constraint(model.t, rule=eh_hydrogen_balance_rule, doc="EnergyHub_hydrogen_balance")
    model.eh_biomass_balance = pyo.Constraint(model.t, rule=eh_biomass_balance_rule, doc="EnergyHub_biomass_balance")
    model.eh_waste_balance = pyo.Constraint(model.t, rule=eh_waste_balance_rule, doc="EnergyHub_waste_balance")

    ################################################################################
    # NEIGHBORHOOD ENERGY BALANCES
    ################################################################################

    # Electricity balance neighborhood (Power balance in Watt)
    def neighborhood_elec_balance_rule(model, t):
        return (model.residual_feed[t] + model.power_from_grid[t] + model.eh_power_to_grid[t]
                == model.residual_power[t] + model.power_to_grid[t] + model.eh_power_from_grid[t])

    def trafo_binary1_rule(model, t):
        return model.power_from_grid[t] <= model.yTrafo[t] * (siteData["trafoMax_W"] if siteData["enable_trafoMax_W"] else BIG_M)

    def trafo_binary2_rule(model, t):
        return model.power_to_grid[t] <= (1 - model.yTrafo[t]) * (siteData["trafoMax_W"] if siteData["enable_trafoMax_W"] else BIG_M)

    model.neighborhood_elec_balance = pyo.Constraint(model.t, rule=neighborhood_elec_balance_rule,
                                                     doc="Power_balance_neighborhood")
    model.trafo_binary1 = pyo.Constraint(model.t, rule=trafo_binary1_rule, doc="Power_limitation_from_grid")
    model.trafo_binary2 = pyo.Constraint(model.t, rule=trafo_binary2_rule, doc="Power_limitation_to_grid")

    # Gas balance neighborhood (Power balance in Watt)
    def neighborhood_gas_balance_rule(model, t):
        return (model.power_gas_from_grid[t] + model.eh_gas_to_grid[t]
                == model.eh_gas_from_grid[t] + sum(
                    model.gas_dom["CHP", n, t] + model.gas_dom["BOI", n, t] for n in model.n))

    def neighborhood_biomass_balance_rule(model, t):
        return (model.power_biomass_import[t]  # Biomass supply
                == model.eh_biom_import[t] +
                sum(model.biomass_dom["BBOI", n, t] for n in model.n)  # Biomass demand
                )

    def neighborhood_hydrogen_balance_rule(model, t):
        return (model.power_hydrogen_grid_import[t] + model.eh_hydrogen_to_neighborhood[t] ==
                model.eh_hydrogen_from_neighborhood[t]
                + sum(model.hydrogen_dom["H2BOI", n, t] + model.hydrogen_dom["FC", n, t] for n in model.n))

    def neighborhood_oil_balance_rule(model, t):
        return model.power_oil_import[t] == sum(model.oil_dom["OBOI", n, t] for n in model.n)

    def neighborhood_waste_balance_rule(model, t):
        return model.power_waste_import[t] == model.eh_waste_import[t]  # No Waste-Export

    def neighborhood_district_heat_rule(model, t):
        return model.power_district_heating_import[t] == sum(model.dh_heat_supply[n, t] for n in model.n)

    model.neighborhood_gas_balance = pyo.Constraint(model.t, rule=neighborhood_gas_balance_rule,
                                                    doc="Gas_balance_neighborhood")
    model.neighborhood_biomass_balance = pyo.Constraint(model.t, rule=neighborhood_biomass_balance_rule,
                                                        doc="Biomass_balance_neighborhood")
    model.neighborhood_hydrogen_balance = pyo.Constraint(model.t, rule=neighborhood_hydrogen_balance_rule,
                                                         doc="Hydrogen_balance_neighborhood")
    model.neighborhood_oil_balance = pyo.Constraint(model.t, rule=neighborhood_oil_balance_rule,
                                                    doc="Oil_balance_neighborhood")
    model.neighborhood_waste_balance = pyo.Constraint(model.t, rule=neighborhood_waste_balance_rule,
                                                      doc="Waste_balance_neighborhood")
    model.neighborhood_district_heat = pyo.Constraint(model.t, rule=neighborhood_district_heat_rule, doc="District_heat_balance_neighborhood")
    ################################################################################
    # %% Summation of energy sources
    ################################################################################

    def from_grid_total_gas_rule(model):
        return model.from_grid_total_gas == dt * sum(model.power_gas_from_grid[t] for t in model.t) / 1000

    def from_grid_total_el_rule(model):
        return model.from_grid_total_el == dt * sum(model.power_from_grid[t] for t in model.t) / 1000

    def to_grid_total_el_rule(model):
        return model.to_grid_total_el == dt * sum(model.power_to_grid[t] for t in model.t) / 1000

    def from_grid_total_hydrogen_rule(model):
        return model.from_grid_total_hydrogen == dt * sum(model.power_hydrogen_grid_import[t] for t in model.t) / 1000

    def total_biomass_used_rule(model):
        return model.total_biomass_used == dt * sum(model.power_biomass_import[t] for t in model.t) / 1000

    def total_waste_used_rule(model):
        return model.total_waste_used == dt * sum(model.power_waste_import[t] for t in model.t) / 1000

    def total_oil_used_rule(model):
        return model.total_oil_used == dt * sum(model.power_oil_import[t] for t in model.t) / 1000

    def total_district_heat_used_rule(model):
        return model.total_district_heat_used == dt * sum(model.power_district_heating_import[t] for t in model.t) / 1000

    def to_grid_total_el_buildings_rule(model):
        return model.to_grid_total_el_buildings == dt * sum(model.res_dom_feed[n, t] for n in model.n for t in model.t) / 1000

    def from_grid_total_el_buildings_rule(model):
        return model.from_grid_total_el_buildings == dt * sum(model.res_dom_power[n, t] for n in model.n for t in model.t) / 1000

    def to_grid_total_el_eh_rule(model):
        return model.to_grid_total_el_eh == dt * sum(model.eh_power_to_grid[t] for t in model.t) / 1000

    def from_grid_total_el_eh_rule(model):
        return model.from_grid_total_el_eh == dt * sum(model.eh_power_from_grid[t] for t in model.t) / 1000

    model.from_grid_total_gas_constraint = pyo.Constraint(rule=from_grid_total_gas_rule, doc="from_grid_total_gas")
    model.from_grid_total_el_constraint = pyo.Constraint(rule=from_grid_total_el_rule, doc="from_grid_total_el")
    model.to_grid_total_el_constraint = pyo.Constraint(rule=to_grid_total_el_rule, doc="to_grid_total_el")
    model.from_grid_total_hydrogen_constraint = pyo.Constraint(rule=from_grid_total_hydrogen_rule, doc="from_grid_total_hydrogen")
    model.total_biomass_used_constraint = pyo.Constraint(rule=total_biomass_used_rule, doc="total_biomass_used")
    model.total_waste_used_constraint = pyo.Constraint(rule=total_waste_used_rule, doc="total_waste_used")
    model.total_oil_used_constraint = pyo.Constraint(rule=total_oil_used_rule, doc="total_oil_used")
    model.to_grid_total_el_buildings_constraint = pyo.Constraint(rule=to_grid_total_el_buildings_rule, doc="to_grid_total_el_buildings")
    model.from_grid_total_el_buildings_constraint = pyo.Constraint(rule=from_grid_total_el_buildings_rule, doc="from_grid_total_el_buildings")
    model.to_grid_total_el_eh_constraint = pyo.Constraint(rule=to_grid_total_el_eh_rule, doc="to_grid_total_el_eh")
    model.from_grid_total_el_eh_constraint = pyo.Constraint(rule=from_grid_total_el_eh_rule, doc="from_grid_total_el_eh")
    model.total_district_heat_used_constraint = pyo.Constraint(rule=total_district_heat_used_rule, doc="total_district_heat_used")

    ################################################################################
    # Daily Peak Calculation
    ################################################################################

    # Daily peak needs to be larger or equal than the power from the grid at each time step of the day
    def daily_peak_basic_rule(model, d, t_local):
        d_int = int(d)
        t_local_int = int(t_local)
        day_start = d_int * int(24 / dt)
        if day_start + t_local_int < len(time_steps):
            t_global = day_start + t_local_int
            return model.daily_peak[d] >= model.power_from_grid[t_global]
        else:
            return pyo.Constraint.Skip

    # Only one peak per day is allowed
    def daily_peak_selection_rule(model, d):
        d_int = int(d)
        day_start = d_int * int(24 / dt)
        day_end = min(day_start + int(24 / dt), len(time_steps))
        return sum(model.is_daily_peak[d, t] for t in range(day_start, day_end)) == 1

    # Implementation of BIG-M constraints for daily peak upper bound
    def daily_peak_upper_bound_rule(model, d, t):
        d_int = int(d)
        day_start = d_int * int(24 / dt)
        day_end = min(day_start + int(24 / dt), len(time_steps))

        if day_start <= t < day_end:
            return model.daily_peak[d] <= model.power_from_grid[t] + BIG_M * (1 - model.is_daily_peak[d, t])
        else:
            return pyo.Constraint.Skip

    # Implementation of BIG-M constraints for daily peak lower bound
    def daily_peak_lower_bound_rule(model, d, t):
        d_int = int(d)
        day_start = d_int * int(24 / dt)
        day_end = min(day_start + int(24 / dt), len(time_steps))

        if day_start <= t < day_end:
            return model.daily_peak[d] >= model.power_from_grid[t] - BIG_M * (1 - model.is_daily_peak[d, t])
        else:
            return pyo.Constraint.Skip

    def peaksum_rule(model):
        return model.peaksum == sum(model.daily_peak[d] for d in model.days)

    # Create constraints for each day and time step within that day for the daily peak calculation and sum
    model.t_day = pyo.Set(initialize=range(int(24 / dt)))
    model.daily_peak_constraints = pyo.Constraint(model.days, model.t_day, rule=daily_peak_basic_rule,
                                                  doc="Daily_peak_rule")
    model.daily_peak_selection = pyo.Constraint(model.days, rule=daily_peak_selection_rule, doc="Daily_peak_selection")
    model.daily_peak_upper_bound = pyo.Constraint(model.days, model.t, rule=daily_peak_upper_bound_rule,
                                                  doc="Daily_peak_upper_bound")
    model.daily_peak_lower_bound = pyo.Constraint(model.days, model.t, rule=daily_peak_lower_bound_rule,
                                                  doc="Daily_peak_lower_bound")
    model.peaksum_constraint = pyo.Constraint(rule=peaksum_rule, doc="Sum_of_all_daily_peaks")

    ################################################################################
    # DEFINE OBJECTIVE FUNCTION
    ################################################################################

    # Operational costs
    def operational_costs_rule(model):
        return (model.operational_costs == model.from_grid_total_el_buildings * ecoData["price_supply_el"]
                - model.to_grid_total_el_buildings * ecoData["revenue_feed_in_el"]
                + model.from_grid_total_el_eh * ecoData["price_supply_el_eh"]
                - model.to_grid_total_el_eh * ecoData["revenue_feed_in_el_eh"]
                + model.from_grid_total_gas * ecoData["price_supply_gas"]
                + model.from_grid_total_hydrogen * ecoData["price_hydrogen"]
                + model.total_biomass_used * ecoData["price_biomass"]
                + model.total_waste_used * ecoData["price_waste"]
                + model.total_oil_used * ecoData["price_oil"]
                + model.total_district_heat_used * ecoData["price_district_heat"]
                )

    # Emissions
    def co2_total_rule(model):
        return (model.co2_total == model.from_grid_total_el * ecoData["co2_el_grid"]
                + model.from_grid_total_gas * ecoData["co2_gas"]
                + model.from_grid_total_hydrogen * ecoData["co2_hydrogen"]
                + model.total_biomass_used * ecoData["co2_biom"]
                + model.total_waste_used * ecoData["co2_waste"]
                + model.total_oil_used * ecoData["co2_oil"]
                + model.total_district_heat_used * ecoData["co2_district_heat"]
                )

    # Select objective
    def obj_rule(model):
        if model_param_eh["optim_focus"] == 0:
            return model.obj == model.operational_costs
        elif model_param_eh["optim_focus"] == 1:
            return model.obj == model.co2_total

    model.operational_costs_constraint = pyo.Constraint(rule=operational_costs_rule, doc="Total_amount_operational_costs")
    model.co2_total_constraint = pyo.Constraint(rule=co2_total_rule, doc="Total_amount_CO2_emissions")
    model.obj_constraint = pyo.Constraint(rule=obj_rule, doc="Objective_function")
    model.objective = pyo.Objective(expr=model.obj, sense=pyo.minimize, doc="Objective_function_minimization")

    print("Pyomo model built successfully")
    return model


def solve_model_and_extract_results(model, data):
    """
    Solves the Pyomo model and extracts results in the same format as the original Gurobi code.
    """
    # Folder to save model and results
    result_dir = "results"
    if not os.path.exists(result_dir):
        os.makedirs(result_dir)

    lp_filename = os.path.join(result_dir, "opti_central_model.lp")
    model.write(lp_filename, io_options={'symbolic_solver_labels': True})

    # temporary log-file for the solver
    solver_log_path = os.path.join(result_dir, "solver_output.log")
    # Path for error file
    errorfile_path = os.path.join(result_dir, "errorfile_opti_central.txt")

    # Solve the model
    solver, solver_options = solver_config.create_solver()
    results = solver.solve(model, tee=True, logfile=solver_log_path, options=solver_options)

    # Check if solution is optimal, otherwise write an error file
    term_cond = results.solver.termination_condition
    if term_cond == pyo.TerminationCondition.infeasible:
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
        with open('errorfile.txt', 'w') as f:
            f.write('Model is unbounded\n')
        return None
    elif results.solver.termination_condition == pyo.TerminationCondition.optimal:
        print("Model solved to optimality")
    else:
        print(f"Solver status: {results.solver.termination_condition}")
        with open('errorfile.txt', 'w') as f:
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

    solution_file = os.path.join(result_dir, 'solution_file.txt')
    write_solution_file(model, solution_file)

    # Extract results
    timeData = data.time
    time_steps = range(int(timeData["clusterLength"] / timeData["timeResolution"]))
    dt = timeData["timeResolution"] / timeData["dataResolution"]
    nbuildings = len(data.district)

    # Extract results from the model into a single results dictionary
    results_dict = {}

    # Overall energy imports and exports in kWh
    results_dict["from_grid_total_el"] = pyo.value(model.from_grid_total_el)
    results_dict["to_grid_total_el"] = pyo.value(model.to_grid_total_el)
    results_dict["from_grid_total_gas"] = pyo.value(model.from_grid_total_gas)
    results_dict["from_grid_total_hydrogen"] = pyo.value(model.from_grid_total_hydrogen)
    results_dict["total_biomass_used"] = pyo.value(model.total_biomass_used)
    results_dict["total_oil_used"] = pyo.value(model.total_oil_used)
    results_dict["total_waste_used"] = pyo.value(model.total_waste_used)
    results_dict["total_district_heat_used"] = pyo.value(model.total_district_heat_used)


    # energy imports and exports per time step in W
    results_dict["P_dem_total"] = []
    results_dict["P_inj_total"] = []
    results_dict["P_dem_gcp"] = []
    results_dict["P_inj_gcp"] = []
    results_dict["P_gas_total"] = []
    results_dict["P_hydrogen_total"] = []
    results_dict["P_biomass_total"] = []
    results_dict["P_oil_total"] = []
    results_dict["P_waste_total"] = []
    results_dict["P_district_heat_total"] = []

    for t in time_steps:
        results_dict["P_dem_total"].append(round(pyo.value(model.residual_power[t]), 0))
        results_dict["P_inj_total"].append(round(pyo.value(model.residual_feed[t]), 0))
        results_dict["P_dem_gcp"].append(round(pyo.value(model.power_from_grid[t]), 0))
        results_dict["P_inj_gcp"].append(round(pyo.value(model.power_to_grid[t]), 0))
        results_dict["P_gas_total"].append(round(pyo.value(model.power_gas_from_grid[t]), 0))
        results_dict["P_hydrogen_total"].append(round(pyo.value(model.power_hydrogen_grid_import[t]), 0))
        results_dict["P_biomass_total"].append(round(pyo.value(model.power_biomass_import[t]), 0))
        results_dict["P_oil_total"].append(round(pyo.value(model.power_oil_import[t]), 0))
        results_dict["P_waste_total"].append(round(pyo.value(model.power_waste_import[t]), 0))
        results_dict["P_district_heat_total"].append(round(pyo.value(model.power_district_heating_import[t]), 0))

    # Overall costs and emissions
    results_dict["Cost_total"] = pyo.value(model.operational_costs)
    results_dict["Emission_total"] = pyo.value(model.co2_total)

    ################################################################################
    # Energy Hub results
    ################################################################################

    def helper_func_extract_eh_results(model, results_dict, variable_type, device_set, time_steps):
        """
        Helper function to extract Energy Hub results for a specific variable type for all devices in the device set.

        Args:
            model: Pyomo model with solved variables
            results_dict: Dictionary to store results
            energy_type: String name for the energy type (e.g., "eh_hydrogen", "eh_power")
            device_set: Set of devices for this energy type
            time_steps: Range of time steps
        """
        results_dict[variable_type] = {}
        for device in device_set:
            results_dict[variable_type][device] = []
            for t in time_steps:
                results_dict[variable_type][device].append(
                    round(pyo.value(model.__getattribute__(f"{variable_type}_{device}")[t]), 0)
                )

    # Extract results for each energy type using the helper function
    helper_func_extract_eh_results(model=model, results_dict=results_dict, variable_type="eh_power",
                                   device_set=EH_ECS_POWER, time_steps=time_steps)
    helper_func_extract_eh_results(model=model, results_dict=results_dict, variable_type="eh_heat",
                                   device_set=EH_ECS_HEAT, time_steps=time_steps)
    helper_func_extract_eh_results(model=model, results_dict=results_dict, variable_type="eh_cool",
                                   device_set=EH_ECS_COOL, time_steps=time_steps)
    helper_func_extract_eh_results(model=model, results_dict=results_dict, variable_type="eh_gas",
                                   device_set=EH_ECS_GAS, time_steps=time_steps)
    helper_func_extract_eh_results(model=model, results_dict=results_dict, variable_type="eh_hydrogen",
                                   device_set=EH_ECS_HYDROGEN, time_steps=time_steps)
    helper_func_extract_eh_results(model=model, results_dict=results_dict, variable_type="eh_biom",
                                   device_set=EH_ECS_BIOMASS, time_steps=time_steps)
    helper_func_extract_eh_results(model=model, results_dict=results_dict, variable_type="eh_waste",
                                   device_set=EH_ECS_WASTE, time_steps=time_steps)

    # Storage results
    helper_func_extract_eh_results(model=model, results_dict=results_dict, variable_type="eh_ch",
                                   device_set=EH_ECS_STORAGE, time_steps=time_steps)
    helper_func_extract_eh_results(model=model, results_dict=results_dict, variable_type="eh_dch",
                                   device_set=EH_ECS_STORAGE, time_steps=time_steps)
    helper_func_extract_eh_results(model=model, results_dict=results_dict, variable_type="eh_soc",
                                   device_set=EH_ECS_STORAGE, time_steps=time_steps)

    ################################################################################
    # Building results
    ################################################################################

    # Add results for each building
    for n in range(nbuildings):
        results_dict[n] = {}
        results_dict[n]["res_load"] = []
        results_dict[n]["res_inj"] = []
        results_dict[n]["res_gas"] = []
        results_dict[n]["res_biomass"] = []
        results_dict[n]["res_oil"] = []
        results_dict[n]["res_hydrogen"] = []
        for t in time_steps:
            results_dict[n]["res_load"].append(round(pyo.value(model.res_dom_power[n, t]), 0))
            results_dict[n]["res_inj"].append(round(pyo.value(model.res_dom_feed[n, t]), 0))
            gas_total = pyo.value(model.gas_dom["BOI", n, t]) + pyo.value(
                model.gas_dom["CHP", n, t])  # ! This should not be here -> Doubling of Code possible
            results_dict[n]["res_gas"].append(round(gas_total, 0))
            results_dict[n]["res_biomass"].append(round(pyo.value(model.biomass_dom["BBOI", n, t]), 0))
            results_dict[n]["res_oil"].append(round(pyo.value(model.oil_dom["OBOI", n, t]), 0))
            hydrogen_total = pyo.value(model.hydrogen_dom["H2BOI", n, t]) + pyo.value(
                model.hydrogen_dom["FC", n, t])  # ! This should not be here -> Doubling of Code possible
            results_dict[n]["res_hydrogen"].append(round(hydrogen_total, 0))

    # Heat devices
    for n in range(nbuildings):
        for device in ECS_HEAT:
            results_dict[n][device] = {}
            results_dict[n][device]["Q_th"] = []
            for t in time_steps:
                results_dict[n][device]["Q_th"].append(round(pyo.value(model.heat_dom[device, n, t]), 0))

    # Cooling devices
    for n in range(nbuildings):
        for device in ECS_COOL:
            results_dict[n][device] = {}
            results_dict[n][device]["Q_cool"] = []
            for t in time_steps:
                results_dict[n][device]["Q_cool"].append(round(pyo.value(model.cool_dom[device, n, t]), 0))

    # HP modes
    for n in range(nbuildings):
        for device in HP_MODI:
            results_dict[n][device] = {}
            results_dict[n][device]["Q_th"] = []
            results_dict[n][device]["P_el"] = []
            for t in time_steps:
                results_dict[n][device]["Q_th"].append(round(pyo.value(model.heat_mode[device, n, t]), 0))
                results_dict[n][device]["P_el"].append(round(pyo.value(model.power_mode[device, n, t]), 0))

    # Power devices
    for n in range(nbuildings):
        for device in ECS_POWER:
            results_dict[n][device] = {}
            results_dict[n][device]["P_el"] = []
            for t in time_steps:
                results_dict[n][device]["P_el"].append(round(pyo.value(model.power_dom[device, n, t]), 0))

    # Storage devices
    for n in range(nbuildings):
        for device in ECS_STORAGE:
            results_dict[n][device] = {}
            for v in ("ch", "dch", "soc"):
                results_dict[n][device][v] = []
            for t in time_steps:
                results_dict[n][device]["ch"].append(pyo.value(model.ch_dom[device, n, t]))
                results_dict[n][device]["dch"].append(pyo.value(model.dch_dom[device, n, t]))
                results_dict[n][device]["soc"].append(pyo.value(model.soc_dom[device, n, t]))

    results_dict["peaksum"] = pyo.value(model.peaksum)
    results_dict["daily_peak"] = {}
    for d in [0, 1, 2, 3, 4, 5, 6]:
        results_dict["daily_peak"][d] = pyo.value(model.daily_peak[d])

    return results_dict
