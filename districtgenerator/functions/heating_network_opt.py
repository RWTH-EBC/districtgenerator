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
import textwrap
from scipy.interpolate import interp1d
# from districtgenerator.functions.load_params_central_devices import calc_COP

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
    # ---------- 1. prepare parameters for the optimization ----------
    # calculate supply and return temperature
    data, param = load_parameter(data)

    # set result path
    dir_dia = data.resultPath + "\\network"
    if not os.path.exists(dir_dia):
        os.makedirs(dir_dia)

    generation = data.heat_grid_data["generation"]["value"]
    topology = data.heat_grid_data["topology_option"]["value"]
    temperature_mode = data.heat_grid_data["temperature_mode"]["value"]
    result_folder = f"{data.scenario_name}_{generation}_{topology}_{temperature_mode}"
    dir_result = os.path.join(dir_dia, result_folder)
    if not os.path.exists(dir_result):
        os.makedirs(dir_result)

    # save result path in param
    param["dir_result"] = dir_result
    data.heat_grid_data["resultPath"] = dir_result

    # calculate the flow (heat loss is first neglected in calculating flow)
    # initialize the attribute to store pipeline information
    data.pipeline = {}
    # define the save path for the pipeline information (only for check the differences across various stages)
    file_path = os.path.join(dir_result, "pipe_preprocess.json")
    data, param = calc_flow(data, param, heat_loss_pipe=None, heat_loss_pipe_cluster=None, save_path=file_path)

    # ---------- 2. optimize or calculate the pipe diameter ----------
    # decide whether to optimize or calculate the diameter (can be changed in heat_grid.json)
    heuristic = data.heat_grid_data["heuristic"]["value"]

    # The friction factor is determined iteratively because it is tightly coupled with pipe diameter and flow velocity,
    # which would otherwise introduce nonlinear constraints to the optimization.
    # get the initial friction factor
    f_fric_new = data.heat_grid_data["pipe"]["f_fric"]["value"]  # 0.025,        pipe friction factor
    f_fric_old = f_fric_new

    # Set maximum iteration count
    max_iter = 30
    tol = 5e-4
    converged = False
    for i in range(max_iter):
        if heuristic == False:
            # run the optimization
            data, model, param = optimization_diameter(data, param, f_fric_new)
        else:
            # calculate the diameter of each pipeline segments based on the maximum permitted pressure drop
            data, param = calc_diameter(data, param, f_fric_new)

        # calculate the heat loss with the diameter result
        data, heat_loss_pipe, heat_loss_pipe_cluster = calc_heat_loss_pipe(data, param)

        # recalculate the flow with heat loss
        file_path = os.path.join(dir_result, f"pipe_iter_{i+1}.json")
        data, param = calc_flow(data, param, heat_loss_pipe=heat_loss_pipe,
                                heat_loss_pipe_cluster=heat_loss_pipe_cluster, save_path=file_path)

        # calculate the friction factor with the diameter result
        f_fric_new = calc_f_fric(data, param)

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

    # save the final converged friction factor
    param["f_fric"] = f_fric_new

    if heuristic == False:
        # write the optimization solution file
        solution_file = os.path.join(dir_result, 'solution_file.txt')
        write_solution_file(model, solution_file)

    # output and process the results
    output_diameter(data, param)

    return data

def to_jsonable(obj):
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, tuple):
        return list(obj)
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    return obj

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

def aggregate_heat_loads(network, building_demand, heat_loss_pipe=None, root="EH1"):
    """
    Aggregate pipe flows from buildings to plant

    Parameters
    ----------
    network : dict
        Network topology, key = parent node, value = list of child nodes
    building_demand : dict
        key = building name, value = ndarray of heat loads (W or kW).
    heat_loss_pipe : dict
        key = (parent, child), value = ndarray of heat loss on this pipe.
    root : string
        Root node name

    Returns
    -------
    pipe_loads : dict
        key= (parent, child), value=ndarray of heat delivered into that pipe AFTER loss deduction.
    """
    if heat_loss_pipe is None:
        heat_loss_pipe = {}

    pipe_loads = {}

    def dfs(node):
        """
        Returns total *heat demand* from the subtree under this node.

        Parameters
        ----------
        node : str
            Current node being processed in the DFS traversal.

        Returns
        -------
        total_load : ndarray, same shape with the value of building_demand
            Including building load + downstream loads + heat losses
        """

        total_load = 0
        # If the current node represents a building, add its own flow
        if node in building_demand:
            total_load += building_demand[node]

        # If there are no downstream nodes → this is a terminal node
        # Return its own flow directly
        if not network.get(node, []):
            return total_load

        # Traverse all child nodes and accumulate their loads
        for child in network[node]:
            downstream_load = dfs(child)

            # Deduct pipe heat loss
            loss = heat_loss_pipe.get((node, child), 0)
            delivered = downstream_load + loss

            # Store the load carried in this pipe
            pipe_loads[(node, child)] = delivered

            # This node must provide what's delivered onward
            total_load += delivered

        return total_load

    # Start the recursive traversal from the root node (energy hub)
    dfs(root)
    return pipe_loads

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

