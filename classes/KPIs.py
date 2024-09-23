# -*- coding: utf-8 -*-

import sys
import numpy as np
import os
import json
import reportlab
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.graphics.shapes import *
from reportlab.graphics.charts.piecharts import Pie
from datetime import datetime
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph


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
                co2_pv += np.sum(self.inputData["district"][id]["generationPV_cluster"][c, :]
                                 * data.time["timeResolution"] / 3600 / 1000) * CO2_factor_pv \
                          * self.inputData["clusterWeights"][self.inputData["clusters"][c]]


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

    def create_kpi_pdf(self,result_path):
        """
        Generate a PDF file with a list of KPIs.

        Parameters:
        - filename: The name of the PDF file to create.
        - title: The title of the document.
        - kpis: A list of strings, where each string is a KPI to be written in the document.
        """

    def create_certificate(kennwerte, opt_ergebnisse, struktur, gebaeudeliste):
        """
        Creates an energy certificate in PDF format for a neighborhood created via the EBC Quartiersgenerator.

        Args:
            kennwerte: a dictionary with the following keys (in order, formatted as strings), and all values formatted as
            strings with the corresponding units (unless otherwise specified):
                Primärenergiebedarf: primary energy demand of the district
                Endenergiebedarf: end energy demand of the district
                Norm-Heizlast insgesamt: the overall heat demand of the district
                Solltemperatur: set-point temperature of the buildings in the district
                Bedarfe: a TUPLE containing three values (float/int) for demands of electricity, heat, and water heating (in that order)
                Max. Leistungen: a TUPLE containing three values (float/int) for the maximum power of each energy type, in the order above

            opt_ergebnisse: a dictionary with the following keys (in order, formatted as strings), and all values formatted
            as strings with the corresponding units:
                CO2-äqui. Emissionen: CO2-equivalent emissions of the district
                Energiekosten: energy cost for the district
                Spitzenlast (el.) gesamt: peak load for the district
                Max. Einspeiseleistung gesamt: maximum feed-in power of the district
                Supply-Cover-Faktor: supply cover factor
                Demand-Cover-Faktor: demand cover factor

            struktur: a dictionary with the following keys (in order, formatted as strings) and and all values formatted as
            strings with the corresponding units (unless otherwise specified):
                EFH: a DICTIONARY containing the following keys and values pertaining to single-family homes in the district
                (keys formatted as strings, values formatted as strings including the relevant units):
                    Anzahl: the number of buildings of this type in the district
                    Gesamtfläche: the total floor space of these buildings (without unit!)
                    vor 1968: the total floor space of the buildings of this type built before 1968, in m^2 (without unit in string!)
                    1968-1979: the total floor space of the buildings of this type built between 1968 and 1979, in m^2 (without unit in string!)
                    1979-1983: the total floor space of the buildings of this type built between 1979 and 1983, in m^2 (without unit in string!)
                    1984-1994: the total floor space of the buildings of this type built between 1984 and 1994, in m^2 (without unit in string!)
                    1995-2001: the total floor space of the buildings of this type built between 1995 and 2001, in m^2 (without unit in string!)
                    2002-2009: the total floor space of the buildings of this type built between 2002 and 2009, in m^2 (without unit in string!)
                    2010-2015: the total floor space of the buildings of this type built between 2010 and 2015, in m^2 (without unit in string!)
                    ab 2016: the total floor space of the buildings of this type built since 2016, in m^2 (without unit in string!)
                MFH: a DICTIONARY formatted as specified above, with the values pertaining to multiple-family homes.
                Reihenhaus: a DICTIONARY formatted as specified above, with the values pertaining to townhouses.
                Block: a DICTIONARY formatted as specified above, with the values pertaining to block buildings.
                Wohnungen gesamt: number of households in the district
                Bewohner gesamt: number of residents in the district
                Nettowohnfläche gesamt: net living space in the district
                Standort (PLZ): the zip code of the district
                Testreferenzjahr: the reference year and reference weather conditions, formatted as "YYYY / warm"
                Quartiersname: the name of the district

            gebaeudeliste: a two-dimensional list, with each index corresponding to a building ID and the list in each index containing the following values:
                building: SFH, MFH, Townhouse, or Block
                year: year of construction
                retrofit: 1 (yes) or 0 (no)
                area: floor space
                heater: type of heating
                PV:
                STC:
                EV:
                BAT:
                f_TES:
                f_BAT:
                f_EV:
                f_PV:
                f_STC:
                gamma_PV:
                ev_charging:


        Returns:
            certificate: a PDF file diplaying the relevant information

        """
        # initialize certificate
        certificate = canvas.Canvas("certificate.pdf", pagesize=reportlab.lib.pagesizes.A4)
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
        certificate.setFont("Helvetica", 12)
        certificate.drawString(177, height - ((top3 + bottom3) / 2) - 4, struktur["Quartiersname"])
        today = datetime.now()
        certificate.drawString(400, height - ((top3 + bottom3) / 2) - 4,
                               "Erstellt am " + str(today.day) + "." + str(today.month) + "." + str(today.year))

        # filling in the first section
        # in the create_certificate function, the argument would be a dictionary of parameters and their values. this dictionary would be titled quartier_daten

        certificate.setFont("Helvetica", 12)
        content = tuple(kennwerte.keys())
        values = tuple(kennwerte.values())
        content = content[0:4]
        values = values[0:4]

        i = 0
        for item in content:
            certificate.drawString(85, height - top1 - 32 - (18 * i), item + ":")
            i = i + 1

        j = 0
        for value in values:
            certificate.drawString(240, height - top1 - 32 - (18 * j), str(value))
            j = j + 1

        bottom_kennwerte = top1 + 32 + 18 * j

        # create a subsection for optimization results, fill in the values

        certificate.setLineWidth(1)
        certificate.setLineCap(2)
        certificate.line(72, height - bottom_kennwerte, 325, height - bottom_kennwerte)
        certificate.line(325, height - bottom_kennwerte, 325, height - bottom1)

        certificate.setFont("Helvetica-Bold", 14)
        certificate.drawString(85, height - bottom_kennwerte - 25, "Optimierungsergebnisse")

        certificate.setFont("Helvetica", 12)
        opt_keys = tuple(opt_ergebnisse.keys())
        opt_values = tuple(opt_ergebnisse.values())

        i = 0
        for item in opt_keys:
            certificate.drawString(85, height - bottom_kennwerte - 50 - (18 * i), item + ":")
            i = i + 1

        j = 0
        for value in opt_values:
            certificate.drawString(260, height - bottom_kennwerte - 50 - (18 * j), str(value))
            j = j + 1

        # create graphics for the energy demands and maximum powers by energy type
        d = Drawing(300, 300)

        pc = Pie()
        pc.width = 90
        pc.height = 90
        pc.data = kennwerte["Bedarfe"]
        pc.labels = ['Strom: ' + str(pc.data[0]), 'Wärme: ' + str(pc.data[1]), 'TWW: ' + str(pc.data[2])]

        pc.slices.strokeWidth = 1
        pc.slices.labelRadius = 1.5
        pc.slices.fontName = "Helvetica"
        pc.slices.strokeColor = colors.white

        pc.slices[0].fillColor = colors.Color(0 / 256, 85 / 256, 31 / 256)
        pc.slices[1].fillColor = colors.Color(134 / 256, 169 / 256, 26 / 256)
        pc.slices[2].fillColor = colors.Color(122 / 256, 186 / 256, 214 / 256)

        d.add(pc)

        d.drawOn(certificate, (width / 2) + 80, height - top1 - 120)

        certificate.setFont("Helvetica-Bold", 14)
        certificate.drawString(340, height - top1 - 20, "Energiebedarfe (kWh)")

        max_leistungen = kennwerte["Max. Leistungen"]
        leist_labels = ("Strom: ", "Wärme: ", "TWW: ")

        ML_top = 265

        certificate.drawString(340, height - ML_top, "Maximale Leistungen")

        certificate.setStrokeColorRGB(54 / 256, 132 / 256, 39 / 256)
        certificate.setLineWidth(5)
        certificate.setLineCap(2)
        certificate.setFont("Helvetica", 12)

        for i in range(len(max_leistungen)):
            certificate.drawString(340, height - ML_top - 25 - (20 * i), leist_labels[i])
            certificate.line(390, height - ML_top - 21 - (20 * i), 390 + (5 * max_leistungen[i]),
                             height - ML_top - 21 - (20 * i))
            certificate.drawString(400 + (5 * max_leistungen[i]), height - ML_top - 25 - (20 * i),
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

        certificate.drawString((table_width * 2 / 5) + (((table_width / 5) - (len(EFH_values[0]) - 5) * 6.8) / 2) - 8,
                               table_top - 14 - 18, EFH_values[0])
        certificate.drawString((table_width * 3 / 5) + (((table_width / 5) - (len(MFH_values[0]) - 5) * 6.8) / 2) - 8,
                               table_top - 14 - 18, MFH_values[0])
        certificate.drawString((table_width * 4 / 5) + (((table_width / 5) - (len(RH_values[0]) - 5) * 6.8) / 2) - 8,
                               table_top - 14 - 18, RH_values[0])
        certificate.drawString((table_width) + (((table_width / 5) - (len(B_values[0]) - 5) * 6.8) / 2) - 8,
                               table_top - 14 - 18, B_values[0])

        for i in range(1, len(EFH_values)):
            certificate.drawString((table_width * 2 / 5) + ((table_width / 5) / 2) + 12.3 - (len(EFH_values[i]) * 6.5),
                                   table_top - 14 - 18 - (18 * i), EFH_values[i])
            certificate.drawString((table_width * 2 / 5) + ((table_width / 5) / 2) + 16, table_top - 14 - 18 - (18 * i),
                                   "m\u00B2")
        for i in range(1, len(MFH_values)):
            certificate.drawString((table_width * 3 / 5) + ((table_width / 5) / 2) + 12.3 - (len(MFH_values[i]) * 6.5),
                                   table_top - 14 - 18 - (18 * i), MFH_values[i])
            certificate.drawString((table_width * 3 / 5) + ((table_width / 5) / 2) + 16, table_top - 14 - 18 - (18 * i),
                                   "m\u00B2")
        for i in range(1, len(RH_values)):
            certificate.drawString((table_width * 4 / 5) + ((table_width / 5) / 2) + 12.3 - (len(RH_values[i]) * 6.5),
                                   table_top - 14 - 18 - (18 * i), RH_values[i])
            certificate.drawString((table_width * 4 / 5) + ((table_width / 5) / 2) + 16, table_top - 14 - 18 - (18 * i),
                                   "m\u00B2")
        for i in range(1, len(B_values)):
            certificate.drawString((table_width) + ((table_width / 5) / 2) + 12.3 - (len(B_values[i]) * 6.5),
                                   table_top - 14 - 18 - (18 * i), B_values[i])
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
        terms = ["First Term", "Second Term", "Third Term"]
        details = [
            "This text represents the details about the first term. It's a relatively long text, in order to test whether or not the text wrapping works as intended. With luck, the paragraph will continue into the next line while maintaining its format and will also determine the placement of the following term with its details.",
            "This text provides details about the second term. It is shorter than the first text, but hopefully still long enough to wrap onto a second line.",
            "This text provides details about the third term."
            ]

        details_Style = ParagraphStyle('My Para style',
                                       fontName='Helvetica',
                                       fontSize=10,
                                       alignment=0,
                                       leftIndent=20,
                                       firstLineIndent=-20
                                       )

        term_height = height - 72

        for i in range(len(terms)):
            p = Paragraph("<b>" + terms[i] + ":</b> " + details[i], details_Style)
            p.wrap(width - 144, term_height)
            num_lines = len(p.blPara.lines)
            term_height = term_height - num_lines * 10
            p.drawOn(certificate, 72, term_height)
            term_height = term_height - 15

        # save certificate
        certificate.save()
