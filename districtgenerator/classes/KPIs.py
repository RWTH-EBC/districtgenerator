# -*- coding: utf-8 -*-

import numpy as np
import os
import math
from itertools import zip_longest
from districtgenerator.classes.certificate_generator import CertificateBuilder
import pandas as pd

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
        self.districtHeat_year = None
        self.shared_el_year = None
        self.total_shared_el = None

        self.dcf_year = None
        self.scf_year = None
        self.annual_fixed_costs_decentral = None
        self.annual_fixed_costs_central = None

        self.decentral_device_energy_year = None
        self.central_device_energy_year = None
        self.decentral_device_energy_avg = None
        self.central_device_energy_avg = None

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
        inputData["simulated_years"] = sorted(data.ecoData["interpolation_points"])
        inputData["observation_time"] = data.ecoData["observation_time"]
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

        # Weights of each year:
        year_weights = {}
        for idx, year in enumerate(inputData["simulated_years"]):
            if idx < len(inputData["simulated_years"]) - 1:
                year_weights[year] = inputData["simulated_years"][idx + 1] - year  # time until next support year
            else:
                year_weights[year] = inputData["observation_time"] - year  # time from last support year to end of observation period

        inputData["year_weights"] = year_weights

        self.inputData = inputData

        # prepare data to compute KPIs
        self.prepareData(data)

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
                    idx = data.building_dict[int(bldg_id)]
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
            clipped_demand = np.clip(self.residualLoad[year], a_min=0, a_max=None) # clip to positive values, since demand is positive
            self.peakDemand[year] = round(np.max(clipped_demand), 3)
            # maximal injection [kW]
            clipped_injection = np.clip(self.residualLoad[year], a_min=None, a_max=0) # clip to negative values, since injection is negative
            self.peakInjection[year] = round(abs(np.min(clipped_injection)), 3)

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
        self.shared_el_year = {}

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
            self.shared_el_year[year] = 0

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
                self.shared_el_year[year] += opt_res["total_shared_el"] * weight

                self.el_dem_buildings[year] += opt_res["from_grid_total_el_buildings"] * weight
                self.el_inj_buildings[year] += opt_res["to_grid_total_el_buildings"] * weight
                self.el_dem_eh[year] += opt_res["from_grid_total_el_eh"] * weight
                self.el_inj_eh[year] += opt_res["to_grid_total_el_eh"] * weight

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

        self.dcf_year = {}
        self.scf_year = {}

        sum_ClusterWeights = sum(self.inputData["clusterWeights"][self.inputData["clusters"][c]]
                        for c in range(len(self.inputData["clusters"])))


        for year in self.inputData["simulated_years"]:
            self.supplyCoverFactor[year] = np.zeros(len(self.inputData["clusters"]))
            self.demandCoverFactor[year] = np.zeros(len(self.inputData["clusters"]))


            min = np.zeros([len(self.inputData["clusters"]), len(data.district[0]["user"].elec_cluster[0])], dtype=float)
            nenner_sup = np.zeros([len(self.inputData["clusters"]), len(data.district[0]["user"].elec_cluster[0])], dtype=float)
            nenner_dem = np.zeros([len(self.inputData["clusters"]), len(data.district[0]["user"].elec_cluster[0])], dtype=float)

            total_weighted_shared = 0.0
            total_weighted_demand = 0.0
            total_weighted_supply = 0.0

            for c in range(len(self.inputData["clusters"])):
                cluster_weight = self.inputData["clusterWeights"][self.inputData["clusters"][c]]
                for t in range(len(data.district[0]["user"].elec_cluster[0])):
                    a = 0
                    b = 0
                    # sum of all buildings for each timestep
                    for bldg_id in data.scenario["id"]:
                        idx = data.building_dict[int(bldg_id)]
                        a += self.inputData["resultsOptimization"][year][c][idx]["res_load"][t]
                        b += self.inputData["resultsOptimization"][year][c][idx]["res_inj"][t]

                    # Energy Hub
                    a += self.inputData["resultsOptimization"][year][c]["energy_hub"]["res_load"][t]
                    b += self.inputData["resultsOptimization"][year][c]["energy_hub"]["res_inj"][t]

                    # At the same time step t, either res_load or res_inj should be 0.
                    # However, a and b could both be greater than 0 at the same time step t,
                    # since they represent the sums of all the buildings.
                    # If both a and b are greater than 0, it means electricity is being transported from one building to another.
                    # sum of all timesteps
                    nenner_dem[c, t] = a
                    nenner_sup[c, t] = b
                    min[c, t] = np.min([a, b])

                sum_min = np.sum(min[c, :])
                sum_dem = np.sum(nenner_dem[c, :])
                sum_sup = np.sum(nenner_sup[c, :])


                self.demandCoverFactor[year][c] = np.divide(
                sum_min, sum_dem,
                out=np.ones_like(sum_min), where=(sum_dem != 0)
                )
                self.supplyCoverFactor[year][c] = np.divide(
                sum_min, sum_sup,
                out=np.zeros_like(sum_min), where=(sum_sup != 0)
                )

                # Weighted Energy Exchange within the neighborhood accumulated across all clusters for each year
                weight_norm = cluster_weight / sum_ClusterWeights
                total_weighted_shared += sum_min * weight_norm
                total_weighted_demand += sum_dem * weight_norm
                total_weighted_supply += sum_sup * weight_norm

            
            # Calculate the weighted average of the cover factors across clusters for each year
            self.dcf_year[year] = (
                total_weighted_shared / total_weighted_demand 
                if total_weighted_demand != 0 else 1.0
            )
            
            self.scf_year[year] = (
                total_weighted_shared / total_weighted_supply 
                if total_weighted_supply != 0 else 0.0
            )

        return None

    def calc_annual_cost_total(self, data):

        scenario = data.scenario
        decentral_device_data = data.decentral_device_data
        district = data.district
        physics = data.physics

        capacities = {}
        for n in range(len(district)):
            capacities[n] = {}
            capacities[n]["BOI"] = district[n]["capacities"]["BOI"] / 1000
            capacities[n]["BBOI"] = district[n]["capacities"]["BBOI"] / 1000
            capacities[n]["H2BOI"] = district[n]["capacities"]["H2BOI"] / 1000
            capacities[n]["OBOI"] = district[n]["capacities"]["OBOI"] / 1000
            capacities[n]["HP"] = district[n]["capacities"]["HP"] / 1000
            capacities[n]["EH"] = district[n]["capacities"]["EH"] / 1000
            capacities[n]["EH_DHW"] = district[n]["capacities"]["EH_DHW"] / 1000
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
            capacities[n]["TES_DHW"] = (district[n]["capacities"]["TES_DHW"] / physics["rho_water"] / physics["c_p_water"] /
                                        decentral_device_data["TES_DHW"]["T_diff_max"] * 3600)

        calc_annual_investment = {}
        calc_annual_investment_unsubsidized = {}
        self.decentral_individual_devices_annualized_cost = {} # Dictionary to store annualized cost per device and building
        self.annual_fixed_costs_decentral = 0
        self.annual_fixed_costs_decentral_unsubsidized = 0

        devices = ["BOI", "BBOI", "H2BOI", "OBOI", "HP", "EH", "EH_DHW", "CC", "CHP", "FC", "DH", "PV", "STC", "EV", "BAT", "TES", "TES_DHW"]

        # Iteration over all buildings and then over all devices
        for n in range(len(district)):
            self.decentral_individual_devices_annualized_cost[n] = {}
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
        """
        Calculate the detailed costs for each simulated year.
        """
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
                "revenue_feed_in_el": -(self.el_inj_buildings[year] * ecoData["revenue_feed_in_el"] + self.el_inj_eh[year] * ecoData["revenue_feed_in_el_eh"]),
                "shared_el_costs_buildings": self.shared_el_year[year] *  ecoData["price_energy_sharing_fee"] # Cost of energy sharing within the neighborhood
            }

    def calc_energy_by_device(self, data):
        """
        Calculate total yearly energy generated/consumed by each device
        """
        self.decentral_device_energy_year = {}
        self.central_device_energy_year = {}

        observation_time = self.inputData["observation_time"]
        year_weights = self.inputData["year_weights"]

        # Calculate yearly totals
        for year in self.inputData["simulated_years"]:
            self.decentral_device_energy_year[year] = {} # Now structured as: year -> building_id/energy_hub -> device -> metric -> energy, Maybe later change to building_id/energy_hub -> device -> metric -> year -> energy
            self.central_device_energy_year[year] = {}

            for c in range(len(self.inputData["clusters"])):
                cluster_id = self.inputData["clusters"][c]
                weight = self.inputData["clusterWeights"][cluster_id]
                opt_res = self.inputData["resultsOptimization"][year][c]

                # Energy Hub devices
                eh_res = opt_res["energy_hub"]
                for dev, val in eh_res.items():
                    if dev not in self.central_device_energy_year[year]:
                        self.central_device_energy_year[year][dev] = {} 
                    if isinstance(val, dict):
                        for metric, energy in val.items():
                            if str(metric).startswith("gen_") or str(metric).startswith("cons_") or metric in ["ch", "dch"]: 
                                if metric not in self.central_device_energy_year[year][dev]:
                                    self.central_device_energy_year[year][dev][metric] = 0
                                self.central_device_energy_year[year][dev][metric] += energy * weight

                # Decentral building devices (except EVs):
                for bldg_id in data.scenario["id"]:
                    idx = data.building_dict[int(bldg_id)] #Todo: Change to allow str!
                    if bldg_id not in self.decentral_device_energy_year[year]:
                        self.decentral_device_energy_year[year][bldg_id] = {}
                    bldg_res = opt_res[idx]

                    for dev, val in bldg_res.items():
                        if isinstance(val, dict) and dev not in ["EV"]:
                            if dev not in self.decentral_device_energy_year[year][bldg_id]:
                                self.decentral_device_energy_year[year][bldg_id][dev] = {}
                            for metric, energy in val.items():
                                if str(metric).startswith("gen_") or str(metric).startswith("cons_") or metric in ["ch", "dch"]: 
                                    if metric not in self.decentral_device_energy_year[year][bldg_id][dev]:
                                        self.decentral_device_energy_year[year][bldg_id][dev][metric] = 0
                                    self.decentral_device_energy_year[year][bldg_id][dev][metric] += energy * weight

        # Calculate the avg energy per year for each device
        self.decentral_device_energy_avg = {}
        self.central_device_energy_avg = {}

        all_eh_devices = set()
        # First, collect all device names across the years
        for year in self.inputData["simulated_years"]:
            # Energy Hub devices
            all_eh_devices.update(self.central_device_energy_year[year].keys())
           
        for dev in all_eh_devices:
            self.central_device_energy_avg[dev] = {}

            all_metrics = set() # all metrics e.g. gen_power etc. associated with the device
            for year in self.inputData["simulated_years"]:
                if dev in self.central_device_energy_year[year]:
                    all_metrics.update(self.central_device_energy_year[year][dev].keys())
            
            # For each of the metics calculate the weighted sum
            for metric in all_metrics:
                total = 0
                for year in self.inputData["simulated_years"]:
                    if dev in self.central_device_energy_year[year] and metric in self.central_device_energy_year[year][dev]:
                        total += self.central_device_energy_year[year][dev][metric] * year_weights[year]

                self.central_device_energy_avg[dev][metric] = total/observation_time

        # Decentral devices
        for bldg_id in data.scenario["id"]:
            self.decentral_device_energy_avg[bldg_id] = {}
            all_devices = set()
            
            # Get all devices associated with the building across the years
            for year in self.inputData["simulated_years"]:
                if bldg_id in self.decentral_device_energy_year[year]:
                    all_devices.update(self.decentral_device_energy_year[year][bldg_id].keys())

            # For each device, get all associated metrics across the years and calculate the weighted average
            for dev in all_devices:
                self.decentral_device_energy_avg[bldg_id][dev] = {}
                all_metrics = set()
                for year in self.inputData["simulated_years"]:
                    if dev in self.decentral_device_energy_year[year][bldg_id]:
                        all_metrics.update(self.decentral_device_energy_year[year][bldg_id][dev].keys())

                # For each of the metics calculate the weighted sum
                for metric in all_metrics:
                    total = 0
                    for year in self.inputData["simulated_years"]:
                        if dev in self.decentral_device_energy_year[year][bldg_id] and metric in self.decentral_device_energy_year[year][bldg_id][dev]:
                            total += self.decentral_device_energy_year[year][bldg_id][dev][metric] * year_weights[year]

                    self.decentral_device_energy_avg[bldg_id][dev][metric] = total / observation_time

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

            # total CO2 emissions [kg/a]
            total_co2 = co2_dem_grid + co2_gas + co2_biom + co2_waste + co2_hydrogen + co2_oil + co2_district_heat

            # CO2 emissions for each simulated year
            self.co2emissions[year] = { #! Save individual contributions for possible later use. Important: Do not sum all values. Comined already included.
                "total_co2": total_co2,
                "co2_dem_grid": co2_dem_grid,
                "co2_gas": co2_gas,
                "co2_biom": co2_biom,
                "co2_waste": co2_waste,
                "co2_hydrogen": co2_hydrogen,
                "co2_oil": co2_oil,
                "co2_district_heat": co2_district_heat
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
        Calculate total areas and demands of the district.

        Parameters
        ----------
        data : Datahandler object
            Datahandler object which contains all relevant information to compute the key performance indicators (KPIs).

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
                total_number_flats += building["user"].nb_flats
                for flat in building["user"].nb_occ:
                    total_number_occ += flat
            elif "+" in building["buildingFeatures"]["building"]: #TODO: This requires a working mixed building implementation
                total_area_mixed += building["buildingFeatures"]["area"]
                total_number_flats += building["user"].nb_res_flats
                for flat in building["user"].nb_res_occ:
                    total_number_occ += flat
            else:
                total_area_non_residential += building["buildingFeatures"]["area"]
            total_ICE_fuel_liters += np.sum(building["user"].ice_carprofile)  # liters per timestep summed over year

            # sum all building design heat and cooling loads
            total_heat_load += building["envelope"].heatload + building["envelope"].dhwpower
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

        Uses year weights to account for the interval that each simulated year represents.


        Retuns
        -------
        None.
        """
        # Calculate year weights (duration each simulated year represents)
        sorted_years = sorted(self.inputData["simulated_years"])
        observation_time = data.ecoData["observation_time"]
        year_weights = self.inputData["year_weights"]

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
        self.total_shared_el = sum(self.shared_el_year[year] * year_weights[year] for year in sorted_years) # total shared electricity within the neighborhood

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
        self.calc_energy_by_device(data)
        self.calculateCO2emissions(data)
        self.calculateAutonomy()
        self.calc_annual_cost_total(data)
        self.calc_total_areas_and_demands(data)
        self.calculateGasolineCosts(data)
        self.calc_total_consumption_and_emissions(data)
        self.calculateDetailedCostsPerYear(data)
        self.saveKPIs(scenario_name=data.scenario_name, result_path=data.resultPath, buildings=data.district, file_format=data.report_config["kpi_save_type"])

    def saveKPIs(self, scenario_name, result_path, buildings, file_format):
        """
        Save all calculated KPIs in a file. Ensure that calculateAllKPIs() has been called before. Saves as the specified file format (csv/excel)

        Parameters
        - scenario_name: The name of the scenario for which the KPIs are saved. Used in the filename.
        - result_path: The path where the KPI file should be saved.
        - buildings: The list of building data, used for saving building-specific KPIs.
        - file_format: The file format to save the KPIs in. Supported formats are "csv" and "xlsx".
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
        kpi_data_yearly["Shared Electricity within District (kWh/a)"] = {year: self.shared_el_year.get(year, None) for year in years}
        kpi_data_yearly["Gas Consumption (kWh/a)"] = {year: self.gas_year.get(year, None) for year in years}
        kpi_data_yearly["Biomass Consumption (kWh/a)"] = {year: self.biomass_year.get(year, None) for year in years}
        kpi_data_yearly["Waste Consumption (kWh/a)"] = {year: self.waste_year.get(year, None) for year in years}
        kpi_data_yearly["Hydrogen Consumption (kWh/a)"] = {year: self.hydrogen_year.get(year, None) for year in years}
        kpi_data_yearly["Oil Consumption (kWh/a)"] = {year: self.oil_year.get(year, None) for year in years}
        kpi_data_yearly["District Heat Consumption (kWh/a)"] = {year: self.districtHeat_year.get(year, None) for year in years}
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
        kpi_data_yearly["Electricity Costs (€/a)"] = {year: self.detailed_costs_year.get(year, {}).get("electricity", None) for year in years}
        kpi_data_yearly["Gas Costs (€/a)"] = {year: self.detailed_costs_year.get(year, {}).get("gas", None) for year in years}
        kpi_data_yearly["Oil Costs (€/a)"] = {year: self.detailed_costs_year.get(year, {}).get("oil", None) for year in years}
        kpi_data_yearly["Waste Costs (€/a)"] = {year: self.detailed_costs_year.get(year, {}).get("waste", None) for year in years}
        kpi_data_yearly["Biomass Costs (€/a)"] = {year: self.detailed_costs_year.get(year, {}).get("biomass", None) for year in years}
        kpi_data_yearly["District Heat Costs (€/a)"] = {year: self.detailed_costs_year.get(year, {}).get("district_heat", None) for year in years}
        kpi_data_yearly["Hydrogen Costs (€/a)"] = {year: self.detailed_costs_year.get(year, {}).get("hydrogen", None) for year in years}
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
        kpi_data_static["Average CO2 Emissions (t/a)"] = self.avg_co2_emissions
        
        kpi_data_static[""] = '' # Empty row

        # Unless the structure of the district changes, these values are static. Changing devices or capacities would require rework of annualized costs.
        kpi_data_static["Annualized Fixed Costs Decentral (€/a)"] = self.annual_fixed_costs_decentral
        kpi_data_static["Annualized Fixed Costs Decentral Unsubsidized (€/a)"] = self.annual_fixed_costs_decentral_unsubsidized
        kpi_data_static["Annualized Fixed Costs Central (€/a)"] = self.annual_fixed_costs_central
        kpi_data_static["Annualized Fixed Costs Central Unsubsidized (€/a)"] = self.annual_fixed_costs_central_unsubsidized
        kpi_data_static["Average Operation Costs (€/a)"] = self.avg_operationCosts
        kpi_data_static["Residential Area (m²)"] = self.totalarea_residential
        kpi_data_static["Mixed Area (m²)"] = self.total_area_mixed
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
                if device_name == "T_reduction_measures":
                    continue # TODO: Skip this for now and decide later how to handle it.
                
                # Determine unit based on device type
                if device_name in ["TES", "TES_DHW"]:
                    unit = "Liter"
                elif device_name in ["BAT", "EV"]:
                    unit = "kWh"
                elif device_name in ["PV", "STC"]:
                    unit = "m²"
                else:
                    unit = "kW"

                row_data = {
                    'Building ID': building["unique_name"],
                    'Device': device_name,
                    'Capacity': round(device_info['cap'], 3) if device_info['cap'] != '' else '-',
                    'Unit': unit,
                    'Annualized Cost (€/a)': round(device_info['subsidized_annual_cost'], 2),
                    'Annualized Cost Unsubsidized (€/a)': round(device_info['unsubsidized_annual_cost'], 2)
                }
                
                avg_metrics = self.decentral_device_energy_avg.get(building_id, {}).get(device_name, {})
                for metric_name, val in avg_metrics.items():
                    row_data[f"Avg. {metric_name} (kWh/a)"] = round(val, 2)

                for year in years:
                    yearly_metrics = self.decentral_device_energy_year.get(year, {}).get(building_id, {}).get(device_name, {})
                    for metric_name, val in yearly_metrics.items():
                        row_data[f"Year {year} {metric_name} (kWh/a)"] = round(val, 2)

                dec_device_data_list.append(row_data)

        # Central Devices capacities and subsidized and unsubsidized annualized costs
        cent_device_data_list = []
        for device_name, device_info in self.central_individual_devices_annualized_cost.items():
            # Determine unit based on device type
            if device_name == "Heat_Grid":
                unit = "-"
            elif device_name in ["TES", "CTES", "BAT", "GS", "H2S"]:
                unit = "kWh"
            elif device_name in ["PV", "STC", "WT"]:
                unit = "kWp"
            else:
                unit = "kW"

            row_data = {
                'Device': device_name,
                'Capacity': round(device_info['cap'], 3) if device_info['cap'] != '' else '-',
                'Unit': unit,
                'Annualized Cost Subsidized (€/a)': round(device_info['subsidized_annual_cost'], 2),
                'Annualized Cost Unsubsidized (€/a)': round(device_info['unsubsidized_annual_cost'], 2)
            }

            avg_metrics = self.central_device_energy_avg.get(device_name, {})
            for metric_name, val in avg_metrics.items():
                row_data[f"Avg. {metric_name} (kWh/a)"] = round(val, 2)

            for year in years:
                yearly_metrics = self.central_device_energy_year.get(year, {}).get(device_name, {})
                for metric_name, val in yearly_metrics.items():
                    row_data[f"Year {year} {metric_name} (kWh/a)"] = round(val, 2)
            cent_device_data_list.append(row_data)

        # Create DataFrame for year-dependent KPIs
        kpi_df_yearly = pd.DataFrame.from_dict(kpi_data_yearly, orient='index')
        kpi_df_yearly.columns = [f"Year {year}" for year in years]
        kpi_df_yearly.index.name = "KPI"
        kpi_df_yearly.reset_index(inplace=True)

        # Create DataFrame for year-independent KPIs
        kpi_df_static = pd.DataFrame(list(kpi_data_static.items()), columns=['KPI', 'Value'])



        def sort_device_columns(df, static_cols, years):
            """
            Sort DataFrame columns: static columns first, then averages, then yearly values.
            """
            if df.empty:
                return df

            dynamic_cols = [col for col in df.columns if col not in static_cols]
            avg_cols = [col for col in dynamic_cols if col.startswith("Avg.")]
            avg_cols.sort(key=lambda x: (1 if " ch " in x or " dch " in x else 0, x)) # ch and dch columns after other columns for the same year

            year_cols = []
            for year in years:
                cols_for_year = [col for col in dynamic_cols if col.startswith(f"Year {year} ")]
                cols_for_year.sort(key=lambda x: (1 if " ch " in x or " dch " in x else 0, x)) # ch and dch columns after other columns for the same year
                
                year_cols.extend(cols_for_year)
            return df[static_cols + avg_cols + year_cols]

        # Create DataFrame for decentral devices. Ensure proper ordering of columns.
        kpi_df_dec_devices = pd.DataFrame(dec_device_data_list) if dec_device_data_list else pd.DataFrame()
        static_cols_dec = ['Building ID', 'Device', 'Capacity', 'Unit', 'Annualized Cost (€/a)', 'Annualized Cost Unsubsidized (€/a)']
        kpi_df_dec_devices = sort_device_columns(df=kpi_df_dec_devices, static_cols = static_cols_dec, years=years)

        # Create DataFrame for central devices. Ensure proper ordering of columns.
        kpi_df_cent_devices = pd.DataFrame(cent_device_data_list) if cent_device_data_list else pd.DataFrame()
        static_cols_cent = ['Device', 'Capacity', 'Unit', 'Annualized Cost Subsidized (€/a)', 'Annualized Cost Unsubsidized (€/a)']
        kpi_df_cent_devices = sort_device_columns(df=kpi_df_cent_devices, static_cols = static_cols_cent, years=years)

        
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
                kpi_df_dec_devices.to_excel(writer, sheet_name='Decentral Devices', index=False)
                if not kpi_df_cent_devices.empty:
                    kpi_df_cent_devices.to_excel(writer, sheet_name='Central Devices', index=False)

            print(f"KPIs saved to: {filename}")

        elif file_format == "csv":
            kpi_df_yearly.to_csv(os.path.join(result_path, f"KPIs_{scenario_name}_yearly.csv"), index=False, sep=';', decimal=',')
            kpi_df_static.to_csv(os.path.join(result_path, f"KPIs_{scenario_name}_static.csv"), index=False, sep=';', decimal=',')
            kpi_df_dec_devices.to_csv(os.path.join(result_path, f"KPIs_{scenario_name}_decentral_devices.csv"), index=False, sep=';', decimal=',')
            if not kpi_df_cent_devices.empty:
                kpi_df_cent_devices.to_csv(os.path.join(result_path, f"KPIs_{scenario_name}_central_devices.csv"), index=False, sep=';', decimal=',')

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