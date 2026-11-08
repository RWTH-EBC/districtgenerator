# -*- coding: utf-8 -*-
"""Optionale WH1-Erweiterung für 2-Leiter-EHDO/Pyomo.

Diese Datei wird AUSSCHLIESSLICH bei generation == '4G' und einem
Industrienetzlauf aktiviert. Bestehendes 2-Leiter-Modell und 5G bleiben
unveraendert. Leistungseinheiten: Netz kW, EHDO kW, opti_central W.

Annahmen: 8760 1h-Werte;
Industrie-WP elektrisch innerhalb der EH-Strombilanz. WH-Leitung bei
Nullfluss abgesperrt, bei Aktivitaet konstanter quasistationaerer Verlust.
"""
from pathlib import Path
import numpy as np
from districtgenerator.functions import heating_network_2leiter as single_network

# Anlagendaten: vor wissenschaftlicher Bewertung kalibrieren!
# Industrie-HX: Preise je Quelltyp Q1–Q6; None = bestehende
# Gebaeude-Uebergabestation (heat_grid_data: C_subst, ...).
HX_INV_EUR_PER_KW_BY_Q = {
    "Q1": 250.0,
    "Q2": 250.0,
    "Q3": 250.0,
    "Q4": 250.0,
    "Q5": 250.0,
    "Q6": 250.0,
    "Q7": 250.0,
}

HX_OM_EUR_PER_UNIT_YEAR_BY_Q = {
    "Q1": 1000.0,
    "Q2": 1000.0,
    "Q3": 1000.0,
    "Q4": 1000.0,
    "Q5": 1000.0,
    "Q6": 1000.0,
    "Q7": 1000.0,
}

HX_LIFETIME_YEARS_BY_Q = {
    'Q1': 20, 'Q2': 20, 'Q3': 20,
    'Q4': 20, 'Q5': 20, 'Q6': 20, 'Q7': 20,
}

#Wärmepumpen Werte
WH_HP_INV_EUR_PER_KW = 1110.0  # Ausgangsannahme wie zentrale HP
WH_HP_LIFE_YEARS = 20
WH_HP_OM_FRACTION = 0.033
WH_HP_TEST_FIXED_KW = None

# Industrie-TES: eigene Auslegungsgrenze; Kosten/Verluste werden
# aus dem bereits vorhandenen zentralen TES-Datensatz übernommen.
INDUSTRY_TES_MAX_ENERGY_KWH = 5000.0
INDUSTRY_TES_FULL_CHARGE_H = 2.0  # P_max = E_inst / 2 h
INDUSTRY_TES_ETA_CH = 0.98
INDUSTRY_TES_ETA_DCH = 0.98


def _industry_tes_enabled(data):
    return bool(getattr(data, 'heat_grid_data', {}).get('industrial_tes_enabled', False))


def _tes_check_parameters(loss):
    if not (0 <= float(loss) < 1):
        raise ValueError('Industrie-TES: Speicherverlust muss zwischen 0 und 1 liegen')
    if INDUSTRY_TES_MAX_ENERGY_KWH <= 0 or INDUSTRY_TES_FULL_CHARGE_H <= 0:
        raise ValueError('Industrie-TES: positive Kapazitaets- und Leistungsgrenze erforderlich')
    if not (0 < INDUSTRY_TES_ETA_CH <= 1 and 0 < INDUSTRY_TES_ETA_DCH <= 1):
        raise ValueError('Industrie-TES: ungueltige Lade-/Entladewirkungsgrade')


def _tes_design_variables(model, data, devs):
    if not _industry_tes_enabled(data):
        return False
    import pyomo.environ as pyo
    tes = devs['TES']  # gleicher Kostendatensatz wie zentraler TES
    loss = float(tes['sto_loss'])
    _tes_check_parameters(loss)
    model.wh_tes_loss = loss
    model.wh_tes_inv_var = float(tes['inv_var'])
    model.wh_tes_inv_base = float(tes['inv_base'])
    model.wh_tes_ann_factor = float(tes['ann_factor'])
    model.wh_tes_om_fraction = float(tes['cost_om'])
    for value in (model.wh_tes_inv_var, model.wh_tes_inv_base,
                  model.wh_tes_ann_factor, model.wh_tes_om_fraction):
        if not np.isfinite(value) or value < 0:
            raise ValueError('Industrie-TES: ungueltige TES-Kostenparameter')
    model.wh_tes_capacity = pyo.Var(within=pyo.NonNegativeReals,
                                    bounds=(0.0, INDUSTRY_TES_MAX_ENERGY_KWH))
    idx = (model.support_years, model.clusters, model.time_steps)
    model.wh_tes_charge = pyo.Var(*idx, within=pyo.NonNegativeReals)  # kW
    model.wh_tes_discharge = pyo.Var(*idx, within=pyo.NonNegativeReals)  # kW
    model.wh_tes_soc = pyo.Var(*idx, within=pyo.NonNegativeReals)  # kWh
    model.wh_tes_mode = pyo.Var(*idx, within=pyo.Binary)
    model.wh_tes_annual_cost = pyo.Expression(expr=model.wh_tes_capacity * (
            model.wh_tes_inv_var * model.wh_tes_ann_factor
            + model.wh_tes_inv_base * model.wh_tes_om_fraction))
    return True


