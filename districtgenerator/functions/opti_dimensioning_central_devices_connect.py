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

import gurobipy as gp
import numpy as np
import time
import os
import csv
#from optim_app.help_functions import create_excel_file

def run_optim_connect(dataCon, devsCon, paramCon, demCon, result_dictCon):

    # Load data for one district for test reasons
    # TODO: Change for several districts
    devs=devsCon[list(devsCon.keys())[0]]
    dem=demCon[list(demCon.keys())[0]]

    
     #%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    # Cluster days and time horizon

    # Load data for one district for test reasons
    data=dataCon[0]
    param=paramCon[list(paramCon.keys())[0]] 
    # Load model parameters
    start_time = time.time()

    clusters = range(data.time["clusterNumber"])
    # calculate cluster time horizon
    clusterHorizon = int((data.time["clusterLength"] / data.time["timeResolution"]))
    time_steps = range(clusterHorizon)
    dt = data.time["timeResolution"] / data.time["dataResolution"]
    year = range(52)

    # Get sigma function that assigns each time period (day or week) of the year to a design period
    sigma = param["sigma"]

    #%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    # Initialize all all_devs to store all_devs for each district 
    all_devsCon = {}

    for district in dataCon:
        # Get the scenario_name of the district
        scenario_name = district.scenario_name
        # Call setup_devices and store the results
        all_devsCon[scenario_name] = setup_devices()

    # Print scenario_name for test reasons
    # TODO: Change for several districts
    print(f"Scenario name for optimization: {dataCon[0].scenario_name}")

    #%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    # Set up model and create variables

    # Create a new model
    model = gp.Model("Energy_hub_model")

    # Create variables for each district and store them in a dictionary
    # Works only for one district so far
    # TODO: Change for several districts
    variablesCon = {}
    for district in dataCon:
        # Get the scenario_name of the district
        scenario_name = district.scenario_name
        # Retrieve the corresponding all_devs data from all_devsCon
        if scenario_name in all_devsCon:
            all_devs = all_devsCon[scenario_name]
            # Call add_variables to add variables to the model
            variables={}
            variables = add_variables_per_district(district, model, all_devs, clusters, time_steps, year)
            variablesCon[scenario_name] = variables

    # Print cap variable for test reasons
    print(f"Cap of variablesCon are: {variablesCon[dataCon[0].scenario_name]["cap"]}")


    #%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    # Objective functions
    obj = {}
    obj["tac"] = model.addVar(vtype="C", lb=-gp.GRB.INFINITY, name="total_annualized_costs")
    obj["co2"] = model.addVar(vtype="C", lb=-gp.GRB.INFINITY, name="total_CO2")

    #%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    # Assign objective function
    model.update()
    model.setObjective((1-param["optim_focus"]) * obj["tac"]
                        + param["optim_focus"]  * obj["co2"], gp.GRB.MINIMIZE)


    #%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    # Add constraints for each district
    for district in dataCon:
        # Get the scenario_name of the district
        scenario_name = district.scenario_name
        # Retrieve the corresponding variables for all districts
        all_devs = all_devsCon[scenario_name]
        devs = devsCon[scenario_name]

        cap = variablesCon[scenario_name]["cap"]

        heat = variablesCon[scenario_name]["heat"]
        power = variablesCon[scenario_name]["power"]
        cool = variablesCon[scenario_name]["cool"]
        gas = variablesCon[scenario_name]["gas"]
        area = variablesCon[scenario_name]["area"]
        biom = variablesCon[scenario_name]["biom"]
        waste = variablesCon[scenario_name]["waste"]
        hydrogen = variablesCon[scenario_name]["hydrogen"]
        ch = variablesCon[scenario_name]["ch"]
        soc = variablesCon[scenario_name]["soc"]
        dem = demCon[scenario_name]
        param = paramCon[scenario_name]
        grid_limit_el = variablesCon[scenario_name]["grid_limit_el"]
        grid_limit_gas = variablesCon[scenario_name]["grid_limit_gas"]
        from_gas_grid_total = variablesCon[scenario_name]["from_gas_grid_total"]
        to_gas_grid_total = variablesCon[scenario_name]["to_gas_grid_total"]
        from_el_grid_total = variablesCon[scenario_name]["from_el_grid_total"]
        to_el_grid_total = variablesCon[scenario_name]["to_el_grid_total"]
        biom_import_total = variablesCon[scenario_name]["biom_import_total"]
        waste_import_total = variablesCon[scenario_name]["waste_import_total"]
        hydrogen_import_total = variablesCon[scenario_name]["hydrogen_import_total"]
        supply_costs_el = variablesCon[scenario_name]["supply_costs_el"]
        cap_costs_el = variablesCon[scenario_name]["cap_costs_el"]
        rev_feed_in_el = variablesCon[scenario_name]["rev_feed_in_el"]
        supply_costs_gas = variablesCon[scenario_name]["supply_costs_gas"]
        cap_costs_gas = variablesCon[scenario_name]["cap_costs_gas"]
        rev_feed_in_gas = variablesCon[scenario_name]["rev_feed_in_gas"]
        supply_costs_biom = variablesCon[scenario_name]["supply_costs_biom"]
        supply_costs_waste = variablesCon[scenario_name]["supply_costs_waste"]
        supply_costs_hydrogen = variablesCon[scenario_name]["supply_costs_hydrogen"]
        inv = variablesCon[scenario_name]["inv"]
        c_inv = variablesCon[scenario_name]["c_inv"]
        c_om = variablesCon[scenario_name]["c_om"]
        c_total = variablesCon[scenario_name]["c_total"]

        # Call add_constraints to add constraints to the model
        add_constraints_per_district(
            model, all_devs, devs, cap, clusters, time_steps,
            heat, power, cool, gas, area, biom, waste, hydrogen, ch, soc,
            dem, param, dt, year, sigma,grid_limit_el, grid_limit_gas,
            from_gas_grid_total, to_gas_grid_total,from_el_grid_total, to_el_grid_total,
            biom_import_total, waste_import_total, hydrogen_import_total, supply_costs_el,
            cap_costs_el, rev_feed_in_el, supply_costs_gas, cap_costs_gas,rev_feed_in_gas, 
            supply_costs_biom, supply_costs_waste, supply_costs_hydrogen, inv, c_inv, c_om, c_total
            )
        
        # Print cap variable for test reasons
        print(f"Cap of variablesCon afer add_constr are: {variablesCon[dataCon[0].scenario_name]["cap"]}")

    #%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    #%% DIFINE VARIBALES FOR OBJECTIVE FUNCTIONS
    #TODO: Change for several districts
    all_devs = all_devsCon[dataCon[0].scenario_name]
    tac_sum_total = 0
    co2_sum_total = 0

    for district in dataCon:
        # Get the scenario_name of the district
        scenario_name = district.scenario_name
        # Retrieve the corresponding variables for all districts
        c_total = variablesCon[scenario_name]["c_total"]
        all_devs = all_devsCon[scenario_name]
        data = district
        supply_costs_gas = variablesCon[scenario_name]["supply_costs_gas"]
        cap_costs_gas = variablesCon[scenario_name]["cap_costs_gas"]
        supply_costs_el = variablesCon[scenario_name]["supply_costs_el"]
        cap_costs_el = variablesCon[scenario_name]["cap_costs_el"]
        rev_feed_in_el = variablesCon[scenario_name]["rev_feed_in_el"]
        rev_feed_in_gas = variablesCon[scenario_name]["rev_feed_in_gas"]
        supply_costs_biom = variablesCon[scenario_name]["supply_costs_biom"]
        supply_costs_waste = variablesCon[scenario_name]["supply_costs_waste"]
        supply_costs_hydrogen = variablesCon[scenario_name]["supply_costs_hydrogen"]
        from_gas_grid_total = variablesCon[scenario_name]["from_gas_grid_total"]
        param = paramCon[scenario_name]
        biom_import_total = variablesCon[scenario_name]["biom_import_total"]
        waste_import_total = variablesCon[scenario_name]["waste_import_total"]
        from_el_grid_total = variablesCon[scenario_name]["from_el_grid_total"]
        hydrogen_import_total = variablesCon[scenario_name]["hydrogen_import_total"]
        to_el_grid_total = variablesCon[scenario_name]["to_el_grid_total"]
        to_gas_grid_total = variablesCon[scenario_name]["to_gas_grid_total"]
        # Total annualized costs per district

        tac_sum_distr = (
            sum(c_total[dev] for dev in all_devs) + data.heat_grid_data["ann_costs"] + data.heat_grid_data["om_costs"] # annualized investments and O&M
            + supply_costs_gas + cap_costs_gas # gas costs
            + supply_costs_el + cap_costs_el # electricity costs
            - rev_feed_in_el - rev_feed_in_gas # revenues
            + supply_costs_biom # biomass
            + supply_costs_waste # waste
            + supply_costs_hydrogen
            + (
                from_gas_grid_total * param["co2_gas"] 
                + biom_import_total * param["co2_biom"] 
                + waste_import_total * param["co2_waste"]) * param["co2_tax"] # CO2 tax
        )  
        # Sum up total annualized costs for all districts
        tac_sum_total += tac_sum_distr

        # Annual CO2 emissions: Implicit emissions by power supply from national grid is penalized, feed-in is ignored
        co2_sum_distr = (
            from_el_grid_total * param["co2_el_grid"]
            + from_gas_grid_total * param["co2_gas"]
            + biom_import_total * param["co2_biom"]
            + waste_import_total * param["co2_waste"]
            + hydrogen_import_total * param["co2_hydrogen"]
            - to_el_grid_total * param["co2_el_feed_in"]
            - to_gas_grid_total * param["co2_gas_feed_in"])
        
        # Sum up total CO2 emissions for all districts
        co2_sum_total += co2_sum_distr

    # Total annualized costs for all districts as contraint to obj variable
    model.addConstr(obj["tac"] == tac_sum_total)
    # Total CO2 emissions for all districts as constraint to obj variable
    model.addConstr(obj["co2"] == co2_sum_total)


    # # Total annualized costs for one district: Old code
    # model.addConstr(obj["tac"] == sum(c_total[dev] for dev in all_devs) + data.heat_grid_data["ann_costs"] + data.heat_grid_data["om_costs"] # annualized investments and O&M
    #                             + supply_costs_gas + cap_costs_gas # gas costs
    #                             + supply_costs_el + cap_costs_el # electricity costs
    #                             - rev_feed_in_el - rev_feed_in_gas # revenues
    #                             + supply_costs_biom # biomass
    #                             + supply_costs_waste # waste
    #                             + supply_costs_hydrogen
    #                             + (from_gas_grid_total * param["co2_gas"] + biom_import_total * param["co2_biom"] + waste_import_total * param["co2_waste"]) * param["co2_tax"]) # CO2 tax


    # # Annual CO2 emissions: Implicit emissions by power supply from national grid is penalized, feed-in is ignored
    # model.addConstr(obj["co2"] == from_el_grid_total * param["co2_el_grid"]
    #                                   + from_gas_grid_total * param["co2_gas"]
    #                                   + biom_import_total * param["co2_biom"]
    #                                   + waste_import_total * param["co2_waste"]
    #                                   + hydrogen_import_total * param["co2_hydrogen"]
    #                                   - to_el_grid_total * param["co2_el_feed_in"]
    #                                   - to_gas_grid_total * param["co2_gas_feed_in"])
    
    #%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    # Set model parameters and execute calculation

    print("Precalculation and model set up done in %f seconds."  % (time.time() - start_time))

    # Set solver parameters
    model.Params.MIPGap   = 0.02  # ---,   gap for branch-and-bound algorithm
    # model.Params.method = 2     # ---,   -1: default, 0: primal simplex, 1: dual simplex, 2: barrier, etc.

    # Execute calculation
    start_time = time.time()
    model.optimize()
    print("Optimization done. (%f seconds.)" % (time.time() - start_time))


    #%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    # Check and save results

    #TODO: Change for several districts!!!!
    result_dict=result_dictCon[list(result_dictCon.keys())[0]]

    # Check if optimal solution was found
    if model.Status in (3, 4) or model.SolCount == 0:  # "INFEASIBLE" or "INF_OR_UNBD"

        print("Optimization: No feasible solution found.")
        try:
            print("Try to calculate IIS.")
            model.computeIIS()
            model.write("model.ilp")
            print("IIS was calculated and saved as model.ilp")

        except:
            print("Could not calculate IIS.")
        return {}

    else:
        # Save results
        result_dir = "results"
        if not os.path.exists(result_dir):
            os.makedirs(result_dir)

        # Save results after optimization
        model.write(os.path.join(result_dir, "model.sol"))
        model.write(os.path.join(result_dir,  "model.lp"))

        # Process results for the whole network and store them in result_dictCon
        result_dictCon["network"] = {}
        result_dictCon["network"]["tac"] = int(obj["tac"].X)      # EUR/a 
        result_dictCon["network"]["co2"] = int(obj["co2"].X/1000) # t/a

        # Process results for each district and store them in result_dictCon
        for district in dataCon:
            # Get the scenario_name of the district
            scenario_name = district.scenario_name
            # Retrieve the corresponding variables for all districts
            result_dict = result_dictCon[scenario_name]
            inv = variablesCon[scenario_name]["inv"]
            c_inv = variablesCon[scenario_name]["c_inv"]
            c_om = variablesCon[scenario_name]["c_om"]
            all_devs = all_devsCon[scenario_name]
            devs = devsCon[scenario_name]
            cap = variablesCon[scenario_name]["cap"]
            power = variablesCon[scenario_name]["power"]
            gas = variablesCon[scenario_name]["gas"]
            biom = variablesCon[scenario_name]["biom"]
            waste = variablesCon[scenario_name]["waste"]
            from_el_grid_total = variablesCon[scenario_name]["from_el_grid_total"]
            to_el_grid_total = variablesCon[scenario_name]["to_el_grid_total"]
            from_gas_grid_total = variablesCon[scenario_name]["from_gas_grid_total"]
            to_gas_grid_total = variablesCon[scenario_name]["to_gas_grid_total"]
            biom_import_total = variablesCon[scenario_name]["biom_import_total"]
            waste_import_total = variablesCon[scenario_name]["waste_import_total"]
            hydrogen_import_total = variablesCon[scenario_name]["hydrogen_import_total"]
            data = district
            param = paramCon[scenario_name]
            hydrogen = variablesCon[scenario_name]["hydrogen"]
            supply_costs_el = variablesCon[scenario_name]["supply_costs_el"]
            cap_costs_el = variablesCon[scenario_name]["cap_costs_el"]
            rev_feed_in_el = variablesCon[scenario_name]["rev_feed_in_el"]
            supply_costs_gas = variablesCon[scenario_name]["supply_costs_gas"]
            cap_costs_gas = variablesCon[scenario_name]["cap_costs_gas"]
            rev_feed_in_gas = variablesCon[scenario_name]["rev_feed_in_gas"]
            supply_costs_biom = variablesCon[scenario_name]["supply_costs_biom"]
            supply_costs_waste = variablesCon[scenario_name]["supply_costs_waste"]
            supply_costs_hydrogen = variablesCon[scenario_name]["supply_costs_hydrogen"]
            area = variablesCon[scenario_name]["area"]
            heat = variablesCon[scenario_name]["heat"]
            cool = variablesCon[scenario_name]["cool"]
            ch = variablesCon[scenario_name]["ch"]

            result_dict = process_results_per_district(result_dict, inv, c_inv, c_om, all_devs, devs, cap, power, gas, 
                            biom, waste, from_el_grid_total, to_el_grid_total, from_gas_grid_total, 
                            to_gas_grid_total, biom_import_total, waste_import_total, hydrogen_import_total, obj, 
                            data, param, clusters, time_steps, hydrogen, supply_costs_el,cap_costs_el,rev_feed_in_el,
                            supply_costs_gas,cap_costs_gas,rev_feed_in_gas,supply_costs_biom,supply_costs_waste,
                            supply_costs_hydrogen, area, heat, dt, cool, ch)
            
            save_results_csv(result_dict, scenario_name, result_dir, all_devs)
            
            result_dictCon[scenario_name] = result_dict
        
        return result_dictCon

