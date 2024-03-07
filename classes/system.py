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
        with open(os.path.join(self.file_path, 'decentral_device_data.json')) as json_file:
            jsonData = json.load(json_file)
            for subData in jsonData:
                dev[subData["abbreviation"]] = {}
                for subsubData in subData["specifications"]:
                    dev[subData["abbreviation"]][subsubData["name"]] = subsubData["value"]

        BES = {}

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

                    # battery (BAT)
            if k == "BAT":
                # Factor [Wh / W_PV], [Wh = Wh/W * W/m2 * m2]
                # design refers to buildable roof area (0.4 * area)
                # BES["BAT"] = buildingFeatures["f_BAT"] \
                #              * dev["PV"]["P_nominal"] \
                #              * building["envelope"].A["opaque"]["roof"] \
                #              * buildingFeatures["f_PV"] \
                #              * buildingFeatures["BAT"]
                BES["BAT"] = buildingFeatures["BAT"]

            # electric vehicle (EV)
            if k == "EV":
                # [Wh]
                if buildingFeatures["EV"] == 0:
                    BES["EV"] = float(0)
                else:
                    BES["EV"] = float(1
                                  * (40000 * (buildingFeatures["EV"] == "small")
                                     + 60000 * (buildingFeatures["EV"] == "medium")
                                     + 80000 * (buildingFeatures["EV"] == "large")
                                     )
                                  )

            # photovoltaic (PV)
            if k == "PV":
                BES["PV"] = {}
                # areaPV_temp = building["envelope"].A["opaque"]["roof"] \
                #               * buildingFeatures["f_PV"] \
                #               * buildingFeatures["PV"]
                areaPV_temp = buildingFeatures["PV_area"]
                BES["PV"]["nb_modules"] = int(areaPV_temp / dev["PV"]["area_real"])  # [-]
                BES["PV"]["area"] = BES["PV"]["nb_modules"] * dev["PV"]["area_real"]  # [m²]
                BES["PV"]["P_ref"] = BES["PV"]["area"] * dev["PV"]["P_nominal"]  # [W]

            # solar thermal energy (STC)
            if k == "STC":
                # BES["STC"] = {}
                # BES["STC"]["area"] = building["envelope"].A["opaque"]["roof"] \
                #                      * buildingFeatures["f_STC"] \
                #                      * buildingFeatures["STC"]
                BES["STC"]["area"] = buildingFeatures["STC_area"]

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

    def designCES(self, demands_district, devs, input_webtool):
        """
        Dimensioning of central devices.

        Parameters
        ----------
        data_centralDevices : dictionary
            Data of central devices.

        Returns
        -------
        capacities_centralDevices : dictionary
            The capacities of the central devices.
        """

        # initialise capacities of central devices
        capacities = {}

        if "photovoltaic_check_ehdo" == None:
            devs["PV"]["feasible"] = False
        else:
            devs["PV"]["feasible"] = True
            devs["PV"]["min_area"] = str("photovoltaic_min_input_ehdo")
            devs["PV"]["max_area"] = str("photovoltaic_max_input_ehdo")

        if "wind_turbines_check_ehdo" == None:
            devs["WT"]["feasible"] = False
        else:
            devs["WT"]["feasible"] = True
            devs["WT"]["min_cap"] = str(input_webtool["wind_turbines_min_input_ehdo"])
            devs["WT"]["max_cap"] = str(input_webtool["wind_turbines_max_input_ehdo"])

        if "hydropower_check_ehdo" == None:
            devs["WAT"]["feasible"] = False
        else:
            devs["WAT"]["feasible"] = True
            devs["WAT"]["min_cap"] = str(input_webtool["hydropower_min_input_ehdo"])
            devs["WAT"]["max_cap"] = str(input_webtool["hydropower_max_input_ehdo"])

        if "solar_thermal_collector_check_ehdo" == None:
            devs["STC"]["feasible"] = False
        else:
            devs["STC"]["feasible"] = True
            devs["STC"]["min_area"] = str("solar_thermal_collector_min_input_ehdo")
            devs["STC"]["max_area"] = str("solar_thermal_collector_max_input_ehdo")

        if "heat_pump_check_ehdo" == None:
            devs["HP"]["feasible"] = False
        else:
            devs["HP"]["feasible"] = True
            devs["HP"]["min_cap"] = str("heat_pump_min_input_ehdo")
            devs["HP"]["max_cap"] = str("heat_pump_max_input_ehdo")

        if "electric_boiler_check_ehdo" == None:
            devs["EB"]["feasible"] = False
        else:
            devs["EB"]["feasible"] = True
            devs["EB"]["min_cap"] = str("electric_boiler_min_input_ehdo")
            devs["EB"]["max_cap"] = str("electric_boiler_max_input_ehdo")

        if "compression_chiller_check_ehdo" == None:
            devs["CC"]["feasible"] = False
        else:
            devs["CC"]["feasible"] = True
            devs["CC"]["min_cap"] = str("compression_chiller_min_input_ehdo")
            devs["CC"]["max_cap"] = str("compression_chiller_max_input_ehdo")

        if "absorption_chiller_check_ehdo" == None:
            devs["AC"]["feasible"] = False
        else:
            devs["AC"]["feasible"] = True
            devs["AC"]["min_cap"] = str("absorption_chiller_min_input_ehdo")
            devs["AC"]["max_cap"] = str("absorption_chiller_max_input_ehdo")

        if "CHP_unit_check_ehdo" == None:
            devs["CHP"]["feasible"] = False
        else:
            devs["CHP"]["feasible"] = True
            devs["CHP"]["min_cap"] = str("CHP_unit_min_input_ehdo")
            devs["CHP"]["max_cap"] = str("CHP_unit_max_input_ehdo")


        if "biomass_CHP_check_ehdo" == None:
            devs["BCHP"]["feasible"] = False
        else:
            devs["BCHP"]["feasible"] = True
            devs["BCHP"]["min_cap"] = str("biomass_CHP_min_input_ehdo")
            devs["BCHP"]["max_cap"] = str("biomass_CHP_max_input_ehdo")

        if "biomass_boiler_check_ehdo" == None:
            devs["BBOI"]["feasible"] = False
        else:
            devs["BBOI"]["feasible"] = True
            devs["BBOI"]["min_cap"] = str("biomass_boiler_min_input_ehdo")
            devs["BBOI"]["max_cap"] = str("biomass_boiler_max_input_ehdo")

        if "waste_CHP_check_ehdo" == None:
            devs["WCHP"]["feasible"] = False
        else:
            devs["WCHP"]["feasible"] = True
            devs["WCHP"]["min_cap"] = str("waste_CHP_min_input_ehdo")
            devs["WCHP"]["max_cap"] = str("waste_CHP_max_input_ehdo")

        if "waste_boiler_check_ehdo" == None:
            devs["WBOI"]["feasible"] = False
        else:
            devs["WBOI"]["feasible"] = True
            devs["WBOI"]["min_cap"] = str("waste_boiler_min_input_ehdo")
            devs["WBOI"]["max_cap"] = str("waste_boiler_max_input_ehdo")

        if "electrolyzer_check_ehdo" == None:
            devs["ELYZ"]["feasible"] = False
        else:
            devs["ELYZ"]["feasible"] = True
            devs["ELYZ"]["min_cap"] = str("electrolyzer_min_input_ehdo")
            devs["ELYZ"]["max_cap"] = str("electrolyzer_max_input_ehdo")

        if "fuel_cell_check_ehdo" == None:
            devs["FC"]["feasible"] = False
        else:
            devs["FC"]["feasible"] = True
            devs["FC"]["min_cap"] = str("fuel_cell_min_input_ehdo")
            devs["FC"]["max_cap"] = str("fuel_cell_max_input_ehdo")

        if "hydrogen_storage_check_ehdo" == None:
            devs["H2S"]["feasible"] = False
        else:
            devs["H2S"]["feasible"] = True
            devs["H2S"]["min_cap"] = str("hydrogen_storage_min_input_ehdo")
            devs["H2S"]["max_cap"] = str("hydrogen_storage_max_input_ehdo")

        if "heat_check_ehdo" == None:
            devs["TES"]["feasible"] = False
        else:
            devs["TES"]["feasible"] = True
            devs["TES"]["min_volume"] = str("heat_min_input_ehdo")
            devs["TES"]["max_volume"] = str("heat_max_input_ehdo")

        if "cold_check_ehdo" == None:
            devs["CTES"]["feasible"] = False
        else:
            devs["CTES"]["feasible"] = True
            devs["CTES"]["min_volume"] = str("cold_min_input_ehdo")
            devs["CTES"]["max_volume"] = str("cold_max_input_ehdo")

        if "battery_check_ehdo" == None:
            devs["BAT"]["feasible"] = False
        else:
            devs["BAT"]["feasible"] = True
            devs["BAT"]["min_cap"] = str("battery_min_input_ehdo")
            devs["BAT"]["max_cap"] = str("battery_max_input_ehdo")

        return devs