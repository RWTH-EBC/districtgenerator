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

import numpy as np
import math
import EHDO.clustering_medoid as clustering
import time
import os
import csv
import json
import copy
import sys
import EHDO.solar_modeling as solar_modeling


def load_params(data, demands_district):

    # TODO: Änderungen von Marius kontrollieren!
    srcPath = os.path.dirname(os.path.abspath(__file__))

    result_dict = {}

    # import model parameters from json-file
    param = {}
    with open(os.path.join(os.path.dirname(srcPath), 'data', 'model_parameters_EHDO.json')) as json_file:
        jsonData = json.load(json_file)
        for subData in jsonData:
            if subData["name"] != "ref":
                param[subData["name"]] = subData["value"]
            else:
                param[subData["name"]] = {}
                for subSubData in subData["value"]:
                    param[subData["name"]][subSubData["name"]] = subSubData["value"]

    param_uncl = {}  # unclustered time series for weather data

    path_input_data = "input_data"

    ################################################################
    # GENERAL PARAMETERS

    physics = {}
    with open(os.path.join(os.path.dirname(srcPath), 'data', 'physics_data.json')) as json_file:
        jsonData = json.load(json_file)
        for subData in jsonData:
            physics[subData["name"]] = subData["value"]

    param["c_w"] = physics["c_p_water"]  # kJ/(kgK)
    param["rho_w"] = physics["rho_water"]  # kg/m3

    ################################################################
    # LOAD WEATHER DATA

    param_uncl["T_air"] = data.site["T_e"]
    param_uncl["GHI"] = data.site["SunTotal"]
    param_uncl["DHI"] = data.site["SunDiffuse"]
    param_uncl["wind_speed"] = data.site["wind_speed"]

    ################################################################
    # LOAD DEMANDS

    dem_uncl = {}

    heat_district = demands_district["heat"] + demands_district["dhw"]
    cooling_district = demands_district["cooling"]
    electricity_district = demands_district["elec"]

    dem_uncl["heat"] = heat_district
    dem_uncl["cool"] = cooling_district
    dem_uncl["power"] = electricity_district
    dem_uncl["hydrogen"] = np.zeros(len(heat_district))

    for k in ["heat", "cool", "power", "hydrogen"]:
        param["peak_"+k] = np.max(dem_uncl[k])


    ################################################################
    # DESIGN DAY CLUSTERING

    param["n_clusters"] = data.time["clusterNumber"]  # Number of design days

    # Collect the time series to be clustered
    time_series = [dem_uncl["heat"], dem_uncl["cool"], dem_uncl["power"], dem_uncl["hydrogen"], param_uncl["T_air"], param_uncl["GHI"], param_uncl["DHI"], param_uncl["wind_speed"]]
    # Only building demands and weather data are clustered using k-medoids algorithm; secondary time series are clustered manually according to k-medoids result
    inputs_clustering = np.array(time_series)
    # Execute k-medoids algorithm
    print("Cluster design days...")
    start = time.time()
    (clustered_series, nc, z) = clustering.cluster(inputs_clustering,
                                     param["n_clusters"],
                                     norm = 2,
                                     mip_gap = 0.02,
                                     )
    print("Design day clustering finished. (" + str(time.time()-start) + ")\n")

    dem = {}
    dem["heat"] = clustered_series[0]
    dem["cool"] = clustered_series[1]
    dem["power"] = clustered_series[2]
    dem["hydrogen"] = clustered_series[3]
    param["T_air"] = clustered_series[4]
    param["GHI"] = clustered_series[5]
    param["DHI"] = clustered_series[6]
    param["wind_speed"] = clustered_series[7]

    # Save number of design days and design-day matrix
    param["day_weights"] = nc
    param["day_matrix"] = z

    # Get sigma-function: for each day of the year, find the corresponding design day
    # Get list of days which are used as design days
    typedays = np.zeros(param["n_clusters"], dtype = np.int32)
    n = 0
    for d in range(365):
        if any(z[d]):
            typedays[n] = d
            n += 1
    # Assign each day of the year to its design day
    sigma = np.zeros(365, dtype = np.int32)
    for day in range(len(sigma)):
        d = np.where(z[:,day] == 1 )[0][0]
        sigma[day] = np.where(typedays == d)[0][0]
    param["sigma"] = sigma

    # Cluster secondary time series
    #for k in ["T_air", "GHI", "wind_speed"]:
    #    series_clustered = np.zeros((param["n_clusters"], 24))
    #    for d in range(param["n_clusters"]):
    #        for t in range(24):
    #            series_clustered[d][t] = param_uncl[k][24*typedays[d]+t]
        # Replace original time series with the clustered one
    #    param[k] = series_clustered

    ################################################################
    # LOAD TECHNICAL PARAMETERS


    # load technical parameter from json-file
    # load data about central devices from JSON-file
    techParams = {}
    with open(os.path.join(os.path.dirname(srcPath), 'data', 'technical_parameters_EHDO.json')) as json_file:
        jsonData = json.load(json_file)
        for subData in jsonData:
            techParams[subData["abbreviation"]] = {}
            for subsubData in subData["specifications"]:
                techParams[subData["abbreviation"]][subsubData["name"]] = subsubData["value"]

    devs = copy.deepcopy(techParams)

    # Photovoltaics
    if devs["PV"]["feasible"] == "True":
        devs["PV"]["feasible"] = True
    elif devs["PV"]["feasible"] == "False":
        devs["PV"]["feasible"] = False
    else:
        sys.exit("Invalid input!")
    # For correlation between area and peak power
    devs["PV"]["G_stc"] = 1  # kW/m^2,  solar radiation under standard test conditions (STC)

    devs["PV"]["norm_power"] = solar_modeling.pv_system(direct_tilted_irrad = param["GHI"] - param["DHI"],
                                                 diffuse_tilted_irrad = param["DHI"],
                                                 theta = 0,
                                                 T_air = param["T_air"],
                                                 wind_speed = param["wind_speed"]
                                                 )/1e3  # in kW/kWp


    # Wind turbine
    if devs["WT"]["feasible"] == "True":
        devs["WT"]["feasible"] = True
    elif devs["WT"]["feasible"] == "False":
        devs["WT"]["feasible"] = False
    else:
        sys.exit("Invalid input!")

    devs["WT"]["norm_power"] = calc_WT_power(devs, param) # relative power between 0 and 1

    # Hydropower
    devs["WAT"] = {
        "feasible":  False,  # Technology enabled/disabled
        "inv_var":   1000,   # EUR/kW
        "life_time": 40,     # a, life time
        "cost_om":   0.02,   # ---
        "min_cap":   0,      # kW_el
        "max_cap":   10000,  # kW_el
        "potential": 1000,   # kW_el
        }

    # Solar thermal collector
    if devs["STC"]["feasible"] == "True":
        devs["STC"]["feasible"] = True
    elif devs["STC"]["feasible"] == "False":
        devs["STC"]["feasible"] = False
    else:
        sys.exit("Invalid input!")
    # For correlation between area and peak power
    devs["STC"]["G_stc"] = 1  # kW/m^2,  solar radiation under standard test conditions (STC)

    devs["STC"]["specific_heat"] = solar_modeling.collector_system(direct_tilted_irrad = param["GHI"] - param["DHI"],
                                                              diffuse_tilted_irrad = param["DHI"],
                                                              theta = 0,
                                                              T_air = param["T_air"]
                                                              )/1e3


    ### Heating and cooling ###

    # Heat pump (depending on investment and COP, it can be air source or ground source heat pump)
    if devs["HP"]["feasible"] == "True":
        devs["HP"]["feasible"] = True
    elif devs["HP"]["feasible"] == "False":
        devs["HP"]["feasible"] = False
    else:
        sys.exit("Invalid input!")
    devs["HP"]["COP"] = devs["HP"]["COP"] * np.ones((param["n_clusters"], 24))

    # Electric boiler
    if devs["EB"]["feasible"] == "True":
        devs["EB"]["feasible"] = True
    elif devs["EB"]["feasible"] == "False":
        devs["EB"]["feasible"] = False
    else:
        sys.exit("Invalid input!")

    # Compression chiller
    devs["CC"] = {
        "feasible":  False,
        "inv_var":   600,
        "COP":       5,
        "life_time": 20,
        "cost_om":   0.05,
        "min_cap":   0,
        "max_cap":   10000,  # kW_th
    }

    # Absorption chiller
    devs["AC"] = {
        "feasible":  False,
        "inv_var":   750,
        "eta_th":    0.6,
        "life_time": 20,
        "cost_om":   0.05,
        "min_cap":   0,
        "max_cap":   10000,  # kW_th
    }


    ### Natural gas ###

    # CHP
    if devs["CHP"]["feasible"] == "True":
        devs["CHP"]["feasible"] = True
    elif devs["CHP"]["feasible"] == "False":
        devs["CHP"]["feasible"] = False
    else:
        sys.exit("Invalid input!")

    # Gas boiler
    if devs["BOI"]["feasible"] == "True":
        devs["BOI"]["feasible"] = True
    elif devs["BOI"]["feasible"] == "False":
        devs["BOI"]["feasible"] = False
    else:
        sys.exit("Invalid input!")

    # Gas heat pump
    devs["GHP"] = {
        "feasible":  False,
        "inv_var":   900,
        "COP":       1.5,
        "life_time": 20,
        "cost_om":   0.03,
        "min_cap":   0,
        "max_cap":   10000,  # kw_th,
    }


    ### Biomass and waste ###

    # Biomass CHP
    devs["BCHP"] = {
        "feasible":  False,
        "inv_var":   2000,  # kW_el
        "eta_el":    0.35,
        "eta_th":    0.5,
        "life_time": 20,
        "cost_om":   0.08,
        "min_cap":   0,
        "max_cap":   10000, # kW_el
    }

    # Biomass boiler
    devs["BBOI"] = {
        "feasible":  False,
        "inv_var":   300,
        "eta_th":    0.95,
        "life_time": 20,
        "cost_om":   0.04,
        "min_cap":   0,
        "max_cap":   10000,
    }

    # Waste CHP
    devs["WCHP"] = {
        "feasible":  False,
        "inv_var":   2000,  # kW_el
        "eta_el":    0.35,
        "eta_th":    0.5,
        "life_time": 20,
        "cost_om":   0.08,
        "min_cap":   0,
        "max_cap":   10000, # kW_el
    }

    # Waste boiler
    devs["WBOI"] = {
        "feasible":  False,
        "inv_var":   300,
        "eta_th":    0.95,
        "life_time": 20,
        "cost_om":   0.04,
        "min_cap":   0,
        "max_cap":   10000,
    }

    ### Hydrogen ###

    # Electrolyzer
    devs["ELYZ"] = {
        "feasible":  False,
        "inv_var":   1500,
        "eta_el":    0.7,
        "life_time": 20,
        "cost_om":   0.08,
        "min_cap":   0,
        "max_cap":   10000,  # kW_el
    }

    # Fuel cell
    devs["FC"] = {
        "feasible":  False,
        "inv_var":   4000,
        "eta_el":    0.35,
        "eta_th":    0.5,
        "life_time": 20,
        "cost_om":   0.05,
        "min_cap":   0,
        "max_cap":   10000,
        "enable_heat_diss": True,
    }

    # Hydrogen storage
    devs["H2S"] = {
        "feasible":  False,
        "inv_var":   150,  # EUR/kWh
        "sto_loss":  0,
        "life_time": 20,
        "cost_om":   0.05,
        "min_cap":   0,
        "max_cap":   100000,  # kWh
    }

    # Sabatier reactor
    devs["SAB"] = {
        "feasible":  False,
        "inv_var":   800,
        "eta":       83,
        "life_time": 20,
        "cost_om":   0.05,
        "min_cap":   0,
        "max_cap":   10000,
    }


    ### Storages ###

    # Heat thermal energy storage
    if devs["TES"]["feasible"] == "True":
        devs["TES"]["feasible"] = True
    elif devs["TES"]["feasible"] == "False":
        devs["TES"]["feasible"] = False
    else:
        sys.exit("Invalid input!")
    deltaT = devs["TES"]["delta_T"]
    devs["TES"]["min_cap"] = devs["TES"]["min_volume"] * param["rho_w"] * param["c_w"] * deltaT / 3600  # kWh
    devs["TES"]["max_cap"] = devs["TES"]["max_volume"] * param["rho_w"] * param["c_w"] * deltaT / 3600  # kWh
    devs["TES"]["inv_var"] = devs["TES"]["inv_var"] / (param["rho_w"] * param["c_w"] * deltaT / 3600)  # EUR/kWh
    devs["TES"]["soc_init"] = 0.5  # [-], maximum initial state of charge

    # Cold thermal energy storage
    deltaT = 10
    devs["CTES"] = {
        "feasible":  False,
        "inv_var":   500 / (param["rho_w"] * param["c_w"] * deltaT / 3600), # EUR/kWh
        "sto_loss":  0.005,
        "life_time": 20,
        "cost_om":   0.01,
        "min_cap":   0 * param["rho_w"] * param["c_w"] * deltaT / 3600, # kWh
        "max_cap":   100000 * param["rho_w"] * param["c_w"] * deltaT / 3600, # kWh
        "delta_T":   deltaT, # K,
        "soc_init":  0.5,  # ---,              maximum initial state of charge
    }

    # Battery
    if devs["BAT"]["feasible"] == "True":
        devs["BAT"]["feasible"] = True
    elif devs["BAT"]["feasible"] == "False":
        devs["BAT"]["feasible"] = False
    else:
        sys.exit("Invalid input!")
    devs["BAT"]["sto_loss"] = 0  # [1/h], standby losses over one time step
    devs["BAT"]["soc_init"] = 0.5,  # [-], maximum initial state of charge

    # Gas storage
    devs["GS"] = {
        "feasible":  False,
        "inv_var":   150, # EUR/kWh
        "life_time": 20,
        "cost_om":   0.01,
        "min_cap":   0, # kWh
        "max_cap":   10000, # kWh
        "sto_loss":  0,    # 1/h,              standby losses over one time step
        "soc_init":  0.5,  # ---,              maximum initial state of charge
    }


    ################################################################
    # LOAD MODEL PARAMETERS

    # load economic and ecologic data (of the district generator)
    ecoData = {}
    with open(os.path.join(os.path.dirname(srcPath), 'data', 'eco_data.json')) as json_file:
        jsonData = json.load(json_file)
        for subData in jsonData:
            ecoData[subData["name"]] = subData["value"]

    ### Energy costs ###
    # Electricity costs
    if param["enable_supply_el"] == "True":
        param["enable_supply_el"] = True
    elif param["enable_supply_el"] == "False":
        param["enable_supply_el"] = False
    else:
        sys.exit("Invalid input!")
    param["price_supply_el"] = ecoData["C_dem_electricity"]

    param["price_cap_el"] = 0  # kEUR/MW
    if param["enable_feed_in_el"] == "True":
        param["enable_feed_in_el"] = True
    elif param["enable_feed_in_el"] == "False":
        param["enable_feed_in_el"] = False
    else:
        sys.exit("Invalid input!")
    param["revenue_feed_in_el"] = ecoData["C_feed_electricity"]

    param["enable_cap_limit_el"] = False
    param["cap_limit_el"]        = 1000  # kW

    param["enable_supply_limit_el"] = False
    param["supply_limit_el"]        = 100000 # kWh/a


    # Natural gas
    if param["enable_supply_gas"] == "True":
        param["enable_supply_gas"] = True
    elif param["enable_supply_gas"] == "False":
        param["enable_supply_gas"] = False
    else:
        sys.exit("Invalid input!")
    param["price_supply_gas"] = ecoData["C_dem_gas"]
    param["price_cap_gas"] = 0
    param["enable_feed_in_gas"]      = False
    param["revenue_feed_in_gas"]     = 0.01

    param["enable_cap_limit_gas"]    = False
    param["cap_limit_gas"]           = 100  # kW
    param["enable_supply_limit_gas"] = False
    param["supply_limit_gas"]        = 100000 # kWh/a


    # Biomass
    param["enable_supply_biomass"]    = False
    param["price_biomass"]            = 0.2  # EUR/kWh
    param["enable_supply_limit_biom"] = False
    param["supply_limit_biomass"]     = 100000  #kWh


    # Hydrogen
    param["enable_supply_hydrogen"]       = False
    param["price_hydrogen"]               = 0.4  # EUR/kWh
    param["enable_supply_limit_hydrogen"] = False
    param["supply_limit_hydrogen"]        = 100000  #kWh


    # Waste
    param["enable_supply_waste"]       = False
    param["price_waste"]               = 0.05  # EUR/kWh
    param["enable_supply_limit_waste"] = False
    param["supply_limit_waste"]        = 100000  #kWh


    ### Ecological impact ###
    """param["co2_tax"]         = 180 / 1000"""  # EUR/kg
    param["co2_el_grid"]     = ecoData["Emi_elec"] # kg/kWh
    """param["co2_el_feed_in"]  = 0.3""" # kg/kWh
    param["co2_gas"]         = ecoData["Emi_gas"] # kg/kWh
    param["co2_gas_feed_in"] = 0.2 # kg/kWh
    param["co2_biom"]        = 0.6 # kg/kWh
    param["co2_waste"]       = 0.7 / 1000  # kg/kWh
    param["co2_hydrogen"]    = 0.4 / 1000  # kg/kWh


    ### General ###
    """param["optim_focus"]       = 0
    param["interest_rate"]     = 0.05
    param["observation_time"]  = 20"""
    param["peak_dem_met_conv"] = True

    ### Reference scenario ###
    """param["ref"] = {}
    param["ref"]["enable_hp"]  = False
    param["ref"]["cop_hp"]     = 5
    param["ref"]["cop_cc"]     = 5
    param["ref"]["enable_chp"] = False"""


    ################################################################
    # INITIALIZE CALCULATION

    # Calculate annual investments
    devs, param = calc_annual_investment(devs, param)

    # Calculate reference scenario
    result_dict = calc_reference(devs, dem, param, dem_uncl, result_dict)

    # print("=== PARAMETER ===")
    # print(param)
    # print("=== TECHNOLOGIES ===")
    # print(devs)

    # Calculate values for post-processing
    result_dict = calc_monthly_dem(dem_uncl, param_uncl, result_dict)

    return param, devs, dem, result_dict



