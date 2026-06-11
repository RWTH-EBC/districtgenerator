# -*- coding: utf-8 -*-
import districtgenerator.functions.opti_dimensioning_central_devices as opti_dimensioning_central_devices
import districtgenerator.functions.get_params_central_devices as get_params_central_devices
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

        self.design_load_heating = None
        self.bivalent_load_heating = None
        self.design_load_cooling = None
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
        self.design_load_heating = building["envelope"].heatload
        limit_load_heating = building["envelope"].heatlimit

        self.bivalent_load_heating = self.design_load_heating + (limit_load_heating - self.design_load_heating) / (T_heatlimit - T_design) \
                             * (T_bivalent - T_design)

        # %% DHW design power (storage-based smoothing)
        # 1-minute DHW profiles contain short peaks that should not be used directly for sizing.
        # Instead of designing the heat generator for these extreme peaks, we assume the presence
        # of a short-term DHW storage that buffers peak demands.
        # The design load is therefore based on a 60-minute moving average of the DHW demand.
        # This corresponds to a storage that can be fully charged within 1 hour by the heat
        # generator.
        # Source of the 60-minutes assumption:
        # Zuschlag et al. (2026),
        # "How refrigerant cycle modeling shapes the techno-economic analysis
        #  of centralized vs. decentralized heat supply systems for city districts"

        dhw_minutely = building["user"].dhw_minutely
        max_power_dhw = np.max(dhw_minutely)
        window_steps = 60  # 60-minute moving average (1-min timestep)
        kernel = np.ones(window_steps) / window_steps
        heat_W_rolling = np.convolve(dhw_minutely, kernel, mode="same")

        Q_nom_DHW_W = float(np.max(heat_W_rolling))
        self.design_load_dhw = Q_nom_DHW_W

        # Design load for cooling
        self.design_load_cooling = building["envelope"].coolingload

        BES = {}

        # check if heating by grid
        if buildingFeatures["heater"] == "heat_grid":
            BES["heat_grid"] = 1
        else:
            BES["heat_grid"] = 0

        # Define hybrid heating systems for heat pumps
        hybrid_systems = {
            "HP": {"hp": "HP", "backup": "EH"},      # typical heat pump system with electric backup
            "GHP": {"hp": "HP", "backup": "BOI"},      # Gas Hybrid Heat Pump
            "BHP": {"hp": "HP", "backup": "BBOI"},     # Biomass Hybrid Heat Pump
            "H2HP": {"hp": "HP", "backup": "H2BOI"},   # Hydrogen Hybrid Heat Pump
            "OHP": {"hp": "HP", "backup": "OBOI"}      # Oil Hybrid Heat Pump
        }

        dhw_heater = buildingFeatures["dhw_heater"] # heater to be utilized for DHW generation

        for k in self.decentral_device_data.keys():
            BES[k] = {}
            # heat pump (HP) capacity refers to heat load at bivalent temperature
            if k == "HP":
                if buildingFeatures["heater"] in hybrid_systems:
                    BES["HP"] = self.bivalent_load_heating
                else:
                    BES["HP"] = 0


            # Capacity of heating systems other than heat pumps
            if k in ("BOI", "BBOI", "OBOI","H2BOI", "FC", "CHP", "EH", "DH"):
                # As the primary heating system
                if buildingFeatures["heater"] == k:
                    if dhw_heater is None:
                        BES[k] = self.design_load_heating + self.design_load_dhw
                    else:
                        BES[k] = self.design_load_heating

                # As the backup system in a hybrid heat pump system
                elif buildingFeatures["heater"] in hybrid_systems and hybrid_systems[buildingFeatures["heater"]]["backup"] == k:
                    if dhw_heater is None:
                        BES[k] = (self.design_load_heating - self.bivalent_load_heating) + self.design_load_dhw
                    else:
                        BES[k] = (self.design_load_heating - self.bivalent_load_heating)
                else:
                    BES[k] = 0

            # thermal energy storage (TES)
            if k == "TES":
                # No TES if the system is centralized
                if buildingFeatures["heater"] == "heat_grid":
                    BES["TES"] = 0
                else:
                    # f_TES in l per kW design load
                    # [Wh = l/kW * kW * g/l * J/(gK) * K / 3600]
                    # design refers to DHL
                    BES["TES"] = buildingFeatures["f_TES"] \
                                    * self.design_load_heating / 1000 \
                                    * self.physics["rho_water"] \
                                    * self.physics["c_p_water"] \
                                    * self.decentral_device_data["TES"]["T_diff_max"] \
                                    / 3600
                    
            if k == "TES_DHW": 
                if dhw_heater == "EH_DHW": #TODO Check which heaters should have a storage for DHW and which not
                    BES["TES_DHW"] = 0 # No TES if DHW is generated with electric heater (since we assume an instantaneous electric water heater)
                else: 
                    tau_DHW = 1  # hour
                    BES["TES_DHW"] = tau_DHW * self.design_load_dhw  # [Wh]

            if k == "EH_DHW":
                if dhw_heater == "EH_DHW":
                    min_size_instantaneous_heater = 18000 # W | 18 kW chosen as minimum size for instantaneous electric water heaters according to Tab. 6.32 Anschluss von Elektrogeräten aus Laasch et. al. Haustechnik (2013)
                    # For residential buildings it is assumed an electric water heater is present in every flat. If the max_power_dhw is larger then this is chosen.
                    nb_units = getattr(building["user"], "nb_units", 1)
                    nb_flats = getattr(building["user"], "nb_flats", 1)
                    #TODO: Check if this should be applied to nb_units or nb_flats
                    # print(f"DEBUG: nb_flats: {nb_flats}, nb_units: {nb_units}, max_power_dhw: {max_power_dhw}, min_size_instantaneous_heater: {min_size_instantaneous_heater}")
                    if nb_flats == None: nb_flats = 1 # For non-residential buildings
                    
                    BES["EH_DHW"] = max(max_power_dhw, nb_flats * min_size_instantaneous_heater)  # [W] 
                else:
                    BES["EH_DHW"] = 0

            # compression chiller (CC)
            # A compression chiller is only designed if the building is actively cooled
            # and not connected to a heat grid (since cooling would then be provided centrally).
            if k == "CC":
                BES["CC"] = self.design_load_cooling * buildingFeatures["cooling"] * (1 - BES["heat_grid"])

            # battery (BAT)
            if k == "BAT":
                # Factor [Wh / W_PV], [Wh = Wh/W * W/m2 * m2]
                # design refers to buildable roof area (0.4 * area)
                BES["BAT"] = buildingFeatures["f_BAT"] \
                             * self.decentral_device_data["PV"]["P_nominal"] \
                             * building["envelope"].A["opaque"]["roof"] \
                             * (buildingFeatures["f_PV1"] + buildingFeatures["f_PV2"])

            # electric vehicle (EV)
            if k == "EV":
                # [Wh]
                BES["EV"] = float(sum(building["user"].ev_capacity))

            # photovoltaic (PV)
            if k == "PV":
                BES["PV"] = {}
                # f_PV is the fraction of the roof area that is suitable and available for PV installation
                areaPV_temp = building["envelope"].A["opaque"]["roof"] \
                              * (buildingFeatures["f_PV1"] + buildingFeatures["f_PV2"])
                BES["PV"]["nb_modules"] = int(areaPV_temp / self.decentral_device_data["PV"]["area_real"])  # [-]
                BES["PV"]["area"] = BES["PV"]["nb_modules"] * self.decentral_device_data["PV"]["area_real"]  # [m²]
                BES["PV"]["P_ref"] = BES["PV"]["area"] * self.decentral_device_data["PV"]["P_nominal"]  # [W]

            # solar thermal energy (STC)
            if k == "STC":
                BES["STC"] = {}
                # f_STC is the fraction of the roof area that is suitable and available for STC installation
                BES["STC"]["area"] = building["envelope"].A["opaque"]["roof"] \
                                     * buildingFeatures["f_STC"]

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

        # Load parameters of the energy hub
        param, devs, dem, result_dict = get_params_central_devices.get_params(data)

        # Run optimization
        capacities_centralDevices = opti_dimensioning_central_devices.run_optim(data, devs, param, dem, result_dict)

        return capacities_centralDevices