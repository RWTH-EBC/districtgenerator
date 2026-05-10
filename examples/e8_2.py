# -*- coding: utf-8 -*-

"""
e8_scenario_evaluation_with_saver.py

Multi-BM scenario evaluation with results saving capability.

Features:
- Automatisches Speichern aller Ergebnisse in pkl Dateien
- Automatische p_max/npv_ref Übergabe vom Reference-Run zu den anderen BMs
- Laden und Vergleichen von gespeicherten Ergebnissen
- KEINE Plots (nur Daten speichern)

Workflow:
  1. run_reference_and_all_bms() - Führt Reference aus, übergibt p_max automatisch, dann alle BMs
  2. load_and_analyze_results() - Lädt gespeicherte pkl Dateien für spätere Analyse
"""

from districtgenerator.classes import *
import warnings
import pickle
import os
import copy
from datetime import datetime

# Import des result_saver Moduls
try:
    from districtgenerator.functions.result_saver import ( save_all_results,load_results,load_multiple_results)
except ImportError:
    try:
        from districtgenerator.classes.result_saver import save_all_results, load_results, load_multiple_results
    except ImportError:
        print("Warning: result_saver module not found.")


        def save_all_results(data, filename=None, include_time_series=True):
            print("result_saver not available - skipping save")
            return None


RESULTS_SUBFOLDER = "bm_results"
RESULT_ROOT = r"C:\Users\rha-csa\PycharmProjects\districtgenerator\districtgenerator\results"
SCENARIOS_ROOT = r"C:\Users\rha-csa\PycharmProjects\districtgenerator\districtgenerator\data\scenarios"


def clear_bm_postprocessing_cache(data):
    """
    Clear cached BM postprocessing quantities on `data`.

    Must be called before each new optimization run because changed
    HEAT_GRID membership or changed dispatch invalidates heat/PV/grid-flow
    caches stored on `data._bm_postprocessing_cache`.
    """
    if hasattr(data, "_bm_postprocessing_cache"):
        delattr(data, "_bm_postprocessing_cache")

# ══════════════════════════════════════════════════════════════════════
# PER-BM OPTIMIZATION WITH RESULTS SAVING (OHNE PLOTS)
# ══════════════════════════════════════════════════════════════════════

def run_optimization_for_bm(data, business_model, save_results=True,
                            include_time_series=True):
    """
    Run full optimization pipeline for a specific business model.
    Speichert automatisch alle Ergebnisse in eine pkl Datei.
    KEINE Plots.

    Returns
    -------
    data : Datahandler
        Datahandler with optimization results.
    results_filepath : str or None
        Path to saved results file.
    """
    # Reset result containers
    data.resultsOptimization = {}
    if hasattr(data, 'KPIs'):
        data.KPIs = None

    # Cache aus vorherigen Optimierungen invalidieren — Heat-Grid-Mitgliedschaft
    # und Dispatch können sich geändert haben.
    clear_bm_postprocessing_cache(data)

    print(f"\n{'=' * 60}")
    print(f"Running optimization for Business Model: {business_model}")
    print(f"{'=' * 60}")

    data.optimizationClusters()
    clear_bm_postprocessing_cache(data)
    data.calculateKPIs()


    results_filepath = None
    if save_results:
        print("  Saving results to pkl file ...")
        try:
            results_dir = os.path.join(data.resultPath, RESULTS_SUBFOLDER)
            os.makedirs(results_dir, exist_ok=True)

            filename = f"results_{data.scenario_name}_{business_model}.pkl"

            original_result_path = data.resultPath
            data.resultPath = results_dir

            results_filepath = save_all_results(
                data,
                filename=filename,
                include_time_series=include_time_series
            )

            data.resultPath = original_result_path

        except Exception as e:
            print(f"  ⚠ Warning: Could not save results: {e}")

    return data, results_filepath


# ══════════════════════════════════════════════════════════════════════
# REFERENCE RUN WITH AUTOMATIC NPV_REF EXTRACTION
# ══════════════════════════════════════════════════════════════════════

