# -*- coding: utf-8 -*-
"""
Regression tests for the results of the examples e5, e7, e8 and e9.

Every example runs with a fixed random seed and the scenario files in tests/results_data/scenarios.
Demand profiles and selected KPI values are compared with the reference results in
tests/results_data/reference. Residual load is checked against the calculated power flows.

If a demand-profile reference file is missing, it is written from the current results and the test is skipped.
After an intended change of the demand profiles, set the environment variable UPDATE_REFERENCE_RESULTS=1
to replace the demand-profile reference files, and check the changes with git diff before committing them.
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
}

# Demand profiles of each building that are compared as time series
PROFILES = ("heat", "cooling", "elec", "dhw", "occ", "gains", "EV_carcharging_ondemand")

# Relative tolerance for deterministic demand results
RTOL_PROFILES = 1e-9
REFERENCE_MIP_GAP = 0.01  # Solver gap used by the reference configuration.
DEMAND_KPIS = ("total_heating_demand", "total_cooling_demand", "total_electricity_demand",
    "total_dhw_demand", "total_EV_demand")

UPDATE = os.environ.get("UPDATE_REFERENCE_RESULTS") == "1"


def run_example(module_name, function_name, result_path):
    """Run an example with the test scenarios and write all outputs to result_path."""
    module = import_module(f"examples.{module_name}")
    datahandler = module.Datahandler

    def test_datahandler(*args, **kwargs):
        kwargs.update(resultPath=str(result_path), scenario_file_path=str(SCENARIOS))
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


class TestResults(unittest.TestCase):
    """Check reproducible demands and optimized operation for the examples."""

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

    def check_operation(self, prefix, data):
        """Check quantities that remain meaningful for different optimal dispatches."""
        expected = pd.read_csv(REFERENCE / f"{prefix}_kpis.csv", index_col=0).iloc[:, 0]
        demand = [getattr(data.KPIs, name) for name in DEMAND_KPIS]
        np.testing.assert_allclose(demand, expected.loc[list(DEMAND_KPIS)],
                                   rtol=RTOL_PROFILES, atol=1e-9, err_msg=f"{prefix} demand KPIs")
        years = data.ecoData["interpolation_points"]
        steps = data.time["clusterLength"] // data.time["timeResolution"]
        self.assertLessEqual(data.pyomo_config["solver_options"]["mip_gap"], REFERENCE_MIP_GAP)
        self.assertEqual(set(data.resultsOptimization), set(years))
        self.assertEqual(len(data.clusters), data.time["clusterNumber"])
        self.assertEqual(sum(data.clusterWeights[c] for c in data.clusters), len(data.site["T_e"]) // steps)
        for year in years:
            results = data.resultsOptimization[year]
            self.assertEqual(set(results), set(range(len(data.clusters))))
            loads, annual_cost = [], 0.0
            for index, cluster in enumerate(data.clusters):
                result = results[index]
                flows = np.stack([
                    result["P_dem_gcp"], result["P_inj_gcp"], result["P_dem_total"],
                    result["P_inj_total"], result["energy_hub"]["res_load"],
                    result["energy_hub"]["res_inj"],
                ])
                self.assertEqual(flows.shape, (6, steps))
                self.assertTrue(np.isfinite(flows).all())
                imports, exports, building_load, building_feed, hub_load, hub_feed = flows
                net_grid = imports - exports
                # Each of the six exported flows is rounded to the nearest watt.
                np.testing.assert_allclose(net_grid, building_load - building_feed + hub_load - hub_feed,
                                           rtol=0, atol=3, err_msg=f"{prefix}, year {year}, cluster {cluster}")
                loads.append(net_grid / 1000)
                annual_cost += result["Cost_total"] * data.clusterWeights[cluster]
            np.testing.assert_array_equal(data.KPIs.residualLoad[year], loads)
            self.assertEqual(data.KPIs.operationCosts[year], round(annual_cost))
            reference_cost = expected[f"operationCosts[{year}]"]
            # The saved annual KPI is rounded to euros. Both runs use a MIP gap for operating costs.
            allowed_difference = REFERENCE_MIP_GAP * max(abs(reference_cost), abs(annual_cost)) + 0.5
            self.assertLessEqual(abs(annual_cost - reference_cost), allowed_difference,
                                 f"{prefix} year {year} operating costs: {annual_cost:.2f} vs {reference_cost:.2f} EUR")

    def check_example(self, prefix, data, with_kpis=True):
        """Compare the demand profiles and, if calculated, the KPIs of an example."""
        self.assertEqual(data.random_seed, 42)
        with self.subTest(results="profiles"):
            self.assert_reference(f"{prefix}_profiles", demand_profiles(data), RTOL_PROFILES)
        if with_kpis:
            self.check_operation(prefix, data)

    def test_e5_generate_demands(self):
        """Example 5 always generates the same demand profiles."""
        with tempfile.TemporaryDirectory() as result_path:
            data = run_example("e5_generate_demands", "example5_generate_demands", result_path)
        self.check_example("e5", data, with_kpis=False)

    def test_e7_decentral_scenario_evaluation(self):
        """Check demand profiles and optimized operation for Example 7."""
        with tempfile.TemporaryDirectory() as result_path:
            data = run_example("e7_decentral_scenario_evaluation", "example7_decentral_scenario_evaluation",
                               result_path)
        self.check_example("e7", data)

    def test_e8_central_scenario_evaluation(self):
        """Check demand profiles and optimized operation for Example 8."""
        with tempfile.TemporaryDirectory() as result_path:
            data = run_example("e8_central_scenario_evaluation", "example8_central_scenario_evaluation",
                               result_path)
        self.check_example("e8", data)

    def test_e9_non_residential_scenario_evaluation(self):
        """Check demand profiles and optimized operation for Example 9."""
        with tempfile.TemporaryDirectory() as result_path:
            data = run_example("e9_non_residential_scenario_evaluation",
                               "example9_non_residential_scenario_evaluation", result_path)
        self.check_example("e9", data)


if __name__ == '__main__':
    unittest.main()
