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
# from districtgenerator.functions.load_params_central_devices import calc_COP

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

    # 4. Solve network temperatures
    data, param = compute_network_temperatures(data, param)

    # 5. Calculate pipe heat losses
    data, param = calc_heat_loss_pipe(data, param)

    # 6. Compute pump power
    data, param = compute_pump_power(data, param)

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

        heating_demand = np.maximum(heating + dhw - generationSTC, 0)  # kW
        building["user"].heating_demand = heating_demand  # kW

        # Additional heat required to cover substation heat losses
        subst_loss = heating_demand * (h_loss_subst / 100)
        heat_loss_substation += subst_loss                # kW

        # Total heat demand supplied by the network
        # (building demand + substation heat losses)
        net_heat_demand += heating_demand + subst_loss

    # Build temperature requirements and loads per pipeline node (Building)
    T_sup_req_by_node = {}
    T_ret_req_by_node = {}
    Q_by_node = {}

    # todo: check later if we have it in the config
    dT_HX_sup = 8.0 # K  minimum temperature difference required between the primary supply (network) and the secondary supply (building heating system)
    dT_HX_ret = 4.0 # K  minimum temperature difference required between the primary return (network) and the secondary return (building heating system)

    # DHW requirements
    # °C domestic hot water temperature todo: check later if we have it in the config
    T_dhw_required = 50.0

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
        Tr_req_DHW = T_dhw_required + dT_HX_ret

        # If domestic hot water is demanded, the network supply
        # temperature must at least meet the DHW heat exchanger
        # requirement
        dhw_load = np.asarray(building["user"].dhw, dtype=float) / 1000.0  # kW
        sh_load = np.asarray(building["user"].heat, dtype=float) / 1000.0  # kW

        # Supply temperature constraint
        Ts_req = Ts_req_SH.copy()
        dhw_mask = dhw_load > 0
        Ts_req[dhw_mask] = np.maximum(Ts_req_SH[dhw_mask], Ts_req_DHW)

        # Return temperature mixing
        # The building return temperature is computed as the
        # mass-flow weighted mixture of the space heating (SH)
        # and domestic hot water (DHW) return streams.
        # Mass flows are derived from load / temperature difference

        Tr_req = Tr_req_SH.copy()

        deltaT_SH = Ts_req_SH - Tr_req_SH
        deltaT_DHW = Ts_req_DHW - Tr_req_DHW

        # Avoid division by zero / invalid ΔT
        eps_dT = 1e-6  # K
        eps_m = 1e-12
        valid_SH = deltaT_SH > eps_dT

        m_SH = np.zeros_like(sh_load, dtype=float)
        m_DHW = np.zeros_like(dhw_load, dtype=float)

        m_SH[valid_SH] = sh_load[valid_SH] / deltaT_SH[valid_SH]
        m_DHW = dhw_load / deltaT_DHW

        m_tot = m_SH + m_DHW

        # cases:
        # - only SH active -> Tr_req already equals Tr_req_SH
        # - only DHW active -> set to Tr_req_DHW
        dhw_only = (m_DHW > 0) & (m_SH <= 0)
        Tr_req[dhw_only] = Tr_req_DHW

        # both active -> mix
        both = (m_SH > 0) & (m_DHW > 0) & (m_tot > eps_m)
        Tr_req[both] = (m_SH[both] * Tr_req_SH[both] + m_DHW[both] * Tr_req_DHW) / m_tot[both]

        # Building heat load
        Q = np.asarray(building["user"].heating_demand, dtype=float)
        Q = Q * (1.0 + h_loss_subst / 100.0)

        T_sup_req_by_node[node_key] = Ts_req
        T_ret_req_by_node[node_key] = Tr_req
        Q_by_node[node_key] = Q

    # store them into param
    param["T_sup_req_by_node"] = T_sup_req_by_node
    param["T_ret_req_by_node"] = T_ret_req_by_node
    param["Q_by_node"] = Q_by_node

    # Automatic pipe type selection (only if generation="auto")
    gen = str(data.heat_grid_data["generation"]).lower()

    if gen == "auto":

        Ts_max = max(np.max(Ts) for Ts in T_sup_req_by_node.values())

        if Ts_max > 60:
            gen_auto = "3rd"
        elif Ts_max > 35:
            gen_auto = "4th"
        else:
            gen_auto = "5th"

        if gen_auto == "3rd":
            data.pipe_data = data.pipe_data_all["3rd"]

        elif gen_auto == "4th":
            pmr_data = data.pipe_data_all["4th"]
            kmr_data = data.pipe_data_all["3rd"]

            # add KMR pipes for DN > 150
            kmr_large = kmr_data[kmr_data["Nominal diameter (DN)"] > 150]
            data.pipe_data = pd.concat([pmr_data, kmr_large], ignore_index=True)

        elif gen_auto == "5th":
            data.pipe_data = data.pipe_data_all["5th"]

        print(
            f"[INFO] Automatic pipe generation selection: {gen_auto} generation "
            f"(max required supply temperature = {Ts_max:.1f}°C)"
        )

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
    path = extract_longest_branches(network)

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
    param["path"] = path
    param["HP_ann_factor"] = HP_ann_factor

    T_sup_cfg, T_ret_cfg = get_configured_network_temperatures(data)
    param["T_sup_network_config"] = T_sup_cfg
    param["T_ret_network_config"] = T_ret_cfg

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
    h_loss_subst = data.heat_grid_data["h_loss_subst"]         # 5%, Heat losses at the substation

    T_sup_req_by_node = param["T_sup_req_by_node"]
    T_ret_req_by_node = param["T_ret_req_by_node"]

    # Determine the assumed supply temperature used to calculate
    # the mass flows at the building-level in the network.

    # Two operating modes are possible:
    # 1) Automatic temperature mode (generation = "auto"):
    #    The supply temperature is taken as the maximum supply
    #    temperature required by any connected building at each timestep.
    # 2) Generation-dependent temperature mode (generation = "3rd", "4th", "5th"):
    #    The supply temperature is predefined by the network configuration
    #    (constant value or heating curve).
    T_sup_cfg = param.get("T_sup_network_config", None)

    if T_sup_cfg is None:
        Ts_matrix = np.vstack(list(T_sup_req_by_node.values()))
        T_sup_network = np.max(Ts_matrix, axis=0)
    else:
        T_sup_network = np.asarray(T_sup_cfg, dtype=float)

    param["T_sup_network_for_flow"] = T_sup_network

    # Lookup: building position -> node id
    node_lookup = {
        tuple(node_info["pos"]): key
        for key, node_info in data.pipeline_nodes.items()
    }

    building_massflow = {}  # kg/s arrays

    # Building demand + building mass flow
    for building in data.district:

        if building["buildingFeatures"]["heater"] != "heat_grid":
            continue

        pos_building = tuple(building["buildingFeatures"]["position"])
        node_key = node_lookup.get(pos_building)
        if node_key is None:
            continue

        # heat demand including substation losses (kW)
        demand = building["user"].heating_demand * (1 + h_loss_subst / 100)
        # ignore very small loads (< 50 W)
        demand = np.where(demand < 0.05, 0.0, demand)

        # use the network supply temperature instead of the building-specific
        # supply requirement. Buildings regulate heat extraction via control
        # valves, so the mass flow depends on the available network supply
        # temperature and the required return temperature of the building.
        Ts = T_sup_network
        Tr = T_ret_req_by_node[node_key]
        deltaT = np.maximum(Ts - Tr, 1.0)

        # kg/s
        m_dot = demand * 1000 / (c_f * deltaT)
        building_massflow[node_key] = m_dot

    # Aggregate mass flows along the network
    network = data.pipeline_topology
    building_massflow = enforce_min_leaf_circulation(building_massflow, network, param, root="EH1")
    pipe_massflows = aggregate_mass_flows(network, building_massflow, root="EH1")

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

        # convert kg/s → m³/s
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
    dp_pipe_max = data.heat_grid_data["pipe"]["dp_pipe_max"]     # 300Pa/m,      maximum pipe pressure gradient (Planungshandbuch Fernwärme)
    dp_pipe_min = data.heat_grid_data["pipe"]["dp_pipe_min"]    # 30Pa/m,       minimum pipe pressure gradient (Source: Improved genetic algorithm for pipe diameter optimization of an existing large-scale district heating network https://doi.org/10.1016/j.energy.2024.131970)

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
            if dp_pipe_min <= dp_per_m <= dp_pipe_max:
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

