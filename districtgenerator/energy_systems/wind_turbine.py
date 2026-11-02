# -*- coding: utf-8 -*-

# based on code from EHDO - ENERGY HUB DESIGN OPTIMIZATION Tool

"""Wind-height correction and turbine power curves for generation profiles.

The central-hub model returns dimensionless output relative to a 500 kW
Enercon E40 reference turbine so it can scale to the optimized capacity.
"""
import sys
import pandas as pd
import numpy as np
import os
from districtgenerator.utilities.paths import PACKAGE_DIR


def windSpeed_h(windSpeed_ref, h_ref, h, exponent):
    """Extrapolate reference wind speed to a target height with Hellmann's law.

    Parameters
    ----------
    windSpeed_ref : float or numpy.ndarray
        Wind speed at the measurement height in m/s.
    h_ref : float
        Measurement height above ground in m.
    h : float
        Target height, typically turbine hub height, in m.
    exponent : float
        Dimensionless wind-shear exponent representing terrain roughness.

    Returns
    -------
    float or numpy.ndarray
        Wind speed in m/s at the target height, with the input speed's shape.
    """
    
    windSpeed_h = windSpeed_ref * (h / h_ref) ** exponent
    
    return windSpeed_h


def factor_windSpeed(coreData_central_WT):
    """Calculate the height correction applied to measured wind speed.

    Parameters
    ----------
    coreData_central_WT : dict
        Turbine settings: hub height ``H`` and reference measurement height
        ``H_ref`` in m (both positive), and Hellmann exponent ``alfa``.

    Returns
    -------
    float
        Dimensionless multiplier converting reference-height wind speed to
        hub-height wind speed.
    """

    h = coreData_central_WT["H"]  # tower height of wind turbine [m]
    h_ref = coreData_central_WT["H_ref"]  # reference height of wind speed measurements [m]
    exponent = coreData_central_WT["alfa"]  # Hellmann exponent [-]

    # potential formulation by Hellmann
    factor_WS = (h / h_ref) ** exponent

    return factor_WS


def get_turbine_power(wind_speed, power_curve):
    """Interpolate a turbine's power output for one wind speed.

    Parameters
    ----------
    wind_speed : float
        Hub-height wind speed in m/s.
    power_curve : pandas.DataFrame
        Wind speed in m/s in column 0 and electrical power in kW in column 1,
        sorted by increasing speed, with a first point at zero speed.

    Returns
    -------
    float
        Interpolated electrical output in kW.
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
    """Read a packaged turbine power curve by model identifier.

    Parameters
    ----------
    wind_turbine_model : str
        Model identifier used in ``data/wind_turbine_models/WT_<model>.csv``,
        for example ``"Enercon_E40"``.

    Returns
    -------
    pandas.DataFrame
        Power-curve table read from the semicolon-separated CSV, with wind
        speed in m/s in the first column and electrical output in kW.
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
        data_folder = os.path.join(PACKAGE_DIR, "data")
        power_curve_path = os.path.join(data_folder, "wind_turbine_models", "WT_" + wind_turbine_model + ".csv")
        power_curve = pd.read_csv(power_curve_path, header=0, delimiter=";")  # wind_speed [m/s], power [kW]

    except:
        # terminate calculation and write error message
        sys.exit("ERROR: No data for selected wind turbine model found!")
    
    return power_curve


