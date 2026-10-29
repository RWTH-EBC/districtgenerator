"""
Weather data of the district: test reference year (TRY) loading and interpolation.
"""
import os

import numpy as np

from districtgenerator.environment.site import get_holidays, select_plz_data


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
    # todo: maybe put in config if more TRY years are added?
    if data.site["TRYYear"] == "TRY2015":
        first_row = 35
        data.initial_day = 3 # Thursday
    elif data.site["TRYYear"] == "TRY2045":
        first_row = 37
        data.initial_day = 6 # Sunday


    select_plz_data(data)
    # load weather data
    # select the correct file depending on the TRY weather station location
    weatherData = np.loadtxt(os.path.join(data.filePath, "weather", "TRY_" + data.site["TRYYear"][-4:] + "_" + data.site["TRYType"])
        + "/"
        + data.site["TRYYear"] + "_"
        + str(data.site["Location"]) + "_" + str(data.site["TRYType"])
        + ".dat",
        skiprows=first_row - 1)

    """
    # Use this function to load old TRY-weather data
    weatherData = np.loadtxt(os.path.join(self.filePath, 'weather')
                             + "/"
                             + self.site["TRYYear"] + "_Zone"
                             + str(self.site["climateZone"]) + "_"
                             + self.site["TRYType"] + ".txt",
                             skiprows=first_row - 1)"""

    # weather data starts with 1st january at 1:00 am.
    # Add data point for 0:00 am to be able to perform interpolation.
    weatherData_temp = weatherData[-1:, :]
    weatherData = np.append(weatherData_temp, weatherData, axis=0)

    # get weather data of interest
    [temp_sunDirect, temp_sunDiff, temp_tempe, temp_wind, temp_rhum, temp_pre, temp_ssw] = \
        [weatherData[:, 12], weatherData[:, 13], weatherData[:, 5], weatherData[:, 8], weatherData[:, 11], weatherData[:, 6], weatherData[:, 9]]

    data.time["timeSteps"] = int(data.time["dataLength"] / data.time["timeResolution"])

    # load the holidays
    if data.site["TRYYear"] == "TRY2015":
        data.calendar["holidays"] = get_holidays(country_code="DE", year=2015)
    elif data.site["TRYYear"] == "TRY2045":
        data.calendar["holidays"] = get_holidays(country_code="DE", year=2045)

    # interpolate input data to achieve required data resolution
    # transformation from values for points in time to values for time intervals
    data.site["SunDirect"] = np.interp(np.arange(0, data.time["dataLength"] + 1, data.time["timeResolution"]),      # Direct horizontal radiation
                                       np.arange(0, data.time["dataLength"] + 1, data.time["dataResolution"]),
                                       temp_sunDirect)[0:-1]
    data.site["SunDiffuse"] = np.interp(np.arange(0, data.time["dataLength"] + 1, data.time["timeResolution"]),     # Diffuse horizontal radiation
                                        np.arange(0, data.time["dataLength"] + 1, data.time["dataResolution"]),
                                        temp_sunDiff)[0:-1]
    data.site["T_e"] = np.interp(np.arange(0, data.time["dataLength"] + 1, data.time["timeResolution"]),
                                 np.arange(0, data.time["dataLength"] + 1, data.time["dataResolution"]),
                                 temp_tempe)[0:-1]
    data.site["wind_speed"] = np.interp(np.arange(0, data.time["dataLength"] + 1, data.time["timeResolution"]),
                                        np.arange(0, data.time["dataLength"] + 1, data.time["dataResolution"]),
                                        temp_wind)[0:-1]
    data.site["r_humidity"] = np.interp(np.arange(0, data.time["dataLength"] + 1, data.time["timeResolution"]),
                                        np.arange(0, data.time["dataLength"] + 1, data.time["dataResolution"]),
                                        temp_rhum)[0:-1]
    data.site["pressure"] = np.interp(np.arange(0, data.time["dataLength"] + 1, data.time["timeResolution"]),
                                        np.arange(0, data.time["dataLength"] + 1, data.time["dataResolution"]),
                                        temp_pre)[0:-1]
    data.site["ssw"] = np.interp(np.arange(0, data.time["dataLength"] + 1, data.time["timeResolution"]),
                                    np.arange(0, data.time["dataLength"] + 1, data.time["dataResolution"]),
                                    1 - np.clip(temp_ssw, 0, 8) / 8.0)[0:-1]

    data.site["SunTotal"] = data.site["SunDirect"] + data.site["SunDiffuse"] # This is the GHI (Global Horizontal Irradiance)
