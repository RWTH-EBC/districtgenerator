# -*- coding: utf-8 -*-
"""
Fast checks of the package structure: imports, compatibility aliases and shared helpers.
"""
import importlib
import math
import pickle
import pkgutil
import unittest
import warnings

import districtgenerator

OLD_PATHS = {
    "districtgenerator.classes.datahandler": "districtgenerator.datahandler",
    "districtgenerator.classes.users": "districtgenerator.buildings.profiles.users",
    "districtgenerator.classes.envelope_7R2C": "districtgenerator.buildings.thermal.model_7r2c.envelope",
    "districtgenerator.functions._5R1C": "districtgenerator.buildings.thermal.model_5r1c.simulation",
    "districtgenerator.functions.opti_central": "districtgenerator.optimization.central.operation",
    "districtgenerator.functions.heating_network_simple": "districtgenerator.energy_systems.heating_network",
    "districtgenerator.data_handling.config": "districtgenerator.config.settings",
}


class TestStructure(unittest.TestCase):
    """Unit tests for the package structure of the districtgenerator."""

    def test_all_modules_import(self):
        """Every module of the workflow packages can be imported."""
        names = [m.name for m in pkgutil.walk_packages(districtgenerator.__path__, "districtgenerator.")]
        for name in names:
            with self.subTest(module=name):
                importlib.import_module(name)

    def test_public_import(self):
        """The Datahandler is available from the package and from the old classes package."""
        from districtgenerator import Datahandler
        from districtgenerator.classes import Datahandler as OldDatahandler
        self.assertIs(Datahandler, OldDatahandler)

    def test_old_module_paths(self):
        """Old module paths resolve to the new modules and warn about the move."""
        for old, new in OLD_PATHS.items():
            with self.subTest(module=old):
                with warnings.catch_warnings(record=True):
                    warnings.simplefilter("always")
                    module = importlib.import_module(old)
                self.assertIs(module, importlib.import_module(new))

    def test_old_system_module(self):
        """BES and CES are still importable from the old system module."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from districtgenerator.classes.system import BES, CES
        from districtgenerator.energy_systems.building_energy_system import BES as NewBES
        from districtgenerator.energy_systems.central_energy_system import CES as NewCES
        self.assertIs(BES, NewBES)
        self.assertIs(CES, NewCES)

    def test_old_pickles(self):
        """Pickles that reference classes by their old module path can be loaded."""
        from districtgenerator.environment.solar import Sun
        legacy = b"cdistrictgenerator.classes.solar\nSun\n."
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            self.assertIs(pickle.loads(legacy), Sun)

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
