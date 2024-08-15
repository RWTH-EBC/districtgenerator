# -*- coding: utf-8 -*-
"""
"""

import os, math
import json 
import random as rd
import numpy as np
import richardsonpy
import richardsonpy.classes.stochastic_el_load_wrapper as wrap
import richardsonpy.classes.appliance as app_model
import richardsonpy.classes.lighting as light_model
from districtgenerator.profils import Profiles , NonResidentialProfiles
import functions.heating_profile_5R1C as heating
import functions.schedule_reader as schedules
import functions.light_demand as light_demand
from districtgenerator.solar import SunIlluminance


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
    def __init__(self, building_usage, area, file, envelope, site, time, nb_of_days):
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
        self.nb_occ = []
        self.occ = None
        self.dhw = None
        self.elec = None
        self.gains = None
        self.heat = None
        self.occupancy_schedule = None
        self.appliance_schedule = None
        self.lighntning_schedule = None
        
        # Define the path to the JSON file
        base_path = os.getcwd()
        occupancy_json_path = os.path.join(base_path,  'data', 'occupancy_schedules', 
                                           'average_occupancy.json')
        electricity_json_path = os.path.join(base_path,  'data', 'consumption_data', 
                                             'average_electricity_per_occupants.json')

        # Load the JSON data from the specified path
        self.occupancy_data = self.load_json_data(occupancy_json_path)
        self.electricity_data = self.load_json_data(electricity_json_path)
        self.generate_schedules()


        # self.generate_number_flats(area)
        self.generate_number_occupants()
        self.generate_annual_el_consumption_equipment()
        self.generate_annual_el_consumption_lightning()
        # To-Do: Validate Sum of electricity
        self.elec = self.annual_appliance_demand + self.annual_lightning_demand
        # self.generate_lighting_index()
        # self.create_el_wrapper()

    
    def load_json_data(self, json_path):
        with open(json_path, 'r') as file:
            data = json.load(file)
            return data



    def generate_number_occupants(self):
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
                self.nb_occ.append(self.area/occupancy_values["Gering"])
                self.occupancy = "Gering"
            elif random_nb < 2 / 3:
                self.nb_occ.append(self.area/occupancy_values["Mittel"])
                self.occupancy = "Mittel"
            else:
                self.nb_occ.append(self.area/occupancy_values["Hoch"])
                self.occupancy = "Hoch"
        else:
            print(f"No data about number of occupants available for building type: {self.usage}")

    def generate_schedules(self):
        # get schedules occupancy
        df_schedules, schedule = schedules.get_schedule(self.usage)
        self.occupancy_schedule = schedules.adjust_schedule(inital_day= 0, schedule=df_schedules[["DAY", "HOUR", "OCCUPANCY"]], nb_days=self.nb_of_days)
        self.appliance_schedule =  schedules.adjust_schedule(inital_day= 0, schedule=df_schedules[["DAY", "HOUR", "APPLIANCES"]], nb_days=self.nb_of_days)
        self.lighntning_schedule = schedules.adjust_schedule(inital_day= 0, schedule=df_schedules[["DAY", "HOUR", "LIGHTING"]], nb_days=self.nb_of_days)

    
    def generate_occupancy(self):
        self.occ = self.occupancy_schedule["OCCUPANCY"] * self.nb_occ
        
    def generate_annual_el_consumption_equipment(self, equipment="Mittel"):
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
        # [1] S. Henning and K. Jagnow, “Statistische Untersuchung der Flächen- und Nutzstromanateile von Zonen in Nichtwohngebäuden (Fortführung),” 51/2023, Jul. 2023. [Online]. Available: https://www.bbsr.bund.de/BBSR/DE/veroeffentlichungen/bbsr-online/2023/bbsr-online-51-2023-dl.pdf?__blob=publicationFile&v=3
        # [2] K. Jagnow and S. Henning, “Statistische Untersuchung der Flächen- und Nutzstromanteile von Zonen in Nichtwohngebäuden,” Hochschule	Magdeburg-Stendal, Mar. 2020. [Online]. Available: https://www.h2.de/fileadmin/user_upload/Fachbereiche/Bauwesen/Forschung/Forschungsberichte/Endbericht_SWD-10.08.18.7-18.29.pdf


        
        if self.usage in self.electricity_data:
            electricity_values = self.electricity_data[self.usage]
            try: 
                annual_el_demand_temp = electricity_values[equipment] * self.area 
                self.annual_appliance_demand = rd.gauss(annual_el_demand_temp,
                                                        annual_el_demand_temp * 0.10)  # assumption: standard deviation 20% of mean value

            except KeyError:
                print(f"No data about annual electrical consumption available for building type: {self.usage}")
            # To Do 
            # Check if randomifaction of electriciy set up works  
        else:
            print(f"No data about annual electrical consumption available available for building type: {self.usage}")

    def generate_annual_el_consumption_lightning(self):
        """
        Creates 
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
        self.annual_lightning_demand = light_demand.calculate_light_demand(building_type=self.usage, illuminance=illuminance, 
                                                                           occupancy_schedule=self.occupancy_schedule, area=self.area)
    
    def generate_dhw_profile(self):
        """
        Generates a dhw profile
        Based on the TEK Ansatz and DIBS. 

        Generate a stochastic dhw profile
        (on base of pycity_base)

        Parameters
        ----------
        time_resolution : integer
            resolution of time steps of output array in seconds.
        activity_profile : array
            Numpy-arry with acctive occupants 10-minutes-wise.
        prob_profiles_dhw: array
            probabilities of dhw usage
        initial_day : integer
            Day of the week with which the generation starts
            1-7 for monday-sunday.

        Returns
        -------
        dhw_heat : array
            Numpy-array with heat demand of dhw consumption in W.

        """

        # Run simulation
        # run the simulation for just x days
        # therefor occupancy has to have the length of x days
        # TEK for Water and heat? 
        TEK_dhw, TEK_name = schedules.get_tek(self.usage)  # TEK_dhw in kWh/m2*a
        # To-Do,  Figure whty there is a 1000 in the formula
        # Code taken from DIBS and adjusted for
        # style and attributes to fit districtgenerator
        occupancy_full_usage_hours = self.occupancy_schedule["OCCUPANCY"].sum()  # in h/a
        TEK_dhw_per_Occupancy_Full_Usage_Hour = TEK_dhw / occupancy_full_usage_hours  # in kWh/m2*h

        self.dhw= self.occupancy_schedule["OCCUPANCY"] * TEK_dhw_per_Occupancy_Full_Usage_Hour * 1000 * self.area





    def calcProfiles(self, site, time_resolution, time_horizon, initital_day=1):
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
        
        # To-Do
        # Write a funtion, that get's occupancy data 
        # based on amount of occupants and SIA profiles 
        # Write Function that generates an lighning profile
        # Write DHW function

        #temp_obj = NonResidentialProfiles(building_type=self.usage, max_number_occupants=self.nb_occ, area=self.area,
        #                                  initital_day=initital_day, nb_days=nb_days, time_resolution=time_resolution)
        #self.occ = temp_obj.generate_occupancy_profiles()
        self.generate_dhw_profile()
        # Electircal profile needs to be generated for this 
        # Calculation of user demand + lighning + other 
        #self.elec = temp_obj.generate_el_profile(irradiance=irradiation,
        #                                         annual_demand=self.annual_elctric_demand, 
        #                                         appliance_demand=self.annual_appliance_demand,
        #                                         light_demand=self.annual_lightning_demand)
        self.calculate_gain_profile()
        self.generate_el_demand()
        self.generate_occupancy()
    
    def generate_el_demand(self, normalization=True):
        self.elec = self.annual_lightning_demand + self.annual_appliance_demand

        
    def calculate_gain_profile(self):
        """
        Generate profile of internal gains

        Parameters
        -------
        personGain : float
            Heat dissipation of one person
            Source: SIA 2024/2015 D - Raumnutzungsdaten für Energie- und Gebäudetechnik
        lightGain : float
            share of waste heat (LED)
            Source: Elsland, Rainer ; Peksen, Ilhan ; Wietschel, Martin: Are Internal Heat
            Gains Underestimated in Thermal Performance Evaluation of Buildings? In: Energy Procedia
            62 (2014), Januar, 32–41.
        appGain :
            share of waste heat (assumed)
            Source: Elsland, Rainer ; Peksen, Ilhan ; Wietschel, Martin: Are Internal Heat
            Gains Underestimated in Thermal Performance Evaluation of Buildings? In: Energy Procedia
            62 (2014), Januar, 32–41.
        occ_profile : float
             stochastic occupancy profiles for a district
        app_load : Array-like
            Electric load profile of appliances in W.
        light_load : Array-like
            Electric load profile of lighting in W.

        Returns
        -------
        gains : array
            Internal gain of each flat

        """
        # To - Do adjust to personal heat gains depending on builiding type 
        # To-Do: check that the correct data is used from SIA
        personGain = 70.0  # [Watt]
        lightGain = 0.65
        appGain = 0.33
        #To-Do: Write function to gather correct data

        self.gains = self.occupancy_schedule["OCCUPANCY"] * personGain + self.lighntning_schedule["LIGHTING"] * lightGain + self.appliance_schedule["APPLIANCES"] * appGain

        
        


    def calcHeatingProfile(self,site,envelope,time_resolution):

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
        (Q_HC, T_i, T_s, T_m, T_op) = heating.calculate(envelope,site["T_e"],dt)
        # heating  load for the current time step in Watt
        self.heat = np.zeros(len(Q_HC))
        for t in range(len(Q_HC)):
            self.heat[t] = max(0,Q_HC[t])

    def saveProfiles(self,unique_name,path):
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
        np.savetxt(path + '/elec_' + unique_name + '.csv', self.elec, fmt='%1.2f', delimiter=',')
        np.savetxt(path + '/dhw_' + unique_name + '.csv', self.dhw, fmt='%1.2f', delimiter=',')
        np.savetxt(path + '/occ_' + unique_name + '.csv', self.occ, fmt='%1.2f', delimiter=',')
        np.savetxt(path + '/gains_' + unique_name + '.csv', self.gains, fmt='%1.2f', delimiter=',')

        '''
        fields = [name + "_" + str(id), str(sum(self.nb_occ))]
        with open(path + '/_nb_occupants.csv','a') as f :
            writer = csv.writer(f)
            writer.writerow(fields)
        '''

    def saveHeatingProfile(self,unique_name,path) :
        '''
        Save heat demand to csv

        Parameters
        ----------
        unique_name : string
            unique building name
        path : string
            results path
        '''
        print(path)

        np.savetxt(path + '/heat_' + unique_name + '.csv',self.heat,fmt='%1.2f',delimiter=',')

    def loadProfiles(self,unique_name,path):
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

    test = Users(building="SFH",
                area=1000)

    test.calcProfiles()