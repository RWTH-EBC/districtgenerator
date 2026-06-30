# -*- coding: utf-8 -*-

import numpy as np
import math
import os
import json
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import fluids
import textwrap
import pandas as pd

"""
Simple 2-pipe district-heating network model.

The Energy Hub supply temperature is calculated as:

    T_sup_EH(t) = max_n(T_sup_req,n(t))

The return temperature is calculated directly from the
mass-flow-weighted SH/DHW return temperatures of all connected buildings.

Pipe heat losses are calculated afterward from network-level supply and return
temperatures. In this simplified model, pipe heat losses do not change the
supply or return temperature along the pipes.

The model workflow is:
    1) prepare building loads and temperature requirements
    2) calculate building and pipe mass flows
    3) size pipe diameters
    4) compute local hydraulic losses
    5) calculate EH return temperature from building return mixing
    6) calculate pipe heat losses from
    7) compute pump power and network costs
"""

# MAIN WORKFLOW

def network_2leiter_simple(data, compute_costs=True, save_debug=True):
    """
    Simple auto-only 2-pipe network model.

    Assumptions
    -----------
    - Pipe heat losses are calculated, but they do not change
      supply or return temperatures along the pipes.
    - EH return temperature is calculated directly from the mixed building
      return flows.
    """

    # 1) Load parameters
    data, param = load_parameter_2leiter(data)
    prepare_result_folder(data, param)

    # 2) Initialize network pipes
    data.pipeline = {}
    initialize_pipeline_from_topology(data)

    # 3) Select pipe class based on maximum auto supply temperature
    update_pipe_data_selection(data, param, float(np.max(param["T_sup_design_base"])))

    # 4) Calculate building and pipe mass flows
    data, param = calc_flow_2leiter(data, param)

    # 5) Select pipe diameters
    data, param = calc_diameter_2leiter(data, param)

    # 6) Local hydraulic losses
    hydraulic_features = identify_junction_and_bends(data)
    data, zeta = compute_zeta_values(data, param, hydraulic_features)
    param["zeta"] = zeta
    param["hydraulic_features"] = hydraulic_features

    # 7) Calculate EH return temperature directly from building returns
    data, param = compute_return_temperature_EH_2leiter(data, param)

    # 8) Calculate pipe heat losses from network-level temperatures
    data, param = calc_heat_loss_pipe_simple_2leiter(data, param)

    # 9) Pump power
    data, param = compute_pump_power_2leiter(data, param)

    # 10) Plot network results
    plot_network_results_2leiter(data, param)

    if save_debug:
        _save_debug_outputs(data, param)

    if compute_costs:
        compute_and_save_network_costs_2leiter(data, param)

    return data, param

# PARAMETER PREPARATION

def load_parameter_2leiter(data):
    """
    Prepare loads, required supply temperatures, economic parameters,
    and the auto supply-temperature profile.

    The return temperature is not prescribed in this model.
    It is calculated later from SH/DHW return flows, return-pipe heat exchange,
    and return mixing at the energy hub.
    """

    param = {}

    # Heat grid data and basic parameters
    heat_grid_data = data.heat_grid_data

    T_len = len(data.heat_grid_data["T_soil"])
    heat_loss_substation = np.zeros(T_len, dtype=float)
    net_heat_demand = np.zeros(T_len, dtype=float)

    h_loss_subst = data.heat_grid_data["h_loss_subst"]  # Heat losses at the substation

    # HX design assumptions
    # Space heating HX
    dT_HX_sup_SH = 4.0
    dT_HX_ret_SH_design = 3.0  # Source: Leitfaden zur Planung von Fernwärme-Übergabestationen https://www.verenum.ch/Dokumente/Leitfaden_FW-UGST_V1.0.pdf

    # DHW HX
    dT_HX_sup_DHW = 4.0
    dT_HX_ret_DHW_min = 10.0  # Source: Leitfaden zur Planung von Fernwärme-Übergabestationen https://www.verenum.ch/Dokumente/Leitfaden_FW-UGST_V1.0.pdf

    T_dhw_required = float(data.decentral_device_data["TES_DHW"]["T_DHW_needed"])

    # Cold water temperature for DHW heat exchanger
    T_cold_water = 10.0

    # Build fast lookup: building position -> node id
    node_lookup = {
        tuple(node_info["pos"]): key
        for key, node_info in data.pipeline_nodes.items()}

    # Calculate building heat demand connected to the district heating grid
    for building in data.district:
        if building["buildingFeatures"]["heater"] not in ["heat_grid", "heat_grid_SH"]:
            continue

        heating = building["user"].heat / 1000  # kW
        dhw = building["user"].dhw / 1000  # kW
        generationSTC = building["generationSTC"] / 1000  # kW

        if building["buildingFeatures"]["heater"] == "heat_grid":
            net_building_demand = np.maximum(heating + dhw - generationSTC, 0.0)

        elif building["buildingFeatures"]["heater"] == "heat_grid_SH":
            net_building_demand = np.maximum(heating - generationSTC, 0.0)

        building["user"].net_building_demand = net_building_demand  # kW

        # Additional heat required to cover substation heat losses
        subst_loss = net_building_demand * (h_loss_subst / 100)
        heat_loss_substation += subst_loss                # kW

        # Total heat demand supplied by the network
        # (building demand + substation heat losses)
        net_heat_demand += net_building_demand + subst_loss

    # Build temperature requirements and loads at the substatiom
    T_sup_req_by_node = {}
    T_sec_supply_SH_by_node = {}
    T_sec_return_SH_by_node = {}
    T_sec_supply_DHW_by_node = {}
    T_sec_return_DHW_by_node = {}
    Q_SH_by_node = {}
    Q_DHW_by_node = {}
    Q_DHW_decentral_by_node = {}
    Q_by_node = {}
    UA_SH_by_node = {}
    UA_DHW_by_node = {}

    for building in data.district:
        if building["buildingFeatures"]["heater"] not in ["heat_grid", "heat_grid_SH"]:
            continue

        pos_building = tuple(building["buildingFeatures"]["position"])

        node_key = node_lookup.get(pos_building)

        if node_key is None:
            continue

        buildings_heating_curve = building["envelope"].heating_curve["unclustered"]

        # Required supply and return temperatures
        if data.heat_grid_data["enable_low_temp_measures"] == True:
            Ts_sec_SH = np.asarray(buildings_heating_curve["Ts_curve_reduced"], dtype=float)
            Tr_sec_SH = np.asarray(buildings_heating_curve["Tr_curve_reduced"], dtype=float)
        else:
            Ts_sec_SH = np.asarray(buildings_heating_curve["Ts_curve"], dtype=float)
            Tr_sec_SH = np.asarray(buildings_heating_curve["Tr_curve"], dtype=float)

        Ts_req_SH = Ts_sec_SH + dT_HX_sup_SH
        Ts_req_DHW = T_dhw_required + dT_HX_sup_DHW

        # The network supply temperature must satisfy both space heating (SH)
        # and domestic hot water (DHW) requirements. Therefore, the required
        # supply temperature at the building is defined as the maximum of the
        # SH and DHW supply temperature levels.
        dhw_load = np.asarray(building["user"].dhw, dtype=float) / 1000.0  # kW
        sh_load = np.asarray(building["user"].heat, dtype=float) / 1000.0  # kW

        # Supply temperature constraint
        #Ts_req = np.maximum(Ts_req_SH, Ts_req_DHW)

        if building["buildingFeatures"]["heater"] == "heat_grid":
            Ts_req = np.maximum(Ts_req_SH, Ts_req_DHW)

        elif building["buildingFeatures"]["heater"] == "heat_grid_SH":
            Ts_req = Ts_req_SH

        # Building heat load
        #todo: STC are still not considered here
        Q_SH = sh_load * (1.0 + h_loss_subst / 100.0)
        #Q_DHW = dhw_load * (1.0 + h_loss_subst / 100.0)
        #Q_total = Q_SH + Q_DHW

        Q_DHW_total = dhw_load * (1.0 + h_loss_subst / 100.0)

        if building["buildingFeatures"]["heater"] == "heat_grid":
            Q_DHW_grid = Q_DHW_total
            Q_DHW_decentral = np.zeros(T_len, dtype=float)

        elif building["buildingFeatures"]["heater"] == "heat_grid_SH":
            Q_DHW_grid = np.zeros(T_len, dtype=float)
            Q_DHW_decentral = Q_DHW_total

        Q_total = Q_SH + Q_DHW_grid





        HX_UA_safety_factor = 1.0  # [-] heat-exchanger oversizing factor; 1.15 means 15% larger UA than theoretical design UA

        # Design UA for SH heat exchanger
        if np.any(Q_SH > 0.0):
            Q_SH_design_W = building["bes_obj"].design_load_heating * (1.0 + h_loss_subst / 100.0)          # [W] design space-heating load of the building
            T_s_SH_secondary_design = max(Ts_sec_SH)                   # Temperature from the heating curve of the building at the norm outside design temperature T_ne
            T_r_SH_secondary_design = max(Tr_sec_SH)                   # Temperature from the heating curve of the building at the norm outside design temperature T_ne

            T_s_SH_primary_design = T_s_SH_secondary_design + dT_HX_sup_SH
            T_r_SH_primary_design = T_r_SH_secondary_design + dT_HX_ret_SH_design

            UA_SH = HX_UA_safety_factor * hx_calc_UA_design(
                Q_design_W=Q_SH_design_W,
                T_primary_in_design=T_s_SH_primary_design,
                T_primary_out_design=T_r_SH_primary_design,
                T_secondary_in_design=T_r_SH_secondary_design,
                T_secondary_out_design=T_s_SH_secondary_design
            )
        else:
            UA_SH = 0.0

        # Design UA for DHW heat exchanger
        if building["buildingFeatures"]["heater"] == "heat_grid" and np.any(Q_DHW_grid > 0.0):
            Q_DHW_design_W = building["bes_obj"].design_load_dhw * (1.0 + h_loss_subst / 100.0)
            T_cold_DHW_secondary_design = float(T_cold_water)
            T_hot_DHW_secondary_design = float(T_dhw_required)

            T_s_DHW_primary_design = T_hot_DHW_secondary_design + dT_HX_sup_DHW
            T_r_DHW_primary_design = T_cold_DHW_secondary_design + dT_HX_ret_DHW_min

            UA_DHW = HX_UA_safety_factor * hx_calc_UA_design(
                Q_design_W=Q_DHW_design_W,
                T_primary_in_design=T_s_DHW_primary_design,
                T_primary_out_design=T_r_DHW_primary_design,
                T_secondary_in_design=T_cold_DHW_secondary_design,
                T_secondary_out_design=T_hot_DHW_secondary_design
            )
        else:
            UA_DHW = 0.0

        T_sup_req_by_node[node_key] = Ts_req

        # Secondary-side temperatures
        T_sec_supply_SH_by_node[node_key] = Ts_sec_SH
        T_sec_return_SH_by_node[node_key] = Tr_sec_SH
        T_sec_supply_DHW_by_node[node_key] = np.full(T_len, T_dhw_required, dtype=float)
        T_sec_return_DHW_by_node[node_key] = np.full(T_len, T_cold_water, dtype=float)

        # Loads at the substation
        Q_SH_by_node[node_key] = Q_SH
        #Q_DHW_by_node[node_key] = Q_DHW
        Q_DHW_by_node[node_key] = Q_DHW_grid
        Q_DHW_decentral_by_node[node_key] = Q_DHW_decentral
        Q_by_node[node_key] = Q_total

        UA_SH_by_node[node_key] = UA_SH
        UA_DHW_by_node[node_key] = UA_DHW

    # store them into param
    param["T_sup_req_by_node"] = T_sup_req_by_node
    param["T_sec_supply_SH_by_node"] = T_sec_supply_SH_by_node
    param["T_sec_return_SH_by_node"] = T_sec_return_SH_by_node
    param["T_sec_supply_DHW_by_node"] = T_sec_supply_DHW_by_node
    param["T_sec_return_DHW_by_node"] = T_sec_return_DHW_by_node
    param["Q_SH_by_node"] = Q_SH_by_node
    param["Q_DHW_by_node"] = Q_DHW_by_node
    param["Q_DHW_decentral_by_node"] = Q_DHW_decentral_by_node
    param["Q_by_node"] = Q_by_node
    param["UA_SH_by_node"] = UA_SH_by_node
    param["UA_DHW_by_node"] = UA_DHW_by_node
    param["heat_loss_substation"] = heat_loss_substation
    param["net_heat_demand"] = net_heat_demand

    # Auto-only supply temperature mode.
    # The EH supply temperature is set to the highest building supply-temperature
    # requirement at each timestep. No fixed supply mode, heating curve mode,
    # return_temperature input, or delta_T input is used in this simplified model.
    if heat_grid_data.get("supply_temperature") != "auto":
        raise ValueError(
            "This simplified 2-pipe model only supports "
            "data.heat_grid_data['supply_temperature'] = 'auto'."
        )

    # Use the highest required building supply temperature at each timestep
    Ts_matrix = np.vstack(list(T_sup_req_by_node.values()))
    T_sup_design_base = np.max(Ts_matrix, axis=0)

    param["T_sup_design_base"] = T_sup_design_base

    # Annualization factors.
    pipe_lifetime = heat_grid_data["pipe"]["pipe_lifetime"]
    heat_grid_data["pipe"]["pipe_ann_factor"] = calc_annual_factor(data, pipe_lifetime)

    pump_lifetime = heat_grid_data["pump"]["pump_lifetime"]
    heat_grid_data["pump"]["pump_ann_factor"] = calc_annual_factor(data, pump_lifetime)

    HP_lifetime = data.central_device_data["AirHP"]["life_time"]
    param["HP_ann_factor"] = calc_annual_factor(data, HP_lifetime)

    return data, param