#%% SUB-FUNCTIONS ##################################################


def calc_reference(devs, dem, param, dem_uncl, result_dict):
    """
    Calculation of reference scenario/system.
    """

    days = range(param["n_clusters"])
    time_steps = range(24)

    el_chp = {}
    gas_chp = {}
    heat_chp= {}
    el_hp = {}
    heat_hp = {}
    heat_boiler = {}
    gas_boiler = {}
    cool_chiller = {}
    el_chiller = {}
    h2_elyz = {}
    el_elyz = {}
    el_dem = {}
    gas_dem = {}
    for d in days:
        el_chp[d] = np.zeros(24)
        gas_chp[d] = np.zeros(24)
        heat_chp[d]= np.zeros(24)
        el_hp[d] = np.zeros(24)
        heat_hp[d] = np.zeros(24)
        heat_boiler[d] = np.zeros(24)
        gas_boiler[d] = np.zeros(24)
        cool_chiller[d] = np.zeros(24)
        h2_elyz[d] = np.zeros(24)
        el_elyz[d] = np.zeros(24)
        el_chiller[d] = np.zeros(24)
        el_dem[d] = np.zeros(24)
        gas_dem[d] = np.zeros(24)
        for t in time_steps:

            # Chiller
            cool_chiller[d][t] = dem["cool"][d][t]
            el_chiller[d][t] = cool_chiller[d][t] / param["ref"]["cop_cc"]

            # Electrolyzer
            h2_elyz[d][t] = dem["hydrogen"][d][t]
            el_elyz[d][t] = h2_elyz[d][t] / devs["ELYZ"]["eta_el"]

            # Total electricity demand to be covered in each time step
            total_power_dem = dem["power"][d][t] + el_chiller[d][t] + el_elyz[d][t]

            # Case 1: CHP and HP enabled
            if param["ref"]["enable_chp"] and param["ref"]["enable_hp"]:
                #print("Case 1: CHP and HP enabled")

                # Boiler not operated
                heat_boiler[d][t] = 0
                gas_boiler[d][t] = 0

                hp_runs = (dem["heat"][d][t] > (total_power_dem/devs["CHP"]["eta_el"]*devs["CHP"]["eta_th"]))

                if hp_runs:
                    #print("Heat pump runs")
                    el_hp[d][t] = (dem["heat"][d][t] - (total_power_dem/devs["CHP"]["eta_el"]*devs["CHP"]["eta_th"])) / ((devs["CHP"]["eta_th"]/devs["CHP"]["eta_el"]) + param["ref"]["cop_hp"])
                    heat_hp[d][t] = param["ref"]["cop_hp"] * el_hp[d][t]
                    el_chp[d][t] = el_hp[d][t] + total_power_dem
                    gas_chp[d][t] = el_chp[d][t] / devs["CHP"]["eta_el"]
                    heat_chp[d][t] = gas_chp[d][t] * devs["CHP"]["eta_th"]
                    el_dem[d][t] = 0

                else:  # if HP is not running
                    #print("Heat pump does not run")
                    # Heat pump not operated
                    el_hp[d][t] = 0
                    heat_hp[d][t] = 0

                    # CHP runs at part-load and covers heating demand exactly, electricity drawn from grid
                    heat_chp[d][t] = dem["heat"][d][t]
                    gas_chp[d][t] = heat_chp[d][t] / devs["CHP"]["eta_th"]
                    el_chp[d][t] = gas_chp[d][t] * devs["CHP"]["eta_el"]

            # Case 2: CHP and BOI enabled
            elif param["ref"]["enable_chp"] and (not param["ref"]["enable_hp"]):
                #print("Case 2: CHP and BOI enabled")
                # Heat pump not operated
                el_hp[d][t] = 0
                heat_hp[d][t] = 0

                # check if CHP covers heat demand alone
                boi_runs = (total_power_dem / devs["CHP"]["eta_el"] * devs["CHP"]["eta_th"]) < dem["heat"][d][t]

                # CHP runs at part-load due to low heating demand, electricity drawn from grid
                if boi_runs:
                    #print("Boiler runs")
                    el_chp[d][t] = total_power_dem
                    gas_chp[d][t] = total_power_dem / devs["CHP"]["eta_el"]
                    heat_chp[d][t] = gas_chp[d][t] * devs["CHP"]["eta_th"]
                    heat_boiler[d][t] = dem["heat"][d][t] - heat_chp[d][t]
                    gas_boiler[d][t] = heat_boiler[d][t] / devs["BOI"]["eta_th"]

                else:  # if BOI is not running
                    #print("Boiler does not run")
                    heat_boiler[d][t] = 0
                    gas_boiler[d][t] = 0

                    heat_chp[d][t] = dem["heat"][d][t]
                    gas_chp[d][t] = heat_chp[d][t] / devs["CHP"]["eta_th"]
                    el_chp[d][t] = gas_chp[d][t] * devs["CHP"]["eta_el"]


            # Case 3: HP enabled (no CHP)
            elif (not param["ref"]["enable_chp"]) and param["ref"]["enable_hp"]:
                #print("Case 3: HP enabled (no CHP)")
                # CHP and boiler not operated
                el_chp[d][t] = 0
                gas_chp[d][t] = 0
                heat_chp[d][t] = 0
                heat_boiler[d][t] = 0
                gas_boiler[d][t] = 0

                # Heat pump
                heat_hp[d][t] = dem["heat"][d][t]
                el_hp[d][t] = heat_hp[d][t] / param["ref"]["cop_hp"]

            # Case 4: BOI enabled (no CHP)
            elif (not param["ref"]["enable_chp"]) and (not param["ref"]["enable_hp"]):
                #print("Case 4: BOI enabled (no CHP)")
                # CHP and heat pump not operated
                el_chp[d][t] = 0
                gas_chp[d][t] = 0
                heat_chp[d][t] = 0
                el_hp[d][t] = 0
                heat_hp[d][t] = 0

                # Gas boiler
                heat_boiler[d][t] = dem["heat"][d][t]
                gas_boiler[d][t] = heat_boiler[d][t] / devs["BOI"]["eta_th"]


            # Sum up
            el_dem[d][t] = dem["power"][d][t] + el_chiller[d][t] + el_hp[d][t] + el_elyz[d][t] - el_chp[d][t]
            gas_dem[d][t] = gas_boiler[d][t] + gas_chp[d][t]


            #print("dem[heat][d][t] = " + str(dem["heat"][d][t]))
            #print("total_power_dem = " + str(total_power_dem))
            #print("el_chp[d][t] = " + str(el_chp[d][t]))
            #print("heat_chp[d][t] = " + str(heat_chp[d][t]))

            #print("el_hp[d][t] = " + str(el_hp[d][t]))
            #print("heat_hp[d][t] = " + str(heat_hp[d][t]))

            #print("heat_boiler[d][t] = " + str(heat_boiler[d][t]))

            #print("gas_boiler[d][t] = " + str(gas_boiler[d][t]))
            #print("gas_chp[d][t] = " + str(gas_chp[d][t]))

            #print("el_dem[d][t] = " + str(el_dem[d][t]))
            #print("gas_dem[d][t] = " + str(gas_dem[d][t]))

    # Sum up
    result_dict["ref"] = {}
    result_dict["ref"]["heat_hp_total"] = int(sum(sum(heat_hp[d][t] for t in time_steps) * param["day_weights"][d] for d in days)/1000)
    result_dict["ref"]["el_chp_total"] = int(sum(sum(el_chp[d][t] for t in time_steps) * param["day_weights"][d] for d in days)/1000)
    result_dict["ref"]["heat_boi_total"] = int(sum(sum(heat_boiler[d][t] for t in time_steps) * param["day_weights"][d] for d in days)/1000)
    result_dict["ref"]["cool_cc_total"] = int(sum(sum(cool_chiller[d][t] for t in time_steps) * param["day_weights"][d] for d in days)/1000)
    result_dict["ref"]["hydrogen_elyz_total"] = int(sum(sum(h2_elyz[d][t] for t in time_steps) * param["day_weights"][d] for d in days)/1000)
    result_dict["ref"]["el_dem_total"] = int(sum(sum(el_dem[d][t] for t in time_steps) * param["day_weights"][d] for d in days)/1000)
    result_dict["ref"]["gas_dem_total"] = int(sum(sum(gas_dem[d][t] for t in time_steps) * param["day_weights"][d] for d in days)/1000)


    ### DETERMINE CAPACITIES ###
    # Calculate all flows for the unclustered time series again, and then determine the capacities

    el_chp_uncl = np.zeros(8760)
    gas_chp_uncl = np.zeros(8760)
    heat_chp_uncl = np.zeros(8760)
    el_hp_uncl = np.zeros(8760)
    heat_hp_uncl = np.zeros(8760)
    heat_boiler_uncl = np.zeros(8760)
    gas_boiler_uncl = np.zeros(8760)
    el_elyz_uncl = np.zeros(8760)
    el_chiller_uncl = np.zeros(8760)
    el_dem_uncl = np.zeros(8760)
    gas_dem_uncl = np.zeros(8760)

    for t in range(8760):

        # Chiller and electrolyzer
        el_chiller_uncl[t] = dem_uncl["cool"][t] / param["ref"]["cop_cc"]
        el_elyz_uncl[t] = dem_uncl["hydrogen"][t] / devs["ELYZ"]["eta_el"]

        # Total electricity demand to be covered in each time step
        total_power_dem = dem_uncl["power"][t] + el_chiller_uncl[t] + el_elyz_uncl[t]

        # Case 1: CHP and HP enabled
        if param["ref"]["enable_chp"] and param["ref"]["enable_hp"]:
            #print("Case 1: CHP and HP enabled")

            # Boiler not operated
            heat_boiler_uncl[t] = 0
            gas_boiler_uncl[t] = 0

            hp_runs = (dem_uncl["heat"][t] > (total_power_dem/devs["CHP"]["eta_el"]*devs["CHP"]["eta_th"]))

            if hp_runs:
                #print("Heat pump runs")
                el_hp_uncl[t] = (dem_uncl["heat"][t] - (total_power_dem/devs["CHP"]["eta_el"]*devs["CHP"]["eta_th"])) / ((devs["CHP"]["eta_th"]/devs["CHP"]["eta_el"]) + param["ref"]["cop_hp"])
                heat_hp_uncl[t] = param["ref"]["cop_hp"] * el_hp_uncl[t]
                el_chp_uncl[t] = el_hp_uncl[t] + total_power_dem
                gas_chp_uncl[t] = el_chp_uncl[t] / devs["CHP"]["eta_el"]
                heat_chp_uncl[t] = gas_chp_uncl[t] * devs["CHP"]["eta_th"]
                el_dem_uncl[t] = 0

            else:  # if HP is not running
                #print("Heat pump does not run")
                # Heat pump not operated
                el_hp_uncl[t] = 0
                heat_hp_uncl[t] = 0

                # CHP runs at part-load and covers heating demand exactly, electricity drawn from grid
                heat_chp_uncl[t] = dem_uncl["heat"][t]
                gas_chp_uncl[t] = heat_chp_uncl[t] / devs["CHP"]["eta_th"]
                el_chp_uncl[t] = gas_chp_uncl[t] * devs["CHP"]["eta_el"]

        # Case 2: CHP and BOI enabled
        elif param["ref"]["enable_chp"] and (not param["ref"]["enable_hp"]):
            #print("Case 2: CHP and BOI enabled")
            # Heat pump not operated
            el_hp_uncl[t] = 0
            heat_hp_uncl[t] = 0

            # check if CHP covers heat demand alone
            boi_runs = (total_power_dem / devs["CHP"]["eta_el"] * devs["CHP"]["eta_th"]) < dem_uncl["heat"][t]

            # CHP runs at part-load due to low heating demand, electricity drawn from grid
            if boi_runs:
                #print("Boiler runs")
                el_chp_uncl[t] = total_power_dem
                gas_chp_uncl[t] = total_power_dem / devs["CHP"]["eta_el"]
                heat_chp_uncl[t] = gas_chp_uncl[t] * devs["CHP"]["eta_th"]
                heat_boiler_uncl[t] = dem_uncl["heat"][t] - heat_chp_uncl[t]
                gas_boiler_uncl[t] = heat_boiler_uncl[t] / devs["BOI"]["eta_th"]

            else:  # if BOI is not running
                #print("Boiler does not run")
                heat_boiler_uncl[t] = 0
                gas_boiler_uncl[t] = 0

                heat_chp_uncl[t] = dem_uncl["heat"][t]
                gas_chp_uncl[t] = heat_chp_uncl[t] / devs["CHP"]["eta_th"]
                el_chp_uncl[t] = gas_chp_uncl[t] * devs["CHP"]["eta_el"]


        # Case 3: HP enabled (no CHP)
        elif (not param["ref"]["enable_chp"]) and param["ref"]["enable_hp"]:
            #print("Case 3: HP enabled (no CHP)")
            # CHP and boiler not operated
            el_chp_uncl[t] = 0
            gas_chp_uncl[t] = 0
            heat_chp_uncl[t] = 0
            heat_boiler_uncl[t] = 0
            gas_boiler_uncl[t] = 0

            # heat pump
            heat_hp_uncl[t] = dem_uncl["heat"][t]
            el_hp_uncl[t] = heat_hp_uncl[t] / param["ref"]["cop_hp"]

        # Case 4: BOI enabled (no CHP)
        elif (not param["ref"]["enable_chp"]) and (not param["ref"]["enable_hp"]):
            #print("Case 4: BOI enabled (no CHP)")
            # CHP and heat pump not operated
            el_chp_uncl[t] = 0
            gas_chp_uncl[t] = 0
            heat_chp_uncl[t] = 0
            el_hp_uncl[t] = 0
            heat_hp_uncl[t] = 0

            # Gas boiler
            heat_boiler_uncl[t] = dem_uncl["heat"][t]
            gas_boiler_uncl[t] = heat_boiler_uncl[t] / devs["BOI"]["eta_th"]


        # Sum up
        el_dem_uncl[t] = dem_uncl["power"][t] + el_chiller_uncl[t] + el_hp_uncl[t] + el_elyz_uncl[t] - el_chp_uncl[t]
        gas_dem_uncl[t] = gas_boiler_uncl[t] + gas_chp_uncl[t]

    # Capacity is maximum of generation (of unclustered time series)
    result_dict["ref"]["chp_cap"] = int(np.max(el_chp_uncl))
    result_dict["ref"]["hp_cap"] = int(np.max(heat_hp_uncl))
    result_dict["ref"]["boiler_cap"] = int(np.max(heat_boiler_uncl))
    result_dict["ref"]["chiller_cap"] = int(np.max(dem_uncl["cool"]))
    result_dict["ref"]["elyz_cap"] = int(np.max(dem_uncl["hydrogen"]) / devs["ELYZ"]["eta_el"])

    # Electricity
    result_dict["ref"]["el_grid_cap"] = np.max([np.max(el_dem[d]) for d in days])
    result_dict["ref"]["gas_grid_cap"] = np.max([np.max(gas_dem[d]) for d in days])

    result_dict["ref"]["gas_costs"] = result_dict["ref"]["gas_grid_cap"] * param["price_cap_gas"] + result_dict["ref"]["gas_dem_total"]* 1000 * param["price_supply_gas"] # cap price and supply price

    result_dict["ref"]["el_costs"] = result_dict["ref"]["el_grid_cap"] * param["price_cap_el"] + result_dict["ref"]["el_dem_total"]*1000 * param["price_supply_el"] # cap price and supply price

    # CO2 tax
    result_dict["ref"]["co2_costs"] = result_dict["ref"]["gas_dem_total"] * param["co2_gas"] * param["co2_tax"] * 1000

    result_dict["ref"]["invest_om"] = (
        (devs["CHP"]["ann_factor"] + devs["CHP"]["cost_om"]) * devs["CHP"]["inv_var"] * result_dict["ref"]["chp_cap"]
        + (devs["BOI"]["ann_factor"] + devs["BOI"]["cost_om"]) * devs["BOI"]["inv_var"] * result_dict["ref"]["boiler_cap"]
        + (devs["HP"]["ann_factor"] + devs["HP"]["cost_om"]) * devs["HP"]["inv_var"] * result_dict["ref"]["hp_cap"]
        + (devs["CC"]["ann_factor"] + devs["CC"]["cost_om"]) * devs["CC"]["inv_var"] * result_dict["ref"]["chiller_cap"]
        + (devs["ELYZ"]["ann_factor"] + devs["ELYZ"]["cost_om"]) * devs["ELYZ"]["inv_var"] * result_dict["ref"]["elyz_cap"])

    result_dict["ref"]["tac"] = int(result_dict["ref"]["invest_om"]
                               + result_dict["ref"]["gas_costs"]
                               + result_dict["ref"]["el_costs"]
                               + result_dict["ref"]["co2_costs"])

    result_dict["ref"]["co2"] = int(result_dict["ref"]["gas_dem_total"] * param["co2_gas"] + result_dict["ref"]["el_dem_total"] * param["co2_el_grid"])  # t/a  (= t/MWh x MWh)

    # For result page listing of technologies
    result_dict["ref"]["enable_chp"] = param["ref"]["enable_chp"]
    result_dict["ref"]["enable_hp"] = param["ref"]["enable_hp"]

    return result_dict



