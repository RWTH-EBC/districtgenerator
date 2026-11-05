# -*- coding: utf-8 -*-
"""
Smoke test of the heating concept selection (optimization/heating_concept.py).

The selection is run once for a small building with two candidates and solved with HiGHS. The device
and price parameters come from the example configuration, the profiles from the mock data of
test_operation_devices.py. Only the sizing (designECS) is replaced by fixed capacities. The test checks
that the selection runs through and selects the cheapest candidate, not the exact cost values.
"""
import json
import tempfile
import types
import unittest
from pathlib import Path

import numpy as np
import pyomo.environ as pyo

from districtgenerator.config.settings import load_global_config
from districtgenerator.economics import price_paths
from districtgenerator.optimization.heating_concept import choose_heating_concept
from test_operation_devices import make_mock_data

CANDIDATES = ["HP", "BOI"]


def make_selection_data(result_path, enable_low_temp_measures, undersized=()):
    """
    Mock data of one building with the device and price parameters of the example configuration.

    The heaters in undersized get only 100 W, so the demand cannot be covered and the candidate is infeasible.
    """
    config = load_global_config()
    data = make_mock_data()
    data.district = data.district[:1]
    data.decentral_device_data = {dev: dict(params) for dev, params in config.decentral.__dict__.items()}
    data.decentral_device_data["HP"]["enable_low_temp_measures"] = enable_low_temp_measures
    data.physics = dict(config.physics.__dict__)
    data.ecoData = dict(config.eco.__dict__)
    data.all_sim_ecoData = price_paths.calculate_eco_data_per_simulated_year(data.ecoData)
    data.pyomo_config = {"solver_name": "highs", "solver_executable": None, "solver_options": {}}
    data.resultPath = result_path
    data.time["clusterNumber"] = 1
    data.clusters = [0]
    data.clusterWeights = {0: 365}

    building = data.district[0]
    building["buildingFeatures"]["id"] = 0
    building["envelope"].heatload = 8000  # W
    curve = building["envelope"].heating_curve["clustered"]
    curve["low_temp_measures_binding"] = True
    curve["Ts_curve_reduced"] = curve["Ts_curve"] - 10

    def design_ecs(candidate, site):
        """Fixed capacities instead of the sizing rules: only the candidate heater, a TES and a chiller."""
        capacities = {dev: 0 for dev in ("BOI", "BBOI", "H2BOI", "OBOI", "HP", "EH", "EH_DHW", "CC", "CHP", "FC",
                                         "DH", "EV", "BAT", "TES", "TES_DHW", "heat_grid")}
        capacities.update({"PV": {"area": 0}, "STC": {"area": 0}, "TES": 5000, "TES_DHW": 2000, "CC": 5000})
        heater = candidate["buildingFeatures"]["heater"]
        capacities[heater] = 100 if heater in undersized else 20000  # W
        return capacities

    building["bes_obj"] = types.SimpleNamespace(designECS=design_ecs)
    return data, building


@unittest.skipUnless(pyo.SolverFactory("highs").available(exception_flag=False), "HiGHS (highspy) is not installed")
class TestChooseHeatingConcept(unittest.TestCase):
    """Smoke test of choose_heating_concept with HiGHS."""

    def _run(self, enable_low_temp_measures, candidates=CANDIDATES, undersized=()):
        with tempfile.TemporaryDirectory() as result_path:
            data, building = make_selection_data(result_path, enable_low_temp_measures, undersized)
            choose_heating_concept(data, building, candidates)
            comparison_file = Path(result_path) / "heating_selection" / "building_0" / "comparison.json"
            with comparison_file.open(encoding="utf-8") as file:
                comparison = json.load(file)
        return building, comparison

    def test_selects_cheapest_candidate(self):
        """Both candidates are feasible, the one with the lowest total annual cost is selected and applied."""
        building, comparison = self._run(enable_low_temp_measures=False)
        candidates = comparison["candidates"]
        for concept in CANDIDATES:
            with self.subTest(concept=concept):
                self.assertEqual(candidates[concept]["status"], "optimal")
                self.assertGreater(candidates[concept]["total_annual_cost_eur"], 0)
        cheapest = min(CANDIDATES, key=lambda concept: candidates[concept]["total_annual_cost_eur"])
        self.assertEqual(comparison["selected_heater"], cheapest)
        self.assertEqual(building["buildingFeatures"]["heater"], cheapest)
        self.assertEqual(building["capacities"][cheapest], 20000)
        self.assertEqual(building["heating_selection"]["selected_heater"], cheapest)
        # Without low temperature measures, the heat pump has no costs for them
        self.assertNotIn("T_reduction_measures", candidates["HP"]["device_costs"])

    def test_low_temp_measures_costs(self):
        """With low temperature measures, their investment is part of the fixed costs of the heat pump only."""
        _, comparison = self._run(enable_low_temp_measures=True)
        candidates = comparison["candidates"]
        self.assertIn("T_reduction_measures", candidates["HP"]["device_costs"])
        self.assertGreater(candidates["HP"]["device_costs"]["T_reduction_measures"]["subsidized_annual_cost"], 0)
        self.assertNotIn("T_reduction_measures", candidates["BOI"]["device_costs"])

    def test_infeasible_candidate_is_discarded(self):
        """An infeasible candidate is marked as infeasible and does not stop the selection."""
        building, comparison = self._run(enable_low_temp_measures=False, candidates=["EH", "BOI"], undersized=("EH",))
        self.assertEqual(comparison["candidates"]["EH"]["status"], "infeasible")
        self.assertEqual(comparison["selected_heater"], "BOI")
        self.assertEqual(building["buildingFeatures"]["heater"], "BOI")

    def test_no_feasible_candidate(self):
        """If no candidate is feasible, a ValueError is raised."""
        with self.assertRaises(ValueError):
            self._run(enable_low_temp_measures=False, candidates=["EH"], undersized=("EH",))


if __name__ == '__main__':
    unittest.main()
