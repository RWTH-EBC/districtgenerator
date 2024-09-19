# -*- coding: utf-8 -*-

import json
import pickle
import os
from typing import Any
import numpy as np
import pandas as pd
from itertools import count
from teaser.project import Project
from districtgenerator.envelope import Envelope
from districtgenerator.solar import Sun
from districtgenerator.users import Users
from districtgenerator.plots import DemandPlots
from districtgenerator.non_residential import NonResidential
from districtgenerator.non_residential_users import NonResidentialUsers
import functions.weather_handling as weather_handling
import functions.path_checks as path_checks

RESIDENTIAL_BUILDING_TYPES = ["SFH", "TH", "MFH", "AB"]
NON_RESIDENTIAL_BUILDING_TYPES = ["IWU Hotels, Boarding, Restaurants or Catering", "IWU Office, Administrative or Government Buildings",
                                  "IWU Trade Buildings", "IWU Technical and Utility (supply and disposal)", "IWU School, Day Nursery and other Care", "IWU Transport",
                                  "IWU Health and Care", "IWU Sports Facilities", "IWU Culture and Leisure", "IWU Research and University Teaching", "IWU Technical and Utility (supply and disposal)",
                                  "IWU Generalized (1) Services building", "IWU Generalized (2) Production buildings", "IWU Production, Workshop, Warehouse or Operations"]

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
    weatherFile::
        path to weather file, which is not a TRY file. If None, the TRY file is used. 
        file should follow the following format, according to DWD naming conventions 
        temp_sunDirect = B  Direkte Sonnenbestrahlungsstaerke (horiz. Ebene)
        temp_sunDiff = D Diffuse Sonnenbetrahlungsstaerke (horiz. Ebene)
        temp_temp = t Lufttemperatur in 2m Hoehe ueber Grund 
        direct_illuminance = direct illuminance, only present in epw file
        diffuse_illuminance = diffuse illuminance, only present in epw file

    sheetFile:
        path to scenario file, which is a csv file. If None, the csv file is used.
        Can be used to provide more detailed information for gerneation of the buildings models in the district
       
    """

    def __init__(self, weather_file=None, sheet_file=None):
        self.site = {}
        self.time = {}
        self.district = []
        self.scenario_name = None
        self.scenario = None
        self.counter = {}
        self.building_dict = {} # Dictionary to store Residential Building IDs
        self.srcPath = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.filePath = os.path.join(self.srcPath, 'data')
        self.resultPath = os.path.join(self.srcPath, 'results', 'demands')
        self.weatherFile = weather_file
        self.sheetFile = sheet_file
        self.advancedModel = None
        if weather_file is not None:
            self.timestamp = weather_handling.get_time_horizon(self.weatherFile)


    def setResultPath(self, new_path=None):
            """
            Sets the path where the results will be saved.

            Args:
                new_path (str, optional): The new path to set. If not provided, the default path will be used.

            Returns:
                None
            """
            if new_path is not None:
                new_path = path_checks.check_path(new_path)
            else: 
                new_path = os.path.join(self.srcPath, 'results', 'demands', f'{self.scenario_name}')
                new_path = path_checks.check_path(new_path)
            self.resultPath = new_path 
    
    def setAdvancedModel(self, pathAdvancedModel=None):
            """
            Sets the path and loads data for advanded modelling

            Args:
                new_path (str, optional): The new path to set. If not provided, the default path will be used.

            Returns:
                None
            """
            self.advancedModel = pathAdvancedModel if pathAdvancedModel is not None else None

    def setWeatherFile(self, pathWeatherFile=None):
            """
            Sets the path and loads data for weather file

            Args:
                new_path (str, optional): The new path to set. If not provided, the default path will be used.

            Returns:
                None
            """
            self.weatherFile = pathWeatherFile if pathWeatherFile is not None else None
            # Update of time stamp
            if pathWeatherFile is not None:
                self.timestamp  = weather_handling.get_time_horizon(self.weatherFile)

    def generateEnvironment(self):
        """
        Load physical district environment - site and weather

        Parameters
        ----------

        Returns
        -------

        """
        # To-Do: Illuminance calculation for both epw and DWD
        # To-Do: Set time stamp for epw

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

        # Check if a weather file is presented, if not TRY is taken 
        if self.weatherFile != None:
            if self.weatherFile.endswith(".epw"):
                # load data from epw file 
                weatherData = weather_handling.getEpWeather(self.weatherFile)
                # Set Last hour to the year to first 
                weatherData = pd.concat([weatherData.iloc[[-1]], weatherData]).reset_index(drop=True)
                temp_sunDirect = weatherData["Direct Normal Radiation"].to_numpy()
                temp_sunDiff = weatherData["Diffuse Horizontal Radiation"].to_numpy()
                temp_temp = weatherData["Dry Bulb Temperature"].to_numpy()
                direct_illuminance = weatherData["Direct Normal Illuminance"].to_numpy()
                diffuse_illuminance = weatherData["Diffuse Horizontal Illuminance"].to_numpy()
            else:
                # if an weather file is presented, this can be used for calcuation
                # it should be a csv files with the following columns, according to the DWD TRY files
                # temp_sunDirect = B  Direkte Sonnenbestrahlungsstaerke (horiz. Ebene) float or int
                # temp_sunDiff = D Diffuse Sonnenbetrahlungsstaerke (horiz. Ebene)  float or int
                # temp_temp = t Lufttemperatur in 2m Hoehe ueber Grund float or int
                # To-Do: Figure out, how to gather illuminance from a DWD file?
                weatherData = pd.read_csv(self.weatherFile)
                weatherData = pd.concat([weatherData.iloc[[-1]], weatherData]).reset_index(drop=True)
                temp_sunDirect = weatherData["B"].to_numpy()
                temp_sunDiff = weatherData["D"].to_numpy()
                temp_temp = weatherData["t"].to_numpy()
              
        else: 
            # This works for the predefined weather files 
            weather_file = os.path.join(self.filePath, 'weather', 'DWD',
                                f"{self.site['TRYYear']}_Zone{self.site['climateZone']}_{self.site['TRYType']}.txt")
            weatherData = np.loadtxt(weather_file,
                                 skiprows=first_row - 1)
            # weather data starts with 1st january at 1:00 am. Add data point for 0:00 am to be able to perform interpolation.
            weatherData_temp = weatherData[-1:, :]
            weatherData = np.append(weatherData_temp, weatherData, axis=0)

            # get weather data of interest
            # variables according to dwd sheet
            # temp_sunDirect = B  Direkte Sonnenbestrahlungsstaerke (horiz. Ebene)
            # temp_sunDiff = D Diffuse Sonnenbetrahlungsstaerke (horiz. Ebene) 
            # temp_temp = t Lufttemperatur in 2m Hoehe ueber Grund
            [temp_sunDirect, temp_sunDiff, temp_temp] = [weatherData[:, 12], weatherData[:, 13], weatherData[:, 5]]

        # %% load time information and requirements
        # needed for data conversion into the right time format
        with open(os.path.join(self.filePath, 'time_data.json')) as json_file:
            jsonData = json.load(json_file)
            for subData in jsonData :
                self.time[subData["name"]] = subData["value"]
        # check for Gap year and adjust data length
        if len(temp_sunDiff) == 8785:
            # 31622400 = 60 * 60 * 24 * 366
            self.time["dataLength"] =  31622400
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
        if self.weatherFile != None:
            if self.weatherFile.endswith(".epw"):
                self.site["IlluminanceDirect"] = np.interp(np.arange(0, self.time["dataLength"]+1, self.time["timeResolution"]),
                                                np.arange(0, self.time["dataLength"]+1, self.time["dataResolution"]),
                                                direct_illuminance)[0:-1]
                
                self.site["IlluminaceDiffuse"] = np.interp(np.arange(0, self.time["dataLength"]+1, self.time["timeResolution"]),
                                                np.arange(0, self.time["dataLength"]+1, self.time["dataResolution"]),
                                                diffuse_illuminance)[0:-1]
            

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
        
        self.resultPath = os.path.join(self.srcPath, 'results', 'demands', self.scenario_name)
        

        # initialize buildings for scenario
        for id in self.scenario["id"]:
            # create empty dict for observed building
            building = {}

            # store features of the observed building
            building["buildingFeatures"] = self.scenario.loc[id]

            # append building to district
            self.district.append(building)

        self.generate_building_dict()

    def generate_building_dict(self):
        """
        Processes the scenario file and checks wheter or wheter not the building is in 'SFH', 'TH', 'MFH', 'AB'. 
        Creates a temp storage, to handle TEASER prj with ids starting from ß. 

        Args:
            csv_file (str): Path to the CSV file containing building data with 'id' and 'building' columns.

        Returns:
            None: Modifies the internal building_dict attribute of the class.
        """

        
        # Filter the data for specified building types
        filtered_data = self.scenario[self.scenario['building'].isin(['SFH', 'TH', 'MFH', 'AB'])]
        
        # Generate the dictionary
        temp_id = 0
        for index, row in filtered_data.iterrows():
            self.building_dict[row['id']] = temp_id
            temp_id += 1

    def generateBuildings(self):
        """
        Load building envelope and user data


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
        
   

        if self.advancedModel is not None:
            # if a model file is presented, this can be used for advanced parameterization of the buildings 
            # it should be a csv file with the following 
            model_data = pd.read_csv(self.advancedModel)
            # Check types
            # Ensure 'height' and 'storeys_above_ground' are of float type
            if not np.issubdtype(model_data['height'].dtype, np.number):
                model_data['height'] = pd.to_numeric(model_data['height'], errors='coerce')
            if not np.issubdtype(model_data['storeys_above_ground'].dtype, np.number):
                model_data['storeys_above_ground'] = pd.to_numeric(model_data['storeys_above_ground'], errors='coerce')

                # %% create TEASER project
        # create one project for the whole district
        prj = Project(load_data=True)
        prj.name = self.scenario_name
        print(f"Creating buildings for {self.scenario_name}")
        for building in self.district:
            print(f"Creating building {building['buildingFeatures']['building']}")
            # check if building type is residential or non residential 
            if building["buildingFeatures"]["building"] in  RESIDENTIAL_BUILDING_TYPES:
   
            
                # convert short names into designation needes for TEASER
                building_type = bldgs["buildings_long"][bldgs["buildings_short"].index(building["buildingFeatures"]["building"])]
                retrofit_level = bldgs["retrofit_long"][bldgs["retrofit_short"].index(building["buildingFeatures"]["retrofit"])]

                
                # If a an advanced model is presented, the number of floors and the height of the floors can be taken from the model file
                if self.advancedModel is not None:
                    number_of_floors = model_data['storeys_above_ground'].values[
                        building['buildingFeatures'].id
                    ]
                    height_of_floors = model_data['average_floor_height'].values[building['buildingFeatures'].id]
                
                else:  
                    number_of_floors = 3
                    height_of_floors = 3.125
                # adds residentials buildings to TEASER project
                # To Do: Write code to add non residential buildings 

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
                    teaser_id = self.building_dict[building["buildingFeatures"]["id"]]

                    building["envelope"] = Envelope(prj=prj,
                                                    building_params=building["buildingFeatures"],
                                                    construction_type=retrofit_level,
                                                    file_path = self.filePath,
                                                    teaser_id=teaser_id)
                    

                    # %% create user object
                    # containing number occupants, electricity demand,...
                    building["user"] = Users(building=building["buildingFeatures"]["building"],
                                            area=building["buildingFeatures"]["area"])

                    # %% calculate design heat loads
                    # at norm outside temperature
                    building["heatload"] = building["envelope"].calcHeatLoad(site=self.site, method="design")
                    # at bivalent temperature
                    building["bivalent"] = building["envelope"].calcHeatLoad(site=self.site, method="bivalent")
                    # at heatimg limit temperature
                    building["heatlimit"] = building["envelope"].calcHeatLoad(site=self.site, method="heatlimit")
                    # for drinking hot water
                    building["dhwload"] = bldgs["dhwload"][bldgs["buildings_short"].index(building["buildingFeatures"]["building"])] * building["user"].nb_flats
            # Check if the building type is a supported non residential building. 
            elif building["buildingFeatures"]["building"] in NON_RESIDENTIAL_BUILDING_TYPES:
                 # If a an advanced model is presented, the number of floors and the height of the floors can be taken from the model file
                if self.advancedModel is not None:
                    number_of_floors = model_data['storeys_above_ground'].values[
                        building['buildingFeatures'].id
                    ]
                    height_of_floors = model_data['average_floor_height'].values[building['buildingFeatures'].id]
                else:
                    number_of_floors = 3
                    height_of_floors = 3.125

                nrb_prj = NonResidential(
                        usage=building["buildingFeatures"]["building"],
                        name="IWUNonResidentialBuilding",
                        year_of_construction=building["buildingFeatures"]["year"],
                        number_of_floors=number_of_floors,
                        height_of_floors=height_of_floors,
                        net_leased_area=building["buildingFeatures"]["area"],)
                # %% create envelope object
                # containing all physical data of the envelope
                
                building["envelope"] = Envelope(prj=nrb_prj,
                                                building_params=building["buildingFeatures"],
                                                construction_type=None,
                                                file_path = self.filePath)
              
                
                #illuminance = Sun

                # %% create user object
                # containing number occupants, electricity demand,...
                nb_of_days = self.timestamp.dt.date.nunique()
                building["user"] = NonResidentialUsers(building_usage=building["buildingFeatures"]["building"],
                                                       area=building["buildingFeatures"]["area"],
                                                       envelope= building["envelope"],
                                                       file=self.filePath, site=self.site, time=self.time, nb_of_days=nb_of_days)
            
                
                

                # %% calculate design heat loads
                # at norm outside temperature
                building["heatload"] = building["envelope"].calcHeatLoad(site=self.site, method="design")
                # at bivalent temperature
                building["bivalent"] = building["envelope"].calcHeatLoad(site=self.site, method="bivalent")
                # at heatimg limit temperature
                building["heatlimit"] = building["envelope"].calcHeatLoad(site=self.site, method="heatlimit")
                # for drinking hot water
                # To-Do figure hot water demand out for Non Residential
                # in DIBS the IWU Approach of Teilenergiekennwerte is chosen 
                # 
                # building["dhwload"] = bldgs["dhwload"][bldgs["buildings_short"].index(building["buildingFeatures"]["building"])] * building["user"].nb_flats
            elif building["buildingFeatures"]["building"] not in NON_RESIDENTIAL_BUILDING_TYPES and building["buildingFeatures"]["building"] not in RESIDENTIAL_BUILDING_TYPES:
                print(f"The building type {building['buildingFeatures']['building']} is currently not supported. Please check the type of {building} and try again.")
            else:
                raise AttributeError(f"The building type {building['buildingFeatures']['building']} is currently not supported. ")



    def generateDemands(self, calcUserProfiles:bool=True, saveUserProfiles:bool=True, savePath:str =None):
        """
        Generate occupancy profile, heat demand, domestic hot water demand and heating demand

        Parameters
        ----------
        calcUserProfiles: bool, optional
            True: calculate new user profiles
            False: load user profiles from file
        saveUserProfiles: bool, optional
            True for saving calculated user profiles in workspace (Only taken into account if calcUserProfile is True)
        savePath: string, optional
            Optional name to save the user profiles in a different folder than the default one 

        Returns
        -------
        """
        set = []
        if not os.path.exists(self.resultPath):
            os.makedirs(self.resultPath)
        if os.path.exists(self.resultPath):
            print("The folder already exists. Will overwrite existing files.")
        for building in self.district:
            if building["buildingFeatures"]["building"] in RESIDENTIAL_BUILDING_TYPES:
                # %% create unique building name
                # needed for loading and storing data with unique name
                # name is composed of building type, number of flats, serial number of building of this properties
                name = str(building["buildingFeatures"]["id"]) + "_" + building["buildingFeatures"]["building"] + "_" + str(building["user"].nb_flats)
                if name not in set:
                    set.append(name)
                    self.counter[name] = count()
                nb = next(self.counter[name])
                building["unique_name"] = name + "_" + str(nb)
            elif building["buildingFeatures"]["building"] in NON_RESIDENTIAL_BUILDING_TYPES:
                name = str(building["buildingFeatures"]["id"]) + "_" + building["buildingFeatures"]["building"] + "_" + str(building["user"].nb_occ)
                if name not in set:
                    set.append(name)
                    self.counter[name] = count()
                nb = next(self.counter[name])
                building["unique_name"] = name + "_" + str(nb)
            elif building["buildingFeatures"]["building"] not in NON_RESIDENTIAL_BUILDING_TYPES and building["buildingFeatures"]["building"] not in RESIDENTIAL_BUILDING_TYPES:
                print(f"The building type {building['buildingFeatures']['building']} is currently not supported. "
                      f"Please check the type of building {building} and try again.")
            else:
                raise AttributeError(f"The building type {building['buildingFeatures']['building']} is currently not supported. "
                                     f"Please check the type of building {building} and try again.")
                

            # calculate or 
            # load user profiles
            if calcUserProfiles:
                building["user"].calcProfiles(site=self.site,
                                              time_horizon=self.time["dataLength"],
                                              time_resolution=self.time["timeResolution"])
                if saveUserProfiles:
                    if savePath is not None:
                        savePath = os.path.join(self.resultPath, 'results', 'demands', savePath)
                        building["user"].saveProfiles(building["unique_name"], savePath)
                    else: 
                        building["user"].saveProfiles(building["unique_name"], self.resultPath)

                print("Calculate demands of building " + building["unique_name"])

            else:
                # To Do -> implement loading of user profiles
                building["user"].loadProfiles(building["unique_name"], self.resultPath)
                print("Load demands of building " + building["unique_name"])

            building["envelope"].calcNormativeProperties(self.SunRad,building["user"].gains)

            # calculate heating profiles
            building["user"].calcHeatingProfile(site=self.site,
                                                envelope=building["envelope"],
                                                time_resolution=self.time["timeResolution"])

            if saveUserProfiles :
                if savePath is not None:
                    savePath = os.path.join(self.resultPath, savePath)
                    building["user"].saveProfiles(building["unique_name"], savePath)
                    print(f"Save heating profile of building {building['unique_name']} in {savePath}")
                else:
                    building["user"].saveProfiles(building["unique_name"], self.resultPath)
                    print(f"Save heating profile of building {building['unique_name']} in {savePath}")

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


    def plot(self, mode='default', initialTime=0, timeHorizon=31536000, 
             savePlots=True, timeStamp=False, show=False):
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
