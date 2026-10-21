"""
Run examples 1-10 with a fixed random seed and compare their results
with the saved reference results.

For normal testing, simply run this file. No extra settings are needed,
and the saved reference results will not be changed.

Only after an intentional change: set the environment variable
UPDATE_EXAMPLE_BASELINES=1 to replace the saved reference results.
Remove this variable afterwards to return to normal testing.
"""

import json
from importlib import import_module
import os
from pathlib import Path
import sys

from unittest.mock import patch

from dotenv import dotenv_values
import numpy as np
import pandas as pd
import pytest


TEST_DATA = Path(__file__).parent / "test_examples"  # Inputs and saved results for the tests
SCENARIOS = TEST_DATA / "scenarios"  # The fixed test district CSVs
TEST_CONFIG = TEST_DATA / "config" / "example.env"  # Fixed EXAMPLE settings for all ten tests

EXAMPLES = {
    1: ("e1_initialize_datahandler", "example1_initialize_datahandler"),
    2: ("e2_generate_environment", "example2_generate_environment"),
    3: ("e3_initialize_buildings", "example3_initialize_buildings"),
    4: ("e4_generate_buildings", "example4_generate_buildings"),
    5: ("e5_generate_demands", "example5_generate_demands"),
    6: ("e6_individual_district", "example6_config_file_loading"),
    7: ("e7_decentral_scenario_evaluation", "example7_decentral_scenario_evaluation"),
    8: ("e8_central_scenario_evaluation", "example8_central_scenario_evaluation"),
    9: ("e9_non_residential_scenario_evaluation", "example9_non_residential_scenario_evaluation"),
    10: ("e10_exec_multiple_scenarios", "example9_multiple_configs"),
}

OVERRIDES = {
    "RANDOM_SEED": "42",  # Use the same random seed whenever profiles are generated
    "PARALLELIZATION": "multiprocessing",
    "TIMERESOLUTION": "3600",
    "CLUSTERLENGTH": "604800",
    "CLUSTERNUMBER": "2",
    "NUM_INTERPOLATION_POINTS": "1",
    "SOLVER_NAME": "gurobi",
    "SOLVER_OPTIONS__THREADS": "1",
    "SOLVER_OPTIONS__MIP_GAP": "0.001",
    "SOLVER_OPTIONS__TIME_LIMIT": "300",
}


def write_config(path, **changes):
    """
    Create a temporary copy of the test configuration with the settings
    needed for this run. The original configuration is not changed.
    """
    values = dict(dotenv_values(TEST_CONFIG, interpolate=False))
    values.update(OVERRIDES)  # Apply the settings shared by all tests, such as the seed and solver
    values.update(changes)
    path.parent.mkdir(parents=True, exist_ok=True)  # Create the output folder if it does not exist
    path.write_text("\n".join(f"{key}={value}" for key, value in values.items() if value is not None) + "\n", encoding="utf-8")
    return values


def run_example(number, output):
    """
    Run the selected example with fixed test inputs and a separate output folder.

    Temporarily redirect Datahandler to the test configuration and district CSVs
    without changing the example script or replacing its calculations.
    Check that the expected outputs exist and return the calculated data.
    """
    output.mkdir(parents=True, exist_ok=True)
    (output / "results").mkdir(exist_ok=True)
    module_name, function_name = EXAMPLES[number]
    module = import_module(f"examples.{module_name}")
    function = getattr(module, function_name)
    real_datahandler = module.Datahandler
    config = output / ".env.REGRESSION"
    values = write_config(config)
    config_results = {}

    def configured_datahandler(*args, **kwargs):
        # Redirect inputs/outputs only; the example still uses the real model.
        selected_config = Path(kwargs["env_path"]) if number == 10 else config
        result_path = output / "results"
        if number == 10:
            result_path = result_path / selected_config.name
        # Datahandler may write calculation progress during initialization.
        result_path.mkdir(parents=True, exist_ok=True)
        kwargs.update(
            env_path=str(selected_config),
            resultPath=str(result_path),
            scenario_file_path=str(SCENARIOS),
        )
        data = real_datahandler(*args, **kwargs)
        config_results[selected_config.name] = data
        return data

    # Scope environment overrides so a user's shell cannot override the test inputs.
    with patch.object(module, "Datahandler", side_effect=configured_datahandler), patch.dict(
        os.environ, {key: value for key, value in values.items() if value is not None}
    ):
        if number == 10:
            configs = output / "configs"
            write_config(configs / ".env.A")
            write_config(configs / ".env.B", T_SET_MIN="19.0")
            # Each config is independently loaded from disk, not the enclosing environment.
            with patch.dict(os.environ):
                for key in values:
                    os.environ.pop(key, None)
                result = function(configs_dir=configs)
            assert len(result) == 2
            # Compare configurations by name, independent of filesystem ordering.
            return [config_results[name] for name in sorted(config_results)]
        data = function()
    assert data.random_seed == 42
    assert data.district or number <= 2
    if number == 8:
        assert len(data.district) == 3
        assert set(data.scenario["building"]) == {"SFH", "MFH", "OB"}
    if number >= 5:
        for name in ("heat", "elec"):
            assert sum(float(np.sum(getattr(b["user"], name))) for b in data.district) > 0, f"Empty {name} demands"
    if number in (7, 8, 9):
        assert data.resultsOptimization and data.KPIs is not None
        assert list((output / "results").rglob("*.pdf")), "The example did not produce a certificate."
    return data


