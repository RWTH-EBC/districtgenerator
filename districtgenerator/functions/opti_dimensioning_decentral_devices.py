"""Select a building's cheapest heating concept with existing fixed sizing rules."""

import copy
import json
from pathlib import Path

import numpy as np
import pyomo.environ as pyo

from districtgenerator.classes.KPIs import KPIs
from districtgenerator.classes.system import BES
from districtgenerator.functions import opti_central, solver_config


def annual_operation_weights(eco_data):
    """Discount support-year intervals and annualize over the observation horizon."""
    horizon = eco_data["observation_time"]
    rate = eco_data["interest_rate"]
    q = 1 + rate
    years = sorted(eco_data["interpolation_points"])
    crf = 1 / horizon if rate == 0 else q ** horizon * rate / (q ** horizon - 1)
    return {
        year: crf * sum(q ** -(t + 1) for t in range(
            year, years[index + 1] if index + 1 < len(years) else horizon))
        for index, year in enumerate(years)
    }


def choose_heating_concept(data, building, candidates):
    """Compare standalone building costs; final district operation is optimized later."""
    requested = building["buildingFeatures"]["heater"]
    building_id = int(building["buildingFeatures"]["id"])
    result_dir = Path(data.resultPath) / "heating_selection" / f"building_{building_id}"
    result_dir.mkdir(parents=True, exist_ok=True)
    year_weights = annual_operation_weights(data.ecoData)
    evaluated = {}
    sized = {}
    selected = None
    best_cost = float("inf")

    for concept in candidates:
        candidate = building.copy()
        candidate["buildingFeatures"] = building["buildingFeatures"].copy()
        candidate["buildingFeatures"]["heater"] = concept
        candidate["envelope"] = copy.copy(building["envelope"])
        candidate["capacities"] = building["bes_obj"].designECS(candidate, data.site)
        sized[concept] = candidate["capacities"]

        evaluation = copy.copy(data)
        evaluation.district = [candidate]
        evaluation.centralDevices = {}
        evaluation.pyomo_config = copy.deepcopy(data.pyomo_config)
        if evaluation.pyomo_config["solver_name"] == "gurobi":
            # Distinguish infeasibility from unboundedness before rejecting a candidate.
            evaluation.pyomo_config["solver_options"]["dual_reductions"] = 0

        if BES.get_cooling_supply(candidate["buildingFeatures"]) == "cooling_grid":
            # Network cooling is independent of the local heating choice.
            candidate["user"] = copy.copy(building["user"])
            candidate["user"].cooling_cluster = np.zeros_like(building["user"].cooling_cluster)
            candidate["buildingFeatures"]["cooling"] = 0

        opti_central.compute_decentral_hp_sink_temperature(
            [candidate], data.decentral_device_data, data.design_building_data)
        device_costs = KPIs.building_fixed_costs(data, candidate)
        fixed_cost = sum(device["subsidized_annual_cost"] for device in device_costs.values())
        operating_by_year = {}
        feasible = True
        concept_dir = result_dir / concept
        concept_dir.mkdir(exist_ok=True)

        for year in year_weights:
            annual_operation = 0.0
            economics = dict(data.all_sim_ecoData[year], optimization_focus=0)
            for cluster in range(data.time["clusterNumber"]):
                model = pyo.ConcreteModel(name=f"Heating_selection_{concept}_{year}_{cluster}")
                opti_central.build_model(model, evaluation, year, cluster, economics)
                result = solver_config.execute_and_diagnose(
                    model, evaluation.pyomo_config, model.name, str(concept_dir))
                termination = result.solver.termination_condition
                if termination == pyo.TerminationCondition.infeasible:
                    evaluated[concept] = {"status": "infeasible", "year": year, "cluster": cluster}
                    feasible = False
                    break
                if termination != pyo.TerminationCondition.optimal:
                    raise RuntimeError(
                        f"Building {building_id}, concept {concept}: solver ended with {termination}; "
                        "the cheapest concept cannot be determined reliably.")
                annual_operation += (pyo.value(model.operational_costs)
                                     * data.clusterWeights[data.clusters[cluster]])
            if not feasible:
                break
            operating_by_year[year] = annual_operation

        if not feasible:
            continue
        operating_cost = sum(operating_by_year[year] * weight for year, weight in year_weights.items())
        total = fixed_cost + operating_cost
        evaluated[concept] = {
            "status": "optimal", "annual_fixed_cost_eur": fixed_cost,
            "annual_operating_cost_eur": operating_cost, "total_annual_cost_eur": total,
            "operating_cost_by_support_year_eur": operating_by_year,
            "device_costs": device_costs,
        }
        if total < best_cost:
            selected, best_cost = concept, total

    summary = {
        "requested_heater": requested, "selected_heater": selected,
        "basis": "Standalone building, fixed capacities, minimum total annual cost",
        "candidates": evaluated,
    }
    with (result_dir / "comparison.json").open("w", encoding="utf-8") as output:
        json.dump(summary, output, indent=2, default=float, allow_nan=False)
    if selected is None:
        raise ValueError(f"Building {building_id}: no feasible heating concept among {candidates}.")
    building["heating_selection"] = summary
    building["buildingFeatures"]["heater"] = selected
    building["capacities"] = sized[selected]
    print(f"Building {building_id}: selected {selected}, total annual cost {best_cost:.2f} EUR/a.")