def calc_annual_investment(devs, param):
    """
    Calculation of total investment costs including replacements (based on VDI 2067-1, pages 16-17).

    Parameters
    ----------
    dev : dictionary
        technology parameter
    param : dictionary
        economic parameters

    Returns
    -------
    annualized fix and variable investment
    """

    observation_time = param["observation_time"]
    interest_rate = param["interest_rate"]
    q = 1 + param["interest_rate"]

    # Calculate capital recovery factor
    CRF = ((q**observation_time)*interest_rate)/((q**observation_time)-1)

    # Calculate annuity factor for each device
    for device in devs.keys():

        # Get device life time
        life_time = devs[device]["life_time"]

        # Number of required replacements
        n = int(math.floor(observation_time / life_time))

        # Investment for replacements
        invest_replacements = sum((q ** (-i * life_time)) for i in range(1, n+1))

        # Residual value of final replacement
        res_value = ((n+1) * life_time - observation_time) / life_time * (q ** (-observation_time))

        # Calculate annualized investments
        if life_time > observation_time:
            devs[device]["ann_factor"] = (1 - res_value) * CRF
        else:
            devs[device]["ann_factor"] = ( 1 + invest_replacements - res_value) * CRF

    # Save capital recovery factor
    param["CRF"] = CRF

    return devs, param



