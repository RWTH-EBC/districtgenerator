# Scripts to get weather data from EPW files and other sources. 

import pandas as pd 

def getEpWeather(file_path:str):
    """
    Function gets EPW weather data from a file and returns it as a pandas dataframe. 

    Information about epw files: https://bigladdersoftware.com/epx/docs/8-3/auxiliary-programs/energyplus-weather-file-epw-data-dictionary.html#field-dry-bulb-temperature 
    Returns:
    weather: pandas dataframe  with the columns: 
        - DirNormRad
        - DiffHorRad
        - DryBulbTemp
    Index is a timestamp in the yyyy-mm-dd-hh format. 
    """

    # Define the column names as per EPW file documentation
    col_names = ["Year", "Month", "Day", "Hour", "Minute", 
                 "Data Source and Uncertainty Flags", "Dry Bulb Temperature", 
                 "Dew Point Temperature", "Relative Humidity", "Atmospheric Station Pressure", 
                 "Extraterrestrial Horizontal Radiation", "Extraterrestrial Direct Normal Radiation", 
                 "Horizontal Infrared Radiation Intensity", "Global Horizontal Radiation", 
                 "Direct Normal Radiation", "Diffuse Horizontal Radiation", 
                 "Global Horizontal Illuminance", "Direct Normal Illuminance", 
                 "Diffuse Horizontal Illuminance", "Zenith Luminance", "Wind Direction", 
                 "Wind Speed", "Total Sky Cover", "Opaque Sky Cover", "Visibility", 
                 "Ceiling Height", "Present Weather Observation", "Present Weather Codes", 
                 "Precipitable Water", "Aerosol Optical Depth", "Snow Depth", 
                 "Days Since Last Snowfall", "Albedo", "Liquid Precipitation Depth", 
                 "Liquid Precipitation Quantity"]
    
    # Load the file
    df = pd.read_csv(file_path, skiprows=8, header=None, names=col_names)
    
    # Creating a timestamp column in the required format
    df['Timestamp'] = pd.to_datetime(df[['Year', 'Month', 'Day', 'Hour']]) - pd.Timedelta(hours=1)
    
    # Adjust the minute and second to 00:00, as EPW files do not contain this information
    df['Timestamp'] = df['Timestamp'].dt.strftime('%Y-%m-%d-%H-00-00')
    
    # Select the required columns
    df = df[['Timestamp', 'Direct Normal Radiation', 'Diffuse Horizontal Radiation', 'Dry Bulb Temperature', 
              "Direct Normal Illuminance",  "Diffuse Horizontal Illuminance",]]
    
    return df

def getTryWeather(file_path: str) -> pd.DataFrame:
    """
    Parse a TRY weather data file into a DataFrame with a timestamp index.
    Assumes specific file formatting.
    
    Parameters:
    - file_path: str, the path to the TRY weather data file.

    Returns:
    - weather: pd.DataFrame, a DataFrame with a timestamp.
    """
    col_names = ['Year', 'Month', 'Day', 'Hour'] + ['extra_{}'.format(i) for i in range(20)]  # Adjust according to actual data structure
    df = pd.read_csv(file_path, sep='\s+', names=col_names, skiprows=1)  # Adjust skiprows based on actual file header
    df['Timestamp'] = pd.to_datetime(df[['Year', 'Month', 'Day', 'Hour']])
    return df

def get_time_horizon(file_path: str) -> int:
    """
    Determine the number of days covered in the specified weather file.

    Parameters:
    - file_path: str, path to the weather data file.

    Returns:
    - int, number of days covered in the weather file.
    """
    if file_path.lower().endswith('.epw'):
        df = getEpWeather(file_path)
    elif file_path.lower().endswith('.txt'):  # Assuming TRY files are .txt
        df = getTryWeather(file_path)
    else:
        raise ValueError("Unsupported file type. Only EPW and TRY files are supported.")
    
    # Assuming 'Timestamp' is formatted as 'YYYY-MM-DD-HH'
    return df['Timestamp'].str.slice(0, 10).nunique()

def get_time_hoirzon(file_path:str):
    

if __name__ == "__main__":
    print("This is a module, it should not be run standalone")

    # Test Run with
    # 