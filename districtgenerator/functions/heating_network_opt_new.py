# -*- coding: utf-8 -*-

import numpy as np
import math
import os
import json
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import fluids
import textwrap
from scipy.interpolate import interp1d
from tqdm import tqdm
import pandas as pd

def network_design(data):
    """
    Main workflow for the district heating network design.

    The network is designed using fixed design mass flows derived from
    building heat demand and required temperature levels.

    Pipe diameters are selected based on hydraulic constraints
    (pressure gradient and velocity limits). Using the resulting pipe
    geometry, network temperatures are solved while accounting for
    distributed pipe heat losses and thermal interaction between the
    supply and return pipes.

    Pump power is then calculated based on friction and local pressure
    losses along all network branches. A single circulation pump is
    assumed at the energy hub (EH), and the required pump head is
    determined from the hydraulically most demanding branch.

    Important modelling assumption
    -------------------------------
    Mass flows are determined once from building heat demand and
    required temperature difference and remain constant during the
    design process. Pipe heat losses therefore influence network
    temperatures and the required plant supply temperature, but they
    do not change pipe mass flows or pipe diameters.

    Steps
    -----
    1. Load and prepare network parameters
    2. Compute design mass flows in the network
    3. Size pipe diameters based on hydraulic limits
    4. Solve network temperatures including pipe heat losses
    5. Calculate thermal losses in all pipe segments
    6. Compute pump power based on hydraulic pressure losses
    7. Generate result plots
    8. Compute annualized network investment and operating costs
    """

    # 1. Load parameters
    data, param = load_parameter(data)

    # prepare result folder
    prepare_result_folder(data, param)

    # initialize pipeline dictionary
    data.pipeline = {}

    # 2. Compute design mass flows
    data, param = calc_flow(data, param)

    # 3. Size pipe diameters
    data, param = calc_diameter(data, param)

    # 4. Size pump
    data, param = compute_pump_power(data, param)

    # 5. Solve network temperatures
    data, param = compute_network_temperatures(data, param)

    # 6. Calculate pipe heat losses
    data, param = calc_heat_loss_pipe(data, param)

    # 7. Plot network results
    plot_network_results(data, param)

    # 8. Compute network costs
    compute_and_save_network_costs(data, param)

    return data

def load_parameter(data):
    """
    Prepare all parameters required for district heating network calculations.

    This function processes the district building data and network configuration
    to derive the thermal and hydraulic inputs needed for network design.
    It determines building heat demand, supply and return temperature
    requirements at each node, and pipe thermal properties.

    Additionally, it prepares economic parameters (annualization factors),
    pipe thermal resistance parameters according to DIN EN 13941, and
    extracts the network branch structure from the topology.

    Parameters
    ----------
    data : datahandler class
        Contains district buildings, heat grid configuration,
        pipeline topology, and economic parameters.

    Returns
    -------
    data : datahandler class
        Updated data object containing additional heat grid parameters.

    param : dict
        Dictionary containing prepared thermal loads, temperature
        requirements, pipe parameters, and network branch information.
    """

    param = {}

    # Heat grid data and basic parameters
    heat_grid_data = data.heat_grid_data

    T_len = len(data.heat_grid_data["T_soil"])
    heat_loss_substation = np.zeros(T_len, dtype=float)
    net_heat_demand = np.zeros(T_len, dtype=float)

    h_loss_subst = data.heat_grid_data["h_loss_subst"]  # 5%, Heat losses at the substation

    # Build fast lookup: building position -> node id
    node_lookup = {
        tuple(node_info["pos"]): key
        for key, node_info in data.pipeline_nodes.items()}

    # Calculate building heat demand connected to the district heating grid
    for building in data.district:
        if building["buildingFeatures"]["heater"] != "heat_grid":
            continue

        heating = building["user"].heat / 1000  # kW
        dhw = building["user"].dhw / 1000  # kW
        generationSTC = building["generationSTC"] / 1000  # kW

        net_building_demand = np.maximum(heating + dhw - generationSTC, 0)  # kW
        building["user"].net_building_demand = net_building_demand  # kW

        # Additional heat required to cover substation heat losses
        subst_loss = net_building_demand * (h_loss_subst / 100)
        heat_loss_substation += subst_loss                # kW

        # Total heat demand supplied by the network
        # (building demand + substation heat losses)
        net_heat_demand += net_building_demand + subst_loss

    # Build temperature requirements and loads at the substatiom
    T_sup_req_by_node = {}
    T_ret_req_by_node_SH = {}
    T_ret_req_by_node_DHW = {}
    Q_SH_by_node = {}
    Q_DHW_by_node = {}
    Q_by_node = {}

    dT_HX_sup = 8.0 # K  minimum temperature difference required between the primary supply (network) and the secondary supply (building heating system)
    dT_HX_ret = 4.0 # K  minimum temperature difference required between the primary return (network) and the secondary return (building heating system)
    T_dhw_required = float(data.decentral_device_data["TES_DHW"]["T_DHW_needed"])   # °C needed domestic hot water temperature

    for building in data.district:
        if building["buildingFeatures"]["heater"] != "heat_grid":
            continue

        pos_building = tuple(building["buildingFeatures"]["position"])

        node_key = node_lookup.get(pos_building)

        if node_key is None:
            continue

        buildings_heating_curve = building["envelope"].heating_curve["unclustered"]

        # Required supply and return temperatures
        Ts_req_SH = np.asarray(buildings_heating_curve["Ts_curve"], dtype=float) + dT_HX_sup
        Tr_req_SH = np.asarray(buildings_heating_curve["Tr_curve"], dtype=float) + dT_HX_ret

        Ts_req_DHW = T_dhw_required + dT_HX_sup
        Tr_req_DHW = 30.0  # Assume the return temperature at the primary side of DHW is 30 °C

        # The network supply temperature must satisfy both space heating (SH)
        # and domestic hot water (DHW) requirements. Therefore, the required
        # supply temperature at the building is defined as the maximum of the
        # SH and DHW supply temperature levels.
        dhw_load = np.asarray(building["user"].dhw, dtype=float) / 1000.0  # kW
        sh_load = np.asarray(building["user"].heat, dtype=float) / 1000.0  # kW

        # Supply temperature constraint
        Ts_req = np.maximum(Ts_req_SH, Ts_req_DHW)

        # Building heat load
        #todo: STC are still not considered here
        Q_SH = sh_load * (1.0 + h_loss_subst / 100.0)
        Q_DHW = dhw_load * (1.0 + h_loss_subst / 100.0)
        Q_total = Q_SH + Q_DHW

        T_sup_req_by_node[node_key] = Ts_req
        T_ret_req_by_node_SH[node_key] = Tr_req_SH
        T_ret_req_by_node_DHW[node_key] = np.full(T_len, Tr_req_DHW, dtype=float)

        # Loads at the substation
        Q_SH_by_node[node_key] = Q_SH
        Q_DHW_by_node[node_key] = Q_DHW
        Q_by_node[node_key] = Q_total

    # store them into param
    param["T_sup_req_by_node"] = T_sup_req_by_node
    param["T_ret_req_by_node_SH"] = T_ret_req_by_node_SH
    param["T_ret_req_by_node_DHW"] = T_ret_req_by_node_DHW
    param["Q_SH_by_node"] = Q_SH_by_node
    param["Q_DHW_by_node"] = Q_DHW_by_node
    param["Q_by_node"] = Q_by_node

    # Get network supply temperature profile if availabe
    T_sup_cfg = get_configured_network_temperatures(data)
    param["T_sup_network_config"] = T_sup_cfg

    # temperature-based pipe selection
    Ts_config = data.heat_grid_data.get("supply_temperature", "auto")

    if Ts_config == "auto":
        Ts_max = max(np.max(Ts) for Ts in T_sup_req_by_node.values())
    else:
        Ts_max = float(Ts_config)

    # select pipe data
    if Ts_max > 60:
        pipe_data = data.pipe_data_all["KMR"]

    elif Ts_max > 35:
        pmr_data = data.pipe_data_all["PMR"]
        # add KMR pipes for DN > 150
        kmr_data = data.pipe_data_all["KMR"]
        kmr_large = kmr_data[kmr_data["Nominal diameter (DN)"] > 150]
        pipe_data = pd.concat([pmr_data, kmr_large], ignore_index=True)

    else:
        pipe_data = data.pipe_data_all["PE"]

    data.pipe_data = pipe_data

    print(f"[INFO] Pipe selection based on temperature: T = {Ts_max:.1f}°C")

    # Pipe diameter data
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

    # Network topology
    # Extract longest root-to-leaf branches from the network topology
    network = data.pipeline_topology

    # calculate the ann_factor
    # pipe
    pipe_lifetime = heat_grid_data["pipe"]["pipe_lifetime"]  # 30a,          pipe lifetime (VDI 2067)
    # calculate the Annualization Factor and add to datahandler
    pipe_ann_factor = calc_annual_factor(data, pipe_lifetime)
    data.heat_grid_data["pipe"]["pipe_ann_factor"] = pipe_ann_factor

    # pump
    pump_lifetime = heat_grid_data["pump"]["pump_lifetime"]  # 10a,          pump lifetime (VDI 2067 Umwälzpumpe)
    # calculate the Annualization Factor and add to datahandler
    pump_ann_factor = calc_annual_factor(data, pump_lifetime)
    data.heat_grid_data["pump"]["pump_ann_factor"] = pump_ann_factor

    # HP
    HP_lifetime = data.central_device_data["AirHP"]["life_time"]      # 25a,          Maximum lifetime. source:
    HP_ann_factor = calc_annual_factor(data, HP_lifetime)

    # Store parameters
    param["heat_loss_substation"] = heat_loss_substation
    param["net_heat_demand"] = net_heat_demand
    param["pipe_dict"] = pipe_dict
    param["HP_ann_factor"] = HP_ann_factor

    return data, param

def calc_flow(data, param, save_path=None):
    """
    Calculate mass and volumetric flow rates in each pipe segment.

    Mass flows are computed assuming a common network supply temperature
    equal to the highest supply temperature required by any building
    at each timestep.

    The function calculates building mass flows and aggregates them
    through the network topology to determine pipe flows.

    Parameters
    ----------
    data : datahandler class
        Contains district buildings, pipeline nodes, and topology.

    param : dict
        Dictionary containing temperature requirements and network
        parameters.

    save_path : str, optional
        If provided, pipeline data will be exported as a JSON file
        for debugging or inspection.

    Returns
    -------
    data : datahandler class
        Updated pipeline dictionary containing flows and pipe geometry.

    param : dict
        Unmodified parameter dictionary passed through the function.
    """

    # Fluid properties
    c_f = data.heat_grid_data["fluid"]["c_f"]  # 4180J/(kg*K), fluid specific heat capacity
    rho_f = data.heat_grid_data["fluid"]["rho_f"]  # 1000kg/m^3,   fluid density

    T_sup_req_by_node = param["T_sup_req_by_node"]
    T_ret_req_by_node_SH = param["T_ret_req_by_node_SH"]
    T_ret_req_by_node_DHW = param["T_ret_req_by_node_DHW"]
    Q_SH_by_node = param["Q_SH_by_node"]
    Q_DHW_by_node = param["Q_DHW_by_node"]

    # Determine the assumed supply temperature used to calculate
    # the mass flows at the building-level in the network.

    # Two operating modes are possible:
    # 1) Automatic temperature mode (supply_temperature = "auto"):
    #    The supply temperature is taken as the maximum supply
    #    temperature required by any connected building at each timestep.
    # 2) Given supply mode (supply_temperature = float):
    #    The supply temperature is predefined (constant or heating curve).
    T_sup_cfg = param.get("T_sup_network_config", None)

    if T_sup_cfg is None:
        Ts_matrix = np.vstack(list(T_sup_req_by_node.values()))
        T_sup_network = np.max(Ts_matrix, axis=0)
    else:
        T_sup_network = np.asarray(T_sup_cfg, dtype=float)

    param["T_sup_design"] = T_sup_network

    # Lookup: building position -> node id
    node_lookup = {
        tuple(node_info["pos"]): key
        for key, node_info in data.pipeline_nodes.items()
    }

    param["building_massflow_SH"] = {}  # kg/s; # Mass flow through the space heating (SH) heat exchanger of the building substation.
    param["building_massflow_DHW"] = {} # kg/s; # Mass flow through the domestic hot water (DHW) heat exchanger of the building substation.
    param["building_massflow_HX"] = {}  # kg/s; # Total mass flow passing through all heat exchangers in the building substation. Equal to the sum of SH and DHW heat exchanger flows

    # Store peak mass flows for each building.
    param["building_massflow_max_SH"] = {}
    param["building_massflow_max_DHW"] = {}

    # Minimum flow fraction relative to the building's peak flow.
    # Ensures continuous circulation through the heat exchanger and avoids zero-flow conditions.
    alpha = data.heat_grid_data["min_flow_fraction"]  # minimum flow fraction

    # Building demand + building mass flow
    for building in data.district:

        if building["buildingFeatures"]["heater"] != "heat_grid":
            continue

        pos_building = tuple(building["buildingFeatures"]["position"])
        node_key = node_lookup.get(pos_building)
        if node_key is None:
            continue

        # use the network supply temperature instead of the building-specific
        # supply requirement. Buildings regulate heat extraction via control
        # valves, so the mass flow depends on the available network supply
        # temperature and the required return temperatures of the building.
        Ts = T_sup_network
        Tr_SH = T_ret_req_by_node_SH[node_key]
        Tr_DHW = T_ret_req_by_node_DHW[node_key]

        # ignore very small loads (< 10 W)
        Q_SH = np.where(Q_SH_by_node[node_key] < 0.01, 0.0, Q_SH_by_node[node_key])  # kW
        Q_DHW = np.where(Q_DHW_by_node[node_key] < 0.01, 0.0, Q_DHW_by_node[node_key])  # kW

        deltaT_SH = Ts - Tr_SH
        deltaT_DHW = Ts - Tr_DHW

        # kg/s; Mass flows derived from energy balance
        m_SH = Q_SH * 1000.0 / (c_f * deltaT_SH)
        m_DHW = Q_DHW * 1000.0 / (c_f * deltaT_DHW)

        # max over time
        m_SH_max = float(np.max(m_SH))
        m_DHW_max = float(np.max(m_DHW))

        # Enforce minimum flow as a fraction of peak flow to ensure continuous circulation
        m_SH = np.maximum(m_SH, alpha * m_SH_max)
        m_DHW = np.maximum(m_DHW, alpha * m_DHW_max)

        m_dot = m_SH + m_DHW

        # store everything
        param["building_massflow_max_SH"][node_key] = m_SH_max
        param["building_massflow_max_DHW"][node_key] = m_DHW_max

        param["building_massflow_SH"][node_key] = m_SH
        param["building_massflow_DHW"][node_key] = m_DHW
        param["building_massflow_HX"][node_key] = m_dot

    # Aggregate mass flows along the network
    network = data.pipeline_topology

    # Mass flow in each pipe segment , equal to the sum of all downstream building_massflow_HX values.
    pipe_massflows = aggregate_mass_flows(network, param["building_massflow_HX"], root="EH1")

    # Convert to volumetric flows and store
    for (parent, child), massflow_array in pipe_massflows.items():

        # generate pipe id using node pair: "parent->child"
        pipe_id = f"{parent}->{child}"

        # Pipe geometry
        pos_parent = data.pipeline_nodes[parent]["pos"]
        pos_child = data.pipeline_nodes[child]["pos"]

        # convert to numpy array
        p1 = np.array(pos_parent, dtype=float)
        p2 = np.array(pos_child, dtype=float)

        # Pipe length (Euclidean distance)
        length = float(np.linalg.norm(p1 - p2))

        # m³/s; Volumetric flow rate in the pipe segment.
        flow_array = massflow_array / rho_f

        mask = flow_array > 1e-9

        if np.any(mask):
            flow_max = float(np.max(flow_array[mask]))
            flow_min = float(np.min(flow_array[mask]))
        else:
            flow_max = 0.0
            flow_min = 0.0

        # store into data.pipeline
        if pipe_id not in data.pipeline:

            data.pipeline[pipe_id] = {
                "from": parent,  # string, name of start node
                "to": child,  # string, name of end node
                "from_pos": pos_parent,  # tuple, coordinate of start node
                "to_pos": pos_child,  # tuple, coordinate of end node
                "length": length,  # length of the pipe
                "flow": flow_array,
                "flow_max": flow_max,
                "flow_min": flow_min}

        else:

            data.pipeline[pipe_id].update({
                "flow": flow_array,
                "flow_max": flow_max,
                "flow_min": flow_min
            })

    # Save pipeline data for debugging
    if save_path is not None:
        json_ready = to_jsonable(data.pipeline)
        with open(save_path, "w") as f:
            json.dump(json_ready, f, indent=4)

    return data, param