def run_reference(scenario_name, env_path=".env.CONFIG.REF_BOI",
                  reference_key=None, reference_case=None,
                  topology_option="road", calcUserProfiles=False,
                  saveUserProfiles=False, save_results=True,
                  include_time_series=True,
                  scenario_variant=None, scenario_dir=None):
    """
    Schlanker Reference-Run:
    generateDistrictComplete -> optimizationClusters -> calculateKPIs -> optional save.

    Rückwärtskompatibel:
    - Ohne reference_key/reference_case läuft die Funktion wie bisher.
    - Mit reference_key werden PKL-Dateien eindeutig je Referenzfall benannt.
    - Mit reference_case wird ecoData["reference_case"] explizit gesetzt.
    """
    warnings.filterwarnings("ignore", category=FutureWarning)

    if reference_key is None:
        reference_key = "ref_boi"

    print(f"\n{'#' * 60}")
    print(f"# REFERENCE RUN: {reference_key}")
    print(f"{'#' * 60}\n")

    data = Datahandler(
        scenario_name=scenario_name,
        env_path=env_path,
        scenario_variant=scenario_variant,
        scenario_dir=scenario_dir,
        resultPath=RESULT_ROOT
    )

    data.ecoData["business_model"] = reference_key
    data.ecoData["reference_key"] = reference_key
    if reference_case is not None:
        data.ecoData["reference_case"] = reference_case

    if "topology_option" in data.heat_grid_data:
        topology_option = data.heat_grid_data["topology_option"]

    data.generateDistrictComplete(
        calcUserProfiles=calcUserProfiles,
        saveUserProfiles=saveUserProfiles,
        topology_option=topology_option
    )

    data.optimizationClusters()
    data.calculateKPIs()

    p_max = getattr(data.KPIs, "p_max", None)
    npv_ref = getattr(data.KPIs, "npv_ref", None)
    npv_ref_by_building = getattr(data.KPIs, "npv_ref_by_building", {})
    reference_case = getattr(data.KPIs, "reference_case", reference_case)

    print(f"\n{'=' * 60}")
    print(f"REFERENCE RESULTS: {reference_key}")
    print(f"{'=' * 60}")
    print(f"  reference_case = {reference_case}")
    print("  p_max          = not applicable in reference run" if p_max is None else f"  p_max          = {p_max:.6f} EUR/kWh ({p_max * 100:.4f} ct/kWh)")
    print(f"  npv_ref        = {npv_ref:,.0f} EUR" if npv_ref is not None else "  npv_ref        = NOT CALCULATED")
    print(f"{'=' * 60}")

    results_filepath = None
    if save_results:
        try:
            scenario_folder = getattr(data, "scenario_variant", None) or data.scenario_name.split("_")[0]
            results_dir = os.path.join(data.resultPath, RESULTS_SUBFOLDER, scenario_folder)
            os.makedirs(results_dir, exist_ok=True)

            original_result_path = data.resultPath
            data.resultPath = results_dir

            results_filepath = save_all_results(
                data,
                filename=f"results_{scenario_name}_{reference_key}.pkl",
                include_time_series=include_time_series
            )

            data.resultPath = original_result_path
        except Exception as e:
            print(f"Warning: Could not save reference results: {e}")

    return data, p_max, npv_ref, npv_ref_by_building, reference_case, results_filepath


# ══════════════════════════════════════════════════════════════════════
# BM COMPARISON WITH AUTOMATIC REFERENCE INJECTION
# ══════════════════════════════════════════════════════════════════════

