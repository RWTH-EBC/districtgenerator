# -*- coding: utf-8 -*-
"""
Script to generate heating and cooling demands according to DIN EN ISO 13790.
"""

from __future__ import division
import numpy as np
import numpy.linalg as linalg


def _solve(A, b):
    return linalg.solve(A, b)


def _calculateNoHeat(zoneParameters, T_e, t_m_previous, dt, timestep):
    """
    Calculate the temperatures (T_op, T_m, T_air, T_s) if neither heating nor
    cooling devices are activated.
    This is necessary to enable a deadband between cooling and heating mode.

    Parameters
    ----------
    zoneParameters : ZoneParameters
        Resistances and capacity
    zoneInputs : ZoneInputs
        External inputs (solar, internal gains, set temperatures)
    T_m_init : float
        Initial temperature of the thermal mass in degree Celsius.
    timestep : integer, optional
        Define which index is relevant (zoneInputs, H_ve)

    Returns
    -------
    T_op : float
        .
    T_m : float
        .
    T_air : float
        .
    T_s : float
        .
    """

    # Note: If not stated differently, all equations, pages and sections
    # refer to DIN EN ISO 13790:2008 (the official German version of
    # ISO 13790:2008).

    # Extract parameters
    H_tr_is = zoneParameters.H_tr_is        # in W/K
    H_tr_ms = zoneParameters.H_tr_ms        # in W/K
    H_tr_w  = zoneParameters.H_tr_w         # in W/K
    H_ve    = zoneParameters.H_ve           # in W/K
    C_m     = zoneParameters.C_m            # in J/K
    H_tr_em = zoneParameters.H_tr_em[0]  # in W/K

    Phi_ia = zoneParameters.phi_ia
    Phi_m  = zoneParameters.phi_m
    Phi_st = zoneParameters.phi_st


    # Initialize A*x = b
    # x: T_m, T_s, T_air (T_i), Q_HC
    A = np.zeros((3,3))
    b = np.zeros(3)

    # Row wise entering
    A[0,0] = H_tr_em + H_tr_ms + C_m / (3600 * dt)
    A[0,1] = - H_tr_ms
    A[1,0] = - H_tr_ms
    A[1,1] = H_tr_ms + H_tr_is + H_tr_w
    A[1,2] = - H_tr_is
    A[2,1] = - H_tr_is
    A[2, 2] = H_ve + H_tr_is

    b[0] = Phi_m[timestep] + H_tr_em * T_e[timestep] + C_m * t_m_previous / (3600 * dt)
    b[1] = Phi_st[timestep] + H_tr_w * T_e[timestep]
    b[2] = Phi_ia[timestep] + H_ve * T_e[timestep]

    # Solve for "x"
    x = _solve(A, b)

    T_i = x[2]
    T_s = x[1]
    T_m = x[0]

    weight = 0.3
    T_op = weight * T_i + (1 - weight) * T_s
    return (T_op, T_m, T_i, T_s)