def update_pipe_data_selection(data, param, Ts_max):
    """
    Select pipe catalogue based on maximum supply temperature and compute
    heat-loss factors

    Returns True if the pipe catalogue changed.
    """

    heat_grid_data = data.heat_grid_data

    if Ts_max > 60.0:
        pipe_class = "KMR"
        pipe_data = data.pipe_data_all["KMR"].copy()
    elif Ts_max > 35.0:
        pipe_class = "PMR+KMR_large"
        pmr_data = data.pipe_data_all["PMR"]
        kmr_data = data.pipe_data_all["KMR"]
        kmr_large = kmr_data[kmr_data["Nominal diameter (DN)"] > 150]
        pipe_data = pd.concat([pmr_data, kmr_large], ignore_index=True)
    else:
        pipe_class = "PE"
        pipe_data = data.pipe_data_all["PE"].copy()

    old_class = param.get("pipe_class")
    changed = old_class is not None and old_class != pipe_class

    data.pipe_data = pipe_data
    param["pipe_class"] = pipe_class

    pipe_dict = data.pipe_data.set_index("Nominal diameter (DN)").to_dict(orient="index")

    # Heat loss parameters (DIN EN 13941)
    k_soil = heat_grid_data["k_soil"] # 1.52 W/(m*K),     Soil thermal conductivity, corresponding to λ_s in EN 13941
    k_pipe = heat_grid_data["k_PUF"]  # 0.03 W/(m*K),    Thermal conductivity of pipe insulation materials, corresponding to λ_i in EN 13941.

    # Corrected burial depth including surface thermal resistance
    # at the soil surface (EN 13941 correction)
    Z_c = heat_grid_data["grid_depth"] + 0.069 * k_soil

    # Distance between the centerlines of the supply and return pipelines
    D_heating_network = data.heat_grid_data["D_heating_network"] # 1m

    # symmetrical and (a) antisymmetrical heat loss factors
    # Heat Interference Correction Factor Between Pipes (Heat Transfer Between Supply and Return Water)
    b = np.log((1 + (2 * Z_c / D_heating_network) ** 2) ** 0.5)  # DIN EN 13941-1 D.3
    for DN, pipe in pipe_dict.items():
        da = pipe["Outer diameter (pipe) (mm)"]
        Da = pipe["Outer diameter (case) (mm)"]
        # The soil thermal resistance term depends on the burial depth Zc
        # and the outer diameter Da of the pipe plus insulation layer.
        a = np.log(4 * Z_c / (Da / 1000))  # DIN EN 13941-1 D.3
        # The thermal resistance component of the insulation layer depends on the outer diameter Da of the pipe plus
        # insulation layer and the outer diameter da of the steel pipe.
        beta = k_soil / k_pipe * np.log(Da / da)  # DIN EN 13941-1 D.7
        # ks / ka：symmetrical and (a) antisymmetrical heat loss factors according to zero-order multipole formula
        ks_heating_network = (a + beta + b) ** -1  # DIN EN 13941-1 D.3
        ka_heating_network = (a + beta - b) ** -1
        pipe["symmetrical heat loss factor"] = ks_heating_network
        pipe["antisymmetrical heat loss factor"] = ka_heating_network # to consider heat flow between supply and return pipes

    param["pipe_dict"] = pipe_dict

    print(f"[INFO] Pipe selection: {pipe_class}, design T = {Ts_max:.1f} °C")
    return changed

# FLOW, DIAMETER, HYDRAULICS

def initialize_pipeline_from_topology(data):
    """Create data.pipeline entries for every topology edge."""

    T_len = len(data.heat_grid_data["T_soil"])

    for parent, children in data.pipeline_topology.items():
        for child in children:
            pipe_id = f"{parent}->{child}"
            pos_parent = data.pipeline_nodes[parent]["pos"]
            pos_child = data.pipeline_nodes[child]["pos"]
            p1 = np.asarray(pos_parent, dtype=float)
            p2 = np.asarray(pos_child, dtype=float)
            length = float(np.linalg.norm(p1 - p2))

            data.pipeline[pipe_id] = {
                "from": parent,
                "to": child,
                "from_pos": pos_parent,
                "to_pos": pos_child,
                "length": length,
                "flow": np.zeros(T_len, dtype=float),
                "flow_max": 0.0,
                "flow_min": 0.0,
            }

