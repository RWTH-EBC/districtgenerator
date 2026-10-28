"""Obtain ten successful districts per Paper_3 type with BERGFEST settings.

Try up to twenty numeric seeds per type until ten pass all three cost cases.
Failed districts remain recorded and are skipped on resume. Use --dry-run to check
inputs without optimization, --pilot for the first district's three cases, or
--resume <run-folder> to continue a saved run. Existing results are never reused
as writable workspaces: retries receive a new attempt directory.
For Slurm arrays, use --resume <run-folder> --type A (one task per type).
"""

import argparse
from contextlib import ExitStack, contextmanager, redirect_stdout
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
import tarfile
from uuid import uuid4
import xml.etree.ElementTree as ET
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
PAPER_ROOT = ROOT / "districtgenerator" / "data" / "scenarios" / "Paper_3"
RUNS_ROOT = PAPER_ROOT / "optimization_runs"
CONFIG = ROOT / "districtgenerator" / "data" / ".env.CONFIG.BERGFEST"
TYPES = "ABCDEFHI"
CASES = ("mean", "min", "max")
TARGET_PER_TYPE = 10
FUNDING_VARIANTS = ("funding_off", "funding_on")
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
        for seed, path in found:
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
    if manifest["version"] not in (1, 2, 3, 4) or manifest["cases"] != list(CASES):
        raise ValueError("Unsupported batch manifest.")
    if digest(run_dir / ".env.CONFIG.BERGFEST") != manifest["config_sha256"]:
        raise ValueError("The saved run configuration was modified; start a new run instead.")
    output_policy(manifest)
    if manifest["version"] == 4:
        validate_comparison(run_dir, manifest)
    return manifest


def evaluation_runs(run_dir, manifest):
    """Use one shared success counter for both funding variants."""
    if manifest.get("version") == 4:
        return [(run_dir / variant, variant) for variant in FUNDING_VARIANTS]
    return [(run_dir, "")]


def validate_comparison(run_dir, manifest):
    configs = []
    if manifest["variants"] != list(FUNDING_VARIANTS):
        raise ValueError("Unsupported funding variants.")
    for variant in FUNDING_VARIANTS:
        child = load_manifest(run_dir / variant)
        if (child["version"] != 3 or child.get("comparison_parent") != ".."
                or child["districts"] != manifest["districts"]
                or child["config_sha256"] != manifest["variant_config_sha256"][variant]
                or output_policy(child) != output_policy(manifest)):
            raise ValueError(f"Comparison variant was modified: {variant}")
        config = validate_config(run_dir / variant / ".env.CONFIG.BERGFEST")
        if config.central.EB["feasible"]:
            raise ValueError("EB must be excluded from both comparison variants.")
        if config.funding.enabled != (variant == "funding_on"):
            raise ValueError(f"Incorrect funding switch in {variant}.")
        values = config.model_dump()
        values["funding"].pop("enabled")
        # EcoConfig retains dotenv extras, including a duplicate of this switch.
        for section in values.values():
            if isinstance(section, dict):
                section.pop("funding_enabled", None)
        configs.append(values)
    if configs[0] != configs[1]:
        raise ValueError("Comparison configurations must differ only in FUNDING_ENABLED.")


def create_comparison_variants(run_dir, manifest):
    from dotenv import set_key

    manifest.update(version=4, variants=list(FUNDING_VARIANTS), variant_config_sha256={})
    for variant in FUNDING_VARIANTS:
        child_dir = run_dir / variant
        child_dir.mkdir()
        config_path = child_dir / ".env.CONFIG.BERGFEST"
        shutil.copyfile(run_dir / ".env.CONFIG.BERGFEST", config_path)
        set_key(str(config_path), "FUNDING_ENABLED", str(variant == "funding_on"), quote_mode="never")
        child = {key: manifest[key] for key in ("districts", "cases", "output_policy", "created")}
        child.update(version=3, comparison_parent="..", config_sha256=digest(config_path))
        manifest["variant_config_sha256"][variant] = child["config_sha256"]
        write_json_new(child_dir / "manifest.json", child)
    validate_comparison(run_dir, manifest)


def output_policy(manifest):
    """Freeze output choices per run; old manifests keep their original outputs."""
    if manifest["version"] < 3:
        return {"solver_export_lp": True, "solver_export_txt": True,
                "solver_export_compact": False, "batch_save_district_pickle": True}
    policy = manifest["output_policy"]
    required = {"solver_export_lp", "solver_export_txt", "solver_export_compact",
                "batch_save_district_pickle"}
    if set(policy) != required or any(type(value) is not bool for value in policy.values()):
        raise ValueError("Invalid saved output policy.")
    if not (policy["solver_export_txt"] or policy["solver_export_compact"]):
        raise ValueError("Detailed solver results must be retained in TXT or compact form.")
    return policy


