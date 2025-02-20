# -*- coding: utf-8 -*-
import json
import statistics
import os, math
import random as rd
import numpy as np
from classes.profils import Profiles
import classes.stochastic_load_wrapper_non_residential as wrap_light
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
    annual_el_demand : array-like
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
        self.nb_rooms = None
        self.nb_main_rooms = None
        self.total_main_area = None
        self.annual_el_demand = None
        self.annual_el_demand_zones = {}
        self.annual_heat_demand = None
        self.annual_dhw_demand = None
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

        # Initialize SIA class and read data
        self.SIA2024 = SIA.read_SIA_data()
        if self.building in {"OB", "School", "Grocery_store"}:
            self.building_zones = self.SIA2024[self.building]


        self.generate_number_flats_and_rooms(area)
        self.generate_number_occupants(area)
        self.generate_annual_el_consumption_residential()
        self.generate_annual_app_el_consumption_non_residential(area)  # Annual electricity consumption of all devices including the electricity required for ventilation and excluding the electricity required for lighting

        self.generate_lighting_index(area, year_of_construction, retrofit)
        self.create_el_wrapper()

    def generate_number_flats_and_rooms(self, area):
        """
        Generate number of flats for different of building types.
        Possible building types are:
            - single family house (SFH)
            - terraced house (TH)
            - multifamily house (MFH)
            - apartment block (AP)

        Parameters
        ----------
        area : integer
            Floor area of different building types.
        total_main_area : float
            The main area consists only of the workspaces, which here are the offices
        Returns
        -------
        None.
        """

        if self.building == "SFH":
            self.nb_flats = 1
        elif self.building == "TH":
            self.nb_flats = 1
        elif self.building == "MFH":
            if area <= 2 * 100:
                self.nb_flats = 3
            elif area <= 4 * 100:
                self.nb_flats = 5
            elif area > 4 * 100:
                self.nb_flats = rd.randint((area//80)-1, (area//80)+1)
        elif self.building == "AB":
            if area <= 2 * 100:
                self.nb_flats = 3
            elif area <= 4 * 100:
                self.nb_flats = 5
            elif area > 4 * 100:
                self.nb_flats = rd.randint((area//80)-1, (area//80)+1)
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

            if self.building == "School":
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

            if self.building == "Grocery_store":
                proportion_selling_space = 0
                nb_rooms = 0
                mean_area_per_main_room = 400
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
    def generate_number_occupants(self,area):
        """
        Generate number of occupants for different of building types.

        Parameters
        ----------
        random_nb : random number in [0,1).

        Returns
        -------
        None.
        """

        if self.building == "SFH":
            # choose random number of occupants (1-5) for single family houses  (assumption)
            probabilities = (0.245114, 0.402323, 0.154148, 0.148869, 0.049623) # Probabilities of having 1, 2, 3, 4 or 5 occupants in a single-family house, assuming a maximum of 5 occupants. Sources: https://www.destatis.de/DE/Themen/Gesellschaft-Umwelt/Wohnen/Tabellen/tabelle-wo2-mietwohnungen.html and https://www.destatis.de/DE/Themen/Gesellschaft-Umwelt/Wohnen/Tabellen/tabelle-wo2-eigentuemerwohnungen.html
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

        elif self.building == "TH":
            # choose random number of occupants (1-5) for terraced houses  (assumption)
            probabilities = (0.236817, 0.400092, 0.157261, 0.154371, 0.051457) # Probabilities of having 1, 2, 3, 4 or 5 occupants in a terraced house, assuming a maximum of 4 occupants. Sources: https://www.destatis.de/DE/Themen/Gesellschaft-Umwelt/Wohnen/Tabellen/tabelle-wo2-mietwohnungen.html and https://www.destatis.de/DE/Themen/Gesellschaft-Umwelt/Wohnen/Tabellen/tabelle-wo2-eigentuemerwohnungen.html
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

        elif self.building == "MFH":
            # choose random number of occupants (1-5) for each flat in the multi family house  (assumption)
            probabilities = (0.490622, 0.307419, 0.101949, 0.074417, 0.024805) # Probabilities of having 1, 2, 3, 4 or 5 occupants in a flat, assuming a maximum of 4 occupants. Sources: https://www.destatis.de/DE/Themen/Gesellschaft-Umwelt/Wohnen/Tabellen/tabelle-wo2-mietwohnungen.html and https://www.destatis.de/DE/Themen/Gesellschaft-Umwelt/Wohnen/Tabellen/tabelle-wo2-eigentuemerwohnungen.html
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

        elif self.building == "AB":
            # choose random number of occupants (1-5) for each flat in the apartment block  (assumption)
            probabilities = (0.490622, 0.307419, 0.101949, 0.074417, 0.024805) # Probabilities of having 1, 2, 3, 4 or 5 occupants in a flat, assuming a maximum of 4 occupants. Sources: https://www.destatis.de/DE/Themen/Gesellschaft-Umwelt/Wohnen/Tabellen/tabelle-wo2-mietwohnungen.html and https://www.destatis.de/DE/Themen/Gesellschaft-Umwelt/Wohnen/Tabellen/tabelle-wo2-eigentuemerwohnungen.html
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

        elif self.building == "OB":
                # loop over all office rooms of current office building
                for k in range(self.nb_main_rooms):
                    # self.nb_occ is the number of occupants in every main room
                    self.nb_occ.append(round(rd.gauss(self.total_main_area/self.nb_main_rooms/12,area/self.nb_main_rooms/12 * 0.15)))  # 12 m² area per occupant (source: SIA); assumption: random number based on a Gaussian distribution with a standard deviation of 15%

        elif self.building == "School":
                # loop over all School main rooms of current School building
                for k in range(self.nb_main_rooms):
                    # self.nb_occ is the number of occupants in every main room
                    self.nb_occ.append(round(rd.gauss(self.total_main_area/self.nb_main_rooms/3,area/self.nb_main_rooms/3 * 0.15)))  # 3 m² area per occupant (source: SIA); assumption: random number based on a Gaussian distribution with a standard deviation of 15%

        elif self.building == "Grocery_store":
                for k in range(self.nb_main_rooms):
                    # self.nb_occ is the number of occupants in every main room
                    self.nb_occ.append(round(rd.gauss(self.total_main_area/self.nb_main_rooms/8,area/self.nb_main_rooms/8 * 0.15)))
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

            self.annual_el_demand = np.zeros(self.nb_flats)
            for j in range(self.nb_flats):
                if self.building == "SFH":
                    random_nb = rd.random()  # picking random number in [0,1) to decide between which 2 values of consumption_range the annual electricity consumption lies
                    i = 1
                    while i <= 7:
                        if random_nb < sum(probabilities[:i]):
                            self.annual_el_demand[j] = rd.randint(consumption_range["SFH"][self.nb_occ[j]][i - 1], consumption_range["SFH"][self.nb_occ[j]][i])
                            # A random integer is selected as the current demand, which must lie between the two values determined by the first random number
                            break
                        i += 1
                if self.building == "TH":
                    random_nb = rd.random()  # picking random number in [0,1) to decide between which 2 values of consumption_range the annual electricity consumption lies
                    i = 1
                    while i <= 7:
                        if random_nb < sum(probabilities[:i]):
                            self.annual_el_demand[j] = rd.randint(consumption_range["SFH"][self.nb_occ[j]][i - 1],consumption_range["SFH"][self.nb_occ[j]][i])
                            # A random integer is selected as the current demand, which must lie between the two values determined by the first random number
                            break
                        i += 1
                if self.building == "MFH":
                    random_nb = rd.random()  # picking random number in [0,1) to decide between which 2 values of consumption_range the annual electricity consumption lies
                    i = 1
                    while i <= 7:
                        if random_nb < sum(probabilities[:i]):
                            self.annual_el_demand[j] = rd.randint(consumption_range["MFH"][self.nb_occ[j]][i - 1], consumption_range["MFH"][self.nb_occ[j]][i])
                            # A random integer is selected as the current demand, which must lie between the two values determined by the first random number
                            break
                        i += 1
                if self.building == "AB":
                    random_nb = rd.random()  # picking random number in [0,1) to decide between which 2 values of consumption_range the annual electricity consumption lies
                    i = 1
                    while i <= 7:
                        if random_nb < sum(probabilities[:i]):
                            self.annual_el_demand[j] = rd.randint(consumption_range["MFH"][self.nb_occ[j]][i - 1], consumption_range["MFH"][self.nb_occ[j]][i])
                            # A random integer is selected as the current demand, which must lie between the two values determined by the first random number
                            break
                        i += 1

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
            illuminance_range = {
                "OB": (300, 650),
                "School": (300, 500),
                "Grocery_store": (500, 750),
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
                appliancesDemand = 0.904 * self.annual_el_demand[j]

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

    def calcProfiles(self, site, holidays, time_resolution, time_horizon, building, path, initial_day=1):
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
        #if building["unique_name"]

        if self.building in {"SFH","TH","MFH","AB"}:

            self.occ = np.zeros(int(time_horizon / time_resolution))
            self.dhw = np.zeros(int(time_horizon / time_resolution))
            self.elec = np.zeros(int(time_horizon / time_resolution))
            self.gains = np.zeros(int(time_horizon / time_resolution))
            self.car = np.zeros(int(time_horizon / time_resolution))
            if building['buildingFeatures']['building'] == "AB":
                unique_name = "MFH_" + str(building["user"].nb_flats) + "_" + str(building['buildingFeatures']['id'])
            elif building['buildingFeatures']['building'] == "TH":
                unique_name = "SFH_" + str(building["user"].nb_flats) + "_" + str(building['buildingFeatures']['id'])
            else:
                unique_name = building['unique_name']
            for j in range(self.nb_flats):
                temp_obj = Profiles(number_occupants=self.nb_occ[j], number_occupants_building=sum(self.nb_occ),initial_day=initial_day, nb_days=nb_days, time_resolution=time_resolution, building=self.building)
                self.dhw = self.dhw + temp_obj.generate_dhw_profile(building=building, holidays = holidays)
                # Occupancy profile in a flat
                self.occ = self.occ + temp_obj.generate_occupancy_profiles_residential()
                self.elec = self.elec + temp_obj.generate_el_profile_residential(holidays = holidays,
                                                                                 irradiance=irradiation,
                                                                                 el_wrapper=self.el_wrapper[j],
                                                                                 annual_demand=self.annual_el_demand[j])
                self.gains = self.gains + temp_obj.generate_gain_profile_residential()
            # currently only one car per building possible
            self.car = self.car + temp_obj.generate_EV_profile(self.occ)

        # ------ Webtool: import of existing time series to save computing time ------ #
        #self.occ = np.loadtxt(path + '/occ_' + unique_name + '.csv', delimiter=',')
        #self.car = np.loadtxt(path + '/car_' + unique_name + '.csv', delimiter=',')
        #self.elec = np.loadtxt(path + '/elec_' + unique_name + '.csv', delimiter=',')
        #self.gains = np.loadtxt(path + '/gains_' + unique_name + '.csv', delimiter=',')

        else:
            temp_obj = Profiles(number_occupants=round(statistics.mean(self.nb_occ)), number_occupants_building=sum(self.nb_occ),initial_day=initial_day, nb_days=nb_days, time_resolution=time_resolution,building=self.building)
            # Occupancy profile in the building
            _,self.occ,_ = temp_obj.generate_profiles_non_residential(holidays = holidays)
            self.elec = temp_obj.generate_el_profile_non_residential(irradiance=irradiation,el_wrapper=self.el_wrapper[0],annual_demand_app=self.annual_el_demand_zones)

            gains_persons, gains_others = temp_obj.generate_gain_profile_non_residential()
            self.gains = gains_persons + gains_others

            self.dhw = temp_obj.generate_dhw_profile(building=building, holidays=holidays)
            self.car = temp_obj.generate_EV_profile(self.occ)

#            gains_persons = np.zeros(int(time_horizon / time_resolution))
#            for j in range(self.nb_main_rooms):
#                temp_obj_persons = Profiles(self.nb_occ[j], initial_day, nb_days, time_resolution, self.building)
#                occ,_ = temp_obj_persons.generate_profiles_non_residential()
#                temp_gains_persons, _ = temp_obj_persons.generate_gain_profile_non_residential()
#                gains_persons += temp_gains_persons
#            _, temp_gains_others = temp_obj.generate_gain_profile_non_residential(gains_others = True)
#            gains_others = temp_gains_others
#            self.gains = gains_persons + gains_others

    def calcHeatingProfile(self, site, envelope, night_setback, holidays, time_resolution):
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
        Q_HC : float
            Heating (positive) or cooling (negative) load for the current time
            step in Watt.

        Returns
        -------
        None.
        """

        dt = time_resolution/(60*60)
        # calculate the temperatures (Q_HC, T_op, T_m, T_air, T_s)
        if night_setback==1:
            (Q_H, Q_C, T_op, T_m, T_i, T_s) = heating.calc_night_setback(envelope, site["T_e"], holidays, dt, self.building)
        elif night_setback==0:
            (Q_H, Q_C, T_op, T_m, T_i, T_s) = heating.calc(envelope, site["T_e"], holidays, dt, self.building)
        # heating and cooling loads for the current time step in Watt
        self.heat = Q_H
        self.cooling = Q_C
        self.annual_heat_demand = np.sum(Q_H)
        self.annual_cooling_demand = np.sum(Q_C)

    def saveProfiles(self, unique_name, path):
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

        np.savetxt(path + '/elec_' + unique_name + '.csv', self.elec, fmt='%1.2f', delimiter=',', header="Electricity demand in W", comments="")
        np.savetxt(path + '/dhw_' + unique_name + '.csv', self.dhw, fmt='%1.2f', delimiter=',', header="Drinking hot water in W", comments="")
        np.savetxt(path + '/occ_' + unique_name + '.csv', self.occ, fmt='%1.2f', delimiter=',', header="Occupancy of persons", comments="")
        np.savetxt(path + '/gains_' + unique_name + '.csv', self.gains, fmt='%1.2f', delimiter=',', header="Internal gains in W", comments="")
        np.savetxt(path + '/car_' + unique_name + '.csv', self.car, fmt='%1.2f', delimiter=',', header="Electricity demand of EV in W", comments="")

        '''
        fields = [name + "_" + str(id), str(sum(self.nb_occ))]
        with open(path + '/_nb_occupants.csv','a') as f :
            writer = csv.writer(f)
            writer.writerow(fields)
        '''

    def saveHeatingProfile(self, unique_name, path):
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

        np.savetxt(path + '/cooling_' + unique_name + '.csv', self.cooling, fmt='%1.2f', delimiter=',', header="Cooling demand in W", comments="")
        np.savetxt(path + '/heating_' + unique_name + '.csv', self.heat, fmt='%1.2f', delimiter=',', header="Heat demand in W", comments="")

    def loadProfiles(self, unique_name, path):
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

        self.elec = np.loadtxt(path + '/elec_' + unique_name + '.csv', delimiter=',', skiprows=1)
        self.dhw = np.loadtxt(path + '/dhw_' + unique_name + '.csv', delimiter=',', skiprows=1)
        self.occ = np.loadtxt(path + '/occ_' + unique_name + '.csv', delimiter=',', skiprows=1)
        self.gains = np.loadtxt(path + '/gains_' + unique_name + '.csv', delimiter=',', skiprows=1)
        self.car = np.loadtxt(path + '/car_' + unique_name + '.csv', delimiter=',', skiprows=1)


if __name__ == '__main__':

    test = Users(building="SFH",
                 area=1000)

    test.calcProfiles()
