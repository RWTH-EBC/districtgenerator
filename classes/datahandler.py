# -*- coding: utf-8 -*-

import json
import pickle
import os
import numpy as np
import pandas as pd
from itertools import count
from teaser.project import Project
from classes.envelope import Envelope
from classes.solar import Sun
from classes.users import Users
from classes.plots import DemandPlots

class Datahandler():
    """
    Abstract class for data handling
    Collects data from input files, TEASER, User and Enevelope.

    Attributes
    ----------
    site:
        dict for site data, e.g. weather
    time:
        dict for time settings
    district:
        list of all buildings within district
    scenario_name:
        name of scenario file
    scenario:
        scenario data
    counter:
        dict for counting number of equal building types
    srcPath:
        source path
    filePath:
        file path

    """

    def __init__(self):
        self.site = {}
        self.time = {}
        self.district = []
        self.scenario_name = None
        self.scenario = None
        self.counter = {}
        self.srcPath = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.filePath = os.path.join(self.srcPath, 'data')
        self.resultPath = os.path.join(self.srcPath, 'results', 'demands')


    def generateEnvironment(self):
        """
        Load physical district environment - site and weather

        Parameters
        ----------

        Returns
        -------

        """

        # %% load information about of the site under consideration
        # important for weather conditions
        with open(os.path.join(self.filePath, 'site_data.json')) as json_file:
            jsonData = json.load(json_file)
            for subData in jsonData:
                self.site[subData["name"]] = subData["value"]

        # %% load weather data for site
        # extract irradiation and ambient temperature
        first_row = {}
        if self.site["TRYYear"]=="TRY2015":
            first_row = 35
        elif self.site["TRYYear"]=="TRY2045":
            first_row = 37

        weatherData = np.loadtxt(os.path.join(self.filePath, 'weather')
                                 + "/"
                                 + self.site["TRYYear"] + "_Zone"
                                 + str(self.site["climateZone"]) + "_"
                                 + self.site["TRYType"] + ".txt",
                                 skiprows=first_row - 1)


        # weather data starts with 1st january at 1:00 am. Add data point for 0:00 am to be able to perform interpolation.
        weatherData_temp = weatherData[-1:, :]
        weatherData = np.append(weatherData_temp, weatherData, axis=0)

        # get weather data of interest
        [temp_sunDirect,  temp_sunDiff, temp_temp] = [weatherData[:, 12], weatherData[:, 13], weatherData[:, 5]]

        # %% load time information and requirements
        # needed for data conversion into the right time format
        with open(os.path.join(self.filePath, 'time_data.json')) as json_file:
            jsonData = json.load(json_file)
            for subData in jsonData :
                self.time[subData["name"]] = subData["value"]
        self.time["timeSteps"] = int(self.time["dataLength"] / self.time["timeResolution"])

        # interpolate input data to achieve required data resolution
        # transformation from values for points in time to values for time intervals
        self.site["SunDirect"] = np.interp(np.arange(0, self.time["dataLength"]+1, self.time["timeResolution"]),
                                           np.arange(0, self.time["dataLength"]+1, self.time["dataResolution"]),
                                           temp_sunDirect)[0:-1]
        self.site["SunDiffuse"] = np.interp(np.arange(0, self.time["dataLength"]+1, self.time["timeResolution"]),
                                            np.arange(0, self.time["dataLength"]+1, self.time["dataResolution"]),
                                            temp_sunDiff)[0:-1]
        self.site["T_e"] = np.interp(np.arange(0, self.time["dataLength"]+1, self.time["timeResolution"]),
                                     np.arange(0, self.time["dataLength"]+1, self.time["dataResolution"]),
                                     temp_temp)[0:-1]

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
                                        beam=self.site["SunDirect"],
                                        diffuse=self.site["SunDiffuse"],
                                        albedo=self.site["albedo"])


    def initializeBuildings(self, scenario_name='example'):
        """
        Fill district with buildings from scenario file

        Parameters
        ----------
        scenario_name: string, optional
            name of scenario file to be read

        Returns
        -------

        """

        self.scenario_name = scenario_name
        self.scenario = pd.read_csv(os.path.join(self.filePath, 'scenarios')
                                    + "/"
                                    + self.scenario_name + ".csv",
                                    header=0, delimiter=";")

        # initialize buildings for scenario
        for id in self.scenario["id"]:
            # create empty dict for observed building
            building = {}

            # store features of the observed building
            building["buildingFeatures"] = self.scenario.loc[id]

            # append building to district
            self.district.append(building)


    def generateBuildings(self):
        """
        Load building envelope and user data

        Parameters
        ----------

        Returns
        -------

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

            # convert short names into designation needes for TEASER
            building_type = bldgs["buildings_long"][bldgs["buildings_short"].index(building["buildingFeatures"]["building"])]
            retrofit_level = bldgs["retrofit_long"][bldgs["retrofit_short"].index(building["buildingFeatures"]["retrofit"])]

            # add buildings to TEASER project
            prj.add_residential(
                method='tabula_de',
                usage=building_type,
                name="ResidentialBuildingTabula",
                year_of_construction=building["buildingFeatures"]["year"],
                number_of_floors=3,
                height_of_floors=3.125,
                net_leased_area=building["buildingFeatures"]["area"],
                construction_type=retrofit_level)

            # %% create envelope object
            # containing all physical data of the envelope
            building["envelope"] = Envelope(prj=prj,
                                            building_params=building["buildingFeatures"],
                                            construction_type=retrofit_level,
                                            file_path = self.filePath)

            # %% create user object
            # containing number occupants, electricity demand,...
            building["user"] = Users(building=building["buildingFeatures"]["building"],
                             area=building["buildingFeatures"]["area"])

            # %% calculate design heat loads
            # at norm outside temperature
            building["heatload"] = building["envelope"].calcHeatLoad(site=self.site, method="design")
            # at bivalent temperature
            building["bivalent"] = building["envelope"].calcHeatLoad(site=self.site, method="bivalenz")
            # at heatimg limit temperature
            building["heatlimit"] = building["envelope"].calcHeatLoad(site=self.site, method="heatlimit")
            # for drinking hot water
            building["dhwload"] = bldgs["dhwload"][bldgs["buildings_short"].index(building["buildingFeatures"]["building"])] * building["user"].nb_flats


    def generateDemands(self, calcUserProfiles=True, saveUserProfiles=True):
        """
        Generate occupancy profile, heat demand, domestic hot water demand and heating demand

        Parameters
        ----------
        calcUserProfiles: bool, optional
            True: calculate new user profiles
            False: load user profiles from file
        saveUserProfiles: bool, optional
            True for saving calculated user profiles in workspace (Only taken into account if calcUserProfile is True)

        Returns
        -------
        """

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

            # calculate or load user profiles
            if calcUserProfiles:
                building["user"].calcProfiles(site=self.site,
                                              time_horizon=self.time["dataLength"],
                                              time_resolution=self.time["timeResolution"])
                if saveUserProfiles:
                    building["user"].saveProfiles(building["unique_name"], self.resultPath)

                print("Calculate demands of building " + building["unique_name"])

            else:
                building["user"].loadProfiles(building["unique_name"], self.resultPath)
                print("Load demands of building " + building["unique_name"])

            building["envelope"].calcNormativeProperties(self.SunRad,building["user"].gains)

            # calculate heating profiles
            building["user"].calcHeatingProfile(site=self.site,
                                                envelope=building["envelope"],
                                                time_resolution=self.time["timeResolution"])

            if saveUserProfiles :
                building["user"].saveHeatingProfile(building["unique_name"], self.resultPath)

        print("Finished generating demands!")


    def generateDistrictComplete(self, scenario_name='example', calcUserProfiles=True, saveUserProfiles=True):
        """
        All in one solution for district and demand generation

        Parameters
        ----------
        scenario_name:string, optional
            name of scenario file to be read
        calcUserProfiles: bool, optional
            True: calculate new user profiles
            False: load user profiles from file
        saveUserProfiles: bool, optional
            True for saving calculated user profiles in workspace (Only taken into account if calcUserProfile is True)

        Returns
        -------

        """

        self.generateEnvironment()
        self.initializeBuildings(scenario_name)
        self.generateBuildings()
        self.generateDemands(calcUserProfiles, saveUserProfiles)

    def saveDistrict(self):
        """
        Save district dict as pickle file

        Parameters
        ----------

        Returns
        -------

        """
        with open(self.resultPath + "/" + self.scenario_name + ".p",'wb') as fp:
            pickle.dump(self.district, fp, protocol=pickle.HIGHEST_PROTOCOL)


    def loadDistrict(self, scenario_name='example'):
        """
        Load district dict from pickle file

        Parameters
        ----------

        Returns
        -------

        """
        self.scenario_name = scenario_name

        with open(self.resultPath + "/" + self.scenario_name + ".p", 'rb') as fp:
            self.district = pickle.load(fp)


    def plot(self, mode='default', initialTime=0, timeHorizon=31536000, savePlots=True, timeStamp=False, show=False):
        """
        Create plots of the energy consumption and generation.

        Parameters
        ----------
        mode : string, optional
            Choose a single plot or show all of them as default. The default is 'default'.
            Possible modes are ['elec', 'dhw', 'gains', 'heating', 'electricityDemand', 'heatDemand']
        initialTime : integer, optional
            Start of the plot in seconds from the beginning of the year. The default is 0.
        timeHorizon : integer, optional
            Length of the time horizon that is plotted in seconds. The default is 31536000 (what equals one year).
        savePlots : boolean, optional
            Decision if plots are saved under results/plots/. The default is True.
        timeStamp : boolean, optional
            Decision if saved plots get a unique name by adding a time stamp. The default is False.

        Returns
        -------
        None.

        """

        # initialize plots and prepare data for plotting
        demandPlots = DemandPlots()
        demandPlots.preparePlots(self)

        # check which resolution for plots is used
        if initialTime == 0 and timeHorizon == 31536000:
            plotResolution = 'monthly'
        else:
            plotResolution = 'stepwise'

        # the selection of possible plots
        plotTypes = ['elec', 'dhw', 'gains', 'heating', 'electricityDemand', 'heatDemand']

        if mode == 'default':
            # create all default plots
            demandPlots.defaultPlots(plotResolution, initialTime=initialTime, timeHorizon=timeHorizon,
                                     savePlots=savePlots, timeStamp=timeStamp, show=show)
        elif mode in plotTypes:
            # create a plot
            demandPlots.onePlot(plotType=mode, plotResolution=plotResolution, initialTime=initialTime,
                                timeHorizon=timeHorizon, savePlots=savePlots, timeStamp=timeStamp, show=show)
        else:
            # print massage that input is not valid
            print('\n Selected plot mode is not valid. So no plot could de generated. \n')