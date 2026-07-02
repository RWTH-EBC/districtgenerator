# -*- coding: utf-8 -*-

from districtgenerator.classes import *
import traceback


def generate_demands_for_scenario(district, seed, buildings=30):
    scenario_name = f"district_{district}_seed_{seed}_buildings_{buildings}"

    print(f"\n=== Running {scenario_name} ===")

    data = Datahandler(
        scenario_name=scenario_name,
        env_path=".env.CONFIG.PAPER"
    )

    data.generateEnvironment()
    data.initializeBuildings()
    data.generateBuildings()

    data.generateDemands(
        calcUserProfiles=True,
        saveUserProfiles=True
    )

    return data


if __name__ == "__main__":

    districts = list("I")
    seeds = range(10, 21)
    buildings = 30

    failed_runs = []

    for district in districts:
        for seed in seeds:
            scenario_name = f"district_{district}_seed_{seed}_buildings_{buildings}"

            try:
                generate_demands_for_scenario(
                    district=district,
                    seed=seed,
                    buildings=buildings
                )

            except Exception as e:
                print(f"\n!!! Failed: {scenario_name}")
                print(e)
                traceback.print_exc()
                failed_runs.append(scenario_name)

    print("\n=== Batch run finished ===")

    if failed_runs:
        print("Failed scenarios:")
        for scenario in failed_runs:
            print(f"- {scenario}")
    else:
        print("All scenarios completed successfully.")