def calc_flow_2leiter(data, param):
    """
    Calculate SH, DHW, building-total, and pipe flows.
    """

    c_f = data.heat_grid_data["fluid"]["c_f"]
    rho_f = data.heat_grid_data["fluid"]["rho_f"]
    alpha = float(data.heat_grid_data.get("min_flow_fraction", 0.0))

    T_sup_EH = np.asarray(param["T_sup_design_base"], dtype=float)
    T_len = len(T_sup_EH)

    param["building_massflow_SH"] = {}
    param["building_massflow_DHW"] = {}
    param["building_massflow_HX"] = {}
    param["building_massflow_max_SH"] = {}
    param["building_massflow_max_DHW"] = {}
    param["building_massflow_max_HX"] = {}
    param["T_return_SH_actual"] = {}
    param["T_return_DHW_actual"] = {}

    for n in param["Q_by_node"].keys():

        Q_SH = np.asarray(param["Q_SH_by_node"][n], dtype=float)
        Q_DHW = np.asarray(param["Q_DHW_by_node"][n], dtype=float)

        Q_SH_eff = np.where(Q_SH < 0.01, 0.0, Q_SH)
        Q_DHW_eff = np.where(Q_DHW < 0.01, 0.0, Q_DHW)

        Tsi_SH = np.asarray(param["T_sec_return_SH_by_node"][n], dtype=float)
        Tso_SH = np.asarray(param["T_sec_supply_SH_by_node"][n], dtype=float)

        Tsi_DHW = np.asarray(param["T_sec_return_DHW_by_node"][n], dtype=float)
        Tso_DHW = np.asarray(param["T_sec_supply_DHW_by_node"][n], dtype=float)

        UA_SH = float(param["UA_SH_by_node"][n])
        UA_DHW = float(param["UA_DHW_by_node"][n])

        m_SH_raw = np.zeros(T_len, dtype=float)     # Empty array
        m_DHW_raw = np.zeros(T_len, dtype=float)    # Empty array

        Tr_SH_raw = np.full(T_len, np.nan, dtype=float)         # Empty array
        Tr_DHW_raw = np.full(T_len, np.nan, dtype=float)        # Empty array

        for t in range(T_len):

            Ts = float(T_sup_EH[t])

            # Space heating HX
            Q_SH_W = float(Q_SH_eff[t]) * 1000.0

            Tr_SH, m_SH = hx_primary_return_and_flow(
                Q_W=Q_SH_W,
                T_primary_in=Ts,
                T_secondary_in=float(Tsi_SH[t]),
                T_secondary_out=float(Tso_SH[t]),
                UA=UA_SH,
                c_p=c_f)

            Tr_SH_raw[t] = Tr_SH
            m_SH_raw[t] = m_SH

            # DHW HX
            Q_DHW_W = float(Q_DHW_eff[t]) * 1000.0

            Tr_DHW, m_DHW = hx_primary_return_and_flow(
                Q_W=Q_DHW_W,
                T_primary_in=Ts,
                T_secondary_in=float(Tsi_DHW[t]),
                T_secondary_out=float(Tso_DHW[t]),
                UA=UA_DHW,
                c_p=c_f
            )

            Tr_DHW_raw[t] = Tr_DHW
            m_DHW_raw[t] = m_DHW

        # Apply minimum flow fraction if used
        m_SH_max = float(np.max(m_SH_raw)) if np.any(m_SH_raw > 0.0) else 0.0
        m_DHW_max = float(np.max(m_DHW_raw)) if np.any(m_DHW_raw > 0.0) else 0.0

        m_SH = np.maximum(m_SH_raw, alpha * m_SH_max)
        m_DHW = np.maximum(m_DHW_raw, alpha * m_DHW_max)

        # Recalculate return temperatures if minimum flow changes the flow
        Tr_SH_actual = np.full(T_len, np.nan, dtype=float)
        Tr_DHW_actual = np.full(T_len, np.nan, dtype=float)

        active_SH = Q_SH_eff > 0.0
        active_DHW = Q_DHW_eff > 0.0

        # If no load, return and supply temperatures are equal
        Tr_SH_actual[~active_SH] = T_sup_EH[~active_SH]
        Tr_DHW_actual[~active_DHW] = T_sup_EH[~active_DHW]

        mask_SH = active_SH & (m_SH > 1e-12)
        mask_DHW = active_DHW & (m_DHW > 1e-12)

        Tr_SH_actual[mask_SH] = (
                T_sup_EH[mask_SH]
                - Q_SH_eff[mask_SH] * 1000.0 / (m_SH[mask_SH] * c_f)
        )

        Tr_DHW_actual[mask_DHW] = (
                T_sup_EH[mask_DHW]
                - Q_DHW_eff[mask_DHW] * 1000.0 / (m_DHW[mask_DHW] * c_f)
        )

        m_HX = m_SH + m_DHW

        param["building_massflow_SH"][n] = m_SH
        param["building_massflow_DHW"][n] = m_DHW
        param["building_massflow_HX"][n] = m_HX
        param["building_massflow_max_SH"][n] = m_SH_max
        param["building_massflow_max_DHW"][n] = m_DHW_max
        param["building_massflow_max_HX"][n] = (float(np.max(m_HX)) if np.any(m_HX > 0.0) else 0.0)
        param["T_return_SH_actual"][n] = Tr_SH_actual
        param["T_return_DHW_actual"][n] = Tr_DHW_actual

    # Aggregate building flows into pipe flows
    pipe_massflows = aggregate_mass_flows(
        data.pipeline_topology,
        param["building_massflow_HX"],
        root="EH1"
    )
    param["pipe_massflows"] = pipe_massflows

    for (parent, child), massflow_array in pipe_massflows.items():
        pipe_id = f"{parent}->{child}"
        flow_array = massflow_array / rho_f
        mask = flow_array > 1e-12

        data.pipeline[pipe_id]["flow"] = flow_array
        data.pipeline[pipe_id]["flow_max"] = (float(np.max(flow_array[mask])) if np.any(mask) else 0.0)
        data.pipeline[pipe_id]["flow_min"] = (float(np.min(flow_array[mask])) if np.any(mask) else 0.0)

    return data, param

def calc_diameter_2leiter(data, param):
    """
    Select appropriate pipe diameters for each network segment.

    Pipe diameters are determined by directly evaluating each
    available nominal diameter (DN). For every candidate DN the
    velocity, Reynolds number, friction factor and pressure
    gradient are computed using the Darcy–Weisbach equation.

    The smallest DN satisfying both hydraulic and velocity
    constraints is selected.

    Parameters
    ----------
    data : datahandler
        Contains pipeline flow data and fluid properties.

    param : dict
        Dictionary containing available pipe diameters.

    Returns
    -------
    data : datahandler
        Updated pipeline dictionary including selected DN.

    param : dict
        Unmodified parameter dictionary.
    """

    # Fluid density
    rho_f = data.heat_grid_data["fluid"]["rho_f"]  # 1000kg/m^3,   fluid density
    nu_f = data.heat_grid_data["fluid"]["nu_f"]

    # Allowable pressure gradient limits
    dp_pipe_max = data.heat_grid_data["pipe"]["dp_pipe_max"]     # Pa/m,      maximum pipe pressure gradient (Planungshandbuch Fernwärme)
    #dp_pipe_min = data.heat_grid_data["pipe"]["dp_pipe_min"]    # Pa/m,       minimum pipe pressure gradient (Source: Improved genetic algorithm for pipe diameter optimization of an existing large-scale district heating network https://doi.org/10.1016/j.energy.2024.131970)

    pipe_dict = param["pipe_dict"]
    DN_list = sorted(pipe_dict)

    # Evaluate DN candidates
    for pipe_id, pipe in data.pipeline.items():

        V_max = pipe["flow_max"]  # volumetric flow [m³/s]

        best_DN = None
        f_selected = None

        # test DN from smallest to largest
        for DN in DN_list:

            vals = pipe_dict[DN]

            d_i = vals["Inner diameter (pipe) (mm)"] / 1000.0
            rough = vals["Roughness (mm)"] / 1000.0

            A = np.pi * d_i**2 / 4.0
            v = V_max / A

            # Velocity constraint based on maximum volumetric flow.
            # Typical district heating design limits are:
            #   ≤ 1.2 m/s for small pipes (DN ≤ 32)
            #   ≤ 2.0 m/s for larger pipes.
            # Sources:
            # Leitfaden Nahwärme, Frauenhofer Umsicht (1998), Seite A53
            # Planungshandbuch Fernwärme (2021), Verenum AG: Bild 1.4 auf S.13
            v_lim = 1.2 if DN <= 32 else 2.0
            if v > v_lim:
                continue

            Re = v * d_i / nu_f
            f = fluids.friction.friction_factor(Re=Re, eD=rough / d_i)

            dp_per_m = f * rho_f * v**2 / (2.0 * d_i)

            # Choose the smallest feasible diameter
            if dp_per_m <= dp_pipe_max:
                best_DN = DN
                f_selected = f
                break

        # fallback if no DN satisfies both limits
        if best_DN is None:
            best_DN = DN_list[-1]
            vals = pipe_dict[best_DN]
            d_i = vals["Inner diameter (pipe) (mm)"] / 1000.0
            rough = vals["Roughness (mm)"] / 1000.0

            A = np.pi * d_i**2 / 4.0
            v = V_max / A
            Re = v * d_i / nu_f
            f_selected = fluids.friction.friction_factor(Re=Re, eD=rough / d_i)

        pipe["DN"] = best_DN
        pipe["f_fric"] = float(f_selected)
        pipe["d_i"] = pipe_dict[best_DN]["Inner diameter (pipe) (mm)"]

    return data, param

