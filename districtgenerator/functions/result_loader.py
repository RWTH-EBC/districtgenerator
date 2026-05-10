# -*- coding: utf-8 -*-
"""
result_loader.py — Helfer fuer die Auswertung der gespeicherten pkl-Dateien.

Workflow:
    from districtgenerator.functions.result_loader import (
        load_summary, load_timeseries, load_topology,
        reconstruct_8760, compute_supply_shares, compute_heat_density,
        get_run_keys, load_run,
    )

    runs = get_run_keys(results_dir)              # alle (scen, bm) Tripel
    s = load_summary(results_dir, "E02_bm", "waermecontracting")
    t = load_timeseries(results_dir, "E02_bm", "waermecontracting")

    # 8760-Rekonstruktion einer Cluster-Reihe (bzw. n*168 ~ 8760)
    full_year = reconstruct_8760(t["buildings"][year][cluster_idx]["BOI_Q_th"], t)
    # ... oder fuer ein ganzes dict:
    bldg_full = reconstruct_buildings_year(t, year=2025, building_name="...")

    # Versorgungsanteile pro Gebaeude
    shares = compute_supply_shares(t, year=2025)

    # Waermedichte (auch nachtraeglich aus summary)
    rho = compute_heat_density(s)
"""

import os
import glob
import pickle
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


# ══════════════════════════════════════════════════════════════════════
# DATEI-LADER
# ══════════════════════════════════════════════════════════════════════

def _load_pkl(filepath: str) -> Dict[str, Any]:
    with open(filepath, "rb") as f:
        return pickle.load(f)


def _build_path(results_dir: str, kind: str, scenario_name: str, business_model: str) -> str:
    """kind in {'summary','timeseries','topology'}."""
    return os.path.join(results_dir, f"{kind}_{scenario_name}_{business_model}.pkl")


def load_summary(results_dir: str, scenario_name: str, business_model: str) -> Dict[str, Any]:
    return _load_pkl(_build_path(results_dir, "summary", scenario_name, business_model))


def load_timeseries(results_dir: str, scenario_name: str, business_model: str) -> Dict[str, Any]:
    return _load_pkl(_build_path(results_dir, "timeseries", scenario_name, business_model))


def load_topology(results_dir: str, scenario_name: str, business_model: str) -> Optional[Dict[str, Any]]:
    fp = _build_path(results_dir, "topology", scenario_name, business_model)
    return _load_pkl(fp) if os.path.exists(fp) else None


def load_run(results_dir: str, scenario_name: str, business_model: str,
             with_timeseries: bool = True, with_topology: bool = True) -> Dict[str, Any]:
    """Laedt summary + ggf. timeseries + topology in ein dict."""
    out = {"summary": load_summary(results_dir, scenario_name, business_model)}
    if with_timeseries:
        try:
            out["timeseries"] = load_timeseries(results_dir, scenario_name, business_model)
        except FileNotFoundError:
            out["timeseries"] = None
    if with_topology:
        out["topology"] = load_topology(results_dir, scenario_name, business_model)
    return out


def get_run_keys(results_dir: str) -> List[Tuple[str, str]]:
    """Findet alle (scenario_name, business_model)-Paare anhand der summary-Dateien."""
    out = []
    for fp in sorted(glob.glob(os.path.join(results_dir, "summary_*.pkl"))):
        try:
            md = _load_pkl(fp).get("metadata", {})
            out.append((md.get("scenario_name"), md.get("business_model")))
        except Exception:
            continue
    return out


# ══════════════════════════════════════════════════════════════════════
# 8760-REKONSTRUKTION
# ══════════════════════════════════════════════════════════════════════

def _build_period_to_cluster(cluster_assignments: Dict[int, List[int]]) -> Dict[int, int]:
    """{period_index: cluster_index}."""
    p2c = {}
    for c, periods in cluster_assignments.items():
        for p in periods:
            p2c[int(p)] = int(c)
    return p2c


