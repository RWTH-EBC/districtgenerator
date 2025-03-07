# -*- coding: utf-8 -*-

import json
import os
import districtgenerator.functions.opti_dimensioning_central_devices as opti_dimensioning_central_devices
import districtgenerator.functions.load_params_central_devices as load_params_central_devices
from .solar import Sun
import districtgenerator.functions.wind_turbines as wind_turbines
import numpy as np


class BES:
    """
    Abstract class for design of the building energy system.

    Parameters
    ----------
    file_path : string
        File path to the data directory of the districtgenerator.
    """

    def __init__(self, physics, decentral_device_data, design_building_data, file_path):
        """
        Constructor of building energy system (BES) class.

        Returns
        -------
        None.
        """

        self.design_load = None
        self.bivalent_load = None
        self.physics = physics
        self.decentral_device_data = decentral_device_data
        self.design_building_data = design_building_data
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
        T_bivalent = self.design_building_data["T_bivalent"]
        T_heatlimit = self.design_building_data["T_heatlimit"]
        T_design = site["T_ne"]  # [°C] outside design temperature

        # %% conduct linear interpolation
        # for optimal design at bivalent temperature
        self.design_load = building["envelope"].heatload + building["dhwload"]
        limit_load = building["envelope"].heatlimit

        self.bivalent_load = self.design_load + (limit_load - self.design_load) / (T_heatlimit - T_design) \
                             * (T_bivalent - T_design)

        BES = {}

        # check if heating by grid
        if buildingFeatures["heater"] == "heat_grid":
            BES["heat_grid"] = 1
        else:
            BES["heat_grid"] = 0

        for k in self.decentral_device_data.keys():
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

            # thermal energy storage (TES)
            if k == "TES":
                # f_TES in l per kW design load
                # [Wh = l/kW * kW * g/l * J/(gK) * K / 3600]
                # design refers to DHL
                if buildingFeatures["heater"] == "heat_grid":
                    BES["TES"] = 0
                else:
                    BES["TES"] = buildingFeatures["f_TES"] \
                                * self.design_load / 1000 \
                                * self.physics["rho_water"] \
                                * self.physics["c_p_water"] \
                                * self.decentral_device_data["TES"]["T_diff_max"] \
                                / 3600

                    # battery (BAT)
            if k == "BAT":
                # Factor [Wh / W_PV], [Wh = Wh/W * W/m2 * m2]
                # design refers to buildable roof area (0.4 * area)
                BES["BAT"] = buildingFeatures["f_BAT"] \
                             * self.decentral_device_data["PV"]["P_nominal"] \
                             * building["envelope"].A["opaque"]["roof"] \
                             * buildingFeatures["f_PV"] \
                             * buildingFeatures["BAT"]

            # electric vehicle (EV)
            if k == "EV":
                # [Wh]
                BES["EV"] = float(buildingFeatures["EV"] * buildingFeatures["f_EV"])

            # photovoltaic (PV)
            if k == "PV":
                BES["PV"] = {}
                areaPV_temp = building["envelope"].A["opaque"]["roof"] \
                              * buildingFeatures["f_PV"] \
                              * buildingFeatures["PV"]
                BES["PV"]["nb_modules"] = int(areaPV_temp / self.decentral_device_data["PV"]["area_real"])  # [-]
                BES["PV"]["area"] = BES["PV"]["nb_modules"] * self.decentral_device_data["PV"]["area_real"]  # [m²]
                BES["PV"]["P_ref"] = BES["PV"]["area"] * self.decentral_device_data["PV"]["P_nominal"]  # [W]

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


    def designCES(self, data):
        """
        Dimensioning of central devices with EHDO

        Parameters
        ----------

        Returns
        -------
        capacities_centralDevices : dictionary
            The capacities of the central devices.
        """

        # Load parameters
        param, devs, dem, result_dict = load_params_central_devices.load_params(data)

        # Run optimization
        capacities_centralDevices = opti_dimensioning_central_devices.run_optim(data, devs, param, dem, result_dict)

        return capacities_centralDevices

    def generation(self, data):

        filePath = data.filePath
        time = data.time
        site = data.site
        global sun
        sun = Sun(filePath=filePath)
        # calculate theoretical PV generation
        potentialPV, defaultSTC = \
            sun.calcPVAndSTCProfile(time=time,
                                    site=site,
                                    area_roof=data.centralDevices["capacities"]["area"]["PV"],
                                    # In Germany, this is a roof pitch between 30 and 35 degrees
                                    beta=[35],
                                    # surface azimuth angles (Orientation to the south: 0°)
                                    gamma=[0],
                                    usageFactorPV=1,
                                    usageFactorSTC=0)

        # calculate theoretical STC generation
        defaultPV, pontentialSTC = \
            sun.calcPVAndSTCProfile(time=time,
                                    site=site,
                                    area_roof=data.centralDevices["capacities"]["area"]["STC"],
                                    # In Germany, this is a roof pitch between 30 and 35 degrees
                                    beta=[35],
                                    # surface azimuth angles (Orientation to the south: 0°)
                                    gamma=[0],
                                    usageFactorPV=0,
                                    usageFactorSTC=1)

        potentialWIND = wind_turbines.WT_generation(site["wind_speed"])
        potentialWIND = (potentialWIND / np.max(potentialWIND)) * (data.centralDevices["capacities"]["power_kW"]["WT"] * 1000)


        return (potentialPV, pontentialSTC, potentialWIND)