# -*- coding: utf-8 -*-
"""
Written by Felix Rehmann, 2024
rehmann@tu-berlin.de
"""

import os, math
import json 
import random as rd
import numpy as np
from districtgenerator.profils import Profiles, NonResidentialProfiles
from districtgenerator.solar import SunIlluminance
import functions.heating_profile_5R1C as heating
import functions.schedule_reader as schedules
import functions.light_demand as light_demand
from typing import Dict, List, Any, Optional
import pandas as pd

current_file_path = os.path.abspath(__file__)
base_path = os.path.dirname(os.path.dirname(current_file_path))

class NonResidentialUsers():
    """
    A class for modeling non-residential building usage profiles, including occupancy, 
    electricity, and water heating demands based on the building's usage type and area. 
    This class leverages TEASER project data structures and is designed to support 
    energy analysis tasks.

    Parameters
    ----------
    building_usage : str
        The usage type of the building, which should match keys in occupancy and 
        electricity data files.
    area : float
        Total floor area of the building in square meters.
    file : str
        Path to the building envelope data file.
    envelope : object
        An object representing the physical envelope of the building including 
        attributes like windows, walls, and thermal properties.
    site : dict
        A dictionary containing site-specific data such as timezone, location, and 
        local climate data.
    time : dict
        A dictionary with time resolution and time steps for simulation.
    nb_of_days : int
        Number of days for which the simulation is to be run.

    Attributes
    ----------
    annual_appliance_demand : float
        The calculated annual demand for appliances in kWh.
    annual_lightning_demand : float
        The calculated annual lighting demand in kWh.
    nb_occ : list
        List of number of occupants based on building usage type.
    occ : np.array
        Occupancy profile for the building.
    dhw : np.array
        Daily hot water usage profile for the building.
    elec : np.array
        Electrical demand profile for the building.
    gains : np.array
        Internal gains from occupants, appliances, and lighting.
    heat : np.array
        Heating demand profile for the building.
    occupancy_schedule : np.array
        Scheduled occupancy profile based on typical usage patterns.
    appliance_schedule : np.array
        Scheduled appliance usage profile.
    lighntning_schedule : np.array
        Scheduled lighting usage profile.
    occupancy_data : dict
        Loaded occupancy data from JSON.
    electricity_data : dict
        Loaded electricity data from JSON.

    Methods
    -------
    load_json_data(json_path)
        Loads data from a JSON file located at the specified path.
    generate_number_occupants()
        Calculates the number of occupants based on building usage and area.
    generate_schedules()
        Generates daily usage schedules for occupancy, appliances, and lighting.
    generate_annual_el_consumption_equipment()
        Calculates annual electricity consumption for equipment based on building type.
    generate_annual_el_consumption_lightning()
        Calculates annual electricity consumption for lighting.
    generate_dhw_profile()
        Generates a daily hot water usage profile based on occupancy and building type.
    create_el_wrapper()
        Creates an electricity usage profile wrapper for lighting and appliances.
    calcProfiles(site, time_resolution, time_horizon, initital_day=1)
        Calculates and aggregates all profiles (occupancy, electricity, dhw, etc.) for the building.
    calcHeatingProfile(site, envelope, time_resolution)
        Calculates the heating demand for the building based on the envelope and site data.
    saveProfiles(unique_name, path)
        Saves generated profiles to CSV files.
    loadProfiles(unique_name, path)
        Loads profiles from previously saved CSV files.

    """
    def __init__(self, building_usage: str, area: float, file: str, envelope: Any,
                site: Dict[str, Any], time: Dict[str, Any], nb_of_days: int) -> None:
        """
        Constructor of Users Class
        """

        self.usage = building_usage 
        self.area = area
        self.file = file
        self.envelope = envelope
        
        self.site = site 
        self.time = time
        self.nb_of_days = nb_of_days
        #self.nb_flats = None
        self.annual_appliance_demand = None
        self.annual_lightning_demand = None
        self.appliance_demand = None
        self.lightning_demand = None
        self.nb_occ = []
        self.occ = None
        self.dhw = None
        self.elec = None
        self.gains = None
        self.heat = None
        self.cool = None
        self.occupancy_schedule = None
        self.appliance_schedule = None
        self.lighntning_schedule = None
        
        occupancyJsonPath = os.path.join(base_path, 'data', 'occupancy_schedules',
                                         'average_occupancy.json')
        electricityJsonPath = os.path.join(base_path, 'data', 'consumption_data',
                                           'average_electricity_per_occupants.json')

        # Load the JSON data from the specified path
        self.occupancy_data = self.load_json_data(occupancyJsonPath)
        self.electricity_data = self.load_json_data(electricityJsonPath)
        self.generate_schedules()


        # self.generate_number_flats(area)
        self.generate_number_occupants()
        # Match equipment to occupancy level
        self.generate_annual_el_consumption_equipment(equipment=self.occupancy)
        self.generate_annual_el_consumption_lightning()
        self.generate_el_demand()
        # To-Do: Validate Sum of electricity

    
    def load_json_data(self, json_path: str) -> Dict[str, Any]:
        """
        Load JSON data from the specified file path.

        Args:
            json_path (str): Path to the JSON file.

        Returns:
            Dict[str, Any]: Loaded JSON data as a dictionary.
        """
        with open(json_path, 'r', encoding='utf-8') as file:
            return json.load(file)


    def generate_number_occupants(self) -> None:
        '''
        Generate number of occupants for different of building types.
        According to the data in  data/occupancy_schedules/average_occupancy.json

        Parameters
        ----------
        random_nb : random number in [0,1)

        '''
        if self.usage in self.occupancy_data:
            occupancy_values = self.occupancy_data[self.usage]
            random_nb = rd.random()  # picking random number in [0,1)
            if random_nb < 1 / 3:
                self.nb_occ.append(round(self.area/occupancy_values["Gering"]))
                self.occupancy = "Gering"
            elif random_nb < 2 / 3:
                self.nb_occ.append(round(self.area/occupancy_values["Mittel"]))
                self.occupancy = "Mittel"
            else:
                self.nb_occ.append(round(self.area/occupancy_values["Hoch"]))
                self.occupancy = "Hoch"
        else:
            print(f"No data about number of occupants available for building type: {self.usage}")


    def generate_schedules(self) -> None:
        """
        Generate occupancy, appliance, and lighting schedules for the building.
        """
     
        df_schedules, schedule = schedules.getSchedule(self.usage)
        if df_schedules is not None:
            self.occupancy_schedule = schedules.adjust_schedule(initial_day= 0, schedule=df_schedules[["DAY", "HOUR", "OCCUPANCY"]], nb_days=self.nb_of_days)
            self.appliance_schedule =  schedules.adjust_schedule(initial_day= 0, schedule=df_schedules[["DAY", "HOUR", "APPLIANCES"]], nb_days=self.nb_of_days)
            self.lighntning_schedule = schedules.adjust_schedule(initial_day= 0, schedule=df_schedules[["DAY", "HOUR", "LIGHTING"]], nb_days=self.nb_of_days)
        else:
            print(f"No schedules found for {self.usage} and {schedule}")

    
    def generate_occupancy(self) -> None:
        """Generate occupancy profile based on schedule and number of occupants."""
        std_dev = self.occupancy_schedule["OCCUPANCY"] * 0.20
        random_multiplier = np.random.normal(   
            loc=self.occupancy_schedule["OCCUPANCY"],
            scale=std_dev
        )
        random_multiplier = np.clip(random_multiplier, a_min=0, a_max=None)
        self.occ = random_multiplier * self.nb_occ
        
    def generate_annual_el_consumption_equipment(self, equipment: str = "Mittel") -> None:
        '''
        Generate annual elictricity consumption in dependency of the building type and the average area. 
        
        Attributes
        ---------
        equipment - depending on the class of equipment, the electricity demand is caclulated. 
        Data is described in: data/consumption_data/info.txt
        Possible Values are: "Gering", "Mittel", "Hoch". Default is "Mittel. 
            "Gering": 4.5,
            "Mittel": 6.5,
            "Hoch": 23

        Parameters
        ----------
        standard_consumption : standard annual consumption in kWh (assumption)
         - dhw demand is not included 

        '''
        # For Residential buildings,
        # the Stromspiegel is used
        # In DIBS only electricity used for heating is simulated
        # Several approaches might be used for Non-Residential,
        # such as calculation bases on users, tasks, e.g. 
        # Here the calculation is done, based on the average equipment in the building type 
        # For more information see: 
        # [1] S. Henning and K. Jagnow, "Statistische Untersuchung der Flächen- und Nutzstromanateile von Zonen in Nichtwohngebäuden (Fortführung)," 51/2023, Jul. 2023. [Online]. Available: https://www.bbsr.bund.de/BBSR/DE/veroeffentlichungen/bbsr-online/2023/bbsr-online-51-2023-dl.pdf?__blob=publicationFile&v=3
        # [2] K. Jagnow and S. Henning, "Statistische Untersuchung der Flächen- und Nutzstromanteile von Zonen in Nichtwohngebäuden," Hochschule	Magdeburg-Stendal, Mar. 2020. [Online]. Available: https://www.h2.de/fileadmin/user_upload/Fachbereiche/Bauwesen/Forschung/Forschungsberichte/Endbericht_SWD-10.08.18.7-18.29.pdf


        
        if self.usage in self.electricity_data:
            electricity_values = self.electricity_data[self.usage]
            try: 
                # To-Do: Check if data is series
                # Units: electricity_values[equipment] in kWh/m2*a , self.area in m2
                # Hier Fehler da 
                annual_el_demand_temp = electricity_values[equipment] * self.area
                appliance_full_usage_hours = self.appliance_schedule["APPLIANCES"].sum()
                average_hourly_demand = annual_el_demand_temp / appliance_full_usage_hours
                # assumption: standard deviation 20% of mean value
                # Correct standard deviation to 20% as per the comment
                std_dev = self.appliance_schedule["APPLIANCES"] * 0.20
                random_multiplier = np.random.normal(
                    loc=self.appliance_schedule["APPLIANCES"],
                    scale=std_dev
                )
                random_multiplier = np.clip(random_multiplier, a_min=0, a_max=None)
                self.appliance_demand = average_hourly_demand * random_multiplier * 1000

            except KeyError:
                print(f"No data about annual electrical consumption available for building type: {self.usage}")
            except TypeError:
                print("Data was 0 for building type: {self.usage}")
        else:
            print(f"No data about annual electrical consumption available available for building type: {self.usage}")

    def generate_annual_el_consumption_lightning(self) -> None:
        """
        Creates the annual lightning demand.
        Calculates the illuminance on the windows and then calculates the lightning demand.

        """
        # Mapping cardinal directions to azimuth angles
        windows = self.envelope.A["window"] # ["window"]
        # Filter out the 'sum' key if present
        windows = {key: value for key, value in windows.items() if key not in  ['roof', 'floor', 'sum']}
        orientations = {
            'north': 0,
            'east': 90,
            'south': 180,
            'west': 270
        }

        beta = [90] * len(windows)  # tilt for all windows
        gamma = [orientations[key] for key in windows.keys()]  # azimuths based on orientation
        Sun = SunIlluminance(filePath=self.envelope.file_path)
        illuminance = Sun.calcIlluminance(initialTime=0, timeDiscretization=self.time["timeResolution"],
                                          timeSteps=self.time["timeSteps"], timeZone=self.site["timeZone"], location=self.site["location"], altitude=self.site["altitude"],
                                          beta=beta, gamma=gamma,
                                          normal_direct_illuminance=self.site["IlluminanceDirect"], 
                                          horizontal_diffuse_illuminance=self.site["IlluminaceDiffuse"])
        

        # To-Do: 
        # Calculate Energy Demand throuhg lighning
        self.lightning_demand = light_demand.calculate_light_demand(building_type=self.usage, illuminance=illuminance,
                                                                   occupancy_schedule=self.occupancy_schedule, area=self.area)
        
        self.annual_lightning_demand = self.lightning_demand.sum() / 1000
        
    
    def generate_dhw_profile(self) -> None:
        """
        Generates a dhw profile
        Based on the TEK Ansatz and DIBS. 
        Original data by: BBSR 
        https://www.bbsr.bund.de/BBSR/DE/forschung/programme/zb/Auftragsforschung/5EnergieKlimaBauen/2019/vergleichswerte-nwg/01-start.html?pos=2

        Returns
        -------
        dhw : array
            Numpy-array with heat demand of dhw consumption in W.

        """

        # Run simulation
        # run the simulation for just x days
        # therefor occupancy has to have the length of x days
        # TEK for Water and heat? 
        TEK_dhw, TEK_name = schedules.get_tek(self.usage)  # TEK_dhw in kWh/m2*a
        # Code taken from DIBS and adjusted for
        # style and attributes to fit districtgenerator
        # https://www.iwu.de/fileadmin/publikationen/energie/tektool/2014_IWU_H%C3%B6rnerEtAl_Teilenergiekennwerte%E2%80%93Neue-Wege-in-der-Energieanalyse-von-Nichtwohngeb%C3%A4uden-im-Bestand.pdf
        if TEK_dhw is not None:
            occupancy_full_usage_hours = self.occupancy_schedule["OCCUPANCY"].sum()  # in h/a
            TEK_dhw_per_Occupancy_Full_Usage_Hour = TEK_dhw / occupancy_full_usage_hours  # in kWh/m2*a / h/a = kW/m2
            self.dhw = self.occupancy_schedule["OCCUPANCY"] * TEK_dhw_per_Occupancy_Full_Usage_Hour * 1000 * self.area
        else:
            print(f"No data about annual dhw consumption available for building type: {self.usage}. DHW demand is set to zero.")
            self.dhw = np.zeros(len(self.occupancy_schedule))



    def calcProfiles(self, site: Dict[str, Any], time_resolution: int, 
                     time_horizon: int, initital_day: int = 1) -> None:
        '''
        Calclulate profiles for every flat and summarize them for the whole building

        Parameters
        ----------
        site: dict
            site data, e.g. weather
        initial_day : integer
            Day of the week with which the generation starts
            1-7 for monday-sunday.
        time_horizon : integer
            Time horizon for which a stochastic profile is generated.
        time_resolution : integer
            resolution of time steps of output array in seconds.
        irradiation: array
            if none is given default weather data (TRY 2015 Potsdam) is used


        '''

        irradiation = site["SunTotal"]
        T_e = site["T_e"]

        time_day = 24 * 60 * 60
        nb_days = int(time_horizon/time_day)

        self.occ = np.zeros(int(time_horizon/time_resolution))
        self.dhw = np.zeros(int(time_horizon/time_resolution))
        self.elec = np.zeros(int(time_horizon/time_resolution))
        self.gains = np.zeros(int(time_horizon/time_resolution))
        self.generate_occupancy()
        self.generate_dhw_profile()
        self.generate_el_demand()
        self.calculate_gain_profile()
    
    def generate_el_demand(self, normalization: bool = True) -> None:
        """
        Generate electricity demand.

        Returns: numpy array
            Electricity demand in W.
        """
        # To-Do: Implement process demand
        self.elec = self.lightning_demand + self.appliance_demand

        
    def calculate_gain_profile(self) -> None:
        """
        Generate profile of internal gains

        Parameters
        -------
        personGain : float
            Heat dissipation of one person
            q_I_p in Multi_zone_averag typology
        lightGain : float
            share of waste heat (LED)
            Source: Elsland, Rainer ; Peksen, Ilhan ; Wietschel, Martin: Are Internal Heat
            Gains Underestimated in Thermal Performance Evaluation of Buildings? In: Energy Procedia
            62 (2014), Januar, 32–41.
        appGain :
            share of waste heat (assumed)
            q_I_p in Multi_zone_averag typology 
        self.occ : float
             stochastic occupancy profiles for a district
        self.appliance_demand : Array-like
            Electric load profile of appliances in W.
        self.lightning_demand : Array-like
            Electric load profile of lighting in W.

        Returns
        -------
        gains : array
            Internal gain of each building.
        """
        
        # To-Do: check that the correct data is used from SIA
        # These are default values for residential buildings
        # To-Do: Check Units 
        # Use Dibs documentaiton https://iwugermany.github.io/dibs/

        personGain = 70.0  # [Watt]
        lightGain = 0.65 # [Watt]
        appGain = 0.33 # Watt
        
         # q_I_p = personGain
        # lightGain = constant value for all buildings
        # q_I_fac = appGain  
        # data\multi_zone_average\info.txt
        q_I_p, q_I_fac, multi_zone_name = schedules.get_multi_zone_average(self.usage)
        if q_I_p is not None:
            # Unit is Wh/m2d 
            # Convert to W/m2
            personGain = q_I_p / 24
        else:
            print(f"No data about person gains available for building type: {self.usage}")
        if q_I_fac is not None:
            # Unit is Wh/m2d 
            # Convert to W/m2
            appGain = q_I_fac / 24
        else:
            print(f"No data about appliance gains available for building type: {self.usage}")
        
        # occupancy schedule is in people , person gain in W/person 
        # Light schedule is in  light gain in W/m2
        # Check unit for light demand
        # Appliance schedule in W/m2, appliance gain in W/m2

        self.gains =  (
            self.occ *  personGain 
            + self.lightning_demand * lightGain 
            + self.appliance_demand * appGain
        )
        if self.gains.sum() < 0:
            print("Internal gains are negative. This migth be due to cooling devices.")


    def calcHeatingProfile(self, site: Dict[str, Any], 
                           envelope: Any, time_resolution: int) -> None:

        '''
        Calclulate heat demand for each building

        Parameters
        ----------
        site: dict
            site data, e.g. weather
        envelope: object
            containing all physical data of the envelope
        time_resolution : integer
            resolution of time steps of output array in seconds.
        Q_HC : float
            Heating (positive) or cooling (negative) load for the current time
            step in Watt.

        '''
        
        dt = time_resolution/(60*60)
        # calculate the temperatures (Q_HC, T_op, T_m, T_air, T_s)
        (Q_HC, T_i, T_s, T_m, T_op) = heating.calculate(envelope, envelope.T_set_min, site["T_e"], dt)
        # heating  load for the current time step in Watt
        self.heat = np.zeros(len(Q_HC))
        self.heat = np.maximum(0, Q_HC)

        (Q_HC, T_i, T_s, T_m, T_op) = heating.calculate(envelope, envelope.T_set_max, site["T_e"], dt)
        # Cooling load for the current time step in Watt
        self.cool = np.zeros(len(Q_HC))
        self.cool = np.minimum(0, Q_HC)

            
    def saveProfiles(self,unique_name: str,path: str) -> None:
        '''
        Save profiles to csv

        Parameters
        ----------
        unique_name : string
            unique building name
        path : string
            results path
        '''
        if not os.path.exists(path):
            os.makedirs(path)
 
        data = pd.DataFrame({
            'elec': self.elec,
            'dhw': self.dhw,
            'occ': self.occ,
            'gains': self.gains,
            'heat': self.heat,
            'cool': self.cool  
        })
        data.to_csv(os.path.join(path, f'{unique_name}.csv'), index=False)

        '''
        fields = [name + "_" + str(id), str(sum(self.nb_occ))]
        with open(path + '/_nb_occupants.csv','a') as f :
            writer = csv.writer(f)
            writer.writerow(fields)
        '''

    def loadProfiles(self,unique_name: str,path: str) -> None:
        '''
        Load profiles from csv

        Parameters
        ----------
        unique_name : string
            unique building name
        path : string
            results path
        '''

        self.elec = np.loadtxt(path + '/elec_' + unique_name + '.csv', delimiter=',')
        self.dhw = np.loadtxt(path + '/dhw_' + unique_name + '.csv', delimiter=',')
        self.occ = np.loadtxt(path + '/occ_' + unique_name + '.csv', delimiter=',')
        self.gains = np.loadtxt(path + '/gains_' + unique_name + '.csv', delimiter=',')


    