def run_all_bms_with_reference_values(
    scenario_name,
    bm_configs,
    p_max,
    npv_ref,
    npv_ref_by_building,
    reference_case,
    reference_key="reference",
    topology_option="road",
    save_results=True,
    include_time_series=True,
    scenario_variant=None,
    scenario_dir=None
):
    """
    Ein Basislauf pro BM und Referenzfall:
    - <bm>_base: genau eine Optimierung mit allen Wärmenetzgebäuden, nicht gespeichert.
    - <bm>_B: KPI-Auswertung aus base, gespeichert.
    - <bm>_A: KPI-Auswertung aus base; neue Optimierung nur bei Ausschlüssen.
    - Iterationen werden nicht gespeichert; nur der finale A-Stand wird gespeichert.
    - Kundenanlage/all-or-none-BMs werden nur als B ausgewertet und gespeichert.
    """
    results = {}
    saved_files = {}

    def _make_datahandler(env_path):
        return Datahandler(
            scenario_name=scenario_name,
            env_path=env_path,
            scenario_variant=scenario_variant,
            scenario_dir=scenario_dir,
            resultPath=RESULT_ROOT
        )

    def _inject_reference_values(data, bm_name, scenario_flag):
        data.ecoData["business_model"] = bm_name
        data.ecoData["scenario"] = scenario_flag
        data.ecoData["reference_key"] = reference_key

        if npv_ref_by_building:
            data.ecoData["npv_ref_by_building"] = copy.deepcopy(npv_ref_by_building)
            print(f"  -> Injected npv_ref_by_building for {len(npv_ref_by_building)} buildings")

        if reference_case is not None:
            data.ecoData["reference_case"] = reference_case
            print(f"  -> Injected reference_case = {reference_case}")

        if p_max is not None:
            data.ecoData["p_max"] = p_max

        if npv_ref is not None:
            data.ecoData["npv_ref"] = npv_ref

    def _apply_exclusions_to_scenario_table(data, excluded_original_ids):
        """
        Setzt ausgeschlossene Gebäude direkt in data.scenario auf BOI.

        Voraussetzung:
        Die Gebäude-ID der CSV ist der Index von data.scenario.
        """
        excluded_original_ids = set(excluded_original_ids or [])
        if not excluded_original_ids:
            return

        missing = excluded_original_ids.difference(data.scenario.index)
        if missing:
            raise KeyError(
                f"Excluded building IDs not found in scenario index: {sorted(missing)}"
            )

        data.scenario.loc[list(excluded_original_ids), "heater"] = "BOI"

    def _generate_district(data, excluded_original_ids=None):
        """
        Generiert den District für Basis/B/A.

        Bei Szenario A werden ausgeschlossene Gebäude VOR generateDistrictComplete()
        auf BOI gesetzt. Damit sind dezentrale Geräte, Wärmenetz,
        Rohrdimensionierung, zentrale Anlagen und Clusterprofile konsistent.
        """
        _apply_exclusions_to_scenario_table(data, excluded_original_ids)

        bm_topology_option = data.heat_grid_data.get("topology_option", topology_option)
        data.generateDistrictComplete(
            calcUserProfiles=False,
            saveUserProfiles=False,
            topology_option=bm_topology_option
        )

    def _building_indices_to_original_ids(data, building_indices):
        original_ids = set()
        for n in building_indices:
            if 0 <= n < len(data.district):
                original_id = data.district[n]["buildingFeatures"].get("original_bldg_id")
                if original_id is not None:
                    original_ids.add(original_id)
        return original_ids

    def _save_result(data, bm_name, scenario_flag):
        filepath = None
        if not save_results:
            return filepath

        print("  Saving results to pkl file ...")
        try:
            scenario_folder = getattr(data, "scenario_variant", None) or data.scenario_name.split("_")[0]
            results_dir = os.path.join(data.resultPath, RESULTS_SUBFOLDER, scenario_folder)
            os.makedirs(results_dir, exist_ok=True)

            filename = f"results_{data.scenario_name}_{reference_key}_{bm_name}_{scenario_flag}.pkl"

            original_result_path = data.resultPath
            data.resultPath = results_dir

            filepath = save_all_results(
                data,
                filename=filename,
                include_time_series=include_time_series
            )

            data.resultPath = original_result_path
        except Exception as e:
            print(f"  Warning: Could not save results: {e}")

        return filepath

    def _recalculate_existing_run_for_scenario(data, bm_name, scenario_flag, save_this_result=True):
        # Shallow copy: große Optimierungsergebnisse (resultsOptimization)
        # werden per Referenz geteilt; nur ecoData/KPIs werden isoliert.
        # Das ist sicher, weil A- und B-KPI-Auswertung dasselbe
        # Optimierungsergebnis nutzen — nur die Aggregation unterscheidet sich.
        scenario_data = copy.copy(data)
        scenario_data.ecoData = dict(data.ecoData)
        scenario_data.ecoData["scenario"] = scenario_flag
        scenario_data.ecoData["reference_key"] = reference_key
        scenario_data.all_sim_ecoData = scenario_data.calculate_ecoData_per_cluster()
        scenario_data.KPIs = None
        scenario_data.calculateKPIs()

        filepath = _save_result(scenario_data, bm_name, scenario_flag) if save_this_result else None
        return scenario_data, filepath

    def _derive_scenario_a_from_breakdown(data, bm_name):
        breakdown = getattr(data.KPIs, "bm_breakdown", {}) or {}

        # Kundenanlage: fachlich all-or-none. Keine A-Iteration.
        if bm_name == "waermecontracting_kundenanlage" or breakdown.get("allows_building_exclusion") is False:
            return {
                "connected": [],
                "excluded": [],
                "needs_iteration": False,
                "building_details": breakdown.get("scenario_b", {}).get("building_details", {}),
                "skip_a": True,
            }

        scenario_a = breakdown.get("scenario_a", {}) or {}
        if scenario_a:
            return {
                "connected": scenario_a.get("connected", []),
                "excluded": scenario_a.get("excluded", []),
                "needs_iteration": scenario_a.get("needs_iteration", False),
                "building_details": scenario_a.get("building_details", {}),
                "skip_a": False,
            }

        # Fallback für ältere BM-Klassen: aus scenario_b-Diagnose ableiten, falls vorhanden.
        scenario_b = breakdown.get("scenario_b", {}) or {}
        building_details = scenario_b.get("building_details", {}) or {}
        excluded = sorted(
            n for n, details in building_details.items()
            if details.get("npv_wn_at_price", 0.0) < details.get("npv_ref", 0.0)
        )
        connected = sorted(n for n in building_details.keys() if n not in excluded)

        return {
            "connected": connected,
            "excluded": excluded,
            "needs_iteration": len(excluded) > 0,
            "building_details": building_details,
            "skip_a": False,
        }

    def _initial_considered_original_ids(data, scenario_a_result):
        indices = list(scenario_a_result.get("connected", [])) + list(scenario_a_result.get("excluded", []))
        ids = _building_indices_to_original_ids(data, indices)
        if ids:
            return ids
        # Fallback: alle aktuellen HEAT_GRID-Gebäude im Basislauf.
        heat_grid_indices = [
            n for n, building in enumerate(data.district)
            if building.get("buildingFeatures", {}).get("heater", "").upper() == "HEAT_GRID"
        ]
        return _building_indices_to_original_ids(data, heat_grid_indices)

    for bm_name, env_path in bm_configs.items():
        print(f"\n{'#' * 60}")
        print(f"# Processing Business Model: {bm_name} | Reference: {reference_key}")
        print(f"{'#' * 60}\n")

        # ==========================================================
        # BASISLAUF: gemeinsame Optimierung für A und B
        # ==========================================================
        print(f"--- Running {bm_name} / Basislauf (= gemeinsame Optimierung für A und B) ---")

        data_base = _make_datahandler(env_path)
        _inject_reference_values(data_base, bm_name, "B")
        _generate_district(data_base)

        data_base, _ = run_optimization_for_bm(
            data_base,
            f"{bm_name}_base",
            save_results=False,
            include_time_series=False
        )

        # ==========================================================
        # SCENARIO B: nur KPI-Auswertung aus dem Basislauf
        # ==========================================================
        data_b, filepath_b = _recalculate_existing_run_for_scenario(
            data_base,
            bm_name,
            "B",
            save_this_result=True
        )

        results[f"{reference_key}_{bm_name}_B"] = data_b
        saved_files[f"{reference_key}_{bm_name}_B"] = filepath_b

        # ==========================================================
        # SCENARIO A: aus Basislauf ableiten; nur bei Ausschlüssen neu optimieren
        # ==========================================================
        data_a_basis, _ = _recalculate_existing_run_for_scenario(
            data_base,
            bm_name,
            "A",
            save_this_result=False
        )
        scenario_a_basis = _derive_scenario_a_from_breakdown(data_a_basis, bm_name)

        if scenario_a_basis.get("skip_a", False):
            print("  -> Scenario A skipped: BM is all-or-none.")
            continue

        excluded_original_ids = _building_indices_to_original_ids(
            data_a_basis,
            scenario_a_basis.get("excluded", [])
        )
        considered_original_ids = _initial_considered_original_ids(data_a_basis, scenario_a_basis)

        # Niemand ausgeschlossen -> A ist identisch zur Basisoptimierung.
        if not excluded_original_ids:
            print("  -> Scenario A reuses the basis optimization: no uneconomic buildings found.")
            filepath_a = _save_result(data_a_basis, bm_name, "A")
            results[f"{reference_key}_{bm_name}_A"] = data_a_basis
            saved_files[f"{reference_key}_{bm_name}_A"] = filepath_a
            continue

        # Alle betrachteten Gebäude ausgeschlossen -> A nicht tragfähig; keine neue Optimierung nötig.
        if considered_original_ids and len(excluded_original_ids) == len(considered_original_ids):
            print("  -> Scenario A not feasible: all considered buildings excluded.")
            filepath_a = _save_result(data_a_basis, bm_name, "A")
            results[f"{reference_key}_{bm_name}_A"] = data_a_basis
            saved_files[f"{reference_key}_{bm_name}_A"] = filepath_a
            continue

        print(
            f"--- Running {bm_name} / Scenario A "
            f"(start with {len(excluded_original_ids)} exclusions from basis run) ---"
        )

        max_iter = 10
        data_a = None
        iteration_history = []
        scenario_a_not_feasible = False

        for iteration in range(1, max_iter + 1):
            print(
                f"  -> Scenario A iteration {iteration}: "
                f"excluded original IDs = {sorted(excluded_original_ids)}"
            )

            data_a = _make_datahandler(env_path)
            _inject_reference_values(data_a, bm_name, "A")
            _generate_district(data_a, excluded_original_ids=excluded_original_ids)

            data_a, _ = run_optimization_for_bm(
                data_a,
                f"{bm_name}_A",
                save_results=False,
                include_time_series=False
            )

            scenario_a_result = _derive_scenario_a_from_breakdown(data_a, bm_name)
            newly_excluded = _building_indices_to_original_ids(
                data_a,
                scenario_a_result.get("excluded", [])
            )

            additional_exclusions = newly_excluded.difference(excluded_original_ids)

            iteration_history.append({
                "iteration": iteration,
                "excluded_before": sorted(excluded_original_ids),
                "newly_excluded": sorted(newly_excluded),
                "additional_exclusions": sorted(additional_exclusions),
                "p_min": getattr(data_a.KPIs, "p_min", None),
                "p_max": getattr(data_a.KPIs, "p_max", None),
                "connected_original_ids": sorted(
                    building["buildingFeatures"].get("original_bldg_id")
                    for building in data_a.district
                    if building["buildingFeatures"].get("heater", "").upper() == "HEAT_GRID"
                ),
            })

            if not additional_exclusions:
                print("  -> Scenario A converged: no additional buildings excluded.")
                break

            excluded_original_ids.update(additional_exclusions)

            if considered_original_ids and len(excluded_original_ids) == len(considered_original_ids):
                print("  -> Scenario A not feasible after iteration: all considered buildings excluded.")
                scenario_a_not_feasible = True
                break

        # Nur finalen A-Zustand speichern; keine Zwischeniterationsdateien.
        if data_a is None:
            data_a = data_a_basis

        data_a.ecoData["iteration_history"] = iteration_history
        data_a.ecoData["final_excluded_original_ids"] = sorted(excluded_original_ids)
        data_a.ecoData["scenario_a_not_feasible"] = scenario_a_not_feasible

        filepath_a = _save_result(data_a, bm_name, "A")
        results[f"{reference_key}_{bm_name}_A"] = data_a
        saved_files[f"{reference_key}_{bm_name}_A"] = filepath_a

    _print_results_summary(results, saved_files)
    return results, saved_files