def compute_pump_power_2leiter(data, param):
    """Compute required pump power and pump head profiles for the final state."""

    rho = data.heat_grid_data["fluid"]["rho_f"]
    nu_f = data.heat_grid_data["fluid"]["nu_f"]
    eta_pump = data.heat_grid_data["pump"]["eta_pump"]
    dp_substation = float(data.heat_grid_data.get("dp_substation", 0.0))
    dp_energy_hub = float(data.heat_grid_data.get("dp_energy_hub", 0.0))

    root = "EH1"
    topo = data.pipeline_topology
    pipe_dict = param["pipe_dict"]
    T_len = len(data.heat_grid_data["T_soil"])
    building_nodes = list(param["Q_by_node"].keys())

    parent, order = _topology_parent_order(topo, root)
    pair_to_pid = {(p["from"], p["to"]): pid for pid, p in data.pipeline.items()}
    path_to_root = _path_to_root(order, parent, root)

    P_pump = np.zeros(T_len, dtype=float)
    dp_pump = np.zeros(T_len, dtype=float)

    for t in range(T_len):
        pipe_dp = {}

        for pid, pipe in data.pipeline.items():
            DN = pipe["DN"]
            d_i = pipe_dict[DN]["Inner diameter (pipe) (mm)"] / 1000.0
            rough = pipe_dict[DN]["Roughness (mm)"] / 1000.0
            L = pipe["length"]
            V = float(pipe["flow"][t])

            A = np.pi * d_i ** 2 / 4.0
            v = V / A if A > 0 else 0.0
            Re = v * d_i / nu_f if nu_f > 0 else 0.0
            f = fluids.friction.friction_factor(Re=Re, eD=rough / d_i)

            dp_friction = 2.0 * f * (L / d_i) * (rho * v ** 2 / 2.0)
            dp_local = pipe.get("zeta", 0.0) * (rho * v ** 2 / 2.0)
            pipe_dp[pid] = dp_friction + dp_local

        dp_crit = 0.0
        for n in building_nodes:
            dp_path = sum(pipe_dp[pair_to_pid[(par, ch)]] for par, ch in path_to_root[n])
            dp_crit = max(dp_crit, dp_path + dp_substation)

        V_total = sum(
            float(pipe["flow"][t])
            for pipe in data.pipeline.values()
            if pipe["from"] == root
        )

        dp_total = dp_crit + dp_energy_hub
        dp_pump[t] = dp_total
        P_pump[t] = V_total * dp_total / eta_pump

    safety_factor = float(data.heat_grid_data.get("pump_safety_factor", 1.3))

    data.heat_grid_data["P_pump"] = P_pump
    data.heat_grid_data["pump_power_design"] = float(np.max(P_pump)) / 1000.0 * safety_factor
    data.heat_grid_data["dp_pump_max"] = float(np.max(dp_pump)) * safety_factor
    param["dp_pump_profile"] = dp_pump

    return data, param

def compute_return_temperature_EH_2leiter(data, param):
    """
    Calculate Energy Hub return temperature directly from building returns.

    The SH and DHW primary return temperatures are already calculated
    in calc_flow_2leiter from the UA heat exchanger model.
    """

    T_sup_EH = np.asarray(param["T_sup_design_base"], dtype=float)
    T_len = len(T_sup_EH)

    building_nodes = list(param["Q_by_node"].keys())

    T_ret_building = {n: np.zeros(T_len, dtype=float) for n in building_nodes}
    T_ret_EH = np.zeros(T_len, dtype=float)

    for t in range(T_len):

        m_total_sum = 0.0
        Tmix_sum = 0.0

        for n in building_nodes:

            m_SH = float(param["building_massflow_SH"][n][t])
            m_DHW = float(param["building_massflow_DHW"][n][t])
            m_HX = float(param["building_massflow_HX"][n][t])

            Tr_SH = float(param["T_return_SH_actual"][n][t])
            Tr_DHW = float(param["T_return_DHW_actual"][n][t])

            Ts = float(T_sup_EH[t])

            if m_HX > 1e-12:
                Tr_building = (
                                      m_SH * Tr_SH
                                      + m_DHW * Tr_DHW
                              ) / m_HX
            else:
                Tr_building = Ts

            T_ret_building[n][t] = Tr_building

            if m_HX > 1e-12:
                m_total_sum += m_HX
                Tmix_sum += m_HX * Tr_building

        if m_total_sum > 1e-12:
            T_ret_EH[t] = Tmix_sum / m_total_sum
        else:
            # No flow/no load: return temperature is not physically defined.
            # Use supply temperature as neutral fallback.
            T_ret_EH[t] = T_sup_EH[t]

    data.heat_grid_data["T_supply_EH"] = T_sup_EH
    data.heat_grid_data["T_return_EH"] = T_ret_EH

    param["T_ret_building"] = T_ret_building

    return data, param

def calc_heat_loss_pipe_simple_2leiter(data, param):
    """
    Calculate pipe heat losses for the simple 2-pipe model.

    For each pipe segment i:

        Q_loss_sup,i = UA_i * (T_sup_EH - T_soil)
        Q_loss_ret,i = UA_i * (T_ret_EH - T_soil)

        Q_loss_total,i = Q_loss_sup,i + Q_loss_ret,i

    Positive values mean heat loss to the soil.
    Negative values mean heat gain from the soil.
    """

    k_soil = data.heat_grid_data["k_soil"]
    T_soil = np.asarray(data.heat_grid_data["T_soil"], dtype=float)

    T_sup_EH = np.asarray(data.heat_grid_data["T_supply_EH"], dtype=float)
    T_ret_EH = np.asarray(data.heat_grid_data["T_return_EH"], dtype=float)

    heat_loss_pipe = {}
    annual_heat_loss_network_signed = 0.0

    for pid, pipe in data.pipeline.items():

        parent = pipe["from"]
        child = pipe["to"]
        DN = pipe["DN"]

        ks = param["pipe_dict"][DN]["symmetrical heat loss factor"]

        # UA of one pipe line for this segment
        UA = 2.0 * np.pi * k_soil * ks * pipe["length"]  # W/K

        Q_sup = UA * (T_sup_EH - T_soil) / 1000.0  # kW
        Q_ret = UA * (T_ret_EH - T_soil) / 1000.0  # kW

        Q_total = Q_sup + Q_ret

        pipe["heat_loss_pipe"] = Q_total
        pipe["heat_loss_supply"] = Q_sup
        pipe["heat_loss_return"] = Q_ret

        heat_loss_pipe[(parent, child)] = Q_total
        annual_heat_loss_network_signed += float(np.sum(Q_total))

    param["heat_loss_pipe"] = heat_loss_pipe
    param["annual_heat_loss_pipes_signed"] = annual_heat_loss_network_signed

    heat_loss_pos_network = np.zeros_like(T_soil, dtype=float)
    heat_gain_pos_network = np.zeros_like(T_soil, dtype=float)

    for t in range(len(T_soil)):
        net = sum(float(pipe["heat_loss_pipe"][t]) for pipe in data.pipeline.values())
        heat_loss_pos_network[t] = max(net, 0.0)
        heat_gain_pos_network[t] = max(-net, 0.0)

    param["annual_heat_loss_pos"] = float(np.sum(heat_loss_pos_network))
    param["annual_heat_gain_pos"] = float(np.sum(heat_gain_pos_network))

    param["annual_heat_loss_pos_total"] = (
            float(np.sum(param["heat_loss_substation"]))
            + param["annual_heat_loss_pos"]
    )

    data.heat_grid_data["total_losses_heating_network"] = (
            param["heat_loss_substation"]
            + heat_loss_pos_network
    )

    for pid, pipe in data.pipeline.items():
        length = max(float(pipe["length"]), 1e-12)
        pipe["heat_loss_density"] = (
                float(np.sum(pipe["heat_loss_pipe"])) / 1000.0 / length
        )  # MWh/m

    return data, param



#################################################################################################
#################################################################################################
#################################################################################################

# COSTS AND OUTPUTS