def save_code_provenance(run_dir):
    """Record the tracked code revision and local changes without changing Git state."""
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                            capture_output=True, check=False)
    changes = subprocess.run(["git", "diff", "--binary", "HEAD", "--"], cwd=ROOT,
                             capture_output=True, check=False)
    if commit.returncode or changes.returncode:
        raise RuntimeError("Cannot record code provenance; start this research batch from a Git checkout.")
    (run_dir / "code_commit.txt").write_bytes(commit.stdout)
    (run_dir / "code_changes.patch").write_bytes(changes.stdout)
    return {name: digest(run_dir / name) for name in ("code_commit.txt", "code_changes.patch")}


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
    config = validate_config(run_dir / ".env.CONFIG.BERGFEST")
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
        policy = output_policy(manifest)
        data.pyomo_config.update({key: value for key, value in policy.items() if key.startswith("solver_")})
        data.scenario["heater"] = "heat_grid"
        if not config.report.batch_building_pv_enabled:
            data.scenario[["f_PV1", "f_PV2"]] = 0.0
        data.scenario.to_csv(attempt / "scenario_heat_grid.csv", sep=";", index=False)
        data.generateDistrictComplete(calcUserProfiles=False, saveUserProfiles=False,
                                      topology_option=data.heat_grid_data["topology_option"],
                                      gen_cars=None)
        if not all(b["buildingFeatures"]["heater"] == "heat_grid" for b in data.district):
            raise ValueError("Not all buildings are connected to heat_grid.")
        if not config.report.batch_building_pv_enabled:
            for building in data.district:
                pv = building["capacities"]["PV"]
                if (np.any(np.asarray(building["generationPV"]) != 0)
                        or any(pv[key] != 0 for key in ("nb_modules", "area", "P_ref"))):
                    raise ValueError(f"Building PV was not disabled: {building['unique_name']}")
        data.optimizationClusters()
        data.calculateKPIs()
        if policy["batch_save_district_pickle"]:
            data.saveDistrict()
        data.KPIs.create_certificate(data=data, result_path=data.resultPath)
        write_json_new(attempt / "completed.json", {"scenario": scenario, "case": case,
                       "finished": datetime.now().astimezone().isoformat(), "output_policy": policy})
    except Exception:
        write_json_new(attempt / "failed.json", {"error": traceback.format_exc()})
        raise


@contextmanager
def type_lock(run_dir, kind):
    """Hold an OS lock; process exit releases it without deleting the lock file."""
    with (run_dir / f"type_{kind}.lock").open("a+b") as stream:
        if os.name == "nt":
            import msvcrt
            if stream.tell() == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            acquire = lambda: msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            release = lambda: msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            acquire = lambda: fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            release = lambda: fcntl.flock(stream, fcntl.LOCK_UN)
        try:
            acquire()
        except OSError as error:
            raise RuntimeError(f"Another task already owns type {kind} in {run_dir}") from error
        try:
            yield
        finally:
            release()


def run_batch(run_dir, manifest, pilot, district_type=None, retry_failed=False):
    kinds = [district_type] if district_type else list(TYPES)
    if district_type is not None and district_type not in TYPES:
        raise ValueError(f"Unknown district type: {district_type}")
    # Whole-batch and per-type invocations use the same locks.
    with ExitStack() as stack:
        for kind in kinds:
            stack.enter_context(type_lock(run_dir, kind))
        return run_selected_types(run_dir, manifest, pilot, kinds, retry_failed)


