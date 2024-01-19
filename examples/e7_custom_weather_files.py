import os
import pandas as pd

# Define the weather path
weather_path = "C:\\Users\\felix\\Programmieren\\tecdm\\src\\districtgenerator\\data\\weather\\FZK_DWD-TRY-MiddleYear_DWD.csv"

# Check if the weather file exists
if os.path.exists(weather_path):
    # Read the weather data
    weather_data = pd.read_csv(weather_path)
    # Do something with the weather data
    # ...
else:
    print("Weather file not found!")
