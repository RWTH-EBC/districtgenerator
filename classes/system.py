# -*- coding: utf-8 -*-

import json
import os


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
        Constructor of System class.

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
                    T_design = subData["Theta_e"] # [°C] outside design temperature

        # %% conduct linear interpolation
        # for optimal design at bivalent temperature
        design_load = building["heatload"] + building["dhwload"]
        limit_load = building["heatlimit"]

        bivalent_load = design_load + (limit_load-design_load)/(T_heatlimit-T_design) * (T_bivalent-T_design)

        # Load list of possible devices
        dev = {}
        with open(os.path.join(self.file_path, 'device_data.json')) as json_file:
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
                BES[k] = design_load * (buildingFeatures["heater"] == k)

            # heat pump (HP) capacity refers to heat load at bivalent temperature
            if k == "HP":
                BES["HP"] = bivalent_load * (buildingFeatures["heater"] == k)

            # electric heating (EH) exists if HP exists
            if k == "EH":
                BES["EH"] = (design_load - bivalent_load) * (buildingFeatures["heater"] == "HP")

            # thermal energy storage (TES) always exists
            if k == "TES":
                # Factor [l/kW], [Wh = l/kW * kW * g/l * J/(gK) * K / 3600]
                # design refers to DHL
                BES["TES"] = buildingFeatures["f_TES"] \
                             * design_load / 1000 \
                             * physics["rho_water"] \
                             * physics["c_p_water"] \
                             * dev["TES"]["T_diff_max"] \
                             / 3600

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