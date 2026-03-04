# -*- coding: utf-8 -*-
import os
import numpy as np
from teaser.project import Project
from .non_residential import NonResidential
from typing import Optional, Tuple
import pandas as pd


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
        SFH: single family house; TH: terraced house; MFH: multifamily house; AP: apartment block.
    """

    def __init__(self, prj, building_params, construction_data, physics, design_building_data, file_path, u_values, calcThick, extra):
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

        #AIX HEAT
        self.thick_req = []

        self.prj = prj
        self.id = building_params["id"]
        self.construction_year = building_params["year"]
        self.construction_data = construction_data
        self.physics = physics
        self.design_building_data = design_building_data
        self.retrofit = building_params["retrofit"]
        self.usage_short = building_params["building"]
        self.file_path = file_path
        self.id = int(building_params.get("id_teaser", building_params["id"]))
        self.loadParams()
        self.loadComponentProperties(prj, u_values, calcThick, extra)
        self.loadAreas(prj)

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

    def loadComponentProperties(self, prj, u_values, calcThick, extra=None):
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
        self.opaque_ext = ["wall", "roof", "floor"]
        self.opaque = {"wall", "roof", "floor", "intWall", "ceiling", "intFloor"}

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
                            elem["building_age_group"][1] and \
                            elem["construction_data"] == self.construction_data \
                            + "_1_" + self.usage_short:
                        for lay in elem["layer"].items():
                            self.d["opaque"][comp] = np.append(self.d["opaque"][comp],
                                                               lay[1]["thickness"])
                            material_prop = self.loadMaterialID(
                                lay[1]["material"]["material_id"], material_bind)
                            self.rho["opaque"][comp] = np.append(self.rho["opaque"][comp],
                                                                 material_prop[1])
                            self.Lambda["opaque"][comp] = np.append(self.Lambda["opaque"][comp],
                                                                    material_prop[2])
                            self.cp["opaque"][comp] = np.append(self.cp["opaque"][comp],
                                                                material_prop[3] * 1000)

            comp = "floor"
            # FLOOR: Materials and U-value
            for name, elem in element_bind.items():
                if "GroundFloor" in name:
                    if elem["building_age_group"][0] <= self.construction_year <= \
                            elem["building_age_group"][1] and \
                            elem["construction_data"] == self.construction_data \
                            + "_1_" + self.usage_short:
                        for lay in elem["layer"].items():
                            self.d["opaque"][comp] = np.append(self.d["opaque"][comp],
                                                               lay[1]["thickness"])
                            material_prop = self.loadMaterialID(
                                lay[1]["material"]["material_id"], material_bind)
                            self.rho["opaque"][comp] = np.append(self.rho["opaque"][comp],
                                                                 material_prop[1])
                            self.Lambda["opaque"][comp] = np.append(self.Lambda["opaque"][comp],
                                                                    material_prop[2])
                            self.cp["opaque"][comp] = np.append(self.cp["opaque"][comp],
                                                                material_prop[3] * 1000)

            comp = "intWall"
            # INTERNAL WALL: Materials and U-value
            for name, elem in element_bind.items():
                if "InnerWall" in name:
                    dummy = min(2015,
                                self.construction_year)  # data available until 2015
                    if elem["building_age_group"][0] <= dummy <= \
                            elem["building_age_group"][1] and elem["construction_data"] == "tabula_de_standard":
                        for lay in elem["layer"].items():
                            self.d["opaque"][comp] = np.append(self.d["opaque"][comp],
                                                               lay[1]["thickness"])
                            material_prop = self.loadMaterialID(
                                lay[1]["material"]["material_id"], material_bind)
                            self.rho["opaque"][comp] = np.append(self.rho["opaque"][comp],
                                                                 material_prop[1])
                            self.Lambda["opaque"][comp] = np.append(self.Lambda["opaque"][comp],
                                                                    material_prop[2])
                            self.cp["opaque"][comp] = np.append(self.cp["opaque"][comp],
                                                                material_prop[3] * 1000)

            comp = "ceiling"
            # CEILING: Materials and U-value
            for name, elem in element_bind.items():
                if "Ceiling" in name:
                    dummy = min(2015,
                                self.construction_year)  # data available until 2015
                    if elem["building_age_group"][0] <= dummy <= \
                            elem["building_age_group"][1] and \
                            elem["construction_data"] == "tabula_de_standard":
                        for lay in elem["layer"].items():
                            self.d["opaque"][comp] = np.append(self.d["opaque"][comp],
                                                               lay[1]["thickness"])
                            material_prop = self.loadMaterialID(
                                lay[1]["material"]["material_id"], material_bind)
                            self.rho["opaque"][comp] = np.append(self.rho["opaque"][comp],
                                                                 material_prop[1])
                            self.Lambda["opaque"][comp] = np.append(self.Lambda["opaque"][comp],
                                                                    material_prop[2])
                            self.cp["opaque"][comp] = np.append(self.cp["opaque"][comp],
                                                                material_prop[3] * 1000)

            comp = "intFloor"
            # INTERNAL FLOOR: Materials and U-value
            for name, elem in element_bind.items():
                if "Floor" in name and "GroundFloor" not in name:
                    dummy = min(2015,
                                self.construction_year)  # data available until 2015
                    if elem["building_age_group"][0] <= dummy <= \
                            elem["building_age_group"][1] and \
                            elem["construction_data"] == "tabula_de_standard":
                        for lay in elem["layer"].items():
                            self.d["opaque"][comp] = np.append(self.d["opaque"][comp],
                                                               lay[1]["thickness"])
                            material_prop = self.loadMaterialID(
                                lay[1]["material"]["material_id"], material_bind)
                            self.rho["opaque"][comp] = np.append(self.rho["opaque"][comp],
                                                                 material_prop[1])
                            self.Lambda["opaque"][comp] = np.append(self.Lambda["opaque"][comp],
                                                                    material_prop[2])
                            self.cp["opaque"][comp] = np.append(self.cp["opaque"][comp],
                                                                material_prop[3] * 1000)

            comp = "window"
            # INTERNAL FLOOR: Materials and U-value
            for name, elem in element_bind.items():
                if "Window" in name:
                    if elem["building_age_group"][0] <= self.construction_year <= \
                            elem["building_age_group"][1] and \
                            elem["construction_data"] == self.construction_data \
                            + "_1_" + self.usage_short:
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

            # thermalTransmittanceWindow
            self.U["window"] = min(2.8, (1.0 / (self.R_si["window"]
                                                + sum(self.d["window"]
                                                    / self.Lambda["window"])
                                                + self.R_se["window"])))

            # Base row info
            u_row = {
                "ID": self.id,
            }

            # Add calculated U-values
            # for comparison with given U-values
            u_row.update({
                "wall_calc": self.U["opaque"]["wall"],
                "roof_calc": self.U["opaque"]["roof"],
                "floor_calc": self.U["opaque"]["floor"],
                "window_calc": self.U["window"],
                "age": extra[0],
                "retrofit": extra[1],
                "id": extra[2],
                "type": extra[3]
            })

            # if given u-values (e.g. from platform in example.csv) are provided, update U-values accordingly
            # Mapping: (Index in u_values, Ziel-Dict, Ziel-Key)
            mapping = [
                (0, self.U["opaque"], 'wall'),
                (1, self.U["opaque"], 'roof'),
                (2, self.U["opaque"], 'floor'),
                (3, self.U, 'window')  # Achtung: Hier direkt in self.U
            ]

            for idx, target_dict, key in mapping:
                # Schutz vor IndexError, falls u_values zu kurz ist
                if idx < len(u_values):
                    val = u_values[idx]
                    if val != 0 and not pd.isna(val):
                        target_dict[key] = val

            if calcThick:
                self.thick_req = self.compute_insulation_thickness(self.U['opaque'])
            else:
                self.thick_req = None



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
            self.U["opaque"]["floor"] = prj.parameters["u_ug"]
            self.U["window"]  = prj.parameters["u_fen"]
            self.g_gl["window"] = prj.parameters["g_gl_fen"]

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
            self.U["opaque"]["floor"] = prj.parameters["u_ug"]
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

            self.A["opaque"]["wall"] = sum(self.A["opaque"][d] for d in drct)                                      # all external walls

            try:
                self.A["opaque"]["roof"] = sum(r.area for r in prj.buildings[self.id].thermal_zones[0].rooftops)   # Roof
            except KeyError:
                self.A["opaque"]["roof"] = 0.0

            self.A["opaque"]["floor"] = sum(r.area for r in prj.buildings[self.id].thermal_zones[0].ground_floors)        # GroundFloor


            self.A["opaque"]["intFloor"] = self.A["f"] - self.A["opaque"]["floor"]  # all internal floors
            self.A["opaque"]["ceiling"] = self.A["opaque"]["intFloor"] # all ceilings
            self.A["opaque"]["intWall"] = sum(r.area for r in prj.buildings[self.id].thermal_zones[0].inner_walls)  # all internal walls

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

            self.A["opaque"]["floor"] = prj.outer_area["Ground Floor"]["area"]
            self.A["opaque"]["wall"] = sum(self.A["opaque"][d] for d in drct)

            # Area of internal floor equals usable area
            self.A["opaque"]["intFloor"] = self.A["f"] - self.A["opaque"]["floor"]
            # Area of the highest floor equals area of base plate
            self.A["opaque"]["ceiling"] = self.A["opaque"]["floor"]
            # Assumption: 6 continuous walls per floor (3*N-S, 3*E-W)
            self.A["opaque"]["intWall"] = 1.5 * self.A["opaque"]["wall"]

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


    def compute_insulation_thickness(self, target_U_values, insulation_lambda: float = 0.04):
        """
        Calculates existing thickness and required insulation to meet target U-values.

        Parameters
        ----------
        target_U_values : dict
            U-values per component, e.g. {'wall': 0.24, 'roof': 0.24, 'floor': 0.3}
        insulation_lambda : float
            Thermal conductivity of insulation [W/mK]

        Returns
        -------
        thickness_existing : dict
            Existing component thicknesses [m]
        insulation_needed : dict
            Extra insulation to reach target U-values [m]
        """
        thickness_existing = {}
        insulation_needed = []

        for comp in ['wall', 'roof', 'floor']:
            R_material = sum(self.d['opaque'][comp] / self.Lambda['opaque'][comp])
            R_si = self.R_si['opaque'][comp]
            R_se = self.R_se['opaque'][comp]
            R_total = R_material + R_si + R_se

            thickness_existing[comp] = sum(self.d['opaque'][comp])

            U_target = target_U_values[comp]
            R_target = 1 / U_target if U_target > 0 else float('inf')
            d_ins = (R_target - R_total) * insulation_lambda
            insulation_thickness = max(0, d_ins if d_ins > 0.03 else 0)  # makes sure that the extra insulation is more than 3 cm.

            insulation_needed.append(insulation_thickness)

        return insulation_needed

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
                Q_nHC = (H["envelope_air"] + H["vent"] + (H["floor"] * f_g1 * f_g2 * G_w)) * (self.T_set_min - site["T_ne"])
                if night_setback == 1:
                    # Q_hu: Heating-up power (W) to cover the additional load after a night setback,
                    # based on a standard factor (20 W/m² as per DIN/TS 12831)
                    Q_hu = 20 * self.A["f"]
                    Q_nHC += Q_hu

            if method == "bivalent":
                Q_nHC = (H["envelope_air"] + H["vent"] + (H["floor"] * f_g1 * f_g2 * G_w)) * (self.T_set_min - self.T_bivalent)

            if method == "heatlimit":
                Q_nHC = (H["envelope_air"] + H["vent"] + (H["floor"] * f_g1 * f_g2 * G_w)) * (self.T_set_min - self.T_heatlimit)
        except ValueError:
            raise ValueError(f"Method '{method}' not implemented for heating load calculation. Use 'design', 'bivalent' or 'heatlimit'.")
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
        dict with H_wall, H_window, H_roof, H_floor, H_vent, H_envelope_air, H_total :
            Transmission heat transfer coefficients [W/K]
        """
        # Thermal bridge surcharge for opaque components (categroy A) [table 2, DIN/TS 12831-1]
        U_TB = 0.05  # [W/m²K]

        H = {}
        H["wall"] = self.A["opaque"]["wall"] * (self.U["opaque"]["wall"] + U_TB)
        H["window"] = self.A["window"]["sum"] * (self.U["window"] + U_TB)
        H["roof"] = self.A["opaque"]["roof"] * (self.U["opaque"]["roof"] + U_TB)
        H["floor"] = self.A["opaque"]["floor"] * self.U["opaque"]["floor"]
        H["vent"] = self.ventilationRate * self.c_p_air * self.rho_air * self.V / 3600
        H["envelope_air"] = H["wall"] + H["window"] + H["roof"]
        H["total"] = H["envelope_air"] + H["floor"] + H["vent"]

        return H

    def calcCoolingLoad(self, site, method="design", nb_occ=2):
        """
        Calculate design (nominal) cooling load at design outside temperature
        Compare to SIA2024 or VDI2078 for more details about the method.
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
            Q_trans = (H["wall"] + H["window"] + H["roof"]) * (T_e_design - T_i) + \
                      H["floor"] * (T_ground - T_i)
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
        if self.usage_short in ["SFH", "MFH", "TH", "AB"]:
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
        m_dot_air = self.ventilationRate * self.rho_air * self.V / 3600

        if x_out > x_in:
            return m_dot_air * (x_out - x_in) * h_fg

        return 0

    def calculateHeatCapacity(self, prj):
        if isinstance(prj, Project):
            self.C_m = sum((self.kappa["opaque"][x]
                            * self.A["opaque"][x]) for x in self.opaque)
        elif isinstance(prj, NonResidential):
            # Assumption of thermal heat capacity
            # According to DIN EN ISO 13790:2008-09, S. 81
            # -----------------------------------------------------------------------------------------
            # |   Building Mass   |           Cm [in J/K]                      |
            # -----------------------------------------------------------------------------------------
            # |    Very Light     |         80000 * Am                         |
            # |      Light        |         110000 * Am                        |
            # |      Medium       |         165000 * Am                        |
            # |      Heavy        |         260000 * Am                        |
            # |   Very Heavy      |         370000 * Am                        |
            # -----------------------------------------------------------------------------------------
            # Am is the effective area responsible for the heat capacity
            A_m = sum(self.A["opaque"][x] for x in self.opaque)

            if prj.construction_type == "Tabula":
                self.C_m = 162000 * A_m
            elif prj.construction_type == "Light":
                self.C_m = 110000 * A_m
            elif prj.construction_type == "Medium":
                self.C_m = 165000 * A_m
            elif prj.construction_type == "Heavy":
                self.C_m = 260000 * A_m
            else:
                raise ValueError(
                    f"{prj.construction_type} currently not implemented for calculateHeatCapacity for Non Residential Buildings")

        else:
            raise TypeError(
                f"Currently no method implemented for caluclation of average Heat Capacity for type f{type(prj)}")

        return self.C_m

    def calcNormativeProperties(self, SunRad, internal_gains):
        """
        Calculate normative properties according to DIN EN ISO 13790.

        Parameters
        ----------
        SunRad : array-like
            Solar radiation.
        internal_gains :
            Internal gains of the building.

        Returns
        -------
        None.
        """

        if SunRad is None:
            SunRad = []
        C_m = self.calculateHeatCapacity(self.prj)

        # specific heat transfer coefficient
        # (DIN EN ISO 13790 2008-09, section 7.2.2.2, page 35)
        self.h_is = 3.45  # [W/(m²K)]
        # non-dimensional relation between the area of all indoor surfaces and the
        # effective floor area A["f"]
        # (DIN EN ISO 13790 2008-09, section 7.2.2.2, page 36)
        self.lambda_at = 4.5
        # specific heat transfer coefficient
        # (DIN EN ISO 13790 2008-09, section 12.2.2, page 79)
        self.h_ms = 9.1  # [W/(m²K)]

        # Form factor for radiation between the element and the sky
        # (DIN EN ISO 13790 2008-09, section 11.4.6, page 73)
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
        # (DIN EN ISO 13790 2008-09, section C2, page 110, eq. C.1)
        self.phi_ia = 0.5 * phi_int

        # thermal transmittance coefficient H_ve [W/K]
        # (DIN EN ISO 13790 2008-09, section 9.3.1, equation 21, page 49)
        self.H_ve = self.rho_air * self.c_p_air \
                    * self.ventilationRate * self.V / 3600

        # thermal transmittance coefficient H_tr_is [W/K]
        # (DIN EN ISO 13790 2008-09, section 7.2.2.2, equation 9, page 35)
        self.A_tot = self.lambda_at * self.A["f"]
        self.H_tr_is = self.h_is * self.A_tot

        # shadow coefficient for sun blinds
        # (DIN EN ISO 13790 2008-09, section 11.4.3, page 71)
        # Assumption : no sun blinds (modelled manually, see below)
        self.F_sh_gl = 1

        # ratio of window-frame
        # (DIN EN ISO 13790 2008-09, section 11.4.5, page 73)
        self.F_F = 0

        # thermal radiation transfer
        # [kW/(m²*K)] DIN EN ISO 13790 2008-09, section 11.4.6, page 73
        h_r_factor = 5.0  # W / (m²K)
        self.h_r = {
            ("opaque", "wall"): h_r_factor * np.array(self.epsilon["opaque"]["wall"]),
            ("opaque", "roof"): h_r_factor * np.array(self.epsilon["opaque"]["roof"]),
            ("opaque", "floor"): h_r_factor * np.array(self.epsilon["opaque"]["floor"]),
            "window": h_r_factor * np.array(self.epsilon["window"])}

        # H_tr_w (DIN EN ISO 13790 2008-09, section 8.3.1, page 44, eq. 18)
        self.H_tr_w = self.A["window"]["sum"] * self.U["window"]

        self.H_tr_ms = sum(self.A["opaque"][x] for x in self.opaque) * self.h_ms

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

        # dictionary for irradiation to imitate sun blinds manually [kW/m²]
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
                    self.I_sol["window", directions[drct3]][t] = 0.15 * SunRad[drct3, t].copy()

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
            # Am is the effective area responsible for the heat capacity
            self.A_m = sum(self.A["opaque"][x] for x in self.opaque)

            # heat flow into the thermalmass phi_m [kW]
            # (DIN EN ISO 13790, section C2, page 110, eq. C.2)
            self.phi_m[t] = self.A_m / self.A_tot * (0.5 * phi_int[t] + phi_sol[t])

            # heat flow onto the thermal mass’s surface phi_st [kW]
            # (DIN EN ISO 13790, section C2, page 110, eq. C.3)
            self.phi_st[t] = (1 - self.A_m / self.A_tot - self.H_tr_w / 9.1 / self.A_tot) * (0.5 * phi_int[t] + phi_sol[t])

            # thermal transmittance coefficient H_tr_em [W/K]
            # Simplification: H_tr_em = H_tr_op
            # (DIN EN ISO 13790, section 8.3, page 43)
            self.H_tr_em[t] = sum(self.A["opaque"][drct2]
                                  * self.U["opaque"][drct2] * self.b_tr[drct2][t]
                                  for drct2 in direction2)


