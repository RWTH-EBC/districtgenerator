# -*- coding: utf-8 -*-
"""
4-Element (10-node) dynamic zone solver.

Elements:
    External Wall (ew), Roof (r), Floor (f), Internal Wall (iw).
Nodes:
    Air, Radiative Star (rad),
    T_s_ew, T_m_ew, T_s_r, T_m_r, T_s_f, T_m_f, T_s_iw, T_m_iw.
"""

from typing import Dict, Optional, Tuple
import numpy as np


def _build_setpoints_arrays(envelope, n, dt_h, building_type, night_setback, holidays, initial_day: int = 0):
    """Generates setpoint arrays honoring schedules, holidays, and night setbacks."""
    dt_s = dt_h * 3600.0
    steps_per_day = int(round(86400.0 / dt_s))
    T_heat = np.full(n, float(envelope.T_set_min), dtype=float)
    T_cool = np.full(n, float(envelope.T_set_max), dtype=float)

    if building_type in {"SFH", "TH", "MFH", "AB"}:
        if night_setback:
            for t in range(n):
                hod = (t % steps_per_day) * dt_s / 3600.0
                if hod >= 22 or hod < 6:
                    T_heat[t] = float(getattr(envelope, "T_set_min_night", envelope.T_set_min - 3.0))
                    T_cool[t] = float(getattr(envelope, "T_set_max_night", envelope.T_set_max + 1.0))
    else:
        holidays = set(holidays or [])
        for t in range(n):
            day = t // steps_per_day
            hod = (t % steps_per_day) * dt_s / 3600.0
            weekday = (int(initial_day) + int(day)) % 7
            is_weekend = (weekday in (5, 6))
            is_holiday = (day in holidays)
            working_day = (not is_weekend) and (not is_holiday)

            if hod >= 18 or hod < 6:
                T_heat[t] = float(getattr(envelope, "T_set_min_night", envelope.T_set_min - 3.0)) if working_day \
                    else float(getattr(envelope, "T_set_min_free_day", envelope.T_set_min - 3.0))
                T_cool[t] = float(getattr(envelope, "T_set_max_night", envelope.T_set_max + 1.0))
            else:
                T_heat[t] = float(envelope.T_set_min) if working_day \
                    else float(getattr(envelope, "T_set_min_free_day", envelope.T_set_min))
                T_cool[t] = float(envelope.T_set_max) if working_day else 100.0

    return T_heat, T_cool


def _extract_element_params(envelope, dt_s: float) -> Dict[str, float]:
    """
    Extracts capacities (C), surface resistances (R1), residual resistances (Rrest),
    convective conductances (G_conv), and radiative conductances (G_rad) for the 4 elements.
    """
    H_ve = float(envelope.rho_air) * float(envelope.c_p_air) * float(envelope.ventilationRate) * float(
        envelope.V) / 3600.0
    C_air = float(envelope.rho_air) * float(envelope.c_p_air) * float(envelope.V)

    # Helper to safely extract parameters or apply defaults
    def _safe_get(attr, default=1e-5):
        if not hasattr(envelope, attr):
            print(f"Attribute {attr} not found in envelope object.")
        return float(getattr(envelope, attr, default))

    return {
        "dt": float(dt_s),
        "C_air": C_air,
        "H_ve": H_ve,

        # External Wall
        "C_ew": _safe_get("C_ew"),
        "G_1_ew": 1.0 / _safe_get("R1_ew", 1e15),
        "G_rest_ew": 1.0 / _safe_get("Rrest_ew", 1e15),
        "G_conv_ew": _safe_get("h_conv_ew", 2.7) * _safe_get("A_ew", 0.0),
        "G_rad_ew": _safe_get("h_rad_ew", 5.0) * _safe_get("A_ew", 0.0),

        # Roof
        "C_r": _safe_get("C_r"),
        "G_1_r": 1.0 / _safe_get("R1_r", 1e15),
        "G_rest_r": 1.0 / _safe_get("Rrest_r", 1e15),
        "G_conv_r": _safe_get("h_conv_r", 2.7) * _safe_get("A_r", 0.0),
        "G_rad_r": _safe_get("h_rad_r", 5.0) * _safe_get("A_r", 0.0),

        # Floor
        "C_f": _safe_get("C_f"),
        "G_1_f": 1.0 / _safe_get("R1_f", 1e15),
        "G_rest_f": 1.0 / _safe_get("Rrest_f", 1e15),
        "G_conv_f": _safe_get("h_conv_f", 2.7) * _safe_get("A_f", 0.0),
        "G_rad_f": _safe_get("h_rad_f", 5.0) * _safe_get("A_f", 0.0),

        # Internal Wall
        "C_iw": _safe_get("C_iw"),
        "G_1_iw": 1.0 / _safe_get("R1_iw", 1e15),
        "G_rest_iw": 1.0 / _safe_get("Rrest_iw", 1e15),  # Often 0 for adiabatic
        "G_conv_iw": _safe_get("h_conv_iw", 2.7) * _safe_get("A_iw", 0.0),
        "G_rad_iw": _safe_get("h_rad_iw", 5.0) * _safe_get("A_iw", 0.0),
    }