def setup_devices():
   
    # Create set of devices
    all_devs = ["PV", "WT", "STC", "WAT",
                "HP", "EB", "CC", "AC",
                "CHP", "BOI", "GHP",
                "BCHP", "BBOI", "WCHP", "WBOI",
                "ELYZ", "FC", "H2S", "SAB",
                "TES", "CTES", "BAT", "GS",
                ]
    return all_devs

def add_variables_per_district(district, model, all_devs, clusters, time_steps, year):
    # Device's capacity (i.e. rated power)
    cap = {}
    for device in all_devs:
        cap[device] = model.addVar(vtype="C", name="nominal_capacity_" + str(device) + "_" + str(district.scenario_name))
    

    # Roof area used for PV and solar thermal collector installation
    area = {}
    for device in ["PV", "STC"]:
        area[device] = model.addVar(vtype = "C", name="roof_area_" + str(device) + "_" + str(district.scenario_name))

    # Gas flow to/from devices
    gas = {}
    for device in ["CHP", "BOI", "GHP", "SAB", "from_grid", "to_grid"]:
        gas[device] = {}
        for d in clusters:
            gas[device][d] = {}
            for t in time_steps:
                gas[device][d][t] = model.addVar(vtype="C", name="gas_" + device + "_d" + str(d) + "_t" + str(t)+ "_" + str(district.scenario_name))

    # Electric power to/from devices
    power = {}
    for device in ["PV", "WT", "WAT", "HP", "EB", "CC", "CHP", "BCHP", "WCHP", "ELYZ", "FC", "from_grid", "to_grid"]:
        power[device] = {}
        for d in clusters:
            power[device][d] = {}
            for t in time_steps:
                power[device][d][t] = model.addVar(vtype="C", name="power_" + device + "_d" + str(d) + "_t" + str(t)+ "_" + str(district.scenario_name))

    # Heat to/from devices
    heat = {}
    for device in ["STC", "HP", "EB", "AC", "CHP", "BOI", "GHP", "BCHP", "BBOI", "WCHP", "WBOI", "FC"]:
        heat[device] = {}
        for d in clusters:
            heat[device][d] = {}
            for t in time_steps:
                heat[device][d][t] = model.addVar(vtype="C", name="heat_" + device + "_d" + str(d) + "_t" + str(t) + "_" + str(district.scenario_name))

    # Cooling power to/from devices
    cool = {}
    for device in ["CC", "AC"]:
        cool[device] = {}
        for d in clusters:
            cool[device][d] = {}
            for t in time_steps:
                cool[device][d][t] = model.addVar(vtype="C", name="cool_" + device + "_d" + str(d) + "_t" + str(t)+ "_" + str(district.scenario_name))

    # Hydrogen to/from devices
    hydrogen = {}
    for device in ["ELYZ", "FC", "SAB", "import"]:
        hydrogen[device] = {}
        for d in clusters:
            hydrogen[device][d] = {}
            for t in time_steps:
                hydrogen[device][d][t] = model.addVar(vtype="C", name="hydrogen_" + device + "_d" + str(d) + "_t" + str(t)+ "_" + str(district.scenario_name))

    # Biomass to devices
    biom = {}
    for device in ["BCHP", "BBOI", "import"]:
        biom[device] = {}
        for d in clusters:
            biom[device][d] = {}
            for t in time_steps:
                biom[device][d][t] = model.addVar(vtype="C", name="biom_" + device + "_d" + str(d) + "_t" + str(t)+ "_" + str(district.scenario_name))

    # Waste to devices
    waste = {}
    for device in ["WCHP", "WBOI", "import"]:
        waste[device] = {}
        for d in clusters:
            waste[device][d] = {}
            for t in time_steps:
                waste[device][d][t] = model.addVar(vtype="C", name="waste_" + device + "_d" + str(d) + "_t" + str(t)+ "_" + str(district.scenario_name))

    # Storage variables
    ch = {}  # Energy flow to charge storage device
    soc = {} # State of charge
    for device in ["TES", "CTES", "BAT", "H2S", "GS"]:
        ch[device] = {}
        soc[device] = {}
        for d in clusters:
            ch[device][d] = {}
            for t in time_steps:
                # For charge variable: ch is positive if storage is charged, and negative if storage is discharged
                ch[device][d][t] = model.addVar(vtype="C", lb=-gp.GRB.INFINITY, name="ch_" + device + "_d" + str(d) + "_t" + str(t)+ "_" + str(district.scenario_name))
        # The SoC is considered for the whole year
        for time_period in year:
            soc[device][time_period] = {}
            for t in time_steps:
                soc[device][time_period][t] = model.addVar(vtype="C", name="soc_" + device + "_d" + str(time_period) + "_t" + str(t)+ "_" + str(district.scenario_name))

    # Variables for annual device costs
    inv = {}
    c_inv = {}
    c_om = {}
    c_total = {}
    for device in all_devs:
        inv[device] = model.addVar(vtype = "C", name="investment_costs_" + device+ "_" + str(district.scenario_name))
    for device in all_devs:
        c_inv[device] = model.addVar(vtype = "C", name="annual_investment_costs_" + device+ "_" + str(district.scenario_name))
    for device in all_devs:
        c_om[device] = model.addVar(vtype = "C", name="om_costs_" + device+ "_" + str(district.scenario_name))
    for device in all_devs:
        c_total[device] = model.addVar(vtype = "C", name="total_annual_costs_" + device+ "_" + str(district.scenario_name))

    # Capacity of grid connections (gas and electricity)
    grid_limit_el  = model.addVar(vtype = "C", name="grid_limit_el"+ "_" + str(district.scenario_name))
    grid_limit_gas = model.addVar(vtype = "C", name="grid_limit_gas"+ "_" + str(district.scenario_name))

    # Total energy amounts taken from grid and fed into grid
    from_el_grid_total = model.addVar(vtype = "C", name="from_el_grid_total"+ "_" + str(district.scenario_name))
    to_el_grid_total   = model.addVar(vtype = "C", name="to_el_grid_total"+ "_" + str(district.scenario_name))

    from_gas_grid_total = model.addVar(vtype = "C", name="from_gas_grid_total"+ "_" + str(district.scenario_name))
    to_gas_grid_total   = model.addVar(vtype = "C", name="to_gas_grid_total"+ "_" + str(district.scenario_name))

    biom_import_total     = model.addVar(vtype = "C", name="biom_import_total"+ "_" + str(district.scenario_name))
    waste_import_total    = model.addVar(vtype = "C", name="waste_import_total"+ "_" + str(district.scenario_name))
    hydrogen_import_total = model.addVar(vtype = "C", name="hydrogen_import_total"+ "_" + str(district.scenario_name))

    # Total revenue from feed-in
    rev_feed_in_gas = model.addVar(vtype="C", name="rev_feed_in_gas"+ "_" + str(district.scenario_name))
    rev_feed_in_el  = model.addVar(vtype="C", name="rev_feed_in_el"+ "_" + str(district.scenario_name))

    # Electricity/gas/biomass costs
    supply_costs_el       = model.addVar(vtype = "C", name="supply_costs_el"+ "_" + str(district.scenario_name))
    cap_costs_el          = model.addVar(vtype = "C", name="cap_costs_el"+ "_" + str(district.scenario_name))
    supply_costs_gas      = model.addVar(vtype = "C", name="supply_costs_gas"+ "_" + str(district.scenario_name))
    cap_costs_gas         = model.addVar(vtype = "C", name="cap_costs_gas"+ "_" + str(district.scenario_name))
    supply_costs_biom     = model.addVar(vtype = "C", name="supply_costs_biomass"+ "_" + str(district.scenario_name))
    supply_costs_waste    = model.addVar(vtype = "C", lb=-gp.GRB.INFINITY, name="supply_costs_waste"+ "_" + str(district.scenario_name))
    supply_costs_hydrogen = model.addVar(vtype = "C", name="supply_costs_hydrogen"+ "_" + str(district.scenario_name))

    # Return all variables as a dictionary
    variables = {
        "cap": cap,
        "area": area,
        "gas": gas,
        "power": power,
        "heat": heat,
        "cool": cool,
        "hydrogen": hydrogen,
        "biom": biom,
        "waste": waste,
        "ch": ch,
        "soc": soc,
        "grid_limit_el": grid_limit_el,
        "grid_limit_gas": grid_limit_gas,
        "from_el_grid_total": from_el_grid_total,
        "to_el_grid_total": to_el_grid_total,
        "from_gas_grid_total": from_gas_grid_total,
        "to_gas_grid_total": to_gas_grid_total,
        "biom_import_total": biom_import_total,
        "waste_import_total": waste_import_total,
        "hydrogen_import_total": hydrogen_import_total,
        "rev_feed_in_gas": rev_feed_in_gas,
        "rev_feed_in_el": rev_feed_in_el,
        "supply_costs_el": supply_costs_el,
        "cap_costs_el": cap_costs_el,
        "supply_costs_gas": supply_costs_gas,
        "cap_costs_gas": cap_costs_gas,
        "supply_costs_biom": supply_costs_biom,
        "supply_costs_waste": supply_costs_waste,
        "supply_costs_hydrogen": supply_costs_hydrogen,
        "inv": inv,
        "c_inv": c_inv,
        "c_om": c_om,
        "c_total": c_total,
        
    }

    return variables

