# -*- coding: utf-8 -*-

# based on code from EHDO - ENERGY HUB DESIGN OPTIMIZATION Tool

"""Wind-height correction and turbine power curves for generation profiles.

The central-hub model returns dimensionless output relative to a 500 kW
Enercon E40 reference turbine so it can scale to the optimized capacity.
"""
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
    """Interpolate turbine output for one wind speed or a time series.

    Parameters
    ----------
    wind_speed : float or array_like
        Hub-height wind speed in m/s.
    power_curve : pandas.DataFrame
        Wind speed in m/s in column 0 and electrical power in kW in column 1,
        sorted by increasing speed, starting with zero speed and zero power.

    Returns
    -------
    numpy scalar or numpy.ndarray
        Electrical output in kW.
    """
    return np.interp(
        wind_speed, power_curve.iloc[:, 0], power_curve.iloc[:, 1],
        left=0.0, right=0.0,
    )


def powerCurve(wind_turbine_model):
    """Read a packaged turbine power curve by model identifier.

    Parameters
    ----------
    wind_turbine_model : str
        Model identifier used in ``data/energy_systems/WT_<model>.csv``,
        for example ``"Enercon_E40"``.

    Returns
    -------
    pandas.DataFrame
        Power-curve table read from the semicolon-separated CSV, with wind
        speed in m/s in the first column and electrical output in kW.
    """
    power_curve_path = os.path.join(
        PACKAGE_DIR, "data", "energy_systems", "WT_" + wind_turbine_model + ".csv"
    )
    return pd.read_csv(power_curve_path, header=0, delimiter=";")


def WT_generation(array_windSpeed):
    """Calculate an Enercon E40 electrical generation time series.

    Parameters
    ----------
    array_windSpeed : array_like
        One-dimensional sequence of hub-height wind speeds in m/s, ordered
        by time. Speeds outside the tabulated range produce zero output.

    Returns
    -------
    numpy.ndarray
        Electrical power in W at each input time step, shape ``(n_steps,)``.
        The model is fixed to the packaged ``Enercon_E40`` curve; no height
        correction is applied here.
    """
    power_curve = powerCurve("Enercon_E40")
    # Load once for the whole time series and convert the curve's kW to W.
    return get_turbine_power(array_windSpeed, power_curve) * 1000


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
    data : districtgenerator.datahandler.Datahandler
        Full reference-height wind-speed series in m/s under
        ``site["wind_speed"]``.

    Returns
    -------
    WT_power_norm : numpy.ndarray
        Full-series electrical output divided by the curve's 500 kW rating;
        dimensionless.
    WT_power_norm_clustered : numpy.ndarray
        Dimensionless representative-period output.
    """

    power_curve = powerCurve("Enercon_E40")
    wind_settings = devs["WT"]
    height_factor = factor_windSpeed({
        "H": wind_settings["hub_h"],
        "H_ref": wind_settings["ref_h"],
        "alfa": wind_settings["h_coeff"],
    })
    wind_speed_corr = np.asarray(data.site["wind_speed"]) * height_factor
    wind_speed_corr_clustered = np.asarray(param["wind_speed"]) * height_factor

    # Both profiles use the same CSV curve; retain the E40's 500 kW reference rating.
    WT_power_norm = get_turbine_power(wind_speed_corr, power_curve) / 500
    WT_power_norm_clustered = get_turbine_power(wind_speed_corr_clustered, power_curve) / 500
    return WT_power_norm, WT_power_norm_clustered


def interpolate_power_curve(wind_speed, power_curve):
    """Interpolate wind-turbine output from indexed supporting points.

    Parameters
    ----------
    wind_speed : float
        Hub-height speed in m/s, including the final tabulated speed.
    power_curve : dict
        Contiguous integer keys starting at 0, in increasing wind-speed order,
        mapped to ``(wind speed in m/s, electrical power in kW)``. The first
        supporting point must be at zero speed.

    Returns
    -------
    float
        Electrical output in kW.
    """
    power_curve_table = pd.DataFrame([power_curve[k] for k in range(len(power_curve))])
    return get_turbine_power(wind_speed, power_curve_table)