def _print_results_summary(results, saved_files):
    """Print summary of all BM results (text only, no plots)."""
    print(f"\n{'#' * 60}")
    print(f"# RESULTS SUMMARY — {len(results)} business models")
    print(f"{'#' * 60}\n")

    print(f"{'BM':<15} {'p_min (ct)':>12} {'p_max (ct)':>12} {'Feasible':>10} {'TAC (EUR/a)':>14}")
    print("-" * 66)

    for bm_name, data in results.items():
        kpis = data.KPIs if hasattr(data, 'KPIs') and data.KPIs else None
        cap = data.centralDevices.get("capacities", {}) if hasattr(data, "centralDevices") else {}

        p_min = getattr(kpis, 'p_min', None)
        p_max_val = getattr(kpis, 'p_max', None)
        tac = cap.get("tac", None)

        p_min_s = f"{p_min * 100:.2f}" if p_min is not None else "-"
        p_max_s = f"{p_max_val * 100:.2f}" if p_max_val is not None else "-"
        tac_s = f"{tac:,.0f}" if tac is not None else "-"
        feas = "Yes" if (p_min and p_max_val and p_min <= p_max_val) else "No" if (p_min and p_max_val) else "-"

        print(f"{bm_name:<15} {p_min_s:>12} {p_max_s:>12} {feas:>10} {tac_s:>14}")

    # Installed technologies
    print(f"\n{'BM':<15} {'Installed Technologies'}")
    print("-" * 66)
    for bm_name, data in results.items():
        cap = data.centralDevices.get("capacities", {}) if hasattr(data, "centralDevices") else {}
        techs = []
        for dev in ["HP", "EB", "CHP", "BCHP", "WCHP", "BOI", "BBOI", "WBOI",
                    "STC", "PV", "WT", "TES", "BAT", "GHP", "FC"]:
            if dev in cap and isinstance(cap[dev], dict):
                c = cap[dev].get("cap", 0)
                if c > 0:
                    unit = "m²" if dev in ("STC", "PV") else ("kWh" if dev in ("TES", "BAT") else "kW")
                    techs.append(f"{dev}={c:.0f}{unit}")
        print(f"{bm_name:<15} {', '.join(techs) if techs else '-'}")

    # Saved files
    print(f"\n{'BM':<15} {'Saved Results File'}")
    print("-" * 66)
    for bm_name, filepath in saved_files.items():
        if filepath:
            print(f"{bm_name:<15} {os.path.basename(filepath)}")
        else:
            print(f"{bm_name:<15} (not saved)")


