## -*- coding: utf-8 -*-
"""
result_saver.py — Modulare Speicherung der Simulationsergebnisse.

Drei Dateien pro Run:
  summary_<scen>_<bm>.pkl    : KPIs, Kapazitaeten, BM-Breakdown, Heat-Grid-Metriken,
                                Eco-Daten inkl. Preis-Zeitreihen (klein, immer geladen)
  timeseries_<scen>_<bm>.pkl : Cluster-Reihen (Energy Hub + Gebaeude)
                                + clusterAssignments/clusterWeights fuer 8760-Rekonstruktion
  topology_<scen>_<bm>.pkl   : Pipeline-Topologie und Pipe-Specs

Public API (rueckwaertskompatibel):
    save_all_results(data, filename, include_time_series) -> str
        Schreibt summary + timeseries + topology. Gibt Pfad der summary-Datei zurueck.
        `filename` darf "results_<scen>_<bm>.pkl" heissen — Praefix wird ersetzt.

    load_results(filepath) -> dict
    load_multiple_results(dir, pattern) -> dict
"""

import os
import pickle
import re
import heapq
from datetime import datetime
from typing import Any, Dict, Optional

import numpy as np


# ══════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════

def _safe_getattr(obj, attr, default=None):
    if obj is None:
        return default
    return getattr(obj, attr, default)


def _to_list(arr):
    if arr is None:
        return None
    if hasattr(arr, "tolist"):
        return arr.tolist()
    if isinstance(arr, dict):
        return {k: _to_list(v) for k, v in arr.items()}
    if isinstance(arr, (list, tuple)):
        return [_to_list(item) for item in arr]
    return arr


def _is_arraylike(x) -> bool:
    return isinstance(x, (list, tuple, np.ndarray)) and not isinstance(x, (str, bytes))


def _common_metadata(data) -> Dict[str, Any]:
    """Metadaten, die in JEDER der drei Dateien identisch landen."""
    return {
        "scenario_name": data.scenario_name,
        "scenario_variant": getattr(data, "scenario_variant", None),
        "business_model": data.ecoData.get("business_model"),
        "reference_key": data.ecoData.get("reference_key"),
        "reference_case": data.ecoData.get("reference_case"),
        "timestamp": datetime.now().isoformat(),
        "observation_time": data.ecoData.get("observation_time"),
        "interpolation_points": list(data.ecoData.get("interpolation_points", [])),
        # Cluster-Metadaten — fuer Rekonstruktion auf 8760
        "clusterNumber": data.time.get("clusterNumber"),
        "clusterLength_s": data.time.get("clusterLength"),
        "timeResolution_s": data.time.get("timeResolution"),
        "dataResolution_s": data.time.get("dataResolution"),
        "clusterWeights": dict(getattr(data, "clusterWeights", {}) or {}),
        "clusterAssignments": {
            int(k): list(v) for k, v in
            (getattr(data, "clusterAssignments", {}) or {}).items()
        },
    }


def _resolve_paths(data, filename: Optional[str]) -> Dict[str, str]:
    """
    Bestimmt die drei Output-Pfade. Akzeptiert Legacy-`results_*.pkl` Namen
    und ersetzt das Praefix.
    """
    if filename is None:
        bm = data.ecoData.get("business_model", "unknown")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = f"{data.scenario_name}_{bm}_{ts}"
    else:
        base = filename[:-4] if filename.endswith(".pkl") else filename
        stem = re.sub(r"^(results|summary|timeseries|topology)_", "", base)

    out_dir = data.resultPath
    return {
        "summary":    os.path.join(out_dir, f"summary_{stem}.pkl"),
        "timeseries": os.path.join(out_dir, f"timeseries_{stem}.pkl"),
        "topology":   os.path.join(out_dir, f"topology_{stem}.pkl"),
    }


# ══════════════════════════════════════════════════════════════════════
# KPI EXTRACTION (incl. BM-Breakdown)
# ══════════════════════════════════════════════════════════════════════

# BM-Breakdown-Attribute. Generisch dumpen — Plot-Code pickt selbst raus.
_BM_BREAKDOWN_ATTRS = (
    "bm_breakdown",
    "reference_breakdown",
    "waermecontracting_breakdown",
    "gemeinschaftliche_gebaeudeversorgung_breakdown",
    "kundenanlage_breakdown",
    "genossenschaft_breakdown",
)

_YEARLY_KPI_KEYS = (
    "peakDemand", "peakInjection", "peakToValley",
    "W_inj_GCP_year", "W_dem_GCP_year",
    "W_inj_buildings_year", "W_dem_buildings_year",
    "gas_year", "biomass_year", "waste_year", "hydrogen_year",
    "oil_year", "districtHeat_year",
    "dcf_year", "scf_year",
    "operationCosts", "co2emissions",
    "energy_autonomy_year", "gasoline_costs",
    "lcoh_year_building", "lcoh_year_eh",
)