def _step10_free_float(params, state10, bnd_t, gains_t):
    """
    10x10 Matrix solving for [T_air, T_rad, T_s_ew, T_m_ew, T_s_r, T_m_r, T_s_f, T_m_f, T_s_iw, T_m_iw].
    """
    dt = params["dt"]
    A = np.zeros((10, 10))
    b = np.zeros(10)

    T_air_p, T_rad_p, T_s_ew_p, T_m_ew_p, T_s_r_p, T_m_r_p, T_s_f_p, T_m_f_p, T_s_iw_p, T_m_iw_p = state10

    # 0. Air Node
    A[0, 0] = params["C_air"] / dt + params["G_conv_ew"] + params["G_conv_r"] + params["G_conv_f"] + params[
        "G_conv_iw"] + params["H_ve"]
    A[0, 2] = -params["G_conv_ew"]
    A[0, 4] = -params["G_conv_r"]
    A[0, 6] = -params["G_conv_f"]
    A[0, 8] = -params["G_conv_iw"]
    b[0] = (params["C_air"] / dt) * T_air_p + gains_t["Q_kon"] + params["H_ve"] * bnd_t["T_ext"]

    # 1. Radiative Star Node
    A[1, 1] = params["G_rad_ew"] + params["G_rad_r"] + params["G_rad_f"] + params["G_rad_iw"]
    A[1, 2] = -params["G_rad_ew"]
    A[1, 4] = -params["G_rad_r"]
    A[1, 6] = -params["G_rad_f"]
    A[1, 8] = -params["G_rad_iw"]
    b[1] = gains_t["Q_rad"]

    # --- Element Mappings ---
    elements = [
        (2, "ew", bnd_t["theta_eq_ew"]),
        (4, "r", bnd_t["theta_eq_r"]),
        (6, "f", bnd_t["T_ground"]),
        (8, "iw", bnd_t["T_ext"])  # Assuming adiabatic if G_rest_iw is ~0
    ]

    for idx, (s_idx, prefix, boundary_temp) in enumerate(elements):
        m_idx = s_idx + 1
        T_m_prev = state10[m_idx]

        # Surface Node
        A[s_idx, 0] = -params[f"G_conv_{prefix}"]
        A[s_idx, 1] = -params[f"G_rad_{prefix}"]
        A[s_idx, s_idx] = params[f"G_conv_{prefix}"] + params[f"G_rad_{prefix}"] + params[f"G_1_{prefix}"]
        A[s_idx, m_idx] = -params[f"G_1_{prefix}"]
        b[s_idx] = gains_t.get(f"Q_sol_{prefix}", 0.0)

        # Mass Node
        A[m_idx, s_idx] = -params[f"G_1_{prefix}"]
        A[m_idx, m_idx] = params[f"C_{prefix}"] / dt + params[f"G_1_{prefix}"] + params[f"G_rest_{prefix}"]
        b[m_idx] = (params[f"C_{prefix}"] / dt) * T_m_prev + params[f"G_rest_{prefix}"] * boundary_temp

    # Regularize thermal nodes to prevent Singular Matrix for missing building elements
    A[np.arange(10), np.arange(10)] += 1e-6

    return np.linalg.solve(A, b)