# ══════════════════════════════════════════════════════════════════════
# COMBINED WORKFLOW: REFERENCES + ALL BMs
# ══════════════════════════════════════════════════════════════════════

def run_reference_and_all_bms(reference_scenario_name, bm_scenario_name, bm_configs,
                              reference_env=".env.CONFIG.REF_BOI",
                              reference_configs=None,
                              topology_option="road",
                              calcUserProfiles=False, saveUserProfiles=False,
                              save_results=True, include_time_series=True,
                              scenario_variant=None, scenario_dir=None):
    """
    HAUPTFUNKTION: Führt Referenzläufe und danach alle BMs aus.

    Rückwärtskompatibel:
    - Wenn reference_configs None ist, wird wie bisher ein einzelner Referenzlauf
      über reference_env ausgeführt.
    - Wenn reference_configs gesetzt ist, wird jeder Referenzfall separat gerechnet
      und die BM-Ergebnisse werden mit reference_key im Dateinamen abgegrenzt.
    """
    all_results = {}
    all_saved_files = {}
    reference_values = {}

    if reference_configs is None:
        reference_configs = {
            "ref_boi": {
                "env": reference_env,
                "reference_case": "boi",
            }
        }

    # Auch alte Form {"ref_boi": ".env..."} unterstützen.
    normalized_reference_configs = {}
    for reference_key, cfg in reference_configs.items():
        if isinstance(cfg, dict):
            normalized_reference_configs[reference_key] = {
                "env": cfg.get("env"),
                "reference_case": cfg.get("reference_case"),
                "scenario_name": cfg.get("scenario_name"),
            }
        else:
            normalized_reference_configs[reference_key] = {
                "env": cfg,
                "reference_case": "hp_pv" if "wp" in reference_key.lower() or "hp" in reference_key.lower() else "boi",
            }

    for ref_index, (reference_key, ref_cfg) in enumerate(normalized_reference_configs.items()):
        print(f"\n{'#' * 60}")
        print(f"# REFERENCE COMPARISON: {reference_key}")
        print(f"{'#' * 60}\n")

        ref_env = ref_cfg["env"]
        ref_case = ref_cfg.get("reference_case")
        ref_scenario_name = ref_cfg.get("scenario_name", reference_scenario_name)

        # Demand-Profile sind heater-/business-model-unabhängig.
        # Beim ersten Reference-Run einmalig erzeugen, danach von Disk laden.
        is_first_run = (ref_index == 0)
        ref_calc = bool(calcUserProfiles) if is_first_run else False
        ref_save = bool(saveUserProfiles) if is_first_run else False
        if not is_first_run and (calcUserProfiles or saveUserProfiles):
            print(f"  -> Demand profiles already generated; reusing from disk")

        ref_data, p_max, npv_ref, npv_ref_by_building, reference_case, ref_filepath = run_reference(
            scenario_name=ref_scenario_name,
            env_path=ref_env,
            reference_key=reference_key,
            reference_case=ref_case,
            topology_option=topology_option,
            calcUserProfiles=ref_calc,
            saveUserProfiles=ref_save,
            save_results=save_results,
            include_time_series=include_time_series,
            scenario_variant=scenario_variant,
            scenario_dir=scenario_dir,
        )

        all_results[reference_key] = ref_data
        all_saved_files[reference_key] = ref_filepath

        reference_values[reference_key] = {
            "p_max": p_max,
            "npv_ref": npv_ref,
            "npv_ref_by_building": npv_ref_by_building,
            "reference_case": reference_case,
        }

        bm_results, bm_files = run_all_bms_with_reference_values(
            scenario_name=bm_scenario_name,
            bm_configs=bm_configs,
            p_max=p_max,
            npv_ref=npv_ref,
            npv_ref_by_building=npv_ref_by_building,
            reference_case=reference_case,
            reference_key=reference_key,
            topology_option=topology_option,
            save_results=save_results,
            include_time_series=include_time_series,
            scenario_variant=scenario_variant,
            scenario_dir=scenario_dir,
        )

        all_results.update(bm_results)
        all_saved_files.update(bm_files)

    print(f"\n{'#' * 60}")
    print("# ALL REFERENCE COMPARISONS COMPLETED")
    print(f"{'#' * 60}")
    print(f"Saved {len(all_saved_files)} result files.")

    return all_results, all_saved_files, reference_values

