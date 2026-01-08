# -*- coding: utf-8 -*-

import json
import pickle
import os
import sys
import copy
import datetime
import multiprocessing

import numpy as np
import openpyxl
import pandas as pd
import random as rd
import holidays as hol
from teaser.project import Project
from .envelope import Envelope
from .solar import Sun
from .users import Users
from .system import BES
from .system import CES
from .plots import DemandPlots
from .optimizer import Optimizer
from .KPIs import KPIs
from .non_residential import NonResidential
import districtgenerator.functions.clustering_medoid as cm
from districtgenerator.data_handling.config import GlobalConfig, load_global_config, LocationConfig, TimeConfig, DesignBuildingConfig, EcoConfig, PhysicsConfig, EHDOConfig, GurobiConfig, HeatGridConfig, CalendarConfig
from districtgenerator.data_handling.central_device_config import CentralDeviceConfig
from districtgenerator.data_handling.decentral_device_config import DecentralDeviceConfig


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

    def __init__(self,
                 scenario_name = None,
                 resultPath = None,
                 scenario_file_path = None,
                 srcPath = os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 filePath = None,
                 env_path = None,
                 run_name: str = None):
        """
        Constructor of Datahandler class.

        Parameters
        ----------
        scenario_name : str, optional
            Name of the scenario file. If none given, takes scenario_name from globalConfig else "example".
        resultPath : str, optional
            Path to save results. If None, it defaults to 'srcPath/results'.
        scenario_file_path : str, optional
            Path to the scenario file. If None, it defaults to 'filePath/scenarios'.
        srcPath : str, optional
            Source path of the district generator. The default is the parent directory of this file.
        filePath : str, optional
            Path to the data directory. If None, it defaults to 'srcPath/data'.
        env_path : str, optional
            Path to the environment configuration file. If None, it defaults to the global configuration file.

        Returns
        -------
        None.
        """
        self.global_config: GlobalConfig = load_global_config(env_file=env_path)

        self.conf_scenario_name = self.global_config.scenario_name.scenario_name
        if filePath is None:
            filePath = os.path.join(srcPath, 'data')

        self.initial_day = None
        self.district = []
        self.u_values = ()
        self.scenario_name = scenario_name or self.global_config.scenario_name.scenario_name or "example"
        self.scenario = None
        self.total_building_area = None
        # Config data
        self.site = {}
        self.time = {}
        self.design_building_data = {}
        self.physics = {}
        self.decentral_device_data = {}
        self.params_ehdo_technical = {}
        self.params_ehdo_model = {}
        self.central_device_data = {}
        self.calendar = {}
        self.ecoData = {}
        self.heat_grid_data = {}
        self.pipe_data = {}
        self.gurobiConfig = self.global_config.gurobi
        # Additional attributes
        self.counter = {}
        self.calcThick = self.global_config.flags.calcThick
        self.calcOcc = self.global_config.flags.calcOcc
        self.calcOccProf = self.global_config.flags.calcOccProf
        self.building_dict = {} # Dictionary to store Residential Building IDs
        self.srcPath = srcPath
        self.filePath = filePath
        if scenario_file_path is not None:
            self.scenario_file_path = scenario_file_path
        else:
            self.scenario_file_path = os.path.join(self.filePath, 'scenarios')

        if resultPath is not None:
            self.resultPath = resultPath
        else:
            self.resultPath = os.path.join(self.srcPath, 'results')

        if run_name is not None:
            # Create the path to demands and generation
            self.demands_path = os.path.join(self.resultPath, 'demands', self.scenario_name) # test if always necessary, run_name)
            self.generation_path = os.path.join(self.resultPath, 'generation', self.scenario_name, run_name)
            self.optimization_path = os.path.join(self.resultPath, 'optimization', self.scenario_name, run_name)

        else:
            self.demands_path = os.path.join(self.resultPath, 'demands', self.scenario_name)
            self.generation_path = os.path.join(self.resultPath, 'generation', self.scenario_name)
            self.optimization_path = os.path.join(self.resultPath, 'optimization', self.scenario_name)


        os.makedirs(self.demands_path, exist_ok=True)
        os.makedirs(self.generation_path, exist_ok=True)
        os.makedirs(self.optimization_path, exist_ok=True)



        self.KPIs = None
        self.load_all_data(
            site_config=self.global_config.location,
            time_config=self.global_config.time,
            design_building_config=self.global_config.design_building,
            physics_config=self.global_config.physics,
            decentral_config=self.global_config.decentral,
            ehdo_config=self.global_config.ehdo,
            eco_config=self.global_config.eco,
            central_config=self.global_config.central,
            calendar_config=self.global_config.calendar,
            heat_grid_config=self.global_config.heatgrid
        )

        self.buildings_completed = 0
        self.buildings_total = 0
        self.progress_file = os.path.join(self.resultPath, 'progress.json')

    def get_progress(self):
        return {
            'completed': self.buildings_completed,
            'total': self.buildings_total,
            'percentage': (self.buildings_completed / max(self.buildings_total, 1)) * 100,
        }

    def save_progress(self):
        if self.progress_file:
            progress_data = self.get_progress()

            try:
                with open(self.progress_file, 'w') as f:
                    json.dump(progress_data, f)
            except Exception as e:
                print(f"Couldn't save calculation progress: {e}")

    def load_all_data(self, site_config: LocationConfig,
                      time_config: TimeConfig,
                      design_building_config: DesignBuildingConfig,
                      physics_config: PhysicsConfig,
                      decentral_config: DecentralDeviceConfig,
                      ehdo_config: EHDOConfig,
                      eco_config: EcoConfig,
                      central_config: CentralDeviceConfig,
                      calendar_config: CalendarConfig,
                      heat_grid_config: HeatGridConfig):
        """
        Load all data needed for district generation from configuration files.

        Parameters
        ----------
        site_config : LocationConfig
            Location configuration data.
        time_config : TimeConfig
            Time configuration data.
        design_building_config : DesignBuildingConfig
            Design building configuration data.
        physics_config : PhysicsConfig
            Physics configuration data.
        decentral_config : DecentralDeviceConfig
            Decentral device configuration data.
        ehdo_config : EHDOConfig
            EHDO model configuration data.
        eco_config : EcoConfig
            Economic configuration data.
        central_config : CentralDeviceConfig
            Central device configuration data.
        calendar_config : CalendarConfig
            Calendar configuration data.
        heat_grid_config : HeatGridConfig
            Heat grid configuration data.
        Returns
        -------
        None.
        """

        # %% load scenario file with building information
        self.scenario = {}
        self.scenario = pd.read_csv(self.scenario_file_path + "/" + self.scenario_name + ".csv",
                                    header=0, delimiter=";")

        # %% load information about of the site under consideration (used in generateEnvironment)
        # important for weather conditions
        for attr, value in site_config.__dict__.items():
            self.site[attr] = value

        # %% load time information and requirements (used in generateEnvironment)
        # needed for data conversion into the right time format
        for attr, value in time_config.__dict__.items():
            self.time[attr] = value

        # %% load general building information
        # contains definitions and parameters that affect all buildings (used in envelope and system BES/CES)
        for attr, value in design_building_config.__dict__.items():
            self.design_building_data[attr] = value

        # load building physics data (used in envelope and system BES/CES)
        for attr, value in physics_config.__dict__.items():
            self.physics[attr] = value

        # Load list of possible devices (used in system BES)
        # Iterate over all attributes of the config instance
        for attribute, value in decentral_config.__dict__.items():
            # Split the attribute into abbreviation and parameter name parts based on the first underscore
            abbr, _, param = attribute.partition("_")

            # Initialize the sub-dictionary if needed.
            if abbr not in self.decentral_device_data:
                self.decentral_device_data[abbr] = {}
            self.decentral_device_data[abbr][param] = value

        for attr, value in ehdo_config.__dict__.items():
            self.params_ehdo_model[attr] = value

        # load economic and ecologic data (of the district generator) (used in system CES)
        for attr, value in eco_config.__dict__.items():
            self.ecoData[attr] = value

        # Load list of possible devices (used in system BES)
        # Iterate over all attributes of the config instance
        for attribute, value in central_config.__dict__.items():
            # Split the attribute into abbreviation and parameter name parts based on the first underscore
            abbr, _, param = attribute.partition("_")

            # Initialize the sub-dictionary if needed.
            if abbr not in self.central_device_data:
                self.central_device_data[abbr] = {}
            self.central_device_data[abbr][param] = value

        # load calendar data (used in generateDemands and generateEnvironment)
        for attr, value in calendar_config.__dict__.items():
            self.calendar[attr] = value

        for attr, value in heat_grid_config.__dict__.items():
            self.heat_grid_data[attr] = value

        csv_path = os.path.join(self.filePath, 'pipe_specifications.csv')
        self.pipe_data = pd.read_csv(csv_path, sep=";")

    def select_plz_data(self):
        """
        Select the closest TRY weather station for the location of the postal code.

        Returns
        -------
        None.
        """

        # Try to find the location of the postal code and matched TRY weather station
        try:
            workbook = openpyxl.load_workbook(self.filePath + "/plz_geocoord_matched.xlsx")
            sheet = workbook.active

            for row in sheet.iter_rows(values_only=True):
                if self.site["zip"] == str(row[0]):
                    weatherdatafile = row[3]
                    self.site["Location"] = weatherdatafile[8:-9]
                    break
            else:
                # If postal code cannot be found: Message and select weather data file from Aachen
                raise ValueError("Postal code cannot be found")


        except Exception as e:
            # If postal code cannot be found: Message and select weathter data file from Aachen
            print("Postal code cannot be found, location changed to Aachen")
            self.site["zip"] = "52064"
            self.site["Location"] = 507755060854

            # deprecated?
            ## Add new weatherdatafile_location, if you want an individual location:
            ## Files can be found here: https://www.dwd.de/DE/leistungen/testreferenzjahre/testreferenzjahre.html
            ## Every file has to be stored in the folder reffering to the correct Year and season in the subfolders of '.\districtgenerator\data\weather\
            ## Example: TRY2015_507755060854_Wint.dat has to be stored in '.\districtgenerator\data\weather\TRY_2015_Winter'
            ## Uncomment the following line:
            # weatherdatafile_location = 507755060854

    def get_holidays(self, country_code: str, year: int, state: str = None):
        """
        Get the Julian day (day of the year) for holidays in a specific country, year, and state.

        Parameters
        ----------
            country_code : string
                The country's ISO 3166-1 alpha-2 code (e.g., 'DE' for Germany).
            year : integer
                The year for which to retrieve holidays.
            state : string
                The state or region subdivision code (e.g., 'NW' for North Rhine-Westphalia in Germany).

        Returns
        -------
            julian_holidays : list
                A list of tuples containing the Julian day of the holiday.
        """
        try:
            # Initialize the holidays object for the given country, year, and state
            holidays = hol.country_holidays(country_code, years=year, subdiv=state)

            # Get the Julian day for each holiday
            julian_holidays = [holiday_date.timetuple().tm_yday for holiday_date in holidays.keys()]

            return julian_holidays
        except KeyError:
            return f"Invalid country or state code '{country_code}', '{state}'. Please provide valid codes."

    def generateEnvironment(self):
        """
        Load physical district environment - site and weather.

        Returns
        -------
        None.
        """
        # %% load first day of the year
        # todo: maybe put in config if more TRY years are added?
        if self.site["TRYYear"] == "TRY2015":
            first_row = 35
            self.initial_day = 3 # Thursday
        elif self.site["TRYYear"] == "TRY2045":
            first_row = 37
            self.initial_day = 6 # Sunday


        self.select_plz_data()
        # load weather data
        # select the correct file depending on the TRY weather station location
        weatherData = np.loadtxt(os.path.join(self.filePath, "weather", "TRY_" + self.site["TRYYear"][-4:] + "_" + self.site["TRYType"])
            + "/"
            + self.site["TRYYear"] + "_"
            + str(self.site["Location"]) + "_" + str(self.site["TRYType"])
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
        [temp_sunDirect, temp_sunDiff, temp_tempe, temp_wind, temp_rhum, temp_pre] = \
            [weatherData[:, 12], weatherData[:, 13], weatherData[:, 5], weatherData[:, 8], weatherData[:, 11], weatherData[:, 6]]

        self.time["timeSteps"] = int(self.time["dataLength"] / self.time["timeResolution"])

        # load the holidays
        if self.site["TRYYear"] == "TRY2015":
            self.calendar["holidays"] = self.get_holidays(country_code="DE", year=2015)
        elif self.site["TRYYear"] == "TRY2045":
            self.calendar["holidays"] = self.get_holidays(country_code="DE", year=2045)

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
                                     temp_tempe)[0:-1]
        self.site["wind_speed"] = np.interp(np.arange(0, self.time["dataLength"] + 1, self.time["timeResolution"]),
                                            np.arange(0, self.time["dataLength"] + 1, self.time["dataResolution"]),
                                            temp_wind)[0:-1]
        self.site["r_humidity"] = np.interp(np.arange(0, self.time["dataLength"] + 1, self.time["timeResolution"]),
                                            np.arange(0, self.time["dataLength"] + 1, self.time["dataResolution"]),
                                            temp_rhum)[0:-1]
        self.site["pressure"] = np.interp(np.arange(0, self.time["dataLength"] + 1, self.time["timeResolution"]),
                                            np.arange(0, self.time["dataLength"] + 1, self.time["dataResolution"]),
                                            temp_pre)[0:-1]

        self.site["SunTotal"] = self.site["SunDirect"] + self.site["SunDiffuse"] # This is the GHI (Global Horizontal Irradiance)

        # Load other site-dependent values based on DIN/TS 12831-1:2020-04
        filePath = os.path.join(self.filePath, 'site_data.txt')
        site_data = pd.read_csv(filePath, delimiter='\t', dtype={'Zip': str})

        # Filter data for the specific zip code
        filtered_data = site_data[site_data['Zip'] == self.site["zip"]]

        # extract the needed values
        self.site["altitude"] = filtered_data.iloc[0]['Altitude']
        self.site["location"] = [filtered_data.iloc[0]['Latitude'],filtered_data.iloc[0]['Longitude']]
        self.site["T_ne"] = filtered_data.iloc[0]['T_ne'] # norm outside temperature for calculating the design heat load
        self.site["T_me"] = filtered_data.iloc[0]['T_me'] # mean annual temperature for calculating the design heat load

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
                                                beamRadiation=self.site["SunDirect"],
                                                diffuseRadiation=self.site["SunDiffuse"],
                                                albedo=self.site["albedo"])

    def initializeBuildings(self):
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
        name_pool = []
        self.building_dict = {}

        # Initialize buildings for scenario
        # Loop over all buildings using iterrows
        for bldg_id, row in self.scenario.iterrows():
            bldg_id = int(bldg_id)
            building = {}

            # Store features of the observed building
            building["buildingFeatures"] = row.to_dict()  # Convert row to dictionary

            # Add thermal transmittance if available
            if "thermalTransmittanceFacade" in self.scenario.columns:
                building["buildingFeatures"]["thermalTransmittance"] = (
                    row["thermalTransmittanceFacade"],
                    row["thermalTransmittanceRoof"],
                    row["thermalTransmittanceFloor"],
                    row["thermalTransmittanceWindow"]
                )
            else:
                building["buildingFeatures"]["thermalTransmittance"] = None

            # Create unique building name
            name = f"{bldg_id}_{row['building']}"

            # Check for duplicate names
            if name in name_pool:
                print(f"Duplicate name: {name}, skipping")
                continue
            name_pool.append(name)

            # Assign the unique name to the building
            building["unique_name"] = name

            # Append building to district
            self.district.append(building)
            self.building_dict[bldg_id] = len(self.district) - 1

            # Count number of buildings to predict the approximate calculation time
            if row["building"] in ("SFH", "TH"):
                num_sfh += 1
            elif row["building"] in ("MFH", "AB"):
                num_mfh += 1

        # Calculate calculation time for the whole district generation
        duration += datetime.timedelta(seconds=3 * num_sfh + 12 * num_mfh)
        print(f"This calculation will take about {duration}.")

    def generateBuildings(self):
        """
        Load building envelope and user data.

        Returns
        -------
        None.
        """

        # %% load general building information
        # contains definitions and parameters that affect all buildings
        bldgs = self.design_building_data

        # %% create TEASER project
        # create one project for the whole district
        prj = Project()
        prj.name = self.scenario_name

        for building in self.district:

            # convert short names into designation needed for TEASER
            building_type = bldgs["buildings_long"][bldgs["buildings_short"].index(building["buildingFeatures"]["building"])]

            # add buildings to TEASER project
            if building_type in {"single_family_house", "multi_family_house", "terraced_house", "apartment_block"}:
                retrofit_level = bldgs["retrofit_long"][bldgs["retrofit_short"].index(building["buildingFeatures"]["retrofit"])]
                if retrofit_level == "tabula_standard":
                    construction_data = 'tabula_de_standard'
                    if building["buildingFeatures"]["year"]>2015:
                        building["buildingFeatures"]["year"]=2015  #bugfix for tabula standard
                elif retrofit_level == "tabula_retrofit":
                    construction_data = 'tabula_de_retrofit'
                elif retrofit_level == "tabula_adv_retrofit":
                    construction_data = 'tabula_de_adv_retrofit'
                else: construction_data = "tabula_standard" #bugfix

                height = building["buildingFeatures"]["height"]
                number_of_floors = building["buildingFeatures"]["number_of_floors"]
                if number_of_floors == 0:
                    # Determining the number of floors in a building based on its type.
                    # The method estimates the number of floors by:
                    # - Assigning a range of possible floor areas per level based on building type.
                    # - Randomly selecting a value within the assigned range using the TABULA German Building Typology.
                    # - Calculating the total number of floors by dividing the building’s total floor area
                    #   by the selected single-floor area.

                    if building_type == "single_family_house":
                        one_floor_area = rd.randint(62, 115)  # Source: TABULA German Building Typology
                        # Calculate the number of floors, rounding to the nearest integer and ensuring at least 1
                        number_of_floors = max(1, round(building["buildingFeatures"]["area"] / one_floor_area))

                    elif building_type == "terraced_house":
                        one_floor_area = rd.randint(50, 73)  # Source: TABULA German Building Typology
                        # Calculate the number of floors, rounding to the nearest integer and ensuring at least 1
                        number_of_floors = max(1, round(building["buildingFeatures"]["area"] / one_floor_area))

                    elif building_type == "multi_family_house":
                        # Generate a valid one-floor area and number of floors in one step
                        one_floor_area = rd.randint(102, 971)  # Source: TABULA German Building Typology
                        # Calculate the number of floors, rounding to the nearest integer and ensuring at least 2
                        number_of_floors = max(2, round(building["buildingFeatures"]["area"] / one_floor_area))
                        # Cap the number of floors to a maximum of 8
                        if number_of_floors > 8:
                            number_of_floors = 8

                    elif building_type == "apartment_block":
                        one_floor_area = rd.randint(350, 540)  # Source: TABULA German Building Typology
                        # Calculate the number of floors, rounding to the nearest integer and ensuring at least 3
                        number_of_floors = max(3, round(building["buildingFeatures"]["area"] / one_floor_area))

                height_of_floors = height / number_of_floors
                # Determining the typical floor height based on the building's construction year.
                # Older buildings (constructed before 1960) generally have higher ceilings, while newer buildings
                # (built from 1960 onwards) tend to have lower ceilings.
                # Source: https://www.wohnung.com/ratgeber/418/alt-und-neubau-deckenhoehe
                if height_of_floors < 2.5:
                    if building["buildingFeatures"]["year"] < 1960:
                        height_of_floors = 3.3  # m
                    elif building["buildingFeatures"]["year"] >= 1960:
                        height_of_floors = 2.5  # m

                if building["buildingFeatures"]["year"] < 1960:
                    height_of_floors = 3.3  # m
                elif building["buildingFeatures"]["year"] >= 1960:
                    height_of_floors = 2.5  # m

                # add buildings to TEASER project
                prj.add_residential(name="ResidentialBuildingTabula",
                                    geometry_data="tabula_de_" + building_type,
                                    construction_data=construction_data,
                                    year_of_construction=building["buildingFeatures"]["year"],
                                    number_of_floors=number_of_floors,
                                    height_of_floors=height_of_floors,
                                    net_leased_area=building["buildingFeatures"]["area"])


                building["buildingFeatures"] = building["buildingFeatures"].copy()
                building["buildingFeatures"]["id_teaser"] = len(prj.buildings) - 1

                # %% create envelope object
                extra = [building["buildingFeatures"]["year"], building["buildingFeatures"]["retrofit"], building["buildingFeatures"]["gmlId"] if "gmlId" in building["buildingFeatures"] else building["buildingFeatures"]["id"], building["buildingFeatures"]["building"]]
            # containing all physical data of the envelope
                building["envelope"] = Envelope(prj=prj,
                                                building_params=building["buildingFeatures"],
                                                construction_data=construction_data,
                                                physics=self.physics,
                                                design_building_data=self.design_building_data,
                                                file_path=self.filePath,
                                                u_values=building["buildingFeatures"]["thermalTransmittance"],
                                                extra = extra,
                                                calcThick = self.calcThick)
            else:

                retrofit_level = bldgs["retrofit_long_non_residential"][bldgs["retrofit_short_non_residential"].index(building["buildingFeatures"]["retrofit"])]
                construction_type = bldgs["construction_type_long"][bldgs["construction_type_short"].index(building["buildingFeatures"]["construction_type"])]

                if building["buildingFeatures"]["year"] < 1960:
                    height_of_floors = 3.3  # m
                elif building["buildingFeatures"]["year"] >= 1960:
                    height_of_floors = 2.5  # m

                nrb_prj = NonResidential(
                        usage=building["buildingFeatures"]["building"],
                        name="NonResidentialBuilding",
                        year_of_construction=building["buildingFeatures"]["year"],
                        height_of_floors=height_of_floors,
                        net_leased_area=building["buildingFeatures"]["area"],          # Total net leased area of the building, or of the building part if it is a mixed-use building.
                        total_building_area=(                                          # Total net leased area of building
                            building["buildingFeatures"]["area"] if self.total_building_area is None
                            else self.total_building_area),
                        construction_type=construction_type,
                        retrofit_level=retrofit_level)

                # %% create envelope object
                # containing all physical data of the envelope

                building["envelope"] = Envelope(prj=nrb_prj,
                                                building_params=building["buildingFeatures"],
                                                construction_type=construction_type,
                                                physics=self.physics,
                                                design_building_data=self.design_building_data,
                                                file_path=self.filePath)

            # %% create user object
            # containing number occupants, electricity demand,...
            building["user"] = Users(building=building["buildingFeatures"]["building"],
                                     area=building["buildingFeatures"]["area"],
                                     year_of_construction=building["buildingFeatures"]["year"],
                                     retrofit=building["buildingFeatures"]["retrofit"],
                                     nb_occ=building["buildingFeatures"]["nb_occ"] if ("nb_occ" in building["buildingFeatures"] and not pd.isna(building["buildingFeatures"]["nb_occ"])) else None,
                                     nb_flats=int(float(building["buildingFeatures"]["nb_flats"])) if "nb_flats" in building["buildingFeatures"] else None,
                                     dict= self.srcPath,
                                     scenario_name=self.scenario_name,
                                     calcOcc = self.calcOcc,
                                     calcOccProf = self.calcOccProf)

            night_setback = building["buildingFeatures"]["night_setback"]
            # %% calculate design heat loads
            # at norm outside temperature
            building["envelope"].heatload = building["envelope"].calcHeatLoad(site=self.site, method="design", night_setback = night_setback)
            # at bivalent temperature
            building["envelope"].bivalent = building["envelope"].calcHeatLoad(site=self.site, method="bivalent", night_setback = night_setback)
            # at heating limit temperature
            building["envelope"].heatlimit = building["envelope"].calcHeatLoad(site=self.site, method="heatlimit", night_setback = night_setback)
            # for drinking hot water
            building["dhwpower"] = bldgs["dhwpower"][bldgs["buildings_short"].index(building["user"].building)] * building["buildingFeatures"]["area"]

            index = bldgs["buildings_short"].index(building["buildingFeatures"]["building"])
            building["buildingFeatures"] = building["buildingFeatures"].copy()
            building["buildingFeatures"]["mean_drawoff_dhw"] = bldgs["mean_drawoff_vol_per_day"][index]

    def generateDemands(self, name = None, calcUserProfiles=True, saveUserProfiles=True,  max_threads=8):
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

        args_list = [(self, building, calcUserProfiles, saveUserProfiles) for building in self.district]

        self.buildings_total = len(self.district)
        self.buildings_completed = 0

        results = []
        self.save_progress()

        with multiprocessing.Pool(processes=max_threads) as pool:
            for i, result in enumerate(pool.imap_unordered(generate_demands_worker_wrapper, args_list)):
                self.buildings_completed += 1
                results.append(result)

                self.save_progress()

                print(f"building {self.buildings_completed}/{self.buildings_total} calculated " +
                      f"({(self.buildings_completed / self.buildings_total) * 100:.1f}%): {result.get('unique_name', '')}")

        for result in results:
            building = next(b for b in self.district if b["unique_name"] == result["unique_name"])
            building["user"].elec = result["elec"]
            building["user"].dhw = result["dhw"]
            building["user"].cooling = result["cooling"]
            building["user"].heat = result["heating"]
            building["gmlId"] = result["id"]
            building["user"].occ = result["occ"]
            building["user"].carcharging_ondemand =  result["carcharging_ondemand"]
            building["user"].carprofile = result["carprofile"]
            building["user"].ev_capacity = result.get("ev_capacity")
            building["user"].gains = result["gains"]
            building["user"].nb_units = result["nb_units"]
            building["user"].nb_occ = result["nb_occ"]
            building["envelope"] = result["envelope"]
            building_features = building["buildingFeatures"].copy()
            building_features["night_setback"] = result["night_setback"]
            building["buildingFeatures"] = building_features

        self.save_progress()

        print("Finished generating demands with multiprocessing!")

    def generate_demands_worker(self, building, calcUserProfiles, saveUserProfiles):
        """
        :param building:
        :param calcUserProfiles: bool
            True: calculate new user profiles.
            False: load user profiles from file.
            The default is True.
        :param saveUserProfiles: bool
            True for saving calculated user profiles in workspace (Only taken into account if calcUserProfile is True).
            The default is True.
        """
        print(f'starting {building["unique_name"]}')

        # calculate or load user profiles
        if calcUserProfiles:
            building["user"].calcProfiles(site=self.site,
                                          holidays=self.calendar["holidays"],
                                          time_resolution=self.time["timeResolution"],
                                          time_horizon=self.time["dataLength"],
                                          building_devices_data=self.decentral_device_data,
                                          building=building,
                                          path=self.demands_path,
                                          initial_day = self.initial_day)

            if saveUserProfiles:
                self.saveProfiles(name=building["unique_name"],
                                  elec=building["user"].elec,
                                  dhw= building["user"].dhw,
                                  occ= building["user"].occ,
                                  gains= building["user"].gains,
                                  carcharging_ondemand=building["user"].carcharging_ondemand,
                                  carprofile=building["user"].carprofile,
                                  nb_units= building["user"].nb_units,
                                  nb_occ= building["user"].nb_occ,
                                  ev_capacity=building["user"].ev_capacity or [0],
                                  heatload= building["envelope"].heatload,
                                  bivalent= building["envelope"].bivalent,
                                  heatlimit= building["envelope"].heatlimit,
                                  thick_req= building["envelope"].thick_req,
                                  path=os.path.join(self.demands_path))
                    #building["user"].saveProfiles(building["unique_name"], building["envelope"], os.path.join(self.resultPath, 'demands'))

            # print("Calculate demands of building " + building["unique_name"])

        else:
            (building["user"].elec, building["user"].dhw,
             building["user"].occ, building["user"].gains,
             building["user"].carcharging_ondemand, building["user"].carprofile, building["user"].nb_flats, building["user"].nb_main_rooms,
             building["user"].nb_occ, building["user"].ev_capacity, building["envelope"].heatload,
             building["envelope"].bivalent,
             building["envelope"].heatlimit) = self.loadProfiles(building["unique_name"],
                                                                 os.path.join(self.demands_path))
            (building["user"].heat, building["user"].cooling, building["gmlId"]) = self.loadHeatingProfiles(building["unique_name"], os.path.join(self.demands_path))
            # building["user"].loadProfiles(building["unique_name"], os.path.join(self.resultPath, 'demands'))
            print("Load demands of building " + building["unique_name"])

        building["envelope"].calcNormativeProperties(self.site["SunRad"], building["user"].gains)

        night_setback = building["buildingFeatures"]["night_setback"]

        is_cooled = building["user"].cooling is not None and building["user"].cooling > 0

        # calculate or load heating profiles
        if calcUserProfiles:
            building["user"].calcHeatingProfile(site=self.site,
                                                envelope=building["envelope"],
                                                night_setback=night_setback,
                                                is_cooled=is_cooled,
                                                calendar=self.calendar,
                                                time_resolution=self.time["timeResolution"]
                                                )

            if saveUserProfiles:
                idArray = []
                idArray.append(building["buildingFeatures"]["gmlId"] if "gmlId" in building["buildingFeatures"] else building["buildingFeatures"]["id"])
                self.saveHeatingProfile(heat=building["user"].heat,
                                        cooling=building["user"].cooling,
                                        name=building["unique_name"],
                                        gmlId=idArray,
                                        path=os.path.join(self.demands_path))
                #building["user"].saveHeatingProfile(building["unique_name"], os.path.join(self.resultPath, 'demands'))
            else:
                heat, cooling, id = self.loadHeatingProfiles(name=building["unique_name"],
                                                             path=(self.demands_path))
                building["user"].heat = heat
                building["user"].cooling = cooling
                building["gmlId"] = id

        print("Finished generating demands!")

    def generateDistrictComplete(self, name = None, calcUserProfiles=True, saveUserProfiles=True,
                                 designDevs=True, saveGenProfiles=True, optimization=True, pv_standard=True):
        """
        All in one solution for district and demand generation.

        Parameters
        ----------

        name: string, optional
            option to set a unique name for the district scenario. Else building["unique_name"] will be used.
        calcUserProfiles: bool, optional
            True: calculate new user profiles. Only if generateDemands is True.
            False: load user profiles from file.
            The default is True.
        saveUserProfiles: bool, optional
            True for saving calculated user profiles in workspace (Only taken into account if calcUserProfile is True).
            The default is True.
        designDevs: bool, optional
            Decision if devices (central / decentral) will be designed. The default is True.
        saveGenProfiles: bool, optional
            Decision if generation profiles of designed devices will be saved. Just relevant if 'designDevs=True'.
            The default is True.
        optimization: bool, optional
            Decision if the operation costs for each cluster will be optimized. The default is True.

        Returns
        -------
        None.
        """

        self.initializeBuildings()
        self.generateEnvironment()
        self.generateBuildings()

        # depending on calcUserProfiles either calculate new user profiles or load them from file
        self.generateDemands(name, calcUserProfiles, saveUserProfiles)

        if designDevs:
            if self.district[0]["buildingFeatures"]["heater"] == "heat_grid":
                centralEnergySupply = True
                self.designDevicesComplete(saveGenerationProfiles=saveGenProfiles)
            else:
                centralEnergySupply = False
                self.designDecentralDevices(saveGenerationProfiles=saveGenProfiles, pv_standard=pv_standard)
                self.centralDevices = {}

            if optimization:
                # Within a clustered time series, data points are aggregated across different time periods
                # based on the k-medoids method
                self.clusterProfiles(centralEnergySupply)

    def saveProfiles(self, name, elec, dhw, occ, gains, carcharging_ondemand, carprofile, ev_capacity, nb_units, nb_occ, heatload, bivalent, heatlimit, thick_req, path):
        """
        Save profiles to separate parquet files.

        Parameters
        ----------
        name : string
            Unique building name.
        elec : list
            Hourly electricity demand in W.
        dhw : list
            Hourly domestic hot water demand in W.
        occ : list
            Hourly occupancy of persons.
        gains : list
            Hourly internal gains in W.
        carcharging_ondemand : list
            Hourly electricity demand of EV in W.
        carprofile : list
            Hourly energy demand of EV in Wh.
        nb_units : int
            Number of flats in the building.
        nb_occ : list
            Number of occupants in the building.
        heatload : float
            Design heat load in W.
        bivalent : float
            Bivalent heat load in W.
        heatlimit : float
            Heat limit heat load in W.
        thick_req : list, optional
            Insulation thickness requirements for walls, roof, and floor.
        path : string
            Results path.

        Returns
        -------
        None.
        """
        directory_path = os.path.join(self.demands_path, name)
        os.makedirs(directory_path, exist_ok=True)

        # Create DataFrames directly from the input variables
        elec_df = pd.DataFrame(elec, columns=['elec'])
        dhw_df = pd.DataFrame(dhw, columns=['dhw'])
        occ_df = pd.DataFrame(occ, columns=['occ'])
        gains_df = pd.DataFrame(gains, columns=['gains'])
        carcharging_ondemand_df = pd.DataFrame(carcharging_ondemand, columns=['car'])
        carprofile_df = pd.DataFrame(carprofile, columns=['Electric Vehicle Energy Demand (Wh)'])

        # Sum the values in nb_occ and create a DataFrame
        if isinstance(nb_occ, list):
            total_nb_occ = sum(int(num) for num in nb_occ)  # Calculate the sum
        else:
            total_nb_occ = nb_occ
        nb_occ_df = pd.DataFrame([total_nb_occ], columns=['occ'])
        #nb_occ_list_df = pd.DataFrame([[nb_occ]], columns=['occ list'])
        # todo: idea to save the full list of occupants per building unit for further analysis, does not work properly yet

        # Create DataFrames for building info
        nb_flats_df = pd.DataFrame([nb_units], columns=['Number of Flats or Main Rooms'])
        heatload_df = pd.DataFrame([heatload], columns=['heatload'])
        bivalent_df = pd.DataFrame([bivalent], columns=['bivalent'])
        heatlimit_df = pd.DataFrame([heatlimit], columns=['Heat Limit Heat Load (W)'])
        #print(ev_capacity)
        ev_capacity_df = pd.DataFrame(ev_capacity, columns=['EV Capacity (Wh)'])


        # If thick_req is provided, create DataFrames for insulation
        if thick_req:
            wall_ins_df = pd.DataFrame([thick_req[0]], columns=['Wall Insulation Thickness'])
            roof_ins_df = pd.DataFrame([thick_req[1]], columns=['Roof Insulation Thickness'])
            floor_ins_df = pd.DataFrame([thick_req[2]], columns=['Floor Insulation Thickness'])

        # Define file paths for each DataFrame
        elec_file = os.path.join(directory_path, 'elec.parquet')
        dhw_file = os.path.join(directory_path, 'dhw.parquet')
        occ_file = os.path.join(directory_path, 'occ.parquet')
        gains_file = os.path.join(directory_path, 'gains.parquet')
        carcharging_file = os.path.join(directory_path, 'carcharging.parquet')
        carprofile_file = os.path.join(directory_path, 'carprofile.parquet')
        nb_flats_file = os.path.join(directory_path, 'nb_flats.parquet')
        nb_occ_file = os.path.join(directory_path, 'nb_occ.parquet')
        #nb_occ_list_file = os.path.join(directory_path, 'nb_occ_list.parquet')
        heatload_file = os.path.join(directory_path, 'heatload.parquet')
        bivalent_file = os.path.join(directory_path, 'bivalent.parquet')
        heatlimit_file = os.path.join(directory_path, 'heatlimit.parquet')
        ev_capacity_file = os.path.join(directory_path, 'ev_capacity.parquet')

        # Save each DataFrame to Parquet, overwriting any existing files
        elec_df.to_parquet(elec_file, engine='pyarrow', index=False)
        dhw_df.to_parquet(dhw_file, engine='pyarrow', index=False)
        occ_df.to_parquet(occ_file, engine='pyarrow', index=False)
        gains_df.to_parquet(gains_file, engine='pyarrow', index=False)
        carcharging_ondemand_df.to_parquet(carcharging_file, engine='pyarrow', index=False)
        carprofile_df.to_parquet(carprofile_file, engine='pyarrow', index=False)
        nb_flats_df.to_parquet(nb_flats_file, engine='pyarrow', index=False)
        nb_occ_df.to_parquet(nb_occ_file, engine='pyarrow', index=False)
        #nb_occ_list_df.to_parquet(nb_occ_list_file, engine='pyarrow', index=False)
        heatload_df.to_parquet(heatload_file, engine='pyarrow', index=False)
        bivalent_df.to_parquet(bivalent_file, engine='pyarrow', index=False)
        heatlimit_df.to_parquet(heatlimit_file, engine='pyarrow', index=False)
        ev_capacity_df.to_parquet(ev_capacity_file, engine='pyarrow', index=False)

        # Save insulation DataFrames if they exist
        if thick_req:
            wall_ins_file = os.path.join(directory_path, 'wall_ins.parquet')
            roof_ins_file = os.path.join(directory_path, 'roof_ins.parquet')
            floor_ins_file = os.path.join(directory_path, 'floor_ins.parquet')

            wall_ins_df.to_parquet(wall_ins_file, engine='pyarrow', index=False)
            roof_ins_df.to_parquet(roof_ins_file, engine='pyarrow', index=False)
            floor_ins_df.to_parquet(floor_ins_file, engine='pyarrow', index=False)

    def saveHeatingProfile(self, heat, cooling, name, gmlId, path):
        """
        Save heating demand to parquet files in the specified directory.

        Parameters
        ----------
        heat: list
            Hourly heating demand in W.
        cooling: list
            Hourly cooling demand in W.
        name : string
            Unique building name.
        gmlId : list
            List of gmlIds.
        path : string
            Results path.

        Returns
        -------
        None.
        """
        # Create the directory path
        directory_path = os.path.join(self.demands_path, name)
        os.makedirs(directory_path, exist_ok=True)

        # Create DataFrames
        cooling_df = pd.DataFrame(cooling, columns=['cooling'])
        heating_df = pd.DataFrame(heat, columns=['heating'])
        id_df = pd.DataFrame(gmlId, columns=['gmlId'])

        # Define file paths for each DataFrame
        cooling_file = os.path.join(directory_path, 'cooling.parquet')
        heating_file = os.path.join(directory_path, 'heating.parquet')
        id_file = os.path.join(directory_path, 'id.parquet')

        # Save cooling DataFrame, overwriting any existing file
        cooling_df.to_parquet(cooling_file, engine='pyarrow', index=False)

        # Save heating DataFrame, overwriting any existing file
        heating_df.to_parquet(heating_file, engine='pyarrow', index=False)

        # Save id DataFrame, overwriting any existing file
        id_df.to_parquet(id_file, engine='pyarrow', index=False)


    def loadProfiles(self, name, path):
        """
        Load profiles from parquet files.

        Parameters
        ----------
        name : string
            Unique building name.
        path : string
            Results path.

        Returns
        -------
        tuple
            Loaded profile data in the correct order.
        """
        # Create the directory path
        directory_path = os.path.join(self.demands_path, name)
        os.makedirs(directory_path, exist_ok=True)
        # Hourly profiles
        elec = pd.read_parquet(os.path.join(directory_path, 'elec.parquet'), engine='pyarrow')['elec'].to_numpy()
        dhw = pd.read_parquet(os.path.join(directory_path, 'dhw.parquet'), engine='pyarrow')['dhw'].to_numpy()
        occ = pd.read_parquet(os.path.join(directory_path, 'occ.parquet'), engine='pyarrow')['occ'].to_numpy()
        gains = pd.read_parquet(os.path.join(directory_path, 'gains.parquet'), engine='pyarrow')['gains'].to_numpy()
        carcharging_ondemand = pd.read_parquet(os.path.join(directory_path, 'carcharging.parquet'), engine='pyarrow')['car'].to_numpy()
        carprofile = pd.read_parquet(os.path.join(directory_path, 'carprofile.parquet'), engine='pyarrow')['Electric Vehicle Energy Demand (Wh)'].to_numpy()

        # Building info
        nb_flats = int(pd.read_parquet(os.path.join(directory_path, 'nb_flats.parquet'), engine='pyarrow')['Number of Flats or Main Rooms'][0])
        nb_occ = [int(pd.read_parquet(os.path.join(directory_path, 'nb_occ.parquet'), engine='pyarrow')['occ'][0])]
        #nb_occ_list = pd.read_parquet(os.path.join(directory_path, 'nb_occ_list.parquet'), engine='pyarrow')['occ list'].to_numpy()
        ev_capacity = pd.read_parquet(os.path.join(directory_path, 'ev_capacity.parquet'), engine='pyarrow')['EV Capacity (Wh)'].to_numpy()

        # Envelope data
        heatload = float(pd.read_parquet(os.path.join(directory_path, 'heatload.parquet'), engine='pyarrow')['heatload'][0])
        bivalent = float(pd.read_parquet(os.path.join(directory_path, 'bivalent.parquet'), engine='pyarrow')['bivalent'][0])
        heatlimit = float(pd.read_parquet(os.path.join(directory_path, 'heatlimit.parquet'), engine='pyarrow')['Heat Limit Heat Load (W)'][0])

        return elec, dhw, occ, gains, carcharging_ondemand, carprofile, nb_flats, nb_flats, nb_occ, ev_capacity, heatload, bivalent, heatlimit


    def loadHeatingProfiles(self, name, path):
        """
        Load heating profiles from parquet files.

        Parameters
        ----------
        name : string
            Unique building name.
        path : string
            Results path.

        Returns
        -------
        tuple
            Loaded heating and cooling data.
        """

        # Create the directory path
        directory_path = os.path.join(self.demands_path, name)
        os.makedirs(directory_path, exist_ok=True)

        # Load heating and cooling data from their respective Parquet files
        heat = pd.read_parquet(os.path.join(directory_path, 'heating.parquet'), engine='pyarrow')['heating'].to_numpy()
        cooling = pd.read_parquet(os.path.join(directory_path, 'cooling.parquet'), engine='pyarrow')['cooling'].to_numpy()
        id = pd.read_parquet(os.path.join(directory_path, 'id.parquet'), engine='pyarrow')['gmlId'].to_numpy()

        return heat, cooling, id

    def designDecentralDevices(self, saveGenerationProfiles=True, pv_standard=True):
        """
        Calculate capacities, generation profiles of renewable energies and EV load profiles for decentral devices.

        Parameters
        ----------
        saveGenerationProfiles : bool, optional
            True: save decentral PV and STC profiles as CSV-file.
            False: don't save decentral PV and STC profiles as CSV-file.
            The default is True.
        pv_standard: bool, optional
            True: use standard PV calculation with one roof surface.
            False: use detailed PV calculation with multiple roof surfaces / Fiware input data necessary.
            The default is True.

        Returns
        -------
        None.
        """

        for building in self.district:

            # Create BES object for building
            bes_obj = BES(physics=self.physics,
                        decentral_device_data=self.decentral_device_data,
                        design_building_data=self.design_building_data,
                        file_path=self.filePath)

            building["capacities"] = bes_obj.designECS(building, self.site)

            # save the building capacities from here, need to force HP as device, output in
            try:
                if not pv_standard:

                    # Parse string inputs to lists
                    roof_areas = [float(area) for area in building["buildingFeatures"]["surfaceAreaSuitableForSolarPV"].split("|")]
                    roof_inclinations = [float(beta) for beta in str(building["buildingFeatures"]["roofInclination"]).split("|")]
                    cardinal_directions = [float(gamma) for gamma in str(building["buildingFeatures"]["cardinalDirection"]).split("|")]
                    roof_shapes = str(building["buildingFeatures"]["roofShape"]).split("|")

                    # Adjust inclinations: flat roofs (0°) get default value (35°)
                    roof_inclinations = [beta if beta != 0 else 35 for beta in roof_inclinations]

                    # Call calcPVAndSTCProfile once with all roof segments
                    building["generationPV"], building["generationSTC"] = sun.calcPVAndSTCProfile(
                        time=self.time,
                        site=self.site,
                        areas=roof_areas,
                        betas=roof_inclinations,
                        gammas=cardinal_directions,
                        usageFactorPV=1, #set to 1 because roof area is netto
                        usageFactorSTC=1,
                        devices=self.decentral_device_data,
                    )

                    # ---- LOGGING ----
                    # pv_rows = []
                    # for i in range(len(roof_areas)):
                    #     pv_row = {
                    #         "ID": f"{building['buildingFeatures']['gmlId']}_roof_{i + 1}",
                    #         "calculated_area_roof": building["envelope"].A["opaque"]["roof"]/building["buildingFeatures"]["number_of_floors"]*building["buildingFeatures"]["f_PV"],
                    #         "actual_area_roof": roof_areas[i],
                    #         "calculated_beta": 35,
                    #         "actual_beta": roof_inclinations[i],
                    #         "calculated_gamma": building["buildingFeatures"]["gamma_PV"],
                    #         "actual_gamma": cardinal_directions[i],
                    #         "roofShape": roof_shapes[i]
                    #     }
                    #     pv_rows.append(pv_row)

                    # # Save logs to CSV
                    # pv_log_path = os.path.join(self.filePath, "logs", "pv_values_log.csv")
                    # try:
                    #     df_existing_pv = pd.read_csv(pv_log_path)
                    #     df_new_pv = pd.concat([df_existing_pv, pd.DataFrame(pv_rows)], ignore_index=True)
                    # except FileNotFoundError:
                    #     df_new_pv = pd.DataFrame(pv_rows)

                    # do not save log to reduce write operations
                    #df_new_pv.to_csv(pv_log_path, index=False, float_format='%.10f')

                    # ---- SAVE GENERATION PROFILES (Optional) ----
                    if saveGenerationProfiles:
                        # base_directory = os.path.join(self.resultPath, 'generation', self.scenario_name)
                        # os.makedirs(base_directory, exist_ok=True)
                        np.savetxt(
                            self.generation_path
                            + '/decentralPV_' + building["unique_name"] + '_' + self.scenario_name + '_'
                            + building["buildingFeatures"]["gmlId"].replace(":", "_") + '.csv',
                            building["generationPV"],
                            delimiter=';',
                            fmt='%.2f'
                        )

                        np.savetxt(
                            self.generation_path
                            + '/decentralSTC_' + building["unique_name"] + '_' + self.scenario_name + '_'
                            + building["buildingFeatures"]["gmlId"].replace(":", "_") + '.csv',
                            building["generationSTC"],
                            delimiter=';',
                            fmt='%.2f'
                        )
                else:
                    raise Exception("Using standard PV calculation")
            except:
                print("DEBUG: Using standard PV calculation for building " + building["unique_name"])
                # Standard single-surface calculation
                building["generationPV"], building["generationSTC"] = sun.calcPVAndSTCProfile(
                    time=self.time,
                    site=self.site,
                    areas=[building["envelope"].A["opaque"]["roof"]],
                    betas=[35],
                    gammas=[building["buildingFeatures"]["gamma_PV"]],
                    usageFactorPV=building["buildingFeatures"]["f_PV"],
                    usageFactorSTC=building["buildingFeatures"]["f_STC"],
                    devices=self.decentral_device_data
                )

                if saveGenerationProfiles:
                    # base_directory = os.path.join(self.resultPath, 'generation', self.scenario_name)
                    # os.makedirs(base_directory, exist_ok=True)
                    np.savetxt(
                        self.generation_path
                        + '/decentralPV_' + building["unique_name"] + '_' + self.scenario_name + '_'
                        + building["buildingFeatures"]["gmlId"].replace(":", "_") + '.csv',
                        building["generationPV"], delimiter=';',
                           fmt='%.2f')

                    np.savetxt(
                        self.generation_path
                        + '/decentralSTC_' + building["unique_name"] + '_' + self.scenario_name + '_'
                        + building["buildingFeatures"]["gmlId"].replace(":", "_") + '.csv',
                        building["generationSTC"], delimiter=';',
                           fmt='%.2f')


    def designCentralDevices(self, saveGenerationProfiles):
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

        # dimensioning of central devices
        self.centralDevices["capacities"] = self.centralDevices["ces_obj"].designCES(self)

        # calculate theoretical PV, STC and Wind generation
        self.centralDevices["generation"] = {}
        self.centralDevices["generation"]["PV"] = self.centralDevices["capacities"]["PV_generation_uncl"]
        self.centralDevices["generation"]["STC"] = self.centralDevices["capacities"]["STC_generation_uncl"]
        self.centralDevices["generation"]["Wind"] = self.centralDevices["capacities"]["WT_generation_uncl"]

        # optionally save generation profiles
        if saveGenerationProfiles == True:
            np.savetxt(os.path.join(self.generation_path, 'centralPV.csv'),
                       self.centralDevices["generation"]["PV"],
                       delimiter=';',
                       fmt='%.2f')
            np.savetxt(os.path.join(self.generation_path, 'centralSTC.csv'),
                       self.centralDevices["generation"]["STC"],
                       delimiter=';',
                       fmt='%.2f')
            np.savetxt(os.path.join(self.generation_path, 'centralWind.csv'),
                       self.centralDevices["generation"]["Wind"],
                       delimiter=';',
                       fmt='%.2f')

    def designDevicesComplete(self, saveGenerationProfiles=True):
        """
        Design decentral and central devices.

        Parameters
        ----------
        saveGenerationProfiles : bool, optional
            Decision if generation profiles of designed devices will be saved. The default is True.

        Returns
        -------
        None.
        """

        self.designDecentralDevices(saveGenerationProfiles)
        self.designCentralDevices(saveGenerationProfiles)

    def clusterProfiles(self, centralEnergySupply):
        """
        Perform time series aggregation for profiles by using the k-medoids clustering algorithm.

        Returns
        -------
        None.
        """

        # calculate cluster time horizon
        initialArrayLenght = (self.time["clusterLength"] / self.time["timeResolution"])
        lenghtArray = initialArrayLenght
        while lenghtArray <= len(self.site["T_e"]):
            lenghtArray += initialArrayLenght
        lenghtArray = int(lenghtArray - initialArrayLenght)

        # adjust profiles with calculated array length
        adjProfiles = {}
        # loop over buildings
        for i, b in enumerate(self.district):
            adjProfiles[i] = {}
            adjProfiles[i]["elec"] = b["user"].elec[0:lenghtArray]
            adjProfiles[i]["dhw"] = b["user"].dhw[0:lenghtArray]
            adjProfiles[i]["heat"] = b["user"].heat[0:lenghtArray]
            adjProfiles[i]["cooling"] = b["user"].cooling[0:lenghtArray]
            adjProfiles[i]["occ"] = b["user"].occ[0:lenghtArray]
            adjProfiles[i]["carcharging_ondemand"] = b["user"].carcharging_ondemand[0:lenghtArray]
            adjProfiles[i]["carprofile"] = b["user"].carprofile[0:lenghtArray]
            adjProfiles[i]["generationPV"] = b["generationPV"][0:lenghtArray]
            adjProfiles[i]["generationSTC"] = b["generationSTC"][0:lenghtArray]

        if centralEnergySupply == True:

            adjProfiles["losses_heating_network"] = self.heat_grid_data["total_losses_heating_network"][0:lenghtArray]
            adjProfiles["losses_cooling_network"] = self.heat_grid_data["total_losses_cooling_network"][0:lenghtArray]

            if self.centralDevices["capacities"]["WT"]["cap"] > 0:
                adjProfiles["generationCentralWT"] = self.centralDevices["generation"]["Wind"][0:lenghtArray]
            else:
                # no central WT exists; but array with just zeros leads to problem while clustering
                adjProfiles["generationCentralWT"] = np.ones(lenghtArray) * sys.float_info.epsilon

            if self.centralDevices["capacities"]["PV"]["cap"] > 0:
                adjProfiles["generationCentralPV"] = self.centralDevices["generation"]["PV"][0:lenghtArray]
            else:
                # no central PV exists; but array with just zeros leads to problem while clustering
                adjProfiles["generationCentralPV"] = np.ones(lenghtArray) * sys.float_info.epsilon

            if self.centralDevices["capacities"]["STC"]["cap"] > 0:
                adjProfiles["generationCentralSTC"] = self.centralDevices["generation"]["STC"][0:lenghtArray]
            else:
                # no central STC exists; but array with just zeros leads to problem while clustering
                adjProfiles["generationCentralSTC"] = np.ones(lenghtArray) * sys.float_info.epsilon

        # wind speed and ambient temperature
        adjProfiles["T_e"] = self.site["T_e"][0:lenghtArray]

        # Prepare clustering
        # weights for clustering algorithm indicating the focus onto this profile
        # Scaling flags for each profile (True = scale after clustering, False = preserve values)

        inputsClustering, weights, scalings = [], [], []

        # loop over buildings
        for i in range(len(self.district)):
            inputsClustering.append(adjProfiles[i]["elec"])
            weights.append(1)
            scalings.append(True)

            inputsClustering.append(adjProfiles[i]["dhw"])
            weights.append(1)
            scalings.append(True)

            inputsClustering.append(adjProfiles[i]["heat"])
            weights.append(1)
            scalings.append(True)

            inputsClustering.append(adjProfiles[i]["cooling"])
            weights.append(1)
            scalings.append(False)

            inputsClustering.append(adjProfiles[i]["occ"])
            weights.append(0)
            scalings.append(False)

            inputsClustering.append(adjProfiles[i]["carcharging_ondemand"])
            weights.append(0)      # This profile is not used at all for clustering
            scalings.append(False)  # This profile is not scaled

            inputsClustering.append(adjProfiles[i]["carprofile"])
            weights.append(0)      # This profile is not used at all for clustering
            scalings.append(False)  # This profile is not scaled

            inputsClustering.append(adjProfiles[i]["generationPV"])
            weights.append(1)
            scalings.append(True)

            inputsClustering.append(adjProfiles[i]["generationSTC"])
            weights.append(1)
            scalings.append(True)

        # Higher weight for outdoor temperature and central generation profiles,
        # since they each occur only once (unlike the building profiles)
        # and should therefore receive the same weight as the number of buildings.

        # ambient temperature
        inputsClustering.append(adjProfiles["T_e"])
        weights.append(len(self.district))
        scalings.append(True)

        if centralEnergySupply == True:

            # Heating and cooling networks losses
            inputsClustering.append(adjProfiles["losses_heating_network"])
            weights.append(0)
            scalings.append(False)

            inputsClustering.append(adjProfiles["losses_cooling_network"])
            weights.append(0)
            scalings.append(False)

            # central renewable generation
            inputsClustering.append(adjProfiles["generationCentralWT"])
            weights.append(len(self.district))
            scalings.append(True)

            inputsClustering.append(adjProfiles["generationCentralPV"])
            weights.append(len(self.district))
            scalings.append(True)

            inputsClustering.append(adjProfiles["generationCentralSTC"])
            weights.append(len(self.district))
            scalings.append(True)

        # Perform clustering
        (newProfiles, nc, y, z, transfProfiles) = cm.cluster(np.array(inputsClustering),
                                                             number_clusters=self.time["clusterNumber"],
                                                             len_cluster=int(initialArrayLenght),
                                                             weights=weights,
                                                             scalings=scalings)

        # safe clustered profiles of all buildings
        for i in range(len(self.district)):
            index_house = int(9)    # number of profiles per building
            self.district[i]["user"].elec_cluster = newProfiles[index_house * i]
            self.district[i]["user"].dhw_cluster = newProfiles[index_house * i + 1]
            self.district[i]["user"].heat_cluster = newProfiles[index_house * i + 2]
            self.district[i]["user"].cooling_cluster = newProfiles[index_house * i + 3]
            self.district[i]["user"].occ_cluster = newProfiles[index_house * i + 4]
            self.district[i]["user"].carcharging_ondemand_cluster = newProfiles[index_house * i + 5]
            self.district[i]["user"].carprofile_cluster = newProfiles[index_house * i + 6]
            self.district[i]["generationPV_cluster"] = newProfiles[index_house * i + 7]
            self.district[i]["generationSTC_cluster"] = newProfiles[index_house * i + 8]

        if centralEnergySupply == True:
            self.site["T_e_cluster"] = newProfiles[-6]
            self.heat_grid_data["total_losses_heating_network_cluster"] = newProfiles[-5]
            self.heat_grid_data["total_losses_cooling_network_cluster"] = newProfiles[-4]
            self.centralDevices["generation"]["Wind_cluster"] = newProfiles[-3]
            self.centralDevices["generation"]["PV_cluster"] = newProfiles[-2]
            self.centralDevices["generation"]["STC_cluster"] = newProfiles[-1]
        else:
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


    def saveDistrict(self):
        """
        Save district dict as pickle file.

        Returns
        -------
        None.
        """

        with open(self.resultPath + "/" + self.scenario_name + ".p", 'wb') as fp:
            pickle.dump(self.district, fp, protocol=pickle.HIGHEST_PROTOCOL)

    def loadDistrict(self, scenario_name='example'):
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

        with open(self.resultPath + "/" + self.scenario_name + ".p", 'rb') as fp:
            self.district = pickle.load(fp)

    def plot(self, mode='default', initialTime=0, timeHorizon=31536000, savePlots=True, timeStamp=False, show=False):
        """
        Create plots of the energy consumption and generation.

        Parameters
        ----------
        mode : string, optional
            Choose a single plot or show all of them as default. The default is 'default'.
            Possible modes are:
            ['elec', 'dhw', 'gains', 'occ', 'car', 'heating', 'pv', 'stc', 'electricityDemand', 'heatDemand'].
        initialTime : integer, optional
            Start of the plot in seconds from the beginning of the year. The default is 0.
        timeHorizon : integer, optional
            Length of the time horizon that is plotted in seconds. The default is 31536000 (what equals one year).
        savePlots : boolean, optional
            Decision if plots are saved under results/plots/. The default is True.
        timeStamp : boolean, optional
            Decision if saved plots get a unique name by adding a time stamp. The default is False.
        show : boolean, optional
            Decision if saved plots are presented directly to the user. The default is False.

        Returns
        -------
        None.
        """

        # initialize plots and prepare data for plotting
        demandPlots = DemandPlots(resultPath=self.resultPath)
        demandPlots.preparePlots(self)

        # check which resolution for plots is used
        if initialTime == 0 and timeHorizon == 31536000:
            plotResolution = 'monthly'
        else:
            plotResolution = 'stepwise'

        # the selection of possible plots
        plotTypes = \
            ['elec', 'dhw', 'gains', 'occ', 'car', 'heating', 'pv', 'stc', 'electricityDemand', 'heatDemand', 'wt']

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

    def optimizationClusters(self):
        """
        Optimize the operation costs for each cluster.

        Returns
        -------
        None.
        """
        optiData = {}

        # initialize result list for all clusters
        self.resultsOptimization = []

        for cluster in range(self.time["clusterNumber"]):
            # optimize operating costs of the district for current cluster
            self.optimizer = Optimizer(self, cluster, self.gurobiConfig)
            results_temp = self.optimizer.run_cen_opti()

            # save results as attribute
            self.resultsOptimization.append(results_temp)

        # ensure result path to results/optimization exists
        # json_path = f'{self.resultPath}/optimization/{self.scenario_name}'
        # os.makedirs(json_path, exist_ok=True)

        with open(f'{self.optimization_path}/result_opti_central_total.json', 'w') as f:
            json.dump(self.resultsOptimization, f, indent=4)


    def calulateKPIs(self):
        """
        Calculate key performance indicators (KPIs).

        Returns
        -------
        None.
        """

        # initialize KPI class
        self.KPIs = KPIs(self, decentral_config=self.decentral_device_data)
        # calculate KPIs
        self.KPIs.calculateAllKPIs(self)


def generate_demands_worker_wrapper(args):
    """
    Wrapper-Funktion außerhalb der Klasse, da multiprocessing pickling benötigt.
    Args enthält (building, calcUserProfiles, saveUserProfiles, andere Parameter)
    """
    self_ref, building, calcUserProfiles, saveUserProfiles = args
    self_ref.generate_demands_worker(building, calcUserProfiles, saveUserProfiles)

    result = {
        "unique_name": building["unique_name"],
        "elec": building["user"].elec,
        'dhw': building["user"].dhw,
        'cooling': building["user"].cooling,
        'heating': building["user"].heat,
        'occ': building["user"].occ,
        'carcharging_ondemand': building["user"].carcharging_ondemand,
        'carprofile': building["user"].carprofile,
        "ev_capacity": building["user"].ev_capacity,
        'gains': building["user"].gains,
        'id': building['buildingFeatures']["gmlId"],
        "nb_units": building["user"].nb_units,
        'nb_occ': building["user"].nb_occ,
        'envelope': building["envelope"],
        'night_setback': building["buildingFeatures"]["night_setback"],
    }

    return result
