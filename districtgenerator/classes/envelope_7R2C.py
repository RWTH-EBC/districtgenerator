# -*- coding: utf-8 -*-

import json
import os
import numpy as np
from teaser.project import Project
from .non_residential import GenericNonResidential, NonResidential
import logging

class Surface:
    """Lightweight surface abstraction for VDI6007 aggregation."""

    def __init__(self, name, surface_type, area, opaque_area, glazed_area,
                 u_value, kappa, A1n_t2, A1n_t7, omega_bt,
                 window=None,
                 conv_heat_trans_coef_int=2.5,
                 conv_heat_trans_coef_ext=20.0,
                 rad_heat_trans_coef=5.0,
                 thermal_resistances=None):

        self.name = name
        self.surface_type = surface_type
        self._area = float(area)
        self._opaque_area = float(opaque_area)
        self._glazed_area = float(glazed_area)
        self.u_value = u_value
        self.kappa = kappa
        self._A1n_t2 = A1n_t2
        self._A1n_t7 = A1n_t7
        self.omega_bt = omega_bt
        self.window = window

        # coefficients
        self._conv_heat_trans_coef_int = conv_heat_trans_coef_int
        self._conv_heat_trans_coef_ext = conv_heat_trans_coef_ext
        self.rad_heat_trans_coef = rad_heat_trans_coef

        # use real resistances if provided, otherwise fallback
        if thermal_resistances is not None and len(thermal_resistances) > 0:
            self.thermal_resistances = list(thermal_resistances)
        else:
            self.thermal_resistances = [1 / u_value] if u_value > 0 else [1e15]

    def _VDI6007_surface_params(self, sup, asim):
        """Surface-specific VDI6007 parameters (Section 6.4)."""
        if not isinstance(sup, float):
            raise TypeError(
                f"ERROR surface {self.name} input sup is not a float: sup {sup}"
            )
        if not isinstance(asim, bool):
            raise TypeError(
                f"ERROR surface {self.name} input asim is not a boolean: asim {asim}"
            )

        if sup == 0:
            sup = 1e-7
        rw = sum(self.thermal_resistances) / sup

        R1_t, C1_t = {}, {}

        for a, omega, days in zip(
            [self._A1n_t2, self._A1n_t7],
            [self.omega_bt[0], self.omega_bt[1]],
            ["2", "7"],
        ):
            # Calculate R1
            R1 = (
                1 / sup *
                ((np.real(a[1, 1]) - 1) * np.real(a[0, 1])
                 + np.imag(a[1, 1]) * np.imag(a[0, 1]))
                / ((np.real(a[1, 1]) - 1) ** 2 + (np.imag(a[1, 1])) ** 2)
            )

            # Calculate C1
            if not asim:
                C1 = (
                    sup *
                    ((np.real(a[1, 1]) - 1) ** 2 + (np.imag(a[1, 1])) ** 2)
                    / (
                        omega *
                        (np.real(a[0, 1]) * np.imag(a[1, 1])
                         - (np.real(a[1, 1]) - 1) * np.imag(a[0, 1]))
                    )
                )
            else:
                # asymmetrically loaded (AW)
                C1 = (
                    sup *
                    (1 / (omega * R1 * sup)) *
                    (
                        rw * sup
                        - np.real(a[0, 1]) * np.real(a[1, 1])
                        - np.imag(a[1, 1]) * np.imag(a[0, 1])
                    )
                    / (
                        np.real(a[1, 1]) * np.imag(a[0, 1])
                        - np.real(a[0, 1]) * np.imag(a[1, 1])
                    )
                )

            R1_t[days] = R1
            C1_t[days] = C1

        # Criterion to choose 2-day vs 7-day period
        rr = R1_t["2"] / R1_t["7"]
        cr = C1_t["2"] / C1_t["7"]

        if (rr > 0.99 and cr < 0.95) or (
            (rr < 0.95 and cr < 0.95) and (abs(rr - cr) > 0.3)
        ):
            return R1_t["2"], C1_t["2"]
        else:
            return R1_t["7"], C1_t["7"]

