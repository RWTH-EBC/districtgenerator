# -*- coding: utf-8 -*-
import json
import statistics
import os, math
import random as rd
import numpy as np
import pandas as pd
import openpyxl
from .profiles import Profiles
from . import power_simulation_non_residential as wrap_light
import richardsonpy
import richardsonpy.classes.stochastic_el_load_wrapper as wrap
import richardsonpy.classes.appliance as app_model
import richardsonpy.classes.lighting as light_model
import districtgenerator.functions._5R1C as heating_5R1C
import districtgenerator.functions._7R2C as heating_7R2C
from districtgenerator.classes.non_residential import GenericNonResidential

RES_BUILDINGS = {"SFH", "TH", "MFH", "AB"}

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

    @property
    def nb_units(self) -> int:
        """
        Unified number of 'units' in the building:
        - residential: number of flats
        - non-residential: number of main rooms
        """
        if self.is_residential:
            return int(self.nb_flats or 0)
        return int(self.nb_main_rooms or 0)

    @nb_units.setter
    def nb_units(self, value: int) -> None:
        if self.is_residential:
            self.nb_flats = int(value)
        else:
            self.nb_main_rooms = int(value)

    def __init__(self, building, area, year_of_construction, retrofit, SIA2024=None):
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
        self.EV_carprofile = None
        self.EV_carcharging_ondemand = None
        self.ev_capacity = None
        self.ice_carprofile = None
        self.individual_car_profiles = []
        self.has_ventilation = False # Usually no ventilation system in residential buildings.

        self.is_residential = self.building in RES_BUILDINGS

        # Initialize SIA class and read data
        self.SIA2024 = SIA2024
        if not self.is_residential:
            self.building_zones = self.SIA2024[self.building]
            self.nwg_config = GenericNonResidential(self.building) # Load configuration for non-residential building.

        self.generate_number_flats_and_rooms(area)
        self.generate_number_occupants(area)

        if self.is_residential:
            self.generate_annual_el_consumption_residential()
        else:
            self.generate_annual_app_el_consumption_non_residential(
                area, year_of_construction, retrofit)  # Annual electricity consumption of all devices including the electricity required for ventilation and excluding the electricity required for lighting

        self.generate_lighting_index(area, year_of_construction, retrofit)
        self.create_el_wrapper()

    def generate_number_flats_and_rooms(self, area):
        """
        Generate number of flats and main rooms for different building types.
        Possible building types are:
            - single family house (SFH)
            - terraced house (TH)
            - multifamily house (MFH)
            - apartment block (AB)
            - Defined non-residential building types (see non_residential_behavior.json and config.py)

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
            nb_rooms = 0
            # Primary zone is the main zone of the building, which is used to determine the mean area per main room for occupancy calculations.
            primary_main_zone = self.nwg_config.get_main_zone_name()

            if primary_main_zone is None:
                raise ValueError(f"Primary main zone not specified for building type '{self.building}' in non-residential behavior configuration. Cannot calculate number of main rooms.")

            # Find the mean area per main room for the primary main zone from the SIA2024 data.
            # This is used to estimate the number of main rooms in the building based on the total area of the building and the proportion of the area that is considered as main space.
            mean_area_per_main_room = None
            for data in self.SIA2024.values():
                if data.get('Zone_name_GER') == primary_main_zone:
                    mean_area_per_main_room = data.get('area_room')
                    break

            if mean_area_per_main_room is None:
                raise ValueError(f"Main zone '{primary_main_zone}' not found in SIA2024 data for building type '{self.building}'. Cannot calculate number of main rooms.")

            for number, data in self.SIA2024.items():
                zone_name = data.get('Zone_name_GER')
                if zone_name:
                    # Sum total rooms for the entire building
                    proportion = self.building_zones.get(zone_name, 0)
                    nb_rooms += area * proportion / data['area_room']

            self.nb_rooms = round(nb_rooms)

            proportion_main_space = sum(self.building_zones.get(zone, 0) for zone in self.nwg_config.get_main_room_zones())
            self.total_main_area = area * proportion_main_space
            self.nb_main_rooms = max(round(self.total_main_area / rd.gauss(mean_area_per_main_room, mean_area_per_main_room * 0.1)), 1)

            # Checks here and raise Exceptions if incosistant values are generated
            if proportion_main_space == 0:
                raise ValueError(f"Main space proportion is 0. Check 'main_room_zones' for '{self.building}'.")

            if self.nb_rooms < 1:
                raise ValueError(f"Calculated total rooms is 0 (due to small area). Building area must be larger.")

            if self.nb_main_rooms > self.nb_rooms:
                self.nb_main_rooms = self.nb_rooms # Number of main rooms limited by total rooms. Maybe a warning here?

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

        # --- Residential buildings ---

        if self.is_residential:
            # choose random number of occupants (1-5) for residential houses (assumption)
            # Probabilities of having 1, 2, 3, 4 or 5 occupants in a residential house, assuming a maximum of 5 occupants.
            # Sources: https://www.destatis.de/DE/Themen/Gesellschaft-Umwelt/Wohnen/Tabellen/tabelle-wo2-mietwohnungen.html
            #          https://www.destatis.de/DE/Themen/Gesellschaft-Umwelt/Wohnen/Tabellen/tabelle-wo2-eigentuemerwohnungen.html
            res_probs = {
                    "SFH": (0.245114, 0.402323, 0.154148, 0.148869, 0.049623),
                    "TH":  (0.236817, 0.400092, 0.157261, 0.154371, 0.051457),
                    "MFH": (0.490622, 0.307419, 0.101949, 0.074417, 0.024805),
                    "AB":  (0.490622, 0.307419, 0.101949, 0.074417, 0.024805)
                }
            probabilities = res_probs[self.building]

            for k in range(self.nb_flats):
                random_nb = rd.random() # picking random number in [0,1)
                for j in range(1, 6):
                    if random_nb < sum(probabilities[:j]):
                        self.nb_occ.append(j)
                        break
                else:
                    self.nb_occ.append(5)

        # --- Non-residential buildings ---
        else:

            # Calculate the area per occupant from SIA2024 data
            # The area per occupant [m²/person] is derived from:
            # area_per_occupant = W_per_person [W/person] / dQ_persons_perA [W/m²],
            # which represents the floor area associated with one person based on the
            # sensible heat gain per person and the internal heat gain density per area.

            primary_main_zone = self.nwg_config.get_main_zone_name()
            area_per_occupant = None
            for data in self.SIA2024.values():
                if data.get('Zone_name_GER') == primary_main_zone:
                    # area_per_occ [m²/P] = W_per_person [W/P] / dQ_persons_perA [W/m²]
                    w_per_p = float(data.get('W_per_person', None))
                    dq_per_a = float(data.get('dQ_persons_perA', None))

                    if w_per_p is None or dq_per_a is None:
                        raise ValueError(f"Missing 'W_per_person' or 'dQ_persons_perA' data for main zone '{primary_main_zone}' in SIA2024 data. Cannot calculate area per occupant.")
                    if w_per_p <= 0 or dq_per_a <= 0:
                        raise ValueError(f"'W_per_person' and 'dQ_persons_perA' must be positive values for main zone '{primary_main_zone}' in SIA2024 data. Cannot calculate area per occupant.")
                    if dq_per_a > 0:
                        area_per_occupant = w_per_p / dq_per_a
                    break

            if area_per_occupant is None:
                raise ValueError(f"Area per occupant could not be calculated for building type '{self.building}'. Check SIA2024 data for primary main zone '{primary_main_zone}'.")

            for k in range(self.nb_main_rooms):
                mean_occ = self.total_main_area / self.nb_main_rooms / area_per_occupant # Estimated number of occupants
                std_occ = (self.total_main_area / self.nb_main_rooms / area_per_occupant) * 0.15 # Assumption

                # Random number based on Gaussian distribution
                occ = round(rd.gauss(mean_occ, std_occ))
                self.nb_occ.append(max(occ, 0))  # Ensure minimum is 0

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
        if self.is_residential:
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
                            self.annual_el_demand_per_flat[j] = rd.randint(consumption_range["SFH"][self.nb_occ[j]][i - 1], consumption_range["SFH"][self.nb_occ[j]][i])
                            # A random integer is selected as the current demand, which must lie between the two values determined by the first random number
                            break
                        i += 1
                if self.building == "TH":
                    random_nb = rd.random()  # picking random number in [0,1) to decide between which 2 values of consumption_range the annual electricity consumption lies
                    i = 1
                    while i <= 7:
                        if random_nb < sum(probabilities[:i]):
                            self.annual_el_demand_per_flat[j] = rd.randint(consumption_range["SFH"][self.nb_occ[j]][i - 1], consumption_range["SFH"][self.nb_occ[j]][i])
                            # A random integer is selected as the current demand, which must lie between the two values determined by the first random number
                            break
                        i += 1
                if self.building == "MFH":
                    random_nb = rd.random()  # picking random number in [0,1) to decide between which 2 values of consumption_range the annual electricity consumption lies
                    i = 1
                    while i <= 7:
                        if random_nb < sum(probabilities[:i]):
                            self.annual_el_demand_per_flat[j] = rd.randint(consumption_range["MFH"][self.nb_occ[j]][i - 1], consumption_range["MFH"][self.nb_occ[j]][i])
                            # A random integer is selected as the current demand, which must lie between the two values determined by the first random number
                            break
                        i += 1
                if self.building == "AB":
                    random_nb = rd.random()  # picking random number in [0,1) to decide between which 2 values of consumption_range the annual electricity consumption lies
                    i = 1
                    while i <= 7:
                        if random_nb < sum(probabilities[:i]):
                            self.annual_el_demand_per_flat[j] = rd.randint(consumption_range["MFH"][self.nb_occ[j]][i - 1], consumption_range["MFH"][self.nb_occ[j]][i])
                            # A random integer is selected as the current demand, which must lie between the two values determined by the first random number
                            break
                        i += 1
                self.annual_el_demand += self.annual_el_demand_per_flat[j]
        else:
            raise ValueError("This method is only applicable for residential buildings. Use 'generate_annual_app_el_consumption_non_residential' for non-residential buildings.")

    def generate_annual_app_el_consumption_non_residential(self, area, year_of_construction, retrofit):             # Annual electricity consumption of all devices including the electricity required for ventilation and excluding the electricity required for lighting

        if self.is_residential:
            raise ValueError("This method is only applicable for non-residential buildings. Use 'generate_annual_el_consumption_residential' for residential buildings.")

        vent_factor = int(self.nwg_config.get_ventilation())

        # SIA 2024 energy performance levels:
        # - Standard: Standard values for new buildings
        # - Goal: Ambitious targets for highly efficient buildings
        # - Existing: Typical values for older, unrenovated buildings (older than 1980)
        # Decide mode based on the year of construction and retrofit status of the building

        # TODO: Check if logic is applicable, and if the standard deviation values are reasonable.
        if year_of_construction < 1980 and retrofit == 0:
            mode = 'existing'
            std_dev = 0.15 # 15%
        elif retrofit == 2:
            mode = 'goal'
            std_dev = 0.05 # 5%
        else:
            mode = 'standard'
            std_dev = 0.1 # 10%

        # Generate a single random factor for the entire building.
        rng = np.random.default_rng()
        random_factor = rng.normal(loc=1.0, scale=std_dev)

        for number, data in self.SIA2024.items():
            zone_name = data.get('Zone_name_GER')

            if not zone_name:
                continue

            proportion = self.building_zones.get(zone_name, 0)

            if proportion == 0:
                self.annual_el_demand_zones[zone_name] = 0
                continue


            yearly_demands = {
                'standard': data['E_devices_year_kwh']['standard'] + data['E_vent_year_kwh']['standard'] * vent_factor,
                'goal': data['E_devices_year_kwh']['goal'] + data['E_vent_year_kwh']['goal'] * vent_factor,
                'existing': data['E_devices_year_kwh']['existing'] + data['E_vent_year_kwh']['existing'] * vent_factor
            }

            if mode == 'existing':
                demand_randomized = max(yearly_demands[mode] * random_factor, yearly_demands['standard'])  # Ensure not better state than 'standard'
            elif mode == 'standard':
                demand_randomized = max(yearly_demands[mode] * random_factor, yearly_demands['goal'])  # Ensure not better state than 'goal'
            else:
                demand_randomized = max(yearly_demands[mode] * random_factor, 0)  # For 'goal' mode, only negative values are prevented. Maybe find a better lower bound

            annual_el_demand_zone = area * proportion * demand_randomized

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
            Floor area of the building in square meters.
        year_of_construction : int
            Year the building was constructed.
        retrofit : int
            Indicates if the building is retrofitted (0 = no, otherwise yes).

        Returns
        -------
        None.
        """

        # --- Residential buildings ---
        if self.is_residential:
            for j in range(self.nb_flats):
                self.lighting_index.append(int(rd.random() * 100))

        # --- Non-residential buildings ---
        else:
            file_name = "LightBulbs_nonresidential.json"
            # Source: https://www.umweltbundesamt.de/system/files/medien/1410/publikationen/2017-11-06_climate-change_26-2017_klimaneutraler-gebaeudebestand-ii.pdf
            # If the building was constructed before the year 2000 and has not been retrofitted
            # (indicated by `retrofit == 0`), select "combi_1" as the bulb configuration.
            if year_of_construction < 2000 and retrofit == 0:
                bulbs_combination =  "combi_1"
            # For buildings constructed in or after the year 2000, or for buildings that have been retrofitted
            # (indicated by any value other than 0 for `retrofit`), select "combi_2" as the bulb configuration.
            else:
                bulbs_combination = "combi_2"

            try:
                with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'non_residential',
                            file_name)) as json_file:
                    jsonData = json.load(json_file)
            except FileNotFoundError:
                print(f"Error: File '{file_name}' not found.")
                return

            # Process data for different building types
            selected_combination = jsonData.get(bulbs_combination, [])

            # Fetch dynamic illuminance range from config
            min_lux = self.nwg_config.get_min_illuminance()
            max_lux = self.nwg_config.get_max_illuminance()

            for _ in range(self.nb_rooms):
                room_illuminance = rd.randint(min_lux, max_lux)
                room_area = area / self.nb_rooms
                lm_needed = room_illuminance * room_area
                total_lm = 0
                # selected_lamps = []

                # Install random bulbs as long as the required luminous flux has not yet been reached.
                while total_lm < lm_needed:
                    lamp = rd.choice(selected_combination)
                    # selected_lamps.append(lamp)
                    total_lm += lamp["luminous_flux"]
                    self.bulbs_power.append(lamp["power"])

    def create_el_wrapper(self):
        """
        Create a wrapper-object
        holding information about the lighting and appliance configuration.

        Returns
        -------
        None.
        """
        if self.is_residential:
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
            self.el_wrapper.append(wrap_light.ElectricityProfile(lights, self.building))

    def calcProfiles(self, site, holidays, time_resolution, time_horizon, building, building_devices_data, path, initial_day, gen_cars=True):
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
        gen_cars : bool, optional if turned to false no car profiles are generated to improve perfomance if cars are not needed. The default is True.
            Be aware that setting it to false causes the simulation to not possess cars even if the scenario says so.

        Returns
        -------
        None.
        """

        if hasattr(self, 'create_el_wrapper'):
            self.create_el_wrapper()

        irradiation = site["SunTotal"]
        T_e = site["T_e"]

        time_day = 24 * 60 * 60
        nb_days = int(time_horizon/time_day)

        self.occ = np.zeros(int(time_horizon / time_resolution))
        self.dhw = np.zeros(int(time_horizon / time_resolution))
        self.elec = np.zeros(int(time_horizon / time_resolution))
        self.gains = np.zeros(int(time_horizon / time_resolution))
        self.EV_carprofile = np.zeros(int(time_horizon / time_resolution))
        self.EV_carcharging_ondemand = np.zeros(int(time_horizon / time_resolution))
        self.ev_capacity = [0.0]
        self.ice_carprofile = np.zeros(int(time_horizon / time_resolution))
        self.individual_car_profiles = []

        # Residential buildings
        if self.is_residential:

            current_index = 0  # To keep track of the starting index for car profiles Id in each flat
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

                # Calculate car profiles for residential buildings if gen_cars is True.
                if gen_cars:
                    (EV_carprofile, EV_on_demand_charging, ev_capacity,
                     ice_carprofile, individual_car_profiles) = temp_obj.generate_car_profile(
                         building=building,
                         building_devices_data=building_devices_data,
                         holidays=holidays,
                         start_index_car=current_index)

                    self.EV_carprofile = self.EV_carprofile + EV_carprofile  # Sum car profiles over all flats in the building
                    self.EV_carcharging_ondemand = self.EV_carcharging_ondemand + EV_on_demand_charging
                    self.ev_capacity += ev_capacity
                    self.ice_carprofile = self.ice_carprofile + ice_carprofile
                    self.individual_car_profiles.extend(individual_car_profiles)
                    current_index += len(individual_car_profiles)  # Update the starting index for the next flat of the building

        else:
            # Non-residential buildings
            school_holiday_days = set()
            if self.nwg_config.is_affected_by_school_holidays():
                # Define average school holiday day ranges (Julian days)
                SCHOOL_HOLIDAYS = [
                    range(94, 107),  # Osterferien
                    range(189, 233),  # Sommerferien
                    range(285, 298),  # Herbstferien
                    list(range(357, 366)) + list(range(1, 7)),  # Weihnachtsferien
                ]

                # Set for the school holiday days for later use in the profile generation
                for r in SCHOOL_HOLIDAYS:
                    school_holiday_days.update(r)

            holidays = set(holidays or [])
            holidays.update(school_holiday_days)
            holidays = sorted(list(holidays))  # keep format consistent

            temp_obj = Profiles(number_occupants=round(statistics.mean(self.nb_occ)), number_occupants_building=sum(self.nb_occ),initial_day=initial_day, nb_days=nb_days, time_resolution=time_resolution,building=self.building,SIA2024=self.SIA2024)
            # Occupancy profile in the building
            _,self.occ,_ = temp_obj.generate_profiles_non_residential(holidays = holidays)
            self.elec = temp_obj.generate_el_profile_non_residential(irradiance=irradiation,el_wrapper=self.el_wrapper[0],annual_demand_app=self.annual_el_demand_zones)

            gains_persons, gains_others = temp_obj.generate_gain_profile_non_residential()
            self.gains = gains_persons + gains_others

            self.dhw = temp_obj.generate_dhw_profile(building=building, holidays=holidays)

            # Calculate car profiles for non-residential buildings if gen_cars is True.
            if gen_cars:
                # Car calculation for every non-residential building
                (EV_carprofile, EV_on_demand_charging, ev_capacity,
                ice_carprofile, individual_car_profiles) = temp_obj.generate_car_profile(
                    building=building,
                    building_devices_data=building_devices_data,
                    holidays=holidays
                )
                self.EV_carprofile += EV_carprofile
                self.EV_carcharging_ondemand += EV_on_demand_charging
                self.ev_capacity += ev_capacity
                self.ice_carprofile += ice_carprofile
                self.individual_car_profiles.extend(individual_car_profiles)

    def calcHeatingProfile(self, site, envelope, thermal_model, night_setback, is_cooled, calendar, time_resolution, initial_day):
        """
        Calculate heat demand for each building.

        Parameters
        ----------
        site: dict
            Site data, e.g. weather.
        envelope: object
            Containing all physical data of the envelope.
        night_setback : integer
            1 if night setback is activated, 0 if not.
        is_cooled : integer
            1 if the building is actively cooled, 0 if not.
        calendar : dict
            Information about TRY (holidays, heating period, etc.).
        time_resolution : integer
            Resolution of time steps of output array in seconds.

        Outputs
        -------
        Q_H : float
            Heating load for the current time step in Watt.
        Q_C : float
            Cooling load for the current time step in Watt.

        Returns
        -------
        None.
        """

        dt = time_resolution / (60 * 60)

        local_calendar = calendar.copy()
        local_holidays = set(calendar.get("holidays", []) or [])

        # Extend holidays for schools
        school_holiday_days = set()
        if not self.is_residential:
            if self.nwg_config.is_affected_by_school_holidays():
                # Define average school holiday day ranges (Julian days)
                SCHOOL_HOLIDAYS = [
                    range(94, 107),  # Osterferien
                    range(189, 233),  # Sommerferien
                    range(285, 298),  # Herbstferien
                    list(range(357, 366)) + list(range(1, 7)),  # Weihnachtsferien
                ]

                # Set for the school holiday days for later use in the profile generation
                for r in SCHOOL_HOLIDAYS:
                    local_holidays.update(r)

        local_calendar["holidays"] = sorted(list(local_holidays))

        if thermal_model == "5R1C":
            heating = heating_5R1C
        elif thermal_model == "7R2C":
            heating = heating_7R2C
        else:
            raise ValueError(f"Unknown thermal_model_type: {thermal_model}")

        # calculate the temperatures (Q_HC, T_op, T_m, T_air, T_s)
        if night_setback == 1:
            (Q_H, Q_C, T_op, T_m, T_i, T_s) = heating.calc_night_setback(envelope, site["T_e"], local_calendar, dt, initial_day,
                                                                         self.building)
        elif night_setback == 0:
            (Q_H, Q_C, T_op, T_m, T_i, T_s) = heating.calc(envelope, site["T_e"], local_calendar, dt, initial_day, self.building)

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