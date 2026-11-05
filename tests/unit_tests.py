# -*- coding: utf-8 -*-
"""
Unit tests for single functions of the districtgenerator.

The expected values are calculated by hand, so the tests do not depend on data files or other modules.
"""
import unittest

import numpy as np

from districtgenerator.time_series.resolution import changeResolution
from districtgenerator.optimization.central.dimensioning import _discount_factor
from districtgenerator.optimization.central.parameters import calc_monthly_dem


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


class TestDiscountFactor(unittest.TestCase):
    """Unit tests for _discount_factor of the central dimensioning optimization."""

    def test_zero_interest_rate(self):
        """Without interest, the discount factor is the interval length."""
        self.assertEqual(_discount_factor(5, 5, 0), 5)

    def test_first_year_is_discounted(self):
        """Support year 0 refers to the first year of VDI 2067, so it is already discounted once."""
        self.assertAlmostEqual(_discount_factor(0, 1, 0.05), 1 / 1.05)

    def test_interval_from_first_year(self):
        """Interval of three years from support year 0: 1/1.1 + 1/1.1^2 + 1/1.1^3."""
        self.assertAlmostEqual(_discount_factor(0, 3, 0.1), 2.486851991, places=8)

    def test_interval_from_later_year(self):
        """Interval of two years from support year 5: 1/1.1^6 + 1/1.1^7."""
        self.assertAlmostEqual(_discount_factor(5, 2, 0.1), 1.077632048, places=8)

    def test_intervals_cover_observation_period(self):
        """The intervals of all support years add up to the present value factor of the whole period."""
        interest_rate = 0.05
        intervals = {0: 5, 5: 5, 10: 10}  # support years [0, 5, 10] and an observation period of 20 years
        total = sum(_discount_factor(year, length, interest_rate) for year, length in intervals.items())
        self.assertAlmostEqual(total, (1 - 1.05 ** -20) / 0.05)


class TestCalcMonthlyDem(unittest.TestCase):
    """Unit tests for calc_monthly_dem of the central parameter preparation."""

    @staticmethod
    def _demands(values):
        """Same profile for heat, cooling and power."""
        return {m: np.array(values, dtype=float) for m in ("heat", "cool", "power")}

    def test_constant_hourly(self):
        """Constant 1 kW in hourly resolution: 744 h in January, 672 h in February, 8760 h per year."""
        result = calc_monthly_dem(self._demands(np.ones(8760)), 3600, {})
        self.assertAlmostEqual(result["monthly_dem"]["heat"]["Jan"], 0.744)
        self.assertAlmostEqual(result["monthly_dem"]["heat"]["Feb"], 0.672)
        self.assertEqual(result["year_sum"]["heat"], 8)
        self.assertEqual(result["year_peak"]["heat"], 1)

    def test_constant_quarter_hourly(self):
        """The same constant demand in quarter-hourly resolution gives the same energy."""
        result = calc_monthly_dem(self._demands(np.ones(35040)), 900, {})
        self.assertAlmostEqual(result["monthly_dem"]["cool"]["Jan"], 0.744)
        self.assertAlmostEqual(result["monthly_dem"]["cool"]["Dec"], 0.744)
        self.assertEqual(result["year_sum"]["cool"], 8)

    def test_month_boundaries(self):
        """A demand only in January is completely assigned to January."""
        values = np.zeros(8760)
        values[:744] = 2
        result = calc_monthly_dem(self._demands(values), 3600, {})
        self.assertAlmostEqual(result["monthly_dem"]["power"]["Jan"], 1.488)
        self.assertAlmostEqual(sum(result["monthly_dem"]["power"].values()), 1.488)

    def test_peak(self):
        """The annual peak is the maximum demand value in kW."""
        values = np.ones(8760)
        values[4000] = 50
        result = calc_monthly_dem(self._demands(values), 3600, {})
        self.assertEqual(result["year_peak"]["heat"], 50)


if __name__ == '__main__':
    unittest.main()
