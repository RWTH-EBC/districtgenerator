# -*- coding: utf-8 -*-

# based on code from EHDO - ENERGY HUB DESIGN OPTIMIZATION Tool

import sys
import pandas as pd
import numpy as np
import os


def windSpeed_h(windSpeed_ref, h_ref, h, exponent):
    """
    Calculation of wind speed in another height.

    Parameters
    ----------
    windSpeed_ref : float
        speed of the wind at height h_ref in [m/s].
    h_ref : float
        height h_ref in [m].
    h : float
        height  h in [m].
    exponent : float
        Hellmann exponent.

    Returns
    -------
    windSpeed_h : float
        speed of the wind at height h in [m/s].
    """
    
    windSpeed_h = windSpeed_ref * (h / h_ref) ** exponent
    
    return windSpeed_h


def factor_windSpeed(coreData_central_WT):
    """
    Calculation of ratio between wind speeds in different heights.

    Parameters
    ----------
    coreData_central_WT : dictionary
        Data of the wind turbine.

    Returns
    -------
    factor_WS : float
        ratio of wind speed in height h and wind speed in height h_ref [-].
    """

    h = coreData_central_WT["H"]  # tower height of wind turbine [m]
    h_ref = coreData_central_WT["H_ref"]  # reference height of wind speed measurements [m]
    exponent = coreData_central_WT["alfa"]  # Hellmann exponent [-]

    # potential formulation by Hellmann
    factor_WS = (h / h_ref) ** exponent

    return factor_WS


def get_turbine_power(wind_speed, power_curve):
    """
    Calculate power of wind turbine for a wind speed value.

    Parameters
    ----------
    wind_speed : float
        Wind speed value [m/s].
    power_curve : pandas DataFrame
        DataFrame with entries for each supporting point of the power curve.
        For each supporting point a tuple exists:
        first tuple entry : wind speed [m/s]
        second tuple entry : power of wind turbine [kW]

    Returns
    -------
    power : float
        Generated wind turbine power [kW].
    """

    if wind_speed <= 0:
        power = 0
    elif wind_speed > power_curve.iloc[-1, 0]:
        print("Error: Wind speed is " + str(wind_speed) + " m/s and exceeds wind power curve table.")
        power = 0
    else:
        # Linear interpolation between the two next data points
        for k in range(len(power_curve)):
            if power_curve.iloc[k, 0] > wind_speed:
               power = (power_curve.iloc[k, 1] - power_curve.iloc[k - 1, 1]) / (power_curve.iloc[k, 0]-power_curve.iloc[k - 1, 0]) * (wind_speed-power_curve.iloc[k - 1, 0]) + power_curve.iloc[k - 1, 1]
               break
    
    return power


def powerCurve(wind_turbine_model):
    """
    Function returns power curve of (different) wind turbine models.

    Parameters
    ----------
    wind_turbine_model : string
        Model name of the wind turbine.

    Returns
    -------
    power_curve : pandas DataFrame
        DataFrame with entries for each supporting point of the power curve.
        For each supporting point a tuple exists:
        first tuple entry : wind speed [m/s] 
        second tuple entry : power of wind turbine [kW]
    """

    # information source for Enercon E40: https://www.wind-turbine-models.com/turbines/67-enercon-e-40-5.40
    # possible tower heights: 42/48/65 m
    # power_curve = {0:  (0.0,    0.00),
    #                1:  (2.4,    0.00),
    #                2:  (2.5,    1.14),
    #                3:  (3.0,    4.37),
    #                4:  (3.5,   10.64),
    #                5:  (4.0,   18.87),
    #                6:  (4.5,   29.77),
    #                7:  (5.0,   40.39),
    #                8:  (5.5,   52.85),
    #                9:  (6.0,   69.36),
    #                10: (6.5,   88.02),
    #                11: (7,    112.19),
    #                12: (7.5,  134.67),
    #                13: (8,    165.38),
    #                14: (8.5,  197.08),
    #                15: (9,    236.89),
    #                16: (9.5,  279.46),
    #                17: (10,   328.00),
    #                18: (10.5, 362.93),
    #                19: (11,   396.64),
    #                20: (11.5, 435.27),
    #                21: (12,   465.15),
    #                22: (12.5, 483.63),
    #                23: (13,   495.95),
    #                24: (14,   500.00),
    #                25: (25,   500.00),
    #                26: (25.1,   0.00),
    #                27: (1000,   0.00),
    #                }

    try:
        # open power curve of wind turbine
        data_folder = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
        power_curve_path = os.path.join(data_folder, "wind_turbine_models", "WT_" + wind_turbine_model + ".csv")
        power_curve = pd.read_csv(power_curve_path, header=0, delimiter=";")  # wind_speed [m/s], power [kW]

    except:
        # terminate calculation and write error message
        sys.exit("ERROR: No data for selected wind turbine model found!")
    
    return power_curve


def WT_generation(array_windSpeed):
    """
    Calculate wind power generation for all given values of wind speed.

    Parameters
    ----------
    array_windSpeed : array
        Multiple wind speed values in a 1D-array [m/s].
    powerCurve : pandas DataFrame
        DataFrame with entries for each supporting point of the power curve.
        For each supporting point a tuple exists:
        first tuple entry : wind speed [m/s]
        second tuple entry : power of wind turbine [kW]

    Returns
    -------
    array_WT_power : array
        Generated power of wind turbine [W].
    """
    # initialize list for results
    array_WT_power = []

    for t in range(len(array_windSpeed)):
        # calculate generated wind power for each time step
        windSpeed_t = array_windSpeed[t]
        array_WT_power.append(get_turbine_power(windSpeed_t, powerCurve("Enercon_E40")))  # [kW]

    # transform to array and change unit to Watt
    array_WT_power = np.array(array_WT_power) * 1000  # [W]

    return array_WT_power