def calc_monthly_dem(dem_uncl, param_uncl, result_dict):

    month_tuple = ("Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec")
    days_sum = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365]

    monthly_dem = {}
    year_peak = {}
    year_sum = {}
    for m in ["heat", "cool", "power", "hydrogen"]:
        monthly_dem[m] = {}
        year_peak[m] = int(np.max(dem_uncl[m]))
        year_sum[m] = int(np.sum(dem_uncl[m]) / 1000)
        for month in range(12):
            monthly_dem[m][month_tuple[month]] = sum(dem_uncl[m][t] for t in range(days_sum[month]*24, days_sum[month+1]*24)) / 1000

    result_dict["monthly_dem"] = monthly_dem
    result_dict["year_peak"] = year_peak
    result_dict["year_sum"] = year_sum


    #monthly_val = {}
    #year_peak = {}
    #year_sum = {}
    #for m in ["T_air", "GHI"]:  # "wind_speed"]:
    #    monthly_val[m] = {}
    #    year_peak[m] = int(np.max(param_uncl[m]))
    #    year_sum[m] = int(np.sum(param_uncl[m]) / 1000)
    #    for month in range(12):
    #        monthly_val[m][month_tuple[month]] = sum(param_uncl[m][t] for t in range(days_sum[month]*24, #days_sum[month+1]*24)) / 1000

    #result_dict["monthly_val"] = monthly_val

    return result_dict


