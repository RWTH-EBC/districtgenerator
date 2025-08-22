# -*- coding: utf-8 -*-

import sys
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

    def __init__(self, data, decentral_config):
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
        self.annual_investment_total = None
        self.totalarea = None
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
        self.prepareData(data, decentral_config)
        self.calculateResidualLoad(data)
        self.calculatePeakLoad()
        self.calculatePeakToValley()
        self.calculateEnergyExchangeGCP(data)
        self.calculateEnergyExchangeWithinDistrict(data)
        self.calculateAutonomy()
        self.calculateCoverFactors(data)
        self.calc_annual_cost_total(data.scenario, data.decentral_device_data, data.district, data.physics)

    def prepareData(self, data, decentralDev):
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
        # todo: chekc decentralDev
        # initialize lists
        electricityDemand_cluster = []
        electricityGeneration_cluster = []
        electricityGenerationRenewable_cluster = []
        lossesBattery_cumulated_cluster = []
        # Load data of decentral devices (to calculate battery losses)
        srcPath = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        #decentralDev = {}
        #with open(os.path.join(srcPath, 'data', 'decentral_device_data.json')) as json_file:
        #    jsonData = json.load(json_file)
        #    for subData in jsonData:
        #        decentralDev[subData["abbreviation"]] = {}
        #        for subsubData in subData["specifications"]:
        #            decentralDev[subData["abbreviation"]][subsubData["name"]] = subsubData["value"]

        # summed el. load of all buildings , [number of time periods, time steps within periods]
        self.sum_res_load = np.zeros([len(data.clusters), len(data.district[0]["user"].elec_cluster[0])])
        # summed el. injection of all buildings
        self.sum_res_inj = np.zeros([len(data.clusters), len(data.district[0]["user"].elec_cluster[0])])
        # el. load central energy unit
        centralEnergyUnit_load = np.zeros([len(data.clusters), len(data.district[0]["user"].elec_cluster[0])])
        # el. injection central energy unit
        centralEnergyUnit_inj = np.zeros([len(data.clusters), len(data.district[0]["user"].elec_cluster[0])])

        ### for buildings
        # loop over cluster
        for c in range(len(self.inputData["clusters"])):
            # loop over buildings
            for id in data.scenario["id"]:
                self.sum_res_load[c, :] += np.array(self.inputData["resultsOptimization"][c][id]["res_load"])
                self.sum_res_inj[c, :]  += np.array(self.inputData["resultsOptimization"][c][id]["res_inj"])

        ### for central energy unit

    def calculateResidualLoad(self, data):
        """
        Calculate residual load at grid connection point (GCP) in [kW].
        Demand is positive and injection negative.

        Returns
        -------
        None.
        """

        res = np.zeros([len(self.inputData["clusters"]), len(data.district[0]["user"].elec_cluster[0])])

        # loop over cluster
        for c in range(len(self.inputData["clusters"])):
            for t in range(len(data.district[0]["user"].elec_cluster[0])):
                res[c, t] = self.inputData["resultsOptimization"][c]["P_dem_gcp"][t]\
                            - self.inputData["resultsOptimization"][c]["P_inj_gcp"][t]

        # create array and change unit from [W] to [kW]
        self.residualLoad = res / 1000

    def calculatePeakLoad(self):
        """
        Calculate peak demand and peak injection at grid connection point (GCP) in [kW].

        Returns
        -------
        None.
        """

        # maximal load [kW]
        self.peakDemand = round(np.max(self.residualLoad[:, :-4]), 3)

        # maximal injection [kW]
        self.peakInjection = round(np.min(self.residualLoad) *(-1), 3)

    def calculatePeakToValley(self):
        """
        Calculate the difference between the maximum and the minimum of the residual load in [kW].

        Returns
        -------
        None.
        """

        PtV = np.zeros(len(self.inputData["clusters"]))
        for c in range(len(self.inputData["clusters"])):
            PtV[c] = round(max(self.residualLoad[c, :-4]) - min(self.residualLoad[c, :-4]), 3)

        # peak to valley for each time period[kW]
        self.peakToValley = max(PtV)

    def calculateEnergyExchangeGCP(self, data):

        # Electricity [kWh] feed into the superordinated grid
        W_inj_GCP = np.zeros(len(data.clusters))
        # Electricity [kWh] covered by the superordinated grid
        W_dem_GCP = np.zeros(len(data.clusters))
        Gas = np.zeros(len(data.clusters))

        # electricity feed into and covered by superordinated grid for one year [kWh]
        self.W_inj_GCP_year = 0
        self.W_dem_GCP_year = 0
        self.Gas_year = 0
        # loop over cluster
        for c in range(len(self.inputData["clusters"])):
            W_dem_GCP[c] = sum(self.inputData["resultsOptimization"][c]["P_dem_gcp"]) \
                                     * data.time["timeResolution"] / 3600 / 1000
            W_inj_GCP[c] = sum(self.inputData["resultsOptimization"][c]["P_inj_gcp"]) \
                                     * data.time["timeResolution"] / 3600 / 1000
            Gas[c] = sum(self.inputData["resultsOptimization"][c]["P_gas_total"]) * data.time["timeResolution"] / 3600 / 1000
            self.W_dem_GCP_year += W_dem_GCP[c] * self.inputData["clusterWeights"][self.inputData["clusters"][c]]
            self.W_inj_GCP_year += W_inj_GCP[c] * self.inputData["clusterWeights"][self.inputData["clusters"][c]]
            self.Gas_year += Gas[c] * self.inputData["clusterWeights"][self.inputData["clusters"][c]]

    def calculateEnergyExchangeWithinDistrict(self, data):

        # Electricity [kWh] feed into the local grid by buildings
        W_inj_buildings = np.zeros(len(data.clusters))
        # Electricity [kWh] purchase of buildings
        W_dem_buildings = np.zeros(len(data.clusters))

        self.W_inj_buildings_year = 0
        self.W_dem_buildings_year = 0
        # loop over cluster
        for c in range(len(self.inputData["clusters"])):
            self.W_dem_buildings_year += sum(self.sum_res_load[c, :] * data.time["timeResolution"] / 3600 / 1000) \
                                         * self.inputData["clusterWeights"][self.inputData["clusters"][c]]
            self.W_inj_buildings_year += sum(self.sum_res_inj[c, :] * data.time["timeResolution"] / 3600 / 1000) \
                                         * self.inputData["clusterWeights"][self.inputData["clusters"][c]]

    def calculateCoverFactors(self, data):
        """
        Calculate the ratio between the self-consumed electricity and the total electricity demand.

        Returns
        -------
        None.
        """

        self.supplyCoverFactor = np.zeros(len(self.inputData["clusters"]))
        self.demandCoverFactor = np.zeros(len(self.inputData["clusters"]))

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
                for id in data.scenario["id"]:
                    a += self.inputData["resultsOptimization"][c][id]["res_load"][t]
                    b += self.inputData["resultsOptimization"][c][id]["res_inj"][t]
                # sum of all timesteps
                nenner_dem[c, t] += a
                nenner_sup[c, t] += b
                min[c, t] = np.min([a, b])

            self.demandCoverFactor[c] = np.sum(min[c, :]) / np.sum(nenner_dem[c, :])
            self.supplyCoverFactor[c] = np.sum(min[c, :]) / np.sum(nenner_sup[c, :])

        self.dcf_year = 0
        self.scf_year = 0
        sum_ClusterWeights = 0
        # loop over cluster
        for c in range(len(self.inputData["clusters"])):
            sum_ClusterWeights += self.inputData["clusterWeights"][self.inputData["clusters"][c]]
        for c in range(len(self.inputData["clusters"])):
            self.dcf_year += self.demandCoverFactor[c] * (self.inputData["clusterWeights"][self.inputData["clusters"][c]]
                                                          / sum_ClusterWeights)
            self.scf_year += self.supplyCoverFactor[c] * (self.inputData["clusterWeights"][self.inputData["clusters"][c]]
                                                          / sum_ClusterWeights)

    def calc_annual_cost_total(self, scenario, decentral_device_data, district, physics):

        # Count occurrences of "BOI", "HP", and "CHP" in the 'heater' column
        heater_counts = scenario['heater'].value_counts()
        heater_counts["TES"] = heater_counts.sum()

        # Sum the values in the 'PV', 'STC', 'EV', and 'BAT' columns
        heater_counts["PV"] = scenario['PV'].sum()
        heater_counts["STC"] = scenario['STC'].sum()
        heater_counts["EV"] = scenario['EV'].sum()
        heater_counts["BAT"] = scenario['BAT'].sum()

        capacities = {}
        for n in range(len(district)):
            capacities[n] = {}
            capacities[n]["BOI"] = district[n]["capacities"]["BOI"] / 1000
            capacities[n]["HP"] = district[n]["capacities"]["HP"] / 1000
            capacities[n]["CHP"] = district[n]["capacities"]["CHP"] / 1000
            capacities[n]["PV"] = district[n]["capacities"]["PV"]["area"]
            capacities[n]["STC"] = district[n]["capacities"]["STC"]["area"]
            capacities[n]["EV"] =  district[n]["capacities"]["EV"] / 1000
            capacities[n]["BAT"] = district[n]["capacities"]["BAT"] / 1000
            capacities[n]["TES"] = (district[n]["capacities"]["TES"] / physics["rho_water"] / physics["c_p_water"] /
                                    decentral_device_data["TES"]["T_diff_max"] * 3600)

        for n in range(len(district)):
            calc_annual_investment = {}
            for dev in ["BOI", "HP", "CHP", "PV", "STC", "EV", "BAT", "TES"]:
                calc_annual_investment[dev] = {}
                try:
                    if heater_counts[dev] > 0:
                        calc_annual_investment[dev] = self.calc_annual_cost_device(decentral_device_data[dev],
                                                                                decentral_device_data["inv_data"],
                                                                                capacities[n][dev])
                    else: calc_annual_investment[dev] = 0
                except:
                    calc_annual_investment[dev] = 0
                    heater_counts[dev] = 0

        self.annual_investment_total = (calc_annual_investment["BOI"] * heater_counts["BOI"]
                                        + calc_annual_investment["HP"] * heater_counts["HP"]
                                        + calc_annual_investment["CHP"] * heater_counts["CHP"]
                                        + calc_annual_investment["PV"] * heater_counts["PV"]
                                        + calc_annual_investment["STC"] * heater_counts["STC"]
                                        + calc_annual_investment["EV"] * heater_counts["EV"]
                                        + calc_annual_investment["BAT"] * heater_counts["BAT"]
                                        + calc_annual_investment["BAT"] * heater_counts["BAT"])

    def calc_annual_cost_device(self, dev, param, cap):
        """
        Calculation of total investment costs including replacements (based on VDI 2067-1, pages 16-17).

        Parameters
        ----------
        dev : dictionary
            technology parameter
        param : dictionary
            economic parameters

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

        observation_time = param["observation_time"]
        interest_rate = param["interest_rate"]
        q = 1 + param["interest_rate"]

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
        inv = dev["inv_var"] * cap
        # Annual investment costs
        c_inv= inv * ann_factor
        # Operation and maintenance costs
        c_om = dev["cost_om"] * inv
        # Total annual cost
        c_total = c_inv + c_om

        return c_total


    def calculateOperationCosts(self, data):
        """
        Calculate the operation cost for one year in [€].

        Returns
        -------
        None.
        """

        # list with central operation costs for each cluster [€]
        operationCosts_clusters = []
        for c in range(len(self.inputData["clusters"])):
            operationCosts_clusters.append(self.inputData["resultsOptimization"][c]["Cost_total"])

        # multiply central operation costs of each cluster with the weight of respective cluster
        temp_operationCosts = 0
        for c in range(len(self.inputData["clusters"])):
            temp_operationCosts \
                += operationCosts_clusters[c] * self.inputData["clusterWeights"][self.inputData["clusters"][c]]

        # central operation costs for one year [€]
        self.operationCosts = round(temp_operationCosts, 2) / 1000

    def calculateCO2emissions(self, data, json_data):
        """
        Calculate the CO2 emissions for one year in [kg].

        Parameters
        ----------
        data: Datahandler object
            Datahandler object which contains relevant economic data.
        json_data : dict
            Dictionary containing the CO2 emission factors for electricity, gas, and PV.

        Returns
        -------
        None.
        """

        # important for weather conditions

        # todo: check
        CO2_factor_el_grid = json_data["co2_el_grid"]  # Emi_elec_grid
        CO2_factor_gas = json_data["co2_gas"]          # Emi_gas
        CO2_factor_pv = json_data["co2_biom"]          # Emi_pv  ??? does not have key co2_pv

        # change unit from [Wh] to [kWh] and consider time resolution --> in function "calculateEnergyExchangeGCP"
        co2_dem_grid = self.W_dem_GCP_year * CO2_factor_el_grid
        co2_gas = self.Gas_year * CO2_factor_gas

        # caused CO2 emissions by PV [kg]
        co2_pv = 0
        for c in range(len(self.inputData["clusters"])):
            for id in range(len(self.inputData["district"])):
                try:
                    co2_pv += np.sum(self.inputData["district"][id]["generationPV_cluster"][c, :]
                                 * data.time["timeResolution"] / 3600 / 1000) * CO2_factor_pv \
                          * self.inputData["clusterWeights"][self.inputData["clusters"][c]]
                except KeyError:
                    co2_pv += 0


        # CO2 emissions for one year
        self.co2emissions = [co2_dem_grid, co2_pv, co2_gas]

    def calculateAutonomy(self):
        """
        Calculation of the ratio of operating time in which the local electricity demand is completely covered
        by electricity generation in the district.

        Returns
        -------
        None.
        """
        LOLP = np.zeros(len(self.inputData["clusters"]))
        self.energy_autonomy = np.zeros(len(self.inputData["clusters"]))

        # loop over cluster
        for c in range(len(self.inputData["clusters"])):
            y = 0
            for t in range(len(self.residualLoad[c])):
                if self.residualLoad[c, t] > 0:
                    y += 1
                else:
                    y += 0
            LOLP[c] = y / len(self.residualLoad[c])
        self.energy_autonomy = np.array([1, 1, 1, 1]) - LOLP

        self.energy_autonomy_year = 0
        sum_ClusterWeights = 0
        ## loop over cluster
        for c in range(len(self.inputData["clusters"])):
            sum_ClusterWeights += self.inputData["clusterWeights"][self.inputData["clusters"][c]]
        for c in range(len(self.inputData["clusters"])):
            self.energy_autonomy_year += self.energy_autonomy[c] * (
                    self.inputData["clusterWeights"][self.inputData["clusters"][c]] / sum_ClusterWeights)

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
        total_net_leased_area = 0
        total_number_flats = 0
        total_number_occ = 0
        total_heat_load = 0
        # total_cooling_load = 0
        total_heating_demand = 0
        total_cooling_demand = 0
        total_electricity_demand = 0
        total_dhw_demand = 0
        sum_electricity_profile = []
        sum_heat_profile = []
        sum_cool_profile = []
        sum_dhw_profile = []

        for building in data.district:
            # sum all building areas
            total_net_leased_area += building["buildingFeatures"]["area"]
            total_number_flats += building["user"].nb_flats
            for flat in building["user"].nb_occ:
                total_number_occ += flat

            # sum all building design heat and cooling loads
            total_heat_load += building["envelope"].heatload
            # total_cooling_load += building["envelope"].cooling_load

            # sum all building demands
            total_heating_demand += sum(building["user"].heat)
            total_cooling_demand += sum(building["user"].cooling)
            total_electricity_demand += sum(building["user"].elec)
            total_dhw_demand += sum(building["user"].dhw)

            # sum all building demand profiles
            sum_electricity_profile = [sum(i) for i in zip_longest(
                sum_electricity_profile, building["user"].elec, fillvalue=0)] # w/o cars
            sum_heat_profile = [sum(i) for i in zip_longest(
                sum_electricity_profile, building["user"].heat, fillvalue=0)]
            sum_cool_profile = [sum(i) for i in zip_longest(
                sum_electricity_profile, building["user"].cooling, fillvalue=0)]
            sum_dhw_profile = [sum(i) for i in zip_longest(
                sum_electricity_profile, building["user"].dhw, fillvalue=0)]

        self.totalarea = total_net_leased_area
        self.totalnumberflats = total_number_flats
        self.totalnumberocc = total_number_occ
        self.totalheatload = total_heat_load
        # self.totalcoolingload = total_cooling_load
        self.total_heating_demand = total_heating_demand
        self.total_cooling_demand = total_cooling_demand
        self.total_electricity_demand = total_electricity_demand
        self.total_dhw_demand = total_dhw_demand
        self.total_electricity_peak = max(sum_electricity_profile)
        self.total_heat_peak = max(sum_heat_profile)
        self.total_dhw_peak = max(sum_dhw_profile)
        self.total_cooling_peak = max(sum_cool_profile)

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
        #self.calculateSupplyCoverFactor()
        self.calculateOperationCosts(data)
        self.calculateCO2emissions(data, data.ecoData)
        self.calculateAutonomy()
        self.calc_annual_cost_total(data.scenario, data.decentral_device_data, data.district, data.physics)
        self.calc_total_areas_and_demands(data)

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
            gebaeudeliste.append([building["buildingFeatures"]["building"],
                                  building["buildingFeatures"]["year"],
                                  building["buildingFeatures"]["retrofit"],
                                  building["buildingFeatures"]["area"],
                                  building["buildingFeatures"]["heater"],
                                  building["buildingFeatures"]["PV"],
                                  building["buildingFeatures"]["STC"],
                                  building["buildingFeatures"]["EV"],
                                  building["buildingFeatures"]["BAT"],
                                  building["buildingFeatures"]["f_TES"],
                                  building["buildingFeatures"]["f_BAT"],
                                  building["buildingFeatures"]["f_EV"],
                                  building["buildingFeatures"]["f_PV"],
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
        #                 f_EV:
        #                 f_PV:
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
                                               + self.total_dhw_demand) / 1000, 2)) + " kWh/a",
                "Norm-Heizlast": str(round(self.totalheatload / 1000)) + " kW",
                "Solltemperatur": str(data.design_building_data["T_set_min"]) + " \u00B0C / " + str(
                    data.design_building_data["T_set_max"]) + " \u00B0C",
                "Bedarfe": (round(self.total_electricity_demand / 1000000, 2),
                            round(self.total_heating_demand / 1000000, 2),
                            round(self.total_dhw_demand / 1000000, 2),
                            round(self.total_cooling_demand / 1000000, 2)),
                "Max. Leistungen": (round(self.total_electricity_peak / 1000),
                                    round(self.total_heat_peak / 1000),
                                    round(self.total_dhw_peak / 1000),
                                    round(self.total_cooling_peak / 1000))
            }
        opt_ergebnisse={
                "CO2-äqui. Emissionen": str(round(sum(self.co2emissions))) + " t/a",
                "Energiekosten": str(round(self.operationCosts)) + " \u20AC/a",
                "Spitzenlast (el.)": str(round(self.peakDemand, 2)) + " kW",
                "Max. Einspeiseleistung": str(round(self.peakInjection, 2)) + " kW",
                "Supply-Cover-Faktor": str(round(self.scf_year, 2)),
                "Demand-Cover-Faktor": str(round(self.dcf_year, 2))
            }
        struktur={
                "EFH": SFH,
                "MFH": MFH,
                "Reihenhaus": TH,
                "Block": AB,
                "Wohneinheiten gesamt": self.totalnumberflats,
                "Bewohner gesamt": self.totalnumberocc,
                "Nettowohnfläche gesamt": str(self.totalarea) + " m\u00B2",
                "Standort (PLZ)": str(data.site["zip"]),
                "Testreferenzjahr": str(data.site["TRYYear"])[3:] + " / " + str(data.site["TRYType"]),
                "Quartiersname": str(data.scenario_name)
            }

        if result_path is None:
            src_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            filename = os.path.join(src_path, "results", "Quartiersenergieausweis.pdf")
        else:
            filename = os.path.join(result_path, "Quartiersenergieausweis.pdf")

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
        bottom2 = 700

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
        content = content[0:3]
        values = values[0:3]

        i = 0
        for item in content:
            certificate.drawString(85, height - top1 - 32 - (18 * i), item + ":")
            i = i + 1

        j = 0
        for value in values:
            certificate.drawString(200, height - top1 - 32 - (18 * j), str(value))
            j = j + 1

        bottom_kennwerte = top1 + 32 + 18 * j

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
        legend.columnMaximum = 2
        legend.boxAnchor = 'nw'
        legend.y = -5
        legend.x = -36
        legend.colorNamePairs = [
            (colors.Color(0 / 256, 85 / 256, 31 / 256), u'Strom: ' + str(pc.data[0])),
            (colors.Color(134 / 256, 169 / 256, 26 / 256), u'Wärme: ' + str(pc.data[1])),
            (colors.Color(54 / 256, 132 / 256, 39 / 256), u'TWW: ' + str(pc.data[2])),
            (colors.Color(122 / 256, 186 / 256, 214 / 256), u'Kälte: ' + str(pc.data[3])),]
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

        for ii in range(n_rows + 1):
            certificate.line(90, table_top - (18 * ii), width - 90, table_top - (18 * ii))

        for jj in range(n_columns + 1):
            certificate.line(90 + table_width * (jj / n_columns), table_top, 90 + table_width * (jj / n_columns),
                             table_bottom)

        # column titles
        certificate.setFont("Helvetica-Bold", 11.5)
        column_titles = ("Gebäudetyp", "EFH", "MFH", "Reihenhaus", "Block")
        for i in range(5):
            certificate.drawString(
                90 + table_width * (i / n_columns) + (((table_width / 5) - len(column_titles[i]) * 6.8) / 2),
                table_top - 14, column_titles[i])

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

        certificate.drawString((table_width * 2 / 5) + (((table_width / 5) - (EFH_values[0] - 5) * 6.8) / 2) - 8,
                               table_top - 14 - 18, str(EFH_values[0]))
        certificate.drawString((table_width * 3 / 5) + (((table_width / 5) - (MFH_values[0] - 5) * 6.8) / 2) - 8,
                               table_top - 14 - 18, str(MFH_values[0]))
        certificate.drawString((table_width * 4 / 5) + (((table_width / 5) - (RH_values[0] - 5) * 6.8) / 2) - 8,
                               table_top - 14 - 18, str(RH_values[0]))
        certificate.drawString((table_width) + (((table_width / 5) - (B_values[0] - 5) * 6.8) / 2) - 8,
                               table_top - 14 - 18, str(B_values[0]))

        for i in range(1, len(EFH_values)):
            certificate.drawString((table_width * 2 / 5) + ((table_width / 5) / 2) + 12.3 - (len(str(EFH_values[i])) * 6.5),
                                   table_top - 14 - 18 - (18 * i), str(EFH_values[i]))
            certificate.drawString((table_width * 2 / 5) + ((table_width / 5) / 2) + 16, table_top - 14 - 18 - (18 * i),
                                   "m\u00B2")
        for i in range(1, len(MFH_values)):
            certificate.drawString((table_width * 3 / 5) + ((table_width / 5) / 2) + 12.3 - (len(str(MFH_values[i])) * 6.5),
                                   table_top - 14 - 18 - (18 * i), str(MFH_values[i]))
            certificate.drawString((table_width * 3 / 5) + ((table_width / 5) / 2) + 16, table_top - 14 - 18 - (18 * i),
                                   "m\u00B2")
        for i in range(1, len(RH_values)):
            certificate.drawString((table_width * 4 / 5) + ((table_width / 5) / 2) + 12.3 - (len(str(RH_values[i])) * 6.5),
                                   table_top - 14 - 18 - (18 * i), str(RH_values[i]))
            certificate.drawString((table_width * 4 / 5) + ((table_width / 5) / 2) + 16, table_top - 14 - 18 - (18 * i),
                                   "m\u00B2")
        for i in range(1, len(B_values)):
            certificate.drawString((table_width) + ((table_width / 5) / 2) + 12.3 - (len(str(B_values[i])) * 6.5),
                                   table_top - 14 - 18 - (18 * i), str(B_values[i]))
            certificate.drawString((table_width) + ((table_width / 5) / 2) + 16, table_top - 14 - 18 - (18 * i),
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

        n_columns = 17
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
            "Gebäude ID", "Gebäudetyp", "Baujahr", "Sanierung", "Wohnfläche", "Heizung", "PV", "STC", "EV", "BAT",
            "fTES", "fBAT", "fEV", "fPV", "fSTC", "gammaPV ", "EV Charging")
            for i in range(len(column_titles)):
                certificate.drawString(54 + table_width * (i / n_columns) + (
                            ((table_width / len(column_titles)) - len(column_titles[i]) * 3.2) / 2), table_top - 11,
                                       column_titles[i])

            # add table values
            certificate.setFont("Helvetica", 6)
            for i in range(len(gebaeudeliste)):
                certificate.drawString((table_width / 17) + (((table_width / 17) - (len(str(i))) * 3.2) / 2) + 10,
                                       table_top - 11 - 18 - (18 * i), str(i))
                for j in range(16):
                    certificate.drawString((table_width * (j + 2) / 17) + (
                                ((table_width / 17) - (len(str(gebaeudeliste[i][j]))) * 3.2) / 2) + 10,
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

        else:

            for page in range(1, total_pages + 1, 1):

                if page != total_pages or len(gebaeudeliste) % 26 == 0:
                    for ii in range(n_rows + 1):
                        certificate.line(54, table_top - (18 * ii), width - 54, table_top - (18 * ii))
                    for jj in range(n_columns + 1):
                        certificate.line(54 + table_width * (jj / n_columns), table_top,
                                         54 + table_width * (jj / n_columns), table_bottom)

                    # add table values
                    certificate.setFont("Helvetica", 6)
                    for i in range(26):
                        certificate.drawString((table_width / 17) + (
                                    ((table_width / 17) - (len(str(i + (26 * (page - 1))))) * 3.2) / 2) + 10,
                                               table_top - 11 - 18 - (18 * i), str(i + (26 * (page - 1))))
                        for j in range(16):
                            certificate.drawString((table_width * (j + 2) / 17) + (((table_width / 17) - (
                                len(str(gebaeudeliste[i + (26 * (page - 1))][j]))) * 3.2) / 2) + 10,
                                                   table_top - 11 - 18 - (18 * i),
                                                   str(gebaeudeliste[i + (26 * (page - 1))][j]))

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
                    for i in range(n_rows - 1):
                        certificate.drawString((table_width / 17) + (
                                    ((table_width / 17) - (len(str(i + (26 * (page - 1))))) * 3.2) / 2) + 10,
                                               table_top - 11 - 18 - (18 * i), str(i + (26 * (page - 1))))
                        for j in range(16):
                            certificate.drawString((table_width * (j + 2) / 17) + (((table_width / 17) - (
                                len(str(gebaeudeliste[i + (26 * (page - 1))][j]))) * 3.2) / 2) + 10,
                                                   table_top - 11 - 18 - (18 * i),
                                                   str(gebaeudeliste[i + (26 * (page - 1))][j]))

                            # column titles
                certificate.setFont("Helvetica-Bold", 6)
                column_titles = (
                "Gebäude ID", "Gebäudetyp", "Baujahr", "Sanierung", "Wohnfläche", "Heizung", "PV", "STC", "EV", "BAT",
                "fTES", "fBAT", "fEV", "fPV", "fSTC", "gammaPV ", "EV Charging")
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

        # end page, continue to next page
        certificate.showPage()

        # swap page orientation back to portrait
        certificate.setPageSize((height, width))
        height, width = width, height

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
            "<b>Gebäudetyp:</b> SFH = Einfamilienhaus, MFH = Mehrfamilienhaus, AB = Wohnblock<br />"
            "<b>Baujahr:</b> Baualtersklasse (vor 1969, 1968-1978, 1979-1983, 1984-1994, 1995-2001, 2002-2009, "
            "2010-2015, ab 2016)<br />"
            "<b>Sanierung:</b> 0 = Bestand, 1 = Sanierung nach EnEV 2016, 2 = Sanierung nach KfW 55<br />"
            "<b>Wohnfläche:</b> Nettoraumfläche in m²<br />"
            "<b>Heizung:</b> ausgewählter Wärmeerzeuger<br />"
            "<b>PV:</b> 0 = Photovoltaic nicht vorhanden, 1 = Photovoltaic vorhanden<br />"
            "<b>STC:</b> 0 = Solarthermie nicht vorhanden, 1 = Solarthermie vorhanden<br />"
            "<b>EV:</b> 0 = Elektroauto nicht vorhanden, 1 = Elektroauto vorhanden<br />"
            "<b>BAT:</b> 0 = Batteriespeicher nicht vorhanden, 1 = Betteriespeicher vorhanden<br />"
            "<b>fTES:</b> Größe des Pufferspeichers in Liter<br />"
            "<b>fBAT:</b> Größe des Batteriespeichers in abhängigkeit der Leistung der PV-Anlage in Wh/W_PV<br />"
            "<b>fEV:</b> Größe des Batteriespeichers im Elektroauto in Wh<br />"
            "<b>fPV:</b> Anteil der Dachfläche, die mit Photovoltaic ausgestattet ist (Informationen zu Dachflächen "
            "sind den Typgebäuden nach Tabula zu entnehmen)<br />"
            "<b>fSTC:</b> Anteil der Dachfläche, die mit Solarthermie ausgestattet ist (Informationen zu Dachflächen "
            "sind den Typgebäuden nach Tabula zu entnehmen)<br />"
            "<b>gammaPV:</b> Azimut = Himmelsausrichtung der PV-Anlage, Ausrichtung nach Süden: 0°<br />"
            "<b>EV Charging:</b> Ladeverhalten des Elektroautos (bi-direktional: Be- und Entladung, Nutzung als "
            "Stromspeicher, on-demand: Beladung nach Bedarf, intelligent: optimierte Beladung)<br />",
            "Die hier angegebenen Werte basieren auf den rechnerischen Bedarfen auf Nutzerebene. "
            "Ein Anlagenbetrieb ist hier nicht berücksichtigt.<br />"
            "<b>Nutzenergiebedarf:</b> Über alle Gebäude aufsummierter Nutzenergiebedarf (Haushaltsstrom, Wärme, "
            "Trinkwarmwasser und Kälte)<br />"
            "<b>Norm-Heizlast:</b> Über alle Gebäude aufsummierte Norm-Heizlast nach DIN EN ISO 13790<br />"
            "<b>Solltemperatur:</b> Voreingestellte Solltemperatur für die Gebäude. Wird für die Berechnung der "
            "Wärmebedarfsprofile genutzt.<br />"
            "<b>Energiebedarfe (kWh):</b> Über alle Gebäude aufsummierten Jahresenergiebedarfe auf Basis der "
            "generierten Bedarfsprofile (für Wärme, Kälte, Haushaltsstrom und Trinkwarmwasser)<br />"
            "<b>Maximale Leistungen:</b> Maximale Leistungen in kW im Quartier auf Basis der aufsummierten "
            "Bedarfsprofile aller Gebäude (ohne Betriebsoptimierung)<br /><br />",
            "Die hier angegebenen Werte wurden nach einer Betriebsoptimierung unter Berücksichtigung aller "
            "definierten Anlagen (Erzeuger wie auch Speicher) im Quartier berechnet.<br />"
            "<b>CO2-äqui. Emissionen:</b> Im Quartier emittierte CO2-Äquivalente in t/a durch den optimierten "
            "Betrieb (Gasbedarf und Strombedarf)<br />"
            "<b>Energiekosten:</b> Spezifische Betriebskosten des gesamten Quartiers in €/kWh auf Basis der "
            "Betriebsoptimierung<br />"
            "<b>Spitzenlast (el.):</b> Maximaler Strombezug des gesamten Quartiers aus übergeordnetem "
            "Stromnetz auf Basis der Betriebsoptimierung<br />"
            "<b>Max. Einspeiseleistung:</b> Maximale Stromeinspeisung des gesamten Quartiers in "
            "übergeordnetes Stromnetz auf Basis der Betriebsoptimierung<br />"
            "<b>Supply-Cover-Faktor:</b> Anteil des im Quartier erzeugten Stroms am gesamten elektrischen "
            "Energiebedarf (typischerweise Werte zwischen 0 und 1; >1 steht für ein 'Plus-Energie-Quartier', "
            "dass mehr Sotrm erzeugt, als es verbaucht)<br />"
            "<b>Demand-Cover-Faktor:</b> Anteil des Strombedarfs, der durch im Quartier erzeugten Strom "
            "gedeckt wird (Werte zwischen 0 und 1)<br />"
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