# -*- coding: utf-8 -*-

"""
We reached the final step, to generate our first district: Generate demand profiles for our buildings.
"""

# Import classes of the districtgenerator to be able to use the district generator.
from districtgenerator.classes import *
from districtgenerator.data_handling.config import load_global_config
import csv
import os
import warnings


SCENARIO_NAME = "district_F_seed_27_buildings_30"
ENV_PATH = ".env.CONFIG.EXAMPLE"


def _scenario_csv_path(scenario_name):
    return os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "districtgenerator",
        "data",
        "scenarios",
        f"{scenario_name}.csv"
    )


def _heater_values_from_scenario(scenario_name):
    with open(_scenario_csv_path(scenario_name), newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        return {
            str(row.get("heater", "")).strip()
            for row in reader
            if str(row.get("heater", "")).strip()
        }


def get_system_output_label(scenario_name, env_path=ENV_PATH):
    global_config = load_global_config(env_file=env_path)
    heatgrid_generation = str(global_config.heatgrid.heatgrid_generation).upper()
    heat_grid_heaters = _heater_values_from_scenario(scenario_name).intersection(
        {"heat_grid", "heat_grid_OEB", "heat_grid_BEB"}
    )

    if not heat_grid_heaters:
        return "decentral"

    if heatgrid_generation == "5G":
        return "central_5G"

    central_types = []
    if "heat_grid" in heat_grid_heaters:
        central_types.append("4G")
    if "heat_grid_OEB" in heat_grid_heaters:
        central_types.append("OEB")
    if "heat_grid_BEB" in heat_grid_heaters:
        central_types.append("BEB")

    return "central_" + "_".join(central_types)


def get_investment_sensitivity_cases(env_path=ENV_PATH):
    global_config = load_global_config(env_file=env_path)
    if global_config.eco.investment_sensitivity_enabled:
        return ["min", "mean", "max"]
    return ["mean"]


def run_scenario_evaluation_case(
        scenario_name=SCENARIO_NAME,
        env_path=ENV_PATH,
        investment_sensitivity_case="mean",
        output_scenario_name=None
):
    warnings.filterwarnings("ignore", category=FutureWarning)

    # Initialize District
    data = Datahandler(
        scenario_name=scenario_name,
        output_scenario_name=output_scenario_name,
        investment_sensitivity_case=investment_sensitivity_case,
        env_path=env_path
    )

    # We directly generate a complete district.
    # This includes the use of the EHDO tool to obtain an optimized energy central for neighborhoods.
    # EHDO is a tool for planning and designing complex energy systems.
    # Its key feature is the coupling of different sectors (e.g., electricity, heating, cooling).
    # In the early planning phases of energy supply concepts for neighborhoods,
    # the tool provides an initial assessment of the optimal system configuration, sizing,
    # and economic efficiency.
    # As input, EHDO requires data on energy demands and location (weather),
    # which are provided directly from the output of the district generator.
    # Additional information about the technologies to be considered for the dimensioning
    # of the energy central and the economic parameters are read from additional
    # .csv and .json data sources.

    topology_option = data.heat_grid_data["topology_option"]

    data.generateDistrictComplete(
        calcUserProfiles=False,
        saveUserProfiles=False,
        topology_option=topology_option,
        gen_cars=True
    )

    # Calculation of the devices' optimal operation
    data.optimizationClusters()

    # Calculation of the key performance indicators using the devices' operation profiles of clustered time periods
    data.calculateKPIs()

    # Create a certificate (PDF) which summarizes the district parameters and calculated KPIs
    data.KPIs.create_certificate(data=data, result_path=data.resultPath)
    print(f"Completed {data.output_scenario_name} ({investment_sensitivity_case} investment case).")
    return data


def example8_scenario_evaluation():
    investment_cases = get_investment_sensitivity_cases(ENV_PATH)
    system_label = get_system_output_label(SCENARIO_NAME, ENV_PATH)
    results = {}

    for investment_case in investment_cases:
        output_base_name = f"{SCENARIO_NAME}_{system_label}"
        output_scenario_name = (
            f"{output_base_name}_inv_{investment_case}"
            if len(investment_cases) > 1
            else output_base_name
        )
        results[investment_case] = run_scenario_evaluation_case(
            scenario_name=SCENARIO_NAME,
            env_path=ENV_PATH,
            investment_sensitivity_case=investment_case,
            output_scenario_name=output_scenario_name
        )

    print("Congratulations! You calculated an optimized device operation for the selected neighborhood!")
    if len(results) == 1:
        return results["mean"]
    return results


if __name__ == '__main__':
    data = example8_scenario_evaluation()
