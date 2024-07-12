import unittest
from functions.weather_handling import get_time_horizon  # Ensure correct import path
import pandas as pd

class TestGetTimeHorizon(unittest.TestCase):
    def test_epw_file(self):
        epw_file_path = r'data\weather\EPW\DEU_BE_Berlin-Schonefeld.AP.103850_TMYx.2004-2018.epw'
        result = get_time_horizon(epw_file_path)
        unique_days = result.dt.date.nunique()  # Extract unique dates from timestamps
        self.assertTrue(unique_days == 365 or unique_days == 366, f"Expected 365 or 366 days, got {unique_days}")

    def test_try_file(self):
        try_file_path = r'data\weather\DWD\TRY2015_Zone3_warm.txt'
        result = get_time_horizon(try_file_path)
        unique_days = result.dt.date.nunique()  # Extract unique dates from timestamps
        self.assertTrue(unique_days == 365 or unique_days == 366, f"Expected 365 or 366 days, got {unique_days}")

if __name__ == '__main__':
    unittest.main()



