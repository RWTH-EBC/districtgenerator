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
import numpy as np
import openpyxl
import pandas as pd
import random as rd
import holidays as hol
import re
from teaser.project import Project
from .envelope_5R1C import Envelope as Envelope_5R1C
from .envelope_7R2C import Envelope as Envelope_7R2C
from .solar import Sun
from .users import Users
from .system import BES
from .system import CES
from .plots import DemandPlots
from .KPIs import KPIs
from .non_residential import NonResidential
import districtgenerator.functions.SIA as SIA
import districtgenerator.functions.clustering_medoid as cm
from districtgenerator.functions import opti_central
import districtgenerator.functions.heating_network_simple as heating_network_simple
from districtgenerator.functions.heating_network_opt import network_optimization
from districtgenerator.functions.design_network_with_node import run_pipeline_node
from districtgenerator.functions.design_network_with_road import run_pipeline_road
from districtgenerator.functions.heating_network_simple import calculate_soil_temperature
from districtgenerator.data_handling.config import GlobalConfig, load_global_config, LocationConfig, TimeConfig, DesignBuildingConfig, EcoConfig, PhysicsConfig, EHDOConfig, PyomoConfig, HeatGridConfig, CalendarConfig, CentralDeviceConfig, DecentralDeviceConfig, ReportConfig

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
                 heat_map_berlin = False
                 ):
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
        heat_map_berlin : bool, optional
            Whether the data is given in the heat map berlin format. The default is False.

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
        self.calendar = {}
        self.ecoData = {}
        self.all_sim_ecoData = {} # Later overwriten with the calculated economic data for the simulated years
        self.heat_grid_data = {}
        self.pipe_data = {}
        self.pyomo_config = {}
        self.report_config = {}
        # Additional attributes
        self.counter = {}
        self.building_dict = {} # Dictionary to store Residential Building IDs
        self.srcPath = srcPath
        self.filePath = filePath
        self.cluster_meta = None
        self.heat_map_berlin = heat_map_berlin
        self.pv_stc_potential = None

        if scenario_file_path is not None:
            self.scenario_file_path = scenario_file_path
        else:
            self.scenario_file_path = os.path.join(self.filePath, 'scenarios')

        if resultPath is not None:
            self.resultPath = resultPath
        else:
            self.resultPath = os.path.join(self.srcPath, 'results')

        self.KPIs = None
        self.load_all_data(
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
            pyomo_config=global_config.pyomo,
            report_config=global_config.report
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
                      pyomo_config: PyomoConfig,
                      report_config: ReportConfig):
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

        # --- 1. Load all Configs ---

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

        # load report configuration data
        for attr, value in report_config.__dict__.items():
            self.report_config[attr] = value

        # load heat grid data (used in heating network design and optimization)
        for attr, value in heat_grid_config.__dict__.items():
            self.heat_grid_data[attr] = value

        # --- 2. Load scenario data ---

        dtype_dict = {'id': str, 'building': str, 'year': int, 'retrofit': int, 'construction_type': int, 'night_setback': int,
                    'area': float, 'heater': str, 'cooling': int, 'EV': float, 'f_TES': float, 'f_BAT': float, 'f_PV1': float, 'f_PV2': float,
                    'f_STC': float, 'gamma_PV': float, 'ev_charging': str,}

        # %% load scenario file with building information
        if self.heat_map_berlin:
            # %% load heat map berlin formatted scenario file
            self.map_wkb_to_scenario_format(self.scenario_file_path + "/" + self.scenario_name + ".csv",
                                            self.scenario_file_path + "/" + self.scenario_name + "_dg.csv")
            self.scenario = (pd.read_csv(os.path.join(self.scenario_file_path, f"{self.scenario_name}_dg.csv"), delimiter=";",
                                         converters={"position": parse_position}, dtype=dtype_dict).set_index("id", drop=False))
            self.pv_stc_potential = pd.read_csv(
                self.scenario_file_path + "/" + self.scenario_name + "_pv_stc_potential.csv",
                delimiter=';',
                usecols=["uuid", "richtung", "neigung", "dachtyp", "modanetto"]
            )
        else:
            # %% load normal formatted scenario file
            self.scenario = (pd.read_csv(os.path.join(self.scenario_file_path, f"{self.scenario_name}.csv"), delimiter=";",
                                         converters={"position": parse_position}, dtype=dtype_dict).set_index("id", drop=False))

        json_path = os.path.join(self.scenario_file_path, f"{self.scenario_name}.json")

        if os.path.exists(json_path):
            with open(json_path, encoding="utf-8") as json_file:
                jsonData = json.load(json_file)
                self.site["district_parameters"] = jsonData["parameters"]

        # --- 3. Load pipe data based on the selected heat grid generation ---

        self.pipe_file_path = os.path.join(self.filePath, 'pipe')
        # select the pipe file based on the generation selection
        # KMR for 3rd generation; PMR for 4th generation; PE for 5th generation
        if self.heat_grid_data["generation"] == "3rd":
            csv_path = os.path.join(self.pipe_file_path, 'pipe_specifications_KMR.csv')
            self.pipe_data = pd.read_csv(csv_path, sep=";")

        elif self.heat_grid_data["generation"] == "4th":
            pmr_path = os.path.join(self.pipe_file_path, 'pipe_specifications_PMR.csv')
            pmr_data = pd.read_csv(pmr_path, sep=";")
            # add KMR pipes for DN > 150
            kmr_path = os.path.join(self.pipe_file_path, 'pipe_specifications_KMR.csv')
            kmr_data = pd.read_csv(kmr_path, sep=";")
            kmr_data = kmr_data[kmr_data["Nominal diameter (DN)"] > 150]
            self.pipe_data = pd.concat([pmr_data, kmr_data], ignore_index=True)

        elif self.heat_grid_data["generation"] == "5th":
            csv_path = os.path.join(self.pipe_file_path, 'pipe_specifications_PE.csv')
            self.pipe_data = pd.read_csv(csv_path, sep=";")
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

        # Load other site-dependent values based on DIN/TS 12831-1:2020-04 and VDI 2078-2015 (KLZ)
        filePath = os.path.join(self.filePath, 'site_data_with_KLZ.txt')
        site_data = pd.read_csv(filePath, delimiter='\t', dtype={'Zip': str})

        # Filter data for the specific zip code
        filtered_data = site_data[site_data['Zip'] == self.site["zip"]]

        # extract the needed values
        self.site["altitude"] = filtered_data.iloc[0]['Altitude']
        self.site["location"] = [filtered_data.iloc[0]['Latitude'],filtered_data.iloc[0]['Longitude']]
        self.site["T_ne"] = filtered_data.iloc[0]['T_ne'] # norm outside temperature for calculating the design heat load
        self.site["T_me"] = filtered_data.iloc[0]['T_me'] # mean annual temperature for calculating the design heat load

        # KLZ added to site_data based on nearest VDI station (generate_klz_site_data.py)
        klz = filtered_data.iloc[0]['KLZ']
        # Cooling limit temperatures based on Cooling Laod Zones (Kühllastzonen)
        # Calculated based on estimated amplitude based on VDI 2078 p. 117
        # To account for thermal mass and avoid outliers, T_me is used as average plus amplitude
        vdi_climate_data = {
            1: (23.3, 6.7),  # Zone 1 (Cool)
            2: (24.1, 7.4),  # Zone 2 (Moderate)
            3: (25, 8.0),  # Zone 3 (Warm)
            4: (26.1, 8.4),  # Zone 4 (Hot)
        }

        # Calculation: T_max = T_me + Amplitude
        if klz in vdi_climate_data:
            t_mean, amplitude = vdi_climate_data[klz]
            self.site["T_design_cooling"] = t_mean + amplitude
        else:
            # Fallback (Standard Zone 3)
            t_mean, amplitude = vdi_climate_data[3]
            self.site["T_design_cooling"] = t_mean + amplitude

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

    def is_mixed_building(self, building_type):
        """
        Check if a building type is a mixed-use building (contains "+").

        Parameters
        ----------
        building_type : str
            The building type string (e.g., "MFH+RETAIL").

        Returns
        -------
        bool
            True if the building type contains "+", False otherwise.
        """
        return "+" in building_type

    def combine_mixed_building_demands(self, saveUserProfiles):
        """
        Combine demand profiles from split mixed-use buildings back into a single building.
        This should be called after generateDemands() but before designDecentralDevices().

        Creates a new combined building with summed demand profiles.
        Both main and secondary buildings are deleted, replaced by the combined building.
        An Excel file is created for each combined building showing all demand profiles.

        Returns
        -------
        None
        """
        # Find all mixed building parts grouped by parent ID
        mixed_buildings = {}
        for idx, building in enumerate(self.district):
            if building["buildingFeatures"].get("is_mixed_part", False):
                parent_id = building["buildingFeatures"]["mixed_parent_id"]
                if parent_id not in mixed_buildings:
                    mixed_buildings[parent_id] = []
                mixed_buildings[parent_id].append((idx, building))

        if mixed_buildings:
            print(f"Found {len(mixed_buildings)} mixed-use building groups to recombine.")

        # Combine each group of mixed buildings
        buildings_to_remove = []
        buildings_to_add = []

        for parent_id, buildings in mixed_buildings.items():
            if len(buildings) < 2:
                continue

            # Find main and secondary buildings
            main_idx, main_building = None, None
            secondary_idx, secondary_building = None, None

            for idx, building in buildings:
                if building["buildingFeatures"]["mixed_role"] == "main":
                    main_idx, main_building = idx, building
                elif building["buildingFeatures"]["mixed_role"] == "secondary":
                    secondary_idx, secondary_building = idx, building

            if main_building is None or secondary_building is None:
                continue

            # Create a NEW combined building based on the original building features
            combined_building = {}

            # Copy building features from main building (which has original_bldg_id)
            combined_building["buildingFeatures"] = main_building["buildingFeatures"].copy()

            # Update building type to show it's mixed
            main_type = main_building["buildingFeatures"]["building"]
            secondary_type = secondary_building["buildingFeatures"]["building"]
            combined_building["buildingFeatures"]["building"] = f"{main_type}+{secondary_type}"

            # Sum up total area from both parts
            combined_building["buildingFeatures"]["area"] = (
                main_building["buildingFeatures"]["area"] +
                secondary_building["buildingFeatures"]["area"])

            # Mark as combined and remove mixed-part flags
            combined_building["buildingFeatures"]["is_mixed_combined"] = True
            if "is_mixed_part" in combined_building["buildingFeatures"]:
                del combined_building["buildingFeatures"]["is_mixed_part"]
            if "mixed_role" in combined_building["buildingFeatures"]:
                del combined_building["buildingFeatures"]["mixed_role"]
            if "mixed_parent_id" in combined_building["buildingFeatures"]:
                del combined_building["buildingFeatures"]["mixed_parent_id"]

            # Create unique name for combined building
            combined_building["unique_name"] = f"{self.scenario_name}_{parent_id}_{main_type}+{secondary_type}"

            # Copy envelope and user objects from main building
            combined_building["envelope"] = copy.deepcopy(main_building["envelope"])

            # Create new user object with combined demands
            combined_building["user"] = copy.deepcopy(main_building["user"])

            # Combine all demand profiles by summing (element-wise with numpy arrays)
            combined_building["user"].elec = np.array(np.array(main_building["user"].elec) + np.array(secondary_building["user"].elec))
            combined_building["user"].dhw = np.array(np.array(main_building["user"].dhw) + np.array(secondary_building["user"].dhw))
            combined_building["user"].heat = np.array(np.array(main_building["user"].heat) + np.array(secondary_building["user"].heat))
            combined_building["user"].cooling = np.array(np.array(main_building["user"].cooling) + np.array(secondary_building["user"].cooling))
            combined_building["user"].gains = np.array(np.array(main_building["user"].gains) + np.array(secondary_building["user"].gains))
            combined_building["user"].occ = np.array(np.array(main_building["user"].occ) + np.array(secondary_building["user"].occ))

            combined_building["user"].EV_carcharging_ondemand = np.array(np.array(main_building["user"].EV_carcharging_ondemand) + np.array(secondary_building["user"].EV_carcharging_ondemand))
            combined_building["user"].EV_carprofile = np.array(np.array(main_building["user"].EV_carprofile) + np.array(secondary_building["user"].EV_carprofile))
            combined_building["user"].ice_carprofile = np.array(np.array(main_building["user"].ice_carprofile) + np.array(secondary_building["user"].ice_carprofile))

            # Combine EV capacities
            cap_main = main_building["user"].ev_capacity if main_building["user"].ev_capacity is not None else []
            cap_sec = secondary_building["user"].ev_capacity if secondary_building["user"].ev_capacity is not None else []

            # Ensure values are lists to prevent addition errors
            if isinstance(cap_main, (int, float)): cap_main = [cap_main]
            if isinstance(cap_sec, (int, float)): cap_sec = [cap_sec]

            combined_building["user"].ev_capacity = list(cap_main) + list(cap_sec)

            # Combine individual car profiles and reassign unique IDs
            cars_main = main_building["user"].individual_car_profiles.copy() if hasattr(main_building["user"], "individual_car_profiles") and main_building["user"].individual_car_profiles else []
            cars_sec = secondary_building["user"].individual_car_profiles.copy() if hasattr(secondary_building["user"], "individual_car_profiles") and secondary_building["user"].individual_car_profiles else []

            combined_building["user"].individual_car_profiles = []
            new_car_id = 0

            for car in cars_main:
                car_copy = car.copy()
                car_copy["car_id"] = new_car_id
                combined_building["user"].individual_car_profiles.append(car_copy)
                new_car_id += 1

            for car in cars_sec:
                car_copy = car.copy()
                car_copy["car_id"] = new_car_id
                combined_building["user"].individual_car_profiles.append(car_copy)
                new_car_id += 1

            # Sum up user counts differentiate if residential or non-residential
            if main_type in {"SFH", "TH", "MFH", "AB"}:
                combined_building["user"].nb_res_flats = main_building["user"].nb_units
                combined_building["user"].nb_res_occ = main_building["user"].nb_occ.copy()
                combined_building["user"].nb_nonres_flats = secondary_building["user"].nb_units
                combined_building["user"].nb_nonres_occ = secondary_building["user"].nb_occ
            elif secondary_type in {"SFH", "TH", "MFH", "AB"}:
                combined_building["user"].nb_res_flats = secondary_building["user"].nb_units
                combined_building["user"].nb_res_occ = secondary_building["user"].nb_occ.copy()
                combined_building["user"].nb_nonres_flats = main_building["user"].nb_units
                combined_building["user"].nb_nonres_occ = main_building["user"].nb_occ
            else: raise Exception(f"At least one part of the mixed building has to be residential. Please check building types for {combined_building['unique_name']}.")

            combined_building["user"].nb_units = main_building["user"].nb_units + secondary_building["user"].nb_units
            combined_building["user"].nb_occ = np.concatenate([main_building["user"].nb_occ, secondary_building["user"].nb_occ])

            # sum up the design loads for heating and cooling
            combined_building["envelope"].heatload = main_building["envelope"].heatload + secondary_building["envelope"].heatload
            combined_building["envelope"].bivalent = main_building["envelope"].bivalent + secondary_building["envelope"].bivalent
            combined_building["envelope"].heatlimit = main_building["envelope"].heatlimit + secondary_building["envelope"].heatlimit
            combined_building["envelope"].coolingload = main_building["envelope"].coolingload + secondary_building["envelope"].coolingload

            # Adjust areas from envelope:
            combined_building["envelope"].A = {}

            main_A = main_building["envelope"].A
            sec_A = secondary_building["envelope"].A

            # 1. Sum total area:
            combined_building["envelope"].A['f'] = main_A['f']+ sec_A['f']

            # 2. Sum up all opaque areas (walls, roof, floor, etc.)
            combined_building["envelope"].A['opaque'] = {}
            all_keys = set(main_A.get('opaque', {}).keys()).union(set(sec_A.get('opaque', {}).keys()))
            for key in all_keys:
                combined_building["envelope"].A['opaque'][key] = main_A['opaque'].get(key, 0) + sec_A['opaque'].get(key, 0)

            # 3. Sum up all window areas
            combined_building["envelope"].A['window'] = {}
            all_keys = set(main_A.get('window', {}).keys()).union(set(sec_A.get('window', {}).keys()))
            for key in all_keys:
                combined_building["envelope"].A['window'][key] = main_A['window'].get(key, 0) + sec_A['window'].get(key, 0)

            # Sum up DHW power and generation
            combined_building["dhwpower"] = main_building["dhwpower"] + secondary_building["dhwpower"]

            print(f"Combined mixed building {parent_id}: "
                  f"{main_type} + {secondary_type} → NEW combined building")

            # Save combined profiles to Excel file
            if saveUserProfiles:
                self.saveProfiles(name=combined_building["unique_name"],
                                  elec=combined_building["user"].elec,
                                  dhw=combined_building["user"].dhw,
                                  occ=combined_building["user"].occ,
                                  gains=combined_building["user"].gains,
                                  EV_carcharging_ondemand=combined_building["user"].EV_carcharging_ondemand,
                                  EV_carprofile=combined_building["user"].EV_carprofile,
                                  nb_units=combined_building["user"].nb_units,
                                  nb_occ=combined_building["user"].nb_occ,
                                  ev_capacity=combined_building["user"].ev_capacity or [0],
                                  ice_carprofile=combined_building["user"].ice_carprofile,
                                  heatload=combined_building["envelope"].heatload,
                                  bivalent=combined_building["envelope"].bivalent,
                                  heatlimit=combined_building["envelope"].heatlimit,
                                  coolingload=combined_building["envelope"].coolingload,
                                  dhwpower=combined_building["dhwpower"],
                                  envelope_areas=combined_building["envelope"].A,
                                  path=os.path.join(self.resultPath, 'demands'),
                                  individual_car_profiles=combined_building["user"].individual_car_profiles)

            # Mark both buildings for removal
            buildings_to_remove.append(main_idx)
            buildings_to_remove.append(secondary_idx)

            # Add new combined building to the list
            buildings_to_add.append(combined_building)

        # Remove both main and secondary buildings (in reverse order to maintain indices)
        for idx in sorted(buildings_to_remove, reverse=True):
            del self.district[idx]

        # Add all new combined buildings to the district
        for combined_building in buildings_to_add:
            self.district.append(combined_building)

        # Rebuild building_dict completely for ALL buildings
        # After removing/adding buildings, indices have shifted
        self.building_dict = {}
        for idx, building in enumerate(self.district):
            if "original_bldg_id" in building["buildingFeatures"]:
                original_id = building["buildingFeatures"]["original_bldg_id"]
                self.building_dict[original_id] = idx

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
            bldg_id = str(bldg_id)
            building = {}

            # Store features of the observed building
            building["buildingFeatures"] = row.copy()
            building["buildingFeatures"]["original_bldg_id"] = bldg_id # Used for tracking the building throughout the mixed building splitting and combining process

            # Unique name = "<scenario>_<id>_<building type>"
            name = f"{self.scenario_name}_{bldg_id}_{row['building']}"
            if name in name_pool:
                print(f"Duplicate name: {name}, skipping")
                continue
            name_pool.append(name)

            building["unique_name"] = name
            self.district.append(building)
            self.building_dict[bldg_id] = len(self.district) - 1

            # Count for time estimate #* Does not account for mixed-use and non-residential buildings
            if row["building"] in ("SFH", "TH"):
                num_sfh += 1
            elif row["building"] in ("MFH", "AB"):
                num_mfh += 1

        # Rough time estimate
        duration += datetime.timedelta(seconds=3 * num_sfh + 12 * num_mfh)
        print(f"This calculation will take about {duration}.")

        self.split_mixed_buildings()

    def split_mixed_buildings(self):
        """
        Splits mixed-use buildings into main and secondary building parts.
        """
        bldgs = self.design_building_data

        buildings_to_process = []
        buildings_to_skip = []

        for idx, building in enumerate(self.district):
            if self.is_mixed_building(building["buildingFeatures"]["building"]):
                # This building needs to be split - we'll handle it separately
                buildings_to_skip.append(idx)

                # Split the building type
                building_types = building["buildingFeatures"]["building"].split("+")
                main_type = building_types[0]
                secondary_type = building_types[1]

                total_area = building["buildingFeatures"]["area"]

                # Calculate number of floors for the main building type
                main_building_long = bldgs["buildings_long"][bldgs["buildings_short"].index(main_type)]

                # Calculate floors based on main building type
                if main_building_long == "single_family_house":
                    one_floor_area = rd.randint(*self._get_one_floor_area_range_res(main_building_long))
                    total_floors = max(2, round(total_area / one_floor_area))
                elif main_building_long == "terraced_house":
                    one_floor_area = rd.randint(*self._get_one_floor_area_range_res(main_building_long))
                    total_floors = max(2, round(total_area / one_floor_area))
                elif main_building_long == "multi_family_house":
                    one_floor_area = rd.randint(*self._get_one_floor_area_range_res(main_building_long))
                    total_floors = max(2, round(total_area / one_floor_area))
                    if total_floors > 8: total_floors = 8
                elif main_building_long == "apartment_block":
                    one_floor_area = rd.randint(*self._get_one_floor_area_range_res(main_building_long))
                    total_floors = max(3, round(total_area / one_floor_area))
                else:
                    # Generate a NonResidential building and get number of floors
                    retrofit_level = bldgs["retrofit_long_non_residential"][bldgs["retrofit_short_non_residential"].index(building["buildingFeatures"]["retrofit"])]
                    construction_type = bldgs["construction_type_long"][bldgs["construction_type_short"].index(building["buildingFeatures"]["construction_type"])]

                    temp_building = NonResidential(
                        usage=main_type,
                        name="NonResidentialBuilding",
                        year_of_construction=building["buildingFeatures"]["year"],
                        net_leased_area=building["buildingFeatures"]["area"],          # Total net leased area of the building, or of the building part if it is a mixed-use building.
                        total_building_area=(                                          # Total net leased area of building
                            building["buildingFeatures"]["area"] if self.total_building_area is None
                            else self.total_building_area),
                        construction_type=construction_type,
                        retrofit_level=retrofit_level,
                        number_of_floors=None
                        )
                    total_floors = max(2,int(temp_building.get_number_of_floors())) # If building is split it needs at least two floors
                    del temp_building

                # Recalculate one_floor_area based on total area and total floors to ensure consistency
                one_floor_area = total_area / total_floors

                # Allocate 1 floor to secondary, rest to main (main must have at least 1)
                secondary_floors = 1
                main_floors = total_floors - secondary_floors

                # Calculate areas based on floors
                secondary_area = one_floor_area * secondary_floors
                main_area = total_area - secondary_area

                # Create main building
                main_building = {}
                main_row = building["buildingFeatures"].copy()
                main_row["building"] = main_type
                main_row["area"] = main_area
                main_row["is_mixed_part"] = True
                main_row["mixed_parent_id"] = building["buildingFeatures"]["original_bldg_id"]
                main_row["mixed_role"] = "main"
                main_row["fixed_floors"] = main_floors

                main_building["buildingFeatures"] = main_row
                main_building["unique_name"] = f"{self.scenario_name}_{idx}_{main_type}_Main"
                buildings_to_process.append(main_building)

                # Create secondary building
                secondary_building = {}
                secondary_row = building["buildingFeatures"].copy()
                secondary_row["building"] = secondary_type
                secondary_row["area"] = secondary_area
                secondary_row["is_mixed_part"] = True
                secondary_row["mixed_parent_id"] = building["buildingFeatures"]["original_bldg_id"]
                secondary_row["mixed_role"] = "secondary"
                secondary_row["fixed_floors"] = secondary_floors

                secondary_building["buildingFeatures"] = secondary_row
                secondary_building["unique_name"] = f"{self.scenario_name}_{idx}_{secondary_type}_Secondary"
                buildings_to_process.append(secondary_building)

                print(f"Split mixed building {building['buildingFeatures']['original_bldg_id']}: "
                      f"{building['buildingFeatures']['building']} (Total: {total_area:.0f} m², {total_floors} floors) -> "
                      f"{main_type} ({main_area:.0f} m², {main_floors} floors) + "
                      f"{secondary_type} ({secondary_area:.0f} m², {secondary_floors} floor)")

        # Replace district with processed buildings
        new_district = []
        for idx, building in enumerate(self.district):
            if idx not in buildings_to_skip:
                new_district.append(building)
        new_district.extend(buildings_to_process)
        self.district = new_district

        # Rebuild building_dict
        self.building_dict = {}
        for idx, building in enumerate(self.district):
            if "original_bldg_id" in building["buildingFeatures"]:
                original_id = building["buildingFeatures"]["original_bldg_id"]
                # Only map the main building for mixed types, or all regular buildings
                if building["buildingFeatures"].get("mixed_role") == "main" or not building["buildingFeatures"].get("is_mixed_part", False):
                    self.building_dict[original_id] = idx

    # Helper function to get floor area range for residential building types based on TABULA typology
    def _get_one_floor_area_range_res(self, building_type):
        """
        Floor area ranges for different residential building types based on the TABULA German Building Typology

        Returns
        -------
        tuple
            A tuple containing the minimum and maximum floor area for one floor of the given building type.
        """
        if building_type == "single_family_house":
            return (62, 115) # Source: TABULA German Building Typology
        elif building_type == "terraced_house":
            return (50, 73) # Source: TABULA German Building Typology
        elif building_type == "multi_family_house":
            return (102, 971) # Source: TABULA German Building Typology
        elif building_type == "apartment_block":
            return (350, 540) # Source: TABULA German Building Typology
        else: raise ValueError(f"Unknown building type for residential floor area estimation according to TABULA: {building_type}")

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
                if retrofit_level == "tabula_retrofit":
                    construction_data = 'tabula_de_retrofit'
                elif retrofit_level == "tabula_adv_retrofit":
                    construction_data = 'tabula_de_adv_retrofit'
                else:
                    # tabula standard
                    construction_data = 'tabula_de_standard'

                # Determining the number of floors in a building based on its type.
                # The method estimates the number of floors by:
                # - Assigning a range of possible floor areas per level based on building type.
                # - Randomly selecting a value within the assigned range using the TABULA German Building Typology.
                # - Calculating the total number of floors by dividing the building’s total floor area
                #   by the selected single-floor area.

                # Check if floors are already fixed those are used (from mixed building splitting)
                if "fixed_floors" in building["buildingFeatures"]:
                    number_of_floors = building["buildingFeatures"]["fixed_floors"]
                elif building_type == "single_family_house":
                    one_floor_area = rd.randint(*self._get_one_floor_area_range_res(building_type))  
                    # Calculate the number of floors, rounding to the nearest integer and ensuring at least 1
                    number_of_floors = max(1, round(building["buildingFeatures"]["area"] / one_floor_area))

                elif building_type == "terraced_house":
                    one_floor_area = rd.randint(*self._get_one_floor_area_range_res(building_type))  # Source: TABULA German Building Typology
                    # Calculate the number of floors, rounding to the nearest integer and ensuring at least 1
                    number_of_floors = max(1, round(building["buildingFeatures"]["area"] / one_floor_area))

                elif building_type == "multi_family_house":
                    # Generate a valid one-floor area and number of floors in one step
                    one_floor_area = rd.randint(*self._get_one_floor_area_range_res(building_type)) # Source: TABULA German Building Typology
                    # Calculate the number of floors, rounding to the nearest integer and ensuring at least 2
                    number_of_floors = max(2, round(building["buildingFeatures"]["area"] / one_floor_area))
                    # Cap the number of floors to a maximum of 8
                    if number_of_floors > 8:
                        number_of_floors = 8

                elif building_type == "apartment_block":
                    one_floor_area = rd.randint(*self._get_one_floor_area_range_res(building_type))  # Source: TABULA German Building Typology
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

                # add buildings to TEASER project
                prj.add_residential(name="ResidentialBuildingTabula",
                                    geometry_data="tabula_de_" + building_type,
                                    construction_data=construction_data,
                                    year_of_construction=building["buildingFeatures"]["year"],
                                    number_of_floors=number_of_floors,
                                    height_of_floors=height_of_floors,
                                    net_leased_area=building["buildingFeatures"]["area"])
                
                if building["buildingFeatures"].get("is_mixed_part", False):
                    if isinstance(prj, Project):
                        mixed_res_part = prj.buildings[-1]
                        for r in mixed_res_part.thermal_zones[0].ground_floors:
                            # Ensure no ground area for the residential part.
                            r.area = 1e-9 # Set to a very small value to avoid division by zero errors in Envelope calculations



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
                                                construction_data=construction_data,
                                                physics=self.physics,
                                                design_building_data=self.design_building_data,
                                                file_path=self.filePath,
                                                SIA2024=self.SIA2024)

            else:

                retrofit_level = bldgs["retrofit_long_non_residential"][bldgs["retrofit_short_non_residential"].index(building["buildingFeatures"]["retrofit"])]
                construction_type = bldgs["construction_type_long"][bldgs["construction_type_short"].index(building["buildingFeatures"]["construction_type"])]

                if "fixed_floors" in building["buildingFeatures"]:
                    number_of_floors = building["buildingFeatures"]["fixed_floors"]
                else:
                    number_of_floors = None # No information about the number of floors is given

                nrb_prj = NonResidential(
                        usage=building["buildingFeatures"]["building"],
                        name="NonResidentialBuilding",
                        year_of_construction=building["buildingFeatures"]["year"],
                        net_leased_area=building["buildingFeatures"]["area"],          # Total net leased area of the building, or of the building part if it is a mixed-use building.
                        total_building_area=(                                          # Total net leased area of building
                            building["buildingFeatures"]["area"] if self.total_building_area is None
                            else self.total_building_area),
                        construction_type=construction_type,
                        retrofit_level=retrofit_level,
                        number_of_floors=number_of_floors,
                        is_mixed_part=building["buildingFeatures"].get("is_mixed_part", False)
                        )

                # %% create envelope object
                # containing all physical data of the envelope
                # NOTE: For non-residential buildings, the available input data
                # only supports the 5R1C thermal model. A 7R2C mode is not
                # feasible here due to missing parameters for VDI 6007 modeling.

                Envelope = Envelope_5R1C
                building["thermal_model"] = "5R1C"

                building["envelope"] = Envelope(prj=nrb_prj,
                                                building_params=building["buildingFeatures"],
                                                construction_data=construction_type,
                                                physics=self.physics,
                                                design_building_data=self.design_building_data,
                                                file_path=self.filePath,
                                                SIA2024=self.SIA2024)

            # %% create user object
            # containing number occupants, electricity demand,...
            building["user"] = Users(building=building["buildingFeatures"]["building"],
                                     area=building["buildingFeatures"]["area"],
                                     year_of_construction=building["buildingFeatures"]["year"],
                                     retrofit=building["buildingFeatures"]["retrofit"],
                                     SIA2024=self.SIA2024)

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
            # %% calculate design cooling load
            building["envelope"].coolingload = building["envelope"].calcCoolingLoad(site=self.site, nb_occ=np.sum(building["user"].nb_occ))

            index = bldgs["buildings_short"].index(building["buildingFeatures"]["building"])
            building["buildingFeatures"]["mean_drawoff_dhw"] = bldgs["mean_drawoff_vol_per_day"][index]

    def generateDemands(self, calcUserProfiles=True, saveUserProfiles=True, max_threads=8, gen_cars=True):
        use_multiprocessing = True #todo: False while debugging

        # Thread count is limited by the maximum available CPU cores. Using more threads than cores usually provides no additional benefit but requires more temporary storage.
        max_threads = min(max_threads, multiprocessing.cpu_count())

        args_list = [(self, building, calcUserProfiles, saveUserProfiles, gen_cars) for building in self.district]

        self.buildings_total = len(self.district)
        self.buildings_completed = 0

        results = [] # Store results from worker processes

        self.save_progress()

        if use_multiprocessing:
            with multiprocessing.Pool(processes=max_threads) as pool:
                for result in pool.imap_unordered(generate_demands_worker_wrapper, args_list):
                    self.buildings_completed += 1
                    results.append(result)
                    self.save_progress()
                    print(
                        f"building {self.buildings_completed}/{self.buildings_total} calculated "
                        f"({(self.buildings_completed / self.buildings_total) * 100:.1f}%): "
                        f"{result.get('unique_name', '')}"
                    )
        else:
            for args in args_list:
                result = generate_demands_worker_wrapper(args)
                self.buildings_completed += 1
                results.append(result)

                self.save_progress()

                print(f"building {self.buildings_completed}/{self.buildings_total} calculated " +
                      f"({(self.buildings_completed / self.buildings_total) * 100:.1f}%): {result.get('unique_name', '')}")

        for result in results:
            building = next(b for b in self.district if b["unique_name"] == result["unique_name"])
            
            if not calcUserProfiles:
                if "user" not in building:
                    building["user"] = DummyUser()
                if "envelope" not in building:
                    building["envelope"] = DummyEnvelope()
                    building["envelope"].construction_year = building["buildingFeatures"]["year"]
                    building["envelope"].retrofit = building["buildingFeatures"]["retrofit"]

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
            building["dhwpower"] = result["dhwpower"]
            building_features = building["buildingFeatures"].copy()
            building_features["night_setback"] = result["night_setback"]
            building["buildingFeatures"] = building_features

        self.save_progress()


        print("Finished generating demands with multiprocessing!")

        # Combine demand profiles for mixed-use buildings
        self.combine_mixed_building_demands(saveUserProfiles)

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

            building["user"].calcHeatingProfile(site=self.site,
                                                envelope=building["envelope"],
                                                thermal_model=building["thermal_model"],
                                                night_setback=night_setback,
                                                is_cooled=is_cooled,
                                                calendar=self.calendar,
                                                time_resolution=self.time["timeResolution"],
                                                initial_day=self.initial_day)

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
                                  coolingload=building["envelope"].coolingload,
                                  dhwpower=building["dhwpower"],
                                  envelope_areas=building["envelope"].A,
                                  path=os.path.join(self.resultPath, 'demands'),
                                  individual_car_profiles=building["user"].individual_car_profiles)
                
                self.saveHeatingProfile(heat=building["user"].heat,
                                        cooling=building["user"].cooling,
                                        name=building["unique_name"],
                                        path=os.path.join(self.resultPath, 'demands'))

        else:
            # Generate dummy user and envelope objects instead of Teaser and User objects as demand calculation is skipped.
            if "user" not in building:
                building["user"] = DummyUser()
            
            if "envelope" not in building:
                building["envelope"] = DummyEnvelope()
                building["envelope"].construction_year = building["buildingFeatures"]["year"]
                building["envelope"].retrofit = building["buildingFeatures"]["retrofit"]
                    

            (building["user"].elec, building["user"].dhw,
             building["user"].occ, building["user"].gains,
             building["user"].EV_carcharging_ondemand,
             building["user"].EV_carprofile,
             building["user"].ice_carprofile,
             building["user"].nb_units,
             building["user"].nb_main_rooms,
             building["user"].nb_occ, building["user"].ev_capacity, building["envelope"].heatload,
             building["envelope"].bivalent,
             building["envelope"].heatlimit, building["envelope"].coolingload, building["dhwpower"], building["envelope"].A,
             building["user"].individual_car_profiles) = self.loadProfiles(building["unique_name"],
                                                                 os.path.join(self.resultPath, 'demands'), gen_cars= gen_cars)
            print("Load demands of building " + building["unique_name"])

            heat, cooling = self.loadHeatingProfiles(name=building["unique_name"],
                                                     path=os.path.join(self.resultPath, 'demands'))
            building["user"].heat = heat
            building["user"].cooling = cooling

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

        if calcUserProfiles: # Only generate the building envelopes and user objects if we need to calculate new profiles.
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
            else:
                print("Generating and optimizing heating network...")
                self.generateNetwork(topology_option)
                self.prepareClusteringInputs()
                self.optimization_heatingnetwork()

            # initialize the seasonal storage for the heat grid
            seasonal_storage_kWh_a = self.heat_grid_data["seasonal_storage_kWh_a"]
            # Convert kWh/a to kW (assuming constant supply throughout the year)
            seasonal_storage_kW_max = seasonal_storage_kWh_a / (365 * 24) # Currently assumes a constant supply throughout the year.
            seasonal_storage_kW = np.ones(len(self.heat_grid_data["total_losses_heating_network"])) * seasonal_storage_kW_max
            self.heat_grid_data["seasonal_storage_kW"] = seasonal_storage_kW

            # Initialize waste heat availability for the heat grid
            if self.heat_grid_data["nominal_waste_heat_capacity_kW"] is None: self.heat_grid_data["nominal_waste_heat_capacity_kW"] = 0
            nominal_waste_heat_capacity_kW = self.heat_grid_data["nominal_waste_heat_capacity_kW"]
            self.heat_grid_data["waste_heat_kW"] = np.ones(len(self.heat_grid_data["total_losses_heating_network"])) * nominal_waste_heat_capacity_kW

            self.designCentralDevices(saveGenerationProfiles=True)
            self.finalizeClusterProfiles()
            
        else:
            print("No central heat grid detected — skipping heating network design.")
            self.centralDevices = {}
            self.prepareClusteringInputs()

    def saveProfiles(self, name, elec, dhw, occ, gains, EV_carcharging_ondemand,
                     EV_carprofile, ev_capacity, ice_carprofile, nb_units,
                     nb_occ, heatload, bivalent, heatlimit, coolingload, dhwpower,
                     envelope_areas, path, individual_car_profiles=None):
        """
        Save profiles to csv.

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
        car : list
            Hourly electricity demand of EV in W.
        nb_units : int
            Number of units in the building.
        nb_occ : list
            Number of occupants in the building.
        heatload : float
            Design heat load in W.
        bivalent : float
            Bivalent heat load in W.
        heatlimit : float
            Heat limit heat load in W.
        coolingload : float
            Design cooling load in W.
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
                "Heat Limit Heat Load (W)": [heatlimit],
                "Design Cooling Load (W)": [coolingload],
                "DHW Power (W)": [dhwpower],
                "Envelope Areas": [json.dumps(envelope_areas)]
            }), ["Number of Flats or main Rooms", "Number of Occupants", "EV_capacities",
                 "Design Heat Load (W)", "Bivalent Heat Load (W)",
                 "Heat Limit Heat Load (W)", "Design Cooling Load (W)", "DHW Power (W)", "Envelope Areas"])
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
        heat: list
            Hourly heating demand in W.
        cooling: list
            Hourly cooling demand in W.
        name : string
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
        name : string
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
                if len(row)>1:
                    data.append(list(row))
                else:
                    data.append(row[0])
            return np.array(data)

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
        nb_units = int(other_data[0])
        nb_main_rooms = nb_units
        nb_occ = np.fromstring(other_data[1], dtype=int, sep=',')
        EV_capacity = np.fromstring(other_data[2], dtype=float, sep=',')
        heatload = float(other_data[3])
        bivalent = float(other_data[4])
        heatlimit = float(other_data[5])
        coolingload = float(other_data[6])
        dhwpower = float(other_data[7])
        envelope_areas_json = other_data[8]
        envelope_areas = json.loads(envelope_areas_json)

        workbook.close()

        return elec, dhw, occ, gains, EV_carcharging_ondemand, EV_carprofile, ice_carprofile, nb_units, nb_main_rooms, nb_occ, EV_capacity, heatload, bivalent, heatlimit, coolingload, dhwpower, envelope_areas, individual_car_profiles

    def loadHeatingProfiles(self, name, path):
        """
        Load profiles from csv.

        Parameters
        ----------
        name : string
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

        dt_s = self.time["timeResolution"]

        for building in self.district:

            if self.heat_map_berlin:
                # Read PV potentials for the current building from the DataFrame
                pv_data = self.pv_stc_potential[self.pv_stc_potential["uuid"] == building["buildingFeatures"]["alkis_id"]]
                # Initialize sums for PV and STC
                time_steps = int(self.time["dataLength"] / self.time["timeResolution"])
                total_pv_generation = np.zeros(time_steps)
                total_stc_generation = np.zeros(time_steps)

                # Loop over each PV sub-area for this building
                for idx, row in pv_data.iterrows():
                    area = row["modanetto"]  # Area of the sub-surface
                    roof_type = row["dachtyp"]  # Roof type

                    # Check if roof is flat and adjust tilt and azimuth accordingly
                    if roof_type == "flach":
                        tilt = 30  # Flat roofs: 30 degrees tilt
                        azimuth = 0  # Flat roofs: south orientation (0°)
                    else:
                        azimuth = row["richtung"]  # Orientation (gamma)
                        tilt = row["neigung"]  # Tilt angle (beta)

                    # Calculate PV and STC profiles for this sub-area
                    pv_profile, stc_profile = sun.calcPVAndSTCProfile(
                        time=self.time,
                        site=self.site,
                        devices=self.decentral_device_data,
                        area_roof=area,
                        beta=[tilt],
                        gamma=[azimuth],
                        usageFactorPV1=1,
                        usageFactorPV2=0,
                        usageFactorSTC=building["buildingFeatures"]["f_STC"]
                    )

                    # Sum up the profiles
                    total_pv_generation += pv_profile
                    total_stc_generation += stc_profile

                # Store the summed values
                building["generationPV"] = total_pv_generation
                building["generationSTC"] = total_stc_generation


            else:
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

        # Pre-cluster for the optimization of the decentral heating system
        def is_opt_like(v):
            s = str(v or "").strip().lower()
            return (
                    s in ("opt", "opt_geg", "opt_custom")
                    or ("," in s)
                    or s.startswith(("opt:", "opt[", "opt(", "opt{"))
                    or (s.startswith("[") and s.endswith("]"))
                    or (s.startswith("(") and s.endswith(")"))
                    or (s.startswith("{") and s.endswith("}"))
            )
        any_opt = any(is_opt_like(b["buildingFeatures"].get("heater", "")) for b in self.district)

        if any_opt:
            self.clusterProfiles(centralEnergySupply=False)

            self.cluster_meta = {
                "clusterWeights": self.clusterWeights,
                "clusters": self.clusters,
                "len_cluster": int(self.time["clusterLength"] / self.time["timeResolution"]),
                "clusterNumber": self.time["clusterNumber"],
            }

        for building in self.district:
            building["cluster_meta"] = self.cluster_meta

            # create building energy system object (may choose heater if "opt")
            building["bes_obj"] = BES(
                physics=self.physics,
                decentral_device_data=self.decentral_device_data,
                design_building_data=self.design_building_data,
                file_path=self.filePath,
                eco_data=self.ecoData,
                pyomo_config=self.pyomo_config
            )

            # get capacities of all possible devices
            building["capacities"] = building["bes_obj"].designECS(building, self.site, dt_s=dt_s)

            # Optionally save PV/STC generation profiles
            if saveGenerationProfiles == True:
                try:
                    np.savetxt(os.path.join(self.resultPath, 'generation') + '/decentralPV_' + building["unique_name"] + '.csv',
                            building["generationPV"],
                            delimiter=',')
                    np.savetxt(os.path.join(self.resultPath, 'generation')
                            + '/decentralSTC_' + building["unique_name"] + '.csv',
                            building["generationSTC"],
                            delimiter=',')
                except Exception as e:

                    print(building["generationPV"])


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
            adjProfiles["seasonal_storage_kW"] = self.heat_grid_data["seasonal_storage_kW"][0:lengthArray]
            adjProfiles["waste_heat_kW"] = self.heat_grid_data["waste_heat_kW"][0:lengthArray]
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

            inputsClustering.append(adjProfiles["seasonal_storage_kW"])
            weights.append(0)
            scalings.append(False)

            inputsClustering.append(adjProfiles["waste_heat_kW"])
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
            self.heat_grid_data["seasonal_storage_cluster_kW"] = newProfiles[index_central + 2]
            self.heat_grid_data["waste_heat_cluster_kW"] = newProfiles[index_central + 3]
            self.heat_grid_data["pump_power_cluster"] = newProfiles[index_central + 4]
            self.centralDevices["generation"]["Wind_cluster"] = newProfiles[index_central + 5]
            self.centralDevices["generation"]["PV_cluster"] = newProfiles[index_central + 6]
            self.centralDevices["generation"]["STC_cluster"] = newProfiles[index_central + 7]

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
        print(f"\nOptimization of clusters for all simulated years completed in {end_time - start_time:.2f} seconds.")

        for year, clusters in self.resultsOptimization.items():
            for cluster, result in clusters.items():
                eh_results = opti_central.get_profiles_eh(result, data=self)
                eh_dir = os.path.join(self.resultPath, 'EnergyHub')
                os.makedirs(eh_dir, exist_ok=True)
                csv_filepath = os.path.join(eh_dir, f"{self.scenario_name}_eh_profiles_year_{year}_cluster_{cluster}.csv")
                eh_results.to_csv(csv_filepath, index=False, sep=';', decimal=',')


        # Check which clusters were unsolvable
        failed_optimizations = []
        for year, clusters in self.resultsOptimization.items():
            for cluster, result in clusters.items():
                if result is None:
                    failed_optimizations.append((year, cluster))

        if failed_optimizations:
            error_message = "The following optimization runs failed:\n"
            for year, cluster in failed_optimizations:
                error_message += f"  - Year: {year}, Cluster: {cluster}\n"
            
            error_message += "\nPlease check the corresponding 'errorfile_opti_central_*.txt' and '.ilp' files in the 'optimization_results' directory for further information."
            raise Exception(error_message)

    def calculate_ecoData_per_cluster(self):
        ecoData = self.ecoData
        simulated_years = self.ecoData["interpolation_points"]
        observation_time = self.ecoData["observation_time"]

        # select the relevant subset of ecoData for optimization
        single_value_keys = ['num_interpolation_points','interpolation_points', 'observation_time','interest_rate', 'optimization_focus']
        ecoData = {k: v for k, v in self.ecoData.copy().items() if k not in single_value_keys}

        # All keys that have co2 in name are undiscounted
        undiscounted_keys = set()
        co2_keys = set([k for k in ecoData.keys() if 'co2' in k.lower()])
        undiscounted_keys.update(co2_keys)

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
        if q < 1:
                print(f"Warning: interest factor q < 1 (q={q}). If not wanted check ecoData interest rate.")

        for year in simulated_years:
            relevant_years = year_segments[year]
            all_sim_ecoData[year] = {}  # Initialize dictionary for this year

            n = len(relevant_years)

            if q!=1:
                denom = sum(1/(q**idx) for idx in range(n))
            elif q==1:
                denom = n

            for key in ecoData.keys():
                subset_values = [ecoData[key][i] for i in relevant_years if i < len(ecoData[key])]

                # Calculate present value (PV) of the subset values
                if key in undiscounted_keys:
                    pv = sum(subset_values)  # No discounting for these keys
                    effective_price = pv / n  # For undiscounted values, the effective value is just the average over the years in the segment
                else:
                    pv = sum(val / (q ** idx) for idx, val in enumerate(subset_values))
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

    def map_wkb_to_scenario_format(self, wkb_file_path, output_file_path, batch_size=100):
        """
        Convert data from the WKB export format into the Quartier scenario format.

        The resulting scenario data is written to:
        - one combined CSV file at `output_file_path`
        - multiple batch CSV files, each containing at most `batch_size` buildings

        In addition, a reference CSV containing the original WKB rows for all accepted
        buildings is written by replacing "dg" with "wkb" in `output_file_path`.

        Validation rules:
        - Buildings with invalid or missing required values are skipped.
        - If a string-based value cannot be mapped to the target format, the building
          is skipped and the issue is printed.
        """

        def map_building_type(building_type_raw: str) -> str | None:
            """
            Map IWU/input building type strings to project-specific building types.

            Residential building rules use case-insensitive substring matching:
            - contains "EFH" -> "SFH"
            - contains "RH"  -> "TH"
            - contains "MFH" -> "MFH"
            - contains "GMH" -> "MFH"

            Other building types use exact matching.

            Returns:
                str | None:
                    The mapped building type, or None if the value cannot be mapped.
            """
            if building_type_raw is None or pd.isna(building_type_raw):
                return None

            value = str(building_type_raw).strip()
            value_upper = value.upper()

            # Residential buildings: substring-based matching
            if "GMH" in value_upper:
                return "MFH"
            if "MFH" in value_upper:
                return "MFH"
            if "EFH" in value_upper:
                return "SFH"
            if "RH" in value_upper:
                return "TH"

            exact_mapping = {
                # Non-residential buildings (IWU -> Quartiersgenerator)
                "NWG_TYP_A": "OB",
                "NWG_TYP_B": "UNI",
                "NWG_TYP_C": "HOSPITAL",
                "NWG_TYP_D": "SC",
                "NWG_TYP_E": "CULTURE",
                "NWG_TYP_F": "SPORT",
                "NWG_TYP_G": "RE",
                "NWG_TYP_H": "WORKSHOP",
                "NWG_TYP_I": "RETAIL",
                "NWG_TYP_J": "-",
                "NWG_TYP_K": "-",
                "NWG_TYP_SON": "-",

                # Mixed-use buildings (IWU -> Quartiersgenerator)
                "MN_TYP_A": "RETAIL+MFH",
                "MN_TYP_B": "MFH",
                "MN_TYP_C": "MFH+RETAIL",
                "MN_TYP_D": "MFH+WORKSHOP",
                "MN_A": "RETAIL+MFH",
                "MN_B": "MFH",
                "MN_C": "MFH+RETAIL",
                "MN_D": "MFH+WORKSHOP",
            }

            return exact_mapping.get(value_upper)

        def map_heater_type(heating_system_raw: str) -> str | None:
            """
            Map heating system strings to internal heater type codes.

            Returns:
                str | None:
                    The mapped heater type, or None if the value cannot be mapped.
            """
            if heating_system_raw is None or pd.isna(heating_system_raw):
                return "BOI"  # Default value for missing input

            value = str(heating_system_raw).strip()

            mapping = {
                "Gaskessel": "BOI",
                "Fernwärme": "DH",
                "Blockheizkraftwerk": "CHP",
                "Wärmepumpe": "HP",
                "Heat Pump": "HP",
                "Biomassekessel": "BBOI",
                "Ölkessel": "OBOI",
                "Wasserstoffkessel": "H2BOI",
                "opt": "opt",
                "opt_geg": "opt_geg",
                "opt_custom": "opt_custom",
                "heat_grid": "heat_grid",
            }

            return mapping.get(value)

        def map_retrofit_status(retrofit_status_raw: str) -> int | None:
            """
            Map retrofit status strings to integer codes.

            Mapping:
            - unsaniert   -> 0
            - teilsaniert -> 1
            - vollsaniert -> 2
            - saniert     -> 2

            Returns:
                int | None:
                    The mapped retrofit code, or None if the value cannot be mapped.
            """
            if retrofit_status_raw is None or pd.isna(retrofit_status_raw):
                return 0  # Default value for missing input

            value = str(retrofit_status_raw).strip()

            mapping = {
                "unsaniert": 0,
                "teilsaniert": 1,
                "vollsaniert": 2,
                "saniert": 2,
            }

            return mapping.get(value)

        def safe_convert_area(area_raw):
            """
            Safely convert an area value to a positive integer.

            Supports German decimal notation by replacing commas with dots.

            Returns:
                int | None:
                    A positive integer area value, or None if conversion fails
                    or the value is not positive.
            """
            if pd.isna(area_raw):
                return None

            try:
                value = area_raw
                if isinstance(value, str):
                    value = value.replace(",", ".").strip()
                    value = float(value)

                value = int(value)
                return value if value > 0 else None
            except (ValueError, TypeError):
                return None

        def safe_convert_year(year_raw):
            """
            Safely convert a year value to an integer.

            Returns:
                int | None:
                    The converted year, or None if conversion fails.
            """
            if pd.isna(year_raw):
                return None

            try:
                return int(float(year_raw))
            except (ValueError, TypeError):
                return None

        def has_valid_heat_demand(simulated_heat_demand_raw, measured_heat_demand_raw):
            """
            Check whether both simulated and measured heat demand values are valid.

            A value is considered valid if it can be converted to float and is > 0.
            """
            try:
                simulated = float(simulated_heat_demand_raw)
                measured = float(measured_heat_demand_raw)
                return simulated > 0 and measured > 0
            except (ValueError, TypeError):
                return False

        def convert_to_local_coordinates(df, x_col="x", y_col="y"):
            """
            Convert global coordinates into a local coordinate system by shifting
            the minimum x and y values to zero.
            """
            min_x = df[x_col].min()
            min_y = df[y_col].min()
            df["x_local"] = df[x_col] - min_x
            df["y_local"] = df[y_col] - min_y
            return df

        def print_row_problem(row_index, alkis_id, field_name, field_value, problem_description):
            """
            Print a standardized validation or mapping error for a building row.
            """
            print(
                f"Skipping building at row {row_index}"
                f"{f' (alkis_id={alkis_id})' if alkis_id is not None else ''}: "
                f"{problem_description} | field='{field_name}', value='{field_value}'"
            )

        def validate_and_transform_row(row, row_index):
            """
            Validate a WKB row and transform it into the target scenario format.

            Returns:
                dict | None:
                    A dictionary with transformed values if the row is valid,
                    otherwise None.
            """
            alkis_id = row.get("alkis_id")

            area = safe_convert_area(row.get("gross_floor_area"))
            if area is None:
                print_row_problem(
                    row_index, alkis_id, "gross_floor_area", row.get("gross_floor_area"),
                    "invalid gross floor area"
                )
                return None
            if area > 20000:
                print_row_problem(
                    row_index, alkis_id, "gross_floor_area", row.get("gross_floor_area"),
                    "gross floor area is implausibly large"
                )
                return None

            # if row.get("heat_relevance") != "wärmerelevant":
            #     print_row_problem(
            #         row_index, alkis_id, "heat_relevance", row.get("heat_relevance"),
            #         "building is not heat-relevant"
            #     )
            #     return None

            building_type = map_building_type(row.get("iwu_class"))
            if building_type is None:
                print_row_problem(
                    row_index, alkis_id, "iwu_class", row.get("iwu_class"),
                    "unmapped building type"
                )
                return None

            construction_year = safe_convert_year(row.get("construction_year"))
            if construction_year is None:
                print_row_problem(
                    row_index, alkis_id, "construction_year", row.get("construction_year"),
                    "invalid construction year"
                )
                return None

            retrofit_status = map_retrofit_status(row.get("renovation_state_simulated"))
            if retrofit_status is None:
                print_row_problem(
                    row_index, alkis_id, "renovation_state_simulated", row.get("renovation_state_simulated"),
                    "unmapped retrofit status"
                )
                return None

            heater_type = map_heater_type(row.get("heating_system"))
            if heater_type is None:
                print_row_problem(
                    row_index, alkis_id, "heating_system", row.get("heating_system"),
                    "unmapped heating system"
                )
                return None

            # if not has_valid_heat_demand(row.get("heat_demand_simulated"), row.get("energy_consumption_sh")):
            #     print_row_problem(
            #         row_index,
            #         alkis_id,
            #         "heat_demand_simulated / energy_consumption_sh",
            #         f"{row.get('heat_demand_simulated')} / {row.get('energy_consumption_sh')}",
            #         "invalid simulated or measured heat demand"
            #     )
            #     return None

            return {
                "alkis_id": alkis_id,
                "position": (row["x_local"], row["y_local"]),
                "building": building_type,
                "year": construction_year,
                "retrofit": retrofit_status,
                "construction_type": "2",  # Default: standard construction type
                "night_setback": 0,  # Default
                "area": area,
                "number_of_floors": row.get("number_floors"),
                "heater": heater_type,
                "cooling": 0,
                "EV": 0,  # Default
                "f_TES": 35,
                "f_BAT": 0,
                "f_PV1": 1,
                "f_PV2": 0,
                "f_STC": 0,
                "gamma_PV": 0,
                "ev_charging": "on_demand",
            }

        def determine_wastewater_heat_potential(column):
            """Extract a numeric waste heat potential from strings of the form 'x bis y kW'."""

            unique_values = set(column.dropna().unique())
            potentials = []

            for value in unique_values:
                match = re.match(r"^\s*(\d+(?:[\.,]\d+)?)\s+bis\s+(\d+(?:[\.,]\d+)?)\s*kW\s*$", str(value), re.IGNORECASE)
                if not match:
                    continue

                lower_bound = float(match.group(1).replace(",", "."))
                upper_bound = float(match.group(2).replace(",", "."))

                # Use the mean as the nominal capacity of the potential range.#
                val = (lower_bound + upper_bound) / 2
                if val > 5000:
                    potentials.append(5000)  # Cap the potential at 5000 kW
                else:
                    potentials.append(val)

            return max(potentials) if potentials else 0

        # Read WKB data
        wkb_data = pd.read_csv(
            wkb_file_path,
            encoding="utf-8",
            delimiter=",",
            decimal=".",
            na_values=["NULL", "null", "", "nan"]
        )

        # Ensure coordinates are numeric
        wkb_data["x"] = pd.to_numeric(wkb_data["x"], errors="coerce")
        wkb_data["y"] = pd.to_numeric(wkb_data["y"], errors="coerce")

        # Convert global EPSG:25833 coordinates to local coordinates for the simulation
        wkb_data = convert_to_local_coordinates(wkb_data, "x", "y")

        scenario_rows = []
        accepted_wkb_rows = []

        for row_index, row in wkb_data.iterrows():
            transformed_row = validate_and_transform_row(row, row_index)
            if transformed_row is None:
                continue

            transformed_row["id"] = transformed_row.get("alkis_id", f"building_row_{row_index}")
            scenario_rows.append(transformed_row)

            # Store the original WKB row for traceability
            wkb_row = row.to_dict()
            wkb_row["id"] = transformed_row.get("alkis_id", f"building_row_{row_index}")
            accepted_wkb_rows.append(wkb_row)

        scenario_df = pd.DataFrame(scenario_rows)
        accepted_wkb_df = pd.DataFrame(accepted_wkb_rows)

        # Save batch CSV files
        num_csv = max(1, (len(scenario_df) + batch_size - 1) // batch_size)
        print(f"Total valid buildings processed: {len(scenario_df)}. Saving to {num_csv} CSV file(s).")

        for batch_index in range(num_csv):
            batch_df = scenario_df.iloc[batch_index * batch_size:(batch_index + 1) * batch_size]
            batch_output_path = output_file_path.replace(".csv", f"_{batch_index}.csv")
            batch_df.to_csv(batch_output_path, sep=";", index=False)

        # Save combined CSV files
        scenario_df.to_csv(output_file_path, sep=";", index=False)
        accepted_wkb_df.to_csv(output_file_path.replace("dg", "wkb"), sep=";", index=False)

        # Adjust the nominal_waste_heat_capacity_kW of the heat grid data based on the waste heat potential if it is not already set
        if self.heat_grid_data["nominal_waste_heat_capacity_kW"] is None:
            key = "pot_abwasser_entzugsleistungsbereich_kw"
            if key in wkb_data.columns:
                self.heat_grid_data["nominal_waste_heat_capacity_kW"] = determine_wastewater_heat_potential(wkb_data[key])
            else:
                self.heat_grid_data["nominal_waste_heat_capacity_kW"] = 0
        return scenario_df

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

        # only get the position of buildings connected to the heat grid
        buildings_info = []
        for building in self.district:
            if building["buildingFeatures"]["heater"] == "heat_grid":
                pos = building["buildingFeatures"]["position"]
                building_dict = {"id": building["buildingFeatures"]["id"],
                                 "building": building["unique_name"],
                                 "position": pos}
                buildings_info.append(building_dict)

        if os.path.exists(json_path):
            district_type = self.site["district_parameters"]["district_type"]
            with open(json_path, encoding="utf-8") as json_file:
                jsonData = json.load(json_file)
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

        run_pipeline_node(district_type, buildings_info, transformer_info)

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

        # only get the position of buildings connected to the heat grid
        buildings_info = []
        for building in self.district:
            if building["buildingFeatures"]["heater"] == "heat_grid":
                building_dict = {"id": building["buildingFeatures"]["id"],
                                 "building": building["unique_name"],
                                 "position": building["buildingFeatures"]["position"]}
                buildings_info.append(building_dict)

        with open(os.path.join(self.scenario_file_path, f"{self.scenario_name}.json"), encoding="utf-8") as json_file:
            jsonData = json.load(json_file)
        lines_info = jsonData["values"]["lines_info"]
        transformer_info = jsonData["values"]["transformer_station"]

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
        network_optimization(self)

class DummyUser: pass

class DummyEnvelope: pass

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
        'dhwpower': building["dhwpower"],
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