# ══════════════════════════════════════════════════════════════════════
# LOAD AND ANALYZE (ohne Neuberechnung!)
# ══════════════════════════════════════════════════════════════════════

def load_and_analyze_results(results_dir, scenario_name=None):
    """
    Lade gespeicherte Ergebnisse und analysiere sie ohne Neuberechnung.
    """
    all_results = {}

    pattern = f"summary_{scenario_name}_*.pkl" if scenario_name else "summary_*.pkl"

    import glob
    files = glob.glob(os.path.join(results_dir, pattern))

    if not files:
        print(f"No result files found in {results_dir} with pattern {pattern}")
        return all_results

    print(f"\nLoading {len(files)} result files from {results_dir}...")

    for filepath in files:
        try:
            with open(filepath, 'rb') as f:
                result = pickle.load(f)

            bm_name = result.get("metadata", {}).get("business_model", "unknown")
            if bm_name == "unknown" or bm_name is None:
                basename = os.path.basename(filepath)
                stem = basename.replace(".pkl", "")
                # Praefix entfernen (summary_ / results_ / timeseries_ / topology_)
                for prefix in ("summary_", "timeseries_", "topology_", "results_"):
                    if stem.startswith(prefix):
                        stem = stem[len(prefix):]
                        break
                parts = stem.split("_")

                # Schema (nach Praefix-Strip):
                # E02_bm_ref_boi_waermecontracting_ggv_A
                if len(parts) >= 5 and parts[-1] in ("A", "B"):
                    scenario_flag = parts[-1]
                    reference_key = "_".join(parts[2:4])
                    bm_name_raw = "_".join(parts[4:-1])
                    bm_name = f"{reference_key}_{bm_name_raw}_{scenario_flag}"
                elif len(parts) >= 2:
                    bm_name = "_".join(parts[1:])
                else:
                    bm_name = stem

            all_results[bm_name] = result
            print(f"  ✓ Loaded: {bm_name}")

        except Exception as e:
            print(f"  ✗ Error loading {filepath}: {e}")

    print(f"\n✓ Loaded {len(all_results)} result files")

    return all_results