def calc_diameter(data, param):
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
            v_lim = 1.2 if DN <= 32 else 2.0  #todo: find source
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

def compute_pump_power(data, param):
    """
    Compute the circulation pump power required for the district heating network.

    A single central pump is assumed at the energy hub (EH1). The pump
    provides one common differential pressure for the entire network.
    The required pump head is determined by the hydraulically most
    demanding path (critical path) from the energy hub to any building.

    Hydraulic model
    ---------------
    Pressure losses are calculated from:
    - distributed pipe friction (Darcy–Weisbach equation)
    - local losses (bends, tees, diameter changes) via ζ-values
    - one substation pressure drop per building branch

    For each building, the total pressure drop is obtained by summing
    all pipe and local losses along the path from the energy hub to the
    building, and adding the corresponding substation pressure drop.
    The required pump head is then given by the maximum of these path
    pressure drops.

    An additional pressure loss at the energy hub is added once as a
    common system-level loss.

    Pump power
    ----------
    The electrical pump power is computed as:

        P_pump = Vdot_total * Δp_total / η_pump

    where:
    - Vdot_total is the total volumetric flow at the energy hub
    - Δp_total is the required pump head (critical path + energy hub loss)
    - η_pump is the pump efficiency

    Modeling assumptions
    -------------------
    - Tree-shaped network (no loops)
    - Single central pump (no distributed pumping)
    - Identical supply and return hydraulic behavior (friction doubled)
    - Substation pressure drops are equal for all buildings (if constant input)

    This formulation corresponds to a pressure-controlled network,
    where the pump head is set by the critical branch and excess
    pressure in less demanding branches is dissipated implicitly
    (e.g. by control valves).
    """

    pipe_dict = param["pipe_dict"]
    rho_f = data.heat_grid_data["fluid"]["rho_f"]
    eta_pump = data.heat_grid_data["pump"]["eta_pump"]   # electric pump efficiency
    dp_substation = data.heat_grid_data.get("dp_substation")  #todo: Wert prüfen
    dp_energy_hub = data.heat_grid_data.get("dp_energy_hub")  #todo: Wert prüfen

    # Compute local loss coefficients (zeta)
    hydraulic_features = identify_junction_and_bends(data)
    data, zeta = compute_zeta_values(data, param, hydraulic_features)

    # save local hydraulic loss data
    export_data = {
        "node_type": hydraulic_features["node_type"],
        "pipe_angle": hydraulic_features["pipe_angle"],
        "diameter_change": hydraulic_features["diameter_change"],
        "zeta": zeta
    }

    save_path = os.path.join(param["dir_result"], "local_hydraulic_loss_data.json")
    with open(save_path, "w") as f:
        json.dump(export_data, f, indent=4)

    # Compute pressure drop per pipe
    pipe_dp = {}

    for pipe_id, pipe in data.pipeline.items():

        f_i = pipe.get("f_fric", data.heat_grid_data["pipe"]["f_fric"])

        DN = pipe["DN"]  # mm
        d_i = pipe_dict[DN]["Inner diameter (pipe) (mm)"] / 1000.0  # m
        length = pipe["length"]  # m
        flow = pipe["flow"]  # m3/s

        # velocity
        area = np.pi * d_i**2 / 4.0
        velocity = flow / area  # m/s

        # friction losses (Darcy–Weisbach)
        dp_friction = f_i * (length / d_i) * (rho_f * velocity**2 / 2.0)

        # *2: supply + return
        dp_friction *= 2.0

        # local losses
        zeta_pipe = pipe["zeta"]
        dp_local = rho_f * zeta_pipe * velocity**2 / 2.0

        # total pressure drop for this pipe
        pipe_dp[pipe_id] = dp_friction + dp_local  # Pa

    # Build topology paths
    topo = data.pipeline_topology
    root = "EH1"

    parent = {}
    order = []

    def dfs(node):
        order.append(node)
        for ch in topo.get(node, []):
            parent[ch] = node
            dfs(ch)

    dfs(root)

    # paths from each node to root
    path_to_root = {}
    for n in order:
        path = []
        cur = n
        while cur != root:
            par = parent[cur]
            path.append((par, cur))
            cur = par
        path_to_root[n] = path

    # Identify building nodes
    building_nodes = list(param["Q_by_node"].keys())

    # Mapping pipe pairs
    pair_to_pid = {(p["from"], p["to"]): pid for pid, p in data.pipeline.items()}

    T_e = data.site["T_e"]

    # Critical path evaluation
    dp_worst = np.zeros_like(T_e, dtype=float)

    for n in building_nodes:
        dp_line = np.zeros_like(T_e, dtype=float)

        # Sum pressure losses along full path EH → building
        for (par, ch) in path_to_root[n]:
            pid = pair_to_pid[(par, ch)]
            dp_line += pipe_dp[pid]

        dp_line += dp_substation  # one substation on that branch

        # Take maximum across all buildings
        dp_worst = np.maximum(dp_worst, dp_line)

    # Add energy hub losses
    dp_total = dp_worst + dp_energy_hub

    # Total volumetric flow at EH
    Vdot_total_profile = np.zeros_like(T_e, dtype=float)
    for pipe_id, pipe in data.pipeline.items():
        if pipe["from"] == root:
            Vdot_total_profile += pipe["flow"]

    # Pump electrical power
    pump_power = Vdot_total_profile * dp_total / (eta_pump * 1000.0)  # kW

    # Pump design electrical power
    data.heat_grid_data["pump_power_design"] = float(np.max(pump_power)) * 1.3 # kW #todo: Sicherheitsfaktoren benötigt?

    # Pump design head
    data.heat_grid_data["dp_pump_max"] = float(np.max(dp_total)) * 1.3  # Pa    #todo: Sicherheitsfaktoren benötigt?

    return data, param

def compute_network_temperatures(data, param):
    """
    Solve the supply and return temperature distribution
    in the district heating network for all timesteps.

    The formulation perform a steady-state temperature propagation
    through the network while considering pipe heat losses.

    Supply Flow:
        Forward propagation from the plant (root) to all nodes.

    Return Flow:
        Backward propagation from buildings to the plant.
        Return streams from multiple branches are mixed.

    Solution strategy
    -----------------
    - Supply and return temperatures are thermally decoupled.
    - For fixed EH supply temperature and fixed mass flows, the
      temperature field is solved directly without inner iteration.
    - Return-temperature deficits are corrected by increasing
      building-level mass flows subject to hydraulic constraints.
    - Remaining supply-temperature deficits are incrementaly corrected
      by the EH supply temperature.

    Returns
    -------
    T_sup_EH : ndarray
        Required supply temperature at Energy hub.

    T_ret_EH : ndarray
        Return temperature arriving at Energy hub.

    T_sup_node : dict
        Supply temperature at each node.

    T_ret_node : dict
        Mixed return temperature at each node.

    T_sup_pipe_out : dict
        Supply pipe outlet temperature (before mixing with other branches).

    T_ret_pipe_out : dict
        Return pipe outlet temperature (before mixing with other branches).
    """

    T_sup_cfg = data.heat_grid_data.get("supply_temperature", "auto")

    if T_sup_cfg != "auto":
        return compute_network_temperatures_given(data, param)

    return compute_network_temperatures_auto(data, param)

def compute_network_temperatures_auto(data, param, max_iter=20, tol=0.5, relax=0.3):
    """
    Solve the network with automatic adjustment of the energy-hub supply temperature.

    Control logic
    -------------
    - The operator adjusts the supply temperature at the energy hub (EH).
    - Buildings react locally by adapting primary mass flow based on the
      delivered supply temperature and their required return temperatures.
    - Hydraulics are enforced subject to pump limits.
    - If the delivered supply temperatures are still insufficient, the EH
      supply temperature is increased and the process is repeated.

    Notes
    -----
    - This is a quasi-steady thermo-hydraulic operating-point solver.
    - It is consistent with compute_network_temperatures_given(), but adds
      an outer temperature-control loop.
    """

    shared = _prepare_network_temperature_solver(data, param)

    topo = shared["topo"]
    pipe_dict = shared["pipe_dict"]
    nu_f = shared["nu_f"]
    c_f = shared["c_f"]
    rho = shared["rho"]
    T_soil = shared["T_soil"]
    T_len = shared["T_len"]
    T_sup_req_by_node = shared["T_sup_req_by_node"]
    T_ret_req_by_node_SH = shared["T_ret_req_by_node_SH"]
    T_ret_req_by_node_DHW = shared["T_ret_req_by_node_DHW"]
    Q_SH_by_node = shared["Q_SH_by_node"]
    Q_DHW_by_node = shared["Q_DHW_by_node"]
    Q_by_node = shared["Q_by_node"]
    root = shared["root"]
    pipes = shared["pipes"]
    order = shared["order"]
    path_to_root = shared["path_to_root"]
    supply_edges = shared["supply_edges"]
    return_children_edges = shared["return_children_edges"]
    pipe_UA_s = shared["pipe_UA_s"]

    T_sup_EH = shared["T_sup_EH"]
    T_ret_EH = shared["T_ret_EH"]
    P_pump = shared["P_pump"]
    T_sup_node = shared["T_sup_node"]
    T_ret_node = shared["T_ret_node"]
    T_sup_pipe_out = shared["T_sup_pipe_out"]
    T_ret_pipe_out = shared["T_ret_pipe_out"]
    T_ret_building_SH = shared["T_ret_building_SH"]
    T_ret_building_DHW = shared["T_ret_building_DHW"]

    alpha = data.heat_grid_data["min_flow_fraction"]
    P_pump_max = data.heat_grid_data["pump_power_design"] * 1000.0 # in Watt
    dp_pump_max = data.heat_grid_data["dp_pump_max"]   # Pa

    # Nodes representing buildings (substations) connected to the network.
    building_nodes = list(Q_by_node.keys())

    sup_deficits = []
    heat_deficits = []

    # Simulation per timestep
    for t in tqdm(range(T_len), desc="Solving network temperatures", unit="timestep"):

        # Initial supply temperature guess
        # The supply temperature at the energy hub (Ts) is initialized as the design supply
        # temperature which is the maximum required supply temperature among all buildings
        # at timestep t.
        Ts = float(param["T_sup_design"][t])
        result = None
        last_hydraulics = None
        timestep_converged = False

        # Outer control loop: operator raises EH supply temperature if needed
        for control_iter in range(max_iter):

            inner_converged = False
            result = None
            prev_T_sup_node = {n: Ts for n in building_nodes}

            # Inner fixed-point loop: buildings adapt flow, hydraulics are enforced,
            # temperatures are solved, repeat until flow/temperature state converges
            for iter_idx in range(max_iter):

                old_flow_HX = {n: float(param["building_massflow_HX"][n][t]) for n in building_nodes}

                # Building-side flow adaptation
                for n in building_nodes:
                    Ts_del = Ts if result is None else result["T_sup_node"][n]

                    Tr_req_SH = float(T_ret_req_by_node_SH[n][t])
                    Tr_req_DHW = float(T_ret_req_by_node_DHW[n][t])

                    Q_SH_W = float(Q_SH_by_node[n][t]) * 1000.0
                    Q_DHW_W = float(Q_DHW_by_node[n][t]) * 1000.0

                    m_SH = Q_SH_W / (c_f * (Ts_del - Tr_req_SH))
                    m_DHW = Q_DHW_W / (c_f * (Ts_del - Tr_req_DHW))

                    m_SH_min = alpha * float(param["building_massflow_max_SH"][n])
                    m_DHW_min = alpha * float(param["building_massflow_max_DHW"][n])

                    m_SH_target = max(m_SH, m_SH_min)
                    m_DHW_target = max(m_DHW, m_DHW_min)

                    # Under-relaxation
                    param["building_massflow_SH"][n][t] = ((1.0 - relax) * param["building_massflow_SH"][n][t] + relax * m_SH_target)
                    param["building_massflow_DHW"][n][t] = ((1.0 - relax) * param["building_massflow_DHW"][n][t] + relax * m_DHW_target)
                    param["building_massflow_SH"][n][t] = max(param["building_massflow_SH"][n][t], m_SH_min)
                    param["building_massflow_DHW"][n][t] = max(param["building_massflow_DHW"][n][t], m_DHW_min)
                    param["building_massflow_HX"][n][t] = (param["building_massflow_SH"][n][t] + param["building_massflow_DHW"][n][t])

                # Hydraulic feasibility loop
                last_hydraulics = None
                for _ in range(max_iter):

                    pipe_massflows = aggregate_mass_flows(
                        topo,
                        param["building_massflow_HX"],
                        root=root)

                    # Update pipe flows
                    for (par, ch), m_arr in pipe_massflows.items():
                        pid = f"{par}->{ch}"
                        pipes[pid]["flow"][t] = m_arr[t] / rho

                    hydraulics = evaluate_hydraulics(
                        t=t,
                        pipe_massflows=pipe_massflows,
                        pipes=pipes,
                        pipe_dict=pipe_dict,
                        path_to_root=path_to_root,
                        building_nodes=building_nodes,
                        rho=rho,
                        nu_f=nu_f,
                        data=data,
                        root=root)

                    hydraulic_capped = enforce_pump_constraint(
                        t=t,
                        param=param,
                        building_nodes=building_nodes,
                        path_to_root=path_to_root,
                        hydraulics=hydraulics,
                        data=data,
                        P_pump_max=P_pump_max,
                        dp_pump_max=dp_pump_max,
                        alpha=alpha)

                    if not hydraulic_capped:
                        last_hydraulics = hydraulics
                        break

                # If hydraulics are impossible even after capping, try a higher Ts
                # in the outer loop because higher Ts may reduce required flow.
                if last_hydraulics is None:
                    break

                # Solve temperatures for this hydraulically feasible state
                result = solve_network_temperatures(
                    t=t,
                    Ts=Ts,
                    building_nodes=building_nodes,
                    pipes=pipes,
                    rho=rho,
                    c_f=c_f,
                    T_soil=T_soil,
                    supply_edges=supply_edges,
                    order=order,
                    return_children_edges=return_children_edges,
                    pipe_UA_s=pipe_UA_s,
                    param=param,
                    T_sup_req_by_node=T_sup_req_by_node,
                    T_ret_req_by_node_SH=T_ret_req_by_node_SH,
                    T_ret_req_by_node_DHW=T_ret_req_by_node_DHW,
                    Q_SH_by_node=Q_SH_by_node,
                    Q_DHW_by_node=Q_DHW_by_node,
                    root=root
                )

                # Check convergence of the inner thermo-hydraulic loop
                max_rel_flow_change = 0.0
                max_temp_change = 0.0

                for n in building_nodes:
                    old_flow = old_flow_HX[n]
                    new_flow = float(param["building_massflow_HX"][n][t])
                    rel = abs(new_flow - old_flow) / old_flow
                    max_rel_flow_change = max(max_rel_flow_change, rel)

                    if iter_idx > 0:
                        old_T = prev_T_sup_node[n]
                        new_T = float(result["T_sup_node"][n])
                        max_temp_change = max(max_temp_change, abs(new_T - old_T))

                if iter_idx > 0 and max_rel_flow_change < 5e-3 and max_temp_change < 1e-2:
                    inner_converged = True
                    break

                prev_T_sup_node = {n: float(result["T_sup_node"][n]) for n in building_nodes}

            # If no hydraulically feasible state was found at this Ts, increase Ts and retry
            if last_hydraulics is None or result is None:
                Ts += 1.0
                continue

            # Check final thermal feasibility at this Ts
            sup_deficit = float(result["sup_deficit"])
            max_heat_deficit = max(result["heat_deficit_by_node"].values())

            if inner_converged and sup_deficit <= tol and max_heat_deficit <= 50.0:
                timestep_converged = True
                break

            # Operator raises Ts if thermal requirements are not yet met
            Ts += max(1.0, sup_deficit)

        if not timestep_converged:
            raise RuntimeError(
                f"[ERROR] Automatic Ts control did not converge at timestep {t} "
                f"within {max_iter} outer iterations."
            )

        # Store final deficits
        sup_deficits.append(float(result["sup_deficit"]))
        heat_deficits.append(max(result["heat_deficit_by_node"].values()))

        # Store final converged state
        P_pump[t] = float(last_hydraulics["P_required"])
        T_sup_EH[t] = Ts
        T_ret_EH[t] = result["Tr"]

        for n in order:
            T_sup_node[n][t] = result["T_sup_node"].get(n, 0.0)
            T_ret_node[n][t] = result["T_ret_node"].get(n, 0.0)

        for edge, value in result["T_sup_pipe_out"].items():
            T_sup_pipe_out[edge][t] = value

        for edge, value in result["T_ret_pipe_out"].items():
            T_ret_pipe_out[edge][t] = value

        for bn in building_nodes:
            T_ret_building_SH[bn][t] = result["T_ret_building_SH"][bn]
            T_ret_building_DHW[bn][t] = result["T_ret_building_DHW"][bn]

    # Print supply temperature deficit summary
    sup_deficits_arr = np.array(sup_deficits)
    sup_mask = sup_deficits_arr > 0.0

    if np.any(sup_mask):
        max_sup = sup_deficits_arr.max()
        t_max_sup = int(np.argmax(sup_deficits_arr))
        mean_sup = sup_deficits_arr[sup_mask].mean()
        count_sup = sup_mask.sum()

        print("\n=== TEMPERATURE SUPPLY DEFICIT SUMMARY ===")
        print(f"Max deficit: {max_sup:.2f} K at timestep {t_max_sup}")
        print(f"Mean deficit (only deficit timesteps): {mean_sup:.2f} K")
        print(f"Number of deficit timesteps: {count_sup} / {T_len}")
    else:
        print("\n=== TEMPERATURE SUPPLY DEFICIT SUMMARY ===")
        print("No supply temperature deficits.")

    # Print heat deficit summary
    heat_deficits_arr = np.array(heat_deficits)
    heat_mask = heat_deficits_arr > 0.0

    if np.any(heat_mask):
        max_heat = heat_deficits_arr.max()
        t_max_heat = int(np.argmax(heat_deficits_arr))
        mean_heat = heat_deficits_arr[heat_mask].mean()
        count_heat = heat_mask.sum()

        print("\n=== HEAT DEFICIT SUMMARY ===")
        print(f"Max deficit: {max_heat:.1f} W at timestep {t_max_heat}")
        print(f"Mean deficit (only deficit timesteps): {mean_heat:.1f} W")
        print(f"Number of deficit timesteps: {count_heat} / {T_len}")
    else:
        print("\n=== HEAT DEFICIT SUMMARY ===")
        print("No heat deficits.")

    return _finalize_network_temperature_solver(data, param, shared)