def reconstruct_8760(values_per_cluster: Dict[int, np.ndarray],
                     timeseries_or_meta: Dict[str, Any]) -> np.ndarray:
    """
    Rekonstruiert die volle Jahresreihe aus Cluster-Reihen.

    Parameters
    ----------
    values_per_cluster : {cluster_idx: array_per_cluster}
        Werte je Cluster (Laenge = time_steps_per_cluster).
    timeseries_or_meta : dict
        Entweder das geladene `timeseries`-Dict oder dessen `metadata`-Sub-Dict.

    Returns
    -------
    np.ndarray
        Geometrie: num_periods * time_steps_per_cluster.
        Bei clusterLength=604800s (Woche) und 52 Clustern → 52*168 = 8736 ≈ 8760.
    """
    md = timeseries_or_meta.get("metadata", timeseries_or_meta)
    cluster_assignments = md.get("clusterAssignments") \
        or timeseries_or_meta.get("metadata", {}).get("clusterAssignments", {})
    p2c = _build_period_to_cluster(cluster_assignments)
    num_periods = max(p2c.keys()) + 1 if p2c else 0
    if num_periods == 0:
        return np.array([])

    # Schrittlaenge je Cluster
    any_cluster = next(iter(values_per_cluster.values()))
    steps = len(any_cluster)
    out = np.zeros(num_periods * steps)

    for period in range(num_periods):
        c = p2c.get(period)
        if c is None or c not in values_per_cluster:
            continue
        out[period * steps:(period + 1) * steps] = values_per_cluster[c]

    return out


def reconstruct_buildings_year(timeseries: Dict[str, Any], year: int,
                                building_name: str) -> Dict[str, np.ndarray]:
    """
    Rekonstruiert ALLE Reihen eines Gebaeudes fuer ein Jahr auf 8760(-naehe).

    Returns: {key: full_year_array}
    """
    out = {}
    bldg_per_cluster = {}
    for cluster_idx, bldgs in timeseries["buildings"].get(year, {}).items():
        if building_name in bldgs:
            bldg_per_cluster[cluster_idx] = bldgs[building_name]

    if not bldg_per_cluster:
        return out

    # Schluessel-Vereinigung (manche Cluster haben evtl. nicht alle keys)
    keys = set()
    for bd in bldg_per_cluster.values():
        keys.update(k for k, v in bd.items() if isinstance(v, np.ndarray))

    for k in keys:
        per_cluster = {c: bd.get(k) for c, bd in bldg_per_cluster.items() if isinstance(bd.get(k), np.ndarray)}
        if per_cluster:
            out[k] = reconstruct_8760(per_cluster, timeseries)
    return out


def reconstruct_energy_hub_year(timeseries: Dict[str, Any], year: int) -> Dict[str, np.ndarray]:
    """Rekonstruiert alle EH-Reihen fuer ein Jahr auf 8760-naehe."""
    out = {}
    eh_per_cluster = timeseries["energy_hub"].get(year, {})
    if not eh_per_cluster:
        return out
    keys = set()
    for c_data in eh_per_cluster.values():
        keys.update(k for k, v in c_data.items() if isinstance(v, np.ndarray))
    for k in keys:
        per_cluster = {c: cd.get(k) for c, cd in eh_per_cluster.items() if isinstance(cd.get(k), np.ndarray)}
        if per_cluster:
            out[k] = reconstruct_8760(per_cluster, timeseries)
    return out


# ══════════════════════════════════════════════════════════════════════
# AGGREGATIONEN MIT CLUSTER-GEWICHTEN (ohne Rekonstruktion)
# ══════════════════════════════════════════════════════════════════════

def _cluster_weights(timeseries: Dict[str, Any]) -> Dict[int, int]:
    md = timeseries.get("metadata", {})
    return {int(k): int(v) for k, v in md.get("clusterWeights", {}).items()}


