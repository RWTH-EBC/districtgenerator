"""Extraction of certificate data from the Datahandler and the KPIs."""
from collections import OrderedDict
import pandas as pd
from districtgenerator.analysis.certificate.components import ReportComponent


class DataExtractor(ReportComponent):
    """
    This class extracts the data from the input data structure and prepares it for the certificate.
    """
    def __init__(self, data, kpis) -> None:
        """
        Args:
            data: Input data structure (Datahandler-Object from dataHandler.py)
            kpis: Key performance indicators (KPI-Object from KPIs.py)
        """
        self.data = data
        self.kpis = kpis
        self.building_stats = {}
        self.building_df = None
        self.key_performance_indicator = None
        self.optimization_results = None
        self.district_structure = None
        self.energyhub_df = None
        self.decentral_df = None
        self.district_layout = None

        

        # Building features to be included in the building_df and the keys to extract the data from buildingFeatures
        self.mapping_building_list = OrderedDict([ # key: display name value: data key to extract value from buildingFeatures
            (self.translate("name_building_type"), "building"),
            (self.translate("name_building_year"), "year"),
            (self.translate("name_building_retrofit"), "retrofit"),
            (self.translate("name_sp_mass"), "construction_type"),
            (self.translate("name_night_setback"), "night_setback"),
            (self.translate("name_building_area"), "area"),
            (self.translate("name_heating_tech"), "heater"),
            (self.translate("name_dhw_heating_tech"), "dhw_heater"),
            (self.translate("name_ev_share"), "EV"),
            (self.translate("name_f_tes"), "f_TES"),
            (self.translate("name_f_bat"), "f_BAT"),
            (self.translate("name_f_pv1"), "f_PV1"),
            (self.translate("name_f_pv2"), "f_PV2"),
            (self.translate("name_f_stc"), "f_STC"),
            (self.translate("name_gamma_pv"), "gamma_PV"),
            (self.translate("name_ev_charging"), "ev_charging")
        ])

        self._extract_data()

    def _get_year_category(self, year:int) -> str:
        """
        Returns the building year category as a string based on the given year.
        Args:
            year: Building year as an integer
        Returns:
            Building year category as a string
        """
        if year < 1968: return self.translate("name_age_cat_before_1968")
        if 1968 <= year <= 1978: return self.translate("name_age_cat_1968_1978")
        if 1979 <= year <= 1983: return self.translate("name_age_cat_1979_1983")
        if 1984 <= year <= 1994: return self.translate("name_age_cat_1984_1994")
        if 1995 <= year <= 2001: return self.translate("name_age_cat_1995_2001")
        if 2002 <= year <= 2009: return self.translate("name_age_cat_2002_2009")
        if 2010 <= year <= 2015: return self.translate("name_age_cat_2010_2015")
        return self.translate("name_age_cat_after_2016")

    def _process_buildings(self):
        """
        Processes the building data and populates the building_stats and list_of_buildings attributes.
        """
        template_dict = OrderedDict([
            (self.translate("name_number_bldgs"), 0), (self.translate("name_total_area"), 0), (self.translate("name_age_cat_before_1968"), 0),
            (self.translate("name_age_cat_1968_1978"), 0), (self.translate("name_age_cat_1979_1983"), 0), (self.translate("name_age_cat_1984_1994"), 0),
            (self.translate("name_age_cat_1995_2001"), 0), (self.translate("name_age_cat_2002_2009"), 0), (self.translate("name_age_cat_2010_2015"), 0),
            (self.translate("name_age_cat_after_2016"), 0)
        ])

        building_types = ['SFH', 'TH', 'MFH', 'AB', 'OB', 'SC', 'GS', 'RE', "UNI", "HOSPITAL", "CULTURE", "SPORT", "RETAIL", "WORKSHOP", "MIXED"]
        
        self.building_stats = {b_type: template_dict.copy() for b_type in building_types}
        building_data_list = []
        for idx, building in enumerate(self.data.district):
            features = building["buildingFeatures"]
            b_type = features["building"]
            stat_type = "MIXED" if "+" in b_type else b_type

            if stat_type in self.building_stats:
                # Update building statistics by this building
                self.building_stats[stat_type][self.translate("name_number_bldgs")] += 1
                self.building_stats[stat_type][self.translate("name_total_area")] += features["area"]
                year_category = self._get_year_category(features["year"])
                self.building_stats[stat_type][year_category] += features["area"]

            building_dict = {}
            building_dict[self.translate("name_building_id")] = features["id"]

            # Add to the dictionary from the mapping
            building_dict.update({
                display_name: features.get(data_key)
                for display_name, data_key in self.mapping_building_list.items()
            })

            # manual adjustments: 
            if features.get("heater") == "heat_grid":
                building_dict["fTES"] = 0 # if building is connected to heat grid, no local TES even if otherwise specified

            # Add dictionary to the list
            building_data_list.append(building_dict)

        self.building_df = pd.DataFrame(building_data_list)

        # TODO: Maybe add here dtype casting e.g. ensure area is integer not float ....
    
    def _extract_key_performance_indicator(self):
        """Extracts the general key performance indicators."""
        years = self.kpis.inputData["simulated_years"]
        obs_time = self.data.ecoData["observation_time"]
        to_kW = 1000 # Convert W to kW for power values
        to_MWh = 1000000 # Convert W to MWh for energy values

        # Prepare Data -> # TODO: Move to KPIs class
        avg_autonomy = sum(self.kpis.energy_autonomy_year[y] for y in years) / len(years)
        avg_scf = sum(self.kpis.scf_year[y] for y in years) / len(years)
        avg_dcf = sum(self.kpis.dcf_year[y] for y in years) / len(years)

        # Overall_summary
        self.district_key_kpis = [
            [self.translate("kpi_net_energy_demand"), f"{round((self.kpis.total_heating_demand + self.kpis.total_cooling_demand + self.kpis.total_electricity_demand + self.kpis.total_dhw_demand + self.kpis.total_EV_demand) / to_MWh, 1)} MWh/a"],
            [self.translate("kpi_standard_heat_load"), f"{round(self.kpis.totalheatload / to_kW, 1)} kW"],
            [self.translate("kpi_project_time"), f"{obs_time} {self.translate('name_years')}"]
        ]

        self.district_operation_kpis = [
            [self.translate("kpi_avg_co2_emissions"), f"{round(self.kpis.avg_co2_emissions, 2)} t/a"],
            [self.translate("kpi_avg_energy_costs"), f"{round(self.kpis.avg_operationCosts, 0)} €/a"],
            [self.translate("kpi_sys_costs_central"), f"{round(self.kpis.annual_fixed_costs_central, 0)} €/a"],
            [self.translate("kpi_sys_costs_decentral"), f"{round(self.kpis.annual_fixed_costs_decentral, 0)} €/a"],
            [self.translate("kpi_peak_load_el"), f"{round(max(self.kpis.peakDemand.values()), 1)} kW"],
            [self.translate("kpi_max_feed_in"), f"{round(max(self.kpis.peakInjection.values()), 1)} kW"],
            [self.translate("kpi_autonomy_rate"), f"{round(avg_autonomy * 100, 1)} %"],
            [self.translate("kpi_supply_cover_ratio"), f"{round(avg_scf * 100, 1)} %"],
            [self.translate("kpi_demand_cover_ratio"), f"{round(avg_dcf * 100, 1)} %"],
        ]

        # max loads in kW
        self.max_loads_table = [
            [f"{self.translate('name_heat')}:", f"{int(round(self.kpis.total_heat_peak / to_kW))} kW"],
            [f"{self.translate('name_el')}:", f"{int(round(self.kpis.total_electricity_peak / to_kW))} kW"],
            [f"{self.translate('name_dhw')}:", f"{int(round(self.kpis.total_dhw_peak / to_kW))} kW"],
            [f"{self.translate('name_cool')}:", f"{int(round(self.kpis.total_cooling_peak / to_kW))} kW"]
        ]

        # energy demand in MWh/a
        self.pie_chart_energy = {
            self.translate("name_el"): round(self.kpis.total_electricity_demand / to_MWh, 2),
            self.translate("name_heat"): round(self.kpis.total_heating_demand / to_MWh, 2),
            self.translate("name_dhw"): round(self.kpis.total_dhw_demand / to_MWh, 2),
            self.translate("name_cool"): round(self.kpis.total_cooling_demand / to_MWh, 2),
            self.translate("name_ev"): round(self.kpis.total_EV_demand / to_MWh, 2)
        }
        
        # Bar charts:
        self.bar_costs_data = []
        self.bar_co2_data = []
        
        for y in years:
            # Fetch cost breakdown
            costs = self.kpis.detailed_costs_year[y]
            self.bar_costs_data.append({
                "Year": y,
                self.translate("name_central_costs"): round(costs["eh_fixed"], 0),
                self.translate("name_decentral_costs"): round(costs["decentral_fixed"], 0),
                self.translate("name_el"): round(costs["electricity"], 0),
                self.translate("name_gas"): round(costs["gas"], 0),
                self.translate("name_oil"): round(costs["oil"], 0),
                self.translate("name_waste"): round(costs["waste"], 0),
                self.translate("name_biomass"): round(costs["biomass"], 0),
                self.translate("name_district_heat"): round(costs["district_heat"], 0),
                self.translate("name_hydrogen"): round(costs["hydrogen"], 0),
                self.translate("name_feed_in_revenue"): round(costs["revenue_feed_in_el"], 0)
            })

            # Fetch CO2 breakdown
            em = self.kpis.co2emissions[y]
            self.bar_co2_data.append({
                "Year": y,
                self.translate("name_el"): round(em["co2_dem_grid"], 2),
                self.translate("name_gas"): round(em["co2_gas"], 2),
                self.translate("name_oil"): round(em["co2_oil"], 2),
                self.translate("name_waste"): round(em["co2_waste"], 2),
                self.translate("name_biomass"): round(em["co2_biom"], 2),
                self.translate("name_district_heat"): round(em["co2_district_heat"], 2),
                self.translate("name_hydrogen"): round(em["co2_hydrogen"], 2)
            })

            # Maybe later add also the development of the energy demand over the years as a stacked bar if renovation measures or other changes are implemented in the multi-year simulation.

            self.key_performance_indicator = {
            "district_key_kpis": self.district_key_kpis,
            "district_operation_kpis": self.district_operation_kpis,
            "max_loads_table": self.max_loads_table,
            "pie_chart_energy": self.pie_chart_energy,
            "bar_costs_data": self.bar_costs_data,
            "bar_co2_data": self.bar_co2_data,
            "observation_time": obs_time
            }

    def _extract_district_structure(self):
        """Extracts the structural information of the district and prepares tables."""
        res_types = {'SFH', 'TH', 'MFH', 'AB'}
        mixed_types = {'MIXED'}

        first_b_type = list(self.building_stats.keys())[0]
        all_keys = list(self.building_stats[first_b_type].keys())
        age_classes = all_keys[2:] # Change to actively exclude Anzahl and Gesamtfläche instead of relying on the order

        agg_stats = {
            self.translate("name_res_bldg"): {self.translate("name_number_bldgs"): 0, self.translate("name_total_area"): 0},
            self.translate("name_mixed_bldg"): {self.translate("name_number_bldgs"): 0, self.translate("name_total_area"): 0},
            self.translate("name_com_bldg"): {self.translate("name_number_bldgs"): 0, self.translate("name_total_area"): 0}
        }
        for cat in agg_stats:
            for age in age_classes:
                agg_stats[cat][age] = 0

        details_rows = []

        # Build the aggregated stats and the details rows at the same time by iterating through the building types only once
        for b_type, stats in self.building_stats.items():
            
            # Map to main category
            if b_type in res_types:
                cat = self.translate("name_res_bldg")
            elif b_type in mixed_types:
                cat = self.translate("name_mixed_bldg")
            else:
                cat = self.translate("name_com_bldg")

            # Sum up for the compact table
            agg_stats[cat][self.translate("name_number_bldgs")] += stats[self.translate("name_number_bldgs")]
            agg_stats[cat][self.translate("name_total_area")] += stats[self.translate("name_total_area")]
            for age in age_classes:
                agg_stats[cat][age] += stats[age]

            # Detailed row for the landscape page - ALWAYS appended
            translated_name = self._translate_building_type(b_type)
            detail_row = {
                self.translate("name_building_type"): translated_name,
                self.translate("name_number_bldgs"): stats[self.translate("name_number_bldgs")] if stats[self.translate("name_number_bldgs")] > 0 else "-"            
                }
            for age in age_classes:
                detail_row[age] = f"{round(stats[age])} m²" if stats[age] > 0 else "-"
            details_rows.append(detail_row)

        # Summary Table displayed on the first page
        summary_table_data = [
            ["", self.translate("name_res_bldg"), self.translate("name_mixed_bldg"), self.translate("name_com_bldg")],
            [self.translate("name_number_bldgs"), 
             str(agg_stats[self.translate("name_res_bldg")][self.translate("name_number_bldgs")]) if agg_stats[self.translate("name_res_bldg")][self.translate("name_number_bldgs")] > 0 else "-", 
             str(agg_stats[self.translate("name_mixed_bldg")][self.translate("name_number_bldgs")]) if agg_stats[self.translate("name_mixed_bldg")][self.translate("name_number_bldgs")] > 0 else "-", 
             str(agg_stats[self.translate("name_com_bldg")][self.translate("name_number_bldgs")]) if agg_stats[self.translate("name_com_bldg")][self.translate("name_number_bldgs")] > 0 else "-"],
            [self.translate("name_total_area"), 
             f"{round(agg_stats[self.translate("name_res_bldg")][self.translate("name_total_area")])} m²" if agg_stats[self.translate("name_res_bldg")][self.translate("name_total_area")] > 0 else "-", 
             f"{round(agg_stats[self.translate("name_mixed_bldg")][self.translate("name_total_area")])} m²" if agg_stats[self.translate("name_mixed_bldg")][self.translate("name_total_area")] > 0 else "-", 
             f"{round(agg_stats[self.translate("name_com_bldg")][self.translate("name_total_area")])} m²" if agg_stats[self.translate("name_com_bldg")][self.translate("name_total_area")] > 0 else "-"]
        ]
        for age in age_classes:
            w_area = agg_stats[self.translate("name_res_bldg")][age]
            m_area = agg_stats[self.translate("name_mixed_bldg")][age]
            g_area = agg_stats[self.translate("name_com_bldg")][age]

            summary_table_data.append([
                age,
                f"{round(w_area)} m²" if w_area > 0 else "-",
                f"{round(m_area)} m²" if m_area > 0 else "-",
                f"{round(g_area)} m²" if g_area > 0 else "-"
            ])

        # General info to be displayed below the summary table on the first page
        general_info = [
            [self.translate("gen_info_nb_dwellings"), str(self.kpis.totalnumberflats)],
            [self.translate("gen_info_nb_residents"), str(self.kpis.totalnumberocc)],
            [self.translate("gen_info_postal_code_loc"), f"{str(self.data.site['zip'])}"],
            # [self.translate("gen_info_district_area"), f"{round(self.data.site['district_area'], 2)} ha"],
            [self.translate("gen_info_ref_year"), f"{str(self.data.site['TRYYear'])[3:]} / {self.data.site['TRYType']}"]
        ]

        # 4. Pack everything into the final structure
        self.district_structure = {
            "summary_table": summary_table_data,
            "general_info": general_info,
            "df_details": pd.DataFrame(details_rows)
        }
        
    def _translate_building_type(self, b_type:str) -> str:
        """Translates the building type from the data to the display name."""
        return self.translate(f"bldg_{b_type}")

    def _extract_energyhub_data(self):
        """Extracts the energyhub data for central devices."""
        try:
            capacities = self.data.centralDevices["capacities"]
            central_configs = self.data.central_device_data
            
            col_device = self.translate("table_device_colname")
            col_capacity = self.translate("table_capacity_colname")
            col_cost = self.translate("table_cost_sub_colname")
            not_selected_text = self.translate("msg_not_selected")
            
            device_list = []

            def append_energyhub_row(device_name, capacity, annual_cost):
                device_list.append({
                    col_device: device_name,
                    col_capacity: capacity,
                    col_cost: annual_cost
                })

            all_cost_devices = set(self.kpis.central_individual_devices_annualized_cost.keys())

            # Iterate through all feasible devices
            for dev, config in central_configs.items(): 
                if not isinstance(config, dict):
                    continue
                if not config.get("feasible", False):
                    continue                
                
                cap = 0
                annual_cost_sub = "-"
                annual_cost_unsub = "-"
                cost_unit = ""

                if dev in capacities:
                    spec = capacities[dev]
                    cap = round(spec["cap"], 2)
                
                    if dev in self.kpis.central_individual_devices_annualized_cost:
                        device_cost_info = self.kpis.central_individual_devices_annualized_cost[dev]
                        annual_cost_sub = round(device_cost_info["subsidized_annual_cost"], 2)
                        annual_cost_unsub = round(device_cost_info["unsubsidized_annual_cost"], 2)
                        all_cost_devices.discard(dev) # Remove this device from the set of devices as it has been processed
                        cost_unit = " €/a"


                # Get the device name and unit
                name, base_unit = self.get_central_device_name(dev)

                display_cap, display_unit = self._determine_unit(cap=cap*1000, base_unit= base_unit)

                if cap <= 0:
                    display_cap = not_selected_text
                    display_unit = ""

                # Append dict to the device list
                append_energyhub_row(
                    device_name=name,
                    capacity=f"{display_cap} {display_unit}".strip(),
                    annual_cost=f"{annual_cost_sub}{cost_unit}"
                )

            # Add all devices that are in the cost breakdown but not in the feasible central device data
            for dev in all_cost_devices:
                cost = round(self.kpis.central_individual_devices_annualized_cost[dev]['subsidized_annual_cost'], 2)
                if cost == 0:
                    continue # Skip devices that have zero cost
                elif cost > 0:
                    cost_unit = " €/a"

                name, base_unit = self.get_central_device_name(dev)
                cap = 0
                display_cap, display_unit = self._determine_unit(cap=cap*1000, base_unit=base_unit) # Convert kW to W for unit determination

                if display_cap <= 0:
                    display_cap = "-"

                append_energyhub_row(
                    device_name=name,
                    capacity=f"{display_cap} {display_unit}".strip(),
                    annual_cost=f"{cost}{cost_unit}"
                )

            # Create the DataFrame only if devices are present
            if device_list:
                self.energyhub_df = pd.DataFrame(device_list)
            else:
                self.energyhub_df = None


        except (KeyError, AttributeError) as e:
            # If no central devices are defined, set energyhub_df to None
            if "capacities" not in self.data.centralDevices: # if truly no central devices are defined
                self.energyhub_df = None
            else: 
                raise Exception(f"Error extracting energyhub data. Please check the structure of centralDevices and central_device_data in the input data.\n Caused error: {e}")

    def _extract_decentral_data(self):
        """Extracts and aggregates decentral device capacities and counts across all buildings, excluding EV."""
        try:
            aggregated_data = {}

            # 1. Iterate over all buildings and their decentral devices
            for b_index, devices in self.kpis.decentral_individual_devices_annualized_cost.items():
                for dev_name, info in devices.items():
                    # Skip Electric Vehicles and virtual measures
                    if dev_name in ["T_reduction_measures"]:
                        continue

                    # Direct access to enforce crash on missing keys
                    cap = info["cap"]
                    cost = info["subsidized_annual_cost"]
                    
                    if cap == '' or cap is None:
                        cap = 0
                        
                    cap_float = float(cap)
                    cost_float = float(cost)

                    # Initialize dictionary structure for new devices
                    if dev_name not in aggregated_data:
                        aggregated_data[dev_name] = {"count": 0, "total_cap": 0.0, "total_cost": 0.0}
                        
                    # Add to aggregate sum and increment the count
                    if dev_name == "EV":
                        ev_caps = self.data.district[int(b_index)]["user"].ev_capacity
                        if ev_caps is None:
                            ev_caps = []
                        elif isinstance(ev_caps, (int, float)):
                            ev_caps = [ev_caps]

                        ev_count = sum(1 for x in ev_caps if float(x) > 0)
                        aggregated_data[dev_name]["count"] += ev_count
                    else:
                        aggregated_data[dev_name]["count"] += 1

                    aggregated_data[dev_name]["total_cap"] += cap_float
                    aggregated_data[dev_name]["total_cost"] += cost_float

            device_list = []
            
            # 2. Format the aggregated data into a list of dictionaries for the DataFrame
            for dev_name, data in aggregated_data.items():
                name, base_unit = self.get_decentral_device_name(dev_name)
                
                if "W" in base_unit:
                    cap_for_determination = data['total_cap'] * 1000 # For devices with power or energy units the conversion requires W or Wh as input
                else:
                    cap_for_determination = data['total_cap']

                total_cap_adjusted, total_unit_adjusted = self._determine_unit(cap=cap_for_determination, base_unit=base_unit)
                total_power = f"{total_cap_adjusted} {total_unit_adjusted}".strip()  

                cost = round(data['total_cost'], 2)
                if cost == 0:
                    ann_cost = f"-"
                elif cost >0:
                    ann_cost = f"{cost} €/a"
                else:
                    raise ValueError(f"Negative cost value encountered for device {dev_name}: {cost}. Please check the input data for inconsistencies.")

                
                device_list.append({
                    self.translate("table_device_colname"): name,
                    self.translate("table_count_colname"): data["count"],
                    self.translate("table_total_cap_colname"): total_power,
                    self.translate("table_cost_colname"): ann_cost
                })
                
            # 3. Create the DataFrame
            if device_list:
                self.decentral_df = pd.DataFrame(device_list)
            else:
                self.decentral_df = None

        except AttributeError as e:
            print(f"Warning: Decentral device data could not be extracted. {e}")
            self.decentral_df = None

    def _extract_district_layout(self):
        """Extracts district layout information including building positions, network topology, and installed devices."""
        layout_data = {
            "buildings": [],
            "network_nodes": {},
            "network_edges": {},
            "pipeline_data": {}
        }

        # Extract building positions, connectivity status, and devices
        for building in self.data.district:
            features = building["buildingFeatures"]
            
            # Safely get position
            if "position" in features and isinstance(features["position"], (tuple, list)) and len(features["position"]) >= 2:
                pos = features["position"]
                
                # Check for installed devices (capacity > 0)
                installed_devices = []
                if "capacities" in building:
                    for device_name, cap in building["capacities"].items():
                        # Capacities can be either a dict {"cap": X} or a direct number
                        if isinstance(cap, dict) and "cap" in cap and float(cap["cap"]) > 0:
                            installed_devices.append(device_name)
                        elif isinstance(cap, (int, float)) and float(cap) > 0:
                            installed_devices.append(device_name)
                
                # If the heater is defined in features and not in capacities, add it
                main_heater = features["heater"]
                if main_heater not in installed_devices:
                    installed_devices.append(main_heater)

                layout_data["buildings"].append({
                    "id": building["unique_name"], # TODO: After Mixed Building Implementation change to: features["original_bldg_id"],
                    "name": building["unique_name"],
                    "x": float(pos[0]),
                    "y": float(pos[1]),
                    "type": features["building"],
                    "is_connected": main_heater == "heat_grid",
                    "devices": installed_devices
                })

        # Extract network topology if central heating network was generated
        if hasattr(self.data, 'pipeline_nodes') and self.data.pipeline_nodes:
            layout_data["network_nodes"] = self.data.pipeline_nodes
        
        if hasattr(self.data, 'pipeline_topology') and self.data.pipeline_topology:
            layout_data["network_edges"] = self.data.pipeline_topology

        if hasattr(self.data, 'pipeline') and self.data.pipeline:
            layout_data["pipeline_data"] = self.data.pipeline

        self.district_layout = layout_data

    def _extract_data(self):
        """Extracts and processes all necessary data for the certificate."""
        self._process_buildings()
        self._extract_key_performance_indicator()
        self._extract_district_structure()
        self._extract_energyhub_data()
        self._extract_decentral_data()
        self._extract_district_layout()
        # Additional data extraction methods can be added here

    def get_central_device_name(self, dev: str) -> tuple[str, str]: 
        """
        Returns the central device name and unit based on the device key. <sub>th</sub> for thermal devices and <sub>el</sub> for electric devices. If not specified, default is "W".

        Args:
            dev (str): device key (e.g. "HP", "PV").
            data (object): The data object containing central device data.

        Returns:
            tuple[str, str]: A tuple consisting of the full name and the unit.
        """
        

        device_unit_map = { # if not specified, default is "W"
            "H2S": "Wh",
            "TES": "Wh<sub>th</sub>",
            "CTES": "Wh<sub>th</sub>",
            "BAT": "Wh<sub>el</sub>",
            "GS": "Wh",
            "PV": "Wp<sub>el</sub>",
            "WT": "Wp<sub>el</sub>",
            "WAT": "W<sub>el</sub>",
            "CHP": "W<sub>el</sub>",
            "BCHP": "W<sub>el</sub>",
            "WCHP": "W<sub>el</sub>",
            "ELYZ": "W<sub>el</sub>",
            "FC": "W<sub>el</sub>",
            "STC": "Wp<sub>th</sub>",
            "HP": "W<sub>th</sub>",
            "GroundHP": "W<sub>th</sub>",
            "EB": "W<sub>th</sub>",
            "BOI": "W<sub>th</sub>",
            "GHP": "W<sub>th</sub>",
            "BBOI": "W<sub>th</sub>",
            "WBOI": "W<sub>th</sub>",
            "CC": "W<sub>th</sub>",
            "AirCC": "W<sub>th</sub>",
            "AC": "W<sub>th</sub>",
            "Heat_Grid": "W<sub>th</sub>"
        }

        name = self.translate(f"device_{dev}")
        unit = device_unit_map.get(dev, "W")

        return name, unit
    
    def get_decentral_device_name(self, dev: str) -> tuple[str, str]:
        """
        Returns the decentral device name and unit based on the device key.
        Args:
            dev (str): device key (e.g. "HP", "PV", "OBOI").
        Returns:
            tuple[str, str]: A tuple consisting of the full name and the base unit (W or Wh) without any prefixes.
        """

        device_unit_map = { 
            "BAT": "Wh<sub>el</sub>",
            "TES": "l",
            "TES_DHW": "l",
            "EV": "Wh<sub>el</sub>",
            "STC": "m²",
            "PV": "m²",
            "HP": "W<sub>th</sub>",
            "HP35": "W<sub>th</sub>",
            "HP55": "W<sub>th</sub>",
            "EH": "W<sub>th</sub>",
            "EH_DHW": "W<sub>th</sub>",
            "CHP": "W<sub>th</sub>",
            "BOI": "W<sub>th</sub>",
            "BBOI": "W<sub>th</sub>",
            "OBOI": "W<sub>th</sub>",
            "H2BOI": "W<sub>th</sub>",
            "FC": "W<sub>th</sub>",
            "DH": "W<sub>th</sub>",
            "heat_grid": "W<sub>th</sub>",
            "CC": "W<sub>th</sub>"
        }

        # All devices
        name = self.translate(f"device_{dev}")
        base_unit = device_unit_map.get(dev, "W")
        return name, base_unit
    
    @staticmethod
    def _determine_unit(cap: float, base_unit: str) -> tuple[float, str]:
        """
        Determines the appropriate unit (kW, MW, GW) based on the capacity value and the base unit. 
        Input cap is expected to be in W/Wh/m²/l.

        Args:
            cap (float): The capacity value in W/Wh/m²/l.
            base_unit (str): The base unit (e.g., "W", "Wh", "m²", "l"). Does allow suffixes like "W<sub>th</sub>".

        Returns:
            tuple[float, str]: A tuple containing the adjusted capacity and the appropriate unit.
        """

        if base_unit == "m²":
            if cap >= 10000:
                adjusted_cap = round(cap / 10000, 2)
                adjusted_unit = "ha"  # Hectar for large areas
            else:
                adjusted_cap = round(cap, 2)
                adjusted_unit = base_unit
                
        elif base_unit == "l":
            if cap >= 1000:
                adjusted_cap = round(cap / 1000, 2)
                adjusted_unit = "m³"  # Cubic meters for large volumes
            else:
                adjusted_cap = int(round(cap, 0))
                adjusted_unit = "l"
                
        elif cap <= 0:
            adjusted_cap = cap
            adjusted_unit = base_unit  
            
        elif cap >= 1000000000:
            adjusted_cap = round(cap / 1000000000, 2)
            adjusted_unit = "G" + base_unit  # Giga
        elif cap >= 1000000:
            adjusted_cap = round(cap / 1000000, 2)
            adjusted_unit = "M" + base_unit  # Mega
        elif cap >= 1000:
            adjusted_cap = round(cap / 1000, 2)
            adjusted_unit = "k" + base_unit  # Kilo
        else:
            adjusted_cap = round(cap, 2)
            adjusted_unit = base_unit

        return adjusted_cap, adjusted_unit


    def get_key_performance_indicator(self):
        return self.key_performance_indicator

    def get_optimization_results(self):
        return self.optimization_results

    def get_district_structure(self):
        return self.district_structure
    
    def get_building_df(self):
        return self.building_df

    def get_energyhub_df(self):
        return self.energyhub_df

    def get_decentral_df(self):
        return self.decentral_df
    
    def get_district_layout(self):
        return self.district_layout

    def get_scenario_name(self):
        return self.data.scenario_name

################################################################################
# Certificate Builder
################################################################################
