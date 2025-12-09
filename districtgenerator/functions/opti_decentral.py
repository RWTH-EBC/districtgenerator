# opti_decentral.py — revised
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Decentralized operational optimization for a building district.
Created: 2024-02-26, revised: 2025-09-29
Author: Joel Schölzel
"""
import time
import gurobipy as gp

def _get_Te_series(siteData, cluster_idx, T_len):
    """
    Robust extractor for ambient temperature [°C] over the cluster horizon.
    Tries several common keys and both dict/attribute styles.
    Falls back to 0°C if nothing found.
    """
    possible = [
        "T_e_cluster", "Te_cluster", "Ta_cluster", "ambient_temperature_cluster",
        "T_e", "Te", "Ta", "ambient_temperature", "outdoor_temperature",
        "weather_Te_cluster", "weather_Te"
    ]

    def _take(val):
        # Accept dict-of-clusters or a flat sequence; trim/pad to T_len
        import collections
        if isinstance(val, dict):
            if cluster_idx in val:
                seq = list(val[cluster_idx])
            else:
                # take any first key if cluster index missing
                try:
                    first_key = next(iter(val))
                    seq = list(val[first_key])
                except StopIteration:
                    return None
        else:
            seq = list(val)
        if len(seq) >= T_len:
            return seq[:T_len]
        # pad with last value if too short
        pad_val = seq[-1] if len(seq) else 0.0
        return seq + [pad_val] * (T_len - len(seq))

    # dict access
    if isinstance(siteData, dict):
        for k in possible:
            if k in siteData:
                got = _take(siteData[k])
                if got is not None:
                    return got
    # attribute access
    for k in possible:
        if hasattr(siteData, k):
            got = _take(getattr(siteData, k))
            if got is not None:
                return got

    print("[warn] No ambient temperature found in data.site → using 0°C fallback.")
    return [0.0] * T_len


def _cop_safe(Te, Ts, grade, min_delta=3.0, cop_min=1.0, cop_max=8.0):
    """
    Compute a numerically safe COP coefficient for linear constraints:
    COP = grade * (273.15 + Ts) / max(min_delta, Ts - Te), then clamp.
    """
    delta = max(min_delta, Ts - Te)
    cop = grade * (273.15 + Ts) / delta
    return max(cop_min, min(cop, cop_max))

def run_opti_decentral(model, data, cluster: int):
    """
    Min-cost / min-CO2 operation of decentralized devices with optional heat sharing.
    Expects 'data' to provide: time, ecoData, site, decentral_device_data, params_ehdo_model, district.
    Optionally: data.heat_link_cap (nb x nb) in W, otherwise no heat links.
    """

    # ---------------------------
    # Unpack data & basic sizes
    # ---------------------------
    timeData = data.time
    ecoData = data.ecoData
    siteData = data.site
    param_dec_devs = data.decentral_device_data
    model_param = data.params_ehdo_model
    buildingData = data.district

    nb = len(buildingData)
    time_steps = range(int(timeData["clusterLength"] / timeData["timeResolution"]))
    dt = timeData["timeResolution"] / timeData["dataResolution"]  # factor for Wh integration
    last_time_step = len(time_steps) - 1

    # optional heat link capacities (W). If not provided: all zeros (no links)
    heat_link_cap = getattr(data, "heat_link_cap", None)
    if heat_link_cap is None:
        heat_link_cap = [[0.0 if i != j else 0.0 for j in range(nb)] for i in range(nb)]

    # ---------------------------
    # Profiles & exogenous series
    # ---------------------------
    #T_e = siteData["T_e_cluster"][cluster]   # list of °C
    T_len = int(timeData["clusterLength"] / timeData["timeResolution"])
    T_e = _get_Te_series(siteData, cluster, T_len)  # list[float] length == T_len
    Q_DHW, Q_heating, PV_gen, STC_heat, elec_dem = {}, {}, {}, {}, {}

    for n in range(nb):
        Q_DHW[n]     = buildingData[n]["user"].dhw_cluster[cluster]
        Q_heating[n] = buildingData[n]["user"].heat_cluster[cluster]
        elec_dem[n]  = buildingData[n]["user"].elec_cluster[cluster]
        # optional gens:
        PV_gen[n]  = buildingData[n].get("generationPV_cluster", {}).get(cluster, [0.0]*len(elec_dem[n]))
        STC_heat[n]= buildingData[n].get("generationSTC_cluster", {}).get(cluster, [0.0]*len(elec_dem[n]))

    # ensure capacities exist
    for n in range(nb):
        buildingData[n].setdefault("capacities", {})
        caps = buildingData[n]["capacities"]
        caps.setdefault("PV", {"area": 0.0})
        caps.setdefault("STC", {"area": 0.0})
        for dev in ["HP", "EH", "BAT", "TES"]:
            caps.setdefault(dev, 0.0)

    # ---------------------------
    # Sets / devices
    # ---------------------------
    ecs_heat = ("HP", "EH", "STC")     # heat-producing paths
    ecs_power = ("HP", "EH")           # electric consumers (PV handled exogenously via PV_gen)
    ecs_storage = ("TES", "BAT")
    hp_modi = ("HP35", "HP55")

    # ---------------------------
    # Initial SoCs (Wh)
    # ---------------------------
    soc_nom = {"TES": {}, "BAT": {}}
    soc_init = {"TES": {}, "BAT": {}}
    for n in range(nb):
        soc_nom["TES"][n]  = buildingData[n]["capacities"]["TES"]
        soc_nom["BAT"][n]  = buildingData[n]["capacities"]["BAT"]
        soc_init["TES"][n] = 0.5 * soc_nom["TES"][n]
        soc_init["BAT"][n] = 0.5 * soc_nom["BAT"][n]

    # ---------------------------
    # Variables
    # ---------------------------
    # Electric power of devices
    power_dom = {dev: {n: {t: model.addVar(vtype="C",
                                           name=f"power_{dev}_n{n}_t{t}") 
                           for t in time_steps}
                       for n in range(nb)}
                 for dev in ecs_power}

    # Heat output of devices
    heat_dom = {dev: {n: {t: model.addVar(vtype="C",
                                          name=f"heat_{dev}_n{n}_t{t}")
                          for t in time_steps}
                      for n in range(nb)}
                for dev in ecs_heat}

    # HP modes
    power_mode = {m: {n: {t: model.addVar(vtype="C",
                                          name=f"power_mode_{m}_n{n}_t{t}")
                          for t in time_steps}
                      for n in range(nb)}
                  for m in hp_modi}
    heat_mode  = {m: {n: {t: model.addVar(vtype="C",
                                          name=f"heat_mode_{m}_n{n}_t{t}")
                          for t in time_steps}
                      for n in range(nb)}
                  for m in hp_modi}

    # DHW via EH split (falls du das getrennt brauchst)
    dhw_dom = {"EH": {n: {t: model.addVar(vtype="C",
                                          name=f"dhw_EH_n{n}_t{t}")
                          for t in time_steps}
                      for n in range(nb)}}

    # Directed heat flows between buildings (i→j)
    heat_connection = {i: {j: {t: model.addVar(vtype="C",
                                               name=f"heat_conn_n{i}_n{j}_t{t}")
                               for t in time_steps}
                           for j in range(nb) if j != i}
                       for i in range(nb)}
    # Net heat import per building
    net_heat_import = {n: {t: model.addVar(vtype="C",
                                           lb=-gp.GRB.INFINITY,
                                           name=f"net_heat_import_n{n}_t{t}")
                           for t in time_steps}
                       for n in range(nb)}

    # Storage vars
    soc_dom = {dev: {n: {t: model.addVar(vtype="C",
                                         name=f"soc_{dev}_n{n}_t{t}")
                         for t in time_steps}
                     for n in range(nb)}
               for dev in ecs_storage}
    ch_dom  = {dev: {n: {t: model.addVar(vtype="C",
                                         name=f"ch_{dev}_n{n}_t{t}")
                         for t in time_steps}
                     for n in range(nb)}
               for dev in ecs_storage}
    dch_dom = {dev: {n: {t: model.addVar(vtype="C",
                                         name=f"dch_{dev}_n{n}_t{t}")
                         for t in time_steps}
                     for n in range(nb)}
               for dev in ecs_storage}

    # Residuals per building
    res_dom = {"power": {n: {t: model.addVar(vtype="C",
                                             name=f"residual_power_n{n}_t{t}")
                             for t in time_steps}
                         for n in range(nb)},
               "feed":  {n: {t: model.addVar(vtype="C",
                                             name=f"residual_feed_n{n}_t{t}")
                             for t in time_steps}
                         for n in range(nb)}}

    # Binary: either import or feed at building level
    binary = {"HLINE": {n: {t: model.addVar(vtype=gp.GRB.BINARY,
                                            name=f"bin_HLINE_n{n}_t{t}")
                            for t in time_steps}
                        for n in range(nb)},
              "BAT":   {n: {t: model.addVar(vtype=gp.GRB.BINARY,
                                            name=f"bin_BAT_n{n}_t{t}")
                            for t in time_steps}
                        for n in range(nb)}}

    # Residual neighborhood totals
    residual = {"power": {t: model.addVar(vtype="C",
                                          name=f"P_dem_total_{t}")
                          for t in time_steps},
                "feed":  {t: model.addVar(vtype="C",
                                          name=f"P_inj_total_{t}")
                          for t in time_steps}}

    # Grid exchange at PCC/GCP
    power = {"from_grid": {t: model.addVar(vtype="C", lb=0.0,
                                           name=f"P_dem_gcp_{t}")
                           for t in time_steps},
             "to_grid":   {t: model.addVar(vtype="C", lb=0.0,
                                           name=f"P_inj_gcp_{t}")
                           for t in time_steps}}

    # Trafostellung (kein gleichzeitiges Beziehen/Einspeisen am GCP)
    yTrafo = model.addVars(time_steps, vtype="B", name="yTrafo")

    # Aggregierte Größen
    from_grid_total_el = model.addVar(vtype="C", name="from_grid_total_el")
    to_grid_total_el   = model.addVar(vtype="C", name="to_grid_total_el")
    daily_peak = {d: model.addVar(vtype="C", lb=-gp.GRB.INFINITY,
                                  name=f"peak_network_load_d{d}")
                  for d in range(7)}
    peaksum = model.addVar(vtype="C", lb=-gp.GRB.INFINITY, name="sum_peak_daily_network_load")

    operational_costs = model.addVar(vtype="C", lb=-gp.GRB.INFINITY, name="Cost_total")
    co2_total         = model.addVar(vtype="C", lb=-gp.GRB.INFINITY, name="Emission_total")
    obj               = model.addVar(vtype="C", lb=-gp.GRB.INFINITY, name="obj")

    # ---------------------------
    # Objective
    # ---------------------------
    model.update()
    model.setObjective(obj, gp.GRB.MINIMIZE)

    # ---------------------------
    # Constraints
    # ---------------------------

    # Device capacity limits
    for n in range(nb):
        for t in time_steps:
            model.addConstr(heat_dom["HP"][n][t] <= buildingData[n]["capacities"]["HP"],
                            name=f"HP_heat_cap_{n}_{t}")
            model.addConstr(power_dom["EH"][n][t] <= buildingData[n]["capacities"]["EH"],
                            name=f"EH_el_cap_{n}_{t}")
            model.addConstr(heat_dom["STC"][n][t] <= STC_heat[n][t],
                            name=f"STC_heat_avail_{n}_{t}")

            # HP mode split
            model.addConstr(heat_dom["HP"][n][t] ==
                            heat_mode["HP35"][n][t] + heat_mode["HP55"][n][t],
                            name=f"HP_heat_split_{n}_{t}")
            model.addConstr(power_dom["HP"][n][t] ==
                            power_mode["HP35"][n][t] + power_mode["HP55"][n][t],
                            name=f"HP_power_split_{n}_{t}")

            # Mode eligibility by construction year
            if buildingData[n]["envelope"].construction_year >= 1995 and buildingData[n]["capacities"]["HP"] > 0:
                model.addConstr(power_mode["HP55"][n][t] == 0, name=f"HP_mode_only35_{n}_{t}")
            elif buildingData[n]["envelope"].construction_year < 1995 and buildingData[n]["capacities"]["HP"] > 0:
                model.addConstr(power_mode["HP35"][n][t] == 0, name=f"HP_mode_only55_{n}_{t}")

            # HP conversion (simple Carnot-like)
            # Replace inside the time-step loop where HP conversions are set:
            cop35 = _cop_safe(Te=T_e[t], Ts=35.0, grade=param_dec_devs["HP"]["grade"])
            cop55 = _cop_safe(Te=T_e[t], Ts=55.0, grade=param_dec_devs["HP"]["grade"])

            model.addConstr(
                heat_mode["HP35"][n][t] == power_mode["HP35"][n][t] * cop35,
                name=f"Conv_HP35_{n}_{t}"
            )
            model.addConstr(
                heat_mode["HP55"][n][t] == power_mode["HP55"][n][t] * cop55,
                name=f"Conv_HP55_{n}_{t}"
)

            # Electric heater split
            model.addConstr(heat_dom["EH"][n][t] + dhw_dom["EH"][n][t] == power_dom["EH"][n][t],
                            name=f"EH_heat_power_dhw_balance_{n}_{t}")

    # Storage limits & efficiencies
    BIGM = 1e7
    for n in range(nb):
        for t in time_steps:
            # Charge/discharge power caps
            for dev in ecs_storage:
                cap = buildingData[n]["capacities"][dev]
                model.addConstr(ch_dom[dev][n][t]  <= cap * param_dec_devs[dev]["coeff_ch"],
                                name=f"max_ch_{dev}_{n}_{t}")
                model.addConstr(dch_dom[dev][n][t] <= cap * param_dec_devs[dev]["coeff_ch"],
                                name=f"max_dch_{dev}_{n}_{t}")
                # SOC bounds
                model.addConstr(soc_dom[dev][n][t] <= param_dec_devs[dev]["soc_max"] * cap,
                                name=f"soc_max_{dev}_{n}_{t}")
                model.addConstr(soc_dom[dev][n][t] >= param_dec_devs[dev]["soc_min"] * cap,
                                name=f"soc_min_{dev}_{n}_{t}")

            # TES energy balance (all heat goes to TES; demand bedient aus TES + heat import)
            if t == 0:
                soc_prev_tes = soc_init["TES"][n]
            else:
                soc_prev_tes = soc_dom["TES"][n][t-1]

            model.addConstr(
                soc_dom["TES"][n][t] ==
                soc_prev_tes * param_dec_devs["TES"]["eta_standby"]
                + (ch_dom["TES"][n][t] * param_dec_devs["TES"]["eta_ch"]
                   - dch_dom["TES"][n][t] / param_dec_devs["TES"]["eta_ch"]) * dt,
                name=f"TES_balance_{n}_{t}"
            )

            # All available heat is charged to TES
            model.addConstr(
                ch_dom["TES"][n][t] ==
                heat_dom["HP"][n][t] + heat_dom["EH"][n][t] + dhw_dom["EH"][n][t] + heat_dom["STC"][n][t],
                name=f"TES_charging_{n}_{t}"
            )

            # BAT energy balance
            if t == 0:
                soc_prev_bat = soc_init["BAT"][n]
            else:
                soc_prev_bat = soc_dom["BAT"][n][t-1]

            model.addConstr(
                soc_dom["BAT"][n][t] ==
                soc_prev_bat * param_dec_devs["BAT"]["eta_standby"]
                + (ch_dom["BAT"][n][t] * param_dec_devs["BAT"]["eta_ch"]
                   - dch_dom["BAT"][n][t] / param_dec_devs["BAT"]["eta_ch"]) * dt,
                name=f"BAT_balance_{n}_{t}"
            )

            # No simultaneous charge & discharge for BAT
            model.addConstr(dch_dom["BAT"][n][t] <= binary["BAT"][n][t] * BIGM, name=f"BAT_bin1_{n}_{t}")
            model.addConstr(ch_dom["BAT"][n][t]  <= (1 - binary["BAT"][n][t]) * BIGM, name=f"BAT_bin2_{n}_{t}")

    # Net heat import definition & heat link capacities
    for i in range(nb):
        for t in time_steps:
            inflow  = gp.quicksum(heat_connection[j][i][t] for j in range(nb) if j != i)
            outflow = gp.quicksum(heat_connection[i][j][t] for j in range(nb) if j != i)
            model.addConstr(net_heat_import[i][t] == inflow - outflow, name=f"net_heat_n{i}_t{t}")

        for j in range(nb):
            if i == j: 
                continue
            for t in time_steps:
                model.addConstr(heat_connection[i][j][t] <= heat_link_cap[i][j],
                                name=f"heat_link_cap_{i}_{j}_{t}")

    # Residual per-building: either import or feed electricity
    for n in range(nb):
        for t in time_steps:
            model.addConstr(res_dom["power"][n][t] <= binary["HLINE"][n][t] * BIGM, name=f"HLINE_bin1_{n}_{t}")
            model.addConstr(res_dom["feed"][n][t]  <= (1 - binary["HLINE"][n][t]) * BIGM, name=f"HLINE_bin2_{n}_{t}")

    # Building electricity balance
    for n in range(nb):
        for t in time_steps:
            model.addConstr(
                res_dom["power"][n][t] + PV_gen[n][t] + dch_dom["BAT"][n][t]
                == elec_dem[n][t] + power_dom["HP"][n][t] + power_dom["EH"][n][t]
                   + ch_dom["BAT"][n][t] + res_dom["feed"][n][t],
                name=f"Elec_balance_n{n}_t{t}"
            )
            # Feed-in cannot exceed local PV + battery discharge
            model.addConstr(
                res_dom["feed"][n][t] <= PV_gen[n][t] + dch_dom["BAT"][n][t],
                name=f"Feed_cap_n{n}_t{t}"
            )

    # District electricity balance (GCP)
    for t in time_steps:
        model.addConstr(residual["power"][t] == gp.quicksum(res_dom["power"][n][t] for n in range(nb)),
                        name=f"res_power_{t}")
        model.addConstr(residual["feed"][t]  == gp.quicksum(res_dom["feed"][n][t]  for n in range(nb)),
                        name=f"res_feed_{t}")

        model.addConstr(power["from_grid"][t] + residual["feed"][t] ==
                        residual["power"][t] + power["to_grid"][t],
                        name=f"Elec_balance_district_{t}")

        model.addConstr(power["from_grid"][t] <= yTrafo[t] * BIGM, name=f"Trafo_bin1_{t}")
        model.addConstr(power["to_grid"][t]   <= (1 - yTrafo[t]) * BIGM, name=f"Trafo_bin2_{t}")

    # Heat demand covering (per building): from TES and heat net import
    for n in range(nb):
        for t in time_steps:
            model.addConstr(
                dch_dom["TES"][n][t] + net_heat_import[n][t] == Q_DHW[n][t] + Q_heating[n][t],
                name=f"Heat_demand_cover_{n}_{t}"
            )

    # Aggregations
    model.addConstr(from_grid_total_el == dt * gp.quicksum(power["from_grid"][t] for t in time_steps),
                    name="from_grid_total_el_def")
    model.addConstr(to_grid_total_el   == dt * gp.quicksum(power["to_grid"][t]   for t in time_steps),
                    name="to_grid_total_el_def")

    # Peaks per day (robust for arbitrary cluster lengths)
    import math
    steps_per_day = max(1, int(round(24 / timeData["timeResolution"])))
    num_steps = len(list(time_steps))
    num_days = max(1, math.ceil(num_steps / steps_per_day))

    daily_peak = {d: model.addVar(vtype="C", lb=-gp.GRB.INFINITY,
                                name=f"peak_network_load_d{d}")
                for d in range(num_days)}
    peaksum = model.addVar(vtype="C", lb=-gp.GRB.INFINITY, name="sum_peak_daily_network_load")

    for d in range(num_days):
        start = d * steps_per_day
        end   = min((d + 1) * steps_per_day, num_steps)
        idxs  = list(range(start, end))
        model.addConstr(daily_peak[d] == gp.max_([power["from_grid"][t] for t in idxs]),
                        name=f"daily_peak_{d}")

    model.addConstr(peaksum == gp.quicksum(daily_peak[d] for d in range(num_days)),
                    name="peaksum_def")


    # Objective selection
    model.addConstr(
        operational_costs == from_grid_total_el * ecoData["price_supply_el"]
                            - to_grid_total_el   * ecoData["revenue_feed_in_el"],
        name="Cost_total_def"
    )
    model.addConstr(
        co2_total == from_grid_total_el * ecoData["co2_el_grid"],
        name="Emission_total_def"
    )

    if model_param["optim_focus"] == 0:
        model.addConstr(obj == operational_costs + 1.0 * peaksum, name="obj_costs")
    else:
        model.addConstr(obj == co2_total + 1.0 * peaksum, name="obj_co2")

    # ---------------------------
    # Solve
    # ---------------------------
    t0 = time.time()
    model.optimize()
    runtime = time.time() - t0
    print("\n********************************************")
    print(f"Model run time: {runtime:.2f} s")
    print("********************************************\n")

    if model.status in (gp.GRB.Status.INFEASIBLE, gp.GRB.Status.INF_OR_UNBD):
        model.computeIIS()
        with open('errorfile.txt', 'w', encoding='utf-8') as f:
            f.write('The following constraint(s) cannot be satisfied:\n')
            for c in model.getConstrs():
                if c.IISConstr:
                    f.write(f'{c.constrName}\n')

    # ---------------------------
    # Collect results
    # ---------------------------
    results = {
        "from_grid_total_el": from_grid_total_el.X,
        "to_grid_total_el": to_grid_total_el.X,
        "P_dem_total": [residual["power"][t].X for t in time_steps],
        "P_inj_total": [residual["feed"][t].X for t in time_steps],
        "P_dem_gcp":   [power["from_grid"][t].X for t in time_steps],
        "P_inj_gcp":   [power["to_grid"][t].X for t in time_steps],
        "Cost_total": operational_costs.X,
        "Emission_total": co2_total.X,
        "peaksum": peaksum.X,
        "daily_peak": {int(d): daily_peak[d].X for d in daily_peak},
        "net_heat_import": {n: [net_heat_import[n][t].X for t in time_steps] for n in range(nb)},
        "heat_connection": {(i, j): [heat_connection[i][j][t].X for t in time_steps]
                            for i in range(nb) for j in range(nb) if i != j},
    }

    for n in range(nb):
        results[n] = {
            "res_load": [res_dom["power"][n][t].X for t in time_steps],
            "res_inj":  [res_dom["feed"][n][t].X  for t in time_steps]
        }
        for dev in ecs_heat:
            results[n][dev] = {"Q_th": [heat_dom[dev][n][t].X for t in time_steps]}
        for m in hp_modi:
            results[n][m] = {
                "Q_th": [heat_mode[m][n][t].X for t in time_steps],
                "P_el": [power_mode[m][n][t].X for t in time_steps]
            }
        for dev in ecs_power:
            results[n][dev] = {"P_el": [power_dom[dev][n][t].X for t in time_steps]}
        for dev in ecs_storage:
            results[n][dev] = {
                "ch":  [ch_dom[dev][n][t].X  for t in time_steps],
                "dch": [dch_dom[dev][n][t].X for t in time_steps],
                "soc": [soc_dom[dev][n][t].X for t in time_steps],
            }

    return results

# --- Runner: Run this file directly, loading your .env for FIWARE -------------
if __name__ == "__main__":
    import argparse, os, sys, json
    from pathlib import Path
    import importlib.util
    from types import SimpleNamespace
    import gurobipy as gp



    THIS_DIR = Path(__file__).resolve().parent
    os.chdir(THIS_DIR)  # stabile Relativpfade
    
        # VOR dem Laden aus BES_design:
    logs_dir = (THIS_DIR / "udp_optimizer" / "udp_optimizer" / "decentral_opti" / "data" / "logs")
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"[warn] konnte logs-verzeichnis nicht anlegen: {logs_dir} -> {e}")


    parser = argparse.ArgumentParser(description="Run decentralized optimization")
    parser.add_argument("--cluster", type=int, default=0, help="Cluster index (default: 0)")
    parser.add_argument("--out", type=str, default="results_decentral.json", help="Output JSON file")
    parser.add_argument("--env", type=str,
                        default=r"N:\Forschung\EBC0938_BMWK_AIX-Heat_DEQ\Students\hgo-jsc\MA_code\.env",
                        help="Path to .env with FIWARE credentials")
    parser.add_argument("--demo", action="store_true",
                        help="Force demo data (skip FIWARE even if .env loads).")
    args = parser.parse_args()

    # --- 1) .env laden (mit Fallback, falls python-dotenv fehlt) --------------
    def load_env_file(dotenv_path: Path):
        try:
            from dotenv import load_dotenv, find_dotenv
            load_dotenv(dotenv_path=str(dotenv_path), override=True)
            return True
        except Exception:
            # Minimaler Fallback-Parser (KEY=VALUE, unterstützt einfache "..."-Werte)
            if not dotenv_path.exists():
                return False
            for line in dotenv_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"): 
                    continue
                if "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("'").strip('"')
                # einfache ${VAR}-Expansion
                if "${" in val and "}" in val:
                    import re
                    def repl(m):
                        return os.environ.get(m.group(1), "")
                    val = re.sub(r"\$\{([^}]+)\}", lambda m: repl(m), val)
                os.environ[key] = val
            return True

    env_loaded = load_env_file(Path(args.env))
    if env_loaded:
        print(f"[env] loaded: {args.env}")
        # kurze Sichtprüfung
        print(f"[env] FIWARE_URL_LD={os.environ.get('FIWARE_URL_LD')}")
        print(f"[env] NGSI_VERSION={os.environ.get('NGSI_VERSION')}")
    else:
        print(f"[env] WARN: could not load .env at {args.env}")

    # --- 2) Datenquelle wählen -------------------------------------------------
    def build_demo_data(nb=2, T=24):
        time = {"clusterLength": float(T), "timeResolution": 1.0, "dataResolution": 1.0}
        ecoData = {"price_supply_el": 0.30/1000.0, "revenue_feed_in_el": 0.08/1000.0, "co2_el_grid": 0.40/1000.0}
        site = {"T_e_cluster": {0: [0.0]*T}}
        decentral_device_data = {
            "HP":  {"grade": 0.45},
            "TES": {"eta_ch": 0.98, "eta_standby": 0.999,  "coeff_ch": 0.5, "soc_min": 0.05, "soc_max": 1.0},
            "BAT": {"eta_ch": 0.95, "eta_standby": 0.9995, "coeff_ch": 1.0, "soc_min": 0.05, "soc_max": 1.0},
        }
        def flat(v): return [float(v)]*T
        district = []
        for n in range(nb):
            year = 2000 if n % 2 else 1990
            user = SimpleNamespace(heat_cluster={0: flat(3000)}, dhw_cluster={0: flat(500)}, elec_cluster={0: flat(400)})
            capacities = {"HP": 6000.0, "EH": 8000.0, "BAT": 5000.0, "TES": 20000.0,
                          "PV": {"area": 0.0}, "STC": {"area": 0.0}}
            district.append({"gmlId": f"B{n}",
                             "envelope": SimpleNamespace(construction_year=year),
                             "user": user,
                             "generationPV_cluster": {0: flat(0.0)},
                             "generationSTC_cluster": {0: flat(0.0)},
                             "capacities": capacities})
        heat_link_cap = [[0.0]*nb for _ in range(nb)]
        if nb >= 2:
            heat_link_cap[0][1] = 3000.0
            heat_link_cap[1][0] = 3000.0
        return SimpleNamespace(time=time, ecoData=ecoData, site=site,
                               decentral_device_data=decentral_device_data,
                               params_ehdo_model={"optim_focus": 0},
                               district=district, heat_link_cap=heat_link_cap)

    def load_data_via_bes_design():
        # Besorge BES_design.py aus deinem Repo (relativ & absolut)
        candidates = [
            THIS_DIR / "udp_optimizer" / "udp_optimizer" / "BES_design.py",
            Path(r"N:\Forschung\EBC0938_BMWK_AIX-Heat_DEQ\Students\hgo-jsc\MA_code\udp_optimizer\udp_optimizer\BES_design.py"),
        ]
        for p in candidates:
            if p.exists():
                spec = importlib.util.spec_from_file_location("BES_design_local", str(p))
                mod = importlib.util.module_from_spec(spec)
                assert spec.loader is not None
                spec.loader.exec_module(mod)
                if hasattr(mod, "calc_bes_scenario"):
                    return mod.calc_bes_scenario()
        raise RuntimeError("BES_design.py not found or has no calc_bes_scenario().")

    if args.demo:
        data = build_demo_data()
        print("[data] Using DEMO data (skipping FIWARE).")
    else:
        try:
            data = load_data_via_bes_design()
            print("[data] Loaded via BES_design.calc_bes_scenario()")
        except Exception as e:
            print(f"[data] WARN: FIWARE/BES_design failed → {e}\n       Falling back to DEMO.")
            data = build_demo_data()

    # --- 3) Optimieren --------------------------------------------------------
    model = gp.Model("decentral_op")
    results = run_opti_decentral(model, data, cluster=args.cluster)

    # Tuple-Keys serialisierbar machen
    to_save = dict(results)
    if "heat_connection" in to_save:
        to_save["heat_connection"] = {f"{i}-{j}": v for (i, j), v in to_save["heat_connection"].items()}

    out_path = THIS_DIR / args.out
    out_path.write_text(json.dumps(to_save, indent=2), encoding="utf-8")

    print("\n=== Decentral Optimization finished ===")
    print(f"Cluster: {args.cluster}")
    if "Cost_total" in results: print(f"Total cost: {results['Cost_total']:.3f}")
    if "Emission_total" in results: print(f"Total CO2:  {results['Emission_total']:.3f}")
    print(f"Saved results to: {out_path}\n")
