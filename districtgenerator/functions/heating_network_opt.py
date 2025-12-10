# -*- coding: utf-8 -*-

import pyomo.environ as pyo
from pyomo.util.infeasible import log_infeasible_constraints
import numpy as np
import math
import os
import json
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import districtgenerator.functions.solver_config as solver_config
import fluids

def calc_annual_factor(data, life_time):
    """
    Calculation of total investment costs including replacements (based on VDI 2067-1, pages 16-17).

    Parameters
    ----------
    life_time : int
        economic parameters

    Returns
    -------
    annualized fix and variable investment
    """

    observation_time = data.params_ehdo_model["observation_time"]
    interest_rate = data.params_ehdo_model["interest_rate"]
    q = 1 + data.params_ehdo_model["interest_rate"]

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
    # T_supply_min, T_supply_max = 75, 60
    # dT_min, dT_max = 20, 10
    # Supply and return water temperature difference at an outdoor temperature of -10°C
    dT_min = T_supply_min - T_return_min
    # Supply and return water temperature difference at an outdoor temperature of 15°C
    dT_max = T_supply_max - T_return_max

    # --- supply temperature ---
    T_supply = np.interp(
        T_e,
        [T_min, T_max],
        [T_supply_min, T_supply_max]
    )

    # --- temperature difference ---
    dT = np.interp(
        T_e,
        [T_min, T_max],
        [dT_min, dT_max]
    )

    # return temperature
    T_return = T_supply - dT

    return T_supply, T_return

def aggregate_flows(network, building_flows, root="EH1"):
    """
    Aggregate pipe flows from buildings to plant

    Parameters
    ----------
    network : dict
        Network topology, key = parent node, value = list of child nodes
    building_flows : dict
        key=building name, value=ndarray of flows
    root : string
        Root node name

    Returns
    -------
    pipe_flows : dict
        key= (parent, child), value=ndarray of flows
    """
    pipe_flows = {}

    def dfs(node):
        """
        Recursively compute flow for a node

        Parameters
        ----------
        node : str
            Current node being processed in the DFS traversal.

        Returns
        -------
        total_flow : ndarray, same shape with the value of building_flows
            Total flow passing through this node (own flow + downstream flows).
        """

        total_flow = 0
        # If the current node represents a building, add its own flow
        if node in building_flows:
            total_flow += building_flows[node]

        # If there are no downstream nodes → this is a terminal node
        # Return its own flow directly
        if not network.get(node, []):
            return total_flow

        # Traverse all child nodes and accumulate their flows
        for child in network[node]:
            child_flow = dfs(child)
            pipe_flows[(node, child)] = child_flow
            total_flow += child_flow

        return total_flow

    # Start the recursive traversal from the root node (energy hub)
    dfs(root)
    return pipe_flows

