# -*- coding: utf-8 -*-
"""
Unit tests for single functions of the districtgenerator.

The expected values are calculated by hand, so the tests do not depend on data files or other modules.
"""
import unittest
from copy import deepcopy
from types import SimpleNamespace

import numpy as np

from districtgenerator.time_series.resolution import changeResolution
from districtgenerator.economics.price_paths import calculate_eco_data_per_simulated_year
from districtgenerator.energy_systems.building_energy_system import BES


class TestChangeResolution(unittest.TestCase):
    """Unit tests for changeResolution of the time_series package."""

    def test_mean_downsampling(self):
        """Quarter-hourly values are averaged to hourly values."""
        values = np.array([1, 2, 3, 4, 5, 6, 7, 8], dtype=float)
        result = changeResolution(values, 900, 3600, "mean")
        np.testing.assert_allclose(result, [2.5, 6.5])

    def test_sum_downsampling_keeps_energy(self):
        """Quarter-hourly values are summed to hourly values and the total stays the same."""
        values = np.array([1, 2, 3, 4, 5, 6, 7, 8], dtype=float)
        result = changeResolution(values, 900, 3600, "sum")
        np.testing.assert_allclose(result, [10, 26])
        self.assertAlmostEqual(result.sum(), values.sum())

    def test_mean_upsampling_interpolates(self):
        """Hourly values are linearly interpolated to half-hourly values, the last value is held."""
        values = np.array([0, 2], dtype=float)
        result = changeResolution(values, 3600, 1800, "mean")
        np.testing.assert_allclose(result, [0, 1, 2, 2])

    def test_mean_incomplete_last_step(self):
        """If the last new time step is not completely covered, the last old value is repeated."""
        values = np.array([1, 2, 3], dtype=float)
        result = changeResolution(values, 900, 1800, "mean")
        np.testing.assert_allclose(result, [1.5, 3])

    def test_same_resolution(self):
        """The values do not change if the old and new resolution are the same."""
        values = np.array([4, 1, 7, 3], dtype=float)
        for method in ("mean", "sum"):
            with self.subTest(method=method):
                np.testing.assert_allclose(changeResolution(values, 3600, 3600, method), values)

    def test_unknown_method(self):
        """An unknown aggregation method raises a ValueError."""
        with self.assertRaises(ValueError):
            changeResolution(np.ones(4), 900, 3600, "max")


class TestEconomicYearGroups(unittest.TestCase):
    """Check representative prices and emission factors against simple averages."""

    def setUp(self):
        self.eco_data = {
            "observation_time": 5,
            "interpolation_points": [0, 2],
            "num_interpolation_points": None,
            "interest_rate": 1.0,
            "optimization_focus": 0,
            "price_supply_el": [10, 40, 20, 80, 160],
            "co2_el_grid": [1, 3, 2, 4, 6],
        }

    def test_discounted_prices_and_undiscounted_emissions(self):
        """Group prices use discount weights while CO2 factors remain plain means."""
        original = deepcopy(self.eco_data)
        result = calculate_eco_data_per_simulated_year(self.eco_data)

        # A deliberately simple 100% rate gives weights 1, 1/2, 1/4.
        # Years 0–1: (10 + 20) / 1.5 = 20.
        # Years 2–4: (20 + 40 + 40) / 1.75 = 400/7.
        self.assertEqual(set(result), {0, 2})
        self.assertAlmostEqual(result[0]["price_supply_el"], 20)
        self.assertAlmostEqual(result[2]["price_supply_el"], 400 / 7)
        self.assertAlmostEqual(result[0]["co2_el_grid"], 2)
        self.assertAlmostEqual(result[2]["co2_el_grid"], 4)
        for year in (0, 2):
            self.assertEqual(result[year]["observation_time"], 5)
            self.assertEqual(result[year]["interpolation_points"], [0, 2])
        self.assertEqual(self.eco_data, original)

class TestBuildingDeviceSizing(unittest.TestCase):
    """Check heating and DHW capacities without profiles from external files."""

    def setUp(self):
        self.system = BES(
            physics={},
            decentral_device_data={
                code: {} for code in ("HP", "BOI", "EH", "TES_DHW", "EH_DHW")
            },
            design_building_data={"T_bivalent": 0, "T_heatlimit": 15},
        )
        self.site = {"T_ne": -10}
        self.building = {
            "buildingFeatures": {"heater": "BOI", "dhw_heater": None},
            "envelope": SimpleNamespace(
                heatload=10000, heatlimit=0, coolingload=0
            ),
            "user": SimpleNamespace(
                dhw_minutely=np.full(120, 1000.0)
            ),
        }

    def test_boiler_covers_space_heating_and_buffered_dhw(self):
        """Buffering a short DHW peak avoids sizing the boiler for that raw peak."""
        # One minute at 61 kW and 59 minutes at 1 kW average to 2 kW.
        self.building["user"].dhw_minutely[60] = 61000
        capacities = self.system.designECS(self.building, self.site)
        self.assertAlmostEqual(capacities["BOI"], 12000)
        self.assertAlmostEqual(capacities["TES_DHW"], 2000)
        self.assertEqual(capacities["HP"], 0)
        self.assertEqual(capacities["EH_DHW"], 0)

    def test_heat_pump_and_backup_cover_the_design_load(self):
        """The heat pump covers 6 kW; backup covers 4 kW plus 1 kW DHW."""
        self.building["buildingFeatures"]["heater"] = "HP"
        capacities = self.system.designECS(self.building, self.site)
        self.assertAlmostEqual(capacities["HP"], 6000)
        self.assertAlmostEqual(capacities["EH"], 5000)
        self.assertAlmostEqual(capacities["TES_DHW"], 1000)
        self.assertEqual(capacities["BOI"], 0)


if __name__ == '__main__':
    unittest.main()
