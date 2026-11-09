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
from districtgenerator.buildings.typology.non_residential import GenericNonResidential, NonResidential
from districtgenerator.buildings.thermal.model_7r2c.envelope import Envelope as Envelope_7R2C
import logging
from districtgenerator.buildings.thermal.vdi6007_common import impedence_parallel, long_wave_radiation, tri2star

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
