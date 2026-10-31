# -*- coding: utf-8 -*-

"""
Batch-generate demand profiles for existing typdistrict scenario CSV files.

Generate profiles from the general scenarios folder:
    python examples/e5_batch.py

Generate profiles for the 80 active Paper_3 districts:
    python examples/e5_batch.py --paper-3

Paper_3 reads Paper_3/districts and writes Paper_3/load_profiles/<scenario>.
General mode reads districtgenerator/data/scenarios and writes
districtgenerator/results/demands. Add --dry-run to preview either mode.
One scenario runs at a time with up to eight apartment-level profile processes.
"""

import argparse
import csv
import hashlib
import random
import re
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_DIR = REPO_ROOT / "districtgenerator" / "data" / "scenarios"
DEMAND_DIR = REPO_ROOT / "districtgenerator" / "results" / "demands"
PAPER_3_DISTRICTS_PER_TYPE = 10

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


def find_scenarios(districts, buildings, seeds=None, scenario_dir=SCENARIO_DIR):
    """
    Return scenario names for existing CSV files matching district/building filters.
    """
    seed_filter = set(seeds) if seeds is not None else None
    scenarios = []

    for district in districts:
        pattern = f"district_{district}_seed_*_buildings_{buildings}.csv"
        for csv_path in Path(scenario_dir).glob(pattern):
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


def profile_workbook_is_complete(unique_name, require_thermal=True, demand_dir=DEMAND_DIR):
    """
    Return True when the saved building demand workbook exists and has all needed sheets.
    """
    profile_file = Path(demand_dir) / f"{unique_name}.xlsx"
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


def missing_profile_tasks(scenario_name, scenario_file, demand_dir):
    """Count missing profiles, treating split mixed-use parts as one group."""
    missing = 0
    with Path(scenario_file).open(newline='', encoding='utf-8-sig') as stream:
        for row in csv.DictReader(stream, delimiter=';'):
            prefix = f"{scenario_name}_{row['id']}_"
            if '+' in row['building']:
                main, secondary = row['building'].split('+')
                checks = [(prefix + main + '_Main', True),
                          (prefix + secondary + '_Secondary', True),
                          (prefix + row['building'], False)]
                count = 2
            else:
                checks, count = [(prefix + row['building'], True)], 1
            if not all(profile_workbook_is_complete(name, require_thermal=thermal, demand_dir=demand_dir)
                       for name, thermal in checks):
                missing += count
    return missing


def filter_missing_profile_buildings(data, force=False):
    """
    Keep only buildings whose profile workbook is missing or incomplete.

    Mixed-use buildings are handled as groups: if one split part or the combined
    profile is missing, both split parts are regenerated together.
    """
    if force:
        return len(data.district), 0

    demand_dir = Path(data.resultPath) / "demands"
    mixed_groups = {}
    for building in data.district:
        features = building["buildingFeatures"]
        if features.get("is_mixed_part", False):
            mixed_groups.setdefault(features["mixed_parent_id"], []).append(building)

    mixed_parents_to_regenerate = set()
    missing_regular_building_names = set()

    for building in data.district:
        features = building["buildingFeatures"]
        if profile_workbook_is_complete(building["unique_name"], demand_dir=demand_dir):
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
            demand_dir=demand_dir,
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


def generate_demands_for_scenario(scenario_name, max_threads=8, force=False,
                                  scenario_dir=None, result_root=None):
    """
    Generate and save demand profiles for one scenario.
    """
    from districtgenerator.classes import Datahandler

    print(f"\n=== Running {scenario_name} ===")

    result_path = Path(result_root) / scenario_name if result_root is not None else None
    scenario_file = Path(scenario_dir or SCENARIO_DIR) / f"{scenario_name}.csv"
    demand_dir = result_path / 'demands' if result_path is not None else DEMAND_DIR
    if not force and missing_profile_tasks(scenario_name, scenario_file, demand_dir) == 0:
        print(f"All building profiles already exist for {scenario_name}; skipping scenario.")
        return scenario_name
    # Reuse the same random streams when resuming an incomplete scenario.
    profile_seed = int.from_bytes(hashlib.sha256(scenario_name.encode('utf-8')).digest()[:4], 'little')
    random.seed(profile_seed)
    import numpy as np
    np.random.seed(profile_seed)
    print(f"Profile seed: {profile_seed}")
    if result_path is not None:
        result_path.mkdir(parents=True, exist_ok=True)
        (result_path / "demands").mkdir(exist_ok=True)

    data = Datahandler(
        scenario_name=scenario_name,
        env_path=".env.CONFIG.PAPER",
        scenario_file_path=str(scenario_dir) if scenario_dir is not None else None,
        resultPath=str(result_path) if result_path is not None else None,
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
        profile_seed=profile_seed,
    )

    return scenario_name


