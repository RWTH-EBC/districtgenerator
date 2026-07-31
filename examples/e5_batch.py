# -*- coding: utf-8 -*-

"""
Batch-generate demand profiles for existing typdistrict scenario CSV files.

Default use:
    python examples/e5_batch.py

By default, this processes all existing district A, B, C, D, E, F, H and I
scenarios with 30 buildings. It runs three scenarios in parallel, each with
four building profile threads. This gives parallelism across scenarios and
buildings without pushing memory usage as hard as many manually started runs.
"""

import argparse
import re
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_DIR = REPO_ROOT / "districtgenerator" / "data" / "scenarios"
DEMAND_DIR = REPO_ROOT / "districtgenerator" / "results" / "demands"

BASE_PROFILE_REQUIRED_SHEETS = {
    "Electricity",
    "Hot Water",
    "Hot Water Minute",
    "Occupancy",
    "Internal Gains",
    "EV_demand_agg",
    "EV_charging_agg",
    "ICE_fuel_agg",
    "EV_demand_individual",
    "EV_charging_individual",
    "ICE_fuel_individual",
    "Car_availibility_individual",
    "Car Info",
    "Building Info",
}

THERMAL_PROFILE_REQUIRED_SHEETS = {
    "heating",
    "cooling",
}

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def find_scenarios(districts, buildings, seeds=None):
    """
    Return scenario names for existing CSV files matching district/building filters.
    """
    seed_filter = set(seeds) if seeds is not None else None
    scenarios = []

    for district in districts:
        pattern = f"district_{district}_seed_*_buildings_{buildings}.csv"
        for csv_path in SCENARIO_DIR.glob(pattern):
            match = re.fullmatch(
                rf"district_{district}_seed_(\d+)_buildings_{buildings}\.csv",
                csv_path.name,
            )
            if match is None:
                continue

            seed = int(match.group(1))
            if seed_filter is not None and seed not in seed_filter:
                continue

            scenarios.append((district, seed, csv_path.stem))

    return sorted(scenarios, key=lambda item: (item[0], item[1]))


def profile_workbook_is_complete(unique_name, require_thermal=True):
    """
    Return True when the saved building demand workbook exists and has all needed sheets.
    """
    profile_file = DEMAND_DIR / f"{unique_name}.xlsx"
    if not profile_file.exists():
        return False

    required_sheets = set(BASE_PROFILE_REQUIRED_SHEETS)
    if require_thermal:
        required_sheets.update(THERMAL_PROFILE_REQUIRED_SHEETS)

    try:
        import openpyxl

        workbook = openpyxl.load_workbook(profile_file, read_only=True, data_only=True)
        missing_sheets = required_sheets.difference(workbook.sheetnames)
        workbook.close()
    except Exception:
        return False

    return not missing_sheets


def mixed_group_combined_name(scenario_name, buildings):
    """
    Return the combined profile name that Datahandler writes for a mixed-use group.
    """
    main_building = None
    secondary_building = None
    parent_id = None

    for building in buildings:
        features = building["buildingFeatures"]
        parent_id = features["mixed_parent_id"]
        if features["mixed_role"] == "main":
            main_building = building
        elif features["mixed_role"] == "secondary":
            secondary_building = building

    if main_building is None or secondary_building is None:
        return None

    main_type = main_building["buildingFeatures"]["building"]
    secondary_type = secondary_building["buildingFeatures"]["building"]
    return f"{scenario_name}_{parent_id}_{main_type}+{secondary_type}"


def filter_missing_profile_buildings(data, force=False):
    """
    Keep only buildings whose profile workbook is missing or incomplete.

    Mixed-use buildings are handled as groups: if one split part or the combined
    profile is missing, both split parts are regenerated together.
    """
    if force:
        return len(data.district), 0

    mixed_groups = {}
    for building in data.district:
        features = building["buildingFeatures"]
        if features.get("is_mixed_part", False):
            mixed_groups.setdefault(features["mixed_parent_id"], []).append(building)

    mixed_parents_to_regenerate = set()
    missing_regular_building_names = set()

    for building in data.district:
        features = building["buildingFeatures"]
        if profile_workbook_is_complete(building["unique_name"]):
            continue

        if features.get("is_mixed_part", False):
            mixed_parents_to_regenerate.add(features["mixed_parent_id"])
        else:
            missing_regular_building_names.add(building["unique_name"])

    for parent_id, buildings in mixed_groups.items():
        combined_name = mixed_group_combined_name(data.scenario_name, buildings)
        if combined_name is not None and not profile_workbook_is_complete(
            combined_name,
            require_thermal=False,
        ):
            mixed_parents_to_regenerate.add(parent_id)

    buildings_to_generate = []
    for building in data.district:
        features = building["buildingFeatures"]
        if features.get("is_mixed_part", False):
            if features["mixed_parent_id"] in mixed_parents_to_regenerate:
                buildings_to_generate.append(building)
        elif building["unique_name"] in missing_regular_building_names:
            buildings_to_generate.append(building)

    original_count = len(data.district)
    skipped_count = original_count - len(buildings_to_generate)
    data.district = buildings_to_generate

    return len(buildings_to_generate), skipped_count


