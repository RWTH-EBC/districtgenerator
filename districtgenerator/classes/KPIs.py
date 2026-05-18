# -*- coding: utf-8 -*-

import numpy as np
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
        inputData["nbIntervals"] = 0
        for c in inputData["clusters"]:
            inputData["nbIntervals"] += inputData["clusterWeights"][c]

        # prepare the results of the optimizations for each cluster
        inputData["resultsOptimization"] = data.resultsOptimization
        inputData["district"] = data.district

        self.inputData = inputData

        # AIX HEAT Modification
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

        # initialize lists
        electricityDemand_cluster = []
        electricityGeneration_cluster = []
        electricityGenerationRenewable_cluster = []
        lossesBattery_cumulated_cluster = []
        # Load data of decentral devices (to calculate battery losses)
        srcPath = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        self.sum_res_load = {}
        self.sum_res_inj = {}
        self.sum_res_gas = {}

        centralEnergyUnit_load = {}
        centralEnergyUnit_inj = {}

        for year in self.inputData["simulated_years"]:
            # summed el. load of all buildings , [number of time periods, time steps within periods]
            self.sum_res_load[year] = np.zeros([len(data.clusters), len(data.district[0]["user"].elec_cluster[0])])
            # summed el. injection of all buildings
            self.sum_res_inj[year] = np.zeros([len(data.clusters), len(data.district[0]["user"].elec_cluster[0])])
            self.sum_res_gas[year] = np.zeros([len(data.clusters), len(data.district[0]["user"].elec_cluster[0])])
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
                    self.sum_res_gas[year][c, :]  += np.array(self.inputData["resultsOptimization"][year][c][idx]["res_gas"])

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

        W_inj_GCP = {}
        W_dem_GCP = {}
        gas = {}
        biomass = {}
        waste = {}
        hydrogen = {}
        oil = {}
        districtHeat = {}

        for year in self.inputData["simulated_years"]:
            # Electricity [kWh] feed into the superordinated grid
            W_inj_GCP[year] = np.zeros(len(data.clusters))
            # Electricity [kWh] covered by the superordinated grid
            W_dem_GCP[year] = np.zeros(len(data.clusters))

            # Fuel consumption [kWh]
            gas[year] = np.zeros(len(data.clusters))
            biomass[year] = np.zeros(len(data.clusters))
            waste[year] = np.zeros(len(data.clusters))
            hydrogen[year] = np.zeros(len(data.clusters))
            oil[year] = np.zeros(len(data.clusters))

            # District heat consumption [kWh]
            districtHeat[year] = np.zeros(len(data.clusters))

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
            # Variables for the yearly consumption calculation
            self.W_inj_GCP_year[year] = 0
            self.W_dem_GCP_year[year] = 0
            self.gas_year[year] = 0
            self.biomass_year[year] = 0
            self.waste_year[year] = 0
            self.hydrogen_year[year] = 0
            self.oil_year[year] = 0
            self.districtHeat_year[year] = 0

            # loop over cluster
            for c in range(len(self.inputData["clusters"])):
                W_dem_GCP[year][c] = sum(self.inputData["resultsOptimization"][year][c]["P_dem_gcp"]) \
                                        * data.time["timeResolution"] / 3600 / 1000 # from Ws to kWh
                W_inj_GCP[year][c] = sum(self.inputData["resultsOptimization"][year][c]["P_inj_gcp"]) \
                                        * data.time["timeResolution"] / 3600 / 1000
                gas[year][c] = sum(self.inputData["resultsOptimization"][year][c]["P_gas_total"]) * data.time["timeResolution"] / 3600 / 1000
                biomass[year][c] = sum(self.inputData["resultsOptimization"][year][c]["P_biomass_total"]) * data.time["timeResolution"] / 3600 / 1000
                waste[year][c] = sum(self.inputData["resultsOptimization"][year][c]["P_waste_total"]) * data.time["timeResolution"] / 3600 / 1000
                hydrogen[year][c] = sum(self.inputData["resultsOptimization"][year][c]["P_hydrogen_total"]) * data.time["timeResolution"] / 3600 / 1000
                oil[year][c] = sum(self.inputData["resultsOptimization"][year][c]["P_oil_total"]) * data.time["timeResolution"] / 3600 / 1000
                districtHeat[year][c] = sum(self.inputData["resultsOptimization"][year][c]["P_district_heat_total"]) * data.time["timeResolution"] / 3600 / 1000


                self.W_dem_GCP_year[year] += W_dem_GCP[year][c] * self.inputData["clusterWeights"][self.inputData["clusters"][c]]
                self.W_inj_GCP_year[year] += W_inj_GCP[year][c] * self.inputData["clusterWeights"][self.inputData["clusters"][c]]
                self.gas_year[year] += gas[year][c] * self.inputData["clusterWeights"][self.inputData["clusters"][c]]
                self.biomass_year[year] += biomass[year][c] * self.inputData["clusterWeights"][self.inputData["clusters"][c]]
                self.waste_year[year] += waste[year][c] * self.inputData["clusterWeights"][self.inputData["clusters"][c]]
                self.hydrogen_year[year] += hydrogen[year][c] * self.inputData["clusterWeights"][self.inputData["clusters"][c]]
                self.oil_year[year] += oil[year][c] * self.inputData["clusterWeights"][self.inputData["clusters"][c]]
                self.districtHeat_year[year] += districtHeat[year][c] * self.inputData["clusterWeights"][self.inputData["clusters"][c]]

    def calculateEnergyExchangeWithinDistrict(self, data):

        self.W_inj_buildings_year = {}
        self.W_dem_buildings_year = {}

        # loop over cluster
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
        nenner_sup = np.zeros([len(self.inputData["clusters"]), len(data.district[0]["user"].elec_cluster[0])],
                              dtype=float)
        nenner_dem = np.zeros([len(self.inputData["clusters"]), len(data.district[0]["user"].elec_cluster[0])],
                              dtype=float)

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
        counts["PV"] = scenario.apply(lambda row: 1 if (row.get('f_PV1',0) > 0 or row.get('f_PV2',0) > 0 or row.get("f_PV", 0)) else 0, axis=1).sum()
        counts["STC"] = scenario['f_STC'].apply(lambda x: 1 if x > 0 else 0).sum()
        counts["EV"] = sum((lambda ev: len(ev) if any(x > 0 for x in ev) else 0)(d["user"].ev_capacity)for d in district)
        counts["BAT"] = scenario['f_BAT'].apply(lambda x: 1 if x > 0 else 0).sum()

        ## AIX HEAT
        # calc_annual_investment = {dev: 0 for dev in ["BOI", "HP", "CHP", "PV", "STC", "EV", "BAT", "TES"]}
        # to include all devices with inv_var in decentral_device_data
        investable_devices_list = [
            dev
            for dev, properties in decentral_device_data.items()
            if 'inv_var' in properties
        ]
        calc_annual_investment = {dev: 0 for dev in investable_devices_list}

        # Refactor
        for n, building_id in enumerate(data.scenario["id"]):
            ## Initialize cost dictionary for this building
            self.kpis_per_building[building_id]['costs'] = {}
            building_annual_cost = 0

            capacities = {}
            # ADD new technologies here!!
            capacities["BOI"] = district[n]["capacities"]["BOI"] / 1000
            capacities["BBOI"] = district[n]["capacities"]["BBOI"] / 1000
            capacities["HP"] = district[n]["capacities"]["HP"] / 1000
            capacities["CHP"] = district[n]["capacities"]["CHP"] / 1000
            capacities["PV"] = district[n]["capacities"]["PV"]["area"]
            capacities["STC"] = district[n]["capacities"]["STC"]["area"]
            capacities["EV"] = district[n]["capacities"]["EV"] / 1000
            capacities["BAT"] = district[n]["capacities"]["BAT"] / 1000
            capacities["TES"] = (district[n]["capacities"]["TES"] / physics["rho_water"] / physics["c_p_water"] /
                                 decentral_device_data["TES"]["T_diff_max"] * 3600)
            capacities["EH"] = district[n]["capacities"]["EH"] / 1000

            for dev in investable_devices_list:
                try:
                    # Check if the device exists for this building based on its capacity
                    if capacities.get(dev) and capacities[dev] > 0:
                        annual_cost_device = self.calc_annual_cost_device(
                            decentral_device_data[dev],
                            data.ecoData,
                            capacities[dev])

                        # Add to building and district totals
                        building_annual_cost += annual_cost_device
                        calc_annual_investment[dev] += annual_cost_device

                        ## Store per-device cost for the building
                        self.kpis_per_building[building_id]['costs'][f'annual_cost_{dev}_eur'] = annual_cost_device
                except Exception as e:
                    print("Error calculating annual cost for device", dev, "in building", building_id, ":", e)
            ## Store total annualized fixed cost for the building
            self.kpis_per_building[building_id]['costs']['annual_fixed_costs_eur'] = building_annual_cost
        ## END AIX HEAT

        capacities = {}
        for n in range(len(district)):
            capacities[n] = {}
            capacities[n]["BOI"] = district[n]["capacities"]["BOI"] / 1000
            capacities[n]["BBOI"] = district[n]["capacities"]["BBOI"] / 1000
            capacities[n]["H2BOI"] = district[n]["capacities"]["H2BOI"] / 1000
            capacities[n]["OBOI"] = district[n]["capacities"]["OBOI"] / 1000
            capacities[n]["HP"] = district[n]["capacities"]["HP"] / 1000
            capacities[n]["EH"] = district[n]["capacities"]["EH"] / 1000
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

        devices = ["BOI", "BBOI", "H2BOI", "OBOI", "HP", "EH", "CHP", "FC", "DH", "PV", "STC", "EV", "BAT", "TES"]
        #todo: test
        # print("Installable Devices: \n")
        # print(investable_devices_list)
        # print("ALl devices: \n")
        # print(devices)

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

        # for building in data.district:
        for i, building in enumerate(data.district):
            building_id = data.scenario["id"][i]
            b_kpis = self.kpis_per_building[building_id]

            b_kpis['heating_system'] = building["buildingFeatures"].get("heater", "N/A")
            active_technologies = {} #[]
            building_technologies = building.get('capacities', {})

            for tech_name, tech_value in building_technologies.items():
                if isinstance(tech_value, (int, float)):
                    if tech_value > 0:
                        active_technologies[tech_name] = {"capacity": tech_value}
                elif isinstance(tech_value, dict) and not tech_name == "inv":  # avoid 'inv' sub-dictionary
                    tech_details = {}
                    has_positive_value = False
                    for key, value in tech_value.items():
                        # P_ref in W
                        if value > 0:
                            has_positive_value = True
                            tech_details[key] = value
                    if has_positive_value:
                        active_technologies[tech_name] = tech_details
            b_kpis['active_technologies'] = active_technologies

            if building["buildingFeatures"]["building"] in {"SFH", "MFH", "TH", "AB"}:
                # sum all building areas
                total_area_residential += building["buildingFeatures"]["area"]
                total_number_flats += building["user"].nb_flats
                for flat in building["user"].nb_occ:
                    total_number_occ += flat
                b_kpis['area_m2'] = building["buildingFeatures"]["area"]
                b_kpis['building_type'] = "residential"
            else:
                total_area_non_residential += building["buildingFeatures"]["area"]
                total_ICE_fuel_liters += np.sum(building["user"].ice_carprofile)  # liters per timestep summed over year
                b_kpis['area_m2'] = building["buildingFeatures"]["area"]
                b_kpis['building_type'] = "non_residential"

            # sum all building design heat and cooling loads
            ## TODO DISKUSSION: MÜsste die HEat Load nicht über die Jahre abnehmen wegen maßnahemn zb?
            heat_load = building["envelope"].heatload + building["envelope"].dhwpower
            cooling_load = max(building["user"].cooling)
            total_heat_load += heat_load
            total_cooling_load += cooling_load
            b_kpis['total_heat_load_kW'] = heat_load / 1000
            b_kpis['cooling_load_kW'] = cooling_load / 1000
            b_kpis['heat_load_kW'] = building["envelope"].heatload / 1000
            b_kpis["dhw_power_kW"] = building["envelope"].dhwpower / 1000

            # sum all building demands
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
        self.total_electricity_peak = max(sum_electricity_profile) if sum_electricity_profile else 0
        self.total_heat_peak = max(sum_heat_profile) if sum_heat_profile else 0
        self.total_dhw_peak = max(sum_dhw_profile) if sum_dhw_profile else 0
        self.total_cooling_peak = max(sum_cool_profile) if sum_cool_profile else 0
        self.total_EV_peak = max(sum_EV_profile) if sum_EV_profile else 0
        self.total_ICE_fuel_liters = float(total_ICE_fuel_liters)

    def calculate_per_building_kpis(self, data):
        """
        Calculates technical KPIs for each building individually and stores them per year.
        This includes energy exchange with the local grid, self-consumption, and autonomy.
        """
        time_res_h = data.time["timeResolution"] / 3600

        price_gas_per_kwh = data.ecoData["price_supply_gas"]  # Expected unit: €/kWh
        co2_factor_gas_per_kwh = data.ecoData["co2_gas"]  # kgCO2/kWh
        price_el_per_kwh = data.ecoData["price_supply_el"]  # Expected unit: €/kWh
        revenue_feed_el_per_kwh = data.ecoData["revenue_feed_in_el"]  # Expected unit: €/kWh
        co2_factor_el_per_kwh = data.ecoData["co2_el_grid"]  # kgCO2/kWh
        price_biom_per_kwh = data.ecoData.get("price_biomass", 0)  # €/k
        co2_factor_biom_per_kwh = data.ecoData.get("co2_biom", 0)  # kgCO2/kWh
        price_oil_per_kwh = data.ecoData.get("price_oil", 0)
        co2_factor_oil_per_kwh = data.ecoData.get("co2_oil", 0)
        price_hydrogen_per_kwh = data.ecoData.get("price_hydrogen", 0)
        co2_factor_hydrogen_per_kwh = data.ecoData.get("co2_hydrogen", 0)

        for i, building_id in enumerate(data.scenario["id"]):

            # Initialize building in dictionary if not already present
            if building_id not in self.kpis_per_building:
                self.kpis_per_building[building_id] = {}
            b_kpis = self.kpis_per_building[building_id]

            for year_idx, year in enumerate(self.inputData["simulated_years"]):

                if year not in b_kpis:
                    b_kpis[year] = {}
                b_kpis[year]['tech'] = {}
                b_kpis[year]['eco'] = {}

                # Dynamische Werte für das aktuelle Jahr ermitteln
                curr_price_gas = price_gas_per_kwh[year_idx] \
                    if isinstance(price_gas_per_kwh, list) else price_gas_per_kwh
                curr_price_el = price_el_per_kwh[year_idx] \
                    if isinstance(price_el_per_kwh, list) else price_el_per_kwh
                curr_price_biom = price_biom_per_kwh[year_idx] \
                    if isinstance(price_biom_per_kwh, list) else price_biom_per_kwh
                curr_rev_feed_el = revenue_feed_el_per_kwh[year_idx] \
                    if isinstance(revenue_feed_el_per_kwh, list) else revenue_feed_el_per_kwh
                curr_co2_gas = co2_factor_gas_per_kwh[year_idx] \
                    if isinstance(co2_factor_gas_per_kwh, list) else co2_factor_gas_per_kwh
                curr_co2_el = co2_factor_el_per_kwh[year_idx] \
                    if isinstance(co2_factor_el_per_kwh, list) else co2_factor_el_per_kwh
                curr_co2_biom = co2_factor_biom_per_kwh[year_idx] \
                    if isinstance(co2_factor_biom_per_kwh, list) else co2_factor_biom_per_kwh
                curr_price_oil = price_oil_per_kwh[year_idx] \
                    if isinstance(price_oil_per_kwh, list) else price_oil_per_kwh
                curr_co2_oil = co2_factor_oil_per_kwh[year_idx] \
                    if isinstance(co2_factor_oil_per_kwh, list) else co2_factor_oil_per_kwh
                curr_price_hydrogen = price_hydrogen_per_kwh[year_idx] \
                    if isinstance(price_hydrogen_per_kwh, list) else price_hydrogen_per_kwh
                curr_co2_hydrogen = co2_factor_hydrogen_per_kwh[year_idx] \
                    if isinstance(co2_factor_hydrogen_per_kwh, list) else co2_factor_hydrogen_per_kwh

                annual_demand_from_grid = 0
                annual_injection_to_grid = 0
                annual_gross_generation = 0
                annual_gross_demand = 0
                timesteps_autonomous = 0
                annual_gas_consumption_kwh = 0
                annual_biomass_consumption_kwh = 0
                annual_oil_consumption_kwh = 0
                annual_hydrogen_consumption_kwh = 0

                for c_idx, c_name in enumerate(self.inputData["clusters"]):
                    cluster_weight = self.inputData["clusterWeights"][c_name]

                    res = self.inputData["resultsOptimization"][year][c_idx][building_id]

                    # Energy exchange with the local grid
                    res_load_kwh = np.sum(res["res_load"]) / 1000 * time_res_h
                    res_inj_kwh = np.sum(res["res_inj"]) / 1000 * time_res_h
                    res_gas_kwh = np.sum(res.get("res_gas", 0)) / 1000 * time_res_h
                    res_biom_kwh = np.sum(res.get("res_biomass", 0)) / 1000 * time_res_h
                    res_oil_kwh = np.sum(res.get("res_oil", 0)) / 1000 * time_res_h
                    res_hydrogen_kwh = np.sum(res.get("res_hydrogen", 0)) / 1000 * time_res_h

                    annual_demand_from_grid += res_load_kwh * cluster_weight
                    annual_injection_to_grid += res_inj_kwh * cluster_weight
                    annual_gas_consumption_kwh += res_gas_kwh * cluster_weight
                    annual_biomass_consumption_kwh += res_biom_kwh * cluster_weight
                    annual_oil_consumption_kwh += res_oil_kwh * cluster_weight
                    annual_hydrogen_consumption_kwh += res_hydrogen_kwh * cluster_weight

                    # --- 1. Calculate Total On-site Electrical Generation for each timestep ---
                    gen_pv = np.array(res.get("PV", {}).get("P_el", 0))
                    gen_chp = np.array(res.get("CHP", {}).get("P_el", 0))
                    gen_fc = np.array(res.get("FC", {}).get("P_el", 0))

                    # For the battery, discharge is generation (positive P_el)
                    bat_power = np.array(res.get("BAT", {}).get("P_el", 0))
                    gen_bat_discharge = np.maximum(0, bat_power)

                    gross_gen_ts = gen_pv + gen_chp + gen_fc + gen_bat_discharge

                    # --- 2. Calculate Total On-site Electrical Demand for each timestep ---
                    demand_base = np.array(res.get("Elec_dem", {}).get("P_el", 0))
                    demand_hp = np.array(res.get("HP", {}).get("P_el", 0))
                    demand_eh = np.array(res.get("EH", {}).get("P_el", 0))
                    demand_ev = np.array(res.get("EV", {}).get("P_el", 0))
                    demand_cc = np.array(res.get("CC", {}).get("P_el", 0)) # wenn der Strom braucht

                    # For the battery, charge is a demand (negative P_el, so we take its absolute value)
                    demand_bat_charge = np.maximum(0, -bat_power)

                    gross_demand_ts = (demand_base + demand_hp + demand_eh + demand_cc + demand_ev + demand_bat_charge)

                    # --- 3. Sum up for the annual values ---
                    # Convert from W to kWh for the cluster period
                    annual_gross_generation += (np.sum(gross_gen_ts) / 1000 * time_res_h) * cluster_weight
                    annual_gross_demand += (np.sum(gross_demand_ts) / 1000 * time_res_h) * cluster_weight

                    # Autonomy: timesteps where the building does not draw from the grid
                    timesteps_autonomous += np.sum(np.array(res["res_load"]) == 0) * cluster_weight

                # Store annual grid exchange values
                b_kpis[year]['tech']['grid_demand_kWh'] = annual_demand_from_grid
                b_kpis[year]['tech']['grid_injection_kWh'] = annual_injection_to_grid

                # Store annual gross generation and demand
                b_kpis[year]['tech']['gross_generation_kWh'] = annual_gross_generation
                b_kpis[year]['tech']['gross_demand_kWh'] = annual_gross_demand

                # Store the annual gas / oil / hydrogen consumption
                b_kpis[year]['tech']['gas_consumption_kwh'] = annual_gas_consumption_kwh
                b_kpis[year]['tech']['biomass_consumption_kwh'] = annual_biomass_consumption_kwh
                b_kpis[year]['tech']['oil_consumption_kwh'] = annual_oil_consumption_kwh
                b_kpis[year]['tech']['hydrogen_consumption_kwh'] = annual_hydrogen_consumption_kwh

                # --- Calculate and Store Economic KPIs ---
                annual_gas_cost = annual_gas_consumption_kwh * curr_price_gas
                b_kpis[year]['eco']['gas_cost'] = annual_gas_cost

                annual_el_cost = annual_demand_from_grid * curr_price_el
                b_kpis[year]['eco']['el_cost'] = annual_el_cost

                annual_biom_cost = annual_biomass_consumption_kwh * curr_price_biom
                b_kpis[year]['eco']['biomass_cost'] = annual_biom_cost

                annual_el_revenue = annual_injection_to_grid * curr_rev_feed_el
                b_kpis[year]['eco']['el_revenue'] = annual_el_revenue

                annual_oil_cost = annual_oil_consumption_kwh * curr_price_oil
                b_kpis[year]['eco']['oil_cost'] = annual_oil_cost

                annual_hydrogen_cost = annual_hydrogen_consumption_kwh * curr_price_hydrogen
                b_kpis[year]['eco']['hydrogen_cost'] = annual_hydrogen_cost

                total_costs = (annual_gas_cost + annual_el_cost - annual_el_revenue +
                               annual_biom_cost + annual_oil_cost + annual_hydrogen_cost)
                b_kpis[year]['eco']['total_energy_cost_eur'] = total_costs

                # Calculate total annual CO2 emissions from electricity
                annual_el_co2_kg = annual_demand_from_grid * curr_co2_el
                b_kpis[year]['eco']['el_co2_emissions_kg'] = annual_el_co2_kg

                # Calculate total annual CO2 emissions from gas
                annual_gas_co2_kg = annual_gas_consumption_kwh * curr_co2_gas
                b_kpis[year]['eco']['gas_co2_emissions_kg'] = annual_gas_co2_kg

                annual_biom_co2_kg = annual_biomass_consumption_kwh * curr_co2_biom
                b_kpis[year]['eco']['biomass_co2_emissions_kg'] = annual_biom_co2_kg

                annual_oil_co2_kg = annual_oil_consumption_kwh * curr_co2_oil
                b_kpis[year]['eco']['oil_co2_emissions_kg'] = annual_oil_co2_kg

                annual_hydrogen_co2_kg = annual_hydrogen_consumption_kwh * curr_co2_hydrogen
                b_kpis[year]['eco']['hydrogen_co2_emissions_kg'] = annual_hydrogen_co2_kg

                # Calculate total annual CO2 emissions (gas + electricity)
                total_emissions = (annual_gas_co2_kg + annual_el_co2_kg + annual_biom_co2_kg +
                                   annual_oil_co2_kg + annual_hydrogen_co2_kg)
                b_kpis[year]['eco']['total_co2_emissions_kg'] = total_emissions

                # =========================================================================
                # FINAL KPI CALCULATIONS (Self-Sufficiency and Self-Consumption)
                # =========================================================================

                # Self-Sufficiency Rate (SSR) or Autonomy Rate
                if annual_gross_demand > 0:
                    ssr = (annual_gross_demand - annual_demand_from_grid) / annual_gross_demand
                else:
                    ssr = 0
                b_kpis[year]['tech']['self_sufficiency_rate'] = ssr

                # Self-Consumption Rate (SCR)
                if annual_gross_generation > 0:
                    scr = (annual_gross_generation - annual_injection_to_grid) / annual_gross_generation
                else:
                    scr = 0
                b_kpis[year]['tech']['self_consumption_rate'] = scr

                # Timestep-based Autonomy
                total_timesteps_in_year = 8760 / time_res_h
                if total_timesteps_in_year > 0:
                    b_kpis[year]['tech']['autonomy_timestep_rate'] = timesteps_autonomous / total_timesteps_in_year
                else:
                    b_kpis[year]['tech']['autonomy_timestep_rate'] = 0

            # Update the main dictionary
            self.kpis_per_building[building_id] = b_kpis

    def calculateGasolineCosts(self, data):
        """Compute annual gasoline costs (€) for each simulated year."""
        self.gasoline_costs = {}

        for year in self.inputData["simulated_years"]:
            price_per_liter = data.all_sim_ecoData[year]["price_gasoline_liter"]  # €/liter
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

        # Calculate total CO2 emissions over all years (weighted by interval length)
        self.total_co2_all = sum(self.co2emissions[year]["total_co2"] * year_weights[year] for year in sorted_years) # total CO2 emissions
        self.total_co2_dem_grid = sum(self.co2emissions[year]["co2_dem_grid"] * year_weights[year] for year in sorted_years) # CO2 emissions from electricity from grid
        self.total_co2_gas = sum(self.co2emissions[year]["co2_gas"] * year_weights[year] for year in sorted_years) # CO2 emissions from gas consumption
        self.total_co2_biom = sum(self.co2emissions[year]["co2_biom"] * year_weights[year] for year in sorted_years) # CO2 emissions from biomass consumption
        self.total_co2_waste = sum(self.co2emissions[year]["co2_waste"] * year_weights[year] for year in sorted_years) # CO2 emissions from waste consumption
        self.total_co2_hydrogen = sum(self.co2emissions[year]["co2_hydrogen"] * year_weights[year] for year in sorted_years) # CO2 emissions from hydrogen consumption
        self.total_co2_oil = sum(self.co2emissions[year]["co2_oil"] * year_weights[year] for year in sorted_years) # CO2 emissions from oil consumption
        self.total_co2_district_heat = sum(self.co2emissions[year]["co2_district_heat"] * year_weights[year] for year in sorted_years) # CO2 emissions from district heat consumption

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

        self.prepareData(data) # Needed for sum_res_load/inj
        self.calculateResidualLoad(data)
        self.calculatePeakLoad()
        self.calculatePeakToValley()
        self.calculateEnergyExchangeGCP(data)
        self.calculateEnergyExchangeWithinDistrict(data)
        self.calculateCoverFactors(data)
        self.calculateOperationCosts(data)
        self.calculateCO2emissions(data)
        self.calculateAutonomy()

        # Combined district and per-building calculations
        self.calc_annual_cost_total(data)
        self.calc_total_areas_and_demands(data)
        self.calculateGasolineCosts(data)
        self.calc_total_consumption_and_emissions(data)

        # Per-building KPI calculation method
        self.calculate_per_building_kpis(data)

    def KPIs_to_dict(self, data):
        """
        Collects all calculated KPI-Attributes and returns them as JSON-serializable dict.
        Numpy Arrays and datatypes are converted to python lists
        """

        # recursive help function
        def convert_numpy(obj):
            if isinstance(obj, dict):
                return {str(k): convert_numpy(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_numpy(i) for i in obj]
            elif isinstance(obj, np.ndarray):
                return [convert_numpy(i) for i in obj.tolist()]
            elif isinstance(obj, (np.float16, np.float32, np.float64)):
                return float(obj)
            elif isinstance(obj, (np.intc, np.intp, np.int8, np.int16, np.int32, np.int64)):
                return int(obj)
            return obj

        # ACHTUNG: Falls Kosten & CO2 jetzt auch pro Jahr berechnet werden (also Dicts sind),
        # musst du sie hier pro Jahr addieren.
        # Annahme hier: Wenn es Dicts sind, summieren wir sie pro Jahr.
        total_costs_eur_per_a = {}
        if isinstance(self.operationCosts, dict):
            for year in self.inputData["simulated_years"]:
                op_cost = self.operationCosts.get(year, 0)
                fix_dec = self.annual_fixed_costs_decentral.get(year, 0) if isinstance(
                    self.annual_fixed_costs_decentral, dict) else (self.annual_fixed_costs_decentral or 0)
                fix_cen = self.annual_fixed_costs_central.get(year, 0) if isinstance(self.annual_fixed_costs_central,
                                                                                     dict) else (
                            self.annual_fixed_costs_central or 0)
                total_costs_eur_per_a[year] = op_cost + fix_dec + fix_cen
        else:
            total_costs_eur_per_a = (self.operationCosts or 0) + \
                                    (self.annual_fixed_costs_decentral or 0) + \
                                    (self.annual_fixed_costs_central or 0)


        raw_kpi_results = {
            "general_info": {
                "res_area_m2": self.totalarea_residential,
                "non_res_area_m2": self.totalarea_non_residential,
                "total_nb_flats": self.totalnumberflats,
                "total_nb_occ": self.totalnumberocc,
                "total_headload_kW": self.totalheatload / 1000 if self.totalheatload else 0,
                "total_coolingload_kW": self.totalcoolingload / 1000 if self.totalcoolingload else 0,
            },
            "annual_energy_demand": {
                "total_heating_kWh": self.total_heating_demand / 1000 if self.total_heating_demand else 0,
                "total_cooling_kWh": self.total_cooling_demand / 1000 if self.total_cooling_demand else 0,
                "total_dhw_kWh": self.total_dhw_demand / 1000 if self.total_dhw_demand else 0,
                "total_el_kWh": self.total_electricity_demand / 1000 if self.total_electricity_demand else 0,
                "total_ev_kWh": self.total_EV_demand / 1000 if self.total_EV_demand else 0,
            },
            "total_economic_kpis": {
                "total_operation_costs_eur_per_a": self.operationCosts,
                "annual_fixed_costs_decentral_eur_per_a": self.annual_fixed_costs_decentral,
                "annual_fixed_costs_central_eur_per_a": self.annual_fixed_costs_central,
                "total_costs_eur_per_a": total_costs_eur_per_a
            },
            "ecological_kpis": {
            "co2_emissions_el_t_per_a": {str(year): data.get("co2_dem_grid", 0) for year, data in self.co2emissions.items()} if self.co2emissions else None,
            "co2_emissions_gas_t_per_a": {str(year): data.get("co2_gas", 0) for year, data in self.co2emissions.items()} if self.co2emissions else None,
            "co2_emissions_total_t_per_a": {str(year): data.get("total_co2", 0) for year, data in self.co2emissions.items()} if self.co2emissions else None
        },
            "technical_kpis_grid_interaction": {
            "peak_demand_kW": {str(year): val for year, val in self.peakDemand.items()} if isinstance(self.peakDemand, dict) else self.peakDemand,

            "peak_injection_kW": {
                str(year): (val if val > 0 else 0) for year, val in self.peakInjection.items()
            } if isinstance(self.peakInjection, dict) else (self.peakInjection if self.peakInjection and self.peakInjection > 0 else 0),

            "peak_to_valley_kW": {str(year): val for year, val in self.peakToValley.items()} if isinstance(self.peakToValley, dict) else self.peakToValley,

            "energy_supply_kwh_per_a": {str(year): val for year, val in self.W_dem_GCP_year.items()} if isinstance(self.W_dem_GCP_year, dict) else self.W_dem_GCP_year,

            "energy_injection_kwh_per_a": {str(year): val for year, val in self.W_inj_GCP_year.items()} if isinstance(self.W_inj_GCP_year, dict) else self.W_inj_GCP_year,

            "gas_supply_kwh_per_a": {str(year): val for year, val in self.gas_year.items()} if isinstance(self.gas_year, dict) else self.gas_year,
        },
            "technical_kpis_autonomy_district": {
            "energy_autonomy_year_pct": {str(year): val * 100 for year, val in self.energy_autonomy_year.items()}
                if isinstance(self.energy_autonomy_year, dict)
                else (self.energy_autonomy_year * 100 if self.energy_autonomy_year else None),
            "supply_cover_factor_year_pct": {str(year): val * 100 for year, val in self.scf_year.items()}
                if isinstance(getattr(self, 'scf_year', None), dict)
                else (self.scf_year * 100 if getattr(self, 'scf_year', None) else None),
            "demand_cover_factor_year_pct": {str(year): val * 100 for year, val in self.dcf_year.items()}
                if isinstance(getattr(self, 'dcf_year', None), dict)
                else (self.dcf_year * 100 if getattr(self, 'dcf_year', None) else None)
        },
            "kpis_per_bldg": self.kpis_per_building
        }

        kpi_results = convert_numpy(raw_kpi_results)

        # Save to file
        output_path = f'{data.optimization_path}/KPIs_opti_central.json'
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(kpi_results, f, indent=4)

        return kpi_results

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
                                  building["buildingFeatures"].get("f_PV1",0),
                                  building["buildingFeatures"].get("f_PV2",0),
                                  building["buildingFeatures"].get("f_PV", 0),
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