def compute_network_temperatures_given(data, param, max_iter=20, relax=0.3):
    """
    Solve the network for a given supply temperature.

    In this mode the energy hub (EH) supply temperature is predefined and
    is therefore not adjusted by the solver. The solver checks whether the network
    can satisfy all constraints (thermal + hydraulic).
    """

    shared = _prepare_network_temperature_solver(data, param)

    topo = shared["topo"]
    pipe_dict = shared["pipe_dict"]
    nu_f = shared["nu_f"]
    c_f = shared["c_f"]
    rho = shared["rho"]
    T_soil = shared["T_soil"]
    T_len = shared["T_len"]
    T_sup_req_by_node = shared["T_sup_req_by_node"]
    T_ret_req_by_node_SH = shared["T_ret_req_by_node_SH"]
    T_ret_req_by_node_DHW = shared["T_ret_req_by_node_DHW"]
    Q_SH_by_node = shared["Q_SH_by_node"]
    Q_DHW_by_node = shared["Q_DHW_by_node"]
    Q_by_node = shared["Q_by_node"]
    root = shared["root"]
    pipes = shared["pipes"]
    order = shared["order"]
    path_to_root = shared["path_to_root"]
    supply_edges = shared["supply_edges"]
    return_children_edges = shared["return_children_edges"]
    pipe_UA_s = shared["pipe_UA_s"]

    T_sup_EH = shared["T_sup_EH"]
    T_sup_EH[:] = np.asarray(param["T_sup_network_config"], dtype=float)
    T_ret_EH = shared["T_ret_EH"]
    T_sup_node = shared["T_sup_node"]
    T_ret_node = shared["T_ret_node"]
    T_sup_pipe_out = shared["T_sup_pipe_out"]
    T_ret_pipe_out = shared["T_ret_pipe_out"]
    T_ret_building_SH = shared["T_ret_building_SH"]
    T_ret_building_DHW = shared["T_ret_building_DHW"]
    P_pump = shared["P_pump"]

    alpha = data.heat_grid_data["min_flow_fraction"]
    P_pump_max = data.heat_grid_data["pump_power_design"] * 1000.0 # in Watt
    dp_pump_max = data.heat_grid_data["dp_pump_max"]   # Pa

    building_nodes = list(Q_by_node.keys())

    sup_deficits = []
    heat_deficits = []

    for t in tqdm(range(T_len), desc="Solving network temperatures (fixed Ts)", unit="timestep"):

        Ts = float(T_sup_EH[t])
        result = None
        converged = False
        prev_T_sup_node = {n: Ts for n in building_nodes}

        # Iterate to couple mass flows and temperatures until a consistent solution is found
        for iter_idx in range(max_iter):

            old_flow_HX = {n: float(param["building_massflow_HX"][n][t]) for n in building_nodes}

            # Update building mass flows based on delivered supply temperature
            for n in building_nodes:
                Ts_del = Ts if result is None else result["T_sup_node"][n]

                Tr_req_SH = float(T_ret_req_by_node_SH[n][t])
                Tr_req_DHW = float(T_ret_req_by_node_DHW[n][t])

                Q_SH_W = float(Q_SH_by_node[n][t]) * 1000.0
                Q_DHW_W = float(Q_DHW_by_node[n][t]) * 1000.0

                m_SH = Q_SH_W / (c_f * (Ts_del - Tr_req_SH))
                m_DHW = Q_DHW_W / (c_f * (Ts_del - Tr_req_DHW))

                m_SH_min = alpha * float(param["building_massflow_max_SH"][n])
                m_DHW_min = alpha * float(param["building_massflow_max_DHW"][n])

                m_SH_target = max(m_SH, m_SH_min)
                m_DHW_target = max(m_DHW, m_DHW_min)

                # Under-relaxation to avoid oscillation of flow/temperature coupling
                param["building_massflow_SH"][n][t] = ((1.0 - relax) * param["building_massflow_SH"][n][t] + relax * m_SH_target)
                param["building_massflow_DHW"][n][t] = ((1.0 - relax) * param["building_massflow_DHW"][n][t] + relax * m_DHW_target)
                param["building_massflow_SH"][n][t] = max(param["building_massflow_SH"][n][t], m_SH_min)
                param["building_massflow_DHW"][n][t] = max(param["building_massflow_DHW"][n][t], m_DHW_min)
                param["building_massflow_HX"][n][t] = (param["building_massflow_SH"][n][t] + param["building_massflow_DHW"][n][t])

            # Iterate hydraulics to enforce pump constraints (adjust flows until feasible)
            last_hydraulics = None
            for _ in range(max_iter):

                pipe_massflows = aggregate_mass_flows(
                    topo,
                    param["building_massflow_HX"],
                    root=root)

                for (par, ch), m_arr in pipe_massflows.items():
                    pid = f"{par}->{ch}"
                    pipes[pid]["flow"][t] = m_arr[t] / rho

                hydraulics = evaluate_hydraulics(
                    t=t,
                    pipe_massflows=pipe_massflows,
                    pipes=pipes,
                    pipe_dict=pipe_dict,
                    path_to_root=path_to_root,
                    building_nodes=building_nodes,
                    rho=rho,
                    nu_f=nu_f,
                    data=data,
                    root=root)

                hydraulic_capped = enforce_pump_constraint(
                    t=t,
                    param=param,
                    building_nodes=building_nodes,
                    path_to_root=path_to_root,
                    hydraulics=hydraulics,
                    data=data,
                    P_pump_max=P_pump_max,
                    dp_pump_max=dp_pump_max,
                    alpha=alpha)

                if not hydraulic_capped:
                    last_hydraulics = hydraulics
                    break

            if last_hydraulics is None:
                raise RuntimeError(
                    f"[ERROR] Pump constraint cannot be satisfied at timestep {t} "
                    f"after {max_iter} iterations. Required hydraulic power exceeds pump capacity."
                )

            # Temperature solver with current hydraulic state
            result = solve_network_temperatures(
                t=t,
                Ts=Ts,
                building_nodes=building_nodes,
                pipes=pipes,
                rho=rho,
                c_f=c_f,
                T_soil=T_soil,
                supply_edges=supply_edges,
                order=order,
                return_children_edges=return_children_edges,
                pipe_UA_s=pipe_UA_s,
                param=param,
                T_sup_req_by_node=T_sup_req_by_node,
                T_ret_req_by_node_SH=T_ret_req_by_node_SH,
                T_ret_req_by_node_DHW=T_ret_req_by_node_DHW,
                Q_SH_by_node=Q_SH_by_node,
                Q_DHW_by_node=Q_DHW_by_node,
                root=root
            )

            # Convergence check (flows + temperatures)
            max_rel_flow_change = 0.0
            max_temp_change = 0.0

            for n in building_nodes:
                old_flow = old_flow_HX[n]
                new_flow = float(param["building_massflow_HX"][n][t])
                rel = abs(new_flow - old_flow) / old_flow
                max_rel_flow_change = max(max_rel_flow_change, rel)

                # temperature change
                if iter_idx > 0:
                    old_T = prev_T_sup_node[n]
                    new_T = float(result["T_sup_node"][n])
                    max_temp_change = max(max_temp_change, abs(new_T - old_T))

            # convergence condition
            if iter_idx > 0 and max_rel_flow_change < 5e-3 and max_temp_change < 1e-2:
                converged = True
                break

            # store current temperatures for next iteration
            prev_T_sup_node = {n: float(result["T_sup_node"][n]) for n in building_nodes}

        if not converged:
            raise RuntimeError(f"[ERROR] Flow/temperature iteration did not converge at timestep {t}")

        # Feasibility checks only after convergence
        sup_deficit = float(result["sup_deficit"])
        max_heat_deficit = max(result["heat_deficit_by_node"].values())

        sup_deficits.append(sup_deficit)
        heat_deficits.append(max_heat_deficit)

        # Store results
        P_pump[t] = float(last_hydraulics["P_required"])
        T_ret_EH[t] = result["Tr"]

        for n in order:
            T_sup_node[n][t] = result["T_sup_node"].get(n, 0.0)
            T_ret_node[n][t] = result["T_ret_node"].get(n, 0.0)

        for edge, value in result["T_sup_pipe_out"].items():
            T_sup_pipe_out[edge][t] = value

        for edge, value in result["T_ret_pipe_out"].items():
            T_ret_pipe_out[edge][t] = value

        for bn in building_nodes:
            T_ret_building_SH[bn][t] = result["T_ret_building_SH"][bn]
            T_ret_building_DHW[bn][t] = result["T_ret_building_DHW"][bn]

    # Print supply temperature deficit
    sup_deficits_arr = np.array(sup_deficits)
    sup_mask = sup_deficits_arr > 0.0

    if np.any(sup_mask):
        max_sup = sup_deficits_arr.max()
        t_max_sup = int(np.argmax(sup_deficits_arr))
        mean_sup = sup_deficits_arr[sup_mask].mean()
        count_sup = sup_mask.sum()

        print("\n=== TEMPERATURE SUPPLY DEFICIT SUMMARY ===")
        print(f"Max deficit: {max_sup:.2f} K at timestep {t_max_sup}")
        print(f"Mean deficit (only deficit timesteps): {mean_sup:.2f} K")
        print(f"Number of deficit timesteps: {count_sup} / {T_len}")
    else:
        print("\n=== TEMPERATURE SUPPLY DEFICIT SUMMARY ===")
        print("No supply temperature deficits.")

    # Print heat deficit
    heat_deficits_arr = np.array(heat_deficits)
    heat_mask = heat_deficits_arr > 0.0

    if np.any(heat_mask):
        max_heat = heat_deficits_arr.max()
        t_max_heat = int(np.argmax(heat_deficits_arr))
        mean_heat = heat_deficits_arr[heat_mask].mean()
        count_heat = heat_mask.sum()

        print("\n=== HEAT DEFICIT SUMMARY ===")
        print(f"Max deficit: {max_heat:.1f} W at timestep {t_max_heat}")
        print(f"Mean deficit (only deficit timesteps): {mean_heat:.1f} W")
        print(f"Number of deficit timesteps: {count_heat} / {T_len}")
    else:
        print("\n=== HEAT DEFICIT SUMMARY ===")
        print("No heat deficits.")

    return _finalize_network_temperature_solver(data, param, shared)

def calc_heat_loss_pipe(data, param):
    """
    Calculate thermal heat losses for each pipe segment.
    Heat loss is computed separately for supply and return pipes

    Parameters
    ----------
    data : datahandler
        Contains pipeline flows and geometry.

    param : dict
        Contains node temperatures and pipe outlet temperatures.

    Returns
    -------
    data : datahandler
        Updated pipeline entries including heat_loss_pipe.

    heat_loss_pipe : dict
        Mapping (parent, child) -> total pipe heat loss [kW].
    """

    c_f = data.heat_grid_data["fluid"]["c_f"]
    rho = data.heat_grid_data["fluid"]["rho_f"]

    T_sup_node = param["T_sup_node"]
    T_ret_node = param["T_ret_node"]
    T_sup_pipe_out = param["T_sup_pipe_out"]
    T_ret_pipe_out = param["T_ret_pipe_out"]

    heat_loss_pipe = {}

    for pid, pipe in data.pipeline.items():

        parent = pipe["from"]
        child = pipe["to"]

        flow = pipe["flow"]           # m³/s
        m_dot = flow * rho            # kg/s

        # Supply loss
        T_in_sup = T_sup_node[parent]
        T_out_sup = T_sup_pipe_out[(parent, child)]

        Q_sup = m_dot * c_f * (T_in_sup - T_out_sup) / 1000  # kW

        # Return loss
        T_in_ret = T_ret_node[child]
        T_out_ret = T_ret_pipe_out[(parent, child)]

        Q_ret = m_dot * c_f * (T_in_ret - T_out_ret) / 1000  # kW

        Q_total = Q_sup + Q_ret

        pipe["heat_loss_pipe"] = Q_total
        heat_loss_pipe[(parent, child)] = Q_total

    param["heat_loss_pipe"] = heat_loss_pipe
    param["annual_heat_loss_pipes"] = sum(np.sum(Q_pipe) for Q_pipe in heat_loss_pipe.values())  # kWh

    return data, param

