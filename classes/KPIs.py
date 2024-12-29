# -*- coding: utf-8 -*-

import sys
import numpy as np
import os
import json
import math

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
        self.annual_investment_total = None

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
        self.prepareData(data)
        self.calculateResidualLoad(data)
        self.calculatePeakLoad()
        self.calculatePeakToValley()
        self.calculateEnergyExchangeGCP(data)
        self.calculateEnergyExchangeWithinDistrict(data)
        self.calculateAutonomy()
        self.calculateCoverFactors(data)
        self.calc_annual_cost_total(data.scenario)

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
        decentralDev = {}
        with open(os.path.join(srcPath, 'data', 'decentral_device_data.json')) as json_file:
            jsonData = json.load(json_file)
            for subData in jsonData:
                decentralDev[subData["abbreviation"]] = {}
                for subsubData in subData["specifications"]:
                    decentralDev[subData["abbreviation"]][subsubData["name"]] = subsubData["value"]

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

        # How much of the electricity demand is covered by the self-generated electricity? [-]


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

    def calc_annual_cost_total(self, scenario):

        optiData = {}
        optiData["HP"] = {}
        optiData["HP"]["cap"] = 20 # kW
        optiData["HP"]["life_time"] = 15
        optiData["HP"]["inv_var"] = 900 # €/kW
        optiData["HP"]["cost_om"] = 0.05

        optiData["param"] = {}
        optiData["param"]["observation_time"] = 20
        optiData["param"]["interest_rate"] = 0.05

        # Count occurrences of "BOI", "HP", and "CHP" in the 'heater' column
        heater_counts = scenario['heater'].value_counts()

        # Sum the values in the 'PV', 'STC', 'EV', and 'BAT' columns
        heater_counts["PV"] = scenario['PV'].sum()
        heater_counts["STC"] = scenario['STC'].sum()
        heater_counts["EV"] = scenario['EV'].sum()
        heater_counts["BAT"] = scenario['BAT'].sum()

        calc_annual_investment = {}
        for dev in ["BOI", "HP", "CHP", "PV", "STC", "EV", "BAT"]:
            calc_annual_investment[dev] = {}
            try:
                if heater_counts[dev] > 0:
                    calc_annual_investment[dev] = self.calc_annual_cost_device(optiData["HP"], optiData["param"])
                else: calc_annual_investment[dev] = 0
            except:
                calc_annual_investment[dev] = 0
                heater_counts[dev] = 0

        self.annual_investment_total = calc_annual_investment["BOI"] * heater_counts["BOI"] \
                                  + calc_annual_investment["HP"] * heater_counts["HP"] \
                                  + calc_annual_investment["CHP"] * heater_counts["CHP"] \
                                  + calc_annual_investment["PV"] * heater_counts["PV"] \
                                  + calc_annual_investment["STC"] * heater_counts["STC"] \
                                  + calc_annual_investment["EV"] * heater_counts["EV"] \
                                  + calc_annual_investment["BAT"] * heater_counts["BAT"]
    def calc_annual_cost_device(self, dev, param):
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
        # Lebensdauer [Jahre]
        # Betriebs- und Wartungskosten [% of Invest]
        # Defaultwerte aus Technikkatalog KKW (Moritz, Nico)

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
        inv = dev["inv_var"] * dev["cap"]
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

    def calculateCO2emissions(self, data):
        """
        Calculate the CO2 emissions for one year in [kg].

        Returns
        -------
        None.
        """

        filePath = os.path.join(data.srcPath, 'data')
        # important for weather conditions
        with open(os.path.join(filePath, 'eco_data.json')) as json_file:
            jsonData = json.load(json_file)

        CO2_factor_el_grid = jsonData[3]["value"]  # Emi_elec_grid
        CO2_factor_gas = jsonData[4]["value"]      # Emi_gas
        CO2_factor_pv = jsonData[5]["value"]       # Emi_pv

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
        Returns
        -------
        None.
        """
        LOLP = np.zeros(len(self.inputData["clusters"]))
        self.EnergyAutonomy = np.zeros(len(self.inputData["clusters"]))

        # loop over cluster
        for c in range(len(self.inputData["clusters"])):
            y = 0
            for t in range(len(self.residualLoad[c])):
                if self.residualLoad[c, t] > 0:
                    y += 1
                else:
                    y += 0
            LOLP[c] = y / len(self.residualLoad[c])
        self.EnergyAutonomy = np.array([1,1,1,1]) - LOLP

        self.EnergyAutonomy_year = 0
        sum_ClusterWeights = 0
        ## loop over cluster
        for c in range(len(self.inputData["clusters"])):
            sum_ClusterWeights += self.inputData["clusterWeights"][self.inputData["clusters"][c]]
        #for c in range(len(self.inputData["clusters"])):
        #    self.EnergyAutonomy_year += EnergyAutonomy[c] * (self.inputData["clusterWeights"][self.inputData["clusters"][c]]
        #                                                  / sum_ClusterWeights)

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
        self.calculateCO2emissions(data)
        self.calculateAutonomy()
        self.calc_annual_cost_total(data.scenario)
