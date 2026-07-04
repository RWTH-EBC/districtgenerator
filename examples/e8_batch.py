# -*- coding: utf-8 -*-

"""
Batch version of e8_scenario_evaluation.py.

Runs the full district generation, central/decentral design, clustered operation,
KPI calculation, and certificate generation for multiple 30-building scenarios.
"""

from districtgenerator.classes import *
from districtgenerator.data_handling.config import load_global_config
import os
import traceback
import warnings


ENV_PATH = ".env.CONFIG.PAPER"
DISTRICTS = list("A")
SEEDS = range(1, 6)
BUILDINGS = 30
CREATE_CERTIFICATE = True
BUILDING_HEATER_OVERRIDE = "HP,BOI,BBOI"  # Example: "heat_grid", "heat_grid_SH", "HP", "BOI", or "opt". None keeps the scenario CSV values.


def get_investment_sensitivity_cases(env_path=ENV_PATH):
    global_config = load_global_config(env_file=env_path)
    if global_config.eco.investment_sensitivity_enabled:
        return ["min", "mean", "max"]
    return ["mean"]


def run_scenario_evaluation(
        scenario_name,
        env_path=ENV_PATH,
        create_certificate=CREATE_CERTIFICATE,
        building_heater_override=BUILDING_HEATER_OVERRIDE,
        investment_sensitivity_case="mean",
        output_scenario_name=None
):
    warnings.filterwarnings("ignore", category=FutureWarning)

    run_label = output_scenario_name or scenario_name
    print(f"\n=== Running {run_label} ({investment_sensitivity_case} investment case) ===")

    data = Datahandler(
        scenario_name=scenario_name,
        output_scenario_name=output_scenario_name,
        investment_sensitivity_case=investment_sensitivity_case,
        env_path=env_path
    )

    if building_heater_override is not None:
        data.scenario["heater"] = str(building_heater_override)
        print(f"Forced all building heaters to: {building_heater_override}")

    topology_option = data.heat_grid_data["topology_option"]

    data.generateDistrictComplete(
        calcUserProfiles=False,
        saveUserProfiles=False,
        topology_option=topology_option,
        gen_cars=False
    )

    data.optimizationClusters()
    data.calculateKPIs()

    if create_certificate:
        data.KPIs.create_certificate(data=data, result_path=data.resultPath)

    print(f"Completed {run_label}")
    return data


def scenario_exists(scenario_name):
    scenario_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "districtgenerator",
        "data",
        "scenarios"
    )

    csv_path = os.path.join(scenario_dir, f"{scenario_name}.csv")
    json_path = os.path.join(scenario_dir, f"{scenario_name}.json")

    return os.path.isfile(csv_path) and os.path.isfile(json_path)


def run_batch():
    failed_runs = []
    skipped_runs = []
    completed_runs = []
    investment_cases = get_investment_sensitivity_cases(ENV_PATH)

    for district in DISTRICTS:
        for seed in SEEDS:
            scenario_name = f"district_{district}_seed_{seed}_buildings_{BUILDINGS}"

            if not scenario_exists(scenario_name):
                print(f"\n--- Skipping missing scenario: {scenario_name}")
                skipped_runs.append(scenario_name)
                continue

            for investment_case in investment_cases:
                run_label = f"{scenario_name}_inv_{investment_case}" if len(investment_cases) > 1 else scenario_name

                try:
                    run_scenario_evaluation(
                        scenario_name=scenario_name,
                        building_heater_override=BUILDING_HEATER_OVERRIDE,
                        investment_sensitivity_case=investment_case,
                        output_scenario_name=run_label
                    )
                    completed_runs.append(run_label)

                except Exception as exc:
                    print(f"\n!!! Failed: {run_label}")
                    print(exc)
                    traceback.print_exc()
                    failed_runs.append(run_label)

    print("\n=== Batch run finished ===")
    print(f"Completed: {len(completed_runs)}")
    print(f"Skipped:   {len(skipped_runs)}")
    print(f"Failed:    {len(failed_runs)}")

    if failed_runs:
        print("\nFailed scenarios:")
        for scenario_name in failed_runs:
            print(f"- {scenario_name}")

    if skipped_runs:
        print("\nSkipped scenarios:")
        for scenario_name in skipped_runs:
            print(f"- {scenario_name}")

    return {
        "completed": completed_runs,
        "skipped": skipped_runs,
        "failed": failed_runs,
    }


if __name__ == "__main__":
    batch_results = run_batch()
