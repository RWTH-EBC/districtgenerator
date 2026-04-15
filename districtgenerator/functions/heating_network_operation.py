# -*- coding: utf-8 -*-

import numpy as np
import math
import os
import json
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import fluids
import textwrap
from tqdm import tqdm

def network_operation(data, param):

    # 1. Solve network temperatures
    data, param = compute_network_temperatures(data, param)

    # 2. Calculate pipe heat losses
    data, param = calc_heat_loss_pipe(data, param)

    # 3. Plot network results
    plot_network_results(data, param)

    # 4. Compute network costs
    compute_and_save_network_costs(data, param)

    return data

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

def to_jsonable(obj):
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, tuple):
        return list(obj)
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    return obj