def compute_network_temperatures(data, param, max_iter=20, tol=1e-1, relax=0.5):
    """
    Solve the supply and return temperature distribution
    in the district heating network for all timesteps.

    Full twin-pipe heat transfer model including thermal interaction between
    supply and return pipes. Uses the symmetrical and antisymmetrical heat
    loss factors according to DIN EN 13941 and solves the analytical
    counter-flow twin-pipe equations.

    For each timestep a steady-state temperature propagation
    through the network is solved while considering pipe heat losses.

    The solver assumes fixed pipe mass flows (determined earlier
    during the design stage).

    The solver performs a temperature propagation:

    Supply Flow:
        Forward propagation from the plant (root) to all nodes.

    Return Flow:
        Backward propagation from buildings to the plant.
        Return streams from multiple branches are mixed
        using mass-flow weighted averaging.

    The plant supply temperature is iteratively adjusted until
    all active buildings receive at least their required supply
    temperature after accounting for pipe heat losses.

    Returns
    -------
    T_sup_EH : ndarray
        Required supply temperature at plant.

    T_ret_EH : ndarray
        Return temperature arriving at plant.

    T_sup_node : dict
        Supply temperature at each node (after pipe decay).

    T_ret_node : dict
        Mixed return temperature at each node.

    T_sup_pipe_out : dict
        Supply pipe outlet temperature (before mixing with other branches).

    T_ret_pipe_out : dict
        Return pipe outlet temperature (before mixing with other branches).
    """

    generation = str(data.heat_grid_data.get("generation", "auto")).lower()

    if generation != "auto":
        return compute_network_temperatures_fixed_generation(data, param)

    topo = data.pipeline_topology
    pipe_dict = param["pipe_dict"]

    c_f = data.heat_grid_data["fluid"]["c_f"]   # J/kgK
    rho = data.heat_grid_data["fluid"]["rho_f"] # kg/m3
    k_soil = data.heat_grid_data["k_soil"]

    # soil temperature profile
    T_soil = data.heat_grid_data["T_soil"]  # ndarray [t], °C
    T_len = len(T_soil)

    T_sup_req_by_node = param["T_sup_req_by_node"]
    T_ret_req_by_node = param["T_ret_req_by_node"]
    Q_by_node = param["Q_by_node"]
    root = "EH1"

    # numerical threshold
    Q_eps = 1e-2  # kW minimum relevant building load

    pipes = data.pipeline
    circ_nodes = param.get("circulation_leaves", [])

    # Precompute parent map and topological order
    parent = {}
    order = []

    def dfs(node):
        order.append(node)
        for ch in topo.get(node, []):
            parent[ch] = node
            dfs(ch)

    dfs(root)

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

    T_sup_node = {n: np.zeros(T_len) for n in order}
    T_ret_node = {n: np.zeros(T_len) for n in order}

    T_sup_pipe_out = {(p["from"], p["to"]): np.zeros(T_len) for p in pipes.values()}
    T_ret_pipe_out = {(p["from"], p["to"]): np.zeros(T_len) for p in pipes.values()}

    # Main timestep loop
    Q_items = list(Q_by_node.items())

    def twin_pipe_step_counterflow(Tsup_in_parent, Tret_in_child, T_soil, m_dot, UA_s, UA_a, c_f):
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

    # Simulation per timestep
    for t in tqdm(range(T_len), desc="Solving network temperatures", unit="timestep"):

        # Treat below as inactive to avoid numerical noise
        active_nodes = [n for (n, q) in Q_items if float(q[t]) > Q_eps]

        # Initial temperature guesses
        # The supply temperature at the energy hub (Ts) is initialized as the
        # maximum required supply temperature among all active buildings at timestep t.
        # The return temperature (Tr) is initialized as the mean return temperature
        # requirement of the active buildings.
        if active_nodes:
            Ts = max(float(T_sup_req_by_node[n][t]) for n in active_nodes)
            # for Tr, a safer guess is a load-weighted average, but min is okay if you clamp
            Tr = float(np.mean([float(T_ret_req_by_node[n][t]) for n in active_nodes]))
        else:
            # no demand anywhere: keep a reasonable standby
            Ts = float(np.mean([float(T_sup_req_by_node[n][t]) for n in T_sup_req_by_node]))
            Tr = float(np.mean([float(T_ret_req_by_node[n][t]) for n in T_ret_req_by_node]))

        Tsoil_t = float(T_soil[t])

        # Previous iterate segment temperatures used as coupling references
        Tsup_prev = {}
        Tret_prev = {}
        for par, node, pid in supply_edges:
            Tsup_prev[(par, node)] = Ts
            Tret_prev[(par, node)] = Tr

        # Fixed-point iteration for (Ts, Tr)
        for _ in range(max_iter):
            Ts_old = Ts
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

                Tsup_out_child, _ = twin_pipe_step_counterflow(
                    Tsup_in_parent=T_sup_in,
                    Tret_in_child=T_ret_ref,
                    T_soil=Tsoil_t,
                    m_dot=m_dot,
                    UA_s=pipe_UA_s[pid],
                    UA_a=pipe_UA_a[pid],
                    c_f=c_f
                )

                T_sup_out = Tsup_out_child

                T_sup_pipe_out[(par, node)][t] = T_sup_out  # the supply temperature at the outlet of the pipe connecting par→node
                T_sup_node[node][t] = T_sup_out             # the supply temperature assigned to the node itself
                Tsup_new[(par, node)] = T_sup_out

            # Supply deficit and Ts update target
            deficit = 0.0
            for n in active_nodes:
                req = float(T_sup_req_by_node[n][t])
                got = float(T_sup_node[n][t])
                if np.isfinite(got):
                    deficit = max(deficit, req - got)

            deficit = max(deficit, 0.0)
            Ts_new = Ts + deficit

            # Backward pass (return)
            # initialize return temps to current guess
            for n in order:
                T_ret_node[n][t] = Tr

            # (A) building return temperatures for active nodes based on energy balance.
            for bn in active_nodes:

                # Identify the pipe feeding the building
                par = parent.get(bn)
                pid = pair_to_pid[(par, bn)]

                flow_t = pipes[pid]["flow"][t]
                m_dot = flow_t * rho

                Q_W = float(Q_by_node[bn][t]) * 1000.0  # W
                Ts_del = float(T_sup_node[bn][t])

                # energy balance return temperature
                Tr_act = Ts_del - Q_W / (m_dot * c_f)
                T_ret_node[bn][t] = Tr_act

                # Diagnostic check: building return below design return temperature
                Tr_req = float(T_ret_req_by_node[bn][t])
                dT_HX = 4  # todo:config
                if Tr_act < Tr_req - dT_HX:
                    raise ValueError(
                        f"Return temperature violation at timestep {t}, node {bn}: "
                        f"{Tr_act:.2f} °C is below required limit "
                        f"{Tr_req - dT_HX:.2f} °C (design return {Tr_req:.2f} °C)."
                    )

            # (B) Circulation nodes (buildings where minimum circulation flow was enforced earlier).
            # These nodes have non-zero flow even when the connected building has no heat demand (because of the circulation)
            # In that case the water does not pass through a heat exchanger but bypasses the building.
            # Physically this represents a circulation or bypass valve used to
            # maintain minimum branch flow and avoid stagnation.
            # Since no heat is extracted (Q = 0), the return temperature must equal the
            # delivered supply temperature:
            if circ_nodes:
                for cn in circ_nodes:
                    if cn not in active_nodes:
                        T_ret_node[cn][t] = T_sup_node[cn][t]

            # propagate return upstream with pipe cooling + mixing
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

                    _, Tret_out_parent = twin_pipe_step_counterflow(
                        Tsup_in_parent=T_sup_ref,
                        Tret_in_child=T_ret_in,
                        T_soil=Tsoil_t,
                        m_dot=m_dot,
                        UA_s=pipe_UA_s[pid],
                        UA_a=pipe_UA_a[pid],
                        c_f=c_f
                    )
                    T_ret_arrive = Tret_out_parent

                    T_ret_pipe_out[(node, ch)][t] = T_ret_arrive
                    Tret_new[(node, ch)] = T_ret_arrive

                    m_sum += m_dot
                    Tmix += m_dot * T_ret_arrive

                if m_sum > 0.0:
                    T_ret_node[node][t] = Tmix / m_sum
                else:
                    T_ret_node[node][t] = Tr

            Tr_new = float(T_ret_node[root][t])

            # Relaxation
            Ts = (1.0 - relax) * Ts + relax * Ts_new
            Tr = (1.0 - relax) * Tr + relax * Tr_new

            # update coupling references for next fixed-point iterate
            Tsup_prev = Tsup_new
            Tret_prev = Tret_new

            if max(abs(Ts - Ts_old), abs(Tr - Tr_old)) < tol:
                break

        T_sup_EH[t] = Ts
        T_ret_EH[t] = Tr

    data.heat_grid_data["T_supply_EH"] = T_sup_EH
    data.heat_grid_data["T_return_EH"] = T_ret_EH
    param["T_sup_node"] = T_sup_node
    param["T_ret_node"] = T_ret_node
    param["T_sup_pipe_out"] = T_sup_pipe_out
    param["T_ret_pipe_out"] = T_ret_pipe_out

    return data, param