def _calculateHeat(zoneParameters, T_e, T_set,T_m_init, dt, timestep):
    """
    Calculate the temperatures (Q_HC, T_op, T_m, T_air, T_s) that result when
    reaching a given set temperature T_set.

    Parameters
    ----------
    zoneParameters : ZoneParameters
        Resistances and capacity
    zoneInputs : ZoneInputs
        External inputs (solar, internal gains, set temperatures)
    T_m_init : float
        Initial temperature of the thermal mass in degree Celsius.
    T_set : float
        Set temperature in degree Celsius.
    timestep : integer, optional
        Define which index is relevant (zoneInputs, H_ve)

    Returns
    -------
    Q_HC : float
        Heating (positive) or cooling (negative) load for the current time
        step in Watt.
    T_op : float
        .
    T_m : float
        .
    T_air : float
        .
    T_s : float
        .
    """

    # Note: If not stated differently, all equations, pages and sections
    # refer to DIN EN ISO 13790:2008 (the official German version of
    # ISO 13790:2008).

    # Extract parameters
    H_tr_is = zoneParameters.H_tr_is        # in W/K
    H_tr_ms = zoneParameters.H_tr_ms        # in W/K
    H_tr_w  = zoneParameters.H_tr_w         # in W/K
    H_ve    = zoneParameters.H_ve           # in W/K
    C_m     = zoneParameters.C_m            # in J/K
    H_tr_em = zoneParameters.H_tr_em[0]  # in W/K
    Q_nHC = zoneParameters.heatload  # design (nominal) heat load

    Phi_ia = zoneParameters.phi_ia
    Phi_m  = zoneParameters.phi_m
    Phi_st = zoneParameters.phi_st

    # Initialize A*x = b
    # x: T_m, T_s, T_air (T_i), Q_HC
    A = np.zeros((4,4))
    b = np.zeros(4)

    # Row wise entering
    A[0,0] = H_tr_em + H_tr_ms + C_m / (3600 * dt)
    A[0,1] = - H_tr_ms
    A[1,0] = - H_tr_ms
    A[1,1] = H_tr_ms + H_tr_is + H_tr_w
    A[1,2] = - H_tr_is
    A[2,1] = - H_tr_is
    A[2,2] = H_ve + H_tr_is
    A[2,3] = -1
    A[3,2] = 0.3
    A[3,1] = 1 - A[3,2]

    b[0] = Phi_m[timestep] + H_tr_em * T_e[timestep] + C_m * T_m_init / (3600 * dt)
    b[1] = Phi_st[timestep] + H_tr_w * T_e[timestep]
    b[2] = Phi_ia[timestep] + H_ve * T_e[timestep]
    b[3] = T_set

    # Solve for "x"
    x = _solve(A, b)

    # Linear system of equations to determine T_i, T_s, T_m, Q_HC (in kW)
    T_i  = x[2]
    T_s  = x[1]
    T_m  = x[0]
    Q_HC = x[3]

    # If Q_HC exceeds Q_nHC, re-solve assuming Q_HC = Q_nHC
    if Q_HC > Q_nHC:
        # Remove the row and column corresponding to Q_HC
        A_reduced = A[:3, :3]  # Exclude the last row and column
        b_reduced = b[:3]      # Exclude the last element of b

        # Adjust b to account for Q_HC = Q_nHC
        b_reduced[2] += Q_nHC  # Subtract fixed Q_HC from the third equation

        # Re-solve the system
        x_reduced  =  _solve(A_reduced, b_reduced)  # Exclude Q_HC column and row

        # Update results
        T_i = x_reduced[2]
        T_s = x_reduced[1]
        T_m = x_reduced[0]
        Q_HC = Q_nHC

    weight = 0.3
    T_op = weight * T_i + (1 - weight) * T_s
    return (Q_HC, T_op, T_m, T_i, T_s)