# Heat pump COP, part 2: Generalized COP estimation of heat pump processes
# DOI: 10.18462/iir.gl.2018.1386
# Source: JENSEN J. et al. Heat pump COP, part 2: generalized COP estimation of heat pump processes.
def calc_COP(devs_param, temperatures):
    """
    calculate COP of Heat Pump
    (Modified version of calc_COP from load_params_central_devices.py)

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

    # Entropic mean temperautures (or Logarithmic mean temperatures)
    t_h_s = dt_h / np.log((t_h_in + dt_h) / t_h_in)
    t_c_s = dt_c / np.log(t_c_in / (t_c_in - dt_c))

    # Prevent numeric issues
    t_h_s = np.where(t_h_s == t_c_s, t_h_s + 1e-5, t_h_s)

    # Lorentz-COP
    COP_Lor = t_h_s / (t_h_s - t_c_s)

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
    COP_max = devs_param["COP_max"]
    COP = np.clip(COP, 0, COP_max)

    return COP

def load_parameter(data):
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
    generation = heat_grid_data["generation"]["value"]
    temperature_mode = heat_grid_data["temperature_mode"]["value"]
    if temperature_mode == "Heating_curve":
        # Variable-constant operation mode (Heating curve)
        T_supply_min = heat_grid_data["T_hot_heating_network"]["Heating_curve"]["min"][generation]["value"]
        T_supply_max = heat_grid_data["T_hot_heating_network"]["Heating_curve"]["max"][generation]["value"]
        T_return_min = heat_grid_data["T_cold_heating_network"]["Heating_curve"]["min"][generation]["value"]
        T_return_max = heat_grid_data["T_cold_heating_network"]["Heating_curve"]["max"][generation]["value"]
        T_supply_cluster, T_return_cluster = heating_curve(T_e_cluster, T_supply_min, T_supply_max, T_return_min,
                                                           T_return_max)
        T_supply, T_return = heating_curve(T_e, T_supply_min, T_supply_max, T_return_min, T_return_max)
    elif temperature_mode == "Constant":
        # Constant operation mode
        T_supply_value = heat_grid_data["T_hot_heating_network"]["Constant"][generation]["value"]
        T_return_value = heat_grid_data["T_cold_heating_network"]["Constant"][generation]["value"]
        T_supply = np.full_like(T_e, T_supply_value)
        T_return = np.full_like(T_e, T_return_value)
        T_supply_cluster = np.full((len(weeks), time_steps), T_supply_value)  # °C
        T_return_cluster = np.full((len(weeks), time_steps), T_return_value)  # °C
    else:
        message = "Please select a valid temperature mode between 'Heating_curve' and 'Constant' in heat_grid.json."
        print(message)

    # ΔT = T_supply - T_return (°C)
    # if Constant operation mode, int
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

    # 4 load heating demand for each building
    heat_loss_substation = np.zeros_like(deltaT)
    heat_supply = np.zeros_like(deltaT)
    h_loss_subst = data.heat_grid_data["h_loss_subst"]["value"]  # 5%, Heat losses at the substation

    for building in data.district:
        if building["buildingFeatures"]["heater"] == "heat_grid":
            # read (clustered) demand pofile for each building
            # clustered value (for the optimization)
            heating_cluster = building["user"].heat_cluster / 1000  # kW
            dhw_cluster = building["user"].dhw_cluster / 1000  # kW
            generationSTC_cluster = building["generationSTC_cluster"] / 1000  # kW

            heating_demand_cluster = np.maximum(heating_cluster + dhw_cluster - generationSTC_cluster, 0)  # kW
            building["user"].heating_demand_cluster = heating_demand_cluster  # kW

            # year profile (for calculation of max and min permitted pipeline diameter)
            heating = building["user"].heat / 1000  # kW
            dhw = building["user"].dhw / 1000  # kW
            generationSTC = building["generationSTC"] / 1000  # kW

            heating_demand = np.maximum(heating + dhw - generationSTC, 0)  # kW
            building["user"].heating_demand = heating_demand  # kW
            # Sum the heat losses in the substations
            heat_loss_substation += heating_demand * (h_loss_subst / 100)  # kW
            # Sum the heat demand in the network
            heat_supply += heating_demand

    # 4 norm diameter
    pipe_dict = data.pipe_data.set_index("Nominal diameter (DN)").to_dict(orient="index")
    # To read data(eg. outer diameter) from pipes of different diameters, use pipe_dict[20][“outer diameter”]

    # 5 heat loss parameters
    # coefficient of thermal conductivity
    k_soil = heat_grid_data["k_soil"]["value"]  # 1.52 W/(m*K),     Soil thermal conductivity, corresponding to λ_s in EN 13941
    k_pipe = heat_grid_data["k_PUF"]["value"]  # 0.03 W/(m*K),    Thermal conductivity of pipe insulation materials, corresponding to λ_i in EN 13941.

    # corrected value of depth
    # so that the surface transition insulance Ro at the soil surface is included
    Z_c = heat_grid_data["grid_depth"]["value"] + 0.069 * k_soil

    # Distance between the centerlines of the supply and return pipelines
    D_heating_network = data.heat_grid_data["D_heating_network"]["value"]  # 1m

    # symmetrical and (a) antisymmetrical heat loss factors
    # Heat Interference Correction Factor Between Pipes (Heat Transfer Between Supply and Return Water)
    b = np.log((1 + (2 * Z_c / D_heating_network) ** 2) ** 0.5)     # DIN EN 13941-1 D.3
    for DN, pipe in pipe_dict.items():
        da = pipe["Outer diameter (pipe) (mm)"]
        Da = pipe["Outer diameter (case) (mm)"]
        # The soil thermal resistance term depends on the burial depth Zc
        # and the outer diameter Da of the pipe plus insulation layer.
        a = np.log(4 * Z_c / (Da / 1000))           # DIN EN 13941-1 D.3
        # The thermal resistance component of the insulation layer depends on the outer diameter Da of the pipe plus
        # insulation layer and the outer diameter da of the steel pipe.
        beta = k_soil / k_pipe * np.log(Da / da)    # DIN EN 13941-1 D.7
        # ks / ka：symmetrical and (a) antisymmetrical heat loss factors according to zero-order multipole formula
        ks_heating_network = (a + beta + b) ** -1   # DIN EN 13941-1 D.3
        # ka_heating_network = (a + beta - b) ** -1
        pipe["symmetrical heat loss factor"] = ks_heating_network
        # pipe["antisymmetrical heat loss factor"] = ka_heating_network

    # 6 network topology
    # Extract all the branches from the topology (from root node to terminal node)
    network = data.pipeline_topology
    path = extract_longest_branches(network)

    # 7 calcaulate the ann_factor
    # pipe
    pipe_lifetime = heat_grid_data["pipe"]["pipe_lifetime"]["value"]  # 30a,          pipe lifetime (VDI 2067)
    # calculate the Annualization Factor and add to datahandler
    pipe_ann_factor = calc_annual_factor(data, pipe_lifetime)
    data.heat_grid_data["pipe"]["pipe_ann_factor"] = pipe_ann_factor

    # pump
    pump_lifetime = heat_grid_data["pump"]["pump_lifetime"]["value"]  # 10a,          pump lifetime (VDI 2067 Umwälzpumpe)
    # calculate the Annualization Factor and add to datahandler
    pump_ann_factor = calc_annual_factor(data, pump_lifetime)
    data.heat_grid_data["pump"]["pump_ann_factor"] = pump_ann_factor

    # HP
    HP_lifetime = data.central_device_data["AirHP"]["life_time"]      # 25a,          Maximum lifetime. source:
    HP_ann_factor = calc_annual_factor(data, HP_lifetime)

    # prepare parameters for the optimization model
    param = {}
    param["T_s"] = T_s
    param["T_s_cluster"] = T_s_cluster
    param["deltaT"] = deltaT
    param["deltaT_cluster"] = deltaT_cluster
    param["T_return"] = T_return
    param["T_return_cluster"] = T_return_cluster
    param["T_supply"] = T_supply
    param["heat_loss_substation"] = heat_loss_substation
    param["heat_supply"] = heat_supply
    param["pipe_dict"] = pipe_dict
    param["path"] = path
    param["HP_ann_factor"] = HP_ann_factor

    return data, param

def calc_flow(data, param, heat_loss_pipe=None, heat_loss_pipe_cluster=None, save_path=None):
    """
    Calculate the supply and return temperature and the flow rate in each pipe segment

    Parameters
    ----------
    data: class datahandler
    param: dictionary
    heat_loss_pipe

    Returns
    -------
    data: class datahandler
    param: dictionary
        including parameters for diameter optimization
    """
    # 1 load temperatures
    deltaT = param["deltaT"]
    deltaT_cluster = param["deltaT_cluster"]

    # 2 fluids parameters
    c_f = data.heat_grid_data["fluid"]["c_f"]["value"]  # 4180J/(kg*K), fluid specific heat capacity
    rho_f = data.heat_grid_data["fluid"]["rho_f"]["value"]  # 1000kg/m^3,   fluid density

    # 3 load heat demand for each building node
    building_demand_cluster = {}
    building_demand = {}
    h_loss_subst = data.heat_grid_data["h_loss_subst"]["value"]  # 5%, Heat losses at the substation
    # match the coordinate and add data to building_demand
    for building in data.district:
        if building["buildingFeatures"]["heater"] == "heat_grid":
            pos_building = tuple(building["buildingFeatures"]["position"])
            # The heat supplied to the building by the network should include heat losses from the substation.
            demand_cluster = building["user"].heating_demand_cluster * (1 + h_loss_subst / 100) # kW
            demand = building["user"].heating_demand * (1 + h_loss_subst / 100)                 # kW

            # find corresponding pipeline node
            for key, node_info in data.pipeline_nodes.items():
                if tuple(node_info["pos"]) == pos_building:
                    building_demand_cluster[key] = demand_cluster
                    building_demand[key] = demand
                    break  # break once found

    # 4 aggregate the heat load of every pipe segment
    network = data.pipeline_topology
    pipe_loads_cluster = aggregate_heat_loads(network, building_demand_cluster, heat_loss_pipe_cluster, root="EH1")
    pipe_loads = aggregate_heat_loads(network, building_demand, heat_loss_pipe, root="EH1")

    # Iterate through each pipe in pipe_loads_cluster
    for idx, ((parent, child), loads_cluster_array) in enumerate(pipe_loads_cluster.items(), 1):
        # generate pipe id: pipe1, pipe2, ...
        pipe_id = f"pipe{idx}"

        # extract coordinates
        pos_parent = data.pipeline_nodes[parent]["pos"]
        pos_child = data.pipeline_nodes[child]["pos"]

        # convert to numpy array
        p1 = np.array(pos_parent, dtype=float)
        p2 = np.array(pos_child, dtype=float)

        # Euclidean distance
        length = float(np.linalg.norm(p1 - p2)) # m

        # calculate the flow
        # heating_demand_cluster in kW, c_f in J/kg·K, 1kW = 1kJ/s
        # V_dot = Q / (c*ΔT*ρ) in m³/s
        # clustered value (for the optimization)
        flow_cluster_array = loads_cluster_array * 1000 / (c_f * deltaT_cluster * rho_f)  # m³/s
        # year profile (for calculation of max and min permitted pipeline diameter)
        loads_array = pipe_loads[(parent, child)]
        flow_array = loads_array * 1000 / (c_f * deltaT * rho_f)  # m³/s
        # Retrieve the maximum and minimum flow rates, and convert the data type to float.
        flow_max = float(np.max(flow_array[flow_array > 1e-6]))   # m³/s
        flow_min = float(np.min(flow_array[flow_array > 1e-6]))   # m³/s

        # store into data.pipeline
        if pipe_id not in data.pipeline:
            # first time to create a new distionary
            data.pipeline[pipe_id] = {
                "from": parent,  # string, name of start node
                "to": child,  # string, name of end node
                "from_pos": pos_parent,  # tuple, coordinate of start node
                "to_pos": pos_child,  # tuple, coordinate of end node
                "length": length,  # length of the pipe
                "flow_cluster": flow_cluster_array,  # original 2D flow array
                "flow": flow_array,
                "flow_max": flow_max,
                "flow_min": flow_min
            }
        else:
            # dictionary also filled, only update the flow data
            data.pipeline[pipe_id].update({
                "flow_cluster": flow_cluster_array,
                "flow": flow_array,
                "flow_max": flow_max,
                "flow_min": flow_min
            })

    # save results for data validation
    if save_path is not None:
        json_ready = to_jsonable(data.pipeline)
        with open(save_path, "w") as f:
            json.dump(json_ready, f, indent=4)

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
    # total_demand_cluster = param["total_demand_cluster"]
    T_s_cluster = param["T_s_cluster"]
    deltaT_cluster = param["deltaT_cluster"]

    # 3 fluids parameters
    heat_grid_data = data.heat_grid_data
    c_f = heat_grid_data["fluid"]["c_f"]["value"]  # 4180J/(kg*K), fluid specific heat capacity
    rho_f = heat_grid_data["fluid"]["rho_f"]["value"]  # 1000kg/m^3,   fluid density

    # 4 energy hub setup

    # 5 pump parameters
    eta_pump = heat_grid_data["pump"]["eta_pump"]["value"]        # 0.65,         electric pump efficiency

    # constant pressure drops outside the pipe network
    dp_substation = heat_grid_data["pump"].get("dp_substation", {}).get("value", 0.0)  # Pa
    dp_energy_hub = heat_grid_data["pump"].get("dp_energy_hub", {}).get("value", 0.0)  # Pa
    dp_station_total = dp_substation + dp_energy_hub  # Pa

    # total volume flow at energy hub for each cluster/week/time
    # total_demand_cluster in kW, c_f in J/(kg*K), rho_f in kg/m³, deltaT_cluster in K
    # V̇ = Q / (c * ΔT * ρ)
    # Vdot_total_cluster = total_demand_cluster * 1000.0 / (c_f * deltaT_cluster * rho_f)  # m³/s
    # It can also be derived by summing the flow rates at the energy hub node.
    Vdot_total_cluster = None    # m³/s
    for pipe in data.pipeline.values():
        if pipe["from"] == "EH1":
            if Vdot_total_cluster is None:
                # 第一次遇到，就拷贝一份
                Vdot_total_cluster = np.array(pipe["flow_cluster"])
            else:
                Vdot_total_cluster += pipe["flow_cluster"]

    # extra pump power (kW) from substations + energy hub
    # P = V̇ * Δp / (η * 1000)  [kW]
    P_station_cluster = Vdot_total_cluster * dp_station_total / (eta_pump * 1000.0)

    # 6 pipe parameters
    # conv_pipe = heat_grid_data["pipe"]["conv_pipe"]["value"]         # 3600W/(m^2 K), convective heat transfer between flowing fluid and the pipe's inner surface
    # f_fric = heat_grid_data["pipe"]["f_fric"]["value"]               # 0.025,        pipe friction factor
    dp_pipe_max = heat_grid_data["pipe"]["dp_pipe_max"]["value"]     # 500Pa/m,      maximum pipe pressure gradient (300Pa/m in Planungshandbuch Fernwärme)
    dp_pipe_min = heat_grid_data["pipe"]["dp_pipe_min"]["value"]     # 30Pa/m,       minimum pipe pressure gradient (Improved genetic algorithm for pipe diameter optimization of an existing large-scale district heating network https://doi.org/10.1016/j.energy.2024.131970)

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

    # 7 econimic factor
    # 1) pipe
    cost_om_pipe = heat_grid_data["pipe"]["cost_om_pipe"]["value"]       # 0.005         pipe operation and maintenance costs as share of investment (VDI 2067)
    pipe_ann_factor = heat_grid_data["pipe"]["pipe_ann_factor"]     # Annualization Factor


    # 2) pump
    inv_pump = heat_grid_data["pump"]["inv_pump"]["value"]               # 700EUR/kW,    specific investment
    price_el_pumps = data.ecoData["price_supply_el_eh"]    # 0.3141€/kWh,  electricity costs for pump supply used for network design (equals LEC of CHP for 7000 full load hours)
    cost_om_pump = heat_grid_data["pump"]["cost_om_pump"]["value"]       # 0.03          cost share for operation & maintenance
    pump_ann_factor = heat_grid_data["pump"]["pump_ann_factor"]     # Annualization Factor

    # 3) heat loss
    inv_HP = data.central_device_data["AirHP"]["inv_var"]               # 1500€/kW,      source:
    cost_om_HP = data.central_device_data["AirHP"]["cost_om"]           # 0.025,        1/year (fraction of inv_var), source: VDI2067
    HP_ann_factor = param["HP_ann_factor"]

    # Calculate heat pump COPs
    devs_param = {
        "feasible": True,
        "dT_evap": 10,                  # K,    temperature difference in evaporator (how much the air cools down in the evaporator); Source: JENSEN J. et al. Heat pump COP, part 2: generalized COP estimation of heat pump processes
        "dT_cond": deltaT_cluster,      # K,    temperature difference in condenser (how much network's fluid heats up in the condenser)
        "dT_pinch_cond": 2,             # K,    temperature difference between both fluids in the condenser at pinch point; Source: Klingebiel et al. https://doi.org/10.1016/j.enbuild.2023.113397
        "dT_pinch_evap": 5,             # K,    temperature difference between both fluids in the evaporator at pinch point
        "eta_compr": 0.8,               # ---,  isentropic efficiency of compression; Source: Wirtz et al. https://doi.org/10.1016/j.apenergy.2019.114158
        "heatloss_compr": 0.3,          # ---,  heat loss rate of compression; # Source: JENSEN J. et al. Heat pump COP, part 2: generalized COP estimation of heat pump processes
        "COP_max": 7,                   # ---,  maximum heat pump COP
    }
    # Temperatures
    t_c_in = data.site["T_e_cluster"] + 273.15   # heat source inlet (Air)
    dt_c = devs_param["dT_evap"]                 # heat source temperature difference
    t_h_in = param["T_return_cluster"] + 273.15  # heat sink (Network fluid) inlet temperature
    dt_h = devs_param["dT_cond"]
    # call the calculation function
    COP_HP = calc_COP(devs_param, [t_c_in, dt_c, t_h_in, dt_h])

    # calculate the price for co2 of the electrity from grid
    p_co2 = data.params_ehdo_model["co2_tax"]                           # 0,            carbon pricing (0.055€/kg in Germany in 2025 from website https://carbonpricingdashboard.worldbank.org/compliance/price)
    EF = data.ecoData["co2_el_grid"]                                    # 0.363kg/kWh,  CO2 emissions for electricity import (grid mix)

    # calculate the total unit cost of producing heat of AirHP
    heat_loss_prefac = (price_el_pumps + p_co2 * EF) / COP_HP           # €/kWh,  total unit cost of producing heat to cover network heat losses.

    # 8 get possible norm diameter options for each pipe segment
    pipe_dict = param["pipe_dict"]
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
    k_soil = heat_grid_data["k_soil"]["value"]  # 1.52 W/(m*K),     Soil thermal conductivity, corresponding to λ_s in EN 13941

    # 10 network topology
    # Extract all the branches from the topology (from root node to terminal node)
    path = param["path"]

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

    # Also define a set of devices for investments (pipes,pumps,HP) to hold inv / tac
    invest_devs = ["pipes", "pumps", "HP"]
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

    # Additional heat pump capacity (kW) required to compensate network heat losses
    model.HP_cap = pyo.Var(within=pyo.NonNegativeReals, initialize=0.0, doc="Additional heat pump capacity (kW) to cover heat losses")

    # total annual heat loss (kWh) and energy cost
    model.heat_loss_total = pyo.Var(within=pyo.NonNegativeReals, initialize=0.0, doc="Total annual heat loss (kWh)")
    model.heat_loss_energy_cost = pyo.Var(within=pyo.NonNegativeReals, initialize=0.0, doc="Total annual heat loss energy cost (EUR)")

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

    # linear method
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

    # 7) Additional heat pump capacity must be >= heat loss at each pipe/week/t
    def heatpump_capacity_rule(model, week, t):
        return pyo.quicksum(model.heat_loss_pipe[pipe, week, t] for pipe in model.pipe) <= model.HP_cap

    model.heat_pump_capacity_constr = pyo.Constraint(model.week, model.t, rule=heatpump_capacity_rule,
                                                  doc="Additional heat pump capacity must cover total pipe heat losses")

    # 8) Total heat loss in a year (sum over pipes, weeks, time weighted by cluster weights)
    def total_heat_loss_rule(model):
        return model.heat_loss_total == pyo.quicksum(
            pyo.quicksum(model.heat_loss_pipe[pipe, week, t] for t in model.t) * data.clusterWeights[week]
            for pipe in model.pipe for week in model.week
        )

    model.total_heat_loss_constr = pyo.Constraint(rule=total_heat_loss_rule,
                                                  doc="Total annual heat loss (kWh)")

    # %% STEP FIVE: define the objective function
    # 1) Investment and TAC calculations for the *additional* heat pump capacity
    def inv_heatpump_rule(model):
        return model.inv["HP"] == model.HP_cap * inv_HP

    model.inv_heatpump_constr = pyo.Constraint(rule=inv_heatpump_rule,
                                             doc="Boiler investment = capacity * unit cost")

    def tac_heatpump_rule(model):
        return model.tac["HP"] == model.inv["HP"] * (HP_ann_factor + cost_om_HP)

    model.tac_heatpump_constr = pyo.Constraint(rule=tac_heatpump_rule, doc="TAC for additional heatpump capacity")

    def heatpump_energy_cost_rule(model):
        return model.heat_loss_energy_cost == pyo.quicksum(
            model.heat_loss_pipe[pipe, week, t] *
            heat_loss_prefac[week_to_i[week], t] *
            data.clusterWeights[week]
            for pipe in model.pipe
            for week in model.week
            for t in model.t
        )

    model.heat_pump_energy_cost_constr = pyo.Constraint(rule=heatpump_energy_cost_rule,
                                                  doc="Additional heat pump energy cost for covering total pipe heat losses")

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
        # tac_network == tac_pipes + tac_pumps + tac_HP + pump_energy_total*price_el_pumps + heat_loss_total*heat_loss_prefac
        return model.tac_network == (model.tac["pipes"] + model.tac["pumps"] + model.tac["HP"]
                                     + model.pump_energy_total * price_el_pumps
                                     + model.heat_loss_energy_cost)

    model.tac_network_constr = pyo.Constraint(rule=tac_network_rule,
                                              doc="Link tac_network to components")

    # Objective: minimize tac_network
    model.objective = pyo.Objective(expr=model.tac_network, sense=pyo.minimize,
                              doc="Minimize total annualized network cost")

    print("Pyomo model built successfully")

    # %% STEP SIX: solve the model and output
    # Folder to save model and results
    dir_result = param["dir_result"]

    lp_filename = os.path.join(dir_result, "opti_pipe_diameter_model.lp")
    model.write(lp_filename, io_options={'symbolic_solver_labels': True})

    # temporary log-file for the solver
    solver_log_path = os.path.join(dir_result, "solver_output.log")

    # Solve the model
    solver, solver_options = solver_config.create_solver()

    solver_options["primal_feasibility_tolerance"] = 1e-9
    solver_options["mip_feasibility_tolerance"] = 1e-9

    results = solver.solve(model, tee=True, options=solver_options)

    # get the optimized diameter for each pipe segment
    pipe_candidates = param["pipe_candidates"]
    for pipe in data.pipeline.keys():
        for d in pipe_candidates[pipe]:
            if pyo.value(model.z[pipe, d]) > 0.5:
                data.pipeline[pipe]["DN"] = d
                break  # Once the selected pipe diameter is found, exit the loop.

    return data, model, param

def calc_diameter(data, param, f_fric):
    """
    Calculate the diameter of each pipeline segments based on the maximum permitted pressure drop.

    The method for calculating pressure drop is based on a Darcy–Weisbach-derived formulation.

    Parameters
    ----------
    data: class datahandler
    f_fric: float
        friction factor of pipeline, Iteration parameter

    Returns
    -------
    data: class datahandler
    """
    # load fluids parameters
    heat_grid_data = data.heat_grid_data
    rho_f = heat_grid_data["fluid"]["rho_f"]["value"]  # 1000kg/m^3,   fluid density

    # load feasible pipe pressure gradient range
    dp_pipe_max = 300     # 300Pa/m,      maximum pipe pressure gradient (Planungshandbuch Fernwärme)
    dp_pipe_min = heat_grid_data["pipe"]["dp_pipe_min"]["value"]     # 30Pa/m,       minimum pipe pressure gradient (Improved genetic algorithm for pipe diameter optimization of an existing large-scale district heating network https://doi.org/10.1016/j.energy.2024.131970)

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

    # load norm diameter
    pipe_dict = param["pipe_dict"]

    # get possible norm diameter options for each pipe segment
    for pipe_id, pipe in data.pipeline.items():
        d_min = pipe["d_min"]
        d_max = pipe["d_max"]

        # find all feasible DN
        candidates = [
            DN for DN, vals in pipe_dict.items()
            if vals["Inner diameter (pipe) (mm)"] >= d_min and vals["Inner diameter (pipe) (mm)"] <= d_max
        ]

        if candidates:
            # select the smallest diameter
            best_DN = min(
                candidates,
                key=lambda DN: pipe_dict[DN]["Inner diameter (pipe) (mm)"]
            )
            pipe["DN"] = best_DN

    return data, param

def calc_heat_loss_pipe(data, param):
    pipe_dict = param["pipe_dict"]

    # calculate heat loss in network
    T_s = param["T_s"]
    T_soil = data.heat_grid_data["T_soil"]
    k_soil = data.heat_grid_data["k_soil"]["value"]

    heat_loss_pipe = {}
    heat_loss_pipe_cluster = {}
    for pipe_id, pipe in data.pipeline.items():
        DN = pipe["DN"]  # mm
        ks = pipe_dict[DN]["symmetrical heat loss factor"]
        length = pipe["length"] # m

        # *2: The first factor of two accounts for the heat loss of both the supply and return pipes.
        # *2: The second factor of two is in the equation of calculating q_s from DIN EN 13941.
        pipe["heat_loss_pipe"] = 2 * (T_s - T_soil) * 2 * np.pi * k_soil * ks * length / 1000  # kW, DIN EN 13941-1 D.11

        # prepare heat_loss_pipe for recalculate the flow
        # shape like: key = (parent, child), value = ndarray of heat loss on this pipe.
        parent = pipe["from"]
        child = pipe["to"]
        heat_loss_pipe[(parent, child)] = pipe["heat_loss_pipe"]

        # get cluster array
        # list of clustered typical weeks
        weeks = data.clusters
        # how many timesteps are there in a typical week
        time_steps = int(data.time["clusterLength"] / data.time["timeResolution"])

        cluster_array = np.zeros((len(weeks), time_steps))
        for i, week_id in enumerate(weeks):
            # find the start and end timestep of the week in the yearly profile
            start = week_id * time_steps
            end = start + time_steps
            cluster_array[i, :] = pipe["heat_loss_pipe"][start:end]
        heat_loss_pipe_cluster[(parent, child)] = cluster_array

    return data, heat_loss_pipe, heat_loss_pipe_cluster

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

def output_diameter(data, param):
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
    dir_result = param["dir_result"]

    # calculate heat loss
    # save heat loss(yearly profile) in data.heat_grid_data["total_losses_heating_network"]
    # load heat loss in substation
    heat_loss_substation = param["heat_loss_substation"]

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

    # calculate and save total heat loss
    heat_loss_total = heat_loss_substation + heat_loss_network
    data.heat_grid_data["total_losses_heating_network"] = heat_loss_total
    annual_heat_loss = np.sum(heat_loss_total)                      # kWh
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

    plt.show()

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
    c_f = data.heat_grid_data["fluid"]["c_f"]["value"]  # 4180J/(kg*K), fluid specific heat capacity
    rho_f = data.heat_grid_data["fluid"]["rho_f"]["value"]  # 1000kg/m^3,   fluid density
    pipe_dict = param["pipe_dict"]
    f_fric = param["f_fric"]
    for pipe_id, pipe in data.pipeline.items():
        flow_max = pipe["flow_max"]  # m3/s
        DN = pipe["DN"]  # mm
        d_i = pipe_dict[DN]["Inner diameter (pipe) (mm)"]  # mm
        pipe["d_i"] = d_i
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
                max_heat_loss_density - min_heat_loss_density)  # range: 1-5
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

    plt.show()

    # ---------- 7. save pump power(yearly profile) ----------
    # save pump power(yearly profile) in data.heat_grid_data["pump_power"]
    f_fric = param["f_fric"]
    eta_pump = data.heat_grid_data["pump"]["eta_pump"]["value"]  # 0.65,         electric pump efficiency
    prefac = (8 * f_fric) / (rho_f ** 2 * np.pi ** 2 * eta_pump) / 1000

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

    save_path = os.path.join(dir_result, "local_hydraulic_loss_data.json")
    with open(save_path, "w") as f:
        json.dump(export_data, f, indent=4)

    pump_power_pipe = {}
    for pipe_id, pipe in data.pipeline.items():
        DN = pipe["DN"]  # mm
        d_i = pipe_dict[DN]["Inner diameter (pipe) (mm)"]  # mm
        length = pipe["length"]  # m
        flow = pipe["flow"]  # m3/s
        # pump power to cover friction loss
        # *2: The first factor of two accounts for the pump power of both the supply and return pipes.
        # *1.2: The factor of 1.2 accounts for an additional 20% of local losses.(source: Planungshandbuch Fernwärme)
        pump_power_friction = prefac * length * 2 * ((flow * rho_f) ** 3) / ((d_i / 1000) ** 5)  # kW

        # pump power to cover local loss
        velocity = flow / (np.pi * (d_i / 1000) ** 2 / 4)  # m/s
        zeta = pipe["zeta"]
        local_pressure_drop = rho_f * zeta * velocity**2 / 2  # Pa
        pump_power_local = local_pressure_drop * flow / (eta_pump * 1000.0)  # kW

        # total pump power for this pipe segment
        pump_power_pipe[pipe_id] = pump_power_friction + pump_power_local  # kW

    # Build mapping from oriented node pair to pipe id (assume unique per pair)
    pair_to_pid = {}
    for pid, info in data.pipeline.items():
        pair_to_pid[(info["from"], info["to"])] = pid

    path = param["path"]
    pump_power_line = {}
    for line, nodes in path.items():
        # Initialize pump power array for this line
        pump = np.zeros_like(heat_loss_substation)
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

    # Final pump power: (pipe friction + local pressure loss) from worst line + station/hub component
    pump_power = np.max(pump_matrix, axis=0) + P_station_profile

    data.heat_grid_data["pump_power"] = pump_power
    # print("Total pump power in network calculation finished successfully.")

    # ---------- 8. save cost ----------
    # cost of substation
    buildings_connected = [b for b in data.district if b["buildingFeatures"]["heater"] == "heat_grid"]
    C_substations = 0
    for building in buildings_connected:
        substation_capacity = building["envelope"].heatload/1000 + building["dhwpower"]/1000  #kW
        substation_costs = substation_capacity * data.heat_grid_data["C_subst"]["value"]
        C_substations += substation_costs
    substation_lifetime = data.heat_grid_data["lifetime_subst"]["value"]
    substation_ann_factor = calc_annual_factor(data, substation_lifetime)
    substation_ann_costs = C_substations * substation_ann_factor
    substation_om_costs = len(buildings_connected) * data.heat_grid_data["cost_om_subst"]["value"]
    # print(f"Substations annualized cost: {substation_ann_costs:.2f} €")
    # print(f"Substations O&M cost per year: {substation_om_costs:.2f} €")

    # cost of pipes
    inv_pipes = 0
    inv_construction = 0
    for pipe in data.pipeline.keys():
        # load diameters for each pipe
        DN = data.pipeline[pipe]["DN"]
        inv_pipes += DN * param["pipe_dict"][DN]["Pipe Cost (€/m)"] * 2     # *2 for supply and return
        inv_construction += DN * param["pipe_dict"][DN]["Construction Cost (€/m)"]
    # calculate the cost for the pipes
    pipe_ann_factor = data.heat_grid_data["pipe"]["pipe_ann_factor"]
    pipes_ann_costs = (inv_pipes + inv_construction) * pipe_ann_factor
    pipes_om_costs = inv_pipes * data.heat_grid_data["pipe"]["cost_om_pipe"]["value"]
    # print(f"Pipes annualized cost: {pipes_ann_costs:.2f} €")
    # print(f"Pipes O&M cost per year: {pipes_om_costs:.2f} €")

    # calculate the capacity of the pump
    pump_cap = np.max(pump_power)   # kW
    # print(f"The capacity of the pump should be bigger than {pump_cap:5f}kW.")

    # calculate the investment for the pump
    inv_pump = pump_cap * data.heat_grid_data["pump"]["inv_pump"]["value"]

    # cost of pump
    pump_ann_costs = inv_pump * data.heat_grid_data["pump"]["pump_ann_factor"]
    pump_om_costs = inv_pump * data.heat_grid_data["pump"]["cost_om_pump"]["value"]
    # print(f"Pump annualized cost: {pump_ann_costs:.2f} €")
    # print(f"Pump O&M cost per year: {pump_om_costs:.2f} €")

    # cost of electricity
    pump_energy_total = np.sum(pump_power)  # kWh
    # print(f"The total electricity consumption for the pump is {pump_energy_total:5f}kWh/a.")
    pump_electricity_costs = pump_energy_total * data.ecoData["price_supply_el_eh"]

    # calculate the total cost
    network_om_costs = pipes_om_costs + pump_om_costs + substation_om_costs
    network_ann_costs = pipes_ann_costs + pump_ann_costs + pump_electricity_costs + substation_ann_costs
    data.heat_grid_data["om_costs"] = network_om_costs
    data.heat_grid_data["ann_costs"] = network_ann_costs

    # get cost of heat loss
    # calculate capacity
    cap_HP = np.max(heat_loss_total)
    # calculate investment, o&m cost and electricity cost
    HP_inv_costs = cap_HP * data.central_device_data["AirHP"]["inv_var"]
    HP_ann_costs = HP_inv_costs * param["HP_ann_factor"]
    HP_om_costs = HP_inv_costs * data.central_device_data["AirHP"]["cost_om"]
    # calculate yearly COP profile and the eletricity cost for the HP
    devs_param = {
        "feasible": True,
        "dT_evap": 10,      # K,    temperature difference in evaporator (how much the air cools down in the evaporator); Source: JENSEN J. et al. Heat pump COP, part 2: generalized COP estimation of heat pump processes
        "dT_cond": deltaT,  # K,    temperature difference in condenser (how much network's fluid heats up in the condenser)
        "dT_pinch_cond": 2, # K,    temperature difference between both fluids in the condenser at pinch point; Source: Klingebiel et al. https://doi.org/10.1016/j.enbuild.2023.113397
        "dT_pinch_evap": 5, # K,    temperature difference between both fluids in the evaporator at pinch point
        "eta_compr": 0.8,   # ---,  isentropic efficiency of compression; Source: Wirtz et al. https://doi.org/10.1016/j.apenergy.2019.114158
        "heatloss_compr": 0.3, # ---,  heat loss rate of compression; # Source: JENSEN J. et al. Heat pump COP, part 2: generalized COP estimation of heat pump processes
        "COP_max": 7,       # ---,  maximum heat pump COP
    }
    # Temperatures
    t_c_in = data.site["T_e"] + 273.15  # heat source inlet (Air)
    dt_c = devs_param["dT_evap"]  # heat source temperature difference
    t_h_in = param["T_return"] + 273.15  # heat sink (Network fluid) inlet temperature
    dt_h = devs_param["dT_cond"]
    # call the calculation function
    COP_HP = calc_COP(devs_param, [t_c_in, dt_c, t_h_in, dt_h])
    HP_electricity_costs = np.sum(heat_loss_total / COP_HP) * data.ecoData["price_supply_el_eh"]

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
        "Electricity costs for the heatpump": HP_electricity_costs
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

    base = os.path.join(dir_result, f"network_cost_stack_{data.scenario_name}")
    plt.savefig(base + ".png")  # PNG
    plt.savefig(base + ".svg")  # SVG
    print("Cost stacked plot of heat grid saved to:", base)

    plt.show()

    # ---------- 10. save parameters, energy-consumption and costs to a json-file ----------
    # output average temperatures for validation of the heat loss
    T_soil = data.heat_grid_data["T_soil"]
    T_soil_mean = np.mean(T_soil)
    T_s_mean = np.mean(T_s)
    T_supply = param["T_supply"]
    T_supply_mean = np.mean(T_supply)

    # output heat supply for validation of the percentage of pump electricity and heat loss
    heat_supply = param["heat_supply"]  # kW
    total_heat_supply = np.sum(heat_supply) # kWh

    results = {
        "f_fric": {
            "value": float(f_fric),
            "unit": "-",
            "description": "Darcy friction factor used in the hydraulic calculation"
        },
        "T_soil_mean": {
            "value": float(T_soil_mean),
            "unit": "°C",
            "description": "The annual average temperature of soil"
        },
        "T_s_mean": {
            "value": float(T_s_mean),
            "unit": "°C",
            "description": "The annual average of the midpoint temperature between supply and return"
        },
        "T_supply_mean": {
            "value": float(T_supply_mean),
            "unit": "°C",
            "description": "The annual average supply temperature"
        },
        "total_pipe_length": {
            "value": float(total_pipe_length),
            "unit": "m",
            "description": "Sum of all pipe segments in the network"
        },
        "total_heat_supply": {
            "value": float(total_heat_supply),
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
            "value": float(pump_energy_total / total_heat_supply * 100),
            "unit": "%",
            "description": "Pump total annual electricity consumption as a percentage of network heat supply"
        },
        "annual_heat_loss": {
            "value": float(annual_heat_loss),
            "unit": "kWh",
            "description": "Annual heat loss (including pipelines and substations)"
        },
        "heat_loss_density": {
            "value": float(annual_heat_loss_network * 1000 / 8760 / total_pipe_length),
            "unit": "W/m",
            "description": "Heat loss density (only including pipelines)"
        },
        "heat_loss_percentage": {
            "value": float(annual_heat_loss / total_heat_supply * 100),
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

    json_path = os.path.join(dir_result, "heat_grid_parameters_outputs.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, ensure_ascii=False)

    print("Output JSON-file saved to::", json_path)

    return data

def calc_f_fric(data, param):
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
    pipe_dict = param["pipe_dict"]
    nu_f = data.heat_grid_data["fluid"]["nu_f"]["value"]    # m2/s

    for pid, pipe in data.pipeline.items():
        flow_max = pipe["flow_max"]  # m3/s
        DN = pipe["DN"]  # mm
        d_i = pipe_dict[DN]["Inner diameter (pipe) (mm)"]  # mm
        k = pipe_dict[DN]["Roughness (mm)"]  # mm

        # calculate the maximum velocity
        v_max = flow_max / (np.pi * (d_i / 1000) ** 2 / 4)  # m/s
        # calculate the Reynolds number
        Re = v_max * (d_i / 1000) / nu_f

        # f_fric is calculated by friction_factor() using the default Clamond method for turbulent flow.
        pipe["f_fric"] = fluids.friction.friction_factor(Re=Re, eD=k/d_i)

    f_fric = sum(data.pipeline[pipe]["f_fric"] for pipe in data.pipeline.keys())/len(data.pipeline.keys())

    return f_fric

def identify_junction_and_bends(data, tol=1e-6):
    """
    Identify pipe junction type , bends, and diameter changes.
    Calculate the turning angle at downstream pipe.

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
    node_type = {}              # "source" or "end" or "straight" or "bend" or "tee" or "cross"
    pipe_angle = {}             # save the angle between the incoming and outgoing pipe (pipe_angle[downstream_pipe]=angle)
    diameter_change = {}        # whether the downstream pipeline has a diameter change (diameter_change[downstream_pipe]=True/False)

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
            else:   # deg == 4
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
    Compute ζ (local resistance) for each pipe based on:
    - bends
    - tees / crosses
    - diameter changes
    all parameters from Book Technische Strömungslehre

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

    for pid, pipe in pipes.items():
        node = pipe["from"]  # ζ defined at outgoing pipe
        ntype = node_type[node]
        f_fric = param["f_fric"]
        d = pipes[pid]["d_i"]       # mm
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
            R = pipe_dict[DN]["Radius (mm)"]   # mm
            K1 = -0.000041 * ang**2 + 0.0146 * ang + 0.05      # Bild 4.140 (Polynomial Fitting)
            K2 = 0.21 / (R/d) ** 0.5                           # Bild 4.141 (for sharp bend) / 4.143 (for smooth bend)
            K3 = 1                                      # (h=b for round tube) Bild 4.142 (for sharp bend) / 4.144 (for smooth bend)
            zeta_U = K1 * K2 * K3                       # Gl. 4.184b
            zeta_R = 0.0175 * f_fric * R/d * ang        # Gl. 4.185a
            zeta_total = 2 * (zeta_U + zeta_R)          # *2 for supply and return

        # ----------------------------
        # 3) Tee or Cross junction
        # ----------------------------
        elif ntype in ("tee", "cross"):
            # the supply zeta is for the Vertrennung, and the return zeta is for the Vereinigung
            # child angle at this node
            ang = pipe_angle.get(pid, 0.0)

            pid_up = incoming_pipes[node][0]
            flow_child = sum(pipe["flow"])
            flow_up = sum(pipes[pid_up]["flow"])
            flow_ratio = np.clip(flow_child / flow_up, 0, 1)

            if ang is None:
                zeta_total = 0.0
            else:
                # branch vs run direction
                if ang > angle_branch_threshold:
                    # branch line

                    # prepare the zeta value for certain flow ratio at three typical angles 45°, 60°, 90°
                    zeta_45_supply = 1.018 * flow_ratio ** 2 - 1.482 * flow_ratio + 0.933    # Bild 4.150 (Polynomial Fitting)
                    zeta_60_supply = 1.098 * flow_ratio ** 2 - 1.334 * flow_ratio + 1        # Bild 4.150 (Polynomial Fitting)
                    zeta_90_supply = 0.920 * flow_ratio ** 2 - 0.611 * flow_ratio + 0.995    # Bild 4.150 (Polynomial Fitting)
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
                    zeta_45_return = - 1.852 * flow_ratio ** 2 + 1.118 * flow_ratio - 0.056  # Bild 4.150 (Polynomial Fitting)
                    zeta_60_return = - 1.250 * flow_ratio ** 2 + 0.911 * flow_ratio + 0.144  # Bild 4.150 (Polynomial Fitting)
                    zeta_90_return = 0.031 * flow_ratio ** 2 + 0.486 * flow_ratio + 0.079    # Bild 4.150 (Polynomial Fitting)

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
                kontraktionszahl = 0.49 * area_ratio ** 2 - 0.12 * area_ratio + 0.624           # Bild 4.128 (Polynomial Fitting)
                zeta_dia_change_supply = 1.5 * ((1-kontraktionszahl)/kontraktionszahl) ** 2     # Gl. 4.179
                # pipe expansion in return pipes
                zeta_dia_change_return = (1 - (d_child / d_up) ** 2) ** 2                       # Tabelle 4.19 Bezug auf Eintrittsquerschnitt
            elif d_up < d_child:
                # pipe expansion in supply pipes
                zeta_dia_change_supply = ((d_child / d_up) ** 2 - 1) ** 2                       # Tabelle 4.19 Bezug auf Austrittsquerschnitt
                # pipe contraction in return pipes
                area_ratio = (d_up / d_child) ** 2
                kontraktionszahl = 0.49 * area_ratio ** 2 - 0.12 * area_ratio + 0.624           # Bild 4.128 (Polynomial Fitting)
                zeta_dia_change_up = 1.5 * ((1-1/kontraktionszahl) * kontraktionszahl) ** 2     # Gl. 4.179
                factor = (pipes[pid_up]["velocity_max"] / pipes[pid]["velocity_max"]) ** 2
                zeta_dia_change_return = zeta_dia_change_up * factor

            zeta_dia_change = zeta_dia_change_supply + zeta_dia_change_return
            zeta_total += zeta_dia_change

        # store back to result
        zeta[pid] = zeta_total
        data.pipeline[pid]["zeta"] = zeta_total

    return data, zeta
