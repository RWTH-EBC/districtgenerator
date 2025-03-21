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
import districtgenerator.functions.clustering_medoid as clustering
import time
import os
import sys
import copy
import pandas as pd

def load_params(data):

    result_dict = {}
    # import model parameters
    central_device_data = copy.deepcopy(data.central_device_data)
    param = copy.deepcopy(data.params_ehdo_model)
    ecoData = copy.deepcopy(data.ecoData)
    param_uncl = {}  # unclustered time series for weather data

    ################################################################
    # GENERAL PARAMETERS
    physics = data.physics
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

    for b in range(len(data.district)):
        if b == 0:
            heating = data.district[b]["user"].heat / 1000 # kW
            cooling = data.district[b]["user"].cooling * 0 / 1000 # kW
            dhw = data.district[b]["user"].dhw / 1000 # kW
            electricityAppliances = data.district[b]["user"].elec / 1000 # kW

        else:
            heating += data.district[b]["user"].heat / 1000 # kW
            cooling += data.district[b]["user"].cooling * 0 / 1000 # kW
            dhw += data.district[b]["user"].dhw / 1000 # kW
            electricityAppliances += data.district[b]["user"].elec / 1000 # kW

    heat_total = heating + dhw
    electricity_total = electricityAppliances
    dem_uncl["heat"] = heat_total
