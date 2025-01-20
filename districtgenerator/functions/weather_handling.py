# Scripts to get weather data from EPW files and other sources. 

import pandas as pd 

def getEpWeather(file_path:str) -> pd.DataFrame:
    """
    Function gets EPW weather data from a file and returns it as a pandas dataframe. 

    Information about epw files:
    https://bigladdersoftware.com/epx/docs/8-3/auxiliary-programs/energyplus-weather-file-epw-data-dictionary.html#field-dry-bulb-temperature 
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
    #df['Timestamp'] = df['Timestamp'].dt.strftime('%Y-%m-%d-%H-00-00')
    
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
    if "2015" or "2045" in file_path:
        if "2015" in file_path:
            year = 2015
        elif "2045" in file_path:
            year = 2015
        with open(file_path, "r") as file:
            for line_number, line in enumerate(file, start=1):
                if "***" in line:
                    header_row = (
                        line_number - 1 - 1
                    )  # -1 for header above *** and -1 for start to count at 0
                    break

   

    else:
        raise ValueError("Unsupported format type for TRY files. Only 2015 and 2045 are supported.")
    df = pd.read_table(
        filepath_or_buffer=file_path,
        header=header_row,
        sep='\s+',
        skip_blank_lines=False,
        encoding="latin",
    )
    df = df.iloc[1:]
    df["YEAR"] = year 
    df["MONTH"] = df["MM"].astype(int)
    df["DAY"] = df["DD"].astype(int)
    df["HOUR"] = df["HH"].astype(int)
    df['Timestamp'] = pd.to_datetime(df[["YEAR", 'MONTH', 'DAY', 'HOUR']])
    return df

def get_time_horizon(file_path: str) -> pd.Series:
    """
    Extracts timestamps from a weather file and returns them as a pandas Series.

    Parameters:
    - file_path: str
      The path to the weather data file.

    Returns:
    - pd.Series
      A pandas Series object containing the timestamps extracted from the weather file, formatted as 'YYYY-MM-DD-HH'.

    Raises:
    - ValueError
      If the file type is not supported. Only EPW and TRY files are supported.
    """
    if file_path.lower().endswith('.epw'):
        df = getEpWeather(file_path)
    elif file_path.lower().endswith('.txt'):  # Assuming TRY files are .txt
        df = getTryWeather(file_path)
    else:
        raise ValueError("Unsupported file type. Only EPW and TRY files are supported.")
    
    return df['Timestamp']
    

if __name__ == "__main__":
    print("This is a module, it should not be run standalone")

    # Test Run with
    # 