def _tes_design_constraints(model, data):
    if not hasattr(model, 'wh_tes_capacity'):
        return
    dt = float(data.time['timeResolution']) / 3600.0
    if abs(dt - 1.0) > 1e-12:
        raise NotImplementedError('Industrie-TES: aktuell 1-h-Zeitschritte')
    rate_max = INDUSTRY_TES_MAX_ENERGY_KWH / INDUSTRY_TES_FULL_CHARGE_H
    for y in model.support_years:
        for d in model.clusters:
            ts = list(model.time_steps)
            for i, t in enumerate(ts):
                ix = y, d, t
                prev = ts[i-1] if i else ts[-1]
                model.wh_constraints.add(model.wh_tes_soc[ix] <= model.wh_tes_capacity)
                model.wh_constraints.add(model.wh_tes_charge[ix] <=
                                         model.wh_tes_capacity / INDUSTRY_TES_FULL_CHARGE_H)
                model.wh_constraints.add(model.wh_tes_discharge[ix] <=
                                         model.wh_tes_capacity / INDUSTRY_TES_FULL_CHARGE_H)
                model.wh_constraints.add(model.wh_tes_charge[ix] <= rate_max * model.wh_tes_mode[ix])
                model.wh_constraints.add(model.wh_tes_discharge[ix] <= rate_max * (1-model.wh_tes_mode[ix]))
                model.wh_constraints.add(
                    model.wh_tes_soc[ix] ==
                    (1-model.wh_tes_loss)**dt * model.wh_tes_soc[y,d,prev]
                    + (INDUSTRY_TES_ETA_CH*model.wh_tes_charge[ix]
                       - model.wh_tes_discharge[ix]/INDUSTRY_TES_ETA_DCH) * dt)
    # Anfang und Ende jeder repraesentativen Woche zyklisch verbunden:
    # keine fiktiven Verschiebungen zwischen nicht zusammenhaengenden Wochen.


def _tes_operating_variables(model, data):
    if not _industry_tes_enabled(data):
        return False
    import pyomo.environ as pyo
    caps = getattr(data, 'centralDevices', {}).get('capacities', {})
    if 'industry_tes_capacity_kWh' not in caps or 'industry_tes_sto_loss' not in caps:
        raise ValueError('Industrie-TES: EHDO-Kapazitaet/Verlustdaten fehlen')
    e_kWh = float(caps['industry_tes_capacity_kWh'])
    loss = float(caps['industry_tes_sto_loss'])
    _tes_check_parameters(loss)
    if not np.isfinite(e_kWh) or e_kWh < -1e-8 or e_kWh > INDUSTRY_TES_MAX_ENERGY_KWH+1e-6:
        raise ValueError('Industrie-TES: ungueltige installierte Kapazitaet')
    model.wh_tes_installed_Wh = max(0.,e_kWh) * 1000.0
    model.wh_tes_loss = loss
    model.wh_tes_charge = pyo.Var(model.t, within=pyo.NonNegativeReals)  # W
    model.wh_tes_discharge = pyo.Var(model.t, within=pyo.NonNegativeReals)  # W
    model.wh_tes_soc = pyo.Var(model.t, within=pyo.NonNegativeReals)  # Wh
    model.wh_tes_mode = pyo.Var(model.t, within=pyo.Binary)
    return True