def plot_network_results_2leiter(data, param):
    """
    Generate network plots for the simple 2-pipe model.

    Plots:
        1) pipe ID map
        2) pipe diameter map
        3) maximum velocity map
        4) maximum pressure-gradient map
        5) energy-density map
        6) heat-loss-density map

    Note
    ----
    In this simplified model, pipe temperatures are not propagated.
    Therefore, energy density is calculated with the network-level
    temperature difference:

        DeltaT_network = T_supply_EH - T_return_EH
    """

    dir_result = param["dir_result"]
    os.makedirs(dir_result, exist_ok=True)

    rho_f = data.heat_grid_data["fluid"]["rho_f"]
    c_f = data.heat_grid_data["fluid"]["c_f"]

    cmap = plt.cm.RdYlGn_r

    def _line_width(value, vmin, vmax):
        if abs(vmax - vmin) < 1e-12:
            return 3.0
        return 1.0 + 5.0 * (value - vmin) / (vmax - vmin)

    def _safe_norm(values):
        vmin = min(values)
        vmax = max(values)
        if abs(vmax - vmin) < 1e-12:
            vmax = vmin + 1.0
        return mcolors.Normalize(vmin=vmin, vmax=vmax)

    def _midpoint_label(ax, start, end, text):
        mid_x = (start[0] + end[0]) / 2.0
        mid_y = (start[1] + end[1]) / 2.0

        ha = "center"
        dx = 0.0
        dy = 0.0

        if abs(start[1] - end[1]) < 1e-6:
            dy = 2.0
            if start[0] > end[0] and start[0] - end[0] < 20:
                ha = "right"
            elif start[0] < end[0] and end[0] - start[0] < 20:
                ha = "left"
        else:
            dx = 6.0

        ax.text(
            mid_x + dx,
            mid_y + dy,
            text,
            fontsize=8,
            ha=ha,
            color="black",
            fontweight="bold"
        )

    def _finish_plot(fig, ax, title, filename):
        ax.set_title(title)
        ax.set_aspect("equal")
        ax.grid(True, linestyle="--", linewidth=0.3)

        base = os.path.join(dir_result, filename)
        fig.savefig(base + ".png", bbox_inches="tight")
        fig.savefig(base + ".svg", bbox_inches="tight")
        plt.close(fig)

    # -------------------------------------------------------------------------
    # 1) Pipeline map labeled by pipe ID
    # -------------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(10, 8))

    for idx, (pipe_id, pipe) in enumerate(data.pipeline.items(), start=1):
        start = tuple(pipe["from_pos"])
        end = tuple(pipe["to_pos"])

        ax.plot(
            [start[0], end[0]],
            [start[1], end[1]],
            color="#1f77b4",
            linewidth=3,
            alpha=0.5
        )

        _midpoint_label(ax, start, end, str(idx))

    _finish_plot(
        fig,
        ax,
        "Labeled by Pipe ID",
        f"pipeline_id_{data.scenario_name}"
    )

    # -------------------------------------------------------------------------
    # 2) Pipeline map by diameter
    # -------------------------------------------------------------------------
    DN_values = [pipe["DN"] for pipe in data.pipeline.values()]
    min_DN = min(DN_values)
    max_DN = max(DN_values)
    norm_DN = _safe_norm(DN_values)

    fig, ax = plt.subplots(figsize=(10, 8))

    for pipe_id, pipe in data.pipeline.items():
        start = tuple(pipe["from_pos"])
        end = tuple(pipe["to_pos"])
        DN = pipe["DN"]

        lw = _line_width(DN, min_DN, max_DN)
        color = cmap(norm_DN(DN))

        ax.plot(
            [start[0], end[0]],
            [start[1], end[1]],
            color=color,
            linewidth=lw
        )

        _midpoint_label(ax, start, end, f"DN{DN}")

    _finish_plot(
        fig,
        ax,
        "Diameter",
        f"pipeline_diameter_{data.scenario_name}"
    )

    # -------------------------------------------------------------------------
    # Calculate hydraulic plotting values
    # -------------------------------------------------------------------------
    for pipe_id, pipe in data.pipeline.items():
        flow_max = abs(float(pipe["flow_max"]))  # m3/s
        d_i = float(pipe["d_i"]) / 1000.0        # m
        f_i = float(pipe.get("f_fric", data.heat_grid_data["pipe"].get("f_fric", 0.02)))

        area = np.pi * d_i ** 2 / 4.0

        if area > 0.0:
            velocity_max = flow_max / area
        else:
            velocity_max = 0.0

        # Darcy-Weisbach pressure gradient, friction only [Pa/m]
        if d_i > 0.0:
            pressure_drop_max = f_i * rho_f * velocity_max ** 2 / (2.0 * d_i)
        else:
            pressure_drop_max = 0.0

        pipe["velocity_max"] = velocity_max
        pipe["pressure_drop_max"] = pressure_drop_max

    # -------------------------------------------------------------------------
    # 3) Pipeline map by maximum velocity
    # -------------------------------------------------------------------------
    velocity_values = [pipe["velocity_max"] for pipe in data.pipeline.values()]
    min_v = min(velocity_values)
    max_v = max(velocity_values)
    norm_v = _safe_norm(velocity_values)

    fig, ax = plt.subplots(figsize=(10, 8))

    for pipe_id, pipe in data.pipeline.items():
        start = tuple(pipe["from_pos"])
        end = tuple(pipe["to_pos"])
        velocity_max = pipe["velocity_max"]

        lw = _line_width(velocity_max, min_v, max_v)
        color = cmap(norm_v(velocity_max))

        ax.plot(
            [start[0], end[0]],
            [start[1], end[1]],
            color=color,
            linewidth=lw
        )

        _midpoint_label(ax, start, end, f"{velocity_max:.3f}")

    _finish_plot(
        fig,
        ax,
        "Maximum velocity (m/s)",
        f"pipeline_velocity_max_{data.scenario_name}"
    )

    # -------------------------------------------------------------------------
    # 4) Pipeline map by maximum pressure gradient
    # -------------------------------------------------------------------------
    pressure_values = [pipe["pressure_drop_max"] for pipe in data.pipeline.values()]
    min_dp = min(pressure_values)
    max_dp = max(pressure_values)
    norm_dp = _safe_norm(pressure_values)

    fig, ax = plt.subplots(figsize=(10, 8))

    for pipe_id, pipe in data.pipeline.items():
        start = tuple(pipe["from_pos"])
        end = tuple(pipe["to_pos"])
        pressure_drop_max = pipe["pressure_drop_max"]

        lw = _line_width(pressure_drop_max, min_dp, max_dp)
        color = cmap(norm_dp(pressure_drop_max))

        ax.plot(
            [start[0], end[0]],
            [start[1], end[1]],
            color=color,
            linewidth=lw
        )

        _midpoint_label(ax, start, end, f"{pressure_drop_max:.3f}")

    _finish_plot(
        fig,
        ax,
        "Maximum pressure drop (Pa/m)",
        f"pipeline_pressure_drop_max_{data.scenario_name}"
    )

    # -------------------------------------------------------------------------
    # 5) Pipeline map by energy density
    # -------------------------------------------------------------------------
    T_sup_EH = np.asarray(data.heat_grid_data["T_supply_EH"], dtype=float)
    T_ret_EH = np.asarray(data.heat_grid_data["T_return_EH"], dtype=float)
    deltaT_network = T_sup_EH - T_ret_EH

    for pipe_id, pipe in data.pipeline.items():
        flow = np.abs(np.asarray(pipe["flow"], dtype=float))  # m3/s
        length = max(float(pipe["length"]), 1e-12)

        # W = J/s. With hourly timesteps, sum(W) / 1e6 gives MWh.
        energy_total = np.sum(c_f * rho_f * flow * deltaT_network) / 1e6
        pipe["energy_density"] = float(energy_total / length)  # MWh/m

    energy_values = [pipe["energy_density"] for pipe in data.pipeline.values()]
    min_energy = min(energy_values)
    max_energy = max(energy_values)
    norm_energy = _safe_norm(energy_values)

    fig, ax = plt.subplots(figsize=(10, 8))

    for pipe_id, pipe in data.pipeline.items():
        start = tuple(pipe["from_pos"])
        end = tuple(pipe["to_pos"])
        energy_density = pipe["energy_density"]

        lw = _line_width(energy_density, min_energy, max_energy)
        color = cmap(norm_energy(energy_density))

        ax.plot(
            [start[0], end[0]],
            [start[1], end[1]],
            color=color,
            linewidth=lw
        )

        _midpoint_label(ax, start, end, f"{energy_density:.3f}")

    _finish_plot(
        fig,
        ax,
        "Energy density (MWh/m)",
        f"pipeline_energy_density_{data.scenario_name}"
    )

    # -------------------------------------------------------------------------
    # 6) Pipeline map by heat-loss density
    # -------------------------------------------------------------------------
    for pipe_id, pipe in data.pipeline.items():
        length = max(float(pipe["length"]), 1e-12)

        if "heat_loss_density" not in pipe:
            pipe["heat_loss_density"] = (
                    float(np.sum(pipe["heat_loss_pipe"])) / 1000.0 / length
            )  # MWh/m

    heat_loss_density_values = [
        pipe["heat_loss_density"]
        for pipe in data.pipeline.values()
    ]

    min_hl = min(heat_loss_density_values)
    max_hl = max(heat_loss_density_values)
    norm_hl = _safe_norm(heat_loss_density_values)

    fig, ax = plt.subplots(figsize=(10, 8))

    for pipe_id, pipe in data.pipeline.items():
        start = tuple(pipe["from_pos"])
        end = tuple(pipe["to_pos"])
        heat_loss_density = pipe["heat_loss_density"]

        lw = _line_width(heat_loss_density, min_hl, max_hl)
        color = cmap(norm_hl(heat_loss_density))

        ax.plot(
            [start[0], end[0]],
            [start[1], end[1]],
            color=color,
            linewidth=lw
        )

        _midpoint_label(ax, start, end, f"{heat_loss_density:.3f}")

    _finish_plot(
        fig,
        ax,
        "Heat loss density (MWh/m)",
        f"pipeline_heat_loss_density_{data.scenario_name}"
    )

    print("Network plots saved to:", dir_result)

    return data, param

