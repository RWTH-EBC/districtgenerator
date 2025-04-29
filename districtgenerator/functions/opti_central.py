#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created 26.02.2024
@author: Joel Schölzel
"""
import os, json
import gurobipy as gp
import time
import numpy as np

def run_opti_central(model, data, cluster):


    timeData = data.time
    ecoData = data.ecoData
    siteData = data.site
    param_dec_devs = data.decentral_device_data
    model_param_eh = data.params_ehdo_model
    central_device_data = data.central_device_data
    buildingData = data.district
    energyHubData = data.centralDevices
    heatingNetworkData = data.heat_grid_data

    now = time.time()
    # %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    # Setting up the model
    # number of buildings in neighborhood
    buildings = len(buildingData)
    time_steps = range(int(timeData["clusterLength"] / timeData["timeResolution"]))
    dt = timeData["timeResolution"] / timeData["dataResolution"]
    last_time_step = len(time_steps) - 1

    T_e = siteData["T_e_cluster"][cluster]  # ambient temperature [°C]

    # Consider network losses only if a heating/cooling network exists
    try:
        network_losses_heating = heatingNetworkData["total_losses_heating_network_cluster"][cluster] * 1000 # W
        network_losses_cooling = heatingNetworkData["total_losses_cooling_network_cluster"][cluster] * 1000 # W
    except:
        network_losses_heating = [0] * T_e
        network_losses_cooling = [0] * T_e

    Q_DHW = {}      # DHW (domestic hot water) demand [W]
    Q_heating = {}  # space heating [W]
    Q_cooling = {}  # space cooling [W]
    PV_gen = {}     # electricity generation of PV [W]
    STC_heat = {}   # electricity generation of PV [W]
    EV_dem = {}     # electricity demand electric vehicle (EV) [Wh]
    EV_charging_ondemand = {}     # charging power electric vehicle (EV) if on-demand [W]

    elec_dem = {}   # electricity demand for appliances and lighting [W]
    occ = {}
    for n in range(buildings):
        Q_DHW[n] = buildingData[n]["user"].dhw_cluster[cluster]
        Q_heating[n] = buildingData[n]["user"].heat_cluster[cluster]
        Q_cooling[n] = buildingData[n]["user"].cooling_cluster[cluster]
        elec_dem[n] = buildingData[n]["user"].elec_cluster[cluster]
        occ[n] = buildingData[n]["user"].occ_cluster[cluster]
        try:
            PV_gen[n] = buildingData[n]["generationPV_cluster"][cluster]
            STC_heat[n] = buildingData[n]["generationSTC_cluster"][cluster]
            EV_dem[n] = buildingData[n]["user"].carprofile_cluster[cluster]
            EV_charging_ondemand[n] = buildingData[n]["user"].carcharging_ondemand_cluster[cluster]
        except:
            PV_gen[n] = [0] * len(elec_dem[n])
            STC_heat[n] = [0] * len(elec_dem[n])
            EV_dem[n] = [0] * len(elec_dem[n])
            EV_charging_ondemand[n] = [0] * len(elec_dem[n])

    # %% Sets of energy conversion systems in the buildings
    ecs_heat = ("HP", "EH", "CHP", "FC", "BOI", "STC", "heat_grid")
    ecs_cool = ("CC", "heat_grid")
    ecs_power = ("HP", "EH", "CC", "CHP", "FC", "PV")  # power consuming/producing devices (photovoltaic (PV))
    ecs_gas = ("CHP", "FC", "BOI")  # gas consuming devices
    ecs_storage = ("BAT", "TES", "EV")  # battery (BAT), thermal energy storage (TES), electric vehicle (EV)
    hp_modi = ("HP35", "HP55")  # modi of the HP with different HP supply temperatures in °C

    # Create set for energy hub devices
    eh_devs = ["PV", "WT", "STC", "WAT",
                "HP", "EB", "CC", "AC",
                "CHP", "BOI", "GHP",
                "BCHP", "BBOI", "WCHP", "WBOI",
                "ELYZ", "FC", "H2S", "SAB",
                "TES", "CTES", "BAT", "GS",
                ]

    # %% TECHNICAL PARAMETERS
    soc_init = {}
    soc_init["TES"] = {}
    soc_init["BAT"] = {}
    soc_init["EV"] = {}
    for n in range(buildings):
        # Initial state of charge
        soc_init["TES"][n] = buildingData[n]["capacities"]["TES"] * param_dec_devs["TES"]["init"]  # Wh
        soc_init["BAT"][n] = buildingData[n]["capacities"]["BAT"] * param_dec_devs["BAT"]["init"]  # Wh
        soc_init["EV"][n] = buildingData[n]["capacities"]["EV"] * param_dec_devs["EV"]["init"]    # Wh

        # %% TECHNICAL CONSTRAINTS

    # %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    # CREATE VARIABLES

    # %% OPERATIONAL BUILDING VARIABLES
    #   NOTE: Subscript "dom" = "domestic"
    # Electrical power to/from electricity-based domestic devices
    power_dom = {}
    for device in ecs_power:
        power_dom[device] = {}
        for n in range(buildings):
            power_dom[device][n] = {}
            for t in time_steps:
                power_dom[device][n][t] = model.addVar(vtype="C",name="power_" + device + "_n" + str(n) + "_t" + str(t))

    # Heat to/from devices
    heat_dom = {}
    for device in ecs_heat:
        heat_dom[device] = {}
        for n in range(buildings):
            heat_dom[device][n] = {}
            for t in time_steps:
                heat_dom[device][n][t] = model.addVar(vtype="C",name="heat_" + device + "_n" + str(n) + "_t" + str(t))

    # Cool from devices
    cool_dom = {}
    for device in ecs_cool:
        cool_dom[device] = {}
        for n in range(buildings):
            cool_dom[device][n] = {}
            for t in time_steps:
                cool_dom[device][n][t] = model.addVar(vtype="C",name="cool_" + device + "_n" + str(n) + "_t" + str(t))

    power_mode= {}
    for device in hp_modi:
        power_mode[device] = {}
        for n in range(buildings):
            power_mode[device][n] = {}
            for t in time_steps:
                power_mode[device][n][t] = model.addVar(vtype="C",name="power_mode_" + device + "_n" + str(n) + "_t" + str(t))

    # Heat to/from devices
    heat_mode = {}
    for device in hp_modi:
        heat_mode[device] = {}
        for n in range(buildings):
            heat_mode[device][n] = {}
            for t in time_steps:
                heat_mode[device][n][t] = model.addVar(vtype="C",name="heat_mode_" + device + "_n" + str(n) + "_t" + str(t))

    # Gas to devices
    gas_dom = {}
    for device in ecs_gas:
        gas_dom[device] = {}
        for n in range(buildings):
            gas_dom[device][n] = {}
            for t in time_steps:
                gas_dom[device][n][t] = model.addVar(vtype="C",name="gas" + device + "_n" + str(n) + "_t" + str(t))

    # Storage variables
    soc_dom = {}  # State of charge
    ch_dom = {}
    dch_dom = {}
    for device in ecs_storage:
        soc_dom[device] = {}  # Energy (Wh)
        ch_dom[device] = {}  # Power(W)
        dch_dom[device] = {}  # Power (W)
        for n in range(buildings):
            soc_dom[device][n] = {}
            ch_dom[device][n] = {}
            dch_dom[device][n] = {}
            for t in time_steps:
                soc_dom[device][n][t] = model.addVar(vtype="C",name="soc_" + device + "_n" + str(n) + "_t" + str(t))
                ch_dom[device][n][t] = model.addVar(vtype="C",name="ch_dom_" + device + "_n" + str(n) + "_t" + str(t))
                dch_dom[device][n][t] = model.addVar(vtype="C",name="dch_dom_" + device + "_n" + str(n) + "_t" + str(t))

    # Residual building demands (in W)
    res_dom = {}
    res_dom["power"] = {}
    res_dom["feed"] = {}
    for n in range(buildings):
        # Electricity demand
        res_dom["power"][n] = {}
        res_dom["feed"][n] = {}
        for t in time_steps:
            res_dom["power"][n][t] = model.addVar(vtype="C",name="residual_power_n" + str(n) + "_t" + str(t))
            res_dom["feed"][n][t] = model.addVar(vtype="C",name="residual_feed_n" + str(n) + "_t" + str(t))

    # Binary variables to prevent simultaneous feed-in and electricity purchase for each building,
    # as well as simultaneous charging and discharging of the battery and electric vehicle
    binary = {}
    for device in ["HLINE","BAT","EV"]:
        binary[device] = {}
        for n in range(buildings):
            binary[device][n] = {}
            for t in time_steps:
                binary[device][n][t] = model.addVar(vtype=gp.GRB.BINARY,
                                                    name="factor_binary_" + device + "_n" + str(n) + "_t" + str(t))

    # Total residual electricity demand of the buildings
    residual = {}
    residual["power"] = {}  # Residual demand
    residual["feed"] = {}  # Residual feed in
    for t in time_steps:
        residual["power"][t] = model.addVar(vtype="C",name="P_dem_total_" + str(t))
        residual["feed"][t] = model.addVar(vtype="C",name="P_inj_total_" + str(t))

    # Binary variable indicating the activation of the transformer that connects the local grid to the overlying grid
    yTrafo = model.addVars(time_steps,vtype="B",name="yTrafo_" + str(t))

    # Gas flow to/from devices
    eh_gas = {}
    for device in ["CHP", "BOI", "GHP", "SAB", "from_grid", "to_grid"]:
        eh_gas[device] = {}
        for t in time_steps:
            eh_gas[device][t] = model.addVar(vtype="C", name="gas_" + device + "_t" + str(t))

    # Electric power to/from devices
    eh_power = {}
    for device in ["PV", "WT", "WAT", "HP", "EB", "CC", "CHP", "BCHP", "WCHP", "ELYZ",
                   "FC", "from_grid", "to_grid"]:
        eh_power[device] = {}
        for t in time_steps:
            eh_power[device][t] = model.addVar(vtype="C", name="eh_power_" + device + "_t" + str(t))

    # Heat to/from devices
    eh_heat = {}
    for device in ["STC", "HP", "EB", "AC", "CHP", "BOI", "GHP", "BCHP", "BBOI", "WCHP",
                   "WBOI", "FC", "grid"]:
        eh_heat[device] = {}
        for t in time_steps:
            eh_heat[device][t] = model.addVar(vtype="C", name="eh_heat_" + device + "_t" + str(t))

    # Cooling power to/from devices
    eh_cool = {}
    for device in ["CC", "AC", "grid"]:
        eh_cool[device] = {}
        for t in time_steps:
            eh_cool[device][t] = model.addVar(vtype="C", name="eh_cool_" + device + "_t" + str(t))

    # Hydrogen to/from devices
    eh_hydrogen = {}
    for device in ["ELYZ", "FC", "SAB", "import"]:
        eh_hydrogen[device] = {}
        for t in time_steps:
            eh_hydrogen[device][t] = model.addVar(vtype="C", name="eh_hydrogen_" + device + "_t" + str(t))

    # Biomass to devices
    eh_biom = {}
    for device in ["BCHP", "BBOI", "import"]:
        eh_biom[device] = {}
        for t in time_steps:
            eh_biom[device][t] = model.addVar(vtype="C", name="eh_biom_" + device + "_t" + str(t))

    # Waste to devices
    eh_waste = {}
    for device in ["WCHP", "WBOI", "import"]:
        eh_waste[device] = {}
        for t in time_steps:
            eh_waste[device][t] = model.addVar(vtype="C", name="waste_" + device + "_t" + str(t))

    # Storage variables
    eh_ch = {}# Energy flow to charge storage device
    eh_dch = {}# Energy flow to discharge storage device
    eh_soc = {} # State of charge
    eh_soc_init = {} # Initial state of charge
    binary_EH = {}
    for device in ["TES", "CTES", "BAT", "H2S", "GS"]:
        eh_ch[device] = {}
        eh_soc[device] = {}
        eh_dch[device] = {}
        binary_EH[device] = {}
        # Initial state of charge
        if energyHubData == {}:
            eh_soc_init[device] = 0  # Wh
        else:
            eh_soc_init[device] = energyHubData["capacities"][device]["cap"] * 1000 * 0.5  # Wh
        for t in time_steps:
            eh_ch[device][t] = model.addVar(vtype="C", name="eh_ch_" + device + "_t" + str(t))
            eh_dch[device][t] = model.addVar(vtype="C", name="eh_dch_" + device + "_t" + str(t))
            eh_soc[device][t] = model.addVar(vtype="C", name="soc_" + device + "_t" + str(t))
            binary_EH[device][t] = model.addVar(vtype=gp.GRB.BINARY, name="factor_binary_EH_" + device + "_t" + str(t))

    # %% BALANCING UNIT VARIABLES

    # Electrical power to/from grid at Grid Network Point (GNP), gas from grid
    # TODO: rename
    power = {}
    power["from_grid"] = {} # from main grid to local grid
    power["to_grid"] = {} # from local grid to main grid
    power["gas_from_grid"] = {}  # from main grid
    for t in time_steps:
        power["from_grid"][t] = model.addVar(vtype="C",lb=0,name="P_dem_gcp_" + str(t))
        power["to_grid"][t] = model.addVar(vtype="C", lb=0, name="P_inj_gcp_" + str(t))
        power["gas_from_grid"][t] = model.addVar(vtype="C", lb=0, name="P_gas_total_" + str(t))

    # total energy amounts taken from grid
    from_grid_total_el = model.addVar(vtype="C",name="from_grid_total_el")
    # total power to grid
    to_grid_total_el = model.addVar(vtype="C",name="to_grid_total_el")
    # total gas amounts taken from grid
    from_grid_total_gas = model.addVar(vtype="C",name="from_grid_total_gas")
    # total hydrogen amounts taken from grid
    from_grid_total_hydrogen = model.addVar(vtype = "C", name="from_grid_total_hydrogen")
    # total biomass used
    total_biomass_used = model.addVar(vtype = "C", name="total_biomass_used")
    # total waste used
    total_waste_used = model.addVar(vtype = "C", lb=-gp.GRB.INFINITY, name="total_waste_used")

    # Variables for annual device costs
    eh_c_total = {}
    for device in eh_devs:
        eh_c_total[device] = model.addVar(vtype = "C", name="eh_total_annual_costs_" + device)

    # daily peak
    days = [0,1,2,3,4,5,6]
    daily_peak = {}
    for d in days:
        daily_peak[d] = model.addVar(vtype="C",lb=-gp.GRB.INFINITY,name="peak_network_load")
    peaksum = model.addVar(vtype="c",lb=-gp.GRB.INFINITY,name="sum_peak_daily_network_load")

    # Total operational costs
    operational_costs = model.addVar(vtype="C",lb=-gp.GRB.INFINITY,name="Cost_total")
    # Total gross CO2 emissions
    co2_total = model.addVar(vtype="C",lb=-gp.GRB.INFINITY,name="Emission_total")

    # Objective function
    obj = model.addVar(vtype="C",lb=-gp.GRB.INFINITY,name="obj")

    # %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    # DEFINE OBJECTIVE FUNCTION
    model.update()
    model.setObjective(obj)
    model.ModelSense = gp.GRB.MINIMIZE

    # Add capacity constraints ENERGY HUB
    for t in time_steps:
        if energyHubData == {}:
            for device in ["STC", "EB", "HP", "BOI", "GHP", "BBOI", "WBOI"]:
                model.addConstr(eh_heat[device][t] == 0)
            for device in ["PV", "WT", "WAT", "CHP", "BCHP", "WCHP", "ELYZ", "FC", "from_grid", "to_grid"]:
                model.addConstr(eh_power[device][t] == 0)
            for device in ["CC", "AC", "grid"]:
                model.addConstr(eh_cool[device][t] == 0)

        else:
            for device in ["STC", "EB", "HP", "BOI", "GHP", "BBOI", "WBOI"]:
                model.addConstr(eh_heat[device][t] <= energyHubData["capacities"][device]["cap"] * 1000) # W
            model.addConstr(eh_heat["STC"][t] <= energyHubData["generation"]["STC_cluster"][cluster][t] * 1000,
                        name="STC_generation_energyHub_" + str(t))

            for device in ["PV", "WT", "WAT", "CHP", "BCHP", "WCHP", "ELYZ", "FC", "from_grid", "to_grid"]:
                model.addConstr(eh_power[device][t] <= energyHubData["capacities"][device]["cap"] * 1000) # W
            model.addConstr(eh_power["PV"][t] <= energyHubData["generation"]["PV_cluster"][cluster][t] * 1000,
                        name="PV_generation_energyHub_" + str(t))
            model.addConstr(eh_power["WT"][t] == energyHubData["generation"]["Wind_cluster"][cluster][t] * 1000,
                        name="WT_generation_energyHub_" + str(t))

            for device in ["CC", "AC"]:
                model.addConstr(eh_cool[device][t] <= energyHubData["capacities"][device]["cap"] * 1000) # W

    # state of charge < storage capacity
    for device in ["TES", "CTES", "BAT", "H2S", "GS"]:
        for t in time_steps:
            if energyHubData == {}:
                model.addConstr(eh_soc[device][t] == 0)
            else:
                model.addConstr(eh_soc[device][t] <= energyHubData["capacities"][device]["cap"] * 1000) # Wh

    #%% INPUT / OUTPUT CONSTRAINTS
    for t in time_steps:
        # Electric heat pump
        if energyHubData == {}:
            model.addConstr(eh_heat["HP"][t] == 0)
        else:
            COP_HP_eh = energyHubData["capacities"]["devs"]["HP"]["COP"][cluster]
            model.addConstr(eh_heat["HP"][t] == eh_power["HP"][t] * COP_HP_eh[t])
        # Electric boiler
        model.addConstr(eh_heat["EB"][t] == eh_power["EB"][t] * central_device_data["EB"]["eta_th"])
        # Compression chiller
        if energyHubData == {}:
            model.addConstr(eh_cool["CC"][t] == 0)
        else:
            COP_CC_eh = energyHubData["capacities"]["devs"]["CC"]["COP"][cluster]
            model.addConstr(eh_cool["CC"][t] == eh_power["CC"][t] * COP_CC_eh[t])
        # Absorption chiller
        model.addConstr(eh_cool["AC"][t] == eh_heat["AC"][t] * central_device_data["AC"]["eta_th"])
        # Gas CHP
        model.addConstr(eh_power["CHP"][t] == eh_gas["CHP"][t] * central_device_data["CHP"]["eta_el"])
        model.addConstr(eh_heat["CHP"][t] == eh_gas["CHP"][t] * central_device_data["CHP"]["eta_th"])
        # Gas boiler
        model.addConstr(eh_heat["BOI"][t] == eh_gas["BOI"][t] * central_device_data["BOI"]["eta_th"])
        # Gas heat pump
        model.addConstr(eh_heat["GHP"][t] == eh_gas["GHP"][t] * central_device_data["GHP"]["COP"])
        # Biomass CHP
        model.addConstr(eh_power["BCHP"][t] == eh_biom["BCHP"][t] * central_device_data["BCHP"]["eta_el"])
        model.addConstr(eh_heat["BCHP"][t] == eh_biom["BCHP"][t] * central_device_data["BCHP"]["eta_th"])
        # Biomass boiler
        model.addConstr(eh_heat["BBOI"][t] == eh_biom["BBOI"][t] * central_device_data["BBOI"]["eta_th"])
        # Waste CHP
        model.addConstr(eh_power["WCHP"][t] == eh_waste["WCHP"][t] * central_device_data["WCHP"]["eta_el"])
        model.addConstr(eh_heat["WCHP"][t] == eh_waste["WCHP"][t] * central_device_data["WCHP"]["eta_th"])
        # Waste boiler
        model.addConstr(eh_heat["WBOI"][t] == eh_waste["WBOI"][t] * central_device_data["WBOI"]["eta_th"])
        # Electrolyzer
        model.addConstr(eh_hydrogen["ELYZ"][t] == eh_power["ELYZ"][t] * central_device_data["ELYZ"]["eta_el"])
        # Fuel cell
        model.addConstr(eh_power["FC"][t] == eh_hydrogen["FC"][t] * central_device_data["FC"]["eta_el"])
        # Heat must be used
        model.addConstr(eh_heat["FC"][t] == eh_hydrogen["FC"][t] * central_device_data["FC"]["eta_th"])
        # Sabatier reactor
        model.addConstr(eh_gas["SAB"][t] == eh_hydrogen["SAB"][t] * central_device_data["SAB"]["eta"])


    # %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    # ADD CONSTRAINTS

    # Device generation <= device capacity
    for n in range(buildings):
        for t in time_steps:
            for device in ["HP", "CHP", "BOI", "FC", "EH"]:
                model.addConstr(heat_dom[device][n][t] <= buildingData[n]["capacities"][device], name=str(device) + "_heat_cap_" + str(n))

    for n in range(buildings):
        for t in time_steps:
            for device in ["CC"]:
                model.addConstr(cool_dom[device][n][t] <= buildingData[n]["capacities"][device], name=str(device) + "_cool_cap_" + str(n))

    for n in range(buildings):
        for t in time_steps:
            model.addConstr(heat_dom["STC"][n][t] <= STC_heat[n][t], name=str("STC") + "_heat_cap_" + str(n) + str(t))


    for n in range(buildings):
        for t in time_steps:
            # Energy balance heat pump
            model.addConstr(heat_dom["HP"][n][t] == heat_mode["HP35"][n][t] + heat_mode["HP55"][n][t],
                name="Conversion_heat_" + str(n) + "_" + str(t))

            model.addConstr(power_dom["HP"][n][t] == power_mode["HP35"][n][t] + power_mode["HP55"][n][t],
                name="Conversion_power_" + str(n) + "_" + str(t))

            # heat generation of heat pump for each modus
            if buildingData[n]["envelope"].construction_year >= 1995 and buildingData[n]["capacities"]["HP"] > 0:
                # HP can only run in HP35 mode if building is new enough
                model.addConstr(power_mode["HP55"][n][t] == 0,
                                name="Activity_mode_" + str(n) + "_" + str(t))
            elif buildingData[n]["envelope"].construction_year < 1995 and buildingData[n]["capacities"]["HP"] > 0:
                model.addConstr(power_mode["HP35"][n][t] == 0,
                                name="Activity_mode_" + str(n) + "_" + str(t))

            # Energy conversion heat pump modus 35
            model.addConstr(heat_mode["HP35"][n][t] == power_mode["HP35"][n][t] * param_dec_devs["HP"]["grade"]
                            * (273.15 + 35) / (35 - T_e[t]),
                            name="Conversion_HP35_" + str(n) + "_" + str(t))
            # Energy conversion heat pump modus 55
            model.addConstr(heat_mode["HP55"][n][t] == power_mode["HP55"][n][t] * param_dec_devs["HP"]["grade"]
                            * (273.15 + 55) / (55 - T_e[t]),
                            name="Conversion_HP55_" + str(n) + "_" + str(t))

            # Compression chiller
            model.addConstr(cool_dom["CC"][n][t] == power_dom["CC"][n][t] * param_dec_devs["CC"]["grade"]
                            * (273.15 + 5) / (T_e[t] - 5),
                                name="CC_energybalance_cooling_" + str(n) + "_" + str(t))

            # Electric heater
            model.addConstr(heat_dom["EH"][n][t] == param_dec_devs["EH"]["eta_th"] * power_dom["EH"][n][t],
                                name="EH_energybalance_heating_" + str(n) + "_" + str(t))

            # CHP
            model.addConstr(heat_dom["CHP"][n][t] == param_dec_devs["CHP"]["eta_th"] * gas_dom["CHP"][n][t],
                            name="chp_energybalance_heating" + str(n) + "_" + str(t))

            model.addConstr(power_dom["CHP"][n][t] == param_dec_devs["CHP"]["eta_el"] * gas_dom["CHP"][n][t],
                            name="chp_energybalance_power" + str(n) + "_" + str(t))

            # FC
            model.addConstr(heat_dom["FC"][n][t] == param_dec_devs["FC"]["eta_th"] * gas_dom["FC"][n][t],
                            name="fc_energybalance_heating" + str(n) + "_" + str(t))

            model.addConstr(power_dom["FC"][n][t] == param_dec_devs["FC"]["eta_el"] * gas_dom["FC"][n][t],
                            name="fc_energybalance_power" + str(n) + "_" + str(t))

            # BOILER
            model.addConstr(heat_dom["BOI"][n][t] == param_dec_devs["BOI"]["eta_th"] * gas_dom["BOI"][n][t],
                            name="boiler_energybalance_heating" + str(n) + "_" + str(t))

    # min and max storage level, charging and discharging
    for n in range(buildings):
        for device in ecs_storage:
            for t in time_steps:
                model.addConstr(ch_dom[device][n][t] <= buildingData[n]["capacities"][device] * param_dec_devs[device]["coeff_ch"],
                                name="max_ch_cap_" + str(device) + "_" + str(n) + "_" + str(t))
                model.addConstr(dch_dom[device][n][t] <= buildingData[n]["capacities"][device] * param_dec_devs[device]["coeff_ch"],
                                name="max_dch_cap_" + str(device) + "_" + str(n) + "_" + str(t))

                model.addConstr(soc_dom[device][n][t] <= param_dec_devs[device]["soc_max"] * buildingData[n]["capacities"][device],
                                name="max_soc_" + str(device) + "_" + str(n) + "_" + str(t))
                model.addConstr(soc_dom[device][n][t] >= param_dec_devs[device]["soc_min"] * buildingData[n]["capacities"][device],
                                name="min_soc_" + str(device) + "_" + str(n) + "_" + str(t))

    # %% DOMESTIC FLEXIBILITIES
    # SOC coupled over all times steps (Energy amount balance, Wh)

    # %% EV CONSTRAINTS
    device = "EV"

    for n in range(buildings):

        plug_in_time = None
        # Define the charging period (parking time or until the end of time_steps)
        parking_time = 12 / dt if buildingData[n]["buildingFeatures"]["building"] in {"SFH", "TH", "MFH", "AB"} else 7 / dt

        if buildingData[n]["buildingFeatures"]["ev_charging"] in {"intelligent", "bi_directional", "on_demand"}:

            for t in time_steps:
                if t == 0:
                    soc_prev = soc_init[device][n]
                else:
                    soc_prev = soc_dom[device][n][t - 1]


                # Energy balance
                # This is the general constraint that applies directly (without additional constraints) when the EV has a bidirectional charging mode
                model.addConstr(soc_dom[device][n][t] == soc_prev * param_dec_devs[device]["eta_standby"] ** dt
                                + ch_dom[device][n][t] * param_dec_devs[device]["eta_ch"] * dt
                                - dch_dom[device][n][t] / param_dec_devs[device]["eta_ch"] * dt
                                - EV_dem[n][t],
                                name="EV_storage_balance_" + str(n) + "_" + str(t))


                if buildingData[n]["buildingFeatures"]["ev_charging"] == "on_demand":
                    # On_demand EVs can only charge, not discharge
                    model.addConstr(dch_dom[device][n][t] == 0, name="p_feed_ev")
                    model.addConstr(ch_dom[device][n][t] == EV_charging_ondemand[n][t], name="charge_ondemand_ev_" + str(n) + "_" + str(t))

                elif buildingData[n]["buildingFeatures"]["ev_charging"] in {"intelligent", "bi_directional"}:

                    if t == last_time_step:
                    # In the case of on-demand, this constraint is not needed because the car is directly charged the same amount as it consumes
                            model.addConstr(soc_dom[device][n][t] == soc_init[device][n])

                    # Detect charging periods based on EV_dem
                    if plug_in_time is None and EV_dem[n][t] > 0:
                        plug_in_time = t
                    # If charging start time is found
                    if plug_in_time is not None:
                        # Charging period constraints
                        if t >= plug_in_time and t < min(plug_in_time + parking_time, len(time_steps)):
                            # Within charging period, allow charging and discharging
                            if buildingData[n]["buildingFeatures"]["ev_charging"] == "intelligent":
                                # Intelligent EVs can only charge, not discharge
                                model.addConstr(dch_dom[device][n][t] == 0, name="p_feed_ev")

                        else:
                            # Outside charging period, force charging and discharging power to zero
                            model.addConstr(ch_dom[device][n][t] == 0, name="no_charging" + str(n) + "_" + str(t))
                            model.addConstr(dch_dom[device][n][t] == 0, name="no_discharging" + str(n) + "_" + str(t))
                            # to reset plug_in_time when time is outside the parking_time window
                            if t >= plug_in_time + parking_time:
                                plug_in_time = None
                    else:
                        # When it's not a plug-in time, charging and discharging rate is zero
                        model.addConstr(ch_dom[device][n][t] == 0, name="not_plug-in-time_charging_" + str(n) + "_" + str(t))
                        model.addConstr(dch_dom[device][n][t] == 0, name="not_plug-in-time_discharging_" + str(n) + "_" + str(t))

                    model.addConstr(dch_dom[device][n][t] <= binary[device][n][t] * 10000000,
                                    name="Binary1_ev_" + str(n) + "_" + str(t))
                    model.addConstr(ch_dom[device][n][t] <= (1 - binary[device][n][t]) * 10000000,
                                    name="Binary2_ev_" + str(n) + "_" + str(t))
        else:
            raise ValueError(
                f"Invalid 'ev_charging' value: '{buildingData[n]['buildingFeatures']['ev_charging']}'. "f" It should be one of 'intelligent', 'bi_directional', or 'on_demand'.")




    # %% TES CONSTRAINTS
    device = "TES"
    for n in range(buildings):
        # Energy balance
        for t in time_steps:
            if t == 0:
                    soc_prev = soc_init[device][n]
            else:
                    soc_prev = soc_dom[device][n][t - 1]

            model.addConstr(soc_dom[device][n][t] == soc_prev * param_dec_devs[device]["eta_standby"] ** dt
                                                     + ch_dom[device][n][t]  * param_dec_devs[device]["eta_ch"] * dt
                                                     - dch_dom[device][n][t] / param_dec_devs[device]["eta_ch"] * dt,
                            name= str(device) + "_storage_balance_" + str(n) + "_" + str(t))

            if t == last_time_step:
                model.addConstr(soc_dom[device][n][t] == soc_init[device][n],
                                name="End_" + str(device) + "_storage_" + str(n) + "_" + str(t))

            model.addConstr(ch_dom[device][n][t] == heat_dom["CHP"][n][t] + heat_dom["HP"][n][t] + heat_dom["BOI"][n][t]
                            + heat_dom["EH"][n][t] + heat_dom["STC"][n][t] + heat_dom["FC"][n][t],
                            name="Heat_charging_" + str(n) + "_" + str(t))
            model.addConstr(dch_dom[device][n][t] + heat_dom["heat_grid"][n][t] == Q_DHW[n][t] + Q_heating[n][t],
                            name="Heat_discharging_" + str(n) + "_" + str(t))

    # %% BAT CONSTRAINTS
    device = "BAT"
    for n in range(buildings):
        # Energy balance
        for t in time_steps:
            if t == 0:
                    soc_prev = soc_init[device][n]
            else:
                    soc_prev = soc_dom[device][n][t - 1]

            model.addConstr(soc_dom[device][n][t] == soc_prev * param_dec_devs[device]["eta_standby"] ** dt
                            + ch_dom[device][n][t] * param_dec_devs[device]["eta_ch"] * dt
                            - dch_dom[device][n][t] / param_dec_devs[device]["eta_ch"] * dt,
                            name=str(device) + "_storage_balance_" + str(n) + "_" + str(t))

            if t == last_time_step:
                model.addConstr(soc_dom[device][n][t] == soc_init[device][n],
                                name="End_" + str(device) + "_storage_" + str(n) + "_" + str(t))

            model.addConstr(dch_dom[device][n][t] <= binary[device][n][t] * 10000000,
                            name="Binary1_bat_" + str(n) + "_" + str(t))
            model.addConstr(ch_dom[device][n][t] <= (1 - binary[device][n][t]) * 10000000,
                            name="Binary2_bat_" + str(n) + "_" + str(t))

    for n in range(buildings):
        for t in time_steps:
            model.addConstr(res_dom["power"][n][t] <= binary["HLINE"][n][t] * 10000000,
                            name="Binary1_hline_" + str(n) + "_" + str(t))
            model.addConstr(res_dom["feed"][n][t] <= (1 - binary["HLINE"][n][t]) * 10000000,
                            name="Binary2_hline_" + str(n) + "_" + str(t))

    # Residual loads
    for t in time_steps:
        # Residual network electricity demand (Power balance in Watt)
        model.addConstr(residual["power"][t] == sum(res_dom["power"][n][t] for n in range(buildings)), name="res_power"+ str(t))
        model.addConstr(residual["feed"][t] == sum(res_dom["feed"][n][t] for n in range(buildings)), name="res_feed"+ str(t))

    # %% BUILDINGS ENERGY BALANCES (Power balance, W)
    for n in range(buildings):
        for t in time_steps:
            # Electricity balance
            model.addConstr(res_dom["power"][n][t] + PV_gen[n][t]
                            + power_dom["CHP"][n][t] + power_dom["FC"][n][t] + dch_dom["BAT"][n][t] + dch_dom["EV"][n][t]
                            == elec_dem[n][t] + ch_dom["EV"][n][t]
                            + power_dom["HP"][n][t] + power_dom["EH"][n][t]
                            + ch_dom["BAT"][n][t] + res_dom["feed"][n][t],
                            name="Electricity_balance_" + str(n) + "_" + str(t))

            model.addConstr(res_dom["feed"][n][t] <= PV_gen[n][t] + power_dom["CHP"][n][t] + power_dom["FC"][n][t] + dch_dom["BAT"][n][t] + dch_dom["EV"][n][t],
                            name="Feed-in_max_" + str(n) + "_" + str(t))

            # Cooling balance
            model.addConstr(cool_dom["CC"][n][t] + cool_dom["heat_grid"][n][t] == Q_cooling[n][t],
                            name="Cooling_balance_" + str(n) + "_" + str(t))

    # %% ENERGY HUB ENERGY BALANCES
    for t in time_steps:
        # Heating balance
        model.addConstr(eh_heat["STC"][t] + eh_heat["HP"][t] + eh_heat["EB"][t] + eh_heat["CHP"][t]
                        + eh_heat["BOI"][t] + eh_heat["GHP"][t] + eh_heat["BCHP"][t] + eh_heat["BBOI"][t]
                        + eh_heat["WCHP"][t] + eh_heat["WBOI"][t] + eh_heat["FC"][t] +eh_dch["TES"][t]
                        == eh_heat["grid"][t] + eh_heat["AC"][t] + eh_ch["TES"][t],
                        name="Heating_balance_EnergyHub_" + str(t))

        model.addConstr(eh_heat["grid"][t] >= sum(heat_dom["heat_grid"][n][t] for n in range(buildings)) + network_losses_heating[t],
                        name="Heat_Supply_EnergyHub_" + str(t))

        model.addConstr(eh_cool["grid"][t] >= sum(cool_dom["heat_grid"][n][t] for n in range(buildings)) + network_losses_cooling[t],
                        name="Cool_Supply_EnergyHub_" + str(t))

        # Electricity balance
        model.addConstr(eh_power["PV"][t] + eh_power["WT"][t] + eh_power["WAT"][t] + eh_power["CHP"][t] + eh_power["BCHP"][t]
                        + eh_power["WCHP"][t] + eh_power["FC"][t] + eh_power["from_grid"][t] + eh_dch["BAT"][t]
                        == eh_power["HP"][t] + eh_power["EB"][t] + eh_power["CC"][t]
                        + eh_power["ELYZ"][t] + eh_ch["BAT"][t] + eh_power["to_grid"][t],
                        name="Electricity_balance_EnergyHub_" + str(t))

        # Cooling balance
        model.addConstr(eh_cool["AC"][t] + eh_cool["CC"][t] + eh_dch["CTES"][t] == eh_cool["grid"][t] + eh_ch["CTES"][t])

        # Gas balance
        model.addConstr(eh_gas["from_grid"][t] + eh_gas["SAB"][t] == eh_gas["CHP"][t] + eh_gas["BOI"][t]
                        + eh_gas["GHP"][t] + eh_ch["GS"][t] + eh_gas["to_grid"][t],
                        name="Gas_balance_EnergyHub_" + str(t))
        # Hydrogen balance
        model.addConstr(eh_hydrogen["ELYZ"][t] + eh_hydrogen["import"][t]
                        == eh_hydrogen["FC"][t] + eh_hydrogen["SAB"][t] + eh_ch["H2S"][t])
        # Biomass balance
        model.addConstr(eh_biom["import"][t] == eh_biom["BCHP"][t] + eh_biom["BBOI"][t])
        # Waste balance
        model.addConstr(eh_waste["import"][t] == eh_waste["WCHP"][t] + eh_waste["WBOI"][t])

        for device in ["TES", "CTES", "BAT"]:
            if t == 0:
                eh_soc_prev = eh_soc_init[device]
            else:
                eh_soc_prev = eh_soc[device][t - 1]

            model.addConstr(eh_soc[device][t] == eh_soc_prev * (1-central_device_data[device]["sto_loss"]) ** dt
                            + eh_ch[device][t] * dt - eh_dch[device][t] * dt,
                            name="Storage_balance_energyHub" + str(device) + "_" + str(t))

            if t == last_time_step:
                model.addConstr(eh_soc[device][t] == eh_soc_init[device])

            model.addConstr(eh_dch[device][t] <= binary_EH[device][t] * 10000000,
                            name="Binary1_Storage_EH_" + "_" + str(t))
            model.addConstr(eh_ch[device][t] <= (1 - binary_EH[device][t]) * 10000000,
                            name="Binary2_Storage_EH_" + "_" + str(t))

    # Electricity balance neighborhood (Power balance in Watt)
    for t in time_steps:
        model.addConstr(residual["feed"][t] + power["from_grid"][t] + eh_power["to_grid"][t]
                        == residual["power"][t] + power["to_grid"][t] + eh_power["from_grid"][t],
                        name="Elec_balance_neighborhood"+ str(t))

        model.addConstr(power["from_grid"][t] <= yTrafo[t] * 10000000,     name="Binary1_" + str(t))
        model.addConstr(power["to_grid"][t] <= (1 - yTrafo[t]) * 10000000, name="Binary2_" + str(t))

    # Gas balance neighborhood (Power balance in Watt)
    for t in time_steps:
        model.addConstr(power["gas_from_grid"][t] + eh_gas["to_grid"][t]
                        == eh_gas["from_grid"][t] + sum(gas_dom["CHP"][n][t] + gas_dom["BOI"][n][t] for n in range(buildings)))

    # %% Summation of energy sources
    # Total gas amount taken from grid (kWh)
    model.addConstr(from_grid_total_gas == dt * sum(power["gas_from_grid"][t] for t in time_steps) / 1000, name="from_grid_total_gas")
    # Total electricity amount taken from grid (kWh)
    model.addConstr(from_grid_total_el == dt * sum(power["from_grid"][t] for t in time_steps) / 1000, name="from_grid_total_el")
    # Total electricity feed-in (kWh)
    model.addConstr(to_grid_total_el == dt * sum(power["to_grid"][t] for t in time_steps) / 1000, name="to_grid_total_el")
    # Total hydrogen amount taken from grid (kWh)
    model.addConstr(from_grid_total_hydrogen == dt * sum(eh_hydrogen["import"][t] for t in time_steps) / 1000, name="from_grid_total_hydrogen")
    # Total biomass used (kWh)
    model.addConstr(total_biomass_used == dt * sum(eh_biom["import"][t] for t in time_steps) / 1000, name="total_biomass_used")
    # Total waste used (kWh)
    model.addConstr(total_waste_used == dt * sum(eh_waste["import"][t] for t in time_steps) / 1000, name="total_waste_used")

    # %% OBJECTIVE FUNCTIONS
    # select the objective function based on input parameters
    ### Total operational costs
    model.addConstr(operational_costs == from_grid_total_el * ecoData["price_supply_el"]
                                            - to_grid_total_el * ecoData["revenue_feed_in_el"]
                                            + from_grid_total_gas * ecoData["price_supply_gas"]
                                            + from_grid_total_hydrogen * ecoData["price_hydrogen"]
                                            + total_biomass_used * ecoData["price_biomass"]
                                            + total_waste_used * ecoData["price_waste"]
                                            , name="Total_amount_operational_costs")

    # Emissions
    model.addConstr(co2_total == from_grid_total_el * ecoData["co2_el_grid"]
                                    + from_grid_total_gas * ecoData["co2_gas"]
                                    + from_grid_total_hydrogen * ecoData["co2_hydrogen"]
                                    + total_biomass_used * ecoData["co2_waste"]
                                    + total_waste_used * ecoData["co2_biom"]
                                    , name="Total_amount_emissions")

    # daily peaks
    for d in days:
        model.addConstr(daily_peak[d] == gp.max_(power["from_grid"][t] for t in range(d * int(24/dt), d * int(24/dt) + int(24/dt))))
    model.addConstr(peaksum == sum(daily_peak[d] for d in days))

    # Set objective
    if model_param_eh["optim_focus"] == 0:
        model.addConstr(obj == operational_costs + peaksum * 1)
    elif model_param_eh["optim_focus"] == 1:
        model.addConstr(obj == co2_total + peaksum * 1)

    # Carry out optimization
    model.optimize()

    later = time.time()
    difference = later - now
    print("********************************************")
    print("Model run time was " + str(difference) + " seconds")
    print("********************************************")

    if model.status == gp.GRB.Status.INFEASIBLE:
        print("Model is infeasible")
        # Compute IIS and write details to file
        model.computeIIS()
        with open('errorfile.txt', 'w') as f:
            f.write('\nThe following constraint(s) cannot be satisfied:\n')
            for c in model.getConstrs():
                if c.IISConstr:
                    f.write(f'{c.ConstrName}\n')
        # Save IIS info
        model.write("model.ilp")

    elif model.status == gp.GRB.Status.UNBOUNDED:
        print("Model is unbounded")
    elif model.status == gp.GRB.Status.OPTIMAL:
        print("Model solved to optimality")
    else:
        print(f"Model status: {model.status}")

    # Save model files in current directory
    model.write("model.lp")
    if model.Status == gp.GRB.Status.OPTIMAL:
        model.write("model.sol")

    # %% SAVE RESULTS IN ONE CENTRAL RESULT FILE: result_file

    results = {}
    results["from_grid_total_el"] = from_grid_total_el.X
    results["to_grid_total_el"] = to_grid_total_el.X
    results["from_grid_total_gas"] = from_grid_total_gas.X

    results["P_dem_total"] = []
    results["P_inj_total"] = []
    results["P_dem_gcp"] = []
    results["P_inj_gcp"] = []
    results["P_gas_total"] = []
    for t in time_steps:
        results["P_dem_total"].append(round(residual["power"][t].X, 0))
        results["P_inj_total"].append(round(residual["feed"][t].X, 0))
        results["P_dem_gcp"].append(round(power["from_grid"][t].X, 0))
        results["P_inj_gcp"].append(round(power["to_grid"][t].X, 0))
        results["P_gas_total"].append(round(power["gas_from_grid"][t].X, 0))

    results["Cost_total"] = operational_costs.X
    results["Emission_total"] = co2_total.X

    # add results of the buildings
    for n in range(buildings):
        results[n] = {}
        results[n]["res_load"] = []
        results[n]["res_inj"] = []
        results[n]["res_gas"] = []
        for t in time_steps:
            results[n]["res_load"].append(round(res_dom["power"][n][t].X, 0))
            results[n]["res_inj"].append(round(res_dom["feed"][n][t].X, 0))
            results[n]["res_gas"].append(round(gas_dom["BOI"][n][t].X + gas_dom["CHP"][n][t].X+gas_dom["FC"][n][t].X, 0))

    for n in range(buildings):
        for device in ecs_heat:
            results[n][device] = {}
            results[n][device]["Q_th"] = []
            for t in time_steps:
                results[n][device]["Q_th"].append(round(heat_dom[device][n][t].X, 0))

    for n in range(buildings):
        for device in ecs_cool:
            results[n][device] = {}
            results[n][device]["Q_cool"] = []
            for t in time_steps:
                results[n][device]["Q_cool"].append(round(cool_dom[device][n][t].X, 0))

    for n in range(buildings):
        for device in hp_modi:
            results[n][device] = {}
            results[n][device]["Q_th"] = []
            results[n][device]["P_el"] = []
            for t in time_steps:
                results[n][device]["Q_th"].append(round(heat_mode[device][n][t].X, 0))
                results[n][device]["P_el"].append(round(power_mode[device][n][t].X, 0))

    for n in range(buildings):
        for device in ecs_power:
            results[n][device] = {}
            results[n][device]["P_el"] = []
            for t in time_steps:
                results[n][device]["P_el"].append(round(power_dom[device][n][t].X, 0))

    for n in range(buildings):
        for device in ecs_storage:
            results[n][device] = {}
            for v in ("ch", "dch", "soc"):
                results[n][device][v] = []
            for t in time_steps:
                results[n][device]["ch"].append(ch_dom[device][n][t].X)
                results[n][device]["dch"].append(dch_dom[device][n][t].X)
                results[n][device]["soc"].append(soc_dom[device][n][t].X)

    results["peaksum"] = peaksum.X
    results["daily_peak"] = {}
    for d in days:
        results["daily_peak"][d] = daily_peak[d].X

    return results