def plot_network_results(data, param):
    """
    Plot results

    Parameters
    ----------
    data: class datahandler
    param: dictionary

    Returns
    -------
    data: class datahandler
    """
    # Folder to save model and results
    dir_result = param["dir_result"]

    # calculate heat loss
    # load heat loss in substation
    heat_loss_substation = param.get("heat_loss_substation", param.get("heat_loss_substation_heating"))
    # load cooling loss in substation (5th gen only, safe default otherwise)
    cool_loss_substation = param.get("cool_loss_substation", param.get("heat_loss_substation_cooling"))

    # sum the heat loss in the network and calculate the heat loss density
    heat_loss_network = np.zeros_like(heat_loss_substation)
    total_pipe_length = 0
    annual_heat_loss_network = 0
    for pipe_id, pipe in data.pipeline.items():
        length = pipe["length"]
        total_pipe_length += length
        annual_heat_loss_pipe = np.sum(pipe["heat_loss_pipe"])
        pipe["heat_loss_density"] = annual_heat_loss_pipe / 1000 / length  # MWh/m
        annual_heat_loss_network += annual_heat_loss_pipe
        heat_loss_network += pipe["heat_loss_pipe"]

    t_s = len(next(iter(data.pipeline.values()))["heat_loss_pipe"])  # Number of time steps
    heat_loss_pos_network = np.zeros(t_s, dtype=float)
    heat_gain_pos_network = np.zeros(t_s, dtype=float)

    #Calculates the annual heat loss and gain visible for the energy hub (only when total heat loss added by all pipes ist >0 for losses or <0 for gains)
    for time_step in range(t_s):
        net = sum(pipe["heat_loss_pipe"][time_step] for pipe in data.pipeline.values())
        heat_loss_pos_network[time_step] = max(net, 0.0)
        heat_gain_pos_network[time_step] = max(-net, 0.0)

    annual_heat_loss_pos = np.sum(heat_loss_pos_network)
    annual_heat_gain_pos = np.sum(heat_gain_pos_network)

    heat_loss_pos_total = heat_loss_substation + heat_loss_pos_network

    param["annual_heat_loss_pos"] = annual_heat_loss_pos
    param["annual_heat_loss_pos_total"] = np.sum(heat_loss_substation) + annual_heat_loss_pos     # kWh
    data.heat_grid_data["total_losses_heating_network"] = heat_loss_pos_total
    # total_heat_loss_per_m = annual_heat_loss / total_pipe_length    # kWh/m
    # print("Total heat loss in network calculation finished successfully.")
    # print(f"Annual heat loss in pipeline network is {total_heat_loss_per_m:.2f} kWh per meter.")

    # recalculate the flow distribution with heat loss
    # file_path = os.path.join(dir_result, "pipe_postprocess.json")
    # data, param = calc_flow(data, param, heat_loss_pipe=heat_loss_pipe, heat_loss_pipe_cluster=heat_loss_pipe_cluster, save_path=file_path)

    # ---------- 1. plot Pipeline Map - Labeled by Pipe ID ----------
    fig, ax = plt.subplots(figsize=(10, 8))
    for idx, (pipe_id, pipe) in enumerate(data.pipeline.items(), start=1):
        start = tuple(pipe["from_pos"])
        end = tuple(pipe["to_pos"])
        ax.plot([start[0], end[0]], [start[1], end[1]], color="#1f77b4", linewidth=3, alpha=0.5)

        # Label the pipeline with id at midpoints.
        mid_x = (start[0] + end[0]) / 2
        mid_y = (start[1] + end[1]) / 2
        dy = 0
        dx = 0
        if abs(start[1] - end[1]) < 1e-6:  # horizontal
            dy = 2
        else:  # vertical
            dx = 6
        ax.text(mid_x + dx, mid_y + dy, str(idx), fontsize=8, color='black', ha='center', fontweight='bold')

    ax.set_title("Labeled by Pipe ID")
    ax.set_aspect('equal')

    base = os.path.join(dir_result, f"pipeline_id_{data.scenario_name}")
    plt.savefig(base + ".png")  # PNG
    plt.savefig(base + ".svg")  # SVG
    ax.grid(True, linestyle='--', linewidth=0.3)

#    plt.show()

    # ---------- 2. plot Pipeline Map - Diameter ----------
    fig, ax = plt.subplots(figsize=(10, 8))

    # Retrieve all selected pipe diameter sizes
    DN_values = [data.pipeline[pipe]["DN"] for pipe in data.pipeline.keys()]
    min_DN, max_DN = min(DN_values), max(DN_values)

    # Map pipe diameter to the color of the pipe in the plot
    norm = mcolors.Normalize(vmin=min_DN, vmax=max_DN)
    cmap = plt.cm.RdYlGn_r  # red → yellow → green

    for pipe_id, pipe in data.pipeline.items():
        start = tuple(pipe["from_pos"])
        end = tuple(pipe["to_pos"])

        DN = pipe["DN"]
        # Map pipe diameter to line width in the plot
        den = (max_DN - min_DN)
        if den == 0:
            lw = 3
        else:
            lw = 1 + 5 * (DN - min_DN) / (max_DN - min_DN)  # range: 1-5
        # The thicker the pipe, the redder its color; the thinner the pipe, the greener its color.
        color = cmap(norm(DN))

        ax.plot([start[0], end[0]], [start[1], end[1]], color=color, linewidth=lw)

        # The pipe diameter can be marked at the midpoint.
        mid_x = (start[0] + end[0]) / 2
        mid_y = (start[1] + end[1]) / 2
        ha = "center"
        dy = 0
        if abs(start[1] - end[1]) < 1e-6:
            dy = 2
            if start[0] > end[0] and start[0] - end[0] < 20:
                ha = "right"
            elif start[0] < end[0] and end[0] - start[0] < 20:
                ha = "left"
        ax.text(mid_x, mid_y + dy, f"DN{DN}", fontsize=8, ha=ha, color='black', fontweight='bold')

    ax.set_title("Diameter")
    ax.set_aspect('equal')
    ax.grid(True, linestyle='--', linewidth=0.3)

    base = os.path.join(dir_result, f"pipeline_diameter_{data.scenario_name}")
    plt.savefig(base + ".png")  # PNG
    plt.savefig(base + ".svg")  # SVG

#    plt.show()

    # ---------- 3. plot Pipeline Map - Maximum velocity (m/s) ----------
    # calculate the max. velocity and the max. pressure drop
    c_f = data.heat_grid_data["fluid"]["c_f"]  # 4180J/(kg*K), fluid specific heat capacity
    rho_f = data.heat_grid_data["fluid"]["rho_f"]  # 1000kg/m^3,   fluid density
    pipe_dict = param["pipe_dict"]

    for pipe_id, pipe in data.pipeline.items():
        f_i = pipe.get("f_fric")
        flow_max = pipe["flow_max"]  # m3/s
        d_i = pipe["d_i"]  # mm
        # length = pipe["length"]             # m
        pipe["velocity_max"] = flow_max / (np.pi * (d_i / 1000) ** 2 / 4)  # m/s
        pipe["pressure_drop_max"] = f_i * 8 * rho_f * flow_max ** 2 / (np.pi ** 2 * (d_i / 1000) ** 5) # Pa/m

    fig, ax = plt.subplots(figsize=(10, 8))

    # Retrieve all velocity_max_values of every pipe segment
    velocity_max_values = [data.pipeline[pipe]["velocity_max"] for pipe in data.pipeline.keys()]
    min_velocity_max, max_velocity_max = min(velocity_max_values), max(velocity_max_values)

    norm_v = mcolors.Normalize(vmin=min_velocity_max, vmax=max_velocity_max)
    # cmap = plt.cm.RdYlGn_r  # red → yellow → green

    for pipe_id, pipe in data.pipeline.items():
        start = tuple(pipe["from_pos"])
        end = tuple(pipe["to_pos"])

        velocity_max = pipe["velocity_max"]
        # Map velocity_max to line width in the plot
        lw = 1 + 5 * (velocity_max - min_velocity_max) / (max_velocity_max - min_velocity_max)  # range: 1-5
        # bigger velocity_max, redder; smaller velocity_max, greener
        color = cmap(norm_v(velocity_max))

        ax.plot([start[0], end[0]], [start[1], end[1]], color=color, linewidth=lw)

        # mark at the midpoint
        mid_x = (start[0] + end[0]) / 2
        mid_y = (start[1] + end[1]) / 2
        ha = "center"
        dy = 0
        if abs(start[1] - end[1]) < 1e-6:
            dy = 2
            if start[0] > end[0] and start[0] - end[0] < 20:
                ha = "right"
            elif start[0] < end[0] and end[0] - start[0] < 20:
                ha = "left"
        ax.text(mid_x, mid_y + dy, f"{velocity_max:.3f}", fontsize=8, ha=ha, color='black', fontweight='bold')

    ax.set_title("Maximum velocity (m/s)")
    ax.set_aspect('equal')
    ax.grid(True, linestyle='--', linewidth=0.3)

    base = os.path.join(dir_result, f"pipeline_velocity_max_{data.scenario_name}")
    plt.savefig(base + ".png")  # PNG
    plt.savefig(base + ".svg")  # SVG

#    plt.show()

    # ---------- 4. plot Pipeline Map - Maximum pressure drop (Pa/m) ----------
    fig, ax = plt.subplots(figsize=(10, 8))

    # Retrieve all pressure_drop_max_values of every pipe segment
    pressure_drop_max_values = [data.pipeline[pipe]["pressure_drop_max"] for pipe in data.pipeline.keys()]
    min_pressure_drop_max, max_pressure_drop_max = min(pressure_drop_max_values), max(pressure_drop_max_values)

    norm_pressure_drop = mcolors.Normalize(vmin=min_pressure_drop_max, vmax=max_pressure_drop_max)
    # cmap = plt.cm.RdYlGn_r  # red → yellow → green

    for pipe_id, pipe in data.pipeline.items():
        start = tuple(pipe["from_pos"])
        end = tuple(pipe["to_pos"])

        pressure_drop_max = pipe["pressure_drop_max"]
        # Map pressure_drop_max to line width in the plot
        lw = 1 + 5 * (pressure_drop_max - min_pressure_drop_max) / (
                    max_pressure_drop_max - min_pressure_drop_max)  # range: 1-5
        # bigger pressure_drop_max, redder; smaller pressure_drop_max, greener
        color = cmap(norm_pressure_drop(pressure_drop_max))

        ax.plot([start[0], end[0]], [start[1], end[1]], color=color, linewidth=lw)

        # mark at the midpoint
        mid_x = (start[0] + end[0]) / 2
        mid_y = (start[1] + end[1]) / 2
        ha = "center"
        dy = 0
        if abs(start[1] - end[1]) < 1e-6:
            dy = 2
            if start[0] > end[0] and start[0] - end[0] < 20:
                ha = "right"
            elif start[0] < end[0] and end[0] - start[0] < 20:
                ha = "left"
        ax.text(mid_x, mid_y + dy, f"{pressure_drop_max:.3f}", fontsize=8, ha=ha, color='black', fontweight='bold')

    ax.set_title("Maximum pressure drop (Pa/m)")
    ax.set_aspect('equal')
    ax.grid(True, linestyle='--', linewidth=0.3)

    base = os.path.join(dir_result, f"pipeline_pressure_drop_max_{data.scenario_name}")
    plt.savefig(base + ".png")  # PNG
    plt.savefig(base + ".svg")  # SVG

#    plt.show()

    # ---------- 5. plot Pipeline Map - Energy_density (MWh/m) ----------
    for pipe_id, pipe in data.pipeline.items():
        parent = pipe["from"]
        child = pipe["to"]
        # c_f in J/kg·K, rho_f in kg/m3
        flow = abs(pipe["flow"])  # m3/s
        length = pipe["length"]  # m
        # The transported heat in each pipe
        T_out_sup = param["T_sup_pipe_out"][(parent, child)]
        T_in_ret = param["T_ret_node"][child]
        deltaT_pipe = T_out_sup - T_in_ret
        energy_total = np.sum(c_f * rho_f * flow * deltaT_pipe) / 1e6  # MWh
        pipe["energy_density"] = energy_total / length  # MWh/m

    fig, ax = plt.subplots(figsize=(10, 8))

    # Retrieve all energy_density_values of every pipe segment
    energy_density_values = [data.pipeline[pipe]["energy_density"] for pipe in data.pipeline.keys()]
    min_energy_density, max_energy_density = min(energy_density_values), max(energy_density_values)

    norm_energy_density = mcolors.Normalize(vmin=min_energy_density, vmax=max_energy_density)
    # cmap = plt.cm.RdYlGn_r  # red → yellow → green

    for pipe_id, pipe in data.pipeline.items():
        start = tuple(pipe["from_pos"])
        end = tuple(pipe["to_pos"])

        energy_density = pipe["energy_density"]
        # Map pressure_drop_max to line width in the plot
        lw = 1 + 5 * (energy_density - min_energy_density) / (
                max_energy_density - min_energy_density)  # range: 1-5
        # bigger energy_density, redder; smaller energy_density, greener
        color = cmap(norm_energy_density(energy_density))

        ax.plot([start[0], end[0]], [start[1], end[1]], color=color, linewidth=lw)

        # mark at the midpoint
        mid_x = (start[0] + end[0]) / 2
        mid_y = (start[1] + end[1]) / 2
        ha = "center"
        dy = 0
        if abs(start[1] - end[1]) < 1e-6:
            dy = 2
            if start[0] > end[0] and start[0] - end[0] < 20:
                ha = "right"
            elif start[0] < end[0] and end[0] - start[0] < 20:
                ha = "left"
        ax.text(mid_x, mid_y + dy, f"{energy_density:.3f}", fontsize=8, ha=ha, color='black', fontweight='bold')

    ax.set_title("Energy density (MWh/m)")
    ax.set_aspect('equal')
    ax.grid(True, linestyle='--', linewidth=0.3)

    base = os.path.join(dir_result, f"pipeline_energy_density_{data.scenario_name}")
    plt.savefig(base + ".png")  # PNG
    plt.savefig(base + ".svg")  # SVG

#    plt.show()

    # ---------- 6. plot Pipeline Map - Heat_loss_density (MWh/m) ----------
    fig, ax = plt.subplots(figsize=(10, 8))

    # Retrieve all heat_loss_density_values of every pipe segment
    heat_loss_density_values = [data.pipeline[pipe]["heat_loss_density"] for pipe in data.pipeline.keys()]
    min_heat_loss_density, max_heat_loss_density = min(heat_loss_density_values), max(heat_loss_density_values)

    norm_heat_loss_density = mcolors.Normalize(vmin=min_heat_loss_density, vmax=max_heat_loss_density)
    # cmap = plt.cm.RdYlGn_r  # red → yellow → green

    for pipe_id, pipe in data.pipeline.items():
        start = tuple(pipe["from_pos"])
        end = tuple(pipe["to_pos"])

        heat_loss_density = pipe["heat_loss_density"]
        # Map pressure_drop_max to line width in the plot
        lw = 1 + 5 * (heat_loss_density - min_heat_loss_density) / (
                max_heat_loss_density - min_heat_loss_density + 1e-12)  # range: 1-5
        # bigger energy_density, redder; smaller energy_density, greener
        color = cmap(norm_heat_loss_density(heat_loss_density))

        ax.plot([start[0], end[0]], [start[1], end[1]], color=color, linewidth=lw)

        # mark at the midpoint
        mid_x = (start[0] + end[0]) / 2
        mid_y = (start[1] + end[1]) / 2
        ha = "center"
        dy = 0
        if abs(start[1] - end[1]) < 1e-6:
            dy = 2
            if start[0] > end[0] and start[0] - end[0] < 20:
                ha = "right"
            elif start[0] < end[0] and end[0] - start[0] < 20:
                ha = "left"
        ax.text(mid_x, mid_y + dy, f"{heat_loss_density:.3f}", fontsize=8, ha=ha, color='black', fontweight='bold')

    ax.set_title("Heat loss density (MWh/m)")
    ax.set_aspect('equal')
    ax.grid(True, linestyle='--', linewidth=0.3)

    base = os.path.join(dir_result, f"pipeline_heat_loss_density_{data.scenario_name}")
    plt.savefig(base + ".png")  # PNG
    plt.savefig(base + ".svg")  # SVG