#    dem_uncl["cool"] = cooling
    dem_uncl["cool"] = cooling * 0

    dem_uncl["power"] = electricity_total
    for k in ["heat", "cool", "power"]:
        param["peak_"+k] = np.max(dem_uncl[k])
    param["peak_hydrogen"] = 0
    df = pd.DataFrame.from_dict(dem_uncl)

    # Save the DataFrame to an Excel file
    df.to_excel('dem_total.xlsx', index=False)

    ################################################################
    # DESIGN CLUSTERING

    # calculate cluster time horizon
    clusterHorizon = int((data.time["clusterLength"] / data.time["timeResolution"]))
    adjustedHorizon = clusterHorizon
    while adjustedHorizon <= len(data.site["T_e"]):
        adjustedHorizon += clusterHorizon
    adjustedHorizon -= clusterHorizon
    adjustedHorizon = int(adjustedHorizon)

    # Collect the time series to be clustered
    time_series = [dem_uncl["heat"][0:adjustedHorizon], dem_uncl["cool"][0:adjustedHorizon], dem_uncl["power"][0:adjustedHorizon],
                   param_uncl["T_air"][0:adjustedHorizon], param_uncl["GHI"][0:adjustedHorizon], param_uncl["DHI"][0:adjustedHorizon],
                   param_uncl["wind_speed"][0:adjustedHorizon]]

    # Only building demands and weather data are clustered using k-medoids algorithm; secondary time series are clustered manually according to k-medoids result
    inputs = np.array(time_series)
    # Execute k-medoids algorithm
    print("Cluster design days...")
    start = time.time()
    (clustered_series, nc, y, z, inputsTransformed) = clustering.cluster(inputs,
                                     data.time["clusterNumber"],
                                     len_cluster=int(clusterHorizon),
                                     norm = 2,
                                     mip_gap = 0.02,
                                     )

    print("Design clustering finished. (" + str(time.time()-start) + ")\n")

    dem = {}
    dem["heat"] = clustered_series[0]
    dem["cool"] = clustered_series[1]
    dem["power"] = clustered_series[2]
    param["T_air"] = clustered_series[3]
    param["GHI"] = clustered_series[4]
    param["DHI"] = clustered_series[5]
    param["wind_speed"] = clustered_series[6]

    # Save number of design days and design-day matrix
    param["day_weights"] = nc
    param["day_matrix"] = z

    # Get sigma-function: for each day of the year, find the corresponding design day
    # Get list of days which are used as design days
    typedays = np.zeros(data.time["clusterNumber"], dtype = np.int32)
    n = 0
    for d in range(52):
        if any(z[d]):
            typedays[n] = d
            n += 1
    # Assign each day of the year to its design day
    sigma = np.zeros(52, dtype = np.int32)
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

    all_models = {}
    for key, value in central_device_data.items():
        all_models[key] = {
            "enabled": value.get("feasible", False),
            "CCOP_feasible": value.get("CCOP_feasible", False),
            "ASHP_feasible": value.get("ASHP_feasible", False),
            "CSV_feasible": value.get("CSV_feasible", False),
            "eta": value.get("eta", 0) * 100,
            "life_time": value.get("life_time", 0),
            "inv_var": value.get("inv_var", 0),
            "cost_om": value.get("cost_om", 0) * 100,
            "max_area": value.get("max_area", 0),
            "min_area": value.get("min_area", 0),
            "G_stc": value.get("G_stc", 0),
            "min_cap": value.get("min_cap", 0),
            "max_cap": value.get("max_cap", 0),
            "min_vol": value.get("min_vol", 0),
            "max_vol": value.get("max_vol", 0),
            "h_coeff": value.get("h_coeff", 0),
            "hub_h": value.get("hub_h", 0),
            "ref_h": value.get("ref_h", 0),
            "norm_power": value.get("norm_power", 0),
            "potential": value.get("potential", 0),
            "eta_el": value.get("eta_el", 0) * 100,
            "eta_th": value.get("eta_th", 0) * 100,
            "COP": value.get("COP", 0),
            "ASHP_carnot_eff": value.get("ASHP_carnot_eff", 0),
            "ASHP_supply_temp": value.get("ASHP_supply_temp", 0),
            "COP_const": value.get("COP_const", 0),
            "sto_loss": value.get("sto_loss", 0) * 100,
            "delta_T": value.get("delta_T", 0),
            "soc_init": value.get("soc_init", 0),
            "enable_heat_diss": value.get("enable_heat_diss", False)
        }

    devs = {}

    # Photovoltaics
    devs["PV"] = {
        "feasible": all_models["PV"]["enabled"],
        "eta": all_models["PV"]["eta"] / 100,
        "life_time": all_models["PV"]["life_time"],
        "inv_var": all_models["PV"]["inv_var"],
        "cost_om": all_models["PV"]["cost_om"] / 100,
        "max_area": all_models["PV"]["max_area"],
        "min_area": all_models["PV"]["min_area"],
        # For correlation between area and peak power:
        "G_stc": 1,  # kW/m^2,  solar radiation under standard test conditions (STC)
    }
    #devs["PV"]["norm_power"] = solar_modeling.pv_system(direct_tilted_irrad = param["GHI"] - param["DHI"],
    #                                             diffuse_tilted_irrad = param["DHI"],
    #                                             theta = 0,
    #                                             T_air = param["T_air"],
    #                                             wind_speed = param["wind_speed"]
    #                                             )/1e3  # in kW/kWp

    # Wind turbine
    devs["WT"] = {
        "feasible": all_models["WT"]["enabled"],
        "inv_var": all_models["WT"]["inv_var"],
        "life_time": all_models["WT"]["life_time"],
        "cost_om": all_models["WT"]["cost_om"] / 100,
        "min_cap": all_models["WT"]["min_cap"],
        "max_cap": all_models["WT"]["max_cap"],
        "h_coeff": all_models["WT"]["h_coeff"],  # hellmann_coeff
        "hub_h": all_models["WT"]["hub_h"],
        "ref_h": all_models["WT"]["ref_h"],
    }
    devs["WT"]["norm_power"] = calc_WT_power(devs, param, data.time["clusterNumber"])  # relative power between 0 and 1

    # Hydropower
    devs["WAT"] = {
        "feasible": all_models["WAT"]["enabled"],
        "inv_var": all_models["WAT"]["inv_var"],
        "life_time": all_models["WAT"]["life_time"],
        "cost_om": all_models["WAT"]["cost_om"] / 100,
        "min_cap": all_models["WAT"]["min_cap"],
        "max_cap": all_models["WAT"]["max_cap"],
        "potential": all_models["WAT"]["potential"],
    }

    # Solar thermal collector
    devs["STC"] = {
        "feasible": all_models["STC"]["enabled"],
        "eta": all_models["STC"]["eta"] / 100,
        "inv_var": all_models["STC"]["inv_var"],
        "life_time": all_models["STC"]["life_time"],
        "cost_om": all_models["STC"]["cost_om"] / 100,
        "max_area": all_models["STC"]["max_area"],
        "min_area": all_models["STC"]["min_area"],
        # For correlation between area and peak power:
        "G_stc": 1,  # kW/m^2,  solar radiation under standard test conditions (STC)
    }

    ### Natural gas ###

    # CHP
    devs["CHP"] = {
        "feasible": all_models["CHP"]["enabled"],
        "inv_var": all_models["CHP"]["inv_var"],
        "eta_el": all_models["CHP"]["eta_el"] / 100,
        "eta_th": all_models["CHP"]["eta_th"] / 100,
        "life_time": all_models["CHP"]["life_time"],
        "cost_om": all_models["CHP"]["cost_om"] / 100,
        "min_cap": all_models["CHP"]["min_cap"],
        "max_cap": all_models["CHP"]["max_cap"],
    }

    # Gas boiler
    devs["BOI"] = {
        "feasible": all_models["BOI"]["enabled"],
        "inv_var": all_models["BOI"]["inv_var"],
        "eta_th": all_models["BOI"]["eta_th"] / 100,
        "life_time": all_models["BOI"]["life_time"],
        "cost_om": all_models["BOI"]["cost_om"] / 100,
        "min_cap": all_models["BOI"]["min_cap"],
        "max_cap": all_models["BOI"]["max_cap"],
    }

    # Gas heat pump
    devs["GHP"] = {
        "feasible": all_models["GHP"]["enabled"],
        "inv_var": all_models["GHP"]["inv_var"],
        "COP": all_models["GHP"]["COP"],
        "life_time": all_models["GHP"]["life_time"],
        "cost_om": all_models["GHP"]["cost_om"] / 100,
        "min_cap": all_models["GHP"]["min_cap"],
        "max_cap": all_models["GHP"]["max_cap"],
    }

    ### Heating and cooling ###

    # Heat pump (depending on investment and COP, it can be air source or ground source heat pump)
    devs["HP"] = {
        "feasible": all_models["HP"]["enabled"],
        "CCOP_feasible": all_models["HP"]["CCOP_feasible"],
        "ASHP_feasible": all_models["HP"]["ASHP_feasible"],
        "CSV_feasible": all_models["HP"]["CSV_feasible"],
        "COP_const": all_models["HP"]["COP_const"],
        "inv_var": all_models["HP"]["inv_var"],
        "life_time": all_models["HP"]["life_time"],
        "cost_om": all_models["HP"]["cost_om"] / 100,
        "min_cap": all_models["HP"]["min_cap"],
        "max_cap": all_models["HP"]["max_cap"],
    }
    # COP assignment

    COP = np.ones((data.time["clusterNumber"], clusterHorizon))
    eta_carnot = all_models["HP"]["ASHP_carnot_eff"] / 100
    supply_temp = all_models["HP"]["ASHP_supply_temp"]
    for d in range(data.time["clusterNumber"]):
        for t in range(clusterHorizon):
            COP[d][t] = eta_carnot * (supply_temp + 273.15) / (supply_temp - param["T_air"][d][t])
    devs["HP"]["COP"] = COP

    # COP assignment
    if all_models["HP"]["enabled"]:
        #if (not all_models["HeatPump"]["CCOP_feasible"]) and (not all_models["HeatPump"]["ASHP_feasible"]) and (
        #not all_models["HeatPump"]["CSV_feasible"]):
        #    flags["HeatPump_no_COP_option_selected"] = False
        if all_models["HP"]["CCOP_feasible"]:
            devs["HP"]["COP"] = np.ones((data.time["clusterNumber"], clusterHorizon)) * all_models["HP"]["COP_const"]
        elif all_models["HP"]["ASHP_feasible"]:
            COP = np.ones((data.time["clusterNumber"], clusterHorizon))
            eta_carnot = all_models["HP"]["ASHP_carnot_eff"] / 100
            supply_temp = all_models["HP"]["ASHP_supply_temp"]
            for d in range(data.time["clusterNumber"]):
                for t in range(clusterHorizon):
                    COP[d][t] = eta_carnot * (supply_temp + 273.15) / (supply_temp - param["T_air"][d][t])
            devs["HP"]["COP"] = COP

        elif all_models["HP"]["CSV_feasible"]:
            #try:
                COP_unclustered = np.loadtxt(os.path.join(os.path.dirname(data.srcPath), 'districtgenerator', 'data',
                                                          'coefficient_of_performance.txt'))
                # Cluster COP time series
                COP_clustered = np.zeros((data.time["clusterNumber"], clusterHorizon))
                for d in range(data.time["clusterNumber"]):
                    for t in range(24):
                        COP_clustered[d][t] = COP_unclustered[clusterHorizon * typedays[d] + t]
                # Replace original time series with the clustered one
                devs["HP"]["COP"] = COP_clustered
            #except:
            #    flags["HeatPump_invalid_file"] = False
    else:
        devs["HP"]["COP"] = np.ones((data.time["clusterNumber"], clusterHorizon))


    # Electric boiler
    devs["EB"] = {
        "feasible": all_models["EB"]["enabled"],
        "inv_var": all_models["EB"]["inv_var"],
        "eta_th": all_models["EB"]["eta_th"] / 100,
        "life_time": all_models["EB"]["life_time"],
        "cost_om": all_models["EB"]["cost_om"] / 100,
        "min_cap": all_models["EB"]["min_cap"],
        "max_cap": all_models["EB"]["max_cap"],
    }

    # Compression chiller
    devs["CC"] = {
        "feasible": all_models["CC"]["enabled"],
        "inv_var": all_models["CC"]["inv_var"],
        "COP": all_models["CC"]["COP"],
        "life_time": all_models["CC"]["life_time"],
        "cost_om": all_models["CC"]["cost_om"] / 100,
        "min_cap": all_models["CC"]["min_cap"],
        "max_cap": all_models["CC"]["max_cap"],
    }

    # Absorption chiller
    devs["AC"] = {
        "feasible": all_models["AC"]["enabled"],
        "inv_var": all_models["AC"]["inv_var"],
        "eta_th": all_models["AC"]["eta_th"],
        "life_time": all_models["AC"]["life_time"],
        "cost_om": all_models["AC"]["cost_om"] / 100,
        "min_cap": all_models["AC"]["min_cap"],
        "max_cap": all_models["AC"]["max_cap"],
    }

    ### Biomass and waste ###

    # Biomass CHP
    devs["BCHP"] = {
        "feasible": all_models["BCHP"]["enabled"],
        "inv_var": all_models["BCHP"]["inv_var"],
        "eta_el": all_models["BCHP"]["eta_el"] / 100,
        "eta_th": all_models["BCHP"]["eta_th"] / 100,
        "life_time": all_models["BCHP"]["life_time"],
        "cost_om": all_models["BCHP"]["cost_om"] / 100,
        "min_cap": all_models["BCHP"]["min_cap"],
        "max_cap": all_models["BCHP"]["max_cap"],
    }

    # Biomass boiler
    devs["BBOI"] = {
        "feasible": all_models["BBOI"]["enabled"],
        "inv_var": all_models["BBOI"]["inv_var"],
        "eta_th": all_models["BBOI"]["eta_th"] / 100,
        "life_time": all_models["BBOI"]["life_time"],
        "cost_om": all_models["BBOI"]["cost_om"] / 100,
        "min_cap": all_models["BBOI"]["min_cap"],
        "max_cap": all_models["BBOI"]["max_cap"],
    }

    # Waste CHP
    devs["WCHP"] = {
        "feasible": all_models["WCHP"]["enabled"],
        "inv_var": all_models["WCHP"]["inv_var"],
        "eta_el": all_models["WCHP"]["eta_el"] / 100,
        "eta_th": all_models["WCHP"]["eta_th"] / 100,
        "life_time": all_models["WCHP"]["life_time"],
        "cost_om": all_models["WCHP"]["cost_om"] / 100,
        "min_cap": all_models["WCHP"]["min_cap"],
        "max_cap": all_models["WCHP"]["max_cap"],
    }

    # Waste boiler
    devs["WBOI"] = {
        "feasible": all_models["WBOI"]["enabled"],
        "inv_var": all_models["WBOI"]["inv_var"],
        "eta_th": all_models["WBOI"]["eta_th"] / 100,
        "life_time": all_models["WBOI"]["life_time"],
        "cost_om": all_models["WBOI"]["cost_om"] / 100,
        "min_cap": all_models["WBOI"]["min_cap"],
        "max_cap": all_models["WBOI"]["max_cap"],
    }

    ### Hydrogen ###

    # Electrolyzer
    devs["ELYZ"] = {
        "feasible": all_models["ELYZ"]["enabled"],
        "inv_var": all_models["ELYZ"]["inv_var"],
        "eta_el": all_models["ELYZ"]["eta_el"] / 100,
        "life_time": all_models["ELYZ"]["life_time"],
        "cost_om": all_models["ELYZ"]["cost_om"] / 100,
        "min_cap": all_models["ELYZ"]["min_cap"],
        "max_cap": all_models["ELYZ"]["max_cap"],
    }

    # Fuel cell
    devs["FC"] = {
        "feasible": all_models["FC"]["enabled"],
        "inv_var": all_models["FC"]["inv_var"],
        "eta_el": all_models["FC"]["eta_el"] / 100,
        "eta_th": all_models["FC"]["eta_th"] / 100,
        "life_time": all_models["FC"]["life_time"],
        "cost_om": all_models["FC"]["cost_om"] / 100,
        "min_cap": all_models["FC"]["min_cap"],
        "max_cap": all_models["FC"]["max_cap"],
        "enable_heat_diss": all_models["FC"]["enable_heat_diss"],
    }

    # Hydrogen storage
    devs["H2S"] = {
        "feasible": all_models["H2S"]["enabled"],
        "inv_var": all_models["H2S"]["inv_var"],
        "sto_loss": 0,
        "life_time": all_models["H2S"]["life_time"],
        "cost_om": all_models["H2S"]["cost_om"] / 100,
        "min_cap": all_models["H2S"]["min_cap"],
        "max_cap": all_models["H2S"]["max_cap"],
    }

    # Sabatier reactor
    devs["SAB"] = {
        "feasible": all_models["SAB"]["enabled"],
        "inv_var": all_models["SAB"]["inv_var"],
        "eta": all_models["SAB"]["eta"] / 100,
        "life_time": all_models["SAB"]["life_time"],
        "cost_om": all_models["SAB"]["cost_om"] / 100,
        "min_cap": all_models["SAB"]["min_cap"],
        "max_cap": all_models["SAB"]["max_cap"],
    }

    ### Storages ###

    # Heat thermal energy storage
    devs["TES"] = {
        "feasible": all_models["TES"]["enabled"],
        "inv_var": all_models["TES"]["inv_var"] / (
                    param["rho_w"] * param["c_w"] * all_models["TES"]["delta_T"] / 3600),  # EUR/kWh
        "sto_loss": all_models["TES"]["sto_loss"] / 100,
        "life_time": all_models["TES"]["life_time"],
        "cost_om": all_models["TES"]["cost_om"] / 100,
        "min_cap": all_models["TES"]["min_vol"] * param["rho_w"] * param["c_w"] * all_models[
            "TES"]["delta_T"] / 3600,  # kWh
        "max_cap": all_models["TES"]["max_vol"] * param["rho_w"] * param["c_w"] * all_models[
            "TES"]["delta_T"] / 3600,  # kWh
        "delta_T": all_models["TES"]["delta_T"],  # K
        "soc_init": 0.5,  # ---,              maximum initial state of charge
    }

    # Cold thermal energy storage
    devs["CTES"] = {
        "feasible": all_models["CTES"]["enabled"],
        "inv_var": all_models["CTES"]["inv_var"] / (
                    param["rho_w"] * param["c_w"] * all_models["CTES"]["delta_T"] / 3600),  # EUR/kWh
        "sto_loss": all_models["CTES"]["sto_loss"] / 100,
        "life_time": all_models["CTES"]["life_time"],
        "cost_om": all_models["CTES"]["cost_om"] / 100,
        "min_cap": all_models["CTES"]["min_vol"] * param["rho_w"] * param["c_w"] * all_models[
            "CTES"]["delta_T"] / 3600,  # kWh
        "max_cap": all_models["CTES"]["max_vol"] * param["rho_w"] * param["c_w"] * all_models[
            "CTES"]["delta_T"] / 3600,  # kWh
        "delta_T": all_models["CTES"]["delta_T"],  # K,
        "soc_init": 0.5,  # ---,              maximum initial state of charge
    }

    # Battery
    devs["BAT"] = {
        "feasible": all_models["BAT"]["enabled"],
        "inv_var": all_models["BAT"]["inv_var"],
        "life_time": all_models["BAT"]["life_time"],
        "cost_om": all_models["BAT"]["cost_om"] / 100,
        "min_cap": all_models["BAT"]["min_cap"],
        "max_cap": all_models["BAT"]["max_cap"],
        "sto_loss": 0,  # 1/h,              standby losses over one time step
        "soc_init": 0.5,  # ---,              maximum initial state of charge
    }

    # Gas storage
    devs["GS"] = {
        "feasible": all_models["GS"]["enabled"],
        "inv_var": all_models["GS"]["inv_var"],  # EUR/kWh
        "life_time": all_models["GS"]["life_time"],
        "cost_om": all_models["GS"]["cost_om"] / 100,
        "min_cap": all_models["GS"]["min_cap"],  # kWh
        "max_cap": all_models["GS"]["max_cap"],  # kWh
        "sto_loss": 0,  # 1/h,              standby losses over one time step
        "soc_init": 0.5,  # ---,              maximum initial state of charge
    }

    ################################################################
    ### Energy costs ###
    param["price_supply_el"]    = ecoData["price_supply_el"]
    param["revenue_feed_in_el"] = ecoData["revenue_feed_in_el"]
    param["price_biomass"]      = ecoData["price_biomass"]
    param["price_waste"]        = ecoData["price_waste"]
    param["price_supply_gas"]   = ecoData["price_supply_gas"]
    param["price_hydrogen"]     = ecoData["price_hydrogen"]

    ### Ecological impact ###
    param["co2_el_grid"]     = ecoData["co2_el_grid"] # kg/kWh
    param["co2_gas"]         = ecoData["co2_gas"] # kg/kWh
    param["co2_biom"]        = ecoData["co2_biom"] # kg/kWh
    param["co2_waste"]       = ecoData["co2_waste"]  # kg/kWh
    param["co2_hydrogen"]    = ecoData["co2_hydrogen"]  # kg/kWh

    ################################################################
    # INITIALIZE CALCULATION

    # Calculate annual investments
    devs, param = calc_annual_investment(devs, param)
    # Calculate values for post-processing
    result_dict = calc_monthly_dem(dem_uncl, param_uncl, result_dict)

    return param, devs, dem, result_dict



#%% SUB-FUNCTIONS ##################################################

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
    for m in ["heat", "cool", "power"]:
        monthly_dem[m] = {}
        year_peak[m] = int(np.max(dem_uncl[m]))
        year_sum[m] = int(np.sum(dem_uncl[m]) / 1000)
        for month in range(12):
            monthly_dem[m][month_tuple[month]] = sum(dem_uncl[m][t] for t in range(days_sum[month]*24, days_sum[month+1]*24)) / 1000

    result_dict["monthly_dem"] = monthly_dem # in kW
    result_dict["year_peak"] = year_peak # in W
    result_dict["year_sum"] = year_sum # in kW


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


def calc_WT_power(devs, param, clusterNumber):
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
    for d in range(clusterNumber):
        for t in range(24*7):
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