def compute_and_save_network_costs_2leiter(data, param):
    """Compute annualized network costs and save heat_grid_parameters_outputs.json."""

    buildings_connected = [
        b for b in data.district
        if b["buildingFeatures"]["heater"] in ["heat_grid", "heat_grid_SH"]
    ]

    C_substations = 0.0
    for building in buildings_connected:
        if building["buildingFeatures"]["heater"] == "heat_grid_SH":
            substation_capacity = (
                    building["bes_obj"].design_load_heating / 1000.0
            )
        else:
            substation_capacity = (
                    building["bes_obj"].design_load_heating / 1000.0
                    + building["bes_obj"].design_load_dhw / 1000.0
            )
        C_substations += substation_capacity * data.heat_grid_data["C_subst"]

    substation_lifetime = data.heat_grid_data["lifetime_subst"]
    substation_ann_factor = calc_annual_factor(data, substation_lifetime)
    substation_ann_costs = C_substations * substation_ann_factor
    substation_om_costs = len(buildings_connected) * data.heat_grid_data["cost_om_subst"]

    inv_pipes = 0.0
    inv_construction = 0.0
    for pipe in data.pipeline.values():
        DN = pipe["DN"]
        length = pipe["length"]
        inv_pipes += length * param["pipe_dict"][DN]["Pipe Cost (€/m)"] * 2.0
        inv_construction += length * param["pipe_dict"][DN]["Construction Cost (€/m)"]

    pipe_ann_factor = data.heat_grid_data["pipe"]["pipe_ann_factor"]
    pipes_ann_costs = (inv_pipes + inv_construction) * pipe_ann_factor
    pipes_om_costs = (inv_pipes + inv_construction) * data.heat_grid_data["pipe"]["cost_om_pipe"]

    pump_cap = data.heat_grid_data["pump_power_design"]
    inv_pump = pump_cap * data.heat_grid_data["pump"]["inv_pump"]
    pump_ann_costs = inv_pump * data.heat_grid_data["pump"]["pump_ann_factor"]
    pump_om_costs = inv_pump * data.heat_grid_data["pump"]["cost_om_pump"]

    pump_energy_total = float(np.sum(data.heat_grid_data["P_pump"]) / 1000.0)  # kWh/a for hourly timestep
    pump_electricity_costs = pump_energy_total * data.ecoData["price_supply_el_eh"][0]

    network_om_costs = pipes_om_costs + pump_om_costs + substation_om_costs
    network_ann_costs = pipes_ann_costs + pump_ann_costs + substation_ann_costs

    data.heat_grid_data["om_costs"] = network_om_costs
    data.heat_grid_data["ann_costs"] = network_ann_costs

    # -------------------------------------------------------------------------
    # Plot annual network cost stack
    # -------------------------------------------------------------------------
    costs = {
        "Annualized investment for substations": substation_ann_costs,
        "Operation and maintenance cost for substations": substation_om_costs,
        "Annualized investment for pipes": pipes_ann_costs,
        "Operation and maintenance cost for pipes": pipes_om_costs,
        "Annualized investment for the pump": pump_ann_costs,
        "Operation and maintenance cost for the pump": pump_om_costs,
        "Electricity costs for the pump": pump_electricity_costs,
    }

    labels = list(costs.keys())
    values = np.asarray(list(costs.values()), dtype=float)

    x = np.arange(1)

    fig, ax = plt.subplots(figsize=(10, 14))

    cmap = plt.get_cmap("tab20")
    colors = [cmap(i) for i in range(len(labels))]

    bottom = np.zeros_like(x, dtype=float)

    for i, value in enumerate(values):
        ax.bar(
            x,
            value,
            bottom=bottom,
            label=labels[i],
            color=colors[i],
            width=0.8,
        )
        bottom += value

    wrapped_labels = [
        "\n".join(textwrap.wrap(label, width=20))
        for label in labels
    ]

    ax.set_ylabel("Annual costs (€/a)")
    ax.set_title("Annual Cost Stacked Chart")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{data.scenario_name}"])
    ax.legend(
        wrapped_labels,
        bbox_to_anchor=(1.05, 1),
        loc="upper left",
        labelspacing=0.8,
    )

    plt.tight_layout()

    base = os.path.join(
        param["dir_result"],
        f"network_cost_stack_{data.scenario_name}"
    )

    plt.savefig(base + ".png", bbox_inches="tight")
    plt.savefig(base + ".svg", bbox_inches="tight")
    plt.close(fig)

    print("Cost stacked plot of heat grid saved to:", base)


    ###################################################
    #Debug Diagramme
    ###################################################


    # Daten auslesen
    T_supply_EH = data.heat_grid_data["T_supply_EH"]
    T_return_EH = data.heat_grid_data["T_return_EH"]

    # Zeitachse als Index
    time = np.arange(len(T_supply_EH))

    # Speicherpfad
    save_dir = r"S:\districtgenerator\districtgenerator\results\network\district_E_buildings_30_road"
    save_path = os.path.join(save_dir, "temperature_EH.png")

    # Ordner erstellen, falls er noch nicht existiert
    os.makedirs(save_dir, exist_ok=True)

    # Diagramm erstellen
    plt.figure(figsize=(20, 10))

    plt.plot(time, T_supply_EH, color="red", label="T_supply_EH")
    plt.plot(time, T_return_EH, color="blue", label="T_return_EH")

    plt.xlabel("Zeitindex")
    plt.ylabel("Temperatur [°C]")
    plt.title("Verlauf von Vorlauf- und Rücklauftemperatur EH")
    plt.grid(True)
    plt.legend()
    plt.tight_layout()

    # Diagramm speichern
    plt.savefig(save_path, dpi=300, bbox_inches="tight")

    # Diagramm anzeigen
    #plt.show()

    print(f"Diagramm gespeichert unter: {save_path}")

    T_soil_mean = float(np.mean(data.heat_grid_data["T_soil"]))
    T_supply_mean = float(np.mean(data.heat_grid_data["T_supply_EH"]))
    T_return_mean = float(np.mean(data.heat_grid_data["T_return_EH"]))
    total_pipe_length = float(sum(pipe["length"] for pipe in data.pipeline.values()))

    total_net_heat_demand = float(np.sum(param["net_heat_demand"]))
    total_heat_produced_EH = total_net_heat_demand + float(param.get("annual_heat_loss_pos", 0.0))

    results = {
        "model": {
            "value": "simple_merged_2leiter",
            "unit": "-",
            "description": "Merged simple 2-pipe design and operation model"
        },
        "pipe_class": {
            "value": str(param.get("pipe_class", "unknown")),
            "unit": "-",
            "description": "Selected pipe catalogue class"
        },
        "T_soil_mean": {
            "value": T_soil_mean,
            "unit": "°C",
            "description": "Annual average soil temperature"
        },
        "T_supply_mean": {
            "value": T_supply_mean,
            "unit": "°C",
            "description": "Annual average supply temperature at EH"
        },
        "T_return_mean": {
            "value": T_return_mean,
            "unit": "°C",
            "description": "Annual average return temperature at EH calculated by the model"
        },
        "total_pipe_length": {
            "value": total_pipe_length,
            "unit": "m",
            "description": "Sum of all pipe segment lengths"
        },
        "total_heat_produced_EH": {
            "value": total_heat_produced_EH,
            "unit": "kWh",
            "description": "Network demand including substation losses plus positive pipe heat losses"
        },
        "total_net_heat_demand": {
            "value": total_net_heat_demand,
            "unit": "kWh",
            "description": "Heat supplied to substations including substation losses"
        },
        "pump_capacity": {
            "value": float(pump_cap),
            "unit": "kW",
            "description": "Required design pump electrical power"
        },
        "pump_design_head": {
            "value": float(data.heat_grid_data["dp_pump_max"]),
            "unit": "Pa",
            "description": "Required design pump head including safety factor"
        },
        "pump_electricity_consumption": {
            "value": pump_energy_total,
            "unit": "kWh",
            "description": "Annual pump electricity consumption"
        },
        "pump_electricity_consumption_percentage": {
            "value": float(pump_energy_total / max(total_heat_produced_EH, 1e-12) * 100.0),
            "unit": "%",
            "description": "Pump electricity as share of EH heat production"
        },
        "annual_total_heat_loss": {
            "value": float(param.get("annual_heat_loss_pos_total", 0.0)),
            "unit": "kWh",
            "description": "Annual positive heat loss including pipes and substations"
        },
        "annual_pipe_heat_loss": {
            "value": float(param.get("annual_heat_loss_pos", 0.0)),
            "unit": "kWh",
            "description": "Annual positive pipe heat loss"
        },
        "pipes_heat_loss_density": {
            "value": float(param.get("annual_heat_loss_pos", 0.0) * 1000.0 / 8760.0 / max(total_pipe_length, 1e-12)),
            "unit": "W/m",
            "description": "Average positive pipe heat loss density"
        },
        "heat_loss_percentage": {
            "value": float(param.get("annual_heat_loss_pos_total", 0.0) / max(total_heat_produced_EH, 1e-12) * 100.0),
            "unit": "%",
            "description": "Total positive heat loss as share of EH heat production"
        },
        "pipes_heat_loss_percentage": {
            "value": float(param.get("annual_heat_loss_pos", 0.0) / max(total_heat_produced_EH, 1e-12) * 100.0),
            "unit": "%",
            "description": "Positive pipe heat loss as share of EH heat production"
        },
        "substation_ann_costs": {"value": float(substation_ann_costs), "unit": "€", "description": "Annualized substation investment"},
        "substation_om_costs": {"value": float(substation_om_costs), "unit": "€", "description": "Substation O&M costs"},
        "pipes_ann_costs": {"value": float(pipes_ann_costs), "unit": "€", "description": "Annualized pipe investment"},
        "pipes_om_costs": {"value": float(pipes_om_costs), "unit": "€", "description": "Pipe O&M costs"},
        "pump_ann_costs": {"value": float(pump_ann_costs), "unit": "€", "description": "Annualized pump investment"},
        "pump_om_costs": {"value": float(pump_om_costs), "unit": "€", "description": "Pump O&M costs"},
        "pump_electricity_costs": {"value": float(pump_electricity_costs), "unit": "€", "description": "Pump electricity costs"},
        "network_ann_costs": {"value": float(network_ann_costs), "unit": "€", "description": "Total annualized network investment"},
        "network_om_costs": {"value": float(network_om_costs), "unit": "€", "description": "Total network O&M costs"},
        "network_total_costs": {
            "value": float(network_ann_costs + network_om_costs + pump_electricity_costs),
            "unit": "€",
            "description": "Total annual network costs including pump electricity"
        },
    }

    json_path = os.path.join(param["dir_result"], "heat_grid_parameters_outputs.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, ensure_ascii=False)

    print("Output JSON-file saved to:", json_path)
    return data

# Helper functions

def aggregate_mass_flows(network, building_massflow, root="EH1"):
    """Aggregate downstream building mass flows in a tree topology."""

    pipe_massflows = {}

    def dfs(node):
        total_flow = None

        if node in building_massflow:
            total_flow = building_massflow[node].copy()

        for child in network.get(node, []):
            downstream_flow = dfs(child)
            pipe_massflows[(node, child)] = downstream_flow.copy()
            total_flow = downstream_flow.copy() if total_flow is None else total_flow + downstream_flow

        if total_flow is None:
            return np.zeros_like(next(iter(building_massflow.values())))

        return total_flow

    dfs(root)
    return pipe_massflows

def calc_annual_factor(data, life_time):
    """Annualization factor according to the same VDI-2067-style logic."""

    observation_time = data.ecoData["observation_time"]
    interest_rate = data.ecoData["interest_rate"]
    q = 1.0 + interest_rate

    CRF = ((q ** observation_time) * interest_rate) / ((q ** observation_time) - 1.0)
    n = int(math.floor(observation_time / life_time))
    invest_replacements = sum((q ** (-i * life_time)) for i in range(1, n + 1))
    res_value = ((n + 1) * life_time - observation_time) / life_time * (q ** (-observation_time))

    if life_time > observation_time:
        ann_factor = (1.0 - res_value) * CRF
    else:
        ann_factor = (1.0 + invest_replacements - res_value) * CRF

    return ann_factor

# LOCAL LOSSES

def identify_junction_and_bends(data, tol=1e-6):
    """Identify source/end/straight/bend/tee/cross nodes and diameter changes."""

    topology = data.pipeline_topology
    pipes = data.pipeline

    incoming_pipes = {node: [] for node in data.pipeline_nodes.keys()}
    outgoing_pipes = {node: [] for node in data.pipeline_nodes.keys()}

    for pid, p in pipes.items():
        parent = p["from"]
        child = p["to"]
        outgoing_pipes.setdefault(parent, []).append(pid)
        incoming_pipes.setdefault(child, []).append(pid)

    def node_xy(node):
        return tuple(data.pipeline_nodes[node]["pos"])

    def is_collinear(p0, p1, p2):
        v1 = (p1[0] - p0[0], p1[1] - p0[1])
        v2 = (p2[0] - p0[0], p2[1] - p0[1])
        cross = abs(v1[0] * v2[1] - v1[1] * v2[0])
        return cross <= tol

    def angle_between(p0, p1, p2):
        v1 = (p0[0] - p1[0], p0[1] - p1[1])
        v2 = (p2[0] - p0[0], p2[1] - p0[1])
        n1 = math.hypot(*v1)
        n2 = math.hypot(*v2)
        if n1 <= 1e-12 or n2 <= 1e-12:
            return 0.0
        dot = v1[0] * v2[0] + v1[1] * v2[1]
        cosang = max(-1.0, min(1.0, dot / (n1 * n2)))
        return math.degrees(math.acos(cosang))

    def diameter_changed(pid_up, pid_dn):
        try:
            return pipes[pid_dn]["DN"] != pipes[pid_up]["DN"]
        except KeyError:
            return False

    node_type = {}
    pipe_angle = {}
    diameter_change = {}

    for node in data.pipeline_nodes.keys():
        inc = incoming_pipes.get(node, [])
        out = outgoing_pipes.get(node, [])
        deg = len(inc) + len(out)

        if len(inc) == 0:
            node_type[node] = "source"
            continue
        if len(out) == 0:
            node_type[node] = "end"
            continue

        if deg >= 3:
            node_type[node] = "tee" if deg == 3 else "cross"
            p0 = node_xy(node)

            for pid_in in inc:
                p_in = node_xy(pipes[pid_in]["from"])
                for pid_out in out:
                    p_out = node_xy(pipes[pid_out]["to"])
                    pipe_angle[pid_out] = angle_between(p0, p_in, p_out)

            if len(inc) == 1:
                pid_up = inc[0]
                for pid_dn in out:
                    diameter_change[pid_dn] = diameter_changed(pid_up, pid_dn)
            continue

        if len(inc) == 1 and len(out) == 1:
            pid_up = inc[0]
            pid_dn = out[0]
            p_node = node_xy(node)
            p_up = node_xy(pipes[pid_up]["from"])
            p_dn = node_xy(pipes[pid_dn]["to"])

            if is_collinear(p_node, p_up, p_dn):
                node_type[node] = "straight"
                pipe_angle[pid_dn] = 0.0
            else:
                node_type[node] = "bend"
                pipe_angle[pid_dn] = angle_between(p_node, p_up, p_dn)

            diameter_change[pid_dn] = diameter_changed(pid_up, pid_dn)
            continue

        node_type[node] = "unknown"

    return {
        "node_type": node_type,
        "incoming_pipes": incoming_pipes,
        "outgoing_pipes": outgoing_pipes,
        "pipe_angle": pipe_angle,
        "diameter_change": diameter_change,
    }


def compute_zeta_values(data, param, hydraulic_features, angle_branch_threshold=10.0):
    """Compute local hydraulic resistance coefficients zeta per pipe."""

    node_type = hydraulic_features["node_type"]
    incoming_pipes = hydraulic_features["incoming_pipes"]
    outgoing_pipes = hydraulic_features["outgoing_pipes"]
    pipe_angle = hydraulic_features["pipe_angle"]
    diameter_change = hydraulic_features["diameter_change"]

    zeta = {}
    pipes = data.pipeline
    pipe_dict = param["pipe_dict"]
    eps = 1e-12

    for pid, pipe in pipes.items():
        node = pipe["from"]
        ntype = node_type.get(node, "unknown")
        f_i = pipes[pid].get("f_fric", data.heat_grid_data["pipe"].get("f_fric", 0.02))
        d = pipes[pid]["d_i"]  # mm
        DN = pipes[pid]["DN"]

        if ntype in ("source", "end", "straight"):
            zeta_total = 0.0

        elif ntype == "bend":
            ang = pipe_angle.get(pid, 0.0)
            R = pipe_dict[DN].get("Radius (mm)", max(d, 1e-6))
            K1 = -0.000041 * ang ** 2 + 0.0146 * ang + 0.05
            K2 = 0.21 / max((R / d), 1e-12) ** 0.5
            K3 = 1.0
            zeta_U = K1 * K2 * K3
            zeta_R = 0.0175 * f_i * R / d * ang
            zeta_total = 2.0 * (zeta_U + zeta_R)

        elif ntype in ("tee", "cross"):
            inc = incoming_pipes.get(node, [])
            if len(inc) == 0:
                zeta_total = 0.0
            else:
                ang = pipe_angle.get(pid, 0.0)
                pid_up = inc[0]
                flow_child = float(pipe["flow_max"])
                flow_up = float(pipes[pid_up]["flow_max"])
                flow_ratio = np.clip(flow_child / max(flow_up, eps), 0.0, 1.0)

                if ang > angle_branch_threshold:
                    zeta_45_supply = 1.018 * flow_ratio ** 2 - 1.482 * flow_ratio + 0.933
                    zeta_60_supply = 1.098 * flow_ratio ** 2 - 1.334 * flow_ratio + 1.000
                    zeta_90_supply = 0.920 * flow_ratio ** 2 - 0.611 * flow_ratio + 0.995
                    zeta_45_return = -1.333 * flow_ratio ** 2 + 2.509 * flow_ratio - 0.846
                    zeta_60_return = -1.576 * flow_ratio ** 2 + 3.097 * flow_ratio - 0.883
                    zeta_90_return = -1.313 * flow_ratio ** 2 + 3.193 * flow_ratio - 0.995

                    ang_eff = min(max(ang, 45.0), 90.0)
                    zeta_supply = np.interp(ang_eff, [45.0, 60.0, 90.0], [zeta_45_supply, zeta_60_supply, zeta_90_supply])
                    zeta_return = np.interp(ang_eff, [45.0, 60.0, 90.0], [zeta_45_return, zeta_60_return, zeta_90_return])
                    zeta_total = float(zeta_supply + zeta_return)
                else:
                    fr = 1.0 - flow_ratio
                    zeta_supply = 1.0045 * fr ** 2 - 0.6116 * fr + 0.0925
                    pids = outgoing_pipes.get(node, [])
                    branch_pids = [p for p in pids if p != pid]
                    branch_angles = [pipe_angle.get(p, 45.0) for p in branch_pids]
                    ang_a = max(branch_angles) if branch_angles else 45.0
                    ang_eff = min(max(ang_a, 45.0), 90.0)

                    zeta_45_return = -1.852 * fr ** 2 + 1.118 * fr + 0.056
                    zeta_60_return = -1.250 * fr ** 2 + 0.911 * fr + 0.144
                    zeta_90_return = 0.031 * fr ** 2 + 0.486 * fr + 0.079
                    zeta_return = np.interp(ang_eff, [45.0, 60.0, 90.0], [zeta_45_return, zeta_60_return, zeta_90_return])
                    zeta_total = float(zeta_supply + zeta_return)
        else:
            zeta_total = 0.0

        # Diameter change loss.
        if diameter_change.get(pid, False):
            inc = incoming_pipes.get(node, [])
            if inc:
                pid_up = inc[0]
                d_child = pipes[pid]["d_i"]
                d_up = pipes[pid_up]["d_i"]

                if d_up > d_child:
                    area_ratio = (d_child / d_up) ** 2
                    kontraktionszahl = 0.49 * area_ratio ** 2 - 0.12 * area_ratio + 0.624
                    zeta_supply = 1.5 * ((1.0 - kontraktionszahl) / kontraktionszahl) ** 2
                    zeta_return = (1.0 - (d_child / d_up) ** 2) ** 2
                    zeta_total += zeta_supply + zeta_return

                elif d_up < d_child:
                    zeta_supply = ((d_child / d_up) ** 2 - 1.0) ** 2
                    area_ratio = (d_up / d_child) ** 2
                    kontraktionszahl = 0.49 * area_ratio ** 2 - 0.12 * area_ratio + 0.624
                    zeta_up = 1.5 * ((1.0 - kontraktionszahl) / kontraktionszahl) ** 2
                    v_up = pipes[pid_up]["flow_max"] / max(np.pi * (d_up / 1000.0) ** 2 / 4.0, eps)
                    v_dn = pipes[pid]["flow_max"] / max(np.pi * (d_child / 1000.0) ** 2 / 4.0, eps)
                    zeta_return = zeta_up * (v_up / max(v_dn, eps)) ** 2
                    zeta_total += zeta_supply + zeta_return

        zeta[pid] = float(max(zeta_total, 0.0))
        data.pipeline[pid]["zeta"] = zeta[pid]

    return data, zeta

# ============================================================
# Heat exchanger helper functions for house substations
# ============================================================

def hx_lmtd(dT1, dT2):
    """
    Logarithmic mean temperature difference.

    dT1 = T_primary_in  - T_secondary_out
    dT2 = T_primary_out - T_secondary_in
    """

    dT1 = float(dT1)
    dT2 = float(dT2)

    eps = 1e-9

    if not np.isfinite(dT1) or not np.isfinite(dT2):
        return np.nan

    if dT1 <= eps or dT2 <= eps:
        return np.nan

    if abs(dT1 - dT2) < 1e-7:
        return 0.5 * (dT1 + dT2)

    return (dT1 - dT2) / np.log(dT1 / dT2)

def hx_calc_UA_design(
        Q_design_W,
        T_primary_in_design,
        T_primary_out_design,
        T_secondary_in_design,
        T_secondary_out_design):

    """
    Calculate the heat-exchanger design UA value from one design point.
    This function assumes an ideal counterflow heat exchanger.
    """

    dT1 = T_primary_in_design - T_secondary_out_design
    dT2 = T_primary_out_design - T_secondary_in_design

    DTlm = hx_lmtd(dT1, dT2)

    return Q_design_W / DTlm

def hx_primary_return_and_flow(
        Q_W,
        T_primary_in,
        T_secondary_in,
        T_secondary_out,
        UA,
        c_p,
        eps=1e-6,
        tol_T=1e-2,
        max_iter=30):
    """
    Solve primary return temperature and primary mass flow
    for a counterflow heat exchanger.

    Primary side:
        T_primary_in  = network supply
        T_primary_out = network return, solved here

    Secondary side:
        T_secondary_in  = building return or cold water
        T_secondary_out = building supply or DHW temperature
    """

    Q_W = float(Q_W)

    # No heat demand: no primary mass flow.
    # Return temperature is not physically defined, so use supply as neutral value.
    if Q_W <= 0.0:
        return T_primary_in, 0.0

    # The temperature difference at the hot end of the counterflow heat exchanger.
    dT1 = T_primary_in - T_secondary_out

    # Search range for primary return temperature
    lo = T_secondary_in + eps
    hi = T_primary_in - eps

    def q_model(T_primary_out):
        dT2 = T_primary_out - T_secondary_in
        DTlm = hx_lmtd(dT1, dT2)
        return UA * DTlm

    # Bisection solver with early stopping
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        Q_mid = q_model(mid)

        if Q_mid < Q_W:
            lo = mid
        else:
            hi = mid

        if hi - lo < tol_T:
            break

    T_primary_out = 0.5 * (lo + hi)

    dT_primary = max(T_primary_in - T_primary_out, eps)

    m_dot_primary = Q_W / (c_p * dT_primary)

    return T_primary_out, m_dot_primary

def prepare_result_folder(data, param):
    dir_dia = os.path.join(data.resultPath, "network")
    os.makedirs(dir_dia, exist_ok=True)

    topology = data.heat_grid_data["topology_option"]
    result_folder = f"{data.scenario_name}_{topology}_simple_2leiter"
    dir_result = os.path.join(dir_dia, result_folder)
    os.makedirs(dir_result, exist_ok=True)

    param["dir_result"] = dir_result
    return dir_result

def _topology_parent_order(topo, root):
    parent = {}
    order = []

    def dfs(node):
        order.append(node)
        for ch in topo.get(node, []):
            parent[ch] = node
            dfs(ch)

    dfs(root)
    return parent, order


def _path_to_root(order, parent, root):
    path_to_root = {}
    for n in order:
        path = []
        cur = n
        while cur != root:
            par = parent[cur]
            path.append((par, cur))
            cur = par
        path_to_root[n] = path
    return path_to_root

def _save_debug_outputs(data, param):
    pipeline_path = os.path.join(param["dir_result"], "pipeline_simple_2leiter.json")
    with open(pipeline_path, "w", encoding="utf-8") as f:
        json.dump(to_jsonable(data.pipeline), f, indent=4, ensure_ascii=False)

    hydraulic_path = os.path.join(param["dir_result"], "local_hydraulic_loss_data.json")
    export_data = {
        "node_type": param.get("hydraulic_features", {}).get("node_type", {}),
        "pipe_angle": param.get("hydraulic_features", {}).get("pipe_angle", {}),
        "diameter_change": param.get("hydraulic_features", {}).get("diameter_change", {}),
        "zeta": param.get("zeta", {}),
    }
    with open(hydraulic_path, "w", encoding="utf-8") as f:
        json.dump(to_jsonable(export_data), f, indent=4, ensure_ascii=False)

    print("Debug outputs saved to:", param["dir_result"])


def to_jsonable(obj):
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, tuple):
        return list(obj)
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (np.integer, np.floating)):
        return obj.item()
    return obj
