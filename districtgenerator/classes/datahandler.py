# -*- coding: utf-8 -*-

import json
import pickle
import os
import numpy as np
import pandas as pd
import random as rd
from itertools import count
from teaser.project import Project
from .envelope import Envelope
from .solar import Sun
from .users import Users

class Datahandler():
    """
    Handles data collection, processing, and simulation for urban building energy modeling.

    This class integrates various sources of data, including site information, weather conditions,
    building configurations, and user behaviors. It generates realistic demand profiles for heating,
    domestic hot water, and electricity consumption.

    Attributes:
        - site (dict): Stores site-related data including weather and location.
        - time (dict): Stores time-related parameters.
        - district (list): A list containing all buildings.
        - scenario_name (str or None): Name of the current scenario file being used.
        - scenario (pd.DataFrame or None): DataFrame containing the scenario's buildings parameters.
        - counter (dict): Tracks unique building identifiers.
        - srcPath (str): The base directory path of the project.
        - filePath (str): The directory path where data files are stored.
        - resultPath (str): The directory path where demand results are stored.
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
        Loads and processes site and weather data for the simulation environment.
        ----------

        Parameters
        ----------
            - Site-specific data from `site_data.json`.
            - Loads weather data (solar radiation and temperature) based on the selected TRY (Test Reference Year).

        Returns
        ----------
            - Saving the interpolated data to the data handler.
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
        self.site["SunRad"] = sun.getSolarGains(initialTime=0,
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
        Initializes the district by loading building data from a scenario file.

        ----------

        Parameters
        ----------
            - scenario_name (str, optional): The name of the scenario file to be read. Defaults to 'example'.

        Returns
        ----------
            - Populates the `district` list with building objects containing their respective features.
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


    def generateBuildings(self, rng=None):
        """
        Loads building envelope and user data for each building in the district.

        ----------

        Parameters
        ----------
            - building features (dict): Contains building-specific data.
            - number_of_floors (int): The number of floors in the building.
            - height_of_floors (float): The height of each floor in the building.

        Returns
        ----------
            - Creates and assigns building envelope data using the `Envelope` class.
            - Generates and assigns user profiles for each building using the `Users` class.
            - Computes design heat loads and assigns to each building.
        """

        rg = rng or rd

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

            # Determining the number of floors in a building based on its type.
            # The method estimates the number of floors by:
            # - Assigning a range of possible floor areas per level based on building type.
            # - Randomly selecting a value within the assigned range using the TABULA German Building Typology.
            # - Calculating the total number of floors by dividing the building’s total floor area
            #   by the selected single-floor area.

            if building_type == "single_family_house":
                one_floor_area = rg.randint(62, 115)  # Source: TABULA German Building Typology
                # Calculate the number of floors, rounding to the nearest integer and ensuring at least 1
                number_of_floors = max(1, round(building["buildingFeatures"]["area"] / one_floor_area))

            elif building_type == "terraced_house":
                one_floor_area = rg.randint(50, 73)  # Source: TABULA German Building Typology
                # Calculate the number of floors, rounding to the nearest integer and ensuring at least 1
                number_of_floors = max(1, round(building["buildingFeatures"]["area"] / one_floor_area))

            elif building_type == "multi_family_house":
                # Generate a valid one-floor area and number of floors in one step
                one_floor_area = rg.randint(102, 971)  # Source: TABULA German Building Typology
                # Calculate the number of floors, rounding to the nearest integer and ensuring at least 2
                number_of_floors = max(2, round(building["buildingFeatures"]["area"] / one_floor_area))
                # Cap the number of floors to a maximum of 8
                if number_of_floors > 8:
                    number_of_floors = 8

            elif building_type == "apartment_block":
                one_floor_area = rg.randint(350, 540)  # Source: TABULA German Building Typology
                # Calculate the number of floors, rounding to the nearest integer and ensuring at least 3
                number_of_floors = max(3, round(building["buildingFeatures"]["area"] / one_floor_area))

            # Determining the typical floor height based on the building's construction year.
            # Older buildings (constructed before 1960) generally have higher ceilings, while newer buildings
            # (built from 1960 onwards) tend to have lower ceilings.
            # Source: https://www.wohnung.com/ratgeber/418/alt-und-neubau-deckenhoehe

            if building["buildingFeatures"]["year"] < 1960:
                height_of_floors = 3.3 # m
            elif building["buildingFeatures"]["year"] >= 1960:
                height_of_floors = 2.5 # m

            # add buildings to TEASER project
            prj.add_residential(
                method='tabula_de',
                usage=building_type,
                name="ResidentialBuildingTabula",
                year_of_construction=building["buildingFeatures"]["year"],
                number_of_floors=number_of_floors,
                height_of_floors=height_of_floors,
                net_leased_area=building["buildingFeatures"]["area"],
                construction_type=retrofit_level)

            # %% create envelope object
            # containing all physical data of the envelope
            building["envelope"] = Envelope(prj=prj,
                                            building_params=building["buildingFeatures"],
                                            construction_type=retrofit_level,
                                            file_path = self.filePath)

            # %% create user object
            # containing number occupants, electricity demand, ...
            if rng is not None:
                building_seed = 42 + building["buildingFeatures"]["id"]
                building_rng = rd.Random(int(building_seed))
            else:
                building_rng = None

            building["user"] = Users(building=building["buildingFeatures"]["building"],
                             area=building["buildingFeatures"]["area"], rng=building_rng)

            # %% calculate design heat loads
            # at norm outside temperature
            building["heatload"] = building["envelope"].calcHeatLoad(site=self.site, method="design")
            # at bivalent temperature
            building["bivalent"] = building["envelope"].calcHeatLoad(site=self.site, method="bivalent")
            # at heatimg limit temperature
            building["heatlimit"] = building["envelope"].calcHeatLoad(site=self.site, method="heatlimit")
            # for drinking hot water
            building["dhwload"] = bldgs["dhwload"][bldgs["buildings_short"].index(building["buildingFeatures"]["building"])] * building["user"].nb_flats


    def generateDemands(self, calcUserProfiles=True, saveUserProfiles=True):
        """
        Generates cooling, heating, domestic hot water demand and household electricity demand profiles
        for each building.

        ----------

        Parameters
        ----------
            - calcUserProfiles (bool, optional): Determines whether to calculate new user profiles (`True`) or load
            existing ones (`False`). Defaults to `True`.
            - saveUserProfiles (bool, optional): If `True`, saves calculated user profiles to the workspace.
            Only applicable if `calcUserProfiles` is `True`.

        Returns
        ----------
            - Computes user behavior profiles for energy demand estimation.
            - Cooling, heating, domestic hot water demand and household electricity demand profiles based on user behavior, envelope properties and site conditions.
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

            building["envelope"].calcNormativeProperties(self.site["SunRad"],building["user"].gains)

            # calculate heating profiles
            building["user"].calcHeatingProfile(site=self.site,
                                                envelope=building["envelope"],
                                                time_resolution=self.time["timeResolution"])

            if saveUserProfiles :
                building["user"].saveHeatingProfile(building["unique_name"], self.resultPath)

        print("Finished generating demands!")


    def generateDistrictComplete(self, scenario_name='example', calcUserProfiles=True, saveUserProfiles=True):
        """
        Executes the complete process of district generation, including environment setup,
        building initialization, envelope creation, and demand calculation.

        """

        self.generateEnvironment()
        self.initializeBuildings(scenario_name)
        self.generateBuildings()
        self.generateDemands(calcUserProfiles, saveUserProfiles)

    def saveDistrict(self):
        """
        Saves the district data as a pickle file for later use.

        ----------

        Returns
        ----------
        - Stores the current `district` data as a pickle file in the results directory.
        """
        with open(self.resultPath + "/" + self.scenario_name + ".p",'wb') as fp:
            pickle.dump(self.district, fp, protocol=pickle.HIGHEST_PROTOCOL)


    def loadDistrict(self, scenario_name='example'):
        """
        Loads district data from a previously saved pickle file.

        ----------

        Parameters
        ----------
            - scenario_name (str, optional): The name of the scenario file to be loaded. Defaults to 'example'.

        Returns
        ----------
            - Restores the `district` data from the saved pickle file in the results directory.
        """
        self.scenario_name = scenario_name

        with open(self.resultPath + "/" + self.scenario_name + ".p", 'rb') as fp:
            self.district = pickle.load(fp)