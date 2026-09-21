# -*- coding: utf-8 -*-

import numpy as np
import os
import math
from itertools import zip_longest
from districtgenerator.classes.certificate_generator import CertificateBuilder
import pandas as pd

# Unit lookup for device capacities in the KPI export tables (saveKPIs); default is "kW" for anything not listed.
DECENTRAL_DEVICE_UNIT_MAP = {"TES": "Liter", "TES_DHW": "Liter", "BAT": "kWh", "EV": "kWh", "PV": "m²", "STC": "m²"}
CENTRAL_DEVICE_UNIT_MAP = {"Heat_Grid": "-", "TES": "kWh", "CTES": "kWh", "BAT": "kWh", "GS": "kWh", "H2S": "kWh",
                           "PV": "kWp", "STC": "kWp", "WT": "kWp"}


def _get_yearly_val(val_list, idx):
    """Resolve a possibly year-indexed economic parameter (a list, one entry per simulated year) to its
    value for the given year index; a scalar parameter is returned as-is."""
    return val_list[idx] if isinstance(val_list, list) else val_list


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

        self.gas_year = None
        self.biomass_year = None
        self.waste_year = None
        self.hydrogen_year = None
        self.oil_year = None
        self.districtHeat_year = None

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
        self.total_area_mixed = None
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
        inputData["simulated_years"] = sorted(data.ecoData["interpolation_points"])
        inputData["observation_time"] = data.ecoData["observation_time"]
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
        # TODO: unfinished scaffolding carried over from develop - electricityDemand_cluster/
        # electricityGeneration_cluster/electricityGenerationRenewable_cluster/lossesBattery_cumulated_cluster
        # and centralEnergyUnit_load/centralEnergyUnit_inj below are never populated or read anywhere;
        # either finish the intended "central energy unit load/injection" and battery-loss tracking, or
        # remove this block.
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
            # summed gas usage of all buildings
            self.sum_res_gas[year] = np.zeros([len(data.clusters), len(data.district[0]["user"].elec_cluster[0])])
            # el. load / injection central energy unit
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
                    self.sum_res_gas[year][c, :] += np.array(self.inputData["resultsOptimization"][year][c][idx].get("res_gas", 0))

        ### for central energy unit
        # todo?

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
                opt_res = self.inputData["resultsOptimization"][year][c]
                res[c, :] = np.array(opt_res["P_dem_gcp"]) - np.array(opt_res["P_inj_gcp"])
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

        self.el_dem_buildings = {}
        self.el_inj_buildings = {}
        self.el_dem_eh = {}
        self.el_inj_eh = {}

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

                self.el_dem_buildings[year] += opt_res["from_grid_total_el_buildings"] * weight
                self.el_inj_buildings[year] += opt_res["to_grid_total_el_buildings"] * weight
                self.el_dem_eh[year] += opt_res["from_grid_total_el_eh"] * weight
                self.el_inj_eh[year] += opt_res["to_grid_total_el_eh"] * weight

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
                self.W_dem_buildings_year[year] += sum(self.sum_res_load[year][c, :] * data.time["timeResolution"] / 3600 / 1000) * weight
                self.W_inj_buildings_year[year] += sum(self.sum_res_inj[year][c, :] * data.time["timeResolution"] / 3600 / 1000) * weight

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

        sum_ClusterWeights = self.inputData["nbIntervals"]

        for year in self.inputData["simulated_years"]:
            self.supplyCoverFactor[year] = np.zeros(len(self.inputData["clusters"]))
            self.demandCoverFactor[year] = np.zeros(len(self.inputData["clusters"]))

            total_weighted_shared = 0.0
            total_weighted_demand = 0.0
            total_weighted_supply = 0.0

            for c in range(len(self.inputData["clusters"])):
                cluster_weight = self.inputData["clusterWeights"][self.inputData["clusters"][c]]
                # Sum of all buildings for each timestep, reusing prepareData()'s precomputed per-cluster
                # sums (self.sum_res_load/self.sum_res_inj), plus the energy hub's own res_load/res_inj.
                eh_res = self.inputData["resultsOptimization"][year][c]["energy_hub"]
                a = self.sum_res_load[year][c, :] + np.array(eh_res["res_load"])
                b = self.sum_res_inj[year][c, :] + np.array(eh_res["res_inj"])

                # At the same time step t, either res_load or res_inj should be 0.
                # However, a and b could both be greater than 0 at the same time step t,
                # since they represent the sums of all the buildings.
                # If both a and b are greater than 0, it means electricity is being transported from one building to another.
                min_val = np.minimum(a, b)

                sum_min = np.sum(min_val)
                sum_dem = np.sum(a)
                sum_sup = np.sum(b)

                self.demandCoverFactor[year][c] = np.divide(
                    sum_min, sum_dem, out=np.ones_like(sum_min), where=(sum_dem != 0))
                self.supplyCoverFactor[year][c] = np.divide(
                    sum_min, sum_sup, out=np.zeros_like(sum_min), where=(sum_sup != 0))

                # Weighted energy exchange within the neighborhood, accumulated across all clusters for each year
                weight_norm = cluster_weight / sum_ClusterWeights
                total_weighted_shared += sum_min * weight_norm
                total_weighted_demand += sum_dem * weight_norm
                total_weighted_supply += sum_sup * weight_norm

            # Weighted average of the cover factors across clusters for each year (ratio of weighted sums)
            self.dcf_year[year] = total_weighted_shared / total_weighted_demand if total_weighted_demand != 0 else 1.0
            self.scf_year[year] = total_weighted_shared / total_weighted_supply if total_weighted_supply != 0 else 0.0

        return None

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

        calc_annual_investment = {}
        calc_annual_investment_unsubsidized = {}
        self.decentral_individual_devices_annualized_cost = {} # Dictionary to store annualized cost per device and building
        self.annual_fixed_costs_decentral = 0
        self.annual_fixed_costs_decentral_unsubsidized = 0

        # Iteration over all buildings and then over all devices
        for n in range(len(district)):
            building_id = scenario["id"][n]
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
                "EH_DHW": district[n]["capacities"].get("EH_DHW", 0) / 1000,
                "CC": district[n]["capacities"].get("CC", 0) / 1000,
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
                                                                            1) * 3600) if "TES" in decentral_device_data else 0,
                "TES_DHW": (district[n]["capacities"].get("TES_DHW", 0) / physics["rho_water"] / physics[
                    "c_p_water"] / decentral_device_data.get("TES_DHW", {}).get("T_diff_max",
                                                                            1) * 3600) if "TES_DHW" in decentral_device_data else 0
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
                    # TODO: 'from_grid'/'to_grid' are grid-connection-limit entries added
                    # unconditionally by opti_dimensioning_central_devices.py (not real central devices),
                    # with cap=inf when enable_cap_limit_el is off. This filter only excludes cap<=0, so
                    # they pass through with cap=inf into central_individual_devices_annualized_cost -
                    # this is what caused the inf crash in saveKPIs' rounding. Also surfaces even in
                    # decentral scenarios (e.g. e7) that pass designEnergyhub=True.
                    if not isinstance(dev_spec, dict) or dev_spec.get("cap", 0) <= 0:
                        continue
                    total_subsidized = dev_spec.get("ann_inv_cost", 0) + dev_spec.get("om_cost", 0)
                    total_unsubsidized = dev_spec.get("ann_inv_cost_unsubsidized", 0) + dev_spec.get("om_cost", 0)
                    self.central_individual_devices_annualized_cost[dev_name] = {
                        "cap": dev_spec.get("cap", 0), "subsidized_annual_cost": total_subsidized,
                        "unsubsidized_annual_cost": total_unsubsidized
                    }

            if hasattr(data, 'heat_grid_data') and data.heat_grid_data:
                heat_grid_total_cost = data.heat_grid_data.get("costs", 0)
                heat_grid_cost = data.heat_grid_data.get("ann_costs", 0) + data.heat_grid_data.get("om_costs", 0)
                if heat_grid_total_cost > 0 or heat_grid_cost > 0:
                    self.central_individual_devices_annualized_cost["Heat_Grid"] = {
                        "cap": '', "subsidized_annual_cost": heat_grid_cost, "unsubsidized_annual_cost": heat_grid_cost
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
                "revenue_feed_in_el": -(self.el_inj_buildings[year] * ecoData["revenue_feed_in_el"] + self.el_inj_eh[year] * ecoData["revenue_feed_in_el_eh"])
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
        else:
            raise ValueError(f"Mode {mode} for investment cost calculation not recognized. Possible modes are 'subsidized' and 'unsubsidized'.")

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
        sum_ClusterWeights = self.inputData["nbIntervals"]

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
        total_area_residential, total_area_non_residential, total_area_mixed = 0, 0, 0
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

            b_type = building["buildingFeatures"]["building"]
            if data.is_mixed_building(b_type):
                total_area_mixed += building["buildingFeatures"]["area"]
                # Use the residential-only counts (nb_res_flats/nb_res_occ), not nb_flats/nb_occ, which
                # reflect the whole combined building (residential + non-residential parts merged).
                total_number_flats += building["user"].nb_res_flats
                total_number_occ += sum(building["user"].nb_res_occ)
                b_kpis['area_m2'] = building["buildingFeatures"]["area"]
                b_kpis['building_type'] = "mixed"
            elif b_type in {"SFH", "MFH", "TH", "AB"}:
                total_area_residential += building["buildingFeatures"]["area"]
                total_number_flats += building["user"].nb_flats
                total_number_occ += sum(building["user"].nb_occ)
                b_kpis['area_m2'] = building["buildingFeatures"]["area"]
                b_kpis['building_type'] = "residential"
            else:
                total_area_non_residential += building["buildingFeatures"]["area"]
                b_kpis['area_m2'] = building["buildingFeatures"]["area"]
                b_kpis['building_type'] = "non_residential"

            total_ICE_fuel_liters += np.sum(building["user"].ice_carprofile) # liters per timestep
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
            electricity_demand = sum(building["user"].elec)  # w/o EVs and electric-based heaters
            ev_demand = sum(building["user"].EV_carprofile)
            dhw_demand = sum(building["user"].dhw)

            total_heating_demand += heating_demand
            total_cooling_demand += cooling_demand
            total_electricity_demand += electricity_demand  # w/o EVs and electric-based heaters
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
        self.total_area_mixed = total_area_mixed
        self.totalarea_non_residential = total_area_non_residential
        self.totalnumberflats = total_number_flats
        self.totalnumberocc = total_number_occ
        self.totalheatload = total_heat_load
        self.totalcoolingload = total_cooling_load
        self.total_heating_demand = total_heating_demand
        self.total_cooling_demand = total_cooling_demand
        self.total_electricity_demand = total_electricity_demand    # w/o EVs and electric-based heaters
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

                curr_price_gas = _get_yearly_val(eco["price_supply_gas"], year_idx)
                curr_price_el = _get_yearly_val(eco["price_supply_el"], year_idx)
                curr_price_biom = _get_yearly_val(eco.get("price_biomass", 0), year_idx)
                curr_rev_feed_el = _get_yearly_val(eco["revenue_feed_in_el"], year_idx)
                curr_co2_gas = _get_yearly_val(eco["co2_gas"], year_idx)
                curr_co2_el = _get_yearly_val(eco["co2_el_grid"], year_idx)
                curr_co2_biom = _get_yearly_val(eco.get("co2_biom", 0), year_idx)
                curr_price_oil = _get_yearly_val(eco.get("price_oil", 0), year_idx)
                curr_co2_oil = _get_yearly_val(eco.get("co2_oil", 0), year_idx)
                curr_price_hydrogen = _get_yearly_val(eco.get("price_hydrogen", 0), year_idx)
                curr_co2_hydrogen = _get_yearly_val(eco.get("co2_hydrogen", 0), year_idx)

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

                    res_load_kwh = np.sum(res_load_kw) * time_res_h
                    res_inj_kwh = np.sum(res_inj_kw) * time_res_h

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
        self.calculate_per_building_kpis(data)
        self.saveKPIs(scenario_name=data.scenario_name, result_path=data.resultPath, buildings=data.district, file_format=data.report_config["kpi_save_type"])

    @staticmethod
    def _round_sig(x):
        """Round a numeric value to a whole number if |x| >= 1, else to 2 decimal places, so exported
        tables don't carry more precision than is meaningful. Non-numeric values (labels, units, '-'
        placeholders), NaN, 0 and +/-inf pass through unchanged."""
        if not isinstance(x, (int, float, np.integer, np.floating)) or isinstance(x, bool):
            return x
        if pd.isna(x) or x == 0 or np.isinf(x):
            return x
        return int(round(x)) if abs(x) >= 1 else round(x, 2)

    @staticmethod
    def _append_metric_columns(row_data, avg_metrics, yearly_metrics_by_year):
        """Append 'Avg. X (kWh/a)' and 'Year N X (kWh/a)' columns to a device row_data dict, from an
        avg-metrics dict and a {year: yearly_metrics_dict} mapping (caller resolves any building_id lookup)."""
        for metric_name, val in avg_metrics.items():
            row_data[f"Avg. {metric_name} (kWh/a)"] = round(val, 2)
        for year, yearly_metrics in yearly_metrics_by_year.items():
            for metric_name, val in yearly_metrics.items():
                row_data[f"Year {year} {metric_name} (kWh/a)"] = round(val, 2)

    def _yearly_series(self, source, key=None, years=None):
        """Build a {year: value} dict for the yearly KPI table, pulling from a
        {year: value} dict (key=None) or a {year: {key: value}} dict (key given)."""
        years = years if years is not None else sorted(self.inputData["simulated_years"])
        if key is None:
            return {year: source.get(year, None) for year in years}
        return {year: source.get(year, {}).get(key, None) for year in years}

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
        kpi_data_yearly["Peak Demand district (kW)"] = self._yearly_series(self.peakDemand)
        kpi_data_yearly["Peak Injection district (kW)"] = self._yearly_series(self.peakInjection)
        kpi_data_yearly["Peak to Valley (kW)"] = self._yearly_series(self.peakToValley)
        kpi_data_yearly["Electricity Injection to Grid (kWh/a)"] = self._yearly_series(self.W_inj_GCP_year)
        kpi_data_yearly["Electricity Demand from Grid (kWh/a)"] = self._yearly_series(self.W_dem_GCP_year)
        kpi_data_yearly["Gas Consumption (kWh/a)"] = self._yearly_series(self.gas_year)
        kpi_data_yearly["Biomass Consumption (kWh/a)"] = self._yearly_series(self.biomass_year)
        kpi_data_yearly["Waste Consumption (kWh/a)"] = self._yearly_series(self.waste_year)
        kpi_data_yearly["Hydrogen Consumption (kWh/a)"] = self._yearly_series(self.hydrogen_year)
        kpi_data_yearly["Oil Consumption (kWh/a)"] = self._yearly_series(self.oil_year)
        kpi_data_yearly["District Heat Consumption (kWh/a)"] = self._yearly_series(self.districtHeat_year)
        # Note: "within District" here means residual electricity exchanged between buildings inside the
        # district (from prepareData()/calculateEnergyExchangeWithinDistrict), not exchange with the public
        # grid at the GCP (that's "...to/from Grid" above). The per-building "Grid Demand/Injection (kWh/a)"
        # columns in the Building KPIs sheet below reconcile to this district total, not to the GCP figures.
        # TODO: consider renaming those per-building columns (e.g. "Residual Demand/Injection") to avoid confusion.
        kpi_data_yearly["Electricity Injection within District (kWh/a)"] = self._yearly_series(self.W_inj_buildings_year)
        kpi_data_yearly["Electricity Demand within District (kWh/a)"] = self._yearly_series(self.W_dem_buildings_year)
        kpi_data_yearly["Demand Cover Factor (-)"] = self._yearly_series(self.dcf_year)
        kpi_data_yearly["Supply Cover Factor (-)"] = self._yearly_series(self.scf_year)
        kpi_data_yearly["Operation Costs (€/a)"] = self._yearly_series(self.operationCosts)
        kpi_data_yearly["CO2 Emissions (t/a)"] = self._yearly_series(self.co2emissions, "total_co2")
        kpi_data_yearly["CO2 Emissions Grid Electricity (t/a)"] = self._yearly_series(self.co2emissions, "co2_dem_grid")
        kpi_data_yearly["CO2 Emissions Gas (t/a)"] = self._yearly_series(self.co2emissions, "co2_gas")
        kpi_data_yearly["CO2 Emissions Biomass (t/a)"] = self._yearly_series(self.co2emissions, "co2_biom")
        kpi_data_yearly["CO2 Emissions Waste (t/a)"] = self._yearly_series(self.co2emissions, "co2_waste")
        kpi_data_yearly["CO2 Emissions Hydrogen (t/a)"] = self._yearly_series(self.co2emissions, "co2_hydrogen")
        kpi_data_yearly["CO2 Emissions Oil (t/a)"] = self._yearly_series(self.co2emissions, "co2_oil")
        kpi_data_yearly["CO2 Emissions District Heat (t/a)"] = self._yearly_series(self.co2emissions, "co2_district_heat")
        kpi_data_yearly["Electricity Costs (€/a)"] = self._yearly_series(self.detailed_costs_year, "electricity")
        kpi_data_yearly["Gas Costs (€/a)"] = self._yearly_series(self.detailed_costs_year, "gas")
        kpi_data_yearly["Oil Costs (€/a)"] = self._yearly_series(self.detailed_costs_year, "oil")
        kpi_data_yearly["Waste Costs (€/a)"] = self._yearly_series(self.detailed_costs_year, "waste")
        kpi_data_yearly["Biomass Costs (€/a)"] = self._yearly_series(self.detailed_costs_year, "biomass")
        kpi_data_yearly["District Heat Costs (€/a)"] = self._yearly_series(self.detailed_costs_year, "district_heat")
        kpi_data_yearly["Hydrogen Costs (€/a)"] = self._yearly_series(self.detailed_costs_year, "hydrogen")
        kpi_data_yearly["Revenue from Electricity Feed-in (€/a)"] = self._yearly_series(self.detailed_costs_year, "revenue_feed_in_el")
        kpi_data_yearly["Autonomy (Time Fraction)"] = self._yearly_series(self.energy_autonomy_year)
        kpi_data_yearly["Gasoline Costs (€/a)"] = self._yearly_series(self.gasoline_costs)
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
                    # HP "geringinvestive Massnahmen" (config: HP__enable_measures / HP__measures_inv_fix,
                    # computed in calc_annual_cost_total): low-investment retrofit measures that lower the
                    # heating system's supply/return temperature to improve heat-pump efficiency. This cost
                    # IS included in the building's aggregate cost (kpis_per_building[...]['costs']
                    # ['annual_fixed_costs_eur'], and therefore in the Building KPIs sheet's "Annual Fixed
                    # Costs Decentral" total), but is deliberately left out of this per-device table since it
                    # isn't a "device" in the same sense as the others. Pre-existing decision (predates the
                    # 2026-09 KPIs.py merge cleanup, introduced together with saveKPIs itself, commit
                    # 727de13) - not yet resolved whether to show it as its own row here or elsewhere.
                    # TODO: decide how/where to surface this cost per-device; until then, per-building sums
                    # in this sheet will not exactly reconcile to the Building KPIs sheet for HP buildings
                    # that have this measure applied.
                    continue

                unit = DECENTRAL_DEVICE_UNIT_MAP.get(device_name, "kW")

                row_data = {
                    'Building ID': building["unique_name"],
                    'Device': device_name,
                    'Capacity': round(device_info['cap'], 3) if device_info['cap'] != '' else '-',
                    'Unit': unit,
                    'Annualized Cost (€/a)': round(device_info['subsidized_annual_cost'], 2),
                    'Annualized Cost Unsubsidized (€/a)': round(device_info['unsubsidized_annual_cost'], 2)
                }

                avg_metrics = self.decentral_device_energy_avg.get(building_id, {}).get(device_name, {})
                yearly_metrics_by_year = {
                    year: self.decentral_device_energy_year.get(year, {}).get(building_id, {}).get(device_name, {})
                    for year in years
                }
                self._append_metric_columns(row_data, avg_metrics, yearly_metrics_by_year)

                dec_device_data_list.append(row_data)

        # Central Devices capacities and subsidized and unsubsidized annualized costs
        cent_device_data_list = []
        for device_name, device_info in self.central_individual_devices_annualized_cost.items():
            unit = CENTRAL_DEVICE_UNIT_MAP.get(device_name, "kW")

            row_data = {
                'Device': device_name,
                'Capacity': round(device_info['cap'], 3) if device_info['cap'] != '' else '-',
                'Unit': unit,
                'Annualized Cost Subsidized (€/a)': round(device_info['subsidized_annual_cost'], 2),
                'Annualized Cost Unsubsidized (€/a)': round(device_info['unsubsidized_annual_cost'], 2)
            }

            avg_metrics = self.central_device_energy_avg.get(device_name, {})
            yearly_metrics_by_year = {
                year: self.central_device_energy_year.get(year, {}).get(device_name, {}) for year in years
            }
            self._append_metric_columns(row_data, avg_metrics, yearly_metrics_by_year)
            cent_device_data_list.append(row_data)

        # Create list of per-building KPIs (one row per building per simulated year)
        building_data_list = []
        for building_id, b_kpis in self.kpis_per_building.items():
            for year in years:
                tech_data = b_kpis.get(year, {}).get('tech', {})
                eco_data = b_kpis.get(year, {}).get('eco', {})
                costs_data = b_kpis.get('costs', {})
                building_data_list.append({
                    'Building ID': building_id,
                    'Year': year,
                    'Building Type': b_kpis.get('building_type', 'N/A'),
                    'Heating System': b_kpis.get('heating_system', 'N/A'),
                    'Area (m²)': b_kpis.get('area_m2', 0),
                    'Total Heat Load (kW)': b_kpis.get('total_heat_load_kW', 0),
                    'Annual Heating Demand (kWh/a)': b_kpis.get('annual_heating_demand_kWh', 0),
                    'Annual Electricity Demand (kWh/a)': b_kpis.get('annual_electricity_demand_kWh', 0),
                    'Annual DHW Demand (kWh/a)': b_kpis.get('annual_dhw_demand_kWh', 0),
                    'Annual Cooling Demand (kWh/a)': b_kpis.get('annual_cooling_demand_kWh', 0),
                    'Annual EV Demand (kWh/a)': b_kpis.get('annual_ev_demand_kWh', 0),
                    'Peak Demand (kW)': tech_data.get('peak_demand_kW', 0),
                    'Peak Injection (kW)': tech_data.get('peak_injection_kW', 0),
                    'Grid Demand (kWh/a)': tech_data.get('grid_demand_kWh', 0),
                    'Grid Injection (kWh/a)': tech_data.get('grid_injection_kWh', 0),
                    'Gross Generation (kWh/a)': tech_data.get('gross_generation_kWh', 0),
                    'Gross Demand (kWh/a)': tech_data.get('gross_demand_kWh', 0),
                    'Gas Consumption (kWh/a)': tech_data.get('gas_consumption_kwh', 0),
                    'Biomass Consumption (kWh/a)': tech_data.get('biomass_consumption_kwh', 0),
                    'Oil Consumption (kWh/a)': tech_data.get('oil_consumption_kwh', 0),
                    'Hydrogen Consumption (kWh/a)': tech_data.get('hydrogen_consumption_kwh', 0),
                    'Self-Sufficiency Rate (%)': tech_data.get('self_sufficiency_rate', 0) * 100,
                    'Self-Consumption Rate (%)': tech_data.get('self_consumption_rate', 0) * 100,
                    'Autonomy Timestep Rate (%)': tech_data.get('autonomy_timestep_rate', 0) * 100,
                    'Total Energy Cost (€/a)': eco_data.get('total_energy_cost_eur', 0),
                    'Total CO2 Emissions (kg/a)': eco_data.get('total_co2_emissions_kg', 0),
                    'Annual Fixed Costs Decentral (€/a)': costs_data.get('annual_fixed_costs_eur', 0),
                })
        kpi_df_buildings = pd.DataFrame(building_data_list)

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

        # Round all numeric values for export: whole numbers for |x| >= 1, 2 decimals below that.
        for df in (kpi_df_yearly, kpi_df_static, kpi_df_dec_devices, kpi_df_cent_devices, kpi_df_buildings):
            if not df.empty:
                df[df.columns] = df[df.columns].map(self._round_sig)

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
                kpi_df_buildings.to_excel(writer, sheet_name='Building KPIs', index=False)

            print(f"KPIs saved to: {filename}")

        elif file_format == "csv":
            kpi_df_yearly.to_csv(os.path.join(result_path, f"KPIs_{scenario_name}_yearly.csv"), index=False, sep=';', decimal=',')
            kpi_df_static.to_csv(os.path.join(result_path, f"KPIs_{scenario_name}_static.csv"), index=False, sep=';', decimal=',')
            kpi_df_dec_devices.to_csv(os.path.join(result_path, f"KPIs_{scenario_name}_decentral_devices.csv"), index=False, sep=';', decimal=',')
            if not kpi_df_cent_devices.empty:
                kpi_df_cent_devices.to_csv(os.path.join(result_path, f"KPIs_{scenario_name}_central_devices.csv"), index=False, sep=';', decimal=',')
            kpi_df_buildings.to_csv(os.path.join(result_path, f"KPIs_{scenario_name}_buildings.csv"), index=False, sep=';', decimal=',')

            print(f"KPIs saved to: {result_path} as CSV files: KPIs_{scenario_name}_*.csv")

        elif file_format == None:
            print("KPIs not saved to file as no file format specified in report configuration.")
        else:
            print(f"Unsupported file format: {file_format}")


    def create_certificate(self, data, result_path, file_name=None):
        """
        Generate a certificate as PDF file with a list of KPIs and a list with building information.

        Parameters:
        - filename: The name of the PDF file to create.
        - title: The title of the document.
        - kpis: A list of strings, where each string is a KPI to be written in the document.
        """

        certGenerator = CertificateBuilder(data = data, kpis=self, result_path=result_path, file_name=file_name)
        certGenerator.generate_certificate()