def run_selected_types(run_dir, manifest, pilot, kinds, retry_failed=False):
    candidates = sorted(manifest["districts"], key=lambda item: (item["type"], item["seed"]))
    candidates = [item for item in candidates if item["type"] in kinds]
    items = candidates[:1] if pilot else candidates
    successful = {kind: [] for kind in kinds}
    failed = {kind: [] for kind in kinds}
    evaluations = [(variant_dir, variant, case)
                   for variant_dir, variant in evaluation_runs(run_dir, manifest) for case in CASES]
    for item in items:
        kind = item["type"]
        if len(successful[kind]) >= TARGET_PER_TYPE:
            continue
        district_dir = run_dir / item["name"]
        all_complete = all(any((variant_dir / item["name"] / case).glob("attempt_*/completed.json"))
                           for variant_dir, _, case in evaluations)
        if (district_dir / "district_failed.json").exists() and not all_complete and not retry_failed:
            failed[kind].append(item["name"])
            print(f"Previously failed district: {item['name']}; trying next seed.", flush=True)
            continue
        district_failed = False
        if manifest.get("version") == 4:
            district_dir.mkdir(parents=True, exist_ok=True)
        for variant_dir, variant, case in evaluations:
            case_dir = variant_dir / item["name"] / case
            label = f"{variant} / {case}" if variant else case
            if any(case_dir.glob("attempt_*/completed.json")):
                print(f"Already complete: {item['name']} / {label}", flush=True)
                continue
            case_dir.mkdir(parents=True, exist_ok=True)
            number = 1
            while (case_dir / f"attempt_{number:03d}").exists():
                number += 1
            attempt = case_dir / f"attempt_{number:03d}"
            attempt.mkdir()
            log = case_dir / f"attempt_{number:03d}.log"
            print(f"Running {item['name']} / {label}; log: {log}", flush=True)
            with log.open("x", encoding="utf-8") as stream:
                result = subprocess.run(
                    [sys.executable, "-u", str(Path(__file__).resolve()), "--worker",
                     str(variant_dir), item["name"], case, str(attempt)],
                    stdout=stream, stderr=subprocess.STDOUT, cwd=attempt, check=False)
            if result.returncode < 0:
                raise RuntimeError(
                    f"Worker terminated by signal {-result.returncode}; inspect {log} and Slurm "
                    "resource limits before resuming. District is not excluded.")
            if result.returncode != 0 or not (attempt / "completed.json").exists():
                print(f"FAILED: {item['name']} / {label}; see {log}", flush=True)
                failure = {
                    "scenario": item["name"], "case": case, "variant": variant, "returncode": result.returncode,
                    "log": str(log.relative_to(run_dir)),
                    "finished": datetime.now().astimezone().isoformat(),
                }
                prefix = f"{variant}_" if variant else ""
                write_json_new(district_dir / f"district_failure_{prefix}{case}_{attempt.name}.json", failure)
                if not (district_dir / "district_failed.json").exists():
                    write_json_new(district_dir / "district_failed.json", failure)
                failed[kind].append(item["name"])
                district_failed = True
                break
            print(f"Completed {item['name']} / {label}", flush=True)
        if not district_failed:
            successful[kind].append(item["name"])
            print(f"Type {kind}: {len(successful[kind])}/{TARGET_PER_TYPE} successful districts.", flush=True)
    shortfalls = {kind: TARGET_PER_TYPE - len(names) for kind, names in successful.items()
                  if len(names) < TARGET_PER_TYPE}
    report = {"pilot": pilot, "types": kinds, "retry_failed": retry_failed,
              "variants": [variant for _, variant in evaluation_runs(run_dir, manifest)],
              "successful": successful, "failed": failed,
              "shortfalls": shortfalls, "target_per_type": TARGET_PER_TYPE}
    report_path = run_dir / f"batch_summary_{datetime.now():%Y%m%d-%H%M%S}_{uuid4().hex[:6]}.json"
    write_json_new(report_path, report)
    print(f"Summary: {report_path}", flush=True)
    if pilot:
        print("Pilot finished; the full per-type target was not attempted.", flush=True)
        if any(failed.values()):
            raise RuntimeError("Pilot district failed; inspect its logs before submitting the full batch.")
    elif shortfalls:
        raise RuntimeError(f"Candidates exhausted; missing successful districts by type: {shortfalls}")
    else:
        print(f"Target reached: {TARGET_PER_TYPE} successful districts per selected type {kinds}, "
              f"all {len(evaluations)} evaluations per district complete.", flush=True)