class Envelope:
    """
    Abstract class for envelop component management handling.

    Parameters
    ----------
    prj : Project()
        Project() instance of TEASER, contains functions to generate archetype buildings.
    building_params : dict
        Building parameters like construction year, retrofit.
    construction_data : string
        Building type.
    file_path : str
        File path.

    Attributes
    ----------
    id : int
        ID of the building form the scenario-json-file.
    construction_year : int
        Construction year of the building.
    retrofit : int
        Abbreviations of the retrofit level of the building.
        0: standard; 1: retrofit; 2: advanced retrofit (according to the web-database TABULA).
    usage_short : string
        building types. Possible are:
        SFH: single family house; TH: terraced house; MFH: multifamily house; AB: apartment block.
    """

    def __init__(self, prj, building_params, construction_data, physics, design_building_data, file_path, SIA2024 = None):
        """
        Constructor of Envelope class.

        Returns
        -------
        None.
        """

        self.U = {}
        self.d = {}
        self.d_iso = {}
        self.rho = {}
        self.cp = {}
        self.Lambda = {}
        self.kappa = {}
        self.g_gl = {}
        self.R_se = {}
        self.R_si = {}
        self.epsilon = {}
        self.alpha_Sc = {}

        self.prj = prj
        self.id = building_params["id"]
        self.construction_year = building_params["year"]
        self.construction_data = construction_data
        self.physics = physics
        self.design_building_data = design_building_data
        self.retrofit = building_params["retrofit"]
        self.usage_short = building_params["building"]
        self.is_residential = self.usage_short in {"SFH", "TH", "MFH", "AB"}

        # Initialize SIA class and read data
        self.SIA2024 = SIA2024
        if not self.is_residential:
            self.building_zones = self.SIA2024[self.usage_short]
            self.nwg_config = GenericNonResidential(self.usage_short) # Load configuration for non-residential building.

        self.file_path = file_path
        self.id = int(building_params.get("id_teaser", building_params["id"]))
        self.loadParams()
        self.loadComponentProperties(prj)
        self.loadAreas(prj)
        self.build_surface_list()
        self.setup_ventilation()

    def loadParams(self):
        """
        load physical and use-specific parameters.

        Parameters
        ----------
        physics : json file
            Physical and use-specific parameters.

        Returns
        -------
        None.
        """

        self.c_p_air = self.physics["c_p_air"]  # [J/kgK]
        self.rho_air = self.physics["rho_air"]  # [kg/m3]
        self.T_set_min = self.design_building_data["T_set_min"]
        self.T_set_min_night = self.design_building_data["T_set_min_night"]
        self.T_set_min_free_day = self.design_building_data["T_set_min_free_day"]
        self.T_set_max = self.design_building_data["T_set_max"]
        self.T_set_max_night = self.design_building_data["T_set_max_night"]
        self.ventilationRate = self.design_building_data["ventilation_rate"]
        self.T_bivalent = self.design_building_data["T_bivalent"]
        self.T_heatlimit = self.design_building_data["T_heatlimit"]

    def setup_ventilation(self):
        """
        Calculates ventilation parameters (Airflows, Heat Recovery Efficiency, H_ve)
        and sets them as class attributes.
        Sets: self.eta_temp_vent, self.V_dot, self.V_dot_infiltration
        """
        if self.is_residential:
            V_dot_area = self.ventilationRate * self.V  # m³/h
            V_dot_infiltration = 0
            eta_temp_vent = 0  # Assumption: No heat recovery for residential buildings.
        else: # Non-residential buildings
            # Determine building standard (existing, standard, goal) based on construction year and retrofit level of the building. Based on the SIA2024 categorization.
            if self.construction_year < 1980 and self.retrofit == 0:
                mode = 'existing' # existing
            elif self.retrofit == 2:
                mode = 'goal' # goal
            else:
                mode = 'standard' # standard

            eta_temp_vent = 0
            if self.nwg_config.get_ventilation():
                print("Calculating ventilation parameters for non-residential building based on SIA2024 data and building configuration.")
                # Determine temperature efficiency of ventilation (eta_temp_vent) based on building standard (existing, standard, goal)
                main_zone_name = self.nwg_config.get_main_zone_name()
                for number, data in self.SIA2024.items():
                    zone_name = data.get('Zone_name_GER')
                    if zone_name == main_zone_name: # Main zone determines the ventilation heat recovery efficiency. Can be problematic if main zone has no heat recovery according to SIA2024, but other zones do. Maybe use weighted average of all zones instead?
                        print(data.keys())
                        eta_temp_vent = data['eta_temp_vent'][mode]
                        break

            # Ventilation is sum of required ventilation over all zones
            V_dot_area = 0
            V_dot_infiltration = 0

            for number, data in self.SIA2024.items():
                zone_name = data.get('Zone_name_GER')
                if zone_name:
                    proportion = self.building_zones.get(zone_name, 0)
                    if proportion > 0:
                        zone_area = self.A["f"] * proportion

                        # Ventilation by area
                        q_v_area = data['airFlow_perA_perh'] #m³/(h·m²)
                        V_dot_area += zone_area * q_v_area

                        # Ventilation to balance out Infiltration
                        q_v_infiltration = data['airFlow_infiltration_perA_perh'][mode]
                        V_dot_infiltration += zone_area * q_v_infiltration


        self.eta_temp_vent = eta_temp_vent
        self.V_dot = V_dot_area
        self.V_dot_infiltration = V_dot_infiltration

    def specificHeatCapacity(self, d, d_iso, density, cp):
        """
        Computation of (specific) heat capacity of each wall-type-surface.
        DIN EN ISO 13786:2008-04: Appendix A.2.4: Method of effective thickness
        (latest: DIN EN ISO 13786:2018-04; here it is appendix C.2.4).
        Result is in [J/m²K].

        Parameters
        ----------
        d : array-like
            Thicknesses of the single layers of the wall [m].
        d_iso : float
            Thickness of materials between the considered surface and the first thermal insulation layer [m].
        density : array-like
            Densities of the single layers of the wall [kg/m³].
        cp : array-like
            Specific heat capacities of the single layers of the wall [J/(kg⋅K)].

        Returns
        -------
        kappa : float
            Area-related heat capacity of each wall-type-surface [J/m²K].
        """

        # determine effective thickness
        d_t = min(0.5 * np.sum(d), d_iso, 0.1)

        sum_d_i = d[0]
        i = 0
        kappa = 0
        while sum_d_i <= d_t:
            kappa += d[i] * density[i] * cp[i]
            i += 1
            sum_d_i += d[i]
        else:
            sum_d_i -= d[i]
            d_part = d_t - sum_d_i
            kappa += d_part * density[i] * cp[i]

        return kappa

    def loadMaterialID(self, mat_id, data_class):
        """
        Material loader by id.

        Parameters
        ----------
        mat_id : string
            Material id.
        data_class : ordered dictionary
            Dictionary with material data ordered by material id.

        Returns
        -------
        name : string
            Material type.
        density : float
            Density of the material.
        thermal_conduc : float
            Thermal conductivity.
        heat_capac : float
            Heat capacity.
        solar_absorp : float
            Solar adsorption.
        """

        binding = data_class
        for id, mat in binding.items():

            if id == mat_id:
                name = mat["name"]
                density = mat["density"]
                thermal_conduc = float(mat["thermal_conduc"])
                heat_capac = mat["heat_capac"]
                solar_absorp = mat["solar_absorp"]

        return (name, density, thermal_conduc, heat_capac, solar_absorp)

    def loadComponentProperties(self, prj):
        """
        Load component-specific material parameters.

        Parameters
        ----------
        prj : class
            Contains functions to generate archetype buildings.

        Returns
        -------
        None.
        """

        self.attributes = [
            self.d,
            self.d_iso,
            self.rho,
            self.cp,
            self.Lambda,
            self.U,
            self.kappa,
            self.R_se,
            self.R_si,
            self.epsilon,
            self.alpha_Sc,
            self.g_gl
        ]
        self.opaque_ext = ["wall", "roof", "groundfloor"]
        self.opaque = {"wall", "roof", "groundfloor", "intWall", "ceiling", "intFloor"}

        for x in self.attributes:
            x["window"] = []
            x["opaque"] = {}
            for y in self.opaque:
                x["opaque"][y] = []

        # Heat transfer resistances for opaque components
        self.R_se["opaque"]["wall"] = 0.04  # m²K/W ISO 6946 Table 1
        self.R_se["opaque"]["roof"] = 0.04  # m²K/W ISO 6946 Table 1
        self.R_se["opaque"]["groundfloor"] = 0.00  # m²K/W ISO 6946 Table 1

        for x in self.opaque_ext:
            self.R_si["opaque"][x] = 0.13  # m²K/W ISO 6946 Table 1

        # Internal surfaces
        self.R_si["opaque"]["intWall"] = 0.13  # m²K/W ISO 6946 Table 1
        self.R_se["opaque"]["intWall"] = 0.13  # m²K/W ISO 6946 Table 1

        self.R_si["opaque"]["ceiling"] = 0.13  # m²K/W ISO 6946 Table 1
        self.R_se["opaque"]["ceiling"] = 0.13  # m²K/W ISO 6946 Table 1

        self.R_si["opaque"]["intFloor"] = 0.13  # m²K/W ISO 6946 Table 1
        self.R_se["opaque"]["intFloor"] = 0.13  # m²K/W ISO 6946 Table 1

        # ASHRAE 140 : 2011, Table 5.6 p.19
        self.R_se["window"] = 0.0476  # ASHRAE 140 : 2011, Table 5.6 p.19
        self.R_si["window"] = 0.13  # m²K/W DIN EN ISO 6946:2008-04, Table 1

        # ASHRAE 140 : 2011, Table 5.3, page 18 (infrared emittance)
        for x in self.opaque_ext:
            self.epsilon["opaque"][x] = 0.9
        self.epsilon["window"] = 0.9

        # ASHRAE 140 : 2011, Table 5.3,
        # page 18 (absorption coefficient opaque area)
        for x in self.opaque_ext:
            self.alpha_Sc["opaque"][x] = 0.6

        if isinstance(prj, Project):

            material_bind = prj.data.material_bind
            element_bind = prj.data.element_bind

            comp = "wall"
            # WALLS: Materials and U-value
            for name, elem in element_bind.items():
                if "OuterWall" in name:
                    if elem["building_age_group"][0] <= self.construction_year <= \
                            elem["building_age_group"][1] and elem["construction_data"] == self.construction_data + "_1_" + self.usage_short:

                        for lay in elem["layer"].items():
                            self.d["opaque"][comp] = np.append(self.d["opaque"][comp], lay[1]["thickness"])
                            material_prop = self.loadMaterialID(lay[1]["material"]["material_id"], material_bind)
                            self.rho["opaque"][comp] = np.append(self.rho["opaque"][comp], material_prop[1])
                            self.Lambda["opaque"][comp] = np.append(self.Lambda["opaque"][comp], material_prop[2])
                            self.cp["opaque"][comp] = np.append(self.cp["opaque"][comp], material_prop[3] * 1000)

            comp = "roof"
            # ROOF: Materials and U-value
            for name, elem in element_bind.items():
                if "Rooftop" in name:
                    if elem["building_age_group"][0] <= self.construction_year <= \
                        elem["building_age_group"][1] and elem[
                    "construction_data"] == self.construction_data + "_1_" + self.usage_short:

                        for lay in elem["layer"].items():
                            self.d["opaque"][comp] = np.append(self.d["opaque"][comp], lay[1]["thickness"])
                            material_prop = self.loadMaterialID(lay[1]["material"]["material_id"], material_bind)
                            self.rho["opaque"][comp] = np.append(self.rho["opaque"][comp], material_prop[1])
                            self.Lambda["opaque"][comp] = np.append(self.Lambda["opaque"][comp], material_prop[2])
                            self.cp["opaque"][comp] = np.append(self.cp["opaque"][comp], material_prop[3] * 1000)

            comp = "groundfloor"
            # FLOOR: Materials and U-value
            for name, elem in element_bind.items():
                if "GroundFloor" in name:
                    if elem["building_age_group"][0] <= self.construction_year <= \
                        elem["building_age_group"][1] and elem[
                    "construction_data"] == self.construction_data + "_1_" + self.usage_short:

                        for lay in elem["layer"].items():
                            self.d["opaque"][comp] = np.append(self.d["opaque"][comp], lay[1]["thickness"])
                            material_prop = self.loadMaterialID(lay[1]["material"]["material_id"], material_bind)
                            self.rho["opaque"][comp] = np.append(self.rho["opaque"][comp], material_prop[1])
                            self.Lambda["opaque"][comp] = np.append(self.Lambda["opaque"][comp], material_prop[2])
                            self.cp["opaque"][comp] = np.append(self.cp["opaque"][comp], material_prop[3] * 1000)

            comp = "intWall"
            # INTERNAL WALL: Materials and U-value
            for name, elem in element_bind.items():
                if "InnerWall" in name:
                    dummy = min(2015,
                                self.construction_year)  # data available until 2015
                    if elem["building_age_group"][0] <= dummy <= \
                        elem["building_age_group"][1] and elem["construction_data"] == "tabula_de_standard":

                        for lay in elem["layer"].items():
                            self.d["opaque"][comp] = np.append(self.d["opaque"][comp], lay[1]["thickness"])
                            material_prop = self.loadMaterialID(lay[1]["material"]["material_id"], material_bind)
                            self.rho["opaque"][comp] = np.append(self.rho["opaque"][comp], material_prop[1])
                            self.Lambda["opaque"][comp] = np.append(self.Lambda["opaque"][comp], material_prop[2])
                            self.cp["opaque"][comp] = np.append(self.cp["opaque"][comp], material_prop[3] * 1000)

            comp = "ceiling"
            # CEILING: Materials and U-value
            for name, elem in element_bind.items():
                if "Ceiling" in name:
                    dummy = min(2015,
                                self.construction_year)  # data available until 2015
                    if elem["building_age_group"][0] <= dummy <= \
                        elem["building_age_group"][1] and elem["construction_data"] == "tabula_de_standard":

                        for lay in elem["layer"].items():
                            self.d["opaque"][comp] = np.append(self.d["opaque"][comp], lay[1]["thickness"])
                            material_prop = self.loadMaterialID(lay[1]["material"]["material_id"], material_bind)
                            self.rho["opaque"][comp] = np.append(self.rho["opaque"][comp], material_prop[1])
                            self.Lambda["opaque"][comp] = np.append(self.Lambda["opaque"][comp], material_prop[2])
                            self.cp["opaque"][comp] = np.append(self.cp["opaque"][comp], material_prop[3] * 1000)

            comp = "intFloor"
            # INTERNAL FLOOR: Materials and U-value
            for name, elem in element_bind.items():
                if "Floor" in name and "GroundFloor" not in name:
                    dummy = min(2015,
                                self.construction_year)  # data available until 2015
                    if elem["building_age_group"][0] <= dummy <= \
                        elem["building_age_group"][1] and elem["construction_data"] == "tabula_de_standard":

                        for lay in elem["layer"].items():
                            self.d["opaque"][comp] = np.append(self.d["opaque"][comp], lay[1]["thickness"])
                            material_prop = self.loadMaterialID(lay[1]["material"]["material_id"], material_bind)
                            self.rho["opaque"][comp] = np.append(self.rho["opaque"][comp], material_prop[1])
                            self.Lambda["opaque"][comp] = np.append(self.Lambda["opaque"][comp], material_prop[2])
                            self.cp["opaque"][comp] = np.append(self.cp["opaque"][comp], material_prop[3] * 1000)

            comp = "window"
            # INTERNAL FLOOR: Materials and U-value
            for name, elem in element_bind.items():
                if "Window" in name and elem["building_age_group"][0] <= self.construction_year <= \
                        elem["building_age_group"][1] and elem[
                    "construction_data"] == self.construction_data + "_1_" + self.usage_short:

                    self.g_gl["window"] = elem["g_value"]
                    for lay in elem["layer"].items():
                        self.d["window"] = np.append(self.d["window"],
                                                     lay[1]["thickness"])
                        material_prop = self.loadMaterialID(
                            lay[1]["material"]["material_id"], material_bind)
                        self.rho["window"] = np.append(self.rho["window"],
                                                       material_prop[1])
                        self.Lambda["window"] = np.append(self.Lambda["window"],
                                                          material_prop[2])
                        self.cp["window"] = np.append(self.cp["window"],
                                                      material_prop[3] * 1000)

            for x in self.opaque:
                self.d_iso["opaque"][x] = sum(self.d["opaque"][x])
            # Compute U and kappa for each component
            for x in self.opaque:
                self.kappa["opaque"][x] = self.specificHeatCapacity(
                    self.d["opaque"][x],
                    self.d_iso["opaque"][x],
                    self.rho["opaque"][x],
                    self.cp["opaque"][x]
                )
                self.U["opaque"][x] = 1.0 / (self.R_si["opaque"][x]
                                             + sum(self.d["opaque"][x]
                                                   / self.Lambda["opaque"][x])
                                             + self.R_se["opaque"][x])

            for x in ["intWall", "ceiling", "intFloor"]:
                self.kappa["opaque"][x] = self.specificHeatCapacity(
                    self.d["opaque"][x],
                    self.d_iso["opaque"][x],
                    self.rho["opaque"][x],
                    self.cp["opaque"][x]
                )

            self.U["window"] = min(2.8, (1.0 / (self.R_si["window"]
                                                + sum(self.d["window"]
                                                      / self.Lambda["window"])
                                                + self.R_se["window"])))

            # Adjust the heating set temperature to account for the occupant behavior
            # This is done to account for:
            # - The tendency in poorly insulated buildings (high U-values) for occupants to set lower temperatures to avoid high energy bills,
            # - And the trend in well-insulated modern buildings (low U-values) to maintain higher temperatures for comfort, as the energy demand increase is relatively small,
            # - Only some parts of the building are heated directly, the rest are adjacent rooms which are heated indirectly to 15°C (assumption).
            # Source:
            # Umweltbundesamt (2022). *Realitätsnahe Berechnung des Energiebedarfs – Ad-hoc Papier*. 8. July 2022.
            # Authors: Bernhard von Manteuffel, Markus Offermann (Guidehouse)

            # Adjust the heating set temperature based on the level of insulation of the building, as mentioned in the first two points:
            if self.U["opaque"]["wall"] > 1:
                self.T_set_min = 18
            elif self.U["opaque"]["wall"] < 0.3:
                self.T_set_min = 22
            else:
                self.T_set_min = -5.7143 * self.U["opaque"]["wall"] + 23.714

            # Adjust the heating set temperature based on the area of the heated portion of the building, as mentioned in the third point:
            if self.U["opaque"]["wall"] > 1:
                if prj.buildings[0].type_of_building in {"SingleFamilyHouse", "TerracedHouse"}:
                    self.partially_heated_portion = 0.4
                elif prj.buildings[0].type_of_building in {"MultiFamilyHouse", "ApartmentBlock"}:
                    self.partially_heated_portion = 0.3
            elif self.U["opaque"]["wall"] < 0.3:
                if prj.buildings[0].type_of_building in {"SingleFamilyHouse", "TerracedHouse"}:
                    self.partially_heated_portion = 0.15
                elif prj.buildings[0].type_of_building in {"MultiFamilyHouse", "ApartmentBlock"}:
                    self.partially_heated_portion = 0.10
            else:
                if prj.buildings[0].type_of_building in {"SingleFamilyHouse", "TerracedHouse"}:
                    self.partially_heated_portion = 0.35714 * self.U["opaque"]["wall"] + 0.042857
                elif prj.buildings[0].type_of_building in {"MultiFamilyHouse", "ApartmentBlock"}:
                    self.partially_heated_portion = 0.28571 * self.U["opaque"]["wall"] + 0.014286
            self.T_set_min = 15 * self.partially_heated_portion + self.T_set_min * (1 - self.partially_heated_portion)
            self.T_set_min_night = self.T_set_min - 3 # Source: Umweltbundesamt (2022). *Realitätsnahe Berechnung des Energiebedarfs – Ad-hoc Papier*.


        elif isinstance(prj, NonResidential):
            # Accessing u-values from Non-Residential typology
            self.U["opaque"]["wall"] = prj.parameters["u_aw"]
            self.U["opaque"]["roof"] = prj.parameters["u_d_opak"]
            self.U["opaque"]["groundfloor"] = prj.parameters["u_ug"]
            self.U["window"]  = prj.parameters["u_fen"]
            self.g_gl["window"] = prj.parameters["g_gl_fen"]

    def loadAreas(self, prj):
        """
        Load component-specific area data.

        Parameters
        ----------
        prj : class
            Contains functions to generate archetype buildings.

        Returns
        -------
        None.
        """
        if isinstance(prj, Project):

            self.V = prj.buildings[self.id].volume

            self.A = {}  # in m2
            self.A["f"] = prj.buildings[self.id].thermal_zones[0].area

            drct = ("south", "west", "north", "east")
            self.A["opaque"] = {}
            if not prj.buildings[self.id].type_of_building == "TerracedHouse":
                self.A["opaque"]["north"] = prj.buildings[self.id].thermal_zones[0].outer_walls[0].area        # one external wall
                self.A["opaque"]["south"] = prj.buildings[self.id].thermal_zones[0].outer_walls[2].area
                self.A["opaque"]["east"] = prj.buildings[self.id].thermal_zones[0].outer_walls[1].area
                self.A["opaque"]["west"] = prj.buildings[self.id].thermal_zones[0].outer_walls[3].area
            else:
                self.A["opaque"]["north"] = prj.buildings[self.id].thermal_zones[0].outer_walls[0].area
                self.A["opaque"]["south"] = prj.buildings[self.id].thermal_zones[0].outer_walls[1].area
                self.A["opaque"]["east"] = 0.0
                self.A["opaque"]["west"] = 0.0

            self.A["opaque"]["walls"] = sum(self.A["opaque"][d] for d in drct)                                      # all external walls

            try:
                self.A["opaque"]["roof"] = sum(r.area for r in prj.buildings[self.id].thermal_zones[0].rooftops)   # Roof
            except KeyError:
                self.A["opaque"]["roof"] = 0.0

            self.A["opaque"]["groundfloor"] = sum(r.area for r in prj.buildings[self.id].thermal_zones[0].ground_floors)        # GroundFloor


            self.A["opaque"]["intfloor"] = self.A["opaque"]["groundfloor"]        # one internal Floor
            self.A["opaque"]["intfloors"] = self.A["f"]  - self.A["opaque"]["groundfloor"]  # all internal floors

            self.A["opaque"]["ceiling"] = self.A["opaque"]["intfloor"] # one ceiling
            self.A["opaque"]["ceilings"] = self.A["opaque"]["intfloors"] # all ceilings
            self.A["opaque"]["intWalls"] = sum(r.area for r in prj.buildings[self.id].thermal_zones[0].inner_walls)  # all internal walls

            self.A["window"] = {}
            if not prj.buildings[self.id].type_of_building == "TerracedHouse":
                self.A["window"]["north"] = prj.buildings[self.id].thermal_zones[0].windows[0].area             # one window
                self.A["window"]["south"] = prj.buildings[self.id].thermal_zones[0].windows[2].area
                self.A["window"]["east"] = prj.buildings[self.id].thermal_zones[0].windows[1].area
                self.A["window"]["west"] = prj.buildings[self.id].thermal_zones[0].windows[3].area
            else:
                self.A["window"]["north"] = prj.buildings[self.id].thermal_zones[0].windows[0].area
                self.A["window"]["south"] =prj.buildings[self.id].thermal_zones[0].windows[1].area
                self.A["window"]["east"] = 0.0
                self.A["window"]["west"] = 0.0

            self.A["window"]["roof"] = 0.0
            self.A["window"]["floor"] = 0.0

            self.A["window"]["sum"] = sum(self.A["window"][d] for d in drct)                  # all windows

        elif isinstance(prj, NonResidential):
            self.V = prj.volume

            self.A = {}  # in m2

            self.A["f"] = prj.net_leased_area

            drct = ("south", "west", "north", "east")
            self.A["opaque"] = {}
            self.A["opaque"]["south"] = prj.outer_area["Exterior Facade South"]["area"]
            self.A["opaque"]["north"] = prj.outer_area["Exterior Facade North"]["area"]
            try:
                self.A["opaque"]["west"] = prj.outer_area["Exterior Facade West"]["area"]
                self.A["opaque"]["east"] = prj.outer_area["Exterior Facade East"]["area"]
            except KeyError:
                self.A["opaque"]["west"] = 0.0
                self.A["opaque"]["east"] = 0.0

            try:
                self.A["opaque"]["roof"] = prj.outer_area["Rooftop"]["area"]
            except KeyError:
                self.A["opaque"]["roof"] = 0.0

            self.A["opaque"]["groundfloor"] = prj.outer_area["Ground Floor"]["area"]
            self.A["opaque"]["walls"] = sum(self.A["opaque"][d] for d in drct)

            # Area of internal floor equals usable area
            self.A["opaque"]["intFloor"] = self.A["f"] - self.A["opaque"]["groundfloor"]
            # Area of the highest floor equals area of base plate
            self.A["opaque"]["ceiling"] = self.A["opaque"]["groundfloor"]
            # Assumption: 6 continuous walls per floor (3*N-S, 3*E-W)
            self.A["opaque"]["intWalls"] = 1.5 * self.A["opaque"]["walls"]

            self.A["window"] = {}
            self.A["window"]["south"] = prj.window_area["Window Facade South"]["area"]
            self.A["window"]["north"] = prj.window_area["Window Facade North"]["area"]
            try:
                self.A["window"]["west"] = prj.window_area["Window Facade West"]["area"]
                self.A["window"]["east"] = prj.window_area["Window Facade East"]["area"]
            except KeyError:
                self.A["window"]["west"] = 0.0
                self.A["window"]["east"] = 0.0

            self.A["window"]["roof"] = 0.0
            self.A["window"]["floor"] = 0.0

            self.A["window"]["sum"] = sum(self.A["window"][d] for d in drct)

        else:
            raise TypeError("The provided project is not a TEASER project or a Non-Residential Building Class object.")

    def build_transfer_matrices(self, d, rho, cp, Lambda):
        """Build VDI6007 transfer matrices for a construction given layer data."""
        R = d / Lambda
        C = cp * rho * d
        T_bt = np.array([2, 7])  # days
        omega_bt = 2 * np.pi / (86400 * T_bt)

        Z_t2 = np.zeros((2, 2, len(d)), complex)
        Z_t7 = np.zeros((2, 2, len(d)), complex)

        for i in range(len(d)):
            r, c = R[i], C[i]
            Av = np.zeros((2, 2, 2), complex)
            for om in range(2):
                arg = np.sqrt(0.5 * omega_bt[om] * r * c)
                Av[0, 0, om] = np.cosh(arg) * np.cos(arg) + 1j * np.sinh(arg) * np.sin(arg)
                Av[1, 1, om] = Av[0, 0, om]
                Av[0, 1, om] = (r / (2 * arg)) * (
                        np.cosh(arg) * np.sin(arg) + np.sinh(arg) * np.cos(arg)
                        + 1j * (np.cosh(arg) * np.sin(arg) - np.sinh(arg) * np.cos(arg))
                )
                Av[1, 0, om] = (-arg / r) * (
                        np.cosh(arg) * np.sin(arg) - np.sinh(arg) * np.cos(arg)
                        - 1j * (np.cosh(arg) * np.sin(arg) + np.sinh(arg) * np.cos(arg))
                )
            Z_t2[:, :, i] = Av[:, :, 0]
            Z_t7[:, :, i] = Av[:, :, 1]

        A1n_t2 = Z_t2[:, :, 0]
        A1n_t7 = Z_t7[:, :, 0]
        for i in range(1, len(d)):
            A1n_t2 = np.matmul(A1n_t2, Z_t2[:, :, i])
            A1n_t7 = np.matmul(A1n_t7, Z_t7[:, :, i])

        return A1n_t2, A1n_t7, omega_bt

    def build_surface_list(self):
        """Builds the _surface_list for VDI6007 from Envelope data."""

        # Heat transfer coefficients (ISO 6946)
        CONV_HEAT_TRANS_COEF_INT = {
            "ExtWall": 2.7,
            "Roof": 2.7,
            "GroundFloor": 2.7,
            "IntWall": 2.7,
            "IntCeiling": 1.7,
            "IntFloor": 1.7,
        }

        CONV_HEAT_TRANS_COEF_EXT = {
            "ExtWall": 20.0,
            "Roof": 20.0,
            "GroundFloor": 995.0   # (approx ground coupling)
        }

        RAD_HEAT_TRANS_COEF = 5.0

        self._surface_list = []

        # --- External walls ---
        R_layers = list(self.d["opaque"]["wall"] / self.Lambda["opaque"]["wall"])
        A1n_t2, A1n_t7, omega_bt = self.build_transfer_matrices(
            self.d["opaque"]["wall"],
            self.rho["opaque"]["wall"],
            self.cp["opaque"]["wall"],
            self.Lambda["opaque"]["wall"]
        )
        self._surface_list.append(
            Surface(
                name="ExtWall",
                surface_type="ExtWall",
                area=self.A["opaque"]["walls"],
                opaque_area=self.A["opaque"]["walls"],
                glazed_area=self.A["window"]["sum"],
                u_value=self.U["opaque"]["wall"],
                kappa=self.kappa["opaque"]["wall"],
                A1n_t2=A1n_t2,
                A1n_t7=A1n_t7,
                omega_bt=omega_bt,
                window={
                    "u_value": self.U["window"],
                    "g_value": self.g_gl["window"],
                    "Ri_w": self.R_si["window"],
                    "Rl_w": self.R_se["window"]
                },
                conv_heat_trans_coef_int=CONV_HEAT_TRANS_COEF_INT["ExtWall"],
                conv_heat_trans_coef_ext=CONV_HEAT_TRANS_COEF_EXT["ExtWall"],
                rad_heat_trans_coef=RAD_HEAT_TRANS_COEF,
                thermal_resistances=R_layers
            )
        )

        # --- Roof ---
        R_layers = list(self.d["opaque"]["roof"] / self.Lambda["opaque"]["roof"])
        A1n_t2, A1n_t7, omega_bt = self.build_transfer_matrices(
            self.d["opaque"]["roof"],
            self.rho["opaque"]["roof"],
            self.cp["opaque"]["roof"],
            self.Lambda["opaque"]["roof"]
        )
        self._surface_list.append(
            Surface(
                name="Roof",
                surface_type="Roof",
                area=self.A["opaque"]["roof"],
                opaque_area=self.A["opaque"]["roof"],
                glazed_area=0.0,
                u_value=self.U["opaque"]["roof"],
                kappa=self.kappa["opaque"]["roof"],
                A1n_t2=A1n_t2,
                A1n_t7=A1n_t7,
                omega_bt=omega_bt,
                conv_heat_trans_coef_int=CONV_HEAT_TRANS_COEF_INT["Roof"],
                conv_heat_trans_coef_ext=CONV_HEAT_TRANS_COEF_EXT["Roof"],
                rad_heat_trans_coef=RAD_HEAT_TRANS_COEF,
                thermal_resistances=R_layers
            )
        )

        # --- Ground Floor ---
        R_layers = list(self.d["opaque"]["groundfloor"] / self.Lambda["opaque"]["groundfloor"])
        A1n_t2, A1n_t7, omega_bt = self.build_transfer_matrices(
            self.d["opaque"]["groundfloor"],
            self.rho["opaque"]["groundfloor"],
            self.cp["opaque"]["groundfloor"],
            self.Lambda["opaque"]["groundfloor"]
        )
        self._surface_list.append(
            Surface(
                name="GroundFloor",
                surface_type="GroundFloor",
                area=self.A["opaque"]["groundfloor"],
                opaque_area=self.A["opaque"]["groundfloor"],
                glazed_area=0.0,
                u_value=self.U["opaque"]["groundfloor"],
                kappa=self.kappa["opaque"]["groundfloor"],
                A1n_t2=A1n_t2,
                A1n_t7=A1n_t7,
                omega_bt=omega_bt,
                conv_heat_trans_coef_int=CONV_HEAT_TRANS_COEF_INT["GroundFloor"],
                conv_heat_trans_coef_ext=CONV_HEAT_TRANS_COEF_EXT["GroundFloor"],
                rad_heat_trans_coef=RAD_HEAT_TRANS_COEF,
                thermal_resistances=R_layers
            )
        )

        # --- Internal walls ---
        R_layers = list(self.d["opaque"]["intWall"] / self.Lambda["opaque"]["intWall"])
        A1n_t2, A1n_t7, omega_bt = self.build_transfer_matrices(
            self.d["opaque"]["intWall"],
            self.rho["opaque"]["intWall"],
            self.cp["opaque"]["intWall"],
            self.Lambda["opaque"]["intWall"]
        )
        self._surface_list.append(
            Surface(
                name="IntWall",
                surface_type="IntWall",
                area=self.A["opaque"]["intWalls"],
                opaque_area=self.A["opaque"]["intWalls"],
                glazed_area=0.0,
                u_value=self.U["opaque"]["intWall"],
                kappa=self.kappa["opaque"]["intWall"],
                A1n_t2=A1n_t2,
                A1n_t7=A1n_t7,
                omega_bt=omega_bt,
                conv_heat_trans_coef_int=CONV_HEAT_TRANS_COEF_INT["IntWall"],
                rad_heat_trans_coef=RAD_HEAT_TRANS_COEF,
                thermal_resistances=R_layers
            )
        )

        # --- Ceilings ---
        R_layers = list(self.d["opaque"]["ceiling"] / self.Lambda["opaque"]["ceiling"])
        A1n_t2, A1n_t7, omega_bt = self.build_transfer_matrices(
            self.d["opaque"]["ceiling"],
            self.rho["opaque"]["ceiling"],
            self.cp["opaque"]["ceiling"],
            self.Lambda["opaque"]["ceiling"]
        )
        self._surface_list.append(
            Surface(
                name="Ceiling",
                surface_type="IntCeiling",
                area=self.A["opaque"]["ceilings"],
                opaque_area=self.A["opaque"]["ceilings"],
                glazed_area=0.0,
                u_value=self.U["opaque"]["ceiling"],
                kappa=self.kappa["opaque"]["ceiling"],
                A1n_t2=A1n_t2,
                A1n_t7=A1n_t7,
                omega_bt=omega_bt,
                conv_heat_trans_coef_int=CONV_HEAT_TRANS_COEF_INT["IntCeiling"],
                rad_heat_trans_coef=RAD_HEAT_TRANS_COEF,
                thermal_resistances=R_layers
            )
        )

        # --- Internal floors ---
        R_layers = list(self.d["opaque"]["intFloor"] / self.Lambda["opaque"]["intFloor"])
        A1n_t2, A1n_t7, omega_bt = self.build_transfer_matrices(
            self.d["opaque"]["intFloor"],
            self.rho["opaque"]["intFloor"],
            self.cp["opaque"]["intFloor"],
            self.Lambda["opaque"]["intFloor"]
        )
        self._surface_list.append(
            Surface(
                name="IntFloor",
                surface_type="IntFloor",
                area=self.A["opaque"]["intfloors"],
                opaque_area=self.A["opaque"]["intfloors"],
                glazed_area=0.0,
                u_value=self.U["opaque"]["intFloor"],
                kappa=self.kappa["opaque"]["intFloor"],
                A1n_t2=A1n_t2,
                A1n_t7=A1n_t7,
                omega_bt=omega_bt,
                conv_heat_trans_coef_int=CONV_HEAT_TRANS_COEF_INT["IntFloor"],
                rad_heat_trans_coef=RAD_HEAT_TRANS_COEF,
                thermal_resistances=R_layers
            )
        )

    def calcHeatLoad(self, site, night_setback, method="design"):
        """
        Calculate design (nominal) heat load at norm outside temperature

        Parameters
        ----------
        site : dict
            Information about location and climate conditions.
        night_setback : int
            1 if night setback is used, 0 otherwise
        method : string, optional
            Method to calculate heat load. The default is "design".

        Returns
        -------
        Q_nHC : float
            Heat load.
        """
        H = self._calcTransmissionCoefficients()

        # Correction factor for annual fluctuation of the outdoor temperature (fθann) [DIN/TS 12831-1, 4.3.1]
        f_g1 = 1.45
        # Reduction factor (fix,k) [DIN EN 12831-1, 6.3.2.5 and table 7]
        f_g2 = (self.T_set_min - site["T_me"]) / (self.T_set_min - site["T_ne"])
        # influence of groundwater neglected [DIN/TS 12831-1, 4.3.1]
        G_w = 1.0
        try:
            if method == "design":
                Q_nHC = (H["envelope_air"] + H["vent"] + (H["groundfloor"] * f_g1 * f_g2 * G_w)) * (
                            self.T_set_min - site["T_ne"])
                if night_setback == 1:
                    # Q_hu: Heating-up power (W) to cover the additional load after a night setback,
                    # based on a standard factor (20 W/m² as per DIN/TS 12831)
                    Q_hu = 20 * self.A["f"]
                    Q_nHC += Q_hu

            if method == "bivalent":
                Q_nHC = (H["envelope_air"] + H["vent"] + (H["groundfloor"] * f_g1 * f_g2 * G_w)) * (
                            self.T_set_min - self.T_bivalent)

            if method == "heatlimit":
                Q_nHC = (H["envelope_air"] + H["vent"] + (H["groundfloor"] * f_g1 * f_g2 * G_w)) * (
                            self.T_set_min - self.T_heatlimit)
        except ValueError:
            raise ValueError(
                f"Method '{method}' not implemented for heating load calculation. Use 'design', 'bivalent' or 'heatlimit'.")
        except KeyError as e:
            raise KeyError(f"Missing key in site data: {e}")
        except Exception as e:
            raise Exception(f"An error occurred during heating load calculation: {e}")

        return Q_nHC

    def _calcTransmissionCoefficients(self):
        """
        Calculate transmission heat transfer coefficients.
        Used by both heating and cooling load calculations.

        Returns
        -------
        dict with H_walls, H_window, H_roof, H_groundfloor, H_vent, H_envelope_air, H_total :
            Transmission heat transfer coefficients [W/K]
        """
        # Thermal bridge surcharge for opaque components (categroy A) [table 2, DIN/TS 12831-1]
        U_TB = 0.05  # [W/m²K]

        H = {}
        H["walls"] = self.A["opaque"]["walls"] * (self.U["opaque"]["wall"] + U_TB)
        H["window"] = self.A["window"]["sum"] * (self.U["window"] + U_TB)
        H["roof"] = self.A["opaque"]["roof"] * (self.U["opaque"]["roof"] + U_TB)
        H["groundfloor"] = self.A["opaque"]["groundfloor"] * self.U["opaque"]["groundfloor"]
        H["vent"] = self.rho_air * self.c_p_air/ 3600  * (self.V_dot * (1-self.eta_temp_vent) + self.V_dot_infiltration) # Ventilation heat transfer coefficient (W/K), accounting for heat recovery efficiency
        H["envelope_air"] = H["walls"] + H["window"] + H["roof"]
        H["total"] = H["envelope_air"] + H["groundfloor"] + H["vent"]

        return H

    def calculateHeatCapacity(self, prj=None):
        """
        Compute building effective thermal mass heat capacity C_m [J/K]
        from area-related heat capacities kappa [J/m²K] and areas [m²].

        This is a simple, robust aggregation for the cooling-load storage factor.
        """
        Cm = 0.0

        # External opaque components
        Cm += float(self.kappa["opaque"]["wall"]) * float(self.A["opaque"]["walls"])
        Cm += float(self.kappa["opaque"]["roof"]) * float(self.A["opaque"]["roof"])
        Cm += float(self.kappa["opaque"]["groundfloor"]) * float(self.A["opaque"]["groundfloor"])

        # Internal mass (use the keys that exist in your A-dict)
        Cm += float(self.kappa["opaque"]["intWall"]) * float(self.A["opaque"].get("intWalls", 0.0))
        Cm += float(self.kappa["opaque"]["ceiling"]) * float(self.A["opaque"].get("ceilings", 0.0))
        Cm += float(self.kappa["opaque"]["intFloor"]) * float(self.A["opaque"].get("intfloors", 0.0))

        self.C_m = Cm
        return Cm

    def calcCoolingLoad(self, site, method="design", nb_occ=2):
        """
        Calculate design (nominal) cooling load at design outside temperature
        Compare to SIA2024 or VDI2078 for more details on the method.
        https://cms.sia.ch/de/api/getMedia/941

        Static calculation pyhsically based on VDI 2078 (1996) and DIN EN ISO 13790
        Parameters
        ----------
        site : dict
            Information about location and climate conditions.
            Must contain site["T_design_cooling"] and site["SunRad"]
        method : string, optional
            Method to calculate cooling load. The default is "design".
        nb_occ : int, optional
            Number of occupants. The default is 2.

        Returns
        -------
        Q_nC : float
            Cooling load in W
        """
        if method != "design":
            raise ValueError(f"Method '{method}' currently not implemented for cooling load calculation")

        # 0. Pre-requisites
        if not hasattr(self, 'C_m'):
            self.calculateHeatCapacity(self.prj)

        H = self._calcTransmissionCoefficients()

        # 1. Define Temperatures
        T_e_design = site["T_design_cooling"]  # based on Klima
        T_i = self.T_set_max  # Indoor cooling setpoint, 26°C (Sommerlicher Wärmeschutz (DIN 4108-2))
        T_ground = site.get("T_ground", 18)  # Default 18°C

        # 2. Transmission Heat Gains in W
        # Floor typically reduces load (ground is cooler)
        if T_e_design > T_i:
            Q_trans = (H["walls"] + H["window"] + H["roof"]) * (T_e_design - T_i) + \
                      H["groundfloor"] * (T_ground - T_i)
        else:
            Q_trans = 0

        # 3. Ventilation Sensible Heat Gains in W
        if T_e_design > T_i:
            Q_vent_sensible = H["vent"] * (T_e_design - T_i)
        else:
            Q_vent_sensible = 0

        # 4. Solar Heat Gains in W
        Q_solar = self._calc_solar_load_design()

        # 5. Internal Heat Gains in W (Sensible & Latent)
        Q_internal_sensible, Q_internal_latent = self._calc_internal_loads_design(nb_occ)

        # 6. Ventilation Latent Heat Gains in W (Dehumidification)
        Q_vent_latent = self._calc_latent_ventilation_load(site, T_i)

        # 7. Thermal Mass Reduction (Storage Factor)
        # Time constant for thermal delay in hours (J / W)
        # Approximation of the dynamic storage effect using a static reduction factor.
        #     # While VDI 2078 (2015) prescribes a dynamic simulation (response factors),
        #     # this static approach (based on ISO 13790 / EN 12831 concepts) is sufficient
        #     # for nominal load estimation (sizing).
        tau = self.C_m / H["total"] / 3600
        # Reduction factor f_storage (heuristic formula)
        # High mass -> high tau -> low f_storage -> lower peak load
        f_storage = 1 / (1 + tau / 15)

        # 8. Total Cooling Load in W
        # Convective loads (ventilation) are immediate.
        # Radiative loads (solar, internal) are dampened by f_storage.
        Q_nC = (Q_trans + Q_solar + Q_internal_sensible) * f_storage + \
               Q_vent_sensible + Q_vent_latent + Q_internal_latent

        return max(Q_nC, 0)

    def _calc_solar_load_design(self):
        """Helper to calculate solar gains based on VDI 2078 (Table D.2 for July).
        Conservative estimate for peak summer conditions.
        Returns
        -------
        Q_solar : float
            Solar heat gains in W
        """
        # Assumed maximum solar radiation on different facades at peak summer conditions (July) in (W/m²)
        I_sol_max = {
            "north": 164, "east": 739, "south": 605, "west": 739, "roof": 927
        }

        # g-Value and Frame Factor
        g_value = self.g_gl.get("window", 0.6)
        if isinstance(g_value, (list, np.ndarray)):
            g_value = np.mean(g_value)

        f_frame = getattr(self, "F_F", 0.3)
        fc_value = 1.0  # Shading (1.0 = none)

        Q_solar = 0
        if "window" in self.A:
            for direction in ["north", "east", "south", "west", "roof"]:
                area = self.A["window"].get(direction, 0)
                if area > 0:
                    rad = I_sol_max.get(direction, 0)
                    Q_solar += area * rad * g_value * (1 - f_frame) * fc_value
        else:
            # Fallback: Assume average solar radiation of 600 W/m²
            Q_solar = self.A["window"]["sum"] * 600 * g_value * (1 - f_frame) * fc_value

        return Q_solar

    def _calc_internal_loads_design(self, nb_occ):
        """Helper to calculate sensible and latent internal gains.

        Parameters
        ----------
        nb_occ : int
            Number of occupants.
        Returns
        -------
        Q_internal_sensible : float
            Sensible internal heat gains in W
        Q_internal_latent : float
            Latent internal heat gains in W
        """

        # Standard values: 5-7 W/m² for residential, 10-20 W/m² for offices
        # Includes: Appliances, Lighting, and Sensible heat from persons.
        # Values derived from SIA 2024 / DIN V 18599 standard profiles:
        #
        # - Residential (5 W/m²):
        #   Conservative average for modern apartments.
        #   Accounts for efficient lighting, typical appliance mix, and lower occupancy density.
        #
        # - Office (15 W/m²):
        #   Standard value for office usage. Composition approx.:
        #   ~ 6 W/m² from Persons (Sensible heat at ~15 m²/person)
        #   ~ 9 W/m² from Equipment (Laptops/PC) and Lighting.
        if self.is_residential:
            q_int = 5  # Residential
        else:
            q_int = 15  # Non-Residential

        Q_internal_sensible = q_int * self.A["f"]

        # 2. Latent Heat Gains (Humidity load per person)
        # Assumption: 45 W per person
        # Represents humidity load (perspiration/respiration) relevant for dehumidification.
        # Source: VDI 2078 (Heat emission of human body)
        # - Activity: "Seated / Light work" (Total metabolic rate ~120 W)
        # - Condition: At design room temperature (~24°C - 26°C)
        # - Split: ~75 W Sensible (included in q_int above) / ~45 W Latent
        Q_internal_latent = int(nb_occ) * 45

        return Q_internal_sensible, Q_internal_latent

    def _calc_latent_ventilation_load(self, site, T_i):
        """Helper to calculate latent ventilation heat gains (dehumidification).
        Parameters
        ----------
        site : dict
            Site information including altitude.
        T_i : float
            Indoor temperature in °C.
        Returns
        -------
        Q_vent_latent : float
            Latent ventilation heat gains in W
        """

        # Calculate mean atmospheric pressure based on altitude in Pa based on location
        p_atm = np.mean(site["pressure"])*100

        # Indoor Saturation vapor pressure in Pa - Magnus formula
        p_sat_in = 611.2 * np.exp(17.62 * T_i / (243.12 + T_i))

        # Indoor Humidity ratio in (kg water/kg dry air) at 50% RH (estimation)
        RH_in = 0.5
        x_in = 0.622 * RH_in * p_sat_in / (p_atm - RH_in * p_sat_in)

        # Outdoor Humidity ratio in (kg water/kg dry) air
        # Absolute humidity = 12.5 g/kg (p.118 of VDI 2078 as max value at design conditions)
        x_out = 0.0125

        # Calculate Load
        h_fg = 2500000  # J/kg - latent heat of vaporization
        m_dot_air = self.rho_air * (self.V_dot + self.V_dot_infiltration) / 3600

        if x_out > x_in:
            return m_dot_air * (x_out - x_in) * h_fg

        return 0

    def _VDI6007_params(self, SunRad):
        """Calculates the thermal zone parameters of the VDI 6007.

        Results stored as attributes:
        Araum_tot, Aaw_tot, Araum_opaque, Aaw_opaque,
        R1AW, R1IW, C1AW, C1IW,
        RgesAW, RrestAW,
        RalphaStarIL, RalphaStarAW, RalphaStarIW,
        UA_tot, Htr_op, Htr_w
        """

        alphaStr = 5      # VDI 6007
        alphaKonA = 20    # VDI 6007

        # init aggregators
        R1IW_m, C1IW_m, R_IW = [], [], []
        R1AW_v, C1AW_v, HAW_v, HAF_v = [], [], [], []
        alphaKonAW, alphaKonIW, alphaKonAF = [], [], []
        RalphaStrAW, RalphaStrIW, RalphaStrAF = [], [], []
        AreaAW, AreaAF, AreaIW = [], [], []

        # Reset area attributes
        self.Araum_tot = 0
        self.Aaw_tot = 0
        self.Araum_opaque = 0
        self.Aaw_opaque = 0
        self.ext_wall_opaque_area = 0
        self.ext_wall_glazed_area = 0
        self.ext_roof_area = 0

        # --- loop over available surfaces ---
        for surface in self._surface_list:
            self.Araum_tot += surface._area
            self.Araum_opaque += surface._opaque_area

            if surface.surface_type == "ExtWall":
                self.ext_wall_opaque_area += surface._opaque_area
                self.ext_wall_glazed_area += surface._glazed_area
            if surface.surface_type == "Roof":
                self.ext_roof_area += surface._area

            if surface.surface_type in ["ExtWall", "GroundFloor", "Roof"]:
                self.Aaw_tot += surface._area
                self.Aaw_opaque += surface._opaque_area

                surface_R1, surface_C1 = surface._VDI6007_surface_params(surface._area, asim=True)
                C1AW_v.append(surface_C1)

                # opaque part
                HAW_v.append(surface.u_value * surface._opaque_area)
                alphaKonAW.append(surface._opaque_area * surface._conv_heat_trans_coef_int)
                RalphaStrAW.append(1 / (surface._opaque_area * surface.rad_heat_trans_coef))

                # glazed part
                try:
                    if surface._glazed_area > 1e-5:
                        HAF_v.append(surface.window["u_value"] * surface._glazed_area)
                        alphaKonAF.append(
                            surface._glazed_area * (1.0 / surface.window["Ri_w"] - surface.rad_heat_trans_coef)
                        )
                        RalphaStrAF.append(1 / (surface._glazed_area * surface.rad_heat_trans_coef))
                    else:
                        R_AF_v = 1e15
                        HAF_v.append(0.0)
                        alphaKonAF.append(0.0)
                        RalphaStrAF.append(1e15)
                except (AttributeError, KeyError, TypeError):
                    # no window object or missing keys
                    R_AF_v = 1e15
                    HAF_v.append(0.0)
                    alphaKonAF.append(0.0)
                    RalphaStrAF.append(1e15)

                # wall+glazing parallel resistance
                R1AW_v.append(surface_R1)

                AreaAW.append(surface._opaque_area)
                AreaAF.append(surface._glazed_area)

            elif surface.surface_type in ["IntWall", "IntCeiling", "IntFloor"]:
                surface_R1, surface_C1 = surface._VDI6007_surface_params(surface._area, asim=False)
                R1IW_m.append(surface_R1)
                C1IW_m.append(surface_C1)
                R_IW.append(sum(surface.thermal_resistances))
                alphaKonIW.append(surface._opaque_area * surface._conv_heat_trans_coef_int)
                RalphaStrIW.append(1 / (surface._opaque_area * surface.rad_heat_trans_coef))
                AreaIW.append(surface._area)

            else:
                raise TypeError(f"Surface {surface.name}: unknown type {surface.surface_type}")

        # --- parallel impedances ---
        self.R1AW, self.C1AW = impedence_parallel(np.array(R1AW_v), np.array(C1AW_v))
        self.R1IW, self.C1IW = impedence_parallel(np.array(R1IW_m), np.array(C1IW_m))

        # --- final params ---
        self.RgesAW = 1 / (sum(HAW_v) + sum(HAF_v))
        RalphaKonAW = 1 / (sum(alphaKonAW) + sum(alphaKonAF))
        RalphaKonIW = 1 / sum(alphaKonIW)

        if sum(AreaAW) <= sum(AreaIW):
            RalphaStrAWIW = 1 / (sum(1 / np.array(RalphaStrAW)) + sum(1 / np.array(RalphaStrAF)))
        else:
            RalphaStrAWIW = 1 / sum(1 / np.array(RalphaStrIW))

        self.RrestAW = self.RgesAW - self.R1AW - 1 / (1 / RalphaKonAW + 1 / RalphaStrAWIW)

        RalphaGesAW_A = 1 / (alphaKonA * (sum(AreaAF) + sum(AreaAW)))
        if self.RgesAW < RalphaGesAW_A:
            self.RrestAW = RalphaGesAW_A
            self.R1AW = self.RgesAW - self.RrestAW - 1 / (1 / RalphaKonAW + 1 / RalphaStrAWIW)
            if self.R1AW < 1e-10:
                self.R1AW = 1e-10

        self.RalphaStarIL, self.RalphaStarAW, self.RalphaStarIW = tri2star(RalphaStrAWIW, RalphaKonIW, RalphaKonAW)

        self.UA_tot = sum(HAW_v) + sum(HAF_v)
        self.Htr_op = sum(HAW_v)
        self.Htr_w = sum(HAF_v)

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

        Returns
        -------
        np.ndarray
            Time series of θ_eq [°C].
        """
        T_out = np.asarray(weather["T_e"], dtype=float)
        n = len(T_out)

        F_sh_urban_shading = 1 #Todo: check this shading factor (now we assume no shading)

        # --- longwave radiation ---
        Eatm, Eerd, theta_erd, theta_atm = long_wave_radiation(T_out, weather["ssw"])
        alpha_str_lw = (Eatm + Eerd) / (theta_atm - theta_erd)
        alpha_str_lw[(alpha_str_lw == 0.) & ((theta_atm - theta_erd) == 0)] = 5.

        # --- accumulators ---
        theta_eq_opaque = np.zeros(n, dtype=float)  # opaque parts (walls + roof)
        theta_eq_window = np.zeros(n, dtype=float)  # windows (conduction + LW only)
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
            mask = (I_sol > 200.0) & (T_out > 19.0)
            F_sh_t[mask] = 0.25  # 25% of sun passes

            if ori in ["south", "west", "north", "east"]:
                if s_wall is None:
                    continue

                alpha_a = s_wall._conv_heat_trans_coef_ext + s_wall.rad_heat_trans_coef
                phi = 0.5      #DIN EN ISO 13790 2008-09, section 11.4.6, page 73
                alpha_s = float(self.alpha_Sc["opaque"]["wall"])  # absorptance of the surface
                A_opa = float(self.A["opaque"].get(ori, 0.0))
                U_opa = float(self.U["opaque"]["wall"])
                A_win = float(self.A["window"].get(ori, 0.0))
                U_win = float(self.U["window"])
                g_val = float(self.g_gl.get("window", 0.6))

            elif ori == "roof":
                if s_roof is None:
                    continue
                alpha_a = s_roof._conv_heat_trans_coef_ext + s_roof.rad_heat_trans_coef
                phi = 1.0      #DIN EN ISO 13790 2008-09, section 11.4.6, page 73
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

            # --- per-surface θ_eq contributions ---
            theta_eq_opaque += (T_out + delta_theta_lw + delta_theta_kw) * U_opa * A_opa / self.UA_tot
            theta_eq_window += (T_out + delta_theta_lw) * U_win * A_win / self.UA_tot

            # --- window solar transmission as internal gains ---
            if A_win > 0:
                I_win = I_sol * F_sh_t
                Q_solar_win = I_win * g_val * A_win  # total transmitted [W]
                Q_il_str += Q_solar_win * RAD_FRAC
                Q_il_kon += Q_solar_win * CONV_FRAC

        # --- ground floor (no solar / no sky view) ---
        A_gf = float(self.A["opaque"].get("groundfloor", 0.0))
        if A_gf > 0:
            U_gf = float(self.U["opaque"].get("groundfloor", 0.0))
            T_ground = np.full_like(T_out, np.mean(T_out))
            theta_eq_opaque += T_ground * U_gf * A_gf / self.UA_tot

        # final series
        self.theta_eq_tot = theta_eq_opaque + theta_eq_window
        self.Q_il_str = Q_il_str
        self.Q_il_kon = Q_il_kon
        self.internal_gains = internal_gains

def long_wave_radiation(theta_a, SSW):
    '''Estimation of sky and ground temperatures and longwave radiation from the atmosphere and ground via VDI6007 model:
    theta_a outdoor air temperature [°C]
    SSW factor to count the clear non-clear sky

    Parameters
    ----------
    theta_a : numpy.array
        external temperature [°C]
    SSW : float
        factor to count the clear non-clear sky range 0-1 (1 clear sky)

    Returns
    -------
    tuple
        tupleof np.array:
        irradiance from sky vault,
        irradiance from ground,
        ground equivalent temeprature,
        sky equivalent temeperature

    Raises
    ------
    TypeError
        if not numpy array or floats
    '''

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
    '''Given two vectors (thermal resistances R and thermal
    capacitances C) of length m (number of walls of the same type, ie either
    IW or AW), calculates the equivalent complex thermal resistance Zeq
    according to T_RA (period in days)

    Parameters
    ----------
    R : numpy.array
        numpy.array with the surfaces resistances
    C: numpy.array
        numpy.array with the surfaces capacitances
    T_RA: float
        Reference time (number of days)

    Returns
    -------
    tuple
        tuple of floats: the equivalent resistance anc capacitance

    Raises
    ------
    TypeError
        if not numpy arrays or floats
    '''

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
    '''Transforms three resistances in triangular connection into
    three resistances in star connection

    Parameters
    ----------
    T1 : float
        Resistance 1
    T2: float
        Resistance 2
    T3: float
        Resistance 3

    Returns
    -------
    tuple
        tuple of floats: 3 new resistances (star connection)

    Raises
    ------
    TypeError
        if not or floats
    '''

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