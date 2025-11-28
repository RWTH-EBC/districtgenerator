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
import districtgenerator.functions.clustering_medoid as cm
import districtgenerator.functions.heating_network_simple as heating_network_simple
from districtgenerator.functions.heating_network_opt import network_optimization
from districtgenerator.functions.design_network_with_node import run_pipeline_node
from districtgenerator.functions.design_network_with_road import run_pipeline_road
from districtgenerator.functions.heating_network_simple import calculate_soil_temperature
from .plots_balances import plot_all

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

    def __init__(self, scenario_name = "example", heat_map_berlin = False, resultPath = None, scenario_file_path = None):
        """
        Constructor of Datahandler class.

        Returns
        -------
        None.
        """

        self.site = {}
        self.time = {}
        self.initial_day = None
        self.district = []
        self.scenario_name = scenario_name
        self.heat_map_berlin = heat_map_berlin
        self.pv_stc_potential = None
        self.scenario = None
        self.total_building_area = None
        self.design_building_data = {}
        self.physics = {}
        self.decentral_device_data = {}
        self.params_ehdo_technical = {}
        self.params_ehdo_model = {}
        self.central_device_data = {}
        self.ecoData = {}
        self.counter = {}
        self.building_dict = {} # Dictionary to store Residential Building IDs
        self.srcPath = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.filePath = os.path.join(self.srcPath, 'data')

        if scenario_file_path is not None:
            self.scenario_file_path = scenario_file_path
        else:
            self.scenario_file_path = os.path.join(self.filePath, 'scenarios')

        if resultPath is not None:
            self.resultPath = resultPath
        else:
            self.resultPath = os.path.join(self.srcPath, 'results')

        self.KPIs = None
        self.load_all_data()

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

    def load_all_data(self):
        """
        General data import from JSON files and transformation into dictionaries.

        Returns
        -------
        None.
        """

        # %% load information about of the site under consideration (used in generateEnvironment)
        # important for weather conditions
        with open(os.path.join(self.filePath, 'site_data.json')) as json_file:
            jsonData = json.load(json_file)
            for subData in jsonData:
                self.site[subData["name"]] = subData["value"]

        # %% load time information and requirements (used in generateEnvironment)
        # needed for data conversion into the right time format
        with open(os.path.join(self.filePath, 'time_data.json')) as json_file:
            jsonData = json.load(json_file)
            for subData in jsonData:
                self.time[subData["name"]] = subData["value"]

        if self.heat_map_berlin:
            # %% load heat map berlin data
            self.map_wkb_to_scenario_format(self.scenario_file_path + "/" + self.scenario_name + ".csv",
                                            self.scenario_file_path + "/" + self.scenario_name + "_dg.csv")
            self.scenario = (pd.read_csv(os.path.join(self.scenario_file_path, f"{self.scenario_name}_dg.csv"), delimiter=";",
                                         converters={"position": parse_position}).set_index("id", drop=False))
            self.pv_stc_potential = pd.read_csv(
                self.scenario_file_path + "/" + self.scenario_name + "_pv_stc_potential.csv",
                delimiter=';',
                usecols=["uuid", "richtung", "neigung", "dachtyp", "modanetto"]
            )
        else:
            # %% load scenario file with building information
            self.scenario = (pd.read_csv(os.path.join(self.scenario_file_path, f"{self.scenario_name}.csv"), delimiter=";",
                                         converters={"position": parse_position}).set_index("id", drop=False))


        json_path = os.path.join(self.scenario_file_path, f"{self.scenario_name}.json")

        if os.path.exists(json_path):
            with open(json_path, encoding="utf-8") as json_file:
                jsonData = json.load(json_file)
                self.site["district_parameters"] = jsonData["parameters"]

        # %% load general building information
        # contains definitions and parameters that affect all buildings (used in envelope and system BES/CES)
        with open(os.path.join(self.filePath, 'design_building_data.json')) as json_file:
            jsonData = json.load(json_file)
            for subData in jsonData:
                self.design_building_data[subData["name"]] = subData["value"]

        # load building physics data (used in envelope and system BES/CES)
        with open(os.path.join(self.filePath, 'physics_data.json')) as json_file:
            jsonData = json.load(json_file)
            for subData in jsonData:
                self.physics[subData["name"]] = subData["value"]

        # Load list of possible devices (used in system BES)
        with open(os.path.join(self.filePath, 'decentral_device_data.json')) as json_file:
            jsonData = json.load(json_file)
            for subData in jsonData:
                self.decentral_device_data[subData["abbreviation"]] = {}
                for subsubData in subData["specifications"]:
                    self.decentral_device_data[subData["abbreviation"]][subsubData["name"]] = subsubData["value"]

        # import model parameters from json-file (used in system CES)
        with open(os.path.join(self.filePath, 'model_parameters_EHDO.json')) as json_file:
            jsonData = json.load(json_file)
            for subData in jsonData:
                if subData["name"] != "ref":
                    self.params_ehdo_model[subData["name"]] = subData["value"]
                else:
                    self.params_ehdo_model[subData["name"]] = {}
                    for subSubData in subData["value"]:
                        self.params_ehdo_model[subData["name"]][subSubData["name"]] = subSubData["value"]

        # load economic and ecologic data (of the district generator) (used in system CES)
        with open(os.path.join(self.filePath, 'eco_data.json')) as json_file:
            jsonData = json.load(json_file)
            for subData in jsonData:
                self.ecoData[subData["name"]] = subData["value"]

        with open(os.path.join(self.filePath, 'central_device_data.json')) as json_file:
            self.central_device_data = json.load(json_file)

        with open(os.path.join(self.filePath, 'heat_grid.json')) as json_file:
            self.heat_grid_data = json.load(json_file)

        self.pipe_file_path = os.path.join(self.filePath, 'pipe')
        # select the pipe file based on the generation selection
        # KMR for 3rd generation; PMR for 4th generation; PE for 5th generation
        if self.heat_grid_data["generation"]["value"] == "3rd":
            csv_path = os.path.join(self.pipe_file_path, 'pipe_specifications_KMR.csv')
            self.pipe_data = pd.read_csv(csv_path, sep=";")
        elif self.heat_grid_data["generation"]["value"] == "4th":
            csv_path = os.path.join(self.pipe_file_path, 'pipe_specifications_PMR.csv')
            self.pipe_data = pd.read_csv(csv_path, sep=";")
        elif self.heat_grid_data["generation"]["value"] == "5th":
            csv_path = os.path.join(self.pipe_file_path, 'pipe_specifications_PE.csv')
            self.pipe_data = pd.read_csv(csv_path, sep=";")
            pass
        else:
            print("Please select from the 3rd, 4th, or 5th generation and enter it into heat_grid.json.")

    def select_plz_data(self):
        """
        Select the closest TRY weather station for the location of the postal code.

        Returns
        -------
        weatherdatafile_location: int
            Location of the TRY weather station in lambert projection.
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

        Args:
            country_code (str): The country's ISO 3166-1 alpha-2 code (e.g., 'DE' for Germany).
            year (int): The year for which to retrieve holidays.
            state (str): The state or region subdivision code (e.g., 'NW' for North Rhine-Westphalia in Germany).

        Returns:
            list: A list of tuples containing the Julian day of the holiday.
        """
        try:
            # Initialize the holidays object for the given country, year, and state
            holidays = hol.CountryHoliday(country_code, years=year, subdiv=state)

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
            self.time["holidays"] = self.get_holidays(country_code="DE", year=2015)
        elif self.site["TRYYear"] == "TRY2045":
            self.time["holidays"] = self.get_holidays(country_code="DE", year=2045)

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

        # calculate or load user profiles
        if calcUserProfiles:
            building["user"].calcProfiles(site=self.site,
                                          holidays=self.time["holidays"],
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
                                                holidays=self.time["holidays"],
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

            if self.heat_map_berlin:
                # Read PV potentials for the current building from the DataFrame
                pv_data = self.pv_stc_potential[self.pv_stc_potential["uuid"] == building["buildingFeatures"]["alkis_id"]]
                # Initialize sums for PV and STC
                total_pv_generation = None
                total_stc_generation = None

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
                        area_roof=area,
                        beta=[tilt],
                        gamma=[azimuth],
                        usageFactorPV1=1,
                        usageFactorPV2=0,
                        usageFactorSTC=building["buildingFeatures"]["f_STC"]
                    )

                    # Sum up the profiles
                    if total_pv_generation is None:
                        total_pv_generation = pv_profile
                        total_stc_generation = stc_profile
                    else:
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
                                                             scalings=scalings)

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
            self.centralDevices["generation"]["Wind_cluster"] = newProfiles[index_central + 2]
            self.centralDevices["generation"]["PV_cluster"] = newProfiles[index_central + 3]
            self.centralDevices["generation"]["STC_cluster"] = newProfiles[index_central + 4]

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
        optiData = {}

        # initialize result list for all clusters
        self.resultsOptimization = []

        for cluster in range(self.time["clusterNumber"]):
            # optimize operating costs of the district for current cluster
            self.optimizer = Optimizer(self, cluster)
            results_temp = self.optimizer.run_cen_opti()

            # save results as attribute
            self.resultsOptimization.append(results_temp)

    def calulateKPIs(self):
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

        # Plot everything
        plot_all(self)

    def map_wkb_to_scenario_format(self, wkb_file_path, output_file_path, batch_size=8):
        """
        Überträgt Daten aus WKB_export Format in Quartier Format und zerlegt diese in so viele Dateien, dass jede Datei max. batch_size Gebäude enthält.
        """

        # Mapping-Funktionen definieren
        def map_building_type(gebaeudetype):
            """Mappt Gebäudetypen"""
            mapping = {
                'EFH': 'SFH',  # Einfamilienhaus -> Single Family House
                'RH': 'TH',  # Reihenhaus -> Terraced House
                'MFH': 'MFH',  # Mehrfamilienhaus -> Multi Family House
                'GMH': 'MFH'  # Geschosswohnhaus -> Multi Family House
            }
            return mapping.get(gebaeudetype, None)

        def map_heater_type(heizsystem):
            """Mappt Heizungstypen - konsistent mit Dictionary-Ansatz"""
            if pd.isna(heizsystem):
                return 'BOI'  # Default

            # Dictionary-Mapping wie beim building_type
            mapping = {
                'Gaskessel': 'BOI',
                'Fernwärme': 'DH',
                'Blockheizkraftwerk': 'CHP',
                'Wärmepumpe': 'HP',
                'Heat Pump': 'HP',
                'Biomassekessel': 'BBOI',
                'Ölkessel': 'OBOI',
                'Wasserstoffkessel': 'H2BOI',
            }

            return mapping.get(heizsystem, 'BOI')  # Default falls nicht gefunden

        def map_retrofit_status(sanierungszustand):
            """Mappt Sanierungszustand - auch mit Dictionary"""
            if pd.isna(sanierungszustand):
                return 0  # Default

            # Dictionary-Mapping
            mapping = {
                'unsaniert': 0,
                'teilsaniert': 1,
                'vollsaniert': 2,
                'saniert': 2  # Falls nur "saniert" ohne "voll" steht
            }

            return mapping.get(sanierungszustand,
                               None)  # Rückgabe None falls nicht gefunden damit diese Zeile später aussortiert wird

        def safe_convert_area(area_value):
            """Sicher Flächenwerte konvertieren"""
            if pd.isna(area_value): return None  # None if area_value is NaN

            try:
                # Komma durch Punkt ersetzen für deutsche Zahlenformate
                if isinstance(area_value, str):
                    area_value = area_value.replace(',', '.')
                    area_value = float(area_value)
                area_value = int(area_value)
                if area_value > 0:
                    return area_value
                else:
                    return None
            except:
                return None

        def safe_convert_year(year_value):

            if pd.isna(year_value):
                return None  # Default
            try:
                return int(float(year_value))
            except:
                return None

        def check_heat_demand_valid(heat_demand_simulated, heat_demand_measured):
            """Überprüft, ob beide Energiebedarfe (simuliert und gemessen) gültige Werte haben"""
            try:
                simulated = float(heat_demand_simulated)
                measured = float(heat_demand_measured)
                if simulated > 0 and measured > 0:
                    return True
                else:
                    return False
            except:
                return False

        def convert_to_local_coordinates(df, x_col="x", y_col="y"):
            """Convert UTM coordinates to a local coordinate system."""
            min_x = df[x_col].min()
            min_y = df[y_col].min()
            df["x_local"] = df[x_col] - min_x
            df["y_local"] = df[y_col] - min_y
            return df

        def check_all_values(row, idx):
            """Überprüft, ob alle notwendigen Werte vorhanden sind"""
            # gross_floor_area > 0
            if safe_convert_area(row.get('gross_floor_area')) == None:
                print(f"row {idx}: Invalid gross_floor_area: {row.get('gross_floor_area')}")
                return False
            if safe_convert_area(row.get('gross_floor_area')) > 20000:
                print(f"row {idx}: Building with too large gross_floor_area: {row.get('gross_floor_area')}")
                return False
            # heat_relevance
            if row.get('heat_relevance') != 'wärmerelevant':
                print(f"row {idx}: Invalid heat_relevance: {row.get('heat_relevance')}")
                return False
            # building_type_simplified vorhanden
            if map_building_type(row.get('building_type_simplified')) == None:
                print(f"Invalid building_type_simplified: {row.get('building_type_simplified')}")
                return False
            # construction_year vorhanden
            if safe_convert_year(row.get('construction_year')) == None:
                print(f"row {idx}: Invalid construction_year: {row.get('construction_year')}")
                return False
            # renovation_state_simulated vorhanden
            if map_retrofit_status(row.get('renovation_state_simulated')) == None:
                print(f"row {idx}: Invalid renovation_state_simulated: {row.get('renovation_state_simulated')}")
                return False

            # for a meaningful comparison, only buldings with a registered heat_demand (simulated and measured) are considered
            if check_heat_demand_valid(row.get('heat_demand_simulated'), row.get('energy_consumption_sh')) == False:
                print(
                    f"row {idx}: Invalid heat_demand_simulated or energy_consumption_sh: {row.get('heat_demand_simulated')}, {row.get('energy_consumption_sh')}")
                return False

            # Only if all checks are passed return true
            return True

        # WKB Daten einlesen
        wkb_data = pd.read_csv(wkb_file_path, encoding='utf-8', delimiter=',', decimal='.',
                               na_values=['NULL', 'null', '', 'nan'])

        # Make sure x/y are numeric
        wkb_data["x"] = pd.to_numeric(wkb_data["x"], errors="coerce")
        wkb_data["y"] = pd.to_numeric(wkb_data["y"], errors="coerce")

        # Convert global EPSG:25833 coords → local coords for our simulation
        wkb_data = convert_to_local_coordinates(wkb_data, "x", "y")

        # Sort the df by the 'gross_floor_area' key -> Buildings with big areas first to avoid them being last and then not profiting as much as they could from multiprocessing
        wkb_data['gross_floor_area'] = pd.to_numeric(wkb_data['gross_floor_area'], errors='coerce')
        wkb_data = wkb_data.sort_values(by='gross_floor_area', ascending=False)

        # Quartier Dataframe erstellen
        quartier_data = []
        wkb_data_for_csv = []

        new_id = 0

        for idx, row in wkb_data.iterrows():
            # Nur Wohngebäude berücksichtigen
            if row.get('type_of_use') == 'Wohnhaus' or pd.isna(row.get('type_of_use')):
                if check_all_values(row, idx):
                    quartier_row = {
                        'id': new_id,
                        'alkis_id': row.get('alkis_id'),
                        "position": (row["x_local"], row["y_local"]),
                        'building': map_building_type(row.get('building_type_simplified')),
                        'year': safe_convert_year(row.get('construction_year')),
                        'retrofit': map_retrofit_status(row.get('renovation_state_simulated')),
                        # Standard: nicht saniert
                        'construction_type': '',  # Leer lassen wie im Original
                        'night_setback': 0,  # Standard
                        'area': safe_convert_area(row.get('gross_floor_area')),
                        'number_of_floors': row.get('number_floors'),
                        'heater': map_heater_type(row.get('heating_system')),
                        'cooling': 0,
                        'EV': 0,  # Standard
                        'f_TES': 35,  # Wie im Original
                        'f_BAT': 0,  # Wie im Original
                        'f_PV1': 0,  # Wie im Original
                        'f_PV2': 0,  # Wie im Original
                        'f_STC': 0,  # Wie im Original
                        'gamma_PV': 0,  # Wie im Original
                        'ev_charging': 'on_demand',  # Wie im Original
                    }
                    quartier_data.append(quartier_row)

                    # Get the original WKB row for reference
                    wkb_row = row.to_dict()
                    wkb_row['id'] = new_id  # Add new_id for reference
                    wkb_data_for_csv.append(wkb_row)
                    new_id += 1

        # DataFrame erstellen
        quartier_df = pd.DataFrame(quartier_data)
        wkb_df = pd.DataFrame(wkb_data_for_csv)

        # Als CSV speichern
        num_csv = max(1, (len(quartier_df) + batch_size - 1) // batch_size)  # Berechne Anzahl der benötigten Dateien
        print(f"Total buildings processed: {len(quartier_df)}. Saving in {num_csv} CSV file(s).")

        for i in range(num_csv):
            batch_quartier_df = quartier_df.iloc[i * batch_size:(i + 1) * batch_size]
            quartier_batch_path = output_file_path.replace(".csv", f"_{i}.csv")
            batch_quartier_df.to_csv(quartier_batch_path, sep=';', index=False)

        # all_buildings combined CSV files
        quartier_df.to_csv(output_file_path, sep=';', index=False)
        wkb_df.to_csv(output_file_path.replace("dg", "wkb"), sep=';', index=False)

        return quartier_df
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

        if os.path.exists(json_path):
            district_type = self.site["district_parameters"]["district_type"]
            with open(json_path, encoding="utf-8") as json_file:
                jsonData = json.load(json_file)
                buildings_info = jsonData["values"]["buildings_info"]
                transformer_info = jsonData["values"]["transformer_station"]
        else:
            # if JSON file not found → Extract building coordinates from district data
            district_type = "unknown"
            buildings_info = []
            for building in self.district:
                pos = building["buildingFeatures"]["position"]
                building_dict = {"building": building["unique_name"],
                                 "position": pos}
                buildings_info.append(building_dict)

            # Randomly choose one building as transformer base
            chosen_building = random.choice(buildings_info)
            base_pos = chosen_building["position"]

            # Apply small random offset between choosen building and transformer (e.g., ±5 meters)
            offset_x = random.uniform(-5, 5)
            offset_y = random.uniform(-5, 5)
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

        with open(os.path.join(self.scenario_file_path, f"{self.scenario_name}.json"), encoding="utf-8") as json_file:
            jsonData = json.load(json_file)
        buildings_info = jsonData["values"]["buildings_info"]
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
        topology_file = f"topology_{topology_option}_{district_type}_buildings_{len(self.district)}.json"

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

def generate_demands_worker_wrapper(args):
    """
    Wrapper-Funktion außerhalb der Klasse, da multiprocessing pickling benötigt.
    Startet den Worker und den Monitor-Thread für ein Gebäude.
    Args enthält (building, calcUserProfiles, saveUserProfiles, andere Parameter)
    """
    try:
        warnings.filterwarnings("ignore",
                                category=FutureWarning)  # ! Ignoriere FutureWarnings in Multiprocessing for better readability of terminal output
        start_time_building = time.time()

        self_ref, building, calcUserProfiles, saveUserProfiles, gen_cars = args
        building_name = building.get("unique_name")

        # Event zum Stoppen des Monitor-Threads
        stop_event = threading.Event()

        timeout_duration = 1800  # 30 minutes to identify long-running threads
        monitor = threading.Thread(
            target=monitor_task,
            args=(start_time_building, timeout_duration, building_name, stop_event),
            daemon=True
        )
        monitor.start()

        # Starting the demand generation worker
        try:
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
        finally:
            # This part is always executed, even if an error occurs in the try block to safely close the monitor thread
            stop_event.set()
            monitor.join(timeout=1)  # Wait for the monitor thread to finish (with timeout)

        # Time needed for calculating this building
        end_time_building = time.time()
        duration_building = end_time_building - start_time_building

        return result, duration_building
    except Exception as e:
        print(f"Error in generate_demands_worker_wrapper for building {building.get('unique_name')}: {e}")
        return None, None


def monitor_task(start_time, timeout_duration, building_name, stop_event):
    """
    Monitors the progress of a task and gives a warning if the thread takes longer than the specified timeout duration.
    """

    # Wait for the specified timeout duration and check if the task is completed. During this time the thread is inactive.
    # If stop_event is set, the return is True, otherwise False after timeout
    was_stopped_in_time = stop_event.wait(timeout=timeout_duration)

    if was_stopped_in_time:
        pass  # Task completed within the timeout duration
    else:
        elapsed_time = time.time() - start_time
        print(f"Runtime Warning: The task for building {building_name} is already taking {elapsed_time:.2f} seconds.")

    # The monitoring thread ends here

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
