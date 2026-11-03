# -*- coding: utf-8 -*-
"""Vereinfachtes 2-Leiter-Netz mit EH1 und einem Industrieeinspeiser WH1.

Separates, *opt-in* Mehrquellenmodell. Die bestehende Datei
`heating_network_2leiter.py` wird NICHT verändert.

Bewusst beibehalten aus dem Referenzmodell:
- globale stündliche Netzvorlauf- und Rücklauftemperatur (keine Rohrtemperaturabfälle)
- Gebäudewärmeübertrager, Heizkurven, DN-Kataloge, Leitungskosten
- bestehende EH-orientierte baumförmige Topologie als geometrische Grundlage

Neu: ein WH1-Anschluss, vorzeichenbehaftete Rohr-Massenströme,
Temperaturprüfung der Q1-Q7-Quellen, begrenzbare Wärmepumpenoption,
separate EH-/WH-Energierechnung und überschlägige Zwei-Pumpen-Auslegung.

WICHTIGE EINSCHRÄNKUNGEN: Dies ist ein *thermohydraulisch vereinfachtes*
Modell für die vorbereitende Netzauslegung, KEIN gekoppelter Druck-
und Temperaturfeldsolver. Die berechneten Pumpenleistungen beruhen auf
kritischen Pfaden je Einspeiser und ersetzen keinen hydraulischen Abgleich.
Der EHDO-/Pyomo-Dispatcher muss separat an die tatsächlich genutzte
Industrie-Wärme angebunden werden. Die unter `heat_grid_data` hinterlegten
Abwärme-Zeitreihen sind zunächst Diagnose-/Kopplungsgrößen.

Voraussetzungen: aktueller Datahandler hat bereits
`data.pipeline_nodes` und `data.pipeline_topology` geladen, und die
Szenario-JSON enthält `values.industrial_sites` mit NPZ-/CSV-Referenzen.
Nur ein Industrieeinspeiser je Szenario ist in dieser Version vorgesehen.
"""

from __future__ import annotations

from pathlib import Path
import json
import warnings
import math
import numpy as np
import pandas as pd

from districtgenerator.functions import heating_network_2leiter as single



HX_HOT_APPROACH_K = 5.0
HX_COLD_APPROACH_K = 5.0
HX_UA_SAFETY_FACTOR = 1.0
SUPPORTED_INDUSTRY_HX_Q_TYPES = frozenset({'Q1', 'Q2', 'Q3', 'Q4', 'Q5', 'Q6', 'Q7'})


def calculate_source_hx_specs(industry, supply_C, return_C, direct_max_kW,
                              demand_cap_kW, *, hot_approach_K=HX_HOT_APPROACH_K):
    """UA-/LMTD-Bemessung fuer JEDE direkt nutzbare Abwaermequelle.

    Je Quelle: UA pro kW Nennleistung am unguenstigsten noch zulaessigen
    Netzzustand. Stundenfaktor = LMTD(t) / LMTD(Bemessung).
    Q_direkt(t) <= HX_Nennleistung[kW] * Stundenfaktor(t).
    Nennleistung ist durch Quelle und die stündliche Abnahme begrenzt.
    """
    sup = np.asarray(supply_C, dtype=float)
    ret = np.asarray(return_C, dtype=float)
    raw = np.asarray(direct_max_kW, dtype=float)
    demand = np.asarray(demand_cap_kW, dtype=float)
    temperatures = np.asarray(industry["temperatures_C"], dtype=float)
    source_info = industry["source_info"]
    if "Quellklasse_Code" not in source_info.columns:
        raise ValueError("PFA-Quellen-CSV enthaelt keine Spalte 'Quellklasse_Code'.")
    classes = source_info["Quellklasse_Code"].astype(str).str.strip().str.upper().tolist()
    if raw.ndim != 2 or raw.shape[1] != sup.size or sup.shape != ret.shape or demand.shape != sup.shape:
        raise ValueError("Zeitreihenformen der Industrie-Waermeuebertrager stimmen nicht ueberein.")
    if raw.shape[0] != len(classes) or temperatures.shape != (len(classes),):
        raise ValueError("Quellklassen und Quellentemperaturen passen nicht zum Profil.")
    if not np.isfinite(sup).all() or not np.isfinite(ret).all():
        raise ValueError("Ungültige Netztemperaturen für Quellwaermeuebertrager.")
    if np.any((demand > 1e-9) & (ret >= sup)):
        raise ValueError("Positiver Netzbedarf ohne Vorlauf-Ruecklauf-Temperaturhub.")
    if not np.isfinite(raw).all() or (raw < 0).any() or (demand < 0).any():
        raise ValueError("Ungültige Quellwärme oder Abnahmegrenze.")

    S, T = raw.shape
    factor = np.zeros((S, T), dtype=float)
    ua_per_kW = np.zeros(S, dtype=float)
    capacity_limit = np.zeros(S, dtype=float)
    q_num = np.zeros(S, dtype=float)
    for s, qcode in enumerate(classes):
        if not qcode.startswith("Q") or not qcode[1:].isdigit():
            raise ValueError(f"Unbekannte Quellklasse {qcode!r} bei Quelle {s}")
        q_num[s] = int(qcode[1:])
        active = (raw[s] > 1e-9) & (demand > 1e-9) & (ret < sup) & (temperatures[s] >= sup + hot_approach_K)
        if not np.any(active):
            continue  # Kein direkt nutzbarer Waermeuebertrager noetig

        # Nicht parametrisierte heiße Q7-Quellen dürfen nicht kostenlos laufen.
        if qcode not in SUPPORTED_INDUSTRY_HX_Q_TYPES:
            raise ValueError(f"Direkt nutzbare Quelle {s}: Quelltyp {qcode} "
                             "ist nicht für Industrie-Wärmeübertrager freigegeben.")

        idx = int(np.where(active)[0][np.argmax(sup[active])])
        t_primary_in = float(temperatures[s])
        t_sec_in_design = float(ret[idx])
        t_sec_out_design = float(sup[idx])
        t_primary_out_design = t_sec_in_design + HX_COLD_APPROACH_K
        ua_one_kw = single.hx_calc_UA_design(
            Q_design_W=1000.0,
            T_primary_in_design=t_primary_in,
            T_primary_out_design=t_primary_out_design,
            T_secondary_in_design=t_sec_in_design,
            T_secondary_out_design=t_sec_out_design,
        ) * HX_UA_SAFETY_FACTOR
        if not np.isfinite(ua_one_kw) or ua_one_kw <= 0:
            raise ValueError(f"Kein physikalisch gültiges Design-UA für Quelle {s}")
        ua_per_kW[s] = ua_one_kw
        dt_lm_design = 1000.0 * HX_UA_SAFETY_FACTOR / ua_one_kw

        for t in np.where(active)[0]:
            dT_hot = t_primary_in - float(sup[t])
            # Gleiche Gegenstrom-LMTD-Funktion wie für die Gebäude.
            # Am realen Zeitpunkt: Quellenaustritt mindestens um einen
            # festen Temperaturansatz ueber dem Netzruecklauf.
            dT_cold = HX_COLD_APPROACH_K
            lmtd = single.hx_lmtd(dT_hot, dT_cold)
            if np.isfinite(lmtd) and lmtd > 0:
                factor[s, t] = lmtd / dt_lm_design

        pos = factor[s] > 1e-12
        if not np.any(pos):
            raise ValueError(f"Kein zulaessiger HX-Uebergang fuer Quelle {s}")
        q_cap = np.minimum(raw[s, pos], demand[pos])
        capacity_limit[s] = float(np.max(q_cap / factor[s, pos]))

    return {
        "hx_factor": factor,
        "hx_cap_upper": capacity_limit,
        "hx_UA_per_kW": ua_per_kW,
        "hx_q_number": q_num,
    }


# ============================================================================
# BENUTZER-PRESETS: None => einmalige Konsolenabfrage beim ersten Aufruf.
# ============================================================================
# "direct_only": ausschließlich unmittelbar temperaturtaugliche Quellen
# "all_sources_hp": direkte Quellen direkt, zu kalte Quellen über Industrie-WP
INDUSTRY_HEAT_MODE = None  # "direct_only" | "all_sources_hp" | None
# "forced": maximal mögliche Nutzung, beschränkt durch Wärmeabnahme und Technik
# "optimizer": quellenweise freigegeben; zunächst keine Einspeisung ohne Optimierungsergebnis
INDUSTRY_DISPATCH_MODE = None  # "forced" | "optimizer" | None

# Vorläufige technische Parameter, keine validierte WP-Kennlinie!
INDUSTRY_HP_ETA_CARNOT = 0.40
INDUSTRY_HP_MAX_OUTPUT_KW = None  # None = keine Kapazitätsbegrenzung; keine Wirtschaftsauslegung
INDUSTRY_DIRECT_APPROACH_K = 5.0
INDUSTRY_HP_EVAP_APPROACH_K = 5.0
INDUSTRY_HP_COND_APPROACH_K = 5.0

# Wird nur pro Python-Prozess einmal über die Konsole abgefragt.
_PROMPT_CACHE = {}


def _choose_setting(value, preset, kind):
    choices = {
        "heat": {"1": "direct_only", "2": "all_sources_hp",
                 "direct_only": "direct_only", "all_sources_hp": "all_sources_hp"},
        "dispatch": {"1": "forced", "2": "optimizer",
                     "forced": "forced", "optimizer": "optimizer"},
    }[kind]
    proposed = preset if value is None else value
    if proposed is not None:
        key = str(proposed).strip().lower()
        if key not in choices:
            raise ValueError(f"Ungültige Einstellung {kind}={proposed!r}; erlaubt: {sorted(set(choices.values()))}")
        return choices[key]
    if kind in _PROMPT_CACHE:
        return _PROMPT_CACHE[kind]
    if kind == "heat":
        print("\nINDUSTRIELLE ABWÄRME – TEMPERATURVARIANTE")
        print("  1 = Nur Quellen mit ausreichender Temperatur direkt einspeisen")
        print("  2 = Auch zu kalte Quellen über eine Industrie-Wärmepumpe nutzbar")
    else:
        print("\nINDUSTRIELLE ABWÄRME – EINSATZSTRATEGIE")
        print("  1 = Erzwungene Strategie: verfügbare Wärme vorrangig bis zum Bedarf nutzen")
        print("  2 = Optimierer entscheidet später für jede Quelle über die Nutzung")
    while True:
        answer = input("Auswahl [1/2]: ").strip().lower()
        if answer in choices:
            _PROMPT_CACHE[kind] = choices[answer]
            return choices[answer]
        print("Bitte 1 oder 2 eingeben.")


def resolve_industry_modes(heat_mode=None, dispatch_mode=None):
    return (_choose_setting(heat_mode, INDUSTRY_HEAT_MODE, "heat"),
            _choose_setting(dispatch_mode, INDUSTRY_DISPATCH_MODE, "dispatch"))


def _array(a, n, label):
    arr = np.asarray(a, dtype=float)
    if arr.shape != (n,) or not np.isfinite(arr).all():
        raise ValueError(f"{label}: erwartet {n} endliche Stundenwerte, erhalten {arr.shape}")
    return arr


def _safe_scenario_file(directory: Path, filename: str) -> Path:
    if not filename or Path(filename).name != filename:
        raise ValueError(f"Unsicherer Szenario-Dateiname: {filename!r}")
    result = directory / filename
    if not result.is_file():
        raise FileNotFoundError(result)
    return result


