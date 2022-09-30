# -*- coding: utf-8 -*-
"""
"""

import json
import os
import pandas as pd
import numpy as np


class Envelope():
    """
    Abstract class for envelop component management handling

    Parameters
    ----------
    prj : Project()
        Project() instance of TEASER, contains functions to generate
        archetype buildings
    building_params : dict
        building parameters like construction year, retrofit
    construction_type : string
        building type
    file_path : str
        file path

    Attributes
    ----------
    id :

    construction_year : int
        construction year of the building
    retrofit : string
        retrofit of the building
    usage_short :

    """

    def __init__(self, prj, building_params, construction_type, file_path):
        """
        Constructor of Envelope Class
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

        self.id = building_params["id"]
        self.construction_year = building_params["year"]
        self.construction_type = construction_type
        self.retrofit = building_params["retrofit"]
        self.usage_short = building_params["building"]
        self.file_path = file_path
        self.loadParams()
        self.loadComponentProperties(prj)
        self.loadAreas(prj)

    def loadParams(self):
        """
        load physical and use-specific parameters

        Parameters
        ----------
        physics : json file
            physical and use-specific parameters

        """

        physics = {}
        with open(os.path.join(self.file_path,
                               'physics_data.json')) as json_file:
            jsonData = json.load(json_file)
            for subData in jsonData:
                physics[subData["name"]] = subData["value"]

        self.c_p_air = physics["c_p_air"]  # [J/kgK]
        self.rho_air = physics["rho_air"]  # [kg/m3]

        design_data = {}
        with open(os.path.join(self.file_path,
                               'design_building_data.json')) as json_file:
            jsonData = json.load(json_file)
            for subData in jsonData:
                design_data[subData["name"]] = subData["value"]

        self.T_set_min = design_data["T_set_min"]
        self.ventilationRate = design_data["ventilation_rate"]

    def specificHeatCapacity(self, d, d_iso, density, cp):
        """
        Computation of (specific) heat capacity of each wall-type-surface
        ISO 13786 A.2.4
        Result is in J/m2K

        Parameters
        ----------
        d :

        d_iso :

        density :

        cp :

        Returns
        ----------
        kappa : float
            (specific) heat capacity of each wall-type-surface

        """
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
        mat_id :

        data_class :

        Returns
        ----------

        name : string
            material type
        density : float
            density of the material
        thermal_conduc :
            thermal conductivity
        heat_capac :
            heat capacity
        solar_absorp :
            solar adsorption
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
        Load component-specific material parameters

        Parameters
        ----------
        prj : class
            contains functions to generate archetype buildings

        """

        material_bind = prj.data.material_bind
        element_bind = prj.data.element_bind

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
        self.opaque_ext = ["wall", "roof", "floor"]
        self.opaque = {"wall", "roof", "floor", "intWall", "ceiling",
                       "intFloor"}

        for x in self.attributes:
            x["window"] = []
            x["opaque"] = {}
            for y in self.opaque:
                x["opaque"][y] = []

        # Heat transfer resistances for opaque components
        self.R_se["opaque"]["wall"] = 0.04  # m²K/W ISO 6946 Table 1
        self.R_se["opaque"]["roof"] = 0.04  # m²K/W ISO 6946 Table 1
        self.R_se["opaque"]["floor"] = 0.00  # m²K/W ISO 6946 Table 1

        for x in self.opaque_ext:
            self.R_si["opaque"][x] = 0.13  # m²K/W ISO 6946 Table 1

        # ASHRAE 140 : 2011, Table 5.6 p.19
        self.R_se["window"] = 0.0476  # ASHRAE 140 : 2011, Table 5.6 p.19
        self.R_si["window"] = 0.13  # m²K/W DIN EN ISO 6946:2008-04, Table 1

        # ASHRAE 140 : 2011, Table 5.3, page 18 (infrared emittance)
        for x in self.opaque_ext:
            self.epsilon["opaque"][x] = 0.9
        self.epsilon["window"] = 0.9

        # ASHRAE 140 : 2011, Table 5.3,
        # page 18 (Absorptionskoeffizient opake Fläche)
        for x in self.opaque_ext:
            self.alpha_Sc["opaque"][x] = 0.6

        comp = "wall"
        # WALLS: Materials and U-value
        for name, elem in element_bind.items():
            if "OuterWall" in name:
                if elem["building_age_group"][0] <= self.construction_year <= \
                        elem["building_age_group"][1] and \
                        elem["construction_type"] == self.construction_type \
                        + "_1_" + self.usage_short:
                    for lay in elem["layer"].items():
                        self.d["opaque"][comp] = np.append(self.d[
                                                               "opaque"][comp],
                                                           lay[1]["thickness"])
                        material_prop = self.loadMaterialID(
                            lay[1]["material"]["material_id"], material_bind)
                        self.rho["opaque"][comp] = np.append(self.rho[
                                                                 "opaque"][
                                                                 comp],
                                                             material_prop[1])
                        self.Lambda["opaque"][comp] = np.append(self.Lambda[
                                                                    "opaque"][
                                                                    comp],
                                                                material_prop[
                                                                    2])
                        self.cp["opaque"][comp] = np.append(self.cp[
                                                                "opaque"][
                                                                comp],
                                                            material_prop[
                                                                3] * 1000)

        comp = "roof"
        # ROOF: Materials and U-value
        for name, elem in element_bind.items():
            if "Rooftop" in name:
                if elem["building_age_group"][0] <= self.construction_year <= \
                        elem["building_age_group"][1] and \
                        elem["construction_type"] == self.construction_type \
                        + "_1_" + self.usage_short:
                    for lay in elem["layer"].items():
                        self.d["opaque"][comp] = np.append(self.d[
                                                               "opaque"][comp],
                                                           lay[1]["thickness"])
                        material_prop = self.loadMaterialID(
                            lay[1]["material"]["material_id"], material_bind)
                        self.rho["opaque"][comp] = np.append(self.rho[
                                                                 "opaque"][
                                                                 comp],
                                                             material_prop[1])
                        self.Lambda["opaque"][comp] = np.append(self.Lambda[
                                                                    "opaque"][
                                                                    comp],
                                                                material_prop[
                                                                    2])
                        self.cp["opaque"][comp] = np.append(self.cp[
                                                                "opaque"][
                                                                comp],
                                                            material_prop[
                                                                3] * 1000)

        comp = "floor"
        # FLOOR: Materials and U-value
        for name, elem in element_bind.items():
            if "GroundFloor" in name:
                if elem["building_age_group"][0] <= self.construction_year <= \
                        elem["building_age_group"][1] and \
                        elem["construction_type"] == self.construction_type \
                        + "_1_" + self.usage_short:
                    for lay in elem["layer"].items():
                        self.d["opaque"][comp] = np.append(self.d[
                                                               "opaque"][comp],
                                                           lay[1]["thickness"])
                        material_prop = self.loadMaterialID(
                            lay[1]["material"]["material_id"], material_bind)
                        self.rho["opaque"][comp] = np.append(self.rho[
                                                                 "opaque"][
                                                                 comp],
                                                             material_prop[1])
                        self.Lambda["opaque"][comp] = np.append(self.Lambda[
                                                                    "opaque"][
                                                                    comp],
                                                                material_prop[
                                                                    2])
                        self.cp["opaque"][comp] = np.append(self.cp[
                                                                "opaque"][
                                                                comp],
                                                            material_prop[
                                                                3] * 1000)

        comp = "intWall"
        # INTERNAL WALL: Materials and U-value
        for name, elem in element_bind.items():
            if "InnerWall" in name:
                dummy = min(2015,
                            self.construction_year)  # data available until 2015
                if elem["building_age_group"][0] <= dummy <= \
                        elem["building_age_group"][1] and \
                        elem["construction_type"] == "tabula_standard":
                    for lay in elem["layer"].items():
                        self.d["opaque"][comp] = np.append(self.d[
                                                               "opaque"][comp],
                                                           lay[1]["thickness"])
                        material_prop = self.loadMaterialID(
                            lay[1]["material"]["material_id"], material_bind)
                        self.rho["opaque"][comp] = np.append(self.rho[
                                                                 "opaque"][
                                                                 comp],
                                                             material_prop[1])
                        self.Lambda["opaque"][comp] = np.append(self.Lambda[
                                                                    "opaque"][
                                                                    comp],
                                                                material_prop[
                                                                    2])
                        self.cp["opaque"][comp] = np.append(self.cp[
                                                                "opaque"][
                                                                comp],
                                                            material_prop[
                                                                3] * 1000)

        comp = "ceiling"
        # CEILING: Materials and U-value
        for name, elem in element_bind.items():
            if "Ceiling" in name:
                dummy = min(2015,
                            self.construction_year)  # data available until 2015
                if elem["building_age_group"][0] <= dummy <= \
                        elem["building_age_group"][1] and \
                        elem["construction_type"] == "tabula_standard":
                    for lay in elem["layer"].items():
                        self.d["opaque"][comp] = np.append(self.d[
                                                               "opaque"][comp],
                                                           lay[1]["thickness"])
                        material_prop = self.loadMaterialID(
                            lay[1]["material"]["material_id"], material_bind)
                        self.rho["opaque"][comp] = np.append(self.rho[
                                                                 "opaque"][
                                                                 comp],
                                                             material_prop[1])
                        self.Lambda["opaque"][comp] = np.append(self.Lambda[
                                                                    "opaque"][
                                                                    comp],
                                                                material_prop[
                                                                    2])
                        self.cp["opaque"][comp] = np.append(self.cp[
                                                                "opaque"][
                                                                comp],
                                                            material_prop[
                                                                3] * 1000)

        comp = "intFloor"
        # INTERNAL FLOOR: Materials and U-value
        for name, elem in element_bind.items():
            if "Floor" in name:
                dummy = min(2015,
                            self.construction_year)  # data available until 2015
                if elem["building_age_group"][0] <= dummy <= \
                        elem["building_age_group"][1] and \
                        elem["construction_type"] == "tabula_standard":
                    for lay in elem["layer"].items():
                        self.d["opaque"][comp] = np.append(self.d[
                                                               "opaque"][comp],
                                                           lay[1]["thickness"])
                        material_prop = self.loadMaterialID(
                            lay[1]["material"]["material_id"], material_bind)
                        self.rho["opaque"][comp] = np.append(self.rho[
                                                                 "opaque"][
                                                                 comp],
                                                             material_prop[1])
                        self.Lambda["opaque"][comp] = np.append(self.Lambda[
                                                                    "opaque"][
                                                                    comp],
                                                                material_prop[
                                                                    2])
                        self.cp["opaque"][comp] = np.append(self.cp[
                                                                "opaque"][
                                                                comp],
                                                            material_prop[
                                                                3] * 1000)

        comp = "window"
        # INTERNAL FLOOR: Materials and U-value
        for name, elem in element_bind.items():
            if "Window" in name:
                if elem["building_age_group"][0] <= self.construction_year <= \
                        elem["building_age_group"][1] and \
                        elem["construction_type"] == self.construction_type \
                        + "_1_" + self.usage_short:
                    self.g_gl["window"] = elem["g_value"]
                    for lay in elem["layer"].items():
                        self.d["window"] = np.append(self.d[
                                                         "window"],
                                                     lay[1]["thickness"])
                        material_prop = self.loadMaterialID(
                            lay[1]["material"]["material_id"], material_bind)
                        self.rho["window"] = np.append(self.rho[
                                                           "window"],
                                                       material_prop[1])
                        self.Lambda["window"] = np.append(self.Lambda[
                                                              "window"],
                                                          material_prop[2])
                        self.cp["window"] = np.append(self.cp[
                                                          "window"],
                                                      material_prop[3] * 1000)

        for x in self.opaque:
            self.d_iso["opaque"][x] = sum(self.d["opaque"][x])
        # Compute U and kappa for each component
        for x in self.opaque_ext:
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

    def loadAreas(self, prj):

        """
        Load component-specific area data

        Parameters
        ----------
        prj : class
            contains functions to generate archetype buildings

        """

        self.V = prj.buildings[self.id].volume

        self.A = {}  # in m2
        self.A["f"] = prj.buildings[self.id].net_leased_area

        drct = ("south", "west", "north", "east")
        self.A["opaque"] = {}
        self.A["opaque"]["south"] = prj.buildings[self.id].outer_area[0.0]
        self.A["opaque"]["north"] = prj.buildings[self.id].outer_area[180.0]
        try:
            self.A["opaque"]["west"] = prj.buildings[self.id].outer_area[90.0]
            self.A["opaque"]["east"] = prj.buildings[self.id].outer_area[270.0]
        except KeyError:
            self.A["opaque"]["west"] = 0.0
            self.A["opaque"]["east"] = 0.0

        try:
            self.A["opaque"]["roof"] = prj.buildings[self.id].outer_area[-1]
        except KeyError:
            self.A["opaque"]["roof"] = 1.2 * prj.buildings[
                self.id].outer_area[-2]

        self.A["opaque"]["floor"] = prj.buildings[self.id].outer_area[-2]
        self.A["opaque"]["wall"] = sum(self.A["opaque"][d] for d in drct)

        # Fläche hausinterner Fußboden entspricht Nutzfläche
        self.A["opaque"]["intFloor"] = self.A["f"]
        # Fläche oberste Geschossdecke entspricht Fläche Bodenplatte
        self.A["opaque"]["ceiling"] = self.A["opaque"]["floor"]
        # Annahme 6 durchgehende Wände pro Geschoss (3*N-S, 3*O_W)
        self.A["opaque"]["intWall"] = 1.5 * self.A["opaque"]["wall"]

        self.A["window"] = {}
        self.A["window"]["south"] = prj.buildings[self.id].window_area[0.0]
        self.A["window"]["north"] = prj.buildings[self.id].window_area[180.0]
        try:
            self.A["window"]["west"] = prj.buildings[self.id].window_area[90.0]
            self.A["window"]["east"] = prj.buildings[
                self.id].window_area[270.0]
        except KeyError:
            self.A["window"]["west"] = 0.0
            self.A["window"]["east"] = 0.0

        self.A["window"]["roof"] = 0.0
        self.A["window"]["floor"] = 0.0

        self.A["window"]["sum"] = sum(self.A["window"][d] for d in drct)

    def calcHeatLoad(self, site, method="design"):

        """

        Parameters
        ----------
        site : dict
            information about location and climate conditions
        method : string
            method to calculate heat load
        Returns
        -------

        Q_nHC : float
            heat load

        """

        with open(os.path.join(self.file_path, 'design_weather_data.json')) \
                as json_file:
            jsonData = json.load(json_file)
            for subData in jsonData:
                if subData["Klimazone"] == site["climateZone"]:
                    # outside design temperature in °C
                    T_ne = subData["Theta_e"]
                    # outside average temperature in °C
                    T_me = subData["Theta_e_m"]

        U_TB = 0.05  # [W/m²K] Wärmebrückenzuschlag
        f_g1 = 1.45  # Korrekturfaktor jährliche Schwankung der Außentemperatur
        # Reduction factor
        f_g2 = (self.T_set_min - T_me) / (self.T_set_min - T_ne)
        G_w = 1.0  # influence of ground water neglected

        Q_nHC = (self.A["opaque"]["wall"] * (
                self.U["opaque"]["wall"] + U_TB)
                 + self.A["window"]["sum"] * self.U["window"]
                 + self.A["opaque"]["roof"] * self.U["opaque"]["roof"]
                 + self.A["opaque"]["floor"] * self.U["opaque"]["floor"]
                 * f_g1 * f_g2 * G_w
                 + self.ventilationRate * self.c_p_air * self.rho_air
                 * self.V / 3600) * (self.T_set_min - T_ne)

        return Q_nHC

    def calcNormativeProperties(self, SunRad, internal_gains):

        """

        Parameters
        ----------
        SunRad : array
            solar radiation
        internal_gains :
            internal gains of the building
        """

        if SunRad is None:
            SunRad = []
        self.C_m = sum((self.kappa["opaque"][x]
                        * self.A["opaque"][x]) for x in self.opaque)
        temp = self.C_m / self.A["f"]

        # 5 possible building classes DIN EN ISO 13790
        x = np.zeros(5)
        # upper and lower bounds for classes
        low = [0.0, 95000.0, 137500.0, 212500.0, 315000.0]
        up = [95000.0, 137500.0, 212500.0, 315000.0, 10000000.0]

        for i in range(len(low)):
            if low[i] <= temp <= up[i]:
                x[i] = 1
            else:
                x[i] = 0

        # Constants for calculation of A_m, dependent of building class
        # (DIN EN ISO 13790, section 12.3.1.2, page 81, table 12)
        f_class_values = [2.5, 2.5, 2.5, 3.0, 3.5]
        self.f_class = {"Am": sum(x * f_class_values)}

        # specific heat transfer coefficient
        # (DIN EN ISO 13790, section 7.2.2.2, page 35)
        self.h_is = 3.45  # [W/(m²K)]
        # non-dimensional relation between the area of all indoor surfaces and the
        # effective floor area A["f"]
        # (DIN EN ISO 13790, section 7.2.2.2, page 36)
        self.lambda_at = 4.5
        # specific heat transfer coefficient
        # (DIN EN ISO 13790, section 12.2.2, page 79)
        self.h_ms = 9.1  # [W/(m²K)]

        # Form factor for radiation between the element and the sky
        # (DIN EN ISO 13790, section 11.4.6, page 73)
        # No direct interaction between sun and floor, therefore the
        # corresponding F_r entry is zero.
        self.F_r = {"south": 0.5,
                    "west": 0.5,
                    "north": 0.5,
                    "east": 0.5,
                    "roof": 1.0,
                    "floor": 0.0}

        # %% Internal gains phi_int[W]
        # simulated instead of using DIN EN ISO 13790, Table G.8, page 140
        phi_int = internal_gains

        # heat flow phi_ia [W]
        # (DIN EN ISO 13790, section C2, page 110, eq. C.1)
        self.phi_ia = 0.5 * phi_int

        # thermal transmittance coefficient H_ve [W/K]
        # (DIN EN ISO 13790, section 9.3.1, equation 21, page 49)
        self.H_ve = self.rho_air * self.c_p_air \
                    * self.ventilationRate * self.V / 3600

        # thermal transmittance coefficient H_tr_is [W/K]
        # (DIN EN ISO 13790, section 7.2.2.2, equation 9, page 35)
        self.A_tot = self.lambda_at * self.A["f"]
        self.H_tr_is = self.h_is * self.A_tot

        # shadow coefficient for sunblinds
        # (DIN EN ISO 13790, section 11.4.3, page 71)
        # Assumption : no sunblinds (modelled manually, see below)
        self.F_sh_gl = 1

        # ratio of window-frame
        # (DIN EN ISO 13790, section 11.4.5, page 73)
        self.F_F = 0

        # thermal radiation transfer
        # [kW/(m²*K)] DIN EN ISO 13790, section 11.4.6, page 73
        h_r_factor = 5.0  # W / (m²K)
        self.h_r = {
            ("opaque", "wall"): h_r_factor * np.array(self.epsilon[
                                                          "opaque"]["wall"]),
            ("opaque", "roof"): h_r_factor * np.array(self.epsilon[
                                                          "opaque"]["roof"]),
            ("opaque", "floor"): h_r_factor * np.array(self.epsilon[
                                                           "opaque"]["floor"]),
            "window": h_r_factor * np.array(self.epsilon["window"])}

        # A_m (DIN EN ISO 13790, section 12.3.1.2, page 81, table 12)
        self.A_m = self.f_class["Am"] * self.A["f"]

        # H_tr_w (DIN EN ISO 13790, section 8.3.1, page 44, eq. 18)
        self.H_tr_w = self.A["window"]["sum"] * self.U["window"]

        self.H_tr_ms = self.f_class["Am"] * self.A["f"] * self.h_ms

        # matching coefficient for thermal transmittance coefficient
        # if temperature is unequal to T_e, otherwise = 1
        # Assumption: Constant annual heat flow through ground
        # (ISO 13370 A.5 p 25 eq. A8)
        T_e_mon = 9.71  # monthly mean outside temperature
        T_i_appr = 22.917  # monthly approximated room temperature

        T_i_year = 22.917  # annual mean indoor temperature
        T_e_year = 9.71  # annual mean outside temperature

        # ground p.44 ISO 13790
        # Heating period from October until May (important for T_i_appr)
        self.b_floor = (T_i_year - T_e_year) / (T_i_appr - T_e_mon)

        self.b_tr = {"wall": np.ones(len(SunRad[0])),
                     "roof": np.ones(len(SunRad[0])),
                     "floor": np.zeros(len(SunRad[0]))}
        self.b_tr["floor"][:] = self.b_floor

        # Mean difference between outdoor temperature and
        # the apparent sky-temperature
        # (DIN EN ISO 13790, section 11.4.6,  page 73)
        self.Delta_theta_er = 11  # [K]

        # dictionary for irradiation to imitate sunblinds manually [kW/m²]
        self.I_sol = {}
        directions = ("south", "west", "north", "east", "roof")
        for drct in range(len(directions)):
            self.I_sol[directions[drct]] = SunRad[drct, :].copy()
            self.I_sol["window", directions[drct]] = SunRad[drct, :].copy()

        self.I_sol["floor"] = np.zeros_like(self.I_sol["roof"])
        self.I_sol["window", "floor"] = np.zeros_like(self.I_sol["roof"])

        limit_shut_blinds = 100  # W/m²
        for t in range(len(SunRad[0])):
            for drct3 in range(len(directions)):  # for all directions
                if SunRad[drct3, t] > limit_shut_blinds:
                    self.I_sol["window", directions[drct3]][t] = 0.15 * SunRad[
                        drct3, t].copy()

        # reference variables to reduce code length
        A_j_k = {}
        B_i_k = {}

        direction = ("south", "west", "north", "east", "roof", "floor")
        direction2 = ("wall", "roof", "floor")
        direction3 = ("south", "west", "north", "east")
        direction4 = ("roof", "floor")

        for t in range(len(SunRad[0])):
            # auxiliary variable for walls
            for drct3 in direction3:
                A_j_k[t, drct3] = (self.U["opaque"]["wall"]
                                   * self.R_se["opaque"]["wall"]
                                   * self.A["opaque"][drct3]
                                   * (self.alpha_Sc["opaque"]["wall"]
                                      * self.I_sol[drct3][t]
                                      - self.h_r["opaque", "wall"] * self.F_r[
                                          drct3] * self.Delta_theta_er))

            # auxiliary variable for roof/ceiling
            for drct4 in direction4:
                A_j_k[t, drct4] = (self.U["opaque"][drct4]
                                   * self.R_se["opaque"][drct4]
                                   * self.A["opaque"][drct4]
                                   * (self.alpha_Sc["opaque"][drct4]
                                      * self.I_sol[drct4][t]
                                      - self.h_r["opaque", drct4] * self.F_r[
                                          drct4] * self.Delta_theta_er))

            for drct in direction:
                B_i_k[t, drct] = self.A["window"][drct] \
                                 * (self.g_gl["window"] * (1 - self.F_F)
                                    * self.I_sol["window", drct][t]
                                    * self.F_sh_gl - self.R_se["window"]
                                    * self.U["window"] * self.h_r["window"]
                                    * self.Delta_theta_er * self.F_r[drct])

        phi_sol = {}
        self.phi_m = {}
        self.phi_st = {}
        self.H_tr_em = {}
        for t in range(len(SunRad[0])):
            # heat flow phi_sol [kW]
            # (DIN EN ISO 13790, section 11.3.2, page 67, eq. 43)
            phi_sol[t] = (sum(A_j_k[t, drct3] for drct3 in direction3) +
                          sum(A_j_k[t, drct4] for drct4 in direction4) +
                          sum(B_i_k[t, drct] for drct in direction)
                          )

            # heat flow phi_m [kW]
            # (DIN EN ISO 13790, section C2, page 110, eq. C.2)
            self.phi_m[t] = (self.A_m / self.A_tot * 0.5 * phi_int[t] +
                             1.0 / self.A_tot * self.A["f"] *
                             (sum(
                                 self.f_class["Am"] * A_j_k[t, drct3] for drct3
                                 in direction3)
                              + sum(self.f_class["Am"] * A_j_k[t, drct4] for
                                    drct4 in direction4)
                              + sum(self.f_class["Am"] * B_i_k[t, drct] for
                                    drct in direction)
                              ))

            # heat flow phi_st [kW]
            # (DIN EN ISO 13790, section C2, page 110, eq. C.3)
            self.phi_st[t] = (0.5 * phi_int[t] + phi_sol[t] - self.phi_m[t] -
                              self.H_tr_w / 9.1 / self.A_tot * 0.5 * phi_int[
                                  t] -
                              1.0 / 9.1 / self.A_tot * self.A["window"][
                                  "sum"] *
                              (sum(self.U["window"] * A_j_k[t, drct3] for drct3
                                   in direction3)
                               + sum(self.U["window"] * A_j_k[t, drct4] for
                                     drct4 in direction4)
                               + sum(self.U["window"] * B_i_k[t, drct] for drct
                                     in direction)
                               ))

            # thermal transmittance coefficient H_tr_em [W/K]
            # Simplification: H_tr_em = H_tr_op
            # (DIN EN ISO 13790, section 8.3, page 43)
            self.H_tr_em[t] = sum(self.A["opaque"][drct2]
                                  * self.U["opaque"][drct2] * self.b_tr[drct2][
                                      t]
                                  for drct2 in direction2)
