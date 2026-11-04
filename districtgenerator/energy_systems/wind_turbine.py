# -*- coding: utf-8 -*-

# based on code from EHDO - ENERGY HUB DESIGN OPTIMIZATION Tool

"""Wind-height correction and turbine power curves for generation profiles.

The central-hub model returns dimensionless output relative to a 500 kW
Enercon E40 reference turbine so it can scale to the optimized capacity.
"""
import numpy as np


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
    data : Datahandler
        Datahandler with the unclustered wind speed in ``data.site["wind_speed"]`` (m/s)
        and the number of clusters in ``data.time["clusterNumber"]``.

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
    wind_speed_corr = data.site["wind_speed"] * (devs["WT"]["hub_h"]/devs["WT"]["ref_h"]) ** devs["WT"]["h_coeff"]  # m/s
    wind_speed_corr_clustered = param["wind_speed"] * (devs["WT"]["hub_h"] / devs["WT"]["ref_h"]) ** devs["WT"]["h_coeff"]  # m/s

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