def _step11_with_setpoint(params, state10, bnd_t, gains_t, T_set, w_op, sigma, Q_limit, Q_limit_cool):
    """
    11x11 Matrix solving for states + Q_HC to maintain Operative Temperature.
    """
    dt = params["dt"]
    A = np.zeros((11, 11))
    b = np.zeros(11)

    T_air_p, T_rad_p, T_s_ew_p, T_m_ew_p, T_s_r_p, T_m_r_p, T_s_f_p, T_m_f_p, T_s_iw_p, T_m_iw_p = state10

    # 0. Air Node
    A[0, 0] = params["C_air"] / dt + params["G_conv_ew"] + params["G_conv_r"] + params["G_conv_f"] + params[
        "G_conv_iw"] + params["H_ve"]
    A[0, 2] = -params["G_conv_ew"]
    A[0, 4] = -params["G_conv_r"]
    A[0, 6] = -params["G_conv_f"]
    A[0, 8] = -params["G_conv_iw"]
    A[0, 10] = -sigma[1]
    b[0] = (params["C_air"] / dt) * T_air_p + gains_t["Q_kon"] + params["H_ve"] * bnd_t["T_ext"]

    # 1. Radiative Star Node
    A[1, 1] = params["G_rad_ew"] + params["G_rad_r"] + params["G_rad_f"] + params["G_rad_iw"]
    A[1, 2] = -params["G_rad_ew"]
    A[1, 4] = -params["G_rad_r"]
    A[1, 6] = -params["G_rad_f"]
    A[1, 8] = -params["G_rad_iw"]
    A[1, 10] = -sigma[0]
    b[1] = gains_t["Q_rad"]

    # --- Element Mappings ---
    elements = [
        (2, "ew", bnd_t["theta_eq_ew"]),
        (4, "r", bnd_t["theta_eq_r"]),
        (6, "f", bnd_t["T_ground"]),
        (8, "iw", bnd_t["T_ext"])
    ]

    for idx, (s_idx, prefix, boundary_temp) in enumerate(elements):
        m_idx = s_idx + 1
        T_m_prev = state10[m_idx]

        A[s_idx, 0] = -params[f"G_conv_{prefix}"]
        A[s_idx, 1] = -params[f"G_rad_{prefix}"]
        A[s_idx, s_idx] = params[f"G_conv_{prefix}"] + params[f"G_rad_{prefix}"] + params[f"G_1_{prefix}"]
        A[s_idx, m_idx] = -params[f"G_1_{prefix}"]
        b[s_idx] = gains_t.get(f"Q_sol_{prefix}", 0.0)

        A[m_idx, s_idx] = -params[f"G_1_{prefix}"]
        A[m_idx, m_idx] = params[f"C_{prefix}"] / dt + params[f"G_1_{prefix}"] + params[f"G_rest_{prefix}"]
        b[m_idx] = (params[f"C_{prefix}"] / dt) * T_m_prev + params[f"G_rest_{prefix}"] * boundary_temp

    # 10. Operative Temperature Constraint
    A[10, 0] = w_op
    A[10, 1] = (1.0 - w_op)
    b[10] = T_set

    # Regularize thermal nodes only (indices 0 through 9). Do NOT regularize the control constraint row (index 10).
    A[np.arange(10), np.arange(10)] += 1e-6

    sol = np.linalg.solve(A, b)
    Q_HC = sol[10]

    # Heating Limit
    if Q_limit is not None and Q_HC > Q_limit:
        Qc = float(Q_limit)
        A10 = A[:10, :10].copy()
        b10 = b[:10].copy()
        b10[0] += sigma[1] * Qc
        b10[1] += sigma[0] * Qc
        sol[:10] = np.linalg.solve(A10, b10)
        sol[10] = Qc

    # Cooling Limit
    if Q_limit_cool is not None and Q_HC < -float(Q_limit_cool):
        Qc = -float(Q_limit_cool)
        A10 = A[:10, :10].copy()
        b10 = b[:10].copy()
        b10[0] += sigma[1] * Qc
        b10[1] += sigma[0] * Qc
        sol[:10] = np.linalg.solve(A10, b10)
        sol[10] = Qc

    return sol