def compute_network_temperatures_fixed_generation(data, param, max_iter=20, tol=1e-1, relax=0.5):
    """
   Solve the supply and return temperature distribution in the district
   heating network for all timesteps assuming a fixed-generation network.

   In this mode the energy hub (EH) supply temperature is predefined by the
   selected network generation (3rd, 4th, or 5th generation) and is therefore
   not adjusted by the solver. The configured EH supply temperature is applied
   as a boundary condition and propagated through the network.

   Unlike the automatic mode (`compute_network_temperatures`), the EH supply
   temperature is not iteratively increased to meet building supply
   temperature requirements.

   Differences to Auto Mode
   ------------------------
   In `compute_network_temperatures` (auto mode):

       - The EH supply temperature is unknown.
       - The solver iteratively increases the EH supply temperature until all
         buildings receive at least their required supply temperature.

   In this function:

       - The EH supply temperature is fixed by the selected generation.
       - Building supply requirements are checked diagnostically but do not
         influence the EH temperature.

   Parameters
   ----------
   data : datahandler class
       Contains network topology, pipe properties, fluid parameters,
       and soil temperature time series.

   param : dict
       Dictionary containing prepared network parameters such as building
       heat loads, pipe heat-loss factors, and temperature requirements.

   max_iter : int, optional
       Maximum number of fixed-point iterations per timestep.

   tol : float, optional
       Convergence tolerance for the return temperature iteration [K].

   relax : float, optional
       Relaxation factor applied to the return temperature update to
       improve numerical stability.

   Returns
   -------
   """

    topo = data.pipeline_topology
    pipe_dict = param["pipe_dict"]

    c_f = data.heat_grid_data["fluid"]["c_f"]   # J/kgK
    rho = data.heat_grid_data["fluid"]["rho_f"] # kg/m3
    k_soil = data.heat_grid_data["k_soil"]

    T_soil = np.asarray(data.heat_grid_data["T_soil"], dtype=float)
    T_len = len(T_soil)

    T_sup_req_by_node = param["T_sup_req_by_node"]
    T_ret_req_by_node = param["T_ret_req_by_node"]
    Q_by_node = param["Q_by_node"]
    root = "EH1"

    T_sup_EH = np.asarray(param["T_sup_network_config"], dtype=float)
    T_ret_EH_cfg = np.asarray(param["T_ret_network_config"], dtype=float) # only used for the first step in the iteration

    Q_eps = 1e-2

    pipes = data.pipeline
    circ_nodes = param.get("circulation_leaves", [])

    # Precompute parent map and topological order
    parent = {}
    order = []

    def dfs(node):
        order.append(node)
        for ch in topo.get(node, []):
            parent[ch] = node
            dfs(ch)

    dfs(root)

    children_map = {n: topo.get(n, []) for n in order}
    pair_to_pid = {(p["from"], p["to"]): pid for pid, p in pipes.items()}
    supply_edges = [(parent[n], n, pair_to_pid[(parent[n], n)]) for n in order if n != root]

    return_children_edges = {}
    for node in order:
        chs = children_map[node]
        if chs:
            return_children_edges[node] = [(ch, pair_to_pid[(node, ch)]) for ch in chs]

    # UA values
    pipe_UA_s = {}
    pipe_UA_a = {}
    for pid, p in pipes.items():
        DN = p["DN"]
        ks = pipe_dict[DN]["symmetrical heat loss factor"]
        ka = pipe_dict[DN]["antisymmetrical heat loss factor"]
        pipe_UA_s[pid] = 2.0 * np.pi * k_soil * ks * p["length"]
        pipe_UA_a[pid] = 2.0 * np.pi * k_soil * ka * p["length"]

    T_ret_EH = np.zeros(T_len)
    T_sup_node = {n: np.zeros(T_len) for n in order}
    T_ret_node = {n: np.zeros(T_len) for n in order}
    T_sup_pipe_out = {(p["from"], p["to"]): np.zeros(T_len) for p in pipes.values()}
    T_ret_pipe_out = {(p["from"], p["to"]): np.zeros(T_len) for p in pipes.values()}

    Q_items = list(Q_by_node.items())

    def twin_pipe_step_counterflow(Tsup_in_parent, Tret_in_child, T_soil, m_dot, UA_s, UA_a, c_f):
        Ks = UA_s / (m_dot * c_f)
        Ka = UA_a / (m_dot * c_f)

        a = float(Tsup_in_parent) - float(T_soil)
        b = float(Tret_in_child) - float(T_soil)

        mu = math.sqrt(Ks * Ka)
        r = math.sqrt(Ks / Ka)

        sh = math.sinh(mu)
        ch = math.cosh(mu)

        denom = (1.0 + r * r) * sh + 2.0 * r * ch

        C2 = (b - a * (ch + r * sh)) / denom
        C1 = a + r * C2

        Tsup_out_child = float(T_soil) + (
            C1 * (ch - r * sh) +
            C2 * (sh - r * ch)
        )

        Tret_out_parent = float(T_soil) + (C1 + r * C2)

        return Tsup_out_child, Tret_out_parent

    for t in tqdm(range(T_len), desc="Solving fixed-generation network temperatures", unit="timestep"):
        Ts = float(T_sup_EH[t])
        Tr_guess = float(T_ret_EH_cfg[t])
        Tsoil_t = float(T_soil[t])

        active_nodes = [n for (n, q) in Q_items if float(q[t]) > Q_eps]

        # initialize coupling references
        Tsup_prev = {}
        Tret_prev = {}
        for par, node, pid in supply_edges:
            Tsup_prev[(par, node)] = Ts
            Tret_prev[(par, node)] = Tr_guess

        for _ in range(max_iter):
            Tr_old = Tr_guess

            # forward pass (supply)
            T_sup_node[root][t] = Ts
            Tsup_new = {}

            for par, node, pid in supply_edges:
                flow_t = pipes[pid]["flow"][t]
                m_dot = float(flow_t) * rho

                T_sup_in = float(T_sup_node[par][t])

                # coupled return reference from previous iterate
                T_ret_ref = float(Tret_prev[(par, node)])

                Tsup_out_child, _ = twin_pipe_step_counterflow(
                    Tsup_in_parent=T_sup_in,
                    Tret_in_child=T_ret_ref,
                    T_soil=Tsoil_t,
                    m_dot=m_dot,
                    UA_s=pipe_UA_s[pid],
                    UA_a=pipe_UA_a[pid],
                    c_f=c_f
                )

                T_sup_pipe_out[(par, node)][t] = Tsup_out_child
                T_sup_node[node][t] = Tsup_out_child
                Tsup_new[(par, node)] = Tsup_out_child

            # initialize return side
            for n in order:
                T_ret_node[n][t] = Tr_guess

            # building returns
            for bn in active_nodes:
                par = parent.get(bn)
                pid = pair_to_pid[(par, bn)]
                flow_t = pipes[pid]["flow"][t]
                m_dot = float(flow_t) * rho

                Q_W = float(Q_by_node[bn][t]) * 1000.0
                Ts_del = float(T_sup_node[bn][t])

                Tr_act = Ts_del - Q_W / (m_dot * c_f)
                T_ret_node[bn][t] = Tr_act

            # circulation leaves: bypass
            for cn in circ_nodes:
                if cn not in active_nodes:
                    T_ret_node[cn][t] = T_sup_node[cn][t]

            # backward pass
            Tret_new = {}

            for node in reversed(order):
                edges = return_children_edges.get(node)
                if not edges:
                    continue

                m_sum = 0.0
                Tmix = 0.0

                for ch, pid in edges:
                    flow_t = pipes[pid]["flow"][t]
                    m_dot = float(flow_t) * rho

                    T_ret_in = float(T_ret_node[ch][t])
                    T_sup_ref = float(Tsup_new[(node, ch)])

                    _, Tret_out_parent = twin_pipe_step_counterflow(
                        Tsup_in_parent=T_sup_ref,
                        Tret_in_child=T_ret_in,
                        T_soil=Tsoil_t,
                        m_dot=m_dot,
                        UA_s=pipe_UA_s[pid],
                        UA_a=pipe_UA_a[pid],
                        c_f=c_f
                    )

                    T_ret_pipe_out[(node, ch)][t] = Tret_out_parent
                    Tret_new[(node, ch)] = Tret_out_parent

                    m_sum += m_dot
                    Tmix += m_dot * Tret_out_parent

                if m_sum > 0.0:
                    T_ret_node[node][t] = Tmix / m_sum
                else:
                    T_ret_node[node][t] = Tr_guess

            Tr_new = float(T_ret_node[root][t])

            # relaxation only on return iteration
            Tr_guess = (1.0 - relax) * Tr_guess + relax * Tr_new

            # update edge-wise return references for next iterate
            for edge in Tret_prev:
                if edge in Tret_new:
                    Tret_prev[edge] = (1.0 - relax) * Tret_prev[edge] + relax * Tret_new[edge]

            Tsup_prev = Tsup_new

            if abs(Tr_guess - Tr_old) < tol:
                break

        # store converged timestep results
        T_ret_EH[t] = Tr_guess

        # diagnostics after convergence
        for bn in active_nodes:
            Ts_req = float(T_sup_req_by_node[bn][t])
            Tr_req = float(T_ret_req_by_node[bn][t])

            Ts_del = float(T_sup_node[bn][t])
            Tr_del = float(T_ret_node[bn][t])

            # Diagnostics after convergence
            if Ts_del < Ts_req:
                raise ValueError(
                    f"Supply temperature violation at timestep {t}, node {bn}: "
                    f"delivered supply {Ts_del:.2f} °C is below required "
                    f"{Ts_req:.2f} °C. "
                    f"The fixed generation supply temperature is insufficient "
                    f"for this building."
                )

            dT_HX_r = 4.0  # TODO: move to config

            if Tr_del < Tr_req - dT_HX_r:
                raise ValueError(
                    f"Return temperature violation at timestep {t}, node {bn}: "
                    f"delivered return {Tr_del:.2f} °C is below required limit "
                    f"{Tr_req - dT_HX_r:.2f} °C "
                    f"(design return {Tr_req:.2f} °C). "
                )

    data.heat_grid_data["T_supply_EH"] = T_sup_EH
    data.heat_grid_data["T_return_EH"] = T_ret_EH

    param["T_sup_node"] = T_sup_node
    param["T_ret_node"] = T_ret_node
    param["T_sup_pipe_out"] = T_sup_pipe_out
    param["T_ret_pipe_out"] = T_ret_pipe_out

    return data, param

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