def annual_sum(values_per_cluster: Dict[int, np.ndarray],
               timeseries: Dict[str, Any], dt_h: Optional[float] = None) -> float:
    """
    Gewichtete Jahressumme (Energie/Integral) aus Cluster-Reihen
    OHNE explizite 8760-Rekonstruktion.

    sum_total = sum_c weight[c] * sum(arr[c]) * dt_h
    """
    weights = _cluster_weights(timeseries)
    if dt_h is None:
        dt_h = timeseries["metadata"].get("timeResolution_s", 3600) / 3600.0
    total = 0.0
    for c, arr in values_per_cluster.items():
        if arr is None: continue
        total += float(weights.get(int(c), 1)) * float(np.sum(arr)) * dt_h
    return total


# ══════════════════════════════════════════════════════════════════════
# VERSORGUNGSANTEILE PRO GEBAEUDE
# ══════════════════════════════════════════════════════════════════════

def compute_supply_shares(timeseries: Dict[str, Any], year: int) -> Dict[str, Dict[str, float]]:
    """
    Anteile der Waermequellen am Gesamtwaermebezug je Gebaeude (Jahr).

    Returns
    -------
    {building_name: {source: share, "total_kWh": E_total}}
    """
    weights = _cluster_weights(timeseries)
    dt_h = timeseries["metadata"].get("timeResolution_s", 3600) / 3600.0

    # Gebaeude-Liste ueber alle Cluster
    bldg_names = set()
    for c_dict in timeseries["buildings"].get(year, {}).values():
        bldg_names.update(c_dict.keys())

    out = {}
    for name in bldg_names:
        # source -> energy [kWh]
        per_source = {}
        for cluster_idx, bldgs in timeseries["buildings"].get(year, {}).items():
            bd = bldgs.get(name)
            if not bd:
                continue
            qbs = bd.get("Q_th_by_source")
            if not qbs:
                continue
            w = float(weights.get(int(cluster_idx), 1))
            for src, arr in qbs.items():
                e = w * float(np.sum(arr)) * dt_h  # arr in kW -> kWh
                per_source[src] = per_source.get(src, 0.0) + e

        total = sum(per_source.values())
        if total > 0:
            shares = {f"share_{k}": v / total for k, v in per_source.items()}
            shares.update({f"E_{k}_kWh": v for k, v in per_source.items()})
            shares["total_kWh"] = total
        else:
            shares = {"total_kWh": 0.0}
        out[name] = shares

    return out


def compute_supply_shares_central(timeseries: Dict[str, Any], year: int) -> Dict[str, float]:
    """
    Anteile der Waermequellen am EH-Output (zentral) im Jahr.

    Beantwortet: laeuft der grosse Gaskessel in Spitzen oder durchgehend?
    -> Jahresanteil + Vollbenutzungsstunden.
    """
    weights = _cluster_weights(timeseries)
    dt_h = timeseries["metadata"].get("timeResolution_s", 3600) / 3600.0

    eh = timeseries["energy_hub"].get(year, {})
    sources = ("HP", "BOI", "BBOI", "CHP", "BCHP", "WCHP", "WBOI", "EB", "GHP", "FC", "STC")
    energy_kwh = {s: 0.0 for s in sources}

    for cluster_idx, eh_data in eh.items():
        w = float(weights.get(int(cluster_idx), 1))
        for s in sources:
            arr = eh_data.get(f"heat_{s}")
            if arr is None: continue
            energy_kwh[s] += w * float(np.sum(arr)) * dt_h

    total = sum(energy_kwh.values())
    out = {f"E_{s}_kWh": e for s, e in energy_kwh.items()}
    if total > 0:
        out.update({f"share_{s}": e / total for s, e in energy_kwh.items()})
    out["total_kWh"] = total
    return out


