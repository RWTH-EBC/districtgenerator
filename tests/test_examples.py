# -*- coding: utf-8 -*-

"""
If you run the examples with Python console, you can see the output file.
To do this right-hand click the test_example.py file.
Then choose 'Modify Run Configuration' and tick 'Run with Python Console'.
"""

import unittest
import numpy as np
import random

class TestExamples(unittest.TestCase):
    """Unit Tests for the DistrictGenerator"""

    def test_e1_initialize_datahandle(self):
        """Tests the executability of example 1"""
        from examples import e1_initialize_datahandler as e1

        # Executing the example and checking if no exceptions occur
        data_e1 = e1.example1_initialize_datahandler()
        self.assertIsNotNone(data_e1)  # Ensure that data is returned
        # Check functionality works as expected with exemplary output
        self.assertEqual(data_e1.district, [])

    def test_e2_generate_environment(self):
        """Tests the executability of example 2"""
        from examples import e2_generate_environment as e2

        # Executing the example and checking if no exceptions occur
        data_e2 = e2.example2_generate_environment()
        self.assertIsNotNone(data_e2)  # Ensure that data is returned
        # Check functionality works as expected with exemplary output
        self.assertIsInstance(data_e2.site['T_e'][0], float)

    def test_e3_initialize_buildings(self):
        """Tests the executability of example 3"""
        from examples import e3_initialize_buildings as e3

        # Executing the example and checking if no exceptions occur
        data_e3 = e3.example3_initialize_buildings()
        self.assertIsNotNone(data_e3)  # Ensure that data is returned
        # Check functionality works as expected with exemplary output
        self.assertIsInstance(data_e3.district[0]["buildingFeatures"]["id"], np.integer)
        self.assertIsInstance(data_e3.district[0]["buildingFeatures"]["building"], str)
        self.assertIsInstance(data_e3.district[0]["buildingFeatures"]["year"], np.integer)
        self.assertIsInstance(data_e3.district[0]["buildingFeatures"]["retrofit"], np.integer)
        self.assertIsInstance(data_e3.district[0]["buildingFeatures"]["area"], np.integer)

    def test_e4_generate_buildings(self):
        """Tests the executability of example 4"""
        from examples import e4_generate_buildings as e4

        # Executing the example and checking if no exceptions occur
        data_e4 = e4.example4_generate_buildings()
        self.assertIsNotNone(data_e4)  # Ensure that data is returned
        # Check functionality works as expected with exemplary output
        self.assertIsInstance(data_e4.district[0]["envelope"].A["opaque"], dict)

    def test_e5_generate_demands(self):
        """Run the example multiple times with a deterministic building setup using a seeded RNG,
        and verify that the generated demands remain within a reasonable range."""
        from examples import e5_generate_demands as e5

        for i in range(20):
            # Fixed seed RNG to pass
            rng = random.Random(42)
            np.random.seed(42)

            data_e5 = e5.example5_generate_demands(rng=rng)

            # Expected outputs per building in Wh.
            # - Expected values for heat and DHW are averaged over multiple runs,
            #   as the richardson.py tool stochastically generates varying occupancy profiles.
            #   These profiles influence DHW demand directly, and heating demand indirectly via internal gains.
            # - For electricity, the values are based on the source:
            #   https://www.stromspiegel.de/stromverbrauch-verstehen/stromverbrauch-im-haushalt/#c120951
            expected_outputs = [
                {"total_heat": 16_520_000, "total_elec": 4_000_000, "total_dhw": 1_600_000},  # Building 0
                {"total_heat": 9_090_000, "total_elec": 3_000_000, "total_dhw": 1_330_000},   # Building 1
                {"total_heat": 29_210_000, "total_elec": 7_700_000, "total_dhw": 4_980_000},  # Building 2
                {"total_heat": 17_120_000, "total_elec": 5_300_000, "total_dhw": 3_510_000},  # Building 3
            ]

            for idx, (building, expected) in enumerate(zip(data_e5.district, expected_outputs)):
                heat = building["user"].heat
                elec = building["user"].elec
                dhw = building["user"].dhw

                # Check functionality works as expected with exemplary output
                self.assertIsInstance(heat, np.ndarray, f"Building {idx}: Heat is not ndarray")

                actual = {
                    "total_heat": np.sum(heat) * data_e5.time["timeResolution"] / 3600,
                    "total_elec": np.sum(elec) * data_e5.time["timeResolution"] / 3600,
                    "total_dhw": np.sum(dhw) * data_e5.time["timeResolution"] / 3600,
                }

                for key in expected:
                    expected_val = expected[key]
                    tol = expected_val * 0.10  # ±10% tolerance
                    lower = expected_val - tol
                    upper = expected_val + tol
                    actual_val = actual[key]

                    self.assertTrue(
                        lower <= actual_val <= upper,
                        f"Building {idx}: {key}={actual_val:.2f} not within 10% of expected {expected_val:.2f}"
                    )

if __name__ == '__main__':
    unittest.main()