def package_results(run_dir, destination=None, dry_run=False):
    """Package selected successful cases, never modify or delete run outputs.

    Legacy TXT solutions are kept unless an equivalent compact export exists.
    Pickles, LP models and failed/interrupted attempts stay on the cluster.
    """
    run_dir = run_dir.resolve()
    manifest = load_manifest(run_dir)
    latest = {}
    for path in sorted(run_dir.glob("batch_summary_*.json"), key=lambda p: (p.stat().st_mtime_ns, p.name)):
        summary = json.loads(path.read_text(encoding="utf-8"))
        if not summary["pilot"]:
            for kind in summary["types"]:
                latest[kind] = (path, summary)
    selected = {}
    files = {run_dir / "manifest.json", run_dir / ".env.CONFIG.BERGFEST"}
    if manifest["version"] == 4:
        for variant in FUNDING_VARIANTS:
            files.update({run_dir / variant / "manifest.json", run_dir / variant / ".env.CONFIG.BERGFEST"})
    for name, checksum in manifest.get("code_provenance", {}).items():
        if name not in {"code_commit.txt", "code_changes.patch"} or digest(run_dir / name) != checksum:
            raise ValueError("Saved code provenance is missing or modified.")
        files.add(run_dir / name)
    known = {item["name"]: item for item in manifest["districts"]}
    for kind in TYPES:
        if kind not in latest:
            raise ValueError(f"No final summary for type {kind}.")
        path, summary = latest[kind]
        names = summary["successful"][kind]
        if (summary["shortfalls"].get(kind, 0) or len(names) != TARGET_PER_TYPE
                or len(set(names)) != TARGET_PER_TYPE):
            raise ValueError(f"Type {kind} has not reached ten successful districts.")
        files.add(path)
        for name in names:
            if name not in known or known[name]["type"] != kind:
                raise ValueError(f"Unknown district in summary: {name}")
            for variant_dir, variant, case in ((directory, variant, case)
                    for directory, variant in evaluation_runs(run_dir, manifest) for case in CASES):
                markers = sorted((variant_dir / name / case).glob("attempt_*/completed.json"))
                if not markers:
                    raise ValueError(f"Missing completed case: {name}/{case}")
                marker = markers[-1]
                completed = json.loads(marker.read_text(encoding="utf-8"))
                if completed["scenario"] != name or completed["case"] != case:
                    raise ValueError(f"Invalid completion marker: {marker}")
                attempt = marker.parent
                selected[f"{variant + '/' if variant else ''}{name}/{case}"] = str(attempt.relative_to(run_dir))
                for entry in attempt.rglob("*"):
                    if entry.is_file():
                        if entry.suffix in {".lp", ".p"}:
                            continue
                        if entry.name.startswith("solution_file_") and entry.suffix == ".txt":
                            model_name = entry.stem[len("solution_file_"):]
                            if (entry.parent / f"variables_{model_name}.csv.gz").is_file():
                                continue
                        files.add(entry)
                log = attempt.with_suffix(".log")
                if log.is_file():
                    files.add(log)
    for path in files:
        if path.is_symlink() or not path.resolve().is_relative_to(run_dir):
            raise ValueError(f"Refusing archive member outside the run: {path}")
    if dry_run:
        print(f"Would package {len(selected)} cases, {len(files)} files, "
              f"{sum(path.stat().st_size for path in files) / 2**30:.2f} GiB before compression.")
        return
    if destination is None:
        destination = run_dir.parent / f"{run_dir.name}_selected_{uuid4().hex[:6]}.tar.gz"
    destination = destination.resolve()
    if destination.is_relative_to(run_dir):
        raise ValueError("The archive must be outside the source run folder.")
    # Exclusive creation prevents overwriting even if another packer starts concurrently.
    with destination.open("xb") as output:
        with tarfile.open(fileobj=output, mode="w:gz", compresslevel=1) as archive:
            for path in sorted(files):
                archive.add(path, arcname=f"{run_dir.name}/{path.relative_to(run_dir).as_posix()}", recursive=False)
            payload = json.dumps({"cases": selected, "excluded": ["LP models", "district pickles",
                                 "failed/interrupted attempts", "TXT with a compact equivalent"]}, indent=2).encode()
            info = tarfile.TarInfo(f"{run_dir.name}/backup_selection.json")
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    checksum = sha256()
    with destination.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(block)
    with Path(str(destination) + ".sha256").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(f"{checksum.hexdigest()}  {destination.name}\n")
    print(f"Selected-result archive created: {destination}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Check all selected input profiles without optimization or output creation.")
    parser.add_argument("--pilot", action="store_true", help="Run the first selected district's three cases (six for paired funding); resume later for the rest.")
    parser.add_argument("--resume", type=Path, help="Continue a saved run using its immutable configuration snapshot.")
    parser.add_argument("--type", choices=list(TYPES), dest="district_type",
                        help="With --resume, process only this settlement type (Slurm array task).")
    parser.add_argument("--retry-failed-districts", action="store_true",
                        help="With --resume, revisit excluded districts after fixing their failure cause; preserve all attempts.")
    parser.add_argument("--worker", nargs=4, metavar=("RUN", "SCENARIO", "CASE", "ATTEMPT"), help=argparse.SUPPRESS)
    parser.add_argument("--package", type=Path, help="Archive final successful results without running optimization; --dry-run previews selection.")
    parser.add_argument("--package-output", type=Path, help="New archive path for --package; existing files are never overwritten.")
    parser.add_argument("--paired-funding", action="store_true", help="Create a matched funding OFF/ON comparison; EB must be disabled.")
    parser.add_argument("--prepare-only", action="store_true", help="Create immutable run snapshots and exit without optimization (safe on login nodes).")
    args = parser.parse_args()
    if args.package:
        if (args.resume or args.pilot or args.worker or args.district_type or args.retry_failed_districts
                or args.paired_funding or args.prepare_only):
            parser.error("--package cannot be combined with optimization options.")
        if args.dry_run:
            package_results(args.package, args.package_output, dry_run=True)
            return
        with ExitStack() as stack:
            for kind in TYPES:
                stack.enter_context(type_lock(args.package.resolve(), kind))
            package_results(args.package, args.package_output, args.dry_run)
        return
    if args.package_output:
        parser.error("--package-output requires --package.")
    if args.district_type and (not args.resume or args.worker):
        parser.error("--type requires --resume and cannot be combined with --worker.")
    if args.paired_funding and (args.resume or args.worker):
        parser.error("--paired-funding creates a new comparison; resume its parent folder without this flag.")
    if args.prepare_only and (args.resume or args.worker or args.pilot or args.dry_run):
        parser.error("--prepare-only creates a new run and cannot be combined with resume, worker, pilot or dry-run.")
    if args.retry_failed_districts and (not args.resume or args.worker):
        parser.error("--retry-failed-districts requires --resume and cannot be combined with --worker.")
    if args.worker:
        run, scenario, case, attempt = args.worker
        worker(Path(run).resolve(), scenario, case, Path(attempt))
        return
    if args.resume:
        run_dir = args.resume.resolve()
        manifest = load_manifest(run_dir)
        if manifest.get("comparison_parent"):
            parser.error("Resume the comparison parent folder, not an individual funding variant.")
        config_path = run_dir / ".env.CONFIG.BERGFEST"
        items = manifest["districts"]
    else:
        items = select_districts()
        config_path = CONFIG
    paired = args.paired_funding or (args.resume and manifest["version"] == 4)
    if paired and validate_config(config_path).central.EB["feasible"]:
        parser.error("Set C_EB__FEASIBLE=False before preparing the comparison.")
    selected = [item for item in items if item["type"] == args.district_type] if args.district_type else items
    selected = selected[:1] if args.pilot else selected
    if not selected:
        parser.error("The saved manifest contains no candidates for the selected type.")
    for district_type in TYPES:
        seeds = [item["seed"] for item in selected if item["type"] == district_type]
        if seeds:
            print(f"Type {district_type}: seeds {seeds}")
    per_district = 6 if paired else 3
    print(f"Available: {len(selected)} candidates, up to {len(selected) * per_district} case evaluations. "
          f"Target: {TARGET_PER_TYPE} successful districts per type (all {per_district} evaluations).", flush=True)
    preflight(selected, config_path)
    if args.dry_run:
        return
    if not args.resume:
        RUNS_ROOT.mkdir(parents=True, exist_ok=True)
        prefix = "COMPARISON" if paired else "BERGFEST"
        run_dir = RUNS_ROOT / f"{prefix}_{datetime.now():%Y%m%d-%H%M%S}_{uuid4().hex[:6]}"
        run_dir.mkdir()
        shutil.copyfile(CONFIG, run_dir / ".env.CONFIG.BERGFEST")
        config = validate_config(run_dir / ".env.CONFIG.BERGFEST")
        policy = {key: getattr(config.pyomo, key) for key in
                  ("solver_export_lp", "solver_export_txt", "solver_export_compact")}
        policy["batch_save_district_pickle"] = config.report.batch_save_district_pickle
        manifest = {"version": 3, "districts": items, "cases": list(CASES), "output_policy": policy,
                    "code_provenance": save_code_provenance(run_dir),
                    "config_sha256": digest(run_dir / ".env.CONFIG.BERGFEST"),
                    "created": datetime.now().astimezone().isoformat()}
        output_policy(manifest)
        if paired:
            create_comparison_variants(run_dir, manifest)
        write_json_new(run_dir / "manifest.json", manifest)
    print(f"All outputs will be stored under: {run_dir}", flush=True)
    if args.prepare_only:
        print("Prepared only; no optimization executed. Submit the saved folder to Slurm.", flush=True)
        return
    run_batch(run_dir, manifest, args.pilot, district_type=args.district_type,
              retry_failed=args.retry_failed_districts)


if __name__ == "__main__":
    main()
