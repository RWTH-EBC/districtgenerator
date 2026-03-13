# -*- coding: utf-8 -*-

import json
import pickle
import os
import sys
import copy
import datetime
import multiprocessing
import random
import time
import math
import warnings
import threading
import numpy as np
import openpyxl
import pandas as pd
import random as rd
import holidays as hol
from teaser.project import Project
from .envelope_5R1C import Envelope as Envelope_5R1C
from .envelope_7R2C import Envelope as Envelope_7R2C
from .solar import Sun
from .users import Users
from .system import BES
from .system import CES
from .plots import DemandPlots
from .optimizer import Optimizer
from .KPIs import KPIs
from .non_residential import NonResidential
import districtgenerator.functions.SIA as SIA
import districtgenerator.functions.clustering_medoid as cm
from districtgenerator.functions import opti_central
import districtgenerator.functions.heating_network_simple as heating_network_simple
from districtgenerator.functions.heating_network_opt import network_optimization
from districtgenerator.functions.heating_network_new import network_optimization2
from districtgenerator.functions.heating_network_new2 import network_optimization3

from districtgenerator.functions.design_network_with_node import run_pipeline_node
from districtgenerator.functions.design_network_with_road import run_pipeline_road
from districtgenerator.functions.heating_network_simple import calculate_soil_temperature
from districtgenerator.data_handling.config import GlobalConfig, load_global_config, LocationConfig, TimeConfig, DesignBuildingConfig, EcoConfig, PhysicsConfig, EHDOConfig, PyomoConfig, HeatGridConfig, CalendarConfig, CentralDeviceConfig, DecentralDeviceConfig, WasteHeatConfig
from .plots_balances import plot_all
import matplotlib.pyplot as plt



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
                 env_path = None):
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

        global_config: GlobalConfig = load_global_config(env_file=env_path)

        if filePath is None:
            filePath = os.path.join(srcPath, 'data')

        self.initial_day = None
        self.district = []
        self.scenario_name = scenario_name
        self.scenario = None
        self.total_building_area = None

        # Config Data
        self.site = {}
        self.time = {}
        self.design_building_data = {}
        self.physics = {}
        self.decentral_device_data = {}
        self.params_ehdo_technical = {}
        self.params_ehdo_model = {}
        self.central_device_data = {}
        self.calendar = {} #! This is new; check if everywhere correctly integrated
        self.ecoData = {}
        self.all_sim_ecoData = {} # Later overwritten with the calculated economic data for the simulated years
        self.heat_grid_data = {}
        self.pipe_data = None
        self.pyomo_config = {}
        self.counter = {}
        self.building_dict = {} # Dictionary to store Residential Building IDs
        self.srcPath = srcPath
        self.filePath = filePath
        self.waste_heat_data = {}

        if scenario_file_path is not None:
            self.scenario_file_path = scenario_file_path
        else:
            self.scenario_file_path = os.path.join(self.filePath, 'scenarios')

        if resultPath is not None:
            self.resultPath = resultPath
        else:
            self.resultPath = os.path.join(self.srcPath, 'results')

        self.KPIs = None
        self.load_all_data( #! This function needs to be adapted to the new config structure
            site_config=global_config.location,
            time_config=global_config.time,
            design_building_config=global_config.design_building,
            physics_config=global_config.physics,
            decentral_config=global_config.decentral,
            ehdo_config=global_config.ehdo,
            eco_config=global_config.eco,
            central_config=global_config.central,
            calendar_config=global_config.calendar,
            heat_grid_config=global_config.heatgrid,
            pyomo_config=global_config.pyomo
        )

        self.buildings_completed = 0
        self.buildings_total = 0
        self.progress_file = os.path.join(self.resultPath, 'progress.json')

        self.pipeline = {}

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
                      heat_grid_config: HeatGridConfig,
                      pyomo_config: PyomoConfig):
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
        self.scenario = (pd.read_csv(os.path.join(self.scenario_file_path, f"{self.scenario_name}.csv"), delimiter=";",
                                     converters={"position": parse_position}).set_index("id", drop=False))

        json_path = os.path.join(self.scenario_file_path, f"{self.scenario_name}.json")

        if os.path.exists(json_path):
            with open(json_path, encoding="utf-8") as json_file:
                jsonData = json.load(json_file)
                self.site["district_parameters"] = jsonData["parameters"]
                #bounds = jsonData["parameters"]["district_bounds"]
                #self.site["area"] = (bounds["xmax"] - bounds["xmin"]) * (bounds["ymax"] - bounds["ymin"])
                #print(f"Hier ist die area: {self.site['area']} und hier sind xmax: {bounds['xmax']}, xmin:{bounds['xmin']}, ymax:{bounds['ymax']} und ymin:{bounds['ymin']}")

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
        for attr, value in decentral_config.__dict__.items():
            self.decentral_device_data[attr] = value

        for attr, value in ehdo_config.__dict__.items():
            self.params_ehdo_model[attr] = value

        # load economic and ecologic data (of the district generator) (used in system CES)
        for attr, value in eco_config.__dict__.items():
            self.ecoData[attr] = value

        # Load list of possible devices (used in system BES)
        # Iterate over all attributes of the config instance
        for attr, value in central_config.__dict__.items():
            self.central_device_data[attr] = value

        # load calendar data (used in generateDemands and generateEnvironment)
        for attr, value in calendar_config.__dict__.items():
            self.calendar[attr] = value

        # load pyomo solver data (used in optimization functions)
        for attr, value in pyomo_config.__dict__.items():
            self.pyomo_config[attr] = value


        #! Das hier überarbeiten, damit es in die neue Struktur passt?
        for attr, value in heat_grid_config.__dict__.items():
            self.heat_grid_data[attr] = value

        # with open(os.path.join(self.filePath, 'heat_grid.json')) as json_file:
        #     self.heat_grid_data = json.load(json_file)

        self.pipe_file_path = os.path.join(self.filePath, 'pipe')
        # select the pipe file based on the generation selection
        # KMR for 3rd generation; PMR for 4th generation; PE for 5th generation
        if self.heat_grid_data["generation"] == "3rd":
            csv_path = os.path.join(self.pipe_file_path, 'pipe_specifications_KMR.csv')
            self.pipe_data = pd.read_csv(csv_path, sep=";")
        elif self.heat_grid_data["generation"] == "4th":
            csv_path = os.path.join(self.pipe_file_path, 'pipe_specifications_PMR.csv')
            self.pipe_data = pd.read_csv(csv_path, sep=";")
        elif self.heat_grid_data["generation"] == "5th":
            csv_path = os.path.join(self.pipe_file_path, 'pipe_specifications_PE.csv')
            self.pipe_data = pd.read_csv(csv_path, sep=";")
            pass
        else:
            print("Please select from the 3rd, 4th, or 5th generation and enter it into the config file.")

        # Determine the all_sim_ecoData which contains prices, co2 factors for each simulated year used for optimizations:
        self.all_sim_ecoData = self.calculate_ecoData_per_cluster()

        self.SIA2024 = SIA.read_SIA_data()

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
            """  
                Add new weatherdatafile_location, if you want an individual location: 
                Files can be found here: https://www.dwd.de/DE/leistungen/testreferenzjahre/testreferenzjahre.html 
                Every file has to be stored in the folder reffering to the correct Year and season in the subfolders of '\districtgenerator\data\weather\ 
                Example: TRY2015_507755060854_Wint.dat has to be stored in '\districtgenerator\data\weather\TRY_2015_Winter' 
                Uncomment the following line  
            """
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
        [temp_sunDirect, temp_sunDiff, temp_tempe, temp_wind, temp_rhum, temp_pre, temp_ssw] = \
            [weatherData[:, 12], weatherData[:, 13], weatherData[:, 5], weatherData[:, 8], weatherData[:, 11], weatherData[:, 6], weatherData[:, 9]]

        self.time["timeSteps"] = int(self.time["dataLength"] / self.time["timeResolution"])

        # load the holidays
        if self.site["TRYYear"] == "TRY2015":
            self.calendar["holidays"] = self.get_holidays(country_code="DE", year=2015)
        elif self.site["TRYYear"] == "TRY2045":
            self.calendar["holidays"] = self.get_holidays(country_code="DE", year=2045)


        # interpolate input data to achieve required data resolution
        # transformation from values for points in time to values for time intervals
        self.site["SunDirect"] = np.interp(np.arange(0, self.time["dataLength"] + 1, self.time["timeResolution"]),      # Direct horizontal radiation
                                           np.arange(0, self.time["dataLength"] + 1, self.time["dataResolution"]),
                                           temp_sunDirect)[0:-1]
        self.site["SunDiffuse"] = np.interp(np.arange(0, self.time["dataLength"] + 1, self.time["timeResolution"]),     # Diffuse horizontal radiation
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
        self.site["ssw"] = np.interp(np.arange(0, self.time["dataLength"] + 1, self.time["timeResolution"]),
                                        np.arange(0, self.time["dataLength"] + 1, self.time["dataResolution"]),
                                        1 - np.clip(temp_ssw, 0, 8) / 8.0)[0:-1]

        self.site["SunTotal"] = self.site["SunDirect"] + self.site["SunDiffuse"] # This is the GHI (Global Horizontal Irradiance)

        # Load other site-dependent values based on DIN/TS 12831-1:2020-04
        srcPath = os.path.dirname(os.path.abspath(__file__))
        filePath = os.path.join(os.path.dirname(srcPath), 'data', 'site_data.txt')
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

        # calculate the soil temperature profile
        dt = self.time["timeResolution"] / self.time["dataResolution"]
        calculate_soil_temperature(self, dt)

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

        # initialize buildings for scenario
        # loop over all buildings
        for bldg_id, row in self.scenario.iterrows():
            bldg_id = int(bldg_id)
            building = {}

            # Store features of the observed building
            building["buildingFeatures"] = row

            # Unique name = "<id>_<building type>"
            name = f"{bldg_id}_{row['building']}"
            if name in name_pool:
                print(f"Duplicate name: {name}, skipping")
                continue
            name_pool.append(name)

            building["unique_name"] = name
            self.district.append(building)
            self.building_dict[bldg_id] = len(self.district) - 1

            # Count for time estimate
            if row["building"] in ("SFH", "TH"):
                num_sfh += 1
            elif row["building"] in ("MFH", "AB"):
                num_mfh += 1


        # Rough time estimate
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
        prj = Project(load_data=True)
        prj.name = self.scenario_name

        for building in self.district:

            # convert short names into designation needed for TEASER
            building_type = bldgs["buildings_long"][bldgs["buildings_short"].index(building["buildingFeatures"]["building"])]

            # add buildings to TEASER project
            if building_type in {"single_family_house", "multi_family_house", "terraced_house", "apartment_block"}:
                retrofit_level = bldgs["retrofit_long"][bldgs["retrofit_short"].index(building["buildingFeatures"]["retrofit"])]

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
                    one_floor_area = rd.randint(102, 971) # Source: TABULA German Building Typology
                    # Calculate the number of floors, rounding to the nearest integer and ensuring at least 2
                    number_of_floors = max(2, round(building["buildingFeatures"]["area"] / one_floor_area))
                    # Cap the number of floors to a maximum of 8
                    if number_of_floors > 8:
                        number_of_floors = 8

                elif building_type == "apartment_block":
                    one_floor_area = rd.randint(350, 540)  # Source: TABULA German Building Typology
                    # Calculate the number of floors, rounding to the nearest integer and ensuring at least 3
                    number_of_floors = max(3, round(building["buildingFeatures"]["area"] / one_floor_area))

                # Determining the typical floor height based on the building's construction year.
                # Older buildings (constructed before 1960) generally have higher ceilings, while newer buildings
                # (built from 1960 onwards) tend to have lower ceilings.
                # Source: https://www.wohnung.com/ratgeber/418/alt-und-neubau-deckenhoehe

                if building["buildingFeatures"]["year"] < 1960:
                    height_of_floors = 3.3  # m
                elif building["buildingFeatures"]["year"] >= 1960:
                    height_of_floors = 2.5  # m

                prj.add_residential(method='tabula_de',
                                    usage=building_type,
                                    name="ResidentialBuildingTabula",
                                    year_of_construction=building["buildingFeatures"]["year"],
                                    number_of_floors=number_of_floors,
                                    height_of_floors=height_of_floors,
                                    net_leased_area=building["buildingFeatures"]["area"],
                                    construction_type=retrofit_level)


                building["buildingFeatures"] = building["buildingFeatures"].copy()
                building["buildingFeatures"]["id_teaser"] = len(prj.buildings) - 1

                # %% create envelope object
                # containing all physical data of the envelope

                if self.design_building_data["thermal_model_type"] == "5R1C":
                    Envelope = Envelope_5R1C
                    building["thermal_model"] = "5R1C"
                elif self.design_building_data["thermal_model_type"] == "7R2C":
                    Envelope = Envelope_7R2C
                    building["thermal_model"] = "7R2C"
                else:
                    raise ValueError(f"Unknown thermal_model_type: {self.design_building_data['thermal_model_type']}")

                building["envelope"] = Envelope(prj=prj,
                                                building_params=building["buildingFeatures"],
                                                construction_type=retrofit_level,
                                                physics=self.physics,
                                                design_building_data=self.design_building_data,
                                                file_path=self.filePath)

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
                # NOTE: For non-residential buildings, the available input data
                # only supports the 5R1C thermal model. A 7R2C mode is not
                # feasible here due to missing parameters for VDI 6007 modeling.

                Envelope = Envelope_5R1C
                building["thermal_model"] = "5R1C"

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
                                     retrofit=building["buildingFeatures"]["retrofit"])

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
            building["buildingFeatures"]["mean_drawoff_dhw"] = bldgs["mean_drawoff_vol_per_day"][index]

    def generateDemands(self, calcUserProfiles=True, saveUserProfiles=True, max_threads=8, gen_cars=True):
        # Thread count is limited by the maximum available CPU cores. Using more threads than cores usually provides no additional benefit but requires more temporary storage.
        max_threads = min(max_threads, multiprocessing.cpu_count())

        args_list = [(self, building, calcUserProfiles, saveUserProfiles, gen_cars) for building in self.district]

        self.buildings_total = len(self.district)
        self.buildings_completed = 0

        results = [] # Store results from worker processes

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
            building["user"].occ = result["occ"]
            building["user"].EV_carcharging_ondemand =  result["EV_carcharging_ondemand"]
            building["user"].EV_carprofile = result["EV_carprofile"]
            building["user"].ev_capacity = result.get("ev_capacity")
            building["user"].ice_carprofile = result["ice_carprofile"]
            building["user"].gains = result["gains"]
            building["user"].nb_units = result["nb_units"]
            building["user"].nb_occ = result["nb_occ"]
            building["user"].individual_car_profiles = result.get("individual_car_profiles", [])
            building["envelope"] = result["envelope"]
            building_features = building["buildingFeatures"].copy()
            building_features["night_setback"] = result["night_setback"]
            building["buildingFeatures"] = building_features

        self.save_progress()


        print("Finished generating demands with multiprocessing!")

    def generate_demands_worker(self, building, calcUserProfiles, saveUserProfiles, gen_cars = True):
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
        warnings.filterwarnings("ignore", category=FutureWarning)

        # calculate or load user profiles
        if calcUserProfiles:
            building["user"].calcProfiles(site=self.site,
                                          holidays=self.calendar["holidays"],
                                          time_resolution=self.time["timeResolution"],
                                          time_horizon=self.time["dataLength"],
                                          building_devices_data=self.decentral_device_data,
                                          building=building,
                                          path=os.path.join(self.resultPath, 'demands'),
                                          initial_day=self.initial_day,
                                          gen_cars=gen_cars)

            if saveUserProfiles:
                self.saveProfiles(name=building["unique_name"],
                                  elec=building["user"].elec,
                                  dhw=building["user"].dhw,
                                  occ=building["user"].occ,
                                  gains=building["user"].gains,
                                  EV_carcharging_ondemand=building["user"].EV_carcharging_ondemand,
                                  EV_carprofile=building["user"].EV_carprofile,
                                  nb_units=building["user"].nb_units,
                                  nb_occ=building["user"].nb_occ,
                                  ev_capacity=building["user"].ev_capacity or [0],
                                  ice_carprofile=building["user"].ice_carprofile,
                                  heatload=building["envelope"].heatload,
                                  bivalent=building["envelope"].bivalent,
                                  heatlimit=building["envelope"].heatlimit,
                                  path=os.path.join(self.resultPath, 'demands'),
                                  individual_car_profiles=building["user"].individual_car_profiles)

        else:
            (building["user"].elec, building["user"].dhw,
             building["user"].occ, building["user"].gains,
             building["user"].EV_carcharging_ondemand,
             building["user"].EV_carprofile,
             building["user"].ice_carprofile,
             building["user"].nb_flats,
             building["user"].nb_main_rooms,
             building["user"].nb_occ, building["user"].ev_capacity, building["envelope"].heatload,
             building["envelope"].bivalent,
             building["envelope"].heatlimit,
             building["user"].individual_car_profiles) = self.loadProfiles(building["unique_name"],
                                                                 os.path.join(self.resultPath, 'demands'), gen_cars= gen_cars)
            print("Load demands of building " + building["unique_name"])

        if building.get("thermal_model") == "5R1C":
            building["envelope"].calcNormativeProperties(self.site["SunRad"], building["user"].gains)
        elif building.get("thermal_model") == "7R2C":
            # Compute VDI6007 params
            building["envelope"]._VDI6007_params(self.site["SunRad"])
            # Compute equivalent temperature
            building["envelope"].calc_theta_eq(self.site, building["user"].gains)
        else:
            raise ValueError(f"Unknown thermal_model_type: {self.design_building_data['thermal_model_type']}")

        night_setback = building["buildingFeatures"]["night_setback"]

        is_cooled = building["buildingFeatures"]["cooling"] # Indicates whether the building is actively cooled

        # calculate or load heating profiles
        if calcUserProfiles:
            building["user"].calcHeatingProfile(site=self.site,
                                                envelope=building["envelope"],
                                                thermal_model=building["thermal_model"],
                                                night_setback=night_setback,
                                                is_cooled=is_cooled,
                                                holidays=self.calendar["holidays"],
                                                time_resolution=self.time["timeResolution"],
                                                initial_day=self.initial_day)

            if saveUserProfiles:
                self.saveHeatingProfile(heat=building["user"].heat,
                                        cooling=building["user"].cooling,
                                        name=building["unique_name"],
                                        path=os.path.join(self.resultPath, 'demands'))
                # building["user"].saveHeatingProfile(building["unique_name"], os.path.join(self.resultPath, 'demands'))
        else:
            heat, cooling = self.loadHeatingProfiles(name=building["unique_name"],
                                                     path=os.path.join(self.resultPath, 'demands'))
            building["user"].heat = heat
            building["user"].cooling = cooling


    def generate_waste_heat_source(self, waste_heat_source, distance):

        # Computes position relative to district boundaries (non-deterministic) while respecting minimum distance constraint
        def calc_position(distance):
            json_path = os.path.join(self.scenario_file_path, f"{self.scenario_name}.json")
            if os.path.exists(json_path):
                with open(json_path, encoding="utf-8") as json_file:
                    jsonData = json.load(json_file)
                    bounds = jsonData["parameters"]["district_bounds"]

            side = random.choice(['left', 'right', 'bottom', 'top'])

            if side == 'left':
                x = bounds['xmin'] - distance
                y = random.uniform(bounds['ymin'], bounds['ymax'])
            elif side == 'right':
                x = bounds['xmax'] + distance
                y = random.uniform(bounds['ymin'], bounds['ymax'])
            elif side == 'bottom':
                y = bounds['ymin'] - distance
                x = random.uniform(bounds['xmin'], bounds['xmax'])
            else:
                y = bounds['ymax'] + distance
                x = random.uniform(bounds['xmin'], bounds['xmax'])

            return [x, y]

        def generate_waste_heat_profiles():
            import numpy as np

            timesteps = int(self.time["dataLength"] / self.time["timeResolution"])

            # waste heat profile of a data center (DC)
            if waste_heat_source == "Rechenzentrum":
                connected_load = 500                             # connected load of a DC in kW (Enterprise: 5000 kW, Colocation: 20000 kW, Hyperscale: 150000 kW)
                self.waste_heat_data["size"] = connected_load     #https://www.powercontrol.co.uk/news-blog/blog/what-are-the-different-types-of-data-centre-power-design-and-the-future-of-infrastructure/#:~:text=Enterprise%20data%20centres%20are%20privately,link%20national%20and%20international%20networks

                laod_factor = 0.5                                 # ratio of the actual IT power usage to the maximum connected load
                it_load = connected_load * laod_factor
                T_hot = 35                                       # exit temperature of the server room
                T_cold = 20                                       # entry temperature of the server room
                waste_heat_profile = np.full(timesteps, it_load)
                temperature_profile = np.full(timesteps, T_hot)

            # waste heat profile of a wastewater treatment plant (WWTP)
            if waste_heat_source == "Kläranlage":
                c_p_ww = 4.18  # in kJ/kgK
                rho_ww = 1000  # in kg/m^3
                PE = 10000  # Population equivalent (Einwohnerwert): indicates the average load of wastewater from one inhabitant with biodegradable substances
                self.waste_heat_data["size"] = PE
                Vdot_person_daily = 126  # daily water consumption per person in L/d
                Vdot_person_hourly = Vdot_person_daily / 24 * 0.001  # hourly water consumption per person in m^3/h
                Vdot_ww = np.full(timesteps, PE * Vdot_person_hourly)

                T_min = 10.0  # °C
                T_max = 20.0  # °C
                mean_temp = (T_min + T_max) / 2
                amplitude = (T_max - T_min) / 2
                T_ref = 8  # °C

                temperature_profile = []
                for day in range(8760):
                    temperature_profile.append(mean_temp - (amplitude * np.cos(2 * math.pi * (day / 8760))))

                delta_T = np.array(temperature_profile).flatten() - T_ref

                waste_heat_profile = (Vdot_ww * c_p_ww * rho_ww * delta_T) / 3600

            # waste heat profile for industry
            if waste_heat_source in ["Papierindustrie", "Baustoff"]:
                production_annual = 100000
                schicht = 3
                self.waste_heat_data["size"] = production_annual

                waste_heat_profile, temperature_profile = generate_industrial_profile(self, waste_heat_source, production_annual, timesteps, schicht)

                print(f"Hier ist das Abwärmeprofil: {waste_heat_profile}")



            return waste_heat_profile, temperature_profile



        def calc_temperature_lift(waste_heat_profile, temperature_profile, T_supply):
            waste_heat_profile_hp = []
            COP = []
            is_HP_used = []
            deltaT_pinch = 5 # Minimum temperature approach at heat exchanger pinch point (in K)
            eta = 0.5 #

            for i in range(8760):
                if temperature_profile[i] < T_supply + deltaT_pinch:
                    COP_carnot = (T_supply + 273.15) / ((T_supply + 273.15) - (temperature_profile[i] + 273.15))
                    COP_real = COP_carnot * eta
                    Q_lift = waste_heat_profile[i] * COP_real
                    waste_heat_profile_hp.append(Q_lift)
                    COP.append(COP_real)
                    is_HP_used.append(True)
                else:
                    waste_heat_profile_hp.append(waste_heat_profile[i])
                    is_HP_used.append(False)
                    COP.append(0)

            waste_heat_profile_hp = np.array(waste_heat_profile_hp)

            return waste_heat_profile_hp, COP, is_HP_used

        def calc_hex_costs():
            return 1



        # The waste heat source data can be generated automatically using typdistrict_postprocess
        # or entered manually (for testing purposes). When generated via typdistrict_postprocess,
        # a comprehensive JSON file containing all relevant data is produced.
        json_path = os.path.join(self.scenario_file_path, "wh_source.json")
        if os.path.exists(json_path):
            with open(json_path, encoding="utf-8") as json_file:
                jsonData = json.load(json_file)
                position = jsonData[0]["position"]
                self.waste_heat_data["type"] = jsonData[0]["type"]
        else:
            position = calc_position(distance)
            self.waste_heat_data["type"] = waste_heat_source


        self.waste_heat_data["position"] = position
        self.waste_heat_data["distance"] = distance

        # calculation of an hourly waste heat and temperature profile
        waste_heat_profile, temperature_profile = generate_waste_heat_profiles()

        import matplotlib.pyplot as plt
        import numpy as np

        # Arrays sicherstellen
        abwaerme_profil = np.array(waste_heat_profile).flatten()
        temperatur_profil = np.array(temperature_profile).flatten()

        stunden_pro_woche = 7 * 24  # 168
        woche = 2  # zweite Woche

        start = (woche - 1) * stunden_pro_woche +96
        end = woche * stunden_pro_woche + 96

        # Ausschnitt für Woche 2
        abwaerme_week = abwaerme_profil[start:end]
        temperatur_week = temperatur_profil[start:end]
        stunden_week = np.arange(stunden_pro_woche)  # 0..167

        fig, ax1 = plt.subplots(figsize=(12, 4))

        # Linke Y-Achse: Abwärme
        ax1.plot(stunden_week, abwaerme_week, linewidth=0.8, color='blue', label='Abwärmeleistung')
        ax1.set_ylabel('Leistung (kW)')
        ax1.tick_params(axis='y')
        ax1.set_ylim(min(abwaerme_week) * 0.75, max(abwaerme_week) * 1.5)

        # Rechte Y-Achse: Temperatur
        ax2 = ax1.twinx()
        ax2.plot(stunden_week, temperatur_week, linewidth=0.8, color='red', label='Temperatur')
        ax2.set_ylabel('Temperatur (°C)')
        ax2.tick_params(axis='y')
        ax2.set_ylim(min(temperatur_week) * 0.95, max(temperatur_week) * 1.05)

        # X‑Achse: Stunden im Wochenverlauf
        stunden_ticks = np.arange(0, stunden_pro_woche, 24)
        tage_labels = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']
        ax1.set_xticks(stunden_ticks)
        ax1.set_xticklabels(tage_labels)

        # Legende
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left', fontsize=10)

        ax1.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig("abbildung.pdf", format='pdf', dpi=300, bbox_inches='tight')
        plt.show()

        self.waste_heat_data["temperature_profile"] = temperature_profile

        # Waste heat temperature is evaluated for direct integration feasibility.
        # If T_wh < T_required, heat pump provides necessary temperature lift.
        generation = self.heat_grid_data["generation"]
        T_supply = self.heat_grid_data["T_hot_heating_network"]["constant"][generation]
        waste_heat_profile_hp, COP, is_HP_used = calc_temperature_lift(waste_heat_profile, temperature_profile, T_supply)

        self.waste_heat_data["waste_heat_profile"] = waste_heat_profile_hp
        self.waste_heat_data["COP"] = COP
        self.waste_heat_data["HP"] = is_HP_used

        ##########################################
        # WASTE HEAT ECO DATA
        ##########################################
        self.waste_heat_data["inv_var_hex"]= calc_hex_costs()     # Investment costs for heat exchanger, costs for heat pump are calculated in opti_dimensioning_central_devices
        self.waste_heat_data["om_costs_hex"] = 0
        self.waste_heat_data["life_time"] = 20







    def generateWHProfiles(self, waste_heat_source, distance):
        self.waste_heat_data["type"] = waste_heat_source
        self.waste_heat_data["distance"] = distance

        def calc_position(distance):
            json_path = os.path.join(self.scenario_file_path, f"{self.scenario_name}.json")
            if os.path.exists(json_path):
                with open(json_path, encoding="utf-8") as json_file:
                    jsonData = json.load(json_file)
                    bounds = jsonData["parameters"]["district_bounds"]

            side = random.choice(['left', 'right', 'bottom', 'top'])

            if side == 'left':
                x = bounds['xmin'] - distance
                y = random.uniform(bounds['ymin'], bounds['ymax'])
            elif side == 'right':
                x = bounds['xmax'] + distance
                y = random.uniform(bounds['ymin'], bounds['ymax'])
            elif side == 'bottom':
                y = bounds['ymin'] - distance
                x = random.uniform(bounds['xmin'], bounds['xmax'])
            else:
                y = bounds['ymax'] + distance
                x = random.uniform(bounds['xmin'], bounds['xmax'])

            return [x, y]

        json_path = os.path.join(self.scenario_file_path, "wh_source.json")

        if os.path.exists(json_path):
            with open(json_path, encoding="utf-8") as json_file:
                jsonData = json.load(json_file)
                position = jsonData[0]["position"]
                wh_source = jsonData[0]["type"]
        else:
            position = calc_position(distance)
        self.waste_heat_data["position"] = position


        if waste_heat_source == "C":

            connected_load = 5000                                             # connected load of a DC in kW
            self.waste_heat_data["size"] = connected_load


            laod_factor = 0.5                                                 # ratio of the actual IT power usage to the maximum connected load
            it_load = connected_load * laod_factor
            #T_hot = 60                                                        # exit temperature of the server room
            T_cold = 20                                                       # entry temperature of the server room
            timesteps = int(self.time["dataLength"]/self.time["timeResolution"])
            waste_heat_profile = np.full(timesteps, it_load)
            temperature_profile = np.full(timesteps, T_hot)

        if waste_heat_source == "D":
            c_p_ww = 4.18 # in kJ/kgK
            rho_ww = 1000 # in kg/m^3
            PE = 10000    # Population equivalent (Einwohnerwert): indicates the average load of wastewater from one inhabitant with biodegradable substances
            Vdot_person_daily = 126 # daily water consumption per person in L/d
            Vdot_person_hourly = Vdot_person_daily/24 * 0.001 # hourly water consumption per person in m^3/h
            Vdot_ww = np.full(8760, PE * Vdot_person_hourly)

            T_min = 10.0  # °C
            T_max = 20.0  # °C
            mean_temp = (T_min + T_max) / 2
            amplitude = (T_max - T_min) / 2
            T_ref = 8 # °C

            temperature_profile = []
            for day in range(8760):
                temperature_profile.append(mean_temp - (amplitude * np.cos(2 * math.pi * (day / 8760))))

            delta_T = np.array(temperature_profile).flatten() - T_ref

            waste_heat_profile = (Vdot_ww * c_p_ww * rho_ww * delta_T)/3600

            self.waste_heat_data["size"] = PE

        self.waste_heat_data["waste_heat_profile"] = waste_heat_profile
        self.waste_heat_data["temperature_profile"] = temperature_profile

        print(waste_heat_profile)









        def seasonalProfile(name, path):
            xlsx_file = os.path.join(path, name + ".xlsx")
            df = pd.read_excel(xlsx_file, sheet_name='Abwärmepotentiale')
            df_months = df.iloc[:, 17:29].apply(pd.to_numeric, errors='coerce').dropna()
            df_months.columns = range(12)
            df_norm = df_months.div(df_months.sum(axis=1), axis=0)
            df_norm_mean = df_norm.mean(axis=0)



            monate = np.arange(12)
            data_long = df_norm.stack().reset_index(name='Lastfaktor')
            data_long.columns = ['Kuehler_ID', 'Monat', 'Lastfaktor']
            y_all = data_long['Lastfaktor'].values
            monate_long = data_long['Monat'].values
            y_mean = df_norm.mean(axis=0).values
            from scipy.optimize import curve_fit
            from sklearn.linear_model import LinearRegression

            t_aussen = np.array([2.5, 3.5, 7.0, 11.0, 15.5, 18.5, 20.5, 20.0, 16.5, 12.0, 7.0, 3.5])
            t_aussen_long = np.tile(t_aussen, len(data_long) // 12)

            model = LinearRegression()
            model.fit(t_aussen_long.reshape(-1, 1), y_all)
            y_pred_temp = model.predict(t_aussen_long.reshape(-1, 1))
            r2_temp = model.score(t_aussen_long.reshape(-1, 1), y_all)

            print(f"📊 LINEAR T_aussen (y_all, N={len(y_all)}):")
            print(f"y = {model.coef_[0]:.4f} * T + {model.intercept_:.4f}")
            print(f"R²(T) = {r2_temp:.4f}")

            def sinus_halb(x, A, B, phi):  # A=Amplitude, B=Offset
                return A * np.sin(np.pi * (x-phi) / 6) + B  # Halbperiode!

            # Fit (non-linear least squares)
            popt, pcov = curve_fit(sinus_halb, monate_long, y_all)
            A_opt, B_opt, phi_opt = popt
            perr = np.sqrt(np.diag(pcov))
            print(f"✅ Optimal: y = {A_opt:.4f} * sin(π * t / 6) + {B_opt:.4f}")

            import matplotlib.pyplot as plt
            # R²
            y_fit = sinus_halb(monate_long, *popt)
            r2 = 1 - np.sum((y_all - y_fit) ** 2) / np.sum((y_all - np.mean(y_all)) ** 2)

            print(f"Optimal: y = {A_opt:.4f}±{perr[0]:.4f} * sin(π*(t-{phi_opt:.2f}) / 6) + {B_opt:.4f}±{perr[1]:.4f}")
            print(f"R² = {r2:.4f}")

            # Plot
            plt.figure(figsize=(10, 6))
            plt.plot(monate, y_mean, 'ko-', linewidth=3, label='Real Mittel')
            plt.plot(monate, y_fit, 'r--', linewidth=3, label=f'Fit R²={r2:.3f}')
            plt.xlabel('Monat (0=Januar, 11=Dezember)');
            plt.ylabel('Normierter Lastfaktor')
            plt.title('Automatische Sinus-Regression mit Phase')
            plt.legend();
            plt.grid(alpha=0.3);
            plt.show()

            # Monatsnamen
            monats_namen = ['Jan', 'Feb', 'Mrz', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']

            # LONG-FORMAT erzeugen (DAS hat gefehlt)
            data_long = df_norm.reset_index(drop=True).stack().reset_index(name='Lastfaktor')
            data_long.columns = ['ID', 'Monat', 'y']
            data_long['Monat'] = data_long['Monat'].astype(int)


            plt.figure(figsize=(10, 5))

         #   plt.scatter(
         #       data_long["Monat"] + 1,  # 1–12 statt 0–11
         #       data_long["Lastfaktor"],
         #       alpha=0.25,
         #       s=10
         #   )

            # Mittelwertprofil
            plt.plot(
                range(1, 13),
                df_norm_mean.values,
                linewidth=3,
                label="Mittelwertprofil"
            )

            plt.xticks(range(1, 13), monats_namen)
            plt.xlabel("Monat")
            plt.ylabel("Normierter Lastfaktor")
            plt.title("Saisonale Verteilung der Kühlhäuser")
            plt.grid(alpha=0.2)

            plt.tight_layout()
            plt.savefig(os.path.join(path, 'kuehler_saison_scatter.png'), dpi=300)
            plt.show()
            plt.close()


            return df_norm
        #x = seasonalProfile("Kühlhäuser_preprocessed", path=os.path.join(self.resultPath, 'demands'))



        def loadProfile(name, path, temp_profile):



            # create array with value from the csv file
            csv_file = os.path.join(path, name + '.csv')
            df = pd.read_csv(csv_file, usecols=["Mean_Value"], sep=";", decimal=",")
            profile = df["Mean_Value"].to_numpy()[1:]

            # adjust array with profile data, in case it is missing entries or has to many of them
            if len(profile) >= 35040:
                profile = profile[:35040]
            else:
                missing = 35040 - len(profile)
                profile = np.concatenate([profile, np.full(missing, profile[-1])])  #TODO add interpolation and adjust to match initial days and holidays

            # convert the profile to an hourly profile (original data consists of 15 min steps)
            hourly_profile = profile.reshape(-1, 4).mean(axis=1)
            normed_profile = hourly_profile / hourly_profile.sum()

            # create electricity and waste heat profile
            if name == "WWTP":
                delta_T = np.array(temp_profile).flatten() - 8
                PE = self.waste_heat_data[wh_source]["PE"]
                V_dot = 142/1000 * PE * 365
                c_p = 4.2
                rho = 1000
                wh_profile = normed_profile * c_p * rho * V_dot * (1/3600) * delta_T
            else:
                # ratio between specific electricity and heat, and yearly energy consumption
                spec_wh = self.waste_heat_data[wh_source]["spec_wh"]
                prod_quantity = self.waste_heat_data[wh_source]["prod_quantity"]

                wh_profile = normed_profile * spec_wh * prod_quantity

            return wh_profile

        def calcProfile(name, temperature, time_resolution, time_horizon):

            timesteps = int(time_horizon / time_resolution)


            if name == "DC":
                it_load = self.waste_heat_data[wh_source]["IT_Load"]
                profile = np.full(timesteps, it_load)

                T_DCin = 15
                for i in range(timesteps):
                    COP = calcCOP(temperature[i])
                    if temperature[i] >= T_DCin:
                        profile[i] += it_load/COP


                # Cooling Degree Day Methode
                #CDD_ges = 0
                #CDD = []
                #for i in range(timesteps):
                #    if temperature[i] > T_set:
                #        CDD.append(temperature[i] - T_set)
                #        CDD_ges += temperature[i] - T_set
                #    else:
                #        CDD.append(0)
                #for i in range(timesteps):
                #    profile[i] += it_load * (pue - 1) * (CDD[i] / CDD_ges) * timesteps

            return profile

        def tempProfile(name):
            if name in ["paper", "DC"]:
                temp = self.waste_heat_data[wh_source]["wh_temperature"]
                temp_profile = np.full(8760, temp)
            if name == "WWTP":
                temp_profile = []
                for day in range(8760):
                    temp_profile.append(15 - (5 * np.cos(2 * math.pi * (day/8760))))


            return temp_profile

        def calcCOP(T_out):
            from scipy.interpolate import interp1d
            T_reference = np.array([0, 5, 10, 15, 20, 25, 30, 35, 40])
            COP_reference = np.array([5.8, 5.5, 5.1, 4.7, 4.34, 3.9, 3.5, 3.1, 2.6])

            cop_func = interp1d(T_reference, COP_reference, kind='linear',
                                fill_value='extrapolate', bounds_error=False)

            return cop_func(T_out)


        #temp_profile = tempProfile(name=wh_source)


#        if self.waste_heat_data[wh_source]["profile_type"] == "load":
#            self.waste_heat_data["profile"] = loadProfile(name=wh_source, path=os.path.join(self.resultPath, 'demands'), temp_profile=temp_profile)
#        else:
#            self.waste_heat_data["profile"] = calcProfile(wh_source, self.site["T_e"], self.time["timeResolution"],
#                                                          self.time["dataLength"])


#        waste_heat_profile = self.waste_heat_data["profile"]


        import matplotlib.pyplot as plt
        abwaerme_profil = np.array(waste_heat_profile).flatten()  # Vollständiges Array
        temperatur_profil = np.array(temperature_profile).flatten()

        # Zeitachse: 8760 Stunden (1 Jahr)
        stunden = np.arange(8760)

        fig, ax1 = plt.subplots(figsize=(14, 6))

        # Linke Y-Achse: Abwärme (blau)
        ax1.plot(stunden, abwaerme_profil, linewidth=0.8, color='blue', label='Abwärmeleistung')
        ax1.set_ylabel('Leistung (kW)', color='blue', fontsize=22)
        ax1.tick_params(axis='y', labelcolor='blue')

        # Rechte Y-Achse: Temperatur (rot)
        ax2 = ax1.twinx()
        ax2.plot(stunden, temperatur_profil, linewidth=0.8, color='red', label='Temperatur')
        ax2.set_ylabel('Temperatur (°C)', color='red', fontsize=22)
        ax2.tick_params(axis='y', labelcolor='red')

        # X-Achse (gemeinsam)
        monats_ticks = np.arange(0, 8760, 8760 // 12)
        monats_labels = ['Jan', 'Feb', 'Mrz', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']
        ax1.set_xticks(monats_ticks)
        ax1.set_xticklabels(monats_labels, rotation=45)


        # Titel
        fig.suptitle('Abwärme- und Temperaturprofil', fontsize=14, y=1.00)

        # Legenden kombinieren
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left', fontsize=18)

        # Grid
        ax1.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig('abwaerme_temp_profil.png', dpi=300, bbox_inches='tight')
        plt.show()


        return waste_heat_profile

    def generateDistrictComplete(self, calcUserProfiles=True, saveUserProfiles=True, topology_option="road", gen_cars=True):
        """
        All in one solution for district and demand generation.
        Within a clustered time series, data points are aggregated across different time periods
        based on the k-medoids method.

        Parameters
        ----------

        calcUserProfiles: bool, optional
            True: calculate new user profiles.
            False: load user profiles from file.
            The default is True.
        saveUserProfiles: bool, optional
            True for saving calculated user profiles in workspace (Only taken into account if calcUserProfile is True).
            The default is True.
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
        self.generateEnvironment()
        self.initializeBuildings()
        self.generateBuildings()
        self.generateDemands(calcUserProfiles, saveUserProfiles, gen_cars=gen_cars)
        self.designDecentralDevices(saveGenerationProfiles=True)

        # Check if district uses central energy supply (heat grid)
        has_heat_grid = any(
            building["buildingFeatures"]["heater"] == "heat_grid"
            for building in self.district)

        if has_heat_grid:
            # Verify geometry data (district_parameters)

            # --- Check if building positions are available and valid ---
            missing_positions = (
                    "position" not in self.scenario.columns
                    or self.scenario["position"].isnull().any()
                    or any(
                not isinstance(p, tuple) or len(p) != 2 or not all(isinstance(x, (int, float)) for x in p)
                for p in self.scenario["position"]))
            if missing_positions:
                print("No district geometry found — running simple heating network design.")
                heating_network_simple.heating_network(self)
                self.designCentralDevices(saveGenerationProfiles=True)
                self.finalizeClusterProfiles()
            else:
                print("Generating and optimizing heating network...")
                self.generateNetwork(topology_option)
                self.prepareClusteringInputs()
                self.optimization_heatingnetwork()
                self.designCentralDevices(saveGenerationProfiles=True)
                self.finalizeClusterProfiles()
        else:
            print("No central heat grid detected — skipping heating network design.")
            self.centralDevices = {}
            self.prepareClusteringInputs()

    def saveProfiles(self, name, elec, dhw, occ, gains, EV_carcharging_ondemand,
                     EV_carprofile, ev_capacity, ice_carprofile, nb_units,
                     nb_occ, heatload, bivalent, heatlimit, path,
                     individual_car_profiles=None):
        """
        Save profiles to csv.

        Parameters
        ----------
        unique_name : string
            Unique building name.
        path : string
            Results path.

        Returns
        -------
        None.
        """
        car_info_list = []
        EV_demand_individual = {}
        EV_charging_individual = {}
        ICE_fuel_individual = {}
        Car_availibility_individual = {}
        # Prepare individual car profiles for saving
        if individual_car_profiles is not None and len(individual_car_profiles) > 0:
            for i, car in enumerate(individual_car_profiles):
                car_id = car.get('car_id')
                car_info_list.append({"car_id": car_id,
                        "type": car.get("type"),
                        "location": car.get("location"),
                        "battery_capacity_wh": car.get("battery_capacity_wh")})
                if car['consumption_profile_wh'] is not None:
                    EV_demand_individual[f'EV_demand_car_{i}'] = car['consumption_profile_wh']
                if car['on_demand_charging_profile_w'] is not None:
                    EV_charging_individual[f'EV_charging_car_{i}'] = car['on_demand_charging_profile_w']
                if car['fuel_profile_l'] is not None:
                    ICE_fuel_individual[f'ICE_fuel_car_{i}'] = car['fuel_profile_l']
                if car['availability_profile'] is not None:
                    Car_availibility_individual[f'Car_availibility_car_{i}'] = car['availability_profile']

        # Create Dataframes fot the individual car profiles
        df_car_info = pd.DataFrame(car_info_list)
        df_EV_demand_individual = pd.DataFrame(EV_demand_individual)
        df_EV_charging_individual = pd.DataFrame(EV_charging_individual)
        df_ICE_fuel_individual = pd.DataFrame(ICE_fuel_individual)
        df_Car_availibility_individual = pd.DataFrame(Car_availibility_individual)

        data_dict = {
            'Electricity': (pd.DataFrame(elec), ["Electricity Demand (W)"]),
            'Hot Water': (pd.DataFrame(dhw), ["Drinking Hot Water Demand (W)"]),
            'Occupancy': (pd.DataFrame(occ), ["Number of Occupants"]),
            'Internal Gains': (pd.DataFrame(gains), ["Internal Gains (W)"]),
            'EV_demand_agg': (pd.DataFrame(EV_carprofile), ["Total Electric Vehicle Energy Demand (Wh)"]),
            'EV_charging_agg': (pd.DataFrame(EV_carcharging_ondemand), ["Total Electric Vehicle Charging Power on-Demand (W)"]),
            'ICE_fuel_agg': (pd.DataFrame(ice_carprofile), ["Total ICE Fuel consumption per timestep (L)"]),
            'EV_demand_individual': (df_EV_demand_individual,list(df_EV_demand_individual.columns)),
            'EV_charging_individual': (df_EV_charging_individual,list(df_EV_charging_individual.columns)),
            'ICE_fuel_individual': (df_ICE_fuel_individual,list(df_ICE_fuel_individual.columns)),
            'Car_availibility_individual': (df_Car_availibility_individual,list(df_Car_availibility_individual.columns)),
            'Car Info': (df_car_info, list(df_car_info.columns)),
            'Building Info': (pd.DataFrame({
                "Number of Flats or main Rooms": [nb_units],
                "Number of Occupants": str(nb_occ)[1:-1],
                'EV_capacity_agg': str(ev_capacity)[1:-1],
                "Design Heat Load (W)": [heatload],
                "Bivalent Heat Load (W)": [bivalent],
                "Heat Limit Heat Load (W)": [heatlimit]
            }), ["Number of Flats or main Rooms", "Number of Occupants", "EV_capacities",
                 "Design Heat Load (W)", "Bivalent Heat Load (W)",
                 "Heat Limit Heat Load (W)"])
        }

        excel_file = os.path.join(path, name + '.xlsx')
        with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
            for sheet_name, (data, header) in data_dict.items():
                df = pd.DataFrame(data)
                df.to_excel(writer, sheet_name=sheet_name, index=False, header=header)

    def saveHeatingProfile(self, heat, cooling, name, path):
        """
        Save heating demand to csv.

        Parameters
        ----------
        unique_name : string
            Unique building name.
        path : string
            Results path.

        Returns
        -------
        None.
        """

        excel_file = os.path.join(path, name + '.xlsx')
        with pd.ExcelWriter(excel_file, engine='openpyxl', mode='a', if_sheet_exists='overlay') as writer:
            cooling_df = pd.DataFrame(cooling)
            heating_df = pd.DataFrame(heat)
            cooling_df.to_excel(writer, sheet_name='cooling', index=False, header=['Cooling in W'])
            heating_df.to_excel(writer, sheet_name='heating', index=False, header=['Heating in W'])

    def loadProfiles(self, name, path, gen_cars=True):
        """
        Load profiles from csv.

        Parameters
        ----------
        unique_name : string
            Unique building name.
        path : string
            Results path.

        Returns
        -------
        """

        excel_file = os.path.join(path, name + '.xlsx')
        workbook = openpyxl.load_workbook(excel_file, data_only=True)

        def load_sheet_to_numpy(workbook, sheet_name):
            sheet = workbook[sheet_name]
            data = []
            for row in sheet.iter_rows(min_row=2, values_only=True):
                if len(row)>1:
                    data.append(list(row))
                else:
                    data.append(row[0])
            return np.array(data)

        building_id = int(name.split('_')[0])
        idx = self.building_dict[building_id]

        elec = load_sheet_to_numpy(workbook, 'Electricity')
        dhw = load_sheet_to_numpy(workbook, 'Hot Water')
        occ = load_sheet_to_numpy(workbook, 'Occupancy')
        gains = load_sheet_to_numpy(workbook, 'Internal Gains')

        # Load car profiles
        individual_car_profiles = []
        if gen_cars: # Only load car profiles if cars are supposed to be generated
            EV_carprofile = load_sheet_to_numpy(workbook, 'EV_demand_agg')
            EV_carcharging_ondemand = load_sheet_to_numpy(workbook, 'EV_charging_agg')
            ice_carprofile = load_sheet_to_numpy(workbook, 'ICE_fuel_agg')

            df_car_info = pd.read_excel(excel_file, sheet_name='Car Info')
            df_EV_demand = pd.read_excel(excel_file, sheet_name='EV_demand_individual')
            df_EV_charging = pd.read_excel(excel_file, sheet_name='EV_charging_individual')
            df_ICE_fuel = pd.read_excel(excel_file, sheet_name='ICE_fuel_individual')
            df_Car_avail = pd.read_excel(excel_file, sheet_name='Car_availibility_individual')

            #reconstruct individual car profiles
            for i, row in df_car_info.iterrows():
                # Extract car details
                car_id = row['car_id']
                car_type = row['type']
                location = row['location']
                battery_capacity_wh = row['battery_capacity_wh']

                # Extracts profiles
                ev_demand_col = f'EV_demand_car_{i}'
                ev_charge_col = f'EV_charging_car_{i}'
                ice_fuel_col = f'ICE_fuel_car_{i}'
                avail_col = f'Car_availibility_car_{i}'

                if ev_demand_col in df_EV_demand.columns:
                    consumption_profile_wh = df_EV_demand[ev_demand_col].to_numpy()
                else:
                    consumption_profile_wh = None
                if ev_charge_col in df_EV_charging.columns:
                    on_demand_charging_profile_w = df_EV_charging[ev_charge_col].to_numpy()
                else:
                    on_demand_charging_profile_w = None
                if ice_fuel_col in df_ICE_fuel.columns:
                    fuel_profile_l = df_ICE_fuel[ice_fuel_col].to_numpy()
                else:
                    fuel_profile_l = None
                if avail_col in df_Car_avail.columns:
                    availability_profile = df_Car_avail[avail_col].to_numpy()
                else:
                    availability_profile = None

                car_profile = {
                    'car_id': car_id,
                    'type': car_type,
                    'location': location,
                    'battery_capacity_wh': battery_capacity_wh,
                    'consumption_profile_wh': consumption_profile_wh,
                    'on_demand_charging_profile_w': on_demand_charging_profile_w,
                    'fuel_profile_l': fuel_profile_l,
                    'availability_profile': availability_profile
                }
                individual_car_profiles.append(car_profile)

        else:
            # if no cars are generated, return zero profiles
            EV_carprofile = np.zeros(int(self.time["dataLength"] / self.time["timeResolution"]))
            EV_carcharging_ondemand = np.zeros(int(self.time["dataLength"] / self.time["timeResolution"]))
            ice_carprofile = np.zeros(int(self.time["dataLength"] / self.time["timeResolution"]))

        # Load building info
        sheet = workbook['Building Info']
        other_data = [cell for cell in sheet.iter_rows(min_row=2, max_row=2, values_only=True)][0]  # Extracts first row
        nb_flats = int(other_data[0])
        nb_main_rooms = nb_flats
        nb_occ = np.fromstring(other_data[1], dtype=int, sep=',')
        EV_capacity = np.fromstring(other_data[2], dtype=float, sep=',')
        heatload = float(other_data[3])
        bivalent = float(other_data[4])
        heatlimit = float(other_data[5])

        workbook.close()

        return elec, dhw, occ, gains, EV_carcharging_ondemand, EV_carprofile, ice_carprofile, nb_flats, nb_main_rooms, nb_occ, EV_capacity, heatload, bivalent, heatlimit, individual_car_profiles

    def loadHeatingProfiles(self, name, path):
        """
        Load profiles from csv.

        Parameters
        ----------
        unique_name : string
            Unique building name.
        path : string
            Results path.

        Returns
        -------
        None.
        """

        excel_file = os.path.join(path, name + '.xlsx')
        workbook = openpyxl.load_workbook(excel_file, data_only=True)

        def load_sheet_to_numpy(workbook, sheet_name):
            sheet = workbook[sheet_name]
            data = []
            for row in sheet.iter_rows(min_row=2, values_only=True):
                data.append(row[0])
            return np.array(data)

        heat = load_sheet_to_numpy(workbook, 'heating')
        cooling = load_sheet_to_numpy(workbook, 'cooling')

        workbook.close()

        return heat, cooling

    def designDecentralDevices(self, saveGenerationProfiles=True):
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

            # %% create building energy system object
            # get capacities of all possible devices
            building["bes_obj"] = BES(physics=self.physics,
                          decentral_device_data=self.decentral_device_data,
                          design_building_data=self.design_building_data,
                          file_path=self.filePath)
            building["capacities"] = building["bes_obj"].designECS(building, self.site)

            # calculate PV and STC generation
            building["generationPV"], building["generationSTC"] = \
                sun.calcPVAndSTCProfile(time=self.time,
                                        site=self.site,
                                        devices=self.decentral_device_data,
                                        area_roof=building["envelope"].A["opaque"]["roof"],
                                        # In Germany, this is a roof pitch between 30 and 35 degrees
                                        beta=[35],
                                        # surface azimuth angles (Orientation to the south: 0°)
                                        gamma=[building["buildingFeatures"]["gamma_PV"]],
                                        usageFactorPV1=building["buildingFeatures"]["f_PV1"],
                                        usageFactorPV2=building["buildingFeatures"]["f_PV2"],
                                        usageFactorSTC=building["buildingFeatures"]["f_STC"])

            # optionally save generation profiles
            if saveGenerationProfiles == True:
                np.savetxt(os.path.join(self.resultPath, 'generation')
                           + '/decentralPV_' + building["unique_name"] + '.csv',
                           building["generationPV"],
                           delimiter=',')
                np.savetxt(os.path.join(self.resultPath, 'generation')
                           + '/decentralSTC_' + building["unique_name"] + '.csv',
                           building["generationSTC"],
                           delimiter=',')

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
            np.savetxt(os.path.join(self.resultPath, 'generation', 'centralPV.csv'),
                       self.centralDevices["generation"]["PV"],
                       delimiter=',')
            np.savetxt(os.path.join(self.resultPath, 'generation', 'centralSTC.csv'),
                       self.centralDevices["generation"]["STC"],
                       delimiter=',')
            np.savetxt(os.path.join(self.resultPath, 'generation', 'centralWind.csv'),
                       self.centralDevices["generation"]["Wind"],
                       delimiter=',')

    def prepareClusteringInputs(self):
        """
        Prepare and cluster building-level demand and environmental data.
        """
        print("Preparing initial clustering (pre-optimization)...")
        self.clusterProfiles(centralEnergySupply=False)

    def finalizeClusterProfiles(self):
        """
        Perform final clustering including central generation and
        heating network losses after optimization.
        """
        print("Finalizing clustering (post-optimization)...")
        self.clusterProfiles(centralEnergySupply=True)

    def clusterProfiles(self, centralEnergySupply):
        """
        Perform time series aggregation for profiles by using the k-medoids clustering algorithm.

        Returns
        -------
        None.
        """

        # calculate cluster time horizon
        initialArrayLenght = (self.time["clusterLength"] / self.time["timeResolution"])
        lengthArray = initialArrayLenght
        while lengthArray <= len(self.site["T_e"]):
            lengthArray += initialArrayLenght
        lengthArray = int(lengthArray - initialArrayLenght)

        # adjust profiles with calculated array length
        adjProfiles = {}
        # loop over buildings
        for i, b in enumerate(self.district):
            adjProfiles[i] = {}
            adjProfiles[i]["elec"] = b["user"].elec[0:lengthArray]
            adjProfiles[i]["dhw"] = b["user"].dhw[0:lengthArray]
            adjProfiles[i]["heat"] = b["user"].heat[0:lengthArray]
            adjProfiles[i]["cooling"] = b["user"].cooling[0:lengthArray]
            adjProfiles[i]["occ"] = b["user"].occ[0:lengthArray]
            adjProfiles[i]["EV_carcharging_ondemand"] = b["user"].EV_carcharging_ondemand[0:lengthArray]
            adjProfiles[i]["EV_carprofile"] = b["user"].EV_carprofile[0:lengthArray]
            adjProfiles[i]["generationPV"] = b["generationPV"][0:lengthArray]
            adjProfiles[i]["generationSTC"] = b["generationSTC"][0:lengthArray]

            # Individual car profiles
            adjProfiles[i]["individual_cars"] = []

            for car in b["user"].individual_car_profiles:
                adj_car = {
                    "availability_profile": car["availability_profile"][0:lengthArray] if car["availability_profile"] is not None else None,
                    "consumption_profile_wh": car["consumption_profile_wh"][0:lengthArray] if car["consumption_profile_wh"] is not None else None,
                    "on_demand_charging_profile_w": car["on_demand_charging_profile_w"][0:lengthArray] if car["on_demand_charging_profile_w"] is not None else None,
                    "fuel_profile_l": car["fuel_profile_l"][0:lengthArray] if car["fuel_profile_l"] is not None else None
                }
                adjProfiles[i]["individual_cars"].append(adj_car)

        if centralEnergySupply == True:

            adjProfiles["losses_heating_network"] = self.heat_grid_data["total_losses_heating_network"][0:lengthArray]
            adjProfiles["losses_cooling_network"] = self.heat_grid_data["total_losses_cooling_network"][0:lengthArray]
            adjProfiles["pump_power"] = self.heat_grid_data["pump_power"][0:lengthArray]

            if self.centralDevices["capacities"]["WT"]["cap"] > 0:
                adjProfiles["generationCentralWT"] = self.centralDevices["generation"]["Wind"][0:lengthArray]
            else:
                # no central WT exists; but array with just zeros leads to problem while clustering
                adjProfiles["generationCentralWT"] = np.ones(lengthArray) * sys.float_info.epsilon

            if self.centralDevices["capacities"]["PV"]["cap"] > 0:
                adjProfiles["generationCentralPV"] = self.centralDevices["generation"]["PV"][0:lengthArray]
            else:
                # no central PV exists; but array with just zeros leads to problem while clustering
                adjProfiles["generationCentralPV"] = np.ones(lengthArray) * sys.float_info.epsilon

            if self.centralDevices["capacities"]["STC"]["cap"] > 0:
                adjProfiles["generationCentralSTC"] = self.centralDevices["generation"]["STC"][0:lengthArray]
            else:
                # no central STC exists; but array with just zeros leads to problem while clustering
                adjProfiles["generationCentralSTC"] = np.ones(lengthArray) * sys.float_info.epsilon

            if "waste_heat_profile" in self.waste_heat_data:
                adjProfiles["COP_profile"] = self.waste_heat_data["COP"][0:lengthArray]
                adjProfiles["HP_profile"] = self.waste_heat_data["HP"][0:lengthArray]


        if "waste_heat_profile" in self.waste_heat_data:
            adjProfiles["waste_heat_profile"] = self.waste_heat_data["waste_heat_profile"][0:lengthArray]


        # wind speed, solar radiance, ambient temperature and soil temperature
        adjProfiles["wind_speed"] = self.site["wind_speed"][0:lengthArray]
        adjProfiles["SunTotal"] = self.site["SunTotal"][0:lengthArray]
        adjProfiles["T_e"] = self.site["T_e"][0:lengthArray]
        adjProfiles["T_soil"] = self.heat_grid_data["T_soil"][0:lengthArray]

        # Prepare clustering
        # weights for clustering algorithm indicating the focus onto this profile
        # The relevant features for clustering are
        # 1. electricity demand of the buildings (each building with weight 1)
        # 2. outdoor temperature (weight = number of buildings)
        # 3. Windspeed (weight = number of buildings) - only if central WT exists
        # 4. Solar Radiation (weight = number of buildings if central PV or STC exist and + 1 for each building with PV or STC)
        # The profiles are not scaled currently. If otherwise desired set scalings.append(True) for the relevant profiles.

        inputsClustering, weights, scalings = [], [], []

        # loop over buildings
        for i in range(len(self.district)):
            inputsClustering.append(adjProfiles[i]["elec"])
            weights.append(1)
            scalings.append(False)

            inputsClustering.append(adjProfiles[i]["dhw"])
            weights.append(0)
            scalings.append(False)

            inputsClustering.append(adjProfiles[i]["heat"])
            weights.append(0)
            scalings.append(False)

            inputsClustering.append(adjProfiles[i]["cooling"])
            weights.append(0)
            scalings.append(False)

            inputsClustering.append(adjProfiles[i]["occ"])
            weights.append(0)
            scalings.append(False)

            inputsClustering.append(adjProfiles[i]["EV_carcharging_ondemand"])
            weights.append(0)      # This profile is not used at all for clustering
            scalings.append(False)  # This profile is not scaled

            inputsClustering.append(adjProfiles[i]["EV_carprofile"])
            weights.append(0)      # This profile is not used at all for clustering
            scalings.append(False)  # This profile is not scaled

            inputsClustering.append(adjProfiles[i]["generationPV"])
            weights.append(0)
            scalings.append(False)

            inputsClustering.append(adjProfiles[i]["generationSTC"])
            weights.append(0)
            scalings.append(False)

        # Add individual car profiles
        index_individual_cars_start = len(inputsClustering)
        for i in range(len(self.district)):
            for car in adjProfiles[i]["individual_cars"]:
                # 4 profiles per car

                if car["availability_profile"] is not None:
                    inputsClustering.append(car["availability_profile"])
                    weights.append(0) # Vorerst kein Gewicht
                    scalings.append(False)

                if car["consumption_profile_wh"] is not None:
                    inputsClustering.append(car["consumption_profile_wh"])
                    weights.append(0)
                    scalings.append(False)

                if car["on_demand_charging_profile_w"] is not None:
                    inputsClustering.append(car["on_demand_charging_profile_w"])
                    weights.append(0)
                    scalings.append(False)

                if car["fuel_profile_l"] is not None:
                    inputsClustering.append(car["fuel_profile_l"])
                    weights.append(0)
                    scalings.append(False)


        # Add central energy supply profiles
        index_central = len(inputsClustering) # Index of the first entry of central energy profiles

        if centralEnergySupply == True:

            # Heating and cooling networks losses
            inputsClustering.append(adjProfiles["losses_heating_network"])
            weights.append(0)
            scalings.append(False)

            inputsClustering.append(adjProfiles["losses_cooling_network"])
            weights.append(0)
            scalings.append(False)

            # central pump power
            inputsClustering.append(adjProfiles["pump_power"])
            weights.append(0)
            scalings.append(False)

            # central renewable generation
            inputsClustering.append(adjProfiles["generationCentralWT"])
            weights.append(0)
            scalings.append(False)

            inputsClustering.append(adjProfiles["generationCentralPV"])
            weights.append(0)
            scalings.append(False)

            inputsClustering.append(adjProfiles["generationCentralSTC"])
            weights.append(0)
            scalings.append(False)

            if "waste_heat_profile" in self.waste_heat_data:
                inputsClustering.append(adjProfiles["COP_profile"])
                weights.append(0)
                scalings.append(False)

                inputsClustering.append(adjProfiles["HP_profile"])
                weights.append(0)
                scalings.append(False)


        if "waste_heat_profile" in self.waste_heat_data:
            inputsClustering.append(adjProfiles["waste_heat_profile"])
            weights.append(0)
            scalings.append(False)

        # Wind speed (only relevant for clustering)
        inputsClustering.append(adjProfiles["wind_speed"])
        if centralEnergySupply == True and self.centralDevices["capacities"]["WT"]["cap"] > 0: weights.append(len(self.district))
        else: weights.append(0)
        scalings.append(False)

        # Solar radiation (only relevant for clustering)
        inputsClustering.append(adjProfiles["SunTotal"])
        # determine weight for solar radiation
        solar_weight = 0
        if centralEnergySupply == True:
            if (self.centralDevices["capacities"]["PV"]["cap"] > 0 or
                self.centralDevices["capacities"]["STC"]["cap"] > 0):
                solar_weight += len(self.district)

        for i in range(len(self.district)):
            if (self.district[i]["buildingFeatures"]["f_PV1"] > 0 or
                self.district[i]["buildingFeatures"]["f_PV2"] > 0 or
                self.district[i]["buildingFeatures"]["f_STC"] > 0):
                solar_weight += 1

        weights.append(solar_weight)
        scalings.append(False)

        # ambient temperature
        inputsClustering.append(adjProfiles["T_e"])
        weights.append(len(self.district))
        scalings.append(False)

        # soil temperature
        inputsClustering.append(adjProfiles["T_soil"])
        weights.append(0)
        scalings.append(False)

        # Perform clustering
        (newProfiles, nc, y, z, transfProfiles) = cm.cluster(np.array(inputsClustering),
                                                             number_clusters=self.time["clusterNumber"],
                                                             len_cluster=int(initialArrayLenght),
                                                             weights=weights,
                                                             scalings=scalings,
                                                             pyomo_config=self.pyomo_config)

        # safe clustered profiles of all buildings
        for i in range(len(self.district)):
            index_house = int(9)    # number of profiles per building
            self.district[i]["user"].elec_cluster = newProfiles[index_house * i]
            self.district[i]["user"].dhw_cluster = newProfiles[index_house * i + 1]
            self.district[i]["user"].heat_cluster = newProfiles[index_house * i + 2]
            self.district[i]["user"].cooling_cluster = newProfiles[index_house * i + 3]
            self.district[i]["user"].occ_cluster = newProfiles[index_house * i + 4]
            self.district[i]["user"].EV_carcharging_ondemand_cluster = newProfiles[index_house * i + 5]
            self.district[i]["user"].EV_carprofile_cluster = newProfiles[index_house * i + 6]
            self.district[i]["generationPV_cluster"] = newProfiles[index_house * i + 7]
            self.district[i]["generationSTC_cluster"] = newProfiles[index_house * i + 8]


        # Get individual car profiles
        profile_counter = index_individual_cars_start
        for i in range(len(self.district)):
            self.district[i]["user"].individual_car_profiles_cluster = []

            for car in self.district[i]["user"].individual_car_profiles:
                profiles_car_counter = 0
                clustered_car_data = {
                    # Get important metadata from the original
                    "car_id": car.get("car_id"),
                    "type": car.get("type"),
                    "location": car.get("location"),
                    "battery_capacity_wh": car.get("battery_capacity_wh"),
                }
                if car["availability_profile"] is not None:
                    clustered_car_data["availability_profile_cluster"] = newProfiles[profile_counter]
                    profiles_car_counter += 1
                else:
                    clustered_car_data["availability_profile_cluster"] = None

                if car["consumption_profile_wh"] is not None:
                    clustered_car_data["consumption_profile_wh_cluster"] = newProfiles[profile_counter + profiles_car_counter]
                    profiles_car_counter += 1
                else:
                    clustered_car_data["consumption_profile_wh_cluster"] = None

                if car["on_demand_charging_profile_w"] is not None:
                    clustered_car_data["on_demand_charging_profile_w_cluster"] = newProfiles[profile_counter + profiles_car_counter]
                    profiles_car_counter += 1
                else:
                    clustered_car_data["on_demand_charging_profile_w_cluster"] = None

                if car["fuel_profile_l"] is not None:
                    clustered_car_data["fuel_profile_l_cluster"] = newProfiles[profile_counter + profiles_car_counter]
                    profiles_car_counter += 1
                else:
                    clustered_car_data["fuel_profile_l_cluster"] = None

                self.district[i]["user"].individual_car_profiles_cluster.append(clustered_car_data)
                # Increment counter for the next car by 4
                profile_counter += profiles_car_counter


        if centralEnergySupply == True:
            self.heat_grid_data["total_losses_heating_network_cluster"] = newProfiles[index_central]
            self.heat_grid_data["total_losses_cooling_network_cluster"] = newProfiles[index_central + 1]
            self.heat_grid_data["pump_power_cluster"] = newProfiles[index_central + 2]
            self.centralDevices["generation"]["Wind_cluster"] = newProfiles[index_central + 3]
            self.centralDevices["generation"]["PV_cluster"] = newProfiles[index_central + 4]
            self.centralDevices["generation"]["STC_cluster"] = newProfiles[index_central + 5]
            if "waste_heat_profile" in self.waste_heat_data:
                self.waste_heat_data["COP_clustered"] = newProfiles[index_central + 6]
                self.waste_heat_data["HP_clustered"] = newProfiles[index_central + 7]
                self.waste_heat_data["clustered_profile"] = newProfiles[index_central + 8]
        elif "waste_heat_profile" in self.waste_heat_data:
            self.waste_heat_data["clustered_profile"] = newProfiles[index_central]



        self.site["T_e_cluster"] = newProfiles[-2]
        self.heat_grid_data["T_soil_cluster"] = newProfiles[-1]

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

        # initialize result dictionary for all clusters
        self.resultsOptimization = {}

        simulated_years = self.ecoData["interpolation_points"]

        self.resultsOptimization = {year: {} for year in simulated_years}

        # Remove all solution files from previous optimizations
        opti_central.remove_previous_models_and_solutions() # For better visibility remove previous solution files

        # simulate all years
        start_time = time.time()
        for i, year in enumerate(simulated_years):
            sim_ecoData = self.all_sim_ecoData[year]

            # Simulate each cluster every year
            for cluster in range(self.time["clusterNumber"]):
                # optimize operating costs of the district for current cluster
                print(f"\nStarting optimization for cluster {cluster + 1}/{self.time['clusterNumber']} for year {i+1}/{len(simulated_years)}...")
                results_temp = opti_central.run_opti_central(data=self, year=year, cluster=cluster, sim_ecoData=sim_ecoData)

                # save results as attribute
                self.resultsOptimization[year][cluster] = results_temp # Save the results of the optimization for each cluster

        end_time = time.time()
        print(f"\nOptimization of all clusters for all simulated years completed in {end_time - start_time:.2f} seconds.")

    def calculate_ecoData_per_cluster(self):
        ecoData = self.ecoData
        simulated_years = self.ecoData["interpolation_points"]
        observation_time = self.ecoData["observation_time"]

        # select the relevant subset of ecoData for optimization
        single_value_keys = ['num_interpolation_points','interpolation_points', 'observation_time','interest_rate', 'optimization_focus']
        ecoData = {k: v for k, v in self.ecoData.copy().items() if k not in single_value_keys}

        # Identify the years that belong to each interpolation segment
        year_segments = {k: [] for k in simulated_years}


        for i in range(observation_time): # 0,1,...,observation_time-1
            for j in range(len(simulated_years)):
                if simulated_years[j] == simulated_years[-1]:
                    if i >= simulated_years[j]:
                        year_segments[simulated_years[j]].append(i)
                        break
                if simulated_years[j] <= i < simulated_years[j+1]:
                    year_segments[simulated_years[j]].append(i)
                    break

        all_sim_ecoData = {}

        interest_factor = self.ecoData['interest_rate']
        q = 1 + interest_factor

        for year in simulated_years:
            relevant_years = year_segments[year]
            all_sim_ecoData[year] = {}  # Initialize dictionary for this year

            n = len(relevant_years)
            if q < 1:
                print(f"Warning: interest factor q < 1 (q={q}). If not wanted check ecoData interest rate.")

            if q!=1:
                denom = sum(1/(q**idx) for idx in range(n))
            elif q==1:
                denom = n

            for key in ecoData.keys():
                subset_values = [ecoData[key][i] for i in relevant_years if i < len(ecoData[key])]

                # Calculate present value (PV) of the subset values
                pv = sum(val / (q ** idx) for idx, val in enumerate(subset_values))

                # Calculate effective annualized price
                effective_price = pv/denom

                all_sim_ecoData[year][key] = effective_price

            # Add the values in single_value_keys to each year's ecoData
            for key in single_value_keys:
                all_sim_ecoData[year][key] = self.ecoData[key]

        return all_sim_ecoData

    def calculateKPIs(self):
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
        #self.KPIs.dumpdata(self)

        # Plot everything
        #plot_all(self)

    def designNetworkwithNode(self):
        """
        Ignore road restrictions and connect all building nodes and energy center nodes via the shortest path.
        using Minimum Spanning Tree(MST) algorithm

        Returns
        -------
        None.
        """
        # get the input data for the optimizer
        json_path = os.path.join(self.scenario_file_path, f"{self.scenario_name}.json")
        wasteheat_path = os.path.join(self.scenario_file_path, "wh_source.json")

        # only get the position of buildings connected to the heat grid
        buildings_info = []
        for building in self.district:
            if building["buildingFeatures"]["heater"] == "heat_grid":
                pos = building["buildingFeatures"]["position"]
                building_dict = {"building": building["unique_name"],
                                 "position": pos}
                buildings_info.append(building_dict)

        if os.path.exists(json_path):
            district_type = self.site["district_parameters"]["district_type"]
            with open(json_path, encoding="utf-8") as json_file:
                jsonData = json.load(json_file)
                # buildings_info = jsonData["values"]["buildings_info"]
                transformer_info = jsonData["values"]["transformer_station"]
        else:
            # if JSON file not found → Extract building coordinates from district data
            district_type = "unknown"

            # Randomly choose one building as transformer base
            chosen_building = random.choice(buildings_info)
            base_pos = chosen_building["position"]

            # Apply small random offset between choosen building and transformer (e.g., ±5 meters)
            min_dist = 5  # minimum 5 meters away
            max_dist = 10  # minimum 5 meters away
            distance = random.uniform(min_dist, max_dist)
            angle = random.uniform(0, 2 * math.pi)

            offset_x = distance * math.cos(angle)
            offset_y = distance * math.sin(angle)
            transformer_info = {
                "position": [base_pos[0] + offset_x, base_pos[1] + offset_y]
            }

        if "waste_heat_profile" in self.waste_heat_data:
            wasteheat_info = self.waste_heat_data["position"]
        else:
            wasteheat_info = None



        run_pipeline_node(district_type, buildings_info, transformer_info, wasteheat_info)

    def designNetworkwithRoad(self):
        """
        Consider road constraints, ensuring all main pipelines are laid beneath roads.
        using Steiner Tree algorithm

        Returns
        -------
        None.
        """
        # get the input data for the optimizer
        district_type = self.site["district_parameters"]["district_type"]
        building_width = self.site["district_parameters"]["building_width"]
        house_connection = self.site["district_parameters"]["house_connection"]

        wasteheat_path = os.path.join(self.scenario_file_path, "wh_source.json")

        # only get the position of buildings connected to the heat grid
        buildings_info = []
        i = 0
        for building in self.district:
            if building["buildingFeatures"]["heater"] == "heat_grid":
                pos = building["buildingFeatures"]["position"]
                building_dict = {"id": i,
                                 "building": building["unique_name"],
                                 "position": pos}
                buildings_info.append(building_dict)
                i += 1

        with open(os.path.join(self.scenario_file_path, f"{self.scenario_name}.json"), encoding="utf-8") as json_file:
            jsonData = json.load(json_file)
        # buildings_info = jsonData["values"]["buildings_info"]
        lines_info = jsonData["values"]["lines_info"]
        transformer_info = jsonData["values"]["transformer_station"]
        if os.path.exists(wasteheat_path):
            with open(wasteheat_path, encoding="utf-8") as json_file:
                jsonData = json.load(json_file)

        run_pipeline_road(district_type, building_width, house_connection, buildings_info, lines_info, transformer_info)

    def generateNetwork(self, topology_option):
        """
        Select a method for optimizing the network topology structure and optimize/load file

        Parameters
        ----------
        topology_option: string
            “node”: ignores road constraints,
            “road”: considers road constraints, ensuring all main pipelines are laid beneath roads.
        Returns
        -------
        None.
        """

        # --- Check if the geometry JSON exists ---
        if "district_parameters" not in self.site and topology_option == "road":
            print(
                "The district geometry JSON ('<scenario_name>.json') was not found.\n"
                "The district layout (roads) is not defined, only building positions are available.\n"
                "Switching to topology_option='node' instead of 'road'."
            )
            topology_option = "node"
        else:
            topology_option = topology_option
        topology_option = "node"
        # design the heating network
        if topology_option == "node":
            self.designNetworkwithNode()
        elif topology_option == "road":
            self.designNetworkwithRoad()

        # get topology filename
        json_path = os.path.join(self.scenario_file_path, f"{self.scenario_name}.json")
        if os.path.exists(json_path):
            district_type = self.site["district_parameters"]["district_type"]
        else:
            # if JSON file not found
            district_type = "unknown"
        connected_building_count = sum(
            1 for building in self.district
            if building["buildingFeatures"]["heater"] == "heat_grid"
        )
        topology_file = f"topology_{topology_option}_{district_type}_buildings_{connected_building_count}.json"

        # load the file of the heating network topology
        with open(os.path.join(self.scenario_file_path, topology_file)) as json_file:
            jsonData = json.load(json_file)

        self.pipeline_nodes = jsonData.get("nodes", {})
        self.pipeline_topology = jsonData.get("edges", {})
        self.pipeline_topology_wh = jsonData.get("edges_wh", {})

    def optimization_heatingnetwork(self):
        """
        Optimize the diameter of each pipeline segments.

        The heating system generation and temperature mode is selected in heat_grid.json.
        Heating system generation: "3rd", "4th" or "5th"
            Each heating generation corresponds to different supply and return water temperatures.
        Temperature mode: "Constant" or "Heating_curve"
            Constant: The supply and return temperature is set as a constant value.
            Heating_curve(Variable-constant operation mode): controlled within limits depending on the outdoor temperature

        Returns
        -------
        None.
        """
        network_optimization3(self)


def generate_demands_worker_wrapper(args):
    """
    Wrapper-Funktion außerhalb der Klasse, da multiprocessing pickling benötigt.
    Args enthält (building, calcUserProfiles, saveUserProfiles, andere Parameter)
    """
    self_ref, building, calcUserProfiles, saveUserProfiles, gen_cars = args
    self_ref.generate_demands_worker(building, calcUserProfiles, saveUserProfiles, gen_cars=gen_cars)

    result = {
        "unique_name": building["unique_name"],
        "elec": building["user"].elec,
        'dhw': building["user"].dhw,
        'cooling': building["user"].cooling,
        'heating': building["user"].heat,
        'occ': building["user"].occ,
        'EV_carcharging_ondemand': building["user"].EV_carcharging_ondemand,
        'EV_carprofile': building["user"].EV_carprofile,
        "ev_capacity": building["user"].ev_capacity,
        'ice_carprofile': building["user"].ice_carprofile,
        'gains': building["user"].gains,
        "nb_units": building["user"].nb_units,
        'nb_occ': building["user"].nb_occ,
        'envelope': building["envelope"],
        'night_setback': building["buildingFeatures"]["night_setback"],
        'individual_car_profiles': building["user"].individual_car_profiles
    }

    return result

def parse_position(val):
    """
    The building coordinates read directly from CSV files are often irregular and need correction.
    For example: ('1','2','.','3',',','4','5','.','6') → (12.3, 45.6)
    """
    # If the input is a string like "(12.3,45.6)", parse it into a tuple of floats.
    if isinstance(val, str):
        return tuple(float(x.strip()) for x in val.strip("()").split(","))
    # If the input is a tuple or list of characters like ('1', '2', '.', '3', ',', '4', '5', '.', '6')
    elif isinstance(val, (tuple, list)):
        pos_str = "".join(val)
        return tuple(float(x.strip()) for x in pos_str.strip("()").split(","))
    # For other data types, return the value as is.
    return val

def generate_industrial_profile(self, waste_heat_source, prod, timesteps, schichttyp):
    T_ref = np.mean(self.site["T_e"])  # reference temperature is assumed to be the average outside temperature
    print(f"Hier ist die durchschnittliche Außenlufttemp: {T_ref}")
    deltaT_pinch = 5  # pinch point temperature in K
    generation = self.heat_grid_data["generation"]
    print(generation)
    T_supply = self.heat_grid_data["T_hot_heating_network"]["constant"][generation]
    T_return = self.heat_grid_data["T_cold_heating_network"]["constant"][generation]
    T_collector_water_supply = T_supply + deltaT_pinch
    T_collector_water_return = T_return + deltaT_pinch

    json_path = os.path.join(self.scenario_file_path, "waste_heat", f"{waste_heat_source}.xlsx")

    df = pd.read_excel(json_path, sheet_name="Tabelle1")
    #print(df.columns.tolist())


    standort_col = 'Ort'
    waerme_col = "Wärmemenge pro Jahr (in kWh/a)"
    production_col  = 'Produktionsmenge [Tonnen/a]'
    #c_p_col = 'Cp [kJ/kg*K]'
    temperature_col = 'Durchschnittliches Temperaturniveau (in °C)'
    hours_col = 'Durchschnittliche tägl. Verfügbarkeit (in h)'

    industry_data = {}
    for idx, row in df.iterrows():
        standort = row[standort_col]

        if pd.isna(standort):
            continue

        if standort not in industry_data:
            industry_data[standort] = {
                "Jahresproduktionsmenge": row[production_col],
                "Wärmemenge": [],
                "Temperatur": [],
                "Verfügbarkeit": [],
                "c_p": []
            }

        industry_data[standort]["Wärmemenge"].append(row[waerme_col])
        industry_data[standort]["Temperatur"].append(row[temperature_col])
        industry_data[standort]["Verfügbarkeit"].append(row[hours_col])
        #industry_data[standort]["c_p"].append(row[c_p_col])

    for loc in list(industry_data.keys()):
        direct = False
        for i, value in enumerate(industry_data[loc]["Temperatur"]):
            if value >= T_collector_water_supply + deltaT_pinch:
                direct = True
        if direct == False:
            del industry_data[loc]



    # Determine operational profile: German manufacturing uses 1-2 or 3-shift schedules,
    # but PfA data is ambiguous (some sources < working hours (e.g. non-continous processes), others > working hours (e.g. baseload)).
    # Decision rule classifies shift type systematically.
    for loc in industry_data:
        sum_heat = 0
        sum_heat_hours = 0
        for i, value in enumerate(industry_data[loc]["Wärmemenge"]):
            sum_heat += value
            sum_heat_hours += industry_data[loc]["Verfügbarkeit"][i] * value
        weighted_hours = sum_heat_hours / sum_heat
        print(weighted_hours)


        for i, value in enumerate(industry_data[loc]["Wärmemenge"]):
            if 0 <= weighted_hours < 10:                      # 1-Schicht Modell
                industry_data[loc]["Schichtmodell"] = 1
                if industry_data[loc]["Verfügbarkeit"][i] > 8:
                    industry_data[loc]["Wärmemenge"][i] = value * (8/industry_data[loc]["Verfügbarkeit"][i])
            elif 10 <= weighted_hours < 18:                    # 2-Schicht Modell
                industry_data[loc]["Schichtmodell"] = 2
                if industry_data[loc]["Verfügbarkeit"][i] > 16:
                    industry_data[loc]["Wärmemenge"][i] = value * (16/industry_data[loc]["Verfügbarkeit"][i])
            else:                                               # 3-Schicht Modell
                industry_data[loc]["Schichtmodell"] = 3


    for loc in list(industry_data.keys()):
        if industry_data[loc]["Schichtmodell"] is not schichttyp:
            del industry_data[loc]
    for loc in industry_data:



        # Pinch analysis determines maximum integrable waste heat into heating network
        # No stream mixing assumed between waste heat sources
        industry_data[loc]["CP"] = {}



        industry_data[loc]["Wärmemenge"] = np.array(industry_data[loc]["Wärmemenge"])
        industry_data[loc]["Temperatur"] = np.array(industry_data[loc]["Temperatur"])
        sort_idx = np.argsort(industry_data[loc]["Temperatur"])[::-1]
        industry_data[loc]["Wärmemenge"] = industry_data[loc]["Wärmemenge"][sort_idx]
        industry_data[loc]["Temperatur"] = industry_data[loc]["Temperatur"][sort_idx]

        for i, value in enumerate(industry_data[loc]["Temperatur"]):
            # CP is the slope of hot streams in T-H diagram: CP = 1/(m * c_p)
            industry_data[loc]["CP"][i] = (industry_data[loc]["Temperatur"][i] - T_ref)/industry_data[loc]["Wärmemenge"][i]

        hot_curve = {
            "T_hot": [],
            "T_cold": [],
            "CP": [],
            "Q": []
        }
        cold_curve = {}

        def calculate_Q_max(i, j):
            Q = 0
            if i == len(industry_data[loc]["Temperatur"])-1:
                Q_stream = (industry_data[loc]["Temperatur"][i] - (T_collector_water_return + deltaT_pinch))/industry_data[loc]["CP"][j]
                Q += Q_stream

                hot_curve["T_hot"].append(industry_data[loc]["Temperatur"][i])
                hot_curve["T_cold"].append(T_collector_water_return + deltaT_pinch)
                hot_curve["CP"].append(industry_data[loc]["CP"][j])
                hot_curve["Q"].append(Q_stream)

                return Q
            if (industry_data[loc]["Temperatur"][i+1] < T_collector_water_return + deltaT_pinch):
                Q_stream = (industry_data[loc]["Temperatur"][i]- (T_collector_water_return + deltaT_pinch))/industry_data[loc]["CP"][j]
                Q += Q_stream

                hot_curve["T_hot"].append(industry_data[loc]["Temperatur"][i])
                hot_curve["T_cold"].append(T_collector_water_return + deltaT_pinch)
                hot_curve["CP"].append(industry_data[loc]["CP"][j])
                hot_curve["Q"].append(Q_stream)

                return Q
            else:
                Q_stream = (industry_data[loc]["Temperatur"][i]- industry_data[loc]["Temperatur"][i+1])/industry_data[loc]["CP"][j]
                Q+= Q_stream

                hot_curve["T_hot"].append(industry_data[loc]["Temperatur"][i])
                hot_curve["T_cold"].append(industry_data[loc]["Temperatur"][i+1])
                hot_curve["CP"].append(industry_data[loc]["CP"][j])
                hot_curve["Q"].append(Q_stream)

                if industry_data[loc]["CP"][j] <= industry_data[loc]["CP"][i+1]:
                    Q += calculate_Q_max(i+1, j)
                else:
                    Q += calculate_Q_max(i+1, i+1)

            return Q



        Q = calculate_Q_max(0, 0)



        cold_curve["T_hot"] = T_collector_water_supply
        cold_curve["T_cold"] = T_collector_water_return
        cold_curve["CP"] = (T_collector_water_supply - T_collector_water_return)/Q



        def calculate_Q_real(hot_curve, cold_curve, CP_water, T_cold):
            T_hot = cold_curve["T_hot"]

            n = len(hot_curve["T_hot"])
            Q = 0
            for i in range(n-1, -1, -1):
                Q += hot_curve["Q"][i]
                while hot_curve["T_hot"][i] < T_cold + CP_water * Q + deltaT_pinch:
                    hot_curve["Q"][i] = max(0, hot_curve["Q"][i] - 10)
                    Q -= 10
                    hot_curve["CP"][i] = (hot_curve["T_hot"][i] - hot_curve["T_cold"][i])/hot_curve["Q"][i]


            CP_water = (T_hot-T_cold)/np.sum(hot_curve["Q"])

            return CP_water

        CP_water_old = cold_curve["CP"]
        converged = False
        while converged == False:
            CP_water_new = calculate_Q_real(hot_curve, cold_curve, cold_curve["CP"], cold_curve["T_cold"])
            cold_curve["CP"] = CP_water_new
            diff = abs(CP_water_new - CP_water_old)
            if diff == 0:
                converged = True

            CP_water_old = CP_water_new

        industry_data[loc]["Q"] = np.sum(hot_curve["Q"])
        print(f"Hier ist der Name: {loc}")
        print(f"Hier ist die Abwärmemenge: {industry_data[loc]['Q']}")




        def plot_composite_curves(hot_curve, cold_curve, steps_per_segment=100):
            """
            Plottet Hot- und Cold-Composite-Curves mit Steigung, basierend auf CP.

            hot_curve : dict
                {'T_hot': [...], 'T_cold': [...], 'CP': [...]}
            cold_curve : dict
                {'T_hot': float, 'T_cold': float, 'CP': float}
            steps_per_segment : int
                Anzahl der Unterteilungen pro Segment für glatte Linien
            """

            # --- Hot Curve ---
            T_hot = hot_curve['T_hot']
            T_cold_hot = hot_curve['T_cold']
            CP_hot = hot_curve['CP']

            Q_hot = [0]
            T_hot_cont = [T_hot[0]]

            for th, tc, cp in zip(T_hot, T_cold_hot, CP_hot):
                deltaT = th - tc
                deltaQ = deltaT / cp  # Wärmemenge dieses Segments
                Q_segment = np.linspace(Q_hot[-1], Q_hot[-1] + deltaQ, steps_per_segment)
                T_segment = th - cp * (Q_segment - Q_hot[-1])
                Q_hot.extend(Q_segment[1:])
                T_hot_cont.extend(T_segment[1:])

            # --- Cold Curve ---
            T_c_start = cold_curve['T_hot']
            T_c_end = cold_curve['T_cold']
            CP_c = cold_curve['CP']

            Q_cold = [0]
            T_cold_cont = [T_c_start]

            for i in range(len(Q_hot) - 1):
                deltaQ = Q_hot[i + 1] - Q_hot[i]
                T_new = T_cold_cont[-1] - CP_c * deltaQ
                T_cold_cont.append(T_new)
                Q_cold.append(Q_hot[i + 1])

            # --- Plot ---
            plt.figure(figsize=(8, 6))
            plt.plot(Q_hot, T_hot_cont, color='red', linewidth=2)
            plt.plot(Q_hot, T_hot_cont, label='Composite Curve Abwärme', color='red', linewidth=2)
            plt.plot(Q_cold, T_cold_cont, label='Sammelwasser', color='blue', linewidth=2)
            plt.xlabel("ΔQ [kWh]")
            plt.ylabel("Temperatur [°C]")
            #plt.title("Hot and Cold Composite Curves")
            plt.grid(False)
            plt.legend()
            #plt.gca().set_xticklabels([])  # X-Achse ohne Zahlen
            #plt.gca().set_yticklabels([])  # Y-Achse ohne Zahlen
            plt.savefig("abbildung.pdf", format='pdf', dpi=300, bbox_inches='tight')
            plt.show()

        #plot_composite_curves(hot_curve, cold_curve)
        print(industry_data[loc]["Schichtmodell"])


    from sklearn.metrics import r2_score

    waste_heat_amount = []
    production_annual = []

    for loc in industry_data:
        waste_heat_amount.append(industry_data[loc]["Q"])
        production_annual.append(industry_data[loc]["Jahresproduktionsmenge"])

    # In NumPy-Arrays umwandeln
    Q = np.array(waste_heat_amount)
    P = np.array(production_annual)

    # Sortierindizes (absteigend nach Q)
    sort_idx = np.argsort(Q)[::-1]

    Q_sorted = Q[sort_idx]
    P_sorted = P[sort_idx]

    print("Hier ist Q:", Q_sorted)
    print("Hier ist P:", P_sorted)

    x = np.array(production_annual)
    y = np.array(waste_heat_amount)

    # Lineare Regression durch den Ursprung: y = m * x
    m = np.sum(x * y) / np.sum(x ** 2)  # OLS ohne Achsenabschnitt

    # Vorhersage
    y_pred = m * x

    # R² berechnen
    r2 = r2_score(y, y_pred)

    # Regressionslinie erzeugen
    x_line = np.linspace(min(x), max(x), 100)
    y_line = m * x_line  # kein + b

    # Plot
    plt.figure(figsize=(7, 5))
    plt.scatter(x, y, label="Datenpunkte")
    plt.plot(x_line, y_line, color="red", label="Regressionsgerade")

    plt.xlabel("Jahresproduktionsmenge")
    plt.ylabel("Abwärmemenge Q [kWh]")

    plt.text(
        0.05, 0.95,
        f"$R^2$ = {r2:.3f}",
        transform=plt.gca().transAxes,
        verticalalignment='top'
    )

    plt.grid(True, which="both")
    #plt.legend()
    plt.savefig("abbildung.pdf", format='pdf', dpi=300, bbox_inches='tight')
    #plt.show()

    # Hochrechnung
    waste_heat_annual = m * prod
    print(f"Hier ist m: {m} und hier ist prod: {prod}")

#    from collections import Counter
#    count = []
#    for i in industry_data:
#        count.append(industry_data[i]["Schichtmodell"])
#    max_count = Counter(count).most_common(1)[0][0]
#    print(max_count, count)

    holidays = self.calendar["holidays"]
    initial_day = self.initial_day

    waste_heat_profile = []

    for i in range(timesteps):

        hour = i % 24
        day = (initial_day + i // 24) % 7
        day_index = i // 24 + 1

        is_weekend = day >= 5
        is_holiday = day_index in holidays

        value = 0

        if schichttyp == 3:
            if not is_holiday:
                value = 1

        elif schichttyp == 2:
            if not is_weekend and not is_holiday and 6 <= hour < 22:
                value = 1

        elif schichttyp == 1:
            if not is_weekend and not is_holiday and 7 <= hour < 15:
                value = 1

        waste_heat_profile.append(value)

    operating_hours = sum(waste_heat_profile)
    waste_heat_hour = waste_heat_annual/operating_hours

    waste_heat_profile = np.array(waste_heat_profile, dtype=float)
    waste_heat_profile = np.where(waste_heat_profile == 1, waste_heat_hour, 0.0)

    temperature_profile = np.full(timesteps, T_collector_water_supply)

    return waste_heat_profile, temperature_profile