def calc_night_setback(zoneParameters, T_e, calendar, dt, building_type):
    """
    Calculate heating and cooling demand with night setback for residential buildings
    and night set up for non-residential buildings.

    Parameters
    ----------
    zoneParameters : ZoneParameters
        Resistances and capacity
    T_e : ndarray
        External Temperature for each time step in degree Celsius.
    calendar : dict
        Dictionary containing information about heating period and holidays
    dt : float
        Time step in hours
    building_type : str
        Type of the building, e.g. "SFH", "TH", "MFH

    Returns
    -------
    Q_H : ndarray
        Heating load for each time step in Watt.
    Q_C : ndarray
        Cooling load for each time step in Watt.
    T_op : ndarray
        Operative temperature for each time step in degree Celsius.
    T_m : ndarray
        Temperature of the thermal mass for each time step in degree Celsius.
    T_i : ndarray
        Air temperature for each time step in degree Celsius.
    T_s : ndarray
        Surface temperature for each time step in degree Celsius.
    """
    if building_type in {"SFH", "TH", "MFH", "AB"}:
        T_m_init = zoneParameters.T_set_min - 0.5 # [°C] Assumption
    else:
        T_m_init = 16  # [°C] For non-residential buildings, the temperature at the beginning of the year is assumed to be very low since the building wasn't heated during the long holiday

    T_set = zoneParameters.T_set_min # THeatingSet
    T_set_night = zoneParameters.T_set_min_night  # THeatingSet
    T_set_ub = zoneParameters.T_set_max                    # TCoolingSet
    T_set_ub_night = zoneParameters.T_set_max_night  # THeatingSet
    T_set_free_day = zoneParameters.T_set_min_free_day #THeatingSet during non-working days in a non-residential building

    # Extract dates from calendar
    heating_start = calendar["heating_period_start"] # Day of year (0-364)
    heating_end = calendar["heating_period_end"] # Day of year (0-364)
    cooling_start = calendar["cooling_period_start"] # Day of year (0-364)
    cooling_end = calendar["cooling_period_end"] # Day of year (0-364)
    holidays = calendar["holidays"] # List of tuples for holidays

    numberTimesteps = len(T_e)

    # Initialize results
    T_i  = np.zeros(numberTimesteps)
    T_s  = np.zeros(numberTimesteps)
    T_m  = np.zeros(numberTimesteps)
    Q_H = np.zeros(numberTimesteps)
    Q_C = np.zeros(numberTimesteps)
    T_op = np.zeros(numberTimesteps)


    timesteps_per_day = numberTimesteps / 365  # Calculate timesteps per day
    if building_type in {"SFH", "TH", "MFH", "AB"}:
        night_hours = list(range(22, 24)) + list(range(0, 6))  # 22:00 to 05:59 Source: E. Sperber et al. (2024), Turn down your thermostats – A contribution to overcoming the European gas crisis? The example of Germany
    else:
        night_hours = list(range(18, 24)) + list(range(0, 6))  # 18:00 to 05:59

    for t in range(numberTimesteps):

        if t == 0:
            t_m_previous = T_m_init
        else:
            t_m_previous = T_m[t-1]

        # Calculate hour of the day
        day_fraction = (t % timesteps_per_day) / timesteps_per_day
        hour_of_day = int(day_fraction * 24)

        # Calculate current day
        day = t // timesteps_per_day

        # Define if heating or cooling season
        cooling_season = (day in range(cooling_start, cooling_end)) and calendar["consider_cooling_period"]
        # negative because of year ending in heating period
        heating_season = (day not in range(heating_end, heating_start)) and calendar["consider_heating_period"]

        # Compute what happens without heating (deadband)
        (t_op, t_m, t_i, t_s) = _calculateNoHeat(zoneParameters,
                                                 T_e,
                                                 t_m_previous,
                                                 dt,
                                                 timestep=t)

        if building_type in {"SFH", "TH", "MFH", "AB"}:
            # Check if the current hour is nighttime
            if hour_of_day in night_hours:
                current_T_set = T_set_night
                current_T_set_ub = T_set_ub_night
            else:
                current_T_set = T_set
                current_T_set_ub = T_set_ub
            if t_op < current_T_set and heating_season:
                # Compute heat demand
                (q_hc, t_op, t_m, t_i, t_s) = _calculateHeat(zoneParameters,
                                                             T_e,
                                                             current_T_set,
                                                             t_m_previous,
                                                             dt,
                                                             timestep=t)
            elif t_op > current_T_set_ub and cooling_season:
                # Compute cooling demand
                (q_hc, t_op, t_m, t_i, t_s) = _calculateHeat(zoneParameters,
                                                             T_e,
                                                             current_T_set_ub,
                                                             t_m_previous,
                                                             dt,
                                                             timestep=t)
            else:
                # Nothing to do
                q_hc = 0

        else:
            if hour_of_day in night_hours:
                if (day % 7 not in (0, 6) and day not in holidays):
                    current_T_set = T_set_night
                else:
                    current_T_set = T_set_free_day
                current_T_set_ub = T_set_ub_night
            else:
                if (day % 7 not in (0, 6) and day not in holidays):
                    current_T_set = T_set
                else:
                    current_T_set = T_set_free_day
                current_T_set_ub = T_set_ub
            if t_op < current_T_set and heating_season:
                # Compute heat demand
                (q_hc, t_op, t_m, t_i, t_s) = _calculateHeat(zoneParameters,
                                                             T_e,
                                                             current_T_set,
                                                             t_m_previous,
                                                             dt,
                                                             timestep=t)
            elif (t_op > current_T_set_ub and cooling_season and
                (day % 7 not in (0, 6) and
                 day not in holidays)):
                # Compute cooling demand
                (q_hc, t_op, t_m, t_i, t_s) = _calculateHeat(zoneParameters,
                                                             T_e,
                                                             current_T_set_ub,
                                                             t_m_previous,
                                                             dt,
                                                             timestep=t)
            else:
                # Nothing to do
                q_hc = 0


        # Insert results for current time step
        if q_hc >= 0:
            Q_H[t] = q_hc
            Q_C[t] = 0
        elif q_hc < 0:
            Q_C[t] = -1 * q_hc
            Q_H[t] = 0
        T_m[t] = t_m
        T_i[t] = t_i
        T_s[t] = t_s
        T_op[t] = t_op

    return (Q_H, Q_C, T_op, T_m, T_i, T_s)


