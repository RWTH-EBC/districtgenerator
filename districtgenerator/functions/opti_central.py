#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created 26.02.2024
@author: Joel Schölzel
"""
import os, json
import gurobipy as gp
import time

def run_opti_central(model, buildingData, energyHubData, site, cluster, srcPath, optiData = {}):

    if optiData == {}:
        optiData["webtool"] = False

    now = time.time()
    # %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    # Setting up the model
    # number of buildings in neighborhood
    nb = len(buildingData)


    ecoData = {}
    timeData = {}
    for data in ("eco", "time"):
        with open(srcPath + "/data/" + data + "_data.json") as json_file:
            jsonData = json.load(json_file)
            for subData in jsonData:
                if data == "eco":
                    ecoData[subData["name"]] = subData["value"]
                else:
                    timeData[subData["name"]] = subData["value"]
    time_steps = range(int(timeData["clusterLength"] / timeData["timeResolution"]))
    dt = timeData["timeResolution"] / timeData["dataResolution"]
    last_time_step = len(time_steps) - 1

    # load parameters of decentral energy conversion devices
    param_dec_devs = {}
    with open(srcPath + "/data/" + "decentral_device_data.json") as json_file:
        jsonData = json.load(json_file)
        for subData in jsonData:
            param_dec_devs[subData["abbreviation"]] = {}
            for subsubData in subData["specifications"]:
                param_dec_devs[subData["abbreviation"]][subsubData["name"]] = subsubData["value"]

    # load parameters of central energy conversion devices
    model_param_eh = {}
    with open(srcPath + "/data/" + "model_parameters_EHDO.json") as json_file:
        jsonData = json.load(json_file)
        for subData in jsonData:
            model_param_eh[subData["name"]] = subData["value"]
    technical_param_eh = {}
    with open(srcPath + "/data/" + "technical_parameters_EHDO.json") as json_file:
        jsonData = json.load(json_file)
        for subData in jsonData:
            technical_param_eh[subData["abbreviation"]] = {}
            for subsubData in subData["specifications"]:
                technical_param_eh[subData["abbreviation"]][subsubData["name"]] = subsubData["value"]


    T_e = site["T_e_cluster"][cluster]  # ambient temperature [°C]
    Q_DHW = {}      # DHW (domestic hot water) demand [W]
    Q_heating = {}  # space heating [W]
    PV_gen = {}     # electricity generation of PV [W]
    STC_heat = {}   # electricity generation of PV [W]
    EV_dem = {}     # electricity demand electric vehicle (EV) [Wh]
    elec_dem = {}   # electricity demand for appliances and lighting [W]
    occ = {}
    for n in range(nb):
        Q_DHW[n] = buildingData[n]["user"].dhw_cluster[cluster]
        Q_heating[n] = buildingData[n]["user"].heat_cluster[cluster]
        elec_dem[n] = buildingData[n]["user"].elec_cluster[cluster]
        occ[n] = buildingData[n]["user"].occ[:len(elec_dem[n])]
        try:
            PV_gen[n] = buildingData[n]["generationPV_cluster"][cluster]
            STC_heat[n] = buildingData[n]["generationSTC_cluster"][cluster]
            EV_dem[n] = buildingData[n]["user"].car_cluster[cluster]
        except:
            PV_gen[n] = [0] * len(elec_dem[n])
            STC_heat[n] = [0] * len(elec_dem[n])
            EV_dem[n] = [0] * len(elec_dem[n])


    # %% Sets of energy conversion systems
    # heat generation devices (heat pump (HP), electric heating (EH),
    # combined heat and power (CHP), fuel cell (FC), boiler (BOI), solar thermal collector (STC))
    ecs_heat = ("HP", "EH", "CHP", "FC", "BOI", "STC", "heat_grid")
    ecs_power = ("HP", "EH", "CHP", "FC", "PV")  # power consuming/producing devices (photovoltaic (PV))
    ecs_sell = ("CHP", "FC", "PV", "BAT")
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

    try:
        a = buildingData[0]["capacities"]
    except KeyError:
        for n in range(nb):
            buildingData[n]["capacities"] = {}
            for dev in ["HP", "EH", "CHP", "FC", "BOI", "STC", "BAT", "TES", "EV"]:
                buildingData[n]["capacities"][dev] = 0

    # %% TECHNICAL PARAMETERS
    soc_nom = {}
    soc_nom["TES"] = {}
    soc_nom["BAT"] = {}
    soc_nom["EV"] = {}
    soc_init = {}
    soc_init["TES"] = {}
    soc_init["BAT"] = {}
    soc_init["EV"] = {}
    for n in range(nb):
        # Define nominal SOC_nom according to capacities
        soc_nom["TES"][n] = buildingData[n]["capacities"]["TES"]
        soc_nom["BAT"][n] = buildingData[n]["capacities"]["BAT"]
        soc_nom["EV"][n] = buildingData[n]["capacities"]["EV"]
        # Initial state of charge
        soc_init["TES"][n] = soc_nom["TES"][n] * 0.5  # Wh
        soc_init["BAT"][n] = soc_nom["BAT"][n] * 0.5  # Wh
        soc_init["EV"][n] = soc_nom["EV"][n] * 0.5    # Wh

        # %% TECHNICAL CONSTRAINTS

    # %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    # CREATE VARIABLES

    # %% OPERATIONAL BUILDING VARIABLES
    #   NOTE: Subscript "dom" = "domestic"
    # Electrical power to/from electricity-based domestic devices
    power_dom = {}
    for device in ecs_power:
        power_dom[device] = {}
        for n in range(nb):
            power_dom[device][n] = {}
            for t in time_steps:
                power_dom[device][n][t] = model.addVar(vtype="C",name="power_" + device + "_n" + str(n) + "_t" + str(t))

    # Heat to/from devices
    heat_dom = {}
    for device in ecs_heat:
        heat_dom[device] = {}
        for n in range(nb):
            heat_dom[device][n] = {}
            for t in time_steps:
                heat_dom[device][n][t] = model.addVar(vtype="C",name="heat_" + device + "_n" + str(n) + "_t" + str(t))

    power_mode= {}
    for device in hp_modi:
        power_mode[device] = {}
        for n in range(nb):
            power_mode[device][n] = {}
            for t in time_steps:
                power_mode[device][n][t] = model.addVar(vtype="C",name="power_mode_" + device + "_n" + str(n) + "_t" + str(t))

    # Heat to/from devices
    heat_mode = {}
    for device in hp_modi:
        heat_mode[device] = {}
        for n in range(nb):
            heat_mode[device][n] = {}
            for t in time_steps:
                heat_mode[device][n][t] = model.addVar(vtype="C",name="heat_mode_" + device + "_n" + str(n) + "_t" + str(t))

    # Heat to/from devices
    dhw_dom = {}
    for device in ["EH"]:
        dhw_dom[device] = {}
        for n in range(nb):
            dhw_dom[device][n] = {}
            for t in time_steps:
                dhw_dom[device][n][t] = model.addVar(vtype="C",name="heat_" + device + "_n" + str(n) + "_t" + str(t))

    # Gas to devices
    gas_dom = {}
    for device in ecs_gas:
        gas_dom[device] = {}
        for n in range(nb):
            gas_dom[device][n] = {}
            for t in time_steps:
                gas_dom[device][n][t] = model.addVar(vtype="C",name="gas" + device + "_n" + str(n) + "_t" + str(t))

    # Storage variables
    soc_dom = {}  # State of charge
    ch_dom = {}
    dch_dom = {}
    for device in ecs_storage:
        soc_dom[device] = {}  # Energy (kWh)
        ch_dom[device] = {}  # Power(kW)
        dch_dom[device] = {}  # Power (kW)
        for n in range(nb):
            soc_dom[device][n] = {}
            ch_dom[device][n] = {}
            dch_dom[device][n] = {}
            for t in time_steps:
                soc_dom[device][n][t] = model.addVar(vtype="C",name="soc_" + device + "_n" + str(n) + "_t" + str(t))
                ch_dom[device][n][t] = model.addVar(vtype="C",name="ch_dom_" + device + "_n" + str(n) + "_t" + str(t))
                dch_dom[device][n][t] = model.addVar(vtype="C",name="dch_dom_" + device + "_n" + str(n) + "_t" + str(t))

    # Residual building demands (in kW)  [Sum for each building of all devices]
    res_dom = {}
    res_dom["power"] = {}
    res_dom["feed"] = {}
    for n in range(nb):
        # Electricity demand
        res_dom["power"][n] = {}
        res_dom["feed"][n] = {}
        for t in time_steps:
            res_dom["power"][n][t] = model.addVar(vtype="C",name="residual_power_n" + str(n) + "_t" + str(t))
            res_dom["feed"][n][t] = model.addVar(vtype="C",name="residual_feed_n" + str(n) + "_t" + str(t))

    # binary variable for each house to avoid simuultaneous feed-in and purchase of electric energy
    binary = {}
    for device in ["HLINE","BAT","EV"]:
        binary[device] = {}
        for n in range(nb):
            binary[device][n] = {}
            for t in time_steps:
                binary[device][n][t] = model.addVar(vtype=gp.GRB.BINARY,
                                                    name="factor_binary_" + device + "_n" + str(n) + "_t" + str(t))

    # Residual network demand
    residual = {}
    residual["power"] = {}  # Residual network electricity demand
    residual["feed"] = {}  # Residual feed in
    for t in time_steps:
        residual["power"][t] = model.addVar(vtype="C",name="P_dem_total_" + str(t))
        residual["feed"][t] = model.addVar(vtype="C",name="P_inj_total_" + str(t))

    # activation variable for trafo load
    yTrafo = model.addVars(time_steps,vtype="B",name="yTrafo_" + str(t))

    # Device's capacity (i.e. rated power)
    eh_cap = {}
    for device in eh_devs:
        eh_cap[device] = model.addVar(vtype="C", name="eh_nominal_capacity_" + str(device))

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
    for device in ["CC", "AC"]:
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
    for device in ["TES", "CTES", "BAT", "H2S", "GS"]:
        eh_ch[device] = {}
        eh_soc[device] = {}
        eh_dch[device] = {}
        # Initial state of charge
        eh_soc_init[device] = eh_cap[device] * 0.5  # Wh
        for t in time_steps:
            eh_ch[device][t] = model.addVar(vtype="C", lb=-gp.GRB.INFINITY, name="eh_ch_" + device + "_t" + str(t))
            eh_dch[device][t] = model.addVar(vtype="C", lb=-gp.GRB.INFINITY, name="eh_dch_" + device + "_t" + str(t))
            eh_soc[device][t] = model.addVar(vtype="C", name="soc_" + device + "_t" + str(t))


    # %% BALANCING UNIT VARIABLES

    # Electrical power to/from grid at GNP, gas from grid
    # TODO: rename
    power = {}
    power["from_grid"] = {}
    power["to_grid"] = {}
    power["gas_from_grid"] = {}
    for t in time_steps:
        power["from_grid"][t] = model.addVar(vtype="C",lb=0,name="P_dem_gcp_" + str(t))
        power["to_grid"][t] = model.addVar(vtype="C", lb=0, name="P_inj_gcp_" + str(t))
        power["gas_from_grid"][t] = model.addVar(vtype="C", lb=0, name="P_gas_total_" + str(t))

    # total energy amounts taken from grid
    from_grid_total_el = model.addVar(vtype="C",name="from_grid_total_el")
    # total power to grid
    to_grid_total_el = model.addVar(vtype="C",name="to_grid_total_el")
    # total gas amounts taken from grid
    from_grid_total_gas = model.addVar(vtype="C",name="from_grid_total_el")
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
        for device in ["STC", "EB", "HP", "BOI", "GHP", "BBOI", "WBOI"]:
            # todo: webtool
            if energyHubData == {}:
                model.addConstr(eh_heat[device][t] == 0)
            else:
                model.addConstr(eh_heat[device][t] <= energyHubData["capacities"]["heat_kW"][device] * 10000) # W
        model.addConstr(eh_heat["STC"][t] <= energyHubData["generation"]["STC_cluster"][cluster][t],
                        name="STC_generation_energyHub_" + str(t))
        for device in ["PV", "WT", "WAT", "CHP", "BCHP", "WCHP", "ELYZ", "FC", "from_grid", "to_grid"]:
            # todo: webtool
            if energyHubData == {}:
                model.addConstr(eh_power[device][t] == 0)
            else:
                model.addConstr(eh_power[device][t] <= energyHubData["capacities"]["power_kW"][device] * 1000) # W
        model.addConstr(eh_power["PV"][t] <= energyHubData["generation"]["PV_cluster"][cluster][t],
                        name="PV_generation_energyHub_" + str(t))
        model.addConstr(eh_power["WT"][t] == energyHubData["generation"]["Wind_cluster"][cluster][t],
                        name="WT_generation_energyHub_" + str(t))
        for device in ["CC", "AC"]:
            model.addConstr(eh_cool[device][t] <= eh_cap[device])
        #for device in ["SAB"]:
        #    model.addConstr(eh_gas[device][t] <= eh_cap[device])

    # state of charge < storage capacity
    for device in ["TES", "CTES", "BAT", "H2S", "GS"]:
        for t in time_steps:
            # todo: webtool
            if energyHubData == {}:
                model.addConstr(eh_soc[device][t] == 0)
            else:
                model.addConstr(eh_soc[device][t] <= eh_cap[device] * 1000) # Wh

    #%% INPUT / OUTPUT CONSTRAINTS
    if optiData["webtool"] == True:
        for t in time_steps:
            # todo: COP
            # Electric heat pump
            model.addConstr(eh_heat["HP"][t] == eh_power["HP"][t] * eh_devs["eh_HP"]["COP"][t])
            # Electric boiler
            model.addConstr(eh_heat["EB"][t] == eh_power["EB"][t] * eh_devs["eh_EB"]["eta_th"])
            # Compression chiller
            model.addConstr(eh_cool["CC"][t] == eh_power["CC"][t] * eh_devs["eh_CC"]["COP"])
            # Absorption chiller
            model.addConstr(eh_cool["AC"][t] == eh_heat["AC"][t] * devs["AC"]["eta_th"])
            # Gas CHP
            model.addConstr(eh_power["CHP"][t] == eh_gas["CHP"][t] * devs["CHP"]["eta_el"])
            model.addConstr(eh_heat["CHP"][t] == eh_gas["CHP"][t] * devs["CHP"]["eta_th"])
            # Gas boiler
            model.addConstr(eh_heat["BOI"][t] == eh_gas["BOI"][t] * devs["BOI"]["eta_th"])
            # Gas heat pump
            model.addConstr(eh_heat["GHP"][t] == eh_gas["GHP"][t] * devs["GHP"]["COP"])
            # Biomass CHP
            model.addConstr(eh_power["BCHP"][t] == eh_biom["BCHP"][t] * devs["BCHP"]["eta_el"])
            model.addConstr(eh_heat["BCHP"][t] == eh_biom["BCHP"][t] * devs["BCHP"]["eta_th"])
            # Biomass boiler
            model.addConstr(eh_heat["BBOI"][t] == eh_biom["BBOI"][t] * devs["BBOI"]["eta_th"])
            # Waste CHP
            model.addConstr(eh_power["WCHP"][t] == eh_waste["WCHP"][t] * devs["WCHP"]["eta_el"])
            model.addConstr(eh_heat["WCHP"][t] == eh_waste["WCHP"][t] * devs["WCHP"]["eta_th"])
            # Waste boiler
            model.addConstr(eh_heat["WBOI"][t] == eh_waste["WBOI"][t] * devs["WBOI"]["eta_th"])
            # Electrolyzer
            model.addConstr(eh_hydrogen["ELYZ"][t] == eh_power["ELYZ"][t] * devs["ELYZ"]["eta_el"])
            # Fuel cell
            model.addConstr(eh_power["FC"][t] == eh_hydrogen["FC"][t] * devs["FC"]["eta_el"])
            # Heat must be used
            model.addConstr(eh_heat["FC"][t] == eh_hydrogen["FC"][t] * devs["FC"]["eta_th"])
            # Sabatier reactor
            model.addConstr(eh_gas["SAB"][t] == eh_hydrogen["SAB"][t] * devs["SAB"]["eta"])
    else:
        for t in time_steps:
            # Electric heat pump
            # todo: variable COP
            model.addConstr(eh_heat["HP"][t] == eh_power["HP"][t] * technical_param_eh["HP"]["COP"])
            # Electric boiler
            model.addConstr(eh_heat["EB"][t] == eh_power["EB"][t] * technical_param_eh["EB"]["eta_th"])
            # Compression chiller
            model.addConstr(eh_cool["CC"][t] == eh_power["CC"][t] * technical_param_eh["CC"]["COP"])
            # Absorption chiller
            model.addConstr(eh_cool["AC"][t] == eh_heat["AC"][t] * technical_param_eh["AC"]["eta_th"])
            # Gas CHP
            model.addConstr(eh_power["CHP"][t] == eh_gas["CHP"][t] * technical_param_eh["CHP"]["eta_el"])
            model.addConstr(eh_heat["CHP"][t] == eh_gas["CHP"][t] * technical_param_eh["CHP"]["eta_th"])
            # Gas boiler
            model.addConstr(eh_heat["BOI"][t] == eh_gas["BOI"][t] * technical_param_eh["BOI"]["eta_th"])
            # Gas heat pump
            model.addConstr(eh_heat["GHP"][t] == eh_gas["GHP"][t] * technical_param_eh["GHP"]["COP"])
            # Biomass CHP
            model.addConstr(eh_power["BCHP"][t] == eh_biom["BCHP"][t] * technical_param_eh["BCHP"]["eta_el"])
            model.addConstr(eh_heat["BCHP"][t] == eh_biom["BCHP"][t] * technical_param_eh["BCHP"]["eta_th"])
            # Biomass boiler
            model.addConstr(eh_heat["BBOI"][t] == eh_biom["BBOI"][t] * technical_param_eh["BBOI"]["eta_th"])
            # Waste CHP
            model.addConstr(eh_power["WCHP"][t] == eh_waste["WCHP"][t] * technical_param_eh["WCHP"]["eta_el"])
            model.addConstr(eh_heat["WCHP"][t] == eh_waste["WCHP"][t] * technical_param_eh["WCHP"]["eta_th"])
            # Waste boiler
            model.addConstr(eh_heat["WBOI"][t] == eh_waste["WBOI"][t] * technical_param_eh["WBOI"]["eta_th"])
            # Electrolyzer
            model.addConstr(eh_hydrogen["ELYZ"][t] == eh_power["ELYZ"][t] * technical_param_eh["ELYZ"]["eta_el"])
            # Fuel cell
            model.addConstr(eh_power["FC"][t] == eh_hydrogen["FC"][t] * technical_param_eh["FC"]["eta_el"])
            # Heat must be used
            model.addConstr(eh_heat["FC"][t] == eh_hydrogen["FC"][t] * technical_param_eh["FC"]["eta_th"])
            # Sabatier reactor
            model.addConstr(eh_gas["SAB"][t] == eh_hydrogen["SAB"][t] * technical_param_eh["SAB"]["eta"])


    # %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    # ADD CONSTRAINTS

    # Device generation <= device capacity
    for n in range(nb):
        for t in time_steps:
            for device in ["HP", "CHP", "BOI"]:
                model.addConstr(heat_dom[device][n][t] <= buildingData[n]["capacities"][device], name=str(device) + "_heat_cap_" + str(n))

    for n in range(nb):
        for t in time_steps:
            for device in ["EH", ]:
                model.addConstr(power_dom[device][n][t] <= buildingData[n]["capacities"][device], name=str(device) + "_heat_cap_" + str(n))

    for n in range(nb):
        for t in time_steps:
            model.addConstr(heat_dom["STC"][n][t] <= STC_heat[n][t], name=str("STC") + "_heat_cap_" + str(n) + str(t))


    for n in range(nb):
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


            # Electric heater
            model.addConstr(heat_dom["EH"][n][t] + dhw_dom["EH"][n][t] == power_dom["EH"][n][t],
                                name="EH_heat_power_dhw_balance_" + str(n) + "_" + str(t))

            # if EH exists, it has to produce a certain amount of dhw
            # (60-35)/(60-10) = 0.5, (60-55)/(60-10) = 0.1
            # TODO: In oder to ensure flexible operation of EH, just use daily sums. Alternative: time step wise
            if buildingData[n]["capacities"]["HP"] == 0:
                model.addConstr(dhw_dom["EH"][n][t] + heat_dom["EH"][n][t]  == 0,
                                name="EH_energybalance_" + str(n) + "_" + str(t))
            elif buildingData[n]["envelope"].construction_year >= 1995 and buildingData[n]["capacities"]["HP"] > 0:
                model.addConstr(dhw_dom["EH"][n][t] >= Q_DHW[n][t] * (60-35)/(60-10),
                                name="EH_energybalance_" + str(n) + "_" + str(t))
            else:
                model.addConstr(dhw_dom["EH"][n][t] >= Q_DHW[n][t] * (60-55)/(60-10),
                                name="EH_energybalance_" + str(n) + "_" + str(t))


            # CHP
            model.addConstr(heat_dom["CHP"][n][t] == param_dec_devs["CHP"]["eta_th"] * gas_dom["CHP"][n][t],
                            name="chp_energybalance_heating" + str(n) + "_" + str(t))

            model.addConstr(power_dom["CHP"][n][t] == param_dec_devs["CHP"]["eta_el"] * gas_dom["CHP"][n][t],
                            name="chp_energybalance_power" + str(n) + "_" + str(t))

            # BOILER
            model.addConstr(heat_dom["BOI"][n][t] == param_dec_devs["BOI"]["eta_th"] * gas_dom["BOI"][n][t],
                            name="boiler_energybalance_heating" + str(n) + "_" + str(t))

#    for n in nodes:
#        # balance for high temp heat generators
#        model.addConstr(sum(heat_dom["EH"][n][t] + heat_dom["HP55"][n][t] + heat_dom["boiler"][n][t] + heat_dom["CHP"][n][t] for t in time_steps)
#                            >= (55-35)/(55-15) * sum(nodes[n]["dhw"][:,idx][t] for t in time_steps), name="Dhw_high_temp_" + str(n) + "_" + str(t))


    # min and max storage level, charging and discharging
    for n in range(nb):
        for device in ecs_storage:
            for t in time_steps:
                model.addConstr(ch_dom[device][n][t] <= buildingData[n]["capacities"][device] * param_dec_devs[device]["coeff_ch"],
                                name="max_ch_cap_" + str(device) + "_" + str(n) + "_" + str(t))
                model.addConstr(dch_dom[device][n][t] <= buildingData[n]["capacities"][device] * param_dec_devs[device]["coeff_ch"],
                                name="max_dch_cap_" + str(device) + "_" + str(n) + "_" + str(t))

                model.addConstr(soc_dom[device][n][t] <= param_dec_devs[device]["soc_max"] * buildingData[n]["capacities"][device],
                                name="max_soc_bat_" + str(device) + "_" + str(n) + "_" + str(t))
                model.addConstr(soc_dom[device][n][t] >= param_dec_devs[device]["soc_min"] * buildingData[n]["capacities"][device],
                                name="max_soc_bat_" + str(device) + "_" + str(n) + "_" + str(t))

    # %% EV CONSTRAINTS CONSTRAINTS
    device = "EV"
    for n in range(nb):
        # Energy balance
        for t in time_steps:
            if t == 0:
                soc_prev = soc_init[device][n]
            else:
                soc_prev = soc_dom[device][n][t - 1]

            model.addConstr(soc_dom[device][n][t] == soc_prev
                            + ch_dom[device][n][t] * param_dec_devs[device]["eta_ch"]* dt
                            - dch_dom[device][n][t] / param_dec_devs[device]["eta_ch"] * dt
                            - EV_dem[n][t],
                            name="EV_storage_balance_" + str(n) + "_" + str(t))

            if t == last_time_step:
                model.addConstr(soc_dom[device][n][t] == soc_init[device][n])

            model.addConstr(dch_dom[device][n][t] <= binary[device][n][t] * 1000000,
                            name="Binary1_ev" + str(n) + "_" + str(t))
            model.addConstr(ch_dom[device][n][t] <= (1 - binary[device][n][t]) * 1000000,
                            name="Binary2_ev" + str(n) + "_" + str(t))

            if buildingData[n]["buildingFeatures"]["ev_charging"] == "on_demand":
                model.addConstr(ch_dom[device][n][t] >= EV_dem[n][t], name="res_power_ev")
                model.addConstr(dch_dom[device][n][t] == 0, name="p_feed_ev")
            else:
                # Charging only possible when someone is at home
                if occ[n][t] != 0:
                    #if t == last_time_step:
                    #    model.addConstr(ch_dom[device][n][t] <= nodes[n][device]["cap"])
                    #else: model.addConstr(ch_dom[device][n][t] <= nodes[n]["ev_avail"][:,idx][t] * nodes[n][device]["max_ch_ev"])
                    if buildingData[n]["buildingFeatures"]["ev_charging"] == "bi_directional":
                        model.addConstr(dch_dom[device][n][t] <= buildingData[n]["capacities"][device] * param_dec_devs[device]["coeff_ch"])
                    else:
                        model.addConstr(dch_dom[device][n][t] == 0)
                else:
                    model.addConstr(ch_dom[device][n][t] == 0)
                    model.addConstr(dch_dom[device][n][t] == 0)

    # %% DOMESTIC FLEXIBILITIES

    # SOC coupled over all times steps (Energy amount balance, kWh)
    for n in range(nb):
        # Energy balance energy storages
        for t in time_steps:
            device = "TES"
            if t == 0:
                    soc_prev = soc_init[device][n]
            else:
                    soc_prev = soc_dom[device][n][t - 1]

            model.addConstr(soc_dom[device][n][t] == soc_prev * param_dec_devs[device]["eta_standby"]
                                                     + (ch_dom[device][n][t]  * param_dec_devs[device]["eta_ch"]
                                                     - dch_dom[device][n][t] / param_dec_devs[device]["eta_ch"])*dt,
                            name= str(device) + "_storage_balance_" + str(n) + "_" + str(t))

            if t == last_time_step:
                model.addConstr(soc_dom[device][n][t] == soc_init[device][n],
                                name="End_" + str(device) + "_storage_" + str(n) + "_" + str(t))

            model.addConstr(ch_dom[device][n][t] == heat_dom["CHP"][n][t] + heat_dom["HP"][n][t] + heat_dom["BOI"][n][t]
                            + heat_dom["EH"][n][t] + dhw_dom["EH"][n][t] + heat_dom["STC"][n][t],
                            name="Heat_charging_" + str(n) + "_" + str(t))
            model.addConstr( heat_dom["heat_grid"][n][t] == Q_DHW[n][t] + Q_heating[n][t], #dch_dom[device][n][t] +
                            name="Heat_discharging_" + str(n) + "_" + str(t))

            device = "BAT"
            if t == 0:
                soc_prev = soc_init[device][n]
            else:
                soc_prev = soc_dom[device][n][t - 1]

            model.addConstr(soc_dom[device][n][t] == soc_prev * param_dec_devs[device]["eta_standby"]
                            + (ch_dom[device][n][t] * param_dec_devs[device]["eta_ch"]
                            - dch_dom[device][n][t] / param_dec_devs[device]["eta_ch"])*dt,
                            name=str(device) + "_storage_balance_" + str(n) + "_" + str(t))

            if t == last_time_step:
                model.addConstr(soc_dom[device][n][t] == soc_init[device][n],
                                name="End_" + str(device) + "_storage_" + str(n) + "_" + str(t))

            model.addConstr(dch_dom[device][n][t] <= binary[device][n][t] * 1000000,
                            name="Binary1_ev" + str(n) + "_" + str(t))
            model.addConstr(ch_dom[device][n][t] <= (1 - binary[device][n][t]) * 1000000,
                            name="Binary2_ev" + str(n) + "_" + str(t))

    for n in range(nb):
        for t in time_steps:
            model.addConstr(res_dom["power"][n][t] <= binary["HLINE"][n][t] * 1000000,
                            name="Binary1_" + str(n) + "_" + str(t))
            model.addConstr(res_dom["feed"][n][t] <= (1 - binary["HLINE"][n][t]) * 1000000,
                            name="Binary2_" + str(n) + "_" + str(t))

    # Residual loads
    for t in time_steps:
        # Residual network electricity demand (Power balance in Watt)
        model.addConstr(residual["power"][t] == sum(res_dom["power"][n][t] for n in range(nb)), name="res_power"+ str(t))
        model.addConstr(residual["feed"][t] == sum(res_dom["feed"][n][t] for n in range(nb)), name="res_feed"+ str(t))

    # %% BUILDINGS ENERGY BALANCES (Power balance, kW)
    # Electricity balance
    for n in range(nb):
        for t in time_steps:
            model.addConstr(res_dom["power"][n][t] + PV_gen[n][t]
                            + power_dom["CHP"][n][t] + dch_dom["BAT"][n][t] + dch_dom["EV"][n][t]
                            == elec_dem[n][t] + ch_dom["EV"][n][t]
                            + power_dom["HP"][n][t] + power_dom["EH"][n][t] +
                            ch_dom["BAT"][n][t]  + res_dom["feed"][n][t],
                            name="Electricity_balance_" + str(n) + "_" + str(t))
            model.addConstr(res_dom["feed"][n][t] <= power_dom["PV"][n][t] + power_dom["CHP"][n][t] + dch_dom["BAT"][n][t], # + dch_dom["EV"][n][t],
                            name="Feed-in_max_" + str(n) + "_" + str(t))

    # %% ENERGY HUB ENERGY BALANCES
    for t in time_steps:
        # Heating balance
        model.addConstr(eh_heat["STC"][t] + eh_heat["HP"][t] + eh_heat["EB"][t] + eh_heat["CHP"][t]
                        + eh_heat["BOI"][t] + eh_heat["GHP"][t] + eh_heat["BCHP"][t] + eh_heat["BBOI"][t]
                        + eh_heat["WCHP"][t] + eh_heat["WBOI"][t] + eh_heat["FC"][t] +eh_dch["TES"][t]
                        == eh_heat["grid"][t] + eh_heat["AC"][t] + eh_ch["TES"][t],
                        name="Heating_balance_EnergyHub_" + str(t))
        # todo: heat losses heat grid
        model.addConstr(eh_heat["grid"][t] >= sum(heat_dom["heat_grid"][n][t] for n in range(nb)),
                        name="Heat_Supply_EnergyHub_" + str(t))
        # Electricity balance
        model.addConstr(eh_power["PV"][t] + eh_power["WT"][t] + eh_power["WAT"][t] + eh_power["CHP"][t]
                        + eh_power["BCHP"][t] + eh_power["WCHP"][t] + eh_power["FC"][t] + eh_power["from_grid"][t]
                        == eh_power["HP"][t] + eh_power["EB"][t] + eh_power["CC"][t]
                        + eh_power["ELYZ"][t] + eh_ch["BAT"][t] + eh_power["to_grid"][t],
                        name="Electricity_balance_EnergyHub_" + str(t))
        # # Cooling balance
        # model.addConstr(eh_cool["AC"][t] + eh_cool["CC"][t] == dem["cool"][t] + eh_ch["CTES"][t])
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
            model.addConstr(eh_soc[device][t] == eh_soc_prev * (1-technical_param_eh[device]["sto_loss"])
                            + eh_ch[device][t] - eh_dch[device][t],
                            name="Storage_balance_energyHub" + str(device) + "_" + str(t))
            if t == last_time_step:
                model.addConstr(eh_soc[device][t] == eh_soc_init[device])

    # Electricity balance neighborhood (Power balance in Watt)
    for t in time_steps:
        model.addConstr(residual["feed"][t] + power["from_grid"][t] + eh_power["from_grid"][t]
                        == residual["power"][t] + power["to_grid"][t] + eh_power["to_grid"][t],
                        name="Elec_balance_neighborhood"+ str(t))
        #model.addConstr(power["to_grid"][t] == residual["feed"][t])
        model.addConstr(power["from_grid"][t] <= yTrafo[t] * 10000000,     name="Binary1_" + str(t))
        model.addConstr(power["to_grid"][t] <= (1 - yTrafo[t]) * 10000000, name="Binary2_" + str(t))

    # Gas balance neighborhood (Power balance in Watt)
    for t in time_steps:
        model.addConstr(power["gas_from_grid"][t] + eh_gas["to_grid"][t]
                        == eh_gas["from_grid"][t] + sum(gas_dom["CHP"][n][t] + gas_dom["BOI"][n][t] for n in range(nb)))


    # %% Summation of energy sources
    # Total gas amount taken from grid (Wh)
    model.addConstr(from_grid_total_gas == dt * sum(power["gas_from_grid"][t] for t in time_steps), name="from_grid_total_gas")
    # Total electricity amount taken from grid (Wh)
    model.addConstr(from_grid_total_el == dt * sum(power["from_grid"][t] for t in time_steps), name="from_grid_total_el")
    # Total electricity feed-in (Wh)
    model.addConstr(to_grid_total_el == dt * sum(power["to_grid"][t] for t in time_steps), name="to_grid_total_el")
    # Total hydrogen amount taken from grid (Wh)
    model.addConstr(from_grid_total_hydrogen == dt * sum(eh_hydrogen["import"][t] for t in time_steps), name="from_grid_total_hydrogen")
    # Total biomass used (Wh)
    model.addConstr(total_biomass_used == dt * sum(eh_biom["import"][t] for t in time_steps), name="total_biomass_used")
    # Total waste used (Wh)
    model.addConstr(total_waste_used == dt * sum(eh_waste["import"][t] for t in time_steps), name="total_waste_used")


    # %% OBJECTIVE FUNCTIONS
    # select the objective function based on input parameters
    ### Total operational costs
    if optiData["webtool"] == True:
        model.addConstr(operational_costs == from_grid_total_el * optiData["C_dem_electricity"]
                                            - to_grid_total_el * optiData["C_feed_electricity"]
                                            + from_grid_total_gas * optiData["C_dem_gas"]
                                            + from_grid_total_hydrogen * optiData["price_hydrogen"]
                                            + total_biomass_used * optiData["price_biomass"]
                                            + total_waste_used * optiData["price_waste"]
                                            , name="Total_amount_operational_costs")
    else:
        model.addConstr(operational_costs == from_grid_total_el * ecoData["C_dem_electricity"]
                                            - to_grid_total_el * ecoData["C_feed_electricity"]
                                            + from_grid_total_gas * ecoData["C_dem_gas"]
                                            + from_grid_total_hydrogen * model_param_eh["price_hydrogen"]
                                            + total_biomass_used * model_param_eh["price_biomass"]
                                            + total_waste_used * model_param_eh["price_waste"]
                                            ,name="Total_amount_operational_costs")

    # Emissions
    if optiData["webtool"] == True:
        model.addConstr(co2_total == from_grid_total_el * optiData["Emi_elec"]
                                    + from_grid_total_gas * optiData["Emi_gas"]
                                    + from_grid_total_hydrogen * optiData["Emi_hydrogen"]
                                    + total_biomass_used * optiData["Emi_biomass"]
                                    + total_waste_used * optiData["Emi_waste"]
                                    , name="Total_amount_emissions")
    else:
        model.addConstr(co2_total == from_grid_total_el * ecoData["Emi_elec"]
                                    + from_grid_total_gas * ecoData["Emi_gas"]
                                    + from_grid_total_hydrogen * model_param_eh["price_hydrogen"]
                                    + total_biomass_used * model_param_eh["price_biomass"]
                                    + total_waste_used * model_param_eh["price_waste"])

    # daily peaks
    for d in days:
        model.addConstr(daily_peak[d] == gp.max_(power["from_grid"][t] for t in range(d * int(24/dt), d * int(24/dt) + int(24/dt))))
    model.addConstr(peaksum == sum(daily_peak[d] for d in days))

    # Set objective
    if optiData["webtool"] == True:
        if optiData["obj"] == "costs":
            model.addConstr(obj == operational_costs + peaksum * 1)
        elif optiData["obj"] == "co2_total":
            model.addConstr(obj == co2_total + peaksum * 1)
    else:
        model.addConstr(obj == operational_costs + peaksum * 1)

    # Carry out optimization
    model.optimize()

    later = time.time()
    difference = later - now
    print("********************************************")
    print("Model run time was " + str(difference) + " seconds")
    print("********************************************")

    if model.status == gp.GRB.Status.INFEASIBLE or model.status == gp.GRB.Status.INF_OR_UNBD:
        print(model.status)
        model.computeIIS()
        f = open('errorfile.txt','w')
        f.write('\nThe following constraint(s) cannot be satisfied:\n')
        for c in model.getConstrs():
            if c.IISConstr:
                f.write('%s' % c.constrName)
                f.write('\n')
        f.close()

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
    for n in range(nb):
        results[n] = {}
        results[n]["res_load"] = []
        results[n]["res_inj"] = []
        results[n]["res_gas"] = []
        for t in time_steps:
            results[n]["res_load"].append(round(res_dom["power"][n][t].X, 0))
            results[n]["res_inj"].append(round(res_dom["feed"][n][t].X, 0))
            results[n]["res_gas"].append(round(gas_dom["BOI"][n][t].X + gas_dom["CHP"][n][t].X+gas_dom["FC"][n][t].X, 0))

    for n in range(nb):
        for device in ecs_heat:
            results[n][device] = {}
            results[n][device]["Q_th"] = []
            for t in time_steps:
                results[n][device]["Q_th"].append(round(heat_dom[device][n][t].X, 0))

    for n in range(nb):
        for device in hp_modi:
            results[n][device] = {}
            results[n][device]["Q_th"] = []
            results[n][device]["P_el"] = []
            for t in time_steps:
                results[n][device]["Q_th"].append(round(heat_mode[device][n][t].X, 0))
                results[n][device]["P_el"].append(round(power_mode[device][n][t].X, 0))

    for n in range(nb):
        for device in ecs_power:
            results[n][device] = {}
            results[n][device]["P_el"] = []
            for t in time_steps:
                results[n][device]["P_el"].append(round(power_dom[device][n][t].X, 0))

    for n in range(nb):
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