def calc_WT_power(devs, param):
    """
    According to data sheet of wind turbine Enercon E40.
    """

    power_curve = {0:  (0.0,    0.00),
                   1:  (2.4,    0.00),
                   2:  (2.5,    1.14),
                   3:  (3.0,    4.37),
                   4:  (3.5,   10.64),
                   5:  (4.0,   18.87),
                   6:  (4.5,   29.77),
                   7:  (5.0,   40.39),
                   8:  (5.5,   52.85),
                   9:  (6.0,   69.36),
                   10: (6.5,   88.02),
                   11: (7,    112.19),
                   12: (7.5,  134.67),
                   13: (8,    165.38),
                   14: (8.5,  197.08),
                   15: (9,    236.89),
                   16: (9.5,  279.46),
                   17: (10,   328.00),
                   18: (10.5, 362.93),
                   19: (11,   396.64),
                   20: (11.5, 435.27),
                   21: (12,   465.15),
                   22: (12.5, 483.63),
                   23: (13,   495.95),
                   24: (14,   500.00),
                   25: (25,   500.00),
                   26: (25.1,   0.00),
                   27: (1000,   0.00),
                   }

    wind_speed_corr = param["wind_speed"]*(devs["WT"]["hub_h"]/devs["WT"]["ref_h"]) ** devs["WT"]["h_coeff"]  # kW

    WT_power = np.zeros(np.shape(wind_speed_corr))
    for d in range(param["n_clusters"]):
        for t in range(24):
            WT_power[d][t] = get_turbine_power(wind_speed_corr[d][t], power_curve)

    WT_power_norm = WT_power / 500  # power_curve with 500 kW as maximum output

    return WT_power_norm


def get_turbine_power(wind_speed, power_curve):
    if wind_speed <= 0:
        return 0
    if wind_speed > power_curve[len(power_curve)-1][0]:
        print("Error: Wind speed is " + str(wind_speed) + " m/s and exceeds wind power curve table.")
        return 0

    # Linear interpolation:
    for k in range(len(power_curve)):
        if power_curve[k][0] > wind_speed:
           power = (power_curve[k][1]-power_curve[k-1][1])/(power_curve[k][0]-power_curve[k-1][0]) * (wind_speed-power_curve[k-1][0]) + power_curve[k-1][1]
           break
    return power