def run_scenario_job(job):
    """
    Worker wrapper for optional scenario-level multiprocessing.
    """
    scenario_name, max_threads, force, scenario_dir, result_root = job
    return generate_demands_for_scenario(
        scenario_name=scenario_name,
        max_threads=max_threads,
        force=force,
        scenario_dir=scenario_dir,
        result_root=result_root,
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
    source_group = parser.add_mutually_exclusive_group()
    source_group.add_argument(
        "--paper-3",
        action="store_true",
        help="Use Paper_3/districts and save under Paper_3/load_profiles/<scenario>.",
    )
    source_group.add_argument(
        "--general-scenarios",
        action="store_false",
        dest="paper_3",
        help="Use the general scenario and result folders (default).",
    )
    parser.set_defaults(paper_3=False)
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
        default=8,
        help="Maximum profile processes per scenario. Default: 8 (flat-level generation).",
    )
    parser.add_argument(
        "--scenario-workers",
        type=int,
        default=1,
        help=(
            "Number of scenarios to process in parallel. Default: 1. "
            "Each scenario has its own profile process pool, so keep this at 1 "
            "when using eight profile workers to avoid multiplying process counts."
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

    if args.max_threads < 1 or args.scenario_workers < 1:
        parser.error("Worker counts must be positive.")
    paper_root = SCENARIO_DIR / "Paper_3"
    if args.paper_3:
        scenario_dir = next((p.resolve() for p in (paper_root / 'districts', paper_root / 'Districts')
                             if p.is_dir()), paper_root)
        organized = scenario_dir != paper_root
        result_root = paper_root / ("load_profiles" if organized else "results")
    else:
        scenario_dir, result_root = SCENARIO_DIR, None
    if not scenario_dir.is_dir():
        parser.error(f"Scenario folder does not exist: {scenario_dir}")
    if args.paper_3 and (args.districts != "ABCDEFHI" or args.buildings != 30 or args.seeds is not None):
        parser.error("Paper_3 mode processes all active districts; do not combine it with district, building or seed filters.")

    districts = [district.strip().upper() for district in args.districts if district.strip()]
    seeds = parse_seed_list(args.seeds)
    scenarios = find_scenarios(districts, args.buildings, seeds=seeds, scenario_dir=scenario_dir)
    if args.paper_3:
        for district in districts:
            count = sum(item[0] == district for item in scenarios)
            if count != PAPER_3_DISTRICTS_PER_TYPE:
                parser.error(f"Paper_3 must contain {PAPER_3_DISTRICTS_PER_TYPE} districts of type {district}; found {count}.")
        missing_json = [name for _, _, name in scenarios if not (scenario_dir / f"{name}.json").is_file()]
        if missing_json:
            parser.error(f"Missing district JSON files: {', '.join(missing_json)}")

    print(f"Scenario inputs: {scenario_dir}")
    print(f"Profile outputs: {result_root / '<scenario>' / 'demands' if result_root is not None else DEMAND_DIR}")
    print(f"Found {len(scenarios)} scenario(s).")
    print(
        f"Run mode: {args.scenario_workers} scenario worker(s), "
        f"{args.max_threads} profile process(es) per scenario (flat-level generation)."
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
                    scenario_dir=scenario_dir,
                    result_root=result_root,
                )
            except Exception as error:
                print(f"\n!!! Failed: {scenario_name}")
                print(error)
                traceback.print_exc()
                failed_runs.append(scenario_name)
    else:
        jobs = [
            (scenario_name, args.max_threads, args.force, scenario_dir, result_root)
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