def print_loaded_results_summary(all_results):
    """Druckt eine Zusammenfassung der geladenen Ergebnisse."""
    print(f"\n{'#' * 60}")
    print(f"# LOADED RESULTS SUMMARY — {len(all_results)} business models")
    print(f"{'#' * 60}\n")

    print(f"{'BM':<15} {'p_min (ct)':>12} {'p_max (ct)':>12} {'Feasible':>10} {'NPV Diff (€)':>14}")
    print("-" * 66)

    for bm_name, result in all_results.items():
        kpis = result.get("kpis", {}).get("static", {})

        p_min = kpis.get("p_min")
        p_max = kpis.get("p_max")
        npv_diff = kpis.get("npv_difference")

        p_min_s = f"{p_min * 100:.2f}" if p_min is not None else "-"
        p_max_s = f"{p_max * 100:.2f}" if p_max is not None else "-"
        npv_s = f"{npv_diff:,.0f}" if npv_diff is not None else "-"
        feas = "Yes" if (p_min and p_max and p_min <= p_max) else "No" if (p_min and p_max) else "-"

        print(f"{bm_name:<15} {p_min_s:>12} {p_max_s:>12} {feas:>10} {npv_s:>14}")

    # Installed technologies (mit korrekten Einheiten)
    STORAGE_DEVICES = ["TES", "CTES", "BAT", "H2S", "GS"]
    AREA_DEVICES = ["PV", "STC"]

    print(f"\n{'BM':<15} {'Installed Technologies'}")
    print("-" * 66)
    for bm_name, result in all_results.items():
        caps = result.get("capacities", {}).get("central", {})
        techs = []
        for dev in ["HP", "EB", "CHP", "BCHP", "WCHP", "BOI", "BBOI", "WBOI",
                    "STC", "PV", "WT", "TES", "BAT", "CTES", "GHP", "FC"]:
            if dev in caps:
                dev_data = caps[dev]
                if dev in STORAGE_DEVICES:
                    c = dev_data.get("cap_kWh", 0)
                    if c > 0:
                        techs.append(f"{dev}={c:.0f}kWh")
                elif dev in AREA_DEVICES:
                    c = dev_data.get("cap_m2", 0)
                    if c > 0:
                        techs.append(f"{dev}={c:.0f}m²")
                else:
                    c = dev_data.get("cap_kW", 0)
                    if c > 0:
                        techs.append(f"{dev}={c:.0f}kW")
        print(f"{bm_name:<15} {', '.join(techs) if techs else '-'}")

    # Heat grid comparison
    print(f"\n{'BM':<15} {'Pipe Length [m]':>16} {'Heat Loss [%]':>14} {'Ann. Costs [€/a]':>18}")
    print("-" * 66)
    for bm_name, result in all_results.items():
        hg = result.get("heat_grid", {})
        metrics = hg.get("metrics", {})
        costs = hg.get("costs", {})

        length = metrics.get("total_pipe_length_m", 0)
        loss = metrics.get("heat_loss_percentage", 0)
        ann = costs.get("ann_costs", 0)

        print(f"{bm_name:<15} {length:>16.0f} {loss:>14.1f} {ann:>18,.0f}")

