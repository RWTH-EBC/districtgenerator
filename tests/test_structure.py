# -*- coding: utf-8 -*-
"""
Fast checks of the package structure: imports and shared helpers.
"""
import importlib
import math
import pkgutil
import unittest

import districtgenerator

# Packages of the old structure that were removed during the restructuring
OLD_PACKAGES = (
    "districtgenerator.classes",
    "districtgenerator.functions",
    "districtgenerator.data_handling",
)


class TestStructure(unittest.TestCase):
    """Unit tests for the package structure of the districtgenerator."""

    def test_all_modules_import(self):
        """Every module of the workflow packages can be imported."""
        names = [m.name for m in pkgutil.walk_packages(districtgenerator.__path__, "districtgenerator.")]
        for name in names:
            with self.subTest(module=name):
                importlib.import_module(name)

    def test_public_import(self):
        """The Datahandler is available directly from the package."""
        from districtgenerator import Datahandler
        from districtgenerator.datahandler import Datahandler as ModuleDatahandler
        self.assertIs(Datahandler, ModuleDatahandler)

    def test_old_packages_removed(self):
        """The old packages classes, functions and data_handling no longer exist."""
        for old in OLD_PACKAGES:
            with self.subTest(package=old):
                with self.assertRaises(ModuleNotFoundError):
                    importlib.import_module(old)

    def test_thermal_registry(self):
        """Each thermal model type maps to its envelope and simulation."""
        from districtgenerator.buildings import thermal
        for model_type in ("5R1C", "7R2C", "FourElements"):
            with self.subTest(model=model_type):
                self.assertEqual(thermal.get_envelope_class(model_type).__name__, "Envelope")
                self.assertTrue(hasattr(thermal.get_simulation(model_type), "calc"))
        with self.assertRaises(ValueError):
            thermal.get_envelope_class("3R1C")

    def test_annuity(self):
        """Annuity factors follow VDI 2067-1 with replacements and residual value."""
        from districtgenerator.economics import annuity
        observation_time, interest_rate = 20, 0.05
        q = 1 + interest_rate
        crf = (q ** observation_time * interest_rate) / (q ** observation_time - 1)
        self.assertAlmostEqual(annuity.capital_recovery_factor(observation_time, interest_rate), crf)
        self.assertAlmostEqual(annuity.capital_recovery_factor(20, 0), 1 / 20)
        # Life time 15 a: one replacement after 15 a, residual value of 10 a
        res_value = (2 * 15 - 20) / 15 * q ** -20
        expected = (1 + q ** -15 - res_value) * crf
        self.assertAlmostEqual(annuity.annuity_factor(15, observation_time, interest_rate), expected)
        # Life time longer than the observation period: no replacement
        res_value = (30 - 20) / 30 * q ** -20
        self.assertAlmostEqual(annuity.annuity_factor(30, observation_time, interest_rate), (1 - res_value) * crf)

    def test_cooling_supply_rules(self):
        """Missing cooler values default to a cooling grid for heat grid buildings, else a local chiller."""
        from districtgenerator.energy_systems import technologies
        self.assertEqual(technologies.get_cooling_supply({"heater": "heat_grid", "cooling": 1}), "cooling_grid")
        self.assertEqual(technologies.get_cooling_supply({"heater": "HP", "cooling": 1, "cooler": math.nan}), "CC")
        self.assertIsNone(technologies.get_cooling_supply({"heater": "HP", "cooling": 0}))
        self.assertEqual(technologies.get_heating_candidates("opt"), technologies.HEATING_CONCEPTS)


if __name__ == '__main__':
    unittest.main()