def compute_pump_power(data, param):
    """
    Compute the circulation pump power required for the district heating network.

    Pump power is calculated from hydraulic pressure losses caused by
    pipe friction and local resistances (bends, junctions, and diameter
    changes). Local resistance coefficients (ζ) are derived automatically
    from the network topology.

    Hydraulic losses are aggregated along predefined root-to-leaf
    network branches. A single circulation pump is assumed at the
    energy hub (EH), therefore the required pump head is determined
    by the hydraulically most demanding branch (worst path).

    Additional pressure losses at substations and the energy hub
    are added as a system-level pressure drop.

    Parameters
    ----------
    data : object
        Network data structure containing pipeline properties, flows,
        and heat grid parameters. The result is stored in
        ``data.heat_grid_data["pump_power"]``.
    param : dict
        Model parameters including network paths (``param["path"]``) and
        time series information (``param["T_s"]``).
    """

    pipe_dict = param["pipe_dict"]
    rho_f = data.heat_grid_data["fluid"]["rho_f"]

    # save pump power(yearly profile) in data.heat_grid_data["pump_power"]
    eta_pump = data.heat_grid_data["pump"]["eta_pump"]  # 0.65,         electric pump efficiency

    # calculate zeta for local pressure drop
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

    pump_power_pipe = {}
    for pipe_id, pipe in data.pipeline.items():
        f_i = pipe.get("f_fric", data.heat_grid_data["pipe"]["f_fric"])
        prefac_i = (8.0 * f_i) / (rho_f ** 2 * np.pi ** 2 * eta_pump) / 1000.0
        DN = pipe["DN"]  # mm
        d_i = pipe_dict[DN]["Inner diameter (pipe) (mm)"]  # mm
        length = pipe["length"]  # m
        flow = abs(pipe["flow"])  # m3/s
        # pump power to cover friction loss
        # *2: The first factor of two accounts for the pump power of both the supply and return pipes.
        pump_power_friction = prefac_i * length * 2 * ((flow * rho_f) ** 3) / ((d_i / 1000) ** 5)  # kW

        # pump power to cover local loss
        velocity = flow / (np.pi * (d_i / 1000) ** 2 / 4)  # m/s
        zeta_pipe = pipe["zeta"]
        local_pressure_drop = rho_f * zeta_pipe * velocity**2 / 2  # Pa
        pump_power_local = local_pressure_drop * flow / (eta_pump * 1000.0)  # kW

        # total pump power for this pipe segment
        pump_power_pipe[pipe_id] = pump_power_friction + pump_power_local  # kW

    # Build mapping from oriented node pair to pipe id (assume unique per pair)
    pair_to_pid = {}
    for pid, info in data.pipeline.items():
        pair_to_pid[(info["from"], info["to"])] = pid

    path = param["path"]
    T_supply = data.heat_grid_data["T_supply_EH"]

    pump_power_line = {}
    for line, nodes in path.items():
        # Initialize pump power array for this line
        pump = np.zeros_like(T_supply, dtype=float)
        # Sum up pump power along all pipeline segments in this line
        for i in range(len(nodes) - 1):
            a, b = nodes[i], nodes[i + 1]
            pid = pair_to_pid[(a, b)]
            pump += pump_power_pipe[pid]
        # Store total pump power time series for this line
        pump_power_line[line] = pump

    # Stack all line pump power arrays into a 2D matrix: (n_lines, n_timesteps)
    pump_matrix = np.array(list(pump_power_line.values()))

    # Add yearly station + hub pressure-drop component
    dp_substation = data.heat_grid_data.get("dp_substation", 0.0)  # Pa
    dp_energy_hub = data.heat_grid_data.get("dp_energy_hub", 0.0)  # Pa
    dp_station_total = dp_substation + dp_energy_hub                                # Pa

    # Calcualte total volume flow at energy hub as sum of flows leaving EH1
    Vdot_total_profile = np.zeros_like(T_supply, dtype=float)
    for pipe_id, pipe in data.pipeline.items():
        if pipe["from"] == "EH1":
            Vdot_total_profile += abs(pipe["flow"])  # m³/s

    # Extra pump power from substations + energy hub
    # P = V̇ * Δp / (η * 1000)
    P_station_profile = Vdot_total_profile * dp_station_total / (eta_pump * 1000.0)  # kW

    # Final pump power: (pipe friction + local pressure loss) from worst line + station/hub component
    pump_power = np.max(pump_matrix, axis=0) + P_station_profile

    data.heat_grid_data["pump_power"] = pump_power
    # print("Total pump power in network calculation finished successfully.")

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
    # save heat loss(yearly profile) in data.heat_grid_data["total_losses_heating_network"]
    # load heat loss in substation
    heat_loss_substation = param.get("heat_loss_substation", param.get("heat_loss_substation_heating", 0.0))
    # load cooling loss in substation (5th gen only, safe default otherwise)
    cool_loss_substation = param.get("cool_loss_substation", param.get("heat_loss_substation_cooling", 0.0))

    # calculate heat loss in every pipe segment
    # data, heat_loss_pipe, heat_loss_pipe_cluster = calc_heat_loss_pipe(data, param)

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
        substation_capacity = building["envelope"].heatload/1000 + building["dhwpower"]/1000  #kW
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
    pump_cap = np.max(data.heat_grid_data["pump_power"])   # kW
    # print(f"The capacity of the pump should be bigger than {pump_cap:5f}kW.")

    # calculate the investment for the pump
    inv_pump = pump_cap * data.heat_grid_data["pump"]["inv_pump"]

    # cost of pump
    pump_ann_costs = inv_pump * data.heat_grid_data["pump"]["pump_ann_factor"]
    pump_om_costs = inv_pump * data.heat_grid_data["pump"]["cost_om_pump"]
    # print(f"Pump annualized cost: {pump_ann_costs:.2f} €")
    # print(f"Pump O&M cost per year: {pump_om_costs:.2f} €")

    # electricity cost of the circulation pump
    pump_energy_total = np.sum(data.heat_grid_data["pump_power"])  # kWh
    # print(f"The total electricity consumption for the pump is {pump_energy_total:5f}kWh/a.")
    pump_electricity_costs = pump_energy_total * data.ecoData["price_supply_el_eh"][0]

    # calculate the total cost
    network_om_costs = pipes_om_costs + pump_om_costs + substation_om_costs
    network_ann_costs = pipes_ann_costs + pump_ann_costs + substation_ann_costs
    data.heat_grid_data["om_costs"] = network_om_costs
    data.heat_grid_data["ann_costs"] = network_ann_costs

    # get cost of heat loss
    # calculate capacity
    cap_HP = np.max(data.heat_grid_data["total_losses_heating_network"])
    # calculate investment, o&m cost and electricity cost
    HP_inv_costs = cap_HP * data.central_device_data["AirHP"]["inv_var"]
    HP_ann_costs = HP_inv_costs * param["HP_ann_factor"]
    HP_om_costs = HP_inv_costs * data.central_device_data["AirHP"]["cost_om"]

    deltaT_EH = data.heat_grid_data["T_supply_EH"] - data.heat_grid_data["T_return_EH"]

    # calculate yearly COP profile and the electricity cost for the HP
    devs_param = {
        "feasible": True,
        "dT_evap": 10,      # K,    temperature difference in evaporator (how much the air cools down in the evaporator); Source: JENSEN J. et al. Heat pump COP, part 2: generalized COP estimation of heat pump processes
        "dT_cond": deltaT_EH,  # K,    temperature difference in condenser (how much network's fluid heats up in the condenser)
        "dT_pinch_cond": 2, # K,    temperature difference between both fluids in the condenser at pinch point; Source: Klingebiel et al. https://doi.org/10.1016/j.enbuild.2023.113397
        "dT_pinch_evap": 5, # K,    temperature difference between both fluids in the evaporator at pinch point
        "eta_compr": 0.8,   # ---,  isentropic efficiency of compression; Source: Wirtz et al. https://doi.org/10.1016/j.apenergy.2019.114158
        "heatloss_compr": 0.3, # ---,  heat loss rate of compression; # Source: JENSEN J. et al. Heat pump COP, part 2: generalized COP estimation of heat pump processes
        "COP_max": 7,       # ---,  maximum heat pump COP
    }
    # Temperatures
    t_c_in = data.site["T_e"] + 273.15  # heat source inlet (Air)
    dt_c = devs_param["dT_evap"]  # heat source temperature difference
    t_h_in = data.heat_grid_data["T_return_EH"] + 273.15  # heat sink (Network fluid) inlet temperature
    dt_h = devs_param["dT_cond"]
    # call the calculation function
    COP_HP = calc_COP(devs_param, [t_c_in, dt_c, t_h_in, dt_h])
    HP_electricity_costs = np.sum(data.heat_grid_data["total_losses_heating_network"]/ COP_HP) * data.ecoData["price_supply_el_eh"][0]

    # ---------- 9. plot cost in stacked bar chart ----------
    costs = {
        "Annualized investment for substations": substation_ann_costs,
        "Operation and maintenance cost for substations": substation_om_costs,
        "Annualized investment for pipes": pipes_ann_costs,
        "Operation and maintenance cost for pipes": pipes_om_costs,
        "Annualized investment for the pump": pump_ann_costs,
        "Operation and maintenance cost for the pump": pump_om_costs,
        "Electricity costs for the pump": pump_electricity_costs,
        "Annualized investment for the heatpump": HP_ann_costs,
        "Operation and maintenance cost for the heatpump": HP_om_costs,
        "Electricity costs for the heatpump": HP_electricity_costs,
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

    # --- Axis labels, title, ticks ---
    ax.set_ylabel("Annual Costs [EUR/a]")
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

    # ---------- 10. save parameters, energy-consumption and costs to a json-file ----------
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
        "HP_ann_costs": {
            "value": float(HP_ann_costs),
            "unit": "€",
            "description": "Annualized investment for the heat pump for covering heat loss"
        },
        "HP_om_costs": {
            "value": float(HP_om_costs),
            "unit": "€",
            "description": "O&M cost for the heat pump for covering heat loss"
        },
        "HP_electricity_costs": {
            "value": float(HP_electricity_costs),
            "unit": "€",
            "description": "Electricity cost for the heat pump for covering heat loss"
        },
        "network_ann_costs": {
            "value": float(network_ann_costs),
            "unit": "€",
            "description": "Total annualized investment for the heating network (excluding cost for pump electricity and heat loss)"
        },
        "network_om_costs": {
            "value": float(network_om_costs),
            "unit": "€",
            "description": "Total O&M cost for the heating network (excluding cost for pump electricity and heat loss)"
        },
        "network_total_costs": {
            "value": float(network_ann_costs + network_om_costs + pump_electricity_costs + HP_ann_costs + HP_om_costs + HP_electricity_costs),
            "unit": "€",
            "description": "Total annual cost for the heating network (including cost for pump electricity and heat loss)"
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

def extract_longest_branches(edges, root="EH1"):
    """
    Extract the longest root-to-leaf branches from the network topology.

    Parameters
    ----------
    edges : dict
        Topology dictionary
        shape like {"EH1":["node1"], "node1":["bldg1","node2"], ...}
    root : str
        Root node (default "EH1")

    Returns
    -------
    dict
        {"line1":[...], "line2":[...], ...}
    """
    all_paths = []

    # DFS to collect all paths
    def dfs(path, current):
        """
        Depth-First Search (DFS) to collect all possible paths
        from the root node down to each terminal (leaf) node.

        Parameters
        ----------
        path : list
            The current traversal path (list of node names).
        current : str
            The current node being visited.

        Returns
        -------
        None
        """
        # If current node has no outgoing edges → it’s a leaf node
        if current not in edges or not edges[current]:
            all_paths.append(path[:])  # Save a copy of the current path
            return
        # Continue DFS for all child nodes
        for nxt in edges[current]:
            dfs(path + [nxt], nxt)

    # Start DFS traversal from the root node
    dfs([root], root)

    # Filter out paths that are prefixes of longer ones
    # (Keep only the longest, complete branch paths)
    filtered = []
    for p in all_paths:
        if not any(p != q and len(p) < len(q) and p == q[:len(p)] for q in all_paths):
            filtered.append(p)

    # Convert the list of paths into a dictionary format
    result = {f"line{i + 1}": path for i, path in enumerate(filtered)}
    return result

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

def enforce_min_leaf_circulation(building_massflow, network, param, root="EH1", alpha=0.1):
    """
    Enforce minimum circulation flow at terminal (leaf) nodes.

    For each leaf node a minimum flow requirement is imposed:

        m_leaf >= alpha * m_leaf_max

    where m_leaf_max is the maximum observed mass flow in that
    branch. If the current flow falls below this threshold,
    additional circulation flow is injected.

    This prevents low-flow conditions and ensures that
    terminal branches maintain minimum circulation.
    """

    parent = get_parent_map(network, root)
    leaves = get_leaves(network, root)

    pipe_massflows = aggregate_mass_flows(network, building_massflow, root)

    # compute max leaf flows once
    if "leaf_mdot_max" not in param:

        leaf_max = {}

        for leaf in leaves:

            par = parent.get(leaf)

            if par is None:
                continue

            m = pipe_massflows[(par, leaf)]

            leaf_max[leaf] = float(np.max(m))

        param["leaf_mdot_max"] = leaf_max

    leaf_mdot_max = param["leaf_mdot_max"]

    # determine timestep length
    T = len(param["net_heat_demand"])

    for leaf in leaves:

        par = parent.get(leaf)

        if par is None:
            continue

        m_current = pipe_massflows[(par, leaf)]

        m_min = alpha * leaf_mdot_max.get(leaf, 0)

        deficit = np.maximum(0.0, m_min - m_current)

        if np.max(deficit) <= 0:
            continue

        if leaf not in building_massflow:
            building_massflow[leaf] = np.zeros(T)

        building_massflow[leaf] += deficit

    param["circulation_leaves"] = leaves

    return building_massflow

def get_parent_map(network, root="EH1"):
    parent = {}
    stack = [root]

    while stack:
        node = stack.pop()

        for child in network.get(node, []):
            parent[child] = node
            stack.append(child)

    return parent

def get_leaves(network, root="EH1"):
    nodes = set(network.keys()) | {c for kids in network.values() for c in kids}

    leaves = [
        n for n in nodes
        if len(network.get(n, [])) == 0 and n != root
    ]

    return leaves

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

def calc_COP(devs_param, temperatures):
    """
    calculate COP of Heat Pump

    Source: JENSEN J. et al. Heat pump COP, part 2: generalized COP estimation of heat pump processes.
    Heat pump COP, part 2: Generalized COP estimation of heat pump processes
    DOI: 10.18462/iir.gl.2018.1386

    Parameters
    ----------
    devs_param: dict
        parameters of the heat pump
    temperatures: lst
        temperatures of the heat source and heat sink ([t_c_in, dt_c, t_h_in, dt_h])

    Returns
    -------
    COP: np.array
        COP array of same shape as input temperature
    """
    # get temperature parameters
    t_c_in = temperatures[0]
    dt_c = temperatures[1]
    t_h_in = temperatures[2]
    dt_h = temperatures[3]

    # device parameters
    dt_pp_cond = devs_param["dT_pinch_cond"]  # pinch point temperature difference in the condenser
    dt_pp_evap = devs_param["dT_pinch_evap"]  # pinch point temperature difference in the evaporator

    eta_is = devs_param["eta_compr"]  # isentropic compression efficiency
    f_Q = devs_param["heatloss_compr"]  # heat loss rate during compression

    # Entropic mean temperautures (or Logarithmic mean temperatures) of the heat sink and heat source
    t_h_s = dt_h / np.log((t_h_in + dt_h) / t_h_in)
    t_c_s = dt_c / np.log(t_c_in / (t_c_in - dt_c))

    # Next 3 paragraphs increase the robustness of the method to handel 5G Network temperatures which can lead to Temp_in_air > Temp_heat_sink which is equivalent to free heating
    COP_max = devs_param["COP_max"]
    eps = 1e-6

    # Avoid division by 0 in valid region, therefore replaced by dummy value 1.0 (which prevents crashes) if not valid
    delta = np.where((t_h_s - t_c_s) > eps, (t_h_s - t_c_s), 1.0)

    # Lorentz-COP (only meaningful where valid)
    COP_Lor = t_h_s / delta

    # linear model equations; Source: JENSEN J. et al. Heat pump COP, part 2: generalized COP estimation of heat pump processes.
    dt_r_H = 0.2 * (t_h_in + dt_h - (
                t_c_in - dt_c) + (dt_pp_cond + dt_pp_evap)) + 0.2 * dt_h + 0.016  # mean entropic heat difference in condenser deducting dt_pp and assuming an ammonia heat pump
    w_is = 0.0014 * (t_h_in + dt_h - (
                t_c_in - dt_c) + (dt_pp_cond + dt_pp_evap)) - 0.0015 * dt_h + 0.039  # ratio of isentropic expansion work to isentropic compression work and assuming an ammonia heat pump

    # help values
    num = 1 + (dt_r_H + dt_pp_cond) / t_h_s
    denom = 1 + (dt_r_H + 0.5 * dt_c + (dt_pp_cond + dt_pp_evap)) / (t_h_s - t_c_s)

    # COP
    COP = COP_Lor * num / denom * eta_is * (1 - w_is) + 1 - eta_is - f_Q

    # limit COP's
    #COP_max = devs_param["COP_max"]

    # In invalid region set COP to COP_max
    COP = np.where((t_h_s - t_c_s) > eps, COP, COP_max)
    COP = np.clip(COP, 0, COP_max)

    return COP

def heating_curve(T_e, T_supply_min, T_supply_max, T_return_min, T_return_max):
    """
    Sliding temperature heating curve (2D version).

    Parameters
    ----------
    T_e : np.ndarray
        Ambient temperature matrix [°C]

    Returns
    -------
    T_supply : np.ndarray, same shape
        Supply temperature [°C]
    T_return : np.ndarray, same shape
        Return temperature [°C]
    """
    T_e = np.array(T_e, dtype=float)  # make sure the datatype is ndarray

    # the information of the bounds and turning point
    T_min, T_max = -10, 15
    # Supply and return water temperature difference at an outdoor temperature of -10°C
    dT_min = T_supply_min - T_return_min
    # Supply and return water temperature difference at an outdoor temperature of 15°C
    dT_max = T_supply_max - T_return_max

    # supply temperature
    T_supply = np.interp(T_e,[T_min, T_max],[T_supply_min, T_supply_max])

    # temperature difference
    dT = np.interp(T_e,[T_min, T_max],[dT_min, dT_max])

    # return temperature
    T_return = T_supply - dT

    return T_supply, T_return

def get_configured_network_temperatures(data):
    """
    Return generation-dependent network supply/return temperature profiles.
    """

    heat_grid_data = data.heat_grid_data
    generation = str(heat_grid_data.get("generation", "auto")).lower()
    temperature_mode = str(heat_grid_data.get("temperature_mode", "constant")).lower()

    # AUTO mode → temperatures solved later by network model
    if generation == "auto":
        return None, None

    if generation not in {"3rd", "4th", "5th"}:
        raise ValueError(
            f"Unsupported heat grid generation '{generation}'. "
            f"Use 'auto', '3rd', '4th', or '5th'."
        )

    T_len = len(heat_grid_data["T_soil"])

    # CONSTANT TEMPERATURE MODE
    if temperature_mode == "constant":

        Ts = heat_grid_data["T_hot_heating_network"]["constant"][generation]
        Tr = heat_grid_data["T_cold_heating_network"]["constant"][generation]

        T_supply = np.full(T_len, Ts, dtype=float)
        T_return = np.full(T_len, Tr, dtype=float)

        return T_supply, T_return

    # HEATING CURVE MODE
    if temperature_mode == "heating_curve":

        # Otherwise compute with heating curve
        T_e = np.asarray(data.site["T_e"], dtype=float)

        T_supply_min = heat_grid_data["T_hot_heating_network"]["heating_curve"]["min"][generation]
        T_supply_max = heat_grid_data["T_hot_heating_network"]["heating_curve"]["max"][generation]
        T_return_min = heat_grid_data["T_cold_heating_network"]["heating_curve"]["min"][generation]
        T_return_max = heat_grid_data["T_cold_heating_network"]["heating_curve"]["max"][generation]

        T_supply, T_return = heating_curve(T_e, T_supply_min, T_supply_max, T_return_min, T_return_max)

        return T_supply, T_return

    raise ValueError(f"Unsupported temperature_mode '{temperature_mode}'.")

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
