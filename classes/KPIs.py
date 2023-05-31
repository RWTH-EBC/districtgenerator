# -*- coding: utf-8 -*-

import sys
import numpy as np
import os
import json


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
        self.residualLoad = None
        self.peakDemand = None
        self.peakInjection = None
        self.peakToValley = None
        self.demandCoverFactor = None
        self.supplyCoverFactor = None
        self.operationCosts = None
        self.co2emissions = None
        self.renewableElectricityGenerationFactor = None

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
        decentralDev = {}
        with open(os.path.join(srcPath, 'data', 'decentral_device_data.json')) as json_file:
            jsonData = json.load(json_file)
            for subData in jsonData:
                decentralDev[subData["abbreviation"]] = {}
                for subsubData in subData["specifications"]:
                    decentralDev[subData["abbreviation"]][subsubData["name"]] = subsubData["value"]

        for c in range(len(self.inputData["clusters"])):  # loop over cluster

            # electricity demand [kWh]
            electricityDemand_cluster_c = np.zeros(len(data.district[0]["user"].elec_cluster[c]))
            # demand of all buildings
            for b in data.scenario["id"]:
                electricityDemand_cluster_c += \
                    (data.district[b]["user"].elec_cluster[c]
                     + self.inputData["resultsOptimization"][c][b]["EV_ch"]
                     + self.inputData["resultsOptimization"][c][b]["HP_P_el"]
                     + self.inputData["resultsOptimization"][c][b]["EH_P_el"]) \
                    * data.time["timeResolution"] / 3600 / 1000
            # demand of central devices
            electricityDemand_cluster_c += \
                (np.array(self.inputData["resultsOptimization"][c]["centralDevices"]["HP_air_P_el_central"])
                 + self.inputData["resultsOptimization"][c]["centralDevices"]["HP_geo_P_el_central"]
                 + self.inputData["resultsOptimization"][c]["centralDevices"]["EH_P_el_central"]) \
                * data.time["timeResolution"] / 3600 / 1000
            electricityDemand_cluster.append(electricityDemand_cluster_c)

            # electricity generation [kWh]
            renewableGeneration_cumulated_c = 0
            electricityGeneration_cluster_c = 0
            # generation of buildings
            for b in data.scenario["id"]:
                electricityGeneration_cluster_c += \
                    (np.array(self.inputData["resultsOptimization"][c][b]["PV_P_el"])
                     + self.inputData["resultsOptimization"][c][b]["FC_P_el"]
                     + self.inputData["resultsOptimization"][c][b]["CHP_P_el"]) \
                    * data.time["timeResolution"] / 3600 / 1000
                renewableGeneration_cumulated_c += \
                    np.array(self.inputData["resultsOptimization"][c][b]["PV_P_el"]) \
                    * data.time["timeResolution"] / 3600 / 1000
            electricityGeneration_cluster_c += \
                (np.array(self.inputData["resultsOptimization"][c]["centralDevices"]["PV_P_el_central"])
                 + self.inputData["resultsOptimization"][c]["centralDevices"]["WT_P_el_central"]
                 + self.inputData["resultsOptimization"][c]["centralDevices"]["FC_P_el_central"]
                 + self.inputData["resultsOptimization"][c]["centralDevices"]["CHP_P_el_central"]) \
                * data.time["timeResolution"] / 3600 / 1000
            renewableGeneration_cumulated_c += \
                (np.array(self.inputData["resultsOptimization"][c]["centralDevices"]["PV_P_el_central"])
                 + self.inputData["resultsOptimization"][c]["centralDevices"]["WT_P_el_central"]) \
                * data.time["timeResolution"] / 3600 / 1000
            electricityGeneration_cluster.append(electricityGeneration_cluster_c)
            electricityGenerationRenewable_cluster.append(renewableGeneration_cumulated_c)

        ################################################################################################################

        # electricity generation for one year [kWh]
        electricityGeneration_year = 0
        for c in range(len(electricityGeneration_cluster)):  # loop over cluster
            electricityGeneration_c = sum(electricityGeneration_cluster[c])
            electricityGeneration_year += \
                electricityGeneration_c * self.inputData["clusterWeights"][self.inputData["clusters"][c]]
        self.inputData["electricityGeneration_year"] = electricityGeneration_year

        # renewable electricity generation for one year [kWh]
        renewableElectricityGeneration_year = 0
        for c in range(len(electricityGenerationRenewable_cluster)):  # loop over cluster
            renewableElectricityGeneration_c = sum(electricityGenerationRenewable_cluster[c])
            renewableElectricityGeneration_year += \
                renewableElectricityGeneration_c * self.inputData["clusterWeights"][self.inputData["clusters"][c]]
        self.inputData["renewableElectricityGeneration_year"] = renewableElectricityGeneration_year

        # electricity demand for one year [kWh]
        electricityDemand_year = 0
        for c in range(len(electricityDemand_cluster)):  # loop over cluster
            electricityDemand_c = sum(electricityDemand_cluster[c])
            electricityDemand_year += \
                electricityDemand_c * self.inputData["clusterWeights"][self.inputData["clusters"][c]]
        self.inputData["electricityDemand_year"] = electricityDemand_year

        # electricity demand from grid for one year [kWh]
        electricityDemandGCP_year = 0
        for c in range(len(self.inputData["resultsOptimization"])):  # loop over cluster
            electricityDemandGCP_c = sum(self.inputData["resultsOptimization"][c]["P_dem_gcp"]) \
                                     * data.time["timeResolution"] / 3600 / 1000
            electricityDemandGCP_year += \
                electricityDemandGCP_c * self.inputData["clusterWeights"][self.inputData["clusters"][c]]

        # self-consumption considering shift by battery [kWh]
        # requirement: same state of charge at beginning and end of clusters
        self.inputData["selfConsumption_year"] = electricityDemand_year - electricityDemandGCP_year

    def calculateResidualLoad(self):
        """
        Calculate residual load at grid connection point (GCP) in [kW].
        Demand is positive and injection negative.

        Returns
        -------
        None.
        """

        # compose residual load for one year from data of demand and injection for each cluster
        P_gcp = []
        for interval in range(self.inputData["nbIntervals"]):  # loop over intervals of the hole year (days/weeks/etc.)
            for clusterID in range(len(self.inputData["clusters"])):  # loop over cluster
                if interval in self.inputData["clusterAssignments"][self.inputData["clusters"][clusterID]]:
                    # append data of cluster representing current interval
                    P_gcp.append(np.array(self.inputData["resultsOptimization"][clusterID]["P_dem_gcp"])
                                 - np.array(self.inputData["resultsOptimization"][clusterID]["P_inj_gcp"]))
                    break

        # create array and change unit from [W] to [kW]
        self.residualLoad = np.array(P_gcp).flatten() / 1000

    def calculatePeakLoad(self):
        """
        Calculate peak demand and peak injection at grid connection point (GCP) in [kW].

        Returns
        -------
        None.
        """

        # maximal demand [kW]
        max_temp = max(self.residualLoad)
        if max_temp >= 0:
            self.peakDemand = round(max_temp, 3)
        else:
            self.peakDemand = 0

        # maximal injection [kW]
        min_temp = min(self.residualLoad)
        if min_temp <= 0:
            self.peakInjection = round(- min_temp, 3)
        else:
            self.peakInjection = 0

    def calculatePeakToValley(self):
        """
        Calculate the difference between the maximum and the minimum of the residual load in [kW].

        Returns
        -------
        None.
        """

        # peak to valley [kW]
        self.peakToValley = round(max(self.residualLoad) - min(self.residualLoad), 3)

    def calculateDemandCoverFactor(self):
        """
        Calculate the ratio between the self-consumed electricity and the total electricity demand.

        Returns
        -------
        None.
        """

        # How much of the electricity demand is covered by the self-generated electricity? [-]
        self.demandCoverFactor = \
            round(self.inputData["selfConsumption_year"] / self.inputData["electricityDemand_year"], 4)

    def calculateSupplyCoverFactor(self):
        """
        Calculate the ratio between the self-consumed electricity and the self-generated electricity.

        Returns
        -------
        None.
        """

        # How much of the self-generated electricity is used locally? [-]
        self.supplyCoverFactor = \
            round(self.inputData["selfConsumption_year"] / self.inputData["electricityGeneration_year"], 4)

    def calculateOperationCosts(self):
        """
        Calculate the operation cost for one year in [€].

        Returns
        -------
        None.
        """

        # list with central operation costs for each cluster [€]
        operationCosts_clusters = []
        for c in range(len(self.inputData["clusters"])):
            operationCosts_clusters.append(sum(self.inputData["resultsOptimization"][c]["C_total_central"]))

        # multiply central operation costs of each cluster with the weight of respective cluster
        temp_operationCosts = 0
        for c in range(len(self.inputData["clusters"])):
            temp_operationCosts \
                += operationCosts_clusters[c] * self.inputData["clusterWeights"][self.inputData["clusters"][c]]

        # central operation costs for one year [€]
        self.operationCosts = round(temp_operationCosts, 2)

    def calculateCO2emissions(self):
        """
        Calculate the CO2 emissions for one year in [kg].

        Returns
        -------
        None.
        """

        # list with CO2 emissions for each cluster [g]
        co2_clusters = []
        for c in range(len(self.inputData["clusters"])):
            co2_clusters.append(sum(self.inputData["resultsOptimization"][c]["Emi_total_central"]))

        # multiply CO2 emissions of each cluster with the weight of respective cluster
        temp_co2 = 0
        for c in range(len(self.inputData["clusters"])):
            temp_co2 += co2_clusters[c] * self.inputData["clusterWeights"][self.inputData["clusters"][c]]

        # CO2 emissions for one year; change unit from [g] to [kg]
        self.co2emissions = round(temp_co2 / 1000, 3)

    def calculateRenewableElectricityGenerationFactor(self):
        """
        Calculate the ratio between the renewable generated electricity and the total generated electricity.

        Returns
        -------
        None.
        """

        # How much of the self-generated electricity is renewable electricity? [-]
        self.renewableElectricityGenerationFactor = \
            round(self.inputData["renewableElectricityGeneration_year"] / self.inputData["electricityGeneration_year"],
                  4)

    def calculateAllKPIs(self):
        """
        Calculate all KPIs.

        Returns
        -------
        None.
        """

        self.calculateResidualLoad()
        self.calculatePeakLoad()
        self.calculatePeakToValley()
        self.calculateDemandCoverFactor()
        self.calculateSupplyCoverFactor()
        self.calculateOperationCosts()
        self.calculateCO2emissions()
        self.calculateRenewableElectricityGenerationFactor()