def _tes_operating_constraints(model, data):
    if not hasattr(model, 'wh_tes_installed_Wh'):
        return
    dt = float(data.time['timeResolution']) / 3600.0
    if abs(dt-1.0)>1e-12:
        raise NotImplementedError('Industrie-TES: aktuell 1-h-Zeitschritte')
    max_power_W = model.wh_tes_installed_Wh / INDUSTRY_TES_FULL_CHARGE_H
    ts = list(model.t)
    for i,t in enumerate(ts):
        prev = ts[i-1] if i else ts[-1]
        model.wh_constraints.add(model.wh_tes_soc[t] <= model.wh_tes_installed_Wh)
        model.wh_constraints.add(model.wh_tes_charge[t] <= max_power_W)
        model.wh_constraints.add(model.wh_tes_discharge[t] <= max_power_W)
        model.wh_constraints.add(model.wh_tes_charge[t] <= max_power_W * model.wh_tes_mode[t])
        model.wh_constraints.add(model.wh_tes_discharge[t] <= max_power_W * (1-model.wh_tes_mode[t]))
        model.wh_constraints.add(
            model.wh_tes_soc[t] == (1-model.wh_tes_loss)**dt * model.wh_tes_soc[prev]
            + (INDUSTRY_TES_ETA_CH*model.wh_tes_charge[t]
               - model.wh_tes_discharge[t]/INDUSTRY_TES_ETA_DCH)*dt)



def industry_hx_cost_parameters(q_code, heat_grid_data):
    """Einheitliche Kostenbasis wie die bisherigen Gebaeude-Uebergabestationen."""
    q_code = str(q_code).strip().upper()
    if q_code not in HX_INV_EUR_PER_KW_BY_Q:
        raise ValueError(
            f"Quellklasse {q_code!r} nicht in Q1-Q6 parametrisiert. "
            "Bitte diese Klasse explizit mit Kosten ergaenzen; keine kostenlose Einspeisung."
        )
    inv = HX_INV_EUR_PER_KW_BY_Q[q_code]
    om = HX_OM_EUR_PER_UNIT_YEAR_BY_Q[q_code]
    lifetime = HX_LIFETIME_YEARS_BY_Q[q_code]
    inv = heat_grid_data["C_subst"] if inv is None else inv
    om = heat_grid_data["cost_om_subst"] if om is None else om
    lifetime = heat_grid_data["lifetime_subst"] if lifetime is None else lifetime
    inv, om, lifetime = float(inv), float(om), int(lifetime)
    if not np.isfinite(inv) or not np.isfinite(om) or inv < 0 or om < 0 or lifetime <= 0:
        raise ValueError(f"Unzulaessige Waermeuebertragerkosten fuer {q_code}")
    return inv, om, lifetime


def enabled(data):
    h = getattr(data, 'heat_grid_data', {})
    return (h.get('heatgrid_generation') == '4G'
            and h.get('industrial_heat_mode') in ('direct_only', 'all_sources_hp')
            and h.get('industrial_dispatch_mode') in ('forced', 'optimizer'))