_STATIC_KPI_KEYS = (
    "totalarea_residential", "totalarea_non_residential",
    "totalnumberflats", "totalnumberocc",
    "totalheatload", "totalcoolingload",
    "total_heating_demand", "total_cooling_demand",
    "total_electricity_demand", "total_EV_demand", "total_dhw_demand",
    "total_electricity_peak", "total_heat_peak", "total_dhw_peak",
    "total_cooling_peak", "total_EV_peak",
    "total_ICE_fuel_liters",
    "annual_fixed_costs_decentral", "annual_fixed_costs_decentral_unsubsidized",
    "annual_fixed_costs_central", "annual_fixed_costs_central_unsubsidized",
    "total_W_dem_GCP", "total_W_inj_GCP",
    "total_W_dem_buildings", "total_W_inj_buildings",
    "total_gas", "total_biomass", "total_waste", "total_hydrogen",
    "total_oil", "total_districtHeat",
    "total_co2_all", "total_co2_dem_grid", "total_co2_gas",
    "total_co2_biom", "total_co2_waste", "total_co2_hydrogen",
    "total_co2_oil", "total_co2_district_heat",
    "business_model", "reference_case", "evaluation_method",
    "p_min", "p_max",
    "npv_coop", "npv_ref", "npv_difference", "economically_favorable",
    "Q_heat_delivered_kWh", "lcoh",
    "npv_ref_by_building",
)


