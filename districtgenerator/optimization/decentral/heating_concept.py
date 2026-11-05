"""
Selection of the cheapest heating concept of a building.

Each candidate heating concept is sized with the fixed sizing rules of the building energy system
and its operation is optimized for the building alone. The concept with the lowest total annual cost (annualized device costs plus annualized operational
costs) is selected. 
"""

import copy
import json
from pathlib import Path

import numpy as np
import pyomo.environ as pyo

from districtgenerator.analysis.kpis import KPIs
from districtgenerator.energy_systems import technologies
from districtgenerator.optimization import solver as solver_config
from districtgenerator.optimization.central import operation as opti_central


def annual_operation_weights(eco_data):
    """
    Weights to annualize the operational costs of the support years.

    Each support year represents the years until the next support year (or until the end of the
    observation period). The operational costs of these years are discounted to the start of the
    observation period and annualized with the capital recovery factor, so they are comparable with
    the annualized device costs. The weights of all support years add up to 1.

    Note: The KPIs weight the support years with the number of years without discounting.

    Note: The same result is given by capital_recovery_factor (economics.annuity) times
    _discount_factor with the interval lengths of _support_year_weights (both in
    optimization.central.dimensioning). Keep both implementations consistent when changing one.

    Parameters
    ----------
    eco_data : dict
        Economic data with the observation period ("observation_time"), the interest rate
        ("interest_rate") and the support years ("interpolation_points"), relative to the start of
        the observation period.

    Returns
    -------
    dict
        Weight for each support year. Multiplied with the operational costs of one year of the
        support year and summed up, this gives the annualized operational costs.
    """
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
    """
    Selects the heating concept with the lowest total annual cost for one building.

    For every candidate, the devices are sized with the fixed sizing rules (designECS) and the
    operation of the building alone is optimized for all clusters and support years with the cost
    focus. Candidates without a feasible solution (infeasible or infeasibleOrUnbounded) are
    discarded. The total annual cost is the sum of
    the annualized device costs (with subsidies) and the annualized operational costs, see
    annual_operation_weights. The comparison of all candidates is saved as
    <resultPath>/heating_selection/building_<id>/comparison.json.

    Parameters
    ----------
    data : Datahandler
        Datahandler with clustered profiles (clusterProfiles must be called before), cluster weights,
        site data, device parameters, economic data of the support years and solver settings.
    building : dict
        Building of data.district. Is changed in place, see Returns.
    candidates : list of str
        Heating concepts (values of buildingFeatures["heater"], e.g. "HP", "BOI") that are compared.

    Returns
    -------
    None
        The building is changed in place: buildingFeatures["heater"] is set to the selected concept,
        "capacities" to its sized devices and "heating_selection" to the comparison of all candidates.

    Raises
    ------
    ValueError
        If no candidate has a feasible solution.
    RuntimeError
        If the solver ends neither optimal nor infeasible, e.g. because of a time limit.
    """
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

        if technologies.get_cooling_supply(candidate["buildingFeatures"]) == "cooling_grid":
            # Network cooling is independent of the local heating choice.
            candidate["user"] = copy.copy(building["user"])
            candidate["user"].cooling_cluster = np.zeros_like(building["user"].cooling_cluster)
            candidate["buildingFeatures"]["cooling"] = 0

        # Sets envelope.hp_measures, which is needed for the investment costs of the measures
        opti_central.apply_hp_low_temp_measures([candidate], data.decentral_device_data)
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
                # Unbounded is not possible in practice (bounded generation, imports have prices), so
                # infeasibleOrUnbounded of solvers other than Gurobi is treated as infeasible.
                if termination in (pyo.TerminationCondition.infeasible,
                                   pyo.TerminationCondition.infeasibleOrUnbounded):
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