def load_industry_bridge(data):
    if not enabled(data):
        data.industry_optimization = None
        return None
    folder = Path(data.resultPath) / 'network' / (f'{data.scenario_name}_road_2leiter_industrie')
    bounds = folder / 'industrie_quellen_optimierer_grenzen_8760.npz'
    operated = folder / 'industrie_mehrquellen_zeitreihen_8760.npz'
    if not bounds.is_file() or not operated.is_file():
        raise FileNotFoundError('WH1-Optimierung: benoetigte Netzwerk-NPZ fehlt: ' + str(folder))
    with np.load(bounds, allow_pickle=False) as f:
        b = {k: np.asarray(f[k], dtype=float) for k in f.files}
    with np.load(operated, allow_pickle=False) as f:
        o = {k: np.asarray(f[k], dtype=float) for k in f.files}
    sh = b['source_input_kW'].shape
    if len(sh) != 2 or sh[1] != 8760 or sh[0] == 0:
        raise ValueError('WH1: Quellenprofil muss (n_quellen, 8760) sein')
    # Die Obergrenze fuer die Industrie-WP muss eine gueltige 8760h-Zeitreihe sein.
    demand_cap = np.asarray(b['demand_massflow_cap_kW'], dtype=float)
    if (demand_cap.shape != (8760,)
            or not np.isfinite(demand_cap).all()
            or np.any(demand_cap < 0.0)):
        raise ValueError('WH1: ungueltige 8760h-Quartiersabnahmegrenze')
    for k in ('direct_max_kW', 'hp_max_kW', 'hp_electric_per_output'):
        if b[k].shape != sh or not np.isfinite(b[k]).all() or (b[k] < 0).any():
            raise ValueError('WH1: ungueltige technische Quelle: ' + k)
    if (b['hp_electric_per_output'] >= 1).any():
        raise ValueError('WH1: HP-Elektrizitaetsanteil muss kleiner als 1 sein')
    required = ('industrial_direct_by_source_kW', 'industrial_hp_by_source_kW')
    for k in required:
        if o[k].shape != sh:
            raise ValueError('WH1: falsche Matrixform: ' + k)
    loss = np.asarray(data.heat_grid_data.get('industrial_connection_nominal_loss_kW'), dtype=float)
    if loss.shape != (8760,) or not np.isfinite(loss).all():
        raise ValueError('WH1: Industrie-Netzmodell muss nominale Anschlussleitungsverluste exportieren')
    total_losses = np.asarray(data.heat_grid_data['total_losses_heating_network'], dtype=float)
    active_losses = np.asarray(data.heat_grid_data['industrial_connection_heat_loss_kW'], dtype=float)
    if total_losses.shape != (8760,) or active_losses.shape != (8760,):
        raise ValueError('WH1: Netzverluste muessen 8760 Werte umfassen')
    base_losses = total_losses - active_losses
    if (base_losses < -1e-6).any():
        raise ValueError('WH1: negative Basis-Netzverluste')
    cap_raw = np.ravel(b.get('hp_max_output_kw', np.array([np.nan])))[0]
    hp_cap = None if np.isnan(cap_raw) else float(cap_raw)
    hx_keys = (
        'hx_factor_kW_per_kW', 'hx_max_design_capacity_kW',
        'hx_UA_W_K_per_kW', 'hx_q_number',
    )
    missing_hx = [k for k in hx_keys if k not in b]
    if missing_hx:
        raise ValueError(f'WH1-HX: NPZ ohne neue Parameter: {missing_hx}')
    if b['hx_factor_kW_per_kW'].shape != sh:
        raise ValueError('WH1-HX: Faktorenform muss (Quellen,8760) sein')
    if any(b[k].shape != (sh[0],) for k in hx_keys[1:]):
        raise ValueError('WH1-HX: statische Parameter pro Quelle erwartet')
    if not np.isfinite(b['hx_factor_kW_per_kW']).all() or (b['hx_factor_kW_per_kW'] < 0).any():
        raise ValueError('WH1-HX: ungueltige LMTD-Faktoren')
    data.industry_optimization = {
        'mode': data.heat_grid_data['industrial_dispatch_mode'],
        'heat_mode': data.heat_grid_data['industrial_heat_mode'],
        'source_input': b['source_input_kW'],
        'direct_max': b['direct_max_kW'],
        'hp_max': b['hp_max_kW'],
        'hp_el_frac': b['hp_electric_per_output'],
        'demand_cap': np.asarray(b['demand_massflow_cap_kW'], dtype=float),
        'forced_direct': o['industrial_direct_by_source_kW'],
        'forced_hp': o['industrial_hp_by_source_kW'],
        'nominal_loss': np.maximum(loss, 0.0),
        'base_losses': np.maximum(base_losses, 0.0),
        'hp_fixed_max_kw': hp_cap,
        'hx_factor': b['hx_factor_kW_per_kW'],
        'hx_static': {
            'cap_upper': b['hx_max_design_capacity_kW'],
            'ua_per_kw': b['hx_UA_W_K_per_kW'],
            'q_num': b['hx_q_number'],
        },
    }
    print(f'[WH1-OPT] {sh[0]} Quellen geladen; Modus={data.industry_optimization["mode"]}.')
    return data.industry_optimization


def _bridge(data):
    if not enabled(data):
        return None
    return getattr(data, 'industry_optimization', None) or load_industry_bridge(data)


def _week(data, original_index, steps):
    if int(data.time['timeResolution']) != 3600:
        raise NotImplementedError('WH1: bislang nur Stundenraster (3600 s)')
    offset = int(original_index) * int(steps)
    if offset < 0 or offset + steps > 8760:
        raise IndexError('WH1: repraesentatives Zeitfenster ausserhalb der 8760 Stunden')
    return slice(offset, offset + int(steps))