def _building_feature_snapshot(data, n) -> Dict[str, Any]:
    """Stammdaten für Gebäudeindex n aus data.district / data.scenario."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return {"building_index": n}

    snap: Dict[str, Any] = {"building_index": n}
    try:
        bf = data.district[n].get("buildingFeatures", {})
    except (IndexError, AttributeError, TypeError):
        bf = {}

    for key in ("original_bldg_id", "building", "year", "retrofit", "area",
                "heater", "nb_of_flats", "PV", "STC", "BAT", "EV", "f_TES"):
        if key in bf:
            snap[key] = bf[key]

    try:
        snap["unique_name"] = data.district[n].get("unique_name")
    except (IndexError, AttributeError, TypeError):
        snap["unique_name"] = None

    return snap


def _enrich_building_details_with_features(bm_breakdown: Dict[str, Any], data) -> None:
    """
    Hängt Gebäude-Stammdaten an jedes building_details[n] in allen
    bm_breakdown-Sub-Strukturen (scenario_a, scenario_b, ...).
    Ergänzt zusätzlich connected_features / excluded_features Listen mit denselben
    Stammdaten, damit ausgeschlossene Gebäude direkt analysierbar sind.
    """
    if not bm_breakdown:
        return

    for attr_name, attr_val in bm_breakdown.items():
        if not isinstance(attr_val, dict):
            continue

        # Direkte building_details auf oberster Ebene
        _attach_features_to_details(attr_val, data)

        # Verschachtelte scenario_a / scenario_b Strukturen
        for sub_key in ("scenario_a", "scenario_b"):
            sub = attr_val.get(sub_key)
            if isinstance(sub, dict):
                _attach_features_to_details(sub, data)


def _attach_features_to_details(container: Dict[str, Any], data) -> None:
    details = container.get("building_details")
    if isinstance(details, dict):
        for n, d in details.items():
            if isinstance(d, dict) and "_features" not in d:
                try:
                    n_int = int(n)
                except (TypeError, ValueError):
                    continue
                d["_features"] = _building_feature_snapshot(data, n_int)

    # connected/excluded sind reine Index-Listen → parallele *_features Liste
    for list_key, out_key in (("connected", "connected_features"),
                              ("excluded",  "excluded_features")):
        idx_list = container.get(list_key)
        if isinstance(idx_list, (list, tuple)) and out_key not in container:
            features = []
            for n in idx_list:
                try:
                    features.append(_building_feature_snapshot(data, int(n)))
                except (TypeError, ValueError):
                    continue
            container[out_key] = features


def _extract_kpis(data) -> Dict[str, Any]:
    if not hasattr(data, "KPIs") or data.KPIs is None:
        return {}

    kpis = data.KPIs
    years = sorted(kpis.inputData.get("simulated_years", []))

    yearly = {k: _safe_getattr(kpis, k, {}) for k in _YEARLY_KPI_KEYS}
    static = {k: _safe_getattr(kpis, k) for k in _STATIC_KPI_KEYS}

    bm_breakdown = {}
    for attr in _BM_BREAKDOWN_ATTRS:
        val = _safe_getattr(kpis, attr)
        if val is not None:
            bm_breakdown[attr] = val

    # Anreichern: Gebäude-Stammdaten an building_details hängen, damit
    # nachvollziehbar ist, WARUM ein Gebäude in Szenario A ausgeschlossen wurde
    # (Baujahr, Typ, Fläche, Heater, original_bldg_id).
    _enrich_building_details_with_features(bm_breakdown, data)

    return {
        "yearly": yearly,
        "static": static,
        "bm_breakdown": bm_breakdown,
        "device_costs": {
            "decentral": _safe_getattr(kpis, "decentral_individual_devices_annualized_cost", {}),
            "central":   _safe_getattr(kpis, "central_individual_devices_annualized_cost", {}),
        },
        "residual_load": {
            "sum_res_load": _safe_getattr(kpis, "sum_res_load", {}),
            "sum_res_inj":  _safe_getattr(kpis, "sum_res_inj", {}),
            "residualLoad": _safe_getattr(kpis, "residualLoad", {}),
        },
        "cover_factors": {
            "supplyCoverFactor": _safe_getattr(kpis, "supplyCoverFactor", {}),
            "demandCoverFactor": _safe_getattr(kpis, "demandCoverFactor", {}),
        },
        "energy_autonomy": _safe_getattr(kpis, "energy_autonomy", {}),
        "simulated_years": years,
    }


# ══════════════════════════════════════════════════════════════════════
# CAPACITY EXTRACTION
# ══════════════════════════════════════════════════════════════════════

_STORAGE_DEVS = ("TES", "CTES", "BAT", "H2S", "GS")
_AREA_DEVS = ("PV", "STC")


def _cap_unit_dict(dev: str, dev_data: dict) -> dict:
    cap = dev_data.get("cap", 0)
    common = {
        "ann_inv_cost": dev_data.get("ann_inv_cost", 0),
        "ann_inv_cost_unsubsidized": dev_data.get("ann_inv_cost_unsubsidized", 0),
        "om_cost": dev_data.get("om_cost", 0),
        "gen_kWh": dev_data.get("gen_kWh", 0),
    }
    if dev in _STORAGE_DEVS:
        return {"cap_kWh": cap, **common}
    if dev in _AREA_DEVS:
        return {"cap_m2": cap, "cap_kW_peak": cap, **common}
    return {"cap_kW": cap, **common}


def _extract_capacities(data) -> Dict[str, Any]:
    capacities = {"central": {}, "decentral": {}, "central_raw": {}}

    # ----- ZENTRAL -----
    if hasattr(data, "centralDevices") and isinstance(data.centralDevices, dict):
        cap_data = data.centralDevices.get("capacities", {})
        if isinstance(cap_data, dict):
            capacities["central_raw"] = cap_data
            device_list = ["PV", "WT", "STC", "WAT", "HP", "EB", "CC", "AC",
                           "CHP", "BOI", "GHP", "BCHP", "BBOI", "WCHP", "WBOI",
                           "ELYZ", "FC", "H2S", "SAB", "TES", "CTES", "BAT", "GS"]
            for dev in device_list:
                if dev in cap_data and isinstance(cap_data[dev], dict):
                    capacities["central"][dev] = _cap_unit_dict(dev, cap_data[dev])

            capacities["central"]["_summary"] = {
                "tac": cap_data.get("tac", 0),
                "co2": cap_data.get("co2", 0),
                "total_inv_cost": cap_data.get("total_inv_cost", 0),
                "total_ann_inv_cost": cap_data.get("total_ann_inv_cost", 0),
                "total_om_cost": cap_data.get("total_om_cost", 0),
                "from_el_grid_total": cap_data.get("from_el_grid_total", 0),
                "to_el_grid_total": cap_data.get("to_el_grid_total", 0),
                "from_gas_grid_total": cap_data.get("from_gas_grid_total", 0),
            }
            if "area" in cap_data:
                capacities["central"]["_areas"] = cap_data["area"]

    # ----- DEZENTRAL -----
    if hasattr(data, "district") and isinstance(data.district, list):
        for n, building in enumerate(data.district):
            if not isinstance(building, dict):
                continue
            building_name = building.get("unique_name", f"building_{n}")
            building_caps = {}
            if "capacities" in building:
                bldg_cap = building["capacities"]
                for dev in ["HP", "BOI", "BBOI", "H2BOI", "OBOI", "CHP", "FC",
                            "EH", "DH", "PV", "BAT", "TES", "STC", "CC"]:
                    if dev in bldg_cap:
                        val = bldg_cap[dev]
                        if isinstance(val, dict):
                            cap = val.get("cap", 0)
                            extras = {k: v for k, v in val.items() if k != "cap"}
                        else:
                            cap = val
                            extras = {}
                        if dev in _STORAGE_DEVS:
                            building_caps[dev] = {"cap_kWh": cap, **extras}
                        elif dev in _AREA_DEVS:
                            building_caps[dev] = {"cap_m2": cap, "cap_kW_peak": cap, **extras}
                        else:
                            building_caps[dev] = {"cap_kW": cap, **extras}

            bf = building.get("buildingFeatures", {})
            building_caps["_info"] = {
                "building_id": n,
                "original_bldg_id": bf.get("original_bldg_id"),
                "unique_name": building_name,
                "building_type": bf.get("building", "unknown"),
                "year_of_construction": bf.get("year", 0),
                "retrofit": bf.get("retrofit", 0),
                "area": bf.get("area", 0),
                "heater": bf.get("heater", "unknown"),
                "number_of_flats": bf.get("nb_of_flats", 0),
            }
            capacities["decentral"][building_name] = building_caps

    return capacities


# ══════════════════════════════════════════════════════════════════════
# HEAT GRID — Summary-Anteil
# ══════════════════════════════════════════════════════════════════════

def _heat_density(hg: dict, total_pipe_length_m: float, district_area_m2: Optional[float]) -> dict:
    """Waermedichte (Trasse + Flaeche). Rohwerte – Loader/Plot rechnet weiter."""
    q_kwh = hg.get("total_net_heat_demand")
    out = {
        "total_net_heat_demand_kWh": q_kwh,
        "total_pipe_length_m": total_pipe_length_m,
        "district_area_m2": district_area_m2,
        "heat_density_kWh_per_m_a": None,
        "heat_density_MWh_per_ha_a": None,
    }
    if q_kwh and total_pipe_length_m:
        out["heat_density_kWh_per_m_a"] = float(q_kwh) / float(total_pipe_length_m)
    if q_kwh and district_area_m2:
        out["heat_density_MWh_per_ha_a"] = (float(q_kwh) / 1000.0) / (float(district_area_m2) / 10_000.0)
    return out


def _extract_heat_grid_summary(data) -> Dict[str, Any]:
    if not hasattr(data, "heat_grid_data") or not data.heat_grid_data:
        return {}
    hg = data.heat_grid_data

    pipe_length = sum(pipe.get("length", 0)
                      for pipe in getattr(data, "pipeline", {}).values())

    district_area = None
    if hasattr(data, "site"):
        dp = data.site.get("district_parameters", {}) or {}
        district_area = dp.get("district_area") or dp.get("area")

    return {
        "config": {
            "generation": hg.get("generation"),
            "topology_option": hg.get("topology_option"),
            "temperature_mode": hg.get("temperature_mode"),
            "heuristic": hg.get("heuristic"),
            "T_hot_heating_network": hg.get("T_hot_heating_network"),
            "T_cold_heating_network": hg.get("T_cold_heating_network"),
            "k_soil": hg.get("k_soil"),
            "k_PUF": hg.get("k_PUF"),
            "grid_depth": hg.get("grid_depth"),
            "D_heating_network": hg.get("D_heating_network"),
            "h_loss_subst": hg.get("h_loss_subst"),
            "pipe_config": hg.get("pipe", {}),
        },
        "costs": {
            "total_investment": hg.get("costs", 0),
            "ann_costs": hg.get("ann_costs", 0),
            "om_costs": hg.get("om_costs", 0),
            "substation_ann_costs": hg.get("substation_ann_costs"),
            "substation_om_costs": hg.get("substation_om_costs"),
            "pipes_ann_costs": hg.get("pipes_ann_costs"),
            "pipes_om_costs": hg.get("pipes_om_costs"),
            "pump_ann_costs": hg.get("pump_ann_costs"),
            "pump_om_costs": hg.get("pump_om_costs"),
            "pump_electricity_costs": hg.get("pump_electricity_costs"),
            "HP_ann_costs": hg.get("HP_ann_costs"),
            "HP_om_costs": hg.get("HP_om_costs"),
            "HP_electricity_costs": hg.get("HP_electricity_costs"),
            "pipe_ann_factor": hg.get("pipe", {}).get("pipe_ann_factor"),
            "pump_ann_factor": hg.get("pump", {}).get("pump_ann_factor"),
        },
        "metrics": {
            "total_pipe_length_m": pipe_length,
            "num_connected_buildings": hg.get("num_connected_buildings"),
            "annual_heat_loss_kWh": hg.get("annual_heat_loss"),
            "heat_loss_density_W_per_m": hg.get("heat_loss_density"),
            "heat_loss_percentage": hg.get("heat_loss_percentage"),
            "pump_capacity_kW": hg.get("pump_capacity"),
            "pump_electricity_consumption_kWh": hg.get("pump_electricity_consumption"),
            "pump_electricity_percentage": hg.get("pump_electricity_consumption_percentage"),
            "total_net_heat_demand_kWh": hg.get("total_net_heat_demand"),
            "T_soil_mean": hg.get("T_soil_mean"),
            "T_supply_mean": hg.get("T_supply_mean"),
            "T_return_mean": hg.get("T_return_mean"),
        },
        "heat_density": _heat_density(hg, pipe_length, district_area),
    }



def _network_distances_from_pipeline(pipeline: dict, nodes: dict) -> Dict[str, float]:
    """
    Berechnet kuerzeste Rohrleitungsdistanzen [m] von der Energiezentrale
    zu allen Knoten anhand der gespeicherten pipeline-Kanten.
    """
    if not isinstance(pipeline, dict) or not pipeline:
        return {}

    # Energiezentrale robust erkennen
    eh_nodes = []
    if isinstance(nodes, dict):
        for node_id, node_data in nodes.items():
            role = None
            if isinstance(node_data, dict):
                role = str(node_data.get("role", "")).upper()
            if role == "EH" or str(node_id).upper().startswith("EH"):
                eh_nodes.append(str(node_id))
    if not eh_nodes:
        eh_nodes = ["EH1"]

    graph = {}
    for _, edge in pipeline.items():
        if not isinstance(edge, dict):
            continue
        u = edge.get("from")
        v = edge.get("to")
        length = edge.get("length")
        if u is None or v is None or length is None:
            continue
        try:
            length = float(length)
        except (TypeError, ValueError):
            continue
        u = str(u)
        v = str(v)
        graph.setdefault(u, []).append((v, length))
        graph.setdefault(v, []).append((u, length))

    distances = {}
    pq = []
    for eh in eh_nodes:
        if eh in graph or eh in nodes:
            distances[eh] = 0.0
            heapq.heappush(pq, (0.0, eh))

    while pq:
        dist, node = heapq.heappop(pq)
        if dist > distances.get(node, float("inf")):
            continue
        for nxt, length in graph.get(node, []):
            nd = dist + length
            if nd < distances.get(nxt, float("inf")):
                distances[nxt] = nd
                heapq.heappush(pq, (nd, nxt))

    return distances


def _extract_building_node_mapping(data, nodes: dict, distances: dict) -> Dict[str, Any]:
    """
    Speichert eine robuste Zuordnung Gebaeude -> Topologie-Knoten.

    Wichtig: Die eindeutige Zuordnung ist nur sicher, wenn der Heat-Grid-Code
    Gebaeude-Knoten in der Reihenfolge der HEAT_GRID-Gebaeude als bldg1, bldg2, ...
    anlegt. Deshalb werden sowohl der gemappte Knoten als auch die Kandidaten
    gespeichert. Nicht angeschlossene Gebaeude haben i. d. R. keinen Topologie-Knoten.
    """
    mapping = {}
    if not hasattr(data, "district") or not isinstance(data.district, list):
        return mapping

    nodes = nodes or {}
    node_ids = set(str(k) for k in nodes.keys()) if isinstance(nodes, dict) else set()

    # bldg1, bldg2, ... werden typischerweise nur fuer angeschlossene HEAT_GRID-Gebaeude erzeugt.
    heat_grid_indices = []
    for n, building in enumerate(data.district):
        if not isinstance(building, dict):
            continue
        bf = building.get("buildingFeatures", {}) or {}
        heater = str(bf.get("heater", "")).upper()
        if heater == "HEAT_GRID":
            heat_grid_indices.append(n)

    hg_index_to_node = {}
    for order, n in enumerate(heat_grid_indices, start=1):
        candidate = f"bldg{order}"
        if candidate in node_ids:
            hg_index_to_node[n] = candidate

    for n, building in enumerate(data.district):
        if not isinstance(building, dict):
            continue
        bf = building.get("buildingFeatures", {}) or {}
        unique_name = building.get("unique_name", f"building_{n}")

        candidate_nodes = [
            hg_index_to_node.get(n),
            f"bldg{n}",
            f"bldg{n + 1}",
            str(n),
            str(unique_name),
        ]
        candidate_nodes = [c for c in candidate_nodes if c is not None]

        topology_node = None
        for cand in candidate_nodes:
            if str(cand) in node_ids:
                topology_node = str(cand)
                break

        pos = None
        if topology_node is not None and isinstance(nodes.get(topology_node), dict):
            pos = nodes[topology_node].get("pos")

        mapping[str(n)] = {
            "building_index": n,
            "unique_name": unique_name,
            "original_bldg_id": bf.get("original_bldg_id"),
            "building_type": bf.get("building", "unknown"),
            "year_of_construction": bf.get("year", 0),
            "retrofit": bf.get("retrofit", 0),
            "area": bf.get("area", 0),
            "number_of_flats": bf.get("nb_of_flats", 0),
            "heater": bf.get("heater", "unknown"),
            "topology_node": topology_node,
            "candidate_topology_nodes": candidate_nodes,
            "node_position": _to_list(pos),
            "distance_to_energy_hub_m": distances.get(topology_node) if topology_node is not None else None,
        }

    return mapping


def _extract_heat_grid_topology(data) -> Dict[str, Any]:
    """Topologie + Pipe-Specs + Heat-Grid-Zeitreihen (8760 + clustered)."""
    if not hasattr(data, "heat_grid_data") or not data.heat_grid_data:
        return {}
    hg = data.heat_grid_data

    raw_nodes = getattr(data, "pipeline_nodes", {})
    raw_pipeline = getattr(data, "pipeline", {})
    distances_to_eh = _network_distances_from_pipeline(raw_pipeline, raw_nodes)
    building_node_mapping = _extract_building_node_mapping(data, raw_nodes, distances_to_eh)

    topo = {
        "topology": {
            "nodes": _to_list(raw_nodes),
            "edges": _to_list(getattr(data, "pipeline_topology", {})),
            "pipeline": _to_list(raw_pipeline),
        },
        "building_node_mapping": building_node_mapping,
        "building_distances_to_energy_hub_m": {
            k: v.get("distance_to_energy_hub_m") for k, v in building_node_mapping.items()
        },
        "pipe_specifications": {},
        "time_series_8760": {
            "losses_heating_network_kW": _to_list(hg.get("total_losses_heating_network")),
            "losses_cooling_network_kW": _to_list(hg.get("total_losses_cooling_network")),
            "pump_power_kW": _to_list(hg.get("pump_power")),
            "T_soil_C": _to_list(hg.get("T_soil")),
        },
        "time_series_clustered": {
            "losses_heating_network_kW": _to_list(hg.get("total_losses_heating_network_cluster")),
            "losses_cooling_network_kW": _to_list(hg.get("total_losses_cooling_network_cluster")),
            "pump_power_kW": _to_list(hg.get("pump_power_cluster")),
            "T_soil_C": _to_list(hg.get("T_soil_cluster")),
        },
    }

    if hasattr(data, "pipe_data") and data.pipe_data is not None:
        try:
            if hasattr(data.pipe_data, "to_dict"):
                topo["pipe_specifications"] = data.pipe_data.to_dict("records")
            else:
                topo["pipe_specifications"] = dict(data.pipe_data)
        except Exception:
            pass

    return topo


# ══════════════════════════════════════════════════════════════════════
# TIME SERIES (Cluster-Aufloesung)
# ══════════════════════════════════════════════════════════════════════

def _extract_time_series(data) -> Dict[str, Any]:
    """
    Cluster-Reihen pro Jahr und Cluster.
    Geometrie:  num_clusters * time_steps_per_cluster
    Beispiel: 4 Cluster, clusterLength=604800s (Woche), dt=3600s -> 4 * 168 = 672 Schritte
              52 Cluster -> 52 * 168 = 8736 Schritte (~ 8760)
    """
    ts = {"energy_hub": {}, "buildings": {}, "district_totals": {}, "metadata": {}}

    if not hasattr(data, "resultsOptimization") or not data.resultsOptimization:
        return ts

    time_steps = int(data.time["clusterLength"] / data.time["timeResolution"])
    num_clusters = data.time["clusterNumber"]
    num_buildings = len(data.district)

    ts["metadata"] = {
        "time_steps_per_cluster": time_steps,
        "num_clusters": num_clusters,
        "num_buildings": num_buildings,
        "time_resolution_seconds": data.time["timeResolution"],
        "cluster_length_seconds": data.time["clusterLength"],
    }

    years = sorted(data.resultsOptimization.keys())

    for year in years:
        ts["energy_hub"][year] = {}
        ts["buildings"][year] = {}
        ts["district_totals"][year] = {}
        year_results = data.resultsOptimization[year]

        for cluster in range(num_clusters):
            cluster_results = year_results.get(cluster, {})

            # ----- ENERGY HUB -----
            eh_data = {}
            eh_power_devs = ("PV", "WT", "WAT", "HP", "EB", "CC", "CHP",
                             "BCHP", "WCHP", "ELYZ", "FC", "from_grid", "to_grid")
            if "eh_power" in cluster_results:
                for dev in eh_power_devs:
                    if dev in cluster_results["eh_power"]:
                        eh_data[f"power_{dev}"] = np.array(cluster_results["eh_power"][dev])

            eh_heat_devs = ("STC", "HP", "EB", "AC", "CHP", "BOI", "GHP",
                            "BCHP", "BBOI", "WCHP", "WBOI", "FC", "to_grid")
            if "eh_heat" in cluster_results:
                for dev in eh_heat_devs:
                    if dev in cluster_results["eh_heat"]:
                        eh_data[f"heat_{dev}"] = np.array(cluster_results["eh_heat"][dev])

            if "eh_cool" in cluster_results:
                for dev in ("CC", "AC", "to_grid"):
                    if dev in cluster_results["eh_cool"]:
                        eh_data[f"cool_{dev}"] = np.array(cluster_results["eh_cool"][dev])

            for storage_type in ("eh_ch", "eh_dch", "eh_soc"):
                if storage_type in cluster_results:
                    for dev in ("TES", "CTES", "BAT", "H2S", "GS"):
                        if dev in cluster_results[storage_type]:
                            eh_data[f"{storage_type}_{dev}"] = np.array(cluster_results[storage_type][dev])

            for key in ("P_dem_total", "P_inj_total", "P_dem_gcp", "P_inj_gcp",
                        "P_gas_total", "P_hydrogen_total", "P_biomass_total",
                        "P_oil_total", "P_waste_total", "P_district_heat_total",
                        "eh_to_buildings"):
                if key in cluster_results:
                    eh_data[key] = np.array(cluster_results[key])

            ts["energy_hub"][year][cluster] = eh_data

            # ----- GEBAEUDE -----
            buildings_data = {}
            tot_res_load = np.zeros(time_steps)
            tot_res_inj = np.zeros(time_steps)
            tot_pv = np.zeros(time_steps)
            tot_demand = np.zeros(time_steps)
            tot_hp_el = np.zeros(time_steps)
            tot_heat_demand = np.zeros(time_steps)
            tot_dhw_demand = np.zeros(time_steps)

            for n in range(num_buildings):
                building_name = data.district[n].get("unique_name", f"building_{n}")
                br = cluster_results.get(n, {})
                bd = {"_building_id": n}

                if "res_load" in br:
                    bd["res_load"] = np.array(br["res_load"]); tot_res_load += bd["res_load"]
                if "res_inj" in br:
                    bd["res_inj"] = np.array(br["res_inj"]); tot_res_inj += bd["res_inj"]

                # Strom
                for dev in ("PV", "HP", "EH", "CC", "CHP", "FC"):
                    if dev in br and "P_el" in br[dev]:
                        arr = np.array(br[dev]["P_el"])
                        bd[f"{dev}_P_el"] = arr
                        if dev == "PV": tot_pv += arr
                        if dev == "HP": tot_hp_el += arr
                if "Elec_dem" in br and "P_el" in br["Elec_dem"]:
                    bd["Elec_dem"] = np.array(br["Elec_dem"]["P_el"])
                    tot_demand += bd["Elec_dem"]

                # Waerme pro Quelle (HP/BOI/CHP/heat_grid/EH/STC/BBOI/FC) — fuer Versorgungsanalyse
                q_by_source = {}
                for dev in ("HP", "BOI", "BBOI", "CHP", "FC", "EH", "STC", "heat_grid"):
                    if dev in br and "Q_th" in br[dev]:
                        arr = np.array(br[dev]["Q_th"])
                        bd[f"{dev}_Q_th"] = arr
                        q_by_source[dev] = arr
                if q_by_source:
                    bd["Q_th_by_source"] = q_by_source

                # Bedarfe Waerme
                if "Heating_dem" in br and "Q_th" in br["Heating_dem"]:
                    bd["Heating_dem"] = np.array(br["Heating_dem"]["Q_th"])
                    tot_heat_demand += bd["Heating_dem"]
                if "DHW_dem" in br and "Q_th" in br["DHW_dem"]:
                    bd["DHW_dem"] = np.array(br["DHW_dem"]["Q_th"])
                    tot_dhw_demand += bd["DHW_dem"]

                # Speicher dezentral
                for dev in ("BAT", "TES"):
                    if dev in br:
                        for key in ("ch", "dch", "soc"):
                            if key in br[dev]:
                                bd[f"{dev}_{key}"] = np.array(br[dev][key])

                # EV
                if "EV" in br:
                    ev_ch = np.zeros(time_steps); ev_dch = np.zeros(time_steps)
                    for car_id, car_data in br["EV"].items():
                        if isinstance(car_data, dict):
                            if "ch" in car_data:  ev_ch  += np.array(car_data["ch"])
                            if "dch" in car_data: ev_dch += np.array(car_data["dch"])
                    bd["EV_ch"] = ev_ch; bd["EV_dch"] = ev_dch

                buildings_data[building_name] = bd

            ts["buildings"][year][cluster] = buildings_data
            ts["district_totals"][year][cluster] = {
                "total_res_load": tot_res_load,
                "total_res_inj": tot_res_inj,
                "total_pv": tot_pv,
                "total_demand": tot_demand,
                "total_hp_el": tot_hp_el,
                "total_heat_demand": tot_heat_demand,
                "total_dhw_demand": tot_dhw_demand,
            }

    return ts


# ══════════════════════════════════════════════════════════════════════
# ECO TIME SERIES (Preis-Verlaeufe ueber Beobachtungszeitraum)
# ══════════════════════════════════════════════════════════════════════

# Felder, die in all_sim_ecoData[year] potenziell vorkommen
_ECO_PRICE_KEYS = (
    "price_supply_el", "price_supply_gas", "price_supply_biomass",
    "price_supply_hydrogen", "price_supply_oil", "price_supply_waste",
    "price_supply_district_heat",
    "revenue_feed_in_el", "price_el_revenue",
    "co2_factor_el", "co2_factor_gas",
)


def _extract_eco(data) -> Dict[str, Any]:
    """
    Eco-Daten inkl. Preis-Zeitreihen ueber Stuetzjahre.
    Akzeptiert sowohl Skalare (heutiger Stand) als auch Arrays (zukuenftig stuendlich).
    """
    eco_static = dict(data.ecoData) if hasattr(data, "ecoData") else {}

    by_year = {}
    if hasattr(data, "all_sim_ecoData"):
        for year, eco_y in data.all_sim_ecoData.items():
            if not isinstance(eco_y, dict):
                continue
            year_dump = {}
            for k in _ECO_PRICE_KEYS:
                if k in eco_y:
                    v = eco_y[k]
                    year_dump[k] = _to_list(v) if _is_arraylike(v) else v
            for k, v in eco_y.items():
                if k in year_dump:
                    continue
                if isinstance(v, (int, float, str, bool)) or v is None:
                    year_dump[k] = v
                elif _is_arraylike(v):
                    year_dump[k] = _to_list(v)
            by_year[year] = year_dump

    return {
        "static": eco_static,
        "by_year": by_year,
    }


# ══════════════════════════════════════════════════════════════════════
# MAIN SAVE
# ══════════════════════════════════════════════════════════════════════

def save_all_results(data, filename: Optional[str] = None,
                     include_time_series: bool = True) -> str:
    """
    Schreibt summary + (optional) timeseries + topology.
    Gibt Pfad der summary-Datei zurueck.
    """
    paths = _resolve_paths(data, filename)
    os.makedirs(os.path.dirname(paths["summary"]), exist_ok=True)
    meta = _common_metadata(data)

    # ===== SUMMARY =====
    summary = {
        "metadata": meta,
        "kpis": _extract_kpis(data),
        "capacities": _extract_capacities(data),
        "heat_grid": _extract_heat_grid_summary(data),
        "eco": _extract_eco(data),
    }
    with open(paths["summary"], "wb") as f:
        pickle.dump(summary, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"  ✓ summary    : {os.path.basename(paths['summary'])}")

    # ===== TIMESERIES =====
    if include_time_series:
        extracted = _extract_time_series(data)
        ts = {
            "metadata": meta,
            "ts_meta": extracted.get("metadata", {}),
            "energy_hub": extracted.get("energy_hub", {}),
            "buildings": extracted.get("buildings", {}),
            "district_totals": extracted.get("district_totals", {}),
        }
        with open(paths["timeseries"], "wb") as f:
            pickle.dump(ts, f, protocol=pickle.HIGHEST_PROTOCOL)
        print(f"  ✓ timeseries : {os.path.basename(paths['timeseries'])}")

    # ===== TOPOLOGY =====
    topo_payload = _extract_heat_grid_topology(data)
    if topo_payload:
        topo = {"metadata": meta, **topo_payload}
        with open(paths["topology"], "wb") as f:
            pickle.dump(topo, f, protocol=pickle.HIGHEST_PROTOCOL)
        print(f"  ✓ topology   : {os.path.basename(paths['topology'])}")

    return paths["summary"]


# ══════════════════════════════════════════════════════════════════════
# LOAD
# ══════════════════════════════════════════════════════════════════════

def load_results(filepath: str) -> Dict[str, Any]:
    with open(filepath, "rb") as f:
        results = pickle.load(f)
    md = results.get("metadata", {})
    print(f"✓ loaded {os.path.basename(filepath)}  "
          f"(scen={md.get('scenario_name')}, bm={md.get('business_model')})")
    return results


def load_multiple_results(result_dir: str, pattern: str = "summary_*.pkl") -> Dict[str, Any]:
    import glob
    out = {}
    for fp in glob.glob(os.path.join(result_dir, pattern)):
        name = os.path.basename(fp).replace(".pkl", "")
        out[name] = load_results(fp)
    print(f"\n✓ loaded {len(out)} files from {result_dir}")
    return out