#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created 26.02.2024
@author: Joel Schölzel
"""
import os, json
import gurobipy as gp
import time

def run_opti_central(model, buildingData, site, cluster, srcPath):
    now = time.time()

    # %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    # Setting up the model
    # number of buildings in neighborhood
    nb = len(buildingData)

    # load parameters of decentral energy conversion devices
    path = srcPath
    param_dec_devs = {}
    with open(path + "/data/" + "decentral_device_data.json") as json_file:
        jsonData = json.load(json_file)
        for subData in jsonData:
            param_dec_devs[subData["abbreviation"]] = {}
            for subsubData in subData["specifications"]:
                param_dec_devs[subData["abbreviation"]][subsubData["name"]] = subsubData["value"]

    T_e = site["T_e_cluster"][cluster]  # ambient temperature [°C]
    Q_DHW = {}      # DHW (domestic hot water) demand [W]
    Q_heating = {}  # space heating [W]
    PV_gen = {}     # electricity generation of PV [W]
    STC_heat = {}   # electricity generation of PV [W]
    EV_dem = {}     # electricity demand electric vehicle (EV) [Wh]
    elec_dem = {}   # electricity demand for appliances and lighting [W]
    for n in range(nb):
        Q_DHW[n] = buildingData[n]["user"].dhw_cluster[cluster]
        Q_heating[n] = buildingData[n]["user"].heat_cluster[cluster]
        PV_gen[n] = buildingData[n]["generationPV_cluster"][cluster]
        STC_heat[n] = buildingData[n]["generationSTC_cluster"][cluster]
        EV_dem[n] = buildingData[n]["user"].car_cluster[cluster]
        elec_dem[n] = buildingData[n]["user"].elec_cluster[cluster]

    ecoData = {}
    timeData = {}
    for data in ("eco", "time"):
        with open(path + "/data/" + data + "_data.json") as json_file:
            jsonData = json.load(json_file)
            for subData in jsonData:
                if data == "eco":
                    ecoData[subData["name"]] = subData["value"]
                else:
                    timeData[subData["name"]] = subData["value"]

    time_steps = range(int(timeData["clusterLength"] / timeData["timeResolution"]))
    dt = timeData["timeResolution"] / timeData["dataResolution"]
    last_time_step = len(time_steps) - 1

    # %% Sets of energy conversion systems
    # heat generation devices (heat pump (HP), electric heating (EH),
    # combined heat and power (CHP), fuel cell (FC), boiler (BOI), solar thermal collector (STC))
    # TODO: add STC
    ecs_heat = ("HP", "EH", "CHP", "FC", "BOI", "STC")
    ecs_power = ("HP", "EH", "CHP", "FC", "PV")  # power consuming/producing devices (photovoltaic (PV))
    ecs_sell = ("CHP", "FC", "PV", "BAT")
    ecs_gas = ("CHP", "FC", "BOI")  # gas consuming devices
    ecs_storage = ("BAT", "TES") #, "EV")  # battery (BAT), thermal energy storage (TES), electric vehicle (EV)
    hp_modi = ("HP35", "HP55")  # modi of the HP with different HP supply temperatures in °C

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

    # daily peak
    days = [0,1,2,3,4,5,6]
    daily_peak = {}
    for d in days:
        daily_peak[d] = model.addVar(vtype="c",lb=-gp.GRB.INFINITY,name="peak_network_load")
    peaksum = model.addVar(vtype="c",lb=-gp.GRB.INFINITY,name="sum_peak_daily_network_load")

    # Total operational costs
    operational_costs = model.addVar(vtype="C",lb=-gp.GRB.INFINITY,name="Cost_total")
    # Total gross CO2 emissions
    co2_total = model.addVar(vtype="c",lb=-gp.GRB.INFINITY,name="Emission_total")

    # Objective function
    obj = model.addVar(vtype="C",lb=-gp.GRB.INFINITY,name="obj")

    # %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    # DEFINE OBJECTIVE FUNCTION
    model.update()
    model.setObjective(obj)
    model.ModelSense = gp.GRB.MINIMIZE

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

            # self.m.addConstr(
            #    (self.heat_mode["HP35", t] == self.heat_mode_eh[t] + self.heat_mode_tes[t]
            #     for t in self.timesteps),
            #    name="Conversion_heat_35_" + str(self.id))

            # Activity of HP modus: HP can only produce heat if modus is activated
           # for device in hp_modi:
           #     model.addConstr(heat_mode[device][n][t] <= buildingData[n]["capacities"]["HP"],
           #         name="Activity_mode_" + str(n) + "_" + str(t))

            # on/off operation of HP
#            model.addConstr(heat_dom["HP35"][n][t] <= binary["HP35"][n][t] * nodes[n][device]["cap"],
#                            name="heatpump_operation_binary" + str(n) + "_" + str(t))
#            # on/off limit for HP due to TES temperatures
#            model.addConstr(soc_dom["TES"][n][t] <= (1 - binary["HP35"][n][t] * (1 - 15/30)) * soc_nom["TES"][n],
#                            name="heatpump_soc_temp_relation" + str(n) + "_" + str(t))
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
    #for n in nodes:
    #    # Energy balance
    #    for t in time_steps:
    #        if t == 0:
    #            soc_prev = soc_init[device][n]
    #        else:
    #            soc_prev = soc_dom[device][n][t - 1]

    #        model.addConstr(soc_dom[device][n][t] == soc_prev
    #                        + ch_dom[device][n][t] * nodes[n][device]["eta_ch_ev"] * dt
    #                        - dch_dom[device][n][t] / nodes[n][device]["eta_dch_ev"] * dt
    #                        - nodes[n]["ev_dem_leave"][:,idx][t])

    #        if t == last_time_step:
    #            model.addConstr(soc_dom[device][n][t] == soc_init[device][n])

     #       model.addConstr(dch_dom[device][n][t] <= binary[device][n][t] * nodes[n][device]["max_dch_ev"],
    #                        name="Binary1_ev" + str(n) + "_" + str(t))
    #        model.addConstr(ch_dom[device][n][t] <= (1 - binary[device][n][t]) * nodes[n][device]["max_ch_ev"],
    #                        name="Binary2_ev" + str(n) + "_" + str(t))

    #        model.addConstr(soc_dom[device][n][t] >= nodes[n][device]["min_soc"] * nodes[n][device]["cap"])
    #        model.addConstr(soc_dom[device][n][t] <= nodes[n][device]["max_soc"] * nodes[n][device]["cap"])

    #        if options["ev_charging"] == "on_demand":
    #            model.addConstr(ch_dom[device][n][t] == nodes[n]["ev_dem_arrive"][:,idx][t], name="res_power_ev")
     #           model.addConstr(dch_dom[device][n][t] == 0, name="p_feed_ev")
     #       else:
     #           if t == last_time_step:
     #               model.addConstr(ch_dom[device][n][t] <= nodes[n][device]["cap"])
     #           else: model.addConstr(ch_dom[device][n][t] <= nodes[n]["ev_avail"][:,idx][t] * nodes[n][device]["max_ch_ev"])
     #           if options["ev_charging"] == "bi_directional":
     #               model.addConstr(dch_dom[device][n][t] <= nodes[n]["ev_avail"][:, idx][t] * nodes[n][device]["max_dch_ev"])
     #           else:
     #               model.addConstr(dch_dom[device][n][t] == 0)

    # %% DOMESTIC FLEXIBILITIES

    # SOC coupled over all times steps (Energy amount balance, kWh)
    for n in range(nb):
        # Energy balance energy storages
        for t in time_steps:
            #for device in ecs_storage:
            device = "TES"
            if t == 0:
                    soc_prev = soc_init[device][n]
            else:
                    soc_prev = soc_dom[device][n][t - 1]
                #if t == last_time_step:
                #    model.addConstr(soc_dom[device][n][t] == soc_init[device][n],
                #                    name="End_" + str(device) + "_storage_" + str(n) + "_" + str(t))

            model.addConstr(soc_dom[device][n][t] == soc_prev * param_dec_devs[device]["eta_standby"]
                                + ch_dom[device][n][t] * dt
                                - dch_dom[device][n][t] * dt,name= str(device) + "_storage_balance_" + str(n) + "_" + str(t))

            model.addConstr(ch_dom[device][n][t] == heat_dom["CHP"][n][t] + heat_dom["HP"][n][t] + heat_dom["BOI"][n][t]
                            + heat_dom["EH"][n][t] + dhw_dom["EH"][n][t] + heat_dom["STC"][n][t],
                            name="Heat_charging_" + str(n) + "_" + str(t))
            model.addConstr(dch_dom[device][n][t] == Q_DHW[n][t] + Q_heating[n][t],
                            name="Heat_discharging_" + str(n) + "_" + str(t))

            device = "BAT"
            if t == 0:
                soc_prev = soc_init[device][n]
            else:
                soc_prev = soc_dom[device][n][t - 1]
            # if t == last_time_step:
            #    model.addConstr(soc_dom[device][n][t] == soc_init[device][n],
            #                    name="End_" + str(device) + "_storage_" + str(n) + "_" + str(t))

            model.addConstr(soc_dom[device][n][t] == soc_prev * param_dec_devs[device]["eta_standby"]
                            + ch_dom[device][n][t] * dt
                            - dch_dom[device][n][t] * dt,
                            name=str(device) + "_storage_balance_" + str(n) + "_" + str(t))




    # %% ENERGY BALANCES (Power balance, kW)

    for n in range(nb):
        for t in time_steps:
            model.addConstr(res_dom["power"][n][t] + PV_gen[n][t]
                            + power_dom["CHP"][n][t] + dch_dom["BAT"][n][t] #+ dch_dom["EV"][n][t]
                            == elec_dem[n][t] #+ ch_dom["EV"][n][t]
                            + power_dom["HP"][n][t] + power_dom["EH"][n][t] +
                            ch_dom["BAT"][n][t]  + res_dom["feed"][n][t],
                            name="Electricity_balance_" + str(n) + "_" + str(t))

            model.addConstr(res_dom["feed"][n][t] <= power_dom["PV"][n][t] + power_dom["CHP"][n][t] + dch_dom["BAT"][n][t], # + dch_dom["EV"][n][t],
                            name="Feed-in_max_" + str(n) + "_" + str(t))


    for n in range(nb):
        for t in time_steps:
            model.addConstr(res_dom["power"][n][t] <= binary["HLINE"][n][t] * 1000000,
                            name="Binary1_" + str(n) + "_" + str(t))
            model.addConstr(res_dom["feed"][n][t] <= (1 - binary["HLINE"][n][t]) * 1000000,
                            name="Binary2_" + str(n) + "_" + str(t))

    # %% SUM UP: BUILDING CONSTRAINTS

    # Residual loads
    for t in time_steps:
        # Residual network electricity demand (Power balance, MW)
        model.addConstr(residual["power"][t] == sum(res_dom["power"][n][t] for n in range(nb)), name="res_power"+ str(t))
        model.addConstr(residual["feed"][t] == sum(res_dom["feed"][n][t] for n in range(nb)), name="res_feed"+ str(t))

    # %% ENERGY BALANCES: NETWORK AND ENERGY HUB

    for t in time_steps:
        # Electricity balance neighborhood(Power balance, MW)
        model.addConstr(residual["feed"][t] + power["from_grid"][t] == residual["power"][t] + power["to_grid"][t],
                        name="Elec_balance_neighborhood"+ str(t))
        #model.addConstr(power["to_grid"][t] == residual["feed"][t])
        model.addConstr(power["from_grid"][t] <= yTrafo[t] * 10000000,     name="Binary1_" + str(n) + "_" + str(t))
        model.addConstr(power["to_grid"][t] <= (1 - yTrafo[t]) * 10000000, name="Binary2_" + str(n) + "_" + str(t))


    # %% SUM UP TOTAL ELECTRICITY FROM AND TO GRID

    # Total electricity amounts taken from grid (Energy amounts, MWh)
    model.addConstr(from_grid_total_el == dt * sum(power["from_grid"][t] for t in time_steps), name="from_grid_total_el")

    # Total gas amounts taken from grid (Energy amounts, MWh)
    for t in time_steps:
        model.addConstr(power["gas_from_grid"][t] == sum(gas_dom["CHP"][n][t] + gas_dom["BOI"][n][t] for n in range(nb)))

    model.addConstr(from_grid_total_gas == dt * sum(power["gas_from_grid"][t] for t in time_steps))

    # Total electricity feed-in (Energy amounts, MWh)
    model.addConstr(to_grid_total_el == dt * sum(power["to_grid"][t] for t in time_steps), name="to_grid_total_el")

    # %% OBJECTIVE FUNCTIONS
    # select the objective function based on input parameters

    ### Total operational costs
    #model.addConstr(
    #    operational_costs == from_grid_total_el * params["eco"]["elec_price"]
    #    + power["from_grid"][t] * params["eco"]["peak_price"] - to_grid_total_el * params["eco"]["eeg_pv"])
    ### Total operational costs without peak price
    model.addConstr(operational_costs == from_grid_total_el * ecoData["C_dem_electricity"]
                                        - to_grid_total_el * ecoData["C_feed_electricity"]
                                        + from_grid_total_gas * ecoData["C_dem_gas"], name="operational_costs")

    # Emissions
    model.addConstr(co2_total == dt * sum(power["from_grid"][t] for t in time_steps) * ecoData["Emi_elec"]
                                 + dt * sum(power["to_grid"][t] for t in time_steps) * ecoData["Emi_pv"]
                                 + from_grid_total_gas * ecoData["Emi_gas"]) # kWh*kg/kWh

    # daily peaks
    for d in days:
        #model.addConstr(daily_peak[d] >= sum(power["to_grid"][t] for t in range(d*96, d*96+96)))
        model.addConstr(daily_peak[d] == gp.max_(power["from_grid"][t] for t in range(d * 96, d * 96 + 96)))
    model.addConstr(peaksum == sum(daily_peak[d] for d in days))

    # Set objective
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


    """

    # add results of the decentral devices
    dev_var = 
    device = ("TES", "BAT", "EV")
    for n in range(nb):  # loop over buildings
        for dev in device:
            for v in dev_var:
                for t in time_steps:
                    results[n][str(dev) + "_" + v].append(round(model.getVarByName(v + "_" + str(id) + "[" + str(t) + "]").x, 0))

    # add results of the decentral devices
    dev_var = ("ch", "dch", "soc")
    device = ("TES", "BAT", "EV")
    for n in range(nb):  # loop over buildings
        for dev in device:
            for v in dev_var:
                for t in time_steps:
                    results[n][str(dev) + "_" + v].append(round(model.getVarByName(v + "_" + str(id) + "[" + str(t) + "]").x, 0))
    """




    return results