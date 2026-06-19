# -*- coding: utf-8 -*-
import math
import numpy as np
import pyomo.environ as pyo
import districtgenerator.functions.solver_config as solver_config

"""
Fixed-design building operation optimization + cheapest concept selection.

- Installed capacities are fixed (coming from BES design sizing rules).
- For heater="opt", we evaluate multiple concepts and choose the minimum TAC concept.
"""

BIG_M = 1e8

def capital_recovery_factor(interest_rate, years):
    n = int(max(years, 1))
    i = float(interest_rate)
    if abs(i) < 1e-12:
        return 1.0 / n
    q = 1.0 + i
    return (q**n * i) / (q**n - 1.0)

def annualized_investment_over_horizon(inv_total, eco_data):
    return float(inv_total) * capital_recovery_factor(eco_data["interest_rate"], eco_data["observation_time"])

def annualized_device_cost_over_horizon(dev, eco_data, cap, mode):
    """
    Horizon-consistent annualized cost (CAPEX with replacements+residual value + fixed O&M)
    """
    observation_time = int(eco_data["observation_time"])
    interest_rate = float(eco_data["interest_rate"])
    q = 1.0 + interest_rate

    life_time = int(dev["life_time"])
    if life_time <= 0:
        raise ValueError(f"Invalid life_time={life_time} for device.")

    CRF = capital_recovery_factor(interest_rate, observation_time)

    # number of replacements within horizon
    n_rep = int(math.floor(observation_time / life_time))

    # discounted replacement investments
    invest_replacements = sum((q ** (-i * life_time)) for i in range(1, n_rep + 1))

    # residual value of the last installed unit at end of horizon
    res_value = ((n_rep + 1) * life_time - observation_time) / life_time * (q ** (-observation_time))

    # annuity factor to convert "effective NPV of capex stream" into annual cost over horizon
    if life_time > observation_time:
        ann_factor = (1.0 - res_value) * CRF
    else:
        ann_factor = (1.0 + invest_replacements - res_value) * CRF

    inv_unsubsidized = float(dev["inv_base"]) * float(cap)
    inv_subsidized = float(dev["inv_var"]) * float(cap)

    if mode == "subsidized":
        c_inv = inv_subsidized * ann_factor
    elif mode == "unsubsidized":
        c_inv = inv_unsubsidized * ann_factor
    else:
        raise ValueError("mode must be 'subsidized' or 'unsubsidized'")

    # fixed O&M: use unsubsidized investment
    c_om = 0.0
    if dev.get("cost_om", None) is not None:
        c_om += float(dev["cost_om"]) * inv_unsubsidized

    # optional: capacity fee
    if dev.get("cap_fee", None) is not None:
        c_om += float(dev["cap_fee"]) * float(cap)

    return float(c_inv + c_om)

