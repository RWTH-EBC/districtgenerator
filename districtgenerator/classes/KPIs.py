# -*- coding: utf-8 -*-

import sys
import numpy as np
import pandas as pd
import os
import json
import math
import reportlab
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.graphics.shapes import *
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.legends import Legend
from datetime import datetime
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph
from itertools import zip_longest


class KPIs:

    def __init__(self, data):
        """
        Constructor of KPIs class.

        Parameters
        ----------
        data : Datahandler object
            Datahandler object which contains all relevant information to compute the key performance indicators (KPIs).
        decentral_config : dict
            Dict containing the decentral configuration parameters.

        Returns
        -------
        None.
        """
        # initialize KPIs
        self.sum_res_load = None
        self.sum_res_inj = None
        self.sum_res_gas = None
        self.residualLoad = None
        self.peakDemand = None
        self.peakInjection = None
        self.peakToValley = None
        self.supplyCoverFactor = None
        self.demandCoverFactor = None
        self.operationCosts = None
        self.co2emissions = None
        self.W_inj_GCP_year = None
        self.W_dem_GCP_year = None
        self.Gas_year = None
        self.dcf_year = None
        self.scf_year = None
        self.annual_fixed_costs_decentral = None
        self.annual_fixed_costs_central = None
        self.totalarea_residential = None
        self.totalarea_non_residential = None
        self.totalheatload = None
        self.totalcoolingload = None
        self.totalnumberflats = None
        self.totalnumberocc = None
        self.total_heating_demand = None
        self.total_cooling_demand = None
        self.total_electricity_demand = None
        self.total_dhw_demand = None

        # Data structure for per-building metrics
        self.kpis_per_building = {bid: {} for bid in data.scenario["id"]}

        # initialize input data for calculation of KPIs
        inputData = {}
        
        # Information about simulated years
        inputData["simulated_years"] = data.ecoData["interpolation_points"]
        inputData["sim_ecoData"] = data.all_sim_ecoData

        # information about clusters
        inputData["clusters"] = data.clusters
        inputData["clusterWeights"] = data.clusterWeights
        inputData["clusterAssignments"] = data.clusterAssignments

        # number of represented intervals
        inputData["nbIntervals"] = sum(inputData["clusterWeights"][c] for c in inputData["clusters"])

        # prepare the results of the optimizations for each cluster
        inputData["resultsOptimization"] = data.resultsOptimization
        inputData["district"] = data.district

        self.inputData = inputData

        # Execute calculations
        self.calculateAllKPIs(data)

    def prepareData(self, data):
        """
        Prepare the data to compute the KPIs demand and supply cover factor
        as well as the ratio of renewable electricity generation.

        Parameters
        ----------
        data : Datahandler object
            Datahandler object which contains all relevant information to compute the key performance indicators (KPIs).

        Returns
        -------
        None.
        """
        self.sum_res_load = {}
        self.sum_res_inj = {}
        self.sum_res_gas = {}

        for year in self.inputData["simulated_years"]:
            self.sum_res_load[year] = np.zeros([len(data.clusters), len(data.district[0]["user"].elec_cluster[0])])
            self.sum_res_inj[year] = np.zeros([len(data.clusters), len(data.district[0]["user"].elec_cluster[0])])
            self.sum_res_gas[year] = np.zeros([len(data.clusters), len(data.district[0]["user"].elec_cluster[0])])

        for year in self.inputData["simulated_years"]:
            for c in range(len(self.inputData["clusters"])):
                for bldg_id in data.scenario["id"]:
                    idx = data.building_dict[int(bldg_id)]
                    self.sum_res_load[year][c, :] += np.array(
                        self.inputData["resultsOptimization"][year][c][idx]["res_load"])
                    self.sum_res_inj[year][c, :] += np.array(
                        self.inputData["resultsOptimization"][year][c][idx]["res_inj"])
                    self.sum_res_gas[year][c, :] += np.array(
                        self.inputData["resultsOptimization"][year][c][idx].get("res_gas", 0))

    def calculateResidualLoad(self, data):
        """
        Calculate residual load at grid connection point (GCP) in [kW] for each year.
        Demand is positive and injection negative.

        Returns
        -------
        None.
        """
        self.residualLoad = {}

        # loop over cluster and change unit from [W] to [kW]
        for year in self.inputData["simulated_years"]:
            res = np.zeros([len(self.inputData["clusters"]), len(data.district[0]["user"].elec_cluster[0])])
            for c in range(len(self.inputData["clusters"])):
                for t in range(len(data.district[0]["user"].elec_cluster[0])):
                    res[c, t] = self.inputData["resultsOptimization"][year][c]["P_dem_gcp"][t] - \
                                self.inputData["resultsOptimization"][year][c]["P_inj_gcp"][t]
            self.residualLoad[year] = res / 1000

    def calculatePeakLoad(self):
        """
        Calculate peak demand and peak injection at grid connection point (GCP) in [kW] for each year.

        Returns
        -------
        None.
        """
        self.peakDemand = {}
        self.peakInjection = {}
        for year in self.inputData["simulated_years"]:
            # maximal load [kW]
            self.peakDemand[year] = round(np.max(self.residualLoad[year]), 3)
            # maximal injection [kW]
            self.peakInjection[year] = round(abs(np.min(self.residualLoad[year])), 3)

    def calculatePeakToValley(self):
        """
        Calculate the difference between the maximum and the minimum of the residual load in [kW] for each year.

        Returns
        -------
        None.
        """
        self.peakToValley = {}
        for year in self.inputData["simulated_years"]:
            PtV = np.zeros(len(self.inputData["clusters"]))
            for c in range(len(self.inputData["clusters"])):
                PtV[c] = round(max(self.residualLoad[year][c, :]) - min(self.residualLoad[year][c, :]), 3)
            # peak to valley for each time period[kW]
            self.peakToValley[year] = max(PtV)

    def calculateEnergyExchangeGCP(self, data):
        """
        Calculate energy exchange of the district with its environment in [kWh] for each year.
        """

        # electricity feed into and covered by superordinated grid for one year [kWh]
        self.W_inj_GCP_year = {}
        self.W_dem_GCP_year = {}
        self.gas_year = {}
        self.biomass_year = {}
        self.waste_year = {}
        self.hydrogen_year = {}
        self.oil_year = {}
        self.districtHeat_year = {}

        for year in self.inputData["simulated_years"]:
            # Electricity [kWh] feed into the superordinated grid
            self.W_inj_GCP_year[year] = 0
            # Electricity [kWh] covered by the superordinated grid
            self.W_dem_GCP_year[year] = 0

            # Fuel consumption [kWh]
            self.gas_year[year] = 0
            self.biomass_year[year] = 0
            self.waste_year[year] = 0
            self.hydrogen_year[year] = 0
            self.oil_year[year] = 0

            # District heat consumption [kWh]
            self.districtHeat_year[year] = 0

            for c in range(len(self.inputData["clusters"])):
                weight = self.inputData["clusterWeights"][self.inputData["clusters"][c]]
                self.W_dem_GCP_year[year] += (sum(self.inputData["resultsOptimization"][year][c]["P_dem_gcp"]) *
                                              data.time["timeResolution"] / 3600 / 1000) * weight
                self.W_inj_GCP_year[year] += (sum(self.inputData["resultsOptimization"][year][c]["P_inj_gcp"]) *
                                              data.time["timeResolution"] / 3600 / 1000) * weight
                self.gas_year[year] += (sum(self.inputData["resultsOptimization"][year][c]["P_gas_total"]) * data.time[
                    "timeResolution"] / 3600 / 1000) * weight
                self.biomass_year[year] += (sum(self.inputData["resultsOptimization"][year][c]["P_biomass_total"]) *
                                            data.time["timeResolution"] / 3600 / 1000) * weight
                self.waste_year[year] += (sum(self.inputData["resultsOptimization"][year][c]["P_waste_total"]) *
                                          data.time["timeResolution"] / 3600 / 1000) * weight
                self.hydrogen_year[year] += (sum(self.inputData["resultsOptimization"][year][c]["P_hydrogen_total"]) *
                                             data.time["timeResolution"] / 3600 / 1000) * weight
                self.oil_year[year] += (sum(self.inputData["resultsOptimization"][year][c]["P_oil_total"]) * data.time[
                    "timeResolution"] / 3600 / 1000) * weight
                self.districtHeat_year[year] += (sum(
                    self.inputData["resultsOptimization"][year][c]["P_district_heat_total"]) * data.time[
                                                     "timeResolution"] / 3600 / 1000) * weight

    def calculateEnergyExchangeWithinDistrict(self, data):
        """
        Calculate energy exchange within the district in [kWh] for each year.

        Returns
        -------
        None.
        """
        self.W_inj_buildings_year = {}
        self.W_dem_buildings_year = {}

        for year in self.inputData["simulated_years"]:
            self.W_inj_buildings_year[year] = 0
            self.W_dem_buildings_year[year] = 0
            for c in range(len(self.inputData["clusters"])):
                weight = self.inputData["clusterWeights"][self.inputData["clusters"][c]]
                self.W_dem_buildings_year[year] += sum(
                    self.sum_res_load[year][c, :] * data.time["timeResolution"] / 3600 / 1000) * weight
                self.W_inj_buildings_year[year] += sum(
                    self.sum_res_inj[year][c, :] * data.time["timeResolution"] / 3600 / 1000) * weight

    def calculateCoverFactors(self, data):
        """
        Calculate the ratio between the self-consumed electricity and the total electricity demand for each year.
        Only uses residual loads and injections. Does not consider direct consumption within buildings.

        Returns
        -------
        None.
        """
        self.supplyCoverFactor = {}
        self.demandCoverFactor = {}

        self.dcf_year = {}
        self.scf_year = {}

        sum_ClusterWeights = sum(self.inputData["clusterWeights"][self.inputData["clusters"][c]] for c in
                                 range(len(self.inputData["clusters"])))

        for year in self.inputData["simulated_years"]:
            self.supplyCoverFactor[year] = np.zeros(len(self.inputData["clusters"]))
            self.demandCoverFactor[year] = np.zeros(len(self.inputData["clusters"]))
            self.dcf_year[year] = 0
            self.scf_year[year] = 0

            min_val = np.zeros([len(self.inputData["clusters"]), len(data.district[0]["user"].elec_cluster[0])])
            nenner_sup = np.zeros([len(self.inputData["clusters"]), len(data.district[0]["user"].elec_cluster[0])])
            nenner_dem = np.zeros([len(self.inputData["clusters"]), len(data.district[0]["user"].elec_cluster[0])])

            for c in range(len(self.inputData["clusters"])):
                for t in range(len(data.district[0]["user"].elec_cluster[0])):
                    a = 0
                    b = 0
                    # sum of all buildings for each timestep
                    for bldg_id in data.scenario["id"]:
                        idx = data.building_dict[int(bldg_id)]
                        a += self.inputData["resultsOptimization"][year][c][idx]["res_load"][t]
                        b += self.inputData["resultsOptimization"][year][c][idx]["res_inj"][t]
                    # At the same time step t, either res_load or res_inj should be 0.
                    # However, a and b could both be greater than 0 at the same time step t,
                    # since they represent the sums of all the buildings.
                    # If both a and b are greater than 0, it means electricity is being transported from one building to another.
                    # sum of all timesteps
                    nenner_dem[c, t] += a
                    nenner_sup[c, t] += b
                    min_val[c, t] = np.min([a, b])

                self.demandCoverFactor[year][c] = np.sum(min_val[c, :]) / np.sum(nenner_dem[c, :]) if np.sum(
                    nenner_dem[c, :]) else 0
                self.supplyCoverFactor[year][c] = np.sum(min_val[c, :]) / np.sum(nenner_sup[c, :]) if np.sum(
                    nenner_sup[c, :]) else 0

                # Calculate weighted average over all years
                weight = self.inputData["clusterWeights"][self.inputData["clusters"][c]] / sum_ClusterWeights
                self.dcf_year[year] += self.demandCoverFactor[year][c] * weight
                self.scf_year[year] += self.supplyCoverFactor[year][c] * weight

    def calc_annual_cost_total(self, data):
        """
        Calculate the total annualized costs of the devices in the district for each year. This includes both decentralized and central devices.

        Returns
        -------
        None.
        """
        scenario = data.scenario
        decentral_device_data = data.decentral_device_data
        district = data.district
        physics = data.physics

        # Filter only investable devices based on the dictionary
        investable_devices_list = [dev for dev, properties in decentral_device_data.items() if 'inv_var' in properties]

        self.annual_fixed_costs_decentral = 0
        self.annual_fixed_costs_decentral_unsubsidized = 0
        self.decentral_individual_devices_annualized_cost = {}

        # Iteration over all buildings
        for n, building_id in enumerate(scenario["id"]):
            self.decentral_individual_devices_annualized_cost[n] = {}
            if 'costs' not in self.kpis_per_building[building_id]:
                self.kpis_per_building[building_id]['costs'] = {}

            building_annual_cost = 0
            building_annual_cost_unsub = 0

            capacities = {
                "BOI": district[n]["capacities"].get("BOI", 0) / 1000,
                "BBOI": district[n]["capacities"].get("BBOI", 0) / 1000,
                "H2BOI": district[n]["capacities"].get("H2BOI", 0) / 1000,
                "OBOI": district[n]["capacities"].get("OBOI", 0) / 1000,
                "HP": district[n]["capacities"].get("HP", 0) / 1000,
                "EH": district[n]["capacities"].get("EH", 0) / 1000,
                "CHP": district[n]["capacities"].get("CHP", 0) / 1000,
                "FC": district[n]["capacities"].get("FC", 0) / 1000,
                "DH": district[n]["capacities"].get("DH", 0) / decentral_device_data.get("DH", {}).get("eta_th",
                                                                                                       1) / 1000,
                "PV": district[n]["capacities"].get("PV", {}).get("area", 0),
                "STC": district[n]["capacities"].get("STC", {}).get("area", 0),
                "EV": district[n]["capacities"].get("EV", 0) / 1000,
                "BAT": district[n]["capacities"].get("BAT", 0) / 1000,
                "TES": (district[n]["capacities"].get("TES", 0) / physics["rho_water"] / physics[
                    "c_p_water"] / decentral_device_data.get("TES", {}).get("T_diff_max",
                                                                            1) * 3600) if "TES" in decentral_device_data else 0
            }

            # HP temperature measures
            if capacities.get("HP", 0) > 0 and district[n]["envelope"].hp_measures:
                heatload_kw = district[n]["envelope"].heatload / 1000
                inv_eur_per_kw = decentral_device_data["HP"]["measures_inv_fix"]
                ann_cost_meas = self.calc_annualized_investment(inv_eur_per_kw * heatload_kw, data.ecoData)

                building_annual_cost += ann_cost_meas
                building_annual_cost_unsub += ann_cost_meas

                self.decentral_individual_devices_annualized_cost[n]["T_reduction_measures"] = {
                    "cap": heatload_kw, "subsidized_annual_cost": ann_cost_meas,
                    "unsubsidized_annual_cost": ann_cost_meas
                }
                self.kpis_per_building[building_id]['costs']['annual_cost_HP_measures_eur'] = ann_cost_meas

            # Loop dynamically over investable devices
            for dev in investable_devices_list:
                cap = capacities.get(dev, 0)
                if cap > 0:
                    subsidized_cost = self.calc_annual_cost_device(decentral_device_data[dev], data.ecoData, cap,
                                                                   mode="subsidized")
                    unsubsidized_cost = self.calc_annual_cost_device(decentral_device_data[dev], data.ecoData, cap,
                                                                     mode="unsubsidized")

                    if dev == "EH" and capacities.get("HP", 0) > 0:
                        subsidized_cost = 0.0
                        unsubsidized_cost = 0.0

                    building_annual_cost += subsidized_cost
                    building_annual_cost_unsub += unsubsidized_cost

                    self.decentral_individual_devices_annualized_cost[n][dev] = {
                        "cap": cap, "subsidized_annual_cost": subsidized_cost,
                        "unsubsidized_annual_cost": unsubsidized_cost
                    }
                    self.kpis_per_building[building_id]['costs'][f'annual_cost_{dev}_eur'] = subsidized_cost

            self.kpis_per_building[building_id]['costs']['annual_fixed_costs_eur'] = building_annual_cost
            self.annual_fixed_costs_decentral += building_annual_cost
            self.annual_fixed_costs_decentral_unsubsidized += building_annual_cost_unsub

        # Central devices
        self.central_individual_devices_annualized_cost = {}
        try:
            self.annual_fixed_costs_central = data.centralDevices["capacities"]["total_ann_inv_cost"] + \
                                              data.centralDevices["capacities"]["total_om_cost"]
            self.annual_fixed_costs_central_unsubsidized = data.centralDevices["capacities"][
                                                               "total_ann_inv_cost_unsubsidized"] + \
                                                           data.centralDevices["capacities"]["total_om_cost"]

            if hasattr(data, 'centralDevices') and 'capacities' in data.centralDevices:
                for dev_name, dev_spec in data.centralDevices["capacities"].items():
                    if not isinstance(dev_spec, dict) or dev_spec.get("cap", 0) <= 0:
                        continue
                    total_subsidized = dev_spec.get("ann_inv_cost", 0) + dev_spec.get("om_cost", 0)
                    total_unsubsidized = dev_spec.get("ann_inv_cost_unsubsidized", 0) + dev_spec.get("om_cost", 0)
                    self.central_individual_devices_annualized_cost[dev_name] = {
                        "cap": dev_spec.get("cap", 0), "subsidized_annual_cost": total_subsidized,
                        "unsubsidized_annual_cost": total_unsubsidized
                    }

            if hasattr(data, 'heat_grid_data') and data.heat_grid_data:
                heat_grid_cost = data.heat_grid_data.get("ann_costs", 0) + data.heat_grid_data.get("om_costs", 0)
                if heat_grid_cost > 0:
                    self.central_individual_devices_annualized_cost["Heat_Grid"] = {
                        "cap": '', "subsidized_annual_cost": heat_grid_cost, "unsubsidized_annual_cost": heat_grid_cost
                    }
        except KeyError:
            self.annual_fixed_costs_central = 0
            self.annual_fixed_costs_central_unsubsidized = 0

    def calc_annual_cost_device(self, dev, ecoData, cap, mode="subsidized"):
        """
        Calculation of total investment costs including replacements (based on VDI 2067-1, pages 16-17).

        Parameters
        ----------
        dev : dictionary
            technology parameter
        ecoData : dictionary
            economic parameters (interest_rate, observation_time)
        cap: float
            installed capacity of the device [kW]
        mode: str, optional
            calculation mode. The default is "subsidized". Alternative 'unsubsidized' (without subsidies).

        Returns
        -------
        annualized fix and variable investment
        """

        # Projektlaufzeit (observation_time)
        # Zinssatz (für Kapitalkosten) (interest_rate)
        # Anschaffungskosten inkl. Installation, etc. [€/kW]
        # Lebensdauer (life_time) [years]
        # Betriebs- und Wartungskosten (operation and maintenance costs, c_om) [% of Invest]

        # Values from Technikkatalog (Langreder et al. 2024):
        # Langreder, Nora; Lettow, Frederik; Sahnoun, Malek; Kreidelmeyer, Sven; Wünsch, Aurel; Lengning, Saskia et al.
        # (2024): Technikkatalog Wärmeplanung. Hg. v. ifeu – Institut für Energie- und Umweltforschung Heidelberg,
        # Öko-Institut e.V., IER Stuttgart, adelphi consult GmbH, Becker Büttner Held PartGmbB, Prognos AG, et al.
        # Online available at:
        # https://api.kww-halle.de/fileadmin/user_upload/Technikkatalog_W%C3%A4rmeplanung_Version_1.1_August24.xlsx

        observation_time = ecoData["observation_time"]
        interest_rate = ecoData["interest_rate"]
        q = 1 + ecoData["interest_rate"]

        # Calculate capital recovery factor
        CRF = ((q ** observation_time) * interest_rate) / ((q ** observation_time) - 1)

        # Get device life time
        life_time = dev["life_time"]

        # Number of required replacements
        n = int(math.floor(observation_time / life_time))

        # Investment for replacements
        invest_replacements = sum((q ** (-i * life_time)) for i in range(1, n + 1))

        # Residual value of final replacement
        res_value = ((n + 1) * life_time - observation_time) / life_time * (q ** (-observation_time))

        # Calculate annualized investments
        if life_time > observation_time:
            ann_factor = (1 - res_value) * CRF
        else:
            ann_factor = (1 + invest_replacements - res_value) * CRF

        # Save capital recovery factor
        # param["CRF"] = CRF

        # Total investment costs

        inv_unsubsidized = dev["inv_base"] * cap
        inv_subsidized = dev["inv_var"] * cap

        # Annualized investment costs
        if mode == "subsidized":
            c_inv = inv_subsidized * ann_factor
        elif mode == "unsubsidized":
            c_inv = inv_unsubsidized * ann_factor

        c_om = 0 # Operation, maintenance and capacity costs

        if dev.get("cost_om", None) is not None:
            # operation and maintenance costs [€/(a*€_invested)] Always use the unsubsidized investment for O&M calculation
            c_om += dev["cost_om"] * inv_unsubsidized
        if dev.get("cap_fee", None) is not None:
            c_om += dev["cap_fee"] * cap # if a Capacity fee exists [€/(kW*a)]

        # Total annual cost
        return c_inv + c_om

    def calc_annualized_investment(self, inv_total, ecoData):
        """
        Annualize a one-time investment (no replacements, no O&M).
        """
        observation_time = ecoData["observation_time"]
        interest_rate = ecoData["interest_rate"]
        q = 1 + interest_rate
        # Capital recovery factor
        CRF = ((q ** observation_time) * interest_rate) / ((q ** observation_time) - 1)
        return inv_total * CRF

    def calculateOperationCosts(self, data):
        """
                Calculate the operation cost for each simulated year in [€].

                Returns
                -------
                None.
                """

        # list with central operation costs for each cluster in each year [€]
        self.operationCosts = {}
        for year in self.inputData["simulated_years"]:
            temp_operationCosts = 0
            for c in range(len(self.inputData["clusters"])):
                temp_operationCosts += self.inputData["resultsOptimization"][year][c]["Cost_total"] * \
                                       self.inputData["clusterWeights"][self.inputData["clusters"][c]]
            # central operation costs for each year [€]
            self.operationCosts[year] = round(temp_operationCosts, 0)

    def calculateCO2emissions(self, data):
        """
        Calculate the CO2 emissions for each simulated year in [kg].

        Returns
        -------
        None.
        """
        self.co2emissions = {}
        for year in self.inputData["simulated_years"]:
            ecoData = data.all_sim_ecoData[year]

            # CO2 emissions [kg/a]
            co2_dem_grid = self.W_dem_GCP_year[year] * ecoData["co2_el_grid"] / 1000
            co2_gas = self.gas_year[year] * ecoData["co2_gas"] / 1000
            co2_biom = self.biomass_year[year] * ecoData["co2_biom"] / 1000
            co2_waste = self.waste_year[year] * ecoData["co2_waste"] / 1000
            co2_hydrogen = self.hydrogen_year[year] * ecoData["co2_hydrogen"] / 1000
            co2_oil = self.oil_year[year] * ecoData["co2_oil"] / 1000
            co2_district_heat = self.districtHeat_year[year] * ecoData["co2_district_heat"] / 1000

            # total CO2 emissions [kg/a]
            total_co2 = co2_dem_grid + co2_gas + co2_biom + co2_waste + co2_hydrogen + co2_oil + co2_district_heat

            # CO2 emissions for each simulated year
            self.co2emissions[year] = {
                # ! Save individual contributions for possible later use. Important: Do not sum all values. Comined already included.
                "total_co2": total_co2, "co2_dem_grid": co2_dem_grid, "co2_gas": co2_gas,
                "co2_biom": co2_biom, "co2_waste": co2_waste, "co2_hydrogen": co2_hydrogen,
                "co2_oil": co2_oil, "co2_district_heat": co2_district_heat
            }

    def calculateAutonomy(self):
        """
        Calculation of the ratio of operating time in which the local electricity demand is completely covered
        by electricity generation in the district for each simulated year.

        Returns
        -------
        None.
        """
        self.energy_autonomy = {}
        self.energy_autonomy_year = {}
        # Clalculate cluster weights sum once
        sum_ClusterWeights = sum(self.inputData["clusterWeights"][self.inputData["clusters"][c]] for c in
                                 range(len(self.inputData["clusters"])))

        # Loop over each simulated year
        for year in self.inputData["simulated_years"]:
            energy_autonomy_clusters = np.zeros(len(self.inputData["clusters"]))
            for c in range(len(self.inputData["clusters"])):
                total_timesteps = self.residualLoad[year][c, :].size
                y = np.sum(self.residualLoad[year][c, :] > 0)
                energy_autonomy_clusters[c] = 1 - (y / total_timesteps)

            # Store per-cluster autonomy for this year
            self.energy_autonomy[year] = energy_autonomy_clusters
            # Calculate weighted average for this year
            self.energy_autonomy_year[year] = sum(energy_autonomy_clusters[c] * (
                        self.inputData["clusterWeights"][self.inputData["clusters"][c]] / sum_ClusterWeights) for c in
                                                  range(len(self.inputData["clusters"])))

    def calc_total_areas_and_demands(self, data):
        """
        Calculate total areas and demands of the district.
        Stores additionally per-building KPIs in the self.kpis_per_building dictionary.

        Parameters
        ----------
        data : Datahandler object
            Datahandler object which contains all relevant information to compute the key performance indicators (KPIs).

        Returns
        -------
        None.
        """
        total_area_residential, total_area_non_residential = 0, 0
        total_number_flats, total_number_occ = 0, 0
        total_heat_load, total_cooling_load = 0, 0
        total_heating_demand, total_cooling_demand = 0, 0
        total_electricity_demand, total_EV_demand, total_dhw_demand = 0, 0, 0
        total_ICE_fuel_liters = 0

        sum_electricity_profile, sum_EV_profile, sum_heat_profile, sum_cool_profile, sum_dhw_profile = [], [], [], [], []

        for i, building in enumerate(data.district):
            building_id = data.scenario["id"][i]
            b_kpis = self.kpis_per_building[building_id]

            b_kpis['heating_system'] = building["buildingFeatures"].get("heater", "N/A")
            active_technologies = {}
            building_technologies = building.get('capacities', {})

            for tech_name, tech_value in building_technologies.items():
                if isinstance(tech_value, (int, float)) and tech_value > 0:
                    active_technologies[tech_name] = {"capacity": tech_value}
                elif isinstance(tech_value, dict) and tech_name != "inv":
                    tech_details = {k: v for k, v in tech_value.items() if v > 0}
                    if tech_details:
                        active_technologies[tech_name] = tech_details
            b_kpis['active_technologies'] = active_technologies

            if building["buildingFeatures"]["building"] in {"SFH", "MFH", "TH", "AB"}:
                total_area_residential += building["buildingFeatures"]["area"]
                total_number_flats += building["user"].nb_flats
                total_number_occ += sum(building["user"].nb_occ)
                b_kpis['area_m2'] = building["buildingFeatures"]["area"]
                b_kpis['building_type'] = "residential"
            else:
                total_area_non_residential += building["buildingFeatures"]["area"]
                b_kpis['area_m2'] = building["buildingFeatures"]["area"]
                b_kpis['building_type'] = "non_residential"

            total_ICE_fuel_liters += np.sum(building["user"].ice_carprofile)
            heat_load = building["envelope"].heatload + building["envelope"].dhwpower
            cooling_load = max(building["user"].cooling)
            total_heat_load += heat_load
            total_cooling_load += cooling_load

            b_kpis['total_heat_load_kW'] = heat_load / 1000
            b_kpis['cooling_load_kW'] = cooling_load / 1000
            b_kpis['heat_load_kW'] = building["envelope"].heatload / 1000
            b_kpis["dhw_power_kW"] = building["envelope"].dhwpower / 1000

            heating_demand = sum(building["user"].heat)
            cooling_demand = sum(building["user"].cooling)
            electricity_demand = sum(building["user"].elec)
            ev_demand = sum(building["user"].EV_carprofile)
            dhw_demand = sum(building["user"].dhw)

            total_heating_demand += heating_demand
            total_cooling_demand += cooling_demand
            total_electricity_demand += electricity_demand
            total_EV_demand += ev_demand
            total_dhw_demand += dhw_demand

            b_kpis['annual_heating_demand_kWh'] = heating_demand / 1000
            b_kpis['annual_cooling_demand_kWh'] = cooling_demand / 1000
            b_kpis['annual_electricity_demand_kWh'] = electricity_demand / 1000
            b_kpis['annual_ev_demand_kWh'] = ev_demand / 1000
            b_kpis['annual_dhw_demand_kWh'] = dhw_demand / 1000

            sum_electricity_profile = [sum(x) for x in
                                       zip_longest(sum_electricity_profile, building["user"].elec, fillvalue=0)]
            sum_EV_profile = [sum(x) for x in zip_longest(sum_EV_profile, building["user"].EV_carprofile, fillvalue=0)]
            sum_heat_profile = [sum(x) for x in zip_longest(sum_heat_profile, building["user"].heat, fillvalue=0)]
            sum_cool_profile = [sum(x) for x in zip_longest(sum_cool_profile, building["user"].cooling, fillvalue=0)]
            sum_dhw_profile = [sum(x) for x in zip_longest(sum_dhw_profile, building["user"].dhw, fillvalue=0)]

        self.totalarea_residential = total_area_residential
        self.totalarea_non_residential = total_area_non_residential
        self.totalnumberflats = total_number_flats
        self.totalnumberocc = total_number_occ
        self.totalheatload = total_heat_load
        self.totalcoolingload = total_cooling_load
        self.total_heating_demand = total_heating_demand
        self.total_cooling_demand = total_cooling_demand
        self.total_electricity_demand = total_electricity_demand
        self.total_EV_demand = total_EV_demand
        self.total_dhw_demand = total_dhw_demand
        self.total_electricity_peak = max(sum_electricity_profile) if sum_electricity_profile else 0
        self.total_heat_peak = max(sum_heat_profile) if sum_heat_profile else 0
        self.total_dhw_peak = max(sum_dhw_profile) if sum_dhw_profile else 0
        self.total_cooling_peak = max(sum_cool_profile) if sum_cool_profile else 0
        self.total_EV_peak = max(sum_EV_profile) if sum_EV_profile else 0
        self.total_ICE_fuel_liters = float(total_ICE_fuel_liters)

    def calculate_per_building_kpis(self, data):

        time_res_h = data.time["timeResolution"] / 3600
        eco = data.ecoData

        for i, building_id in enumerate(data.scenario["id"]):
            if building_id not in self.kpis_per_building:
                self.kpis_per_building[building_id] = {}
            b_kpis = self.kpis_per_building[building_id]

            for year_idx, year in enumerate(self.inputData["simulated_years"]):
                if year not in b_kpis:
                    b_kpis[year] = {}
                b_kpis[year]['tech'] = {}
                b_kpis[year]['eco'] = {}

                # Helpers to resolve dynamic prices
                def get_yearly_val(val_list, idx):
                    return val_list[idx] if isinstance(val_list, list) else val_list

                curr_price_gas = get_yearly_val(eco["price_supply_gas"], year_idx)
                curr_price_el = get_yearly_val(eco["price_supply_el"], year_idx)
                curr_price_biom = get_yearly_val(eco.get("price_biomass", 0), year_idx)
                curr_rev_feed_el = get_yearly_val(eco["revenue_feed_in_el"], year_idx)
                curr_co2_gas = get_yearly_val(eco["co2_gas"], year_idx)
                curr_co2_el = get_yearly_val(eco["co2_el_grid"], year_idx)
                curr_co2_biom = get_yearly_val(eco.get("co2_biom", 0), year_idx)
                curr_price_oil = get_yearly_val(eco.get("price_oil", 0), year_idx)
                curr_co2_oil = get_yearly_val(eco.get("co2_oil", 0), year_idx)
                curr_price_hydrogen = get_yearly_val(eco.get("price_hydrogen", 0), year_idx)
                curr_co2_hydrogen = get_yearly_val(eco.get("co2_hydrogen", 0), year_idx)

                annual_demand_from_grid, annual_injection_to_grid = 0, 0
                annual_gross_generation, annual_gross_demand = 0, 0
                timesteps_autonomous = 0
                annual_gas, annual_biom, annual_oil, annual_hydrogen = 0, 0, 0, 0
                building_peak_demand_kw, building_peak_inj_kw = 0, 0

                for c_idx, c_name in enumerate(self.inputData["clusters"]):
                    cluster_weight = self.inputData["clusterWeights"][c_name]
                    res = self.inputData["resultsOptimization"][year][c_idx][building_id]

                    res_load_kw = np.array(res["res_load"]) / 1000
                    max_in_cluster_load = np.max(res_load_kw)
                    if max_in_cluster_load > building_peak_demand_kw:
                        building_peak_demand_kw = max_in_cluster_load

                    res_inj_kw = np.array(res["res_inj"]) / 1000
                    max_in_cluster_inj = np.max(res_inj_kw)
                    if max_in_cluster_inj > building_peak_inj_kw:
                        building_peak_inj_kw = max_in_cluster_inj

                    res_load_kwh = np.sum(res["res_load"]) / 1000 * time_res_h
                    res_inj_kwh = np.sum(res["res_inj"]) / 1000 * time_res_h

                    annual_demand_from_grid += res_load_kwh * cluster_weight
                    annual_injection_to_grid += res_inj_kwh * cluster_weight
                    annual_gas += (np.sum(res.get("res_gas", 0)) / 1000 * time_res_h) * cluster_weight
                    annual_biom += (np.sum(res.get("res_biomass", 0)) / 1000 * time_res_h) * cluster_weight
                    annual_oil += (np.sum(res.get("res_oil", 0)) / 1000 * time_res_h) * cluster_weight
                    annual_hydrogen += (np.sum(res.get("res_hydrogen", 0)) / 1000 * time_res_h) * cluster_weight

                    # Gross Generation
                    gen_pv = np.array(res.get("PV", {}).get("P_el", 0))
                    gen_chp = np.array(res.get("CHP", {}).get("P_el", 0))
                    gen_fc = np.array(res.get("FC", {}).get("P_el", 0))
                    bat_power = np.array(res.get("BAT", {}).get("P_el", 0))
                    gross_gen_ts = gen_pv + gen_chp + gen_fc + np.maximum(0, bat_power)

                    # Gross Demand
                    demand_base = np.array(res.get("Elec_dem", {}).get("P_el", 0))
                    demand_hp = np.array(res.get("HP", {}).get("P_el", 0))
                    demand_eh = np.array(res.get("EH", {}).get("P_el", 0))
                    demand_ev = np.array(res.get("EV", {}).get("P_el", 0))
                    demand_cc = np.array(res.get("CC", {}).get("P_el", 0))
                    gross_demand_ts = demand_base + demand_hp + demand_eh + demand_cc + demand_ev + np.maximum(0,
                                                                                                               -bat_power)

                    annual_gross_generation += (np.sum(gross_gen_ts) / 1000 * time_res_h) * cluster_weight
                    annual_gross_demand += (np.sum(gross_demand_ts) / 1000 * time_res_h) * cluster_weight
                    timesteps_autonomous += np.sum(np.array(res["res_load"]) == 0) * cluster_weight

                b_kpis[year]['tech'].update({
                    'peak_demand_kW': building_peak_demand_kw,
                    'peak_injection_kW': building_peak_inj_kw,
                    'grid_demand_kWh': annual_demand_from_grid,
                    'grid_injection_kWh': annual_injection_to_grid,
                    'gross_generation_kWh': annual_gross_generation,
                    'gross_demand_kWh': annual_gross_demand,
                    'gas_consumption_kwh': annual_gas,
                    'biomass_consumption_kwh': annual_biom,
                    'oil_consumption_kwh': annual_oil,
                    'hydrogen_consumption_kwh': annual_hydrogen,
                    'self_sufficiency_rate': (
                                                         annual_gross_demand - annual_demand_from_grid) / annual_gross_demand if annual_gross_demand > 0 else 0,
                    'self_consumption_rate': (
                                                         annual_gross_generation - annual_injection_to_grid) / annual_gross_generation if annual_gross_generation > 0 else 0,
                    'autonomy_timestep_rate': timesteps_autonomous / (8760 / time_res_h) if (
                                                                                                        8760 / time_res_h) > 0 else 0
                })

                b_kpis[year]['eco'].update({
                    'total_energy_cost_eur': (annual_gas * curr_price_gas) + (
                                annual_demand_from_grid * curr_price_el) - (
                                                         annual_injection_to_grid * curr_rev_feed_el) + (
                                                         annual_biom * curr_price_biom) + (
                                                         annual_oil * curr_price_oil) + (
                                                         annual_hydrogen * curr_price_hydrogen),
                    'total_co2_emissions_kg': (annual_gas * curr_co2_gas) + (annual_demand_from_grid * curr_co2_el) + (
                                annual_biom * curr_co2_biom) + (annual_oil * curr_co2_oil) + (
                                                          annual_hydrogen * curr_co2_hydrogen)
                })

    def calculateGasolineCosts(self, data):
        """Compute annual gasoline costs (€) for each simulated year."""
        self.gasoline_costs = {}
        for year in self.inputData["simulated_years"]:
            price_per_liter = data.all_sim_ecoData[year]["price_gasoline_liter"] # €/liter
            self.gasoline_costs[year] = float(self.total_ICE_fuel_liters) * float(price_per_liter)


    def calc_total_consumption_and_emissions(self, data):
        """
        Calculates:
        - total consumption of energy carriers in the district
        - total CO2 emissions of the district for each energy carrier

        Uses year weights to account for the interval that each simulated year represents.


        Retuns
        -------
        None.
        """
        sorted_years = sorted(self.inputData["simulated_years"])
        observation_time = data.ecoData["observation_time"]
        year_weights = {
            year: (sorted_years[idx + 1] - year) if idx < len(sorted_years) - 1 else (observation_time - year) for
            idx, year in enumerate(sorted_years)}

        # Calculate total consumption over all years (weighted by interval length)
        self.total_W_dem_GCP = sum(
            self.W_dem_GCP_year[year] * year_weights[year] for year in sorted_years)  # demand from grid
        self.total_W_inj_GCP = sum(
            self.W_inj_GCP_year[year] * year_weights[year] for year in sorted_years)  # injection to grid
        self.total_W_dem_buildings = sum(self.W_dem_buildings_year[year] * year_weights[year] for year in
                                         sorted_years)  # total residual electricity demand within district by buildings
        self.total_W_inj_buildings = sum(self.W_inj_buildings_year[year] * year_weights[year] for year in
                                         sorted_years)  # total residual electricity injection within district by buildings
        self.total_gas = sum(
            self.gas_year[year] * year_weights[year] for year in sorted_years)  # gas consumption of the district
        self.total_biomass = sum(
            self.biomass_year[year] * year_weights[year] for year in sorted_years)  # biomass consumption
        self.total_waste = sum(self.waste_year[year] * year_weights[year] for year in sorted_years)  # waste consumption
        self.total_hydrogen = sum(
            self.hydrogen_year[year] * year_weights[year] for year in sorted_years)  # hydrogen consumption
        self.total_oil = sum(self.oil_year[year] * year_weights[year] for year in sorted_years)  # oil consumption
        self.total_districtHeat = sum(
            self.districtHeat_year[year] * year_weights[year] for year in sorted_years)  # district heat consumption

        # Calculate total CO2 emissions over all years (weighted by interval length)
        self.total_co2_all = sum(
            self.co2emissions[year]["total_co2"] * year_weights[year] for year in sorted_years)  # total CO2 emissions
        self.total_co2_dem_grid = sum(self.co2emissions[year]["co2_dem_grid"] * year_weights[year] for year in
                                      sorted_years)  # CO2 emissions from electricity from grid
        self.total_co2_gas = sum(self.co2emissions[year]["co2_gas"] * year_weights[year] for year in
                                 sorted_years)  # CO2 emissions from gas consumption
        self.total_co2_biom = sum(self.co2emissions[year]["co2_biom"] * year_weights[year] for year in
                                  sorted_years)  # CO2 emissions from biomass consumption
        self.total_co2_waste = sum(self.co2emissions[year]["co2_waste"] * year_weights[year] for year in
                                   sorted_years)  # CO2 emissions from waste consumption
        self.total_co2_hydrogen = sum(self.co2emissions[year]["co2_hydrogen"] * year_weights[year] for year in
                                      sorted_years)  # CO2 emissions from hydrogen consumption
        self.total_co2_oil = sum(self.co2emissions[year]["co2_oil"] * year_weights[year] for year in
                                 sorted_years)  # CO2 emissions from oil consumption
        self.total_co2_district_heat = sum(self.co2emissions[year]["co2_district_heat"] * year_weights[year] for year in
                                           sorted_years)  # CO2 emissions from district heat consumption

    def calculateAllKPIs(self, data):
        self.prepareData(data)
        self.calculateResidualLoad(data)
        self.calculatePeakLoad()
        self.calculatePeakToValley()
        self.calculateEnergyExchangeGCP(data)
        self.calculateEnergyExchangeWithinDistrict(data)
        self.calculateCoverFactors(data)
        self.calculateOperationCosts(data)
        self.calculateCO2emissions(data)
        self.calculateAutonomy()
        self.calc_annual_cost_total(data)
        self.calc_total_areas_and_demands(data)
        self.calculateGasolineCosts(data)
        self.calc_total_consumption_and_emissions(data)
        self.calculate_per_building_kpis(data)

    def KPIs_to_csv(self, scenario_name, output_dir):
        """
        Exports relational, flattened CSVs to the given output directory.
        """
        if output_dir is None:
            output_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        else:
            os.makedirs(output_dir, exist_ok=True)

        total_district_area = self.totalarea_residential + self.totalarea_non_residential
        building_data = []
        district_data = []

        # collect all dynamically used technology names across all buildings and years to create consistent columns in the output table
        all_techs = set()
        for b_id, b_kpis in self.kpis_per_building.items():
            if "active_technologies" in b_kpis:
                all_techs.update(b_kpis["active_technologies"].keys())
            if "costs" in b_kpis:
                for k in b_kpis["costs"].keys():
                    if k.startswith("annual_cost_") and k.endswith("_eur"):
                        all_techs.add(k.replace("annual_cost_", "").replace("_eur", ""))
        all_techs = sorted(list(all_techs))

        # loop over all simulated years
        for year in self.inputData["simulated_years"]:

            sum_bldg_co2_kg = 0
            sum_bldg_gross_gen = 0
            sum_bldg_gross_dem = 0

            # -----------------------------------------------------------------
            # Buildings
            # -----------------------------------------------------------------
            for b_id, b_kpis in self.kpis_per_building.items():

                tech_data = b_kpis.get(year, {}).get("tech", {})
                eco_data = b_kpis.get(year, {}).get("eco", {})
                costs_data = b_kpis.get("costs", {})
                b_area = b_kpis.get("area_m2", 0)

                # Basis-Daten
                row = {
                    "Building_ID": b_id,
                    "Year": year,
                    "Building_Type": b_kpis.get("building_type", "N/A"),
                    "Area_m2": b_area,
                    "Heating_System": b_kpis.get("heating_system", "N/A"),
                    "Total_Heat_Load_kW": b_kpis.get("total_heat_load_kW", 0),
                    "Annual_Heating_Demand_kWh": b_kpis.get("annual_heating_demand_kWh", 0),
                    "Annual_El_Demand_kWh": b_kpis.get("annual_electricity_demand_kWh", 0),
                    "Peak_Demand_kW": tech_data.get("peak_demand_kW", 0),
                    "Peak_Injection_kW": tech_data.get("peak_injection_kW", 0)
                }

                # central costs allocation based on area (if available)
                central_costs = self.annual_fixed_costs_central.get(year,
                                                                    self.annual_fixed_costs_central) if isinstance(
                    self.annual_fixed_costs_central, dict) else self.annual_fixed_costs_central
                row["Allocated_Central_Costs_by_area_EUR"] = (
                                                                 b_area / total_district_area) * central_costs if total_district_area > 0 and central_costs else 0

                # put capacities and costs in columns next to each other (better readability)
                for tech in all_techs:
                    cap_val = list(b_kpis.get("active_technologies", {}).get(tech, {f"cap": 0}).values())[
                        0] if tech in b_kpis.get("active_technologies", {}) else 0
                    cost_val = costs_data.get(f"annual_cost_{tech}_eur", 0)

                    row[f"Cap_{tech}"] = cap_val
                    row[f"Cost_{tech}_EUR"] = cost_val

                row["Annual_Fixed_Costs_Decentral_EUR"] = costs_data.get("annual_fixed_costs_eur", 0)

                # Grid exchange & gross flows
                row["Grid_Demand_kWh"] = tech_data.get("grid_demand_kWh", 0)
                row["Grid_Injection_kWh"] = tech_data.get("grid_injection_kWh", 0)
                row["Gross_Demand_kWh"] = tech_data.get("gross_demand_kWh", 0)
                row["Gross_Generation_kWh"] = tech_data.get("gross_generation_kWh", 0)

                # Consumption of energy carriers
                row["Gas_Consumption_kWh"] = tech_data.get("gas_consumption_kwh", 0)
                row["Biomass_Consumption_kWh"] = tech_data.get("biomass_consumption_kwh", 0)
                row["Oil_Consumption_kWh"] = tech_data.get("oil_consumption_kwh", 0)
                row["Hydrogen_Consumption_kWh"] = tech_data.get("hydrogen_consumption_kwh", 0)

                # KPIs (in percent)
                row["supply_cover_factor_pct"] = tech_data.get("self_sufficiency_rate", 0) * 100
                row["self_consumption_rate_pct"] = tech_data.get("self_consumption_rate", 0) * 100
                row["autonomy_timestep_rate_pct"] = tech_data.get("autonomy_timestep_rate", 0) * 100

                # total costs & emissions
                row["Total_Operational_Costs_EUR"] = eco_data.get("total_energy_cost_eur", 0)
                row["Total_CO2_Emissions_kg"] = eco_data.get("total_co2_emissions_kg", 0)

                building_data.append(row)

                # Add for district comparison
                sum_bldg_co2_kg += eco_data.get("total_co2_emissions_kg", 0)
                sum_bldg_gross_gen += tech_data.get("gross_generation_kWh", 0)
                sum_bldg_gross_dem += tech_data.get("gross_demand_kWh", 0)

            # -----------------------------------------------------------------
            # District
            # -----------------------------------------------------------------
            co2_dict = self.co2emissions.get(year, {})
            # Information: the district calculations are in t/a, so we divide by 1000 to get kg/a like the buildings

            district_row = {
                "Year": year,
                "Total_Area_Res_m2": self.totalarea_residential,
                "Total_Area_NonRes_m2": self.totalarea_non_residential,

                "Total_Heating_Demand_kWh": self.total_heating_demand / 1000 if self.total_heating_demand else 0,
                "Total_El_Demand_kWh": self.total_electricity_demand / 1000 if self.total_electricity_demand else 0,
                "Peak_Demand_kW": self.peakDemand.get(year, 0) if isinstance(self.peakDemand,
                                                                             dict) else self.peakDemand,
                "Peak_Injection_kW": self.peakInjection.get(year, 0) if isinstance(self.peakInjection,
                                                                                   dict) else self.peakInjection,

                "Operation_Costs_EUR": self.operationCosts.get(year, 0) if isinstance(self.operationCosts,
                                                                                      dict) else self.operationCosts,
                "Fixed_Costs_Decentral_EUR": self.annual_fixed_costs_decentral,
                "Fixed_Costs_Central_EUR": self.annual_fixed_costs_central,

                # CO2 Metriken
                "Total_CO2_Emissions_t": co2_dict.get("total_co2", 0),
                "CO2_Difference_to_Buildings_Sum_t": co2_dict.get("total_co2", 0) - (sum_bldg_co2_kg / 1000),
                # Saved CO2 Emissions from Grid Electricity
                "CO2_Grid_El_t": co2_dict.get("co2_dem_grid", 0),
                "CO2_Gas_t": co2_dict.get("co2_gas", 0),
                "CO2_Biomass_t": co2_dict.get("co2_biom", 0),
                "CO2_Waste_t": co2_dict.get("co2_waste", 0),
                "CO2_Hydrogen_t": co2_dict.get("co2_hydrogen", 0),
                "CO2_Oil_t": co2_dict.get("co2_oil", 0),
                "CO2_District_Heat_t": co2_dict.get("co2_district_heat", 0),

                # KPIs (in percent)
                "supply_cover_factor_pct": self.scf_year.get(year, 0) * 100 if isinstance(self.scf_year, dict) else (
                    self.scf_year * 100 if self.scf_year else 0),
                "demand_cover_factor_pct": self.dcf_year.get(year, 0) * 100 if isinstance(self.dcf_year, dict) else (
                    self.dcf_year * 100 if self.dcf_year else 0),
                "energy_autonomy_factor_pct": self.energy_autonomy_year.get(year, 0) * 100 if isinstance(self.energy_autonomy_year,
                                                                                      dict) else (
                    self.energy_autonomy_year * 100 if self.energy_autonomy_year else 0),

                # gid exchange & Gross Flows
                "Grid_Demand_kWh": self.W_dem_GCP_year.get(year, 0),
                "Grid_Injection_kWh": self.W_inj_GCP_year.get(year, 0),
                "Gross_Generation_kWh": sum_bldg_gross_gen,
                "Gross_Demand_kWh": sum_bldg_gross_dem
            }
            district_data.append(district_row)

        def round_sig(x):
            """
            rounds dynamic based on the magnitude of the number
            """
            if pd.isna(x) or x == 0: return x
            abs_x = abs(x)
            if abs_x >= 1: return int(round(x))
            else: return round(x, 2)

        df_buildings = pd.DataFrame(building_data)
        df_district = pd.DataFrame(district_data)

        for x in [df_buildings, df_district]:
            float_cols = x.select_dtypes(include=['float']).columns
            x[float_cols] = x[float_cols].map(round_sig)

        df_buildings.to_csv(os.path.join(output_dir, f"kpis_buildings_{scenario_name}.csv"), index=False)
        df_district.to_csv(os.path.join(output_dir, f"kpis_district_{scenario_name}.csv"), index=False)

    def create_certificate(self, data, result_path):
        """
        Generate a certificate as PDF file with a list of KPIs and a list with building information.

        Parameters:
        - filename: The name of the PDF file to create.
        - title: The title of the document.
        - kpis: A list of strings, where each string is a KPI to be written in the document.
        """

        # preprocessing buildinglist
        template_dict = {"Anzahl": 0,
               "Gesamtfläche": 0,
               "vor 1968": 0,
               "1968-1978": 0,
               "1979-1983": 0,
               "1984-1994": 0,
               "1995-2001": 0,
               "2002-2009": 0,
               "2010-2015": 0,
               "ab 2016": 0,
               }
        SFH = dict(template_dict)
        TH = dict(template_dict)
        MFH = dict(template_dict)
        AB = dict(template_dict)
        gebaeudeliste = []

        for building in data.district:
            if building["buildingFeatures"]["building"] == 'SFH':
                SFH["Anzahl"] += 1
                SFH["Gesamtfläche"] += building["buildingFeatures"]["area"]
                if building["buildingFeatures"]["year"] < 1968:
                    SFH["vor 1968"] += building["buildingFeatures"]["area"]
                elif building["buildingFeatures"]["year"] >= 1968 and building["buildingFeatures"]["year"] <= 1978 :
                    SFH["1968-1978"] += building["buildingFeatures"]["area"]
                elif building["buildingFeatures"]["year"] >= 1979 and building["buildingFeatures"]["year"] <= 1983 :
                    SFH["1979-1983"] += building["buildingFeatures"]["area"]
                elif building["buildingFeatures"]["year"] >= 1984 and building["buildingFeatures"]["year"] <= 1994 :
                    SFH["1984-1994"] += building["buildingFeatures"]["area"]
                elif building["buildingFeatures"]["year"] >= 1995 and building["buildingFeatures"]["year"] <= 2001 :
                    SFH["1995-2001"] += building["buildingFeatures"]["area"]
                elif building["buildingFeatures"]["year"] >= 2002 and building["buildingFeatures"]["year"] <= 2009:
                    SFH["2002-2009"] += building["buildingFeatures"]["area"]
                elif building["buildingFeatures"]["year"] >= 2010 and building["buildingFeatures"]["year"] <= 2015:
                    SFH["2010-2015"] += building["buildingFeatures"]["area"]
                elif building["buildingFeatures"]["year"] >= 2016:
                    SFH["ab 2016"] += building["buildingFeatures"]["area"]
            elif building["buildingFeatures"]["building"] == 'TH':
                TH["Anzahl"] += 1
                TH["Gesamtfläche"] += building["buildingFeatures"]["area"]
                if building["buildingFeatures"]["year"] < 1968:
                    TH["vor 1968"] += building["buildingFeatures"]["area"]
                elif building["buildingFeatures"]["year"] >= 1968 and building["buildingFeatures"]["year"] <= 1978 :
                    TH["1968-1978"] += building["buildingFeatures"]["area"]
                elif building["buildingFeatures"]["year"] >= 1979 and building["buildingFeatures"]["year"] <= 1983 :
                    TH["1979-1983"] += building["buildingFeatures"]["area"]
                elif building["buildingFeatures"]["year"] >= 1984 and building["buildingFeatures"]["year"] <= 1994 :
                    TH["1984-1994"] += building["buildingFeatures"]["area"]
                elif building["buildingFeatures"]["year"] >= 1995 and building["buildingFeatures"]["year"] <= 2001 :
                    TH["1995-2001"] += building["buildingFeatures"]["area"]
                elif building["buildingFeatures"]["year"] >= 2002 and building["buildingFeatures"]["year"] <= 2009:
                    TH["2002-2009"] += building["buildingFeatures"]["area"]
                elif building["buildingFeatures"]["year"] >= 2010 and building["buildingFeatures"]["year"] <= 2015:
                    TH["2010-2015"] += building["buildingFeatures"]["area"]
                elif building["buildingFeatures"]["year"] >= 2016:
                    TH["ab 2016"] += building["buildingFeatures"]["area"]
            elif building["buildingFeatures"]["building"] == 'MFH':
                MFH["Anzahl"] += 1
                MFH["Gesamtfläche"] += building["buildingFeatures"]["area"]
                if building["buildingFeatures"]["year"] < 1968:
                    MFH["vor 1968"] += building["buildingFeatures"]["area"]
                elif building["buildingFeatures"]["year"] >= 1968 and building["buildingFeatures"]["year"] <= 1978 :
                    MFH["1968-1978"] += building["buildingFeatures"]["area"]
                elif building["buildingFeatures"]["year"] >= 1979 and building["buildingFeatures"]["year"] <= 1983 :
                    MFH["1979-1983"] += building["buildingFeatures"]["area"]
                elif building["buildingFeatures"]["year"] >= 1984 and building["buildingFeatures"]["year"] <= 1994 :
                    MFH["1984-1994"] += building["buildingFeatures"]["area"]
                elif building["buildingFeatures"]["year"] >= 1995 and building["buildingFeatures"]["year"] <= 2001 :
                    MFH["1995-2001"] += building["buildingFeatures"]["area"]
                elif building["buildingFeatures"]["year"] >= 2002 and building["buildingFeatures"]["year"] <= 2009:
                    MFH["2002-2009"] += building["buildingFeatures"]["area"]
                elif building["buildingFeatures"]["year"] >= 2010 and building["buildingFeatures"]["year"] <= 2015:
                    MFH["2010-2015"] += building["buildingFeatures"]["area"]
                elif building["buildingFeatures"]["year"] >= 2016:
                    MFH["ab 2016"] += building["buildingFeatures"]["area"]
            elif building["buildingFeatures"]["building"] == 'AB':
                AB["Anzahl"] += 1
                AB["Gesamtfläche"] += building["buildingFeatures"]["area"]
                if building["buildingFeatures"]["year"] < 1968:
                    AB["vor 1968"] += building["buildingFeatures"]["area"]
                elif building["buildingFeatures"]["year"] >= 1968 and building["buildingFeatures"]["year"] <= 1978 :
                    AB["1968-1978"] += building["buildingFeatures"]["area"]
                elif building["buildingFeatures"]["year"] >= 1979 and building["buildingFeatures"]["year"] <= 1983 :
                    AB["1979-1983"] += building["buildingFeatures"]["area"]
                elif building["buildingFeatures"]["year"] >= 1984 and building["buildingFeatures"]["year"] <= 1994 :
                    AB["1984-1994"] += building["buildingFeatures"]["area"]
                elif building["buildingFeatures"]["year"] >= 1995 and building["buildingFeatures"]["year"] <= 2001 :
                    AB["1995-2001"] += building["buildingFeatures"]["area"]
                elif building["buildingFeatures"]["year"] >= 2002 and building["buildingFeatures"]["year"] <= 2009:
                    AB["2002-2009"] += building["buildingFeatures"]["area"]
                elif building["buildingFeatures"]["year"] >= 2010 and building["buildingFeatures"]["year"] <= 2015:
                    AB["2010-2015"] += building["buildingFeatures"]["area"]
                elif building["buildingFeatures"]["year"] >= 2016:
                    AB["ab 2016"] += building["buildingFeatures"]["area"]

            # enforce fTES=0 when heater is heat_grid
            f_TES = 0 if building["buildingFeatures"]["heater"] == "heat_grid" \
                else building["buildingFeatures"]["f_TES"]

            gebaeudeliste.append([building["buildingFeatures"]["building"],
                                  building["buildingFeatures"]["year"],
                                  building["buildingFeatures"]["retrofit"],
                                  building["buildingFeatures"]["construction_type"],
                                  building["buildingFeatures"]["night_setback"],
                                  building["buildingFeatures"]["area"],
                                  building["buildingFeatures"]["heater"],
                                  building["buildingFeatures"]["EV"],
                                  f_TES,
                                  building["buildingFeatures"]["f_BAT"],
                                  building["buildingFeatures"]["f_PV1"],
                                  building["buildingFeatures"]["f_PV2"],
                                  building["buildingFeatures"]["f_STC"],
                                  building["buildingFeatures"]["gamma_PV"],
                                  building["buildingFeatures"]["ev_charging"]])

        # create dicts to categorize KPIs and building information
        # kennwerte: a dictionary with the following keys (in order, formatted as strings), and all values formatted as
        #             strings with the corresponding units (unless otherwise specified):
        #                 Primärenergiebedarf: primary energy demand of the district
        #                 Endenergiebedarf: end energy demand of the district
        #                 Norm-Heizlast insgesamt: the overall heat demand of the district
        #                 Solltemperatur: set-point temperature of the buildings in the district
        #                 Bedarfe: a TUPLE containing three values (float/int) for demands of electricity, heat, and water heating (in that order)
        #                 Max. Leistungen: a TUPLE containing three values (float/int) for the maximum power of each energy type, in the order above
        #
        #             opt_ergebnisse: a dictionary with the following keys (in order, formatted as strings), and all values formatted
        #             as strings with the corresponding units:
        #                 CO2-äqui. Emissionen: CO2-equivalent emissions of the district
        #                 Energiekosten: energy cost for the district
        #                 Spitzenlast (el.) gesamt: peak load for the district
        #                 Max. Einspeiseleistung gesamt: maximum feed-in power of the district
        #                 Supply-Cover-Faktor: supply cover factor
        #                 Demand-Cover-Faktor: demand cover factor
        #
        #             struktur: a dictionary with the following keys (in order, formatted as strings) and and all values formatted as
        #             strings with the corresponding units (unless otherwise specified):
        #                 EFH: a DICTIONARY containing the following keys and values pertaining to single-family homes in the district
        #                 (keys formatted as strings, values formatted as strings including the relevant units):
        #                     Anzahl: the number of buildings of this type in the district
        #                     Gesamtfläche: the total floor space of these buildings (without unit!)
        #                     vor 1968: the total floor space of the buildings of this type built before 1968, in m^2 (without unit in string!)
        #                     1968-1979: the total floor space of the buildings of this type built between 1968 and 1979, in m^2 (without unit in string!)
        #                     1979-1983: the total floor space of the buildings of this type built between 1979 and 1983, in m^2 (without unit in string!)
        #                     1984-1994: the total floor space of the buildings of this type built between 1984 and 1994, in m^2 (without unit in string!)
        #                     1995-2001: the total floor space of the buildings of this type built between 1995 and 2001, in m^2 (without unit in string!)
        #                     2002-2009: the total floor space of the buildings of this type built between 2002 and 2009, in m^2 (without unit in string!)
        #                     2010-2015: the total floor space of the buildings of this type built between 2010 and 2015, in m^2 (without unit in string!)
        #                     ab 2016: the total floor space of the buildings of this type built since 2016, in m^2 (without unit in string!)
        #                 MFH: a DICTIONARY formatted as specified above, with the values pertaining to multiple-family homes.
        #                 Reihenhaus: a DICTIONARY formatted as specified above, with the values pertaining to townhouses.
        #                 Block: a DICTIONARY formatted as specified above, with the values pertaining to block buildings.
        #                 Wohnungen gesamt: number of households in the district
        #                 Bewohner gesamt: number of residents in the district
        #                 Nettowohnfläche gesamt: net living space in the district
        #                 Standort (PLZ): the zip code of the district
        #                 Testreferenzjahr: the reference year and reference weather conditions, formatted as "YYYY / warm"
        #                 Quartiersname: the name of the district
        #
        #             gebaeudeliste: a two-dimensional list, with each index corresponding to a building ID and the list in each index containing the following values:
        #                 building: SFH, MFH, Townhouse, or Block
        #                 year: year of construction
        #                 retrofit: 1 (yes) or 0 (no)
        #                 area: floor space
        #                 heater: type of heating
        #                 PV:
        #                 STC:
        #                 EV:
        #                 BAT:
        #                 f_TES:
        #                 f_BAT:
        #                 f_PV1:
        #                 f_PV2:
        #                 f_STC:
        #                 gamma_PV:
        #                 ev_charging:
        kennwerte={
                # TODO: We don't have any primary factors for gas and electricity mix. Should be added?
                # "Primärenergiebedarf": "120 kWh/m\u00B2a",
                # TODO: Discuss total final energy calculation and if a specific value would be better
                "Nutzenergiebedarf": str(round((self.total_electricity_demand
                                               + self.total_heating_demand
                                               + self.total_cooling_demand
                                               + self.total_dhw_demand
                                               + self.total_EV_demand ) / 1000000, 1)) + " MWh/a",
                "Norm-Heizlast": str(round(self.totalheatload / 1000)) + " kW",

                "Bedarfe": (round(self.total_electricity_demand / 1000000, 2),
                            round(self.total_heating_demand / 1000000, 2),
                            round(self.total_dhw_demand / 1000000, 2),
                            round(self.total_cooling_demand / 1000000, 2),
                            round(self.total_EV_demand / 1000000, 2)),
        "Max. Leistungen": (round(self.total_electricity_peak / 1000),
                                    round(self.total_heat_peak / 1000),
                                    round(self.total_dhw_peak / 1000),
                                    round(self.total_cooling_peak / 1000))

        }
        opt_ergebnisse={
                "CO2-äqui. Emissionen": str(round(self.co2emissions[0]['total_co2'])) + " t/a",
                "Energiekosten": str(round(self.operationCosts[0])) + " \u20AC/a",
                "Spritkosten": str(round(self.gasoline_costs[0] or 0)) + " \u20AC/a",
                "Dezentrale Fixkosten": str(round(self.annual_fixed_costs_decentral)) + " \u20AC/a",
                "Zentrale Fixkosten": str(round(self.annual_fixed_costs_central)) + " \u20AC/a",
                "Spitzenlast (el.)": str(round(self.peakDemand[0], 2)) + " kW",
                "Max. Einspeiseleistung": str(round(self.peakInjection[0], 2)) + " kW",
                "Supply-Cover-Faktor": str(round(self.scf_year[0] * 100, 0)) + " %",
                "Demand-Cover-Faktor": str(round(self.dcf_year[0] * 100, 0)) + " %",

        }
        struktur={
                "EFH": SFH,
                "MFH": MFH,
                "Reihenhaus": TH,
                "Block": AB,
                "Wohneinheiten gesamt": self.totalnumberflats,
                "Bewohner gesamt": self.totalnumberocc,
                "Nettowohnfläche gesamt": str(self.totalarea_residential) + " m\u00B2",
                "Nettofläche GHD gesamt": str(self.totalarea_non_residential) + " m\u00B2",
                "Standort (PLZ)": str(data.site["zip"]),
                "Testreferenzjahr": str(data.site["TRYYear"])[3:] + " / " + str(data.site["TRYType"]),
                "Quartiersname": str(data.scenario_name)
            }

        if result_path is None:
            src_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            filename = os.path.join(src_path, "results", f"Quartiersenergieausweis_{data.scenario_name}.pdf")
        else:
            filename = os.path.join(result_path, f"Quartiersenergieausweis_{data.scenario_name}.pdf")

        # initialize certificate
        certificate = canvas.Canvas(filename, pagesize=reportlab.lib.pagesizes.A4)
        width, height = reportlab.lib.pagesizes.A4

        # draw line for header and add title
        certificate.setStrokeColorRGB(54 / 256, 132 / 256, 39 / 256)
        certificate.setLineWidth(4)
        certificate.line(72, height - 60, width - 72, height - 60)
        certificate.setFont("Helvetica-Bold", 20)
        certificate.drawString(72, height - 50, "Quartiersenergieausweis")

        # draw lines for first section and add section title
        top1 = 90  # top of the section
        bottom1 = 350  # bottom of the section

        certificate.setStrokeColorRGB(54 / 256, 132 / 256, 39 / 256)
        certificate.setLineWidth(2)
        certificate.setLineCap(2)
        certificate.line(72, height - top1, 78, height - top1)
        certificate.line(277, height - top1, width - 72, height - top1)
        certificate.line(72, height - top1, 72, height - bottom1)
        certificate.line(72, height - bottom1, width - 72, height - bottom1)
        certificate.line(width - 72, height - bottom1, width - 72, height - top1)
        certificate.setFont("Helvetica-Bold", 16)
        certificate.drawString(85, height - top1 - 6, "Energetische Kennwerte")

        # do the same for the second section
        top2 = 380
        bottom2 = 720

        certificate.line(72, height - top2, 78, height - top2)
        certificate.line(223, height - top2, width - 72, height - top2)
        certificate.line(72, height - top2, 72, height - bottom2)
        certificate.line(72, height - bottom2, width - 72, height - bottom2)
        certificate.line(width - 72, height - bottom2, width - 72, height - top2)
        certificate.drawString(85, height - top2 - 6, "Quartiersstruktur")

        # do the same for the final section
        top3 = 730
        bottom3 = 770

        certificate.line(72, height - top3, width - 72, height - top3)
        certificate.line(72, height - bottom3, width - 72, height - bottom3)
        certificate.line(72, height - top3, 72, height - bottom3)
        certificate.line(width - 72, height - top3, width - 72, height - bottom3)
        certificate.setFont("Helvetica-Bold", 12)
        certificate.drawString(85, height - ((top3 + bottom3) / 2) - 4, "Quartiersname: ")
        certificate.setFont("Helvetica", 10)
        certificate.drawString(177, height - ((top3 + bottom3) / 2) - 4, struktur["Quartiersname"])
        certificate.drawString(380, height - ((top3 + bottom3) / 2) - 4,
                               "Erstellt am: " + datetime.now().strftime('%d.%m.%Y %H:%M'))

        # filling in the first section
        # in the create_certificate function, the argument would be a dictionary of parameters and their values. this dictionary would be titled quartier_daten

        certificate.setFont("Helvetica", 12)
        content = tuple(kennwerte.keys())
        values = tuple(kennwerte.values())
        content = content[0:2]
        values = values[0:2]

        i = 0
        for item in content:
            certificate.drawString(85, height - top1 - 32 - (18 * i), item + ":")
            i = i + 1

        j = 0
        for value in values:
            certificate.drawString(200, height - top1 - 32 - (18 * j), str(value))
            j = j + 1

        bottom_kennwerte = top1 + 25 + 18 * j

        # create a subsection for optimization results, fill in the values

        certificate.setLineWidth(1)
        certificate.setLineCap(2)
        certificate.line(72, height - bottom_kennwerte, 325, height - bottom_kennwerte)
        certificate.line(325, height - bottom_kennwerte, 325, height - bottom1)

        certificate.setFont("Helvetica-Bold", 14)
        certificate.drawString(85, height - bottom_kennwerte - 25, "Optimierter Anlagenbetrieb")

        certificate.setFont("Helvetica", 12)
        opt_keys = tuple(opt_ergebnisse.keys())
        opt_values = tuple(opt_ergebnisse.values())

        i = 0
        for item in opt_keys:
            certificate.drawString(85, height - bottom_kennwerte - 50 - (18 * i), item + ":")
            i = i + 1

        j = 0
        for value in opt_values:
            certificate.drawString(230, height - bottom_kennwerte - 50 - (18 * j), str(value))
            j = j + 1

        # create graphics for the energy demands and maximum powers by energy type
        d = Drawing(300, 300)

        pc = Pie()
        pc.width = 90
        pc.height = 90
        pc.data = kennwerte["Bedarfe"]
        pc.labels = None#['Strom: ' + str(pc.data[0]), 'Wärme: ' + str(pc.data[1]), 'TWW: ' + str(pc.data[2]),'Kälte: '+str(pc.data[3])]
        #pc.sideLabelsOffset = 0.1
        #pc.sideLabels = 1
        #pc.checkLabelOverlap = 1

        pc.slices.strokeWidth = 1
        pc.slices.labelRadius = 1.5
        pc.slices[3].labelRadius = 1.2
        pc.slices.fontName = "Helvetica"
        pc.slices.strokeColor = colors.white

        pc.slices[0].fillColor = colors.Color(0 / 256, 85 / 256, 31 / 256)
        pc.slices[1].fillColor = colors.Color(134 / 256, 169 / 256, 26 / 256)
        pc.slices[2].fillColor = colors.Color(54 / 256, 132 / 256, 39 / 256)
        pc.slices[3].fillColor = colors.Color(122 / 256, 186 / 256, 214 / 256)
        pc.slices[4].fillColor = colors.Color(102 / 256, 51 / 256, 153 / 256)

        d.add(pc)

        legend = Legend()
        legend.alignment = 'right'
        legend.fontName = "Helvetica"
        legend.fontSize = 10
        legend.dx = 7
        legend.dy = 7
        legend.yGap = 0
        legend.deltax = 90
        legend.deltay = 10
        legend.strokeWidth = 0
        legend.strokeColor = colors.white
        legend.columnMaximum = 3
        legend.boxAnchor = 'nw'
        legend.y = -5
        legend.x = -36
        legend.colorNamePairs = [
            (colors.Color(0 / 256, 85 / 256, 31 / 256), u'Strom: ' + str(pc.data[0])),
            (colors.Color(134 / 256, 169 / 256, 26 / 256), u'Wärme: ' + str(pc.data[1])),
            (colors.Color(54 / 256, 132 / 256, 39 / 256), u'TWW: ' + str(pc.data[2])),
            (colors.Color(122 / 256, 186 / 256, 214 / 256), u'Kälte: ' + str(pc.data[3])),
            (colors.Color(102 / 256, 51 / 256, 153 / 256), u'EV: ' + str(pc.data[4])),]
        d.add(legend)

        d.drawOn(certificate,(width/2)+80,height-top1-120)

        certificate.setFont("Helvetica-Bold", 14)
        certificate.drawString(340, height - top1 - 20, "Energiebedarfe in MWh")

        max_leistungen = kennwerte["Max. Leistungen"]
        leist_labels = ("Strom: ", "Wärme: ", "TWW: ","Kälte: ")

        ML_top = 263

        certificate.drawString(340, height - ML_top, "Maximale Leistungen")

        certificate.setStrokeColorRGB(54 / 256, 132 / 256, 39 / 256)
        certificate.setLineWidth(5)
        certificate.setLineCap(2)
        certificate.setFont("Helvetica", 12)

        scaling_line = 75 / max(max_leistungen)

        for i in range(len(max_leistungen)):
            certificate.drawString(340, height - ML_top - 18 - (18 * i), leist_labels[i])
            certificate.line(387, height - ML_top - 16 - (18 * i), 390 + (scaling_line * max_leistungen[i]),
                             height - ML_top - 16 - (18 * i))
            certificate.drawString(395 + (scaling_line * max_leistungen[i]), height - ML_top - 18 - (18 * i),
                                   str(max_leistungen[i]) + " kW")

        # create table in section 2
        n_rows = 11
        n_columns = 5
        certificate.setStrokeColorRGB(0, 0, 0)
        certificate.setLineWidth(1)
        certificate.setLineCap(2)
        table_top = height - top2 - 20
        table_bottom = table_top - (18 * n_rows)
        table_width = width - 180

        first_column_width = (table_width / 5) * 1.3
        remaining_column_width = (table_width - first_column_width) / 4

        # Draw horizontal lines
        for ii in range(n_rows + 1):
            certificate.line(90, table_top - (18 * ii), width - 90, table_top - (18 * ii))

        # Draw vertical lines with adjusted column widths
        x_position = 90  # Starting x position for first column

        # First column
        certificate.line(x_position, table_top, x_position, table_bottom)
        x_position += first_column_width  # Move to next column

        # Remaining columns
        for jj in range(1, n_columns + 1):
            certificate.line(x_position, table_top, x_position, table_bottom)
            x_position += remaining_column_width  # Move to the next column

        # Column titles
        certificate.setFont("Helvetica-Bold", 11.5)
        column_titles = ("Wohngebäudetyp", "EFH", "MFH", "Reihenhaus", "Block")

        # Draw column titles
        x_position = 90  # Reset x position

        certificate.drawString(
            x_position + (first_column_width - len(column_titles[0]) * 6.8) / 2, table_top - 14, column_titles[0]
        )
        x_position += first_column_width  # Move to next column

        for i in range(1, 5):
            certificate.drawString(
                x_position + (remaining_column_width - len(column_titles[i]) * 6.8) / 2, table_top - 14,
                column_titles[i]
            )
            x_position += remaining_column_width  # Move to next column

        # row titles
        row_titles = tuple(struktur["EFH"].keys())

        for i in range(len(row_titles)):
            certificate.drawString(94 + (((table_width / 5) - len(row_titles[i]) * 6.8) / 2),
                                   table_top - 14 - 18 - (18 * i), row_titles[i])

        # fill in table values
        certificate.setFont("Helvetica", 11.5)
        EFH_values = tuple(struktur["EFH"].values())
        MFH_values = tuple(struktur["MFH"].values())
        RH_values = tuple(struktur["Reihenhaus"].values())
        B_values = tuple(struktur["Block"].values())

        certificate.drawString((table_width * 2 / 5) + ((table_width / 5) / 2) + 17 - (len(str(EFH_values[0])) * 6.5),
                               table_top - 14 - 18, str(EFH_values[0]))
        certificate.drawString((table_width * 3 / 5) + ((table_width / 5) / 2) + 17 - (len(str(MFH_values[0])) * 6.5),
                               table_top - 14 - 18, str(MFH_values[0]))
        certificate.drawString((table_width * 4 / 5) + ((table_width / 5) / 2) + 17 - (len(str(RH_values[i])) * 6.5),
                               table_top - 14 - 18, str(RH_values[0]))
        certificate.drawString((table_width) + ((table_width / 5) / 2) + 17 - (len(str(B_values[i])) * 6.5),
                               table_top - 14 - 18, str(B_values[0]))

        for i in range(1, len(EFH_values)):
            certificate.drawString((table_width * 2 / 5) + ((table_width / 5) / 2) + 17 - (len(str(EFH_values[i])) * 6.5),
                                   table_top - 14 - 18 - (18 * i), str(EFH_values[i]))
            certificate.drawString((table_width * 2 / 5) + ((table_width / 5) / 2) + 22, table_top - 14 - 18 - (18 * i),
                                   "m\u00B2")
        for i in range(1, len(MFH_values)):
            certificate.drawString((table_width * 3 / 5) + ((table_width / 5) / 2) + 17 - (len(str(MFH_values[i])) * 6.5),
                                   table_top - 14 - 18 - (18 * i), str(MFH_values[i]))
            certificate.drawString((table_width * 3 / 5) + ((table_width / 5) / 2) + 22, table_top - 14 - 18 - (18 * i),
                                   "m\u00B2")
        for i in range(1, len(RH_values)):
            certificate.drawString((table_width * 4 / 5) + ((table_width / 5) / 2) + 17 - (len(str(RH_values[i])) * 6.5),
                                   table_top - 14 - 18 - (18 * i), str(RH_values[i]))
            certificate.drawString((table_width * 4 / 5) + ((table_width / 5) / 2) + 22, table_top - 14 - 18 - (18 * i),
                                   "m\u00B2")
        for i in range(1, len(B_values)):
            certificate.drawString((table_width) + ((table_width / 5) / 2) + 17 - (len(str(B_values[i])) * 6.5),
                                   table_top - 14 - 18 - (18 * i), str(B_values[i]))
            certificate.drawString((table_width) + ((table_width / 5) / 2) + 22, table_top - 14 - 18 - (18 * i),
                                   "m\u00B2")

        # fill in the info under the table
        certificate.setFont("Helvetica", 12)
        struktur_keys = tuple(struktur.keys())
        struktur_keys = struktur_keys[4:-1]
        struktur_values = tuple(struktur.values())
        struktur_values = struktur_values[4:-1]

        i = 0
        for item in struktur_keys:
            certificate.drawString(185, table_bottom - 20 - (18 * i), item + ":")
            i = i + 1

        j = 0
        for value in struktur_values:
            certificate.drawString(350, table_bottom - 20 - (18 * j), str(value))
            j = j + 1

        # end first page, continue to next page
        certificate.showPage()

        # swap page orientation to landscape
        certificate.setPageSize((height, width))
        height, width = width, height

        # create table
        if len(gebaeudeliste) <= 26:
            n_rows = len(gebaeudeliste) + 1
        else:
            n_rows = 27

        n_columns = 16
        certificate.setStrokeColorRGB(0, 0, 0)
        certificate.setLineWidth(1)
        certificate.setLineCap(2)
        table_top = height - 54
        table_bottom = table_top - (18 * n_rows)
        table_width = width - 108
        total_pages = (len(gebaeudeliste) // 26) + 1

        if len(gebaeudeliste) % 26 == 0:
            total_pages = total_pages - 1

        if total_pages == 1:

            for ii in range(n_rows + 1):
                certificate.line(54, table_top - (18 * ii), width - 54, table_top - (18 * ii))
            for jj in range(n_columns + 1):
                certificate.line(54 + table_width * (jj / n_columns), table_top, 54 + table_width * (jj / n_columns),
                                 table_bottom)

            # column titles
            certificate.setFont("Helvetica-Bold", 6)
            column_titles = (
            "Gebäude ID", "Gebäudetyp", "Baujahr", "Sanierung", "Sp-Masse", "N-Absenkung", "Wohnfläche", "Heizung", "EV",
            "fTES", "fBAT", "fPV1", "fPV2", "fSTC", "gammaPV ", "EV Charging")
            for i in range(len(column_titles)):
                certificate.drawString(54 + table_width * (i / n_columns) + (
                            ((table_width / len(column_titles)) - len(column_titles[i]) * 3.2) / 2), table_top - 11,
                                       column_titles[i])

            # add table values
            certificate.setFont("Helvetica", 6)
            for i in range(len(gebaeudeliste)):
                certificate.drawString((table_width / n_columns) + (((table_width / n_columns) - (len(str(i))) * 3.2) / 2) + 10,
                                       table_top - 11 - 18 - (18 * i), str(i))
                for j in range(15):
                    certificate.drawString((table_width * (j + 2) / n_columns) + (
                                ((table_width / n_columns) - (len(str(gebaeudeliste[i][j]))) * 3.2) / 2) + 10,
                                           table_top - 11 - 18 - (18 * i), str(gebaeudeliste[i][j]))

                    # add border and title
            certificate.setStrokeColorRGB(54 / 256, 132 / 256, 39 / 256)
            certificate.setLineWidth(2)
            certificate.setLineCap(2)
            certificate.line(36, height - 36, 78, height - 36)
            certificate.line(230, height - 36, width - 36, height - 36)
            certificate.line(36, height - 36, 36, 36)
            certificate.line(36, 36, width - 36, 36)
            certificate.line(width - 36, 36, width - 36, height - 36)
            certificate.setFont("Helvetica-Bold", 16)
            certificate.drawString(85, height - 36 - 6, "Liste der Gebäude")

            # end page, continue to next page
            certificate.showPage()

        else:
            num_data_cols = len(gebaeudeliste[0])
            for page in range(1, total_pages + 1, 1):
                offset = 26 * (page - 1)
                rows_on_page = min(26, len(gebaeudeliste) - offset)

                if page != total_pages or len(gebaeudeliste) % 26 == 0:
                    for ii in range(n_rows + 1):
                        certificate.line(54, table_top - (18 * ii), width - 54, table_top - (18 * ii))
                    for jj in range(n_columns + 1):
                        certificate.line(54 + table_width * (jj / n_columns), table_top,
                                         54 + table_width * (jj / n_columns), table_bottom)

                    # add table values
                    certificate.setFont("Helvetica", 6)
                    for i in range(rows_on_page):
                        row_idx = offset + i
                        certificate.drawString((table_width / 15) + (
                                    ((table_width / 15) - (len(str(i + (26 * (page - 1))))) * 3.2) / 2) + 10,
                                               table_top - 11 - 18 - (18 * i), str(row_idx))
                        for j in range(num_data_cols):
                            val = gebaeudeliste[row_idx][j]
                            certificate.drawString((table_width * (j + 2) / 15) + (((table_width / 15) - (
                                len(str(gebaeudeliste[i + (26 * (page - 1))][j]))) * 3.2) / 2) + 10,
                                                   table_top - 11 - 18 - (18 * i),
                                                   str(val))

                elif page == total_pages:

                    n_rows = len(gebaeudeliste) % 26 + 1
                    table_bottom = table_top - (18 * n_rows)

                    for ii in range(n_rows + 1):
                        certificate.line(54, table_top - (18 * ii), width - 54, table_top - (18 * ii))
                    for jj in range(n_columns + 1):
                        certificate.line(54 + table_width * (jj / n_columns), table_top,
                                         54 + table_width * (jj / n_columns), table_bottom)

                    # add table values
                    certificate.setFont("Helvetica", 6)
                    for i in range(rows_on_page):
                        row_idx = offset + i
                        certificate.drawString((table_width / 15) + (
                                ((table_width / 15) - (len(str(i + (26 * (page - 1))))) * 3.2) / 2) + 10,
                                               table_top - 11 - 18 - (18 * i), str(row_idx))
                        for j in range(num_data_cols):
                            val = gebaeudeliste[row_idx][j]
                            certificate.drawString((table_width * (j + 2) / 15) + (((table_width / 15) - (
                                len(str(gebaeudeliste[i + (26 * (page - 1))][j]))) * 3.2) / 2) + 10,
                                                   table_top - 11 - 18 - (18 * i),
                                                   str(val))
                            # column titles
                certificate.setFont("Helvetica-Bold", 6)
                column_titles = (
                    "Gebäude ID", "Gebäudetyp", "Baujahr", "Sanierung", "Sp-Masse", "N-Absenkung",
                    "Wohnfläche", "Heizung", "EV",
                    "fTES", "fBAT", "fPV1", "fPV2", "fSTC", "gammaPV ", "EV Charging")
                for i in range(len(column_titles)):
                    certificate.drawString(54 + table_width * (i / n_columns) + (
                                ((table_width / len(column_titles)) - len(column_titles[i]) * 3.2) / 2), table_top - 11,
                                           column_titles[i])

                # add border and title
                certificate.setStrokeColorRGB(54 / 256, 132 / 256, 39 / 256)
                certificate.setLineWidth(2)
                certificate.setLineCap(2)
                certificate.line(36, height - 36, 78, height - 36)
                certificate.line(268, height - 36, width - 36, height - 36)
                certificate.line(36, height - 36, 36, 36)
                certificate.line(36, 36, width - 36, 36)
                certificate.line(width - 36, 36, width - 36, height - 36)
                certificate.setFont("Helvetica-Bold", 16)
                certificate.drawString(85, height - 36 - 6,
                                       "Liste der Gebäude (" + str(page) + "/" + str(total_pages) + ")")

                certificate.showPage()

        try:
            data.centralDevices["capacities"]

            certificate.setPageSize(reportlab.lib.pagesizes.A4)

            width, height = reportlab.lib.pagesizes.A4
            top4 = 40
            bottom4 = 350

            certificate.setStrokeColorRGB(54 / 256, 132 / 256, 39 / 256)
            certificate.setLineWidth(2)
            certificate.setLineCap(2)
            certificate.line(72, height - top4, 78, height - top4)
            certificate.line(180, height - top4, width - 72, height - top4)
            certificate.line(72, height - top4, 72, height - bottom4)
            certificate.line(72, height - bottom4, width - 72, height - bottom4)
            certificate.line(width - 72, height - bottom4, width - 72, height - top4)
            certificate.setFont("Helvetica-Bold", 16)
            certificate.drawString(85, height - top4 - 6, "Energy Hub")

            # ——— prepare rows: only feasible devices
            rows = [["Device", "Capacity"]]
            for dev, spec in data.centralDevices["capacities"].items():
                # skip non-dict entries
                if not isinstance(spec, dict):
                    continue
                cap = spec.get("cap", None)
                if cap is None or cap <= 0:
                    continue

                # HP special naming
                if dev in ["HP","GHP","BHP","H2HP","OHP"]:
                    if data.central_device_data["AirHP"]["feasible"]:
                        name = "Air-source Heat Pump"
                    elif data.central_device_data["GroundHP"]["feasible"]:
                        name = "Ground-source Heat Pump"
                    else:
                        name = "Heat Pump"
                    unit = "kW"

                # CC special naming
                elif dev == "CC":
                    if data.central_device_data["AirCC"]["feasible"]:
                        name = "Air-cooled Chiller"
                    else:
                        name = "Cooling Chiller"
                    unit = "kW"

                # for everything else
                else:
                    name_map = {
                        "PV": "Solar Panels",
                        "WT": "Wind Turbine",
                        "WAT": "Water Turbine",
                        "STC": "Solar Thermal Collector",
                        "CHP": "Combined Heat & Power",
                        "BOI": "Boiler",
                        "GHP": "Gas Heat Pump",
                        "EB": "Electric Boiler",
                        "AC": "Absorption Chiller",
                        "BCHP": "Biogas CHP",
                        "BBOI": "Biogas Boiler",
                        "WCHP": "Waste Heat CHP",
                        "WBOI": "Waste Heat Boiler",
                        "ELYZ": "Electrolyzer",
                        "FC": "Fuel Cell",
                        "H2S": "Hydrogen Storage",
                        "SAB": "Sabatier Reactor",
                        "TES": "Heat Storage",
                        "CTES": "Cold Storage",
                        "BAT": "Battery",
                        "GS": "Gas Storage"
                    }
                    name = name_map.get(dev, dev)
                    unit_map = {
                        "TES": "kWh",
                        "CTES": "kWh",
                        "BAT": "kWh",
                        "GS": "kWh"
                    }
                    unit = unit_map.get(dev, "kW")

                rows.append([name, f"{cap:.2f} {unit}"])


            n_rows = len(rows)
            margin = 100
            table_width = width - 2 * margin
            first_col = table_width * 0.4
            second_col = table_width - first_col
            row_h = 18

            table_top = height - top4 - 15
            table_bottom = table_top - n_rows * row_h

            certificate.setStrokeColorRGB(0, 0, 0)
            certificate.setLineWidth(1)

            for i in range(n_rows + 1):
                y = table_top - i * row_h
                certificate.line(margin, y, margin + table_width, y)

            x = margin
            certificate.line(x, table_top, x, table_bottom)
            x += first_col
            certificate.line(x, table_top, x, table_bottom)
            x += second_col
            certificate.line(x, table_top, x, table_bottom)

            certificate.setFont("Helvetica-Bold", 11.5)
            certificate.drawCentredString(margin + first_col / 2, table_top - 3 * row_h / 4, rows[0][0])
            certificate.drawCentredString(margin + first_col + second_col / 2, table_top - 3 * row_h / 4,
                                          rows[0][1])

            certificate.setFont("Helvetica", 11.5)
            for idx, (dev, cap) in enumerate(rows[1:], start=1):
                y = table_top - idx * row_h - 3 * row_h / 4
                certificate.drawCentredString(margin + first_col / 2, y, dev)
                certificate.drawCentredString(margin + first_col + second_col / 2, y, cap)

            certificate.showPage()

        except KeyError:
            pass

        certificate.setPageSize(reportlab.lib.pagesizes.A4)
        width, height = reportlab.lib.pagesizes.A4

        # add border and title
        certificate.setStrokeColorRGB(54 / 256, 132 / 256, 39 / 256)
        certificate.setLineWidth(2)
        certificate.setLineCap(2)
        certificate.line(36, height - 36, 78, height - 36)
        certificate.line(250, height - 36, width - 36, height - 36)
        certificate.line(36, height - 36, 36, 36)
        certificate.line(36, 36, width - 36, 36)
        certificate.line(width - 36, 36, width - 36, height - 36)
        certificate.setFont("Helvetica-Bold", 16)
        certificate.drawString(85, height - 36 - 6, "Allgemeine Hinweise")

        # add information
        terms = ["Bezeichnungen in der Liste der Gebäude", "Energetische Kennwerte", "Optimierter Anlagenbetrieb"]
        details = [
            "<b>Gebäude ID:</b> Gebäudenummer zur Identifizierung<br />"
            "<b>Gebäudetyp:</b> SFH = Einfamilienhaus, MFH = Mehrfamilienhaus, TH = Reihenhaus, AB = Wohnblock, "
            "OB = Bürogebäude, SC = Schule, GS = Lebensmittelgeschäft, RE = Restaurant, "
            "MFH+GR = Mehrfamilienhaus+Lebensmittelgeschäft, AB+GR = Wohnblock+Lebensmittelgeschäft, "
            "MFH+RE = Mehrfamilienhaus+Restaurant, AB+RE = Wohnblock+Restaurant<br />"
            "<b>Baujahr:</b> Baualtersklasse (vor 1969, 1968-1978, 1979-1983, 1984-1994, 1995-2001, 2002-2009, "
            "2010-2015, ab 2016)<br />"
            "<b>Sanierung für Wohngebäude:</b> 0 = Bestand, 1 = Sanierung nach EnEV 2016, 2 = Sanierung nach KfW 55<br />"
            "<b>Sanierung für Nichtwohngebäude:</b> 0 = Nichtsaniert, 1 = Teilsaniert (nur Fenster und Wände), "
            "2 = Vollsaniert (Decke, Fenster, Dach und Wände)<br />"
            "<b>Sp-Masse:</b> Gebäudespeichermasse: 0 = Leichtbau, 1 = Mittelbau, 2 = Massivbau<br />"
            "<b>N-Absenkung:</b> Nachtabsenkung: 0 = keine Nachtabsenkung, 1 = mit Nachtabsenkung<br />"
            "<b>Wohnfläche:</b> Nettoraumfläche in m²<br />"
            "<b>Heizung:</b> ausgewählter Wärmeerzeuger<br />"
            "<b>EV:</b> Zwischen 0 und 1; Anteil der Elektroautos am Gesamtfahrzeugbestand im Gebäude<br />"
            "<b>fTES:</b> Größe des Pufferspeichers in Liter pro kW Heizleistung der Wärmeerzeugungsanlage<br />"
            "<b>fBAT:</b> Größe des Batteriespeichers in abhängigkeit der Leistung der PV-Anlage in Wh/W_PV<br />"
            "<b>fPV1:</b> Anteil der gesamten Dachfläche, der auf Dachseite 1 mit Photovoltaik belegt ist. Dachseite 1 "
            "ist dabei die Seite, für die der Azimutwinkel gammaPV vergegeben wird (Informationen zu Dachflächen "
            "sind den Typgebäuden nach Tabula zu entnehmen)<br />"
            "<b>fPV2:</b> Anteil der gesamten Dachfläche, der auf Dachseite 2 mit Photovoltaik belegt ist. Der Azimutwinkel "
            'von Dachseite 2 wird als 180° zu gammaPV gedreht ("gegenüberliegend") berechnet. <br />'
            "<b>fSTC:</b> Anteil der Dachfläche, die mit Solarthermie ausgestattet ist (Informationen zu Dachflächen "
            "sind den Typgebäuden nach Tabula zu entnehmen)<br />"
            "<b>gammaPV:</b> Azimut = Himmelsausrichtung von Dachseite 1, Ausrichtung nach Süden entspricht 0°<br />"
            "<b>EV Charging:</b> Ladeverhalten des Elektroautos (bi-direktional: Be- und Entladung, Nutzung als "
            "Stromspeicher, on-demand: Beladung nach Bedarf, intelligent: optimierte Beladung)<br />",
            "Die hier angegebenen Werte basieren auf den rechnerischen Bedarfen auf Nutzerebene. "
            "Ein Anlagenbetrieb ist hier nicht berücksichtigt.<br />"
            "<b>Nutzenergiebedarf:</b> Über alle Gebäude aufsummierter Nutzenergiebedarf (Haushaltsstrom, Wärme, "
            "Trinkwarmwasser, Kälte und EV-Strom)<br />"
            "<b>Norm-Heizlast:</b> Über alle Gebäude aufsummierte Norm-Heizlast nach DIN EN ISO 13790<br />"
            "<b>Energiebedarfe (MWh):</b> Über alle Gebäude aufsummierten Jahresenergiebedarfe auf Basis der "
            "generierten Bedarfsprofile (für Wärme, Kälte, Haushaltsstrom, Trinkwarmwasser und Elektroautos)<br />"
            "<b>Maximale Leistungen:</b> Maximale Leistungen in kW im Quartier auf Basis der aufsummierten "
            "Bedarfsprofile aller Gebäude (ohne Betriebsoptimierung)<br /><br /><br />",
            "Die hier angegebenen Werte wurden nach einer Betriebsoptimierung unter Berücksichtigung aller "
            "definierten Anlagen (Erzeuger wie auch Speicher) im Quartier berechnet.<br />"
            "<b>CO2-äqui. Emissionen:</b> Im Quartier emittierte CO2-Äquivalente in t/a durch den optimierten "
            "Betrieb (Gasbedarf und Strombedarf)<br />"
            "<b>Energiekosten:</b> Spezifische Betriebskosten des gesamten Quartiers in €/kWh auf Basis der "
            "Betriebsoptimierung<br />"
            "<b>Fixed Costs:</b> total fixed, annualized cost of all installed energy assets, including capital "
            "expenditures (CAPEX) and fixed operation & maintenance (O&M) costs<br />"
            "<b>Spitzenlast (el.):</b> Maximaler Strombezug des gesamten Quartiers aus übergeordnetem "
            "Stromnetz auf Basis der Betriebsoptimierung<br />"
            "<b>Max. Einspeiseleistung:</b> Maximale Stromeinspeisung des gesamten Quartiers in "
            "übergeordnetes Stromnetz auf Basis der Betriebsoptimierung<br />"
            "<b>Supply-Cover-Faktor:</b> Anteil des aus den Gebäuden des Quartiers ins lokale Netz eingespeisten "
            "Stroms, der für den Eigenverbrauch innerhalb des Quartiers durch andere Gebäude genutzt wird "
            "(Werte zwischen 0 % und 100 %)<br />"  
            "<b>Demand-Cover-Faktor:</b> Anteil des residualen Strombedarfs im Quartier, der durch den von den Gebäuden "
            "im Quartier erzeugten und ins lokale Netz eingespeisten Stroms gedeckt wird (Werte zwischen 0 % und 100 %)<br />"
            "<b>El-Autonomy-Faktor:</b> Anteil der Betriebszeit, in der der lokale Strombedarf vollständig durch die "
            "Stromerzeugung im Quartier gedeckt wird (Werte zwischen 0 % und 100 %)<br />"
            ]

        details_Style = ParagraphStyle('My Para style',
                                       fontName='Helvetica',
                                       fontSize=10,
                                       alignment=0,
                                       leftIndent=10,
                                       firstLineIndent=-20,
                                       spaceafter=6
                                       )

        term_height = height - 100

        for i in range(len(terms)):
            p = Paragraph("<font size=12><b>" + terms[i] + ":</b></font> <br />" + details[i], details_Style)
            p.wrap(width - 144, term_height)
            num_lines = len(p.blPara.lines)
            term_height = term_height - num_lines * 10
            p.drawOn(certificate, 72, term_height)
            term_height = term_height - 30

        # save certificate
        certificate.save()