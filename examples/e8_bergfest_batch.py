"""Optimize the first ten numeric seeds per Paper_3 type with BERGFEST settings.

Run this file normally for all 240 district/cost cases. Use --dry-run to check
inputs without optimization, --pilot for the first district's three cases, or
--resume <run-folder> to continue a saved run. Existing results are never reused
as writable workspaces: retries receive a new attempt directory.
"""

import argparse
from contextlib import redirect_stdout
from datetime import datetime
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
import traceback
from uuid import uuid4
import xml.etree.ElementTree as ET
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
PAPER_ROOT = ROOT / "districtgenerator" / "data" / "scenarios" / "Paper_3"
RUNS_ROOT = PAPER_ROOT / "optimization_runs"
CONFIG = ROOT / "districtgenerator" / "data" / ".env.CONFIG.BERGFEST"
TYPES = "ABCDEFHI"
CASES = ("mean", "min", "max")
REQUIRED_SHEETS = {
    "Electricity", "Hot Water", "Hot Water Minute", "Occupancy", "Internal Gains",
    "EV_demand_agg", "EV_charging_agg", "ICE_fuel_agg", "EV_demand_individual",
    "EV_charging_individual", "ICE_fuel_individual", "Car_availibility_individual",
    "Car Info", "Building Info", "heating", "cooling",
}
sys.path.insert(0, str(ROOT))


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def select_districts():
    selected = []
    for district_type in TYPES:
        found = []
        for path in PAPER_ROOT.glob(f"district_{district_type}_seed_*_buildings_30.csv"):
            match = re.fullmatch(rf"district_{district_type}_seed_(\d+)_buildings_30", path.stem)
            if match:
                found.append((int(match[1]), path))
        found.sort()
        if len(found) != 20:
            raise ValueError(f"Expected 20 original districts of type {district_type}; found {len(found)}.")
        for seed, path in found[:10]:
            selected.append({"type": district_type, "seed": seed, "name": path.stem,
                             "csv_sha256": digest(path), "json_sha256": digest(path.with_suffix('.json'))})
    return selected


def validate_config(path):
    from districtgenerator.data_handling.config import load_global_config

    config = load_global_config(env_file=str(path))
    if config.eco.hub_electricity_price_mode != "dynamic":
        raise ValueError("BERGFEST must enable dynamic EH purchase/feed-in prices.")
    if not config.eco.investment_sensitivity_enabled:
        raise ValueError("BERGFEST must enable investment sensitivity for mean/min/max.")
    if config.heatgrid.heatgrid_generation != "4G":
        raise ValueError("This batch is configured for the agreed 4G heat_grid system.")
    return config


def validate_source(item):
    for suffix in ("csv", "json"):
        path = PAPER_ROOT / f"{item['name']}.{suffix}"
        if digest(path) != item[f"{suffix}_sha256"]:
            raise ValueError(f"Original scenario changed since this run was prepared: {path}")


def preflight(items, config_path):
    from districtgenerator.classes.datahandler import Datahandler

    validate_config(config_path)
    checked = 0
    for item in items:
        validate_source(item)
        profile_dir = PAPER_ROOT / "results" / item["name"] / "demands"
        # Initialization also resolves mixed-use split names, without generating demands.
        with redirect_stdout(io.StringIO()):
            data = Datahandler(scenario_name=item["name"], env_path=str(config_path),
                               scenario_file_path=str(PAPER_ROOT), resultPath=str(profile_dir.parent))
            if len(data.scenario) != 30:
                raise ValueError(f"Expected 30 scenario rows: {item['name']}")
            data.scenario["heater"] = "heat_grid"
            data.initializeBuildings()
        for building in data.district:
            path = profile_dir / f"{building['unique_name']}.xlsx"
            with ZipFile(path) as archive:
                workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            sheets = {element.attrib["name"] for element in workbook.findall(
                "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheets/"
                "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet")}
            missing = REQUIRED_SHEETS - sheets
            if missing:
                raise ValueError(f"Incomplete saved profile {path}: {sorted(missing)}")
            checked += 1
        print(f"Checked {item['name']}: {len(data.district)} saved building profiles.", flush=True)
    print(f"Preflight passed: {len(items)} districts, {checked} workbooks; no optimization executed.")


def write_json_new(path, payload):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2)


def load_manifest(run_dir):
    run_dir = run_dir.resolve()
    if not run_dir.is_relative_to(RUNS_ROOT.resolve()):
        raise ValueError("The resume folder must be inside Paper_3/optimization_runs.")
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest["version"] != 1 or manifest["cases"] != list(CASES):
        raise ValueError("Unsupported batch manifest.")
    if digest(run_dir / ".env.CONFIG.BERGFEST") != manifest["config_sha256"]:
        raise ValueError("The saved run configuration was modified; start a new run instead.")
    return manifest


