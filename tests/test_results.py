# -*- coding: utf-8 -*-
"""
Regression tests for the results of the examples e5, e7, e8 and e9.

Every example runs with a fixed random seed and the scenario files in tests/results_data/scenarios.
Selected time series (demand profiles, residual load) and single KPI values are compared with the
reference results in tests/results_data/reference.

If a reference file is missing, it is written from the current results and the test is skipped.
After an intended change of the results, set the environment variable UPDATE_REFERENCE_RESULTS=1
to replace the reference files, and check the changes with git diff before committing them.
"""
import os
import tempfile
import unittest
from importlib import import_module
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

TEST_DATA = Path(__file__).parent / "results_data"
SCENARIOS = TEST_DATA / "scenarios"
REFERENCE = TEST_DATA / "reference"

# Settings that override .env.CONFIG.EXAMPLE, so that every run produces the same results
OVERRIDES = {
    "RANDOM_SEED": "42",
    "SOLVER_OPTIONS__THREADS": "1",
    "SOLVER_NAME": "highs",
}

# Demand profiles of each building that are compared as time series
PROFILES = ("heat", "cooling", "elec", "dhw", "occ", "gains", "EV_carcharging_ondemand")

# Relative tolerances: generated profiles must be equal, optimization results may differ within the MIP gap
RTOL_PROFILES = 1e-9
RTOL_OPTIMIZATION = 1e-6

UPDATE = os.environ.get("UPDATE_REFERENCE_RESULTS") == "1"


def run_example(module_name, function_name, result_path):
    """Run an example with the test scenarios and write all outputs to result_path."""
    module = import_module(f"examples.{module_name}")
    datahandler = module.Datahandler

    def test_datahandler(*args, **kwargs):
        kwargs.update(resultPath=str(result_path), scenario_file_path=str(SCENARIOS),
                      env_path=str(TEST_DATA / ".env.CONFIG.TEST"))
        return datahandler(*args, **kwargs)

    with patch.object(module, "Datahandler", side_effect=test_datahandler), patch.dict(os.environ, OVERRIDES):
        return getattr(module, function_name)()


def demand_profiles(data):
    """Time series of the demand profiles of all buildings, one column per building and profile."""
    columns = {}
    for building in data.district:
        building_id = building["buildingFeatures"]["id"]
        for name in PROFILES:
            profile = getattr(building["user"], name, None)
            if profile is not None:
                columns[f"{building_id}_{name}"] = pd.Series(np.ravel(profile), dtype=float)
    return pd.DataFrame(columns)  # Shorter profiles are filled with NaN


def collect_values(name, value, values):
    """Add a numeric value, or all numeric values of a (nested) dict, e.g. 'peakDemand[0]' for year 0."""
    if isinstance(value, dict):
        for key, item in value.items():
            collect_values(f"{name}[{key}]", item, values)
    elif isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(value, bool):
        values[name] = float(value)


def kpi_values(kpis):
    """All single numeric KPI values of the KPIs object, including the values per simulated year."""
    values = {}
    for name, value in vars(kpis).items():
        if name != "inputData":
            collect_values(name, value, values)
    return pd.Series(values, name="value").sort_index()


def residual_load(kpis):
    """Time series of the residual load of the district, one column per simulated year."""
    return pd.DataFrame({f"residualLoad[{year}]": np.ravel(load) for year, load in kpis.residualLoad.items()})


class TestResults(unittest.TestCase):
    """Checks that the examples always produce the same results."""

    def assert_reference(self, name, actual, rtol):
        """Compare a DataFrame or Series with its reference CSV file, or write the reference if missing."""
        path = REFERENCE / f"{name}.csv"
        if UPDATE or not path.exists():
            REFERENCE.mkdir(parents=True, exist_ok=True)
            actual.to_csv(path, float_format="%.15g")
            self.skipTest(f"Reference results written to {path}")
        expected = pd.read_csv(path, index_col=0)
        if isinstance(actual, pd.Series):
            expected = expected.iloc[:, 0]
            self.assertEqual(sorted(actual.index), sorted(expected.index), f"Different KPIs in {name}")
            actual, expected = actual.sort_index(), expected.sort_index()
        else:
            self.assertEqual(list(actual.columns), list(expected.columns), f"Different columns in {name}")
            self.assertEqual(len(actual), len(expected), f"Different number of time steps in {name}")
        np.testing.assert_allclose(actual.to_numpy(dtype=float), expected.to_numpy(dtype=float),
                                   rtol=rtol, atol=1e-9, err_msg=f"Results of {name} changed")

    def check_example(self, prefix, data, with_kpis=True):
        """Compare the demand profiles and, if calculated, the KPIs of an example."""
        self.assertEqual(data.random_seed, 42)
        with self.subTest(results="profiles"):
            self.assert_reference(f"{prefix}_profiles", demand_profiles(data), RTOL_PROFILES)
        if with_kpis:
            with self.subTest(results="residual load"):
                self.assert_reference(f"{prefix}_residual_load", residual_load(data.KPIs), RTOL_OPTIMIZATION)
            with self.subTest(results="kpis"):
                self.assert_reference(f"{prefix}_kpis", kpi_values(data.KPIs), RTOL_OPTIMIZATION)

    def test_e5_generate_demands(self):
        """Example 5 always generates the same demand profiles."""
        with tempfile.TemporaryDirectory() as result_path:
            data = run_example("e5_generate_demands", "example5_generate_demands", result_path)
        self.check_example("e5", data, with_kpis=False)

    def test_e7_decentral_scenario_evaluation(self):
        """Example 7 always produces the same profiles and KPIs."""
        with tempfile.TemporaryDirectory() as result_path:
            data = run_example("e7_decentral_scenario_evaluation", "example7_decentral_scenario_evaluation",
                               result_path)
        self.check_example("e7", data)

    def test_e8_central_scenario_evaluation(self):
        """Example 8 always produces the same profiles and KPIs."""
        with tempfile.TemporaryDirectory() as result_path:
            data = run_example("e8_central_scenario_evaluation", "example8_central_scenario_evaluation",
                               result_path)
        self.check_example("e8", data)

    def test_e9_non_residential_scenario_evaluation(self):
        """Example 9 always produces the same profiles and KPIs."""
        with tempfile.TemporaryDirectory() as result_path:
            data = run_example("e9_non_residential_scenario_evaluation",
                               "example9_non_residential_scenario_evaluation", result_path)
        self.check_example("e9", data)


if __name__ == '__main__':
    unittest.main()