def load_industry(data, n_hours):
    """Industrie aus der *aktuellen* Szenario-JSON/NPZ/CSV laden."""
    folder = Path(data.scenario_file_path)
    path = folder / f"{data.scenario_name}.json"
    with path.open(encoding="utf-8") as f:
        scenario = json.load(f)
    industries = scenario.get("values", {}).get("industrial_sites", [])
    if len(industries) != 1:
        raise ValueError(f"Dieses Modell verlangt genau einen Industriestandort; gefunden: {len(industries)}")
    industry = industries[0]
    pos = np.asarray(industry["position"], dtype=float)
    if pos.shape != (2,) or not np.isfinite(pos).all():
        raise ValueError("Industrieposition ist ungültig")
    profile_path = _safe_scenario_file(folder, industry["profile_file"])
    source_path = _safe_scenario_file(folder, industry["sources_file"])
    with np.load(profile_path, allow_pickle=False) as archive:
        profiles = np.asarray(archive["source_profiles"], dtype=float)
        site_profile = np.asarray(archive["site_profile"], dtype=float)
    if profiles.ndim != 2 or profiles.shape[1] != n_hours:
        raise ValueError(
            "PFA-Profile und Netzwerkzeitschritte stimmen nicht überein. "
            f"PFA={profiles.shape}; Netzstunden={n_hours}. "
            "Stündliches 8760h-Modell verwenden; keine stille Interpolation."
        )
    if not np.isfinite(profiles).all() or np.any(profiles < 0):
        raise ValueError("PFA-Quellen enthalten ungültige oder negative Energiemengen")
    if not np.allclose(profiles.sum(axis=0), _array(site_profile, n_hours, "Standortprofil"), atol=1e-5, rtol=1e-8):
        raise ValueError("Die Summe der Quellenprofile entspricht nicht dem Standortprofil")
    source_info = pd.read_csv(source_path, sep=";", encoding="utf-8-sig")
    if len(source_info) != profiles.shape[0] or "Temperatur_C" not in source_info:
        raise ValueError("Quellenmetadaten (Temperaturen/Reihenfolge) passen nicht zur NPZ-Datei")
    temps = pd.to_numeric(source_info["Temperatur_C"], errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(temps).all():
        raise ValueError("Quellentemperaturen fehlen. Keine unbegründete direkte Einspeisung zulässig.")
    # PFA-Generator: 1h-Intervalle mit Zahlenwerten in kWh => mittlere kW in diesem Intervall.
    if industry.get("profile_resolution_hours") != 1:
        raise ValueError("Nur PFA-Profile mit 1 Stunde Zeitauflösung werden unterstützt")
    return {"metadata": industry, "position": tuple(pos), "source_profiles_kW": profiles,
            "temperatures_C": temps, "source_info": source_info}


def _children_edges(topology):
    return [(parent, child) for parent, children in topology.items() for child in children]


def _distance_and_projection(point, a, b):
    a, b, point = (np.asarray(v, dtype=float) for v in (a, b, point))
    ab = b - a
    norm2 = float(ab @ ab)
    t = np.clip(float((point - a) @ ab / norm2), 0.0, 1.0) if norm2 > 0 else 0.0
    projection = a + t * ab
    return float(np.linalg.norm(point - projection)), tuple(projection), float(t)


def attach_wh_to_topology(data, industrial_position):
    """Industrie an nächstgelegenem Trassen-SEGMENT anschließen (nicht private Hausleitung).

    Falls der Projektionspunkt innerhalb eines Segments liegt, wird diese
    Leitung geteilt. Das bestehende Baummodell bleibt ein Baum mit EH1 als
    *Orientierungswurzel*; tatsächliche Strömungsrichtungen werden später
    aus den vorzeichenbehafteten Massenströmen ermittelt.
    """
    nodes = data.pipeline_nodes
    topo = data.pipeline_topology
    if "EH1" not in nodes:
        raise ValueError("EH1 fehlt in den Netzknoten")
    if "WH1" in nodes:
        raise ValueError("WH1 ist schon in der Topologie vorhanden")
    edges = _children_edges(topo)
    if not edges:
        raise ValueError("Leere Wärmenetztopologie")
    edges_road = [
        (p, c) for p, c in edges
        if nodes[p].get("role") != "bldg" and nodes[c].get("role") != "bldg"
           and not p.lower().startswith("bldg") and not c.lower().startswith("bldg")
    ]
    if not edges_road:
        # bei ungewöhnlichen sehr kleinen Topologien Verbindung an EH
        best_node = "EH1"
        connection = tuple(nodes[best_node]["pos"])
    else:
        candidates = []
        for p, c in edges_road:
            d, proj, t = _distance_and_projection(industrial_position, nodes[p]["pos"], nodes[c]["pos"])
            candidates.append((d, p, c, proj, t))
        _, parent, child, connection, t = min(candidates, key=lambda e: e[0])
        tol = 1e-7
        if t <= tol:
            best_node = parent
            connection = tuple(nodes[best_node]["pos"])
        elif t >= 1.0 - tol:
            best_node = child
            connection = tuple(nodes[best_node]["pos"])
        else:
            best_node = "node_industrie_anschluss"
            if best_node in nodes:
                raise ValueError(f"Knotenname {best_node} bereits belegt")
            nodes[best_node] = {"role": "node", "pos": list(connection)}
            topo[parent] = [best_node if v == child else v for v in topo[parent]]
            topo[best_node] = [child]
    length = float(np.linalg.norm(np.asarray(industrial_position) - np.asarray(connection)))
    if length <= 1e-7:
        raise ValueError("Industrie und Anschlussknoten fallen zusammen; industrielle Anschlussleitung nicht definiert")
    nodes["WH1"] = {"role": "WH", "pos": list(industrial_position)}
    topo.setdefault(best_node, []).append("WH1")
    topo["WH1"] = []
    # Verbindung aller Knoten + Zyklenfreiheit prüfen
    visited, active = set(), set()
    def walk(n):
        if n in active or n in visited:
            raise ValueError("Topologie ist kein eindeutiger Baum")
        active.add(n)
        for c in topo.get(n, []):
            walk(c)
        active.remove(n)
        visited.add(n)
    walk("EH1")
    if visited != set(nodes):
        raise ValueError("Topologie enthält nicht erreichbare Netzknoten")
    return {"node_id": "WH1", "connection_node": best_node,
            "connection_position": list(connection), "connection_length_m": length}



def build_industry_envelope(industry, T_supply, *, heat_mode,
                            direct_approach_K=INDUSTRY_DIRECT_APPROACH_K,
                            hp_eta_carnot=INDUSTRY_HP_ETA_CARNOT,
                            hp_evaporator_approach_K=INDUSTRY_HP_EVAP_APPROACH_K,
                            hp_condenser_approach_K=INDUSTRY_HP_COND_APPROACH_K):
    """Zeit- und quellenweise zulässige Wärmeleistung in kW.

    ACHTUNG: Die Maxima der direkten und der HP-Option sind getrennte
    Alternativen. Bei einer Quelle dürfen sie NICHT einfach addiert werden:
        Q_direct + Q_hp * (1 - 1/COP) <= Q_source_input.
    Bei direkter Einspeisung ist COP=inf (elektrische Leistung=0).
    HP ist nur für Quellen erlaubt, die direkt nicht temperiert genug sind.
    """
    if heat_mode not in ("direct_only", "all_sources_hp"):
        raise ValueError("Unbekannter heat_mode")
    source = np.asarray(industry["source_profiles_kW"], dtype=float)
    temperatures = np.asarray(industry["temperatures_C"], dtype=float)
    t_sup = np.asarray(T_supply, dtype=float)
    n_sources, n_hours = source.shape
    if t_sup.shape != (n_hours,) or not np.isfinite(t_sup).all():
        raise ValueError("Ungültiges Netzvorlauftemperaturprofil")
    if any(v < 0 for v in (direct_approach_K, hp_evaporator_approach_K, hp_condenser_approach_K)):
        raise ValueError("Temperaturansätze müssen >=0 K sein")
    if not 0.0 < float(hp_eta_carnot) < 1.0:
        raise ValueError("HP-Carnot-Güte muss zwischen 0 und 1 liegen")
    direct = np.zeros_like(source)
    hp = np.zeros_like(source)
    hp_electric_per_output = np.zeros_like(source)
    hp_cop = np.full_like(source, np.inf)
    for i, source_t in enumerate(temperatures):
        direct_mask = source_t >= t_sup + direct_approach_K
        direct[i, direct_mask] = source[i, direct_mask]
        if heat_mode == "all_sources_hp":
            hp_mask = ~direct_mask & (source[i] > 0)
            if np.any(hp_mask):
                condenser_K = t_sup[hp_mask] + hp_condenser_approach_K + 273.15
                evaporator_K = source_t - hp_evaporator_approach_K + 273.15
                lift = condenser_K - evaporator_K
                if np.any(lift <= 0):
                    raise ValueError("Ungültiger Temperaturhub für Industrie-WP")
                cop = np.clip(hp_eta_carnot * condenser_K / lift, 1.05, 8.0)
                hp[i, hp_mask] = source[i, hp_mask] * cop / (cop - 1.0)
                hp_electric_per_output[i, hp_mask] = 1.0 / cop
                hp_cop[i, hp_mask] = cop
    return {
        "source_input_kW": source,
        "direct_max_kW": direct,
        "hp_max_kW": hp,
        "hp_electric_per_output": hp_electric_per_output,
        "hp_cop": hp_cop,
        "hp_total_capacity_kW": None,
        "heat_mode": heat_mode,
    }


def build_thermal_availability(industry, T_supply, *, direct_approach_K=5.0,
                               hp_eta_carnot=None, hp_max_output_kw=None,
                               hp_evaporator_approach_K=5.0,
                               hp_condenser_approach_K=5.0):
    """Kompatibilität für den bisherigen API-Aufruf. Keine gemeinsame Summierung beider Wege."""
    mode = "direct_only" if hp_eta_carnot is None else "all_sources_hp"
    envelope = build_industry_envelope(
        industry, T_supply, heat_mode=mode, direct_approach_K=direct_approach_K,
        hp_eta_carnot=(INDUSTRY_HP_ETA_CARNOT if hp_eta_carnot is None else hp_eta_carnot),
        hp_evaporator_approach_K=hp_evaporator_approach_K,
        hp_condenser_approach_K=hp_condenser_approach_K)
    possible = envelope["direct_max_kW"] + envelope["hp_max_kW"]
    return possible, envelope["hp_electric_per_output"], envelope["hp_max_kW"] > 0


def _finalize_source_dispatch(envelope, direct_used, hp_used, demand_kW, *,
                              hp_max_output_kw=None, label):
    source = envelope["source_input_kW"]
    direct_max = envelope["direct_max_kW"]
    hp_max = envelope["hp_max_kW"]
    fraction = envelope["hp_electric_per_output"]
    direct_used = np.asarray(direct_used, dtype=float)
    hp_used = np.asarray(hp_used, dtype=float)
    demand = np.asarray(demand_kW, dtype=float)
    if direct_used.shape != source.shape or hp_used.shape != source.shape:
        raise ValueError("Optimierer-Einspeisungen benötigen die Matrixform (n_Quellen,8760)")
    if demand.shape != (source.shape[1],):
        raise ValueError("Ungültige Verbrauchszeitreihe")
    if not np.isfinite(direct_used).all() or not np.isfinite(hp_used).all():
        raise ValueError("Einspeisungen enthalten NaN/Inf")
    tol = 1e-6
    if np.any(direct_used < -tol) or np.any(hp_used < -tol):
        raise ValueError("Negative Einspeisung ist nicht erlaubt")
    if np.any(direct_used > direct_max + tol) or np.any(hp_used > hp_max + tol):
        raise ValueError("Mindestens eine Quelleneinspeisung überschreitet die thermische Obergrenze")
    waste_used = direct_used + hp_used * (1.0 - fraction)
    if np.any(waste_used > source + tol):
        raise ValueError("Quellenenergie mehrfach genutzt – unzulässige Doppelzählung")
    hp_total = hp_used.sum(axis=0)
    if hp_max_output_kw is not None:
        if not float(hp_max_output_kw) > 0:
            raise ValueError("hp_max_output_kw muss positiv sein")
        if np.any(hp_total > float(hp_max_output_kw) + tol):
            raise ValueError("WP-Summenleistung überschreitet ihre Kapazitätsgrenze")
    total = direct_used.sum(axis=0) + hp_total
    if np.any(total > demand + tol):
        raise ValueError("Industrieeinspeisung übersteigt die Verbraucherabnahme")
    return {
        "used_source_direct_kW": direct_used,
        "used_source_hp_output_kW": hp_used,
        "used_source_heat_to_grid_kW": direct_used + hp_used,
        "used_heat_to_grid_kW": total,
        "industrial_hp_electric_kW": (hp_used * fraction).sum(axis=0),
        "used_source_waste_heat_kW": waste_used.sum(axis=0),
        "available_heat_to_grid_kW": (direct_max + hp_max).sum(axis=0),
        "discarded_or_unusable_waste_heat_kW": np.maximum(source.sum(axis=0) - waste_used.sum(axis=0), 0),
        "EH_building_heat_kW": np.maximum(demand - total, 0.0),
        "dispatch_label": label,
    }


def dispatch_industrial_heat(industry, T_supply, Q_consumers_kw, *,
                             direct_approach_K=5.0, hp_eta_carnot=None,
                             hp_max_output_kw=None, envelope=None):
    """Verpflichtende PRIORITÄT für INDUSTRIE soweit nutzbar und Nachfrage vorhanden.

    'forced' erzwingt die BetriebsSTRATEGIE, nicht die Abnahme unverkäuflicher
    Überschüsse. Wärmeüberschüsse werden abgeregelt. Direkte Wärme zuerst,
    danach Wärmepumpe in aufsteigender Stromintensität je Stunde.
    """
    if envelope is None:
        mode = "direct_only" if hp_eta_carnot is None else "all_sources_hp"
        envelope = build_industry_envelope(
            industry, T_supply, heat_mode=mode, direct_approach_K=direct_approach_K,
            hp_eta_carnot=INDUSTRY_HP_ETA_CARNOT if hp_eta_carnot is None else hp_eta_carnot)
    direct_max, hp_max = envelope["direct_max_kW"], envelope["hp_max_kW"]
    elec_fraction = envelope["hp_electric_per_output"]
    demand = np.maximum(np.asarray(Q_consumers_kw, dtype=float), 0.0)
    if demand.shape != (direct_max.shape[1],):
        raise ValueError("Wärmebedarfszeitreihe stimmt nicht mit Industrieprofil überein")
    direct = np.zeros_like(direct_max)
    hp = np.zeros_like(hp_max)
    remaining = demand.copy()
    for i in range(direct_max.shape[0]):
        direct[i] = np.minimum(direct_max[i], remaining)
        remaining -= direct[i]
    hp_remaining = np.full_like(remaining, np.inf if hp_max_output_kw is None else float(hp_max_output_kw))
    for t in range(len(remaining)):
        for i in np.argsort(elec_fraction[:, t]):
            if hp_max[i, t] <= 0:
                continue
            used = min(hp_max[i, t], remaining[t], hp_remaining[t])
            hp[i, t] = used
            remaining[t] -= used
            hp_remaining[t] -= used
    return _finalize_source_dispatch(envelope, direct, hp, demand,
                                     hp_max_output_kw=hp_max_output_kw,
                                     label="forced_priority")


def validate_optimizer_dispatch(envelope, demand_kW, direct_to_grid_kW,
                                hp_to_grid_kW=None, *, hp_max_output_kw=None):
    """Nimmt fertige quellenweise Entscheidungen aus EXTERNER Optimierung entgegen.

    Erwartet zwei Matrizen (Anzahl Q-Quellen, 8760): direkte Einspeisung
    und thermische HP-Ausgangsleistung, jeweils kW.
    Strombedarf der HP wird daraufhin exakt gemäß gespeicherter COP-Näherung
    abgeleitet. Die Optimierung selbst wird hier bewusst NICHT erfunden.
    """
    direct = np.asarray(direct_to_grid_kW, dtype=float)
    hp = np.zeros_like(direct) if hp_to_grid_kW is None else hp_to_grid_kW
    return _finalize_source_dispatch(envelope, direct, hp, demand_kW,
                                     hp_max_output_kw=hp_max_output_kw,
                                     label="optimizer_result")

def signed_flows_on_tree(topology, buildings_kg_s, wh_kg_s, *, root="EH1"):
    """Exakte Knoten-MASSENbilanz für gegebene Einspeisemengen auf einem Baum.

    Positives Vorzeichen: EH1-orientierte Kante parent->child;
    negatives Vorzeichen: physikalische Strömung child->parent.
    """
    wh_kg_s = np.asarray(wh_kg_s, dtype=float)
    net = {key: np.asarray(val, dtype=float).copy() for key, val in buildings_kg_s.items()}
    if "WH1" in net:
        raise ValueError("WH1 darf kein Verbraucher sein")
    net["WH1"] = -wh_kg_s
    flows = {}
    def dfs(n):
        total = net.get(n, np.zeros_like(wh_kg_s)).copy()
        for child in topology.get(n, []):
            sub = dfs(child)
            flows[(n, child)] = sub
            total += sub
        return total
    EH = dfs(root)
    if np.any(EH < -1e-7):
        raise ValueError("Die Industrie würde am EH einen Netto-Rückfluss erzwingen")
    return flows, np.maximum(EH, 0.0)


def _apply_signed_flows(data, param, pipe_massflows):
    rho = float(data.heat_grid_data["fluid"]["rho_f"])
    param["pipe_massflows_signed"] = pipe_massflows
    # Gleicher Schlüssel wie im bisherigen Modell, nun mit tatsächlichen Vorzeichen.
    param["pipe_massflows"] = pipe_massflows
    for (p, c), mass in pipe_massflows.items():
        key = f"{p}->{c}"
        if key not in data.pipeline:
            raise KeyError(f"Leitungssegment {key} fehlt")
        flow = mass / rho
        positive_abs = np.abs(flow)
        active = positive_abs > 1e-12
        data.pipeline[key]["flow"] = flow
        data.pipeline[key]["flow_max"] = float(positive_abs.max())
        data.pipeline[key]["flow_min"] = float(positive_abs[active].min()) if np.any(active) else 0.0
        data.pipeline[key]["flow_reversal_hours"] = int(np.count_nonzero(flow < -1e-12))


def _pipe_pressure_drop(data, param, t):
    """Reibung und lokale Verluste für Vorlauf + Rücklauf (2 gleiche Rohre)."""
    import fluids
    rho = float(data.heat_grid_data["fluid"]["rho_f"])
    nu = float(data.heat_grid_data["fluid"]["nu_f"])
    result = {}
    for key, pipe in data.pipeline.items():
        V = abs(float(pipe["flow"][t]))
        if V < 1e-12:
            result[key] = 0.0
            continue
        props = param["pipe_dict"][pipe["DN"]]
        d = float(props["Inner diameter (pipe) (mm)"]) / 1000.0
        rough = float(props["Roughness (mm)"]) / 1000.0
        area = math.pi * d * d / 4
        v = V / area
        Re = v * d / nu
        f = fluids.friction.friction_factor(Re=Re, eD=rough / d)
        dp_pair = 2 * f * (float(pipe["length"]) / d) * rho * v * v / 2
        dp_local = float(pipe.get("zeta", 0.0)) * rho * v * v / 2
        result[key] = dp_pair + dp_local
    return result


def compute_dual_pumps(data, param, m_EH, m_WH):
    """Überschlägige Druckpfad-/Pumpenberechnung für ZWEI Einspeiser.

    Strömungsrichtungen aus den bilanzierten Nettoströmen; getrennte
    kritische Druckverlustpfade von EH1 und WH1 bis zu ihren erreichbaren
    Verbrauchern. Keine Drucknetz-/Regelventiloptimierung.
    """
    import networkx as nx
    rho = float(data.heat_grid_data["fluid"]["rho_f"])
    eta = float(data.heat_grid_data["pump"]["eta_pump"])
    n = len(m_EH)
    dp_subst = float(data.heat_grid_data.get("dp_substation", 0))
    dp_EH = float(data.heat_grid_data.get("dp_energy_hub", 0))
    dp_WH = float(data.heat_grid_data.get("dp_industry", dp_EH))
    consumers = set(param["Q_by_node"])
    P_EH, P_WH = np.zeros(n), np.zeros(n)
    head_EH, head_WH = np.zeros(n), np.zeros(n)
    for t in range(n):
        drops = _pipe_pressure_drop(data, param, t)
        graph = nx.DiGraph()
        for key, pipe in data.pipeline.items():
            v = float(pipe["flow"][t])
            if abs(v) < 1e-12:
                continue
            u, w = pipe["from"], pipe["to"]
            if v < 0:
                u, w = w, u
            graph.add_edge(u, w, weight=drops[key])
        for source, mass, power, head, dp_src in (
                ("EH1", m_EH, P_EH, head_EH, dp_EH),
                ("WH1", m_WH, P_WH, head_WH, dp_WH),
        ):
            if mass[t] <= 1e-12:
                continue
            paths = nx.single_source_dijkstra_path_length(graph, source, weight="weight")
            critical = max((dp for k, dp in paths.items() if k in consumers), default=0.0)
            total_dp = critical + dp_subst + dp_src
            head[t] = total_dp
            power[t] = float(mass[t] / rho) * total_dp / eta
    P = P_EH + P_WH
    safety = float(data.heat_grid_data.get("pump_safety_factor", 1.3))
    data.heat_grid_data["P_pump"] = P
    data.heat_grid_data["pump_power_design"] = float(P.max()) / 1000 * safety
    data.heat_grid_data["dp_pump_max"] = float(max(head_EH.max(), head_WH.max())) * safety
    param["dp_pump_profile"] = np.maximum(head_EH, head_WH)
    param["P_pump_EH_W"] = P_EH
    param["P_pump_WH_W"] = P_WH
    param["dp_pump_EH_Pa"] = head_EH
    param["dp_pump_WH_Pa"] = head_WH
    return data, param

def design_pumps_two_scenarios(data, param, m_consumers, m_wh_design,
                               actual_flows, m_eh_actual, m_wh_actual):
    """Konservative Pumpen-Vorauslegung: EH-only und technisch WH-max.

    Pumpen von EH1 und WH1 werden GETRENNT bemessen. Der reale/aktuelle
    Fahrplan bleibt fuer P_pump und die Betriebs-Zeitreihen erhalten.
    Dies ist KEINE Nachrechnung der spaeteren Pyomo-Entscheidungen.
    """
    grid = data.heat_grid_data
    cases = {}
    try:
        for name, wh in (
                ("EH_only", np.zeros_like(m_wh_design)),
                ("WH_max", np.asarray(m_wh_design, dtype=float)),
        ):
            flows_case, m_eh_case = signed_flows_on_tree(
                data.pipeline_topology, m_consumers, wh
            )
            _apply_signed_flows(data, param, flows_case)
            data, param = compute_dual_pumps(data, param, m_eh_case, wh)
            cases[name] = {
                "EH1_power_max_W": float(np.max(param["P_pump_EH_W"])),
                "WH1_power_max_W": float(np.max(param["P_pump_WH_W"])),
                "EH1_dp_max_Pa": float(np.max(param["dp_pump_EH_Pa"])),
                "WH1_dp_max_Pa": float(np.max(param["dp_pump_WH_Pa"])),
            }
    finally:
        # Die beiden Auslegungsfaelle duerfen die Betriebswerte NICHT ueberschreiben.
        _apply_signed_flows(data, param, actual_flows)
        for edge, vmax in param["pipe_design_envelope_max_vol_m3_s"].items():
            data.pipeline[f"{edge[0]}->{edge[1]}"]["flow_max"] = vmax
        data, param = compute_dual_pumps(data, param, m_eh_actual, m_wh_actual)

    safety = float(grid.get("pump_safety_factor", 1.3))
    if not np.isfinite(safety) or safety <= 0:
        raise ValueError("pump_safety_factor muss positiv und endlich sein")
    p_eh_kw = safety * max(c["EH1_power_max_W"] for c in cases.values()) / 1000.0
    p_wh_kw = safety * max(c["WH1_power_max_W"] for c in cases.values()) / 1000.0
    dp_eh = safety * max(c["EH1_dp_max_Pa"] for c in cases.values())
    dp_wh = safety * max(c["WH1_dp_max_Pa"] for c in cases.values())

    # Bestehende Kostenrechnung verwendet pump_power_design [kW].
    # Nicht max(EH+WH), sondern Summe der einzeln ausgelegten Pumpen.
    grid["pump_power_design"] = p_eh_kw + p_wh_kw
    grid["dp_pump_max"] = max(dp_eh, dp_wh)
    grid["pump_power_design_EH_kW"] = p_eh_kw
    grid["pump_power_design_WH_kW"] = p_wh_kw
    grid["dp_pump_design_EH_Pa"] = dp_eh
    grid["dp_pump_design_WH_Pa"] = dp_wh
    param["pump_design_cases"] = cases
    param["pump_design_method"] = "EH_only_und_WH_max_vor_Pyomo"
    # grid['P_pump'] und param['P_pump_*_W'] bleiben der aktuelle Betrieb.
    return data, param


def _safe_select_diameters(data, param):
    """Bestehende Dimensionierung mit abgesicherter Nullflussbehandlung."""
    # Nullflusssegmente erhalten DN_min statt Re=0 an fluids.friction_factor zu geben.
    no_flow = [p for p in data.pipeline.values() if p["flow_max"] < 1e-12]
    for pipe in no_flow:
        pipe["flow_max"] = 1e-13
    try:
        return single.calc_diameter_2leiter(data, param)
    finally:
        for pipe in no_flow:
            pipe["flow_max"] = 0.0




def _dimension_for_operating_envelope(data, param, m_consumers, m_design_WH):
    """Rohre für beide Extremfälle auslegen: EH allein und max. WH-Priorität.

    Kein Bedarf für binäre quellenbezogene Wegevariablen, solange die Trasse
    baumförmig bleibt. Die Dimensionierung verwendet den größten ABSOLUTbetrag
    je Rohr aus beiden 8760h-Szenarien. Das ist konservativ für Zwischenzustände
    auf einem Baum.
    """
    flows_no, _ = signed_flows_on_tree(data.pipeline_topology, m_consumers, np.zeros_like(m_design_WH))
    flows_yes, _ = signed_flows_on_tree(data.pipeline_topology, m_consumers, m_design_WH)
    rho = float(data.heat_grid_data["fluid"]["rho_f"])
    peak_vol = {}
    for edge in flows_no:
        peak_vol[edge] = max(float(np.max(np.abs(flows_no[edge]))),
                             float(np.max(np.abs(flows_yes[edge])))) / rho
        data.pipeline[f"{edge[0]}->{edge[1]}"]["flow_max"] = peak_vol[edge]
        data.pipeline[f"{edge[0]}->{edge[1]}"]["flow_design_max"] = peak_vol[edge]
    data, param = _safe_select_diameters(data, param)
    param["pipe_design_envelope_max_vol_m3_s"] = peak_vol
    return data, param


def _make_industry_costs(data, param):
    """Bisherige Netz-Investitionsformeln; EH/WH-Wärmepumpe nicht mitgerechnet."""
    grid = data.heat_grid_data
    inv_pipes = sum(float(p["length"]) * 2.0 * float(param["pipe_dict"][p["DN"]]["Pipe Cost (€/m)"])
                    for p in data.pipeline.values())
    inv_construction = sum(float(p["length"]) * float(param["pipe_dict"][p["DN"]]["Construction Cost (€/m)"])
                           for p in data.pipeline.values())
    pipe_ann = grid["pipe"]["pipe_ann_factor"]
    pipes_annual = (inv_pipes + inv_construction) * pipe_ann
    pipes_om = (inv_pipes + inv_construction) * grid["pipe"]["cost_om_pipe"]
    pump_inv = grid["pump_power_design"] * grid["pump"]["inv_pump"]
    pump_annual = pump_inv * grid["pump"]["pump_ann_factor"]
    pump_om = pump_inv * grid["pump"]["cost_om_pump"]
    pump_kWh_a = float(np.sum(grid["P_pump"])) / 1000.0
    costs = {
        "pipe_investment_EUR": inv_pipes,
        "construction_investment_EUR": inv_construction,
        "pipe_annuity_EUR_a": pipes_annual,
        "pipe_om_EUR_a": pipes_om,
        "pump_investment_EUR": pump_inv,
        "pump_annuity_EUR_a": pump_annual,
        "pump_om_EUR_a": pump_om,
        "pump_electric_kWh_a": pump_kWh_a,
        "costs_exclude_industrial_hp": True,
        "costs_exclude_substations": True,
    }
    return costs

def _wh_connection_pipe(data):
    """Ermittelt die exklusive Anschlussleitung zum Industriestandort."""
    matches = [
        (key, pipe)
        for key, pipe in data.pipeline.items()
        if pipe["to"] == "WH1"
    ]

    if len(matches) != 1:
        raise RuntimeError(
            f"Eine WH1-Anschlussleitung erwartet, gefunden: {len(matches)}"
        )

    return matches[0]


def _nominal_wh_connection_loss_kW(data, param):
    """Berechnet die theoretischen Verluste einer warmen WH1-Leitung."""

    _, pipe = _wh_connection_pipe(data)

    ks = float(
        param["pipe_dict"][pipe["DN"]]["symmetrical heat loss factor"]
    )

    ua = (
            2.0
            * math.pi
            * float(data.heat_grid_data["k_soil"])
            * ks
            * float(pipe["length"])
    )

    ts = np.asarray(
        data.heat_grid_data["T_supply_EH"], dtype=float
    )
    tr = np.asarray(
        data.heat_grid_data["T_return_EH"], dtype=float
    )
    soil = np.asarray(
        data.heat_grid_data["T_soil"], dtype=float
    )

    return ua * (ts + tr - 2.0 * soil) / 1000.0



def _correct_wh_connection_losses(data, param):
    """
    Setzt die Wärmeverluste der WH1-Leitung bei Stillstand auf null.

    Annahme: Die Anschlussleitung ist bei Nullfluss abgesperrt
    und wird nicht aktiv warmgehalten.
    """

    pipe_id, wh_pipe = _wh_connection_pipe(data)

    active = (
            np.abs(np.asarray(wh_pipe["flow"], dtype=float)) > 1e-12
    )

    for key in (
            "heat_loss_pipe",
            "heat_loss_supply",
            "heat_loss_return",
    ):
        wh_pipe[key] = np.where(
            active,
            np.asarray(wh_pipe[key], dtype=float),
            0.0,
        )

    wh_pair = (wh_pipe["from"], wh_pipe["to"])
    param["heat_loss_pipe"][wh_pair] = wh_pipe["heat_loss_pipe"]

    wh_pipe["heat_loss_density"] = (
            float(np.sum(wh_pipe["heat_loss_pipe"]))
            / 1000.0
            / max(float(wh_pipe["length"]), 1e-12)
    )

    pipe_sum = np.sum(
        np.stack([
            np.asarray(p["heat_loss_pipe"], dtype=float)
            for p in data.pipeline.values()
        ]),
        axis=0,
    )

    positive_pipe = np.maximum(pipe_sum, 0.0)

    param["annual_heat_loss_pipes_signed"] = float(
        pipe_sum.sum()
    )
    param["annual_heat_loss_pos"] = float(
        positive_pipe.sum()
    )
    param["annual_heat_gain_pos"] = float(
        np.maximum(-pipe_sum, 0.0).sum()
    )

    subst = np.asarray(
        param["heat_loss_substation"], dtype=float
    )

    param["annual_heat_loss_pos_total"] = (
            float(subst.sum()) + float(positive_pipe.sum())
    )

    data.heat_grid_data["total_losses_heating_network"] = (
            subst + positive_pipe
    )

    param["industry_WH_connection_active_hours"] = int(
        np.count_nonzero(active)
    )
    param["industry_WH_connection_pipe_id"] = pipe_id

    return (
        np.maximum(
            np.asarray(wh_pipe["heat_loss_pipe"], dtype=float),
            0.0,
        ),
        positive_pipe,
    )


def _save_industry_topology(data, folder: Path):
    """Geänderten Netzbaum szenariospezifisch speichern; alte Topologie bleibt erhalten."""
    obj = {"nodes": data.pipeline_nodes, "edges": data.pipeline_topology,
           "description": "EH1-orientierte Geometrie. Reale Flussrichtung kann je Stunde abweichen."}
    with (folder / "topologie_2leiter_industrie.json").open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def _plot_industry_topology(data, folder: Path):
    """Kompakte Darstellung des Industrieanschlusses und des bestehenden Netzes."""
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10, 6))
    for p, c in _children_edges(data.pipeline_topology):
        x1, y1 = data.pipeline_nodes[p]["pos"]
        x2, y2 = data.pipeline_nodes[c]["pos"]
        ax.plot([x1, x2], [y1, y2], color=("darkorange" if c == "WH1" else "steelblue"),
                linewidth=(2.6 if c == "WH1" else 1.4), zorder=1)
    for key, node in data.pipeline_nodes.items():
        x, y = node["pos"]
        role = node.get("role", "node")
        if key == "EH1":
            ax.scatter(x, y, s=100, c="firebrick", label="Energy Hub (EH1)", zorder=4)
        elif key == "WH1":
            ax.scatter(x, y, s=100, c="darkorange", marker="D",
                       label="Industrieabwärme (WH1)", zorder=4)
        elif role == "bldg" or key.startswith("bldg"):
            ax.scatter(x, y, s=11, c="steelblue", alpha=0.8, zorder=3)
    ax.set_aspect("equal", adjustable="datalim")
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    ax.set_title("Wärmenetz mit zwei Einspeisern – Topologie (nicht Flussrichtung)")
    ax.legend(loc="best")
    ax.grid(alpha=0.15)
    fig.tight_layout()
    fig.savefig(folder / "netzlayout_2leiter_industrie.png", dpi=180)
    plt.close(fig)


