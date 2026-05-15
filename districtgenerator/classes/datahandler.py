# -*- coding: utf-8 -*-

import json
import csv
import pickle
import os
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import warnings
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
from .KPIs import KPIs
from .non_residential import NonResidential
import districtgenerator.functions.SIA as SIA
import districtgenerator.functions.clustering_processing as cp
from districtgenerator.functions import opti_central
import districtgenerator.functions.heating_network_simple as heating_network_simple
from districtgenerator.functions.heating_network_simple import calculate_soil_temperature
from districtgenerator.data_handling.config import GlobalConfig, load_global_config, LocationConfig, TimeConfig, DesignBuildingConfig, EcoConfig, PhysicsConfig, EHDOConfig, PyomoConfig, HeatGridConfig, CalendarConfig, CentralDeviceConfig, DecentralDeviceConfig

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
                 env_path = None,
                 run_name: str = None,
                 project_data_path: str = None):
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

        self.conf_scenario_name = global_config.scenario_name.scenario_name
        
        srcPath = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        filePath = os.path.join(srcPath, 'data')

        self.srcPath = srcPath
        self.filePath = filePath

        self.initial_day = None
        self.district = []
        self.u_values = ()
        self.scenario_name = scenario_name or global_config.scenario_name.scenario_name or "example"
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
        self.all_sim_ecoData = {} # Later overwriten with the calculated economic data for the simulated years
        self.heat_grid_data = {}
        self.pipe_data = {}
        self.pyomo_config = {}
        # Additional attributes
        self.counter = {}
        self.calcThick = global_config.flags.calcThick
        self.calcOcc = global_config.flags.calcOcc
        self.calcOccProf = global_config.flags.calcOccProf
        self.building_dict = {} # Dictionary to store Residential Building IDs
        
        if scenario_file_path is not None:
            self.scenario_file_path = scenario_file_path
        elif project_data_path is not None:
            self.scenario_file_path = os.path.join(project_data_path, "DG", "scenarios")
        else:
            self.scenario_file_path = os.path.join(self.filePath, 'scenarios')

        if resultPath is not None:
            self.resultPath = resultPath
        elif project_data_path is not None:
            self.resultPath = os.path.join(project_data_path, "DG", "results")
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

        # load heat grid data (used in heating network design and optimization)
        for attr, value in heat_grid_config.__dict__.items():
            self.heat_grid_data[attr] = value

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
            pass
        else:
            print("Please select from the 3rd, 4th, or 5th generation and enter it into the config file.")

        # Determine the all_sim_ecoData which contains prices, co2 factors for each simulated year used for optimizations:
        self.all_sim_ecoData = self.calculate_ecoData_per_cluster()

        self.SIA2024 = SIA.read_SIA_data(self.filePath)

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
            building["buildingFeatures"] = row

            # Unique name = "<id>_<building type>"
            # in DEVELOP WITH {self.scenario_name}_ before bldg_id.. why?
            name = f"{bldg_id}_{row['building']}"

            if name in name_pool:
                print(f"Duplicate name: {name}, skipping")
                continue
            name_pool.append(name)

            # Assign the unique name to the building
            building["unique_name"] = name

            # Store features of the observed building
            building["buildingFeatures"] = row.to_dict()  # Convert row to dictionary

            ## ADDITION AIX HEAT for replacing values with default
            ## ggf den unique_name hier mit übergeben
            self.check_values(building["buildingFeatures"])

            # Validate that the sum of PV and STC roof area fractions does not exceed 1
            f_pv = building["buildingFeatures"].get("f_PV", 0) or 0
            f_stc = building["buildingFeatures"].get("f_STC", 0) or 0
            if f_pv + f_stc > 1:
                warnings.warn(
                    f"Building {bldg_id} ('{row['building']}'): f_PV ({f_pv}) + f_STC ({f_stc}) = {f_pv + f_stc} > 1. "
                    f"The combined PV and STC area exceeds the available rooftop area.",
                    UserWarning
                )

            # fixed order of values for later use!!
            target_cols = [
                "thermalTransmittanceFacade",
                "thermalTransmittanceRoof",
                "thermalTransmittanceFloor",
                "thermalTransmittanceWindow"
            ]

            values = []
            for col in target_cols:
                val = row.get(col)
                if val is None or pd.isna(val):
                    values.append(0)
                else:
                    values.append(val)

            building["buildingFeatures"]["thermalTransmittance"] = tuple(values)

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

    def check_values(self, buildingFeatures):
        """
        Check if necessary values are present.
        Parameters
        ----
        buildingFeatures: pandas.DataFrame
        DataFrame containing building features.

        Returns
        ---
        building_features: pandas.DataFrame
        DataFrame containing building features (updated if necessary).

        """
        # gmlId nur für AIX HEAT!
        necessary_values = ["area", "building", "year", "gmlId"]
        optional_values = ["number_of_floors",  "nb_occ", "nb_flats", "thermalTransmittanceRoof",
                           "thermalTransmittanceFacade", "thermalTransmittanceFloor", "thermalTransmittanceWindow", "height"]
        specific_values = ["f_TES", "f_BAT", "heater", "f_PV", "f_STC", "night_setback", "retrofit", "EV", "cooling"]

        default_values = {
            #optional values
            "number_of_floors": "random",
            "nb_occ": "random",
            "nb_flats": "random",
            "thermalTransmittanceRoof": "TEASER",
            "thermalTransmittanceFacade": "TEASER",
            "thermalTransmittanceFloor": "TEASER",
            "thermalTransmittanceWindow": "TEASER",
            "height": "calculate height_of_floors instead",
            # specific values
            "night_setback": 0,
            "retrofit": 0,
            "EV": 0,
            "f_TES": 35,
            "f_BAT": 1,
            "heater": "BOI",
            "f_PV": 0.4,
            "f_STC": 0.4,
            "cooling": 0
        }
        for val in necessary_values:
            if val not in buildingFeatures or pd.isna(buildingFeatures.get(val)):
                raise ValueError(f"{val} is a necessary value.")
        for val in optional_values:
            if val not in buildingFeatures or pd.isna(buildingFeatures.get(val)):
                print(f"{buildingFeatures['gmlId']}: --- {val} is not provided, districtgenerator will default to {default_values[val]}. ---")
                try:
                    del buildingFeatures[val]
                except KeyError:
                    pass
        for val in specific_values:
            if val not in buildingFeatures or pd.isna(buildingFeatures.get(val)):
                print(f"{buildingFeatures['gmlId']}: --- {val} set to {default_values[val]}. ---")
                buildingFeatures[val] = default_values[val]

        return buildingFeatures


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
                    if building["buildingFeatures"]["year"]>2015:
                        building["buildingFeatures"]["year"]=2015  #bugfix for tabula standard
                elif retrofit_level == "tabula_adv_retrofit":
                    construction_data = 'tabula_de_adv_retrofit'
                else:
                    # tabula standard
                    construction_data = 'tabula_de_standard'

                height = building["buildingFeatures"].get("height", 0)
                number_of_floors = building["buildingFeatures"].get("number_of_floors", 0)
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

                if self.design_building_data["thermal_model_type"] == "5R1C":
                    Envelope = Envelope_5R1C
                    building["thermal_model"] = "5R1C"
                elif self.design_building_data["thermal_model_type"] == "7R2C":
                    Envelope = Envelope_7R2C
                    building["thermal_model"] = "7R2C"
                else:
                    raise ValueError(f"Unknown thermal_model_type: {self.design_building_data['thermal_model_type']}")

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
                                                file_path=self.filePath)

            # %% create user object
            # containing number occupants, electricity demand,...
            building["user"] = Users(building=building["buildingFeatures"]["building"],
                                     area=building["buildingFeatures"]["area"],
                                     year_of_construction=building["buildingFeatures"]["year"],
                                     retrofit=building["buildingFeatures"]["retrofit"],
                                     SIA2024=self.SIA2024,
                                     nb_occ=building["buildingFeatures"]["nb_occ"] if ("nb_occ" in building["buildingFeatures"] and not pd.isna(building["buildingFeatures"]["nb_occ"])) else None,
                                     nb_flats=int(float(building["buildingFeatures"]["nb_flats"])) if "nb_flats" in building["buildingFeatures"] else None,
                                     scenario_name=self.scenario_name,
                                     calcOcc = self.calcOcc,
                                     calcOccProf = self.calcOccProf)

            night_setback = building["buildingFeatures"]["night_setback"]
            # %% calculate design heat loads in W
            # at norm outside temperature
            building["envelope"].heatload = building["envelope"].calcHeatLoad(site=self.site, method="design", night_setback = night_setback)
            # at bivalent temperature
            building["envelope"].bivalent = building["envelope"].calcHeatLoad(site=self.site, method="bivalent", night_setback = night_setback)
            # at heating limit temperature
            building["envelope"].heatlimit = building["envelope"].calcHeatLoad(site=self.site, method="heatlimit", night_setback = night_setback)
            # for drinking hot water
            building["envelope"].dhwpower = bldgs["dhwpower"][bldgs["buildings_short"].index(building["user"].building)] * building["buildingFeatures"]["area"]

            # %% calculate design cooling load
            building["envelope"].coolingload = building["envelope"].calcCoolingLoad(site=self.site, nb_occ=np.sum(building["user"].nb_occ))

            index = bldgs["buildings_short"].index(building["buildingFeatures"]["building"])
            building["buildingFeatures"] = building["buildingFeatures"].copy()
            building["buildingFeatures"]["mean_drawoff_dhw"] = bldgs["mean_drawoff_vol_per_day"][index]

    def generateDemands(self,name = None,  calcUserProfiles=True, saveUserProfiles=True, max_threads=8, gen_cars=True):
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

        self.buildings_total = len(self.district)
        self.buildings_completed = 0
        self.save_progress()

        results = []

        # Threads avoid pickling issues on Windows (no spawn, no handle duplication).
        with ThreadPoolExecutor(max_workers=max_threads) as ex:
            future_map = {
                ex.submit(self.generate_demands_worker, building, calcUserProfiles, saveUserProfiles, gen_cars): building[
                    "unique_name"]
                for building in self.district
            }

            for fut in as_completed(future_map):
                unique_name = future_map[fut]
                #try:
                result = fut.result()
                #except Exception as e:
                #    print(f"Error in building {unique_name}: {e}")
                #    continue

                self.buildings_completed += 1
                results.append(result)
                self.save_progress()

                print(f"building {self.buildings_completed}/{self.buildings_total} calculated "
                    f"({(self.buildings_completed / self.buildings_total) * 100:.1f}%): {unique_name}")

        # Write results back to district objects
        for result in results:
            building = next(b for b in self.district if b["unique_name"] == result["unique_name"])
            building["user"].elec = result["elec"]
            building["user"].dhw = result["dhw"]
            building["user"].cooling = result["cooling"]
            building["user"].heat = result["heating"]
            ## AIX HEAT
            building["gmlId"] = result["gmlId"]

            # IMPORTANT: remove the trailing comma (your current code makes this a 1-tuple)
            building["user"].occ = result["occ"]

            building["user"].EV_carcharging_ondemand =  result["EV_carcharging_ondemand"]
            building["user"].EV_carprofile = result["EV_carprofile"]
            building["user"].ev_capacity = result.get("ev_capacity")
            building["user"].ice_carprofile = result["ice_carprofile"]

            building["user"].gains = result["gains"]
            building["user"].nb_units = result["nb_units"]
            building["user"].nb_occ = result["nb_occ"]
            building["user"].individual_car_profiles = result.get("individual_car_profiles", [])

            # If Envelope is not safely serializable, keep the existing one and only store what you need.
            # If you really need it, keep it, but threads don't require pickling so it's fine.
            building["envelope"] = result["envelope"]
            building_features = building["buildingFeatures"].copy()
            building_features["night_setback"] = result["night_setback"]
            building["buildingFeatures"] = building_features

        self.save_progress()

        print("Finished generating demands with threading!")

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
                                          path=self.demands_path,
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
                                  thick_req= building["envelope"].thick_req,
                                  path=os.path.join(self.demands_path),
                                  individual_car_profiles=building["user"].individual_car_profiles)

        else:
            (building["user"].elec, building["user"].dhw,
             building["user"].occ, building["user"].gains,
             building["user"].EV_carcharging_ondemand, building["user"].EV_carprofile, building["user"].ice_carprofile, building["user"].nb_flats, building["user"].nb_main_rooms,
             building["user"].nb_occ, building["user"].ev_capacity, building["envelope"].heatload,
             building["envelope"].bivalent,
             building["envelope"].heatlimit,
             building["user"].individual_car_profiles) = self.loadProfiles(building["unique_name"],
                                                                 self.demands_path, gen_cars= gen_cars)
            (building["user"].heat, building["user"].cooling, building["gmlId"]) = self.loadHeatingProfiles(building["unique_name"], os.path.join(self.demands_path))
            # building["user"].loadProfiles(building["unique_name"], os.path.join(self.resultPath, 'demands'))
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
                                                calendar=self.calendar,
                                                time_resolution=self.time["timeResolution"],
                                                initial_day=self.initial_day)

            if saveUserProfiles:
                # idArray = []
                build_id = building["buildingFeatures"]["gmlId"] if "gmlId" in building["buildingFeatures"] else building["buildingFeatures"]["id"]
                self.saveHeatingProfile(heat=building["user"].heat,
                                        cooling=building["user"].cooling,
                                        name=building["unique_name"],
                                        gmlId=build_id,
                                        path=os.path.join(self.demands_path))
                #building["user"].saveHeatingProfile(building["unique_name"], os.path.join(self.resultPath, 'demands'))
            else:
                heat, cooling, id = self.loadHeatingProfiles(name=building["unique_name"],
                                                             path=(self.demands_path))
                building["user"].heat = heat
                building["user"].cooling = cooling
                building["gmlId"] = id

        print("Finished generating demands!")

        return {
            "unique_name": building["unique_name"],
            "elec": building["user"].elec,
            "dhw": building["user"].dhw,
            "cooling": building["user"].cooling,
            "heating": building["user"].heat,
            "occ": building["user"].occ,
            #AIXHEAT
            "gmlId": building["buildingFeatures"]["gmlId"],
            "EV_carcharging_ondemand": building["user"].EV_carcharging_ondemand,
            "EV_carprofile": building["user"].EV_carprofile,
            "ev_capacity": getattr(building["user"], "ev_capacity", None),
            "ice_carprofile": building["user"].ice_carprofile,
            "gains": building["user"].gains,
            "nb_units": building["user"].nb_units,  # or nb_flats/nb_main_rooms depending on your model
            "nb_occ": building["user"].nb_occ,
            "individual_car_profiles": getattr(building["user"], "individual_car_profiles", []),
            "envelope": building["envelope"],
            "night_setback": building["buildingFeatures"]["night_setback"],
        }

    def generateDistrictComplete(self, name = None, calcUserProfiles=True, saveUserProfiles=True,
                                 gen_cars=True, pv_standard=True, max_threads=8):
        """
        All in one solution for district and demand generation.
        Within a clustered time series, data points are aggregated across different time periods
        based on the k-medoids method.

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
        self.generateDemands(calcUserProfiles, saveUserProfiles, gen_cars=gen_cars, max_threads=max_threads)
        self.designDecentralDevices(saveGenerationProfiles=True, pv_standard=pv_standard)

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
                self.generateNetwork(topology_option="node")
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
                     nb_occ, heatload, bivalent, heatlimit, thick_req, path,
                     individual_car_profiles=None):
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
        nb_flats : int
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

        os.makedirs(path, exist_ok=True)

        time_resolution = self.time["timeResolution"]
        time_horizon = self.time["dataLength"]
        num_timesteps = int(time_horizon / time_resolution)

        # timeseries data points
        ts_dict = {
            'timestep': np.arange(num_timesteps) * (time_resolution / 3600),  # Index-Column (hour of the year)
            'elec': elec,
            'dhw': dhw,
            'occ': occ,
            'gains': gains,
            'EV_carprofile': EV_carprofile,
            'EV_carcharging_ondemand': EV_carcharging_ondemand,
            'ice_carprofile': ice_carprofile
        }

        car_info_list = []
        # Prepare individual car profiles for saving
        if individual_car_profiles is not None:
            for i, car in enumerate(individual_car_profiles):
                car_info_list.append({
                    "car_id": car.get('car_id'),
                    "type": car.get("type"),
                    "location": car.get("location"),
                    "battery_capacity_wh": car.get("battery_capacity_wh")
                })
                # Create Dataframes fot the individual car profiles
                if car['consumption_profile_wh'] is not None:
                    ts_dict[f'EV_demand_car_{i}'] = car['consumption_profile_wh']
                if car['on_demand_charging_profile_w'] is not None:
                    ts_dict[f'EV_charging_car_{i}'] = car['on_demand_charging_profile_w']
                if car['fuel_profile_l'] is not None:
                    ts_dict[f'ICE_fuel_car_{i}'] = car['fuel_profile_l']
                if car['availability_profile'] is not None:
                    ts_dict[f'Car_availability_car_{i}'] = car['availability_profile']

        df_ts = pd.DataFrame(ts_dict)
        df_ts.to_csv(os.path.join(path, f"{name}_timeseries.csv"), index=False)

        # Singular Data points (static)
        static_dict = {
            'nb_units': [nb_units],
            'nb_occ': [json.dumps(list(nb_occ) if isinstance(nb_occ, (list, np.ndarray)) else [nb_occ])],
            'ev_capacity': [
                json.dumps(list(ev_capacity) if isinstance(ev_capacity, (list, np.ndarray)) else [ev_capacity])],
            'heatload': [heatload],
            'bivalent': [bivalent],
            'heatlimit': [heatlimit],
            'car_info': [json.dumps(car_info_list)]
        }

        if thick_req is not None:
            static_dict['thick_req'] = [json.dumps(list(thick_req) if isinstance(thick_req, (list, np.ndarray)) else [thick_req])]

        df_static = pd.DataFrame(static_dict)
        df_static.to_csv(
            os.path.join(path, f"{name}_static.csv"),
            sep=';',
            index=False,
            float_format="%.3f"
        )


    def saveHeatingProfile(self, heat, cooling, name, gmlId, path):
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
        gmlId : str
            str of gmlId.
        path : string
            Results path.

        Returns
        -------
        None.
        """
        ts_path = os.path.join(path, f"{name}_timeseries.csv")
        if os.path.exists(ts_path):
            df_ts = pd.read_csv(ts_path)
        else:
            df_ts = pd.DataFrame()

        df_ts['heating'] = heat
        df_ts['cooling'] = cooling
        df_ts.to_csv(ts_path, index=False, float_format="%.3f", sep=";")

        static_path = os.path.join(path, f"{name}_static.csv")
        if os.path.exists(static_path):
            df_static = pd.read_csv(static_path, sep=";")
        else:
            df_static = pd.DataFrame()

        # wieso ist die gmlId als Liste gespeichert?
        df_static['gmlId'] = gmlId
        df_static.to_csv(static_path, index=False, float_format="%.3f", sep=";")


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
        ts_path = os.path.join(path, f"{name}_timeseries.csv")
        static_path = os.path.join(path, f"{name}_static.csv")

        df_ts = pd.read_csv(ts_path, sep=";")
        df_static = pd.read_csv(static_path, sep=";")

        elec = df_ts['elec'].to_numpy()
        dhw = df_ts['dhw'].to_numpy()
        occ = df_ts['occ'].to_numpy()
        gains = df_ts['gains'].to_numpy()

        nb_flats = int(df_static['nb_units'].iloc[0])
        nb_main_rooms = nb_flats
        heatload = float(df_static['heatload'].iloc[0])
        bivalent = float(df_static['bivalent'].iloc[0])
        heatlimit = float(df_static['heatlimit'].iloc[0])

        nb_occ = np.array(json.loads(df_static['nb_occ'].iloc[0]))
        ev_capacity = np.array(json.loads(df_static['ev_capacity'].iloc[0]))
        car_info_list = json.loads(df_static['car_info'].iloc[0])

        # Load car profiles
        individual_car_profiles = []
        if gen_cars: # Only load car profiles if cars are supposed to be generated
            EV_carprofile = df_ts['EV_carprofile'].to_numpy()
            EV_carcharging_ondemand = df_ts['EV_carcharging_ondemand'].to_numpy()
            ice_carprofile = df_ts['ice_carprofile'].to_numpy()

            for i, info in enumerate(car_info_list):
                car_profile = {
                    'car_id': info['car_id'],
                    'type': info['type'],
                    'location': info['location'],
                    'battery_capacity_wh': info['battery_capacity_wh'],
                    'consumption_profile_wh': df_ts[
                        f'EV_demand_car_{i}'].to_numpy() if f'EV_demand_car_{i}' in df_ts.columns and not df_ts[
                        f'EV_demand_car_{i}'].isnull().all() else None,
                    'on_demand_charging_profile_w': df_ts[
                        f'EV_charging_car_{i}'].to_numpy() if f'EV_charging_car_{i}' in df_ts.columns and not df_ts[
                        f'EV_charging_car_{i}'].isnull().all() else None,
                    'fuel_profile_l': df_ts[
                        f'ICE_fuel_car_{i}'].to_numpy() if f'ICE_fuel_car_{i}' in df_ts.columns and not df_ts[
                        f'ICE_fuel_car_{i}'].isnull().all() else None,
                    'availability_profile': df_ts[
                        f'Car_availability_car_{i}'].to_numpy() if f'Car_availability_car_{i}' in df_ts.columns and not
                    df_ts[f'Car_availability_car_{i}'].isnull().all() else None
                }
                individual_car_profiles.append(car_profile)
        else:
            # if no cars are generated, return zero profiles

            length = int(self.time["dataLength"] / self.time["timeResolution"])
            EV_carprofile = np.zeros(length)
            EV_carcharging_ondemand = np.zeros(length)
            ice_carprofile = np.zeros(length)

        return elec, dhw, occ, gains, EV_carcharging_ondemand, EV_carprofile, ice_carprofile, nb_flats, nb_main_rooms, nb_occ, ev_capacity, heatload, bivalent, heatlimit, individual_car_profiles

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
        tuple
            Loaded heating and cooling data.
        """
        ts_path = os.path.join(path, f"{name}_timeseries.csv")
        static_path = os.path.join(path, f"{name}_static.csv")

        df_ts = pd.read_csv(ts_path, sep=";")
        df_static = pd.read_csv(static_path, sep=";")

        heating = df_ts['heating'].to_numpy()
        cooling = df_ts['cooling'].to_numpy()
        gmlId = df_static['gmlId']

        return heating, cooling, gmlId

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

            # %% create building energy system object
            # get capacities of all possible devices
            building["bes_obj"] = BES(physics=self.physics,
                          decentral_device_data=self.decentral_device_data,
                          design_building_data=self.design_building_data,
                          file_path=self.filePath)
            building["capacities"] = building["bes_obj"].designECS(building, self.site)

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
                    building["user"].generationPV, building["user"].generationSTC = sun.calcPVAndSTCProfile(
                        time=self.time,
                        site=self.site,
                        area_roof=roof_areas,
                        betas=roof_inclinations,
                        gammas=cardinal_directions,
                        usageFactorPV=1, #set to 1 because roof area is netto
                        usageFactorSTC=1,
                        devices=self.decentral_device_data,
                    )

                    # ---- SAVE GENERATION PROFILES (Optional) ----
                    if saveGenerationProfiles:
                        # base_directory = os.path.join(self.resultPath, 'generation', self.scenario_name)
                        # os.makedirs(base_directory, exist_ok=True)
                        np.savetxt(
                            self.generation_path
                            + '/decentralPV_' + building["unique_name"] + '_' + self.scenario_name + '_'
                            + building["buildingFeatures"]["gmlId"].replace(":", "_") + '.csv',
                            building["user"].generationPV,
                            delimiter=';',
                            fmt='%.2f'
                        )

                        np.savetxt(
                            self.generation_path
                            + '/decentralSTC_' + building["unique_name"] + '_' + self.scenario_name + '_'
                            + building["buildingFeatures"]["gmlId"].replace(":", "_") + '.csv',
                            building["user"].generationSTC,
                            delimiter=';',
                            fmt='%.2f'
                        )
                else:
                    raise Exception("Using standard PV calculation")
            except:
                print("DEBUG: Using standard PV calculation for building " + building["unique_name"])
                # Standard single-surface calculation
                building["user"].generationPV, building["user"].generationSTC = \
                    sun.calcPVAndSTCProfile(time=self.time,
                                            site=self.site,
                                            devices=self.decentral_device_data,
                                            area_roof=[building["envelope"].A["opaque"]["roof"]],
                                            # In Germany, this is a roof pitch between 30 and 35 degrees
                                            betas=[35],
                                            # surface azimuth angles (Orientation to the south: 0°)
                                            gammas=[building["buildingFeatures"].get("gamma_PV", 0)],
                                            #DEFAULT VALUES FOR VALUE CHECK IN DATAHANDLER?? TODO
                                            usageFactorPV1=building["buildingFeatures"].get("f_PV1", 0),
                                            usageFactorPV2=building["buildingFeatures"].get("f_PV2", 0),
                                            usageFactorPV=building["buildingFeatures"].get("f_PV", 0),
                                            usageFactorSTC=building["buildingFeatures"].get("f_STC", 0.2))

                # optionally save generation profiles
                if saveGenerationProfiles == True:
                    np.savetxt(
                        self.generation_path
                        + '/decentralPV_' + building["unique_name"] + '_' + self.scenario_name + '_'
                        + building["buildingFeatures"]["gmlId"].replace(":", "_") + '.csv',
                        building["user"].generationPV,
                        delimiter=';',
                        fmt='%.2f'
                    )

                    np.savetxt(
                        self.generation_path
                        + '/decentralSTC_' + building["unique_name"] + '_' + self.scenario_name + '_'
                        + building["buildingFeatures"]["gmlId"].replace(":", "_") + '.csv',
                        building["user"].generationSTC,
                        delimiter=';',
                        fmt='%.2f'
                    )


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

        (self.clusters, self.clusterAssignments, self.clusterWeights,
         self.site, self.district, self.heat_grid_data) = (cp.clustering_processing(self.time, self.site, self.district,
                                                                                    self.heat_grid_data, self.centralDevices,
                                                                                    self.pyomo_config, centralEnergySupply))

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
                results_temp = opti_central.run_opti_central(data=self, year=year, cluster=cluster,
                                                             sim_ecoData=sim_ecoData, resultPath=self.resultPath)

                # save results as attribute
                self.resultsOptimization[year][cluster] = results_temp # Save the results of the optimization for each cluster

        end_time = time.time()

        with open(f'{self.optimization_path}/result_opti_central_total.json', 'w') as f:
            json.dump(self.resultsOptimization, f, indent=4)
        print(
            f"\nOptimization of all clusters for all simulated years completed in {end_time - start_time:.2f} seconds.")

    def calculate_ecoData_per_cluster(self):
        ecoData = self.ecoData
        # Change this to take the interpolation points from ecoData instead of hardcoding them
        self.ecoData["interpolation_points"] = [0]
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