def add_constraints_per_district(
        model, all_devs, devs, cap, clusters, time_steps, 
        heat, power, cool, gas, area, biom, waste, hydrogen, 
        ch, soc, dem, param, dt, year, sigma, grid_limit_el, grid_limit_gas,
        from_gas_grid_total, to_gas_grid_total,from_el_grid_total, to_el_grid_total, 
        biom_import_total, waste_import_total, hydrogen_import_total, supply_costs_el,
        cap_costs_el, rev_feed_in_el, supply_costs_gas, cap_costs_gas,rev_feed_in_gas, 
        supply_costs_biom, supply_costs_waste, supply_costs_hydrogen, inv, c_inv, c_om, c_total):
       # Add constraints

    #%% Constraints defined by user in GUI
    #

    for device in all_devs:
        if devs[device]["feasible"] == False:
            model.addConstr(cap[device] == 0)


    #%% CONTINUOUS SIZING OF DEVICES: minimum capacity <= capacity <= maximum capacity

    for device in ["WT", "WAT", "HP", "EB", "CC", "AC", "CHP", "BOI", "GHP", "BCHP", "BBOI", "WCHP", "WBOI", "ELYZ", "FC", "H2S", "SAB", "TES", "CTES", "BAT", "GS"]:  # PV/STC is not listed due to min_area/max_area.
        if devs[device]["feasible"]:
            model.addConstr(cap[device] >= devs[device]["min_cap"])
            model.addConstr(cap[device] <= devs[device]["max_cap"])

    for d in clusters:
        for t in time_steps:
            for device in ["STC", "EB", "HP", "BOI", "GHP", "BBOI", "WBOI"]:
                model.addConstr(heat[device][d][t] <= cap[device])

            for device in ["PV", "WT", "WAT", "CHP", "BCHP", "WCHP", "ELYZ", "FC"]:
                model.addConstr(power[device][d][t] <= cap[device])

            for device in ["CC", "AC"]:
                model.addConstr(cool[device][d][t] <= cap[device])

            for device in ["SAB"]:
                model.addConstr(gas[device][d][t] <= cap[device])

            # Limitation of power from and to grid
            for device in ["from_grid", "to_grid"]:
                model.addConstr(power[device][d][t] <= grid_limit_el)
                model.addConstr(gas[device][d][t]   <= grid_limit_gas)

            # PV and STC: minimum area < used roof area <= maximum area
            for device in ["PV", "STC"]:
                if devs[device]["feasible"]:
                    model.addConstr(area[device] >= devs[device]["min_area"])
                    model.addConstr(area[device] <= devs[device]["max_area"])

            # Correlation between PV area and peak power; cap["PV"] is only needed for calculating investment costs
            model.addConstr(cap["PV"] == area["PV"] * devs["PV"]["G_stc"] * devs["PV"]["eta"])

            # Correlation between STC area and peak power; cap["STC"] is only needed for calculating investment costs
            model.addConstr(cap["STC"] == area["STC"] * devs["STC"]["G_stc"] * devs["STC"]["eta"])


    # state of charge < storage capacity
    for device in ["TES", "CTES", "BAT", "H2S", "GS"]:
        for time_period in year:
            for t in time_steps:
                model.addConstr(soc[device][time_period][t] <= cap[device])

    #%% INPUT / OUTPUT CONSTRAINTS

    for d in clusters:
        for t in time_steps:

            # Photovoltaics
            # Correlation between area and peek power is used
            model.addConstr(power["PV"][d][t] <= devs["PV"]["norm_power_clustered"][d][t]/1000 * area["PV"])

            # Wind turbine
            model.addConstr(power["WT"][d][t] <= devs["WT"]["norm_power_clustered"][d][t] * cap["WT"])

            # Hydropower
            model.addConstr(power["WAT"][d][t] <= devs["WAT"]["potential"])

            # Solar thermal collector
            model.addConstr(heat["STC"][d][t] <= devs["STC"]["norm_power_clustered"][d][t]/1000 * area["STC"])

            # Electric heat pump
            model.addConstr(heat["HP"][d][t] == power["HP"][d][t] * devs["HP"]["COP"][d][t])

            # Electric boiler
            model.addConstr(heat["EB"][d][t] == power["EB"][d][t] * devs["EB"]["eta_th"])

            # Compression chiller
            model.addConstr(cool["CC"][d][t] == power["CC"][d][t] * devs["CC"]["COP"][d][t])

            # Absorption chiller
            model.addConstr(cool["AC"][d][t] == heat["AC"][d][t] * devs["AC"]["eta_th"])

            # Gas CHP
            model.addConstr(power["CHP"][d][t] == gas["CHP"][d][t] * devs["CHP"]["eta_el"])
            model.addConstr(heat["CHP"][d][t] == gas["CHP"][d][t] * devs["CHP"]["eta_th"])

            # Gas boiler
            model.addConstr(heat["BOI"][d][t] == gas["BOI"][d][t] * devs["BOI"]["eta_th"])

            # Gas heat pump
            model.addConstr(heat["GHP"][d][t] == gas["GHP"][d][t] * devs["GHP"]["COP"])

            # Biomass CHP
            model.addConstr(power["BCHP"][d][t] == biom["BCHP"][d][t] * devs["BCHP"]["eta_el"])
            model.addConstr(heat["BCHP"][d][t] == biom["BCHP"][d][t] * devs["BCHP"]["eta_th"])

            # Biomass boiler
            model.addConstr(heat["BBOI"][d][t] == biom["BBOI"][d][t] * devs["BBOI"]["eta_th"])

            # Waste CHP
            model.addConstr(power["WCHP"][d][t] == waste["WCHP"][d][t] * devs["WCHP"]["eta_el"])
            model.addConstr(heat["WCHP"][d][t] == waste["WCHP"][d][t] * devs["WCHP"]["eta_th"])

            # Waste boiler
            model.addConstr(heat["WBOI"][d][t] == waste["WBOI"][d][t] * devs["WBOI"]["eta_th"])

            # Electrolyzer
            model.addConstr(hydrogen["ELYZ"][d][t] == power["ELYZ"][d][t] * devs["ELYZ"]["eta_el"])

            # Fuel cell
            model.addConstr(power["FC"][d][t] == hydrogen["FC"][d][t] * devs["FC"]["eta_el"])
            if devs["FC"]["enable_heat_diss"]:   # Heat can also be dissipated
                model.addConstr(heat["FC"][d][t] <= hydrogen["FC"][d][t] * devs["FC"]["eta_th"])
            else:   # Heat must be used
                model.addConstr(heat["FC"][d][t] == hydrogen["FC"][d][t] * devs["FC"]["eta_th"])

            # Sabatier reactor
            model.addConstr(gas["SAB"][d][t] == hydrogen["SAB"][d][t] * devs["SAB"]["eta"])

    #%% GLOBAL ENERGY BALANCES

    for d in clusters:
        for t in time_steps:

            # Heating balance
            model.addConstr(heat["STC"][d][t] + heat["HP"][d][t] + heat["EB"][d][t] + heat["CHP"][d][t] + heat["BOI"][d][t] + heat["GHP"][d][t] + heat["BCHP"][d][t] + heat["BBOI"][d][t]+ heat["WCHP"][d][t] + heat["WBOI"][d][t] + heat["FC"][d][t] == dem["heat"][d][t] + heat["AC"][d][t] + ch["TES"][d][t])

            # Electricity balance
            model.addConstr(power["PV"][d][t] + power["WT"][d][t] + power["WAT"][d][t] + power["CHP"][d][t] + power["BCHP"][d][t] + power["WCHP"][d][t] + power["FC"][d][t] + power["from_grid"][d][t] == dem["power"][d][t] + power["HP"][d][t] + power["EB"][d][t] + power["CC"][d][t] + power["ELYZ"][d][t] + ch["BAT"][d][t] + power["to_grid"][d][t])

            # Cooling balance
            model.addConstr(cool["AC"][d][t] + cool["CC"][d][t] == dem["cool"][d][t] + ch["CTES"][d][t])

            # Gas balance
            model.addConstr(gas["from_grid"][d][t] + gas["SAB"][d][t] == gas["CHP"][d][t] + gas["BOI"][d][t] + gas["GHP"][d][t] + ch["GS"][d][t] + gas["to_grid"][d][t])

            # Hydrogen balance
            model.addConstr(hydrogen["ELYZ"][d][t] + hydrogen["import"][d][t] == hydrogen["FC"][d][t] + hydrogen["SAB"][d][t] + ch["H2S"][d][t])

            # Biomass balance
            model.addConstr(biom["import"][d][t] == biom["BCHP"][d][t] + biom["BBOI"][d][t])

            # Waste balance
            model.addConstr(waste["import"][d][t] == waste["WCHP"][d][t] + waste["WBOI"][d][t])


    #%% MEET PEAK DEMANDS OF UNCLUSTERED DEMANDS

    if param["peak_dem_met_conv"] == False:  # only the secured capacities, so without the renewable technologies

        # Heating
        model.addConstr(cap["HP"] + cap["EB"]
                      + cap["CHP"] / devs["CHP"]["eta_el"] * devs["CHP"]["eta_th"]
                      + cap["BOI"]
                      + cap["GHP"]
                      + cap["BCHP"] / devs["BCHP"]["eta_el"] * devs["BCHP"]["eta_th"]
                      + cap["BBOI"]
                      + cap["WCHP"] / devs["WCHP"]["eta_el"] * devs["WCHP"]["eta_th"]
                      + cap["WBOI"]
                      + cap["FC"] / devs["FC"]["eta_el"] * devs["FC"]["eta_th"]
                      >= param["peak_heat"])

        # Cooling
        model.addConstr(cap["CC"] + cap["AC"] >= param["peak_cool"])

        # Power
        model.addConstr(cap["CHP"] + cap["BCHP"] + cap["WCHP"] + cap["FC"] + grid_limit_el >= param["peak_power"])

        # Hydrogen
        if (param["enable_supply_hydrogen"] == False) and devs["ELYZ"]["feasible"]:
            model.addConstr(cap["ELYZ"] >= param["peak_hydrogen"])


    else:  # With STC, PV, WIND, HYDROPOWER (renewable technologies)

        # Heating
        model.addConstr(cap["STC"] + cap["HP"] + cap["EB"]
                      + cap["CHP"] / devs["CHP"]["eta_el"] * devs["CHP"]["eta_th"]
                      + cap["BOI"]
                      + cap["GHP"]
                      + cap["BCHP"] / devs["BCHP"]["eta_el"] * devs["BCHP"]["eta_th"]
                      + cap["BBOI"]
                      + cap["WCHP"] / devs["WCHP"]["eta_el"] * devs["WCHP"]["eta_th"]
                      + cap["WBOI"]
                      + cap["FC"] / devs["FC"]["eta_el"] * devs["FC"]["eta_th"]
                      >= param["peak_heat"])

        # Cooling
        model.addConstr(cap["CC"] + cap["AC"] >= param["peak_cool"])

        # Power
        model.addConstr(cap["PV"] + cap["WT"] + cap["WAT"] + cap["CHP"] + cap["BCHP"] + cap["WCHP"] + cap["FC"] + grid_limit_el >= param["peak_power"])

        # Hydrogen
        if (param["enable_supply_hydrogen"] == False) and devs["ELYZ"]["feasible"]:
            model.addConstr(cap["ELYZ"] >= param["peak_hydrogen"])


    #%% STORAGE DEVICES

    for device in ["TES", "CTES", "BAT", "H2S", "GS"]:
        for time_period in year:
            for t in np.arange(1, len(time_steps)):

                # Energy balance: soc(t) = soc(t-1) + charge - discharge
                model.addConstr(soc[device][time_period][t] == soc[device][time_period][t-1] * (1-devs[device]["sto_loss"]) ** dt + ch[device][sigma[time_period]][t] * dt)

            # Transition between two consecutive time periods
            if time_period > 0:
                model.addConstr(soc[device][time_period][0] == soc[device][time_period-1][len(time_steps)-1] * (1-devs[device]["sto_loss"]) ** dt + ch[device][sigma[time_period]][0] * dt)

        # Cyclic year condition
        model.addConstr(soc[device][0][0] ==  soc[device][len(year)-1][len(time_steps)-1] * (1-devs[device]["sto_loss"]) ** dt + ch[device][sigma[0]][0] * dt)


    #%% SUM UP RESULTS

    ### Total energy import/feed-in ###
    # Total amount of gas taken from and to grid
    model.addConstr(from_gas_grid_total == dt * sum(sum(gas["from_grid"][d][t] for t in time_steps) * param["cluster_weights"][d] for d in clusters))
    model.addConstr(to_gas_grid_total   == dt * sum(sum(gas["to_grid"][d][t] for t in time_steps) * param["cluster_weights"][d] for d in clusters))

    # Total electric energy from and to grid
    model.addConstr(from_el_grid_total == dt * sum(sum(power["from_grid"][d][t] for t in time_steps) * param["cluster_weights"][d] for d in clusters))
    model.addConstr(to_el_grid_total   == dt * sum(sum(power["to_grid"][d][t] for t in time_steps) * param["cluster_weights"][d] for d in clusters))

    # Total amount of biomass imported
    model.addConstr(biom_import_total == dt * sum(sum(biom["import"][d][t] for t in time_steps) * param["cluster_weights"][d] for d in clusters))

    # Total amount of waste imported
    model.addConstr(waste_import_total == dt * sum(sum(waste["import"][d][t] for t in time_steps) * param["cluster_weights"][d] for d in clusters))

    # Total amount of hydrogen imported
    model.addConstr(hydrogen_import_total == dt * sum(sum(hydrogen["import"][d][t] for t in time_steps) * param["cluster_weights"][d] for d in clusters))


    ### Costs ###
    # Costs/revenues for electricity
    model.addConstr(supply_costs_el  == from_el_grid_total  * param["price_supply_el"])
    model.addConstr(cap_costs_el == (grid_limit_el * param["price_cap_el"] if param["enable_price_cap_el"] else 0))
    model.addConstr(rev_feed_in_el   == to_el_grid_total    * param["revenue_feed_in_el"])

    # Costs/revenues for natural gas
    model.addConstr(supply_costs_gas == from_gas_grid_total * param["price_supply_gas"])
    model.addConstr(cap_costs_gas    == grid_limit_gas      * param["price_cap_gas"])
    model.addConstr(rev_feed_in_gas  == to_gas_grid_total   * param["revenue_feed_in_gas"])

    # Costs for biomass, waste and hydrogen
    model.addConstr(supply_costs_biom     == biom_import_total     * param["price_biomass"])
    model.addConstr(supply_costs_waste    == waste_import_total    * param["price_waste"])
    model.addConstr(supply_costs_hydrogen == hydrogen_import_total * param["price_hydrogen"])


    ### Supply limitations ###
    # Forbid/allow feed-in (user input)
    if param["enable_feed_in_el"] != True:
        model.addConstr(to_el_grid_total == 0)
    if param["enable_feed_in_gas"] != True:
        model.addConstr(to_gas_grid_total == 0)

    # Limitation of electricity supply (user input)
    if param["enable_supply_el"] != True:
        model.addConstr(from_el_grid_total == 0)
    if param["enable_cap_limit_el"] == True:
        model.addConstr(grid_limit_el <= param["cap_limit_el"])
    if param["enable_supply_limit_el"] == True:
        model.addConstr(from_el_grid_total <= param["supply_limit_el"])

    # Limitation of gas supply (user input)
    if param["enable_supply_gas"] != True:
        model.addConstr(from_gas_grid_total == 0)
    if param["enable_cap_limit_gas"] == True:
        model.addConstr(grid_limit_gas <= param["cap_limit_gas"])
    if param["enable_supply_limit_gas"] == True:
        model.addConstr(from_gas_grid_total <= param["supply_limit_gas"])

    # Limitation of biomass supply (user input)
    if param["enable_supply_biomass"] != True:
        model.addConstr(biom_import_total == 0)
    if param["enable_supply_limit_biomass"] == True:
        model.addConstr(biom_import_total <= param["supply_limit_biomass"])

    # Limitation of waste supply (user input)
    if param["enable_supply_waste"] != True:
        model.addConstr(waste_import_total == 0)
    if param["enable_supply_limit_waste"] == True:
        model.addConstr(waste_import_total <= param["supply_limit_waste"])

    # Limitation of hydrogen supply (user input)
    if param["enable_supply_hydrogen"] != True:
        model.addConstr(hydrogen_import_total == 0)
    if param["enable_supply_limit_hydrogen"] == True:
        model.addConstr(hydrogen_import_total <= param["supply_limit_hydrogen"])


    # Total investment costs for the energy hub
    for device in all_devs:
        model.addConstr(inv[device] == devs[device]["inv_var"] * cap[device])

    # Annual investment costs for the energy hub
    for device in all_devs:
        model.addConstr(c_inv[device] == inv[device] * devs[device]["ann_factor"])

    # Operation and maintenance costs for the energy hub
    for device in all_devs:
        model.addConstr(c_om[device] == devs[device]["cost_om"] * inv[device])

    # Total annual costs for the energy hub
    for device in all_devs:
        model.addConstr(c_total[device] == c_inv[device] + c_om[device])


