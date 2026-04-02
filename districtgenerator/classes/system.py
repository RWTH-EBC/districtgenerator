# -*- coding: utf-8 -*-
import re
import numpy as np
from districtgenerator.functions.opti_dimensioning_decentral_devices import choose_cheapest_heating_concept_fixed_design
import districtgenerator.functions.opti_dimensioning_central_devices as opti_dimensioning_central_devices
import districtgenerator.functions.load_params_central_devices as load_params_central_devices

class BES:
    """
    Building Energy System (BES):
    - Standard-based sizing of device capacities (no sizing optimization)
    - If heater == "opt": choose cheapest heating concept considering FIXED capacities,
      by running an OPERATION optimization per candidate.
    """

    def __init__(self, physics, decentral_device_data, design_building_data, file_path, eco_data, pyomo_config):
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
        self.eco_data = eco_data
        self.pyomo_config = pyomo_config

    def designECS(self, building, site, dt_s):
        """
        Design of the building energy system.

        Parameters
        ----------
        building : dictionary
            Information about the building.
        site : dictionary
            Information about location and climatic conditions.
        dt_s : int
            Timestep length.

        Returns
        -------
        dict
            Capacities and device sizing results.
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

        window_steps = 60  # 60-minute moving average (1-min timestep)

        kernel = np.ones(window_steps) / window_steps
        heat_W_rolling = np.convolve(dhw_minutely, kernel, mode="same")

        Q_nom_DHW_W = float(np.max(heat_W_rolling))
        self.design_load_dhw = Q_nom_DHW_W

        # Design load for cooling
        self.design_load_cooling = building["envelope"].coolingload

        # If heater == "opt": choose cheapest heating concept FIRST
        heater_raw = buildingFeatures.get("heater", "")
        mode, allowed, manual = self._parse_heater_spec(heater_raw)

        if mode in ("opt", "opt_geg", "opt_custom"):

            # build full candidates (opt/opt_geg handled inside _candidate_fixed_capacities)
            candidates = self._candidate_fixed_capacities(building, mode=("opt_geg" if mode == "opt_geg" else "opt"))

            # if custom list: filter them
            if mode == "opt_custom":
                candidates = self._filter_candidates(candidates, allowed)

            chosen, evals = choose_cheapest_heating_concept_fixed_design(
                demand_heat_w=building["user"].heat_cluster,
                demand_dhw_w=building["user"].dhw_cluster,
                demand_el_w=building["user"].elec_cluster,
                ev_on_demand_w=building["user"].EV_carcharging_ondemand_cluster,
                site=site,
                pv_gen_w=building["generationPV_cluster"],
                stc_gen_w=building["generationSTC_cluster"],
                candidates=candidates,
                dt_s=dt_s,
                decentral_device_data=self.decentral_device_data,
                eco_data=self.eco_data,
                pyomo_config=self.pyomo_config,
                design_building_data=self.design_building_data,
                building=building,
                cluster_meta=building.get("cluster_meta", None)
            )

            buildingFeatures["heater"] = chosen

        elif mode == "manual":
            # keep whatever manual heater was given
            if manual is not None:
                buildingFeatures["heater"] = str(manual).strip()

        BES = {}

        # check if heating by grid
        BES["heat_grid"] = 1 if buildingFeatures["heater"] == "heat_grid" else 0

        # Define hybrid heating systems for heat pumps
        hybrid_systems = {
            "HP": {"hp": "HP", "backup": "EH"},      # typical heat pump system with electric backup
            "GHP": {"hp": "HP", "backup": "BOI"},      # Gas Hybrid Heat Pump
            "BHP": {"hp": "HP", "backup": "BBOI"},     # Biomass Hybrid Heat Pump
            "H2HP": {"hp": "HP", "backup": "H2BOI"},   # Hydrogen Hybrid Heat Pump
            "OHP": {"hp": "HP", "backup": "OBOI"}      # Oil Hybrid Heat Pump
        }

        for k in self.decentral_device_data.keys():
            BES[k] = {}
            # heat pump (HP) capacity refers to heat load at bivalent temperature
            if k == "HP":
                if buildingFeatures["heater"] in hybrid_systems:
                    BES["HP"] = self.bivalent_load_heating
                else:
                    BES["HP"] = 0

            # Capacity of heating systems other than heat pumps
            if k in ("BOI", "BBOI", "OBOI", "H2BOI", "EH", "DH"):
                # As the primary heating system
                if buildingFeatures["heater"] == k:
                    BES[k] = self.design_load_heating + self.design_load_dhw
                # As the backup system in a hybrid heat pump system
                elif buildingFeatures["heater"] in hybrid_systems and hybrid_systems[buildingFeatures["heater"]]["backup"] == k:
                    BES[k] = (self.design_load_heating - self.bivalent_load_heating) + self.design_load_dhw
                else:
                    BES[k] = 0

            # handle CHP/FC separately (co-generation)
            if k == "CHP":
                if buildingFeatures["heater"] == "CHP":
                    BES["CHP"] = self.design_load_heating + self.design_load_dhw
                else:
                    BES["CHP"] = 0

            if k == "FC":
                if buildingFeatures["heater"] == "FC":
                    BES["FC"] = self.design_load_heating + self.design_load_dhw
                else:
                    BES["FC"] = 0

            # thermal energy storage (TES)
            if k == "TES":
                # No TES if the system is centralized
                if buildingFeatures["heater"] in ("heat_grid", "DH"):
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

            # DHW storage (separate from SH TES)
            if k == "TES_DHW":
                # No TES_DHW if the system is centralized
                if buildingFeatures["heater"] in ("heat_grid", "DH"):
                    BES["TES_DHW"] = 0
                # 1-hour storage of design DHW load
                else:
                    tau_DHW = 1  # hour
                    BES["TES_DHW"] = tau_DHW * self.design_load_dhw  # [Wh]

            # compression chiller (CC)
            # A compression chiller is only designed if the building is actively cooled
            # and not connected to a heat grid (since cooling would then be provided centrally).
            if k == "CC":
                BES["CC"] = self.design_load_cooling * buildingFeatures["cooling"] * (1 - BES["heat_grid"])

            # battery (BAT)
            if k == "BAT":
                # Factor [Wh / W_PV], [Wh = Wh/W * W/m2 * m2]
                # design refers to buildable roof area (f_PV * roof area)
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

    def _candidate_fixed_capacities(self, building, mode):

        """
        Build fixed-size candidate capacities for each heating concept.
        Heating generator capacities are fixed by design/bivalent rule.

        Parameters
        ----------
        building : dict
            Building data structure containing envelope, user, and feature information.
        mode : str
            Selection mode for candidate generation:
            - "opt"     : consider all available heating concepts (default behavior)
            - "opt_geg" : consider only GEG-compliant heating concepts
                          (HP, BBOI, H2BOI, FC, GHP, BHP, OHP, H2HP)

        Returns
        -------
        candidates : dict[str, dict]
        """

        bf = building["buildingFeatures"]

        design = float(self.design_load_heating)
        bivalent = float(self.bivalent_load_heating)
        design_dhw  = float(self.design_load_dhw)

        fixed_common = {}
        if bf["heater"] in ("heat_grid", "DH"):
            fixed_common["TES"] = 0.0
            fixed_common["TES_DHW"] = 0.0
        else:
            # TES
            fixed_common["TES"] = (bf["f_TES"] * design / 1000 * self.physics["rho_water"] * self.physics["c_p_water"]
                    * self.decentral_device_data["TES"]["T_diff_max"] / 3600)
            # TES_DHW
            tau_DHW = 1  # = 1 hour of storage
            fixed_common["TES_DHW"] = tau_DHW * design_dhw  # [Wh]

        fixed_common["BAT"] = (
                bf["f_BAT"] * self.decentral_device_data["PV"]["P_nominal"]
                * building["envelope"].A["opaque"]["roof"] * (bf["f_PV1"] + bf["f_PV2"])
        )

        areaPV_temp = building["envelope"].A["opaque"]["roof"] * (bf["f_PV1"] + bf["f_PV2"])
        fixed_common["PV"] = {
            "nb_modules": int(areaPV_temp / self.decentral_device_data["PV"]["area_real"]),
            "area": int(areaPV_temp / self.decentral_device_data["PV"]["area_real"]) * self.decentral_device_data["PV"][
                "area_real"],
            "P_ref": int(areaPV_temp / self.decentral_device_data["PV"]["area_real"]) *
                     self.decentral_device_data["PV"]["area_real"] * self.decentral_device_data["PV"]["P_nominal"],
        }
        fixed_common["STC"] = {"area": building["envelope"].A["opaque"]["roof"] * bf["f_STC"]}

        # candidate heating concepts
        candidates = {}

        # Initialize all relevant heating device keys to 0
        def blank_caps():
            caps = dict(fixed_common)
            caps.update({
                "HP": 0.0,
                "EH": 0.0,
                "BOI": 0.0,
                "BBOI": 0.0,
                "OBOI": 0.0,
                "H2BOI": 0.0,
                "CHP": 0.0,
                "FC": 0.0,
            })
            return caps

        # monovalent (single primary heater)
        for dev in ("BOI", "BBOI", "OBOI", "H2BOI", "EH", "CHP", "FC"):
            caps = blank_caps()
            caps[dev] = design + design_dhw
            candidates[dev] = caps

        # heat pump hybrids
        hybrids = {
            "HP": "EH",
            "GHP": "BOI",
            "BHP": "BBOI",
            "H2HP": "H2BOI",
            "OHP": "OBOI",
        }

        for concept, backup in hybrids.items():
            caps = blank_caps()
            caps["HP"] = bivalent
            caps[backup] = max(design - bivalent, 0.0) + design_dhw
            candidates[concept] = caps

        mode = (mode or "opt").strip().lower()
        if mode == "opt_geg":
            allowed = {"HP", "BBOI", "H2BOI", "FC", "GHP", "BHP", "OHP", "H2HP"}
            candidates = {k: v for k, v in candidates.items() if k in allowed}

            if not candidates:
                raise RuntimeError("opt_GEG produced no candidates. Check allowed set / candidate keys.")

        return candidates

    def _parse_heater_spec(self, heater_value):
        """
        Valid inputs:
          - "heat_grid" (manual)
          - "DH" (manual)
          - "opt"
          - "opt_geg"
          - custom list: "HP,BBOI" or "[HP,BBOI]" or "opt:[HP,BBOI]" (but NOT containing DH/heat_grid)
          - single manual tech: "HP", "BOI", ...
        Returns:
          mode: "manual" | "opt" | "opt_geg" | "opt_custom"
          allowed: set[str] | None
          manual: str | None
        """

        if heater_value is None:
            return "manual", None, None

        s = str(heater_value).strip()
        if not s:
            return "manual", None, None

        low = s.lower()

        # explicit optimization keywords
        if low in ("opt", "opt_geg"):
            return low, None, None

        # detect list-ish syntax
        is_custom = (
                ("," in s) or
                (s.startswith("[") and s.endswith("]")) or
                (s.startswith("(") and s.endswith(")")) or
                (s.startswith("{") and s.endswith("}")) or
                low.startswith("opt:") or low.startswith("opt[") or low.startswith("opt(") or low.startswith("opt{")
        )

        if is_custom:
            cleaned = re.sub(r"^\s*opt\s*[: ]?\s*", "", s, flags=re.IGNORECASE).strip()

            # strip wrappers
            if (cleaned.startswith("[") and cleaned.endswith("]")) or \
                    (cleaned.startswith("(") and cleaned.endswith(")")) or \
                    (cleaned.startswith("{") and cleaned.endswith("}")):
                cleaned = cleaned[1:-1].strip()

            tokens = [t.strip() for t in cleaned.split(",") if t.strip()]
            allowed = {t.upper() for t in tokens}

            # empty list -> treat as manual
            if not allowed:
                return "manual", None, s

            # forbid DH / heat_grid inside optimization lists
            forbidden = {"DH", "HEAT_GRID", "HEATGRID", "HEAT-GRID"}
            if allowed & forbidden:
                raise ValueError(
                    f"Invalid heater list {sorted(allowed)}: DH/heat_grid cannot be part of optimization lists. "
                    f"Use 'DH' or 'heat_grid' alone if you want a fixed choice."
                )

            return "opt_custom", allowed, None

        # otherwise: manual single tech (including 'DH' or 'heat_grid')
        return "manual", None, s

    def _filter_candidates(self, candidates, allowed_set):
        """Filter candidate dict by allowed_set; raise if nothing remains."""
        allowed_set = {a.upper() for a in (allowed_set or set())}
        filtered = {k: v for k, v in candidates.items() if k.upper() in allowed_set}

        if not filtered:
            raise RuntimeError(
                f"Custom heater candidate list {sorted(allowed_set)} produced no valid candidates. "
                f"Valid keys include: {sorted(candidates.keys())}"
            )
        return filtered

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
        param, devs, dem, result_dict = load_params_central_devices.load_params(data)

        # Run optimization
        capacities_centralDevices = opti_dimensioning_central_devices.run_optim(data, devs, param, dem, result_dict)

        return capacities_centralDevices