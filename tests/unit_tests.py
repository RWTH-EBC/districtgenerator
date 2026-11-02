# -*- coding: utf-8 -*-
"""
Unit tests for single functions of the districtgenerator.

The expected values are calculated by hand, so the tests do not depend on data files or other modules.
"""
import unittest

import numpy as np

from districtgenerator.time_series.resolution import changeResolution


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


if __name__ == '__main__':
    unittest.main()
