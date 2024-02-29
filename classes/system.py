# -*- coding: utf-8 -*-

import json
import os
import functions.wind_turbines as wind_turbines


class BES:
    """
    Abstract class for design of the building energy system.

    Parameters
    ----------
    file_path : string
        File path to the data directory of the districtgenerator.
    """

    def __init__(self, file_path):
        """
        Constructor of building energy system (BES) class.

        Returns
        -------
        None.
        """

        self.file_path = file_path

    def designECS(self, building, site):
        """
        Design of the building energy system.

        Parameters
        ----------
        building : dictionary
            Information about the building.
        site : dictionary
            Information about location and climatic conditions.
        physics : json file
            Physical and use-specific parameters.
        T_bivalent : float
            Outdoor temperature at which the heating capacity of the
            heat pump can just cover the heat demand of the building.
        T_heatlimit : float
            Max outdoor temperature at which the heat pump generates heat.
        dev : list
            List of possible devices.

        Returns
        -------
        BES : class
             building energy system
        """

        buildingFeatures = building["buildingFeatures"]

        physics = {}
        with open(os.path.join(self.file_path, 'physics_data.json')) as json_file:
            jsonData = json.load(json_file)
            for subData in jsonData:
                physics[subData["name"]] = subData["value"]

        design_data = {}
        with open(os.path.join(self.file_path, 'design_building_data.json')) as json_file:
            jsonData = json.load(json_file)
            for subData in jsonData:
                design_data[subData["name"]] = subData["value"]
        T_bivalent = design_data["T_bivalent"]
        T_heatlimit = design_data["T_heatlimit"]

        with open(os.path.join(self.file_path, 'design_weather_data.json')) as json_file:
            jsonData = json.load(json_file)
            for subData in jsonData:
                if subData["Klimazone"] == site["climateZone"]:
                    T_design = subData["Theta_e"]  # [°C] outside design temperature

        # %% conduct linear interpolation
        # for optimal design at bivalent temperature
        self.design_load = building["heatload"] + building["dhwload"]
        limit_load = building["heatlimit"]

        self.bivalent_load = self.design_load + (limit_load - self.design_load) / (T_heatlimit - T_design) \
                             * (T_bivalent - T_design)

        # Load list of possible devices
        dev = {}
        with open(os.path.join(self.file_path, 'param_dec_devices.json')) as json_file:
            jsonData = json.load(json_file)
            for subData in jsonData:
                dev[subData["abbreviation"]] = {}
                for subsubData in subData["specifications"]:
                    dev[subData["abbreviation"]][subsubData["name"]] = subsubData["value"]

        BES = {}

        # check if heating by grid
        if buildingFeatures["heater"] == "heat_grid":
            BES["heat_grid"] = 1
        else:
            BES["heat_grid"] = 0

        for k in dev.keys():
            BES[k] = {}

            # capacity of boiler (BOI), fuel cell (FC) or combined heat and power (CHP) refers to design heat load
            if k in ("BOI", "FC", "CHP"):
                BES[k] = self.design_load * (buildingFeatures["heater"] == k)

            # heat pump (HP) capacity refers to heat load at bivalent temperature
            if k == "HP":
                BES["HP"] = self.bivalent_load * (buildingFeatures["heater"] == k)

            # electric heating (EH) exists if HP exists
            if k == "EH":
                BES["EH"] = (self.design_load - self.bivalent_load) * (buildingFeatures["heater"] == "HP")

            # thermal energy storage (TES) always exists
            if k == "TES":
                # Factor [l/kW], [Wh = l/kW * kW * g/l * J/(gK) * K / 3600]
                # design refers to DHL
                BES["TES"] = buildingFeatures["f_TES"] \
                             * self.design_load / 1000 \
                             * physics["rho_water"] \
                             * physics["c_p_water"] \
                             * dev["TES"]["T_diff_max"] \
                             / 3600
                if buildingFeatures["heater"] == "heat_grid":
                    BES["TES"] = 0

                    # battery (BAT)
            if k == "BAT":
                # Factor [Wh / W_PV], [Wh = Wh/W * W/m2 * m2]
                # design refers to buildable roof area (0.4 * area)
                BES["BAT"] = buildingFeatures["f_BAT"] \
                             * dev["PV"]["P_nominal"] \
                             * building["envelope"].A["opaque"]["roof"] \
                             * buildingFeatures["f_PV"] \
                             * buildingFeatures["BAT"]

            # electric vehicle (EV)
            if k == "EV":
                # [Wh]
                BES["EV"] = float(buildingFeatures["EV"]
                                  * (40000 * (buildingFeatures["f_EV"] == "S")
                                     + 60000 * (buildingFeatures["f_EV"] == "M")
                                     + 80000 * (buildingFeatures["f_EV"] == "L")
                                     )
                                  )

            # photovoltaic (PV)
            if k == "PV":
                BES["PV"] = {}
                areaPV_temp = building["envelope"].A["opaque"]["roof"] \
                              * buildingFeatures["f_PV"] \
                              * buildingFeatures["PV"]
                BES["PV"]["nb_modules"] = int(areaPV_temp / dev["PV"]["area_real"])  # [-]
                BES["PV"]["area"] = BES["PV"]["nb_modules"] * dev["PV"]["area_real"]  # [m²]
                BES["PV"]["P_ref"] = BES["PV"]["area"] * dev["PV"]["P_nominal"]  # [W]

            # solar thermal energy (STC)
            if k == "STC":
                BES["STC"] = {}
                BES["STC"]["area"] = building["envelope"].A["opaque"]["roof"] \
                                     * buildingFeatures["f_STC"] \
                                     * buildingFeatures["STC"]

        return BES


