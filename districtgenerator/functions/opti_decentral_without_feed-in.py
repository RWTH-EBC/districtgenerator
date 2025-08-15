#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created 26.02.2024
@author: Joel Schölzel
"""
import os, json
import gurobipy as gp
import time
import math



def run_opti_decentral(model, data, cluster):


    timeData = data.time
    ecoData = data.ecoData
    siteData = data.site
    param_dec_devs = data.decentral_device_data
    model_param_eh = data.params_ehdo_model
    buildingData = data.district
    price_per_m = 100  # €/m z.B.

    # calculate distance between buildings
    def distance(i, j):
        x1, y1 = buildingData[i]["position"]
        x2, y2 = buildingData[j]["position"]
        return math.sqrt((x2 - x1)**2 + (y2 - y1)**2)

    now = time.time()
    # %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    # Setting up the model
    # number of buildings in neighborhood
    nb = len(buildingData)
    time_steps = range(int(timeData["clusterLength"] / timeData["timeResolution"]))
    dt = timeData["timeResolution"] / timeData["dataResolution"]
    last_time_step = len(time_steps) - 1

    T_e = siteData["T_e_cluster"][cluster]  # ambient temperature [°C]
    Q_DHW = {}      # DHW (domestic hot water) demand [W]
    Q_heating = {}  # space heating [W]
    PV_gen = {}     # electricity generation of PV [W]
    STC_heat = {}   # heat generation of SolarThermal [W]
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
        except:
            PV_gen[n] = [0] * len(elec_dem[n])
            STC_heat[n] = [0] * len(elec_dem[n])


    # %% Sets of energy conversion systems
    # heat generation devices (heat pump (HP), electric heating (EH),
    # solar thermal collector (STC))
    ecs_heat = ("HP", "EH", "STC") # heat producing devices
    ecs_power = ("HP", "EH", "PV")  # power consuming/producing devices 
    ecs_storage = ("TES", "BAT")  # storage systems
    hp_modi = ("HP35", "HP55")  # HP operation modes

    try:
        a = buildingData[0]["capacities"]
    except KeyError:
        for n in range(nb):
            buildingData[n]["capacities"] = {}
            buildingData[n]["capacities"]["PV"] = {}
            buildingData[n]["capacities"]["STC"] = {}
            for dev in ["HP", "EH", "BAT", "TES"]:
                buildingData[n]["capacities"][dev] = 0
            buildingData[n]["capacities"]["PV"]["area"] = 0
            buildingData[n]["capacities"]["STC"]["area"] = 0

    # %% TECHNICAL PARAMETERS
    soc_nom = {}
    soc_nom["TES"] = {}
    soc_nom["BAT"] = {}
    soc_init = {}
    soc_init["BAT"] = {}
    soc_init["TES"] = {}
    for n in range(nb):
        # Define nominal SOC_nom according to capacities
        soc_nom["TES"][n] = buildingData[n]["capacities"]["TES"]
        soc_nom["BAT"][n] = buildingData[n]["capacities"]["BAT"]
        # Initial state of charge
        soc_init["TES"][n] = soc_nom["TES"][n] * 0.5  # Wh
        soc_init["BAT"][n] = soc_nom["BAT"][n] * 0.5  # Wh

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

    # Heat transfer between buildings
    heat_connection = {}
    for i in range(nb):
        heat_connection[i] = {}
        for j in range(nb):
            if i != j:  # no self-connections
                heat_connection[i][j] = {}
                for t in time_steps:
                    heat_connection[i][j][t] = model.addVar(
                        vtype="C",
                        name=f"heat_conn_n{i}_n{j}_t{t}"
                    )
    # Binary decision for possible connection existence (investment variable)
    connection_exists = {}
    for i in range(nb):
        connection_exists[i] = {}
        for j in range(nb):
            if i != j:
                connection_exists[i][j] = model.addVar(
                    vtype="B",  # binary: 1 if pipe installed
                    name=f"conn_exists_n{i}_n{j}"
                )

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


    # connection costs
    connection_costs = {}
    connection_costs = model.addVar(vtype="C", name="connection_costs")

    # %% BALANCING UNIT VARIABLES

    # Electrical power imported from grid per building
    power_from_grid = {}
    for n in range(nb):
        power_from_grid[n] = {}
        for t in time_steps:
            power_from_grid[n][t] = model.addVar(vtype="C", lb=0, name=f"P_from_grid_n{n}_t{t}")

    # total energy amounts taken from grid
    from_grid_total_el = model.addVar(vtype="C",name="from_grid_total_el")

    # Total operational costs
    operational_costs = model.addVar(vtype="C",lb=-gp.GRB.INFINITY,name="Cost_total")
    # Total fixed costs of the district (investment costs)   #needs to be defined
    tech_fixcosts = {
        "PV": siteData["PV_fixcosts"],
        "STC": siteData["STC_fixcosts"],
        "HP": siteData["HP_fixcosts"],
        "EH": siteData["EH_fixcosts"],
        "BAT": siteData["BAT_fixcosts"],
        "TES": siteData["TES_fixcosts"]
    }
    # Binary installation variables for each technology
    y_dev = {}  # 1 if device installed in building n
    for dev in ["PV", "STC", "HP", "EH", "BAT", "TES"]:
        y_dev[dev] = {}
        for n in range(nb):
            y_dev[dev][n] = model.addVar(vtype="B", name=f"install_{dev}_n{n}")

    fixcost_sum = gp.quicksum(
        y_dev[dev][n] * tech_fixcosts[dev]
        for n in range(nb) for dev in ["PV", "STC", "HP", "EH", "BAT", "TES"]
    )

    # Total costs of the district (investment + operational costs + connection costs)
    total_costs = model.addVar(vtype="C", name="total_costs")
    # Total gross CO2 emissions
    co2_total = model.addVar(vtype="C",lb=-gp.GRB.INFINITY,name="Emission_total")

    # Objective function
    obj = model.addVar(vtype="C",lb=-gp.GRB.INFINITY,name="obj")

    # %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    # DEFINE OBJECTIVE FUNCTION
    model.update()
    model.setObjective(obj)
    model.ModelSense = gp.GRB.MINIMIZE

    # %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    # ADD CONSTRAINTS

    # total energy from grid
    for t in time_steps:
        model.addConstr(
            from_grid_total_el[t] == sum(power_from_grid[n][t] for n in range(nb)),
            name=f"grid_import_sum_t{t}"
        )

    # Device generation <= device capacity
    for n in range(nb):
        for t in time_steps:
            for device in ["HP"]:
                model.addConstr(heat_dom[device][n][t] <= buildingData[n]["capacities"][device], name=str(device) + "_heat_cap_" + str(n))

    for n in range(nb):
        for t in time_steps:
            for device in ["EH"]:
                model.addConstr(power_dom[device][n][t] <= buildingData[n]["capacities"][device], name=str(device) + "_heat_cap_" + str(n))

    for n in range(nb):
        for t in time_steps:
            model.addConstr(heat_dom["STC"][n][t] <= STC_heat[n][t], name=str("STC") + "_heat_cap_" + str(n) + str(t))

    for n in range(nb):
        for t in time_steps:
            model.addConstr(power_dom["PV"][n][t] <= PV_gen[n][t], name=str("PV") + "_power_cap_" + str(n) + str(t))



    for n in range(nb):
        for t in time_steps:
            # Energy balance heat pump
            model.addConstr(heat_dom["HP"][n][t] == heat_mode["HP35"][n][t] + heat_mode["HP55"][n][t], name="Conversion_heat_" + str(n) + "_" + str(t))
            model.addConstr(power_dom["HP"][n][t] == power_mode["HP35"][n][t] + power_mode["HP55"][n][t], name="Conversion_power_" + str(n) + "_" + str(t))

            # heat generation of heat pump for each modus
            if buildingData[n]["envelope"].construction_year >= 1995 and buildingData[n]["capacities"]["HP"] > 0:
                # HP can only run in HP35 mode if building is new enough
                model.addConstr(power_mode["HP55"][n][t] == 0, name="Activity_mode_" + str(n) + "_" + str(t))

            elif buildingData[n]["envelope"].construction_year < 1995 and buildingData[n]["capacities"]["HP"] > 0:
                model.addConstr(power_mode["HP35"][n][t] == 0, name="Activity_mode_" + str(n) + "_" + str(t))

            # Energy conversion heat pump modus 35
            model.addConstr(heat_mode["HP35"][n][t] == power_mode["HP35"][n][t] * param_dec_devs["HP"]["grade"] * (273.15 + 35) / (35 - T_e[t]), name="Conversion_HP35_" + str(n) + "_" + str(t))
            # Energy conversion heat pump modus 55
            model.addConstr(heat_mode["HP55"][n][t] == power_mode["HP55"][n][t] * param_dec_devs["HP"]["grade"] * (273.15 + 55) / (55 - T_e[t]), name="Conversion_HP55_" + str(n) + "_" + str(t))


            # Electric heater
            model.addConstr(heat_dom["EH"][n][t] + dhw_dom["EH"][n][t] == power_dom["EH"][n][t], name="EH_heat_power_dhw_balance_" + str(n) + "_" + str(t))

    # min and max storage level, charging and discharging
    for n in range(nb):
        for device in ecs_storage:
            for t in time_steps:
                model.addConstr(ch_dom[device][n][t] <= buildingData[n]["capacities"][device] * param_dec_devs[device]["coeff_ch"], name="max_ch_cap_" + str(device) + "_" + str(n) + "_" + str(t))
                model.addConstr(dch_dom[device][n][t] <= buildingData[n]["capacities"][device] * param_dec_devs[device]["coeff_ch"], name="max_dch_cap_" + str(device) + "_" + str(n) + "_" + str(t)) #check ch oder dch
                model.addConstr(soc_dom[device][n][t] <= param_dec_devs[device]["soc_max"] * buildingData[n]["capacities"][device], name="max_soc_bat_" + str(device) + "_" + str(n) + "_" + str(t))
                model.addConstr(soc_dom[device][n][t] >= param_dec_devs[device]["soc_min"] * buildingData[n]["capacities"][device], name="max_soc_bat_" + str(device) + "_" + str(n) + "_" + str(t))

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

            model.addConstr(soc_dom[device][n][t] == soc_prev * param_dec_devs[device]["eta_standby"] + (ch_dom[device][n][t]  * param_dec_devs[device]["eta_ch"] - dch_dom[device][n][t] / param_dec_devs[device]["eta_ch"])*dt,
                            name= str(device) + "_storage_balance_" + str(n) + "_" + str(t))

            if t == last_time_step:
                model.addConstr(soc_dom[device][n][t] == soc_init[device][n], name="End_" + str(device) + "_storage_" + str(n) + "_" + str(t)) #wichtig, wenn man über lange zeit macht?

            model.addConstr(ch_dom[device][n][t] == heat_dom["HP"][n][t] + heat_dom["EH"][n][t] + dhw_dom["EH"][n][t] + heat_dom["STC"][n][t], name="Heat_charging_" + str(n) + "_" + str(t))
            model.addConstr(dch_dom[device][n][t] + heat_dom["heat_grid"][n][t] == Q_DHW[n][t] + Q_heating[n][t], name="Heat_discharging_" + str(n) + "_" + str(t))

            device = "BAT"
            if t == 0:
                soc_prev = soc_init[device][n]
            else:
                soc_prev = soc_dom[device][n][t - 1]

            model.addConstr(soc_dom[device][n][t] == soc_prev * param_dec_devs[device]["eta_standby"] + (ch_dom[device][n][t] * param_dec_devs[device]["eta_ch"] - dch_dom[device][n][t] / param_dec_devs[device]["eta_ch"])*dt,
                            name=str(device) + "_storage_balance_" + str(n) + "_" + str(t))

            if t == last_time_step:
                model.addConstr(soc_dom[device][n][t] == soc_init[device][n], name="End_" + str(device) + "_storage_" + str(n) + "_" + str(t))


    # %% BUILDINGS ENERGY BALANCES (Power balance, kW)
    # Electricity balance
    for n in range(nb):
        for t in time_steps:
            model.addConstr(PV_gen[n][t] + dch_dom["BAT"][n][t] + power_from_grid[n][t] == elec_dem[n][t] + power_dom["HP"][n][t] + power_dom["EH"][n][t] + ch_dom["BAT"][n][t], name="Electricity_balance_" + str(n) + "_" + str(t))

    
    # 
    model.addConstr(
        connection_costs == gp.quicksum(
            connection_exists[i][j] * price_per_m * distance(i, j)
            for i in range(nb) for j in range(i+1, nb)  # i<j, so no double counting
        ),
        name="total_connection_costs"
    )
       

    # %% Summation of energy sources


    # %% OBJECTIVE FUNCTIONS
    # select the objective function based on input parameters
    ### Total operational costs
    model.addConstr(operational_costs == from_grid_total_el * ecoData["price_supply_el"], name="Total_amount_operational_costs")
    # Total costs
    model.addConstr(total_costs == fixcost_sum + connection_costs + operational_costs, name="Total_costs_constraint")
    # Emissions
    model.addConstr(co2_total == from_grid_total_el * ecoData["co2_el_grid"], name="Total_amount_emissions")



    # Set objective
    if model_param_eh["optim_focus"] == 0:
        model.addConstr(obj == operational_costs)
    elif model_param_eh["optim_focus"] == 1:
        model.addConstr(obj == co2_total)


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

    results["P_dem_total"] = []
    results["P_inj_total"] = []
    results["P_dem_gcp"] = []
    results["P_inj_gcp"] = []

    results["Cost_total"] = operational_costs.X
    results["Emission_total"] = co2_total.X

    # add results of the buildings
    for n in range(nb):
        results[n] = {}
        results[n]["res_load"] = []
        results[n]["res_inj"] = []

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

    return results