def extract_longest_branches(edges, root="EH1"):
    """
    Extract all the branches from the topology
    (from root node to terminal node)

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

def calc_flow_and_temperature(data):
    """
    Calculate the supply and return temperature and the flow rate in each pipe segment

    Parameters
    ----------
    data: class datahandler

    Returns
    -------
    data: class datahandler
    param: dictionary
        including parameters for diameter optimization
    """
    # 1 time setup
    # timeData = data.time
    # dt = timeData["timeResolution"] / timeData["dataResolution"]
    # list of clustered typical weeks
    weeks = data.clusters
    # how many timesteps are there in a typical week
    time_steps = int(data.time["clusterLength"] / data.time["timeResolution"])

    # 2 ambient temperature
    T_e_cluster = data.site["T_e_cluster"]  # ndarray, shape = (n_clusters, len_cluster)
    T_e = data.site["T_e"]

    # 3 supply and return temperature
    heat_grid_data = data.heat_grid_data
    generation = heat_grid_data["generation"]
    temperature_mode = heat_grid_data["temperature_mode"]
    if temperature_mode == "heating_curve":
        # Variable-constant operation mode (Heating curve)
        T_supply_min = heat_grid_data["T_hot_heating_network"]["heating_curve"]["min"][generation]
        T_supply_max = heat_grid_data["T_hot_heating_network"]["heating_curve"]["max"][generation]
        T_return_min = heat_grid_data["T_cold_heating_network"]["heating_curve"]["min"][generation]
        T_return_max = heat_grid_data["T_cold_heating_network"]["heating_curve"]["max"][generation]
        T_supply_cluster, T_return_cluster = heating_curve(T_e_cluster, T_supply_min, T_supply_max, T_return_min,
                                                           T_return_max)
        T_supply, T_return = heating_curve(T_e, T_supply_min, T_supply_max, T_return_min, T_return_max)
    elif temperature_mode == "constant":
        # constant operation mode
        T_supply_value = heat_grid_data["T_hot_heating_network"]["constant"][generation]
        T_return_value = heat_grid_data["T_cold_heating_network"]["constant"][generation]
        T_supply = np.full_like(T_e, T_supply_value)
        T_return = np.full_like(T_e, T_return_value)
        T_supply_cluster = np.full((len(weeks), time_steps), T_supply_value)  # °C
        T_return_cluster = np.full((len(weeks), time_steps), T_return_value)  # °C
    else:
        message = "Please select a valid temperature mode between 'heating_curve' and 'constant' in heat_grid.json."
        print(message)

    # ΔT = T_supply - T_return (°C)
    # if constant operation mode, int
    # if Variable-constant operation mode,ndarray, shape = (n_clusters, len_cluster)
    deltaT_cluster = T_supply_cluster - T_return_cluster  # °C
    deltaT = T_supply - T_return  # °C

    # Temperatures of pipes in the symmetrical and the antisymmetrical calculation case (DIN EN 13941)
    T_s_cluster = (T_supply_cluster + T_return_cluster) / 2
    T_s = (T_supply + T_return) / 2
    # Antisymmetrical heat loss is not considered in this optimization.
    # Since it calculates the heat conduction between the supply and return pipes,
    # the supply pipe loses heat while the return pipe gains it, resulting in a net system heat loss of zero.
    # T_a = (T_supply - T_return)/2

    # 4 fluids parameters
    c_f = heat_grid_data["fluid"]["c_f"]  # 4180J/(kg*K), fluid specific heat capacity
    rho_f = heat_grid_data["fluid"]["rho_f"]  # 1000kg/m^3,   fluid density

    # 5 read demand and calculate mass flow to every building
    heat_loss_substation = np.zeros_like(T_e)
    total_demand_cluster = np.zeros(
        (len(weeks), time_steps))  # Create a 2D array filled with zeros (weeks × time steps)
    total_demand = np.zeros_like(T_e)
    h_loss_subst = data.heat_grid_data["h_loss_subst"]  # 5%, Heat losses at the substation
    for building in data.district:
        # read (clustered) demand pofile for each building
        # clustered value (for the optimization)
        heating_cluster = building["user"].heat_cluster / 1000  # kW
        dhw_cluster = building["user"].dhw_cluster / 1000  # kW
        generationSTC_cluster = building["generationSTC_cluster"] / 1000  # kW

        heating_demand_cluster = np.maximum(heating_cluster + dhw_cluster - generationSTC_cluster, 0)  # kW
        building["user"].heating_demand_cluster = heating_demand_cluster  # kW
        # Sum the heat demand in the network
        total_demand_cluster += heating_demand_cluster * (1 + h_loss_subst / 100)   # kW

        # year profile (for calculation of max and min permitted pipeline diameter)
        heating = building["user"].heat / 1000  # kW
        dhw = building["user"].dhw / 1000  # kW
        generationSTC = building["generationSTC"] / 1000  # kW

        heating_demand = np.maximum(heating + dhw - generationSTC, 0)  # kW
        building["user"].heating_demand = heating_demand  # kW
        # Sum the heat demand in the network
        total_demand += heating_demand * (1 + h_loss_subst / 100)  # kW
        # Sum the heat losses in the substations
        heat_loss_substation += heating_demand * h_loss_subst / 100  # kW

        # The volume flow in each building  m³/s
        # heating_demand_cluster in kW, c_f in J/kg·K, 1kW = 1kJ/s
        # V_dot = Q / (c*ΔT*ρ)
        # clustered value (for the optimization)
        flow_cluster = heating_demand_cluster * 1000 * (1 + h_loss_subst / 100) / (c_f * deltaT_cluster * rho_f)  # m³/s
        building["user"].flow_cluster = flow_cluster  # m³/s
        # year profile (for calculation of max and min permitted pipeline diameter)
        flow = heating_demand * 1000 * (1 + h_loss_subst / 100) / (c_f * deltaT * rho_f)  # m³/s
        building["user"].flow = flow  # m³/s

    # generate the dict of buildng flow
    # key = building_name, string; value = flow, ndarray
    building_flows_cluster = {}
    building_flows = {}

    # match the coordinate and add data to building_flows
    for building in data.district:
        pos_building = tuple(building["buildingFeatures"]["position"])
        flow_cluster = building["user"].flow_cluster
        flow = building["user"].flow

        # find corresponding pipeline node
        for key, node_info in data.pipeline_nodes.items():
            if tuple(node_info["pos"]) == pos_building:
                building_flows_cluster[key] = flow_cluster
                building_flows[key] = flow
                data.pipeline_nodes[key]["flow_cluster"] = flow_cluster
                break  # break once found

    # 6 mass flow and capacity of each pipe
    network = data.pipeline_topology
    # calculate the flow for each pipe segment
    pipe_flow_cluster = aggregate_flows(network, building_flows_cluster, root="EH1")
    pipe_flow = aggregate_flows(network, building_flows, root="EH1")

    # Iterate through each pipe in pipe_flow_cluster
    for idx, ((parent, child), flow_cluster_array) in enumerate(pipe_flow_cluster.items(), 1):
        # generate pipe id: pipe1, pipe2, ...
        pipe_id = f"pipe{idx}"

        # extract coordinates
        pos_parent = data.pipeline_nodes[parent]["pos"]
        pos_child = data.pipeline_nodes[child]["pos"]

        # convert to numpy array
        p1 = np.array(pos_parent, dtype=float)
        p2 = np.array(pos_child, dtype=float)

        # Euclidean distance
        length = float(np.linalg.norm(p1 - p2))

        # store into data.pipeline
        data.pipeline[pipe_id] = {
            "from": parent,  # string, name of start node
            "to": child,  # string, name of end node
            "from_pos": pos_parent,  # tuple, coordinate of start node
            "to_pos": pos_child,  # tuple, coordinate of end node
            "length": length,  # length of the pipe
            "flow_cluster": flow_cluster_array  # original 2D flow array
        }

    # Iterate through each pipe in pipe_flow
    for idx, ((parent, child), flow_array) in enumerate(pipe_flow.items(), 1):
        # generate pipe id: pipe1, pipe2, ...
        pipe_id = f"pipe{idx}"
        data.pipeline[pipe_id]["flow"] = flow_array

        # Retrieve the maximum and minimum flow rates, and convert the data type to float.
        flow_max = float(np.max(flow_array[flow_array > 1e-6]))
        flow_min = float(np.min(flow_array[flow_array > 1e-6]))
        # store into data.pipeline
        data.pipeline[pipe_id]["flow_max"] = flow_max
        data.pipeline[pipe_id]["flow_min"] = flow_min

    # prepare parameters for the optimization model
    param = {}
    param["total_demand_cluster"] = total_demand_cluster
    param["total_demand"] = total_demand
    param["heat_loss_substation"] = heat_loss_substation
    param["T_s"] = T_s
    param["T_s_cluster"] = T_s_cluster
    param["deltaT"] = deltaT
    param["deltaT_cluster"] = deltaT_cluster

    return data, param

def optimization_diameter(data, param, f_fric):
    """
    Optimize the diameter of each pipeline segments.

    The method for calculating heat loss is from DIN EN 13941.
    The method for calculating pump power is based on a Darcy–Weisbach-derived formulation.
        The equation originates from the Darcy–Weisbach pressure drop:
        Δp = f_fric * (L/D) * (ρ * v² / 2)
        where velocity v is expressed by the mass flow rate:
        v = 4 * m_dot / (ρ * π * D²)
        Substituting into P = Δp * Q / η with Q = m_dot / ρ yields:
        P = (8 * f_fric / (π² * η * ρ²)) * (1/1000) * L * (m_dot³ / D⁵)

    Parameters
    ----------
    data: class datahandler
    param: dictionary
    f_fric: float
        friction factor of pipeline, Iteration parameter

    Returns
    -------
    data: class datahandler
    model: pyomo optimization model
    param: dictionary
    """
    # %% STEP ONE: load all parameters
    # 1 time setup
    # timeData = data.time
    # dt = timeData["timeResolution"] / timeData["dataResolution"]
    # list of clustered typical weeks
    weeks = data.clusters
    # how many timesteps are there in a typical week
    time_steps = int(data.time["clusterLength"] / data.time["timeResolution"])

    # Map week -> index i
    # Assuming 'weeks' is an ordered iterable matching the cluster index order used to create flow_cluster
    week_to_i = {w: i for i, w in enumerate(weeks)}

    # 2 demand and temperature
    total_demand_cluster = param["total_demand_cluster"]
    T_s_cluster = param["T_s_cluster"]
    deltaT_cluster = param["deltaT_cluster"]

    # 3 fluids parameters
    heat_grid_data = data.heat_grid_data
    c_f = heat_grid_data["fluid"]["c_f"]  # 4180J/(kg*K), fluid specific heat capacity
    rho_f = heat_grid_data["fluid"]["rho_f"]  # 1000kg/m^3,   fluid density

    # 4 energy hub setup

    # 5 pump parameters
    eta_pump = heat_grid_data["pump"]["eta_pump"]        # 0.65,         electric pump efficiency

    # constant pressure drops outside the pipe network
    dp_substation = heat_grid_data["pump"].get("dp_substation", {}).get("value", 0.0)  # Pa
    dp_energy_hub = heat_grid_data["pump"].get("dp_energy_hub", {}).get("value", 0.0)  # Pa
    dp_station_total = dp_substation + dp_energy_hub  # Pa

    # total volume flow at energy hub for each cluster/week/time
    # total_demand_cluster in kW, c_f in J/(kg*K), rho_f in kg/m³, deltaT_cluster in K
    # V̇ = Q / (c * ΔT * ρ)
    Vdot_total_cluster = total_demand_cluster * 1000.0 / (c_f * deltaT_cluster * rho_f)  # m³/s

    # extra pump power (kW) from substations + energy hub
    # P = V̇ * Δp / (η * 1000)  [kW]
    P_station_cluster = Vdot_total_cluster * dp_station_total / (eta_pump * 1000.0)

    # 6 pipe parameters
    # conv_pipe = heat_grid_data["pipe"]["conv_pipe"]        # 3600W/(m^2 K), convective heat transfer between flowing fluid and the pipe's inner surface
    # f_fric = heat_grid_data["pipe"]["f_fric"]               # 0.025,        pipe friction factor
    dp_pipe_max = heat_grid_data["pipe"]["dp_pipe_max"]     # 300Pa/m,      maximum pipe pressure gradient (Planungshandbuch Fernwärme)
    dp_pipe_min = heat_grid_data["pipe"]["dp_pipe_min"]     # 30Pa/m,       minimum pipe pressure gradient (Improved genetic algorithm for pipe diameter optimization of an existing large-scale district heating network https://doi.org/10.1016/j.energy.2024.131970)

    # pre-factor for pump power calculation
    prefac = (8 * f_fric) / (rho_f ** 2 * np.pi ** 2 * eta_pump) / 1000

    # Calculate minimum inner pipe diameters [mm] due to limitation of pipe friction
    for pipe_id, pipe in data.pipeline.items():
        # The allowable diameter range calculated based on the friction pressure loss formula(Darcy-Weisbach equation)
        # The minimum pipe diameter is determined by the maximum specific friction of 300 Pa/m.
        d_min_calc = ((8 * pipe["flow_max"] ** 2 * f_fric * rho_f) / (np.pi ** 2 * dp_pipe_max)) ** 0.2 * 1000  # mm
        pipe["d_min"] = d_min_calc
        # The maximum pipe diameter is determined by the minimum specific friction of 30 Pa/m.
        d_max_calc = ((8 * pipe["flow_max"] ** 2 * f_fric * rho_f) / (np.pi ** 2 * dp_pipe_min)) ** 0.2 * 1000  # mm
        # Ensure d_max is meaningfully larger than d_min:
        # For very low flow rates, d_max_calc can be almost equal to d_min_calc (numerically too close).
        # To avoid an unrealistically narrow or zero design range, enforce at least a 20 mm gap.
        pipe["d_max"] = max(d_max_calc, d_min_calc + 20)

    # Distance between the centerlines of the supply and return pipelines
    D_heating_network = data.heat_grid_data["D_heating_network"]  # 1m

    # 7 econimic factor
    # pipe
    # inv_earth_work = heat_grid_data["pipe"]["inv_earth_work"]  # 250EUR/m,  preparation costs for pipe installation
    # inv_pipe = heat_grid_data["pipe"]["inv_pipe"]              # 1146.71EUR/(m^2*m), price for PE pipe without insulation per diameter^2 and m pipe length
    pipe_lifetime = heat_grid_data["pipe"]["pipe_lifetime"]     # 30a,          pipe lifetime (VDI 2067)
    cost_om_pipe = heat_grid_data["pipe"]["cost_om_pipe"]       # 0.005         pipe operation and maintenance costs as share of investment (VDI 2067)

    # calculate the Annualization Factor and add to datahandler
    pipe_ann_factor = calc_annual_factor(data, pipe_lifetime)
    data.heat_grid_data["pipe"]["pipe_ann_factor"] = pipe_ann_factor

    # pump
    inv_pump = heat_grid_data["pump"]["inv_pump"]               # 700EUR/kW,    specific investment
    pump_lifetime = heat_grid_data["pump"]["pump_lifetime"]     # 10a,          pump lifetime (VDI 2067 Umwälzpumpe)

    price_el_pumps = data.ecoData["price_supply_el_eh"]    # 0.3141€/kWh,  electricity costs for pump supply used for network design (equals LEC of CHP for 7000 full load hours)
    cost_om_pump = heat_grid_data["pump"]["cost_om_pump"]       # 0.03          cost share for operation & maintenance

    # calculate the Annualization Factor and add to datahandler
    pump_ann_factor = calc_annual_factor(data, pump_lifetime)
    data.heat_grid_data["pump"]["pump_ann_factor"] = pump_ann_factor

    # heat loss
    p_gas = data.ecoData["price_supply_gas_eh"]                         # 0.1236€/kWh,  Gas price.
    eta_boiler = data.central_device_data["BOI"]["eta_th"]              # 0.99,         Thermal efficiency, source: Technikkatalog-Waermeplanung_Oktober2025.xlsx (Tabelle 20)
    p_co2 = data.params_ehdo_model["co2_tax"]                           # 0,            carbon pricing (0.055€/kg in Germany in 2025 from website https://carbonpricingdashboard.worldbank.org/compliance/price)
    EF = data.ecoData["co2_gas"]                                        # 0.201kg/kWh,  CO2 emissions by burning natural gas.
    inv_boiler = data.central_device_data["BOI"]["inv_var"]             # 138€/kW,      source: Technikkatalog-Waermeplanung_Oktober2025.xlsx (Tabelle 20)
    cost_om_boiler = data.central_device_data["BOI"]["cost_om"]         # 0.02,         1/year (fraction of inv_var) source: VDI2067
    boiler_lifetime = data.central_device_data["BOI"]["life_time"]      # 25a,          Maximum lifetime. source: Technikkatalog-Waermeplanung_Oktober2025.xlsx (Tabelle 20)
    boiler_ann_factor = calc_annual_factor(data, boiler_lifetime)
    heat_loss_prefac = p_gas / eta_boiler + p_co2 * EF                  # €/kWh,  total unit cost of producing heat to cover network heat losses.

    # 8 norm diameter
    pipe_dict = data.pipe_data.set_index("Nominal diameter (DN)").to_dict(orient="index")
    # To read data(eg. outer diameter) from pipes of different diameters, use pipe_dict[20][“outer diameter”]

    # precompute: d5: diameter^5 in m^5
    # the diameter here should use the inner diameter of the pipe
    d5 = {d: (pipe_dict[d]["Inner diameter (pipe) (mm)"] / 1000.0) ** 5 for d in pipe_dict.keys()}  # mm -> m and ^5

    # get possible norm diameter options for each pipe segment
    pipe_candidates = {}
    for pipe_id, pipe in data.pipeline.items():
        d_max = pipe["d_max"]
        d_min = pipe["d_min"]
        pipe_candidates[pipe_id] = []
        for DN in pipe_dict.keys():
            d_i = pipe_dict[DN]["Inner diameter (pipe) (mm)"]
            if d_i >= d_min and d_i <= d_max:
                pipe_candidates[pipe_id].append(DN)
    param["pipe_candidates"] = pipe_candidates

    # 9 heat loss parameters
    # soil temperature
    # T_soil = np.full((len(weeks), time_steps), 10.0)      # °C, simplified method with constant value
    T_soil_cluster = heat_grid_data["T_soil_cluster"]

    # coefficient of thermal conductivity
    k_soil = heat_grid_data["k_soil"]  # 1.52 W/(m*K),     Soil thermal conductivity, corresponding to λ_s in EN 13941
    k_pipe = heat_grid_data["k_PUF"]   # 0.03 W/(m*K),    Thermal conductivity of pipe insulation materials, corresponding to λ_i in EN 13941.

    # corrected value of depth
    # so that the surface transition insulance Ro at the soil surface is included
    Z_c = heat_grid_data["grid_depth"] + 0.069 * k_soil

    # symmetrical and (a) antisymmetrical heat loss factors
    # Heat Interference Correction Factor Between Pipes (Heat Transfer Between Supply and Return Water)
    b = np.log((1 + (2 * Z_c / D_heating_network) ** 2) ** 0.5)
    for DN, pipe in pipe_dict.items():
        da = pipe["Outer diameter (pipe) (mm)"]
        Da = pipe["Outer diameter (case) (mm)"]
        # The soil thermal resistance term depends on the burial depth Zc
        # and the outer diameter Da of the pipe plus insulation layer.
        a = np.log(4 * Z_c / (Da / 1000))
        # The thermal resistance component of the insulation layer depends on the outer diameter Da of the pipe plus
        # insulation layer and the outer diameter da of the steel pipe.
        beta = k_soil / k_pipe * np.log(Da/da)
        # ks / ka：symmetrical and (a) antisymmetrical heat loss factors according to zero-order multipole formula
        ks_heating_network = (a + beta + b) ** -1
        # ka_heating_network = (a + beta - b) ** -1
        pipe["symmetrical heat loss factor"] = ks_heating_network
        # pipe["antisymmetrical heat loss factor"] = ka_heating_network

    param["pipe_dict"] = pipe_dict

    # 10 network topology
    # Extract all the branches from the topology (from root node to terminal node)
    network = data.pipeline_topology
    path = extract_longest_branches(network)
    param["path"] = path

    # Build pair_to_pid mapping: oriented node pair -> pipe id (same as your Gurobi code)
    pair_to_pid = {}
    for pid, info in data.pipeline.items():
        pair_to_pid[(info["from"], info["to"])] = pid

    # %% STEP TWO: initialize the model and create sets
    # Create a new model
    model = pyo.ConcreteModel(name="grid_pipe_diameters")

    model.pipe = pyo.Set(initialize=data.pipeline.keys(), doc="Pipe segments in the network")
    model.week = pyo.Set(initialize=weeks, doc="Typical weeks")
    model.t = pyo.Set(initialize=range(time_steps), doc="Time steps within a typical week")

    # Because candidate diameters differ per pipe, build a (pipe,diam) pair set
    pipe_diam_pairs = [(p, d) for p in pipe_candidates for d in pipe_candidates[p]]
    model.pipe_diam = pyo.Set(dimen=2, initialize=pipe_diam_pairs,
                              doc="Pairs of pipe and its feasible diameters")

    # Also define a set of devices for investments (pipes,pumps,BOI) to hold inv / tac
    invest_devs = ["pipes", "pumps", "BOI"]
    model.invest_devs = pyo.Set(initialize=invest_devs, doc="Device types for investment & cost tracking")

    lines = list(path.keys())
    model.lines = pyo.Set(initialize=lines, doc="List of path lines")

    # %% STEP THREE: create variables
    # Binary choice: z[p,d] == 1 if pipe p uses diameter d
    model.z = pyo.Var(model.pipe_diam, within=pyo.Binary, doc="1 if pipe p uses diameter d")

    # Pump power for each pipe segment, week, timestep (unbounded real) -- corresponds to pump_pipe[pipe][week][t]
    model.pump_pipe = pyo.Var(model.pipe, model.week, model.t, within=pyo.NonNegativeReals,
                              doc="Pump power per pipe, week, and timestep (kW)")

    # pump_el[week,t] -- pump power per path/time aggregated (kW)
    model.pump_el = pyo.Var(model.week, model.t, within=pyo.NonNegativeReals, doc="Total pump power at each timestep (kW)")

    # pump design capacity (max of pump power) (kW) - non-negative
    model.pump_cap = pyo.Var(within=pyo.NonNegativeReals, initialize=0.0, doc="Pump design capacity (kW)")

    # total annual pump energy (kWh)
    model.pump_energy_total = pyo.Var(within=pyo.NonNegativeReals, initialize=0.0, doc="Total annual pump energy (kWh)")

    # heat loss per pipe/week/t (kW)
    model.heat_loss_pipe = pyo.Var(model.pipe, model.week, model.t, within=pyo.NonNegativeReals,
                                   doc="Heat loss per pipe, week, timestep (kW)")

    # Additional boiler capacity (kW) required to compensate network heat losses
    model.boiler_cap = pyo.Var(within=pyo.NonNegativeReals, initialize=0.0, doc="Additional boiler capacity (kW) to cover heat losses")

    # total annual heat loss (kWh)
    model.heat_loss_total = pyo.Var(within=pyo.NonNegativeReals, initialize=0.0, doc="Total annual heat loss (kWh)")

    # total annualized network cost (EUR)
    model.tac_network = pyo.Var(within=pyo.NonNegativeReals, initialize=0.0,
                                doc="Total annualized cost of network (EUR)")

    # investment and TAC variables for devices (indexed)
    model.inv = pyo.Var(model.invest_devs, within=pyo.NonNegativeReals, initialize=0.0,
                        doc="Investment costs by device (EUR)")
    model.tac = pyo.Var(model.invest_devs, within=pyo.NonNegativeReals, initialize=0.0,
                        doc="Annualized costs by device (EUR)")

    # %% STEP FOUR: define the constraints
    # 1) Each pipe must choose exactly one diameter
    def choose_one_diameter_rule(model, pipe):
        return sum(model.z[pipe, d] for d in pipe_candidates[pipe]) == 1

    model.choose_one_diameter = pyo.Constraint(model.pipe, rule=choose_one_diameter_rule,
                                               doc="Each pipe picks exactly one diameter")

    # 2) Pump power relation per pipe/week/t
    # P_p,w,t = Σ_d [ prefac * L_p * 2*(1+0.2) * (ρ_f * V̇_p,w,t)^3 / D_d^5 ] * z[p,d]
    # prefac already contains 8*f_fric/(π²*η_pump*ρ_f²)/1000  → kW units

    def pump_pipe_relation_rule(model, pipe, week, t):
        i = week_to_i[week]
        flow_value = data.pipeline[pipe]["flow_cluster"][i, t]  # m³/s

        length = data.pipeline[pipe]["length"]  # m
        m_dot = rho_f * flow_value  # kg/s

        # If flow is exactly zero, RHS will be 0 and pump_pipe will be forced to 0 anyway
        return model.pump_pipe[pipe, week, t] == sum(
            prefac * length * 2.0 * (1.0 + 0.2)
            * (m_dot ** 3)
            / ((pipe_dict[d]["Inner diameter (pipe) (mm)"] / 1000.0) ** 5)
            * model.z[pipe, d]
            for d in pipe_candidates[pipe]
        )

    model.pump_pipe_relation = pyo.Constraint(
        model.pipe, model.week, model.t,
        rule=pump_pipe_relation_rule,
        doc="Pump power vs diameter-flow relation (kW)"
    )

    # 3) For each path (line) and time, pump_el >= sum of pump_pipe along the path
    def pump_el_ge_path_rule(model, line, week, t):
        nodes = path[line]
        # accumulate pump_pipe for each pipe along the path (orientation a->b)
        expr = sum(model.pump_pipe[pair_to_pid[(nodes[i], nodes[i + 1])], week, t] for i in range(len(nodes) - 1))

        i = week_to_i[week]
        extraP = P_station_cluster[i, t]  # kW

        return model.pump_el[week, t] >= expr + extraP

    model.pump_el_ge_path = pyo.Constraint(model.lines, model.week, model.t, rule=pump_el_ge_path_rule,
                                           doc="pump_el >= sum of pump_pipe along path")

    # 4) pump_el <= pump_cap for design capacity bounding at each time
    def pump_cap_rule(model, week, t):
        return model.pump_el[week, t] <= model.pump_cap

    model.pump_capacity_limit = pyo.Constraint(model.week, model.t, rule=pump_cap_rule,
                                               doc="pump_el <= pump_cap for every time / design capacity constraint")

    # 5) pump_energy_total == sum_t sum_week (pump_el[t] * clusterWeight[week])
    def pump_energy_total_rule(model):
        return model.pump_energy_total == sum(sum(model.pump_el[w, t] for t in model.t) * data.clusterWeights[w] for w in model.week)

    model.pump_energy_total_constr = pyo.Constraint(rule=pump_energy_total_rule,
                                                    doc="Total annual pump energy (kWh)")

    # 6) heat_loss per pipe/week/t
    # ks = sum(pipe_dict[d]['symmetrical heat loss factor'] * z[p,d] for d in candidates)
    # *2: The first factor of two accounts for the heat loss of both the supply and return pipes.
    # *2: The second factor of two is in the equation of calculating q_s from DIN EN 13941.
    def heat_loss_rule(model, pipe, week, t):
        ks = pyo.quicksum(pipe_dict[d]["symmetrical heat loss factor"] * model.z[pipe, d] for d in pipe_candidates[pipe])
        i = week_to_i[week]
        length = data.pipeline[pipe]["length"]
        return model.heat_loss_pipe[pipe, week, t] == 2 * (T_s_cluster[i, t] - T_soil_cluster[i, t]) * 2 * np.pi * k_soil * ks * length / 1000

    model.heat_loss_def = pyo.Constraint(model.pipe, model.week, model.t, rule=heat_loss_rule,
                                         doc="Heat loss calculation per pipe/week/t")

    # 7) Additional boiler capacity must be >= heat loss at each pipe/week/t
    def boiler_capacity_rule(model, week, t):
        return pyo.quicksum(model.heat_loss_pipe[pipe, week, t] for pipe in model.pipe) <= model.boiler_cap

    model.boiler_capacity_constr = pyo.Constraint(model.week, model.t, rule=boiler_capacity_rule,
                                                  doc="Additional boiler capacity must cover total pipe heat losses")

    # 8) Total heat loss in a year (sum over pipes, weeks, time weighted by cluster weights)
    def total_heat_loss_rule(model):
        return model.heat_loss_total == pyo.quicksum(
            pyo.quicksum(model.heat_loss_pipe[pipe, week, t] for t in model.t) * data.clusterWeights[week]
            for pipe in model.pipe for week in model.week
        )

    model.total_heat_loss_constr = pyo.Constraint(rule=total_heat_loss_rule,
                                                  doc="Total annual heat loss (kWh)")

    # %% STEP FIVE: define the objective function
    # 1) Investment and TAC calculations for the *additional* boiler capacity
    def inv_boiler_rule(model):
        return model.inv["BOI"] == model.boiler_cap * inv_boiler

    model.inv_boiler_constr = pyo.Constraint(rule=inv_boiler_rule,
                                             doc="Boiler investment = capacity * unit cost")

    def tac_boiler_rule(model):
        return model.tac["BOI"] == model.inv["BOI"] * (boiler_ann_factor + cost_om_boiler)

    model.tac_boiler_constr = pyo.Constraint(rule=tac_boiler_rule, doc="TAC for additional boiler capacity")

    # 2) Pump investment and TAC
    def inv_pump_rule(model):
        return model.inv["pumps"] == model.pump_cap * inv_pump

    model.inv_pump_constr = pyo.Constraint(rule=inv_pump_rule, doc="Pump investment = pump_cap * unit cost")

    def tac_pump_rule(model):
        return model.tac["pumps"] == model.inv["pumps"] * (pump_ann_factor + cost_om_pump)

    model.tac_pump_constr = pyo.Constraint(rule=tac_pump_rule, doc="Pump TAC")

    # 3) Investment and TAC for pipes
    def inv_earth_work_expr(model, pipe):
        return pyo.quicksum(pipe_dict[d]["Construction Cost (€/m)"] * model.z[pipe, d] for d in pipe_candidates[pipe])

    model.inv_earth_work = pyo.Expression(model.pipe, rule=inv_earth_work_expr,
                                          doc="Earth work cost per m given chosen diameter")

    def inv_pipe_cost_expr(model, pipe):
        return sum(pipe_dict[d]["Pipe Cost (€/m)"] * model.z[pipe, d] for d in pipe_candidates[pipe])

    model.inv_pipe_cost = pyo.Expression(model.pipe, rule=inv_pipe_cost_expr,
                                         doc="Pipe cost per m given chosen diameter")

    # inv["pipes"] >= sum((inv_earth_work + inv_pipe_cost) * length)
    # 2 * : for supply and return pipelines
    def inv_pipes_rule(model):
        return model.inv["pipes"] >= sum(
            (model.inv_earth_work[p] + 2 * model.inv_pipe_cost[p]) * data.pipeline[p]["length"] for p in model.pipe)

    model.inv_pipes_constr = pyo.Constraint(rule=inv_pipes_rule, doc="Total pipe investment lower bound")

    # tac["pipes"] == inv["pipes"] * (pipe_ann_factor + cost_om_pipe)
    def tac_pipes_rule(model):
        return model.tac["pipes"] == model.inv["pipes"] * (pipe_ann_factor + cost_om_pipe)

    model.tac_pipes_constr = pyo.Constraint(rule=tac_pipes_rule, doc="Pipe TAC calculation")

    # 4) Total annualized network cost linking and objective
    def tac_network_rule(model):
        # tac_network == tac_pipes + tac_pumps + tac_BOI + pump_energy_total*price_el_pumps + heat_loss_total*heat_loss_prefac
        return model.tac_network == (model.tac["pipes"] + model.tac["pumps"] + model.tac["BOI"]
                                     + model.pump_energy_total * price_el_pumps
                                     + model.heat_loss_total * heat_loss_prefac)

    model.tac_network_constr = pyo.Constraint(rule=tac_network_rule,
                                              doc="Link tac_network to components")

    # Objective: minimize tac_network
    model.objective = pyo.Objective(expr=model.tac_network, sense=pyo.minimize,
                              doc="Minimize total annualized network cost")

    print("Pyomo model built successfully")

    # %% STEP SIX: solve the model and output
    # Folder to save model and results
    dir_dia = data.resultPath + "\\diameters"
    if not os.path.exists(dir_dia):
        os.makedirs(dir_dia)

    generation = heat_grid_data["generation"]
    topology = heat_grid_data["topology_option"]
    temperature_mode = heat_grid_data["temperature_mode"]
    result_folder = f"{data.scenario_name}_{generation}_{topology}_{temperature_mode}"
    dir_result = os.path.join(dir_dia, result_folder)
    if not os.path.exists(dir_result):
        os.makedirs(dir_result)

    lp_filename = os.path.join(dir_result, "opti_pipe_diameter_model.lp")
    model.write(lp_filename, io_options={'symbolic_solver_labels': True})

    # temporary log-file for the solver
    solver_log_path = os.path.join(dir_result, "solver_output.log")

    # Solve the model
    solver, solver_options = solver_config.create_solver(pyomo_config=data.pyomo_config)

    solver_options["primal_feasibility_tolerance"] = 1e-9
    solver_options["mip_feasibility_tolerance"] = 1e-9

    results = solver.solve(model, tee=True, options=solver_options)

    return data, model, param

def output_diameter(data, model, param):
    """
    Output the optimization solution file and plot solutions

    Parameters
    ----------
    data: class datahandler
    model: pyomo optimization model
    param: dictionary

    Returns
    -------
    data: class datahandler
    """
    # Folder to save model and results
    dir_dia = data.resultPath + "\\diameters"
    if not os.path.exists(dir_dia):
        os.makedirs(dir_dia)

    generation = data.heat_grid_data["generation"]
    topology = data.heat_grid_data["topology_option"]
    temperature_mode = data.heat_grid_data["temperature_mode"]
    result_folder = f"{data.scenario_name}_{generation}_{topology}_{temperature_mode}"
    dir_result = os.path.join(dir_dia, result_folder)
    if not os.path.exists(dir_result):
        os.makedirs(dir_result)

    # Save all variable values in a solution file:
    def write_solution_file(model, filename):
        """
        Write solution values to a file in a format similar to Gurobi's .sol files
        """
        try:
            with open(filename, 'w') as f:
                f.write("# Solution file\n")
                f.write(f"# Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"# Objective value: {pyo.value(model.objective)}\n")
                f.write("# Variable values\n")

                # Write all variable values
                for var in model.component_objects(pyo.Var, active=True):
                    if var.is_indexed():
                        for index in var:
                            if var[index].value is not None:
                                f.write(f"{var.name}[{index}] {var[index].value:.6f}\n")
                    else:
                        if var.value is not None:
                            f.write(f"{var.name} {var.value:.6f}\n")

                f.write("# End of solution\n")
            print(f"Solution written to {filename}")

        except Exception as e:
            print(f"Warning: Could not write solution file {filename}: {e}")
        return None

    solution_file = os.path.join(dir_result, 'solution_file.txt')
    write_solution_file(model, solution_file)

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

    plt.show()

    # ---------- 2. plot Pipeline Map - Diameter ----------
    # get the optimized diameter for each pipe segment
    pipe_candidates = param["pipe_candidates"]
    for pipe in data.pipeline.keys():
        for d in pipe_candidates[pipe]:
            if pyo.value(model.z[pipe, d]) > 0.5:
                data.pipeline[pipe]["DN"] = d
                break  # Once the selected pipe diameter is found, exit the loop.

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

    plt.show()

    # ---------- 3. plot Pipeline Map - Maximum velocity (m/s) ----------
    # calculate the max. velocity and the max. pressure drop
    c_f = data.heat_grid_data["fluid"]["c_f"]  # 4180J/(kg*K), fluid specific heat capacity
    rho_f = data.heat_grid_data["fluid"]["rho_f"]  # 1000kg/m^3,   fluid density
    pipe_dict = param["pipe_dict"]
    f_fric = param["f_fric"]
    for pipe_id, pipe in data.pipeline.items():
        flow_max = pipe["flow_max"]  # m3/s
        DN = pipe["DN"]  # mm
        d_i = pipe_dict[DN]["Inner diameter (pipe) (mm)"]  # mm
        # length = pipe["length"]             # m
        pipe["velocity_max"] = flow_max / (np.pi * (d_i / 1000) ** 2 / 4)  # m/s
        pipe["pressure_drop_max"] = f_fric * 8 * rho_f * flow_max ** 2 / (np.pi ** 2 * (d_i / 1000) ** 5)  # Pa/m

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

    plt.show()

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

    plt.show()

    # ---------- 5. plot Pipeline Map - Energy_density (MWh/m) ----------
    deltaT = param["deltaT"]
    for pipe_id, pipe in data.pipeline.items():
        # c_f in J/kg·K, rho_f in kg/m3
        flow = pipe["flow"]  # m3/s
        length = pipe["length"]  # m
        energy_total = np.sum(c_f * flow * rho_f * deltaT) / 1000000  # MWh
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

    plt.show()

    # ---------- 6. save heat loss(yearly profile) ----------
    # save heat loss(yearly profile) in data.heat_grid_data["total_losses_heating_network"]
    # load heat loss in substation
    heat_loss_substation = param["heat_loss_substation"]

    # calculate heat loss in network
    T_s = param["T_s"]
    T_soil = data.heat_grid_data["T_soil"]
    k_soil = data.heat_grid_data["k_soil"]
    heat_loss_network = np.zeros_like(T_s)
    # print(type(T_s), type(T_soil), T_s.shape, getattr(T_soil, "shape", None))
    total_pipe_length = 0
    for pipe_id, pipe in data.pipeline.items():
        DN = pipe["DN"]  # mm
        ks = pipe_dict[DN]["symmetrical heat loss factor"]
        length = pipe["length"]
        total_pipe_length += length
        # *2: The first factor of two accounts for the heat loss of both the supply and return pipes.
        # *2: The second factor of two is in the equation of calculating q_s from DIN EN 13941.
        pipe["heat_loss_pipe"] = 2 * (T_s - T_soil) * 2 * np.pi * k_soil * ks * length / 1000   # kW
        heat_loss_network += pipe["heat_loss_pipe"]

    # calculate and save total heat loss
    heat_loss_total = heat_loss_substation + heat_loss_network
    data.heat_grid_data["total_losses_heating_network"] = heat_loss_total
    annual_heat_loss = np.sum(heat_loss_total)
    total_heat_loss_per_m = annual_heat_loss / total_pipe_length
    print("Total heat loss in network calculation finished successfully.")
    print(f"Annual heat loss in pipeline network is {total_heat_loss_per_m:.2f} kWh per meter.")

    # ---------- 7. save pump power(yearly profile) ----------
    # save pump power(yearly profile) in data.heat_grid_data["pump_power"]
    f_fric = param["f_fric"]
    eta_pump = data.heat_grid_data["pump"]["eta_pump"]  # 0.65,         electric pump efficiency
    prefac = (8 * f_fric) / (rho_f ** 2 * np.pi ** 2 * eta_pump) / 1000
    pump_power_pipe = {}
    for pipe_id, pipe in data.pipeline.items():
        DN = pipe["DN"]  # mm
        d_i = pipe_dict[DN]["Inner diameter (pipe) (mm)"]  # mm
        length = pipe["length"]  # m
        flow = pipe["flow"]  # m3/s
        # *2: The first factor of two accounts for the pump power of both the supply and return pipes.
        # *1.2: The factor of 1.2 accounts for an additional 20% of local losses.(source: Planungshandbuch Fernwärme)
        pump_power_pipe[pipe_id] = prefac * length * 2 * (1 + 0.2) * ((flow * rho_f) ** 3) / ((d_i / 1000) ** 5)

    # Build mapping from oriented node pair to pipe id (assume unique per pair)
    pair_to_pid = {}
    for pid, info in data.pipeline.items():
        pair_to_pid[(info["from"], info["to"])] = pid

    path = param["path"]
    pump_power_line = {}
    for line, nodes in path.items():
        # Initialize pump power array for this line
        pump = np.zeros_like(T_s)
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
    dp_substation = data.heat_grid_data.get("dp_substation", {}).get("value", 0.0)  # Pa
    dp_energy_hub = data.heat_grid_data.get("dp_energy_hub", {}).get("value", 0.0)  # Pa
    dp_station_total = dp_substation + dp_energy_hub                                # Pa

    # Approximate total volume flow at energy hub as sum of flows leaving EH1
    T_s = param["T_s"]  # only used for shape
    Vdot_total_profile = np.zeros_like(T_s, dtype=float)
    for pipe_id, pipe in data.pipeline.items():
        if pipe["from"] == "EH1":
            Vdot_total_profile += pipe["flow"]  # m³/s

    # Extra pump power from substations + energy hub
    # P = V̇ * Δp / (η * 1000)
    P_station_profile = Vdot_total_profile * dp_station_total / (eta_pump * 1000.0)  # kW

    # Final pump power: pipe friction (worst line) + station/hub component
    pump_power = np.max(pump_matrix, axis=0) + P_station_profile

    data.heat_grid_data["pump_power"] = pump_power
    print("Total pump power in network calculation finished successfully.")

    # ---------- 8. save cost ----------
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
    print(f"Substations annualized cost: {substation_ann_costs:.2f} €")
    print(f"Substations O&M cost per year: {substation_om_costs:.2f} €")

    # cost of pipes
    pipes_tac_costs = pyo.value(model.tac["pipes"])
    pipe_ann_factor = data.heat_grid_data["pipe"]["pipe_ann_factor"]
    cost_om_pipe = data.heat_grid_data["pipe"]["cost_om_pipe"]
    pipes_om_costs = pipes_tac_costs * cost_om_pipe / (pipe_ann_factor + cost_om_pipe)
    pipes_ann_costs = pipes_tac_costs - pipes_om_costs
    print(f"Pipes annualized cost: {pipes_ann_costs:.2f} €")
    print(f"Pipes O&M cost per year: {pipes_om_costs:.2f} €")

    # calculate the capacity of the pump
    pump_cap = np.max(pump_power)
    print(f"The capacity of the pump should be bigger than {pump_cap:5f}kW.")

    # calculate the investment for the pump
    inv_pump = pump_cap * data.heat_grid_data["pump"]["inv_pump"]

    # cost of pump
    pump_ann_costs = inv_pump * data.heat_grid_data["pump"]["pump_ann_factor"]
    pump_om_costs = inv_pump * data.heat_grid_data["pump"]["cost_om_pump"]
    print(f"Pump annualized cost: {pump_ann_costs:.2f} €")
    print(f"Pump O&M cost per year: {pump_om_costs:.2f} €")

    # cost of electricity
    pump_energy_total = np.sum(pump_power)
    print(f"The total electricity consumption for the pump is {pump_energy_total:5f}kWh/a.")
    electricity_costs = pump_energy_total * data.ecoData["price_supply_el_eh"]

    # calculate the total cost
    network_om_costs = pipes_om_costs + pump_om_costs + substation_om_costs
    network_ann_costs = pipes_ann_costs + pump_ann_costs + electricity_costs + substation_ann_costs
    data.heat_grid_data["om_costs"] = network_om_costs
    data.heat_grid_data["ann_costs"] = network_ann_costs

    # save energy and costs to a json-file
    results = {
        "f_fric": {
            "value": float(f_fric),
            "unit": "-",
            "description": "Darcy friction factor used in the hydraulic calculation"
        },
        "total_pipe_length": {
            "value": float(total_pipe_length),
            "unit": "m",
            "description": "Sum of all pipe segments in the network"
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
        "annual_heat_loss": {
            "value": float(annual_heat_loss),
            "unit": "kWh",
            "description": "Annual heat loss (including pipelines and substations)"
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
        "network_ann_costs": {
            "value": float(network_ann_costs),
            "unit": "€",
            "description": "Total annualized investment for the heating network"
        },
        "network_om_costs": {
            "value": float(network_om_costs),
            "unit": "€",
            "description": "Total O&M cost for the heating network"
        }
    }

    json_path = os.path.join(dir_result, "parameters_outputs.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, ensure_ascii=False)

    print("Saved JSON to:", json_path)

    return data

def calc_f_fric(data, model, param):
    """
    Calculate the friction factor based on the optimization results.

    Parameters
    ----------
    data: class datahandler
    model: pyomo optimization model
    param: dictionary

    Returns
    -------
    f_fric: float
    """
    # 1 calculate the Reynolds number
    # get the optimized diameter for each pipe segment
    pipe_candidates = param["pipe_candidates"]
    pipe_result = {}
    for pipe in data.pipeline.keys():
        pipe_result[pipe] = {}
        for d in pipe_candidates[pipe]:
            if pyo.value(model.z[pipe, d]) > 0.5:
                pipe_result[pipe]["DN"] = d
                break  # Once the selected pipe diameter is found, exit the loop.

    pipe_dict = param["pipe_dict"]
    nu_f = data.heat_grid_data["fluid"]["nu_f"]    # m2/s

    for pipe in data.pipeline.keys():
        flow_max = data.pipeline[pipe]["flow_max"]  # m3/s
        DN = pipe_result[pipe]["DN"]  # mm
        d_i = pipe_dict[DN]["Inner diameter (pipe) (mm)"]  # mm
        k = pipe_dict[DN]["Roughness (mm)"]  # mm

        # calculate the maximum velocity
        v_max = flow_max / (np.pi * (d_i / 1000) ** 2 / 4)  # m/s
        # calculate the Reynolds number
        Re = v_max * (d_i / 1000) / nu_f

        # f_fric is calculated by friction_factor() using the default Clamond method for turbulent flow.
        pipe_result[pipe]["f_fric"] = fluids.friction.friction_factor(Re=Re, eD=k/d_i)

    f_fric = sum(pipe_result[pipe]["f_fric"] for pipe in data.pipeline.keys())/len(data.pipeline.keys())

    return f_fric

def network_optimization(data):
    """
    Optimize pipe diameter and iterate on friction factor

    Parameters
    ----------
    data: class datahandler

    Returns
    -------
    data: class datahandler
    """
    # calculate flow and temperature and prepare for the optimization
    data, param = calc_flow_and_temperature(data)

    # get the initial friction factor
    f_fric_new = data.heat_grid_data["pipe"]["f_fric"]  # 0.025,        pipe friction factor
    f_fric_old = f_fric_new

    # Set maximum iteration count
    max_iter = 30
    tol = 5e-4
    converged = False
    for i in range(max_iter):
        # run the optimization
        data, model, param = optimization_diameter(data, param, f_fric_new)
        f_fric_new = calc_f_fric(data, model, param)

        # print the current iteration status
        print(f"Iteration {i + 1}: f_fric_old = {f_fric_old:.6f}, f_fric_new = {f_fric_new:.6f}")

        # Check convergence
        if abs(f_fric_new - f_fric_old) < tol:
            converged = True
            print(f"Converged after {i + 1} iterations. Final f_fric = {f_fric_new:.6f}")
            break

        # Update value for next iteration
        f_fric_old = f_fric_new

    if not converged:
        print(f"Not converged after {max_iter} iterations. Last f_fric = {f_fric_new:.6f}")

    param["f_fric"] = f_fric_new

    output_diameter(data, model, param)

    return data