def compute_and_save_network_costs(data, param):
    """
    Compute annualized investment costs, operation and maintenance (O&M) costs,
    and electricity costs for the district heating network.

    The function evaluates the economic performance of the designed network
    by calculating costs for the following components:

    - building substations
    - district heating pipes (material and construction)
    - circulation pump
    - electricity consumption of the pump
    - heat pump required to compensate network heat losses

    Annualization factors are derived from component lifetimes using the
    VDI 2067 methodology.

    Returns
    -------
    dict
        Dictionary containing all calculated cost components.
    """

    # cost of substation
    buildings_connected = [b for b in data.district if b["buildingFeatures"]["heater"] == "heat_grid"]
    C_substations = 0
    for building in buildings_connected:
        substation_capacity = building["bes_obj"].design_load_heating/1000 + building["bes_obj"].design_load_dhw/1000  #kW
        substation_costs = substation_capacity * data.heat_grid_data["C_subst"]
        C_substations += substation_costs
    substation_lifetime = data.heat_grid_data["lifetime_subst"]
    substation_ann_factor = calc_annual_factor(data, substation_lifetime)
    substation_ann_costs = C_substations * substation_ann_factor
    substation_om_costs = len(buildings_connected) * data.heat_grid_data["cost_om_subst"]

    # cost of pipes
    inv_pipes = 0
    inv_construction = 0
    for pipe in data.pipeline.keys():
        # load diameters for each pipe
        DN = data.pipeline[pipe]["DN"]
        length = data.pipeline[pipe]["length"]
        inv_pipes += length * param["pipe_dict"][DN]["Pipe Cost (€/m)"] * 2     # *2 for supply and return
        inv_construction += length * param["pipe_dict"][DN]["Construction Cost (€/m)"]
    # calculate the cost for the pipes
    pipe_ann_factor = data.heat_grid_data["pipe"]["pipe_ann_factor"]
    pipes_ann_costs = (inv_pipes + inv_construction) * pipe_ann_factor
    pipes_om_costs = (inv_pipes + inv_construction) * data.heat_grid_data["pipe"]["cost_om_pipe"]
    # print(f"Pipes annualized cost: {pipes_ann_costs:.2f} €")
    # print(f"Pipes O&M cost per year: {pipes_om_costs:.2f} €")

    # calculate the capacity of the pump
    pump_cap = data.heat_grid_data["pump_power_design"]   # kW
    # print(f"The capacity of the pump should be bigger than {pump_cap:5f}kW.")

    # calculate the investment for the pump
    inv_pump = pump_cap * data.heat_grid_data["pump"]["inv_pump"]

    # cost of pump
    pump_ann_costs = inv_pump * data.heat_grid_data["pump"]["pump_ann_factor"]
    pump_om_costs = inv_pump * data.heat_grid_data["pump"]["cost_om_pump"]
    # print(f"Pump annualized cost: {pump_ann_costs:.2f} €")
    # print(f"Pump O&M cost per year: {pump_om_costs:.2f} €")

    # electricity cost of the circulation pump
    pump_energy_total = np.sum(data.heat_grid_data["P_pump"])/1000  # kWh
    # print(f"The total electricity consumption for the pump is {pump_energy_total:5f}kWh/a.")
    pump_electricity_costs = pump_energy_total * data.ecoData["price_supply_el_eh"][0]

    # calculate the total cost
    network_om_costs = pipes_om_costs + pump_om_costs + substation_om_costs
    network_ann_costs = pipes_ann_costs + pump_ann_costs + substation_ann_costs
    data.heat_grid_data["om_costs"] = network_om_costs
    data.heat_grid_data["ann_costs"] = network_ann_costs

    # plot costs in stacked bar chart
    costs = {
        "Annualized investment for substations": substation_ann_costs,
        "Operation and maintenance cost for substations": substation_om_costs,
        "Annualized investment for pipes": pipes_ann_costs,
        "Operation and maintenance cost for pipes": pipes_om_costs,
        "Annualized investment for the pump": pump_ann_costs,
        "Operation and maintenance cost for the pump": pump_om_costs,
        "Electricity costs for the pump": pump_electricity_costs,
    }

    # --- Unpack data ---
    labels = list(costs.keys())
    values = np.array(list(costs.values()))

    # --- If you compare multiple scenarios, expand this array ---
    x = np.arange(1)  # Only one scenario for now
    fig, ax = plt.subplots(figsize=(10, 14))

    # --- Automatically assign distinguishable colors ---
    cmap = plt.get_cmap("tab20")  # 20 distinct colors
    colors = [cmap(i) for i in range(len(labels))]

    # --- Draw stacked bar chart ---
    bottom = np.zeros_like(x, dtype=float)
    for i, (label, val) in enumerate(zip(labels, values)):
        ax.bar(x, val, bottom=bottom, label=label, color=colors[i], width=0.8)
        bottom += val

    # Automatic line wrapping
    wrapped_labels = [
        "\n".join(textwrap.wrap(label, width=20))
        for label in labels
    ]

    # Axis labels, title, ticks
    ax.set_ylabel("Annual Costs in (€/a)")
    ax.set_title("Annual Cost Stacked Chart")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{data.scenario_name}"])
    ax.legend(wrapped_labels, bbox_to_anchor=(1.05, 1), loc='upper left', labelspacing=0.8)

    plt.tight_layout()

    base = os.path.join(param["dir_result"], f"network_cost_stack_{data.scenario_name}")
    plt.savefig(base + ".png")  # PNG
    plt.savefig(base + ".svg")  # SVG
    print("Cost stacked plot of heat grid saved to:", base)