if __name__ == '__main__':

    from districtgenerator.envelope import Envelope
    from districtgenerator.non_residential import NonResidential
    from districtgenerator.datahandler import weather_handling

    # Define building parameters
    building_params = {
        'id' : 0,
        "year": 2000,  # Example year, adjust as needed
        "retrofit": 0,
        'building' : "IWU Hotels, Boarding, Restaurants or Catering",
        'area' : 100
    }
    nrb_prj = NonResidential(
                        usage=building_params["building"],
                        name="IWUNonResidentialBuilding",
                        year_of_construction=building_params["year"],
                        number_of_floors=3,
                        height_of_floors=3,
                        net_leased_area=building_params["area"])
                # %% create envelope object
                # containing all physical data of the envelope
                
    envelope = Envelope(prj=nrb_prj,building_params=building_params,
                        construction_type=None,
                        file_path = r"C:/Users/felix/Programmieren/tecdm/src/districtgenerator/data")
   


    site = {}
    # Define other parameters
    with open(os.path.join(r"C:/Users/felix/Programmieren/tecdm/src/districtgenerator/data", 'site_data.json')) as json_file:
        jsonData = json.load(json_file)
        for subData in jsonData:
            site[subData["name"]] = subData["value"]

    time = {}
    with open(os.path.join(r"C:/Users/felix/Programmieren/tecdm/src/districtgenerator/data", 'time_data.json')) as json_file:
        jsonData = json.load(json_file)
        for subData in jsonData:
            time[subData["name"]] = subData["value"]

    time["timeSteps"] = int(time["dataLength"] / time["timeResolution"])
    weather_file = r'C:\Users\felix\Programmieren\tecdm\src\districtgenerator\data\weather\EPW\AMY_2010_2022_2021.epw'
    weatherData = weather_handling.getEpWeather(weather_file)
    weatherData = pd.concat([weatherData.iloc[[-1]], weatherData]).reset_index(drop=True)
    temp_sunDirect = weatherData["Direct Normal Radiation"].to_numpy()
    temp_sunDiff = weatherData["Diffuse Horizontal Radiation"].to_numpy()
    temp_temp = weatherData["Dry Bulb Temperature"].to_numpy()
    direct_illuminance = weatherData["Direct Normal Illuminance"].to_numpy()
    diffuse_illuminance = weatherData["Diffuse Horizontal Illuminance"].to_numpy()
    site["IlluminanceDirect"] = np.interp(np.arange(0, time["dataLength"]+1, time["timeResolution"]),
                                                np.arange(0, time["dataLength"]+1, time["dataResolution"]),
                                                direct_illuminance)[0:-1]
                
    site["IlluminaceDiffuse"] = np.interp(np.arange(0, time["dataLength"]+1, time["timeResolution"]),
                                                np.arange(0, time["dataLength"]+1, time["dataResolution"]),
                                                diffuse_illuminance)[0:-1]

    site["SunDirect"] = np.interp(np.arange(0, time["dataLength"]+1, time["timeResolution"]),
                                           np.arange(0, time["dataLength"]+1, time["dataResolution"]),
                                           temp_sunDirect)[0:-1]
    site["SunDiffuse"] = np.interp(np.arange(0, time["dataLength"]+1, time["timeResolution"]),
                                           np.arange(0, time["dataLength"]+1, time["dataResolution"]),
                                           temp_sunDiff)[0:-1]
    site["T_e"] = np.interp(np.arange(0, time["dataLength"]+1, time["timeResolution"]),
                                     np.arange(0, time["dataLength"]+1, time["dataResolution"]),
                                     temp_temp)[0:-1]
    site["SunTotal"] = site["SunDirect"] + site["SunDiffuse"]
    test = NonResidentialUsers(building_usage=building_params["building"],
                area=1000, file="", envelope=envelope, site=site, time=time, nb_of_days=365)
    
    test.calcProfiles(site=site, time_resolution=time["timeResolution"], time_horizon=time["dataLength"])

    envelope.calcNormativeProperties(SunRad=site["SunTotal"], internal_gains=test.gains)
    test.calcHeatingProfile(site=site, envelope=envelope, time_resolution=time["timeResolution"])