def _map_states_for_legacy(envelope, T_air, T_s_dict, T_m_dict):
    """Collapses the 4-element separated nodes back into single equivalent T_m and T_s."""
    C_ew = getattr(envelope, "C_ew", 0.0)
    C_r = getattr(envelope, "C_r", 0.0)
    C_f = getattr(envelope, "C_f", 0.0)
    C_iw = getattr(envelope, "C_iw", 0.0)

    C_sum = C_ew + C_r + C_f + C_iw
    if C_sum == 0: C_sum = 1.0

    T_m = (C_ew * T_m_dict['ew'] + C_r * T_m_dict['r'] +
           C_f * T_m_dict['f'] + C_iw * T_m_dict['iw']) / C_sum

    A_ew = getattr(envelope, "A_ew", 0.0)
    A_r = getattr(envelope, "A_r", 0.0)
    A_f = getattr(envelope, "A_f", 0.0)
    A_iw = getattr(envelope, "A_iw", 0.0)

    A_sum = A_ew + A_r + A_f + A_iw
    if A_sum == 0: A_sum = 1.0

    T_s = (A_ew * T_s_dict['ew'] + A_r * T_s_dict['r'] +
           A_f * T_s_dict['f'] + A_iw * T_s_dict['iw']) / A_sum

    return T_m, T_air, T_s


