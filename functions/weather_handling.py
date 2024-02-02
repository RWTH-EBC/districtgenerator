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
    df = df[['Timestamp', 'Direct Normal Radiation', 'Diffuse Horizontal Radiation', 'Dry Bulb Temperature']]
    
    return df


if __name__ == "__main__":
    print("This is a module, it should not be run standalone") 

    # Test Run with
    # 