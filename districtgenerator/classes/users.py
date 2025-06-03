# -*- coding: utf-8 -*-
import json
import statistics
import os, math
import random as rd
import numpy as np
import pandas as pd
import openpyxl
from .profils import Profiles
from . import stochastic_load_wrapper_non_residential as wrap_light
import richardsonpy
import richardsonpy.classes.stochastic_el_load_wrapper as wrap
import richardsonpy.classes.appliance as app_model
import richardsonpy.classes.lighting as light_model
import districtgenerator.functions.heating_profile_5R1C as heating
import districtgenerator.functions.SIA as SIA

class Users:
    """
    Building Users class describing the number of occupants and their configs.

    Parameters
    ----------
    building : string
        Building type according to TABULA database.
    area : integer
        Total floor area of the building [m²].

    Attributes
    ----------
    building : string
        Building type according to TABULA database.
    nb_flats : integer
        Number of flats in building.
    nb_rooms : integer
        Number of rooms in the building
    nb_main_rooms : integer
        Number of main rooms (= working rooms) in the Building. For example the office rooms in an office building
    total_main_area : float
        The Area of the main rooms
    annual_el_demand_zones : dict
        The annual electricity demand of each zone of the building, without considering the electricity needed for lighting
    annual_el_demand_per_flat : array-like
        Annual electricity consumption in dependency of the building type and the number of occupants.
    lighting_index : integer
        This index defines the lighting configuration of the household.
    bulbs_power : list
        List of the rated electrical power of the light bulbs required for the building
    el_wrapper : object
        This objects holds information about the lighting and appliance configuration.
    nc_occ : list
        List with the number of occupants for each flat of the current building.
    occ : array-like
        Occupancy profile for each flat of the current building.
    dhw : array-like
        Drinking hot water profile for each building.
    elec : array-like
        Electrical demand for each building.
    gains : array-like
        Internal gains for each building.
    heat : array-like
        Heat demand for each building.
    """

    def __init__(self, building, area, year_of_construction, retrofit):
        """
        Constructor of Users class.

        Returns
        -------
        None.
        """

        self.building = building
        self.nb_flats = None
        self.annual_el_demand_per_flat = None
        self.nb_rooms = None
        self.nb_main_rooms = None
        self.total_main_area = None
        self.annual_el_demand = None
        self.annual_el_demand_zones = {}
        self.annual_heat_demand = None
        self.annual_cooling_demand = None
        self.lighting_index = []
        self.bulbs_power = []
        self.el_wrapper = []
        self.nb_occ = []
        self.occ = None
        self.dhw = None
        self.elec = None
        self.gains = None
        self.heat = None
        self.cooling = None
        self.carprofile = None
        self.carcharging_ondemand = None
        self.ev_capacity = None

        # Initialize SIA class and read data
        self.SIA2024 = SIA.read_SIA_data()
        if self.building in {"OB", "SC", "GS", "RE"}:
            self.building_zones = self.SIA2024[self.building]

        self.generate_number_flats_and_rooms(area)
        self.generate_number_occupants(area)
        self.generate_annual_el_consumption_residential()
        self.generate_annual_app_el_consumption_non_residential(
            area)  # Annual electricity consumption of all devices including the electricity required for ventilation and excluding the electricity required for lighting

        self.generate_lighting_index(area, year_of_construction, retrofit)
        self.create_el_wrapper()

    def generate_number_flats_and_rooms(self, area):
        """
        Generate number of flats and main rooms for different building types.
        Possible building types are:
            - single family house (SFH)
            - terraced house (TH)
            - multifamily house (MFH)
            - apartment block (AP)
            - office building (OB)
            - school (SC)
            - grocery store (GS)
            - restaurant (RE)

        Parameters
        ----------
        area : integer
            Floor area of different building types.

        Returns
        -------
        nb_flats : int
            The estimated number of flats.
        total_main_area : float
            The main area consists only of the main zones in the building
        """

        # Residential buildings
        # If the building is a SFH or TH,
        # it has only one flat.
        if self.building in ["SFH", "TH"]:
            self.nb_flats = 1

        # If the building is a MFH or AB,
        # we estimate the number of flats probabilistically.
        elif self.building in ["MFH", "AB"]:
            # Data source: Federal Statistical Office of Germany (Destatis), Zensus 2022
            # URL: https://www.zensus2022.de/
            # This method estimates the number of flats for multi-family houses (MFH) and apartment buildings (AB)
            # based on statistical data from Zensus 2022. The approach follows these steps:
            # 1. A predefined set of apartment size categories (in square meters) is used, each with an associated
            #   probability based on real-world statistics.
            # 2. A random apartment size category is selected using a weighted probability distribution.
            # 3. The mean value of the selected size range is used as the approximate flat size.
            # 4. The total number of flats is calculated by dividing the building’s total floor area by the selected flat size.
            # 5. The method ensures that the estimated number of flats is at least 2, as MFH and AB buildings should have
            #   multiple flats.

            area_categories = [(20, 39), (40, 59), (60, 79), (80, 99), (100, 119), (120, 139), (140, 159), (160, 179), (180, 199)]
            probabilities = [0.05896, 0.181403, 0.23811, 0.17094, 0.118865, 0.107155, 0.067465, 0.0350566, 0.02204]
            while True:
                # Choose one consistent flat size for the entire building
                chosen_area_range = rd.choices(area_categories, weights=probabilities, k=1)[0]
                chosen_area = (chosen_area_range[0] + chosen_area_range[1]) // 2  # Use the mean area of the selected range

                # Calculate the number of flats using rounding to the nearest integer
                self.nb_flats = round(area / chosen_area)

                # Ensure at least 2 flats
                if self.nb_flats > 1:
                    break

        # Non-residential buildings

        else:
            if self.building == "OB":
                proportion_office = 0
                nb_rooms = 0
                mean_area_per_main_room = 36                                    # According to SIA, the net area is 36 m² per office.
                for number, data in self.SIA2024.items():
                    zone_name = data.get('Zone_name_GER')
                    if zone_name:
                        proportion = self.building_zones[zone_name]
                        nb_rooms += area * proportion / data['area_room']
                self.nb_rooms = round(nb_rooms)

                for zone_name in {"Einzel-, Gruppenbüro", "Grossraumbüro"}:
                        proportion_office += self.building_zones[zone_name]
                self.total_main_area = area * proportion_office
                self.nb_main_rooms = round(self.total_main_area / rd.gauss(mean_area_per_main_room, mean_area_per_main_room * 0.1))   # A random number of offices following a Gaussian distribution with a mean of mean_area_per_main_room (36 m²) and a standard deviation of 10%. The number of offices is calculated in order to later determine the number of occupants of the building depending on it

            if self.building == "SC":
                proportion_classrooms = 0
                nb_rooms = 0
                mean_area_per_main_room = 70  # According to SIA, the net area is 70 m² per classroom.
                for number, data in self.SIA2024.items():
                    zone_name = data.get('Zone_name_GER')
                    if zone_name:
                        proportion = self.building_zones[zone_name]
                        nb_rooms += area * proportion / data['area_room']
                self.nb_rooms = round(nb_rooms)

                for zone_name in {"Schulzimmer", "Lehrerzimmer", "Bibliothek", "Hörsaal"}:
                    proportion_classrooms += self.building_zones[zone_name]
                self.total_main_area = area * proportion_classrooms
                self.nb_main_rooms = round(self.total_main_area / rd.gauss(mean_area_per_main_room,
                                                                           mean_area_per_main_room * 0.1))  # A random number of classrooms following a Gaussian distribution with a mean of mean_area_per_main_room (70 m²) and a standard deviation of 10%. The number of offices is calculated in order to later determine the number of occupants of the building depending on it

            if self.building == "GS":
                proportion_selling_space = 0
                nb_rooms = 0
                mean_area_per_main_room = 400         # According to SIA
                for number, data in self.SIA2024.items():
                    zone_name = data.get('Zone_name_GER')
                    if zone_name:
                        proportion = self.building_zones[zone_name]
                        nb_rooms += area * proportion / data['area_room']
                self.nb_rooms = round(nb_rooms)

                for zone_name in {"Lebensmittelverkauf"}:
                    proportion_selling_space += self.building_zones[zone_name]
                self.total_main_area = area * proportion_selling_space
                self.nb_main_rooms = max(round(self.total_main_area / rd.gauss(mean_area_per_main_room,
                                                                           mean_area_per_main_room * 0.1)),1)

            if self.building == "RE":
                proportion_restaurant = 0
                nb_rooms = 0
                mean_area_per_main_room = 144   # According to SIA
                for number, data in self.SIA2024.items():
                    zone_name = data.get('Zone_name_GER')
                    if zone_name:
                        proportion = self.building_zones[zone_name]
                        nb_rooms += area * proportion / data['area_room']
                self.nb_rooms = round(nb_rooms)

                for zone_name in {"Restaurant", "Küche zu Restaurant"}:
                    proportion_restaurant += self.building_zones[zone_name]
                self.total_main_area = area * proportion_restaurant
                self.nb_main_rooms = max(round(self.total_main_area / rd.gauss(mean_area_per_main_room,
                                                                           mean_area_per_main_room * 0.1)),1)

    def generate_number_occupants(self,area):
        """
        Generate number of occupants for different building types.

        Parameters
        ----------
        random_nb : random number in [0,1).

        Returns
        -------
        None.
        """

        if self.building == "SFH":
            # choose random number of occupants (1-5) for single family houses  (assumption)
            # Probabilities of having 1, 2, 3, 4 or 5 occupants in a single-family house, assuming a maximum of 5 occupants.
            # Sources: https://www.destatis.de/DE/Themen/Gesellschaft-Umwelt/Wohnen/Tabellen/tabelle-wo2-mietwohnungen.html
            #          https://www.destatis.de/DE/Themen/Gesellschaft-Umwelt/Wohnen/Tabellen/tabelle-wo2-eigentuemerwohnungen.html
            probabilities = (0.245114, 0.402323, 0.154148, 0.148869, 0.049623)
            # loop over all flats of current single family house
            for k in range(self.nb_flats):
                random_nb = rd.random()  # picking random number in [0,1)
                j = 1  # staring with one occupant
                # the random number decides how many occupants are chosen (1-5)
                while j <= 5 :
                    if random_nb < sum(probabilities[:j]) :
                        self.nb_occ.append(j)  # minimum is 1 occupant
                        break
                    j += 1
                else:
                    # Fallback in case no condition matched (due to floating-point issues)
                    self.nb_occ.append(5)

        elif self.building == "TH":
            # choose random number of occupants (1-5) for terraced houses  (assumption)
            # Probabilities of having 1, 2, 3, 4 or 5 occupants in a terraced house, assuming a maximum of 5 occupants.
            # Sources: https://www.destatis.de/DE/Themen/Gesellschaft-Umwelt/Wohnen/Tabellen/tabelle-wo2-mietwohnungen.html
            #          https://www.destatis.de/DE/Themen/Gesellschaft-Umwelt/Wohnen/Tabellen/tabelle-wo2-eigentuemerwohnungen.html
            probabilities = (0.236817, 0.400092, 0.157261, 0.154371, 0.051457)
            # loop over all flats of current terraced house
            for k in range(self.nb_flats):
                random_nb = rd.random()  # picking random number in [0,1)
                j = 1  # staring with one occupant
                # the random number decides how many occupants are chosen (1-5)
                while j <= 5 :
                    if random_nb < sum(probabilities[:j]) :
                        self.nb_occ.append(j)  # minimum is 1 occupant
                        break
                    j += 1
                else:
                    # Fallback in case no condition matched (due to floating-point issues)
                    self.nb_occ.append(5)

        elif self.building == "MFH":
            # choose random number of occupants (1-5) for each flat in the multi family house  (assumption)
            # Probabilities of having 1, 2, 3, 4 or 5 occupants in a flat, assuming a maximum of 5 occupants.
            # Sources: https://www.destatis.de/DE/Themen/Gesellschaft-Umwelt/Wohnen/Tabellen/tabelle-wo2-mietwohnungen.html
            #          https://www.destatis.de/DE/Themen/Gesellschaft-Umwelt/Wohnen/Tabellen/tabelle-wo2-eigentuemerwohnungen.html
            probabilities = (0.490622, 0.307419, 0.101949, 0.074417, 0.024805)
            # loop over all flats of current multi family house
            for k in range(self.nb_flats):
                random_nb = rd.random()  # picking random number in [0,1)
                j = 1  # staring with one occupant
                # the random number decides how many occupants are chosen (1-5)
                while j <= 5 :
                    if random_nb < sum(probabilities[:j]) :
                        self.nb_occ.append(j)  # minimum is 1 occupant
                        break
                    j += 1
                else:
                    # Fallback in case no condition matched (due to floating-point issues)
                    self.nb_occ.append(5)

        elif self.building == "AB":
            # choose random number of occupants (1-5) for each flat in the apartment block  (assumption)
            # Probabilities of having 1, 2, 3, 4 or 5 occupants in a flat, assuming a maximum of 5 occupants.
            # Sources: https://www.destatis.de/DE/Themen/Gesellschaft-Umwelt/Wohnen/Tabellen/tabelle-wo2-mietwohnungen.html
            #          https://www.destatis.de/DE/Themen/Gesellschaft-Umwelt/Wohnen/Tabellen/tabelle-wo2-eigentuemerwohnungen.html
            probabilities = (0.490622, 0.307419, 0.101949, 0.074417, 0.024805)
            # loop over all flats of current apartment block
            for k in range(self.nb_flats):
                random_nb = rd.random()  # picking random number in [0,1)
                j = 1  # staring with one occupant
                # the random number decides how many occupants are chosen (1-5)
                while j <= 5 :
                    if random_nb < sum(probabilities[:j]) :
                        self.nb_occ.append(j)  # minimum is 1 occupant
                        break
                    j += 1
                else:
                    # Fallback in case no condition matched (due to floating-point issues)
                    self.nb_occ.append(5)

        elif self.building == "OB":
                # loop over all office rooms of current office building
                for k in range(self.nb_main_rooms):
                    # self.nb_occ is the number of occupants in every main room
                    self.nb_occ.append(round(rd.gauss(self.total_main_area/self.nb_main_rooms/12,area/self.nb_main_rooms/12 * 0.15)))  # 12 m² area per occupant (source: SIA); assumption: random number based on a Gaussian distribution with a standard deviation of 15%

        elif self.building == "SC":
                # loop over all School main rooms of current School building
                for k in range(self.nb_main_rooms):
                    # self.nb_occ is the number of occupants in every main room
                    self.nb_occ.append(round(rd.gauss(self.total_main_area/self.nb_main_rooms/3,area/self.nb_main_rooms/3 * 0.15)))  # 3 m² area per occupant (source: SIA); assumption: random number based on a Gaussian distribution with a standard deviation of 15%

        elif self.building == "GS":
                for k in range(self.nb_main_rooms):
                    # self.nb_occ is the number of occupants in every main room
                    self.nb_occ.append(round(rd.gauss(self.total_main_area/self.nb_main_rooms/8,area/self.nb_main_rooms/8 * 0.15)))  # 8 m² area per occupant (source: SIA); assumption: random number based on a Gaussian distribution with a standard deviation of 15%

        elif self.building == "RE":
                for k in range(self.nb_main_rooms):
                    # self.nb_occ is the number of occupants in every main room
                    self.nb_occ.append(round(rd.gauss(self.total_main_area/self.nb_main_rooms/2,area/self.nb_main_rooms/2 * 0.15)))  # 2 m² area per occupant (source: SIA); assumption: random number based on a Gaussian distribution with a standard deviation of 15%

    def generate_annual_el_consumption_residential(self):
        """
        Generate annual electricity consumption
        in dependency of the building type and the number of occupants.

        Parameters
        ----------
        consumption_range : range of the annual consumption of electricity in kWh, not including electricity used for heating, dhw and cooling

        Returns
        -------
        None.
        """
        if self.building in {"SFH","TH","MFH","AB"}:
        # source: https://www.stromspiegel.de/fileadmin/ssi/stromspiegel/Downloads/StromspiegelFlyer_2023_Web.pdf
        # method: https://www.stromspiegel.de/ueber-uns-partner/methodik-des-stromspiegels/
        # Depending on the number of occupants in the household, there is a range of annual electricity demand with the corresponding probabilities
            consumption_range = {"SFH" : {1 : [1100,1400,1800,2200,2600,3400,4500,4800],
                                             2 : [1700,2000,2500,2800,3100,3500,4300,4600],
                                             3 : [2200,2500,3000,3500,3900,4400,5200,5500],
                                             4 : [2500,2800,3500,3900,4300,5000,6000,6300],
                                             5 : [2900,3200,4000,4500,5200,6000,7600,7900]},
                                    "MFH" : {1 : [600,800,1000,1300,1500,1700,2100,2300],
                                             2 : [1200,1400,1700,2000,2300,2500,3000,3200],
                                             3 : [1500,1700,2100,2500,2900,3300,3800,4000],
                                             4 : [1600,1800,2300,2600,3000,3600,4400,4600],
                                             5 : [1300,1500,2100,2700,3400,4100,5500,5700]}}

            probabilities = [0.143, 0.143, 0.143, 0.142, 0.143, 0.143, 0.143]

            self.annual_el_demand_per_flat = np.zeros(self.nb_flats)
            self.annual_el_demand = 0
            for j in range(self.nb_flats):
                if self.building == "SFH":
                    random_nb = rd.random()  # picking random number in [0,1) to decide between which 2 values of consumption_range the annual electricity consumption lies
                    i = 1
                    while i <= 7:
                        if random_nb < sum(probabilities[:i]):
                            self.annual_el_demand_per_flat[j] = rd.randint(consumption_range["SFH"][self.nb_occ[j]][i - 1], consumption_range["SFH"][self.nb_occ[j]][i])                            # A random integer is selected as the current demand, which must lie between the two values determined by the first random number
                            break
                        i += 1
                if self.building == "TH":
                    random_nb = rd.random()  # picking random number in [0,1) to decide between which 2 values of consumption_range the annual electricity consumption lies
                    i = 1
                    while i <= 7:
                        if random_nb < sum(probabilities[:i]):
                            self.annual_el_demand_per_flat[j] = rd.randint(consumption_range["SFH"][self.nb_occ[j]][i - 1], consumption_range["SFH"][self.nb_occ[j]][i])                            # A random integer is selected as the current demand, which must lie between the two values determined by the first random number
                            break
                        i += 1
                if self.building == "MFH":
                    random_nb = rd.random()  # picking random number in [0,1) to decide between which 2 values of consumption_range the annual electricity consumption lies
                    i = 1
                    while i <= 7:
                        if random_nb < sum(probabilities[:i]):
                            self.annual_el_demand_per_flat[j] = rd.randint(consumption_range["MFH"][self.nb_occ[j]][i - 1], consumption_range["MFH"][self.nb_occ[j]][i])                            # A random integer is selected as the current demand, which must lie between the two values determined by the first random number
                            break
                        i += 1
                if self.building == "AB":
                    random_nb = rd.random()  # picking random number in [0,1) to decide between which 2 values of consumption_range the annual electricity consumption lies
                    i = 1
                    while i <= 7:
                        if random_nb < sum(probabilities[:i]):
                            self.annual_el_demand_per_flat[j] = rd.randint(consumption_range["MFH"][self.nb_occ[j]][i - 1], consumption_range["MFH"][self.nb_occ[j]][i])                            # A random integer is selected as the current demand, which must lie between the two values determined by the first random number
                            break
                        i += 1
                self.annual_el_demand += self.annual_el_demand_per_flat[j]
    def generate_annual_app_el_consumption_non_residential(self, area, ventilation=0):             # Annual electricity consumption of all devices including the electricity required for ventilation and excluding the electricity required for lighting

        if self.building not in {"SFH","TH","MFH","AB"}:
            for number, data in self.SIA2024.items():
                zone_name = data.get('Zone_name_GER')
                if zone_name:
                        proportion = self.building_zones[zone_name]
                        yearly_electricity_standard = (  # no consideration of electricity for lighting
                                data['E_devices_year_kwh']['standard'] +
                                data['E_vent_year_kwh']['standard'] * ventilation)
                        yearly_electricity_goal = (  # no consideration of electricity for lighting
                                data['E_devices_year_kwh']['goal'] +
                                data['E_vent_year_kwh']['goal'] * ventilation)
                        yearly_electricity_existing = (  # no consideration of electricity for lighting
                                data['E_devices_year_kwh']['existing'] +
                                data['E_vent_year_kwh']['existing'] * ventilation)
                        consumptions = [yearly_electricity_standard, yearly_electricity_goal, yearly_electricity_existing]
                        consumption_range = [min(consumptions), statistics.median(consumptions),
                                                    max(consumptions)]  # composing a range for the consumption using data from SIA
                        probabilities = [0.5, 0.5]

                        annual_el_demand_zone = 0
                        for j in range(self.nb_main_rooms):
                            random_nb = rd.random()  # picking random number in [0,1) to decide between which 2 values of consumption_range the annual electricity consumption lies
                            i = 1
                            while i <= 2:
                                if random_nb < sum(probabilities[:i]):
                                    annual_el_demand_zone_room = rd.randint(
                                        round(area * consumption_range[i - 1] * proportion / self.nb_main_rooms),
                                        round(area * consumption_range[i] * proportion / self.nb_main_rooms))
                                    annual_el_demand_zone += annual_el_demand_zone_room

                                    # A random integer is selected as the current demand, which must lie between the two values determined by the first random number
                                    break
                                i += 1
                        self.annual_el_demand_zones[zone_name] = annual_el_demand_zone

    def generate_lighting_index(self, area, year_of_construction, retrofit):
        """
        Choose a random lighting index between 0 and 99 for the residential buildings.
        This index defines the lighting configuration of the household.
        There are 100 predefined lighting configurations.

        Assumptions: - All lighting configurations have the same probability.
                     - No differences between SFH, TH, MFH and AB.

        Select a list of bulbs for the non-residential buildings, depending on the needed
        room illuminance

        Parameters
        ----------
        area : float
            The area of the building in square meters.
        year_of_construction : int
            The year the building was constructed.
        retrofit : str
            Indicates whether the building is retrofitted or not
        room_illuminance : int
            The needed illuminance for the rooms in lux (Source: DIN EN 12464-1)
        lm_needed : float
            The luminous flux needed for a room in lumen
        total_lm : float
            The total luminous flux of all installed bulbs
        selected_lamps : list
            The list of the choosen lamps
        random_nb : random number in [0,1).

        Returns
        -------
        None.
        """

        if self.building in {"SFH","TH","MFH","AB"}:
            for j in range(self.nb_flats):
                random_nb = rd.random()
                self.lighting_index.append(int(random_nb * 100))

        else:
            file_name = "LightBulbs_nonresidential.json"
            # If the building was constructed before the year 2000 and has not been retrofitted
            # (indicated by `retrofit == 0`), select "combi_1" as the bulb configuration.
            if year_of_construction < 2000 and retrofit == 0:
                bulbs_combination =  "combi_1"
            # For buildings constructed in or after the year 2000, or for buildings that have been retrofitted
            # (indicated by any value other than 0 for `retrofit`), select "combi_2" as the bulb configuration.
            else:
                bulbs_combination = "combi_2"

            try:
                with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data',
                                   file_name)) as json_file:
                    jsonData = json.load(json_file)
            except FileNotFoundError:
                print(f"Error: File '{file_name}' not found.")
                return

            # Process data for different building types
            selected_combination = jsonData.get(bulbs_combination, [])
            # Source: DIN EN 12464-1
            illuminance_range = {
                "OB": (300, 650),
                "SC": (300, 400),
                "GS": (500, 750),
                "RE": (300, 500)
            }

            for _ in range(self.nb_rooms):
                room_illuminance = rd.randint(*illuminance_range[self.building])
                room_area = area / self.nb_rooms
                lm_needed = room_illuminance * room_area
                total_lm = 0
                selected_lamps = []

                # Install random bulbs as long as the required luminous flux has not yet been reached.
                while total_lm < lm_needed:
                    lamp = rd.choice(selected_combination)
                    selected_lamps.append(lamp)
                    total_lm += lamp["luminous_flux"]
                    self.bulbs_power.append(lamp["power"])

    def create_el_wrapper(self):
        """
        Create a wrapper-object
        holding information about the lighting and appliance configuration.

        Parameters
        ----------
        annual_demand : integer
            Annual electricity demand in kWh.
        light_config : integer
            This index defines the lighting configuration of the household.
            There are 100 predefined lighting configurations.

        Returns
        -------
        None.
        """
        if self.building in {"SFH","TH","MFH","AB"}:
            src_path = os.path.dirname(richardsonpy.__file__)
            path_app = os.path.join(src_path, 'inputs', 'Appliances.csv')
            path_light = os.path.join(src_path, 'inputs', 'LightBulbs.csv')

            for j in range(self.nb_flats):

                # annual demand of the electric appliances (annual demand minus lighting)
                # source: https://www.umweltbundesamt.de/daten/private-haushalte-konsum/wohnen/energieverbrauch-privater-haushalte#stromverbrauch-mit-einem-anteil-von-rund-einem-funftel
                # share of the electricity demand for lighting of the total electricity demand without heating, dhw and cooling for 2022: 7.9 / 81.8 = 9.6%
                appliancesDemand = 0.904 * self.annual_el_demand_per_flat[j]

                # Create and save appliances object
                appliances = \
                    app_model.Appliances(path_app,
                                         annual_consumption=appliancesDemand,
                                         randomize_appliances=True,
                                         max_iter=15,
                                         prev_heat_dev=True)

                # Create and save light configuration object
                lights = light_model.load_lighting_profile(filename=path_light,
                                                           index=self.lighting_index[j])

                #  Create wrapper object
                self.el_wrapper.append(wrap.ElectricityProfile(appliances, lights))

        else:

            # Save light configuration object
            lights = self.bulbs_power

            #  Create wrapper object only for lighting
            self.el_wrapper.append(wrap_light.ElectricityProfile(lights))

    def calcProfiles(self, site, holidays, time_resolution, time_horizon, building, building_devices_data, path, initial_day):
        """
        Calculate profiles for every flat and summarize them for the whole building

        Parameters
        ----------
        site: dict
            Site data, e.g. weather.
        time_resolution : integer
            Resolution of time steps of output array in seconds.
        time_horizon : integer
            Time horizon for which a stochastic profile is generated.
        initial_day : integer, optional
            Day of the week with which the generation starts.
            1-7 for monday-sunday. The default is 1.

        Returns
        -------
        None.
        """

        irradiation = site["SunTotal"]
        T_e = site["T_e"]

        time_day = 24 * 60 * 60
        nb_days = int(time_horizon/time_day)
        if self.building in {"SFH", "TH", "MFH", "AB"}:

            self.occ = np.zeros(int(time_horizon / time_resolution))
            self.dhw = np.zeros(int(time_horizon / time_resolution))
            self.elec = np.zeros(int(time_horizon / time_resolution))
            self.gains = np.zeros(int(time_horizon / time_resolution))
            self.carprofile = np.zeros(int(time_horizon / time_resolution))
            self.carcharging_ondemand = np.zeros(int(time_horizon / time_resolution))
            self.ev_capacity = []

            for j in range(self.nb_flats):
                temp_obj = Profiles(number_occupants=self.nb_occ[j], number_occupants_building=sum(self.nb_occ),
                                    initial_day=initial_day, nb_days=nb_days, time_resolution=time_resolution,
                                    building=self.building)
                self.dhw = self.dhw + temp_obj.generate_dhw_profile(building=building, holidays=holidays)

                # Occupancy profile in a flat
                self.occ = self.occ + temp_obj.generate_occupancy_profiles_residential()
                self.elec = self.elec + temp_obj.generate_el_profile_residential(holidays=holidays,
                                                                                 irradiance=irradiation,
                                                                                 el_wrapper=self.el_wrapper[j],
                                                                                 annual_demand=self.annual_el_demand_per_flat[j])

                self.gains = self.gains + temp_obj.generate_gain_profile_residential()
                carprofile, on_demand_charging, ev_capacity = temp_obj.generate_ev_profile(building=building, building_devices_data = building_devices_data, holidays=holidays)
                self.carprofile = self.carprofile + carprofile # Sum car profiles over all flats in the building
                self.carcharging_ondemand = self.carcharging_ondemand + on_demand_charging
                self.ev_capacity += ev_capacity

        else:
            temp_obj = Profiles(number_occupants=round(statistics.mean(self.nb_occ)), number_occupants_building=sum(self.nb_occ),initial_day=initial_day, nb_days=nb_days, time_resolution=time_resolution,building=self.building)
            # Occupancy profile in the building
            _,self.occ,_ = temp_obj.generate_profiles_non_residential(holidays = holidays)
            self.elec = temp_obj.generate_el_profile_non_residential(irradiance=irradiation,el_wrapper=self.el_wrapper[0],annual_demand_app=self.annual_el_demand_zones)

            gains_persons, gains_others = temp_obj.generate_gain_profile_non_residential()
            self.gains = gains_persons + gains_others

            self.dhw = temp_obj.generate_dhw_profile(building=building, holidays=holidays)

            # In the case of non-residential buildings, EVs are only for office buildings
            if self.building in {"OB"}:
                self.carprofile, self.carcharging_ondemand, self.ev_capacity = temp_obj.generate_ev_profile(building=building, building_devices_data = building_devices_data, holidays=holidays)
            else:
                self.carprofile = np.zeros(len(self.occ), dtype=np.float64)
                self.carcharging_ondemand = np.zeros(len(self.occ), dtype=np.float64)
                self.ev_capacity = [0.0]

    def calcHeatingProfile(self, site, envelope, night_setback, is_cooled, holidays, time_resolution):
        """
        Calculate heat demand for each building.

        Parameters
        ----------
        site: dict
            Site data, e.g. weather.
        envelope: object
            Containing all physical data of the envelope.
        time_resolution : integer
            Resolution of time steps of output array in seconds.
        Q_H : float
            Heating load for the current time step in Watt.
        Q_C : float
            Cooling load for the current time step in Watt.

        Returns
        -------
        None.
        """

        dt = time_resolution / (60 * 60)
        # calculate the temperatures (Q_HC, T_op, T_m, T_air, T_s)
        if night_setback == 1:
            (Q_H, Q_C, T_op, T_m, T_i, T_s) = heating.calc_night_setback(envelope, site["T_e"], holidays, dt,
                                                                         self.building)
        elif night_setback == 0:
            (Q_H, Q_C, T_op, T_m, T_i, T_s) = heating.calc(envelope, site["T_e"], holidays, dt, self.building)

        # Force cooling to zero if building is not actively cooled
        if is_cooled == 0:
            Q_C = np.zeros_like(Q_C)

        # heating and cooling loads for the current time step in Watt
        self.heat = Q_H
        self.cooling = Q_C
        self.annual_heat_demand = np.sum(Q_H)
        self.annual_cooling_demand = np.sum(Q_C)

if __name__ == '__main__':

    test = Users(building="SFH",
                 area=1000)

    test.calcProfiles()