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
from .plot import plot_all

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

    def __init__(self, scenario_name = "example", resultPath = None, scenario_file_path = None):
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

        # %% load scenario file with building information
        self.scenario = pd.read_csv(self.scenario_file_path + "/" + self.scenario_name + ".csv",
                                    header=0, delimiter=";")

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

        csv_path = os.path.join(self.filePath, 'pipe_specifications.csv')
        self.pipe_data = pd.read_csv(csv_path, sep=";")

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
        [temp_sunDirect, temp_sunDiff, temp_tempe, temp_wind, temp_rhum, temp_pre] = \
            [weatherData[:, 12], weatherData[:, 13], weatherData[:, 5], weatherData[:, 8], weatherData[:, 11], weatherData[:, 6]]

        self.time["timeSteps"] = int(self.time["dataLength"] / self.time["timeResolution"])

        # load the holidays
        if self.site["TRYYear"] == "TRY2015":
            self.time["holidays"] = self.get_holidays(country_code="DE", year=2015)
        elif self.site["TRYYear"] == "TRY2045":
            self.time["holidays"] = self.get_holidays(country_code="DE", year=2045)

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
        # Building type counters
        building_counts = {
            "SFH": 0, "TH": 0, "MFH": 0, "AB": 0, "OB": 0, "SC": 0,
            "GS": 0, "RE": 0, "MFH+OB": 0, "AB+OB": 0, "MFH+GS": 0,
            "AB+GS": 0, "MFH+RE": 0, "AB+RE": 0
        }

        name_pool = set()
        # Prepare a new list to collect updated scenario rows
        new_scenario = []
        next_id = 0

        # initialize buildings for scenario
        # Iterate through all buildings in scenario
        for idx, row in self.scenario.iterrows():

            # Ensure ID is numeric
            if not isinstance(idx, (int, float)):
                try:
                    idx = float(idx)
                except (ValueError, TypeError):
                    raise ValueError(f"Building ID '{idx}' is not a number")

            # Make a copy of the row to work on.
            building_features = row.copy()
            building_type = row["building"]

            # Check if the building type is a combined type
            if building_type in ['MFH+OB', 'AB+OB', 'MFH+GS', 'AB+GS', 'MFH+RE', 'AB+RE']:
                secondary_mapping = {"MFH+OB": "OB", "AB+OB": "OB", "MFH+GS": "GS", "AB+GS": "GS", "MFH+RE": "RE", "AB+RE": "RE"}
                # Assumptions: For office building: occupies the area of 4 flats; for grocery store: occupies 4 flats; for restaurant: occupies 2 flats:
                secondary_shares = {"OB": 4, "GS": 4, "RE": 2}
                secondary_type = secondary_mapping[building_type]
                secondary_share = secondary_shares[secondary_type]
                total_area = building_features["area"]

                # Determine the number of flats for the MFH portion.
                # Pick a random number assuming a typical flat has an area of about 80 m^2 (Source: Ergebnisse des Zensus 2022 Gebäude- und Wohnungszählung),
                # then subtract the office building's/grocery store's/restaurant's assumed share.
                num_flats = rd.randint((total_area // 80) - 1, (total_area // 80) + 1) - secondary_share
                if num_flats < 1:
                    raise ValueError("Building area is too small for a mixed-use configuration.")

                # Calculate the area per flat based on the total number of flats (MFH + secondary share):
                area_per_flat = total_area / (num_flats + secondary_share)
                # Determine the area of the MFH portion:
                mfh_area = int(num_flats * area_per_flat)
                # Set the area for secondary part of the building as the remaining area.
                secondary_area = int(total_area - mfh_area)

                # Make a copy of the building features for the MFH part
                mfh_building = building_features.copy()
                mfh_building.update({"id": next_id, "building": "MFH", "area": mfh_area, "construction_type": ""})

                # Create secondary building part
                secondary_building = building_features.copy()
                secondary_building.update({"id": next_id + 1, "building": secondary_type, "area": secondary_area,
                                           "PV": 0, "STC": 0, "BAT": 0, "f_BAT": 0, "f_PV": 0, "f_STC": 0,
                                           "gamma_PV": 0})

                # Assign unique mix identifier
                mix_value = f"mix {next_id} {next_id + 1}"
                mfh_building["mix"] = mix_value
                secondary_building["mix"] = mix_value

                # Generate unique names
                # needed for loading and storing data with unique name
                # name is composed of building id, and building type
                for building in [mfh_building, secondary_building]:
                    unique_name = f"{building['id']}_{building['building']}_{building.get('mix', '')}"
                    if unique_name in name_pool:
                        raise ValueError(f"Duplicate building name: {unique_name}")
                    name_pool.add(unique_name)
                    building["unique_name"] = unique_name

                # Save buildings
                self.district.append({"buildingFeatures": mfh_building})
                new_scenario.append(mfh_building)
                self.district.append({"buildingFeatures": secondary_building})
                new_scenario.append(secondary_building)
                next_id += 2

            else:
                # For non-mixed buildings, assign the next available id.
                building_features["id"] = next_id

                # %% Create unique building name
                # needed for loading and storing data with unique name
                # name is composed of building id, and building type
                unique_name = f"{building_features['id']}_{building_features['building']}"
                if unique_name in name_pool:
                    raise ValueError(f"Duplicate building name: {unique_name}")
                name_pool.add(unique_name)
                building_features["unique_name"] = unique_name

                self.district.append({"buildingFeatures": building_features})
                new_scenario.append(building_features)
                next_id += 1

            # Count number of builidings to predict the approximate calculation time
            building_counts[building_type] += 1
            #ToDo: Add the calculation time

        # Update self.scenario with the new (split) building entries.
        self.scenario = pd.DataFrame(new_scenario)
        self.generate_building_dict()

    def generate_building_dict(self):
        """
        Processes the scenario file and checks whether the building is residential or a mixed-use building.
        Creates a temp storage, to handle TEASER prj with ids starting from 0.

        Args:
            csv_file (str): Path to the CSV file containing building data with 'id' and 'building' columns.

        Returns:
            None: Modifies the internal building_dict attribute of the class.
        """

        # Filter the data for specified building types
        filtered_data = self.scenario[self.scenario['building'].isin(['SFH', 'TH', 'MFH', 'AB', 'MFH+OB', 'AB+OB', 'MFH+GS', 'AB+GS', 'MFH+RE', 'AB+RE'])]

        # Generate the dictionary
        temp_id = 0
        for index, row in filtered_data.iterrows():
            self.building_dict[row['id']] = temp_id
            temp_id += 1

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

                # %% create envelope object
                # containing all physical data of the envelope
                teaser_id = self.building_dict[building["buildingFeatures"]["id"]]
                building["envelope"] = Envelope(prj=prj,
                                                building_params=building["buildingFeatures"],
                                                construction_type=retrofit_level,
                                                physics=self.physics,
                                                design_building_data=self.design_building_data,
                                                file_path=self.filePath,
                                                teaser_id=teaser_id)

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

        for building in self.district:
            # calculate or load user profiles
            if calcUserProfiles:
                building["user"].calcProfiles(site=self.site,
                                              holidays=self.time["holidays"],
                                              time_resolution=self.time["timeResolution"],
                                              time_horizon=self.time["dataLength"],
                                              building_devices_data=self.decentral_device_data,
                                              building=building,
                                              path=os.path.join(self.resultPath, 'demands'),
                                              initial_day = self.initial_day)

                if saveUserProfiles:
                    self.saveProfiles(name=building["buildingFeatures"]["unique_name"],
                                      elec=building["user"].elec,
                                      dhw=building["user"].dhw,
                                      occ=building["user"].occ,
                                      gains=building["user"].gains,
                                      carcharging_ondemand=building["user"].carcharging_ondemand,
                                      carprofile=building["user"].carprofile,
                                      nb_flats_or_mainrooms=building["user"].nb_flats if building["buildingFeatures"]["building"] in {"SFH", "MFH", "TH", "AB"} else building["user"].nb_main_rooms,
                                      nb_occ=building["user"].nb_occ,
                                      ev_capacity=building["user"].ev_capacity or [0],
                                      heatload=building["envelope"].heatload,
                                      bivalent=building["envelope"].bivalent,
                                      heatlimit=building["envelope"].heatlimit,
                                      path=os.path.join(self.resultPath, 'demands'))

                print("Calculate demands of building " + building["buildingFeatures"]["unique_name"])

            else:
                (building["user"].elec, building["user"].dhw,
                 building["user"].occ, building["user"].gains,
                 building["user"].carcharging_ondemand, building["user"].carprofile, building["user"].nb_flats, building["user"].nb_main_rooms,
                 building["user"].nb_occ, building["user"].ev_capacity, building["envelope"].heatload,
                 building["envelope"].bivalent,
                 building["envelope"].heatlimit) = self.loadProfiles(building["buildingFeatures"]["unique_name"],
                                                                     os.path.join(self.resultPath, 'demands'))

                print("Load demands of building " + building["buildingFeatures"]["unique_name"])

            building["envelope"].calcNormativeProperties(self.site["SunRad"], building["user"].gains)

            night_setback = building["buildingFeatures"]["night_setback"]

            is_cooled = building["buildingFeatures"]["cooling"] # Indicates whether the building is actively cooled

            # calculate or load heating profiles
            if calcUserProfiles:
                building["user"].calcHeatingProfile(site=self.site,
                                                    envelope=building["envelope"],
                                                    night_setback=night_setback,
                                                    is_cooled=is_cooled,
                                                    holidays=self.time["holidays"],
                                                    time_resolution=self.time["timeResolution"]
                                                    )

                if saveUserProfiles:
                    self.saveHeatingProfile(heat=building["user"].heat,
                                            cooling=building["user"].cooling,
                                            name=building["buildingFeatures"]["unique_name"],
                                            path=os.path.join(self.resultPath, 'demands'))

            else:
                heat, cooling = self.loadHeatingProfiles(name=building["buildingFeatures"]["unique_name"],
                                                         path=os.path.join(self.resultPath, 'demands'))
                building["user"].heat = heat
                building["user"].cooling = cooling

        print("Finished generating demands!")

    def saveProfiles(self, name, elec, dhw, occ, gains, carcharging_ondemand, carprofile, ev_capacity, nb_flats_or_mainrooms, nb_occ, heatload, bivalent, heatlimit, path):
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

        data_dict = {
            'Electricity': (pd.DataFrame(elec), ["Electricity Demand (W)"]),
            'Hot Water': (pd.DataFrame(dhw), ["Drinking Hot Water Demand (W)"]),
            'Occupancy': (pd.DataFrame(occ), ["Number of Occupants"]),
            'Internal Gains': (pd.DataFrame(gains), ["Internal Gains (W)"]),
            'EV_charging': (pd.DataFrame(carcharging_ondemand), ["Electric Vehicle Charging Power on-Demand (W)"]),
            'EV_demand': (pd.DataFrame(carprofile), ["Electric Vehicle Energy Demand (Wh)"]),
            'Building Info': (pd.DataFrame({
                "Number of Flats or main Rooms": [nb_flats_or_mainrooms],
                "Number of Occupants": str(nb_occ)[1:-1],
                'EV_capacity': str(ev_capacity)[1:-1],
                "Design Heat Load (W)": [heatload],
                "Bivalent Heat Load (W)": [bivalent],
                "Heat Limit Heat Load (W)": [heatlimit]
            }), ["Number of Flats or main Rooms", "Number of Occupants", "EV_capacities",
                 "Design Heat Load (W)", "Bivalent Heat Load (W)",
                 "Heat Limit Heat Load (W)"])
        }

        # Define the Excel file path
        excel_file = os.path.join(path, name + '.xlsx')

        # Save each dataset into an Excel sheet with appropriate column names
        with pd.ExcelWriter(excel_file, engine='xlsxwriter') as writer:
            for sheet_name, (df, headers) in data_dict.items():
                df.to_excel(writer, sheet_name=sheet_name, index=False, header=headers)

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

        # Create a dictionary for storing datasets and their corresponding headers
        data_dict = {
            'Cooling': (pd.DataFrame(cooling), ["Cooling Demand (W)"]),
            'Heating': (pd.DataFrame(heat), ["Heating Demand (W)"])
        }

        with pd.ExcelWriter(excel_file, engine='openpyxl', mode='a', if_sheet_exists='overlay') as writer:
            for sheet_name, (df, headers) in data_dict.items():
                df.to_excel(writer, sheet_name=sheet_name, index=False, header=headers)

    def loadProfiles(self, name, path):
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

        building_id = int(name.split('_')[0])

        elec = load_sheet_to_numpy(workbook, 'Electricity')
        dhw = load_sheet_to_numpy(workbook, 'Hot Water')
        occ = load_sheet_to_numpy(workbook, 'Occupancy')
        gains = load_sheet_to_numpy(workbook, 'Internal Gains')
        if self.district[building_id]["buildingFeatures"].EV == 0:
            shape = elec.shape
            carcharging_ondemand = np.zeros(shape)
            carprofile = np.zeros(shape)
        else:
            carcharging_ondemand = load_sheet_to_numpy(workbook, 'EV_charging')
            carprofile = load_sheet_to_numpy(workbook, 'EV_demand')
        sheet = workbook['Building Info']
        other_data = [cell for cell in sheet.iter_rows(min_row=2, max_row=2, values_only=True)][0]  # Extracts first row
        nb_flats = int(other_data[0])
        nb_mainrooms = int(other_data[0])
        nb_occ = np.fromstring(other_data[1], dtype=int, sep=',')
        EV_capacity = np.fromstring(other_data[2], dtype=float, sep=',')
        heatload = float(other_data[3])
        bivalent = float(other_data[4])
        heatlimit = float(other_data[5])

        workbook.close()

        return elec, dhw, occ, gains, carcharging_ondemand, carprofile, nb_flats, nb_mainrooms, nb_occ, EV_capacity, heatload, bivalent, heatlimit

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

        heat = load_sheet_to_numpy(workbook, 'Heating')
        cooling = load_sheet_to_numpy(workbook, 'Cooling')

        workbook.close()

        return heat, cooling

    def generateDistrictComplete(self, calcUserProfiles=True, saveUserProfiles=True):
        """
        All in one solution for district and demand generation.

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

        self.initializeBuildings()
        self.generateEnvironment()
        self.generateBuildings()
        self.generateDemands(calcUserProfiles, saveUserProfiles)

        #Todo: make a mix of central and decentral buildings possible
        if self.district[0]["buildingFeatures"]["heater"] == "heat_grid":
            centralEnergySupply = True
            self.designDevicesComplete(saveGenerationProfiles=True)
        else:
            centralEnergySupply = False
            self.designDecentralDevices(saveGenerationProfiles=True)
            self.centralDevices = {}

        # Within a clustered time series, data points are aggregated across different time periods
        # based on the k-medoids method
        self.clusterProfiles(centralEnergySupply)

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
            bes_obj = BES(physics=self.physics,
                          decentral_device_data= self.decentral_device_data,
                          design_building_data=self.design_building_data,
                          file_path=self.filePath)
            building["capacities"] = bes_obj.designECS(building, self.site)

            # calculate PV and STC generation
            building["generationPV"], building["generationSTC"] = \
                sun.calcPVAndSTCProfile(time=self.time,
                                        site=self.site,
                                        area_roof=building["envelope"].A["opaque"]["roof"],
                                        # In Germany, this is a roof pitch between 30 and 35 degrees
                                        beta=[35],
                                        # surface azimuth angles (Orientation to the south: 0°)
                                        gamma=[building["buildingFeatures"]["gamma_PV"]],
                                        usageFactorPV=building["buildingFeatures"]["f_PV"],
                                        usageFactorSTC=building["buildingFeatures"]["f_STC"])

            # optionally save generation profiles
            if saveGenerationProfiles == True:
                np.savetxt(os.path.join(self.resultPath, 'generation')
                           + '/decentralPV_' + building["buildingFeatures"]["unique_name"] + '.csv',
                           building["generationPV"],
                           delimiter=',')
                np.savetxt(os.path.join(self.resultPath, 'generation')
                           + '/decentralSTC_' + building["buildingFeatures"]["unique_name"] + '.csv',
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

    def designDevicesComplete(self, saveGenerationProfiles=True):
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
        lenghtArray -= initialArrayLenght
        lenghtArray = int(lenghtArray)

        # adjust profiles with calculated array length
        adjProfiles = {}
        # loop over buildings
        for id in self.scenario["id"]:
            adjProfiles[id] = {}
            adjProfiles[id]["elec"] = self.district[id]["user"].elec[0:lenghtArray]
            adjProfiles[id]["dhw"] = self.district[id]["user"].dhw[0:lenghtArray]
            adjProfiles[id]["heat"] = self.district[id]["user"].heat[0:lenghtArray]
            adjProfiles[id]["cooling"] = self.district[id]["user"].cooling[0:lenghtArray]
            adjProfiles[id]["occ"] = self.district[id]["user"].occ[0:lenghtArray]
            adjProfiles[id]["carcharging_ondemand"] = self.district[id]["user"].carcharging_ondemand[0:lenghtArray]
            adjProfiles[id]["carprofile"] = self.district[id]["user"].carprofile[0:lenghtArray]
            adjProfiles[id]["generationPV"] = self.district[id]["generationPV"][0:lenghtArray]
            adjProfiles[id]["generationSTC"] = self.district[id]["generationSTC"][0:lenghtArray]

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
        inputsClustering = []

        # weights for clustering algorithm indicating the focus onto this profile
        weights = []

        # Scaling flags for each profile (True = scale after clustering, False = preserve values)
        scalings = []

        # loop over buildings
        for id in self.scenario["id"]:
            inputsClustering.append(adjProfiles[id]["elec"])
            weights.append(1)
            scalings.append(True)

            inputsClustering.append(adjProfiles[id]["dhw"])
            weights.append(1)
            scalings.append(True)

            inputsClustering.append(adjProfiles[id]["heat"])
            weights.append(1)
            scalings.append(True)

            inputsClustering.append(adjProfiles[id]["cooling"])
            weights.append(1)
            scalings.append(False)

            inputsClustering.append(adjProfiles[id]["occ"])
            weights.append(0)
            scalings.append(False)

            inputsClustering.append(adjProfiles[id]["carcharging_ondemand"])
            weights.append(0)      # This profile is not used at all for clustering
            scalings.append(False)  # This profile is not scaled

            inputsClustering.append(adjProfiles[id]["carprofile"])
            weights.append(0)      # This profile is not used at all for clustering
            scalings.append(False)  # This profile is not scaled

            inputsClustering.append(adjProfiles[id]["generationPV"])
            weights.append(1)
            scalings.append(True)

            inputsClustering.append(adjProfiles[id]["generationSTC"])
            weights.append(1)
            scalings.append(True)

        # Higher weight for outdoor temperature and central generation profiles,
        # since they each occur only once (unlike the building profiles)
        # and should therefore receive the same weight as the number of buildings.

        # ambient temperature
        inputsClustering.append(adjProfiles["T_e"])
        weights.append(len(self.scenario["id"]))
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
            weights.append(len(self.scenario["id"]))
            scalings.append(True)

            inputsClustering.append(adjProfiles["generationCentralPV"])
            weights.append(len(self.scenario["id"]))
            scalings.append(True)

            inputsClustering.append(adjProfiles["generationCentralSTC"])
            weights.append(len(self.scenario["id"]))
            scalings.append(True)

        # Perform clustering
        (newProfiles, nc, y, z, transfProfiles) = cm.cluster(np.array(inputsClustering),
                                                             number_clusters=self.time["clusterNumber"],
                                                             len_cluster=int(initialArrayLenght),
                                                             weights=weights,
                                                             scalings=scalings)

        # safe clustered profiles of all buildings
        for id in self.scenario["id"]:
            index_house = int(9)    # number of profiles per building
            self.district[id]["user"].elec_cluster = newProfiles[index_house * id]
            self.district[id]["user"].dhw_cluster = newProfiles[index_house * id + 1]
            self.district[id]["user"].heat_cluster = newProfiles[index_house * id + 2]
            self.district[id]["user"].cooling_cluster = newProfiles[index_house * id + 3]
            self.district[id]["user"].occ_cluster = newProfiles[index_house * id + 4]
            self.district[id]["user"].carcharging_ondemand_cluster = newProfiles[index_house * id + 5]
            self.district[id]["user"].carprofile_cluster = newProfiles[index_house * id + 6]
            self.district[id]["generationPV_cluster"] = newProfiles[index_house * id + 7]
            self.district[id]["generationSTC_cluster"] = newProfiles[index_house * id + 8]

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