class CES:
    """
    Abstract class for design of the central energy system.
    """

    def __init__(self):
        """
        Constructor of central energy system (CES) class.

        Returns
        -------
        None.
        """

        self.central_design_load = 0
        self.central_bivalent_load = 0

        self.roofAreaDistrict = 0

    def add_loads(self, bes_obj):
        """
        Add loads of building, that is provided with heat by the central devices, to cumulated sum.

        Parameters
        ----------
        bes_obj : building energy system (BES) object
            BES-object contains the loads.

        Returns
        -------
        None.
        """

        self.central_design_load += bes_obj.design_load  # [W]
        self.central_bivalent_load += bes_obj.bivalent_load  # [W]

    def add_roofArea(self, building):
        """
        Add roof area of building to roof area of district.

        Parameters
        ----------
        building : dictionary
            Contains envelope-object with roof area of building.

        Returns
        -------
        None.
        """

        self.roofAreaDistrict += building["envelope"].A["opaque"]["roof"]

    def designCES(self, infos_centralDevices, data_centralDevices):
        """
        Dimensioning of central devices.

        Parameters
        ----------
        infos_centralDevices : pandas DataFrame
            Information about central devices.
        data_centralDevices : dictionary
            Data of central devices.

        Returns
        -------
        capacities_centralDevices : dictionary
            The capacities of the central devices.
        """

        '''
        Information to the used factors:
        f_heat is defined for HP_air, HP_geo, BOI, CHP and FC
        f_heat is the ratio between the heat output of these devices and the design load of the heat grid
        f for STC is the ratio between the area of the central STCs and the roof area of the hole district
        f for PV is the ratio between the area of the central PV modules and the roof area of the hole district
        f for WT is the ratio between the nominal power of the central WT and a central PV system using all roof area
        f for TES is equal to the hours a fully charged central TES can provide the design load of the heat grid 
        f for BAT is equal to the hours a fully charged central BAT can provide the design load of a central PV with an 
            area equal to the sum of all roofs
        '''

        # initialise capacities of central devices
        capacities_centralDevices = {}

        # %% dimensioning of all central devices with heat output
        # air heat pump and electric heating
        capacities_centralDevices["HP_air"] = \
            infos_centralDevices.loc[infos_centralDevices["type"] == "HP_air", ["f_heat"]].iloc[0, 0] # [W]

        # geo-thermal heat pump
        capacities_centralDevices["HP_geo"] = \
            infos_centralDevices.loc[infos_centralDevices["type"] == "HP_geo", ["f_heat"]].iloc[0, 0] # [W]

        capacities_centralDevices["EH"] = \
            infos_centralDevices.loc[infos_centralDevices["type"] == "HP_air", ["f_heat"]].iloc[0, 0] # [W]

        # BOI
        capacities_centralDevices["BOI"] = \
            infos_centralDevices.loc[infos_centralDevices["type"] == "BOI", ["f_heat"]].iloc[0, 0] # [W]

        # combined heat and power (CHP)
        capacities_centralDevices["CHP"] = \
            infos_centralDevices.loc[infos_centralDevices["type"] == "CHP", ["f_heat"]].iloc[0, 0] # [W]

        # fuel cell (FC)
        capacities_centralDevices["FC"] = \
            infos_centralDevices.loc[infos_centralDevices["type"] == "FC", ["f_heat"]].iloc[0, 0] # [W]

        # solar thermal energy (STC)
        capacities_centralDevices["STC"] = {}
        capacities_centralDevices["STC"]["area"] = \
            infos_centralDevices.loc[infos_centralDevices["type"] == "STC", ["f"]].iloc[0, 0] \
            * self.roofAreaDistrict  # [m²]

        # %% dimensioning of all central devices with only electrical output

        # photovoltaic (PV)
        capacities_centralDevices["PV"] = {}
        areaPV_temp = infos_centralDevices.loc[infos_centralDevices["type"] == "PV", ["f"]].iloc[0, 0] \
                      * self.roofAreaDistrict  # [m²]
        capacities_centralDevices["PV"]["nb_modules"] = int(areaPV_temp / data_centralDevices["PV"]["area_real"])  # [-]
        capacities_centralDevices["PV"]["area"] = capacities_centralDevices["PV"]["nb_modules"] \
                                                  * data_centralDevices["PV"]["area_real"]  # [m²]
        capacities_centralDevices["PV"]["P_ref"] = capacities_centralDevices["PV"]["area"] \
                                                   * data_centralDevices["PV"]["P_nominal"]  # [W]
        nb_modulesPV_roof_max = int(self.roofAreaDistrict / data_centralDevices["PV"]["area_real"])  # [-]
        P_PV_roof_max = nb_modulesPV_roof_max \
                        * data_centralDevices["PV"]["area_real"] * data_centralDevices["PV"]["P_nominal"]  # [W]

        # wind turbine(s) (WT)
        capacities_centralDevices["WT"] = {}
        capacities_centralDevices["WT"]["P_ref"] = \
            infos_centralDevices.loc[infos_centralDevices["type"] == "WT", ["f"]].iloc[0, 0]  # [W]
        if capacities_centralDevices["WT"]["P_ref"] > 0:
            capacities_centralDevices["WT"]["nb_WT"] = 1
        else:
            capacities_centralDevices["WT"]["nb_WT"] = 0
        capacities_centralDevices["WT"]["powerCurve"] = \
            wind_turbines.powerCurve(data_centralDevices["WT"]["wind_turbine_model"])  # wind_speed [m/s], power [kW]
        #P_max_WT = capacities_centralDevices["WT"]["powerCurve"]["power"].max() * 1000  # [W]
        #capacities_centralDevices["WT"]["nb_WT"] = int(capacities_centralDevices["WT"]["P_ref"] / P_max_WT)
        #capacities_centralDevices["WT"]["P_ref"] = P_max_WT * capacities_centralDevices["WT"]["nb_WT"]

        # %% dimensioning of storages

        # thermal energy storage (TES)
        capacities_centralDevices["TES"] = \
            infos_centralDevices.loc[infos_centralDevices["type"] == "TES", ["f"]].iloc[0, 0]  # [Wh]

        # battery (BAT)
        '''Is the power input/output of the battery high enough???'''
        '''IDEA: P_ref could be defined otherwise; e.g. as maximum of P_ref for PV and WT...'''
        capacities_centralDevices["BAT"] = \
            infos_centralDevices.loc[infos_centralDevices["type"] == "BAT", ["f"]].iloc[0, 0] # [Wh]

        return capacities_centralDevices