# -*- coding: utf-8 -*-

import numpy as np
import math
import os
import json
import fluids
from scipy.interpolate import interp1d
import pandas as pd

def network_design(data):
    """
    Main workflow for the district heating network design.

    The network is designed using fixed design mass flows derived from
    building heat demand and required temperature levels.

    Pipe diameters are selected based on hydraulic constraints
    (pressure gradient and velocity limits).

    Pump power is then calculated based on friction and local pressure
    losses along all network branches. A single circulation pump is
    assumed at the energy hub (EH), and the required pump head is
    determined from the hydraulically most demanding branch.

    Important modelling assumption
    -------------------------------
    Mass flows are determined once from building heat demand and
    required temperature difference and remain constant during the
    design process.

    Steps
    -----
    1. Load and prepare network parameters
    2. Compute design mass flows in the network
    3. Size pipe diameters based on hydraulic limits
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

    return data, param

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