def _numeric(value):
    """Convert pandas and NumPy values to Python types that can be saved as JSON."""
    if isinstance(value, pd.Series):
        return _numeric(value.to_dict())
    if isinstance(value, dict):
        return {str(k): _numeric(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return np.asarray(value).tolist()
    if isinstance(value, np.generic):
        return _numeric(value.item())
    return value


def profile_arrays(result, prefix=""):
    """
    Collect the weather and building profiles produced by an example for the NPZ file
    """
    if isinstance(result, list):
        profiles = {}
        for index, data in enumerate(result):
            # Prefix each configuration's profile names so they do not overwrite each other
            profiles.update(profile_arrays(data, f"{prefix}{index}/"))
        return profiles
    profiles = {}
    for name in ("T_e", "SunTotal"):
        if name in result.site:
            profiles[f"{prefix}environment/{name}"] = np.asarray(result.site[name], dtype=float)
    for building in result.district:
        user = building.get("user")
        if user is None:
            continue
        for name in ("heat", "dhw", "elec", "cooling"):
            values = getattr(user, name, None)
            if values is not None:
                # Include the building ID so every building is compared separately
                profiles[f"{prefix}building-{building['buildingFeatures']['id']}/{name}"] = np.asarray(values, dtype=float)
    for name, values in profiles.items():
        # Fail on NaN or infinity
        assert np.isfinite(values).all(), f"Non-finite profile: {name}"
    return profiles


def compare_profiles(actual, expected):
    """
    Compare each calculated profile with its saved reference at every timestep

    Fail if a profile is missing, has a different shape or contains values that
    differ beyond the small numerical tolerances below
    """
    assert set(actual) == set(expected), "Changed profile names"
    for name in expected:
        assert actual[name].shape == expected[name].shape, f"Changed profile shape: {name}"
        np.testing.assert_allclose(actual[name], expected[name], rtol=1e-7, atol=1e-5, err_msg=name)


def snapshot(result):
    """
    Collect an example's settings and main results for the JSON reference file.

    Include the building inputs, demand summaries and any clustering or
    optimization results the example has produced. The full profiles are saved
    separately in NPZ files. This function collects results; comparison happens
    later in compare_metrics.
    """
    if isinstance(result, list):
        # Example 10 returns one data object per configuration.
        return {str(index): snapshot(data) for index, data in enumerate(result)}
    data = result
    metrics = {
        "settings": {"seed": data.random_seed, "scenario": data.scenario_name,
                     "timestep_s": data.time["timeResolution"], "solver": data.pyomo_config["solver_name"],
                     "mip_gap": data.pyomo_config["solver_options"]["mip_gap"],
                     "support_years": data.ecoData["interpolation_points"]},
        "scenario": json.loads(data.scenario.to_json(orient="records")),  # Save the input table as one record per row
        "buildings": {},
    }
    for name in ("T_e", "SunTotal"):
        if name in data.site:
            # Summarize the weather here; the NPZ file stores every timestep
            values = np.asarray(data.site[name], dtype=float).reshape(-1)
            metrics[f"environment/{name}"] = {"size": len(values), "mean": float(values.mean()),
                                               "min": float(values.min()), "max": float(values.max())}
    for building in data.district:
        # Use the building ID to keep each building's results separate
        key = str(building["buildingFeatures"]["id"])
        item = {"features": _numeric(building["buildingFeatures"])}
        envelope = building.get("envelope")
        if envelope is not None:
            # Early examples have not created the thermal building model yet
            item["heatload_W"] = float(envelope.heatload)
        user = building.get("user")
        if user is not None:
            item["occupants"] = _numeric(user.nb_occ)
            for name in ("heat", "dhw", "elec", "cooling"):
                profile = getattr(user, name, None)
                if profile is None:
                    # Demand profiles do not exist yet in the earlier examples
                    continue
                values = np.asarray(profile, dtype=float).reshape(-1)
                if values.size:
                    # Reject invalid demands, allowing only tiny negative rounding errors
                    assert np.isfinite(values).all(), f"Non-finite {name} profile"
                    assert np.min(values) >= -1e-6, f"Negative {name} demand"
                    dt_h = data.time["timeResolution"] / 3600
                    steps_per_day = int(24 / dt_h)
                    # Convert power in W to energy in kWh using the timestep length
                    item[name] = {"size": len(values), "annual_kWh": float(values.sum() * dt_h / 1000),
                                  "peak_W": float(values.max()),
                                  "daily_kWh": (values.reshape(-1, steps_per_day).sum(axis=1) * dt_h / 1000).tolist()}
        metrics["buildings"][key] = item
    if hasattr(data, "clusters"):
        # Check both the selected representative periods and how often they occur
        metrics["clusters"] = _numeric(data.clusters)
        metrics["cluster_weights"] = _numeric(data.clusterWeights)
    if data.KPIs is not None:
        # Only the examples that calculate KPIs have these optimization summaries
        kpis = data.KPIs
        metrics["optimization"] = {
            name: _numeric(getattr(kpis, name)) for name in (
                "operationCosts", "annual_fixed_costs_decentral", "annual_fixed_costs_central",
                "co2emissions", "W_dem_GCP_year", "W_inj_GCP_year", "gas_year",
            )
        }
        metrics["optimization"]["central_capacities"] = {
            key: value["cap"] for key, value in data.centralDevices.get("capacities", {}).items()
            # Grid entries are connection limits (possibly unlimited), not installed devices.
            if key not in ("from_grid", "to_grid") and isinstance(value, dict) and "cap" in value
        }
        metrics["optimization"]["building_capacities"] = {
            str(b["buildingFeatures"]["id"]): _numeric(b["capacities"]) for b in data.district
        }
    # Fail if the summary cannot be saved as JSON or contains NaN/infinity
    json.dumps(metrics, allow_nan=False)
    return metrics


def compare_metrics(actual, expected, path=""):
    """
    Compare the calculated summary with the saved JSON reference.

    Check every field, including values inside dictionaries and lists. Allow
    small numerical differences.
    """
    if isinstance(expected, dict):
        assert isinstance(actual, dict) and actual.keys() == expected.keys(), f"Changed fields at {path}"
        for key, value in expected.items():
            compare_metrics(actual[key], value, f"{path}/{key}")
    elif isinstance(expected, list):
        # Lists must have the same length and match in the same order
        assert isinstance(actual, list) and len(actual) == len(expected), f"Changed shape at {path}"
        for index, value in enumerate(expected):
            compare_metrics(actual[index], value, f"{path}/{index}")
    elif isinstance(expected, (float, int)) and not isinstance(expected, bool):
        # Treat True/False as exact settings, not numbers with a tolerance
        optimized = "/optimization/" in path
        absolute_tolerance = 1e-5
        if optimized:
            # Solver results allow 0.5% relative difference plus a small absolute allowance
            absolute_tolerance = 1.0 if "cost" in path.lower() else 0.001
            # Cost values allow 1 EUR; other values allow 0.001 in their saved units
            if "/central_capacities/" in path:
                absolute_tolerance = 0.11  # The design exporter rounds capacities to 0.1
        # NumPy checks: |actual - expected| <= atol + rtol * |expected|
        np.testing.assert_allclose(actual, expected, rtol=0.005 if optimized else 1e-7,
                                   atol=absolute_tolerance, err_msg=path)
    else:
        # Text, booleans and None must match exactly
        assert actual == expected, f"Changed value at {path}: {actual!r} != {expected!r}"


BASELINES = TEST_DATA / "reference_results"


@pytest.fixture(scope="module")
def example_results(tmp_path_factory):
    return tmp_path_factory.mktemp("example-regression")


@pytest.mark.parametrize("number", EXAMPLES, ids=lambda number: f"example-{number:02d}")
def test_example_regression(number, example_results):
    output = example_results / f"example-{number:02d}"
    data = run_example(number, output)
    actual = snapshot(data)
    profiles = profile_arrays(data)
    output.mkdir(parents=True, exist_ok=True)
    (output / "actual.json").write_text(json.dumps(actual, indent=2, allow_nan=False), encoding="utf-8")
    np.savez_compressed(output / "actual.npz", **profiles)
    baseline = BASELINES / f"example-{number:02d}.json"

    if os.environ.get("UPDATE_EXAMPLE_BASELINES") == "1":
        BASELINES.mkdir(parents=True, exist_ok=True)
        baseline.write_text(json.dumps(actual, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        np.savez_compressed(baseline.with_suffix(".npz"), **profiles)
    else:
        assert baseline.is_file(), f"Missing reference {baseline}. Generate and review the reference results first."
        compare_metrics(actual, json.loads(baseline.read_text(encoding="utf-8")))
        with np.load(baseline.with_suffix(".npz"), allow_pickle=False) as expected:
            compare_profiles(profiles, dict(expected))


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    raise SystemExit(pytest.main([__file__, "-q", *sys.argv[1:]]))
