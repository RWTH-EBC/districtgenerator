# -*- coding: utf-8 -*-
"""
Thermal-envelope utilities for the VDI 6007 7R2C building model.

This module defines the :class:`Envelope` and :class:`Surface` classes used to
translate TEASER or non-residential building data into thermal parameters for
a reduced-order VDI 6007 representation. It also provides helper functions for
long-wave radiation and thermal-network aggregation.

The docstrings follow PEP 257 and the NumPy/numpydoc section conventions so
that the API can be rendered consistently by Sphinx-based documentation.
"""

import numpy as np
from teaser.project import Project
from .non_residential import GenericNonResidential, NonResidential
from .envelope_7R2C import Envelope as Envelope_7R2C
import logging

class Envelope(Envelope_7R2C):
    """
    Represent a building envelope with a VDI 6007-based 7R2C thermal model.

    This class extends the :class:`Envelope_7R2C` class to use the FourElement model.
    Therefore, the parameters are required for external and internal walls, roof and floor separately.

    """

    def _VDI6007_params(self):
        """
        Calculate aggregated thermal-zone parameters according to VDI 6007.
        Separates capacities and resistances for Exterior Wall, Roof, Floor, and Internal Wall
        to be compatible with the 4-element (10-node) dynamic solver.
        """

        alphaStr = 5  # VDI 6007 Radiative coefficient
        alphaKonA = 20  # VDI 6007 External convective coefficient

        # Initialize dictionary to hold parameters for each element
        self.elements = {
            "ew": {"C": [], "R1": [], "H_op": [], "H_win": [], "A_op": [], "A_win": [], "alphaKon": [],
                   "RalphaStr": []},
            "r": {"C": [], "R1": [], "H_op": [], "H_win": [], "A_op": [], "A_win": [], "alphaKon": [],
                  "RalphaStr": []},
            "f": {"C": [], "R1": [], "H_op": [], "H_win": [], "A_op": [], "A_win": [], "alphaKon": [],
                  "RalphaStr": []},
            "iw": {"C": [], "R1": [], "H_op": [], "H_win": [], "A_op": [], "A_win": [], "alphaKon": [],
                   "RalphaStr": []}
        }

        # Map surface types to prefix keys
        type_mapping = {
            "ExtWall": "ew",
            "Roof": "r",
            "GroundFloor": "f",
            "IntWall": "iw",
            "IntCeiling": "iw",
            "IntFloor": "iw"
        }

        # Reset area attributes
        self.Araum_tot = 0
        self.A_ew = 0
        self.A_r = 0
        self.A_f = 0
        self.A_iw = 0

        # --- loop over available surfaces ---
        for surface in self._surface_list:
            self.Araum_tot += surface._area

            prefix = type_mapping[surface.surface_type]
            asim = surface.surface_type in ["ExtWall", "GroundFloor", "Roof"]
            surface_R1, surface_C1 = surface._VDI6007_surface_params(surface._area, asim=asim)

            self.elements[prefix]["C"].append(surface_C1)
            self.elements[prefix]["R1"].append(surface_R1)
            self.elements[prefix]["A_op"].append(surface._opaque_area)
            self.elements[prefix]["A_win"].append(surface._glazed_area)

            # Opaque part heat transfer
            self.elements[prefix]["H_op"].append(surface.u_value * surface._opaque_area)
            self.elements[prefix]["alphaKon"].append(surface._opaque_area * surface._conv_heat_trans_coef_int)
            self.elements[prefix]["RalphaStr"].append(1 / (surface._opaque_area * surface.rad_heat_trans_coef))

            # Area accumulators
            if prefix == "ew":
                self.A_ew += surface._area
            elif prefix == "r":
                self.A_r += surface._area
            elif prefix == "f":
                self.A_f += surface._area
            elif prefix == "iw":
                self.A_iw += surface._area

            # Glazed part heat transfer
            if surface.surface_type in ["ExtWall", "Roof"]:
                if surface._glazed_area > 1e-5:
                    self.elements[prefix]["H_win"].append(surface.window["u_value"] * surface._glazed_area)
                    self.elements[prefix]["alphaKon"].append(
                        surface._glazed_area * (1.0 / surface.window["Ri_w"] - surface.rad_heat_trans_coef)
                    )
                    self.elements[prefix]["RalphaStr"].append(
                        1 / (surface._glazed_area * surface.rad_heat_trans_coef))
                else:
                    self.elements[prefix]["H_win"].append(0.0)

        # --- Aggregate parameters for each element ---
        for prefix in ["ew", "r", "f", "iw"]:
            # Parallel Impedances
            if len(self.elements[prefix]["R1"]) > 0:
                R1, C1 = impedence_parallel(np.array(self.elements[prefix]["R1"]),
                                            np.array(self.elements[prefix]["C"]))
            else:
                R1, C1 = 1e15, 0.0  # Dummy values for missing elements

            setattr(self, f"C_{prefix}", C1)
            setattr(self, f"R1_{prefix}", R1)

            # Calculate Rrest (Only for exterior elements)
            if prefix in ["ew", "r", "f"] and sum(self.elements[prefix]["A_op"]) > 0:
                H_tot = sum(self.elements[prefix]["H_op"]) + sum(self.elements[prefix]["H_win"])
                Rges = 1 / H_tot if H_tot > 0 else 1e15

                alphaKon_tot = sum(self.elements[prefix]["alphaKon"])
                RalphaKon = 1 / alphaKon_tot if alphaKon_tot > 0 else 1e15

                RalphaStr = 1 / sum(1 / np.array(self.elements[prefix]["RalphaStr"]))

                Rrest = Rges - R1 - 1 / (1 / RalphaKon + 1 / RalphaStr)

                # Check against minimum exterior resistance
                Area_tot = sum(self.elements[prefix]["A_op"]) + sum(self.elements[prefix]["A_win"])
                RalphaGes_A = 1 / (alphaKonA * Area_tot) if Area_tot > 0 else 1e15

                if Rges < RalphaGes_A:
                    Rrest = RalphaGes_A
                    R1 = Rges - Rrest - 1 / (1 / RalphaKon + 1 / RalphaStr)
                    if R1 < 1e-10: R1 = 1e-10
                    setattr(self, f"R1_{prefix}", R1)

                setattr(self, f"Rrest_{prefix}", Rrest)
            else:
                setattr(self, f"Rrest_{prefix}", 1e15)

            # Store convective and radiative conductances directly (used in the 10-node solver)
            h_conv_int = 2.7 if prefix != "iw" else 1.7  # Derived from _surface_list defaults
            setattr(self, f"h_conv_{prefix}", h_conv_int)
            setattr(self, f"h_rad_{prefix}", 5.0)

        # Global UA Total
        self.UA_tot = sum(
            [sum(self.elements[p]["H_op"]) + sum(self.elements[p]["H_win"]) for p in ["ew", "r", "f"]])

    def calc_theta_eq(self, weather, internal_gains):
        """
        Calculate equivalent external temperature θ_eq [°C] according to VDI 6007.

        Parameters
        ----------
        weather : dict
            Must contain:
              - weather["T_e"] : array of outdoor air temperature [°C]
              - weather["SunRad"] : ndarray with shape (5, n)
                order: [south, west, north, east, roof], unit W/m²
              - weather["ssw"] : array, sky state factor [0–1]
        internal_gains : array-like
            Internal-gain time series

        Returns
        -------
        None.

        """
        T_out = np.asarray(weather["T_e"], dtype=float)
        n = len(T_out)

        F_sh_urban_shading = 1 #Todo: check this shading factor (now we assume no shading)

        # --- longwave radiation ---
        Eatm, Eerd, theta_erd, theta_atm = long_wave_radiation(T_out, weather["ssw"])
        alpha_str_lw = (Eatm + Eerd) / (theta_atm - theta_erd)
        alpha_str_lw[(alpha_str_lw == 0.) & ((theta_atm - theta_erd) == 0)] = 5.

        # --- accumulators ---
        theta_eq_ew_sum = np.zeros(n, dtype=float)
        theta_eq_r_sum = np.zeros(n, dtype=float)
        UA_ew = 0.0
        UA_r = 0.0

        Q_il_str = np.zeros(n, dtype=float)  # radiative solar gains
        Q_il_kon = np.zeros(n, dtype=float)  # convective solar gains

        # radiant/convective split (VDI typical ~60/40)
        RAD_FRAC = 0.60
        CONV_FRAC = 1.0 - RAD_FRAC

        # quick access to surface objects by type (for ext. coeffs)
        surf_by_type = {s.surface_type: s for s in self._surface_list}
        s_wall = surf_by_type.get("ExtWall")
        s_roof = surf_by_type.get("Roof")

        # --- orientations and irradiance ---
        orientations = ["south", "west", "north", "east", "roof"]
        SunRad = np.asarray(weather["SunRad"], dtype=float)  # shape (5, n)

        for i, ori in enumerate(orientations):
            I_sol = SunRad[i, :]  # W/m²
            F_sh_t = np.ones_like(I_sol)
            mask = I_sol > 100.0
            F_sh_t[mask] = 0.15

            if ori in ["south", "west", "north", "east"]:
                if s_wall is None:
                    continue

                alpha_a = s_wall._conv_heat_trans_coef_ext + s_wall.rad_heat_trans_coef
                phi = 0.5
                alpha_s = float(self.alpha_Sc["opaque"]["wall"])
                A_opa = float(self.A["opaque"].get(ori, 0.0))
                U_opa = float(self.U["opaque"]["wall"])
                A_win = float(self.A["window"].get(ori, 0.0))
                U_win = float(self.U["window"])
                g_val = float(self.g_gl.get("window", 0.6))

            elif ori == "roof":
                if s_roof is None:
                    continue
                alpha_a = s_roof._conv_heat_trans_coef_ext + s_roof.rad_heat_trans_coef
                phi = 1.0
                alpha_s = float(self.alpha_Sc["opaque"]["roof"])
                A_opa = float(self.A["opaque"].get("roof", 0.0))
                U_opa = float(self.U["opaque"]["roof"])
                A_win = float(self.A["window"].get("roof", 0.0))
                U_win = float(self.U["window"])
                g_val = float(self.g_gl.get("window", 0.6))
            else:
                continue

            # --- shortwave ---
            delta_theta_kw = I_sol * alpha_s / alpha_a

            # --- longwave ---
            delta_theta_lw = (
                    ((theta_erd - T_out) * (1 - phi) +
                     (theta_atm - T_out) * phi)
                    * alpha_str_lw * 0.9 / (0.93 * alpha_a)
            )

            # --- per-element UA-weighted θ_eq contributions ---
            UA_opa = U_opa * A_opa
            UA_win = U_win * A_win

            if ori in ["south", "west", "north", "east"]:
                UA_ew += UA_opa + UA_win
                theta_eq_ew_sum += (T_out + delta_theta_lw + delta_theta_kw) * UA_opa
                theta_eq_ew_sum += (T_out + delta_theta_lw) * UA_win
            elif ori == "roof":
                UA_r += UA_opa + UA_win
                theta_eq_r_sum += (T_out + delta_theta_lw + delta_theta_kw) * UA_opa
                theta_eq_r_sum += (T_out + delta_theta_lw) * UA_win

            # --- window solar transmission as internal gains ---
            if A_win > 0:
                I_win = I_sol * F_sh_t
                Q_solar_win = I_win * g_val * A_win
                Q_il_str += Q_solar_win * RAD_FRAC
                Q_il_kon += Q_solar_win * CONV_FRAC

        # --- Finalize Series ---
        self.theta_eq_ew = theta_eq_ew_sum / UA_ew if UA_ew > 0 else T_out.copy()
        self.theta_eq_r = theta_eq_r_sum / UA_r if UA_r > 0 else T_out.copy()

        self.Q_il_str = Q_il_str
        self.Q_il_kon = Q_il_kon
        self.internal_gains = internal_gains

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