def simulate_4element(envelope, T_ext, dt_s, T_set_heat, T_set_cool, calendar, w_op=0.5):
    """Executes the timestep loop for the 4-element matrix."""
    n = len(T_ext)
    params = _extract_element_params(envelope, dt_s)

    # Safe fallback gains if envelope does not supply them yet
    Q_kon = getattr(envelope, "Q_il_kon", np.zeros(n))
    Q_rad = getattr(envelope, "Q_il_str", np.zeros(n))
    theta_ew = getattr(envelope, "theta_eq_ew", T_ext)
    theta_r = getattr(envelope, "theta_eq_r", T_ext)
    T_grnd = getattr(envelope, "T_ground", np.full(n, 10.0))

    if calendar is not None:
        steps_per_day = int(round(86400.0 / dt_s))
        day = (np.arange(n) // steps_per_day).astype(int)
        cool_on = (day >= calendar.get("cooling_period_start", 0)) & (day < calendar.get("cooling_period_end", 365))
        heat_on = ~((day >= calendar.get("heating_period_end", 150)) & (
                    day < calendar.get("heating_period_start", 250)))
    else:
        cool_on = np.ones(n, dtype=bool)
        heat_on = np.ones(n, dtype=bool)

    T_air = np.zeros(n);
    T_op = np.zeros(n)
    Q_H = np.zeros(n);
    Q_C = np.zeros(n)

    T_s_dict = {"ew": np.zeros(n), "r": np.zeros(n), "f": np.zeros(n), "iw": np.zeros(n)}
    T_m_dict = {"ew": np.zeros(n), "r": np.zeros(n), "f": np.zeros(n), "iw": np.zeros(n)}

    T0 = float(getattr(envelope, "T_set_min", 20.0))
    state10 = np.full(10, T0)
    sigma = (0.0, 1.0)  # All convective by default

    for t in range(n):
        bnd_t = {"T_ext": T_ext[t], "theta_eq_ew": theta_ew[t], "theta_eq_r": theta_r[t], "T_ground": T_grnd[t]}
        gains_t = {"Q_kon": Q_kon[t], "Q_rad": Q_rad[t], "Q_sol_ew": 0.0, "Q_sol_r": 0.0, "Q_sol_f": 0.0,
                   "Q_sol_iw": 0.0}

        # 1. Free-float
        ff_res = _step10_free_float(params, state10, bnd_t, gains_t)
        T_op_ff = w_op * ff_res[0] + (1.0 - w_op) * ff_res[1]

        need_heat = (T_op_ff < T_set_heat[t]) and heat_on[t]
        need_cool = (T_op_ff > T_set_cool[t]) and cool_on[t]

        # 2. Control Application
        if need_heat or need_cool:
            T_target = T_set_heat[t] if need_heat else T_set_cool[t]
            res = _step11_with_setpoint(
                params, state10, bnd_t, gains_t, T_target, w_op, sigma,
                getattr(envelope, "heatload", None), getattr(envelope, "coolingload", None)
            )
            state10 = res[:10]
            Q_HC = res[10]
        else:
            state10 = ff_res
            Q_HC = 0.0

        # Record States
        T_air[t] = state10[0]
        T_op[t] = w_op * state10[0] + (1.0 - w_op) * state10[1]
        T_s_dict["ew"][t] = state10[2];
        T_m_dict["ew"][t] = state10[3]
        T_s_dict["r"][t] = state10[4];
        T_m_dict["r"][t] = state10[5]
        T_s_dict["f"][t] = state10[6];
        T_m_dict["f"][t] = state10[7]
        T_s_dict["iw"][t] = state10[8];
        T_m_dict["iw"][t] = state10[9]

        if Q_HC >= 0:
            Q_H[t] = Q_HC
        else:
            Q_C[t] = -Q_HC

    return {
        "Q_H": Q_H, "Q_C": Q_C, "T_op": T_op, "T_air": T_air,
        "T_s_ew": T_s_dict["ew"], "T_m_ew": T_m_dict["ew"],
        "T_s_r": T_s_dict["r"], "T_m_r": T_m_dict["r"],
        "T_s_f": T_s_dict["f"], "T_m_f": T_m_dict["f"],
        "T_s_iw": T_s_dict["iw"], "T_m_iw": T_m_dict["iw"]
    }


def calc(envelope, T_e, calendar, dt, initial_day, building_type):
    T_e = np.asarray(T_e, dtype=float)
    T_heat, T_cool = _build_setpoints_arrays(envelope, len(T_e), dt, building_type, False, calendar["holidays"],
                                             initial_day)

    out = simulate_4element(envelope, T_e, dt * 3600.0, T_heat, T_cool, calendar)
    T_m, T_i, T_s = _map_states_for_legacy(
        envelope, out["T_air"],
        {"ew": out["T_s_ew"], "r": out["T_s_r"], "f": out["T_s_f"], "iw": out["T_s_iw"]},
        {"ew": out["T_m_ew"], "r": out["T_m_r"], "f": out["T_m_f"], "iw": out["T_m_iw"]}
    )
    return (out["Q_H"], out["Q_C"], out["T_op"], T_m, T_i, T_s)


def calc_night_setback(envelope, T_e, calendar, dt, initial_day, building_type):
    T_e = np.asarray(T_e, dtype=float)
    T_heat, T_cool = _build_setpoints_arrays(envelope, len(T_e), dt, building_type, True, calendar["holidays"],
                                             initial_day)

    out = simulate_4element(envelope, T_e, dt * 3600.0, T_heat, T_cool, calendar)
    T_m, T_i, T_s = _map_states_for_legacy(
        envelope, out["T_air"],
        {"ew": out["T_s_ew"], "r": out["T_s_r"], "f": out["T_s_f"], "iw": out["T_s_iw"]},
        {"ew": out["T_m_ew"], "r": out["T_m_r"], "f": out["T_m_f"], "iw": out["T_m_iw"]}
    )
    return (out["Q_H"], out["Q_C"], out["T_op"], T_m, T_i, T_s)