#    plt.show()

    # save parameters, energy-consumption and costs to a json-file
    # output average temperatures for validation of the heat loss
    T_soil = data.heat_grid_data["T_soil"]
    T_soil_mean = np.mean(T_soil)
    T_supply_mean = np.mean(data.heat_grid_data["T_supply_EH"])
    T_return_mean = np.mean(data.heat_grid_data["T_return_EH"])

    # output heat supply for validation of the percentage of pump electricity and heat loss
    net_heat_demand = param["net_heat_demand"]  # kW
    total_net_heat_demand = np.sum(net_heat_demand) # kWh

    total_pipe_length = sum(pipe["length"] for pipe in data.pipeline.values())

    results = {
        "f_fric_mean": {
            "value": float(param.get("f_fric_mean", data.heat_grid_data["pipe"]["f_fric"])),
            "unit": "-",
            "description": "Mean Darcy friction factor used in the hydraulic calculation"
        },
        "T_soil_mean": {
            "value": float(T_soil_mean),
            "unit": "°C",
            "description": "The annual average temperature of soil"
        },
        "T_supply_mean": {
            "value": float(T_supply_mean),
            "unit": "°C",
            "description": "The annual average supply temperature at the EH"
        },
        "T_return_mean": {
            "value": float(T_return_mean),
            "unit": "°C",
            "description": "The annual average return temperature at the EH"
        },
        "total_pipe_length": {
            "value": float(total_pipe_length),
            "unit": "m",
            "description": "Sum of all pipe segments in the network"
        },
        "total_net_heat_demand": {
            "value": float(total_net_heat_demand),
            "unit": "kWh",
            "description": "Total annual heat supplied by the heating network"
        },
        "pump_capacity": {
            "value": float(pump_cap),
            "unit": "kW",
            "description": "Required pump power for the designed heating network"
        },
        "pump_electricity_consumption": {
            "value": float(pump_energy_total),
            "unit": "kWh",
            "description": "Total annual electricity consumption for the pump"
        },
        "pump_electricity_consumption_percentage": {
            "value": float(pump_energy_total / total_net_heat_demand * 100),
            "unit": "%",
            "description": "Pump total annual electricity consumption as a percentage of network heat supply"
        },
        "annual_heat_loss": {
            "value": float(param["annual_heat_loss_pos_total"]),
            "unit": "kWh",
            "description": "Annual heat loss (including pipelines and substations)"
        },
        "heat_loss_density": {
            "value": float(param["annual_heat_loss_pos"] * 1000 / 8760 / total_pipe_length),
            "unit": "W/m",
            "description": "Heat loss density (only including pipelines)"
        },
        "heat_loss_percentage": {
            "value": float(param["annual_heat_loss_pos_total"] / total_net_heat_demand * 100),
            "unit": "%",
            "description": "Annual heat loss (including pipelines and substations) as a percentage of network heat supply"
        },
        "substation_ann_costs": {
            "value": float(substation_ann_costs),
            "unit": "€",
            "description": "Annualized investment for the substations"
        },
        "substation_om_costs": {
            "value": float(substation_om_costs),
            "unit": "€",
            "description": "O&M cost for the substations"
        },
        "pipes_ann_costs": {
            "value": float(pipes_ann_costs),
            "unit": "€",
            "description": "Annualized investment for the pipes"
        },
        "pipes_om_costs": {
            "value": float(pipes_om_costs),
            "unit": "€",
            "description": "O&M cost for the pipes"
        },
        "pump_ann_costs": {
            "value": float(pump_ann_costs),
            "unit": "€",
            "description": "Annualized investment for the pump"
        },
        "pump_om_costs": {
            "value": float(pump_om_costs),
            "unit": "€",
            "description": "O&M cost for the pump"
        },
        "pump_electricity_costs": {
            "value": float(pump_electricity_costs),
            "unit": "€",
            "description": "Electricity cost for the pump"
        },
        "network_ann_costs": {
            "value": float(network_ann_costs),
            "unit": "€",
            "description": "Total annualized investment for the heating network (excluding cost for pump electricity)"
        },
        "network_om_costs": {
            "value": float(network_om_costs),
            "unit": "€",
            "description": "Total O&M cost for the heating network (excluding cost for pump electricity)"
        },
        "network_total_costs": {
            "value": float(network_ann_costs + network_om_costs + pump_electricity_costs),
            "unit": "€",
            "description": "Total annual cost for the heating network (including cost for pump electricity)"
        }
    }

    json_path = os.path.join(param["dir_result"], "heat_grid_parameters_outputs.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, ensure_ascii=False)

    print("Output JSON-file saved to:", json_path)

    return data

##############################################################################################################################
##############################################################################################################################
# HELPER FUNCTIONS
##############################################################################################################################
##############################################################################################################################

def calc_annual_factor(data, life_time):
    """
    Calculate the annualization factor for an investment
    according to VDI 2067-1.

    The factor converts investment costs into equivalent
    annual costs while accounting for component replacements
    during the observation period.

    Parameters
    ----------
    data : datahandler
        Contains economic parameters such as observation
        period and interest rate.

    life_time : int
        Technical lifetime of the component (years).

    Returns
    -------
    float
        Annualization factor (dimensionless).
    """

    observation_time = data.ecoData["observation_time"]
    interest_rate = data.ecoData["interest_rate"]
    q = 1 + interest_rate

    # Calculate capital recovery factor
    # Annualized cost = Present value × Capital Recovery Factor (CRF)
    CRF = ((q**observation_time)*interest_rate)/((q**observation_time)-1)

    # Number of required replacements
    n = int(math.floor(observation_time / life_time))

    # Investment for replacements
    invest_replacements = sum((q ** (-i * life_time)) for i in range(1, n+1))

    # Residual value of final replacement
    res_value = ((n+1) * life_time - observation_time) / life_time * (q ** (-observation_time))

    # Calculate annualized investments
    if life_time > observation_time:
        ann_factor = (1 - res_value) * CRF
    else:
        ann_factor = (1 + invest_replacements - res_value) * CRF

    return ann_factor

def aggregate_mass_flows(network, building_massflow, root="EH1"):
    """
    Aggregate mass flows through the network topology.

    Building mass flows are propagated upstream through the
    network tree so that each pipe carries the sum of all
    downstream building flows.

    Parameters
    ----------
    network : dict
        Network topology, key = parent node, value = list of child nodes
    building_massflow : dict
        key = building node, value = ndarray of mass flow (kg/s)
    root : str
        Root node name

    Returns
    -------
    pipe_massflows : dict
        key = (parent, child), value = ndarray of mass flow (kg/s)
    """

    pipe_massflows = {}

    def dfs(node):
        total_flow = None

        if node in building_massflow:
            total_flow = building_massflow[node].copy()

        for child in network.get(node, []):
            downstream_flow = dfs(child)
            pipe_massflows[(node, child)] = downstream_flow.copy()

            if total_flow is None:
                total_flow = downstream_flow.copy()
            else:
                total_flow = total_flow + downstream_flow

        if total_flow is None:
            # No building downstream → return zero flow time series
            return np.zeros_like(next(iter(building_massflow.values())))

        return total_flow

    dfs(root)
    return pipe_massflows

def identify_junction_and_bends(data, tol=1e-6):
    """
    Identify hydraulic junction types and geometric properties of the pipeline network.

    The function analyses the pipeline topology and determines for each node:

    - node type (source, end, straight, bend, tee, cross)
    - turning angles between connected pipe segments
    - diameter changes between upstream and downstream pipes

    These geometric properties are required for estimating local hydraulic
    resistance coefficients (ζ) caused by bends, tees, and diameter
    transitions.

    Parameters
    ----------
    data

    Returns
    -------
    dict:
        node_type[node] = "source" or "end" or "straight" or "bend" or "tee" or "cross"
        pipe_angle[pipe_id] = turning angle at downstream pipe
        diameter_change[pipe_id] = True/False
    """
    topology = data.pipeline_topology
    pipes = data.pipeline

    # node → incoming/outgoing pipe list
    incoming_pipes = {node: [] for node in topology}
    outgoing_pipes = {node: [] for node in topology}

    # ------------------ 1) get incoming/outgoing pipe of each node ------------------
    for pid, p in pipes.items():
        parent = p["from"]
        child = p["to"]
        outgoing_pipes.setdefault(parent, []).append(pid)
        incoming_pipes.setdefault(child, []).append(pid)

    # ------------------ 2) helper functions ------------------
    def node_xy(node):
        """ return the coordinate of the node """
        pos = data.pipeline_nodes[node]["pos"]
        return tuple(pos)

    def is_collinear(p0, p1, p2):
        """ check if three points are collinear """
        # the vector of p0p1
        v1 = (p1[0] - p0[0], p1[1] - p0[1])
        # the vector of p0p2
        v2 = (p2[0] - p0[0], p2[1] - p0[1])
        cross = abs(v1[0] * v2[1] - v1[1] * v2[0])
        return cross <= tol

    def angle_between(p0, p1, p2):
        """ calculate the angle between two vector p0p1 and p0p2 (0-180 degree) """
        # p0 is the turning node
        v1 = (p0[0] - p1[0], p0[1] - p1[1])  # upstream → node
        v2 = (p2[0] - p0[0], p2[1] - p0[1])  # node → downstream
        # lengths
        n1 = math.hypot(*v1)
        n2 = math.hypot(*v2)
        # dot product
        dot = v1[0] * v2[0] + v1[1] * v2[1]
        cosang = dot / (n1 * n2)
        cosang = max(-1.0, min(1.0, cosang))
        return math.degrees(math.acos(cosang))

    def diameter_changed(pid_up, pid_dn):
        """ check whether the downstream pipeline(pid_dn) has a diameter change """
        try:
            d_up = pipes[pid_up]["DN"]
            d_dn = pipes[pid_dn]["DN"]
            return d_dn != d_up
        except KeyError:
            return False

    # ------------------ 3) indentify node type and store angles ------------------
    node_type = {}  # "source" or "end" or "straight" or "bend" or "tee" or "cross"
    pipe_angle = {}  # save the angle between the incoming and outgoing pipe (pipe_angle[downstream_pipe]=angle)
    diameter_change = {}  # whether the downstream pipeline has a diameter change (diameter_change[downstream_pipe]=True/False)

    all_nodes = data.pipeline_nodes.keys()

    for node in all_nodes:
        inc = incoming_pipes[node]
        out = outgoing_pipes[node]
        deg = len(inc) + len(out)

        # ----------- 3.1 Source / End node -----------
        if len(inc) == 0:
            node_type[node] = "source"
            continue
        if len(out) == 0:
            node_type[node] = "end"
            continue

        # ----------- 3.2 Tee / Cross junction -----------
        if deg >= 3:
            if deg == 3:
                node_type[node] = "tee"
            else:  # deg == 4
                node_type[node] = "cross"

            # calculate the angle
            p0 = node_xy(node)

            for pid_in in inc:
                pid_in_from = pipes[pid_in]["from"]
                p_in = node_xy(pid_in_from)

                for pid_out in out:
                    pid_out_to = pipes[pid_out]["to"]
                    p_out = node_xy(pid_out_to)

                    angle = angle_between(p0, p_in, p_out)
                    pipe_angle[pid_out] = angle

            # check diameter changes
            if len(inc) == 1:
                pid_up = inc[0]
                for pid_dn in out:
                    diameter_change[pid_dn] = diameter_changed(pid_up, pid_dn)
            continue

        # ----------- 3.3 Bend or Straight (1 in + 1 out) -----------
        if len(inc) == 1 and len(out) == 1:
            pid_up = inc[0]
            pid_dn = out[0]

            # get the coordinate of the three nodes
            p_node = node_xy(node)
            p_up = node_xy(pipes[pid_up]["from"])
            p_dn = node_xy(pipes[pid_dn]["to"])

            # if three nodes are collinear, then the node is not a bend
            if is_collinear(p_node, p_up, p_dn):
                node_type[node] = "straight"
                pipe_angle[pid_dn] = 0.0
            else:
                node_type[node] = "bend"
                angle = angle_between(p_node, p_up, p_dn)
                pipe_angle[pid_dn] = angle

            diameter_change[pid_dn] = diameter_changed(pid_up, pid_dn)
            continue

        # other unexpected cases
        node_type[node] = "unknown"

    return {
        "node_type": node_type,
        "incoming_pipes": incoming_pipes,
        "outgoing_pipes": outgoing_pipes,
        "pipe_angle": pipe_angle,
        "diameter_change": diameter_change
    }

def compute_zeta_values(data, param, hydraulic_features, angle_branch_threshold=10):
    """
    Compute local hydraulic resistance coefficients (ζ) for each pipe segment.

    Local pressure losses are calculated based on pipe geometry and
    network topology. The following hydraulic elements are considered:

    - pipe bends
    - tee and cross junctions
    - pipe diameter expansions and contractions

    Resistance coefficients are determined using empirical correlations
    from the book "Technische Strömungslehre" by Bohl and Elmendorf. For tee and cross junctions,
    polynomial approximations of published diagrams are used.

    Parameters
    ----------
    data: object
        Your data class containing pipeline and nodes.
    param: dict
    hydraulic_features: dict
        Output from identify_junction_and_bends().
    angle_branch_threshold: float
        Angle (deg) above which a pipe is considered a 'branch' in tee/cross.

    Returns
    -------
    dict
        zeta[pipe_id] = numeric ζ value
    """

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
        node = pipe["from"]  # ζ is assigned to the downstream pipe leaving this node
        ntype = node_type[node]
        f_i = pipes[pid].get("f_fric", data.heat_grid_data["pipe"]["f_fric"])
        d = pipes[pid]["d_i"]  # mm
        DN = pipes[pid]["DN"]

        # ----------------------------
        # 1) Straight-through
        # ----------------------------
        if ntype == "straight":
            zeta_total = 0.0

        # ----------------------------
        # 2) Bend
        # ----------------------------
        elif ntype == "bend":
            ang = pipe_angle.get(pid, 0.0)
            R = pipe_dict[DN]["Radius (mm)"]  # mm
            K1 = -0.000041 * ang ** 2 + 0.0146 * ang + 0.05  # Bild 4.140 (Polynomial Fitting)
            K2 = 0.21 / (R / d) ** 0.5  # Bild 4.141 (for sharp bend) / 4.143 (for smooth bend)
            K3 = 1  # (h=b for round tube) Bild 4.142 (for sharp bend) / 4.144 (for smooth bend)
            zeta_U = K1 * K2 * K3  # Gl. 4.184b
            zeta_R = 0.0175 * f_i * R / d * ang  # Gl. 4.185a
            zeta_total = 2 * (zeta_U + zeta_R)  # *2 for supply and return

        # ----------------------------
        # 3) Tee or Cross junction
        # ----------------------------
        elif ntype in ("tee", "cross"):
            # the supply zeta is for the splitting (Trennung), and the return zeta is for the merging (Vereinigung)
            # child angle at this node
            ang = pipe_angle.get(pid, 0.0)

            pid_up = incoming_pipes[node][0]
            flow_child = pipe["flow_max"]
            flow_up = pipes[pid_up]["flow_max"]
            flow_ratio_raw = flow_child / max(flow_up, eps)
            flow_ratio = np.clip(flow_ratio_raw, 0.0, 1.0)

            if ang is None:
                zeta_total = 0.0
            else:
                # branch vs run direction
                if ang > angle_branch_threshold:
                    # branch line

                    # prepare the zeta value for certain flow ratio at three typical angles 45°, 60°, 90°
                    zeta_45_supply = 1.018 * flow_ratio ** 2 - 1.482 * flow_ratio + 0.933  # Bild 4.150 (Polynomial Fitting)
                    zeta_60_supply = 1.098 * flow_ratio ** 2 - 1.334 * flow_ratio + 1  # Bild 4.150 (Polynomial Fitting)
                    zeta_90_supply = 0.920 * flow_ratio ** 2 - 0.611 * flow_ratio + 0.995  # Bild 4.150 (Polynomial Fitting)
                    zeta_45_return = - 1.333 * flow_ratio ** 2 + 2.509 * flow_ratio - 0.846  # Bild 4.150 (Polynomial Fitting)
                    zeta_60_return = - 1.576 * flow_ratio ** 2 + 3.097 * flow_ratio - 0.883  # Bild 4.150 (Polynomial Fitting)
                    zeta_90_return = - 1.313 * flow_ratio ** 2 + 3.193 * flow_ratio - 0.995  # Bild 4.150 (Polynomial Fitting)

                    # angle interpolation
                    angles = np.array([45.0, 60.0, 90.0])
                    zeta_supply_values = np.array([zeta_45_supply, zeta_60_supply, zeta_90_supply])
                    zeta_return_values = np.array([zeta_45_return, zeta_60_return, zeta_90_return])
                    # generate the linear interpolation function
                    f_supply = interp1d(angles, zeta_supply_values, kind="linear", fill_value='extrapolate')
                    f_return = interp1d(angles, zeta_return_values, kind="linear", fill_value='extrapolate')
                    # if edge handling needed?
                    if ang < 45:
                        ang_eff = 45
                    elif ang > 90:
                        ang_eff = 90
                    else:
                        ang_eff = ang
                    zeta_supply = f_supply(ang_eff)
                    zeta_return = f_return(ang_eff)
                    zeta_total = zeta_supply + zeta_return
                else:
                    # straight-through
                    flow_ratio = 1 - flow_ratio
                    zeta_supply = 1.0045 * flow_ratio ** 2 - 0.6116 * flow_ratio + 0.0925  # Bild 4.150 (Polynomial Fitting)

                    # prepare the zeta value for certain flow ratio at three typical angles 45°,60°, 90°
                    zeta_45_return = - 1.852 * flow_ratio ** 2 + 1.118 * flow_ratio + 0.056  # Bild 4.150 (Polynomial Fitting)
                    zeta_60_return = - 1.250 * flow_ratio ** 2 + 0.911 * flow_ratio + 0.144  # Bild 4.150 (Polynomial Fitting)
                    zeta_90_return = 0.031 * flow_ratio ** 2 + 0.486 * flow_ratio + 0.079  # Bild 4.150 (Polynomial Fitting)

                    # angle interpolation
                    angles = np.array([45.0, 60.0, 90.0])
                    zeta_return_values = np.array([zeta_45_return, zeta_60_return, zeta_90_return])
                    # generate the linear interpolation function
                    f_return = interp1d(angles, zeta_return_values, kind="linear", fill_value='extrapolate')

                    # get the angle of the Abzweig (branch) pipe
                    pids = outgoing_pipes[node]
                    branch_pids = [p for p in pids if p != pid]
                    branch_angles = [pipe_angle[p] for p in branch_pids]
                    ang_a = max(branch_angles)

                    # if edge handling needed?
                    if ang_a < 45:
                        ang_eff = 45
                    elif ang_a > 90:
                        ang_eff = 90
                    else:
                        ang_eff = ang_a
                    zeta_return = f_return(ang_eff)

                    zeta_total = zeta_supply + zeta_return

        # ----------------------------
        # 4) Source / End node
        # ----------------------------
        elif ntype in ("source", "end"):
            zeta_total = 0.0

        else:
            # unknown or unsupported
            zeta_total = 0.0

        # ----------------------------
        # 5) Add diameter change ζ (if any)
        # ----------------------------
        if diameter_change.get(pid, False):
            d_child = pipes[pid]["d_i"]
            # find upstream pipe id
            # only one incoming pipe exists in a tree structure
            # try to find it
            pid_up = incoming_pipes[node][0]
            d_up = pipes[pid_up]["d_i"]

            if d_up > d_child:
                # pipe contraction in supply pipes
                area_ratio = (d_child / d_up) ** 2
                kontraktionszahl = 0.49 * area_ratio ** 2 - 0.12 * area_ratio + 0.624  # Bild 4.128 (Polynomial Fitting)
                zeta_dia_change_supply = 1.5 * ((1 - kontraktionszahl) / kontraktionszahl) ** 2  # Gl. 4.179
                # pipe expansion in return pipes
                zeta_dia_change_return = (1 - (
                            d_child / d_up) ** 2) ** 2  # Tabelle 4.19 Bezug auf Eintrittsquerschnitt
            elif d_up < d_child:
                # pipe expansion in supply pipes
                zeta_dia_change_supply = ((
                                                      d_child / d_up) ** 2 - 1) ** 2  # Tabelle 4.19 Bezug auf Austrittsquerschnitt
                # pipe contraction in return pipes
                area_ratio = (d_up / d_child) ** 2
                kontraktionszahl = 0.49 * area_ratio ** 2 - 0.12 * area_ratio + 0.624  # Bild 4.128 (Polynomial Fitting)
                zeta_dia_change_up = 1.5 * ((1 - kontraktionszahl) / kontraktionszahl) ** 2  # Gl. 4.179
                v_up = pipes[pid_up]["flow_max"] / (np.pi * (pipes[pid_up]["d_i"] / 1000) ** 2 / 4)
                v_dn = pipes[pid]["flow_max"] / (np.pi * (pipes[pid]["d_i"] / 1000) ** 2 / 4)
                factor = (v_up / v_dn) ** 2
                zeta_dia_change_return = zeta_dia_change_up * factor
            zeta_dia_change = zeta_dia_change_supply + zeta_dia_change_return
            zeta_total += zeta_dia_change

        # store back to result
        zeta[pid] = zeta_total
        data.pipeline[pid]["zeta"] = zeta_total

    return data, zeta

def heating_curve(T_e, T_ne, T_supply_min, T_supply_max):
    """
    Linear heating curve based on outdoor temperature.

    Parameters
    ----------
    T_e : np.ndarray
        Outdoor temperature [°C]

    T_supply_min : float
        Minimum supply temperature (warm outdoor conditions) [°C]

    T_supply_max : float
        Maximum supply temperature (cold outdoor conditions) [°C]

    Returns
    -------
    T_supply : np.ndarray
        Supply temperature profile [°C]
    """
    T_e = np.asarray(T_e, dtype=float)

    # Outdoor temperature range (typical DH operation)
    T_out_min = T_ne  # Nominal outside temperature
    T_out_max = 18.0   # heating limit

    # Linear interpolation
    T_supply = np.interp(T_e, [T_out_min, T_out_max], [T_supply_max, T_supply_min])

    # Enforce bounds
    T_supply = np.clip(T_supply, T_supply_min, T_supply_max)

    return T_supply

def get_configured_network_temperatures(data):
    """
    Returns supply temperature profile based on configuration.

    Modes
    -----
    - "auto":
        Supply temperature is determined later from building requirements
        → returns None

    - "constant":
        Fixed supply temperature over time

    - "heating_curve":
        Outdoor-temperature-dependent supply temperature
    """

    heat_grid_data = data.heat_grid_data

    # AUTO MODE
    Ts_config = heat_grid_data.get("supply_temperature", "auto")

    if Ts_config == "auto":
        return None

    temperature_mode = str(heat_grid_data.get("temperature_mode", "constant")).lower()

    T_len = len(heat_grid_data["T_soil"])

    # Heating period
    day_start = int(data.calendar["heating_period_start"])
    day_end = int(data.calendar["heating_period_end"])

    start = (day_start - 1) * 24
    end = (day_end - 1) * 24

    # CONSTANT MODE
    if temperature_mode == "constant":
        T_sup_max = float(Ts_config)

        # define minimum temperature
        dT = float(heat_grid_data.get("delta_T"))
        T_sup_min = T_sup_max - dT

        T_supply = np.full(T_len, T_sup_max, dtype=float)

        # enforce summer period = minimum temperature
        T_supply[end:start] = T_sup_min

        return T_supply

    # HEATING CURVE MODE
    if temperature_mode == "heating_curve":

        T_e = np.asarray(data.site["T_e"], dtype=float)
        T_ne = data.site["T_ne"] # nominal outside temperature

        dT = float(heat_grid_data.get("delta_T"))

        T_sup_max = float(Ts_config) #given temperature is assumed to be the max supply temperature
        T_sup_min = T_sup_max - dT

        T_supply = heating_curve(T_e, T_ne, T_sup_min, T_sup_max)

        # enforce summer period = minimum temperature
        T_supply[end:start] = T_sup_min

        return T_supply

    # INVALID MODE
    raise ValueError(f"Unsupported temperature_mode '{temperature_mode}'")

def _prepare_network_temperature_solver(data, param):
    topo = data.pipeline_topology
    pipe_dict = param["pipe_dict"]

    dp_pipe_max = data.heat_grid_data["pipe"]["dp_pipe_max"]
    nu_f = data.heat_grid_data["fluid"]["nu_f"]
    c_f = data.heat_grid_data["fluid"]["c_f"]  # J/kgK
    rho = data.heat_grid_data["fluid"]["rho_f"]  # kg/m3
    k_soil = data.heat_grid_data["k_soil"]

    # soil temperature profile
    T_soil = data.heat_grid_data["T_soil"]  # ndarray [t], °C
    T_len = len(T_soil)

    T_sup_req_by_node = param["T_sup_req_by_node"]
    T_ret_req_by_node_SH = param["T_ret_req_by_node_SH"]
    T_ret_req_by_node_DHW = param["T_ret_req_by_node_DHW"]
    Q_SH_by_node = param["Q_SH_by_node"]
    Q_DHW_by_node = param["Q_DHW_by_node"]
    Q_by_node = param["Q_by_node"]
    root = "EH1"

    pipes = data.pipeline

    # Precompute parent map and topological order
    parent = {}
    order = []

    def dfs(node):
        order.append(node)
        for ch in topo.get(node, []):
            parent[ch] = node
            dfs(ch)

    dfs(root)

    # Build path from each node to root
    path_to_root = {}
    for n in order:
        path = []
        cur = n
        while cur != root:
            par = parent[cur]
            path.append((par, cur))
            cur = par
        path_to_root[n] = path

    # children map
    children_map = {n: topo.get(n, []) for n in order}

    #  Precompute pipe-id lookup and edge lists
    pair_to_pid = {(p["from"], p["to"]): pid for pid, p in pipes.items()}

    # Supply propagation edges in DFS order (root -> leaves)
    supply_edges = [(parent[n], n, pair_to_pid[(parent[n], n)]) for n in order if n != root]

    # Return mixing needs node->children edges. Precompute per node.
    return_children_edges = {}
    for node in order:
        chs = children_map[node]
        if not chs:
            continue
        return_children_edges[node] = [(ch, pair_to_pid[(node, ch)]) for ch in chs]

    # Precompute UA per pipe
    # UA = 2*pi*k_soil*ks*L  (W/K), ks depends on DN, L on pipe
    pipe_UA_s = {}
    pipe_UA_a = {}
    for pid, p in pipes.items():
        DN = p["DN"]
        ks = pipe_dict[DN]["symmetrical heat loss factor"]
        ka = pipe_dict[DN]["antisymmetrical heat loss factor"]
        pipe_UA_s[pid] = 2.0 * np.pi * k_soil * ks * p["length"]
        pipe_UA_a[pid] = 2.0 * np.pi * k_soil * ka * p["length"]

    # Allocate outputs
    T_sup_EH = np.zeros(T_len)
    T_ret_EH = np.zeros(T_len)
    P_pump = np.zeros(T_len)

    T_sup_node = {n: np.zeros(T_len) for n in order}
    T_ret_node = {n: np.zeros(T_len) for n in order}

    T_sup_pipe_out = {(p["from"], p["to"]): np.zeros(T_len) for p in pipes.values()}
    T_ret_pipe_out = {(p["from"], p["to"]): np.zeros(T_len) for p in pipes.values()}

    # calculated return temperatures at the building substations
    T_ret_building_SH = {n: np.zeros(T_len) for n in Q_by_node.keys()}
    T_ret_building_DHW = {n: np.zeros(T_len) for n in Q_by_node.keys()}

    return {
        "topo": topo,
        "pipe_dict": pipe_dict,
        "dp_pipe_max": dp_pipe_max,
        "nu_f": nu_f,
        "c_f": c_f,
        "rho": rho,
        "k_soil": k_soil,
        "T_soil": T_soil,
        "T_len": T_len,
        "T_sup_req_by_node": T_sup_req_by_node,
        "T_ret_req_by_node_SH": T_ret_req_by_node_SH,
        "T_ret_req_by_node_DHW": T_ret_req_by_node_DHW,
        "Q_SH_by_node": Q_SH_by_node,
        "Q_DHW_by_node": Q_DHW_by_node,
        "Q_by_node": Q_by_node,
        "root": root,
        "pipes": pipes,
        "parent": parent,
        "order": order,
        "path_to_root": path_to_root,
        "children_map": children_map,
        "pair_to_pid": pair_to_pid,
        "supply_edges": supply_edges,
        "return_children_edges": return_children_edges,
        "pipe_UA_s": pipe_UA_s,
        "pipe_UA_a": pipe_UA_a,
        "T_sup_EH": T_sup_EH,
        "T_ret_EH": T_ret_EH,
        "P_pump": P_pump,
        "T_sup_node": T_sup_node,
        "T_ret_node": T_ret_node,
        "T_sup_pipe_out": T_sup_pipe_out,
        "T_ret_pipe_out": T_ret_pipe_out,
        "T_ret_building_SH": T_ret_building_SH,
        "T_ret_building_DHW": T_ret_building_DHW,
    }

def evaluate_hydraulics(t, pipe_massflows, pipes,
                        pipe_dict, path_to_root, building_nodes, rho,
                        nu_f, data, root):
    """
    Compute pressure losses and pump power for current flow state.
    """

    dp_substation = data.heat_grid_data.get("dp_substation")
    dp_energy_hub = data.heat_grid_data.get("dp_energy_hub")

    # total volumetric flow at root
    V_total = sum(
        m_arr[t] / rho
        for (par, ch), m_arr in pipe_massflows.items()
        if par == root
    )

    # Compute pressure losses per pipe and per path
    pipe_dp = {}

    # pipe-level dp (friction + local losses)
    for (par, ch), m_arr in pipe_massflows.items():
        pid = f"{par}->{ch}"
        pipe = pipes[pid]

        V = float(pipe["flow"][t])
        DN = pipe["DN"]

        d_i = pipe_dict[DN]["Inner diameter (pipe) (mm)"] / 1000.0
        rough = pipe_dict[DN]["Roughness (mm)"] / 1000.0
        L = pipe["length"]

        A = np.pi * d_i ** 2 / 4.0
        v = V / A if A > 0 else 0.0

        Re = v * d_i / nu_f if nu_f > 0 else 0.0

        f = fluids.friction.friction_factor(Re=Re, eD=rough / d_i)

        # friction (supply + return) + local losses
        dp = (2.0 * f * (L / d_i) * (rho * v ** 2 / 2.0) +
              pipe["zeta"] * (rho * v ** 2 / 2.0))


        pipe_dp[pid] = dp

    # path dp
    dp_path_by_node = {}
    dp_crit = 0.0

    for n in building_nodes:
        dp_path = sum(
            pipe_dp[f"{par}->{ch}"]
            for (par, ch) in path_to_root[n]
        ) + dp_substation

        dp_path_by_node[n] = dp_path
        dp_crit = max(dp_crit, dp_path)

    # add energy hub losses
    dp_total = dp_crit + dp_energy_hub

    # Required pump power
    eta_pump = data.heat_grid_data["pump"]["eta_pump"]
    P_required = dp_total * V_total / eta_pump

    return {
        "P_required": P_required,
        "dp_path_by_node": dp_path_by_node,
        "dp_total": dp_total,
        "pipe_dp": pipe_dp,
        "V_total": V_total
    }

def enforce_pump_constraint(
        t,
        param,
        building_nodes,
        path_to_root,
        hydraulics,
        data,
        P_pump_max,
        dp_pump_max,
        alpha):
    """
    Apply pump constraint by reducing building mass flows.
    Returns True if flows were modified.
    """

    P_required = hydraulics["P_required"]
    dp_required = hydraulics["dp_total"]

    # No constraint violation
    if P_required <= P_pump_max and dp_required <= dp_pump_max:
        return False  # no change

    dp_path_by_node = hydraulics["dp_path_by_node"]
    pipe_dp = hydraulics["pipe_dp"]

    # Fixed pressure losses (cannot be influenced)
    dp_substation = data.heat_grid_data.get("dp_substation")
    dp_energy_hub = data.heat_grid_data.get("dp_energy_hub")
    dp_fixed = dp_substation + dp_energy_hub

    # Critical path
    n_crit = max(dp_path_by_node, key=dp_path_by_node.get)
    critical_edges = set(path_to_root[n_crit])
    dp_crit_total = dp_path_by_node[n_crit] - dp_substation

    # Head constraint
    # Only the flow-dependent (pipe) losses can be reduced by lowering mass flow.
    # Since these losses scale ~ m^2, we scale flows with sqrt() so that
    # the total pressure drop (fixed + variable) matches the pump head limit.
    if dp_required > dp_pump_max:
        dp_var_required = dp_required - dp_fixed
        dp_var_max = dp_pump_max - dp_fixed
        r_dp = (dp_var_max / dp_var_required) ** 0.5
    else:
        r_dp = 1.0

    # Power constraint (approximate)
    if P_required > P_pump_max:
        # Pump power does not scale purely with m^3 because the total
        # pressure drop contains both fixed and flow-dependent parts.
        # Use a moderate reduction factor as a practical mixed-scaling approximation.
        r_power = (P_pump_max / P_required) ** 0.5
    else:
        r_power = 1.0

    # Final reduction factor
    base_reduction = min(r_dp, r_power)

    # Prevent increasing flows (Safety)
    base_reduction = min(base_reduction, 1.0)

    # Apply weighted reduction
    for n in building_nodes:
        # pressure contribution to critical path
        dp_overlap = sum(
            pipe_dp[f"{par}->{ch}"]
            for (par, ch) in path_to_root[n]
            if (par, ch) in critical_edges
        )

        # weight (avoid zero influence)
        weight = max(dp_overlap / dp_crit_total, 0.1)

        # blended reduction
        reduction = 1.0 - weight * (1.0 - base_reduction)

        # apply reduction
        param["building_massflow_SH"][n][t] *= reduction
        param["building_massflow_DHW"][n][t] *= reduction

        # enforce minimum flow
        m_SH_min = alpha * float(param["building_massflow_max_SH"][n])
        m_DHW_min = alpha * float(param["building_massflow_max_DHW"][n])

        param["building_massflow_SH"][n][t] = max(param["building_massflow_SH"][n][t], m_SH_min)
        param["building_massflow_DHW"][n][t] = max(param["building_massflow_DHW"][n][t], m_DHW_min)
        param["building_massflow_HX"][n][t] = (param["building_massflow_SH"][n][t] + param["building_massflow_DHW"][n][t])

    return True

def solve_network_temperatures(
        t, Ts, building_nodes,
        pipes, rho, c_f, T_soil,
        supply_edges, return_children_edges, order,
        pipe_UA_s,
        param,
        T_sup_req_by_node,
        T_ret_req_by_node_SH,
        T_ret_req_by_node_DHW,
        Q_SH_by_node,
        Q_DHW_by_node,
        root
):
    """
    Solve temperature field for one timestep with fixed Ts and fixed flows.
    """

    Tsoil_t = float(T_soil[t])

    T_sup_node_loc = {}
    T_ret_node_loc = {}
    T_sup_pipe_out_loc = {}
    T_ret_pipe_out_loc = {}
    T_ret_building_SH_loc = {}
    T_ret_building_DHW_loc = {}

    # Supply propagation
    T_sup_node_loc[root] = Ts

    for par, node, pid in supply_edges:
        flow_t = pipes[pid]["flow"][t]
        m_dot = float(flow_t) * rho
        T_sup_in = float(T_sup_node_loc[par])

        Tsup_out_child = single_pipe_temperature(
            T_in=T_sup_in,
            T_soil=Tsoil_t,
            m_dot=m_dot,
            UA=pipe_UA_s[pid],
            c_f=c_f
        )

        T_sup_pipe_out_loc[(par, node)] = Tsup_out_child
        T_sup_node_loc[node] = Tsup_out_child

    # Buildings
    heat_deficit_by_node = {}

    for bn in building_nodes:
        m_SH = float(param["building_massflow_SH"][bn][t])
        m_DHW = float(param["building_massflow_DHW"][bn][t])
        m_HX = float(param["building_massflow_HX"][bn][t])

        Q_SH_W = float(Q_SH_by_node[bn][t]) * 1000.0
        Q_DHW_W = float(Q_DHW_by_node[bn][t]) * 1000.0
        Ts_del = float(T_sup_node_loc[bn])

        Tr_req_SH = float(T_ret_req_by_node_SH[bn][t])
        Tr_req_DHW = float(T_ret_req_by_node_DHW[bn][t])

        # SH
        if Q_SH_W > 0.0:
            # heat extraction
            Q_SH_del = m_SH * c_f * (Ts_del - Tr_req_SH)
            Tr_SH = Tr_req_SH
        else:
            # no demand (pure circulation)
            Q_SH_del = 0.0
            Tr_SH = Ts_del

        # DHW
        if Q_DHW_W > 0.0:
            Q_DHW_del = m_DHW * c_f * (Ts_del - Tr_req_DHW)
            Tr_DHW = Tr_req_DHW
        else:
            Q_DHW_del = 0.0
            Tr_DHW = Ts_del

        T_ret_building_SH_loc[bn] = Tr_SH
        T_ret_building_DHW_loc[bn] = Tr_DHW

        # mixed return at substation
        Tr_HX = (m_SH * Tr_SH + m_DHW * Tr_DHW) / m_HX
        T_ret_node_loc[bn] = Tr_HX

        # unmet demand (if flow or Ts insufficient)
        heat_deficit_by_node[bn] = max(Q_SH_W - Q_SH_del, Q_DHW_W - Q_DHW_del, 0.0)

    # Return propagation
    for node in reversed(order):
        edges = return_children_edges.get(node)
        if not edges:
            continue

        m_sum = 0.0
        Tmix = 0.0

        for ch, pid in edges:
            flow_t = pipes[pid]["flow"][t]
            m_dot = flow_t * rho
            T_ret_in = float(T_ret_node_loc[ch])

            Tret_out_parent = single_pipe_temperature(
                T_in=T_ret_in,
                T_soil=Tsoil_t,
                m_dot=m_dot,
                UA=pipe_UA_s[pid],
                c_f=c_f
            )

            T_ret_pipe_out_loc[(node, ch)] = Tret_out_parent

            m_sum += m_dot
            Tmix += m_dot * Tret_out_parent

        T_ret_node_loc[node] = Tmix / m_sum

    Tr = float(T_ret_node_loc[root])

    # Supply deficit
    sup_deficit = 0.0

    for n in building_nodes:
        Ts_req = float(T_sup_req_by_node[n][t])
        Ts_del = float(T_sup_node_loc[n])
        sup_deficit = max(sup_deficit, Ts_req - Ts_del)

    return {
        "Tr": Tr,
        "T_sup_node": T_sup_node_loc,
        "T_ret_node": T_ret_node_loc,
        "T_sup_pipe_out": T_sup_pipe_out_loc,
        "T_ret_pipe_out": T_ret_pipe_out_loc,
        "T_ret_building_SH": T_ret_building_SH_loc,
        "T_ret_building_DHW": T_ret_building_DHW_loc,
        "sup_deficit": max(sup_deficit, 0.0),
        "heat_deficit_by_node": heat_deficit_by_node,
    }

def _finalize_network_temperature_solver(data, param, shared):
    data.heat_grid_data["T_supply_EH"] = shared["T_sup_EH"]
    data.heat_grid_data["T_return_EH"] = shared["T_ret_EH"]
    data.heat_grid_data["P_pump"] = shared["P_pump"]
    param["T_sup_pipe_out"] = shared["T_sup_pipe_out"]
    param["T_ret_pipe_out"] = shared["T_ret_pipe_out"]
    param["T_sup_node"] = shared["T_sup_node"]
    param["T_ret_node"] = shared["T_ret_node"]
    param["T_ret_building_SH"] = shared["T_ret_building_SH"]
    param["T_ret_building_DHW"] = shared["T_ret_building_DHW"]
    return data, param

def single_pipe_temperature(T_in, T_soil, m_dot, UA, c_f):
    return float(T_soil) + (float(T_in) - float(T_soil)) * np.exp(-UA / (m_dot * c_f))

def prepare_result_folder(data, param):
    """
    Create the result directory used to store network design outputs.
    """

    dir_dia = os.path.join(data.resultPath, "network")
    os.makedirs(dir_dia, exist_ok=True)

    topology = data.heat_grid_data["topology_option"]
    result_folder = f"{data.scenario_name}_{topology}"

    dir_result = os.path.join(dir_dia, result_folder)
    os.makedirs(dir_result, exist_ok=True)

    param["dir_result"] = dir_result

    return dir_result

def to_jsonable(obj):
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, tuple):
        return list(obj)
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    return obj