def process_results_per_district(result_dict, inv,c_inv,c_om, all_devs, devs, cap, power, gas, 
                           biom, waste, from_el_grid_total, to_el_grid_total, from_gas_grid_total, 
                           to_gas_grid_total, biom_import_total, waste_import_total, hydrogen_import_total, obj, 
                           data, param, clusters, time_steps, hydrogen,supply_costs_el,cap_costs_el,rev_feed_in_el,
                           supply_costs_gas,cap_costs_gas,rev_feed_in_gas,supply_costs_biom,supply_costs_waste,
                           supply_costs_hydrogen, area, heat, dt, cool, ch):
        
        ##### For further analysis
        for k in all_devs:
            result_dict[k] = {}

        result_dict["devs"] = devs

        # Moved to run_optim_connect()
        # result_dict["tac"] = int(obj["tac"].X)      # EUR/a 
        # result_dict["co2"] = int(obj["co2"].X/1000) # t/a

        for k in cap.keys():
            result_dict[k] = {"cap": round(cap[k].X, 1)}

        # Add 'from_grid' capacity if the option is enabled
        if param["enable_cap_limit_el"]:
            result_dict["from_grid"] = {"cap": param["cap_limit_el"]}
            result_dict["to_grid"] = {"cap": param["cap_limit_el"]}
        else:
            result_dict["from_grid"] = {"cap": float("inf")}
            result_dict["to_grid"] = {"cap": float("inf")}
            

        result_dict["total_inv_cost"]        = int(sum(inv[k].X for k in cap.keys()) + data.heat_grid_data["costs"])
        result_dict["total_ann_inv_cost"]    = int(sum(c_inv[k].X for k in cap.keys()) + data.heat_grid_data["ann_costs"])
        result_dict["total_om_cost"]         = int(sum(c_om[k].X  for k in cap.keys()) + data.heat_grid_data["om_costs"])

        result_dict["from_el_grid_total"]    = int(from_el_grid_total.X / 1000)    # MWh
        result_dict["to_el_grid_total"]      = int(to_el_grid_total.X / 1000)      # MWh
        result_dict["from_gas_grid_total"]   = int(from_gas_grid_total.X / 1000)   # MWh
        result_dict["to_gas_grid_total"]     = int(to_gas_grid_total.X / 1000)     # MWh
        result_dict["biom_import_total"]     = int(biom_import_total.X / 1000)     # MWh
        result_dict["waste_import_total"]    = int(waste_import_total.X / 1000)    # MWh
        result_dict["hydrogen_import_total"] = int(hydrogen_import_total.X / 1000) # MWh

        # CO2 emissions
        result_dict["co2_onsite_emissions"] = int((from_gas_grid_total.X * param["co2_gas"] + biom_import_total.X * param["co2_biom"] + waste_import_total.X * param["co2_waste"])/1000)
        #result_dict["co2_global_emissions"] = int(result_dict["co2"]/1000)  # Moved to run_optim_connect()
        result_dict["co2_credit_feedin"] = int((to_el_grid_total.X * param["co2_el_feed_in"] + to_gas_grid_total.X * param["co2_gas_feed_in"])/1000)
        result_dict["co2_tax_total"] = int(result_dict["co2_onsite_emissions"] * param["co2_tax"] * 1000)  # EUR, only gas, biomass and waste.

        # Calculate maximum grid flows (electricity and gas)
        for k in ["from_grid", "to_grid"]:
            result_dict["max_el_" + k] = 0
            for d in clusters:
                for t in time_steps:
                    if power[k][d][t].X > result_dict["max_el_" + k]:
                        result_dict["max_el_" + k] = power[k][d][t].X
            result_dict["max_el_" + k] = int(result_dict["max_el_" + k])

        for k in ["from_grid", "to_grid"]:
            result_dict["max_gas_" + k] = 0
            for d in clusters:
                for t in time_steps:
                    if gas[k][d][t].X > result_dict["max_gas_" + k]:
                        result_dict["max_gas_" + k] = gas[k][d][t].X
            result_dict["max_gas_" + k] = int(result_dict["max_gas_" + k])

        result_dict["max_biom"] = 0
        for d in clusters:
            for t in time_steps:
                if biom["import"][d][t].X > result_dict["max_biom"]:
                    result_dict["max_biom"] = biom["import"][d][t].X
        result_dict["max_biom"] = int(result_dict["max_biom"])

        result_dict["max_waste"] = 0
        for d in clusters:
            for t in time_steps:
                if waste["import"][d][t].X > result_dict["max_waste"]:
                    result_dict["max_waste"] = waste["import"][d][t].X
        result_dict["max_waste"] = int(result_dict["max_waste"])

        result_dict["max_hydrogen"] = 0
        for d in clusters:
            for t in time_steps:
                if hydrogen["import"][d][t].X > result_dict["max_hydrogen"]:
                    result_dict["max_hydrogen"] = hydrogen["import"][d][t].X
        result_dict["max_hydrogen"] = int(result_dict["max_hydrogen"])

        # Costs
        result_dict["supply_costs_el"] = int(supply_costs_el.X)
        result_dict["cap_costs_el"] = int(cap_costs_el.X)
        result_dict["total_el_costs"] = int(supply_costs_el.X + cap_costs_el.X)
        result_dict["rev_feed_in_el"] = int(rev_feed_in_el.X)

        result_dict["supply_costs_gas"] = int(supply_costs_gas.X)
        result_dict["cap_costs_gas"] = int(cap_costs_gas.X)
        result_dict["total_gas_costs"] = int(supply_costs_gas.X + cap_costs_gas.X)
        result_dict["rev_feed_in_gas"] = int(rev_feed_in_gas.X)

        result_dict["supply_costs_biom"] = int(supply_costs_biom.X)
        result_dict["supply_costs_waste"] = int(supply_costs_waste.X)
        result_dict["supply_costs_hydrogen"] = int(supply_costs_hydrogen.X)

        # Prepare time series of renewable generation (without curtailment)
        
        result_dict["PV_generation_uncl"] = devs["PV"]["norm_power"] / 1000 * area["PV"].X          # in kW
        result_dict["WT_generation_uncl"] = devs["WT"]["norm_power"] * cap["WT"].X                  # in kW
        result_dict["STC_generation_uncl"] = devs["STC"]["norm_power"] / 1000 * area["STC"].X       # in kW

        # Prepare time series of renewable curtailment
        power["PV_curtail"] = {}
        power["WT_curtail"] = {}
        power["WAT_curtail"] = {}
        heat["STC_curtail"] = {}
        for d in clusters:
            power["PV_curtail"][d] = {}
            power["WT_curtail"][d] = {}
            power["WAT_curtail"][d] = {}
            heat["STC_curtail"][d] = {}
            for t in time_steps:
                power["PV_curtail"][d][t] = devs["PV"]["norm_power_clustered"][d][t]/1000 * area["PV"].X - power["PV"][d][t].X
                power["WT_curtail"][d][t] = devs["WT"]["norm_power_clustered"][d][t] * cap["WT"].X - power["WT"][d][t].X
                power["WAT_curtail"][d][t] = np.min([cap["WAT"].X, devs["WAT"]["potential"]]) - power["WAT"][d][t].X
                heat["STC_curtail"][d][t] = devs["STC"]["norm_power_clustered"][d][t]/1000  * area["STC"].X - heat["STC"][d][t].X

        result_dict["PV"]["curtailed"]  = int(dt * (sum(sum(power["PV_curtail"][d][t] for t in time_steps) * param["cluster_weights"][d] for d in clusters)))
        result_dict["STC"]["curtailed"] = int(dt * (sum(sum(heat["STC_curtail"][d][t] for t in time_steps) * param["cluster_weights"][d] for d in clusters)))
        result_dict["WT"]["curtailed"]  = int(dt * (sum(sum(power["WT_curtail"][d][t] for t in time_steps) * param["cluster_weights"][d] for d in clusters)))
        result_dict["WAT"]["curtailed"] = int(dt * (sum(sum(power["WAT_curtail"][d][t] for t in time_steps) * param["cluster_weights"][d] for d in clusters)))

        result_dict["power_profile"] = {}
        result_dict["power_kW"] = {}
        for device in ["PV", "WT", "WAT", "HP", "EB", "CC", "CHP", "BCHP", "WCHP", "ELYZ", "FC", "from_grid",
                       "to_grid"]:
            result_dict["power_profile"][device] = []
            for d in clusters:
                for t in time_steps:
                    result_dict["power_profile"][device].append(power[device][d][t].X)
            result_dict["power_kW"][device] = int(max(result_dict["power_profile"][device]))

        # Heat to/from devices
        result_dict["heat_profile"] = {}
        result_dict["heat_kW"] = {}
        for device in ["STC", "HP", "EB", "AC", "CHP", "BOI", "GHP", "BCHP", "BBOI", "WCHP", "WBOI", "FC"]:
            result_dict["heat_profile"][device] = []
            for d in clusters:
                for t in time_steps:
                    result_dict["heat_profile"][device].append(heat[device][d][t].X)
            result_dict["heat_kW"][device] = int(max(result_dict["heat_profile"][device]))

        result_dict["area"] = {}
        for device in ["PV", "STC"]:
            result_dict["area"][device] = int(area[device].X)

        # Calculate generation
        eps = 0.01
        for k in ["STC", "HP", "EB", "BOI", "GHP", "BBOI", "WBOI"]:
            result_dict[k]["gen_kWh"] = dt * sum(sum(heat[k][d][t].X for t in time_steps) * param["cluster_weights"][d] for d in clusters)  # in kWh
            result_dict[k]["gen"] = int(dt * sum(sum(heat[k][d][t].X for t in time_steps) * param["cluster_weights"][d] for d in clusters)/1000)  # in MWh

        for k in ["CC", "AC"]:
            result_dict[k]["gen_kWh"] = dt * sum(sum(cool[k][d][t].X for t in time_steps) * param["cluster_weights"][d] for d in clusters)  # in kWh
            result_dict[k]["gen"] = int(dt * sum(sum(cool[k][d][t].X for t in time_steps) * param["cluster_weights"][d] for d in clusters)/1000)  # in MWh

        for k in ["PV", "WT", "WAT", "CHP", "BCHP", "WCHP", "ELYZ", "FC"]:
            result_dict[k]["gen_kWh"] = dt * sum(sum(power[k][d][t].X for t in time_steps) * param["cluster_weights"][d] for d in clusters)  # in kWh
            result_dict[k]["gen"] = int(dt * sum(sum(power[k][d][t].X for t in time_steps) * param["cluster_weights"][d] for d in clusters)/1000)  # in MWh

        # Calculate hydrogen generation for ELYZ
        result_dict["ELYZ"]["gen_H2"] = int(dt * sum(sum(power["ELYZ"][d][t].X * devs["ELYZ"]["eta_el"]for t in time_steps) * param["cluster_weights"][d] for d in clusters)/1000)  # in MWh

        for k in ["SAB"]:
            result_dict[k]["gen_kWh"] = dt * sum(sum(gas[k][d][t].X for t in time_steps) * param["cluster_weights"][d] for d in clusters)  # in kWh
            result_dict[k]["gen"] = int(dt * sum(sum(gas[k][d][t].X for t in time_steps) * param["cluster_weights"][d] for d in clusters)/1000)  # in MWh

        # Calculate full load hours
        for k in ["PV", "WT", "WAT", "STC", "HP", "EB", "CC", "AC", "CHP", "BOI", "GHP", "BCHP", "BBOI", "WCHP", "WBOI", "ELYZ", "FC", "SAB"]:
            if cap[k].X > eps:
                result_dict[k]["hrs"] = int(result_dict[k]["gen_kWh"] / cap[k].X)
            else:
                result_dict[k]["hrs"] = 0


        # Select technologies that are installed (to list only these in results)
        for k in all_devs:
            if cap[k].X > eps:
                result_dict[k]["inst"] = True
            else:
                result_dict[k]["inst"] = False

        # Calculate charge cycles of storages
        for k in ["TES", "CTES", "BAT", "H2S", "GS"]:
            if cap[k].X > eps:
                result_dict[k]["chc"] = int(dt * sum(sum(abs(ch[k][d][t].X)/2 for t in time_steps) * param["cluster_weights"][d] for d in clusters) / cap[k].X)
            else:
                result_dict[k]["chc"] = 0

        # Calculate volume of thermal storages
        for k in ["TES", "CTES"]:
            result_dict[k]["vol_liter"] = round(cap[k].X / (param["c_w"] * param["rho_w"] * devs[k]["delta_T"]) * 3600 * 1000, 1)

        # Calculate emissions
        result_dict["total_co2_el"] = int(from_el_grid_total.X * param["co2_el_grid"]/1000) # t/a
        result_dict["total_co2_el_feed_in"] = int(to_el_grid_total.X * param["co2_el_feed_in"]/1000) # t/a
        result_dict["total_co2_gas"] = int(from_gas_grid_total.X * param["co2_gas"]/1000) # t/a
        result_dict["total_co2_gas_feed_in"] = int(to_gas_grid_total.X * param["co2_gas_feed_in"]/1000) # t/a
        result_dict["total_co2_biom"] = int(biom_import_total.X * param["co2_biom"]/1000) # t/a
        result_dict["total_co2_waste"] = int(waste_import_total.X * param["co2_waste"]/1000) # t/a
        result_dict["total_co2_hydrogen"] = int(hydrogen_import_total.X * param["co2_hydrogen"]/1000) # t/a

        return result_dict