# Core operation model
def run_building_operation_fixed_design_one_concept(demand_heat_w, demand_dhw_w, demand_el_w, ev_on_demand_w, site, pv_gen_w,
    stc_gen_w, capacities, dt_s, decentral_device_data, eco_data, pyomo_config, design_building_data, building, cluster_meta):
    """
    Solve fixed-design operation for a single concept (= one capacities dict).
    """

    # Capacity extraction
    def cap_w(dev):
        v = capacities.get(dev, 0.0)
        return float(v) if isinstance(v, (int, float)) else 0.0

    def cap_wh(dev):
        v = capacities.get(dev, 0.0)
        return float(v) if isinstance(v, (int, float)) else 0.0

    def cap_area_m2(dev):
        v = capacities.get(dev, 0.0)
        if isinstance(v, dict):
            if "area" in v:
                return float(v["area"])

    # Parameters
    def dev_param(dev, key):
        return float(decentral_device_data.get(dev, {}).get(key))

    # Efficiencies
    eta_eh = dev_param("EH", "eta_th")
    eta_ewh = dev_param("EWH", "eta_th")
    eta_boi = dev_param("BOI", "eta_th")
    eta_bboi = dev_param("BBOI", "eta_th")
    eta_oboi = dev_param("OBOI", "eta_th")
    eta_h2boi = dev_param("H2BOI", "eta_th")
    eta_chp_el = dev_param("CHP", "eta_el")
    eta_chp_th = dev_param("CHP", "eta_th")
    eta_fc_el = dev_param("FC", "eta_el")
    eta_fc_th = dev_param("FC", "eta_th")
    fc_heat_dissipation_allowed = bool(decentral_device_data.get("FC", {}).get("enable_heat_diss", True))
    tes_eta_standby = dev_param("TES", "eta_standby")
    tes_eta_ch = dev_param("TES", "eta_ch")
    tes_coeff = dev_param("TES", "coeff_ch")
    tes_dhw_eta_standby = dev_param("TES_DHW", "eta_standby")
    tes_dhw_eta_ch = dev_param("TES_DHW", "eta_ch")
    tes_dhw_coeff = dev_param("TES_DHW", "coeff_ch")
    bat_eta_standby = dev_param("BAT", "eta_standby")
    bat_eta_ch = dev_param("BAT", "eta_ch")
    bat_coeff = dev_param("BAT", "coeff_ch")

    cap_HP_kw_th = cap_w("HP") / 1000.0
    hp_installed = any(cap_w(k) > 0 for k in ["HP", "GHP", "BHP", "H2HP", "OHP"])
    cap_EH_kw_th = cap_w("EH") / 1000.0
    cap_EWH_kw_th = cap_w("EWH") / 1000.0
    cap_BOI_kw_th = cap_w("BOI") / 1000.0
    cap_BBOI_kw_th = cap_w("BBOI") / 1000.0
    cap_OBOI_kw_th = cap_w("OBOI") / 1000.0
    cap_H2BOI_kw_th = cap_w("H2BOI") / 1000.0

    cap_CHP_kw_th = cap_w("CHP") / 1000.0
    cap_CHP_kw_el = cap_CHP_kw_th * (eta_chp_el / eta_chp_th)
    cap_FC_kw_th = cap_w("FC") / 1000.0
    cap_FC_kw_el = cap_FC_kw_th * (eta_fc_el / eta_fc_th)

    area_PV_m2 = cap_area_m2("PV")
    area_STC_m2 = cap_area_m2("STC")

    cap_TES_kwh = cap_wh("TES") / 1000.0
    cap_TES_L = cap_TES_kwh / ((1000 * 4180 * float(decentral_device_data["TES"]["T_diff_max"]) * 0.001) / 3.6e6)

    cap_TES_DHW_kwh = cap_wh("TES_DHW") / 1000.0
    cap_TES_DHW_L = cap_TES_DHW_kwh / ((1000 * 4180 * float(decentral_device_data["TES_DHW"]["T_diff_max"]) * 0.001) / 3.6e6)

    cap_BAT_kwh = cap_wh("BAT") / 1000.0

    tes_init_frac = float(decentral_device_data.get("TES", {}).get("init"))
    tes_DHW_init_frac = float(decentral_device_data.get("TES_DHW", {}).get("init"))
    bat_init_frac = float(decentral_device_data.get("BAT", {}).get("init"))

    soc_init_TES = cap_TES_kwh * tes_init_frac  # kWh
    soc_init_TES_DHW = cap_TES_DHW_kwh * tes_DHW_init_frac
    soc_init_BAT = cap_BAT_kwh * bat_init_frac  # kWh

    # HP parameters
    hp_grade = dev_param("HP", "grade")

    # Prepare time series
    heat_w = np.asarray(demand_heat_w, dtype=float).reshape(-1) + np.asarray(demand_dhw_w, dtype=float).reshape(-1)
    heat_SH_w = np.asarray(demand_heat_w, dtype=float).reshape(-1)
    heat_DHW_w = np.asarray(demand_dhw_w, dtype=float).reshape(-1)
    el_w = np.asarray(demand_el_w, dtype=float).reshape(-1)
    T_out = np.asarray(site["T_e_cluster"], dtype=float).reshape(-1)
    hc = building["envelope"].heating_curve.get("clustered")
    Tsink_curve = np.asarray(hc["Ts_curve"], dtype=float).reshape(-1)
    Tsink_curve_reduced = np.asarray(hc["Ts_curve_reduced"], dtype=float).reshape(-1)

    # Temperature reduction measures are applied only if:
    # - a heat pump is installed,
    # - the scenario enables low-temperature measures,
    # - and the heating curve has reduced DESIGN temperatures
    T_measures_applied = (hp_installed
                            and bool(decentral_device_data.get("HP", {}).get("enable_low_temp_measures"))
                            and hc["low_temp_measures_binding"])

    n = int(heat_w.size)

    # Convert to kW / kWh
    heat_kw = heat_w / 1000.0
    heat_SH_kw = heat_SH_w / 1000.0
    heat_DHW_kw = heat_DHW_w / 1000.0
    el_kw = el_w / 1000.0
    pv_kw_av = np.maximum(np.asarray(pv_gen_w, dtype=float).reshape(-1), 0.0) / 1000.0
    stc_kw_av = np.maximum(np.asarray(stc_gen_w, dtype=float).reshape(-1), 0.0) / 1000.0
    ev_kw = np.maximum(np.asarray(ev_on_demand_w, dtype=float).reshape(-1), 0.0) / 1000.0
    dt_h = float(dt_s) / 3600.0

    # Cluster weighting
    len_cluster = int(cluster_meta["len_cluster"])
    cluster_weights = cluster_meta["clusterWeights"]
    cluster_ids = list(cluster_meta["clusters"])

    # Build weight per timestep depending on which cluster this timestep belongs to
    weight_t = np.zeros(n, dtype=float)
    for t in range(n):
        k = t // len_cluster
        cid = cluster_ids[k]
        weight_t[t] = float(cluster_weights[cid])

    # Fixed annualized costs (CAPEX+O&M)
    def dev_dict(dev_name):
        d = dict(decentral_device_data.get(dev_name, {}))

        # ensure inv_var exists (your original fallback logic)
        if "inv_var" not in d or d["inv_var"] is None:
            base = float(d.get("inv_base", 0.0))
            sub = float(d.get("inv_subsidy_rate", 0.0))
            d["inv_var"] = base * (1.0 - sub)
        return d

    # HP "measures" extra cost (only if enabled + applied)
    T_measures_inv_fix = float(decentral_device_data.get("HP", {}).get("measures_inv_fix", 0.0))
    heatload_kw = float(building["envelope"].heatload) / 1000.0

    T_measures_cost = 0.0
    if hp_installed and T_measures_applied and T_measures_inv_fix > 0:
        inv_total = T_measures_inv_fix * heatload_kw
        T_measures_cost = annualized_investment_over_horizon(inv_total, eco_data)

    fixed_cost = 0.0
    fixed_cost += T_measures_cost

    # Annualized device costs over horizon (subsidized CAPEX + O&M on unsubsidized CAPEX)
    fixed_cost += annualized_device_cost_over_horizon(dev_dict("HP"), eco_data, cap_HP_kw_th, mode="subsidized")
    # EH is assumed to be integrated into HP system.
    # Therefore, no separate EH investment is charged when an HP is installed.
    if not hp_installed:
        fixed_cost += annualized_device_cost_over_horizon(dev_dict("EH"), eco_data, cap_EH_kw_th, mode="subsidized")
    fixed_cost += annualized_device_cost_over_horizon(dev_dict("EWH"),eco_data,cap_EWH_kw_th,mode="subsidized")
    fixed_cost += annualized_device_cost_over_horizon(dev_dict("BOI"), eco_data, cap_BOI_kw_th, mode="subsidized")
    fixed_cost += annualized_device_cost_over_horizon(dev_dict("BBOI"), eco_data, cap_BBOI_kw_th, mode="subsidized")
    fixed_cost += annualized_device_cost_over_horizon(dev_dict("OBOI"), eco_data, cap_OBOI_kw_th, mode="subsidized")
    fixed_cost += annualized_device_cost_over_horizon(dev_dict("H2BOI"), eco_data, cap_H2BOI_kw_th, mode="subsidized")
    fixed_cost += annualized_device_cost_over_horizon(dev_dict("CHP"), eco_data, cap_CHP_kw_th, mode="subsidized")
    fixed_cost += annualized_device_cost_over_horizon(dev_dict("FC"), eco_data, cap_FC_kw_th, mode="subsidized")
    fixed_cost += annualized_device_cost_over_horizon(dev_dict("BAT"), eco_data, cap_BAT_kwh, mode="subsidized")
    fixed_cost += annualized_device_cost_over_horizon(dev_dict("TES"), eco_data, cap_TES_L, mode="subsidized")
    fixed_cost += annualized_device_cost_over_horizon(dev_dict("TES_DHW"), eco_data, cap_TES_DHW_L, mode="subsidized")
    fixed_cost += annualized_device_cost_over_horizon(dev_dict("PV"), eco_data, area_PV_m2, mode="subsidized")
    fixed_cost += annualized_device_cost_over_horizon(dev_dict("STC"), eco_data, area_STC_m2, mode="subsidized")

    # Optimization problem
    m = pyo.ConcreteModel("BuildingOperationFixedDesign")
    m.T = pyo.RangeSet(0, n - 1)

    # Support years
    support_years = list(eco_data.get("interpolation_points", [0]))
    m.Y = pyo.Set(initialize=support_years, ordered=True)

    # Heat outputs (kW_th)
    m.q_HP_SH = pyo.Var(m.Y, m.T, within=pyo.NonNegativeReals)
    m.q_HP_DHW = pyo.Var(m.Y, m.T, within=pyo.NonNegativeReals)
    m.q_EH_SH = pyo.Var(m.Y, m.T, within=pyo.NonNegativeReals)
    m.q_EWH_DHW = pyo.Var(m.Y, m.T, within=pyo.NonNegativeReals)
    m.q_EH_DHW = pyo.Var(m.Y, m.T, within=pyo.NonNegativeReals)
    m.q_BOI_SH = pyo.Var(m.Y, m.T, within=pyo.NonNegativeReals)
    m.q_BOI_DHW = pyo.Var(m.Y, m.T, within=pyo.NonNegativeReals)
    m.q_BBOI_SH = pyo.Var(m.Y, m.T, within=pyo.NonNegativeReals)
    m.q_BBOI_DHW = pyo.Var(m.Y, m.T, within=pyo.NonNegativeReals)
    m.q_OBOI_SH = pyo.Var(m.Y, m.T, within=pyo.NonNegativeReals)
    m.q_OBOI_DHW = pyo.Var(m.Y, m.T, within=pyo.NonNegativeReals)
    m.q_H2BOI_SH = pyo.Var(m.Y, m.T, within=pyo.NonNegativeReals)
    m.q_H2BOI_DHW = pyo.Var(m.Y, m.T, within=pyo.NonNegativeReals)
    m.q_CHP_SH = pyo.Var(m.Y, m.T, within=pyo.NonNegativeReals)
    m.q_CHP_DHW = pyo.Var(m.Y, m.T, within=pyo.NonNegativeReals)
    m.q_FC_SH = pyo.Var(m.Y, m.T, within=pyo.NonNegativeReals)
    m.q_FC_DHW = pyo.Var(m.Y, m.T, within=pyo.NonNegativeReals)

    # Electric outputs (kW_el)
    m.p_HP = pyo.Var(m.Y, m.T, within=pyo.NonNegativeReals)
    m.p_CHP = pyo.Var(m.Y, m.T, within=pyo.NonNegativeReals)
    m.p_FC = pyo.Var(m.Y, m.T, within=pyo.NonNegativeReals)

    m.p_grid_in = pyo.Var(m.Y, m.T, within=pyo.NonNegativeReals)
    m.p_grid_out = pyo.Var(m.Y, m.T, within=pyo.NonNegativeReals)
    m.bin_GRID = pyo.Var(m.Y, m.T, within=pyo.Binary)

    # PV/STC used
    m.pv_used = pyo.Var(m.Y, m.T, within=pyo.NonNegativeReals)
    m.stc_used_SH = pyo.Var(m.Y, m.T, within=pyo.NonNegativeReals)
    m.stc_used_DHW = pyo.Var(m.Y, m.T, within=pyo.NonNegativeReals)

    # Storages
    m.tes_ch = pyo.Var(m.Y, m.T, within=pyo.NonNegativeReals)
    m.tes_dis = pyo.Var(m.Y, m.T, within=pyo.NonNegativeReals)
    m.soc_TES = pyo.Var(m.Y, m.T, within=pyo.NonNegativeReals)
    m.bin_TES = pyo.Var(m.Y, m.T, within=pyo.Binary)

    m.tes_dhw_ch = pyo.Var(m.Y, m.T, within=pyo.NonNegativeReals)
    m.tes_dhw_dis = pyo.Var(m.Y, m.T, within=pyo.NonNegativeReals)
    m.soc_TES_DHW = pyo.Var(m.Y, m.T, within=pyo.NonNegativeReals)
    m.bin_TES_DHW = pyo.Var(m.Y, m.T, within=pyo.Binary)

    m.bat_ch = pyo.Var(m.Y, m.T, within=pyo.NonNegativeReals)
    m.bat_dis = pyo.Var(m.Y, m.T, within=pyo.NonNegativeReals)
    m.soc_BAT = pyo.Var(m.Y, m.T, within=pyo.NonNegativeReals)
    m.bin_BAT = pyo.Var(m.Y, m.T, within=pyo.Binary)

    # EV
    m.p_EV_ch = pyo.Var(m.Y, m.T, within=pyo.NonNegativeReals)

    # constraints

    def hp_capacity_rule(mm, y, t):
        if cap_HP_kw_th <= 0:
            return mm.q_HP_SH[y, t] + mm.q_HP_DHW[y, t] == 0.0

        Tout = float(T_out[t])
        T_biv = float(design_building_data["T_bivalent"])
        # Relative slope "a" to consider temperature-dependent HP available heat capacity
        # Source:https://doi.org/10.1016/j.enbuild.2021.111204
        a_HP = 0.04  # 1/K
        Q_max = cap_HP_kw_th * (1 + a_HP * (Tout - T_biv))
        Q_max = max(Q_max, 0.0)
        return mm.q_HP_SH[y, t] + mm.q_HP_DHW[y, t] <= Q_max

    m.lim_HP = pyo.Constraint(m.Y, m.T, rule=hp_capacity_rule)
    m.lim_EH = pyo.Constraint(m.Y, m.T, rule=lambda mm, y, t: mm.q_EH_SH[y, t] + mm.q_EH_DHW[y, t] <= cap_EH_kw_th)
    m.lim_EWH = pyo.Constraint(m.Y, m.T, rule=lambda mm, y, t: mm.q_EWH_DHW[y, t] <= cap_EWH_kw_th)
    m.lim_BOI = pyo.Constraint(m.Y, m.T, rule=lambda mm, y, t: mm.q_BOI_SH[y, t] + mm.q_BOI_DHW[y, t] <= cap_BOI_kw_th)
    m.lim_BBOI = pyo.Constraint(m.Y, m.T, rule=lambda mm, y, t: mm.q_BBOI_SH[y, t] + mm.q_BBOI_DHW[y, t] <= cap_BBOI_kw_th)
    m.lim_OBOI = pyo.Constraint(m.Y, m.T, rule=lambda mm, y, t: mm.q_OBOI_SH[y, t] + mm.q_OBOI_DHW[y, t] <= cap_OBOI_kw_th)
    m.lim_H2BOI = pyo.Constraint(m.Y, m.T, rule=lambda mm, y, t: mm.q_H2BOI_SH[y, t] + mm.q_H2BOI_DHW[y, t] <= cap_H2BOI_kw_th)

    m.lim_CHP_p = pyo.Constraint(m.Y, m.T, rule=lambda mm, y, t: mm.p_CHP[y, t] <= cap_CHP_kw_el)
    m.lim_FC_p = pyo.Constraint(m.Y, m.T, rule=lambda mm, y, t: mm.p_FC[y, t] <= cap_FC_kw_el)

    m.lim_pv = pyo.Constraint(m.Y, m.T, rule=lambda mm, y, t: mm.pv_used[y, t] <= pv_kw_av[t])
    m.lim_stc = pyo.Constraint(m.Y, m.T, rule=lambda mm, y, t: mm.stc_used_SH[y, t] + mm.stc_used_DHW[y, t] <= stc_kw_av[t])

    m.ev_on_demand_fix = pyo.Constraint(m.Y, m.T, rule=lambda mm, y, t: mm.p_EV_ch[y, t] == float(ev_kw[t]))

    soc_min_TES = float(decentral_device_data.get("TES", {}).get("soc_min"))
    soc_max_TES = float(decentral_device_data.get("TES", {}).get("soc_max"))
    m.tes_soc_max = pyo.Constraint(m.Y, m.T, rule=lambda mm, y, t: mm.soc_TES[y, t] <= soc_max_TES * cap_TES_kwh)
    m.tes_soc_min = pyo.Constraint(m.Y, m.T, rule=lambda mm, y, t: mm.soc_TES[y, t] >= soc_min_TES * cap_TES_kwh)
    m.tes_bin_dis = pyo.Constraint(m.Y, m.T, rule=lambda mm, y, t: mm.tes_dis[y, t] <= mm.bin_TES[y, t] * BIG_M)
    m.tes_bin_ch = pyo.Constraint(m.Y, m.T, rule=lambda mm, y, t: mm.tes_ch[y, t] <= (1 - mm.bin_TES[y, t]) * BIG_M)

    soc_min_TES_DHW = float(decentral_device_data.get("TES_DHW", {}).get("soc_min"))
    soc_max_TES_DHW = float(decentral_device_data.get("TES_DHW", {}).get("soc_max"))
    m.tes_dhw_soc_max = pyo.Constraint(m.Y, m.T, rule=lambda mm, y, t: mm.soc_TES_DHW[y, t] <= soc_max_TES_DHW * cap_TES_DHW_kwh)
    m.tes_dhw_soc_min = pyo.Constraint(m.Y, m.T, rule=lambda mm, y, t: mm.soc_TES_DHW[y, t] >= soc_min_TES_DHW * cap_TES_DHW_kwh)
    m.tes_dhw_bin_dis = pyo.Constraint(m.Y, m.T, rule=lambda mm, y, t: mm.tes_dhw_dis[y, t] <= mm.bin_TES_DHW[y, t] * BIG_M)
    m.tes_dhw_bin_ch = pyo.Constraint(m.Y, m.T, rule=lambda mm, y, t: mm.tes_dhw_ch[y, t] <= (1 - mm.bin_TES_DHW[y, t]) * BIG_M)

    soc_min_BAT = float(decentral_device_data.get("BAT", {}).get("soc_min"))
    soc_max_BAT = float(decentral_device_data.get("BAT", {}).get("soc_max"))
    m.bat_soc_max = pyo.Constraint(m.Y, m.T, rule=lambda mm, y, t: mm.soc_BAT[y, t] <= soc_max_BAT * cap_BAT_kwh)
    m.bat_soc_min = pyo.Constraint(m.Y, m.T, rule=lambda mm, y, t: mm.soc_BAT[y, t] >= soc_min_BAT * cap_BAT_kwh)
    m.bat_bin_dis = pyo.Constraint(m.Y, m.T, rule=lambda mm, y, t: mm.bat_dis[y, t] <= mm.bin_BAT[y, t] * BIG_M)
    m.bat_bin_ch = pyo.Constraint(m.Y, m.T, rule=lambda mm, y, t: mm.bat_ch[y, t] <= (1 - mm.bin_BAT[y, t]) * BIG_M)

    if tes_coeff > 0 and cap_TES_kwh > 0:
        m.tes_ch_lim = pyo.Constraint(m.Y, m.T, rule=lambda mm, y, t: mm.tes_ch[y, t] <= tes_coeff * cap_TES_kwh)
        m.tes_dis_lim = pyo.Constraint(m.Y, m.T, rule=lambda mm, y, t: mm.tes_dis[y, t] <= tes_coeff * cap_TES_kwh)

    if tes_dhw_coeff > 0 and cap_TES_DHW_kwh > 0:
        m.tes_dhw_ch_lim = pyo.Constraint(m.Y, m.T, rule=lambda mm, y, t: mm.tes_dhw_ch[y, t] <= tes_dhw_coeff * cap_TES_DHW_kwh)
        m.tes_dhw_dis_lim = pyo.Constraint(m.Y, m.T, rule=lambda mm, y, t: mm.tes_dhw_dis[y, t] <= tes_dhw_coeff * cap_TES_DHW_kwh)

    if bat_coeff > 0 and cap_BAT_kwh > 0:
        m.bat_ch_lim = pyo.Constraint(m.Y, m.T, rule=lambda mm, y, t: mm.bat_ch[y, t] <= bat_coeff * cap_BAT_kwh)
        m.bat_dis_lim = pyo.Constraint(m.Y, m.T, rule=lambda mm, y, t: mm.bat_dis[y, t] <= bat_coeff * cap_BAT_kwh)

    # Prevent simultaneous import and export (BIG-M)
    m.grid_bin_in = pyo.Constraint(m.Y, m.T, rule=lambda mm, y, t: mm.p_grid_in[y, t] <= mm.bin_GRID[y, t] * BIG_M)
    m.grid_bin_out = pyo.Constraint(m.Y, m.T, rule=lambda mm, y, t: mm.p_grid_out[y, t] <= (1 - mm.bin_GRID[y, t]) * BIG_M)

    # HP conversion
    def hp_conv_rule(mm, y, t):
        if cap_HP_kw_th <= 0:
            return mm.q_HP_SH[y, t] + mm.q_HP_DHW[y, t] == 0.0

        # choose sink temperature depending on whether measures are applied
        Tsink_SH = float(Tsink_curve_reduced[t]) if T_measures_applied else float(Tsink_curve[t])
        Tsink_DHW = float(decentral_device_data["TES_DHW"]["T_DHW_needed"])
        Tout = float(T_out[t])

        dT_SH = max(Tsink_SH - Tout, 0.1)
        dT_DHW = max(Tsink_DHW - Tout, 0.1)


        cop_sh_raw = hp_grade * (273.15 + Tsink_SH) / dT_SH
        cop_dhw_raw = hp_grade * (273.15 + Tsink_DHW) / dT_DHW

        COP_SH = min(cop_sh_raw, 7.0)
        COP_DHW = min(cop_dhw_raw, 7.0)

        return mm.p_HP[y, t] == (mm.q_HP_SH[y, t] / COP_SH + mm.q_HP_DHW[y, t] / COP_DHW)

    m.hp_conversion = pyo.Constraint(m.Y, m.T, rule=hp_conv_rule)

    # CHP/FC heat-electric coupling
    m.chp_heat_link = pyo.Constraint(
        m.Y, m.T, rule=lambda mm, y, t: mm.q_CHP_SH[y, t] + mm.q_CHP_DHW[y, t] == mm.p_CHP[y, t] * (eta_chp_th / eta_chp_el))

    if fc_heat_dissipation_allowed:
        m.fc_heat_link = pyo.Constraint(
            m.Y, m.T, rule=lambda mm, y, t: mm.q_FC_SH[y, t] + mm.q_FC_DHW[y, t] <= mm.p_FC[y, t] * (eta_fc_th / eta_fc_el))
    else:
        m.fc_heat_link = pyo.Constraint(
            m.Y, m.T, rule=lambda mm, y, t: mm.q_FC_SH[y, t] + mm.q_FC_DHW[y, t] == mm.p_FC[y, t] * (eta_fc_th / eta_fc_el))

    # Storage SOC dynamics
    # SOC recursion: reset at the start of each representative period
    def tes_soc_rule(mm, y, t):
        if (t % len_cluster) == 0:
            soc_prev = soc_init_TES
        else:
            soc_prev = mm.soc_TES[y, t - 1]
        return mm.soc_TES[y, t] == soc_prev * (tes_eta_standby ** dt_h) + (mm.tes_ch[y, t] * tes_eta_ch - mm.tes_dis[y, t] / tes_eta_ch) * dt_h

    def tes_dhw_soc_rule(mm, y, t):
        if (t % len_cluster) == 0:
            soc_prev = soc_init_TES_DHW
        else:
            soc_prev = mm.soc_TES_DHW[y, t - 1]

        return mm.soc_TES_DHW[y, t] == soc_prev * (tes_dhw_eta_standby ** dt_h) + (mm.tes_dhw_ch[y, t] * tes_dhw_eta_ch - mm.tes_dhw_dis[y, t] / tes_dhw_eta_ch) * dt_h

    def bat_soc_rule(mm, y, t):
        if (t % len_cluster) == 0:
            soc_prev = soc_init_BAT
        else:
            soc_prev = mm.soc_BAT[y, t - 1]
        return mm.soc_BAT[y, t] == soc_prev * (bat_eta_standby ** dt_h) + (mm.bat_ch[y, t] * bat_eta_ch - mm.bat_dis[y, t] / bat_eta_ch) * dt_h

    m.tes_soc_dyn = pyo.Constraint(m.Y, m.T, rule=tes_soc_rule)
    m.tes_dhw_soc_dyn = pyo.Constraint(m.Y, m.T, rule=tes_dhw_soc_rule)
    m.bat_soc_dyn = pyo.Constraint(m.Y, m.T, rule=bat_soc_rule)

    # End of each representative period returns to initial SOC
    n_clusters = int(np.ceil(n / len_cluster))
    m.C = pyo.RangeSet(0, n_clusters - 1)

    def tes_final_soc_rule(mm, y, c):
        t_last = c * len_cluster + (len_cluster - 1)
        if t_last >= n:
            return pyo.Constraint.Skip
        return mm.soc_TES[y, t_last] == soc_init_TES

    def tes_dhw_final_soc_rule(mm, y, c):
        t_last = c * len_cluster + (len_cluster - 1)
        if t_last >= n:
            return pyo.Constraint.Skip
        return mm.soc_TES_DHW[y, t_last] == soc_init_TES_DHW

    def bat_final_soc_rule(mm, y, c):
        t_last = c * len_cluster + (len_cluster - 1)
        if t_last >= n:
            return pyo.Constraint.Skip
        return mm.soc_BAT[y, t_last] == soc_init_BAT

    m.tes_final_soc = pyo.Constraint(m.Y, m.C, rule=tes_final_soc_rule)
    m.tes_dhw_final_soc = pyo.Constraint(m.Y, m.C, rule=tes_dhw_final_soc_rule)
    m.bat_final_soc = pyo.Constraint(m.Y, m.C, rule=bat_final_soc_rule)

    # Energy balances
    # Heat
    m.heat_balance_SH = pyo.Constraint(
        m.Y, m.T,
        rule=lambda mm, y, t:
        mm.q_HP_SH[y,t] + mm.q_EH_SH[y,t] + mm.q_BOI_SH[y,t] + mm.q_BBOI_SH[y,t] + mm.q_OBOI_SH[y,t] + mm.q_H2BOI_SH[y,t] + mm.q_CHP_SH[y,t] + mm.q_FC_SH[y,t] + mm.stc_used_SH[y,t] + mm.tes_dis[y,t]
        == float(heat_SH_kw[t]) + mm.tes_ch[y,t])

    m.heat_balance_DHW = pyo.Constraint(
        m.Y, m.T,
        rule=lambda mm, y, t:
        mm.q_HP_DHW[y, t] + mm.q_EH_DHW[y, t] + mm.q_EWH_DHW[y, t] + mm.q_BOI_DHW[y, t] + mm.q_BBOI_DHW[y, t] + mm.q_OBOI_DHW[y, t] + mm.q_H2BOI_DHW[y, t] + mm.q_CHP_DHW[y, t] + mm.q_FC_DHW[y, t] + mm.stc_used_DHW[y, t] + mm.tes_dhw_dis[y, t]
        == float(heat_DHW_kw[t]) + mm.tes_dhw_ch[y, t])

    # Electricity
    def el_balance_rule(mm, y, t):
        return (
            mm.pv_used[y, t] + mm.p_CHP[y, t] + mm.p_FC[y, t] + mm.bat_dis[y, t] + mm.p_grid_in[y, t]
            == float(el_kw[t]) + mm.p_EV_ch[y, t] + mm.p_HP[y, t] + (mm.q_EH_SH[y, t] + mm.q_EH_DHW[y, t]) / eta_eh + mm.q_EWH_DHW[y, t] / eta_ewh + mm.bat_ch[y, t] + mm.p_grid_out[y, t])

    m.el_balance = pyo.Constraint(m.Y, m.T, rule=el_balance_rule)


    # Multi-year prices consideration
    # Support years
    support_years = eco_data.get("interpolation_points", [0])

    n_years = int(eco_data["observation_time"])
    i = float(eco_data["interest_rate"])
    q = 1.0 + i

    # Each support year covers until the next support year
    interval_len = {}
    for idx, y in enumerate(support_years):
        if idx < len(support_years) - 1:
            interval_len[y] = support_years[idx + 1] - y
        else:
            interval_len[y] = n_years - y

    # robust access: lists in EcoConfig are expanded to observation_time already
    def eco_year(key: str, y: int) -> float:
        v = eco_data.get(key)
        if isinstance(v, (list, tuple, np.ndarray)):
            yy = int(y)
            if yy < 0:
                yy = 0
            return float(v[yy])
        return float(v)

    def discount_factor_for_interval(start_year: int, years_in_interval: int) -> float:
        # geometric series discount factor for years [start_year .. start_year+years_in_interval-1]
        if abs(i) < 1e-12:
            return float(years_in_interval)
        base = 1.0 / (q ** start_year)
        series = (1.0 - (1.0 / q) ** years_in_interval) / (1.0 - 1.0 / q)
        return base * series

    # annualize the NPV like EHDO
    if abs(i) < 1e-12:
        ann_fac_horizon = 1.0 / n_years
    else:
        ann_fac_horizon = (i * (q ** n_years)) / ((q ** n_years) - 1.0)

    def annual_energy_cost_expr(mm, y):
        # prices at support year y
        p_el_y = eco_year("price_supply_el", y)
        r_el_y = eco_year("revenue_feed_in_el", y)
        p_gas_y = eco_year("price_supply_gas", y)
        p_biom_y = eco_year("price_biomass", y)
        p_oil_y = eco_year("price_oil", y)
        p_h2_y = eco_year("price_hydrogen", y)

        expr = 0.0
        for t in range(n):
            w = float(weight_t[t])

            # electricity import/export
            expr += w * (mm.p_grid_in[y, t] * dt_h) * p_el_y
            expr -= w * (mm.p_grid_out[y, t] * dt_h) * r_el_y

            # gas: BOI fuel + CHP fuel (by electric output)
            gas_kw = ((mm.q_BOI_SH[y, t] + mm.q_BOI_DHW[y, t]) / eta_boi) + (mm.p_CHP[y, t] / eta_chp_el)
            expr += w * (gas_kw * dt_h) * p_gas_y

            # biomass
            expr += w * ((mm.q_BBOI_SH[y, t] + mm.q_BBOI_DHW[y, t]) / eta_bboi * dt_h) * p_biom_y

            # oil
            expr += w * ((mm.q_OBOI_SH[y, t] + mm.q_OBOI_DHW[y, t]) / eta_oboi * dt_h) * p_oil_y

            # hydrogen: H2BOI fuel + FC fuel
            h2_kw = ((mm.q_H2BOI_SH[y, t] + mm.q_H2BOI_DHW[y, t]) / eta_h2boi) + (mm.p_FC[y, t] / eta_fc_el)
            expr += w * (h2_kw * dt_h) * p_h2_y

        return expr  # €/year for that price year

    # NPV of energy costs over horizon using support-year intervals
    npv_energy = 0.0
    for y in support_years:
        df = discount_factor_for_interval(y, interval_len[y])
        npv_energy += annual_energy_cost_expr(m, y) * df

    annualized_energy_costs = npv_energy * ann_fac_horizon

    # Objective function
    m.obj = pyo.Objective(expr=fixed_cost + annualized_energy_costs, sense=pyo.minimize)

    # Solve
    solver, solver_options = solver_config.create_solver(pyomo_config=pyomo_config)
    results = solver.solve(m, tee=False, options=solver_options)

    tc = results.solver.termination_condition
    if tc != pyo.TerminationCondition.optimal:
        raise RuntimeError(f"Fixed-design building operation did not solve to optimality. Termination: {tc}")

    # Extract results
    def val(x):
        v = pyo.value(x)
        return 0.0 if v is None else float(v)

    # For reporting totals across the whole horizon:
    # weight each support-year by how many years it represents.
    years_weight = interval_len

    # Per support year annual totals (kWh/a)
    el_import_kwh_by_year = {}
    el_export_kwh_by_year = {}
    pv_used_kwh_by_year = {}
    stc_used_kwh_by_year = {}
    ev_charge_kwh_by_year = {}

    for y in support_years:
        el_import_kwh_by_year[y] = sum(val(m.p_grid_in[y, t]) * dt_h * float(weight_t[t]) for t in range(n))
        el_export_kwh_by_year[y] = sum(val(m.p_grid_out[y, t]) * dt_h * float(weight_t[t]) for t in range(n))
        pv_used_kwh_by_year[y] = sum(val(m.pv_used[y, t]) * dt_h * float(weight_t[t]) for t in range(n))
        stc_used_kwh_by_year[y] = sum((val(m.stc_used_SH[y, t]) + val(m.stc_used_DHW[y, t])) * dt_h * float(weight_t[t]) for t in range(n))
        ev_charge_kwh_by_year[y] = sum(val(m.p_EV_ch[y, t]) * dt_h * float(weight_t[t]) for t in range(n))

    # Totals over whole horizon (kWh over observation time)
    el_import_kwh_horizon = sum(el_import_kwh_by_year[y] * years_weight[y] for y in support_years)
    el_export_kwh_horizon = sum(el_export_kwh_by_year[y] * years_weight[y] for y in support_years)
    pv_used_kwh_horizon = sum(pv_used_kwh_by_year[y] * years_weight[y] for y in support_years)
    stc_used_kwh_horizon = sum(stc_used_kwh_by_year[y] * years_weight[y] for y in support_years)
    ev_charge_kwh_horizon = sum(ev_charge_kwh_by_year[y] * years_weight[y] for y in support_years)

    res = {
        "status": str(tc),
        "tac_eur_per_a": val(m.obj),
        "fixed_cost_eur_per_a": float(fixed_cost),
        "annualized_energy_costs_eur_per_a": float(val(annualized_energy_costs)),
        "support_years": list(support_years),

        # per-support-year results (annual kWh for that support year)
        "el_import_kWh_by_year": {int(y): float(v) for y, v in el_import_kwh_by_year.items()},
        "el_export_kWh_by_year": {int(y): float(v) for y, v in el_export_kwh_by_year.items()},
        "pv_used_kWh_by_year": {int(y): float(v) for y, v in pv_used_kwh_by_year.items()},
        "stc_used_kWh_by_year": {int(y): float(v) for y, v in stc_used_kwh_by_year.items()},
        "ev_charge_kWh_by_year": {int(y): float(v) for y, v in ev_charge_kwh_by_year.items()},

        # totals across observation horizon (kWh over all years)
        "el_import_kWh_horizon": float(el_import_kwh_horizon),
        "el_export_kWh_horizon": float(el_export_kwh_horizon),
        "pv_used_kWh_horizon": float(pv_used_kwh_horizon),
        "stc_used_kWh_horizon": float(stc_used_kwh_horizon),
        "ev_charge_kWh_horizon": float(ev_charge_kwh_horizon),
        "T_measures_applied": bool(T_measures_applied),
        "T_measures_cost_eur_per_a": float(T_measures_cost),
        "heatload_kW": float(heatload_kw),
    }

    return res

