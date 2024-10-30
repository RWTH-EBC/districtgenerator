import unittest
import random as rd
from random import sample
import os
import pandas as pd
from districtgenerator import *
from functions import path_checks
# Should create simulations for residential buildings
# Write a test that all functions run through without errors
# Check if the results exist and are not zero
class TestResidential(unittest.TestCase):
    def setUp(self):
        # Create test scenario
        self.test_data = { 
            'id': [0, 1, 2, 3],
            'building': [
                "SFH",
                "SFH", 
                "TH",
                "TH"
            ],
            'year': [rd.randint(1900, 2024) for _ in range(4)],
            'retrofit': [0] * 4,
            'area': [rd.randint(10, 100) for _ in range(4)]
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
        data.setResultPath()
        data.generateBuildings()

        data.generateDemands()

        # Add assertions to check if the results exist and are not zero
        self.assertTrue(os.path.exists(self.scenario_path), f"Scenario file not found: {self.scenario_path}")
        self.assertGreater(os.path.getsize(self.scenario_path), 0, f"Scenario file is empty: {self.scenario_path}")
        folder_path = os.getcwd()
        results_path = os.path.join(folder_path, 'results', 'demands', 'test_scenario')
        for file in os.listdir(results_path):
            if file.endswith('.csv'):
                file_path = os.path.join(results_path, file)
                df = pd.read_csv(file_path, sep=',')
                # Check if the required columns are present
                required_columns = ["elec", "dhw", "occ", "gains", "heat"]
                for column in required_columns:
                    self.assertIn(column, df.columns, f"Column {column} not found in file: {file_path}")
                self.assertGreaterEqual(df["heat"].sum(), 0, f"Heat sum is negative in file: {file_path}")
                self.assertGreaterEqual(df["elec"].sum(), 0, f"Electricity sum is negative in file: {file_path}")
                self.assertGreaterEqual(df["dhw"].sum(), 0, f"DHW sum is negative in file: {file_path}")
                self.assertGreaterEqual(df["occ"].sum(), 0, f"Occupancy sum is negative in file: {file_path}")
                # Gains can be negative due to cooling
                self.assertTrue(df["gains"].notna().any(), f"Gains column has no values in file: {file_path}")

                               
    def tearDown(self):
        # Delete all files created in the test
        if os.path.exists(self.scenario_path):
            os.remove(self.scenario_path)
        
        # Delete any other files that might have been created during the test
        folder_path = os.getcwd()  # Use current working directory instead of parent
        results_path = os.path.join(folder_path, 'results', 'demands', 'test_scenario')
        
        # Check if the directory exists before trying to delete files
        if os.path.exists(results_path):
            for file in os.listdir(results_path):
                file_path = os.path.join(results_path, file)
                if os.path.isfile(file_path):
                    try:
                        os.remove(file_path)
                    except PermissionError:
                        print(f"Unable to delete {file_path}. File may be in use.")
        else:
            print(f"Results directory not found: {results_path}")
        
        # Remove the results directory if it's empty
        try:
            os.rmdir(results_path)
        except OSError:
            print(f"Unable to remove directory {results_path}. It may not be empty or you may not have permission.")



if __name__ == '__main__':
    unittest.main()