def WT_generation(array_windSpeed):
    """Calculate an Enercon E40 electrical generation time series.

    Parameters
    ----------
    array_windSpeed : array_like
        One-dimensional sequence of hub-height wind speeds in m/s, ordered
        by time. Positive speeds must be below the curve's final table speed.

    Returns
    -------
    numpy.ndarray
        Electrical power in W at each input time step, shape ``(n_steps,)``.
        The model is fixed to the packaged ``Enercon_E40`` curve; no height
        correction is applied here.
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


# %% Enercon E-40 power curve used for the central energy hub

def calc_WT_power(devs, param, data):
    """Calculate normalized Enercon E40 output for full and clustered weather.

    Parameters
    ----------
    devs : dict
        ``WT`` settings: ``hub_h`` and ``ref_h`` (positive heights in m), and
        ``h_coeff`` (dimensionless Hellmann wind-shear exponent).
    param : dict
        Clustered reference-height wind speeds in m/s under ``wind_speed``,
        shape ``(clusterNumber, steps_per_cluster)``.

    Returns
    -------
    WT_power_norm : numpy.ndarray
        Full-series electrical output divided by the curve's 500 kW rating;
        dimensionless.
    WT_power_norm_clustered : numpy.ndarray
        Dimensionless representative-period output.
    """

    power_curve = {0:  (0.0,    0.00),
                   1:  (2.4,    0.00),
                   2:  (2.5,    1.14),
                   3:  (3.0,    4.37),
                   4:  (3.5,   10.64),
                   5:  (4.0,   18.87),
                   6:  (4.5,   29.77),
                   7:  (5.0,   40.39),
                   8:  (5.5,   52.85),
                   9:  (6.0,   69.36),
                   10: (6.5,   88.02),
                   11: (7,    112.19),
                   12: (7.5,  134.67),
                   13: (8,    165.38),
                   14: (8.5,  197.08),
                   15: (9,    236.89),
                   16: (9.5,  279.46),
                   17: (10,   328.00),
                   18: (10.5, 362.93),
                   19: (11,   396.64),
                   20: (11.5, 435.27),
                   21: (12,   465.15),
                   22: (12.5, 483.63),
                   23: (13,   495.95),
                   24: (14,   500.00),
                   25: (25,   500.00),
                   26: (25.1,   0.00),
                   27: (1000,   0.00),
                   }
    wind_speed_corr = data.site["wind_speed"] * (devs["WT"]["hub_h"]/devs["WT"]["ref_h"]) ** devs["WT"]["h_coeff"]  # kW
    wind_speed_corr_clustered = param["wind_speed"] * (devs["WT"]["hub_h"] / devs["WT"]["ref_h"]) ** devs["WT"]["h_coeff"]  # kW

    WT_power = np.zeros(np.shape(wind_speed_corr))
    WT_power_clustered = np.zeros(np.shape(wind_speed_corr_clustered))

    for i in range(len(wind_speed_corr)):
        WT_power[i] = interpolate_power_curve(wind_speed_corr[i], power_curve)

    for d in range(data.time["clusterNumber"]):
        for t in range(len(wind_speed_corr_clustered[d])):
            WT_power_clustered[d][t] = interpolate_power_curve(wind_speed_corr_clustered[d][t], power_curve)

    WT_power_norm = WT_power / 500  # power_curve with 500 kW as maximum output
    WT_power_norm_clustered = WT_power_clustered / 500  # power_curve with 500 kW as maximum output

    return WT_power_norm, WT_power_norm_clustered


def interpolate_power_curve(wind_speed, power_curve):
    """Interpolate wind-turbine output from indexed supporting points.

    Parameters
    ----------
    wind_speed : float
        Hub-height speed in m/s. Positive inputs must be strictly below the
        final tabulated speed.
    power_curve : dict
        Contiguous integer keys starting at 0, in increasing wind-speed order,
        mapped to ``(wind speed in m/s, electrical power in kW)``. The first
        supporting point must be at zero speed.

    Returns
    -------
    float
        Electrical output in kW.
    """
    if wind_speed <= 0:
        return 0
    if wind_speed > power_curve[len(power_curve)-1][0]:
        print("Error: Wind speed is " + str(wind_speed) + " m/s and exceeds wind power curve table.")
        return 0

    # Linear interpolation:
    for k in range(len(power_curve)):
        if power_curve[k][0] > wind_speed:
           power = (power_curve[k][1]-power_curve[k-1][1])/(power_curve[k][0]-power_curve[k-1][0]) * (wind_speed-power_curve[k-1][0]) + power_curve[k-1][1]
           break
    return power
