"""
Helpers shared by the VDI 6007 thermal models (7R2C and four elements).
"""
import logging

import numpy as np


def long_wave_radiation(theta_a, SSW):
    """
    Estimate long-wave sky and ground radiation according to VDI 6007.

    Parameters
    ----------
    theta_a : array-like
        Outdoor air temperature in °C.
    SSW : float or array-like
        Sky-state factor between 0 and 1, where 1 represents clear sky. If an
        array is supplied, it must be broadcast-compatible with ``theta_a``.

    Returns
    -------
    Ea : numpy.ndarray
        Atmospheric long-wave irradiance in W/m².
    Ee : numpy.ndarray
        Ground-related long-wave irradiance term in W/m².
    theta_erd : numpy.ndarray
        Equivalent ground temperature in °C.
    theta_atm : numpy.ndarray
        Equivalent sky temperature in °C.
    """

    Ea_1 = 9.9 * 5.671 * 10 ** (-14) * (273.15 + theta_a) ** 6

    alpha_L = 2.30 - 7.37 * 10 ** (-3) * (273.15 + theta_a)
    alpha_M = 2.48 - 8.23 * 10 ** (-3) * (273.15 + theta_a)
    alpha_H = 2.89 - 1.00 * 10 ** (-2) * (273.15 + theta_a)

    Ea = Ea_1 * (1 + (alpha_L + (1 - (1 - SSW) / 3) * alpha_M + ((1 - (1 - SSW) / 3) ** 2) * alpha_H) * (
            (1 - SSW) / 3) ** 2.5)
    Ee = -(0.93 * 5.671 * 10 ** (-8) * (273.15 + theta_a) ** 4 + (1 - 0.93) * Ea)

    theta_erd = ((-Ee / (0.93 * 5.67)) ** 0.25) * 100 - 273.15  # [°C]
    theta_atm = ((Ea / (0.93 * 5.67)) ** 0.25) * 100 - 273.15  # [°C]

    return Ea, Ee, theta_erd, theta_atm


def impedence_parallel(R, C, T_RA=5.):
    """
    Aggregate parallel thermal impedances into one resistance-capacitance pair.

    Given thermal resistances and capacitances for surface groups of the same
    category, the function calculates the equivalent complex impedance at the
    selected reference period and converts it back to an equivalent resistance
    and capacitance.

    Parameters
    ----------
    R : numpy.ndarray
        One-dimensional array of thermal resistances in K/W.
    C : numpy.ndarray
        One-dimensional array of thermal capacitances in J/K.
    T_RA : float, optional
        Reference period in days. The default is 5.0 days.

    Returns
    -------
    R1eq : float
        Equivalent thermal resistance in K/W.
    C1eq : float
        Equivalent thermal capacitance in J/K.
    """

    # Check input data type
    if not isinstance(R, np.ndarray):
        raise TypeError(f'ERROR impedenceParallel function, input R is not a np.array: R {R}')
    if not isinstance(C, np.ndarray):
        raise TypeError(f'ERROR impedenceParallel function, input C is not a np.array: C {C}')
    if not isinstance(T_RA, float):
        raise TypeError(f'ERROR impedenceParallel function, input T_RA is not a float: T_RA {T_RA}')

        # T_RA = 5;       % Period = 5 days
    omega_RA = 2 * np.pi / (86400 * T_RA)
    z = np.zeros(len(R), complex)
    z = (R + 1j / (omega_RA * C))  # vettore delle Z

    Z1eq = 1 / (sum(1 / z))  # Z equivalente

    R1eq = np.real(Z1eq)
    C1eq = +1 / (omega_RA * np.imag(Z1eq))

    # Check output quality

    if R1eq < 0. or C1eq < 0.:
        logging.warning(
            f"WARNING impedenceParallel function, There's something wrong with the calculation, R or C is negative.. R {R1eq}, C {C1eq}")

    return R1eq, C1eq


def tri2star(T1, T2, T3):
    """
    Transform three delta-connected resistances into an equivalent star network.

    Parameters
    ----------
    T1 : float
        First delta resistance.
    T2 : float
        Second delta resistance.
    T3 : float
        Third delta resistance.

    Returns
    -------
    S1 : float
        First star resistance, opposite ``T1`` in the implemented convention.
    S2 : float
        Second star resistance, opposite ``T2`` in the implemented convention.
    S3 : float
        Third star resistance, opposite ``T3`` in the implemented convention.
    """

    # Check input data type
    if not isinstance(T1, float):
        raise TypeError(f'ERROR tri2star function, input T1 is not a float: T1 {T1}')
    if not isinstance(T2, float):
        raise TypeError(f'ERROR tri2star function, input T2 is not a float: T2 {T2}')
    if not isinstance(T3, float):
        raise TypeError(f'ERROR tri2star function, input T3 is not a float: T3 {T3}')

    # Check input data quality

    if T1 < 0. or T2 < 0. or T3 < 0.:
        logging.warning(
            f"WARNING tri2star funtion, There's something wrong with the input, one of them is negative.. T1 {T1}, T2 {T2}, T3 {T3}")

    T_sum = T1 + T2 + T3
    S1 = T2 * T3 / T_sum
    S2 = T1 * T3 / T_sum
    S3 = T2 * T1 / T_sum

    return S1, S2, S3