def generate_demands_for_scenario(scenario_name, max_threads, force=False):
    """
    Generate and save demand profiles for one scenario.
    """
    from districtgenerator.classes import Datahandler

    print(f"\n=== Running {scenario_name} ===")

    data = Datahandler(
        scenario_name=scenario_name,
        env_path=".env.CONFIG.PAPER",
    )

    data.generateEnvironment()
    data.initializeBuildings()
    data.generateBuildings()

    buildings_to_generate, skipped_count = filter_missing_profile_buildings(
        data,
        force=force,
    )
    if buildings_to_generate == 0:
        print(f"All building profiles already exist for {scenario_name}; skipping scenario.")
        return scenario_name

    if skipped_count:
        print(
            f"Skipping {skipped_count} already complete building profile(s); "
            f"generating {buildings_to_generate} missing/incomplete profile(s)."
        )

    data.generateDemands(
        calcUserProfiles=True,
        saveUserProfiles=True,
        max_threads=max_threads,
    )

    return scenario_name


def run_scenario_job(job):
    """
    Worker wrapper for optional scenario-level multiprocessing.
    """
    scenario_name, max_threads, force = job
    return generate_demands_for_scenario(
        scenario_name=scenario_name,
        max_threads=max_threads,
        force=force,
    )


def parse_seed_list(seed_text):
    """
    Parse seed strings like '1,2,5-8'.
    """
    if not seed_text:
        return None

    seeds = set()
    for part in seed_text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = part.split("-", 1)
            seeds.update(range(int(start), int(end) + 1))
        else:
            seeds.add(int(part))

    return sorted(seeds)


def main():
    parser = argparse.ArgumentParser(
        description="Generate demand profiles for existing typdistrict scenario CSVs."
    )
    parser.add_argument(
        "--districts",
        default="ABCDEFHI",
        help="District types to process, e.g. EF or EFG. Default: ABCDEFHI.",
    )
    parser.add_argument(
        "--buildings",
        type=int,
        default=30,
        help="Number of buildings in the scenario name. Default: 30.",
    )
    parser.add_argument(
        "--seeds",
        default=None,
        help="Optional seed filter, e.g. 1,2,5-8. Default: all existing seeds.",
    )
    parser.add_argument(
        "--max-threads",
        type=int,
        default=4,
        help="Maximum building-profile threads per scenario. Default: 4.",
    )
    parser.add_argument(
        "--scenario-workers",
        type=int,
        default=3,
        help=(
            "Number of scenarios to process in parallel. Default: 3. "
            "For example, --scenario-workers 3 --max-threads 4 runs three "
            "scenarios at once, each with four building-profile threads."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only list scenarios without generating profiles.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recalculate all building profiles, even if saved profiles already exist.",
    )
    args = parser.parse_args()

    districts = [district.strip().upper() for district in args.districts if district.strip()]
    seeds = parse_seed_list(args.seeds)
    scenarios = find_scenarios(districts, args.buildings, seeds=seeds)

    print(f"Found {len(scenarios)} scenario(s).")
    print(
        f"Run mode: {args.scenario_workers} scenario worker(s), "
        f"{args.max_threads} building thread(s) per scenario."
    )
    for _, seed, scenario_name in scenarios:
        print(f"  seed {seed}: {scenario_name}")

    if args.dry_run:
        return

    failed_runs = []

    if args.scenario_workers <= 1:
        for _, _, scenario_name in scenarios:
            try:
                generate_demands_for_scenario(
                    scenario_name=scenario_name,
                    max_threads=args.max_threads,
                    force=args.force,
                )
            except Exception as error:
                print(f"\n!!! Failed: {scenario_name}")
                print(error)
                traceback.print_exc()
                failed_runs.append(scenario_name)
    else:
        jobs = [
            (scenario_name, args.max_threads, args.force)
            for _, _, scenario_name in scenarios
        ]
        with ProcessPoolExecutor(max_workers=args.scenario_workers) as executor:
            future_to_scenario = {
                executor.submit(run_scenario_job, job): job[0]
                for job in jobs
            }
            for future in as_completed(future_to_scenario):
                scenario_name = future_to_scenario[future]
                try:
                    finished_scenario = future.result()
                    print(f"\n=== Finished {finished_scenario} ===")
                except Exception as error:
                    print(f"\n!!! Failed: {scenario_name}")
                    print(error)
                    traceback.print_exc()
                    failed_runs.append(scenario_name)

    print("\n=== Batch run finished ===")

    if failed_runs:
        print("Failed scenarios:")
        for scenario in failed_runs:
            print(f"- {scenario}")
    else:
        print("All scenarios completed successfully.")


if __name__ == "__main__":
    main()