def operating_window(data, cluster, steps):
    ind = _bridge(data)
    if ind is None:
        return None
    # Bei cm.cluster sind die aktivierten Originalintervalle in data.clusters
    # aufsteigend sortiert und korrespondieren den Zeilen der Clusterprofile.
    selected = getattr(data, 'clusters', [])
    if len(selected) != int(data.time['clusterNumber']):
        raise RuntimeError('WH1: Anzahl repraesentativer Cluster stimmt nicht')
    sl = _week(data, selected[int(cluster)], steps)
    return {k: (v[:, sl] if np.asarray(v).ndim == 2 else v[sl])
            for k, v in ind.items() if isinstance(v, np.ndarray)} | {
        'mode': ind['mode'], 'heat_mode': ind['heat_mode'],
        'hp_fixed_max_kw': ind['hp_fixed_max_kw'],
        'hx_static': ind['hx_static']}


def design_windows(data, param, steps):
    ind = _bridge(data)
    if ind is None:
        return None
    reps = [int(x) for x in param['typedays']]
    if len(reps) != int(data.time['clusterNumber']):
        raise ValueError('WH1: EHDO-Cluster repraesentieren nicht die erwarteten Wochen')
    sl = [_week(data, i, steps) for i in reps]
    windows = {}
    for k, v in ind.items():
        if not isinstance(v, np.ndarray):
            continue
        # Quellenmatrizen -> (n_quellen, n_cluster, n_stunden),
        # skalare Zeitprofile -> (n_cluster, n_stunden).
        if v.ndim == 2:
            windows[k] = np.stack([v[:, s] for s in sl], axis=1)
        elif v.ndim == 1:
            windows[k] = np.stack([v[s] for s in sl], axis=0)
        else:
            raise ValueError('WH1: nicht unterstuetzte Datenmatrix ' + k)
    return windows | {
        'mode': ind['mode'], 'heat_mode': ind['heat_mode'],
        'hp_fixed_max_kw': ind['hp_fixed_max_kw'],
        'hx_static': ind['hx_static']}


def _cap_limit(ind):
    """Maximale thermische WP-Ausgangsleistung in kW.

    Minimum aus Industrie-Spitzenangebot, maximaler abnehmbarer
    Quartierswaermeleistung und einer optionalen Benutzergrenze.
    Dies ist eine OBERGRENZE, keine vorweggenommene Auslegungsentscheidung.
    """
    hp_max = np.asarray(ind['hp_max'], dtype=float)
    demand_cap = np.asarray(ind['demand_cap'], dtype=float)
    if hp_max.ndim != 2 or demand_cap.ndim != 1:
        raise ValueError('WH1: ungueltige Dimensionen fuer WP-Leistungsgrenze')
    if (not np.isfinite(hp_max).all() or not np.isfinite(demand_cap).all()
            or np.any(hp_max < 0) or np.any(demand_cap < 0)):
        raise ValueError('WH1: ungueltige Werte fuer WP-Leistungsgrenze')

    industry_peak_kw = float(np.max(hp_max.sum(axis=0)))
    district_peak_kw = float(np.max(demand_cap))
    upper_kw = min(industry_peak_kw, district_peak_kw)

    preset_kw = ind.get('hp_fixed_max_kw')
    if preset_kw is not None:
        preset_kw = float(preset_kw)
        if not np.isfinite(preset_kw) or preset_kw < 0:
            raise ValueError('WH1: WP-Leistungspreset muss endlich und >= 0 sein')
        upper_kw = min(upper_kw, preset_kw)
    return max(0.0, upper_kw)