def worker(run_dir, scenario, case, attempt):
    import matplotlib
    matplotlib.use("Agg")
    import numpy as np
    from districtgenerator.classes.datahandler import Datahandler

    manifest = load_manifest(run_dir)
    item = next(item for item in manifest["districts"] if item["name"] == scenario)
    if case not in CASES:
        raise ValueError(f"Unknown investment case: {case}")
    validate_source(item)
    validate_config(run_dir / ".env.CONFIG.BERGFEST")
    expected_parent = (run_dir / scenario / case).resolve()
    attempt = attempt.resolve()
    if attempt.parent != expected_parent or not re.fullmatch(r"attempt_\d{3}", attempt.name):
        raise ValueError("Invalid case output directory.")
    if any(attempt.iterdir()):
        raise FileExistsError(f"Attempt directory is not empty: {attempt}")
    # Isolate legacy relative solver logs inside this case, including child processes.
    os.chdir(attempt)
    random.seed(item["seed"])
    np.random.seed(item["seed"])
    for folder in ("generation", "network", "optimization_results"):
        (attempt / folder).mkdir()
    try:
        data = Datahandler(
            scenario_name=scenario, output_scenario_name=f"{scenario}_central_4G_inv_{case}",
            investment_sensitivity_case=case, env_path=str(run_dir / ".env.CONFIG.BERGFEST"),
            resultPath=str(attempt), scenario_file_path=str(PAPER_ROOT),
            profile_input_path=str(PAPER_ROOT / "results" / scenario / "demands"),
            network_output_path=str(attempt / "network" / "topology"))
        data.scenario["heater"] = "heat_grid"
        data.scenario.to_csv(attempt / "scenario_heat_grid.csv", sep=";", index=False)
        data.generateDistrictComplete(calcUserProfiles=False, saveUserProfiles=False,
                                      topology_option=data.heat_grid_data["topology_option"],
                                      gen_cars=None)
        if not all(b["buildingFeatures"]["heater"] == "heat_grid" for b in data.district):
            raise ValueError("Not all buildings are connected to heat_grid.")
        data.optimizationClusters()
        data.calculateKPIs()
        data.saveDistrict()
        data.KPIs.create_certificate(data=data, result_path=data.resultPath)
        write_json_new(attempt / "completed.json", {"scenario": scenario, "case": case,
                       "finished": datetime.now().astimezone().isoformat()})
    except Exception:
        write_json_new(attempt / "failed.json", {"error": traceback.format_exc()})
        raise


def run_batch(run_dir, manifest, pilot):
    items = manifest["districts"][:1] if pilot else manifest["districts"]
    failed = 0
    for item in items:
        for case in CASES:
            case_dir = run_dir / item["name"] / case
            if any(case_dir.glob("attempt_*/completed.json")):
                print(f"Already complete: {item['name']} / {case}", flush=True)
                continue
            case_dir.mkdir(parents=True, exist_ok=True)
            number = 1
            while (case_dir / f"attempt_{number:03d}").exists():
                number += 1
            attempt = case_dir / f"attempt_{number:03d}"
            attempt.mkdir()
            log = case_dir / f"attempt_{number:03d}.log"
            print(f"Running {item['name']} / {case}; log: {log}", flush=True)
            with log.open("x", encoding="utf-8") as stream:
                result = subprocess.run(
                    [sys.executable, "-u", str(Path(__file__).resolve()), "--worker",
                     str(run_dir), item["name"], case, str(attempt)],
                    stdout=stream, stderr=subprocess.STDOUT, cwd=attempt, check=False)
            if result.returncode != 0 or not (attempt / "completed.json").exists():
                failed += 1
                print(f"FAILED: {item['name']} / {case}; see {log}", flush=True)
                # Do not repeat the same infrastructure failure across all 240 jobs.
                raise RuntimeError(f"Batch stopped after a failed case. Resume with --resume {run_dir}")
            print(f"Completed {item['name']} / {case}", flush=True)
    print(f"Finished selected cases. Run folder: {run_dir}; failures: {failed}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Check all selected input profiles without optimization or output creation.")
    parser.add_argument("--pilot", action="store_true", help="Run only the first district in mean/min/max; resume later for the rest.")
    parser.add_argument("--resume", type=Path, help="Continue a saved run using its immutable configuration snapshot.")
    parser.add_argument("--worker", nargs=4, metavar=("RUN", "SCENARIO", "CASE", "ATTEMPT"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        run, scenario, case, attempt = args.worker
        worker(Path(run).resolve(), scenario, case, Path(attempt))
        return
    if args.resume:
        run_dir = args.resume.resolve()
        manifest = load_manifest(run_dir)
        config_path = run_dir / ".env.CONFIG.BERGFEST"
        items = manifest["districts"]
    else:
        items = select_districts()
        config_path = CONFIG
    selected = items[:1] if args.pilot else items
    for district_type in TYPES:
        seeds = [item["seed"] for item in selected if item["type"] == district_type]
        if seeds:
            print(f"Type {district_type}: seeds {seeds}")
    print(f"Selected {len(selected)} districts x 3 investment cases = {len(selected) * 3} evaluations.")
    preflight(selected, config_path)
    if args.dry_run:
        return
    if not args.resume:
        RUNS_ROOT.mkdir(parents=True, exist_ok=True)
        run_dir = RUNS_ROOT / f"BERGFEST_{datetime.now():%Y%m%d-%H%M%S}_{uuid4().hex[:6]}"
        run_dir.mkdir()
        shutil.copyfile(CONFIG, run_dir / ".env.CONFIG.BERGFEST")
        manifest = {"version": 1, "districts": items, "cases": list(CASES),
                    "config_sha256": digest(run_dir / ".env.CONFIG.BERGFEST"),
                    "created": datetime.now().astimezone().isoformat()}
        write_json_new(run_dir / "manifest.json", manifest)
    print(f"All outputs will be stored under: {run_dir}", flush=True)
    run_batch(run_dir, manifest, args.pilot)


if __name__ == "__main__":
    main()