##############################################################################################################################
##############################################################################################################################
# NOT USED FUNCTIONS
##############################################################################################################################
##############################################################################################################################
def compute_network_temperatures_twin_pipe_auto(data, param, max_iter=20, tol=0.5, relax=0.5):
    """
    Twin-pipe network temperature solver with coupled supply/return iteration.
    """

    shared = _prepare_network_temperature_solver(data, param)

    topo = shared["topo"]
    pipe_dict = shared["pipe_dict"]
    dp_pipe_max = shared["dp_pipe_max"]
    nu_f = shared["nu_f"]
    c_f = shared["c_f"]
    rho = shared["rho"]
    T_soil = shared["T_soil"]
    T_len = shared["T_len"]
    T_sup_req_by_node = shared["T_sup_req_by_node"]
    T_ret_req_by_node_SH = shared["T_ret_req_by_node_SH"]
    T_ret_req_by_node_DHW = shared["T_ret_req_by_node_DHW"]
    Q_SH_by_node = shared["Q_SH_by_node"]
    Q_DHW_by_node = shared["Q_DHW_by_node"]
    Q_by_node = shared["Q_by_node"]
    root = shared["root"]
    pipes = shared["pipes"]
    order = shared["order"]
    path_to_root = shared["path_to_root"]
    supply_edges = shared["supply_edges"]
    return_children_edges = shared["return_children_edges"]
    pipe_UA_s = shared["pipe_UA_s"]
    pipe_UA_a = shared["pipe_UA_a"]

    T_sup_EH = shared["T_sup_EH"]
    T_ret_EH = shared["T_ret_EH"]
    T_sup_node = shared["T_sup_node"]
    T_ret_node = shared["T_ret_node"]
    T_sup_pipe_out = shared["T_sup_pipe_out"]
    T_ret_pipe_out = shared["T_ret_pipe_out"]
    T_ret_building_SH = shared["T_ret_building_SH"]
    T_ret_building_DHW = shared["T_ret_building_DHW"]

    alpha = data.heat_grid_data["min_flow_fraction"]

    # Simulation per timestep
    for t in tqdm(range(T_len), desc="Solving network temperatures", unit="timestep"):

        # Nodes representing buildings (substations) connected to the network.
        building_nodes = list(Q_by_node.keys())

        # Initial temperature guesses
        # The supply temperature at the energy hub (Ts) is initialized as the design supply
        # temperature which is the maximum required supply temperature among all  buildings
        # at timestep t. The return temperature at the energy hub (Tr) is initialized using
        # a fixed temperature difference relative to the supply temperature
        Ts = float(param["T_sup_design"][t])
        Tr = Ts - 15.0 if t == 0 else float(T_ret_EH[t - 1])

        # The outer control loop adjusts the energy-hub supply temperature and the
        # building-specific mass flows in order to satisfy thermal constraints.
        # - Supply temperature deficits are corrected by increasing the
        #   energy-hub supply temperature.
        # - Return temperature deficits are corrected locally by increasing the
        #   mass flow at the affected building substations, as long as the
        #   hydraulic pressure-drop limit is not exceeded.
        # - The interaction between thermal and hydraulic effects is explicitly considered:
        #     * Increasing mass flow reduces pipe heat losses and can improve supply
        #       temperatures at downstream nodes.
        #     * Increasing Ts raises both supply and return temperatures across the network.
        # - The Ts update is adaptively damped based on:
        #     * whether return-temperature deficits are improving between iterations, and
        #     * whether further flow increases are hydraulically feasible.
        flow_scale_by_node = {n: 1.0 for n in building_nodes}
        flow_increase_factor = 1.10
        ts_update_factor = 0.50
        prev_ret_deficit = np.inf

        # Reuse the previous inner-loop return profile as the initial guess for the
        # next outer control iteration of the same timestep.
        Tret_prev_cache = None

        for control_iter in range(max_iter):

            flow_blocked = True

            # Reset building mass flows to their original design values and apply a
            # building-specific scaling factor. The same scaling factor is applied to
            # both SH and DHW flows, assuming a single control action (valve opening)
            # that proportionally affects the total primary-side mass flow through
            # the substation heat exchanger.
            for n in building_nodes:
                scale = flow_scale_by_node[n]

                param["building_massflow_SH"][n][t] = (param["building_massflow_SH_design"][n][t] * scale)
                param["building_massflow_DHW"][n][t] = (param["building_massflow_DHW_design"][n][t] * scale)
                param["building_massflow_HX"][n][t] = (
                        param["building_massflow_SH"][n][t] +
                        param["building_massflow_DHW"][n][t])

            # Aggregate the updated building mass flows to pipe mass flows.
            pipe_massflows = aggregate_mass_flows(
                topo,
                param["building_massflow_HX"],
                root=root
            )

            for (parent_node, child_node), m_arr in pipe_massflows.items():
                pid = f"{parent_node}->{child_node}"
                pipes[pid]["flow"][t] = m_arr[t] / rho

            Tsoil_t = float(T_soil[t])

            # Previous iterate segment temperatures used as coupling references
            if Tret_prev_cache is None:
                Tret_prev = {}
                for par, node, pid in supply_edges:
                    Tret_prev[(par, node)] = Tr
            else:
                Tret_prev = Tret_prev_cache.copy()

            # Fixed-point iteration for the temperature field at fixed Ts and fixed flows.
            # In this inner loop, Ts is not changed. Only the coupled supply/return
            # temperature field is iterated to convergence.
            for _ in range(max_iter):
                Tr_old = Tr

                # Forward pass (supply)
                T_sup_node[root][t] = Ts

                Tsup_new = {}

                # propagate along edges
                for par, node, pid in supply_edges:
                    flow_t = pipes[pid]["flow"][t]  # m3/s
                    m_dot = float(flow_t) * rho  # kg/s

                    T_sup_in = float(T_sup_node[par][t])

                    # During the supply propagation, the return temperature in each pipe segment is
                    # temporarily assumed equal to its value from the previous iteration in order
                    # to compute the new supply temperature.
                    T_ret_ref = float(Tret_prev[(par, node)])

                    Tsup_out_child, _ = twin_pipe_temperatures(
                        Tsup_in_parent=T_sup_in,
                        Tret_in_child=T_ret_ref,
                        T_soil=Tsoil_t,
                        m_dot=m_dot,
                        UA_s=pipe_UA_s[pid],
                        UA_a=pipe_UA_a[pid],
                        c_f=c_f)

                    T_sup_pipe_out[(par, node)][t] = Tsup_out_child  # the supply temperature at the outlet of the pipe connecting par→node
                    T_sup_node[node][t] = Tsup_out_child  # the supply temperature assigned to the node itself
                    Tsup_new[(par, node)] = Tsup_out_child

                # Backward pass (return)
                # initialize return temps to current guess
                for n in order:
                    T_ret_node[n][t] = Tr

                # building return temperatures for active nodes based on energy balance.
                for bn in building_nodes:

                    m_SH = float(param["building_massflow_SH"][bn][t])
                    m_DHW = float(param["building_massflow_DHW"][bn][t])
                    m_HX = float(param["building_massflow_HX"][bn][t])

                    Q_SH_W = float(Q_SH_by_node[bn][t]) * 1000.0  # W
                    Q_DHW_W = float(Q_DHW_by_node[bn][t]) * 1000.0  # W

                    Ts_del = float(T_sup_node[bn][t])

                    # energy balance return temperature
                    Tr_SH = Ts_del - Q_SH_W / (m_SH * c_f)
                    Tr_DHW = Ts_del - Q_DHW_W / (m_DHW * c_f)

                    T_ret_building_SH[bn][t] = Tr_SH
                    T_ret_building_DHW[bn][t] = Tr_DHW

                    Tr_HX = (m_SH * Tr_SH + m_DHW * Tr_DHW) / m_HX
                    T_ret_node[bn][t] = Tr_HX

                Tret_new = {}

                for node in reversed(order):
                    edges = return_children_edges.get(node)
                    if not edges:
                        continue

                    m_sum = 0.0
                    Tmix = 0.0

                    for ch, pid in edges:
                        flow_t = pipes[pid]["flow"][t]
                        m_dot = flow_t * rho

                        T_ret_in = float(T_ret_node[ch][t])

                        # Frozen reference from current supply pass:
                        # use supply temperature at downstream side of segment
                        T_sup_ref = float(Tsup_new[(node, ch)])

                        _, Tret_out_parent = twin_pipe_temperatures(
                            Tsup_in_parent=T_sup_ref,
                            Tret_in_child=T_ret_in,
                            T_soil=Tsoil_t,
                            m_dot=m_dot,
                            UA_s=pipe_UA_s[pid],
                            UA_a=pipe_UA_a[pid],
                            c_f=c_f)

                        T_ret_pipe_out[(node, ch)][t] = Tret_out_parent
                        Tret_new[(node, ch)] = Tret_out_parent

                        m_sum += m_dot
                        Tmix += m_dot * Tret_out_parent

                    T_ret_node[node][t] = Tmix / m_sum if m_sum > 0.0 else Tr

                Tr_new = float(T_ret_node[root][t])

                # Relaxation
                Tr = (1.0 - relax) * Tr + relax * Tr_new

                # update coupling references for next fixed-point iterate
                for edge in Tret_prev:
                    if edge in Tret_new:
                        Tret_prev[edge] = (1.0 - relax) * Tret_prev[edge] + relax * Tret_new[edge]

                if abs(Tr - Tr_old) < tol:
                    break

            # Cache converged/last inner-loop return profile for the next outer control iteration.
            Tret_prev_cache = Tret_prev.copy()

            # Evaluate deficits after the temperature field has converged
            sup_deficit = 0.0
            ret_deficit_by_node = {}

            for n in building_nodes:
                Ts_req = float(T_sup_req_by_node[n][t])
                Ts_del = float(T_sup_node[n][t])
                sup_deficit = max(sup_deficit, Ts_req - Ts_del)

                Tr_req_SH = float(T_ret_req_by_node_SH[n][t])
                Tr_calc_SH = float(T_ret_building_SH[n][t])

                Tr_req_DHW = float(T_ret_req_by_node_DHW[n][t])
                Tr_calc_DHW = float(T_ret_building_DHW[n][t])

                ret_def = max(Tr_req_SH - Tr_calc_SH, Tr_req_DHW - Tr_calc_DHW, 0.0)

                ret_deficit_by_node[n] = ret_def

            sup_deficit = max(sup_deficit, 0.0)
            max_ret_deficit = max(ret_deficit_by_node.values()) if ret_deficit_by_node else 0.0

            # Stop if all temperature constraints are met.
            if (sup_deficit <= tol) and (max_ret_deficit <= tol):
                break

            # Correct return-temperature deficits by locally increasing the mass flow
            # at individual building substations.
            # The hydraulic feasibility of this increase is then checked along the
            # path between the energy hub and the respective building. Since the
            # network is modeled as a tree with demand-driven flow aggregation,
            # only pipes along this path are affected by the change in flow.
            # If the allowable pressure-gradient limit is exceeded in any pipe
            # along this path, the flow increase for this building is rejected.
            for n in building_nodes:

                if ret_deficit_by_node[n] <= tol:
                    continue

                # try increasing only for this building
                proposed_scale = flow_scale_by_node[n] * flow_increase_factor

                # temporarily apply
                old_scale = flow_scale_by_node[n]
                flow_scale_by_node[n] = proposed_scale

                # recompute flows
                for bn in building_nodes:
                    scale = flow_scale_by_node[bn]

                    param["building_massflow_SH"][bn][t] = (
                            param["building_massflow_SH_design"][bn][t] * scale)
                    param["building_massflow_DHW"][bn][t] = (
                            param["building_massflow_DHW_design"][bn][t] * scale)
                    param["building_massflow_HX"][bn][t] = (
                            param["building_massflow_SH"][bn][t] +
                            param["building_massflow_DHW"][bn][t])

                pipe_massflows = aggregate_mass_flows(
                    topo,
                    param["building_massflow_HX"],
                    root=root)

                # assign temporary flows
                for (par, ch), m_arr in pipe_massflows.items():
                    pid = f"{par}->{ch}"
                    pipes[pid]["flow"][t] = m_arr[t] / rho

                # check only path to this building
                violation = False
                for (par, ch) in path_to_root[n]:
                    pid = f"{par}->{ch}"
                    pipe = pipes[pid]

                    V = float(pipe["flow"][t])
                    DN = pipe["DN"]

                    d_i = pipe_dict[DN]["Inner diameter (pipe) (mm)"] / 1000.0
                    rough = pipe_dict[DN]["Roughness (mm)"] / 1000.0

                    A = np.pi * d_i ** 2 / 4.0
                    v = V / A if A > 0 else 0.0

                    Re = v * d_i / nu_f if nu_f > 0 else 0.0

                    if Re > 0:
                        f = fluids.friction.friction_factor(Re=Re, eD=rough / d_i)
                        dp_per_m = f * rho * v ** 2 / (2.0 * d_i)
                    else:
                        dp_per_m = 0.0

                    if dp_per_m > dp_pipe_max:
                        violation = True
                        break

                # Accept or reject the proposed flow increase based on hydraulic feasibility.
                # If the pressure-gradient constraint is violated in any pipe along the path,
                # the flow increase is rejected and the previous scaling is restored.
                # Otherwise, the increase is accepted.
                if violation:
                    flow_scale_by_node[n] = old_scale  # revert
                else:
                    flow_blocked = False

            # If at least one flow increase was accepted, restart the outer loop.
            # This gives the solver the opportunity to exploit the reduction in pipe
            # heat losses before increasing the plant supply temperature.
            if not flow_blocked:
                continue

            # Correct supply-temperature deficits by increasing the energy-hub supply temperature (Ts).
            # The update is adaptively damped to account for the coupled thermo-hydraulic behavior:
            # - If flow increases are blocked by hydraulic constraints, Ts becomes the only
            #   remaining control variable and is therefore adjusted more aggressively.
            # - If return-temperature deficits are improving between iterations, this indicates
            #   that flow adjustments are effective, so Ts is increased moderately.
            # - If neither condition is met, a conservative update is applied to avoid overshooting,
            #   since future flow adjustments may still improve the temperature distribution.
            # This strategy balances the interaction between flow-driven heat-loss reduction
            # and direct temperature increase at the energy hub.
            if sup_deficit > tol:
                improving = max_ret_deficit < prev_ret_deficit
                if flow_blocked:
                    beta = 1.0  # hydraulics limit → must rely on Ts
                elif improving:
                    beta = 0.7  # flow helping → moderate Ts increase
                else:
                    beta = 0.3  # flow not helping → be conservative
                Ts += ts_update_factor * beta * sup_deficit

            prev_ret_deficit = max_ret_deficit

        else:
            print(f"[WARNING] Timestep {t}: control loop not converged")

        T_sup_EH[t] = Ts
        T_ret_EH[t] = Tr

    return _finalize_network_temperature_solver(data, param, shared)