def add_operational_source(model, data, cluster, steps):
    """Pyomo-Variablen in W fuer eine Betriebs-Clusterwoche.

    Aufruf NACH der Erstellung von model.t, VOR den Netzbilanzen.
    """
    ind = operating_window(data, cluster, steps)
    if ind is None:
        return None
    import pyomo.environ as pyo
    source_count = ind['source_input'].shape[0]
    model.wh_sources = pyo.RangeSet(0, source_count-1)
    model.wh_direct = pyo.Var(model.wh_sources, model.t, within=pyo.NonNegativeReals)
    model.wh_hp = pyo.Var(model.wh_sources, model.t, within=pyo.NonNegativeReals)
    model.wh_on = pyo.Var(model.t, within=pyo.Binary)
    model.wh_net = pyo.Var(model.t, within=pyo.NonNegativeReals)
    model.wh_hp_el = pyo.Expression(model.t, rule=lambda m,t: sum(
        m.wh_hp[s,t] * float(ind['hp_el_frac'][s,t]) for s in m.wh_sources))
    tes_on = _tes_operating_variables(model, data)
    model.wh_gross = pyo.Expression(model.t, rule=lambda m,t:
    sum(m.wh_direct[s,t]+m.wh_hp[s,t] for s in m.wh_sources)
    - (m.wh_tes_charge[t]-m.wh_tes_discharge[t] if tes_on else 0))
    model.wh_constraints = pyo.ConstraintList()
    hx_caps = getattr(data, 'centralDevices', {}).get('capacities', {}).get(
        'industry_hx_capacities_kW'
    )
    if hx_caps is None:
        raise ValueError('WH1-HX: EHDO hat keine HX-Kapazitaeten uebergeben')
    hx_caps = np.asarray(hx_caps, dtype=float)
    if hx_caps.shape != (source_count,) or (hx_caps < 0).any():
        raise ValueError('WH1-HX: falsche Quelle-zu-Kapazitaet-Zuordnung')
    capacity_kw = _cap_limit(ind)
    designed = getattr(data, 'centralDevices', {}).get('capacities', {}).get('industry_hp_capacity_kW')
    if designed is not None:
        capacity_kw = min(capacity_kw, float(designed))
    for t in model.t:
        maxgross = max(0.,float(ind['demand_cap'][t]))*1000
        if not tes_on:
            maxgross = min(maxgross, float((ind['direct_max'][:,t]+ind['hp_max'][:,t]).sum())*1000)
        model.wh_constraints.add(model.wh_gross[t] <= maxgross * model.wh_on[t])
        model.wh_constraints.add(model.wh_net[t] == model.wh_gross[t]
                                 - float(ind['nominal_loss'][t])*1000*model.wh_on[t])
        model.wh_constraints.add(sum(model.wh_hp[s,t] for s in model.wh_sources) <= capacity_kw * 1000)
        for s in model.wh_sources:
            model.wh_constraints.add(model.wh_direct[s,t] <= float(ind['direct_max'][s,t])*1000)
            model.wh_constraints.add(model.wh_direct[s,t] <= float(ind['hx_factor'][s,t]) * float(hx_caps[int(s)]) * 1000.0)
            model.wh_constraints.add(model.wh_hp[s,t] <= float(ind['hp_max'][s,t])*1000)
            model.wh_constraints.add(model.wh_direct[s,t] + model.wh_hp[s,t] *
                                     (1-float(ind['hp_el_frac'][s,t])) <= float(ind['source_input'][s,t])*1000)
            if ind['mode'] == 'forced' and not tes_on:
                model.wh_direct[s,t].fix(float(ind['forced_direct'][s,t])*1000)
                model.wh_hp[s,t].fix(float(ind['forced_hp'][s,t])*1000)
        if ind['mode'] == 'forced':
            model.wh_on[t].fix(int(float(ind['forced_direct'][:,t].sum()+ind['forced_hp'][:,t].sum()) > 1e-8))
    _tes_operating_constraints(model, data)
    model.wh_base_loss_W = pyo.Param(model.t, initialize=lambda m,t: float(ind['base_losses'][t])*1000)
    return ind


def operating_result(model):
    if not hasattr(model, 'wh_sources'):
        return None
    import pyomo.environ as pyo
    result = {
        'direct_W': [[float(pyo.value(model.wh_direct[s,t])) for t in model.t] for s in model.wh_sources],
        'hp_output_W': [[float(pyo.value(model.wh_hp[s,t])) for t in model.t] for s in model.wh_sources],
        'gross_W': [float(pyo.value(model.wh_gross[t])) for t in model.t],
        'net_W': [float(pyo.value(model.wh_net[t])) for t in model.t],
        'hp_electric_W': [float(pyo.value(model.wh_hp_el[t])) for t in model.t],
        'connection_loss_W': [float(pyo.value(model.wh_gross[t])) -
                              float(pyo.value(model.wh_net[t])) for t in model.t],
    }
    if hasattr(model, 'wh_tes_soc'):
        result.update({
            'tes_charge_W': [float(pyo.value(model.wh_tes_charge[t])) for t in model.t],
            'tes_discharge_W': [float(pyo.value(model.wh_tes_discharge[t])) for t in model.t],
            'tes_soc_Wh': [float(pyo.value(model.wh_tes_soc[t])) for t in model.t],
        })
    return result


