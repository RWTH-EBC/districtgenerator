# -*- coding: utf-8 -*-

import json
import pickle
import os
import sys
import copy
import datetime
import numpy as np
import openpyxl
import pandas as pd
import matplotlib.pyplot as plt
from itertools import count
from teaser.project import Project
from classes.envelope import Envelope
from classes.solar import Sun
from classes.users import Users
from classes.system import BES
from classes.system import CES
from classes.plots import DemandPlots
from classes.optimizer import Optimizer
from classes.KPIs import KPIs
import functions.clustering_medoid as cm
import functions.wind_turbines as wind_turbines
import EHDO.load_params as load_params_EHDO
import EHDO.optim_model as optim_model_EHDO


class Datahandler:
    """
    Abstract class for data handling.
    Collects data from input files, TEASER, User and Envelope.

    Attributes
    ----------
    site:
        Dict for site data, e.g. weather.
    time:
        Dict for time settings.
    district:
        List of all buildings within district.
    scenario_name:
        Name of scenario file.
    scenario:
        Scenario data.
    counter:
        Dict for counting number of equal building types.
    srcPath:
        Source path.
    filePath:
        File path.
    """

    def __init__(self):
        """
        Constructor of Datahandler class.

        Returns
        -------
        None.
        """

        self.site = {}
        self.time = {}
        self.district = []
        self.scenario_name = None
        self.scenario = None
        self.counter = {}
        self.outputV1 = {}
        self.outputV2 = {}
        self.srcPath = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.filePath = os.path.join(self.srcPath, 'data')
        self.resultPath = os.path.join(self.srcPath, 'results')
        self.KPIs = None

    def select_plz_data(self, plz):
        """
        Select the closest TRY weather station for the location of the postal code.

        Parameters
        ----------
        plz: string
            Postal code of the district generated.

        Returns
        -------
        weatherdatafile_location: int
            Location of the TRY weather station in lambert projection.
        """

        # Try to find the location of the postal code and matched TRY weather station
        try:
            print("################################")
            print(self.filePath)
            workbook = openpyxl.load_workbook(self.filePath + "/plz_geocoord_matched.xlsx")
            sheet = workbook.active

            for row in sheet.iter_rows(values_only=True):
                print(row)

                if plz == str(row[0]):
                    latitude = row[4]
                    longitude = row[5]
                    weatherdatafile = row[3]
                    weatherdatafile_location = weatherdatafile[8:-9]
                    break
            else:
                # If postal code cannot be found: Message and select weather data file from Aachen
                raise ValueError("Postal code cannot be found")


        except Exception as e:
            # If postal code cannot be found: Message and select weathter data file from Aachen
            print("Postal code cannot be found, location changed to Aachen")
            weatherdatafile_location = 37335002675500

        return weatherdatafile_location

    def generateEnvironment(self, plz):
        """
        Load physical district environment - site and weather.

        Returns
        -------
        None.
        """

        # %% load information about of the site under consideration
        # important for weather conditions
        with open(os.path.join(self.filePath, 'site_data.json')) as json_file:
            jsonData = json.load(json_file)
            for subData in jsonData:
                self.site[subData["name"]] = subData["value"]

        # %% load weather data for site
        # extract irradiation and ambient temperature
        if self.site["TRYYear"] == "TRY2015":
            first_row = 35
        elif self.site["TRYYear"] == "TRY2045":
            first_row = 37

        # select the correct file depending on the TRY weather station location
        weatherData = np.loadtxt(
            os.path.join(self.filePath, 'weather', "TRY_" + self.site["TRYYear"][-4:] + "_" + self.site["TRYType"],
                         self.site["TRYType"])
            + "/"
            + self.site["TRYYear"] + "_"
            + str(self.select_plz_data(plz)) + "_" + str(self.site["TRYType"])
            + ".dat",
            skiprows=first_row - 1)

        """
        # Use this function to load old TRY-weather data
        weatherData = np.loadtxt(os.path.join(self.filePath, 'weather')
                                 + "/"
                                 + self.site["TRYYear"] + "_Zone"
                                 + str(self.site["climateZone"]) + "_"
                                 + self.site["TRYType"] + ".txt",
                                 skiprows=first_row - 1)"""

        # weather data starts with 1st january at 1:00 am.
        # Add data point for 0:00 am to be able to perform interpolation.
        weatherData_temp = weatherData[-1:, :]
        weatherData = np.append(weatherData_temp, weatherData, axis=0)

        # get weather data of interest
        [temp_sunDirect, temp_sunDiff, temp_temp, temp_wind] = \
            [weatherData[:, 12], weatherData[:, 13], weatherData[:, 5], weatherData[:, 8]]

        # %% load time information and requirements
        # needed for data conversion into the right time format
        with open(os.path.join(self.filePath, 'time_data.json')) as json_file:
            jsonData = json.load(json_file)
            for subData in jsonData:
                self.time[subData["name"]] = subData["value"]
        self.time["timeSteps"] = int(self.time["dataLength"] / self.time["timeResolution"])

        # interpolate input data to achieve required data resolution
        # transformation from values for points in time to values for time intervals
        self.site["SunDirect"] = np.interp(np.arange(0, self.time["dataLength"] + 1, self.time["timeResolution"]),
                                           np.arange(0, self.time["dataLength"] + 1, self.time["dataResolution"]),
                                           temp_sunDirect)[0:-1]
        self.site["SunDiffuse"] = np.interp(np.arange(0, self.time["dataLength"] + 1, self.time["timeResolution"]),
                                            np.arange(0, self.time["dataLength"] + 1, self.time["dataResolution"]),
                                            temp_sunDiff)[0:-1]
        self.site["T_e"] = np.interp(np.arange(0, self.time["dataLength"] + 1, self.time["timeResolution"]),
                                     np.arange(0, self.time["dataLength"] + 1, self.time["dataResolution"]),
                                     temp_temp)[0:-1]
        self.site["wind_speed"] = np.interp(np.arange(0, self.time["dataLength"] + 1, self.time["timeResolution"]),
                                            np.arange(0, self.time["dataLength"] + 1, self.time["dataResolution"]),
                                            temp_wind)[0:-1]

        self.site["SunTotal"] = self.site["SunDirect"] + self.site["SunDiffuse"]

        # Calculate solar irradiance per surface direction - S, W, N, E, Roof represented by angles gamma and beta
        global sun
        sun = Sun(filePath=self.filePath)
        self.SunRad = sun.getSolarGains(initialTime=0,
                                        timeDiscretization=self.time["timeResolution"],
                                        timeSteps=self.time["timeSteps"],
                                        timeZone=self.site["timeZone"],
                                        location=self.site["location"],
                                        altitude=self.site["altitude"],
                                        beta=[90, 90, 90, 90, 0],
                                        gamma=[0, 90, 180, 270, 0],
                                        beamRadiation=self.site["SunDirect"],
                                        diffuseRadiation=self.site["SunDiffuse"],
                                        albedo=self.site["albedo"])

    # def initializeBuildings(self, scenario_name='example'):
    def initializeBuildings(self, list_all: list = None, scenario_name='example'):
        """
        Fill district with buildings from scenario file.

        Parameters
        ----------
        scenario_name: string, optional
            Name of scenario file to be read. The default is 'example'.

        Returns
        -------
        None.
        """
        duration = datetime.timedelta(minutes=1)
        num_sfh = 0
        num_mfh = 0
        self.scenario_name = scenario_name
        if list_all is not None:
            self.scenario = pd.DataFrame(list_all, columns=['id', 'type', 'year', 'condition', 'area'])
        else:
            self.scenario = pd.read_csv(os.path.join(self.filePath, 'scenarios')
                                        + "/"
                                        + self.scenario_name + ".csv",
                                        header=0, delimiter=";")

        for id, entry in enumerate(list_all):
            list = list_all[id]
            building = {}
            building["buildingFeatures"] = pd.Series(
                [list[0], list[1], list[2], list[3], list[4], 3, 1, 2, 3, 1, 2, 3, 1, 2, 3, 1],
                index=['id', 'building', 'year', 'retrofit', 'area', 'heater', 'PV',
                       'STC', 'EV', 'BAT', 'f_TES', 'f_BAT', 'f_EV', 'f_PV', 'f_STC',
                       'gamma_PV', ])

            self.district.append(building)

            if building["buildingFeatures"]["building"] == 'SFH' or building["buildingFeatures"]["building"] == 'TH':
                num_sfh += 1
            elif building["buildingFeatures"]["building"] == 'MFH' or building["buildingFeatures"]["building"] == 'AB':
                num_mfh += 1

        # Calculate calculation time for the whole district generation
        duration += datetime.timedelta(seconds=3 * num_sfh + 12 * num_mfh)
        print("This calculation will take about " + str(duration) + " .")

    def generateBuildings(self):
        """
        Load building envelope and user data.

        Returns
        -------
        None.
        """

        # %% load general building information
        # contains definitions and parameters that affect all buildings
        bldgs = {}
        with open(os.path.join(self.filePath, 'design_building_data.json')) as json_file:
            jsonData = json.load(json_file)
            for subData in jsonData:
                bldgs[subData["name"]] = subData["value"]

        # %% create TEASER project
        # create one project for the whole district
        prj = Project(load_data=True)
        prj.name = self.scenario_name

        for building in self.district:
            # convert short names into designation needed for TEASER
            building_type = \
                bldgs["buildings_long"][bldgs["buildings_short"].index(building["buildingFeatures"]["building"])]
            retrofit_level = \
                bldgs["retrofit_long"][bldgs["retrofit_short"].index(building["buildingFeatures"]["retrofit"])]

            # add buildings to TEASER project
            prj.add_residential(method='tabula_de',
                                usage=building_type,
                                name="ResidentialBuildingTabula",
                                year_of_construction=building["buildingFeatures"]["year"],
                                number_of_floors=3,
                                height_of_floors=3.125,
                                net_leased_area=building["buildingFeatures"]["area"] * bldgs["ratio_area"][
                                    bldgs["buildings_short"].index(building["buildingFeatures"]["building"])],
                                construction_type=retrofit_level)

            # %% create envelope object
            # containing all physical data of the envelope
            building["envelope"] = Envelope(prj=prj,
                                            building_params=building["buildingFeatures"],
                                            construction_type=retrofit_level,
                                            file_path=self.filePath)

            # %% create user object
            # containing number occupants, electricity demand,...
            building["user"] = Users(building=building["buildingFeatures"]["building"],
                                     area=building["buildingFeatures"]["area"])

            index = bldgs["buildings_short"].index(building["buildingFeatures"]["building"])
            building["buildingFeatures"]["mean_drawoff_dhw"] = bldgs["mean_drawoff_vol_per_day"][index]

    def generateDemands(self, calcUserProfiles=True, saveUserProfiles=True):
        """
        Generate occupancy profile, heat demand, domestic hot water demand and heating demand.

        Parameters
        ----------
        calcUserProfiles: bool, optional
            True: calculate new user profiles.
            False: load user profiles from file.
            The default is True.
        saveUserProfiles: bool, optional
            True for saving calculated user profiles in workspace (Only taken into account if calcUserProfile is True).
            The default is True.

        Returns
        -------
        None.
        """

        district_heat = np.zeros(self.time["timeSteps"])
        district_cooling = np.zeros(self.time["timeSteps"])
        district_elec = np.zeros(self.time["timeSteps"])
        district_dhw = np.zeros(self.time["timeSteps"])

        set = []
        for building in self.district:

            # %% create unique building name
            # needed for loading and storing data with unique name
            # name is composed of building type, number of flats, serial number of building of this properties
            name = building["buildingFeatures"]["building"] + "_" + str(building["user"].nb_flats)
            if name not in set:
                set.append(name)
                self.counter[name] = count()
            nb = next(self.counter[name])

            building["unique_name"] = name + "_" + str(nb)
            self.outputV1[building["unique_name"]] = {}

            # calculate or load user profiles
            if calcUserProfiles:
                building["user"].calcProfiles(site=self.site,
                                              time_resolution=self.time["timeResolution"],
                                              time_horizon=self.time["dataLength"],
                                              building=building,
                                              path=os.path.join(self.filePath, 'demands'))

                if saveUserProfiles:
                    building["user"].saveProfiles(building["unique_name"], os.path.join(self.resultPath, 'demands'))

                print("Calculate demands of building " + building["unique_name"])

            else:
                building["user"].loadProfiles(building["unique_name"], os.path.join(self.resultPath, 'demands'))
                print("Load demands of building " + building["unique_name"])

            # check if EV exist
            building["clusteringData"] = {
                "potentialEV": copy.deepcopy(building["user"].car)
            }
            building["user"].car *= building["buildingFeatures"]["EV"]

            building["envelope"].calcNormativeProperties(self.SunRad, building["user"].gains)

            # calculate heating profiles
            building["user"].calcHeatingProfile(site=self.site,
                                                envelope=building["envelope"],
                                                time_resolution=self.time["timeResolution"])

            if saveUserProfiles:
                building["user"].saveHeatingProfile(building["unique_name"], os.path.join(self.resultPath, 'demands'))

            self.outputV1[building["unique_name"]]["heat"] = building["user"].getProfiles()[0]
            self.outputV1[building["unique_name"]]["cooling"] = building["user"].getProfiles()[1]
            self.outputV1[building["unique_name"]]["elec"] = building["user"].getProfiles()[2]
            self.outputV1[building["unique_name"]]["dhw"] = building["user"].getProfiles()[3]

            district_heat += building["user"].getProfiles()[0]
            district_cooling += building["user"].getProfiles()[1]
            district_elec += building["user"].getProfiles()[2]
            district_dhw += building["user"].getProfiles()[3]

        self.outputV1.update({
            'district_heat': district_heat,
            'district_cooling': district_cooling,
            'district_elec': district_elec,
            'district_dhw': district_dhw,
        })

        if saveUserProfiles:
            np.savetxt(os.path.join(self.resultPath, 'demands') + '/cooling_district.csv', district_cooling,
                       fmt='%1.2f', delimiter=',')
            np.savetxt(os.path.join(self.resultPath, 'demands') + '/heating_district.csv', district_heat, fmt='%1.2f',
                       delimiter=',')
            np.savetxt(os.path.join(self.resultPath, 'demands') + '/dhw_district.csv', district_dhw, fmt='%1.2f',
                       delimiter=',')
            np.savetxt(os.path.join(self.resultPath, 'demands') + '/elec_district.csv', district_elec, fmt='%1.2f',
                       delimiter=',')

        print("Finished generating demands!")

    def outputWebtoolV1(self):
        #    for i in range(len(self.district)):
        #        self.outputV1[i] = {}
        #        self.outputV1[i]["heat"] = self.district[i]["user"]["heat"]
        #        self.outputV1[i]["cooling"] = self.district[i]["user"]["cooling"]
        #        self.outputV1[i]["dhw"] = self.district[i]["user"]["dhw"]
        #        self.outputV1[i]["elec"] = self.district[i]["user"]["elec"]
        return self.outputV1

    def generateDistrictComplete(self, scenario_name='example', building_list: list = [], calcUserProfiles=True,
                                 saveUserProfiles=True, plz='52064',
                                 fileName_centralSystems="central_devices_example", saveGenProfiles=True,
                                 designDevs=False, clustering=False, optimization=False):
        """
        All in one solution for district and demand generation.

        Parameters
        ----------
        scenario_name: string, optional
            Name of scenario file to be read. The default is 'example'.
        calcUserProfiles: bool, optional
            True: calculate new user profiles.
            False: load user profiles from file.
            The default is True.
        saveUserProfiles: bool, optional
            True for saving calculated user profiles in workspace (Only taken into account if calcUserProfile is True).
            The default is True.
        plz: string
            Postal code of the district
        fileName_centralSystems : string, optional
            File name of the CSV-file that will be loaded. The default is "central_devices_test".
        saveGenProfiles: bool, optional
            Decision if generation profiles of designed devices will be saved. Just relevant if 'designDevs=True'.
            The default is True.
        designDevs: bool, optional
            Decision if devices will be designed. The default is False.
        clustering: bool, optional
            Decision if profiles will be clustered. The default is False.
        optimization: bool, optional
            Decision if the operation costs for each cluster will be optimized. The default is False.

        Returns
        -------
        None.
        """

        self.initializeBuildings(building_list, scenario_name)
        self.generateEnvironment(plz)
        self.generateBuildings()
        self.generateDemands(calcUserProfiles, saveUserProfiles)
        if designDevs:
            self.designDevicesComplete(fileName_centralSystems, saveGenProfiles)
        if clustering:
            if designDevs:
                self.clusterProfiles()
            else:
                print("Clustering is not possible without the design of energy conversion devices!")
        if optimization:
            if designDevs and clustering:
                self.optimizationClusters()
            else:
                print("Optimization is not possible without clustering and the design of energy conversion devices!")

    def designDecentralDevices(self, input_webtool: dict, saveGenerationProfiles=True):
        """
        Calculate capacities, generation profiles of renewable energies and EV load profiles for decentral devices.

        Parameters
        ----------
        saveGenerationProfiles : bool, optional
            True: save decentral PV and STC profiles as CSV-file.
            False: don't save decentral PV and STC profiles as CSV-file.
            The default is True.

        Returns
        -------
        None.
        """

        for building in self.district:

            building["buildingFeatures"]["heater"] = input_webtool[building["buildingFeatures"]["id"]]["heater"]  # str
            building["buildingFeatures"]["f_TES"] = input_webtool[building["buildingFeatures"]["id"]][
                "tes_input"]  # liter

            building["buildingFeatures"]["PV_area"] = input_webtool[building["buildingFeatures"]["id"]][
                "pv_input"]  # m2
            if building["buildingFeatures"]["PV_area"] > 0:
                building["buildingFeatures"]["PV"] = 1
            else:
                building["buildingFeatures"]["PV"] = 0
            building["buildingFeatures"]["BAT"] = input_webtool[building["buildingFeatures"]["id"]]["bat_input"]  # Wh

            building["buildingFeatures"]["STC_area"] = input_webtool[building["buildingFeatures"]["id"]][
                "stc_input"]  # m2
            if building["buildingFeatures"]["STC_area"] > 0:
                building["buildingFeatures"]["STC"] = 1
            else:
                building["buildingFeatures"]["STC"] = 0

            building["buildingFeatures"]["EV"] = input_webtool[building["buildingFeatures"]["id"]][
                "ev_input"]  # S, M, L

            # %% load general building information
            # contains definitions and parameters that affect all buildings
            bldgs = {}
            with open(os.path.join(self.filePath, 'design_building_data.json')) as json_file:
                jsonData = json.load(json_file)
                for subData in jsonData:
                    bldgs[subData["name"]] = subData["value"]

            # %% calculate design heat loads
            # at norm outside temperature
            building["heatload"] = building["envelope"].calcHeatLoad(site=self.site, method="design")
            # at bivalent temperature
            building["bivalent"] = building["envelope"].calcHeatLoad(site=self.site, method="bivalent")
            # at heating limit temperature
            building["heatlimit"] = building["envelope"].calcHeatLoad(site=self.site, method="heatlimit")
            # for drinking hot water
            building["dhwload"] = \
                bldgs["dhwload"][bldgs["buildings_short"].index(building["buildingFeatures"]["building"])] * \
                building["user"].nb_flats

            # %% create building energy system object
            # get capacities of all possible devices
            bes_obj = BES(file_path=self.filePath)
            building["capacities"] = bes_obj.designECS(building, self.site)

            # calculate theoretical PV generation

            sun = Sun(filePath=self.filePath)

            f_PV = building["buildingFeatures"]["PV_area"] / (
                        building["buildingFeatures"]["PV_area"] + building["buildingFeatures"]["STC_area"] )
            f_STC = building["buildingFeatures"]["PV_area"] / (
                        building["buildingFeatures"]["PV_area"] + building["buildingFeatures"]["STC_area"])

            potentialPV, potentialSTC = \
                sun.calcPVAndSTCProfile(time=self.time,
                                        site=self.site,
                                        #area_roof=building["envelope"].A["opaque"]["roof"],
                                        area_roof=building["buildingFeatures"]["PV_area"] + building["buildingFeatures"]["STC_area"] ,
                                        beta=[35],
                                        gamma=[building["buildingFeatures"]["gamma_PV"]],
                                        #usageFactorPV=building["buildingFeatures"]["f_PV"],
                                        #usageFactorSTC=building["buildingFeatures"]["f_STC"])
                                        usageFactorPV = f_PV,
                                        usageFactorSTC = f_STC)

            # assign real PV generation to building
            building["generationPV"] = potentialPV * building["buildingFeatures"]["PV"]

            # assign real STC generation to building
            building["generationSTC"] = potentialSTC * building["buildingFeatures"]["STC"]

            # clustering data
            building["clusteringData"]["potentialPV"] = potentialPV
            building["clusteringData"]["potentialSTC"] = potentialSTC

            # optionally save generation profiles
            if saveGenerationProfiles == True:
                np.savetxt(os.path.join(self.resultPath, 'renewableGeneration')
                           + '/decentralPV_' + building["unique_name"] + '.csv',
                           building["generationPV"],
                           delimiter=',')
                np.savetxt(os.path.join(self.resultPath, 'renewableGeneration')
                           + '/decentralSTC_' + building["unique_name"] + '.csv',
                           building["generationSTC"],
                           delimiter=',')

        print("done with optimizing")

    def designCentralDevices(self, input_webtool, central_scenario="central_devices_example",
                             saveGenerationProfiles=True, ):
        """
        Calculate capacities and generation profiles of renewable energies for central devices.

        Parameters
        ----------
        saveGenerationProfiles : bool, optional
            True: save central PV, STC and WT profiles as CSV-file.
            False: don't save central PV, STC and WT profiles as CSV-file.
            The default is True.


        Returns
        -------
        None.
        """

        # initialization
        self.centralDevices = {}

        # initialize central energy system object
        self.centralDevices["ces_obj"] = CES()

        demands_district = {}
        demands_district["heat"] = np.loadtxt(os.path.join(self.resultPath, 'demands') + '/heating_district.csv',
                                              delimiter=',')
        demands_district["cooling"] = np.loadtxt(os.path.join(self.resultPath, 'demands') + '/cooling_district.csv',
                                                 delimiter=',')
        demands_district["dhw"] = np.loadtxt(os.path.join(self.resultPath, 'demands') + '/dhw_district.csv',
                                             delimiter=',')
        demands_district["elec"] = np.loadtxt(os.path.join(self.resultPath, 'demands') + '/elec_district.csv',
                                              delimiter=',')

        # Load parameters
        param, devs, dem, result_dict = load_params_EHDO.load_params(self, demands_district)

        # Input from webtool of devs (feasible = True/False, min/max cap, ....)
        devs = self.centralDevices["ces_obj"].designCES(self, demands_district, devs, input_webtool)

        # load data about central devices from JSON-file
        self.centralDevices["data"] = {}
        with open(os.path.join(self.filePath, 'central_device_data.json')) as json_file:
            jsonData = json.load(json_file)
            for subData in jsonData:
                self.centralDevices["data"][subData["abbreviation"]] = {}
                for subsubData in subData["specifications"]:
                    self.centralDevices["data"][subData["abbreviation"]][subsubData["name"]] = subsubData["value"]

        # load data from JSON-file about wind turbine
        self.centralDevices["data"]["WT"]["power_curve"] = {}
        # open power curve of wind turbine
        power_curve = pd.read_csv(os.path.join(self.filePath, 'wind_turbine_models/WT_WT_Enercon_E40.csv'),
                                  header=0, delimiter=";")  # wind_speed [m/s], power [kW]
        self.centralDevices["data"]["WT"]["power_curve"] = power_curve

        # dimensioning of central devices
        self.centralDevices["capacities"] = self.centralDevices["ces_obj"].designCES(energyCentralData)

        # calculate potential central PV and STC generation (with the roof area of the hole district for each!)
        # todo: Why are different areas used?
        potentialCentralPV, potentialCentralSTC = \
            sun.calcPVAndSTCProfile(time=self.time,
                                    site=self.site,
                                    area_roof=self.centralDevices["ces_obj"].roofAreaDistrict,
                                    devicesType="central",
                                    beta=[35],
                                    gamma=[0],
                                    usageFactorPV=1,
                                    usageFactorSTC=1)

        # assign real central PV generation to central energy unit
        self.centralDevices["renewableGeneration"] = {}
        self.centralDevices["renewableGeneration"]["centralPV"] = potentialCentralPV

        # assign real central STC generation to central energy unit
        self.centralDevices["renewableGeneration"]["centralSTC"] = potentialCentralSTC

        # calculate potential central WT generation (for one wind turbine)
        factor_windSpeed = wind_turbines.factor_windSpeed(self.centralDevices["data"]["WT"])  # [-]
        wind_speed_WT = self.site["wind_speed"] * factor_windSpeed  # [m/s]
        potentialCentralWT = \
            wind_turbines.WT_generation(wind_speed_WT, self.centralDevices["capacities"]["WT"]["powerCurve"])  # [W]

        # clustering data
        self.centralDevices["clusteringData"] = {
            "potentialCentralPV": potentialCentralPV,
            "potentialCentralSTC": potentialCentralSTC,
            "potentialCentralWT": potentialCentralWT,
        }

        # optionally save generation profiles
        if saveGenerationProfiles == True:
            np.savetxt(os.path.join(self.resultPath, 'renewableGeneration') + '/centralPV.csv',
                       self.centralDevices["renewableGeneration"]["centralPV"],
                       delimiter=',')
            np.savetxt(os.path.join(self.resultPath, 'renewableGeneration') + '/centralSTC.csv',
                       self.centralDevices["renewableGeneration"]["centralSTC"],
                       delimiter=',')
            np.savetxt(os.path.join(self.resultPath, 'renewableGeneration') + '/centralWT.csv',
                       self.centralDevices["renewableGeneration"]["centralWT"],
                       delimiter=',')

    def designDevicesComplete(self, fileName_centralSystems="central_devices_example", saveGenerationProfiles=True):
        """
        Design decentral and central devices.

        Parameters
        ----------
        fileName_centralSystems : string, optional
            File name of the CSV-file that will be loaded. The default is "central_devices_test".
        saveGenerationProfiles : bool, optional
            Decision if generation profiles of designed devices will be saved. The default is True.

        Returns
        -------
        None.
        """

        self.designDecentralDevices(saveGenerationProfiles)
        # self.designCentralDevices(saveGenerationProfiles)

    def clusterProfiles(self, centralEnergySupply):
        """
        Perform time series aggregation for profiles by using the k-medoids clustering algorithm.

        Returns
        -------
        None.
        """

        # calculate length of array
        initialArrayLenght = (self.time["clusterLength"] / self.time["timeResolution"])
        lenghtArray = initialArrayLenght
        while lenghtArray <= len(self.site["T_e"]):
            lenghtArray += initialArrayLenght
        lenghtArray -= initialArrayLenght
        lenghtArray = int(lenghtArray)

        # adjust profiles with calculated array length
        adjProfiles = {}
        # loop over buildings
        for id in self.scenario["id"]:
            adjProfiles[id] = {}
            # TODO: Ist es sinnvoll stochastische Zeitreihen zu clustern?
            adjProfiles[id]["elec"] = self.district[id]["user"].elec[0:lenghtArray]
            adjProfiles[id]["dhw"] = self.district[id]["user"].dhw[0:lenghtArray]
            # adjProfiles[id]["gains"] = self.district[id]["user"].gains[0:lenghtArray]
            # adjProfiles[id]["occ"] = self.district[id]["user"].occ[0:lenghtArray]
            adjProfiles[id]["heat"] = self.district[id]["user"].heat[0:lenghtArray]
            adjProfiles[id]["cooling"] = self.district[id]["user"].cooling[0:lenghtArray]
            if self.district[id]["buildingFeatures"]["EV"] != 0:
                adjProfiles[id]["car"] = self.district[id]["user"].car[0:lenghtArray]
            else:
                # no EV exists; but array with just zeros leads to problem while clustering
                adjProfiles[id]["car"] = \
                    self.district[id]["clusteringData"]["potentialEV"][0:lenghtArray] * sys.float_info.epsilon
            if self.district[id]["buildingFeatures"]["PV"] != 0:
                adjProfiles[id]["generationPV"] = self.district[id]["generationPV"][0:lenghtArray]
            else:
                # no PV module installed; but array with just zeros leads to problem while clustering
                adjProfiles[id]["generationPV"] = \
                    self.district[id]["clusteringData"]["potentialPV"][0:lenghtArray] * sys.float_info.epsilon
            if self.district[id]["buildingFeatures"]["STC"] != 0:
                adjProfiles[id]["generationSTC"] = self.district[id]["generationSTC"][0:lenghtArray]
            else:
                # no STC installed; but array with just zeros leads to problem while clustering
                adjProfiles[id]["generationSTC"] = \
                    self.district[id]["clusteringData"]["potentialSTC"][0:lenghtArray] * sys.float_info.epsilon

        # solar radiation on surfaces with different orientation
        adjProfiles["Sun"] = {}
        for drct in range(len(self.SunRad)):
            adjProfiles["Sun"][drct] = self.SunRad[drct][0:lenghtArray]

        if centralEnergySupply == True:

            # central renewable generation
            if self.centralDevices["capacities"]["WT"]["nb_WT"] > 0:
                existence_centralWT = 1
                adjProfiles["generationCentralWT"] = self.centralDevices["renewableGeneration"]["centralWT"][
                                                     0:lenghtArray]
            else:
                # no central WT exists; but array with just zeros leads to problem while clustering
                existence_centralWT = 0
                adjProfiles["generationCentralWT"] = \
                    self.centralDevices["clusteringData"]["potentialCentralWT"][0:lenghtArray] * sys.float_info.epsilon
            if self.centralDevices["capacities"]["PV"]["nb_modules"] > 0:
                existence_centralPV = 1
                adjProfiles["generationCentralPV"] = self.centralDevices["renewableGeneration"]["centralPV"][
                                                     0:lenghtArray]
            else:
                # no central PV exists; but array with just zeros leads to problem while clustering
                existence_centralPV = 0
                adjProfiles["generationCentralPV"] = \
                    self.centralDevices["clusteringData"]["potentialCentralPV"][0:lenghtArray] * sys.float_info.epsilon
            if self.centralDevices["capacities"]["STC"]["area"] > 0:
                existence_centralSTC = 1
                adjProfiles["generationCentralSTC"] = \
                    self.centralDevices["renewableGeneration"]["centralSTC"][0:lenghtArray]
            else:
                # no central STC exists; but array with just zeros leads to problem while clustering
                existence_centralSTC = 0
                adjProfiles["generationCentralSTC"] = \
                    self.centralDevices["clusteringData"]["potentialCentralSTC"][0:lenghtArray] * sys.float_info.epsilon
        # wind speed and ambient temperature
        # adjProfiles["wind_speed"] = self.site["wind_speed"][0:lenghtArray]
        adjProfiles["T_e"] = self.site["T_e"][0:lenghtArray]

        # Prepare clustering
        inputsClustering = []
        # loop over buildings
        for id in self.scenario["id"]:
            inputsClustering.append(adjProfiles[id]["elec"])
            inputsClustering.append(adjProfiles[id]["dhw"])
            # inputsClustering.append(adjProfiles[id]["gains"])
            # inputsClustering.append(adjProfiles[id]["occ"])
            inputsClustering.append(adjProfiles[id]["car"])
            inputsClustering.append(adjProfiles[id]["generationPV"])
            inputsClustering.append(adjProfiles[id]["generationSTC"])
            inputsClustering.append(adjProfiles[id]["heat"])
            inputsClustering.append(adjProfiles[id]["cooling"])
        # solar radiation on surfaces with different orientation
        for drct in range(len(self.SunRad)):
            inputsClustering.append(adjProfiles["Sun"][drct])

        if centralEnergySupply == True:
            # central renewable generation
            inputsClustering.append(adjProfiles["generationCentralWT"])
            inputsClustering.append(adjProfiles["generationCentralPV"])
            inputsClustering.append(adjProfiles["generationCentralSTC"])
        # wind speed and ambient temperature
        # inputsClustering.append(adjProfiles["wind_speed"])
        inputsClustering.append(adjProfiles["T_e"])

        # weights for clustering algorithm indicating the focus onto this profile
        weights = np.ones(len(inputsClustering))
        # higher weight for outdoor temperature (should at least have the same weight as number of buildings)
        weights[-1] = len(self.scenario["id"]) + len(self.SunRad)

        # Perform clustering
        (newProfiles, nc, y, z, transfProfiles) = cm.cluster(np.array(inputsClustering),
                                                             number_clusters=self.time["clusterNumber"],
                                                             len_day=int(initialArrayLenght),
                                                             weights=weights)

        # safe clustering solution in district data
        # safe clustered profiles of all buildings
        for id in self.scenario["id"]:
            index_house = int(7)  # number of profiles per building
            self.district[id]["user"].elec_cluster = newProfiles[index_house * id]
            self.district[id]["user"].dhw_cluster = newProfiles[index_house * id + 1]
            # self.district[id]["user"].gains_cluster = newProfiles[index_house * id + 2]
            # self.district[id]["user"].occ_cluster = newProfiles[index_house * id + 3]
            # assign real EV, PV and STC generation for clustered data to buildings
            # (array with zeroes if EV, PV or STC does not exist)
            if self.district[id]["buildingFeatures"]["EV"] == 0:
                self.district[id]["user"].car_cluster = newProfiles[index_house * id + 2] * 0
            else:
                self.district[id]["user"].car_cluster = newProfiles[index_house * id + 2]
            if self.district[id]["buildingFeatures"]["PV"] == 0:
                self.district[id]["generationPV_cluster"] = newProfiles[index_house * id + 3] * 0
            else:
                self.district[id]["generationPV_cluster"] = newProfiles[index_house * id + 3]
            if self.district[id]["buildingFeatures"]["STC"] == 0:
                self.district[id]["generationSTC_cluster"] = newProfiles[index_house * id + 4] * 0
            else:
                self.district[id]["generationSTC_cluster"] = newProfiles[index_house * id + 4]
            self.district[id]["user"].heat_cluster = newProfiles[index_house * id + 5]
            self.district[id]["user"].cooling_cluster = newProfiles[index_house * id + 6]
        # safe clustered solar radiation on surfaces with different orientation

        if centralEnergySupply == True:
            # save clustered data for real central renewable generation
            self.centralDevices["renewableGeneration"]["centralWT_cluster"] = newProfiles[-5] * existence_centralWT
            self.centralDevices["renewableGeneration"]["centralPV_cluster"] = newProfiles[-4] * existence_centralPV
            self.centralDevices["renewableGeneration"]["centralSTC_cluster"] = newProfiles[-3] * existence_centralSTC

        self.SunRad_cluster = {}
        for drct in range(len(self.SunRad)):
            self.SunRad_cluster[drct] = newProfiles[-1 - len(self.SunRad) + drct]
        # save clustered wind speed and ambient temperature
        # self.site["wind_speed_cluster"] = newProfiles[-2]
        self.site["T_e_cluster"] = newProfiles[-1]

        # clusters
        self.clusters = []
        for i in range(len(y)):
            if y[i] != 0:
                self.clusters.append(i)

        # clusters and their assigned nodes (days/weeks/etc)
        self.clusterAssignments = {}
        for c in self.clusters:
            self.clusterAssignments[c] = []
            temp = z[c]
            for i in range(len(temp)):
                if temp[i] == 1:
                    self.clusterAssignments[c].append(i)

        # weights indicating how often a cluster appears
        self.clusterWeights = {}
        for c in self.clusters:
            self.clusterWeights[c] = len(self.clusterAssignments[c])

        """self.clusteringCheck = {}
        for c in self.clusters:
            self.clusteringCheck[c] = sum(self.clusterAssignments[c])"""

    def saveDistrict(self):
        """
        Save district dict as pickle file.

        Returns
        -------
        None.
        """

        with open(self.resultPath + "/" + self.scenario_name + ".p", 'wb') as fp:
            pickle.dump(self.district, fp, protocol=pickle.HIGHEST_PROTOCOL)

    def loadDistrict(self, list_all: list = [], scenario_name='example'):
        """
        Load district dict from pickle file.

        Parameters
        ----------
        scenario_name : string, optional
            Name of district file to be read. The default is 'example'.

        Returns
        -------
        None.
        """

        self.scenario_name = scenario_name

        # initialize buildings for scenario
        # loop over all buildings
        for id, entry in enumerate(list_all):
            list = list_all[id]
            building = {}
            building["buildingFeatures"] = pd.Series(
                [list[0], list[1], list[2], list[3], list[4], 3, 1, 2, 3, 1, 2, 3, 1, 2, 3, 1],
                index=['id', 'building', 'year', 'retrofit', 'area', 'heater', 'PV',
                       'STC', 'EV', 'BAT', 'f_TES', 'f_BAT', 'f_EV', 'f_PV', 'f_STC',
                       'gamma_PV', ])

    def plot(self):

        # factor to convert power [kW] for one timestep to energy [kWh] for one timestep
        factor = self.time['timeResolution'] / 3600

        # loop over buildings to sum upp energy consumptions and generations for the hole district
        demands = {}
        for b in range(len(self.district)):
            demands['elec'] += self.district[b]['user'].elec / 1000
            demands['dhw'] += self.district[b]['user'].dhw / 1000
            demands['cooling'] += self.district[b]['user'].cooling / 1000
            demands['heating'] += self.district[b]['user'].heat / 1000

        peakDemands = [np.max(demands['heating']), np.max(demands['cooling']), np.max(demands['dhw']), np.max(demands['elec'])]
        energyDemands = [np.sum(demands['heating']), np.sum(demands['cooling']), np.sum(demands['dhw']), np.sum(demands['elec'])]

        # days per month and cumulated days of months
        daysInMonhs = np.array([31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])
        cumutaltedDays = np.zeros(12)
        for i in range(len(cumutaltedDays)):
            if i == 0:
                cumutaltedDays[i] = daysInMonhs[i]
            else:
                cumutaltedDays[i] = cumutaltedDays[i-1] + daysInMonhs[i]

        # array with last time step of each month
        monthlyDataSteps = cumutaltedDays * 24 * 3600 / self.time['timeResolution']

        # create monthly data for bar plots
        demands['heat_monthly'] = []
        demands['cooling_monthly'] = []
        demands['dhw_monthly'] = []
        demands['elec_monthly'] = []

        for m in range(len(cumutaltedDays)):
            if m == 0:
                # first month starts with time step zero
                start = 0
            else:
                # all the other months starts one time step after the last time step of the previous month
                start = int(monthlyDataSteps[m - 1]) + 1
            end = int(monthlyDataSteps[m]) + 1
            # convert power [W] to energy per month [kWh] by multiplication with factor
            demands['heating_monthly'].append(np.sum(demands['heating'][start:end] * factor))
            demands['cooling_monthly'].append(np.sum(demands['cooling'][start:end] * factor))
            demands['dhw_monthly'].append(np.sum(demands['dhw'][start:end] * factor))
            demands['elec_monthly'].append(np.sum(demands['elec'][start:end] * factor))

        # plots
        # Monatsabkürzungen definieren
        monats_abk = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']
        # Farben für die Diagramme definieren
        farben = ['blue', 'green', 'red', 'purple']

        # Grafiken mit den Anpassungen erstellen
        fig, axs = plt.subplots(4, 1, figsize=(10, 20))
        daten = [demands['heating_monthly'], demands['cooling_monthly'], demands['dhw_monthly'], demands['elec_monthly']]
        for i, ax in enumerate(axs):
            ax.bar(monats_abk, daten[i], color=farben[i])  # Balkendiagramm mit spezifischer Farbe
            ax.set_title(f'Grafik {i + 1}')  # Titel setzen
            ax.set_xlabel('Monat')  # X-Achsenbeschriftung
            ax.set_ylabel('Energie in kWh')  # Y-Achsenbeschriftung

        plt.tight_layout()
        plt.savefig('pfad_angeben.png')

        return peakDemands, energyDemands

    def optimizationClusters(self, centralEnergySupply):
        """
        Optimize the operation costs for each cluster.

        Returns
        -------
        None.
        """

        # initialize result list for all clusters
        self.resultsOptimization = []

        for cluster in range(self.time["clusterNumber"]):
            # optimize operating costs of the district for current cluster
            self.optimizer = Optimizer(self, cluster, centralEnergySupply)
            results_temp = self.optimizer.run_cen_opti()
            # save results as attribute
            self.resultsOptimization.append(results_temp)

    def calulateKPIs(self, result_path=None):
        """
        Calculate key performance indicators (KPIs).

        Returns
        -------
        None.
        """

        # initialize KPI class
        self.KPIs = KPIs(self)
        # calculate KPIs
        self.KPIs.calculateAllKPIs(self)
        # Generate a PDF file with a list of KPIs.
        self.KPIs.create_kpi_pdf(result_path)

    def optimizationWithEHDO(self):
        """
        Optimization with EHDO.

        Returns
        -------
        None.
        """

        demands_district = {}
        demands_district["heat"] = np.loadtxt(os.path.join(self.resultPath, 'demands') + '/heating_district.csv',
                                              delimiter=',')
        demands_district["cooling"] = np.loadtxt(os.path.join(self.resultPath, 'demands') + '/cooling_district.csv',
                                                 delimiter=',')
        demands_district["dhw"] = np.loadtxt(os.path.join(self.resultPath, 'demands') + '/dhw_district.csv',
                                             delimiter=',')
        demands_district["elec"] = np.loadtxt(os.path.join(self.resultPath, 'demands') + '/elec_district.csv',
                                              delimiter=',')

        # Load parameters
        # TODO: Input ob devs feasible = True/False, min/max cap, ....
        param, devs, dem, result_dict = load_params_EHDO.load_params(self, demands_district)

        # Run optimization
        self.resultsEHDO = optim_model_EHDO.run_optim(devs, param, dem, result_dict)