def calc(zoneParameters, T_e, calendar, dt, building_type):
    """
    """
    if building_type in {"SFH", "TH", "MFH", "AB"}:
        T_m_init = zoneParameters.T_set_min - 0.4 # [°C] Assumption
    else:
        T_m_init = 16  # [°C] For non-residential buildings, the temperature at the beginning of the year is assumed to be very low since the building wasn't heated during the long holiday

    T_set = zoneParameters.T_set_min  # THeatingSet
    T_set_ub = zoneParameters.T_set_max  # TCoolingSet
    T_set_free_day = zoneParameters.T_set_min_free_day #THeatingSet during non-working days in a non-residential building

    numberTimesteps = len(T_e)

    # Extract dates from calendar
    heating_start = calendar["heating_period_start"]  # Day of year (0-364)
    heating_end = calendar["heating_period_end"]  # Day of year (0-364)
    cooling_start = calendar["cooling_period_start"]  # Day of year (0-364)
    cooling_end = calendar["cooling_period_end"]  # Day of year (0-364)
    holidays = calendar["holidays"]  # List of tuples for holidays

    # Initialize results
    T_i = np.zeros(numberTimesteps)
    T_s = np.zeros(numberTimesteps)
    T_m = np.zeros(numberTimesteps)
    Q_H = np.zeros(numberTimesteps)
    Q_C = np.zeros(numberTimesteps)
    T_op = np.zeros(numberTimesteps)

    timesteps_per_day = numberTimesteps / 365  # Calculate timesteps per day

    for t in range(numberTimesteps):

        if t == 0:
            t_m_previous = T_m_init
        else:
            t_m_previous = T_m[t - 1]

        # Calculate current day
        day = t // timesteps_per_day

        # Define cooling season
        # theoretical gleichzeitig
        cooling_season = (day in range(cooling_start, cooling_end)) and calendar["consider_cooling_period"]
        # negative because of year ending in heating period
        heating_season = (day not in range(heating_end, heating_start)) and calendar["consider_heating_period"]

        # Compute what happens without heating (deadband)
        (t_op, t_m, t_i, t_s) = _calculateNoHeat(zoneParameters,
                                                 T_e,
                                                 t_m_previous,
                                                 dt,
                                                 timestep=t)

        if building_type in {"SFH", "TH", "MFH", "AB"}:
            #             if t_op < T_set and (not heating_period or day not in range(heating_end, heating_start)):
            current_T_set = T_set
            current_T_set_ub = T_set_ub
            if t_op < current_T_set and heating_season:
                current_T_set = T_set
                # Compute heat demand
                (q_hc, t_op, t_m, t_i, t_s) = _calculateHeat(zoneParameters,
                                                             T_e,
                                                             current_T_set,
                                                             t_m_previous,
                                                             dt,
                                                             timestep=t)
            elif t_op > current_T_set_ub and cooling_season:
                # Compute cooling demand
                (q_hc, t_op, t_m, t_i, t_s) = _calculateHeat(zoneParameters,
                                                             T_e,
                                                             current_T_set_ub,
                                                             t_m_previous,
                                                             dt,
                                                             timestep=t)
            else:
                # Nothing to do
                q_hc = 0

        else:
            # Non residential buildings
            if (day % 7 not in (0, 6) and day not in holidays):
                current_T_set = T_set
            else:
                current_T_set = T_set_free_day
            current_T_set_ub = T_set_ub

            if (t_op < current_T_set and heating_season):
                # Compute heat demand
                (q_hc, t_op, t_m, t_i, t_s) = _calculateHeat(zoneParameters,
                                                             T_e,
                                                             current_T_set,
                                                             t_m_previous,
                                                             dt,
                                                             timestep=t)
            elif (t_op > current_T_set_ub and cooling_season and
                  (day % 7 not in (0, 6) and
                   day not in holidays)):
                # Compute cooling demand
                (q_hc, t_op, t_m, t_i, t_s) = _calculateHeat(zoneParameters,
                                                             T_e,
                                                             current_T_set_ub,
                                                             t_m_previous,
                                                             dt,
                                                             timestep=t)
            else:
                # Nothing to do
                q_hc = 0

        # Insert results for current time step
        if q_hc >= 0:
            Q_H[t] = q_hc
            Q_C[t] = 0
        elif q_hc < 0:
            Q_C[t] = -1 * q_hc
            Q_H[t] = 0
        T_m[t] = t_m
        T_i[t] = t_i
        T_s[t] = t_s
        T_op[t] = t_op

    return (Q_H, Q_C, T_op, T_m, T_i, T_s)