def resolve_scenario_dir(base_dir, scenario_variant):
    district_letter = scenario_variant[0].upper()
    return os.path.join(base_dir, f"District_{district_letter}", scenario_variant)
# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    # ═══════════════════════════════════════════════════════════════════
    # KONFIGURATION
    # ═══════════════════════════════════════════════════════════════════
    SCENARIO_VARIANT = "A01"
    SCENARIO_DIR = resolve_scenario_dir(SCENARIOS_ROOT, SCENARIO_VARIANT)

    REFERENCE_SCENARIO_NAME = f"{SCENARIO_VARIANT}_ref"
    BM_SCENARIO_NAME = f"{SCENARIO_VARIANT}_bm"

    BM_CONFIGS = {
        "waermecontracting": ".env.CONFIG.WAERMECONTRACTING",
        "waermecontracting_ggv": ".env.CONFIG.WAERMECONTRACTING_GGV",
        "waermecontracting_kundenanlage": ".env.CONFIG.WAERMECONTRACTING_KUNDENANLAGE",
        "waermegenossenschaft": ".env.CONFIG.WAERMEGENOSSENSCHAFT",
    }

    # Demand-Profile sind heater- und business-model-unabhängig.
    # -> ALLE Reference-Varianten teilen denselben scenario_name (REFERENCE_SCENARIO_NAME),
    # damit auch der via get_base_demand_name abgeleitete Demand-Filename identisch ist.
    # Unterschied zwischen ref_boi/ref_wp liegt allein im env_path und reference_case.
    REFERENCE_CONFIGS = {
        "ref_boi": {
            "env": ".env.CONFIG.REF_BOI",
            "reference_case": "boi",
            "scenario_name": f"{SCENARIO_VARIANT}_ref_boi",
        },
        "ref_wp": {
            "env": ".env.CONFIG.REF_WP",
            "reference_case": "hp_pv",
            "scenario_name": f"{SCENARIO_VARIANT}_ref_wp",
        },
    }

    all_results, all_saved_files, ref_values = run_reference_and_all_bms(
        reference_scenario_name=REFERENCE_SCENARIO_NAME,
        bm_scenario_name=BM_SCENARIO_NAME,
        bm_configs=BM_CONFIGS,
        reference_configs=REFERENCE_CONFIGS,
        topology_option="road",
        calcUserProfiles=False,
        saveUserProfiles=False,
        save_results=True,
        include_time_series=True,
        scenario_variant=SCENARIO_VARIANT,
        scenario_dir=SCENARIO_DIR,
    )
    # ═══════════════════════════════════════════════════════════════════
    # OPTION 2: Nur gespeicherte Ergebnisse laden (schnell!)
    # ═══════════════════════════════════════════════════════════════════

    # results_dir = f"results/{RESULTS_SUBFOLDER}"
    # all_results = load_and_analyze_results(results_dir, SCENARIO_NAME)
    # print_loaded_results_summary(all_results)