def plot_industry_network_after_optimization(data):
    """Visualisiert optimierte Clusterwochen hydraulisch, ohne das Netz zu verändern.

    Jahreskarten sind mit den Clusterhäufigkeiten gewichtet; sie sind
    KEINE validierte 8760-h-Nachrechnung. Rohr-DN und Pumpeninvestition
    bleiben unverändert. Nur bei vorhandener 4G-Industrie aktiv.
    """
    if (data.heat_grid_data.get('heatgrid_generation') != '4G'
            or not isinstance(getattr(data, 'industry_optimization', None), dict)):
        return

    param = getattr(data, '_industry_network_plot_param', None)
    if param is None:
        raise RuntimeError('Industrie-Postplot: Netzparameter wurden nicht gespeichert.')
    result_by_year = getattr(data, 'resultsOptimization', None)
    if not isinstance(result_by_year, dict) or not result_by_year:
        raise RuntimeError('Industrie-Postplot erst nach optimizationClusters() aufrufen.')

    from types import SimpleNamespace
    import csv
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors

    dt_h = float(data.time['timeResolution']) / 3600.0
    if abs(dt_h - 1.0) > 1e-12:
        raise NotImplementedError('Industrie-Postplot benötigt Stundenwerte (3600 s).')
    steps = int(round(float(data.time['clusterLength']) /
                      float(data.time['timeResolution'])))
    clusters = [int(c) for c in data.clusters]
    if steps <= 0 or len(clusters) != int(data.time['clusterNumber']):
        raise ValueError('Industrie-Postplot: Clusterkonfiguration ungültig.')

    g = data.heat_grid_data
    rho = float(g['fluid']['rho_f'])
    cp = float(g['fluid']['c_f'])
    pipe_keys = list(data.pipeline)
    original_supply = np.asarray(g['T_supply_EH'], dtype=float)
    original_return = np.asarray(g['T_return_EH'], dtype=float)
    original_soil = np.asarray(g['T_soil'], dtype=float)
    node_mass = {key: np.asarray(arr, dtype=float)
                 for key, arr in param['building_massflow_HX'].items()}
    if any(arr.shape != (8760,) for arr in [original_supply, original_return,
                                            original_soil, *node_mass.values()]):
        raise ValueError('Industrie-Postplot: originale Netzzeitreihen nicht 8760 Stunden.')
    if sum(int(data.clusterWeights[c]) for c in clusters) * steps != 8736:
        raise ValueError('Industrie-Postplot: erwartete 8736 Clusterstunden fehlen.')

    root = (Path(data.resultPath) / 'network' /
            f'{data.scenario_name}_road_2leiter_industrie' /
            'nach_betriebsoptimierung')
    root.mkdir(parents=True, exist_ok=True)

    def _series(wh, field, n, *, divide=1000.0):
        arr = np.asarray(wh[field], dtype=float) / divide
        if arr.shape != (n,) or not np.isfinite(arr).all():
            raise ValueError(f'Industrie-Postplot: {field} hat ungültige Form/Werte: {arr.shape}')
        return arr

    def _save_map(folder, rows, name, field, title, unit, decimals=2):
        vals = np.array([r[field] for r in rows], dtype=float)
        valid = np.isfinite(vals)
        if not np.any(valid):
            raise ValueError(f'Industrie-Postplot: keine gültigen Kartendaten für {field}')
        a, b = float(vals[valid].min()), float(vals[valid].max())
        if abs(b-a) < 1e-12:
            b = a + 1.0
        norm = mcolors.Normalize(vmin=a, vmax=b)
        cmap = plt.get_cmap('viridis')
        fig, ax = plt.subplots(figsize=(12, 9))
        annotate = len(rows) <= 85
        for rec in rows:
            pipe = data.pipeline[rec['pipe_id']]
            x1, y1 = pipe['from_pos']
            x2, y2 = pipe['to_pos']
            val = float(rec[field])
            is_valid = np.isfinite(val)
            # Für MWh/m undefinierte Null-Längen-Segmente neutral zeichnen;
            # sie verzerren NICHT mehr Farbskala oder Textbeschriftungen.
            color = cmap(norm(val)) if is_valid else '0.75'
            ax.plot([x1, x2], [y1, y2], color=color, linewidth=3.0,
                    solid_capstyle='round')
            if annotate and is_valid:
                ax.text((x1+x2)/2, (y1+y2)/2, f'{val:.{decimals}f}',
                        fontsize=6, ha='center', va='center', alpha=.85)
        sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
        fig.colorbar(sm, ax=ax, label=unit, shrink=.72)
        ax.set_aspect('equal', adjustable='datalim')
        ax.set_xlabel('x [m]')
        ax.set_ylabel('y [m]')
        ax.set_title(title + '\nClustergewichtete Betriebsnäherung, 8736 h; keine 8760-h-Validierung')
        ax.grid(alpha=.15)
        fig.tight_layout()
        stem = folder / name
        fig.savefig(str(stem) + '.png', dpi=160)
        fig.savefig(str(stem) + '.svg')
        plt.close(fig)

    # Vergleichsbasis: nur JAHR 0, danach unabhängiger Vergleich.
    # Bei Basiswert ~0: absolute Toleranz statt nicht definierter Prozentzahl.
    # Diese Schwellwerte können je nach Modellmaßstab angepasst werden.
    annual_tolerance = {
        'direct_MWh': 0.01,
        'hp_heat_MWh': 0.01,
        'gross_MWh': 0.01,
        'net_MWh': 0.01,
        'connection_loss_MWh': 0.01,
        'pump_EH_MWh': 0.001,
        'pump_WH_MWh': 0.001,
    }
    pipe_tolerance = {
        'velocity_max_m_s': 0.001,
        'pressure_gradient_max_Pa_m': 0.01,
        'energy_density_MWh_m': 0.0001,
        'heat_loss_density_MWh_m': 0.0001,
        'reversal_h': 1.0,
    }
    profile_tolerance = {
        'direct_kW': 0.05,
        'hp_kW': 0.05,
        'pump_EH_kW': 0.0001,
        'pump_WH_kW': 0.0001,
    }
    plot_stems = (
        'pipeline_velocity_postopt',
        'pipeline_pressure_gradient_postopt',
        'pipeline_energy_density_postopt',
        'pipeline_heat_loss_density_postopt',
        'pipeline_flow_reversal_postopt',
        'industrie_und_pumpen_postopt',
        'beispielwoche_industrie_pumpen',
    )

    def _test_delta(reference, current, near_zero_floor):
        # Funktioniert für Skalare ebenso wie für komplette Zeitreihen.
        # Bei Zeitreihen und Rohrfeldern wird das schlimmste Element erfasst.
        ref = np.asarray(reference, dtype=float)
        cur = np.asarray(current, dtype=float)
        if ref.shape != cur.shape:
            raise ValueError('Industrie-Postplot: Vergleiche erfordern gleiche Formen.')
        delta = float(np.max(np.abs(cur - ref)))
        ref_scale = float(np.max(np.abs(ref)))
        if ref_scale < near_zero_floor:
            threshold = float(near_zero_floor)
            percent = None  # Jahr 0 nahe 0: prozentualer Vergleich unbestimmt
        else:
            threshold = 0.05 * ref_scale
            percent = 100.0 * delta / ref_scale
        return {
            'max_abs_diff': delta,
            'reference_scale': ref_scale,
            'threshold_abs': threshold,
            'deviation_percent': percent,
            'over_5_percent': bool(delta > threshold),
        }

    baseline_annual = None
    baseline_rows = None
    baseline_profiles = None
    comparison_report = []
    year_entries = sorted(result_by_year.items(), key=lambda t: int(t[0]))
    if not year_entries or int(year_entries[0][0]) != 0:
        raise ValueError('Industrie-Postplot: Stützjahr 0 als Vergleichsbasis fehlt.')

    for year, cluster_results in year_entries:
        year = int(year)
        folder = root / f'jahr_{year}'
        accum = {key: dict(energy_MWh=0.0, heat_loss_MWh=0.0,
                           velocity_max_m_s=0.0, pressure_gradient_max_Pa_m=0.0,
                           reversal_h=0.0) for key in pipe_keys}
        annual = dict(direct_MWh=0.0, hp_heat_MWh=0.0, gross_MWh=0.0,
                      net_MWh=0.0, connection_loss_MWh=0.0,
                      pump_EH_MWh=0.0, pump_WH_MWh=0.0)
        example = None
        example_gross = -1.0
        profile_parts = {name: [] for name in profile_tolerance}
        for c, medoid in enumerate(clusters):
            wh = cluster_results[c].get('industrial_wh')
            if not isinstance(wh, dict):
                raise ValueError(f'Industrie-Postplot: industrial_wh fehlt für Jahr {year}, Cluster {c}.')
            direct_matrix = np.asarray(wh['direct_W'], dtype=float) / 1000.0
            hp_matrix = np.asarray(wh['hp_output_W'], dtype=float) / 1000.0
            if (direct_matrix.ndim != 2 or hp_matrix.shape != direct_matrix.shape or
                    direct_matrix.shape[1] != steps or
                    not np.isfinite(direct_matrix).all() or not np.isfinite(hp_matrix).all()):
                raise ValueError(f'Industrie-Postplot: Quellmatrizen ungültig in Jahr {year}, Cluster {c}.')
            gross = _series(wh, 'gross_W', steps)
            net = _series(wh, 'net_W', steps)
            wh_loss_opti = _series(wh, 'connection_loss_W', steps)
            if (not np.allclose(direct_matrix.sum(axis=0) + hp_matrix.sum(axis=0), gross, atol=.01)
                    or not np.allclose(gross - net, wh_loss_opti, atol=.01)):
                raise ValueError(f'Industrie-Postplot: Pyomo-Wärmebilanz in Jahr {year}, Cluster {c} inkonsistent.')

            start = medoid * steps
            sl = slice(start, start + steps)
            if start < 0 or start + steps > 8760:
                raise ValueError(f'Industrie-Postplot: ungültiges Zeitfenster Cluster {c}.')
            weight = int(data.clusterWeights[medoid])
            if weight <= 0:
                raise ValueError(f'Industrie-Postplot: ungültiges Clustergewicht {weight}.')
            delta_t = original_supply[sl] - original_return[sl]
            if np.any((gross > 1e-9) & (delta_t <= 1e-9)):
                raise ValueError(f'Industrie-Postplot: kein Temperaturhub in Jahr {year}, Cluster {c}.')
            m_wh = np.divide(gross*1000.0, cp*delta_t,
                             out=np.zeros_like(gross), where=delta_t > 1e-9)
            buildings = {node: arr[sl] for node, arr in node_mass.items()}
            m_build = sum(buildings.values(), np.zeros(steps))
            if (m_wh > m_build + 1e-4).any():
                raise ValueError(f'Industrie-Postplot: WH1 übersteigt die Gebäudemassenströme (Jahr {year}, Cluster {c}).')
            flows, m_eh = signed_flows_on_tree(data.pipeline_topology, buildings, m_wh)

            # Unabhängige 168h-Arbeitskopie: weder DN, Pumpeninvestition,
            # voroptimierte P_pump-Zeitreihe noch KPI-Bilanz überschreiben.
            week_grid = dict(g)
            week_grid['T_soil'] = original_soil[sl]
            week_grid['T_supply_EH'] = original_supply[sl]
            week_grid['T_return_EH'] = original_return[sl]
            week = SimpleNamespace(
                heat_grid_data=week_grid,
                pipeline={key: dict(pipe) for key, pipe in data.pipeline.items()},
                pipeline_topology=data.pipeline_topology,
            )
            p_week = dict(param)
            p_week['heat_loss_substation'] = np.asarray(param['heat_loss_substation'], dtype=float)[sl]
            _apply_signed_flows(week, p_week, flows)
            week, p_week = single.calc_heat_loss_pipe_simple_2leiter(week, p_week)
            connection_loss_kW, _ = _correct_wh_connection_losses(week, p_week)
            if not np.allclose(connection_loss_kW, wh_loss_opti, atol=.05, rtol=1e-5):
                raise ValueError(
                    f'Industrie-Postplot: WH1-Leitungsverlust weicht von Pyomo ab '
                    f'(Jahr {year}, Cluster {c}, max '
                    f'{np.max(np.abs(connection_loss_kW-wh_loss_opti)):.3f} kW).'
                )
            week, p_week = compute_dual_pumps(week, p_week, m_eh, m_wh)
            annual['direct_MWh'] += weight*float(direct_matrix.sum())/1000.0
            annual['hp_heat_MWh'] += weight*float(hp_matrix.sum())/1000.0
            annual['gross_MWh'] += weight*float(gross.sum())/1000.0
            annual['net_MWh'] += weight*float(net.sum())/1000.0
            annual['connection_loss_MWh'] += weight*float(wh_loss_opti.sum())/1000.0
            annual['pump_EH_MWh'] += weight*float(np.sum(p_week['P_pump_EH_W']))/1e6
            annual['pump_WH_MWh'] += weight*float(np.sum(p_week['P_pump_WH_W']))/1e6
            # Stundenprofile: dieselben acht Medoid-Wochen in allen Stützjahren.
            # Damit lösen auch veränderte Fahrpläne bei gleicher Jahressumme aus.
            profile_parts['direct_kW'].append(direct_matrix.sum(axis=0).copy())
            profile_parts['hp_kW'].append(hp_matrix.sum(axis=0).copy())
            profile_parts['pump_EH_kW'].append(
                np.asarray(p_week['P_pump_EH_W'], dtype=float).copy()/1000.0)
            profile_parts['pump_WH_kW'].append(
                np.asarray(p_week['P_pump_WH_W'], dtype=float).copy()/1000.0)

            # Stündliche Belastungen der optimierten repräsentativen Woche.
            for pipe_id, p in week.pipeline.items():
                dest = accum[pipe_id]
                q = np.asarray(p['flow'], dtype=float)
                d = float(p['d_i'])/1000.0
                if d <= 0:
                    raise ValueError(f'Unzulässiger Rohrdurchmesser in {pipe_id}')
                v = abs(q)/(np.pi*d*d/4.0)
                vmax = float(np.max(v))
                f = float(p.get('f_fric', g['pipe'].get('f_fric', .02)))
                grad = f*rho*vmax*vmax/(2.0*d)  # Original: ein Rohr, reine Reibung.
                dest['velocity_max_m_s'] = max(dest['velocity_max_m_s'], vmax)
                dest['pressure_gradient_max_Pa_m'] = max(dest['pressure_gradient_max_Pa_m'], grad)
                dest['reversal_h'] += weight*float(np.count_nonzero(q < -1e-12))
                dest['energy_MWh'] += weight*float(np.sum(cp*rho*abs(q)*delta_t))/1e6
                dest['heat_loss_MWh'] += weight*float(np.sum(p['heat_loss_pipe']))/1000.0

            # Ein beispielhafter Cluster je Jahr: der mit der höchsten WH-Bruttowärme.
            if float(gross.sum()) > example_gross:
                example_gross = float(gross.sum())
                example = dict(cluster=c, medoid=medoid, direct=direct_matrix.sum(axis=0),
                               hp=hp_matrix.sum(axis=0), gross=gross,
                               p_eh=p_week['P_pump_EH_W']/1000.0,
                               p_wh=p_week['P_pump_WH_W']/1000.0)

        hours = steps*sum(int(data.clusterWeights[c]) for c in clusters)
        annual['modelled_h'] = hours
        annual['method'] = 'cluster-weighted representative week hydraulics, not 8760h dispatch'
        annual['year'] = year
        rows = []
        for key in pipe_keys:
            p = data.pipeline[key]
            x = accum[key]
            length = float(p['length'])
            if not np.isfinite(length) or length < 0.0:
                raise ValueError(f'Industrie-Postplot: ungültige Rohrlänge {length} in {key}')

            # Unter 1 mm ist eine längenbezogene Kennzahl für ein
            # Rohrsegment hier nicht aussagekräftig. Solche Segmente
            # bleiben hydraulisch unverändert im Netz erhalten.
            valid_length = length >= 1e-3
            if not valid_length and year == 0:
                print(f'[WH1-POSTPLOT] Verbindungskante {key}: '
                      f'Länge {length:.3e} m; '
                      'MWh/m in Diagramm und Vergleich ausgeschlossen.')

            rows.append(dict(
                pipe_id=key,
                DN=p['DN'],
                length_m=length,
                energy_density_MWh_m=(x['energy_MWh'] / length
                                      if valid_length else float('nan')),
                heat_loss_density_MWh_m=(x['heat_loss_MWh'] / length
                                         if valid_length else float('nan')),
                velocity_max_m_s=x['velocity_max_m_s'],
                pressure_gradient_max_Pa_m=x['pressure_gradient_max_Pa_m'],
                reversal_h=x['reversal_h'],
            ))

        # Jedes Jahr wurde bis hierher vollständig hydraulisch nachgerechnet.
        # Jetzt wird entschieden, ob die Diagramme tatsächlich nötig sind.
        profiles = {name: np.concatenate(chunks)
                    for name, chunks in profile_parts.items()}
        details = []
        if year == 0:
            baseline_annual = {key: float(annual[key]) for key in annual_tolerance}
            baseline_rows = {
                str(row['pipe_id']): {key: float(row[key]) for key in pipe_tolerance}
                for row in rows
            }
            baseline_profiles = {key: value.copy() for key, value in profiles.items()}
            make_plots = True
        else:
            for key, floor in annual_tolerance.items():
                item = _test_delta(baseline_annual[key], annual[key], floor)
                item.update(group='jahreswert', field=key)
                details.append(item)

            for key, floor in pipe_tolerance.items():
                # Ein einziges relevantes Rohr darf einen zusätzlichen
                # Diagrammsatz auslösen; keine Mittelung über alle Rohre.
                pipe_checks = []
                for row in rows:
                    pid = str(row['pipe_id'])
                    if pid not in baseline_rows:
                        raise ValueError(f'Industrie-Postplot: Rohr {pid} nicht in Jahr 0.')
                    reference_value = baseline_rows[pid][key]
                    current_value = row[key]
                    valid_ref = np.isfinite(reference_value)
                    valid_cur = np.isfinite(current_value)
                    if not valid_ref or not valid_cur:
                        if valid_ref != valid_cur:
                            raise ValueError(
                                f'Industrie-Postplot: Gültigkeit von {key} '
                                f'für Rohr {pid} hat sich gegenüber Jahr 0 geändert.'
                            )
                        # Beide Werte sind nicht definiert: nicht vergleichen.
                        continue
                    item = _test_delta(reference_value, current_value, floor)
                    item['pipe_id'] = pid
                    pipe_checks.append(item)
                if not pipe_checks:
                    continue
                worst = max(pipe_checks,
                            key=lambda item: item['max_abs_diff'] /
                                             max(item['threshold_abs'], 1e-30))
                # Der Quotient berücksichtigt die individuelle 5-%-Grenze
                # jedes Rohres, nicht den größten Netzbezugswert.
                worst.update(group='rohr', field=key)
                details.append(worst)

            for key, floor in profile_tolerance.items():
                item = _test_delta(baseline_profiles[key], profiles[key], floor)
                item.update(group='stundenprofil', field=key)
                details.append(item)
            make_plots = any(item['over_5_percent'] for item in details)

        triggers = [f"{item['group']}.{item['field']}"
                    + (f" (Rohr {item['pipe_id']})" if 'pipe_id' in item else '')
                    for item in details if item['over_5_percent']]
        comparison_report.append({
            'year': year,
            'reference_year': 0,
            'plots_created': bool(make_plots),
            'reasons': triggers if year != 0 else ['Referenzjahr: immer plotten'],
            'checks': details,
        })
        if not make_plots:
            # Nur bekannte, von dieser Funktion erzeugte Alt-Dateien löschen,
            # damit keine veralteten Diagramme eines früheren Laufs verbleiben.
            if folder.is_dir():
                for stem in plot_stems:
                    for ext in ('.png', '.svg'):
                        old_file = folder / (stem + ext)
                        if old_file.is_file():
                            old_file.unlink()
                for fname in ('rohrwerte_postopt.csv',
                              'jahresuebersicht_postopt.json'):
                    old_file = folder / fname
                    if old_file.is_file():
                        old_file.unlink()
                if not any(folder.iterdir()):
                    folder.rmdir()
            print(f'[WH1-POSTPLOT] Jahr {year}: <=5 % gegenüber Jahr 0; '
                  'keine zusätzlichen Diagramme.')
            continue

        folder.mkdir(parents=True, exist_ok=True)
        if year != 0:
            print(f'[WH1-POSTPLOT] Jahr {year}: >5 % gegenüber Jahr 0 in '
                  + ', '.join(triggers[:5])
                  + (' ...' if len(triggers) > 5 else ''))

        maps = (
            ('pipeline_velocity_postopt', 'velocity_max_m_s',
             'Maximale Strömungsgeschwindigkeit in den Optimierungswochen', 'm/s', 2),
            ('pipeline_pressure_gradient_postopt', 'pressure_gradient_max_Pa_m',
             'Maximaler Rohrreibungs-Druckgradient in den Optimierungswochen', 'Pa/m (ein Rohr)', 1),
            ('pipeline_energy_density_postopt', 'energy_density_MWh_m',
             'Rohr-Energiedichte, clustergewichtet', 'MWh/m (8736 h)', 2),
            ('pipeline_heat_loss_density_postopt', 'heat_loss_density_MWh_m',
             'Rohr-Wärmeverlustdichte, clustergewichtet', 'MWh/m (8736 h)', 2),
            ('pipeline_flow_reversal_postopt', 'reversal_h',
             'Stunden mit Strömung entgegen der Netzreferenzrichtung',
             'h (clustergewichtet, 8736 h)', 0),
        )
        for name, field, title, unit, precision in maps:
            _save_map(folder, rows, name, field, title, unit, precision)

        with (folder/'rohrwerte_postopt.csv').open('w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter=';')
            writer.writeheader()
            writer.writerows(rows)
        with (folder/'jahresuebersicht_postopt.json').open('w', encoding='utf-8') as f:
            json.dump(annual, f, indent=2, ensure_ascii=False)

        fig, axs = plt.subplots(1, 2, figsize=(11, 4))
        axs[0].bar(0, annual['direct_MWh'], label='Direkt', color='tab:orange')
        axs[0].bar(0, annual['hp_heat_MWh'], bottom=annual['direct_MWh'],
                   label='Industrie-WP', color='tab:red')
        axs[0].bar(1, annual['net_MWh'], label='Netto am Quartier', color='tab:blue')
        axs[0].bar(1, annual['connection_loss_MWh'], bottom=annual['net_MWh'],
                   label='WH1-Leitungsverlust', color='tab:gray')
        axs[0].set_xticks([0, 1], ['WH1 erzeugt', 'WH1 verteilt'])
        axs[0].set_ylabel('MWh pro 8736 Modellstunden')
        axs[0].legend(fontsize=8)
        axs[1].bar(['EH1', 'WH1'], [annual['pump_EH_MWh'], annual['pump_WH_MWh']],
                   color=['tab:blue', 'tab:orange'])
        axs[1].set_ylabel('Pumpenstrom [MWh je 8736 Modellstunden]')
        fig.suptitle(f'Industrie/Netz – optimierter Betrieb Stützjahr {year}\n'
                     'Clustergewichtete Jahresnäherung (keine 8760-h-Simulation)')
        fig.tight_layout()
        fig.savefig(folder/'industrie_und_pumpen_postopt.png', dpi=160)
        fig.savefig(folder/'industrie_und_pumpen_postopt.svg')
        plt.close(fig)

        fig, axs = plt.subplots(2, 1, figsize=(12, 7), sharex=True)
        x = np.arange(steps)
        axs[0].stackplot(x, example['direct'], example['hp'],
                         labels=['Direktwärme', 'Industrie-WP'],
                         colors=['tab:orange', 'tab:red'], alpha=.8)
        axs[0].set_ylabel('WH1-Brutto [kW]')
        axs[0].legend(loc='upper right')
        axs[1].plot(x, example['p_eh'], label='EH1-Pumpe', color='tab:blue')
        axs[1].plot(x, example['p_wh'], label='WH1-Pumpe', color='tab:orange')
        axs[1].set_xlabel('Stunde der repräsentativen Woche')
        axs[1].set_ylabel('Elektrische Pumpenleistung [kW]')
        axs[1].legend(loc='upper right')
        axs[1].grid(alpha=.2)
        fig.suptitle(f'Optimierter Wochenbetrieb Jahr {year}, Cluster {example["cluster"]} '
                     f'(Originalwoche {example["medoid"]})')
        fig.tight_layout()
        fig.savefig(folder/'beispielwoche_industrie_pumpen.png', dpi=160)
        fig.savefig(folder/'beispielwoche_industrie_pumpen.svg')
        plt.close(fig)
        print(f'[WH1-POSTPLOT] Jahr {year}: {len(maps)} neue Rohrkarten und '
              f'2 Betriebsdiagramme erzeugt ({hours} clustergewichtete Stunden) -> {folder}')

    # Ein Vergleichsprotokoll wird IMMER geschrieben, auch für übersprungene Jahre.
    with (root / 'vergleich_stuetzjahre_gegen_jahr_0.json').open(
            'w', encoding='utf-8') as handle:
        json.dump({
            'reference_year': 0,
            'relative_threshold_percent': 5.0,
            'comparison': 'je Stützjahr einzeln gegen Jahr 0',
            'near_zero_rule': 'Abweichung > absolute Toleranz',
            'annual_zero_floors': annual_tolerance,
            'pipe_zero_floors': pipe_tolerance,
            'profile_zero_floors': profile_tolerance,
            'year_decisions': comparison_report,
        }, handle, ensure_ascii=False, indent=2)



def network_2leiter_industrie(
        data, *, heat_mode=None, dispatch_mode=None,
        optimized_direct_kW=None, optimized_hp_kW=None,
        hp_eta_carnot=None, hp_max_output_kw=None,
        direct_approach_K=None,
        compute_costs=True, save_debug=True, plot_detailed=True):
    """Vereinfachtes Zwei-Einspeiser-Netz; unveränderte Single-Source-Module.

    In optimizer mode WITHOUT an external solution, the computed ACTUAL
    network is EH-only; the per-source technical envelope and a conservative
    two-scenario pipe design are exported. This is NOT an economic dispatch.
    Re-run with optimized_direct_kW / optimized_hp_kW after optimization.
    """
    mode_heat, mode_dispatch = resolve_industry_modes(heat_mode, dispatch_mode)
    eta = INDUSTRY_HP_ETA_CARNOT if hp_eta_carnot is None else float(hp_eta_carnot)
    max_hp = INDUSTRY_HP_MAX_OUTPUT_KW if hp_max_output_kw is None else hp_max_output_kw
    approach = INDUSTRY_DIRECT_APPROACH_K if direct_approach_K is None else float(direct_approach_K)
    n = len(np.asarray(data.heat_grid_data["T_soil"]))
    if n != 8760 or int(data.time.get("timeResolution", 3600)) != 3600:
        raise ValueError("Industrieintegration erwartet 8760 Stunden in 3600-s-Schritten")
    if mode_dispatch == "forced" and (optimized_direct_kW is not None or optimized_hp_kW is not None):
        raise ValueError("Optimierer-Entscheidung bei forced-Modus ist nicht erlaubt")
    if mode_dispatch == "optimizer" and optimized_hp_kW is not None and optimized_direct_kW is None:
        raise ValueError("Optimierer benötigt zusätzlich die Matrix der direkten Einspeisung")
    industry = load_industry(data, n)
    attachment = attach_wh_to_topology(data, industry["position"])
    data, param = single.load_parameter_2leiter(data)
    folder = Path(data.resultPath) / "network" / f"{data.scenario_name}_road_2leiter_industrie"
    folder.mkdir(parents=True, exist_ok=True)
    param["dir_result"] = str(folder)
    data.pipeline = {}
    single.initialize_pipeline_from_topology(data)
    single.update_pipe_data_selection(data, param, float(np.max(param["T_sup_design_base"])))

    # Gebäudelasten, -Übergabestationen und gesamte Gebäudemassenströme:
    # bewusst dieselbe Berechnung wie in heating_network_2leiter.py.
    data, param = single.calc_flow_2leiter(data, param)
    data, param = single.compute_return_temperature_EH_2leiter(data, param)
    t_sup = _array(param["T_sup_design_base"], n, "T_supply")
    t_ret = _array(data.heat_grid_data["T_return_EH"], n, "T_return")
    demand = sum((np.asarray(v, dtype=float) for v in param["Q_by_node"].values()), np.zeros(n))
    mass_build = sum((np.asarray(v, dtype=float) for v in param["building_massflow_HX"].values()), np.zeros(n))
    cp = float(data.heat_grid_data["fluid"]["c_f"])
    delta_t = t_sup - t_ret
    if np.any((demand > 1e-6) & (delta_t <= 1e-7)):
        raise ValueError("Bei positivem Netzbedarf fehlt eine positive Vorlauf-Rücklauf-Differenz")
    # m_build*cp*dT sollte die tatsächliche Gebäude-Heizleistung abbilden.
    power_from_m = mass_build * cp * np.maximum(delta_t, 0.0) / 1000.0
    err = np.max(np.abs(power_from_m - demand))
    tolerance = max(0.01, float(np.max(demand)) * 0.01)
    if err > tolerance:
        raise RuntimeError(f"Gebäude-Energiebilanz inkonsistent (max. {err:.3f} kW Fehler)")
    # Industrieeinspeisung zusätzlich auf die tatsächlich
    # durch den Gebäudemassenstrom abnehmbare Leistung begrenzen.
    demand_dispatch_cap = np.minimum(
        np.maximum(demand, 0.0),
        np.maximum(power_from_m, 0.0),
    )

    param["industry_dispatch_demand_cap_kW"] = demand_dispatch_cap

    envelope = build_industry_envelope(industry, t_sup, heat_mode=mode_heat,
                                       direct_approach_K=approach, hp_eta_carnot=eta)
    envelope["hp_total_capacity_kW"] = max_hp
    # Quelle fuer Quelle: Gegenstrom-LMTD/UA wie Gebaeude-HX.
    hx_specs = calculate_source_hx_specs(
        industry,
        supply_C=t_sup,
        return_C=t_ret,
        direct_max_kW=envelope["direct_max_kW"],
        demand_cap_kW=demand_dispatch_cap,
        hot_approach_K=approach,
    )
    forced_possible = dispatch_industrial_heat(
        industry,
        t_sup,
        demand_dispatch_cap,
        hp_max_output_kw=max_hp,
        envelope=envelope,
    )
    if mode_dispatch == "forced":
        dispatch = forced_possible
        pending = False
    elif optimized_direct_kW is not None:
        dispatch = validate_optimizer_dispatch(
            envelope, demand_dispatch_cap, optimized_direct_kW, optimized_hp_kW,
            hp_max_output_kw=max_hp)
        pending = False
    else:
        zero = np.zeros_like(envelope["source_input_kW"])
        dispatch = _finalize_source_dispatch(
            envelope, zero, zero, demand_dispatch_cap, hp_max_output_kw=max_hp,
            label="optimizer_pending_EH_only")
        pending = True
        warnings.warn("[Industrie] Optimierer-Modus ohne Ergebnis: keine Industrieeinspeisung; "
                      "technische Quellen-Grenzen gespeichert. EH versorgt vorläufig 100 %.")

    def source_mass(Q):
        m = np.zeros(n, dtype=float)
        valid = (Q > 1e-9) & (delta_t > 1e-7)
        m[valid] = Q[valid] * 1000.0 / (cp * delta_t[valid])
        if np.any((Q > 1e-9) & ~valid):
            raise ValueError("Industrieeinspeisung ohne Temperaturhub")
        if np.any(m > mass_build + 1e-5):
            raise RuntimeError("Industrie-Massenstrom überschreitet Gebäude-Abnahme")
        return m

    m_wh = source_mass(dispatch["used_heat_to_grid_kW"])
    m_wh_design = source_mass(forced_possible["used_heat_to_grid_kW"])
    # Für beliebige Zwischenwerte der Quellenentscheidung wird der
    # segmentweise Maximalbetrag aus EH-only und WH-priority verwendet.
    data, param = _dimension_for_operating_envelope(
        data, param, param["building_massflow_HX"], m_wh_design)


    # Prüfen, ob die industrielle Wärmeleistung ausreicht,
    # um wenigstens die Anschlussleitungsverluste zu decken.
    nominal_wh_loss = np.maximum(
        _nominal_wh_connection_loss_kW(data, param),
        0.0
    )

    candidate_wh_gross = np.asarray(
        dispatch["used_heat_to_grid_kW"],
        dtype=float
    )

    no_net_export = (
            (candidate_wh_gross > 1e-9)
            & (candidate_wh_gross <= nominal_wh_loss + 1e-9)
    )

    if np.any(no_net_export):

        if mode_dispatch == "forced":

            keep = (~no_net_export)[None, :]

            dispatch = _finalize_source_dispatch(
                envelope,
                np.where(
                    keep,
                    dispatch["used_source_direct_kW"],
                    0.0
                ),
                np.where(
                    keep,
                    dispatch["used_source_hp_output_kW"],
                    0.0
                ),
                demand_dispatch_cap,
                hp_max_output_kw=max_hp,
                label="forced_priority_with_WH_connection_cutoff",
            )

            print(
                f"[Industrie] {int(no_net_export.sum())} h "
                "mit zu geringer Nettoeinspeisung abgeschaltet."
            )

        elif not pending:
            raise ValueError(
                "Die Industrieeinspeisung ist in einigen Stunden "
                "kleiner als der Wärmeverlust der WH1-Leitung. "
                "Diese Stunden müssen vom Optimierer ausgeschlossen werden."
            )

    # Massenströme nach einer eventuellen Abschaltung neu berechnen
    m_wh = source_mass(
        dispatch["used_heat_to_grid_kW"]
    )

    flows, m_eh = signed_flows_on_tree(data.pipeline_topology, param["building_massflow_HX"], m_wh)
    _apply_signed_flows(data, param, flows)
    # Die tatsächlich berechneten Flüsse sind nicht die Bemessungs-Maxima.
    # Für Rohrdiagramme / DN bleiben die Bemessungswerte bewusst bestehen.
    for edge, vmax in param["pipe_design_envelope_max_vol_m3_s"].items():
        data.pipeline[f"{edge[0]}->{edge[1]}"]["flow_max"] = vmax

    param.update({
        "industry_attachment": attachment,
        "industrial_dispatch": dispatch,
        "industrial_envelope": envelope,
        "industrial_dispatch_pending": pending,
        "industry_heat_mode": mode_heat,
        "industry_dispatch_mode": mode_dispatch,
        "m_source_EH_kg_s": m_eh,
        "m_source_WH_kg_s": m_wh,
    })
    hydraulics = single.identify_junction_and_bends(data)
    data, zeta = single.compute_zeta_values(data, param, hydraulics)
    param["zeta"] = zeta
    param["hydraulic_features"] = hydraulics
    # Ursprüngliche Berechnung der Leitungsverluste
    data, param = single.calc_heat_loss_pipe_simple_2leiter(
        data, param
    )
    wh_nominal_loss = np.maximum(_nominal_wh_connection_loss_kW(data, param), 0.0)
    data.heat_grid_data["industrial_connection_nominal_loss_kW"] = wh_nominal_loss

    # Spezielle Korrektur für die zeitweise inaktive WH1-Leitung
    wh_line_losses, pipe_losses = _correct_wh_connection_losses(
        data, param
    )

    # Pumpenleistung vereinfacht berechnen
    data, param = design_pumps_two_scenarios(
        data, param, param["building_massflow_HX"], m_wh_design,
        flows, m_eh, m_wh
    )

    # Brutto-Wärmeleistung am Ausgang der Industrieanlage
    Q_ind = np.asarray(
        dispatch["used_heat_to_grid_kW"],
        dtype=float
    )

    # Netto-Wärmeleistung nach der Industrieanschlussleitung
    Q_ind_received = np.maximum(
        Q_ind - wh_line_losses,
        0.0
    )

    # Verluste im übrigen Quartiersnetz
    loss_rest_network = np.maximum(
        pipe_losses - wh_line_losses,
        0.0
    )

    # EH übernimmt die Restlast einschließlich der übrigen Verluste
    Q_eh = (
            demand
            - Q_ind_received
            + loss_rest_network
    )

    if np.any(Q_eh < -1e-5):
        raise RuntimeError("Negative EH-Restwärmelast")

    # Wärmebilanz am Anschluss des Quartiersnetzes
    if not np.allclose(
            Q_eh + Q_ind_received,
            demand + loss_rest_network,
            rtol=1e-9,
            atol=1e-5,
    ):
        raise RuntimeError(
            "Stündliche Netz-Energiebilanz am Quartiersanschluss verletzt"
        )

    # Gesamtbilanz unter Einbeziehung der Industrieanschlussleitung
    if not np.allclose(
            Q_eh + Q_ind,
            demand + pipe_losses,
            rtol=1e-9,
            atol=1e-5,
    ):
        raise RuntimeError(
            "Stündliche Gesamtwärmebilanz verletzt"
        )

    param["industrial_heat_reaching_district_kW"] = Q_ind_received
    param["industrial_WH_connection_loss_kW"] = wh_line_losses


    data.heat_grid_data["industrial_heat_to_grid_kW"] = Q_ind
    data.heat_grid_data["industrial_heat_reaching_district_kW"] = Q_ind_received
    data.heat_grid_data["industrial_connection_heat_loss_kW"] = wh_line_losses
    data.heat_grid_data["industrial_hp_electric_kW"] = dispatch["industrial_hp_electric_kW"]
    data.heat_grid_data["industrial_available_heat_to_grid_kW"] = dispatch["available_heat_to_grid_kW"]
    data.heat_grid_data["industrial_source_waste_heat_used_kW"] = dispatch["used_source_waste_heat_kW"]
    data.heat_grid_data["EH_heat_required_with_industry_kW"] = Q_eh
    data.heat_grid_data["industrial_connection_length_m"] = attachment["connection_length_m"]
    data.heat_grid_data["industrial_dispatch_pending"] = pending
    data.heat_grid_data["industrial_heat_mode"] = mode_heat
    data.heat_grid_data["industrial_dispatch_mode"] = mode_dispatch

    _save_industry_topology(data, folder)
    _plot_industry_topology(data, folder)
    if plot_detailed:
        # Sechs bestehende Auswertungsdiagramme wiederverwenden.
        single.plot_network_results_2leiter(data, param)
    if save_debug:
        single._save_debug_outputs(data, param)
    costs = _make_industry_costs(data, param) if compute_costs else {}
    if compute_costs:
        data.heat_grid_data["ann_costs"] = costs["pipe_annuity_EUR_a"] + costs["pump_annuity_EUR_a"]
        data.heat_grid_data["om_costs"] = costs["pipe_om_EUR_a"] + costs["pump_om_EUR_a"]
        with (folder / "industrie_netzerzeugung_kosten.json").open("w", encoding="utf-8") as f:
            json.dump(costs, f, indent=2, ensure_ascii=False)

    # Export der technischen Optimierer-Grenzen: je Quelle und Stunde,
    # zusätzlich Summenkapazität aller industriellen Wärmepumpen.
    param["industry_optimizer_bounds_file"] = str(folder / "industrie_quellen_optimierer_grenzen_8760.npz")
    np.savez_compressed(
        folder / "industrie_quellen_optimierer_grenzen_8760.npz",
        direct_max_kW=envelope["direct_max_kW"],
        hp_max_kW=envelope["hp_max_kW"],
        hp_electric_per_output=envelope["hp_electric_per_output"],
        source_input_kW=envelope["source_input_kW"],
        hp_max_output_kw=np.array([np.nan if max_hp is None else float(max_hp)]),
        demand_massflow_cap_kW=param["industry_dispatch_demand_cap_kW"],
        hx_factor_kW_per_kW=hx_specs["hx_factor"],
        hx_max_design_capacity_kW=hx_specs["hx_cap_upper"],
        hx_UA_W_K_per_kW=hx_specs["hx_UA_per_kW"],
        hx_q_number=hx_specs["hx_q_number"],
    )
    np.savez_compressed(
        folder / "industrie_mehrquellen_zeitreihen_8760.npz",
        industry_heat_to_grid_kW=Q_ind,
        industrial_heat_reaching_district_kW=Q_ind_received,
        industrial_connection_pipe_losses_kW=wh_line_losses,
        network_pipe_losses_excl_industrial_connection_kW=loss_rest_network,
        industrial_direct_by_source_kW=dispatch["used_source_direct_kW"],
        industrial_hp_by_source_kW=dispatch["used_source_hp_output_kW"],
        industrial_hp_electric_kW=dispatch["industrial_hp_electric_kW"],
        industrial_source_waste_heat_used_kW=dispatch["used_source_waste_heat_kW"],
        EH_heat_required_kW=Q_eh,
        network_pipe_losses_kW=pipe_losses,
        pump_power_EH_W=param["P_pump_EH_W"],
        pump_power_WH_W=param["P_pump_WH_W"],
        )
    report = {
        "model": "2leiter_industrie_multimode_v2",
        "heat_mode": mode_heat,
        "dispatch_mode": mode_dispatch,
        "optimizer_pending": pending,
        "dispatch_status": dispatch["dispatch_label"],
        "geometry": attachment,
        "industry_id": industry["metadata"].get("id", "industry_001"),
        "industry_group": industry["metadata"].get("group_id"),
        "sources_count": int(envelope["source_input_kW"].shape[0]),
        "industrial_waste_heat_available_kWh_a": float(envelope["source_input_kW"].sum()),
        "industrial_possible_heat_to_grid_kWh_a": float((envelope["direct_max_kW"] + envelope["hp_max_kW"]).sum()),
        "industrial_heat_used_kWh_a": float(Q_ind.sum()),
        "industrial_heat_reaching_district_kWh_a": float(Q_ind_received.sum()),
        "industrial_connection_pipe_loss_kWh_a": float(wh_line_losses.sum()),
        "industrial_connection_active_hours": int(param["industry_WH_connection_active_hours"]),
        "industrial_HP_electricity_kWh_a": float(dispatch["industrial_hp_electric_kW"].sum()),
        "EH_heat_required_kWh_a_including_pipe_losses": float(Q_eh.sum()),
        "pipe_loss_kWh_a": float(pipe_losses.sum()),
        "total_pipe_length_m": float(sum(p["length"] for p in data.pipeline.values())),
        "max_signed_mass_balance_residual_kg_s": float(np.max(np.abs(
            m_eh + m_wh - mass_build))),
        "design_cases": ["EH_only", "forced_maximal_industrial_use"],
        "network_costs": costs,
        "limitations": [
            "Keine gekoppelte Druckfeldrechnung; Pumpenleistung nur Näherung, ohne garantierte Genauigkeit",
            "Globales T-Vorlauf/Rücklauf wie im originalen vereinfachten 2-Leiter-Modell",
            "Netzverluste dem EH zugerechnet; keine Iteration der Massenströme wegen Verlusten",
            "Industrie-Wärmepumpe: stationäres Carnot-Näherungsmodell, keine Kosten oder Auslegung",
            "Im Optimierer-Modus OHNE Lösung ist die EH-only-Rechnung nur vorläufig",
            "Die Pyomo/EHDO-Variablen und Wärmebilanz sind im aktuellen Optimierer noch nicht angeschlossen",
        ],
    }
    with (folder / "industrie_mehrquellen_bericht.json").open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"[2-LEITER/INDUSTRIE] {mode_heat}/{mode_dispatch}; "
          f"WH brutto {float(Q_ind.sum())/1e6:.3f} GWh/a, "
          f"am Quartier {float(Q_ind_received.sum())/1e6:.3f} GWh/a; "
          f"EH-Rest {float(Q_eh.sum())/1e6:.3f} GWh/a; "
          f"Optimierung ausstehend={pending}")
    # Nur für die spätere Post-Pyomo-Auswertung der optimierten Cluster.
    # Keine neuen Dateien; param bleibt im laufenden Datahandler erreichbar.
    data._industry_network_plot_param = param
    return data, param