def peak_to_full_load_hours(timeseries: Dict[str, Any], year: int,
                             device: str, capacity_kw: float) -> Optional[float]:
    """
    Vollbenutzungsstunden eines zentralen Geraets:  E_year_kWh / cap_kW.
    Indikator: << 2000 h => Spitzenlast, > 4000 h => Grundlast.
    """
    if not capacity_kw:
        return None
    shares = compute_supply_shares_central(timeseries, year)
    e = shares.get(f"E_{device}_kWh", 0.0)
    return e / float(capacity_kw)


# ══════════════════════════════════════════════════════════════════════
# WAERMEDICHTE (aus summary, nachtraeglich)
# ══════════════════════════════════════════════════════════════════════

def compute_heat_density(summary: Dict[str, Any],
                          district_area_m2: Optional[float] = None) -> Dict[str, float]:
    """
    Waermedichte aus summary. Wenn `district_area_m2` mitgegeben wird, hat es Vorrang
    vor dem im summary gespeicherten Wert.
    """
    hg = summary.get("heat_grid", {}) or {}
    metrics = hg.get("metrics", {}) or {}
    hd = hg.get("heat_density", {}) or {}

    q_kwh = metrics.get("total_net_heat_demand_kWh") or hd.get("total_net_heat_demand_kWh")
    L = metrics.get("total_pipe_length_m") or hd.get("total_pipe_length_m")
    A = district_area_m2 or hd.get("district_area_m2")

    out = {
        "total_net_heat_demand_kWh": q_kwh,
        "total_pipe_length_m": L,
        "district_area_m2": A,
        "heat_density_kWh_per_m_a": (float(q_kwh) / float(L)) if (q_kwh and L) else None,
        "heat_density_MWh_per_ha_a": (
            (float(q_kwh) / 1000.0) / (float(A) / 10_000.0)
        ) if (q_kwh and A) else None,
    }
    return out


# ══════════════════════════════════════════════════════════════════════
# BM-VERGLEICHS-TABELLE
# ══════════════════════════════════════════════════════════════════════

def comparison_table(results_dir: str) -> List[Dict[str, Any]]:
    """
    Eine Zeile pro Run – Kerngroessen fuer BM-Vergleich.
    Liefert eine Liste von Dicts (zur Konvertierung in DataFrame).
    """
    rows = []
    for fp in sorted(glob.glob(os.path.join(results_dir, "summary_*.pkl"))):
        try:
            s = _load_pkl(fp)
        except Exception:
            continue
        md = s.get("metadata", {})
        kpi = s.get("kpis", {}) or {}
        static = kpi.get("static", {}) or {}
        hg = (s.get("heat_grid") or {}).get("metrics", {}) or {}
        hd = (s.get("heat_grid") or {}).get("heat_density", {}) or {}

        rows.append({
            "scenario_name": md.get("scenario_name"),
            "business_model": md.get("business_model"),
            "reference_key": md.get("reference_key"),
            "reference_case": md.get("reference_case"),
            "p_min_ct_per_kWh": (static.get("p_min") or 0) * 100 if static.get("p_min") is not None else None,
            "p_max_ct_per_kWh": (static.get("p_max") or 0) * 100 if static.get("p_max") is not None else None,
            "npv_coop": static.get("npv_coop"),
            "npv_ref": static.get("npv_ref"),
            "npv_difference": static.get("npv_difference"),
            "economically_favorable": static.get("economically_favorable"),
            "Q_heat_delivered_kWh": static.get("Q_heat_delivered_kWh"),
            "lcoh": static.get("lcoh"),
            "total_pipe_length_m": hg.get("total_pipe_length_m"),
            "heat_loss_percentage": hg.get("heat_loss_percentage"),
            "heat_density_kWh_per_m_a": hd.get("heat_density_kWh_per_m_a"),
            "heat_density_MWh_per_ha_a": hd.get("heat_density_MWh_per_ha_a"),
        })
    return rows
