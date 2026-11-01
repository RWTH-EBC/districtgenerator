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

# Anlagendaten: vor wissenschaftlicher Bewertung kalibrieren!
WH_HP_INV_EUR_PER_KW = 1110.0  # Ausgangsannahme wie zentrale HP
WH_HP_LIFE_YEARS = 20
WH_HP_OM_FRACTION = 0.033
WH_HP_TEST_FIXED_KW = None


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
        'hp_fixed_max_kw': ind['hp_fixed_max_kw']}


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
        'hp_fixed_max_kw': ind['hp_fixed_max_kw']}


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
    model.wh_gross = pyo.Expression(model.t, rule=lambda m,t: sum(
        m.wh_direct[s,t]+m.wh_hp[s,t] for s in m.wh_sources))
    model.wh_constraints = pyo.ConstraintList()
    capacity_kw = _cap_limit(ind)
    designed = getattr(data, 'centralDevices', {}).get('capacities', {}).get('industry_hp_capacity_kW')
    if designed is not None:
        capacity_kw = min(capacity_kw, float(designed))
    for t in model.t:
        maxgross = float((ind['direct_max'][:,t]+ind['hp_max'][:,t]).sum()) * 1000
        maxgross = min(maxgross, max(0., float(ind['demand_cap'][t]))*1000)
        model.wh_constraints.add(model.wh_gross[t] <= maxgross * model.wh_on[t])
        model.wh_constraints.add(model.wh_net[t] == model.wh_gross[t]
                                 - float(ind['nominal_loss'][t])*1000*model.wh_on[t])
        model.wh_constraints.add(sum(model.wh_hp[s,t] for s in model.wh_sources) <= capacity_kw * 1000)
        for s in model.wh_sources:
            model.wh_constraints.add(model.wh_direct[s,t] <= float(ind['direct_max'][s,t])*1000)
            model.wh_constraints.add(model.wh_hp[s,t] <= float(ind['hp_max'][s,t])*1000)
            model.wh_constraints.add(model.wh_direct[s,t] + model.wh_hp[s,t] *
                                     (1-float(ind['hp_el_frac'][s,t])) <= float(ind['source_input'][s,t])*1000)
            if ind['mode'] == 'forced':
                model.wh_direct[s,t].fix(float(ind['forced_direct'][s,t])*1000)
                model.wh_hp[s,t].fix(float(ind['forced_hp'][s,t])*1000)
        if ind['mode'] == 'forced':
            model.wh_on[t].fix(int(float(ind['forced_direct'][:,t].sum()+ind['forced_hp'][:,t].sum()) > 1e-8))
    model.wh_base_loss_W = pyo.Param(model.t, initialize=lambda m,t: float(ind['base_losses'][t])*1000)
    return ind


def operating_result(model):
    if not hasattr(model, 'wh_sources'):
        return None
    import pyomo.environ as pyo
    return {
        'direct_W': [[float(pyo.value(model.wh_direct[s,t])) for t in model.t] for s in model.wh_sources],
        'hp_output_W': [[float(pyo.value(model.wh_hp[s,t])) for t in model.t] for s in model.wh_sources],
        'gross_W': [float(pyo.value(model.wh_gross[t])) for t in model.t],
        'net_W': [float(pyo.value(model.wh_net[t])) for t in model.t],
        'hp_electric_W': [float(pyo.value(model.wh_hp_el[t])) for t in model.t],
        'connection_loss_W': [float(pyo.value(model.wh_gross[t])) -
                              float(pyo.value(model.wh_net[t])) for t in model.t],
    }


def add_design_source(model, data, param, steps):
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
    model.wh_hp_el = pyo.Expression(model.support_years, model.clusters, model.time_steps,
                                    rule=lambda m,y,d,t: sum(m.wh_hp[s,y,d,t]*float(ind['hp_el_frac'][s,d,t]) for s in m.wh_sources))
    model.wh_gross = pyo.Expression(model.support_years, model.clusters, model.time_steps,
                                    rule=lambda m,y,d,t: sum(m.wh_direct[s,y,d,t]+m.wh_hp[s,y,d,t] for s in m.wh_sources))
    model.wh_constraints = pyo.ConstraintList()
    for y in model.support_years:
        for d in model.clusters:
            for t in model.time_steps:
                maxgross = float((ind['direct_max'][:,d,t]+ind['hp_max'][:,d,t]).sum())
                maxgross = min(maxgross, max(0.,float(ind['demand_cap'][d,t])))
                model.wh_constraints.add(model.wh_gross[y,d,t] <= maxgross * model.wh_on[y,d,t])
                model.wh_constraints.add(model.wh_net[y,d,t] == model.wh_gross[y,d,t]
                                         - float(ind['nominal_loss'][d,t])*model.wh_on[y,d,t])
                model.wh_constraints.add(sum(model.wh_hp[s,y,d,t] for s in model.wh_sources) <= model.wh_hp_cap)
                for s in model.wh_sources:
                    model.wh_constraints.add(model.wh_direct[s,y,d,t] <= float(ind['direct_max'][s,d,t]))
                    model.wh_constraints.add(model.wh_hp[s,y,d,t] <= float(ind['hp_max'][s,d,t]))
                    model.wh_constraints.add(model.wh_direct[s,y,d,t] + model.wh_hp[s,y,d,t] *
                                             (1-float(ind['hp_el_frac'][s,d,t])) <= float(ind['source_input'][s,d,t]))
                    if ind['mode'] == 'forced':
                        model.wh_direct[s,y,d,t].fix(float(ind['forced_direct'][s,d,t]))
                        model.wh_hp[s,y,d,t].fix(float(ind['forced_hp'][s,d,t]))
                if ind['mode'] == 'forced':
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
    # Lebenszyklusannahme analog zentralem HP-Parameter – einfache Annuity.
    i = float(param['interest_rate'])
    if i < 0:
        raise ValueError('Zinssatz fuer Industrie-WP darf nicht negativ sein')
    crf = (i*(1+i)**WH_HP_LIFE_YEARS/((1+i)**WH_HP_LIFE_YEARS-1)) if i else 1/WH_HP_LIFE_YEARS
    model.wh_annual_capex = pyo.Expression(expr=model.wh_hp_cap * WH_HP_INV_EUR_PER_KW * (crf+WH_HP_OM_FRACTION))
    return ind