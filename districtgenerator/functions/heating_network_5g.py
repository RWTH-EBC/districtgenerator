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
5G district-heating network model.

The warm pipe and cold pipe temperatures are fixed in this model.

Decentral reversible heat pumps in every connected building provide space heating,
domestic hot water, and active cooling.

Pipe heat losses/gains are calculated from the prescribed warm/cold pipe
temperatures only in timesteps where a pipe segment carries mass flow.
They do not feed back into the pipe temperatures.

The model workflow is:
    1) prepare building loads and temperature requirements
    2) calculate building mass flows
    3) aggregate signed pipe mass flows for every time step
    4) size pipe diameters
    5) compute local hydraulic losses
    6) calculate pipe heat losses and gains
    7) calculate the signed residual thermal demand at the energy hub
    8) compute pump power and network costs
"""

# MAIN WORKFLOW

def network_5G(data, compute_costs=True, save_debug=False):
    """
    Simple 2-pipe network model for 5G bidirectional networks.

    Assumptions
    -----------
    - Warm and cold pipe temperatures are fixed.
    - Decentral reversible heat pumps are the interface between the
      building circuits and the 5G pipe pair.
    - Pipe heat losses/gains are counted only in timesteps where a pipe
      segment carries mass flow. They do not change the fixed pipe
      temperatures along the network.
    """

    # 1) Load parameters
    data, param = load_parameter_5g_fixed(data)
    prepare_result_folder(data, param)

    # 2) Initialize network pipes
    data.pipeline = {}
    initialize_pipeline_from_topology(data)

    # 3) Select pipe class based on maximum fixed warm-pipe temperature
    update_pipe_data_selection(data, param, float(np.max(param["T_warm_fixed_5g"])))

    # 4) Calculate building and pipe mass flows
    data, param = calc_flow_5g_fixed(data, param)

    # 5) Select pipe diameters
    data, param = calc_diameter_5g_fixed(data, param)

    # 6) Local hydraulic losses
    hydraulic_features = identify_junction_and_bends(data)
    data, zeta = compute_zeta_values(data, param, hydraulic_features)
    param["zeta"] = zeta
    param["hydraulic_features"] = hydraulic_features

    # 7) Calculate pipe heat losses from network-level temperatures
    data, param = calc_heat_loss_pipe_5g_fixed(data, param)

    # 8) Calculate signed residual thermal demand at the Energy Hub
    data, param = compute_eh_residual_thermal_5g(data, param)

    # 9) Pump power
    data, param = compute_pump_power_5g_fixed(data, param)

    # 10) Plot network results
    plot_network_results_5g_fixed(data, param)

    if save_debug:
        _save_debug_outputs(data, param)

    if compute_costs:
        compute_and_save_network_costs_5g_fixed(data, param)

    return data, param

def load_parameter_5g_fixed(data):
    """
    Prepare building loads, useful-side temperature requirements,
    decentralized heat-pump electricity demand, signed 5G network loads,
    and fixed warm/cold pipe temperatures for the 5G model.

    Model assumptions
    -----------------
    - Only buildings with heater == "heat_grid" are connected.
    - Warm pipe and cold pipe temperatures are fixed.
    - Heating mode:
          warm pipe -> decentralized HP -> cold pipe
    - Cooling mode:
          building cooling loop -> reversible HP -> cold/warm pipe pair
    - Decentral reversible heat pumps exchange heat between the building
      circuits and the fixed-temperature 5G pipe pair.
    - Pipe heat losses/gains are calculated later and do not feed back into
      the pipe temperatures.
    """

    param = {}

    heat_grid_data = data.heat_grid_data
    heat_grid_data["network_model"] = "5g_fixed"
    T_len = len(data.heat_grid_data["T_soil"])

    # Helper: scalar turned into a full profile
    def _as_profile(value, name):
        if isinstance(value, dict):
            value = value["value"]
        array = np.asarray(value, dtype=float)
        if array.shape == ():
            array = np.full(T_len, float(array), dtype=float)
        if len(array) != T_len:
            raise ValueError(
                f"{name} must be scalar or have length {T_len}, "
                f"but has length {len(array)}."
            )
        return array

    # Fixed 5G pipe temperatures and basic assumptions
    T_warm_fixed = _as_profile(heat_grid_data.get("T_warm_5G", 20.0),"T_warm_5G")
    T_cold_fixed = _as_profile(heat_grid_data.get("T_cold_5G", 10.0),"T_cold_5G")
    deltaT_5g = T_warm_fixed - T_cold_fixed

    param["T_warm_fixed_5g"] = T_warm_fixed
    param["T_cold_fixed_5g"] = T_cold_fixed
    param["deltaT_5g"] = deltaT_5g

    data.heat_grid_data["T_warm_fixed_5g"] = T_warm_fixed
    data.heat_grid_data["T_cold_fixed_5g"] = T_cold_fixed

    h_loss_subst = float(heat_grid_data.get("h_loss_subst", 0.0))
    heat_loss_substation = np.zeros(T_len, dtype=float)

    # Decentral heat-pump and building-side assumptions.
    T_dhw_required = float(data.decentral_device_data["TES_DHW"]["T_DHW_needed"])
    T_cold_water = 10.0

    # Reversible decentralized heat pump for the 5G network.
    hp_5g_data = data.decentral_device_data.get("HP_5G", {})

    # Building-side temperatures for active cooling.
    T_cooling_supply_sec = 12.0
    T_cooling_return_sec = 18.0

    # Temperature approaches used to estimate refrigerant-side temperatures.
    dT_HP_evap_heating = 2.0
    dT_HP_cond_heating = 2.0
    dT_HP_evap_cooling = 2.0
    dT_HP_cond_cooling = 2.0

    hp_5g_grade = float(hp_5g_data.get("grade", 0.4))
    COP_min = 1.01
    COP_max = 8.0

    # Build fast lookup: building position -> node id
    node_lookup = {
        tuple(node_info["pos"]): key
        for key, node_info in data.pipeline_nodes.items()
    }

    T_sec_supply_SH_by_node = {}
    T_sec_return_SH_by_node = {}

    T_sec_supply_DHW_by_node = {}
    T_sec_return_DHW_by_node = {}

    T_sec_supply_COOL_by_node = {}
    T_sec_return_COOL_by_node = {}

    T_sink_supply_SH_by_node = {}
    T_sink_supply_DHW_by_node = {}

    Q_SH_by_node = {}
    Q_DHW_by_node = {}
    Q_heat_useful_by_node = {}
    Q_cooling_by_node = {}

    Q_heat_from_network_by_node = {}
    Q_cooling_to_network_by_node = {}
    Q_5g_signed_by_node = {}

    P_HP_decentral_by_node = {}
    P_backup_decentral_by_node = {}
    COP_SH_by_node = {}
    COP_DHW_by_node = {}
    EER_COOL_by_node = {}

    # District-level profiles
    net_useful_heat_demand = np.zeros(T_len, dtype=float)
    net_cooling_demand = np.zeros(T_len, dtype=float)

    net_heat_extraction_5g = np.zeros(T_len, dtype=float)
    net_heat_rejection_5g = np.zeros(T_len, dtype=float)
    net_thermal_balance_5g = np.zeros(T_len, dtype=float)

    net_decentral_HP_el = np.zeros(T_len, dtype=float)
    net_decentral_backup_el = np.zeros(T_len, dtype=float)

    invalid_5g_heaters = sorted({
        building["buildingFeatures"]["heater"]
        for building in data.district
        if building["buildingFeatures"]["heater"] in ("heat_grid_OEB", "heat_grid_BEB")
    })

    if invalid_5g_heaters:
        raise ValueError(
            "The 5G network model only supports heater='heat_grid' for connected buildings. "
            f"Unsupported 5G heat-grid variants found: {invalid_5g_heaters}. "
            "Use the conventional 2-pipe model for heat_grid_OEB and heat_grid_BEB."
        )

    # Building loop
    for building in data.district:

        heater = building["buildingFeatures"]["heater"]

        if heater != "heat_grid":
            continue

        pos_building = tuple(building["buildingFeatures"]["position"])
        node_key = node_lookup.get(pos_building)

        if node_key is None:
            print(f"WARNUNG: Gebäude mit node_key {node_key} konnte nicht gefunden werden und wurde übersprungen! [1]")
            continue

        buildings_heating_curve = building["envelope"].heating_curve["unclustered"]

        if data.heat_grid_data["enable_low_temp_measures"] == True:
            Ts_sec_SH = np.asarray(buildings_heating_curve["Ts_curve_reduced"], dtype=float)
            Tr_sec_SH = np.asarray(buildings_heating_curve["Tr_curve_reduced"], dtype=float)

        else:
            Ts_sec_SH = np.asarray(buildings_heating_curve["Ts_curve"], dtype=float)
            Tr_sec_SH = np.asarray(buildings_heating_curve["Tr_curve"], dtype=float)

        # HP sink temperatures required by the building circuits.
        T_sink_SH = Ts_sec_SH
        T_sink_DHW = np.full(T_len, T_dhw_required, dtype=float)

        sh_load = np.asarray(building["user"].heat, dtype=float) / 1000.0
        dhw_load = np.asarray(building["user"].dhw, dtype=float) / 1000.0

        cooling_profile = getattr(building["user"], "cooling", np.zeros(T_len, dtype=float))
        cooling_load = np.asarray(cooling_profile, dtype=float) / 1000.0

        # Useful building heat loads before substation losses.
        Q_SH_useful = sh_load.copy()
        Q_DHW_useful = dhw_load.copy()

        # Loads covered by the 5G building heat pumps, including substation losses.
        Q_SH = Q_SH_useful * (1.0 + h_loss_subst / 100.0)
        Q_DHW = Q_DHW_useful * (1.0 + h_loss_subst / 100.0)
        Q_heat_useful = Q_SH_useful + Q_DHW_useful
        Q_cooling = cooling_load

        heat_loss_substation += Q_heat_useful * h_loss_subst / 100.0

        # Decentral HP COP and network-side heat extraction

        COP_SH = calc_decentral_hp_cop_heating(
            T_sink_C=T_sink_SH,
            T_warm_in_C=T_warm_fixed,
            T_cold_out_C=T_cold_fixed,
            T_len=T_len,
            hp_5g_grade=hp_5g_grade,
            COP_min=COP_min,
            COP_max=COP_max,
            dT_HP_evap_heating=dT_HP_evap_heating,
            dT_HP_cond_heating=dT_HP_cond_heating
        )

        COP_DHW = calc_decentral_hp_cop_heating(
            T_sink_C=T_sink_DHW,
            T_warm_in_C=T_warm_fixed,
            T_cold_out_C=T_cold_fixed,
            T_len=T_len,
            hp_5g_grade=hp_5g_grade,
            COP_min=COP_min,
            COP_max=COP_max,
            dT_HP_evap_heating=dT_HP_evap_heating,
            dT_HP_cond_heating=dT_HP_cond_heating
        )

        EER_COOL = calc_decentral_hp_eer_cooling(
            T_cooling_supply_C=T_cooling_supply_sec,
            T_warm_out_C=T_warm_fixed,
            T_len=T_len,
            hp_5g_grade=hp_5g_grade,
            COP_min=COP_min,
            COP_max=COP_max,
            dT_HP_evap_cooling=dT_HP_evap_cooling,
            dT_HP_cond_cooling=dT_HP_cond_cooling
        )

        hp_5g_heat_cap = (building["bes_obj"].bivalent_load_heating / 1000.0
                * (1.0 + h_loss_subst / 100.0))
        hp_5g_cool_cap = float(np.max(Q_cooling)) if np.any(Q_cooling > 0.0) else 0.0
        hp_5g_capacity = max(hp_5g_heat_cap, hp_5g_cool_cap)

        Q_heat_total = Q_SH + Q_DHW
        Q_HP_heat_total = np.minimum(Q_heat_total, hp_5g_capacity)

        # The integrated electric backup covers heating/DHW peaks above the
        # bivalent HP_5G capacity. SH is prioritized; remaining HP capacity is
        # used for DHW.
        Q_HP_SH = np.minimum(Q_SH, Q_HP_heat_total)
        Q_HP_DHW = np.minimum(Q_DHW, np.maximum(Q_HP_heat_total - Q_HP_SH, 0.0))
        Q_backup_SH = Q_SH - Q_HP_SH
        Q_backup_DHW = Q_DHW - Q_HP_DHW
        P_backup_5g = Q_backup_SH + Q_backup_DHW

        # Electric power consumption
        P_HP_SH = np.divide(Q_HP_SH, COP_SH, out=np.zeros_like(Q_HP_SH))
        P_HP_DHW = np.divide(Q_HP_DHW, COP_DHW, out=np.zeros_like(Q_HP_DHW))
        P_HP_cooling = np.divide(Q_cooling, EER_COOL, out=np.zeros_like(Q_cooling))

        # Heat extracted from 5G network
        Q_from_network_SH = Q_HP_SH - P_HP_SH
        Q_from_network_DHW = Q_HP_DHW - P_HP_DHW

        Q_heat_from_network = Q_from_network_SH + Q_from_network_DHW
        P_HP_decentral = P_HP_SH + P_HP_DHW + P_HP_cooling + P_backup_5g

        # Heat rejected to the 5G network by active reversible cooling.
        Q_cooling_to_network = Q_cooling + P_HP_cooling

        # Signed network load:
        # positive = heat extracted from network
        # negative = heat injected into network
        Q_5g_signed = Q_heat_from_network - Q_cooling_to_network

        # Store node values
        T_sec_supply_SH_by_node[node_key] = Ts_sec_SH
        T_sec_return_SH_by_node[node_key] = Tr_sec_SH

        T_sec_supply_DHW_by_node[node_key] = np.full(T_len, T_dhw_required, dtype=float)
        T_sec_return_DHW_by_node[node_key] = np.full(T_len, T_cold_water, dtype=float)

        T_sec_supply_COOL_by_node[node_key] = np.full(T_len, T_cooling_supply_sec, dtype=float)
        T_sec_return_COOL_by_node[node_key] = np.full(T_len, T_cooling_return_sec, dtype=float)

        T_sink_supply_SH_by_node[node_key] = T_sink_SH
        T_sink_supply_DHW_by_node[node_key] = T_sink_DHW

        Q_SH_by_node[node_key] = Q_SH
        Q_DHW_by_node[node_key] = Q_DHW
        Q_heat_useful_by_node[node_key] = Q_heat_useful
        Q_cooling_by_node[node_key] = Q_cooling

        Q_heat_from_network_by_node[node_key] = Q_heat_from_network
        Q_cooling_to_network_by_node[node_key] = Q_cooling_to_network
        Q_5g_signed_by_node[node_key] = Q_5g_signed

        P_HP_decentral_by_node[node_key] = P_HP_decentral
        P_backup_decentral_by_node[node_key] = P_backup_5g
        COP_SH_by_node[node_key] = COP_SH
        COP_DHW_by_node[node_key] = COP_DHW
        EER_COOL_by_node[node_key] = EER_COOL

        # Aggregate district-level profiles
        net_useful_heat_demand += Q_heat_useful
        net_cooling_demand += Q_cooling

        net_heat_extraction_5g += Q_heat_from_network
        net_heat_rejection_5g += Q_cooling_to_network
        net_thermal_balance_5g += Q_5g_signed

        net_decentral_HP_el += P_HP_decentral
        net_decentral_backup_el += P_backup_5g

        # Store on building object for later result extraction/debugging
        building["user"].net_5g_signed_demand = Q_5g_signed
        building["user"].net_5g_heat_extraction = Q_heat_from_network
        building["user"].net_5g_cooling_rejection = Q_cooling_to_network
        building["user"].decentral_5g_HP_el = P_HP_decentral
        building["user"].decentral_5g_backup_el = P_backup_5g

    # Store into param
    param["T_sec_supply_SH_by_node"] = T_sec_supply_SH_by_node
    param["T_sec_return_SH_by_node"] = T_sec_return_SH_by_node
    param["T_sec_supply_DHW_by_node"] = T_sec_supply_DHW_by_node
    param["T_sec_return_DHW_by_node"] = T_sec_return_DHW_by_node
    param["T_sec_supply_COOL_by_node"] = T_sec_supply_COOL_by_node
    param["T_sec_return_COOL_by_node"] = T_sec_return_COOL_by_node
    param["T_sink_supply_SH_by_node"] = T_sink_supply_SH_by_node
    param["T_sink_supply_DHW_by_node"] = T_sink_supply_DHW_by_node
    param["Q_SH_by_node"] = Q_SH_by_node
    param["Q_DHW_by_node"] = Q_DHW_by_node
    param["Q_heat_useful_by_node"] = Q_heat_useful_by_node
    param["Q_cooling_by_node"] = Q_cooling_by_node
    param["Q_heat_from_network_by_node"] = Q_heat_from_network_by_node
    param["Q_cooling_to_network_by_node"] = Q_cooling_to_network_by_node
    param["Q_5g_signed_by_node"] = Q_5g_signed_by_node
    param["P_HP_decentral_by_node"] = P_HP_decentral_by_node
    param["P_backup_decentral_by_node"] = P_backup_decentral_by_node
    param["COP_SH_by_node"] = COP_SH_by_node
    param["COP_DHW_by_node"] = COP_DHW_by_node
    param["EER_COOL_by_node"] = EER_COOL_by_node
    param["heat_loss_substation"] = heat_loss_substation
    param["net_useful_heat_demand_5g"] = net_useful_heat_demand
    param["net_cooling_demand_5g"] = net_cooling_demand
    param["net_heat_extraction_5g"] = net_heat_extraction_5g
    param["net_heat_rejection_5g"] = net_heat_rejection_5g
    param["net_thermal_balance_5g"] = net_thermal_balance_5g
    param["net_decentral_HP_el_5g"] = net_decentral_HP_el
    param["net_decentral_backup_el_5g"] = net_decentral_backup_el

    # Store also on data.heat_grid_data for plotting / later coupling
    data.heat_grid_data["net_useful_heat_demand_5g"] = net_useful_heat_demand
    data.heat_grid_data["net_cooling_demand_5g"] = net_cooling_demand
    data.heat_grid_data["net_heat_extraction_5g"] = net_heat_extraction_5g
    data.heat_grid_data["net_heat_rejection_5g"] = net_heat_rejection_5g
    data.heat_grid_data["net_thermal_balance_5g"] = net_thermal_balance_5g
    data.heat_grid_data["net_decentral_HP_el_5g"] = net_decentral_HP_el
    data.heat_grid_data["net_decentral_backup_el_5g"] = net_decentral_backup_el

    # Annualization factors
    pipe_lifetime = heat_grid_data["pipe"]["pipe_lifetime"]
    heat_grid_data["pipe"]["pipe_ann_factor"] = calc_annual_factor(data, pipe_lifetime)

    pump_lifetime = heat_grid_data["pump"]["pump_lifetime"]
    heat_grid_data["pump"]["pump_ann_factor"] = calc_annual_factor(data, pump_lifetime)

    # Decentral 5G HP annualization factor for later network/device costing
    hp_lifetime = data.decentral_device_data.get("HP_5G", {}).get("life_time", None)
    param["decentral_HP_5G_ann_factor"] = calc_annual_factor(data, hp_lifetime)

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

    # Thermal conductivity of PE pipe material [W/(m K)]
    k_PE = heat_grid_data["k_PE"]

    for DN, pipe in pipe_dict.items():
        if pipe_class == "PE":
            di = float(pipe["Inner diameter (pipe) (mm)"])
            d_o = float(pipe["Outer diameter (pipe) (mm)"])
            # The PE outer diameter is directly in contact with the soil.
            Da = d_o
            a = np.log(4.0 * Z_c / (Da / 1000.0))
            # Thermal resistance of the PE pipe wall.
            beta = k_soil / k_PE * np.log(d_o / di)

        else:
            da = float(pipe["Outer diameter (pipe) (mm)"])
            Da = float(pipe["Outer diameter (case) (mm)"])
            a = np.log(4.0 * Z_c / (Da / 1000.0))
            beta = k_soil / k_pipe * np.log(Da / da)

        ks_heating_network = (a + beta + b) ** -1
        ka_heating_network = (a + beta - b) ** -1

        pipe["symmetrical heat loss factor"] = ks_heating_network
        pipe["antisymmetrical heat loss factor"] = ka_heating_network

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
                "flow_max_abs": 0.0,
                "massflow_5g": np.zeros(T_len, dtype=float),
                "massflow_max_abs_5g": 0.0,
            }

def calc_flow_5g_fixed(data, param):
    """
    Calculate building and pipe mass flows for the 5G fixed-temperature model.

    Sign convention
    ---------------
    positive mass flow:
        warm pipe -> building -> cold pipe

    negative mass flow:
        cold pipe -> building -> warm pipe
    """

    c_f = float(data.heat_grid_data["fluid"]["c_f"])      # J/(kg K)
    rho_f = float(data.heat_grid_data["fluid"]["rho_f"])  # kg/m3

    T_warm_fixed = np.asarray(param["T_warm_fixed_5g"], dtype=float)
    T_cold_fixed = np.asarray(param["T_cold_fixed_5g"], dtype=float)

    param["building_massflow_heat_5g"] = {}
    param["building_massflow_cool_5g"] = {}
    param["building_massflow_signed_5g"] = {}
    param["building_massflow_max_heat_5g"] = {}
    param["building_massflow_max_cool_5g"] = {}
    param["building_massflow_max_abs_5g"] = {}
    param["deltaT_heating_5g"] = {}
    param["deltaT_cooling_5g"] = {}

    for n in param["Q_5g_signed_by_node"].keys():

        Q_heat = np.asarray(param["Q_heat_from_network_by_node"][n], dtype=float)
        Q_cool = np.asarray(param["Q_cooling_to_network_by_node"][n], dtype=float)

        # Remove numerical noise
        Q_heat_eff = np.where(Q_heat < 0.01, 0.0, Q_heat)
        Q_cool_eff = np.where(Q_cool < 0.01, 0.0, Q_cool)

        deltaT_heat = T_warm_fixed - T_cold_fixed
        deltaT_cool = T_warm_fixed - T_cold_fixed

        if np.any(deltaT_heat <= 1e-9):
            raise ValueError(f"Invalid heating deltaT at node {n}: ")

        if np.any(deltaT_cool <= 1e-9):
            raise ValueError(f"Invalid cooling deltaT at node {n}: ")

        # Building-side mass flows
        m_heat_raw = Q_heat_eff * 1000.0 / (c_f * deltaT_heat)
        m_cool_raw = Q_cool_eff * 1000.0 / (c_f * deltaT_cool)

        m_heat_max = (float(np.max(m_heat_raw)) if np.any(m_heat_raw > 0.0) else 0.0)
        m_cool_max = (float(np.max(m_cool_raw)) if np.any(m_cool_raw > 0.0) else 0.0)

        # No minimum flow is imposed in the 5G model because flow direction is
        # determined by the local heating/cooling balance.
        m_heat = m_heat_raw
        m_cool = m_cool_raw

        # Signed net mass flow at the building connection.
        m_signed = m_heat - m_cool

        param["building_massflow_heat_5g"][n] = m_heat
        param["building_massflow_cool_5g"][n] = m_cool
        param["building_massflow_signed_5g"][n] = m_signed

        param["building_massflow_max_heat_5g"][n] = m_heat_max
        param["building_massflow_max_cool_5g"][n] = m_cool_max
        param["building_massflow_max_abs_5g"][n] = (
            float(np.max(np.abs(m_signed)))
            if np.any(np.abs(m_signed) > 0.0)
            else 0.0
        )

        param["deltaT_heating_5g"][n] = deltaT_heat
        param["deltaT_cooling_5g"][n] = deltaT_cool

    # Aggregate building flows into pipe flows
    pipe_massflows = aggregate_mass_flows(data.pipeline_topology, param["building_massflow_signed_5g"], root="EH1")
    param["pipe_massflows_5g"] = pipe_massflows

    for (parent, child), massflow_array in pipe_massflows.items():

        pipe_id = f"{parent}->{child}"

        massflow_array = np.asarray(massflow_array, dtype=float)

        # Signed volume flow [m3/s]
        flow_array = massflow_array / rho_f

        data.pipeline[pipe_id]["massflow_5g"] = massflow_array
        data.pipeline[pipe_id]["flow"] = flow_array

        data.pipeline[pipe_id]["massflow_max_abs_5g"] = (float(np.max(np.abs(massflow_array))) if np.any(np.abs(massflow_array) > 0.0) else 0.0)
        data.pipeline[pipe_id]["flow_max_abs"] = (float(np.max(np.abs(flow_array))) if np.any(np.abs(flow_array) > 0.0) else 0.0)
        data.pipeline[pipe_id]["flow_max"] = (float(np.max(flow_array)) if np.any(flow_array > 1e-12) else 0.0)
        data.pipeline[pipe_id]["flow_min"] = (float(np.min(flow_array)) if np.any(flow_array < -1e-12) else 0.0)

    return data, param

def calc_diameter_5g_fixed(data, param):
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

        # 5G bidirectional flow: use maximum absolute volume flow
        V_max = float(pipe.get("flow_max_abs", 0.0))  # volumetric flow [m³/s]

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

def calc_heat_loss_pipe_5g_fixed(data, param):
    """
    Calculate pipe heat losses/gains for the 5G fixed-temperature model.

    Heat exchange with the soil is only counted in timesteps where the pipe
    segment carries mass flow. In inactive timesteps, the segment is treated
    as not actively temperature-maintained.

    For each pipe segment i:

        Q_warm,i = UA_i * (T_warm,i - T_soil)
        Q_cold,i = UA_i * (T_cold,i - T_soil)

        Q_total,i = Q_warm,i + Q_cold,i

    Sign convention
    ---------------
    Positive values:
        heat loss from pipe to soil

    Negative values:
        heat gain from soil into pipe
    """

    k_soil = float(data.heat_grid_data["k_soil"])
    T_soil = np.asarray(data.heat_grid_data["T_soil"], dtype=float)

    T_warm_default = np.asarray(param["T_warm_fixed_5g"], dtype=float)
    T_cold_default = np.asarray(param["T_cold_fixed_5g"], dtype=float)

    heat_exchange_pipe_5g = {}
    heat_exchange_warm_pipe_5g = {}
    heat_exchange_cold_pipe_5g = {}

    network_warm_exchange = np.zeros_like(T_soil, dtype=float)
    network_cold_exchange = np.zeros_like(T_soil, dtype=float)
    network_total_exchange = np.zeros_like(T_soil, dtype=float)

    for pid, pipe in data.pipeline.items():

        parent = pipe["from"]
        child = pipe["to"]
        DN = pipe["DN"]

        ks = param["pipe_dict"][DN]["symmetrical heat loss factor"]

        # UA of one pipe line for this segment [W/K]
        UA = 2.0 * np.pi * k_soil * ks * pipe["length"]

        Q_warm = UA * (T_warm_default - T_soil) / 1000.0  # kW
        Q_cold = UA * (T_cold_default - T_soil) / 1000.0  # kW

        active_pipe = np.abs(np.asarray(pipe["massflow_5g"], dtype=float)) > 1e-9
        Q_warm = np.where(active_pipe, Q_warm, 0.0)
        Q_cold = np.where(active_pipe, Q_cold, 0.0)

        Q_total = Q_warm + Q_cold

        pipe["heat_exchange_warm_5g"] = Q_warm
        pipe["heat_exchange_cold_5g"] = Q_cold
        pipe["heat_exchange_pipe_5g"] = Q_total

        pipe["heat_loss_pipe"] = Q_total

        heat_exchange_pipe_5g[(parent, child)] = Q_total
        heat_exchange_warm_pipe_5g[(parent, child)] = Q_warm
        heat_exchange_cold_pipe_5g[(parent, child)] = Q_cold

        network_warm_exchange += Q_warm
        network_cold_exchange += Q_cold
        network_total_exchange += Q_total

        length = max(float(pipe["length"]), 1e-12)

        pipe["heat_exchange_density_5g"] = (float(np.sum(Q_total)) / 1000.0 / length)  # MWh/m if timestep = 1 h
        pipe["heat_exchange_warm_density_5g"] = (float(np.sum(Q_warm)) / 1000.0 / length)
        pipe["heat_exchange_cold_density_5g"] = (float(np.sum(Q_cold)) / 1000.0 / length)

    # Network-level signed heat exchange
    heat_loss_pos_network = np.maximum(network_total_exchange, 0.0)
    heat_gain_pos_network = np.maximum(-network_total_exchange, 0.0)

    warm_loss_pos_network = np.maximum(network_warm_exchange, 0.0)
    warm_gain_pos_network = np.maximum(-network_warm_exchange, 0.0)

    cold_loss_pos_network = np.maximum(network_cold_exchange, 0.0)
    cold_gain_pos_network = np.maximum(-network_cold_exchange, 0.0)

    param["heat_exchange_pipe_5g"] = heat_exchange_pipe_5g
    param["heat_exchange_warm_pipe_5g"] = heat_exchange_warm_pipe_5g
    param["heat_exchange_cold_pipe_5g"] = heat_exchange_cold_pipe_5g

    param["network_warm_exchange_5g"] = network_warm_exchange
    param["network_cold_exchange_5g"] = network_cold_exchange
    param["network_total_exchange_5g"] = network_total_exchange

    param["heat_loss_pos_network_5g"] = heat_loss_pos_network
    param["heat_gain_pos_network_5g"] = heat_gain_pos_network

    param["warm_loss_pos_network_5g"] = warm_loss_pos_network
    param["warm_gain_pos_network_5g"] = warm_gain_pos_network

    param["cold_loss_pos_network_5g"] = cold_loss_pos_network
    param["cold_gain_pos_network_5g"] = cold_gain_pos_network

    # Annual sums
    param["annual_heat_exchange_pipes_signed_5g"] = float(np.sum(network_total_exchange))
    param["annual_heat_loss_pos_5g"] = float(np.sum(heat_loss_pos_network))
    param["annual_heat_gain_pos_5g"] = float(np.sum(heat_gain_pos_network))
    param["annual_warm_pipe_exchange_signed_5g"] = float(np.sum(network_warm_exchange))
    param["annual_cold_pipe_exchange_signed_5g"] = float(np.sum(network_cold_exchange))
    param["annual_warm_pipe_loss_pos_5g"] = float(np.sum(warm_loss_pos_network))
    param["annual_cold_pipe_gain_pos_5g"] = float(np.sum(cold_gain_pos_network))

    # Optional substation losses, normally already included in building loads
    heat_loss_substation = np.asarray(param.get("heat_loss_substation", np.zeros_like(T_soil)), dtype=float)
    param["annual_heat_loss_pos_total_5g"] = (float(np.sum(heat_loss_substation)) + param["annual_heat_loss_pos_5g"])

    # Store on data for plots / exports
    data.heat_grid_data["network_warm_exchange_5g"] = network_warm_exchange
    data.heat_grid_data["network_cold_exchange_5g"] = network_cold_exchange
    data.heat_grid_data["network_total_exchange_5g"] = network_total_exchange

    data.heat_grid_data["total_heat_loss_5g_pos"] = heat_loss_pos_network
    data.heat_grid_data["total_heat_gain_5g_pos"] = heat_gain_pos_network

    # Compatibility only.
    data.heat_grid_data["total_losses_heating_network"] = (heat_loss_substation + heat_loss_pos_network)
    data.heat_grid_data["total_losses_cooling_network"] = heat_gain_pos_network

    return data, param

def compute_eh_residual_thermal_5g(data, param):
    """
    Calculate the signed thermal demand at the 5G Energy Hub
    positive: Energy Hub must supply heat to the 5G network
    negative: Energy Hub must remove heat from the 5G network
    """

    net_thermal_balance_5g = np.asarray(param["net_thermal_balance_5g"], dtype=float)
    network_total_exchange_5g = np.asarray(param["network_total_exchange_5g"], dtype=float)
    eh_residual_thermal_5g = net_thermal_balance_5g + network_total_exchange_5g

    param["eh_residual_thermal_5g"] = eh_residual_thermal_5g
    data.heat_grid_data["eh_residual_thermal_5g"] = eh_residual_thermal_5g

    return data, param

def compute_pump_power_5g_fixed(data, param):
    """
    Compute equivalent pump power and pump head profiles for the
    5G fixed-temperature model.

    Pump electricity is calculated as the sum of hydraulic work in all
    active pipe segments and building/EH interfaces. Hydraulic losses
    depend on abs(flow), not on signed flow.

    The pressure-head profile is kept as a critical-path indicator for
    reporting and compatibility. Exact 5G pump placement and pressure
    control are not resolved.
    """

    rho = float(data.heat_grid_data["fluid"]["rho_f"])
    nu_f = float(data.heat_grid_data["fluid"]["nu_f"])
    eta_pump = float(data.heat_grid_data["pump"]["eta_pump"])
    dp_substation = float(data.heat_grid_data.get("dp_substation", 0.0))
    dp_energy_hub = float(data.heat_grid_data.get("dp_energy_hub", 0.0))

    root = "EH1"
    topo = data.pipeline_topology
    pipe_dict = param["pipe_dict"]
    T_len = len(data.heat_grid_data["T_soil"])
    building_nodes = list(param["building_massflow_signed_5g"].keys())

    parent, order = _topology_parent_order(topo, root)
    pair_to_pid = {(p["from"], p["to"]): pid for pid, p in data.pipeline.items()}
    path_to_root = _path_to_root(order, parent, root)

    P_pump = np.zeros(T_len, dtype=float)       # W
    dp_pump = np.zeros(T_len, dtype=float)      # Pa

    for pipe in data.pipeline.values():
        pipe["dp_friction_5g"] = np.zeros(T_len, dtype=float)
        pipe["dp_local_5g"] = np.zeros(T_len, dtype=float)
        pipe["dp_pipe_5g"] = np.zeros(T_len, dtype=float)
        pipe["pump_power_pipe_5g"] = np.zeros(T_len, dtype=float)

    for t in range(T_len):

        pipe_dp = {}
        P_pipes_t = 0.0

        # Pipe pressure losses and pipe hydraulic power
        for pid, pipe in data.pipeline.items():
            DN = pipe["DN"]
            d_i = pipe_dict[DN]["Inner diameter (pipe) (mm)"] / 1000.0
            rough = pipe_dict[DN]["Roughness (mm)"] / 1000.0
            L = float(pipe["length"])
            # 5G: hydraulics use absolute value
            V = abs(float(pipe["flow"][t]))  # m3/s

            if V <= 1e-12:
                pipe_dp[pid] = 0.0
                continue

            A = np.pi * d_i**2 / 4.0
            v = V / A
            Re = v * d_i / nu_f if nu_f > 0 else 0.0
            f = fluids.friction.friction_factor(Re=Re, eD=rough / d_i)

            # factor 2.0 for warm + cold pipe friction
            dp_friction = 2.0 * f * (L / d_i) * (rho * v**2 / 2.0)
            dp_local = pipe.get("zeta", 0.0) * (rho * v**2 / 2.0)
            dp_pipe = dp_friction + dp_local

            pipe_dp[pid] = dp_pipe

            pipe["dp_friction_5g"][t] = dp_friction
            pipe["dp_local_5g"][t] = dp_local
            pipe["dp_pipe_5g"][t] = dp_pipe

            # Equivalent distributed pipe pumping power
            P_pipe = V * dp_pipe / eta_pump
            pipe["pump_power_pipe_5g"][t] = P_pipe

            P_pipes_t += P_pipe

        # Critical-path pressure-head indicator
        dp_crit = 0.0

        for n in building_nodes:
            if n not in path_to_root:
                continue
            dp_path = sum(pipe_dp[pair_to_pid[(par, ch)]] for par, ch in path_to_root[n])
            dp_crit = max(dp_crit, dp_path + dp_substation)

        dp_total = dp_crit + dp_energy_hub
        dp_pump[t] = dp_total

        # Substation pressure losses
        P_substations_t = 0.0

        for n in building_nodes:

            m_net = abs(float(param["building_massflow_signed_5g"][n][t]))
            V_sub = m_net / rho
            P_substations_t += V_sub * dp_substation / eta_pump

        # Energy hub pressure losses
        V_EH = sum(
            abs(float(pipe["flow"][t]))
            for pipe in data.pipeline.values()
            if pipe["from"] == root
        )

        P_EH_t = V_EH * dp_energy_hub / eta_pump

        # Total equivalent pump power
        P_pump[t] = P_pipes_t + P_substations_t + P_EH_t

    safety_factor = float(data.heat_grid_data.get("pump_safety_factor", 1.3))

    data.heat_grid_data["P_pump"] = P_pump
    data.heat_grid_data["pump_power_design"] = (float(np.max(P_pump)) / 1000.0 * safety_factor)
    data.heat_grid_data["dp_pump_max"] = (float(np.max(dp_pump)) * safety_factor)

    param["dp_pump_profile_5g"] = dp_pump
    param["P_pump_profile_5g"] = P_pump

    # Compatibility alias for existing result/export functions
    param["dp_pump_profile"] = dp_pump

    return data, param

#################################################################################################
#################################################################################################
#################################################################################################

# COSTS AND OUTPUTS

def plot_network_results_5g_fixed(data, param):
    """
    Generate network plots for the 5G fixed-temperature model.

    Plots:
        1) pipe ID map
        2) pipe diameter map
        3) maximum absolute velocity map
        4) maximum pressure-gradient map
        5) transported energy-density map
        6) signed heat-exchange-density map

    For hydraulic plots, abs(flow) is used.
    For energy density, abs(flow) is used because the map should show
    transported thermal energy, independent of direction.
    """

    dir_result = param["dir_result"]
    output_name = getattr(data, "output_scenario_name", data.scenario_name)
    os.makedirs(dir_result, exist_ok=True)

    rho_f = float(data.heat_grid_data["fluid"]["rho_f"])
    c_f = float(data.heat_grid_data["fluid"]["c_f"])
    nu_f = float(data.heat_grid_data["fluid"]["nu_f"])

    pipe_dict = param["pipe_dict"]

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
        "5G network - labeled by Pipe ID",
        f"pipeline_id_5g_{output_name}"
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
        "5G network - diameter",
        f"pipeline_diameter_5g_{output_name}"
    )

    # -------------------------------------------------------------------------
    # Calculate hydraulic plotting values
    # -------------------------------------------------------------------------
    for pipe_id, pipe in data.pipeline.items():

        # 5G: signed flow -> use maximum absolute volumetric flow
        flow_max_abs = abs(float(pipe.get("flow_max_abs", 0.0)))  # m3/s
        DN = pipe["DN"]
        d_i = pipe_dict[DN]["Inner diameter (pipe) (mm)"] / 1000.0
        rough = pipe_dict[DN]["Roughness (mm)"] / 1000.0

        area = np.pi * d_i**2 / 4.0

        if area > 0.0:
            velocity_max = flow_max_abs / area
        else:
            velocity_max = 0.0

        if velocity_max > 0.0 and d_i > 0.0:
            Re = velocity_max * d_i / nu_f if nu_f > 0.0 else 0.0
            f_i = fluids.friction.friction_factor(
                Re=Re,
                eD=rough / d_i
            )
            pressure_drop_max = f_i * rho_f * velocity_max**2 / (2.0 * d_i)
        else:
            f_i = 0.0
            pressure_drop_max = 0.0

        pipe["velocity_max_5g"] = float(velocity_max)
        pipe["pressure_drop_max_5g"] = float(pressure_drop_max)

        # Compatibility names, falls alte Exportfunktionen darauf zugreifen
        pipe["velocity_max"] = float(velocity_max)
        pipe["pressure_drop_max"] = float(pressure_drop_max)

    # -------------------------------------------------------------------------
    # 3) Pipeline map by maximum absolute velocity
    # -------------------------------------------------------------------------
    velocity_values = [
        pipe["velocity_max_5g"]
        for pipe in data.pipeline.values()
    ]

    min_v = min(velocity_values)
    max_v = max(velocity_values)
    norm_v = _safe_norm(velocity_values)

    fig, ax = plt.subplots(figsize=(10, 8))

    for pipe_id, pipe in data.pipeline.items():
        start = tuple(pipe["from_pos"])
        end = tuple(pipe["to_pos"])
        velocity_max = pipe["velocity_max_5g"]

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
        "5G network - maximum absolute velocity (m/s)",
        f"pipeline_velocity_max_5g_{output_name}"
    )

    # -------------------------------------------------------------------------
    # 4) Pipeline map by maximum pressure gradient
    # -------------------------------------------------------------------------
    pressure_values = [
        pipe["pressure_drop_max_5g"]
        for pipe in data.pipeline.values()
    ]

    min_dp = min(pressure_values)
    max_dp = max(pressure_values)
    norm_dp = _safe_norm(pressure_values)

    fig, ax = plt.subplots(figsize=(10, 8))

    for pipe_id, pipe in data.pipeline.items():
        start = tuple(pipe["from_pos"])
        end = tuple(pipe["to_pos"])
        pressure_drop_max = pipe["pressure_drop_max_5g"]

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
        "5G network - maximum pressure gradient (Pa/m)",
        f"pipeline_pressure_drop_max_5g_{output_name}"
    )

    # -------------------------------------------------------------------------
    # 5) Pipeline map by transported energy density
    # -------------------------------------------------------------------------
    T_warm = np.asarray(param["T_warm_fixed_5g"], dtype=float)
    T_cold = np.asarray(param["T_cold_fixed_5g"], dtype=float)

    deltaT_5g = T_warm - T_cold

    for pipe_id, pipe in data.pipeline.items():

        flow_abs = np.abs(np.asarray(pipe["flow"], dtype=float))  # m3/s
        length = max(float(pipe["length"]), 1e-12)

        # W = J/s.
        # For hourly timesteps, sum(W) / 1e6 gives MWh.
        energy_total = np.sum(c_f * rho_f * flow_abs * deltaT_5g) / 1e6
        pipe["energy_density_5g"] = float(energy_total / length)

        # Compatibility name
        pipe["energy_density"] = pipe["energy_density_5g"]

    energy_values = [pipe["energy_density_5g"] for pipe in data.pipeline.values()]
    min_energy = min(energy_values)
    max_energy = max(energy_values)
    norm_energy = _safe_norm(energy_values)

    fig, ax = plt.subplots(figsize=(10, 8))

    for pipe_id, pipe in data.pipeline.items():
        start = tuple(pipe["from_pos"])
        end = tuple(pipe["to_pos"])
        energy_density = pipe["energy_density_5g"]

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
        "5G network - transported energy density (MWh/m)",
        f"pipeline_energy_density_5g_{output_name}"
    )

    # -------------------------------------------------------------------------
    # 6) Pipeline map by signed heat-exchange density
    # -------------------------------------------------------------------------
    for pipe_id, pipe in data.pipeline.items():
        length = max(float(pipe["length"]), 1e-12)

        if "heat_exchange_density_5g" not in pipe:

            if "heat_exchange_pipe_5g" in pipe:
                pipe["heat_exchange_density_5g"] = (
                        float(np.sum(pipe["heat_exchange_pipe_5g"]))
                        / 1000.0
                        / length
                )

            elif "heat_loss_pipe" in pipe:
                pipe["heat_exchange_density_5g"] = (
                        float(np.sum(pipe["heat_loss_pipe"]))
                        / 1000.0
                        / length
                )

            else:
                pipe["heat_exchange_density_5g"] = 0.0

        # Compatibility name
        pipe["heat_loss_density"] = pipe["heat_exchange_density_5g"]

    heat_exchange_density_values = [
        pipe["heat_exchange_density_5g"]
        for pipe in data.pipeline.values()
    ]

    min_hx = min(heat_exchange_density_values)
    max_hx = max(heat_exchange_density_values)
    norm_hx = _safe_norm(heat_exchange_density_values)

    fig, ax = plt.subplots(figsize=(10, 8))

    for pipe_id, pipe in data.pipeline.items():
        start = tuple(pipe["from_pos"])
        end = tuple(pipe["to_pos"])
        heat_exchange_density = pipe["heat_exchange_density_5g"]

        lw = _line_width(heat_exchange_density, min_hx, max_hx)
        color = cmap(norm_hx(heat_exchange_density))

        ax.plot(
            [start[0], end[0]],
            [start[1], end[1]],
            color=color,
            linewidth=lw
        )

        _midpoint_label(ax, start, end, f"{heat_exchange_density:.3f}")

    _finish_plot(
        fig,
        ax,
        "5G network - signed heat exchange density (MWh/m)",
        f"pipeline_heat_exchange_density_5g_{output_name}"
    )

    print("5G network plots saved to:", dir_result)

    return data, param

def compute_and_save_network_costs_5g_fixed(data, param):
    """
    Compute annualized 5G network costs and save
    heat_grid_parameters_outputs.json.

    Cost scope
    ----------
    Included:
        - decentralized reversible 5G heat pumps
        - warm/cold pipes
        - construction
        - network pumps
        - pump electricity

    Not included here:
        - central energy hub device costs

    Those should be handled in the device/energy-system optimization.
    """

    # Connected buildings
    buildings_connected = [
        b for b in data.district
        if b["buildingFeatures"]["heater"] == "heat_grid"
    ]

    # Decentralized 5G heat-pump sizing
    hp_5g_capacity_total = 0.0
    hp_5g_backup_capacity_total = 0.0

    h_loss_subst = float(data.heat_grid_data.get("h_loss_subst", 0.0))
    hp_5g_backup_safety_factor = 1.2

    for building in buildings_connected:

        sh_load = np.asarray(building["user"].heat, dtype=float) / 1000.0
        dhw_load = np.asarray(building["user"].dhw, dtype=float) / 1000.0
        heat_load = (sh_load + dhw_load) * (1.0 + h_loss_subst / 100.0)

        cooling_profile = getattr(
            building["user"],
            "cooling",
            np.zeros(len(data.heat_grid_data["T_soil"]), dtype=float)
        )

        cool_cap = float(np.max(np.asarray(cooling_profile, dtype=float))) / 1000.0

        heat_hp_cap = (building["bes_obj"].bivalent_load_heating / 1000.0
                * (1.0 + h_loss_subst / 100.0))
        hp_5g_capacity = max(heat_hp_cap, cool_cap)
        hp_5g_backup_capacity = (
                max(float(np.max(heat_load)) - hp_5g_capacity, 0.0)
                * hp_5g_backup_safety_factor)

        hp_5g_capacity_total += hp_5g_capacity
        hp_5g_backup_capacity_total += hp_5g_backup_capacity

    # Decentralized 5G heat-pump costs
    hp_data = data.decentral_device_data["HP_5G"]

    inv_hp_5g_subsidized = hp_5g_capacity_total * hp_data["inv_var"]
    inv_hp_5g_unsubsidized = hp_5g_capacity_total * hp_data["inv_base"]

    hp_5g_ann_factor = param.get(
        "decentral_HP_5G_ann_factor",
        calc_annual_factor(data, hp_data["life_time"])
    )

    hp_5g_ann_costs = inv_hp_5g_subsidized * hp_5g_ann_factor
    hp_5g_om_costs = inv_hp_5g_unsubsidized * hp_data.get("cost_om", 0.0)
    hp_5g_om_costs += hp_5g_capacity_total * hp_data.get("cap_fee", 0.0)

    # Pipe costs
    inv_pipes = 0.0
    inv_construction = 0.0
    for pipe in data.pipeline.values():
        DN = pipe["DN"]
        length = float(pipe["length"])
        inv_pipes += (length * param["pipe_dict"][DN]["Pipe Cost (€/m)"] * 2.0)
        inv_construction += length * param["pipe_dict"][DN]["Construction Cost (€/m)"]


    pipe_ann_factor = data.heat_grid_data["pipe"]["pipe_ann_factor"]
    pipes_ann_costs = (inv_pipes + inv_construction) * pipe_ann_factor
    pipes_om_costs = (inv_pipes + inv_construction) * data.heat_grid_data["pipe"]["cost_om_pipe"]

    # Pump costs
    pump_cap = float(data.heat_grid_data["pump_power_design"])  # kW
    inv_pump = pump_cap * data.heat_grid_data["pump"]["inv_pump"]
    pump_ann_costs = (inv_pump * data.heat_grid_data["pump"]["pump_ann_factor"])
    pump_om_costs = (inv_pump * data.heat_grid_data["pump"]["cost_om_pump"])

    pump_energy_total = (float(np.sum(data.heat_grid_data["P_pump"])) / 1000.0)
    pump_electricity_costs = pump_energy_total * data.ecoData["price_supply_el_eh"][0]

    # Total network costs
    network_om_costs_without_HP_5G = pipes_om_costs + pump_om_costs
    network_ann_costs_without_HP_5G = pipes_ann_costs + pump_ann_costs
    network_om_costs = network_om_costs_without_HP_5G + hp_5g_om_costs
    network_ann_costs = network_ann_costs_without_HP_5G + hp_5g_ann_costs
    network_total_costs = network_ann_costs + network_om_costs + pump_electricity_costs

    data.heat_grid_data["HP_5G_capacity"] = hp_5g_capacity_total
    data.heat_grid_data["HP_5G_backup_capacity"] = hp_5g_backup_capacity_total
    data.heat_grid_data["HP_5G_ann_costs"] = hp_5g_ann_costs
    data.heat_grid_data["HP_5G_om_costs"] = hp_5g_om_costs
    data.heat_grid_data["ann_costs_without_HP_5G"] = network_ann_costs_without_HP_5G
    data.heat_grid_data["om_costs_without_HP_5G"] = network_om_costs_without_HP_5G
    data.heat_grid_data["om_costs"] = network_om_costs
    data.heat_grid_data["ann_costs"] = network_ann_costs
    data.heat_grid_data["network_total_costs"] = network_total_costs

    # ------------------------------------------------------------------
    # Plot annual network cost stack
    # ------------------------------------------------------------------
    output_name = getattr(data, "output_scenario_name", data.scenario_name)

    costs = {
        "Annualized investment for decentralized 5G heat pumps": hp_5g_ann_costs,
        "Maintenance cost for decentralized 5G heat pumps": hp_5g_om_costs,
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
    ax.set_title("Annual Cost Stacked Chart - 5G fixed network")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{output_name}"])
    ax.legend(
        wrapped_labels,
        bbox_to_anchor=(1.05, 1),
        loc="upper left",
        labelspacing=0.8,
    )

    plt.tight_layout()

    base = os.path.join(
        param["dir_result"],
        f"network_cost_stack_5g_{output_name}"
    )

    plt.savefig(base + ".png", bbox_inches="tight")
    plt.savefig(base + ".svg", bbox_inches="tight")
    plt.close(fig)

    print("Cost stacked plot of 5G heat grid saved to:", base)

    # Temperature plot: warm/cold/soil
    T_warm = np.asarray(param["T_warm_fixed_5g"], dtype=float)
    T_cold = np.asarray(param["T_cold_fixed_5g"], dtype=float)
    T_soil = np.asarray(data.heat_grid_data["T_soil"], dtype=float)

    time = np.arange(len(T_warm))

    fig, ax = plt.subplots(figsize=(20, 10))

    ax.plot(time, T_warm, color="red", label="T_warm_5g")
    ax.plot(time, T_cold, color="blue", label="T_cold_5g")
    ax.plot(time, T_soil, color="brown", label="T_soil", alpha=0.7)

    ax.set_xlabel("Time index")
    ax.set_ylabel("Temperature [°C]")
    ax.set_title("5G fixed pipe temperatures and soil temperature")
    ax.grid(True)
    ax.legend()
    plt.tight_layout()

    temperature_plot_path = os.path.join(
        param["dir_result"],
        f"temperature_5g_{output_name}.png"
    )

    plt.savefig(temperature_plot_path, dpi=300, bbox_inches="tight")
    plt.close(fig)

    print("5G temperature diagram saved to:", temperature_plot_path)

    # Aggregate technical outputs
    total_pipe_length = float(sum(pipe["length"] for pipe in data.pipeline.values()))
    total_useful_heat_demand_5g = float(np.sum(param.get("net_useful_heat_demand_5g", 0.0)))
    total_cooling_demand_5g = float(np.sum(param.get("net_cooling_demand_5g", 0.0)))
    total_heat_extraction_5g = float(np.sum(param.get("net_heat_extraction_5g", 0.0)))
    total_heat_rejection_5g = float(np.sum(param.get("net_heat_rejection_5g", 0.0)))
    total_thermal_balance_5g = float(np.sum(param.get("net_thermal_balance_5g", 0.0)))
    total_decentral_HP_el_5g = float(np.sum(param.get("net_decentral_HP_el_5g", 0.0)))
    total_decentral_backup_el_5g = float(np.sum(param.get("net_decentral_backup_el_5g", 0.0)))

    eh_residual_thermal_5g = np.asarray(param["eh_residual_thermal_5g"], dtype=float)

    total_EH_heat_supply_5g = float(np.sum(np.maximum(eh_residual_thermal_5g, 0.0)))
    total_EH_heat_rejection_5g = float(np.sum(np.maximum(-eh_residual_thermal_5g, 0.0)))
    total_building_exchange_5g = total_heat_extraction_5g + total_heat_rejection_5g

    annual_heat_exchange_signed_5g = float(param.get("annual_heat_exchange_pipes_signed_5g", 0.0))
    annual_heat_loss_pos_5g = float(param.get("annual_heat_loss_pos_5g", 0.0))
    annual_heat_gain_pos_5g = float(param.get("annual_heat_gain_pos_5g", 0.0))
    annual_warm_pipe_exchange_signed_5g = float(param.get("annual_warm_pipe_exchange_signed_5g", 0.0))
    annual_cold_pipe_exchange_signed_5g = float(param.get("annual_cold_pipe_exchange_signed_5g", 0.0))

    data.heat_grid_data["HP_5G_capacity"] = float(hp_5g_capacity_total)
    data.heat_grid_data["HP_5G_backup_capacity"] = float(hp_5g_backup_capacity_total)
    data.heat_grid_data["HP_5G_ann_costs"] = float(hp_5g_ann_costs)
    data.heat_grid_data["HP_5G_om_costs"] = float(hp_5g_om_costs)

    # JSON output
    results = {
        "model": {
            "value": "5g_fixed",
            "unit": "-",
            "description": "5G fixed-temperature warm/cold pipe network model"
        },
        "pipe_class": {
            "value": str(param.get("pipe_class", "unknown")),
            "unit": "-",
            "description": "Selected pipe catalogue class"
        },
        "number_of_connected_buildings": {
            "value": int(len(buildings_connected)),
            "unit": "-",
            "description": "Buildings with buildingFeatures['heater'] == 'heat_grid'"
        },
        "T_soil_mean": {
            "value": float(np.mean(T_soil)),
            "unit": "°C",
            "description": "Annual average soil temperature"
        },
        "T_warm_mean_5g": {
            "value": float(np.mean(T_warm)),
            "unit": "°C",
            "description": "Annual average fixed warm pipe temperature"
        },
        "T_cold_mean_5g": {
            "value": float(np.mean(T_cold)),
            "unit": "°C",
            "description": "Annual average fixed cold pipe temperature"
        },
        "deltaT_5g_mean": {
            "value": float(np.mean(T_warm - T_cold)),
            "unit": "K",
            "description": "Annual average warm/cold pipe temperature difference"
        },
        "total_pipe_length": {
            "value": total_pipe_length,
            "unit": "m",
            "description": "Sum of all pipe segment lengths"
        },
        "total_useful_heat_demand_5g": {
            "value": total_useful_heat_demand_5g,
            "unit": "kWh",
            "description": "Useful SH + DHW demand covered by decentralized 5G heat pumps"
        },
        "total_cooling_demand_5g": {
            "value": total_cooling_demand_5g,
            "unit": "kWh",
            "description": "Useful cooling demand covered by reversible decentralized 5G heat pumps"
        },
        "total_heat_extraction_from_network_5g": {
            "value": total_heat_extraction_5g,
            "unit": "kWh",
            "description": "Heat extracted from the warm pipe by decentralized heat pumps"
        },
        "total_heat_rejection_to_network_5g": {
            "value": total_heat_rejection_5g,
            "unit": "kWh",
            "description": "Heat rejected to the warm pipe by reversible decentralized 5G heat pumps in cooling mode"
        },
        "total_signed_building_thermal_balance_5g": {
            "value": total_thermal_balance_5g,
            "unit": "kWh",
            "description": "Positive = net building heat extraction, negative = net building heat rejection"
        },
        "total_decentral_HP_electricity_5g": {
            "value": total_decentral_HP_el_5g,
            "unit": "kWh",
            "description": "Electricity demand of reversible decentralized 5G heat pumps, including integrated electric backup"
        },
        "total_decentral_HP_backup_electricity_5g": {
            "value": total_decentral_backup_el_5g,
            "unit": "kWh",
            "description": "Electricity demand of the integrated zero-cost electric backup of decentralized 5G heat pumps"
        },
        "annual_pipe_heat_exchange_signed_5g": {
            "value": annual_heat_exchange_signed_5g,
            "unit": "kWh",
            "description": "Signed pipe heat exchange with soil; positive = loss to soil, negative = gain from soil"
        },
        "annual_pipe_heat_loss_pos_5g": {
            "value": annual_heat_loss_pos_5g,
            "unit": "kWh",
            "description": "Positive part of annual pipe heat exchange"
        },
        "annual_pipe_heat_gain_pos_5g": {
            "value": annual_heat_gain_pos_5g,
            "unit": "kWh",
            "description": "Negative part of pipe heat exchange reported as positive heat gain"
        },
        "annual_warm_pipe_exchange_signed_5g": {
            "value": annual_warm_pipe_exchange_signed_5g,
            "unit": "kWh",
            "description": "Signed warm pipe heat exchange with soil"
        },
        "annual_cold_pipe_exchange_signed_5g": {
            "value": annual_cold_pipe_exchange_signed_5g,
            "unit": "kWh",
            "description": "Signed cold pipe heat exchange with soil"
        },
        "total_EH_heat_supply_5g": {
            "value": total_EH_heat_supply_5g,
            "unit": "kWh",
            "description": "Positive residual thermal energy that must be supplied at the EH including pipe heat exchange"
        },
        "total_EH_heat_rejection_5g": {
            "value": total_EH_heat_rejection_5g,
            "unit": "kWh",
            "description": "Negative residual thermal energy that must be rejected/removed at the EH including pipe heat exchange"
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
            "description": "Annual network pump electricity consumption"
        },
        "pump_electricity_consumption_percentage_of_building_exchange": {
            "value": float(
                pump_energy_total
                / max(total_building_exchange_5g, 1e-12)
                * 100.0
            ),
            "unit": "%",
            "description": "Pump electricity as share of total building-side network heat exchange"
        },
        "pipes_heat_exchange_density_signed": {
            "value": float(
                annual_heat_exchange_signed_5g
                * 1000.0
                / 8760.0
                / max(total_pipe_length, 1e-12)
            ),
            "unit": "W/m",
            "description": "Average signed pipe heat exchange density"
        },
        "pipes_heat_loss_density_pos": {
            "value": float(
                annual_heat_loss_pos_5g
                * 1000.0
                / 8760.0
                / max(total_pipe_length, 1e-12)
            ),
            "unit": "W/m",
            "description": "Average positive pipe heat loss density"
        },
        "pipes_heat_gain_density_pos": {
            "value": float(
                annual_heat_gain_pos_5g
                * 1000.0
                / 8760.0
                / max(total_pipe_length, 1e-12)
            ),
            "unit": "W/m",
            "description": "Average positive pipe heat gain density"
        },
        "pipes_ann_costs": {
            "value": float(pipes_ann_costs),
            "unit": "€",
            "description": "Annualized pipe investment"
        },
        "pipes_om_costs": {
            "value": float(pipes_om_costs),
            "unit": "€",
            "description": "Pipe O&M costs"
        },
        "pump_ann_costs": {
            "value": float(pump_ann_costs),
            "unit": "€",
            "description": "Annualized pump investment"
        },
        "pump_om_costs": {
            "value": float(pump_om_costs),
            "unit": "€",
            "description": "Pump O&M costs"
        },
        "pump_electricity_costs": {
            "value": float(pump_electricity_costs),
            "unit": "€",
            "description": "Pump electricity costs"
        },
        "network_ann_costs_without_HP_5G": {
            "value": float(network_ann_costs_without_HP_5G),
            "unit": "€",
            "description": "Annualized network investment without decentralized 5G heat pumps"
        },
        "network_om_costs_without_HP_5G": {
            "value": float(network_om_costs_without_HP_5G),
            "unit": "€",
            "description": "Network O&M costs without decentralized 5G heat pumps"
        },
        "network_ann_costs": {
            "value": float(network_ann_costs),
            "unit": "€",
            "description": "Total annualized network investment"
        },
        "network_om_costs": {
            "value": float(network_om_costs),
            "unit": "€",
            "description": "Total network O&M costs"
        },
        "network_total_costs": {
            "value": float(network_total_costs),
            "unit": "€",
            "description": "Total annual network costs including pump electricity"
        },
        "decentral_HP_5G_capacity": {
            "value": float(hp_5g_capacity_total),
            "unit": "kW",
            "description": "Total thermal capacity of decentralized 5G heat pumps"
        },
        "decentral_HP_5G_backup_capacity": {
            "value": float(hp_5g_backup_capacity_total),
            "unit": "kW",
            "description": "Total thermal capacity of integrated zero-cost electric backup for decentralized 5G heat pumps"
        },
        "decentral_HP_5G_ann_costs": {
            "value": float(hp_5g_ann_costs),
            "unit": "€",
            "description": "Annualized investment of decentralized 5G heat pumps"
        },
        "decentral_HP_5G_om_costs": {
            "value": float(hp_5g_om_costs),
            "unit": "€",
            "description": "Annual O&M costs of decentralized 5G heat pumps"
        },
    }

    json_path = os.path.join(param["dir_result"], "heat_grid_parameters_outputs.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, ensure_ascii=False)

    print("Output JSON-file saved to:", json_path)
    return data

# Helper functions

def calc_decentral_hp_cop_heating(
        T_sink_C,
        T_warm_in_C,
        T_cold_out_C,
        T_len,
        hp_5g_grade,
        COP_min,
        COP_max,
        dT_HP_evap_heating,
        dT_HP_cond_heating
):
    """
    Carnot-based COP for decentralized 5G heat pumps in heating mode.

    The evaporator temperature is approximated below the mean 5G source
    temperature, while the condenser temperature is approximated above the
    building-side sink temperature.
    """
    T_sink_C = np.asarray(T_sink_C, dtype=float)
    T_warm_in_C = np.asarray(T_warm_in_C, dtype=float)
    T_cold_out_C = np.asarray(T_cold_out_C, dtype=float)

    if T_sink_C.shape == ():
        T_sink_C = np.full(T_len, float(T_sink_C), dtype=float)

    if T_warm_in_C.shape == ():
        T_warm_in_C = np.full(T_len, float(T_warm_in_C), dtype=float)

    if T_cold_out_C.shape == ():
        T_cold_out_C = np.full(T_len, float(T_cold_out_C), dtype=float)

    # Approximate the source temperature by the mean 5G water temperature
    # between warm-pipe inlet and cold-pipe outlet.
    T_source_C = 0.5 * (T_warm_in_C + T_cold_out_C)

    T_evap_K = T_source_C - dT_HP_evap_heating + 273.15
    T_cond_K = T_sink_C + dT_HP_cond_heating + 273.15

    lift = T_cond_K - T_evap_K
    if np.any(lift <= 0.0):
        raise ValueError(
            "Invalid 5G heat-pump heating COP calculation: "
            "the condenser temperature must be higher than the evaporator temperature."
        )

    COP = hp_5g_grade * T_cond_K / lift
    COP = np.clip(COP, COP_min, COP_max)

    return COP


def calc_decentral_hp_eer_cooling(
        T_cooling_supply_C,
        T_warm_out_C,
        T_len,
        hp_5g_grade,
        COP_min,
        COP_max,
        dT_HP_evap_cooling,
        dT_HP_cond_cooling
):
    """
    Carnot-based EER for reversible decentralized 5G heat pumps in cooling mode.

    The evaporator temperature is approximated below the building cooling
    supply temperature, while the condenser temperature is approximated
    above the 5G warm-pipe temperature.
    """
    T_cooling_supply_C = np.asarray(T_cooling_supply_C, dtype=float)
    T_warm_out_C = np.asarray(T_warm_out_C, dtype=float)

    if T_cooling_supply_C.shape == ():
        T_cooling_supply_C = np.full(T_len, float(T_cooling_supply_C), dtype=float)

    if T_warm_out_C.shape == ():
        T_warm_out_C = np.full(T_len, float(T_warm_out_C), dtype=float)

    T_evap_K = T_cooling_supply_C - dT_HP_evap_cooling + 273.15
    T_cond_K = T_warm_out_C + dT_HP_cond_cooling + 273.15

    lift = T_cond_K - T_evap_K
    if np.any(lift <= 0.0):
        raise ValueError(
            "Invalid 5G heat-pump cooling EER calculation: "
            "the condenser temperature must be higher than the evaporator temperature."
        )

    EER = hp_5g_grade * T_evap_K / lift
    EER = np.clip(EER, COP_min, COP_max)

    return EER

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
                flow_child = float(pipe.get("flow_max_abs", abs(pipe.get("flow_max", 0.0))))
                flow_up = float(pipes[pid_up].get("flow_max_abs", abs(pipes[pid_up].get("flow_max", 0.0))))
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

                    flow_up_abs = float(pipes[pid_up].get("flow_max_abs", abs(pipes[pid_up].get("flow_max", 0.0))))
                    flow_dn_abs = float(pipes[pid].get("flow_max_abs", abs(pipes[pid].get("flow_max", 0.0))))
                    v_up = flow_up_abs / max(np.pi * (d_up / 1000.0) ** 2 / 4.0, eps)
                    v_dn = flow_dn_abs / max(np.pi * (d_child / 1000.0) ** 2 / 4.0, eps)

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
    output_name = getattr(data, "output_scenario_name", data.scenario_name)
    result_folder = f"{output_name}_{topology}_5g_fixed"
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
    pipeline_path = os.path.join(param["dir_result"], "pipeline_5g_fixed.json")
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