def twin_pipe_temperatures(Tsup_in_parent, Tret_in_child, T_soil, m_dot, UA_s, UA_a, c_f):
    """
    Compute the outlet temperatures of a twin-pipe district heating segment

    The model describes a buried supply and return pipe exchanging heat with
    the surrounding soil and with each other.

    Governing energy balances along the pipe:

        m_dot * c_f * dTsup/dx = -q_sup
        m_dot * c_f * dTret/dx =  q_ret

    Using the DIN EN 13941 heat-loss decomposition:

        q_sup = UA_s * ((Tsup + Tret)/2 - T_soil) + UA_a * ((Tsup - Tret)/2)
        q_ret = UA_s * ((Tsup + Tret)/2 - T_soil) - UA_a * ((Tsup - Tret)/2)

    where

        UA_s : symmetric heat loss to the soil
        UA_a : antisymmetric heat exchange between the two pipes

    For the analytical solution the temperatures are written relative to soil:

        θ_sup = Tsup - T_soil
        θ_ret = Tret - T_soil

    and transformed into

        u = (θ_sup + θ_ret) / 2   -> average pipe temperature above soil
        v = (θ_sup - θ_ret) / 2   -> half the supply-return temperature difference

    which leads to the coupled system

        u' = -Ka * v
        v' = -Ks * u

    with

        Ks = UA_s / (m_dot * c_f)
        Ka = UA_a / (m_dot * c_f)

    Solving this system yields hyperbolic functions (cosh/sinh).

    Counterflow boundary conditions:

        Tsup(0) = Tsup_in_parent
        Tret(1) = Tret_in_child

    giving the temperatures at the opposite ends:

        Tsup_out_child
        Tret_out_parent

    Parameters
    ----------
    Tsup_in_parent : float
        Supply temperature entering the pipe at the parent node [°C].

    Tret_in_child : float
        Return temperature entering the pipe from the child node [°C].

    T_soil : float
        Soil temperature surrounding the pipe [°C].

    m_dot : float
        Mass flow rate of the fluid [kg/s].

    UA_s : float
        Symmetric heat loss coefficient to soil [W/K].

    UA_a : float
        Antisymmetric heat transfer coefficient between pipes [W/K].

    c_f : float
        Fluid specific heat capacity [J/(kg*K)].

    Returns
    -------
    Tsup_out_child : float
        Supply temperature at the downstream (child) end of the pipe [°C].

    Tret_out_parent : float
        Return temperature at the upstream (parent) end of the pipe [°C].
    """

    # Convert heat-transfer coefficients to decay rates
    Ks = UA_s / (m_dot * c_f)
    Ka = UA_a / (m_dot * c_f)

    # Temperatures relative to soil temperature
    a = float(Tsup_in_parent) - float(T_soil)  # θ_sup at x = 0
    b = float(Tret_in_child) - float(T_soil)  # θ_ret at x = 1

    # Parameter controlling exponential decay
    mu = math.sqrt(Ks * Ka)

    # Ratio of symmetric to antisymmetric decay
    r = math.sqrt(Ks / Ka)

    # Hyperbolic functions from analytical solution
    sh = math.sinh(mu)
    ch = math.cosh(mu)

    # Solve integration constants from boundary conditions
    denom = (1.0 + r * r) * sh + 2.0 * r * ch

    C2 = (b - a * (ch + r * sh)) / denom
    C1 = a + r * C2

    # Supply temperature at downstream end (child node)
    Tsup_out_child = float(T_soil) + (
            C1 * (ch - r * sh) +
            C2 * (sh - r * ch)
    )

    # Return temperature arriving at upstream end (parent node)
    Tret_out_parent = float(T_soil) + (C1 + r * C2)

    return Tsup_out_child, Tret_out_parent