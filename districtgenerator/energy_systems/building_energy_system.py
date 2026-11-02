# -*- coding: utf-8 -*-
"""
Building energy system: sizing of the decentral devices of each building.
"""
import os

import numpy as np

from districtgenerator.energy_systems import technologies
from districtgenerator.environment.solar import Sun

class BES:
    """
    Size the Building Energy System (BES) of an individual building.

    Parameters
    ----------
    physics : dict
        Physical constants, including water density  and heat capacity,
         used for storage sizing.
    decentral_device_data : dict
        Technology parameters keyed by device code.
    design_building_data : dict
        Design assumptions.
    file_path : str or os.PathLike
        DistrictGenerator data-directory path retained for callers.

    Attributes
    ----------
    design_load_heating : float or None
        Building space-heating design load in W, populated by ``designECS``.
    bivalent_load_heating : float or None
        Space-heating load at the bivalent temperature in W.
    design_load_cooling : float or None
        Cooling design load in W.
    """

    HEATING_CONCEPTS = technologies.HEATING_CONCEPTS

    # Supply rules live in energy_systems.technologies; kept here for existing callers
    get_heating_candidates = staticmethod(technologies.get_heating_candidates)
    get_cooling_supply = staticmethod(technologies.get_cooling_supply)
    compression_chiller_cop = staticmethod(technologies.compression_chiller_cop)

    def __init__(self, physics, decentral_device_data, design_building_data, file_path):
        """Store the inputs used to size a building's energy system.

        Parameters
        ----------
        physics : dict
            Water properties ``rho_water`` (g/L) and ``c_p_water`` (J/(g K)).
        decentral_device_data : dict
            Device specifications keyed by technology code.
        design_building_data : dict
            Bivalent and heating-limit temperatures in °C.
        file_path : str or os.PathLike
            Path to the project data directory.

        Returns
        -------
        None
            Initializes design-load attributes; sizing runs separately in ``designECS``.
        """

        self.design_load_heating = None
        self.bivalent_load_heating = None
        self.design_load_cooling = None
        self.physics = physics
        self.decentral_device_data = decentral_device_data
        self.design_building_data = design_building_data
        self.file_path = file_path

    def designECS(self, building, site):
        """Size devices for one building's selected supply concept.

        Parameters
        ----------
        building : dict
            Prepared building record with ``buildingFeatures``, ``envelope``, and
            ``user``.
        site : dict
            Site conditions with outdoor design temperature ``T_ne`` in °C.

        Returns
        -------
        dict
            Capacities by device.
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
            # Cooling supply can be selected independently of network heating.
            if k == "CC":
                BES["CC"] = self.design_load_cooling if self.get_cooling_supply(buildingFeatures) == "CC" else 0

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


def design_decentral_devices(data, saveGenerationProfiles=True):
    """Size building devices and calculate rooftop generation profiles.

    Parameters
    ----------
    data : District with generated envelopes and user demands, site weather,
     time settings, physical constants, device parameters, and output paths.
    saveGenerationProfiles : bool, optional
        If True (default), write each building's PV and STC power profiles in W
        as semicolon-separated CSV files beneath ``data.resultPath/generation``.

    Returns
    -------
    None
        Adds ``bes_obj`` and ``capacities`` to each building and sets its user's
        ``generationPV`` and ``generationSTC`` arrays in W. For candidate heater
        lists, selects a concept and updates the building and scenario heater.
    """

    candidates = [technologies.get_heating_candidates(building["buildingFeatures"]["heater"])
                  for building in data.district]

    # Solar irradiance on the tilted roof surfaces is needed for the PV and STC yield
    sun = Sun(filePath=data.filePath)
    for building, choices in zip(data.district, candidates):

        # %% create building energy system object
        # get capacities of all possible devices
        building["bes_obj"] = BES(physics=data.physics,
                      decentral_device_data=data.decentral_device_data,
                      design_building_data=data.design_building_data,
                      file_path=data.filePath)
        requested_heater = building["buildingFeatures"]["heater"]
        try:
            if choices:
                building["buildingFeatures"]["heater"] = choices[0]
            building["capacities"] = building["bes_obj"].designECS(building, data.site)
        finally:
            building["buildingFeatures"]["heater"] = requested_heater

        # calculate PV and STC generation
        #building["generationPV"], building["generationSTC"] = \
        building["user"].generationPV, building["user"].generationSTC = \
            technologies.calc_pv_and_stc_profile(sun=sun,
                                                 time=data.time,
                                    site=data.site,
                                    devices=data.decentral_device_data,
                                    area_roof=building["envelope"].A["opaque"]["roof"],
                                    # In Germany, this is a roof pitch between 30 and 35 degrees
                                    beta=[35],
                                    # surface azimuth angles (Orientation to the south: 0°)
                                    gamma=[building["buildingFeatures"]["gamma_PV"]],
                                    usageFactorPV1=building["buildingFeatures"]["f_PV1"],
                                    usageFactorPV2=building["buildingFeatures"]["f_PV2"],
                                    usageFactorSTC=building["buildingFeatures"]["f_STC"])

        # optionally save generation profiles
        if saveGenerationProfiles == True:
            generation_path = os.path.join(data.resultPath, 'generation')
            os.makedirs(generation_path, exist_ok=True)
            np.savetxt(os.path.join(data.resultPath, 'generation')
                       + '/decentralPV_' + building["unique_name"] + '.csv',
                       building["user"].generationPV,
                       delimiter=';',
                       fmt='%.2f')
            np.savetxt(os.path.join(data.resultPath, 'generation')
                       + '/decentralSTC_' + building["unique_name"] + '.csv',
                       building["user"].generationSTC,
                       delimiter=';',
                       fmt='%.2f')

    if any(candidates):
        from districtgenerator.optimization.decentral.heating_concept import choose_heating_concept

        data.clusterProfiles(centralEnergySupply=False)
        for building, choices in zip(data.district, candidates):
            if choices:
                choose_heating_concept(data, building, choices)
                data.scenario.loc[data.scenario["id"] == building["buildingFeatures"]["id"], "heater"] = (
                    building["buildingFeatures"]["heater"])
