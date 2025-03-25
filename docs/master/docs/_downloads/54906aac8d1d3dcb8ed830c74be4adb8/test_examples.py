# -*- coding: utf-8 -*-

"""
If you run the examples with Python console, you can see the output file.
To do this right-hand click the test_example.py file.
Then choose 'Modify Run Configuration' and tick 'Run with Python Console'.
"""

import unittest

class TestExamples(unittest.TestCase):
    """Unit Tests for the DistrictGenerator"""

    def test_e1_initialize_datahandle(self):
        """Tests the executability of example 1"""
        from examples import e1_initialize_datahandler as e1

        # Executing the example and checking if no exceptions occur
        data_e1 = e1.example1_initialize_datahandler()
        self.assertIsNotNone(data_e1)  # Ensure that data is returned

    def test_e2_generate_environment(self):
        """Tests the executability of example 2"""
        from examples import e2_generate_environment as e2

        # Executing the example and checking if no exceptions occur
        data_e2 = e2.example2_generate_environment()
        self.assertIsNotNone(data_e2)  # Ensure that data is returned

    def test_e3_initialize_buildings(self):
        """Tests the executability of example 3"""
        from examples import e3_initialize_buildings as e3

        # Executing the example and checking if no exceptions occur
        data_e3 = e3.example3_initialize_buildings()
        self.assertIsNotNone(data_e3)  # Ensure that data is returned

    def test_e4_generate_buildings(self):
        """Tests the executability of example 4"""
        from examples import e4_generate_buildings as e4

        # Executing the example and checking if no exceptions occur
        data_e4 = e4.example4_generate_buildings()
        self.assertIsNotNone(data_e4)  # Ensure that data is returned

    def test_e5_generate_demands(self):
        """Tests the executability of example 5"""
        from examples import e5_generate_demands as e5

        # Executing the example and checking if no exceptions occur
        data_e5 = e5.example5_generate_demands()
        self.assertIsNotNone(data_e5)  # Ensure that data is returned

if __name__ == '__main__':
    unittest.main()