def add_design_source(model, data, param, steps, devs=None):
    """Pyomo-Variablen in kW fuer EHDO, auf param['typedays'] abgebildet."""
    ind = design_windows(data, param, steps)
    if ind is None:
        return None
    import pyomo.environ as pyo
    S = ind['source_input'].shape[0]
    model.wh_sources = pyo.RangeSet(0, S-1)
    model.wh_direct = pyo.Var(model.wh_sources, model.support_years, model.clusters,
                              model.time_steps, within=pyo.NonNegativeReals)
    model.wh_hp = pyo.Var(model.wh_sources, model.support_years, model.clusters,
                          model.time_steps, within=pyo.NonNegativeReals)
    model.wh_on = pyo.Var(model.support_years, model.clusters, model.time_steps,
                          within=pyo.Binary)
    model.wh_net = pyo.Var(model.support_years, model.clusters, model.time_steps,
                           within=pyo.NonNegativeReals)
    # Den Kapazitaetsdeckel aus dem VOLLSTAENDIGEN Jahr bestimmen, nicht nur
    # aus Repraesentanten. Sonst kann ein spaeterer Clusterlauf zu hoch liegen.
    full_ind = _bridge(data)
    model.wh_hp_cap = pyo.Var(within=pyo.NonNegativeReals,
                              bounds=(0, _cap_limit(full_ind)))
    if WH_HP_TEST_FIXED_KW is not None:
        fixed_kw = float(WH_HP_TEST_FIXED_KW)
        if not 0.0 <= fixed_kw <= _cap_limit(full_ind):
            raise ValueError('Industrie-WP-Testkapazitaet ausserhalb der Grenze')
        model.wh_hp_cap.fix(fixed_kw)

    hx_up = np.asarray(ind['hx_static']['cap_upper'], dtype=float)
    if hx_up.shape != (S,) or (hx_up < 0).any():
        raise ValueError("WH1-HX: ungueltige Auslegungskapazitaeten")
    # Jede Quelle erhaelt eine EIGENE investierbare HX-Nennleistung [kW].
    model.wh_hx_cap = pyo.Var(
        model.wh_sources, within=pyo.NonNegativeReals,
        bounds=lambda m, s: (0.0, float(hx_up[int(s)])),
    )
    # 1 = Kosten fuer einen installierten Quellwaermeuebertrager.
    model.wh_hx_built = pyo.Var(model.wh_sources, within=pyo.Binary)

    model.wh_hp_el = pyo.Expression(model.support_years, model.clusters, model.time_steps,
                                    rule=lambda m,y,d,t: sum(m.wh_hp[s,y,d,t]*float(ind['hp_el_frac'][s,d,t]) for s in m.wh_sources))
    if _industry_tes_enabled(data) and devs is None:
        raise ValueError('Industrie-TES: devs aus EHDO an die Bridge uebergeben')
    tes_on = _tes_design_variables(model, data, devs)
    model.wh_gross = pyo.Expression(model.support_years, model.clusters, model.time_steps,
                                    rule=lambda m,y,d,t:
                                    sum(m.wh_direct[s,y,d,t]+m.wh_hp[s,y,d,t] for s in m.wh_sources)
                                    - (m.wh_tes_charge[y,d,t]-m.wh_tes_discharge[y,d,t] if tes_on else 0))
    model.wh_constraints = pyo.ConstraintList()
    for s in model.wh_sources:
        model.wh_constraints.add(
            model.wh_hx_cap[s] <= float(hx_up[int(s)]) * model.wh_hx_built[s]
        )
        if float(hx_up[int(s)]) <= 1e-9:
            model.wh_hx_built[s].fix(0)

    for y in model.support_years:
        for d in model.clusters:
            for t in model.time_steps:
                maxgross = max(0.,float(ind['demand_cap'][d,t]))
                if not tes_on:
                    maxgross = min(maxgross, float((ind['direct_max'][:,d,t]+ind['hp_max'][:,d,t]).sum()))
                model.wh_constraints.add(model.wh_gross[y,d,t] <= maxgross * model.wh_on[y,d,t])
                model.wh_constraints.add(model.wh_net[y,d,t] == model.wh_gross[y,d,t]
                                         - float(ind['nominal_loss'][d,t])*model.wh_on[y,d,t])
                model.wh_constraints.add(sum(model.wh_hp[s,y,d,t] for s in model.wh_sources) <= model.wh_hp_cap)
                for s in model.wh_sources:
                    model.wh_constraints.add(model.wh_direct[s,y,d,t] <= float(ind['direct_max'][s,d,t]))
                    model.wh_constraints.add(model.wh_direct[s,y,d,t] <= float(ind['hx_factor'][s,d,t]) * model.wh_hx_cap[s])
                    model.wh_constraints.add(model.wh_hp[s,y,d,t] <= float(ind['hp_max'][s,d,t]))
                    model.wh_constraints.add(model.wh_direct[s,y,d,t] + model.wh_hp[s,y,d,t] *
                                             (1-float(ind['hp_el_frac'][s,d,t])) <= float(ind['source_input'][s,d,t]))
                    if ind['mode'] == 'forced':
                        model.wh_direct[s,y,d,t].fix(float(ind['forced_direct'][s,d,t]))
                        model.wh_hp[s,y,d,t].fix(float(ind['forced_hp'][s,d,t]))
                if ind['mode'] == 'forced' and not tes_on:
                    model.wh_on[y,d,t].fix(int(float(ind['forced_direct'][:,d,t].sum()+
                                                     ind['forced_hp'][:,d,t].sum()) > 1e-8))
    if ind['mode'] == 'forced':
        required_peak_kw = float(np.max(full_ind['forced_hp'].sum(axis=0)))
        permitted_peak_kw = _cap_limit(full_ind)
        if required_peak_kw > permitted_peak_kw + 1e-5:
            raise ValueError(
                'WH1: erzwungene WP-Spitze ueberschreitet Quartiers-/'
                f'Technikgrenze: {required_peak_kw:.3f} > '
                f'{permitted_peak_kw:.3f} kW. '
                'Bitte erzwungenes Netzprofil und WP-Preset abgleichen.'
            )
        model.wh_hp_cap.fix(required_peak_kw)
    _tes_design_constraints(model, data)


    if ind['mode'] == 'forced':
        for s in model.wh_sources:
            q = np.asarray(full_ind['forced_direct'][int(s)], dtype=float)
            fac = np.asarray(full_ind['hx_factor'][int(s)], dtype=float)
            if np.any((q > 1e-8) & (fac <= 1e-12)):
                raise ValueError("Erzwungene Direktwaerme ohne Waermeuebertrager")
            use = fac > 1e-12
            required = float(np.max(q[use] / fac[use])) if np.any(use) else 0.0
            if required > float(hx_up[int(s)]) + 1e-5:
                raise ValueError("Erzwungene HX-Leistung ausserhalb Auslegungsgrenze")
            model.wh_hx_cap[s].fix(required)
            model.wh_hx_built[s].fix(int(required > 1e-8))

    # Lebenszyklusannahme analog zentralem HP-Parameter – einfache Annuity.
    i = float(param['interest_rate'])
    if i < 0:
        raise ValueError('Zinssatz fuer Industrie-WP darf nicht negativ sein')
    crf = (i*(1+i)**WH_HP_LIFE_YEARS/((1+i)**WH_HP_LIFE_YEARS-1)) if i else 1/WH_HP_LIFE_YEARS
    model.wh_annual_capex = pyo.Expression(expr=model.wh_hp_cap * WH_HP_INV_EUR_PER_KW * (crf+WH_HP_OM_FRACTION))

    # Preis-/Annuitaetslogik WIE bei bestehenden Uebergabestationen:
    # Investition in EUR/kW, lebensdauerspezifischer Annuitaetsfaktor,
    # fester Wartungsbetrag pro installiertem Uebertrager.
    model.wh_hx_inv_per_kw = []
    model.wh_hx_om_per_year = []
    model.wh_hx_ann_factor = []
    model.wh_hx_q_codes = []
    for s in model.wh_sources:
        qcode = "Q" + str(int(ind['hx_static']['q_num'][int(s)]))
        if float(hx_up[int(s)]) > 0.0:
            inv, om, lifetime = industry_hx_cost_parameters(
                qcode, data.heat_grid_data
            )
            annual_factor = single_network.calc_annual_factor(data, lifetime)
        else:
            inv, om, annual_factor = 0.0, 0.0, 0.0
        model.wh_hx_q_codes.append(qcode)
        model.wh_hx_inv_per_kw.append(float(inv))
        model.wh_hx_om_per_year.append(float(om))
        model.wh_hx_ann_factor.append(float(annual_factor))

    model.wh_hx_annual_cost = pyo.Expression(expr=sum(
        model.wh_hx_cap[s]
        * model.wh_hx_inv_per_kw[int(s)]
        * model.wh_hx_ann_factor[int(s)]
        + model.wh_hx_built[s] * model.wh_hx_om_per_year[int(s)]
        for s in model.wh_sources
    ))

    return ind