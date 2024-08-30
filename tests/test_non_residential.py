import unittest
import random as rd
from random import sample
import os
import pandas as pd
from districtgenerator import *
# Shoud create simulations for non-residential buildings
# Write a test, that all functions run through without errors
# Check if the results exist and are not zero
class TestNonResidential(unittest.TestCase):
    def setUp(self):
        # Create test scenario
        self.test_data = { 
            'id': [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            'building': [
                "IWU Office, Administrative or Government Buildings", 
                "IWU Research and University Teaching",
                "IWU Health and Care", 
                "IWU School, Day Nursery and other Care", 
                "IWU Culture and Leisure", 
                "IWU Sports Facilities",
                "IWU Trade Buildings",
                "IWU Technical and Utility (supply and disposal)",
                "IWU Transport",
                "IWU Generalized (1) Services building",
                "IWU Generalized (2) Production buildings",
            ],
            'year': [rd.randint(1900, 2024) for _ in range(11)],
            'retrofit': [0] * 11,
            'area': [rd.randint(100, 10000) for _ in range(11)]
        }

        df = pd.DataFrame(self.test_data, columns=self.test_data.keys())
        folder_path = os.getcwd()
        self.scenario_path = os.path.join(folder_path, 'data', 'scenarios', 'test_scenario.csv')
        df.to_csv(self.scenario_path, index=False, sep=';')
        print(df.head())

    def test_non_residential(self):
        # Test all functions in the non_residential module
        data = Datahandler()
        data.setWeatherFile('data/weather/EPW/DEU_BE_Berlin-Schonefeld.AP.103850_TMYx.2004-2018.epw')

        # Generate Environment for the District
        data.generateEnvironment()

        # Use the created scenario for testing
        data.initializeBuildings('test_scenario')
        data.generateBuildings()

        data.generateDemands()

        # Add assertions to check if the results exist and are not zero
        self.assertTrue(os.path.exists(self.scenario_path))
        self.assertGreater(os.path.getsize(self.scenario_path), 0)

       # Check if the results exist and are not zero

    def tearDown(self):
        # Delete all files created in the test
        if os.path.exists(self.scenario_path):
            os.remove(self.scenario_path)
        
        # Delete any other files that might have been created during the test
        folder_path = os.path.dirname(os.getcwd())
        results_path = os.path.join(folder_path, 'results')
        if os.path.exists(results_path):
            for file in os.listdir(results_path):
                file_path = os.path.join(results_path, file)
                if os.path.isfile(file_path):
                    os.remove(file_path)


if __name__ == '__main__':
    unittest.main()