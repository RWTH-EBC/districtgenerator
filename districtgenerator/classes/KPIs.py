# -*- coding: utf-8 -*-

import sys
import numpy as np
import os
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
import pandas as pd
from districtgenerator.classes.certificate_generator import CertificateBuilder

class KPIs:

    def __init__(self, data):
        """
        Constructor of KPIs class.

        Parameters
        ----------
        data : Datahandler object
            Datahandler object which contains all relevant information to compute the key performance indicators (KPIs).

        Returns
        -------
        None.
        """

        # initialize KPIs
        self.sum_res_load = None
        self.sum_res_inj = None
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
        self.gas_year = None
        self.biomass_year = None
        self.waste_year = None
        self.hydrogen_year = None
        self.oil_year = None
        self.district_heat_year = None
        self.seasonal_storage_used_year = None
        self.seasonal_storage_potential_year = None 
        self.seasonal_storage_utilization_year = None
        self.waste_heat_used_year = None
        self.waste_heat_potential_year = None
        self.waste_heat_utilization_year = None
        self.dcf_year = None
        self.scf_year = None
        self.annual_fixed_costs_decentral = None
        self.annual_fixed_costs_central = None
        self.decentral_individual_devices_annualized_cost = None
        self.central_individual_devices_annualized_cost = None
        self.total_ICE_fuel_liters = None
        self.gasoline_costs = None
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
        inputData["nbIntervals"] = 0
        for c in inputData["clusters"]:
            inputData["nbIntervals"] += inputData["clusterWeights"][c]

        # prepare the results of the optimizations for each cluster
        inputData["resultsOptimization"] = data.resultsOptimization
        inputData["district"] = data.district

        self.inputData = inputData

        # prepare data to compute KPIs
        self.prepareData(data)
        self.calculateResidualLoad(data)
        self.calculatePeakLoad()
        self.calculatePeakToValley()
        self.calculateEnergyExchangeGCP(data)
        self.calculateEnergyExchangeWithinDistrict(data)
        self.calculateAutonomy()
        self.calculateCoverFactors(data)
        self.calc_annual_cost_total(data)
        self.calc_total_areas_and_demands(data)
        self.calculateLCOH_buildings(data)
        self.calculateLCOH_EH(data)
        self.calculateOperationCosts(data)
        self.calculateCO2emissions(data)
        self.calculateGasolineCosts(data)

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

        # initialize lists
        electricityDemand_cluster = []
        electricityGeneration_cluster = []
        electricityGenerationRenewable_cluster = []
        lossesBattery_cumulated_cluster = []
        # Load data of decentral devices (to calculate battery losses)
        srcPath = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        self.sum_res_load = {}
        self.sum_res_inj = {}
        centralEnergyUnit_load = {}
        centralEnergyUnit_inj = {}

        for year in self.inputData["simulated_years"]:
            # summed el. load of all buildings , [number of time periods, time steps within periods]
            self.sum_res_load[year] = np.zeros([len(data.clusters), len(data.district[0]["user"].elec_cluster[0])])
            # summed el. injection of all buildings
            self.sum_res_inj[year] = np.zeros([len(data.clusters), len(data.district[0]["user"].elec_cluster[0])])
            # el. load central energy unit
            centralEnergyUnit_load[year] = np.zeros([len(data.clusters), len(data.district[0]["user"].elec_cluster[0])])
            # el. injection central energy unit
            centralEnergyUnit_inj[year] = np.zeros([len(data.clusters), len(data.district[0]["user"].elec_cluster[0])])

        ### for buildings
        for year in self.inputData["simulated_years"]:
            # loop over cluster
            for c in range(len(self.inputData["clusters"])):
                # loop over buildings
                for bldg_id in data.scenario["id"]:
                    idx = data.building_dict[str(bldg_id)]
                    self.sum_res_load[year][c, :] += np.array(self.inputData["resultsOptimization"][year][c][idx]["res_load"])
                    self.sum_res_inj[year][c, :] += np.array(self.inputData["resultsOptimization"][year][c][idx]["res_inj"])

        ### for central energy unit

    def calculateResidualLoad(self, data):
        """
        Calculate residual load at grid connection point (GCP) in [kW] for each year.
        Demand is positive and injection negative.

        Returns
        -------
        None.
        """
        res = {}
        for year in self.inputData["simulated_years"]:
            res[year] = np.zeros([len(self.inputData["clusters"]), len(data.district[0]["user"].elec_cluster[0])])

        # loop over cluster
        for year in self.inputData["simulated_years"]:
            for c in range(len(self.inputData["clusters"])):
                for t in range(len(data.district[0]["user"].elec_cluster[0])):
                    res[year][c, t] = self.inputData["resultsOptimization"][year][c]["P_dem_gcp"][t]\
                                - self.inputData["resultsOptimization"][year][c]["P_inj_gcp"][t]

        # create array and change unit from [W] to [kW]
        self.residualLoad = {}
        for year in self.inputData["simulated_years"]:
            self.residualLoad[year] = res[year] / 1000

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
            self.peakDemand[year] = round(np.max(self.residualLoad[year]), 3) #! Previously there was [:-4]? Why exclude last 4 time steps?
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
                PtV[c] = round(max(self.residualLoad[year][c, :]) - min(self.residualLoad[year][c, :]), 3) #! Removed [:-4], check if necessary

            # peak to valley for each time period[kW]
            self.peakToValley[year] = max(PtV)

    def calculateEnergyExchangeGCP(self, data):
        """
        Calculate energy exchange of the district with its environment in [kWh] for each year.
        """

        self.W_inj_GCP_year = {}
        self.W_dem_GCP_year = {}
        self.gas_year = {}
        self.biomass_year = {}
        self.waste_year = {}
        self.hydrogen_year = {}
        self.oil_year = {}
        self.districtHeat_year = {}
        self.seasonal_storage_used_year = {}
        self.seasonal_storage_potential_year = {}
        self.seasonal_storage_utilization_year = {}
        self.waste_heat_used_year = {}
        self.waste_heat_potential_year = {}
        self.waste_heat_utilization_year = {}

        self.el_dem_buildings = {}
        self.el_inj_buildings = {}
        self.el_dem_eh = {}
        self.el_inj_eh = {}

        for year in self.inputData["simulated_years"]:
            # Variables for the yearly consumption calculation
            self.W_inj_GCP_year[year] = 0
            self.W_dem_GCP_year[year] = 0
            self.gas_year[year] = 0
            self.biomass_year[year] = 0
            self.waste_year[year] = 0
            self.hydrogen_year[year] = 0
            self.oil_year[year] = 0
            self.districtHeat_year[year] = 0
            self.seasonal_storage_used_year[year] = 0
            self.seasonal_storage_potential_year[year] = 0
            self.waste_heat_used_year[year] = 0
            self.waste_heat_potential_year[year] = 0

            self.el_dem_buildings[year] = 0
            self.el_inj_buildings[year] = 0
            self.el_dem_eh[year] = 0
            self.el_inj_eh[year] = 0

            # loop over cluster
            for c in range(len(self.inputData["clusters"])):
                weight = self.inputData["clusterWeights"][self.inputData["clusters"][c]]
                opt_res = self.inputData["resultsOptimization"][year][c]

                self.W_dem_GCP_year[year] += opt_res["from_grid_total_el"] * weight
                self.W_inj_GCP_year[year] += opt_res["to_grid_total_el"] * weight
                self.gas_year[year] += opt_res["from_grid_total_gas"] * weight
                self.biomass_year[year] += opt_res["total_biomass_used"] * weight
                self.waste_year[year] += opt_res["total_waste_used"] * weight
                self.hydrogen_year[year] += opt_res["from_grid_total_hydrogen"] * weight
                self.oil_year[year] += opt_res["total_oil_used"] * weight
                self.districtHeat_year[year] += opt_res["total_district_heat_used"] * weight
                self.seasonal_storage_used_year[year] += opt_res["total_seasonal_dch"] * weight
                self.seasonal_storage_potential_year[year] += opt_res["total_seasonal_dch_potential"] * weight
                self.waste_heat_used_year[year] += opt_res["total_waste_heat_used"] * weight
                self.waste_heat_potential_year[year] += opt_res["total_waste_heat_potential"] * weight

                self.el_dem_buildings[year] += opt_res["from_grid_total_el_buildings"] * weight
                self.el_inj_buildings[year] += opt_res["to_grid_total_el_buildings"] * weight
                self.el_dem_eh[year] += opt_res["from_grid_total_el_eh"] * weight
                self.el_inj_eh[year] += opt_res["to_grid_total_el_eh"] * weight

            self.seasonal_storage_utilization_year[year] = (self.seasonal_storage_used_year[year] / self.seasonal_storage_potential_year[year]) if self.seasonal_storage_potential_year[year] > 0 else None
            self.waste_heat_utilization_year[year] = (self.waste_heat_used_year[year] / self.waste_heat_potential_year[year]) if self.waste_heat_potential_year[year] > 0 else None

    def calculateEnergyExchangeWithinDistrict(self, data):

        self.W_inj_buildings_year = {}
        self.W_dem_buildings_year = {}

        for year in self.inputData["simulated_years"]:
            self.W_inj_buildings_year[year] = 0
            self.W_dem_buildings_year[year] = 0
            # loop over cluster
            for c in range(len(self.inputData["clusters"])):
                self.W_dem_buildings_year[year] += sum(self.sum_res_load[year][c, :] * data.time["timeResolution"] / 3600 / 1000) \
                                            * self.inputData["clusterWeights"][self.inputData["clusters"][c]]
                self.W_inj_buildings_year[year] += sum(self.sum_res_inj[year][c, :] * data.time["timeResolution"] / 3600 / 1000) \
                                            * self.inputData["clusterWeights"][self.inputData["clusters"][c]]

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

        for year in self.inputData["simulated_years"]:
            self.supplyCoverFactor[year] = np.zeros(len(self.inputData["clusters"]))
            self.demandCoverFactor[year] = np.zeros(len(self.inputData["clusters"]))


            min = np.zeros([len(self.inputData["clusters"]), len(data.district[0]["user"].elec_cluster[0])], dtype=float)
            nenner_sup = np.zeros([len(self.inputData["clusters"]), len(data.district[0]["user"].elec_cluster[0])], dtype=float)
            nenner_dem = np.zeros([len(self.inputData["clusters"]), len(data.district[0]["user"].elec_cluster[0])], dtype=float)

            for c in range(len(self.inputData["clusters"])):
                for t in range(len(data.district[0]["user"].elec_cluster[0])):
                    a = 0
                    b = 0
                    # sum of all buildings for each timestep
                    for bldg_id in data.scenario["id"]:
                        idx = data.building_dict[str(bldg_id)]
                        a += self.inputData["resultsOptimization"][year][c][idx]["res_load"][t]
                        b += self.inputData["resultsOptimization"][year][c][idx]["res_inj"][t]
                    # At the same time step t, either res_load or res_inj should be 0.
                    # However, a and b could both be greater than 0 at the same time step t,
                    # since they represent the sums of all the buildings.
                    # If both a and b are greater than 0, it means electricity is being transported from one building to another.
                    # sum of all timesteps
                    nenner_dem[c, t] += a
                    nenner_sup[c, t] += b
                    min[c, t] = np.min([a, b])

                self.demandCoverFactor[year][c] = np.sum(min[c, :]) / np.sum(nenner_dem[c, :])
                self.supplyCoverFactor[year][c] = np.sum(min[c, :]) / np.sum(nenner_sup[c, :])

        # Calculate weighted average over all years

        self.dcf_year = {}
        self.scf_year = {}

        sum_ClusterWeights = sum(self.inputData["clusterWeights"][self.inputData["clusters"][c]]
                             for c in range(len(self.inputData["clusters"])))

        for year in self.inputData["simulated_years"]:
            self.dcf_year[year] = 0
            self.scf_year[year] = 0
            for c in range(len(self.inputData["clusters"])):
                weight = self.inputData["clusterWeights"][self.inputData["clusters"][c]] / sum_ClusterWeights
                self.dcf_year[year] += self.demandCoverFactor[year][c] * weight
                self.scf_year[year] += self.supplyCoverFactor[year][c] * weight

    def calc_annual_cost_total(self, data):

        scenario = data.scenario
        decentral_device_data = data.decentral_device_data
        district = data.district
        physics = data.physics

        # Count occurrences in the 'heater' column
        counts = scenario['heater'].value_counts()

        # Sum the values in the 'TES', 'PV', 'STC', 'EV', and 'BAT' columns
        counts["TES"] = scenario.apply(lambda row: 1 if (row['f_TES'] > 0 and row['heater'] != 'heat_grid') else 0,axis=1).sum()
        counts["PV"] = scenario.apply(lambda row: 1 if (row['f_PV1'] > 0 or row['f_PV2'] > 0) else 0, axis=1).sum()
        counts["STC"] = scenario['f_STC'].apply(lambda x: 1 if x > 0 else 0).sum()
        counts["EV"] = sum((lambda ev: len(ev) if any(x > 0 for x in ev) else 0)(d["user"].ev_capacity)for d in district)
        counts["BAT"] = scenario['f_BAT'].apply(lambda x: 1 if x > 0 else 0).sum()

        capacities = {}
        for n in range(len(district)):
            capacities[n] = {}
            capacities[n]["BOI"] = district[n]["capacities"]["BOI"] / 1000
            capacities[n]["BBOI"] = district[n]["capacities"]["BBOI"] / 1000
            capacities[n]["H2BOI"] = district[n]["capacities"]["H2BOI"] / 1000
            capacities[n]["OBOI"] = district[n]["capacities"]["OBOI"] / 1000
            capacities[n]["HP"] = district[n]["capacities"]["HP"] / 1000
            capacities[n]["EH"] = district[n]["capacities"]["EH"] / 1000
            capacities[n]["CC"] = district[n]["capacities"]["CC"] / 1000
            capacities[n]["CHP"] = district[n]["capacities"]["CHP"] / 1000
            capacities[n]["FC"] = district[n]["capacities"]["FC"] / 1000
            capacities[n]["DH"] = district[n]["capacities"]["DH"]/ decentral_device_data["DH"]["eta_th"] / 1000 # Price is payed for the power of the connection not for the actual thermal power delivered
            capacities[n]["PV"] = district[n]["capacities"]["PV"]["area"]
            capacities[n]["STC"] = district[n]["capacities"]["STC"]["area"]
            capacities[n]["EV"] =  district[n]["capacities"]["EV"] / 1000
            capacities[n]["BAT"] = district[n]["capacities"]["BAT"] / 1000
            capacities[n]["TES"] = (district[n]["capacities"]["TES"] / physics["rho_water"] / physics["c_p_water"] /
                                    decentral_device_data["TES"]["T_diff_max"] * 3600)

        calc_annual_investment = {}
        calc_annual_investment_unsubsidized = {}
        self.decentral_individual_devices_annualized_cost = {} #Dictionary to store annualized cost per device and building
        self.annual_fixed_costs_decentral = 0
        self.annual_fixed_costs_decentral_unsubsidized = 0

        devices = ["BOI", "BBOI", "H2BOI", "OBOI", "HP", "EH", "CC", "CHP", "FC", "DH", "PV", "STC", "EV", "BAT", "TES"]

        # Iteration over all buildings and then over all devices
        for n in range(len(district)):
            self.decentral_individual_devices_annualized_cost[n] = {} # Each building gets a sub-dictionary to store the annualized cost of its devices even if no devices are installed
            calc_annual_investment[n] = 0
            calc_annual_investment_unsubsidized[n] = 0

            # HP temperature measures
            # Only count measures if HP exists and sink temperature higher than 45°C
            if capacities[n]["HP"] > 0 and district[n]["envelope"].hp_measures == True:
                heatload_kw = district[n]["envelope"].heatload / 1000  # kW
                inv_eur_per_kw = data.decentral_device_data["HP"]["measures_inv_fix"]
                inv_total = inv_eur_per_kw * heatload_kw  # €

                ann_cost_meas = self.calc_annualized_investment(inv_total, data.ecoData)

                # Add to totals
                calc_annual_investment[n] += ann_cost_meas
                calc_annual_investment_unsubsidized[n] += ann_cost_meas

                self.decentral_individual_devices_annualized_cost[n]["T_reduction_measures"] = {
                    "cap": heatload_kw,
                    "subsidized_annual_cost": ann_cost_meas,
                    "unsubsidized_annual_cost": ann_cost_meas,
                }

            for dev in devices:
                cap = capacities[n][dev]
                if cap > 0:
                    subsidized_cost = self.calc_annual_cost_device(
                        decentral_device_data[dev],
                        data.ecoData,
                        cap,
                        mode="subsidized")

                    unsubsidized_cost = self.calc_annual_cost_device(
                        decentral_device_data[dev],
                        data.ecoData,
                        cap,
                        mode="unsubsidized")

                    # If HP is installed, EH investment is assumed to be included in HP
                    # → keep EH capacity visible, but set EH annualized costs to 0
                    if dev == "EH" and capacities[n].get("HP", 0) > 0:
                        subsidized_cost = 0.0
                        unsubsidized_cost = 0.0

                    calc_annual_investment[n] += subsidized_cost
                    calc_annual_investment_unsubsidized[n] += unsubsidized_cost
                    self.decentral_individual_devices_annualized_cost[n][dev] = {"cap":cap,
                                                                        "subsidized_annual_cost":subsidized_cost,
                                                                        "unsubsidized_annual_cost":unsubsidized_cost}

            self.annual_fixed_costs_decentral += calc_annual_investment[n] # Annualized investment costs with subsidies
            self.annual_fixed_costs_decentral_unsubsidized += calc_annual_investment_unsubsidized[n] # Annualized investment costs without subsidies

        # Central devices individual costs
        self.central_individual_devices_annualized_cost = {}
        try:
            self.annual_fixed_costs_central = data.centralDevices["capacities"]["total_ann_inv_cost"] + data.centralDevices["capacities"]["total_om_cost"]
            self.annual_fixed_costs_central_unsubsidized = data.centralDevices["capacities"]["total_ann_inv_cost_unsubsidized"] + data.centralDevices["capacities"]["total_om_cost"]

            # Extract individual device costs from optimization results
            if hasattr(data, 'centralDevices') and 'capacities' in data.centralDevices:
                for dev_name, dev_spec in data.centralDevices["capacities"].items():
                    # Skip non-dict entries (like total_ann_inv_cost, etc.)
                    if not isinstance(dev_spec, dict):
                        continue
                    cap = dev_spec.get("cap", 0)
                    if cap <= 0:
                        continue

                    # Get annualized costs directly from optimization results
                    subsidized_cost = dev_spec.get("ann_inv_cost", 0)
                    unsubsidized_cost = dev_spec.get("ann_inv_cost_unsubsidized", 0)
                    om_cost = dev_spec.get("om_cost", 0)

                    # Total costs (investment + O&M)
                    total_subsidized = subsidized_cost + om_cost
                    total_unsubsidized = unsubsidized_cost + om_cost

                    # Store in dictionary (similar to decentral devices)
                    self.central_individual_devices_annualized_cost[dev_name] = {
                        "cap": cap,
                        "subsidized_annual_cost": total_subsidized,
                        "unsubsidized_annual_cost": total_unsubsidized
                    }

            # Add heat grid costs if available
            if hasattr(data, 'heat_grid_data') and data.heat_grid_data:
                heat_grid_ann_cost = data.heat_grid_data.get("ann_costs", 0)
                heat_grid_om_cost = data.heat_grid_data.get("om_costs", 0)
                heat_grid_total_cost = data.heat_grid_data.get("costs", 0)

                # Only add if costs exist
                if heat_grid_total_cost > 0 or (heat_grid_ann_cost + heat_grid_om_cost) > 0:
                    self.central_individual_devices_annualized_cost["Heat_Grid"] = {
                        "cap": '',  # Use total investment cost as "capacity" indicator
                        "subsidized_annual_cost": heat_grid_ann_cost + heat_grid_om_cost,
                        "unsubsidized_annual_cost": heat_grid_ann_cost + heat_grid_om_cost  # Same for heat grid (no subsidies)
                    }

        except KeyError:
            self.annual_fixed_costs_central = 0
            self.annual_fixed_costs_central_unsubsidized = 0

    def calculateDetailedCostsPerYear(self, data):
        """Calculate the detailed costs for each simulated year."""
        self.detailed_costs_year = {}

        for year in self.inputData["simulated_years"]:
            ecoData = data.all_sim_ecoData[year]


            # Save all costs in a dictionary for each year
            self.detailed_costs_year[year] = {
                "eh_fixed": self.annual_fixed_costs_central,
                "decentral_fixed": self.annual_fixed_costs_decentral,
                "electricity": self.el_dem_buildings[year] * ecoData["price_supply_el"] + self.el_dem_eh[year] * ecoData["price_supply_el_eh"],
                "gas": self.gas_year[year] * ecoData["price_supply_gas"],
                "oil": self.oil_year[year] * ecoData["price_oil"],
                "waste": self.waste_year[year] * ecoData["price_waste"],
                "biomass": self.biomass_year[year] * ecoData["price_biomass"],
                "district_heat": self.districtHeat_year[year] * ecoData["price_district_heat"],
                "hydrogen": self.hydrogen_year[year] * ecoData["price_hydrogen"],
                "waste_heat": self.waste_heat_used_year[year] * ecoData["price_waste_heat"],
                "revenue_feed_in_el": -(self.el_inj_buildings[year] * ecoData["revenue_feed_in_el"] + self.el_inj_eh[year] * ecoData["revenue_feed_in_el_eh"])
            }

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
        else: raise ValueError(f"Mode {mode} for investment cost calculation not recognized. Possible modes are 'subsidized' and 'unsubsidized'.")

        c_om = 0 # Operation, maintenance and capacity costs

        if dev.get("cost_om",None) is not None: # operation and maintenance costs [€/(a*€_invested)] Always use the unsubsidized investment for O&M calculation
            c_om += dev["cost_om"] * inv_unsubsidized

        if dev.get("cap_fee",None) is not None : # if a Capacity fee exists [€/(kW*a)]
            c_om += dev["cap_fee"] * cap

        # Total annual cost
        c_total = c_inv + c_om

        return c_total

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

        operationCosts_clusters = {}
        self.operationCosts = {}

        for year in self.inputData["simulated_years"]:
            operationCosts_clusters[year] = {}
            for c in range(len(self.inputData["clusters"])):
                operationCosts_clusters[year][c] = self.inputData["resultsOptimization"][year][c]["Cost_total"]
                #print(f"Operation costs for year {year}, cluster {c}: {operationCosts_clusters[year][c]} €")

            # multiply central operation costs of each cluster with the weight of respective cluster
            temp_operationCosts = 0
            for c in range(len(self.inputData["clusters"])):
                temp_operationCosts += operationCosts_clusters[year][c] * self.inputData["clusterWeights"][self.inputData["clusters"][c]]

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
            co2_dem_grid = self.W_dem_GCP_year[year] * ecoData["co2_el_grid"] / 1000    # in t/a
            co2_gas = self.gas_year[year] * ecoData["co2_gas"] / 1000                   # in t/a
            co2_biom = self.biomass_year[year] * ecoData["co2_biom"] / 1000         # in t/a
            co2_waste = self.waste_year[year] * ecoData["co2_waste"] / 1000             # in t/a
            co2_hydrogen = self.hydrogen_year[year] * ecoData["co2_hydrogen"] / 1000       # in t/a
            co2_oil = self.oil_year[year] * ecoData["co2_oil"] / 1000                       # in t/a
            co2_district_heat = self.districtHeat_year[year] * ecoData["co2_district_heat"] / 1000   # in t/a
            co2_waste_heat = self.waste_heat_used_year[year] * ecoData["co2_waste_heat"] / 1000   # in t/a

            # total CO2 emissions [kg/a]
            total_co2 = co2_dem_grid + co2_gas + co2_biom + co2_waste + co2_hydrogen + co2_oil + co2_district_heat + co2_waste_heat

            # CO2 emissions for each simulated year
            self.co2emissions[year] = { #! Save individual contributions for possible later use. Important: Do not sum all values. Comined already included.
                "total_co2": total_co2,
                "co2_dem_grid": co2_dem_grid,
                "co2_gas": co2_gas,
                "co2_biom": co2_biom,
                "co2_waste": co2_waste,
                "co2_hydrogen": co2_hydrogen,
                "co2_oil": co2_oil,
                "co2_district_heat": co2_district_heat,
                "co2_waste_heat": co2_waste_heat
            }

    def calculateLCOH_buildings(self, data):
        """
        Calculate the building-level Levelized Cost of Heat (LCOH) in ct/kWh.

        This function computes the average cost per unit of useful heat delivered
        to each building for every simulated year. The LCOH includes:

        For co-generation technologies (CHP and fuel cells) producing both heat
        and electricity, fuel costs are allocated using a price-based allocation
        method:
                share_heat = (Q * price_dh) / (Q * price_dh + E * price_el)

        Parameters
        ----------
        data

        Returns
        -------
        None
        """

        years = self.inputData["simulated_years"]
        clusters = self.inputData["clusters"]
        cweights = self.inputData["clusterWeights"]
        dt = float(data.time["timeResolution"])

        self.lcoh_year_building = {}

        for year in years:
            eco = data.all_sim_ecoData[year]

            price_gas = eco["price_supply_gas"]
            price_el = eco["price_supply_el"]
            price_biom = eco.get("price_biomass", 0.0)
            price_h2 = eco.get("price_hydrogen", 0.0)
            price_oil = eco.get("price_oil", 0.0)
            price_dh = eco.get("price_district_heat", 0.0)

            self.lcoh_year_building[year] = {}

            # LOOP BUILDINGS
            for n in range(len(data.district)):

                Q_total_building = (sum(data.district[n]["user"].dhw) + sum(data.district[n]["user"].heat)) * dt / 3600 / 1000
                fuel_cost_heat = 0.0
                el_cost_heat = 0.0
                dh_cost_heat = 0.0
                fixed_cost_heat = 0.0
                heater_type = data.district[n]["buildingFeatures"]["heater"]

                heat_devices = {"BOI", "BBOI", "H2BOI", "OBOI", "HP", "EH", "CHP", "FC", "DH", "TES", "STC", "T_reduction_measures"}

                # Fixed cost allocation
                for dev, info in self.decentral_individual_devices_annualized_cost.get(n, {}).items():
                    if dev in heat_devices:
                        fixed_cost_heat += float(info.get("subsidized_annual_cost", 0.0))

                # LOOP CLUSTERS
                for c in range(len(clusters)):

                    cw = float(cweights[clusters[c]])
                    cluster = self.inputData["resultsOptimization"][year][c]
                    res = cluster[n]
                    T = len(res.get("res_load", []))

                    # District Heating
                    if heater_type == "DH" and "DH" in res:
                        dh_energy = (np.array(res["DH"].get("Q_th", [0] * T)).sum() * dt / 3600 / 1000)
                        dh_cost_heat += cw * dh_energy * price_dh

                    # Boilers
                    if heater_type in ["BOI", "GHP"] and "BOI" in res:
                        Q = np.array(res["BOI"].get("Q_th", [0] * T))
                        eta = data.decentral_device_data["BOI"]["eta_th"]
                        fuel = Q.sum() / eta * dt / 3600 / 1000
                        fuel_cost_heat += cw * fuel * price_gas

                    if heater_type in ["BBOI", "BHP"] and "BBOI" in res:
                        Q = np.array(res["BBOI"].get("Q_th", [0] * T))
                        eta = data.decentral_device_data["BBOI"]["eta_th"]
                        fuel = Q.sum() / eta * dt / 3600 / 1000
                        fuel_cost_heat += cw * fuel * price_biom

                    if heater_type in ["OBOI", "OHP"] and "OBOI" in res:
                        Q = np.array(res["OBOI"].get("Q_th", [0] * T))
                        eta = data.decentral_device_data["OBOI"]["eta_th"]
                        fuel = Q.sum() / eta * dt / 3600 / 1000
                        fuel_cost_heat += cw * fuel * price_oil

                    if heater_type in ["H2BOI", "H2HP"] and "H2BOI" in res:
                        Q = np.array(res["H2BOI"].get("Q_th", [0] * T))
                        eta = data.decentral_device_data["H2BOI"]["eta_th"]
                        fuel = Q.sum() / eta * dt / 3600 / 1000
                        fuel_cost_heat += cw * fuel * price_h2

                    if heater_type == "CHP" and "CHP" in res:
                        E_chp = np.array(res["CHP"].get("P_el", [0] * T))
                        eta_th = data.decentral_device_data["CHP"]["eta_th"]
                        eta_el = data.decentral_device_data["CHP"]["eta_el"]
                        Q_chp = E_chp/eta_el*eta_th

                        Q_kWh = Q_chp.sum() * dt / 3600 / 1000
                        E_kWh = E_chp.sum() * dt / 3600 / 1000
                        if Q_kWh > 0:
                            fuel_input = Q_kWh / eta_th
                            share_heat = (Q_kWh * price_dh) / (Q_kWh * price_dh + E_kWh * price_el + 1e-9)
                            fuel_cost_heat += cw * share_heat * fuel_input * price_gas

                    if heater_type == "FC" and "FC" in res:
                        E_fc = np.array(res["FC"].get("P_el", [0] * T))
                        eta_th = data.decentral_device_data["FC"]["eta_th"]
                        eta_el = data.decentral_device_data["FC"]["eta_el"]
                        Q_fc = E_fc/eta_el*eta_th

                        Q_kWh = Q_fc.sum() * dt / 3600 / 1000
                        E_kWh = E_fc.sum() * dt / 3600 / 1000
                        if Q_kWh > 0:
                            fuel_input = Q_kWh / eta_th
                            share_heat = (Q_kWh * price_dh) / (Q_kWh * price_dh + E_kWh * price_el + 1e-9)
                            fuel_cost_heat += cw * share_heat * fuel_input * price_h2

                    if heater_type in ["HP", "BHP", "OHP", "H2HP", "GHP", "EH"]:
                        el_heat_from_grid_cluster = 0.0
                        for t in range(T):
                            hp_t = res.get("HP", {}).get("P_el", [0] * T)[t]
                            eh_t = res.get("EH", {}).get("P_el", [0] * T)[t]
                            grid_t = res.get("res_load", [0] * T)[t]
                            el_heat_t = (hp_t + eh_t) * dt / 3600 / 1000
                            grid_t_kWh = grid_t * dt / 3600 / 1000
                            el_heat_from_grid_cluster += min(el_heat_t, grid_t_kWh)
                        el_cost_heat += cw * el_heat_from_grid_cluster * price_el

                # LCOH per building
                total_cost = (
                        fixed_cost_heat +
                        fuel_cost_heat +
                        el_cost_heat +
                        dh_cost_heat)

                if Q_total_building > 1e-9:
                    lcoh = 100.0 * total_cost / Q_total_building
                else:
                    lcoh = 0.0

                self.lcoh_year_building[year][n] = lcoh

    def calculateLCOH_EH(self, data):
        """
        Calculate the Energy Hub Levelized Cost of Heat (LCOH) in ct/kWh.

        This function computes the average cost per unit of useful heat supplied
        by the central Energy Hub to all buildings connected to the district
        heating network for each simulated year.

        For co-generation technologies (CHP, biomass CHP, waste CHP, and fuel
        cells), fuel costs are allocated between heat and electricity using a
        price-based allocation method:

            share_heat = (Q * price_dh) / (Q * price_dh + E * price_el)

        Parameters
        ----------
        data

        Returns
        -------
        None
        """

        years = self.inputData["simulated_years"]
        clusters = self.inputData["clusters"]
        cweights = self.inputData["clusterWeights"]
        dt = float(data.time["timeResolution"])

        self.lcoh_year_eh = {}

        for year in years:

            eco = data.all_sim_ecoData[year]

            # Energy hub specific prices
            price_gas = eco.get("price_supply_gas_eh", eco["price_supply_gas"])
            price_el = eco.get("price_supply_el_eh", eco["price_supply_el"])
            price_biom = eco.get("price_biomass", 0.0)
            price_h2 = eco.get("price_hydrogen", 0.0)
            price_oil = eco.get("price_oil", 0.0)
            price_waste = eco["price_waste"]
            price_waste_heat = eco["price_waste_heat"]
            price_dh = eco.get("price_district_heat", 0.0)

            self.lcoh_year_eh[year] = {}

            # TOTAL HEAT DELIVERED
            Q_total_eh = 0.0

            for n in range(len(data.district)):
                if data.district[n]["buildingFeatures"]["heater"] == "heat_grid":
                    Q_building = (np.sum(data.district[n]["user"].dhw) + np.sum(data.district[n]["user"].heat)) * dt / 3600 / 1000
                    Q_total_eh += Q_building

            fuel_cost_heat = 0.0
            el_cost_heat = 0.0
            fixed_cost_heat = 0.0

            heat_devices = {"TES", "EB", "FC", "WBOI", "WCHP", "BBOI", "BCHP", "HP", "GroundHP", "Waste_HeatHP", "Waste_HeatDirect", "GHP", "BOI", "CHP", "STC"}

            # Central heat-producing devices only
            for dev, info in self.central_individual_devices_annualized_cost.items():
                if dev in heat_devices:
                    fixed_cost_heat += float(info.get("subsidized_annual_cost", 0.0))

            # Heating network investment
            if hasattr(data, "heat_grid_data") and isinstance(data.heat_grid_data, dict):
                fixed_cost_heat += (
                        float(data.heat_grid_data.get("om_costs", 0.0)) +
                        float(data.heat_grid_data.get("ann_costs", 0.0)))

            waste_heat_cost = self.waste_heat_used_year[year] * price_waste_heat

            # LOOP CLUSTERS
            for c in range(len(clusters)):

                cw = float(cweights[clusters[c]])
                cluster = self.inputData["resultsOptimization"][year][c]
                eh_power = cluster["eh_power"]
                eh_heat = cluster["eh_heat"]
                eh_gas = cluster["eh_gas"]
                eh_h2 = cluster["eh_hydrogen"]
                eh_biom = cluster["eh_biom"]
                eh_waste = cluster["eh_waste"]

                T = len(next(iter(eh_power.values())))

                # Gas boilers
                Q = np.array(eh_heat["BOI"])
                eta = data.central_device_data["BOI"]["eta_th"]
                fuel = Q.sum() / eta * dt / 3600 / 1000
                fuel_cost_heat += cw * fuel * price_gas

                # Biomass boiler
                Q = np.array(eh_heat["BBOI"])
                eta = data.central_device_data["BBOI"]["eta_th"]
                fuel = Q.sum() / eta * dt / 3600 / 1000
                fuel_cost_heat += cw * fuel * price_biom

                # Waste boiler
                Q = np.array(eh_heat["WBOI"])
                eta = data.central_device_data["WBOI"]["eta_th"]
                fuel = Q.sum() / eta * dt / 3600 / 1000
                fuel_cost_heat += cw * fuel * price_waste

                # CHP (gas)
                fuel = np.array(eh_gas.get("CHP", [0] * T))
                Q = np.array(eh_heat.get("CHP", [0] * T))
                E = np.array(eh_power.get("CHP", [0] * T))

                fuel_kWh = fuel.sum() * dt / 3600 / 1000
                Q_kWh = Q.sum() * dt / 3600 / 1000
                E_kWh = E.sum() * dt / 3600 / 1000

                if Q_kWh > 0 and E_kWh > 0:
                    share_heat = (Q_kWh * price_dh) / (Q_kWh * price_dh + E_kWh * price_el + 1e-9)
                    fuel_cost_heat += cw * share_heat * fuel_kWh * price_gas

                # Waste CHP (WCHP)
                fuel = np.array(eh_waste.get("WCHP", [0] * T))
                Q = np.array(eh_heat.get("WCHP", [0] * T))
                E = np.array(eh_power.get("WCHP", [0] * T))

                fuel_kWh = fuel.sum() * dt / 3600 / 1000
                Q_kWh = Q.sum() * dt / 3600 / 1000
                E_kWh = E.sum() * dt / 3600 / 1000

                if Q_kWh > 0 and E_kWh > 0:
                    share_heat = (Q_kWh * price_dh) / (Q_kWh * price_dh + E_kWh * price_el + 1e-9)
                    fuel_cost_heat += cw * share_heat * fuel_kWh * price_waste

                # Biomass CHP (BCHP)
                fuel = np.array(eh_biom.get("BCHP", [0] * T))
                Q = np.array(eh_heat.get("BCHP", [0] * T))
                E = np.array(eh_power.get("BCHP", [0] * T))

                fuel_kWh = fuel.sum() * dt / 3600 / 1000
                Q_kWh = Q.sum() * dt / 3600 / 1000
                E_kWh = E.sum() * dt / 3600 / 1000

                if Q_kWh > 0 and E_kWh > 0:
                    share_heat = (Q_kWh * price_dh) / (Q_kWh * price_dh + E_kWh * price_el + 1e-9)
                    fuel_cost_heat += cw * share_heat * fuel_kWh * price_biom

                # Fuel Cell
                fuel = np.array(eh_h2.get("FC", [0] * T))
                Q = np.array(eh_heat.get("FC", [0] * T))
                E = np.array(eh_power.get("FC", [0] * T))

                fuel_kWh = fuel.sum() * dt / 3600 / 1000
                Q_kWh = Q.sum() * dt / 3600 / 1000
                E_kWh = E.sum() * dt / 3600 / 1000

                if Q_kWh > 0 and E_kWh > 0:
                    share_heat = (Q_kWh * price_dh) / (Q_kWh * price_dh + E_kWh * price_el + 1e-9)
                    fuel_cost_heat += cw * share_heat * fuel_kWh * price_h2

                # Electricity cost for all heat pumps and electric boilers
                el_heat_from_grid_cluster = 0.0
                for t in range(T):
                    hp_t = eh_power.get("HP", [0] * T)[t]
                    ghp_t = eh_power.get("GroundHP", [0] * T)[t]
                    whhp_t = eh_power.get("Waste_HeatHP", [0] * T)[t]
                    eb_t = eh_power.get("EB", [0] * T)[t]
                    grid_t =eh_power.get("from_grid", [0] * T)[t]
                    el_heat_t = (hp_t + ghp_t + whhp_t + eb_t) * dt / 3600 / 1000
                    grid_kWh = grid_t * dt / 3600 / 1000
                    el_heat_from_grid_cluster += min(el_heat_t, grid_kWh)
                el_cost_heat += cw * el_heat_from_grid_cluster * price_el

            # LCOH
            total_cost = fixed_cost_heat + fuel_cost_heat + el_cost_heat + waste_heat_cost

            if Q_total_eh > 1e-9:
                lcoh_eh = 100.0 * total_cost / Q_total_eh
            else:
                lcoh_eh = 0.0

            self.lcoh_year_eh[year] = lcoh_eh

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
        sum_ClusterWeights = sum(self.inputData["clusterWeights"][self.inputData["clusters"][c]] for c in range(len(self.inputData["clusters"])))

        # Loop over each simulated year
        for year in self.inputData["simulated_years"]:
            LOLP = np.zeros(len(self.inputData["clusters"]))
            energy_autonomy_clusters = np.zeros(len(self.inputData["clusters"]))

            # Loop over clusters
            for c in range(len(self.inputData["clusters"])):
                y = 0  # Count timesteps with grid demand
                total_timesteps = self.residualLoad[year][c, :].size

                for t in range(total_timesteps):
                    if self.residualLoad[year][c, t] > 0:  # Grid demand (positive)
                        y += 1

                LOLP[c] = y / total_timesteps
                energy_autonomy_clusters[c] = 1 - LOLP[c]

            # Store per-cluster autonomy for this year
            self.energy_autonomy[year] = energy_autonomy_clusters

            # Calculate weighted average for this year
            self.energy_autonomy_year[year] = sum(
                energy_autonomy_clusters[c] * (
                    self.inputData["clusterWeights"][self.inputData["clusters"][c]] / sum_ClusterWeights
                )
                for c in range(len(self.inputData["clusters"]))
            )

    def calc_total_areas_and_demands(self, data):
        """
        Returns
        -------
        None.
        """
        total_area_residential = 0
        total_area_mixed = 0
        total_area_non_residential = 0
        total_number_flats = 0
        total_number_occ = 0
        total_heat_load = 0
        total_cooling_load = 0
        total_heating_demand = 0
        total_cooling_demand = 0
        total_electricity_demand = 0
        total_EV_demand = 0
        total_dhw_demand = 0
        total_ICE_fuel_liters = 0
        sum_electricity_profile = []
        sum_EV_profile = []
        sum_heat_profile = []
        sum_cool_profile = []
        sum_dhw_profile = []

        for building in data.district:
            if building["buildingFeatures"]["building"] in {"SFH", "MFH", "TH", "AB"}:
                # sum all building areas
                total_area_residential += building["buildingFeatures"]["area"]
                total_number_flats += building["user"].nb_units
                for flat in building["user"].nb_occ:
                    total_number_occ += flat
            # Mixed Buildings
            elif "+" in building["buildingFeatures"]["building"]:
                total_area_mixed += building["buildingFeatures"]["area"]
                total_number_flats += building["user"].nb_res_flats
                for flat in building["user"].nb_res_occ:
                    total_number_occ += flat                
            else:
                total_area_non_residential += building["buildingFeatures"]["area"]
            total_ICE_fuel_liters += np.sum(building["user"].ice_carprofile)  # liters per timestep summed over year

            # sum all building design heat and cooling loads
            total_heat_load += building["envelope"].heatload + building["dhwpower"]
            total_cooling_load += max(building["user"].cooling)

            # sum all building demands
            total_heating_demand += sum(building["user"].heat)
            total_cooling_demand += sum(building["user"].cooling)
            total_electricity_demand += sum(building["user"].elec)   # w/o EVs and electric-based heaters
            total_EV_demand += sum(building["user"].EV_carprofile)
            total_dhw_demand += sum(building["user"].dhw)

            # sum all building demand profiles
            sum_electricity_profile = [sum(i) for i in zip_longest(
                sum_electricity_profile, building["user"].elec, fillvalue=0)] # w/o EVs and electric-based heaters
            sum_EV_profile = [sum(i) for i in zip_longest(
                sum_EV_profile, building["user"].EV_carprofile, fillvalue=0)]
            sum_heat_profile = [sum(i) for i in zip_longest(
                sum_heat_profile, building["user"].heat, fillvalue=0)]
            sum_cool_profile = [sum(i) for i in zip_longest(
                sum_cool_profile, building["user"].cooling, fillvalue=0)]
            sum_dhw_profile = [sum(i) for i in zip_longest(
                sum_dhw_profile, building["user"].dhw, fillvalue=0)]

        self.totalarea_residential = total_area_residential
        self.total_area_mixed = total_area_mixed
        self.totalarea_non_residential = total_area_non_residential
        self.totalnumberflats = total_number_flats
        self.totalnumberocc = total_number_occ
        self.totalheatload = total_heat_load
        self.totalcoolingload = total_cooling_load
        self.total_heating_demand = total_heating_demand
        self.total_cooling_demand = total_cooling_demand
        self.total_electricity_demand = total_electricity_demand   # w/o EVs and electric-based heaters
        self.total_EV_demand = total_EV_demand
        self.total_dhw_demand = total_dhw_demand
        self.total_electricity_peak = max(sum_electricity_profile)
        self.total_heat_peak = max(sum_heat_profile)
        self.total_dhw_peak = max(sum_dhw_profile)
        self.total_cooling_peak = max(sum_cool_profile)
        self.total_EV_peak = max(sum_EV_profile)
        self.total_ICE_fuel_liters = float(total_ICE_fuel_liters)

    def calc_total_consumption_and_emissions(self, data):
        """
        Calculates:
        - total consumption of energy carriers in the district
        - total CO2 emissions of the district for each energy carrier
        - Calculates average CO2 emissions per year over the entire observation period.
        - Calculates the total operation costs over the entire observation period.
        - Calculates the average annual operation costs over the entire observation period.

        Uses year weights to account for the interval that each simulated year represents.


        Retuns
        -------
        None.
        """
        # Calculate year weights (duration each simulated year represents)
        sorted_years = sorted(self.inputData["simulated_years"])
        observation_time = data.ecoData["observation_time"]
        year_weights = {}

        for idx, year in enumerate(sorted_years):
            if idx < len(sorted_years) - 1:
                year_weights[year] = sorted_years[idx + 1] - year  # time until next support year
            else:
                year_weights[year] = observation_time - year  # time from last support year to end of observation period

        # Calculate total consumption over all years (weighted by interval length)
        self.total_W_dem_GCP = sum(self.W_dem_GCP_year[year] * year_weights[year] for year in sorted_years) # demand from grid
        self.total_W_inj_GCP = sum(self.W_inj_GCP_year[year] * year_weights[year] for year in sorted_years) # injection to grid
        self.total_W_dem_buildings = sum(self.W_dem_buildings_year[year] * year_weights[year] for year in sorted_years) # total residual electricity demand within district by buildings
        self.total_W_inj_buildings = sum(self.W_inj_buildings_year[year] * year_weights[year] for year in sorted_years) # total residual electricity injection within district by buildings
        self.total_gas = sum(self.gas_year[year] * year_weights[year] for year in sorted_years) # gas consumption of the district
        self.total_biomass = sum(self.biomass_year[year] * year_weights[year] for year in sorted_years) # biomass consumption
        self.total_waste = sum(self.waste_year[year] * year_weights[year] for year in sorted_years) # waste consumption
        self.total_hydrogen = sum(self.hydrogen_year[year] * year_weights[year] for year in sorted_years) # hydrogen consumption
        self.total_oil = sum(self.oil_year[year] * year_weights[year] for year in sorted_years) # oil consumption
        self.total_districtHeat = sum(self.districtHeat_year[year] * year_weights[year] for year in sorted_years) # district heat consumption
        self.total_seasonal_storage_used = sum(self.seasonal_storage_used_year[year] * year_weights[year] for year in sorted_years) # seasonal storage used
        self.total_seasonal_storage_potential = sum(self.seasonal_storage_potential_year[year] * year_weights[year] for year in sorted_years)
        self.total_seasonal_storage_utilization = self.total_seasonal_storage_used / self.total_seasonal_storage_potential if self.total_seasonal_storage_potential > 0 else None
        self.total_waste_heat_used = sum(self.waste_heat_used_year[year] * year_weights[year] for year in sorted_years) # waste heat used
        self.total_waste_heat_potential = sum(self.waste_heat_potential_year[year] * year_weights[year] for year in sorted_years)
        self.total_waste_heat_utilization = self.total_waste_heat_used / self.total_waste_heat_potential if self.total_waste_heat_potential > 0 else None

        # Calculate total CO2 emissions over all years (weighted by interval length)
        self.total_co2_all = sum(self.co2emissions[year]["total_co2"] * year_weights[year] for year in sorted_years) # total CO2 emissions
        self.total_co2_dem_grid = sum(self.co2emissions[year]["co2_dem_grid"] * year_weights[year] for year in sorted_years) # CO2 emissions from electricity from grid
        self.total_co2_gas = sum(self.co2emissions[year]["co2_gas"] * year_weights[year] for year in sorted_years) # CO2 emissions from gas consumption
        self.total_co2_biom = sum(self.co2emissions[year]["co2_biom"] * year_weights[year] for year in sorted_years) # CO2 emissions from biomass consumption
        self.total_co2_waste = sum(self.co2emissions[year]["co2_waste"] * year_weights[year] for year in sorted_years) # CO2 emissions from waste consumption
        self.total_co2_hydrogen = sum(self.co2emissions[year]["co2_hydrogen"] * year_weights[year] for year in sorted_years) # CO2 emissions from hydrogen consumption
        self.total_co2_oil = sum(self.co2emissions[year]["co2_oil"] * year_weights[year] for year in sorted_years) # CO2 emissions from oil consumption
        self.total_co2_district_heat = sum(self.co2emissions[year]["co2_district_heat"] * year_weights[year] for year in sorted_years) # CO2 emissions from district heat consumption

        self.avg_co2_emissions = self.total_co2_all / observation_time
        self.total_operation_costs = sum(self.operationCosts[year] * year_weights[year] for year in sorted_years)
        self.avg_operationCosts = self.total_operation_costs / observation_time
        self.avg_seasonal_storage_potential = self.total_seasonal_storage_potential / observation_time
        self.avg_seasonal_storage_used = self.total_seasonal_storage_used / observation_time
        self.avg_seasonal_storage_utilization = self.total_seasonal_storage_used / self.total_seasonal_storage_potential if self.total_seasonal_storage_potential > 0 else None
        self.avg_waste_heat_potential = self.total_waste_heat_potential / observation_time
        self.avg_waste_heat_used = self.total_waste_heat_used / observation_time
        self.avg_waste_heat_utilization = self.total_waste_heat_used / self.total_waste_heat_potential if self.total_waste_heat_potential > 0 else None

    def calculateGasolineCosts(self, data):
        """Compute annual gasoline costs (€) for each simulated year."""
        self.gasoline_costs = {}

        for year in self.inputData["simulated_years"]:
            price_per_liter = data.all_sim_ecoData[year]["price_gasoline_liter"]  # €/liter
            self.gasoline_costs[year] = float(self.total_ICE_fuel_liters) * float(price_per_liter)

    def calculateAllKPIs(self, data):
        """
        Calculate all KPIs.

        Returns
        -------
        None.
        """

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
        self.calculateDetailedCostsPerYear(data)
        self.calculateLCOH_buildings(data)
        self.calculateLCOH_EH(data)
        self.saveKPIs(scenario_name=data.scenario_name, result_path=data.resultPath, buildings=data.district, file_format=data.report_config["kpi_save_type"])

    def saveKPIs(self, scenario_name, result_path, buildings, file_format):
        """
        Save all calculated KPIs in a file. Ensure that calculateAllKPIs() has been called before. Saves as the specified file format (csv/excel)

        Parameters
        - self: KPICalculator instance
        - scenario_name: Name of the scenario for file naming
        - result_path: Path to save the results
        """

        # Get all simulated years
        years = sorted(self.inputData["simulated_years"])

        # Create dictionary for year-dependent KPIs
        kpi_data_yearly = {}
        kpi_data_yearly["Peak Demand district (kW)"] = {year: self.peakDemand.get(year, None) for year in years}
        kpi_data_yearly["Peak Injection district (kW)"] = {year: self.peakInjection.get(year, None) for year in years}
        kpi_data_yearly["Peak to Valley (kW)"] = {year: self.peakToValley.get(year, None) for year in years}
        kpi_data_yearly["Electricity Injection to Grid (kWh/a)"] = {year: self.W_inj_GCP_year.get(year, None) for year in years}
        kpi_data_yearly["Electricity Demand from Grid (kWh/a)"] = {year: self.W_dem_GCP_year.get(year, None) for year in years}
        kpi_data_yearly["Gas Consumption (kWh/a)"] = {year: self.gas_year.get(year, None) for year in years}
        kpi_data_yearly["Biomass Consumption (kWh/a)"] = {year: self.biomass_year.get(year, None) for year in years}
        kpi_data_yearly["Waste Consumption (kWh/a)"] = {year: self.waste_year.get(year, None) for year in years}
        kpi_data_yearly["Hydrogen Consumption (kWh/a)"] = {year: self.hydrogen_year.get(year, None) for year in years}
        kpi_data_yearly["Oil Consumption (kWh/a)"] = {year: self.oil_year.get(year, None) for year in years}
        kpi_data_yearly["District Heat Consumption (kWh/a)"] = {year: self.districtHeat_year.get(year, None) for year in years}
        kpi_data_yearly["Seasonal Storage Used (kWh/a)"] = {year: self.seasonal_storage_used_year.get(year, None) for year in years}
        kpi_data_yearly["Seasonal Storage Potential (kWh/a)"] = {year: self.seasonal_storage_potential_year.get(year, None) for year in years}
        kpi_data_yearly["Seasonal Storage Utilization (%)"] = {year: self.seasonal_storage_utilization_year[year] * 100 if self.seasonal_storage_utilization_year[year] is not None else None for year in years}
        kpi_data_yearly["Waste Heat Used (kWh/a)"] = {year: self.waste_heat_used_year.get(year, None) for year in years}
        kpi_data_yearly["Waste Heat Potential (kWh/a)"] = {year: self.waste_heat_potential_year.get(year, None) for year in years}
        kpi_data_yearly["Waste Heat Utilization (%)"] = {year: self.waste_heat_utilization_year[year] * 100 if self.waste_heat_utilization_year[year] is not None else None for year in years}
        kpi_data_yearly["Waste Heat Costs (€/a)"] = {year: self.detailed_costs_year.get(year, {}).get("waste_heat", None) for year in years}
        kpi_data_yearly["Electricity Injection within District (kWh/a)"] = {year: self.W_inj_buildings_year.get(year, None) for year in years}
        kpi_data_yearly["Electricity Demand within District (kWh/a)"] = {year: self.W_dem_buildings_year.get(year, None) for year in years}
        kpi_data_yearly["Demand Cover Factor (-)"] = {year: self.dcf_year.get(year, None) for year in years}
        kpi_data_yearly["Supply Cover Factor (-)"] = {year: self.scf_year.get(year, None) for year in years}
        kpi_data_yearly["Operation Costs (€/a)"] = {year: self.operationCosts.get(year, None) for year in years}
        kpi_data_yearly["CO2 Emissions (t/a)"] = {year: self.co2emissions.get(year, {}).get("total_co2", None) for year in years}
        kpi_data_yearly["CO2 Emissions Grid Electricity (t/a)"] = {year: self.co2emissions.get(year, {}).get("co2_dem_grid", None) for year in years}
        kpi_data_yearly["CO2 Emissions Gas (t/a)"] = {year: self.co2emissions.get(year, {}).get("co2_gas", None) for year in years}
        kpi_data_yearly["CO2 Emissions Biomass (t/a)"] = {year: self.co2emissions.get(year, {}).get("co2_biom", None) for year in years}
        kpi_data_yearly["CO2 Emissions Waste (t/a)"] = {year: self.co2emissions.get(year, {}).get("co2_waste", None) for year in years}
        kpi_data_yearly["CO2 Emissions Hydrogen (t/a)"] = {year: self.co2emissions.get(year, {}).get("co2_hydrogen", None) for year in years}
        kpi_data_yearly["CO2 Emissions Oil (t/a)"] = {year: self.co2emissions.get(year, {}).get("co2_oil", None) for year in years}
        kpi_data_yearly["CO2 Emissions District Heat (t/a)"] = {year: self.co2emissions.get(year, {}).get("co2_district_heat", None) for year in years}
        kpi_data_yearly["CO2 Emissions Waste Heat (t/a)"] = {year: self.co2emissions[year]["co2_waste_heat"] for year in years}
        kpi_data_yearly["Electricity Costs (€/a)"] = {year: self.detailed_costs_year.get(year, {}).get("electricity", None) for year in years}
        kpi_data_yearly["Gas Costs (€/a)"] = {year: self.detailed_costs_year.get(year, {}).get("gas", None) for year in years}
        kpi_data_yearly["Oil Costs (€/a)"] = {year: self.detailed_costs_year.get(year, {}).get("oil", None) for year in years}
        kpi_data_yearly["Waste Costs (€/a)"] = {year: self.detailed_costs_year.get(year, {}).get("waste", None) for year in years}
        kpi_data_yearly["Biomass Costs (€/a)"] = {year: self.detailed_costs_year.get(year, {}).get("biomass", None) for year in years}
        kpi_data_yearly["District Heat Costs (€/a)"] = {year: self.detailed_costs_year.get(year, {}).get("district_heat", None) for year in years}
        kpi_data_yearly["Hydrogen Costs (€/a)"] = {year: self.detailed_costs_year.get(year, {}).get("hydrogen", None) for year in years}
        kpi_data_yearly["Waste Heat Costs (€/a)"] = {year: self.detailed_costs_year.get(year, {}).get("waste_heat", None) for year in years}
        kpi_data_yearly["Revenue from Electricity Feed-in (€/a)"] = {year: self.detailed_costs_year.get(year, {}).get("revenue_feed_in_el", None) for year in years}


        kpi_data_yearly["Autonomy (Time Fraction)"] = {year: self.energy_autonomy_year.get(year, None) for year in years}
        kpi_data_yearly["Gasoline Costs (€/a)"] = {year: self.gasoline_costs.get(year, None) for year in years}
        # kpi_data_yearly["CO2 Emissions Gasoline"] = #* Should this be considered, as emissions from EV are considered through electricity consumption? This makes it look EVs are worse for emissions.

        # Create dictionary for year-independent KPIs (same value for all years)
        kpi_data_static = {}
        # Not changing due to same demand profiles in each year and same device capacities (electricity, heat, cars)
        #! This might change in future versions if demand profiles or device capacities vary per year. Then they should be moved to yearly KPIs.
        kpi_data_static["Sum design Heat Load (kW)"] = self.totalheatload/1000
        kpi_data_static["Sum design Cooling Load (kW)"] = self.totalcoolingload/1000
        kpi_data_static["Heating demand (kWh/a)"] = self.total_heating_demand/1000
        kpi_data_static["Cooling demand (kWh/a)"] = self.total_cooling_demand/1000
        kpi_data_static["Electricity demand (Plug loads) (kWh/a)"] = self.total_electricity_demand/1000
        kpi_data_static["EV demand (kWh/a)"] = self.total_EV_demand/1000
        kpi_data_static["DHW demand (kWh/a)"] = self.total_dhw_demand/1000
        kpi_data_static["Electricity demand (Plug loads) Peak (kW)"] = self.total_electricity_peak/1000
        kpi_data_static["Heat demand Peak (kW)"] = self.total_heat_peak/1000
        kpi_data_static["DHW demand Peak (kW)"] = self.total_dhw_peak/1000
        kpi_data_static["Cooling demand Peak (kW)"] = self.total_cooling_peak/1000
        kpi_data_static["EV demand Peak (kW)"] = self.total_EV_peak/1000
        kpi_data_static["Yearly ICE Fuel Consumption (liters/a)"] = self.total_ICE_fuel_liters # Maybe move to yearly KPIs? Even though currently static.
        kpi_data_static[""] = '' # Empty row

        # Unless the structure of the district changes, these values are static. Changing devices or capacities would require rework of annualized costs.
        kpi_data_static["Annualized Fixed Costs Decentral (€/a)"] = self.annual_fixed_costs_decentral
        kpi_data_static["Annualized Fixed Costs Decentral Unsubsidized (€/a)"] = self.annual_fixed_costs_decentral_unsubsidized
        kpi_data_static["Annualized Fixed Costs Central (€/a)"] = self.annual_fixed_costs_central
        kpi_data_static["Annualized Fixed Costs Central Unsubsidized (€/a)"] = self.annual_fixed_costs_central_unsubsidized
        kpi_data_static["Residential Area (m²)"] = self.totalarea_residential
        kpi_data_static["Non-Residential Area (m²)"] = self.totalarea_non_residential
        kpi_data_static["Number of Flats in district (-)"] = self.totalnumberflats
        kpi_data_static["Number of Occupants in district (-)"] = self.totalnumberocc

        # Add here Total total consumptions and CO2 emissions of each energy carrier.
        # kpi_data_static["Electricity Consumption (kWh)"] = '' # Not currently calculated.
        kpi_data_static["Grid Electricity Consumption (MWh)"] = self.total_W_dem_GCP / 1000
        kpi_data_static["Buildings Electricity Consumption (MWh)"] = self.total_W_dem_buildings / 1000
        kpi_data_static["Grid Electricity Injection (MWh)"] = self.total_W_inj_GCP / 1000
        kpi_data_static["Buildings Electricity Injection (MWh)"] = self.total_W_inj_buildings / 1000
        kpi_data_static["Gas Consumption (MWh)"] = self.total_gas / 1000
        kpi_data_static["Biomass Consumption (MWh)"] = self.total_biomass / 1000
        kpi_data_static["Waste Consumption (MWh)"] = self.total_waste / 1000
        kpi_data_static["Hydrogen Consumption (MWh)"] = self.total_hydrogen / 1000
        kpi_data_static["Oil Consumption (MWh)"] = self.total_oil / 1000
        kpi_data_static["District Heat Consumption (MWh)"] = self.total_districtHeat / 1000
        kpi_data_static["Seasonal Storage Used (MWh)"] = self.total_seasonal_storage_used / 1000
        kpi_data_static["Seasonal Storage Potential (MWh)"] = self.total_seasonal_storage_potential / 1000
        kpi_data_static["Seasonal Storage Utilization (-)"] = self.total_seasonal_storage_utilization
        kpi_data_static["Waste Heat Used (MWh)"] = self.total_waste_heat_used / 1000
        kpi_data_static["Waste Heat Potential (MWh)"] = self.total_waste_heat_potential / 1000
        kpi_data_static["Waste Heat Utilization (-)"] = self.total_waste_heat_utilization
        # kpi_data_static["ICE Fuel Consumption (liters)"] = ''

        kpi_data_static["Total CO2 Emissions (t)"] = self.total_co2_all
        kpi_data_static["Total CO2 Emissions Grid Electricity (t)"] = self.total_co2_dem_grid
        kpi_data_static["Total CO2 Emissions Gas (t)"] = self.total_co2_gas
        kpi_data_static["Total CO2 Emissions Biomass (t)"] = self.total_co2_biom
        kpi_data_static["Total CO2 Emissions Waste (t)"] = self.total_co2_waste
        kpi_data_static["Total CO2 Emissions Hydrogen (t)"] = self.total_co2_hydrogen
        kpi_data_static["Total CO2 Emissions Oil (t)"] = self.total_co2_oil
        kpi_data_static["Total CO2 Emissions District Heat (t)"] = self.total_co2_district_heat
        # kpi_data_static["Total CO2 Emissions ICE Fuel (t)"] = '' #* Should this be considered, as emissions from EV are considered through electricity consumption? This makes it look EVs are worse for emissions.

        # Create device data list: Building ID, Device, Capacity [kW], Annualized Cost Subsidized [€/a], Annualized Cost Unsubsidized [€/a]
        dec_device_data_list = []
        for building_id, devices in self.decentral_individual_devices_annualized_cost.items():
            building = buildings[building_id]
            for device_name, device_info in devices.items():
                # Determine unit based on device type
                if device_name == "TES":
                    unit = "Liter"
                elif device_name in ["BAT", "EV"]:
                    unit = "kWh"
                elif device_name in ["PV", "STC"]:
                    unit = "m²"
                else:
                    unit = "kW"

                dec_device_data_list.append({
                    'Building ID': building["unique_name"],
                    'Device': device_name,
                    'Capacity': round(device_info['cap'], 3) if device_info['cap'] != '' else '-',
                    'Unit': unit,
                    'Annualized Cost (€/a)': round(device_info['subsidized_annual_cost'], 2),
                    'Annualized Cost Unsubsidized (€/a)': round(device_info['unsubsidized_annual_cost'], 2)
                })

        # Central Devices capacities and subsidized and unsubsidized annualized costs
        cent_device_data_list = []
        for device_name, device_info in self.central_individual_devices_annualized_cost.items():
            # Determine unit based on device type
            if device_name == "Heat_Grid":
                unit = "-"
            elif device_name in ["TES", "CTES", "BAT", "GS", "H2S"]:
                unit = "kWh"
            elif device_name in ["PV", "STC"]:
                unit = "kW"
            else:
                unit = "kW"

            cent_device_data_list.append({
                'Device': device_name,
                'Capacity': round(device_info['cap'], 3) if device_info['cap'] != '' else '-',
                'Unit': unit,
                'Annualized Cost Subsidized (€/a)': round(device_info['subsidized_annual_cost'], 2),
                'Annualized Cost Unsubsidized (€/a)': round(device_info['unsubsidized_annual_cost'], 2)
            })

        # Create DataFrame for year-dependent KPIs
        kpi_df_yearly = pd.DataFrame.from_dict(kpi_data_yearly, orient='index')
        kpi_df_yearly.columns = [f"Year {year}" for year in years]
        kpi_df_yearly.index.name = "KPI"
        kpi_df_yearly.reset_index(inplace=True)

        # Create DataFrame for year-independent KPIs
        kpi_df_static = pd.DataFrame(list(kpi_data_static.items()), columns=['KPI', 'Value'])

        # Create DataFrame for device costs
        kpi_df_dec_devices = pd.DataFrame(dec_device_data_list) if dec_device_data_list else pd.DataFrame()

        # Create DataFrame for central device costs
        kpi_df_cent_devices = pd.DataFrame(cent_device_data_list) if cent_device_data_list else pd.DataFrame()

        #LCOH Sheet
        lcoh_rows = []

        #Building-level LCOH
        for year in years:
            for b_id, value in self.lcoh_year_building.get(year, {}).items():
                if abs(value) > 1e-6:  # filter zero values
                    building_name = buildings[b_id]["unique_name"]
                    lcoh_rows.append({
                        "Year": year,
                        "Level": "Building",
                        "Name": building_name,
                        "LCOH (ct/kWh)": round(value, 1)
                    })

        #Energy Hub LCOH
        for year, value in self.lcoh_year_eh.items():
            if abs(value) > 1e-6:  # filter zero values
                lcoh_rows.append({
                    "Year": year,
                    "Level": "Energy Hub",
                    "Name": "EH",
                    "LCOH (ct/kWh)": round(value, 1)
                })

        # Create dataframe
        kpi_df_lcoh = pd.DataFrame(lcoh_rows) if lcoh_rows else pd.DataFrame(
            columns=["Year", "Level", "Name", "LCOH (ct/kWh)"])
        
        if result_path is None:
            src_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            result_path = os.path.join(src_path, "results")
            raise Warning(f"Result path not provided. Saving KPIs to default location: {result_path}")
        

        # Save to Excel with four sheets (or three if no central devices)
        if file_format == "xlsx":
            filename = os.path.join(result_path, f"KPIs_{scenario_name}.{file_format}")

            with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                kpi_df_yearly.to_excel(writer, sheet_name='Yearly KPIs', index=False)
                kpi_df_static.to_excel(writer, sheet_name='Static KPIs', index=False)
                kpi_df_dec_devices.to_excel(writer, sheet_name='Decentral Devices Costs', index=False)
                if not kpi_df_cent_devices.empty:
                    kpi_df_cent_devices.to_excel(writer, sheet_name='Central Devices Costs', index=False)
                kpi_df_lcoh.to_excel(writer, sheet_name='LCOH', index=False)

            print(f"KPIs saved to: {filename}")

        elif file_format == "csv":
            kpi_df_yearly.to_csv(os.path.join(result_path, f"KPIs_{scenario_name}_yearly.csv"), index=False, sep=';', decimal=',')
            kpi_df_static.to_csv(os.path.join(result_path, f"KPIs_{scenario_name}_static.csv"), index=False, sep=';', decimal=',')
            kpi_df_dec_devices.to_csv(os.path.join(result_path, f"KPIs_{scenario_name}_decentral_devices.csv"), index=False, sep=';', decimal=',')
            if not kpi_df_cent_devices.empty:
                kpi_df_cent_devices.to_csv(os.path.join(result_path, f"KPIs_{scenario_name}_central_devices.csv"), index=False, sep=';', decimal=',')
            kpi_df_lcoh.to_csv(os.path.join(result_path, f"KPIs_{scenario_name}_lcoh.csv"), index=False, sep=';', decimal=',')

            print(f"KPIs saved to: {result_path} as CSV files: KPIs_{scenario_name}_*.csv")

        elif file_format == None:
            print("KPIs not saved to file as no file format specified in report configuration.")
        else:
            print(f"Unsupported file format: {file_format}")

        

    def create_certificate(self, data, result_path):
            """
            Generate a certificate as PDF file with a list of KPIs and a list with building information.

            Parameters:
            - filename: The name of the PDF file to create.
            - title: The title of the document.
            - kpis: A list of strings, where each string is a KPI to be written in the document.
            """

            certGenerator = CertificateBuilder(data = data, kpis=self, result_path=result_path)
            certGenerator.generate_certificate()
