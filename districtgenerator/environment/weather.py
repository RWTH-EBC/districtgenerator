"""
Weather data of the district: test reference year (TRY) loading and interpolation.
"""
import os

import numpy as np

from districtgenerator.config.settings import LocationConfig
from districtgenerator.environment.site import get_holidays, select_plz_data
from districtgenerator.utilities.paths import DATA_DIR

# Column index in the TRY file for each weather series in data.site
TRY_COLUMNS = {
    "T_e": 5,           # t: air temperature [°C]
    "pressure": 6,      # p: air pressure [hPa]
    "wind_speed": 8,    # WG: wind speed [m/s]
    "ssw": 9,           # N: cloud cover [octas], converted to sky clearness below
    "r_humidity": 11,   # RF: relative humidity [%]
    "SunDirect": 12,    # B: direct horizontal irradiance [W/m²]
    "SunDiffuse": 13,   # D: diffuse horizontal irradiance [W/m²]
}


def load_weather(data):
    """
    Load the TRY weather data of the site and interpolate it to the time resolution.

    Sets the first weekday of the year, the holidays and the weather time series in
    ``data.site``: direct, diffuse and total horizontal irradiance, outdoor temperature,
    wind speed, relative humidity, air pressure and sky clearness.

    Parameters
    ----------
    data : Datahandler
        Datahandler with site and time configuration.

    Returns
    -------
    None.
    """
    # %% load first day of the year
    try_format = LocationConfig.TRY_FORMATS[data.site["TRYYear"]]
    first_row = try_format["first_row"]
    data.initial_day = try_format["initial_day"]

    select_plz_data(data)
    # load weather data
    # select the correct file depending on the TRY weather station location
    weatherData = np.loadtxt(os.path.join(DATA_DIR, "weather",
                                          "TRY_" + data.site["TRYYear"][-4:] + "_" + data.site["TRYType"],
                                          data.site["TRYYear"] + "_" + str(data.site["Location"]) + "_"
                                          + str(data.site["TRYType"]) + ".dat"),
                             skiprows=first_row - 1)

    # weather data starts with 1st january at 1:00 am.
    # Add data point for 0:00 am to be able to perform interpolation.
    # The last hour of the year (31st December) is reused as this first point.
    weatherData_temp = weatherData[-1:, :]
    weatherData = np.append(weatherData_temp, weatherData, axis=0)

    # get weather data of interest
    weather_columns = {key: weatherData[:, column] for key, column in TRY_COLUMNS.items()}
    # cloud cover of 0 to 8 octas -> sky clearness of 1 (clear) to 0 (overcast)
    weather_columns["ssw"] = 1 - np.clip(weather_columns["ssw"], 0, 8) / 8.0

    data.time["timeSteps"] = int(data.time["dataLength"] / data.time["timeResolution"])

    # load the holidays of the TRY year, e.g. "TRY2015" -> 2015
    try_year = int(data.site["TRYYear"][-4:])
    #todo: maybe add state as well for holidays?
    data.calendar["holidays"] = get_holidays(country_code="DE", year=try_year)

    # interpolate input data to achieve required data resolution
    # transformation from values for points in time to values for time intervals
    # Time points of the model (target resolution) and of the TRY file (hourly), in seconds
    target_times = np.arange(0, data.time["dataLength"] + 1, data.time["timeResolution"])
    data_times = np.arange(0, data.time["dataLength"] + 1, data.time["dataResolution"])

    # Interpolate every series in TRY_COLUMNS and store it in data.site under the same key:
    # - SunDirect:  direct horizontal irradiance [W/m²], beam radiation from the sun's direction
    # - SunDiffuse: diffuse horizontal irradiance [W/m²], radiation scattered by the sky and clouds
    # - T_e:        outdoor air temperature [°C]
    # - wind_speed: wind speed at measurement height [m/s]
    # - r_humidity: relative humidity [%]
    # - pressure:   air pressure [hPa]
    # - ssw:        sky clearness [-], 1 = clear sky, 0 = overcast
    # The last point is dropped, so each value belongs to one time interval
    for key, series in weather_columns.items():
        data.site[key] = np.interp(target_times, data_times, series)[0:-1]

    data.site["SunTotal"] = data.site["SunDirect"] + data.site["SunDiffuse"] # This is the GHI (Global Horizontal Irradiance)