def save_results_csv(result_dict, scenario_name, result_dir, all_devs):
    """
    Saves specific results from result_dict into a CSV file.

    Parameters
    ----------
    result_dict : dict
        Dictionary containing the results of the optimization.
    scenario_name : str
        Name of the scenario, used to name the CSV file.
    result_dir : str
        Directory where the CSV file will be saved.

    Returns
    -------
    None
    """
    # Ensure the result directory exists
    os.makedirs(result_dir, exist_ok=True)

    # Define the output file path
    csv_file_path = os.path.join(result_dir, f"{scenario_name}_results.csv")

    # Prepare the data to be written to the CSV file
    data_to_save = [
        ["Cost_parameter", "Value"],  # Header row cost-parameters
        ["co2_tax_total", result_dict.get("co2_tax_total", "")],  # CO2 tax total
        ["total_inv_cost", result_dict.get("total_inv_cost", "")],  # Total investment cost
        ["total_ann_inv_cost", result_dict.get("total_ann_inv_cost", "")],  # Total annual investment cost
        ["total_om_cost", result_dict.get("total_om_cost", "")],  # Total operation and maintenance cost
        ["supply_costs_el", result_dict.get("supply_costs_el", "")],  # Supply costs for electricity
        ["cap_costs_el", result_dict.get("cap_costs_el", "")],  # Capacity costs for electricity
        ["total_el_costs", result_dict.get("total_el_costs", "")],  # Total electricity costs
        ["rev_feed_in_el", result_dict.get("rev_feed_in_el", "")],  # Revenue from electricity feed-in
        ["supply_costs_gas", result_dict.get("supply_costs_gas", "")],  # Supply costs for gas
        ["cap_costs_gas", result_dict.get("cap_costs_gas", "")],  # Capacity costs for gas
        ["total_gas_costs", result_dict.get("total_gas_costs", "")],  # Total gas costs
        ["rev_feed_in_gas", result_dict.get("rev_feed_in_gas", "")],  # Revenue from gas feed-in
        ["supply_costs_biom", result_dict.get("supply_costs_biom", "")],  # Supply costs for biomass
        ["supply_costs_waste", result_dict.get("supply_costs_waste", "")],  # Supply costs for waste
        ["supply_costs_hydrogen", result_dict.get("supply_costs_hydrogen", "")],  # Supply costs for hydrogen
        [], # Empty row for separation
        ["Co2_parameter", "Value"],  # Header row co2-parameters
        ["co2_onsite_emissions", result_dict.get("co2_onsite_emissions", "")],  # Onsite CO2 emissions
        ["co2_credit_feedin", result_dict.get("co2_credit_feedin", "")],  # CO2 credit from feed-in
        ["total_co2_el", result_dict.get("total_co2_el", "")],  # Total CO2 emissions from electricity
        ["total_co2_el_feed_in", result_dict.get("total_co2_el_feed_in", "")],  # Total CO2 emissions from electricity feed-in
        ["total_co2_gas", result_dict.get("total_co2_gas", "")],  # Total CO2 emissions from gas
        ["total_co2_gas_feed_in", result_dict.get("total_co2_gas_feed_in", "")],  # Total CO2 emissions from gas feed-in
        ["total_co2_biom", result_dict.get("total_co2_biom", "")],  # Total CO2 emissions from biomass
        ["total_co2_waste", result_dict.get("total_co2_waste", "")],  # Total CO2 emissions from waste
        ["total_co2_hydrogen", result_dict.get("total_co2_hydrogen", "")],  # Total CO2 emissions from hydrogen
        [],  # Empty row for separation
        ["Grid_flows", "Value"],  # Header row grid flows
        ["from_el_grid_total", result_dict.get("from_el_grid_total", "")],   # Total electricity from grid
        ["to_el_grid_total", result_dict.get("to_el_grid_total", "")],       # Total electricity to grid
        ["from_gas_grid_total", result_dict.get("from_gas_grid_total", "")], # Total gas from grid
        ["to_gas_grid_total", result_dict.get("to_gas_grid_total", "")],     # Total gas to grid
        ["biom_import_total", result_dict.get("biom_import_total", "")],     # Total biomass imported
        ["waste_import_total", result_dict.get("waste_import_total", "")],   # Total waste imported
        ["hydrogen_import_total", result_dict.get("hydrogen_import_total", "")], # Total hydrogen imported
        ["max_el_from_grid", result_dict.get("max_el_from_grid", "")], # Maximum electricity from grid
        ["max_el_to_grid", result_dict.get("max_el_to_grid", "")], # Maximum electricity to grid
        ["max_gas_from_grid", result_dict.get("max_gas_from_grid", "")], # Maximum gas from grid
        ["max_gas_to_grid", result_dict.get("max_gas_to_grid", "")], # Maximum gas to grid
        ["max_biom", result_dict.get("max_biom", "")], # Maximum biomass import
        ["max_waste", result_dict.get("max_waste", "")], # Maximum waste import
        ["max_hydrogen", result_dict.get("max_hydrogen", "")], # Maximum hydrogen import
        [],  # Empty row for separation
        ["Areas PV and STC", "Value"],  # Header row generation parameters
        ["PV", result_dict.get("area", {}).get("PV", 0)],  # Area for PV
        ["STC", result_dict.get("area", {}).get("STC", 0)],  # Area for STC
        [], #  Empty row for separation
        ["volumes of thermal storages", "Value"],  # Header row for storage volumes
        ["TES", result_dict.get("TES", {}).get("vol_liter", 0)],  # Volume of TES in liters
        ["CTES", result_dict.get("CTES", {}).get("vol_liter", 0)],  # Volume of CTES in liters

        # # Calculate volume of thermal storages
        # for k in ["TES", "CTES"]:
        #     result_dict[k]["vol_liter"] 
        ["", ""],  # Empty row for separation
        ["Device-capacity", "Value"],  # Header row for device capacities

    ]
    # Add devices to the CSV file if they are installed
    for device in all_devs:
        if result_dict.get(device, {}).get("inst", False):  # Check if the device is installed
            capacity = result_dict.get(device, {}).get("cap", 0)  # Get the capacity of the device
            data_to_save.append([device, capacity])  # Add the device name to the CSV file

    # Write the data to the CSV file
    with open(csv_file_path, mode="w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file, delimiter=";")
        writer.writerows(data_to_save)

    print(f"Results saved to {csv_file_path}")
    