# Choose cheapest concept (heater="opt")
def choose_cheapest_heating_concept_fixed_design(demand_heat_w, demand_dhw_w, demand_el_w, ev_on_demand_w, site,
    pv_gen_w, stc_gen_w, candidates, dt_s, decentral_device_data, eco_data, pyomo_config, design_building_data, building, cluster_meta):
    """
    Evaluate each candidate concept with operation optimization and return (best_concept, all_results).
    """
    all_results = {}
    best_concept = None
    best_tac = float("inf")

    for concept, caps in candidates.items():
        r = run_building_operation_fixed_design_one_concept(
            demand_heat_w=demand_heat_w,
            demand_dhw_w=demand_dhw_w,
            demand_el_w=demand_el_w,
            ev_on_demand_w=ev_on_demand_w,
            site=site,
            pv_gen_w=pv_gen_w,
            stc_gen_w=stc_gen_w,
            capacities=caps,
            dt_s=dt_s,
            decentral_device_data=decentral_device_data,
            eco_data=eco_data,
            pyomo_config=pyomo_config,
            design_building_data=design_building_data,
            building=building,
            cluster_meta=cluster_meta
        )

        all_results[concept] = r
        tac = float(r["tac_eur_per_a"])
        if tac < best_tac:
            best_tac = tac
            best_concept = concept

    if best_concept is None:
        raise RuntimeError("No feasible candidate concept found for heater='opt'.")

    return best_concept, all_results
